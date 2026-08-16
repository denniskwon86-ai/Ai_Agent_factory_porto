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


# ── 세 상태 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("body,state", [
    (json.dumps({"template_id": "default"}), ak.LEGACY_OFF),          # 키가 없는 옛 메타
    (json.dumps({"runtime_contract_profile": ""}), ak.LEGACY_OFF),    # 명시적 비활성
    (json.dumps({"runtime_contract_profile": "v1"}), ak.V1_ON),
    (json.dumps({"runtime_contract_profile": " V1 "}), ak.V1_ON),
    (json.dumps({"runtime_contract_profile": "v2"}), ak.UNREADABLE),  # 미지원 값
    (json.dumps({"runtime_contract_profile": None}), ak.UNREADABLE),  # 형식 오류
    (json.dumps({"runtime_contract_profile": 1}), ak.UNREADABLE),
    (json.dumps(["목록이 왔다"]), ak.UNREADABLE),                      # 최상위가 객체가 아니다
    ("{망가진 JSON", ak.UNREADABLE),                                   # 파일 손상
])
def test_profile_is_read_as_three_states(tmp_path, body, state):
    """★★★ 「적용 안 함」과 「읽지 못함」은 **다른 사실**이다.

    ⚠️ 둘을 모두 `""` 로 읽으면 신규 `v1` 프로젝트의 메타가 손상되기만 해도
      레거시로 오인되어 계약 통제가 조용히 꺼진다 — **파일 하나를 깨뜨리는 것이
      우회로**가 되고, 그 상태는 오류를 내지 않으므로 아무도 모른다."""
    (tmp_path / "project_meta.json").write_text(body, encoding="utf-8")
    assert fc._read_project_contract_profile_state(str(tmp_path)) == state


def test_missing_meta_is_unreadable_not_legacy(tmp_path):
    """⚠️ 메타가 **없는 것**도 판독 실패다. 모든 생성 경로가 메타를 쓰도록
    fail-closed 된 뒤이므로, 메타가 없다는 것은 「옛날 프로젝트」가 아니라
    「무언가 잘못됐다」는 뜻이다 — 그리고 파일을 지우는 것이 통제를 끄는 가장
    간단한 방법이 되면 안 된다."""
    assert fc._read_project_contract_profile_state(str(tmp_path)) == ak.UNREADABLE
    assert fc._read_project_contract_profile_state(str(tmp_path / "없는폴더")) == ak.UNREADABLE


def test_unreadable_profile_does_not_become_a_value(tmp_path):
    """판독 실패는 `""` 라는 **답**이 되어서는 안 된다 — 호출부가 먼저 막아야 한다."""
    (tmp_path / "project_meta.json").write_text("{망가진", encoding="utf-8")
    assert fc._read_project_runtime_contract_profile(str(tmp_path)) == ""   # 값 자체는 빈 값
    with pytest.raises(Exception) as e:
        fc._assert_contract_profile_readable(str(tmp_path), "P")
    assert getattr(e.value, "status_code", None) == 503


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


def test_corrupted_project_cannot_start_a_sprint(client, tmp_path):
    """★★★ 손상된 메타로는 **가동하지 않는다.**

    ⚠️ 이것을 막지 않으면 신규 `v1` 프로젝트의 메타를 깨뜨리는 것만으로 계약 통제가
      꺼진 채 실행된다. 「레거시 미적용」은 허용하되 「판독 실패」는 허용하지 않는다."""
    r = client.post("/api/v1/factory/projects", json={"project_id": "P3"})
    assert r.status_code == 200, r.text
    (tmp_path / "projects" / "P3" / "project_meta.json").write_text("{깨짐", encoding="utf-8")

    started = {}

    async def _capture(task_id, payload, ws_root):
        started["yes"] = True

    import unittest.mock as _mock
    with _mock.patch.object(fc.orchestrator, "start_sprint", _capture):
        r = client.post("/api/v1/factory/P3/sprint/start",
                        json={"task_id": "PLANNING_1",
                              "project_state_payload": {"project_name": "P3"}})
    assert r.status_code == 503, r.text
    assert not started, "막았다고 하면서 실행이 시작됐다"


def test_corrupted_project_cannot_resume_either(client, tmp_path):
    """⚠️ 시작만 막으면 **재개가 열린 쪽**이 되고, 사용자는 막힌 쪽을 피해 그리로 간다."""
    r = client.post("/api/v1/factory/projects", json={"project_id": "P4"})
    assert r.status_code == 200, r.text
    (tmp_path / "projects" / "P4" / "project_meta.json").write_text("{깨짐", encoding="utf-8")

    resumed = {}

    async def _capture(task_id, feedback, project_id):
        resumed["yes"] = True
        return True

    import unittest.mock as _mock
    with _mock.patch.object(fc.orchestrator, "resume_hotl", _capture):
        r = client.post("/api/v1/factory/P4/hotl/resume",
                        json={"task_id": "PLANNING_1", "feedback": ""})
    assert r.status_code == 503, r.text
    assert not resumed


def test_legacy_project_still_starts(client, tmp_path):
    """★ 판독 실패만 막는다 — **레거시는 그대로 돈다.** 여기가 깨지면 이번 보정이
    「모든 옛 프로젝트를 세운 것」이 된다."""
    ws = tmp_path / "projects" / "OLD"
    ws.mkdir(parents=True)
    (ws / "project_meta.json").write_text(
        json.dumps({"template_id": "default", "owner_user_id": "u"}), encoding="utf-8")

    seen = {}

    async def _capture(task_id, payload, ws_root):
        seen.update(payload)

    import unittest.mock as _mock
    with _mock.patch.object(fc.orchestrator, "start_sprint", _capture):
        r = client.post("/api/v1/factory/OLD/sprint/start",
                        json={"task_id": "PLANNING_1",
                              "project_state_payload": {"project_name": "OLD"}})
    assert r.status_code == 200, r.text
    assert seen.get("runtime_contract_profile") == ""


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
