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
        kit_id="KIT-T", version="1.0.0",
            kit_fingerprint=_register_test_kit(store),
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
    assert set(ix.CONTRACT_OBJECTS) == {
        "PRC-01", "PRC-02", "LOG-01", "LOG-02", "LOG-03", "LOG-04", "LOG-05",
        "INV-01", "MFG-01", "MFG-02", "SLS-01", "FIN-01", "FIN-02", "FIN-03",
    }


def test_기준정보와_대외정보는_검증된_단일키_유형만_추가한다():
    assert ix.REFERENCE_OBJECTS == {
        "MDM-01": ("mdm", "material", "material_id"),
        "MDM-02": ("mdm", "supplier", "supplier_id"),
        "MDM-04": ("mdm", "location", "location_id"),
        "MDM-06": ("mdm", "equipment", "equipment_id"),
        "MDM-07": ("mdm", "account", "account_id"),
        "MDM-08": ("mdm", "logistics-reference", "reference_id"),
        "EXT-01": ("external", "external-observation", "observation_id"),
        "EXT-02": ("external", "external-observation", "observation_id"),
        "EXT-03": ("external", "external-observation", "observation_id"),
    }
    assert ix.COMPOSITE_REFERENCE_OBJECTS == {
        "MDM-05": (("mdm", "bom-line", ("bom_id", "line_no")),),
        "MDM-06": (("mdm", "routing-operation", ("routing_id", "operation_seq")),),
    }
    assert ix.object_id_for({"bom_id": "A|B", "line_no": "C"},
                            ("bom_id", "line_no")) != ix.object_id_for(
                                {"bom_id": "A", "line_no": "B|C"},
                                ("bom_id", "line_no"))
    # 사람용 명칭 정본이 없는 원가센터는 임의로 열지 않는다.
    assert "cost-center" not in {value[1] for value in ix.REFERENCE_OBJECTS.values()}


def test_구버전_인증판_색인_백필은_명시적이고_멱등이다(store, workspace):
    rows = [{
        "material_id": "MAT-1", "material_name": "시험 품목",
        "material_type": "RAW", "base_uom": "TON",
        "tenant_id": TENANT, "scope_node_id": SCOPE,
    }]
    columns = list(rows[0])
    snapshot = _certify(
        store, workspace, key="MDM-01", rows=rows, columns=columns,
        tenant=TENANT, scope=SCOPE)

    # 구버전처럼 인증판은 남았지만 파생 색인만 없는 상태를 재현한다.
    with store.transaction() as conn:
        conn.execute("DELETE FROM object_scope_index WHERE snapshot_id=?",
                     (snapshot["snapshot_id"],))
    assert ix.has_unmaterialized_snapshot(
        store, "mdm", "material", TENANT, "VIRTUAL") is True

    first = ix.backfill_supported_snapshots(store)
    assert first["MDM-01"] == 1
    assert ix.bound_to(store, snapshot["snapshot_id"]) == 1
    assert ix.materialized_object_types(store)["mdm"] == ("material",)

    second = ix.backfill_supported_snapshots(store)
    assert second["MDM-01"] == 1
    assert ix.bound_to(store, snapshot["snapshot_id"]) == 1


def test_객체_유형은_계약의_하이픈_표기다():
    """★ 여기서 표기를 바꾸면 계약과 런타임이 **서로 다른 이름**을 부르게 된다."""
    types = {v[1] for v in ix.CONTRACT_OBJECTS.values()}
    assert types == {
        "procurement-contract", "purchase-order-line", "partner-submission", "shipment",
        "shipment-milestone", "customs-clearance", "transport-event", "inventory-snapshot",
        "production-plan-line", "production-batch", "sales-line", "cost-record",
        "finance-document", "ledger-line",
    }
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
    status, row, _ = ix.lookup(store, "dataset", "shipment", "SHP-000001", TENANT, "VIRTUAL")
    assert status == ix.FOUND
    assert row["tenant_id"] == TENANT and row["scope_node_id"] == SCOPE
    assert row["snapshot_id"] == snap["snapshot_id"]
    #: ★ 본문이 아니라 **위치**가 남는다.
    assert "line=2" in row["row_evidence"]


def test_대상이_아닌_계약키는_색인하지_않는다(store, workspace):
    """★ 0줄이 **정상**인 자리다 — 명시된 온톨로지 계약 밖의 자료다."""
    snap = _certify(store, workspace, key="UNMAPPED-01")
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
    rows = ix.versions(store, "dataset", "shipment", "SHP-000001", TENANT, "VIRTUAL")
    assert len(rows) == 2, rows
    assert [r["certified_at"] for r in rows] == ["2026-03-01T00:00:00+00:00",
                                                 "2026-06-01T00:00:00+00:00"]


