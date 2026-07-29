# ==========================================
# 기준정보 API — **라우트가 실제로 도달하는가**
#
# 함수 단위 테스트는 전부 통과하는데 HTTP 로는 404 가 나는 결함이 있었다:
# `/records/duplicates` 를 `/records/{master_code}` **아래**에 정의해서 경로 변수가
# 'duplicates' 를 master_code 로 잡아먹었다. FastAPI 는 정의 순서로 매칭한다.
#
# 로직 테스트로는 절대 안 잡히는 계열이라 라우팅만 따로 본다.
# ==========================================
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def client():
    import main
    return TestClient(main.app)


# 경로 변수 라우트에 잡아먹히기 쉬운 **고정 경로**들. 새 고정 경로를 추가하면 여기에도 넣는다.
_LITERAL_ROUTES = [
    "/api/v1/master/records/duplicates",
    "/api/v1/master/scope-bindings/coverage",
    "/api/v1/master/scope-bindings/allowed?scope_node_id=node_none",
    "/api/v1/master/documents/quality",
    "/api/v1/catalog/assets/search?q=x",       # `/assets/{asset_id}` 에 잡아먹히기 쉽다
    "/api/v1/catalog/governance/gaps",
    "/api/v1/glossary/terms/expand?q=x",       # `/terms/{term_id}` 에 잡아먹히기 쉽다
    "/api/v1/glossary/match?term=x",
    "/api/v1/lineage/impact?node_type=master&node_id=x",
    "/api/v1/lineage/edges?node_type=master&node_id=x",
    "/api/v1/contracts/evaluate",              # `/{contract_id}` 에 잡아먹히기 쉽다
    "/api/v1/catalog/governance/coverage",
    "/api/v1/external/readiness",
    "/api/v1/external/indicators",
    "/api/v1/shadow/summary",      # `/runs/{run_id}` 에 잡아먹히기 쉽다
    "/api/v1/shadow/runs",
    "/api/v1/workspace/promotions",
    "/api/v1/workspace/promotions/gate?release_id=x",  # `/{...}` 없지만 순서 회귀 방지
    "/api/v1/workspace/shares",
    "/api/v1/readiness/checklist?release_id=x",
    "/api/v1/readiness/impact?node_type=master&node_id=x",
    "/api/v1/readiness/rollbacks",
]


@pytest.mark.parametrize("path", _LITERAL_ROUTES)
def test_literal_route_is_not_shadowed_by_path_param(client, path):
    """★★ 고정 경로가 `/{id}` 라우트에 잡아먹히지 않는가.

    404 면 라우팅이 잘못된 것이다 — 여기서 통과하는 다른 상태코드(200/403 등)는 라우트가
    도달했다는 뜻이므로 허용한다. 이 테스트가 보는 것은 **도달 여부**뿐이다."""
    r = client.get(path)
    assert r.status_code != 404, (
        f"{path} 가 404 다. 경로 변수 라우트(`/{{...}}`)보다 **위에** 정의했는지 확인하라 — "
        f"FastAPI 는 정의 순서로 매칭한다. 응답: {r.text[:200]}")


def test_duplicates_returns_expected_shape(client):
    d = client.get("/api/v1/master/records/duplicates").json()["data"]
    assert set(d) >= {"candidates", "total", "high_confidence", "note"}
    for c in d["candidates"]:
        assert c["confidence"] in ("high", "medium", "low")
        assert len(c["codes"]) == 2 and c["suggested_action"]


def test_coverage_returns_expected_shape(client):
    d = client.get("/api/v1/master/scope-bindings/coverage").json()["data"]
    assert set(d) >= {"total_records", "bound_records", "exposed_records",
                      "exposed_codes", "coverage_ratio"}
    assert d["bound_records"] + d["exposed_records"] == d["total_records"]


def test_approval_without_identity_is_401_not_a_bare_400(client):
    """★★ 조직 강제 모드가 꺼져 있으면(기본값) `user_id` 가 비어 승인이 **아예 불가능**했다.

    가짜 승인자를 만들어 넣으면 아무도 승인하지 않은 것이 승인된 것처럼 기록되므로 거절이
    맞다. 다만 이유 없는 400 이면 사용자는 무엇을 해야 할지 모른다 — 401 + 해결 방법."""
    t = client.post("/api/v1/glossary/terms",
                    json={"canonical_name": "__route_test_term__"},
                    headers={"X-User-Id": "tester"})
    assert t.status_code in (200, 409)
    tid = (t.json()["data"]["term_id"] if t.status_code == 200
           else next(x["term_id"] for x in client.get("/api/v1/glossary/terms").json()["data"]
                     if x["canonical_name"] == "__route_test_term__"))
    try:
        r = client.post(f"/api/v1/glossary/terms/{tid}/approve")
        assert r.status_code == 401
        assert "X-User-Id" in r.json()["detail"], "해결 방법을 알려줘야 한다"
        assert client.post(f"/api/v1/glossary/terms/{tid}/approve",
                           headers={"X-User-Id": "tester"}).status_code == 200
    finally:
        client.delete(f"/api/v1/glossary/terms/{tid}", headers={"X-User-Id": "tester"})


def test_record_path_param_still_works(client):
    """고정 경로를 위로 올린 뒤에도 `/{master_code}` 가 정상이어야 한다(반대 방향 회귀)."""
    r = client.get("/api/v1/master/records/__NO_SUCH_CODE__")
    assert r.status_code == 404 and "존재하지 않는" in r.json()["detail"]
