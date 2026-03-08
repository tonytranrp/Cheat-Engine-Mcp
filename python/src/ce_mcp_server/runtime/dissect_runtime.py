from __future__ import annotations

from ..context import RuntimeModule

DISSECT_RUNTIME = RuntimeModule(
    name="dissect",
    version="2026.03.08.1",
    script=r'''
_G.__ce_mcp = _G.__ce_mcp or {}
_G.__ce_mcp_modules = _G.__ce_mcp_modules or {}
local root = _G.__ce_mcp
root.dissect = root.dissect or {}
local M = root.dissect

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

local function get_dissect_code()
  local dissect_code = getDissectCode()
  if dissect_code == nil then
    error('dissect_code_unavailable')
  end
  return dissect_code
end

local function slice_table(values, limit)
  if values == nil then
    return {}
  end

  local result = {}
  local capped = math.min(#values, limit or #values)
  for index = 1, capped do
    result[#result + 1] = values[index]
  end
  return result
end

function M.clear()
  return run_on_main_thread(function()
    local dissect_code = get_dissect_code()
    dissect_code.clear()
    return {cleared = true}
  end)
end

function M.dissect_module(module_name, clear_first)
  return run_on_main_thread(function()
    local dissect_code = get_dissect_code()
    if clear_first ~= false then
      dissect_code.clear()
    end
    dissect_code.dissect(tostring(module_name))
    return {module_name = tostring(module_name), dissected = true}
  end)
end

function M.dissect_region(base_address, size, clear_first)
  return run_on_main_thread(function()
    local resolved_base = getAddressSafe(base_address)
    if resolved_base == nil then
      error('dissect_region_base_not_found')
    end

    local dissect_code = get_dissect_code()
    if clear_first ~= false then
      dissect_code.clear()
    end
    dissect_code.dissect(resolved_base, tonumber(size) or 0)
    return {base_address = resolved_base, size = tonumber(size) or 0, dissected = true}
  end)
end

function M.get_references(address, limit)
  return run_on_main_thread(function()
    local resolved_address = getAddressSafe(address)
    if resolved_address == nil then
      error('dissect_reference_address_not_found')
    end

    local dissect_code = get_dissect_code()
    local references = dissect_code.getReferences(resolved_address) or {}
    local sliced = slice_table(references, tonumber(limit) or #references)
    return {
      address = resolved_address,
      count = #references,
      returned_count = #sliced,
      truncated = #references > #sliced,
      references = sliced,
    }
  end)
end

function M.get_referenced_strings(limit)
  return run_on_main_thread(function()
    local dissect_code = get_dissect_code()
    local strings = dissect_code.getReferencedStrings() or {}
    local sliced = slice_table(strings, tonumber(limit) or #strings)
    return {
      count = #strings,
      returned_count = #sliced,
      truncated = #strings > #sliced,
      strings = sliced,
    }
  end)
end

function M.get_referenced_functions(limit)
  return run_on_main_thread(function()
    local dissect_code = get_dissect_code()
    local functions = dissect_code.getReferencedFunctions() or {}
    local sliced = slice_table(functions, tonumber(limit) or #functions)
    return {
      count = #functions,
      returned_count = #sliced,
      truncated = #functions > #sliced,
      functions = sliced,
    }
  end)
end

function M.save(path)
  return run_on_main_thread(function()
    local dissect_code = get_dissect_code()
    dissect_code.saveToFile(tostring(path))
    return {saved = true, path = tostring(path)}
  end)
end

function M.load(path)
  return run_on_main_thread(function()
    local dissect_code = get_dissect_code()
    dissect_code.loadFromFile(tostring(path))
    return {loaded = true, path = tostring(path)}
  end)
end

_G.__ce_mcp_modules["dissect"] = "2026.03.08.1"
return {ok = true, module = "dissect", version = "2026.03.08.1"}
''',
)
