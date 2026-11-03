"""Tests for the stats Lambda, run against a mocked DynamoDB (moto).

    pip install -r backend/requirements-dev.txt
    pytest backend/tests
"""
import base64
import importlib.util
import json
import os
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
TREE = json.loads((ROOT / "data" / "tree.json").read_text(encoding="utf-8"))
CERT_IDS = ",".join(TREE["certs"])


def load_handler():
    spec = importlib.util.spec_from_file_location("cert_finder_handler", BACKEND / "handler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("TABLE_NAME", "cert-finder-stats-test")
    monkeypatch.setenv("CERT_IDS", CERT_IDS)
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName="cert-finder-stats-test",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "cert", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "cert", "KeyType": "HASH"}],
        )
        yield load_handler()


def call(api, method, path, body=None, b64=False):
    event = {"rawPath": path, "requestContext": {"http": {"method": method}}}
    if body is not None:
        text = body if isinstance(body, str) else json.dumps(body)
        if b64:
            text = base64.b64encode(text.encode()).decode()
        event["body"] = text
        event["isBase64Encoded"] = b64
    response = api.handler(event, None)
    return response["statusCode"], json.loads(response["body"])


def test_records_results_and_reports_stats(api):
    for cert in ["saa", "saa", "aif", "saa", "mla"]:
        status, body = call(api, "POST", "/result", {"cert": cert})
        assert (status, body) == (200, {"ok": True})

    status, body = call(api, "GET", "/stats")
    assert status == 200
    assert body["total"] == 5
    counts = body["counts"]
    assert counts[0] == {"cert": "saa", "count": 3}
    assert {c["cert"] for c in counts} == set(TREE["certs"])  # zeros included for charts
    assert [c["count"] for c in counts] == sorted((c["count"] for c in counts), reverse=True)


def test_stats_empty_table(api):
    status, body = call(api, "GET", "/stats")
    assert status == 200 and body["total"] == 0
    assert all(c["count"] == 0 for c in body["counts"])


def test_api_prefix_from_cloudfront(api):
    status, _ = call(api, "POST", "/api/result", {"cert": "scs"})
    assert status == 200
    status, body = call(api, "GET", "/api/stats")
    assert status == 200 and {"cert": "scs", "count": 1} in body["counts"]
    assert call(api, "GET", "/api")[0] == 200
    assert call(api, "GET", "/apistats")[0] == 404


def test_trailing_slash_and_base64_body(api):
    status, _ = call(api, "POST", "/result/", {"cert": "dea"}, b64=True)
    assert status == 200
    _, body = call(api, "GET", "/stats/")
    assert {"cert": "dea", "count": 1} in body["counts"]


@pytest.mark.parametrize(
    "body",
    [{"cert": "not-a-cert"}, {"cert": ["saa"]}, {}, ["saa"], "saa", '{"cert": null}'],
)
def test_rejects_unknown_or_malformed_cert(api, body):
    status, response = call(api, "POST", "/result", body)
    assert status == 400 and "error" in response


def test_rejects_invalid_json_and_huge_body(api):
    assert call(api, "POST", "/result", "{not json")[0] == 400
    assert call(api, "POST", "/result", json.dumps({"cert": "saa", "x": "a" * 2000}))[0] == 413
    assert call(api, "POST", "/result", "%%%", b64=False)[0] == 400


def test_bad_routes(api):
    assert call(api, "GET", "/result")[0] == 404
    assert call(api, "POST", "/stats", {"cert": "saa"})[0] == 404
    assert call(api, "DELETE", "/stats")[0] == 404
    status, body = call(api, "GET", "/")
    assert status == 200 and body["service"] == "cert-finder-stats"


def test_storage_error_returns_500(api, monkeypatch):
    def boom(**_):
        from botocore.exceptions import ClientError

        raise ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "UpdateItem")

    monkeypatch.setattr(api.TABLE, "update_item", boom)
    status, body = call(api, "POST", "/result", {"cert": "saa"})
    assert status == 500 and body == {"error": "storage error"}


def test_template_in_sync_with_handler():
    sys.path.insert(0, str(BACKEND))
    import sync_template  # noqa: E402

    template = (BACKEND / "template.yaml").read_text(encoding="utf-8")
    handler = (BACKEND / "handler.py").read_text(encoding="utf-8")
    assert sync_template.build(template, handler) == template, "run: python backend/sync_template.py"
    assert len(sync_template.inline_code(template)) <= sync_template.INLINE_LIMIT


def test_template_cert_ids_match_tree():
    template = (BACKEND / "template.yaml").read_text(encoding="utf-8")
    line = next(l for l in template.splitlines() if l.strip().startswith('Default: "clf'))
    default_ids = line.split('"')[1].split(",")
    assert sorted(default_ids) == sorted(TREE["certs"]), "update CertIds Default in template.yaml"


def test_tree_validator_passes():
    sys.path.insert(0, str(ROOT / "scripts"))
    import validate_tree  # noqa: E402

    rep = validate_tree.Report()
    validate_tree.check_certs(TREE["certs"], rep)
    validate_tree.check_nodes(TREE, rep)
    paths = validate_tree.walk_paths(TREE, rep)
    validate_tree.check_coverage(TREE, paths, rep)
    assert rep.errors == [] and rep.warnings == []
