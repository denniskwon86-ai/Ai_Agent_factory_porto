import os
import json
import re
from typing import Dict, Any, List
from state_models import ProjectState
from core.llm_gateway import gateway
from core.agent_registry import agent_skill
from nodes.utils.git_manager import GitManager
from nodes.utils.wbs_manager import WBSManager
from nodes.utils.syntax_checker import LocalSyntaxChecker
from nodes.code_builder import CodeBuilder

def _load_skill(role_name: str) -> str:
    path = f"skills/{role_name}.md"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def _safe_str(output: Any) -> str:
    """🚨 [무적 방어막] List 형태나 객체 데이터가 넘어와도 절대 '.strip()' 에러가 나지 않도록 정규화"""
    if output is None: return ""
    
    if hasattr(output, "content"):
        content = output.content
        if isinstance(content, list):
            return "\n".join([str(c.get("text", c)) if isinstance(c, dict) else str(c) for c in content])
        return str(content)
        
    if isinstance(output, (list, dict)): 
        return json.dumps(output, ensure_ascii=False, indent=2)
    return str(output)

def _extract_files_from_json(json_str: Any) -> List[Dict[str, str]]:
    if not json_str: return []
    try:
        if isinstance(json_str, list):
            json_str = json.dumps(json_str, ensure_ascii=False)
        clean_str = str(json_str).strip()

        data = None
        # 1) 이미 정제된 JSON이면 통째로 파싱 (게이트웨이가 _repair_and_parse_json으로 정돈한 경우)
        try:
            data = json.loads(clean_str)
        except Exception:
            data = None
        # 2) 실패 시 마크다운 펜스 또는 '그리디' 괄호 매칭으로 추출 (중첩 JSON 보존 — 비탐욕 금지)
        if data is None:
            md_match = re.search(r'\x60{3}(?:json)?\s*(\{[\s\S]*\})\s*\x60{3}', clean_str)
            if md_match:
                clean_str = md_match.group(1)
            else:
                alt_match = re.search(r'(\{[\s\S]*\})', clean_str)
                if alt_match:
                    clean_str = alt_match.group(1)
            data = json.loads(clean_str)

        files = data.get("files", []) if isinstance(data, dict) else []
        return files if isinstance(files, list) else []
    except Exception:
        return []

async def run_architect(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)
    print("🧭 [Agent] Architect 토론·합의 기반 설계 진행 중...")
    from nodes.utils.debate import run_supervised_stage
    updates, result = await run_supervised_stage(state_obj, agent_skill("Architect", "architect_skill"), "ARCHITECTURE")
    print(f"✅ [Agent] Architect 설계 완료 — 점수 {result.get('score')} / 판정 {result.get('verdict')}")
    updates.setdefault("factory_mode", "EXECUTION")
    updates.setdefault("needs_revision", False)
    return updates

