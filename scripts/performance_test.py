#!/usr/bin/env python3
"""
Performance/load test for AZADEXA ERP.
Usage: python scripts/performance_test.py [url] [requests]
"""
import sys
import time
import concurrent.futures
import urllib.request
import urllib.error
import json
from statistics import mean, stdev

DEFAULT_URL = "http://localhost:5000/auth/login"
DEFAULT_REQUESTS = 100
DEFAULT_CONCURRENCY = 10


def make_request(url: str) -> dict:
    start = time.perf_counter()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
        body = b""
    except Exception as e:
        status = 0
        body = str(e).encode()
    elapsed = time.perf_counter() - start
    return {
        "status": status,
        "elapsed_ms": elapsed * 1000,
        "size_bytes": len(body),
    }


def run_load_test(url: str, total_requests: int, concurrency: int) -> dict:
    results = []
    print(f"Testing {url} with {total_requests} requests ({concurrency} concurrent)...")
    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(make_request, url) for _ in range(total_requests)]
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                results.append({"status": 0, "elapsed_ms": 0, "error": str(e)})
    total_time = time.perf_counter() - start

    success = [r for r in results if r.get("status") == 200]
    failures = [r for r in results if r.get("status") != 200]
    latencies = [r["elapsed_ms"] for r in success if "elapsed_ms" in r]

    report = {
        "url": url,
        "total_requests": total_requests,
        "concurrency": concurrency,
        "total_time_sec": round(total_time, 2),
        "successful": len(success),
        "failed": len(failures),
        "throughput_rps": round(total_requests / total_time, 2) if total_time > 0 else 0,
        "latency_ms": {
            "min": round(min(latencies), 2) if latencies else None,
            "max": round(max(latencies), 2) if latencies else None,
            "mean": round(mean(latencies), 2) if latencies else None,
            "p95": round(sorted(latencies)[int(len(latencies) * 0.95)], 2) if latencies else None,
        } if latencies else {},
    }
    return report


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    total = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_REQUESTS
    concurrency = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_CONCURRENCY

    report = run_load_test(url, total, concurrency)
    print(json.dumps(report, indent=2))

    # Save report
    import os
    report_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "performance-report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report saved to {report_path}")


if __name__ == "__main__":
    main()
