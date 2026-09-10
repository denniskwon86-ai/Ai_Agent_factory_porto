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


def _register_test_kit(store, kit_id="KIT-T", version="1.0.0"):
    """시험용 키트를 **등록부에 올리고** 그 지문을 돌려준다.

    ★★★ [M0-3.1 ④] `create_instance` 는 이제 등록된 판본만 받는다. 임의 지문을 적으면
      거부된다 — 앞서 시험이 `fp` 같은 값으로 인증판을 쌓을 수 있었고, 그 위에서
      「정본 계약을 썼다」고 말할 수 없었다.
    ⚠️ 지문을 손으로 적지 않는다. 등록 결과에서 읽는다."""
    store.upsert_kit_version(
        kit_id=kit_id, version=version, name=f"{kit_id} 시험용",
        mode="DEMO/SYNTHETIC", source_path=f"{kit_id}.test.json",
        fingerprint_value=f"fp-test-{kit_id}-{version}", profile={"datasets": []})
    return store.get_kit_version(kit_id, version)["fingerprint"]


def _rows(n=3, scope=SCOPE):
    return [{"shipment_id": f"SHP-{i:06d}", "po_line_id": f"PO-{i:06d}-10",
             "tenant_id": TENANT, "scope_node_id": scope, "etd": "2026-03-01"}
            for i in range(1, n + 1)]


