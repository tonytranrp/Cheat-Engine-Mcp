#pragma once

#include <windows.h>
#include <tlhelp32.h>

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "cepluginsdk.h"
#include "config.hpp"
#include "core_api.h"
#include "core_runtime.hpp"
#include "mcp_client.hpp"

namespace ce_mcp
{
inline constexpr std::size_t kDefaultProcessListLimit = 64;
inline constexpr std::size_t kMaxProcessListLimit = 512;
inline constexpr std::size_t kDefaultModuleListLimit = 256;
inline constexpr std::size_t kMaxModuleListLimit = 2048;
inline constexpr std::size_t kDefaultMemoryMapLimit = 256;
inline constexpr std::size_t kMaxMemoryMapLimit = 8192;
inline constexpr std::size_t kDefaultAobResultLimit = 32;
inline constexpr std::size_t kMaxAobResultLimit = 4096;
inline constexpr std::size_t kAobScanChunkSize = 1024 * 1024;
inline constexpr std::size_t kMaxMemoryTransferSize = 1024 * 1024;

struct AttachedProcessInfo
{
    bool attached = false;
    DWORD process_id = 0;
    std::string process_name;
    std::string image_path;
};

struct ProcessEntryInfo
{
    DWORD process_id = 0;
    DWORD parent_process_id = 0;
    bool attached = false;
    std::string process_name;
};

struct ProcessListResult
{
    std::vector<ProcessEntryInfo> processes;
    std::size_t total_count = 0;
    bool truncated = false;
};

struct ModuleEntryInfo
{
    std::uint64_t base_address = 0;
    std::uint64_t size = 0;
    std::string module_name;
    std::string module_path;
};

struct ModuleListResult
{
    DWORD process_id = 0;
    std::vector<ModuleEntryInfo> modules;
    std::size_t total_count = 0;
    bool truncated = false;
};

struct MemoryRegionInfo
{
    DWORD process_id = 0;
    std::uint64_t address = 0;
    std::uint64_t base_address = 0;
    std::uint64_t allocation_base = 0;
    std::uint64_t region_size = 0;
    DWORD state = 0;
    DWORD protect = 0;
    DWORD allocation_protect = 0;
    DWORD type = 0;
    bool readable = false;
    bool writable = false;
    bool executable = false;
    bool guarded = false;
};

struct MemoryMapQuery
{
    std::uint64_t start_address = 0;
    std::uint64_t end_address = 0;
    std::size_t limit = kDefaultMemoryMapLimit;
    bool include_free = false;
};

struct MemoryMapResult
{
    DWORD process_id = 0;
    std::vector<MemoryRegionInfo> regions;
    std::size_t total_count = 0;
    bool truncated = false;
};

struct SymbolResolutionResult
{
    std::string symbol;
    std::uint64_t address = 0;
    std::string resolved_via;
};

struct AobPatternByte
{
    bool wildcard = false;
    unsigned char value = 0;
};

struct AobScanQuery
{
    std::vector<AobPatternByte> pattern;
    std::optional<std::string> module_name;
    std::optional<std::uint64_t> start_address;
    std::optional<std::uint64_t> end_address;
    std::size_t max_results = kDefaultAobResultLimit;
};

struct AobScanResult
{
    DWORD process_id = 0;
    std::size_t scanned_region_count = 0;
    std::uint64_t scanned_byte_count = 0;
    bool truncated = false;
    std::vector<std::uint64_t> matches;
};

struct MemoryAccessContext
{
    bool attached = false;
    DWORD process_id = 0;
    HANDLE handle = nullptr;
    DWORD win32_error = ERROR_SUCCESS;
};

class ScopedHandle
{
public:
    ScopedHandle() = default;
    explicit ScopedHandle(HANDLE handle) noexcept;
    ~ScopedHandle();

    ScopedHandle(const ScopedHandle&) = delete;
    ScopedHandle& operator=(const ScopedHandle&) = delete;

    ScopedHandle(ScopedHandle&& other) noexcept;
    ScopedHandle& operator=(ScopedHandle&& other) noexcept;

