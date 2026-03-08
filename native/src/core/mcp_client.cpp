#include "mcp_client.hpp"

#include <winsock2.h>
#include <ws2tcpip.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cctype>
#include <condition_variable>
#include <cstring>
#include <deque>
#include <mutex>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <stop_token>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "config.hpp"

namespace
{
class WinsockSession
{
public:
    WinsockSession()
    {
        WSADATA data {};
        const int result = ::WSAStartup(MAKEWORD(2, 2), &data);
        if (result != 0)
        {
            throw std::runtime_error("WSAStartup failed with error " + std::to_string(result) + ".");
        }
    }

    ~WinsockSession()
    {
        ::WSACleanup();
    }

    WinsockSession(const WinsockSession&) = delete;
    WinsockSession& operator=(const WinsockSession&) = delete;
};

class SocketHandle
{
public:
    SocketHandle() = default;
    explicit SocketHandle(SOCKET socket) noexcept : socket_(socket) {}

    ~SocketHandle()
    {
        reset();
    }

    SocketHandle(const SocketHandle&) = delete;
    SocketHandle& operator=(const SocketHandle&) = delete;

    SocketHandle(SocketHandle&& other) noexcept : socket_(std::exchange(other.socket_, INVALID_SOCKET)) {}

    SocketHandle& operator=(SocketHandle&& other) noexcept
    {
        if (this != &other)
        {
            reset();
            socket_ = std::exchange(other.socket_, INVALID_SOCKET);
        }

        return *this;
    }

    [[nodiscard]] SOCKET get() const noexcept
    {
        return socket_;
    }

    [[nodiscard]] bool valid() const noexcept
    {
        return socket_ != INVALID_SOCKET;
    }

    void reset(SOCKET socket = INVALID_SOCKET) noexcept
    {
        if (valid())
        {
            ::closesocket(socket_);
        }

        socket_ = socket;
    }

private:
    SOCKET socket_ = INVALID_SOCKET;
};

std::string trim_line(std::string line)
{
    while (!line.empty() && (line.back() == '\r' || line.back() == '\n'))
    {
        line.pop_back();
    }

    return line;
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

std::optional<std::string> extract_string_field(std::string_view json, std::string_view field)
{
    const std::string needle = "\"" + std::string(field) + "\"";
    const std::size_t key_pos = json.find(needle);
    if (key_pos == std::string_view::npos)
    {
        return std::nullopt;
    }

    const std::size_t colon_pos = json.find(':', key_pos + needle.size());
    if (colon_pos == std::string_view::npos)
    {
        return std::nullopt;
    }

    std::size_t value_pos = colon_pos + 1;
    while (value_pos < json.size() &&
           std::isspace(static_cast<unsigned char>(json[value_pos])) != 0)
    {
        ++value_pos;
    }

    if (value_pos >= json.size() || json[value_pos] != '"')
    {
        return std::nullopt;
    }

    ++value_pos;
    std::string value;
    value.reserve(json.size() - value_pos);

    bool escaped = false;
    for (std::size_t index = value_pos; index < json.size(); ++index)
    {
        const char ch = json[index];

        if (escaped)
        {
            switch (ch)
            {
            case '"':
            case '\\':
            case '/':
                value.push_back(ch);
                break;
            case 'n':
                value.push_back('\n');
                break;
            case 'r':
                value.push_back('\r');
                break;
            case 't':
                value.push_back('\t');
                break;
            default:
                value.push_back(ch);
                break;
            }

            escaped = false;
            continue;
        }

        if (ch == '\\')
        {
            escaped = true;
            continue;
        }

        if (ch == '"')
        {
            return value;
        }

        value.push_back(ch);
    }

    return std::nullopt;
}

std::string make_json_string_array(const std::vector<std::string>& values)
{
    std::ostringstream stream;
    stream << "[";

    for (std::size_t index = 0; index < values.size(); ++index)
    {
        if (index != 0)
        {
            stream << ",";
        }

        stream << "\"" << escape_json_string(values[index]) << "\"";
    }

    stream << "]";
    return stream.str();
}
}

namespace mcp
{
struct Client::Impl
{
    explicit Impl(Config cfg, LogSink sink, RequestHandler handler, ToolNames tools)
        : config(std::move(cfg)),
          log_sink(std::move(sink)),
          request_handler(std::move(handler)),
          advertised_tools(std::move(tools))
    {
    }

