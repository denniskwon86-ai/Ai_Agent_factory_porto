"""★★★ 조직 변경 감사 — **누가 권한을 바꿨는지 남는다.**

## 왜 이 파일이 생겼나 (2026-07-31)

최상위 부서 `hq` 의 이름이 `본사` → `해킹` 으로 바뀌어 있었다. 사용자가 "보안 테스트하다 걸린
것 아니냐"고 물었고, **답할 수 없었다.** 확인된 것은 시각(2026-07-27 23:39:53, 부서 생성 2분 뒤)
뿐이었다:

- 부서 표의 버전 이력은 *무엇이* 바뀌었는지만 담는다(v1 본사 → v2 해킹).
- 감사로그에는 조직 변경이 **한 줄도 없었다** — 기록 대상이 아니었다.
- 그날은 권한 강제가 켜지기 전(7/30 가동)이라 **누구든, 익명으로도** 부서를 개명할 수 있었다.

⚠️ 이 공백이 다른 감사 항목보다 무겁다. 부서·역할·조직범위는 **"누가 무엇을 볼 수 있는가"를
  정의하는 값**이다. 접근 기록을 아무리 남겨도, 그 값의 변경 이력이 없으면 "그때 그 사람에게 왜
  권한이 있었는가"를 설명할 수 없다.

## 왜 코어에서 기록하는가(라우트가 아니라)

그 개명은 화면이 아니라 시드/스크립트 경로였을 가능성이 크다. 라우트에만 기록을 붙이면
**바로 그 경로가 계속 기록되지 않는다.** 그래서 `OrgDirectory` 안에서 남기고, 라우트는 행위자만
전달한다. `actor` 가 비면 `anonymous` 로 남는다 — 기록을 건너뛰지 않는다.
"""
import json

import pytest

from core.enterprise_context import audit
from core.org_directory import OrgDirectory


@pytest.fixture
def org(tmp_path, monkeypatch):
    """감사로그를 tmp 로 돌린 조직도. conftest 가 이미 격리하지만 여기서 경로를 직접 읽는다."""
    log = tmp_path / "audit.jsonl"
    monkeypatch.setattr(audit, "_LOG_PATH", str(log), raising=False)
    o = OrgDirectory(db_path=str(tmp_path / "org.db"))
    o._log = log                      # 테스트 편의 — 읽기 전용으로만 쓴다
    return o


def _events(org, event=None):
    if not org._log.exists():
        return []
    rows = [json.loads(l) for l in org._log.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r for r in rows if not event or r["event"] == event]


# ── 부서 ──────────────────────────────────────────────────────────────────
def test_dept_creation_is_recorded(org):
    """★ 부서 생성이 남는다 — 누가 조직을 만들었는지가 첫 기록이어야 한다."""
    org.create_department("battery", "배터리소재", scope_node_id="MNM_BATTERY", actor="kim")
    ev = _events(org, "ORG_STRUCTURE_CHANGED")
    assert len(ev) == 1
    assert ev[0]["actor"] == "kim" and ev[0]["resource_id"] == "battery"
    assert "MNM_BATTERY" in ev[0]["detail"]


def test_rename_records_before_and_after(org):
    """★★★ **이 파일이 존재하는 이유.** 개명은 "무엇에서 무엇으로"와 **누가**를 함께 남긴다.

    이 한 줄이 있었다면 `본사 → 해킹` 의 행위자를 즉시 알 수 있었다."""
    org.create_department("hq", "본사", actor="seed")
    org.update_department("hq", name_ko="해킹", actor="tester")
    ev = _events(org, "ORG_STRUCTURE_CHANGED")[-1]
    assert ev["actor"] == "tester"
    assert "본사" in ev["detail"] and "해킹" in ev["detail"], "변경 전후가 없으면 추적이 안 된다"
    assert "v1→v2" in ev["reason"]


