# -*- coding: utf-8 -*-
"""[LE-01] Living Enterprise Canvas 읽기 모델 — **경영 홈이 보는 단 하나의 집계.**

## 왜 이 모듈이 생겼는가 (2026-08-24)

승인 시안(`uiux-prototypes/master-concept/index.html`, 2026-07-30 Supervisor 「합격 ·
메인 UI North Star로 채택」)과 그 매핑 문서(`IMPLEMENTATION_MAPPING.md`)는 처음부터
이것을 요구했다:

    GET /api/v1/enterprise-canvas?scope_id=…&as_of=…
      → context · decision_queue · domain_nodes · relationships
        · trust_foundation · agent_summary · cost_summary

⚠️⚠️ **그 API 를 만들지 않았다.** 그래서 화면이 있는 API 를 여섯 군데 긁어모아
(`/briefing`·`/master/types`·`/crosswalk/…`·`/knowledge/packs`·`/external/readiness`·
`/org/tree`) 스스로 조립했고, 시안이 요구한 **수주→손익 도메인 노드**를 줄 곳이 없으니
**조직 트리로 대체**했다. 대체물이 그대로 굳어 「업무 흐름」이 부서 목록이 됐고,
사용자는 「이걸 보고 뭘 해야 하는지 모르겠다」고 했다.

★★★ 디자인이 바뀐 것이 아니라 **디자인이 요구한 집계를 안 만든 것**이었다. 여기서 만든다.

## 도메인 노드는 조직도가 아니라 가치사슬이다

시안의 중앙 축은 `수주·판매 → 원료조달 → 생산계획 → 제련·생산 → 품질 → 물류·출하 →
손익·경영` 일곱 단계다. 부서 계층이 아니다. 그리고 그 일곱은 업무 키트의 **계약키**와
그대로 대응한다 — 그래서 각 단계의 상태를 **지어내지 않고** 인증판에서 읽을 수 있다.

⚠️ 채택 결정문: 「화면에 표시하는 수치·상태·추천은 **실제 API 근거가 있을 때만**
  노출한다.」 시안 화면의 `수요 +3%`·`가동 94%` 는 `PROTOTYPE · SAMPLE DATA` 표기가
  붙은 시안 값이다. 근거가 생기기 전에는 `primary_metric` 을 **비운다.**
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

#: ★ 노드 상태 — 설계서 §4.4 `DomainNodeVM.status` 의 닫힌 목록.
NORMAL = "normal"
ATTENTION = "attention"
DECISION_REQUIRED = "decision_required"

#: 경영 홈은 회사가 무엇을 결정하고 실행할 수 있는지 보여 주는 자리다.
#: 개별 Shadow 비교의 기술적 진단은 이력을 보존하되 Shadow Mode 화면에서 다룬다.
#: 이를 의사결정 대기열에 올리면 검증용 입력 오류가 회사의 대표 안건처럼 보인다.
HOME_EXCLUDED_KINDS = frozenset({"shadow_incomparable"})
BLOCKED = "blocked"
UNKNOWN = "unknown"

#: 시안 중앙 축 — **수주→손익 일곱 단계.**
#:
#: ⚠️ `systems` 는 시안이 각 노드 아래 적은 연결 시스템 이름이다. 지금은 **표시 문구**이고,
#:   실제 연결 여부는 `연계/크로스워크` 가 답한다 — 둘을 같은 것으로 읽지 않게 응답에
#:   `systems_verified: False` 를 함께 싣는다.
#: ★ `contract_keys` 가 이 단계의 **근거**다. 업무 키트의 계약키와 대응시켜, 상태를
#:   짐작하지 않고 인증판에서 읽는다.
DOMAIN_NODES: List[Dict[str, Any]] = [
    {"id": "sales", "sequence": 1, "label": "수주·판매", "systems": "CRM · ERP",
     "contract_keys": ["SLS-01", "MDM-03"]},
    {"id": "sourcing", "sequence": 2, "label": "원료조달", "systems": "구매 · 재고",
     "contract_keys": ["PRC-01", "PRC-02", "MDM-02", "EXT-02"]},
    {"id": "planning", "sequence": 3, "label": "생산계획", "systems": "APS · MES",
     "contract_keys": ["MFG-01", "MDM-05", "SIM-01"]},
    {"id": "production", "sequence": 4, "label": "제련·생산", "systems": "MES · 설비",
     "contract_keys": ["MFG-02", "MFG-03", "MDM-06"]},
    {"id": "quality", "sequence": 5, "label": "품질", "systems": "QMS · LIMS",
     "contract_keys": ["QLT-01"]},
    {"id": "logistics", "sequence": 6, "label": "물류·출하", "systems": "WMS · TMS",
     "contract_keys": ["LOG-01", "LOG-02", "LOG-03", "LOG-04", "LOG-05",
                       "INV-01", "INV-02"]},
    {"id": "finance", "sequence": 7, "label": "손익·경영", "systems": "ERP · Twin",
     "contract_keys": ["FIN-01", "FIN-02", "FIN-03", "DEC-01"]},
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _snapshot_state(store: Any, instance_id: str) -> Dict[str, str]:
    """계약키 → 그 키의 **인증 상태**. 없는 키는 목록에 없다.

    ⚠️ 조회 실패를 빈 딕셔너리로 접지 않는다 — 호출부가 `None` 을 받아
      「확인하지 못했다」로 그린다."""
    out: Dict[str, str] = {}
    for row in store.list_snapshots(instance_id):
        key = str(row.get("dataset_contract_key") or "")
        if not key:
            continue
        st = str(row.get("status") or "")
        #: 인증된 판이 하나라도 있으면 그 키는 인증됨이다(최신 판정은 준비도의 일).
        if st == "certified" or row.get("certified_at"):
            out[key] = "certified"
        else:
            out.setdefault(key, st or "draft")
    return out


def _node_status(keys: List[str], certified: Optional[Dict[str, str]],
                 decisions: int) -> Dict[str, Any]:
    """한 노드의 상태·근거 수.

    ★ 순서가 곧 규칙이다: **결정 대기 > 자료 없음 > 일부 > 정상.**
    ⚠️ 인증판을 못 읽었으면 `unknown` 이다 — 「자료 없음」과 「확인 못 함」은 다르다.
    """
    if certified is None:
        return {"status": UNKNOWN, "evidence_count": None,
                "reason": "인증판 상태를 확인하지 못했습니다."}
    have = [k for k in keys if certified.get(k) == "certified"]
    if decisions:
        #: 이 단계에 사람이 답해야 할 것이 있으면 그것이 먼저다.
        return {"status": DECISION_REQUIRED, "evidence_count": len(have),
                "reason": f"결정 대기 {decisions}건"}
    if not have:
        return {"status": BLOCKED, "evidence_count": 0,
                "reason": "이 단계의 자료가 아직 인증되지 않았습니다."}
    if len(have) < len(keys):
        return {"status": ATTENTION, "evidence_count": len(have),
                "reason": f"필요 {len(keys)}종 중 {len(have)}종만 인증됐습니다."}
    return {"status": NORMAL, "evidence_count": len(have), "reason": ""}


def build(*, scope_node_id: str = "", tenant_id: str = "", entity_mode: str = "",
          briefing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """경영 홈이 보는 단 하나의 집계.

    ★ `briefing` 을 주면 그것을 쓴다 — 라우트가 이미 부른 것을 두 번 부르지 않는다.
    ⚠️ 어느 조각이 실패해도 **전체를 죽이지 않는다.** 실패한 조각은 `unavailable` 로
      남기고 나머지를 준다 — 첫 화면이 한 조각 때문에 통째로 비면 사용자는 로그인이
      깨진 줄 안다.
    """
    unavailable: List[Dict[str, str]] = []

    def _try(name: str, fn, default=None):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — 조각 실패를 전체 실패로 만들지 않는다
            unavailable.append({"source": name, "reason": str(exc)[:160]})
            return default

    if briefing is None:
        def _b():
            from core.enterprise_briefing import enterprise_briefing
            return enterprise_briefing.briefing(
                scope_node_id=scope_node_id, tenant_id=tenant_id,
                entity_mode=entity_mode)
        briefing = _try("enterprise_briefing.briefing", _b, {}) or {}

    sections = briefing.get("sections") or {}

    #: ── 의사결정 대기열 ────────────────────────────────────────────────
    #: ★ 시안 좌측. 「내가 결정할 것」과 「막힌 것」을 **한 줄기로** 세운다 —
    #:   사용자에게는 둘 다 「지금 처리할 일」이고, 성격은 `section` 으로 구분한다.
    queue: List[Dict[str, Any]] = []
    for name in ("my_decisions", "blocked", "data_health", "programs"):
        for it in ((sections.get(name) or {}).get("items") or []):
            if str(it.get("kind") or "") in HOME_EXCLUDED_KINDS:
                continue
            queue.append({**it, "section": name})

    #: ── 도메인 노드 ────────────────────────────────────────────────────
    def _instance():
        from core.data_preparation.store import data_preparation_store as store
        with store.transaction() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT instance_id FROM kit_instances WHERE status='active' "
                "AND (?='' OR scope_node_id=?) ORDER BY created_at LIMIT 1",
                (scope_node_id, scope_node_id))]
        return (store, rows[0]["instance_id"] if rows else "")

    got = _try("data_preparation.kit_instances", _instance, (None, ""))
    store, instance_id = got if got else (None, "")
    certified: Optional[Dict[str, str]] = None
    if store is not None and instance_id:
        certified = _try("data_preparation.list_snapshots",
                         lambda: _snapshot_state(store, instance_id), None)

    nodes: List[Dict[str, Any]] = []
    for spec in DOMAIN_NODES:
        #: 이 단계에 걸린 결정 — 지금은 항목에 단계 표시가 없으므로 0 이다.
        #: ⚠️ 억지로 이어 붙이지 않는다. 브리핑 항목에 `domain` 이 실리면 그때 센다.
        st = _node_status(spec["contract_keys"], certified,
                          decisions=sum(1 for q in queue
                                        if str(q.get("domain") or "") == spec["id"]))
        nodes.append({
            "id": spec["id"], "sequence": spec["sequence"], "label": spec["label"],
            "systems": spec["systems"],
            #: ⚠️ 시안의 `수요 +3%`·`가동 94%` 는 시안 표본값이다. 근거가 생기기 전에는
            #:   비운다 — 채택 결정문이 「실제 API 근거가 있을 때만」이라고 못박았다.
            "primary_metric": None,
            "required_keys": spec["contract_keys"],
            **st,
        })

    return {
        "context": {
            "scope_node_id": scope_node_id,
            "tenant_id": tenant_id,
            "entity_mode": entity_mode,
            "kit_instance_id": instance_id,
        },
        "decision_queue": queue,
        "domain_nodes": nodes,
        #: ⚠️ 시안이 노드 아래 적은 시스템 이름은 **표시 문구**다. 실제 연결 여부가
        #:   아니라는 것을 응답이 스스로 말한다.
        "systems_verified": False,
        "trust_foundation": briefing.get("trust_foundation") or {},
        "cost_summary": sections.get("cost") or {},
        "unavailable": (briefing.get("unavailable") or []) + unavailable,
        "generated_at": _now(),
    }
