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
import re
from typing import Any, Dict, List

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 레지스트리 JSON 위치(루트). 서버 CWD 기준. = "default" 템플릿(SW 파이프라인)의 저장소.
REGISTRY_PATH = os.path.join(_ROOT, "agents_registry.json")

# ── 다중 워크플로우 템플릿 (Copy 모델) ──────────────────────────────────────────
# 기존 단일 레지스트리(agents_registry.json) = "default" 템플릿(SW 파이프라인). 보존·하위호환.
# 추가 템플릿은 templates/<id>.json 에 저장(복사로 생성, 기존은 불변). 작업은 자기 템플릿으로 실행(T2).
TEMPLATES_DIR = os.path.join(_ROOT, "templates")
DEFAULT_TEMPLATE_ID = "default"
_TID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
# templates/ 에 있으나 워크플로우 템플릿이 아닌 예약 설정 파일(목록 노출 제외).
# output_formats.json 은 format_control 이 출력 포맷 정의로 사용한다.
_RESERVED_TEMPLATE_FILES = {"output_formats.json"}

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
    "position": None,    # UI 노드 위치
    "is_start": False,   # 시작점 여부
    "is_end": False,     # 종료점 여부
    "is_framework": False, # 시뮬레이션 프레임워크 고정 에이전트 여부
    "output_format": "", # 포맷 마스터의 출력 양식 ID (빈 값이면 시스템 프롬프트만 사용)
}

