"""★★★ [G1-B 3.5 / I-3] **Host Runtime 전용 데이터 평면.** prefix `/api/v1/appdata/runtime`.

교차검토 `[G1-B-I3-REVIEW-82]` 의 라우트 경계 권고:

> 일반 관리/콘솔 AppData API 에 `proof 없음 → session 판정` 폴백을 추가하지 않는다.
> 브리지는 `/api/v1/appdata/runtime/*` 전용 경로만 사용하고 이 경로는 앱 증명을 **필수**로
> 한다. 같은 라우트에서 증명 누락을 session 으로 내리면 Host Runtime capability 를
> **헤더 하나 생략해** 우회할 수 있다.

## 이 라우터가 기존 `app_data_control` 과 다른 점

| | 관리 API(`/appdata/*`) | **런타임 API(여기)** |
|---|---|---|
| 부르는 주체 | 사람(콘솔·생성기) | **생성 앱**(브리지를 통해) |
| 신원 | 세션 | 세션 **+ 앱 증명** |
| 증명 없음 | 해당 없음 | **차단**(세션으로 내려가지 않는다) |
| 자원 지정 | `dataset_id` | **데이터셋 «이름»** — 릴리스는 증명에서 나온다 |
| 판정 | 기존 판정 강제 · PDP 관측 | **PDP 강제** · 기존 판정 관측 |
| 응답 | 행 전체 | **허용목록 투영** |

★ 마지막 두 줄이 요점이다.

· **판정이 뒤집혀 있다.** 이 경로는 신설이므로 «지키던 동작» 이 없다 — 보존할 것이 없는
  곳에서 낡은 판정을 강제할 이유가 없다. 대신 기존 판정을 **나란히 관측**해서 전환 게이트의
  표본을 만든다(그것이 [4] 카나리가 필요로 하는 바로 그 표본이다).
  ⚠️ 관리 API 의 이중 판정은 **그대로 둔다** — 그쪽은 지키던 동작이 있다.

· **응답을 서버가 깎는다.** 브리지도 깎지만(`hostRuntimeWire.projectRecord`), 그것은 두 번째
  그물이다. 첫 번째 그물이 서버에 있어야 브리지 결함 하나가 곧 조직·계정 식별자 유출이
  되지 않는다.

LLM 0콜.
"""
import dataclasses
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from api.deps import Principal, current_principal, viewing_context, visibility_block_reason
from core import (app_contract_gate, app_policy, app_proof, host_runtime_provider as prov,
                  host_runtime_sdk as sdk, host_runtime_wire as wire)
from core import app_preview
from core.app_capability_token import AppTokenError, app_capability_tokens
from core.app_data import AppDataError, AppDataIntegrityError, app_data_service

router = APIRouter(prefix="/api/v1/appdata/runtime")

#: 앱 증명을 싣는 헤더. ⚠️ 이 값은 **부모 창의 메모리에만** 있다 — iframe 에 건너가지 않는다.
PROOF_HEADER = "X-App-Proof"

#: ★★★ 「이 판은 사라졌다」로 답할 사유들 — `410` 이고 **재발급으로 되살아나지 않는다.**
#: ⚠️ 만료(`401`)와 나누는 이유: 만료는 새 증명을 받아 **같은 프레임**을 계속 쓰지만,
#:   여기는 지금 도는 코드가 **낡은 코드**다. 새 증명을 주면 옛 앱이 새 증명으로 계속 돈다.
_STALE_APP_REASONS = (app_policy.DENY_TOKEN_MANIFEST_MISMATCH,
                      app_policy.DENY_TOKEN_CONTRACT_MISMATCH,
                      app_policy.DENY_TOKEN_MATERIALIZATION_MISMATCH)

#: HTTP 상태로 접는 표. ★ 존재를 숨기는 코드는 404 다.
_STATUS = {
    sdk.ERR_NOT_FOUND: 404,
    sdk.ERR_FORBIDDEN: 403,
    sdk.ERR_EXPIRED: 401,
    sdk.ERR_INVALID: 400,
    sdk.ERR_UNAVAILABLE: 503,
}


class ProofRequest(BaseModel):
    """★★★ **`release_id` 하나만 받는다.**

    ⚠️ `capabilities`·`tenant_id`·`scope_node_id` 를 받지 않는다. 받는 순간 증명은
      「이 화면이 이 앱을 열고 있다」는 **사실**이 아니라 「부르는 쪽이 원한다고 말한 권한」이
      되고, 부모 코드의 실수 하나가 곧 권한 상승이 된다."""
    release_id: str


class RecordWrite(BaseModel):
    payload: Dict[str, Any]


# ── 공통 ──────────────────────────────────────────────────────────────────
def _fail(code: str, *, audit_reason: str = "", actor: str = "", target: str = "",
          path: str = "", status: int = 0) -> HTTPException:
    """앱에게는 **고정 문장**만, 감사에는 **실제 사유**를 남긴다.

    ★★★ 교차검토 계약 (8) — 「정확한 거부 사유는 서버 감사에만 남기고 iframe 에는 SDK 고정
      오류로 접는다.」 사유를 그대로 돌려주면 「어느 조직 범위 밖」·「남의 앱」 같은 사실이
      새어나가고, 그것은 **볼 수 없는 자원이 존재한다**는 정보다."""
    if audit_reason:
        try:
            from core.enterprise_context import audit
            audit.record(
                event=(audit.ACCESS_DENIED_UNAUTHENTICATED if not actor
                       else audit.ACCESS_DENIED_SCOPE_MISMATCH),
                resource_type="app_runtime", resource_id=target or path,
                actor=actor, outcome="denied",
                reason=f"런타임 거부 ({code})",
                #: ⚠️ 은폐는 응답이지 기록이 아니다 — 실제 사유를 남겨야 추적할 수 있다.
                detail=f"path={path} reason={audit_reason}")
        except Exception:
            pass
    return HTTPException(status_code=status or _STATUS.get(code, 403),
                         detail=wire.ERROR_MESSAGE_KO.get(code, wire.ERROR_MESSAGE_KO[
                             sdk.ERR_NOT_FOUND]))


