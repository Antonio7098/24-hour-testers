#!/usr/bin/env python3
"""
Latency measurement script for /slow endpoint
Part of T3-002: Measure latency of /slow endpoint
"""
import requests
import time
import statistics
import json
from datetime import datetime

BASE_URL = "http://localhost:3000"
ENDPOINT = "/slow"
NUM_REQUESTS = 20

def measure_latency():
    """Measure latency of /slow endpoint"""
    print(f"Measuring latency of {BASE_URL}{ENDPOINT}")
    print(f"Sending {NUM_REQUESTS} requests...\n")

    latencies = []
    successes = 0
    failures = 0

    for i in range(NUM_REQUESTS):
        start_time = time.time()
        try:
            response = requests.get(f"{BASE_URL}{ENDPOINT}", timeout=10)
            elapsed = time.time() - start_time
            latencies.append(elapsed)
            successes += 1
            print(f"Request {i+1}: {elapsed:.3f}s - Status: {response.status_code}")
        except Exception as e:
            failures += 1
            print(f"Request {i+1}: FAILED - {str(e)}")

    if latencies:
        latencies.sort()
        print(f"\n=== Latency Statistics ===")
        print(f"Total requests: {NUM_REQUESTS}")
        print(f"Successful: {successes}")
        print(f"Failed: {failures}")
        print(f"Min: {min(latencies):.3f}s")
        print(f"Max: {max(latencies):.3f}s")
        print(f"Mean: {statistics.mean(latencies):.3f}s")
        print(f"Median: {statistics.median(latencies):.3f}s")
        print(f"Std Dev: {statistics.stdev(latencies):.3f}s")

        p95_idx = int(len(latencies) * 0.95)
        p99_idx = int(len(latencies) * 0.99)
        print(f"P95: {latencies[p95_idx]:.3f}s")
        print(f"P99: {latencies[p99_idx]:.3f}s")

        slo_compliant = latencies[p95_idx] < 5.0
        print(f"\nSLO Check (P95 < 5s for /slow): {'PASS' if slo_compliant else 'FAIL'}")

        return {
            "endpoint": ENDPOINT,
            "timestamp": datetime.now().isoformat(),
            "num_requests": NUM_REQUESTS,
            "successful": successes,
            "failed": failures,
            "min_latency": min(latencies),
            "max_latency": max(latencies),
            "mean_latency": statistics.mean(latencies),
            "median_latency": statistics.median(latencies),
            "std_dev": statistics.stdev(latencies),
            "p95_latency": latencies[p95_idx],
            "p99_latency": latencies[p99_idx],
            "slo_compliant": slo_compliant
        }
    else:
        return {"error": "No successful requests"}

if __name__ == "__main__":
    result = measure_latency()
    print(f"\n=== Raw Data ===")
    print(json.dumps(result, indent=2))
