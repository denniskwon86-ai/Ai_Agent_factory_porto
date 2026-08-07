"""[D-017 §9 P2 완료 기준 ⑤] 역할 × 실행 문맥 회귀 매트릭스.

설계(`docs/design_agent_governance_scope_permissions_2026-08-04.md` §11-5)의 완료 기준:

    관리자·manager·member·viewer·익명, REAL·VIRTUAL 조합 회귀 테스트가 통과한다.

## 이 파일이 지키는 **한 가지** 계약

`core/scope_guard.resolve_effective_scope` 의 docstring 이 못박은 것:

    `tenant_id`·`entity_mode` 는 **요청 값 해석에만** 쓰인다. 주체의 범위 계산에는 넣지
    않는다 — 주체가 볼 수 있는 조직은 그 사람의 소속이 정하는 것이고, **요청 문맥이 그것을
    넓히면 «문맥을 바꿔 권한을 얻는» 경로가 생긴다.**

★★★ 그 경로가 왜 위험한가: `entity_mode` 와 `tenant_id` 는 **요청자가 헤더로 보내는 값**이다
  (`X-Entity-Mode`·`X-Enterprise-Tenant`). 즉 주체가 스스로 바꿀 수 있다. 만약 범위 계산이
  그 값을 본다면, viewer 가 헤더 한 줄로 다른 조직을 열람하게 된다 — 서버 코드를 고치지
  않고도 통제가 무너지는 형태다.

⚠️ 이 파일은 «각 역할이 무엇을 볼 수 있는가» 를 새로 정의하지 않는다. 그것은 조직 디렉터리가
  정하고 `test_agent_config_gate.py`·`test_scope_contract.py` 가 이미 지킨다. 여기서 지키는
  것은 **문맥을 바꿔도 그 답이 변하지 않는다**는 불변식 하나다. 축이 둘(역할·문맥)일 때
  한쪽만 검사하면 교차 지점이 비고, 실제로 지금 그 자리가 비어 있었다(VIRTUAL × 역할 0건).

## 왜 «넓어지지 않는다» 만 검사하고 «같다» 를 검사하지 않는가

문맥에 따라 **좁아지는** 것은 정당하다(가상 문맥에서 더 막을 수 있다). 넓어지는 것만이
결함이다. 그래서 단언은 부분집합(⊆)이지 상등(=)이 아니다 — 상등으로 못박으면 나중에
「가상에서는 더 막자」는 정당한 강화가 이 테스트를 깨뜨리고, 그때 사람은 테스트를 고친다.
"""
import pytest

from core.org_directory import AccessScope
from core.scope_guard import resolve_effective_scope

#: 문맥 축. 요청자가 헤더로 **스스로 바꿀 수 있는** 값들이다.
MODES = ["REAL", "VIRTUAL", "COMPETITOR_REFERENCE", ""]
TENANTS = ["tenant_default", "tenant_other", ""]


class _P:
    """`Principal` 대역 — `resolve_effective_scope` 는 `user_id` 와 `scope` 만 본다."""

    def __init__(self, user_id: str, scope):
        self.user_id = user_id
        self.scope = scope


def _scope(**kw) -> AccessScope:
    base = dict(user_id=kw.pop("user_id", "u"), unrestricted=False)
    base.update(kw)
    return AccessScope(**base)


#: 다섯 주체. **실제 형태에 맞춘다** — 운영 DB 사용자 전원이 `roles` 를 갖고 있고
#  viewer 부터 읽기 권한을 받는다(`test_agent_config_gate` 실측 주석 참조).
def _subjects():
    return {
        "익명": _P("", _scope(user_id="")),
        "viewer": _P("v@ls", _scope(
            user_id="v@ls", readable_dept_ids=frozenset({"quality"}),
            readable_scope_nodes=frozenset({"node_q"}), primary_dept_id="quality")),
        "member": _P("m@ls", _scope(
            user_id="m@ls", readable_dept_ids=frozenset({"quality"}),
            writable_dept_ids=frozenset({"quality"}),
            readable_scope_nodes=frozenset({"node_q"}), primary_dept_id="quality")),
        "manager": _P("g@ls", _scope(
            user_id="g@ls", readable_dept_ids=frozenset({"quality", "production"}),
            writable_dept_ids=frozenset({"quality"}),
            manageable_dept_ids=frozenset({"quality"}),
            readable_scope_nodes=frozenset({"node_q", "node_p"}),
            manageable_scope_nodes=frozenset({"node_q"}), primary_dept_id="quality")),
        "관리자": _P("admin@ls", _scope(user_id="admin@ls", unrestricted=True)),
    }


# ── ① 핵심 불변식 — 문맥을 바꿔도 범위가 넓어지지 않는다 ────────────────────
@pytest.mark.parametrize("role", ["익명", "viewer", "member", "manager"])
def test_entity_mode_never_widens_allowed_scopes(role):
    """★★★ 이 파일 전체의 이유.

    `entity_mode` 는 요청자가 `X-Entity-Mode` 헤더로 **스스로 보내는 값**이다. 범위 계산이
    그것을 본다면 헤더 한 줄로 권한이 넓어진다 — 서버 코드를 고치지 않고도 통제가 무너진다.

    ⚠️ `관리자`(unrestricted)는 제외한다. 그 주체는 애초에 전 범위이므로 «넓어짐» 을 잴 수
      없고, 넣으면 이 검사가 무엇을 지키는지 흐려진다."""
    p = _subjects()[role]
    base = set(resolve_effective_scope(p, "", "tenant_default", "REAL").allowed_scopes)
    for mode in MODES:
        got = set(resolve_effective_scope(p, "", "tenant_default", mode).allowed_scopes)
        assert got <= base, (
            f"{role} 가 entity_mode={mode!r} 로 범위를 넓혔다: {sorted(got - base)}")


