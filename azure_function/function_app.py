import azure.functions as func
import logging
import json
import os
import uuid
import requests
from datetime import datetime, UTC
from azure.cosmos import CosmosClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

FASTAPI_URL = os.environ.get("FASTAPI_URL", "")
NGROK_HEADER = {"ngrok-skip-browser-warning": "1"}
COSMOS_URL = os.environ.get("COSMOS_URL", "")
COSMOS_KEY = os.environ.get("COSMOS_KEY", "")
COSMOS_DB = "observability-db"
COSMOS_CONTAINER = "anomalies"


def get_cosmos_container():
    client = CosmosClient(COSMOS_URL, credential=COSMOS_KEY)
    db = client.get_database_client(COSMOS_DB)
    return db.get_container_client(COSMOS_CONTAINER)


@app.route(route="ingest", methods=["POST"])
def ingest(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Azure Function triggered")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)

    logs = body if isinstance(body, list) else [body]

    results = []
    container = get_cosmos_container()

    for log in logs:
        payload = {
            "error_count":    log.get("error_count", 0),
            "latency_ms":     log.get("latency_ms", 0),
            "memory_used_mb": log.get("memory_used_mb", 0),
            "request_count":  log.get("request_count", 0),
            "source":         log.get("source", "azure-monitor"),
            "cloud":          "azure",
        }

        resp = requests.post(
            f"{FASTAPI_URL}/detect",
            json=payload,
            headers=NGROK_HEADER,
            timeout=30,
        )
        result = resp.json()
        logging.info(f"FastAPI response: {result}")

        # Save to Cosmos DB
        item = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "error_count": str(payload["error_count"]),
            "latency_ms": str(payload["latency_ms"]),
            "memory_used_mb": str(payload["memory_used_mb"]),
            "request_count": str(payload["request_count"]),
            "source": payload["source"],
            "cloud": "azure",
            "is_anomaly": str(result.get("is_anomaly", False)),
            "severity": str(result.get("severity", 0)),
            "explanation": result.get("explanation", ""),
        }
        container.upsert_item(item)
        logging.info(f"Saved to Cosmos DB: {item['id']}")

        results.append(result)

    return func.HttpResponse(
        json.dumps({"processed": len(results), "results": results}),
        mimetype="application/json",
        status_code=200,
    )