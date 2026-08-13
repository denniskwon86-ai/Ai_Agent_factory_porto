"""★★★ [G1-B04] 자원 접근 정책 결정점 — **교집합이 실제 권한이다.**

    요청자 권한 ∩ 지금 고른 문맥 ∩ 자원 범위 ∩ 토큰 전수 대조 ∩ 매니페스트 선언 ∩ 자원 정책

하나라도 비면 거부다. 「대부분 통과했으니 통과」는 없다.

## rev.2 — 교차검토 `[G1-B-P0-REVIEW-75]` 가 지적한 fail-open 을 여기서 잠근다

초판은 **골격**이었고 다섯 곳이 열려 있었다. 각각을 시험으로 세운다.

| 지적 | 무엇이 열려 있었나 | 잠그는 시험 |
|---|---|---|
| 1 | 토큰의 tenant·mode·scope·app_id 가 저장만 되고 판정에 안 쓰였다 | `test_토큰_전수_대조_*` |
| 2 | 토큰이 사용자·세션과 대조되지 않아 재사용 가능 | `test_다른_사람의_증명`·`test_다른_세션의_증명` |
| 3 | `owner_dept_id` 가 비면 허용(D-014 위반) | `test_미바인딩_자원은_*` |
| 4 | 앱 토큰의 READ 는 미선언이어도 허용 | `test_읽기도_선언을_요구한다` |
| 5 | (토큰 저장소 쪽) 해시 저장·성공 사용 감사 | `test_app_capability_token.py` |

⚠️ 판정을 **던지지 않고 돌려준다.** 그래야 화면이 「권한 없음」·「문맥 밖」·「남의 앱 증명」을
  다르게 말할 수 있다.
"""
import pytest

import core.app_policy as ap


class _Scope:
    def __init__(self, read=(), write=(), unrestricted=False):
        self.readable_dept_ids = frozenset(read)
        self.writable_dept_ids = frozenset(write)
        self.unrestricted = unrestricted


def _ctx(**kw):
    base = {"tenant_id": "tenant_default", "entity_mode": "REAL", "scope_node_id": ""}
    base.update(kw)
    return base


#: ★ [rev.2] **범용 범위 계약**과 **앱 전용 사실**을 나눠서 만든다.
#:   온톨로지는 `_res()` 만 쓰고 `_facts()` 를 넘기지 않는다.
def _res(**kw):
    base = dict(tenant_id="tenant_default", entity_mode="REAL", scope_node_id="node_hq",
                owner_user_id="", owner_dept_id="hq", binding_state=ap.BOUND, status="active")
    base.update(kw)
    return ap.ResourceScope(**base)


def _facts(**kw):
    base = dict(app_id="app_1", release_id="rel_1", app_class="departmental",
                declared_capabilities=(ap.READ, ap.WRITE, ap.DELETE, ap.MANAGE))
    base.update(kw)
    return ap.AppResourceFacts(**base)


def _user(**kw):
    base = dict(user_id="u@x", scope=_Scope(read={"hq"}, write={"hq"}), ctx=_ctx(),
                session_id="sess_1", via="session")
    base.update(kw)
    return ap.Subject(**base)


def _app(**kw):
    """앱 증명 주체. 기본은 **전수 대조를 전부 통과하는** 값."""
    tok = dict(actor="u@x", session_id="sess_1", app_id="app_1", release_id="rel_1",
               tenant_id="tenant_default", entity_mode="REAL", scope_node_id="node_hq",
               capabilities=(ap.READ, ap.WRITE, ap.DELETE, ap.MANAGE), expired=False)
    tok.update(kw.pop("token", {}))
    base = dict(user_id="u@x", scope=_Scope(read={"hq"}, write={"hq"}), ctx=_ctx(),
                session_id="sess_1", via="app_token", token=tok)
    base.update(kw)
    return ap.Subject(**base)


# ── 대조군 ────────────────────────────────────────────────────────────────
#
# ⚠️ 이것이 없으면 «전부 거부» 도 초록이 된다. 막히는 것만 보는 검사는 통제를 증명하지 않는다.

