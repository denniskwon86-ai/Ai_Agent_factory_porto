# ==========================================
# Supervisor 채점기 - 단계별 Rubric 평가 (V5.1)
# deterministic 검사를 먼저 코드로 평가(LLM 0콜)하고, llm_judge 항목만 Flash 1콜로 채점.
# 토론 자가검증과 Supervisor 게이트가 공유하는 SSOT.
# ==========================================
import os
import re
import json
from criteria import STAGE_RUBRICS, DETERMINISTIC_CHECKS


def _load_skill(role_name: str) -> str:
    path = f"skills/{role_name}.md"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def _parse_json(text):
    # 관대한 파서로 위임 - judge 채점 JSON이 비정형이어도 점수가 0으로 유실되지 않도록
    from nodes.utils.json_utils import loads_lenient
    return loads_lenient(text)


_STAGE_ARTIFACT_FIELD = {
    "RFP": "rfp_summary",
    "PLANNING": "prd_summary",
    "ARCHITECTURE": "architecture_summary",
    "TECH_SPEC": "tech_spec_summary",
}


def _stage_artifact(state, stage_key: str) -> str:
    fe = getattr(state, "frontend_code_summary", "") or ""
    be = getattr(state, "backend_code_summary", "") or ""
    code = (fe + "\n\n" + be).strip()
    if stage_key == "CODE_REVIEW":
        return code
    if stage_key == "QA":
        # 수행사 통합검수: 코드 + 설계서(PRD/아키텍처/기술명세) 대조
        prd = getattr(state, "prd_summary", "") or ""
        arch = getattr(state, "architecture_summary", "") or ""
        tech = getattr(state, "tech_spec_summary", "") or ""
        return (f"[기획서(PRD)]\n{prd}\n\n[아키텍처]\n{arch}\n\n[기술명세]\n{tech}\n\n[구현 코드]\n{code}").strip()
    if stage_key == "SUPERVISOR":
        # 고객사 수용검수: 코드(결과물) + RFP(계약) 대조
        rfp = getattr(state, "rfp_summary", "") or ""
        prd = getattr(state, "prd_summary", "") or ""
        return (f"[요구사항 정의서(RFP) - 계약]\n{rfp or '(RFP 없음 - PRD 기준)'}\n\n[기획서(PRD)]\n{prd}\n\n[구현 결과물 코드]\n{code}").strip()
    field = _STAGE_ARTIFACT_FIELD.get(stage_key)
    if field:
        return getattr(state, field, "") or ""
    return ""


async def score_stage(state, stage_key: str, extra_context: str = "") -> dict:
    """단계 산출물을 rubric으로 채점하고 verdict(PASS/REWORK/ROLLBACK)를 결정한다."""
    from core.llm_gateway import gateway  # 순환 임포트 방지를 위한 지연 임포트

    rubric = STAGE_RUBRICS.get(stage_key)
    if not rubric:
        return {"score": 1.0, "verdict": "PASS", "blocking_fails": [], "per_check": {}}

    per_check = {}
    total_w = 0.0
    got_w = 0.0
    blocking_fails = []
    hard = set(rubric.get("hard_fail_checks", []))
    llm_checks = []
    rationale = ""

    for c in rubric.get("checks", []):
        w = float(c.get("weight", 1))
        total_w += w
        if c.get("type") == "deterministic":
            fn = DETERMINISTIC_CHECKS.get(c["id"])
            passed = False
            try:
                passed = bool(fn(state)) if fn else False
            except Exception:
                passed = False
            per_check[c["id"]] = 1.0 if passed else 0.0
            if passed:
                got_w += w
            elif c["id"] in hard:
                blocking_fails.append(c["id"])
        else:
            llm_checks.append(c)

    if llm_checks:
        judge_skill = _load_skill("judge_skill")
        # 단계별 평가 페르소나(QA=수행사 검수자 / Supervisor=고객사 대리인)를 judge 프롬프트에 주입 - 관점 차등
        persona = _load_skill(rubric.get("judge_persona", "")) if rubric.get("judge_persona") else ""
        persona_block = (persona + "\n\n") if persona else ""
        checks_brief = "\n".join([f'- {c["id"]}: {c["desc"]}' for c in llm_checks])
        artifact = _stage_artifact(state, stage_key)
        if extra_context:
            artifact += f"\n\n{extra_context}"
        prompt = (
            f"{persona_block}{judge_skill}\n\n[평가 기준]:\n{checks_brief}\n\n"
            f"[검토 산출물]:\n{artifact}\n\n"
            '아래 JSON만 출력하라(각 기준 0.0~1.0 점수 + 통과/미흡 사유 한 줄 총평): '
            '{"scores": {"기준id": 0.0}, "rationale": "한 줄 판단 근거"}'
        )
        # QA·Supervisor 같은 고위험 수용검수는 Pro judge로 엄격 채점(rubric의 judge_heavy), 그 외는 Flash 경량.
        judge_heavy = bool(rubric.get("judge_heavy", False))
        raw = await gateway.aexecute(state, prompt, is_heavy=judge_heavy, output_mode="json", light=True)
        jdata = _parse_json(raw)
        scores = jdata.get("scores", {}) or {}
        rationale = str(jdata.get("rationale", "") or "")
        for c in llm_checks:
            try:
                s = float(scores.get(c["id"], 0.0))
            except Exception:
                s = 0.0
            s = max(0.0, min(1.0, s))
            per_check[c["id"]] = s
            got_w += float(c.get("weight", 1)) * s
            if s < 0.5 and c["id"] in hard:
                blocking_fails.append(c["id"])

    score = (got_w / total_w) if total_w > 0 else 1.0
    # 통과 임계는 rubric(criteria.py)을 단일 진실원천으로 사용 (config 중복 제거 - SSOT 단일화)
    threshold = rubric.get("pass_threshold", 0.7)

    if blocking_fails:
        verdict = "ROLLBACK"
    elif score < threshold:
        verdict = "REWORK"
    else:
        verdict = "PASS"

    # 판단 근거(rationale): LLM 총평이 없으면(결정론 전용 단계) 코드 검사 결과로 한 줄 생성
    if not rationale:
        passed_ids = [k for k, v in per_check.items() if v >= 0.5]
        failed_ids = [k for k, v in per_check.items() if v < 0.5]
        rationale = f"기준 {len(per_check)}개 중 {len(passed_ids)}개 충족" + (f", 미달: {', '.join(failed_ids)}" if failed_ids else "")

    return {
        "score": round(score, 3),
        "verdict": verdict,
        "blocking_fails": blocking_fails,
        "per_check": per_check,
        "rationale": rationale,
    }
