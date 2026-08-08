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

from api.deps import (Principal, capabilities_of, current_principal, hidden_envelope,
                      may_see_exact_count, require_caps, viewer_visible_scopes)
from core import admin_capability as cap
from core import agent_asset_adapter as adapter
from core import asset_project_usage as project_usage
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


# ── 「지금 이 자산에 이 행동을 할 수 있는가」 ─────────────────────────────
#
# ★★★ [§8.6 · §10 UI] 판정을 **사유 계산**과 **던지기**로 나눈다.
#
# 왜: 설계 §10 은 「API 403 을 버튼 클릭 후 처음 알게 되는 경로가 없어야 한다」고 못박았다.
# 그런데 화면이 그것을 지키려면 자산마다 «내가 이걸 할 수 있는가» 를 알아야 하고, 화면이
# 그 규칙을 다시 구현하면 **서버와 화면이 서서히 갈라진다**(「버튼은 보이는데 서버는 거부」
# 또는 그 반대). 그때 사용자는 통제가 고장났다고 읽는다.
#
# → 그래서 **서버가 자산마다 답한다.** 아래 `_*_block_reason` 이 유일한 규칙이고,
#   `_assert_may_*` 는 그것을 읽어 403 으로 바꿀 뿐이다. 목록은 같은 함수로 사유를 실어 보낸다.
#
# ⚠️ 목록용 판정은 `require_caps` 를 **부르지 않는다.** 그 함수는 거부를 감사에 남기므로,
#   목록 한 번에 감사 로그가 수십 줄 쌓인다(자산 31개 × 행동 4개). capability 는 한 번만
#   계산해 넘긴다.
def _write_block_reason(c, kind: str, asset: Dict[str, Any], uid: str) -> str:
    if not c.has(_CAPS[kind][2]):
        return "이 종류의 자산을 바꿀 권한이 없습니다."
    if adapter.is_file_asset(asset["asset_id"]):
        try:
            adapter.assert_writable_here(asset["asset_id"])
        except AssetError as e:
            return str(e)
    if asset["visibility"] == VIS_PERSONAL:
        return "" if (asset.get("created_by") or "") == uid else \
            "다른 사람의 개인 자산은 수정할 수 없습니다."
    if asset["visibility"] == VIS_ENTERPRISE and not c.can_publish_enterprise():
        return "전사 자산은 AI 거버넌스 관리자만 수정할 수 있습니다."
    if asset["visibility"] in (VIS_SCOPE, VIS_DESCENDANTS) \
            and not c.can_manage_scope(asset.get("owner_scope_id") or ""):
        # ★ 작성자 본인은 자기 초안을 계속 고칠 수 있어야 한다 — 그러지 않으면 관리자가
        #   아닌 사람은 자기가 만든 것을 한 번 저장한 뒤 고칠 수 없다.
        if (asset.get("created_by") or "") != uid:
            return (f"'{_scope_label(asset.get('owner_scope_id') or '')}' 조직 자산을 "
                    f"수정할 권한이 없습니다 — 관리 범위 밖입니다.")
    return ""


def _submit_block_reason(c, kind: str, asset: Dict[str, Any], uid: str) -> str:
    """「승인 요청」. ⚠️ **개정과 다른 행동이다** — 개정은 승인된 자산에도 할 수 있지만(새 버전을
    쌓고 승인이 풀린다) 승인 요청은 초안·검토 상태에서만 뜻이 있다. 둘을 한 사유로 묶으면
    승인된 자산을 고칠 수 없게 되거나, 이미 승인된 것에 「승인 요청」이 열려 보인다."""
    r = _write_block_reason(c, kind, asset, uid)
    if r:
        return r
    try:
        agent_assets.assert_submittable(asset)
    except AssetError as e:
        return str(e)
    return ""