@pytest.mark.parametrize("action", list(ap.ACTIONS))
def test_사람이_자기_부서_자료를_다룰_수_있다(action):
    d = ap.decide(_user(), _res(), action)
    assert d.allowed, f"{action} 이 막혔다: {d.reason} {d.message}"


@pytest.mark.parametrize("action", list(ap.ACTIONS))
def test_앱_증명이_전수_대조를_통과하면_허용된다(action):
    d = ap.decide(_app(), _res(), action, app=_facts())
    assert d.allowed, f"{action} 이 막혔다: {d.reason} {d.message}"


def test_모든_판정에_기록_의무가_따라온다():
    """★ [rev.2] 쓰기만 남기면 「누가 무엇을 **읽었나**」에 답할 수 없다 — 그것이 곧
    유출 조사가 불가능한 상태다."""
    assert "audit" in ap.decide(_user(), _res(), ap.READ).obligations
    assert "audit" in ap.decide(_user(), _res(), ap.WRITE).obligations


def test_범용_자원은_앱_사실_없이도_판정된다():
    """★ 온톨로지가 같은 PDP 를 쓸 수 있어야 한다 — `app=None` 경로."""
    assert ap.decide(_user(), _res(), ap.READ, app=None).allowed


# ── 지적 1·2 — 토큰 전수 대조 ─────────────────────────────────────────────

def test_다른_사람의_증명은_거부한다():
    """지적 2 — 초판은 `actor` 를 저장만 하고 보지 않아, 남의 증명을 주워 쓸 수 있었다."""
    d = ap.decide(_app(token={"actor": "someone@x"}), _res(), ap.READ, app=_facts())
    assert not d.allowed and d.reason == ap.DENY_TOKEN_ACTOR_MISMATCH


def test_다른_세션의_증명은_거부한다():
    d = ap.decide(_app(token={"session_id": "sess_OLD"}), _res(), ap.READ, app=_facts())
    assert not d.allowed and d.reason == ap.DENY_TOKEN_SESSION_MISMATCH


def test_세션이_없는_증명도_거부한다():
    """⚠️ 「옛 토큰이라 세션이 없다」를 허용하면 그것이 곧 우회로다."""
    d = ap.decide(_app(token={"session_id": ""}), _res(), ap.READ, app=_facts())
    assert not d.allowed and d.reason == ap.DENY_TOKEN_SESSION_MISMATCH


def test_다른_릴리스의_데이터는_거부한다():
    """★★★ 설계 §7-4 — 「이것 하나로 «앱이 남의 데이터를 읽는» 경로가 원천 차단된다」."""
    d = ap.decide(_app(), _res(), ap.READ, app=_facts(release_id="rel_OTHER"))
    assert not d.allowed and d.reason == ap.DENY_TOKEN_APP_MISMATCH


def test_같은_릴리스라도_다른_앱이면_거부한다():
    """지적 1 — `app_id` 도 본다. release 만 보면 같은 릴리스의 다른 앱이 통과한다."""
    d = ap.decide(_app(), _res(), ap.READ, app=_facts(app_id="app_OTHER"))
    assert not d.allowed and d.reason == ap.DENY_TOKEN_APP_MISMATCH


@pytest.mark.parametrize("tok_kw", [
    {"tenant_id": "tenant_other"},
    {"entity_mode": "VIRTUAL"},
])
def test_다른_회사_실행문맥의_증명은_거부한다(tok_kw):
    """지적 1 — 문맥을 바꿔 같은 증명을 재사용하는 경로를 막는다."""
    d = ap.decide(_app(token=tok_kw), _res(), ap.READ, app=_facts())
    assert not d.allowed and d.reason == ap.DENY_TOKEN_CONTEXT_MISMATCH


def test_증명이_묶인_조직_범위_밖이면_거부한다(monkeypatch):
    """지적 1 — `scope_node_id` 를 판정에 쓴다. 저장만 하면 그 축은 없는 것과 같다."""
    import core.project_visibility as pv
    monkeypatch.setattr(pv, "_scope_is_ancestor", lambda a, n: (False, False))
    d = ap.decide(_app(token={"scope_node_id": "node_other"}), _res(), ap.READ, app=_facts())
    assert not d.allowed and d.reason == ap.DENY_TOKEN_SCOPE_MISMATCH


