"""★★★ **업무 객체 범위 색인**을 검증한다. (§7 3단계)

## 이 파일이 지키는 것

    ① 업무 레코드 ID(`STK-…`)와 인증판 ID(`ds_…`)를 **섞지 않는다**
    ② `as_of` 로 판을 고른다 — **「그냥 최신」 금지**
    ③ 동점이면 고르지 않는다 (`AMBIGUOUS` → 503)
    ④ 옛 판을 지우지 않는다 (과거 시점 질의의 전제)
    ⑤ 색인 없이 인증이 서지 않는다

⚠️⚠️ ②가 이 파일의 핵심이다. 「최신을 고르면 되지」는 **과거 시점 질의에 오늘의 답**을
  준다. 화면은 멀쩡하고, 숫자도 그럴듯하고, 아무도 틀린 줄 모른다.
"""
import csv
import io as _io
import json

import pytest

from core.data_preparation import models as m
from core.data_preparation import scope_index as ix
from core.data_preparation import snapshot_service as svc
from core.data_preparation.store import DataPreparationStore

TENANT = "tenant-demo"
SCOPE = "plant-demo"


def _csv(rows, columns):
    buf = _io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _shipment_rows(n=3, tenant=TENANT, scope=SCOPE, prefix="SHP"):
    return [{"shipment_id": f"{prefix}-{i:06d}", "po_line_id": f"PO-{i:06d}-10",
             "tenant_id": tenant, "scope_node_id": scope, "etd": "2026-03-01"}
            for i in range(1, n + 1)]


COLUMNS = ["shipment_id", "po_line_id", "tenant_id", "scope_node_id", "etd"]


@pytest.fixture
def store(tmp_path):
    return DataPreparationStore(str(tmp_path / "data_preparation.db"))


@pytest.fixture
def workspace(tmp_path):
    return str(tmp_path / "raw")


def _certify(store, workspace, *, key="LOG-02", rows=None, columns=None,
             tenant=TENANT, scope=SCOPE, certified_at=None):
    """한 판을 인증까지 올린다. 인증된 Snapshot 을 돌려준다."""
    rows = _shipment_rows() if rows is None else rows
    columns = COLUMNS if columns is None else columns
    instance = store.create_instance(
        kit_id="KIT-T", version="1.0.0", kit_fingerprint="fp",
        tenant_id=tenant, scope_node_id=scope, entity_mode="VIRTUAL")
    binding = store.create_binding(
        instance_id=instance["instance_id"], dataset_contract_key=key,
        provider=m.PROVIDER_FILE_SNAPSHOT, config={},
        tenant_id=tenant, scope_node_id=scope, entity_mode="VIRTUAL")
    for target in (m.VALIDATED, m.APPROVED, m.ACTIVE):
        binding = store.transition(binding["binding_id"], target)
    snap = svc.ingest(store, binding=binding, payload=_csv(rows, columns),
                      file_name=f"{key}.csv", workspace_root=workspace)
    final = svc.run_pipeline(store, snap["snapshot_id"], rows, columns,
                             control={"row_count": len(rows)})
    if certified_at:
        #: ★ 인증 시각을 손으로 정한다 — `as_of` 규칙을 시험하려면 시각이 달라야 한다.
        with store.transaction() as conn:
            conn.execute("UPDATE dataset_snapshots SET certified_at=? WHERE snapshot_id=?",
                         (certified_at, final["snapshot_id"]))
            conn.execute("UPDATE object_scope_index SET certified_at=? WHERE snapshot_id=?",
                         (certified_at, final["snapshot_id"]))
        final = store.get_snapshot(final["snapshot_id"])
    return final


# ── ① 대상 표 ───────────────────────────────────────────────────────────

def test_색인_대상은_다섯_계약키뿐이다():
    """⚠️ 넓히려면 Resolver·관계·계산이 함께 준비돼야 한다 — 표만 넓히면 「승인은 됐는데
    아무도 범위를 확인하지 않은 관계」가 생긴다."""
    assert set(ix.CONTRACT_OBJECTS) == {"PRC-02", "LOG-02", "INV-01", "MFG-01", "SLS-01"}


def test_객체_유형은_계약의_하이픈_표기다():
    """★ 여기서 표기를 바꾸면 계약과 런타임이 **서로 다른 이름**을 부르게 된다."""
    types = {v[1] for v in ix.CONTRACT_OBJECTS.values()}
    assert types == {"purchase-order-line", "shipment", "inventory-snapshot",
                     "production-plan-line", "sales-line"}
    assert all("_" not in t for t in types)


