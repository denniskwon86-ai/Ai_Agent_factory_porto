# ==========================================
# Supervisor 채점기 - 단계별 Rubric 평가 (V5.1)
# deterministic 검사를 먼저 코드로 평가(LLM 0콜)하고, llm_judge 항목만 Flash 1콜로 채점.
# 토론 자가검증과 Supervisor 게이트가 공유하는 SSOT.
# ==========================================
import os
import re
import json
import config
from criteria import STAGE_RUBRICS, DETERMINISTIC_CHECKS


class JudgeUnavailableError(Exception):
    """심판(judge) LLM 자체가 응답 불능인 상태 — '산출물 결함'과 반드시 구분해야 한다.
    이 예외는 노드 → LangGraph → 오케스트레이터의 일반 예외 핸들러까지 전파되어
    SPRINT_FAILED 로 방송된다(fail-loud). 0점 처리로 삼키면 멀쩡한 산출물이
    REWORK 루프를 돌며 쿼터만 태우는 오귀속이 생긴다."""
    pass


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
        # [심판 앵커링] 채점 잣대는 생성 모델과 함께 흔들리면 안 된다 — JUDGE_FORCE_HEAVY 가 켜져
        # 있으면 모든 단계의 judge 를 Pro(가용 최강) 체인으로 고정한다. (끄면 기존 동작:
        # QA/Supervisor 등 rubric 의 judge_heavy 단계만 Pro)
        judge_heavy = bool(rubric.get("judge_heavy", False)) or bool(getattr(config, "JUDGE_FORCE_HEAVY", False))
        # ⚠️ [결함 #19 계열] 심판 채점은 cacheable=False — 재작업 후 개선된 산출물에 옛 점수가
        #   재생되면 점수가 고정돼 재작업 루프가 영원히 수렴하지 못한다(매번 새로 판단해야 함).
        raw = await gateway.aexecute(state, prompt, is_heavy=judge_heavy, output_mode="json", light=True,
                                     cacheable=False)

        # [fail-loud] 심판 호출 실패(인프라 오류)는 산출물 결함이 아니다 — 예외로 표면화한다.
        from core.llm_gateway import is_llm_error_text
        if is_llm_error_text(raw):
            raise JudgeUnavailableError(f"[{stage_key}] 심판 LLM 호출 실패(인프라 오류) — 채점 불가: {str(raw)[:200]}")

        jdata = _parse_json(raw) or {}
        scores = jdata.get("scores", {}) or {}
        rationale = str(jdata.get("rationale", "") or "")

        # 비정형 응답 방어: scores 가 비면 Pro 승격 1회 재시도, 그래도 비면 판정 불가(fail-loud).
        # (조용히 전 항목 0점 처리하면 '심판 오류'가 '산출물 불합격'으로 둔갑한다)
        if not scores:
            print(f"⚠️ [Judge] {stage_key} 채점 JSON 비정형 — Pro 승격 1회 재시도")
            raw = await gateway.aexecute(state, prompt, is_heavy=True, output_mode="json", light=True,
                                         cacheable=False)  # 재시도 채점도 캐시 금지(#19 계열)
            if is_llm_error_text(raw):
                raise JudgeUnavailableError(f"[{stage_key}] 심판 재시도 실패(인프라 오류): {str(raw)[:200]}")
            jdata = _parse_json(raw) or {}
            scores = jdata.get("scores", {}) or {}
            rationale = str(jdata.get("rationale", "") or "")
            if not scores:
                raise JudgeUnavailableError(f"[{stage_key}] 심판 채점 JSON 2회 연속 파싱 실패 — 판정 불가.")
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
