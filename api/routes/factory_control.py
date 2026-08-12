import asyncio
import io
import json
import os
import re
import shutil
import stat
import zipfile
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# [Phase 2/3] 식별·권한은 라우트에서 판정하지 않는다 — api/deps.py 단일 지점이 담당한다.
from api.deps import (
    Principal,
    assert_can_read_dept,
    assert_enterprise,
    assert_identified,
    assert_project_readable,
    assert_project_writable,
    current_principal,
    enterprise_context,
    visibility_block_reason,
)
from core.route_authority import guard as _route_authority_guard
# [D-017 P0] 서버 재검사 — 화면 숨김이 아니라 여기가 유일한 보안 경계다.
from api.deps import require_caps as _require_caps
from core.admin_capability import (AGENT_READ, AGENT_UPDATE, SKILL_PROPOSE,
                                   SYSTEM_DEFAULT_EDIT, WORKFLOW_CREATE, WORKFLOW_READ,
                                   WORKFLOW_RETIRE, WORKFLOW_UPDATE)


def _audit_registry(event: str, p: "Principal", reason: str, detail: str = "") -> None:
    """[D-017 §9 P0-6] 전역 구성 변경을 남긴다.

    ★ 이 경로들은 **한 사람의 저장이 전 사용자에게 반영된다.** 기록이 없으면 "어제까지 되던
      파이프라인이 왜 바뀌었나" 에 아무도 답할 수 없다.
    ⚠️ 기록 실패가 요청을 죽이지 않는다 — 다만 `audit.record` 는 내부에서 실패를 센다."""
    try:
        from core.enterprise_context import audit
        audit.record(getattr(audit, event, event), resource_type="agent_registry",
                     resource_id=event, actor=p.user_id or "", outcome="allowed",
                     reason=reason, detail=detail)
    except Exception:
        pass


#: [D-017 §2.3] 스킬 파일명에 쓰는 에이전트 ID. **경로 구성에 개입할 수 없는 문자만** 허용한다.
#: ⚠️ 예전에는 검증이 없어 `../` 나 절대경로 조각이 파일명으로 들어갈 수 있었다.
_SAFE_AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
from core.enterprise_context import EnterpriseContext
from typing import Optional

from core.async_orchestrator import orchestrator
# 배포된 최종 결과물 보관소의 경로는 **단일 지점**에서 온다(`core/library_paths.py`).
#   여기서 `LIBRARY_DIR = "library"` 로 다시 선언하면 게시는 이 경로에 쓰고 사용여부 제어는
#   다른 경로를 보는 상태가 되어, 실제 프로그램이 "존재하지 않는 프로그램"으로 거부된다.
from core import library_paths
from core import project_visibility as _pv
from core.paths import workspace_path

# ★★ [2026-08-07] 권한 배정표를 **라우터에 붙인다.** 라우트마다 `require_caps` 를 적지
#   않는 이유: 37개에 적으면 37번 빠뜨릴 기회가 생기고, 새 라우트가 생겨도 아무도
#   알려 주지 않는다. 표는 `core/route_authority.ROUTE_CAPS` 하나뿐이며,
#   `tests/test_route_authority_table.py` 가 표와 라우터를 **양방향으로** 대조한다.
router = APIRouter(prefix="/api/v1/factory", dependencies=[Depends(_route_authority_guard)])

#: 사용자에게 보일 자료 이름. 조사(을/를)는 `deps.eul` 이 맞춘다.
WHAT = "공장 실행 기록"


class SprintStartRequest(BaseModel):
    task_id: str
    project_state_payload: dict

class HOTLResumeRequest(BaseModel):
    task_id: str
    feedback: Optional[str] = ""

class RevisionRequest(BaseModel):
    feedback: str

class SupervisorChatRequest(BaseModel):
    task_id: Optional[str] = ""  # 자비스 모드: 태스크 없이도(유휴 상태 포함) 시스템 전체에 대해 대화 가능
    message: str

class ProjectCreateRequest(BaseModel):
    project_id: str
    template_id: str = "default"  # 이 프로젝트가 실행될 워크플로우 템플릿(범용 플랫폼 T2-b)
    output_format_id: str = "default"  # 이 프로젝트에 적용될 출력 포맷
    view_type: str = "react_app"
    knowledge_pack_ids: list = []  # 이 프로젝트에 연결할 도메인 지식팩(그라운딩 RAG)
    master_domains: list = []  # [M1] 이 프로젝트에 적용할 기준정보 도메인 태그
    mcp_live_grounding: bool = False  # [M3] 외부 실측값 병기 토글(기본 off)


class ProjectKnowledgeRequest(BaseModel):
    knowledge_pack_ids: list = []
    master_domains: Optional[list] = None  # [M1] None 이면 기존 값 유지

class ProjectCopyRequest(BaseModel):
    new_project_id: str

class HealRequest(BaseModel):
    error_log: str

class SprintPauseRequest(BaseModel):
    task_id: str

# Windows '.git' 읽기 전용 폴더 강제 권한 해제 콜백 (Python 3.12+ onexc 규격)
def _on_rmtree_error(func, path, exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)

# 경로 파라미터(project_id/release_id)는 파일시스템 경로로 직접 사용되므로 단일 세그먼트만 허용한다.
# '/', '\\', '..', 절대경로, 빈값을 차단해 디렉토리 이탈(path traversal)을 원천 봉쇄한다.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

def _safe_id(value: str, label: str = "id") -> str:
    if not _ID_RE.match(value or ""):
        raise HTTPException(status_code=400, detail=f"잘못된 {label} 형식입니다.")
    return value

# 새로고침/SSE 재연결 후 클라이언트 state가 비거나 stale 해지면, 다음 태스크 페이로드에서
# 누적 산출물(file_index/요약/git)이 유실되어 기존 맥락·기능이 사라진다(감사: file_index_gap).
# → 태스크 시작 시 디스크 진실원본(latest_state.json)에서 '비어 있는 누적 필드만' 채운다
#   (클라이언트가 채운 값/이번 태스크 의도는 절대 덮어쓰지 않는 보수적 병합).
_ACCUMULATED_FIELDS = [
    "file_index", "rfp_summary", "prd_summary", "architecture_summary", "tech_spec_summary",
    "frontend_code_summary", "backend_code_summary", "code_review_report_summary",
    "qa_report_summary", "user_manual_summary", "git_info",
    "architecture_decisions", "technical_debt", "initial_idea", "project_name",
    "domain_agents", "is_mega_project", "parent_project_id", "sub_projects_map", "shared_ledger",
    # [Phase 3] 소유권은 스프린트 사이에 유실되면 안 된다 — 누적 보존 대상에 편입.
    # ⚠️ 여기 있는 것은 **유실 방지**이지 최초 주입이 아니다 — 이미 채워진 값을 전제한다.
    #   최초 주입은 `start_sprint` 가 권위 원본(`project_meta.json`)에서 한다(D-019).
    "owner_dept_id", "owner_user_id", "visibility", "owner_scope_node_id",
    # [M0-d] Blueprint 링크도 유실되면 추적성이 끊긴다(스프린트마다 다시 채워줄 곳이 없다).
    "blueprint_id",
    # [ECM E1/E2 · R-001] 실행 문맥이 유실되면 기준정보 범위 필터가 풀려 다른 법인 기준정보가
    #   프롬프트에 섞인다. 소유권과 같은 이유로 누적 보존 대상이다.
    "tenant_id", "enterprise_scope_id", "entity_mode",
]


def _is_empty(v) -> bool:
    return v in (None, "", [], {})


# 프로젝트↔워크플로우 템플릿 바인딩(T2-b) — 프로젝트 폴더에 영속해, 새로고침/HOTL 재개로
# 프론트 state 가 stale 해져도 모든 태스크가 같은 템플릿으로 실행되도록 보장한다.
def _read_project_meta(workspace_root: str) -> tuple[str, str, str]:
    try:
        with open(_project_meta_path(workspace_root), "r", encoding="utf-8") as f:
            data = json.load(f) or {}
            tid = data.get("template_id", "default")
            fid = data.get("output_format_id", "default")
            vtype = data.get("view_type", "react_app")
        return tid or "default", fid or "default", vtype or "react_app"
    except Exception:
        return "default", "default", "react_app"

def _read_project_template(workspace_root: str) -> str:
    tid, _, _ = _read_project_meta(workspace_root)
    return tid


def _ownership_visible(p, own: dict) -> bool:
    """이 소유권 정보를 가진 자원이 요청자에게 보이는가.

    ★★ [G1-C] **규칙 본체는 `core/project_visibility.py` 에 있다.** 여기 두면 SSE 브로드캐스터가
      같은 질문에 따로 답하게 되고, 그러면 「목록에는 안 보이는 프로젝트의 진행 이벤트가
      실시간으로 흘러드는」 상태가 만들어진다. 그 어긋남은 조용하다.
      `api/deps._enforced` 가 같은 이유로 이미 한 곳에 모여 있다."""
    try:
        return _pv.ownership_visible(p.scope, p.user_id, own)
    except Exception:
        return True                       # 판정 불가는 하위호환 쪽으로 — 원본 계약 그대로


def _iter_visible_projects(p) -> list:
    """요청자에게 보이는 프로젝트 id 목록 (설계서 Phase 4 공용 헬퍼).

    ⚠️ `GET /projects` 와 `supervisor_chat` 이 각자 디렉터리를 훑고 있었는데, 후자는
      **권한을 전혀 보지 않고 전체 프로젝트 이름을 LLM 브리핑에 동봉**했다.
      즉 다른 부서의 프로젝트 이름이 그대로 새어나갔다. 목록 생성을 한 곳으로 모은다."""
    root = workspace_path()
    out = []
    try:
        names = os.listdir(root)
    except Exception:
        return out
    for item in names:
        item_path = os.path.join(root, item)
        if not os.path.isdir(item_path):
            continue
        if _ownership_visible(p, _read_project_ownership(item_path)):
            out.append(item)
    return out


#: ★★ [G1-C] 본체는 `core/project_visibility.py` 로 옮겼다. 이름은 남긴다 —
#:   테스트가 `monkeypatch.setattr(fc, "_read_project_ownership", ...)` 로 이 이름을 갈아끼우고,
#:   이 모듈의 호출부는 모듈 전역을 통해 부르므로 그 대체가 그대로 먹는다.
#:   ⚠️ 그 monkeypatch 는 **브로드캐스터에는 닿지 않는다**(다른 모듈에서 직접 부른다).
#:     SSE 격리를 시험하려면 `core.project_visibility` 쪽을 갈아끼워야 한다.
_read_project_ownership = _pv.read_project_ownership
_project_meta_path = _pv.project_meta_path


def _resolve_scope_node(dept_id: str) -> str:
    """[D-019] 부서 → **지금 시점의** ECM 조직 노드. 못 풀면 빈 값(«미상»)이다.

    ⚠️ 못 푼 것을 상위 노드로 **추측해 채우지 않는다** — 추측이 한 번 맞으면 그 뒤로 아무도
      검증하지 않고, 틀리면 다른 사업부의 비용으로 집계된다(`org_directory._scope_nodes_of`
      의 판단과 같다). 빈 값은 화면에서 «(미상)» 으로 드러난다.
    ⚠️ 이 호출은 **기록 시점에 한 번**만 한다. 나중에 다시 풀면 `update_department` 가 개정한
      새 `scope_node_id` 가 나와 과거 비용이 소급해 움직인다(D-019 스냅샷 규칙).
    ⚠️ 조회 실패가 가동을 막지 않는다 — 조직 축은 계측이고, 계측 장애로 스프린트를 멈추지 않는다."""
    dept_id = str(dept_id or "").strip()
    if not dept_id:
        return ""
    try:
        from core.org_directory import org_directory
        d = org_directory.get_department(dept_id)
        return str((d or {}).get("scope_node_id", "") or "").strip()
    except Exception as e:
        print(f"⚠️ [factory] 부서→조직노드 해석 실패(미상으로 기록): {dept_id}: {e}")
        return ""


def _write_project_meta(workspace_root: str, template_id: str, output_format_id: str = "default", view_type: str = "react_app", knowledge_pack_ids: list = None, master_domains: list = None, mcp_live_grounding: bool = None,
                        owner_dept_id: str = None, owner_user_id: str = None,
                        visibility: str = None, nature: str = None,
                        forked_from: dict = None,
                        tenant_id: str = None, enterprise_scope_id: str = None,
                        entity_mode: str = None, blueprint_id: str = None) -> None:
    """⚠️ 소유권 5필드도 **None 이면 보존**한다(Phase 3).
    이 함수는 템플릿만 바꾸려는 호출부가 많은데, 거기서 소유권이 초기화되면
    프로젝트가 조용히 무소속이 되어 권한 필터에서 사라진다."""
    try:
        # [M1/M3] master_domains·mcp_live_grounding 미지정(None)이면 기존 값을 보존한다 —
        # 이 필드를 안 넘기는 기존 호출부(mega/sub 생성 등)가 기존 설정을 실수로 날리지 않도록.
        # ★ [2026-07-27 P0-1] `knowledge_pack_ids` 도 보존 대상에 편입한다.
        #   기존엔 master_domains/mcp_live_grounding 만 None 이면 보존하고
        #   knowledge_pack_ids 는 보존 로직이 없어 **호출부가 안 넘기면 `[]` 로 초기화**됐다.
        #   이 함수를 부르는 다른 경로(소유권 변경 등)가 지식팩 연결을 조용히 날린다.
        # [ECM-lite] 문맥 4필드도 같은 보존 계약을 따른다 — 템플릿만 바꾸는 호출부가 문맥을
        #   날리면 프로젝트가 조용히 문맥 미지정이 되어 격리가 풀린다(소유권과 같은 위험).
        _own_missing = any(v is None for v in
                           (owner_dept_id, owner_user_id, visibility, nature, forked_from,
                            tenant_id, enterprise_scope_id, entity_mode, blueprint_id))
        _prev = {}
        if (master_domains is None or mcp_live_grounding is None
                or knowledge_pack_ids is None or _own_missing):
            try:
                with open(_project_meta_path(workspace_root), "r", encoding="utf-8") as f:
                    _prev = json.load(f) or {}
            except Exception:
                _prev = {}
        if owner_dept_id is None:
            owner_dept_id = _prev.get("owner_dept_id", "")
        if owner_user_id is None:
            owner_user_id = _prev.get("owner_user_id", "")
        if visibility is None:
            visibility = _prev.get("visibility", "dept")
        if nature is None:
            nature = _prev.get("nature", "")
        if forked_from is None:
            forked_from = _prev.get("forked_from", {})
        if tenant_id is None:
            tenant_id = _prev.get("tenant_id", "") or "tenant_default"
        if enterprise_scope_id is None:
            enterprise_scope_id = _prev.get("enterprise_scope_id", "")
        if entity_mode is None:
            entity_mode = _prev.get("entity_mode", "") or "REAL"
        if blueprint_id is None:
            blueprint_id = _prev.get("blueprint_id", "")
        if master_domains is None:
            master_domains = _prev.get("master_domains", [])
        if mcp_live_grounding is None:
            mcp_live_grounding = _prev.get("mcp_live_grounding", False)
        if knowledge_pack_ids is None:
            knowledge_pack_ids = _prev.get("knowledge_pack_ids", [])
        with open(_project_meta_path(workspace_root), "w", encoding="utf-8") as f:
            json.dump({
                "template_id": template_id or "default",
                "output_format_id": output_format_id or "default",
                "view_type": view_type or "react_app",
                "knowledge_pack_ids": list(knowledge_pack_ids or []),
                "master_domains": list(master_domains or []),
                "mcp_live_grounding": bool(mcp_live_grounding),
                # [Phase 3] 소유권 — 이 파일이 진실원본이고 ownership 테이블은 검색용 미러다.
                "owner_dept_id": owner_dept_id or "",
                "owner_user_id": owner_user_id or "",
                "visibility": visibility or "dept",
                "nature": nature or "",
                "forked_from": forked_from or {},
                # [ECM-lite] 실행 문맥 — 설계서 §10.2. `blueprint_id` 는 이 프로젝트가 어느
                #   Solution Blueprint 에서 나왔는지의 추적 링크(§18-7 추적성).
                "tenant_id": tenant_id or "tenant_default",
                "enterprise_scope_id": enterprise_scope_id or "",
                "entity_mode": entity_mode or "REAL",
                "blueprint_id": blueprint_id or "",
            }, f, ensure_ascii=False, indent=2)
        _sync_project_ownership(workspace_root, owner_dept_id, owner_user_id, visibility, nature)
    except Exception as e:
        print(f"⚠️ project_meta 저장 실패: {e}")


