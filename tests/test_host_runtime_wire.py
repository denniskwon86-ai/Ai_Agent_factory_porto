"""★★★ [G1-B01-B] 호출 계약 — **프론트 구현자가 임의로 정할 수 없게 잠근다.**

교차검토: 「이를 프론트 구현자가 임의로 결정하면 보안 계약이 다시 프론트에 분산됩니다.」

## 이 파일이 지키는 여섯 가지

1. 앱이 보낸 봉투는 **계약에 있는 필드만** 통과한다(모르는 필드는 무시가 아니라 거부).
2. 다른 세대·남의 메시지는 **답하지 않고 버린다**(오류 응답도 정보다).
3. 바꾸는 요청에는 **멱등키가 필수**다.
4. **아직 서버가 검사하지 않는 필드는 거부**한다 — 받아서 무시하면 조용한 거짓말이 된다.
5. 응답은 **허용목록으로 깎인다** — 조직·소유자·계정 식별자가 앱으로 넘어가지 않는다.
6. 전달 실패는 **`NOT_FOUND` 로 접히지 않는다** — 「알 수 없다」가 「없다」가 되면 앱이
   서버에 있는 레코드를 지운다.
"""
import pytest

import core.host_runtime_sdk as sdk
import core.host_runtime_wire as wire

SID = "gen_1"


def _req(**over):
    base = {"type": wire.MSG_REQ, "sid": SID, "request_id": "r1", "op": "data.list",
            "dataset": "todos"}
    base.update(over)
    return base


def _ok(msg, **kw):
    return wire.validate_request(msg, sid=SID, **kw)[0]


# ── ① 봉투 ────────────────────────────────────────────────────────────────

def test_정상_요청은_통과한다():
    """★ 대조군. 이것이 없으면 «전부 거부» 하는 구현도 아래 시험을 전부 통과한다."""
    assert _ok(_req()) == wire.VERDICT_OK


def test_계약에_없는_필드는_무시가_아니라_거부다():
    """⚠️ 「모르는 필드는 무시」로 두면 계약 밖 인자가 조용히 자라고, 그중 하나가 언젠가
    판정 입력이 된다 — `IGNORED_FROM_APP` 이 존재하는 이유가 그 사고다."""
    v, code, _ = wire.validate_request(_req(scope_node_id="node_hq"), sid=SID)
    assert (v, code) == (wire.VERDICT_ERROR, sdk.ERR_INVALID)


def test_op_에_없는_인자는_거부한다():
    """`data.list` 에 `record_id` 를 실어 보내는 것은 계약 위반이다."""
    assert _ok(_req(record_id="rec_1")) == wire.VERDICT_ERROR


@pytest.mark.parametrize("op", sorted(wire.OP_FIELDS))
def test_모든_op_가_SDK_표면과_한_짝이다(op):
    """★ 두 파일이 어긋나면 «표면엔 있는데 부를 수 없는» 또는 그 반대가 생긴다."""
    assert op in sdk.OPS
    assert op in wire.OP_REQUIRED and op in wire.SERVER_ROUTES


def test_SDK_가_연_작업은_전부_호출_계약을_갖는다():
    assert set(sdk.OPS) == set(wire.OP_FIELDS)


def test_봉투_선언이_실제_허용_필드와_일치한다():
    """★ `REQ_FIELDS` 는 문서다. 판정은 op 별 허용목록이 한다(더 좁다). 둘이 어긋나면
    문서가 «보낼 수 있다» 고 적은 필드를 코드가 거부한다 — 그 불일치를 여기서 막는다."""
    union = set(wire.REQ_REQUIRED)
    for fields in wire.OP_FIELDS.values():
        union |= set(fields)
    assert union == set(wire.REQ_FIELDS)


# ── ② 남의 메시지·옛 세대는 답하지 않고 버린다 ────────────────────────────

