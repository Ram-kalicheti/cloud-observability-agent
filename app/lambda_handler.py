import json
import os
import boto3
import base64
import gzip
from datetime import datetime, UTC

import urllib.request
import urllib.error

# using urllib instead of requests — it's built into Python, no extra dependency needed
FASTAPI_URL = os.environ.get("FASTAPI_URL", "http://localhost:8000")


def handler(event, context):
    raw = event.get("awslogs", {}).get("data", "")
    if not raw:
        print("[handler] no log data in event")
        return {"statusCode": 200, "body": "no data"}

    decoded = json.loads(gzip.decompress(base64.b64decode(raw)))
    log_events = decoded.get("logEvents", [])
    print(f"[handler] received {len(log_events)} log events")

    processed = 0
    for log_event in log_events:
        try:
            message = json.loads(log_event["message"])
        except (json.JSONDecodeError, KeyError):
            # skip non-JSON lines — startup messages, stack traces, etc.
            continue

        log_entry = {
            "timestamp": datetime.fromtimestamp(log_event["timestamp"] / 1000, UTC).isoformat(),
            "error_count": message.get("error_count", 0),
            "latency_ms": message.get("latency_ms", 0),
            "memory_used_mb": message.get("memory_used_mb", 0),
            "request_count": message.get("request_count", 0),
            "source": message.get("source", "cloudwatch"),
            "cloud": "aws",
        }

        try:
            req = urllib.request.Request(
                f"{FASTAPI_URL}/detect",
                data=json.dumps(log_entry).encode(),
                headers={
        "Content-Type": "application/json",
        "ngrok-skip-browser-warning": "true",  # bypass ngrok interstitial page
    },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                result = json.loads(resp.read())
                if result.get("is_anomaly"):
                    print(f"[handler] anomaly detected — score {result.get('severity_score')}")
        except urllib.error.URLError as e:
            # log and continue — don't let one failed entry kill the whole batch
            print(f"[handler] failed to call /detect: {e}")
            continue

        processed += 1

    return {
        "statusCode": 200,
        "body": json.dumps({"received": len(log_events), "processed": processed}),
    }