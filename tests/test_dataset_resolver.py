"""★★★ **Dataset Resolver** 를 검증한다. (§7 4단계)

## 이 파일이 지키는 것

    ① 업무 ID(`SHP-…`)로 실제 범위를 찾아낸다 — 인증판 ID 를 넣지 않는다
    ② `as_of` 로 판을 고른다 · 동점이면 `AMBIGUOUS`
    ③ 「없다」·「그 시점엔 아직」·「못 읽었다」를 **가른다**
    ④ 권한 판정은 하지 않는다 — PDP 의 일이다
    ⑤ 봉인된 판과 다르면 런타임이 막는다

⚠️⚠️ 종전 구현은 업무 레코드 ID 를 그대로 `get_snapshot()` 에 넣었다. **영영 못 찾는데
  결과가 `None`** 이라 「범위 밖」과 구분되지 않았고, 나는 그것을 «배선 완료» 로
  보고했다. 이 파일은 그 보고가 다시 나오지 않게 한다 — **실제로 찾아내는지**를 본다.
"""
import csv
import io as _io

import pytest

from core import app_policy, ontology_resolve
from core import ontology_resolvers as R
from core.data_preparation import models as m
from core.data_preparation import scope_index as ix
from core.data_preparation import snapshot_service as svc
from core.data_preparation import store as dp_store
from core.ontology_runtime import ObjectRef, OntologyIntegrityError, OntologyRuntime

TENANT = "tenant-demo"
SCOPE = "plant-demo"
COLUMNS = ["shipment_id", "po_line_id", "tenant_id", "scope_node_id", "etd"]


def _rows(n=3, scope=SCOPE):
    return [{"shipment_id": f"SHP-{i:06d}", "po_line_id": f"PO-{i:06d}-10",
             "tenant_id": TENANT, "scope_node_id": scope, "etd": "2026-03-01"}
            for i in range(1, n + 1)]


def _csv(rows):
    buf = _io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


@pytest.fixture
def indexed(tmp_path, monkeypatch):
    """제품 싱글턴을 격리 저장소로 돌리고, 인증판 하나를 세운다.

    ★ **제품이 실제로 쓰는 싱글턴**(`data_preparation_store`)을 쓴다. 시험만의 저장소를
      따로 만들면 「시험에서는 되는데 제품에서는 안 되는」 배선을 못 잡는다."""
    store = dp_store.data_preparation_store
    monkeypatch.setattr(store, "db_path", str(tmp_path / "dp.db"), raising=False)
    monkeypatch.setattr(store, "_prepared_for", None, raising=False)

    def certify(rows, *, certified_at=None, key="LOG-02"):
        inst = store.create_instance(
            kit_id="KIT-T", version="1.0.0", kit_fingerprint="fp",
            tenant_id=TENANT, scope_node_id=SCOPE, entity_mode="VIRTUAL")
        b = store.create_binding(
            instance_id=inst["instance_id"], dataset_contract_key=key,
            provider=m.PROVIDER_FILE_SNAPSHOT, config={},
            tenant_id=TENANT, scope_node_id=SCOPE, entity_mode="VIRTUAL")
        for target in (m.VALIDATED, m.APPROVED, m.ACTIVE):
            b = store.transition(b["binding_id"], target)
        snap = svc.ingest(store, binding=b, payload=_csv(rows), file_name=f"{key}.csv",
                          workspace_root=str(tmp_path / "raw"))
        final = svc.run_pipeline(store, snap["snapshot_id"], rows, COLUMNS,
                                 control={"row_count": len(rows)})
        if certified_at:
            with store.transaction() as conn:
                conn.execute("UPDATE dataset_snapshots SET certified_at=? "
                             "WHERE snapshot_id=?", (certified_at, final["snapshot_id"]))
                conn.execute("UPDATE object_scope_index SET certified_at=? "
                             "WHERE snapshot_id=?", (certified_at, final["snapshot_id"]))
            final = store.get_snapshot(final["snapshot_id"])
        return final

    return certify


def _ctx(purpose=ontology_resolve.ROOT_LOOKUP, **kw):
    """★ 정체성 두 값을 **기본으로 채운다** — 실제 런타임이 주체 문맥에서 채우는 것과 같다.

    ⚠️ 채우지 않은 문맥을 시험 기본값으로 두면, 「문맥이 반쪽일 때 막힌다」는 통제가
      시험 전체를 빨갛게 만들어 **그 통제를 지우고 싶어진다.**"""
    kw.setdefault("tenant_id", TENANT)
    kw.setdefault("entity_mode", "VIRTUAL")
    return ontology_resolve.ResolveContext(purpose=purpose, **kw)