def test_as_of_는_그_시점의_판을_고른다(two_versions, store):
    """★★★ **이 파일의 핵심.** 「그냥 최신」이면 과거 질의가 오늘의 답을 받는다."""
    old, new = two_versions
    status, row, _ = ix.lookup(store, "dataset", "shipment", "SHP-000001", TENANT, "VIRTUAL",
                               as_of="2026-04-01T00:00:00+00:00")
    assert status == ix.FOUND
    assert row["snapshot_id"] == old["snapshot_id"], (
        "as_of 를 무시하고 최신 판을 골랐다 — 과거 질의에 오늘의 답을 준다")


def test_as_of_가_지나면_새_판을_고른다(two_versions, store):
    """★ 대조군 — 늘 옛 판만 고르면 그것도 틀린 것이다."""
    old, new = two_versions
    status, row, _ = ix.lookup(store, "dataset", "shipment", "SHP-000001", TENANT, "VIRTUAL",
                               as_of="2026-07-01T00:00:00+00:00")
    assert status == ix.FOUND and row["snapshot_id"] == new["snapshot_id"]


def test_인증_전_시점은_없음이_아니라_미결속이다(two_versions, store):
    """★★★ 「그 시점에는 아직 인증되지 않았다」와 「그런 객체가 없다」는 **다른 사실**이다.

    ⚠️ 최신 판으로 메우지 않는 것은 물론이고, 둘을 하나로 뭉쳐도 안 된다 — 사람이 할
      일이 다르다. 앞엣것은 오타를 의심하고, 뒤엣것은 인증 일정을 본다."""
    status, row, _ = ix.lookup(store, "dataset", "shipment", "SHP-000001", TENANT, "VIRTUAL",
                               as_of="2026-01-01T00:00:00+00:00")
    assert status == ix.UNBOUND and row is None
    #: ★ 대조군 — 진짜 없는 객체는 `NOT_FOUND` 여야 한다. 둘이 같아지면 구분이 사라진다.
    missing, _, _ = ix.lookup(store, "dataset", "shipment", "SHP-없는배", TENANT, "VIRTUAL",
                              as_of="2026-01-01T00:00:00+00:00")
    assert missing == ix.NOT_FOUND and missing != status


def test_없는_객체는_없는_것이다(two_versions, store):
    status, row, _ = ix.lookup(store, "dataset", "shipment", "SHP-없는배", TENANT, "VIRTUAL")
    assert status == ix.NOT_FOUND and row is None


def test_새_판에_없는_객체는_옛_판으로_답하지_않는다(two_versions, store):
    """★ `SHP-000003` 은 새 판에만 있다. 옛 시점에는 **없어야** 한다."""
    status, _, _ = ix.lookup(store, "dataset", "shipment", "SHP-000003", TENANT, "VIRTUAL",
                             as_of="2026-04-01T00:00:00+00:00")
    assert status == ix.UNBOUND, "새 판에만 있는 객체를 옛 시점에서 찾아 줬다"


# ── ④ 동점은 고르지 않는다 ──────────────────────────────────────────────

def test_같은_시각의_판이_둘이면_고르지_않는다(store, workspace):
    """★★★ 임의로 고르면 같은 질문의 답이 **실행마다 달라진다.**

    ⚠️ 그러면 재실행 지문이 흔들리고 「이 숫자는 무엇으로 만들었나」에 답할 수 없다."""
    same = "2026-05-01T00:00:00+00:00"
    a = _certify(store, workspace, rows=_shipment_rows(2), certified_at=same)
    b = _certify(store, workspace, rows=_shipment_rows(2), certified_at=same)
    status, row, candidates = ix.lookup(store, "dataset", "shipment", "SHP-000001", TENANT, "VIRTUAL")
    assert status == ix.AMBIGUOUS, f"동점인데 «{status}» 로 골랐다"
    assert row is None
    assert set(candidates) == {a["snapshot_id"], b["snapshot_id"]}


def test_동점이_아니면_고른다(two_versions, store):
    """★ 대조군 — 동점 검사가 **늘 막기만** 하면 그것은 검사가 아니다."""
    status, row, candidates = ix.lookup(store, "dataset", "shipment", "SHP-000001", TENANT, "VIRTUAL")
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
    snap = _certify(store, workspace, key="UNMAPPED-01")
    ok, why = ix.evidence_bound(store, ["UNMAPPED-01.amount"], snap["snapshot_id"])
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
        status, got, _ = ix.lookup(store, "dataset", "shipment", r["shipment_id"], TENANT, "VIRTUAL")
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


