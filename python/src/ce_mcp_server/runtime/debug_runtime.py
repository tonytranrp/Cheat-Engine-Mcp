from __future__ import annotations

from ..context import RuntimeModule

DEBUG_RUNTIME = RuntimeModule(
    name="debug",
    version="2026.03.07.1",
    script=r'''
_G.__ce_mcp = _G.__ce_mcp or {}
_G.__ce_mcp_modules = _G.__ce_mcp_modules or {}
local root = _G.__ce_mcp
root.debug = root.debug or { watches = {}, next_id = 1 }
local M = root.debug

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
    breakpoint_count = #serialize_breakpoint_list(),
    breakpoints = serialize_breakpoint_list(),
    watches = watches,
  }
end

function M.start(interface)
  if not debug_isDebugging() then
    debugProcess(tonumber(interface) or 0)
  end
  return M.status()
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
  local breakpoints = serialize_breakpoint_list()
  return {
    count = #breakpoints,
    breakpoints = breakpoints,
  }
end

function M.watch_start(address, size, trigger, method, max_hits, auto_continue, debugger_interface)
  if not debug_isDebugging() then
    debugProcess(tonumber(debugger_interface) or 0)
  end
  if not debug_isDebugging() then
    error('debugger_start_failed')
  end

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
  }
  M.next_id = M.next_id + 1

  local function on_breakpoint()
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
      pcall(function() debug_removeBreakpoint(watch.address) end)
    end

    if watch.auto_continue and debug_isBroken() then
      debug_continueFromBreakpoint(co_run)
      return 1
    end
    return 0
  end

  watch.callback = on_breakpoint
  M.watches[watch.id] = watch

  local ok
  if normalized_method == nil then
    ok = debug_setBreakpoint(resolved_address, watch.size, normalized_trigger, on_breakpoint)
  else
    ok = debug_setBreakpoint(resolved_address, watch.size, normalized_trigger, normalized_method, on_breakpoint)
  end
  if not ok then
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
  return serialize_watch(watch, true, tonumber(limit) or #watch.hits)
end

function M.watch_stop(watch_id)
  local watch = M.watches[tostring(watch_id)]
  if watch == nil then
    return {stopped = false, watch_id = tostring(watch_id)}
  end
  watch.active = false
  pcall(function() debug_removeBreakpoint(watch.address) end)
  M.watches[tostring(watch_id)] = nil
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
    pcall(function() debug_removeBreakpoint(watch.address) end)
    stopped[#stopped + 1] = {
      watch_id = watch_id,
      address = watch.address,
      hit_count = #watch.hits,
    }
    M.watches[watch_id] = nil
  end
  table.sort(stopped, function(left, right) return left.watch_id < right.watch_id end)
  return {stopped = stopped, count = #stopped}
end

_G.__ce_mcp_modules["debug"] = "2026.03.07.1"
return {ok = true, module = "debug", version = "2026.03.07.1"}
''',
)
