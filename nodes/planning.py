import os
import json
import re
import config
from typing import Dict, Any
from state_models import ProjectState
from core.llm_gateway import gateway, is_llm_error_text
from core.agent_registry import agent_skill
from nodes.utils.wbs_manager import WBSManager

def _load_skill(role_name: str) -> str:
    path = f"skills/{role_name}.md"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f: return f.read()
    return ""

def _extract_code_from_ssot(json_str: str) -> str:
    try:
        data = json.loads(json_str)
        files = data.get("files", [])
        if files and isinstance(files, list): return files[0].get("code", "")
    except Exception: pass
    return ""

async def run_rfp_analyst(state: Any) -> Dict[str, Any]:
    """요구사항 정의서(RFP) 작성 - 기획(PM) 이전에 '무엇을·왜'를 확정하는 기준 계약.
    RFP HOTL 게이트에서 사용자가 피드백을 주면(route_from_rfp 가 여기로 되돌림) 그 피드백을
    재작성 지시로 주입해 RFP 자체를 고친다(다음 단계 PRD 로 새지 않도록)."""
    state_obj = ProjectState.model_validate(state)

    # HOTL 피드백 흡수: 게이트웨이/ContextEngine 은 human_feedback_queue 를 LLM 에 전달하지 않으므로,
    # 최신 피드백을 extra_instruction 으로 직접 합성하는 것이 RFP 재작성에 반영하는 유일한 통로.
    _fb_items = getattr(state_obj, "human_feedback_queue", []) or []
    _latest = _fb_items[-1] if _fb_items else None
    _latest_fb = (_latest.get("feedback", "") if isinstance(_latest, dict) else getattr(_latest, "feedback", "")) or ""

    _clar_qs = getattr(state_obj, "clarification_questions", []) or []
    _clar_sum = (getattr(state_obj, "clarification_summary", "") or "").strip()
    _new_clar_sum = ""
    _extra = ""
    if _clar_qs and not _clar_sum and _latest_fb.strip():
        # 요구 확인 인터뷰(선택형 질문) 답변 최초 소비: RFP 입력으로 주입 + 이후 단계(PRD) 참조용 영속화
        _new_clar_sum = _latest_fb.strip()
        _extra = (f"\n\n[ 사용자 요구 확인(인터뷰) 결과 - 아래 선택/답변을 RFP(요구정의서)에 반드시 반영하십시오]:\n{_new_clar_sum}")
        print(f" [RFP Analyst] 요구 확인 인터뷰 답변 반영해 RFP 작성: {_new_clar_sum[:80]}")
    elif _latest_fb.strip():
        _extra = (f"\n\n[ 사용자 피드백 - RFP(요구정의서)를 이 피드백에 맞게 반드시 수정/반영해 재작성하십시오. "
                  f"다음 단계(기획서)로 미루지 말 것]:\n{_latest_fb.strip()}")
        print(f" [RFP Analyst] 사용자 피드백 반영해 RFP 재작성: {_latest_fb.strip()[:80]}")
    else:
        print(" [Agent] RFP Analyst - 토론·합의 기반 요구사항 정의서(RFP) 작성 중...")

    # 재작성 루프에서도 인터뷰에서 확정한 방향이 유실되지 않도록 항상 참조로 동봉
    if _clar_sum:
        _extra += f"\n\n[참조: 사용자 요구 확인(인터뷰) 결과 - 이 확정 방향과 모순되지 않게 작성하십시오]:\n{_clar_sum}"

    from nodes.utils.debate import run_supervised_stage
    updates, result = await run_supervised_stage(state_obj, agent_skill("RFP_Analyst", "rfp_skill", template_id=state_obj.template_id), "RFP", extra_instruction=_extra)
    print(f"[OK] [Agent] RFP 요구정의 완료 - 점수 {result.get('score')} / 판정 {result.get('verdict')}")
    # 재진입 시 다시 Master_PM 으로 흐르도록 needs_revision 리셋 + 소비한 피드백 큐 비움(다음 단계 재적용 방지)
    updates["needs_revision"] = False
    updates["human_feedback_queue"] = []
    if _new_clar_sum:
        updates["clarification_summary"] = _new_clar_sum
    return updates