def _publish_authz_reason(c, kind: str, asset: Dict[str, Any], uid: str, verb: str) -> str:
    """승인·폐기의 **자격**만 본다 — 상태는 보지 않는다.

    ⚠️ 둘을 갈라 두는 이유: 전사 승격은 «승인 자격» 을 요구하지만 «지금 승인 가능한 상태» 를
      요구하지 않는다(승격은 **이미 승인된** 조직 자산에서 출발한다). 한 함수로 묶었더니
      승격이 항상 「APPROVED 상태에서는 승인할 수 없습니다」로 막혔다."""
    if not c.has(_CAPS[kind][3 if verb == "approve" else 4]):
        return ("승인 권한이 없습니다 — 조직 관리자·AI 관리자가 승인합니다." if verb == "approve"
                else "폐기 권한이 없습니다.")
    if adapter.is_file_asset(asset["asset_id"]):
        try:
            adapter.assert_writable_here(asset["asset_id"])
        except AssetError as e:
            return str(e)
    if asset["visibility"] == VIS_ENTERPRISE and not c.can_publish_enterprise():
        return ("전사 공개 자산의 승인·폐기는 AI 거버넌스 관리자 권한입니다 — "
                "부서 단위에서는 승격을 요청할 수 있습니다.")
    if asset["visibility"] in (VIS_SCOPE, VIS_DESCENDANTS) \
            and not c.can_manage_scope(asset.get("owner_scope_id") or ""):
        return (f"'{_scope_label(asset.get('owner_scope_id') or '')}' 조직 자산을 "
                f"승인·폐기할 권한이 없습니다 — 관리 범위 밖입니다.")
    if asset["visibility"] == VIS_PERSONAL and (asset.get("created_by") or "") != uid:
        return "다른 사람의 개인 자산은 다룰 수 없습니다."
    return ""


def _publish_block_reason(c, kind: str, asset: Dict[str, Any], uid: str, verb: str) -> str:
    """승인·폐기 — 자격 **그리고** 상태.

    ★★ 상태를 여기서 함께 보는 이유: 승인 자격이 있어도 이미 승인된 것은 다시 승인할 수 없고
      폐기된 것은 또 폐기할 수 없다. 이 검사가 빠져 있어 「사유는 비었는데 서버는 403」인
      상태가 있었다 — 2026-08-08 계약 테스트가 잡았다."""
    r = _publish_authz_reason(c, kind, asset, uid, verb)
    if r:
        return r
    try:
        if verb == "approve":
            agent_assets.assert_approvable(asset)
        else:
            agent_assets.assert_retirable(asset)
    except AssetError as e:
        return str(e)
    return ""


def _publish_to_org_block_reason(c, kind: str, asset: Dict[str, Any], uid: str) -> str:
    """「조직에 공개」 — 내 초안을 우리 조직 자산으로.

    ⚠️ **대상 조직의 관리 범위는 여기서 보지 않는다.** 목록 시점에는 사용자가 어느 조직을
      고를지 모르기 때문이다. 그 판정은 실행할 때 `_assert_may_create` 가 하고, 화면은 그
      사유를 그대로 받는다 — 여기서 넘겨짚어 막으면 고를 수 있는 조직까지 막힌다."""
    if adapter.is_file_asset(asset["asset_id"]):
        return "제품 기본 정의는 옮길 수 없습니다 — 복사해서 조직 자산으로 만드십시오."
    if (asset.get("created_by") or "") != uid:
        return "다른 사람의 초안은 옮길 수 없습니다."
    if not c.has(_CAPS[kind][1]):
        return "자산을 만들 권한이 없습니다 — 읽기만 가능합니다."
    try:
        agent_assets.assert_publishable_to_scope(asset)
    except AssetError as e:
        return str(e)
    return ""


