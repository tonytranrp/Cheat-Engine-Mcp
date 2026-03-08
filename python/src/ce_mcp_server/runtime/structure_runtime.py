from __future__ import annotations

from ..context import RuntimeModule

STRUCTURE_RUNTIME = RuntimeModule(
    name="structure",
    version="2026.03.08.1",
    script=r'''
_G.__ce_mcp = _G.__ce_mcp or {}
_G.__ce_mcp_modules = _G.__ce_mcp_modules or {}
local root = _G.__ce_mcp
root.structure = root.structure or {}
local M = root.structure

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

local VALUE_TYPES = {
  byte = vtByte,
  word = vtWord,
  dword = vtDword,
  qword = vtQword,
  float = vtSingle,
  double = vtDouble,
  string = vtString,
  bytearray = vtByteArray,
  binary = vtBinary,
  pointer = vtPointer,
}

local function normalize_vartype(value)
  if value == nil then
    return nil
  end
  if type(value) == 'number' then
    return value
  end
  local key = string.lower(tostring(value))
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

_G.__ce_mcp_modules["structure"] = "2026.03.08.1"
return {ok = true, module = "structure", version = "2026.03.08.1"}
''',
)
