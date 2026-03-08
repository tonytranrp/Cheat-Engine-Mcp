#include "core_runtime_internal.hpp"

#include <mutex>
#include <sstream>

namespace
{
using lua_KContext = intptr_t;
using lua_KFunction = int (__cdecl *)(lua_State*, int, lua_KContext);
using luaL_loadstring_fn = int (__cdecl *)(lua_State*, const char*);
using lua_pcallk_fn = int (__cdecl *)(lua_State*, int, int, int, lua_KContext, lua_KFunction);
using lua_tolstring_fn = const char* (__cdecl *)(lua_State*, int, size_t*);
using lua_settop_fn = void (__cdecl *)(lua_State*, int);

struct LuaApi
{
    luaL_loadstring_fn luaL_loadstring = nullptr;
    lua_pcallk_fn lua_pcallk = nullptr;
    lua_tolstring_fn lua_tolstring = nullptr;
    lua_settop_fn lua_settop = nullptr;
};

std::optional<LuaApi> load_lua_api()
{
    HMODULE module = ::GetModuleHandleW(L"lua53-64.dll");
    if (module == nullptr)
    {
        return std::nullopt;
    }

    LuaApi api;
    api.luaL_loadstring = reinterpret_cast<luaL_loadstring_fn>(::GetProcAddress(module, "luaL_loadstring"));
    api.lua_pcallk = reinterpret_cast<lua_pcallk_fn>(::GetProcAddress(module, "lua_pcallk"));
    api.lua_tolstring = reinterpret_cast<lua_tolstring_fn>(::GetProcAddress(module, "lua_tolstring"));
    api.lua_settop = reinterpret_cast<lua_settop_fn>(::GetProcAddress(module, "lua_settop"));

    if (api.luaL_loadstring == nullptr || api.lua_pcallk == nullptr ||
        api.lua_tolstring == nullptr || api.lua_settop == nullptr)
    {
        return std::nullopt;
    }

    return api;
}

const LuaApi& lua_api()
{
    static const std::optional<LuaApi> api = load_lua_api();
    if (!api)
    {
        throw std::runtime_error("Failed to resolve lua53-64.dll exports from the Cheat Engine process.");
    }

    return *api;
}

std::string make_lua_long_bracket(std::string_view text)
{
    std::size_t level = 0;
    for (;;)
    {
        const std::string closing = "]" + std::string(level, '=') + "]";
        if (text.find(closing) == std::string_view::npos)
        {
            return "[" + std::string(level, '=') + "[" + std::string(text) + "]" +
                   std::string(level, '=') + "]";
        }

        ++level;
    }
}

std::string build_lua_harness(std::string_view user_script, bool as_expression)
{
    std::string chunk;
    if (as_expression)
    {
        chunk = "return (" + std::string(user_script) + ")";
    }
    else
    {
        chunk = std::string(user_script);
    }

    std::ostringstream script;
    script << "local __ce_mcp_user_script = " << make_lua_long_bracket(chunk) << "\n"
           << "local function __ce_mcp_escape(value)\n"
           << "  value = tostring(value)\n"
           << "  value = value:gsub(string.char(92), string.char(92) .. string.char(92))\n"
           << "  value = value:gsub(string.char(34), string.char(92) .. string.char(34))\n"
           << "  value = value:gsub('\\r', '\\\\r')\n"
           << "  value = value:gsub('\\n', '\\\\n')\n"
           << "  value = value:gsub('\\t', '\\\\t')\n"
           << "  return value\n"
           << "end\n"
           << "local function __ce_mcp_is_array(value)\n"
           << "  local max_index = 0\n"
           << "  local count = 0\n"
           << "  for key, _ in pairs(value) do\n"
           << "    if type(key) ~= 'number' or key < 1 or key ~= math.floor(key) then return false end\n"
           << "    if key > max_index then max_index = key end\n"
           << "    count = count + 1\n"
           << "  end\n"
           << "  return max_index == count\n"
           << "end\n"
           << "local function __ce_mcp_encode(value)\n"
           << "  local value_type = type(value)\n"
           << "  if value_type == 'nil' then return 'null' end\n"
           << "  if value_type == 'boolean' then return value and 'true' or 'false' end\n"
           << "  if value_type == 'number' then\n"
           << "    if value ~= value or value == math.huge or value == -math.huge then return 'null' end\n"
           << "    return tostring(value)\n"
           << "  end\n"
           << "  if value_type == 'string' then return '\"' .. __ce_mcp_escape(value) .. '\"' end\n"
           << "  if value_type == 'table' then\n"
           << "    local parts = {}\n"
           << "    if __ce_mcp_is_array(value) then\n"
           << "      for index = 1, #value do parts[#parts + 1] = __ce_mcp_encode(value[index]) end\n"
           << "      return '[' .. table.concat(parts, ',') .. ']'\n"
           << "    end\n"
           << "    for key, item in pairs(value) do\n"
           << "      parts[#parts + 1] = '\"' .. __ce_mcp_escape(key) .. '\":' .. __ce_mcp_encode(item)\n"
           << "    end\n"
           << "    table.sort(parts)\n"
           << "    return '{' .. table.concat(parts, ',') .. '}'\n"
           << "  end\n"
           << "  return '\"' .. __ce_mcp_escape(value) .. '\"'\n"
           << "end\n"
           << "local ok, result = xpcall(function()\n"
           << "  local chunk_fn, err = load(__ce_mcp_user_script, 'ce_mcp_user', 't')\n"
           << "  if not chunk_fn then error(err) end\n"
           << "  return chunk_fn()\n"
           << "end, debug.traceback)\n"
           << "if ok then\n"
           << "  return __ce_mcp_encode({ok=true, result=result})\n"
           << "end\n"
           << "return __ce_mcp_encode({ok=false, error=tostring(result)})\n";
    return script.str();
}
}

