"""[G2 / Wave G] 최소 온톨로지 — **첫 수직 경로 하나만.**

```text
원료 → 구매주문 → 선적·통관 → 입고·재고 → 생산계획 → 제품 → 현금·손익
외부환경 지표 ────────────────────────────────────┘
```

## 이 파일이 «하지 않는» 것

★★★ **Snapshot 본문을 복제하지 않는다.** 관계표에는 **식별자와 근거만** 둔다.
  ⚠️ 본문을 복제하면 그 사본이 원천과 갈라지고, 갈라진 사실은 아무도 모른다.
  그때 두 숫자 중 어느 쪽이 맞는지 답할 방법이 없다.

★★★ **수치를 계산하지 않는다.** 그것은 G4 의 일이다(설계 §12.1).
  ⚠️ 여기서 합계를 내기 시작하면 계산이 두 곳에 생기고, 두 곳은 반드시 갈라진다.

## 무엇을 답하는가

「이 숫자가 어디서 왔고, 무엇에 영향을 주는가」 — **경로**다.
그 경로의 각 칸은 «어느 데이터에서 오는가»(Dataset 계약키)를 들고 있으므로,
Baseline 의 Snapshot 집합과 이어 붙이면 **계보**가 된다.
"""
from typing import Any, Dict, List, NamedTuple, Optional, Tuple


class OntologyError(Exception):
    """경로를 답할 수 없다."""


class Node(NamedTuple):
    key: str
    label: str
    #: 이 칸이 어느 업무 데이터에서 오는가. 빈 값이면 **파생 칸**(계산으로만 생긴다).
    dataset_key: str = ""


#: ★★★ **첫 수직 경로 하나.** 늘리지 않는다 — 설계서가 「첫 경로만 구현/사용한다」고
#:   못 박았다. 여기에 칸을 더하면 그 칸을 채울 데이터가 없는 채로 화면이 늘어난다.
CHAIN: Tuple[Node, ...] = (
    Node("material", "원료", "materials"),
    Node("purchase_order", "구매주문", "purchase_orders"),
    Node("shipment", "선적·통관", "shipments"),
    Node("arrival", "입고·재고", "material_arrivals"),
    Node("production_plan", "생산계획", "production_plans"),
    Node("product", "제품", "products"),
    Node("cash_pl", "현금·손익", "financials"),
)

#: 외부환경 지표는 **사슬 밖에서** 현금·손익으로 들어온다(환율·원자재가 등).
EXTERNAL = Node("external_indicator", "외부환경 지표", "external_indicators")
EXTERNAL_TARGET = "cash_pl"

_BY_KEY: Dict[str, Node] = {n.key: n for n in CHAIN}
_BY_KEY[EXTERNAL.key] = EXTERNAL


def node(key: Any) -> Node:
    """칸 하나. **모르는 이름은 던진다** — 조용히 빈 칸을 만들지 않는다."""
    k = str(key or "").strip()
    if k not in _BY_KEY:
        raise OntologyError(
            f"이 경로에 없는 칸입니다: {k or '(없음)'} — "
            f"가능한 것은 {[n.key for n in CHAIN] + [EXTERNAL.key]} 입니다.")
    return _BY_KEY[k]


def downstream(key: Any) -> List[Node]:
    """이 칸이 **영향을 주는** 칸들(자기 뒤 전부).

    ★ 외부지표는 현금·손익 하나에만 들어간다 — 사슬의 일부가 아니다."""
    n = node(key)
    if n.key == EXTERNAL.key:
        return [_BY_KEY[EXTERNAL_TARGET]]
    idx = [x.key for x in CHAIN].index(n.key)
    return list(CHAIN[idx + 1:])


def upstream(key: Any) -> List[Node]:
    """이 칸이 **영향을 받는** 칸들(자기 앞 전부 + 해당하면 외부지표)."""
    n = node(key)
    if n.key == EXTERNAL.key:
        return []
    idx = [x.key for x in CHAIN].index(n.key)
    out = list(CHAIN[:idx])
    if n.key == EXTERNAL_TARGET:
        out.append(EXTERNAL)
    return out


