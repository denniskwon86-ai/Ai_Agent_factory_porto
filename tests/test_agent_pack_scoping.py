"""★★★ [D-017 §9 P0-4·P0-5] Agent Pack 범위 필터와 미바인딩 폴백 차단.

## 무엇이 열려 있었나 (설계 §2.4)

- 팩 목록이 **요청자 가시 범위나 테넌트로 전혀 필터되지 않았다.** 팩 이름과 목적만으로도
  «저쪽이 무엇을 자동화하고 있는가» 가 드러난다.
- 노드별 에이전트 해석 API 가 **그 노드를 볼 권한을 확인하지 않았다.** 노드 ID 만 알면 다른
  사업부에서 어떤 에이전트가 도는지 읽을 수 있었다.
- 바인딩이 없거나 해석에 실패하면 조용히 `domain_agents` 로 떨어졌다 — 조직이 «이 부서는 이
  에이전트만» 이라고 정해 둔 환경에서도 **승인하지 않은 구성이 그대로 실행됐다.**

## 왜 폴백 차단이 «조건부» 인가

ECM 을 배선하지 않은 부서까지 막으면 조직을 세우기도 전에 프로젝트 생성이 불가능해진다.
막는 것은 **«ECM 을 배선해 두고 바인딩만 빠진»** 경우다 — 그것은 설정 누락이지 미도입이 아니다.
"""
import pytest

from core.enterprise_context.agent_pack_binding import AgentPackStore
from core.enterprise_context.clone_service import CloneService
from core.enterprise_context.repository import EcmRepository
from core.enterprise_context.resolver import EcmResolver


@pytest.fixture()
def packs(tmp_path):
    repo = EcmRepository(db_path=str(tmp_path / "ecm.db"))
    return AgentPackStore(repository=repo, resolver=EcmResolver(repo),
                          clone=CloneService(repository=repo))


# ── P0-4 테넌트 필터 ──────────────────────────────────────────────────────
def test_list_packs_filters_by_tenant(packs):
    """★★★ 다른 테넌트의 팩이 목록에 나오면 안 된다.

    ⚠️ 팩 «이름» 과 «목적» 만으로도 그 회사가 무엇을 자동화하는지 드러난다."""
    packs.create_pack("A사 표준", "생산 자동화", ["planner"], "tenant_a", "u1")
    packs.create_pack("B사 표준", "품질 자동화", ["qa"], "tenant_b", "u2")

    a = packs.list_packs(tenant_id="tenant_a")
    assert len(a) == 1 and a[0]["name"] == "A사 표준"
    b = packs.list_packs(tenant_id="tenant_b")
    assert len(b) == 1 and b[0]["name"] == "B사 표준"


def test_list_packs_without_tenant_keeps_legacy_behavior(packs):
    """★ 테넌트를 주지 않으면 종전대로 전부 — ECM 미도입 흐름을 깨지 않는다."""
    packs.create_pack("A", "x", ["planner"], "tenant_a", "u1")
    packs.create_pack("B", "y", ["qa"], "tenant_b", "u2")
    assert len(packs.list_packs()) == 2


def test_status_and_tenant_filters_combine(packs):
    """★ 두 필터가 **함께** 걸린다 — 하나만 걸리면 다른 쪽으로 새어 나간다."""
    p1 = packs.create_pack("A승인", "x", ["planner"], "tenant_a", "u1")
    packs.create_pack("A초안", "x", ["planner"], "tenant_a", "u1")
    packs.create_pack("B승인", "y", ["qa"], "tenant_b", "u2")
    packs.approve_pack(p1["pack_id"], "boss")
    packs.approve_pack(packs.list_packs(tenant_id="tenant_b")[0]["pack_id"], "boss")

    rows = packs.list_packs(status="APPROVED", tenant_id="tenant_a")
    assert [r["name"] for r in rows] == ["A승인"]


# ── P0-5 미바인딩 폴백 차단 ───────────────────────────────────────────────
def _dept(monkeypatch, scope_node: str, agents):
    """`resolve_department_config` 가 보는 부서 레코드를 갈아 끼운다."""
    import core.org_seed as seed

    class _Dir:
        @staticmethod
        def get_department(_k):
            return {"dept_id": "prod", "name_ko": "생산", "status": "active",
                    "scope_node_id": scope_node, "domain_agents": list(agents),
                    "default_template_id": "", "master_domains": []}

    monkeypatch.setattr(seed, "org_directory", _Dir(), raising=False)
    return seed


