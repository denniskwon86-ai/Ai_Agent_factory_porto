"""★★★ [D-017 §9 P1-1·P1-3] 범위형 자산 저장소 — 조직이 자산을 소유한다.

## 지금 무엇이 문제였나 (설계 §2.1·§5.3)

자산이 전역 파일 하나였다. `agents_registry.json` 을 모두가 공유하고 `templates/*.json` 도
전역이다. 그래서 **«누가 만들었는지 · 어느 조직 것인지 · 승인은 받았는지 · 언제부터 유효한지»**
를 물을 수 없었다. 한 사람이 저장하면 전 사용자의 파이프라인이 바뀌었다.

## 이 파일이 고정하는 계약

1. **버전을 덮어쓰지 않는다.** 과거 산출물이 «어떤 구성으로 만들어졌는가» 에 답하려면 그때의
   정의가 그대로 있어야 한다.
2. **개정하면 승인이 풀린다.** 승인된 자산의 내용을 바꿔 놓고 승인 상태를 유지하면, 그 승인은
   «읽지 않은 문서에 대한 승인» 이 된다.
3. **초안은 실행되지 않는다.** `DRAFT` 가 도는 순간 검토 단계는 형식이 된다.
4. **소유 조직을 모르는 조직 자산은 보이지 않는다.** «모르니까 보여 준다» 가 한 번 통과하면
   그 뒤로 아무도 소유를 채우지 않는다.
"""
import pytest

from core.agent_assets import (KIND_AGENT, KIND_WORKFLOW, RUNNABLE, ST_APPROVED, ST_DRAFT,
                               ST_RETIRED, ST_REVIEW, VIS_DESCENDANTS, VIS_ENTERPRISE,
                               VIS_PERSONAL, VIS_SCOPE, VIS_SYSTEM, AgentAssetStore, AssetError,
                               AssetNotFound)


@pytest.fixture()
def store(tmp_path):
    return AgentAssetStore(db_path=str(tmp_path / "assets.db"))


def _mk(store, **kw):
    args = dict(kind=KIND_AGENT, name_ko="원료 도입계획", body={"role": "x"},
                created_by="kim", owner_scope_id="node_copper", visibility=VIS_SCOPE)
    args.update(kw)
    return store.create(**args)


# ── 생성 ──────────────────────────────────────────────────────────────────
def test_new_asset_starts_as_draft(store):
    """★★ 만들자마자 승인 상태가 되는 지름길을 두지 않는다.

    ⚠️ 한 번 만들면 그 경로로만 만들어지고, 검토 단계는 아무도 지나지 않는 문이 된다."""
    a = _mk(store)
    assert a["status"] == ST_DRAFT
    assert a["current_version"] == 1
    assert a["runnable"] is False, "초안이 돌면 검토는 형식이 된다"


def test_scope_visibility_requires_owner(store):
    """★★★ 개인 범위가 아니면 **소유 조직이 있어야 한다.**

    ⚠️ 소유가 없으면 나중에 «이 자산은 누구 책임인가» 에 답할 수 없고, 답할 수 없으면
      회수·폐기도 할 수 없다."""
    with pytest.raises(AssetError):
        _mk(store, visibility=VIS_SCOPE, owner_scope_id="")
    with pytest.raises(AssetError):
        _mk(store, visibility=VIS_ENTERPRISE, owner_scope_id="")
    # 개인 범위는 소유 조직 없이도 만들 수 있다 — 만든 사람이 곧 소유자다.
    assert _mk(store, visibility=VIS_PERSONAL, owner_scope_id="")["status"] == ST_DRAFT


def test_creator_is_required(store):
    """★ 누가 만들었는지 모르는 자산은 승인할 수 없다."""
    with pytest.raises(AssetError):
        _mk(store, created_by="")


def test_system_assets_cannot_be_created(store):
    """★★ `SYSTEM` 은 제품 기본의 **표시**이지 만들 수 있는 등급이 아니다."""
    with pytest.raises(AssetError):
        _mk(store, visibility=VIS_SYSTEM)


