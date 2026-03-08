#!/usr/bin/env python3
import argparse
import json
import socket
import sys


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


def parse_extra_fields(items):
    fields = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"invalid --field value '{item}', expected key=json")

        key, raw_value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"invalid --field value '{item}', key is empty")

        try:
            fields[key] = json.loads(raw_value)
        except json.JSONDecodeError:
            fields[key] = raw_value

    return fields


def main():
    parser = argparse.ArgumentParser(description="Run a single MCP tool call against the Cheat Engine bridge")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5556)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--id", default="call-1")
    parser.add_argument("--field", action="append", default=[],
                        help="extra top-level request field in key=json format")
    parser.add_argument("--show-hello", action="store_true")
    args = parser.parse_args()

    request = {
        "type": "call",
        "id": args.id,
        "tool": args.tool,
    }
    request.update(parse_extra_fields(args.field))

    with socket.create_server((args.host, args.port), reuse_port=False) as server:
        conn, _addr = server.accept()
        with conn:
            hello = recv_line(conn)
            if hello is None:
                raise RuntimeError("bridge disconnected before sending hello")

            if args.show_hello:
                print(json.dumps(hello, indent=2))

            send_line(conn, request)
            response = recv_line(conn)
            if response is None:
                raise RuntimeError("bridge disconnected before returning a result")

            print(json.dumps(response, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - operator script
        print(str(exc), file=sys.stderr)
        sys.exit(1)