SHIP = ObjectRef("dataset", "shipment", "SHP-000001")


# ── ① 실제로 찾아낸다 ───────────────────────────────────────────────────

def test_업무_ID_로_실제_범위를_찾아낸다(indexed):
    """★★★ **이 파일의 존재 이유.** 종전에는 못 찾으면서 `None` 을 돌려줬다."""
    snap = indexed(_rows())
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.status == ontology_resolve.FOUND, res
    assert res.resource_scope.tenant_id == TENANT
    assert res.resource_scope.scope_node_id == SCOPE
    #: ★ 판·근거·성격이 함께 온다 — 나중에 「무엇으로 만든 답인가」에 답하기 위해서다.
    assert res.snapshot_id == snap["snapshot_id"]
    assert "line=2" in res.row_evidence
    assert res.data_kind == m.DATA_KIND_DEMO


def test_인증판_ID_를_넣으면_찾지_못한다(indexed):
    """★★★ 업무 ID 와 인증판 ID 는 **다른 것**이다.

    ⚠️ 종전 구현은 이 둘을 섞었다. 섞으면 영영 못 찾는데 결과가 「안 보임」과 같아서,
      화면이 「영향 경로 없음」을 그리고 사람은 그것을 사실로 읽는다."""
    snap = indexed(_rows())
    res = R.product_object_scope_resolver(
        ObjectRef("dataset", "shipment", snap["snapshot_id"]), _ctx())
    assert res.status == ontology_resolve.NOT_FOUND, res


def test_행마다_다른_조직_범위가_그대로_온다(indexed):
    """★ 범위는 인증판이 아니라 **행**이 말한다."""
    rows = _rows(3)
    rows[2]["scope_node_id"] = "plant-다른공장"
    indexed(rows)
    a = R.product_object_scope_resolver(SHIP, _ctx())
    b = R.product_object_scope_resolver(
        ObjectRef("dataset", "shipment", "SHP-000003"), _ctx())
    assert a.resource_scope.scope_node_id == SCOPE
    assert b.resource_scope.scope_node_id == "plant-다른공장"


# ── ② as_of 로 판을 고른다 ──────────────────────────────────────────────

def test_as_of_가_판을_고른다(indexed):
    """★★★ 「그냥 최신」이면 **과거 시점 질의에 오늘의 답**을 준다."""
    old = indexed(_rows(2), certified_at="2026-03-01T00:00:00+00:00")
    new = indexed(_rows(3), certified_at="2026-06-01T00:00:00+00:00")
    res = R.product_object_scope_resolver(
        SHIP, _ctx(as_of="2026-04-01T00:00:00+00:00"))
    assert res.status == ontology_resolve.FOUND
    assert res.snapshot_id == old["snapshot_id"], "as_of 를 무시하고 최신을 골랐다"

    later = R.product_object_scope_resolver(
        SHIP, _ctx(as_of="2026-07-01T00:00:00+00:00"))
    assert later.snapshot_id == new["snapshot_id"], "대조군 — 늘 옛 판만 고르면 그것도 틀렸다"


def test_같은_시각의_판이_둘이면_고르지_않는다(indexed):
    """⚠️ 임의로 고르면 같은 질문의 답이 실행마다 달라진다."""
    same = "2026-05-01T00:00:00+00:00"
    a = indexed(_rows(2), certified_at=same)
    b = indexed(_rows(2), certified_at=same)
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.status == ontology_resolve.AMBIGUOUS, res
    assert set(res.candidates) == {a["snapshot_id"], b["snapshot_id"]}


# ── ③ 「모른다」의 종류를 가른다 ────────────────────────────────────────

