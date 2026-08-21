"""★★★ **런타임 경로 → G5 근거** 어댑터를 검증한다. (§7 B1)

## 필수 회귀 (Supervisor 지정)

    ① 숨겨진 중간 노드가 있으면 **경로 전체 비노출**
    ② 권한 밖 구간 수·이름 **비누설**
    ③ `query_id`·`path_fingerprint` 가 G5 까지 **유지**
    ④ 경로 지문 불일치 시 **패키지 생성 거부**
    ⑤ 계산 미구현이 **0 또는 「영향 없음」으로 접히지 않음**
    ⑥ 기존 고정 경로 **fallback 부활 차단**

⚠️⚠️ ⑥이 가장 조용한 고장이다. 고정 경로는 **평소와 똑같이 생겼다** — 승인·범위·판을
  하나도 확인하지 않은 그림인데 화면에서는 구분되지 않는다.
"""
import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

from core import app_policy, calc_capability, ontology_resolve
from core import ontology_path_adapter as A
from core.ontology_runtime import ObjectRef, OntologyRuntime

TENANT, MODE, SCOPE = "tenant-demo", "VIRTUAL", "plant-demo"


@dataclass
class _Scope:
    readable_dept_ids: frozenset = frozenset({"org_demo"})
    writable_dept_ids: frozenset = frozenset({"org_demo"})
    unrestricted: bool = False


def _subject():
    return app_policy.Subject(
        user_id="u@example.com", scope=_Scope(),
        ctx={"tenant_id": TENANT, "entity_mode": MODE, "scope_node_id": SCOPE})


def _scope_obj(node=SCOPE):
    return app_policy.ResourceScope(
        tenant_id=TENANT, entity_mode=MODE, scope_node_id=node,
        owner_dept_id="org_demo", binding_state=app_policy.BOUND, status="active")


def _response(query_id="oq_test", as_of="2026-06-01T00:00:00+00:00", paths=None):
    """런타임 **응답 봉투.** ★ 어댑터는 이것만 받는다 — 질의와 경로를 따로 받으면
    서로 다른 실행에서 나온 둘을 섞을 수 있다."""
    return {"query_id": query_id, "as_of": as_of, "status": "COMPLETE",
            "paths": [_path()] if paths is None else paths}


def _path(*, edges=None, bindings=None, nodes=None, fingerprint="fp_path"):
    nodes = nodes if nodes is not None else [
        {"namespace": "dataset", "object_type": "purchase-order-line",
         "object_id": "PO-000001-10"},
        {"namespace": "dataset", "object_type": "shipment", "object_id": "SHP-000001"},
    ]
    edges = edges if edges is not None else [
        {"relation_id": "rel_1", "relation_type_id": "FULFILLED_BY_SHIPMENT",
         "calculation_ref": ""},
    ]
    default_bindings = {f"dataset:{n['object_type']}:{n['object_id']}": f"ds_{i}"
                        for i, n in enumerate(nodes)}
    return {"nodes": nodes, "edges": edges, "path_fingerprint": fingerprint,
            "bindings": default_bindings if bindings is None else bindings}


# ── ③ 정체성이 유지된다 ─────────────────────────────────────────────────

def test_질의_정체성이_근거에_실린다():
    """★★★ 없으면 「이 안건은 어느 질의의 어느 경로에서 나왔는가」에 답할 수 없다.

    ⚠️ 결과 지문은 **계산**을 재현하지만 **경로**를 재현하지 않는다."""
    out = A.to_evidence(_response("oq_abc", paths=[_path(fingerprint="fp_xyz")]))
    assert out["query_id"] == "oq_abc"
    assert out["path_fingerprint"] == "fp_xyz"
    assert out["as_of"] == "2026-06-01T00:00:00+00:00"


@pytest.mark.parametrize("broken", [
    {"query_id": ""}, {"query_id": "   "},
])
def test_정체성_없는_경로는_거부한다(broken):
    """⚠️ 정체성 없는 경로를 근거로 쓰면 나중에 되짚을 수 없다."""
    with pytest.raises(A.PathAdapterError):
        A.to_evidence({**_response(), **broken})


def test_지문_없는_경로는_거부한다():
    with pytest.raises(A.PathAdapterError):
        A.to_evidence(_response(paths=[_path(fingerprint="")]))


# ── ④ 지문 불일치 시 거부 ───────────────────────────────────────────────

def test_지문이_다르면_다른_경로다():
    """★ 어댑터는 지문을 **그대로** 옮긴다 — G5 가 대조할 수 있어야 한다."""
    a = A.to_evidence(_response(paths=[_path(fingerprint="fp_a")]))
    b = A.to_evidence(_response(paths=[_path(fingerprint="fp_b")]))
    assert a["path_fingerprint"] != b["path_fingerprint"]


#: ⚠️⚠️ [B1.2-1b · 2026-08-21] 여기 있던 `_binding(evidence)` 헬퍼를 **지웠다.**
#:   그것은 `evidence` 에서 `query_id`·`path_fingerprint` 를 **복사**해 `build()` 에 넘겼다.
#:   즉 「이 숫자가 이 경로에서 나왔다」를 증명한 것이 아니라 **호출자가 스스로 주장**한 것이고,
#:   그러면 아무 관계 없는 숫자에도 경로 ID 를 복사해 붙일 수 있다.
#:   같은 호출자가 넘긴 두 문자열 비교는 통제가 아니라 형식 검사다 —
#:   내가 만든 그 헬퍼가 구멍을 실제 결속처럼 보이게 했다.
#: ★ 진짜 결속은 계산기가 봉인한 결과 객체에서 온다(5b/B2). 그때까지 런타임 경로가 붙은
#:   숫자 패키지는 전면 거부이므로, 이 파일의 시험도 **숫자 없이** 사슬을 태운다.


def _calc_result(fingerprint="fp_calc", values=None):
    """`calc_graph.Result` 대역. ★ 제품과 **같은 필드 이름**을 쓴다."""
    from core import calc_graph as cg

    return cg.Result(values=values or {"production_qty": 100.0, "ending_inventory": 10.0,
                                       "purchase_payment": 5.0, "ending_cash": 7.0,
                                       "operating_profit": 3.0},
                     fingerprint=fingerprint, calc_version="1.0.0",
                     baseline_fingerprint="bl_1", data_kind="DEMO/SYNTHETIC",
                     assumptions={"fx_rate_pct": 0.0, "lead_time_days": 0.0,
                                  "power_price_pct": 0.0})


