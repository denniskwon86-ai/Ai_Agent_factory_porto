"""운영 계기판 — LLM 호출 텔레메트리 집계 API (Phase 4, LLM 0콜).

data/llm_call_log.jsonl (게이트웨이가 호출마다 append)을 읽어 프로젝트별로 집계한다.
핵심 축은 tier(pro/flash)가 아니라 **used(실제 모델)** — "이 산출물을 실제로 어느 제공사/모델이
만들었나"가 모델 불변성 실측의 근거이기 때문(Gemini/xAI/Groq/Cerebras/OpenRouter 구분).

안전성:
- 실행 중 append 되는 파일이라 마지막 줄이 부분 기록일 수 있음 → 줄 단위 파싱 실패는 skip(전체 폐기 금지).
- 읽기 전용 — 파이프라인 append 와 충돌 없음.
"""
# ⚠️ `asyncio` 를 빠뜨려 `/asset-hygiene` 이 500 이었다(2026-08-07 실측). 소스 문자열만
#   확인하는 테스트는 이런 실행 오류를 잡지 못한다 — 라우트는 **실제로 호출**해 봐야 한다.
import asyncio
import os
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

# ★ [2026-07-28] Phase 4 의 단기 조치(전사 열람 권한자 전용 게이트)를 해제했다.
#   그때는 로그 키가 `project_name` 뿐이어서 **부서로 매핑할 수단이 없어** 부서별 필터를 만들 수
#   없었고, 그래서 통째로 잠그는 것 말고 방법이 없었다. 이제 게이트웨이가 `owner_dept_id` 와
#   `project_id` 를 함께 남기므로(core/llm_gateway.py) 정상적인 부서 스코프로 대체한다.
#   ⚠️ 귀속 불가(구 레코드, `owner_dept_id` 없음)는 스코프 조회에서 **제외**하고 그 건수를
#     응답에 실어 보낸다 - 조용히 빼면 집계가 틀린 줄도 모르고 작아진다.
from api.deps import Principal, current_principal
from core.llm_cost import estimate_cost_usd, provider_of
from core.paths import data_path

router = APIRouter(prefix="/api/v1/telemetry", tags=["Telemetry"])

_LOG_PATH = data_path("llm_call_log.jsonl")


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
                recs.append(_backfill(r))
    except Exception:
        pass
    return recs


def _backfill(r: dict) -> dict:
    """구 레코드에 비용·제공사를 **소급 산정**한다.

    기존 로그에 이미 `used`(실제 모델)와 입·출력 토큰이 남아 있으므로, 단가표를 나중에 채워도
    과거 데이터를 되살릴 수 있다. 이것이 `core/llm_cost.py` 를 게이트웨이에서 분리한 이유다.
    ⚠️ 파일을 고쳐 쓰지 않는다 — 로그는 append-only 이고 파이프라인이 동시에 쓰는 중이다."""
    if r.get("cost_basis") is None:
        cost, basis = estimate_cost_usd(r.get("used") or "",
                                       r.get("input_tokens") or 0, r.get("output_tokens") or 0)
        r["cost_estimate_usd"] = cost
        r["cost_basis"] = basis
        r["backfilled"] = True
    if not r.get("provider"):
        r["provider"] = provider_of(r.get("used") or "")
    return r


def apply_scope(recs: list, p: Principal) -> dict:
    """부서 스코프를 적용하고 **무엇이 왜 빠졌는지**를 함께 돌려준다.

    조직 미도입/무제한(기본값 `ORG_ENFORCE=False`)이면 전량 통과 — 종전 동작과 동일하다."""
    if p.scope.unrestricted or p.scope.can_run_enterprise:
        return {"records": recs, "excluded_unattributed": 0, "excluded_other_dept": 0,
                "scope": "enterprise"}
    readable = set(p.scope.readable_dept_ids or ())
    kept, unattributed, other = [], 0, 0
    for r in recs:
        dept = str(r.get("owner_dept_id") or "")
        if not dept:
            unattributed += 1          # 귀속 불가 — 남의 부서일 수 있으므로 보여주지 않는다
        elif dept in readable:
            kept.append(r)
        else:
            other += 1
    return {"records": kept, "excluded_unattributed": unattributed,
            "excluded_other_dept": other, "scope": "dept:" + ",".join(sorted(readable))}


