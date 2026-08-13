"""★★★ [G1-B01] **Host Runtime SDK 계약** — 생성 앱에게 열어 주는 표면의 정본.

로드맵 G1-B01: 「생성 앱용 Host Runtime SDK 인터페이스 설계」.

## 이 파일이 «계약» 인 이유

브리지(I-3)는 프론트 코드다. 그런데 **무엇을 열어 주는가** 는 보안 결정이고, 보안 결정이
프론트 코드에만 있으면 리뷰에서 눈으로 찾아야 한다. 그래서 표면을 **여기 한 곳에** 열거하고
시험으로 잠근다 — 브리지는 이 목록을 구현할 뿐 늘리지 못한다.

## 앱이 보는 것 / 보지 못하는 것

    window.afs.data.*      데이터셋 «이름» 으로만 부른다
    window.afs.context     app_id · release_id **만**(표시용)
    window.afs.ready       준비 완료 Promise

⚠️⚠️ **앱은 `release_id` 를 말하지 않는다.** 부모가 붙인다(설계
  `design_app_data_plane_2026-08-08.md` §7-4). `context.release_id` 는 화면에 찍기 위한
  **읽기 전용 표시값**이고, 요청 메시지에 실려 와도 서버는 무시한다 — 앱이 자기 릴리스를
  말할 수 있으면 남의 앱 데이터를 요청할 수 있다.

⚠️⚠️ **사용자·토큰·자격증명은 표면에 없다.** `window.afs.user` 도 `window.afs.token` 도
  만들지 않는다. 앱이 «누가 쓰고 있는가» 를 알아야 하면 그것은 데이터로 받아야 하고,
  그 데이터는 서버가 판정을 거쳐 준다(G1-B02).

## 왜 «범용 fetch» 를 열지 않는가

`window.afs.fetch` 나 `window.afs.sql` 하나만 있으면 SDK 설계가 훨씬 쉽다. 그러나 그 순간
**정책 결정점이 무의미해진다** — 앱이 임의 경로·임의 질의를 만들 수 있으면 판정할 대상이
«무엇을 하려는가» 가 아니라 «어떤 문자열인가» 가 된다. 그래서 **행동 목록을 닫는다.**

LLM 0콜.
"""
from __future__ import annotations

from typing import Dict, Tuple

from core.app_policy import (DELETE, DENY_MANIFEST_CAPABILITY, DENY_PERSONAL,
                             DENY_PRINCIPAL_BLOCKED, DENY_RETIRED, DENY_TOKEN_APP_MISMATCH,
                             DENY_TOKEN_CAPABILITY, DENY_TOKEN_EXPIRED, DENY_UNIDENTIFIED,
                             MANAGE, READ, WRITE)

#: SDK 판. 앱 코드가 `window.afs.version` 으로 확인한다 — 브리지가 바뀌면 올린다.
SDK_VERSION = 1

#: 메시지 봉투의 표식. 이것이 없는 `postMessage` 는 **우리 것이 아니다**.
#: ⚠️ 표식만으로 신뢰하지 않는다 — 출처(source) 검증이 1차이고 이것은 2차다.
ENVELOPE_KEY = "afs"


#: ★ 앱에게 여는 **전부**. 이 목록에 없는 이름은 브리지가 만들지 않는다.
SDK_SURFACE: Tuple[str, ...] = (
    "afs.version",
    "afs.ready",
    "afs.context.app_id",
    "afs.context.release_id",
    "afs.data.schema",
    "afs.data.list",
    "afs.data.get",
    "afs.data.create",
    "afs.data.update",
    "afs.data.remove",
)

#: ⚠️ **명시적으로 금지한다.** 「없으니 안 만들겠지」로 두지 않는다 — 이름을 적어 두면
#:   리뷰에서 «왜 없는가» 를 묻지 않아도 되고, 시험이 되살아남을 잡는다.
FORBIDDEN_SURFACE: Tuple[str, ...] = (
    "afs.user",            # 사용자 정보는 앱이 알 일이 아니다(필요하면 데이터로 받는다)
    "afs.token",           # 앱 증명은 부모가 들고 있다(B03)
    "afs.session",
    "afs.fetch",           # 임의 경로 호출 — 정책 결정점을 무의미하게 만든다
    "afs.sql",             # 임의 질의 — 같은 이유
    "afs.db",
    "afs.parent",          # 부모 창 참조
    "afs.localStorage",    # 부모 저장소
    "afs.env",             # 환경변수·자격증명
)


#: 메시지 `op` → `(정책 행동, 레코드 id 필요 여부)`.
#: ★ 앱이 «하려는 일» 을 **닫힌 목록**으로 받는다. 자유 문자열을 받으면 오타 하나가
#:   «판정하지 않음» 이 되고, 그것이 이 저장소에서 반복된 결함 유형이다.
OPS: Dict[str, Tuple[str, bool]] = {
    "data.schema": (READ, False),
    "data.list": (READ, False),
    "data.get": (READ, True),
    "data.create": (WRITE, False),
    "data.update": (WRITE, True),
    "data.remove": (DELETE, True),
}

#: 앱이 **보내면 안 되는** 필드. 보내와도 서버·브리지가 무시한다.
#: ⚠️ 「무시한다」를 코드로 강제한다 — 「안 보내겠지」는 계약이 아니다.
IGNORED_FROM_APP: Tuple[str, ...] = (
    "release_id",          # §7-4 — 부모가 붙인다
    "app_id",
    "tenant_id",
    "entity_mode",
    "scope_node_id",
    "owner_dept_id",       # 클라이언트가 권한 입력을 정하는 경로
    "owner_user_id",
    "actor",
    "user_id",
)