def impact_path(start: Any, end: Any) -> List[Node]:
    """두 칸 사이의 경로. **뒤에서 앞으로는 가지 않는다.**

    ⚠️ 역방향을 허용하면 「입고가 구매주문에 영향을 준다」 같은 답이 나오고, 그것은
      이 도메인에서 틀린 말이다."""
    a, b = node(start), node(end)
    if a.key == EXTERNAL.key:
        if b.key != EXTERNAL_TARGET:
            raise OntologyError(
                f"외부환경 지표는 «{_BY_KEY[EXTERNAL_TARGET].label}» 에만 들어갑니다.")
        return [a, b]
    keys = [x.key for x in CHAIN]
    if b.key == EXTERNAL.key:
        raise OntologyError("외부환경 지표는 사슬의 끝이 아닙니다.")
    i, j = keys.index(a.key), keys.index(b.key)
    if i > j:
        raise OntologyError(
            f"«{a.label}» 은 «{b.label}» 보다 뒤에 있습니다 — 이 경로는 한 방향입니다.")
    return list(CHAIN[i:j + 1])


def required_datasets(path: List[Node]) -> List[str]:
    """이 경로를 답하려면 어떤 업무 데이터가 필요한가. **정렬해 돌려준다.**"""
    return sorted({n.dataset_key for n in (path or []) if n.dataset_key})


def trace(start: Any, end: Any, *, baseline: Any = None,
          snapshot_index: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """경로 + **그 경로가 어느 판을 근거로 하는가.**

    ★★★ Snapshot 본문을 복제하지 않는다 — **식별자만** 싣는다.
    ⚠️ 근거를 못 찾은 칸을 조용히 빼지 않는다. 빼면 「전부 근거가 있다」로 보이고,
      그것이 곧 근거 없는 계보다."""
    path = impact_path(start, end)
    index = dict(snapshot_index or {})
    steps: List[Dict[str, Any]] = []
    missing: List[str] = []
    for n in path:
        sid = index.get(n.dataset_key, "") if n.dataset_key else ""
        if n.dataset_key and not sid:
            missing.append(n.dataset_key)
        steps.append({"key": n.key, "label": n.label,
                      "dataset_key": n.dataset_key, "snapshot_id": sid})
    return {
        "path": steps,
        "required_datasets": required_datasets(path),
        #: ★ 근거가 빠진 칸을 **드러낸다** — 화면이 「이 경로는 아직 다 설명되지
        #:   않는다」를 말할 수 있어야 한다.
        "missing_evidence": sorted(set(missing)),
        #: ★★★ 사람이 읽는 이름으로도 준다. 계약키(`purchase_orders`)를 그대로
        #:   경영진 화면에 내보내면 §12 위반이고, 무엇이 빠졌는지도 안 읽힌다.
        "missing_steps": [{"key": st["key"], "label": st["label"],
                           "dataset_key": st["dataset_key"]}
                          for st in steps
                          if st["dataset_key"] and not st["snapshot_id"]],
        #: ★★★ **「근거를 확인했다」와 「아직 안 봤다」는 다르다.**
        #:   기준선 없이 부르면 모든 칸이 「근거 없음」으로 보이는데, 그것을 그대로
        #:   경고로 그리면 화면은 아직 고르지도 않은 사용자에게 「근거가 없다」고
        #:   말한다 — 그리고 같은 화면 아래의 안건은 그 판을 근거로 쓴다.
        #:   한 화면에 서로 다른 두 답이 뜨는 것이 이 갈래의 이유다.
        "evidence_checked": snapshot_index is not None,
        "complete": not missing,
        "baseline_fingerprint": str(getattr(baseline, "fingerprint", "") or ""),
        "data_kind": str(getattr(baseline, "data_kind", "") or ""),
    }
