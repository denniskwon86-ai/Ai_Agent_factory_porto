"""★★★ 게시가 **그 판이 사는 평면**에 물질화한다 — 아니면 앱이 영영 안 열린다. (2026-08-27 실측)

## ⚠️⚠️ 무엇이 있었나

`_materialize_contract_for_release` 가 `app_data_service`(**운영 평면**)를 직접 잡고 있었다.
그런데 게시되는 판은 **후보**이고, 후보를 확인하는 쪽은 전부 Preview 평면을 본다:

    쓰는 곳 : 게시 → `app_data_service`            → `data/app_data.db`      (운영)
    찾는 곳 : 증명 발급 · 승격 검사 → `_candidate_plane` → `data/app_data_preview.db` (Preview)

실측 결과 둘 다 터졌다.

  ① **앱을 열 길이 하나도 없었다.** `TEST001` 은 7/7 완주하고 계약까지 APPROVED 였는데
     승격 검사가 「계약에 있는 데이터셋이 물질화되지 않았습니다: ['accounts', 'users']」로
     막았다. 증명 발급도 같은 평면을 보므로 같은 자리에서 막힌다.
  ② **검토 안 된 판이 운영 평면에 썼다.** 운영 `app_data.db` 에 `accounts`·`users` 가
     실제로 들어가 있었다(Preview 평면에는 없었다). Preview 경계가 막으려던 바로 그것이다.

★ 게시 경로의 주석은 「그전까지 이 판은 Preview 평면만 만지고 운영 데이터에 닿지
  않는다(F-1)」고 **적혀 있었다.** 주석이 코드를 대신 주장한 자리다.

## ⚠️ 왜 5,246건이 초록인 채로 이걸 놓쳤나

Preview 경계 시험들은 `viewing_context` 와 평면을 **직접 넣어 준다**(monkeypatch). 넣어 준
값끼리는 늘 맞으므로, 「제품이 실제로 어느 평면을 고르는가」는 아무도 안 물었다.
그래서 이 파일은 **평면을 일치시켜 주지 않는다** — 두 경로가 같은 출처에서 평면을
가져오는지를 묻고, 물질화가 **받은 평면에만** 쓰는지를 본다.
"""
import ast
import inspect
import json
import os
import textwrap

import pytest

from core.wbs_artifact_kind import PROFILE_V1


# ── ① 쓰는 곳과 찾는 곳이 **같은 출처**인가 ────────────────────────────────

def test_게시와_승격검사가_같은_함수로_평면을_고른다():
    """★★★ **이 파일의 요지.** 평면을 두 곳에서 따로 정하면 또 갈린다."""
    import api.routes.factory_control as fc

    for fn in (fc.create_release, fc.promotion_check):
        src = inspect.getsource(fn)
        assert "_candidate_plane" in src, (
            f"{fn.__name__} 이 `_candidate_plane` 을 쓰지 않는다 — "
            "평면을 따로 정하면 쓰는 곳과 찾는 곳이 갈린다")


def test_물질화_함수는_평면을_스스로_고르지_않는다():
    """⚠️ 안에서 운영 싱글턴을 잡으면 부르는 쪽이 무엇을 주든 소용없다."""
    import api.routes.factory_control as fc

    fn = fc._materialize_contract_for_release
    #: ⚠️ **글자가 아니라 코드를 본다.** 설명글에는 결함의 이름이 그대로 적혀 있어야
    #:   다음 사람이 무슨 일이 있었는지 안다 — 원문 검색으로 하면 이 시험이 자기
    #:   주석에 걸린다. AST 는 주석도 문서도 보지 않는다.
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {a.asname or a.name
             for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
             for a in n.names}
    assert "app_data_service" not in used, (
        "물질화가 운영 평면 싱글턴을 직접 잡는다 — 후보 판이 운영 데이터에 쓴다")
    assert "plane" in inspect.signature(fn).parameters, "평면을 인자로 받지 않는다"


# ── ② 받은 평면에만 쓴다 ──────────────────────────────────────────────────