def test_scope_change_is_recorded(org):
    """★★ 조직 범위 변경은 **노출 범위 변경**이다 — 개명보다 무겁다."""
    org.create_department("plant", "공장", scope_node_id="MNM_COPPER", actor="a")
    org.update_department("plant", scope_node_id="MNM_BATTERY", actor="b")
    ev = _events(org, "ORG_STRUCTURE_CHANGED")[-1]
    assert "MNM_COPPER" in ev["detail"] and "MNM_BATTERY" in ev["detail"]


def test_unidentified_change_is_still_recorded_as_anonymous(org):
    """★★★ 행위자가 없어도 **기록은 남는다.**

    ⚠️ "식별되지 않으면 기록하지 않는다"는 가장 나쁜 조합이다 — 익명 경로로 조직이 바뀐 사실
      자체가 조사 대상인데, 그 경로만 로그에서 사라진다. 실제로 그렇게 사라졌다."""
    org.create_department("ghost", "유령", actor="")
    ev = _events(org, "ORG_STRUCTURE_CHANGED")[-1]
    assert ev["actor"] == audit.ANONYMOUS


def test_dept_retirement_is_recorded(org):
    """★ 부서 폐지는 그 부서 사람들의 권한을 없앤다 — 남지 않으면 원인을 찾을 수 없다."""
    org.create_department("gone", "사라질부서", actor="a")
    assert org.retire_department("gone", actor="admin") is True
    ev = _events(org, "ORG_STRUCTURE_CHANGED")[-1]
    assert ev["actor"] == "admin" and "폐지" in ev["reason"]


# ── 사용자 ────────────────────────────────────────────────────────────────
def test_admin_grant_is_recorded(org):
    """★★★ `is_admin` 부여는 **전권 부여**다. 이 한 줄이 나중에 "왜 이 사람이 전부 볼 수
    있었나"의 유일한 답이 된다."""
    org.upsert_user("boss", "보스", is_admin=True, actor="kim")
    ev = _events(org, "ORG_USER_CHANGED")[-1]
    assert ev["actor"] == "kim" and ev["resource_id"] == "boss"
    assert "admin" in ev["detail"]


def test_role_change_is_recorded(org):
    """★★ 역할이 곧 열람·쓰기 범위다(상위 역할은 하위로 상속된다)."""
    org.create_department("qa", "품질", actor="a")
    org.upsert_user("lee", "이", actor="a")
    org.set_user_roles("lee", {"qa": "manager"}, actor="admin")
    ev = _events(org, "ORG_USER_CHANGED")[-1]
    assert "qa=manager" in ev["detail"] and ev["actor"] == "admin"


def test_role_removal_says_what_it_means(org):
    """★ 전부 해제도 남는다 — 빈 dict 를 "변경 없음"으로 흘리면 권한 회수가 조용해진다."""
    org.create_department("qa", "품질", actor="a")
    org.upsert_user("lee", "이", actor="a")
    org.set_user_roles("lee", {"qa": "viewer"}, actor="a")
    org.set_user_roles("lee", {}, actor="admin")
    ev = _events(org, "ORG_USER_CHANGED")[-1]
    assert "전부 해제" in ev["detail"]


def test_user_retirement_is_recorded(org):
    """★★ 폐지는 권한 회수다 — "이 계정이 왜 안 되나"에 답할 근거가 된다."""
    org.upsert_user("tmp", "임시", actor="a")
    assert org.delete_user("tmp", actor="admin") is True
    ev = _events(org, "ORG_USER_CHANGED")[-1]
    assert ev["actor"] == "admin" and "폐지" in ev["reason"]


def test_audit_failure_never_breaks_the_change(org, monkeypatch):
    """★★★ 감사 기록 실패가 **조직 변경을 죽이면 안 된다.**

    권한 인프라의 부작용이 기능을 멈추면 그 인프라가 꺼진다 — 이 저장소가 이미 여러 번 택한
    판단이다(로그는 실패를 소리 내어 알리고, 변경은 진행된다)."""
    def _boom(*a, **kw):
        raise RuntimeError("디스크 꽉 찼다")
    monkeypatch.setattr(audit, "record", _boom)
    d = org.create_department("still", "그래도생성", actor="a")
    assert d["dept_id"] == "still", "감사 실패로 부서 생성이 취소되면 안 된다"
