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
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from api.deps import Principal, current_principal, viewing_context, visibility_block_reason
from core import app_policy, app_proof, host_runtime_sdk as sdk, host_runtime_wire as wire
from core.app_capability_token import AppTokenError, app_capability_tokens
from core.app_data import AppDataError, app_data_service

router = APIRouter(prefix="/api/v1/appdata/runtime")

#: 앱 증명을 싣는 헤더. ⚠️ 이 값은 **부모 창의 메모리에만** 있다 — iframe 에 건너가지 않는다.
PROOF_HEADER = "X-App-Proof"

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
    if rec.get("expired"):
        #: ★ 만료만은 따로 말한다 — 부모가 **한 번** 재발급하면 되는 상태다.
        raise _fail(sdk.ERR_EXPIRED, audit_reason="앱 증명 만료", actor=(p.user_id or ""),
                    path=str(request.url.path))
    return rec


def _judge(p: Principal, proof: Dict[str, Any], action: str, *, op: str, path: str,
           dataset: Optional[Dict[str, Any]] = None) -> None:
    """★★★ **정책 결정점이 강제한다.** 기존 판정은 나란히 돌려 관측만 한다.

    관측이 있어야 [5] 전환 게이트의 「여섯 작업 × 허용·거부」와 부정 시나리오 표본이 쌓인다.
    ⚠️ 관측 실패가 요청을 죽이지 않는다 — 다만 **세어서** 드러낸다."""
    from core.policy_shadow import policy_shadow

    release_id = str(proof.get("release_id", "") or "")
    try:
        ctx = viewing_context(p)
    except HTTPException:
        ctx = {}
    rel = app_proof.read_release(release_id)
    res = app_proof.resource_scope(rel, release_id)
    if dataset is not None:
        res = app_policy.ResourceScope(
            tenant_id=res.tenant_id, entity_mode=res.entity_mode,
            scope_node_id=res.scope_node_id, owner_user_id=res.owner_user_id,
            owner_dept_id=res.owner_dept_id, binding_state=res.binding_state,
            #: ⚠️⚠️ **덮어쓰지 않는다.** 종전에는 여기서 데이터셋 상태만 넣어 `resource_scope`
            #:   가 판정한 «프로그램 사용 중단» 을 지웠고, 그래서 관리자가 끈 프로그램이
            #:   계속 돌았다. 둘 중 **하나라도** 중단이면 중단이다.
            status=("retired" if ((dataset.get("retired_at") or "")
                                  or res.status != "active") else "active"))
    facts = app_proof.app_facts(rel, release_id)
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
                    status=(410 if decision.reason == app_policy.DENY_TOKEN_MANIFEST_MISMATCH
                            else 0))
    #: ★ **허용이 확정된 뒤** 성공 사용을 남긴다(§`record_use`).
    try:
        app_capability_tokens.record_use(proof)
    except Exception:
        pass


def _dataset(proof: Dict[str, Any], name: str) -> Dict[str, Any]:
    """데이터셋 «이름» → 행. **릴리스는 증명에서 나온다 — 요청이 말하지 않는다.**"""
    ds = app_data_service.find_dataset(str(proof.get("release_id", "") or ""), str(name or ""))
    if not ds:
        raise _fail(sdk.ERR_NOT_FOUND)
    return ds


