"""★★★ 프로젝트 삭제 정책 (사용자 결정 2026-08-07).

> 「이미 등록된 프로젝트는 **등록자가 지울 수 있고**(삭제 플래그만 처리, 실제 삭제는 하지
>  않음, 데이터는 남겨둠), **타부서 또는 다른 사람에게 공유·전달 단계까지 된 건 admin 만**
>  삭제 처리 가능하게 하고, **실제 지울 수 있는 권한도 admin 만** 가지도록.」

## 봉합 전 실측 결함

```
viewer(시험 계정) → DELETE /api/v1/factory/projects/{id} → 200
```

읽기 전용 계정이 프로젝트를 **rmtree** 로 지울 수 있었다. 원인은 `assert_project_writable`
하나만 걸려 있었고, 그 함수에 「소유권 미기록 프로젝트는 통과」라는 **읽기용 하위호환**이
들어 있었기 때문이다. 되돌릴 수 없는 삭제에 읽기용 관대함을 쓰면 안 된다.

## 이 파일이 확인하는 네 가지

1. 등록자는 표시 삭제만 — 파일이 **남아 있다**
2. 남의 프로젝트는 못 지운다
3. 공유·전달된 것은 등록자도 못 지운다 (admin 만)
4. 실제 삭제(`?purge=true`)는 admin 만

★ 그리고 다섯째 — **모르면 막는다.** 공유 여부를 확인하지 못하면 «공유 안 됨» 이 아니다.
"""
import json
import os

import pytest

from tests import org_seed

from core import project_deletion as pdel


class _Scope:
    """`AccessScope` 의 최소 대역. 판정이 보는 속성만 갖는다."""
    def __init__(self, unrestricted=False):
        self.unrestricted = unrestricted


ADMIN = _Scope(unrestricted=True)
USER = _Scope()


@pytest.fixture()
def proj(tmp_path, monkeypatch):
    """빈 프로젝트 하나. 라이브러리도 격리한다 — 실제 `library/` 를 읽으면 다른 프로젝트의
    릴리스가 섞여 «공유됨» 판정이 흔들린다."""
    from core import library_paths
    monkeypatch.setattr(library_paths, "_LIBRARY_DIR", str(tmp_path / "library"))
    root = tmp_path / "projects" / "p1"
    root.mkdir(parents=True)
    (root / "project_meta.json").write_text('{"template_id": "default"}', encoding="utf-8")
    (root / "00_wbs_master_plan.json").write_text("{}", encoding="utf-8")
    return str(root)


def _own(monkeypatch, owner: str):
    """`org_directory.get_ownership` 만 대역으로 바꾼다."""
    from core import org_directory as od
    monkeypatch.setattr(od.org_directory, "get_ownership",
                        lambda kind, rid: {"owner_user_id": owner} if owner else None)


# ── ① 등록자는 표시 삭제만, 파일은 남는다 ────────────────────────────────────
def test_owner_may_soft_delete_and_files_survive(proj, monkeypatch):
    _own(monkeypatch, "a@x.com")
    v = pdel.classify(USER, "a@x.com", "p1")
    assert v.may_soft_delete, v.reason
    assert not v.may_hard_delete, "등록자에게 실제 삭제가 열려 있다"

    pdel.mark_deleted(proj, "a@x.com", "정리")
    assert pdel.is_deleted(proj)
    # ★ 데이터는 남는다 — 이것이 결정의 핵심이다.
    assert os.path.exists(os.path.join(proj, "00_wbs_master_plan.json"))
    meta = json.loads(open(os.path.join(proj, "project_meta.json"), encoding="utf-8").read())
    assert meta["template_id"] == "default", "표시 삭제가 기존 메타를 덮어썼다"
    assert meta[pdel.DELETED_BY] == "a@x.com"

    pdel.restore(proj)
    assert not pdel.is_deleted(proj), "되돌리기가 동작하지 않는다"


# ── ② 남의 프로젝트 ─────────────────────────────────────────────────────────
def test_other_user_may_not_delete(proj, monkeypatch):
    _own(monkeypatch, "a@x.com")
    v = pdel.classify(USER, "b@x.com", "p1")
    assert not v.may_soft_delete
    assert "a@x.com" in v.reason, f"누가 등록자인지 말해 주지 않는다: {v.reason}"


def test_anonymous_may_not_delete(proj, monkeypatch):
    _own(monkeypatch, "a@x.com")
    assert not pdel.classify(USER, "", "p1").may_soft_delete


