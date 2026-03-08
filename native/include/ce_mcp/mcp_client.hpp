#pragma once

#include <chrono>
#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace mcp
{
struct Config
{
    std::string host;
    std::uint16_t port = 0;
    std::chrono::milliseconds reconnect_delay {1000};
    std::chrono::milliseconds poll_interval {250};
};

using LogSink = std::function<void(std::string_view)>;
using RequestHandler = std::function<std::optional<std::string>(std::string_view)>;
using ToolNames = std::vector<std::string>;

class Client
{
public:
    explicit Client(Config config,
                    LogSink log_sink = {},
                    RequestHandler request_handler = {},
                    ToolNames advertised_tools = {});
    ~Client();

    Client(const Client&) = delete;
    Client& operator=(const Client&) = delete;
    Client(Client&&) noexcept;
    Client& operator=(Client&&) noexcept;

    void start(int plugin_id);
    void stop() noexcept;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
}
