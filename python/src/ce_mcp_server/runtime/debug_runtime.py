from __future__ import annotations

from ..context import RuntimeModule

DEBUG_RUNTIME = RuntimeModule(
    name="debug",
    version="2026.03.08.4",
    script=r'''
_G.__ce_mcp = _G.__ce_mcp or {}
_G.__ce_mcp_modules = _G.__ce_mcp_modules or {}
local root = _G.__ce_mcp
root.debug = root.debug or { watches = {}, next_id = 1 }
local M = root.debug
M.needs_rebuild = M.needs_rebuild or false

local TRIGGERS = {
  execute = bptExecute,
  access = bptAccess,
  write = bptWrite,
}

local METHODS = {
  int3 = bpmInt3,
  debug_register = bpmDebugRegister,
  exception = bpmException,
}

local CONTINUE_OPTIONS = {
  run = co_run,
  step_into = co_stepinto,
  step_over = co_stepover,
}

local REGISTER_NAMES = {
  'RIP', 'EIP', 'RAX', 'EAX', 'RBX', 'EBX', 'RCX', 'ECX', 'RDX', 'EDX',
  'RSI', 'ESI', 'RDI', 'EDI', 'RBP', 'EBP', 'RSP', 'ESP',
  'R8', 'R9', 'R10', 'R11', 'R12', 'R13', 'R14', 'R15'
}

local function resolve_address(address)
  if type(address) == 'number' then
    return address
  end

  local resolved = getAddressSafe(address)
  if resolved == nil then
    error('debug_address_not_found')
  end
  return resolved
end

local function normalize_trigger(value)
  if value == nil then
    return bptAccess
  end
  if type(value) == 'number' then
    return value
  end
  local key = string.lower(tostring(value))
  if TRIGGERS[key] == nil then
    error('invalid_breakpoint_trigger:' .. key)
  end
  return TRIGGERS[key]
end

local function normalize_method(value)
  if value == nil or tostring(value) == '' then
    return nil
  end
  if type(value) == 'number' then
    return value
  end
  local key = string.lower(tostring(value))
  if METHODS[key] == nil then
    error('invalid_breakpoint_method:' .. key)
  end
  return METHODS[key]
end

local function normalize_continue_option(value)
  if value == nil then
    return co_run
  end
  if type(value) == 'number' then
    return value
  end
  local key = string.lower(tostring(value))
  if CONTINUE_OPTIONS[key] == nil then
    error('invalid_continue_option:' .. key)
  end
  return CONTINUE_OPTIONS[key]
end

local function snapshot_registers()
  local registers = {}
  pcall(function() debug_getContext() end)
  for _, register_name in ipairs(REGISTER_NAMES) do
    local value = rawget(_G, register_name)
    if value ~= nil then
      registers[string.lower(register_name)] = value
    end
  end
  return registers
end

local function current_instruction_pointer(registers)
  if registers.rip ~= nil then
    return registers.rip
  end
  return registers.eip
end

local function serialize_breakpoint_list()
  local breakpoints = debug_getBreakpointList()
  if type(breakpoints) ~= 'table' then
    return {}
  end
  return breakpoints
end

local function breakpoint_registered(address)
  local breakpoints = serialize_breakpoint_list()
  for _, breakpoint in ipairs(breakpoints) do
    if breakpoint == address then
      return true
    end
    if type(breakpoint) == 'table' and tonumber(breakpoint.address) == address then
      return true
    end
  end
  return false
end

local function ensure_debugger_started(interface)
  local requested_interface = tonumber(interface)
  if requested_interface == nil or requested_interface == 0 then
    requested_interface = 2
  end
  if not debug_isDebugging() then
    debugProcess(requested_interface)
  end
  if not debug_isDebugging() then
    error('debugger_start_failed:' .. tostring(requested_interface))
  end
  return requested_interface
end

local function install_watch_breakpoint(watch)
  local call_ok, result
  if watch.method == nil then
    call_ok, result = pcall(debug_setBreakpoint, watch.address, watch.size, watch.trigger, watch.callback)
  else
    call_ok, result = pcall(debug_setBreakpoint, watch.address, watch.size, watch.trigger, watch.method, watch.callback)
  end
  if not call_ok then
    error('debug_setBreakpoint_failed')
  end
  if result == false and not breakpoint_registered(watch.address) then
    error('debug_setBreakpoint_failed')
  end
end

local function collect_active_watches()
  local active_watches = {}
  for _, watch in pairs(M.watches) do
    if watch.active then
      active_watches[#active_watches + 1] = watch
    end
  end
  table.sort(active_watches, function(left, right) return left.id < right.id end)
  return active_watches
end

local function compare_serialized_breakpoints(left, right)
  local left_address = tonumber(left.address) or -1
  local right_address = tonumber(right.address) or -1
  if left_address ~= right_address then
    return left_address < right_address
  end

  local left_source = tostring(left.source or '')
  local right_source = tostring(right.source or '')
  if left_source ~= right_source then
    return left_source < right_source
  end

  return tostring(left.watch_id or '') < tostring(right.watch_id or '')
end

local function serialize_effective_raw_breakpoint(entry)
  local result = {
    source = 'ce_raw_breakpoint',
    reported_by_ce = true,
  }

  if type(entry) == 'number' then
    result.address = entry
    return result
  end

  if type(entry) == 'table' then
    for key, value in pairs(entry) do
      result[key] = value
    end
    if result.address == nil then
      result.address = tonumber(entry.address)
    end
    return result
  end

  result.value = entry
  return result
end

local function serialize_active_watch_breakpoint(watch, raw_visible)
  return {
    source = 'ce_mcp_watch',
    watch_id = watch.id,
    address = watch.address,
    size = watch.size,
    trigger = watch.trigger_name,
    method = watch.method_name,
    active = watch.active and true or false,
    max_hits = watch.max_hits,
    hit_count = #watch.hits,
    debugger_interface = watch.debugger_interface,
    reported_by_ce = raw_visible and true or false,
  }
end

local function summarize_effective_breakpoints()
  local raw_entries = serialize_breakpoint_list()
  local raw_breakpoints = {}
  local raw_address_counts = {}
  for _, entry in ipairs(raw_entries) do
    raw_breakpoints[#raw_breakpoints + 1] = serialize_effective_raw_breakpoint(entry)
    local address = nil
    if type(entry) == 'number' then
      address = entry
    elseif type(entry) == 'table' then
      address = tonumber(entry.address)
    end
    if address ~= nil then
      raw_address_counts[address] = (raw_address_counts[address] or 0) + 1
    end
  end

  local active_watches = collect_active_watches()
  local watch_breakpoints = {}
  local active_watch_addresses = {}
  for _, watch in ipairs(active_watches) do
    active_watch_addresses[watch.address] = (active_watch_addresses[watch.address] or 0) + 1
    watch_breakpoints[#watch_breakpoints + 1] = serialize_active_watch_breakpoint(
      watch,
      (raw_address_counts[watch.address] or 0) > 0
    )
  end
  table.sort(watch_breakpoints, compare_serialized_breakpoints)

  local effective_breakpoints = {}
  for _, watch_breakpoint in ipairs(watch_breakpoints) do
    effective_breakpoints[#effective_breakpoints + 1] = watch_breakpoint
  end
  for _, raw_breakpoint in ipairs(raw_breakpoints) do
    local address = tonumber(raw_breakpoint.address)
    if address == nil or (active_watch_addresses[address] or 0) == 0 then
      effective_breakpoints[#effective_breakpoints + 1] = raw_breakpoint
    end
  end
  table.sort(effective_breakpoints, compare_serialized_breakpoints)

  return {
    count = #effective_breakpoints,
    breakpoints = effective_breakpoints,
    raw_count = #raw_breakpoints,
    raw_breakpoints = raw_breakpoints,
    active_watch_count = #watch_breakpoints,
    watch_breakpoints = watch_breakpoints,
    count_strategy = 'effective',
  }
end

local function rebuild_active_breakpoints(interface_hint)
  if type(detachIfPossible) == 'function' then
    pcall(detachIfPossible)
  end

  local active_watches = collect_active_watches()
  if #active_watches == 0 then
    M.needs_rebuild = false
    return {remaining = 0, debugger_interface = tonumber(interface_hint) or 2}
  end

  local requested_interface = tonumber(interface_hint)
  if requested_interface == nil or requested_interface == 0 then
    for _, watch in ipairs(active_watches) do
      if tonumber(watch.debugger_interface) ~= nil and tonumber(watch.debugger_interface) ~= 0 then
        requested_interface = tonumber(watch.debugger_interface)
        break
      end
    end
  end
  requested_interface = ensure_debugger_started(requested_interface)

  if debug_isBroken() then
    pcall(function() debug_continueFromBreakpoint(co_run) end)
  end

  for _, watch in ipairs(active_watches) do
    install_watch_breakpoint(watch)
  end

  M.needs_rebuild = false
  return {
    remaining = #active_watches,
    debugger_interface = requested_interface,
  }
end

local function sync_breakpoints_if_needed(interface_hint)
  if M.needs_rebuild then
    rebuild_active_breakpoints(interface_hint)
  end
end

local function serialize_watch(watch, include_hits, limit)
  if watch == nil then
    return nil
  end

  local result = {
    watch_id = watch.id,
    address = watch.address,
    size = watch.size,
    trigger = watch.trigger_name,
    method = watch.method_name,
    active = watch.active and true or false,
    max_hits = watch.max_hits,
    hit_count = #watch.hits,
  }

  if include_hits then
    local hits = {}
    local capped = math.min(#watch.hits, limit or #watch.hits)
    for index = 1, capped do
      hits[#hits + 1] = watch.hits[index]
    end
    result.returned_count = #hits
    result.truncated = #watch.hits > #hits
    result.hits = hits
  end

  return result
end

function M.status()
  sync_breakpoints_if_needed()
  local breakpoint_summary = summarize_effective_breakpoints()
  local watches = {}
  for _, watch in pairs(M.watches) do
    watches[#watches + 1] = serialize_watch(watch, false)
  end
  table.sort(watches, function(left, right) return left.watch_id < right.watch_id end)

  return {
    is_debugging = debug_isDebugging() and true or false,
    can_break = debug_canBreak() and true or false,
    is_broken = debug_isBroken() and true or false,
    current_interface = debug_getCurrentDebuggerInterface(),
    breakpoint_count = breakpoint_summary.count,
    breakpoints = breakpoint_summary.breakpoints,
    raw_breakpoint_count = breakpoint_summary.raw_count,
    raw_breakpoints = breakpoint_summary.raw_breakpoints,
    active_watch_count = breakpoint_summary.active_watch_count,
    watch_breakpoints = breakpoint_summary.watch_breakpoints,
    breakpoint_count_strategy = breakpoint_summary.count_strategy,
    watches = watches,
  }
end

function M.start(interface)
  local requested_interface = ensure_debugger_started(interface)
  sync_breakpoints_if_needed(requested_interface)
  local status = M.status()
  status.requested_interface = requested_interface
  return status
end

function M.continue_execution(continue_option)
  if debug_isBroken() then
    debug_continueFromBreakpoint(normalize_continue_option(continue_option))
  end
  return {
    continued = true,
    continue_option = continue_option or 'run',
    is_broken = debug_isBroken() and true or false,
  }
end

function M.list_breakpoints()
  sync_breakpoints_if_needed()
  return summarize_effective_breakpoints()
end

function M.watch_start(address, size, trigger, method, max_hits, auto_continue, debugger_interface)
  local requested_interface = ensure_debugger_started(debugger_interface)
  sync_breakpoints_if_needed(requested_interface)

  local resolved_address = resolve_address(address)
  local normalized_trigger = normalize_trigger(trigger)
  local normalized_method = normalize_method(method)
  local watch = {
    id = 'watch-' .. tostring(M.next_id),
    address = resolved_address,
    size = tonumber(size) or 1,
    trigger = normalized_trigger,
    trigger_name = tostring(trigger or 'access'),
    method = normalized_method,
    method_name = normalized_method ~= nil and tostring(method) or 'default',
    max_hits = tonumber(max_hits) or 32,
    active = true,
    hits = {},
    auto_continue = auto_continue ~= false,
    callback = nil,
    debugger_interface = requested_interface,
  }
  M.next_id = M.next_id + 1

  local function on_breakpoint()
    if not watch.active then
      if watch.auto_continue and debug_isBroken() then
        debug_continueFromBreakpoint(co_run)
        return 1
      end
      return 0
    end

    local registers = snapshot_registers()
    local instruction_pointer = current_instruction_pointer(registers)
    local instruction = nil
    if instruction_pointer ~= nil then
      pcall(function() instruction = disassemble(instruction_pointer) end)
    end

    watch.hits[#watch.hits + 1] = {
      hit_index = #watch.hits + 1,
      address = watch.address,
      instruction_pointer = instruction_pointer,
      instruction = instruction,
      registers = registers,
    }

    if #watch.hits >= watch.max_hits then
      watch.active = false
      M.needs_rebuild = true
    end

    if watch.auto_continue and debug_isBroken() then
      debug_continueFromBreakpoint(co_run)
      return 1
    end
    return 0
  end

  watch.callback = on_breakpoint
  M.watches[watch.id] = watch

  local install_ok = pcall(install_watch_breakpoint, watch)
  if not install_ok then
    M.watches[watch.id] = nil
    error('debug_setBreakpoint_failed')
  end

  return {
    watch = serialize_watch(watch, false),
    status = M.status(),
  }
end

function M.watch_get_hits(watch_id, limit)
  local watch = M.watches[tostring(watch_id)]
  if watch == nil then
    error('debug_watch_not_found:' .. tostring(watch_id))
  end
  sync_breakpoints_if_needed(watch.debugger_interface)
  return serialize_watch(watch, true, tonumber(limit) or #watch.hits)
end

function M.watch_stop(watch_id)
  local watch = M.watches[tostring(watch_id)]
  if watch == nil then
    return {stopped = false, watch_id = tostring(watch_id)}
  end
  watch.active = false
  M.watches[tostring(watch_id)] = nil
  M.needs_rebuild = true
  rebuild_active_breakpoints(watch.debugger_interface)
  return {
    stopped = true,
    watch_id = tostring(watch_id),
    hit_count = #watch.hits,
  }
end

function M.watch_stop_all()
  local stopped = {}
  for watch_id, watch in pairs(M.watches) do
    watch.active = false
    stopped[#stopped + 1] = {
      watch_id = watch_id,
      address = watch.address,
      hit_count = #watch.hits,
    }
    M.watches[watch_id] = nil
  end
  M.needs_rebuild = true
  rebuild_active_breakpoints()
  table.sort(stopped, function(left, right) return left.watch_id < right.watch_id end)
  return {stopped = stopped, count = #stopped}
end

_G.__ce_mcp_modules["debug"] = "2026.03.08.4"
return {ok = true, module = "debug", version = "2026.03.08.4"}
''',
)
