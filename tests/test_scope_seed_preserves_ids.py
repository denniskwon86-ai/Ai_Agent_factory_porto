"""★★★ [D-018 ⑩] 시드·복원이 **기존 `node_id` 를 보존한다. 재생성하지 않는다.**

## 왜 이것이 D-018 의 마지막 조각인가

`node_id` 는 조직 범위의 **정본**이고 다른 저장소가 그 값으로 소유·권한을 기록한다
(`departments.scope_node_id` · `plan_facts.owner_organization_id` · 자산 `owner_scope_id` …).
시드가 «덮어쓰기» 를 «새로 만들기» 로 구현하면 그 참조가 **전부 끊긴다** — 그리고 끊긴 참조는
조용하다: 조회가 «없음» 을 돌려주고 그것은 «권한이 없다» 와 구분되지 않는다.

## 이 결함은 실제로 있었다

`seed_example_organization(force=True)` 가 `node_id` 를 주지 않아 새 id 를 만들려 했다.
D-018 ⑦(코드 유일성)이 그것을 `EcmError` 로 막아 **드러났다** — 막힌 것이 다행이다. 종전에는
같은 코드의 노드가 하나 더 생기고, 그 뒤로 코드 해석이 «모호» 로 거부됐을 것이다.

⚠️ **전체 테스트는 그때 통과했다.** `force=True` 경로를 검증하는 테스트가 없었기 때문이다.
  그래서 이 파일을 만든다 — 회귀를 잡는 것이 아니라 **회귀를 잡을 수 있게** 만드는 것이다.
"""
import pytest

from core.enterprise_context.repository import EcmRepository
from core.enterprise_context.seed import seed_example_organization


@pytest.fixture()
def repo(tmp_path):
    return EcmRepository(db_path=str(tmp_path / "ecm.db"))


def _snapshot(repo):
    return {n.code: n.node_id for n in repo.list_nodes() if n.code}


def _entity_count(repo):
    return len(repo._query("SELECT entity_id FROM enterprise_entities"))


# ── 시드 ──────────────────────────────────────────────────────────────────
def test_seed_is_idempotent_without_force(repo):
    """★ 두 번째 호출은 건너뛴다 — 운영 중 실제 조직을 시드가 덮으면 안 된다."""
    first = seed_example_organization(repo=repo)
    assert first["status"] == "seeded" and first["nodes"] > 0
    again = seed_example_organization(repo=repo)
    assert again["status"] == "skipped" and again["nodes"] == 0
    assert again["node_ids"], "건너뛸 때도 기존 id 를 알려줘야 호출부가 쓸 수 있다"


def test_force_reseed_preserves_every_node_id(repo):
    """★★★ **이 테스트가 이 파일의 핵심이다.** `force=True` 가 정본을 바꾸지 않는다.

    바뀌면 `departments.scope_node_id`·자산 `owner_scope_id`·계획 소유가 **전부 끊긴다.**"""
    seed_example_organization(repo=repo)
    before = _snapshot(repo)
    assert before, "시드가 노드를 만들지 않았다"

    result = seed_example_organization(repo=repo, force=True)
    assert result["status"] == "seeded"
    after = _snapshot(repo)

    assert set(before) == set(after), "코드 집합이 바뀌었다"
    changed = {c: (before[c], after[c]) for c in before if before[c] != after[c]}
    assert not changed, f"node_id 가 재생성됐다(정본이 끊긴다): {changed}"


def test_force_reseed_does_not_multiply_nodes(repo):
    """★★ 노드가 늘지 않는다 — 늘면 같은 코드가 둘이 되고 코드 해석이 «모호» 로 거부된다."""
    seed_example_organization(repo=repo)
    n_before = len(repo.list_nodes())
    seed_example_organization(repo=repo, force=True)
    assert len(repo.list_nodes()) == n_before


def test_force_reseed_does_not_orphan_entities(repo):
    """★★ 엔티티도 재사용한다.

    새로 만들면 노드가 새 엔티티를 가리키고 **옛 엔티티는 고아**가 된다. `entity_mode` 로 문맥을
    판정하므로(실제/가상/경쟁사) 고아 엔티티는 조용한 오염이다."""
    seed_example_organization(repo=repo)
    e_before = _entity_count(repo)
    seed_example_organization(repo=repo, force=True)
    assert _entity_count(repo) == e_before, "엔티티가 늘었다 — 옛 엔티티가 고아가 됐다"


def test_force_reseed_still_updates_content(repo):
    """★ 보존은 **id 만**이다 — 내용(이름·부서 매핑)은 시드 정의대로 갱신돼야 한다.
    그러지 않으면 `force` 가 아무 일도 하지 않는 것이 된다."""
    from core.enterprise_context.models import STATUS_ACTIVE, OrganizationNode
    seed_example_organization(repo=repo)
    node = next(n for n in repo.list_nodes() if n.code == "LS_MNM")
    # 사람이 이름을 잘못 고친 상태를 만든다.
    repo.upsert_node(OrganizationNode(
        node_id=node.node_id, entity_id=node.entity_id, tenant_id=node.tenant_id,
        node_type=node.node_type, code=node.code, name_ko="잘못된 이름",
        dept_id=node.dept_id, status=STATUS_ACTIVE))
    assert repo.get_node(node.node_id).name_ko == "잘못된 이름"

    seed_example_organization(repo=repo, force=True)
    restored = repo.get_node(node.node_id)
    assert restored.name_ko != "잘못된 이름", "force 가 내용을 되돌리지 않았다"
    assert restored.node_id == node.node_id, "내용을 되돌리면서 id 를 바꿨다"


def test_force_reseed_keeps_edges_consistent(repo):
    """엣지도 같은 노드를 가리켜야 한다 — 노드 id 가 보존되므로 엣지가 끊기지 않는다."""
    seed_example_organization(repo=repo)
    before = {(r["from_node_id"], r["to_node_id"], r["relation_type"])
              for r in repo._query("SELECT from_node_id, to_node_id, relation_type "
                                   "FROM organization_edges")}
    seed_example_organization(repo=repo, force=True)
    after = {(r["from_node_id"], r["to_node_id"], r["relation_type"])
             for r in repo._query("SELECT from_node_id, to_node_id, relation_type "
                                  "FROM organization_edges")}
    assert before == after, f"엣지가 바뀌었다 — 상속이 끊긴다. 차이={before ^ after}"


# ── 노드는 지워지지 않는다 ────────────────────────────────────────────────
def test_no_code_path_deletes_nodes():
    """★★★ **노드를 지우는 경로가 없어야 한다.**

    ECM 노드는 상태 변경(`status`)으로만 폐지된다. 행을 지우면 그 id 를 가리키는 소유·권한
    기록이 «없는 조직» 을 가리키게 되고, 그때 fail-closed 는 «아무에게도 보이지 않음» 이다.
    ⚠️ 이 테스트는 소스를 본다 — 동작 테스트로는 «아직 그런 코드가 없다» 를 확인할 수 없다."""
    import glob
    import io
    hits = []
    for f in glob.glob("core/**/*.py", recursive=True) + glob.glob("api/**/*.py", recursive=True) \
            + glob.glob("scripts/**/*.py", recursive=True):
        s = io.open(f, encoding="utf-8").read()
        for table in ("organization_nodes", "enterprise_entities"):
            if f"DELETE FROM {table}" in s or f"DROP TABLE {table}" in s:
                hits.append(f"{f}: {table}")
    assert not hits, f"노드·엔티티를 지우는 코드가 생겼다: {hits}"
