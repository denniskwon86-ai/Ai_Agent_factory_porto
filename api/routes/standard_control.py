"""업무표준(규정/지침) REST API. prefix /api/v1/standards.

에이전트가 따르는 판정 기준·작성 표준을 **법규처럼 조회·개정**하기 위한 라우트.
저장소는 M1 기준정보(master.db `master_records`)이며, 개정 시 새 버전이 생기고
구판은 리니지(`supersedes`)로 보존된다.

응답 봉투는 리포 관례 {"status": "success", "data": ...}.

★★★ [2026-08-04 이관 3/10 실측 결함] **이 파일의 모든 라우트에 권한 검사가 없었다.**
  익명 요청으로 `POST /api/v1/standards` 와 `POST /api/v1/standards/seed?force=true` 가
  그대로 통했다 — 즉 **누구나 에이전트의 판정 기준을 바꿀 수 있었다.** 업무표준을 바꾸면
  이후 모든 산출물의 통과·반려 기준이 바뀌므로, 지식팩을 지우는 것보다 파급이 넓다.
  화면을 라이트 테마로 옮기기 전에 이것부터 막았다 — 보이는 것을 고치는 일보다 앞선다.

  통제 방침:
    · 읽기 — 업무표준은 **전사 제도 문서**다. 조직 소유물이 아니므로 조직 범위로 가리지 않되,
      익명·폐지 계정에는 목록을 주지 않는다(관문 A 의 «미지정 = 비노출»과 같은 계약).
      목록은 200 + `blocked_reason` 으로 돌려준다 — «없다»와 «안 보인다»는 정반대의 사실이다.
    · 쓰기·재시드 — `assert_can_manage_standard`(DA·관리자). 권한 이름 그대로의 대상이다.
    · 개정은 감사에 남긴다(`WORK_STANDARD_CHANGED`). 남지 않으면 지난달 반려된 산출물이
      이번 달 통과한 이유를 설명할 수 없다.
"""
import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import (Principal, assert_can_manage_standard, current_principal,
                      visibility_block_reason)
from core.enterprise_context import audit
from core.master_data import MasterDataError, master_data
from core.work_standard import (
    KIND_GUIDELINE, KIND_REGULATION,
    WORK_GUIDELINE_TYPE, WORK_REGULATION_TYPE,
    get_standard, register_standard, render_standard_brief, standard_code,
)

router = APIRouter(prefix="/api/v1/standards")


def _err(e: MasterDataError):
    msg = str(e)
    raise HTTPException(status_code=409 if "이미 존재" in msg else 400, detail=msg)


def _assert_readable(p: Principal):
    """상세·이력 조회 자격. 목록은 200 + `blocked_reason` 이지만 상세는 403 이다.

    ⚠️ 여기서 404 로 숨기지 않는다. 404 Data Stealth 는 **타 조직 자료의 존재**를 숨기기 위한
      것이고, 업무표준은 전사 제도 문서라 존재 자체가 비밀이 아니다. 숨길 것이 없는 자료를
      404 로 돌려주면 «없는 표준»과 «권한 없음»이 섞여서 운영자가 원인을 찾지 못한다."""
    reason = visibility_block_reason(p)
    if reason:
        audit.record(audit.ACCESS_DENIED_UNAUTHENTICATED, "work_standard", "(목록·상세)",
                     actor=p.user_id, reason=reason,
                     detail="업무표준 조회 자격 없음")
        raise HTTPException(status_code=403, detail=reason)


class CheckItem(BaseModel):
    id: str
    desc: str = ""
    weight: float = 1
    type: str = "llm_judge"          # deterministic | llm_judge
    advisory: bool = False           # True = 보고 전용(통과/반려에 미반영)


