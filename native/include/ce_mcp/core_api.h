#pragma once

#include <windows.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CE_MCP_CORE_API_VERSION 1u

typedef void (__stdcall *CeMcpLogFn)(const char* message);
typedef void* CeMcpCoreHandle;

typedef struct CeMcpHostContext
{
    unsigned int size;
    unsigned int api_version;
    void* exported_functions;
    int plugin_id;
    CeMcpLogFn log;
} CeMcpHostContext;

typedef BOOL (__stdcall *CeMcpCoreStartFn)(const CeMcpHostContext* host, CeMcpCoreHandle* out_handle);
typedef void (__stdcall *CeMcpCoreStopFn)(CeMcpCoreHandle handle);

#ifdef __cplusplus
}
#endif
