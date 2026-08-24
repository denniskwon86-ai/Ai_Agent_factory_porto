"""[트랙 I-2] 생성 앱 데이터 평면 REST API. prefix `/api/v1/appdata`.

설계: `docs/design_app_data_plane_2026-08-08.md`

## 이 라우터가 지키는 것

생성된 앱은 자기 로그인도, 자기 백엔드도 갖지 않는다(`core/app_manifest.py` CL-0 계약).
그래서 앱의 데이터는 **여기를 통해서만** 드나들고, 그 통로에 이미 있는 통제를 전부 태운다.

| 관심사 | 재사용 |
|---|---|
| 주체 식별 | `api/deps.current_principal` |
| 읽기 범위 | `api/deps.assert_release_readable` |
| **쓰기 범위** | `api/deps.assert_release_writable` (트랙 I 에서 신설) |
| 감사 | `core/decision_ledger` — **구조 변경만**(§6) |

★★ **앱은 `release_id` 를 말하지 않는다.** 앱이 자기 릴리스를 지정할 수 있으면 남의 앱
  데이터를 요청할 수 있다. 브리지(부모 창)가 붙이고, 앱은 데이터셋 «이름» 만 말한다.
  이 라우터는 그 계약의 서버 쪽 절반이다 — `release_id` 를 받되 **매번 권한을 재검사**한다.

⚠️ 식별되지 않은 요청의 쓰기는 401 이다. 트랙 H 가 「식별만으로 열리는 쓰기」 65건을
  봉합했는데 여기서 「식별조차 없는 쓰기」를 새로 만들면 그 작업이 무효가 된다.
"""
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from api.deps import (Principal, assert_release_readable, assert_release_writable,
                      current_principal)
from core.app_data import AppDataError, app_data_service

router = APIRouter(prefix="/api/v1/appdata")


# ── 공통 ──────────────────────────────────────────────────────────────────
def _actor(p: Principal) -> str:
    """쓰기 주체. **비어 있으면 401** — 누가 썼는지 모르는 업무 데이터는 만들지 않는다."""
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("앱 데이터를 쓰려면 사용자 식별이 필요합니다. 누가 입력했는지 남지 않는 "
                    "업무 데이터는 나중에 «이 값이 왜 이런가» 에 답할 수 없습니다."))
    return uid


# ── [G1-B P0] 이중 판정 어댑터 ────────────────────────────────────────────
#
# ★★★ 기존 `assert_release_*` 가 **강제**하고, 신규 PDP 는 **관측만** 한다. 어긋남이 0 임을
#   종단으로 확인한 뒤에야 원자적으로 전환한다(교차검토 [G1-B-P0-REVIEW-75]).
#
# ⚠️⚠️ **범위·소유·문맥을 요청 본문에서 읽지 않는다.** `POST /datasets` 는 `owner_dept_id`·
#   `scope_node_id` 를 클라이언트에서 받는데, 그 값을 판정 입력으로 쓰면 **클라이언트가 자기
#   권한을 정하는** 상승 경로가 된다. 서버는 **릴리스**에서 유도한다(`release.json` 이
#   `tenant_id`·`enterprise_scope_id`·`entity_mode`·소유자를 전부 갖고 있다).