def _sync_project_ownership(workspace_root: str, dept_id: str = "", user_id: str = "",
                            visibility: str = "dept", nature: str = "") -> None:
    """파일(진실원본) 저장 직후 `ownership` 미러를 갱신한다.

    ⚠️ 미러가 필요한 이유: 프로젝트 목록이 전량 디렉터리 스캔 + 파일 오픈이라 거기에
      부서 필터·정렬·페이지네이션을 얹으면 감당이 안 된다. 어긋나면 /org/reconcile 로 재구축한다.
      미러 실패가 프로젝트 저장 자체를 막으면 안 되므로 조용히 넘어간다."""
    try:
        from core.org_directory import org_directory
        pid = os.path.basename(os.path.normpath(workspace_root))
        if pid:
            org_directory.set_ownership("project", pid, dept_id=dept_id or "",
                                        owner_user_id=user_id or "",
                                        visibility=visibility or "dept", nature=nature or "")
    except Exception as e:
        print(f"⚠️ ownership 미러 갱신 실패(무시): {e}")


def _read_project_packs(workspace_root: str) -> list:
    """프로젝트에 연결된 지식팩 id 목록(project_meta.json). 없으면 빈 목록."""
    try:
        with open(_project_meta_path(workspace_root), "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        packs = data.get("knowledge_pack_ids", [])
        return [p for p in packs if isinstance(p, str)]
    except Exception:
        return []


def _read_project_master_domains(workspace_root: str) -> list:
    """[M1] 프로젝트에 연결된 기준정보 도메인 태그(project_meta.json). 없으면 빈 목록."""
    try:
        with open(_project_meta_path(workspace_root), "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        doms = data.get("master_domains", [])
        return [d for d in doms if isinstance(d, str)]
    except Exception:
        return []


def _read_project_mcp_live(workspace_root: str) -> bool:
    """[M3] 프로젝트의 외부 실측값 병기 토글(project_meta.json). 기본 False."""
    try:
        with open(_project_meta_path(workspace_root), "r", encoding="utf-8") as f:
            return bool((json.load(f) or {}).get("mcp_live_grounding", False))
    except Exception:
        return False


def _restore_accumulated_from_disk(payload: dict, workspace_root: str) -> dict:
    state_path = os.path.join(workspace_root, "latest_state.json")
    if not os.path.exists(state_path):
        return payload
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            disk = json.load(f)
    except Exception:
        return payload  # 읽기 실패 시 원본 유지
    if not isinstance(disk, dict):
        return payload
    for k in _ACCUMULATED_FIELDS:
        if _is_empty(payload.get(k)) and not _is_empty(disk.get(k)):
            payload[k] = disk[k]
    return payload

class OwnershipUpdate(BaseModel):
    owner_dept_id: Optional[str] = None
    owner_user_id: Optional[str] = None
    visibility: Optional[str] = None      # dept | company | personal
    nature: Optional[str] = None          # 사용자 선언: enterprise | local | personal


@router.put("/{project_id}/ownership")
async def set_project_ownership(project_id: str, req: OwnershipUpdate,
                                p: Principal = Depends(current_principal)):
    """프로젝트의 소유 부서·가시성을 지정한다 (설계서 Phase 3).

    진실원본은 `project_meta.json` 이며, 저장 직후 `ownership` 미러가 갱신된다."""
    _safe_id(project_id, "project_id")
    ws = workspace_path(project_id)
    if not os.path.isdir(ws):
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    assert_project_writable(p, project_id)
    if req.visibility is not None and req.visibility not in ("dept", "company", "personal"):
        raise HTTPException(status_code=400, detail="visibility 는 dept|company|personal 이어야 합니다.")

    tid, fid, vtype = _read_project_meta(ws)
    _write_project_meta(ws, tid, fid, vtype,
                        owner_dept_id=req.owner_dept_id, owner_user_id=req.owner_user_id,
                        visibility=req.visibility, nature=req.nature)
    return {"status": "success", "data": _read_project_ownership(ws)}


@router.get("/projects")
async def get_projects(include_deleted: bool = False,
                       p: Principal = Depends(current_principal)):
    # ★★ [이관 7/10 · 병합 2026-08-05 복원] 소유권 필터(`_ownership_visible`)는 있었지만
    #   **익명 자체가 통과**했다. 미태깅 프로젝트는 하위호환으로 «누구에게나 보이는» 상태이므로,
    #   익명에게 목록을 주면 그 하위호환이 그대로 유출 경로가 된다. 관문 A: 미지정 = 비노출.
    # ⚠️ 병합 검증에서 이것을 놓칠 뻔했다 — 라우트에 `current_principal` 이 **있으므로**
    #   자동 점검은 «통제됨» 으로 셌다. 의존성이 있다는 것과 판정이 있다는 것은 다르다.
    reason = visibility_block_reason(p)
    if reason:
        return {"status": "success", "data": [], "blocked_reason": reason}
    projects_dir = workspace_path()
    os.makedirs(projects_dir, exist_ok=True)

    # [2026-08-07 사용자 결정] 표시 삭제된 프로젝트는 목록에서 뺀다 — 파일은 남아 있다.
    # ⚠️ `include_deleted` 는 **관리자만** 쓸 수 있다. 일반 사용자에게 열어 주면 「지웠는데
    #   그대로 보인다」가 되고, 그때 사용자는 실제 삭제를 요청하게 된다 — 남겨 두려던 이유가
    #   사라진다. 관리자에게 필요한 이유는 되돌리기(`/restore`) 대상을 찾아야 하기 때문이다.
    from core import project_deletion as pdel
    show_deleted = bool(include_deleted) and pdel.is_admin(p.scope)

    project_list = []
    for item in os.listdir(projects_dir):
        item_path = os.path.join(projects_dir, item)
        if os.path.isdir(item_path):
            # [Phase 3/4] 소유권 필터. 이 루프는 이미 메타 파일을 열고 있으므로 추가 I/O 는 실질 0.
            _own = _read_project_ownership(item_path)
            if not _ownership_visible(p, _own):
                continue
            _deleted = pdel.is_deleted(item_path)
            if _deleted and not show_deleted:
                continue
            wbs_path = os.path.join(item_path, "00_wbs_master_plan.json")
            project_name = item
            initial_idea = ""
            total_tasks = 0
            completed_tasks = 0
            template_id, _, _ = _read_project_meta(item_path)
            if os.path.exists(wbs_path):
                try:
                    with open(wbs_path, "r", encoding="utf-8") as f:
                        wbs_data = json.load(f)
                        project_name = wbs_data.get("project_name", item)
                        tasks = wbs_data.get("tasks", [])
                        core_tasks = [t for t in tasks if not str(t.get("task_id", "")).startswith("TASK_REV_")]
                        total_tasks = wbs_data.get("total_tasks", len(core_tasks)) if wbs_data.get("total_tasks") else len(core_tasks)
                        completed_tasks = sum(1 for t in core_tasks if t.get("status") == "DONE")
                except:
                    pass
            state_path = os.path.join(item_path, "latest_state.json")
            is_mega_project = False
            parent_project_id = ""
            if os.path.exists(state_path):
                try:
                    with open(state_path, "r", encoding="utf-8") as f:
                        state_data = json.load(f)
                        initial_idea = state_data.get("initial_idea", "")
                        is_mega_project = state_data.get("is_mega_project", False)
                        parent_project_id = state_data.get("parent_project_id", "")
                except:
                    pass
            project_list.append({
                "id": item, 
                "name": project_name, 
                "initial_idea": initial_idea,
                "is_mega_project": is_mega_project,
                "parent_project_id": parent_project_id,
                "template_id": template_id,
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                # ⚠️ 관리자가 `include_deleted=true` 로 볼 때 **어느 것이 삭제된 것인지** 화면이
                #   구분할 수 있어야 한다. 표시가 없으면 되돌릴 대상을 고를 수 없다.
                "deleted": _deleted,
            })

    return {"status": "success", "data": project_list}

def provision_project(project_id: str, template_id: str = "default",
                      output_format_id: str = "default", view_type: str = "react_app",
                      knowledge_pack_ids: list = None, master_domains: list = None,
                      mcp_live_grounding: bool = None,
                      owner_dept_id: str = "", owner_user_id: str = "",
                      tenant_id: str = None, enterprise_scope_id: str = None,
                      entity_mode: str = None, blueprint_id: str = None) -> str:
    """프로젝트 디렉터리와 `project_meta.json` 을 만든다. **`POST /projects` 와 상담사
    `bootstrap-project` 가 공유하는 단일 경로**다.

    ⚠️ 왜 헬퍼로 뽑는가: 상담사가 프로젝트를 만들 때 이 로직을 복사하면 템플릿 검증·소유권
      기록·ECM 문맥 중 하나가 한쪽에만 반영되어 조용히 어긋난다. 이 프로젝트에서 반복된
      결함 유형이라(생성 경로가 필드를 안 채워 필터가 무력화된 일이 세 번) 경로를 하나로 둔다.

    반환: 확정된 template_id. 검증 실패는 `ValueError`(형식) / `KeyError`(미존재) /
      `FileExistsError`(중복)로 올리고 라우트가 4xx 로 바꾼다 — 저장소 계층이 HTTP 를 모르게 한다."""
    _safe_id(project_id, "project_id")   # 디스크에 안전한 id만 → 이후 모든 라우트가 안전한 id를 다룬다
    # 템플릿 id 검증(형식 + 존재). 미존재/잘못된 형식이면 거부 — 잘못된 바인딩이 조용히 default 로
    # 폴백해 사용자가 고른 워크플로우와 다르게 실행되는 혼란을 막는다.
    from core.agent_registry import _safe_tid, list_templates
    tid = template_id or "default"
    _safe_tid(tid)                                   # 형식 오류 → ValueError
    if tid not in {t["id"] for t in list_templates()}:
        raise KeyError(tid)                          # 미존재 → KeyError
    project_path = workspace_path(project_id)
    if os.path.exists(project_path):
        raise FileExistsError(project_id)
    os.makedirs(project_path, exist_ok=True)
    _write_project_meta(project_path, tid, output_format_id, view_type, knowledge_pack_ids,
                        master_domains, mcp_live_grounding,
                        owner_dept_id=owner_dept_id, owner_user_id=owner_user_id,
                        tenant_id=tenant_id, enterprise_scope_id=enterprise_scope_id,
                        entity_mode=entity_mode, blueprint_id=blueprint_id)
    return tid


@router.post("/projects")
async def create_project(req: ProjectCreateRequest, p: Principal = Depends(current_principal),
                         ctx: "EnterpriseContext" = Depends(enterprise_context)):
    # ★ [2026-07-28 Phase 5] 생성 시점에 **만든 사람의 소속 부서를 소유 부서로 찍는다.**
    #   ⚠️ 왜 여기가 중요한가: 프롬프트 주입 필터(`get_relevant_context`)는 프로젝트에
    #     `owner_dept_id` 가 있을 때만 부서 스코프를 건다. 소유권이 비어 있으면
    #     **필터가 아예 걸리지 않아 전사 산출물이 그대로 주입된다**(fail-open).
    #     즉 소유권을 안 찍으면 "부서 없는 프로젝트를 만들어 남의 부서 산출물을 긁는" 경로가
    #     열린다. 유출은 검색 시점에 막는 것보다 **생성 시점에 소유권을 확정**하는 편이 확실하다.
    #   무소속 사용자/조직 미도입이면 `primary_dept_id` 가 빈 문자열이라 종전과 동일하게
    #     미태깅으로 남는다(하위호환 — 기존 프로젝트를 깨지 않는다).
    # ★★★ [이관 7/10 · 병합 2026-08-05 복원] 그래서 **익명은 입구에서 막는다.** 위 주석이
    #   경고하는 fail-open 경로를 여는 가장 쉬운 방법이 「익명으로 만들기」다 — 소유권이 빌
    #   수밖에 없으므로 주입 필터가 아예 걸리지 않는다.
    _reason = visibility_block_reason(p)
    if _reason:
        raise HTTPException(status_code=403, detail=_reason)
    _own_dept = getattr(p.scope, "primary_dept_id", "") or ""
    try:
        tid = provision_project(
            req.project_id, req.template_id or "default", req.output_format_id, req.view_type,
            req.knowledge_pack_ids, req.master_domains, req.mcp_live_grounding,
            owner_dept_id=_own_dept, owner_user_id=p.user_id or "",
            tenant_id=ctx.tenant_id, enterprise_scope_id=ctx.enterprise_scope_id or _own_dept,
            entity_mode=ctx.entity_mode)
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 template_id 형식입니다.")
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 템플릿입니다: {e.args[0]}")
    except FileExistsError:
        raise HTTPException(status_code=409, detail="이미 존재하는 프로젝트 ID입니다.")
    return {"status": "success", "project_id": req.project_id, "template_id": tid, "view_type": req.view_type, "knowledge_pack_ids": req.knowledge_pack_ids, "master_domains": req.master_domains, "mcp_live_grounding": req.mcp_live_grounding,
            "owner_dept_id": _own_dept, "owner_user_id": p.user_id or "",
            "tenant_id": ctx.tenant_id, "enterprise_scope_id": ctx.enterprise_scope_id or _own_dept,
            "entity_mode": ctx.entity_mode}


@router.put("/projects/{project_id}/knowledge")
async def update_project_knowledge(project_id: str, req: ProjectKnowledgeRequest,
                                   p: Principal = Depends(current_principal)):
    """기존 프로젝트의 지식팩 연결을 변경한다(다음 스프린트부터 반영)."""
    _safe_id(project_id, "project_id")
    workspace_root = f"./projects/{project_id}"
    if not os.path.isdir(workspace_root):
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    assert_project_writable(p, project_id)
    from core.knowledge_base import knowledge_base
    _packs = {pk.get("pack_id"): pk for pk in knowledge_base.list_packs()}
    invalid = [x for x in req.knowledge_pack_ids if x not in _packs]
    if invalid:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 지식팩: {invalid}")
    # ★ [2026-07-28 Phase 5] 지식팩 유출은 **연결 시점**에 막는다.
    #   ⚠️ 왜 검색 시점이 아닌가: 팩은 프로젝트에 연결되면 `ContextEngine` 이 그 팩만
    #     골라 검색하므로(`_read_project_packs` → `search_packs`) 검색 경로 자체는 이미 안전하다.
    #     진짜 구멍은 **읽을 권한 없는 팩을 연결해버리는 것**이고, 그러면 그 뒤 모든 프롬프트가
    #     합법적으로 그 팩을 참조한다. 그래서 관문은 여기 한 곳이다.
    #   소유 부서가 미기록(`""`)인 팩은 전사 공유로 보고 통과시킨다 — Phase 3 의
    #     "소유권 미기록 자원은 막지 않는다"와 같은 규약(하위호환).
    for _pid in req.knowledge_pack_ids:
        _pack_dept = str((_packs.get(_pid) or {}).get("owner_dept_id", "") or "")
        if _pack_dept:
            assert_can_read_dept(p, _pack_dept)
    tid, fid, vtype = _read_project_meta(workspace_root)
    _write_project_meta(workspace_root, tid, fid, vtype, req.knowledge_pack_ids, req.master_domains)
    return {"status": "success", "knowledge_pack_ids": req.knowledge_pack_ids,
            "master_domains": _read_project_master_domains(workspace_root)}

class MegaProjectCreateRequest(BaseModel):
    mega_project_id: str
    template_id: str = "manufacturing-production" # Default master template
    
@router.post("/projects/mega")
async def create_mega_project(req: MegaProjectCreateRequest, p: Principal = Depends(current_principal)):
    """메가 프로젝트 생성 (마스터 + 8개 서브 프로젝트 일괄 프로비저닝)"""
    # ★★★ [이관 7/10 · 병합 2026-08-05 복원] 단건 생성과 **같은 판정**을 여기에도 둔다.
    #   이 경로는 한 번에 9개 프로젝트를 만든다 — 단건만 막으면 우회로가 더 크다.
    _reason = visibility_block_reason(p)
    if _reason:
        raise HTTPException(status_code=403, detail=_reason)
    _safe_id(req.mega_project_id, "mega_project_id")

    # 템플릿 존재 검증 — 미존재 템플릿으로 서브 프로젝트가 default 폴백되는 것을 방지
    from core.agent_registry import _safe_tid, list_templates
    tid = req.template_id or "manufacturing-production"
    try:
        _safe_tid(tid)
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 template_id 형식입니다.")
    if tid not in {t["id"] for t in list_templates()}:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 템플릿입니다: {tid}")
    
    mega_path = workspace_path(req.mega_project_id)
    if os.path.exists(mega_path):
        raise HTTPException(status_code=409, detail="이미 존재하는 메가 프로젝트 ID입니다.")
        
    # 1. 마스터 프로젝트 생성
    os.makedirs(mega_path, exist_ok=True)
    # ★ [2026-07-28 Phase 5] 메가 마스터는 전사 종합이므로 `hq` + `company`(전사 공개).
    #   `scripts/migrate_org_ownership.py:49` 의 추론 규약과 **같은 값**을 쓴다 — 생성 시점에
    #   찍어두면 그 마이그레이션이 신규 메가에 대해 할 일이 없어진다(멱등 유지).
    _write_project_meta(mega_path, tid, "default", "react_app",
                        owner_dept_id="hq", owner_user_id=p.user_id or "", visibility="company")
    
    # ★ [2026-07-27 Phase 1] 하드코딩 맵 3개(domain_agents_map / domain_templates_map /
    #   domain_ko_map)를 제거하고 **부서 기준정보**를 조회한다.
    #   ⚠️ 왜: 부서 하나를 추가·개명·이동·폐지하려면 코드를 고치고 배포해야 했고, 세 맵이
    #     서로 어긋나도 아무도 알아채지 못했다(한 곳에만 추가하면 조용히 누락).
    #   부서가 아직 시드되지 않았다면(조직 미도입) 기존과 동일하게 동작하도록
    #   `core/org_seed._LEGACY_DEPARTMENTS` 를 기본값으로 쓴다 — 하위호환 계약.
    from core.org_directory import org_directory
    from core.org_seed import _LEGACY_DEPARTMENTS, resolve_department_config

    _registered = [d for d in org_directory.list_departments()
                   if (d.get("domain_agents") or d.get("default_template_id"))]
    if _registered:
        _domains = [d["dept_id"] for d in _registered]
    else:
        _domains = [d["dept_id"] for d in _LEGACY_DEPARTMENTS]

    sub_projects_map = {}

    # ★★ [D-017 §9 P0-5 배선] **차단된 부서가 있으면 만들기 전에 멈춘다.**
    #   ⚠️ 이 선검사가 없으면 P0-5 의 차단이 여기서 무력화된다: `resolve_department_config` 가
    #     승인되지 않은 구성을 막으려고 `agents` 를 비워 돌려주는데, 아래 루프가 그 빈 목록을
    #     «미등록 부서» 로 읽고 **레거시 기본값으로 다시 폴백**하기 때문이다.
    #     막아 놓고 호출부에서 되돌리면 통제가 아니라 장식이다.
    #   ★ 부서 하나만 조용히 건너뛰지 않는다 — 메가 프로젝트는 부서들이 함께 도는 것이고,
    #     한 부서가 빠진 채 완주하면 그 산출물이 «전사 검토를 마쳤다» 는 얼굴을 하게 된다.
    _blocked = []
    for domain in _domains:
        _pre = resolve_department_config(domain)
        if _pre.get("blocked_reason"):
            _blocked.append((domain, _pre["blocked_reason"]))
    if _blocked:
        raise HTTPException(
            status_code=400,
            detail=("승인된 에이전트 구성이 없는 부서가 있어 메가 프로젝트를 만들지 않았습니다 "
                    f"({len(_blocked)}개).\n"
                    + "\n".join(f"· {d}: {why}" for d, why in _blocked)))

    # 2. 서브 프로젝트들 생성 — 도메인별 템플릿 및 에이전트 필터 주입
    for domain in _domains:
        _cfg = resolve_department_config(domain)
        if not _cfg.get("agents") and not _cfg.get("template_id"):
            # 미등록 부서 → 이관 원천에서 기본값 확보(조직 미도입 상태의 하위호환)
            #   ⚠️ 여기 도달했다는 것은 위 선검사를 통과했다는 뜻이다 — 즉 «차단» 이 아니라
            #     «ECM 미배선» 이다. 그 둘을 같은 분기에서 다루면 다시 섞인다.
            _legacy = next((d for d in _LEGACY_DEPARTMENTS if d["dept_id"] == domain), {})
            _cfg = {"name_ko": _legacy.get("name_ko", domain), "agents": _legacy.get("agents", []),
                    "template_id": _legacy.get("template", "")}
        domain_agents = _cfg.get("agents") or []

        sub_id = f"{req.mega_project_id}_{domain}"
        sub_path = workspace_path(sub_id)
        os.makedirs(sub_path, exist_ok=True)

        sub_tid = _cfg.get("template_id") or tid
        # 서브 프로젝트는 도메인 특화 템플릿 사용 (없으면 마스터 템플릿)
        # ★ [2026-07-28 Phase 5] `domain` 이 곧 `dept_id` 다 — 서브 프로젝트의 소유 부서로 찍는다.
        #   가시성은 기본값 `dept`: 부서 산출물은 부서 안에서만 프롬프트에 주입된다.
        _write_project_meta(sub_path, sub_tid, "default", "react_app",
                            owner_dept_id=domain, owner_user_id=p.user_id or "")

        domain_name_ko = _cfg.get("name_ko") or domain.upper()
        # 서브 프로젝트 상태 초기화
        sub_state = {
            "is_mega_project": False,
            "parent_project_id": req.mega_project_id,
            "project_name": f"[{domain_name_ko}] {req.mega_project_id}",
            "template_id": sub_tid,
            "domain_agents": domain_agents
        }
        with open(os.path.join(sub_path, "latest_state.json"), "w", encoding="utf-8") as f:
            json.dump(sub_state, f, ensure_ascii=False, indent=2)
            
        sub_projects_map[domain] = sub_id
        
    # 3. 마스터 프로젝트 상태 초기화
    master_state = {
        "is_mega_project": True,
        "parent_project_id": "",
        "sub_projects_map": sub_projects_map,
        "project_name": f"🌟 메가 프로젝트: {req.mega_project_id}",
        "template_id": tid,
        "shared_ledger": {}
    }
    with open(os.path.join(mega_path, "latest_state.json"), "w", encoding="utf-8") as f:
        json.dump(master_state, f, ensure_ascii=False, indent=2)

    return {"status": "success", "mega_project_id": req.mega_project_id, "sub_projects": sub_projects_map}



class MegaPlanRequest(BaseModel):
    initial_idea: str

@router.post("/projects/{project_id}/mega/plan")
async def mega_project_plan(project_id: str, req: MegaPlanRequest, p: Principal = Depends(current_principal)):
    """마스터 에이전트 연동: 초기 기획안을 바탕으로 master_data를 추천/생성"""
    assert_project_writable(p, project_id)
    _safe_id(project_id, "project_id")
    state_path = workspace_path(project_id, "latest_state.json")
    if not os.path.exists(state_path):
        raise HTTPException(status_code=404, detail="마스터 프로젝트 상태를 찾을 수 없습니다.")
        
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            master_state = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태 읽기 오류: {e}")

    # LLM 호출을 통해 master_data 도출
    from core.llm_gateway import gateway
    
    prompt = f"""
당신은 기업의 전사 목표를 설정하고 거시 변수를 관리하는 최고 경영자(CEO/Master) 에이전트입니다.
사용자가 다음의 시나리오 기획을 전달했습니다:
"{req.initial_idea}"

이 기획을 분석하여, 서브 프로젝트(생산, 재무, 마케팅 등) 시뮬레이션 전체에 공통으로 적용될 초기 'master_data'(거시 경제 지표, 전사 예산, 원자재 단가 예측치 등)를 JSON 형태로 도출하세요.
반드시 아래 JSON 스키마를 따르십시오.
{{
    "추천_지표_1": "값",
    "추천_지표_2": "값"
}}
"""
    try:
        response = await gateway.aexecute(
            state=master_state,
            skill_prompt=prompt,
            is_heavy=True,
            output_mode="json"
        )
        recommended_data = json.loads(response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"마스터 데이터 분석 중 오류: {e}")

    master_state["master_data"] = json.dumps(recommended_data, ensure_ascii=False, indent=2)
    master_state["initial_idea"] = req.initial_idea
    
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(master_state, f, ensure_ascii=False, indent=2)
        
    return {"status": "success", "master_data": master_state["master_data"]}

@router.post("/projects/{project_id}/mega/start_all")
async def start_all_mega_subprojects(project_id: str, p: Principal = Depends(current_principal)):
    """마스터에 종속된 모든 서브 프로젝트 일괄 가동"""
    assert_project_writable(p, project_id)
    _safe_id(project_id, "project_id")
    state_path = workspace_path(project_id, "latest_state.json")
    if not os.path.exists(state_path):
        raise HTTPException(status_code=404, detail="마스터 프로젝트 상태를 찾을 수 없습니다.")
        
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            master_state = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태 읽기 오류: {e}")
        
    sub_map = master_state.get("sub_projects_map", {})
    if not sub_map:
        raise HTTPException(status_code=400, detail="연결된 서브 프로젝트가 없습니다.")
        
    results = []
    import time
    for domain, sub_id in sub_map.items():
        sub_ws = workspace_path(sub_id)
        sub_state_path = os.path.join(sub_ws, "latest_state.json")
        
        try:
            with open(sub_state_path, "r", encoding="utf-8") as f:
                sub_state = json.load(f)
        except Exception:
            continue
            
        # 마스터 데이터 주입 - master_data 는 JSON '문자열'이므로 그대로 str 필드에 싣고,
        # shared_ledger(Dict[str, dict])에는 파싱한 dict 를 키로 감싸 넣는다
        # (문자열을 그대로 넣으면 첫 노드의 model_validate 에서 ValidationError 로 서브 전체가 즉사)
        _md_str = master_state.get("master_data", "") or ""
        sub_state["master_data"] = _md_str
        try:
            _md = json.loads(_md_str) if _md_str.strip() else {}
        except Exception:
            _md = {}
        sub_state["shared_ledger"] = {"master_data": _md} if isinstance(_md, dict) else {}
        sub_state["initial_idea"] = master_state.get("initial_idea", "")
        
        # 새 Task ID로 PLANNING 가동
        task_id = f"PLANNING_{int(time.time() * 1000)}_{domain}"
        sub_state["current_sprint_task_id"] = task_id
        sub_state["factory_mode"] = "PLANNING"
        sub_state["workspace_root"] = sub_ws
        sub_state["template_id"] = _read_project_template(sub_ws)
        
        with open(sub_state_path, "w", encoding="utf-8") as f:
            json.dump(sub_state, f, ensure_ascii=False, indent=2)
            
        await orchestrator.start_sprint(task_id, sub_state, sub_ws)
        results.append(sub_id)
        
    return {"status": "success", "started_projects": results}

@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, purge: bool = False,
                         reason: str = "",
                         p: Principal = Depends(current_principal)):
    """프로젝트 삭제 (사용자 결정 2026-08-07).

    - 기본은 **표시 삭제**다 — `project_meta.json` 에 표시만 남기고 **파일은 지우지 않는다.**
      등록자 본인이 할 수 있다. 단, 남에게 공유·전달된 프로젝트는 관리자만 할 수 있다.
    - `?purge=true` 는 **실제 삭제**다 — 디렉터리와 체크포인트를 지운다. **관리자만.**

    ★ 판정은 `core/project_deletion.classify()` 한 곳에 있다. 여기서 조건을 다시 쓰지 않는다 —
      화면·스크립트가 같은 답을 얻어야 「버튼은 보이는데 서버는 거부한다」가 생기지 않는다.

    ⚠️ 종전에는 `assert_project_writable` 하나로 **곧바로 `rmtree`** 했다. 그 함수는
      「소유권 미기록 프로젝트는 통과」라는 읽기용 관대함을 갖고 있어서, 실측에서 **viewer
      계정이 200 을 받았다.** 되돌릴 수 없는 삭제에 읽기용 관대함을 쓰면 안 된다."""
    from core import project_deletion as pdel

    _safe_id(project_id, "project_id")  # rmtree 대상 경로 이탈 방지(가장 파괴적인 벡터)
    assert_project_readable(p, project_id)      # 존재를 알려도 되는 사람인가 먼저
    verdict = pdel.classify(p.scope, p.user_id, project_id)
    try:
        verdict.assert_hard() if purge else verdict.assert_soft()
    except pdel.DeletionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    projects_dir = workspace_path()

    if not purge:
        # ── 표시 삭제 — 아무것도 지우지 않는다 ──────────────────────────────
        # ⚠️ 실행 중 스프린트는 멈춘다. 목록에서 사라진 프로젝트가 계속 돌면서 비용을 쓰면
        #   아무도 그것을 보지 못한다(좀비 스프린트).
        await orchestrator.cancel_project(project_id)
        out = await asyncio.to_thread(pdel.mark_deleted,
                                      os.path.join(projects_dir, project_id),
                                      p.user_id or "", reason)
        return {"status": "success", "data": {**out, "purged": False},
                "message": "표시 삭제했습니다. 데이터는 남아 있으며 관리자가 되돌릴 수 있습니다."}

    # ── 실제 삭제 (관리자만) ────────────────────────────────────────────────
    # 🛑 삭제 전, 해당 프로젝트와 서브 프로젝트들의 실행 중 스프린트를 취소 (좀비 스프린트 방지)
    await orchestrator.cancel_project(project_id)
    sub_projects = []
    if os.path.exists(projects_dir):
        for item in os.listdir(projects_dir):
            if item.startswith(f"{project_id}_"):
                sub_projects.append(item)
                await orchestrator.cancel_project(item)

    project_path = os.path.join(projects_dir, project_id)
    if os.path.exists(project_path):
        try:
            # 🚨 ignore_errors=True 대신 강제 권한 해제(onerror) 로직 적용
            shutil.rmtree(project_path, onexc=_on_rmtree_error)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"삭제 실패 (파일이 사용 중일 수 있습니다): {str(e)}")
            
    # 서브 프로젝트 디렉토리들도 삭제
    for sub in sub_projects:
        sub_path = os.path.join(projects_dir, sub)
        if os.path.exists(sub_path):
            try:
                shutil.rmtree(sub_path, onexc=_on_rmtree_error)
            except Exception:
                pass

    # 체크포인트 DB 정리: 삭제 프로젝트의 스레드(sprint_<pid>__<task>)를 지우지 않으면
    # DB 가 무한 증식하고, 같은 id 로 재생성 시 '옛 프로젝트의 체크포인트'에 이어붙는 오염이 생긴다.
    # (실패해도 프로젝트 삭제 자체는 성공 처리 - 베스트 에포트)
    await _purge_checkpoints([project_id] + sub_projects)
    return {"status": "success", "data": {"project_id": project_id, "purged": True,
                                          "sub_projects": sub_projects}}