def _require_proof(request: Request, p: Principal) -> Dict[str, Any]:
    """앱 증명을 꺼내 온다. **없으면 차단한다 — 세션으로 내려가지 않는다.**

    ⚠️⚠️ 여기서 「증명이 없으면 세션 권한으로」를 허용하면 앱은 **헤더 하나를 생략해서**
      사람의 넓은 권한으로 데이터를 만질 수 있다. 그것이 이 라우터가 따로 있는 이유 전부다."""
    raw = (request.headers.get(PROOF_HEADER, "") or "").strip()
    if not raw:
        raise _fail(sdk.ERR_FORBIDDEN, audit_reason="앱 증명 없음", actor=(p.user_id or ""),
                    path=str(request.url.path))
    #: ★★★ [교차검토 지적 3] `quiet=True` — **해석 단계에서 «사용됨» 을 남기지 않는다.**
    #:   해석은 「토큰이 존재한다」까지만 증명하고 그 뒤에 PDP 가 거부할 수 있다. 먼저
    #:   기록하면 보안 감사에서 「데이터를 만졌다」와 「만지려다 막혔다」가 같은 줄이 되고,
    #:   카나리 증거도 왜곡된다. 성공 사용은 `_judge` 가 허용을 확정한 뒤 남긴다.
    rec = app_capability_tokens.resolve(raw, quiet=True)
    if rec is None:
        #: 없는 증명과 회수된 증명을 구분하지 않는다.
        raise _fail(sdk.ERR_FORBIDDEN, audit_reason="앱 증명을 확인할 수 없음",
                    actor=(p.user_id or ""), path=str(request.url.path))
    #: ★★★ [2026-08-14 카나리 실측] **만료를 여기서 되돌려보내지 않는다.**
    #
    #  종전에는 문 앞에서 401 로 끊었다. 밖에서 보이는 결과는 같지만 그 요청은 **판정에
    #  도달하지 못했고**, 그래서 전환 게이트의 「만료된 증명」 표본이 **영원히 0** 이었다 —
    #  실제로 만료를 태워 보고도 게이트는 「눌러 보지 않았다」고 말했다.
    #
    #  ★ `resolve()` 가 만료를 `None` 이 아니라 `expired=True` 로 돌려주는 이유가 바로
    #    이것이다: 「그런 증명이 없다」와 「만료됐다」는 **판정기가 구분해야** 하는 사실이다.
    #    여기서 가로채면 그 설계가 무의미해진다.
    return rec


def _judge(p: Principal, proof: Dict[str, Any], action: str, *, op: str,
           path: str) -> None:
    """★★★ **정책 결정점이 강제한다.** 기존 판정은 나란히 돌려 관측만 한다.

    관측이 있어야 [5] 전환 게이트의 「여섯 작업 × 허용·거부」와 부정 시나리오 표본이 쌓인다.
    ⚠️ 관측 실패가 요청을 죽이지 않는다 — 다만 **세어서** 드러낸다.

    ## ★★★ [2026-08-14 교차검토 86 ①] **이 함수는 데이터셋보다 먼저 돈다**

    종전에는 `_dataset()` 으로 이름을 먼저 풀고 그 결과를 판정에 넘겼다. 그러면 증명이
    만료됐을 때 **있는 이름은 401, 없는 이름은 404** 가 되어, 만료된 증명 하나로
    **데이터셋 이름을 열거**할 수 있었다. 관측 표본을 만들려다 경계를 약화시킨 것이다.

    ⚠️ 그래서 판정은 **데이터셋을 모른 채** 끝난다. 자원 상태(폐지된 데이터셋)는 판정
      이후 `_assert_active()` 가 따로 본다 — 그때는 이미 증명이 유효함이 확정돼 있다."""
    from core.policy_shadow import policy_shadow

    release_id = str(proof.get("release_id", "") or "")
    try:
        ctx = viewing_context(p)
    except HTTPException:
        ctx = {}
    rel = app_proof.read_release(release_id)
    #: 프로그램 사용 중단(`program_usable`)은 `resource_scope` 안에서 이미 반영된다.
    res = app_proof.resource_scope(rel, release_id)
    facts = app_proof.app_facts(rel, release_id)
    #: ★★★ [I-4 3단계] **지금의** 계약·물질화 지문을 산출해 판정에 넘긴다.
    #:   ⚠️ 발급 때 한 번 보고 마는 것이 아니다 — 계약이 개정되거나 결속이 달라지면
    #:     **다음 요청에서** 그 프레임이 죽어야 한다.
    #: ★★★ [F-3] **그 증명이 만질 평면**으로 지문을 낸다. Preview 증명인데
    #:   운영 평면의 지문을 대조하면 첫 요청부터 「이 판은 사라졌다」가 된다.
    c_fp, m_fp = app_contract_gate.sealed_pair(
        rel, release_id, plane=app_preview.app_data_for(_audience_of(proof)))
    facts = dataclasses.replace(facts, contract_fingerprint=c_fp,
                                materialization_fingerprint=m_fp)
    subject = app_policy.Subject(
        user_id=(p.user_id or ""), scope=p.scope, ctx=ctx,
        session_id=(p.session_id or ""),
        blocked_reason=visibility_block_reason(p),
        #: ★ 여기서만 토큰 축이 켜진다. 관리 API 는 계속 `session` 이다.
        via="app_token", token=proof)
    decision = app_policy.decide(subject, res, action, app=facts)

    #: ── 관측: 기존 판정이라면 어떻게 답했을까 ────────────────────────────
    try:
        from api.deps import assert_release_readable, assert_release_writable
        old_ok = True
        try:
            if action in (app_policy.WRITE, app_policy.DELETE, app_policy.MANAGE):
                assert_release_writable(p, release_id)
            else:
                assert_release_readable(p, release_id)
        except HTTPException:
            old_ok = False
        policy_shadow.observe(path=path, action=action, old_allowed=old_ok,
                              new_allowed=decision.allowed, new_reason=decision.reason,
                              actor=(p.user_id or ""), resource_id=release_id, op=op)
    except Exception as e:                                    # pragma: no cover
        policy_shadow.error(action=action, exc_type=type(e).__name__)

    if not decision.allowed:
        #: ★★★ [2026-08-14 교차검토 84] **앱 선언이 바뀐 것은 «만료» 가 아니다.**
        #
        #  둘 다 앱에게는 `EXPIRED` 로 보이지만 **부모가 할 일이 다르다**:
        #    · 만료      → 새 증명을 받아 **같은 프레임**을 계속 쓴다.
        #    · 선언 변경 → 지금 도는 코드가 **낡은 코드**다. 새 증명을 주면 «옛 앱이 새
        #                  증명으로 계속 도는» 상태가 되고, 그것이 결속을 우회하는 길이다.
        #  그래서 상태코드를 나눈다 — 410 은 「이 판은 사라졌다」이고, 브리지는 그것을 보면
        #  재발급하지 않고 **프레임을 버린다.**
        raise _fail(sdk.app_error_code(decision.reason),
                    audit_reason=decision.reason, actor=(p.user_id or ""),
                    target=release_id, path=path,
                    #: ★ 계약·물질화 변경도 «이 판은 사라졌다» 이므로 410 이다 —
                    #:   재발급으로 되살리면 **옛 코드가 새 증명으로 계속 돈다.**
                    status=(410 if decision.reason in _STALE_APP_REASONS else 0))
    #: ★ **허용이 확정된 뒤** 성공 사용을 남긴다(§`record_use`).
    try:
        app_capability_tokens.record_use(proof)
    except Exception:
        pass


