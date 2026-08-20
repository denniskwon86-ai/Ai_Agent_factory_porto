"""★★★ **조회 문맥·결과 상태 계약**을 검증한다. (2026-08-20 §7-0 산물)

## 이 파일이 지키는 한 가지

    같은 「없음」이 자리에 따라 **다른 답**이어야 한다.

        임의 조회인데 없다         → 없는 게 맞다. 빈 결과
        승인된 관계의 끝점인데 없다 → **무결성 장애.** 503

⚠️⚠️ 종전에는 둘 다 `None` 이었다. 그래서 **승인된 관계가 가리키는 자료가 사라진
  사고**가 화면에서는 「영향 경로 없음」이라는 평온한 사실로 보였다. 사람은 그것을
  읽고 「영향이 없구나」 하고 넘어간다.

★ 아래 시험은 목적 4종 × 상태 5종의 **판정표 전체**를 훑는다. 표의 칸 하나가 조용히
  뒤집히면 여기가 빨강이 된다.
"""
from dataclasses import dataclass

import pytest

from core import app_policy, ontology_resolve
from core.ontology_runtime import (ObjectRef, OntologyIntegrityError, OntologyRuntime,
                                   RelationProposal)

_PURPOSES = ontology_resolve.PURPOSES


def _scope(node="plant_demo", tenant="tenant_demo", mode="REAL"):
    return app_policy.ResourceScope(
        tenant_id=tenant, entity_mode=mode, scope_node_id=node,
        owner_dept_id="org_demo", binding_state=app_policy.BOUND, status="active")


# ── ResolveContext 자체 ──────────────────────────────────────────────────

def test_목적은_기본값을_갖지_않는다():
    """★★★ 「모르겠으면 ROOT_LOOKUP」 같은 기본값은 곧 **「모르겠으면 없는 것으로
    하라」**가 된다 — 그것이 이 계약이 생긴 이유다."""
    with pytest.raises(TypeError):
        ontology_resolve.ResolveContext()          # type: ignore[call-arg]


def test_모르는_목적은_거부한다():
    with pytest.raises(ValueError):
        ontology_resolve.ResolveContext(purpose="WHATEVER")


def test_없음이_정상인_자리는_하나뿐이다():
    """⚠️ 이 집합을 넓히는 것은 **조용한 실패를 하나 더 만드는 일**이다."""
    assert ontology_resolve.ABSENCE_IS_NORMAL == {ontology_resolve.ROOT_LOOKUP}
    for purpose in _PURPOSES:
        ctx = ontology_resolve.ResolveContext(purpose=purpose)
        assert ctx.absence_is_normal == (purpose == ontology_resolve.ROOT_LOOKUP)


# ── ObjectResolution 자체 ────────────────────────────────────────────────

def test_찾았다면서_범위가_없을_수_없다():
    """★ `FOUND` 인데 범위가 없으면 찾은 게 아니다.

    ⚠️ 여기서 막지 않으면 런타임이 `None` 범위로 PDP 를 부르고 **조용히 거부**된다 —
      「권한이 없다」로 보이지만 실제로는 해석기가 반쯤 답한 것이다."""
    with pytest.raises(ValueError):
        ontology_resolve.ObjectResolution(ontology_resolve.FOUND)


@pytest.mark.parametrize("status", [ontology_resolve.NOT_FOUND,
                                    ontology_resolve.UNAVAILABLE,
                                    ontology_resolve.AMBIGUOUS,
                                    ontology_resolve.UNBOUND])
def test_못_찾았다면서_범위를_들고_올_수_없다(status):
    with pytest.raises(ValueError):
        ontology_resolve.ObjectResolution(status, resource_scope=_scope())


def test_모르는_상태는_거부한다():
    with pytest.raises(ValueError):
        ontology_resolve.ObjectResolution("MAYBE")


def test_다섯_상태가_서로_다르다():
    """⚠️ 「없다·못 읽었다·후보가 둘·안 묶였다」는 서로 다른 사실이고 **사람이 할
    일도 다르다.** 하나로 뭉치면 아무도 무엇을 해야 할지 모른다."""
    assert len(set(ontology_resolve.RESOLUTION_STATUSES)) == 5


