"""★★★ [트랙 G] 봉합한 라우터는 **익명에게 아무것도 주지 않는다** — 라우터에서 직접 뽑아 센다.

## 왜 이 파일이 «목록» 이 아니라 «라우터 순회» 인가

`test_planning_control_gate.py` 의 `READ_PATHS` 는 손으로 관리하는 목록이었고, 거기에
`/facts` 가 빠져 있어서 **익명이 경영계획 사실 20건(금액 포함)을 받는 것을 그 파일이
통과시켰다.** 같은 라우터의 다른 GET 5개는 막혀 있었으므로 「이 라우터는 통제된다」로 보였다.

⚠️ **목록을 손으로 관리하면 «새 라우트를 넣으라» 는 주석은 지켜지지 않는다.** 그래서 트랙 G 가
  봉합하는 16개 파일은 처음부터 **라우터 객체를 읽어** 전수 검사한다. 파일을 등록하는 순간
  그 파일의 **모든** 라우트가 검사 대상이 되고, 나중에 라우트를 추가해도 자동으로 걸린다.

## 세는 규칙 — 여기가 이 파일의 핵심이다

★★ **422 를 «차단» 으로 세지 않는다.** 2026-08-05 실측에서 무방비 GET 109개 중 17개가 422
  (파라미터 부족)였고, 그것을 「차단됨」으로 세면 **값을 채우면 열리는 경로**가 통과한다.
  통제는 «요청이 잘못됐다» 가 아니라 «당신이 누구인지 모른다» 로 답해야 한다.

★★ **파라미터를 주지 않는 호출을 반드시 포함한다.** `/planning/facts` 유출의 두 번째 겹이
  이것이었다 — `org_id` 를 비우면 정규화할 대상이 없어 범위 판정이 통과하고, 저장소로 넘어가는
  범위도 비어 행 필터가 걸리지 않는다. 즉 **파라미터를 주지 않는 것이 가장 넓은 조회다.**
  「범위를 명시하면 거부된다」만 확인하면 이 경로를 영원히 못 본다.

★ **200 은 물론이고 404·409 도 통과가 아니다.** 자원이 없어서 404 가 난 것은 통제가 아니라
  **우연**이다(그 자원이 생기는 순간 열린다). 익명에게 허용되는 응답은 401·403 뿐이다.

## 등록부

봉합을 마친 파일만 여기 넣는다. ⚠️ **봉합하지 않은 파일을 미리 넣지 않는다** — 빨간 테스트를
켜 두면 사람이 게이트를 끄고, 그러면 게이트가 아니라 소음이 된다.
"""
import pytest
from fastapi.testclient import TestClient

#: ★★ [P0-1C] 이 파일은 **「당신이 누구인지 모른다」고 답하는가** 를 본다. 즉 인증 경로 자체다.
#  `tests/plugin_test_auth.py` 의 principal override 가 걸리면 익명 요청에도 신원이 생겨
#  봉인이 뚫린 것을 **못 본다** — 실제로 이 마커를 붙이기 전 2건이 그렇게 통과했다.
pytestmark = pytest.mark.real_auth

#: (모듈 경로, 사람이 읽는 이름). 트랙 G 진행에 따라 늘어난다 — 16개가 목표다.
SEALED_ROUTERS = [
    ("api.routes.benchmark_control", "골든 벤치마크"),
    ("api.routes.format_control", "문서 서식"),
    ("api.routes.crosswalk_control", "크로스워크"),
    ("api.routes.workspace_control", "작업공간 공유·승격"),
    ("api.routes.lineage_control", "데이터 품질·계보"),
    ("api.routes.connector_control", "커넥터"),
    ("api.routes.enterprise_context_control", "전사 컨텍스트"),
    ("api.routes.glossary_control", "용어 사전"),
    ("api.routes.program_control", "프로그램"),
    ("api.routes.readiness_control", "도입 준비"),
    ("api.routes.shadow_control", "섀도 실행"),
    ("api.routes.reference_control", "참조 데이터"),
    ("api.routes.factory_control", "공장 실행 기록"),
    ("api.routes.advisor_control", "상담 플레이북"),
    ("api.routes.jarvis_control", "자비스 컨텍스트"),
    ("api.routes.ledger_control", "결정 원장"),
]