# ── ③ 공유·전달된 것은 admin 만 ─────────────────────────────────────────────
def test_shared_project_blocks_owner(proj, monkeypatch, tmp_path):
    """릴리스가 공유돼 있으면 **등록자도** 못 지운다."""
    _own(monkeypatch, "a@x.com")
    (tmp_path / "library" / "p1_20260807_101112").mkdir(parents=True)
    from core.workspace_promotion import workspace
    monkeypatch.setattr(workspace, "list_shares",
                        lambda **kw: [{"share_id": "s1"}])
    monkeypatch.setattr(workspace, "list_forks", lambda **kw: [])
    monkeypatch.setattr(workspace, "list_promotions", lambda status="": [])

    v = pdel.classify(USER, "a@x.com", "p1")
    assert v.shared is True
    assert not v.may_soft_delete
    assert "공유" in v.reason

    # 같은 상황에서 admin 은 된다 — 결정의 후반부다.
    va = pdel.classify(ADMIN, "root@x.com", "p1")
    assert va.may_soft_delete and va.may_hard_delete


def test_unshared_release_does_not_block(proj, monkeypatch, tmp_path):
    """릴리스가 있어도 **공유되지 않았으면** 등록자가 지울 수 있다."""
    _own(monkeypatch, "a@x.com")
    (tmp_path / "library" / "p1_20260807_101112").mkdir(parents=True)
    from core.workspace_promotion import workspace
    monkeypatch.setattr(workspace, "list_shares", lambda **kw: [])
    monkeypatch.setattr(workspace, "list_forks", lambda **kw: [])
    monkeypatch.setattr(workspace, "list_promotions", lambda status="": [])
    monkeypatch.setattr(pdel, "_was_delivered", lambda rid: False)
    assert pdel.classify(USER, "a@x.com", "p1").may_soft_delete


def test_sibling_project_release_is_not_counted(proj, monkeypatch, tmp_path):
    """★ `p1_2` 의 릴리스를 `p1` 의 것으로 세지 않는다.

    ⚠️ `startswith(pid + "_")` 로 세면 `p1_2_20260807_101112` 가 `p1` 의 릴리스로 잡히고,
      **남의 프로젝트 공유 이력 때문에 내 프로젝트 삭제가 막힌다.** 원인을 알 길이 없는
      거부가 되므로 접미사 형식을 엄격히 본다."""
    _own(monkeypatch, "a@x.com")
    (tmp_path / "library" / "p1_2_20260807_101112").mkdir(parents=True)
    assert pdel.releases_of("p1") == []


# ── ④ 실제 삭제는 admin 만 ──────────────────────────────────────────────────
def test_hard_delete_is_admin_only(proj, monkeypatch):
    _own(monkeypatch, "a@x.com")
    from core.workspace_promotion import workspace
    monkeypatch.setattr(workspace, "list_shares", lambda **kw: [])
    monkeypatch.setattr(workspace, "list_forks", lambda **kw: [])
    monkeypatch.setattr(workspace, "list_promotions", lambda status="": [])
    v = pdel.classify(USER, "a@x.com", "p1")
    assert not v.may_hard_delete
    with pytest.raises(pdel.DeletionError):
        v.assert_hard()
    assert pdel.classify(ADMIN, "root@x.com", "p1").may_hard_delete


# ── ⑤ 모르면 막는다 ────────────────────────────────────────────────────────
def test_unknown_owner_blocks(proj, monkeypatch):
    """★★ 소유권 기록이 없으면 «누구나» 가 아니라 «관리자만» 이다.

    종전 `assert_project_writable` 의 「소유권 미기록 프로젝트에 대한 관대함」이 삭제까지
    따라와 viewer 가 200 을 받았다. 읽기의 하위호환을 삭제에 쓰지 않는다."""
    _own(monkeypatch, "")
    v = pdel.classify(USER, "a@x.com", "p1")
    assert not v.may_soft_delete
    assert "등록자 기록이 없어" in v.reason


def test_unknown_share_state_blocks(proj, monkeypatch, tmp_path):
    """★★ 공유 여부를 **확인하지 못하면** «공유 안 됨» 이 아니다.

    저장소가 잠깐 죽은 사이에 공유된 프로젝트가 지워지면 안 된다 — 조회 실패를 0건으로
    두지 않는다는 이 저장소의 규칙이 삭제 판정에도 그대로 적용된다."""
    _own(monkeypatch, "a@x.com")
    (tmp_path / "library" / "p1_20260807_101112").mkdir(parents=True)
    from core.workspace_promotion import workspace

    def _boom(**kw):
        raise RuntimeError("store down")

    monkeypatch.setattr(workspace, "list_shares", _boom)
    monkeypatch.setattr(workspace, "list_forks", lambda **kw: [])
    monkeypatch.setattr(workspace, "list_promotions", lambda status="": [])
    monkeypatch.setattr(pdel, "_was_delivered", lambda rid: False)

    v = pdel.classify(USER, "a@x.com", "p1")
    assert v.shared is None, "확인 실패가 False 로 뭉개졌다"
    assert not v.may_soft_delete
    assert "확인하지 못했습니다" in v.reason


