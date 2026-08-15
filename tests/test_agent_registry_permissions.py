"""★★★ [D-017 §9 P0] 에이전트·워크플로우·스킬 API 권한 봉합.

설계 §2 가 실측한 결함을 여기서 못 박는다.

## 무엇이 열려 있었나

- `GET/PUT /agents`, `POST /agents/reset` 에 **`current_principal` 의존성이 아예 없었다.**
  익명 사용자가 전역 에이전트 구성을 읽고, 덮어쓰고, 초기화할 수 있었다.
- 템플릿 목록·상세·복사·저장·삭제도 사용자·조직 문맥을 받지 않았다.
- `POST /ai-recommend/skill` 은 권한 검사 없이 공용 `skills/` 에 직접 썼고, `agent_id` 를
  파일명에 그대로 써서 **경로 구성에 개입할 수 있었으며**, 기존 공용 스킬을 덮어썼다.

## 이 파일이 지키는 경계

★ 화면 메뉴 숨김과 Route Guard 는 **편의**다. URL 을 아는 사람 앞에서 실제로 막는 것은
  서버뿐이고, 그것을 확인하는 것이 이 테스트다(D-017 3단계 중 ③).
"""
import os
import shutil

import pytest
from fastapi.testclient import TestClient

from tests import org_seed


@pytest.fixture()
def client(monkeypatch, seeded_org):
    """권한 강제를 켠 상태의 앱. **끄면 이 테스트는 아무것도 증명하지 못한다.**

    ⚠️⚠️ `org_directory` 는 해석한 스코프를 **캐시한다.** 강제를 켠 상태로 만든 캐시가 남으면
      뒤에 도는 다른 파일의 테스트가 «권한이 강제된 스코프» 를 물려받아 엉뚱하게 실패한다
      (2026-08-04 실측: `test_master_api_routes` 와 `test_planning_engine` 이 단독으로는
      통과하는데 전체 실행에서만 깨졌다). 그래서 **앞뒤로 캐시를 비운다.**
    ★ 내 테스트가 남긴 상태로 남의 테스트를 깨뜨리면, 그 실패는 원인을 찾는 데만 몇 시간이
      걸린다 — 격리는 예의가 아니라 요구사항이다."""
    import config
    from core.org_directory import org_directory
    org_directory._invalidate()
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    from main import app
    try:
        yield TestClient(app)
    finally:
        org_directory._invalidate()


def _as(uid: str):
    return {"X-Factory-User": uid} if uid else {}


# ── 익명·미등록 (설계 §10 보안 1) ─────────────────────────────────────────
@pytest.mark.parametrize("method,path", [
    ("get", "/api/v1/factory/agents"),
    ("get", "/api/v1/factory/templates"),
])
def test_anonymous_cannot_read_global_registry(client, method, path):
    """★★★ 익명 사용자는 에이전트·템플릿 목록을 **읽을 수 없다.**

    ⚠️ 예전에는 의존성 자체가 없어 누구나 전역 구성을 읽었다."""
    r = getattr(client, method)(path, headers=_as(""))
    assert r.status_code in (401, 403), f"{path} 가 익명에게 {r.status_code} 로 열려 있다"


def test_anonymous_cannot_reset_registry(client):
    """★★★ 되돌릴 수 없는 전역 초기화가 익명에게 열려 있으면 안 된다."""
    r = client.post("/api/v1/factory/agents/reset", headers=_as(""))
    assert r.status_code in (401, 403)


def test_unregistered_user_is_refused(client):
    """★★ 등록되지 않은 사용자도 막힌다 — 헤더에 아무 이름이나 넣으면 통과하면 안 된다."""
    r = client.get("/api/v1/factory/agents", headers=_as("nobody@example.com"))
    assert r.status_code in (401, 403)