# ── 앱에게 돌려주는 오류 ──────────────────────────────────────────────────
#
# ★★★ **판정 사유를 그대로 내보내지 않는다.** PDP 사유는 「어느 조직 범위 밖」·「미승인」
#   같은 사실을 담는데, 그것을 앱(=LLM 이 쓴 코드, 그리고 그 화면을 보는 사람)에게 주면
#   **볼 수 없는 자원의 존재가 사유 모양으로 새어나간다.**
#   G2 온톨로지 설계 §6.2 가 같은 이유로 `blocked` 개수를 응답에서 뺀 것과 같은 판단이다.
#
# 앱이 할 수 있는 일은 넷뿐이므로 코드도 넷이면 충분하다.
ERR_NOT_FOUND = "NOT_FOUND"        # 없거나 · 볼 수 없거나 (구분하지 않는다)
ERR_FORBIDDEN = "FORBIDDEN"        # 이 앱에 그 행동이 허용되지 않았다(매니페스트·증명)
ERR_EXPIRED = "EXPIRED"            # 다시 열면 된다
ERR_INVALID = "INVALID"            # 요청이 계약에 맞지 않는다(앱 코드 문제)

APP_ERROR_CODES: Tuple[str, ...] = (ERR_NOT_FOUND, ERR_FORBIDDEN, ERR_EXPIRED, ERR_INVALID)

#: PDP 사유 → 앱에게 보일 코드. **여기 없는 사유는 전부 `NOT_FOUND`** 로 접힌다
#: (기본값이 «가장 적게 말하는 것» 이어야 새 사유가 생겨도 새는 일이 없다).
_ERROR_MAP: Dict[str, str] = {
    DENY_TOKEN_EXPIRED: ERR_EXPIRED,
    #: 「이 앱에 그 권한이 없다」는 **앱 자신에 대한 사실**이라 알려도 새지 않는다 —
    #: 오히려 알려 줘야 개발자가 매니페스트를 고친다.
    DENY_TOKEN_CAPABILITY: ERR_FORBIDDEN,
    DENY_MANIFEST_CAPABILITY: ERR_FORBIDDEN,
    #: 개인 앱 규칙도 앱 자신의 성질이다.
    DENY_PERSONAL: ERR_FORBIDDEN,
    #: 「로그인이 필요하다」·「계정이 막혔다」는 사용자가 해결할 수 있는 상태다.
    DENY_UNIDENTIFIED: ERR_FORBIDDEN,
    DENY_PRINCIPAL_BLOCKED: ERR_FORBIDDEN,
    #: 폐기된 데이터셋은 존재를 알려도 새지 않는다(그 앱의 자기 데이터셋이다).
    DENY_RETIRED: ERR_NOT_FOUND,
    #: ⚠️ 남의 앱을 가리켰다는 사실도 **알리지 않는다** — 「그 릴리스가 있다」가 된다.
    DENY_TOKEN_APP_MISMATCH: ERR_NOT_FOUND,
}


def app_error_code(deny_reason: str) -> str:
    """PDP 거부 사유를 **앱에게 보일 코드**로 접는다.

    ⚠️ 기본값이 `NOT_FOUND` 인 것이 요점이다. 새 거부 사유가 생겼을 때 아무도 이 표를
      갱신하지 않아도 **가장 적게 말하는 쪽**으로 떨어진다 — 반대로 두면 새 사유가
      그대로 앱에 노출된다."""
    return _ERROR_MAP.get(str(deny_reason or ""), ERR_NOT_FOUND)


def is_mutating(op: str) -> bool:
    """이 `op` 가 데이터를 바꾸는가. 목록에 없으면 **바꾼다고 본다**(fail-closed).

    ⚠️ 모르는 것을 「읽기」로 두면 새 op 가 생겼을 때 쓰기 통제를 건너뛴다."""
    entry = OPS.get(str(op or ""))
    if entry is None:
        return True
    return entry[0] in (WRITE, DELETE, MANAGE)


def action_for(op: str) -> str:
    """`op` → 정책 행동. 모르는 `op` 는 **빈 문자열**이고, 호출부는 그것을 거부해야 한다.

    ⚠️ 여기서 기본 행동을 돌려주지 않는다 — 「모르면 읽기」가 곧 통제 우회다."""
    entry = OPS.get(str(op or ""))
    return entry[0] if entry else ""


def sanitize_request(payload: Dict) -> Dict:
    """앱이 보낸 요청에서 **권한 입력이 될 수 있는 필드를 지운다.**

    ★ 「앱이 안 보내겠지」는 계약이 아니다. LLM 이 쓴 코드가 무엇을 보낼지는 알 수 없고,
      보내온 값을 판정에 쓰는 순간 **클라이언트가 자기 권한을 정하게 된다.**
    ⚠️ 값을 «검증» 하지 않고 **지운다.** 검증하면 「맞으면 쓴다」가 되고, 그러면 언젠가
      맞는 값을 보내는 코드가 생긴다."""
    if not isinstance(payload, dict):
        return {}
    return {k: v for k, v in payload.items() if k not in IGNORED_FROM_APP}
