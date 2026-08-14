"""★★★ [I-3] 파이썬 정본 ↔ 프론트 사본 **동작 대조**.

`test_host_runtime_bridge_contract.py` 는 상수와 «그 줄이 있는가» 를 본다. 이 파일은
**같은 입력에 같은 답을 내는가** 를 본다 — 그것이 실제로 지켜야 하는 것이다.

## 왜 이렇게까지 하는가

계약이 두 언어로 있으면 언젠가 한쪽만 고쳐진다. 그리고 그때 **느슨한 쪽이 실제 동작**이
된다 — 요청은 프론트가 먼저 보고, 프론트가 통과시킨 것만 서버로 간다.

변이 검사에서 실제로 걸렸다: TS `decodeCursor` 의 숫자 검사를 지워도 소스 검사는 통과했다
(파이썬 쪽은 같은 변이를 잡았다). **한쪽만 지켜지는 계약은 지켜지지 않는 계약이다.**

## 왜 node 가 없으면 건너뛰지 않는가

이 저장소는 프론트를 빌드한다 — node 는 선택 사양이 아니다. 건너뛰면 「초록인데 검사는
안 했다」가 되고, 그 상태가 이 저장소에서 반복해 사고를 만들었다.
"""
import json
import os
import shutil
import subprocess

import pytest

from core import host_runtime_wire as wire

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TS_WIRE = os.path.join(ROOT, "frontend", "src", "lib", "hostRuntimeWire.ts")
RUNNER = os.path.join(ROOT, "tests", "js", "host_runtime_wire_runner.mjs")

SID = "gen_1"


def _req(**over):
    base = {"type": wire.MSG_REQ, "sid": SID, "request_id": "r1", "op": "data.list",
            "dataset": "todos"}
    base.update(over)
    return base


#: ★ 각 칸이 **다른 갈래**를 짚는다. 같은 갈래만 여럿 넣으면 표가 커 보일 뿐 검사는 얇다.
CURSORS = ["o50", "", "o", "o0", "o-5", "o1 OR 1=1", "; DROP TABLE", "50",
           "o" + "9" * 30, "O50", "o 50"]

PAGES = [None, {}, {"limit": 10}, {"limit": 9999}, {"limit": 0}, {"limit": -5},
         {"limit": "많이"}, {"limit": True}, {"limit": 3.5}, {"cursor": "o50"},
         {"cursor": "; DROP"}, {"cursor": -1}, {"limit": 20, "cursor": "o40"}]

REQUESTS = [
    #: 통과
    {"msg": _req(), "sid": SID, "inflight": []},
    {"msg": _req(op="data.schema"), "sid": SID, "inflight": []},
    {"msg": _req(op="data.get", record_id="rec_1"), "sid": SID, "inflight": []},
    {"msg": _req(op="data.create", payload={"a": 1}, idempotency_key="k"),
     "sid": SID, "inflight": []},
    {"msg": _req(op="data.update", record_id="r", payload={"a": 1}, idempotency_key="k"),
     "sid": SID, "inflight": []},
    {"msg": _req(op="data.remove", record_id="r", idempotency_key="k"),
     "sid": SID, "inflight": []},
    {"msg": _req(page={"limit": 5}), "sid": SID, "inflight": []},
    #: 버린다(답하지 않는다)
    {"msg": _req(sid="gen_0"), "sid": SID, "inflight": []},
    {"msg": _req(), "sid": "", "inflight": []},
    {"msg": _req(type="afs.hello"), "sid": SID, "inflight": []},
    {"msg": _req(type="other"), "sid": SID, "inflight": []},
    {"msg": None, "sid": SID, "inflight": []},
    {"msg": "문자열", "sid": SID, "inflight": []},
    {"msg": [], "sid": SID, "inflight": []},
    #: 거부
    {"msg": _req(scope_node_id="node_hq"), "sid": SID, "inflight": []},
    {"msg": _req(record_id="rec_1"), "sid": SID, "inflight": []},
    {"msg": _req(request_id=""), "sid": SID, "inflight": []},
    {"msg": _req(request_id="   "), "sid": SID, "inflight": []},
    {"msg": _req(request_id="x" * 200), "sid": SID, "inflight": []},
    {"msg": _req(request_id=7), "sid": SID, "inflight": []},
    {"msg": _req(request_id="r9"), "sid": SID, "inflight": ["r9"]},
    {"msg": _req(op="data.exfiltrate"), "sid": SID, "inflight": []},
    {"msg": _req(op=""), "sid": SID, "inflight": []},
    {"msg": _req(op="data.create", payload={"a": 1}), "sid": SID, "inflight": []},
    {"msg": _req(op="data.update", record_id="r", payload={"a": 1}, idempotency_key="k",
                 version=3), "sid": SID, "inflight": []},
    {"msg": _req(op="data.create", payload={"release_id": "rel_x"}, idempotency_key="k"),
     "sid": SID, "inflight": []},
    {"msg": _req(op="data.create", payload="문자열", idempotency_key="k"),
     "sid": SID, "inflight": []},
    {"msg": _req(op="data.create", payload=[], idempotency_key="k"), "sid": SID, "inflight": []},
    {"msg": _req(page=[]), "sid": SID, "inflight": []},
    {"msg": _req(page="많이"), "sid": SID, "inflight": []},
    {"msg": _req(dataset="d" * 200), "sid": SID, "inflight": []},
    {"msg": _req(dataset=7), "sid": SID, "inflight": []},
    {"msg": _req(op="data.get", record_id=""), "sid": SID, "inflight": []},
]

