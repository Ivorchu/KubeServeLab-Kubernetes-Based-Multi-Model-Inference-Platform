#!/usr/bin/env python3
"""
Run structured Locust experiments and collect Prometheus metrics after each.
Writes results to experiments/<timestamp>/summary.md.

Usage:
    python scripts/run_experiments.py
    python scripts/run_experiments.py --host http://localhost:8000 --prometheus http://localhost:9090
"""
import argparse
import csv
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

EXPERIMENTS = [
    {
        "name": "baseline",
        "description": "Steady mixed traffic across all models — nominal production load",
        "user_class": "BaselineUser",
        "users": 10,
        "spawn_rate": 2,
        "duration": "60s",
    },
    {
        "name": "burst",
        "description": "High-concurrency text-small burst — tests throughput ceiling",
        "user_class": "BurstUser",
        "users": 50,
        "spawn_rate": 10,
        "duration": "60s",
    },
    {
        "name": "overload",
        "description": "Zero-wait sustained load — saturates worker queue, forces timeouts",
        "user_class": "OverloadUser",
        "users": 100,
        "spawn_rate": 25,
        "duration": "90s",
    },
]

LOCUSTFILE = "load_tests/locustfile.py"
PROM_SCRAPE_WAIT = 20  # seconds to wait after Locust finishes before querying Prometheus


# ── Prometheus helpers ────────────────────────────────────────────────────────

def _prom_query(base_url: str, query: str) -> float | None:
    encoded = urllib.parse.quote(query)
    url = f"{base_url}/api/v1/query?query={encoded}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        results = data.get("data", {}).get("result", [])
        if results:
            return float(results[0]["value"][1])
    except Exception:
        pass
    return None


def collect_metrics(prom_url: str, window: str = "2m") -> dict:
    def q(expr):
        return _prom_query(prom_url, expr)

    return {
        "throughput_rps": q(f"sum(rate(api_requests_total[{window}]))"),
        "p50_latency_s":  q(f"histogram_quantile(0.50, sum by (le) (rate(api_request_latency_seconds_bucket[{window}])))"),
        "p99_latency_s":  q(f"histogram_quantile(0.99, sum by (le) (rate(api_request_latency_seconds_bucket[{window}])))"),
        "error_rate":     q(f"sum(rate(api_requests_total{{status=~'failed|timeout'}}[{window}])) / sum(rate(api_requests_total[{window}]))"),
        "cb_open":        q("max(api_circuit_breaker_open) or vector(0)"),
        "timeout_rate":   q(f"sum(rate(api_timeouts_total[{window}]))"),
    }


# ── Locust CSV parsing ────────────────────────────────────────────────────────

def parse_locust_csv(csv_prefix: str) -> dict:
    stats_file = Path(f"{csv_prefix}_stats.csv")
    if not stats_file.exists():
        return {}
    totals = {}
    try:
        with stats_file.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("Name") == "Aggregated":
                    totals = {
                        "total_requests":  int(row.get("Request Count", 0)),
                        "total_failures":  int(row.get("Failure Count", 0)),
                        "median_ms":       float(row.get("50%", 0) or 0),
                        "p99_ms":          float(row.get("99%", 0) or 0),
                        "avg_rps":         float(row.get("Requests/s", 0) or 0),
                    }
    except Exception:
        pass
    return totals


# ── Experiment runner ─────────────────────────────────────────────────────────

def run_experiment(exp: dict, host: str, out_dir: Path) -> dict:
    print(f"\n{'='*60}")
    print(f"  Experiment: {exp['name']}")
    print(f"  {exp['description']}")
    print(f"  Users: {exp['users']}  Spawn: {exp['spawn_rate']}/s  Duration: {exp['duration']}")
    print(f"{'='*60}")

    csv_prefix = str(out_dir / exp["name"])

    # Pass the user class as a positional argument (Locust 2.x syntax)
    cmd = [
        sys.executable, "-m", "locust",
        "-f", LOCUSTFILE,
        "--headless",
        "-u", str(exp["users"]),
        "-r", str(exp["spawn_rate"]),
        "--run-time", exp["duration"],
        "--host", host,
        "--csv", csv_prefix,
        "--only-summary",
        exp["user_class"],
    ]

    print(f"  Running: {' '.join(cmd[2:])}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  WARNING: Locust exited with code {result.returncode}")
        if result.stderr:
            print(f"  stderr: {result.stderr[-500:]}")

    locust_stats = parse_locust_csv(csv_prefix)

    print(f"  Waiting {PROM_SCRAPE_WAIT}s for Prometheus to scrape final metrics...")
    time.sleep(PROM_SCRAPE_WAIT)

    return locust_stats


def collect_prom_metrics(prom_url: str, exp_name: str) -> dict:
    print(f"  Querying Prometheus for {exp_name}...")
    metrics = collect_metrics(prom_url)
    for k, v in metrics.items():
        print(f"    {k}: {v}")
    return metrics


# ── Report generation ─────────────────────────────────────────────────────────

def _fmt(val, unit="", precision=3, fallback="n/a"):
    if val is None:
        return fallback
    return f"{val:.{precision}f}{unit}"


def _pct(val, fallback="n/a"):
    if val is None:
        return fallback
    return f"{val * 100:.1f}%"