def test_unbound_node_blocks_when_enforced(monkeypatch):
    """★★★ 권한 강제 + ECM 배선 + 바인딩 없음 → **부서 기본 목록으로 대체하지 않는다.**

    ⚠️ 대체하면 조직이 승인하지 않은 에이전트가 실행되고, 실행되면 산출물에 흔적이 남아
      되돌릴 수 없다."""
    seed = _dept(monkeypatch, "node_prod", ["planner", "coder"])
    monkeypatch.setattr(seed, "_unbound_block",
                        lambda n, w: f"차단: {n} / {w}", raising=False)

    class _Packs:
        @staticmethod
        def resolve_agents(_n, *a, **k):
            return {"bound": False, "agents": [], "skipped": []}

    import core.enterprise_context.agent_pack_binding as apb
    monkeypatch.setattr(apb, "agent_packs", _Packs(), raising=False)

    cfg = seed.resolve_department_config("prod")
    assert cfg["agents"] == [], "승인되지 않은 구성이 실행되면 안 된다"
    assert cfg["blocked_reason"], "왜 비었는지 말해야 한다"
    assert cfg["agent_source"] == "차단됨(바인딩 없음)"


def test_unwired_department_keeps_legacy_agents(monkeypatch):
    """★★ ECM 을 배선하지 않은 부서는 **종전대로** 동작한다.

    ⚠️ 여기까지 막으면 조직을 세우기 전에 프로젝트 생성이 불가능해진다 — 도입 자체가 막힌다."""
    seed = _dept(monkeypatch, "", ["planner", "coder"])
    cfg = seed.resolve_department_config("prod")
    assert cfg["agents"] == ["planner", "coder"]
    assert cfg["blocked_reason"] == ""


def test_bound_node_merges_pack_and_department(monkeypatch):
    """★ 바인딩이 있으면 팩이 기준이고 부서 고유 목록이 뒤에 얹힌다(둘 다 의도된 값)."""
    seed = _dept(monkeypatch, "node_prod", ["dept_only"])

    class _Packs:
        @staticmethod
        def resolve_agents(_n, *a, **k):
            return {"bound": True, "agents": ["pack_a", "pack_b"], "skipped": []}

    import core.enterprise_context.agent_pack_binding as apb
    monkeypatch.setattr(apb, "agent_packs", _Packs(), raising=False)

    cfg = seed.resolve_department_config("prod")
    assert cfg["agents"] == ["pack_a", "pack_b", "dept_only"]
    assert cfg["blocked_reason"] == ""
    assert "에이전트팩 바인딩" in cfg["agent_source"]


def test_block_message_is_empty_when_enforcement_off(monkeypatch):
    """★★ 강제가 꺼져 있으면 차단 문구가 **비어 있어야** 한다 — 종전 폴백을 유지한다."""
    import core.org_seed as seed
    import core.org_directory as od
    monkeypatch.setattr(od, "_org_enforce_effective", lambda: False, raising=False)
    assert seed._unbound_block("node_x", "테스트") == ""


def test_block_message_explains_what_to_do(monkeypatch):
    """★ 차단 문구가 «무엇을 해야 하는가» 를 말한다. 이유만 적으면 사용자는 멈춘 채로 남는다."""
    import core.org_seed as seed
    import core.org_directory as od
    monkeypatch.setattr(od, "_org_enforce_effective", lambda: True, raising=False)
    msg = seed._unbound_block("node_x", "승인된 에이전트팩 바인딩이 없습니다")
    assert "node_x" in msg
    assert "요청" in msg, "다음 행동이 없으면 안내가 아니다"


def test_unknown_enforcement_does_not_block(monkeypatch):
    """★★ 강제 여부를 **모르면 막지 않는다** — 가용성 쪽으로 기운다.

    ⚠️ 여기서만 fail-open 인 이유: 이 판단이 틀렸을 때 최악이 «승인 안 된 구성 실행» 이지
      «유출» 이 아니다. 유출 경로(범위 필터)는 반대로 fail-closed 다."""
    import core.org_seed as seed
    import core.org_directory as od

    def _boom():
        raise RuntimeError("정책 저장소 장애")

    monkeypatch.setattr(od, "_org_enforce_effective", _boom, raising=False)
    assert seed._unbound_block("node_x", "테스트") == ""