# ══════════════════════════════════════════════════════════════════════════
# 4.1a 보정 — 감사에서 나온 P0 둘·P1 셋 (2026-08-21)
# ══════════════════════════════════════════════════════════════════════════

def test_철회된_인증판은_더_이상_해석되지_않는다(store, workspace):
    """★★★ [P0] 색인 줄은 인증판이 철회돼도 **남는다.**

    ⚠️⚠️ 상태를 안 보면 폐기된 판의 객체가 영원히 `FOUND` 로 답한다 — 철회가 아무 일도
      하지 않는 셈이 된다. 「물렸다」고 기록만 하고 실제로는 그대로 쓰이는 것이다."""
    snap = _certify(store, workspace)
    ok, _, _ = ix.lookup(store, "dataset", "shipment", "SHP-000001", TENANT, "VIRTUAL")
    assert ok == ix.FOUND, "시험 전제가 깨졌다"

    store.advance_snapshot(snap["snapshot_id"], m.REVOKED)
    status, row, _ = ix.lookup(store, "dataset", "shipment", "SHP-000001",
                               TENANT, "VIRTUAL")
    #: ★ 「아예 없다」가 아니라 「더는 묶여 있지 않다」다 — 사람이 볼 곳이 다르다.
    assert status == ix.UNBOUND, f"철회된 판이 «{status}» 로 살아 있다"
    assert row is None


def test_다른_회사의_같은_ID_는_다른_객체다(store, workspace):
    """★★★ [P0] 업무 레코드 ID 는 회사마다 겹친다 — `SHP-000001` 은 어디에나 있다.

    ⚠️⚠️ 정체성에 tenant 가 없으면 **다른 회사의 최신 줄이 우리 줄을 가리거나** 동점을
      만들어 `AMBIGUOUS` 가 된다.
    ★ 이것은 권한이 아니다. 남의 `SHP-000001` 은 「내가 볼 수 없는 우리 배」가 아니라
      **아예 다른 배**다."""
    _certify(store, workspace, rows=_shipment_rows(2),
             certified_at="2026-03-01T00:00:00+00:00")
    other = [dict(r, tenant_id="tenant-남의회사", scope_node_id="plant-남의공장")
             for r in _shipment_rows(2)]
    _certify(store, workspace, rows=other, tenant="tenant-남의회사",
             scope="plant-남의공장", certified_at="2026-09-01T00:00:00+00:00")

    mine, row, _ = ix.lookup(store, "dataset", "shipment", "SHP-000001",
                             TENANT, "VIRTUAL")
    assert mine == ix.FOUND, "남의 회사 줄이 우리 것을 가렸다"
    assert row["tenant_id"] == TENANT

    theirs, trow, _ = ix.lookup(store, "dataset", "shipment", "SHP-000001",
                                "tenant-남의회사", "VIRTUAL")
    assert theirs == ix.FOUND and trow["tenant_id"] == "tenant-남의회사"
    assert row["snapshot_id"] != trow["snapshot_id"], "두 회사가 같은 판을 가리킨다"


def test_실행_문맥이_다르면_다른_객체다(store, workspace):
    """★ `entity_mode` 도 정체성이다 — 실적의 배와 시나리오의 배는 다른 객체다."""
    _certify(store, workspace)
    status, _, _ = ix.lookup(store, "dataset", "shipment", "SHP-000001",
                             TENANT, "REAL")
    assert status == ix.NOT_FOUND, "시나리오 자료가 실적 문맥에서 보였다"


def test_새_인증판에서_빠진_객체는_살아나지_않는다(store, workspace):
    """★★★ [P1] 인증판은 **전체판**이다 — 새 판에 없으면 사라진 것이다.

    ⚠️⚠️ 옛 줄이 남아 있다고 그 객체가 아직 있는 것처럼 답하면, **폐기된 선적이 영원히
      살아 있다.** 그리고 그 답은 그럴듯해서 아무도 틀린 줄 모른다."""
    _certify(store, workspace, rows=_shipment_rows(3),
             certified_at="2026-03-01T00:00:00+00:00")
    #: 새 판에서 `SHP-000003` 이 빠졌다.
    _certify(store, workspace, rows=_shipment_rows(2),
             certified_at="2026-06-01T00:00:00+00:00")

    gone, row, _ = ix.lookup(store, "dataset", "shipment", "SHP-000003",
                             TENANT, "VIRTUAL")
    assert gone == ix.UNBOUND, f"빠진 객체가 «{gone}» 로 살아 있다"
    assert row is None

    #: ★ 대조군 — 새 판에 남아 있는 객체는 그대로 보여야 한다.
    alive, arow, _ = ix.lookup(store, "dataset", "shipment", "SHP-000001",
                               TENANT, "VIRTUAL")
    assert alive == ix.FOUND and arow is not None

    #: ★ 그리고 **과거 시점에서는 여전히 있어야 한다** — 그때는 실제로 있었다.
    past, prow, _ = ix.lookup(store, "dataset", "shipment", "SHP-000003",
                              TENANT, "VIRTUAL", as_of="2026-04-01T00:00:00+00:00")
    assert past == ix.FOUND, "과거 시점의 사실까지 지워 버렸다"


