"""★★★ [G1-B 3.5] Host Runtime 전용 데이터 평면 — **증명 없이는 아무것도 열리지 않는다.**

교차검토 `[G1-B-I3-REVIEW-82]` 의 여덟 계약을 하나씩 잠근다.

1. 세션 인증된 부모만 증명을 발급받는다.
2. 서버가 release·app·Manifest·문맥·capability 를 **직접 산출**한다(클라이언트 입력 금지).
3. 전문은 발급 응답에서 한 번만 나가고 목록·감사에 남지 않는다.
4. **증명 누락 시 session 으로 폴백하지 않는다.**
5. 요청마다 사용자·세션·앱·릴리스·문맥·조직·Manifest 를 전수 대조한다.
6. 로그아웃 시 그 세션의 증명을 회수한다.
7. 만료는 «다시 열면 된다» 로 따로 말한다(부모가 한 번만 재발급).
8. 정확한 사유는 감사에만, 앱에는 SDK 고정 오류로 접힌다.

⚠️ 이 파일은 **실제 라우터**를 태운다. 판정 함수 단위 시험은 「실제 배선을 타지 않으면 그
  초록은 거짓이다」를 막지 못한다 — 이 저장소가 반복해 다친 유형이다.
"""
import json

import pytest

from core import app_policy as ap

H_USER = {"X-Factory-User": "u@x", "X-Session-Token": "sess_raw_1",
          #: ★ 조직 범위를 고른 상태. 고르지 않으면 증명이 나가지 않는다(별도 시험).
          "X-Enterprise-Scope": "node_hq"}
#: 세션 없는 요청(같은 사람, 헤더 신원만) — 증명 발급이 막혀야 한다.
H_NO_SESSION = {"X-Factory-User": "u@x"}


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """실제 앱 + 격리된 라이브러리·앱데이터·증명 저장소."""
    import config
    import core.library_paths as library_paths
    from core.app_capability_token import app_capability_tokens
    from core.org_directory import org_directory
    from core.policy_shadow import policy_shadow

    lib = tmp_path / "library"
    lib.mkdir()

    def _mk(rid, *, caps, project="proj_a", scope="node_hq", dept="hq", tenant="tenant_default"):
        d = lib / rid
        d.mkdir()
        (d / "release.json").write_text(json.dumps({
            "release_id": rid, "project_id": project, "tenant_id": tenant,
            "entity_mode": "REAL", "enterprise_scope_id": scope,
            "owner_user_id": "", "owner_dept_id": dept, "visibility": "dept",
            "manifest": {"fingerprint": "fp_" + rid, "valid": True, "manifest": {
                "version": "1.0", "app_class": "departmental",
                "capabilities": caps, "required_capabilities": []}},
        }, ensure_ascii=False), encoding="utf-8")

    #: 읽기·쓰기·삭제를 선언한 앱
    _mk("rel_ok", caps=["orders.read", "orders.create", "orders.delete"])
    #: 읽기만 선언한 앱 — 「선언 밖은 못 한다」의 대조군
    _mk("rel_readonly", caps=["orders.read"])
    #: 아무것도 선언하지 않은 앱
    _mk("rel_silent", caps=[])
    #: 같은 사용자가 볼 수 있는 **다른 앱** — 증명 교차 사용 대조군
    _mk("rel_other", caps=["orders.read"], project="proj_b")

    monkeypatch.setattr(library_paths, "release_dir",
                        lambda rid: str(lib / str(rid)), raising=False)
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)

    class _Scope:
        readable_dept_ids = frozenset({"hq"})
        writable_dept_ids = frozenset({"hq"})
        unrestricted = False
        can_manage_standard = False
        primary_dept_id = "hq"
        readable_scope_nodes = frozenset({"node_hq"})

        def can_read(self, d):
            return d in self.readable_dept_ids

        def can_write(self, d):
            return d in self.writable_dept_ids

    monkeypatch.setattr(org_directory, "resolve_scope", lambda uid="": _Scope())
    monkeypatch.setattr(org_directory, "is_bootstrap", lambda: False)
    monkeypatch.setattr(org_directory, "get_user",
                        lambda uid: {"user_id": uid, "status": "active"} if uid else None)
    monkeypatch.setattr(org_directory, "get_ownership",
                        lambda kind, rid: {"dept_id": "hq", "owner_user_id": "",
                                           "visibility": "dept"})

    #: ★★ 세션은 **실제 경로**로 만든다 — `X-Session-Token` 헤더를 보내면 `api.deps._session_hash`
    #:   가 `auth_store.session_hash()` 로 해시를 만든다.
    #:   ⚠️ 처음에는 `_session_hash` 를 스텁으로 갈아끼웠는데 **먹지 않았고**, 그 사실이
    #:     「세션 없음」으로 조용히 떨어져 전 시험이 401 이 됐다. 스텁을 고치는 대신
    #:     실제 배선을 태운다 — 하니스가 제품과 다른 세계를 만들면 그 초록은 거짓이다.

    app_capability_tokens._tokens.clear()
    policy_shadow.reset()

    from fastapi.testclient import TestClient
    from main import app
    c = TestClient(app)
    c.lib = lib
    return c


R = "/api/v1/appdata/runtime"


def _proof(c, release_id="rel_ok", headers=None):
    r = c.post(f"{R}/proof", json={"release_id": release_id}, headers=headers or H_USER)
    return r