def test_없음과_미결속과_못읽음이_서로_다르다(indexed, monkeypatch):
    """★★★ 넷은 서로 다른 사실이고 **사람이 할 일도 다르다.**

    ⚠️ 하나로 뭉치면 아무도 무엇을 해야 할지 모른다."""
    indexed(_rows(2), certified_at="2026-06-01T00:00:00+00:00")

    missing = R.product_object_scope_resolver(
        ObjectRef("dataset", "shipment", "SHP-없는배"), _ctx())
    assert missing.status == ontology_resolve.NOT_FOUND

    early = R.product_object_scope_resolver(
        SHIP, _ctx(as_of="2026-01-01T00:00:00+00:00"))
    assert early.status == ontology_resolve.UNBOUND

    def boom(*a, **k):
        raise RuntimeError("저장소가 응답하지 않습니다")

    monkeypatch.setattr(ix, "lookup", boom)
    broken = R.product_object_scope_resolver(SHIP, _ctx())
    assert broken.status == ontology_resolve.UNAVAILABLE

    assert len({missing.status, early.status, broken.status}) == 3


# ── ④ 권한은 PDP 가 정한다 ──────────────────────────────────────────────

class _Scope:
    def __init__(self, depts=(), unrestricted=False):
        self.readable_dept_ids = frozenset(depts)
        self.writable_dept_ids = frozenset(depts)
        self.unrestricted = unrestricted


def _subject(depts=(), unrestricted=True, selected=SCOPE):
    """★★★ [4.1b-0] 부서 집합에 **조직 노드 ID 를 넣지 않는다.**

    ⚠️⚠️ 종전 시험은 `readable_dept_ids` 에 `plant-demo`(조직 노드)를 넣어 통과시켰다.
      실제 `org_directory.resolve_scope()` 는 거기에 **부서 ID** 를 넣는다 — 시험이
      제품과 다른 세계에서 돌고 있었다.

    ★ 시연 데이터에 소유 부서가 없으므로, 조직 경계 자체를 보려면 `unrestricted` 를
      써야 한다. **그것이 지금의 사실**이고, 부서 결속이 생기면 이 기본값을 되돌린다."""
    return app_policy.Subject(
        user_id="u@example.com", scope=_Scope(depts, unrestricted),
        ctx={"tenant_id": TENANT, "entity_mode": "VIRTUAL",
             "scope_node_id": selected})


def test_해석기는_권한을_판정하지_않는다(indexed):
    """★★★ 남의 조직 것이어도 해석기는 **찾았다**고 답한다 — 막는 것은 PDP 다.

    ⚠️ 두 곳에서 권한을 판정하면 규칙이 갈라지고, 갈라진 규칙은 언젠가 한쪽만 고쳐진다."""
    rows = _rows(1, scope="plant-남의공장")
    indexed(rows)
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.status == ontology_resolve.FOUND
    assert res.resource_scope.scope_node_id == "plant-남의공장"


def test_런타임에서는_남의_조직_것이_안_보인다(indexed, tmp_path):
    """★ 그리고 실제로 **막힌다** — 해석기가 찾아도 PDP 가 거른다."""
    indexed(_rows(1, scope="plant-남의공장"))
    rt = OntologyRuntime(str(tmp_path / "ontology.db"),
                         R.product_object_scope_resolver,
                         lambda *a, **k: True)
    ctx = _ctx()
    #: ★ 조직 노드 경계는 `_scope_covers` 가 본다 — 선택한 문맥과 다른 노드는 막힌다.
    assert rt._object_visible(_subject(selected=SCOPE), SHIP, ctx) is False

    #: ★ 대조군 — 내 조직 것이면 보여야 한다. 늘 막히면 통제가 아니라 고장이다.
    indexed([{"shipment_id": "SHP-내것", "po_line_id": "PO-1-10",
              "tenant_id": TENANT, "scope_node_id": SCOPE, "etd": "2026-03-01"}])
    mine = ObjectRef("dataset", "shipment", "SHP-내것")
    assert rt._object_visible(_subject(selected=SCOPE), mine, ctx) is True


# ── ⑤ 문맥에 따라 「없음」의 뜻이 달라진다 ──────────────────────────────

def test_승인된_끝점이_사라지면_무결성_장애다(indexed, tmp_path):
    """★★★ 같은 「없음」이 자리에 따라 다른 답이어야 한다.

    ⚠️⚠️ 임의 조회면 빈 결과가 맞지만, **승인된 관계의 끝점**이면 자료가 사라진 사고다."""
    indexed(_rows(1))
    rt = OntologyRuntime(str(tmp_path / "ontology.db"),
                         R.product_object_scope_resolver, lambda *a, **k: True)
    gone = ObjectRef("dataset", "shipment", "SHP-사라진배")

    assert rt._object_visible(_subject(), gone, _ctx()) is False        # 임의 조회
    with pytest.raises(OntologyIntegrityError):
        rt._object_visible(_subject(), gone,
                           _ctx(purpose=ontology_resolve.RELATION_ENDPOINT))