def generate_summary(results: list[dict], out_file: Path) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# KubeServeLab Load Test Results",
        "",
        f"Generated: {now}",
        "",
        "## Experiments",
        "",
        "| Experiment | Users | Duration | Requests | Failures | Locust p99 (ms) | Prom Throughput | Prom p50 | Prom p99 | Error Rate | Timeouts/s | CB Open |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for r in results:
        exp = r["experiment"]
        ls = r.get("locust_stats", {})
        pm = r.get("prom_metrics", {})
        cb = pm.get("cb_open")
        cb_str = "YES" if cb and cb >= 0.5 else "no"

        lines.append(
            f"| {exp['name']} "
            f"| {exp['users']} "
            f"| {exp['duration']} "
            f"| {ls.get('total_requests', 'n/a')} "
            f"| {ls.get('total_failures', 'n/a')} "
            f"| {_fmt(ls.get('p99_ms'), precision=0)} "
            f"| {_fmt(pm.get('throughput_rps'), ' req/s', 1)} "
            f"| {_fmt(pm.get('p50_latency_s'), 's')} "
            f"| {_fmt(pm.get('p99_latency_s'), 's')} "
            f"| {_pct(pm.get('error_rate'))} "
            f"| {_fmt(pm.get('timeout_rate'), '/s', 2)} "
            f"| {cb_str} |"
        )

    lines += [
        "",
        "## Observations",
        "",
    ]

    for r in results:
        exp = r["experiment"]
        pm = r.get("prom_metrics", {})
        ls = r.get("locust_stats", {})
        lines.append(f"### {exp['name'].capitalize()}")
        lines.append(f"> {exp['description']}")
        lines.append("")

        throughput = pm.get("throughput_rps")
        p99 = pm.get("p99_latency_s")
        error_rate = pm.get("error_rate")
        cb_open = pm.get("cb_open")
        timeout_rate = pm.get("timeout_rate")

        if throughput is not None:
            lines.append(f"- Throughput: **{throughput:.1f} req/s**")
        if p99 is not None:
            lines.append(f"- p99 latency: **{p99:.3f}s**")
        if error_rate is not None:
            lines.append(f"- Error rate: **{error_rate * 100:.1f}%**")
        if timeout_rate is not None and timeout_rate > 0:
            lines.append(f"- Timeout rate: **{timeout_rate:.2f}/s** — queue saturation visible")
        if cb_open is not None and cb_open >= 0.5:
            lines.append("- Circuit breaker: **OPEN** — model rejecting with 503")
        if ls.get("total_failures", 0) == 0 and error_rate is not None and error_rate < 0.01:
            lines.append("- System healthy under this load — no failures recorded")
        lines.append("")

    lines += [
        "## Setup",
        "",
        f"- Locustfile: `{LOCUSTFILE}`",
        "- All experiments run sequentially against the same stack",
        "- Prometheus metrics sampled over a 2-minute window immediately after each run",
        "",
    ]

    out_file.write_text("\n".join(lines))
    print(f"\nSummary written to {out_file}")


# ── Main ──────────────────────────────────────────────────────────────────────

def _check_reachable(url: str, label: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=3)
        return True
    except Exception as exc:
        print(f"  WARNING: {label} not reachable at {url} ({exc})")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Run KubeServeLab load experiments")
    parser.add_argument("--host", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--prometheus", default="http://localhost:9090", help="Prometheus base URL")
    parser.add_argument("--experiment", help="Run only this experiment by name")
    parser.add_argument("--skip-prometheus", action="store_true", help="Skip Prometheus metric collection")
    args = parser.parse_args()

    experiments = EXPERIMENTS
    if args.experiment:
        experiments = [e for e in EXPERIMENTS if e["name"] == args.experiment]
        if not experiments:
            print(f"Unknown experiment '{args.experiment}'. Choose from: {[e['name'] for e in EXPERIMENTS]}")
            sys.exit(1)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("experiments") / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Output directory: {out_dir}")
    print(f"API host:         {args.host}")
    print(f"Prometheus:       {args.prometheus}")

    api_ok = _check_reachable(f"{args.host}/health", "API")
    prom_ok = not args.skip_prometheus and _check_reachable(f"{args.prometheus}/-/ready", "Prometheus")

    if not api_ok:
        print("\nERROR: API is not reachable. Start the stack first:")
        print("  docker compose up -d          # Docker Compose")
        print("  kubectl port-forward ... svc/api 8000:80   # K8s")
        sys.exit(1)

    if not prom_ok and not args.skip_prometheus:
        print("\nWARNING: Prometheus not reachable — metric columns will be empty.")
        print("  To fix: docker compose --profile monitoring up -d")
        print("       or: kubectl port-forward -n kubeservelab svc/prometheus 9090:9090")
        print("  Or rerun with --skip-prometheus to suppress this warning.\n")

    all_results = []
    for exp in experiments:
        locust_stats = run_experiment(exp, args.host, out_dir)
        prom_metrics = collect_prom_metrics(args.prometheus, exp["name"]) if prom_ok else {}
        all_results.append({
            "experiment": exp,
            "locust_stats": locust_stats,
            "prom_metrics": prom_metrics,
        })

    summary_file = out_dir / "summary.md"
    generate_summary(all_results, summary_file)

    # Also write raw JSON for further analysis
    raw_file = out_dir / "results.json"
    raw_file.write_text(json.dumps(all_results, indent=2, default=str))
    print(f"Raw results:      {raw_file}")


if __name__ == "__main__":
    main()
