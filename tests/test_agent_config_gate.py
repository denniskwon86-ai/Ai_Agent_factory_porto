"""★★★ 에이전트 구성·스킬 승인의 노출 통제 (2026-08-04 이관 6/10 실측 결함)

## 무엇이 열려 있었나

익명 요청으로 이것들이 통했다:

- `GET  /api/v1/factory/agents`          → 에이전트 15개 구성 전량
- `PUT  /api/v1/factory/agents`          → 구성 저장(유효한 payload 면 통과)
- `POST /api/v1/factory/agents/reset`    → **200. 레지스트리 파일을 지웠다.**
- `POST /skills/proposals/{id}/approve` → 에이전트 스킬 문서를 실제로 고침

⚠️ 이 레지스트리는 «누가 무엇을 어떤 순서로 하는가»와 **HOTL 중단점**(전문가 개입 지점)을
  정한다. 중단점을 지우면 사람 확인 없이 파이프라인이 끝까지 흐른다 — 자료를 훔치지 않고도
  통제를 무력화하는 경로다. 업무표준(3/10)이 «판정 기준»이었다면 이건 «판정 주체의 구성»이다.

## 이 파일이 지키는 것

읽기는 등록 사용자(관문 A), 쓰기는 데이터 표준 관리자·관리자. 그리고 **초기화가 되돌릴 수
있는지**까지 지킨다 — 권한을 걸어도 권한자가 실수하면 같은 손실이 난다.

⚠️ 파괴적 엔드포인트는 **차단을 확인할 때만** 부른다. 차단되면 아무 일도 일어나지 않으므로
  안전하고, 차단되지 않으면 그 사실 자체가 결함이다. 권한자 경로는 실제 파일을 건드리지 않게
  대역으로 고정한다(실제로 호출해 레지스트리를 날린 사고가 있었다).
"""
import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import Principal, current_principal
from core.org_directory import AccessScope


def _app(monkeypatch, *, enforced=True, user_id="", user=None, scope_kw=None,
         routers=("factory", "skills")):
    import core.org_directory as od
    monkeypatch.setattr(od, "_org_enforce_effective", lambda: enforced)
    monkeypatch.setattr(od.org_directory, "get_user", lambda uid: user)
    app = FastAPI()
    if "factory" in routers:
        import api.routes.factory_control as fc
        app.include_router(fc.router)
    if "skills" in routers:
        import api.routes.skill_control as sc
        app.include_router(sc.router)
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id=user_id,
        scope=AccessScope(user_id=user_id, **(scope_kw or {"unrestricted": False})))
    return app


VALID_PAYLOAD = {
    "id": "default", "name": "기본",
    "agents": [{"id": "A", "name_ko": "가", "role": "역할", "enabled": True}],
    "edges": [],
}


# ── 읽기 ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("uid,user,why", [
    ("", None, "익명"),
    ("ghost@ls", None, "미등록"),
    ("old@ls", {"user_id": "old@ls", "status": "retired"}, "폐지"),
])
def test_agent_config_read_is_blocked(monkeypatch, uid, user, why):
    """구성 조회는 등록 사용자만. 실측에서는 익명에게 에이전트 15개가 나왔다."""
    c = TestClient(_app(monkeypatch, user_id=uid, user=user))
    for path in ("/api/v1/factory/agents", "/api/v1/factory/templates",
                 "/skills/proposals"):
        assert c.get(path).status_code == 403, f"{why} 에게 {path} 가 열려 있다"


def test_agent_config_read_open_for_registered_user(monkeypatch):
    """★ 등록 사용자는 구성을 본다 — 무엇으로 일하는지 못 보면 협업이 안 된다."""
    import core.skill_evolution as se
    monkeypatch.setattr(se.skill_evolution, "list_pending_proposals", lambda: [])
    c = TestClient(_app(
        monkeypatch, user_id="staff@ls", user={"user_id": "staff@ls", "status": "active"},
        scope_kw={"unrestricted": False, "readable_dept_ids": frozenset({"dept-a"})}))
    assert c.get("/api/v1/factory/agents").status_code == 200
    assert c.get("/api/v1/factory/templates").status_code == 200
    assert c.get("/skills/proposals").status_code == 200


# ── 쓰기: 구성을 바꾸는 것은 통제의 핵심이다 ────────────────────────────────
def test_agent_config_writes_require_data_admin(monkeypatch):
    """★★★ 익명·일반 사용자는 구성을 바꾸거나 초기화할 수 없다.

    ⚠️ 여기서 부르는 파괴적 엔드포인트(`reset`)는 **차단되는 것을 확인**하는 용도다.
      403 이면 아무 파일도 건드리지 않는다. 200 이 나오면 그 자체가 결함이다."""
    for uid, user in (("", None),
                      ("staff@ls", {"user_id": "staff@ls", "status": "active"})):
        c = TestClient(_app(
            monkeypatch, user_id=uid, user=user,
            scope_kw={"unrestricted": False, "readable_dept_ids": frozenset({"dept-a"})}))
        assert c.put("/api/v1/factory/agents", json=VALID_PAYLOAD).status_code == 403
        assert c.post("/api/v1/factory/agents/reset").status_code == 403
        assert c.post("/api/v1/factory/agents/restore").status_code == 403
        assert c.post("/api/v1/factory/templates/copy",
                      json={"src_id": "default", "new_id": "x"}).status_code == 403
        assert c.put("/api/v1/factory/templates/x", json=VALID_PAYLOAD).status_code == 403
        assert c.delete("/api/v1/factory/templates/x").status_code == 403