@router.post("/projects/{project_id}/restore")
async def restore_project(project_id: str, p: Principal = Depends(current_principal)):
    """표시 삭제를 되돌린다. **데이터를 남겨 둔 이유가 이것이다.**

    ⚠️ 되돌리기가 없으면 «표시 삭제» 는 이름만 소프트다 — 사용자는 지운 것을 되찾을 방법이
      없고, 그러면 결국 관리자에게 실제 삭제를 요청하게 된다. 판정은 삭제와 같은 곳을 쓴다."""
    from core import project_deletion as pdel

    _safe_id(project_id, "project_id")
    assert_project_readable(p, project_id)
    verdict = pdel.classify(p.scope, p.user_id, project_id)
    try:
        verdict.assert_soft()          # 지울 수 있는 사람이 되돌릴 수도 있다
    except pdel.DeletionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    out = await asyncio.to_thread(pdel.restore,
                                  os.path.join(workspace_path(), project_id))
    if not out.get("restored"):
        raise HTTPException(status_code=404, detail="되돌릴 표시 삭제 기록이 없습니다.")
    return {"status": "success", "data": {"project_id": project_id, "restored": True}}


async def _purge_checkpoints(project_ids: list) -> None:
    """해당 프로젝트들의 LangGraph 체크포인트 스레드를 SQLite 에서 삭제한다.
    GLOB 사용 이유: LIKE 의 '_' 는 와일드카드라 다른 pid 를 오매칭할 수 있다(GLOB 은 '_' 가 리터럴)."""
    import config as _cfg
    try:
        import aiosqlite
        async with aiosqlite.connect(_cfg.PIPELINE_DB_FILE) as db:
            total = 0
            for pid in project_ids:
                pattern = f"sprint_{pid}__*"
                for table in ("checkpoints", "writes"):
                    try:
                        cur = await db.execute(f"DELETE FROM {table} WHERE thread_id GLOB ?", (pattern,))
                        total += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                    except Exception:
                        pass  # 테이블 미존재(첫 가동 전) 등은 무시
            await db.commit()
            if total:
                print(f"🧹 [Checkpoint] 삭제 프로젝트 스레드 정리: {total}행 제거. 공간 회수(VACUUM) 실행...")
                await db.execute("VACUUM")
        if total:
            print("🧹 [Checkpoint] VACUUM 완료.")
    except Exception as e:
        print(f"⚠️ [Checkpoint] 체크포인트 정리 실패(무시하고 진행): {e}")

