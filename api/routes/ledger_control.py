"""Decision Ledger 조회 API — 마스터 명세서 §5.2 / M0 백로그 5.

⚠️ **쓰기 엔드포인트를 의도적으로 만들지 않는다.** Ledger 는 "이 결정이 실제로 일어났다"는
  증거인데, 외부에서 임의로 이벤트를 넣을 수 있으면 그 증거가 무의미해진다. 기록은 **결정이
  실제로 일어나는 코드 경로**(Blueprint 승인, 프로젝트 부트스트랩 등)에서만 이뤄진다.
  같은 이유로 수정·삭제 엔드포인트도 없다 — 정정은 그 결정을 내리는 기능이 정정 이벤트를 잇는다.

권한: 감사 이력은 결정 사유·미확보 데이터·승인자를 담으므로 **부서 문맥 격리를 적용**한다.
  다른 테넌트·다른 상태(가상/경쟁사)의 이력은 이 문맥에서 보이지 않는다.
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from api.deps import (Principal, assert_identified, current_principal, enterprise_context)
from core.decision_ledger import (ACTOR_TYPES, EVENT_TYPES, SUBJECT_TYPES,
                                  decision_ledger)
from core.enterprise_context import EnterpriseContext

router = APIRouter(prefix="/api/v1/ledger", tags=["DecisionLedger"])

#: 사용자에게 보일 자료 이름. 조사(을/를)는 `deps.eul` 이 맞춘다.
WHAT = "결정 원장"



def _scoped(ctx: EnterpriseContext) -> dict:
    """문맥 격리 인자. 무제한 권한이라도 **문맥은 섞지 않는다** — 권한과 문맥은 다른 축이다
    (경영진이라도 가상 시나리오 이력이 실제 이력에 섞여 보이면 안 된다)."""
    return {"tenant_id": ctx.tenant_id, "entity_mode": ctx.entity_mode}


@router.get("/event-types")
async def get_event_types(
        p: Principal = Depends(current_principal)):
    """등록된 이벤트/주체/행위자 유형. 미등록 유형은 기록이 거부되므로 클라이언트가 알아야 한다."""
    assert_identified(p, WHAT)
    return {"status": "success", "data": {
        "event_types": list(EVENT_TYPES), "subject_types": list(SUBJECT_TYPES),
        "actor_types": list(ACTOR_TYPES)}}


@router.get("/events")
async def get_events(subject_type: str = "", subject_id: str = "", event_type: str = "",
                     project_id: str = "", blueprint_id: str = "", limit: int = 100,
                     p: Principal = Depends(current_principal),
                     ctx: EnterpriseContext = Depends(enterprise_context)):
    """결정 이력 조회(최신순). 필터를 조합해 "이 대상에 무슨 결정이 있었나"를 좁힌다."""
    if event_type and event_type not in EVENT_TYPES:
        raise HTTPException(status_code=400, detail=f"등록되지 않은 event_type: {event_type}")
    if subject_type and subject_type not in SUBJECT_TYPES:
        raise HTTPException(status_code=400, detail=f"등록되지 않은 subject_type: {subject_type}")
    rows = await asyncio.to_thread(
        decision_ledger.list_events, subject_type, subject_id, event_type,
        project_id, blueprint_id, ctx.tenant_id, ctx.entity_mode, limit)
    rows = _filter_by_dept(rows, p)
    return {"status": "success", "data": rows, "permission": _scoped(ctx)}


@router.get("/subjects/{subject_type}/{subject_id}/history")
async def get_subject_history(subject_type: str, subject_id: str,
                             p: Principal = Depends(current_principal),
                             ctx: EnterpriseContext = Depends(enterprise_context)):
    """한 대상의 전체 이력(오래된 것부터) — "왜 이렇게 됐나"에 답하는 기본 조회(§1.3)."""
    if subject_type not in SUBJECT_TYPES:
        raise HTTPException(status_code=400, detail=f"등록되지 않은 subject_type: {subject_type}")
    rows = await asyncio.to_thread(decision_ledger.subject_history, subject_type, subject_id)
    rows = [r for r in rows
            if r["tenant_id"] == ctx.tenant_id and r["entity_mode"] == ctx.entity_mode]
    rows = _filter_by_dept(rows, p)
    return {"status": "success", "data": rows, "permission": _scoped(ctx)}


def _filter_by_dept(rows: list, p: Principal) -> list:
    """부서 스코프 적용.

    ⚠️ Ledger 의 `enterprise_scope_id` 는 현재 **부서 id**를 담는다(ECM-lite — E1 에서 ECM
      node_id 로 승격 예정). 그래서 지금은 부서 권한으로 판정할 수 있다. E1 이후에는 노드
      트리를 타야 하므로 이 함수를 ECM 리졸버로 바꿔야 한다.
    ⚠️ 범위가 비어 있는 이벤트(전사 시스템 이벤트 등)는 **무제한 권한자에게만** 보인다 —
      감사 이력은 결정 사유와 승인자를 담으므로 귀속 불명은 통과시키지 않는다(fail-closed)."""
    if p.scope.unrestricted:
        return rows
    readable = set(p.scope.readable_dept_ids or ())
    out = []
    for r in rows:
        scope = r.get("enterprise_scope_id") or ""
        if scope and scope in readable:
            out.append(r)
        elif not scope and (r.get("actor_id") or "") == p.user_id:
            out.append(r)      # 범위 없는 이벤트라도 본인이 행위자면 자기 이력은 볼 수 있다
    return out


@router.get("/verify")
async def verify_chain(p: Principal = Depends(current_principal)):
    """해시 체인 무결성 점검.

    ⚠️ 전체 이력을 재계산하므로 **전사 열람 권한자 전용**이다(문맥별로 나눠 검증할 수 없다 —
      체인은 테넌트를 가로질러 하나로 이어진다).
    ⚠️ 응답의 `limitation` 을 반드시 함께 노출할 것: 이 검증은 DB 직접 조작을 막지 못하고
      불일치를 탐지만 한다. '위조 불가'로 오해하면 안 된다."""
    from api.deps import assert_enterprise
    assert_enterprise(p)
    return {"status": "success", "data": await asyncio.to_thread(decision_ledger.verify_chain)}