@pytest.fixture()
def _contract(tmp_path, monkeypatch):
    """계약 원문 하나를 임시 뿌리에 둔다. **운영 `data/` 는 열지 않는다.**"""
    import nodes.contract as nc

    path = tmp_path / "app_runtime_contract.json"
    path.write_text(json.dumps({"schema_version": "1.0", "status": "APPROVED",
                                "datasets": [{"name": "widgets", "fields": []}]},
                               ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(nc, "contract_path", lambda root: str(path), raising=False)
    return str(path)


def test_물질화는_건네받은_평면에_쓴다(_contract, monkeypatch):
    """★ 감시자를 세우고 **무엇을 받았는지** 본다 — 「평면을 넘긴다」가 아니라
    「그 평면이 도착한다」를 확인한다."""
    import api.routes.factory_control as fc
    from core import contract_materializer as cm

    seen = {}
    sentinel = object()

    class _Out:
        datasets = [{"name": "widgets"}]
        resolved = []

    monkeypatch.setattr(cm, "materialize",
                        lambda contract, **kw: (seen.update(kw), _Out())[1])

    out = fc._materialize_contract_for_release(
        "PX", "PX_20260827_000001", actor_id="tester",
        profile=PROFILE_V1,
        ctx={"tenant_id": "t", "scope_node_id": "s", "entity_mode": "REAL"},
        plane=sentinel)

    assert out["state"] == "MATERIALIZED", out
    assert seen.get("app_data") is sentinel, (
        f"건네준 평면이 아니라 {seen.get('app_data')!r} 에 물질화했다")


def test_평면을_모르면_아무_데도_쓰지_않는다(_contract, monkeypatch):
    """★★★ 모를 때의 기본값이 **가장 위험한 평면**이면 안 된다.

    ⚠️ 종전 구현의 기본값이 정확히 운영 평면이었고, 그것이 이 결함이다."""
    import api.routes.factory_control as fc
    from core import contract_materializer as cm

    called = []
    monkeypatch.setattr(cm, "materialize",
                        lambda *a, **kw: called.append(kw))

    out = fc._materialize_contract_for_release(
        "PX", "PX_20260827_000002", actor_id="tester",
        profile=PROFILE_V1,
        ctx={"tenant_id": "t", "scope_node_id": "s", "entity_mode": "REAL"},
        plane=None)

    assert out["state"] == "FAILED", out
    assert not called, "평면을 모르는데 물질화했다"
    assert "평면" in out["detail"] or "생애주기" in out["detail"], out["detail"]


# ── ③ 후보의 평면은 Preview 다 ───────────────────────────────────────────

def test_후보_판의_평면은_Preview_다(monkeypatch):
    """⚠️ 여기서 평면을 **직접 만들어 넣지 않는다** — 제품이 고르는 것을 그대로 본다."""
    from core import app_preview
    from core.program_lifecycle import program_lifecycle

    import api.routes.factory_control as fc

    monkeypatch.setattr(program_lifecycle, "get_status",
                        lambda rid: {"status": "candidate"}, raising=False)
    plane = fc._candidate_plane("PX_20260827_000003")
    assert plane is not None
    assert plane is app_preview.preview_app_data(), (
        "후보 판이 Preview 평면을 쓰지 않는다 — 검토 전 판이 운영 데이터에 닿는다")


def test_운영_판의_평면은_운영이다(monkeypatch):
    """★ 반대쪽도 본다 — 한쪽만 보면 「전부 Preview」로 고쳐도 초록이 된다."""
    from core import app_preview
    from core.program_lifecycle import program_lifecycle

    import api.routes.factory_control as fc

    monkeypatch.setattr(program_lifecycle, "get_status",
                        lambda rid: {"status": "active"}, raising=False)
    plane = fc._candidate_plane("PX_20260827_000004")
    assert plane is app_preview.app_data_for(app_preview.AUDIENCE_OPERATIONAL)


def test_두_평면은_서로_다른_파일이다():
    """★★★ 대조군이 진짜 대조군인지 먼저 증명한다 — 두 평면이 같은 DB 를 가리키면
    위 시험들은 전부 무의미하게 초록이다."""
    from core import app_preview as ap

    assert (ap.db_path(ap.AUDIENCE_OPERATIONAL)
            != ap.db_path(ap.AUDIENCE_PREVIEW)), "두 평면이 같은 파일이다"
