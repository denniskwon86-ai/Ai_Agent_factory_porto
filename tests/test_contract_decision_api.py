"""★★★ 컴파일러가 **사람에게 넘긴 결정**을 사람이 실제로 내릴 수 있다. (2026-08-26 실측)

## ⚠️⚠️ 무엇이 있었나 — 막다른 길이 둘

계약 컴파일러는 스스로 못 정하는 두 가지를 사람에게 넘긴다. 실측에서 둘 다 나왔고,
**둘 다 정할 방법이 없었다**:

    ① 「사용자 결정이 필요한 요구가 …(지원 대기) 있습니다」
       → `pending_decisions` 를 만드는 곳만 있고 **읽는 곳이 0곳**이었다(전수 확인).
    ② 「데이터셋 «x» 를 «A» 와 «B» 가 다르게 선언했습니다 — 사람이 정해야 합니다」
       → 고를 화면도 API 도 없었다.

★ 합산기의 거절은 **옳다**(자동 병합은 조용한 권한 확대다). 잘못된 것은 「정해야 한다」고
  말해 놓고 정할 자리를 안 준 것이다 — 그것은 통제가 아니라 교착이다.
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.routes.factory_control as fc
from tests import org_seed

BASE = "/api/v1/factory/P1"


@pytest.fixture
def client(tmp_path, monkeypatch, enforced_org):
    import config

    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)
    monkeypatch.chdir(tmp_path)
    import core.paths as _paths
    monkeypatch.setattr(_paths, "PROJECTS_DIR", str(tmp_path / "projects"))
    app = FastAPI()
    app.include_router(fc.router)
    c = TestClient(app)
    r = c.post("/api/v1/factory/projects", json={"project_id": "P1"},
               headers=_as(org_seed.ADMIN))
    assert r.status_code == 200, r.text
    return c


def _as(user):
    return {"X-Factory-User": user}


def _ws(tmp_path):
    import os
    ws = os.path.join("projects", "P1")
    os.makedirs(os.path.join(ws, "contracts", "drafts"), exist_ok=True)
    return ws


def _wbs(ws, tasks):
    import os
    with open(os.path.join(ws, "00_wbs_master_plan.json"), "w", encoding="utf-8") as f:
        json.dump({"tasks": tasks}, f, ensure_ascii=False)


def _draft(ws, task_id, draft):
    import os
    with open(os.path.join(ws, "contracts", "drafts", f"{task_id}.json"),
              "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False)


def _read_draft(ws, task_id):
    import os
    with open(os.path.join(ws, "contracts", "drafts", f"{task_id}.json"),
              encoding="utf-8") as f:
        return json.load(f)


def _dataset(name="rows", action="read", key="PRC-02"):
    return {"name": name, "label": "행", "purpose": "조회",
            "allowed_actions": [action],
            "fields": [{"name": "id", "type": "string", "required": False,
                        "classification": "INTERNAL"}],
            "data_role": "ENTERPRISE_ACTUAL", "source_intent": "ENTERPRISE_READ",
            "duplicate_entry_policy": "DENY_IF_AUTHORITATIVE_SOURCE_EXISTS",
            "enterprise_contract_key": key}


# ══════════════════════════════════════════════════════════════════════════
# ① 무엇이 사람을 기다리는가 — 고를 값까지 함께 준다
# ══════════════════════════════════════════════════════════════════════════

def test_미지원_능력이_고를_값과_함께_보인다(client, tmp_path):
    """★★★ 목록 없이 「정하라」고 하면 무엇을 적어야 하는지 모른다 — 그러면 이 API 도
    다시 막다른 길이다."""
    ws = _ws(tmp_path)
    _wbs(ws, [{"task_id": "T-1", "artifact_kind": "APP"}])
    _draft(ws, "T-1", {"app_class": "departmental", "datasets": [_dataset()],
                       "capability_intents": [
                           {"intent_id": "i1", "requirement_ref": "FR-1",
                            "capability": "file.upload"}]})

    r = client.get(f"{BASE}/contract-decisions/pending", headers=_as(org_seed.ADMIN))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["pending"] is True
    caps = d["capability_decisions"]
    assert len(caps) == 1
    assert caps[0]["capability"] == "file.upload"
    assert caps[0]["choices"], "고를 수 있는 값을 안 줬다"
    assert caps[0]["reason"], "왜 지원되지 않는지 안 알려 준다"


def test_데이터셋_충돌이_무엇이_다른지와_함께_보인다(client, tmp_path):
    """⚠️ 이름만 주면 사람은 두 초안을 손으로 열어 비교해야 하고, 그러면 아무도 안 고른다."""
    ws = _ws(tmp_path)
    _wbs(ws, [{"task_id": "T-1", "artifact_kind": "APP"},
              {"task_id": "T-2", "artifact_kind": "APP"}])
    _draft(ws, "T-1", {"app_class": "departmental",
                       "datasets": [_dataset(action="read")], "capability_intents": []})
    _draft(ws, "T-2", {"app_class": "departmental",
                       "datasets": [_dataset(action="create")], "capability_intents": []})

    r = client.get(f"{BASE}/contract-decisions/pending", headers=_as(org_seed.ADMIN))
    d = r.json()["data"]
    conf = d["dataset_conflicts"]
    assert len(conf) == 1, d
    assert set(conf[0]["choices"]) == {"T-1", "T-2"}, "어느 쪽을 고를지 안 준다"
    assert "allowed_actions" in conf[0]["differences"], "무엇이 다른지 안 준다"


def test_정할_것이_없으면_pending_이_거짓이다(client, tmp_path):
    """⚠️ 「없다」와 「못 읽었다」를 같게 만들지 않는다."""
    ws = _ws(tmp_path)
    _wbs(ws, [{"task_id": "T-1", "artifact_kind": "APP"}])
    _draft(ws, "T-1", {"app_class": "departmental", "datasets": [_dataset()],
                       "capability_intents": [
                           {"intent_id": "i1", "capability": "app_data.read"}]})

    r = client.get(f"{BASE}/contract-decisions/pending", headers=_as(org_seed.ADMIN))
    assert r.json()["data"]["pending"] is False


# ══════════════════════════════════════════════════════════════════════════
# ② 결정이 **초안에 착지**하는가 — 컴파일러의 입력이 초안이다
# ══════════════════════════════════════════════════════════════════════════

def test_능력_결정이_초안에_남는다(client, tmp_path):
    """★★★ 별도 «결정 표» 를 만들고 컴파일러가 안 보면 아무 일도 일어나지 않는다."""
    ws = _ws(tmp_path)
    _wbs(ws, [{"task_id": "T-1", "artifact_kind": "APP"}])
    _draft(ws, "T-1", {"app_class": "departmental", "datasets": [_dataset()],
                       "capability_intents": [
                           {"intent_id": "i1", "capability": "file.upload"}]})

    r = client.post(f"{BASE}/contract-decisions/resolve", headers=_as(org_seed.ADMIN),
                    json={"task_id": "T-1", "capability": "file.upload",
                          "decision": "WAIT", "rationale": "다음 분기로 미룬다"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["draft_applied"] is True

    saved = _read_draft(ws, "T-1")
    assert saved["capability_intents"][0]["user_decision"] == "WAIT"

    #: ★ 정하고 나면 더 이상 사람을 기다리지 않아야 한다.
    again = client.get(f"{BASE}/contract-decisions/pending", headers=_as(org_seed.ADMIN))
    assert again.json()["data"]["pending"] is False


def test_데이터셋_충돌이_한쪽_기준으로_통일된다(client, tmp_path):
    """★ 이긴 선언을 **통째로 복사**한다. 칸을 골라 합치면 그것이 곧 자동 병합이고,
    합산기가 거절한 바로 그 행위다."""
    ws = _ws(tmp_path)
    _wbs(ws, [{"task_id": "T-1", "artifact_kind": "APP"},
              {"task_id": "T-2", "artifact_kind": "APP"}])
    _draft(ws, "T-1", {"app_class": "departmental",
                       "datasets": [_dataset(action="read")], "capability_intents": []})
    _draft(ws, "T-2", {"app_class": "departmental",
                       "datasets": [_dataset(action="create")], "capability_intents": []})

    r = client.post(f"{BASE}/contract-decisions/resolve", headers=_as(org_seed.ADMIN),
                    json={"dataset_key": "rows", "winner_task_id": "T-1"})
    assert r.status_code == 200, r.text

    assert _read_draft(ws, "T-2")["datasets"][0]["allowed_actions"] == ["read"]
    assert client.get(f"{BASE}/contract-decisions/pending",
                      headers=_as(org_seed.ADMIN)).json()["data"]["pending"] is False


def test_결정이_원장에_남는다(client, tmp_path):
    """⚠️⚠️ 초안 파일은 롤백·재생성으로 바뀐다. 「누가 언제 무슨 근거로 이 능력을
    줄이기로 했나」는 **덮어쓸 수 없는 곳**에 있어야 한다."""
    ws = _ws(tmp_path)
    _wbs(ws, [{"task_id": "T-1", "artifact_kind": "APP"}])
    _draft(ws, "T-1", {"app_class": "departmental", "datasets": [_dataset()],
                       "capability_intents": [
                           {"intent_id": "i1", "capability": "file.upload"}]})

    r = client.post(f"{BASE}/contract-decisions/resolve", headers=_as(org_seed.ADMIN),
                    json={"task_id": "T-1", "capability": "file.upload",
                          "decision": "REDUCE", "rationale": "첨부 없이 만든다"})
    #: ⚠️ 원장은 **격리된 싱글턴**을 그대로 쓴다(conftest 가 임시 경로로 돌려 놨다).
    #:   여기서 새 인스턴스를 만들면 운영 경로로 떨어진다.
    from core.decision_ledger import decision_ledger

    ev = decision_ledger.get_event(r.json()["data"]["event_id"])
    assert ev["event_type"] == "APP_CONTRACT_DECISION_RECORDED"
    #: ★ 「무엇을」 결정했는지가 절반이다 — 대상이 못박혀야 한다.
    assert ev["subject_type"] == "app_contract_capability"
    assert ev["subject_id"] == "file.upload"
    assert ev["decision"] == "REDUCE"
    assert ev["actor_id"] == org_seed.ADMIN
    assert "첨부 없이" in ev["rationale"]


# ══════════════════════════════════════════════════════════════════════════
# ③ 통제 — 아무 값이나 받지 않는다
# ══════════════════════════════════════════════════════════════════════════

def test_금지된_능력에_호스트_기능_요청을_받지_않는다(client, tmp_path):
    """★★★ `PROHIBITED` 에서 고를 수 있는 것은 `REDUCE` 뿐이다. 받아 두면 컴파일러가
    그 자리에서 버리고, 결정은 원장에만 남아 **「분명히 정했는데 또 물어본다」**가 된다."""
    ws = _ws(tmp_path)
    _wbs(ws, [{"task_id": "T-1", "artifact_kind": "APP"}])
    _draft(ws, "T-1", {"app_class": "departmental", "datasets": [_dataset()],
                       "capability_intents": [
                           {"intent_id": "i1", "capability": "auth.local_login"}]})

    r = client.post(f"{BASE}/contract-decisions/resolve", headers=_as(org_seed.ADMIN),
                    json={"task_id": "T-1", "capability": "auth.local_login",
                          "decision": "REQUEST_HOST_FEATURE"})
    assert r.status_code == 422
    assert "REDUCE" in r.json()["detail"], "무엇을 고를 수 있는지 알려 주지 않는다"


def test_둘을_한_요청에_담지_못한다(client, tmp_path):
    """⚠️ 절반 성공이 생기면 무엇이 반영됐는지 아무도 모른다."""
    _ws(tmp_path)
    r = client.post(f"{BASE}/contract-decisions/resolve", headers=_as(org_seed.ADMIN),
                    json={"task_id": "T-1", "capability": "file.upload",
                          "decision": "WAIT", "dataset_key": "rows",
                          "winner_task_id": "T-1"})
    assert r.status_code == 422


def test_아무것도_지정하지_않으면_거절한다(client, tmp_path):
    _ws(tmp_path)
    r = client.post(f"{BASE}/contract-decisions/resolve", headers=_as(org_seed.ADMIN),
                    json={})
    assert r.status_code == 422


@pytest.mark.parametrize("user", [org_seed.VIEWER_A, org_seed.MEMBER_B, org_seed.NO_DEPT])
def test_쓰기_권한이_없으면_결정할_수_없다(client, tmp_path, user):
    """⚠️⚠️ 이 결정은 **앱이 갖는 권한**을 바꾼다 — 읽기 권한으로 정할 수 있으면 안 된다."""
    ws = _ws(tmp_path)
    _wbs(ws, [{"task_id": "T-1", "artifact_kind": "APP"}])
    _draft(ws, "T-1", {"app_class": "departmental", "datasets": [_dataset()],
                       "capability_intents": [
                           {"intent_id": "i1", "capability": "file.upload"}]})

    r = client.post(f"{BASE}/contract-decisions/resolve", headers=_as(user),
                    json={"task_id": "T-1", "capability": "file.upload",
                          "decision": "WAIT"})
    assert r.status_code in (401, 403), r.text
    #: ★ 막았으면 **아무것도 바뀌지 않아야** 한다. 422 를 차단으로 세지 않는다.
    assert not _read_draft(ws, "T-1")["capability_intents"][0].get("user_decision")


def test_없는_태스크는_404_다(client, tmp_path):
    """⚠️ 「초안이 없다」와 「값이 틀렸다」를 같은 코드로 답하면 호출부가 구분 못 한다."""
    _ws(tmp_path)
    r = client.post(f"{BASE}/contract-decisions/resolve", headers=_as(org_seed.ADMIN),
                    json={"task_id": "없음", "capability": "file.upload",
                          "decision": "WAIT"})
    assert r.status_code == 404