#: ★★★ **쓰기 탐침을 돌려도 되는 라우터.** 2차 검사(«식별만으로 열리는 쓰기가 없다»)는
#: 여기 있는 것만 찌른다.
#:
#: ⚠️⚠️ **[2026-08-07 실제 사고] 이 목록이 없을 때 탐침이 LLM 비용을 썼다.**
#:   16개 라우터 전체에 쓰기 탐침을 돌렸더니 `POST /factory/{pid}/supervisor/chat` ·
#:   `/heal` · `/sprint/revision` 이 **진짜로 실행됐다** — 로그에 Gemini 호출과
#:   「Sprint Loop Cancelled」가 찍혔다. DB 는 `tmp_path` 로 격리돼 있지만 **LLM 호출은
#:   격리되지 않는다.** 테스트 격리를 «파일·DB» 로만 생각한 것이 틀렸다.
#:
#: ★ 그래서 익명 GET 탐침(1차)은 전 라우터에 돌리되, **쓰기 탐침은 명시적으로 허용한 것만**
#:   돌린다. 라우터를 여기 올리기 전에 「이 파일의 쓰기를 눌러도 바깥으로 나가는 것이 없는가」를
#:   한 번 답해야 한다.
WRITE_PROBE_ROUTERS = {
    "api.routes.benchmark_control",     # evaluate 는 use_llm_judge=False 가 기본
    "api.routes.format_control",        # 파일 쓰기뿐
    "api.routes.crosswalk_control",     # propose 는 use_llm=False 가 기본
    "api.routes.workspace_control",     # DB 쓰기뿐
    "api.routes.lineage_control",       # DB 쓰기뿐
    "api.routes.connector_control",     # execute 는 어댑터 미등록 시 실패
}

#: **쓰지 않는 POST.** 조회인데 본문이 길어 POST 를 쓰는 라우트들 — 아래 2차 검사(«식별만으로
#: 열리는 쓰기가 없다»)에서 제외한다.
#:
#: ⚠️ 자동으로 판별할 방법이 없다(핸들러가 저장소를 부르는지 정적으로 알 수 없다). 그래서
#:   **적어서 선언하게** 한다 — 목록에 올리는 순간 「이것이 정말 읽기인가」를 한 번 답해야 하고,
#:   새로 생기는 POST 는 기본이 «쓰기» 라 그냥 두면 검사에 걸린다. 조용히 통과하는 쪽이 기본이
#:   되면 다음 진짜 쓰기도 같이 새어 나간다.
READ_ONLY_POSTS = {
    # 계약 위반 여부만 계산해 돌려준다. 저장하지 않는다.
    "POST /api/v1/connectors/{connector_id}/validate",
}

#: 경로 파라미터에 채울 값. **존재하지 않는 id 를 쓴다** — 존재하는 것을 쓰면 404 가 «통제» 로
#: 오독될 여지가 없어지는 대신, 익명이 실제 자원을 건드릴 수 있다.
DUMMY = "__track_g_probe__"


def _fill(path: str, endpoint=None) -> str:
    """경로 파라미터를 **이름과 무관하게, 타입에 맞게** 채운다.

    ⚠️ 처음에는 `{scenario_id}`·`{id}` 만 치환했다. 그러자 `{format_id}` 를 가진 라우트가
      «채우지 못한 파라미터» 로 실패했는데, 그건 **통제 결함이 아니라 검사 도구의 결함**이다.
    ⚠️⚠️ 그 다음에는 `{proposal_id}` 가 `int` 인데 문자열을 넣어 422 가 났다. 그것도 도구
      결함이다 — 그리고 **422 는 인가에 도달하지 못했다는 뜻**이므로 그대로 두면 «막혔다» 로
      오독된다. 도구 결함과 제품 결함이 같은 빨강으로 보이면 사람은 게이트를 끈다."""
    import inspect
    import re
    ann = {}
    if endpoint is not None:
        try:
            ann = {n: pr.annotation for n, pr in inspect.signature(endpoint).parameters.items()}
        except (TypeError, ValueError):
            ann = {}

    def _sub(m):
        name = m.group(1).split(":")[0]
        return "1" if ann.get(name) in (int, float) else DUMMY

    return re.sub(r"\{([^}]+)\}", _sub, path)


