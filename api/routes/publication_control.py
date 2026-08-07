"""[CL-3] 대내외 보고 발간 API — 작업서 §CL-BE-04.

오류 코드 규약은 CL-1·CL-2 와 같다(§3-10):
  · 식별 안 됨 → **401**
  · 형식 오류 → **422**
  · 없거나 볼 수 없음 → **404** (403 은 존재를 알린다)
  · 내 것의 정책 위반(게이트 미통과·상태) → **400**

★★ **대외 발간 차단은 화면이 아니라 여기서 일어난다.** 버튼만 비활성화하면 URL 을 아는 사람은
  그대로 게시할 수 있다. `publish` 는 `EXECUTIVE`·`LEGAL_DISCLOSURE` 가 둘 다 승인되지 않으면
  400 으로 거절한다(작업서 §9 "EXTERNAL 은 두 필수 검토 전 발간 API 와 버튼이 모두 차단된다").
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from api.deps import Principal, current_principal
from core.publication import (UNRESTRICTED, PublicationError, PublicationNotFound,
                              publication)

router = APIRouter(tags=["Publication"])


def _actor(p: Principal) -> str:
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("사용자 식별이 필요합니다 — 발간은 '누가 무엇을 대외로 내보냈는가'가 기록의 "
                    "전부입니다. 우측 상단에서 사용자를 지정하십시오."))
    return uid


def _scopes(p: Principal):
    """이 요청자가 볼 수 있는 조직 범위. **모든 라우트가 이것을 서비스에 넘긴다.**

    ★★★ [2026-08-08 실측 결함] 종전에는 아무 라우트도 범위를 넘기지 않았고 서비스에도
      판정이 없었다. 그래서 **아무 상관 없는 식별 사용자가 남의 대외 발간물을 조회·승인하고
      외부로 내보낼 수 있었다.** 기존 테스트 30여 건은 절차 게이트만 봤기 때문에 드러나지 않았다.

    ⚠️ 무제한 주체는 `UNRESTRICTED` 센티넬로 넘긴다 — 빈 집합(`frozenset()`)으로 넘기면
      «범위가 하나도 없는 사람» 이 되어 관리자가 자기 것 말고는 아무것도 못 본다.
    ⚠️ `None` 을 넘기지 않는다. `None` 은 서비스에서 «범위를 넘기지 않았다»(레거시)로 읽혀
      판정이 통째로 꺼진다 — 라우트가 그것을 쓰면 이 수정이 무의미해진다."""
    sc = getattr(p, "scope", None)
    if sc is None or getattr(sc, "unrestricted", False):
        return UNRESTRICTED
    # 부서 id 와 ECM 노드를 함께 본다 — 발간물의 `scope_id` 가 둘 중 어느 표기로도 저장된다
    # (D-005 입력 호환 계약). 한쪽만 보면 그 표기로 저장된 발간물이 관계자에게도 안 보인다.
    return frozenset(set(getattr(sc, "readable_dept_ids", None) or ())
                     | set(getattr(sc, "readable_scope_nodes", None) or ()))


def _hidden():
    raise HTTPException(status_code=404, detail="발간물을 찾을 수 없습니다.")


def _bad(e: Exception):
    raise HTTPException(status_code=400, detail=str(e))


class PubCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    source_type: str
    source_id: str
    audience: str = "INTERNAL"
    publication_type: str = "OPERATIONAL"
    security_class: str = "INTERNAL"
    scope_id: str = ""
    embargo_at: str = ""


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_types: List[str] = []


class ApproveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_type: str
    status: str = "APPROVED"
    comment: str = ""


class PublishBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targets: List[Dict[str, str]]


class ReasonBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str


@router.post("/api/v1/publications")
async def create_publication(req: PubCreate, p: Principal = Depends(current_principal)):
    """승인 Snapshot 에서 발간 초안을 만든다. **원천 없이는 만들 수 없다.**"""
    actor = _actor(p)
    # ★★ [2026-08-08] 생성은 조회가 아니라 **새로 만드는 것**이라 `_scopes()` 를 넘기지 않는다.
    #   대신 «내가 속하지 않은 조직 이름으로 만들 수 없다» 를 여기서 막는다 — 종전에는
    #   `req.scope_id` 를 검증 없이 받아서, 남의 부서 이름을 달아 발간물을 만들 수 있었다.
    #   그렇게 만든 문서는 **그 부서 사람들에게 보이고** 작성자도 계속 볼 수 있다.
    # ⚠️ 400 이다(404 가 아니다). 값을 사용자가 직접 입력했으므로 존재가 새는 것이 아니고,
    #   무엇이 잘못됐는지 알려주지 않으면 고칠 수가 없다.
    scope_id = (req.scope_id or "").strip() or (p.scope.primary_dept_id or "")
    allowed = _scopes(p)
    if scope_id and allowed is not UNRESTRICTED and scope_id not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(f"'{scope_id}' 는 볼 수 있는 조직이 아닙니다 — 자신이 속한 조직으로만 "
                    f"발간물을 만들 수 있습니다."))
    try:
        data = publication.create(
            title=req.title, created_by=actor, source_type=req.source_type,
            source_id=req.source_id, audience=req.audience,
            publication_type=req.publication_type, security_class=req.security_class,
            scope_id=scope_id, embargo_at=req.embargo_at)
    except PublicationError as e:
        _bad(e)
    return {"status": "success", "data": data}


@router.get("/api/v1/publications")
async def list_publications(audience: str = Query(""), status: str = Query(""),
                            scope_id: str = Query(""),
                            p: Principal = Depends(current_principal)):
    _actor(p)
    return {"status": "success",
            "data": publication.list(scope_id=scope_id, audience=audience, status=status,
                                     viewer_scopes=_scopes(p), user_id=_actor(p))}


@router.get("/api/v1/publications/{publication_id}")
async def get_publication(publication_id: str, p: Principal = Depends(current_principal)):
    try:
        return {"status": "success", "data": publication.get(publication_id, _actor(p), _scopes(p))}
    except PublicationNotFound:
        _hidden()


@router.post("/api/v1/publications/{publication_id}/render")
async def render_publication(publication_id: str, p: Principal = Depends(current_principal)):
    """구조화 문서를 만든다.

    ⚠️ **렌더 실패는 400 이고 상태는 올라가지 않는다.** 성공처럼 200 을 주면 화면은 «발간 준비
      완료»를 띄우고, 사용자는 내용 없는 문서에 승인을 누른다."""
    try:
        return {"status": "success", "data": publication.render(publication_id, _actor(p), viewer_scopes=_scopes(p))}
    except PublicationNotFound:
        _hidden()
    except PublicationError as e:
        _bad(e)


@router.post("/api/v1/publications/{publication_id}/request-approval")
async def request_approval(publication_id: str, req: ApprovalRequest,
                           p: Principal = Depends(current_principal)):
    """검토를 요청한다. EXTERNAL 은 `EXECUTIVE`·`LEGAL_DISCLOSURE` 가 자동으로 포함된다."""
    try:
        return {"status": "success",
                "data": publication.request_approval(publication_id, _actor(p), req.review_types,
                                             viewer_scopes=_scopes(p))}
    except PublicationNotFound:
        _hidden()
    except PublicationError as e:
        _bad(e)


@router.post("/api/v1/publications/{publication_id}/approve")
async def approve_publication(publication_id: str, req: ApproveBody,
                              p: Principal = Depends(current_principal)):
    try:
        return {"status": "success",
                "data": publication.approve(publication_id, _actor(p), req.review_type,
                                            req.status, req.comment,
                                            viewer_scopes=_scopes(p))}
    except PublicationNotFound:
        _hidden()
    except PublicationError as e:
        _bad(e)


@router.post("/api/v1/publications/{publication_id}/publish")
async def publish_publication(publication_id: str, req: PublishBody,
                              p: Principal = Depends(current_principal)):
    """승인 완료 후 배포한다.

    ★★ 대외 발간의 이중 승인은 **여기서** 강제된다. 화면 버튼이 아니라 이 경로가 경계다.
    ⚠️ 게시 어댑터가 연결돼 있지 않으면 배포는 `FAILED` 로 기록되고 상태는 올라가지 않는다 —
      아무 데도 안 나간 문서를 «발간됨»으로 두지 않기 위해서다."""
    try:
        return {"status": "success",
                "data": publication.publish(publication_id, _actor(p), req.targets,
                                    viewer_scopes=_scopes(p))}
    except PublicationNotFound:
        _hidden()
    except PublicationError as e:
        _bad(e)


@router.post("/api/v1/publications/{publication_id}/correct")
async def correct_publication(publication_id: str, req: ReasonBody,
                              p: Principal = Depends(current_principal)):
    """정정판을 만든다. **원본은 덮어쓰지 않는다.**"""
    try:
        return {"status": "success",
                "data": publication.correct(publication_id, _actor(p), req.reason, _scopes(p))}
    except PublicationNotFound:
        _hidden()
    except PublicationError as e:
        _bad(e)


@router.post("/api/v1/publications/{publication_id}/withdraw")
async def withdraw_publication(publication_id: str, req: ReasonBody,
                               p: Principal = Depends(current_principal)):
    """회수한다. **이력은 남는다** — 이미 읽은 사람이 무엇을 읽었는지는 지울 수 없다."""
    try:
        return {"status": "success",
                "data": publication.withdraw(publication_id, _actor(p), req.reason, _scopes(p))}
    except PublicationNotFound:
        _hidden()
    except PublicationError as e:
        _bad(e)
