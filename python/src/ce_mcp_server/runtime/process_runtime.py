from __future__ import annotations

from ..context import RuntimeModule

PROCESS_RUNTIME = RuntimeModule(
    name="process",
    version="2026.03.07.1",
    script=r'''
_G.__ce_mcp = _G.__ce_mcp or {}
_G.__ce_mcp_modules = _G.__ce_mcp_modules or {}
local root = _G.__ce_mcp
root.process = root.process or {}
local M = root.process

local function string_list_to_table(list)
  local result = {}
  if list == nil then
    return result
  end
  local count = tonumber(list.Count) or 0
  for index = 0, count - 1 do
    result[#result + 1] = tostring(list[index])
  end
  return result
end

function M.get_ce_version()
  return {version = getCEVersion()}
end

function M.get_cheat_engine_dir()
  return {path = getCheatEngineDir()}
end

function M.get_process_id_from_name(process_name)
  return {process_name = process_name, process_id = getProcessIDFromProcessName(process_name) or 0}
end

function M.get_foreground_process()
  return {process_id = getForegroundProcess() or 0}
end

function M.get_cpu_count()
  return {count = getCPUCount() or 0}
end

function M.target_is_64bit()
  return {is64 = targetIs64Bit() and true or false}
end

function M.get_window_list()
  return {windows = getWindowlist() or {}}
end

function M.get_common_module_list()
  return {modules = string_list_to_table(getCommonModuleList())}
end

function M.get_auto_attach_list()
  return {entries = string_list_to_table(getAutoAttachList())}
end

function M.set_auto_attach_list(entries)
  local list = getAutoAttachList()
  list.Text = table.concat(entries or {}, '\n')
  return {entries = string_list_to_table(list)}
end

function M.clear_auto_attach_list()
  local list = getAutoAttachList()
  list.Text = ''
  return {entries = {}}
end

function M.add_auto_attach_target(entry)
  local list = getAutoAttachList()
  local entries = string_list_to_table(list)
  for _, current in ipairs(entries) do
    if current == entry then
      return {entries = entries}
    end
  end
  entries[#entries + 1] = entry
  list.Text = table.concat(entries, '\n')
  return {entries = string_list_to_table(list)}
end

function M.remove_auto_attach_target(entry)
  local list = getAutoAttachList()
  local entries = string_list_to_table(list)
  local filtered = {}
  for _, current in ipairs(entries) do
    if current ~= entry then
      filtered[#filtered + 1] = current
    end
  end
  list.Text = table.concat(filtered, '\n')
  return {entries = string_list_to_table(list)}
end

_G.__ce_mcp_modules["process"] = "2026.03.07.1"
return {ok = true, module = "process", version = "2026.03.07.1"}
''',
)
