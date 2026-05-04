from prometheus_client import Counter, Histogram

JOBS_PROCESSED = Counter(
    "worker_jobs_total",
    "Total jobs processed by this worker",
    ["model", "status"],
)

INFERENCE_LATENCY = Histogram(
    "worker_inference_latency_seconds",
    "Time spent running the model inference",
    ["model"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)
