"""★★★ [D-018 ⑦] 코드 유일성 제약 + 변경 이력·별칭 보존.

## 결정 (`.agents/DECISIONS.md` `[D-018]` 이행 규칙 ④)

> 코드 조회는 tenant·entity_mode 문맥에서 유일해야 하며 **코드 변경 이력·별칭을 보존**한다.

## 이 파일이 지키는 것

1. **저장 시점에 유일성을 막는다.** 조회 시점 fail-closed 만 있으면 이미 두 노드가 같은 코드를
   갖고 있고, 그때는 «어느 쪽을 고쳐야 하는가» 를 사람이 판단해야 한다.
   ⚠️ DB `UNIQUE` 로 걸 수 없다 — 유일성 범위가 `(tenant_id, entity_mode, code)` 인데
   `entity_mode` 는 다른 표에 있다. 그래서 애플리케이션에서 검증한다.
2. **옛 코드를 버리지 않는다.** `code` 는 조직 개편으로 바뀌고(`LS_MNM` → `LS_METALS`), 정본
   `node_id` 는 그대로지만 **옛 코드로 저장된 외부 연계·문서·사람의 기억**은 그 순간 끊긴다.
   ⚠️ 끊긴 참조는 조용하다 — 조회가 «없음» 을 돌려주고 그것은 «권한이 없다» 와 구분되지 않는다.
3. **현재 코드가 이긴다.** 별칭은 현재 코드로 **못 찾았을 때만** 본다. 그러지 않으면 «이름을
   물려받은 새 조직» 대신 옛 조직이 해석되고, 그것은 권한을 과거로 되돌리는 일이다.
4. **별칭으로 찾아도 정본으로 정규화된다** — 판정은 언제나 `node_id` 를 탄다.
"""
import pytest

from core.enterprise_context.models import (STATUS_ACTIVE, EcmError, EnterpriseEntity,
                                           OrganizationNode)
from core.enterprise_context.repository import EcmRepository
from core.enterprise_context.resolver import EcmResolver


@pytest.fixture()
def repo(tmp_path):
    return EcmRepository(db_path=str(tmp_path / "ecm.db"))


@pytest.fixture()
def resolver(repo):
    return EcmResolver(repo=repo)


def _entity(repo, name, mode="REAL", base=""):
    return repo.upsert_entity(EnterpriseEntity(
        name_ko=name, entity_mode=mode, base_entity_id=base, status=STATUS_ACTIVE))


def _node(repo, entity_id, code, name, node_id="", tenant_id="tenant_default"):
    return repo.upsert_node(OrganizationNode(
        node_id=node_id, entity_id=entity_id, code=code, name_ko=name,
        tenant_id=tenant_id, status=STATUS_ACTIVE))


# ── 저장 시점 유일성 (D-018 ④) ────────────────────────────────────────────
def test_duplicate_code_in_same_context_is_refused_at_write(repo):
    """★★★ **저장 시점에** 막는다 — 조회 시점 fail-closed 만으로는 늦다.

    이미 두 노드가 같은 코드를 갖게 되면 «어느 쪽을 고쳐야 하는가» 를 사람이 판단해야 하고,
    그 사이 코드로 하는 모든 조회가 거부된다."""
    e = _entity(repo, "LS MnM")
    _node(repo, e.entity_id, "LS_MNM", "LS MnM")
    with pytest.raises(EcmError) as ex:
        _node(repo, e.entity_id, "LS_MNM", "중복 시도")
    msg = str(ex.value)
    assert "LS_MNM" in msg and "유일" in msg
    assert "LS MnM" in msg, "어느 노드와 충돌했는지 알려줘야 고칠 수 있다"


def test_same_code_is_allowed_in_a_different_entity_mode(repo):
    """★★ 가상 문맥에는 같은 코드가 있어도 된다 — 유일성 범위가 `(tenant, mode, code)` 다.

    ⚠️ 이것을 막으면 가상 복제가 «접두사 없이 원본 코드를 그대로 쓰는» 방식을 택할 수 없게 된다."""
    real = _entity(repo, "실제")
    virt = _entity(repo, "가상", mode="VIRTUAL", base=real.entity_id)
    _node(repo, real.entity_id, "LS_MNM", "실제")
    _node(repo, virt.entity_id, "LS_MNM", "가상")      # 거부되지 않는다
    assert len(repo.find_nodes_by_code("LS_MNM")) == 2