def test_재고의_객체_열쇠는_인증판_ID_가_아니다():
    """★★★ `INV-01` 은 자기 열 이름이 하필 `snapshot_id` 다.

    ⚠️⚠️ 그 값은 `STK-…` 이고 인증판은 `ds_…` 다. 첫 구현이 이 둘을 섞어서 **영영 못
      찾는데 결과가 `None`** 이었고, 그것이 「범위 밖」과 구분되지 않았다."""
    assert ix.CONTRACT_OBJECTS["INV-01"][2] == "snapshot_id"


# ── ② 인증이 색인을 세운다 ──────────────────────────────────────────────

def test_인증하면_색인이_선다(store, workspace):
    snap = _certify(store, workspace)
    assert snap["state"] == m.DEMO_CERTIFIED
    assert ix.bound_to(store, snap["snapshot_id"]) == 3
    status, row, _ = ix.lookup(store, "dataset", "shipment", "SHP-000001")
    assert status == ix.FOUND
    assert row["tenant_id"] == TENANT and row["scope_node_id"] == SCOPE
    assert row["snapshot_id"] == snap["snapshot_id"]
    #: ★ 본문이 아니라 **위치**가 남는다.
    assert "line=2" in row["row_evidence"]


def test_대상이_아닌_계약키는_색인하지_않는다(store, workspace):
    """★ 0줄이 **정상**인 자리다 — 온톨로지 MVP 대상은 다섯뿐이다."""
    snap = _certify(store, workspace, key="FIN-01")
    assert snap["state"] == m.DEMO_CERTIFIED
    assert ix.bound_to(store, snap["snapshot_id"]) == 0


def test_색인을_못_세우면_인증이_서지_않는다(store, workspace):
    """★★★ 순서가 중요하다 — 인증부터 하면 「인증은 됐는데 색인이 없는 판」이 생기고,
    그 사고는 **질의 시점**에 터진다. 그때는 고칠 사람이 그 자리에 없다.

    ⚠️⚠️ 첫 판은 「예외가 났다」만 봤고 **어떤 상태로 남았는지**를 안 봤다. 그래서
      「인증 뒤에 색인을 세우도록」 뒤집는 변이가 **살아남았다** — 그쪽도 예외는 나기
      때문이다(인증했다가 물린다).

    ★ 갈라야 하는 것은 이것이다:

        인증이 **선 적이 없다**   → RECONCILED, certified_at 이 비어 있다
        인증했다가 **물렸다**     → REVOKED, certified_at 이 찍혀 있다

      뒤엣것은 «인증된 판» 이 잠깐이라도 존재했다는 뜻이고, 그 사이에 읽은 쪽은
      색인 없는 인증판을 본다."""
    rows = _shipment_rows()
    rows[1]["shipment_id"] = ""                  # 업무 ID 가 빈 행
    with pytest.raises(ix.ScopeIndexError):
        _certify(store, workspace, rows=rows)

    with store.transaction() as conn:
        found = [dict(r) for r in conn.execute(
            "SELECT snapshot_id, state, certified_at FROM dataset_snapshots")]
    assert found, "Snapshot 이 아예 없다 — 시험 전제가 깨졌다"
    for row in found:
        assert row["state"] == m.RECONCILED, (
            f"인증이 섰다가 물렸다({row['state']}) — 색인 없는 인증판이 잠깐 존재했다")
        assert not row["certified_at"], (
            f"certified_at 이 찍혔다({row['certified_at']}) — 인증이 선 적이 있다")


def test_같은_판에_업무_ID_가_겹치면_막는다(store, workspace):
    """⚠️ 어느 행이 그 객체인지 알 수 없다 — 「아무거나 하나」로 넘어가면 근거가 흔들린다."""
    rows = _shipment_rows()
    rows[2]["shipment_id"] = rows[0]["shipment_id"]
    with pytest.raises(ix.ScopeIndexError):
        _certify(store, workspace, rows=rows)


def test_남의_tenant_행은_막는다(store, workspace):
    """★★★ 행 수는 그대로여서 **눈으로는 보이지 않는** 오염이다."""
    rows = _shipment_rows()
    rows[1]["tenant_id"] = "tenant-남의회사"
    with pytest.raises(ix.ScopeIndexError):
        _certify(store, workspace, rows=rows)


