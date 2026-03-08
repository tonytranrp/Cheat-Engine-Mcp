#include "core_runtime_internal.hpp"

#include <libhat/scanner.hpp>

#include <algorithm>
#include <cctype>
#include <cstring>
#include <limits>
#include <sstream>
#include <thread>

namespace ce_mcp
{
namespace
{
constexpr std::size_t kRemotePeHeaderReadSize = 16 * 1024;
constexpr std::uint8_t kAobAlignmentX1 = 1;
constexpr std::uint8_t kAobAlignmentX16 = 16;
constexpr std::uint64_t kAobHintNone = 0;
constexpr std::uint64_t kAobHintX86_64 = 1ull << 0;
constexpr std::uint64_t kAobHintPair0 = 1ull << 1;

std::string trim_trailing_nuls(std::string value)
{
    while (!value.empty() && value.back() == '\0')
    {
        value.pop_back();
    }
    return value;
}

std::string normalize_section_name(std::string_view value)
{
    std::string normalized;
    normalized.reserve(value.size());
    for (const char ch : value)
    {
        if (ch != '\0')
        {
            normalized.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(ch))));
        }
    }

    if (!normalized.empty() && normalized.front() == '.')
    {
        normalized.erase(normalized.begin());
    }
    return normalized;
}

std::optional<std::uint8_t> parse_aob_scan_alignment(std::string_view text)
{
    const std::string trimmed = trim_ascii(std::string(text));
    if (trimmed.empty())
    {
        return std::nullopt;
    }

    if (equals_case_insensitive(trimmed, "1") || equals_case_insensitive(trimmed, "x1"))
    {
        return kAobAlignmentX1;
    }
    if (equals_case_insensitive(trimmed, "16") || equals_case_insensitive(trimmed, "x16"))
    {
        return kAobAlignmentX16;
    }
    return std::nullopt;
}

std::optional<std::uint64_t> parse_aob_scan_hints(std::string_view text)
{
    std::string normalized = trim_ascii(std::string(text));
    std::transform(normalized.begin(), normalized.end(), normalized.begin(),
                   [](unsigned char ch)
                   {
                       if (ch == ',' || ch == '+' || ch == ';')
                       {
                           return '|';
                       }
                       return static_cast<char>(std::tolower(ch));
                   });

    if (normalized.empty() || normalized == "none")
    {
        return kAobHintNone;
    }

    std::uint64_t hints = kAobHintNone;
    std::istringstream stream(normalized);
    std::string token;
    while (std::getline(stream, token, '|'))
    {
        token = trim_ascii(token);
        if (token.empty() || token == "none")
        {
            continue;
        }
        if (token == "x86_64" || token == "x86-64" || token == "x64")
        {
            hints |= kAobHintX86_64;
            continue;
        }
        if (token == "pair0")
        {
            hints |= kAobHintPair0;
            continue;
        }
        return std::nullopt;
    }
    return hints;
}

hat::scan_alignment to_libhat_scan_alignment(const std::uint8_t alignment)
{
    return alignment == kAobAlignmentX16 ? hat::scan_alignment::X16 : hat::scan_alignment::X1;
}

hat::scan_hint to_libhat_scan_hint(const std::uint64_t hints)
{
    hat::scan_hint result = hat::scan_hint::none;
    if ((hints & kAobHintX86_64) != 0)
    {
        result |= hat::scan_hint::x86_64;
    }
    if ((hints & kAobHintPair0) != 0)
    {
        result |= hat::scan_hint::pair0;
    }
    return result;
}

std::string format_aob_scan_alignment(const std::uint8_t alignment)
{
    return alignment == kAobAlignmentX16 ? "x16" : "x1";
}

std::string format_aob_scan_hints(const std::uint64_t hints)
{
    if (hints == kAobHintNone)
    {
        return "none";
    }

    std::string result;
    if ((hints & kAobHintX86_64) != 0)
    {
        result += "x86_64";
    }
    if ((hints & kAobHintPair0) != 0)
    {
        if (!result.empty())
        {
            result += "|";
        }
        result += "pair0";
    }
    return result;
}

std::uint64_t parse_request_timeout_ms(std::string_view line)
{
    const auto timeout_text = extract_simple_field(line, "__timeout_ms");
    if (!timeout_text)
    {
        return 0;
    }

    const auto timeout_ms = parse_unsigned_integer(*timeout_text);
    if (!timeout_ms)
    {
        return 0;
    }

    return *timeout_ms;
}

