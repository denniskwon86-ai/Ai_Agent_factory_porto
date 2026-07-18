import os
import json
import re
import asyncio
from pathlib import Path
from typing import Dict, Any, List
import config
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
    """ [무적 방어막] List 형태나 객체 데이터가 넘어와도 절대 '.strip()' 에러가 나지 않도록 정규화"""
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
        # 2) 실패 시 마크다운 펜스 또는 '그리디' 괄호 매칭으로 추출 (중첩 JSON 보존 - 비탐욕 금지)
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

def _collect_disk_files(workspace_root: str, exts: tuple, cap: int = 120) -> List[Dict[str, str]]:
    """워크스페이스 디스크에서 지정 확장자 파일을 수집해 [{file_path, code}] 로 반환.
    프리뷰/회귀 게이트가 '마지막 LLM 출력'이 아니라 '디스크의 현재 전체 파일 집합'을 보도록 한다.
    노이즈 디렉터리(node_modules/.git/.archive 등)는 제외."""
    out: List[Dict[str, str]] = []
    if not workspace_root:
        return out
    root = Path(workspace_root)
    if not root.exists():
        return out
    from core.context_engine import _EXCLUDE_DIRS
    for p in sorted(root.rglob("*")):
        if len(out) >= cap:
            break
        if not p.is_file():
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        if any(seg in _EXCLUDE_DIRS for seg in rel.split("/")):
            continue
        if rel.endswith(exts):
            try:
                out.append({"file_path": rel, "code": p.read_text(encoding="utf-8")})
            except Exception:
                continue
    return out


async def run_architect(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)
    print(" [Agent] Architect 토론·합의 기반 설계 진행 중...")

    # 기획 단계에서 사용자가 승인한 UI 목업이 있으면 화면 구조/컴포넌트 경계를 아키텍처에 반영
    extra = ""
    ui_mockup = (getattr(state_obj, "ui_mockup_summary", "") or "").strip()
    if ui_mockup:
        extra = f"\n\n[참조: 사용자가 승인한 UI 목업 - 화면 구성과 컴포넌트 경계를 아키텍처 설계에 반영하십시오]\n{ui_mockup}"

    from nodes.utils.debate import run_supervised_stage
    updates, result = await run_supervised_stage(state_obj, agent_skill("Architect", "architect_skill", template_id=state_obj.template_id), "ARCHITECTURE", extra_instruction=extra)
    print(f"[OK] [Agent] Architect 설계 완료 - 점수 {result.get('score')} / 판정 {result.get('verdict')}")
    updates.setdefault("factory_mode", "EXECUTION")
    updates.setdefault("needs_revision", False)
    return updates

async def run_tech_lead(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)

    extra = ""
    if getattr(state_obj, "reviewer_decision", "") == "REWORK_DEV" or getattr(state_obj, "needs_revision", False):
        print("️ [Agent] Tech Lead: 결함/기획변경에 따른 토론 기반 재설계(Rework) 진행 중...")
        extra = f"\n\n[ 재작업(Rework) 지시사항]:\n리뷰어 또는 PM의 피드백을 반영하여 설계를 수정하십시오:\n{state_obj.reviewer_feedback}"
    else:
        print("️ [Agent] Tech Lead 토론·합의 기반 기술명세 진행 중...")

    from nodes.utils.debate import run_supervised_stage
    updates, result = await run_supervised_stage(state_obj, agent_skill("Tech_Lead", "tech_lead_skill", template_id=state_obj.template_id), "TECH_SPEC", extra_instruction=extra)
    output_str = updates.get("tech_spec_summary", getattr(state_obj, "tech_spec_summary", "") or "")

    # 기존 STATE_UPDATES(ADR/기술부채/파일인덱스) 파싱 로직 유지
    arch_decisions = state_obj.architecture_decisions
    tech_debt = state_obj.technical_debt
    file_idx = state_obj.file_index

    state_update_match = re.search(r'5\.\s*STATE_UPDATES[\s\S]*?\x60{3}(?:json)?\s*(\{[\s\S]*?\})\s*\x60{3}', output_str)
    if state_update_match:
        try:
            su = json.loads(state_update_match.group(1))
            #  견고화: LLM이 ADR/부채를 객체가 아닌 문자열(ID)로 줄 때 정상 스키마로 변환 (재개 시 검증 크래시 방지)
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
    print(f"[OK] [Agent] Tech Lead 기술명세 완료 - 점수 {result.get('score')} / 판정 {result.get('verdict')}")
    return updates

