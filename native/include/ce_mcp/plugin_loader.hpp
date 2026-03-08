#pragma once

#include <filesystem>
#include <memory>

namespace ce_mcp
{
class PluginLoader
{
public:
    PluginLoader();
    ~PluginLoader();

    PluginLoader(const PluginLoader&) = delete;
    PluginLoader& operator=(const PluginLoader&) = delete;

    bool initialize(void* exported_functions,
                    int plugin_id,
                    const std::filesystem::path& plugin_path);
    void shutdown() noexcept;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
}