def _release_scope(release_id: str) -> "app_policy.ResourceScope":
    """릴리스에서 **서버가 직접** 자원 범위를 만든다.

    ## ★★★ 두 원천을 나눠 쓴다 (shadow 가 실제 완화를 잡아서 고친 것)

    | 축 | 원천 | 왜 |
    |---|---|---|
    | 소유(부서·사용자) | **`ownership` 미러** | 기존 `assert_release_*` 가 보는 바로 그 값 |
    | 문맥(테넌트·실행모드·조직범위) | **`release.json`** | 미러에 그 컬럼이 없다 |

    ⚠️⚠️ 소유 축까지 파일에서 읽었더니 **shadow 에서 「기존 거부 / PDP 허용」이 나왔다.**
      `release.json`(진실원본)과 `ownership`(검색용 미러)은 **어긋날 수 있고**, 그래서
      `POST /api/v1/org/reconcile` 이 존재한다. 어긋난 순간 PDP 가 더 느슨해지면 전환 자체가
      권한 확대가 된다. **이행 기간에는 기존 판정과 같은 값을 봐야** 동등성이 성립한다.

    ★ 미러가 정본이라는 뜻은 아니다. 정본은 파일이고, 드리프트는 `reconcile` 로 고친다.
      여기서 미러를 쓰는 것은 **동등성 증명을 위한 이행 조치**다 — 전환이 끝나고 파일을
      단일 원천으로 삼으려면 그때 드리프트를 먼저 0 으로 만들어야 한다.

    ⚠️ 판독 실패는 `INVALID` 다 — «못 읽었으니 통과» 로 두면 그 순간 통제가 없다
      (`ownership_visible` 1차 구현이 정확히 그렇게 틀렸다)."""
    from core import app_policy
    rid = str(release_id or "")
    try:
        #: ★ 경로를 다시 선언하지 않는다 — 정본은 `core/library_paths` 하나다
        #:   (`factory_control` 이 같은 이유로 그것만 쓴다).
        from core import library_paths
        path = os.path.join(library_paths.release_dir(rid), "release.json")
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError("release.json 최상위가 객체가 아닙니다.")
    except Exception:
        return app_policy.ResourceScope(binding_state=app_policy.INVALID)

    #: 소유 축은 기존 판정과 **같은 값**을 본다. 미러가 없으면 파일로 떨어진다 —
    #: 그때는 기존도 「미기록은 막지 않는다」로 통과하므로 방향이 어긋나지 않는다.
    own_dept = str(d.get("owner_dept_id", "") or "")
    own_user = str(d.get("owner_user_id", "") or "")
    try:
        from core.org_directory import org_directory
        mirror = org_directory.get_ownership("release", rid)
        if mirror:
            own_dept = str(mirror.get("dept_id", "") or "")
            own_user = str(mirror.get("owner_user_id", "") or "")
    except Exception:
        pass                     # 미러 조회 실패는 파일 값을 쓴다(둘 다 없으면 아래에서 막힌다)

    return app_policy.ResourceScope(
        tenant_id=str(d.get("tenant_id", "") or ""),
        entity_mode=str(d.get("entity_mode", "") or ""),
        scope_node_id=str(d.get("enterprise_scope_id", "") or ""),
        owner_user_id=own_user,
        owner_dept_id=own_dept,
        binding_state=app_policy.BOUND)


def _shadow_check(p: Principal, action: str, release_id: str,
                  ds: Optional[Dict[str, Any]] = None) -> None:
    """신규 PDP 를 **판정만** 하고 결과를 관측기에 넘긴다. 절대 막지 않는다.

    ⚠️ 관측 장애가 기능 장애가 되면 안 된다 — 모든 예외를 삼키되 **세어서 드러낸다**."""
    from core import app_policy
    from core.policy_shadow import policy_shadow
    try:
        from api.deps import viewing_context, visibility_block_reason
        try:
            ctx = viewing_context(p)
        except HTTPException:
            #: 문맥을 확정하지 못하면 PDP 는 거부한다 — 그것이 옳고, 여기서는 **강화**로 세인다.
            ctx = {}
        res = _release_scope(release_id)
        if ds is not None:
            res = app_policy.ResourceScope(
                tenant_id=res.tenant_id, entity_mode=res.entity_mode,
                scope_node_id=res.scope_node_id, owner_user_id=res.owner_user_id,
                owner_dept_id=res.owner_dept_id, binding_state=res.binding_state,
                #: 데이터셋의 «폐기» 는 자원 상태다. 릴리스가 아니라 데이터셋이 갖는다.
                status="retired" if (ds.get("retired_at") or "") else "active")
        subject = app_policy.Subject(
            user_id=(p.user_id or ""), scope=p.scope, ctx=ctx,
            #: ★ 동등성 하니스가 증명한 계약 — 이 값을 빠뜨리면 PDP 가 기존보다 느슨해진다.
            blocked_reason=visibility_block_reason(p), via="session")
        facts = app_policy.AppResourceFacts(
            release_id=str(release_id or ""),
            app_class=str((ds or {}).get("app_class", "") or ""))
        d = app_policy.decide(subject, res, action, app=facts if ds is not None else None)
        return d
    except Exception as e:                                   # pragma: no cover
        #: ⚠️⚠️ 예외 **메시지를 넘기지 않는다.** 예외는 자주 입력값을 그대로 문자열에 담고
        #:   (`ValueError(f"…{payload}…")`), 그러면 업무 데이터가 텔레메트리로 흘러든다.
        #:   남기는 것은 «어디서 · 무슨 종류» 까지다.
        policy_shadow.error(action=action, exc_type=type(e).__name__)
        return None


#: ★★ [G1-B05] 라우트 → **SDK 작업**. 전환 게이트가 「여섯 작업을 허용·거부 양쪽으로 눌러
#:   봤는가」를 세려면 관측에 그 이름이 실려야 한다.
#: ⚠️ 앱이 부를 수 없는 라우트(콘솔·생성기용)는 여기 없다 — 빈 문자열이 되고 작업 표본으로
#:   세지 않는다. 「관리 화면에서 눌러 봤으니 덮였다」가 되면 게이트가 무의미해진다.
_PATH_OP: Dict[str, str] = {
    "GET /datasets/by-name": "data.schema",
    "GET /records": "data.list",
    "GET /records/{id}": "data.get",
    "POST /records": "data.create",
    "PUT /records/{id}": "data.update",
    "DELETE /records/{id}": "data.remove",
}