# 증분 개발 지시 - 멀티태스크에서 이전 태스크가 만든 기능을 덮어써 잃어버리는 회귀 방지.
# 소유 파일은 컨텍스트에 '전체 코드'로(절단 없이) 주입되므로, 모델은 기존 기능을 빠짐없이 볼 수 있다.
_INCREMENTAL_GUARD = (
    "\n\n[ 증분 개발 - 절대 준수]: 당신은 빈 화면이 아니라 **기존 코드베이스를 확장**한다. "
    "컨텍스트의 '현재 워크스페이스 실제 파일 상태'에는 당신이 수정할 파일들의 **전체 코드가 절단 없이** 들어 있다. "
    "거기 이미 구현된 모든 기능(데이터 입력/CRUD/목록/상태/이벤트 핸들러 등)을 **절대 삭제하거나 누락하지 말 것.** "
    "이번 태스크의 기능은 **추가/수정만** 하라. 파일을 다시 출력할 때는 반드시 "
    "'기존 코드 전부 + 이번 신규 기능'을 합친 완전한 코드를 내라. 기존 기능을 하나라도 빠뜨리면 즉시 재작업 처리된다."
)

# 개발자별 '소유 파일' 확장자 - 컨텍스트에 전체(무절단) 주입할 대상(증분 codegen).
_FE_OWNED_EXTS = (".tsx", ".ts", ".jsx", ".js", ".css", ".html")
_BE_OWNED_EXTS = (".py",)

async def _swarm_execution(state_obj: ProjectState, base_prompt: str, is_heavy: bool, full_file_exts: tuple, num_swarm: int = 3) -> Any:
    """Micro-Swarm 실행기: N개의 에이전트를 병렬로 띄우고 문법/샌드박스 통과 코드를 선별"""
    
    async def _run_single(variant_id: int):
        # Variant에 따라 시스템 프롬프트를 미세하게 변경하여 다양성(Swarm Diversity) 유도
        variant_prompt = base_prompt + f"\n\n[System Note: You are Swarm Agent #{variant_id}. Focus on writing clean, bug-free code.]"
        try:
            return await gateway.aexecute(state_obj, variant_prompt, is_heavy=is_heavy, full_file_exts=full_file_exts)
        except Exception:
            return None

    print(f" [Micro-Swarm] {num_swarm}개의 병렬 에이전트 생성 중...")
    results = await asyncio.gather(*[_run_single(i) for i in range(1, num_swarm + 1)])
    
    valid_outputs = []
    for idx, raw_out in enumerate(results):
        out_str = _safe_str(raw_out)
        if not out_str: continue
        
        # 파일 추출 및 샌드박스(정적 문법) 검증
        files = _extract_files_from_json(out_str)
        is_valid = True
        for f in files:
            path = f.get("file_path", "")
            code = f.get("code", "")
            if path.endswith((".ts", ".tsx", ".js", ".jsx")):
                valid, _ = LocalSyntaxChecker.check_javascript_syntax(code)
                if not valid: is_valid = False; break
            elif path.endswith(".py"):
                valid, _ = LocalSyntaxChecker.check_python_syntax(code)
                if not valid: is_valid = False; break
                
        if is_valid and files:
            print(f" [Micro-Swarm] 에이전트 #{idx+1}의 코드가 컴파일 검증을 통과했습니다!")
            return raw_out # 첫 번째 성공작 즉시 반환
        else:
            if files: valid_outputs.append(raw_out)
            
    print("⚠️ [Micro-Swarm] 샌드박스를 완벽히 통과한 코드를 찾지 못했습니다. 베스트-에포트 결과를 반환합니다.")
    return valid_outputs[0] if valid_outputs else results[0]


async def run_developer_fe(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)
    print(" [Agent] Frontend Worker 비동기 코딩 중...")
    prompt = _load_skill(agent_skill("Frontend", "frontend_skill", template_id=state_obj.template_id)) + _INCREMENTAL_GUARD
    
    prompt += f"\n\n[참조: UI 기획/목업 설계 - 화면 개발 시 반드시 아래 UI 디자이너의 의도를 그대로 화면에 구현하십시오]\n{getattr(state_obj, 'ui_mockup_summary', '')}"
    prompt += f"\n\n[참조: 아키텍처 설계]\n{getattr(state_obj, 'architecture_summary', '')}"
    prompt += f"\n\n[참조: 기술 명세]\n{getattr(state_obj, 'tech_spec_summary', '')}"

    # 디자인 토큰 가이드 주입 - 일관된 스타일로 첫 판 품질↑(재작업↓). 안정 텍스트라 캐시 친화적.
    _ds = _load_skill("design_system")
    if _ds:
        prompt += "\n\n[디자인 시스템 가이드 - 아래 Tailwind 토큰/레시피를 그대로 사용]\n" + _ds

    _is_rework = getattr(state_obj, "reviewer_decision", "") == "REWORK_DEV" or getattr(state_obj, "developer_retry_count", 0) > 0
    if _is_rework and getattr(state_obj, "reviewer_decision", "") == "REWORK_DEV":
        prompt += f"\n\n[ 재작업(Rework) 지시사항]:\n{state_obj.reviewer_feedback}"

    # 코드 생성: 평시 1회 호출(토큰 3배 낭비·429 폭주 방지), 재작업/재시도 시에만 3중 스웜으로 승격
    output = await _swarm_execution(state_obj, prompt, is_heavy=False, full_file_exts=_FE_OWNED_EXTS, num_swarm=3 if _is_rework else 1)
    return {"frontend_code_summary": _safe_str(output), "build_error_log": "", "failed_node": ""}