def test_범위_없는_행은_막는다(store, workspace):
    rows = _shipment_rows()
    rows[0]["scope_node_id"] = ""
    with pytest.raises(ix.ScopeIndexError):
        _certify(store, workspace, rows=rows)


def test_원본_지문이_다르면_막는다(store, workspace, tmp_path):
    """★★★ 색인은 **인증한 바로 그 바이트**에서 나와야 한다.

    ⚠️ 지문을 안 보고 읽으면 파일이 바뀐 뒤에도 색인이 생기고, 그 색인은 **인증하지
      않은 자료**를 가리킨다."""
    snap = _certify(store, workspace)
    with open(snap["raw_path"], "ab") as f:
        f.write(b"\n")                            # 원본을 건드린다
    with pytest.raises(ix.ScopeIndexError):
        ix.plan(snap)


# ── ③ as_of 로 판을 고른다 ──────────────────────────────────────────────

@pytest.fixture
def two_versions(store, workspace):
    """같은 배(`SHP-000001`)를 담은 판 둘. 인증 시각이 다르다."""
    old = _certify(store, workspace, rows=_shipment_rows(2),
                   certified_at="2026-03-01T00:00:00+00:00")
    new = _certify(store, workspace, rows=_shipment_rows(3),
                   certified_at="2026-06-01T00:00:00+00:00")
    return old, new


def test_옛_판을_지우지_않는다(two_versions, store):
    """★ 옛 판을 지우면 과거 시점 질의가 **오늘의 답**을 낸다 — 조용한 거짓말이다."""
    rows = ix.versions(store, "dataset", "shipment", "SHP-000001")
    assert len(rows) == 2, rows
    assert [r["certified_at"] for r in rows] == ["2026-03-01T00:00:00+00:00",
                                                 "2026-06-01T00:00:00+00:00"]


def test_as_of_는_그_시점의_판을_고른다(two_versions, store):
    """★★★ **이 파일의 핵심.** 「그냥 최신」이면 과거 질의가 오늘의 답을 받는다."""
    old, new = two_versions
    status, row, _ = ix.lookup(store, "dataset", "shipment", "SHP-000001",
                               as_of="2026-04-01T00:00:00+00:00")
    assert status == ix.FOUND
    assert row["snapshot_id"] == old["snapshot_id"], (
        "as_of 를 무시하고 최신 판을 골랐다 — 과거 질의에 오늘의 답을 준다")


def test_as_of_가_지나면_새_판을_고른다(two_versions, store):
    """★ 대조군 — 늘 옛 판만 고르면 그것도 틀린 것이다."""
    old, new = two_versions
    status, row, _ = ix.lookup(store, "dataset", "shipment", "SHP-000001",
                               as_of="2026-07-01T00:00:00+00:00")
    assert status == ix.FOUND and row["snapshot_id"] == new["snapshot_id"]


def test_인증_전_시점에는_없는_것이다(two_versions, store):
    """⚠️ 「그 시점에는 아직 인증되지 않았다」는 **사실**이다 — 최신 판으로 메우지 않는다."""
    status, row, _ = ix.lookup(store, "dataset", "shipment", "SHP-000001",
                               as_of="2026-01-01T00:00:00+00:00")
    assert status == ix.NOT_FOUND and row is None


def test_없는_객체는_없는_것이다(two_versions, store):
    status, row, _ = ix.lookup(store, "dataset", "shipment", "SHP-없는배")
    assert status == ix.NOT_FOUND and row is None


def test_새_판에_없는_객체는_옛_판으로_답하지_않는다(two_versions, store):
    """★ `SHP-000003` 은 새 판에만 있다. 옛 시점에는 **없어야** 한다."""
    status, _, _ = ix.lookup(store, "dataset", "shipment", "SHP-000003",
                             as_of="2026-04-01T00:00:00+00:00")
    assert status == ix.NOT_FOUND


# ── ④ 동점은 고르지 않는다 ──────────────────────────────────────────────