# ── 버전 ──────────────────────────────────────────────────────────────────
def test_revision_stacks_and_keeps_old_version(store):
    """★★★ 버전을 **덮어쓰지 않는다.** 과거 산출물이 그때의 정의를 가리킨다."""
    a = _mk(store, body={"v": 1})
    store.revise(a["asset_id"], {"v": 2}, "kim")
    b = store.revise(a["asset_id"], {"v": 3}, "kim")

    assert b["current_version"] == 3
    assert b["body"] == {"v": 3}
    assert store.get(a["asset_id"], version_no=1)["body"] == {"v": 1}, "1판이 남아 있어야 한다"
    assert [h["version_no"] for h in b["versions"]] == [3, 2, 1]


def test_revision_drops_approval(store):
    """★★★ 개정하면 승인이 **풀린다.**

    ⚠️ 승인된 자산의 내용을 바꿔 놓고 승인 상태를 유지하면, 그 승인은 «읽지 않은 문서에 대한
      승인» 이 된다 — 나중에 «누가 이걸 승인했나» 에 답할 수 없다."""
    a = _mk(store)
    store.submit(a["asset_id"], "kim")
    ap = store.approve(a["asset_id"], "boss")
    assert ap["status"] == ST_APPROVED and ap["approved_by"] == "boss"

    r = store.revise(a["asset_id"], {"changed": True}, "kim")
    assert r["status"] == ST_DRAFT, "내용이 바뀌었으면 다시 검토받아야 한다"
    assert r["approved_by"] == "", "이전 승인자가 남아 있으면 승인된 것처럼 보인다"
    assert r["runnable"] is False


def test_cannot_approve_without_review(store):
    """★ 검토 요청을 건너뛴 승인을 막는다."""
    a = _mk(store)
    with pytest.raises(AssetError):
        store.approve(a["asset_id"], "boss")


def test_retired_asset_cannot_be_revised(store):
    a = _mk(store)
    store.retire(a["asset_id"], "boss")
    with pytest.raises(AssetError):
        store.revise(a["asset_id"], {"x": 1}, "kim")


def test_retire_keeps_the_row(store):
    """★★ 폐기는 **행을 지우지 않는다** — 과거 산출물이 이 자산을 가리키고 있다."""
    a = _mk(store)
    store.retire(a["asset_id"], "boss")
    got = store.get(a["asset_id"])
    assert got["status"] == ST_RETIRED
    assert got["versions"], "이력이 남아야 한다"


def test_unknown_asset_is_not_found(store):
    with pytest.raises(AssetNotFound):
        store.get("as_nope")


# ── 가시성 (P1-3) ─────────────────────────────────────────────────────────
def test_scope_asset_hidden_from_other_org(store):
    """★★★ 다른 조직의 자산은 목록에 나오지 않는다."""
    _mk(store, name_ko="동제련 전용", owner_scope_id="node_copper", visibility=VIS_SCOPE)
    _mk(store, name_ko="배터리 전용", owner_scope_id="node_battery", visibility=VIS_SCOPE)

    seen = store.list_assets(KIND_AGENT, frozenset({"node_copper"}), "lee")
    assert [r["name_ko"] for r in seen] == ["동제련 전용"]


def test_enterprise_and_system_are_visible_to_everyone(store):
    """★ 전사 공개와 제품 기본은 조직과 무관하게 보인다."""
    _mk(store, name_ko="전사 표준", owner_scope_id="node_hq", visibility=VIS_ENTERPRISE)
    seen = store.list_assets(KIND_AGENT, frozenset({"node_battery"}), "lee")
    assert [r["name_ko"] for r in seen] == ["전사 표준"]


def test_personal_asset_only_visible_to_creator(store):
    """★★ 개인 초안은 만든 사람만 본다 — 남의 미완성 초안이 목록에 뜨면 안 된다."""
    _mk(store, name_ko="내 초안", visibility=VIS_PERSONAL, owner_scope_id="", created_by="kim")
    assert len(store.list_assets(KIND_AGENT, frozenset(), "kim")) == 1
    assert store.list_assets(KIND_AGENT, frozenset(), "lee") == []