def aggregate(recs: list) -> dict:
    """레코드 → 집계. used(실제 모델) 분포를 1순위로."""
    totals = {"calls": 0, "ok": 0, "failed": 0, "fallback_calls": 0,
              "downgraded_calls": 0, "total_duration_s": 0.0,
              "total_input_tokens": 0, "total_output_tokens": 0,
              # ★ [2026-07-28] 비용(§10.1). `cost_usd` 는 **산정 가능한 것만의 합**이고
              #   `unpriced_calls` 가 0 이 아니면 그 합은 하한이다 — UI 가 완전한 총액으로
              #   오해하지 않도록 `cost_complete` 로 명시한다.
              "cost_usd": 0.0, "priced_calls": 0, "unpriced_calls": 0}
    by_model = {}      # used(실제 모델) → 카운트  ← 핵심 지표
    by_stage = {}      # stage → {calls, ok, avg_duration_s, models{}}
    by_requested = {}  # requested_tier → {calls, downgraded}
    by_cost_basis = {}  # cost_basis → {calls, cost_usd}  ← 무료/유료/미산정 분리
    by_provider = {}    # provider → {calls, cost_usd}
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

        # ── 비용 ──────────────────────────────────────────────────────────
        basis = r.get("cost_basis") or "unpriced"
        cost = r.get("cost_estimate_usd")
        cb = by_cost_basis.setdefault(basis, {"calls": 0, "cost_usd": 0.0})
        cb["calls"] += 1
        prov = r.get("provider") or "(none)"
        bp = by_provider.setdefault(prov, {"calls": 0, "cost_usd": 0.0})
        bp["calls"] += 1
        if cost is None:
            totals["unpriced_calls"] += 1     # 유료인데 단가 미등록 — 0 으로 삼키지 않는다
        else:
            totals["priced_calls"] += 1
            totals["cost_usd"] += float(cost)
            cb["cost_usd"] += float(cost)
            bp["cost_usd"] += float(cost)

    # 파생 지표 정리
    for s in by_stage.values():
        s["avg_duration_s"] = round(s["dur"] / s["calls"], 2) if s["calls"] else 0.0
        del s["dur"]
    for d in list(by_cost_basis.values()) + list(by_provider.values()):
        d["cost_usd"] = round(d["cost_usd"], 6)
    totals["total_duration_s"] = round(totals["total_duration_s"], 1)
    totals["success_rate"] = round(totals["ok"] / totals["calls"], 3) if totals["calls"] else 0.0
    totals["fallback_rate"] = round(totals["fallback_calls"] / totals["calls"], 3) if totals["calls"] else 0.0
    totals["cost_usd"] = round(totals["cost_usd"], 6)
    # ★ 총액을 '완전한 값'으로 제시할 수 있는지의 판정. 하나라도 미산정이면 이 합은 **하한**이다.
    totals["cost_complete"] = totals["unpriced_calls"] == 0
    # `paid_partial` 은 단가 일부만 등록된 것이라 과소 추정이다 — 총액 해석에 필요하니 노출한다.
    totals["cost_partial_calls"] = by_cost_basis.get("paid_partial", {}).get("calls", 0)

    return {"totals": totals, "by_model": by_model, "by_stage": by_stage,
            "by_requested_tier": by_requested, "by_cost_basis": by_cost_basis,
            "by_provider": by_provider}


def _scope_meta(scoped: dict) -> dict:
    """응답에 실을 권한 범위 근거(§9.3 "조회는 주체·목적·범위·권한 근거를 남긴다")."""
    return {
        "scope": scoped["scope"],
        "excluded_unattributed": scoped["excluded_unattributed"],
        "excluded_other_dept": scoped["excluded_other_dept"],
    }


@router.get("/summary")
async def telemetry_summary(project: str = "", p: Principal = Depends(current_principal)):
    """프로젝트(project_name)별 LLM 호출 집계. project 미지정 시 권한 범위 내 롤업."""
    scoped = apply_scope(_read_records(project), p)
    recs = scoped["records"]
    data = aggregate(recs)
    data["record_count"] = len(recs)
    data["project"] = project or "(전역)"
    data["permission"] = _scope_meta(scoped)
    return {"status": "success", "data": data}


@router.get("/agents")
async def telemetry_by_agent(project: str = "", p: Principal = Depends(current_principal)):
    """[D-017 §9 P4-1] **에이전트별** 호출·성공률·비용·폴백 집계.

    ★★ 응답의 `coverage` 를 무시하지 말 것. 실측(2026-08-07) 기준 전체 호출 1,133건 중
      실행 주체가 기록된 것은 113건(10%)이다 — 계측 축이 나중에 추가됐기 때문이다.
      그 상태에서 에이전트별 비용만 보면 **총비용의 10%만 보이고**, 화면에는 그럴듯한 막대가
      선다. 숫자가 있으면 사람은 그것을 전부라고 읽는다.

    ⚠️ 귀속되지 않은 호출을 버리지 않고 «(미상)» 이라는 이름으로 **같은 표에** 세운다.
      없는 것처럼 만들면 그 90%는 영원히 아무도 보지 않는다.
    ⚠️ 단가를 모르는 호출은 비용에 더하지 않는다 — 0 으로 두면 「공짜였다」는 거짓이 된다."""
    from core.agent_operations import aggregate_by_agent, failing_agents, top_cost_agents
    scoped = apply_scope(_read_records(project), p)
    data = aggregate_by_agent(scoped["records"])
    data["top_cost"] = top_cost_agents(data)
    data["low_success"] = failing_agents(data)
    data["project"] = project or "(전역)"
    data["permission"] = _scope_meta(scoped)
    return {"status": "success", "data": data}