    Config config;
    LogSink log_sink;
    RequestHandler request_handler;
    ToolNames advertised_tools;
    int plugin_id = 0;
    std::jthread worker;
    std::mutex socket_mutex;
    std::mutex send_mutex;
    std::mutex request_queue_mutex;
    std::condition_variable_any request_queue_cv;
    std::deque<std::pair<std::string, SOCKET>> request_queue;
    std::vector<std::jthread> request_workers;
    SOCKET active_socket = INVALID_SOCKET;

    void log(std::string_view message) const
    {
        if (log_sink)
        {
            log_sink(message);
        }
    }

    void start(int id)
    {
        stop();
        plugin_id = id;
        start_request_workers();
        worker = std::jthread(
            [this](std::stop_token stop_token)
            {
                run_loop(stop_token);
            });
    }

    void stop() noexcept
    {
        if (worker.joinable())
        {
            worker.request_stop();
            shutdown_active_socket();
            worker.join();
        }
        stop_request_workers();
    }

    void shutdown_active_socket() noexcept
    {
        std::lock_guard<std::mutex> lock(socket_mutex);
        if (active_socket != INVALID_SOCKET)
        {
            ::shutdown(active_socket, SD_BOTH);
        }
    }

    void set_active_socket(SOCKET socket) noexcept
    {
        std::lock_guard<std::mutex> lock(socket_mutex);
        active_socket = socket;
    }

    void clear_active_socket() noexcept
    {
        std::lock_guard<std::mutex> lock(socket_mutex);
        active_socket = INVALID_SOCKET;
    }

    [[nodiscard]] bool is_socket_active(SOCKET socket) noexcept
    {
        std::lock_guard<std::mutex> lock(socket_mutex);
        return active_socket == socket;
    }

    void start_request_workers()
    {
        stop_request_workers();

        const unsigned int hardware_threads = std::thread::hardware_concurrency();
        const unsigned int worker_count = std::clamp(hardware_threads == 0 ? 4u : hardware_threads, 2u, 6u);
        request_workers.reserve(worker_count);
        for (unsigned int index = 0; index < worker_count; ++index)
        {
            request_workers.emplace_back(
                [this](std::stop_token stop_token)
                {
                    request_worker_loop(stop_token);
                });
        }
    }

    void stop_request_workers() noexcept
    {
        if (request_workers.empty())
        {
            return;
        }

        for (auto& request_worker : request_workers)
        {
            request_worker.request_stop();
        }
        request_queue_cv.notify_all();
        request_workers.clear();

        std::lock_guard<std::mutex> lock(request_queue_mutex);
        request_queue.clear();
    }

    void enqueue_request(std::string line, SOCKET socket)
    {
        {
            std::lock_guard<std::mutex> lock(request_queue_mutex);
            request_queue.emplace_back(std::move(line), socket);
        }
        request_queue_cv.notify_one();
    }

    void clear_request_queue() noexcept
    {
        std::lock_guard<std::mutex> lock(request_queue_mutex);
        request_queue.clear();
    }

    void request_worker_loop(std::stop_token stop_token)
    {
        while (!stop_token.stop_requested())
        {
            std::pair<std::string, SOCKET> request;
            {
                std::unique_lock<std::mutex> lock(request_queue_mutex);
                request_queue_cv.wait(lock, stop_token,
                                      [this]()
                                      {
                                          return !request_queue.empty();
                                      });
                if (stop_token.stop_requested())
                {
                    return;
                }
                if (request_queue.empty())
                {
                    continue;
                }

                request = std::move(request_queue.front());
                request_queue.pop_front();
            }

            process_call_request(request.first, request.second);
        }
    }

