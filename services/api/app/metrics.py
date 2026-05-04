from prometheus_client import Counter, Gauge, Histogram

REQUEST_COUNT = Counter(
    "api_requests_total",
    "Total prediction requests",
    ["model", "status"],
)

REQUEST_LATENCY = Histogram(
    "api_request_latency_seconds",
    "End-to-end request latency in seconds",
    ["model"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

QUEUE_LENGTH = Gauge(
    "api_queue_length",
    "Estimated in-flight requests",
    ["model"],
)

TIMEOUT_COUNT = Counter(
    "api_timeouts_total",
    "Requests that timed out waiting for a worker",
    ["model"],
)