@router.post("/projects/{project_id}/copy")
async def copy_project(project_id: str, req: ProjectCopyRequest,
                          p: Principal = Depends(current_principal)):
    _safe_id(project_id, "project_id")
    assert_project_writable(p, project_id)
    _safe_id(req.new_project_id, "new_project_id")
    
    src_path = workspace_path(project_id)
    dst_path = workspace_path(req.new_project_id)
    
    if not os.path.exists(src_path):
        raise HTTPException(status_code=404, detail="원본 프로젝트가 없습니다.")
    if os.path.exists(dst_path):
        raise HTTPException(status_code=409, detail="새 프로젝트 ID가 이미 존재합니다.")
        
    try:
        shutil.copytree(src_path, dst_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"복사 실패: {e}")
        
    return {"status": "success", "new_project_id": req.new_project_id}

@router.post("/{project_id}/sprint/start")
async def start_sprint(project_id: str, req: SprintStartRequest,
                          p: Principal = Depends(current_principal)):
    _safe_id(project_id, "project_id")
    assert_project_writable(p, project_id)
    workspace_root = f"./projects/{project_id}"
    req.project_state_payload["workspace_root"] = workspace_root
    # T2-b: 프로젝트에 바인딩된 템플릿을 권위 있는 출처(project_meta.json)에서 주입 — 프론트 state 가
    #   stale 해도 모든 태스크가 같은 워크플로우로 실행되도록 보장(오케스트레이터가 이 값으로 그래프 선택).
    req.project_state_payload["template_id"] = _read_project_template(workspace_root)
    # 지식팩 연결도 동일하게 권위 원본에서 주입 - 모든 에이전트 호출의 그라운딩 기준
    req.project_state_payload["knowledge_pack_ids"] = _read_project_packs(workspace_root)
    # [M1] 기준정보 도메인 태그도 권위 원본에서 주입 - 결정론적 기준정보 주입의 도메인 필터
    req.project_state_payload["master_domains"] = _read_project_master_domains(workspace_root)
    # [M3] 외부 실측값 병기 토글도 권위 원본에서 주입(기본 off)
    req.project_state_payload["mcp_live_grounding"] = _read_project_mcp_live(workspace_root)

    # ── [D-019] 소유권도 같은 권위 원본에서 주입한다 ─────────────────────────────
    #
    # ★ 여기에 소유권만 빠져 있었다. `ProjectState.owner_dept_id` 는 **읽는 곳이 3군데인데
    #   주경로에서 채우는 곳이 0군데**였고(비용 텔레메트리·품질 텔레메트리·RAG 부서 필터),
    #   그래서 `llm_call_log.jsonl` 1,133건의 부서 귀속률이 **0%** 였다. 위 4줄과 같은 패턴으로
    #   한 줄씩 붙인다 — 프론트 state 가 stale 해도 진실원본이 이긴다.
    # ⚠️ 비어 있으면 **비운 채로** 둔다. 만든 사람을 모르는 프로젝트에 부서를 추정해 넣으면
    #   그것이 곧 「틀린 부서로 귀속된 비용 통계」이고, 틀린 숫자는 «미상» 보다 나쁘다.
    _own = _read_project_ownership(workspace_root)
    req.project_state_payload["owner_dept_id"] = _own["owner_dept_id"]
    req.project_state_payload["owner_user_id"] = _own["owner_user_id"]
    req.project_state_payload["visibility"] = _own["visibility"]
    # ⚠️ node 는 **지금 찍어서 싣는다**(D-019 스냅샷). 나중에 dept 로 다시 풀면 조직개편이
    #   과거 비용을 소급해 옮긴다. dept 를 node 로 **바꾸는** 것이 아니라 병기임에 유의 —
    #   바꾸면 `knowledge_base` 의 과거사례 주입이 오류 없이 0건이 된다.
    req.project_state_payload["owner_scope_node_id"] = _resolve_scope_node(_own["owner_dept_id"])

    # ── [D-017 §9 P3-2] 이 실행이 **무엇으로 돌았는지** 남긴다 ─────────────────
    #
    # ★ 산출물만 보고는 어느 구성이 만들었는지 되짚을 수 없었다. 그 질문은 언제나 문제가 생긴
    #   뒤에 나오고, 그때는 이미 구성이 여러 번 바뀌어 있다. 그래서 **시작 시점에** 찍는다.
    # ⚠️ 스냅샷 실패가 실행을 막지 않는다 — 기록 기능의 장애가 가동 불가가 되면 안 된다.
    #   대신 실패도 «이유가 붙은 미확인» 으로 기록되므로 조용히 사라지지 않는다.
    try:
        from core import config_snapshot as _snap
        _s = await asyncio.to_thread(_snap.capture,
                                     req.project_state_payload["template_id"])
        await asyncio.to_thread(_snap.write, workspace_root, _s)
        req.project_state_payload["config_fingerprint"] = _s.fingerprint
    except Exception as _e:
        print(f"⚠️ [factory] 구성 스냅샷 기록 실패(가동은 계속): {_e}")

    # 신규 기획(PLANNING)은 새 출발이므로 옛 누적 산출물을 복원하지 않는다.
    # 그 외(실행/리비전) 태스크는 stale 페이로드의 빈 누적 필드를 디스크 진실원본에서 복원.
    if not (req.task_id.startswith("PLANNING") and len(req.task_id.split("_")) == 2):
        req.project_state_payload = _restore_accumulated_from_disk(req.project_state_payload, workspace_root)
        # 🚨 태스크별 재작업 카운터 리셋 — 이전 태스크의 누적(supervisor_hops/developer_retry_count)이
        #   새 태스크로 새어 즉시 상한에 걸려 검수가 통째로 건너뛰어지는 크로스-태스크 오염 차단.
        #   (각 태스크는 독립적인 리뷰/빌드 재작업 예산을 받는다.)
        req.project_state_payload["supervisor_hops"] = 0
        req.project_state_payload["developer_retry_count"] = 0

    # 리비전 태스크(TASK_REV_*)는 Architect를 건너뛰고 Tech_Lead로 직행해야 하므로
    # 프론트엔드 오탐을 방어하기 위해 백엔드에서도 factory_mode를 강제 보정합니다.
    if req.task_id.startswith("TASK_REV_"):
        req.project_state_payload["factory_mode"] = "REVISION"

    req.project_state_payload["current_sprint_task_id"] = req.task_id

    # Reset old stages and inject current_required_agents from WBS
    wbs_path = os.path.join(workspace_root, "00_wbs_master_plan.json")
    if os.path.exists(wbs_path):
        try:
            with open(wbs_path, "r", encoding="utf-8") as f:
                wbs_data = json.load(f)
                for t in wbs_data.get("tasks", []):
                    if t.get("task_id") == req.task_id:
                        req.project_state_payload["current_required_agents"] = t.get("required_agents", [])
                        break
        except Exception:
            pass

    # Clear current_stage and stage_scores for execution so it runs cleanly
    if req.project_state_payload.get("factory_mode") == "EXECUTION" and not (req.task_id.startswith("PLANNING") and len(req.task_id.split("_")) == 2):
        req.project_state_payload["current_stage"] = ""
        # Remove old coding scores so it doesn't skip
        for st in ["CODE_REVIEW", "Backend", "Frontend", "QA"]:
            if "stage_scores" in req.project_state_payload and st in req.project_state_payload["stage_scores"]:
                del req.project_state_payload["stage_scores"][st]

    await orchestrator.start_sprint(req.task_id, req.project_state_payload, workspace_root)
    return {"status": "started", "task_id": req.task_id}

@router.post("/{project_id}/sprint/pause")
async def pause_sprint(project_id: str, req: SprintPauseRequest,
                          p: Principal = Depends(current_principal)):
    _safe_id(project_id, "project_id")
    assert_project_writable(p, project_id)
    await orchestrator.pause_sprint(req.task_id, project_id)
    return {"status": "paused", "task_id": req.task_id}

@router.post("/{project_id}/sprint/stop")
async def stop_sprint(project_id: str, req: SprintPauseRequest,
                          p: Principal = Depends(current_principal)):
    _safe_id(project_id, "project_id")
    assert_project_writable(p, project_id)
    # 빈 reason을 전달하여 SUPERVISOR 피드백 큐 삽입 없이 태스크만 강제 종료(Kill)
    await orchestrator.pause_sprint(req.task_id, project_id, reason="")
    return {"status": "stopped", "task_id": req.task_id}

async def _assert_resumable(project_id: str) -> None:
    """[D-017 §9 P3-4] 멈춰 있는 동안 구성이 바뀌지 않았는가.

    ★★ **두 재개 경로가 같은 한 줄을 쓴다.** 한쪽만 걸면 그쪽만 통제되고, 사용자는 막힌 쪽을
      피해 열린 쪽으로 간다 — 이 저장소가 반복해서 확인한 형태다.
    ⚠️ 판정은 `core/resume_guard.check()` 한 곳에 있다. 여기서 조건을 다시 쓰지 않는다."""
    from core import resume_guard
    ws = workspace_path(project_id)
    v = await asyncio.to_thread(resume_guard.check, ws, _read_project_template(ws))
    if not v.ok:
        # 409 — 요청은 정당하지만 **지금 상태와 맞지 않는다.** 403(권한)도 400(잘못된 요청)도
        # 아니다. 사용자가 할 일은 「구성을 되돌리거나 새로 가동」이다.
        raise HTTPException(status_code=409, detail=v.reason)


@router.post("/{project_id}/hotl/resume")
async def resume_from_hotl(project_id: str, req: HOTLResumeRequest, p: Principal = Depends(current_principal)):
    assert_project_writable(p, project_id)
    _safe_id(project_id, "project_id")
    await _assert_resumable(project_id)
    success = await orchestrator.resume_hotl(req.task_id, req.feedback, project_id)
    if not success:
        raise HTTPException(status_code=500, detail="파이프라인 재가동에 실패했습니다.")
    return {"status": "resumed", "task_id": req.task_id}

@router.post("/{project_id}/sprint/resume-quota")
async def resume_from_quota(project_id: str, req: SprintPauseRequest, p: Principal = Depends(current_principal)):
    """[R2] 쿼터 회복 후 SUSPENDED_QUOTA 로 동결된 스프린트를 마지막 체크포인트에서 재개.
    '처음부터 재실행'이 아니라 중단 지점부터 이어서 실행한다. 쿼터가 아직도 없으면 재개 스트림이
    다시 쿼터 소진을 만나 자연히 재동결된다(400 반환 조건: 대상이 SUSPENDED_QUOTA 상태가 아님)."""
    assert_project_writable(p, project_id)
    _safe_id(project_id, "project_id")
    await _assert_resumable(project_id)
    success = await orchestrator.resume_from_suspend(req.task_id, project_id)
    if not success:
        raise HTTPException(status_code=409, detail="쿼터 재개 대상이 아니거나(이미 실행 중/미동결) 재개에 실패했습니다.")
    return {"status": "resumed", "task_id": req.task_id}

@router.post("/{project_id}/supervisor/chat")
async def supervisor_chat(project_id: str, req: SupervisorChatRequest,
                          p: Principal = Depends(current_principal)):
    _safe_id(project_id, "project_id")
    assert_project_readable(p, project_id)
    state_path = workspace_path(project_id, "latest_state.json")
    state_data = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)
        except:
            pass

    # [자비스 모드] 태스크/가동 여부와 무관하게 시스템 전체 현황을 브리핑으로 동봉 - 슈퍼바이저가
    # "지금 어디까지 됐어?", "왜 멈췄어?", "다른 프로젝트 상태는?" 같은 전역 질문에 답할 수 있게 한다
    snapshot = []
    try:
        st = state_data or {}
        snapshot.append(f"[현재 프로젝트 {project_id}] 단계={st.get('current_stage','?')} / 모드={st.get('factory_mode','?')} "
                        f"/ 태스크={st.get('current_sprint_task_id','없음')} / 단계점수={json.dumps(st.get('stage_scores') or {}, ensure_ascii=False)}")
        wbs_path = workspace_path(project_id, "00_wbs_master_plan.json")
        if os.path.exists(wbs_path):
            with open(wbs_path, "r", encoding="utf-8") as f:
                _tasks = (json.load(f) or {}).get("tasks", [])
            snapshot.append("[WBS] " + (", ".join(f"{t.get('task_id')}:{t.get('status')}" for t in _tasks) if _tasks else "태스크 없음(분할 실패 또는 미실행)"))
        else:
            snapshot.append("[WBS] 아직 생성되지 않음(기획 미완)")
        _hotl = await orchestrator.is_hotl_pending(st.get("current_sprint_task_id", "") or "sprint_init", project_id)
        snapshot.append(f"[HOTL] {'사용자 승인 대기 중' if _hotl else '대기 없음'}")
        from core.sys_logger import get_recent_logs
        snapshot.append("[최근 서버 로그]\n" + "\n".join(get_recent_logs()[-12:]))
        # 🚨 [Phase 4] 부서 유출 차단. 예전엔 전체 프로젝트 이름을 그대로 LLM 브리핑에 넣어
        #   다른 부서의 프로젝트명이 새어나갔다. 요청자에게 보이는 것만 넣는다.
        _projs = _iter_visible_projects(p)
        snapshot.append(f"[열람 가능 프로젝트 {len(_projs)}개] " + ", ".join(_projs[:25]))
    except Exception as e:
        snapshot.append(f"(현황 수집 일부 실패: {e})")

    from core.supervisor_daemon import supervisor_daemon
    response = await supervisor_daemon.handle_user_chat(project_id, req.task_id or "", req.message, state_data,
                                                        system_snapshot="\n".join(snapshot))
    return response

@router.get("/{project_id}/hotl/check")
async def check_hotl(project_id: str, p: Principal = Depends(current_principal)):
    """진행 중(IN_PROGRESS) 태스크가 HOTL 중단점에서 대기 중인지 조회 (SSE 이벤트 유실 복구용)."""
    assert_project_readable(p, project_id)
    _safe_id(project_id, "project_id")

    if await orchestrator.is_hotl_pending("sprint_init", project_id):
        return {"status": "success", "hotl_task_id": "sprint_init"}

    # 기획(PLANNING_*) 태스크는 WBS 목록에 없으므로 latest_state 의 현재 태스크 id 로도 확인
    # - 미확인 시 기획 중 SSE 유실되면 UI/자동화가 인터뷰·RFP·WBS 게이트 대기를 영영 감지 못 한다
    try:
        with open(workspace_path(project_id, "latest_state.json"), "r", encoding="utf-8") as f:
            _cur_tid = (json.load(f) or {}).get("current_sprint_task_id") or ""
        if _cur_tid and _cur_tid != "sprint_init" and await orchestrator.is_hotl_pending(_cur_tid, project_id):
            return {"status": "success", "hotl_task_id": _cur_tid}
    except Exception:
        pass

    from nodes.utils.wbs_manager import WBSManager
    try:
        wbs = WBSManager(workspace_root=f"./projects/{project_id}").get_wbs()
    except Exception:
        wbs = {"tasks": []}
    for t in wbs.get("tasks", []):
        if t.get("status") == "IN_PROGRESS":
            tid = t.get("task_id")
            if await orchestrator.is_hotl_pending(tid, project_id):
                return {"status": "success", "hotl_task_id": tid}
    return {"status": "success", "hotl_task_id": None}