def test_same_code_is_allowed_in_a_different_tenant(repo):
    e1, e2 = _entity(repo, "회사1"), _entity(repo, "회사2")
    _node(repo, e1.entity_id, "HQ", "본사1", tenant_id="tenant_a")
    _node(repo, e2.entity_id, "HQ", "본사2", tenant_id="tenant_b")   # 거부되지 않는다
    assert len(repo.find_nodes_by_code("HQ", tenant_id="tenant_a")) == 1


def test_updating_the_same_node_is_not_a_conflict(repo):
    """★ 자기 자신은 충돌이 아니다 — 그러지 않으면 이름만 바꾸는 갱신도 막힌다."""
    e = _entity(repo, "LS MnM")
    n = _node(repo, e.entity_id, "LS_MNM", "LS MnM")
    again = _node(repo, e.entity_id, "LS_MNM", "LS MnM (이름 수정)", node_id=n.node_id)
    assert again.node_id == n.node_id
    assert repo.get_node(n.node_id).name_ko == "LS MnM (이름 수정)"


def test_empty_code_is_not_subject_to_uniqueness(repo):
    """코드 없는 노드는 여러 개일 수 있다 — 빈 값은 «코드가 없다» 는 사실이지 중복이 아니다."""
    e = _entity(repo, "회사")
    _node(repo, e.entity_id, "", "무코드1")
    _node(repo, e.entity_id, "", "무코드2")
    assert len(repo.find_nodes_by_code("")) == 0


# ── 코드 변경 이력·별칭 (D-018 ④) ────────────────────────────────────────
def test_changing_a_code_records_the_old_one(repo):
    """★★★ 코드를 바꾸면 **옛 코드가 별칭으로 남는다.** 버리면 그 코드로 저장된 외부 연계가
    조용히 끊긴다."""
    e = _entity(repo, "LS MnM")
    n = _node(repo, e.entity_id, "LS_MNM", "LS MnM")
    _node(repo, e.entity_id, "LS_METALS", "LS MnM", node_id=n.node_id)   # 개편으로 코드 변경

    aliases = repo.code_aliases_of(n.node_id)
    assert [a["code"] for a in aliases] == ["LS_MNM"]
    assert aliases[0]["replaced_by"] == "LS_METALS", "무엇으로 바뀌었는지 남아야 한다"
    assert aliases[0]["reason"], "왜 바뀌었는지 남아야 한다"


def test_old_code_still_resolves_to_the_canonical_node(repo, resolver):
    """★★★ 옛 코드로도 **정본**이 나온다 — 그것이 별칭의 목적이다."""
    e = _entity(repo, "LS MnM")
    n = _node(repo, e.entity_id, "LS_MNM", "LS MnM")
    _node(repo, e.entity_id, "LS_METALS", "LS MnM", node_id=n.node_id)

    r = resolver.resolve_scope_ref("LS_MNM")            # 옛 코드로 묻는다
    assert r["resolved"] is True and r["kind"] == "ecm_code_alias"
    assert r["node_id"] == n.node_id
    assert r["code"] == "LS_METALS", "표시용 코드는 **현재** 코드여야 한다"
    assert r["requested_code"] == "LS_MNM", "무엇으로 물었는지도 남아야 한다"


def test_current_code_wins_over_an_alias(repo, resolver):
    """★★★ **현재 코드가 이긴다.** 별칭은 현재 코드로 못 찾았을 때만 본다.

    ⚠️ 그러지 않으면 «옛 코드를 물려받은 새 조직» 대신 옛 조직이 해석되고, 그것은 권한을
      과거로 되돌리는 일이다 — 조직 개편에서 실제로 일어나는 형태다."""
    e = _entity(repo, "회사")
    old = _node(repo, e.entity_id, "DIV_A", "구 A사업부")
    _node(repo, e.entity_id, "DIV_A_LEGACY", "구 A사업부", node_id=old.node_id)  # 코드 이관
    new = _node(repo, e.entity_id, "DIV_A", "신 A사업부")      # 옛 코드를 물려받는다

    r = resolver.resolve_scope_ref("DIV_A")
    assert r["kind"] == "ecm_code" and r["node_id"] == new.node_id, \
        "옛 조직이 해석됐다 — 권한이 과거로 되돌아간다"