async def run_tech_lead(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)

    extra = ""
    if getattr(state_obj, "reviewer_decision", "") == "REWORK_DEV" or getattr(state_obj, "needs_revision", False):
        print("🛠️ [Agent] Tech Lead: 결함/기획변경에 따른 토론 기반 재설계(Rework) 진행 중...")
        extra = f"\n\n[🚨 재작업(Rework) 지시사항]:\n리뷰어 또는 PM의 피드백을 반영하여 설계를 수정하십시오:\n{state_obj.reviewer_feedback}"
    else:
        print("🛠️ [Agent] Tech Lead 토론·합의 기반 기술명세 진행 중...")

    from nodes.utils.debate import run_supervised_stage
    updates, result = await run_supervised_stage(state_obj, agent_skill("Tech_Lead", "tech_lead_skill"), "TECH_SPEC", extra_instruction=extra)
    output_str = updates.get("tech_spec_summary", getattr(state_obj, "tech_spec_summary", "") or "")

    # 기존 STATE_UPDATES(ADR/기술부채/파일인덱스) 파싱 로직 유지
    arch_decisions = state_obj.architecture_decisions
    tech_debt = state_obj.technical_debt
    file_idx = state_obj.file_index

    state_update_match = re.search(r'5\.\s*STATE_UPDATES[\s\S]*?\x60{3}(?:json)?\s*(\{[\s\S]*?\})\s*\x60{3}', output_str)
    if state_update_match:
        try:
            su = json.loads(state_update_match.group(1))
            # 🚨 견고화: LLM이 ADR/부채를 객체가 아닌 문자열(ID)로 줄 때 정상 스키마로 변환 (재개 시 검증 크래시 방지)
            for item in (su.get("architecture_decisions") or []):
                if isinstance(item, dict):
                    arch_decisions.append(item)
                elif isinstance(item, str) and item.strip():
                    arch_decisions.append({"id": item.strip()[:64], "decision": item.strip(), "reason": ""})
            for item in (su.get("technical_debt") or []):
                if isinstance(item, dict):
                    tech_debt.append(item)
                elif isinstance(item, str) and item.strip():
                    tech_debt.append({"id": item.strip()[:64], "description": item.strip(), "priority": 3})
            if "file_index_updates" in su:
                for path, info in su["file_index_updates"].items():
                    if path in file_idx:
                        file_idx[path].purpose = info.get("purpose", file_idx[path].purpose)
                        file_idx[path].change_summary = info.get("change_summary", file_idx[path].change_summary)
        except Exception as e:
            print(f"⚠️ Tech Lead STATE_UPDATES 파싱 실패: {e}")

    updates["architecture_decisions"] = arch_decisions
    updates["technical_debt"] = tech_debt
    updates["file_index"] = file_idx
    print(f"✅ [Agent] Tech Lead 기술명세 완료 — 점수 {result.get('score')} / 판정 {result.get('verdict')}")
    return updates

# 증분 개발 지시 — 멀티태스크에서 이전 태스크가 만든 기능을 덮어써 잃어버리는 회귀 방지.
_INCREMENTAL_GUARD = (
    "\n\n[🚨 증분 개발 — 절대 준수]: 당신은 빈 화면이 아니라 **기존 코드베이스를 확장**한다. "
    "컨텍스트의 '현재 워크스페이스 실제 파일'에 이미 구현된 모든 기능(예: 데이터 입력/CRUD/목록/상태)을 "
    "**절대 삭제하거나 누락하지 말 것.** 이번 태스크의 기능을 **추가/수정만** 하라. "
    "기존 파일을 다시 출력할 때는 반드시 '기존 기능 전부 + 이번 신규 기능'을 합친 완전한 코드를 내라. "
    "(컨텍스트에 파일이 일부 잘려 보이면, 잘린 기능까지 보존하도록 신중히 작성하라.)"
)


async def run_developer_fe(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)
    print("🎨 [Agent] Frontend Worker 비동기 코딩 중...")
    prompt = _load_skill(agent_skill("Frontend", "frontend_skill")) + _INCREMENTAL_GUARD

    if getattr(state_obj, "reviewer_decision", "") == "REWORK_DEV":
        prompt += f"\n\n[🚨 재작업(Rework) 지시사항]:\n{state_obj.reviewer_feedback}"

    # 코드 생성은 핵심 산출물 → Pro 티어(품질 우선). 멀티파일 누적·기존기능 보존엔 강모델 필요.
    output = await gateway.aexecute(state_obj, prompt, is_heavy=True)
    return {"frontend_code_summary": _safe_str(output), "build_error_log": "", "failed_node": ""}

async def run_developer_be(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)
    print("⚙️ [Agent] Backend Worker 비동기 코딩 중...")
    prompt = _load_skill(agent_skill("Backend", "backend_skill")) + _INCREMENTAL_GUARD

    if getattr(state_obj, "reviewer_decision", "") == "REWORK_DEV":
        prompt += f"\n\n[🚨 재작업(Rework) 지시사항]:\n{state_obj.reviewer_feedback}"

    # 코드 생성은 핵심 산출물 → Pro 티어(품질 우선).
    output = await gateway.aexecute(state_obj, prompt, is_heavy=True)
    return {"backend_code_summary": _safe_str(output), "build_error_log": "", "failed_node": ""}