@router.post("/{project_id}/sprint/revision")
async def create_revision_task(project_id: str, req: RevisionRequest, p: Principal = Depends(current_principal)):
    assert_project_writable(p, project_id)
    _safe_id(project_id, "project_id")
    
    if await orchestrator.is_hotl_pending("sprint_init", project_id):
        return {"status": "success", "hotl_task_id": "sprint_init"}
        
    from nodes.utils.wbs_manager import WBSManager
    wbs_mgr = WBSManager(workspace_root=f"./projects/{project_id}")
    task_id = wbs_mgr.add_revision_task(req.feedback)
    if not task_id:
        raise HTTPException(status_code=500, detail="WBS를 찾을 수 없습니다.")
    return {"status": "success", "task_id": task_id}

@router.post("/{project_id}/heal")
async def trigger_self_healing(project_id: str, req: HealRequest, p: Principal = Depends(current_principal)):
    assert_project_writable(p, project_id)
    _safe_id(project_id, "project_id")
    
    if await orchestrator.is_hotl_pending("sprint_init", project_id):
        return {"status": "success", "hotl_task_id": "sprint_init"}
        
    from nodes.utils.wbs_manager import WBSManager

    workspace_root = f"./projects/{project_id}"
    wbs_mgr = WBSManager(workspace_root=workspace_root)

    feedback = f"🚨 [자동 캡처 에러 리포트] UI 렌더링 중 에러 발생:\n{req.error_log}\n해당 에러를 분석하여 코드를 즉시 복원하십시오."
    task_id = wbs_mgr.add_revision_task(feedback)

    state_path = os.path.join(workspace_root, "latest_state.json")
    project_state_payload = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                project_state_payload = json.load(f)
        except:
            pass

    project_state_payload["build_error_log"] = req.error_log
    project_state_payload["factory_mode"] = "REVISION"
    project_state_payload["current_sprint_task_id"] = task_id
    project_state_payload["workspace_root"] = workspace_root
    project_state_payload["template_id"] = _read_project_template(workspace_root)  # T2-b: 바인딩 템플릿 유지

    await orchestrator.start_sprint(task_id, project_state_payload, workspace_root)
    return {"status": "healing_started", "task_id": task_id}

@router.post("/{project_id}/wbs/replan")
async def replan_wbs(project_id: str, p: Principal = Depends(current_principal)):
    """WBS 재분할 - 기획 산출물(RFP/PRD/UI/아키텍처)을 재사용해 Master_PMO 만 재실행한다.
    WBS 분할이 실패(빈 태스크)했거나 부실할 때 기획 전체 재가동 없이 복구하는 경로."""
    assert_project_writable(p, project_id)
    _safe_id(project_id, "project_id")
    workspace_root = f"./projects/{project_id}"
    state_path = os.path.join(workspace_root, "latest_state.json")
    if not os.path.exists(state_path):
        raise HTTPException(status_code=404, detail="프로젝트 상태가 없습니다. 기획부터 가동하세요.")
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            st = json.load(f) or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태 읽기 오류: {e}")
    if not (st.get("prd_summary") or "").strip():
        raise HTTPException(status_code=400, detail="기획 산출물(PRD)이 없어 재분할할 수 없습니다. 기획을 먼저 완료하세요.")

    import time as _time
    task_id = f"REPLAN_{int(_time.time() * 1000)}"
    st["current_sprint_task_id"] = task_id
    st["factory_mode"] = "EXECUTION"  # REPLAN_* 접두사가 라우팅을 결정(기획 산출물 재사용)
    st["needs_revision"] = False
    st["workspace_root"] = workspace_root
    st["template_id"] = _read_project_template(workspace_root)
    ok = await orchestrator.start_sprint(task_id, st, workspace_root)
    if not ok:
        raise HTTPException(status_code=409, detail="이미 실행 중인 스프린트가 있습니다.")
    return {"status": "started", "task_id": task_id}


@router.get("/{project_id}/wbs")
async def get_wbs_master_plan(project_id: str,
                          p: Principal = Depends(current_principal)):
    _safe_id(project_id, "project_id")
    assert_project_readable(p, project_id)
    wbs_path = workspace_path(project_id, "00_wbs_master_plan.json")
    if not os.path.exists(wbs_path):
        return {"status": "not_found", "data": None}
    try:
        with open(wbs_path, "r", encoding="utf-8") as f:
            wbs_data = json.load(f)
        return {"status": "success", "data": wbs_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"WBS 파일을 읽는 중 오류 발생: {str(e)}")

@router.get("/{project_id}/traceability")
async def get_traceability_data(project_id: str,
                          p: Principal = Depends(current_principal)):
    """산출물 추적성 맵핑 데이터(FR-ID ↔ Files)를 조회합니다."""
    _safe_id(project_id, "project_id")
    assert_project_readable(p, project_id)
    workspace_root = f"./projects/{project_id}"
    # ★ [2026-07-27 P0-3] 순수 로더로 교체.
    #   `TraceabilityManager` 생성자가 `os.makedirs` + `_init_if_not_exists()` 를 하므로
    #   **조회(GET)만 해도 파일·디렉터리를 만드는 부수효과**가 있었다.
    #   조회 API 가 상태를 바꾸면 안 된다(존재하지 않는 프로젝트를 조회하면 빈 껍데기가 생긴다).
    from nodes.utils.traceability_manager import read_mappings
    try:
        return {"status": "success", "data": read_mappings(workspace_root)}
    except Exception as e:
        return {"status": "error", "message": f"추적성 데이터 조회 실패: {str(e)}"}

@router.get("/{project_id}/traceability/impact")
async def get_traceability_impact(project_id: str, fr: str = "", file: str = "", feedback: str = "",
                          p: Principal = Depends(current_principal)):
    """[G1-4] 리비전 영향 분석(LLM 0콜) — 특정 FR-ID/파일, 또는 리비전 피드백 텍스트가
    건드리는 파일·태스크·연관 FR 범위를 역인덱스로 산출한다. 리비전 전 재작업 범위·회귀
    주의 대상을 결정론적으로 제시(HOTL 판단 근거)."""
    _safe_id(project_id, "project_id")
    assert_project_readable(p, project_id)
    from nodes.utils.traceability_manager import read_mappings, impact_of, analyze_feedback_impact
    mappings = read_mappings(f"./projects/{project_id}")
    try:
        if feedback:
            data = analyze_feedback_impact(feedback, mappings)
        else:
            fr_ids = [x.strip() for x in fr.split(",") if x.strip()]
            files = [x.strip() for x in file.split(",") if x.strip()]
            data = impact_of(mappings, fr_ids=fr_ids, files=files)
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": f"영향 분석 실패: {str(e)}"}


@router.get("/{project_id}/feed")
async def get_supervisor_feed(project_id: str,
                          p: Principal = Depends(current_principal)):
    """슈퍼바이저 콘솔 피드(토론·채점 내레이션) 조회 — 새로고침/재접속 복구용."""
    _safe_id(project_id, "project_id")
    assert_project_readable(p, project_id)
    feed_path = workspace_path(project_id, "supervisor_feed.json")
    if not os.path.exists(feed_path):
        return {"status": "success", "data": []}
    try:
        with open(feed_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"status": "success", "data": data if isinstance(data, list) else []}
    except Exception:
        return {"status": "success", "data": []}