@pytest.mark.parametrize("bad", [
    {"type": "other.thing", "sid": SID, "request_id": "r1", "op": "data.list"},
    {"type": wire.MSG_HELLO, "sid": SID, "request_id": "r1", "op": "data.list"},
    "문자열", None, [],
])
def test_우리_요청이_아니면_답하지_않는다(bad):
    """★★ 오류로 답하면 **그 답 자체가 정보**다 — 「여기 부모가 있다」가 새어나간다."""
    assert wire.validate_request(bad, sid=SID)[0] == wire.VERDICT_DROP


def test_다른_세대의_메시지는_버린다():
    """★★★ 프레임을 다시 만들면 `sid` 가 바뀐다. 옛 프레임의 늦은 요청이 새 프레임의
    응답 대기열로 흘러들면 **앱이 남의 화면 결과를 받는다.**"""
    assert wire.validate_request(_req(sid="gen_0"), sid=SID)[0] == wire.VERDICT_DROP
    assert wire.validate_request(_req(), sid="")[0] == wire.VERDICT_DROP, \
        "호스트 sid 가 비어 있으면 전부 버려야 한다(악수 전 요청)"


def test_sid_는_권한이_아니라_세대_라벨이다():
    """⚠️ `sid` 는 앱이 자기 프레임에서 읽을 수 있으므로 **비밀이 될 수 없다.**
    이 시험은 그 사실을 문서로 못박는다 — 언젠가 이것을 자격증명으로 쓰려는 변경이 온다."""
    assert "sid" not in sdk.SDK_SURFACE
    assert "afs.session" in sdk.FORBIDDEN_SURFACE


# ── ③ 중복·진행 중 ────────────────────────────────────────────────────────

def test_진행_중인_request_id_는_거부한다():
    """같은 id 가 두 번 뜨면 응답이 어느 약속으로 갈지 정해지지 않는다."""
    assert _ok(_req(request_id="r9"), inflight={"r9"}) == wire.VERDICT_ERROR


@pytest.mark.parametrize("rid", ["", "   ", "x" * 200, 7, None])
def test_request_id_가_없거나_길면_거부한다(rid):
    assert _ok(_req(request_id=rid)) == wire.VERDICT_ERROR


def test_모르는_작업은_거부한다():
    assert _ok(_req(op="data.exfiltrate")) == wire.VERDICT_ERROR
    assert sdk.is_mutating("data.exfiltrate") is True, "거부를 뚫려도 쓰기로 취급돼야 한다"


# ── ④ 바꾸는 요청에는 멱등키가 필수 ───────────────────────────────────────

@pytest.mark.parametrize("op,extra", [
    ("data.create", {"payload": {"t": 1}}),
    ("data.update", {"record_id": "rec_1", "payload": {"t": 1}}),
    ("data.remove", {"record_id": "rec_1"}),
])
def test_바꾸는_요청은_멱등키_없이는_거부한다(op, extra):
    """★★ 이 계약은 `UNAVAILABLE`(결과를 알 수 없다)을 받으면 **재시도하라**고 말한다.
    즉 멱등키가 없으면 **계약이 스스로 중복 쓰기를 만든다.**"""
    assert _ok(_req(op=op, **extra)) == wire.VERDICT_ERROR
    assert _ok(_req(op=op, idempotency_key="k1", **extra)) == wire.VERDICT_OK


def test_읽기는_멱등키를_요구하지_않는다():
    """대조군 — 전부 요구하면 위 시험은 「아무거나 거부」로도 통과한다."""
    assert _ok(_req(op="data.schema")) == wire.VERDICT_OK
    assert _ok(_req(op="data.get", record_id="rec_1")) == wire.VERDICT_OK


@pytest.mark.parametrize("op", ["data.create", "data.update", "data.remove"])
def test_바꾸는_작업은_전부_멱등키를_필수로_선언했다(op):
    assert "idempotency_key" in wire.OP_REQUIRED[op]
    assert sdk.is_mutating(op) is True


def test_멱등_자리는_세대와_데이터셋까지_묶는다():
    """⚠️ 키만으로 묶으면 다른 데이터셋의 같은 키가 서로를 가린다."""
    a = wire.idempotency_slot(SID, "data.create", "todos", "k1")
    assert a != wire.idempotency_slot(SID, "data.create", "notes", "k1")
    assert a != wire.idempotency_slot("gen_2", "data.create", "todos", "k1")
    assert a == wire.idempotency_slot(SID, "data.create", "todos", "k1")