def _record_in(dataset_id: str, record_id: str) -> Dict[str, Any]:
    """레코드가 **그** 데이터셋의 것인지 확인한다(혼동된 대리인 차단과 같은 규칙)."""
    rec = app_data_service.get_record(str(record_id or ""))
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

    try:
        rec = app_capability_tokens.issue(
            actor=uid, session_id=p.session_id,
            app_id=facts.app_id, release_id=release_id, capabilities=caps,
            tenant_id=str(ctx.get("tenant_id", "") or ""),
            entity_mode=str(ctx.get("entity_mode", "") or ""),
            scope_node_id=str(ctx.get("scope_node_id", "") or ""),
            #: ★★★ 발급 시점의 앱 선언을 **봉인**한다. capability 만 비교하면 «같은 권한을
            #:   유지한 채 내용이 바뀐 매니페스트» 가 기존 증명을 무효화하지 못한다.
            manifest_fingerprint=facts.manifest_fingerprint,
            manifest_version=facts.manifest_version,
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
    ds = _dataset(proof, name)
    _judge(p, proof, app_policy.READ, op="data.schema", path="GET /records/schema", dataset=ds)
    _personal_ok(ds, p)
    ds["record_count"] = app_data_service.count_records(ds["dataset_id"])
    return {"status": "success", "data": wire.project_dataset(ds)}


@router.get("/datasets/{name}/records")
async def list_records(name: str, request: Request, limit: int = Query(50), offset: int = Query(0),
                       p: Principal = Depends(current_principal)):
    proof = _require_proof(request, p)
    ds = _dataset(proof, name)
    _judge(p, proof, app_policy.READ, op="data.list", path="GET /records", dataset=ds)
    _personal_ok(ds, p)
    creator = (p.user_id or "") if (ds.get("app_class") or "") == "personal" else ""
    rows, total = app_data_service.list_records(
        ds["dataset_id"], limit=max(1, min(int(limit or 50), wire.MAX_PAGE_LIMIT)),
        offset=max(0, int(offset or 0)), created_by=creator)
    #: ★ 총계를 함께 준다 — 화면이 `len(rows)` 를 «전부» 로 읽으면 상한에 걸린 순간
    #:   사용자는 「우리 데이터는 N건」으로 믿는다.
    return {"status": "success", "data": {
        "records": [wire.project_record(r) for r in rows], "total": int(total)}}


@router.get("/datasets/{name}/records/{record_id}")
async def get_record(name: str, record_id: str, request: Request,
                     p: Principal = Depends(current_principal)):
    proof = _require_proof(request, p)
    ds = _dataset(proof, name)
    _judge(p, proof, app_policy.READ, op="data.get", path="GET /records/{id}", dataset=ds)
    rec = _record_in(ds["dataset_id"], record_id)
    _personal_ok(ds, p, row_creator=rec.get("created_by", ""))
    return {"status": "success", "data": wire.project_record(rec)}


@router.post("/datasets/{name}/records")
async def create_record(name: str, req: RecordWrite, request: Request,
                        p: Principal = Depends(current_principal)):
    proof = _require_proof(request, p)
    actor = _actor(p)
    ds = _dataset(proof, name)
    _judge(p, proof, app_policy.WRITE, op="data.create", path="POST /records", dataset=ds)
    _personal_ok(ds, p)
    try:
        #: ⚠️ 앱이 보낸 권한 관련 필드를 **지운다**(검증이 아니라 삭제). 브리지도 지우지만
        #:   서버가 다시 지운다 — 브리지 결함 하나가 곧 권한 입력이 되지 않게.
        out = app_data_service.create_record(
            ds["dataset_id"], sdk.sanitize_request(req.payload), actor_id=actor)
    except AppDataError as e:
        raise _fail(sdk.ERR_INVALID, audit_reason=str(e)[:120], actor=actor,
                    target=ds["dataset_id"], path="POST /records")
    return {"status": "success", "data": wire.project_record(out)}


@router.put("/datasets/{name}/records/{record_id}")
async def update_record(name: str, record_id: str, req: RecordWrite, request: Request,
                        p: Principal = Depends(current_principal)):
    proof = _require_proof(request, p)
    actor = _actor(p)
    ds = _dataset(proof, name)
    _judge(p, proof, app_policy.WRITE, op="data.update", path="PUT /records/{id}", dataset=ds)
    rec = _record_in(ds["dataset_id"], record_id)
    _personal_ok(ds, p, row_creator=rec.get("created_by", ""))
    try:
        out = app_data_service.update_record(
            record_id, sdk.sanitize_request(req.payload), actor_id=actor)
    except AppDataError as e:
        raise _fail(sdk.ERR_INVALID, audit_reason=str(e)[:120], actor=actor,
                    target=ds["dataset_id"], path="PUT /records/{id}")
    return {"status": "success", "data": wire.project_record(out)}


@router.delete("/datasets/{name}/records/{record_id}")
async def delete_record(name: str, record_id: str, request: Request,
                        p: Principal = Depends(current_principal)):
    proof = _require_proof(request, p)
    actor = _actor(p)
    ds = _dataset(proof, name)
    _judge(p, proof, app_policy.DELETE, op="data.remove", path="DELETE /records/{id}", dataset=ds)
    rec = _record_in(ds["dataset_id"], record_id)
    _personal_ok(ds, p, row_creator=rec.get("created_by", ""))
    try:
        out = app_data_service.delete_record(record_id, actor_id=actor)
    except AppDataError as e:
        raise _fail(sdk.ERR_INVALID, audit_reason=str(e)[:120], actor=actor,
                    target=ds["dataset_id"], path="DELETE /records/{id}")
    return {"status": "success", "data": wire.project_record(out)}
