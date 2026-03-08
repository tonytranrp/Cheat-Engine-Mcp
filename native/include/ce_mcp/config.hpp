#pragma once

#include <cstdint>

namespace ce_mcp::config
{
inline constexpr char kPluginName[] = "MCP Bridge Plugin";
inline constexpr unsigned int kPluginVersion = 1;
inline constexpr unsigned int kSdkVersion = 6;
inline constexpr unsigned int kCoreApiVersion = 1;

inline constexpr char kDefaultHost[] = "127.0.0.1";
inline constexpr std::uint16_t kDefaultPort = 5556;
inline constexpr int kReconnectDelayMs = 1000;
inline constexpr int kPollIntervalMs = 250;

inline constexpr char kLoaderLogPrefix[] = "[ce-mcp-loader] ";
inline constexpr char kCoreLogPrefix[] = "[ce-mcp-core] ";

inline constexpr wchar_t kRuntimeDirectoryName[] = L"runtime";
inline constexpr wchar_t kVersionsDirectoryName[] = L"versions";
inline constexpr wchar_t kCurrentCoreManifestName[] = L"current.txt";
inline constexpr wchar_t kControlInfoFileName[] = L"control.txt";
inline constexpr wchar_t kRuntimeConfigFileName[] = L"mcp_config.txt";
inline constexpr wchar_t kNamedPipePrefix[] = LR"(\\.\pipe\)";
inline constexpr char kControlPipePrefix[] = "ce_mcp_plugin_control_";
inline constexpr wchar_t kCoreVersionPrefix[] = L"ce_mcp_plugin_core_";
}
