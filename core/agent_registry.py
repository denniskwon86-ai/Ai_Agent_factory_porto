"""
에이전트 마스터 레지스트리 (범용 멀티에이전트 플랫폼 — Phase 1)

목표: 그래프에 하드코딩된 "어떤 에이전트가, 무슨 역할로, 어떤 스킬·모델로, 어떤 순서로,
어디서 인간 검토(HOTL)를 받는가"를 외부 JSON(SSOT)으로 분리한다.

- 프롬프트는 이미 skills/*.md로 분리되어 있으므로, 본 레지스트리는 그 메타데이터를 기술한다.
- 파일이 없으면 DEFAULT_REGISTRY(현재 그래프와 동일)를 사용한다 → 무중단/하위호환.
- Phase 1에서 실제 런타임에 반영되는 것: HOTL 중단점(get_interrupt_after).
  (노드/엣지/라우팅의 동적 생성은 Phase 2 build_graph_from_registry에서 다룬다)
"""
import json
import os
from typing import Any, Dict, List

# 레지스트리 JSON 위치(루트). 서버 CWD 기준.
REGISTRY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents_registry.json")

# 에이전트 메타 스키마 키(누락 시 보정)
_AGENT_FIELDS = {
    "id": "",            # 그래프 노드 ID (반드시 그래프와 일치)
    "name_ko": "",       # 표시 이름
    "role": "",          # 역할 설명(편집 가능)
    "skill": "",         # skills/<skill>.md (없으면 "")
    "stage": "",         # criteria/config의 단계 키
    "category": "execution",  # planning | execution | review | system (UI 그룹핑)
    "model_tier": "pro", # pro | flash (논리 티어 — config.ENGINE_TIERS)
    "order": 0,          # 파이프라인 표시 순서
    "enabled": True,     # 비활성 시 파이프라인에서 제외(Phase 2 빌더가 사용)
    "hotl_after": False, # 이 노드 직후 인간 검토 중단점(현재 그래프 interrupt_after에 즉시 반영)
    "debate": False,     # 토론·합의 루프 적용 여부(표시용 — config.DEBATE_STAGES와 정합)
    "llm": True,         # LLM 호출 노드 여부(CodeBuilder 등 시스템 노드는 False)
}

# 현재 하드코딩 그래프(core/agent_graph.py)와 1:1로 동일한 기본 레지스트리.
# id는 그래프의 add_node 이름과 정확히 일치해야 한다.
DEFAULT_REGISTRY: Dict[str, Any] = {
    "version": 1,
    "pipeline_name": "소프트웨어 개발 팩토리",
    "description": "한 줄 아이디어 → RFP → 기획 → 설계 → 구현 → 빌드 → 검수 → QA → 매뉴얼까지 자율 수행하는 기본 파이프라인",
    "agents": [
        {"id": "RFP_Analyst", "name_ko": "RFP 분석가", "role": "발주 의도를 구조화한 요구사항 정의서(RFP) 작성", "skill": "rfp_skill",
         "stage": "RFP", "category": "planning", "model_tier": "pro", "order": 1, "enabled": True, "hotl_after": True, "debate": True, "llm": True},
        {"id": "Master_PM", "name_ko": "마스터 PM", "role": "RFP 기반 심층 기획서(PRD) 작성", "skill": "pm_skill",
         "stage": "PLANNING", "category": "planning", "model_tier": "pro", "order": 2, "enabled": True, "hotl_after": False, "debate": True, "llm": True},
        {"id": "Master_PMO", "name_ko": "마스터 PMO", "role": "PRD를 실행 가능한 WBS(작업분해도)로 분할·에이전트 배정", "skill": "pmo_skill",
         "stage": "PMO", "category": "planning", "model_tier": "pro", "order": 3, "enabled": True, "hotl_after": True, "debate": False, "llm": True},
        {"id": "Architect", "name_ko": "아키텍트", "role": "시스템 아키텍처·ADR 설계", "skill": "architect_skill",
         "stage": "ARCHITECTURE", "category": "execution", "model_tier": "pro", "order": 4, "enabled": True, "hotl_after": False, "debate": True, "llm": True},
        {"id": "Tech_Lead", "name_ko": "테크리드", "role": "기술 사양·인터페이스 상세 설계", "skill": "tech_lead_skill",
         "stage": "TECH_SPEC", "category": "execution", "model_tier": "pro", "order": 5, "enabled": True, "hotl_after": True, "debate": True, "llm": True},
        {"id": "Backend", "name_ko": "백엔드 개발자", "role": "FastAPI 백엔드 코드 생성", "skill": "backend_skill",
         "stage": "EXECUTION", "category": "execution", "model_tier": "pro", "order": 6, "enabled": True, "hotl_after": False, "debate": False, "llm": True},
        {"id": "Frontend", "name_ko": "프론트엔드 개발자", "role": "React 프론트엔드 코드 생성", "skill": "frontend_skill",
         "stage": "EXECUTION", "category": "execution", "model_tier": "pro", "order": 7, "enabled": True, "hotl_after": False, "debate": False, "llm": True},
        {"id": "CodeBuilder", "name_ko": "코드 빌더", "role": "생성된 코드를 워크스페이스에 원자적으로 기록(비-LLM 시스템 노드)", "skill": "",
         "stage": "BUILD", "category": "system", "model_tier": "flash", "order": 8, "enabled": True, "hotl_after": False, "debate": False, "llm": False},
        {"id": "Reviewer", "name_ko": "슈퍼바이저(리뷰어)", "role": "코드 리뷰·렌더/스모크 검증·재작업 판정", "skill": "reviewer_skill",
         "stage": "CODE_REVIEW", "category": "review", "model_tier": "pro", "order": 9, "enabled": True, "hotl_after": False, "debate": False, "llm": True},
        {"id": "QA", "name_ko": "QA 엔지니어", "role": "RFP 추적성 기반 최종 통합 검증", "skill": "qa_skill",
         "stage": "QA", "category": "review", "model_tier": "pro", "order": 10, "enabled": True, "hotl_after": False, "debate": False, "llm": True},
        {"id": "ManualWriter", "name_ko": "매뉴얼 작성가", "role": "최종 사용자 매뉴얼 작성", "skill": "manual_skill",
         "stage": "MANUAL", "category": "review", "model_tier": "flash", "order": 11, "enabled": True, "hotl_after": False, "debate": False, "llm": True},
    ],
}


