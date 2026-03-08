#include "core_runtime_internal.hpp"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <cstring>
#include <sstream>
#include <stdexcept>

namespace ce_mcp
{
ScopedHandle::ScopedHandle(HANDLE handle) noexcept : handle_(handle) {}

ScopedHandle::~ScopedHandle()
{
    reset();
}

ScopedHandle::ScopedHandle(ScopedHandle&& other) noexcept
    : handle_(std::exchange(other.handle_, nullptr))
{
}

ScopedHandle& ScopedHandle::operator=(ScopedHandle&& other) noexcept
{
    if (this != &other)
    {
        reset();
        handle_ = std::exchange(other.handle_, nullptr);
    }

    return *this;
}

HANDLE ScopedHandle::get() const noexcept
{
    return handle_;
}

bool ScopedHandle::valid() const noexcept
{
    return handle_ != nullptr && handle_ != INVALID_HANDLE_VALUE;
}

void ScopedHandle::reset(HANDLE handle) noexcept
{
    if (valid())
    {
        ::CloseHandle(handle_);
    }

    handle_ = handle;
}

std::optional<std::string> read_environment_variable(const char* name)
{
    const DWORD required_size = ::GetEnvironmentVariableA(name, nullptr, 0);
    if (required_size == 0)
    {
        return std::nullopt;
    }

    std::string value(required_size, '\0');
    const DWORD copied = ::GetEnvironmentVariableA(name, value.data(), required_size);
    if (copied == 0)
    {
        return std::nullopt;
    }

    value.resize(copied);
    return value;
}

std::optional<std::uint16_t> parse_port(const std::string& value)
{
    char* end = nullptr;
    const unsigned long parsed = std::strtoul(value.c_str(), &end, 10);
    if (end == value.c_str() || *end != '\0' || parsed == 0UL || parsed > 65535UL)
    {
        return std::nullopt;
    }

    return static_cast<std::uint16_t>(parsed);
}

std::optional<int> parse_positive_int(const std::string& value)
{
    char* end = nullptr;
    const long parsed = std::strtol(value.c_str(), &end, 10);
    if (end == value.c_str() || *end != '\0' || parsed <= 0L)
    {
        return std::nullopt;
    }

    return static_cast<int>(parsed);
}

std::string trim_ascii(std::string value)
{
    const auto not_space = [](unsigned char ch)
    {
        return std::isspace(ch) == 0;
    };

    const auto begin = std::find_if(value.begin(), value.end(),
                                    [&](char ch)
                                    {
                                        return not_space(static_cast<unsigned char>(ch));
                                    });
    const auto end = std::find_if(value.rbegin(), value.rend(),
                                  [&](char ch)
                                  {
                                      return not_space(static_cast<unsigned char>(ch));
                                  })
                         .base();

    if (begin >= end)
    {
        return {};
    }

    return std::string(begin, end);
}

std::optional<std::filesystem::path> runtime_directory_from_module(const void* address)
{
    HMODULE module = nullptr;
    if (::GetModuleHandleExW(
            GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            static_cast<LPCWSTR>(address),
            &module) == FALSE)
    {
        return std::nullopt;
    }

    std::wstring path(MAX_PATH, L'\0');
    DWORD copied = 0;
    while ((copied = ::GetModuleFileNameW(module, path.data(), static_cast<DWORD>(path.size()))) >=
           path.size())
    {
        path.resize(path.size() * 2);
    }

    if (copied == 0)
    {
        return std::nullopt;
    }

    path.resize(copied);
    return std::filesystem::path(path).parent_path().parent_path();
}

void runtime_config_marker()
{
}

bool try_read_opened_process_id(PExportedFunctions exported, DWORD& process_id)
{
    if (exported == nullptr)
    {
        return false;
    }

    __try
    {
        if (exported->OpenedProcessID == nullptr)
        {
            return false;
        }

        process_id = *exported->OpenedProcessID;
        return true;
    }
    __except (EXCEPTION_EXECUTE_HANDLER)
    {
        return false;
    }
}

bool try_read_opened_process_handle(PExportedFunctions exported, HANDLE& process_handle)
{
    if (exported == nullptr)
    {
        return false;
    }

    __try
    {
        if (exported->OpenedProcessHandle == nullptr)
        {
            return false;
        }

        process_handle = *exported->OpenedProcessHandle;
        return true;
    }
    __except (EXCEPTION_EXECUTE_HANDLER)
    {
        return false;
    }
}

bool try_force_detached_process_state(PExportedFunctions exported)
{
    if (exported == nullptr)
    {
        return false;
    }

    __try
    {
        if (exported->OpenedProcessHandle != nullptr)
        {
            HANDLE current_handle = *exported->OpenedProcessHandle;
            if (current_handle != nullptr && current_handle != INVALID_HANDLE_VALUE)
            {
                ::CloseHandle(current_handle);
            }

            *exported->OpenedProcessHandle = nullptr;
        }

        if (exported->OpenedProcessID != nullptr)
        {
            *exported->OpenedProcessID = 0;
        }

        return true;
    }
    __except (EXCEPTION_EXECUTE_HANDLER)
    {
        return false;
    }
}

std::string wide_to_utf8(std::wstring_view value)
{
    if (value.empty())
    {
        return {};
    }

    const int required = ::WideCharToMultiByte(CP_UTF8, 0, value.data(),
                                               static_cast<int>(value.size()), nullptr, 0, nullptr,
                                               nullptr);
    if (required <= 0)
    {
        return {};
    }

    std::string output(static_cast<std::size_t>(required), '\0');
    const int converted = ::WideCharToMultiByte(CP_UTF8, 0, value.data(),
                                                static_cast<int>(value.size()), output.data(),
                                                required, nullptr, nullptr);
    output.resize(converted > 0 ? static_cast<std::size_t>(converted) : 0U);
    return output;
}

std::string escape_json_string(std::string_view input)
{
    std::string output;
    output.reserve(input.size());

    for (const char ch : input)
    {
        switch (ch)
        {
        case '\\':
            output += "\\\\";
            break;
        case '"':
            output += "\\\"";
            break;
        case '\r':
            output += "\\r";
            break;
        case '\n':
            output += "\\n";
            break;
        case '\t':
            output += "\\t";
            break;
        default:
            output.push_back(ch);
            break;
        }
    }

    return output;
}

std::optional<std::string> extract_string_field(std::string_view json, std::string_view field)
{
    const std::string needle = "\"" + std::string(field) + "\"";
    const std::size_t key_pos = json.find(needle);
    if (key_pos == std::string_view::npos)
    {
        return std::nullopt;
    }

    const std::size_t colon_pos = json.find(':', key_pos + needle.size());
    if (colon_pos == std::string_view::npos)
    {
        return std::nullopt;
    }

    std::size_t value_pos = colon_pos + 1;
    while (value_pos < json.size() && std::isspace(static_cast<unsigned char>(json[value_pos])) != 0)
    {
        ++value_pos;
    }

    if (value_pos >= json.size() || json[value_pos] != '"')
    {
        return std::nullopt;
    }

    ++value_pos;
    std::string value;
    bool escaped = false;

    for (std::size_t index = value_pos; index < json.size(); ++index)
    {
        const char ch = json[index];
        if (escaped)
        {
            switch (ch)
            {
            case '"':
            case '\\':
            case '/':
                value.push_back(ch);
                break;
            case 'n':
                value.push_back('\n');
                break;
            case 'r':
                value.push_back('\r');
                break;
            case 't':
                value.push_back('\t');
                break;
            default:
                value.push_back(ch);
                break;
            }

            escaped = false;
            continue;
        }

        if (ch == '\\')
        {
            escaped = true;
            continue;
        }

        if (ch == '"')
        {
            return value;
        }

        value.push_back(ch);
    }

    return std::nullopt;
}

std::optional<std::string> extract_simple_field(std::string_view json, std::string_view field)
{
    if (const auto as_string = extract_string_field(json, field))
    {
        return as_string;
    }

    const std::string needle = "\"" + std::string(field) + "\"";
    const std::size_t key_pos = json.find(needle);
    if (key_pos == std::string_view::npos)
    {
        return std::nullopt;
    }

    const std::size_t colon_pos = json.find(':', key_pos + needle.size());
    if (colon_pos == std::string_view::npos)
    {
        return std::nullopt;
    }

    std::size_t value_pos = colon_pos + 1;
    while (value_pos < json.size() && std::isspace(static_cast<unsigned char>(json[value_pos])) != 0)
    {
        ++value_pos;
    }

    std::size_t end = value_pos;
    while (end < json.size() && json[end] != ',' && json[end] != '}' &&
           std::isspace(static_cast<unsigned char>(json[end])) == 0)
    {
        ++end;
    }

    if (end <= value_pos)
    {
        return std::nullopt;
    }

    return std::string(json.substr(value_pos, end - value_pos));
}

std::optional<std::uint64_t> parse_unsigned_integer(std::string_view text)
{
    std::string value = trim_ascii(std::string(text));
    if (value.empty())
    {
        return std::nullopt;
    }

    char* end = nullptr;
    const unsigned long long parsed = std::strtoull(value.c_str(), &end, 0);
    if (end == value.c_str() || *end != '\0')
    {
        return std::nullopt;
    }

    return static_cast<std::uint64_t>(parsed);
}

int hex_digit_value(char ch)
{
    if (ch >= '0' && ch <= '9')
    {
        return ch - '0';
    }

    if (ch >= 'a' && ch <= 'f')
    {
        return 10 + (ch - 'a');
    }

    if (ch >= 'A' && ch <= 'F')
    {
        return 10 + (ch - 'A');
    }

    return -1;
}

std::optional<std::vector<unsigned char>> parse_hex_bytes(std::string_view text)
{
    std::string filtered;
    filtered.reserve(text.size());

    for (const char ch : text)
    {
        if (std::isspace(static_cast<unsigned char>(ch)) != 0 || ch == ':' || ch == '-' || ch == ',')
        {
            continue;
        }

        filtered.push_back(ch);
    }

    if (filtered.rfind("0x", 0) == 0 || filtered.rfind("0X", 0) == 0)
    {
        filtered.erase(0, 2);
    }

    if (filtered.empty() || (filtered.size() % 2) != 0)
    {
        return std::nullopt;
    }

    std::vector<unsigned char> bytes;
    bytes.reserve(filtered.size() / 2);
    for (std::size_t index = 0; index < filtered.size(); index += 2)
    {
        const int high = hex_digit_value(filtered[index]);
        const int low = hex_digit_value(filtered[index + 1]);
        if (high < 0 || low < 0)
        {
            return std::nullopt;
        }

        bytes.push_back(static_cast<unsigned char>((high << 4) | low));
    }

    return bytes;
}

std::string bytes_to_hex_string(const std::vector<unsigned char>& bytes)
{
    static constexpr char kHexDigits[] = "0123456789ABCDEF";

    std::string output;
    output.reserve(bytes.size() * 2);
    for (const unsigned char byte : bytes)
    {
        output.push_back(kHexDigits[(byte >> 4) & 0x0F]);
        output.push_back(kHexDigits[byte & 0x0F]);
    }

    return output;
}

std::string make_json_string_array(const std::vector<std::string>& values)
{
    std::string output = "[";
    for (std::size_t index = 0; index < values.size(); ++index)
    {
        if (index != 0)
        {
            output += ",";
        }

        output += "\"" + escape_json_string(values[index]) + "\"";
    }

    output += "]";
    return output;
}

std::string memory_state_name(DWORD state)
{
    switch (state)
    {
    case MEM_COMMIT:
        return "MEM_COMMIT";
    case MEM_FREE:
        return "MEM_FREE";
    case MEM_RESERVE:
        return "MEM_RESERVE";
    default:
        return "UNKNOWN";
    }
}

std::string memory_type_name(DWORD type)
{
    switch (type)
    {
    case MEM_IMAGE:
        return "MEM_IMAGE";
    case MEM_MAPPED:
        return "MEM_MAPPED";
    case MEM_PRIVATE:
        return "MEM_PRIVATE";
    case 0:
        return "NONE";
    default:
        return "UNKNOWN";
    }
}

std::string memory_protect_name(DWORD protect)
{
    const DWORD base = protect & 0xFFU;
    std::string name;
    switch (base)
    {
    case PAGE_EXECUTE:
        name = "PAGE_EXECUTE";
        break;
    case PAGE_EXECUTE_READ:
        name = "PAGE_EXECUTE_READ";
        break;
    case PAGE_EXECUTE_READWRITE:
        name = "PAGE_EXECUTE_READWRITE";
        break;
    case PAGE_EXECUTE_WRITECOPY:
        name = "PAGE_EXECUTE_WRITECOPY";
        break;
    case PAGE_NOACCESS:
        name = "PAGE_NOACCESS";
        break;
    case PAGE_READONLY:
        name = "PAGE_READONLY";
        break;
    case PAGE_READWRITE:
        name = "PAGE_READWRITE";
        break;
    case PAGE_WRITECOPY:
        name = "PAGE_WRITECOPY";
        break;
    case 0:
        name = "NONE";
        break;
    default:
        name = "UNKNOWN";
        break;
    }

    if ((protect & PAGE_GUARD) != 0)
    {
        name += "|PAGE_GUARD";
    }
    if ((protect & PAGE_NOCACHE) != 0)
    {
        name += "|PAGE_NOCACHE";
    }
    if ((protect & PAGE_WRITECOMBINE) != 0)
    {
        name += "|PAGE_WRITECOMBINE";
    }

    return name;
}

bool parse_bool(std::string_view text, bool& value)
{
    std::string normalized = trim_ascii(std::string(text));
    std::transform(normalized.begin(), normalized.end(), normalized.begin(),
                   [](unsigned char ch)
                   {
                       return static_cast<char>(std::tolower(ch));
                   });

    if (normalized == "true" || normalized == "1")
    {
        value = true;
        return true;
    }

    if (normalized == "false" || normalized == "0")
    {
        value = false;
        return true;
    }

    return false;
}

bool equals_case_insensitive(std::string_view left, std::string_view right)
{
    return left.size() == right.size() &&
           std::equal(left.begin(), left.end(), right.begin(),
                      [](char lhs, char rhs)
                      {
                          return std::tolower(static_cast<unsigned char>(lhs)) ==
                                 std::tolower(static_cast<unsigned char>(rhs));
                      });
}

bool is_readable_protection(DWORD protect)
{
    if ((protect & PAGE_GUARD) != 0)
    {
        return false;
    }

    switch (protect & 0xFFU)
    {
    case PAGE_READONLY:
    case PAGE_READWRITE:
    case PAGE_WRITECOPY:
    case PAGE_EXECUTE_READ:
    case PAGE_EXECUTE_READWRITE:
    case PAGE_EXECUTE_WRITECOPY:
        return true;
    default:
        return false;
    }
}

bool is_writable_protection(DWORD protect)
{
    switch (protect & 0xFFU)
    {
    case PAGE_READWRITE:
    case PAGE_WRITECOPY:
    case PAGE_EXECUTE_READWRITE:
    case PAGE_EXECUTE_WRITECOPY:
        return true;
    default:
        return false;
    }
}

bool is_executable_protection(DWORD protect)
{
    switch (protect & 0xFFU)
    {
    case PAGE_EXECUTE:
    case PAGE_EXECUTE_READ:
    case PAGE_EXECUTE_READWRITE:
    case PAGE_EXECUTE_WRITECOPY:
        return true;
    default:
        return false;
    }
}

std::optional<std::vector<AobPatternByte>> parse_aob_pattern(std::string_view text)
{
    std::istringstream stream{std::string(text)};
    std::string token;
    std::vector<AobPatternByte> pattern;

    while (stream >> token)
    {
        if (token == "?" || token == "??")
        {
            pattern.push_back({true, 0});
            continue;
        }

        if (token.size() != 2)
        {
            return std::nullopt;
        }

        const int high = hex_digit_value(token[0]);
        const int low = hex_digit_value(token[1]);
        if (high < 0 || low < 0)
        {
            return std::nullopt;
        }

        pattern.push_back({false, static_cast<unsigned char>((high << 4) | low)});
    }

    if (pattern.empty())
    {
        return std::nullopt;
    }

    return pattern;
}

bool aob_matches_at(const std::vector<unsigned char>& buffer,
                    std::size_t start_index,
                    const std::vector<AobPatternByte>& pattern)
{
    for (std::size_t index = 0; index < pattern.size(); ++index)
    {
        if (pattern[index].wildcard)
        {
            continue;
        }

        if (buffer[start_index + index] != pattern[index].value)
        {
            return false;
        }
    }

    return true;
}
}