def _tok(c, release_id="rel_ok"):
    r = _proof(c, release_id)
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _h(tok, extra=None):
    out = dict(H_USER)
    out["X-App-Proof"] = tok
    out.update(extra or {})
    return out


def _mkds(c, name="orders", release_id="rel_ok", app_class=""):
    """관리 API 로 데이터셋을 만든다 — 런타임 API 는 데이터셋을 만들지 않는다."""
    r = c.post("/api/v1/appdata/datasets", headers=H_USER, json={
        "release_id": release_id, "name": name, "app_class": app_class,
        "schema": {"fields": [{"name": "qty", "type": "number"}]}})
    assert r.status_code == 200, r.text
    return r.json()


def test_런타임_응답은_성공과_거부_모두_저장되지_않는다(client):
    """증명·세션·조직 문맥에 따라 답이 달라지는 GET을 URL 캐시로 재사용하면 안 된다.

    특히 이전 증명의 410이 저장되면 새 증명을 발급하고 앱을 다시 열어도 브라우저가 서버를
    부르지 않은 채 계속 «앱 정의 변경»으로 답한다. 오류 응답까지 함께 잠근다.
    """
    issued = _proof(client)
    denied = client.get(f"{R}/datasets/orders/schema", headers=H_USER)
    for response in (issued, denied):
        assert response.headers.get("cache-control") == "no-store"
        assert response.headers.get("pragma") == "no-cache"


# ── ① 증명 없이는 아무것도 열리지 않는다 ──────────────────────────────────

def test_증명이_없으면_세션으로_내려가지_않는다(client):
    """★★★ 교차검토 계약 (4). 폴백을 허용하면 앱은 **헤더 하나를 생략해서** 사람의 넓은
    권한으로 데이터를 만질 수 있다 — 그것이 이 라우터가 따로 있는 이유 전부다.

    ⚠️ 대조군을 함께 본다: 같은 사용자가 **관리 API 로는** 같은 데이터를 읽는다.
      그것이 없으면 이 시험은 「권한이 없어서 막혔다」와 구분되지 않는다."""
    _mkds(client)
    ok = client.get("/api/v1/appdata/datasets", params={"release_id": "rel_ok"}, headers=H_USER)
    assert ok.status_code == 200, f"관리 API 도 막혔다 — 대조가 안 된다: {ok.text}"

    for r in (client.get(f"{R}/datasets/orders/schema", headers=H_USER),
              client.get(f"{R}/datasets/orders/records", headers=H_USER),
              client.post(f"{R}/datasets/orders/records", headers=H_USER,
                          json={"payload": {"qty": 1}})):
        assert r.status_code == 403, f"증명 없이 통과했다: {r.status_code} {r.text[:120]}"


def test_알_수_없는_증명은_있는_증명과_같은_답을_준다(client):
    """★ 「그런 증명은 없다」와 「회수됐다」를 구분해 말하면 그 차이가 곧 정보다."""
    _mkds(client)
    a = client.get(f"{R}/datasets/orders/schema", headers=_h("app_no_such_token"))
    b = client.get(f"{R}/datasets/orders/schema", headers=H_USER)
    assert a.status_code == b.status_code == 403
    assert a.json() == b.json()


# ── ② 서버가 사실을 산출한다 ──────────────────────────────────────────────

def test_발급_요청은_릴리스만_받는다(client):
    """★★★ 교차검토 계약 (2). `capabilities` 를 받을 수 있으면 증명은 «사실» 이 아니라
    «부르는 쪽이 원한다고 말한 권한» 이 된다."""
    r = client.post(f"{R}/proof", headers=H_USER, json={
        "release_id": "rel_ok", "capabilities": ["manage"], "scope_node_id": "node_전사",
        "tenant_id": "tenant_다른회사"})
    assert r.status_code == 200, r.text
    #: 보낸 값이 무시됐는가 — `manage` 는 선언에도 없고 권한에도 없다.
    assert "manage" not in r.json()["data"]["capabilities"]


def test_capability_는_사용자_권한과_매니페스트_선언의_교집합이다(client):
    """★★★ ① 을 빼면 권한을 회수해도 증명 수명 동안 살아 있고, ② 를 빼면 선언하지 않은
    앱이 데이터를 만진다. 둘 다 이 저장소에서 한 번씩 열려 있던 구멍이다."""
    caps = json.loads(_proof(client, "rel_ok").text)["data"]["capabilities"]
    assert set(caps) == {"read", "write", "delete"}, caps

    #: 매니페스트가 읽기만 선언한 앱 — 쓰기는 사람이 할 수 있어도 담기지 않는다.
    caps2 = json.loads(_proof(client, "rel_readonly").text)["data"]["capabilities"]
    assert caps2 == ["read"], caps2


def test_사용자_권한이_없으면_교집합이_비고_발급되지_않는다(client, monkeypatch):
    """⚠️ 빈 권한 증명은 «전부 허용» 으로 오해되기 쉽다. 만들지 않는다."""
    from core.org_directory import org_directory
    monkeypatch.setattr(org_directory, "get_ownership",
                        lambda kind, rid: {"dept_id": "sales", "owner_user_id": ""})
    r = _proof(client, "rel_ok")
    assert r.status_code == 404, r.text


