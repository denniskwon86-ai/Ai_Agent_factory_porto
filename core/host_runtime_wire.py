"""★★★ [G1-B01-B] **호출 계약(Wire Contract)** — 부모와 생성 앱 사이에 오가는 메시지의 정본.

교차검토 `[G1-B01-B]` 의 지시:

> 현재 시험은 메서드 이름과 보안 매핑을 검증하지만, I-3 가 구현할 실제 Wire Contract 는
> 정의하지 않습니다. … 이를 프론트 구현자가 임의로 결정하면 **보안 계약이 다시 프론트에
> 분산됩니다.**

`host_runtime_sdk` 가 «무엇을 열어 주는가» 를 정했다면, 이 파일은 «어떻게 부르는가» 를
정한다. 브리지(I-3)는 이 상수와 판정 함수를 **구현할 뿐 바꾸지 못한다.**

## 봉투

    요청  { type:"afs.req", sid, request_id, op, dataset, record_id?, payload?,
            page?, idempotency_key? }
    응답  { type:"afs.res", sid, request_id, ok, data?, error_code? }
    악수  앱→부모 { type:"afs.hello", request_id, min_version }
          부모→앱 { type:"afs.init", sid, version, context, ok, error_code? }

## ★★★ 이 계약이 서 있는 자리 — `event.origin` 은 경계가 아니다

생성 앱 iframe 은 `sandbox="allow-scripts"` 다(= `allow-same-origin` 없음). 그래서 그 프레임의
출처는 **불투명(opaque)** 이고 `event.origin` 은 `"null"` 로 온다.

⚠️⚠️ `origin === "null"` 을 신뢰 신호로 쓰면 안 된다. **아무 사이트나** 샌드박스 프레임을
  만들어 같은 값을 낼 수 있다. 유일한 1차 경계는 `event.source === iframe.contentWindow`
  **동일성 비교**다. `sid` 는 2차이고, 봉투 표식(`type`)은 3차다.

⚠️⚠️ 같은 이유로 부모는 앱에게 보낼 때 `targetOrigin` 을 지정할 수 없다(불투명 출처에는
  이름이 없다). 즉 **응답은 `"*"` 로 나간다.** 그래서 **응답에 비밀이 실리면 그것은 곧 유출**
  이고, 이 파일의 투영 규칙(§응답 투영)이 선택이 아니라 필수인 이유가 그것이다.

## `sid` 는 자격증명이 아니다

`sid` 는 **프레임 세대(generation) 라벨**이다. 앱이 자기 프레임 안에서 읽을 수 있으므로
비밀이 될 수 없고, 권한 판정에 절대 쓰이지 않는다. 하는 일은 하나 —
**세대가 바뀌면 옛 프레임의 늦은 메시지를 버린다.**

LLM 0콜.
"""
from __future__ import annotations

from typing import Any, Container, Dict, Optional, Tuple

from core.app_data import MAX_PAYLOAD_BYTES
from core.host_runtime_sdk import (APP_ERROR_CODES, ENVELOPE_KEY, ERR_EXPIRED, ERR_FORBIDDEN,
                                   ERR_INVALID, ERR_NOT_FOUND, ERR_UNAVAILABLE,
                                   IGNORED_FROM_APP, OPS, SDK_VERSION)

WIRE_VERSION = 1

#: ★★★ 「이 판은 사라졌다」 — 앱 선언·계약 원문·DB 물질화 중 하나가 바뀌었다.
#: ⚠️ 만료(401)와 **다른 숫자**여야 한다. 같으면 브리지가 재발급하고, 그러면
#:   **옛 코드가 새 증명으로 계속 돈다.** TS 쪽 `STATUS_STALE_APP` 과 짝이다.
STATUS_STALE_APP = 410

# ── 메시지 종류 ───────────────────────────────────────────────────────────
MSG_HELLO = f"{ENVELOPE_KEY}.hello"     # 앱 → 부모 (앱이 먼저 말한다)
MSG_INIT = f"{ENVELOPE_KEY}.init"       # 부모 → 앱
MSG_REQ = f"{ENVELOPE_KEY}.req"         # 앱 → 부모
MSG_RES = f"{ENVELOPE_KEY}.res"         # 부모 → 앱

