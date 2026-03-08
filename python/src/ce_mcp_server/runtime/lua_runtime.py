from __future__ import annotations

from ..context import RuntimeModule

LUA_RUNTIME = RuntimeModule(
    name="lua",
    version="2026.03.08.3",
    script=r'''
_G.__ce_mcp = _G.__ce_mcp or {}
_G.__ce_mcp_modules = _G.__ce_mcp_modules or {}
local root = _G.__ce_mcp
root.lua = root.lua or {}
root.lua_state = root.lua_state or {
  managed_path_entries = {},
  managed_cpath_entries = {},
  configured_library_roots = {},
}
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

local function clone_entries(entries)
  local result = {}
  for _, value in ipairs(entries or {}) do
    result[#result + 1] = tostring(value)
  end
  return result
end

local function has_entry(entries, target)
  for _, current in ipairs(entries or {}) do
    if current == target then
      return true
    end
  end
  return false
end

local function remember_entry(entries, entry)
  local normalized = normalize_path(entry)
  if not has_entry(entries, normalized) then
    entries[#entries + 1] = normalized
  end
end

local function forget_entry(entries, entry)
  local normalized = normalize_path(entry)
  local kept = {}
  for _, current in ipairs(entries or {}) do
    if current ~= normalized then
      kept[#kept + 1] = current
    end
  end
  return kept
end

local function get_state()
  root.lua_state = root.lua_state or {
    managed_path_entries = {},
    managed_cpath_entries = {},
    configured_library_roots = {},
  }
  return root.lua_state
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
  local state = get_state()
  return {
    lua_version = tostring(_VERSION or ''),
    path = package.path or '',
    cpath = package.cpath or '',
    path_entries = split_paths(package.path),
    cpath_entries = split_paths(package.cpath),
    loaded_modules = sorted_keys(package.loaded),
    preloaded_modules = sorted_keys(package.preload),
    searcher_count = get_searcher_count(),
    managed_path_entries = clone_entries(state.managed_path_entries),
    managed_cpath_entries = clone_entries(state.managed_cpath_entries),
    configured_library_roots = clone_entries(state.configured_library_roots),
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
  local state = get_state()
  if result.changed then
    state.managed_path_entries = forget_entry(state.managed_path_entries, result.entry)
  end
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
  local state = get_state()
  if result.changed then
    state.managed_cpath_entries = forget_entry(state.managed_cpath_entries, result.entry)
  end
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
  local snapshot = package_snapshot()
  snapshot.library_root = root_path_normalized
  snapshot.prepend = prepend and true or false
  return snapshot
end

function M.remove_library_root(root_path)
  local root_path_normalized = normalize_path(root_path)
  M.remove_package_path(root_path_normalized .. '/?.lua')
  M.remove_package_path(root_path_normalized .. '/?/init.lua')
  M.remove_package_cpath(root_path_normalized .. '/?.dll')

  local state = get_state()
  state.configured_library_roots = forget_entry(state.configured_library_roots, root_path_normalized)

  local snapshot = package_snapshot()
  snapshot.library_root = root_path_normalized
  return snapshot
end

function M.reset_environment()
  local state = get_state()

  for _, path in ipairs(clone_entries(state.managed_path_entries)) do
    M.remove_package_path(path)
  end
  for _, path in ipairs(clone_entries(state.managed_cpath_entries)) do
    M.remove_package_cpath(path)
  end

  state.managed_path_entries = {}
  state.managed_cpath_entries = {}
  state.configured_library_roots = {}

  local snapshot = package_snapshot()
  snapshot.reset = true
  return snapshot
end

function M.configure_environment(library_roots, package_paths, package_cpaths, prepend, reset_managed)
  if reset_managed then
    M.reset_environment()
  end

  local state = get_state()
  local normalized_roots = {}

  for _, root_path in ipairs(library_roots or {}) do
    local root_path_normalized = normalize_path(root_path)
    normalized_roots[#normalized_roots + 1] = root_path_normalized

    local path_one = M.add_package_path(root_path_normalized .. '/?.lua', prepend)
    if path_one.changed then
      remember_entry(state.managed_path_entries, path_one.added_path)
    end

    local path_two = M.add_package_path(root_path_normalized .. '/?/init.lua', prepend)
    if path_two.changed then
      remember_entry(state.managed_path_entries, path_two.added_path)
    end

    local cpath_one = M.add_package_cpath(root_path_normalized .. '/?.dll', prepend)
    if cpath_one.changed then
      remember_entry(state.managed_cpath_entries, cpath_one.added_path)
    end
  end

  for _, path in ipairs(package_paths or {}) do
    local result = M.add_package_path(path, prepend)
    if result.changed then
      remember_entry(state.managed_path_entries, result.added_path)
    end
  end

  for _, path in ipairs(package_cpaths or {}) do
    local result = M.add_package_cpath(path, prepend)
    if result.changed then
      remember_entry(state.managed_cpath_entries, result.added_path)
    end
  end

  state.configured_library_roots = normalized_roots

  local snapshot = package_snapshot()
  snapshot.prepend = prepend and true or false
  snapshot.reset_managed = reset_managed and true or false
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

_G.__ce_mcp_modules["lua"] = "2026.03.08.3"
return {ok = true, module = "lua", version = "2026.03.08.3"}
''',
)