class StandardUpsert(BaseModel):
    """업무표준 등록/개정 요청. 같은 stage 로 다시 보내면 **새 버전**이 된다."""
    stage: str
    kind: str = KIND_REGULATION      # regulation | guideline
    name: Optional[str] = None
    agent_id: str = ""
    role_statement: str = ""
    # 규정(판정) 전용
    evaluates: str = ""
    # 지침(생성) 전용
    inputs: str = ""
    deliverable: str = ""
    must_include: List[str] = []
    principles: List[str] = []
    # 공통
    must_not: List[str] = []
    checks: List[CheckItem] = []
    pass_threshold: float = 0.7
    hard_fail_checks: List[str] = []
    judge_heavy: bool = False
    judge_persona: str = ""
    valid_from: Optional[str] = None


def _list_all() -> list:
    """등록된 업무표준 전체(현행본)를 규정/지침 구분과 함께 돌려준다."""
    out = []
    for type_id in (WORK_REGULATION_TYPE, WORK_GUIDELINE_TYPE):
        try:
            rows = master_data.list_records(type_id=type_id) or []
        except Exception:
            rows = []
        for r in rows:
            attrs = r.get("attributes") or {}
            if isinstance(attrs, str):
                import json as _j
                try:
                    attrs = _j.loads(attrs or "{}")
                except Exception:
                    attrs = {}
            out.append({
                "master_code": r.get("master_code"),
                "name": r.get("name"),
                "version": r.get("version"),
                "valid_from": r.get("valid_from"),
                "status": r.get("status"),
                "type_id": type_id,
                "kind": attrs.get("standard_kind",
                                  KIND_REGULATION if type_id == WORK_REGULATION_TYPE else KIND_GUIDELINE),
                "stage": attrs.get("stage", ""),
                "agent_id": attrs.get("agent_id", ""),
                "role_statement": attrs.get("role_statement", ""),
                "pass_threshold": attrs.get("pass_threshold"),
                "gate_count": len([c for c in (attrs.get("checks") or []) if not c.get("advisory")]),
                "advisory_count": len([c for c in (attrs.get("checks") or []) if c.get("advisory")]),
            })
    out.sort(key=lambda x: (x["kind"], x["stage"]))
    return out


@router.get("")
async def list_standards(p: Principal = Depends(current_principal)):
    """전체 업무표준 목록(규정/지침). 자격이 없으면 0건 + 이유."""
    reason = visibility_block_reason(p)
    if reason:
        return {"status": "success", "data": [], "blocked_reason": reason}
    return {"status": "success", "data": await asyncio.to_thread(_list_all)}


@router.get("/kinds")
async def list_kinds(p: Principal = Depends(current_principal)):
    """분류 구분 안내 — 화면에서 규정/지침 탭을 그리기 위한 메타.

    ⚠️ 이 응답에는 자료가 없다(분류 이름과 설명뿐). 그래도 자격을 확인한다 —
      익명에게 탭만 그려 주면 화면은 «권한 있음»처럼 보이고 목록만 비어, 사용자는
      «등록된 표준이 없다»로 읽는다. 통제는 화면 전체가 한 방향을 말해야 한다."""
    reason = visibility_block_reason(p)
    if reason:
        return {"status": "success", "data": [], "blocked_reason": reason}
    return {"status": "success", "data": [
        {"kind": KIND_REGULATION, "type_id": WORK_REGULATION_TYPE, "label": "업무규정(판정 에이전트)",
         "desc": "앞 단계 산출물을 받아 통과/반려를 정한다. 기준값을 엄격히 따른다."},
        {"kind": KIND_GUIDELINE, "type_id": WORK_GUIDELINE_TYPE, "label": "업무지침(생성 에이전트)",
         "desc": "산출물을 만든다. 작성 표준을 따르며 통과/반려 권한이 없다."},
    ]}


