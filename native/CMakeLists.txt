cmake_minimum_required(VERSION 3.20)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CE_MCP_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/include/ce_mcp")
set(CE_MCP_CHEAT_ENGINE_SDK_DIR "${CMAKE_CURRENT_SOURCE_DIR}/vendor/cheat_engine")
set(CE_MCP_LIBHAT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/vendor/libhat")
set(CE_MCP_LUA_STUB_DIR "${CMAKE_CURRENT_SOURCE_DIR}/vendor/lua")
set(CE_MCP_LOADER_ARTIFACT_DIR "${CMAKE_BINARY_DIR}/artifacts/loader")
set(CE_MCP_LOADER_LIVE_DIR "${CMAKE_BINARY_DIR}/loader")

set(LIBHAT_INSTALL_TARGET OFF CACHE BOOL "" FORCE)
set(LIBHAT_TESTING OFF CACHE BOOL "" FORCE)
set(LIBHAT_TESTING_ASAN OFF CACHE BOOL "" FORCE)
set(LIBHAT_TESTING_SDE OFF CACHE BOOL "" FORCE)
set(LIBHAT_TESTING_SAMPLE_BIN OFF CACHE BOOL "" FORCE)
set(LIBHAT_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LIBHAT_STATIC_C_LIB OFF CACHE BOOL "" FORCE)
set(LIBHAT_SHARED_C_LIB OFF CACHE BOOL "" FORCE)
set(LIBHAT_MODULE_TARGET OFF CACHE BOOL "" FORCE)
add_subdirectory("${CE_MCP_LIBHAT_DIR}" "${CMAKE_BINARY_DIR}/vendor/libhat" EXCLUDE_FROM_ALL)

add_library(ce_mcp_loader SHARED
    src/loader/ce_mcp_plugin.cpp
    src/loader/plugin_loader.cpp
)

add_library(ce_mcp_core SHARED
    src/core/core_exports.cpp
    src/core/core_exported_tools.cpp
    src/core/core_lua_tools.cpp
    src/core/core_memory_tools.cpp
    src/core/core_process_tools.cpp
    src/core/core_runtime.cpp
    src/core/core_support.cpp
    src/core/mcp_client.cpp
)

target_include_directories(ce_mcp_loader PRIVATE
    "${CE_MCP_INCLUDE_DIR}"
    "${CE_MCP_CHEAT_ENGINE_SDK_DIR}"
    "${CE_MCP_LUA_STUB_DIR}"
)

target_include_directories(ce_mcp_core PRIVATE
    "${CE_MCP_INCLUDE_DIR}"
    "${CE_MCP_CHEAT_ENGINE_SDK_DIR}"
    "${CE_MCP_LUA_STUB_DIR}"
)

target_compile_definitions(ce_mcp_loader PRIVATE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    _CRT_SECURE_NO_WARNINGS
)

target_compile_definitions(ce_mcp_core PRIVATE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    _CRT_SECURE_NO_WARNINGS
)

if (MSVC)
    target_compile_options(ce_mcp_loader PRIVATE /W4 /permissive-)
    target_compile_options(ce_mcp_core PRIVATE /W4 /permissive-)
else()
    target_compile_options(ce_mcp_loader PRIVATE -Wall -Wextra -Wpedantic)
    target_compile_options(ce_mcp_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

target_link_libraries(ce_mcp_core PRIVATE
    libhat::libhat
    ws2_32
)

set_target_properties(ce_mcp_loader PROPERTIES
    OUTPUT_NAME "ce_mcp_plugin"
    RUNTIME_OUTPUT_DIRECTORY "${CE_MCP_LOADER_ARTIFACT_DIR}"
)

set_target_properties(ce_mcp_core PROPERTIES
    OUTPUT_NAME "ce_mcp_plugin_core"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/core"
)

add_custom_target(ce_mcp_loader_deploy
    COMMAND powershell -ExecutionPolicy Bypass -File "${CMAKE_SOURCE_DIR}/tools/dev/deploy-loader.ps1"
            -BuiltLoaderPath "$<TARGET_FILE:ce_mcp_loader>"
            -PluginRoot "${CE_MCP_LOADER_LIVE_DIR}"
    DEPENDS ce_mcp_loader
    VERBATIM
)
