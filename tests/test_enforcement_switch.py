"""★★★ 조직 권한 강제 여부를 **한 곳에서만** 읽는다.

## 무엇이 잘못돼 있었나 (2026-08-08 실측)

강제 여부의 정본은 `data/scope_policy.json` 이고, 그것이 **코드 기본값을 이긴다**
(2026-07-30 사용자 지시로 `org_enforce=true` 로 켜져 있다). `api.deps._enforced()` 가 그
계약을 담고 있고, 그 주석은 「판정 함수들이 **모두 여기서** 같은 답을 얻는다」고 못박는다.

그런데 `current_principal` 한 줄만 `config.ORG_ENFORCE`(=False)를 **직접** 읽고 있었다.
그래서 정책으로 강제를 켠 실서버에서도 **거기서는 익명이 통과**했다. 뒤에 `require_caps` 가
있는 라우트는 거기서 막혔지만, **이 401 에만 기대던 라우트는 열려 있었다** — 실측 당시
`current_principal` 을 쓰면서 다른 관문이 없는 라우트가 5개 파일 34개였다.

## ⚠️⚠️ 단위 테스트가 이것을 **구조적으로 못 봤다**

기존 테스트들은 `monkeypatch.setattr(config, "ORG_ENFORCE", True)` 로 **코드 기본값을 직접**
켠다. 그러면 저 줄이 정상 동작하는 것처럼 보이고 실제로 초록이었다
(`test_capabilities_needs_identification` 이 401 을 단언하며 통과했다). 실서버는 정책 파일로
켜므로 **다른 세계**가 된다.

★ 그래서 이 파일은 **코드 기본값을 끈 채 정책만 켠다.** 같은 뜻의 스위치를 두 곳에서 읽으면
  테스트는 그 불일치를 볼 수 없다 — 두 경로를 갈라서 확인하는 것만이 답이다.
"""
import json

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.deps import Principal, current_principal


def _app():
    """`current_principal` **만** 붙은 라우트. 다른 관문이 없으므로 이 401 이 유일한 통제다."""
    app = FastAPI()

    @app.get("/probe")
    async def probe(p: Principal = Depends(current_principal)):
        return {"user_id": p.user_id, "unrestricted": p.scope.unrestricted}

    return TestClient(app)


@pytest.fixture()
def policy(monkeypatch, tmp_path, ecm_org_seed, seeded_org):
    """정책 파일을 tmp 로 격리하고 «쓰는» 헬퍼를 준다.

    ⚠️ `conftest` 가 이미 `_POLICY_PATH` 를 격리하지만, 여기서는 **값을 직접 써야** 하므로
      경로를 다시 잡고 캐시를 비운다(`resolve_scope` 는 해석 결과를 캐시한다).

    ⚠️⚠️ `seeded_org` 가 필요하다 — 조직이 0건이면 `is_bootstrap()` 이 **전원 무제한**을
      돌려주므로, 강제를 켜도 401 이 나오지 않는다. 그러면 이 파일은 「스위치가 동작한다」를
      확인하지 못한 채 통과하거나 뒤집힌다."""
    import config
    from core import scope_policy
    from core.org_directory import org_directory

    path = tmp_path / "scope_policy.json"
    monkeypatch.setattr(scope_policy, "_POLICY_PATH", str(path), raising=False)

    def write(value):
        if value is None:
            if path.exists():
                path.unlink()
        else:
            path.write_text(json.dumps({"org_enforce": value}), encoding="utf-8")
        org_directory._invalidate()

    org_directory._invalidate()
    try:
        yield write, config, monkeypatch
    finally:
        org_directory._invalidate()


def test_policy_file_turns_enforcement_on_even_when_the_code_default_is_off(policy):
    """★★★ **이것이 실서버의 상태였다** — 정책은 켜져 있고 코드 기본값은 꺼져 있다.

    이 조합에서 익명이 통과하면, 그 401 에만 기대던 라우트가 전부 열린다."""
    write, config, mp = policy
    mp.setattr(config, "ORG_ENFORCE", False, raising=False)
    write(True)
    r = _app().get("/probe")
    assert r.status_code == 401, (
        "정책이 강제를 켰는데 익명이 통과했다 — `current_principal` 이 코드 기본값을 보고 있다")


def test_policy_file_can_also_turn_enforcement_off(policy):
    """★ 끄는 것도 정책이 이긴다. 한 방향만 따르면 「켤 수는 있는데 끌 수 없는」 스위치가 된다 —
    그때 문제가 생기면 되돌리는 방법이 배포뿐이다."""
    write, config, mp = policy
    mp.setattr(config, "ORG_ENFORCE", True, raising=False)
    write(False)
    assert _app().get("/probe").status_code == 200