def _enforce(p: Principal, action: str, release_id: str,
             ds: Optional[Dict[str, Any]] = None, path: str = "") -> None:
    """★★★ [G1-B 6] **원자적 전환.** 어느 판정기가 강제하는지는 정책 스위치 하나가 정한다.

        `scope_policy.app_pdp_enforce()`  True(기본) → 신규 PDP 가 강제
                                          False      → 기존 판정이 강제(롤백)

    ## ⚠️⚠️ 어느 쪽이 강제하든 **두 판정을 모두 계산하고 기록한다**

    전환했다고 관측을 끄면 **되돌릴 근거가 사라진다.** 전환 뒤에 어긋남이 생겨도 아무도
    그것을 세지 않으면, 「되돌려야 하는가」를 감으로 답하게 된다. 그래서 이 함수는 전환
    전후로 **같은 모양**이다 — 바뀌는 것은 「누가 예외를 던지는가」뿐이다.

    ★ 기록의 뜻도 그대로다: `old_allowed` 는 언제나 **기존 판정**, `new_allowed` 는 언제나
      **PDP** 다. 강제자가 바뀌었다고 이 두 이름이 뒤바뀌면 `looser`(권한이 넓어지는 칸)의
      의미가 뒤집히고, 그 순간 게이트 표가 통째로 거짓이 된다.

    ## 왜 기존 판정을 «지우지» 않는가

    지우면 되돌릴 수 없다. 롤백은 배포가 아니라 **정책 파일 한 줄**이어야 한다 —
    운영 중에 되돌릴 수 없는 전환은 아무도 승인하지 않는다(`org_enforce` 와 같은 판단).
    """
    from core import app_policy
    from core import scope_policy
    from core.policy_shadow import policy_shadow

    #: PDP 를 **먼저** 판정한다(부작용 없음). 그래야 기존 판정이 예외를 던져도 관측이 남는다.
    decision = _shadow_check(p, action, release_id, ds)
    mutating = action in (app_policy.WRITE, app_policy.DELETE, app_policy.MANAGE)

    def _old_verdict() -> Tuple[Optional[bool], Optional[HTTPException]]:
        """기존 판정을 **던지지 않고** 물어본다. `(허용?, 거부예외)`.

        ★★★ [교차검토 89 ①] 첫 판은 `HTTPException` 만 잡았다. 그러면 기존 판정기가
          `RuntimeError`·DB 오류를 내는 순간 **PDP 가 정상적으로 허용했더라도** 스위치 분기에
          닿기 전에 요청이 500 으로 죽었다.

        ⚠️ PDP 강제 상태에서 기존 판정기는 **관측자**다. 관측자의 장애가 기능 장애가 되면
          안 된다 — 그것이 이 저장소의 관통 규약이고, `_shadow_check` 도 같은 규약을 따른다.
        ★ 「모른다」를 `None` 으로 돌려준다. `False`(거부)와 **다른 사실**이기 때문이다 —
          롤백 상태에서 그 둘을 뭉개면 「판정 못 함」이 「거부」로 조용히 바뀐다."""
        try:
            if mutating:
                assert_release_writable(p, release_id)
            else:
                assert_release_readable(p, release_id)
            return True, None
        except HTTPException as e:
            return False, e
        except Exception as e:
            #: 관측자의 장애는 **세어서 드러낸다**(조용한 유실 금지).
            policy_shadow.error(action=action, exc_type=type(e).__name__)
            return None, None

    old_ok, old_exc = _old_verdict()

    #: ⚠️ 기존 판정을 **모르면** 어긋남을 세지 않는다. 모르는 값을 `False` 로 채우면
    #:   그 순간 「기존 거부 · PDP 허용」= `looser` 가 되고, 전환 근거 표가 거짓이 된다.
    if decision is not None and old_ok is not None:
        policy_shadow.observe(path=path or "appdata", action=action, old_allowed=old_ok,
                              new_allowed=decision.allowed, new_reason=decision.reason,
                              actor=(p.user_id or ""), resource_id=str(release_id or ""),
                              op=_PATH_OP.get(path, ""))

    if scope_policy.app_pdp_enforce():
        #: ⚠️ 관측이 실패해 판정이 없으면(`None`) **막는다.** 「판정기가 죽었으니 통과」는
        #:   통제가 없는 것과 같다 — 전환의 방향은 언제나 닫는 쪽이다.
        if decision is None:
            exc = HTTPException(status_code=503,
                                detail="접근 판정을 수행하지 못했습니다. 잠시 후 다시 시도해 "
                                       "주십시오.")
            _audit_denied(p, action, release_id, ds, path, exc, None)
            raise exc
        if not decision.allowed:
            #: 관리 API 는 **사람의 표면**이다. 앱 경로처럼 고정 문장으로 접지 않고,
            #: 설계 §3.3 은폐 경계표를 그대로 쓴다:
            #:
            #:     볼 수 없는 자원        → 404 (존재를 알리지 않는다)
            #:     볼 수는 있으나 쓰기만 → 403 (「왜 안 되는지」를 말해야 고칠 수 있다)
            #:
            #: ★ 그 둘을 가르려면 **읽기로 한 번 더 물어본다.** 읽기도 막히면 그 사람에게
            #:   그 자원은 «없는 것» 이고, 읽기가 되면 «있는데 못 바꾸는 것» 이다.
            #: ⚠️ 여기서 뭉개면 둘 중 하나가 반드시 틀린다 — 403 으로 뭉개면 존재가 새고,
            #:   404 로 뭉개면 권한을 고칠 방법을 아무도 모른다.
            status = 403
            if decision.reason in _CONCEAL:
                status = 404
                if mutating:
                    peek = _shadow_check(p, app_policy.READ, release_id, ds)
                    #: ★★★ [교차검토 89 ②] 보조 판정이 **실패하면 404 가 아니다.**
                    #:   404 는 「없다」인데 여기서 참인 것은 「모른다」다 — 그 둘을 뭉개면
                    #:   사용자는 자원이 사라졌다고 읽고, 장애는 조용히 묻힌다.
                    if peek is None:
                        exc = HTTPException(
                            status_code=503,
                            detail="접근 판정을 수행하지 못했습니다. 잠시 후 다시 시도해 "
                                   "주십시오.")
                        _audit_denied(p, action, release_id, ds, path, exc, decision)
                        raise exc
                    if peek.allowed:
                        status = 403
            exc = HTTPException(
                status_code=status,
                detail=decision.message or "이 자료에 대한 권한이 없습니다.")
            _audit_denied(p, action, release_id, ds, path, exc, decision)
            raise exc
        return

    #: 롤백 경로 — 기존 판정이 강제한다(전환 이전과 같은 동작).
    #: ⚠️⚠️ 여기서는 기존 판정이 **강제자**이므로 그것이 죽으면 통과시킬 수 없다.
    #:   「판정을 못 했다」는 «허용» 이 아니라 «모른다» 이고, 모르는 것을 통과시키면
    #:   통제가 없는 것과 같다 — 방향은 언제나 닫는 쪽이다.
    if old_ok is None:
        exc = HTTPException(status_code=503,
                            detail="접근 판정을 수행하지 못했습니다. 잠시 후 다시 시도해 "
                                   "주십시오.")
        _audit_denied(p, action, release_id, ds, path, exc, decision)
        raise exc
    if not old_ok and old_exc is not None:
        _audit_denied(p, action, release_id, ds, path, old_exc, decision)
        raise old_exc