# ── 런타임 판정표 ────────────────────────────────────────────────────────

def _runtime(tmp_path, resolution):
    """항상 같은 답을 내는 해석기를 단 런타임."""
    def resolve(ref, ctx):
        return resolution
    return OntologyRuntime(
        str(tmp_path / "ontology.db"), resolve,
        lambda ledger_id, action, actor, target_type="", target_id="": True)


@dataclass
class _Scope:
    readable_dept_ids: frozenset = frozenset({"org_demo"})
    writable_dept_ids: frozenset = frozenset({"org_demo"})
    unrestricted: bool = False


def _subject():
    """★ `test_ontology_runtime.py` 와 **같은 모양**으로 만든다 — 시험마다 다른 주체를
    쓰면 「여기선 되는데 저기선 안 된다」의 원인이 통제인지 주체인지 알 수 없다."""
    return app_policy.Subject(
        user_id="buyer@example.com", scope=_Scope(),
        ctx={"tenant_id": "tenant_demo", "entity_mode": "REAL",
             "scope_node_id": "plant_demo"})


REF = ObjectRef("dataset", "shipment", "SHP-001")


@pytest.mark.parametrize("status,reason", [
    (ontology_resolve.NOT_FOUND, "없다"),
    (ontology_resolve.UNBOUND, "어느 인증판에도 안 묶였다"),
])
def test_임의_조회에서_없음은_빈_결과다(tmp_path, status, reason):
    """★ 사용자가 검색창에 아무 id 나 넣은 자리 — **없으면 없는 것**이다."""
    rt = _runtime(tmp_path, ontology_resolve.ObjectResolution(status, reason=reason))
    ctx = ontology_resolve.ResolveContext(purpose=ontology_resolve.ROOT_LOOKUP)
    assert rt._object_visible(_subject(), REF, ctx) is False


@pytest.mark.parametrize("purpose", [p for p in _PURPOSES
                                     if p != ontology_resolve.ROOT_LOOKUP])
@pytest.mark.parametrize("status", [ontology_resolve.NOT_FOUND,
                                    ontology_resolve.UNBOUND])
def test_승인된_자리에서_없음은_무결성_장애다(tmp_path, purpose, status):
    """★★★ **이 파일의 핵심.** 승인된 관계가 가리키는 자료가 사라진 것은 사고다.

    ⚠️ 이것이 «없음» 으로 접히면 화면이 「영향 경로 없음」을 그리고, 사람은 그것을
      **사실**로 읽는다."""
    rt = _runtime(tmp_path, ontology_resolve.ObjectResolution(status, reason="사라짐"))
    ctx = ontology_resolve.ResolveContext(purpose=purpose)
    with pytest.raises(OntologyIntegrityError) as err:
        rt._object_visible(_subject(), REF, ctx)
    #: ★ 사유가 남아야 사람이 무엇을 볼지 안다.
    assert status in str(err.value)
    assert purpose in str(err.value)


@pytest.mark.parametrize("purpose", _PURPOSES)
def test_못_읽음은_어느_자리에서나_장애다(tmp_path, purpose):
    """⚠️ 목적과 무관하다 — 못 읽은 것을 없는 것으로 접는 것이 P0-3 이었다."""
    rt = _runtime(tmp_path, ontology_resolve.unavailable("저장소가 응답하지 않음"))
    ctx = ontology_resolve.ResolveContext(purpose=purpose)
    with pytest.raises(OntologyIntegrityError):
        rt._object_visible(_subject(), REF, ctx)


