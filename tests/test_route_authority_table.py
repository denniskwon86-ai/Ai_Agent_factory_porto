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
    #: [DAO-15] 연구자료 «추천» — 수집하지 않고 저장하지도 않지만, 표 대조 대상이다.
    #:   ⚠️ 이 목록에 안 넣으면 표에 적은 항목이 «유령»으로 잡힌다(실제로 걸렸다).
    "api.routes.research_control",
    "api.routes.data_preparation_control",
    #: [BDR-7 / G2·G4] 기준선·시뮬레이션·의사결정 — 운영으로 쓰는 계산 경로다.
    "api.routes.baseline_control",
    #: [B2 / M0-3.3] 경로 계산 — 승인된 자료로 경영 판단용 숫자를 내고 안건을 만든다.
    "api.routes.calculation_control",
    #: [DAO-8] 외부 데이터 수집 — 남의 서버를 부르고 격리 DB 에 행을 넣는다.
    #:   ⚠️ 새 라우터는 **만들 때 함께** 이 목록에 넣는다. 나중에 넣으면 그 사이에
    #:     추가된 라우트가 권한 없이 열린다.
    "api.routes.acquisition_control",
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


def _all_routes():
    """등록된 라우트 **전부** — 읽기 포함.

    ⚠️ `_write_routes()` 는 GET 을 뺀다(「쓰기 라우트가 전부 판정됐는가」를 묻기 때문).
      그런데 표는 **읽기도 막을 수 있다** — 관리자 화면의 조회가 그렇다. 표 대조에
      쓰기 목록을 쓰면 정당한 GET 항목이 «유령» 으로 잡힌다."""
    import importlib
    out = set()
    for mod_path in GUARDED_MODULES:
        m = importlib.import_module(mod_path)
        for r in getattr(m.router, "routes", []):
            for meth in sorted(getattr(r, "methods", set()) or set()):
                if meth not in ("HEAD", "OPTIONS"):
                    out.add(f"{meth} {r.path}")
    assert out, "라우트를 하나도 찾지 못했다 — 검사가 헛돌고 있다"
    return out


# ── ① 표에 있는데 라우트가 없다 ─────────────────────────────────────────────
def test_every_table_entry_matches_a_real_route():
    """★ 오타 하나로 통제가 «없는 라우트» 를 막게 되는 것을 잡는다."""
    real = _all_routes()
    ghosts = sorted(set(ra.ROUTE_CAPS) - real)
    assert not ghosts, (
        "표에 있으나 실제 라우트가 아니다(오타이거나 라우트가 옮겨갔다): " + "; ".join(ghosts))


def test_every_exempt_entry_matches_a_real_route():
    real = _all_routes()
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
def client(enforced_org, monkeypatch, tmp_path):
    """조직도 + **권한 강제 ON** 상태의 앱.

    ⚠️⚠️ 종전에는 `ecm_org_seed`·`seeded_org` 를 썼다. 둘 다 `tests/conftest.py` 에 있고,
      **격리 러너는 conftest 를 읽지 않는다**(`verify_data_usage_holds.py` 는 `--noconftest`
      로 돌며 보고서에 `repository_conftest_loaded: false` 를 찍는다). 그래서 이 파일의
      마지막 통제 4건이 「fixture 없음」으로 **ERROR** 였다 — 통제가 틀린 것이 아니라
      **돌지를 못했다.** 안 도는 통제는 없는 통제와 같다.
    ★ `enforced_org` 는 conftest **와** 격리 플러그인(`tests/usage_hold_test_plugin.py`)
      **양쪽에** 있다. 같은 이름으로 두 세계에서 다 돈다.
    ★★★ 그리고 강제를 **정책 파일**로 켠다. 종전의 `monkeypatch.setattr(config,
      "ORG_ENFORCE", True)` 는 제품이 실제로 읽는 `scope_policy` 경로를 지나지 않는다 —
      `api/deps.py` 가 그 사고를 주석으로 남겨 두었다(「같은 뜻의 스위치를 두 곳에서 읽으면
      테스트는 그 불일치를 볼 수 없다」). 이제 시험과 실서버가 같은 스위치를 본다.
    """
    from core.auth import auth_store
    from core.org_directory import org_directory
    #: 앞선 시험이 남긴 해석 캐시를 지운다 — 남으면 이 조직도가 아니라 «앞 조직도» 를 본다.
    org_directory._invalidate()
    #: ⚠️ 인증 저장소도 격리한다. 세션을 «실제로» 만들되 운영 `data/auth.db` 는 건드리지 않는다.
    #:   경로를 바꾸면 `_init()` 이 새 경로로 다시 준비한다(`_ready` 가 옛 경로라 같지 않다).
    monkeypatch.setattr(auth_store, "db_path", str(tmp_path / "auth.db"))
    from main import app
    #: ★★★ 신원은 **제품이 쓰는 길**로 만든다 — 세션 토큰이다.
    #:   ⚠️ `X-Factory-User` 헤더는 `config.ORG_TRUST_HEADER` 가 켜져 있을 때만 먹는 개발용
    #:     문이고 기본값은 False 다. 그 헤더로 신원을 만들면 「막히는지」가 아니라
    #:     「개발 모드에서 막히는지」를 보게 된다(2026-08-09 에 그 스위치로 완주가 위조됐다).
    token = auth_store.create_session(org_seed.VIEWER_A)["token"]

    #: ★ 대조군이 진짜 대조군인지 **먼저** 증명한다. 아래 셋 중 하나라도 어긋나면 403 이
    #:   떠도 그것은 우리가 보려던 이유 때문이 아니다.
    assert auth_store.resolve(token) == org_seed.VIEWER_A, "세션이 그 사용자를 가리키지 않는다"
    scope = org_directory.resolve_scope(org_seed.VIEWER_A)
    assert not scope.unrestricted, (
        "viewer 가 **무제한**이다 — 조직이 안 심겼거나 부트스트랩 상태다. 이 상태에서는 "
        "막히는지 보려는 통제가 애초에 꺼져 있다")
    from core.scope_policy import org_enforce
    assert org_enforce() is True, "권한 강제가 꺼져 있다 — 이 검사는 아무것도 증명하지 못한다"

    c = TestClient(app)
    c.headers.update({"X-Session-Token": token})
    try:
        yield c
    finally:
        org_directory._invalidate()