#: 존재를 숨겨야 하는 사유 — 「그 자원이 있다」가 새면 안 되는 것들.
#: ★ 기존 판정(`api/deps`)이 쓰던 은폐 경계표와 같은 규칙이다(설계 §3.3).
_CONCEAL = frozenset({
    "SCOPE_DENIED", "CONTEXT_MISMATCH", "RESOURCE_UNBOUND", "RESOURCE_RETIRED",
    "TOKEN_APP_MISMATCH", "TOKEN_SCOPE_MISMATCH", "TOKEN_CONTEXT_MISMATCH",
})


def _audit_denied(p: Principal, action: str, release_id: str,
                  ds: Optional[Dict[str, Any]], path: str,
                  exc: HTTPException, decision) -> None:
    """★★★ [G1-B05] **거부를 남긴다.** 앱 데이터 거부는 지금까지 아무 데도 기록되지 않았다.

    `api/deps._deny` 는 `HTTPException` 을 던질 뿐이고, 그래서 「누가 어느 앱 데이터에
    접근하려다 막혔는가」에 아무도 답할 수 없었다 — 거부된 시도가 침해 신호인데 그것이
    조용했다(`core/enterprise_context/audit` 모듈이 존재하는 이유가 그것이다).

    ⚠️ **허용은 전건 기록하지 않는다.** 그러면 로그가 폭증해 정작 봐야 할 거부가 묻힌다
      (`audit.py` 가 「정상 조회 전건은 기록하지 않는다」로 못박은 규약). 허용 쪽은
      `policy_shadow` 가 세고, 구조 변경은 `decision_ledger` 가 남긴다.
    ⚠️ 기록 실패가 거부를 성공으로 바꾸지 않는다 — 삼키되 요청은 그대로 막힌다."""
    try:
        from core.enterprise_context import audit
        uid = (p.user_id or "").strip()
        audit.record(
            event=(audit.ACCESS_DENIED_UNAUTHENTICATED if not uid
                   else audit.ACCESS_DENIED_SCOPE_MISMATCH),
            resource_type="app_dataset" if ds else "release",
            #: ⚠️ 은폐는 응답이지 기록이 아니다 — 실제 대상을 남긴다(설계 §3.2).
            resource_id=str((ds or {}).get("dataset_id") or release_id or ""),
            actor=uid,
            actor_scopes=getattr(p.scope, "readable_dept_ids", ()) or (),
            outcome="denied",
            reason=f"{action} 거부 (HTTP {exc.status_code})",
            #: PDP 사유를 함께 남긴다 — 이행 기간에 «두 판정이 무엇을 달리 봤는가» 를
            #: 사후에 되짚을 수 있는 유일한 기록이다.
            detail=f"path={path} release={release_id} "
                   f"pdp={(decision.reason if decision is not None else 'n/a')}")
    except Exception:
        pass