def _upload_fields(endpoint) -> list:
    """이 라우트가 요구하는 파일 파라미터 이름들. multipart 라우트를 가려낸다.

    ⚠️ JSON 만 보내면 업로드 라우트는 «파일이 없다» 로 422 를 낸다 — 인가에 도달하지 못한다."""
    import inspect
    from fastapi import UploadFile
    if endpoint is None:
        return []
    try:
        params = inspect.signature(endpoint).parameters
    except (TypeError, ValueError):
        return []
    return [n for n, pr in params.items()
            if pr.annotation is UploadFile or "UploadFile" in str(pr.annotation)]


def _dummy_value(ann):
    import typing
    origin = typing.get_origin(ann)
    if origin in (list, tuple, set):
        return []
    if origin is dict:
        return {}
    if origin is not None:                       # Optional[X] 등 — 첫 인자로 판단한다
        args = [a for a in typing.get_args(ann) if a is not type(None)]
        return _dummy_value(args[0]) if args else DUMMY
    if ann is bool:
        return False
    if ann is int:
        return 1
    if ann is float:
        return 1.0
    return DUMMY


def _dummy_body(route) -> dict:
    """라우트의 요청 모델을 읽어 **검증을 통과하는 최소 본문**을 만든다.

    ★★ 왜 필요한가 — 이것이 이 게이트가 잡은 두 번째 사실이다.
      FastAPI 는 **본문 검증을 인가보다 먼저** 수행한다. 그래서 빈 본문으로 POST 하면 422 가
      나고, 그 422 를 보고 「막혔다」고 세면 **인가 검사는 한 번도 실행되지 않은 채 초록**이 된다.
      공격자는 틀린 본문을 보내지 않는다 — 올바른 본문을 보낸다. 게이트도 그래야 한다.

    ⚠️ 값이 유효한지는 상관없다. 인가에 **도달**하는 것이 목적이다."""
    # ⚠️ 이 FastAPI 판에서는 `body_field.type_`·`.annotation` 이 **둘 다 None** 이다.
    #   모델은 `field_info.annotation` 에 있다. 셋을 순서대로 보는 이유는 판올림 때 조용히
    #   None 이 되어 **본문이 빈 dict 로 만들어지고 그때 422 가 «통제» 로 오독되기** 때문이다.
    bf = getattr(route, "body_field", None)
    model = None
    for holder, attr in ((bf, "type_"), (bf, "annotation"),
                         (getattr(bf, "field_info", None), "annotation")):
        model = getattr(holder, attr, None) if holder is not None else None
        if getattr(model, "model_fields", None):
            break
    fields = getattr(model, "model_fields", None)
    if not fields:
        return {}
    return {name: _dummy_value(f.annotation)
            for name, f in fields.items() if f.is_required()}


def _routes(module_path: str):
    """라우터에서 (method, path) 를 전수로 뽑는다. **여기가 목록을 대신한다.**"""
    import importlib
    mod = importlib.import_module(module_path)
    out = []
    for r in getattr(mod.router, "routes", []):
        path = getattr(r, "path", "")
        for m in sorted(getattr(r, "methods", set()) or set()):
            if m in ("HEAD", "OPTIONS"):
                continue
            ep = getattr(r, "endpoint", None)
            out.append((m, _fill(path, ep), _dummy_body(r), _upload_fields(ep), path))
    assert out, f"{module_path} 에서 라우트를 하나도 찾지 못했다 — 검사가 헛돌고 있다"
    return out