def test_선언하지_않은_앱에는_증명이_나가지_않는다(client):
    """★ 「선언이 없는 앱」과 「권한이 없는 릴리스」를 **구분하지 않는다** — 후자를 구분해
    말하면 남의 릴리스의 존재가 샌다."""
    a = _proof(client, "rel_silent")
    assert a.status_code == 404
    b = client.post(f"{R}/proof", headers=H_USER, json={"release_id": "rel_missing"})
    assert b.status_code == 404 and a.json() == b.json()


def test_세션이_없으면_증명을_발급하지_않는다(client):
    """★★★ 세션에 묶이지 않은 증명은 로그아웃 뒤에도 살아 있다 — **회수할 수 없는 권한**이다."""
    r = client.post(f"{R}/proof", json={"release_id": "rel_ok"}, headers=H_NO_SESSION)
    assert r.status_code == 401, r.text


# ── ③ 전문은 한 번만 나간다 ───────────────────────────────────────────────

def test_증명_전문은_저장소와_목록_어디에도_없다(client):
    from core.app_capability_token import app_capability_tokens
    tok = _tok(client)
    assert tok
    assert all(tok not in str(row) for row in app_capability_tokens.active())
    resolved = app_capability_tokens.resolve(tok)
    assert "token" not in resolved and tok not in str(resolved)


def test_발급_응답에_문맥_비밀이_실리지_않는다(client):
    """⚠️ 부모가 이미 아는 값만 돌려준다. 세션 해시·소유자·부서를 실으면 그것이 로그로 간다."""
    d = json.loads(_proof(client).text)["data"]
    assert set(d) == {"token", "expires_at", "capabilities", "app_id", "release_id",
                      "manifest_fingerprint"}


# ── ④ 전수 대조 ───────────────────────────────────────────────────────────

def test_다른_앱의_증명으로는_읽지_못한다(client):
    """★★★ 혼동된 대리인의 마지막 관문 — 사용자는 두 앱을 다 볼 수 있다(대조군)."""
    _mkds(client, "orders", "rel_ok")
    _mkds(client, "orders", "rel_other")
    good = _tok(client, "rel_ok")
    other = _tok(client, "rel_other")
    assert client.get(f"{R}/datasets/orders/schema", headers=_h(good)).status_code == 200
    #: 남의 앱 증명으로 부르면 그 앱의 데이터셋으로 해석되므로, 이름이 같아도 **다른 자원**이다.
    #: 그리고 어느 쪽이든 존재를 알려 주지 않는다.
    r = client.get(f"{R}/datasets/no_such_name/schema", headers=_h(other))
    assert r.status_code == 404


def test_다른_세션의_증명은_거부된다(client):
    """★★ 로그아웃·재로그인 뒤 재사용 경로."""
    _mkds(client)
    tok = _tok(client)
    assert client.get(f"{R}/datasets/orders/schema", headers=_h(tok)).status_code == 200
    #: 다른 세션 = 다른 세션 토큰. 실제 경로 그대로다.
    r = client.get(f"{R}/datasets/orders/schema",
                   headers={**_h(tok), "X-Session-Token": "sess_raw_2"})
    assert r.status_code == 404, f"다른 세션에서 통했다: {r.status_code}"


def test_다른_사용자의_증명은_거부된다(client):
    _mkds(client)
    tok = _tok(client)
    r = client.get(f"{R}/datasets/orders/schema",
                   headers={"X-Factory-User": "other@x", "X-Session-Token": "sess_raw_1",
                            "X-App-Proof": tok})
    assert r.status_code == 404


def test_선언하지_않은_행동은_증명이_있어도_막힌다(client):
    """★★ 매니페스트가 읽기만 선언한 앱은 **쓰기를 하지 못한다** — 사람이 쓸 수 있어도."""
    _mkds(client, "orders", "rel_readonly")
    tok = _tok(client, "rel_readonly")
    assert client.get(f"{R}/datasets/orders/records", headers=_h(tok)).status_code == 200
    r = client.post(f"{R}/datasets/orders/records", headers=_h(tok), json={"payload": {"qty": 1}})
    assert r.status_code == 403, r.text


# ── ⑤ 로그아웃 회수 ───────────────────────────────────────────────────────

def test_로그아웃하면_그_세션의_증명이_회수된다(client):
    """★★★ 세션만 지우면 앱 증명이 만료(최대 60분)까지 살아 있고, 그동안 생성 앱은 데이터를
    계속 만질 수 있다 — 사용자는 「로그아웃했다」고 믿는데."""
    from core.app_capability_token import app_capability_tokens
    from core.auth import auth_store
    _mkds(client)
    tok = _tok(client)
    assert client.get(f"{R}/datasets/orders/schema", headers=_h(tok)).status_code == 200

    #: ⚠️ 해시 함수를 스텁으로 갈아끼우지 않는다. 그러면 회수 대상 세션과 증명이 가리키는
    #:   세션이 **다른 값**이 되어, 회수가 실패해도 시험은 통과한다(실제로 그렇게 걸렸다).
    #:   로그아웃은 `auth_store.session_hash()` 로 세션을 찾는다 — 발급 때와 같은 함수다.
    r = client.post("/api/v1/auth/logout", headers={"X-Session-Token": "sess_raw_1"})
    assert r.status_code == 200, r.text

    assert app_capability_tokens.resolve(tok) is None, "로그아웃 뒤에도 증명이 살아 있다"
    assert client.get(f"{R}/datasets/orders/schema", headers=_h(tok)).status_code == 403