def _audience_for_release(release_id: str) -> str:
    """이 릴리스의 자료가 **어느 평면에 있는가** — 청중 이름으로 답한다.

    ## ⚠️⚠️ 평면을 안 고르면 「200 인데 0건」이 된다 (2026-08-24 실측)

    업무 키트 앱은 **시연 평면**에 물질화된다(운영 평면은 승격의 일이다). 그런데 이
    라우트는 운영 평면 하나만 보고 있었다. 그래서 데이터셋 6종을 실제로 만든 뒤에도
    목록이 **비어 있었다** — 「우리 회사에 자료가 없다」로 읽히는 화면이다.

    ⚠️ 상태를 못 읽으면 청중이 빈 문자열이다 — 「모르면 운영」으로 접지 않는다.
      그러면 후보 판이 운영 자료를 만진다."""
    from core import app_preview
    from core.program_lifecycle import program_lifecycle

    state = str(program_lifecycle.get_status(str(release_id or "")).get("status") or "")
    return app_preview.audience_for_state(state)


def _plane_of(audience: str):
    """청중 → 데이터 평면.

    ★★★ 운영 평면은 **모듈 전역 이름**(`app_data_service`)으로 돌려준다 — 시험이 그
      이름을 갈아끼워 격리한다. `app_preview.app_data_for()` 는 core 싱글턴을 직접
      돌려주므로 여기서 쓰면 주입이 무력해지고, 실제로 10건이 404 로 뒤집혔다.
    ⚠️ 알 수 없는 청중은 **404 로 은폐**한다 — 「그것이 존재하는데 상태가 이상하다」를
      알려 주지 않는다(`app_data_runtime._audience_of` 와 같은 규약)."""
    from core import app_preview

    if app_preview.is_preview(audience):
        return app_preview.preview_app_data()
    if app_preview.normalize_audience(audience) == app_preview.AUDIENCE_OPERATIONAL:
        return app_data_service
    raise HTTPException(status_code=404, detail="사용할 수 없는 릴리스 상태입니다.")


def _plane_for_release(release_id: str):
    """릴리스 하나가 쓰는 평면. **고르는 것은 여기 한 곳이다.**"""
    return _plane_of(_audience_for_release(release_id))


def _find_dataset_any_plane(dataset_id: str):
    """데이터셋 하나와 **그것이 있던 평면**. 없으면 `(None, None)`.

    ★★★ 찾은 뒤 **권위와 대조한다.** 릴리스 상태가 말하는 청중과 실제로 찾은 평면의
      청중이 다르면 없는 것으로 답한다 — 「어느 서랍에 있든 열어 준다」가 되면 승격
      경계가 사라지고, 후보 판의 자료가 운영 경로로 새어 나온다.
    ⚠️ 두 평면을 뒤지는 것은 **탐색**이지 판정이 아니다. 판정은 아래 대조 한 줄이다."""
    from core import app_preview

    planes = ((app_preview.AUDIENCE_OPERATIONAL, app_data_service),
              (app_preview.AUDIENCE_PREVIEW, app_preview.preview_app_data()))
    for audience, svc in planes:
        try:
            ds = svc.get_dataset(dataset_id)
        except Exception:                        # pragma: no cover - 평면 조회 실패
            continue
        if not ds:
            continue
        if _audience_for_release(str(ds.get("release_id") or "")) != audience:
            #: ⚠️ 상태가 말하는 평면이 아니다 — 승격 중이거나 어긋난 자료다. 은폐한다.
            return None, None
        return ds, svc
    return None, None


def _require_dataset(dataset_id: str) -> Tuple[Dict[str, Any], Any]:
    """★ 데이터셋과 **그 평면**을 함께 돌려준다.

    ⚠️ 평면을 함께 주지 않으면 호출부가 모듈 전역 서비스를 쓰고, 그것은 늘 운영 평면이다
      — 후보 판의 레코드를 읽으면 조용히 0건이 된다."""
    ds, svc = _find_dataset_any_plane(dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="데이터셋을 찾을 수 없습니다.")
    return ds, svc