std::optional<std::chrono::steady_clock::time_point> make_deadline(const std::uint64_t timeout_ms)
{
    if (timeout_ms == 0)
    {
        return std::nullopt;
    }

    return std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
}

bool deadline_reached(const std::optional<std::chrono::steady_clock::time_point>& deadline)
{
    return deadline.has_value() && std::chrono::steady_clock::now() >= *deadline;
}

void cooperative_yield()
{
    ::SwitchToThread();
    std::this_thread::yield();
}

std::optional<std::pair<std::uint64_t, std::uint64_t>> resolve_remote_module_section(HANDLE process,
                                                                                      const std::uint64_t module_base,
                                                                                      const std::uint64_t module_size,
                                                                                      std::string_view section_name)
{
    std::vector<unsigned char> buffer(static_cast<std::size_t>(
        std::min<std::uint64_t>(module_size == 0 ? kRemotePeHeaderReadSize : module_size, kRemotePeHeaderReadSize)));
    SIZE_T bytes_read = 0;
    const BOOL ok = ::ReadProcessMemory(
        process,
        reinterpret_cast<LPCVOID>(static_cast<UINT_PTR>(module_base)),
        buffer.data(),
        buffer.size(),
        &bytes_read);
    if ((ok == FALSE && bytes_read == 0) || bytes_read < sizeof(IMAGE_DOS_HEADER))
    {
        return std::nullopt;
    }

    buffer.resize(static_cast<std::size_t>(bytes_read));
    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(buffer.data());
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew < 0)
    {
        return std::nullopt;
    }

    const std::size_t nt_offset = static_cast<std::size_t>(dos->e_lfanew);
    if (nt_offset + sizeof(DWORD) + sizeof(IMAGE_FILE_HEADER) > buffer.size())
    {
        return std::nullopt;
    }

    const auto signature = *reinterpret_cast<const DWORD*>(buffer.data() + nt_offset);
    if (signature != IMAGE_NT_SIGNATURE)
    {
        return std::nullopt;
    }

    const auto* file_header = reinterpret_cast<const IMAGE_FILE_HEADER*>(buffer.data() + nt_offset + sizeof(DWORD));
    const std::size_t section_offset =
        nt_offset + sizeof(DWORD) + sizeof(IMAGE_FILE_HEADER) + static_cast<std::size_t>(file_header->SizeOfOptionalHeader);
    const std::size_t section_table_size =
        static_cast<std::size_t>(file_header->NumberOfSections) * sizeof(IMAGE_SECTION_HEADER);
    if (section_offset + section_table_size > buffer.size())
    {
        return std::nullopt;
    }

    const std::string requested = normalize_section_name(section_name);
    const auto* sections = reinterpret_cast<const IMAGE_SECTION_HEADER*>(buffer.data() + section_offset);
    for (std::size_t index = 0; index < file_header->NumberOfSections; ++index)
    {
        const auto& section = sections[index];
        const std::string current = normalize_section_name(
            std::string_view(reinterpret_cast<const char*>(section.Name), sizeof(section.Name)));
        if (current != requested)
        {
            continue;
        }

        const std::uint64_t start = module_base + static_cast<std::uint64_t>(section.VirtualAddress);
        std::uint64_t size = static_cast<std::uint64_t>(section.Misc.VirtualSize);
        if (size == 0)
        {
            size = static_cast<std::uint64_t>(section.SizeOfRawData);
        }
        if (module_size != 0)
        {
            const std::uint64_t module_end = module_base + module_size;
            const std::uint64_t max_size = module_end > start ? module_end - start : 0;
            size = std::min(size, max_size);
        }
        if (size == 0)
        {
            return std::nullopt;
        }
        return std::make_pair(start, start + size);
    }

    return std::nullopt;
}
}