async def run_master_pm(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)
    
    #  [PM 상신 루프] 리뷰어가 기획 모순으로 판단하여 PM을 호출한 경우
    if getattr(state_obj, "reviewer_decision", "") == "ESCALATE_PM":
        print("⚖️ [Agent] Master PM: Reviewer의 기획 모순 에스컬레이션 검토 중...")
        prompt = _load_skill(agent_skill("Master_PM", "pm_skill", template_id=state_obj.template_id))
        prompt += (
            f"\n\n[ Reviewer 결재 상신 내용 (ESCALATE_PM)]:\n{state_obj.reviewer_feedback}\n\n"
            "당신은 프로젝트의 총괄 PM입니다. 코드 리뷰어가 기획서의 논리적 모순이나 위배 사항을 보고했습니다.\n"
            "1. 만약 이 지적사항이 전체 흐름상 무시해도 좋다면 응답을 반환하는 JSON 데이터 내에 `\"decision\": \"REJECT\"`로 적고 `\"reason\": \"사유\"`를 명시하십시오.\n"
            "2. 만약 기획 보완이 필요하다면 `\"decision\": \"ACCEPT\"`로 적고, `\"prd_summary\": \"보완된 PRD 내용\"`을 작성하십시오.\n"
            "응답은 반드시 아래 JSON 포맷을 준수하십시오:\n"
            "\x60\x60\x60json\n"
            "{\n"
            "  \"decision\": \"REJECT\" 또는 \"ACCEPT\",\n"
            "  \"reason\": \"(REJECT일 경우 기각 사유)\",\n"
            "  \"prd_summary\": \"(ACCEPT일 경우 수정된 PRD)\"\n"
            "}\n"
            "\x60\x60\x60"
        )
        output = await gateway.aexecute(state_obj, prompt, is_heavy=True, output_mode="json")

        try:
            clean_str = output.strip()
            md_match = re.search(r'\x60{3}(?:json)?\s*(\{[\s\S]*?\})\s*\x60{3}', clean_str)
            if md_match: clean_str = md_match.group(1)
            else:
                bracket_match = re.search(r'(\{[\s\S]*\})', clean_str)
                if bracket_match: clean_str = bracket_match.group(1)
            data = json.loads(clean_str)
            
            if data.get("decision") == "REJECT":
                print("[OK] [PM Decision] PM이 피드백을 기각(Override)했습니다. 개발팀에 강행을 지시합니다.")
                return {
                    "reviewer_decision": "PASS", # 결재 완료 처리
                    "pm_override_reason": data.get("reason", "PM 판단하에 무시 진행"), 
                    "needs_revision": False
                }
            else:
                print(" [PM Decision] PM이 피드백을 수용(ACCEPT)했습니다. PRD를 업데이트하고 개발팀 재작업(Rework)을 지시합니다.")
                return {
                    "reviewer_decision": "REWORK_DEV", # 개발팀으로 루프 반환
                    "pm_override_reason": "",
                    "needs_revision": True,
                    "prd_summary": data.get("prd_summary", state_obj.prd_summary)
                }
        except Exception as e:
            print(f"⚠️ PM 의사결정 파싱 실패, 강제 승인으로 폴백: {e}")
            return {"reviewer_decision": "PASS", "pm_override_reason": "PM 자동 강행 폴백"}

    else:
        # 요구 확인 인터뷰에서 사용자가 선택으로 확정한 방향을 PRD 에도 직접 주입
        _extra = ""
        _clar_sum = (getattr(state_obj, "clarification_summary", "") or "").strip()
        if _clar_sum:
            _extra = f"\n\n[참조: 사용자 요구 확인(인터뷰) 결과 - 기획서(PRD)에 반드시 반영하십시오]:\n{_clar_sum}"

        # PRD 게이트에서 사용자가 피드백을 준 경우(route_from_pm 자기루프) 재작성 지시로 소비
        _fb_items = getattr(state_obj, "human_feedback_queue", []) or []
        _latest = _fb_items[-1] if _fb_items else None
        _latest_fb = (_latest.get("feedback", "") if isinstance(_latest, dict) else getattr(_latest, "feedback", "")) or ""
        if _latest_fb.strip():
            _extra += (f"\n\n[ 사용자 피드백 - 기획서(PRD)를 이 피드백에 맞게 반드시 수정/반영해 재작성하십시오. "
                       f"다음 단계로 미루지 말 것]:\n{_latest_fb.strip()}")
            print(f" [Master PM] 사용자 피드백 반영해 PRD 재작성: {_latest_fb.strip()[:80]}")
        else:
            print(" [Agent] Master PM 토론·합의 기반 기획(PRD) 진행 중...")

        from nodes.utils.debate import run_supervised_stage
        updates, result = await run_supervised_stage(state_obj, agent_skill("Master_PM", "pm_skill", template_id=state_obj.template_id), "PLANNING", extra_instruction=_extra)
        print(f"[OK] [Agent] Master PM 기획 완료 - 점수 {result.get('score')} / 판정 {result.get('verdict')}")
        updates["needs_revision"] = False
        if _latest_fb.strip():
            updates["human_feedback_queue"] = []  # 소비한 피드백 비움(후속 단계 재적용 방지)
        return updates

