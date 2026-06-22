#!/bin/bash
STAGING_URL=${1:-http://localhost:5000}

pip install locust -q
locust -f scripts/performance_test.py --host=$STAGING_URL
# Open http://localhost:8089
# Users: 100, Spawn rate: 10
# Target: Response time < 500ms, Failure rate < 1%
