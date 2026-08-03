"""[ECM E4] 조직 트리 집계 — **합치는 순간 거짓말이 되기 가장 쉬운 계산.**

## 두 가지 집계는 다른 것이다

| 관계 | 무엇을 합치는가 | 법인 경계 |
|---|---|---|
| `OPERATING_PARENT` | 실제로 업무·공정을 수행하는 단위의 **운영 집계** | **넘지 않는다** |
| `CONSOLIDATION_SCOPE` | 지분율(`weight`)을 적용한 **연결 집계** | 넘는다(그게 목적) |

⚠️ 둘을 한 함수로 뭉개면 "전사 합계"가 무엇을 더한 값인지 아무도 모른다. 운영 합계에 다른 법인이
  섞이면 그건 우리 실적이 아니고, 연결 합계에 지분율을 빼먹으면 100% 자회사가 아닌 곳의 매출이
  전액 우리 것이 된다.

## 이 모듈이 거부하는 세 가지

1. **이중 계상.** 부모가 자기 값을 갖고 자식도 값을 가지면 **더하지 않는다.** 그대로 더하면
   실제의 두 배가 되고, 오류는 나지 않으며 손익표는 그럴듯해 보인다
   (`planning_engine.rollup_conflicts` 가 같은 사고를 다룬다 — 우리 일은 고르는 것이 아니라
   **들키게 하는 것**이다).
2. **상태 혼합.** 확정 실적과 가상 계산값을 한 합계에 넣지 않는다(§8.1). 모드별로 따로 합친다.
3. **결손을 0 으로 채우기.** 값이 없는 자식을 0 으로 보면 합계가 **사실처럼** 보인다. 빠진 것을
   세어 함께 돌려준다 — 커버리지 없는 합계는 근거가 아니다.

LLM 0콜.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from core.enterprise_context.models import REL_CONSOLIDATION_SCOPE, REL_OPERATING_PARENT

#: 합계를 신뢰해도 되는 최소 커버리지(자식 중 값이 있는 비율). 이 아래면 경고를 붙인다.
#: ★ 임계값을 코드 한 곳에 둔다 — 화면마다 다른 기준을 쓰면 같은 합계가 어디선 정상, 어디선
#:   경고로 보인다.
COVERAGE_WARN_BELOW = 0.8


class RollupError(ValueError):
    """집계 불가 — 4xx 로 전달한다."""


class Rollup:
    def __init__(self, repository=None):
        self._repo_override = repository

    @property
    def _repo(self):
        if self._repo_override is not None:
            return self._repo_override
        from core.enterprise_context.repository import ecm_repository
        return ecm_repository

    # ── 트리 ──────────────────────────────────────────────────────────────
    def _descendants(self, node_id: str, relation: str) -> List[str]:
        out: List[str] = []
        seen: Set[str] = {node_id}
        frontier = [node_id]
        while frontier:
            nxt = []
            for nid in frontier:
                for ch in self._repo.children(nid, relation):
                    if ch in seen:
                        continue
                    seen.add(ch)
                    out.append(ch)
                    nxt.append(ch)
            frontier = nxt
        return out

    def _edge_weight(self, parent: str, child: str, relation: str) -> float:
        """부모→자식 지분율. 없으면 1.0.

        ⚠️ 연결 집계에서 지분율을 빼먹으면 100% 자회사가 아닌 곳의 매출이 전액 우리 것이 된다."""
        for e in self._repo.list_edges(relation_type=relation):
            if e.from_node_id == parent and e.to_node_id == child:
                try:
                    return float(e.weight if e.weight is not None else 1.0)
                except (TypeError, ValueError):
                    return 1.0
        return 1.0

    def _legal_entity_of(self, node_id: str) -> str:
        """이 노드를 **감싸는 법인** 노드의 entity_id.

        ★★ [2026-08-03 실측 결함] 처음에는 노드 자신의 `entity_id` 를 돌려줬다. 이 저장소의
          조직도는 **노드마다 엔터티가 1:1** 이므로(사업부도 공장도 각자 엔터티를 갖는다) 그러면
          부모와 자식이 항상 다른 값이 되어 **모든 운영 집계가 "법인 경계를 넘었다"** 는 오탐을
          냈다. 실서버에서 `MNM_BATTERY → BATT_PLANT_1/2` 집계에 경고가 붙어 발견했다.
        ⚠️ 오탐 경고는 진짜 경고를 묻는다 — 항상 뜨는 경고는 아무도 읽지 않게 되고, 그러면
          실제로 법인을 넘은 집계도 지나간다. 그래서 **위로 올라가 법인 노드를 찾는다.**
        `entity_type == "legal_entity"` 인 노드를 만나면 그 노드가 속한 법인이다. 못 찾으면
        빈 문자열 — 판정하지 않는다(모르면 경고하지 않는다, 오탐보다 침묵이 낫다)."""
        seen = {node_id}
        frontier = [node_id]
        while frontier:
            nxt = []
            for nid in frontier:
                n = self._repo.get_node(nid)
                if not n:
                    continue
                e = self._repo.get_entity(n.entity_id)
                if e and e.entity_type == "legal_entity":
                    return n.entity_id
                for pid in self._repo.parents(nid, REL_OPERATING_PARENT):
                    if pid not in seen:
                        seen.add(pid)
                        nxt.append(pid)
            frontier = nxt
        return ""

    # ── 집계 ──────────────────────────────────────────────────────────────
    def rollup(self, node_id: str, values_by_node: Dict[str, Dict[str, Any]],
               mode: str = "ACTUAL", relation: str = REL_OPERATING_PARENT,
               keys: Optional[List[str]] = None) -> Dict[str, Any]:
        """`node_id` 아래를 합친다. **무엇을 더했고 무엇이 빠졌는지 함께 돌려준다.**

        `values_by_node` 는 호출자가 준다(실적·계획·스냅샷·시나리오 결과 무엇이든) — 이 함수는
        **트리와 값만** 다루므로 출처가 달라도 규칙이 하나다.
        ⚠️ 서로 다른 상태(실제/가상)의 값을 한 번에 넘기면 안 된다. `mode` 는 그 호출이 어떤
          상태의 값을 다루는지 선언하는 자리이고, 결과에 그대로 붙어 나간다."""
        if relation not in (REL_OPERATING_PARENT, REL_CONSOLIDATION_SCOPE):
            raise RollupError(
                f"집계 관계는 {REL_OPERATING_PARENT} 또는 {REL_CONSOLIDATION_SCOPE} 여야 합니다: "
                f"{relation} — 다른 관계로 합치면 그 합계가 무엇인지 설명할 수 없습니다.")
        if not (node_id or "").strip():
            raise RollupError("node_id 는 필수입니다.")

        descendants = self._descendants(node_id, relation)
        own = dict(values_by_node.get(node_id) or {})
        child_nodes = [d for d in descendants if values_by_node.get(d)]
        all_keys = keys or sorted({k for n in [node_id] + descendants
                                   for k in (values_by_node.get(n) or {})})

        totals: Dict[str, Any] = {}
        conflicts: List[Dict[str, Any]] = []
        contributions: Dict[str, List[Dict[str, Any]]] = {}
        for k in all_keys:
            has_own = k in own and _num(own[k]) is not None
            kids = [(d, _num((values_by_node.get(d) or {}).get(k)))
                    for d in descendants if k in (values_by_node.get(d) or {})]
            kids = [(d, v) for d, v in kids if v is not None]

            if has_own and kids:
                # ★ 자동으로 한쪽을 버리지 않는다 — 어느 쪽이 정본인지는 넣은 사람만 안다.
                conflicts.append({
                    "key": k, "own_value": own[k],
                    "child_nodes": [d for d, _ in kids],
                    "child_sum": round(sum(v for _, v in kids), 6),
                    "why": ("부모에 직접 입력된 값과 자식 값이 함께 있습니다 — 그대로 더하면 "
                            "이중 계상입니다. 어느 쪽이 정본인지 확인하십시오."),
                })
                continue                     # 합계에 넣지 않는다(들키게 한다)
            if has_own:
                totals[k] = _num(own[k])
                contributions[k] = [{"node_id": node_id, "value": _num(own[k]), "weight": 1.0,
                                     "how": "직접 입력"}]
                continue
            if not kids:
                continue                     # 값이 없다 — 0 으로 채우지 않는다
            parts = []
            s = 0.0
            for d, v in kids:
                w = (self._edge_weight_path(node_id, d, relation)
                     if relation == REL_CONSOLIDATION_SCOPE else 1.0)
                s += v * w
                parts.append({"node_id": d, "value": v, "weight": w,
                              "how": "지분율 적용" if relation == REL_CONSOLIDATION_SCOPE
                                     else "운영 집계"})
            totals[k] = round(s, 6)
            contributions[k] = parts

        # 커버리지 — 자식 중 몇이 값을 냈는가. 없으면 합계를 신뢰할 수 없다.
        cov = (len(child_nodes) / len(descendants)) if descendants else 1.0
        out = {
            "node_id": node_id, "mode": mode, "relation": relation,
            "totals": totals, "conflicts": conflicts, "contributions": contributions,
            "coverage": {
                "descendants": len(descendants), "with_values": len(child_nodes),
                "ratio": round(cov, 4),
                "missing": sorted(set(descendants) - set(child_nodes)),
            },
            "notes": [],
        }
        if relation == REL_OPERATING_PARENT:
            crossed = self._crossed_legal_entities(node_id, [d for d, _ in
                                                             [(d, None) for d in child_nodes]])
            if crossed:
                out["notes"].append(
                    f"⚠️ 운영 집계가 법인 경계를 넘었습니다({sorted(crossed)}) — 운영 합계는 "
                    f"한 법인 안에서만 성립합니다. 연결 집계(CONSOLIDATION_SCOPE)를 쓰십시오.")
        if conflicts:
            out["notes"].append(
                f"⚠️ 이중 계상 위험 {len(conflicts)}건은 합계에서 **제외**했습니다 — 자동으로 "
                f"한쪽을 고르지 않습니다.")
        if descendants and cov < COVERAGE_WARN_BELOW:
            out["notes"].append(
                f"⚠️ 하위 조직 {len(descendants)}개 중 {len(child_nodes)}개만 값을 냈습니다"
                f"(커버리지 {out['coverage']['ratio']:.0%}) — 빠진 조직을 0 으로 보지 않았으므로 "
                f"이 합계는 **부분 합계**입니다.")
        return out

    def _edge_weight_path(self, ancestor: str, node: str, relation: str) -> float:
        """조상→노드 경로의 지분율 곱. 다단 자회사에서 지분이 희석되는 것을 반영한다.

        ⚠️ 한 단계만 보면 손자회사 지분이 100% 로 계산된다(A→B 60%, B→C 50% 인데 A→C 를
          100% 로 보는 것)."""
        # 부모 체인을 거꾸로 따라 올라가며 곱한다. 경로가 여러 개면 가장 큰 지분을 쓴다
        # (보수적으로 작은 쪽을 쓰면 합계가 실제보다 작아져 '문제 없음'처럼 보인다).
        best = 0.0
        stack = [(node, 1.0, {node})]
        while stack:
            cur, acc, seen = stack.pop()
            if cur == ancestor:
                best = max(best, acc)
                continue
            for p in self._repo.parents(cur, relation):
                if p in seen:
                    continue
                stack.append((p, acc * self._edge_weight(p, cur, relation), seen | {p}))
        return best if best else 1.0

    def _crossed_legal_entities(self, node_id: str, child_nodes: List[str]) -> Set[str]:
        base = self._legal_entity_of(node_id)
        if not base:
            return set()
        out = set()
        for d in child_nodes:
            le = self._legal_entity_of(d)
            if le and le != base:
                out.add(le)
        return out


def _num(v: Any) -> Optional[float]:
    """숫자로 볼 수 있으면 float. 문자열을 억지로 숫자로 만들지 않는다."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


rollup_service = Rollup()