@router.get("/orgs")
async def telemetry_by_org(project: str = "", p: Principal = Depends(current_principal)):
    """[D-017 §9 P4-2] 조직별 사용량·실패·승인 대기·정책 위반.

    ★★ **각 칸은 «값» 이 아니라 «값 + 읽었는가» 다.** 이 화면은 정의상 «무엇이 안 되어
      있는가» 를 모아 보여 주므로, 원천 하나를 못 읽었을 때 0 을 찍으면 가장 나쁜 방식으로
      틀린다 — 사람은 그것을 「승인 대기 없음」·「위반 없음」으로 읽고 안심한다.

    ⚠️ 「정책 위반 0」이 좋은 소식이 아닐 수 있다. 통제가 없어서 아무것도 거부되지 않았을
      수도 있다 — 응답의 `policy_denials.note` 가 그 가능성을 말한다.
    ⚠️ 자격은 `assert_governance_readable` 이 본다 — 이 화면은 «내 업무» 가 아니라
      «전사 정비 상태» 이고, 어디가 비어 있는지는 그 자체로 보호 대상이다."""
    from api.deps import assert_governance_readable, viewer_scope_nodes
    from core.org_operations import collect
    assert_governance_readable(p)
    scoped = apply_scope(_read_records(project), p)
    data = collect(scoped["records"], viewer_scope_nodes(p))
    data["project"] = project or "(전역)"
    data["permission"] = _scope_meta(scoped)
    return {"status": "success", "data": data}


@router.get("/asset-hygiene")
async def asset_hygiene(p: Principal = Depends(current_principal)):
    """[D-017 §9 P4-4 · 절반] 자산 중복 — **동일과 유사를 분리해서** 낸다.

    ★ 확신의 차이를 화면에서 지우면 사람은 목록 전체를 같은 무게로 읽고, 한 번 잘못 지우면
      다시는 이 목록을 쓰지 않는다(사용자 결정 2026-08-07 안 B).

    ⚠️⚠️ **「미사용」은 제공하지 않는다.** 자산에 사용 이력 필드가 없고 실행 로그의 에이전트
      귀속률이 8% 다. 이 상태에서 「호출 0건 = 미사용」이라고 제안하면 관측되지 않았을 뿐인
      자산을 지우라고 말하게 된다 — `unused.note` 가 그 사실을 말한다.
      **빈 목록으로 두지 않는다**(빈 목록은 「정리할 것이 없다」로 읽힌다).

    ⚠️ LLM 0콜이다(§6.1 「단순 LLM 평가 금지」). 의미 비교를 하지 않는 이유는 근거를 설명할 수
      없는 삭제 제안은 아무도 실행하지 않기 때문이다."""
    from api.deps import assert_governance_readable
    from core.asset_dedup import find_duplicates
    assert_governance_readable(p)
    data = await asyncio.to_thread(find_duplicates)
    return {"status": "success", "data": data}


@router.get("/raw")
async def telemetry_raw(project: str = "", limit: int = 200,
                        p: Principal = Depends(current_principal)):
    """최근 N건 원시 레코드(디버그/타임라인용)."""
    scoped = apply_scope(_read_records(project), p)
    recs = scoped["records"]
    return {"status": "success", "data": recs[-max(1, min(limit, 2000)):],
            "permission": _scope_meta(scoped)}


# ── 품질 결과(§10.3 `quality_outcomes` / §8.3 실패 원인) ─────────────────────
# ⚠️ 왜 `llm_calls` 와 같은 라우터에 두는가: 두 로그는 같은 식별 규약(project/project_id/
#   owner_dept_id)을 쓰고 **같은 부서 스코프 규칙**을 타야 한다. 권한 판정을 두 곳에 두면
#   한쪽만 고쳐졌을 때 조용히 새는 경로가 생긴다(이 프로젝트에서 실제로 겪은 유형).

@router.get("/quality/summary")
async def quality_summary(project: str = "", p: Principal = Depends(current_principal)):
    """게이트별 통과/실패·재작업 횟수·실패 원인 분포·사람 수용 판정 집계.

    ⚠️ 응답의 `unclassified_failures` 와 `human_acceptance.no_human_decision` 은
      **좋은 소식이 아니라 결손**이다 — 각각 "원인을 아직 모른다", "사람이 판단하지 않았다"이며
      통과·승인 쪽에 합산하면 안 된다(응답 `note` 에 같은 문구를 실어 보낸다)."""
    from core import quality_telemetry as qt
    events = qt.read_events(project)
    scoped = apply_scope(events, p)
    outcomes = qt.resolve_outcomes(scoped["records"])
    data = qt.aggregate(outcomes)
    data["project"] = project or "(전역)"
    data["permission"] = _scope_meta(scoped)
    return {"status": "success", "data": data}