# ── ⑥ 사유가 앱에게 새지 않는다 ───────────────────────────────────────────

def test_거부_응답은_고정_문장뿐이다(client):
    """★★★ 교차검토 계약 (8). 사유를 그대로 돌려주면 「어느 조직 범위 밖」·「남의 앱」 같은
    사실이 새어나가고, 그것은 **볼 수 없는 자원이 존재한다**는 정보다."""
    from core import host_runtime_wire as wire
    _mkds(client)
    r = client.get(f"{R}/datasets/orders/schema", headers=H_USER)
    detail = r.json().get("detail", "")
    assert detail in wire.ERROR_MESSAGE_KO.values(), detail
    for leak in ("scope", "node_", "dept", "tenant", "TOKEN_", "release"):
        assert leak not in detail


def test_거부는_감사에_실제_사유로_남는다(client, monkeypatch):
    """⚠️ 은폐는 **응답**이지 기록이 아니다. 기록까지 뭉개면 추적이 불가능해진다."""
    from core.enterprise_context import audit
    seen = []
    monkeypatch.setattr(audit, "record", lambda **kw: seen.append(kw) or True)
    _mkds(client)
    client.get(f"{R}/datasets/orders/schema", headers=H_USER)
    denied = [k for k in seen if k.get("outcome") == "denied"]
    assert denied, "런타임 거부가 감사에 남지 않았다"
    assert "앱 증명 없음" in denied[-1].get("detail", "")


# ── ⑦ 응답 투영 ───────────────────────────────────────────────────────────

def test_런타임_응답에_조직_계정_필드가_없다(client):
    """★★★ 브리지도 깎지만 그것은 **두 번째 그물**이다. 첫 번째가 서버에 있어야 브리지
    결함 하나가 곧 유출이 되지 않는다."""
    from core import host_runtime_wire as wire
    _mkds(client)
    tok = _tok(client)
    made = client.post(f"{R}/datasets/orders/records", headers=_h(tok),
                       json={"payload": {"qty": 3}})
    assert made.status_code == 200, made.text
    rec = made.json()["data"]
    assert set(rec) <= set(wire.RECORD_PUBLIC_FIELDS), rec
    schema = client.get(f"{R}/datasets/orders/schema", headers=_h(tok)).json()["data"]
    assert set(schema) <= set(wire.DATASET_PUBLIC_FIELDS), schema
    #: ⚠️ **응답을 만드는 자리마다** 본다. 한 자리만 확인하면 나머지가 그대로 새고,
    #:   변이 검사에서 실제로 `data.get` 자리가 생존했다.
    got = client.get(f"{R}/datasets/orders/records/{rec['record_id']}",
                     headers=_h(tok)).json()["data"]
    listed = client.get(f"{R}/datasets/orders/records", headers=_h(tok)).json()["data"]["records"]
    assert listed and set(listed[0]) <= set(wire.RECORD_PUBLIC_FIELDS), listed[:1]
    upd = client.put(f"{R}/datasets/orders/records/{rec['record_id']}", headers=_h(tok),
                     json={"payload": {"qty": 5}}).json()["data"]
    rem = client.delete(f"{R}/datasets/orders/records/{rec['record_id']}",
                        headers=_h(tok)).json()["data"]
    for row in (rec, schema, got, listed[0], upd, rem):
        assert set(row) <= (set(wire.RECORD_PUBLIC_FIELDS) | set(wire.DATASET_PUBLIC_FIELDS)), row
        for k in row:
            assert k not in wire.FORBIDDEN_IN_RESPONSE


def test_앱이_보낸_권한_필드는_서버에서도_지워진다(client):
    """⚠️ 브리지가 지우지만 서버가 다시 지운다 — 브리지 결함 하나가 곧 권한 입력이 되지 않게."""
    _mkds(client)
    tok = _tok(client)
    r = client.post(f"{R}/datasets/orders/records", headers=_h(tok),
                    json={"payload": {"qty": 1, "release_id": "rel_other", "actor": "admin"}})
    #: 선언되지 않은 필드는 스키마 검증이 막는다 — 즉 «지워졌다» 는 것이 400 으로 드러나지
    #: 않고 정상 생성으로 나타난다.
    assert r.status_code == 200, r.text
    assert set(r.json()["data"]["payload"]) == {"qty"}


# ── ⑧ 여섯 작업이 전부 배선돼 있다 ────────────────────────────────────────