@router.get("/{project_id}/state/latest")
async def get_latest_state(project_id: str,
                          p: Principal = Depends(current_principal)):
    _safe_id(project_id, "project_id")
    assert_project_readable(p, project_id)
    state_path = workspace_path(project_id, "latest_state.json")
    if not os.path.exists(state_path):
        tid, fid, vtype = _read_project_meta(workspace_path(project_id))
        return {"status": "not_found", "data": {"template_id": tid, "output_format_id": fid, "view_type": vtype}}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state_data = json.load(f)
        # fallback to meta if missing in state
        if "output_format_id" not in state_data or not state_data["output_format_id"]:
            _, fid, vtype = _read_project_meta(workspace_path(project_id))
            state_data["output_format_id"] = fid
            state_data["view_type"] = vtype
        return {"status": "success", "data": state_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태 파일 읽기 오류: {str(e)}")


# ==========================================
# 백엔드 서버 시스템 로그 조회
# ==========================================
@router.get("/logs")
async def get_system_logs(
        p: Principal = Depends(current_principal)):
    """백엔드 메모리 큐에 쌓인 최근 서버 로그를 반환합니다."""
    assert_identified(p, WHAT)
    try:
        from core.sys_logger import get_recent_logs
        logs = get_recent_logs()
        return {"status": "success", "data": logs}
    except ImportError:
        return {"status": "success", "data": ["로그 시스템 초기화 중입니다..."]}


# ==========================================
# 결과물 라이브러리 (배포/최종 결과물 저장 + 보관 + 재실행)
# ==========================================
@router.post("/{project_id}/release")
async def create_release(project_id: str,
                          p: Principal = Depends(current_principal)):
    """완료된 프로젝트의 최종 결과물을 라이브러리에 스냅샷 저장(배포)."""
    _safe_id(project_id, "project_id")  # 경로 이탈 방지 + release_id가 라이브러리 라우트와 왕복 가능하도록 보장
    assert_project_writable(p, project_id)
    state_path = workspace_path(project_id, "latest_state.json")
    if not os.path.exists(state_path):
        raise HTTPException(status_code=404, detail="저장할 결과물 상태가 없습니다.")
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            s = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태 읽기 오류: {str(e)}")

    # [P1-5] 조직 워크플로우(`as_…`)로 만든 프로젝트도 게시돼야 한다.
    # ⚠️ `require_runnable=False` — 이미 실행이 끝난 것이다. 그 사이 자산이 폐기되거나 개정돼
    #   초안으로 내려갔다고 게시를 막으면, **이미 만들어진 산출물을 꺼낼 수 없게** 된다.
    from core.agent_asset_adapter import resolve_workflow
    from core.agent_assets import AssetError, AssetNotFound
    tid = s.get("template_id", "default")
    try:
        template_data = resolve_workflow(tid, require_runnable=False)
    except (AssetError, AssetNotFound) as e:
        # 정의를 못 찾아도 게시 자체는 진행한다 — 산출물은 이미 있다. 다만 **무엇으로 만들었는지
        # 모른다는 사실을 비워서 숨기지 않는다.**
        print(f"⚠️ [publish] 워크플로우 정의를 해석하지 못했습니다({tid}): {e}")
        template_data = {"id": tid, "agents": [], "unresolved": True, "unresolved_reason": str(e)}

    # ★ [2026-07-28 Phase 5] 게시 시점의 소유권을 릴리스에 **고정**한다.
    #   `scripts/migrate_org_ownership.py:99-109` 가 릴리스에 이 필드가 있다고 전제하는데
    #   생성 경로가 안 남겨서 신규 릴리스마다 마이그레이션을 다시 돌려야 했다. 또한 게시 후
    #   프로젝트 소유권이 바뀌어도 **이미 게시된 것의 출처는 게시 당시 부서**여야 한다.
    _rel_own = _read_project_ownership(workspace_path(project_id))

    wbs_tasks = []
    wbs_path = workspace_path(project_id, "00_wbs_master_plan.json")
    if os.path.exists(wbs_path):
        try:
            with open(wbs_path, "r", encoding="utf-8") as f:
                wbs_tasks = json.load(f).get("tasks", [])
        except Exception:
            pass

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    release_id = f"{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    release = {
        "release_id": release_id,
        "project_id": project_id,
        "project_name": s.get("project_name", project_id),
        "created_at": created_at,
        "template_id": s.get("template_id", "default"),
        "deliverable_type": template_data.get("deliverable_type", "software_app"),
        "rfp_summary": s.get("rfp_summary", ""),
        "prd_summary": s.get("prd_summary", ""),
        "architecture_summary": s.get("architecture_summary", ""),
        "tech_spec_summary": s.get("tech_spec_summary", ""),
        "frontend_code_summary": s.get("frontend_code_summary", ""),
        "backend_code_summary": s.get("backend_code_summary", ""),
        "code_review_report_summary": s.get("code_review_report_summary", ""),
        "qa_report_summary": s.get("qa_report_summary", ""),
        "user_manual_summary": s.get("user_manual_summary", ""),
        "wbs_tasks": wbs_tasks,
        # ★ [2026-07-27 P0-2] `artifacts` 를 릴리스 파일에 남긴다.
        #   기존엔 artifacts 가 아래 Chroma 인덱싱의 **입력으로만** 소비되고 release.json 에
        #   저장되지 않아, 게시 후에는 범용 T3 에이전트 산출물을 되찾을 방법이 없었다.
        #   게시 정합화·전사 롤업의 입력원이며, A-1 완주 판정의 '게시 확인' 근거이기도 하다.
        "artifacts": s.get("artifacts", {}) or {},
        "artifact_summaries": {
            k: (v[:2000] if isinstance(v, str) else v)
            for k, v in (s.get("artifacts", {}) or {}).items()
        },
        # 종료 상태를 함께 남겨, 미해결 결함을 안고 게시된 릴리스를 사후에 식별할 수 있게 한다.
        "terminal_status": s.get("terminal_status", ""),
        "terminal_reason": s.get("terminal_reason", ""),
        # [Phase 5] 게시 당시 소유 부서·가시성(위 `_rel_own` 주석 참조).
        "owner_dept_id": _rel_own.get("owner_dept_id", ""),
        "visibility": _rel_own.get("visibility", "dept"),
    }
    # ★★ [CL-0 · 2026-08-03] **App-in-App Capability Manifest 를 릴리스에 고정한다.**
    #   이 릴리스가 나중에 개인에게 전달될 때(CL-1), 수신자는 "이 앱이 무엇을 요구하는가"를 보고
    #   수락한다. 그 선언이 릴리스에 없으면 전달 화면이 보여줄 것이 없고, 결국 "그냥 수락"이 된다.
    #   ⚠️ 능력을 추측해 채우지 않는다 — `minimal()` 은 빈 능력이며 그것이 안전한 방향이다.
    #     그럴듯한 값을 채우면 **선언하지 않은 권한이 선언된 것으로** 남고 이후 판정의 근거가 된다.
    #   ⚠️ 정적 인증 검사(`nodes/utils/platform_auth_checker.py`)는 게시를 막지 않고 결과를
    #     함께 싣는다 — 이 시점에 막으면 이미 만들어진 산출물이 사라지고, 그러면 다음 사람은
    #     검사를 끄는 쪽을 택한다. 차단은 전달(CL-1) 단계에서 한다.
    try:
        from core import app_manifest
        _declared = (s.get("app_manifest") or template_data.get("app_manifest") or {})
        release["manifest"] = app_manifest.snapshot(_declared)
    except Exception as e:
        print(f"⚠️ [CL-0] Manifest 생성 실패(릴리스는 계속 게시): {e}")
        release["manifest"] = {"manifest": None, "fingerprint": "", "valid": False,
                               "errors": [f"생성 실패: {e}"]}
    try:
        from nodes.utils.platform_auth_checker import scan_paths
        _scan = scan_paths([workspace_path(project_id)])
        release["platform_auth_scan"] = {
            "ok": _scan["ok"], "summary": _scan["summary"],
            # 근거 줄을 그대로 싣는다 — 개발자가 반박할 수 있어야 판정이 신뢰받는다.
            "blocking": _scan["blocking"][:20], "warnings": _scan["warnings"][:20],
        }
        if not _scan["ok"]:
            print(f"⚠️ [CL-0] 생성 앱에 자체 인증 신호 {_scan['summary']['blocking']}건 — "
                  f"전달(CL-1) 단계에서 차단된다: {release_id}")
    except Exception as e:
        print(f"⚠️ [CL-0] 자체 인증 정적 검사 실패(릴리스는 계속 게시): {e}")
        release["platform_auth_scan"] = {"ok": None, "error": str(e)}

    # ── [D-017 §9 P3-2] 릴리스에 **무엇이 만들었는지**를 함께 봉인한다 ─────────
    #
    # ★ 프로젝트의 스냅샷은 계속 바뀌지만 릴리스는 그 시점에 고정된다. 릴리스에 붙여 두지
    #   않으면 「이 산출물은 어느 구성이 만들었나」를 나중에 되짚을 수 없다 — 프로젝트 쪽
    #   기록은 그 사이 여러 번 덮였을 수 있기 때문이다.
    # ⚠️ 읽지 못하면 **키를 비우지 않고** «미확인» 을 적는다. 키가 없으면 「옛날 릴리스라
    #   기록이 없다」와 「이번에 못 읽었다」가 같아진다.
    try:
        from core import config_snapshot as _snap
        # ⚠️ 이 함수에는 `workspace_root` 지역변수가 없다 — `workspace_path()` 단일 지점을 쓴다.
        _cur = (_snap.read(workspace_path(project_id)) or {}).get("current")
        release["config_snapshot"] = _cur or {
            "resolved": False, "error": "실행 시점 구성 스냅샷을 찾지 못했습니다."}
    except Exception as _e:
        release["config_snapshot"] = {"resolved": False, "error": f"읽기 실패: {_e}"}

    rel_dir = library_paths.release_dir(release_id)
    os.makedirs(rel_dir, exist_ok=True)
    with open(os.path.join(rel_dir, "release.json"), "w", encoding="utf-8") as f:
        json.dump(release, f, ensure_ascii=False, indent=2)

    # [Phase 5] 릴리스 소유권 미러 — `assert_release_readable`(api/deps.py:129)이 이 미러를
    #   읽는다. 안 심으면 소유권 미기록으로 간주돼 전원 통과한다. 프로젝트와 같은 규약으로,
    #   미러 실패가 게시 자체를 막지 않도록 조용히 넘어간다(`_sync_project_ownership` 동일).
    if _rel_own.get("owner_dept_id"):
        try:
            from core.org_directory import org_directory
            org_directory.set_ownership("release", release_id,
                                        dept_id=_rel_own.get("owner_dept_id", ""),
                                        owner_user_id=_rel_own.get("owner_user_id", ""),
                                        visibility=_rel_own.get("visibility", "dept"))
        except Exception as e:
            print(f"⚠️ 릴리스 ownership 미러 갱신 실패(무시): {e}")

    # 지식 베이스(RAG) 인덱싱 (백그라운드에서 실행되도록 asyncio_task 등록 등 가능하지만 여기서는 간단히 직접 호출)
    try:
        from core.knowledge_base import knowledge_base
        import asyncio
        
        # 파일 내용을 구성
        files_content = {
            "rfp.md": release.get("rfp_summary", ""),
            "prd.md": release.get("prd_summary", ""),
            "architecture.md": release.get("architecture_summary", ""),
            "tech_spec.md": release.get("tech_spec_summary", ""),
            "code_review.md": release.get("code_review_report_summary", ""),
            "qa_report.md": release.get("qa_report_summary", ""),
            "manual.md": release.get("user_manual_summary", "")
        }
        
        # 범용 T3 에이전트들의 산출물
        artifacts = s.get("artifacts", {})
        for k, v in artifacts.items():
            if isinstance(v, str) and v.strip():
                files_content[f"{k}.md"] = v
                
        # 워크스페이스 내 주요 파일들도 읽어서 추가 가능 (코드 등)
        ws_path = workspace_path(project_id)
        for root_dir, _, files in os.walk(ws_path):
            if any(exc in root_dir for exc in [".git", "node_modules", "dist", ".archive"]):
                continue
            for fname in files:
                if fname.endswith(('.md', '.py', '.ts', '.tsx', '.json', '.txt')):
                    fpath = os.path.join(root_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as rf:
                            files_content[fname] = rf.read()
                    except:
                        pass
        
        metadata = {
            "template_id": release.get("template_id", "default"),
            "deliverable_type": release.get("deliverable_type", "software_app"),
            # ★ [2026-07-28 Phase 5] **부서 필터의 유일한 공급원**.
            #   ⚠️ 이것을 안 넘기면 `index_release`(knowledge_base.py:390)가 청크 메타를
            #     `owner_dept_id=""` 로 심고, `get_relevant_context` 의 fail-closed `$in`
            #     필터가 **자기 부서 산출물까지 전부 배제**한다 → 과거사례 RAG 가 오류 하나 없이
            #     조용히 0건이 된다. 실제로 그 상태였다(설계서 재사용자산 표 870행이 전제한
            #     배선의 나머지 절반).
            "owner_dept_id": _rel_own.get("owner_dept_id", ""),
        }

        # 메인 스레드 블로킹을 피하기 위해 비동기로 위임 (FastAPI BackgroundTasks도 좋으나 여기서는 asyncio)
        loop = asyncio.get_running_loop()
        loop.run_in_executor(
            None, 
            knowledge_base.index_release, 
            project_id, 
            release_id, 
            files_content, 
            metadata
        )
    except Exception as e:
        print(f"⚠️ [FactoryControl] 지식 베이스 인덱싱 트리거 실패: {e}")

    return {"status": "success", "release_id": release_id}


# ==========================================
# 산출물 Export (프로젝트 워크스페이스 → zip 다운로드)
# ==========================================
# zip 에서 제외할 무거운/비산출물 디렉토리(빌드 캐시·의존성·VCS·아카이브).
_EXPORT_EXCLUDE_DIRS = {".git", "node_modules", "dist", "build", ".archive", "__pycache__", ".venv", "venv"}


@router.get("/{project_id}/export")
async def export_project_zip(project_id: str,
                          p: Principal = Depends(current_principal)):
    """프로젝트 워크스페이스(생성된 코드·문서 등 모든 산출물)를 zip 으로 패키징해 스트리밍 다운로드한다.
    의존성/빌드 캐시/VCS 디렉토리(_EXPORT_EXCLUDE_DIRS)는 제외한다.
    zip 내부는 project_id 를 최상위 폴더로 하는 상대경로 구조를 유지한다."""
    _safe_id(project_id, "project_id")  # 경로 이탈 방지(임의 디렉토리 압축 차단)
    assert_project_readable(p, project_id)
    project_path = workspace_path(project_id)
    if not os.path.isdir(project_path):
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

    def _build_zip():
        buf = io.BytesIO()
        file_count = 0
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root_dir, dirs, files in os.walk(project_path):
                # 제외 디렉토리는 하위 순회 자체를 건너뛴다(성능·용량).
                dirs[:] = [d for d in dirs if d not in _EXPORT_EXCLUDE_DIRS]
                for fname in files:
                    fpath = os.path.join(root_dir, fname)
                    arcname = os.path.join(project_id, os.path.relpath(fpath, project_path))
                    try:
                        zf.write(fpath, arcname)
                        file_count += 1
                    except Exception:
                        continue  # 잠긴/읽기 불가 파일은 건너뛰고 나머지를 계속 패키징
        return buf, file_count

    # 압축(CPU+디스크)은 동기 작업 - 대형 프로젝트에서 이벤트 루프 동결 방지 위해 스레드로
    buf, file_count = await asyncio.to_thread(_build_zip)

    if file_count == 0:
        raise HTTPException(status_code=404, detail="내보낼 산출물이 없습니다.")

    buf.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="{project_id}.zip"'}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)


# ==========================================
# 시뮬레이션 인자 변경 반복 재실행 (Re-simulation)
# ==========================================
class ResimulateRequest(BaseModel):
    modified_params: dict  # 변경된 인자 값 {"환율": 1450, "유가": 85}
    base_cycle: int = 1    # 기준 사이클 번호

@router.post("/{project_id}/resimulate")
async def resimulate(project_id: str, req: ResimulateRequest,
                          p: Principal = Depends(current_principal)):
    """시뮬레이션 인자를 변경하여 재실행. 기존 변수 정의를 유지한 채 Validator → 실행 파이프라인만 재가동."""
    _safe_id(project_id, "project_id")
    assert_project_writable(p, project_id)
    
    state_path = workspace_path(project_id, "latest_state.json")
    if not os.path.exists(state_path):
        raise HTTPException(status_code=404, detail="재실행할 시뮬레이션 상태가 없습니다.")
    
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            current_state = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태 읽기 오류: {str(e)}")
    
    # 사이클 번호 관리
    cycle_count = current_state.get("sim_cycle_count", 1) + 1
    
    # 이전 사이클 결과를 보존 (artifacts에 사이클 태깅)
    artifacts = current_state.get("artifacts", {})
    artifact_summaries = current_state.get("artifact_summaries", {})
    
    # 이전 사이클 결과를 cycle_N_ 접두사로 보존
    prev_cycle = cycle_count - 1
    preserved_artifacts = {}
    preserved_summaries = {}
    for key, val in artifacts.items():
        preserved_artifacts[f"cycle_{prev_cycle}_{key}"] = val
    for key, val in artifact_summaries.items():
        preserved_summaries[f"cycle_{prev_cycle}_{key}"] = val
    
    # 변경된 인자 정보를 initial_idea에 추가 (에이전트들이 참조할 수 있도록)
    modified_params_text = "\n".join([f"- {k}: {v}" for k, v in req.modified_params.items()])
    resim_context = f"\n\n[시뮬레이션 {cycle_count}사이클 — 인자 변경 재실행]\n변경된 인자:\n{modified_params_text}\n\n이전 사이클({prev_cycle}사이클) 결과와 비교하여 분석하시오."
    
    # 새로운 태스크 ID 생성
    resim_task_id = f"TASK_RESIM_{cycle_count}"
    
    # 상태 업데이트
    updated_state = {
        **current_state,
        "current_sprint_task_id": resim_task_id,
        "factory_mode": "EXECUTION",  # 설계 단계 건너뛰고 실행
        "sim_cycle_count": cycle_count,
        "sim_modified_params": req.modified_params,
        "sim_base_cycle": req.base_cycle,
        "artifacts": {**preserved_artifacts},  # 이전 결과 보존, 현재 사이클은 비우기
        "artifact_summaries": {**preserved_summaries},
        "initial_idea": current_state.get("initial_idea", "") + resim_context,
    }
    
    # 상태 저장
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(updated_state, f, ensure_ascii=False, indent=2)
    
    # 스프린트 가동 (Validator부터 시작 — 설계 건너뛰기)
    workspace = workspace_path(project_id)
    success = await orchestrator.start_sprint(resim_task_id, updated_state, workspace)
    
    if success:
        return {
            "status": "success", 
            "cycle": cycle_count, 
            "task_id": resim_task_id,
            "message": f"{cycle_count}사이클 재실행이 시작되었습니다."
        }
    else:
        raise HTTPException(status_code=409, detail="이미 실행 중인 스프린트가 있습니다.")

@router.get("/library/list")
async def list_releases(
        p: Principal = Depends(current_principal)):
    """라이브러리에 보관된 결과물 목록(요약)."""
    assert_identified(p, WHAT)
    os.makedirs(library_paths.library_dir(), exist_ok=True)

    # ★ [M3] 승격 상태를 목록에 함께 준다. 이것이 없으면 승격이 별도 테이블에만 남아
    #   **"이 앱이 전사 앱인가"를 라이브러리에서 알 수 없다** — 승격 게이트가 통과 기록만
    #   만들고 아무것도 바꾸지 않는 상태가 된다(내가 M3 커밋에서 남긴 한계를 여기서 닫는다).
    #   조회 실패가 목록을 죽이지 않게 감싼다 — 승격은 부가 정보이고 목록은 본체다.
    _promo = {}
    try:
        from core.workspace_promotion import workspace
        for pr in workspace.list_promotions():
            if pr:
                _promo[pr["release_id"]] = pr
    except Exception as e:
        print(f"⚠️ [library] 승격 상태 조회 실패(목록은 계속): {e}")

    # ★ [사용자 결정 2026-07-30] 사용여부를 목록에 함께 준다. 이것이 없으면 IT 관리자가
    #   비활성화해도 목록에서는 여전히 멀쩡해 보이고, 사용자는 눌러본 뒤에야 막혔음을 안다.
    _life = {}
    try:
        from core.program_lifecycle import program_lifecycle
        _life = {r["release_id"]: r for r in program_lifecycle.list_statuses()}
    except Exception as e:
        print(f"⚠️ [library] 사용여부 조회 실패(목록은 계속): {e}")

    items = []
    for rid in os.listdir(library_paths.library_dir()):
        rp = library_paths.release_json(rid)
        if os.path.exists(rp):
            try:
                with open(rp, "r", encoding="utf-8") as f:
                    r = json.load(f)
                _rid = r.get("release_id", rid)
                pr = _promo.get(_rid)
                _lf = _life.get(_rid)
                items.append({
                    # 미기록은 사용 가능으로 보되 `lifecycle_recorded=False` 로 구분한다 —
                    #   추정을 관리자의 결정처럼 표시하면 감사에서 거짓이 된다.
                    "lifecycle_status": (_lf or {}).get("status", "active"),
                    "lifecycle_recorded": bool(_lf),
                    "lifecycle_reason": (_lf or {}).get("reason", ""),
                    "replacement_release_id": (_lf or {}).get("replacement_release_id", ""),
                    "release_id": _rid,
                    "project_name": r.get("project_name", rid),
                    "template_id": r.get("template_id", "default"),
                    "deliverable_type": r.get("deliverable_type", "software_app"),
                    "created_at": r.get("created_at", ""),
                    "task_count": len(r.get("wbs_tasks", [])),
                    # 승격되지 않은 것을 "dept" 로 두지 않는다 — 소유 부서와 승격 여부는
                    #   다른 축이다. 신청조차 없으면 promotion_status 는 빈 값이다.
                    "promotion_status": (pr or {}).get("status", ""),
                    "is_enterprise": bool(pr and pr.get("status") == "promoted"),
                    "promoted_at": (pr or {}).get("promoted_at", ""),
                })
            except Exception:
                continue
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"status": "success", "data": items}


@router.get("/library/item/{release_id}")
async def get_release(release_id: str, p: Principal = Depends(current_principal)):
    """결과물 상세(재실행/프리뷰용 — frontend 코드 포함).

    ⚠️ 사용 중단된 프로그램은 실행 payload 를 제외하고 준다(아래 lifecycle 블록 참조)."""
    _safe_id(release_id, "release_id")  # 경로 이탈로 임의 release.json 읽기 방지
    rp = library_paths.release_json(release_id)
    if not os.path.exists(rp):
        raise HTTPException(status_code=404, detail="결과물을 찾을 수 없습니다.")
    try:
        with open(rp, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"결과물 읽기 오류: {str(e)}")
    # ★ [M3] 승격 이력과 **승격 시점의 게이트 판정 스냅샷**을 함께 준다.
    #   "지금 기준으로 다시 재면 통과할까"와 "그때 무엇을 근거로 승격했나"는 다른 질문이고,
    #   후자에 답할 수 없으면 승인 이력이 근거가 되지 못한다.
    try:
        from core.workspace_promotion import workspace
        pr = workspace.get_promotion(data.get("release_id", release_id))
        data["promotion"] = pr
        data["is_enterprise"] = bool(pr and pr.get("status") == "promoted")
    except Exception as e:
        data["promotion"] = None
        data["promotion_error"] = str(e)

    # ★ [사용자 결정 2026-07-30] 사용 중단된 프로그램은 **기록은 보이되 실행 payload 를 주지
    #   않는다.** 이 경로는 "재실행/프리뷰용"이므로 코드를 그대로 주면 비활성화가 UI 표시에만
    #   의존하게 되고, API 를 직접 부르면 그대로 쓸 수 있다 — 그건 통제가 아니다.
    #   반대로 전체를 404 로 감추면 다른 사용자가 남긴 기록의 출처를 확인할 수 없게 된다.
    try:
        from core.program_lifecycle import ProgramLifecycleError, program_lifecycle
        try:
            data["lifecycle"] = program_lifecycle.assert_usable(
                data.get("release_id", release_id))
        except ProgramLifecycleError as e:
            st = program_lifecycle.get_status(data.get("release_id", release_id))
            for k in ("frontend_code_summary", "backend_code_summary",
                      "artifacts", "artifact_summaries"):
                data.pop(k, None)
            data["lifecycle"] = {"usable": False, "status": st["status"],
                                 "recorded": st["recorded"], "reason": str(e),
                                 "replacement_release_id":
                                     st.get("replacement_release_id", "")}
            data["payload_withheld"] = (
                "사용이 중단된 프로그램이므로 실행·프리뷰용 코드는 제공하지 않습니다. "
                "메타데이터와 이력은 그대로 남아 있습니다(삭제된 것이 아닙니다).")
            try:
                from core.enterprise_context import audit
                audit.record(audit.PROGRAM_USE_BLOCKED, resource_type="program",
                             resource_id=release_id, actor=p.user_id or "",
                             outcome="denied", reason="disabled",
                             detail="library/item payload withheld")
            except Exception:
                pass
    except Exception as e:
        # 사용여부를 못 읽었으면 "사용 가능"이라고 단정하지 않는다.
        data["lifecycle"] = {"usable": None, "status": "unknown", "reason": str(e)}
    return {"status": "success", "data": data}