def test_봉인된_판과_다르면_막힌다(indexed, tmp_path):
    """⚠️ 다른 판으로 답하면 「그때 승인한 그 자료」가 아니게 된다."""
    snap = indexed(_rows(1))
    rt = OntologyRuntime(str(tmp_path / "ontology.db"),
                         R.product_object_scope_resolver, lambda *a, **k: True)
    ok = _ctx(purpose=ontology_resolve.EVIDENCE_VALIDATION,
              required_snapshot_id=snap["snapshot_id"])
    assert rt._object_visible(_subject(selected=SCOPE), SHIP, ok) is True

    bad = _ctx(purpose=ontology_resolve.EVIDENCE_VALIDATION,
               required_snapshot_id="ds_다른판")
    with pytest.raises(OntologyIntegrityError):
        rt._object_visible(_subject(), SHIP, bad)


# ── ⑥ 배선 사실 자체 ────────────────────────────────────────────────────

def test_dataset_은_더_이상_미배선이_아니다():
    """★ 배선 표와 실제 동작이 함께 움직이는지 본다."""
    assert "dataset" in R._RESOLVERS
    src = R.__file__
    assert R._RESOLVERS["dataset"].__name__ == "_resolve_dataset", src


def test_다른_다섯_namespace_는_아직_미배선이다():
    """⚠️ 배선되지 않은 것을 «통과» 로 두지 않는다 — 승인 없는 관계가 그 자리로 들어온다."""
    for namespace in ("mdm", "external", "g4", "decision", "knowledge"):
        res = R.product_object_scope_resolver(
            ObjectRef(namespace, "some_type", "some_id"), _ctx())
        assert res.status == ontology_resolve.UNAVAILABLE, f"{namespace}: {res}"


def test_문맥이_반쪽이면_전부_뒤지지_않는다(indexed):
    """★★★ [P0] 문맥에 tenant·entity_mode 가 없으면 **막는다.**

    ⚠️⚠️ 없다고 「전부 뒤진다」로 넓히면 그 순간 **회사 경계가 사라진다.** 남의 회사
      `SHP-000001` 이 우리 답으로 돌아오고, 행 수도 화면도 멀쩡하다.
    ★ 모르면 막는다 — 이 저장소의 fail-closed 규칙이 여기에도 그대로 적용된다."""
    indexed(_rows())
    for missing in ({"tenant_id": ""}, {"entity_mode": ""}, {"tenant_id": "", "entity_mode": ""}):
        ctx = ontology_resolve.ResolveContext(
            purpose=ontology_resolve.ROOT_LOOKUP,
            tenant_id=missing.get("tenant_id", TENANT),
            entity_mode=missing.get("entity_mode", "VIRTUAL"))
        res = R.product_object_scope_resolver(SHIP, ctx)
        assert res.status == ontology_resolve.UNAVAILABLE, f"{missing}: {res}"


def test_런타임이_주체_문맥에서_정체성을_채운다(indexed, tmp_path):
    """★★★ [P0] 계약을 만들어도 **런타임이 안 채우면 소용없다.**

    ⚠️ 첫 판에서 실제로 그랬다 — `_identity()` 를 빈 값으로 되돌리는 변이가 살아남았다.
      시험들이 문맥을 **직접** 만들어 넘겼기 때문에 런타임이 채우는 경로를 아무도
      지나가지 않았다.
    ★ 그래서 여기서는 `find_paths` 로 **런타임을 통해** 들어가 본다."""
    indexed(_rows())
    seen = []

    def spy(ref, ctx):
        seen.append(ctx)
        return R.product_object_scope_resolver(ref, ctx)

    rt = OntologyRuntime(str(tmp_path / "ontology.db"), spy, lambda *a, **k: True)
    rt.find_paths(_subject(), [SHIP], ["shipment"], [], "2026-12-01T00:00:00")

    assert seen, "해석기가 한 번도 불리지 않았다"
    assert all(c.tenant_id == TENANT for c in seen), (
        f"런타임이 tenant 를 안 넘긴다: {[c.tenant_id for c in seen]}")
    assert all(c.entity_mode == "VIRTUAL" for c in seen), (
        f"런타임이 entity_mode 를 안 넘긴다: {[c.entity_mode for c in seen]}")