def test_정체성이_결정_패키지까지_실린다():
    """★★★ **B1 의 핵심 증명.** 어댑터 반환값에 필드가 있다는 것만으로는 부족하다 —
    `decision_package.build()` 가 실제로 그것을 **저장하는지** 봐야 한다.

    ⚠️⚠️ 첫 판의 시험은 두 지문이 다른지 보고 `build` 함수가 **존재하는지**만 봤다.
      패키지를 만들지도, 저장을 확인하지도 않았다. 그런데 나는 「G5·원장·발간까지
      유지된다」고 보고했다 — **증명된 것은 어댑터 반환값에 필드가 있다까지**였다."""
    from core import decision_package as dp

    evidence = A.to_evidence(_response("oq_keep", paths=[_path(fingerprint="fp_keep")]))
    #: ① 어댑터가 경로 정체성을 싣는가 — 이것이 이 시험의 본래 주제다.
    assert evidence["query_id"] == "oq_keep", evidence
    assert evidence["path_fingerprint"] == "fp_keep", evidence

    #: ② ⚠️ [B1.2-1b] 그 근거로 **숫자** 안건을 만드는 것은 이제 거부된다.
    #:   숫자가 이 경로에서 나왔다는 것을 서버가 확인할 수 없기 때문이다(5b/B2 미구현).
    base = _calc_result("fp_base")
    scenario = _calc_result("fp_scn", {"production_qty": 90.0, "ending_inventory": 12.0,
                                       "purchase_payment": 6.0, "ending_cash": 6.0,
                                       "operating_profit": 2.0})
    with pytest.raises(dp.DecisionError, match="런타임 온톨로지 경로"):
        dp.build(title="지연 영향", owner="owner@afs.invalid", due="2026-09-01",
                 base=base, scenario=scenario, path=evidence)


def test_정체성이_원장_저장과_지문까지_따라간다(tmp_path, monkeypatch):
    """★★★ 근거는 `decision_case` 에 **그대로 저장되고 해시된다.**

    ⚠️ 그러므로 경로 정체성이 바뀌면 `evidence_hash` 도 바뀌어야 한다 — 같은 해시로
      다른 경로를 가리키면 「같은 근거」라는 말이 거짓이 된다."""
    from core import decision_case as dc
    from core import decision_package as dp

    #: ★ 제품이 실제로 쓰는 싱글턴을 쓴다 — conftest 가 격리한 저장소를 그대로 탄다.
    store = dc.decision_case

    #: ★ [B1.2-1b] `build()` 를 거치지 않는다 — 런타임 경로 숫자 패키지는 거부되고, 이
    #  시험의 주제는 **근거가 원장 지문까지 따라가는가** 이지 숫자가 아니다.
    class _Ev:
        def __init__(self, fp):
            self.evidence = A.to_evidence(_response("oq_x", paths=[_path(fingerprint=fp)]))
            self.question = f"지연 영향({fp})"

    def _pkg(fp):
        return _Ev(fp)

    a, b = _pkg("fp_a"), _pkg("fp_b")
    case_a = store.create(question=a.question, created_by="owner@afs.invalid",
                          package={"baseline": "bl_1", "options": ["A", "B"]},
                          evidence=dict(a.evidence))
    case_b = store.create(question=b.question, created_by="owner@afs.invalid",
                          package={"baseline": "bl_1", "options": ["A", "B"]},
                          evidence=dict(b.evidence))
    #: ★ 저장된 근거에 정체성이 **그대로** 있다.
    fetched = store.get(case_a["decision_id"])
    stored = fetched.get("evidence") or fetched.get("evidence_json")
    if isinstance(stored, str):
        import json as _json
        stored = _json.loads(stored)
    assert stored and stored.get("path_fingerprint") == "fp_a", stored
    assert stored.get("query_id") == "oq_x", stored
    #: ★★★ 경로가 다르면 **근거 지문도 다르다** — 같은 해시로 다른 경로를 가리키지 않는다.
    assert case_a["evidence_hash"] != case_b["evidence_hash"], (
        "경로가 달라도 근거 지문이 같다 — 「같은 근거」라는 말이 거짓이 된다")


# ── ① 숨겨진 중간 노드 ──────────────────────────────────────────────────

def test_숨겨진_중간_노드가_있으면_경로가_아예_안_나온다(tmp_path):
    """★★★ 런타임이 **중간 노드를 건너뛴 경로를 만들지 않는다.**

    ⚠️⚠️ 건너뛰면 「A 가 C 에 영향을 준다」가 되는데, 그 사이의 B 를 볼 수 없는 사람에게
      그 문장은 **B 의 존재를 알려 준다.** 그리고 경로 자체도 사실이 아니다."""
    hidden = ObjectRef("dataset", "shipment", "SHP-숨김")

    def resolve(ref, ctx):
        if ref.key == hidden.key:
            #: 남의 조직 것 — 찾긴 하지만 PDP 가 막는다.
            return ontology_resolve.found(_scope_obj("plant-남의공장"),
                                          snapshot_id="ds_hidden")
        return ontology_resolve.found(_scope_obj(), snapshot_id="ds_ok")

    rt = OntologyRuntime(str(tmp_path / "o.db"), resolve, lambda *a, **k: True)
    out = rt.find_paths(_subject(), [ObjectRef("dataset", "purchase-order-line", "PO-1")],
                        ["sales-line"], [], "2026-06-01T00:00:00")
    #: ★ 관계가 하나도 없으므로 경로가 없다. 중요한 것은 **숨긴 채 이어 붙이지 않는다**는 것.
    assert out["paths"] == []
    assert out["status"] == "NO_VISIBLE_PATH"


# ── ② 구간 수·이름 비누설 ───────────────────────────────────────────────