#: 앱이 보낼 수 있는 종류는 둘뿐이다. **그 밖의 것은 답하지 않고 버린다** —
#: 모르는 메시지에 오류로 답하면 그 답 자체가 «부모가 여기 있다» 는 탐침 신호가 된다.
FROM_APP: Tuple[str, ...] = (MSG_HELLO, MSG_REQ)
FROM_HOST: Tuple[str, ...] = (MSG_INIT, MSG_RES)

#: ★ 악수는 **앱이 먼저** 한다. 부모는 프레임이 언제 듣기 시작하는지 알 수 없으므로,
#:   부모가 먼저 문맥을 던지면 그 첫 메시지는 자주 유실된다(경합).
#: ⚠️ 같은 프레임 세대에서 `hello` 를 여러 번 받아도 **같은 `sid` 를 돌려준다.** 새 `sid` 를
#:   내주면 앱이 반복 `hello` 로 진행 중인 요청을 전부 무효화할 수 있다.


# ── 봉투 필드 ─────────────────────────────────────────────────────────────
REQ_FIELDS: Tuple[str, ...] = (
    "type", "sid", "request_id", "op",
    "dataset", "record_id", "payload", "page", "idempotency_key", "version",
)
REQ_REQUIRED: Tuple[str, ...] = ("type", "sid", "request_id", "op")

#: ⚠️ 응답에 `reason`·`detail` 이 없다. 서버가 쓴 자유 문장이 앱으로 넘어가면 거기에
#:   무엇이 실릴지 아무도 통제하지 못한다(예외 메시지에는 경로·식별자·질의가 섞인다).
#:   앱에게 가는 설명은 **`ERROR_MESSAGE_KO` 의 고정 문장**뿐이다.
RES_FIELDS: Tuple[str, ...] = ("type", "sid", "request_id", "ok", "data", "error_code")

#: 응답에 절대 나타나면 안 되는 이름. 투영 허용목록이 1차 방어이고 이것은 **회귀 잠금**이다.
FORBIDDEN_IN_RESPONSE: Tuple[str, ...] = (
    "token", "session_id", "user_id", "actor", "created_by", "updated_by", "deleted_by",
    "owner_user_id", "owner_dept_id", "scope_node_id", "tenant_id", "entity_mode",
    "release_id", "reason", "detail", "traceback",
)


# ── op 별 인자 ────────────────────────────────────────────────────────────
#
# ★ 인자도 **닫힌 목록**이다. 「모르는 필드는 무시」로 두면 계약에 없는 인자가 조용히
#   자라고, 언젠가 그중 하나가 판정 입력이 된다.
OP_FIELDS: Dict[str, Tuple[str, ...]] = {
    "data.schema": ("dataset",),
    "data.list": ("dataset", "page"),
    "data.get": ("dataset", "record_id"),
    "data.create": ("dataset", "payload", "idempotency_key"),
    "data.update": ("dataset", "record_id", "payload", "idempotency_key", "version"),
    "data.remove": ("dataset", "record_id", "idempotency_key", "version"),
}

#: ★★ 바꾸는 요청에는 **멱등키가 필수**다. 키 없는 재시도는 곧 중복 쓰기이고, 앱은
#:   `UNAVAILABLE`(=결과를 알 수 없다)을 받으면 재시도하도록 설계돼 있다 — 즉 키가 없으면
#:   이 계약이 **스스로 중복을 만든다.** 그래서 fail-closed 로 요구한다.
OP_REQUIRED: Dict[str, Tuple[str, ...]] = {
    "data.schema": ("dataset",),
    "data.list": ("dataset",),
    "data.get": ("dataset", "record_id"),
    "data.create": ("dataset", "payload", "idempotency_key"),
    "data.update": ("dataset", "record_id", "payload", "idempotency_key"),
    "data.remove": ("dataset", "record_id", "idempotency_key"),
}

