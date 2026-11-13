#!/usr/bin/env python3
"""Loopback-only service for native HTTP editor/Services acceptance."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import time


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def respond(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Example", "OpenPyCharm")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            if self.path == "/binary":
                self.respond(200, bytes(range(16)), "application/octet-stream")
            elif self.path == "/slow":
                body = b"one response chunk per second\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=UTF-8")
                self.send_header("Content-Length", str(len(body) * 20))
                self.end_headers()
                for _ in range(20):
                    self.wfile.write(body)
                    self.wfile.flush()
                    time.sleep(1)
            else:
                self.respond(200, json.dumps({"status": "ok", "service": "OpenPyCharm HTTP example", "path": self.path}).encode(), "application/json; charset=UTF-8")
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 1024 * 1024:
                self.respond(413, b"Request is too large", "text/plain")
                return
            body = self.rfile.read(length)
            self.respond(200, body, self.headers.get("Content-Type", "application/octet-stream"))
        except (ValueError, BrokenPipeError, ConnectionResetError):
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18081)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    print(f"HTTP fixture listening on http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