def _promote_block_reason(c, kind: str, asset: Dict[str, Any], uid: str) -> str:
    """전사 승격(요청 또는 확정). 조직 승인 자격을 먼저 요구한다."""
    if adapter.is_file_asset(asset["asset_id"]):
        return ("제품 기본 정의는 승격 대상이 아닙니다 — 복사해서 조직 자산으로 만든 뒤 "
                "조직 승인을 받고 승격을 요청하십시오.")
    #: ⚠️ **자격만** 본다. 승격은 이미 승인된 자산에서 출발하므로 「지금 승인 가능한 상태인가」
    #:   를 요구하면 항상 막힌다. 승격 자신의 상태 규칙은 바로 아래 저장소가 갖는다.
    r = _publish_authz_reason(c, kind, asset, uid, "approve")
    if r:
        return r
    try:
        agent_assets.assert_promotable(asset)           # 상태·범위 규칙은 저장소가 갖는다
    except AssetError as e:
        return str(e)
    return ""


def _assert_may_write(p: Principal, kind: str, asset: Dict[str, Any], verb: str):
    """개정. **보이는 자산에 대한 거부는 403** 이고 사유를 말한다."""
    c = require_caps(p, _CAPS[kind][2], resource=f"agent_asset:{kind}", action=verb)
    r = _write_block_reason(c, kind, asset, p.user_id or "")
    if r:
        raise HTTPException(status_code=403, detail=r)
    return c


def _assert_may_publish(p: Principal, kind: str, asset: Dict[str, Any], verb: str,
                        check_state: bool = True):
    """승인·폐기. 조직 범위와 전사 공개를 **따로** 본다(설계 §4.2).

    ⚠️ `check_state=False` 는 **전사 승격 전용**이다 — 승격은 승인 자격을 요구하지만 「지금
      승인 가능한 상태」를 요구하지 않는다(이미 승인된 자산에서 출발한다). 상태 규칙은
      그쪽에서 `assert_promotable` 이 따로 본다."""
    idx = 3 if verb == "approve" else 4
    c = require_caps(p, _CAPS[kind][idx], resource=f"agent_asset:{kind}", action=verb)
    r = (_publish_block_reason if check_state else _publish_authz_reason)(
        c, kind, asset, p.user_id or "", verb)
    if r:
        raise HTTPException(status_code=403, detail=r)
    return c


# ── 응답 모양 ─────────────────────────────────────────────────────────────
def _slim(a: Dict[str, Any], c=None, kind: str = "", uid: str = "") -> Dict[str, Any]:
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
    #: ★★★ [§8.6 · §10 UI] **자산마다 «지금 이걸 할 수 있는가» 를 서버가 답한다.**
    #: 빈 문자열이면 할 수 있고, 아니면 그 문장이 곧 못 하는 이유다. 화면은 이 값을 그대로
    #: 버튼에 붙이면 되므로 규칙을 다시 구현할 필요가 없다 — 그래야 「버튼은 보이는데 서버는
    #: 거부」가 생기지 않는다(2026-08-08 감사에서 실제로 발견: 부서원에게 남의 조직 자산의
    #: «승인 요청» 이 활성으로 보였고, 누르면 403 이었다).
    if c is not None and kind:
        out["blocked"] = {
            "update": _write_block_reason(c, kind, a, uid),
            "submit": _submit_block_reason(c, kind, a, uid),
            "approve": _publish_block_reason(c, kind, a, uid, "approve"),
            "retire": _publish_block_reason(c, kind, a, uid, "retire"),
            "publish_to_org": _publish_to_org_block_reason(c, kind, a, uid),
            "promote": _promote_block_reason(c, kind, a, uid),
            #: 복사는 «이 자산» 이 아니라 «새 자산» 을 만드는 일이다 — 원본이 파일 자산이어도
            #: 막히지 않는다. 오히려 그것이 기본 제공 정의를 쓰는 유일한 방법이다.
            "copy": "" if c.has(_CAPS[kind][1])
                    else "자산을 만들 권한이 없습니다 — 읽기만 가능합니다.",
        }
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
    #: capability 는 **한 번만** 계산해 모든 자산에 넘긴다 — 자산마다 다시 풀면 목록이 느려진다.
    c = capabilities_of(p)
    out = {
        "kind": kind,
        "items": [_slim(r, c, kind, p.user_id or "") for r in rows],
        "total": len(rows),
        #: ★ 목록이 «전부» 인지 «범위 안» 인지 화면이 알아야 한다. 이 표시가 없으면 사용자는
        #  자기가 보는 목록이 전사 전체라고 오해한다.
        "scoped": viewer_visible_scopes(p) is not None,
    }
    #: ★★ [설계 §8.3] 「현재 보는 범위와 **숨겨진 자산 수**」.
    #   `scoped` 는 «걸렀다» 만 말하고 «얼마나» 를 말하지 않는다 — 사용자는 3건을 보면서
    #   그것이 전부인지 30건 중 3건인지 알 수 없다.
    #   ⚠️ 판정을 여기서 새로 만들지 않는다. `hidden_envelope` 이 이미 계약을 갖고 있다 —
    #     **존재는 누구에게나, 정확한 건수는 자료를 관리할 사람에게만**(남의 조직 자산 규모는
    #     그 자체로 정보다). 라우트마다 다시 적으면 그 규칙이 갈라진다.
    if out["scoped"]:
        try:
            all_rows = adapter.list_all(kind, None, p.user_id or "",
                                        include_files=include_files,
                                        include_retired=include_retired)
            if status:
                all_rows = [r for r in all_rows if r.get("status") == status]
            out.update(hidden_envelope(p, len(all_rows), len(rows), exact_for="agent"))
        except Exception as e:                                       # pragma: no cover
            # ⚠️ 세지 못한 것을 «숨김 없음» 으로 두지 않는다 — 그러면 사용자는 목록을 전량으로 읽는다.
            print(f"⚠️ [agent_governance] 숨김 건수 계산 실패: {e}")
            out["hidden_present"] = None
    return out