def test_증명_범위가_상위면_하위_자원을_덮는다(monkeypatch):
    """★ 대조군 — 계층 판정이 «전부 거부» 로 굳지 않았음을 함께 본다."""
    import core.project_visibility as pv
    monkeypatch.setattr(pv, "_scope_is_ancestor", lambda a, n: (True, False))
    assert ap.decide(_app(token={"scope_node_id": "node_parent"}), _res(), ap.READ,
                     app=_facts()).allowed


def test_계층_조회_실패는_거부한다(monkeypatch):
    """⚠️ 조회 실패를 «덮는다» 로 뭉개지 않는다 — 보안 경계에서 실패는 차단 쪽이다."""
    import core.project_visibility as pv
    monkeypatch.setattr(pv, "_scope_is_ancestor", lambda a, n: (False, True))
    d = ap.decide(_app(token={"scope_node_id": "node_parent"}), _res(), ap.READ, app=_facts())
    assert not d.allowed and d.reason == ap.DENY_TOKEN_SCOPE_MISMATCH


def test_토큰에_없는_행동은_거부한다():
    d = ap.decide(_app(token={"capabilities": (ap.READ,)}), _res(), ap.WRITE, app=_facts())
    assert not d.allowed and d.reason == ap.DENY_TOKEN_CAPABILITY


def test_만료된_증명은_거부한다():
    d = ap.decide(_app(token={"expired": True}), _res(), ap.READ, app=_facts())
    assert not d.allowed and d.reason == ap.DENY_TOKEN_EXPIRED


def test_앱_정보_없이_앱_증명을_쓰면_거부한다():
    d = ap.decide(_app(), _res(), ap.READ, app=None)
    assert not d.allowed and d.reason == ap.DENY_TOKEN_APP_MISMATCH


# ── 지적 4 — 읽기도 선언을 요구한다 ───────────────────────────────────────

def test_읽기도_선언을_요구한다():
    """★★★ [rev.2 · 지적 4] 초판은 앱 증명의 READ 를 매니페스트 미선언이어도 허용했다.
    그러면 «선언하지 않은 앱이 데이터를 읽는» 경로가 남는다 — CL-0 감사 지적 D 와 같은 구멍."""
    d = ap.decide(_app(), _res(), ap.READ, app=_facts(declared_capabilities=()))
    assert not d.allowed and d.reason == ap.DENY_MANIFEST_CAPABILITY


def test_레거시_모드를_명시하면_미선언_읽기만_허용한다():
    """⚠️ 하위호환은 **명시**해야 열린다. 기본값으로 열면 그것이 곧 CL-0 이 막으려던 상태다."""
    legacy = _facts(declared_capabilities=(), legacy_mode=True)
    assert ap.decide(_app(), _res(), ap.READ, app=legacy).allowed
    d = ap.decide(_app(), _res(), ap.WRITE, app=legacy)
    assert not d.allowed and d.reason == ap.DENY_MANIFEST_CAPABILITY


def test_선언에_없는_행동은_거부한다():
    d = ap.decide(_app(), _res(), ap.WRITE, app=_facts(declared_capabilities=(ap.READ,)))
    assert not d.allowed and d.reason == ap.DENY_MANIFEST_CAPABILITY


def test_선언이_아예_없는_것과_다른_것만_선언한_것을_다르게_말한다():
    """★ 두 검사는 같은 사유 코드를 내므로 **문구**를 잠근다 — 사용자가 고칠 것이 다르다."""
    none_declared = ap.decide(_app(), _res(), ap.WRITE, app=_facts(declared_capabilities=()))
    other = ap.decide(_app(), _res(), ap.WRITE, app=_facts(declared_capabilities=(ap.READ,)))
    assert none_declared.message != other.message
    assert ap.WRITE not in none_declared.message
    assert ap.WRITE in other.message


def test_사람_경로에는_매니페스트_선언을_요구하지_않는다():
    """★ 매니페스트는 «앱이 무엇을 하겠다고 말했는가» 다. 사람이 화면에서 직접 다루는 경로에
    그것을 요구하면 앱을 열지 않은 관리 작업이 전부 막힌다."""
    assert ap.decide(_user(), _res(), ap.WRITE, app=_facts(declared_capabilities=())).allowed


