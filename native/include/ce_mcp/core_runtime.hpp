#pragma once

#include <memory>

#include "core_api.h"

namespace ce_mcp
{
class CoreRuntime
{
public:
    explicit CoreRuntime(CeMcpHostContext host);
    ~CoreRuntime();

    CoreRuntime(const CoreRuntime&) = delete;
    CoreRuntime& operator=(const CoreRuntime&) = delete;

    CoreRuntime(CoreRuntime&&) noexcept;
    CoreRuntime& operator=(CoreRuntime&&) noexcept;

    void start();
    void stop() noexcept;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
}
