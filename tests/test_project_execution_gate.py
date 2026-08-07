"""★★★ 프로젝트 실행 경로의 자격 통제 (2026-08-04 이관 7/10 실측 결함)

## 무엇이 열려 있었나

`Principal` **조차 없는** 라우트가 8개였고 전부 «실행을 바꾸는» 쓰기였다:

- `POST /{id}/hotl/resume`          → **HOTL 중단점 통과**
- `POST /{id}/sprint/resume-quota`  → 한도로 멈춘 스프린트 재개
- `POST /{id}/sprint/revision`      → 재작업 지시
- `POST /{id}/heal`                 → 자가 치유 실행
- `POST /{id}/wbs/replan`           → 작업 계획 재수립
- `POST /projects/{id}/mega/plan`   → 메가 프로젝트 계획
- `POST /projects/{id}/mega/start_all` → **하위 프로젝트 일괄 실행**(LLM 대량 소모)
- `GET  /{id}/hotl/check`           → 중단 상태 조회

⚠️ 이 중 `hotl/resume` 가 가장 무겁다. 6/10 에서 «HOTL 중단점을 지우려면 관리자 권한이
  필요하다»고 막았는데, **지울 필요도 없이 익명이 그냥 통과시킬 수 있었다.**
  통제 하나를 다른 경로가 무력화하는 전형이고, 그래서 «화면 단위»가 아니라 «경로 단위»로
  훑어야 한다는 것이 이 파일의 존재 이유다.

또한 `GET /projects` 는 소유권 필터가 있었지만 **익명 자체가 통과**했고, 익명이 만든 프로젝트는
소유 부서가 비어 프롬프트 주입 필터가 아예 걸리지 않는다(fail-open). 입구에서 막는다.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import Principal, current_principal
from core.org_directory import AccessScope

PROBE = "__no_such_project_probe__"

#: 실행을 바꾸는 경로. ⚠️ **존재하지 않는 project_id 로만** 부른다 — 통제가 없더라도
#  실제 프로젝트를 건드리지 않는다. 403 이 아니면 그 자체가 결함이다.
#  ⚠️ payload 는 **모델이 요구하는 형태로** 준다. 비워 두면 FastAPI 가 body 검증에서 422 를
#  먼저 내고 자격 검사에 도달하지 않는다 — 그러면 «막혔다»고 잘못 읽는다(실제로 그랬다).
WRITE_PATHS = [
    ("post", f"/api/v1/factory/{PROBE}/hotl/resume", {"task_id": "t1", "feedback": ""}),
    ("post", f"/api/v1/factory/{PROBE}/sprint/resume-quota", {"task_id": "t1"}),
    ("post", f"/api/v1/factory/{PROBE}/sprint/revision", {"feedback": "다시"}),
    ("post", f"/api/v1/factory/{PROBE}/heal", {"error_log": "boom"}),
    ("post", f"/api/v1/factory/{PROBE}/wbs/replan", None),
    ("post", f"/api/v1/factory/projects/{PROBE}/mega/plan", {"initial_idea": "x"}),
    ("post", f"/api/v1/factory/projects/{PROBE}/mega/start_all", None),
]
READ_PATHS = [("get", f"/api/v1/factory/{PROBE}/hotl/check", None)]


def _app(monkeypatch, *, enforced=True, user_id="", user=None, scope_kw=None):
    import api.routes.factory_control as fc
    import core.org_directory as od
    monkeypatch.setattr(od, "_org_enforce_effective", lambda: enforced)
    monkeypatch.setattr(od.org_directory, "get_user", lambda uid: user)
    # ⚠️ 소유권 판정을 대역으로 고정한다. 실제 파일시스템을 읽으면 테스트가 환경에 따라 흔들린다.
    monkeypatch.setattr(fc, "_read_project_ownership", lambda path: {})
    app = FastAPI()
    app.include_router(fc.router)
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id=user_id,
        scope=AccessScope(user_id=user_id, **(scope_kw or {"unrestricted": False})))
    return app


@pytest.mark.parametrize("uid,user,why", [
    ("", None, "익명"),
    ("ghost@ls", None, "미등록"),
    ("old@ls", {"user_id": "old@ls", "status": "retired"}, "폐지"),
])
def test_execution_paths_are_blocked_for_unentitled(monkeypatch, uid, user, why):
    """★★★ 실행을 바꾸는 경로는 자격을 요구한다.

    ⚠️ 종전에는 403 이 아니라 422(payload 검증)·404(프로젝트 없음)가 돌아왔다 —
      즉 **권한 검사를 통과해 본문까지 들어갔다.** 유효한 id 와 payload 만 있으면 통했다."""
    c = TestClient(_app(monkeypatch, user_id=uid, user=user))
    # [2026-08-07] 권한 배정표(`core/route_authority`)가 붙으면서 **익명은 401** 이 된다.
    # ⚠️ 이것은 통제가 약해진 것이 아니라 **이유가 정확해진 것**이다. 이 저장소의 규약이
    #   그렇게 정해져 있다(`api/deps.require_caps` 주석): 401 = «누구인지 밝히십시오»,
    #   403 = «당신에게는 권한이 없습니다». 뭉개면 이미 로그인한 사용자가 또 로그인한다.
    #   미등록·폐지 계정은 **식별은 됐으므로 403 그대로**여야 하고, 아래가 그것을 지킨다.
    ok = (401, 403) if not uid else (403,)
    for method, path, body in WRITE_PATHS + READ_PATHS:
        r = getattr(c, method)(path, json=body) if body is not None else getattr(c, method)(path)
        assert r.status_code in ok, f"{why} 에게 {path} 가 열려 있다(→ {r.status_code})"


def test_hotl_resume_is_denied_for_other_departments(monkeypatch):
    """★★★ 소유 부서가 **기록된** 프로젝트는 그 부서에 쓰기 권한이 있어야 재개할 수 있다.

    ⚠️ 여기서 소유권을 대역으로 **넣어** 확인한다. 소유권이 기록되지 않은 프로젝트는
      `assert_project_writable` 이 통과시키는데(하위호환), 그 관대함이 이 계약을 가려 버린다."""
    import core.org_directory as od
    c = TestClient(_app(
        monkeypatch, user_id="staff@ls", user={"user_id": "staff@ls", "status": "active"},
        scope_kw={"unrestricted": False, "readable_dept_ids": frozenset({"dept-a"}),
                  "writable_dept_ids": frozenset({"dept-a"})}))
    monkeypatch.setattr(od.org_directory, "get_ownership",
                        lambda kind, rid: {"dept_id": "dept-b", "owner_user_id": "other@ls"})
    r = c.post(f"/api/v1/factory/{PROBE}/hotl/resume",
               json={"task_id": "t1", "feedback": ""})
    assert r.status_code == 403, f"다른 부서 소유 프로젝트의 중단점을 통과시켰다(→ {r.status_code})"


def test_unowned_project_stays_permissive_for_identified_users(monkeypatch):
    """★★ **기록된 한계**: 소유권이 없는 프로젝트는 식별된 사용자에게 열려 있다(하위호환).

    ⚠️ 이건 «괜찮다»가 아니라 «지금 이렇다»는 기록이다. 이행 기간에 만들어진 프로젝트를 깨지
      않으려는 조치이고, MDM 의 «바인딩 없으면 통과» 규칙이 유출 창구가 됐던 것과 같은 유형이다.
      → **소유권 미기록 프로젝트 수를 상시 관측해야 한다.** 0 이 되면 이 관대함을 걷어낸다.
      익명·미등록·폐지는 여기서도 막힌다(위 테스트가 지킨다)."""
    import core.org_directory as od
    c = TestClient(_app(
        monkeypatch, user_id="staff@ls", user={"user_id": "staff@ls", "status": "active"},
        scope_kw={"unrestricted": False, "readable_dept_ids": frozenset({"dept-a"}),
                  "writable_dept_ids": frozenset()}))
    monkeypatch.setattr(od.org_directory, "get_ownership", lambda kind, rid: {})
    r = c.post(f"/api/v1/factory/{PROBE}/hotl/resume",
               json={"task_id": "t1", "feedback": ""})
    # ★★★ [2026-08-07 · 이 감지선이 울렸고, 변경은 의도한 것이다]
    #
    #   위 주석은 「의도한 변경이면 이 주석을 고칠 것」이라고 적어 두었다. 고친다.
    #
    #   **소유권 미기록 프로젝트의 관대함은 그대로 두되, 「이 사람이 프로젝트를 돌릴 수 있는
    #   사람인가」를 앞에 세웠다**(`core/route_authority` 표 · `project.run`).
    #   `staff@ls` 는 부서 역할이 없어 그 권한이 없다 — 그래서 이제 403 이다.
    #
    #   ⚠️ 두 판정은 **다른 질문**이고 둘 다 필요하다:
    #     · 「돌릴 수 있는 사람인가」 — 역할에서 나온다(표가 답한다)
    #     · 「이 프로젝트를 돌릴 수 있는가」 — 소유권에서 나온다(하위호환은 여기 남아 있다)
    #   앞의 질문이 없었기 때문에 실측에서 **viewer 가 프로젝트를 지우고 돌릴 수 있었다.**
    #
    #   ★ 실제 사용자에게는 영향이 없다(2026-08-07 실측): manager·member 는 `project.run` 을
    #     갖고 viewer 만 갖지 않는다. 즉 「업무하는 사람이 막히는」 변경이 아니다.
    assert r.status_code == 403, "역할 없는 사용자에게 실행 경로가 열려 있다"

    # 그리고 **역할이 있으면 종전 관대함이 그대로 유지된다** — 이것이 위 관대함의 본체다.
    c2 = TestClient(_app(
        monkeypatch, user_id="member@ls",
        user={"user_id": "member@ls", "status": "active", "roles": {"dept-a": "member"}},
        scope_kw={"unrestricted": False, "readable_dept_ids": frozenset({"dept-a"}),
                  "writable_dept_ids": frozenset()}))
    monkeypatch.setattr(od.org_directory, "get_ownership", lambda kind, rid: {})
    r2 = c2.post(f"/api/v1/factory/{PROBE}/hotl/resume",
                 json={"task_id": "t1", "feedback": ""})
    assert r2.status_code != 403, (
        "소유권 미기록 프로젝트의 하위호환이 사라졌다 — 이행 기간 프로젝트가 깨진다")


def test_project_list_is_blocked_for_anonymous(monkeypatch):
    """★★ 소유권 필터가 있어도 **익명 자체**를 막지 않으면, 미태깅 프로젝트의 하위호환이
    그대로 유출 경로가 된다(«소유권 없음 = 누구에게나 보임»)."""
    c = TestClient(_app(monkeypatch, user_id="", user=None))
    body = c.get("/api/v1/factory/projects").json()
    assert body["data"] == [], "익명에게 프로젝트 목록이 노출됐다"
    assert body.get("blocked_reason"), "0건과 «안 보임»이 구분되지 않는다"


def test_project_creation_requires_identity(monkeypatch):
    """★★★ 익명이 프로젝트를 만들면 소유 부서가 비어 **프롬프트 주입 필터가 걸리지 않는다**
    (fail-open). 즉 «부서 없는 프로젝트를 만들어 남의 부서 산출물을 긁는» 경로가 열린다."""
    c = TestClient(_app(monkeypatch, user_id="", user=None))
    # [2026-08-07] 익명은 이제 **401** 이다 — 위 `test_execution_paths_are_blocked_for_unentitled`
    #   의 주석 참조. 막혔다는 사실은 같고, 사용자가 할 일(«로그인하라»)이 정확해졌다.
    assert c.post("/api/v1/factory/projects",
                  json={"project_id": "x", "initial_idea": "y"}).status_code in (401, 403)
    assert c.post("/api/v1/factory/projects/mega",
                  json={"mega_project_id": "x"}).status_code in (401, 403)


def test_gate_is_transparent_when_enforcement_off(monkeypatch):
    """★★ 강제가 꺼져 있으면 목록을 막지 않는다 — ECM 미도입 흐름의 하위호환 계약.

    ⚠️ 실행 경로는 여기서 확인하지 않는다. `assert_project_writable` 은 강제와 무관한
      소유권 판정이고, 그 계약은 별도 테스트가 지킨다."""
    c = TestClient(_app(monkeypatch, enforced=False, user_id="", user=None))
    body = c.get("/api/v1/factory/projects").json()
    assert not body.get("blocked_reason"), "강제가 꺼졌는데 목록이 막혔다"
