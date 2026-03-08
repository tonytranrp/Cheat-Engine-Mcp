#!/usr/bin/env python3
import argparse
import json
import socket


def send_line(conn, payload):
    conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))


def recv_line(conn):
    data = bytearray()
    while True:
        chunk = conn.recv(1)
        if not chunk:
            break
        if chunk == b"\n":
            break
        if chunk != b"\r":
            data.extend(chunk)
    if not data:
        return None
    return json.loads(data.decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Demo MCP server for the Cheat Engine bridge")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5556)
    args = parser.parse_args()

    with socket.create_server((args.host, args.port), reuse_port=False) as server:
        print(f"listening on {args.host}:{args.port}")
        conn, addr = server.accept()
        with conn:
            print(f"client connected from {addr[0]}:{addr[1]}")
            hello = recv_line(conn)
            print("hello:", json.dumps(hello, indent=2))

            send_line(conn, {"type": "welcome"})
            send_line(conn, {"type": "call", "id": "tools-1", "tool": "ce.list_tools"})
            tools = recv_line(conn)
            print("tools:", json.dumps(tools, indent=2))

            send_line(conn, {"type": "call", "id": "proc-1", "tool": "ce.get_attached_process"})
            attached = recv_line(conn)
            print("attached process:", json.dumps(attached, indent=2))


if __name__ == "__main__":
    main()
