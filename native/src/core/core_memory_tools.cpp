#include "core_runtime_internal.hpp"

#include <algorithm>
#include <limits>
#include <sstream>

namespace ce_mcp
{
std::string CoreRuntime::Impl::make_query_memory_response(std::string_view request_id, std::string_view line) const
{
    const auto address_text = extract_simple_field(line, "address");
    if (!address_text)
    {
        return make_error_response(request_id, "missing_address");
    }

    const auto address = parse_unsigned_integer(*address_text);
    if (!address)
    {
        return make_error_response(request_id, "invalid_address");
    }

    const auto process_id = current_attached_process_id();
    if (!process_id || *process_id == 0)
    {
        return make_error_response(request_id, "no_attached_process");
    }

    MemoryRegionInfo result;
    std::optional<DWORD> error_code;
    try
    {
        error_code = query_memory_region(*address, result);
    }
    catch (const std::exception& exception)
    {
        log(std::string("ce.query_memory failed: ") + exception.what());
        return make_error_response(request_id, "query_memory_failed");
    }
    catch (...)
    {
        log("ce.query_memory failed with an unknown exception.");
        return make_error_response(request_id, "query_memory_failed");
    }

    if (error_code)
    {
        return make_error_response(request_id, "query_memory_failed", *error_code);
    }

    std::ostringstream stream;
    stream << "{\"type\":\"result\",\"id\":" << quote_json_or_literal(request_id)
           << ",\"ok\":true,\"result\":{"
           << "\"process_id\":" << result.process_id
           << ",\"address\":" << result.address
           << ",\"base_address\":" << result.base_address
           << ",\"allocation_base\":" << result.allocation_base
           << ",\"region_size\":" << result.region_size
           << ",\"state\":" << result.state
           << ",\"state_name\":\"" << memory_state_name(result.state) << "\""
           << ",\"protect\":" << result.protect
           << ",\"protect_name\":\"" << memory_protect_name(result.protect) << "\""
           << ",\"allocation_protect\":" << result.allocation_protect
           << ",\"allocation_protect_name\":\"" << memory_protect_name(result.allocation_protect) << "\""
           << ",\"type\":" << result.type
           << ",\"type_name\":\"" << memory_type_name(result.type) << "\""
           << ",\"readable\":" << (result.readable ? "true" : "false")
           << ",\"writable\":" << (result.writable ? "true" : "false")
           << ",\"executable\":" << (result.executable ? "true" : "false")
           << ",\"guarded\":" << (result.guarded ? "true" : "false")
           << "}}";
    return stream.str();
}

std::string CoreRuntime::Impl::make_query_memory_map_response(std::string_view request_id, std::string_view line) const
{
    MemoryMapQuery query;

    if (const auto limit_text = extract_simple_field(line, "limit"))
    {
        const auto parsed_limit = parse_unsigned_integer(*limit_text);
        if (!parsed_limit || *parsed_limit == 0 || *parsed_limit > kMaxMemoryMapLimit)
        {
            return make_error_response(request_id, "invalid_limit");
        }

        query.limit = static_cast<std::size_t>(*parsed_limit);
    }

    if (const auto start_text = extract_simple_field(line, "start_address"))
    {
        const auto start_address = parse_unsigned_integer(*start_text);
        if (!start_address)
        {
            return make_error_response(request_id, "invalid_start_address");
        }

        query.start_address = *start_address;
    }

    if (const auto end_text = extract_simple_field(line, "end_address"))
    {
        const auto end_address = parse_unsigned_integer(*end_text);
        if (!end_address)
        {
            return make_error_response(request_id, "invalid_end_address");
        }

        query.end_address = *end_address;
    }

    if (query.end_address != 0 && query.end_address < query.start_address)
    {
        return make_error_response(request_id, "invalid_address_range");
    }

    if (const auto include_free_text = extract_simple_field(line, "include_free"))
    {
        bool include_free = false;
        if (!parse_bool(*include_free_text, include_free))
        {
            return make_error_response(request_id, "invalid_include_free");
        }

        query.include_free = include_free;
    }

    MemoryMapResult result;
    std::optional<DWORD> error_code;
    try
    {
        error_code = query_memory_map(query, result);
    }
    catch (const std::exception& exception)
    {
        log(std::string("ce.query_memory_map failed: ") + exception.what());
        return make_error_response(request_id, "query_memory_map_failed");
    }
    catch (...)
    {
        log("ce.query_memory_map failed with an unknown exception.");
        return make_error_response(request_id, "query_memory_map_failed");
    }

    if (error_code)
    {
        return make_error_response(request_id, "query_memory_map_failed", *error_code);
    }

    std::ostringstream stream;
    stream << "{\"type\":\"result\",\"id\":" << quote_json_or_literal(request_id)
           << ",\"ok\":true,\"result\":{"
           << "\"process_id\":" << result.process_id
           << ",\"start_address\":" << query.start_address
           << ",\"end_address\":" << query.end_address
           << ",\"include_free\":" << (query.include_free ? "true" : "false")
           << ",\"total_count\":" << result.total_count
           << ",\"returned_count\":" << result.regions.size()
           << ",\"truncated\":" << (result.truncated ? "true" : "false")
           << ",\"regions\":[";

    for (std::size_t index = 0; index < result.regions.size(); ++index)
    {
        if (index != 0)
        {
            stream << ",";
        }

        const auto& entry = result.regions[index];
        stream << "{\"base_address\":" << entry.base_address
               << ",\"allocation_base\":" << entry.allocation_base
               << ",\"region_size\":" << entry.region_size
               << ",\"state\":" << entry.state
               << ",\"state_name\":\"" << memory_state_name(entry.state) << "\""
               << ",\"protect\":" << entry.protect
               << ",\"protect_name\":\"" << memory_protect_name(entry.protect) << "\""
               << ",\"allocation_protect\":" << entry.allocation_protect
               << ",\"allocation_protect_name\":\"" << memory_protect_name(entry.allocation_protect) << "\""
               << ",\"type\":" << entry.type
               << ",\"type_name\":\"" << memory_type_name(entry.type) << "\""
               << ",\"readable\":" << (entry.readable ? "true" : "false")
               << ",\"writable\":" << (entry.writable ? "true" : "false")
               << ",\"executable\":" << (entry.executable ? "true" : "false")
               << ",\"guarded\":" << (entry.guarded ? "true" : "false")
               << "}";
    }

    stream << "]}}";
    return stream.str();
}

std::string CoreRuntime::Impl::make_aob_scan_response(std::string_view request_id, std::string_view line) const
{
    const auto pattern_text = extract_string_field(line, "pattern");
    if (!pattern_text)
    {
        return make_error_response(request_id, "missing_pattern");
    }

    AobScanQuery query;
    const auto pattern = parse_aob_pattern(*pattern_text);
    if (!pattern)
    {
        return make_error_response(request_id, "invalid_pattern");
    }

    query.pattern = *pattern;

    if (const auto module_name = extract_string_field(line, "module_name"))
    {
        query.module_name = *module_name;
    }

    if (const auto start_text = extract_simple_field(line, "start_address"))
    {
        const auto start_address = parse_unsigned_integer(*start_text);
        if (!start_address)
        {
            return make_error_response(request_id, "invalid_start_address");
        }

        query.start_address = *start_address;
    }

    if (const auto end_text = extract_simple_field(line, "end_address"))
    {
        const auto end_address = parse_unsigned_integer(*end_text);
        if (!end_address)
        {
            return make_error_response(request_id, "invalid_end_address");
        }

        query.end_address = *end_address;
    }

    if (query.start_address && query.end_address && *query.end_address < *query.start_address)
    {
        return make_error_response(request_id, "invalid_address_range");
    }

    if (const auto max_results_text = extract_simple_field(line, "max_results"))
    {
        const auto parsed_limit = parse_unsigned_integer(*max_results_text);
        if (!parsed_limit || *parsed_limit == 0 || *parsed_limit > kMaxAobResultLimit)
        {
            return make_error_response(request_id, "invalid_max_results");
        }

        query.max_results = static_cast<std::size_t>(*parsed_limit);
    }

    AobScanResult result;
    std::optional<DWORD> error_code;
    try
    {
        error_code = aob_scan(query, result);
    }
    catch (const std::exception& exception)
    {
        log(std::string("ce.aob_scan failed: ") + exception.what());
        return make_error_response(request_id, "aob_scan_failed");
    }
    catch (...)
    {
        log("ce.aob_scan failed with an unknown exception.");
        return make_error_response(request_id, "aob_scan_failed");
    }

    if (error_code)
    {
        return make_error_response(request_id, "aob_scan_failed", *error_code);
    }

    std::ostringstream stream;
    stream << "{\"type\":\"result\",\"id\":" << quote_json_or_literal(request_id)
           << ",\"ok\":true,\"result\":{"
           << "\"process_id\":" << result.process_id
           << ",\"pattern\":\"" << escape_json_string(*pattern_text) << "\"";
    if (query.module_name)
    {
        stream << ",\"module_name\":\"" << escape_json_string(*query.module_name) << "\"";
    }
    if (query.start_address)
    {
        stream << ",\"start_address\":" << *query.start_address;
    }
    if (query.end_address)
    {
        stream << ",\"end_address\":" << *query.end_address;
    }
    stream << ",\"scanned_region_count\":" << result.scanned_region_count
           << ",\"scanned_byte_count\":" << result.scanned_byte_count
           << ",\"returned_count\":" << result.matches.size()
           << ",\"truncated\":" << (result.truncated ? "true" : "false")
           << ",\"matches\":[";

    for (std::size_t index = 0; index < result.matches.size(); ++index)
    {
        if (index != 0)
        {
            stream << ",";
        }

        stream << result.matches[index];
    }

    stream << "]}}";
    return stream.str();
}

std::string CoreRuntime::Impl::make_read_memory_response(std::string_view request_id, std::string_view line) const
{
    const auto address_text = extract_simple_field(line, "address");
    if (!address_text)
    {
        return make_error_response(request_id, "missing_address");
    }

    const auto address = parse_unsigned_integer(*address_text);
    if (!address)
    {
        return make_error_response(request_id, "invalid_address");
    }

    const auto size_text = extract_simple_field(line, "size");
    if (!size_text)
    {
        return make_error_response(request_id, "missing_size");
    }

    const auto size_value = parse_unsigned_integer(*size_text);
    if (!size_value || *size_value == 0 || *size_value > kMaxMemoryTransferSize)
    {
        return make_error_response(request_id, "invalid_size");
    }

    const auto context = open_attached_process(PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION);
    if (!context.attached)
    {
        return make_error_response(request_id, "no_attached_process");
    }

    if (context.handle == nullptr || context.handle == INVALID_HANDLE_VALUE)
    {
        return make_error_response(request_id, "open_process_failed", context.win32_error);
    }

    ScopedHandle process(context.handle);
    std::vector<unsigned char> buffer(static_cast<std::size_t>(*size_value));
    SIZE_T bytes_read = 0;
    const BOOL ok = ::ReadProcessMemory(process.get(),
                                        reinterpret_cast<LPCVOID>(static_cast<UINT_PTR>(*address)),
                                        buffer.data(), buffer.size(), &bytes_read);
    const DWORD win32_error = ok ? ERROR_SUCCESS : ::GetLastError();
    if (ok == FALSE && bytes_read == 0)
    {
        return make_error_response(request_id, "read_memory_failed", win32_error);
    }

    buffer.resize(static_cast<std::size_t>(bytes_read));

    std::ostringstream stream;
    stream << "{\"type\":\"result\",\"id\":" << quote_json_or_literal(request_id)
           << ",\"ok\":true,\"result\":{"
           << "\"process_id\":" << context.process_id
           << ",\"address\":" << *address
           << ",\"bytes_read\":" << buffer.size()
           << ",\"partial\":" << (ok == FALSE ? "true" : "false")
           << ",\"win32_error\":" << win32_error
           << ",\"bytes_hex\":\"" << bytes_to_hex_string(buffer) << "\"}}";
    return stream.str();
}

std::string CoreRuntime::Impl::make_write_memory_response(std::string_view request_id, std::string_view line) const
{
    const auto address_text = extract_simple_field(line, "address");
    if (!address_text)
    {
        return make_error_response(request_id, "missing_address");
    }

    const auto address = parse_unsigned_integer(*address_text);
    if (!address)
    {
        return make_error_response(request_id, "invalid_address");
    }

    const auto bytes_hex = extract_simple_field(line, "bytes_hex");
    if (!bytes_hex)
    {
        return make_error_response(request_id, "missing_bytes_hex");
    }

    const auto bytes = parse_hex_bytes(*bytes_hex);
    if (!bytes || bytes->empty() || bytes->size() > kMaxMemoryTransferSize)
    {
        return make_error_response(request_id, "invalid_bytes_hex");
    }

    const auto context = open_attached_process(PROCESS_VM_OPERATION | PROCESS_VM_WRITE |
                                               PROCESS_QUERY_LIMITED_INFORMATION);
    if (!context.attached)
    {
        return make_error_response(request_id, "no_attached_process");
    }

    if (context.handle == nullptr || context.handle == INVALID_HANDLE_VALUE)
    {
        return make_error_response(request_id, "open_process_failed", context.win32_error);
    }

    ScopedHandle process(context.handle);
    SIZE_T bytes_written = 0;
    const BOOL ok = ::WriteProcessMemory(process.get(),
                                         reinterpret_cast<LPVOID>(static_cast<UINT_PTR>(*address)),
                                         bytes->data(), bytes->size(), &bytes_written);
    const DWORD win32_error = ok ? ERROR_SUCCESS : ::GetLastError();
    if (ok == FALSE && bytes_written == 0)
    {
        return make_error_response(request_id, "write_memory_failed", win32_error);
    }

    std::ostringstream stream;
    stream << "{\"type\":\"result\",\"id\":" << quote_json_or_literal(request_id)
           << ",\"ok\":true,\"result\":{"
           << "\"process_id\":" << context.process_id
           << ",\"address\":" << *address
           << ",\"bytes_written\":" << bytes_written
           << ",\"partial\":" << (ok == FALSE ? "true" : "false")
           << ",\"win32_error\":" << win32_error
           << ",\"bytes_hex\":\"" << escape_json_string(*bytes_hex) << "\"}}";
    return stream.str();
}

std::optional<DWORD> CoreRuntime::Impl::query_memory_region(std::uint64_t address, MemoryRegionInfo& result) const
{
    const auto context = open_attached_process(PROCESS_QUERY_INFORMATION);
    if (!context.attached)
    {
        return ERROR_INVALID_HANDLE;
    }

    if (context.handle == nullptr || context.handle == INVALID_HANDLE_VALUE)
    {
        return context.win32_error;
    }

    ScopedHandle process(context.handle);
    MEMORY_BASIC_INFORMATION mbi {};
    const SIZE_T queried = ::VirtualQueryEx(
        process.get(),
        reinterpret_cast<LPCVOID>(static_cast<UINT_PTR>(address)),
        &mbi,
        sizeof(mbi));
    if (queried == 0)
    {
        return ::GetLastError();
    }

    result.process_id = context.process_id;
    result.address = address;
    result.base_address = reinterpret_cast<std::uint64_t>(mbi.BaseAddress);
    result.allocation_base = reinterpret_cast<std::uint64_t>(mbi.AllocationBase);
    result.region_size = static_cast<std::uint64_t>(mbi.RegionSize);
    result.state = mbi.State;
    result.protect = mbi.Protect;
    result.allocation_protect = mbi.AllocationProtect;
    result.type = mbi.Type;
    result.readable = is_readable_protection(mbi.Protect);
    result.writable = is_writable_protection(mbi.Protect);
    result.executable = is_executable_protection(mbi.Protect);
    result.guarded = (mbi.Protect & PAGE_GUARD) != 0;
    return std::nullopt;
}

std::optional<DWORD> CoreRuntime::Impl::query_memory_map(const MemoryMapQuery& query, MemoryMapResult& result) const
{
    const auto context = open_attached_process(PROCESS_QUERY_INFORMATION);
    if (!context.attached)
    {
        return ERROR_INVALID_HANDLE;
    }

    if (context.handle == nullptr || context.handle == INVALID_HANDLE_VALUE)
    {
        return context.win32_error;
    }

    ScopedHandle process(context.handle);
    SYSTEM_INFO system_info {};
    ::GetSystemInfo(&system_info);

    const std::uint64_t minimum_address =
        reinterpret_cast<std::uint64_t>(system_info.lpMinimumApplicationAddress);
    const std::uint64_t maximum_address =
        reinterpret_cast<std::uint64_t>(system_info.lpMaximumApplicationAddress);
    std::uint64_t current_address = std::max(query.start_address, minimum_address);
    const std::uint64_t end_address =
        query.end_address == 0 ? maximum_address : std::min(query.end_address, maximum_address);

    result.process_id = context.process_id;

    while (current_address < end_address)
    {
        MEMORY_BASIC_INFORMATION mbi {};
        const SIZE_T queried = ::VirtualQueryEx(
            process.get(),
            reinterpret_cast<LPCVOID>(static_cast<UINT_PTR>(current_address)),
            &mbi,
            sizeof(mbi));
        if (queried == 0)
        {
            const DWORD win32_error = ::GetLastError();
            if (win32_error == ERROR_INVALID_PARAMETER)
            {
                break;
            }

            return win32_error;
        }

        MemoryRegionInfo entry;
        entry.process_id = context.process_id;
        entry.address = current_address;
        entry.base_address = reinterpret_cast<std::uint64_t>(mbi.BaseAddress);
        entry.allocation_base = reinterpret_cast<std::uint64_t>(mbi.AllocationBase);
        entry.region_size = static_cast<std::uint64_t>(mbi.RegionSize);
        entry.state = mbi.State;
        entry.protect = mbi.Protect;
        entry.allocation_protect = mbi.AllocationProtect;
        entry.type = mbi.Type;
        entry.readable = is_readable_protection(mbi.Protect);
        entry.writable = is_writable_protection(mbi.Protect);
        entry.executable = is_executable_protection(mbi.Protect);
        entry.guarded = (mbi.Protect & PAGE_GUARD) != 0;

        if (query.include_free || entry.state != MEM_FREE)
        {
            ++result.total_count;
            if (result.regions.size() < query.limit)
            {
                result.regions.push_back(entry);
            }
            else
            {
                result.truncated = true;
            }
        }

        const std::uint64_t next_address =
            entry.base_address + std::max<std::uint64_t>(entry.region_size, system_info.dwPageSize);
        if (next_address <= current_address)
        {
            break;
        }

        current_address = next_address;
    }

    return std::nullopt;
}

std::optional<DWORD> CoreRuntime::Impl::aob_scan(const AobScanQuery& query, AobScanResult& result) const
{
    const auto context = open_attached_process(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ);
    if (!context.attached)
    {
        return ERROR_INVALID_HANDLE;
    }

    if (context.handle == nullptr || context.handle == INVALID_HANDLE_VALUE)
    {
        return context.win32_error;
    }

    ScopedHandle process(context.handle);
    result.process_id = context.process_id;

    std::uint64_t start_address = 0;
    std::uint64_t end_address = 0;

    if (query.module_name)
    {
        const auto module = find_module_by_name(*query.module_name);
        if (!module)
        {
            return ERROR_NOT_FOUND;
        }

        start_address = module->base_address;
        end_address = module->base_address + module->size;
    }
    else if (query.start_address || query.end_address)
    {
        start_address = query.start_address.value_or(0);
        end_address = query.end_address.value_or(0);
    }

    MemoryMapQuery map_query;
    map_query.start_address = start_address;
    map_query.end_address = end_address;
    map_query.limit = std::numeric_limits<std::size_t>::max();
    map_query.include_free = false;

    MemoryMapResult map_result;
    if (const auto map_error = query_memory_map(map_query, map_result))
    {
        return map_error;
    }

    const std::size_t pattern_size = query.pattern.size();
    if (pattern_size == 0)
    {
        return ERROR_INVALID_PARAMETER;
    }

    for (const auto& region : map_result.regions)
    {
        if (region.state != MEM_COMMIT || !region.readable || region.guarded || region.region_size < pattern_size)
        {
            continue;
        }

        ++result.scanned_region_count;

        const std::uint64_t region_end = region.base_address + region.region_size;
        std::uint64_t cursor = region.base_address;
        std::vector<unsigned char> overlap;

        while (cursor < region_end)
        {
            const std::size_t chunk_size = static_cast<std::size_t>(
                std::min<std::uint64_t>(kAobScanChunkSize, region_end - cursor));
            std::vector<unsigned char> chunk(chunk_size);
            SIZE_T bytes_read = 0;
            const BOOL ok = ::ReadProcessMemory(
                process.get(),
                reinterpret_cast<LPCVOID>(static_cast<UINT_PTR>(cursor)),
                chunk.data(),
                chunk.size(),
                &bytes_read);
            if (ok == FALSE && bytes_read == 0)
            {
                break;
            }

            chunk.resize(static_cast<std::size_t>(bytes_read));
            if (!chunk.empty())
            {
                std::vector<unsigned char> buffer;
                if (!overlap.empty())
                {
                    buffer.reserve(overlap.size() + chunk.size());
                    buffer.insert(buffer.end(), overlap.begin(), overlap.end());
                    buffer.insert(buffer.end(), chunk.begin(), chunk.end());
                }
                else
                {
                    buffer = chunk;
                }

                const std::uint64_t buffer_base = cursor - overlap.size();
                if (buffer.size() >= pattern_size)
                {
                    for (std::size_t index = 0; index + pattern_size <= buffer.size(); ++index)
                    {
                        if (!aob_matches_at(buffer, index, query.pattern))
                        {
                            continue;
                        }

                        result.matches.push_back(buffer_base + index);
                        if (result.matches.size() >= query.max_results)
                        {
                            result.truncated = true;
                            return std::nullopt;
                        }
                    }
                }

                const std::size_t overlap_size = std::min<std::size_t>(
                    pattern_size > 0 ? pattern_size - 1 : 0,
                    buffer.size());
                overlap.assign(buffer.end() - overlap_size, buffer.end());
                result.scanned_byte_count += static_cast<std::uint64_t>(chunk.size());
            }

            if (bytes_read == 0)
            {
                break;
            }

            cursor += static_cast<std::uint64_t>(bytes_read);
        }
    }

    return std::nullopt;
}
}