def _release_state(release_id: str) -> str:
    """이 릴리스가 지금 **후보인가 운영인가.**

    ⚠️ 판독 실패를 「운영」으로 접지 않는다 — 그러면 상태를 못 읽는 순간 후보 판이
      운영 데이터를 만진다. 빈 문자열은 호출부가 거부한다."""
    try:
        from core.program_lifecycle import program_lifecycle

        return str(program_lifecycle.get_status(str(release_id or "")).get("status", ""))
    except Exception:
        return ""


def _audience_of(proof: Dict[str, Any]) -> str:
    """이 증명이 **지금도** 자기 청중과 맞는가.

    ★★★ 발급 시점에 맞았다는 것으로는 부족하다. 후보였던 판이 운영으로 승격되면
      **그때 발급된 Preview 증명이 운영 데이터를 가리키게 된다** — 그것이 교차 사용의
      실제 경로다. 그래서 요청마다 지금 상태에서 다시 유도해 봉인 값과 대조한다.
    ⚠️ 어긋나면 «다시 열면 된다»(`EXPIRED`)로 답한다 — 부모가 새 증명을 받으면 곧바로
      풀린다. 「없다」로 접으면 앱이 화면에서 그 표를 지운다."""
    rid = str(proof.get("release_id", "") or "")
    now_audience = app_preview.audience_for_state(_release_state(rid))
    if not now_audience:
        #: ⚠️⚠️ **404 다(은폐).** 끈 프로그램·격리된 판·못 읽은 상태를 503 으로 답하면
        #:   「그것이 존재하는데 서버가 아프다」를 알려 주는 셈이 된다. 기존 계약은
        #:   「없거나 못 보거나」를 같은 404 로 답하는 것이고, 여기서만 다르게 답하면
        #:   그 차이가 곧 신호다.
        raise _fail(sdk.ERR_NOT_FOUND, audit_reason="사용할 수 없는 릴리스 상태",
                    target=rid)
    try:
        app_preview.assert_audience_match(sealed=proof.get("audience"),
                                          requested=now_audience)
    except app_preview.PreviewBoundaryError as e:
        #: ⚠️ 어느 쪽으로 어긋났는지는 앱에 말하지 않는다 — 감사에만 남긴다.
        raise _fail(sdk.ERR_EXPIRED, audit_reason=f"청중 불일치: {str(e)[:120]}",
                    target=rid)
    return now_audience


def _plane(proof: Dict[str, Any]):
    """이 증명이 만질 수 있는 **데이터 평면 하나.**

    ★★★ 호출부가 «어느 DB 인가» 를 스스로 고르지 않는다 — 고르게 두면 언젠가 한 곳이
      잘못 고르고, 그 한 곳이 곧 경계 위반이다."""
    return app_preview.app_data_for(_audience_of(proof))


def _dataset(proof: Dict[str, Any], name: str) -> Dict[str, Any]:
    """데이터셋 «이름» → 행. **릴리스는 증명에서 나온다 — 요청이 말하지 않는다.**

    ★★★ [2.1b] 결속·판 판독 실패는 `503` 이다. ⚠️ `404`(없다)나 `400`(입력이 틀렸다)로
      접으면 **서버 상태 이상이 사용자 실수처럼 보이고**, 깨진 결속은 아무도 모른 채 남는다."""
    rel = str(proof.get("release_id", "") or "")
    try:
        ds = _plane(proof).find_dataset(rel, str(name or ""))
    except AppDataIntegrityError as e:
        raise _fail(sdk.ERR_UNAVAILABLE, audit_reason=f"무결성: {str(e)[:100]}", target=rel)
    if not ds:
        raise _fail(sdk.ERR_NOT_FOUND)
    return ds


def _fields_of(ds: Dict[str, Any]) -> Tuple[str, ...]:
    """이 릴리스의 판이 아는 필드 — 응답 투영에 쓴다."""
    return wire.schema_field_names(ds.get("schema"))