def test_대외_사유는_구간_수를_말하지_않는다():
    """★★★ 「구간 3개 중 2개가 막혔습니다」는 **구간이 3개 있다는 사실**을 알려 준다.

    ⚠️ 권한이 없는 사람에게 그것은 이미 정보다."""
    blocked_edges = [
        {"relation_id": "r1", "relation_type_id": "AFFECTS",
         "calculation_ref": "CALC.LOGISTICS.ARRIVAL_DELAY.v1"},
        {"relation_id": "r2", "relation_type_id": "AFFECTS",
         "calculation_ref": "CALC.INVENTORY.MATERIAL_SHORTAGE.v1"},
    ]
    out = A.to_evidence(_response(paths=[_path(edges=blocked_edges)]))
    text = out["blocked_reason"]
    assert text == A.PUBLIC_BLOCKED
    import re
    assert not re.search(r"\d", text), f"대외 사유에 숫자가 있다 — {text}"
    for leak in ("CALC.", "relation", "rel_", "r1", "구간"):
        assert leak not in text, f"대외 사유가 «{leak}» 를 누설한다 — {text}"
    #: ★ 대외 근거 어디에도 구간 목록이 없어야 한다.
    assert "segments" not in out


def test_내부_진단에서는_구간과_사유를_그대로_본다():
    """★ 대조군 — 권한 있는 사람은 **무엇이 왜 막혔는지** 알아야 고칠 수 있다."""
    edges = [{"relation_id": "r1", "relation_type_id": "AFFECTS",
              "calculation_ref": "CALC.LOGISTICS.ARRIVAL_DELAY.v1"}]
    diag = A.internal_diagnosis(_response(paths=[_path(edges=edges)]), authorize=lambda: True)
    seg = diag["segments"][0]
    assert seg["calculation_ref"] == "CALC.LOGISTICS.ARRIVAL_DELAY.v1"
    assert seg["executable"] is False
    assert seg["reason"], "내부 진단에 사유가 없다"


# ── ⑤ 계산 미구현이 「영향 없음」으로 접히지 않는다 ─────────────────────

def test_계산이_막히면_완결이_아니다():
    """★★★ 근거가 다 있어도 **계산이 막히면 완결이 아니다.**

    ⚠️⚠️ `complete=True` 로 두면 화면이 「이 경로는 다 설명됐다」고 말하고, 수치가
      비어 있는 것을 사람은 **「영향이 없다」**로 읽는다."""
    edges = [{"relation_id": "r1", "relation_type_id": "AFFECTS",
              "calculation_ref": "CALC.INVENTORY.MATERIAL_SHORTAGE.v1"}]
    out = A.to_evidence(_response(paths=[_path(edges=edges)]))
    assert out["calculation_blocked"] is True
    assert out["complete"] is False
    assert out["blocked_reason"]


def test_수치를_0_으로_채우지_않는다():
    """⚠️ 0 은 「영향이 없다」로 읽힌다. **없는 것은 없는 채로** 둔다."""
    edges = [{"relation_id": "r1", "relation_type_id": "AFFECTS",
              "calculation_ref": "CALC.PRODUCTION.REVENUE_TIMING.v1"}]
    out = A.to_evidence(_response(paths=[_path(edges=edges)]))
    for forbidden in ("metrics", "values", "segment_outputs", "result_fingerprint"):
        assert forbidden not in out, f"막혔는데 «{forbidden}» 를 실었다"


def test_정성_관계는_막힘이_아니다():
    """★ 대조군 — 계산이 **없는** 관계(`FULFILLED_BY_SHIPMENT`)까지 막으면 검사가
    늑대를 외친다."""
    out = A.to_evidence(_response())
    assert out["calculation_blocked"] is False
    assert out["complete"] is True
    assert out["blocked_reason"] == ""


def test_계약에_없는_참조가_붙어_있으면_막는다():
    """⚠️ 계약에 없는 계산 이름이 관계에 붙어 있는 것은 **조용히 넘길 일이 아니다.**"""
    edges = [{"relation_id": "r1", "relation_type_id": "AFFECTS",
              "calculation_ref": "CALC.MADE.UP.v9"}]
    out = A.to_evidence(_response(paths=[_path(edges=edges)]))
    assert out["calculation_blocked"] is True
    diag = A.internal_diagnosis(_response(paths=[_path(edges=edges)]), authorize=lambda: True)
    assert "계약에 없는" in diag["segments"][0]["reason"]


# ── 근거가 빠진 칸을 숨기지 않는다 ──────────────────────────────────────

def test_판이_안_묶인_칸을_드러낸다():
    """★ 빼면 「전부 근거가 있다」로 보이고, 그것이 곧 근거 없는 계보다."""
    out = A.to_evidence(_response(paths=[_path(bindings={})]))
    assert out["missing_evidence"], "근거 없는 칸을 숨겼다"
    assert out["complete"] is False
    #: ★★★ 사람이 읽는 이름으로도 나와야 한다 — 계약키만 주면 안 읽힌다.
    labels = {s["label"] for s in out["missing_steps"]}
    assert "구매주문 라인" in labels or "선적" in labels, labels


def test_사람이_읽는_이름을_쓴다():
    """⚠️ 기계 이름(`inventory-snapshot`)을 경영진 화면에 그대로 내보내면 읽는 사람은
    그것이 무엇인지 모른 채 「모르는 게 있구나」로만 넘긴다."""
    out = A.to_evidence(_response())
    labels = [s["label"] for s in out["path"]]
    assert labels == ["구매주문 라인", "선적"], labels


def test_모르는_유형은_이름을_지어내지_않는다():
    """★ 표에 없으면 기계 이름을 그대로 둔다 — 지어내면 **틀린 이름이 굳는다.**"""
    nodes = [{"namespace": "dataset", "object_type": "brand-new-thing",
              "object_id": "X-1"}]
    out = A.to_evidence(_response(paths=[_path(nodes=nodes, edges=[])]))
    assert out["path"][0]["label"] == "brand-new-thing"


# ── ⑥ 고정 경로 fallback 차단 ───────────────────────────────────────────

def test_고정_경로로_되돌아가지_않는다():
    """★★★ **가장 조용한 고장.**

    ⚠️⚠️ `core/ontology_path.py` 는 칸 이름이 박힌 고정 경로다. 런타임 경로를 못
      만들었을 때 그쪽으로 흘리면, 화면은 승인·범위·판을 **하나도 확인하지 않은
      그림**을 「영향 경로」로 보여 준다 — 그리고 평소와 똑같이 생겼다.
    ★ 산문이 아니라 구문 나무를 본다(주석·문자열은 안 잡힌다)."""
    tree = ast.parse(Path(A.__file__).read_text(encoding="utf-8"))
    imported, used = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.Name):
            used.add(node.id)
    for forbidden in ("ontology_path", "calc_graph", "planning_engine"):
        assert not any(forbidden in name for name in imported), (
            f"어댑터가 «{forbidden}» 를 부른다: {sorted(imported)}")
        assert forbidden not in used, f"어댑터가 «{forbidden}» 를 참조한다"
    for forbidden in ("impact_path", "trace", "simulate"):
        assert forbidden not in used, f"어댑터가 «{forbidden}» 를 부른다"


