#include "plugin_loader.hpp"

#include <windows.h>

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>

#include "cepluginsdk.h"
#include "config.hpp"
#include "core_api.h"

namespace
{
void __stdcall loader_log_sink(const char* message)
{
    if (message == nullptr)
    {
        return;
    }

    std::string line;
    line.reserve(std::char_traits<char>::length(ce_mcp::config::kLoaderLogPrefix) +
                 std::char_traits<char>::length(message) + 2);
    line.append(ce_mcp::config::kLoaderLogPrefix);
    line.append(message);
    line.push_back('\n');
    ::OutputDebugStringA(line.c_str());
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

std::string path_to_utf8(const std::filesystem::path& path)
{
    const auto utf8 = path.u8string();
    return std::string(reinterpret_cast<const char*>(utf8.c_str()), utf8.size());
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

std::filesystem::path path_from_utf8(std::string_view text)
{
    if (text.empty())
    {
        return {};
    }

    const int required = ::MultiByteToWideChar(CP_UTF8, 0, text.data(),
                                               static_cast<int>(text.size()), nullptr, 0);
    if (required <= 0)
    {
        return std::filesystem::path(std::string(text));
    }

    std::wstring wide(required, L'\0');
    const int converted = ::MultiByteToWideChar(CP_UTF8, 0, text.data(),
                                                static_cast<int>(text.size()), wide.data(), required);
    wide.resize(converted > 0 ? static_cast<std::size_t>(converted) : 0U);
    return std::filesystem::path(wide);
}

std::optional<std::string> read_first_line(const std::filesystem::path& path)
{
    std::ifstream input(path, std::ios::binary);
    if (!input)
    {
        return std::nullopt;
    }

    std::string line;
    std::getline(input, line);
    return trim_ascii(line);
}

bool write_text_file(const std::filesystem::path& path, std::string_view text)
{
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if (!output)
    {
        return false;
    }

    output.write(text.data(), static_cast<std::streamsize>(text.size()));
    return static_cast<bool>(output);
}

void remove_if_exists(const std::filesystem::path& path)
{
    std::error_code error;
    std::filesystem::remove(path, error);
}

std::string read_pipe_command(HANDLE pipe)
{
    std::string command;
    command.reserve(512);

    char ch = '\0';
    DWORD read = 0;
    while (::ReadFile(pipe, &ch, 1, &read, nullptr) == TRUE && read == 1)
    {
        if (ch == '\n')
        {
            break;
        }

        if (ch != '\r')
        {
            command.push_back(ch);
        }
    }

    return trim_ascii(command);
}

void write_pipe_response(HANDLE pipe, std::string_view response)
{
    const std::string line = std::string(response) + "\n";
    DWORD written = 0;
    ::WriteFile(pipe, line.data(), static_cast<DWORD>(line.size()), &written, nullptr);
    ::FlushFileBuffers(pipe);
}
}

namespace ce_mcp
{
struct PluginLoader::Impl
{
    struct AttachedProcessInfo
    {
        bool attached = false;
        DWORD process_id = 0;
        std::string process_name;
        std::string image_path;
    };

    struct LoadedCore
    {
        HMODULE module = nullptr;
        CeMcpCoreHandle handle = nullptr;
        CeMcpCoreStopFn stop = nullptr;
        std::filesystem::path path;
    };

    std::mutex mutex;
    ExportedFunctions exported_functions_copy {};
    PExportedFunctions exported_functions = nullptr;
    int plugin_id = 0;
    std::filesystem::path plugin_path;
    std::filesystem::path plugin_root;
    std::filesystem::path runtime_dir;
    std::filesystem::path versions_dir;
    std::filesystem::path current_manifest_path;
    std::filesystem::path control_info_path;
    std::wstring control_pipe_path;
    std::string control_pipe_name;
    std::jthread control_thread;
    LoadedCore current_core;
    bool initialized = false;

    bool initialize(void* ef, int id, const std::filesystem::path& path)
    {
        {
            std::lock_guard<std::mutex> lock(mutex);
            if (initialized)
            {
                loader_log_sink("Loader already initialized.");
                return true;
            }

            std::memset(&exported_functions_copy, 0, sizeof(exported_functions_copy));
            const auto* incoming = static_cast<const ExportedFunctions*>(ef);
            if (incoming != nullptr)
            {
                std::size_t copy_size = sizeof(exported_functions_copy);
                if (incoming->sizeofExportedFunctions > 0)
                {
                    copy_size = std::min<std::size_t>(
                        sizeof(exported_functions_copy),
                        static_cast<std::size_t>(incoming->sizeofExportedFunctions));
                }

                std::memcpy(&exported_functions_copy, incoming, copy_size);
                if (exported_functions_copy.sizeofExportedFunctions <= 0)
                {
                    exported_functions_copy.sizeofExportedFunctions =
                        static_cast<int>(copy_size);
                }

                exported_functions = &exported_functions_copy;
            }
            else
            {
                exported_functions = nullptr;
            }

            plugin_id = id;
            plugin_path = path;
            plugin_root = plugin_path.parent_path();
            runtime_dir = plugin_root / config::kRuntimeDirectoryName;
            versions_dir = runtime_dir / config::kVersionsDirectoryName;
            current_manifest_path = runtime_dir / config::kCurrentCoreManifestName;
            control_info_path = runtime_dir / config::kControlInfoFileName;
            control_pipe_name = config::kControlPipePrefix + std::to_string(::GetCurrentProcessId());
            control_pipe_path = std::wstring(config::kNamedPipePrefix) +
                                std::wstring(control_pipe_name.begin(), control_pipe_name.end());
        }

        std::error_code error;
        std::filesystem::create_directories(versions_dir, error);
        if (error)
        {
            loader_log_sink("Failed to create runtime directories.");
            return false;
        }

        write_control_info();
        control_thread = std::jthread(
            [this](std::stop_token stop_token)
            {
                control_loop(stop_token);
            });

        {
            std::lock_guard<std::mutex> lock(mutex);
            initialized = true;
        }

        if (const auto requested = preferred_core_path())
        {
            reload_core(*requested);
        }
        else
        {
            loader_log_sink("No staged core DLL found. Use tools/dev/update-core.ps1 to stage one.");
        }

        return true;
    }

    void shutdown() noexcept
    {
        {
            std::lock_guard<std::mutex> lock(mutex);
            if (!initialized)
            {
                return;
            }

            initialized = false;
        }

        if (control_thread.joinable())
        {
            control_thread.request_stop();
            wake_control_pipe();
            control_thread.join();
        }

        LoadedCore old_core;
        {
            std::lock_guard<std::mutex> lock(mutex);
            old_core = std::exchange(current_core, {});
        }

        unload_core(std::move(old_core));
        remove_if_exists(control_info_path);
    }

    void control_loop(std::stop_token stop_token)
    {
        while (!stop_token.stop_requested())
        {
            HANDLE pipe = ::CreateNamedPipeW(
                control_pipe_path.c_str(),
                PIPE_ACCESS_DUPLEX,
                PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
                1,
                4096,
                4096,
                0,
                nullptr);

            if (pipe == INVALID_HANDLE_VALUE)
            {
                loader_log_sink("CreateNamedPipeW failed.");
                std::this_thread::sleep_for(std::chrono::milliseconds(250));
                continue;
            }

            const BOOL connected = ::ConnectNamedPipe(pipe, nullptr) == TRUE
                                       ? TRUE
                                       : (::GetLastError() == ERROR_PIPE_CONNECTED ? TRUE : FALSE);

            if (connected == FALSE)
            {
                ::CloseHandle(pipe);
                continue;
            }

            const std::string command = read_pipe_command(pipe);
            const std::string response = execute_command(command);
            write_pipe_response(pipe, response);

            ::DisconnectNamedPipe(pipe);
            ::CloseHandle(pipe);
        }
    }

    std::string execute_command(const std::string& command)
    {
        if (command.empty() || command == "wake")
        {
            return "ok";
        }

        if (command == "status")
        {
            std::lock_guard<std::mutex> lock(mutex);
            if (current_core.module == nullptr)
            {
                return "ok unloaded";
            }

            return "ok loaded " + path_to_utf8(current_core.path);
        }

        if (command == "attached_process")
        {
            const auto info = query_attached_process();
            std::ostringstream stream;
            stream << "ok {\"attached\":" << (info.attached ? "true" : "false")
                   << ",\"process_id\":" << info.process_id
                   << ",\"process_name\":\"" << escape_json_string(info.process_name) << "\""
                   << ",\"image_path\":\"" << escape_json_string(info.image_path) << "\"}";
            return stream.str();
        }

        if (command == "reload")
        {
            const auto requested = preferred_core_path();
            if (!requested)
            {
                return "error no_staged_core";
            }

            return reload_core(*requested) ? "ok reloaded " + path_to_utf8(*requested)
                                           : "error reload_failed";
        }

        constexpr std::string_view reload_prefix = "reload ";
        if (command.rfind(reload_prefix, 0) == 0)
        {
            const auto path_text = trim_ascii(command.substr(reload_prefix.size()));
            if (path_text.empty())
            {
                return "error missing_path";
            }

            const auto requested = std::filesystem::absolute(path_from_utf8(path_text));
            return reload_core(requested) ? "ok reloaded " + path_to_utf8(requested)
                                          : "error reload_failed";
        }

        if (command == "unload")
        {
            LoadedCore old_core;
            {
                std::lock_guard<std::mutex> lock(mutex);
                old_core = std::exchange(current_core, {});
            }

            unload_core(std::move(old_core));
            remove_if_exists(current_manifest_path);
            return "ok unloaded";
        }

        return "error unknown_command";
    }

    bool reload_core(const std::filesystem::path& requested_path)
    {
        std::error_code error;
        const auto normalized_path = std::filesystem::weakly_canonical(requested_path, error);
        const auto target_path = error ? std::filesystem::absolute(requested_path) : normalized_path;

        if (!std::filesystem::exists(target_path))
        {
            loader_log_sink("Requested core DLL does not exist.");
            return false;
        }

        auto new_core = load_core(target_path);
        if (!new_core)
        {
            return false;
        }

        LoadedCore old_core;
        {
            std::lock_guard<std::mutex> lock(mutex);
            old_core = std::exchange(current_core, std::move(*new_core));
            write_text_file(current_manifest_path, path_to_utf8(current_core.path));
        }

        unload_core(std::move(old_core));
        loader_log_sink("Core DLL reloaded.");
        return true;
    }

    std::optional<LoadedCore> load_core(const std::filesystem::path& path)
    {
        HMODULE module = ::LoadLibraryW(path.c_str());
        if (module == nullptr)
        {
            loader_log_sink("LoadLibraryW failed for staged core DLL.");
            return std::nullopt;
        }

        auto start = reinterpret_cast<CeMcpCoreStartFn>(::GetProcAddress(module, "CeMcpCore_Start"));
        auto stop = reinterpret_cast<CeMcpCoreStopFn>(::GetProcAddress(module, "CeMcpCore_Stop"));
        if (start == nullptr || stop == nullptr)
        {
            loader_log_sink("Core DLL exports are missing.");
            ::FreeLibrary(module);
            return std::nullopt;
        }

        CeMcpHostContext host {};
        host.size = sizeof(host);
        host.api_version = CE_MCP_CORE_API_VERSION;
        host.exported_functions = exported_functions;
        host.plugin_id = plugin_id;
        host.log = &loader_log_sink;

        CeMcpCoreHandle handle = nullptr;
        if (start(&host, &handle) == FALSE)
        {
            loader_log_sink("Core startup failed.");
            ::FreeLibrary(module);
            return std::nullopt;
        }

        LoadedCore loaded;
        loaded.module = module;
        loaded.handle = handle;
        loaded.stop = stop;
        loaded.path = path;
        return loaded;
    }

    void unload_core(LoadedCore core) noexcept
    {
        if (core.module == nullptr)
        {
            return;
        }

        if (core.stop != nullptr && core.handle != nullptr)
        {
            core.stop(core.handle);
        }

        ::FreeLibrary(core.module);
    }

    std::optional<std::filesystem::path> preferred_core_path() const
    {
        if (const auto manifest = read_first_line(current_manifest_path))
        {
            const auto from_manifest = path_from_utf8(*manifest);
            if (std::filesystem::exists(from_manifest))
            {
                return from_manifest;
            }
        }

        return latest_staged_core();
    }

    std::optional<std::filesystem::path> latest_staged_core() const
    {
        std::error_code error;
        if (!std::filesystem::exists(versions_dir, error))
        {
            return std::nullopt;
        }

        std::vector<std::filesystem::path> candidates;
        for (const auto& entry : std::filesystem::directory_iterator(versions_dir, error))
        {
            if (error || !entry.is_regular_file())
            {
                continue;
            }

            const auto filename = entry.path().filename().wstring();
            if (filename.rfind(config::kCoreVersionPrefix, 0) == 0 &&
                entry.path().extension() == L".dll")
            {
                candidates.push_back(entry.path());
            }
        }

        if (candidates.empty())
        {
            return std::nullopt;
        }

        std::sort(candidates.begin(), candidates.end());
        return candidates.back();
    }

    void write_control_info() const
    {
        std::ostringstream stream;
        stream << "pipe_name=" << control_pipe_name << "\n";
        stream << "pid=" << ::GetCurrentProcessId() << "\n";
        stream << "plugin_root=" << path_to_utf8(plugin_root) << "\n";
        write_text_file(control_info_path, stream.str());
    }

    void wake_control_pipe() const noexcept
    {
        if (::WaitNamedPipeW(control_pipe_path.c_str(), 250) == FALSE)
        {
            return;
        }

        HANDLE client = ::CreateFileW(control_pipe_path.c_str(), GENERIC_READ | GENERIC_WRITE, 0,
                                      nullptr, OPEN_EXISTING, 0, nullptr);
        if (client == INVALID_HANDLE_VALUE)
        {
            return;
        }

        constexpr char wake_command[] = "wake\n";
        DWORD written = 0;
        ::WriteFile(client, wake_command, sizeof(wake_command) - 1, &written, nullptr);
        ::CloseHandle(client);
    }

    AttachedProcessInfo query_attached_process() const
    {
        AttachedProcessInfo info;
        const auto* exported = static_cast<PExportedFunctions>(exported_functions);
        if (exported == nullptr || exported->OpenedProcessID == nullptr)
        {
            return info;
        }

        info.process_id = *exported->OpenedProcessID;
        info.attached = info.process_id != 0;
        if (!info.attached)
        {
            return info;
        }

        HANDLE process_handle = nullptr;
        bool close_handle = false;
        if (exported->OpenedProcessHandle != nullptr)
        {
            process_handle = *exported->OpenedProcessHandle;
        }

        if (process_handle == nullptr || process_handle == INVALID_HANDLE_VALUE)
        {
            process_handle = ::OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, info.process_id);
            close_handle = process_handle != nullptr;
        }

        if (process_handle == nullptr || process_handle == INVALID_HANDLE_VALUE)
        {
            return info;
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
};

PluginLoader::PluginLoader() : impl_(std::make_unique<Impl>()) {}
PluginLoader::~PluginLoader() = default;

bool PluginLoader::initialize(void* exported_functions,
                              int plugin_id,
                              const std::filesystem::path& plugin_path)
{
    return impl_->initialize(exported_functions, plugin_id, plugin_path);
}

void PluginLoader::shutdown() noexcept
{
    impl_->shutdown();
}
}