@pytest.mark.parametrize("role", ["익명", "viewer", "member", "manager"])
def test_tenant_never_widens_allowed_scopes(role):
    """테넌트도 헤더(`X-Enterprise-Tenant`)로 들어온다 — 같은 이유로 같은 불변식이다."""
    p = _subjects()[role]
    base = set(resolve_effective_scope(p, "", "tenant_default", "REAL").allowed_scopes)
    for t in TENANTS:
        got = set(resolve_effective_scope(p, "", t, "REAL").allowed_scopes)
        assert got <= base, (
            f"{role} 가 tenant_id={t!r} 로 범위를 넓혔다: {sorted(got - base)}")


# ── ② 남의 조직을 문맥으로 열 수 없다 ───────────────────────────────────────
@pytest.mark.parametrize("role", ["viewer", "member", "manager"])
@pytest.mark.parametrize("mode", MODES)
def test_foreign_scope_stays_denied_in_every_mode(role, mode):
    """★ 자기 범위 밖 조직을 요청하면 어떤 문맥에서도 거부다.

    ⚠️ 거부는 `denied=True` 로 오고 라우트가 그것을 **404 로 은폐**한다(§3.3 경계표) —
      403 으로 답하면 «그 조직이 존재한다» 는 사실이 새어나간다."""
    p = _subjects()[role]
    eff = resolve_effective_scope(p, "node_secret_other_div", "tenant_default", mode)
    assert eff.denied, f"{role} 가 mode={mode!r} 에서 남의 조직을 열었다"


@pytest.mark.parametrize("mode", MODES)
def test_anonymous_has_no_scope_in_every_mode(mode):
    """익명은 어떤 문맥에서도 조직 범위를 갖지 않는다.

    ⚠️ 「범위를 명시하지 않으면 필터 없이 통과」하는 종전 계약이 남아 있으므로
      (`no_scope_requested`), 익명 차단은 **라우트의 식별 관문**이 맡는다. 여기서는
      «익명에게 조직 범위가 생기지 않는다» 만 지킨다 — 그것이 이 함수의 책임이다."""
    p = _subjects()["익명"]
    eff = resolve_effective_scope(p, "", "tenant_default", mode)
    assert list(eff.allowed_scopes) == [], f"익명이 mode={mode!r} 에서 범위를 얻었다"


# ── ③ 역할 사이의 포함 관계가 문맥과 무관하게 유지된다 ──────────────────────
@pytest.mark.parametrize("mode", MODES)
def test_role_hierarchy_holds_in_every_mode(mode):
    """viewer ⊆ manager 가 모든 문맥에서 유지된다.

    ★ 이 검사가 없으면 «가상 문맥에서만 viewer 가 manager 보다 넓다» 같은 뒤집힘이 조용히
      들어올 수 있다. 축이 둘일 때는 각 축을 따로 본 검사가 교차 지점을 못 본다."""
    s = _subjects()
    v = set(resolve_effective_scope(s["viewer"], "", "tenant_default", mode).allowed_scopes)
    g = set(resolve_effective_scope(s["manager"], "", "tenant_default", mode).allowed_scopes)
    assert v <= g, f"mode={mode!r} 에서 viewer 가 manager 범위를 벗어났다: {sorted(v - g)}"


# ── ④ 해석 실패가 «전부 허용» 이 되지 않는다 ────────────────────────────────
@pytest.mark.parametrize("mode", MODES)
def test_resolver_failure_yields_empty_scope_not_wildcard(monkeypatch, mode):
    """⚠️ 리솔버가 죽으면 **빈 집합**이어야 한다. 「해석 못 했으니 통과」로 처리하면
    리솔버 장애가 곧 전사 유출이 된다(`_actor_scopes` 주석이 못박은 규칙).

    ★★ [2026-08-08 변이 검사로 발견] 이 검사는 처음에 `eff.denied` 만 봤고 **허수였다.**
      `_actor_scopes` 를 fail-open(`return ["*"]`)으로 바꿔도 통과했다 — 멤버십 판정이
      `"node_q" in ["*"]` 라 와일드카드를 펼치지 않기 때문에 **결함이 있어도 denied 가 True**
      였다. 즉 「거부됐다」는 사실은 fail-closed 의 증거가 되지 못한다.
      → 계약 자체(**빈 집합**)를 단언한다. 변이를 넣으면 실제로 실패한다."""
    import core.enterprise_context.scoping as sc
    monkeypatch.setattr(sc, "visible_scopes",
                        lambda *_a, **_k: (_ for _ in ()).throw(OSError("db locked")))
    p = _subjects()["manager"]
    eff = resolve_effective_scope(p, "", "tenant_default", mode)
    assert list(eff.allowed_scopes) == [], (
        f"mode={mode!r} 에서 리솔버 장애가 «전부 허용» 으로 처리됐다: {eff.allowed_scopes}")


# ── ⑤ 무제한 주체는 문맥과 무관하게 통과한다(하위호환 계약) ─────────────────
@pytest.mark.parametrize("mode", MODES)
def test_unrestricted_subject_passes_in_every_mode(mode):
    """조직 미도입 환경의 하위호환 계약. **정규화는 하되 막지 않는다.**

    ⚠️ 이것을 «권한 없음» 으로 바꾸면 조직을 도입하지 않은 설치에서 제품이 통째로 멈춘다."""
    p = _subjects()["관리자"]
    eff = resolve_effective_scope(p, "node_anything", "tenant_default", mode)
    assert not eff.denied, f"무제한 주체가 mode={mode!r} 에서 막혔다"
    assert eff.reason == "unrestricted"