@router.get("/{stage}")
async def get_one(stage: str, p: Principal = Depends(current_principal)):
    """단계별 현행 업무표준 원문 + 에이전트가 실제로 받는 고지문."""
    _assert_readable(p)
    std = await asyncio.to_thread(get_standard, stage)
    if not std:
        raise HTTPException(status_code=404, detail=f"'{stage}' 업무표준이 없습니다.")
    brief = await asyncio.to_thread(render_standard_brief, stage)
    return {"status": "success", "data": {"standard": std, "agent_brief": brief}}


@router.get("/{stage}/history")
async def get_history(stage: str, p: Principal = Depends(current_principal)):
    """개정 이력(구판 포함) — 법규 연혁처럼 언제 무엇이 바뀌었는지 본다."""
    _assert_readable(p)
    code = standard_code(stage)

    def _hist():
        try:
            with master_data._connect() as conn:   # 이력은 전용 조회 API 가 없어 직접 읽는다
                rows = conn.execute(
                    "SELECT master_code, name, version, valid_from, valid_to, status, source, updated_at "
                    "FROM master_records WHERE master_code=? ORDER BY version DESC", (code,)
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    data = await asyncio.to_thread(_hist)
    if not data:
        raise HTTPException(status_code=404, detail=f"'{code}' 이력이 없습니다.")
    return {"status": "success", "data": data}


@router.post("")
async def upsert_standard(req: StandardUpsert, p: Principal = Depends(current_principal)):
    """업무표준 등록/개정. 같은 단계로 다시 보내면 새 버전이 되고 구판은 보존된다."""
    assert_can_manage_standard(p)
    if req.kind not in (KIND_REGULATION, KIND_GUIDELINE):
        raise HTTPException(status_code=400, detail="kind 는 regulation 또는 guideline 이어야 합니다.")
    payload = {
        "stage": req.stage.upper(),
        "agent_id": req.agent_id,
        "role_statement": req.role_statement,
        "must_not": req.must_not,
        "checks": [c.model_dump() for c in req.checks],
        "pass_threshold": req.pass_threshold,
        "hard_fail_checks": req.hard_fail_checks,
        "judge_heavy": req.judge_heavy,
        "judge_persona": req.judge_persona,
    }
    if req.kind == KIND_REGULATION:
        payload["evaluates"] = req.evaluates
    else:
        payload.update({"inputs": req.inputs, "deliverable": req.deliverable,
                        "must_include": req.must_include, "principles": req.principles})
    label = "업무규정" if req.kind == KIND_REGULATION else "업무지침"
    try:
        rec = await asyncio.to_thread(
            register_standard, req.stage.upper(),
            req.name or f"{req.stage.upper()} {label}", payload, req.kind, req.valid_from, "user")
    except MasterDataError as e:
        _err(e)
    # 개정은 반드시 남긴다 — 판정 기준이 언제 누구에 의해 바뀌었는지가 없으면 과거 산출물의
    # 통과·반려를 설명할 수 없다. 기록 실패는 조용히 넘기지 않는다(`audit.record` 가 알린다).
    audit.record(audit.WORK_STANDARD_CHANGED, "work_standard",
                 standard_code(req.stage.upper()),
                 actor=p.user_id, outcome="allowed",
                 detail=f"{label} 개정 · v{rec.get('version')} · "
                        f"관문 {len([c for c in req.checks if not c.advisory])}개 · "
                        f"통과임계 {req.pass_threshold}")
    return {"status": "success", "data": rec}


@router.post("/seed")
async def reseed(force: bool = False, p: Principal = Depends(current_principal)):
    """코드 기본값(criteria.py)에서 재시드. force=True 면 전 단계를 새 버전으로 재등록한다."""
    assert_can_manage_standard(p)
    from core.work_standard_seed import seed_from_criteria
    data = await asyncio.to_thread(seed_from_criteria, force)
    audit.record(audit.WORK_STANDARD_CHANGED, "work_standard", "(전 단계 재시드)",
                 actor=p.user_id, outcome="allowed",
                 detail=f"코드 기본값 재시드 force={force} · 결과 {data}"[:500])
    return {"status": "success", "data": data}
