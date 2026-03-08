from __future__ import annotations

from ..context import RuntimeModule

TABLE_RUNTIME = RuntimeModule(
    name="table",
    version="2026.03.08.2",
    script=r'''
_G.__ce_mcp = _G.__ce_mcp or {}
_G.__ce_mcp_modules = _G.__ce_mcp_modules or {}
local root = _G.__ce_mcp
root.table = root.table or {}
local M = root.table

local function run_on_main_thread(fn)
  local ok, result = false, nil
  synchronize(function()
    ok, result = pcall(fn)
  end)
  if not ok then
    error(result)
  end
  return result
end

local function raise_error(message)
  error(message, 0)
end

local function normalize_type_key(value)
  local key = string.lower(tostring(value))
  key = string.gsub(key, "^%s+", "")
  key = string.gsub(key, "%s+$", "")
  key = string.gsub(key, "[%s_%-%(%)]", "")
  return key
end

local VALUE_TYPES = {
  byte = vtByte,
  ["1byte"] = vtByte,
  ["1bytes"] = vtByte,
  word = vtWord,
  ["2byte"] = vtWord,
  ["2bytes"] = vtWord,
  dword = vtDword,
  ["4byte"] = vtDword,
  ["4bytes"] = vtDword,
  qword = vtQword,
  ["8byte"] = vtQword,
  ["8bytes"] = vtQword,
  float = vtSingle,
  single = vtSingle,
  double = vtDouble,
  string = vtString,
  bytearray = vtByteArray,
  arrayofbyte = vtByteArray,
  bytes = vtByteArray,
  aob = vtByteArray,
  binary = vtBinary,
  autoassembler = vtAutoAssembler,
  autoassembly = vtAutoAssembler,
  aa = vtAutoAssembler,
  script = vtAutoAssembler,
  pointer = vtPointer,
}

local function normalize_type(value)
  if value == nil then
    return nil
  end
  if type(value) == 'number' then
    return value
  end
  local key = normalize_type_key(value)
  if VALUE_TYPES[key] == nil then
    raise_error('invalid_record_type:' .. key)
  end
  return VALUE_TYPES[key]
end

local function serialize_record(record, include_script)
  if record == nil then
    return nil
  end

  local offsets = {}
  local offset_count = tonumber(record.OffsetCount) or 0
  for index = 0, offset_count - 1 do
    offsets[#offsets + 1] = tonumber(record.Offset[index]) or 0
  end

  local value = nil
  pcall(function() value = record.Value end)
  local script = nil
  if include_script then
    pcall(function() script = record.Script end)
  end
  local is_group_header = false
  pcall(function() is_group_header = record.IsGroupHeader and true or false end)

  return {
    id = tonumber(record.ID) or 0,
    index = tonumber(record.Index) or 0,
    description = tostring(record.Description or ''),
    address = tostring(record.Address or ''),
    current_address = tonumber(record.CurrentAddress) or 0,
    value = value,
    active = record.Active and true or false,
    type = tonumber(record.Type) or 0,
    offset_count = offset_count,
    offsets = offsets,
    is_group_header = is_group_header,
    script = script,
  }
end

local function get_record_by_id(record_id)
  local al = getAddressList()
  return al.getMemoryRecordByID(tonumber(record_id))
end

local function get_record_by_description(description)
  local al = getAddressList()
  return al.getMemoryRecordByDescription(description)
end

local function require_record_by_id(record_id)
  local record = get_record_by_id(record_id)
  if record == nil then
    raise_error('record_not_found:' .. tostring(record_id))
  end
  return record
end

local function apply_record_offsets(record, offsets)
  offsets = offsets or {}
  record.OffsetCount = #offsets
  for index, value in ipairs(offsets) do
    record.Offset[index - 1] = tonumber(value) or 0
  end
end

local function apply_record_options(record, options)
  options = options or {}
  if options.description ~= nil then record.Description = tostring(options.description) end
  if options.address ~= nil then record.Address = tostring(options.address) end
  if options.type ~= nil then record.Type = normalize_type(options.type) end
  if options.value ~= nil then record.Value = tostring(options.value) end
  if options.active ~= nil then record.Active = options.active and true or false end
  if options.offsets ~= nil then
    apply_record_offsets(record, options.offsets)
  end
  if options.script ~= nil then record.Script = tostring(options.script) end
end

local function append_record_to_parent(record, parent)
  if parent == nil then
    return
  end

  local ok = pcall(function() record:appendToEntry(parent) end)
  if not ok then
    ok = pcall(function() record:AppendToEntry(parent) end)
  end
  if not ok then
    raise_error('record_grouping_unsupported')
  end
end

local function create_record_internal(options, parent)
  local al = getAddressList()
  local record = al.createMemoryRecord()
  apply_record_options(record, options)
  append_record_to_parent(record, parent)
  return record
end

function M.list_records(include_script)
  return run_on_main_thread(function()
    local al = getAddressList()
    local records = {}
    local count = tonumber(al.Count) or 0
    for index = 0, count - 1 do
      records[#records + 1] = serialize_record(al.getMemoryRecord(index), include_script and true or false)
    end
    return {count = count, records = records}
  end)
end

function M.get_record_by_id(record_id, include_script)
  return run_on_main_thread(function()
    local record = get_record_by_id(record_id)
    return {record = serialize_record(record, include_script and true or false)}
  end)
end

function M.get_record_by_description(description, include_script)
  return run_on_main_thread(function()
    local record = get_record_by_description(description)
    return {record = serialize_record(record, include_script and true or false)}
  end)
end

function M.find_records_by_description(description)
  return run_on_main_thread(function()
    local al = getAddressList()
    local records = {}
    local count = tonumber(al.Count) or 0
    for index = 0, count - 1 do
      local record = al.getMemoryRecord(index)
      if record ~= nil and tostring(record.Description or '') == tostring(description) then
        records[#records + 1] = serialize_record(record, false)
      end
    end
    return {count = #records, records = records}
  end)
end

function M.get_selected_record(include_script)
  return run_on_main_thread(function()
    local al = getAddressList()
    return {record = serialize_record(al.SelectedRecord, include_script and true or false)}
  end)
end

function M.set_selected_record(record_id)
  return run_on_main_thread(function()
    local al = getAddressList()
    local record = require_record_by_id(record_id)
    al.SelectedRecord = record
    return {record = serialize_record(al.SelectedRecord, false)}
  end)
end

function M.create_record(options)
  return run_on_main_thread(function()
    local record = create_record_internal(options or {}, nil)
    return {record = serialize_record(record, true)}
  end)
end

function M.create_records(records)
  return run_on_main_thread(function()
    records = records or {}
    local created = {}
    for _, options in ipairs(records) do
      created[#created + 1] = serialize_record(create_record_internal(options or {}, nil), true)
    end
    return {count = #created, records = created}
  end)
end

function M.create_record_group(description, records, options)
  return run_on_main_thread(function()
    local group_options = options or {}
    group_options.description = tostring(description)
    local group = create_record_internal(group_options, nil)

    local ok = pcall(function() group.IsGroupHeader = true end)
    if not ok then
      raise_error('record_grouping_unsupported')
    end

    local created = {}
    for _, record_options in ipairs(records or {}) do
      local child = create_record_internal(record_options or {}, group)
      created[#created + 1] = serialize_record(child, true)
    end

    return {
      group = serialize_record(group, false),
      count = #created,
      records = created,
    }
  end)
end

function M.delete_record(record_id)
  return run_on_main_thread(function()
    local record = get_record_by_id(record_id)
    if record == nil then
      return {deleted = false}
    end
    record.destroy()
    return {deleted = true, record_id = tonumber(record_id) or 0}
  end)
end

function M.set_description(record_id, description)
  return run_on_main_thread(function()
    local record = require_record_by_id(record_id)
    record.Description = tostring(description)
    return {record = serialize_record(record, false)}
  end)
end

function M.set_address(record_id, address)
  return run_on_main_thread(function()
    local record = require_record_by_id(record_id)
    record.Address = tostring(address)
    return {record = serialize_record(record, false)}
  end)
end

function M.set_type(record_id, value_type)
  return run_on_main_thread(function()
    local record = require_record_by_id(record_id)
    record.Type = normalize_type(value_type)
    return {record = serialize_record(record, false)}
  end)
end

function M.set_value(record_id, value)
  return run_on_main_thread(function()
    local record = require_record_by_id(record_id)
    record.Value = tostring(value)
    return {record = serialize_record(record, false)}
  end)
end

function M.set_active(record_id, active)
  return run_on_main_thread(function()
    local record = require_record_by_id(record_id)
    record.Active = active and true or false
    return {record = serialize_record(record, false)}
  end)
end

function M.get_offsets(record_id)
  return run_on_main_thread(function()
    local record = require_record_by_id(record_id)
    return {record_id = tonumber(record_id) or 0, offsets = serialize_record(record, false).offsets}
  end)
end

function M.set_offsets(record_id, offsets)
  return run_on_main_thread(function()
    local record = require_record_by_id(record_id)
    apply_record_offsets(record, offsets)
    return {record = serialize_record(record, false)}
  end)
end

function M.get_script(record_id)
  return run_on_main_thread(function()
    local record = require_record_by_id(record_id)
    return {record_id = tonumber(record_id) or 0, script = record.Script}
  end)
end

function M.set_script(record_id, script)
  return run_on_main_thread(function()
    local record = require_record_by_id(record_id)
    record.Script = tostring(script)
    return {record = serialize_record(record, true)}
  end)
end

function M.table_record_count()
  return run_on_main_thread(function()
    local al = getAddressList()
    return {count = tonumber(al.Count) or 0}
  end)
end

function M.table_refresh()
  return run_on_main_thread(function()
    local al = getAddressList()
    al.refresh()
    return {refreshed = true}
  end)
end

function M.table_rebuild_description_cache()
  return run_on_main_thread(function()
    local al = getAddressList()
    al.rebuildDescriptionCache()
    return {rebuilt = true}
  end)
end

function M.table_disable_all_without_execute()
  return run_on_main_thread(function()
    local al = getAddressList()
    al.disableAllWithoutExecute()
    return {disabled = true}
  end)
end

function M.table_load(path)
  return run_on_main_thread(function()
    loadTable(path)
    return {loaded = true, path = path}
  end)
end

function M.table_save(path)
  return run_on_main_thread(function()
    saveTable(path)
    return {saved = true, path = path}
  end)
end

function M.table_create_file(name)
  return run_on_main_thread(function()
    local table_file = createTableFile(name)
    return {name = table_file.Name}
  end)
end

function M.table_find_file(name)
  return run_on_main_thread(function()
    local table_file = findTableFile(name)
    if table_file == nil then
      return {found = false, name = name}
    end
    return {found = true, name = table_file.Name}
  end)
end

function M.table_export_file(name, path)
  return run_on_main_thread(function()
    local table_file = findTableFile(name)
    if table_file == nil then
      return {found = false, name = name, path = path}
    end
    table_file.saveToFile(path)
    return {found = true, name = table_file.Name, path = path}
  end)
end

_G.__ce_mcp_modules["table"] = "2026.03.08.2"
return {ok = true, module = "table", version = "2026.03.08.2"}
''',
)
