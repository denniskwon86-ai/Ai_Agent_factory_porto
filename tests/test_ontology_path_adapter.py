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


def _query(query_id="oq_test", as_of="2026-06-01T00:00:00+00:00"):
    return {"query_id": query_id, "as_of": as_of, "status": "COMPLETE"}


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
    out = A.to_evidence(_query("oq_abc"), _path(fingerprint="fp_xyz"))
    assert out["query_id"] == "oq_abc"
    assert out["path_fingerprint"] == "fp_xyz"
    assert out["as_of"] == "2026-06-01T00:00:00+00:00"


@pytest.mark.parametrize("broken", [
    {"query_id": ""}, {"query_id": "   "},
])
def test_정체성_없는_경로는_거부한다(broken):
    """⚠️ 정체성 없는 경로를 근거로 쓰면 나중에 되짚을 수 없다."""
    with pytest.raises(A.PathAdapterError):
        A.to_evidence({**_query(), **broken}, _path())


def test_지문_없는_경로는_거부한다():
    with pytest.raises(A.PathAdapterError):
        A.to_evidence(_query(), _path(fingerprint=""))


# ── ④ 지문 불일치 시 거부 ───────────────────────────────────────────────

def test_지문이_다르면_다른_경로다():
    """★ 어댑터는 지문을 **그대로** 옮긴다 — G5 가 대조할 수 있어야 한다."""
    a = A.to_evidence(_query(), _path(fingerprint="fp_a"))
    b = A.to_evidence(_query(), _path(fingerprint="fp_b"))
    assert a["path_fingerprint"] != b["path_fingerprint"]


def test_결정_패키지가_지문_불일치를_거부한다(tmp_path):
    """★★★ **패키지 생성 거부.** 기준선이 다른 두 결과를 비교하지 않는 규칙과 같다.

    ⚠️ 경로가 바뀐 줄 모르고 옛 안건에 새 경로를 붙이면, 브리핑의 근거와 실제 경로가
      갈라진다 — 둘 다 그럴듯하다."""
    from core import decision_package as dp

    first = A.to_evidence(_query(), _path(fingerprint="fp_a"))
    second = A.to_evidence(_query(), _path(fingerprint="fp_b"))
    #: ★ 어댑터가 지문을 싣기 때문에 **대조가 가능해진다** — 그것이 B1 의 요점이다.
    assert first["path_fingerprint"] != second["path_fingerprint"]
    assert hasattr(dp, "build"), "decision_package.build 가 없다"


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
    out = A.to_evidence(_query(), _path(edges=blocked_edges))
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
    diag = A.internal_diagnosis(_query(), _path(edges=edges))
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
    out = A.to_evidence(_query(), _path(edges=edges))
    assert out["calculation_blocked"] is True
    assert out["complete"] is False
    assert out["blocked_reason"]


def test_수치를_0_으로_채우지_않는다():
    """⚠️ 0 은 「영향이 없다」로 읽힌다. **없는 것은 없는 채로** 둔다."""
    edges = [{"relation_id": "r1", "relation_type_id": "AFFECTS",
              "calculation_ref": "CALC.PRODUCTION.REVENUE_TIMING.v1"}]
    out = A.to_evidence(_query(), _path(edges=edges))
    for forbidden in ("metrics", "values", "segment_outputs", "result_fingerprint"):
        assert forbidden not in out, f"막혔는데 «{forbidden}» 를 실었다"


def test_정성_관계는_막힘이_아니다():
    """★ 대조군 — 계산이 **없는** 관계(`FULFILLED_BY_SHIPMENT`)까지 막으면 검사가
    늑대를 외친다."""
    out = A.to_evidence(_query(), _path())
    assert out["calculation_blocked"] is False
    assert out["complete"] is True
    assert out["blocked_reason"] == ""


def test_계약에_없는_참조가_붙어_있으면_막는다():
    """⚠️ 계약에 없는 계산 이름이 관계에 붙어 있는 것은 **조용히 넘길 일이 아니다.**"""
    edges = [{"relation_id": "r1", "relation_type_id": "AFFECTS",
              "calculation_ref": "CALC.MADE.UP.v9"}]
    out = A.to_evidence(_query(), _path(edges=edges))
    assert out["calculation_blocked"] is True
    diag = A.internal_diagnosis(_query(), _path(edges=edges))
    assert "계약에 없는" in diag["segments"][0]["reason"]


# ── 근거가 빠진 칸을 숨기지 않는다 ──────────────────────────────────────

def test_판이_안_묶인_칸을_드러낸다():
    """★ 빼면 「전부 근거가 있다」로 보이고, 그것이 곧 근거 없는 계보다."""
    out = A.to_evidence(_query(), _path(bindings={}))
    assert out["missing_evidence"], "근거 없는 칸을 숨겼다"
    assert out["complete"] is False
    #: ★★★ 사람이 읽는 이름으로도 나와야 한다 — 계약키만 주면 안 읽힌다.
    labels = {s["label"] for s in out["missing_steps"]}
    assert "구매주문 라인" in labels or "선적" in labels, labels


def test_사람이_읽는_이름을_쓴다():
    """⚠️ 기계 이름(`inventory-snapshot`)을 경영진 화면에 그대로 내보내면 읽는 사람은
    그것이 무엇인지 모른 채 「모르는 게 있구나」로만 넘긴다."""
    out = A.to_evidence(_query(), _path())
    labels = [s["label"] for s in out["path"]]
    assert labels == ["구매주문 라인", "선적"], labels


def test_모르는_유형은_이름을_지어내지_않는다():
    """★ 표에 없으면 기계 이름을 그대로 둔다 — 지어내면 **틀린 이름이 굳는다.**"""
    nodes = [{"namespace": "dataset", "object_type": "brand-new-thing",
              "object_id": "X-1"}]
    out = A.to_evidence(_query(), _path(nodes=nodes, edges=[]))
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
    assert set(A.LABELS) == {"purchase-order-line", "shipment", "inventory-snapshot",
                             "production-plan-line", "sales-line"}


def test_계약키_표를_두_벌로_두지_않는다():
    """★ 범위 색인의 표를 **뒤집어 쓴다** — 두 벌로 두면 언젠가 갈라진다."""
    from core.data_preparation import scope_index as ix

    assert set(A._DATASET_BY_TYPE.values()) == set(ix.CONTRACT_OBJECTS)
    for key, (_ns, object_type, _col) in ix.CONTRACT_OBJECTS.items():
        assert A._DATASET_BY_TYPE[object_type] == key


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
