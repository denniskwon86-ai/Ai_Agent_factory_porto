"""★★★ [G1-C3] **목록·상세·쓰기·SSE 가 같은 답을 준다** — 종단 일치.

## 왜 이 파일이 가장 중요한가

`test_unified_visibility_judge.py` 는 판정기가 **옳은지**를 본다. 이 파일은 판정기가
**실제로 불리는지**를 본다. 둘은 다른 사실이고, 이 저장소는 그 차이로 여러 번 다쳤다.

> 「`emit_to` 테넌트 격리를 «완료» 로 보고했는데 실서비스 경로에서 작동하지 않았다.
>  그런데도 테스트는 초록이었다 — 테스트가 `CollaborationEvents` 를 건너뛰고 `bus.emit_to()`
>  를 직접 불렀기 때문이다. **테스트가 실제 배선을 타지 않으면 그 초록은 거짓이다.**」
>  (`docs/handoff/G1C3_UNIFIED_VISIBILITY_HANDOFF_2026-08-12.md` §4)

배선 전 상태가 정확히 이랬다 — 판정기 21건이 전부 초록인데 **제품 코드에서 부르는 곳이
0곳**이었다. 그래서 여기서는 HTTP 라우트를 실제로 부르고 SSE 큐를 실제로 들여다본다.

## 무엇이 어긋나면 사고인가

| 어긋남 | 사용자가 보는 것 |
|---|---|
| 목록엔 있는데 상세가 404 | 「눌렀더니 없다」 |
| 목록엔 없는데 SSE 는 온다 | 볼 수 없는 프로젝트의 진행 상황이 실시간으로 흐른다 |
| 목록엔 없는데 쓰기가 통과 | 보이지도 않는 프로젝트를 실행시킨다 |

셋 다 **조용하다.** 오류가 나지 않으므로 아무도 모른다.
"""
import asyncio
import json

import pytest


#: 문맥 축의 네 갈래를 한 자리에서 만든다. `ok` 는 「보여야 하는가」.
#: ⚠️ 실데이터와 같은 모양으로 채운다 — 운영 프로젝트 61/61 이 세 필드를 갖는다.
CASES = {
    "P_IN":        (dict(tenant_id="tenant_default", entity_mode="REAL",
                         enterprise_scope_id="node_in"), True,  ""),
    "P_TENANT":    (dict(tenant_id="tenant_other",   entity_mode="REAL",
                         enterprise_scope_id="node_in"), False, "TENANT_MISMATCH"),
    "P_MODE":      (dict(tenant_id="tenant_default", entity_mode="SANDBOX",
                         enterprise_scope_id="node_in"), False, "MODE_MISMATCH"),
    "P_UNBOUND":   (dict(tenant_id="tenant_default", entity_mode="REAL",
                         enterprise_scope_id=""),        False, "RESOURCE_UNBOUND"),
}