def test_여섯_작업이_전부_돈다(client):
    """★ 대조군 — 하나라도 안 돌면 [4] 카나리가 그 칸의 표본을 만들 수 없다."""
    from core.policy_shadow import policy_shadow
    _mkds(client)
    tok = _tok(client)
    h = _h(tok)
    assert client.get(f"{R}/datasets/orders/schema", headers=h).status_code == 200
    made = client.post(f"{R}/datasets/orders/records", headers=h, json={"payload": {"qty": 1}})
    assert made.status_code == 200, made.text
    rid = made.json()["data"]["record_id"]
    assert client.get(f"{R}/datasets/orders/records", headers=h).status_code == 200
    assert client.get(f"{R}/datasets/orders/records/{rid}", headers=h).status_code == 200
    assert client.put(f"{R}/datasets/orders/records/{rid}", headers=h,
                      json={"payload": {"qty": 2}}).status_code == 200
    assert client.delete(f"{R}/datasets/orders/records/{rid}", headers=h).status_code == 200

    #: ★★ 그리고 그 여섯이 **전환 게이트의 표본으로 쌓였는지** 본다 — 돌기만 하고 관측이
    #:   안 되면 카나리가 「눌러 봤다」를 증명하지 못한다.
    cov = policy_shadow.switch_gate()["op_coverage"]
    for op in ("data.schema", "data.list", "data.get", "data.create", "data.update",
               "data.remove"):
        assert cov[op]["allow"] >= 1, f"{op} 허용 표본이 없다: {cov}"


def test_다른_데이터셋의_레코드에는_런타임에서도_닿지_못한다(client):
    _mkds(client, "orders")
    _mkds(client, "notes")
    tok = _tok(client)
    h = _h(tok)
    made = client.post(f"{R}/datasets/notes/records", headers=h, json={"payload": {"qty": 1}})
    rid = made.json()["data"]["record_id"]
    assert client.get(f"{R}/datasets/orders/records/{rid}", headers=h).status_code == 404
    assert client.put(f"{R}/datasets/orders/records/{rid}", headers=h,
                      json={"payload": {"qty": 9}}).status_code == 404


def test_조직_범위를_고르지_않으면_증명이_나가지_않는다(client):
    """★★★ 「범위 없는 증명」은 판정에서 «좁히지 않음» 이 되어 사실상 전 조직으로 통한다.

    ⚠️ 이 거부만은 **고정 문장으로 접지 않는다.** 부르는 쪽이 iframe 이 아니라 부모 화면이고,
      사용자가 할 일이 분명히 있다 — 범위를 고르면 된다. 「찾을 수 없습니다」로 접으면
      사용자는 앱이 고장 났다고 읽는다.
    ★ 존재 누설이 아니다: 「내가 범위를 안 골랐다」는 **자기 자신의 상태**다."""
    h = {k: v for k, v in H_USER.items() if k != "X-Enterprise-Scope"}
    r = client.post(f"{R}/proof", json={"release_id": "rel_ok"}, headers=h)
    assert r.status_code == 409, r.text
    assert "조직 범위" in r.json()["detail"]


# ── ⑨ 매니페스트 → 정책 행동 (서버 산출의 핵심 표) ────────────────────────

def test_모르는_낱말은_아무_행동도_열지_않는다():
    """★★★ 매니페스트의 capability 는 **업무 낱말**이고 정책 행동은 넷뿐이다. 그 사이를 잇는
    표가 없으면 누군가 코드 안에서 즉석으로 잇게 되고, 그때부터 「어느 선언이 무엇을
    여는가」에 아무도 답하지 못한다.

    ⚠️ 「비슷하니까 읽기겠지」로 넓히면 **그 추측이 곧 권한**이다."""
    from core.app_proof import manifest_actions
    assert manifest_actions({"capabilities": ["orders.훔치기", "orders.exfiltrate"]}) == ()
    #: 동작이 없는 선언도 아무것도 열지 않는다(`app_manifest` 와 같은 규칙).
    assert manifest_actions({"capabilities": ["orders"]}) == ()
    assert manifest_actions(None) == () and manifest_actions("문자열") == ()


def test_두_표기를_모두_읽는다():
    """★ 평면 문자열과 구조화 목록 — `app_manifest` 가 둘 다 저장하므로 둘 다 읽어야 한다."""
    from core.app_proof import manifest_actions
    assert manifest_actions({"capabilities": ["orders.read", "orders.create"]}) == ("read", "write")
    assert manifest_actions({"required_capabilities": [
        {"resource": "orders", "actions": ["update", "delete"]}]}) == ("write", "delete")


def test_행동_표는_정책_행동만_가리킨다():
    """⚠️ 표가 없는 행동을 가리키면 그 선언은 영원히 아무것도 열지 못하고, 아무도 이유를 모른다."""
    from core.app_policy import ACTIONS
    from core.app_proof import MANIFEST_ACTION_WORDS
    assert set(MANIFEST_ACTION_WORDS.values()) <= set(ACTIONS)


def test_매니페스트가_없는_옛_릴리스는_빈_선언이다():
    """★ 그러면 판정이 막는다 — 그것이 옳다(선언하지 않은 앱은 데이터를 만지지 못한다).
    ⚠️ `legacy_mode` 를 기본으로 켜지 않는다: 켜는 것은 사람이 명시하는 일이다."""
    from core.app_proof import app_facts
    f = app_facts({"project_id": "p1"}, "rel_x")
    assert f.declared_capabilities == () and f.legacy_mode is False
    assert f.app_id == "p1" and f.release_id == "rel_x"


def test_릴리스를_못_읽으면_판정_불가로_떨어진다():
    """⚠️ 「못 읽었으니 통과」로 두면 그 순간 통제가 없다."""
    from core import app_policy
    from core.app_proof import resource_scope
    assert resource_scope(None, "rel_x").binding_state == app_policy.INVALID


# ── ⑩ [교차검토 83] 카나리 전에 닫아야 했던 다섯 ─────────────────────────

