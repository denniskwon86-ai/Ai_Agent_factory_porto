"""★★★ 런타임 경로 → **G5 결정 패키지의 근거.** (§7 B1 · 2026-08-21)

## 이것이 하는 일과 하지 않는 일

    한다      런타임이 낸 경로를 `decision_package.build(path=…)` 가 읽는 모양으로 옮긴다
              질의 정체성(`query_id`·`path_fingerprint`)을 함께 싣는다
              계산이 없으면 **막혔다는 사실**을 이름으로 말한다

    안 한다   수치 계산 · 고정 경로와의 혼합이나 fallback · 부분 수치

## ⚠️⚠️ 고정 경로로 되돌아가지 않는다

`core/ontology_path.py` 는 **칸 이름이 박힌** 경로다(원료 → 구매 → … ). 런타임 경로를
못 만들었을 때 그쪽으로 흘리면, 화면은 승인·범위·판을 하나도 확인하지 않은 그림을
「영향 경로」로 보여 준다. 그리고 그것은 **평소와 똑같이 생겼다.**

★ 그래서 이 모듈은 고정 경로를 **부르지도, 알지도 못한다.** 시험이 구문 나무로 확인한다.

## ⚠️ 차단 사유는 두 층이다 (A rev.2 §2.1)

    대외(브리핑·결정 패키지)   「이 경로는 아직 계산할 수 없습니다」 — 구간 정보 없음
    내부(권한 있는 진단)       구간 이름과 §5a 의 차단 사유 그대로

「구간 3개 중 2개가 막혔습니다」는 **구간이 3개 있다는 사실**을 알려 준다. 권한이 없는
사람에게 그것은 이미 정보다.

LLM 0콜.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core import calc_capability
from core.data_preparation import scope_index

#: ★ 사람이 읽는 이름. **닫힌 표다.**
#:
#: ⚠️ 계약키(`LOG-02`)나 기계 이름(`inventory-snapshot`)을 경영진 화면에 그대로
#:   내보내면 읽는 사람은 그것이 무엇인지 모른 채 「모르는 게 있구나」로만 넘긴다.
#: ⚠️ 여기 없는 유형은 **지어내지 않는다** — 기계 이름을 그대로 두고 그 사실이 보이게 한다.
LABELS: Dict[str, str] = {
    "purchase-order-line": "구매주문 라인",
    "shipment": "선적",
    "inventory-snapshot": "재고 스냅샷",
    "production-plan-line": "생산계획 라인",
    "sales-line": "판매 라인",
}

#: 객체 유형 → 계약키. ★ 범위 색인의 표를 **뒤집어 쓴다** — 두 벌로 두면 갈라진다.
_DATASET_BY_TYPE: Dict[str, str] = {
    object_type: key for key, (_ns, object_type, _col) in
    scope_index.CONTRACT_OBJECTS.items()}

#: 대외 문구. ⚠️ 구간 수·이름을 담지 않는다.
PUBLIC_BLOCKED = "이 경로는 아직 계산할 수 없습니다."


class PathAdapterError(Exception):
    """경로를 근거로 옮기지 못했다. ⚠️ 사유가 붙는다."""


def _label(object_type: str) -> str:
    return LABELS.get(object_type, object_type)


def _segments(edges: List[dict]) -> List[dict]:
    """구간마다 «계산이 실행 가능한가».

    ★ 판정은 §5a 가 한다 — 여기서 다시 판단하면 규칙이 두 곳으로 갈라진다."""
    out = []
    for edge in edges or []:
        ref = str(edge.get("calculation_ref", "") or "").strip()
        item = {"relation_id": str(edge.get("relation_id", "")),
                "relation_type_id": str(edge.get("relation_type_id", "")),
                "calculation_ref": ref, "executable": False, "reason": ""}
        if not ref:
            #: ★ 정성 관계는 계산이 없다 — 그것은 «막힘» 이 아니다.
            item["executable"] = True
            out.append(item)
            continue
        try:
            cap = calc_capability.get(ref)
        except calc_capability.CapabilityError as exc:
            #: ⚠️ 계약에 없는 참조가 관계에 붙어 있다 — 조용히 넘기지 않는다.
            item["reason"] = str(exc)
            out.append(item)
            continue
        item["executable"] = cap.executable
        item["reason"] = "" if cap.executable else cap.blocked_reason
        item["state"] = cap.state
        out.append(item)
    return out


def to_evidence(query: Dict[str, Any], path: Dict[str, Any]) -> Dict[str, Any]:
    """런타임 경로 하나 → `decision_package.build(path=…)` 가 읽는 모양.

    ★★★ 반환에 **`query_id`·`path_fingerprint` 가 들어간다.** 그것이 없으면 「이 안건은
      어느 질의의 어느 경로에서 나왔는가」에 답할 수 없다 — 결과 지문은 **계산**을
      재현하지만 **경로**를 재현하지 않는다.

    ⚠️⚠️ 계산이 하나라도 막히면 `complete=False` 이고 **수치를 싣지 않는다.** 부분 수치를
      실으면 화면에 숫자가 뜨고, 사람은 그것을 답으로 읽는다(A rev.2 §2)."""
    if not isinstance(query, dict) or not isinstance(path, dict):
        raise PathAdapterError("경로 또는 질의가 없습니다.")
    #: ⚠️ `.strip()` 이 있어야 한다 — 공백만 있는 값은 **정체성이 아니다.** 그런데
    #:   문자열로는 «있는» 것처럼 보여서, 없는 정체성이 조용히 통과한다.
    query_id = str(query.get("query_id", "") or "").strip()
    fingerprint = str(path.get("path_fingerprint", "") or "").strip()
    if not query_id or not fingerprint:
        #: ⚠️ 정체성 없는 경로를 근거로 쓰지 않는다 — 나중에 되짚을 수 없다.
        raise PathAdapterError("경로에 질의 정체성이 없습니다(query_id·path_fingerprint).")

    nodes = list(path.get("nodes") or [])
    if not nodes:
        raise PathAdapterError("경로에 노드가 없습니다.")
    bindings = dict(path.get("bindings") or {})

    steps: List[Dict[str, Any]] = []
    missing: List[str] = []
    for node in nodes:
        object_type = str(node.get("object_type", ""))
        key = ":".join((str(node.get("namespace", "")), object_type,
                        str(node.get("object_id", ""))))
        dataset_key = _DATASET_BY_TYPE.get(object_type, "")
        snapshot_id = str(bindings.get(key, "") or "")
        if dataset_key and not snapshot_id:
            #: ★ 근거를 못 찾은 칸을 조용히 빼지 않는다 — 빼면 「전부 근거가 있다」로
            #:   보이고, 그것이 곧 근거 없는 계보다.
            missing.append(dataset_key)
        steps.append({"key": key, "label": _label(object_type),
                      "dataset_key": dataset_key, "snapshot_id": snapshot_id})

    segments = _segments(list(path.get("edges") or []))
    blocked = [s for s in segments if not s["executable"]]

    return {
        "path": steps,
        "query_id": query_id,
        "path_fingerprint": fingerprint,
        "as_of": str(query.get("as_of", "") or ""),
        "required_datasets": sorted({s["dataset_key"] for s in steps if s["dataset_key"]}),
        "missing_evidence": sorted(set(missing)),
        #: ★★★ 사람이 읽는 이름으로도 준다(설계 §12).
        "missing_steps": [{"key": s["key"], "label": s["label"],
                           "dataset_key": s["dataset_key"]}
                          for s in steps if s["dataset_key"] and not s["snapshot_id"]],
        #: ⚠️⚠️ 계산이 막히면 근거가 다 있어도 **완결이 아니다.**
        "complete": not missing and not blocked,
        "calculation_blocked": bool(blocked),
        #: 대외 문구 — 구간 수·이름을 담지 않는다.
        "blocked_reason": PUBLIC_BLOCKED if blocked else "",
        "used_snapshots": {s["dataset_key"]: s["snapshot_id"] for s in steps
                           if s["dataset_key"] and s["snapshot_id"]},
    }


def internal_diagnosis(query: Dict[str, Any], path: Dict[str, Any]) -> Dict[str, Any]:
    """**권한 있는 사람에게만** 보이는 진단. 구간 이름과 사유를 그대로 준다.

    ⚠️⚠️ 이 값을 경영 브리핑·결정 패키지에 실으면 안 된다. 구간 수 자체가 정보다."""
    evidence = to_evidence(query, path)
    return {"query_id": evidence["query_id"],
            "path_fingerprint": evidence["path_fingerprint"],
            "segments": _segments(list(path.get("edges") or [])),
            "missing_steps": evidence["missing_steps"]}