    void process_call_request(std::string_view line, SOCKET socket)
    {
        const auto response = request_handler(line);
        if (!response)
        {
            return;
        }

        if (!is_socket_active(socket))
        {
            return;
        }

        if (!send_line(socket, *response))
        {
            log("Failed to send tool call response.");
        }
    }

    void run_loop(std::stop_token stop_token)
    {
        try
        {
            WinsockSession winsock;

            while (!stop_token.stop_requested())
            {
                if (SocketHandle socket = connect_once(); socket.valid())
                {
                    log("Connected to MCP server at " + config.host + ":" +
                        std::to_string(config.port) + ".");
                    set_active_socket(socket.get());

                    if (!send_line(socket.get(), make_hello_message()))
                    {
                        clear_active_socket();
                        continue;
                    }

                    process_session(socket.get(), stop_token);
                    clear_active_socket();
                    clear_request_queue();
                    log("Disconnected from MCP server.");
                }

                if (!wait_for(stop_token, config.reconnect_delay))
                {
                    break;
                }
            }
        }
        catch (const std::exception& exception)
        {
            log("MCP client loop terminated with exception: " + std::string(exception.what()) + ".");
        }
        catch (...)
        {
            log("MCP client loop terminated with an unknown exception.");
        }
    }

    [[nodiscard]] SocketHandle connect_once()
    {
        addrinfo hints {};
        hints.ai_family = AF_UNSPEC;
        hints.ai_socktype = SOCK_STREAM;
        hints.ai_protocol = IPPROTO_TCP;

        addrinfo* result = nullptr;
        const std::string port = std::to_string(config.port);
        const int lookup = ::getaddrinfo(config.host.c_str(), port.c_str(), &hints, &result);
        if (lookup != 0)
        {
            log("getaddrinfo failed with error " + std::to_string(lookup) + ".");
            return {};
        }

        SocketHandle connected_socket;
        for (addrinfo* current = result; current != nullptr; current = current->ai_next)
        {
            SocketHandle candidate(::socket(current->ai_family, current->ai_socktype, current->ai_protocol));
            if (!candidate.valid())
            {
                continue;
            }

            if (::connect(candidate.get(), current->ai_addr, static_cast<int>(current->ai_addrlen)) == 0)
            {
                connected_socket = std::move(candidate);
                break;
            }
        }

        ::freeaddrinfo(result);

        if (!connected_socket.valid())
        {
            log("Unable to connect to MCP server at " + config.host + ":" + std::to_string(config.port) + ".");
        }

        return connected_socket;
    }

    [[nodiscard]] bool send_line(SOCKET socket, std::string_view line)
    {
        std::string payload(line);
        payload.push_back('\n');

        std::lock_guard<std::mutex> send_lock(send_mutex);
        std::size_t offset = 0;
        while (offset < payload.size())
        {
            const int sent = ::send(socket, payload.data() + offset,
                                    static_cast<int>(payload.size() - offset), 0);
            if (sent == SOCKET_ERROR)
            {
                log("send failed with error " + std::to_string(::WSAGetLastError()) + ".");
                return false;
            }

            offset += static_cast<std::size_t>(sent);
        }

        return true;
    }

