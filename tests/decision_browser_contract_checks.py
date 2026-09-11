"""Replay exact bodies captured from the real browser form into the actual API router.

Explicit-path checks: selected by the isolated runner with --browser-report;
not collected by the ordinary test_*.py suite.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from test_decision_creation_contract import client, catalog

report = json.loads(Path(os.environ["DECISION_BROWSER_REPORT"]).read_text(encoding="utf-8"))
assert report["passed"] is True and len(report["submissions"]) == 8


@pytest.mark.parametrize("submission", report["submissions"])
def test_exact_browser_request_creates_persisted_case(client, submission):
    http, _, _ = client
    captured = submission["request"]
    response = http.request(captured["method"], urlparse(captured["url"]).path, json=captured["body"])
    assert response.status_code == 200, response.text
    saved = response.json()["data"]
    assert saved["evidence_basis"] == captured["body"]["evidence_basis"]
    assert saved["package"] == captured["body"]["package"]
    assert saved["evidence"]["simulation_binding"]["run_id"] == "sim_server_only"