def _assert_active(ds: Dict[str, Any]) -> None:
    """폐지된 데이터셋은 없는 것으로 답한다.

    ★ 판정(`_judge`)이 아니라 여기서 보는 이유: 판정은 **데이터셋을 알기 전에** 끝나야
      한다(§`_judge` — 열거 오라클). 그리고 이 시점에는 증명이 유효함이 이미 확정돼 있으므로
      「있다/없다」를 구분해 말해도 새는 것이 없다 — **그 앱 자신의 데이터셋**이다."""
    if (ds.get("retired_at") or ""):
        raise _fail(sdk.ERR_NOT_FOUND, audit_reason=app_policy.DENY_RETIRED,
                    target=str(ds.get("dataset_id", "")))


def _assert_contract_action(proof: Dict[str, Any], ds: Dict[str, Any], need: str, *,
                            p: Principal, path: str) -> None:
    """★★★ [I-4 2단계] **2차 판정 — 이 데이터셋에 이 행동이 계약돼 있는가.**

    ## 왜 1차만으로는 부족한가 (실측)

    `app_proof.manifest_actions()` 는 매니페스트의 모든 capability 를
    `read/write/delete/manage` 의 **전역 합집합**으로 평탄화한다. 그래서

        orders.read + secrets.update  →  전역 read + write

    가 되고, 1차 판정에는 `orders` 에 대한 write 를 막을 근거가 **없다.**
    데이터셋별 권한이 아니었던 것이다.

    ## ⚠️ 순서를 바꾸지 않는다

    이 검사는 **1차(`_judge`) 뒤**다. 1차를 데이터셋 뒤로 옮기면 만료·타인 증명으로
    **데이터셋 이름을 열거**할 수 있게 된다(교차검토 86 에서 실제로 열렸던 구멍).

    ## 거부는 숨기지 않는다

    ⚠️ 여기서의 거부는 **그 앱 자신의 계약**에 대한 사실이므로 `FORBIDDEN` 으로 알린다 —
      숨기면 개발자가 무엇을 고쳐야 하는지 모른 채 이름을 의심한다. 반면 **계약에 없는
      이름**은 `_dataset()` 이 `NOT_FOUND` 로 답한다(존재를 알리지 않는다)."""
    allowed = _plane(proof).allowed_actions(
        str(proof.get("release_id", "") or ""), str(ds.get("dataset_id", "") or ""))
    if allowed is None:
        #: 계약 이전(레거시) 결속 — 2차 판정이 없다.
        #:
        #: ⚠️ 「모르니까 허용」이 아니다. 결속 표에 **`contract_bound=0` 이라고 적혀 있고**,
        #:   `app_data_service.contract_coverage()` 로 릴리스별 적용률을 언제든 셀 수 있다.
        #:   ★ 여기서 텔레메트리를 흘리지 않는 이유: `policy_shadow` 의 행 수는 전환 게이트의
        #:     **분모**다(`MIN_TOTAL`). 레거시 통과를 거기에 쌓으면 표본이 없는 게이트가
        #:     표본이 있는 것처럼 보이고, `error` 로 세면 게이트가 통째로 막힌다.
        return
    if need not in allowed:
        raise _fail(sdk.ERR_FORBIDDEN,
                    audit_reason=f"{app_policy.DENY_DATASET_ACTION}:{need}",
                    actor=(p.user_id or ""), target=str(ds.get("dataset_id", "")), path=path)


# ── [BDR-6] Provider Dispatch ────────────────────────────────────────────
#
# ★★★ 앱 표면은 바뀌지 않는다. 같은 `window.afs.data.list` 가 우리 DB를 읽을 수도,
#   승인된 파일 판을 읽을 수도 있다 — **앱은 어느 쪽인지 모른다.**
#
# ⚠️⚠️ 여기서 «못 읽음» 을 «없음» 으로 접지 않는다. 접으면 앱이 화면에서 그 표를
#   지우고, 사용자는 데이터가 삭제됐다고 읽는다.


def _dispatch(proof: Dict[str, Any], ds: Dict[str, Any], *, allow_stale: bool = False
              ) -> "prov.Resolution":
    """이 요청이 어디로 가는지 **매 요청 정한다.**

    ★ 한 번 통과한 것을 기억해 두지 않는다 — 그 사이에 종료된 결속이 계속 살아 있게 된다."""
    from datetime import datetime, timezone

    rel = str(proof.get("release_id", "") or "")
    binding = _plane(proof).binding_for(rel, str(ds.get("dataset_id", "") or "")) or {}
    intent = str(binding.get("source_intent") or "")
    if not intent:
        #: 계약 이전(레거시) 결속 — 종전대로 우리 DB 다.
        #: ⚠️ 이것은 **폴백이 아니다.** 「출처를 말한 적 없는 옛 결속」이라는 사실이
        #:   결속 표에 `source_intent=''` 로 적혀 있고, 그 뜻은 Native 하나뿐이었다.
        return prov.Resolution(prov.NATIVE, "", None, None, False, "")

    key = str(binding.get("enterprise_contract_key") or "")
    instance_id = str(binding.get("kit_instance_id") or "")
    dp_binding = None
    snapshots: List[Dict[str, Any]] = []
    if key and instance_id:
        try:
            from core.data_preparation.store import data_preparation_store as dp_store

            dp_binding = dp_store.active_binding(instance_id, key)
            snapshots = [r for r in dp_store.list_snapshots(instance_id)
                         if str(r.get("dataset_contract_key") or "") == key]
        except Exception as e:
            #: ⚠️ 원천 저장소 장애를 **빈 목록으로 바꾸지 않는다.** 빈 목록은 「없다」로
            #:   읽히고, 「없다」는 화면에서 0건이 된다.
            raise _fail(sdk.ERR_UNAVAILABLE, audit_reason=f"원천 판독 실패: {str(e)[:100]}",
                        target=str(ds.get("dataset_id", "")))

    try:
        return prov.resolve(source_intent=intent, dataset_contract_key=key,
                            binding=dp_binding, snapshots=snapshots,
                            now=datetime.now(timezone.utc).isoformat(),
                            #: ★★★ 범위는 **증명에 봉인된 값**으로 대조한다 — 요청도
                            #:   결속 표도 아니다. 결속 표의 `kit_instance_id` 가 잘못
                            #:   적혀 있으면 다른 조직의 판을 읽게 되고, 그 화면은
                            #:   오류를 내지 않는다.
                            scope={"tenant_id": str(proof.get("tenant_id", "") or ""),
                                   "scope_node_id": str(proof.get("scope_node_id", "") or ""),
                                   "entity_mode": str(proof.get("entity_mode", "") or "")},
                            allow_stale=allow_stale)
    except prov.ProviderError as e:
        #: ★ 사유는 **감사에만** 남기고 앱에는 코드만 준다 — 사유에는 그 사람이 볼 수
        #:   없는 조직의 내부 상태(승인 전·격리)가 들어 있다.
        raise _fail(e.app_code, audit_reason=f"dispatch:{e.reason}",
                    target=str(ds.get("dataset_id", "")))


