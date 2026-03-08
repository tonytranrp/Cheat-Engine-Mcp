from __future__ import annotations

from ..context import RuntimeModule

SCAN_RUNTIME = RuntimeModule(
    name="scan",
    version="2026.03.07.1",
    script=r'''
_G.__ce_mcp = _G.__ce_mcp or {}
_G.__ce_mcp_modules = _G.__ce_mcp_modules or {}
local root = _G.__ce_mcp
root.scan = root.scan or { sessions = {}, next_id = 1 }
local M = root.scan

M.var_types = {
  byte = vtByte,
  word = vtWord,
  dword = vtDword,
  qword = vtQword,
  float = vtSingle,
  double = vtDouble,
  string = vtString,
  bytearray = vtByteArray,
  binary = vtBinary,
  all = vtAll,
  autoassembler = vtAutoAssembler,
  pointer = vtPointer,
}

M.scan_options = {
  exact = soExactValue,
  between = soValueBetween,
  bigger = soBiggerThan,
  smaller = soSmallerThan,
  increased = soIncreasedValue,
  decreased = soDecreasedValue,
  changed = soChanged,
  unchanged = soUnchanged,
  unknown = soUnknownValue,
}

M.rounding_types = {
  rounded = rtRounded,
  extremerounded = rtExtremerounded,
  truncated = rtTruncated,
}

M.alignment_types = {
  not_aligned = fsmNotAligned,
  aligned = fsmAligned,
  last_digits = fsmLastDigits,
}

local function normalize(mapping, value, fallback)
  if value == nil then
    return fallback
  end
  if type(value) == 'number' then
    return value
  end
  local key = string.lower(tostring(value))
  if mapping[key] == nil then
    error('invalid_enum:' .. key)
  end
  return mapping[key]
end

local function ensure_session(session_id)
  local session = M.sessions[session_id]
  if session == nil then
    error('scan_session_not_found:' .. tostring(session_id))
  end
  return session
end

local function ensure_foundlist(session)
  if session.foundlist == nil then
    session.foundlist = createFoundList(session.memscan)
    session.foundlist.initialize()
  end
  return session.foundlist
end

local function destroy_foundlist(session)
  if session.foundlist ~= nil then
    session.foundlist.deinitialize()
    session.foundlist.destroy()
    session.foundlist = nil
  end
end

local function serialize_found_results(foundlist, limit)
  local results = {}
  local count = tonumber(foundlist.Count) or 0
  local capped = math.min(count, limit or count)
  for index = 0, capped - 1 do
    results[#results + 1] = {
      index = index,
      address = tostring(foundlist.Address[index]),
      value = tostring(foundlist.Value[index]),
    }
  end
  return results, count
end

function M.list_enums()
  return {
    scan_options = M.scan_options,
    var_types = M.var_types,
    rounding_types = M.rounding_types,
    alignment_types = M.alignment_types,
  }
end

function M.create_session()
  local session_id = 'scan-' .. tostring(M.next_id)
  M.next_id = M.next_id + 1
  M.sessions[session_id] = {
    id = session_id,
    memscan = createMemScan(),
    foundlist = nil,
  }
  return {session_id = session_id}
end

function M.destroy_session(session_id)
  local session = ensure_session(session_id)
  destroy_foundlist(session)
  session.memscan.destroy()
  M.sessions[session_id] = nil
  return {session_id = session_id, destroyed = true}
end

function M.destroy_all_sessions()
  for session_id, session in pairs(M.sessions) do
    destroy_foundlist(session)
    session.memscan.destroy()
    M.sessions[session_id] = nil
  end
  return {destroyed = true}
end

function M.list_sessions()
  local sessions = {}
  for session_id, session in pairs(M.sessions) do
    sessions[#sessions + 1] = {
      session_id = session_id,
      has_foundlist = session.foundlist ~= nil,
      only_one_result = session.memscan.OnlyOneResult and true or false,
    }
  end
  table.sort(sessions, function(a, b) return a.session_id < b.session_id end)
  return {sessions = sessions}
end

function M.new_scan(session_id)
  local session = ensure_session(session_id)
  destroy_foundlist(session)
  session.memscan.newScan()
  return {session_id = session_id, reset = true}
end

function M.first_scan(session_id, options)
  local session = ensure_session(session_id)
  options = options or {}
  destroy_foundlist(session)
  session.memscan.firstScan(
    normalize(M.scan_options, options.scan_option, soExactValue),
    normalize(M.var_types, options.value_type, vtDword),
    normalize(M.rounding_types, options.rounding_type, rtRounded),
    tostring(options.input1 or ''),
    tostring(options.input2 or ''),
    tostring(options.start_address or 0),
    tostring(options.stop_address or 0x7fffffffffffffff),
    tostring(options.protection_flags or '*X*C*W'),
    normalize(M.alignment_types, options.alignment_type, fsmNotAligned),
    tostring(options.alignment_param or '1'),
    options.is_hexadecimal_input and true or false,
    options.is_not_binary_string and true or false,
    options.is_unicode_scan and true or false,
    options.is_case_sensitive and true or false
  )
  return {session_id = session_id, started = true}
end

function M.next_scan(session_id, options)
  local session = ensure_session(session_id)
  options = options or {}
  destroy_foundlist(session)
  session.memscan.nextScan(
    normalize(M.scan_options, options.scan_option, soExactValue),
    normalize(M.rounding_types, options.rounding_type, rtRounded),
    tostring(options.input1 or ''),
    tostring(options.input2 or ''),
    options.is_hexadecimal_input and true or false,
    options.is_not_binary_string and true or false,
    options.is_unicode_scan and true or false,
    options.is_case_sensitive and true or false,
    options.is_percentage_scan and true or false,
    tostring(options.saved_result_name or '')
  )
  return {session_id = session_id, started = true}
end

function M.wait(session_id)
  local session = ensure_session(session_id)
  session.memscan.waitTillDone()
  return {session_id = session_id, completed = true}
end

function M.get_progress(session_id)
  local session = ensure_session(session_id)
  local total, current = session.memscan.getProgress()
  return {session_id = session_id, total = total, current = current}
end

function M.attach_foundlist(session_id)
  local session = ensure_session(session_id)
  local foundlist = ensure_foundlist(session)
  return {session_id = session_id, attached = true, count = tonumber(foundlist.Count) or 0}
end

function M.detach_foundlist(session_id)
  local session = ensure_session(session_id)
  destroy_foundlist(session)
  return {session_id = session_id, attached = false}
end

function M.get_result_count(session_id)
  local session = ensure_session(session_id)
  local foundlist = ensure_foundlist(session)
  return {session_id = session_id, count = tonumber(foundlist.Count) or 0}
end

function M.get_results(session_id, limit)
  local session = ensure_session(session_id)
  local foundlist = ensure_foundlist(session)
  local results, count = serialize_found_results(foundlist, limit or 128)
  return {
    session_id = session_id,
    count = count,
    returned_count = #results,
    truncated = count > #results,
    results = results,
  }
end

function M.save_results(session_id, name)
  local session = ensure_session(session_id)
  session.memscan.saveCurrentResults(tostring(name))
  return {session_id = session_id, saved_result_name = tostring(name)}
end

function M.set_only_one_result(session_id, enabled)
  local session = ensure_session(session_id)
  session.memscan.setOnlyOneResult(enabled and true or false)
  return {session_id = session_id, only_one_result = session.memscan.OnlyOneResult and true or false}
end

function M.get_only_result(session_id)
  local session = ensure_session(session_id)
  return {session_id = session_id, address = session.memscan.getOnlyResult()}
end

_G.__ce_mcp_modules["scan"] = "2026.03.07.1"
return {ok = true, module = "scan", version = "2026.03.07.1"}
''',
)