def _assert_personal_owner(ds: Dict[str, Any], p: Principal, row_creator: str = "") -> None:
    """★ `personal` 앱의 데이터는 만든 사람의 것이다(설계 §5-1).

    부서 범위로 열면 **개인 편의 도구가 부서 공유물이 된다** — 사용자가 그렇게 알고 만든 것이
    아니다. 설계서 §2-4 모순 2 가 같은 갈래를 지적했다."""
    if (ds.get("app_class") or "") != "personal":
        return
    if p.scope.unrestricted:
        return
    owner = row_creator or ds.get("created_by") or ""
    if owner and owner != (p.user_id or ""):
        raise HTTPException(
            status_code=403,
            detail="개인용 앱의 데이터는 만든 사람만 볼 수 있습니다.")


def _ledger(event_type: str, dataset_id: str, actor_id: str, decision: str,
            rationale: str = "", evidence: Optional[List[Any]] = None,
            tenant_id: str = "tenant_default", scope: str = "") -> None:
    """구조 변경만 원장에 남긴다(§6). **실패를 삼키지 않는다** — 감사 기록이 조용히
    누락되면 승인 이력 없는 승인이 생긴다(`core/decision_ledger.append` 의 계약)."""
    from core.decision_ledger import decision_ledger
    decision_ledger.append(
        event_type, "app_dataset", dataset_id,
        actor_type="user", actor_id=actor_id,
        decision=decision, rationale=rationale,
        evidence_refs=evidence or [],
        tenant_id=tenant_id or "tenant_default", enterprise_scope_id=scope or "")


# ── 요청 모델 ─────────────────────────────────────────────────────────────
# ⚠️ pydantic v2 다. `class Config: fields = {...}` 는 **조용히 무시된다** — v1 문법이라
#   오류도 나지 않고 별칭만 사라진다. 그러면 생성기가 보낸 `schema` 키가 버려지고 «필드 선언이
#   없다» 로 거부돼, 원인이 별칭이라는 것을 아무도 못 찾는다. v2 문법으로 쓴다.
# ⚠️ 필드명이 `schema_def` 인 이유: `schema` 는 BaseModel 의 예약 이름이다.
class DatasetCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    release_id: str
    name: str
    schema_def: Any = Field(default=None, alias="schema")
    label: str = ""
    app_class: str = ""
    owner_dept_id: str = ""
    scope_node_id: str = ""
    tenant_id: str = "tenant_default"


class SchemaUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_def: Any = Field(default=None, alias="schema")


class RecordWrite(BaseModel):
    payload: Dict[str, Any]


# ── 데이터셋 ──────────────────────────────────────────────────────────────
@router.post("/datasets")
async def create_dataset(req: DatasetCreate, p: Principal = Depends(current_principal)):
    actor = _actor(p)
    _enforce(p, "manage", req.release_id, path="POST /datasets")
    #: ★ 만드는 자리도 **릴리스가 정한 평면**이다 — 후보 판의 데이터셋을 운영 평면에
    #:   만들면 승격을 건너뛴 자료가 생긴다.
    _svc = _plane_for_release(req.release_id)
    try:
        ds = _svc.create_dataset(
            req.release_id, req.name, req.schema_def, actor_id=actor,
            label=req.label, app_class=req.app_class, owner_dept_id=req.owner_dept_id,
            scope_node_id=req.scope_node_id, tenant_id=req.tenant_id or "tenant_default")
    except AppDataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _ledger("APP_DATASET_CREATED", ds["dataset_id"], actor,
            decision=f"{req.release_id} 앱에 데이터셋 '{req.name}' 생성",
            rationale=f"필드 {len(ds['schema'].get('fields', []))}개",
            evidence=[{"release_id": req.release_id, "name": req.name}],
            tenant_id=ds.get("tenant_id", ""), scope=ds.get("scope_node_id", ""))
    return ds


@router.get("/datasets")
async def list_datasets(release_id: str = Query(..., description="어느 앱의 데이터셋인가"),
                        include_retired: bool = False,
                        p: Principal = Depends(current_principal)):
    _enforce(p, "read", release_id, path="GET /datasets")
    _svc = _plane_for_release(release_id)
    rows = _svc.list_datasets(release_id, include_retired=include_retired)
    out = []
    for ds in rows:
        if (ds.get("app_class") or "") == "personal" and not p.scope.unrestricted \
                and ds.get("created_by") and ds["created_by"] != (p.user_id or ""):
            continue          # 목록에서는 조용히 감춘다(단건은 403 으로 이유를 말한다)
        ds["record_count"] = _svc.count_records(ds["dataset_id"])
        out.append(ds)
    return {"datasets": out, "count": len(out), "release_id": release_id}