    void process_session(SOCKET socket, std::stop_token stop_token)
    {
        std::string buffer;
        std::vector<char> chunk(1024);

        while (!stop_token.stop_requested())
        {
            fd_set read_set;
            FD_ZERO(&read_set);
            FD_SET(socket, &read_set);

            timeval timeout = to_timeval(config.poll_interval);
            int ready = ::select(0, &read_set, nullptr, nullptr, &timeout);
            if (ready == SOCKET_ERROR)
            {
                log("select failed with error " + std::to_string(::WSAGetLastError()) + ".");
                return;
            }

            if (ready == 0)
            {
                continue;
            }

            const int received = ::recv(socket, chunk.data(), static_cast<int>(chunk.size()), 0);
            if (received == 0)
            {
                return;
            }

            if (received == SOCKET_ERROR)
            {
                const int error = ::WSAGetLastError();
                if (error == WSAESHUTDOWN)
                {
                    return;
                }

                log("recv failed with error " + std::to_string(error) + ".");
                return;
            }

            buffer.append(chunk.data(), static_cast<std::size_t>(received));

            std::size_t newline = buffer.find('\n');
            while (newline != std::string::npos)
            {
                std::string line = trim_line(buffer.substr(0, newline));
                buffer.erase(0, newline + 1);

                if (!line.empty())
                {
                    handle_line(line, socket);
                }

                newline = buffer.find('\n');
            }
        }
    }

    void handle_line(std::string_view line, SOCKET socket)
    {
        log("Received: " + std::string(line));

        const auto message_type = extract_string_field(line, "type");
        if (!message_type)
        {
            return;
        }

        if (*message_type == "welcome")
        {
            log("MCP server handshake completed.");
            return;
        }

        if (*message_type == "ping")
        {
            const bool sent = send_line(socket, R"({"type":"pong"})");
            if (sent)
            {
                log("Sent pong.");
            }
            return;
        }

        if (*message_type == "call")
        {
            if (!request_handler)
            {
                const bool sent =
                    send_line(socket, R"({"type":"result","ok":false,"error":"no_request_handler"})");
                if (!sent)
                {
                    log("Failed to send no_request_handler response.");
                }
                return;
            }

            enqueue_request(std::string(line), socket);
            return;
        }

        log("Ignoring unsupported message type '" + *message_type + "'.");
    }

    [[nodiscard]] std::string make_hello_message() const
    {
        std::ostringstream stream;
        stream << "{\"type\":\"hello\",\"plugin\":\""
               << escape_json_string(ce_mcp::config::kPluginName)
               << "\",\"plugin_id\":" << plugin_id
               << ",\"ce_process_id\":" << ::GetCurrentProcessId()
               << ",\"sdk_version\":" << ce_mcp::config::kSdkVersion;

        if (!advertised_tools.empty())
        {
            stream << ",\"tools\":" << make_json_string_array(advertised_tools);
        }

        stream
               << "}";
        return stream.str();
    }

    [[nodiscard]] static bool wait_for(std::stop_token stop_token,
                                       std::chrono::milliseconds duration)
    {
        const auto deadline = std::chrono::steady_clock::now() + duration;
        while (!stop_token.stop_requested() && std::chrono::steady_clock::now() < deadline)
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }

        return !stop_token.stop_requested();
    }

    [[nodiscard]] static timeval to_timeval(std::chrono::milliseconds duration)
    {
        const auto seconds = std::chrono::duration_cast<std::chrono::seconds>(duration);
        const auto micros =
            std::chrono::duration_cast<std::chrono::microseconds>(duration - seconds);

        timeval timeout {};
        timeout.tv_sec = static_cast<long>(seconds.count());
        timeout.tv_usec = static_cast<long>(micros.count());
        return timeout;
    }
};

Client::Client(Config config,
               LogSink log_sink,
               RequestHandler request_handler,
               ToolNames advertised_tools)
    : impl_(std::make_unique<Impl>(std::move(config),
                                   std::move(log_sink),
                                   std::move(request_handler),
                                   std::move(advertised_tools)))
{
}

Client::~Client()
{
    if (impl_)
    {
        impl_->stop();
    }
}

Client::Client(Client&&) noexcept = default;
Client& Client::operator=(Client&&) noexcept = default;

void Client::start(int plugin_id)
{
    impl_->start(plugin_id);
}

void Client::stop() noexcept
{
    impl_->stop();
}
}
