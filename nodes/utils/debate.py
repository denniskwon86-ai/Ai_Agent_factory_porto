# ==========================================
# 다중 에이전트 토론·합의 루프 + Supervisor 게이트 헬퍼 — V5.1
# 노드 내부 서브루프(generate -> critique -> revise)로 동작하므로
# LangGraph 사이클을 0개 추가한다(interrupt_after / MemorySaver 무영향).
# ==========================================
import os
import re
import json
import config
from criteria import STAGE_RUBRICS


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


def _is_llm_error(text) -> bool:
    return isinstance(text, str) and ("LLM API LIMIT ERROR" in text or "LLM UNKNOWN ERROR" in text)


def _rubric_brief(stage_key: str) -> str:
    rubric = STAGE_RUBRICS.get(stage_key, {})
    lines = [f'- {c["id"]}: {c["desc"]}' for c in rubric.get("checks", [])]
    return "\n".join(lines) if lines else "- (정의된 기준 없음)"


STAGE_LABELS = {
    "RFP": "요구정의(RFP)",
    "PLANNING": "기획(PRD)",
    "ARCHITECTURE": "아키텍처",
    "TECH_SPEC": "기술명세",
}


async def _emit(state_obj, stage_key: str, phase: str, round_no: int = 0, detail: str = "", meta=None):
    """토론·채점 진행 상황을 SSE로 실시간 생중계 + 피드 파일에 영속화(새로고침 복구용).
    실패해도 파이프라인에 영향 없음."""
    ws = getattr(state_obj, "workspace_root", "") or ""
    payload = {
        "agent": "Supervisor",
        "project_id": os.path.basename(str(ws).rstrip("/\\")),
        "stage": stage_key,
        "stage_label": STAGE_LABELS.get(stage_key, stage_key),
        "phase": phase,
        "round": round_no,
        "detail": detail or f"{STAGE_LABELS.get(stage_key, stage_key)} {phase}",
        "meta": meta or {},
    }
    # 1) 실시간 브로드캐스트
    try:
        from core.broadcaster import factory_broadcaster
        await factory_broadcaster.broadcast("AGENT_ACTIVITY", payload)
    except Exception:
        pass
    # 2) 피드 파일 영속화 (새로고침/재접속 복구)
    try:
        ws = getattr(state_obj, "workspace_root", "") or ""
        if ws:
            from datetime import datetime
            rec = dict(payload)
            rec["ts"] = datetime.now().isoformat()
            fp = os.path.join(ws, "supervisor_feed.json")
            feed = []
            if os.path.exists(fp):
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        feed = json.load(f)
                except Exception:
                    feed = []
            feed.append(rec)
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(feed[-200:], f, ensure_ascii=False)
    except Exception:
        pass


def _build_feedback(result: dict) -> str:
    parts = []
    if result.get("blocking_fails"):
        parts.append("치명 미달 항목: " + ", ".join(result["blocking_fails"]))
    pc = result.get("per_check", {}) or {}
    low = [k for k, v in pc.items() if v < 0.7]
    if low:
        parts.append("보완 필요 항목: " + ", ".join(low))
    parts.append(f"현재 점수 {result.get('score', 0.0)} / 판정 {result.get('verdict', '')}")
    return " / ".join(parts)


_STAGE_SUMMARY_FIELD = {
    "RFP": "rfp_summary",
    "PLANNING": "prd_summary",
    "ARCHITECTURE": "architecture_summary",
    "TECH_SPEC": "tech_spec_summary",
}