# ── ⑤ 아직 없는 기능을 «있는 척» 하지 않는다 ──────────────────────────────

def test_version_은_받아서_무시하지_않고_거부한다():
    """★★★ 서버에 판(version) 컬럼이 없고 `update_record` 는 **마지막 쓰기가 이긴다.**

    받아서 무시하면 앱은 충돌 보호가 있다고 믿고 화면에 그렇게 표시하는데 실제로는 남의
    수정을 덮어쓴다 — 이 저장소가 «조용한 거짓말» 이라 부르는 결함 그대로다."""
    assert "version" in wire.NOT_YET_HONORED
    v, code, why = wire.validate_request(
        _req(op="data.update", record_id="rec_1", payload={"t": 1},
             idempotency_key="k1", version=3), sid=SID)
    assert (v, code) == (wire.VERDICT_ERROR, sdk.ERR_INVALID)
    assert "version" in why


def test_아직_없는_레코드_경로를_계약이_드러낸다():
    """★★★ 지금 서버에는 `PUT /records/{id}` 처럼 **데이터셋을 말하지 않는** 경로가 있다.
    브리지가 그것을 쓰면 앱 A 가 사용자를 대리해 앱 B 의 레코드를 고칠 수 있다
    (혼동된 대리인). 계약은 데이터셋에 매인 경로만 알고, 없는 것은 «없다» 고 적는다."""
    for op in wire.ROUTES_OWED:
        assert "{dataset_id}" in wire.SERVER_ROUTES[op][1]
    for op, (_m, path) in wire.SERVER_ROUTES.items():
        if op != "data.schema":
            assert "{dataset_id}" in path, f"{op} 경로가 데이터셋에 매여 있지 않다"


# ── ⑥ 응답은 허용목록으로 깎인다 ──────────────────────────────────────────

def test_데이터셋_응답에서_조직_소유_필드가_사라진다():
    """★★★ `GET /datasets/by-name` 은 행 전체를 준다 — 거기에 `owner_dept_id`·
    `scope_node_id`·`tenant_id`·`created_by` 가 들어 있다.

    그대로 넘기면 `afs.user` 를 막아 놓고 **데이터로 같은 것을 흘리는** 셈이다.
    ⚠️ 응답은 불투명 출처 프레임으로 가므로 `targetOrigin` 을 지정할 수 없다 —
      즉 `"*"` 로 나간다. 그래서 이 투영은 선택이 아니다."""
    row = {"dataset_id": "ds_1", "name": "todos", "label": "할일", "schema": {"fields": []},
           "record_count": 3, "release_id": "rel_x", "tenant_id": "tenant_default",
           "owner_dept_id": "dept_1", "scope_node_id": "node_hq", "created_by": "a@b.com",
           "app_class": "personal"}
    out = wire.project_dataset(row)
    assert out == {"name": "todos", "label": "할일", "schema": {"fields": []},
                   "record_count": 3}


def test_레코드_응답에서_작성자_계정이_사라진다():
    """⚠️ 「누가 입력했는가」는 **동료의 계정 식별자**다. LLM 이 쓴 앱 코드에 기본으로 줄
    값이 아니다 — 지금 열어 두고 나중에 닫는 것은 불가능하다."""
    row = {"record_id": "rec_1", "dataset_id": "ds_1", "payload": {"t": 1},
           "created_by": "a@b.com", "updated_by": "c@d.com", "deleted_by": "",
           "created_at": "2026-08-13", "updated_at": "", "deleted": False}
    out = wire.project_record(row)
    assert set(out) == {"record_id", "payload", "created_at", "updated_at", "deleted"}


@pytest.mark.parametrize("name", list(wire.FORBIDDEN_IN_RESPONSE))
def test_금지된_이름은_어느_허용목록에도_없다(name):
    """★ 허용목록이 1차 방어이고 이 시험은 회귀 잠금이다 — 누군가 «편의상» 한 줄 늘릴 때 깨진다."""
    assert name not in wire.DATASET_PUBLIC_FIELDS
    assert name not in wire.RECORD_PUBLIC_FIELDS
    assert name not in wire.RES_FIELDS


