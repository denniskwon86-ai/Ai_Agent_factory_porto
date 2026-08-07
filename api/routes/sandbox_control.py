"""[M2 §4.3] VIRTUAL Sandbox capability token REST API. prefix `/api/v1/sandbox`.

발급 · 조회 · 회수. **읽기 전용 · 가상 문맥 전용 · 짧은 만료.**

⚠️ 토큰 전문은 **발급 응답에서 단 한 번만** 준다. 목록·감사로그에는 앞 12자만 남는다 —
  로그나 목록에 자격증명 전문이 실리면 그 로그를 읽을 수 있는 사람이 곧 권한자가 된다.
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, current_principal
from core.sandbox_token import DEFAULT_TTL_MINUTES, SandboxTokenError, sandbox_tokens

router = APIRouter(prefix="/api/v1/sandbox")


def _actor(p: Principal) -> str:
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("임시 권한 발급에는 사용자 식별이 필요합니다. X-User-Id 헤더를 포함하거나 "
                    "ORG_ENFORCE 를 켜십시오 — 누구에게 줬는지 모르는 토큰은 추적이 불가능하고, "
                    "추적되지 않는 임시 권한은 뒷문입니다."))
    return uid


class IssueRequest(BaseModel):
    scope_node_id: str                      # 가상 조직 범위
    ttl_minutes: Optional[int] = DEFAULT_TTL_MINUTES
    purpose: Optional[str] = ""
    tenant_id: Optional[str] = "tenant_default"


def _assert_may_sandbox(p: Principal, scope_node_id: str) -> None:
    """가상 조직 범위로 토큰을 발급할 자격이 있는가.

    ★★★ [2026-08-08 트랙 H] 종전에는 **비어 있는지만** 봤다(「범위 없는 토큰은 '전부 허용'이
      되고 그것은 권한 승급입니다」). 그런데 **남의 범위**는 막지 않아서, 식별된 사용자면
      누구나 **어떤 가상 조직으로든** 읽기 토큰을 발급할 수 있었다.

    ★ 판정 기준은 설계가 이미 정해 두었다 — **가상 조직은 실제 조직의 복제본**이고
      `EnterpriseEntity.base_entity_id` 가 원본을 가리킨다(§7.1 「가상 조직 생성 흐름」).
      그러므로 **원본 조직을 볼 수 있는 사람이 그 복제본도 볼 수 있다.**
      가상 노드를 사용자의 `readable_scope_nodes` 에서 찾는 방식은 쓸 수 없다 — 복제본은
      거기 등록되지 않으므로 **E3 기능이 통째로 죽는다.**

    ⚠️ 해석 실패는 **거부**다(fail-closed). 「원본을 못 찾았으니 통과」로 두면 ECM 조회 장애가
      곧 가상 조직 전면 개방이 된다.
    ⚠️ 무제한 주체(조직 미도입·플랫폼 관리자)는 통과 — 하위호환 계약.
    """
    sc = getattr(p, "scope", None)
    if sc is None or getattr(sc, "unrestricted", False):
        return
    allowed = set(getattr(sc, "readable_scope_nodes", None) or ())
    allowed_depts = set(getattr(sc, "readable_dept_ids", None) or ())
    if scope_node_id in allowed:
        return                                   # 실제 조직 노드를 그대로 준 경우
    try:
        from core.enterprise_context.repository import ecm_repository
        node = ecm_repository.get_node(scope_node_id)
        ent = ecm_repository.get_entity(node.entity_id) if node else None
        base_id = getattr(ent, "base_entity_id", "") if ent else ""
        # 복제 원본 엔터티의 노드들 중 하나라도 내 범위 안이면 통과한다.
        # ⚠️ `list_nodes()` 는 `entity_id` 로 거르지 못한다(tenant/status/entity_mode 만) —
        #   전부 받아 여기서 거른다. 원본은 실제 조직이므로 건수가 작다.
        ok = False
        if base_id:
            for n in ecm_repository.list_nodes() or []:
                if n.entity_id != base_id:
                    continue
                if n.node_id in allowed or (n.dept_id and n.dept_id in allowed_depts):
                    ok = True
                    break
    except Exception as e:
        print(f"⚠️ [sandbox] 복제 원본 해석 실패 — 거부로 처리(fail-closed): {e}")
        ok = False
    if not ok:
        # 404 가 아니라 403 이다 — 사용자가 직접 입력한 값이고, 무엇이 잘못됐는지 알려주지
        #   않으면 고칠 수가 없다. 가상 조직의 존재 자체는 비밀이 아니다(트리에서 보인다).
        raise HTTPException(
            status_code=403,
            detail=("이 가상 조직 범위로는 토큰을 발급할 수 없습니다 — 가상 조직은 실제 조직의 "
                    "복제본이며, **복제 원본을 볼 수 있는 사람만** 그 복제본을 열 수 있습니다."))


@router.post("/token")
async def issue_token(req: IssueRequest, p: Principal = Depends(current_principal)):
    """가상 문맥 읽기 토큰을 발급한다.

    ⚠️ 이 토큰은 **REAL 데이터에 대한 권한을 한 조각도 주지 않는다.** 조직 권한을 올리는
      방식이 금지된 이유는, 실험이 끝난 뒤에도 그 권한이 남기 때문이다."""
    actor = _actor(p)
    _assert_may_sandbox(p, (req.scope_node_id or "").strip())
    try:
        out = await asyncio.to_thread(sandbox_tokens.issue, actor, req.scope_node_id,
                                      req.tenant_id or "tenant_default",
                                      req.ttl_minutes or DEFAULT_TTL_MINUTES,
                                      req.purpose or "")
    except SandboxTokenError as e:
        raise HTTPException(status_code=400, detail=str(e))
    out["note"] = ("이 토큰은 가상 문맥(entity_mode=VIRTUAL) **읽기 전용**이며 지정한 가상 조직 "
                   "범위에서만 유효합니다. REAL 데이터는 열리지 않습니다. 토큰 전문은 이 응답에만 "
                   "포함됩니다 — 목록·감사로그에는 앞 12자만 남습니다.")
    return {"status": "success", "data": out}


@router.get("/tokens")
async def active_tokens(mine_only: bool = True, p: Principal = Depends(current_principal)):
    """살아 있는 토큰 목록(전문 미포함).

    ★ "지금 열려 있는 임시 권한이 무엇인가"에 답할 수 없으면 임시 권한을 운영할 수 없다."""
    actor = (p.user_id or "").strip() if mine_only else ""
    return {"status": "success",
            "data": await asyncio.to_thread(sandbox_tokens.active, actor)}


@router.delete("/token/{token}")
async def revoke_token(token: str, p: Principal = Depends(current_principal)):
    """토큰을 즉시 회수한다 — 만료를 기다리지 않고 끊을 수단이 없으면 사고에 대응할 수 없다.

    ★ **소유자 검사를 두지 않는다(의도).** 이것은 bearer 토큰이다 — 문자열을 아는 사람은
      이미 그 토큰을 **쓸 수** 있으므로, 회수만 막는 것은 보호가 아니라 사고 대응만 늦춘다.
      유출된 토큰을 발견한 사람이 즉시 끊을 수 있어야 한다.

    ⚠️ 다만 **식별은 요구한다**(2026-08-08 트랙 H). 종전에는 `p.user_id` 를 그대로 읽어
      익명도 회수할 수 있었고, 그러면 감사에 `actor=unknown` 으로 남는다 —
      「누가 이 토큰을 끊었나」에 답할 수 없는 회수는 사고 조사에서 쓸모가 없다.
      `issue` 가 식별을 요구하는 것과 같은 이유다."""
    ok = await asyncio.to_thread(sandbox_tokens.revoke, token, _actor(p))
    if not ok:
        # 이미 없는 토큰이다. 존재 여부를 알려 주는 것이 문제되지 않는다 — 토큰 문자열을 이미
        #   알고 있는 호출자에게만 답하는 것이고, 없다는 사실이 곧 "회수됨"이다.
        raise HTTPException(status_code=404, detail="유효한 토큰이 아닙니다(이미 만료·회수됨).")
    return {"status": "success", "data": {"revoked": True}}