@router.delete("/library/item/{release_id}")
async def delete_release(release_id: str, force: bool = False,
                         p: Principal = Depends(current_principal)):
    """⚠️ 기본적으로 **삭제하지 않는다.**

    [사용자 결정 2026-07-30] 이미 다른 사용자가 기록을 남긴 프로그램을 지우면 그 기록이
    고아가 된다 — 결재 이력·감사 로그·지식팩 인덱스·파생 프로그램의 출처가 전부 끊긴다.
    필요한 조치는 "사용 중단"이고, 그건 `POST /programs/{id}/disable` 이다.

    그래도 지워야 하는 경우(오게시·시험 산출물)를 위해 `force=true` 를 남겨두되,
    **IT 관리자 + 이미 비활성 상태 + 의존 없음**을 모두 요구한다."""
    _safe_id(release_id, "release_id")  # 경로 이탈로 임의 디렉토리 삭제 방지
    rel_dir = library_paths.release_dir(release_id)
    if not os.path.isdir(rel_dir):
        raise HTTPException(status_code=404, detail="결과물을 찾을 수 없습니다.")

    if not force:
        raise HTTPException(status_code=409, detail={
            "message": ("배포된 프로그램은 삭제하지 않습니다 — 다른 사용자가 이 프로그램을 "
                        "근거로 남긴 기록이 고아가 됩니다."),
            "do_this_instead": f"POST /api/v1/programs/{release_id}/disable",
            "why": ("사용을 막는 것과 존재를 지우는 것은 다른 조치이며, 필요한 것은 전자입니다. "
                    "비활성화하면 기록·이력은 그대로 보존됩니다."),
            "if_you_really_must": ("IT 관리자 권한 + 이미 비활성 상태 + 의존 대상 없음을 "
                                   "갖춘 뒤 ?force=true 로 요청하십시오."),
        })

    if not (p.scope.unrestricted or p.scope.is_admin or p.scope.can_edit_org):
        raise HTTPException(status_code=403,
                            detail="프로그램 삭제는 IT 관리자만 할 수 있습니다.")
    try:
        from core.program_lifecycle import DISABLED, program_lifecycle
        st = program_lifecycle.get_status(release_id)
        if st["status"] != DISABLED:
            raise HTTPException(status_code=409, detail=(
                f"먼저 사용을 중단시키십시오(현재: {st['status']}). 곧바로 삭제하면 "
                f"사용 중인 프로그램이 예고 없이 사라집니다."))
        dep = program_lifecycle.dependents(release_id)
        if dep["count"]:
            raise HTTPException(status_code=409, detail=(
                f"의존 대상이 있어 삭제할 수 없습니다(영향 범위: {dep['blast_radius']}, "
                f"{dep['count']}건). 비활성 상태로 남겨두십시오."))
    except HTTPException:
        raise
    except Exception as e:
        # 확인할 수 없으면 삭제하지 않는다 — 모르는 것을 "안전하다"로 두지 않는다.
        raise HTTPException(status_code=500, detail=(
            f"사용여부·의존 관계를 확인할 수 없어 삭제를 중단했습니다: {e}"))
    try:
        # delete_project와 동일하게 onexc로 Windows 잠금/읽기전용 파일 실패를 표면화한다(ignore_errors=True의 무음 실패 방지)
        shutil.rmtree(rel_dir, onexc=_on_rmtree_error)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"삭제 실패 (파일이 사용 중일 수 있습니다): {str(e)}")
    return {"status": "success"}


# ==========================================
# 에이전트 마스터 제어판 — 레지스트리(역할/스킬/모델/순서/HOTL/활성화) 조회·저장
# (범용 멀티에이전트 플랫폼 Phase 1: 외부 SSOT. HOTL 중단점은 서버 재시작 시 그래프에 반영)
# ==========================================
class AgentRegistryPayload(BaseModel):
    version: Optional[int] = 1
    pipeline_name: Optional[str] = ""
    description: Optional[str] = ""
    deliverable_type: Optional[str] = "software_app"
    agents: list
    edges: Optional[list] = []


@router.get("/agents")
async def get_agent_registry(p: Principal = Depends(current_principal)):
    """에이전트 마스터 레지스트리 조회.

    ⚠️ [D-017 §2.1] 예전에는 `current_principal` 의존성이 아예 없었다 — 익명·타 사업부
      사용자가 전역 구성을 그대로 읽었다."""
    _require_caps(p, AGENT_READ, resource="agent_registry", action="read")
    # [P1-5] 어댑터를 경유한다. `data` 는 종전과 **같은 registry dict** 이고, 출처 표시만
    # 추가한다 — 화면이 «승인 이력 없이 돌고 있는 정의» 임을 말할 수 있어야 한다.
    from core.agent_asset_adapter import DEFAULT_WORKFLOW_ASSET_ID, get_file_asset
    a = get_file_asset(DEFAULT_WORKFLOW_ASSET_ID)
    return {"status": "success", "data": a["body"],
            "source": a["source"], "needs_migration": a["needs_migration"],
            "edit_via": a["edit_via"]}


@router.put("/agents")
async def update_agent_registry(payload: AgentRegistryPayload,
                                p: Principal = Depends(current_principal)):
    """제어판에서 편집한 레지스트리 저장(검증·정규화 후 영속화).

    ★★ [D-017 §9 P0-3] 이것은 **전역 기본 정의**다. 한 사람이 저장하면 전 사용자·전 프로젝트의
      파이프라인이 바뀐다 — 그래서 플랫폼 관리자 전용이다(`ADMIN_PERMISSIONS`).
      부서 단위로 다르게 쓰고 싶으면 템플릿을 복사한다(Copy 모델)."""
    _require_caps(p, SYSTEM_DEFAULT_EDIT, AGENT_UPDATE,
                  resource="agent_registry", action="update")
    from core.agent_registry import save_registry
    try:
        saved = save_registry(payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"레지스트리 저장 오류: {str(e)}")
    _audit_registry("AGENT_REGISTRY_UPDATED", p, "전역 에이전트 레지스트리 저장",
                    f"agents={len((saved or {}).get('agents') or [])}")
    # 주의: HOTL 중단점 등 실행 반영은 그래프 재컴파일(서버 재시작) 시 적용된다.
    return {"status": "success", "data": saved, "note": "HOTL 중단점 변경은 서버 재시작 후 파이프라인에 반영됩니다."}


@router.post("/agents/reset")
async def reset_agent_registry(p: Principal = Depends(current_principal)):
    """레지스트리를 기본값(현재 SW 파이프라인)으로 초기화.

    ★★ **되돌릴 수 없는 전역 변경**이다. 누군가의 편집이 통째로 사라지므로 플랫폼 관리자 전용."""
    _require_caps(p, SYSTEM_DEFAULT_EDIT, AGENT_UPDATE,
                  resource="agent_registry", action="reset")
    from core.agent_registry import reset_registry
    data = reset_registry()
    _audit_registry("AGENT_REGISTRY_RESET", p, "전역 에이전트 레지스트리 초기화",
                    "사용자 편집분이 기본값으로 대체됨")
    return {"status": "success", "data": data}


@router.post("/agents/restore")
async def restore_agent_registry(p: Principal = Depends(current_principal)):
    """마지막 초기화 **직전** 구성으로 되돌린다. 백업이 없으면 404.

    ★★★ [병합 2026-08-05] 이 경로는 **되돌릴 수단**이다. 위 `reset` 은 되돌릴 수 없는 전역
      변경이고, 실제로 그것을 권한 탐침으로 호출해 `agents_registry.json` 을 잃은 사고가 있었다
      (git 미추적 파일이라 복구가 불가능했다). 그 뒤 `reset_registry()` 가 직전 상태를
      `agents_registry.prev.json` 으로 백업하고 **백업 실패 시 삭제를 거부**하게 됐고, 이
      엔드포인트가 그 백업을 되살린다.
    ⚠️ 자격은 `reset` 과 **같게** 둔다. 복원이 더 쉬우면 «지웠다가 되살리기» 로 통제를 우회할 수
      있고, 더 어려우면 사고를 낸 사람이 스스로 고칠 수 없다."""
    _require_caps(p, SYSTEM_DEFAULT_EDIT, AGENT_UPDATE,
                  resource="agent_registry", action="restore")
    from core.agent_registry import restore_registry
    data = restore_registry()
    if data is None:
        raise HTTPException(status_code=404,
                            detail="되돌릴 직전 구성이 없습니다(초기화 기록이 없습니다).")
    _audit_registry("AGENT_REGISTRY_RESTORED", p, "에이전트 구성 복원(초기화 직전 상태)",
                    "reset 으로 대체된 편집분을 되살렸다")
    return {"status": "success", "data": data}


# ==========================================
# AI 추천 엔진 연동 (파이프라인 및 스킬 자동 생성)
# ==========================================
class AIRecommendPipelineRequest(BaseModel):
    user_request: str
    # [D-017 §9 P2-3] 어느 조직 문맥에서 설계하는가. 비우면 요청자 문맥을 쓴다.
    scope_node_id: str = ""
    tenant_id: str = ""
    entity_mode: str = ""

class AIRecommendSkillRequest(BaseModel):
    agent_id: str
    agent_name_ko: str
    role_description: str

def _assert_agent_config_readable(p: Principal):
    """구성 조회 자격. 에이전트 구성은 사내 운영 정보다 — 익명·미등록에게 주지 않는다.

    ★ [병합 2026-08-05] 이 헬퍼는 브랜치에만 있었다. 충돌을 dev 쪽으로 해결하면서
      함께 사라졌고, 그 결과 `POST /ai-recommend/pipeline` 이 무방비로 돌아갔다.
      그 라우트는 **LLM 을 호출한다** — 자료를 훔치지 않아도 예산을 태울 수 있다."""
    from api.deps import visibility_block_reason
    reason = visibility_block_reason(p)
    if reason:
        raise HTTPException(status_code=403, detail=reason)


@router.post("/ai-recommend/pipeline")
async def ai_recommend_pipeline(req: AIRecommendPipelineRequest, p: Principal = Depends(current_principal)):
    _assert_agent_config_readable(p)
    from core.llm_gateway import gateway

    # ── [D-017 §9 P2-3] 이 조직이 실제로 쓸 수 있는 것을 설계 입력에 넣는다 ──────────
    #
    # ★ 종전에는 `req.user_request` 문장 하나만 넘겼다. 그래서 추천 파이프라인이 **존재하지
    #   않는 데이터와 접근할 수 없는 도구**를 전제로 설계됐고, 그 결과는 둘 중 하나였다 —
    #   실행 단계에서 권한 교집합(P3-3)에 걸려 죽거나, 통제 없는 경로로 흘러 권한 밖 자원을
    #   실제로 건드리거나. 통제를 «사후 거부» 에서 «사전 안내» 로 옮긴다.
    #
    # ⚠️ 범위를 여기서 판정하지 않는다. 수집기가 각 저장소의 `visible_*`/`list_*` 를 그대로
    #   쓰고, 그것들은 이미 `filter_visible` 단일 지점을 지난다.
    from core.agent_design_context import collect as _collect_design_ctx, to_prompt as _ctx_prompt
    from core.enterprise_context.classification import clearance_of_scope
    from core.enterprise_context.scoping import may_drill_down
    _scope_id = (req.scope_node_id or "").strip() or getattr(p.scope, "primary_dept_id", "") or ""
    _ctx = await asyncio.to_thread(
        _collect_design_ctx, _scope_id, (req.tenant_id or "").strip(),
        (req.entity_mode or "").strip() or "REAL",
        clearance_of_scope(p.scope), may_drill_down(p.scope), _scope_id)
    _ctx_block = _ctx_prompt(_ctx)

    # 시뮬레이션 성격 판별 키워드
    sim_keywords = ["시뮬레이션", "시뮬레이터", "simulation", "simulator", "what-if", "시나리오", "scenario"]
    is_simulation = any(kw in req.user_request.lower() for kw in sim_keywords)
    
    if is_simulation:
        # 시뮬레이션 프레임워크: 실행 단계만 AI에게 생성 요청
        prompt = f"""
사용자가 시뮬레이션 파이프라인을 요청했습니다.
시뮬레이션 워크플로우의 "실행 단계(Execution Phase)" 에이전트만 설계해 주세요.
준비 단계(PM, 설계사, 수집기, 검증기)와 평가 단계(분석, 평가, 총괄, 인사이트, 비교)는 시스템이 자동으로 삽입합니다.
당신은 가치사슬이나 업무 프로세스의 핵심 실행 에이전트만 설계하면 됩니다.

사용자 요청: {req.user_request}

출력 형식: 반드시 아래 JSON 스키마를 따를 것 (실행 단계 에이전트만 포함):
{{
    "execution_agents": [
        {{
            "id": "영문_ID_형식",
            "name_ko": "한글 표시명",
            "role": "역할 상세 설명",
            "skill": "skill_name_without_md",
            "stage": "STAGE_NAME",
            "category": "execution",
            "model_tier": "pro",
            "enabled": true,
            "hotl_after": false,
            "debate": false,
            "llm": true
        }}
    ],
    "pipeline_name": "...",
    "description": "..."
}}

실행 에이전트는 3~8개 범위로, 해당 도메인의 핵심 업무 흐름에 맞게 설계하십시오.
"""  # noqa: E501 — [P2-3] 문맥 블록은 아래 `aexecute` 직전에 **한 곳에서** 붙인다
    else:
        # 일반 워크플로우: 전체 파이프라인 생성 (기존 로직)
        prompt = f"""
    사용자가 원하는 에이전트 기능을 바탕으로 전체 파이프라인(에이전트 목록 및 연결 관계)을 설계해 줘.
    요청: {req.user_request}
    
    출력 형식: 반드시 아래 JSON 스키마를 따를 것.
    {{
        "pipeline_name": "...",
        "description": "...",
        "agents": [
            {{
                "id": "영문_ID_형식",
                "name_ko": "한글 표시명",
                "role": "역할 상세 설명",
                "skill": "skill_name_without_md",
                "stage": "STAGE_NAME",
                "category": "planning|execution|review|system 중에 하나 선택",
                "model_tier": "pro",
                "order": 1,
                "enabled": true,
                "hotl_after": false,
                "debate": false,
                "llm": true,
                "is_start": true/false,
                "is_end": true/false
            }}
        ],
        "edges": [
            {{
                "id": "e-source_agent_id-target_agent_id",
                "source": "source_agent_id",
                "target": "target_agent_id",
                "animated": true,
                "style": {{"stroke": "#4b5563", "strokeWidth": 2}}
            }}
        ]
    }}
    """
    llm = gateway  # 요청마다 신규 생성 금지(동기 models.list 네트워크 콜) - 싱글턴 재사용
    # ★ [P2-3] 문맥 블록을 **한 곳에서** 붙인다. 위 두 분기(시뮬레이션/일반)에 각각 끼워 넣으면
    #   한쪽만 고쳐지는 날이 온다 — 이 저장소가 반복해서 확인한 유형이다.
    #   ⚠️ 프롬프트 **앞**에 놓는다. 뒤에 놓으면 긴 JSON 스키마 뒤에 묻혀 모델이 덜 본다.
    res = await llm.aexecute({}, (_ctx_block + prompt) if _ctx_block else prompt,
                             output_mode="json", light=True)
    try:
        import re
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', res, re.DOTALL)
        if match:
            res = match.group(1)
        data = json.loads(res)
        
        if is_simulation:
            # 시뮬레이션 프레임워크 셸 자동 조립
            data = _assemble_simulation_framework(data)
        
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파이프라인 생성 실패: {str(e)}\n\n(LLM 응답: {res[:100]}...)")


