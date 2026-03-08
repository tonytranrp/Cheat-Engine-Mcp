from __future__ import annotations

from ..context import RuntimeModule

LUA_RUNTIME = RuntimeModule(
    name="lua",
    version="2026.03.08.2",
    script=r'''
_G.__ce_mcp = _G.__ce_mcp or {}
_G.__ce_mcp_modules = _G.__ce_mcp_modules or {}
local root = _G.__ce_mcp
root.lua = root.lua or {}
local M = root.lua

local unpack_fn = table.unpack or unpack

local function normalize_path(path)
  return tostring(path or ''):gsub('\\', '/')
end

local function split_paths(value)
  local entries = {}
  local text = tostring(value or '')
  if text == '' then
    return entries
  end

  for entry in string.gmatch(text, '([^;]+)') do
    entries[#entries + 1] = entry
  end
  return entries
end

local function has_entry(entries, target)
  for _, current in ipairs(entries) do
    if current == target then
      return true
    end
  end
  return false
end

local function add_entry(current_value, entry, prepend)
  local normalized = normalize_path(entry)
  local entries = split_paths(current_value)
  if has_entry(entries, normalized) then
    return {
      changed = false,
      entries = entries,
      value = table.concat(entries, ';'),
      entry = normalized,
    }
  end

  if prepend then
    table.insert(entries, 1, normalized)
  else
    entries[#entries + 1] = normalized
  end

  return {
    changed = true,
    entries = entries,
    value = table.concat(entries, ';'),
    entry = normalized,
  }
end

local function remove_entry(current_value, entry)
  local normalized = normalize_path(entry)
  local entries = split_paths(current_value)
  local kept = {}
  local changed = false
  for _, current in ipairs(entries) do
    if current == normalized then
      changed = true
    else
      kept[#kept + 1] = current
    end
  end

  return {
    changed = changed,
    entries = kept,
    value = table.concat(kept, ';'),
    entry = normalized,
  }
end

local function sorted_keys(map)
  local keys = {}
  for key in pairs(map or {}) do
    keys[#keys + 1] = tostring(key)
  end
  table.sort(keys)
  return keys
end

local function get_searcher_count()
  local searchers = package.searchers or package.loaders or {}
  return #searchers
end

local function compile_source(script, chunk_name)
  if loadstring ~= nil then
    return loadstring(tostring(script or ''), chunk_name)
  end
  return load(tostring(script or ''), chunk_name, 't')
end

local function package_snapshot()
  return {
    lua_version = tostring(_VERSION or ''),
    path = package.path or '',
    cpath = package.cpath or '',
    path_entries = split_paths(package.path),
    cpath_entries = split_paths(package.cpath),
    loaded_modules = sorted_keys(package.loaded),
    preloaded_modules = sorted_keys(package.preload),
    searcher_count = get_searcher_count(),
  }
end

function M.get_package_paths()
  return {
    path = package.path or '',
    cpath = package.cpath or '',
    path_entries = split_paths(package.path),
    cpath_entries = split_paths(package.cpath),
  }
end

function M.get_environment()
  return package_snapshot()
end

function M.add_package_path(path, prepend)
  local result = add_entry(package.path or '', path, prepend and true or false)
  package.path = result.value
  return {
    changed = result.changed,
    added_path = result.entry,
    path = package.path,
    path_entries = result.entries,
  }
end

function M.remove_package_path(path)
  local result = remove_entry(package.path or '', path)
  package.path = result.value
  return {
    changed = result.changed,
    removed_path = result.entry,
    path = package.path,
    path_entries = result.entries,
  }
end

function M.add_package_cpath(path, prepend)
  local result = add_entry(package.cpath or '', path, prepend and true or false)
  package.cpath = result.value
  return {
    changed = result.changed,
    added_path = result.entry,
    cpath = package.cpath,
    cpath_entries = result.entries,
  }
end

function M.remove_package_cpath(path)
  local result = remove_entry(package.cpath or '', path)
  package.cpath = result.value
  return {
    changed = result.changed,
    removed_path = result.entry,
    cpath = package.cpath,
    cpath_entries = result.entries,
  }
end

function M.add_library_root(root_path, prepend)
  local root_path_normalized = normalize_path(root_path)
  M.add_package_path(root_path_normalized .. '/?.lua', prepend)
  M.add_package_path(root_path_normalized .. '/?/init.lua', prepend)
  M.add_package_cpath(root_path_normalized .. '/?.dll', prepend)
  return M.get_package_paths()
end

function M.configure_environment(library_roots, package_paths, package_cpaths, prepend)
  local normalized_roots = {}
  for _, root_path in ipairs(library_roots or {}) do
    normalized_roots[#normalized_roots + 1] = normalize_path(root_path)
    M.add_library_root(root_path, prepend)
  end
  for _, path in ipairs(package_paths or {}) do
    M.add_package_path(path, prepend)
  end
  for _, path in ipairs(package_cpaths or {}) do
    M.add_package_cpath(path, prepend)
  end

  local snapshot = package_snapshot()
  snapshot.configured_library_roots = normalized_roots
  snapshot.prepend = prepend and true or false
  return snapshot
end

function M.run_file(path)
  local normalized = normalize_path(path)
  local loader, err = loadfile(normalized, 't')
  if loader == nil then
    error('lua_loadfile_failed:' .. tostring(err))
  end
  return {
    path = normalized,
    result = loader(),
  }
end

function M.require_module(module_name, force_reload)
  local normalized = tostring(module_name or '')
  if normalized == '' then
    error('lua_module_name_required')
  end

  if force_reload then
    package.loaded[normalized] = nil
  end

  local value = require(normalized)
  return {
    module_name = normalized,
    loaded = package.loaded[normalized] ~= nil,
    value = value,
    value_type = type(value),
  }
end

function M.unload_module(module_name)
  local normalized = tostring(module_name or '')
  if normalized == '' then
    error('lua_module_name_required')
  end
  package.loaded[normalized] = nil
  return {
    module_name = normalized,
    loaded = false,
  }
end

function M.list_loaded_modules()
  local modules = sorted_keys(package.loaded)
  return {
    count = #modules,
    modules = modules,
  }
end

function M.list_preloaded_modules()
  local modules = sorted_keys(package.preload)
  return {
    count = #modules,
    modules = modules,
  }
end

function M.preload_module_source(module_name, script, force_reload)
  local normalized = tostring(module_name or '')
  if normalized == '' then
    error('lua_module_name_required')
  end

  local loader, err = compile_source(script, '@ce_mcp_preload:' .. normalized)
  if loader == nil then
    error('lua_preload_compile_failed:' .. tostring(err))
  end

  package.preload[normalized] = function(...)
    return loader(...)
  end
  if force_reload then
    package.loaded[normalized] = nil
  end

  return {
    module_name = normalized,
    preloaded = package.preload[normalized] ~= nil,
    force_reload = force_reload and true or false,
  }
end

function M.preload_module_file(module_name, path, force_reload)
  local normalized = tostring(module_name or '')
  if normalized == '' then
    error('lua_module_name_required')
  end

  local normalized_path = normalize_path(path)
  local loader, err = loadfile(normalized_path, 't')
  if loader == nil then
    error('lua_loadfile_failed:' .. tostring(err))
  end

  package.preload[normalized] = function(...)
    return loader(...)
  end
  if force_reload then
    package.loaded[normalized] = nil
  end

  return {
    module_name = normalized,
    path = normalized_path,
    preloaded = package.preload[normalized] ~= nil,
    force_reload = force_reload and true or false,
  }
end

function M.unpreload_module(module_name)
  local normalized = tostring(module_name or '')
  if normalized == '' then
    error('lua_module_name_required')
  end

  package.preload[normalized] = nil
  return {
    module_name = normalized,
    preloaded = false,
  }
end

function M.call_module_function(module_name, function_name, args, force_reload)
  local module_result = M.require_module(module_name, force_reload)
  if type(module_result.value) ~= 'table' then
    error('lua_module_not_table:' .. tostring(module_name))
  end

  local normalized_function = tostring(function_name or '')
  local fn = module_result.value[normalized_function]
  if type(fn) ~= 'function' then
    error('lua_module_function_missing:' .. tostring(module_name) .. '.' .. normalized_function)
  end

  local call_args = args or {}
  return {
    module_name = tostring(module_name),
    function_name = normalized_function,
    value = fn(unpack_fn(call_args)),
  }
end

_G.__ce_mcp_modules["lua"] = "2026.03.08.2"
return {ok = true, module = "lua", version = "2026.03.08.2"}
''',
)
