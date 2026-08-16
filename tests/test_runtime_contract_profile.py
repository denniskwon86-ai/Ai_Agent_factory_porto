"""★★★ [I-4 §3 · 4단계 P0-5] 계약 절차의 **영속 opt-in** 경계.

이 시험이 전제하는 것: **조직도를 쓰지 않는다.** 프로젝트 생성은 `_is_test_runtime()`
이 검증 샌드박스 문맥을 자동 주입하므로 권한 경계 시험이 아니고, 여기서 보는 것은
「어느 프로젝트가 계약 절차를 타는가」 하나다.

⚠️⚠️ 이 파일이 지키는 것은 한 문장이다 — **기존 프로젝트에 소급 적용되지 않는다.**
  진행 중 프로젝트에 계약 노드가 끼면 `completed_agents` 순서 전제와 체크포인터
  상태가 어긋나고, 그 결함은 **재개할 때에야** 드러난다. 그때는 원인을 찾기 어렵다.
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.routes.factory_control as fc
from core import wbs_artifact_kind as ak


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import core.paths as _paths
    monkeypatch.setattr(_paths, "PROJECTS_DIR", str(tmp_path / "projects"))
    app = FastAPI()
    app.include_router(fc.router)
    return TestClient(app)


# ── 기본값 ───────────────────────────────────────────────────────────────
def test_untouched_meta_has_no_profile(tmp_path):
    """★ 명시하지 않고 쓰면 `""`. **여기서 `v1` 이 나오면 전 프로젝트가 소급된다.**"""
    fc._write_project_meta(str(tmp_path), "default")
    meta = json.loads((tmp_path / "project_meta.json").read_text(encoding="utf-8"))
    assert meta["runtime_contract_profile"] == ""
    assert fc._read_project_runtime_contract_profile(str(tmp_path)) == ""


def test_legacy_meta_without_the_key_reads_as_off(tmp_path):
    """⚠️ 이미 디스크에 있는 메타에는 이 키가 **없다.** 없는 것을 켜짐으로 읽으면
    기존 프로젝트 전부가 다음 스프린트부터 새 절차를 탄다."""
    (tmp_path / "project_meta.json").write_text(
        json.dumps({"template_id": "default", "owner_user_id": "u"}), encoding="utf-8")
    assert fc._read_project_runtime_contract_profile(str(tmp_path)) == ""


def test_unreadable_meta_reads_as_off(tmp_path):
    """⚠️ 다른 fail-closed 자리와 **반대 방향**이다. 손상된 메타를 켜짐으로 읽으면
    고장난 기존 프로젝트가 재개하는 순간 새 절차를 탄다 — 가장 나쁜 조합이다."""
    (tmp_path / "project_meta.json").write_text("{망가진 JSON", encoding="utf-8")
    assert fc._read_project_runtime_contract_profile(str(tmp_path)) == ""
    assert fc._read_project_runtime_contract_profile(str(tmp_path / "없는폴더")) == ""


@pytest.mark.parametrize("raw", ["v2", "V1.0", "1", True, {"v": 1}, "  "])
def test_unknown_profile_value_reads_as_off(tmp_path, raw):
    """알 수 없는 프로필로 도는 프로젝트를 만들지 않는다."""
    (tmp_path / "project_meta.json").write_text(
        json.dumps({"runtime_contract_profile": raw}), encoding="utf-8")
    assert fc._read_project_runtime_contract_profile(str(tmp_path)) == ""


# ── 보존 계약 ────────────────────────────────────────────────────────────
def test_profile_survives_a_meta_update_that_does_not_mention_it(tmp_path):
    """★★★ 템플릿만 바꾸는 호출부가 계약 프로필을 날리면, 진행 중이던 계약 절차가
    **조용히 꺼지고** 그 프로젝트는 계약 없이 계속 돈다. 소유권·문맥 필드가 같은
    이유로 보존 대상인 것과 같다."""
    fc._write_project_meta(str(tmp_path), "default", owner_user_id="u",
                           runtime_contract_profile=ak.PROFILE_V1)
    assert fc._read_project_runtime_contract_profile(str(tmp_path)) == "v1"

    fc._write_project_meta(str(tmp_path), "marketing")      # 프로필을 안 넘긴다
    assert fc._read_project_runtime_contract_profile(str(tmp_path)) == "v1"
    assert fc._read_project_template(str(tmp_path)) == "marketing"


def test_profile_survives_even_when_every_other_field_is_supplied(tmp_path):
    """★★★ 보존 목록에 프로필이 **실제로 들어 있는지**를 뚫는다.

    ⚠️ 앞 시험은 이것을 못 잡는다 — 소유권 필드를 하나라도 비워 두면 그것 때문에
      기존 메타를 읽어 오고, 프로필이 보존 목록에 없어도 **덤으로** 살아남기
      때문이다. 변이 검사에서 이 자리만 놓쳤다.
    ★ 그래서 여기서는 **다른 모든 필드를 명시**해 기존 메타를 읽을 이유를 없앤 뒤,
      프로필 하나만 빼고 부른다. 보존 목록에서 빠지는 순간 값이 사라진다."""
    fc._write_project_meta(str(tmp_path), "default", owner_user_id="u",
                           runtime_contract_profile=ak.PROFILE_V1)

    fc._write_project_meta(
        str(tmp_path), "marketing", "default", "react_app",
        knowledge_pack_ids=[], master_domains=[], mcp_live_grounding=False,
        owner_dept_id="", owner_user_id="u", visibility="dept", nature="",
        forked_from={}, tenant_id="tenant_default", enterprise_scope_id="",
        entity_mode="REAL", blueprint_id="",
        # runtime_contract_profile 만 넘기지 않는다
    )
    assert fc._read_project_runtime_contract_profile(str(tmp_path)) == "v1"


def test_a_legacy_project_is_not_switched_on_by_an_update(tmp_path):
    """⚠️ 반대 방향도 지킨다 — 꺼진 프로젝트가 갱신 한 번으로 켜지면 안 된다."""
    fc._write_project_meta(str(tmp_path), "default", owner_user_id="u")
    fc._write_project_meta(str(tmp_path), "marketing")
    assert fc._read_project_runtime_contract_profile(str(tmp_path)) == ""


# ── 신규 생성 경로만 켠다 ────────────────────────────────────────────────
def test_new_project_is_created_with_the_contract_profile_on(client, tmp_path):
    r = client.post("/api/v1/factory/projects", json={"project_id": "P1"})
    assert r.status_code == 200, r.text
    meta = json.loads((tmp_path / "projects" / "P1" / "project_meta.json")
                      .read_text(encoding="utf-8"))
    assert meta["runtime_contract_profile"] == "v1", (
        "신규 프로젝트는 계약 절차를 켠 채로 시작한다 — 이 경로 하나가 경계 전부다")


# ── 서버가 부여한다 ──────────────────────────────────────────────────────
def test_client_supplied_profile_is_discarded(client, tmp_path):
    """★★★ 클라이언트가 실어 보낸 프로필을 그대로 쓰면, 손으로 만든 요청이나 오래
    열린 브라우저가 **진행 중 프로젝트에 계약 절차를 켤 수 있다.**

    ⚠️ `schema_version` 을 서버가 부여하는 것과 같은 이유다 — 상태를 바꾸는 권한이
      클라이언트에 있으면, 그 경로는 언젠가 반드시 쓰인다."""
    ws = tmp_path / "projects" / "LEGACY"
    ws.mkdir(parents=True)
    fc._write_project_meta(str(ws), "default", owner_user_id="u")   # 프로필 꺼짐
    assert fc._read_project_runtime_contract_profile(str(ws)) == ""

    seen = {}

    async def _capture(task_id, payload, ws_root):
        seen.update(payload)

    #: ⚠️ 실행은 태우지 않는다 — 여기서 보려는 것은 **오케스트레이터에 넘어간 값**이고,
    #:   진짜로 돌리면 LLM 이 나간다.
    import unittest.mock as _mock
    with _mock.patch.object(fc.orchestrator, "start_sprint", _capture):
        r = client.post("/api/v1/factory/LEGACY/sprint/start",
                        json={"task_id": "PLANNING_1",
                              "project_state_payload": {
                                  "runtime_contract_profile": "v1",
                                  "project_name": "LEGACY"}})
    assert r.status_code == 200, r.text
    assert seen.get("runtime_contract_profile") == "", (
        "클라이언트가 보낸 v1 이 살아남았다 — 진행 중 프로젝트가 소급 적용된다")


def test_server_injects_v1_for_a_project_that_has_it(client, tmp_path):
    """★ 반대 방향 — 켜진 프로젝트는 클라이언트가 비워 보내도 서버가 채운다."""
    r = client.post("/api/v1/factory/projects", json={"project_id": "P2"})
    assert r.status_code == 200, r.text

    seen = {}

    async def _capture(task_id, payload, ws_root):
        seen.update(payload)

    import unittest.mock as _mock
    with _mock.patch.object(fc.orchestrator, "start_sprint", _capture):
        client.post("/api/v1/factory/P2/sprint/start",
                    json={"task_id": "PLANNING_1",
                          "project_state_payload": {"runtime_contract_profile": "",
                                                    "project_name": "P2"}})
    assert seen.get("runtime_contract_profile") == "v1"
