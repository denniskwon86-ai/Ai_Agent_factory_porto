# ==========================================
# 단계별 성공 기준(Rubric) 단일 진실 공급원(SSOT) — V5.1
# 토론 비평가와 Supervisor 게이트가 동일 기준을 공유한다.
# 각 check는 type='deterministic'(LLM 0콜, 코드 평가) 또는 'llm_judge'(Flash 1콜).
# ==========================================
import os
import json
import config


def _rfp_text(state) -> str:
    return (getattr(state, "rfp_summary", "") or "").strip()


def _prd_text(state) -> str:
    return (getattr(state, "prd_summary", "") or "").strip()


def _read_wbs_tasks(state) -> list:
    root = getattr(state, "workspace_root", "") or ""
    path = os.path.join(root, config.WBS_FILE)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("tasks", []) or []
    except Exception:
        pass
    return []


# --- Deterministic 검사 레지스트리 (LLM 호출 0회로 핵심 결함 차단) ---
def _check_rfp_min_length(state) -> bool:
    return len(_rfp_text(state)) >= config.RFP_MIN_LENGTH


def _check_prd_min_length(state) -> bool:
    return len(_prd_text(state)) >= config.PRD_MIN_LENGTH


def _check_wbs_min_tasks(state) -> bool:
    return len(_read_wbs_tasks(state)) >= config.WBS_MIN_TASKS


def _check_agents_nonempty(state) -> bool:
    tasks = _read_wbs_tasks(state)
    if not tasks:
        return False
    return all(len(t.get("required_agents", []) or []) > 0 for t in tasks)


def _check_adr_present(state) -> bool:
    return len(getattr(state, "architecture_decisions", []) or []) >= 1


def _check_build_success(state) -> bool:
    return getattr(state, "build_status", "") == "success"


DETERMINISTIC_CHECKS = {
    "rfp_min_length": _check_rfp_min_length,
    "prd_min_length": _check_prd_min_length,
    "wbs_min_tasks": _check_wbs_min_tasks,
    "agents_nonempty": _check_agents_nonempty,
    "adr_present": _check_adr_present,
    "build_success": _check_build_success,
}