@router.get("/datasets/by-name")
async def get_dataset_by_name(release_id: str = Query(...), name: str = Query(...),
                              p: Principal = Depends(current_principal)):
    """★ 브리지가 쓰는 경로 — 앱은 이름만 말하고 `release_id` 는 부모가 붙인다."""
    _enforce(p, "read", release_id, path="GET /datasets/by-name")
    _svc = _plane_for_release(release_id)
    ds = _svc.find_dataset(release_id, name)
    if not ds:
        raise HTTPException(status_code=404, detail=f"데이터셋을 찾을 수 없습니다: {name}")
    _assert_personal_owner(ds, p)
    ds["record_count"] = _svc.count_records(ds["dataset_id"])
    return ds


@router.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: str, p: Principal = Depends(current_principal)):
    ds, _svc = _require_dataset(dataset_id)
    _enforce(p, "read", ds["release_id"], ds, path="GET /datasets/{id}")
    _assert_personal_owner(ds, p)
    ds["record_count"] = _svc.count_records(dataset_id)
    return ds


@router.put("/datasets/{dataset_id}/schema")
async def update_schema(dataset_id: str, req: SchemaUpdate,
                        p: Principal = Depends(current_principal)):
    ds, _svc = _require_dataset(dataset_id)
    actor = _actor(p)
    _enforce(p, "manage", ds["release_id"], ds, path="PUT /datasets/{id}/schema")
    _assert_personal_owner(ds, p)
    try:
        out = _svc.update_schema(dataset_id, req.schema_def, actor_id=actor)
    except AppDataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _ledger("APP_DATASET_SCHEMA_CHANGED", dataset_id, actor,
            decision=f"'{ds['name']}' 스키마 변경",
            rationale=(f"추가 {out.get('added_fields') or '없음'} · "
                       f"제거 {out.get('removed_fields') or '없음'}"),
            evidence=[{"added": out.get("added_fields"), "removed": out.get("removed_fields")}],
            tenant_id=ds.get("tenant_id", ""), scope=ds.get("scope_node_id", ""))
    # ⚠️ 제거된 필드가 있으면 **응답에서 드러낸다.** 기존 레코드의 그 값은 조회에서 사라진다.
    if out.get("removed_fields"):
        out["warning"] = (f"필드 {len(out['removed_fields'])}개가 선언에서 빠졌습니다 — "
                          f"기존 레코드의 해당 값은 화면에서 보이지 않게 됩니다(데이터는 남아 "
                          f"있습니다): {', '.join(out['removed_fields'])}")
    return out


@router.delete("/datasets/{dataset_id}")
async def retire_dataset(dataset_id: str, p: Principal = Depends(current_principal)):
    """폐지. **레코드는 지우지 않는다**(설계 §4-2)."""
    ds, _svc = _require_dataset(dataset_id)
    actor = _actor(p)
    _enforce(p, "manage", ds["release_id"], ds, path="DELETE /datasets/{id}")
    _assert_personal_owner(ds, p)
    try:
        out = _svc.retire_dataset(dataset_id, actor_id=actor)
    except AppDataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _ledger("APP_DATASET_RETIRED", dataset_id, actor,
            decision=f"'{ds['name']}' 폐지",
            rationale="레코드는 보존한다 — 원장이 가리키는 대상이 사라지면 감사 증적이 아니다",
            evidence=[{"record_count": _svc.count_records(dataset_id)}],
            tenant_id=ds.get("tenant_id", ""), scope=ds.get("scope_node_id", ""))
    return out


# ── 레코드 ────────────────────────────────────────────────────────────────
@router.get("/datasets/{dataset_id}/records")
async def list_records(dataset_id: str, limit: int = 200, offset: int = 0,
                       include_deleted: bool = False,
                       p: Principal = Depends(current_principal)):
    ds, _svc = _require_dataset(dataset_id)
    _enforce(p, "read", ds["release_id"], ds, path="GET /records")
    _assert_personal_owner(ds, p)
    # `personal` 앱은 자기 것만 — 데이터셋 소유자와 레코드 작성자가 다를 수 있다.
    creator = ""
    if (ds.get("app_class") or "") == "personal" and not p.scope.unrestricted:
        creator = (p.user_id or "")
    rows, total = _svc.list_records(
        dataset_id, limit=limit, offset=offset,
        include_deleted=include_deleted, created_by=creator)
    # ★ 목록 길이와 총계를 함께 준다 — 화면이 `len(rows)` 를 «전부» 로 읽으면 상한에 걸린
    #   순간 사용자는 「우리 데이터는 200건」으로 믿는다.
    return {"records": rows, "count": len(rows), "total": total,
            "limit": limit, "offset": offset,
            "truncated": (offset + len(rows)) < total,
            "schema": ds.get("schema", {})}