@pytest.mark.parametrize("purpose", _PURPOSES)
def test_후보가_둘이면_어느_자리에서나_장애다(tmp_path, purpose):
    """★★★ 아무거나 고르면 **재실행 지문이 흔들린다** — 같은 질문에 다른 답이 된다.

    ⚠️ 「최신을 고르면 되지」가 특히 위험하다. 과거 시점 질의에 **오늘의 답**을 준다."""
    rt = _runtime(tmp_path, ontology_resolve.ambiguous(("ds_a", "ds_b"), "동점"))
    ctx = ontology_resolve.ResolveContext(purpose=purpose)
    with pytest.raises(OntologyIntegrityError) as err:
        rt._object_visible(_subject(), REF, ctx)
    #: ★ 사람이 무엇 중에서 골라야 하는지 보여야 한다.
    assert "ds_a" in str(err.value) and "ds_b" in str(err.value)


@pytest.mark.parametrize("purpose", _PURPOSES)
def test_찾았으면_권한은_PDP_가_정한다(tmp_path, purpose):
    """★ 대조군 — 통제가 **통과도 시킬 수 있어야** 한다.

    ⚠️⚠️ 그리고 권한 판정은 해석기가 아니라 PDP 의 일이다. 두 곳에서 판정하면 규칙이
      갈라지고, 갈라진 규칙은 언젠가 한쪽만 고쳐진다."""
    rt = _runtime(tmp_path, ontology_resolve.found(_scope()))
    ctx = ontology_resolve.ResolveContext(purpose=purpose)
    assert rt._object_visible(_subject(), REF, ctx) is True

    #: 남의 조직 것이면 **찾았어도** 안 보인다 — 막는 것은 PDP 다.
    rt2 = _runtime(tmp_path, ontology_resolve.found(_scope(node="남의공장")))
    assert rt2._object_visible(_subject(), REF, ctx) is False


# ── 봉인된 판 ────────────────────────────────────────────────────────────

def test_봉인된_판과_다른_판으로_답하면_장애다(tmp_path):
    """★★★ 승인 때 봉인한 판이 있으면 **그 판이어야 한다.**

    ⚠️ 다른 판으로 답하면 「그때 승인한 그 자료」가 아니게 되고 근거가 조용히 바뀐다 —
      감사에서 두 기록이 서로 다른 것을 가리킨다."""
    rt = _runtime(tmp_path, ontology_resolve.found(_scope(), snapshot_id="ds_새판"))
    ctx = ontology_resolve.ResolveContext(
        purpose=ontology_resolve.EVIDENCE_VALIDATION, required_snapshot_id="ds_봉인된판")
    with pytest.raises(OntologyIntegrityError) as err:
        rt._object_visible(_subject(), REF, ctx)
    assert "ds_봉인된판" in str(err.value)


def test_봉인된_판과_같으면_통과한다(tmp_path):
    """★ 대조군 — 봉인 검사가 **늘 막기만** 하면 그것은 검사가 아니다."""
    rt = _runtime(tmp_path, ontology_resolve.found(_scope(), snapshot_id="ds_봉인된판"))
    ctx = ontology_resolve.ResolveContext(
        purpose=ontology_resolve.EVIDENCE_VALIDATION, required_snapshot_id="ds_봉인된판")
    assert rt._object_visible(_subject(), REF, ctx) is True


def test_봉인을_요구하지_않으면_판을_따지지_않는다(tmp_path):
    """★ 조직 노드처럼 인증판에서 오지 않는 객체도 있다 — 그 자리까지 막으면
    검사가 늑대를 외친다."""
    rt = _runtime(tmp_path, ontology_resolve.found(_scope(), snapshot_id=""))
    ctx = ontology_resolve.ResolveContext(purpose=ontology_resolve.RELATION_ENDPOINT)
    assert rt._object_visible(_subject(), REF, ctx) is True


# ── 옛 계약을 조용히 받지 않는다 ─────────────────────────────────────────

