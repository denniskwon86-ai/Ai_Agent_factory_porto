"""[M5] 전사 브리핑 REST API. prefix `/api/v1/briefing`. **LLM 0콜.**

`core/enterprise_briefing.py` 의 집계를 노출한다. 제품 성경 §5.5 가 요구하는 "이해"의 재료다 —
서술(narration)은 이 결과 **위에** 얹는 별개 층이고, 판정은 여기서 끝난다.

## 이 라우터의 불변식

1. **범위를 못 정하면 아무것도 주지 않는다(fail-closed).** 전사 보좌에서 범위 오류의
   기본값이 "전체 노출"이면 그 한 번으로 제품이 끝난다. 거부는 감사로그에 남고 404 로 은폐한다.
2. **`complete=false` 를 200 으로 감추지 않는다.** 읽지 못한 소스가 있으면 그 사실이
   응답 최상위에 있어야 한다 — 조용히 빠진 위험이 가장 위험하다.
3. **actor 는 인증 주체에서 온다.** 클라이언트가 보낸 이름으로 "내가 결정할 것"을 계산하면
   남의 결재함을 들여다볼 수 있다.
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException

from api.deps import Principal, current_principal
from core.enterprise_briefing import SECTIONS, enterprise_briefing
from core.scope_guard import resolve_effective_scope

router = APIRouter(prefix="/api/v1/briefing", tags=["Briefing"])


async def _scope(p: Principal, requested: str, tenant_id: str = "",
                 entity_mode: str = "") -> str:
    """요청 범위를 인증 주체 안에서 교차 검증한다(§B-4 와 같은 경로를 쓴다).

    ★ [D-018 ③④] 판정·정규화는 `api.deps.assert_scope_allowed` **한 곳**에 있다 — 종전에는
      이 코드가 `planning_control`·`connector_control` 에도 복제돼 있었고, 세 벌이면 문맥
      인자를 하나에만 붙이거나 감사 이름을 한 곳만 고치는 일이 생긴다."""
    from api.deps import assert_scope_allowed
    eff = await assert_scope_allowed(p, requested, resource_type="briefing",
                                    tenant_id=tenant_id, entity_mode=entity_mode)
    return eff.scope_node_id


@router.get("")
async def briefing(scope_node_id: str = "", tenant_id: str = "", entity_mode: str = "REAL",
                   p: Principal = Depends(current_principal)):
    """권한 범위 안의 전사 상태 1장.

    ⚠️ `complete=false` 면 **이 브리핑은 전부가 아니다.** `unavailable` 에 읽지 못한 소스가
      있고, 화면은 그것을 숨기지 말 것 — "위험 0건"과 "위험을 못 읽었다"는 다른 사실이다."""
    # ★ [D-018 ③④] 이 라우트는 `tenant_id`·`entity_mode` 를 이미 받고 있었지만 **범위 해석에
    #   넘기지 않았다.** 코드는 그 문맥 안에서만 유일하므로, 넘기지 않으면 가상 시나리오 범위를
    #   실제 문맥으로 해석할 수 있다.
    from api.deps import assert_scope_allowed, scope_meta
    _eff = await assert_scope_allowed(p, scope_node_id, resource_type="briefing",
                                     tenant_id=tenant_id, entity_mode=entity_mode)
    eff = _eff.scope_node_id
    data = await asyncio.to_thread(enterprise_briefing.briefing, p.user_id, eff,
                                   tenant_id, entity_mode, p)
    return {"status": "success", "data": data,
            "permission": {"scope": eff or "(범위 필터 없음)", "actor": p.user_id,
                           **scope_meta(_eff)}}


@router.get("/sections/{section}")
async def section(section: str, scope_node_id: str = "", tenant_id: str = "",
                  entity_mode: str = "REAL",
                  p: Principal = Depends(current_principal)):
    """섹션 하나만 조회(화면 부분 갱신용).

    ⚠️ 섹션 이름을 자유 문자열로 받지 않는다 — 오타가 "빈 결과"로 보이면
      사용자는 위험이 없다고 읽는다."""
    if section not in SECTIONS:
        raise HTTPException(status_code=400,
                            detail=f"알 수 없는 섹션입니다: {section}. "
                                   f"가능: {', '.join(SECTIONS)}")
    eff = await _scope(p, scope_node_id, tenant_id=tenant_id, entity_mode=entity_mode)

    def _one():
        if section == "cost":
            return {"cost": enterprise_briefing.cost(p)}
        fn = {"my_decisions": lambda: enterprise_briefing.my_decisions(
                  p.user_id, eff, tenant_id, entity_mode),
              "blocked": lambda: enterprise_briefing.blocked(eff, tenant_id, entity_mode),
              "data_health": lambda: enterprise_briefing.data_health(eff, tenant_id, entity_mode),
              "programs": enterprise_briefing.programs}[section]
        col = fn()
        return {"items": col.sorted_items(), "count": len(col.items),
                # 실패를 삼키지 않는다 — 섹션 단위 조회에서도 같은 규칙이다.
                "unavailable": col.unavailable,
                "complete": not col.unavailable}

    return {"status": "success", "data": await asyncio.to_thread(_one),
            "section": section,
            "permission": {"scope": eff or "(범위 필터 없음)", "actor": p.user_id}}