def test_같은_시각의_판이_둘이면_고르지_않는다(store, workspace):
    """★★★ 임의로 고르면 같은 질문의 답이 **실행마다 달라진다.**

    ⚠️ 그러면 재실행 지문이 흔들리고 「이 숫자는 무엇으로 만들었나」에 답할 수 없다."""
    same = "2026-05-01T00:00:00+00:00"
    a = _certify(store, workspace, rows=_shipment_rows(2), certified_at=same)
    b = _certify(store, workspace, rows=_shipment_rows(2), certified_at=same)
    status, row, candidates = ix.lookup(store, "dataset", "shipment", "SHP-000001")
    assert status == ix.AMBIGUOUS, f"동점인데 «{status}» 로 골랐다"
    assert row is None
    assert set(candidates) == {a["snapshot_id"], b["snapshot_id"]}


def test_동점이_아니면_고른다(two_versions, store):
    """★ 대조군 — 동점 검사가 **늘 막기만** 하면 그것은 검사가 아니다."""
    status, row, candidates = ix.lookup(store, "dataset", "shipment", "SHP-000001")
    assert status == ix.FOUND and row is not None and candidates == ()


# ── ⑤ 근거가 그 판에 묶여 있는가 ────────────────────────────────────────

def test_근거가_그_판에_묶여_있어야_한다(store, workspace):
    snap = _certify(store, workspace)
    ok, why = ix.evidence_bound(store, ["LOG-02.po_line_id"], snap["snapshot_id"])
    assert ok, why
    bad, why2 = ix.evidence_bound(store, ["INV-01.material_id"], snap["snapshot_id"])
    assert not bad and "없는 근거" in why2


def test_근거가_없으면_거부한다(store, workspace):
    """⚠️ 근거 없는 관계는 「누가 그렇다고 했나」에 답할 수 없다."""
    snap = _certify(store, workspace)
    ok, why = ix.evidence_bound(store, [], snap["snapshot_id"])
    assert not ok and why


def test_색인이_없는_판의_근거는_거부한다(store, workspace):
    snap = _certify(store, workspace, key="FIN-01")
    ok, why = ix.evidence_bound(store, ["FIN-01.amount"], snap["snapshot_id"])
    assert not ok and "색인이 없습니다" in why


def test_근거_목록이_문자열이어도_읽는다(store, workspace):
    """★ 저장소는 JSON 문자열로 들고 있다 — 옮겨 담는 자리에서 뜻이 바뀌면 안 된다."""
    snap = _certify(store, workspace)
    ok, why = ix.evidence_bound(store, json.dumps(["LOG-02.po_line_id"]),
                                snap["snapshot_id"])
    assert ok, why


# ── ⑥ 범위는 «행» 이 말한다 ─────────────────────────────────────────────

def test_한_판_안에서도_조직_범위가_다를_수_있다(store, workspace):
    """★★★ **범위는 인증판이 아니라 «행» 이 말한다.**

    ⚠️⚠️ 실제로 여기서 한 번 틀렸다. 인증판 하나의 `scope_node_id`(첫 행에서 파생된
      값)를 보고 「자료 전체가 한 범위」라고 보고했다 — 정본 다섯 종은 실은 두 조직
      노드에 걸쳐 있었다(battery-02 1,215건 · smelting-01 445건).

    ★ 대표값 하나를 전체의 성질로 넓히면, 조직 격리 시험이 **아무것도 가르지 않는
      자료** 위에서 돌게 된다. 색인은 행마다 그 행의 범위를 적어야 한다."""
    rows = _shipment_rows(3)
    rows[1]["scope_node_id"] = "plant-다른공장"
    rows[2]["scope_node_id"] = "plant-다른공장"
    snap = _certify(store, workspace, rows=rows)
    assert snap["state"] == m.DEMO_CERTIFIED

    scopes = {}
    for r in rows:
        status, got, _ = ix.lookup(store, "dataset", "shipment", r["shipment_id"])
        assert status == ix.FOUND
        scopes.setdefault(got["scope_node_id"], 0)
        scopes[got["scope_node_id"]] += 1
    assert scopes == {SCOPE: 1, "plant-다른공장": 2}, (
        f"행별 범위가 색인에 남지 않았다: {scopes}")


def test_tenant_은_판과_같아야_한다(store, workspace):
    """★ 대조군의 반대쪽 — 조직 노드는 달라도 되지만 **tenant 는 달라선 안 된다.**

    ⚠️ 조직 노드는 한 회사 안의 구분이고, tenant 는 **회사가 다른 것**이다."""
    rows = _shipment_rows(2)
    rows[0]["tenant_id"] = "tenant-남의회사"
    with pytest.raises(ix.ScopeIndexError):
        _certify(store, workspace, rows=rows)