async def run_debate(state_obj, author_skill: str, stage_key: str, rounds: int = None, extra_instruction: str = "") -> tuple:
    """초안 생성 -> (비평 -> 개정) 반복. 합의(치명 결함 0) 시 조기 종료. (최종텍스트, 소진라운드) 반환."""
    from core.llm_gateway import gateway
    rounds = rounds or config.DEBATE_MAX_ROUNDS
    persona = config.STAGE_CRITIC_PERSONAS.get(stage_key, "엄정한 기술 검토자")
    author_prompt = _load_skill(author_skill) + (extra_instruction or "")
    critic_skill = _load_skill("critic_skill")
    rubric_brief = _rubric_brief(stage_key)

    label = STAGE_LABELS.get(stage_key, stage_key)

    # 1) 초안 생성 (Pro, 문서 모드 — strict_json files 스키마 강제 회피)
    await _emit(state_obj, stage_key, "draft", 0, f"{label} 초안을 작성하도록 담당 에이전트를 투입했습니다.")
    draft = await gateway.aexecute(state_obj, author_prompt, is_heavy=True, output_mode="document")
    if _is_llm_error(draft):
        return draft, 0

    rounds_used = 0
    for r in range(rounds):
        critic_prompt = (
            f"{critic_skill}\n\n"
            f"[당신의 비평가 페르소나]: {persona}\n\n"
            f"[평가 기준(rubric)]:\n{rubric_brief}\n\n"
            f"[검토 대상 산출물]:\n{draft}\n\n"
            "위 기준에 비추어 결함을 적대적으로 지적하라. 반드시 아래 JSON만 출력:\n"
            '{"checks": [{"id": "기준id", "pass": true, "severity": "blocking|major|minor", "evidence": "근거"}], "verdict_blocking": false}'
        )
        # 비평가는 항상 Flash + 경량 컨텍스트(요약만)로 비용 억제
        await _emit(state_obj, stage_key, "critique", r + 1, f"{label} 산출물을 '{persona}' 관점으로 검토 중입니다. (비평 {r + 1}R)")
        critique_raw = await gateway.aexecute(state_obj, critic_prompt, is_heavy=False, output_mode="json", light=True)
        rounds_used += 1
        if _is_llm_error(critique_raw):
            break
        cdata = _parse_json(critique_raw)
        checks = cdata.get("checks", []) or []
        blocking = cdata.get("verdict_blocking")
        if blocking is None:
            blocking = any(
                (str(c.get("severity", "")).lower() in ("blocking", "high", "major")) and not c.get("pass", False)
                for c in checks
            )
        # 비평 결과(실제 지적 내용)를 콘솔로 송출
        issues = [c for c in checks if not c.get("pass", True)]
        if issues:
            brief = "; ".join([f"[{c.get('id', '')}] {str(c.get('evidence', '')).strip()}"[:90] for c in issues[:3]])
            crit_detail = f"{label} 비평 결과 — 결함 {len(issues)}건: {brief}"
        else:
            crit_detail = f"{label} 비평 결과 — 치명 결함 없음, 합의 도달."
        await _emit(state_obj, stage_key, "critique_result", r + 1, crit_detail, meta={"checks": checks, "blocking": bool(blocking)})
        if not blocking:
            break  # 합의 성립 → 조기 종료
        if r < rounds - 1:
            feedback = json.dumps(checks, ensure_ascii=False, indent=2)
            revise_prompt = (
                f"{author_prompt}\n\n"
                f"[직전 초안]:\n{draft}\n\n"
                f"[비평가 지적 사항 — 모두 반영하여 개정]:\n{feedback}\n\n"
                "지적된 결함을 모두 해소한 개정 산출물 전체를 작성하라. 축약·생략 금지."
            )
            await _emit(state_obj, stage_key, "revise", r + 1, f"{label} 담당 에이전트에게 비평을 반영해 개정하도록 지시했습니다. (개정 {r + 1}R)")
            revised = await gateway.aexecute(state_obj, revise_prompt, is_heavy=True, output_mode="document")
            if _is_llm_error(revised):
                break
            draft = revised
    return draft, rounds_used


async def run_single_revision(state_obj, author_skill: str, prev_text: str, feedback: str, extra_instruction: str = "") -> str:
    from core.llm_gateway import gateway
    prompt = (
        f"{_load_skill(author_skill)}{extra_instruction or ''}\n\n"
        f"[직전 산출물]:\n{prev_text}\n\n"
        f"[Supervisor 기준 미달 지적]:\n{feedback}\n\n"
        "지적을 모두 반영하여 개정 산출물 전체를 작성하라. 축약·생략 금지."
    )
    return await gateway.aexecute(state_obj, prompt, is_heavy=True, output_mode="document")