def test_투영은_이상한_입력에도_안전하다():
    for bad in (None, [], "문자열", 42):
        assert wire.project_dataset(bad) == {} and wire.project_record(bad) == {}


def test_응답_봉투에_자유_문장이_없다():
    """⚠️ 서버 예외 문구에는 경로·식별자·질의가 섞인다. 앱에게 가는 설명은 고정 문장뿐이다."""
    assert "reason" not in wire.RES_FIELDS and "detail" not in wire.RES_FIELDS
    r = wire.build_response(sid=SID, request_id="r1", ok=False, error_code=sdk.ERR_NOT_FOUND)
    assert set(r) <= set(wire.RES_FIELDS)
    assert r["ok"] is False and "data" not in r


def test_성공_응답에는_오류코드가_실리지_않는다():
    """둘 다 실리면 앱이 어느 쪽을 믿을지 코드마다 달라진다."""
    r = wire.build_response(sid=SID, request_id="r1", ok=True, data={"records": []})
    assert r["ok"] is True and "error_code" not in r


def test_모든_앱_오류_코드에_보여_줄_문장이_있다():
    """⚠️ 없으면 화면이 `NOT_FOUND` 같은 코드 문자열을 그대로 찍는다."""
    assert set(wire.ERROR_MESSAGE_KO) == set(sdk.APP_ERROR_CODES)


# ── ⑦ 전달 실패는 «없다» 가 아니다 ────────────────────────────────────────

def test_전달_실패는_판정_경로를_타지_않는다():
    """★★★ `app_error_code` 의 기본값은 `NOT_FOUND` 다. 시간 초과가 그리로 접히면
    앱은 **서버에 있는 레코드를 화면에서 지운다.** 쓰기였다면 더 나쁘다 — 만들어졌는데
    실패로 알고 다시 만든다."""
    code, _ = wire.transport_error("timeout 15000ms")
    assert code == sdk.ERR_UNAVAILABLE
    assert sdk.app_error_code("timeout") == sdk.ERR_NOT_FOUND, \
        "판정 경로는 여전히 가장 적게 말하는 쪽이어야 한다(둘은 다른 축이다)"


def test_전달_실패_문장은_실패라고_단정하지_않는다():
    """⚠️ 「실패했습니다」로 쓰면 사용자가 다시 누르고, 서버에는 두 건이 남는다."""
    msg = wire.ERROR_MESSAGE_KO[sdk.ERR_UNAVAILABLE]
    assert "실패" not in msg
    assert "다시" in msg


def test_응답_기본값은_알_수_없음이다():
    """오류코드를 빠뜨린 실패 응답이 «없다» 로 굳어지면 안 된다."""
    r = wire.build_response(sid=SID, request_id="r1", ok=False)
    assert r["error_code"] == sdk.ERR_UNAVAILABLE


# ── ⑧ 한계값 ──────────────────────────────────────────────────────────────

def test_요청_상한이_서버_레코드_상한보다_크다():
    """★★ `app_data.py` 가 겪은 함정 — 두 한계가 어긋나면 «서버가 허용하는 값을 앱이
    보낼 수 없는» 구간이 생기고, 사용자에게는 그 관계가 어디에도 보이지 않는다."""
    from core.app_data import MAX_PAYLOAD_BYTES
    assert wire.MAX_REQUEST_BYTES > MAX_PAYLOAD_BYTES
    assert wire.MAX_RESPONSE_BYTES > MAX_PAYLOAD_BYTES, \
        "page 를 1까지 줄여도 못 읽는 레코드가 생긴다"


def test_페이지_상한은_서버_상한보다_낮다():
    assert wire.DEFAULT_PAGE_LIMIT <= wire.MAX_PAGE_LIMIT <= 500