def test_code_default_still_applies_when_no_policy_is_set(policy):
    """★ 정책 파일이 없으면 코드 기본값을 쓴다 — 새 환경에서 강제가 임의로 켜지지 않는다."""
    write, config, mp = policy
    write(None)
    mp.setattr(config, "ORG_ENFORCE", True, raising=False)
    assert _app().get("/probe").status_code == 401
    mp.setattr(config, "ORG_ENFORCE", False, raising=False)
    from core.org_directory import org_directory
    org_directory._invalidate()
    assert _app().get("/probe").status_code == 200


def test_identified_user_passes_even_under_enforcement(policy):
    """★★ 강제는 **익명**을 막는 것이지 사용자를 막는 것이 아니다. 여기서 식별된 사용자까지
    막으면 그 다음 관문(`require_caps`)이 «권한 없음» 을 말할 기회가 사라지고, 사용자는
    「로그인하라」는 답만 반복해서 받는다 — 이미 로그인했는데."""
    write, config, mp = policy
    mp.setattr(config, "ORG_ENFORCE", False, raising=False)
    # ⚠️ [P0-1C] 이 테스트가 보려는 것은 «강제가 익명만 막는가» 이고, 신원을 어떻게 얻는지는
    #   곁가지다. 헤더 신뢰 기본값이 False 로 내려갔으므로 **이 테스트에서만** 되켠다
    #   (승인된 3분류의 셋째 칸: 레거시 스위치 테스트). `_app()` 은 자체 앱이라 플러그인의
    #   principal override 가 닿지 않는다 — 그래서 override 대신 스위치로 해결한다.
    mp.setattr(config, "ORG_TRUST_HEADER", True, raising=False)
    write(True)
    r = _app().get("/probe", headers={"X-Factory-User": "hikwon@lsmnm.com"})
    assert r.status_code == 200 and r.json()["user_id"] == "hikwon@lsmnm.com"


def test_unrestricted_bootstrap_passes_even_under_enforcement(policy):
    """★★★ 조직을 **세우기 전**에는 강제가 켜져 있어도 통과해야 한다.

    `unrestricted` 는 「조직 미도입 또는 부트스트랩」이라는 뜻이다(`AccessScope` 계약). 여기까지
    막으면 조직을 만들 화면 자체가 열리지 않아 **아무도 조직을 세울 수 없고**, 정책을 켠 사람도
    되돌릴 수 없다 — 스스로를 잠그는 상태다. `current_principal` 의 주석이 그 이유를 적어 두었다.

    ⚠️ 이 계약은 **변이 검사로 발견됐다.** `scope.unrestricted` 검사를 지우는 변이가 테스트를
      **통과해 버렸다** — 즉 주석은 있는데 그것을 지키는 검사가 없었다. 주석은 계약을 설명할
      뿐 강제하지 못한다."""
    write, config, mp = policy
    mp.setattr(config, "ORG_ENFORCE", False, raising=False)
    write(True)

    from core.org_directory import AccessScope, org_directory
    mp.setattr(org_directory, "resolve_scope",
               lambda uid: AccessScope(user_id=uid, unrestricted=True))
    r = _app().get("/probe")
    assert r.status_code == 200, "조직을 세우기 전인데 강제가 전 API 를 막았다"
    assert r.json()["unrestricted"] is True


def test_deps_does_not_read_the_config_flag_directly_anymore(policy):
    """★★ 회귀 방지 — **소스에 직접 참조가 남아 있지 않은지** 본다.

    ⚠️ 행동 테스트만으로는 부족하다. 새 라우트나 새 판정이 다시 `config.ORG_ENFORCE` 를 직접
      읽으면 그 경로만 조용히 다른 답을 얻고, 그 상태는 오늘처럼 **실서버에서만** 드러난다."""
    import inspect

    import api.deps as deps
    src = inspect.getsource(deps.current_principal)
    #: ⚠️ **주석은 제외하고 본다.** 이 함수의 주석에는 「`config.ORG_ENFORCE` 를 직접 읽지
    #:   않는다」는 설명이 일부러 들어 있다 — 그 문장까지 걸면 테스트가 «왜 그러면 안 되는지를
    #:   적어 둔 것» 을 위반으로 잡는다. 검사 대상은 **실행되는 코드**다.
    code = "\n".join(line.split("#", 1)[0] for line in src.splitlines())
    assert "ORG_ENFORCE" not in code, (
        "`current_principal` 이 코드 기본값을 다시 직접 읽는다 — `_enforced()` 를 쓸 것")
    assert "_enforced()" in code, "강제 판정이 공용 함수를 지나지 않는다"