    [[nodiscard]] HANDLE get() const noexcept;
    [[nodiscard]] bool valid() const noexcept;
    void reset(HANDLE handle = nullptr) noexcept;

private:
    HANDLE handle_ = nullptr;
};

std::optional<std::string> read_environment_variable(const char* name);
std::optional<std::uint16_t> parse_port(const std::string& value);
std::optional<int> parse_positive_int(const std::string& value);
std::string trim_ascii(std::string value);
std::optional<std::filesystem::path> runtime_directory_from_module(const void* address);
void runtime_config_marker();
bool try_read_opened_process_id(PExportedFunctions exported, DWORD& process_id);
bool try_read_opened_process_handle(PExportedFunctions exported, HANDLE& process_handle);
bool try_force_detached_process_state(PExportedFunctions exported);
std::string wide_to_utf8(std::wstring_view value);
std::string escape_json_string(std::string_view input);
std::optional<std::string> extract_string_field(std::string_view json, std::string_view field);
std::optional<std::string> extract_simple_field(std::string_view json, std::string_view field);
std::optional<std::uint64_t> parse_unsigned_integer(std::string_view text);
int hex_digit_value(char ch);
std::optional<std::vector<unsigned char>> parse_hex_bytes(std::string_view text);
std::string bytes_to_hex_string(const std::vector<unsigned char>& bytes);
std::string make_json_string_array(const std::vector<std::string>& values);
std::string memory_state_name(DWORD state);
std::string memory_type_name(DWORD type);
std::string memory_protect_name(DWORD protect);
bool parse_bool(std::string_view text, bool& value);
bool equals_case_insensitive(std::string_view left, std::string_view right);
bool is_readable_protection(DWORD protect);
bool is_writable_protection(DWORD protect);
bool is_executable_protection(DWORD protect);
std::optional<std::vector<AobPatternByte>> parse_aob_pattern(std::string_view text);
bool aob_matches_at(const std::vector<unsigned char>& buffer,
                    std::size_t start_index,
                    const std::vector<AobPatternByte>& pattern);

struct CoreRuntime::Impl
{
public:
    explicit Impl(CeMcpHostContext host);

    void start();
    void stop() noexcept;

    mcp::Config make_client_config() const;
    void apply_runtime_config_file(mcp::Config& config) const;
    void log(std::string_view message) const;
    mcp::ToolNames tool_names() const;
    std::optional<std::string> handle_request(std::string_view line);

    std::string make_list_tools_response(std::string_view request_id) const;
    std::string make_attach_process_response(std::string_view request_id, std::string_view line) const;
    std::string make_detach_process_response(std::string_view request_id) const;
    std::string make_attached_process_response(std::string_view request_id) const;
    std::string make_process_list_response(std::string_view request_id, std::string_view line) const;
    std::string make_module_list_response(std::string_view request_id, std::string_view line) const;
    std::string make_module_list_full_response(std::string_view request_id) const;
    std::string make_query_memory_response(std::string_view request_id, std::string_view line) const;
    std::string make_query_memory_map_response(std::string_view request_id, std::string_view line) const;
    std::string make_resolve_symbol_response(std::string_view request_id, std::string_view line) const;
    std::string make_aob_scan_response(std::string_view request_id, std::string_view line) const;
    std::string make_exported_list_response(std::string_view request_id, std::string_view line) const;
    std::string make_exported_get_response(std::string_view request_id, std::string_view line) const;
    std::string make_lua_eval_response(std::string_view request_id, std::string_view line) const;
    std::string make_lua_exec_response(std::string_view request_id, std::string_view line) const;
    std::string make_auto_assemble_response(std::string_view request_id, std::string_view line) const;
    std::string make_read_memory_response(std::string_view request_id, std::string_view line) const;
    std::string make_write_memory_response(std::string_view request_id, std::string_view line) const;
    std::string make_error_response(std::string_view request_id,
                                    std::string_view error,
                                    std::optional<DWORD> win32_error = std::nullopt) const;
    std::string quote_json_or_literal(std::string_view value) const;

    std::optional<DWORD> current_attached_process_id() const;
    std::optional<DWORD> resolve_process_id_by_name(std::string_view process_name) const;
    static std::string filename_component(std::string_view path_text);
    bool module_matches_name(const ModuleEntryInfo& module, std::string_view requested_name) const;
    std::optional<ModuleEntryInfo> find_module_by_name(std::string_view module_name) const;
    std::optional<std::pair<std::string, std::uint64_t>> parse_module_offset_symbol(std::string_view symbol) const;
    std::optional<DWORD> attach_process(DWORD process_id) const;
    std::optional<DWORD> detach_process() const;
    MemoryAccessContext open_attached_process(DWORD desired_access) const;
    AttachedProcessInfo query_attached_process() const;
    ProcessListResult list_processes(std::size_t limit) const;
    ModuleListResult list_modules(std::optional<std::size_t> limit) const;
    std::optional<DWORD> query_memory_region(std::uint64_t address, MemoryRegionInfo& result) const;
    std::optional<DWORD> query_memory_map(const MemoryMapQuery& query, MemoryMapResult& result) const;
    bool resolve_symbol_to_address(std::string_view symbol, SymbolResolutionResult& result) const;
    bool resolve_address_to_symbol(std::uint64_t address, SymbolResolutionResult& result) const;
    std::optional<DWORD> aob_scan(const AobScanQuery& query, AobScanResult& result) const;
    std::optional<std::string> execute_lua_eval(std::string_view script, bool as_expression, DWORD& win32_error) const;
    bool execute_auto_assemble(std::string_view script) const;

    CeMcpHostContext host_ {};
    PExportedFunctions exported_ = nullptr;
    std::unique_ptr<mcp::Client> client_;
};
}