# ── 지적 3 — 미바인딩 Fail-closed (D-014) ─────────────────────────────────

def test_미바인딩_자원은_거부한다():
    """★★★ [rev.2 · 지적 3] 초판은 `owner_dept_id` 가 비면 **식별된 사용자에게 허용**했다.
    기존 릴리스 판정의 관대함을 승계한 것인데, 신규 Host Runtime 자원에서 그것은 D-014
    위반이다 — 범위 없는 자원은 «전사 공용» 이 아니라 **비노출**이다."""
    d = ap.decide(_user(), _res(scope_node_id=""), ap.READ)
    assert not d.allowed and d.reason == ap.DENY_UNBOUND


def test_미바인딩은_무제한_권한자에게도_거부한다():
    """⚠️ 손상·미기록은 **고쳐야 할 것**이다. 관리자 화면에 조용히 섞여 보이면 아무도 안 고친다."""
    d = ap.decide(_user(scope=_Scope(unrestricted=True)), _res(scope_node_id=""), ap.READ)
    assert not d.allowed and d.reason == ap.DENY_UNBOUND


def test_부서만_비어도_거부한다():
    """범위는 있는데 소유 부서가 없는 경우 — 레거시로 **명시**하지 않으면 막는다."""
    d = ap.decide(_user(scope=_Scope(read=set(), write=set())), _res(owner_dept_id=""), ap.READ)
    assert not d.allowed and d.reason == ap.DENY_UNBOUND


def test_레거시로_명시된_자원만_관대함이_적용된다():
    """★ 마이그레이션 대상을 **명시적 상태**로만 연다. 빈 값을 관대함으로 읽지 않는다."""
    s = _user(scope=_Scope(read=set(), write=set()))
    assert ap.decide(s, _res(owner_dept_id="", binding_state=ap.LEGACY), ap.READ).allowed


def test_판독_실패_자원은_언제나_거부한다():
    d = ap.decide(_user(scope=_Scope(unrestricted=True)), _res(binding_state=ap.INVALID), ap.READ)
    assert not d.allowed and d.reason == ap.DENY_UNBOUND


# ── 식별 · 문맥 · 조직 권한 ───────────────────────────────────────────────

@pytest.mark.parametrize("action", list(ap.ACTIONS))
def test_식별되지_않으면_읽기도_거부한다(action):
    d = ap.decide(_user(user_id=""), _res(), action)
    assert not d.allowed and d.reason == ap.DENY_UNIDENTIFIED


@pytest.mark.parametrize("ctx,res_kw", [
    (_ctx(tenant_id="tenant_other"), {}),
    (_ctx(entity_mode="VIRTUAL"), {}),
    (_ctx(), {"tenant_id": ""}),          # D-014 — 자원 문맥이 비면 비노출
    (_ctx(), {"entity_mode": ""}),
    ({"tenant_id": "", "entity_mode": ""}, {}),
])
def test_문맥이_어긋나면_거부한다(ctx, res_kw):
    d = ap.decide(_user(ctx=ctx), _res(**res_kw), ap.READ)
    assert not d.allowed and d.reason == ap.DENY_CONTEXT


def test_고른_조직_범위_밖의_자원은_거부한다(monkeypatch):
    """★ [rev.2] 「전권」과 「지금 보는 범위」는 다른 축이다 — 무제한 권한자도 좁혀진다."""
    import core.project_visibility as pv
    monkeypatch.setattr(pv, "_scope_is_ancestor", lambda a, n: (False, False))
    d = ap.decide(_user(scope=_Scope(unrestricted=True), ctx=_ctx(scope_node_id="node_other")),
                  _res(), ap.READ)
    assert not d.allowed and d.reason == ap.DENY_SCOPE


def test_다른_부서_자료는_거부한다():
    d = ap.decide(_user(scope=_Scope(read={"sales"}, write={"sales"})), _res(), ap.READ)
    assert not d.allowed and d.reason == ap.DENY_SCOPE


def test_읽기_권한만_있으면_쓰기는_막힌다():
    s = _user(scope=_Scope(read={"hq"}, write=set()))
    assert ap.decide(s, _res(), ap.READ).allowed
    d = ap.decide(s, _res(), ap.WRITE)
    assert not d.allowed and d.reason == ap.DENY_SCOPE


