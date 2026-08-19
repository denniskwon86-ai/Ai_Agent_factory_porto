"""★★★ 권한 배정표가 **라우터와 어긋나지 않는지** 대조한다.

## 이 파일이 막는 것

표를 만드는 일에는 두 가지 실패가 있고, 둘 다 조용하다.

1. **표에 있는데 라우트가 없다** — 경로를 손으로 적다가 오타가 났거나 라우트가 옮겨갔다.
   이때 통제는 «없는 라우트» 를 막고 있고, 진짜 라우트는 열려 있다.
2. **라우트가 있는데 표에 없다** — 새 쓰기 라우트가 생겼다. 아무도 알려 주지 않는다.

⚠️ 특히 ①이 위험하다. 표가 길수록 «잘 통제되고 있다» 로 보이는데 실제로는 아무것도 막지
  않을 수 있다. 그래서 **양방향으로** 대조한다.

## 그리고 표가 실제로 붙어 있는지

표만 있고 라우터에 의존성이 없으면 아무 일도 일어나지 않는다. 마지막 테스트가
시험 계정(viewer)으로 실제 호출해 **403 이 나오는지** 본다 —
표를 읽었다는 유일한 증거다.

⚠️⚠️ **LLM 을 태우는 라우트는 찌르지 않는다.** 2026-08-07 에 그렇게 해서 실제로 Gemini
  호출이 나갔다(`PROGRESS.md` §G). 여기서는 통제가 **인가 단계에서 막는지**만 보므로,
  막히지 않으면 그대로 실행돼 버린다 — 그래서 안전한 라우트만 고른다.
"""
import pytest
from fastapi.testclient import TestClient

from tests import org_seed

from core import route_authority as ra

#: 표가 다루는 라우터들. 여기 없는 라우터의 쓰기는 이 파일이 검사하지 않는다.
GUARDED_MODULES = [
    "api.routes.factory_control",
    "api.routes.advisor_control",
    "api.routes.program_control",
    "api.routes.connector_control",
    "api.routes.reference_control",
    "api.routes.enterprise_context_control",
    "api.routes.jarvis_control",
    #: [BDR-2] 새 라우터는 **만들 때 함께** 표에 넣는다 — 나중에 넣으면 그 사이에
    #: 추가된 라우트가 권한 없이 열린다.
    "api.routes.data_preparation_control",
    #: [BDR-7 / G2·G4] 기준선·시뮬레이션·의사결정 — 운영으로 쓰는 계산 경로다.
    "api.routes.baseline_control",
]

#: 다른 곳에 이미 판정이 있는 쓰기 라우트를 찾는 표식. `route_authority.EXEMPT` 와 함께 쓴다.
_GUARD_MARKS = ("require_caps", "_require_caps", "assert_can_manage_standard",
                "assert_can_edit_org", "assert_enterprise", "assert_can_write_dept",
                "_assert_may_write", "_assert_may_edit", "project_deletion", "pdel.")


def _write_routes():
    """등록된 쓰기 라우트 전부 — `(키, 소스, 모듈)`."""
    import importlib
    import inspect
    out = []
    for mod_path in GUARDED_MODULES:
        m = importlib.import_module(mod_path)
        for r in getattr(m.router, "routes", []):
            methods = [x for x in sorted(getattr(r, "methods", set()) or set())
                       if x not in ("HEAD", "OPTIONS", "GET")]
            if not methods:
                continue
            try:
                src = inspect.getsource(r.endpoint)
            except Exception:
                src = ""
            for meth in methods:
                out.append((f"{meth} {r.path}", src, mod_path))
    assert out, "쓰기 라우트를 하나도 찾지 못했다 — 검사가 헛돌고 있다"
    return out


# ── ① 표에 있는데 라우트가 없다 ─────────────────────────────────────────────
def test_every_table_entry_matches_a_real_route():
    """★ 오타 하나로 통제가 «없는 라우트» 를 막게 되는 것을 잡는다."""
    real = {k for k, _src, _m in _write_routes()}
    ghosts = sorted(set(ra.ROUTE_CAPS) - real)
    assert not ghosts, (
        "표에 있으나 실제 라우트가 아니다(오타이거나 라우트가 옮겨갔다): " + "; ".join(ghosts))


def test_every_exempt_entry_matches_a_real_route():
    real = {k for k, _src, _m in _write_routes()}
    ghosts = sorted(set(ra.EXEMPT) - real)
    assert not ghosts, "면제 목록에 있으나 실제 라우트가 아니다: " + "; ".join(ghosts)


