"""★★★ [D-018 ③④] API 경계에서 범위를 정본 `node_id` 로 정규화한다.

## 결정 (`.agents/DECISIONS.md` `[D-018]`)

> API 입력에서는 과도기적으로 `node_id`·코드·부서 ID를 모두 허용하고, **API 경계에서 즉시
> `node_id`로 정규화**한다. 응답에는 `scope_node_id`와 함께 표시용 `scope_code`·`scope_name`을 준다.

## 이 파일이 지키는 것

1. **정규화 지점이 하나다.** 종전에는 같은 헬퍼(`_scope`)가 `planning_control`·
   `briefing_control`·`connector_control` 에 **각각 복제**돼 있었다. 세 벌이면 문맥 인자를
   하나에만 붙이거나 감사 이름을 한 곳만 고치는 일이 생기고, 그 경로만 조용히 달라진다.
2. **판정·저장에는 `scope_node_id` 만 쓴다.** `scope_code`·`scope_name` 은 표시용이며 바뀔 수
   있는 의미값이다.
3. **`needs_normalization` 으로 백필 대상을 관측한다.** 코드·부서 id 로 들어온 요청은 그
   저장분이 아직 정본이 아니라는 뜻이다(D-018 ⑤ 진척의 관측 지점).
4. **거부는 감사에 남기고 404 로 은폐한다** — 정규화 리팩터링이 그 계약을 깨지 않았다.
"""
import pytest
from fastapi.testclient import TestClient

from tests import org_seed

#: ★★★ **시험 전용 합성 계정·조직**(`tests/org_seed.py`).
#: ⚠️ 예전에는 운영 조직도와 **운영 ECM 사본**(`ecm_org_seed`)에 기댔다. 깨끗한 checkout 에는
#:   둘 다 없어 이 파일이 마지막까지 남은 환경 의존이었다 — 다른 파일이 전부 초록이 된 뒤에야
#:   드러났다.
ADMIN = org_seed.ADMIN
MGR = org_seed.MANAGER_A          # 읽기·관리 = t_alpha
MEMBER = org_seed.MEMBER_B        # 읽기 = t_beta


def H(uid: str):
    return {"X-Factory-User": uid} if uid else {}


@pytest.fixture()
def client(monkeypatch, seeded_org):
    import config
    from core.org_directory import org_directory
    org_directory._invalidate()
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    from main import app
    try:
        yield TestClient(app)
    finally:
        org_directory._invalidate()


# ── 정규화 지점이 하나다 ──────────────────────────────────────────────────
def test_scope_helpers_delegate_to_one_place(client):
    """★★★ 세 라우트의 `_scope` 가 **같은 함수**에 위임한다.

    ⚠️ 이 테스트는 소스를 본다 — 동작 테스트로는 «세 벌이 우연히 같게 동작하는 상태» 와
      «한 곳에 모인 상태» 를 구분할 수 없고, 갈라지는 순간은 새 인자가 붙을 때다."""
    import inspect

    from api.routes import briefing_control, connector_control, planning_control
    for mod in (planning_control, briefing_control, connector_control):
        src = inspect.getsource(mod._scope)
        assert "assert_scope_allowed" in src, f"{mod.__name__}._scope 가 공통 판정을 쓰지 않는다"
        # 종전 형태(직접 감사 + 직접 404)가 되살아나면 판정이 다시 갈라진다.
        assert "denied_scope" not in src, f"{mod.__name__}._scope 가 감사를 직접 부른다"