def _send(client, method, url, body, uploads, headers=None):
    """인가에 **도달하는** 요청을 만든다 — multipart 라우트에는 파일을 붙인다."""
    if method == "GET":
        return client.request(method, url, headers=headers)
    if uploads:
        files = {n: ("probe.csv", b"a,b\n1,2\n", "text/csv") for n in uploads}
        return client.request(method, url, files=files, headers=headers)
    return client.request(method, url, json=body, headers=headers)


def _cases():
    for module_path, label in SEALED_ROUTERS:
        for method, url, body, uploads, raw in _routes(module_path):
            yield pytest.param(method, url, body, uploads, label,
                               id=f"{method} {raw}")


@pytest.fixture()
def client(monkeypatch, ecm_org_seed):
    """권한 강제를 켠 앱.

    ⚠️ 앞뒤로 스코프 캐시를 비운다 — 강제를 켠 캐시가 남으면 뒤에 도는 다른 파일의 테스트가
      그것을 물려받는다. 실제로 그렇게 «혼자 돌면 통과, 전체로 돌면 실패» 가 났다."""
    import config
    from core.org_directory import org_directory
    org_directory._invalidate()
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    from main import app
    try:
        yield TestClient(app)
    finally:
        org_directory._invalidate()


@pytest.mark.parametrize("method,url,body,uploads,label", list(_cases()))
def test_anonymous_gets_nothing(client, method, url, body, uploads, label):
    """익명 호출은 **401 또는 403** 이어야 한다.

    ⚠️ 404·409·422 는 실패로 센다. 200 은 «0건 + blocked_reason» 일 때만 인정한다
      — 위 «세는 규칙» 참조."""
    r = _send(client, method, url, body, uploads)
    assert r.status_code != 422, (
        f"[{label}] {method} {url} 가 422 를 냈다 — 인가에 **도달하지 못했다**는 뜻이다. "
        f"`_dummy_body` 가 이 라우트의 요청 모델을 못 만든 것이므로 검사 도구를 고쳐야 한다: "
        f"{r.text[:200]}")
    if r.status_code == 200:
        # ★★ **200 을 통째로 면제하지 않는다 — 조건을 검사한다.**
        #   일부 목록 라우트는 일부러 «0건 + 이유» 로 답한다(`crosswalk.list_systems` 등).
        #   화면이 «자료가 없다» 와 «볼 수 없다» 를 구분해야 하기 때문이고, 그것은 이 저장소가
        #   지키는 규칙(조회 실패 ≠ 0건)이다. 그 형태는 자료를 내보내지 않으므로 통제로 인정한다.
        #   ⚠️ 다만 **면제 목록으로 두지 않는다.** 목록은 손으로 관리되고 언젠가 「이것도 예외」가
        #     붙는다. 대신 «자료가 비어 있고 이유가 붙어 있다» 를 그때그때 확인한다 —
        #     자료가 한 건이라도 실려 나오면 그 순간 실패한다.
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        reason = str(body.get("blocked_reason") or "").strip()
        data = body.get("data")
        assert reason and not data, (
            f"[{label}] {method} {url} 가 익명에게 200 을 줬다. «0건 + blocked_reason» 형태여야 "
            f"인정하는데 blocked_reason={reason!r}, data={str(data)[:120]!r} 이다.")
        return
    assert r.status_code in (401, 403), (
        f"[{label}] {method} {url} 가 익명에게 {r.status_code} 로 응답했다. "
        f"401/403 이 아니면 통제가 아니다 — 본문 앞부분: {r.text[:160]}")