def _assert_native_write(res: "prov.Resolution", ds: Dict[str, Any], *, path: str) -> None:
    """★★★ **Native 밖에는 쓰지 않는다.**

    ⚠️ 파일 판·사내 시스템·계산 결과에 앱이 쓰면 그것은 원천과 갈라진 사본이 되고,
      갈라진 사실은 아무도 모른다. L3 write-back 은 별도 Command Contract·승인·멱등·
      보상이 필요하며 이 설계 범위 밖이다."""
    try:
        prov.assert_writable(res.provider)
    except prov.ProviderError as e:
        raise _fail(e.app_code, audit_reason=e.reason,
                    target=str(ds.get("dataset_id", "")), path=path)


def _serve_snapshot(res: "prov.Resolution", *, limit: int = 0, offset: int = 0,
                    record_id: str = "") -> Dict[str, Any]:
    """승인된 판을 읽어 돌려준다. **RAW 지문을 먼저 대조한다.**

    ⚠️ 대조 없이 읽으면 「우리가 인증한 그 파일」이라는 전제가 조용히 깨진 채로
      숫자가 나간다."""
    from core.data_preparation import snapshot_service as ss

    snap = res.snapshot or {}
    path = str(snap.get("raw_path") or "")
    if not path or not ss.verify_raw(path, str(snap.get("checksum") or "")):
        raise _fail(sdk.ERR_UNAVAILABLE, audit_reason="RAW_CHECKSUM_MISMATCH",
                    target=str(snap.get("snapshot_id") or ""))
    try:
        with open(path, "rb") as f:
            parsed = ss.parse_csv(f.read())
    except (OSError, ss.IngestError) as e:
        raise _fail(sdk.ERR_UNAVAILABLE, audit_reason=f"판 판독 실패: {str(e)[:100]}",
                    target=str(snap.get("snapshot_id") or ""))

    meta = prov.public_meta(res)
    if record_id:
        #: 판에는 우리 레코드 id 가 없다 — 행 번호로 부른다.
        try:
            idx = int(record_id)
        except (TypeError, ValueError):
            raise _fail(sdk.ERR_NOT_FOUND)
        if idx < 0 or idx >= len(parsed.rows):
            raise _fail(sdk.ERR_NOT_FOUND)
        return {**meta, "record": parsed.rows[idx]}

    rows, total = prov.snapshot_rows(parsed.rows, limit=limit, offset=offset)
    return {**meta, "records": rows, "total": total}


def _record_in(plane, dataset_id: str, record_id: str) -> Dict[str, Any]:
    """레코드가 **그** 데이터셋의 것인지 확인한다(혼동된 대리인 차단과 같은 규칙).

    ⚠️ 평면을 인자로 받는다 — 전역 운영 저장소를 직접 부르면 Preview 요청이 운영
      레코드를 집는다."""
    rec = plane.get_record(str(record_id or ""))
    if not rec or str(rec.get("dataset_id") or "") != str(dataset_id or ""):
        raise _fail(sdk.ERR_NOT_FOUND)
    return rec


def _personal_ok(ds: Dict[str, Any], p: Principal, row_creator: str = "") -> None:
    """개인용 앱의 레코드는 만든 사람의 것이다(설계 §5-1).

    ⚠️ PDP 는 **데이터셋 소유자**를 보고, 여기서는 **레코드 작성자**를 본다 — 같은 데이터셋
      안에서 사람이 갈릴 수 있다."""
    if (ds.get("app_class") or "") != "personal":
        return
    owner = row_creator or ds.get("created_by") or ""
    if owner and owner != (p.user_id or ""):
        #: ⚠️ 404 다 — 「그 레코드는 있는데 남의 것이다」가 되면 존재가 샌다.
        raise _fail(sdk.ERR_NOT_FOUND, audit_reason=app_policy.DENY_PERSONAL,
                    actor=(p.user_id or ""), target=str(ds.get("dataset_id", "")))


def _actor(p: Principal) -> str:
    uid = (p.user_id or "").strip()
    if not uid:
        raise _fail(sdk.ERR_EXPIRED)
    return uid