def test_is_deleted_is_false_when_meta_unreadable(tmp_path):
    """meta 를 못 읽으면 «삭제됨» 이 아니다 — 여기서는 **보이는 쪽**이 안전한 실패다.

    ⚠️ 반대로 하면 읽기 오류 하나에 프로젝트가 목록에서 통째로 사라진다."""
    root = tmp_path / "p"
    root.mkdir()
    (root / "project_meta.json").write_text("{ 깨진 json", encoding="utf-8")
    assert pdel.is_deleted(str(root)) is False


# ── 라우트가 실제로 이 정책을 쓰는가 ────────────────────────────────────────
#
# ⚠️ 정책 모듈만 초록이고 라우트가 옛 판정을 그대로 쓰면 아무것도 달라지지 않는다.
#   실측 결함이 «viewer 가 DELETE 로 200» 이었으므로 **그 호출을 그대로 재현**한다.
@pytest.fixture()
def client(monkeypatch, tmp_path, ecm_org_seed, seeded_org):
    """★★ [G1-C3 · 2026-08-13] 탐침 프로젝트를 **실제로 만든다.**

    종전에는 존재하지 않는 id 로 불렀고, 그때는 `assert_project_writable` 의 「소유권 미기록은
    통과」 관대함 덕에 판정이 `pdel.classify` 까지 흘러 403 이 나왔다. 그런데 G1-C3 가
    `assert_project_readable` 에 **문맥 축**을 넣으면서 «메타를 못 읽음 → 404» 가 먼저 걸린다.

    ⚠️ 여기서 단언을 `in (403, 404)` 로 느슨하게 바꾸면 **테스트가 권한 축을 더 이상 확인하지
      않게 된다** — 존재하지 않아서 막히는 것과 권한이 없어서 막히는 것은 다른 사실이고,
      이 파일이 잠그려는 것은 후자다. 그래서 조건을 만들어 권한 경로를 그대로 태운다.

    ⚠️ `core.paths.PROJECTS_DIR` 로 격리한다. 이 한 줄이 없으면 테스트가 **제품 `projects/` 에**
      탐침 디렉터리를 만든다(저장소에서 실제로 겪은 사고)."""
    import json
    import config
    import core.paths
    from core.org_directory import org_directory
    org_directory._invalidate()
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    proj_root = tmp_path / "projects"
    (proj_root / "__deletion_probe__").mkdir(parents=True)
    #: 문맥 축을 통과할 만큼만 채운다 — 테넌트·실행모드·소유 범위(D-014: 하나라도 비면 비노출).
    (proj_root / "__deletion_probe__" / "project_meta.json").write_text(
        json.dumps({"template_id": "default", "owner_dept_id": "hq", "visibility": "dept",
                    "tenant_id": "tenant_default", "entity_mode": "REAL",
                    "enterprise_scope_id": "node_probe"}, ensure_ascii=False),
        encoding="utf-8")
    monkeypatch.setattr(core.paths, "PROJECTS_DIR", str(proj_root), raising=False)
    from main import app
    from fastapi.testclient import TestClient
    try:
        yield TestClient(app)
    finally:
        org_directory._invalidate()


def test_route_blocks_viewer_delete(client):
    """★ 봉합 전 실측: 이 호출이 **200** 이었다."""
    r = client.request("DELETE", "/api/v1/factory/projects/__deletion_probe__",
                       headers={"X-Factory-User": org_seed.VIEWER_A})
    assert r.status_code == 403, f"viewer 삭제가 {r.status_code} 로 통과했다: {r.text[:200]}"


def test_route_blocks_viewer_purge(client):
    r = client.request("DELETE", "/api/v1/factory/projects/__deletion_probe__?purge=true",
                       headers={"X-Factory-User": org_seed.VIEWER_A})
    assert r.status_code == 403, f"viewer 실제 삭제가 {r.status_code} 로 통과했다"


def test_route_blocks_anonymous_delete(client):
    r = client.request("DELETE", "/api/v1/factory/projects/__deletion_probe__")
    assert r.status_code in (401, 403)