#: ★★★ **계약에는 있으나 서버가 아직 검사하지 않는 필드.**
#:
#: `version` 은 낙관적 동시성(다른 사람이 먼저 고쳤으면 거부)을 위한 것인데, 지금
#: `app_records` 에 판(version) 컬럼이 없고 `update_record` 는 **마지막 쓰기가 이긴다.**
#:
#: ⚠️⚠️ 받아서 «무시» 하면 안 된다. 그러면 앱은 충돌 보호가 있다고 믿고 화면에 그렇게
#:   표시하는데 실제로는 남의 수정을 덮어쓴다 — 이 저장소가 «조용한 거짓말» 이라 부르는
#:   결함 그대로다. 서버가 검사할 때까지는 **보내면 거부**한다.
#:   서버가 구현되면 이 튜플에서 이름을 빼는 것만으로 열린다(계약 모양은 그대로다).
NOT_YET_HONORED: Tuple[str, ...] = ("version",)


# ── 한계값 ────────────────────────────────────────────────────────────────
#
# ⚠️ 서버의 한계와 **정합해야** 한다. `app_data.py` 가 같은 함정을 이미 겪었다 —
#   스키마가 허용하는 값을 저장할 수 없는 구간이 생기면 사용자에게는 원인이 보이지 않는다.
MAX_REQUEST_BYTES = MAX_PAYLOAD_BYTES + 128 * 1024
assert MAX_REQUEST_BYTES > MAX_PAYLOAD_BYTES, (
    "요청 상한이 레코드 상한보다 작으면 «서버가 허용하는 값을 앱이 보낼 수 없는» 구간이 생긴다")

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
#: ★ 「언제나 진행할 수 있다」 성질 — 한 건이 상한을 넘을 수 없어야 `page` 를 1까지 줄여
#:   반드시 앞으로 나아갈 수 있다. 이 식이 깨지면 **영원히 못 읽는 데이터셋**이 생긴다.
assert MAX_RESPONSE_BYTES > MAX_PAYLOAD_BYTES, "page 를 줄여도 못 읽는 레코드가 생긴다"

#: 서버 상한은 500 이지만 앱은 화면이다. 낮게 잡아 응답 과대를 애초에 줄인다.
MAX_PAGE_LIMIT = 100
DEFAULT_PAGE_LIMIT = 50

REQUEST_TIMEOUT_MS = 15_000      # 한 호출의 응답 대기 상한
READY_TIMEOUT_MS = 5_000         # `hello` 이후 `init` 대기 상한
MAX_INFLIGHT = 8                 # 세대당 동시 진행 요청
MAX_CALLS_PER_MINUTE = 240       # 세대당 호출 예산(폭주 앱 차단)
MAX_ID_LEN = 128                 # request_id · idempotency_key · dataset · record_id
IDEMPOTENCY_TTL_MS = 60_000
MAX_IDEMPOTENCY_ENTRIES = 64


# ── 앱에게 보이는 고정 문장 ───────────────────────────────────────────────
#
# ★ 코드는 기계가 읽고 문장은 사람이 읽는다. 문장을 **여기서만** 만든다 — 서버 예외 문구가
#   앱 화면에 그대로 뜨는 경로를 없앤다.
ERROR_MESSAGE_KO: Dict[str, str] = {
    ERR_NOT_FOUND: "요청한 데이터를 찾을 수 없습니다.",
    ERR_FORBIDDEN: "이 앱에는 그 작업이 허용되어 있지 않습니다.",
    ERR_EXPIRED: "연결이 만료되었습니다. 앱을 다시 열어 주세요.",
    ERR_INVALID: "요청 형식이 올바르지 않습니다.",
    #: ⚠️ 「실패했습니다」라고 쓰지 않는다. 쓰기가 **성공했을 수도 있다** — 그것이 이 코드의 뜻이다.
    ERR_UNAVAILABLE: "지금 결과를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.",
}
assert set(ERROR_MESSAGE_KO) == set(APP_ERROR_CODES), (
    "앱 오류 코드에 보여 줄 문장이 없으면 화면이 코드 문자열을 그대로 찍는다")