def test_소유자_본인은_부서_밖이어도_통과한다():
    s = _user(user_id="me@x", scope=_Scope(read=set(), write=set()))
    assert ap.decide(s, _res(owner_user_id="me@x"), ap.WRITE).allowed


def test_무제한_권한자는_부서_판정을_통과한다():
    assert ap.decide(_user(scope=_Scope(unrestricted=True)), _res(), ap.WRITE).allowed


# ── 개인 앱 ───────────────────────────────────────────────────────────────

def test_개인_앱은_만든_사람만_본다():
    d = ap.decide(_user(user_id="other@x"), _res(owner_user_id="me@x"), ap.READ,
                  app=_facts(app_class="personal"))
    assert not d.allowed and d.reason == ap.DENY_PERSONAL


def test_개인_앱은_무제한_권한자에게도_열리지_않는다():
    """★★ 「관리자니까 남의 개인 메모를 본다」는 권한 문제가 아니라 **신뢰 문제**다."""
    d = ap.decide(_user(user_id="boss@x", scope=_Scope(unrestricted=True)),
                  _res(owner_user_id="me@x"), ap.READ, app=_facts(app_class="personal"))
    assert not d.allowed and d.reason == ap.DENY_PERSONAL


# ── 잡다한 fail-closed ────────────────────────────────────────────────────

def test_사용_중단된_자원은_거부한다():
    d = ap.decide(_user(), _res(status="retired"), ap.READ)
    assert not d.allowed and d.reason == ap.DENY_RETIRED


def test_모르는_행동은_거부한다():
    d = ap.decide(_user(), _res(), "exfiltrate")
    assert not d.allowed and d.reason == ap.DENY_UNKNOWN_ACTION


@pytest.mark.parametrize("subject,resource", [(None, _res()), (_user(), None)])
def test_주체나_자원이_없으면_거부한다(subject, resource):
    assert not ap.decide(subject, resource, ap.READ).allowed


def test_권한_객체가_이상해도_통과시키지_않는다():
    """⚠️ 판정 실패는 **차단** 쪽이어야 한다."""
    class _Broken:
        @property
        def unrestricted(self):
            raise RuntimeError("조직 DB 장애")
    d = ap.decide(_user(scope=_Broken()), _res(), ap.READ)
    assert not d.allowed and d.reason == ap.DENY_SCOPE


def test_사유가_서로_겹치지_않는다(monkeypatch):
    """★ 화면이 원인을 구분해 말할 수 있어야 한다. 사유가 겹치면 「무엇을 고쳐야 하나」가 사라진다."""
    import core.project_visibility as pv
    monkeypatch.setattr(pv, "_scope_is_ancestor", lambda a, n: (False, False))
    reasons = {
        ap.decide(_user(user_id=""), _res(), ap.READ).reason,
        ap.decide(_app(token={"actor": "x@y"}), _res(), ap.READ, app=_facts()).reason,
        ap.decide(_app(token={"session_id": "old"}), _res(), ap.READ, app=_facts()).reason,
        ap.decide(_app(), _res(), ap.READ, app=_facts(release_id="other")).reason,
        ap.decide(_app(token={"tenant_id": "t2"}), _res(), ap.READ, app=_facts()).reason,
        ap.decide(_app(token={"scope_node_id": "n2"}), _res(), ap.READ, app=_facts()).reason,
        ap.decide(_app(token={"capabilities": ()}), _res(), ap.READ, app=_facts()).reason,
        ap.decide(_app(), _res(), ap.WRITE, app=_facts(declared_capabilities=())).reason,
        ap.decide(_user(ctx=_ctx(tenant_id="t2")), _res(), ap.READ).reason,
        ap.decide(_user(), _res(scope_node_id=""), ap.READ).reason,
        ap.decide(_user(scope=_Scope(read={"sales"})), _res(), ap.READ).reason,
        ap.decide(_user(user_id="o@x"), _res(owner_user_id="m@x"), ap.READ,
                  app=_facts(app_class="personal")).reason,
        ap.decide(_user(), _res(status="retired"), ap.READ).reason,
    }
    assert len(reasons) == 13, f"사유가 겹친다: {sorted(reasons)}"
