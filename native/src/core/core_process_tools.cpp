#include "core_runtime_internal.hpp"

#include <algorithm>
#include <filesystem>
#include <sstream>
#include <stdexcept>

namespace ce_mcp
{
std::string CoreRuntime::Impl::make_attach_process_response(std::string_view request_id, std::string_view line) const
{
    const auto pid_text = extract_simple_field(line, "process_id");
    const auto process_name = extract_string_field(line, "process_name");

    if (!pid_text && !process_name)
    {
        return make_error_response(request_id, "missing_process_selector");
    }

    std::optional<DWORD> process_id;
    if (pid_text)
    {
        const auto parsed = parse_unsigned_integer(*pid_text);
        if (!parsed || *parsed == 0 || *parsed > 0xFFFFFFFFull)
        {
            return make_error_response(request_id, "invalid_process_id");
        }

        process_id = static_cast<DWORD>(*parsed);
    }
    else if (process_name)
    {
        process_id = resolve_process_id_by_name(*process_name);
        if (!process_id || *process_id == 0)
        {
            return make_error_response(request_id, "process_not_found");
        }
    }

    const auto attach_error = attach_process(process_id.value());
    if (attach_error)
    {
        return make_error_response(request_id, "attach_process_failed", *attach_error);
    }

    return make_attached_process_response(request_id);
}

std::string CoreRuntime::Impl::make_detach_process_response(std::string_view request_id) const
{
    const auto detach_error = detach_process();
    if (detach_error)
    {
        return make_error_response(request_id, "detach_process_failed", *detach_error);
    }

    return make_attached_process_response(request_id);
}

std::string CoreRuntime::Impl::make_attached_process_response(std::string_view request_id) const
{
    AttachedProcessInfo info;
    try
    {
        info = query_attached_process();
    }
    catch (const std::exception& exception)
    {
        log(std::string("ce.get_attached_process failed: ") + exception.what());
        return make_error_response(request_id, "attached_process_query_failed");
    }
    catch (...)
    {
        log("ce.get_attached_process failed with an unknown exception.");
        return make_error_response(request_id, "attached_process_query_failed");
    }

    std::string response;
    response.reserve(512);
    response += "{\"type\":\"result\",\"id\":";
    response += quote_json_or_literal(request_id);
    response += ",\"ok\":true,\"result\":{";
    response += "\"attached\":";
    response += info.attached ? "true" : "false";
    response += ",\"process_id\":" + std::to_string(info.process_id);
    response += ",\"process_name\":\"" + escape_json_string(info.process_name) + "\"";
    response += ",\"image_path\":\"" + escape_json_string(info.image_path) + "\"";
    response += "}}";
    return response;
}

std::string CoreRuntime::Impl::make_process_list_response(std::string_view request_id, std::string_view line) const
{
    std::size_t limit = kDefaultProcessListLimit;
    if (const auto limit_text = extract_simple_field(line, "limit"))
    {
        const auto parsed_limit = parse_unsigned_integer(*limit_text);
        if (!parsed_limit || *parsed_limit == 0 || *parsed_limit > kMaxProcessListLimit)
        {
            return make_error_response(request_id, "invalid_limit");
        }

        limit = static_cast<std::size_t>(*parsed_limit);
    }

    ProcessListResult result;
    try
    {
        result = list_processes(limit);
    }
    catch (const std::exception& exception)
    {
        log(std::string("ce.get_process_list failed: ") + exception.what());
        return make_error_response(request_id, "process_list_failed");
    }
    catch (...)
    {
        log("ce.get_process_list failed with an unknown exception.");
        return make_error_response(request_id, "process_list_failed");
    }

    std::ostringstream stream;
    stream << "{\"type\":\"result\",\"id\":" << quote_json_or_literal(request_id)
           << ",\"ok\":true,\"result\":{"
           << "\"total_count\":" << result.total_count
           << ",\"returned_count\":" << result.processes.size()
           << ",\"truncated\":" << (result.truncated ? "true" : "false")
           << ",\"processes\":[";

    for (std::size_t index = 0; index < result.processes.size(); ++index)
    {
        if (index != 0)
        {
            stream << ",";
        }

        const auto& entry = result.processes[index];
        stream << "{\"process_id\":" << entry.process_id
               << ",\"parent_process_id\":" << entry.parent_process_id
               << ",\"attached\":" << (entry.attached ? "true" : "false")
               << ",\"process_name\":\"" << escape_json_string(entry.process_name) << "\"}";
    }

    stream << "]}}";
    return stream.str();
}

std::string CoreRuntime::Impl::make_module_list_response(std::string_view request_id, std::string_view line) const
{
    std::size_t limit = kDefaultModuleListLimit;
    if (const auto limit_text = extract_simple_field(line, "limit"))
    {
        const auto parsed_limit = parse_unsigned_integer(*limit_text);
        if (!parsed_limit || *parsed_limit == 0 || *parsed_limit > kMaxModuleListLimit)
        {
            return make_error_response(request_id, "invalid_limit");
        }

        limit = static_cast<std::size_t>(*parsed_limit);
    }

    ModuleListResult result;
    try
    {
        result = list_modules(limit);
    }
    catch (const std::exception& exception)
    {
        log(std::string("ce.list_modules failed: ") + exception.what());
        return make_error_response(request_id, "module_list_failed");
    }
    catch (...)
    {
        log("ce.list_modules failed with an unknown exception.");
        return make_error_response(request_id, "module_list_failed");
    }

    std::ostringstream stream;
    stream << "{\"type\":\"result\",\"id\":" << quote_json_or_literal(request_id)
           << ",\"ok\":true,\"result\":{"
           << "\"process_id\":" << result.process_id
           << ",\"total_count\":" << result.total_count
           << ",\"returned_count\":" << result.modules.size()
           << ",\"truncated\":" << (result.truncated ? "true" : "false")
           << ",\"modules\":[";

    for (std::size_t index = 0; index < result.modules.size(); ++index)
    {
        if (index != 0)
        {
            stream << ",";
        }

        const auto& entry = result.modules[index];
        stream << "{\"base_address\":" << entry.base_address
               << ",\"size\":" << entry.size
               << ",\"module_name\":\"" << escape_json_string(entry.module_name) << "\""
               << ",\"module_path\":\"" << escape_json_string(entry.module_path) << "\"}";
    }

    stream << "]}}";
    return stream.str();
}

std::string CoreRuntime::Impl::make_module_list_full_response(std::string_view request_id) const
{
    ModuleListResult result;
    try
    {
        result = list_modules(std::nullopt);
    }
    catch (const std::exception& exception)
    {
        log(std::string("ce.list_modules_full failed: ") + exception.what());
        return make_error_response(request_id, "module_list_failed");
    }
    catch (...)
    {
        log("ce.list_modules_full failed with an unknown exception.");
        return make_error_response(request_id, "module_list_failed");
    }

    std::ostringstream stream;
    stream << "{\"type\":\"result\",\"id\":" << quote_json_or_literal(request_id)
           << ",\"ok\":true,\"result\":{"
           << "\"process_id\":" << result.process_id
           << ",\"total_count\":" << result.total_count
           << ",\"returned_count\":" << result.modules.size()
           << ",\"truncated\":false"
           << ",\"modules\":[";

    for (std::size_t index = 0; index < result.modules.size(); ++index)
    {
        if (index != 0)
        {
            stream << ",";
        }

        const auto& entry = result.modules[index];
        stream << "{\"base_address\":" << entry.base_address
               << ",\"size\":" << entry.size
               << ",\"module_name\":\"" << escape_json_string(entry.module_name) << "\""
               << ",\"module_path\":\"" << escape_json_string(entry.module_path) << "\"}";
    }

    stream << "]}}";
    return stream.str();
}

std::string CoreRuntime::Impl::make_resolve_symbol_response(std::string_view request_id, std::string_view line) const
{
    const auto symbol = extract_string_field(line, "symbol");
    const auto address_text = extract_simple_field(line, "address");

    if (!symbol && !address_text)
    {
        return make_error_response(request_id, "missing_symbol_selector");
    }

    SymbolResolutionResult result;
    bool ok = false;

    try
    {
        if (symbol)
        {
            ok = resolve_symbol_to_address(*symbol, result);
        }
        else if (address_text)
        {
            const auto address = parse_unsigned_integer(*address_text);
            if (!address)
            {
                return make_error_response(request_id, "invalid_address");
            }

            ok = resolve_address_to_symbol(*address, result);
        }
    }
    catch (const std::exception& exception)
    {
        log(std::string("ce.resolve_symbol failed: ") + exception.what());
        return make_error_response(request_id, "symbol_resolution_failed");
    }
    catch (...)
    {
        log("ce.resolve_symbol failed with an unknown exception.");
        return make_error_response(request_id, "symbol_resolution_failed");
    }

    if (!ok)
    {
        return make_error_response(request_id, "symbol_resolution_failed");
    }

    std::ostringstream stream;
    stream << "{\"type\":\"result\",\"id\":" << quote_json_or_literal(request_id)
           << ",\"ok\":true,\"result\":{"
           << "\"symbol\":\"" << escape_json_string(result.symbol) << "\""
           << ",\"address\":" << result.address
           << ",\"resolved_via\":\"" << escape_json_string(result.resolved_via) << "\"}}";
    return stream.str();
}

std::optional<DWORD> CoreRuntime::Impl::current_attached_process_id() const
{
    if (exported_ == nullptr)
    {
        return std::nullopt;
    }

    DWORD process_id = 0;
    if (!try_read_opened_process_id(exported_, process_id))
    {
        log("Could not read OpenedProcessID safely.");
        return std::nullopt;
    }

    return process_id;
}

std::optional<DWORD> CoreRuntime::Impl::resolve_process_id_by_name(std::string_view process_name) const
{
    if (exported_ == nullptr || exported_->getProcessIDFromProcessName == nullptr)
    {
        try
        {
            const auto processes = list_processes(std::numeric_limits<std::size_t>::max());
            for (const auto& process : processes.processes)
            {
                if (equals_case_insensitive(process.process_name, process_name))
                {
                    return process.process_id;
                }
            }
        }
        catch (...)
        {
        }

        return std::nullopt;
    }

    std::string mutable_name(process_name);
    const DWORD process_id = exported_->getProcessIDFromProcessName(mutable_name.data());
    if (process_id != 0)
    {
        return process_id;
    }

    try
    {
        const auto processes = list_processes(std::numeric_limits<std::size_t>::max());
        for (const auto& process : processes.processes)
        {
            if (equals_case_insensitive(process.process_name, process_name))
            {
                return process.process_id;
            }
        }
    }
    catch (...)
    {
    }

    return std::nullopt;
}

std::string CoreRuntime::Impl::filename_component(std::string_view path_text)
{
    return std::filesystem::path(path_text).filename().string();
}

bool CoreRuntime::Impl::module_matches_name(const ModuleEntryInfo& module, std::string_view requested_name) const
{
    return equals_case_insensitive(module.module_name, requested_name) ||
           equals_case_insensitive(module.module_path, requested_name) ||
           equals_case_insensitive(filename_component(module.module_path), requested_name);
}

std::optional<ModuleEntryInfo> CoreRuntime::Impl::find_module_by_name(std::string_view module_name) const
{
    ModuleListResult modules = list_modules(std::nullopt);
    for (const auto& module : modules.modules)
    {
        if (module_matches_name(module, module_name))
        {
            return module;
        }
    }

    return std::nullopt;
}

std::optional<std::pair<std::string, std::uint64_t>> CoreRuntime::Impl::parse_module_offset_symbol(std::string_view symbol) const
{
    const auto plus = symbol.rfind('+');
    if (plus == std::string_view::npos || plus == 0 || plus + 1 >= symbol.size())
    {
        return std::nullopt;
    }

    const auto offset = parse_unsigned_integer(symbol.substr(plus + 1));
    if (!offset)
    {
        return std::nullopt;
    }

    return std::make_pair(std::string(trim_ascii(std::string(symbol.substr(0, plus)))), *offset);
}

std::optional<DWORD> CoreRuntime::Impl::attach_process(DWORD process_id) const
{
    if (exported_ == nullptr || exported_->openProcessEx == nullptr)
    {
        return ERROR_CALL_NOT_IMPLEMENTED;
    }

    const DWORD result = exported_->openProcessEx(process_id);
    if (result == 0)
    {
        return ::GetLastError();
    }

    const auto attached_process_id = current_attached_process_id();
    if (!attached_process_id || *attached_process_id != process_id)
    {
        return ERROR_GEN_FAILURE;
    }

    return std::nullopt;
}

std::optional<DWORD> CoreRuntime::Impl::detach_process() const
{
    const auto attached_process_id = current_attached_process_id();
    if (!attached_process_id || *attached_process_id == 0)
    {
        return std::nullopt;
    }

    if (exported_ == nullptr || exported_->openProcessEx == nullptr)
    {
        return ERROR_CALL_NOT_IMPLEMENTED;
    }

    ::SetLastError(ERROR_SUCCESS);
    const DWORD result = exported_->openProcessEx(0);
    const auto detached_process_id = current_attached_process_id();
    if (detached_process_id && *detached_process_id == 0)
    {
        return std::nullopt;
    }

    if (result == 0)
    {
        const DWORD win32_error = ::GetLastError();
        if (win32_error != ERROR_SUCCESS)
        {
            if (try_force_detached_process_state(exported_))
            {
                const auto fallback_process_id = current_attached_process_id();
                if (fallback_process_id && *fallback_process_id == 0)
                {
                    return std::nullopt;
                }
            }

            return win32_error;
        }
    }

    if (try_force_detached_process_state(exported_))
    {
        const auto fallback_process_id = current_attached_process_id();
        if (fallback_process_id && *fallback_process_id == 0)
        {
            return std::nullopt;
        }
    }

    return ERROR_GEN_FAILURE;
}

MemoryAccessContext CoreRuntime::Impl::open_attached_process(DWORD desired_access) const
{
    MemoryAccessContext context;
    const auto process_id = current_attached_process_id();
    if (!process_id)
    {
        return context;
    }

    context.process_id = *process_id;
    context.attached = context.process_id != 0;
    if (!context.attached)
    {
        return context;
    }

    context.handle = ::OpenProcess(desired_access, FALSE, context.process_id);
    if (context.handle == nullptr || context.handle == INVALID_HANDLE_VALUE)
    {
        context.handle = nullptr;
        context.win32_error = ::GetLastError();
    }

    return context;
}

AttachedProcessInfo CoreRuntime::Impl::query_attached_process() const
{
    AttachedProcessInfo info;
    const auto process_id = current_attached_process_id();
    if (!process_id)
    {
        return info;
    }

    info.process_id = *process_id;
    info.attached = info.process_id != 0;
    if (!info.attached)
    {
        return info;
    }

    HANDLE process_handle = nullptr;
    bool close_handle = false;
    if (!try_read_opened_process_handle(exported_, process_handle) ||
        process_handle == nullptr || process_handle == INVALID_HANDLE_VALUE)
    {
        const auto context = open_attached_process(PROCESS_QUERY_LIMITED_INFORMATION);
        if (context.handle == nullptr || context.handle == INVALID_HANDLE_VALUE)
        {
            return info;
        }

        process_handle = context.handle;
        close_handle = true;
    }

    std::string image_path(32768, '\0');
    DWORD size = static_cast<DWORD>(image_path.size());
    if (::QueryFullProcessImageNameA(process_handle, 0, image_path.data(), &size) == TRUE && size > 0)
    {
        image_path.resize(size);
        info.image_path = image_path;
        info.process_name = std::filesystem::path(info.image_path).filename().string();
    }

    if (close_handle)
    {
        ::CloseHandle(process_handle);
    }

    return info;
}

ProcessListResult CoreRuntime::Impl::list_processes(std::size_t limit) const
{
    ProcessListResult result;
    const DWORD attached_process_id = current_attached_process_id().value_or(0);

    ScopedHandle snapshot(::CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0));
    if (!snapshot.valid())
    {
        throw std::runtime_error("CreateToolhelp32Snapshot failed.");
    }