async def run_master_pmo(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)
    
    print(" [Agent] Master PMO 비동기 WBS 분할 및 에이전트 스케줄링 진행 중...")
    prompt = _load_skill(agent_skill("Master_PMO", "pmo_skill", template_id=state_obj.template_id))
    prompt += f"\n\n[참조: Master PM이 작성한 PRD]\n{state_obj.prd_summary}"
    # 아키텍처는 기획 단계(UI 승인 직후)에서 이미 확정됨 — WBS 분할의 입력으로 주입
    if (getattr(state_obj, "architecture_summary", "") or "").strip():
        prompt += f"\n\n[참조: Architect가 확정한 시스템 아키텍처 - 태스크 분해 시 모듈 경계와 의존성을 이 설계에 맞추십시오]\n{state_obj.architecture_summary}"
    prompt += (
        "\n\n[ 절대 준수 사항]: PRD를 분석하여 반드시 **최소 4개 이상**의 구체적인 WBS 태스크로 분할하십시오. "
        "각 태스크에는 투입될 에이전트 명단(`required_agents`)을 반드시 포함하십시오. "
        "아키텍처 설계는 기획 단계에서 이미 확정되었으므로 `required_agents`에 `Architect`를 절대 배정하지 마십시오."
    )
    # ★ [I-4 §15] 산출물 종류를 태스크마다 **선언**하게 한다.
    #
    # ⚠️ 이 값이 없어도 파이프라인은 멈추지 않는다 — `wbs_artifact_kind` 가 판독 불가를
    #   `APP`(계약 필수)으로 떨어뜨리기 때문이다. 즉 **모델을 믿고 통제를 맡기지 않는다.**
    #   그런데도 프롬프트에서 요구하는 이유는, 선언된 값과 떨어진 값을 구분해야
    #   「기획이 REPORT 라고 판단했다」와 「읽을 수 없어 APP 이 됐다」가 갈리기 때문이다.
    #   후자가 쌓이면 그것은 앱의 결함이 아니라 **이 프롬프트의 결함**이다.
    prompt += (
        "\n\n[ 산출물 종류]: 각 태스크에 `artifact_kind` 를 다음 중 하나로 정확히 표기하십시오 — "
        "`APP`(사용자가 실행하는 앱), `SIMULATOR`(시뮬레이터), `REPORT`(보고서), "
        "`DOCUMENT`(문서·데이터 정의), `LIBRARY`(재사용 모듈). "
        "목록에 없는 값이나 빈 값은 `APP` 으로 간주되어 런타임 계약 승인 절차를 거치게 됩니다."
    )

    # WBS 게이트에서 사용자가 피드백을 줬으면(재분할 루프) 그 내용을 반영해 다시 분할한다.
    _fb_items = getattr(state_obj, "human_feedback_queue", []) or []
    _latest_fb = (_fb_items[-1].get("feedback", "") if _fb_items and isinstance(_fb_items[-1], dict) else "") or ""
    if _latest_fb.strip():
        prompt += f"\n\n[ 사용자 피드백 - WBS 재분할 시 반드시 반영하십시오]:\n{_latest_fb.strip()}"
        print(f" [Master PMO] 사용자 피드백을 반영해 WBS 를 재분할합니다: {_latest_fb.strip()[:80]}")

    def _parse_wbs_tasks(raw: str) -> list:
        clean_str = (raw or "").strip()
        # 1차: 게이트웨이가 이미 복구한 JSON 일 가능성이 높으므로 전체 파싱 먼저
        try:
            return (json.loads(clean_str) or {}).get("tasks", []) or []
        except Exception:
            pass
        # 2차: 코드펜스/서술 혼입 시 추출 - 반드시 greedy. non-greedy(*?)는 중첩 JSON(tasks 배열)의
        # 첫 '}' 에서 잘려 파싱이 깨지고 '빈 WBS' 가 조용히 저장된다(A-1 완주 스프린트 실측 결함)
        md_match = re.search(r'\x60{3}(?:json)?\s*(\{[\s\S]*\})\s*\x60{3}', clean_str)
        if md_match:
            clean_str = md_match.group(1)
        else:
            bracket_match = re.search(r'(\{[\s\S]*\})', clean_str)
            if bracket_match:
                clean_str = bracket_match.group(1)
        try:
            return (json.loads(clean_str) or {}).get("tasks", []) or []
        except Exception as e:
            print(f"⚠️ WBS 파싱 실패: {e}")
            return []

    output = await gateway.aexecute(state_obj, prompt, is_heavy=True, output_mode="json")

    # ★★ [2026-08-07] 공급자 실패를 «모델이 WBS 를 못 짰다» 로 읽지 않는다.
    #
    # ⚠️⚠️ 게이트웨이는 최종 실패 시 `{"files": [], "error": "LLM UNKNOWN ERROR: ..."}` 를 돌려준다.
    #   이것은 **유효한 JSON 이라서** 아래 `_parse_wbs_tasks` 를 그대로 통과하고 `.get("tasks")` 가
    #   `[]` 를 낸다 — 즉 「LLM 이 죽었다」와 「모델이 빈 WBS 를 냈다」가 **구분되지 않는다.**
    #   `is_llm_error_text` 의 독스트링이 "소비자는 반드시 이 함수로 걸러 fail-loud 처리해야
    #   한다"고 규정하는데 이 노드만 지키지 않고 있었다.
    #
    # 실측(2026-07-29 `test_a1_unitconv_canary2`)이 그 대가를 보여준다 — 공급자가 죽은 상태에서
    #   빈 WBS → 지시 강화 재호출(2배) → 기준 미달 채점 → HOTL 거부 → 재분할이 **7회** 돌았다.
    #   LLM 호출 28줄이 그렇게 쌓였고, 프롬프트에도 모델에도 아무 문제가 없었다.
    #   재시도를 늘리는 처방이었다면 이 루프를 더 길게 만들었을 뿐이다.
    #
    # → 공급자 실패면 **여기서 멈춘다.** 두 번째 호출을 태우지 않고(같은 이유로 또 죽는다),
    #   재분할 예산을 깎지 않고(모델을 시험해 본 적이 없다), `needs_revision` 도 켜지 않는다
    #   (그것이 자동 재분할 루프를 도는 스위치다). WBS 게이트에서 사람이 원인을 보고 판단한다.
    if is_llm_error_text(output):
        print(f"⛔ [Master PMO] LLM 공급자 실패 — WBS 분할을 시도하지 못했습니다. "
              f"기준 미달이 아니므로 재분할 루프에 넣지 않습니다: {str(output)[:200]}")
        return {
            "needs_revision": False,      # ⚠️ True 로 두면 자동 재분할 루프가 돈다(위 실측 7회)
            "current_stage": "PMO",
            # 사람이 보는 문장 — 「WBS 기준 미달」과 **다른 원인**임이 드러나야 한다.
            "supervisor_feedback": (
                "WBS 를 생성하지 못했습니다 — 원인은 산출물 품질이 아니라 **LLM 공급자 호출 실패**입니다. "
                "모델 응답이 오지 않아 분할을 시도할 수 없었습니다. 기존 WBS 는 덮어쓰지 않았습니다. "
                "공급자 상태(할당량·키·네트워크)를 확인한 뒤 이 단계를 다시 실행하십시오."
            ),
        }

    wbs_tasks = _parse_wbs_tasks(_extract_code_from_ssot(output) or output)

    if not wbs_tasks:
        # 빈 WBS 는 치명(실행할 태스크가 없어 파이프라인이 '완료된 척' 멈춘다) → 지시 강화 후 1회 재시도
        # (여기 도달했다면 공급자는 살아 있고 «모델이 형식을 못 맞춘» 경우다 — 지시 강화가 실제로 듣는다)
        print("⚠️ [Master PMO] WBS 태스크 0개 - 지시를 강화해 1회 재시도합니다.")
        retry_prompt = prompt + ("\n\n[ 재시도 - 직전 응답이 유효한 WBS JSON 이 아니었습니다. "
                                 "부연 설명 없이 'tasks' 배열(최소 4개 태스크)을 포함한 JSON 객체 하나만 출력하십시오.]")
        output = await gateway.aexecute(state_obj, retry_prompt, is_heavy=True, output_mode="json")
        if is_llm_error_text(output):
            print("⛔ [Master PMO] 재시도에서도 LLM 공급자 실패 — 재분할 루프에 넣지 않습니다.")
            return {
                "needs_revision": False,
                "current_stage": "PMO",
                "supervisor_feedback": (
                    "WBS 를 생성하지 못했습니다 — 재시도에서도 **LLM 공급자 호출이 실패**했습니다. "
                    "기존 WBS 는 덮어쓰지 않았습니다. 공급자 상태를 확인한 뒤 다시 실행하십시오."
                ),
            }
        wbs_tasks = _parse_wbs_tasks(_extract_code_from_ssot(output) or output)

    if state_obj.workspace_root and wbs_tasks:
        wbs_mgr = WBSManager(state_obj.workspace_root)
        # ★★★ [I-4 4단계 P0-1] **반환값을 받아 쓴다.**
        #
        # ⚠️ 예전에는 반환을 버리고 아래에서 `wbs_tasks[0]` 을 다시 읽었다. 정규화는
        #   새 dict 를 만들므로 원본에는 반영되지 않고, 그래서 **파일에는 `Tech_Lead`
        #   가 있는데 실행 상태(`current_required_agents`)에는 없는** 상태가 됐다.
        #   최초 실행이 계약을 건너뛰는 경로가 정확히 거기였다 — 정규화를 넣어 놓고
        #   그 결과를 안 쓰는 것이 가장 알아채기 어려운 형태의 무력화다.
        wbs_tasks = wbs_mgr.initialize_wbs(
            state_obj.project_name, wbs_tasks,
            runtime_contract_profile=getattr(state_obj, "runtime_contract_profile", ""))
        print(f"[OK] WBS 초기화 완료: 총 {len(wbs_tasks)}개의 태스크가 스케줄링되었습니다.")
    elif not wbs_tasks:
        # 빈 WBS 로 기존 파일을 덮어쓰지 않는다 - 게이트에서 사용자가 피드백(재분할)으로 복구 가능
        print("❌ [Master PMO] 재시도에도 WBS 생성 실패 - 빈 WBS 를 저장하지 않고 재분할 대기 상태로 둡니다.")

    # 첫 번째 실행 가능 태스크의 required_agents를 현재 스프린트 에이전트 명단으로 저장
    first_task_agents = []
    if wbs_tasks:
        first_task_agents = wbs_tasks[0].get("required_agents", [])

    # Supervisor: WBS 분할 기준(deterministic, LLM 0콜) 채점 기록
    from nodes.utils.scoring import score_stage
    pmo_result = await score_stage(state_obj, "PMO")
    scores = dict(getattr(state_obj, "stage_scores", {}) or {})
    scores["PMO"] = pmo_result.get("score", 0.0)
    crit_log = list(getattr(state_obj, "criteria_log", []) or [])
    crit_log.append({
        "stage": "PMO",
        "score": pmo_result.get("score", 0.0),
        "verdict": pmo_result.get("verdict", "PASS"),
        "blocking_fails": pmo_result.get("blocking_fails", []),
    })
    print(f" [Master PMO] WBS 기준 채점 - 점수 {pmo_result.get('score')} / 판정 {pmo_result.get('verdict')}")

    # ★ [2026-07-27] 채점 결과를 **라우팅에 실제로 반영**한다.
    #   ⚠️ 기존 결함: PMO 를 채점해놓고 `route_from_pmo` 는 `needs_revision`(사용자 피드백)만 봐서
    #     **점수가 미달이어도 그대로 통과**했다. 채점 결과는 문자열로 기록되고 버려졌다.
    #     WBS 는 이진이다 — 내용이 빠졌거나 배분이 잘못됐으면 다시 짜야 한다. 그 경로가
    #     자동으로는 존재하지 않았고, 사람이 피드백을 줘야만 재분할됐다.
    _pmo_pass = pmo_result.get("verdict") == "PASS"
    _attempts = dict(getattr(state_obj, "stage_attempt_counts", {}) or {})
    _pmo_tries = int(_attempts.get("PMO", 0)) + 1
    _attempts["PMO"] = _pmo_tries
    _max_tries = getattr(config, "WBS_MAX_RESPLIT_ATTEMPTS", 3)

    if not _pmo_pass and _pmo_tries < _max_tries:
        _fails = pmo_result.get("blocking_fails") or []
        print(f"🔁 [WBS 재분할] 기준 미달({_fails}) — {_pmo_tries}/{_max_tries}회차, WBS 를 다시 분할합니다.")
        return {
            "needs_revision": True,          # route_from_pmo 가 Master_PMO 로 되돌린다
            "current_stage": "PMO",
            "stage_scores": scores,
            "criteria_log": crit_log,
            "stage_attempt_counts": _attempts,
            "supervisor_feedback": (
                f"WBS 기준 미달로 재분할이 필요합니다. 미달 항목: {_fails}. "
                "특히 PRD 의 기능 요구(FR-ID)가 어느 태스크에도 배정되지 않았다면, "
                "그 요구를 담당할 태스크를 반드시 추가하십시오."
            ),
        }
    if not _pmo_pass:
        # 상한 도달: 무한 재분할 대신 사람이 보도록 표면화하고 진행한다(HOTL 게이트가 뒤따른다).
        print(f"⚠️ [WBS] 재분할 {_max_tries}회에도 기준 미달 — 사용자 확인이 필요합니다: {pmo_result.get('blocking_fails')}")

    return {
        "factory_mode": "EXECUTION",
        "needs_revision": False,
        "human_feedback_queue": [],  # 소비한 피드백 비움 - 다음 게이트에서 과거 피드백 재적용 방지
        "current_required_agents": first_task_agents,
        "current_stage": "PMO",
        "stage_scores": scores,
        "criteria_log": crit_log,
        "stage_attempt_counts": _attempts,
        "supervisor_feedback": "" if _pmo_pass else f"WBS 기준 미달(재분할 상한 도달): {pmo_result.get('blocking_fails')}",
    }

async def run_pm(state: Any) -> Dict[str, Any]:
    return await run_master_pm(state)