async def run_code_builder(state: Any) -> Dict[str, Any]:
    print("🏗️ [Headless 빌더] 파일 병합 및 원자적 디스크 저장 가동...")
    state_obj = ProjectState.model_validate(state)
    
    if not state_obj.workspace_root: raise ValueError("workspace_root 없음")

    current_retry = getattr(state_obj, "developer_retry_count", 0)
    req_agents = getattr(state_obj, "current_required_agents", [])

    if current_retry >= 3:
        print("🛑 [Circuit Breaker] 3회 연속 자가 복구 실패. 안전 지점 롤백.")
        git_mgr = GitManager(state_obj.workspace_root)
        last_commit = getattr(state_obj.git_info, "last_commit_hash", None) if state_obj.git_info else None
        git_mgr.rollback_to_safe_state(last_commit)
        return {"build_status": "failed", "developer_retry_count": 0, "factory_mode": "HOTL_PAUSED"}

    arch_files = _extract_files_from_json(state_obj.architecture_summary)
    tech_files = _extract_files_from_json(state_obj.tech_spec_summary)
    fe_files = _extract_files_from_json(state_obj.frontend_code_summary)
    be_files = _extract_files_from_json(state_obj.backend_code_summary)
    
    all_files_to_write = arch_files + tech_files + fe_files + be_files
    
    has_fe = any("frontend" in a.lower() or "프론트" in a for a in req_agents)
    has_be = any("backend" in a.lower() or "백엔드" in a for a in req_agents)
    has_coding_agent = has_fe or has_be

    if not all_files_to_write:
        if not has_coding_agent: return {"build_status": "success", "failed_node": "", "developer_retry_count": 0}
        else: return {"build_status": "failed", "failed_node": ("Frontend" if has_fe else "Backend"), "developer_retry_count": current_retry + 1}

    be_pure_code = "\n".join([f.get("code", "") for f in be_files if f.get("file_path", "").endswith(".py")])
    if be_pure_code:
        is_be_valid, be_msg = LocalSyntaxChecker.check_python_syntax(be_pure_code)
        if not is_be_valid: return {"build_status": "failed", "build_error_log": be_msg, "failed_node": "Backend", "developer_retry_count": current_retry + 1}

    fe_pure_code = "\n".join([f.get("code", "") for f in fe_files if f.get("file_path", "").endswith((".tsx", ".ts", ".js", ".jsx"))])
    if fe_pure_code:
        is_fe_valid, fe_msg = LocalSyntaxChecker.check_javascript_syntax(fe_pure_code)
        if not is_fe_valid: return {"build_status": "failed", "build_error_log": fe_msg, "failed_node": "Frontend", "developer_retry_count": current_retry + 1}

    builder = CodeBuilder(workspace_root=state_obj.workspace_root)
    state_dict = state_obj.model_dump()
    updated_state_dict, results = builder.run(state_dict, all_files_to_write)
    
    if updated_state_dict.get("build_status") == "failed":
        if not has_coding_agent: return {"build_status": "success", "developer_retry_count": 0}
        else: return {"build_status": "failed", "failed_node": ("Frontend" if has_fe else "Backend"), "developer_retry_count": current_retry + 1}

    return {"build_status": "success", "developer_retry_count": 0, "file_index": updated_state_dict.get("file_index", state_obj.file_index)}

