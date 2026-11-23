import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Tuple

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

MESSAGES_TOTAL = Counter(
    "gateway_messages_total",
    "Total messages processed by gateway router",
    ["direction", "outcome"],
)

WORKER_ERRORS_TOTAL = Counter(
    "gateway_worker_errors_total",
    "Total unhandled errors in polling loops",
    ["worker"],
)

WORKER_HEARTBEAT = Gauge(
    "gateway_worker_last_heartbeat_seconds",
    "Unix timestamp of the last successful worker iteration",
    ["worker"],
)


def start_observability_server(
    port: int,
    health_check: Callable[[], Tuple[bool, Dict[str, Any]]],
) -> ThreadingHTTPServer:
    class ObservabilityHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/metrics":
                body = generate_latest()
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/healthz":
                healthy, details = health_check()
                status_code = 200 if healthy else 503
                body = json.dumps({"healthy": healthy, **details}).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            # Suppress default stderr HTTP access logs to keep stdout pure JSON
            return

    server = ThreadingHTTPServer(("0.0.0.0", port), ObservabilityHandler)
    return server