@pytest.mark.parametrize("a,b", [
    ("2026-06-01T00:00:00Z", "2026-06-01T00:00:00+00:00"),
    ("2026-06-01T09:00:00+09:00", "2026-06-01T00:00:00+00:00"),
    ("2026-06-01T00:00:00", "2026-06-01T00:00:00+00:00"),
])
def test_같은_순간은_표기가_달라도_같다(a, b):
    """★★★ [P1] 종전에는 시각을 **문자열 그대로** 비교했다.

    ⚠️ `Z`·`+09:00`·소수초가 섞이면 **같은 순간인데 다르게** 정렬되고, `as_of` 가 몇
      시간씩 조용히 밀린다. 답은 그럴듯하게 나온다."""
    assert ix._utc(a) == ix._utc(b) != ""


def test_읽을_수_없는_시점은_지금으로_대신하지_않는다(store, workspace):
    """⚠️ 못 읽은 `as_of` 를 «지금» 으로 바꾸면 **다른 질문에 답하게** 된다."""
    _certify(store, workspace)
    with pytest.raises(ix.ScopeIndexError):
        ix.lookup(store, "dataset", "shipment", "SHP-000001", TENANT, "VIRTUAL",
                  as_of="언젠가")


def test_인증과_색인은_한_번에_커밋된다(store, workspace, monkeypatch):
    """★★★ [P1] 상태 전환과 색인 적재가 **한 트랜잭션**이어야 한다.

    ⚠️⚠️ 나누면 「인증됐는데 색인이 없는」 구간이 아무리 짧아도 생기고, 그때 읽은 쪽은
      승인된 관계의 끝점에서 503 을 만난다 — 아무도 아무것도 잘못하지 않았는데.
    ★ 색인 기록이 터지면 **인증도 함께 되돌아가야** 한다."""
    def boom(conn, payload, certified_at):
        raise RuntimeError("색인 저장 실패")

    monkeypatch.setattr(ix, "write_conn", boom)
    with pytest.raises(Exception):
        _certify(store, workspace)

    with store.transaction() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT state, certified_at FROM dataset_snapshots")]
    assert rows, "시험 전제가 깨졌다"
    for r in rows:
        assert r["state"] != m.DEMO_CERTIFIED, (
            "색인이 실패했는데 인증이 남았다 — 색인 없는 인증판이 존재한다")
        assert not r["certified_at"], "인증 시각이 찍혔다"


def test_표기가_다른_시각이_정렬을_뒤집지_않는다(store, workspace):
    """★★★ [P1] `_utc()` 를 만든 것만으로는 부족하다 — **정렬이 실제로 그것을 쓰는지**.

    ⚠️⚠️ 첫 판은 `_utc()` 자체만 시험했고, 「정렬 키를 문자열로 되돌리는」 변이가
      **살아남았다.** 도구를 만든 것과 도구를 쓰는 것은 다른 일이다.

    ★ 여기서는 두 판의 인증 시각을 **표기만 다르게** 준다:

        2026-06-01T09:00:00+09:00  = UTC 00:00  (실제로 **먼저**)
        2026-06-01T05:00:00+00:00  = UTC 05:00  (실제로 **나중**)

      문자열로 정렬하면 «05» < «09» 라서 **순서가 뒤집힌다.**"""
    first = _certify(store, workspace, rows=_shipment_rows(2),
                     certified_at="2026-06-01T09:00:00+09:00")
    second = _certify(store, workspace, rows=_shipment_rows(2),
                      certified_at="2026-06-01T05:00:00+00:00")
    status, row, _ = ix.lookup(store, "dataset", "shipment", "SHP-000001",
                               TENANT, "VIRTUAL")
    assert status == ix.FOUND, status
    assert row["snapshot_id"] == second["snapshot_id"], (
        "표기가 섞이자 나중 판을 먼저로 읽었다 — 시각을 문자열로 비교하고 있다")
    assert row["snapshot_id"] != first["snapshot_id"]