async def run_developer_be(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)
    print("⚙️ [Agent] Backend Worker 비동기 코딩 중...")
    prompt = _load_skill(agent_skill("Backend", "backend_skill", template_id=state_obj.template_id)) + _INCREMENTAL_GUARD

    prompt += f"\n\n[참조: 아키텍처 설계]\n{getattr(state_obj, 'architecture_summary', '')}"
    prompt += f"\n\n[참조: 기술 명세]\n{getattr(state_obj, 'tech_spec_summary', '')}"

    _is_rework = getattr(state_obj, "reviewer_decision", "") == "REWORK_DEV" or getattr(state_obj, "developer_retry_count", 0) > 0
    if _is_rework and getattr(state_obj, "reviewer_decision", "") == "REWORK_DEV":
        prompt += f"\n\n[ 재작업(Rework) 지시사항]:\n{state_obj.reviewer_feedback}"

    # 코드 생성: 평시 1회 호출(토큰 3배 낭비·429 폭주 방지), 재작업/재시도 시에만 3중 스웜으로 승격
    output = await _swarm_execution(state_obj, prompt, is_heavy=False, full_file_exts=_BE_OWNED_EXTS, num_swarm=3 if _is_rework else 1)
    return {"backend_code_summary": _safe_str(output), "build_error_log": "", "failed_node": ""}