def test_skill_approval_requires_data_admin(monkeypatch):
    """★★★ 승인은 에이전트의 스킬 문서를 **실제로 고친다** — 자격 없는 승인은 관문이 아니다."""
    touched = []
    import core.skill_evolution as se
    monkeypatch.setattr(se.skill_evolution, "apply_approved_update",
                        lambda pid: touched.append(pid) or True)
    monkeypatch.setattr(se.skill_evolution, "reject_proposal",
                        lambda pid: touched.append(pid) or True)
    for uid, user in (("", None),
                      ("staff@ls", {"user_id": "staff@ls", "status": "active"})):
        c = TestClient(_app(
            monkeypatch, user_id=uid, user=user,
            scope_kw={"unrestricted": False, "readable_dept_ids": frozenset({"dept-a"})}))
        assert c.post("/skills/proposals/prop_1/approve").status_code == 403
        assert c.post("/skills/proposals/prop_1/reject").status_code == 403
    assert touched == [], "차단됐는데 스킬 문서를 건드렸다"


def test_llm_recommend_is_not_open_to_anonymous(monkeypatch):
    """★ 추천 라우트는 **LLM 을 호출한다** — 익명에게 열려 있으면 자료를 훔치지 않아도
    회사 예산과 속도 제한을 태우는 남용 경로가 된다."""
    c = TestClient(_app(monkeypatch, user_id="", user=None))
    assert c.post("/api/v1/factory/ai-recommend/pipeline",
                  json={"user_request": "x"}).status_code == 403
    assert c.post("/api/v1/factory/ai-recommend/skill",
                  json={"agent_id": "A", "agent_name_ko": "가",
                        "role_description": "역할"}).status_code == 403


def test_data_admin_can_still_configure(monkeypatch):
    """★ 관리자의 편집은 막지 않는다 — 통제가 운영을 막으면 통제가 꺼진다.

    ⚠️ 실제 파일을 쓰지 않게 저장 함수를 대역으로 고정한다."""
    import core.agent_registry as ar
    saved = {}
    monkeypatch.setattr(ar, "save_registry", lambda reg: saved.update(reg) or reg)
    c = TestClient(_app(
        monkeypatch, user_id="da@ls", user={"user_id": "da@ls", "status": "active"},
        scope_kw={"unrestricted": False, "can_manage_standard": True}))
    r = c.put("/api/v1/factory/agents", json=VALID_PAYLOAD)
    assert r.status_code == 200, r.text
    assert saved.get("agents"), "관리자 편집이 저장 함수에 도달하지 않았다"


# ── 초기화가 되돌릴 수 있는가 ────────────────────────────────────────────
def test_reset_keeps_previous_state(tmp_path, monkeypatch):
    """★★★ [사고 재발 방지] 초기화는 직전 구성을 남긴다.

    종전에는 파일을 그냥 지웠고, 이 파일은 git 에 커밋되지 않는 런타임 산출물이라 형상관리로도
    복원되지 않았다. 즉 초기화 한 번으로 편집이 **영구히** 사라졌다."""
    import core.agent_registry as ar
    reg = tmp_path / "agents_registry.json"
    prev = tmp_path / "agents_registry.prev.json"
    monkeypatch.setattr(ar, "REGISTRY_PATH", str(reg))
    monkeypatch.setattr(ar, "REGISTRY_BACKUP_PATH", str(prev))

    mine = {"id": "default", "name": "내 구성",
            "agents": [{"id": "MINE", "name_ko": "내가 만든 것", "role": "r", "enabled": True}],
            "edges": []}
    reg.write_text(json.dumps(mine, ensure_ascii=False), encoding="utf-8")

    ar.reset_registry()
    assert not os.path.exists(str(reg)), "초기화가 되지 않았다"
    assert os.path.exists(str(prev)), "직전 구성이 보존되지 않았다 — 되돌릴 수 없다"

    restored = ar.restore_registry()
    assert restored is not None
    assert [a["id"] for a in restored["agents"]] == ["MINE"], "복원된 내용이 다르다"


def test_reset_refuses_when_backup_fails(tmp_path, monkeypatch):
    """★★ 백업을 못 남기면 **지우지 않는다.** 복구 수단이 없는 삭제는 하지 않는 편이 낫다."""
    import core.agent_registry as ar
    reg = tmp_path / "agents_registry.json"
    monkeypatch.setattr(ar, "REGISTRY_PATH", str(reg))
    monkeypatch.setattr(ar, "REGISTRY_BACKUP_PATH", str(tmp_path / "no_such_dir" / "p.json"))
    reg.write_text('{"agents": [{"id": "A", "name_ko": "가", "role": "r"}]}', encoding="utf-8")

    with pytest.raises(RuntimeError):
        ar.reset_registry()
    assert os.path.exists(str(reg)), "백업 실패인데 원본을 지웠다"


def test_restore_without_backup_is_none(tmp_path, monkeypatch):
    """되돌릴 것이 없으면 조용히 성공하지 않는다 — 라우트가 404 로 알린다."""
    import core.agent_registry as ar
    monkeypatch.setattr(ar, "REGISTRY_PATH", str(tmp_path / "r.json"))
    monkeypatch.setattr(ar, "REGISTRY_BACKUP_PATH", str(tmp_path / "p.json"))
    assert ar.restore_registry() is None