@pytest.mark.parametrize("legacy", [None, "그냥 문자열"])
def test_옛_서명의_반환값을_조용히_받지_않는다(tmp_path, legacy):
    """★★★ 옛 해석기는 `ResourceScope | None` 을 돌려줬다.

    ⚠️⚠️ `None` 을 그대로 받으면 그것이 다시 «안 보임» 이 되어 **판정표가 통째로
      무력해진다.** 이식이 덜 끝난 해석기가 하나 남아 있으면, 그 namespace 만
      조용히 옛 동작으로 돌아간다 — 그리고 아무 시험도 빨강이 되지 않는다."""
    def legacy_resolver(ref, ctx):
        return legacy
    rt = OntologyRuntime(
        str(tmp_path / "ontology.db"), legacy_resolver,
        lambda ledger_id, action, actor, target_type="", target_id="": True)
    ctx = ontology_resolve.ResolveContext(purpose=ontology_resolve.ROOT_LOOKUP)
    with pytest.raises(OntologyIntegrityError):
        rt._object_visible(_subject(), REF, ctx)


def test_해석기가_없으면_빈_결과가_아니라_장애다(tmp_path):
    """⚠️ 「배선을 안 했다」가 「영향이 없다」로 보이면 안 된다."""
    rt = OntologyRuntime(str(tmp_path / "ontology.db"), None, None)
    ctx = ontology_resolve.ResolveContext(purpose=ontology_resolve.ROOT_LOOKUP)
    with pytest.raises(OntologyIntegrityError):
        rt._object_visible(_subject(), REF, ctx)


# ── 호출부가 실제로 문맥을 넘기는가 ──────────────────────────────────────

def test_뿌리와_순회가_서로_다른_목적으로_묻는다(tmp_path):
    """★★★ **계약이 있어도 호출부가 안 쓰면 소용없다.**

    ⚠️ 종전 판에서 실제로 그랬다 — 판정 규칙을 다 써 놓고 호출부는 옛 경로를 탔다.
      여기서는 런타임에 질의를 넣고 **해석기가 받은 목적을 모아** 확인한다."""
    seen = []

    def resolve(ref, ctx):
        seen.append((ref.key, ctx.purpose, ctx.as_of))
        return ontology_resolve.found(_scope())

    rt = OntologyRuntime(
        str(tmp_path / "ontology.db"), resolve,
        lambda ledger_id, action, actor, target_type="", target_id="": True)
    rt.find_paths(_subject(), [REF], ["shipment"], [], "2026-08-20T00:00:00")

    assert seen, "해석기가 한 번도 불리지 않았다 — 호출부가 문맥을 안 쓴다"
    purposes = {p for _, p, _ in seen}
    assert purposes == {ontology_resolve.ROOT_LOOKUP}, (
        f"뿌리 조회가 «{purposes}» 로 불렸다")
    #: ★ `as_of` 가 실제로 전달돼야 판을 고를 수 있다.
    assert all(a for _, _, a in seen), f"as_of 가 비어 있다: {seen}"


def test_제안은_제안_목적으로_묻는다(tmp_path):
    """★ 제안 시점의 판을 봐야 한다 — `effective_from` 이 그 관계가 서기 시작하는 때다."""
    seen = []

    def resolve(ref, ctx):
        seen.append(ctx)
        return ontology_resolve.found(_scope())

    rt = OntologyRuntime(
        str(tmp_path / "ontology.db"), resolve,
        lambda ledger_id, action, actor, target_type="", target_id="": True)
    proposal = RelationProposal(
        subject=REF, relation_type_id="AFFECTS",
        object=ObjectRef("dataset", "inventory_snapshot", "STK-1"),
        tenant_id="tenant_demo", enterprise_scope_id="plant_demo", entity_mode="REAL",
        owner_organization_id="org_demo", effective_from="2026-08-20T00:00:00",
        evidence_refs=("ds_1#row=7",))
    try:
        rt._assert_proposal_access(_subject(), proposal)
    except Exception:
        pass                                   # 접근 판정 자체는 다른 시험의 몫이다
    assert seen, "제안이 해석기를 부르지 않았다"
    assert {c.purpose for c in seen} == {ontology_resolve.RELATION_PROPOSAL}
    assert all(c.as_of == "2026-08-20T00:00:00" for c in seen), (
        f"제안 시점이 전달되지 않았다: {[c.as_of for c in seen]}")
    assert all(c.evidence_refs == ("ds_1#row=7",) for c in seen)
