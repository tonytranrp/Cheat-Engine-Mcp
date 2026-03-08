from __future__ import annotations

from ..context import RuntimeModule

STRUCTURE_RUNTIME = RuntimeModule(
    name="structure",
    version="2026.03.08.2",
    script=r'''
_G.__ce_mcp = _G.__ce_mcp or {}
_G.__ce_mcp_modules = _G.__ce_mcp_modules or {}
local root = _G.__ce_mcp
root.structure = root.structure or {}
local M = root.structure

local unpack_fn = table.unpack or unpack

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

local function trim_ascii(value)
  local text = tostring(value or '')
  text = text:gsub('^%s+', '')
  text = text:gsub('%s+$', '')
  return text
end

local function normalize_key(value)
  return trim_ascii(value):lower():gsub('[%s_%-%(%)]', '')
end

local function bytes_to_hex(bytes)
  local parts = {}
  for _, value in ipairs(bytes or {}) do
    parts[#parts + 1] = string.format('%02X', tonumber(value) or 0)
  end
  return table.concat(parts, ' ')
end

local function safe_call(fn, ...)
  local args = {...}
  local ok, result = pcall(function()
    return fn(unpack_fn(args))
  end)
  if not ok then
    return nil
  end
  return result
end

local function safe_read_bytes(address, count)
  return safe_call(readBytes, address, count, true)
end

local function safe_read_string(address, max_length, wide)
  return safe_call(readString, address, max_length, wide and true or false)
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
  pointer = vtPointer,
}

local VALUE_TYPE_NAMES = {
  [vtByte] = 'byte',
  [vtWord] = 'word',
  [vtDword] = 'dword',
  [vtQword] = 'qword',
  [vtSingle] = 'float',
  [vtDouble] = 'double',
  [vtString] = 'string',
  [vtByteArray] = 'bytearray',
  [vtBinary] = 'binary',
  [vtPointer] = 'pointer',
}

local function normalize_vartype(value)
  if value == nil then
    return nil
  end
  if type(value) == 'number' then
    return value
  end
  local key = normalize_key(value)
  if VALUE_TYPES[key] == nil then
    error('invalid_structure_vartype:' .. key)
  end
  return VALUE_TYPES[key]
end

local function resolve_structure(name, index)
  if index ~= nil then
    local numeric_index = tonumber(index)
    if numeric_index == nil then
      error('invalid_structure_index')
    end
    return getStructure(numeric_index)
  end

  if name == nil or tostring(name) == '' then
    error('missing_structure_selector')
  end

  local target = tostring(name)
  local count = getStructureCount()
  for current_index = 0, count - 1 do
    local structure = getStructure(current_index)
    if structure ~= nil and tostring(structure.Name or '') == target then
      return structure, current_index
    end
  end

  return nil
end

local function find_structure_index(target)
  local count = getStructureCount()
  for current_index = 0, count - 1 do
    local structure = getStructure(current_index)
    if structure == target then
      return current_index
    end
  end
  return nil
end

local function serialize_element(element)
  if element == nil then
    return nil
  end

  local child = nil
  local child_struct = nil
  pcall(function() child_struct = element.ChildStruct end)
  if child_struct ~= nil then
    child = {
      name = tostring(child_struct.Name or ''),
      index = find_structure_index(child_struct),
    }
  end

  local owner = nil
  pcall(function() owner = element.Owner end)
  local owner_name = nil
  if owner ~= nil then
    owner_name = tostring(owner.Name or '')
  end

  return {
    owner_name = owner_name,
    offset = tonumber(element.Offset) or 0,
    name = tostring(element.Name or ''),
    vartype = tonumber(element.Vartype) or 0,
    bytesize = tonumber(element.Bytesize) or 0,
    child_struct = child,
    child_struct_start = tonumber(element.ChildStructStart) or 0,
  }
end

local function serialize_structure(structure, include_elements)
  if structure == nil then
    return nil
  end

  local structure_index = find_structure_index(structure)
  local result = {
    index = structure_index,
    name = tostring(structure.Name or ''),
    size = tonumber(structure.Size) or 0,
    count = tonumber(structure.Count) or 0,
    global = structure_index ~= nil,
  }

  if include_elements then
    result.elements = {}
    local count = tonumber(structure.Count) or 0
    for element_index = 0, count - 1 do
      result.elements[#result.elements + 1] = serialize_element(structure.Element[element_index])
    end
  end

  return result
end

local function resolve_child_structure(options)
  if options == nil then
    return nil
  end

  if options.child_structure_index ~= nil or options.child_structure_name ~= nil then
    return resolve_structure(options.child_structure_name, options.child_structure_index)
  end

  return nil
end

local function default_bytesize_for_vartype(vartype, explicit_bytesize)
  local size = tonumber(explicit_bytesize) or 0
  if size > 0 then
    return size
  end
  if vartype == vtByte then return 1 end
  if vartype == vtWord then return 2 end
  if vartype == vtDword or vartype == vtSingle then return 4 end
  if vartype == vtQword or vartype == vtDouble then return 8 end
  if vartype == vtPointer then
    return targetIs64Bit() and 8 or 4
  end
  if vartype == vtString then return 64 end
  if vartype == vtByteArray or vartype == vtBinary then return 16 end
  return 8
end

local function read_scalar_value(vartype, address, bytesize)
  if vartype == vtByte then
    local bytes = safe_read_bytes(address, 1)
    return bytes and bytes[1] or nil, 'integer'
  end
  if vartype == vtWord then
    return safe_call(readSmallInteger, address), 'integer'
  end
  if vartype == vtDword then
    return safe_call(readInteger, address), 'integer'
  end
  if vartype == vtQword then
    return safe_call(readQword, address), 'integer'
  end
  if vartype == vtSingle then
    return safe_call(readFloat, address), 'float'
  end
  if vartype == vtDouble then
    return safe_call(readDouble, address), 'double'
  end
  if vartype == vtPointer then
    return safe_call(readPointer, address), 'pointer'
  end
  if vartype == vtString then
    local max_length = default_bytesize_for_vartype(vartype, bytesize)
    local ascii = safe_read_string(address, max_length, false)
    local wide = safe_read_string(address, max_length, true)
    if ascii ~= nil and wide ~= nil and ascii ~= wide and wide ~= '' then
      return {ascii = ascii, wide = wide}, 'string'
    end
    return ascii or wide, 'string'
  end
  if vartype == vtByteArray or vartype == vtBinary then
    local bytes = safe_read_bytes(address, default_bytesize_for_vartype(vartype, bytesize)) or {}
    return bytes_to_hex(bytes), 'bytes_hex'
  end

  local bytes = safe_read_bytes(address, default_bytesize_for_vartype(vartype, bytesize)) or {}
  return bytes_to_hex(bytes), 'bytes_hex'
end

local function read_structure_instance(structure, base_address, max_depth, include_raw, visited)
  visited = visited or {}
  local structure_index = find_structure_index(structure)
  local visit_key = tostring(structure_index ~= nil and structure_index or tostring(structure.Name or '')) .. '@' .. tostring(base_address)

  if visited[visit_key] then
    return {
      address = base_address,
      address_hex = string.format('0x%X', base_address),
      structure = serialize_structure(structure, false),
      cycle_detected = true,
      fields = {},
    }
  end

  visited[visit_key] = true
  local fields = {}
  local element_count = tonumber(structure.Count) or 0

  for element_index = 0, element_count - 1 do
    local element = structure.Element[element_index]
    local field = serialize_element(element)
    local field_address = base_address + (field.offset or 0)
    field.address = field_address
    field.address_hex = string.format('0x%X', field_address)
    field.vartype_name = VALUE_TYPE_NAMES[field.vartype] or 'unknown'
    field.bytesize = default_bytesize_for_vartype(field.vartype, field.bytesize)

    local child_struct = nil
    pcall(function() child_struct = element.ChildStruct end)
    local child_struct_start = tonumber(field.child_struct_start) or 0

    if child_struct ~= nil and tonumber(max_depth) and tonumber(max_depth) > 0 then
      if field.vartype == vtPointer then
        local pointer_value = safe_call(readPointer, field_address)
        field.value = pointer_value
        field.value_kind = 'pointer'
        if pointer_value ~= nil then
          field.value_hex = string.format('0x%X', pointer_value)
          field.child_address = pointer_value + child_struct_start
          field.child_address_hex = string.format('0x%X', field.child_address)
          field.child = read_structure_instance(child_struct, field.child_address, tonumber(max_depth) - 1, include_raw, visited)
        end
      else
        field.child_address = field_address + child_struct_start
        field.child_address_hex = string.format('0x%X', field.child_address)
        field.child = read_structure_instance(child_struct, field.child_address, tonumber(max_depth) - 1, include_raw, visited)
      end
    else
      local value, value_kind = read_scalar_value(field.vartype, field_address, field.bytesize)
      field.value = value
      field.value_kind = value_kind
      if type(value) == 'number' and (field.vartype == vtPointer or field.vartype == vtQword) then
        field.value_hex = string.format('0x%X', value)
      end
    end

    if include_raw then
      local raw_bytes = safe_read_bytes(field_address, math.min(field.bytesize, 64)) or {}
      field.raw_bytes = raw_bytes
      field.raw_bytes_hex = bytes_to_hex(raw_bytes)
      field.raw_truncated = field.bytesize > #raw_bytes
    end

    fields[#fields + 1] = field
  end

  visited[visit_key] = nil
  return {
    address = base_address,
    address_hex = string.format('0x%X', base_address),
    structure = serialize_structure(structure, false),
    fields = fields,
  }
end

function M.list_structures(include_elements)
  return run_on_main_thread(function()
    local count = getStructureCount()
    local structures = {}
    for structure_index = 0, count - 1 do
      structures[#structures + 1] = serialize_structure(getStructure(structure_index), include_elements and true or false)
    end
    return {count = count, structures = structures}
  end)
end

function M.get_structure(name, index, include_elements)
  return run_on_main_thread(function()
    local structure = resolve_structure(name, index)
    return {structure = serialize_structure(structure, include_elements and true or false)}
  end)
end

function M.create_structure(name, add_global)
  return run_on_main_thread(function()
    local structure = createStructure(tostring(name or ''))
    if add_global ~= false then
      structure.addToGlobalStructureList()
    end
    return {structure = serialize_structure(structure, true)}
  end)
end

function M.delete_structure(name, index, destroy)
  return run_on_main_thread(function()
    local structure = resolve_structure(name, index)
    if structure == nil then
      return {deleted = false}
    end

    pcall(function() structure.removeFromGlobalStructureList() end)
    if destroy ~= false then
      pcall(function() structure.destroy() end)
    end

    return {
      deleted = true,
      name = tostring(structure.Name or ''),
      index = find_structure_index(structure),
    }
  end)
end

function M.add_element(name, index, options)
  return run_on_main_thread(function()
    local structure = resolve_structure(name, index)
    if structure == nil then
      error('structure_not_found')
    end

    options = options or {}
    structure.beginUpdate()
    local ok, result = pcall(function()
      local element = structure.addElement()
      if options.offset ~= nil then element.Offset = tonumber(options.offset) or 0 end
      if options.name ~= nil then element.Name = tostring(options.name) end
      if options.vartype ~= nil then element.Vartype = normalize_vartype(options.vartype) end
      if options.bytesize ~= nil then element.Bytesize = tonumber(options.bytesize) or 0 end

      local child_structure = resolve_child_structure(options)
      if child_structure ~= nil then
        element.ChildStruct = child_structure
      end

      if options.child_struct_start ~= nil then
        element.ChildStructStart = tonumber(options.child_struct_start) or 0
      end

      return element
    end)
    structure.endUpdate()

    if not ok then
      error(result)
    end

    return {
      structure = serialize_structure(structure, true),
      element = serialize_element(result),
    }
  end)
end

function M.define_structure(name, elements, add_global)
  return run_on_main_thread(function()
    local structure = createStructure(tostring(name or ''))
    structure.beginUpdate()
    local ok, err = pcall(function()
      for _, options in ipairs(elements or {}) do
        local element = structure.addElement()
        if options.offset ~= nil then element.Offset = tonumber(options.offset) or 0 end
        if options.name ~= nil then element.Name = tostring(options.name) end
        if options.vartype ~= nil then element.Vartype = normalize_vartype(options.vartype) end
        if options.bytesize ~= nil then element.Bytesize = tonumber(options.bytesize) or 0 end

        local child_structure = resolve_child_structure(options)
        if child_structure ~= nil then
          element.ChildStruct = child_structure
        end

        if options.child_struct_start ~= nil then
          element.ChildStructStart = tonumber(options.child_struct_start) or 0
        end
      end
    end)
    structure.endUpdate()
    if not ok then
      pcall(function() structure.destroy() end)
      error(err)
    end

    if add_global ~= false then
      structure.addToGlobalStructureList()
    end

    return {structure = serialize_structure(structure, true)}
  end)
end

function M.auto_guess(name, index, base_address, offset, size)
  return run_on_main_thread(function()
    local structure = resolve_structure(name, index)
    if structure == nil then
      error('structure_not_found')
    end

    local resolved_base = getAddressSafe(base_address)
    if resolved_base == nil then
      error('structure_base_not_found')
    end

    structure.autoGuess(resolved_base, tonumber(offset) or 0, tonumber(size) or 4096)
    return {structure = serialize_structure(structure, true), base_address = resolved_base}
  end)
end

function M.fill_from_dotnet(name, index, address, change_name)
  return run_on_main_thread(function()
    local structure = resolve_structure(name, index)
    if structure == nil then
      error('structure_not_found')
    end

    local resolved_address = getAddressSafe(address)
    if resolved_address == nil then
      error('structure_dotnet_address_not_found')
    end

    structure.fillFromDotNetAddress(resolved_address, change_name ~= false)
    return {structure = serialize_structure(structure, true), address = resolved_address}
  end)
end

function M.read_structure(name, index, address, max_depth, include_raw)
  return run_on_main_thread(function()
    local structure = resolve_structure(name, index)
    if structure == nil then
      error('structure_not_found')
    end

    local resolved_address = getAddressSafe(address)
    if resolved_address == nil then
      error('structure_instance_address_not_found')
    end

    return read_structure_instance(
      structure,
      resolved_address,
      math.max(0, tonumber(max_depth) or 1),
      include_raw ~= false,
      {}
    )
  end)
end

_G.__ce_mcp_modules["structure"] = "2026.03.08.2"
return {ok = true, module = "structure", version = "2026.03.08.2"}
''',
)