async def run_supervised_stage(state_obj, author_skill: str, stage_key: str, extra_instruction: str = "") -> tuple:
    """토론으로 산출물을 합의하고 Supervisor 기준으로 채점·재작업한 뒤, 상태 업데이트 dict를 반환한다.
    반환: (updates_dict, score_result)
    """
    from nodes.utils.scoring import score_stage
    field = _STAGE_SUMMARY_FIELD.get(stage_key)
    label = STAGE_LABELS.get(stage_key, stage_key)

    artifact, rounds_used = await run_debate(state_obj, author_skill, stage_key, extra_instruction=extra_instruction)
    if field:
        setattr(state_obj, field, artifact)

    rubric_ids = [c["id"] for c in STAGE_RUBRICS.get(stage_key, {}).get("checks", [])]
    await _emit(state_obj, stage_key, "scoring", 0,
                f"{label} 합의안을 제 기준으로 평가합니다. 평가 기준: {', '.join(rubric_ids) or '없음'}",
                meta={"rubric": rubric_ids})
    result = await score_stage(state_obj, stage_key)
    attempts = dict(getattr(state_obj, "stage_attempt_counts", {}) or {})
    used = attempts.get(stage_key, 0)

    # Supervisor 게이트: 기준 미달 시 in-node 재작업 (한도 내)
    while result.get("verdict") != "PASS" and used < config.MAX_STAGE_REWORKS:
        used += 1
        feedback = _build_feedback(result)
        artifact = await run_single_revision(state_obj, author_skill, artifact, feedback, extra_instruction=extra_instruction)
        if _is_llm_error(artifact):
            break
        if field:
            setattr(state_obj, field, artifact)
        result = await score_stage(state_obj, stage_key)

    attempts[stage_key] = used
    scores = dict(getattr(state_obj, "stage_scores", {}) or {})
    scores[stage_key] = result.get("score", 0.0)
    rounds_map = dict(getattr(state_obj, "debate_rounds_used", {}) or {})
    rounds_map[stage_key] = rounds_used
    crit_log = list(getattr(state_obj, "criteria_log", []) or [])
    crit_log.append({
        "stage": stage_key,
        "score": result.get("score", 0.0),
        "verdict": result.get("verdict", "PASS"),
        "blocking_fails": result.get("blocking_fails", []),
        "attempts": used,
    })

    passed = result.get("verdict") == "PASS"
    pc = result.get("per_check", {}) or {}
    pc_brief = ", ".join([f"{k}={v}" for k, v in list(pc.items())[:6]])
    rationale = result.get("rationale", "")
    verdict = result.get("verdict", "PASS")
    verdict_ko = {"PASS": "통과", "REWORK": "재작업", "ROLLBACK": "전단계 회송"}.get(verdict, verdict)
    scored_detail = (
        f"{label} 평가 완료 → 점수 {result.get('score')} / 판정 {verdict_ko}"
        + (f" · 기준별: {pc_brief}" if pc_brief else "")
        + (f" · 판단: {rationale}" if rationale else "")
    )
    await _emit(state_obj, stage_key, "scored", used, scored_detail,
                meta={"per_check": pc, "verdict": verdict, "score": result.get("score"),
                      "rationale": rationale, "blocking_fails": result.get("blocking_fails", [])})
    updates = {
        "current_stage": stage_key,
        "stage_attempt_counts": attempts,
        "stage_scores": scores,
        "debate_rounds_used": rounds_map,
        "criteria_log": crit_log,
        "supervisor_feedback": "" if passed else _build_feedback(result),
    }
    if field:
        updates[field] = artifact
    # 재작업 한도 초과로도 미달 → 인간 개입 신호(기존 HOTL 중단점에서 노출)
    if not passed and config.ON_STAGE_LIMIT_EXCEEDED == "HOTL":
        updates["needs_revision"] = True
    return updates, result