    PROCESSENTRY32W entry {};
    entry.dwSize = sizeof(entry);
    if (::Process32FirstW(snapshot.get(), &entry) == FALSE)
    {
        return result;
    }

    do
    {
        ++result.total_count;
        if (result.processes.size() >= limit)
        {
            result.truncated = true;
            continue;
        }

        ProcessEntryInfo info;
        info.process_id = entry.th32ProcessID;
        info.parent_process_id = entry.th32ParentProcessID;
        info.attached = info.process_id == attached_process_id && attached_process_id != 0;
        info.process_name = wide_to_utf8(entry.szExeFile);
        result.processes.push_back(std::move(info));
    } while (::Process32NextW(snapshot.get(), &entry) == TRUE);

    std::sort(result.processes.begin(), result.processes.end(),
              [](const ProcessEntryInfo& left, const ProcessEntryInfo& right)
              {
                  return left.process_id < right.process_id;
              });

    return result;
}

ModuleListResult CoreRuntime::Impl::list_modules(std::optional<std::size_t> limit) const
{
    ModuleListResult result;
    const auto process_id = current_attached_process_id();
    if (!process_id || *process_id == 0)
    {
        throw std::runtime_error("No process is attached.");
    }

    result.process_id = *process_id;

    ScopedHandle snapshot(::CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32,
                                                     result.process_id));
    if (!snapshot.valid())
    {
        throw std::runtime_error("CreateToolhelp32Snapshot for modules failed.");
    }

    MODULEENTRY32W entry {};
    entry.dwSize = sizeof(entry);
    if (::Module32FirstW(snapshot.get(), &entry) == FALSE)
    {
        return result;
    }

    do
    {
        ++result.total_count;
        if (limit && result.modules.size() >= *limit)
        {
            result.truncated = true;
            continue;
        }

        ModuleEntryInfo info;
        info.base_address = reinterpret_cast<std::uint64_t>(entry.modBaseAddr);
        info.size = static_cast<std::uint64_t>(entry.modBaseSize);
        info.module_name = wide_to_utf8(entry.szModule);
        info.module_path = wide_to_utf8(entry.szExePath);
        result.modules.push_back(std::move(info));
    } while (::Module32NextW(snapshot.get(), &entry) == TRUE);

    std::sort(result.modules.begin(), result.modules.end(),
              [](const ModuleEntryInfo& left, const ModuleEntryInfo& right)
              {
                  return left.base_address < right.base_address;
              });

    return result;
}