def test_증명_발급_뒤_프로그램을_끄면_다음_호출이_막힌다(client):
    """★★★ 지적 1 — 관리자가 「이 프로그램 쓰지 마라」를 기록했는데 **이미 발급된 증명으로
    데이터 접근이 계속되면**, 관리자는 껐다고 믿는데 앱은 돌고 있다."""
    from core.program_lifecycle import program_lifecycle
    _mkds(client)
    tok = _tok(client)
    h = _h(tok)
    assert client.get(f"{R}/datasets/orders/records", headers=h).status_code == 200

    program_lifecycle.set_status("rel_ok", "disabled", actor="admin", reason="검증")
    r = client.get(f"{R}/datasets/orders/records", headers=h)
    assert r.status_code == 404, f"끈 프로그램이 계속 돈다: {r.status_code}"
    #: 새 증명도 나가지 않는다.
    assert _proof(client, "rel_ok").status_code == 404


def test_사용_중단_예고는_막지_않는다(client):
    """★ 대조군 — 예고(`deprecated`)는 경고이지 차단이 아니다. 막아 버리면 이관 기간에
    업무가 멈춘다."""
    from core.program_lifecycle import program_lifecycle
    _mkds(client)
    tok = _tok(client)
    program_lifecycle.set_status("rel_ok", "deprecated", actor="admin", reason="이관 예정")
    assert client.get(f"{R}/datasets/orders/records", headers=_h(tok)).status_code == 200


def test_매니페스트가_바뀌면_기존_증명이_막힌다(client):
    """★★★ 지적 2 — capability 선언만 다시 읽으면 **같은 권한을 유지한 채 내용이 바뀐**
    매니페스트가 기존 증명을 무효화하지 못한다.

    ★ 앱에게는 `EXPIRED`(401) 로 보인다 — 부모가 새 증명을 받으면 곧바로 풀리는 상태다."""
    _mkds(client)
    tok = _tok(client)
    assert client.get(f"{R}/datasets/orders/records", headers=_h(tok)).status_code == 200

    #: 같은 capability 를 유지한 채 지문만 바꾼다.
    path = client.lib / "rel_ok" / "release.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    d["manifest"]["fingerprint"] = "fp_changed"
    path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    r = client.get(f"{R}/datasets/orders/records", headers=_h(tok))
    #: ★ 410 = 「이 판은 사라졌다」. 만료(401)와 **다른 상태**여야 부모가 다르게 행동한다 —
    #:   만료는 재발급으로 풀리지만 선언 변경은 **프레임을 버려야** 한다.
    assert r.status_code == 410, f"바뀐 앱에 옛 증명이 통했다: {r.status_code}"
    assert r.headers.get("cache-control") == "no-store", \
        "이 410이 캐시되면 새 증명을 받아 다시 열어도 이전 오류가 되살아난다"
    #: 서버는 새 증명을 내준다(사용자가 앱을 다시 열면 그것으로 돈다). 낡은 코드에 그것을
    #: 주지 않는 책임은 **브리지**에 있고, 그 계약은 `test_host_runtime_bridge_contract` 가 본다.
    assert client.get(f"{R}/datasets/orders/records",
                      headers=_h(_tok(client))).status_code == 200


def test_거부된_요청은_성공_사용으로_기록되지_않는다(client, monkeypatch):
    """★★★ 지적 3 — 해석은 「토큰이 존재한다」까지만 증명한다. 먼저 기록하면 보안 감사에서
    **「데이터를 만졌다」와 「만지려다 막혔다」가 같은 줄**이 되고 카나리 증거도 왜곡된다."""
    from core.enterprise_context import audit
    _mkds(client, "orders", "rel_readonly")
    tok = _tok(client, "rel_readonly")
    seen = []
    monkeypatch.setattr(audit, "record", lambda **kw: seen.append(kw.get("event")) or True)

    #: 매니페스트가 선언하지 않은 쓰기 → PDP 거부
    r = client.post(f"{R}/datasets/orders/records", headers=_h(tok), json={"payload": {"qty": 1}})
    assert r.status_code == 403, r.text
    assert "APP_TOKEN_USED" not in seen, f"거부됐는데 «사용됨» 이 남았다: {seen}"

    #: 대조군 — 허용되는 요청에서는 남아야 한다(안 남기면 유출 조사를 못 한다).
    seen.clear()
    assert client.get(f"{R}/datasets/orders/records", headers=_h(tok)).status_code == 200
    assert "APP_TOKEN_USED" in seen, "허용됐는데 사용 기록이 없다"


def test_사용여부를_묻지_못하면_막는다(client, monkeypatch):
    """★★★ 보안·안전 경계에서 「못 물어봤으니 통과」는 **통제가 없는 것과 같다.**

    ⚠️ 이 저장소가 `ownership_visible` 1차 구현에서 정확히 그렇게 틀렸다."""
    from core import program_lifecycle as pl
    _mkds(client)
    tok = _tok(client)
    assert client.get(f"{R}/datasets/orders/records", headers=_h(tok)).status_code == 200

    def _boom(release_id):
        raise RuntimeError("사용여부 저장소 장애")
    monkeypatch.setattr(pl.program_lifecycle, "get_status", _boom)
    r = client.get(f"{R}/datasets/orders/records", headers=_h(tok))
    assert r.status_code == 404, f"사용여부를 못 물었는데 통과했다: {r.status_code}"


