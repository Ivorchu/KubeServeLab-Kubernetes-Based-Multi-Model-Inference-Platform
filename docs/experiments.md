# Experiments (Phase 7)

Document load test experiments here as they are run.

## Experiment template

**Hypothesis:**  
**Config:** workers=N, batching=on/off, model=X  
**Tool:** Locust, N users, ramp N/s, duration Xs  
**Results:**

| Metric | Value |
|--------|-------|
| Throughput (req/s) | |
| p50 latency (ms) | |
| p95 latency (ms) | |
| p99 latency (ms) | |
| Error rate | |
| Timeout rate | |

**Conclusion:**

---

## Planned experiments

1. 1 worker vs 2 workers vs 4 workers at 20 concurrent users
2. `text-small` vs `text-large` throughput comparison
3. Failure injection: kill a worker mid-load, observe recovery
4. Queue backpressure: ramp beyond worker capacity, observe queue length growth