@router.get("/quality/raw")
async def quality_raw(project: str = "", limit: int = 200,
                      p: Principal = Depends(current_principal)):
    """접합된 품질 결과 레코드(§10.3 한 줄 형태). 최근 것부터."""
    from core import quality_telemetry as qt
    scoped = apply_scope(qt.read_events(project), p)
    outcomes = qt.resolve_outcomes(scoped["records"])
    outcomes.sort(key=lambda r: r.get("ts") or "", reverse=True)
    return {"status": "success", "data": outcomes[:max(1, min(limit, 2000))],
            "permission": _scope_meta(scoped)}


@router.get("/quality/unclassified")
async def quality_unclassified(project: str = "", limit: int = 50,
                               p: Principal = Depends(current_principal)):
    """원인이 분류되지 않은 실패 목록 — 사람이 분류해야 할 작업 큐."""
    from core import quality_telemetry as qt
    scoped = apply_scope(qt.read_events(project), p)
    outcomes = qt.resolve_outcomes(scoped["records"])
    items = qt.unclassified_failures(outcomes, limit=max(1, min(limit, 500)))
    return {"status": "success", "data": items,
            "causes": list(qt.CAUSES),
            "permission": _scope_meta(scoped)}


class QualityClassifyRequest(BaseModel):
    outcome_id: str
    root_cause: str
    note: str = ""


@router.post("/quality/classify")
async def quality_classify(req: QualityClassifyRequest,
                           p: Principal = Depends(current_principal)):
    """사람이 미분류 실패에 §8.3 원인을 지정한다.

    **식별 없는 분류는 받지 않는다**(401). 원인 통계는 이후 모델·프롬프트·테스트 투자 방향을
    바꾸는 근거가 되므로, 누가 그렇게 판단했는지가 값과 함께 남아야 한다 — 외부 인텔리전스
    원천 승인에 승인자 식별을 요구한 것과 같은 이유다."""
    from core import quality_telemetry as qt
    if not p.user_id:
        raise HTTPException(status_code=401, detail="분류자 식별 정보가 없습니다.")
    if req.root_cause not in qt.ASSIGNABLE_CAUSES:
        raise HTTPException(status_code=400,
                            detail=f"허용되지 않은 원인 값입니다. 가능: {', '.join(qt.ASSIGNABLE_CAUSES)}")
    # ★ 볼 수 없는 부서의 실패를 분류할 수 없다. 읽기 스코프를 그대로 쓰기 판정에 재사용한다
    #   (조회는 되는데 쓰기만 열려 있으면 스코프가 두 벌이 되어 어긋난다).
    visible = apply_scope(qt.read_events(), p)["records"]
    if not any(e.get("event") == "gate" and e.get("outcome_id") == req.outcome_id for e in visible):
        raise HTTPException(status_code=404, detail="해당 품질 결과를 찾을 수 없거나 볼 권한이 없습니다.")
    ok = qt.record_classification(req.outcome_id, req.root_cause, actor=p.user_id, note=req.note)
    if not ok:
        raise HTTPException(status_code=400, detail="분류를 기록하지 못했습니다(outcome_id 확인).")
    return {"status": "success", "data": {"outcome_id": req.outcome_id,
                                          "root_cause": req.root_cause, "actor": p.user_id}}


@router.get("/projects")
async def telemetry_projects(p: Principal = Depends(current_principal)):
    """로그에 등장한 distinct 프로젝트 목록(패널 필터용).

    ⚠️ 이 목록 자체가 프로젝트명 노출이므로 **권한 범위 안의 것만** 돌려준다. Phase 4 는
      부서 매핑 수단이 없어 전사 열람 권한자에게만 열었는데, 이제 레코드에 `owner_dept_id` 가
      있으므로 부서 스코프로 정상화한다. 집계 축이 `project_name` 이므로 이름을 1급으로 유지하되
      `project_id` 도 함께 준다(이름은 바뀔 수 있고 중복될 수 있다)."""
    scoped = apply_scope(_read_records(), p)
    items, seen = [], set()
    for r in scoped["records"]:
        name = r.get("project") or ""
        if not name or name in seen:
            continue
        seen.add(name)
        items.append({"project": name, "project_id": r.get("project_id") or "",
                      "owner_dept_id": r.get("owner_dept_id") or ""})
    return {"status": "success", "data": items, "permission": _scope_meta(scoped)}