# ── ⑪ [교차검토 84] 매니페스트 결속이 실질적으로 서는가 ──────────────────

def test_매니페스트_불일치는_만료와_다른_상태로_구분된다(client):
    """★★★ 둘 다 앱에게는 `EXPIRED` 로 보이지만 **부모가 할 일이 다르다**.

    · 만료      → 새 증명을 받아 **같은 프레임**을 계속 쓴다.
    · 선언 변경 → 지금 도는 코드가 **낡은 코드**다. 새 증명을 주면 「옛 앱이 새 증명으로
                  계속 도는」 상태가 되고, 그것이 결속을 우회하는 길이다.

    상태코드가 같으면 브리지가 그 둘을 **구분할 방법이 없다.**"""
    from core import host_runtime_wire as wire
    _mkds(client)
    tok = _tok(client)
    path = client.lib / "rel_ok" / "release.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    d["manifest"]["fingerprint"] = "fp_changed"
    path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    r = client.get(f"{R}/datasets/orders/records", headers=_h(tok))
    assert r.status_code == 410, f"만료와 같은 상태로 답했다: {r.status_code}"
    #: ⚠️ 사유는 여전히 새지 않는다 — 고정 문장뿐이다.
    assert r.json()["detail"] in wire.ERROR_MESSAGE_KO.values()


def test_빈_지문으로는_증명을_발급할_수_없다(client):
    """★★★ 판정은 「양쪽 다 비면 같다」를 막으려고 빈 값을 거부한다. 그런데 발급이 빈 값을
    만들면 그 증명은 **태어나자마자 아무 데도 못 쓰는** 것이 되고, 왜인지 아무도 모른다.
    막을 곳은 만드는 자리다."""
    from core.app_capability_token import AppCapabilityTokenStore, AppTokenError
    store = AppCapabilityTokenStore()
    for kw in ({"manifest_fingerprint": "", "manifest_version": "1.0"},
               {"manifest_fingerprint": "fp", "manifest_version": ""},
               {}):
        with pytest.raises(AppTokenError):
            store.issue(actor="u@x", session_id="s1", app_id="a1", release_id="r1",
                        capabilities=("read",), tenant_id="t", entity_mode="REAL",
                        scope_node_id="node_hq", **kw)


def test_매니페스트가_없는_릴리스에는_증명이_나가지_않는다(client):
    """⚠️ 지문을 유도할 수 없는 릴리스는 **증명 자체가 성립하지 않는다.**"""
    d = client.lib / "rel_nomanifest"
    d.mkdir()
    (d / "release.json").write_text(json.dumps({
        "release_id": "rel_nomanifest", "project_id": "p", "tenant_id": "tenant_default",
        "entity_mode": "REAL", "enterprise_scope_id": "node_hq", "owner_dept_id": "hq"},
        ensure_ascii=False), encoding="utf-8")
    assert _proof(client, "rel_nomanifest").status_code == 404


@pytest.mark.parametrize("status", ["disabled", "quarantined"])
def test_허용목록에_없는_사용여부는_전부_막는다(client, status):
    """★★★ 종전에는 `status != disabled` 였다. 그러면 **나중에 생기는 상태가 자동으로
    허용**된다 — 새 상태를 만드는 사람은 대개 「막으려고」 만드는데 그 순간 여기가 열려 있다."""
    from core import program_lifecycle as pl
    _mkds(client)
    tok = _tok(client)
    monkey = {"release_id": "rel_ok", "status": status, "recorded": True}
    orig = pl.program_lifecycle.get_status
    pl.program_lifecycle.get_status = lambda rid: (monkey if rid == "rel_ok" else orig(rid))
    try:
        r = client.get(f"{R}/datasets/orders/records", headers=_h(tok))
        assert r.status_code == 404, f"«{status}» 가 통과했다"
    finally:
        pl.program_lifecycle.get_status = orig


# ── ⑫ [카나리 실측] 만료가 «판정에 도달» 하는가 ──────────────────────────

def test_만료된_증명도_판정을_거쳐_표본이_된다(client):
    """★★★ [2026-08-14 격리 카나리 실측] 종전에는 만료를 **문 앞에서** 401 로 끊었다.

    밖에서 보이는 결과는 같지만 그 요청은 **판정에 도달하지 못했고**, 그래서 전환 게이트의
    「만료된 증명」 표본이 **영원히 0** 이었다 — 실제로 만료를 태워 보고도 게이트는
    「눌러 보지 않았다」고 말했다.

    ★ `resolve()` 가 만료를 `None` 이 아니라 `expired=True` 로 돌려주는 이유가 이것이다:
      「그런 증명이 없다」와 「만료됐다」는 **판정기가 구분해야** 하는 사실이다."""
    from core.app_capability_token import app_capability_tokens, token_hash
    from core.policy_shadow import policy_shadow
    from datetime import datetime, timedelta, timezone

    _mkds(client)
    tok = _tok(client)
    policy_shadow.reset()

    #: 시간을 기다리지 않고 만료시킨다(저장 키는 해시다).
    with app_capability_tokens._lock:
        app_capability_tokens._tokens[token_hash(tok)]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    r = client.get(f"{R}/datasets/orders/records", headers=_h(tok))
    assert r.status_code == 401, f"만료가 401 이 아니다: {r.status_code}"
    g = policy_shadow.switch_gate()
    assert g["scenario_coverage"]["만료된 증명"] >= 1, \
        f"만료를 태웠는데 게이트 표본이 0 이다: {g['scenario_coverage']}"
    assert ap.DENY_TOKEN_EXPIRED in g["reasons_seen"]