# ── 서버 경로 ─────────────────────────────────────────────────────────────
#
# ★★★ 브리지가 경로를 지어내지 못하게 한다. 「어느 REST 를 부르는가」가 프론트에 흩어지면
#   그때부터 보안 경계가 프론트 코드 리뷰가 된다.
#
# ⚠️⚠️ **레코드 경로는 데이터셋에 매여 있어야 한다.** 지금 서버에는
#   `PUT /records/{record_id}` · `DELETE /records/{record_id}` 처럼 **데이터셋을 말하지 않는**
#   경로가 있는데, 브리지가 그것을 쓰면 앱은 자기가 이름 붙인 데이터셋이 아니라 **아무
#   레코드 id** 를 가리킬 수 있다. 지금 판정(`assert_release_*`)은 **사용자 기준**이라
#   그 사용자가 볼 수 있는 다른 앱의 레코드면 통과한다 — 앱 A 가 사용자를 대리해 앱 B 의
#   데이터를 고치는 **혼동된 대리인(confused deputy)** 이다.
#   (신규 PDP 는 앱 증명의 `release_id` 를 대조해 이것을 막는다. 그러나 브리지는 전환 전에도
#    안전해야 하므로, 경로 자체를 데이터셋에 매는 것이 정답이다.)
SERVER_ROUTES: Dict[str, Tuple[str, str]] = {
    "data.schema": ("GET", "/api/v1/appdata/datasets/by-name"),
    "data.list": ("GET", "/api/v1/appdata/datasets/{dataset_id}/records"),
    "data.get": ("GET", "/api/v1/appdata/datasets/{dataset_id}/records/{record_id}"),
    "data.create": ("POST", "/api/v1/appdata/datasets/{dataset_id}/records"),
    "data.update": ("PUT", "/api/v1/appdata/datasets/{dataset_id}/records/{record_id}"),
    "data.remove": ("DELETE", "/api/v1/appdata/datasets/{dataset_id}/records/{record_id}"),
}

#: ★ 아직 서버에 없는 경로. 비어 있어야 한다 — 없다고 해서 브리지가 데이터셋 없는 경로로
#:   우회하면 위의 혼동된 대리인이 그대로 열린다.
#: [2026-08-14] `data.get`·`data.update`·`data.remove` 를 만들면서 비웠고, 데이터셋을
#:   말하지 않는 `/records/{record_id}` 는 **제거**했다(그 모양은 안전하게 만들 수 없다).
ROUTES_OWED: Tuple[str, ...] = ()

#: ⚠️ **다시 생기면 안 되는 경로 모양.** 이름을 적어 두면 시험이 되살아남을 잡는다
#:   (`FORBIDDEN_SURFACE` 와 같은 판단).
FORBIDDEN_ROUTE_SHAPES: Tuple[str, ...] = ("/api/v1/appdata/records/",)


# ── 응답 투영 ─────────────────────────────────────────────────────────────
#
# ★★★ **서버 응답을 그대로 넘기지 않는다.** 지금 `GET /datasets/by-name` 은 행 전체를
#   돌려주고 거기에는 `owner_dept_id`·`scope_node_id`·`tenant_id`·`created_by` 가 들어 있다.
#   그것을 앱에 넘기면 `host_runtime_sdk` 가 `afs.user` 를 막아 놓고 **데이터로 같은 것을
#   흘리는** 셈이 된다. 응답은 `"*"` 로 나간다는 사실이 이것을 더 나쁘게 만든다.
#
# ⚠️ 금지목록이 아니라 **허용목록**이다. 금지목록은 서버가 필드를 하나 늘리는 순간 뚫린다.
DATASET_PUBLIC_FIELDS: Tuple[str, ...] = ("name", "label", "schema", "record_count")

#: ⚠️ `dataset_id` 도 주지 않는다 — 앱은 데이터셋을 **이름으로만** 부른다는 것이 계약이고,
#:   id 를 쥐여 주면 그것을 도로 보내는 코드가 생긴다(그리고 그 id 는 남의 것일 수 있다).
RECORD_PUBLIC_FIELDS: Tuple[str, ...] = ("record_id", "payload", "created_at", "updated_at",
                                          "deleted")