# ══════════════════════════════════════════════════════════════════════════
# 4.1b-0 — 조직 노드와 소유 부서는 다른 것이다 (2026-08-21)
# ══════════════════════════════════════════════════════════════════════════

def test_조직_노드를_부서_칸에_넣지_않는다(indexed):
    """★★★ **타입 혼동.** `scope_node_id` 는 ECM 조직 노드이고 `owner_dept_id` 는
    `org_directory` 의 **부서**다.

    ⚠️⚠️ 종전에는 `owner_dept_id=scope_node_id` 로 채웠다. PDP 는
      `owner_dept_id in readable_dept_ids` 를 보는데 그 집합은 **부서 ID** 로 만들어진다.
      그래서 시험이 노드 ID 로 가짜 Scope 를 만들어 통과시키고 있었고, 그것은 **실제
      제품 권한과 다른 세계**였다.

    ★ 실제 사용자는 `org_directory.resolve_scope()` 로 부서 집합을 받는다 — 거기에
      `plant-afs-*` 같은 노드 ID 는 들어 있지 않다."""
    indexed(_rows())
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.status == ontology_resolve.FOUND
    assert res.resource_scope.scope_node_id == SCOPE
    assert res.resource_scope.owner_dept_id != res.resource_scope.scope_node_id, (
        "조직 노드가 부서 칸에 들어갔다 — 실제 권한과 다른 세계가 된다")


def test_소유_부서가_없으면_PDP_가_막는다(indexed):
    """★★★ 시연 데이터에는 아직 부서 칸이 없다. 그래서 **막힌다 — 그것이 맞다.**

    ⚠️ D-014: 미지정은 전사 공용이 아니라 **비노출**이다. 「모르니까 통과」로 두면
      그 자원이 어느 조직 것이었는지 아무도 모르는 채 열린다.
    ★ 사유가 `RESOURCE_UNBOUND` 인 것이 중요하다 — 「권한 없음」과 다른 말이고,
      사람이 할 일도 다르다(소유를 정해야 한다)."""
    indexed(_rows())
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.resource_scope.owner_dept_id == ""

    #: 노드 ID 로 만든 «가짜» Scope — 종전에는 이것이 통과했다.
    class _NodeScope:
        readable_dept_ids = frozenset({SCOPE})
        writable_dept_ids = frozenset({SCOPE})
        unrestricted = False

    subject = app_policy.Subject(
        user_id="u@example.com", scope=_NodeScope(),
        ctx={"tenant_id": TENANT, "entity_mode": "VIRTUAL", "scope_node_id": ""})
    decision = app_policy.decide(subject, res.resource_scope, app_policy.READ)
    assert decision.allowed is False, "노드 ID 로 만든 가짜 권한이 통과했다"
    assert decision.reason == app_policy.DENY_UNBOUND, decision.reason


def test_색인이_소유_부서_칸을_따로_갖는다():
    """★ 표에 자리가 있어야 나중에 **행이 말할 수 있다.** 없으면 또 노드 ID 를 빌려 쓴다."""
    from core.data_preparation import store as dp_store_mod

    ddl = dp_store_mod.__file__
    from pathlib import Path
    src = Path(ddl).read_text(encoding="utf-8")
    assert "owner_dept_id" in src, "색인에 소유 부서 칸이 없다"


# ── ★★★ [G2 Ownership Binding] 소유는 «승인된 결속» 에서만 온다 ────────────
#
# 계약: (tenant_id, entity_mode, dataset_contract_key, scope_node_id, 유효기간)
#         → owner_dept_id
#
# ⚠️⚠️ 업무 데이터 행이 선언하지 않는다. 자기 데이터의 권한 범위를 데이터가 스스로 정하면
#   그것이 곧 자기진술 통제다 — `calc_binding` 과 같은 유형이고, 그 이유로 이미 한 번 지웠다.

OWN_COLUMNS = COLUMNS + ["owner_dept_id"]


def _rows_declaring_owner(dept, n=3, scope=SCOPE):
    """업무 행이 **스스로** 소유 부서를 적은 자료. 색인은 이것을 읽지 않아야 한다."""
    return [{**r, "owner_dept_id": dept} for r in _rows(n, scope)]


