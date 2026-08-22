"""★★★ 런타임 경로 → **G5 결정 패키지의 근거.** (§7 B1 · rev.2 2026-08-21)

## 이것이 하는 일과 하지 않는 일

    한다      런타임 **응답 봉투**에서 경로 하나를 골라 `decision_package.build(path=…)`
              가 읽는 모양으로 옮긴다
              질의 정체성(`query_id`·`path_fingerprint`)을 함께 싣는다
              계산이 없으면 **막혔다는 사실**을 이름으로 말한다

    안 한다   수치 계산 · 고정 경로와의 혼합이나 fallback · 부분 수치 · 권한 판정

## ⚠️⚠️ 질의와 경로를 따로 받지 않는다 (rev.2)

첫 판은 `to_evidence(query, path)` 였다. 그러면 호출부가 **서로 다른 실행에서 나온
둘을 섞을 수 있다**:

    3월 질의(as_of=3월) + 6월 경로(6월 판에 결속된 bindings)

둘 다 개별적으로는 멀쩡하다. 경로 지문은 판에 흔들리지 않게 만들었으므로(A rev.2 §3.6)
**모양으로는 구별되지 않는다.** 그래서 이제 **봉투 전체를 받고 그 안에서 고른다.**

## ⚠️⚠️ 고정 경로로 되돌아가지 않는다

`core/ontology_path.py` 는 **칸 이름이 박힌** 경로다. 런타임 경로를 못 만들었을 때
그쪽으로 흘리면 화면은 승인·범위·판을 하나도 확인하지 않은 그림을 「영향 경로」로
보여 준다 — 그리고 **평소와 똑같이 생겼다.**

## ⚠️ 차단 사유는 두 층이다 (A rev.2 §2.1)

    대외(브리핑·결정 패키지)   「이 경로는 아직 계산할 수 없습니다」 — 구간 정보 없음
    내부(권한 있는 진단)       구간 이름과 §5a 의 차단 사유 그대로

LLM 0콜.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from core import calc_capability
from core.data_preparation import scope_index

#: ★ 사람이 읽는 이름. **닫힌 표다.** 열쇠는 `(namespace, object_type)`.
#:
#: ⚠️ 계약키(`LOG-02`)나 기계 이름(`inventory-snapshot`)을 경영진 화면에 그대로
#:   내보내면 읽는 사람은 그것이 무엇인지 모른 채 「모르는 게 있구나」로만 넘긴다.
#: ⚠️ 여기 없는 유형은 **지어내지 않는다** — 기계 이름을 그대로 두고 그 사실이 보이게 한다.
LABELS: Dict[Tuple[str, str], str] = {
    ("dataset", "purchase-order-line"): "구매주문 라인",
    ("dataset", "shipment"): "선적",
    ("dataset", "inventory-snapshot"): "재고 스냅샷",
    ("dataset", "production-plan-line"): "생산계획 라인",
    ("dataset", "sales-line"): "판매 라인",
}

#: `(namespace, object_type)` → 계약키.
#:
#: ★ 범위 색인의 표를 **뒤집어 쓴다** — 두 벌로 두면 갈라진다.
#: ⚠️⚠️ [2026-08-21 B1.1-4] `namespace` 를 버리면 안 된다. 다른 namespace 의 같은
#:   유형 이름이 **같은 계약키로 접힌다** — 계약이 닫혀 있는 지금은 우연히 맞지만,
#:   `mdm:material` 같은 것이 열리는 순간 조용히 틀린다.
_DATASET_BY_TYPE: Dict[Tuple[str, str], str] = {
    (ns, object_type): key
    for key, (ns, object_type, _col) in scope_index.CONTRACT_OBJECTS.items()}

#: ★★★ **정량 관계**는 계산 없이 설 수 없다(계약 `relation_types[].quantitative`).
#: ⚠️ 계약에서 정량인 것은 `AFFECTS` 하나다. 그런데 `calculation_ref` 없이 들어오면
#:   종전 판은 «정성 관계» 로 보고 **통과시켰다** — 계산이 필요한 자리인데 필요 없는
#:   자리로 오해한 것이다.
QUANTITATIVE_RELATIONS = frozenset({"AFFECTS"})

#: 대외 문구. ⚠️ 구간 수·이름을 담지 않는다.
PUBLIC_BLOCKED = "이 경로는 아직 계산할 수 없습니다."


class PathAdapterError(Exception):
    """경로를 근거로 옮기지 못했다. ⚠️ 사유가 붙는다."""


class PathIntegrityError(Exception):
    """경로 자체가 계약과 어긋난다. ⚠️ **차단이 아니라 장애**다(503)."""


def _label(namespace: str, object_type: str) -> str:
    return LABELS.get((namespace, object_type), object_type)


def _segments(edges: List[dict],
              ledger_verifier: Optional[Callable[[Any], bool]] = None) -> List[dict]:
    """구간마다 «계산이 실행 가능한가».

    ★ 판정은 §5a 가 한다 — 여기서 다시 판단하면 규칙이 두 곳으로 갈라진다.

    ⚠️⚠️ [B1.1 P1] `cap.executable` 만 읽으면 안 된다. 그것은 등록부의 «그때 그랬다»
      이고, **철회는 등록부를 고치지 않는다.** 그래서 §5a 의 `assert_executable()` 을
      통과시킨다 — 그 안에 원장 재검증이 들어 있다.
    ★ 검증기가 없으면 실행 가능으로 **표시하지 않는다.** 지금은 아무것도 `APPROVED`
      가 아니라 결과가 같지만, 승인이 생긴 뒤에 넣으면 **그 사이가 열린다.**"""
    out = []
    for edge in edges or []:
        ref = str(edge.get("calculation_ref", "") or "").strip()
        relation_type = str(edge.get("relation_type_id", "") or "")
        item = {"relation_id": str(edge.get("relation_id", "")),
                "relation_type_id": relation_type,
                "calculation_ref": ref, "executable": False, "reason": ""}
        if not ref:
            if relation_type in QUANTITATIVE_RELATIONS:
                #: ⚠️⚠️ 정량 관계인데 계산이 안 붙어 있다 — **계약 위반**이다.
                #:   「계산이 없으니 정성 관계겠지」로 넘기면 그 관계는 숫자 없이 서고,
                #:   화면은 그 자리를 «영향 없음» 으로 그린다.
                raise PathIntegrityError(
                    f"정량 관계 «{relation_type}» 에 계산 참조가 없습니다.")
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
        item["state"] = cap.state
        try:
            calc_capability.assert_executable(ref, ledger_verifier)
            item["executable"] = True
        except calc_capability.CapabilityError as exc:
            item["executable"] = False
            item["reason"] = cap.blocked_reason or str(exc)
        out.append(item)
    return out


def _select(response: Dict[str, Any], path_fingerprint: str = "",
            index: Optional[int] = None) -> Dict[str, Any]:
    """봉투에서 경로 하나를 고른다. **봉투 밖의 경로는 받지 않는다.**"""
    paths = list(response.get("paths") or [])
    if not paths:
        raise PathAdapterError("응답에 경로가 없습니다.")
    if path_fingerprint:
        picked = [p for p in paths
                  if str(p.get("path_fingerprint", "")).strip() == path_fingerprint.strip()]
        if not picked:
            #: ⚠️ 「이 봉투에 없는 경로」를 조용히 무시하지 않는다 — 다른 실행의 경로를
            #:   붙이려는 시도이거나, 봉투가 바뀐 것이다. 둘 다 사람이 알아야 한다.
            raise PathAdapterError("이 응답에 없는 경로 지문입니다.")
        if len(picked) > 1:                       # pragma: no cover - 지문 충돌
            raise PathAdapterError("같은 지문의 경로가 둘 이상입니다.")
        return picked[0]
    if index is None:
        if len(paths) > 1:
            #: ★ 여럿일 때 **아무거나 고르지 않는다.** 고르면 실행마다 답이 달라진다.
            raise PathAdapterError(
                "경로가 여럿입니다 — path_fingerprint 로 하나를 고르십시오.")
        return paths[0]
    if not 0 <= index < len(paths):
        raise PathAdapterError("경로 번호가 범위를 벗어났습니다.")
    return paths[index]


def to_evidence(response: Dict[str, Any], *, path_fingerprint: str = "",
                index: Optional[int] = None,
                ledger_verifier: Optional[Callable[[Any], bool]] = None
                ) -> Dict[str, Any]:
    """런타임 **응답 봉투** → `decision_package.build(path=…)` 가 읽는 모양.

    ★★★ 반환에 **`query_id`·`path_fingerprint` 가 들어간다.** 그것이 없으면 「이 안건은
      어느 질의의 어느 경로에서 나왔는가」에 답할 수 없다 — 결과 지문은 **계산**을
      재현하지만 **경로**를 재현하지 않는다.

    ⚠️⚠️ [rev.2] 질의와 경로를 **따로 받지 않는다.** 따로 받으면 3월 질의에 6월 경로를
      붙일 수 있고, 경로 지문은 판에 흔들리지 않으므로 모양으로 구별되지 않는다.

    ⚠️⚠️ 계산이 하나라도 막히면 `complete=False` 이고 **수치를 싣지 않는다.**"""
    if not isinstance(response, dict):
        raise PathAdapterError("런타임 응답이 없습니다.")
    #: ⚠️ `.strip()` 이 있어야 한다 — 공백만 있는 값은 **정체성이 아니다.** 그런데
    #:   문자열로는 «있는» 것처럼 보여서, 없는 정체성이 조용히 통과한다.
    query_id = str(response.get("query_id", "") or "").strip()
    if not query_id:
        raise PathAdapterError("응답에 query_id 가 없습니다.")

    path = _select(response, path_fingerprint, index)
    fingerprint = str(path.get("path_fingerprint", "") or "").strip()
    if not fingerprint:
        raise PathAdapterError("경로에 지문이 없습니다.")

    nodes = list(path.get("nodes") or [])
    if not nodes:
        raise PathAdapterError("경로에 노드가 없습니다.")
    bindings = dict(path.get("bindings") or {})

    steps: List[Dict[str, Any]] = []
    missing: List[str] = []
    used: List[Dict[str, str]] = []
    for node in nodes:
        namespace = str(node.get("namespace", ""))
        object_type = str(node.get("object_type", ""))
        key = ":".join((namespace, object_type, str(node.get("object_id", ""))))
        dataset_key = _DATASET_BY_TYPE.get((namespace, object_type), "")
        snapshot_id = str(bindings.get(key, "") or "")
        if dataset_key and not snapshot_id:
            #: ★ 근거를 못 찾은 칸을 조용히 빼지 않는다 — 빼면 「전부 근거가 있다」로
            #:   보이고, 그것이 곧 근거 없는 계보다.
            missing.append(dataset_key)
        if dataset_key and snapshot_id:
            #: ⚠️⚠️ [B1.1-3] **객체별로 보존한다.** 계약키를 열쇠로 한 딕셔너리에 담으면
            #:   같은 유형이 경로에 두 번 나올 때 **앞 판이 조용히 사라진다.**
            used.append({"key": key, "dataset_key": dataset_key,
                         "snapshot_id": snapshot_id})
        steps.append({"key": key, "label": _label(namespace, object_type),
                      "dataset_key": dataset_key, "snapshot_id": snapshot_id})

    segments = _segments(list(path.get("edges") or []), ledger_verifier)
    blocked = [s for s in segments if not s["executable"]]

    return {
        "path": steps,
        "query_id": query_id,
        "path_fingerprint": fingerprint,
        "as_of": str(response.get("as_of", "") or ""),
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
        "used_snapshots": used,
    }


def relation_bindings(response: Dict[str, Any], *, path_fingerprint: str = "",
                      index: Optional[int] = None) -> Dict[str, str]:
    """[B2] 경로의 `{관계 id: 승인 당시 원장 사건}`.

    ★★★ 온톨로지는 관계를 승인할 때 **사건 하나를 그 관계에 묶는다**
      (`ledger_correlation_id`). 계산기가 대조할 것은 그것뿐이다 — 관계 id 로 원장을
      뒤지면 「그 관계를 언급하는 아무 살아 있는 승인」이 근거가 된다.

    ⚠️⚠️ **`to_evidence()` 에 싣지 않는다.** 근거는 안건에 봉인되고 화면에 나간다.
      대외 근거에 구간 목록을 담지 않는 것이 규약이고(`blocked_reason` 이 숫자·이름을
      감추는 것과 같은 이유), 그 규약은 회귀가 지킨다. 그래서 **별도 접근자**다 —
      서버 안에서만 쓰인다.

    ⚠️ 승인 사건이 비어 있는 관계도 **키로 남긴다.** 빼면 「경로의 모든 관계가
      승인됐는가」 검사의 요구 집합이 함께 줄어 검사가 통과해 버린다."""
    path = _select(response, path_fingerprint, index)
    out: Dict[str, str] = {}
    for edge in list(path.get("edges") or []):
        rid = str(edge.get("relation_id", "") or "").strip()
        if rid:
            out[rid] = str(edge.get("ledger_correlation_id", "") or "").strip()
    return out


def internal_diagnosis(response: Dict[str, Any], *, authorize: Callable[[], bool],
                       path_fingerprint: str = "", index: Optional[int] = None,
                       ledger_verifier: Optional[Callable[[Any], bool]] = None
                       ) -> Dict[str, Any]:
    """구간 이름과 사유를 그대로 주는 **내부 진단.**

    ★★★ [B1.1-7] `authorize()` 가 참을 돌려줘야 한다. **주석으로 「권한 있는 사람에게만」
      이라고 적는 것은 통제가 아니다** — 첫 판이 그랬다.
    ⚠️⚠️ 이 값을 경영 브리핑·결정 패키지에 실으면 안 된다. **구간 수 자체가 정보다.**
    ⚠️ 검사기가 없으면 거부한다 — 「안 넘겼으니 통과」는 문을 통째로 여는 것이다."""
    if authorize is None:
        raise PathAdapterError("진단 권한을 확인할 방법 없이 열지 않습니다.")
    try:
        allowed = bool(authorize())
    except Exception as exc:
        raise PathAdapterError(f"진단 권한을 확인하지 못했습니다: {exc}") from exc
    if not allowed:
        raise PathAdapterError("이 진단을 볼 권한이 없습니다.")

    evidence = to_evidence(response, path_fingerprint=path_fingerprint, index=index,
                           ledger_verifier=ledger_verifier)
    path = _select(response, path_fingerprint or evidence["path_fingerprint"], index)
    return {"query_id": evidence["query_id"],
            "path_fingerprint": evidence["path_fingerprint"],
            "segments": _segments(list(path.get("edges") or []), ledger_verifier),
            "missing_steps": evidence["missing_steps"]}