# --- 단계별 Rubric ---
# checks[].type: 'deterministic' | 'llm_judge'
# hard_fail_checks: 하나라도 실패하면 즉시 ROLLBACK/ESCALATE (인간 개입)
STAGE_RUBRICS = {
    "RFP": {
        "checks": [
            {"id": "rfp_min_length", "desc": "요구정의서 본문이 최소 분량 이상", "weight": 1, "type": "deterministic"},
            {"id": "purpose_clear", "desc": "프로그램의 목적·의도(왜 만드는가, 해결할 문제)가 명확히 정의됨", "weight": 2, "type": "llm_judge"},
            {"id": "must_have_components", "desc": "사용자 의도에서 직접 도출된 핵심 요건이 REQ-ID 체크리스트로 빠짐없이 명시됨(아이디어 규모에 비례 — 단순 앱은 소수여도 OK, 단 요청 안 한 엔터프라이즈 기능 환각은 감점)", "weight": 2, "type": "llm_judge"},
            {"id": "acceptance_criteria", "desc": "각 핵심 요구의 인수 기준(완성·정상작동 판정 방법)이 제시됨", "weight": 1, "type": "llm_judge"},
        ],
        "pass_threshold": 0.8,
        "hard_fail_checks": ["rfp_min_length"],
    },
    "PLANNING": {
        "checks": [
            {"id": "prd_min_length", "desc": "PRD 본문이 최소 분량 이상 (빈약한 3~5줄 기획서 차단)", "weight": 1, "type": "deterministic"},
            {"id": "func_req_5", "desc": "기능 요구사항(FR)이 FR-ID로 5개 이상, 각 우선순위(High/Med/Low)와 함께 구체적으로 명시됨", "weight": 2, "type": "llm_judge"},
            {"id": "nonfunc_req", "desc": "비기능 요구사항(성능/보안/확장성/가용성)이 구체적 수치·기준으로 제시됨", "weight": 1, "type": "llm_judge"},
            {"id": "measurable_ac", "desc": "사용자 스토리(US)별 측정 가능한 수용 기준(AC)이 각 2개 이상 제시됨", "weight": 1, "type": "llm_judge"},
            {"id": "data_domain", "desc": "핵심 데이터 엔티티와 엔티티 간 관계(1:N, N:M 등)가 명시됨 (Architect가 스키마 설계에 사용)", "weight": 1, "type": "llm_judge"},
            {"id": "scope_defined", "desc": "In-Scope와 Out-of-Scope가 (제외 이유와 함께) 명확히 구분됨", "weight": 1, "type": "llm_judge"},
            {"id": "rfp_traceability", "desc": "각 FR이 어떤 RFP 요구(REQ-ID)를 충족하는지 추적성이 드러남 (RFP가 있을 때)", "weight": 1, "type": "llm_judge"},
        ],
        "pass_threshold": 0.8,
        "hard_fail_checks": ["prd_min_length"],
    },
    "PMO": {
        "checks": [
            {"id": "wbs_min_tasks", "desc": "WBS 태스크가 4개 이상으로 분할됨", "weight": 2, "type": "deterministic"},
            {"id": "agents_nonempty", "desc": "각 태스크의 required_agents가 비어있지 않음", "weight": 1, "type": "deterministic"},
        ],
        "pass_threshold": 1.0,
        "hard_fail_checks": ["wbs_min_tasks"],
    },
    "ARCHITECTURE": {
        "checks": [
            {"id": "component_boundary", "desc": "컴포넌트/모듈 경계와 책임이 정의됨", "weight": 2, "type": "llm_judge"},
            {"id": "data_flow", "desc": "데이터 흐름 또는 핵심 데이터 모델이 명시됨", "weight": 1, "type": "llm_judge"},
            {"id": "tech_stack", "desc": "기술 스택과 그 선택 근거가 제시됨", "weight": 1, "type": "llm_judge"},
        ],
        "pass_threshold": 0.7,
        "hard_fail_checks": [],
    },
    "TECH_SPEC": {
        "checks": [
            {"id": "file_responsibility", "desc": "파일/모듈별 책임이 구체적으로 명시됨", "weight": 2, "type": "llm_judge"},
            {"id": "api_contract", "desc": "API 계약 또는 인터페이스 규격이 정의됨", "weight": 1, "type": "llm_judge"},
            {"id": "prd_traceability", "desc": "PRD 요구사항과의 추적성(어떤 FR을 구현하는지)이 드러남", "weight": 1, "type": "llm_judge"},
        ],
        "pass_threshold": 0.7,
        "hard_fail_checks": [],
    },
    # Reviewer(개발 엔지니어, 단위 관점): 코드 정확성·버그·해당 단위 기능 동작
    "CODE_REVIEW": {
        "checks": [
            {"id": "build_success", "desc": "빌드/문법 검사 통과", "weight": 3, "type": "deterministic"},
            {"id": "unit_correctness", "desc": "이번 태스크 코드에 명백한 버그/오작동/누락 로직이 없고, 작성한 단위 기능이 실제로 동작하도록 상태·핸들러가 올바르게 연결됨", "weight": 2, "type": "llm_judge"},
            {"id": "code_quality", "desc": "가독성·구조(과도한 단일 거대 파일 지양, 적절한 컴포넌트/함수 분리)·타입 적용이 양호함", "weight": 1, "type": "llm_judge"},
        ],
        "pass_threshold": 0.8,
        "hard_fail_checks": ["build_success"],
    },
    # QA(수행사 인도 전 검수, 전체/통합 관점): 기획서·설계서대로 옳게 통합 구현되어 고객 인도 가능한가
    "QA": {
        "checks": [
            {"id": "build_success", "desc": "빌드/문법 검사 통과", "weight": 2, "type": "deterministic"},
            {"id": "design_conformance", "desc": "구현이 아키텍처·기술명세(설계서)의 파일 책임·인터페이스·데이터 모델대로 되어 있음", "weight": 2, "type": "llm_judge"},
            {"id": "prd_fr_coverage", "desc": "PRD의 기능 요구(FR)가 누락 없이 전체적으로 통합 구현됨(부분/더미 아님)", "weight": 2, "type": "llm_judge"},
            {"id": "integration_soundness", "desc": "모듈/컴포넌트/API 연동과 핵심 E2E 흐름이 끊김 없이 동작할 구조임", "weight": 1, "type": "llm_judge"},
            {"id": "delivery_readiness", "desc": "명백한 미완성·깨진 화면·미연결 기능이 없어 고객에게 인도할 수 있는 수준임", "weight": 1, "type": "llm_judge"},
        ],
        "pass_threshold": 0.8,
        "hard_fail_checks": ["build_success"],
        "judge_heavy": True,
        "judge_persona": "qa_skill",
    },
    # Supervisor(발주 고객사 대리인, 비즈니스 수용): RFP 계약대로인가, 실무에 써먹나, 완료 검수 통과인가 (엄격)
    "SUPERVISOR": {
        "checks": [
            {"id": "rfp_business_coverage", "desc": "RFP의 필수 비즈니스 요구(REQ-ID)가 결과물에서 빠짐없이 실제로 충족됨", "weight": 3, "type": "llm_judge"},
            {"id": "usability_real_work", "desc": "실제 업무에 바로 써먹을 수 있는 수준의 완결성·사용성(핵심 사용자 시나리오가 매끄럽게 수행됨)", "weight": 2, "type": "llm_judge"},
            {"id": "completeness_polish", "desc": "빈틈·미흡·거친 마감이 없어 완성도가 인도·검수 통과 수준임(엄격하게 판단)", "weight": 2, "type": "llm_judge"},
            {"id": "acceptance_signoff", "desc": "발주사 입장에서 용역비를 지불하고 완료 수용해도 될 만한 종합 품질인가", "weight": 1, "type": "llm_judge"},
        ],
        "pass_threshold": 0.85,
        "hard_fail_checks": ["rfp_business_coverage"],
        "judge_heavy": True,
        "judge_persona": "supervisor_skill",
    },
}