def _csv_with_owner(rows):
    buf = _io.StringIO()
    w = csv.DictWriter(buf, fieldnames=OWN_COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _declare_owner(store, dept, *, key="LOG-02", scope=SCOPE, mode="VIRTUAL", **kw):
    from core.data_preparation import ownership_binding as ob
    with store.transaction() as conn:
        return ob.declare(conn, tenant_id=TENANT, entity_mode=mode,
                          dataset_contract_key=key, scope_node_id=scope,
                          owner_dept_id=dept, approved_by="approver@afs.invalid",
                          evidence_ref="FND-01/v1#seed", **kw)


def test_업무_행이_소유_부서를_적어도_색인은_읽지_않는다(indexed, monkeypatch, capsys):
    """★★★ 계약 ⑩ — 행의 선언은 **무시된다.**

    ⚠️ 거부가 아니라 무시로 둔 이유: 그 열이 우연히 섞인 판 전체가 인증되지 못하면, 다음
      사람은 열을 지우는 대신 **이 검사를 끄는 쪽**을 택한다. 다만 조용히 넘기지도 않는다 —
      무시한 횟수를 소리 내어 남긴다."""
    import core.data_preparation.scope_index as si
    monkeypatch.setattr(si, "rows_from_raw",
                        lambda raw, checksum: (_rows_declaring_owner("sales"), OWN_COLUMNS))
    indexed(_rows())
    out = capsys.readouterr().out
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.resource_scope.owner_dept_id != "sales", (
        "업무 행이 적은 소유 부서가 색인에 들어갔다 — 데이터가 자기 권한을 정한 것이다")
    assert res.resource_scope.owner_dept_id == "", "결속이 없으면 비어 있어야 한다"
    assert "무시" in out, "무시했다는 사실을 남기지 않았다"


def test_승인된_결속이_있으면_색인에_물질화되고_봉인된다(indexed, monkeypatch):
    """★ 정본 → 색인. 그리고 **어느 결속에서 나왔는지**가 함께 봉인된다."""
    from core.data_preparation import store as dp
    b = _declare_owner(dp.data_preparation_store, "hq")
    #: ⚠️ 부트스트랩(조직 미도입)이면 부서 검사를 **통째로 건너뛴다** — 그 상태로 시험하면
    #:   「폐지된 부서를 막는다」 계약이 검사되지 않는다. 현실에 없는 모양으로 시험하는 셈이다.
    monkeypatch.setattr(_org(), "is_bootstrap", lambda: False)
    monkeypatch.setattr(_org(), "get_department",
                        lambda d: {"dept_id": d, "status": "active"}, raising=False)
    indexed(_rows())
    with dp.data_preparation_store.transaction() as conn:
        row = dict(conn.execute(
            "SELECT owner_dept_id, owner_binding_id, owner_binding_fingerprint "
            "FROM object_scope_index LIMIT 1").fetchone())
    assert row["owner_dept_id"] == "hq"
    assert row["owner_binding_id"] == b["binding_id"]
    assert row["owner_binding_fingerprint"] == b["fingerprint"]


def test_철회하면_색인이_남아_있어도_막힌다(indexed, monkeypatch):
    """★★★ 계약 ⑥ — **색인이 있어도 요청 시 다시 검증한다.**

    ⚠️ 물질화 시점의 판단을 영구히 믿으면 그것이 곧 「회수해도 계속 유효한 권한」이다 —
      SSE 티켓에서 이미 같은 실수를 고쳤다."""
    from core.data_preparation import ownership_binding as ob
    from core.data_preparation import store as dp
    #: ⚠️ 부트스트랩(조직 미도입)이면 부서 검사를 **통째로 건너뛴다** — 그 상태로 시험하면
    #:   「폐지된 부서를 막는다」 계약이 검사되지 않는다. 현실에 없는 모양으로 시험하는 셈이다.
    monkeypatch.setattr(_org(), "is_bootstrap", lambda: False)
    monkeypatch.setattr(_org(), "get_department",
                        lambda d: {"dept_id": d, "status": "active"}, raising=False)
    b = _declare_owner(dp.data_preparation_store, "hq")
    indexed(_rows())
    assert R.product_object_scope_resolver(SHIP, _ctx()).resource_scope.owner_dept_id == "hq"

    with dp.data_preparation_store.transaction() as conn:
        ob.revoke(conn, b["binding_id"], "auditor@afs.invalid", "근거 미비")
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.resource_scope.owner_dept_id == "", "철회 뒤에도 소유 부서가 살아 있다"


def test_부서가_폐지되면_색인이_있어도_503(indexed, monkeypatch):
    """계약 ⑦ — 결속은 있는데 가리키는 곳이 없다. 「안 보인다」가 아니라 **고쳐야 할 것**이다."""
    from core.data_preparation import store as dp
    #: ⚠️ 부트스트랩(조직 미도입)이면 부서 검사를 **통째로 건너뛴다** — 그 상태로 시험하면
    #:   「폐지된 부서를 막는다」 계약이 검사되지 않는다. 현실에 없는 모양으로 시험하는 셈이다.
    monkeypatch.setattr(_org(), "is_bootstrap", lambda: False)
    monkeypatch.setattr(_org(), "get_department",
                        lambda d: {"dept_id": d, "status": "active"}, raising=False)
    _declare_owner(dp.data_preparation_store, "hq")
    indexed(_rows())
    monkeypatch.setattr(_org(), "get_department",
                        lambda d: {"dept_id": d, "status": "retired"}, raising=False)
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.status == ontology_resolve.UNAVAILABLE, res.status


def test_실제_조직도_Principal_로_PDP_를_대조한다(indexed, monkeypatch):
    """★★★ 계약 ⑪ — **가짜 Scope 가 아니라 제품이 만드는 Principal** 로 본다.

    ⚠️⚠️ 이 세션에서 시험 두 건이 «노드 ID 로 만든 가짜 부서 권한» 으로 통과하고 있었다.
      그래서 여기서는 `org_directory.resolve_scope()` 가 실제로 돌려주는 객체를 쓴다 —
      그 집합은 **부서 ID** 로 만들어지고, 노드 ID 는 들어 있지 않다."""
    from core.data_preparation import store as dp
    from core import app_policy
    #: ⚠️ 부트스트랩(조직 미도입)이면 부서 검사를 **통째로 건너뛴다** — 그 상태로 시험하면
    #:   「폐지된 부서를 막는다」 계약이 검사되지 않는다. 현실에 없는 모양으로 시험하는 셈이다.
    monkeypatch.setattr(_org(), "is_bootstrap", lambda: False)
    monkeypatch.setattr(_org(), "get_department",
                        lambda d: {"dept_id": d, "status": "active"}, raising=False)
    _declare_owner(dp.data_preparation_store, "hq")
    indexed(_rows())
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.resource_scope.owner_dept_id == "hq"

    #: 제품 경로로 만든 권한. 부서를 가진 사람과 못 가진 사람을 나란히 본다.
    class _Scope:
        def __init__(self, depts):
            self.readable_dept_ids = frozenset(depts)
            self.writable_dept_ids = frozenset(depts)
            self.unrestricted = False

    ctxd = {"tenant_id": TENANT, "entity_mode": "VIRTUAL", "scope_node_id": ""}
    allowed = app_policy.decide(
        app_policy.Subject(user_id="a@example.com", scope=_Scope({"hq"}), ctx=ctxd),
        res.resource_scope, app_policy.READ)
    denied = app_policy.decide(
        app_policy.Subject(user_id="b@example.com", scope=_Scope({"sales"}), ctx=ctxd),
        res.resource_scope, app_policy.READ)
    assert allowed.allowed is True, allowed.reason
    assert denied.allowed is False, "다른 부서 사람이 통과했다"


def test_다른_계약키의_결속은_물질화되지_않는다(indexed, monkeypatch):
    """계약 ⑤ — 다른 scope·계약의 결속을 재사용하지 않는다. SLS-01 결속으로 LOG-02 가
    소유자를 얻으면, 승인 하나가 계약 경계를 넘는 것이다."""
    from core.data_preparation import store as dp
    #: ⚠️ 부트스트랩(조직 미도입)이면 부서 검사를 **통째로 건너뛴다** — 그 상태로 시험하면
    #:   「폐지된 부서를 막는다」 계약이 검사되지 않는다. 현실에 없는 모양으로 시험하는 셈이다.
    monkeypatch.setattr(_org(), "is_bootstrap", lambda: False)
    monkeypatch.setattr(_org(), "get_department",
                        lambda d: {"dept_id": d, "status": "active"}, raising=False)
    _declare_owner(dp.data_preparation_store, "sales", key="SLS-01")
    indexed(_rows())                                  # 색인 대상은 LOG-02
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.resource_scope.owner_dept_id == "", "다른 계약키의 결속이 새어 들어왔다"


def _org():
    from core.org_directory import org_directory
    return org_directory
