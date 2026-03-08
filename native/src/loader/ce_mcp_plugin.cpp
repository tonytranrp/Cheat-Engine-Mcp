#include <windows.h>

#include <filesystem>
#include <string>

#define CEPlugin_GetVersion CEPlugin_GetVersion_sdk_decl
#define CEPlugin_InitializePlugin CEPlugin_InitializePlugin_sdk_decl
#define CEPlugin_DisablePlugin CEPlugin_DisablePlugin_sdk_decl
#include "cepluginsdk.h"
#undef CEPlugin_GetVersion
#undef CEPlugin_InitializePlugin
#undef CEPlugin_DisablePlugin

#include "config.hpp"
#include "plugin_loader.hpp"

namespace
{
std::filesystem::path module_path_from_address(const void* address)
{
    HMODULE module = nullptr;
    if (::GetModuleHandleExW(
            GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            static_cast<LPCWSTR>(address), &module) == FALSE)
    {
        return {};
    }

    std::wstring path(MAX_PATH, L'\0');
    DWORD copied = 0;
    while ((copied = ::GetModuleFileNameW(module, path.data(),
                                          static_cast<DWORD>(path.size()))) >= path.size())
    {
        path.resize(path.size() * 2);
    }

    if (copied == 0)
    {
        return {};
    }

    path.resize(copied);
    return std::filesystem::path(path);
}

ce_mcp::PluginLoader& loader()
{
    static ce_mcp::PluginLoader instance;
    return instance;
}
}

extern "C" __declspec(dllexport) BOOL __stdcall CEPlugin_GetVersion(
    PPluginVersion plugin_version,
    int sizeof_plugin_version)
{
    if (plugin_version == nullptr || sizeof_plugin_version != static_cast<int>(sizeof(PluginVersion)))
    {
        return FALSE;
    }

    plugin_version->version = ce_mcp::config::kSdkVersion;
    plugin_version->pluginname = const_cast<char*>(ce_mcp::config::kPluginName);
    return TRUE;
}

extern "C" __declspec(dllexport) BOOL __stdcall CEPlugin_InitializePlugin(
    PExportedFunctions exported,
    int plugin_id)
{
    if (exported == nullptr)
    {
        return FALSE;
    }

    const auto plugin_path = module_path_from_address(reinterpret_cast<const void*>(&CEPlugin_InitializePlugin));
    return loader().initialize(exported, plugin_id, plugin_path) ? TRUE : FALSE;
}

extern "C" __declspec(dllexport) BOOL __stdcall CEPlugin_DisablePlugin(void)
{
    loader().shutdown();
    return TRUE;
}
