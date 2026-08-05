"""[P1-4] 조직별 자산 목록·복사·승인·폐기 API (설계 §7).

## 이 파일의 판정 규칙 — 라우트마다 흩지 않는다

권한 판정은 아래 네 함수에만 있다. 라우트는 그것을 부르고 결과만 쓴다.

  · `_assert_may_read`     — capability 없으면 401/403, 가시 범위 밖이면 **404**
  · `_assert_may_write`    — 개정·복사 대상 판정, 실패는 **403**(사유 포함)
  · `_assert_may_publish`  — 승인. 조직 범위 · 전사 공개를 **따로** 본다
  · `_assert_may_create`   — 만들 수 있는 공개 범위인가

⚠️ 이 판정을 라우트 본문에 펼치면 새 엔드포인트가 하나 늘 때마다 그 경로만 조용히 넓어진다 —
  이 저장소에서 여섯 번 연속 그렇게 새어 나갔다.

## 404 와 403 을 나눈 기준 (설계 §7.1)

- **404** = 목록에 나오지 않는 자산의 상세. 다른 조직 자산의 **존재 자체**를 알리지 않는다.
- **403** = 보이는 자산에 대한 명시적 변경 거부. 여기서 404 를 주면 사용자는 «없어졌나?» 하고
  다시 만들려 하고, 그때 같은 정의가 두 벌이 된다. 무엇이 부족한지 말해야 요청할 수 있다.
- **401** = 식별 없음. `require_caps` 가 이미 구분한다.

## 파일 자산(SYSTEM·LEGACY)

P1-2 어댑터가 노출하는 파일 자산은 **목록·상세·복사만** 된다. 개정·승인·폐기는
`assert_writable_here()` 가 «어디서 바꾸는지» 와 함께 막는다. 복사는 막지 않는다 — 막으면
«제품 기본은 복사해서 쓰십시오» 라는 규칙에 따를 방법이 없어진다.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import Principal, current_principal, require_caps, viewer_visible_scopes
from core import admin_capability as cap
from core import agent_asset_adapter as adapter
from core.agent_assets import (
    KIND_AGENT, KIND_SKILL, KIND_WORKFLOW, RUNNABLE,
    ST_APPROVED, ST_DRAFT, ST_RETIRED, ST_REVIEW,
    VIS_DESCENDANTS, VIS_ENTERPRISE, VIS_PERSONAL, VIS_SCOPE, VIS_SYSTEM,
    AssetError, AssetNotFound, agent_assets,
)
from core.enterprise_context import audit

router = APIRouter(prefix="/api/v1/agent-governance", tags=["agent-governance"])

#: URL 조각 → 자산 종류. 설계 §7 의 경로(`/agents`·`/workflows`·`/skills`)를 그대로 쓴다.
_KIND_BY_PATH = {"agents": KIND_AGENT, "workflows": KIND_WORKFLOW, "skills": KIND_SKILL}

#: 종류별 capability. (읽기, 생성, 수정, 승인, 폐기)
#  ⚠️ 스킬에는 `skill.read` 가 없다(설계 §4.1). 스킬 문서는 에이전트 행동 규칙이므로 읽기는
#    `agent.definition.read` 와 같은 자격으로 둔다 — 새 코드를 지어내면 어느 화면이 그것을
#    확인하지 못해 조용히 막힌다.
_CAPS = {
    KIND_AGENT: (cap.AGENT_READ, cap.AGENT_CREATE, cap.AGENT_UPDATE,
                 cap.AGENT_PUBLISH, cap.AGENT_RETIRE),
    KIND_WORKFLOW: (cap.WORKFLOW_READ, cap.WORKFLOW_CREATE, cap.WORKFLOW_UPDATE,
                    cap.WORKFLOW_PUBLISH, cap.WORKFLOW_RETIRE),
    # 스킬은 제안(propose)과 승인(approve) 둘로만 나뉘어 있다 — 생성·수정이 같은 자격이다.
    KIND_SKILL: (cap.AGENT_READ, cap.SKILL_PROPOSE, cap.SKILL_PROPOSE,
                 cap.SKILL_APPROVE, cap.SKILL_APPROVE),
}


def _kind_of(kind_path: str) -> str:
    k = _KIND_BY_PATH.get(kind_path)
    if not k:
        # 존재하지 않는 종류는 404 다 — «그런 자산 종류가 있는지» 를 알려 줄 필요가 없다.
        raise HTTPException(status_code=404, detail="요청한 자산 종류가 없습니다.")
    return k


def _audit(p: Principal, event: str, asset_id: str, kind: str, outcome: str,
           reason: str = "", detail: str = "") -> None:
    """설계 §7.1 «모든 변경·초기화·승인·바인딩·실행을 감사 로그에 남긴다».
    ⚠️ 감사 실패가 요청 결과를 바꾸지 않는다(`audit.record` 는 예외를 던지지 않는다)."""
    audit.record(event, resource_type=f"agent_asset:{kind}", resource_id=asset_id or "-",
                 actor=p.user_id or "", outcome=outcome, reason=reason, detail=detail)


# ── 판정 (이 파일의 유일한 보안 경계) ──────────────────────────────────────
def _visible_to(p: Principal, asset: Dict[str, Any]) -> bool:
    """이 자산이 요청자에게 보이는가. **목록과 상세가 같은 함수를 쓴다** — 다르면 목록에 없는
    것이 상세로 열리거나(유출) 목록에 있는 것이 404 가 된다(고장).

    ⚠️ 판정 자체는 `adapter.asset_visible` 한 곳에 있다. 기존 API(`factory_control` 의
      `/templates/{id}`)도 같은 함수를 본다 — 두 API 가 각자 판정하면 서서히 갈라진다."""
    return adapter.asset_visible(asset, viewer_visible_scopes(p), p.user_id or "")


def _load_visible(p: Principal, kind: str, asset_id: str) -> Dict[str, Any]:
    """상세 조회의 단일 입구. 없거나 안 보이면 **404**(존재를 알리지 않는다)."""
    try:
        a = adapter.get_any(asset_id)
    except AssetNotFound:
        raise HTTPException(status_code=404, detail="요청한 자산을 찾을 수 없습니다.")
    except AssetError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if a.get("kind") != kind:
        # 종류가 다른 id 로 접근하는 것도 «없음» 이다 — 종류를 바꿔 가며 존재를 탐색하지 못한다.
        raise HTTPException(status_code=404, detail="요청한 자산을 찾을 수 없습니다.")
    if not _visible_to(p, a):
        _audit(p, audit.ACCESS_DENIED_SCOPE_MISMATCH, asset_id, kind, "denied",
               reason="가시 범위 밖", detail="404 로 은폐")
        raise HTTPException(status_code=404, detail="요청한 자산을 찾을 수 없습니다.")
    return a


def _assert_may_read(p: Principal, kind: str):
    return require_caps(p, _CAPS[kind][0], resource=f"agent_asset:{kind}", action="read")


def _scope_label(scope_id: str) -> str:
    """[D-018 ③] 오류 메시지에 쓸 **사람이 읽는 범위 이름.**

    ⚠️ 정본은 `node_41402723bc90` 같은 해시다. 그것을 메시지에 그대로 넣으면 사용자는 **무슨
      조직인지 알 수 없고** 관리자에게 무엇을 요청해야 하는지도 모른다. 백필 후 실제로 그런
      메시지가 나가고 있었다(테스트가 잡았다).
    ★ 이름을 못 찾으면 원본을 보여준다 — 「(미지정)」으로 뭉개면 어느 조직 때문에 막혔는지가
      사라진다."""
    if not (scope_id or "").strip():
        return "(미지정)"
    try:
        from core.enterprise_context.resolver import ecm_resolver
        r = ecm_resolver.resolve_scope_ref(scope_id)
        name, code = r.get("name_ko") or "", r.get("code") or ""
        if name and code:
            return f"{name}({code})"
        return name or code or scope_id
    except Exception:
        return scope_id


def _canonical_owner(owner_scope_id: str) -> str:
    """[D-018 ⑥] **저장할 소유 조직을 정본 `node_id` 로 바꾼다.**

    ⚠️ 해석하지 못하면 **원본을 그대로 둔다.** 빈 값으로 만들면 «소유 미지정» 이 되고, 저장소
      계약상 그 자산은 **아무에게도 보이지 않는다**(«모르니까 보여 준다» 금지) — 만든 사람이
      자기 자산을 잃는다. 해석 실패는 `needs_normalization` 으로 관측되므로 나중에 고칠 수 있다.
    ⚠️ 여기서 거절하지 않는 이유: D-005 입력 호환 계약이 코드·부서 id 를 계속 받기로 했고,
      거절하면 이행이 끝나기 전에 화면이 멈춘다. 정규화는 «받아서 정본으로 저장» 이다."""
    if not (owner_scope_id or "").strip():
        return ""
    try:
        from core.enterprise_context.scoping import resolve_scope_ref
        return resolve_scope_ref(owner_scope_id) or owner_scope_id
    except Exception:
        return owner_scope_id


def _assert_may_create(p: Principal, kind: str, visibility: str, owner_scope_id: str):
    """만들 수 있는 공개 범위인가.

    ★ 전사 공개를 **생성 시점에** 막는다. 승인만 막으면 부서 member 가 만든 초안이 전사 자산
      목록에 «전사» 로 올라앉는다 — 실행은 안 되지만 목록은 그것을 전사 자산으로 보여 준다.
    ★ `can_manage_scope` 는 별칭·정본을 양쪽으로 맞춰 비교한다(백필 이행기) — 여기서 다시
      정규화하지 않는다. 저장할 값의 정규화는 `_canonical_owner` 가 담당한다."""
    c = require_caps(p, _CAPS[kind][1], resource=f"agent_asset:{kind}", action="create")
    if visibility == VIS_SYSTEM:
        raise HTTPException(
            status_code=403,
            detail="제품 기본(SYSTEM) 자산은 만들 수 없습니다 — 복사해서 쓰십시오.")
    if visibility == VIS_ENTERPRISE and not c.can_publish_enterprise():
        raise HTTPException(
            status_code=403,
            detail="전사 공개 자산은 AI 거버넌스 관리자만 만들 수 있습니다 — "
                   "조직 자산으로 만든 뒤 전사 승격을 요청하십시오.")
    if visibility in (VIS_SCOPE, VIS_DESCENDANTS) and not c.can_manage_scope(owner_scope_id):
        raise HTTPException(
            status_code=403,
            detail=f"'{_scope_label(owner_scope_id)}' 조직의 자산을 만들 권한이 없습니다 — "
                   f"관리 범위 밖입니다.")
    return c


def _assert_may_write(p: Principal, kind: str, asset: Dict[str, Any], verb: str):
    """개정. **보이는 자산에 대한 거부는 403** 이고 사유를 말한다."""
    c = require_caps(p, _CAPS[kind][2], resource=f"agent_asset:{kind}", action=verb)
    # 파일 자산은 여기서 바꾸는 것이 아니다 — 어디서 바꾸는지와 함께 막는다.
    if adapter.is_file_asset(asset["asset_id"]):
        adapter.assert_writable_here(asset["asset_id"])         # AssetError → 아래에서 403
    if asset["visibility"] == VIS_PERSONAL:
        if (asset.get("created_by") or "") != (p.user_id or ""):
            raise HTTPException(status_code=403, detail="다른 사람의 개인 자산은 수정할 수 없습니다.")
        return c
    if asset["visibility"] == VIS_ENTERPRISE and not c.can_publish_enterprise():
        raise HTTPException(status_code=403,
                            detail="전사 자산은 AI 거버넌스 관리자만 수정할 수 있습니다.")
    if asset["visibility"] in (VIS_SCOPE, VIS_DESCENDANTS):
        if not c.can_manage_scope(asset.get("owner_scope_id") or ""):
            # ★ 작성자 본인은 자기 초안을 계속 고칠 수 있어야 한다 — 그러지 않으면 관리자가
            #   아닌 사람은 자기가 만든 것을 한 번 저장한 뒤 고칠 수 없다.
            if (asset.get("created_by") or "") != (p.user_id or ""):
                raise HTTPException(
                    status_code=403,
                    detail=f"'{_scope_label(asset.get('owner_scope_id') or '')}' 조직 자산을 "
                           f"수정할 권한이 없습니다 — 관리 범위 밖입니다.")
    return c


def _assert_may_publish(p: Principal, kind: str, asset: Dict[str, Any], verb: str):
    """승인·폐기. 조직 범위와 전사 공개를 **따로** 본다(설계 §4.2)."""
    idx = 3 if verb == "approve" else 4
    c = require_caps(p, _CAPS[kind][idx], resource=f"agent_asset:{kind}", action=verb)
    if adapter.is_file_asset(asset["asset_id"]):
        adapter.assert_writable_here(asset["asset_id"])
    if asset["visibility"] == VIS_ENTERPRISE and not c.can_publish_enterprise():
        raise HTTPException(
            status_code=403,
            detail="전사 공개 자산의 승인·폐기는 AI 거버넌스 관리자 권한입니다 — "
                   "부서 단위에서는 승격을 요청할 수 있습니다.")
    if asset["visibility"] in (VIS_SCOPE, VIS_DESCENDANTS) and \
            not c.can_manage_scope(asset.get("owner_scope_id") or ""):
        raise HTTPException(
            status_code=403,
            detail=f"'{_scope_label(asset.get('owner_scope_id') or '')}' 조직 자산을 "
                   f"승인·폐기할 권한이 없습니다 — 관리 범위 밖입니다.")
    if asset["visibility"] == VIS_PERSONAL and (asset.get("created_by") or "") != (p.user_id or ""):
        raise HTTPException(status_code=403, detail="다른 사람의 개인 자산은 다룰 수 없습니다.")
    return c


# ── 응답 모양 ─────────────────────────────────────────────────────────────
def _slim(a: Dict[str, Any]) -> Dict[str, Any]:
    """목록용. **본문(`body`)과 버전 이력을 뺀다** — 스킬 31개 전문이 목록에 실리면 응답이
    수십 KB 가 되고, 화면은 목록에서 본문을 쓰지 않는다.

    ⚠️⚠️ `agent_assets.list_assets` 가 돌려주는 행에는 `body`·`versions`·`runnable` 이
      **없다**(그 셋은 `get()` 이 붙인다). 그래서 `len(a.get("versions"))` 로 세면
      `version_count` 가 **항상 0** 이 되고, `a.get("runnable")` 은 항상 `None` 이 된다 —
      화면은 그것을 «버전 1개, 실행 불가» 로 읽는다. 행이 실제로 들고 있는 값
      (`current_version`·`status`)에서 계산한다. 파일 자산은 `get()` 과 같은 모양이므로
      `versions` 가 있고, 그때는 그 길이를 쓴다."""
    out = {k: v for k, v in a.items() if k not in ("body", "versions")}
    out["version_count"] = (len(a["versions"]) if "versions" in a
                            else int(a.get("current_version") or 0))
    out["runnable"] = (bool(a["runnable"]) if "runnable" in a
                       else a.get("status") in RUNNABLE)
    return out


class AssetCreate(BaseModel):
    name_ko: str = Field(..., min_length=1)
    body: Dict[str, Any] = Field(default_factory=dict)
    purpose: str = ""
    visibility: str = VIS_PERSONAL
    owner_scope_id: str = ""


class AssetRevise(BaseModel):
    body: Dict[str, Any] = Field(default_factory=dict)


class AssetCopy(BaseModel):
    """복사 대상. 이름을 비우면 원본 이름에 «사본» 을 붙인다."""
    name_ko: str = ""
    visibility: str = VIS_PERSONAL
    owner_scope_id: str = ""


# ── 권한 조회 ─────────────────────────────────────────────────────────────
@router.get("/capabilities")
async def get_capabilities(p: Principal = Depends(current_principal)):
    """현재 사용자의 에이전트 관련 권한과 **그 이유**(설계 §7).

    ★ 권한이 없다는 사실만 주면 화면은 «회색 버튼» 밖에 만들 수 없다. `bootstrap` 을 함께
      주는 이유도 같다 — «권한이 있어서» 와 «아직 아무도 없어서» 는 사용자가 할 일이 다르다."""
    from api.deps import capabilities_of
    c = capabilities_of(p)
    d = c.to_dict()
    d["can_publish_enterprise"] = c.can_publish_enterprise()
    #: 종류별로 실제 가능한 행동. 화면이 이것만 보고 버튼을 정할 수 있어야 한다.
    d["asset_actions"] = {
        path: {
            "read": c.has(_CAPS[k][0]),
            "create": c.has(_CAPS[k][1]),
            "update": c.has(_CAPS[k][2]),
            "approve": c.has(_CAPS[k][3]),
            "retire": c.has(_CAPS[k][4]),
        } for path, k in _KIND_BY_PATH.items()
    }
    #: 승인 이력 없이 돌고 있는 파일 자산 수(P1-2). 관리자만 본다 — 일반 사용자에게는
    #  이관 부채가 «내가 할 수 있는 일» 이 아니다.
    if c.any_admin or c.is_ai_admin or c.is_platform_admin or c.bootstrap:
        try:
            d["file_asset_migration"] = adapter.migration_report()
        except Exception as e:                                       # pragma: no cover
            # 조회 실패를 «0 건» 으로 돌려주지 않는다 — 그러면 이관이 끝난 것처럼 보인다.
            d["file_asset_migration"] = {"complete": False, "error": str(e)}
    return d


# ── 목록·상세 ─────────────────────────────────────────────────────────────
@router.get("/{kind_path}")
async def list_assets(kind_path: str,
                      status: str = Query("", description="DRAFT·REVIEW·APPROVED·RETIRED"),
                      include_files: bool = Query(True, description="파일 자산 포함"),
                      include_retired: bool = Query(False),
                      p: Principal = Depends(current_principal)):
    """가시 범위 안의 자산 목록.

    ⚠️ `viewer_visible_scopes(p)` 를 그대로 넘긴다. 여기서 «모르면 전부» 로 바꾸지 않는다 —
      `frozenset()`(아무 조직도 모른다)은 저장소가 **개인·전사·시스템만** 보이게 처리한다."""
    kind = _kind_of(kind_path)
    _assert_may_read(p, kind)
    rows = adapter.list_all(kind, viewer_visible_scopes(p), p.user_id or "",
                            include_files=include_files, include_retired=include_retired)
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return {
        "kind": kind,
        "items": [_slim(r) for r in rows],
        "total": len(rows),
        #: ★ 목록이 «전부» 인지 «범위 안» 인지 화면이 알아야 한다. 이 표시가 없으면 사용자는
        #  자기가 보는 목록이 전사 전체라고 오해한다.
        "scoped": viewer_visible_scopes(p) is not None,
    }


@router.get("/{kind_path}/{asset_id}")
async def get_asset(kind_path: str, asset_id: str, version_no: int = Query(0),
                    p: Principal = Depends(current_principal)):
    kind = _kind_of(kind_path)
    _assert_may_read(p, kind)
    a = _load_visible(p, kind, asset_id)
    if version_no and not adapter.is_file_asset(asset_id):
        try:
            a = agent_assets.get(asset_id, version_no=version_no)
        except AssetNotFound:
            raise HTTPException(status_code=404, detail="요청한 버전이 없습니다.")
    return a


# ── 생성·개정 ─────────────────────────────────────────────────────────────
@router.post("/{kind_path}")
async def create_asset(kind_path: str, req: AssetCreate,
                       p: Principal = Depends(current_principal)):
    kind = _kind_of(kind_path)
    _assert_may_create(p, kind, req.visibility, req.owner_scope_id)
    if not (p.user_id or "").strip():
        # 저장소도 막지만, 여기서 먼저 401 을 준다 — 저장소의 400 은 «입력이 틀렸다» 로 읽힌다.
        raise HTTPException(status_code=401, detail="사용자 식별이 필요합니다.")
    try:
        a = agent_assets.create(kind, req.name_ko, req.body, p.user_id,
                                owner_scope_id=_canonical_owner(req.owner_scope_id),
                                visibility=req.visibility, purpose=req.purpose)
    except AssetError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _audit(p, audit.AGENT_ASSET_CHANGED, a["asset_id"], kind, "allowed",
           reason="초안 생성", detail=f"visibility={req.visibility} scope={req.owner_scope_id}")
    return a


@router.put("/{kind_path}/{asset_id}")
async def revise_asset(kind_path: str, asset_id: str, req: AssetRevise,
                       p: Principal = Depends(current_principal)):
    """새 버전을 쌓는다. **승인이 풀린다**(저장소 계약) — 내용이 바뀐 뒤에도 승인이 남으면
    그 승인은 읽지 않은 문서에 대한 승인이다."""
    kind = _kind_of(kind_path)
    a = _load_visible(p, kind, asset_id)
    try:
        _assert_may_write(p, kind, a, "update")
        out = agent_assets.revise(asset_id, req.body, p.user_id or "")
    except AssetError as e:
        _audit(p, audit.AGENT_ASSET_CHANGED, asset_id, kind, "denied", reason=str(e))
        raise HTTPException(status_code=403, detail=str(e))
    _audit(p, audit.AGENT_ASSET_CHANGED, asset_id, kind, "allowed",
           reason="개정", detail=f"version={out['current_version']} 승인 해제됨")
    return out


@router.post("/{kind_path}/{asset_id}/copy")
async def copy_asset(kind_path: str, asset_id: str, req: AssetCopy,
                     p: Principal = Depends(current_principal)):
    """자산을 복사해 **새 초안**으로 만든다.

    ★ 파일 자산(SYSTEM·LEGACY) 복사가 이 API 의 주 용도다. 제품 기본을 직접 고칠 수 없게
      막았으므로, 복사가 막히면 사용자는 규칙에 따를 방법이 없다.
    ⚠️ 원본을 **읽을 수 있어야** 복사할 수 있다(`_load_visible`). 그러지 않으면 id 를 아는
      사람이 남의 조직 자산을 복사해 내용을 들여다볼 수 있다."""
    kind = _kind_of(kind_path)
    _assert_may_read(p, kind)
    src = _load_visible(p, kind, asset_id)
    _assert_may_create(p, kind, req.visibility, req.owner_scope_id)
    if not (p.user_id or "").strip():
        raise HTTPException(status_code=401, detail="사용자 식별이 필요합니다.")
    body = src.get("body") or {}
    if adapter.is_file_asset(asset_id) and kind == KIND_SKILL and "markdown" not in body:
        # 목록 경로의 스킬 본문은 파일명만 있다 — 그대로 복사하면 **빈 규칙**이 된다.
        body = (adapter.get_file_asset(asset_id).get("body") or {})
    name = (req.name_ko or "").strip() or f"{src.get('name_ko') or asset_id} 사본"
    try:
        a = agent_assets.create(kind, name, body, p.user_id,
                                owner_scope_id=_canonical_owner(req.owner_scope_id),
                                visibility=req.visibility, purpose=src.get("purpose") or "")
    except AssetError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _audit(p, audit.AGENT_ASSET_CHANGED, a["asset_id"], kind, "allowed",
           reason="복사", detail=f"원본={asset_id} source={src.get('source') or 'DB'}")
    return {**a, "copied_from": asset_id, "copied_from_source": src.get("source") or "DB"}


# ── 승인 흐름 ─────────────────────────────────────────────────────────────
@router.post("/{kind_path}/{asset_id}/submit")
async def submit_asset(kind_path: str, asset_id: str,
                       p: Principal = Depends(current_principal)):
    """검토 요청. **작성자가 할 수 있는 일**이므로 승인 권한을 요구하지 않는다 — 요구하면
    승인권 없는 사람은 자기 초안을 검토에 올릴 수도 없다."""
    kind = _kind_of(kind_path)
    a = _load_visible(p, kind, asset_id)
    try:
        _assert_may_write(p, kind, a, "submit")
        out = agent_assets.submit(asset_id, p.user_id or "")
    except AssetError as e:
        _audit(p, audit.AGENT_ASSET_CHANGED, asset_id, kind, "denied", reason=str(e))
        raise HTTPException(status_code=403, detail=str(e))
    _audit(p, audit.AGENT_ASSET_CHANGED, asset_id, kind, "allowed", reason="검토 요청")
    return out


@router.post("/{kind_path}/{asset_id}/approve")
async def approve_asset(kind_path: str, asset_id: str,
                        p: Principal = Depends(current_principal)):
    kind = _kind_of(kind_path)
    a = _load_visible(p, kind, asset_id)
    try:
        _assert_may_publish(p, kind, a, "approve")
        out = agent_assets.approve(asset_id, p.user_id or "")
    except AssetError as e:
        _audit(p, audit.APPROVAL_GRANTED, asset_id, kind, "denied", reason=str(e))
        raise HTTPException(status_code=403, detail=str(e))
    #: 승인은 `APPROVAL_GRANTED` 로 남긴다 — «누가 이 정의를 실행 가능하게 만들었는가» 는
    #  일반 변경과 다른 질문이고, 감사에서 그 둘을 섞으면 되짚을 수 없다.
    _audit(p, audit.APPROVAL_GRANTED, asset_id, kind, "allowed",
           reason="승인", detail=f"version={out['current_version']} visibility={out['visibility']}")
    return out


@router.post("/{kind_path}/{asset_id}/retire")
async def retire_asset(kind_path: str, asset_id: str,
                       p: Principal = Depends(current_principal)):
    """폐기 — **행을 지우지 않는다**(저장소 계약). 과거 산출물이 이 자산을 가리키고 있다."""
    kind = _kind_of(kind_path)
    a = _load_visible(p, kind, asset_id)
    try:
        _assert_may_publish(p, kind, a, "retire")
        out = agent_assets.retire(asset_id, p.user_id or "")
    except AssetError as e:
        _audit(p, audit.AGENT_ASSET_CHANGED, asset_id, kind, "denied", reason=str(e))
        raise HTTPException(status_code=403, detail=str(e))
    _audit(p, audit.AGENT_ASSET_CHANGED, asset_id, kind, "allowed", reason="폐기")
    return out


# ── 설계 §7 별칭 ──────────────────────────────────────────────────────────
@router.post("/skills/propose")
async def propose_skill(req: AssetCreate, p: Principal = Depends(current_principal)):
    """설계 §7 은 스킬 초안을 `POST /skills/propose` 로 적었다. 동작은 `POST /skills` 와 같다 —
    화면 작업자가 설계 문서대로 불러도 동작해야 하므로 별칭으로 둔다.

    경로 세그먼트가 2개여서 위의 어느 POST 라우트와도 겹치지 않는다(`POST /{kind_path}` 는 1개,
    나머지는 3개). 그래서 등록 순서를 신경 쓸 필요가 없다."""
    return await create_asset("skills", req, p)