#: viewer 로 찔러도 **안전한** 라우트만 고른다 — 막히지 않으면 그대로 실행되기 때문이다.
#: ⚠️ `sprint/start`·`supervisor/chat`·`heal` 은 넣지 않는다. LLM 이 나간다.
#: ⚠️ [2026-09-16 변이 실측] **넷 중 셋만 «표» 의 증인이다.**
#:   표에서 항목을 빼 보면 앞의 셋은 곧바로 빨강이 되는데, `programs/.../disable` 은
#:   **그대로 403 이다** — 그 라우트 안에 `_admin(p)` 라는 **자기 판정이 따로 있어서**
#:   표가 없어도 막는다(제품으로서는 이중 방어라 좋은 일이다).
#:   ★ 그래서 그 한 줄은 「viewer 가 막히는가」의 증인이지 「표가 붙어 있는가」의 증인은
#:     아니다. 지우지 않는다 — 막히는지는 여전히 봐야 한다. 대신 **여기 적어 둔다.**
#:     (표 자체의 부착은 위 셋과 `⑤ 라우터에서 표를 떼어 낸다` 변이가 증명한다.)
SAFE_PROBES = [
    ("POST", "/api/v1/factory/projects", {"project_id": "__authority_probe__"}),
    ("PUT", "/api/v1/factory/projects/__authority_probe__/knowledge", {"pack_ids": []}),
    ("DELETE", "/api/v1/factory/library/item/__authority_probe__", None),
    #: ↓ 표 + 라우트 자체 판정(`_admin`) 둘 다 막는다. 위 주석 참조.
    ("POST", "/api/v1/programs/__authority_probe__/disable", {}),
]


@pytest.mark.real_auth
@pytest.mark.parametrize("method,url,body", SAFE_PROBES)
def test_viewer_is_blocked_by_the_table(client, method, url, body):
    """★★★ 봉합 전 실측: 이 호출들이 viewer 에게 **200** 이었다.

    시험 계정 은 viewer 이며 `_ROLE_CAPS` 상 `project.*` 를 하나도 갖지 않는다.

    ★ `real_auth` — `tests/plugin_test_auth.py` 의 principal 주입을 **쓰지 않는다.**
      그 플러그인의 머리말이 정한 세 분류 중 「인증·권한 테스트 → 실제 로그인 +
      X-Session-Token」이 여기다. 주입으로 통과시키면 실제 인증 연결 결함을 숨긴다."""
    r = client.request(method, url, json=body)
    assert r.status_code == 403, (
        f"viewer 에게 {method} {url} 가 {r.status_code} 로 열려 있다 — 표가 붙지 않았거나 "
        f"권한 배정이 비어 있다: {r.text[:200]}")


def test_the_table_declares_the_caps_we_think_it_does():
    """★ **선언 계약**만 고정한다 — 「표가 런타임에 단독으로 막는다」는 증명이 아니다.

    ⚠️ 위 probe 중 `programs/{release_id}/disable` 은 라우트 안의 `_admin` 이 **먼저** 막아,
      표에서 빼도 403 이 그대로다(변이 실측). 그래서 그 경로에 대해서는 probe 가 「표가
      붙어 있는가」의 증인이 되지 못한다 — 대신 **표에 무엇으로 적혀 있는지**를 여기서
      직접 못박는다. 오타·등급 하향이 조용히 들어오는 것은 이걸로 막힌다.
    ★ 런타임 단독 효력은 나머지 세 probe 와 라우터 의존성이 증명한다. 둘을 섞어 부르지 않는다.
    """
    from core.admin_capability import PROJECT_CREATE, PROJECT_EDIT, PROJECT_RELEASE
    expected = {
        "POST /api/v1/factory/projects": (PROJECT_CREATE,),
        "PUT /api/v1/factory/projects/{project_id}/knowledge": (PROJECT_EDIT,),
        "DELETE /api/v1/factory/library/item/{release_id}": (PROJECT_RELEASE,),
        "POST /api/v1/programs/{release_id}/disable": (PROJECT_RELEASE,),
    }
    for key, caps in expected.items():
        assert key in ra.ROUTE_CAPS, f"표에서 사라졌다: {key}"
        assert ra.ROUTE_CAPS[key] == caps, (
            f"{key} 의 권한이 바뀌었다: {ra.ROUTE_CAPS[key]} != {caps}")


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