#: ⚠️⚠️ **이 라우트는 `/{kind_path}/{asset_id}` 보다 먼저 등록돼야 한다.** FastAPI 는 등록
#:   순서로 매칭하므로, 뒤에 두면 `/agents/usage` 가 `asset_id="usage"` 로 잡혀 404 가 된다.
#:   그 404 는 「사용 현황이 없다」처럼 읽히고, 화면은 그것을 「아무도 안 쓴다」로 그린다.
@router.get("/{kind_path}/usage")
async def asset_usage_summary(kind_path: str,
                              p: Principal = Depends(current_principal)):
    """[설계 §8.4] 이 종류의 자산을 **쓰는 프로젝트가 몇 개인가.**

    ★ 목록과 **따로** 둔 이유: 프로젝트 작업공간을 훑는 일이라 목록마다 하면 목록이 느려지고,
      스캔이 실패했을 때 목록까지 함께 죽는다. 화면은 「사용 현황을 아직 못 받았다」를 별도
      상태로 그릴 수 있어야 한다 — 목록이 있는데 사용 수만 없는 것은 정상적인 중간 상태다.

    ⚠️⚠️ **`project_count` 를 혼자 읽으면 안 된다.** `axis_observed == 0` 이면 그 값은
      「쓰이지 않는다」가 아니라 **「아직 모른다」** 이다(2026-08-08 실측: 56개 프로젝트 중
      구성을 기록한 것이 0개). 순진하게 0 을 그리면 사용자는 전부 폐기해도 된다고 읽고,
      지운 뒤에야 그것이 「안 쓰인 것」이 아니라 「아직 안 본 것」이었음을 안다.

    ⚠️ **어느 프로젝트인지는 자산을 관리할 사람에게만** 준다 — 자산을 볼 자격과 그 자산이
      어느 프로젝트에 쓰이는지 알 자격은 다르다. 판정은 `hidden_envelope` 과 같은 규칙을
      쓴다(`_EXACT_COUNT_RULES["agent"]`) — 여기서 새로 만들면 두 규칙이 갈라진다."""
    kind = _kind_of(kind_path)
    _assert_may_read(p, kind)
    rows = adapter.list_all(kind, viewer_visible_scopes(p), p.user_id or "",
                            include_files=True, include_retired=True)
    #: DB 자산은 목록 행에 `body` 가 없다(본문은 버전 표에 있다). 매칭 키가 본문의 `id` 일 수
    #: 있으므로 DB 자산만 본문을 읽는다 — 파일 자산은 id 규약(`file:<kind>:<native>`)만으로
    #: 맞출 수 있고, 스킬 31개 본문을 여기서 읽으면 응답이 무거워진다.
    enriched = []
    for r in rows:
        if not adapter.is_file_asset(str(r.get("asset_id") or "")) and "body" not in r:
            try:
                r = {**r, "body": (adapter.get_any(r["asset_id"]).get("body") or {})}
            except Exception:
                pass            # 본문을 못 읽어도 `asset_id` 키로는 맞출 수 있다
        enriched.append(r)

    try:
        out = project_usage.usage_for(enriched, kind)
    except Exception as e:                                           # pragma: no cover
        # ★ 실패를 «사용 0건» 으로 돌려주지 않는다 — 그것이 이 기능에서 가장 비싼 거짓말이다.
        print(f"⚠️ [agent_governance] 사용 집계 실패: {e}")
        return {"kind": kind, "available": False, "error": str(e),
                "projects_total": 0, "projects_observed": 0, "axis_observed": 0, "usage": {}}

    if not may_see_exact_count(p, "agent"):
        for v in out["usage"].values():
            v.pop("projects", None)
    out["kind"] = kind
    return out


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