def test_empty_scope_set_is_fail_closed(store):
    """★★★ 조직을 하나도 모르면 **조직 자산은 보이지 않는다.**

    ⚠️ 빈 집합을 «전부 허용» 으로 읽으면, 조직 배정이 안 된 사용자가 전사 자산을 다 본다."""
    _mk(store, name_ko="조직 자산", owner_scope_id="node_copper", visibility=VIS_SCOPE)
    assert store.list_assets(KIND_AGENT, frozenset(), "lee") == []


def test_none_scope_means_no_filter(store):
    """★ `None` 은 «필터하지 않는다» — 호출부가 **의도적으로** 그렇게 준 경우다."""
    _mk(store, name_ko="조직 자산", owner_scope_id="node_copper", visibility=VIS_SCOPE)
    assert len(store.list_assets(KIND_AGENT, None, "lee")) == 1


def test_asset_without_owner_is_invisible(store):
    """★★★ 소유 조직을 모르는 조직 자산은 **보이지 않는다.**

    ⚠️ «모르니까 보여 준다» 가 한 번 통과하면 그 뒤로 아무도 소유를 채우지 않는다.
    (`create` 가 이미 막지만, 마이그레이션으로 들어온 행이 있을 수 있으므로 판정에서도 막는다.)"""
    a = _mk(store, owner_scope_id="node_copper", visibility=VIS_SCOPE)
    with store._connect() as conn:
        conn.execute("UPDATE agent_assets SET owner_scope_id='' WHERE asset_id=?",
                     (a["asset_id"],))
        conn.commit()
    assert store.list_assets(KIND_AGENT, frozenset({"node_copper"}), "kim") == []


def test_retired_assets_are_excluded_by_default(store):
    a = _mk(store, name_ko="쓰던 것")
    store.retire(a["asset_id"], "boss")
    assert store.list_assets(KIND_AGENT, None, "kim") == []
    assert len(store.list_assets(KIND_AGENT, None, "kim", include_retired=True)) == 1


def test_tenant_filter_separates_companies(store):
    """★★ 테넌트가 다르면 목록에 섞이지 않는다."""
    _mk(store, name_ko="A사", tenant_id="t_a", owner_scope_id="n1", visibility=VIS_ENTERPRISE)
    _mk(store, name_ko="B사", tenant_id="t_b", owner_scope_id="n2", visibility=VIS_ENTERPRISE)
    rows = store.list_assets(KIND_AGENT, None, "kim", tenant_id="t_a")
    assert [r["name_ko"] for r in rows] == ["A사"]


def test_kinds_do_not_mix(store):
    """★ 워크플로우를 에이전트 목록에서 보여주지 않는다."""
    _mk(store, kind=KIND_AGENT, name_ko="에이전트")
    _mk(store, kind=KIND_WORKFLOW, name_ko="워크플로우")
    assert [r["name_ko"] for r in store.list_assets(KIND_AGENT, None, "kim")] == ["에이전트"]
    assert [r["name_ko"] for r in store.list_assets(KIND_WORKFLOW, None, "kim")] == ["워크플로우"]


def test_only_approved_is_runnable(store):
    """★★★ 실행 가능한 상태는 `APPROVED` 뿐이다."""
    assert RUNNABLE == (ST_APPROVED,)
    a = _mk(store)
    assert store.get(a["asset_id"])["runnable"] is False
    store.submit(a["asset_id"], "kim")
    assert store.get(a["asset_id"])["runnable"] is False, "검토 중도 실행 대상이 아니다"
    store.approve(a["asset_id"], "boss")
    assert store.get(a["asset_id"])["runnable"] is True


def test_count_by_status_reports_every_status(store):
    """★ 상태별 집계는 **0 인 상태도 키를 남긴다** — 빠진 키를 «없음» 으로 읽으면 안 된다."""
    _mk(store)
    c = store.count_by_status(KIND_AGENT)
    assert c[ST_DRAFT] == 1
    assert c[ST_APPROVED] == 0 and ST_RETIRED in c and ST_REVIEW in c
