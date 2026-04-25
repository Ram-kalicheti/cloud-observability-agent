import json
import os
import boto3
import base64
import gzip
import numpy as np
from datetime import datetime, UTC

from app.detector import AnomalyDetector
from app.explainer import AnomalyExplainer

# reuse across warm invocations
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
table = dynamodb.Table(os.environ.get("DYNAMODB_TABLE", "anomalies"))

detector = AnomalyDetector(contamination=0.1)
explainer = AnomalyExplainer()


def _seed_training_data() -> list[dict]:
    # synthetic baseline — swap once CloudWatch has enough real history
    normal = []
    for _ in range(200):
        normal.append({
            "error_count": int(np.random.normal(2, 1)),
            "latency_ms": int(np.random.normal(120, 20)),
            "memory_used_mb": int(np.random.normal(256, 30)),
            "request_count": int(np.random.normal(100, 15)),
        })
    return normal


def _save_anomaly(anomaly: dict, explanation: str) -> None:
    table.put_item(Item={
        "id": f"{anomaly['timestamp']}-{anomaly['severity_score']}",
        "timestamp": anomaly["timestamp"],
        "severity_score": str(anomaly["severity_score"]),  # DynamoDB doesn't store floats cleanly
        "explanation": explanation,
        "log_entry": json.dumps(anomaly["log_entry"]),
        "cloud": anomaly["log_entry"].get("cloud", "aws"),
    })


# train once at cold start — stays in memory for warm invocations
detector.train(_seed_training_data())


def handler(event, context):
    # CloudWatch sends logs as base64-encoded gzipped JSON
    raw = event.get("awslogs", {}).get("data", "")
    if not raw:
        print("[handler] no log data in event")
        return {"statusCode": 200, "body": "no data"}

    decoded = json.loads(gzip.decompress(base64.b64decode(raw)))
    log_events = decoded.get("logEvents", [])
    print(f"[handler] received {len(log_events)} log events")

    saved = 0
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

        result = detector.detect(log_entry)

        if result["is_anomaly"]:
            explanation = explainer.explain(result)
            _save_anomaly(result, explanation)
            saved += 1
            print(f"[handler] anomaly saved — score {result['severity_score']}")

    return {
        "statusCode": 200,
        "body": json.dumps({"processed": len(log_events), "anomalies_saved": saved}),
    }