# ── 같은 유형 ② 만료일: **판정과 표시가 갈라져 있었다** ───────────────────
#
# ★★★ `ORG_ENFORCE` 와 똑같은 모양의 결함이 만료일에도 있었다(2026-08-08 훑기에서 발견).
#   만료일의 정본도 정책 저장소이고 관리자가 화면에서 바꾼다. `scoping.policy_deadline()` 이
#   그것을 읽는데, **두 곳이 코드 상수 `LEGACY_GRANDFATHER_UNTIL` 을 직접 읽고 있었다**:
#     · `scope_contract.legacy_pending()` — 이행 목록의 `deadline`·`default_deadline`
#     · `master_data` 관문 A 안내 문구
#
#   ⚠️ 그래서 **만료 «판정» 은 정책을 따르고 «표시» 는 코드 상수를 따랐다.** 관리자가 만료일을
#     미루면 사람들은 화면의 옛 날짜로 일정을 잡고, 앞당기면 **적힌 날짜보다 먼저 데이터가
#     사라진다.** 「언제까지 봐주는가」를 틀리게 말하는 이행 목록은 이행을 방해한다.
def test_transition_list_shows_the_deadline_that_is_actually_enforced(policy, monkeypatch):
    """★★★ 화면에 적히는 기한과 실제로 강제되는 기한은 **같아야 한다.**"""
    write, config, mp = policy
    from core import scope_policy
    from core.enterprise_context.scoping import is_expired, policy_deadline

    #: 정책으로 만료일을 앞당긴다 — 코드 상수(2026-12-31)와 다른 값이어야 의미가 있다.
    import json as _json
    path = scope_policy._POLICY_PATH
    with open(path, "w", encoding="utf-8") as f:
        _json.dump({"legacy_grandfather_until": "2026-01-31"}, f)

    assert policy_deadline() == "2026-01-31", "정책이 만료일을 이기지 못한다"

    #: 표시 쪽(이행 목록)이 같은 값을 쓰는가 — 행별 만료일이 없는 자원 기준.
    from core.scope_contract import ScopeContract
    from core.master_data import master_data
    out = ScopeContract(master_data).legacy_pending()
    assert out["default_deadline"] == "2026-01-31", (
        "이행 목록이 코드 상수를 보여준다 — 판정은 정책을 따르는데 표시는 아니다")

    #: 그리고 판정도 같은 값이어야 한다(둘이 갈라지면 데이터가 말없이 사라진다).
    assert is_expired({"scope_type": "LEGACY_UNSCOPED"}, today="2026-02-01") is True
    assert is_expired({"scope_type": "LEGACY_UNSCOPED"}, today="2026-01-01") is False


def test_row_deadline_still_wins_over_the_policy(policy):
    """★ 행에 적힌 `effective_to` 는 전역 정책을 이긴다 — 부서마다 정리 속도가 다른데 만료일이
    하나뿐이면 **가장 느린 부서 때문에 전체를 미루게** 된다(`legacy_deadline` 머리말).

    ⚠️ 이 계약을 표시 쪽이 손으로 다시 계산하고 있었다 — 이제 `legacy_deadline(row)` 한 곳을
      쓴다. 두 곳에 적으면 한쪽만 고쳐졌을 때 목록의 기한과 실제 만료가 어긋난다."""
    write, config, mp = policy
    from core import scope_policy
    from core.enterprise_context.scoping import legacy_deadline
    import json as _json
    with open(scope_policy._POLICY_PATH, "w", encoding="utf-8") as f:
        _json.dump({"legacy_grandfather_until": "2026-01-31"}, f)

    assert legacy_deadline({"effective_to": "2027-06-30"}) == "2027-06-30"
    assert legacy_deadline({}) == "2026-01-31"


def test_no_module_reads_the_deadline_constant_directly(policy):
    """★★ 회귀 방지 — **정책이 있는 값을 코드 상수로 읽는 모듈이 다시 생기지 않는지.**

    ⚠️ 상수 자체는 폴백으로 필요하므로 `scoping`·`scope_policy` 는 제외한다. 그 둘이 정본이고,
      나머지가 상수를 직접 읽으면 그 경로만 정책을 무시한다 — 오늘 두 곳이 그랬다."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    allowed = {"scoping.py", "scope_policy.py"}
    offenders = []
    for p in (root / "core").rglob("*.py"):
        if p.name in allowed:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            code = line.split("#", 1)[0]
            if "LEGACY_GRANDFATHER_UNTIL" in code:
                offenders.append(f"{p.relative_to(root)}:{i}")
    assert not offenders, (
        "만료일 코드 상수를 직접 읽는 곳이 있다 — `policy_deadline()`/`legacy_deadline(row)` 를 "
        f"쓸 것: {offenders}")
