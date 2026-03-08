#include "core_runtime.hpp"

#include <exception>
#include <memory>

namespace
{
using ce_mcp::CoreRuntime;
}

extern "C" __declspec(dllexport) BOOL __stdcall CeMcpCore_Start(
    const CeMcpHostContext* host,
    CeMcpCoreHandle* out_handle)
{
    if (host == nullptr || out_handle == nullptr || host->size != sizeof(CeMcpHostContext) ||
        host->api_version != CE_MCP_CORE_API_VERSION)
    {
        return FALSE;
    }

    try
    {
        auto runtime = std::make_unique<CoreRuntime>(*host);
        runtime->start();
        *out_handle = runtime.release();
        return TRUE;
    }
    catch (const std::exception& exception)
    {
        if (host->log != nullptr)
        {
            host->log(exception.what());
        }

        return FALSE;
    }
    catch (...)
    {
        if (host->log != nullptr)
        {
            host->log("Core startup failed with an unknown exception.");
        }

        return FALSE;
    }
}

extern "C" __declspec(dllexport) void __stdcall CeMcpCore_Stop(CeMcpCoreHandle handle)
{
    auto* runtime = static_cast<CoreRuntime*>(handle);
    if (runtime == nullptr)
    {
        return;
    }

    runtime->stop();
    delete runtime;
}
