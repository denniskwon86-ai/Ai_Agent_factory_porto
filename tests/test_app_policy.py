"""★★★ [G1-B04] 생성 앱 데이터 정책 결정점 — **교집합이 실제 권한이다.**

    요청자 권한 ∩ 지금 고른 문맥 ∩ 토큰 capability ∩ 매니페스트 선언 ∩ 자원 정책

하나라도 비면 거부다. 「대부분 통과했으니 통과」는 없다.

## 이 파일이 지키는 가장 중요한 것

**앱 토큰의 `release_id` 와 자원의 `release_id` 가 다르면 거부한다.** 설계
`design_app_data_plane_2026-08-08.md` §7-4 가 「이것 하나로 «앱이 남의 데이터를 읽는» 경로가
원천 차단된다」고 못박은 규칙이고, 그것을 여기서 잠근다.

⚠️ 판정을 **던지지 않고 돌려준다.** 그래야 화면이 「권한 없음」·「문맥 밖」·「남의 앱 토큰」을
  다르게 말할 수 있다. 한 가지 예외로 뭉개면 사용자는 원인에 도달하지 못한다.
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


def _res(**kw):
    base = dict(kind="dataset", release_id="rel_1", dataset_id="ds_1", app_class="departmental",
                owner_user_id="", owner_dept_id="hq", tenant_id="tenant_default",
                entity_mode="REAL", status="active",
                declared_capabilities=(ap.READ, ap.WRITE))
    base.update(kw)
    return ap.Resource(**base)


def _user(**kw):
    base = dict(user_id="u@x", scope=_Scope(read={"hq"}, write={"hq"}), ctx=_ctx(), via="session")
    base.update(kw)
    return ap.Subject(**base)


def _app(**kw):
    """앱 토큰 주체. 기본은 **자기 릴리스·읽기쓰기 허용**."""
    tok = dict(release_id="rel_1", app_id="app_1", capabilities=(ap.READ, ap.WRITE),
               expired=False)
    tok.update(kw.pop("token", {}))
    base = dict(user_id="u@x", scope=_Scope(read={"hq"}, write={"hq"}), ctx=_ctx(),
                via="app_token", token=tok)
    base.update(kw)
    return ap.Subject(**base)


# ── 기본 통과 (대조군) ─────────────────────────────────────────────────────
#
# ⚠️ 이것이 없으면 «전부 거부» 도 초록이 된다. 막히는 것만 보는 검사는 통제를 증명하지 않는다.

@pytest.mark.parametrize("action", [ap.READ, ap.WRITE, ap.DELETE, ap.MANAGE])
def test_사람이_자기_부서_자료를_다룰_수_있다(action):
    d = ap.decide(_user(), _res(), action)
    assert d.allowed, f"{action} 이 막혔다: {d.reason} {d.message}"


def test_앱_토큰도_자기_릴리스면_통과한다():
    assert ap.decide(_app(), _res(), ap.READ).allowed


def test_쓰기에는_기록_의무가_따라온다():
    """허용만 돌려주고 의무를 말하지 않으면 호출부마다 감사를 빠뜨리는 곳이 생긴다."""
    assert "audit" in ap.decide(_user(), _res(), ap.WRITE).obligations
    assert "audit" not in ap.decide(_user(), _res(), ap.READ).obligations


# ── ★★★ 남의 앱 데이터 (설계 §7-4) ────────────────────────────────────────

def test_앱_토큰은_다른_릴리스의_데이터를_건드릴_수_없다():
    """★★★ 이 한 줄이 「앱이 남의 데이터를 읽는」 경로를 원천 차단한다.

    앱은 데이터셋 «이름» 만 말하고 `release_id` 는 부모(브리지)가 붙인다. 그런데 앱이
    어떤 방법으로든 다른 릴리스를 가리키게 되면, 서버가 마지막으로 막아야 한다."""
    d = ap.decide(_app(token={"release_id": "rel_OTHER"}), _res(release_id="rel_1"), ap.READ)
    assert not d.allowed and d.reason == ap.DENY_TOKEN_APP_MISMATCH


def test_토큰에_없는_행동은_거부한다():
    d = ap.decide(_app(token={"capabilities": (ap.READ,)}), _res(), ap.WRITE)
    assert not d.allowed and d.reason == ap.DENY_TOKEN_CAPABILITY


def test_만료된_토큰은_거부한다():
    d = ap.decide(_app(token={"expired": True}), _res(), ap.READ)
    assert not d.allowed and d.reason == ap.DENY_TOKEN_EXPIRED


# ── 매니페스트 선언 (CL-0 감사 지적 D) ────────────────────────────────────

def test_선언하지_않은_앱은_쓰지_못한다():
    """⚠️ 「선언이 비었으니 전부 허용」은 CL-0 이 막으려던 것 자체다.
    빈 capability 매니페스트가 정상으로 통과하던 것이 감사 지적 D 였다."""
    d = ap.decide(_app(), _res(declared_capabilities=()), ap.WRITE)
    assert not d.allowed and d.reason == ap.DENY_MANIFEST_CAPABILITY


def test_선언에_없는_행동은_거부한다():
    d = ap.decide(_app(), _res(declared_capabilities=(ap.READ,)), ap.WRITE)
    assert not d.allowed and d.reason == ap.DENY_MANIFEST_CAPABILITY


def test_선언이_아예_없는_것과_다른_것만_선언한_것을_다르게_말한다():
    """★ [변이 검사로 드러남 · 2026-08-13] 두 검사는 **같은 사유 코드**를 내므로, 사유만
    단언하면 앞 분기를 통째로 지워도 테스트가 초록이다(실제로 살아남았다).

    그러나 두 상황은 사용자가 할 일이 다르다 —
      · 선언 자체가 없음 → **매니페스트에 데이터 행동을 추가**해야 한다
      · 다른 것만 선언  → **그 행동을 추가**해야 한다
    구분해서 말하지 않으면 「무엇을 고쳐야 하는지」가 사라진다. 그래서 **문구**를 잠근다."""
    none_declared = ap.decide(_app(), _res(declared_capabilities=()), ap.WRITE)
    other_declared = ap.decide(_app(), _res(declared_capabilities=(ap.READ,)), ap.WRITE)
    assert none_declared.message != other_declared.message, \
        "선언 없음과 선언 불일치가 같은 문구다 — 사용자는 무엇을 고쳐야 할지 알 수 없다"
    assert ap.WRITE not in none_declared.message, \
        "선언이 아예 없는데 특정 행동 이름을 지목하면 «그것만 넣으면 된다» 로 읽힌다"
    assert ap.WRITE in other_declared.message


def test_읽기는_선언이_비어도_사람_권한으로_판정한다():
    """★ 읽기까지 선언으로 막지 않는다 — 기존 앱이 전부 멈춘다. 통제를 조이다가 기능을
    끄지 않는다는 저장소 규칙(«막혔으니 안전» 으로 읽으면 아무도 못 쓰는 제품이 된다)."""
    assert ap.decide(_app(), _res(declared_capabilities=()), ap.READ).allowed


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


def test_다른_부서_자료는_거부한다():
    d = ap.decide(_user(scope=_Scope(read={"sales"}, write={"sales"})), _res(), ap.READ)
    assert not d.allowed and d.reason == ap.DENY_SCOPE


def test_읽기_권한만_있으면_쓰기는_막힌다():
    """★ 읽기와 쓰기를 같은 집합으로 보면 viewer 가 쓸 수 있게 된다."""
    s = _user(scope=_Scope(read={"hq"}, write=set()))
    assert ap.decide(s, _res(), ap.READ).allowed
    d = ap.decide(s, _res(), ap.WRITE)
    assert not d.allowed and d.reason == ap.DENY_SCOPE


def test_소유자_본인은_부서_밖이어도_통과한다():
    s = _user(user_id="me@x", scope=_Scope(read=set(), write=set()))
    assert ap.decide(s, _res(owner_user_id="me@x"), ap.WRITE).allowed


def test_무제한_권한자는_부서_판정을_통과한다():
    assert ap.decide(_user(scope=_Scope(unrestricted=True)), _res(), ap.WRITE).allowed


# ── 개인 앱 (설계 §5-1) ───────────────────────────────────────────────────

def test_개인_앱은_만든_사람만_본다():
    d = ap.decide(_user(user_id="other@x"), _res(app_class="personal", owner_user_id="me@x"),
                  ap.READ)
    assert not d.allowed and d.reason == ap.DENY_PERSONAL


def test_개인_앱은_무제한_권한자에게도_열리지_않는다():
    """★★ 「관리자니까 남의 개인 메모를 본다」는 권한 문제가 아니라 **신뢰 문제**다.
    부서 범위로 열면 개인 편의 도구가 부서 공유물이 된다(설계 §2-4 모순 2)."""
    d = ap.decide(_user(user_id="boss@x", scope=_Scope(unrestricted=True)),
                  _res(app_class="personal", owner_user_id="me@x"), ap.READ)
    assert not d.allowed and d.reason == ap.DENY_PERSONAL


# ── 잡다한 fail-closed ────────────────────────────────────────────────────

def test_사용_중단된_데이터셋은_거부한다():
    d = ap.decide(_user(), _res(status="retired"), ap.READ)
    assert not d.allowed and d.reason == ap.DENY_RETIRED


def test_모르는_행동은_거부한다():
    d = ap.decide(_user(), _res(), "exfiltrate")
    assert not d.allowed and d.reason == ap.DENY_UNKNOWN_ACTION


def test_주체가_없으면_거부한다():
    assert not ap.decide(None, _res(), ap.READ).allowed


def test_권한_객체가_이상해도_통과시키지_않는다():
    """⚠️ 판정 실패는 **차단** 쪽이어야 한다. `ownership_visible` 1차 구현이 정확히
    반대로(`except: return True`) 틀렸다."""
    class _Broken:
        @property
        def unrestricted(self):
            raise RuntimeError("조직 DB 장애")
    d = ap.decide(_user(scope=_Broken()), _res(), ap.READ)
    assert not d.allowed and d.reason == ap.DENY_SCOPE


def test_사유가_서로_겹치지_않는다():
    """★ 화면이 원인을 구분해 말할 수 있어야 한다 — 한 가지로 뭉개면 사용자는 원인에
    도달하지 못하고, 개발자는 어디를 고칠지 모른다."""
    reasons = {
        ap.decide(_user(user_id=""), _res(), ap.READ).reason,
        ap.decide(_app(token={"release_id": "other"}), _res(), ap.READ).reason,
        ap.decide(_app(token={"capabilities": ()}), _res(), ap.READ).reason,
        ap.decide(_app(), _res(declared_capabilities=()), ap.WRITE).reason,
        ap.decide(_user(ctx=_ctx(tenant_id="t2")), _res(), ap.READ).reason,
        ap.decide(_user(scope=_Scope(read={"sales"})), _res(), ap.READ).reason,
        ap.decide(_user(user_id="o@x"), _res(app_class="personal", owner_user_id="m@x"),
                  ap.READ).reason,
        ap.decide(_user(), _res(status="retired"), ap.READ).reason,
    }
    assert len(reasons) == 8, f"사유가 겹친다: {sorted(reasons)}"