# ── ② 라우트가 있는데 표에 없다 ─────────────────────────────────────────────
def test_every_write_route_is_decided():
    """★★ 모든 쓰기 라우트가 **셋 중 하나**여야 한다: 표에 있다 · 면제다 · 이미 판정이 있다.

    ⚠️ 「아직 정하지 않았다」는 상태를 허용하지 않는다. 허용하면 새 라우트가 조용히
      «식별만으로 열린» 채 들어온다 — 트랙 H 가 33건이나 쌓인 방식이 그것이다."""
    undecided = []
    for key, src, mod in _write_routes():
        if key in ra.ROUTE_CAPS or key in ra.EXEMPT:
            continue
        if any(mark in src for mark in _GUARD_MARKS):
            continue                     # 라우트 안에 자체 판정이 있다
        undecided.append(f"{key} ({mod.rsplit('.', 1)[-1]})")
    assert not undecided, (
        f"권한이 정해지지 않은 쓰기 라우트 {len(undecided)}개 — `core/route_authority.py` 의 "
        f"표에 넣거나, 라우트 안에서 판정하거나, EXEMPT 에 이유와 함께 올릴 것:\n  "
        + "\n  ".join(undecided))


def test_exempt_entries_carry_a_reason():
    """면제는 **이유와 함께** 만 존재할 수 있다. 빈 이유는 「나중에 보자」의 다른 이름이다."""
    empty = [k for k, why in ra.EXEMPT.items() if not (why or "").strip()]
    assert not empty, "이유 없는 면제: " + "; ".join(empty)


# ── ③ 표가 실제로 붙어 있는가 ───────────────────────────────────────────────
@pytest.fixture()
def client(monkeypatch, ecm_org_seed, seeded_org):
    import config
    from core.org_directory import org_directory
    org_directory._invalidate()
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    from main import app
    try:
        yield TestClient(app)
    finally:
        org_directory._invalidate()


#: viewer 로 찔러도 **안전한** 라우트만 고른다 — 막히지 않으면 그대로 실행되기 때문이다.
#: ⚠️ `sprint/start`·`supervisor/chat`·`heal` 은 넣지 않는다. LLM 이 나간다.
SAFE_PROBES = [
    ("POST", "/api/v1/factory/projects", {"project_id": "__authority_probe__"}),
    ("PUT", "/api/v1/factory/projects/__authority_probe__/knowledge", {"pack_ids": []}),
    ("DELETE", "/api/v1/factory/library/item/__authority_probe__", None),
    ("POST", "/api/v1/programs/__authority_probe__/disable", {}),
]


@pytest.mark.parametrize("method,url,body", SAFE_PROBES)
def test_viewer_is_blocked_by_the_table(client, method, url, body):
    """★★★ 봉합 전 실측: 이 호출들이 viewer 에게 **200** 이었다.

    시험 계정 은 viewer 이며 `_ROLE_CAPS` 상 `project.*` 를 하나도 갖지 않는다."""
    r = client.request(method, url, json=body,
                       headers={"X-Factory-User": org_seed.VIEWER_A})
    assert r.status_code == 403, (
        f"viewer 에게 {method} {url} 가 {r.status_code} 로 열려 있다 — 표가 붙지 않았거나 "
        f"권한 배정이 비어 있다: {r.text[:200]}")


def test_member_may_run_but_not_release():
    """★ 계층을 나눈 이유가 실제로 지켜지는지 — **member 는 돌리지만 게시하지 못한다.**

    ⚠️ 이것을 확인하지 않으면 네 코드가 이름만 다르고 같은 것이 된다."""
    from core.admin_capability import (PROJECT_CREATE, PROJECT_EDIT, PROJECT_RELEASE,
                                       PROJECT_RUN, _ROLE_CAPS)
    member = _ROLE_CAPS["member"]
    assert {PROJECT_CREATE, PROJECT_RUN, PROJECT_EDIT} <= member
    assert PROJECT_RELEASE not in member, "member 가 게시까지 할 수 있다 — 계층이 무너졌다"
    assert not (set((PROJECT_CREATE, PROJECT_RUN, PROJECT_EDIT, PROJECT_RELEASE))
                & _ROLE_CAPS["viewer"]), "viewer 에게 프로젝트 권한이 있다"