@router.post("/datasets/{dataset_id}/records")
async def create_record(dataset_id: str, req: RecordWrite,
                        p: Principal = Depends(current_principal)):
    ds, _svc = _require_dataset(dataset_id)
    actor = _actor(p)
    _enforce(p, "write", ds["release_id"], ds, path="POST /records")
    _assert_personal_owner(ds, p)
    try:
        return _svc.create_record(dataset_id, req.payload, actor_id=actor)
    except AppDataError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _require_record_in(dataset_id: str, record_id: str, svc: Any = None) -> Dict[str, Any]:
    """★★★ [G1-B01-B] **레코드가 «그» 데이터셋의 것인지 확인한다.**

    ## 왜 경로에 데이터셋이 있어야 하는가

    종전 경로는 `PUT /records/{record_id}` 였다 — **데이터셋을 말하지 않는다.** 그래서 앱이
    자기가 이름 붙인 데이터셋이 아니라 **아무 레코드 id** 를 가리킬 수 있었고, 현행 판정
    (`assert_release_*`)은 **사용자 기준**이라 그 사용자가 볼 수 있는 다른 앱의 레코드면
    통과한다 — 앱 A 가 사용자를 대리해 앱 B 의 데이터를 고치는
    **혼동된 대리인(confused deputy)** 이다.

    ★ 신규 PDP 는 앱 증명의 `release_id` 대조로 이것을 막는다. 그러나 **브리지는 전환
      전에도 안전해야 하므로** 경로 자체를 데이터셋에 매는 것이 정답이다. 판정기 교체를
      기다리는 통제는 통제가 아니다.

    ⚠️ 어긋나면 **404** 다. 403 으로 답하면 「그 레코드는 있는데 여기 것이 아니다」가 되어
      **다른 데이터셋의 존재가 새어나간다**(설계 §3.3 은폐 경계표와 같은 규칙)."""
    #: ★ 데이터셋이 있던 **그 평면**에서 읽는다 — 안 주면 늘 운영 평면이다.
    rec = (svc or app_data_service).get_record(record_id)
    if not rec or str(rec.get("dataset_id") or "") != str(dataset_id or ""):
        raise HTTPException(status_code=404, detail="레코드를 찾을 수 없습니다.")
    return rec


@router.get("/datasets/{dataset_id}/records/{record_id}")
async def get_record(dataset_id: str, record_id: str,
                     p: Principal = Depends(current_principal)):
    ds, _svc = _require_dataset(dataset_id)
    rec = _require_record_in(dataset_id, record_id, _svc)
    _enforce(p, "read", ds["release_id"], ds, path="GET /records/{id}")
    _assert_personal_owner(ds, p, row_creator=rec.get("created_by", ""))
    return rec


@router.put("/datasets/{dataset_id}/records/{record_id}")
async def update_record(dataset_id: str, record_id: str, req: RecordWrite,
                        p: Principal = Depends(current_principal)):
    ds, _svc = _require_dataset(dataset_id)
    rec = _require_record_in(dataset_id, record_id, _svc)
    actor = _actor(p)
    _enforce(p, "write", ds["release_id"], ds, path="PUT /records/{id}")
    _assert_personal_owner(ds, p, row_creator=rec.get("created_by", ""))
    try:
        return _svc.update_record(record_id, req.payload, actor_id=actor)
    except AppDataError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/datasets/{dataset_id}/records/{record_id}")
async def delete_record(dataset_id: str, record_id: str,
                        p: Principal = Depends(current_principal)):
    """논리 삭제. 물리 삭제는 제공하지 않는다(설계 §4-2)."""
    ds, _svc = _require_dataset(dataset_id)
    rec = _require_record_in(dataset_id, record_id, _svc)
    actor = _actor(p)
    _enforce(p, "delete", ds["release_id"], ds, path="DELETE /records/{id}")
    _assert_personal_owner(ds, p, row_creator=rec.get("created_by", ""))
    try:
        return _svc.delete_record(record_id, actor_id=actor)
    except AppDataError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ⚠️⚠️ **데이터셋을 말하지 않는 레코드 경로(`/records/{record_id}`)는 두지 않는다.**
#   위 §`_require_record_in` 의 이유로 그 모양은 **안전하게 만들 수 없다** — 호출자가
#   데이터셋을 말하지 않으므로 소속을 대조할 대상이 없다.
#   ★ 제품 코드에 호출자가 없었다(프론트·생성기 전수 확인, 2026-08-14). 시험 둘만 쓰고
#     있었고 함께 옮겼다. 「쓰는 데가 없지만 남겨 둔다」는 것은 **다음 사람이 그 경로를
#     쓰도록 남겨 두는 것**이다.
