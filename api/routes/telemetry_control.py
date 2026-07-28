"""운영 계기판 — LLM 호출 텔레메트리 집계 API (Phase 4, LLM 0콜).

data/llm_call_log.jsonl (게이트웨이가 호출마다 append)을 읽어 프로젝트별로 집계한다.
핵심 축은 tier(pro/flash)가 아니라 **used(실제 모델)** — "이 산출물을 실제로 어느 제공사/모델이
만들었나"가 모델 불변성 실측의 근거이기 때문(Gemini/xAI/Groq/Cerebras/OpenRouter 구분).

안전성:
- 실행 중 append 되는 파일이라 마지막 줄이 부분 기록일 수 있음 → 줄 단위 파싱 실패는 skip(전체 폐기 금지).
- 읽기 전용 — 파이프라인 append 와 충돌 없음.
"""
import os
import json
from fastapi import APIRouter, Depends

# 🚨 [Phase 4] 텔레메트리는 **전역 롤업**이다. 그런데 로그 키가 `project_id` 가 아니라
#   `project_name`(core/llm_gateway.py) 이라 **부서로 매핑할 수단이 없다.**
#   부서별 필터를 정확히 만들 수 없으므로, 단기 조치로 전사 열람 권한자에게만 연다.
#   근본 수정(로그에 project_id·owner_dept_id 를 싣기)은 별도 항목이다.
from api.deps import Principal, assert_enterprise, current_principal

router = APIRouter(prefix="/api/v1/telemetry", tags=["Telemetry"])

_LOG_PATH = os.path.join("data", "llm_call_log.jsonl")


def _read_records(project: str = "") -> list:
    """텔레메트리 로그를 읽어 레코드 리스트로 반환(부분 기록 줄은 건너뜀). project 지정 시 필터."""
    recs = []
    if not os.path.exists(_LOG_PATH):
        return recs
    try:
        with open(_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue  # 부분 기록/깨진 줄 skip
                if project and (r.get("project") or "") != project:
                    continue
                recs.append(r)
    except Exception:
        pass
    return recs


def aggregate(recs: list) -> dict:
    """레코드 → 집계. used(실제 모델) 분포를 1순위로."""
    totals = {"calls": 0, "ok": 0, "failed": 0, "fallback_calls": 0,
              "downgraded_calls": 0, "total_duration_s": 0.0, 
              "total_input_tokens": 0, "total_output_tokens": 0}
    by_model = {}      # used(실제 모델) → 카운트  ← 핵심 지표
    by_stage = {}      # stage → {calls, ok, avg_duration_s, models{}}
    by_requested = {}  # requested_tier → {calls, downgraded}
    for r in recs:
        totals["calls"] += 1
        ok = bool(r.get("ok"))
        totals["ok" if ok else "failed"] += 1
        totals["total_duration_s"] += float(r.get("duration_s", 0) or 0)
        
        totals["total_input_tokens"] += int(r.get("input_tokens", 0) or 0)
        totals["total_output_tokens"] += int(r.get("output_tokens", 0) or 0)

        attempts = r.get("attempts") or []
        # 폴백: 1차 모델이 아닌 게 실제로 응답했거나(재귀 포함) 시도가 2회 이상이면 폴백으로 집계
        if len(attempts) > 1:
            totals["fallback_calls"] += 1
        if r.get("downgraded"):
            totals["downgraded_calls"] += 1

        used = r.get("used") or "(none)"
        by_model[used] = by_model.get(used, 0) + 1

        stage = r.get("stage") or "(none)"
        s = by_stage.setdefault(stage, {"calls": 0, "ok": 0, "dur": 0.0, "models": {}})
        s["calls"] += 1
        s["ok"] += 1 if ok else 0
        s["dur"] += float(r.get("duration_s", 0) or 0)
        s["models"][used] = s["models"].get(used, 0) + 1

        rt = r.get("requested_tier") or r.get("tier") or "(none)"
        rq = by_requested.setdefault(rt, {"calls": 0, "downgraded": 0})
        rq["calls"] += 1
        rq["downgraded"] += 1 if r.get("downgraded") else 0

    # 파생 지표 정리
    for s in by_stage.values():
        s["avg_duration_s"] = round(s["dur"] / s["calls"], 2) if s["calls"] else 0.0
        del s["dur"]
    totals["total_duration_s"] = round(totals["total_duration_s"], 1)
    totals["success_rate"] = round(totals["ok"] / totals["calls"], 3) if totals["calls"] else 0.0
    totals["fallback_rate"] = round(totals["fallback_calls"] / totals["calls"], 3) if totals["calls"] else 0.0

    return {"totals": totals, "by_model": by_model, "by_stage": by_stage, "by_requested_tier": by_requested}


@router.get("/summary")
async def telemetry_summary(project: str = "", p: Principal = Depends(current_principal)):
    """프로젝트(project_name)별 LLM 호출 집계. project 미지정 시 전역 롤업."""
    assert_enterprise(p)
    recs = _read_records(project)
    data = aggregate(recs)
    data["record_count"] = len(recs)
    data["project"] = project or "(전역)"
    return {"status": "success", "data": data}


@router.get("/raw")
async def telemetry_raw(project: str = "", limit: int = 200,
                        p: Principal = Depends(current_principal)):
    """최근 N건 원시 레코드(디버그/타임라인용)."""
    assert_enterprise(p)
    recs = _read_records(project)
    return {"status": "success", "data": recs[-max(1, min(limit, 2000)):]}


@router.get("/projects")
async def telemetry_projects(p: Principal = Depends(current_principal)):
    """로그에 등장한 distinct 프로젝트명 목록(패널 필터용). project_id 가 아니라 로그의
    project_name 기준이라, 프론트가 데이터에서 직접 실제 이름을 받아 필터할 수 있게 한다.

    ⚠️ 이 목록 자체가 **전 부서 프로젝트명 노출**이므로 전사 열람 권한자에게만 연다."""
    assert_enterprise(p)
    names = []
    seen = set()
    for r in _read_records():
        p = r.get("project") or ""
        if p and p not in seen:
            seen.add(p)
            names.append(p)
    return {"status": "success", "data": names}