def test_patching_the_origin_module_affects_every_route(client, monkeypatch, tmp_path):
    """★★ 패치 지점이 하나라는 것을 **거부 주입**으로 확인한다.

    종전에는 라우터마다 이름을 들고 있어 라우터별로 패치해야 했고, 잘못 패치하면 테스트가
    조용히 통과하며 «거부가 동작한다» 고 착각하게 됐다(그 함정이 실제로 기록돼 있었다)."""
    import core.scope_guard as sg
    monkeypatch.setattr(sg, "resolve_effective_scope",
                        lambda p, req="", *a, **kw: sg.EffectiveScope(
                            denied=True, actor="x", allowed_scopes=["t_beta"],
                            reason="requested_scope_not_in_actor_scopes"))
    # 서로 다른 세 라우터가 **모두** 막힌다.
    assert client.get("/api/v1/briefing?scope_node_id=MNM_COPPER",
                      headers=H(MGR)).status_code == 404
    assert client.get("/api/v1/planning/submissions?org_id=MNM_COPPER",
                      headers=H(MGR)).status_code == 404
    assert client.get("/api/v1/connectors?scope_node_id=MNM_COPPER",
                      headers=H(MGR)).status_code == 404


def test_denial_is_still_audited(client, monkeypatch, tmp_path):
    """★★ 404 은폐는 **응답**이고 기록은 남는다 — 리팩터링이 그 계약을 깨지 않았다."""
    import core.scope_guard as sg
    from core.enterprise_context import audit
    monkeypatch.setattr(audit, "_LOG_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(sg, "resolve_effective_scope",
                        lambda p, req="", *a, **kw: sg.EffectiveScope(
                            denied=True, actor="bob", allowed_scopes=["t_beta"],
                            reason="requested_scope_not_in_actor_scopes"))
    client.get("/api/v1/planning/submissions?org_id=MNM_COPPER", headers=H(MGR))
    e = audit.recent(1)[0]
    assert e["event"] == audit.ACCESS_DENIED_SCOPE_MISMATCH
    assert e["requested_scope"] == "MNM_COPPER", "실제 요청 범위가 기록돼야 한다"
    assert e["resource_type"] == "plan_fact", "어느 자원에 대한 시도였는지 남아야 한다"


# ── 응답에 정본 + 표시용 값 (D-018 ③) ────────────────────────────────────
def test_response_carries_node_id_and_display_fields(client):
    """★★★ 화면은 `node_41402723bc90` 을 사람에게 보여줄 수 없다. 정본과 표시값을 함께 준다."""
    r = client.get("/api/v1/planning/facts?org_id=t_alpha&scope_node_id=t_alpha",
                   headers=H(MGR))
    assert r.status_code == 200
    perm = r.json()["permission"]
    assert perm["scope_node_id"].startswith("node_"), \
        f"정본으로 정규화되지 않았다: {perm['scope_node_id']}"
    assert perm["scope_code"] == "t_alpha", "표시용 업무 코드가 없다"
    assert perm["scope_name"], "표시용 이름이 없다"


def test_code_input_is_flagged_for_backfill(client):
    """★★ 코드로 들어온 요청은 `needs_normalization=True` 다 — 그 저장분이 아직 정본이 아니라는
    뜻이고, 백필(D-018 ⑤) 진척을 관측하는 지점이다."""
    r = client.get("/api/v1/planning/facts?org_id=t_alpha&scope_node_id=t_alpha", headers=H(MGR))
    perm = r.json()["permission"]
    assert perm["scope_ref_kind"] == "ecm_code"
    assert perm["needs_normalization"] is True


def test_node_id_input_needs_no_normalization(client, seeded_org):
    """정본으로 들어오면 백필 대상이 아니다."""
    node = org_seed.NODES[org_seed.DEPT_A]
    r = client.get(f"/api/v1/planning/facts?org_id=t_alpha&scope_node_id={node}", headers=H(MGR))
    perm = r.json()["permission"]
    assert perm["scope_node_id"] == node
    assert perm["scope_ref_kind"] == "ecm_node" and perm["needs_normalization"] is False


def test_briefing_also_reports_scope_meta(client):
    """브리핑도 같은 메타를 준다 — 라우트마다 응답 모양이 다르면 화면이 분기해야 한다."""
    r = client.get("/api/v1/briefing?scope_node_id=t_alpha", headers=H(MGR))
    assert r.status_code == 200
    perm = r.json()["permission"]
    assert perm["scope_node_id"].startswith("node_") and perm["scope_code"] == "t_alpha"


