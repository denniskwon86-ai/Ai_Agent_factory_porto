"""골든 벤치마크 REST API. prefix /api/v1/benchmark.

core/golden_benchmark.py 의 3축 채점·스코어카드·회귀비교를 노출한다.
evaluate 는 (use_llm_judge=True 시) LLM 쿼터를 쓰므로 명시적 호출로만 동작한다.
응답 봉투는 리포 관례 {"status": "success", "data": ...}.

## [2026-08-07 · 트랙 G] 무방비 라우트 봉합 — 이 파일은 **6개 전부**가 무방비였다

실측(2026-08-05): 이 라우터의 6개 라우트 중 **하나도 익명을 막지 않았다.** 그중
`POST /{id}/promote-golden` 은 **플랫폼의 품질 기준선 자체를 바꾼다** — 익명이 낮은 점수의
스코어카드를 골든으로 승격시키면, 그 뒤로는 «회귀 없음» 이 계속 참이 된다. 즉 통제를 끄는 것이
아니라 **통제가 거짓말을 하게 만드는** 경로였다. 그래서 16개 파일 중 이것을 먼저 봉합한다.

⚠️ 이 라우터는 프론트·스크립트·테스트 어디에서도 호출되지 않는다(실측). 「쓰는 데가 없으니
  나중에」가 아니라 **쓰는 데가 없으니 지금 엄격하게 닫는다** — 회귀 위험 없이 닫을 수 있는
  때가 지금이고, 화면이 붙은 뒤에는 못 닫는다. `planning_control` 이 「지금은 0건이라 유출이
  없다」로 미뤘다가 데이터가 들어와 실제 유출이 된 것과 반대 방향의 결정이다.

## 권한 배정 근거

| 라우트 | 요구 | 왜 |
|---|---|---|
| `GET /scenarios` · `/{id}/scorecard` · `/{id}/compare` | 식별 | 업무 자료(품질 점수)다 |
| `POST /{id}/evaluate` | `model.policy.manage` | LLM 쿼터를 태우고 스코어카드를 남긴다 |
| `POST /{id}/human-score` | `model.policy.manage` | 사람 점수가 골든 승격의 근거가 된다 |
| `POST /{id}/promote-golden` | `system.default.edit` | 설계 §4.2 «플랫폼 관리자 — 버전 승격만 가능» |

⚠️ **더 정확히는 `benchmark.*` 전용 코드가 있어야 한다.** 그런데 capability 코드를 늘리는 일은
  권한 모델(트랙 B)의 몫이고, 라우트 봉합(트랙 G)에서 조용히 끼워 넣으면 역할 표가 두 트랙에서
  따로 자란다. 여기서는 **의미가 가장 가까운 기존 코드**를 쓰고 그 사실을 적어 둔다.
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from api.deps import Principal, assert_identified, current_principal, require_caps
from core.admin_capability import MODEL_POLICY_MANAGE, SYSTEM_DEFAULT_EDIT
from core.golden_benchmark import golden_benchmark

router = APIRouter(prefix="/api/v1/benchmark")

#: 사용자에게 보일 자료 이름. 조사(을/를)는 `deps.eul` 이 맞춘다.
WHAT = "벤치마크"


class HumanScoreRequest(BaseModel):
    score: float
    notes: Optional[str] = ""


@router.get("/scenarios")
async def list_scenarios(p: Principal = Depends(current_principal)):
    assert_identified(p, WHAT)
    return {"status": "success", "data": golden_benchmark.list_scenarios()}


@router.post("/{scenario_id}/evaluate")
async def evaluate(scenario_id: str, use_llm_judge: bool = False,
                   p: Principal = Depends(current_principal)):
    """시나리오 산출물을 3축으로 채점해 스코어카드를 생성. use_llm_judge=True 는 LLM 쿼터 소비."""
    assert_identified(p, WHAT)
    require_caps(p, MODEL_POLICY_MANAGE, resource="benchmark", action="evaluate")
    try:
        card = await golden_benchmark.evaluate(scenario_id, use_llm_judge=use_llm_judge)
        return {"status": "success", "data": card}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{scenario_id}/scorecard")
async def latest_scorecard(scenario_id: str, p: Principal = Depends(current_principal)):
    assert_identified(p, WHAT)
    card = await asyncio.to_thread(golden_benchmark.latest_scorecard, scenario_id)
    if not card:
        raise HTTPException(status_code=404, detail="스코어카드가 없습니다. 먼저 evaluate 하세요.")
    return {"status": "success", "data": card}


@router.post("/{scenario_id}/human-score")
async def set_human_score(scenario_id: str, req: HumanScoreRequest,
                          p: Principal = Depends(current_principal)):
    assert_identified(p, WHAT)
    require_caps(p, MODEL_POLICY_MANAGE, resource="benchmark", action="human-score")
    try:
        rec = await asyncio.to_thread(golden_benchmark.set_human_score, scenario_id, req.score, req.notes or "")
        return {"status": "success", "data": rec}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{scenario_id}/promote-golden")
async def promote_golden(scenario_id: str, p: Principal = Depends(current_principal)):
    """현재(최신) 스코어카드를 이 시나리오의 골든 기준으로 고정.

    ★★ **이 라우터에서 가장 위험한 한 줄이다.** 골든 기준이 바뀌면 `compare` 의 «회귀 없음» 이
      기준선째로 이동한다 — 품질이 나빠져도 지표는 조용하다. 그래서 플랫폼 관리자 전용이다."""
    assert_identified(p, WHAT)
    require_caps(p, SYSTEM_DEFAULT_EDIT, resource="benchmark", action="promote-golden")
    try:
        card = await asyncio.to_thread(golden_benchmark.promote_golden, scenario_id)
        return {"status": "success", "data": card}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{scenario_id}/compare")
async def compare(scenario_id: str, p: Principal = Depends(current_principal)):
    """골든 기준 대비 최신 스코어카드의 회귀(점수 하락) 리포트."""
    assert_identified(p, WHAT)
    report = await asyncio.to_thread(golden_benchmark.compare, scenario_id)
    return {"status": "success", "data": report}