def test_계산_판정을_스스로_하지_않는다():
    """★ 실행 가능 여부는 §5a 가 정한다 — 두 곳에서 판정하면 규칙이 갈라진다."""
    tree = ast.parse(Path(A.__file__).read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "calc_capability" in names, "§5a 를 쓰지 않고 스스로 판정한다"
    assert "NOT_IMPLEMENTED" not in names and "NOT_IMPLEMENTED" not in attrs, (
        "어댑터가 상태를 직접 비교한다 — 판정은 §5a 의 `executable` 로만")


def test_이름표는_닫힌_표다():
    """⚠️ 최소 경로 다섯 유형 밖의 이름을 지어내지 않는다."""
    #: ★★★ [B1.1-4] 열쇠는 `(namespace, object_type)` 이다. `object_type` 만 쓰면 다른
    #:   namespace 의 같은 이름이 **같은 칸으로 접힌다.**
    assert set(A.LABELS) == {
        ("dataset", "purchase-order-line"), ("dataset", "shipment"),
        ("dataset", "inventory-snapshot"), ("dataset", "production-plan-line"),
        ("dataset", "sales-line")}


def test_계약키_표를_두_벌로_두지_않는다():
    """★ 범위 색인의 표를 **뒤집어 쓴다** — 두 벌로 두면 언젠가 갈라진다."""
    from core.data_preparation import scope_index as ix

    assert set(A._DATASET_BY_TYPE.values()) == set(ix.CONTRACT_OBJECTS)
    for key, (ns, object_type, _col) in ix.CONTRACT_OBJECTS.items():
        #: ⚠️ `namespace` 를 버리면 안 된다 — 계약이 닫힌 지금은 우연히 맞지만,
        #:   `mdm:material` 같은 것이 열리는 순간 조용히 틀린다.
        assert A._DATASET_BY_TYPE[(ns, object_type)] == key


def test_경로_지문은_판에_흔들리지_않는다(tmp_path):
    """★★★ **경로 정체성은 위상이지 판이 아니다.** (A rev.2 §3.6)

    ⚠️⚠️ `bindings` 를 지문 재료로 넣으면 `as_of` 를 바꿀 때마다 **같은 경로가 다른
      경로**가 되어 대조가 무너진다. 「지문이 다르니 다른 경로군요」가 되는데 실제로는
      같은 배·같은 주문행을 지나는 같은 길이다.

    ★ 「어느 판을 봤는가」는 **결과 쪽 사실**이고, 결과 지문에 든다."""
    rt = OntologyRuntime(str(tmp_path / "o.db"), lambda ref, ctx: None,
                         lambda *a, **k: True)
    nodes = [ObjectRef("dataset", "purchase-order-line", "PO-1"),
             ObjectRef("dataset", "shipment", "SHP-1")]
    edges = [{"relation_id": "r1", "relation_type_id": "FULFILLED_BY_SHIPMENT",
              "version": 1, "evidence_refs_json": "[]", "calculation_ref": "",
              "effective_from": "2026-01-01", "effective_to": "",
              "ledger_correlation_id": "ev_1"}]
    march = rt._path(nodes, edges, {"dataset:shipment:SHP-1": "ds_march"})
    june = rt._path(nodes, edges, {"dataset:shipment:SHP-1": "ds_june"})

    assert march["path_fingerprint"] == june["path_fingerprint"], (
        "판이 바뀌자 경로 지문이 바뀌었다 — 같은 길을 다른 길로 센다")
    #: ★ 그래도 **결속은 실려 있어야** 한다 — 그것 없이는 근거를 되짚을 수 없다.
    assert march["bindings"]["dataset:shipment:SHP-1"] == "ds_march"
    assert june["bindings"]["dataset:shipment:SHP-1"] == "ds_june"


# ══════════════════════════════════════════════════════════════════════════
# B1.1 감사 보정 (2026-08-21)
# ══════════════════════════════════════════════════════════════════════════

def test_봉투_밖의_경로를_붙일_수_없다():
    """★★★ [P0-2] 첫 판은 `to_evidence(query, path)` 였다. 그러면 호출부가 **서로 다른
    실행에서 나온 둘을 섞을 수 있다** — 3월 질의에 6월 경로를 붙이는 식으로.

    ⚠️⚠️ 경로 지문은 판에 흔들리지 않게 만들었으므로(A rev.2 §3.6) **모양으로는 구별되지
      않는다.** 둘 다 개별적으로 멀쩡해서 어댑터가 통과시킨다."""
    march = _response("oq_march", as_of="2026-03-01T00:00:00+00:00",
                      paths=[_path(fingerprint="fp_march")])
    #: 6월 실행의 경로를 3월 봉투에 붙이려는 시도.
    with pytest.raises(A.PathAdapterError) as err:
        A.to_evidence(march, path_fingerprint="fp_june")
    assert "없는 경로" in str(err.value)


def test_경로가_여럿이면_아무거나_고르지_않는다():
    """⚠️ 고르면 실행마다 답이 달라지고, 「이 안건은 어느 경로에서 나왔나」가 흔들린다."""
    many = _response(paths=[_path(fingerprint="fp_a"), _path(fingerprint="fp_b")])
    with pytest.raises(A.PathAdapterError):
        A.to_evidence(many)
    #: ★ 대조군 — 지문으로 고르면 통과한다.
    picked = A.to_evidence(many, path_fingerprint="fp_b")
    assert picked["path_fingerprint"] == "fp_b"


def test_같은_유형이_두_번_나와도_판이_사라지지_않는다():
    """★★★ [P1] `used_snapshots` 를 계약키 열쇠 딕셔너리로 두면, 같은 유형이 경로에 두
    번 나올 때 **앞 판이 조용히 사라진다.**

    ⚠️ 그러면 「이 답은 어느 판들로 만들었나」가 틀린 채로 남고, 아무도 못 알아챈다."""
    nodes = [
        {"namespace": "dataset", "object_type": "shipment", "object_id": "SHP-1"},
        {"namespace": "dataset", "object_type": "shipment", "object_id": "SHP-2"},
    ]
    bindings = {"dataset:shipment:SHP-1": "ds_first",
                "dataset:shipment:SHP-2": "ds_second"}
    out = A.to_evidence(_response(paths=[_path(nodes=nodes, edges=[], bindings=bindings)]))
    used = out["used_snapshots"]
    assert isinstance(used, list), f"딕셔너리로 두면 판이 사라진다 — {used!r}"
    assert {u["snapshot_id"] for u in used} == {"ds_first", "ds_second"}, used


def test_정량_관계에_계산이_없으면_무결성_장애다():
    """★★★ [P1] `AFFECTS` 는 계약상 **정량 관계**다(계약의 유일한 정량 관계).

    ⚠️⚠️ `calculation_ref` 없이 들어오면 첫 판은 «정성 관계» 로 보고 **통과시켰다.**
      그러면 그 관계는 숫자 없이 서고, 화면은 그 자리를 «영향 없음» 으로 그린다."""
    edges = [{"relation_id": "r1", "relation_type_id": "AFFECTS",
              "calculation_ref": ""}]
    with pytest.raises(A.PathIntegrityError):
        A.to_evidence(_response(paths=[_path(edges=edges)]))


def test_정성_관계는_계산이_없어도_된다():
    """★ 대조군 — 계약상 정량이 아닌 관계까지 막으면 검사가 늑대를 외친다."""
    out = A.to_evidence(_response())
    assert out["complete"] is True


def test_승인된_계산도_원장을_다시_보고_판정한다(monkeypatch):
    """★★★ [P1] `cap.executable` 만 읽으면 등록부의 «그때 그랬다» 를 믿는 것이다.

    ⚠️⚠️ **철회는 등록부를 고치지 않는다.** 그래서 §5a 의 `assert_executable()` 을
      통과시킨다 — 그 안에 원장 재검증이 있다.
    ★ 검증기가 없으면 실행 가능으로 **표시하지 않는다.** 지금은 아무것도 `APPROVED`
      가 아니라 결과가 같지만, 승인이 생긴 뒤에 넣으면 **그 사이가 열린다.**"""
    ref = "CALC.LOGISTICS.ARRIVAL_DELAY.v1"
    base = calc_capability.get(ref)
    approved = calc_capability.Capability(
        **{**base.__dict__, "state": calc_capability.APPROVED,
           "model_version": "1.0.0", "ledger_event_id": "ev_1", "blocked_reason": ""})
    monkeypatch.setitem(calc_capability._REGISTRY, ref, approved)
    edges = [{"relation_id": "r1", "relation_type_id": "AFFECTS",
              "calculation_ref": ref}]
    envelope = _response(paths=[_path(edges=edges)])

    #: ① 검증기 없음 → 실행 가능으로 표시하지 않는다.
    out = A.to_evidence(envelope)
    assert out["calculation_blocked"] is True, "승인만 보고 통과시켰다"

    #: ② 철회됐다 → 막는다.
    revoked = A.to_evidence(envelope, ledger_verifier=lambda cap: False)
    assert revoked["calculation_blocked"] is True

    #: ③ 대조군 — 확인되면 통과한다.
    ok = A.to_evidence(envelope, ledger_verifier=lambda cap: True)
    assert ok["calculation_blocked"] is False, ok


def test_내부_진단은_권한을_요구한다():
    """★★★ [B1.1-7] 첫 판은 **주석으로만** 「권한 있는 사람에게만」이라고 적었다.

    ⚠️⚠️ 주석은 통제가 아니다. 구간 수 자체가 정보이므로, 권한 검사 없이 열린 진단은
      **권한 밖 사람에게 구간이 몇 개인지 알려 준다.**"""
    envelope = _response()
    with pytest.raises(A.PathAdapterError):
        A.internal_diagnosis(envelope, authorize=lambda: False)
    with pytest.raises(A.PathAdapterError):
        A.internal_diagnosis(envelope, authorize=None)

    def boom():
        raise RuntimeError("권한 저장소가 응답하지 않습니다")

    with pytest.raises(A.PathAdapterError) as broken:
        A.internal_diagnosis(envelope, authorize=boom)
    assert "확인하지 못했" in str(broken.value)

    #: ★ 대조군 — 권한이 있으면 열린다. 늘 막히면 통제가 아니라 고장이다.
    opened = A.internal_diagnosis(envelope, authorize=lambda: True)
    assert opened["segments"], "권한이 있는데도 진단이 비어 있다"
    assert opened["query_id"] and opened["path_fingerprint"]


def test_형제_분기가_서로의_결속을_덮지_않는다(tmp_path):
    """★★★ [P0-3] `bindings` 딕셔너리 **하나를 모든 분기가 공유**하면, 나중 분기의
    결속이 앞 분기의 경로 결과를 덮는다.

    ## 어떻게 덮이나

        R ─rel1→ SHP-A ─rel3→ SHP-B ─…      (A 를 거쳐 B 에 닿는 가지)
        R ─rel2→ SHP-B ─rel4→ 목표          (B 로 바로 가는 가지)

    ⚠️⚠️ BFS 는 깊이 1 을 **전부** 처리한 뒤 깊이 2 로 간다. `SHP-A` 가 먼저 꺼내지면
      그 가지가 `SHP-B` 를 `rel3` 문맥으로 다시 해석해 **공유 딕셔너리를 덮는다.**
      그 뒤에 `SHP-B` 가지가 꺼내져 목표에 닿을 때, 그 경로는 자기가 본 적 없는
      `rel3` 의 판을 근거로 싣게 된다.

    ★ 두 경로 다 그럴듯하게 남는다 — 어느 쪽이 무엇을 봤는지 알 수 없다."""
    from core.ontology_runtime import RelationProposal

    seen_ctx = {}

    def resolve(ref, ctx):
        #: ★ 같은 객체를 **관계마다 다른 판**으로 해석한다 — 봉인된 판이 다른 상황.
        snapshot = f"ds_{ctx.relation_id or 'root'}"
        seen_ctx.setdefault(ref.key, []).append(snapshot)
        return ontology_resolve.found(_scope_obj(), snapshot_id=snapshot)

    rt = OntologyRuntime(str(tmp_path / "o.db"), resolve, lambda *a, **k: True)
    rt.register_relation_type("AFFECTS", "영향을 줌", "AFFECTED_BY", True, "1.0.0",
                              "model_owner", "2026-01-01T00:00:00Z",
                              ledger_correlation_id="led-affects")
    rt.register_constraint("dataset", "shipment", "AFFECTS", "dataset", "shipment",
                           ["approved delay model"], "model_owner",
                           "CALC.LOGISTICS.ARRIVAL_DELAY.v1")

    def ref(oid):
        return ObjectRef("dataset", "shipment", oid)

    def approve(a, b):
        proposal = RelationProposal(
            subject=ref(a), relation_type_id="AFFECTS", object=ref(b),
            tenant_id=TENANT, enterprise_scope_id=SCOPE, entity_mode=MODE,
            owner_organization_id="org_demo", effective_from="2026-01-01T00:00:00Z",
            origin="derived", evidence_refs=("SNAPSHOT:LOG-02:v1",),
            calculation_ref="CALC.LOGISTICS.ARRIVAL_DELAY.v1")
        row = rt.propose_relation(proposal, "steward", _subject())
        row = rt.submit(row["relation_id"], "steward", _subject())
        return rt.approve(row["relation_id"], "governor", "led-1", _subject())

    #: `SHP-A` 가 `SHP-B` 보다 먼저 꺼내지도록 id 를 고른다(정렬 열쇠가 object_id 다).
    approve("SHP-ROOT", "SHP-A")
    approve("SHP-ROOT", "SHP-B")
    approve("SHP-A", "SHP-B")
    approve("SHP-B", "SHP-TARGET")

    out = rt.find_paths(_subject(), [ref("SHP-ROOT")], ["shipment"], [],
                        "2026-06-01T00:00:00")
    assert out["paths"], out

    #: ★★★ 각 경로의 결속은 **그 경로가 실제로 지난 관계**에서 나와야 한다.
    for path in out["paths"]:
        by_key = {n["object_id"]: n for n in path["nodes"]}
        edges = path["edges"]
        for i, node in enumerate(path["nodes"][1:], start=0):
            key = f"dataset:shipment:{node['object_id']}"
            expected = f"ds_{edges[i]['relation_id']}"
            assert path["bindings"][key] == expected, (
                f"경로 {[n['object_id'] for n in path['nodes']]} 의 «{node['object_id']}» "
                f"결속이 {path['bindings'][key]} 다 — 형제 분기가 덮었다(기대 {expected})")


# ══════════════════════════════════════════════════════════════════════════
# B1.2 — 계산 불가 경로 차단 · 근거 지문 사슬 (2026-08-21)
# ══════════════════════════════════════════════════════════════════════════

def _blocked_envelope():
    edges = [{"relation_id": "r1", "relation_type_id": "AFFECTS",
              "calculation_ref": "CALC.INVENTORY.MATERIAL_SHORTAGE.v1"}]
    return _response(paths=[_path(edges=edges)])


def test_계산할_수_없는_경로로_숫자_안건을_만들지_않는다():
    """★★★ [P0] 종전에는 `calculation_blocked` 를 근거에 **적어 두기만** 했다.

    ⚠️⚠️ 그래서 한 패키지 안에 이 둘이 **동시에** 실렸다:

        「이 경로는 아직 계산할 수 없습니다」
        「영업이익이 -200,000,000원 변합니다 — 지금 무엇을 결정해야 합니까?」

    ★ 사람은 **숫자를 읽는다.** 옆줄의 「계산할 수 없습니다」는 각주로 읽히고, 그 숫자는
      이 경로와 아무 상관이 없다 — 기존 시나리오 엔진의 결과다."""
    from core import decision_package as dp

    ev = A.to_evidence(_blocked_envelope())
    assert ev["calculation_blocked"] is True, ev
    with pytest.raises(dp.DecisionError) as err:
        dp.build(title="지연 영향", owner="o@afs.invalid", due="2026-09-01",
                 base=_calc_result("fp_b"),
                 scenario=_calc_result("fp_s", {"production_qty": 90.0,
                                                "ending_inventory": 12.0,
                                                "purchase_payment": 6.0,
                                                "ending_cash": 6.0,
                                                "operating_profit": 2.0}),
                 path=ev)
    #: ⚠️ [B1.2-1b] 사유 문구가 바뀌었다 — 런타임 경로면 **계산 가능 여부를 보기 전에**
    #:   막는다(숫자가 그 경로에서 나왔다는 확인 수단이 없으므로). 둘 다 거부이고,
    #:   여기서 확인할 것은 「숫자 안건이 만들어지지 않는다」이다.
    assert ("계산할 수 없" in str(err.value)
            or "런타임 온톨로지 경로" in str(err.value)), str(err.value)


def test_근거가_빠진_경로로도_숫자_안건을_만들지_않는다():
    """⚠️ 계산이 열려도 **근거 없는 칸이 있으면** 완결이 아니다."""
    from core import decision_package as dp

    ev = A.to_evidence(_response(paths=[_path(bindings={})]))
    assert ev["complete"] is False
    with pytest.raises(dp.DecisionError):
        dp.build(title="x", owner="o@afs.invalid", due="2026-09-01",
                 base=_calc_result("fp_b"),
                 scenario=_calc_result("fp_s", {"production_qty": 90.0,
                                                "ending_inventory": 12.0,
                                                "purchase_payment": 6.0,
                                                "ending_cash": 6.0,
                                                "operating_profit": 2.0}),
                 path=ev)


def test_경로_없는_기존_패키지는_그대로_돈다():
    """★ 대조군 — 온톨로지를 안 쓰는 기존 흐름까지 막으면 그것은 회귀다."""
    from core import decision_package as dp

    pkg = dp.build(title="기존 흐름", owner="o@afs.invalid", due="2026-09-01",
                   base=_calc_result("fp_b"),
                   scenario=_calc_result("fp_s", {"production_qty": 90.0,
                                                  "ending_inventory": 12.0,
                                                  "purchase_payment": 6.0,
                                                  "ending_cash": 6.0,
                                                  "operating_profit": 2.0}))
    assert pkg.question


def test_막힌_경로는_원장에_아무_행도_남기지_않는다():
    """★★★ 「일단 만들고 화면에서 가리자」가 안 되는 이유 — **안건은 원장에 남고
    발간으로 나간다.**"""
    from core import decision_case as dc
    from core import decision_package as dp

    before = len(dc.decision_case.list_cases()) if hasattr(
        dc.decision_case, "list_cases") else None
    with pytest.raises(dp.DecisionError):
        dp.build(title="x", owner="o@afs.invalid", due="2026-09-01",
                 base=_calc_result("fp_b"),
                 scenario=_calc_result("fp_s", {"production_qty": 90.0,
                                                "ending_inventory": 12.0,
                                                "purchase_payment": 6.0,
                                                "ending_cash": 6.0,
                                                "operating_profit": 2.0}),
                 path=A.to_evidence(_blocked_envelope()))
    if before is not None:
        assert len(dc.decision_case.list_cases()) == before, "막혔는데 행이 남았다"


def test_경로_정체성이_발간까지_따라간다():
    """★★★ [B1.2-2] **사슬 전체를 태운다.**

        Decision Package → Decision Case 저장 → evidence_hash
        → Publication 생성 · render → source_evidence_hash 대조
        → 원천 Case 에서 query_id·path_fingerprint 재조회

    ⚠️ 종전 보고는 「원장·발간까지 유지」였지만 **발간 종단은 태운 적이 없었다.**
      코드에 `source_evidence_hash` 를 옮기는 줄이 있다는 것까지가 확인된 전부였다."""
    from core import decision_case as dc
    from core import decision_package as dp
    from core import publication as pub

    #: ★★ [B1.2-1b] **숫자 없이** 사슬을 태운다. 이 시험의 주제는 「근거 지문이 원장에서
    #:   발간까지 그대로 옮겨지는가」이고, 숫자는 그 주제와 무관하다. 종전에는 정성 경로에
    #:   결속되지 않은 시나리오 숫자를 붙여 통과했는데 — **그 시험이 구멍을 지키고 있었다.**
    ev = A.to_evidence(_response("oq_chain", paths=[_path(fingerprint="fp_chain")]))
    assert ev["complete"] is True, ev
    case = dc.decision_case.create(
        question="지연 영향 — 근거 안건(숫자 없음)", created_by="owner@afs.invalid",
        package={"baseline": "bl_1", "options": ["A", "B"]},
        evidence=dict(ev))

    #: ① Decision Case 에 그대로 저장됐는가.
    fetched = dc.decision_case.get(case["decision_id"])
    stored = fetched.get("evidence")
    if isinstance(stored, str):
        import json as _json
        stored = _json.loads(stored)
    assert stored["query_id"] == "oq_chain", stored
    assert stored["path_fingerprint"] == "fp_chain", stored

    #: ② 발간이 그 근거 지문을 옮기는가.
    publication = pub.publication.create(
        title="경영 브리핑", created_by="owner@afs.invalid",
        source_type="DECISION_CASE", source_id=case["decision_id"])
    rendered = pub.publication.render(publication["publication_id"], "owner@afs.invalid")
    #: ★ 렌더 결과는 발간 레코드다. 문서는 **판본**에 들어 있다.
    current = rendered.get("current_version") or {}
    evidence = (current.get("document") or {}).get("evidence") or {}
    assert evidence.get("source_evidence_hash") == case["evidence_hash"], evidence

    #: ③ ★★★ 발간본의 지문으로 **원천을 되짚어** 경로 정체성을 다시 얻는다.
    #:   이것이 「원장·발간까지 유지된다」의 실제 뜻이다.
    back = dc.decision_case.get(evidence["source_id"])
    back_ev = back.get("evidence")
    if isinstance(back_ev, str):
        import json as _json
        back_ev = _json.loads(back_ev)
    assert back_ev["path_fingerprint"] == "fp_chain", back_ev


def test_두_깃발을_따로_본다():
    """★★★ 어댑터에서는 `complete` 와 `calculation_blocked` 가 늘 함께 움직인다
    (`complete = not missing and not blocked`). 그래서 하나만 봐도 지금은 통과한다.

    ⚠️⚠️ 그러나 `path` 는 **어댑터만 만드는 것이 아니다.** 다른 호출부·화면·연동이
      손으로 만든 딕셔너리를 넘길 수 있고, 그때 한쪽만 보면 **문이 열린다.**
    ★ 그래서 둘을 **따로** 본다 — 「지금은 같이 움직이니까」는 계약이 아니다."""
    from core import decision_package as dp

    scenario = _calc_result("fp_s", {"production_qty": 90.0, "ending_inventory": 12.0,
                                     "purchase_payment": 6.0, "ending_cash": 6.0,
                                     "operating_profit": 2.0})
    for hand_made in (
            {"complete": True, "calculation_blocked": True},      # 차단인데 완결이라 주장
            {"complete": False, "calculation_blocked": False},     # 미완결인데 차단 아님
            #: ★ 뒤엣것은 **런타임 경로일 때만** 막는다 — `query_id` 가 그 표시다.
    ):
        with pytest.raises(dp.DecisionError):
            dp.build(title="x", owner="o@afs.invalid", due="2026-09-01",
                     base=_calc_result("fp_b"), scenario=scenario,
                     path={"path": [], "query_id": "oq_1", "path_fingerprint": "fp_1",
                           **hand_made})

    #: ★ 대조군 — 차단이 «전부 막는 것» 이 되면 통제가 아니라 고장이다.
    #: ⚠️ [B1.2-1b] 런타임 경로(`query_id` 있음)로는 이제 **어떤 경우에도** 숫자 안건을 만들 수
    #:   없으므로, 대조군을 **고정 경로**(`query_id` 없음)로 옮긴다. 고정 경로는 근거가 빠진
    #:   단계를 브리핑에 드러내는 것이 통제이고, 그것까지 막으면 그 장치가 도달 불가능해진다.
    #: ⚠️ 대조군은 **실제 고정 경로 모양**이어야 한다. 실측 확인: `ontology_path.trace()` 는
    #:   `query_id` 도 `path_fingerprint` 도 내지 않는다. 종전 이 대조군은
    #:   `path_fingerprint="fp_1"` 을 넣고 있었는데 — 현실에 없는 모양이었고, 판별을 넓히자
    #:   바로 걸렸다. 픽스처가 현실에 없는 모양이면 그 초록은 아무것도 보증하지 않는다.
    ok = dp.build(title="x", owner="o@afs.invalid", due="2026-09-01",
                  base=_calc_result("fp_b"), scenario=scenario,
                  path={"path": [], "complete": True, "calculation_blocked": False})
    assert ok.evidence["query_id"] == "" and ok.evidence["path_fingerprint"] == ""


# ── ★★★ [B1.2-1a] 완결 경로라도 «남의 숫자» 는 붙일 수 없다 ─────────────────

def _complete_path(qid="oq_c", fp="fp_c"):
    return {"path": [], "query_id": qid, "path_fingerprint": fp,
            "complete": True, "calculation_blocked": False}


def _numbers():
    return (_calc_result("fp_b"),
            _calc_result("fp_s", {"production_qty": 90.0, "ending_inventory": 12.0,
                                  "purchase_payment": 6.0, "ending_cash": 6.0,
                                  "operating_profit": 2.0}))


def test_결속_선언이_없으면_완결_경로라도_숫자_안건을_만들지_않는다():
    """★★★ B1.2-1 이 남긴 구멍이다.

    「계산할 수 없습니다」는 사라졌는데 **숫자는 여전히 남의 것**이었다 — 정성 런타임
    경로(`complete=True`)에 그 경로와 결속되지 않은 기존 시나리오 엔진 결과를 붙여
    숫자 안건을 만들 수 있었다. 재감사에서 「발간 회귀가 바로 그 방식으로 통과한다」고
    지적된 자리다.

    ⚠️ 계산 결과와 경로를 **대조**하는 것(B2)은 아직 없다. 없는 대조를 있는 척하지 않고,
      결속 선언이 없으면 막는다 — 「일단 만들고 나중에 검증」은 안 된다. 안건은 원장에
      남고 발간으로 나간다."""
    from core import decision_package as dp
    base, scenario = _numbers()
    with pytest.raises(dp.DecisionError, match="런타임 온톨로지 경로"):
        dp.build(title="x", owner="o@afs.invalid", due="2026-09-01",
                 base=base, scenario=scenario, path=_complete_path())


def test_경로_ID_를_복사해_넘겨도_통과하지_않는다():
    """★★★ [B1.2-1b] 직전 구현(B1.2-1a)이 정확히 여기서 뚫렸다.

    호출자가 `calc_binding` 으로 경로의 `query_id`·`path_fingerprint` 를 **복사**해 넘기면
    통과했다. 그것은 결속 증명이 아니라 **자기진술**이다 — 같은 호출자가 넘긴 두 문자열을
    비교하는 것은 통제가 아니라 형식 검사다.

    이제 `calc_binding` 인자 자체가 없다. 넘기면 `TypeError` 이고, 넘기지 않아도 런타임
    경로면 거부다 — **복사해서 통과할 방법이 없다.**"""
    from core import decision_package as dp
    base, scenario = _numbers()
    with pytest.raises(TypeError):
        dp.build(title="x", owner="o@afs.invalid", due="2026-09-01",
                 base=base, scenario=scenario, path=_complete_path("oq_c", "fp_c"),
                 calc_binding={"query_id": "oq_c", "path_fingerprint": "fp_c"})


def test_식별자가_한쪽만_있어도_런타임으로_보고_막는다():
    """★★ 재감사 지적 — **`query_id` 만 보면 `path_fingerprint` 만 남은 런타임 모양이
    고정 경로로 오인된다.** 둘 중 하나만 있어도 런타임으로 본다.

    ⚠️⚠️ 종전 이 시험은 `{**_complete_path("oq_c","fp_c"), **half}` 로 썼다. `_complete_path`
      가 이미 두 값을 다 넣고 `**half` 가 **같은 값으로 덮으므로**, 한쪽이 빠지는 상황이
      만들어지지 않았다 — 주장과 다른 것을 시험하고 있었다. 이제 **키를 실제로 뺀다.**
    ★ 고정 경로를 잘못 막지 않는다는 근거: `ontology_path.trace()` 는 두 식별자를 둘 다
      내지 않는다(실측 확인).
    """
    from core import decision_package as dp
    base, scenario = _numbers()
    for only in ("query_id", "path_fingerprint"):
        path = {"path": [], "complete": True, "calculation_blocked": False,
                only: "x_only"}
        assert "query_id" not in path or "path_fingerprint" not in path,             "한쪽이 실제로 빠져 있어야 한다 — 덮으면 이 시험은 아무것도 보증하지 않는다"
        with pytest.raises(dp.DecisionError, match="런타임 온톨로지 경로"):
            dp.build(title="x", owner="o@afs.invalid", due="2026-09-01",
                     base=base, scenario=scenario, path=path)


def test_고정_경로_숫자_안건은_그대로_만들어진다():
    """★ 대조군 — 런타임 경로만 막는다. 고정 경로(`query_id` 없음)는 그대로 돈다.

    ⚠️ 여기까지 막으면 「근거가 빠진 단계를 브리핑에 드러낸다」는 통제가 **도달 불가능**해진다."""
    from core import decision_package as dp
    base, scenario = _numbers()
    #: ⚠️ 실제 `ontology_path.trace()` 모양 — 두 식별자를 **둘 다 내지 않는다.**
    pkg = dp.build(title="고정 경로", owner="o@afs.invalid", due="2026-09-01",
                   base=base, scenario=scenario,
                   path={"path": [], "missing_evidence": ["purchase_orders"],
                         "complete": True, "calculation_blocked": False})
    assert pkg.evidence["query_id"] == "" and pkg.evidence["path_fingerprint"] == ""
    #: ★ 그리고 **빠진 근거는 드러난다** — 이것이 고정 경로를 막지 않는 이유다.
    assert pkg.evidence["missing_evidence"] == ["purchase_orders"]


def test_경로_없는_기존_흐름은_그대로_돈다():
    """⚠️ 경로를 쓰지 않는 기존 호출부를 막으면 이 통제가 기능 정지가 된다."""
    from core import decision_package as dp
    base, scenario = _numbers()
    pkg = dp.build(title="기존", owner="o@afs.invalid", due="2026-09-01",
                   base=base, scenario=scenario)
    assert pkg.evidence["query_id"] == "" and pkg.evidence["path_fingerprint"] == ""