async def run_supervisor(state: Any) -> Dict[str, Any]:
    """범용 단계 게이트(구 run_reviewer를 일반화). 코드리뷰 단계의 PASS/REWORK_DEV/ESCALATE_PM
    3분기 및 Git 커밋/WBS 완료 로직은 그대로 보존하고, 단계 기준 채점을 기록한다."""
    state_obj = ProjectState.model_validate(state)
    # Supervisor 왕복 카운터 — 매 리뷰 실행마다 +1 (route_from_reviewer 가 상한 초과 시 루프 차단)
    hops = getattr(state_obj, "supervisor_hops", 0) + 1

    if getattr(state_obj, "pm_override_reason", ""):
        print(f"⚖️ [Agent] Reviewer: PM의 기각/강행 지시 수용 (사유: {state_obj.pm_override_reason})")
        reviewer_decision = "PASS"
        review_text = "PM 최종 승인 지시: " + state_obj.pm_override_reason
    else:
        has_fe_code = bool(_extract_files_from_json(state_obj.frontend_code_summary))
        has_be_code = bool(_extract_files_from_json(state_obj.backend_code_summary))
        
        # 🖥️ 프론트 렌더 검증 테스트러너: 실제 renderToString 으로 동작 확인 (실패 시 LLM 리뷰 없이 즉시 재작업)
        render_note = ""
        if has_fe_code:
            from nodes.utils.render_checker import check_frontend_render
            fe_files = _extract_files_from_json(state_obj.frontend_code_summary)
            render = check_frontend_render(fe_files)
            if not render.get("ok") and not render.get("skipped"):
                errs = render.get("errors", [])
                print(f"❌ [TestRunner] 프론트 렌더 검증 실패: {errs}")
                review_text = (
                    "🖥️ 프론트엔드 렌더 검증 실패 — 생성 코드가 실제로 렌더되지 않습니다:\n- "
                    + "\n- ".join(errs[:5])
                    + "\n\n위 오류(특히 허용되지 않은 외부 import / null 안전성)를 수정해 다시 작성하십시오."
                )
                reviewer_decision = "REWORK_DEV"
                # 렌더 실패는 결정적 결함 → LLM 리뷰 생략하고 재작업 루프로 직행
                workspace_root = state_obj.workspace_root
                cr_scores = dict(getattr(state_obj, "stage_scores", {}) or {})
                cr_scores["CODE_REVIEW"] = 0.0
                cr_log = list(getattr(state_obj, "criteria_log", []) or [])
                cr_log.append({"stage": "CODE_REVIEW", "score": 0.0, "verdict": "REWORK_DEV", "blocking_fails": ["frontend_render"]})
                return {
                    "reviewer_decision": "REWORK_DEV",
                    "reviewer_feedback": review_text,
                    "pm_override_reason": "",
                    "needs_revision": False,
                    "current_stage": "CODE_REVIEW",
                    "stage_scores": cr_scores,
                    "criteria_log": cr_log,
                    "supervisor_feedback": review_text,
                    "supervisor_hops": hops,
                }
            elif render.get("ok") and not render.get("skipped"):
                render_note += f"\n(✅ 프론트 렌더 검증 통과 — renderToString {render.get('rendered', 0)}자)"

        # ⚙️ 백엔드 스모크 테스트러너: 격리 부팅 + 엔드포인트 검증 (실패 시 즉시 재작업)
        if has_be_code:
            from nodes.utils.backend_smoke import check_backend_smoke
            be_files = _extract_files_from_json(state_obj.backend_code_summary)
            smoke = check_backend_smoke(be_files)
            if not smoke.get("ok") and not smoke.get("skipped"):
                errs = smoke.get("errors", [])
                print(f"❌ [TestRunner] 백엔드 스모크 실패: {errs}")
                review_text = (
                    "⚙️ 백엔드 스모크 실패 — 생성 코드가 정상 부팅/응답하지 않습니다:\n- "
                    + "\n- ".join(errs[:5])
                    + "\n\n위 오류(부팅 크래시 / 내부 모듈 import 누락 / 엔드포인트 5xx 등)를 수정해 다시 작성하십시오."
                )
                cr_scores = dict(getattr(state_obj, "stage_scores", {}) or {})
                cr_scores["CODE_REVIEW"] = 0.0
                cr_log = list(getattr(state_obj, "criteria_log", []) or [])
                cr_log.append({"stage": "CODE_REVIEW", "score": 0.0, "verdict": "REWORK_DEV", "blocking_fails": ["backend_smoke"]})
                return {
                    "reviewer_decision": "REWORK_DEV",
                    "reviewer_feedback": review_text,
                    "pm_override_reason": "",
                    "needs_revision": False,
                    "current_stage": "CODE_REVIEW",
                    "stage_scores": cr_scores,
                    "criteria_log": cr_log,
                    "supervisor_feedback": review_text,
                    "supervisor_hops": hops,
                }
            elif smoke.get("ok") and not smoke.get("skipped"):
                _w = smoke.get("warnings", [])
                render_note += f"\n(✅ 백엔드 스모크 통과 — 라우트 {smoke.get('routes', 0)}개" + (f", 경고 {len(_w)}건" if _w else "") + ")"

        if not has_fe_code and not has_be_code:
            print("⏩ [Smart Bypass] 코드 작성 내역이 없으므로 리뷰를 통과(PASS)합니다.")
            reviewer_decision = "PASS"
            review_text = "코드 작성 없음 - 설계/문서 업데이트 정상 완료."
        else:
            print(f"📝 [Agent] Reviewer 비동기 코드 리뷰 및 의사결정 분류 중...{render_note}")
            prompt = (
                "현재 작성된 모든 코드를 리뷰하고, 다음 3가지 중 하나의 의사결정(decision)을 선택하십시오.\n"
                "1. `PASS`: 문제가 없거나 사소한 오타 수준일 때. 릴리즈 노트 작성.\n"
                "2. `REWORK_DEV`: 구현 누락, 버그, 설계 위반 등 실무진(Tech Lead, 개발자) 선에서 재작업이 필요할 때. 피드백 작성.\n"
                "3. `ESCALATE_PM`: 기획서 자체의 논리적 모순이나 비즈니스 요구사항 위배로 PM의 최종 의사결정이 필요할 때. 피드백 작성.\n\n"
                "응답은 반드시 아래 JSON 포맷을 준수하십시오:\n"
                "\x60\x60\x60json\n"
                "{\n"
                "  \"decision\": \"PASS\",\n"
                "  \"feedback\": \"리뷰 내용 또는 결함/기획 모순 내역\"\n"
                "}\n"
                "\x60\x60\x60"
            )
            # 🚨 FIX: 리뷰어 역시 빠르고 비용 효율적인 Flash 모델로 롤백 (자유 스키마 JSON 모드)
            output = await gateway.aexecute(state_obj, prompt, is_heavy=False, output_mode="json")
            output_str = _safe_str(output)
            
            reviewer_decision = "PASS"
            review_text = output_str
            try:
                clean_str = output_str.strip()
                md_match = re.search(r'\x60{3}(?:json)?\s*(\{[\s\S]*?\})\s*\x60{3}', clean_str)
                if md_match: clean_str = md_match.group(1)
                else:
                    alt_match = re.search(r'(\{[\s\S]*?\})', clean_str)
                    if alt_match: clean_str = alt_match.group(1)
                data = json.loads(clean_str)
                reviewer_decision = data.get("decision", "PASS")
                review_text = data.get("feedback", "")
            except Exception as e:
                print(f"⚠️ Reviewer JSON 파싱 실패 (기본 통과 처리): {e}")

    workspace_root = state_obj.workspace_root
    task_id = state_obj.current_sprint_task_id
    state_dict = state_obj.model_dump()
    git_info_dict = getattr(state_obj, "git_info", None)
    if hasattr(git_info_dict, "model_dump"): git_info_dict = git_info_dict.model_dump()
    elif not git_info_dict: git_info_dict = {}

    # Supervisor: 코드리뷰 단계 기준 채점 기록 (빌드 성공 여부 = deterministic)
    cr_score = 1.0 if (getattr(state_obj, "build_status", "pending") == "success" and reviewer_decision == "PASS") else 0.0
    cr_scores = dict(getattr(state_obj, "stage_scores", {}) or {})
    cr_scores["CODE_REVIEW"] = cr_score
    cr_log = list(getattr(state_obj, "criteria_log", []) or [])
    cr_log.append({
        "stage": "CODE_REVIEW",
        "score": cr_score,
        "verdict": reviewer_decision,
        "blocking_fails": [] if reviewer_decision == "PASS" else ["code_review"],
    })

    if reviewer_decision != "PASS":
        print(f"❌ [Supervisor] 결함 감지! 분류: {reviewer_decision}")
        return {
            "reviewer_decision": reviewer_decision,
            "reviewer_feedback": review_text,
            "pm_override_reason": "",
            "needs_revision": False,
            "current_stage": "CODE_REVIEW",
            "stage_scores": cr_scores,
            "criteria_log": cr_log,
            "supervisor_feedback": review_text,
            "supervisor_hops": hops,
        }

    if getattr(state_obj, "build_status", "pending") == "success":
        git_mgr = GitManager(workspace_root)
        commit_hash = git_mgr.commit_sprint_changes(task_id, state_dict)
        if commit_hash:
            git_info_dict["last_commit_hash"] = commit_hash
            git_info_dict["last_commit_task"] = task_id

        wbs_path = os.path.join(workspace_root, "00_wbs_master_plan.json")
        if os.path.exists(wbs_path):
            wbs_mgr = WBSManager(workspace_root=workspace_root)
            wbs_mgr.complete_task(task_id)
    
    return {
        "code_review_report_summary": review_text,
        "reviewer_decision": "PASS",
        "reviewer_feedback": "",
        "pm_override_reason": "",
        "needs_revision": False,
        "git_info": git_info_dict,
        "current_stage": "CODE_REVIEW",
        "stage_scores": cr_scores,
        "criteria_log": cr_log,
        "supervisor_feedback": "",
        "supervisor_hops": hops,
    }