def test_ambiguous_alias_is_refused_not_guessed(repo, resolver):
    """별칭이 여러 노드에 걸리면(코드 재사용) 현재 코드와 **같은 규칙**으로 거부한다."""
    e = _entity(repo, "회사")
    a = _node(repo, e.entity_id, "SHARED", "첫 번째")
    _node(repo, e.entity_id, "FIRST", "첫 번째", node_id=a.node_id)     # SHARED → 별칭
    b = _node(repo, e.entity_id, "SHARED", "두 번째")                   # 코드 재사용
    _node(repo, e.entity_id, "SECOND", "두 번째", node_id=b.node_id)    # SHARED → 별칭(둘째)

    r = resolver.resolve_scope_ref("SHARED")
    assert r["resolved"] is False and r["kind"] == "code_alias_ambiguous"
    assert {c["node_id"] for c in r["candidates"]} == {a.node_id, b.node_id}


def test_alias_lookup_respects_context(repo, resolver):
    """별칭 조회도 tenant·mode 문맥을 지킨다 — 현재 코드와 같은 계약이다."""
    real = _entity(repo, "실제")
    virt = _entity(repo, "가상", mode="VIRTUAL", base=real.entity_id)
    rn = _node(repo, real.entity_id, "OLD_R", "실제")
    _node(repo, real.entity_id, "NEW_R", "실제", node_id=rn.node_id)
    vn = _node(repo, virt.entity_id, "OLD_V", "가상")
    _node(repo, virt.entity_id, "NEW_V", "가상", node_id=vn.node_id)

    assert resolver.resolve_scope_ref("OLD_R", entity_mode="REAL")["node_id"] == rn.node_id
    assert resolver.resolve_scope_ref("OLD_R", entity_mode="VIRTUAL")["resolved"] is False
    assert resolver.resolve_scope_ref("OLD_V", entity_mode="VIRTUAL")["node_id"] == vn.node_id


def test_alias_history_accumulates(repo):
    """★ 코드가 두 번 바뀌면 **이력이 쌓인다** — 마지막 것만 남기면 중간 코드로 온 참조가 끊긴다."""
    e = _entity(repo, "회사")
    n = _node(repo, e.entity_id, "V1", "조직")
    _node(repo, e.entity_id, "V2", "조직", node_id=n.node_id)
    _node(repo, e.entity_id, "V3", "조직", node_id=n.node_id)
    assert {a["code"] for a in repo.code_aliases_of(n.node_id)} == {"V1", "V2"}


def test_alias_does_not_shadow_a_reused_code_after_second_change(repo, resolver):
    """★★ 같은 노드가 옛 코드로 **되돌아가면** 별칭이 현재 코드를 가리지 않는다.

    `V1 → V2 → V1` 처럼 되돌리는 일이 실제로 있다(개편 철회). 그때 `V1` 은 현재 코드이므로
    현재 코드 경로가 이겨야 한다."""
    e = _entity(repo, "회사")
    n = _node(repo, e.entity_id, "V1", "조직")
    _node(repo, e.entity_id, "V2", "조직", node_id=n.node_id)
    _node(repo, e.entity_id, "V1", "조직", node_id=n.node_id)      # 되돌림
    r = resolver.resolve_scope_ref("V1")
    assert r["kind"] == "ecm_code" and r["node_id"] == n.node_id


# ── 판정은 언제나 정본을 탄다 ─────────────────────────────────────────────
def test_alias_resolution_feeds_the_same_canonical_judgement(repo):
    """★★ 별칭으로 들어와도 `visible_scopes` 는 **정본 기준**으로 계산된다."""
    from core.enterprise_context import resolver as _res
    from core.enterprise_context import scoping as sc

    e = _entity(repo, "LS MnM")
    n = _node(repo, e.entity_id, "LS_MNM", "LS MnM")
    _node(repo, e.entity_id, "LS_METALS", "LS MnM", node_id=n.node_id)

    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(_res, "ecm_resolver", EcmResolver(repo=repo))
        assert sc.resolve_scope_ref("LS_MNM") == n.node_id      # 옛 코드 → 정본
        assert n.node_id in sc.visible_scopes("LS_MNM")