def test_empty_scope_is_not_flagged(client):
    """★ 전사 조회(범위 없음)는 정규화할 대상이 없다 — `needs_normalization` 이 True 면
    화면이 «정리할 것이 있다» 고 잘못 표시한다."""
    r = client.get("/api/v1/briefing", headers=H(ADMIN))
    assert r.status_code == 200
    perm = r.json()["permission"]
    assert perm["needs_normalization"] is False and perm["scope_node_id"] == ""


# ── 문맥이 실제로 전달된다 (D-018 ④) ─────────────────────────────────────
def test_entity_mode_reaches_the_resolver(client):
    """★★★ 라우트가 받은 `entity_mode` 가 **범위 해석까지** 간다.

    ⚠️ 종전에는 `briefing`·`/facts` 가 `entity_mode` 를 받아 **저장소 조회에만** 넘기고 해석에는
      넣지 않았다. 코드는 그 문맥 안에서만 유일하므로, 넘기지 않으면 가상 시나리오 범위를
      실제 문맥으로 해석할 수 있다."""
    seen = []
    import core.scope_guard as sg
    orig = sg.resolve_effective_scope

    def spy(p, requested="", tenant_id="", entity_mode="", *a, **kw):
        seen.append({"requested": requested, "tenant_id": tenant_id,
                     "entity_mode": entity_mode})
        return orig(p, requested, tenant_id, entity_mode)

    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(sg, "resolve_effective_scope", spy)
        client.get("/api/v1/briefing?scope_node_id=t_alpha&entity_mode=REAL"
                   "&tenant_id=tenant_default", headers=H(MGR))
    assert seen, "범위 해석이 호출되지 않았다"
    assert seen[0]["entity_mode"] == "REAL" and seen[0]["tenant_id"] == "tenant_default"


def test_wrong_context_does_not_resolve_to_the_other_mode(client, seeded_org):
    """★★★ 실제 코드를 가상 문맥으로 물으면 **해석되지 않는다**(그 반대도 같다).

    이것이 «코드는 tenant·entity_mode 안에서만 유일하다» 의 실질적 의미다."""
    from core.enterprise_context.resolver import ecm_resolver
    r = ecm_resolver.resolve_scope_ref("t_beta", entity_mode="VIRTUAL")
    assert r["resolved"] is False and r["kind"] == "code_out_of_context"
    # 반대 방향: 가상 코드를 실제 문맥으로
    v = ecm_resolver.resolve_scope_ref("v_t_beta", entity_mode="REAL")
    assert v["resolved"] is False and v["kind"] == "code_out_of_context"
    # 맞는 문맥에서는 각자 해석된다 — 막는 것만 확인하면 «전부 막힌 상태» 를 통과로 센다.
    assert ecm_resolver.resolve_scope_ref(
        "t_beta", entity_mode="REAL")["node_id"] == org_seed.NODES[org_seed.DEPT_B]
    assert ecm_resolver.resolve_scope_ref(
        "v_t_beta", entity_mode="VIRTUAL")["node_id"] == org_seed.NODES[org_seed.VIRTUAL_CODE_B]


# ── 통제가 업무를 막지 않는다 ─────────────────────────────────────────────
def test_own_scope_still_passes_after_normalization(client):
    """★★★ 정규화가 자기 조직 접근을 막지 않는다.

    ⚠️ 이 테스트가 이 파일에서 가장 중요하다 — 앞선 세션에서 범위 판정을 조이다가 «자기 조직도
      404» 가 된 적이 있고, 그 상태를 «막혔으니 안전» 으로 읽으면 아무도 못 쓰는 제품이 된다."""
    for uid, org in ((MGR, "t_alpha"), (MEMBER, "t_beta")):
        for path in (f"/api/v1/planning/submissions?org_id={org}",
                     f"/api/v1/planning/facts?org_id={org}&scope_node_id={org}",
                     f"/api/v1/briefing?scope_node_id={org}"):
            r = client.get(path, headers=H(uid))
            assert r.status_code == 200, f"{uid} 가 자기 조직 {org} 의 {path} 에서 막혔다"