bool CoreRuntime::Impl::resolve_symbol_to_address(std::string_view symbol, SymbolResolutionResult& result) const
{
    if (exported_ != nullptr && exported_->sym_nameToAddress != nullptr)
    {
        std::string mutable_symbol(symbol);
        UINT_PTR address = 0;
        if (exported_->sym_nameToAddress(mutable_symbol.data(), &address) != FALSE)
        {
            result.symbol = mutable_symbol;
            result.address = static_cast<std::uint64_t>(address);
            result.resolved_via = "ce_symbol";
            return true;
        }
    }

    const auto module_offset = parse_module_offset_symbol(symbol);
    if (!module_offset)
    {
        return false;
    }

    const auto module = find_module_by_name(module_offset->first);
    if (!module)
    {
        return false;
    }

    result.symbol = module_offset->first + "+" + std::to_string(module_offset->second);
    result.address = module->base_address + module_offset->second;
    result.resolved_via = "module_offset";
    return true;
}

bool CoreRuntime::Impl::resolve_address_to_symbol(std::uint64_t address, SymbolResolutionResult& result) const
{
    if (exported_ != nullptr && exported_->sym_addressToName != nullptr)
    {
        std::vector<char> buffer(4096, '\0');
        if (exported_->sym_addressToName(static_cast<UINT_PTR>(address), buffer.data(),
                                         static_cast<int>(buffer.size())) != FALSE &&
            buffer[0] != '\0')
        {
            result.symbol = buffer.data();
            result.address = address;
            result.resolved_via = "ce_symbol";
            return true;
        }
    }

    ModuleListResult modules = list_modules(std::nullopt);
    for (const auto& module : modules.modules)
    {
        if (address >= module.base_address && address < module.base_address + module.size)
        {
            result.symbol = module.module_name + "+" + std::to_string(address - module.base_address);
            result.address = address;
            result.resolved_via = "module_offset";
            return true;
        }
    }

    return false;
}
}