def _csv(rows, columns=COLUMNS):
    buf = _io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
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
    #: ★★ 소유 결속 승인은 **원장 사건**이다 — 원장도 격리한다. 그러지 않으면 시험 승인이
    #:   제품 감사 이력에 쌓이고, 「승인 몇 건」 집계가 실제보다 많아진다.
    from core.decision_ledger import decision_ledger
    monkeypatch.setattr(decision_ledger, "db_path", str(tmp_path / "ledger.db"),
                        raising=False)

    def certify(rows, *, certified_at=None, key="LOG-02", columns=None):
        source_columns = COLUMNS if columns is None else columns
        inst = store.create_instance(
            kit_id="KIT-T", version="1.0.0",
            kit_fingerprint=_register_test_kit(store),
            tenant_id=TENANT, scope_node_id=SCOPE, entity_mode="VIRTUAL")
        b = store.create_binding(
            instance_id=inst["instance_id"], dataset_contract_key=key,
            provider=m.PROVIDER_FILE_SNAPSHOT, config={},
            tenant_id=TENANT, scope_node_id=SCOPE, entity_mode="VIRTUAL")
        for target in (m.VALIDATED, m.APPROVED, m.ACTIVE):
            b = store.transition(b["binding_id"], target)
        snap = svc.ingest(store, binding=b, payload=_csv(rows, source_columns),
                          file_name=f"{key}.csv",
                          workspace_root=str(tmp_path / "raw"))
        final = svc.run_pipeline(store, snap["snapshot_id"], rows, source_columns,
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
    #: 표시명도 **같은 인증판 원본**에서 온다. 업무 ID 를 화면 이름으로 재사용하지 않는다.
    assert res.display_name.startswith("선적 1")
    assert SHIP.object_id not in res.display_name
    assert len(res.display_fingerprint) == 64


def test_원가센터는_실제_인증판에서_집합으로_해석된다(indexed):
    rows = [
        {"account_id": "1000", "account_name": "현금및현금성자산",
         "cost_center_id": "CC-PROC", "cost_center_name": "원료구매 원가센터",
         "tenant_id": TENANT, "scope_node_id": SCOPE},
        {"account_id": "5000", "account_name": "재료비",
         "cost_center_id": "CC-PROC", "cost_center_name": "원료구매 원가센터",
         "tenant_id": TENANT, "scope_node_id": SCOPE},
    ]
    snapshot = indexed(rows, key="MDM-07", columns=list(rows[0]))
    res = R.product_object_scope_resolver(
        ObjectRef("mdm", "cost-center", "CC-PROC"), _ctx())
    assert res.status == ontology_resolve.FOUND, res
    assert res.snapshot_id == snapshot["snapshot_id"]
    assert res.display_name == "원가센터 1 · 원료구매 원가센터 · 연결 계정 2개"
    assert "CC-PROC" not in res.display_name
    assert res.resource_scope.scope_node_id == SCOPE


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


@pytest.fixture
def real_org(monkeypatch, tmp_path):
    """★★★ **실제 조직도.** 부트스트랩이 아니고, 승인자는 실재하는 데이터 표준 승인자다.

    ⚠️⚠️ [4.1c-B P0-1] 조직도를 세우지 않으면 `resolve_scope()` 가 부트스트랩 예외로
      미등록 사용자에게도 전권을 준다 — 그 상태에서 승인이 전부 통과했다. 소유권 시험은
      **반드시 이 픽스처를 지나야** 승인 권한 검사가 실제로 돈다.
    ⚠️ 부서는 `hq`·`sales` 만 만든다(실제 조직에 임의 배정 금지)."""
    from core.org_directory import OrgDirectory
    import core.org_directory as orgmod
    o = OrgDirectory(db_path=str(tmp_path / "org_own.db"))
    o.create_department("hq", "본사")
    o.create_department("sales", "영업")
    for uid in ("approver@afs.invalid", "auditor@afs.invalid"):
        o.upsert_user(uid, uid.split("@")[0], primary_dept_id="hq",
                      is_data_admin=True, actor="seed")
    monkeypatch.setattr(orgmod, "org_directory", o)
    return o


def _declare_owner(store, dept, *, key="LOG-02", scope=SCOPE, mode="VIRTUAL", **kw):
    """★ **승인 원장 사건을 먼저 남기고** 그 id 로 결속을 세운다.

    ⚠️ 첫 판은 `approved_by="approver@..."` 문자열 하나로 「승인됨」을 주장했다 — 같은
      호출자가 넣은 값을 같은 호출자가 읽는 자기진술이었다. 지금은 원장에 사건이 없으면
      결속 자체가 만들어지지 않는다."""
    from core.data_preparation import ownership_binding as ob
    ap = ob.approve(tenant_id=TENANT, entity_mode=mode, dataset_contract_key=key,
                    scope_node_id=scope, owner_dept_id=dept,
                    actor_id="approver@afs.invalid", evidence_ref="FND-01/v1#seed",
                    **{k: v for k, v in kw.items() if k in ("effective_from", "effective_to")})
    with store.transaction() as conn:
        return ob.declare(conn, tenant_id=TENANT, entity_mode=mode,
                          dataset_contract_key=key, scope_node_id=scope,
                          owner_dept_id=dept, approved_by="approver@afs.invalid",
                          evidence_ref="FND-01/v1#seed",
                          approval_event_id=ap["approval_event_id"],
                          **{**kw, "effective_from": ap["effective_from"]})


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


def test_승인된_결속이_있으면_색인에_물질화되고_봉인된다(indexed, real_org, monkeypatch):
    """★ 정본 → 색인. 그리고 **어느 결속에서 나왔는지**가 함께 봉인된다."""
    from core.data_preparation import store as dp
    b = _declare_owner(dp.data_preparation_store, "hq")
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


def test_철회하면_색인이_남아_있어도_막힌다(indexed, real_org, monkeypatch):
    """★★★ 계약 ⑥ — **색인이 있어도 요청 시 다시 검증한다.**

    ⚠️ 물질화 시점의 판단을 영구히 믿으면 그것이 곧 「회수해도 계속 유효한 권한」이다 —
      SSE 티켓에서 이미 같은 실수를 고쳤다."""
    from core.data_preparation import ownership_binding as ob
    from core.data_preparation import store as dp
    monkeypatch.setattr(_org(), "get_department",
                        lambda d: {"dept_id": d, "status": "active"}, raising=False)
    b = _declare_owner(dp.data_preparation_store, "hq")
    indexed(_rows())
    assert R.product_object_scope_resolver(SHIP, _ctx()).resource_scope.owner_dept_id == "hq"

    with dp.data_preparation_store.transaction() as conn:
        ob.revoke(conn, b["binding_id"], "auditor@afs.invalid", "근거 미비")
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.resource_scope.owner_dept_id == "", "철회 뒤에도 소유 부서가 살아 있다"


def test_부서가_폐지되면_색인이_있어도_503(indexed, real_org, monkeypatch):
    """계약 ⑦ — 결속은 있는데 가리키는 곳이 없다. 「안 보인다」가 아니라 **고쳐야 할 것**이다."""
    from core.data_preparation import store as dp
    monkeypatch.setattr(_org(), "get_department",
                        lambda d: {"dept_id": d, "status": "active"}, raising=False)
    _declare_owner(dp.data_preparation_store, "hq")
    indexed(_rows())
    monkeypatch.setattr(_org(), "get_department",
                        lambda d: {"dept_id": d, "status": "retired"}, raising=False)
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.status == ontology_resolve.UNAVAILABLE, res.status


def test_실제_조직도_Principal_로_PDP_를_대조한다(indexed, monkeypatch, tmp_path):
    """★★★ 계약 ⑪ — **가짜 Scope 가 아니라 조직도가 만드는 실제 AccessScope** 로 본다.

    ⚠️⚠️ [재감사 P1-1] 첫 판은 이 시험 안에서 `class _Scope` 를 손으로 만들어 넣었다.
      그 객체는 `readable_dept_ids` 를 내가 원하는 값으로 채운다 — 즉 **판정기가 아니라
      내가 답을 정했다.** 실제 `resolve_scope()` 가 그 필드를 어떻게 채우는지(부서 상속·
      하위 부서·폐지 사용자 제외)는 하나도 검사되지 않았다.
    ★ 그래서 여기서는 실제 `OrgDirectory` 에 부서와 사용자를 만들고, 제품이 부르는
      `resolve_scope()` 가 돌려주는 객체를 그대로 PDP 에 넘긴다."""
    from core import app_policy
    from core.data_preparation import store as dp
    from core.org_directory import OrgDirectory
    import core.org_directory as orgmod
    import core.scope_policy as sp

    #: ★ 실제 조직도. 부서·사용자를 제품 API 로 만든다.
    org = OrgDirectory(db_path=str(tmp_path / "org_real.db"))
    org.create_department("hq", "본사")
    org.create_department("sales", "영업")
    org.upsert_user("a@example.com", "가", primary_dept_id="hq", actor="seed")
    org.upsert_user("b@example.com", "나", primary_dept_id="sales", actor="seed")
    #: ★★ 승인자도 **실재하는 사람**이어야 한다. `approve()` 는 기준정보·데이터 표준 승인
    #:   권한(`can_manage_standard`)을 요구한다 — 강제를 켠 이 시험에서 그 검사가 실제로
    #:   돌기 때문에, 등록하지 않으면 결속을 만들 수 없다(실측: 이 시험만 빨개졌다).
    org.upsert_user("approver@afs.invalid", "표준승인자", primary_dept_id="hq",
                    is_data_admin=True, actor="seed")
    #: ⚠️ 강제가 꺼져 있으면 `resolve_scope` 가 **전원 무제한**을 돌려준다 — 그 상태로
    #:   대조하면 두 사람이 다 통과하고, 시험은 아무것도 지키지 못한다(실측된 함정이다).
    monkeypatch.setattr(sp, "_read", lambda: {"org_enforce": True})
    monkeypatch.setattr(orgmod, "org_directory", org)

    _declare_owner(dp.data_preparation_store, "hq")
    indexed(_rows())
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.resource_scope.owner_dept_id == "hq", res.status

    scope_a = org.resolve_scope("a@example.com")
    scope_b = org.resolve_scope("b@example.com")
    #: ★★ 먼저 **대조군이 진짜 대조군인지** 증명한다 — 둘 다 무제한이면 아래 판정은 의미가 없다.
    assert scope_a.unrestricted is False and scope_b.unrestricted is False,         "강제가 꺼져 있어 두 사람 다 전권이다 — 이 상태의 통과는 통과가 아니다"
    #: ★ 두 사람 다 **승인 권한은 없다** — 읽기 권한과 승인 권한은 다른 축이다.
    assert not scope_a.can_manage_standard and not scope_b.can_manage_standard
    assert "hq" in scope_a.readable_dept_ids and "hq" not in scope_b.readable_dept_ids

    ctxd = {"tenant_id": TENANT, "entity_mode": "VIRTUAL", "scope_node_id": ""}
    allowed = app_policy.decide(
        app_policy.Subject(user_id="a@example.com", scope=scope_a, ctx=ctxd),
        res.resource_scope, app_policy.READ)
    denied = app_policy.decide(
        app_policy.Subject(user_id="b@example.com", scope=scope_b, ctx=ctxd),
        res.resource_scope, app_policy.READ)
    assert allowed.allowed is True, allowed.reason
    assert denied.allowed is False, "다른 부서 사람이 통과했다"


# ── ⑫ 봉인 네 상태 ────────────────────────────────────────────────────────
#
#   ★★★ [재감사 P0-3] 색인의 `owner_binding_fingerprint` 는 **네 상태**가 있고 각각 다른
#     답이어야 한다. 첫 판은 `sealed != 현재지문` 만 비교해서, **봉인이 빈 문자열이면**
#     비교가 성립하지 않아 그냥 통과했다 — 즉 봉인 없는 색인이 소유 부서를 그대로 얻었다.
#
#       ① 결속 없음(철회 포함)   → 소유 부서 없음(정상적인 비노출)
#       ② 봉인 있음·현재와 같음 → 소유 부서 사용
#       ③ 봉인이 **비어 있음**   → 503(재물질화 필요) — 통과시키면 안 된다
#       ④ 봉인이 현재와 **다름** → 503(색인이 낡았다)

def _seal(store, value):
    """색인의 봉인만 바꿔 넣는다(정본은 그대로) — ③④ 상태를 만드는 유일한 방법이다."""
    with store.transaction() as conn:
        conn.execute("UPDATE object_scope_index SET owner_binding_fingerprint=?", (value,))


def test_봉인이_비어_있으면_503_이고_소유부서를_주지_않는다(indexed, real_org, monkeypatch):
    """★★★ 상태 ③. **가장 위험한 구멍이었다** — 봉인 없는 색인이 조용히 통과했다.

    ⚠️ 「빈 값이면 비교를 건너뛴다」는 코드는 어디에나 있고, 그때마다 검사 하나가 사라진다."""
    from core.data_preparation import store as dp
    monkeypatch.setattr(_org(), "get_department",
                        lambda d: {"dept_id": d, "status": "active"}, raising=False)
    _declare_owner(dp.data_preparation_store, "hq")
    indexed(_rows())
    _seal(dp.data_preparation_store, "")
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.status == ontology_resolve.UNAVAILABLE,         f"봉인 없는 색인이 통과했다: {res.status}/{res.resource_scope.owner_dept_id}"


def test_봉인이_다르면_503_이다(indexed, real_org, monkeypatch):
    """상태 ④ — 색인이 낡았다. 「낡은 소유자」로 답하면 옛 부서 권한이 되살아난다."""
    from core.data_preparation import store as dp
    monkeypatch.setattr(_org(), "get_department",
                        lambda d: {"dept_id": d, "status": "active"}, raising=False)
    _declare_owner(dp.data_preparation_store, "hq")
    indexed(_rows())
    _seal(dp.data_preparation_store, "fp_다른봉인")
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.status == ontology_resolve.UNAVAILABLE, res.status


def test_봉인이_같으면_소유부서를_쓴다(indexed, real_org, monkeypatch):
    """상태 ② — 대조군. 이것이 빨개지면 위 두 검사는 「전부 막는 검사」일 뿐이다."""
    from core.data_preparation import store as dp
    monkeypatch.setattr(_org(), "get_department",
                        lambda d: {"dept_id": d, "status": "active"}, raising=False)
    _declare_owner(dp.data_preparation_store, "hq")
    indexed(_rows())
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.status != ontology_resolve.UNAVAILABLE, res.status
    assert res.resource_scope.owner_dept_id == "hq"


def test_결속이_철회되면_봉인이_남아도_비노출이고_503이_아니다(indexed, real_org, monkeypatch):
    """상태 ① — **여기만 503 이 아니다.** 결속 없음은 정상적인 비노출이고, 점검할 것이 없다.

    ⚠️ 이 넷을 한 덩어리로 뭉개면 「고칠 것이 없는데 고치라고 말하는」 화면이 된다."""
    from core.data_preparation import ownership_binding as ob
    from core.data_preparation import store as dp
    monkeypatch.setattr(_org(), "get_department",
                        lambda d: {"dept_id": d, "status": "active"}, raising=False)
    b = _declare_owner(dp.data_preparation_store, "hq")
    indexed(_rows())
    with dp.data_preparation_store.transaction() as conn:
        ob.revoke(conn, b["binding_id"], "auditor@afs.invalid", "근거 미비")
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.status != ontology_resolve.UNAVAILABLE, "철회를 장애로 답했다"
    assert res.resource_scope.owner_dept_id == ""


# ── ⑬ 인증·색인 원자성 ────────────────────────────────────────────────────

def test_물질화_도중_실패하면_앞서_한_일까지_롤백된다(indexed, real_org, monkeypatch):
    """★★★ [재감사 P0-2] **`executescript()` 는 감싼 트랜잭션을 먼저 커밋한다**(실측):

        BEFORE in_transaction: True → AFTER_SCRIPT: False → ROWS_AFTER_ROLLBACK: 1

    첫 판은 `declare()` 안에서 DDL 을 `executescript` 로 돌렸다. 그래서 「인증 전환과
    색인 기록이 한 트랜잭션에서 함께 성립한다」는 보증이 **주석에만** 있었다.

    ⚠️⚠️ [변이 시험에서 발견] 이 시험의 첫 판은 `declare` **뒤**만 봤다. 그런데
      `executescript` 가 파괴하는 것은 **그 앞에 한 일**이다 — 조기 커밋 뒤의 INSERT 는
      새로 열린 암묵 트랜잭션에 들어가므로 롤백된다. 그래서 DDL 을 되돌려 넣어도 실패가
      0건이었다. **앞선 쓰기를 함께 확인해야** 이 회귀가 통제가 된다."""
    from core.data_preparation import ownership_binding as ob
    from core.data_preparation import store as dp
    store = dp.data_preparation_store
    indexed(_rows())
    ap = ob.approve(tenant_id=TENANT, entity_mode="VIRTUAL", dataset_contract_key="LOG-02",
                    scope_node_id=SCOPE, owner_dept_id="hq",
                    actor_id="approver@afs.invalid", evidence_ref="FND-01/v1#seed")
    with pytest.raises(RuntimeError, match="물질화 중단"):
        with store.transaction() as conn:
            #: ① **먼저** 한 일 — 인증 전환·색인 기록에 해당하는 자리다.
            conn.execute("UPDATE object_scope_index SET owner_dept_id='선행쓰기'")
            #: ② 그 다음 결속 등록. 여기서 DDL 이 돌면 ①이 커밋되어 되돌릴 수 없다.
            ob.declare(conn, tenant_id=TENANT, entity_mode="VIRTUAL",
                       dataset_contract_key="LOG-02", scope_node_id=SCOPE,
                       owner_dept_id="hq", approved_by="approver@afs.invalid",
                       evidence_ref="FND-01/v1#seed",
                       approval_event_id=ap["approval_event_id"],
                       effective_from=ap["effective_from"])
            assert conn.in_transaction, "이미 커밋됐다 — DDL 이 트랜잭션을 끊었다"
            #: ③ 물질화 실패.
            raise RuntimeError("물질화 중단")
    with store.transaction() as conn:
        left = conn.execute("SELECT COUNT(*) FROM object_scope_index "
                            "WHERE owner_dept_id='선행쓰기'").fetchone()[0]
        n = conn.execute("SELECT COUNT(*) FROM dataset_ownership_bindings").fetchone()[0]
    assert left == 0, f"앞서 한 쓰기 {left}건이 롤백되지 않았다 — 원자성이 깨졌다"
    assert n == 0, f"롤백했는데 결속이 {n}건 남았다"


def test_다른_계약키의_결속은_물질화되지_않는다(indexed, real_org, monkeypatch):
    """계약 ⑤ — 다른 scope·계약의 결속을 재사용하지 않는다. SLS-01 결속으로 LOG-02 가
    소유자를 얻으면, 승인 하나가 계약 경계를 넘는 것이다."""
    from core.data_preparation import store as dp
    monkeypatch.setattr(_org(), "get_department",
                        lambda d: {"dept_id": d, "status": "active"}, raising=False)
    _declare_owner(dp.data_preparation_store, "sales", key="SLS-01")
    indexed(_rows())                                  # 색인 대상은 LOG-02
    res = R.product_object_scope_resolver(SHIP, _ctx())
    assert res.resource_scope.owner_dept_id == "", "다른 계약키의 결속이 새어 들어왔다"


def _org():
    from core.org_directory import org_directory
    return org_directory