ROWS = [
    {"dataset_id": "ds_1", "name": "todos", "label": "할일", "schema": {"fields": []},
     "record_count": 3, "release_id": "rel_x", "tenant_id": "tenant_default",
     "owner_dept_id": "dept_1", "scope_node_id": "node_hq", "created_by": "a@b.com"},
    {"record_id": "rec_1", "dataset_id": "ds_1", "payload": {"t": 1},
     "created_by": "a@b.com", "updated_by": "c@d.com", "deleted_by": "",
     "created_at": "2026-08-14", "updated_at": "", "deleted": False},
    {},
]

RESPONSES = [
    {"sid": SID, "request_id": "r1", "ok": True, "data": {"records": []}},
    {"sid": SID, "request_id": "r2", "ok": True, "data": None},
    {"sid": SID, "request_id": "r3", "ok": False, "data": None, "error_code": "NOT_FOUND"},
    {"sid": SID, "request_id": "r4", "ok": False, "data": None, "error_code": ""},
]


@pytest.fixture(scope="module")
def js():
    """프론트 사본을 **실행해서** 답을 받아 온다."""
    node = shutil.which("node")
    assert node, ("node 를 찾지 못했습니다. 이 저장소는 프론트를 빌드하므로 node 는 "
                  "선택 사양이 아닙니다 — 건너뛰면 「초록인데 검사는 안 했다」가 됩니다.")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "cases.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"cursors": CURSORS, "pages": PAGES, "requests": REQUESTS,
                       "rows": ROWS, "responses": RESPONSES}, f, ensure_ascii=False)
        r = subprocess.run([node, RUNNER, TS_WIRE, path], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        assert r.returncode == 0, f"프론트 계약을 실행하지 못했습니다:\n{r.stderr[-1500:]}"
        return json.loads(r.stdout)


# ── ① 커서·페이지 ─────────────────────────────────────────────────────────

def test_커서_해석이_두_구현에서_같다(js):
    """★★★ 커서는 **앱이 보낸 문자열**이다. 한쪽이 느슨하면 그쪽이 실제 동작이 된다."""
    assert js["cursors"] == [wire.decode_cursor(c) for c in CURSORS]


def test_페이지_정규화가_두_구현에서_같다(js):
    expected = [list(wire.normalize_page(p)) for p in PAGES]
    assert js["pages"] == expected


# ── ② 요청 판정 ───────────────────────────────────────────────────────────

def test_요청_판정이_두_구현에서_같다(js):
    """★★★ 여기가 어긋나면 **프론트가 통과시킨 것만 서버로 간다** — 즉 느슨한 쪽이
    실제 통제가 된다."""
    expected = []
    for c in REQUESTS:
        v, code, _why = wire.validate_request(c["msg"], sid=c["sid"],
                                              inflight=set(c["inflight"]))
        expected.append([v, code])
    mismatch = [(i, REQUESTS[i]["msg"], got, want)
                for i, (got, want) in enumerate(zip(js["requests"], expected)) if got != want]
    assert not mismatch, f"{len(mismatch)}칸이 어긋났다: {mismatch[:3]}"


def test_표에_통과와_거부와_폐기가_모두_들어_있다(js):
    """★ 대조군 — 한 종류만 들어 있으면 「전부 거부」하는 구현도 위 시험을 통과한다."""
    kinds = {v for v, _c in js["requests"]}
    assert kinds == {wire.VERDICT_OK, wire.VERDICT_ERROR, wire.VERDICT_DROP}, kinds


# ── ③ 응답 투영 ───────────────────────────────────────────────────────────

def test_투영이_두_구현에서_같다(js):
    """★★★ 한쪽만 깎으면 **조직·계정 식별자가 앱으로 넘어간다.**"""
    assert js["datasets"] == [wire.project_dataset(r) for r in ROWS]
    assert js["records"] == [wire.project_record(r) for r in ROWS]


def test_투영_결과에_금지된_이름이_없다(js):
    for row in js["datasets"] + js["records"]:
        for k in row:
            assert k not in wire.FORBIDDEN_IN_RESPONSE, f"{k} 가 앱으로 넘어간다"


def test_응답_봉투가_두_구현에서_같다(js):
    expected = [wire.build_response(sid=r["sid"], request_id=r["request_id"], ok=r["ok"],
                                    data=r.get("data"), error_code=r.get("error_code", ""))
                for r in RESPONSES]
    assert js["responses"] == expected