#: ⚠️ `created_by`·`updated_by` 를 뺐다. 「누가 입력했는가」는 화면에 필요할 수 있지만
#:   그것은 **동료의 계정 식별자**이고, LLM 이 쓴 앱 코드에 기본으로 줄 값이 아니다.
#:   필요해지면 «표시 이름» 을 서버가 판정해서 주는 별도 항목으로 연다 — 지금 열어 두고
#:   나중에 닫는 것은 불가능하다.


def project_dataset(row: Any) -> Dict[str, Any]:
    """데이터셋 응답을 **허용목록으로 깎는다.**"""
    if not isinstance(row, dict):
        return {}
    return {k: row[k] for k in DATASET_PUBLIC_FIELDS if k in row}


def project_record(row: Any, fields: Optional[Container[str]] = None) -> Dict[str, Any]:
    """레코드 응답을 **허용목록으로 깎는다.**

    ★★★ `fields` 를 주면 `payload` 를 **그 릴리스가 결속한 판의 필드로 투영**한다.

    ⚠️ 투영하지 않으면 구버전 앱이 **자기 판에 없는 필드**를 응답으로 받는다. 그 앱의
      화면은 그것을 모르므로 조용히 버리는데, 사용자는 그 화면을 «전부» 로 읽는다.
      그리고 그 앱이 레코드를 되돌려 보내면 모르는 필드가 함께 실려 온다.
    ⚠️ `fields=None` 은 «투영하지 않는다» 이지 «필드가 없다» 가 아니다 — 빈 집합과
      구분한다(빈 집합이면 payload 는 비워진다)."""
    if not isinstance(row, dict):
        return {}
    out = {k: row[k] for k in RECORD_PUBLIC_FIELDS if k in row}
    if fields is not None and isinstance(out.get("payload"), dict):
        out["payload"] = {k: v for k, v in out["payload"].items() if k in fields}
    return out


def schema_field_names(schema: Any) -> Tuple[str, ...]:
    """스키마 → 필드 이름들. 투영에 쓴다."""
    if not isinstance(schema, dict):
        return ()
    return tuple(str(f.get("name", "")) for f in (schema.get("fields") or [])
                 if isinstance(f, dict) and f.get("name"))


# ── 요청 판정 ─────────────────────────────────────────────────────────────
VERDICT_OK = "ok"
#: ⚠️ **답하지 않고 버린다.** 우리 프레임이 아니거나 옛 세대의 메시지다. 오류로 답하면
#:   그 답이 곧 «여기 부모가 있고 sid 가 틀렸다» 는 정보가 된다.
VERDICT_DROP = "drop"
VERDICT_ERROR = "error"


def _bad(msg: str, code: str = ERR_INVALID) -> Tuple[str, str, str]:
    return (VERDICT_ERROR, code, msg)


