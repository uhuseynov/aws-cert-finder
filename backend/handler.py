"""Cert Finder stats API (AWS Lambda + Function URL + DynamoDB).

POST /result  {"cert": "saa"}  -> counts one finished quiz for that cert
GET  /stats                    -> {"total": n, "counts": [{"cert": id, "count": n}, ...]}
Paths may carry an /api prefix (CloudFront routes /api/* here).
CORS is handled by the Function URL config, not here.
"""
import base64
import json
import logging
import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

log = logging.getLogger()
log.setLevel(logging.INFO)

TABLE = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
ALLOWED = [c.strip() for c in os.environ.get("CERT_IDS", "").split(",") if c.strip()]
MAX_BODY = 1024


def reply(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body),
    }


def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = (event.get("rawPath") or "/").rstrip("/") or "/"
    if path == "/api" or path.startswith("/api/"):
        path = path[4:] or "/"
    try:
        if method == "POST" and path == "/result":
            return record_result(event)
        if method == "GET" and path == "/stats":
            return get_stats()
        if method == "GET" and path == "/":
            return reply(200, {"service": "cert-finder-stats", "endpoints": ["POST /result", "GET /stats"]})
        return reply(404, {"error": "not found"})
    except (ClientError, BotoCoreError):
        log.exception("DynamoDB call failed")
        return reply(500, {"error": "storage error"})


def record_result(event):
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return reply(400, {"error": "bad body"})
    if len(raw) > MAX_BODY:
        return reply(413, {"error": "body too large"})
    try:
        data = json.loads(raw)
    except ValueError:
        return reply(400, {"error": "body must be JSON like {\"cert\": \"saa\"}"})
    cert = data.get("cert") if isinstance(data, dict) else None
    if cert not in ALLOWED:
        return reply(400, {"error": "unknown cert id"})
    TABLE.update_item(
        Key={"cert": cert},
        UpdateExpression="ADD #n :one",
        ExpressionAttributeNames={"#n": "count"},
        ExpressionAttributeValues={":one": 1},
    )
    return reply(200, {"ok": True})


def get_stats():
    counts = {c: 0 for c in ALLOWED}
    kwargs = {}
    while True:
        page = TABLE.scan(**kwargs)
        for item in page.get("Items", []):
            if item.get("cert") in counts:
                counts[item["cert"]] = int(item.get("count", 0))
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], ALLOWED.index(kv[0])))
    return reply(200, {"total": sum(counts.values()), "counts": [{"cert": c, "count": n} for c, n in ordered]})
