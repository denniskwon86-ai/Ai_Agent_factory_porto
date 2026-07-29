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


def _judge_unavailable(state, stage_key: str, message: str) -> JudgeUnavailableError:
    """심판 불능을 **계측한 뒤** 예외 객체를 만들어 돌려준다(호출자가 raise 한다).

    ⚠️ 이것은 §8.3 의 `외부 환경` 실패다 — 산출물의 결함이 아니다. 계측에서 이 둘이 섞이면
      "게이트 실패율"이 공급자 장애로 부풀고, 그 숫자를 보고 프롬프트나 모델을 손대는
      **틀린 처방**으로 이어진다."""
    try:
        from core import quality_telemetry as _qt
        _qt.record_gate(state, gate_name=stage_key, artifact_type=stage_key,
                        verdict="FAIL",
                        root_cause=_qt.CAUSE_EXTERNAL_ENV,
                        root_cause_rule="judge_unavailable",
                        rework_reason=message[:600])
    except Exception:
        pass
    return JudgeUnavailableError(message)


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

    # ★ [2026-07-27] 판정 기준을 **등록된 업무표준(기준정보)** 에서 가져온다.
    #   기존에는 `criteria.py` 의 파이썬 상수를 직접 읽어, 기준을 바꾸려면 코드를 고쳐야 했고
    #   언제 누가 왜 바꿨는지 이력이 남지 않았다. 이제 master.db 의 `work_standard` 레코드가
    #   진실원천이며(법규처럼 버전·시행일·리니지 보존), 미등록/장애 시에만 상수로 폴백한다.
    from core.work_standard import get_standard
    rubric = get_standard(stage_key) or STAGE_RUBRICS.get(stage_key)
    if not rubric:
        return {"score": 1.0, "verdict": "PASS", "blocking_fails": [], "per_check": {}}
    _std_meta = (rubric.get("_meta") or {}) if isinstance(rubric, dict) else {}

    per_check = {}
    total_w = 0.0
    got_w = 0.0
    blocking_fails = []
    hard = set(rubric.get("hard_fail_checks", []))
    llm_checks = []
    rationale = ""

    # ★ [2026-07-27] `advisory: True` = **보고 전용 항목**.
    #   채점해서 리포트에는 남기지만 통과/반려 계산(total_w/got_w)에서는 제외하고,
    #   하드 실패도 시키지 않는다.
    #   ⚠️ 왜 필요한가: 검수 단계가 '기능이 다 되는가'와 '더 잘 만들 수 있는가'를 같은
    #     저울에 올리면, 요구가 전부 구현된 산출물도 품질 점수 미달로 반려된다.
    #     최소 기준만 관문으로 쓰고, 그 이상의 개선 여지는 상위 단계(Supervisor)와
    #     최종 고객에게 **리포트로 전달**하는 것이 옳다.
    advisory_ids = {c["id"] for c in rubric.get("checks", []) if c.get("advisory")}

    for c in rubric.get("checks", []):
        w = float(c.get("weight", 1))
        if c["id"] not in advisory_ids:
            total_w += w
        if c.get("type") == "deterministic":
            fn = DETERMINISTIC_CHECKS.get(c["id"])
            passed = False
            try:
                passed = bool(fn(state)) if fn else False
            except Exception:
                passed = False
            per_check[c["id"]] = 1.0 if passed else 0.0
            if c["id"] in advisory_ids:
                pass   # 보고 전용 — 점수/차단에 반영하지 않는다
            elif passed:
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
        # ★ [2026-07-27] 등록된 업무표준 고지문을 심판 프롬프트에 주입한다.
        #   "우리 시스템의 업무규정에 따르면 당신은 무엇을 어떤 기준값으로 판정해야 한다"를
        #   명시적으로 알려주지 않으면, 심판이 자기 취향으로 잣대를 만든다(실측: 리뷰어가
        #   코드 품질로 반려, QA·Supervisor 가 각자 기준으로 완주를 막음).
        from core.work_standard import render_standard_brief
        _std_brief = render_standard_brief(stage_key)
        prompt = (
            f"{persona_block}{judge_skill}{_std_brief}\n\n[평가 기준]:\n{checks_brief}\n\n"
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
            raise _judge_unavailable(state, stage_key,
                                     f"[{stage_key}] 심판 LLM 호출 실패(인프라 오류) — 채점 불가: {str(raw)[:200]}")

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
                raise _judge_unavailable(state, stage_key,
                                         f"[{stage_key}] 심판 재시도 실패(인프라 오류): {str(raw)[:200]}")
            jdata = _parse_json(raw) or {}
            scores = jdata.get("scores", {}) or {}
            rationale = str(jdata.get("rationale", "") or "")
            if not scores:
                # ⚠️ 이쪽은 인프라가 아니라 **출력 계약** 실패다(호출은 됐는데 형식이 안 맞았다).
                #   같은 예외 타입이라도 원인이 다르므로 분류를 분리한다.
                try:
                    from core import quality_telemetry as _qt
                    _qt.record_gate(state, gate_name=stage_key, artifact_type=stage_key,
                                    verdict="FAIL", root_cause=_qt.CAUSE_OUTPUT_CONTRACT,
                                    root_cause_rule="judge_json_parse_failed_twice",
                                    rework_reason="심판 채점 JSON 2회 연속 파싱 실패")
                except Exception:
                    pass
                raise JudgeUnavailableError(f"[{stage_key}] 심판 채점 JSON 2회 연속 파싱 실패 — 판정 불가.")
        for c in llm_checks:
            try:
                s = float(scores.get(c["id"], 0.0))
            except Exception:
                s = 0.0
            s = max(0.0, min(1.0, s))
            per_check[c["id"]] = s
            if c["id"] in advisory_ids:
                continue   # 보고 전용 — 통과/반려 계산과 차단에서 제외
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

    # ★ [2026-07-29 / 명세서 §10.3 `quality_outcomes`] 게이트 판정을 계측한다. **LLM 0콜.**
    #   여기가 유일한 채점 지점이므로(기획 단계·리뷰·QA·수용검수 전부 이 함수를 탄다) 다른 곳에
    #   같은 판정을 또 기록하면 두 통계가 어긋난다 — 계측도 SSOT 를 지킨다.
    #   ⚠️ 점수 미달의 **원인은 여기서 분류하지 않는다**(unclassified). 어느 기준이 미달인지는
    #     사실이지만 "왜 미달인지"는 이 함수가 알 수 있는 정보가 아니다. 지어내면 §8.3 통계가
    #     근거가 아니라 창작이 된다 — 사람이 사후 분류할 수 있게 outcome_id 만 남긴다.
    try:
        from core import quality_telemetry as _qt
        _failed = [k for k, v in per_check.items()
                   if v < 0.5 and k not in advisory_ids]
        _qt.record_gate(
            state, gate_name=stage_key, artifact_type=stage_key, verdict=verdict,
            score=round(score, 3), threshold=threshold,
            blocking_fails=blocking_fails, failed_checks=_failed,
            rework_reason=("미달 기준: " + ", ".join(_failed)) if _failed else "",
        )
    except Exception:
        pass   # 계측 실패가 채점을 막지 않는다

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