def validate_request(msg: Any, *, sid: str,
                     inflight: Container[str] = ()) -> Tuple[str, str, str]:
    """앱이 보낸 요청을 계약에 대고 본다. `(판정, 오류코드, 사유)` 를 돌려준다.

    ⚠️ 사유는 **로그·개발자용**이다. 앱 화면에는 `ERROR_MESSAGE_KO` 의 고정 문장이 간다.
    ★ 여기서 «권한» 은 보지 않는다 — 권한은 서버의 정책 결정점이 본다. 이 함수는
      **모양**만 본다. 두 곳에서 권한을 보면 두 판정이 어긋난다."""
    if not isinstance(msg, dict):
        return (VERDICT_DROP, "", "봉투가 객체가 아니다")
    if msg.get("type") != MSG_REQ:
        #: `hello` 도 여기로 오지 않는다(악수는 별도 경로). 그 밖의 것은 남의 메시지다.
        return (VERDICT_DROP, "", f"우리 요청이 아니다: {msg.get('type')!r}")
    if not sid or msg.get("sid") != sid:
        #: ★ 프레임 재생성 → 새 `sid`. 옛 프레임의 늦은 요청은 여기서 사라진다.
        return (VERDICT_DROP, "", "다른 세대의 메시지")

    rid = msg.get("request_id")
    if not isinstance(rid, str) or not rid.strip() or len(rid) > MAX_ID_LEN:
        return _bad("request_id 가 없거나 너무 길다")
    if rid in inflight:
        #: 같은 id 가 두 번 뜨면 응답이 어느 약속으로 갈지 정해지지 않는다.
        return _bad(f"이미 진행 중인 request_id: {rid}")

    op = msg.get("op")
    if op not in OPS:
        #: ⚠️ 모르는 op 는 `host_runtime_sdk.is_mutating` 이 **쓰기로** 본다. 여기서 먼저 막는다.
        return _bad(f"알 수 없는 작업: {op!r}")

    #: ⚠️ 모르는 필드를 «무시» 하지 않고 거부한다. 무시하면 계약 밖 인자가 조용히 자라고,
    #:   그중 하나가 언젠가 판정 입력이 된다(그것이 `IGNORED_FROM_APP` 의 교훈이다).
    #: ★ 봉투 전체(`REQ_FIELDS`)가 아니라 **이 op 가 쓰는 것**만 허용한다 — 더 좁고,
    #:   봉투 검사는 여기에 완전히 포함된다(변이로 확인했다. 그래서 따로 두지 않는다).
    allowed = set(OP_FIELDS[op]) | set(REQ_REQUIRED)
    extra = {k for k in msg if k not in allowed}
    if extra:
        return _bad(f"{op} 에 쓸 수 없는 인자: {sorted(extra)}")

    for f in OP_REQUIRED[op]:
        v = msg.get(f)
        if v is None or (isinstance(v, str) and not v.strip()):
            return _bad(f"{op} 에는 {f} 가 필요하다")

    for f in NOT_YET_HONORED:
        if msg.get(f) is not None:
            #: ★★★ 받아서 무시하면 앱이 «있다» 고 믿는다. 없으면 없다고 말한다.
            return _bad(f"{f} 는 아직 서버가 검사하지 않는다 — 지금 보내면 충돌 보호가 "
                        f"있는 것처럼 보이지만 실제로는 마지막 쓰기가 이긴다")

    for f in ("dataset", "record_id", "idempotency_key"):
        v = msg.get(f)
        if v is not None and (not isinstance(v, str) or len(v) > MAX_ID_LEN):
            return _bad(f"{f} 는 {MAX_ID_LEN}자 이내 문자열이어야 한다")

    payload = msg.get("payload")
    if payload is not None:
        if not isinstance(payload, dict):
            return _bad("payload 는 객체여야 한다")
        leaked = set(payload) & set(IGNORED_FROM_APP)
        if leaked:
            #: ⚠️ `sanitize_request` 는 조용히 지운다. 여기서는 **드러낸다** — 앱 코드가
            #:   권한 필드를 보내고 있다는 사실은 개발자가 알아야 할 결함이다.
            return _bad(f"payload 에 권한 관련 필드가 있다(서버는 무시한다): {sorted(leaked)}")

    page = msg.get("page")
    if page is not None and not isinstance(page, dict):
        return _bad("page 는 {limit, cursor} 객체여야 한다")

    return (VERDICT_OK, "", "")


def normalize_page(page: Any) -> Tuple[int, int]:
    """`{limit, cursor}` → `(limit, offset)`. 모양이 어긋나면 **기본값으로 떨어진다.**

    ★ 앱은 `offset` 을 계산하지 않는다. 커서는 **직전 응답이 준 불투명한 값**이고, 앱이
      지어내도 자기 데이터셋 안에서 페이지를 건너뛸 뿐이다(권한은 매 호출 서버가 다시 본다).
      이렇게 두면 나중에 서버가 keyset 페이지네이션으로 바뀌어도 **계약은 그대로**다."""
    limit, offset = DEFAULT_PAGE_LIMIT, 0
    if isinstance(page, dict):
        raw = page.get("limit")
        if isinstance(raw, int) and not isinstance(raw, bool):
            limit = max(1, min(raw, MAX_PAGE_LIMIT))
        offset = decode_cursor(page.get("cursor"))
    return (limit, offset)