@pytest.mark.parametrize("page,expected", [
    (None, (wire.DEFAULT_PAGE_LIMIT, 0)),
    ({}, (wire.DEFAULT_PAGE_LIMIT, 0)),
    ({"limit": 10}, (10, 0)),
    ({"limit": 9999}, (wire.MAX_PAGE_LIMIT, 0)),
    ({"limit": 0}, (1, 0)),
    ({"limit": -5}, (1, 0)),
    ({"limit": "많이"}, (wire.DEFAULT_PAGE_LIMIT, 0)),
    ({"limit": True}, (wire.DEFAULT_PAGE_LIMIT, 0)),
    ({"cursor": "o50"}, (wire.DEFAULT_PAGE_LIMIT, 50)),
    ({"cursor": "; DROP TABLE"}, (wire.DEFAULT_PAGE_LIMIT, 0)),
    ({"cursor": -1}, (wire.DEFAULT_PAGE_LIMIT, 0)),
    #: ⚠️ **표식은 맞는데 속이 아닌** 경우 — 변이 검사에서 이 칸이 비어 있었다.
    #:   `startswith("o")` 만 보고 `int()` 하면 여기서 터지고, 그 예외는 브리지를 죽인다.
    ({"cursor": "o1 OR 1=1"}, (wire.DEFAULT_PAGE_LIMIT, 0)),
    ({"cursor": "o"}, (wire.DEFAULT_PAGE_LIMIT, 0)),
    ({"cursor": "o-5"}, (wire.DEFAULT_PAGE_LIMIT, 0)),
    ({"cursor": "o" + "9" * 30}, (wire.DEFAULT_PAGE_LIMIT, 1_000_000)),
])
def test_페이지는_어떤_입력에도_안전한_값으로_떨어진다(page, expected):
    """⚠️ 커서는 앱이 보낸 문자열이다. 그대로 SQL 로 가면 안 되고, 못 읽으면 0 이다."""
    assert wire.normalize_page(page) == expected


def test_커서는_왕복한다():
    assert wire.decode_cursor(wire.encode_cursor(120)) == 120
    assert wire.encode_cursor(0) == "", "마지막 페이지는 빈 커서(= 더 없음)"


def test_시간_상한이_실제로_설정돼_있다():
    """★ 0 이나 무한이면 응답 없는 호출이 **영원히 매달린다** — 앱은 로딩 화면에서 멈춘다."""
    assert 1_000 <= wire.REQUEST_TIMEOUT_MS <= 60_000
    assert 1_000 <= wire.READY_TIMEOUT_MS <= wire.REQUEST_TIMEOUT_MS
    assert 1 <= wire.MAX_INFLIGHT <= 32
    assert wire.MAX_CALLS_PER_MINUTE >= 1


# ── ⑨ 악수 ────────────────────────────────────────────────────────────────

def test_앱이_먼저_말한다():
    """★ 부모는 프레임이 언제 듣기 시작하는지 모른다. 부모가 먼저 던지면 그 첫 메시지는
    자주 유실된다(경합) — 그러면 `ready` 가 영원히 걸린다."""
    assert wire.MSG_HELLO in wire.FROM_APP and wire.MSG_REQ in wire.FROM_APP
    assert wire.MSG_INIT in wire.FROM_HOST and wire.MSG_RES in wire.FROM_HOST
    assert not (set(wire.FROM_APP) & set(wire.FROM_HOST))


@pytest.mark.parametrize("v,ok", [
    (1, True), (0, False), (2, False), (99, False),
    (None, False), ("1", False), (True, False), (1.0, False),
])
def test_버전_협상은_모양이_이상하면_거절한다(v, ok):
    """⚠️ 「모르니까 통과」로 두면 v2 용 앱이 v1 호스트에서 절반만 동작하고, 그 실패는
    사용자에게 «데이터가 없다» 처럼 보인다."""
    assert wire.accepts_app_version(v) is ok


def test_모든_메시지_종류가_봉투_표식을_쓴다():
    """봉투 표식 없는 `postMessage` 는 우리 것이 아니다(신뢰가 아니라 **구분**이다)."""
    for t in wire.FROM_APP + wire.FROM_HOST:
        assert t.startswith(sdk.ENVELOPE_KEY + ".")