def _assemble_simulation_framework(ai_data: dict) -> dict:
    """AI가 생성한 실행 단계 에이전트를 고정 프레임워크 셸에 조립합니다."""
    
    # 고정 프레임워크: 준비 단계 (order 1~4)
    prep_agents = [
        {"id": "Sim_PM", "name_ko": "시뮬레이션 총괄 PM", "role": "시나리오 프레임워크 수립 및 전체 시뮬레이션 총괄 관리", "skill": "sim_pm", "stage": "SIM_PLANNING", "category": "planning", "model_tier": "pro", "order": 1, "enabled": True, "hotl_after": True, "debate": False, "llm": True, "is_framework": True},
        {"id": "Sim_Designer", "name_ko": "시뮬레이션 변수 설계사", "role": "시뮬레이션에 필요한 인풋 변수 목록 정의", "skill": "sim_designer", "stage": "SIM_DESIGN", "category": "planning", "model_tier": "pro", "order": 2, "enabled": True, "hotl_after": True, "debate": False, "llm": True, "is_framework": True},
        {"id": "Sim_InputCollector", "name_ko": "인풋 수집기", "role": "사용자에게 변수 값 입력 요청", "skill": "sim_input_collector", "stage": "SIM_INPUT", "category": "planning", "model_tier": "flash", "order": 3, "enabled": True, "hotl_after": True, "debate": False, "llm": True, "is_framework": True},
        {"id": "Sim_Validator", "name_ko": "정합성 검증기", "role": "입력된 인자 값의 논리적 정합성 점검", "skill": "sim_validator", "stage": "SIM_VALIDATION", "category": "planning", "model_tier": "pro", "order": 4, "enabled": True, "hotl_after": False, "debate": False, "llm": True, "is_framework": True},
    ]
    
    # AI가 생성한 실행 단계 에이전트 (order 5~)
    exec_agents = ai_data.get("execution_agents", ai_data.get("agents", []))
    for i, agent in enumerate(exec_agents):
        agent["order"] = 5 + i
        agent["is_framework"] = False
    
    exec_end_order = 5 + len(exec_agents)
    
    # 고정 프레임워크: 평가 단계
    eval_agents = [
        {"id": "Analysis_Agent", "name_ko": "분석/개선 에이전트", "role": "가치사슬 병목 분석 및 효율화 포인트 발굴", "skill": "sim_analysis", "stage": "ANALYSIS", "category": "review", "model_tier": "pro", "order": exec_end_order, "enabled": True, "hotl_after": False, "debate": False, "llm": True, "is_framework": True},
        {"id": "Sim_Evaluator", "name_ko": "시뮬레이션 평가사", "role": "시뮬레이션 결과의 정합성, 현실성 평가 및 리스크 스코어링", "skill": "sim_evaluator", "stage": "SIM_EVALUATION", "category": "review", "model_tier": "pro", "order": exec_end_order + 1, "enabled": True, "hotl_after": False, "debate": False, "llm": True, "is_framework": True},
        {"id": "Supervisor_Agent", "name_ko": "경영관리 총괄(슈퍼바이저)", "role": "C레벨 의사결정용 요약 보고서 도출", "skill": "sim_supervisor", "stage": "SUPERVISOR", "category": "review", "model_tier": "pro", "order": exec_end_order + 2, "enabled": True, "hotl_after": True, "debate": False, "llm": True, "is_framework": True},
        {"id": "Sim_Insight", "name_ko": "인사이트 추천 에이전트", "role": "인자 변경 추천, 신규 관리 인자 제안, 민감도 분석", "skill": "sim_insight", "stage": "SIM_INSIGHT", "category": "review", "model_tier": "pro", "order": exec_end_order + 3, "enabled": True, "hotl_after": True, "debate": False, "llm": True, "is_framework": True},
        {"id": "Sim_Comparator", "name_ko": "시나리오 비교 리포터", "role": "2사이클 이상 결과 비교 분석 및 최적 시나리오 추천", "skill": "sim_comparator", "stage": "SIM_COMPARISON", "category": "review", "model_tier": "pro", "order": exec_end_order + 4, "enabled": True, "hotl_after": True, "debate": False, "llm": True, "is_framework": True},
    ]
    
    all_agents = prep_agents + exec_agents + eval_agents
    
    # 엣지 생성 (선형 연결)
    edges = []
    for i in range(len(all_agents) - 1):
        edges.append({
            "id": f"e-{all_agents[i]['id']}-{all_agents[i+1]['id']}",
            "source": all_agents[i]["id"],
            "target": all_agents[i+1]["id"],
            "animated": True,
            "style": {"stroke": "#4b5563", "strokeWidth": 2}
        })
    
    return {
        "pipeline_name": ai_data.get("pipeline_name", "시뮬레이션 파이프라인"),
        "description": ai_data.get("description", ""),
        "deliverable_type": "hybrid_simulation",
        "simulation_framework": True,
        "framework_agents": {
            "preparation": [a["id"] for a in prep_agents],
            "evaluation": [a["id"] for a in eval_agents],
            "resim_entry": "Sim_Validator"
        },
        "agents": all_agents,
        "edges": edges
    }

@router.post("/ai-recommend/skill")
async def ai_recommend_skill(req: AIRecommendSkillRequest,
                             p: Principal = Depends(current_principal)):
    """스킬 문서 초안 생성.

    ⚠️⚠️ [D-017 §2.3] 예전 결함 세 가지를 여기서 막는다:
      ① 권한 검사 없이 공용 `skills/` 에 직접 썼다 → `skill.propose` 를 요구한다.
      ② `agent_id` 를 파일명에 그대로 썼다(정규식 검증 없음) → 경로 구성에 개입할 수 있었다.
      ③ **기존 공용 스킬을 덮어썼다** → 이제 덮어쓰지 않는다. 초안은 `skills/_proposals/`
         아래에 요청자 이름을 붙여 쓰고, 공용 반영은 `skill.approve` 를 가진 사용자가 한다.
    ★ 초안·검토·승인·버전 전체 절차는 설계 §9 P1 이다. P0 에서는 **덮어쓰기를 막는 것**까지."""
    _require_caps(p, SKILL_PROPOSE, resource="skill", action=f"propose:{req.agent_id}")
    if not _SAFE_AGENT_ID.match(str(req.agent_id or "")):
        raise HTTPException(
            status_code=422,
            detail=("에이전트 ID 는 영문·숫자·_·- 만 쓸 수 있습니다(64자 이내) — "
                    "이 값이 파일 경로가 되므로 다른 문자는 허용하지 않습니다."))
    from core.llm_gateway import gateway
    prompt = f"""
    사용자가 지정한 에이전트의 간략한 역할을 바탕으로, 이 에이전트가 어떤 입력을 받아 어떤 산출물을 내고, 누구에게 전달해야 하는지를 명시하는 상세 마크다운 스킬 문서를 작성해 줘.
    - 에이전트 ID: {req.agent_id}
    - 에이전트 명: {req.agent_name_ko}
    - 사용자 입력 간략 역할: {req.role_description}
    
    [출력 요구사항]
    1. 이 에이전트의 구체적 역할과 책임을 상세히 작성할 것 (role 업데이트용으로 사용됨).
    2. 그에 맞는 스킬 마크다운 문서 내용을 작성할 것.
    
    출력 형식: 반드시 아래 JSON 형식으로 반환해 줘.
    {{
        "role_expanded": "에이전트 역할에 대한 2~3줄 상세 설명",
        "skill_markdown": "작성된 스킬 마크다운 내용 전체 (문자열)"
    }}
    """
    llm = gateway  # 요청마다 신규 생성 금지(동기 models.list 네트워크 콜) - 싱글턴 재사용
    res = await llm.aexecute({}, prompt, output_mode="json", light=True)
    try:
        import re
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', res, re.DOTALL)
        if match:
            res = match.group(1)
        data = json.loads(res)
        skill_id = f"{req.agent_id.lower()}_skill"
        # ★★ 공용 스킬을 **덮어쓰지 않는다.** 검토를 거치지 않은 LLM 출력이 전 프로젝트가
        #   쓰는 공용 스킬을 조용히 바꾸면 안 된다 — 초안은 제안 디렉터리에 둔다.
        proposals = os.path.join("skills", "_proposals")
        os.makedirs(proposals, exist_ok=True)
        actor = re.sub(r"[^A-Za-z0-9_.-]", "_", (p.user_id or "anonymous"))[:64]
        draft_path = os.path.join(proposals, f"{skill_id}__{actor}.md")
        with open(draft_path, "w", encoding="utf-8") as f:
            f.write(data["skill_markdown"])
        already = os.path.exists(os.path.join("skills", f"{skill_id}.md"))
        _audit_registry("SKILL_DRAFT_CREATED", p, f"스킬 초안 생성 {skill_id}",
                        f"draft={draft_path} · 공용 존재={already}")
            
        return {
            "status": "success", "role": data["role_expanded"], "skill": skill_id,
            "draft_path": draft_path.replace("\\", "/"),
            # 화면이 «공용에 저장됐다» 고 오해하지 않도록 서버가 직접 말한다.
            "published": False,
            "note": (f"초안을 만들었습니다. 공용 스킬 «{skill_id}» 는 "
                     + ("이미 있으며 덮어쓰지 않았습니다." if already else "아직 없습니다.")
                     + " 공용 반영은 스킬 승인 권한을 가진 사용자가 합니다."),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"스킬 생성 실패: {str(e)}\n\n(LLM 응답: {res[:100]}...)")


# ==========================================
# 다중 워크플로우 템플릿 (Copy 모델) — 기존(default) 보존 + 복사로 새 워크플로우 생성/편집
# ==========================================
class TemplateCopyRequest(BaseModel):
    src_id: str = "default"
    new_id: str
    new_name: Optional[str] = ""


@router.get("/templates")
async def list_workflow_templates(p: Principal = Depends(current_principal)):
    """공존하는 워크플로우 템플릿 목록(항상 default 포함).

    [P1-5] 파일 템플릿 + **가시 범위 안의 승인된 조직 워크플로우**를 함께 준다(설계 §7.1
    «기존 GET 목록은 사용자 가시 범위만 반환한다»). 응답 키는 종전과 같고 `source`·`status`·
    `owner_scope_id` 가 추가된다 — 기존 화면은 모르는 키를 무시한다.

    ⚠️ 승인되지 않은 조직 자산은 넣지 않는다. 기존 화면은 `status` 를 모르므로 «목록에 있으면
      쓸 수 있다» 고 판단하고, 초안으로 프로젝트를 만들려 한다."""
    _require_caps(p, WORKFLOW_READ, resource="workflow_template", action="list")
    from core.agent_asset_adapter import workflow_summaries
    from api.deps import viewer_visible_scopes
    return {"status": "success",
            "data": workflow_summaries(viewer_visible_scopes(p), p.user_id or "")}


@router.get("/templates/{template_id}")
async def get_workflow_template(template_id: str,
                                p: Principal = Depends(current_principal)):
    """[P1-5] 파일 템플릿과 조직 워크플로우(`as_…`)를 같은 경로로 준다.

    ⚠️ 조직 자산은 **가시 범위 밖이면 404** 다(설계 §7.1) — 403 은 «그 조직에 그런 워크플로우가
      있다» 를 알려 준다. 판정은 새 API 와 **같은 함수**(`adapter.asset_visible`)를 쓴다."""
    _require_caps(p, WORKFLOW_READ, resource="workflow_template", action=template_id)
    from core.agent_registry import load_template, _safe_tid
    # ⚠️ 저장소를 직접 import 하지 않고 **어댑터를 경유**한다 — 어댑터가 저장소 참조를 들고
    #   있어야 조회와 판정이 한 곳에 남는다(그러지 않으면 테스트가 갈아끼운 저장소를 이 경로만
    #   비껴가고, 나중에 저장소를 바꿀 때도 이 줄이 빠진다).
    from core.agent_asset_adapter import asset_visible, get_any, is_db_asset_id
    from core.agent_assets import AssetNotFound
    from api.deps import viewer_visible_scopes
    try:
        _safe_tid(template_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if is_db_asset_id(template_id):
        try:
            a = get_any(template_id)
        except AssetNotFound:
            raise HTTPException(status_code=404, detail="요청한 워크플로우를 찾을 수 없습니다.")
        if not asset_visible(a, viewer_visible_scopes(p), p.user_id or ""):
            raise HTTPException(status_code=404, detail="요청한 워크플로우를 찾을 수 없습니다.")
        # ★ `status` 를 함께 준다. 이것 없이 body 만 주면 화면은 초안을 실행 가능한 것으로 본다.
        return {"status": "success", "data": a.get("body") or {},
                "asset_status": a.get("status"), "runnable": a.get("runnable"),
                "owner_scope_id": a.get("owner_scope_id") or ""}
    return {"status": "success", "data": load_template(template_id)}


@router.post("/templates/copy")
async def copy_workflow_template(req: TemplateCopyRequest,
                                 p: Principal = Depends(current_principal)):
    """기존 템플릿을 복사해 새 워크플로우 생성(기존은 불변 — Copy 모델)."""
    _require_caps(p, WORKFLOW_CREATE, resource="workflow_template", action="copy")
    from core.agent_registry import copy_template
    try:
        tpl = copy_template(req.src_id, req.new_id, req.new_name or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _audit_registry("WORKFLOW_TEMPLATE_COPIED", p, f"템플릿 복사 {req.src_id} → {req.new_id}", "")
    return {"status": "success", "template_id": req.new_id, "data": tpl}


@router.put("/templates/{template_id}")
async def update_workflow_template(template_id: str, payload: AgentRegistryPayload,
                                   p: Principal = Depends(current_principal)):
    """★ `default` 는 **시스템 기본 정의**다. 설계 §4.2 «복사·버전 승격만 가능» 에 따라
      직접 수정은 플랫폼 관리자만 할 수 있다 — 나머지는 복사해서 쓴다."""
    if str(template_id) == "default":
        _require_caps(p, SYSTEM_DEFAULT_EDIT, WORKFLOW_UPDATE,
                      resource="workflow_template", action="update:default")
    else:
        _require_caps(p, WORKFLOW_UPDATE, resource="workflow_template",
                      action=f"update:{template_id}")
    from core.agent_registry import save_template, _safe_tid
    try:
        _safe_tid(template_id)
        saved = save_template(template_id, payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"템플릿 저장 오류: {str(e)}")
    _audit_registry("WORKFLOW_TEMPLATE_UPDATED", p, f"템플릿 저장 {template_id}", "")
    return {"status": "success", "data": saved}


@router.delete("/templates/{template_id}")
async def delete_workflow_template(template_id: str,
                                   p: Principal = Depends(current_principal)):
    """⚠️ 삭제는 되돌릴 수 없다 — `workflow.retire` 를 요구한다."""
    if str(template_id) == "default":
        # 시스템 기본 워크플로우는 지우지 않는다. 지우면 신규 프로젝트가 만들어지지 않는다.
        raise HTTPException(status_code=400,
                            detail="기본 워크플로우(default)는 삭제할 수 없습니다 — 복사본을 쓰십시오.")
    _require_caps(p, WORKFLOW_RETIRE, resource="workflow_template",
                  action=f"delete:{template_id}")
    from core.agent_registry import delete_template, _safe_tid
    try:
        _safe_tid(template_id)
        delete_template(template_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _audit_registry("WORKFLOW_TEMPLATE_DELETED", p, f"템플릿 삭제 {template_id}",
                    "되돌릴 수 없음")
    return {"status": "success"}