# 현재 하드코딩 그래프(core/agent_graph.py)와 1:1로 동일한 기본 레지스트리.
# id는 그래프의 add_node 이름과 정확히 일치해야 한다.
DEFAULT_REGISTRY: Dict[str, Any] = {
    "id": "default",
    "version": 1,
    "pipeline_name": "소프트웨어 개발 팩토리",
    "description": "한 줄 아이디어 → RFP → 기획 → 설계 → 구현 → 빌드 → 검수 → QA → 매뉴얼까지 자율 수행하는 기본 파이프라인",
    "deliverable_type": "software_app",
    "agents": [
        {"id": "RFP_Analyst", "name_ko": "RFP 분석가", "role": "발주 의도를 구조화한 요구사항 정의서(RFP) 작성", "skill": "rfp_skill",
         "stage": "RFP", "category": "planning", "model_tier": "pro", "order": 1, "enabled": True, "hotl_after": True, "debate": True, "llm": True},
        {"id": "Master_PM", "name_ko": "마스터 PM", "role": "RFP 기반 심층 기획서(PRD) 작성", "skill": "pm_skill",
         "stage": "PLANNING", "category": "planning", "model_tier": "pro", "order": 2, "enabled": True, "hotl_after": True, "debate": True, "llm": True},
        {"id": "UIDesigner", "name_ko": "UI 디자이너", "role": "기획서 기반 To-Be UI/UX 화면 목업(HTML/CSS) 생성", "skill": "ui_designer_skill",
         "stage": "UI_DESIGN", "category": "planning", "model_tier": "pro", "order": 3, "enabled": True, "hotl_after": False, "debate": True, "llm": True},
        {"id": "VisionQA", "name_ko": "비전 QA", "role": "생성된 UI 화면을 시각적으로 검수", "skill": "",
         "stage": "VISION_QA", "category": "planning", "model_tier": "pro", "order": 4, "enabled": True, "hotl_after": True, "debate": False, "llm": True},
        {"id": "Master_PMO", "name_ko": "마스터 PMO", "role": "PRD를 실행 가능한 WBS(작업분해도)로 분할·에이전트 배정", "skill": "pmo_skill",
         "stage": "PMO", "category": "planning", "model_tier": "pro", "order": 5, "enabled": True, "hotl_after": True, "debate": False, "llm": True},
        {"id": "Architect", "name_ko": "아키텍트", "role": "시스템 아키텍처·ADR 설계", "skill": "architect_skill",
         "stage": "ARCHITECTURE", "category": "execution", "model_tier": "pro", "order": 6, "enabled": True, "hotl_after": False, "debate": True, "llm": True},
        {"id": "Tech_Lead", "name_ko": "테크리드", "role": "기술 사양·인터페이스 상세 설계", "skill": "tech_lead_skill",
         "stage": "TECH_SPEC", "category": "execution", "model_tier": "pro", "order": 7, "enabled": True, "hotl_after": False, "debate": True, "llm": True},
        {"id": "Backend", "name_ko": "백엔드 개발자", "role": "FastAPI 백엔드 코드 생성", "skill": "backend_skill",
         "stage": "EXECUTION", "category": "execution", "model_tier": "pro", "order": 8, "enabled": True, "hotl_after": False, "debate": False, "llm": True},
        {"id": "Frontend", "name_ko": "프론트엔드 개발자", "role": "React 프론트엔드 코드 생성", "skill": "frontend_skill",
         "stage": "EXECUTION", "category": "execution", "model_tier": "pro", "order": 9, "enabled": True, "hotl_after": False, "debate": False, "llm": True},
        {"id": "CodeBuilder", "name_ko": "코드 빌더", "role": "생성된 코드를 워크스페이스에 원자적으로 기록(비-LLM 시스템 노드)", "skill": "",
         "stage": "BUILD", "category": "system", "model_tier": "flash", "order": 10, "enabled": True, "hotl_after": False, "debate": False, "llm": False},
        {"id": "Reviewer", "name_ko": "리뷰어", "role": "단위 코드·버그·해당 단위 기능 동작 검증(개발 엔지니어 관점)", "skill": "reviewer_skill",
         "stage": "CODE_REVIEW", "category": "review", "model_tier": "pro", "order": 11, "enabled": True, "hotl_after": False, "debate": False, "llm": True},
        {"id": "QA", "name_ko": "QA 엔지니어", "role": "기획서·설계서 대비 통합 구현 정합·인도 검수(수행사 인도 전)", "skill": "qa_skill",
         "stage": "QA", "category": "review", "model_tier": "pro", "order": 12, "enabled": True, "hotl_after": False, "debate": False, "llm": True},
        {"id": "Supervisor", "name_ko": "슈퍼바이저(고객사 대리인)", "role": "RFP 대비 비즈니스 수용·완료 최종 검수(고객사 관점·엄격)", "skill": "supervisor_skill",
         "stage": "SUPERVISOR", "category": "review", "model_tier": "pro", "order": 13, "enabled": True, "hotl_after": False, "debate": False, "llm": True},
        {"id": "ManualWriter", "name_ko": "매뉴얼 작성가", "role": "최종 사용자 매뉴얼 작성", "skill": "manual_skill",
         "stage": "MANUAL", "category": "review", "model_tier": "flash", "order": 14, "enabled": True, "hotl_after": False, "debate": False, "llm": True},
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
    result = {
        # 템플릿 식별자(SSOT). 프론트(WorkflowStrip 등)가 default/커스텀을 구분하는 근거이므로
        # 정규화 결과에 항상 실어 보낸다. 원본에 없으면 로더(load_registry/load_template)가 스탬프한다.
        "id": str(reg.get("id", "") or ""),
        "version": int(reg.get("version", 1)),
        "pipeline_name": str(reg.get("pipeline_name", DEFAULT_REGISTRY["pipeline_name"])),
        "description": str(reg.get("description", "")),
        "deliverable_type": str(reg.get("deliverable_type", "software_app")),
        "agents": agents,
        "edges": reg.get("edges", []),
    }
    # 시뮬레이션 프레임워크 메타데이터 보존 — agent_graph.py의 build_graph_from_registry()가
    # simulation_framework / framework_agents 를 참조해 resimulate 라우팅·프레임워크 셸 조립에 사용한다.
    if reg.get("simulation_framework"):
        result["simulation_framework"] = True
        result["framework_agents"] = reg.get("framework_agents", {})
    return result


def load_registry() -> Dict[str, Any]:
    """레지스트리 로드. 파일이 없거나 손상 시 DEFAULT로 안전 폴백.
    반환 결과의 id 는 항상 'default'(기존 단일 레지스트리 = default 템플릿)로 스탬프한다."""
    def _as_default(reg: Dict[str, Any]) -> Dict[str, Any]:
        reg["id"] = DEFAULT_TEMPLATE_ID
        return reg

    if not os.path.exists(REGISTRY_PATH):
        return _as_default(_normalize(DEFAULT_REGISTRY))
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        reg = _normalize(data)
        if not reg["agents"]:
            return _as_default(_normalize(DEFAULT_REGISTRY))
        return _as_default(reg)
    except Exception:
        # 손상된 파일이 그래프 부팅을 막지 않도록 DEFAULT로 폴백
        return _as_default(_normalize(DEFAULT_REGISTRY))


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
    return default if default is not None else ["RFP_Analyst", "Master_PMO"]


def agent_meta(agent_id: str, template_id: str = DEFAULT_TEMPLATE_ID) -> dict:
    """레지스트리에서 해당 에이전트 메타를 반환(미존재/오류 시 {}).
    template_id 로 해당 템플릿 레지스트리에서 조회(T2-b 런타임 해석). 기본은 default(하위호환)."""
    try:
        for a in load_template(template_id).get("agents", []):
            if a.get("id") == agent_id:
                return a
    except Exception:
        pass
    return {}


def agent_skill(agent_id: str, default: str = "", template_id: str = DEFAULT_TEMPLATE_ID) -> str:
    """노드의 스킬 파일명을 레지스트리에서 조회(제어판 override 반영). 미설정 시 default(현행 동작 보존).
    template_id 가 주어지면 그 템플릿의 스킬을 해석(T2-b) — 노드가 state.template_id 를 넘긴다."""
    return agent_meta(agent_id, template_id).get("skill") or default


# ──────────────────────────────────────────────────────────────────────────────
# 다중 템플릿(Copy 모델) — "default"(=기존 단일 레지스트리)는 그대로, 추가 템플릿은 templates/<id>.json
# ──────────────────────────────────────────────────────────────────────────────
def _safe_tid(template_id: str) -> str:
    if not _TID_RE.match(template_id or ""):
        raise ValueError("잘못된 template_id 형식입니다(허용: 영숫자/_/-).")
    return template_id


def _template_path(template_id: str) -> str:
    return os.path.join(TEMPLATES_DIR, f"{_safe_tid(template_id)}.json")


def load_template(template_id: str = DEFAULT_TEMPLATE_ID) -> Dict[str, Any]:
    """템플릿 레지스트리 로드.
    - default: 기존 단일 레지스트리(agents_registry.json, 없으면 DEFAULT_REGISTRY) — 하위호환.
    - 그 외: templates/<id>.json (없거나 손상/빈 결과 시 DEFAULT_REGISTRY 폴백 → 부팅 안전)."""
    if template_id == DEFAULT_TEMPLATE_ID:
        return load_registry()
    path = _template_path(template_id)
    if not os.path.exists(path):
        return _normalize(DEFAULT_REGISTRY)
    try:
        with open(path, "r", encoding="utf-8") as f:
            reg = _normalize(json.load(f))
        if not reg["agents"]:
            return _normalize(DEFAULT_REGISTRY)
        reg["id"] = template_id  # 로더가 실제 template_id 를 SSOT 로 스탬프(파일 내 id 누락/불일치 방어)
        return reg
    except Exception:
        return _normalize(DEFAULT_REGISTRY)


def list_templates() -> List[Dict[str, Any]]:
    """공존하는 워크플로우 템플릿 요약(항상 default 포함)."""
    base = load_registry()
    items = [{
        "id": DEFAULT_TEMPLATE_ID,
        "name": base.get("pipeline_name", "기본 워크플로우"),
        "description": base.get("description", ""),
        "agent_count": len(base.get("agents", [])),
        "builtin": True,
    }]
    if os.path.isdir(TEMPLATES_DIR):
        for fn in sorted(os.listdir(TEMPLATES_DIR)):
            if not fn.endswith(".json"):
                continue
            # 워크플로우 템플릿이 아닌 예약 설정 파일은 제외(예: output_formats.json = 출력 포맷 정의).
            # 이런 파일은 agents 가 없어 load_template 에서 default 로 폴백되며 목록에 노출되면 혼란을 준다.
            if fn in _RESERVED_TEMPLATE_FILES:
                continue
            tid = fn[:-5]
            try:
                reg = load_template(tid)
                items.append({
                    "id": tid,
                    "name": reg.get("pipeline_name", tid),
                    "description": reg.get("description", ""),
                    "agent_count": len(reg.get("agents", [])),
                    "builtin": False,
                })
            except Exception:
                continue
    return items


def save_template(template_id: str, reg: Dict[str, Any]) -> Dict[str, Any]:
    """템플릿 저장(정규화·검증). default 는 기존 레지스트리 경로로 위임."""
    if template_id == DEFAULT_TEMPLATE_ID:
        return save_registry(reg)
    norm = _normalize(reg)
    if not norm["agents"]:
        raise ValueError("최소 1개 이상의 에이전트가 필요합니다.")
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    with open(_template_path(template_id), "w", encoding="utf-8") as f:
        json.dump(norm, f, ensure_ascii=False, indent=2)
    return norm


def copy_template(src_id: str, new_id: str, new_name: str = "") -> Dict[str, Any]:
    """src 템플릿을 복사해 새 템플릿을 만든다(기존 템플릿은 불변 — Copy 모델 핵심)."""
    _safe_tid(new_id)
    if new_id == DEFAULT_TEMPLATE_ID:
        raise ValueError("default 는 예약된 템플릿 id 입니다.")
    if os.path.exists(_template_path(new_id)):
        raise ValueError("이미 존재하는 template_id 입니다.")
    src = dict(load_template(src_id))
    if new_name:
        src["pipeline_name"] = new_name
    return save_template(new_id, src)


def delete_template(template_id: str) -> None:
    if template_id == DEFAULT_TEMPLATE_ID:
        raise ValueError("기본(default) 템플릿은 삭제할 수 없습니다.")
    path = _template_path(template_id)
    if os.path.exists(path):
        os.remove(path)