# ── 일반 사용자 (설계 §4.2) ───────────────────────────────────────────────
def test_member_can_read_but_cannot_overwrite_global(client):
    """★★★ 부서 member 는 읽을 수 있지만 **전역 정의를 덮어쓸 수 없다.**

    ★ 전역 저장은 한 사람의 클릭이 전 사용자·전 프로젝트의 파이프라인을 바꾼다 —
      그래서 설계 §9 P0-3 은 플랫폼 관리자 전용으로 못 박았다."""
    r = client.get("/api/v1/factory/agents", headers=_as(org_seed.AI_ADMIN))
    assert r.status_code == 200, "부서 member 는 읽을 수 있어야 한다"

    body = (r.json() or {}).get("data") or {}
    w = client.put("/api/v1/factory/agents", json=body, headers=_as(org_seed.AI_ADMIN))
    assert w.status_code == 403, "member 가 전역 레지스트리를 덮어쓰면 안 된다"

    z = client.post("/api/v1/factory/agents/reset", headers=_as(org_seed.AI_ADMIN))
    assert z.status_code == 403, "member 가 전역 초기화를 하면 안 된다"


def test_viewer_cannot_create_workflow(client):
    """★★ viewer 는 워크플로우를 만들 수 없다(설계 §4.2)."""
    r = client.post("/api/v1/factory/templates/copy",
                    json={"src_id": "default", "new_id": "viewer_try", "new_name": "x"},
                    headers=_as(org_seed.VIEWER_A))
    assert r.status_code == 403


def test_platform_admin_can_read_global(client):
    r = client.get("/api/v1/factory/agents", headers=_as(org_seed.ADMIN))
    assert r.status_code == 200


# ── 시스템 기본 정의 보호 (설계 §4.2 «복사·버전 승격만») ──────────────────
def test_default_template_cannot_be_deleted(client):
    """★★★ 기본 워크플로우를 지우면 **신규 프로젝트가 만들어지지 않는다.**

    권한과 무관하게 막는다 — 관리자라도 «지울 수 있는 것» 과 «지워도 되는 것» 은 다르다."""
    r = client.delete("/api/v1/factory/templates/default", headers=_as(org_seed.ADMIN))
    assert r.status_code == 400
    assert "복사본" in (r.json() or {}).get("detail", "")


def test_manager_cannot_edit_default_template(client):
    """★★ `default` 는 시스템 기본 정의다. 부서 manager 는 복사해서 쓴다."""
    body = {"agents": [], "version": 1}
    r = client.put("/api/v1/factory/templates/default", json=body,
                   headers=_as(org_seed.AI_ADMIN))
    assert r.status_code in (403, 422), "manager 가 기본 워크플로우를 직접 고치면 안 된다"


# ── 스킬 생성 (설계 §2.3) ─────────────────────────────────────────────────
def test_skill_generation_requires_permission(client):
    """★★ 권한 없이 공용 디렉터리에 파일을 쓰게 두지 않는다."""
    r = client.post("/api/v1/factory/ai-recommend/skill",
                    json={"agent_id": "planner", "agent_name_ko": "기획",
                          "role_description": "x"},
                    headers=_as(org_seed.VIEWER_A))
    assert r.status_code == 403, "viewer 는 스킬 초안을 만들 수 없다"


@pytest.mark.parametrize("bad_id", [
    "../../etc/passwd", "a/b", "a\\b", "..", "with space", "한글", "x" * 65, "",
])
def test_skill_agent_id_is_validated_before_llm(client, bad_id):
    """★★★ [§2.3] `agent_id` 가 **파일 경로가 된다.** 검증을 LLM 호출보다 **먼저** 한다.

    ⚠️ 검증이 뒤에 있으면 잘못된 요청도 LLM 비용을 쓰고, 그 사이 부분 파일이 생길 수 있다.
    ★ 422 를 기대한다 — 권한 문제(403)가 아니라 **입력 형식** 문제다. 둘을 같은 코드로 뭉개면
      사용자는 «권한을 달라» 고 요청하고, 관리자는 이미 있는 권한을 보고 혼란에 빠진다."""
    r = client.post("/api/v1/factory/ai-recommend/skill",
                    json={"agent_id": bad_id, "agent_name_ko": "테스트",
                          "role_description": "x"},
                    headers=_as(org_seed.AI_ADMIN))
    assert r.status_code == 422, f"«{bad_id}» 가 파일명으로 통과했다"