def encode_cursor(offset: int) -> str:
    """다음 페이지 커서. 마지막 페이지면 빈 문자열(= 더 없음)."""
    n = int(offset or 0)
    return f"o{n}" if n > 0 else ""


def decode_cursor(cursor: Any) -> int:
    """커서를 offset 으로. **읽을 수 없으면 0** — 「못 읽었으니 아무 데나」로 두지 않는다."""
    if not isinstance(cursor, str) or not cursor.startswith("o"):
        return 0
    body = cursor[1:]
    if not body.isdigit():
        return 0
    return min(int(body), 1_000_000)


def idempotency_slot(sid: str, op: str, dataset: str, key: str) -> str:
    """세대·작업·데이터셋·키를 묶은 중복 판정 자리.

    ## 이 멱등이 **막는 것과 못 막는 것**

    | | |
    |---|---|
    | 막는다 | `UNAVAILABLE`(결과를 알 수 없다) 을 받고 **같은 키로** 재시도할 때 |
    | 막는다 | 앱이 **안정된 키**를 주는 경우의 중복 제출(예: 저장 버튼 두 번) |
    | **못 막는다** | 앱이 키를 안 줘서 SDK 가 호출마다 새로 만들 때 |
    | **못 막는다** | 새로고침·프레임 재생성 이후의 재전송 |

    ⚠️⚠️ 세 번째 줄이 중요하다. SDK 는 키가 없으면 **호출마다 새 키**를 만든다(내용으로
      키를 만들면 «일부러 같은 값을 두 번 넣는» 정상 입력이 조용히 하나로 합쳐진다).
      그래서 저장 버튼을 두 번 누르는 것은 **앱이 키를 고정해야** 막힌다 — SDK 는 거부
      응답에 그 키를 실어 주어 재시도가 같은 키를 쓰게 한다.

    ⚠️ 세대가 바뀌면 기록이 사라지므로 «정확히 한 번» 이 아니다. 그렇게 말하지 않는다 —
      서버가 멱등키를 저장하기 전까지 이것은 **한 세대 안의 중복 방지**다.
      (서버 쪽 멱등은 `app_records` 변경이 필요하며 아직 없다.)"""
    return "\x1f".join((str(sid or ""), str(op or ""), str(dataset or ""), str(key or "")))


def accepts_app_version(min_version: Any) -> bool:
    """앱이 요구하는 SDK 판을 이 호스트가 만족하는가.

    ⚠️ 모양이 이상하면 **거절**한다. 「모르니까 통과」로 두면 v2 용 앱이 v1 호스트에서
      절반만 동작하고, 그 실패는 «데이터가 없다» 처럼 보인다."""
    if isinstance(min_version, bool) or not isinstance(min_version, int):
        return False
    return 1 <= min_version <= SDK_VERSION


def build_response(*, sid: str, request_id: str, ok: bool,
                   data: Optional[Any] = None, error_code: str = "") -> Dict[str, Any]:
    """응답 봉투. **필드는 계약에 있는 것뿐이다.**

    ⚠️ 성공에는 오류코드가, 실패에는 데이터가 실리지 않는다 — 둘 다 실리면 앱이 어느 쪽을
      믿을지 코드마다 달라진다."""
    out: Dict[str, Any] = {"type": MSG_RES, "sid": sid, "request_id": request_id,
                           "ok": bool(ok)}
    if ok:
        out["data"] = data if data is not None else {}
    else:
        out["error_code"] = error_code or ERR_UNAVAILABLE
    return out


def transport_error(detail: str = "") -> Tuple[str, str]:
    """전달 실패(시간 초과·서버 미도달·응답 과대)를 앱 코드로.

    ★★★ **판정 경로(`app_error_code`)를 타지 않는다.** 그 기본값은 `NOT_FOUND` 이고,
      전달 실패가 «없다» 로 접히면 앱은 서버에 있는 레코드를 화면에서 지운다."""
    return (ERR_UNAVAILABLE, detail[:200])
