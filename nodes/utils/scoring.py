# ==========================================
# Supervisor 채점기 — 단계별 Rubric 평가 (V5.1)
# deterministic 검사를 먼저 코드로 평가(LLM 0콜)하고, llm_judge 항목만 Flash 1콜로 채점.
# 토론 자가검증과 Supervisor 게이트가 공유하는 SSOT.
# ==========================================
import os
import re
import json
import config
from criteria import STAGE_RUBRICS, DETERMINISTIC_CHECKS


def _load_skill(role_name: str) -> str:
    path = f"skills/{role_name}.md"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def _parse_json(text):
    try:
        s = str(text).strip()
        m = re.search(r'(\{[\s\S]*\})', s)
        if m:
            s = m.group(1)
        return json.loads(s)
    except Exception:
        return {}


_STAGE_ARTIFACT_FIELD = {
    "PLANNING": "prd_summary",
    "ARCHITECTURE": "architecture_summary",
    "TECH_SPEC": "tech_spec_summary",
}


def _stage_artifact(state, stage_key: str) -> str:
    if stage_key == "CODE_REVIEW":
        fe = getattr(state, "frontend_code_summary", "") or ""
        be = getattr(state, "backend_code_summary", "") or ""
        return (fe + "\n\n" + be).strip()
    field = _STAGE_ARTIFACT_FIELD.get(stage_key)
    if field:
        return getattr(state, field, "") or ""
    return ""


async def score_stage(state, stage_key: str) -> dict:
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
        checks_brief = "\n".join([f'- {c["id"]}: {c["desc"]}' for c in llm_checks])
        artifact = _stage_artifact(state, stage_key)
        prompt = (
            f"{judge_skill}\n\n[평가 기준]:\n{checks_brief}\n\n"
            f"[검토 산출물]:\n{artifact}\n\n"
            '아래 JSON만 출력하라(각 기준 0.0~1.0 점수 + 통과/미흡 사유 한 줄 총평): '
            '{"scores": {"기준id": 0.0}, "rationale": "한 줄 판단 근거"}'
        )
        raw = await gateway.aexecute(state, prompt, is_heavy=False, output_mode="json", light=True)
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
    threshold = config.STAGE_PASS_THRESHOLDS.get(stage_key, 0.7)

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