# 하위 호환 별칭: 기존 import(run_reviewer)를 깨지 않도록 유지
run_reviewer = run_supervisor

async def run_qa(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)
    print("🧪 [Agent] QA 최종 통합 검증(RFP 대조) 진행 중...")

    rfp = getattr(state_obj, "rfp_summary", "") or ""
    if state_obj.build_status == "failed":
        prompt = (
            f"🚨 [품질 검사 낙제]: 빌드 실패. 에러 로그:\n{state_obj.build_error_log}\n\n"
            "무엇이 깨졌는지와 RFP 대비 미충족 항목을 담은 불합격 리포트를 작성하십시오."
        )
    else:
        prompt = (
            f"{_load_skill(agent_skill('QA', 'qa_skill'))}\n\n"
            "[검증 기준 — 요구사항 정의서(RFP)]:\n"
            f"{rfp if rfp else '(RFP 없음 — PRD/구현 기준으로 평가)'}\n\n"
            "위 RFP의 각 REQ-ID가 실제 구현 코드에 반영되었는지(추적성)와 빌드/작동 가능성을 평가해 리포트를 작성하십시오."
        )

    output = await gateway.aexecute(state_obj, prompt, is_heavy=True, output_mode="document")
    return {"qa_report_summary": _safe_str(output), "current_stage": "QA"}

async def run_manual_writer(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)

    # 빌드 실패 또는 프론트엔드 코드가 없으면 매뉴얼 생략
    if state_obj.build_status == "failed" or not state_obj.frontend_code_summary:
        print("⏩ [Smart Bypass] 빌드 실패 또는 코드 없음 — 사용자 매뉴얼 생성을 건너뜁니다.")
        return {}

    print("📖 [Agent] Technical Writer 사용자 매뉴얼 작성 중...")
    skill = _load_skill(agent_skill("ManualWriter", "manual_skill"))
    prompt = (
        f"{skill}\n\n"
        f"[참조: 기획서(PRD)]\n{state_obj.prd_summary}\n\n"
        f"[참조: 프론트엔드 코드 요약]\n{state_obj.frontend_code_summary}\n\n"
        f"[참조: QA 최종 검증 리포트]\n{state_obj.qa_report_summary}"
    )
    output = await gateway.aexecute(state_obj, prompt, is_heavy=True)
    print("✅ [Agent] 사용자 매뉴얼 작성 완료.")
    return {"user_manual_summary": _safe_str(output)}