std::string CoreRuntime::Impl::make_query_memory_response(std::string_view request_id, std::string_view line) const
{
    const auto address_text = extract_simple_field(line, "address");
    if (!address_text)
    {
        return make_error_response(request_id, "missing_address");
    }

    const auto address = parse_or_resolve_address(*address_text);
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
    query.timeout_ms = parse_request_timeout_ms(line);

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
        const auto start_address = parse_or_resolve_address(*start_text);
        if (!start_address)
        {
            return make_error_response(request_id, "invalid_start_address");
        }

        query.start_address = *start_address;
    }

    if (const auto end_text = extract_simple_field(line, "end_address"))
    {
        const auto end_address = parse_or_resolve_address(*end_text);
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
           << ",\"timed_out\":" << (result.timed_out ? "true" : "false")
           << ",\"count_complete\":" << ((result.truncated || result.timed_out) ? "false" : "true")
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
    query.timeout_ms = parse_request_timeout_ms(line);
    const auto parsed_signature = hat::parse_signature(*pattern_text);
    if (!parsed_signature.has_value() || parsed_signature.value().empty())
    {
        return make_error_response(request_id, "invalid_pattern");
    }

    query.pattern_text = *pattern_text;

    if (const auto module_name = extract_string_field(line, "module_name"))
    {
        query.module_name = *module_name;
    }

    if (const auto section_name = extract_simple_field(line, "section_name"))
    {
        const std::string normalized = trim_ascii(*section_name);
        if (normalized.empty())
        {
            return make_error_response(request_id, "invalid_section_name");
        }

        query.section_name = normalized;
    }

    if (const auto start_text = extract_simple_field(line, "start_address"))
    {
        const auto start_address = parse_or_resolve_address(*start_text);
        if (!start_address)
        {
            return make_error_response(request_id, "invalid_start_address");
        }

        query.start_address = *start_address;
    }

    if (const auto end_text = extract_simple_field(line, "end_address"))
    {
        const auto end_address = parse_or_resolve_address(*end_text);
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

    if (query.module_name && (query.start_address || query.end_address))
    {
        return make_error_response(request_id, "invalid_scan_scope");
    }

    if (query.section_name && !query.module_name)
    {
        return make_error_response(request_id, "section_requires_module");
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

    if (const auto alignment_text = extract_simple_field(line, "scan_alignment"))
    {
        const auto parsed_alignment = parse_aob_scan_alignment(*alignment_text);
        if (!parsed_alignment)
        {
            return make_error_response(request_id, "invalid_scan_alignment");
        }

        query.scan_alignment = *parsed_alignment;
    }

    auto hint_text = extract_simple_field(line, "scan_hint");
    if (!hint_text)
    {
        hint_text = extract_simple_field(line, "scan_hints");
    }
    if (hint_text)
    {
        const auto parsed_hints = parse_aob_scan_hints(*hint_text);
        if (!parsed_hints)
        {
            return make_error_response(request_id, "invalid_scan_hint");
        }

        query.scan_hints = *parsed_hints;
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
    if (query.section_name)
    {
        stream << ",\"section_name\":\"" << escape_json_string(*query.section_name) << "\"";
    }
    if (query.start_address)
    {
        stream << ",\"start_address\":" << *query.start_address;
    }
    if (query.end_address)
    {
        stream << ",\"end_address\":" << *query.end_address;
    }
    stream << ",\"scan_alignment\":\"" << format_aob_scan_alignment(query.scan_alignment) << "\""
           << ",\"scan_hint\":\"" << format_aob_scan_hints(query.scan_hints) << "\"";
    stream << ",\"scanned_region_count\":" << result.scanned_region_count
           << ",\"scanned_byte_count\":" << result.scanned_byte_count
           << ",\"returned_count\":" << result.matches.size()
           << ",\"truncated\":" << (result.truncated ? "true" : "false")
           << ",\"timed_out\":" << (result.timed_out ? "true" : "false")
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

    const auto address = parse_or_resolve_address(*address_text);
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

    const auto address = parse_or_resolve_address(*address_text);
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
    const auto deadline = make_deadline(query.timeout_ms);

    result.process_id = context.process_id;

    while (current_address < end_address)
    {
        if (deadline_reached(deadline))
        {
            result.truncated = true;
            result.timed_out = true;
            break;
        }

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
                break;
            }
        }

        const std::uint64_t next_address =
            entry.base_address + std::max<std::uint64_t>(entry.region_size, system_info.dwPageSize);
        if (next_address <= current_address)
        {
            break;
        }

        current_address = next_address;
        cooperative_yield();
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
    const auto deadline = make_deadline(query.timeout_ms);

    const auto parsed_signature = hat::parse_signature(query.pattern_text);
    if (!parsed_signature.has_value() || parsed_signature.value().empty())
    {
        return ERROR_INVALID_PARAMETER;
    }

    const auto& signature = parsed_signature.value();
    const std::size_t pattern_size = signature.size();
    if (pattern_size == 0)
    {
        return ERROR_INVALID_PARAMETER;
    }

    std::uint64_t start_address = 0;
    std::uint64_t end_address = 0;

    if (query.section_name && !query.module_name)
    {
        return ERROR_INVALID_PARAMETER;
    }

    if (query.module_name && (query.start_address || query.end_address))
    {
        return ERROR_INVALID_PARAMETER;
    }

    if (query.module_name)
    {
        const auto module = find_module_by_name(*query.module_name);
        if (!module)
        {
            return ERROR_NOT_FOUND;
        }

        if (query.section_name)
        {
            const auto bounds = resolve_remote_module_section(
                process.get(),
                module->base_address,
                module->size,
                *query.section_name);
            if (!bounds)
            {
                return ERROR_NOT_FOUND;
            }

            start_address = bounds->first;
            end_address = bounds->second;
        }
        else
        {
            start_address = module->base_address;
            end_address = module->base_address + module->size;
        }
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

    for (const auto& region : map_result.regions)
    {
        if (deadline_reached(deadline))
        {
            result.truncated = true;
            result.timed_out = true;
            break;
        }

        if (region.state != MEM_COMMIT || !region.readable || region.guarded || region.region_size < pattern_size)
        {
            continue;
        }

        const std::uint64_t region_scan_start = std::max(region.base_address, start_address);
        const std::uint64_t region_scan_end =
            end_address == 0 ? region.base_address + region.region_size
                             : std::min(region.base_address + region.region_size, end_address);
        if (region_scan_end <= region_scan_start || region_scan_end - region_scan_start < pattern_size)
        {
            continue;
        }

        ++result.scanned_region_count;

        const std::uint64_t region_end = region_scan_end;
        std::uint64_t cursor = region_scan_start;
        std::vector<unsigned char> overlap;

        while (cursor < region_end)
        {
            if (deadline_reached(deadline))
            {
                result.truncated = true;
                result.timed_out = true;
                return std::nullopt;
            }

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
                const std::uint64_t buffer_base = cursor - static_cast<std::uint64_t>(overlap.size());
                const std::size_t total_size = overlap.size() + chunk.size();
                std::vector<unsigned char> scan_storage(total_size + (query.scan_alignment == kAobAlignmentX16 ? 15u : 0u));
                unsigned char* scan_begin = scan_storage.data();

                if (query.scan_alignment == kAobAlignmentX16)
                {
                    const std::uintptr_t base = reinterpret_cast<std::uintptr_t>(scan_begin);
                    const std::uintptr_t desired_mod = static_cast<std::uintptr_t>(buffer_base & 0x0Fu);
                    const std::uintptr_t offset = (desired_mod + 16u - (base & 0x0Fu)) & 0x0Fu;
                    scan_begin += offset;
                }

                if (!overlap.empty())
                {
                    std::copy(overlap.begin(), overlap.end(), scan_begin);
                }

                std::copy(chunk.begin(), chunk.end(), scan_begin + overlap.size());
                if (total_size >= pattern_size)
                {
                    const auto* scan_bytes_begin = reinterpret_cast<const std::byte*>(scan_begin);
                    const auto* scan_bytes_end = scan_bytes_begin + total_size;
                    const std::size_t remaining_results = query.max_results - result.matches.size();
                    std::vector<hat::const_scan_result> local_matches(remaining_results);
                    const auto [scan_end, used_end] = hat::find_all_pattern(
                        scan_bytes_begin,
                        scan_bytes_end,
                        local_matches.begin(),
                        local_matches.end(),
                        signature,
                        to_libhat_scan_alignment(query.scan_alignment),
                        to_libhat_scan_hint(query.scan_hints));
                    const std::size_t match_count = static_cast<std::size_t>(std::distance(local_matches.begin(), used_end));

                    for (std::size_t index = 0; index < match_count; ++index)
                    {
                        const auto match = local_matches[index];
                        if (!match.has_result())
                        {
                            continue;
                        }
                        const auto match_offset = static_cast<std::size_t>(match.get() - scan_bytes_begin);
                        result.matches.push_back(buffer_base + static_cast<std::uint64_t>(match_offset));
                        if (result.matches.size() >= query.max_results)
                        {
                            result.truncated = true;
                            return std::nullopt;
                        }
                    }

                    if (match_count == remaining_results && scan_end != scan_bytes_end)
                    {
                        result.truncated = true;
                        return std::nullopt;
                    }
                }

                const std::size_t overlap_size = std::min<std::size_t>(
                    pattern_size > 0 ? pattern_size - 1 : 0,
                    total_size);
                overlap.assign(scan_begin + total_size - overlap_size, scan_begin + total_size);
                result.scanned_byte_count += static_cast<std::uint64_t>(chunk.size());
            }

            if (bytes_read == 0)
            {
                break;
            }

            cursor += static_cast<std::uint64_t>(bytes_read);
            cooperative_yield();
        }
    }

    return std::nullopt;
}
}
