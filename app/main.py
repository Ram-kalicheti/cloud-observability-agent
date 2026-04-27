import os
import json
import asyncio
import boto3
import numpy as np
from fastapi import FastAPI, WebSocket
from dotenv import load_dotenv
from app.detector import AnomalyDetector
from app.explainer import AnomalyExplainer
from datetime import datetime, timedelta

load_dotenv()

app = FastAPI()

detector = AnomalyDetector(contamination=0.1)
explainer = AnomalyExplainer()

cw_client = boto3.client("logs", region_name=os.getenv("AWS_REGION", "us-east-1"))
dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
table = dynamodb.Table(os.getenv("DYNAMODB_TABLE", "anomalies"))

connected_clients: list[WebSocket] = []


def fetch_cloudwatch_logs(log_group: str, minutes: int = 10) -> list[dict]:
    end = datetime.utcnow()
    start = end - timedelta(minutes=minutes)

    response = cw_client.filter_log_events(
        logGroupName=log_group,
        startTime=int(start.timestamp() * 1000),
        endTime=int(end.timestamp() * 1000),
    )

    logs = []
    for event in response.get("events", []):
        try:
            message = json.loads(event["message"])
            message["timestamp"] = event["timestamp"]
            message["source"] = log_group
            message["cloud"] = "aws"
            logs.append(message)
        except json.JSONDecodeError:
            continue

    return logs


def save_anomaly(anomaly: dict, explanation: str) -> None:
    table.put_item(Item={
        "id": f"{anomaly['timestamp']}-{anomaly['severity_score']}",
        "timestamp": str(anomaly["timestamp"]),
        "severity_score": str(anomaly["severity_score"]),
        "explanation": explanation,
        "log_entry": json.dumps(anomaly["log_entry"]),
        "cloud": anomaly["log_entry"].get("cloud", "unknown"),
    })


def seed_training_data() -> list[dict]:
    # swap this out once CloudWatch has 200+ real entries
    normal = []
    for _ in range(200):
        normal.append({
            "error_count": int(np.random.normal(2, 1)),
            "latency_ms": int(np.random.normal(120, 20)),
            "memory_used_mb": int(np.random.normal(256, 30)),
            "request_count": int(np.random.normal(100, 15)),
        })
    return normal


@app.on_event("startup")
async def startup():
    training_data = seed_training_data()
    detector.train(training_data)
    print("[main] detector ready")


@app.get("/health")
def health():
    return {"status": "ok", "trained": detector.is_trained}


@app.post("/detect")
async def detect(log_entry: dict):
    result = detector.detect(log_entry)

    if result["is_anomaly"]:
        explanation = explainer.explain(result)
        save_anomaly(result, explanation)
        payload = {**result, "explanation": explanation}

        for client in connected_clients.copy():
            try:
                await client.send_json(payload)
            except Exception:
                connected_clients.remove(client)

        return payload

    return result


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    log_group = os.getenv("CW_LOG_GROUP", "/cloud-observability-agent/logs")

    try:
        while True:
            try:
                logs = fetch_cloudwatch_logs(log_group, minutes=1)
                for entry in logs:
                    result = detector.detect(entry)
                    if result["is_anomaly"]:
                        explanation = explainer.explain(result)
                        await websocket.send_json({**result, "explanation": explanation})
            except Exception as e:
                print(f"[ws] fetch error: {e}")

            # 5 TPS limit on filter_log_events
            await asyncio.sleep(10)
    except Exception:
        connected_clients.remove(websocket)
        await websocket.close()