def test_skill_draft_does_not_overwrite_published(client, monkeypatch, tmp_path):
    """★★★ [§2.3] 검토를 거치지 않은 LLM 출력이 **공용 스킬을 덮어쓰지 않는다.**

    ⚠️ 예전에는 `skills/<id>.md` 에 바로 썼다 — 전 프로젝트가 쓰는 스킬이 한 번의 클릭으로
      조용히 바뀌었고, 되돌릴 방법도 없었다."""
    #: ⚠️ 경로는 **상대경로 그대로** 둔다 — 라우트가 `os.path.join("skills", …)` 로 쓰므로
    #:   여기서 격리 경로로 바꾸면 라우트가 «공용 스킬 없음» 으로 보고 시험 의도가 사라진다.
    #:   (공용 파일은 `finally` 에서 지운다.)
    os.makedirs("skills", exist_ok=True)
    published = os.path.join("skills", "canaryskill_skill.md")
    original = "원본 공용 스킬 — 덮어쓰이면 안 된다"
    with open(published, "w", encoding="utf-8") as f:
        f.write(original)

    async def _fake(_self, _state, _prompt, output_mode="json", light=True):
        return '{"role_expanded": "역할", "skill_markdown": "LLM 이 만든 새 내용"}'

    from core.llm_gateway import LLMGateway, _LazyGateway
    monkeypatch.setattr(LLMGateway, "aexecute", _fake, raising=False)
    #: ★★★ **게이트웨이 «생성» 도 막는다.** `aexecute` 만 갈아끼우면 `_LazyGateway._instance()`
    #:   가 진짜 `LLMGateway()` 를 만들고, 그 생성자가 `GOOGLE_API_KEY` 를 요구한다.
    #: ⚠️ 키는 Git 에 없다 — 그래서 이 시험은 **깨끗한 checkout 에서만** 죽었고, 실패 모습은
    #:   「권한 통제가 깨졌다」였지만 원인은 환경 의존이었다. 이 시험이 확인하려는 것은
    #:   「검토 없는 LLM 출력이 공용 스킬을 덮지 않는다」뿐이고 진짜 모델은 필요 없다.
    monkeypatch.setattr(LLMGateway, "__init__", lambda self, *a, **kw: None, raising=False)
    monkeypatch.setattr(_LazyGateway, "_inst", None, raising=False)  # 캐시된 진짜 인스턴스 무시

    draft_dir = os.path.join("skills", "_proposals")
    try:
        r = client.post("/api/v1/factory/ai-recommend/skill",
                        json={"agent_id": "canaryskill", "agent_name_ko": "카나리",
                              "role_description": "x"},
                        headers=_as(org_seed.AI_ADMIN))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["published"] is False
        assert "덮어쓰지 않았습니다" in body["note"]
        # ★ 공용 파일은 **글자 하나 바뀌지 않아야 한다.**
        assert open(published, encoding="utf-8").read() == original
        assert os.path.isdir(draft_dir), "초안은 제안 디렉터리에 남는다"
    finally:
        if os.path.exists(published):
            os.remove(published)
        shutil.rmtree(draft_dir, ignore_errors=True)


# ── 감사 (설계 §9 P0-6) ───────────────────────────────────────────────────
def test_denied_access_is_recorded(client):
    """★★ 거부를 **기록한다.** 기록이 없으면 «누가 무엇을 시도했는가» 를 물을 수 없다."""
    from core.enterprise_context import audit
    before = len(audit.tail(200)) if hasattr(audit, "tail") else None
    client.post("/api/v1/factory/agents/reset", headers=_as(org_seed.VIEWER_A))
    if before is None:
        pytest.skip("감사 조회 헬퍼가 없어 기록 내용을 확인하지 못한다")
    after = audit.tail(200)
    assert len(after) > before, "거부가 감사에 남지 않았다"
