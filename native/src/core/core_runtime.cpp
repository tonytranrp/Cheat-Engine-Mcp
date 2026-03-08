#include "core_runtime_internal.hpp"

#include <algorithm>
#include <fstream>

namespace ce_mcp
{
CoreRuntime::CoreRuntime(CeMcpHostContext host) : impl_(std::make_unique<Impl>(host)) {}
CoreRuntime::~CoreRuntime() = default;
CoreRuntime::CoreRuntime(CoreRuntime&&) noexcept = default;
CoreRuntime& CoreRuntime::operator=(CoreRuntime&&) noexcept = default;

void CoreRuntime::start()
{
    impl_->start();
}

void CoreRuntime::stop() noexcept
{
    impl_->stop();
}

CoreRuntime::Impl::Impl(CeMcpHostContext host)
    : host_(host),
      exported_(static_cast<PExportedFunctions>(host.exported_functions))
{
}

void CoreRuntime::Impl::start()
{
    client_ = std::make_unique<mcp::Client>(
        make_client_config(),
        [this](std::string_view message)
        {
            log(message);
        },
        [this](std::string_view line)
        {
            return handle_request(line);
        },
        tool_names());
    client_->start(host_.plugin_id);
}

void CoreRuntime::Impl::stop() noexcept
{
    if (client_)
    {
        client_->stop();
    }
}

mcp::Config CoreRuntime::Impl::make_client_config() const
{
    mcp::Config config;
    config.host = ce_mcp::config::kDefaultHost;
    config.port = ce_mcp::config::kDefaultPort;
    config.reconnect_delay = std::chrono::milliseconds(ce_mcp::config::kReconnectDelayMs);
    config.poll_interval = std::chrono::milliseconds(ce_mcp::config::kPollIntervalMs);

    apply_runtime_config_file(config);

    if (const auto host = read_environment_variable("CE_MCP_HOST"))
    {
        config.host = *host;
    }

    if (const auto port_text = read_environment_variable("CE_MCP_PORT"))
    {
        if (const auto port = parse_port(*port_text))
        {
            config.port = *port;
        }
    }

    if (const auto reconnect_text = read_environment_variable("CE_MCP_RECONNECT_DELAY_MS"))
    {
        if (const auto reconnect = parse_positive_int(*reconnect_text))
        {
            config.reconnect_delay = std::chrono::milliseconds(*reconnect);
        }
    }

    return config;
}

void CoreRuntime::Impl::apply_runtime_config_file(mcp::Config& config) const
{
    const auto runtime_dir = runtime_directory_from_module(reinterpret_cast<const void*>(&runtime_config_marker));
    if (!runtime_dir)
    {
        return;
    }

    const auto config_path = runtime_dir.value() / ce_mcp::config::kRuntimeConfigFileName;
    std::ifstream input(config_path);
    if (!input)
    {
        return;
    }

    std::string line;
    while (std::getline(input, line))
    {
        const auto trimmed = trim_ascii(line);
        if (trimmed.empty() || trimmed.front() == '#')
        {
            continue;
        }

        const auto separator = trimmed.find('=');
        if (separator == std::string::npos)
        {
            continue;
        }

        const auto key = trim_ascii(trimmed.substr(0, separator));
        const auto value = trim_ascii(trimmed.substr(separator + 1));

        if (key == "host" && !value.empty())
        {
            config.host = value;
        }
        else if (key == "port")
        {
            if (const auto port = parse_port(value))
            {
                config.port = *port;
            }
        }
        else if (key == "reconnect_delay_ms")
        {
            if (const auto reconnect = parse_positive_int(value))
            {
                config.reconnect_delay = std::chrono::milliseconds(*reconnect);
            }
        }
    }
}

void CoreRuntime::Impl::log(std::string_view message) const
{
    if (host_.log != nullptr)
    {
        std::string line(message);
        host_.log(line.c_str());
        return;
    }

    std::string line;
    line.reserve(std::char_traits<char>::length(ce_mcp::config::kCoreLogPrefix) + message.size() + 2);
    line.append(ce_mcp::config::kCoreLogPrefix);
    line.append(message);
    line.push_back('\n');
    ::OutputDebugStringA(line.c_str());
}

mcp::ToolNames CoreRuntime::Impl::tool_names() const
{
    return {
        "ce.list_tools",
        "ce.get_attached_process",
        "ce.attach_process",
        "ce.detach_process",
        "ce.get_process_list",
        "ce.list_modules",
        "ce.list_modules_full",
        "ce.query_memory",
        "ce.query_memory_map",
        "ce.resolve_symbol",
        "ce.aob_scan",
        "ce.exported.list",
        "ce.exported.get",
        "ce.lua_eval",
        "ce.lua_exec",
        "ce.auto_assemble",
        "ce.read_memory",
        "ce.write_memory",
    };
}

std::optional<std::string> CoreRuntime::Impl::handle_request(std::string_view line)
{
    const auto request_id = extract_simple_field(line, "id").value_or("null");
    const auto tool = extract_string_field(line, "tool");
    if (!tool)
    {
        return make_error_response(request_id, "missing_tool");
    }

    if (*tool == "ce.list_tools")
    {
        return make_list_tools_response(request_id);
    }

    if (*tool == "ce.get_attached_process")
    {
        return make_attached_process_response(request_id);
    }

    if (*tool == "ce.attach_process")
    {
        return make_attach_process_response(request_id, line);
    }

    if (*tool == "ce.detach_process")
    {
        return make_detach_process_response(request_id);
    }

    if (*tool == "ce.get_process_list")
    {
        return make_process_list_response(request_id, line);
    }

    if (*tool == "ce.list_modules")
    {
        return make_module_list_response(request_id, line);
    }

    if (*tool == "ce.list_modules_full")
    {
        return make_module_list_full_response(request_id);
    }

    if (*tool == "ce.query_memory")
    {
        return make_query_memory_response(request_id, line);
    }

    if (*tool == "ce.query_memory_map")
    {
        return make_query_memory_map_response(request_id, line);
    }

    if (*tool == "ce.resolve_symbol")
    {
        return make_resolve_symbol_response(request_id, line);
    }

    if (*tool == "ce.aob_scan")
    {
        return make_aob_scan_response(request_id, line);
    }

    if (*tool == "ce.exported.list")
    {
        return make_exported_list_response(request_id, line);
    }

    if (*tool == "ce.exported.get")
    {
        return make_exported_get_response(request_id, line);
    }

    if (*tool == "ce.lua_eval")
    {
        return make_lua_eval_response(request_id, line);
    }

    if (*tool == "ce.lua_exec")
    {
        return make_lua_exec_response(request_id, line);
    }

    if (*tool == "ce.auto_assemble")
    {
        return make_auto_assemble_response(request_id, line);
    }

    if (*tool == "ce.read_memory")
    {
        return make_read_memory_response(request_id, line);
    }

    if (*tool == "ce.write_memory")
    {
        return make_write_memory_response(request_id, line);
    }

    return make_error_response(request_id, "unsupported_tool");
}

std::string CoreRuntime::Impl::make_list_tools_response(std::string_view request_id) const
{
    std::string response;
    response.reserve(256);
    response += "{\"type\":\"result\",\"id\":";
    response += quote_json_or_literal(request_id);
    response += ",\"ok\":true,\"result\":{\"tools\":";
    response += make_json_string_array(tool_names());
    response += "}}";
    return response;
}

std::string CoreRuntime::Impl::make_error_response(std::string_view request_id,
                                                   std::string_view error,
                                                   std::optional<DWORD> win32_error) const
{
    std::ostringstream stream;
    stream << "{\"type\":\"result\",\"id\":" << quote_json_or_literal(request_id)
           << ",\"ok\":false,\"error\":\"" << escape_json_string(error) << "\"";
    if (win32_error)
    {
        stream << ",\"win32_error\":" << *win32_error;
    }

    stream << "}";
    return stream.str();
}

std::string CoreRuntime::Impl::quote_json_or_literal(std::string_view value) const
{
    const bool numeric = !value.empty() &&
                         std::find_if(value.begin(), value.end(),
                                      [](char ch)
                                      {
                                          return (ch < '0' || ch > '9') && ch != '-';
                                      }) == value.end();
    if (numeric || value == "null" || value == "true" || value == "false")
    {
        return std::string(value);
    }

    return "\"" + escape_json_string(value) + "\"";
}
}