class PublishToScope(BaseModel):
    owner_scope_id: str = Field(..., min_length=1)


@router.post("/{kind_path}/{asset_id}/publish-to-org")
async def publish_asset_to_org(kind_path: str, asset_id: str, req: PublishToScope,
                               p: Principal = Depends(current_principal)):
    """[설계 §8.6] 내 초안을 **우리 조직 자산으로.**

    ★★★ 이 경로가 없어서 화면이 «복사» 로 우회했고, **원본 개인 초안이 그대로 남았다.** 같은
      정의가 두 벌이 되면 어느 쪽이 정본인지 아무도 모르고 한쪽만 고쳐진 채 승인된다.

    ⚠️ 자격은 **생성과 같다**(`create` + 대상 조직 관리 범위). 「조직에 자산을 만들 수 있는
      사람」과 「내 초안을 조직에 올릴 수 있는 사람」이 다르면, 같은 결과를 두 경로로 얻을 수
      있게 되고 그중 느슨한 쪽이 실제 통제가 된다.
    ⚠️ 남의 개인 초안은 애초에 보이지 않는다(`_load_visible` → 404). 그 위에 작성자 본인인지도
      확인한다 — 보이는 것과 옮길 수 있는 것은 다르다."""
    kind = _kind_of(kind_path)
    a = _load_visible(p, kind, asset_id)
    if adapter.is_file_asset(asset_id):
        raise HTTPException(
            status_code=403,
            detail="제품 기본 정의는 옮길 수 없습니다 — 복사해서 조직 자산으로 만드십시오.")
    #: ⚠️ **오늘은 도달하지 않는 방어선이다.** 개인 초안은 작성자에게만 보이므로 위
    #:   `_load_visible` 이 이미 404 를 낸다. 그래도 지우지 않는다 — 가시성 규칙이 바뀌면
    #:   (관리자가 남의 초안을 감사할 수 있게 되는 등) 그 순간 «볼 수 있으니 옮길 수도 있다» 가
    #:   된다. 변이 검사가 「지워도 아무 테스트도 안 깨진다」고 알려 줘서
    #:   `test_author_check_holds_even_if_visibility_ever_widens` 로 못박아 두었다.
    if (a.get("created_by") or "") != (p.user_id or ""):
        raise HTTPException(status_code=403, detail="다른 사람의 초안은 옮길 수 없습니다.")
    _assert_may_create(p, kind, VIS_SCOPE, req.owner_scope_id)
    try:
        out = agent_assets.publish_to_scope(asset_id, _canonical_owner(req.owner_scope_id),
                                            p.user_id or "")
    except AssetError as e:
        _audit(p, audit.AGENT_ASSET_CHANGED, asset_id, kind, "denied", reason=str(e))
        raise HTTPException(status_code=403, detail=str(e))
    _audit(p, audit.AGENT_ASSET_CHANGED, asset_id, kind, "allowed",
           reason="조직 공개", detail=f"scope={req.owner_scope_id} status={out['status']}")
    return out