@pytest.fixture()
def wired(monkeypatch, tmp_path):
    """실제 앱 + 격리된 `projects/` + 무제한 권한자.

    ★ 권한 축을 일부러 **열어 둔다**(무제한). 그래야 여기서 막히는 것이 전부 **문맥 축** 때문임이
      분명해진다 — 두 축이 섞이면 무엇을 검증했는지 알 수 없다.
    ⚠️ `core.paths.PROJECTS_DIR` 로 격리한다. 없으면 제품 `projects/` 에 시험 디렉터리를 만든다."""
    import config
    import core.paths
    from core.org_directory import org_directory

    root = tmp_path / "projects"
    for pid, (meta, _ok, _why) in CASES.items():
        d = root / pid
        d.mkdir(parents=True)
        (d / "project_meta.json").write_text(
            json.dumps({"template_id": "default", "owner_dept_id": "hq",
                        "owner_user_id": "boss@x", "visibility": "dept", **meta},
                       ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(core.paths, "PROJECTS_DIR", str(root), raising=False)
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)

    scope = type("S", (), {"unrestricted": True, "is_admin": True,
                           "readable_dept_ids": frozenset({"hq"}),
                           "readable_scope_nodes": frozenset({"node_in"}),
                           "primary_dept_id": "hq",
                           "can_read": lambda self, d: True,
                           "can_write": lambda self, d: True})()
    monkeypatch.setattr(org_directory, "resolve_scope", lambda uid="": scope)
    monkeypatch.setattr(org_directory, "is_bootstrap", lambda: False)
    monkeypatch.setattr(org_directory, "get_user",
                        lambda uid: {"user_id": uid, "status": "active"} if uid else None)
    monkeypatch.setattr(org_directory, "get_ownership", lambda kind, rid: None)

    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


def _list(client, **params):
    r = client.get("/api/v1/factory/projects", params=params,
                   headers={"X-Factory-User": "boss@x"})
    assert r.status_code == 200, r.text
    return r.json()


# ── ① 목록: 무엇이 보이고, 안 보이는 것의 **사유와 개수**가 실리는가 ───────────

def test_목록은_문맥_밖을_빼고_왜_뺐는지_함께_싣는다(wired):
    """★ 「0건」과 「문맥 밖」과 「못 읽었다」를 화면이 다르게 말할 수 있어야 한다.

    ⚠️ 건수를 싣지 않으면 사용자는 사라진 자료를 **고장**으로 읽는다. 실측에서 그 수가
      59건이었다(검증 샌드박스로 격리한 시험 산출물)."""
    body = _list(wired)
    assert [x["id"] for x in body["data"]] == ["P_IN"]
    assert body["context_blocked_count"] == 3
    #: 정상 격리(다른 테넌트·다른 실행 모드)와 **점검 대상**(못 읽음)을 나눠서 센다.
    assert body["context_needs_attention"] == 1, "미바인딩을 점검 대상으로 세지 않았다"
    assert body["context_blocked_reasons"] == {
        "TENANT_MISMATCH": 1, "MODE_MISMATCH": 1, "RESOURCE_UNBOUND": 1}


def test_목록은_지금_보는_문맥을_함께_알려준다(wired):
    """화면이 「어느 회사·어느 실행 모드로 보고 있는가」를 표시할 수 있어야 한다.
    표시하지 못하면 사용자는 자기가 보는 숫자가 어느 문맥의 것인지 알 수 없다."""
    ctx = _list(wired)["viewing_context"]
    assert ctx["tenant_id"] and ctx["entity_mode"] == "REAL"


# ── ② 상세·쓰기: 목록과 **같은 답**인가 ────────────────────────────────────

@pytest.mark.parametrize("pid", list(CASES))
def test_상세는_목록과_같은_답을_준다(wired, pid):
    """목록에 없는 것을 상세가 열어 주면 「목록 필터」는 통제가 아니라 장식이다.

    ⚠️ 거부는 **404 은폐**다 — 403 은 「그 프로젝트가 존재한다」를 알려 준다(§3.3)."""
    expect_ok = CASES[pid][1]
    r = wired.get(f"/api/v1/factory/{pid}/state/latest",
                  headers={"X-Factory-User": "boss@x"})
    if expect_ok:
        # ⚠️ 라우트 경로가 틀리면 FastAPI 자체 404 가 나고, 그러면 아래 «막혔다» 단언이
        #   **헛되이 통과**한다. 통과 경로를 함께 단언해 그 함정을 막는다.
        assert r.status_code == 200, f"목록엔 있는데 상세가 {r.status_code} 다: {r.text[:200]}"
    else:
        assert r.status_code == 404, f"목록엔 없는데 상세가 {r.status_code} 로 열렸다"
        assert CASES[pid][2] in r.text, "왜 안 보이는지 사유가 없다"


@pytest.mark.parametrize("pid", [p for p, v in CASES.items() if not v[1]])
def test_문맥_밖_프로젝트는_쓰기도_막힌다(wired, pid):
    """★★ **무제한 권한자에게도** 막힌다. 「전권」과 「지금 보는 범위」는 다른 축이고,
    관리자가 A 회사를 보면서 B 회사 프로젝트를 실행시키면 그것은 권한 문제가 아니라 사고다."""
    #: ⚠️ 본문을 함께 보낸다. 빠뜨리면 FastAPI 가 **422 로 먼저** 끊고, 그러면 판정이 아예
    #  불리지 않은 채 「막혔다」로 보인다 — 헛되이 통과하는 검사가 된다.
    r = wired.post(f"/api/v1/factory/{pid}/sprint/stop", json={"task_id": "T1"},
                   headers={"X-Factory-User": "boss@x"})
    assert r.status_code == 404, f"문맥 밖 프로젝트에 쓰기가 {r.status_code} 로 통과했다"


# ── ③ SSE: 목록과 **같은 답**인가 ─────────────────────────────────────────

def _sse_types(bus, q):
    out = []
    while not q.empty():
        line = q.get_nowait()
        if line.startswith("data: "):
            out.append(json.loads(line[6:])["type"])
    return out


@pytest.mark.parametrize("pid", list(CASES))
def test_SSE_는_목록과_같은_답을_준다(monkeypatch, tmp_path, pid):
    """★★★ §3.4 가 「가장 중요」로 표시한 항목.

    목록에 없는 프로젝트의 이벤트가 흘러들면, 그 사람은 **볼 수도 없는 공장의 진행 상황**을
    실시간으로 본다(`NODE_COMPLETED` 는 `state` 전체를 싣는다). 그리고 그 어긋남은 조용하다."""
    import core.paths as paths
    import core.project_visibility as pv
    from core.auth import auth_store
    from core.broadcaster import SSEBroadcaster
    from core.org_directory import org_directory

    meta, expect_ok, _why = CASES[pid]
    monkeypatch.setattr(paths, "workspace_path", lambda *p: "/".join(p), raising=False)
    monkeypatch.setattr(pv, "read_project_ownership",
                        lambda ws: {"owner_dept_id": "hq", "owner_user_id": "boss@x",
                                    "visibility": "dept", **meta})
    monkeypatch.setattr(org_directory, "resolve_scope",
                        lambda uid="": type("S", (), {"unrestricted": True, "is_admin": True,
                                                      "readable_dept_ids": frozenset()})())
    monkeypatch.setattr(org_directory, "is_bootstrap", lambda: False)
    monkeypatch.setattr(org_directory, "get_user",
                        lambda uid: {"user_id": uid, "status": "active"})
    monkeypatch.setattr(auth_store, "session_alive_by_hash", lambda h: True)

    bus = SSEBroadcaster()

    async def scenario():
        agen = bus.subscribe(user_id="boss@x", tenant_id="tenant_default", entity_mode="REAL")
        task = asyncio.ensure_future(agen.asend(None))
        await asyncio.sleep(0.05)
        q = bus.clients[0]
        await bus.broadcast("WBS_UPDATED", {"project_id": pid})
        got = _sse_types(bus, q)
        task.cancel()
        return got

    loop = asyncio.new_event_loop()
    try:
        got = loop.run_until_complete(scenario())
    finally:
        for t in asyncio.all_tasks(loop):
            t.cancel()
        loop.close()

    if expect_ok:
        assert got == ["WBS_UPDATED"], "목록엔 보이는데 이벤트가 오지 않았다(격리가 아니라 고장)"
    else:
        assert got == [], "목록엔 없는 프로젝트의 이벤트가 실시간으로 흘렀다"


# ── ④ 요청 범위 위조: 「요청값을 그대로 믿지 않는다」 ─────────────────────────
#
# ⚠️⚠️ **이 검사는 라우트가 아니라 판정 지점에서 한다.** 이 스위트의 `TestClient` 에서는
#   커스텀 헤더도 쿼리도 라우트까지 도달하지 않는다(실측: 라우트 안에서 언제나 빈 값).
#   그 상태로 라우트를 불러 「404 가 나왔다」를 단언하면, 실제로는 **아무것도 확인하지 못한 채
#   통과**한다 — 이 저장소가 반복해서 겪은 «자기 자신과 합의하는 검사» 다.
#   종단 확인은 pytest 밖에서 실서버로 했고(위조 범위 → 404, 허용 범위 → 200), 여기서는
#   규칙이 판정 지점에 실제로 박혀 있는지를 본다.


def test_고를_수_없는_범위는_404_로_은폐하고_감사에_남긴다(monkeypatch):
    """★ 403 이 아니라 **404** 인 이유 — 403 은 「그 조직이 존재한다」를 알려 준다.
    존재 자체가 다른 회사의 정보다(설계 §3.3 경계표).

    ★★ **은폐는 응답이지 기록이 아니다.** 404 로 돌려주더라도 감사에는 실제 대상과
      요청값을 남긴다 — 남기지 않으면 정상 조회와 권한 상승 시도가 같은 모양이 된다(§3.2)."""
    from fastapi import HTTPException

    import api.deps as deps
    from core.enterprise_context import audit
    from core.org_directory import org_directory

    limited = type("S", (), {"unrestricted": False, "is_admin": False,
                             "readable_dept_ids": frozenset({"hq"}),
                             "readable_scope_nodes": frozenset({"node_in"}),
                             "primary_dept_id": "hq"})()
    monkeypatch.setattr(org_directory, "resolve_scope", lambda uid="": limited)
    seen = []
    monkeypatch.setattr(audit, "record", lambda **kw: seen.append(kw) or True)

    #: 대조군 — 고를 수 있는 범위는 통과해야 한다. 없으면 「전부 막힘」도 초록이 된다.
    ok = deps.viewing_context(deps.Principal("u@x", limited, "node_in"))
    assert ok["scope_node_id"] == "node_in"

    with pytest.raises(HTTPException) as e:
        deps.viewing_context(deps.Principal("u@x", limited, "node_other_company"))
    assert e.value.status_code == 404, "존재를 알리는 403 으로 거절했다"
    assert seen and seen[-1]["resource_id"] == "node_other_company",         "은폐만 하고 감사에 남기지 않았다 — 누가 무엇을 시도했는지 물을 수 없다"
    assert seen[-1]["outcome"] == "denied"