namespace ce_mcp
{
std::string CoreRuntime::Impl::make_lua_eval_response(std::string_view request_id, std::string_view line) const
{
    const auto script = extract_string_field(line, "script");
    if (!script)
    {
        return make_error_response(request_id, "missing_script");
    }

    DWORD win32_error = ERROR_SUCCESS;
    const auto payload = execute_lua_eval(*script, true, win32_error);
    if (!payload)
    {
        return make_error_response(request_id, "lua_eval_failed", win32_error);
    }

    return "{\"type\":\"result\",\"id\":" + quote_json_or_literal(request_id) + "," +
           payload->substr(1, payload->size() - 2) + "}";
}

std::string CoreRuntime::Impl::make_lua_exec_response(std::string_view request_id, std::string_view line) const
{
    const auto script = extract_string_field(line, "script");
    if (!script)
    {
        return make_error_response(request_id, "missing_script");
    }

    DWORD win32_error = ERROR_SUCCESS;
    const auto payload = execute_lua_eval(*script, false, win32_error);
    if (!payload)
    {
        return make_error_response(request_id, "lua_exec_failed", win32_error);
    }

    return "{\"type\":\"result\",\"id\":" + quote_json_or_literal(request_id) + "," +
           payload->substr(1, payload->size() - 2) + "}";
}

std::string CoreRuntime::Impl::make_auto_assemble_response(std::string_view request_id, std::string_view line) const
{
    const auto script = extract_string_field(line, "script");
    if (!script)
    {
        return make_error_response(request_id, "missing_script");
    }

    const std::string wrapped = "return {success=autoAssemble(" + make_lua_long_bracket(*script) + ")}";
    DWORD win32_error = ERROR_SUCCESS;
    const auto payload = execute_lua_eval(wrapped, false, win32_error);
    if (!payload)
    {
        return make_error_response(request_id, "auto_assemble_failed", win32_error);
    }

    return "{\"type\":\"result\",\"id\":" + quote_json_or_literal(request_id) + "," +
           payload->substr(1, payload->size() - 2) + "}";
}

std::optional<std::string> CoreRuntime::Impl::execute_lua_eval(std::string_view script,
                                                               bool as_expression,
                                                               DWORD& win32_error) const
{
    if (exported_ == nullptr || exported_->GetLuaState == nullptr)
    {
        win32_error = ERROR_CALL_NOT_IMPLEMENTED;
        return std::nullopt;
    }

    lua_State* lua_state = exported_->GetLuaState();
    if (lua_state == nullptr)
    {
        win32_error = ERROR_INVALID_HANDLE;
        return std::nullopt;
    }

    const auto& api = lua_api();
    const std::string harness = build_lua_harness(script, as_expression);
    static std::mutex lua_mutex;
    std::lock_guard<std::mutex> lock(lua_mutex);

    api.lua_settop(lua_state, 0);

    if (api.luaL_loadstring(lua_state, harness.c_str()) != 0)
    {
        size_t length = 0;
        const char* error_text = api.lua_tolstring(lua_state, -1, &length);
        log(std::string("luaL_loadstring failed: ") + std::string(error_text ? error_text : "unknown"));
        api.lua_settop(lua_state, 0);
        win32_error = ERROR_BAD_FORMAT;
        return std::nullopt;
    }

    if (api.lua_pcallk(lua_state, 0, 1, 0, 0, nullptr) != 0)
    {
        size_t length = 0;
        const char* error_text = api.lua_tolstring(lua_state, -1, &length);
        log(std::string("lua_pcallk failed: ") + std::string(error_text ? error_text : "unknown"));
        api.lua_settop(lua_state, 0);
        win32_error = ERROR_GEN_FAILURE;
        return std::nullopt;
    }

    size_t length = 0;
    const char* payload = api.lua_tolstring(lua_state, -1, &length);
    std::string output;
    if (payload != nullptr)
    {
        output.assign(payload, length);
    }
    api.lua_settop(lua_state, 0);

    if (output.size() < 2 || output.front() != '{' || output.back() != '}')
    {
        win32_error = ERROR_INVALID_DATA;
        return std::nullopt;
    }

    return output;
}

bool CoreRuntime::Impl::execute_auto_assemble(std::string_view script) const
{
    const std::string wrapped = "return autoAssemble(" + make_lua_long_bracket(script) + ")";
    DWORD win32_error = ERROR_SUCCESS;
    const auto payload = execute_lua_eval(wrapped, false, win32_error);
    return payload.has_value() && payload->find("\"ok\":true") != std::string::npos &&
           payload->find("\"result\":true") != std::string::npos;
}
}
