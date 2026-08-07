"""[D-019] 비용·품질 로그의 조직 축 — **부서 id 와 조직 노드를 함께** 싣는다.

실측(2026-08-07): `data/llm_call_log.jsonl` 1,133건의 부서 귀속률이 **0%** 였다.
원인은 값이 아니라 배선이었다 — `ProjectState.owner_dept_id` 는 읽는 곳이 3군데인데
(비용 텔레메트리·품질 텔레메트리·RAG 부서 필터) **주경로에서 채우는 곳이 0군데**였다.

이 파일이 지키는 것은 세 가지다.

1. `start_sprint` 가 권위 원본(`project_meta.json`)에서 소유권을 주입한다 —
   `template_id` 와 **같은 패턴**. 프론트 state 가 stale 해도 진실원본이 이긴다.
2. 조직 노드는 **병기**이지 대체가 아니다. `owner_dept_id` 에 node_id 를 넣으면
   `knowledge_base` 의 부서 필터가 `get_department(node_id)` → None → 매칭 0건이 되어
   **과거사례 주입이 오류 없이 조용히 끊긴다.** 그 회귀를 여기서 막는다.
3. 못 푼 것을 **추측해 채우지 않는다.** 추측이 한 번 맞으면 그 뒤로 아무도 검증하지 않고,
   틀리면 다른 사업부의 비용으로 집계된다.
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.routes.factory_control as fc
from core import org_operations as oo


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # ⚠️ 작업공간 경로는 절대경로로 고정돼 있다(`core/paths.py`) — cwd 만 옮기면 격리되지
    #   않고 테스트가 제품 `projects/` 에 프로젝트를 만든다.
    import core.paths as _paths
    monkeypatch.setattr(_paths, "PROJECTS_DIR", str(tmp_path / "projects"))
    app = FastAPI()
    app.include_router(fc.router)
    return TestClient(app)


@pytest.fixture
def org(tmp_path, monkeypatch):
    """격리된 조직 디렉터리.

    ⚠️ `org_directory` 싱글턴의 `db_path` 는 **절대경로**라 `chdir` 로 격리되지 않는다
      (conftest 도 `master_data` 만 돌리고 이쪽은 돌리지 않는다). 명시적으로 돌리지 않으면
      이 테스트가 **운영 조직도에 의존**해 폴더에 따라 다른 결과를 낸다."""
    from core.org_directory import org_directory
    monkeypatch.setattr(org_directory, "db_path", str(tmp_path / "org.db"), raising=False)
    monkeypatch.setattr(org_directory, "_scope_cache", {}, raising=False)
    org_directory._init_db()
    return org_directory


# ── ① 부서 → 조직 노드 해석: 모르면 «미상», 추측하지 않는다 ─────────────────────
def test_unmapped_dept_resolves_to_blank_not_a_guess(org):
    """★★★ 이 파일 전체의 이유 중 하나. 빈 값은 «미상» 이고, 추측은 **오귀속**이다."""
    org.create_department("d_nomap", "매핑없는부서")          # scope_node_id 미지정
    assert fc._resolve_scope_node("d_nomap") == ""


def test_unknown_dept_resolves_to_blank(org):
    assert fc._resolve_scope_node("d_ghost") == ""


def test_blank_dept_resolves_to_blank(org):
    assert fc._resolve_scope_node("") == ""
    assert fc._resolve_scope_node(None) == ""


def test_mapped_dept_resolves_to_its_node(org):
    org.create_department("d_batt", "배터리소재", scope_node_id="node_batt")
    assert fc._resolve_scope_node("d_batt") == "node_batt"


def test_directory_failure_does_not_stop_the_sprint(monkeypatch, capsys):
    """⚠️ 조직 축은 계측이다. 계측 장애로 가동을 멈추지 않는다 — 대신 «미상» 으로 남긴다."""
    from core.org_directory import org_directory
    monkeypatch.setattr(org_directory, "get_department",
                        lambda _d: (_ for _ in ()).throw(OSError("db locked")))
    assert fc._resolve_scope_node("d_any") == ""
    assert "db locked" in capsys.readouterr().out


# ── ② start_sprint 가 권위 원본에서 주입한다 ────────────────────────────────
def _capture_sprint(monkeypatch):
    captured = {}

    async def fake_start(task_id, payload, workspace_root):
        captured["payload"] = dict(payload)
        return True

    monkeypatch.setattr(fc.orchestrator, "start_sprint", fake_start)
    return captured


def test_start_sprint_injects_ownership_from_meta(client, tmp_path, monkeypatch, org):
    """페이로드가 비어 있어도 진실원본의 소유권이 실려야 한다 — 이것이 빠져 귀속률이 0% 였다."""
    org.create_department("d_qa", "품질", scope_node_id="node_lsmnm")
    r = client.post("/api/v1/factory/projects", json={"project_id": "PA"})
    assert r.status_code == 200, r.text
    ws = tmp_path / "projects" / "PA"
    fc._write_project_meta(str(ws), "default", owner_dept_id="d_qa",
                           owner_user_id="u1", visibility="dept")

    captured = _capture_sprint(monkeypatch)
    r = client.post("/api/v1/factory/PA/sprint/start",
                    json={"task_id": "PLANNING-1", "project_state_payload": {}})
    assert r.status_code == 200, r.text
    p = captured["payload"]
    assert p["owner_dept_id"] == "d_qa"
    assert p["owner_user_id"] == "u1"
    assert p["owner_scope_node_id"] == "node_lsmnm"


def test_authoritative_source_beats_stale_client_state(client, tmp_path, monkeypatch, org):
    """⚠️ 프론트가 다른 부서를 들고 있어도 진실원본이 이긴다 — `template_id` 와 같은 규칙이다.
    여기서 클라이언트를 이기게 두면 비용이 **보낸 사람 마음대로** 귀속된다."""
    org.create_department("d_real", "실소유", scope_node_id="node_real")
    client.post("/api/v1/factory/projects", json={"project_id": "PB"})
    ws = tmp_path / "projects" / "PB"
    fc._write_project_meta(str(ws), "default", owner_dept_id="d_real", owner_user_id="u1")

    captured = _capture_sprint(monkeypatch)
    r = client.post("/api/v1/factory/PB/sprint/start",
                    json={"task_id": "PLANNING-1",
                          "project_state_payload": {"owner_dept_id": "d_someone_else",
                                                    "owner_scope_node_id": "node_forged"}})
    assert r.status_code == 200, r.text
    assert captured["payload"]["owner_dept_id"] == "d_real"
    assert captured["payload"]["owner_scope_node_id"] == "node_real"


def test_untagged_project_stays_untagged(client, tmp_path, monkeypatch, org):
    """★ 만든 사람을 모르는 프로젝트에 부서를 **채워 넣지 않는다.**
    추정 귀속은 곧 「틀린 부서로 귀속된 비용 통계」이고, 틀린 숫자는 «미상» 보다 나쁘다."""
    client.post("/api/v1/factory/projects", json={"project_id": "PC"})
    captured = _capture_sprint(monkeypatch)
    r = client.post("/api/v1/factory/PC/sprint/start",
                    json={"task_id": "PLANNING-1", "project_state_payload": {}})
    assert r.status_code == 200, r.text
    assert captured["payload"]["owner_dept_id"] == ""
    assert captured["payload"]["owner_scope_node_id"] == ""


def test_ownership_survives_between_sprints(tmp_path):
    """스프린트 사이 유실 방지 — 노드도 같은 대상이다(부서만 남으면 롤업 축이 끊긴다)."""
    assert "owner_scope_node_id" in fc._ACCUMULATED_FIELDS
    (tmp_path / "latest_state.json").write_text(
        json.dumps({"owner_dept_id": "d_x", "owner_scope_node_id": "node_x"}),
        encoding="utf-8")
    out = fc._restore_accumulated_from_disk({}, str(tmp_path))
    assert out["owner_scope_node_id"] == "node_x"


# ── ③ 상태 모델 — 병기이지 대체가 아니다 ────────────────────────────────────
def test_state_carries_both_axes():
    """⚠️ `extra='forbid'` 이므로 선언이 빠지면 소유권을 실은 상태가 ValidationError 로 즉사한다."""
    from state_models import ProjectState
    s = ProjectState(owner_dept_id="d_qa", owner_scope_node_id="node_lsmnm")
    assert s.owner_dept_id == "d_qa" and s.owner_scope_node_id == "node_lsmnm"
    assert ProjectState().owner_scope_node_id == ""


def test_rag_dept_filter_still_keys_on_dept_id():
    """★★★ 회귀 방지. `owner_dept_id` 에 node_id 를 넣으면 이 경로가 **조용히** 0건이 된다
    (`get_department(node_id)` → None → 체인 매칭 0). 오류가 안 나므로 아무도 모른다."""
    import inspect

    import core.knowledge_base as kb
    src = inspect.getsource(kb)
    assert 'getattr(project_state, "owner_dept_id", "")' in src, \
        "부서 필터의 키가 바뀌었다 — 과거사례 주입이 조용히 끊길 수 있다"
    assert "owner_scope_node_id" not in src, \
        "RAG 필터는 조직 노드를 키로 쓰지 않는다(부서 path 체인과 계약이 다르다)"


def test_two_logs_share_the_same_field_name():
    """두 로그가 같은 축으로 붙으려면 필드명이 같아야 한다."""
    import inspect

    import core.llm_gateway as gw
    import core.quality_telemetry as qt
    assert '"owner_scope_node_id"' in inspect.getsource(gw._log_llm_call)
    assert '"owner_scope_node_id"' in inspect.getsource(qt._identity)
    # 체크포인트 경로(dict 상태)에서만 조용히 빠지는 것을 막는다
    assert qt.StateRef({"owner_scope_node_id": "node_x"}).owner_scope_node_id == "node_x"


# ── ④ 집계 — 세는 축은 부서 하나, 노드는 롤업용 ─────────────────────────────
def _rec(**kw):
    base = {"owner_dept_id": "d_qa", "owner_scope_node_id": "node_a",
            "ok": True, "cost_estimate_usd": 0.01}
    base.update(kw)
    return base


def test_counting_axis_stays_dept_not_node():
    """⚠️ node 로 세면 실측상 부서 9개가 한 줄로 뭉친다 — 「(미상) 한 줄」이
    「LS MnM 한 줄」로 바뀔 뿐 부서별 비용은 여전히 없다."""
    u = oo.usage_by_org([_rec(owner_dept_id="d_qa"), _rec(owner_dept_id="d_sales")])
    assert {r["org"] for r in u["orgs"]} == {"d_qa", "d_sales"}


def test_node_is_carried_for_rollup():
    u = oo.usage_by_org([_rec()])
    assert u["orgs"][0]["scope_node_ids"] == ["node_a"]


def test_multiple_nodes_for_one_dept_are_all_kept():
    """조직개편으로 기록 시점이 갈리면 한 부서에 노드가 둘 나온다. 하나를 임의로 고르면
    나머지 기간의 비용이 말없이 다른 조직으로 옮겨간다."""
    u = oo.usage_by_org([_rec(owner_scope_node_id="node_a"),
                         _rec(owner_scope_node_id="node_b")])
    assert u["orgs"][0]["scope_node_ids"] == ["node_a", "node_b"]


def test_missing_node_does_not_invent_one():
    u = oo.usage_by_org([_rec(owner_scope_node_id="")])
    assert u["orgs"][0]["scope_node_ids"] == []


# ── ⑤ 커버리지 — 소급 불가와 기록 누락을 가른다 ──────────────────────────────
def test_pre_field_records_are_counted_separately():
    """★ 「필드가 없던 시기」와 「있는데 안 실린 것」은 **다른 결함**이다. 앞은 어떤 배선을
    고쳐도 되살아나지 않고, 뒤는 고칠 대상이다. 합치면 고칠 수 있는 쪽이 안 보인다."""
    old = {"ok": True, "cost_estimate_usd": 0.01}          # owner_dept_id 키 자체가 없다
    u = oo.usage_by_org([old, _rec(owner_dept_id=""), _rec()])
    cov = u["coverage"]
    assert cov["without_org"] == 2
    assert cov["without_org_pre_field"] == 1
    assert cov["without_org_missing"] == 1
    assert "소급 귀속이 불가능" in cov["note"] and "실리지 않은" in cov["note"]


def test_all_pre_field_says_it_cannot_be_recovered():
    old = {"ok": True}
    note = oo.usage_by_org([old, old])["coverage"]["note"]
    assert "소급 귀속이 불가능합니다" in note


def test_all_missing_points_at_the_recording_path():
    note = oo.usage_by_org([_rec(owner_dept_id="")])["coverage"]["note"]
    assert "기록 경로 점검이 필요합니다" in note


def test_full_attribution_still_says_nothing():
    """⚠️ 문제가 없을 때 경고를 띄우면 다음번 진짜 경고를 아무도 읽지 않는다."""
    assert oo.usage_by_org([_rec()])["coverage"]["note"] == ""