# ── 증명 발급 ─────────────────────────────────────────────────────────────
@router.post("/proof")
async def issue_proof(req: ProofRequest, p: Principal = Depends(current_principal)):
    """★★★ **세션 인증된 부모만 부른다.** 앱(iframe)은 이 경로를 볼 수 없다.

    돌려주는 전문은 **부모 창의 메모리에만** 둔다 — `localStorage` 에도, iframe 에도,
    로그에도 가지 않는다(`test_app_runtime_no_credentials.py` 가 그것을 잠근다).

    ## 무엇을 서버가 정하는가

    `release_id` 를 뺀 전부다 — 앱 식별자·매니페스트·문맥(테넌트·실행모드·조직범위)·
    그리고 **capability**. capability 는 「지금 이 사용자가 실제로 할 수 있는 것」과
    「매니페스트가 선언한 것」의 **교집합**이다(`app_proof.grantable_actions`)."""
    uid = (p.user_id or "").strip()
    if not uid:
        raise _fail(sdk.ERR_EXPIRED)
    #: ⚠️ 세션 해시가 없으면 발급하지 않는다. 세션에 묶이지 않은 증명은 로그아웃 뒤에도
    #:   살아 있고, 그것은 **회수할 수 없는 권한**이다.
    if not (p.session_id or "").strip():
        raise _fail(sdk.ERR_EXPIRED, audit_reason="세션 없이 증명 요청", actor=uid,
                    path="POST /runtime/proof")

    release_id = (req.release_id or "").strip()
    rel = app_proof.read_release(release_id)
    if rel is None:
        raise _fail(sdk.ERR_NOT_FOUND, audit_reason="릴리스 판독 실패", actor=uid,
                    target=release_id, path="POST /runtime/proof")

    try:
        ctx = viewing_context(p)
    except HTTPException:
        raise _fail(sdk.ERR_NOT_FOUND, audit_reason="문맥 확정 불가", actor=uid,
                    target=release_id, path="POST /runtime/proof")

    #: ★★★ 조직 범위를 고르지 않은 상태에서는 증명을 만들지 않는다.
    #
    #  `issue()` 가 「범위 없는 증명은 «전 조직 허용» 이 된다」로 막는 것과 같은 이유이고,
    #  D-014(「미지정은 전사 공용이 아니라 비노출」)의 같은 규칙이다.
    #
    #  ⚠️ 이 응답만은 **고정 문장으로 접지 않는다.** 이 경로를 부르는 것은 iframe 이 아니라
    #    **부모 화면**이고, 사용자가 할 일이 분명히 있다 — 범위를 고르면 된다. 「찾을 수
    #    없습니다」로 접으면 사용자는 앱이 고장 났다고 읽는다.
    #  ★ 이것은 존재 누설이 아니다. 「내가 범위를 안 골랐다」는 **자기 자신의 상태**다.
    if not str(ctx.get("scope_node_id", "") or "").strip():
        raise HTTPException(
            status_code=409,
            detail="조직 범위를 선택해야 앱이 데이터에 연결됩니다. 화면 상단에서 회사·조직을 "
                   "고른 뒤 다시 열어 주십시오.")

    res = app_proof.resource_scope(rel, release_id)
    facts = app_proof.app_facts(rel, release_id)
    subject = app_policy.Subject(user_id=uid, scope=p.scope, ctx=ctx,
                                 session_id=p.session_id,
                                 blocked_reason=visibility_block_reason(p), via="session")
    caps = app_proof.grantable_actions(subject, res, facts)
    if not caps:
        #: ★ 「선언이 없는 앱」과 「권한이 없는 릴리스」를 구분하지 않는다 — 후자를 구분해
        #:   말하면 남의 릴리스의 존재가 샌다.
        raise _fail(sdk.ERR_NOT_FOUND,
                    audit_reason=("매니페스트 미선언" if not facts.declared_capabilities
                                  else "사용자 권한 없음"),
                    actor=uid, target=release_id, path="POST /runtime/proof")

    #: ★★★ [I-4 3단계] **발급 전 일치 게이트.**
    #
    #  두 지문을 봉인하면 «발급 뒤의 변경» 은 잡는다. 그러나 **처음부터 계약과 DB 결속이
    #  다른 상태**에는 아무 말도 하지 않는다 — 그 상태에서 나간 증명은 어긋남을 정상으로
    #  못박고, 이후 모든 대조가 그 어긋남을 기준으로 삼는다.
    #
    #  ⚠️ 봉인은 「그때와 같은가」에 답할 뿐 **「그때가 옳았는가」에는 답하지 않는다.**
    #: ★★★ [I-4 6] **청중은 릴리스 상태가 정한다.** 요청이 고르게 두면 후보 판에
    #:   운영 증명을 달라고 할 수 있고, 그것이 곧 검토되지 않은 코드의 운영 접근이다.
    audience = app_preview.audience_for_state(_release_state(release_id))
    if not audience:
        raise _fail(sdk.ERR_NOT_FOUND, audit_reason="릴리스 상태를 읽을 수 없음",
                    actor=uid, target=release_id, path="POST /runtime/proof")
    if app_preview.is_preview(audience):
        #: ⚠️ Preview 는 `SYNTHETIC_TEST` 문맥에서만 돈다 — 실제 조직 문맥으로 미리보기를
        #:   돌리면 승인 전 판이 만든 숫자가 실적으로 읽힌다.
        try:
            app_preview.assert_preview_context(ctx.get("entity_mode", ""))
        except app_preview.PreviewBoundaryError as e:
            raise _fail(sdk.ERR_FORBIDDEN, audit_reason=str(e)[:160], actor=uid,
                        target=release_id, path="POST /runtime/proof")

    #: ★★★ [F-3] 발급 시점에도 **그 청중의 평면**을 본다 — 후보 판은 Preview
    #:   평면에 물질화되므로, 운영 평면을 보면 「물질화되지 않았습니다」로 막힌다.
    gate = app_contract_gate.evaluate(
        rel, release_id, plane=app_preview.app_data_for(audience))
    if not gate.ok:
        #: ⚠️ 사유를 앱에게 그대로 주지 않는다 — 감사에만 남긴다(다른 거부와 같은 규칙).
        raise _fail(sdk.ERR_NOT_FOUND,
                    audit_reason=f"계약↔물질화 불일치: {' / '.join(gate.reasons)[:160]}",
                    actor=uid, target=release_id, path="POST /runtime/proof")

    try:
        rec = app_capability_tokens.issue(
            actor=uid, session_id=p.session_id, audience=audience,
            app_id=facts.app_id, release_id=release_id, capabilities=caps,
            tenant_id=str(ctx.get("tenant_id", "") or ""),
            entity_mode=str(ctx.get("entity_mode", "") or ""),
            scope_node_id=str(ctx.get("scope_node_id", "") or ""),
            #: ★★★ 발급 시점의 앱 선언을 **봉인**한다. capability 만 비교하면 «같은 권한을
            #:   유지한 채 내용이 바뀐 매니페스트» 가 기존 증명을 무효화하지 못한다.
            manifest_fingerprint=facts.manifest_fingerprint,
            manifest_version=facts.manifest_version,
            #: ★★★ 계약 원문과 물질화를 **함께** 봉인한다(설계 §16-1). 어느 하나라도
            #:   달라지면 그 판은 사라진 것이고, 브리지는 프레임을 버린다.
            contract_fingerprint=gate.contract_fingerprint,
            materialization_fingerprint=gate.materialization_fingerprint,
            purpose="Host Runtime 데이터 평면")
    except AppTokenError as e:
        #: 발급 계약 위반은 앱 코드 문제가 아니라 **자료 상태** 문제다(문맥·범위 공란 등).
        raise _fail(sdk.ERR_NOT_FOUND, audit_reason=f"증명 발급 거부: {e}", actor=uid,
                    target=release_id, path="POST /runtime/proof")

    #: ⚠️ 응답에 전문 말고는 아무 비밀도 싣지 않는다. `fingerprint`·`session_id` 는 남긴다 —
    #:   전자는 감사 대조용이고 후자는 **이미 부모가 가진 값**이다... 가 아니라 해시이므로
    #:   싣지 않는다. 필요한 것만 돌려준다.
    return {"status": "success", "data": {
        "token": rec["token"],
        "expires_at": rec["expires_at"],
        "capabilities": list(caps),
        "app_id": facts.app_id,
        "release_id": release_id,
        "manifest_fingerprint": facts.manifest_fingerprint,
    }}