def test_다른_앱_사유는_런타임_경로에서_구조로_막혀_있다(client):
    """★★★ [카나리 실측] **`TOKEN_APP_MISMATCH` 는 런타임 경로에서 판정으로 재현되지 않는다.**

    서버가 자원을 **증명 자체에서** 유도하므로 `tok.release_id == app.release_id` 가 언제나
    참이다. 즉 이 사유는 판정이 아니라 **구조로** 막혀 있다 — 앱은 남의 릴리스를 «말할
    방법이 없다».

    ⚠️ 그래서 전환 게이트의 「다른 앱의 데이터」 표본은 이 경로에서 **영원히 0** 이다.
      그 사실을 여기 적어 둔다 — 게이트가 닫혀 있는 이유가 「안 눌러 봤다」가 아니라
      「누를 수 없다」임을 다음 사람이 알아야 한다.
    ★ 대신 결과를 확인한다: 남의 앱 증명으로는 이 앱 데이터가 **보이지 않는다.**"""
    import inspect

    import api.routes.app_data_runtime as rt
    src = inspect.getsource(rt._judge)
    #: 자원 사실을 증명의 release_id 로 만든다 — 요청이 릴리스를 말하지 않는다.
    assert 'release_id = str(proof.get("release_id"' in src
    assert "app_proof.app_facts(rel, release_id)" in src

    _mkds(client, "orders", "rel_ok")
    _mkds(client, "orders", "rel_other")
    mine = _tok(client, "rel_ok")
    theirs = _tok(client, "rel_other")
    client.post(f"{R}/datasets/orders/records", headers=_h(mine), json={"payload": {"qty": 7}})
    seen = client.get(f"{R}/datasets/orders/records", headers=_h(theirs))
    assert seen.status_code == 200
    assert seen.json()["data"]["records"] == [], "남의 앱 증명으로 이 앱 데이터가 보인다"


# ── ⑬ [교차검토 86] 만료 증명으로 이름을 열거할 수 없다 ─────────────────

def test_만료된_증명으로_데이터셋_이름을_열거할_수_없다(client):
    """★★★ **P0.** 만료 증명을 판정보다 **데이터셋 조회에 먼저** 넘기면,
    있는 이름은 401 · 없는 이름은 404 가 되어 **이름을 하나씩 확인할 수 있다.**

    관측 표본을 만들려다(만료를 판정에 태우려다) 경계를 약화시킨 회귀였다 —
    「관측을 위해 통제를 늦춘다」는 언제나 이 모양이 된다.

    ⚠️ 두 답이 **완전히 같아야** 한다. 상태코드만 같고 본문이 다르면 그것도 오라클이다."""
    from core.app_capability_token import app_capability_tokens, token_hash
    from datetime import datetime, timedelta, timezone

    _mkds(client, "orders")
    tok = _tok(client)
    with app_capability_tokens._lock:
        app_capability_tokens._tokens[token_hash(tok)]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    exists = client.get(f"{R}/datasets/orders/records", headers=_h(tok))
    absent = client.get(f"{R}/datasets/no_such_dataset/records", headers=_h(tok))
    assert exists.status_code == absent.status_code == 401, \
        f"있는 이름 {exists.status_code} · 없는 이름 {absent.status_code} — 열거된다"
    assert exists.json() == absent.json(), "본문이 달라 이름이 새어나간다"


@pytest.mark.parametrize("proof_kind", ["other_user", "other_session"])
def test_거부되는_증명은_모두_이름을_열거할_수_없다(client, proof_kind):
    """★ 만료만 막고 끝내지 않는다 — **거부되는 모든 축**에서 같아야 한다.
    한 축만 고치면 다음 사고는 다른 축에서 난다."""
    _mkds(client, "orders")
    tok = _tok(client)
    if proof_kind == "other_user":
        h = {"X-Factory-User": "stranger@x", "X-Session-Token": "sess_raw_1",
             "X-Enterprise-Scope": "node_hq", "X-App-Proof": tok}
    else:
        h = {**_h(tok), "X-Session-Token": "sess_raw_9"}
    a = client.get(f"{R}/datasets/orders/records", headers=h)
    b = client.get(f"{R}/datasets/no_such_dataset/records", headers=h)
    assert a.status_code == b.status_code and a.json() == b.json(), \
        f"{proof_kind}: {a.status_code} vs {b.status_code} — 이름이 새어나간다"


def test_판정이_데이터셋을_모른_채_끝난다():
    """★★ 구조로 못박는다. 판정 함수가 데이터셋을 인자로 받으면 **언젠가 다시** 조회가
    앞으로 온다 — 받을 수 없게 두는 편이 확실하다."""
    import inspect

    import api.routes.app_data_runtime as rt
    sig = inspect.signature(rt._judge)
    assert "dataset" not in sig.parameters, "판정이 데이터셋을 알고 있다"
    src = inspect.getsource(rt.get_schema)
    assert src.index("_judge(") < src.index("_dataset("), "데이터셋을 판정보다 먼저 푼다"