@router.post("/{kind_path}/{asset_id}/promote")
async def promote_asset(kind_path: str, asset_id: str,
                        p: Principal = Depends(current_principal)):
    """[설계 §4.2 · §8.6] 조직 자산을 **전사 공용으로.**

    ★★★ 이 경로가 없어서 **서버가 지키지 못할 말을 하고 있었다.** 전사 자산의 승인을 거부할
      때 「부서 단위에서는 승격을 **요청할 수 있습니다**」라고 안내하는데(`_assert_may_publish`),
      그 요청을 받는 곳이 어디에도 없었다 — 안내가 막다른 길로 끝나면 사용자는 규칙을 따를
      방법이 없고, 결국 규칙을 우회할 방법을 찾는다.

    자격에 따라 **두 가지로 갈린다.** 한 버튼이 두 일을 하는 것이 아니라, 같은 요청에 대해
    자격이 답을 정하는 것이다:
      · AI 거버넌스 관리자 → 승격을 **확정**한다(`visibility=ENTERPRISE`, 상태는 `REVIEW` 로
        되돌아간다 — 전사 승인은 조직 승인과 다른 자격이므로 한 번 더 승인받아야 한다)
      · 조직 승인자      → 승격을 **요청**한다. ⚠️ 요청은 가시성을 바꾸지 않는다.

    ⚠️ 조직 승인 자격(`approve`)을 먼저 요구한다. 자기 조직 자산을 승인할 수도 없는 사람이
      그것을 전사로 올려 달라고 요청하는 것은 순서가 뒤집힌 것이다."""
    kind = _kind_of(kind_path)
    a = _load_visible(p, kind, asset_id)
    if adapter.is_file_asset(asset_id):
        raise HTTPException(
            status_code=403,
            detail="제품 기본 정의는 승격 대상이 아닙니다 — 복사해서 조직 자산으로 만든 뒤 "
                   "조직 승인을 받고 승격을 요청하십시오.")
    try:
        c = _assert_may_publish(p, kind, a, "approve", check_state=False)
        if c.can_publish_enterprise():
            out = agent_assets.promote(asset_id, p.user_id or "")
            outcome, reason = "확정", "전사 승격 확정"
        else:
            out = agent_assets.request_promotion(asset_id, p.user_id or "")
            outcome, reason = "요청", "전사 승격 요청"
    except AssetError as e:
        # ★ 400 이 아니라 403 이다. 「입력이 틀렸다」가 아니라 「지금 그 상태로는 안 된다」이고,
        #   사용자가 할 일(조직 승인을 먼저 받는다)이 메시지에 들어 있다.
        _audit(p, audit.AGENT_ASSET_CHANGED, asset_id, kind, "denied", reason=str(e))
        raise HTTPException(status_code=403, detail=str(e))
    _audit(p, audit.APPROVAL_GRANTED if outcome == "확정" else audit.AGENT_ASSET_CHANGED,
           asset_id, kind, "allowed", reason=reason,
           detail=f"visibility={out['visibility']} status={out['status']}")
    return {**out, "promotion_outcome": outcome}


# ── 설계 §7 별칭 ──────────────────────────────────────────────────────────
@router.post("/skills/propose")
async def propose_skill(req: AssetCreate, p: Principal = Depends(current_principal)):
    """설계 §7 은 스킬 초안을 `POST /skills/propose` 로 적었다. 동작은 `POST /skills` 와 같다 —
    화면 작업자가 설계 문서대로 불러도 동작해야 하므로 별칭으로 둔다.

    경로 세그먼트가 2개여서 위의 어느 POST 라우트와도 겹치지 않는다(`POST /{kind_path}` 는 1개,
    나머지는 3개). 그래서 등록 순서를 신경 쓸 필요가 없다."""
    return await create_asset("skills", req, p)