def _coerce_agent(a: Dict[str, Any]) -> Dict[str, Any]:
    """누락 필드 보정 + 타입 강제."""
    out = {}
    for k, default in _AGENT_FIELDS.items():
        v = a.get(k, default)
        if isinstance(default, bool):
            v = bool(v)
        elif isinstance(default, int) and not isinstance(default, bool):
            try:
                v = int(v)
            except (TypeError, ValueError):
                v = default
        else:
            v = v if v is not None else default
        out[k] = v
    return out


def _normalize(reg: Dict[str, Any]) -> Dict[str, Any]:
    agents = [_coerce_agent(a) for a in reg.get("agents", []) if isinstance(a, dict) and a.get("id")]
    agents.sort(key=lambda x: x.get("order", 0))
    return {
        "version": int(reg.get("version", 1)),
        "pipeline_name": str(reg.get("pipeline_name", DEFAULT_REGISTRY["pipeline_name"])),
        "description": str(reg.get("description", "")),
        "agents": agents,
    }


def load_registry() -> Dict[str, Any]:
    """레지스트리 로드. 파일이 없거나 손상 시 DEFAULT로 안전 폴백."""
    if not os.path.exists(REGISTRY_PATH):
        return _normalize(DEFAULT_REGISTRY)
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        reg = _normalize(data)
        if not reg["agents"]:
            return _normalize(DEFAULT_REGISTRY)
        return reg
    except Exception:
        # 손상된 파일이 그래프 부팅을 막지 않도록 DEFAULT로 폴백
        return _normalize(DEFAULT_REGISTRY)


def save_registry(reg: Dict[str, Any]) -> Dict[str, Any]:
    """레지스트리 검증 후 JSON으로 영속화. 정규화된 레지스트리를 반환."""
    norm = _normalize(reg)
    if not norm["agents"]:
        raise ValueError("최소 1개 이상의 에이전트가 필요합니다.")
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(norm, f, ensure_ascii=False, indent=2)
    return norm


def reset_registry() -> Dict[str, Any]:
    """기본 레지스트리로 초기화(파일 삭제)."""
    try:
        if os.path.exists(REGISTRY_PATH):
            os.remove(REGISTRY_PATH)
    except Exception:
        pass
    return _normalize(DEFAULT_REGISTRY)


def get_interrupt_after(default: List[str] = None) -> List[str]:
    """HOTL 중단점 = enabled 이면서 hotl_after=True 인 에이전트 id 목록(파이프라인 순서).
    레지스트리 로드 실패/빈 결과 시 호출측이 넘긴 default(현재 그래프 기본값)로 폴백."""
    try:
        reg = load_registry()
        ids = [a["id"] for a in reg["agents"] if a.get("enabled", True) and a.get("hotl_after", False)]
        if ids:
            return ids
    except Exception:
        pass
    return default if default is not None else ["RFP_Analyst", "Master_PMO", "Tech_Lead"]


def agent_meta(agent_id: str) -> dict:
    """레지스트리에서 해당 에이전트 메타를 반환(미존재/오류 시 {})."""
    try:
        for a in load_registry().get("agents", []):
            if a.get("id") == agent_id:
                return a
    except Exception:
        pass
    return {}


def agent_skill(agent_id: str, default: str = "") -> str:
    """노드의 스킬 파일명을 레지스트리에서 조회(제어판 override 반영). 미설정 시 default(현행 동작 보존)."""
    return agent_meta(agent_id).get("skill") or default