def test_write_routes_are_not_merely_identified(client):
    """★ **식별만으로 열리는 쓰기가 없어야 한다.**

    익명 차단은 «누구인지 모르는 사람» 만 막는다. 등록된 일반 사용자가 골든 기준을 승격시킬 수
    있으면 봉합이 절반만 된 것이다 — 그리고 그 절반은 익명 검사만으로는 **영원히 보이지 않는다.**

    `hikwon_17@lsmnm.com` 은 viewer 다(`test_planning_control_gate` 가 실측해 고른 계정).
    이 계정으로 쓰기가 되면 실패다."""
    viewer = {"X-Factory-User": "hikwon_17@lsmnm.com"}
    opened = []
    for module_path, label in SEALED_ROUTERS:
        if module_path not in WRITE_PROBE_ROUTERS:
            continue                     # 위 «쓰기 탐침을 돌려도 되는 라우터» 참조
        for method, url, body, uploads, raw in _routes(module_path):
            if method == "GET" or f"{method} {raw}" in READ_ONLY_POSTS:
                continue
            # ★ 검증을 통과하는 본문·파일로 보낸다 — 422 는 «인가에 도달하지 못함» 이다.
            r = _send(client, method, url, body, uploads, headers=viewer)
            # 403 이면 통제, 401 은 이 계정이 식별되지 않은 것이므로 별도 문제로 드러낸다.
            if r.status_code not in (401, 403):
                opened.append(f"{method} {url} → {r.status_code}")
    assert not opened, "viewer 에게 열려 있는 쓰기 라우트: " + "; ".join(opened)


def test_registry_matches_track_g_progress():
    """등록부와 `PROGRESS.md` 의 트랙 G 진척이 **같은 수를 말하는지** 본다.

    ⚠️ 진척 표가 코드보다 앞서가는 것이 이 저장소의 오래된 실패 방식이다(「다른 세션의 «완료»
      주장도 코드에서 확인되기 전에는 반영하지 않는다」 — `PROGRESS.md` 머리말).
      여기서는 **코드가 정본**이고, 표가 그것을 넘어서면 실패한다."""
    import pathlib
    import re
    text = pathlib.Path("PROGRESS.md").read_text(encoding="utf-8")
    m = re.search(r"^## G\..*?(\d+)\s*/\s*16", text, re.M)
    assert m, "PROGRESS.md 에서 트랙 G 진척(n/16)을 찾지 못했다"
    claimed = int(m.group(1))
    assert claimed <= len(SEALED_ROUTERS), (
        f"PROGRESS.md 는 트랙 G 를 {claimed}/16 이라 하는데 실제로 봉합·검증된 라우터는 "
        f"{len(SEALED_ROUTERS)}개다. 표가 코드보다 앞서 있다.")


def test_probe_does_not_leak_into_real_projects_dir():
    """★★★ [2026-08-07 실측] **탐침이 실제 `projects/` 에 디렉터리를 남겼다.**

    `projects/__track_g_probe__` 가 남아 있었고, 그 디렉터리 때문에
    `test_agent_asset_adapter::test_skill_names_are_korean_not_slugs` 가 **전체 실행에서만**
    실패했다(혼자 돌면 통과). 지우니 exit 0 이 됐다.

    ⚠️ `conftest.py` 는 DB 를 `tmp_path` 로 격리하지만 **`projects/` 는 격리하지 않는다.**
      라우트를 통해 프로젝트를 만드는 탐침은 그 사실을 알고 써야 한다.

    ★ 「혼자 돌면 통과, 전체로 돌면 실패」를 보면 순서를 의심하기 전에 **«남긴 것»** 을 먼저
      찾으라 — 이 저장소에서 두 번 다 그것이었다.

    이 검사는 탐침 이름의 흔적이 남지 않았는지 본다. 남았다면 **다른 테스트를 깨뜨리기 전에**
    여기서 걸린다."""
    import os
    leaked = []
    for root in ("projects", "library"):
        if not os.path.isdir(root):
            continue
        leaked += [os.path.join(root, n) for n in os.listdir(root) if DUMMY in n]
    assert not leaked, (
        f"탐침이 실제 작업 디렉터리에 흔적을 남겼다: {leaked} — 지우고, 그 탐침이 왜 "
        f"인가를 통과했는지 확인할 것(막혔다면 아무것도 만들어지지 않는다).")