# ── 데이터 ────────────────────────────────────────────────────────────────
@router.get("/datasets/{name}/schema")
async def get_schema(name: str, request: Request, p: Principal = Depends(current_principal)):
    proof = _require_proof(request, p)
    _judge(p, proof, app_policy.READ, op="data.schema", path="GET /records/schema")
    ds = _dataset(proof, name)
    _assert_active(ds)
    _assert_contract_action(proof, ds, "read", p=p, path="GET /records/schema")
    _personal_ok(ds, p)
    #: ⚠️ 스키마 조회도 Dispatch 를 지난다 — 지나지 않으면 준비되지 않은 원천의
    #:   데이터셋이 «스키마는 보이는데 행은 없는» 상태로 보이고, 앱은 0건으로 그린다.
    res = _dispatch(proof, ds)
    if res.provider != prov.NATIVE:
        served = _serve_snapshot(res, limit=1, offset=0)
        ds["record_count"] = int(served["total"])
        return {"status": "success", "data": {**wire.project_dataset(ds),
                                              "as_of": served["as_of"],
                                              "stale": served["stale"]}}
    ds["record_count"] = _plane(proof).count_records(ds["dataset_id"])
    return {"status": "success", "data": wire.project_dataset(ds)}


@router.get("/datasets/{name}/records")
async def list_records(name: str, request: Request, limit: int = Query(50), offset: int = Query(0),
                       p: Principal = Depends(current_principal)):
    proof = _require_proof(request, p)
    _judge(p, proof, app_policy.READ, op="data.list", path="GET /records")
    ds = _dataset(proof, name)
    _assert_active(ds)
    _assert_contract_action(proof, ds, "read", p=p, path="GET /records")
    _personal_ok(ds, p)
    #: ★★★ [BDR-6] 여기서 «어디서 읽을지» 가 정해진다. 앱은 이 분기를 보지 못한다.
    res = _dispatch(proof, ds)
    if res.provider != prov.NATIVE:
        served = _serve_snapshot(
            res, limit=max(1, min(int(limit or 50), wire.MAX_PAGE_LIMIT)),
            offset=max(0, int(offset or 0)))
        fields = _fields_of(ds)
        return {"status": "success", "data": {
            "records": [wire.project_record(r, fields) for r in served["records"]],
            "total": int(served["total"]),
            #: ★ 「언제 것인가」를 함께 준다 — 없으면 사용자는 지금 것으로 읽는다.
            "as_of": served["as_of"], "stale": served["stale"]}}

    creator = (p.user_id or "") if (ds.get("app_class") or "") == "personal" else ""
    rows, total = _plane(proof).list_records(
        ds["dataset_id"], limit=max(1, min(int(limit or 50), wire.MAX_PAGE_LIMIT)),
        offset=max(0, int(offset or 0)), created_by=creator)
    #: ★ 총계를 함께 준다 — 화면이 `len(rows)` 를 «전부» 로 읽으면 상한에 걸린 순간
    #:   사용자는 「우리 데이터는 N건」으로 믿는다.
    return {"status": "success", "data": {
        "records": [wire.project_record(r, _fields_of(ds)) for r in rows],
        "total": int(total)}}


@router.get("/datasets/{name}/records/{record_id}")
async def get_record(name: str, record_id: str, request: Request,
                     p: Principal = Depends(current_principal)):
    proof = _require_proof(request, p)
    _judge(p, proof, app_policy.READ, op="data.get", path="GET /records/{id}")
    ds = _dataset(proof, name)
    _assert_active(ds)
    _assert_contract_action(proof, ds, "read", p=p, path="GET /records/{id}")
    res = _dispatch(proof, ds)
    if res.provider != prov.NATIVE:
        served = _serve_snapshot(res, record_id=record_id)
        return {"status": "success", "data": {
            **wire.project_record(served["record"], _fields_of(ds)),
            "as_of": served["as_of"], "stale": served["stale"]}}
    rec = _record_in(_plane(proof), ds["dataset_id"], record_id)
    _personal_ok(ds, p, row_creator=rec.get("created_by", ""))
    return {"status": "success", "data": wire.project_record(rec, _fields_of(ds))}