async def run_code_builder(state: Any) -> Dict[str, Any]:
    print("️ [Headless 빌더] 파일 병합 및 원자적 디스크 저장 가동...")
    state_obj = ProjectState.model_validate(state)
    
    if not state_obj.workspace_root: raise ValueError("workspace_root 없음")

    current_retry = getattr(state_obj, "developer_retry_count", 0)
    req_agents = getattr(state_obj, "current_required_agents", [])

    if current_retry >= 3:
        print(" [Circuit Breaker] 3회 연속 자가 복구 실패. 안전 지점 롤백.")
        git_mgr = GitManager(state_obj.workspace_root)
        last_commit = getattr(state_obj.git_info, "last_commit_hash", None) if state_obj.git_info else None
        git_mgr.rollback_to_safe_state(last_commit)
        # ⚠️ 무한루프(Ping-Pong) 방지: developer_retry_count를 0으로 초기화하지 않고 그대로 반환하여 라우터가 END로 가게 함
        return {"build_status": "failed", "developer_retry_count": current_retry + 1, "factory_mode": "HOTL_PAUSED"}

    arch_files = _extract_files_from_json(state_obj.architecture_summary)
    tech_files = _extract_files_from_json(state_obj.tech_spec_summary)
    fe_files = _extract_files_from_json(state_obj.frontend_code_summary)
    be_files = _extract_files_from_json(state_obj.backend_code_summary)
    
    all_files_to_write = arch_files + tech_files + fe_files + be_files
    
    has_fe = any("frontend" in a.lower() or "프론트" in a for a in req_agents)
    has_be = any("backend" in a.lower() or "백엔드" in a for a in req_agents)
    has_coding_agent = has_fe or has_be

    #  [무결성 가드] 코딩 에이전트가 요구됐는데 '그 에이전트'의 추출 파일이 0개면(출력 절단/
    #    JSON 전량 폐기/모델 누락 의심) 다른 에이전트 산출물이 있어도 success 로 위장되지 않게
    #    명시적 실패 처리. 이를 빼면 FE 유실 + BE 성공 → success 커밋 → 다음 태스크에 FE 영구 손실.
    if has_fe and not fe_files:
        print(" [무결성] Frontend 요구됐으나 추출 파일 0개 → 빌드 실패(재작업).")
        return {"build_status": "failed", "failed_node": "Frontend",
                "build_error_log": "프론트엔드 산출물이 비어 있습니다(출력 절단/파싱 실패 의심). 기존 코드 전부 + 신규 기능을 합쳐 전체를 다시 생성하십시오.",
                "developer_retry_count": current_retry + 1}
    if has_be and not be_files:
        print(" [무결성] Backend 요구됐으나 추출 파일 0개 → 빌드 실패(재작업).")
        return {"build_status": "failed", "failed_node": "Backend",
                "build_error_log": "백엔드 산출물이 비어 있습니다(출력 절단/파싱 실패 의심). 기존 코드 전부 + 신규 기능을 합쳐 전체를 다시 생성하십시오.",
                "developer_retry_count": current_retry + 1}

    if not all_files_to_write:
        if not has_coding_agent: return {"build_status": "success", "failed_node": "", "developer_retry_count": 0}
        else: return {"build_status": "failed", "failed_node": ("Frontend" if has_fe else "Backend"), "developer_retry_count": current_retry + 1}

    # 파일별 개별 검사 - 전체를 이어붙여 검사하면 뒤 파일의 `from __future__ import` 가
    # "파일 선두여야 한다" SyntaxError 를 내는 등 위양성 빌드 실패가 난다(_swarm_execution 과 동일 패턴)
    for f in be_files:
        fp = f.get("file_path", "")
        if fp.endswith(".py") and f.get("code", ""):
            is_be_valid, be_msg = LocalSyntaxChecker.check_python_syntax(f.get("code", ""))
            if not is_be_valid:
                return {"build_status": "failed", "build_error_log": f"[{fp}] {be_msg}", "failed_node": "Backend", "developer_retry_count": current_retry + 1}

    for f in fe_files:
        fp = f.get("file_path", "")
        if fp.endswith((".tsx", ".ts", ".js", ".jsx")) and f.get("code", ""):
            is_fe_valid, fe_msg = LocalSyntaxChecker.check_javascript_syntax(f.get("code", ""))
            if not is_fe_valid:
                return {"build_status": "failed", "build_error_log": f"[{fp}] {fe_msg}", "failed_node": "Frontend", "developer_retry_count": current_retry + 1}

    builder = CodeBuilder(workspace_root=state_obj.workspace_root)
    state_dict = state_obj.model_dump()
    updated_state_dict, results = builder.run(state_dict, all_files_to_write)
    
    if updated_state_dict.get("build_status") == "failed":
        if not has_coding_agent: return {"build_status": "success", "developer_retry_count": 0}
        else: return {"build_status": "failed", "failed_node": ("Frontend" if has_fe else "Backend"), "developer_retry_count": current_retry + 1}

    # ️ [프리뷰/회귀 정합성] frontend/backend_code_summary 를 'LLM 마지막 출력'이 아니라
    #    '디스크의 현재 전체 파일 집합'으로 재구성. 이번 태스크가 일부 파일만 재출력해도(또는 한
    #    파일을 통째로 누락해도) 과거 파일이 디스크에 남아 프리뷰에서 사라지지 않고, 회귀 게이트가
    #    전체 그림을 본다. 미수정 파일은 baseline 과 동일하므로 회귀로 오인되지 않는다.
    out: Dict[str, Any] = {"build_status": "success", "developer_retry_count": 0,
                           "file_index": updated_state_dict.get("file_index", state_obj.file_index)}
    fe_full = _collect_disk_files(state_obj.workspace_root, _FE_OWNED_EXTS)
    be_full = _collect_disk_files(state_obj.workspace_root, _BE_OWNED_EXTS)
    if fe_full:
        out["frontend_code_summary"] = json.dumps({"files": fe_full}, ensure_ascii=False)
    if be_full:
        out["backend_code_summary"] = json.dumps({"files": be_full}, ensure_ascii=False)
    return out