@router.post("/datasets/{name}/records")
async def create_record(name: str, req: RecordWrite, request: Request,
                        p: Principal = Depends(current_principal)):
    proof = _require_proof(request, p)
    actor = _actor(p)
    _judge(p, proof, app_policy.WRITE, op="data.create", path="POST /records")
    ds = _dataset(proof, name)
    _assert_active(ds)
    _assert_contract_action(proof, ds, "create", p=p, path="POST /records")
    #: ★★★ [BDR-6] **Native 밖에는 쓰지 않는다.** 여기서 막지 않으면 앱이 판 위에
    #:   사본을 만들고, 그 사본은 원천과 갈라진 채 아무도 모르게 남는다.
    _assert_native_write(_dispatch(proof, ds), ds, path="POST /records")
    _personal_ok(ds, p)
    try:
        #: ⚠️ 앱이 보낸 권한 관련 필드를 **지운다**(검증이 아니라 삭제). 브리지도 지우지만
        #:   서버가 다시 지운다 — 브리지 결함 하나가 곧 권한 입력이 되지 않게.
        out = _plane(proof).create_record(
            ds["dataset_id"], sdk.sanitize_request(req.payload), actor_id=actor,
            #: ★ 이 릴리스가 결속한 스키마 판으로 검증한다 — 마스터가 아니다.
            release_id=str(proof.get("release_id", "") or ""))
    except AppDataIntegrityError as e:
        #: ⚠️ 서버 상태 이상은 400 이 아니다 — 사용자가 값을 고쳐도 낫지 않는다.
        raise _fail(sdk.ERR_UNAVAILABLE, audit_reason=f"무결성: {str(e)[:100]}",
                    actor=actor, target=ds["dataset_id"], path="POST /records")
    except AppDataError as e:
        raise _fail(sdk.ERR_INVALID, audit_reason=str(e)[:120], actor=actor,
                    target=ds["dataset_id"], path="POST /records")
    return {"status": "success", "data": wire.project_record(out, _fields_of(ds))}


@router.put("/datasets/{name}/records/{record_id}")
async def update_record(name: str, record_id: str, req: RecordWrite, request: Request,
                        p: Principal = Depends(current_principal)):
    proof = _require_proof(request, p)
    actor = _actor(p)
    _judge(p, proof, app_policy.WRITE, op="data.update", path="PUT /records/{id}")
    ds = _dataset(proof, name)
    _assert_active(ds)
    _assert_contract_action(proof, ds, "update", p=p, path="PUT /records/{id}")
    #: ★★★ [BDR-6] **Native 밖에는 쓰지 않는다.** 여기서 막지 않으면 앱이 판 위에
    #:   사본을 만들고, 그 사본은 원천과 갈라진 채 아무도 모르게 남는다.
    _assert_native_write(_dispatch(proof, ds), ds, path="PUT /records/{id}")
    rec = _record_in(_plane(proof), ds["dataset_id"], record_id)
    _personal_ok(ds, p, row_creator=rec.get("created_by", ""))
    try:
        out = _plane(proof).update_record(
            record_id, sdk.sanitize_request(req.payload), actor_id=actor,
            release_id=str(proof.get("release_id", "") or ""))
    except AppDataIntegrityError as e:
        #: ⚠️ 서버 상태 이상은 400 이 아니다 — 사용자가 값을 고쳐도 낫지 않는다.
        raise _fail(sdk.ERR_UNAVAILABLE, audit_reason=f"무결성: {str(e)[:100]}",
                    actor=actor, target=ds["dataset_id"], path="PUT /records/{id}")
    except AppDataError as e:
        raise _fail(sdk.ERR_INVALID, audit_reason=str(e)[:120], actor=actor,
                    target=ds["dataset_id"], path="PUT /records/{id}")
    return {"status": "success", "data": wire.project_record(out, _fields_of(ds))}


@router.delete("/datasets/{name}/records/{record_id}")
async def delete_record(name: str, record_id: str, request: Request,
                        p: Principal = Depends(current_principal)):
    proof = _require_proof(request, p)
    actor = _actor(p)
    _judge(p, proof, app_policy.DELETE, op="data.remove", path="DELETE /records/{id}")
    ds = _dataset(proof, name)
    _assert_active(ds)
    _assert_contract_action(proof, ds, "delete", p=p, path="DELETE /records/{id}")
    #: ★★★ [BDR-6] **Native 밖에는 쓰지 않는다.** 여기서 막지 않으면 앱이 판 위에
    #:   사본을 만들고, 그 사본은 원천과 갈라진 채 아무도 모르게 남는다.
    _assert_native_write(_dispatch(proof, ds), ds, path="DELETE /records/{id}")
    rec = _record_in(_plane(proof), ds["dataset_id"], record_id)
    _personal_ok(ds, p, row_creator=rec.get("created_by", ""))
    try:
        out = _plane(proof).delete_record(record_id, actor_id=actor)
    except AppDataIntegrityError as e:
        #: ⚠️ 서버 상태 이상은 400 이 아니다 — 사용자가 값을 고쳐도 낫지 않는다.
        raise _fail(sdk.ERR_UNAVAILABLE, audit_reason=f"무결성: {str(e)[:100]}",
                    actor=actor, target=ds["dataset_id"], path="DELETE /records/{id}")
    except AppDataError as e:
        raise _fail(sdk.ERR_INVALID, audit_reason=str(e)[:120], actor=actor,
                    target=ds["dataset_id"], path="DELETE /records/{id}")
    return {"status": "success", "data": wire.project_record(out, _fields_of(ds))}