async def run_reviewer(state: Any) -> Dict[str, Any]:
    """Reviewer(개발 엔지니어, 단위 관점) - 코드 정확성·버그·해당 단위 기능 동작 검증 게이트.
    코드리뷰 단계의 PASS/REWORK_DEV/ESCALATE_PM 3분기 및 Git 커밋/WBS 완료 로직 보존, 단계 기준 채점 기록.
    (역할 분리: '전체 통합 정합'은 QA, '고객 RFP 수용'은 Supervisor 가 담당.)"""
    state_obj = ProjectState.model_validate(state)
    # 리뷰 왕복 카운터 - 매 리뷰 실행마다 +1 (route_from_reviewer 가 상한 초과 시 루프 차단)
    hops = getattr(state_obj, "supervisor_hops", 0) + 1

    if getattr(state_obj, "pm_override_reason", ""):
        print(f"⚖️ [Agent] Reviewer: PM의 기각/강행 지시 수용 (사유: {state_obj.pm_override_reason})")
        reviewer_decision = "PASS"
        review_text = "PM 최종 승인 지시: " + state_obj.pm_override_reason
    elif hops >= getattr(config, "GLOBAL_MAX_SUPERVISOR_HOPS", 8):
        #  [재작업 상한] 이 태스크의 리뷰 재작업 예산 소진 - 더 돌리지 않고 best-effort 로 통과시켜
        #    태스크를 완료(DONE)시키고, 미해결 이슈는 상위 게이트(QA 통합검수 / Supervisor 수용검수)로 이관한다.
        #    (예산 소진 태스크를 IN_PROGRESS 로 방치하면 최종 태스크 판정이 안 돼 QA/Supervisor 가 영영 실행 안 됨.)
        print(f"⚠️ [Reviewer] 재작업 상한({hops}) 도달 - best-effort 수용. 미해결 이슈는 QA/Supervisor 로 이관.")
        reviewer_decision = "PASS"
        review_text = "리뷰 재작업 상한 도달 - best-effort 수용(미해결 이슈는 상위 게이트에서 판정)."
    else:
        has_fe_code = bool(_extract_files_from_json(state_obj.frontend_code_summary))
        has_be_code = bool(_extract_files_from_json(state_obj.backend_code_summary))

        #  [심볼 회귀 게이트] 직전 커밋(baseline) 대비 사라진 export/핸들러/입력요소/엔드포인트를
        #    결정적으로 탐지(LLM 0콜). 모든 다른 게이트는 신규 파일만 stateless 로 보므로 '기능 삭제'를
        #    못 잡는다(삭제는 오히려 통과). 이 게이트가 멀티태스크 기능 소실의 최종 안전망.
        from nodes.utils.regression_checker import check_symbol_regression, is_deletion_intended
        _new_files = _extract_files_from_json(state_obj.frontend_code_summary) + _extract_files_from_json(state_obj.backend_code_summary)
        if _new_files:
            _hf = " ".join(getattr(fi, "feedback", "") if not isinstance(fi, dict) else fi.get("feedback", "")
                           for fi in (getattr(state_obj, "human_feedback_queue", []) or []))
            _allow_del = is_deletion_intended(" ".join([getattr(state_obj, "reviewer_feedback", "") or "",
                                                        getattr(state_obj, "pm_override_reason", "") or "", _hf]))
            _baseline_commit = getattr(getattr(state_obj, "git_info", None), "last_commit_hash", "") or ""
            _git = GitManager(state_obj.workspace_root)
            # 파일마다 git subprocess 를 도는 동기 작업 - 이벤트 루프(SSE/API) 동결 방지 위해 스레드로
            reg = await asyncio.to_thread(
                check_symbol_regression,
                _new_files,
                lambda rel: _git.read_file_at_commit(_baseline_commit, rel),
                allow_deletion=_allow_del,
            )
            if not reg.get("ok"):
                errs = reg.get("errors", [])
                print(f"❌ [Supervisor] 심볼 회귀 감지: {len(reg.get('regressions', []))}개 파일에서 기능 소실")
                review_text = (
                    " 회귀 감지 - 직전 버전에 있던 기능/심볼이 이번 출력에서 사라졌습니다:\n- "
                    + "\n- ".join(errs[:6])
                    + "\n\n[수정 지침] 컨텍스트의 '현재 워크스페이스 실제 파일'에 주어진 기존 코드 전부를 보존하고, "
                      "이번 태스크 기능만 추가/수정해 '기존 전부 + 신규'를 합친 완전한 코드를 다시 출력하십시오. "
                      "기존 기능을 의도적으로 제거해야 한다면 그 사유를 명시하십시오."
                )
                cr_scores = dict(getattr(state_obj, "stage_scores", {}) or {})
                cr_scores["CODE_REVIEW"] = 0.0
                cr_log = list(getattr(state_obj, "criteria_log", []) or [])
                cr_log.append({"stage": "CODE_REVIEW", "score": 0.0, "verdict": "REWORK_DEV", "blocking_fails": ["symbol_regression"]})
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

        # ️ 프론트 렌더 검증 테스트러너: 실제 renderToString 으로 동작 확인 (실패 시 LLM 리뷰 없이 즉시 재작업)
        render_note = ""
        quality_advisory = ""  # 정적 품질 백스톱 권고(하드 차단 아님) - LLM 리뷰어 프롬프트에 주입
        if has_fe_code:
            from nodes.utils.render_checker import check_frontend_render
            fe_files = _extract_files_from_json(state_obj.frontend_code_summary)
            # 최대 60초 동기 subprocess - 이벤트 루프 동결 방지 위해 스레드로
            render = await asyncio.to_thread(check_frontend_render, fe_files)
            if not render.get("ok") and not render.get("skipped"):
                errs = render.get("errors", [])
                print(f"❌ [TestRunner] 프론트 렌더 검증 실패: {errs}")
                review_text = (
                    "️ 프론트엔드 렌더 검증 실패 - 생성 코드가 실제로 렌더되지 않습니다:\n- "
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
                render_note += f"\n([OK] 프론트 렌더 검증 통과 - renderToString {render.get('rendered', 0)}자)"

            # ⌨️ 입력 동작(인터랙티비티) 정적 검증: value 제어 input 에 onChange 누락 = 입력 불가(동결)
            #    renderToString 은 '렌더됨'만 보장하고 '입력됨'은 못 잡으므로 별도 정적 분석으로 차단.
            from nodes.utils.interactivity_checker import check_frontend_interactivity
            interact = check_frontend_interactivity(fe_files)
            if not interact.get("ok"):
                errs = interact.get("errors", [])
                n_frozen = len(interact.get("frozen", []))
                print(f"❌ [TestRunner] 프론트 입력 동작 검증 실패: 동결 입력 {n_frozen}건")
                review_text = (
                    "⌨️ 프론트엔드 입력 동작 검증 실패 - 사용자가 값을 입력할 수 없는 '동결된 입력 필드'가 있습니다:\n- "
                    + "\n- ".join(errs[:5])
                    + "\n\n[수정 지침] 제어 컴포넌트(value={...})에는 반드시 onChange 핸들러와 useState 를 연결하십시오. "
                      "표시 전용 필드라면 readOnly 를 명시하고, 비제어 입력이면 value 대신 defaultValue 를 사용하십시오."
                )
                cr_scores = dict(getattr(state_obj, "stage_scores", {}) or {})
                cr_scores["CODE_REVIEW"] = 0.0
                cr_log = list(getattr(state_obj, "criteria_log", []) or [])
                cr_log.append({"stage": "CODE_REVIEW", "score": 0.0, "verdict": "REWORK_DEV", "blocking_fails": ["frontend_interactivity"]})
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
            else:
                render_note += "\n([OK] 입력 동작 검증 통과 - 제어 입력에 onChange 연결 확인)"

            #  정적 품질 백스톱(Phase 2): 컴포넌트 분리/빈상태/디자인토큰 - 하드 차단이 아니라
            #    권고로 LLM 리뷰어 판단에 주입(오탐 재작업 폭증 방지). frontend_skill/design_system 가
            #    1차 규율, 이 검사기는 그 규율이 무너진 경우를 잡는 백스톱.
            from nodes.utils.quality_checker import check_code_quality
            quality = check_code_quality(fe_files)
            if not quality.get("ok") and not quality.get("skipped"):
                _qw = quality.get("warnings", [])
                quality_advisory = "\n".join(f"- {w}" for w in _qw[:6])
                print(f"⚠️ [QualityCheck] 정적 품질 권고 {len(_qw)}건 (리뷰 판단에 반영)")
                render_note += f"\n(⚠️ 정적 품질 권고 {len(_qw)}건 - 컴포넌트 분리/빈상태/디자인토큰)"
            else:
                render_note += "\n([OK] 정적 품질 점검 통과 - 컴포넌트 분리/빈상태/디자인토큰)"

        # ⚙️ 백엔드 스모크 테스트러너: 격리 부팅 + 엔드포인트 검증 (실패 시 즉시 재작업)
        if has_be_code:
            from nodes.utils.backend_smoke import check_backend_smoke
            be_files = _extract_files_from_json(state_obj.backend_code_summary)
            # 최대 45초 동기 subprocess(격리 부팅) - 이벤트 루프 동결 방지 위해 스레드로
            smoke = await asyncio.to_thread(check_backend_smoke, be_files)
            if not smoke.get("ok") and not smoke.get("skipped"):
                errs = smoke.get("errors", [])
                print(f"❌ [TestRunner] 백엔드 스모크 실패: {errs}")
                review_text = (
                    "⚙️ 백엔드 스모크 실패 - 생성 코드가 정상 부팅/응답하지 않습니다:\n- "
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
                render_note += f"\n([OK] 백엔드 스모크 통과 - 라우트 {smoke.get('routes', 0)}개" + (f", 경고 {len(_w)}건" if _w else "") + ")"

        if not has_fe_code and not has_be_code:
            print("⏩ [Smart Bypass] 코드 작성 내역이 없으므로 리뷰를 통과(PASS)합니다.")
            reviewer_decision = "PASS"
            review_text = "코드 작성 없음 - 설계/문서 업데이트 정상 완료."
        else:
            print(f" [Agent] Reviewer 비동기 코드 리뷰 및 의사결정 분류 중...{render_note}")
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
            # 정적 품질 백스톱 권고를 리뷰 판단에 주입 - 단, 기능 동작에 지장 없는 사소한 권고만으로는
            # REWORK_DEV 를 남발하지 말 것(재작업 비용 통제). 명백한 분리 결여/디자인 난맥만 반영.
            if quality_advisory:
                prompt += (
                    "\n\n[정적 품질 점검 권고 - 아래를 리뷰에 참고하라. 기능 동작은 정상이나 품질 개선 여지가 있는 항목이다.\n"
                    " 심각한 분리 결여/디자인 난맥이면 REWORK_DEV 사유로 포함하되, 사소한 권고만이라면 PASS 해도 된다]\n"
                    + quality_advisory
                )
            #  FIX: 리뷰어 역시 빠르고 비용 효율적인 Flash 모델로 롤백 (자유 스키마 JSON 모드)
            output = await gateway.aexecute(state_obj, prompt, is_heavy=False, output_mode="json")
            output_str = _safe_str(output)
            
            reviewer_decision = "PASS"
            review_text = output_str
            try:
                clean_str = output_str.strip()
                # 1차: 게이트웨이가 이미 복구한 JSON 일 가능성이 높으므로 전체 파싱을 먼저 시도
                try:
                    data = json.loads(clean_str)
                except Exception:
                    # 2차: 코드펜스/서술 혼입 시 추출 - 반드시 greedy(*). non-greedy(*?)는 feedback 안의
                    # 첫 '}' 에서 잘려 파싱이 깨지고, except 폴백이 REWORK 를 PASS 로 둔갑시킨다
                    md_match = re.search(r'\x60{3}(?:json)?\s*(\{[\s\S]*\})\s*\x60{3}', clean_str)
                    if md_match: clean_str = md_match.group(1)
                    else:
                        alt_match = re.search(r'(\{[\s\S]*\})', clean_str)
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


# 하위 호환 별칭: 기존 import(run_supervisor)를 깨지 않도록 - 이제 run_supervisor 는 '고객사 수용검수' 노드(아래 정의).
# (구 run_reviewer 별칭 사용처는 run_reviewer 로 통일됨.)


def _format_gate_report(title: str, result: Dict[str, Any]) -> str:
    """score_stage 결과를 사람이 읽는 검수 리포트(마크다운)로 정리."""
    lines = [f"## {title}", f"- 판정: {result.get('verdict')} · 점수 {result.get('score')}"]
    per = result.get("per_check", {}) or {}
    if per:
        lines.append("- 기준별 점수:")
        for k, v in per.items():
            lines.append(f"  - {'[OK]' if v >= 0.5 else '❌'} {k}: {v}")
    if result.get("blocking_fails"):
        lines.append(f"-  치명 미달: {', '.join(result['blocking_fails'])}")
    if result.get("rationale"):
        lines.append(f"- 총평: {result['rationale']}")
    return "\n".join(lines)


async def run_qa(state: Any) -> Dict[str, Any]:
    """QA(수행사 인도 전 통합 검수) - 기획서·설계서 대비 통합 구현 정합/인도 적합성 평가.
    PASS → Supervisor(고객 수용검수), FAIL → Tech_Lead 재작업. (RFP 비즈니스 수용은 Supervisor 담당.)"""
    state_obj = ProjectState.model_validate(state)
    print(" [Agent] QA 통합 검수(설계서 대비) 진행 중...")
    if state_obj.build_status == "failed":
        report = f"## QA 통합 검수\n- 판정: FAIL (빌드 실패)\n- 에러:\n{state_obj.build_error_log}"
        print(" [QA] 판정: FAIL (빌드 실패)")
        return {"qa_report_summary": report, "qa_verdict": "FAIL", "current_stage": "QA",
                "reviewer_decision": "REWORK_DEV", "reviewer_feedback": report}

    from nodes.utils.scoring import score_stage
    from nodes.utils.test_runner import run_background_tests_and_scans, format_test_results_for_qa
    
    #  [Phase 2] 백그라운드 자동화 테스트 및 스캔 실행
    print("⏳ [QA] 백그라운드 자동화 테스트 및 보안 스캔 실행 중...")
    # pytest/bandit/npm build 등 최대 ~2분 동기 subprocess - 이벤트 루프 동결 방지 위해 스레드로
    test_results = await asyncio.to_thread(run_background_tests_and_scans, state_obj.workspace_root)
    test_report_md = format_test_results_for_qa(test_results)
    if test_report_md:
        print(" [QA] 결정론적 테스트 지표 확보 완료.")

    result = await score_stage(state_obj, "QA", extra_context=test_report_md)
    verdict = "PASS" if result.get("verdict") == "PASS" else "FAIL"
    report = _format_gate_report("QA 통합 검수(기획서·설계서 대비)", result)
    if test_report_md:
        report += f"\n\n{test_report_md}"
        
    print(f" [QA] 판정: {verdict} (점수 {result.get('score')})")
    updates = {"qa_report_summary": report, "qa_verdict": verdict, "current_stage": "QA"}
    if verdict == "FAIL":
        # 설계대로 미구현/통합 결함 → 실무진 재작업(REWORK_DEV→Tech_Lead). 미흡 내역을 피드백으로 전달.
        updates["reviewer_decision"] = "REWORK_DEV"
        updates["reviewer_feedback"] = " [QA 통합 검수 미달 - 설계/통합 결함]\n" + report
    return updates


async def run_supervisor(state: Any) -> Dict[str, Any]:
    """Supervisor(발주 고객사 대리인) - RFP 계약 대비 비즈니스 수용·완료 검수(엄격).
    PASS → ManualWriter, REJECT → PM(ESCALATE_PM, 요구·기능 재조정). route_from_supervisor 가 분기.
    보수적 상한: 수용 시도 2회 초과 시 무한 루프 대신 종료(인간 검토)."""
    state_obj = ProjectState.model_validate(state)
    print("‍⚖️ [Agent] Supervisor 최종 수용검수(RFP 대비) 진행 중...")
    attempts = dict(getattr(state_obj, "stage_attempt_counts", {}) or {})
    attempts["SUPERVISOR"] = attempts.get("SUPERVISOR", 0) + 1

    if state_obj.build_status == "failed":
        report = "## 고객사 수용검수\n- 판정: REJECT (빌드 실패로 인도 불가)"
        return {"supervisor_report_summary": report, "supervisor_verdict": "REJECT",
                "current_stage": "SUPERVISOR", "stage_attempt_counts": attempts}

    from nodes.utils.scoring import score_stage
    result = await score_stage(state_obj, "SUPERVISOR")
    verdict = "PASS" if result.get("verdict") == "PASS" else "REJECT"
    report = _format_gate_report("고객사 최종 수용검수(RFP 대비)", result)
    print(f"‍⚖️ [Supervisor] 수용 판정: {verdict} (점수 {result.get('score')} / 시도 {attempts['SUPERVISOR']})")
    updates = {"supervisor_report_summary": report, "supervisor_verdict": verdict,
               "current_stage": "SUPERVISOR", "stage_attempt_counts": attempts}
    if verdict == "REJECT":
        # 요구·비즈니스 미충족 → PM 상신(요구·기능 재조정). 미흡 내역 전달.
        updates["reviewer_decision"] = "ESCALATE_PM"
        updates["reviewer_feedback"] = "‍⚖️ [고객사 수용검수 반려 - 요구·완성도 미달]\n" + report
    return updates

async def run_manual_writer(state: Any) -> Dict[str, Any]:
    state_obj = ProjectState.model_validate(state)

    # 빌드 실패 또는 프론트엔드 코드가 없으면 매뉴얼 생략
    if state_obj.build_status == "failed" or not state_obj.frontend_code_summary:
        print("⏩ [Smart Bypass] 빌드 실패 또는 코드 없음 - 사용자 매뉴얼 생성을 건너뜁니다.")
        return {}

    print(" [Agent] Technical Writer 사용자 매뉴얼 작성 중...")
    skill = _load_skill(agent_skill("ManualWriter", "manual_skill", template_id=state_obj.template_id))
    prompt = (
        f"{skill}\n\n"
        f"[참조: 기획서(PRD)]\n{state_obj.prd_summary}\n\n"
        f"[참조: 프론트엔드 코드 요약]\n{state_obj.frontend_code_summary}\n\n"
        f"[참조: QA 최종 검증 리포트]\n{state_obj.qa_report_summary}"
    )
    # B2: 매뉴얼은 요약/코드가 이미 프롬프트에 임베드돼 있어 워크스페이스 재주입 불필요(light=True),
    #     사용자 매뉴얼은 고난도 추론이 아니므로 Flash(is_heavy=False)로 충분 - 비용 절감.
    # output_mode 미지정 시 기본 'code'(CodeOutput 구조화 출력 강제)라 매뉴얼이 files JSON 블롭으로 산출됨
    output = await gateway.aexecute(state_obj, prompt, is_heavy=False, light=True, output_mode="document")
    print("[OK] [Agent] 사용자 매뉴얼 작성 완료.")
    return {"user_manual_summary": _safe_str(output)}