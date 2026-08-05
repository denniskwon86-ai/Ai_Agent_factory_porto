"""★★★ [D-018 ⑤] 조직 범위 백필 — 정본으로 바꾸고도 **권한 판정이 유지된다**.

## 이 파일이 지키는 것

1. **불변 이력은 백필하지 않는다.** `decision_ledger_events`(이력 + `event_hash` 체인)와
   `agent_asset_versions`(버전 스냅샷)는 제외 목록에 있어야 한다 — 고치면 이력이 거짓이 되고
   해시 체인이 영구히 깨진다.
2. **모호·미해석 값은 건너뛰고 목록으로 남긴다**(D-018 ②). 임의로 하나를 고르지 않는다.
3. **값을 지우지 않는다.** 해석 실패 시 원본을 그대로 둔다 — 빈 값으로 만들면 «범위 미지정» 이
   되어 fail-closed 로 아무에게도 보이지 않는다(데이터가 사라진 것처럼 보인다).
4. **멱등하다.** 여러 번 돌려도 같다.
5. ★★★ **백필 후에도 권한 판정이 동작한다.** `departments.scope_node_id` 가 `node_*` 로 바뀌면
   `readable_scope_nodes` 도 `node_*` 가 되는데, 다른 표에는 아직 코드가 남아 있다.
   `visible_scopes` 가 **코드와 node_id 를 모두** 집합에 넣기 때문에 양방향으로 매칭된다 —
   그 사실이 깨지면 백필이 곧 «아무도 자기 자료를 못 보는» 사고가 된다.
"""
import os
import sqlite3

import pytest

import scripts.backfill_scope_node_ids as bf


@pytest.fixture()
def fake_data(tmp_path, monkeypatch):
    """격리된 `data/` 를 만들고 백필 스크립트가 그것을 보게 한다.

    ⚠️ 운영 DB 를 향해 백필을 시험하지 않는다 — 되돌릴 수 있어도 «되돌렸다» 를 확인하는 비용이
      크고, 이 저장소는 그 경로로 이미 사고를 냈다."""
    monkeypatch.setattr(bf, "DATA_DIR", str(tmp_path))
    os.makedirs(tmp_path / "master", exist_ok=True)

    m = sqlite3.connect(tmp_path / "master" / "master.db")
    m.execute("CREATE TABLE departments (dept_id TEXT PRIMARY KEY, scope_node_id TEXT)")
    m.execute("CREATE TABLE agent_assets (asset_id TEXT PRIMARY KEY, owner_scope_id TEXT)")
    # 버전 이력 표 — **제외 대상**이므로 코드가 남아 있어야 한다.
    m.execute("CREATE TABLE agent_asset_versions (version_id TEXT PRIMARY KEY, "
              "owner_scope_id TEXT)")
    m.executemany("INSERT INTO departments VALUES (?,?)",
                  [("hq", "LS_MNM"), ("prod", "MNM_BATTERY"), ("none", ""),
                   ("already", "node_deadbeef01")])
    m.executemany("INSERT INTO agent_assets VALUES (?,?)",
                  [("as_1", "LS_MNM"), ("as_2", "__no_such_scope__")])
    m.execute("INSERT INTO agent_asset_versions VALUES ('av_1','LS_MNM')")
    m.commit()
    m.close()

    c = sqlite3.connect(tmp_path / "collaboration.db")
    # 복합 기본키 — 값 기준 갱신이어야 다뤄진다.
    c.execute("CREATE TABLE decision_participants (decision_id TEXT, user_id TEXT, "
              "role TEXT, scope_id TEXT, PRIMARY KEY (decision_id, user_id, role))")
    c.executemany("INSERT INTO decision_participants VALUES (?,?,?,?)",
                  [("d1", "u1", "owner", "LS_MNM"), ("d1", "u2", "reviewer", "LS_MNM")])
    c.commit()
    c.close()
    return tmp_path


@pytest.fixture()
def ecm(tmp_path):
    """격리 ECM 에 `LS_MNM`·`MNM_BATTERY` 노드를 심는다(conftest 가 경로를 tmp 로 바꿔 둔다)."""
    from core.enterprise_context.models import (STATUS_ACTIVE, EnterpriseEntity,
                                               OrganizationNode)
    from core.enterprise_context.repository import ecm_repository as repo
    repo.list_nodes()          # 스키마 생성(conftest 는 경로만 바꾼다)
    e = repo.upsert_entity(EnterpriseEntity(name_ko="LS MnM", entity_mode="REAL",
                                           status=STATUS_ACTIVE))
    top = repo.upsert_node(OrganizationNode(entity_id=e.entity_id, code="LS_MNM",
                                            name_ko="LS MnM", status=STATUS_ACTIVE))
    batt = repo.upsert_node(OrganizationNode(entity_id=e.entity_id, code="MNM_BATTERY",
                                            name_ko="배터리", status=STATUS_ACTIVE))
    return {"top": top, "batt": batt}


def _read(path, table, col):
    con = sqlite3.connect(path)
    try:
        return [r[0] for r in con.execute(f"SELECT {col} FROM {table}")]
    finally:
        con.close()


# ── 제외 목록 (가장 중요) ─────────────────────────────────────────────────
def test_immutable_history_is_excluded_by_name():
    """★★★ 불변 이력 표가 **대상 목록에 없고 제외 목록에 있다.**

    ⚠️ `decision_ledger_events` 는 실측 기준 백필 후보의 91%(513건)다. 가장 큰 덩어리라서
      «완료율» 을 위해 넣고 싶어지는데, 그것이 정확히 하면 안 되는 일이다 — 이력을 고치면
      «그때 그렇게 판단했다» 가 거짓이 되고 `event_hash` 체인이 영구히 깨진다."""
    targets = {(t, c) for _, t, c in bf.TARGETS}
    assert ("decision_ledger_events", "enterprise_scope_id") not in targets
    assert ("agent_asset_versions", "owner_scope_id") not in targets
    excluded = {t for _, t, _ in bf.EXCLUDED}
    assert "decision_ledger_events" in excluded and "agent_asset_versions" in excluded
    for _, _, why in bf.EXCLUDED:
        assert why, "제외 이유가 비어 있으면 다음 사람이 그냥 넣는다"


def test_history_table_is_left_untouched(fake_data, ecm):
    """제외 대상 표의 값은 백필 후에도 그대로다."""
    for db_rel, table, col in bf.TARGETS:
        item, err = bf._plan_for(db_rel, table, col)
        if item:
            bf._apply(item, "test")
    assert _read(fake_data / "master" / "master.db",
                 "agent_asset_versions", "owner_scope_id") == ["LS_MNM"]


# ── 계획 (읽기만) ─────────────────────────────────────────────────────────
def test_plan_resolves_codes_and_skips_unresolvable(fake_data, ecm):
    item, err = bf._plan_for("master/master.db", "agent_assets", "owner_scope_id")
    assert not err
    assert [c["old"] for c in item["plan"]] == ["LS_MNM"]
    assert item["plan"][0]["new"] == ecm["top"].node_id
    # ⚠️ 해석 못 한 값은 **건너뛰고 목록에 남는다** — 조용히 넘기면 아무도 못 고친다.
    assert [s["value"] for s in item["skipped"]] == ["__no_such_scope__"]
    assert item["skipped"][0]["reason"], "왜 건너뛰었는지 남아야 한다"


def test_plan_ignores_empty_and_already_canonical(fake_data, ecm):
    """빈 값은 «범위 미지정» 이라는 사실이므로 대상이 아니고, 이미 정본인 값도 손대지 않는다."""
    item, _ = bf._plan_for("master/master.db", "departments", "scope_node_id")
    olds = [c["old"] for c in item["plan"]]
    assert set(olds) == {"LS_MNM", "MNM_BATTERY"}
    assert "" not in olds and "node_deadbeef01" not in olds
    assert item["already"] == 1


def test_missing_column_is_reported_not_silently_skipped(fake_data, ecm):
    """★ 컬럼 이름이 틀리면 **오류로 보고**한다. 조용히 0건이 되면 «백필했다» 가 거짓이 된다.

    실제로 이 스크립트를 처음 돌릴 때 기본키 이름을 잘못 추측해 두 표가 빠졌고, 그 보고 덕에
    알아챘다(그래서 값 기준 갱신으로 바꿨다)."""
    item, err = bf._plan_for("master/master.db", "departments", "no_such_column")
    assert item is None and "컬럼이 없습니다" in err


# ── 적용 ──────────────────────────────────────────────────────────────────
def test_apply_updates_and_backs_up(fake_data, ecm):
    item, _ = bf._plan_for("master/master.db", "departments", "scope_node_id")
    n = bf._apply(item, "T1")
    assert n == 2
    vals = _read(fake_data / "master" / "master.db", "departments", "scope_node_id")
    assert ecm["top"].node_id in vals and ecm["batt"].node_id in vals
    assert "" in vals and "node_deadbeef01" in vals, "손대지 않아야 할 값이 바뀌었다"
    assert os.path.exists(str(fake_data / "master" / "master.db") + ".bak_backfill_T1"), \
        "백업 없이 썼다 — 되돌릴 수 없다"


def test_apply_handles_composite_primary_key(fake_data, ecm):
    """★★ 값 기준 갱신이므로 **복합 기본키** 표도 다뤄진다.

    기본키 기준으로 만들었다면 `decision_participants`(PK 3개)를 건너뛰었을 것이다."""
    item, err = bf._plan_for("collaboration.db", "decision_participants", "scope_id")
    assert not err
    assert bf._apply(item, "T2") == 2
    assert set(_read(fake_data / "collaboration.db", "decision_participants", "scope_id")) \
        == {ecm["top"].node_id}


def test_apply_is_idempotent(fake_data, ecm):
    """★★ 두 번 돌려도 같다 — 이미 `node_*` 인 값은 어느 옛값 조건에도 걸리지 않는다."""
    item, _ = bf._plan_for("master/master.db", "departments", "scope_node_id")
    bf._apply(item, "T3")
    after_first = sorted(_read(fake_data / "master" / "master.db",
                               "departments", "scope_node_id"))
    item2, _ = bf._plan_for("master/master.db", "departments", "scope_node_id")
    assert item2["plan"] == [], "두 번째 계획이 비어 있어야 한다"
    assert bf._apply(item2, "T3") == 0
    assert sorted(_read(fake_data / "master" / "master.db",
                        "departments", "scope_node_id")) == after_first


def test_apply_never_blanks_a_value(fake_data, ecm):
    """★★★ 해석 실패가 **값 삭제로 이어지지 않는다.**

    빈 값은 «범위 미지정» 이고 fail-closed 로 아무에게도 보이지 않는다 — 데이터가 사라진 것처럼
    보이고, 원인을 찾기 어렵다."""
    item, _ = bf._plan_for("master/master.db", "agent_assets", "owner_scope_id")
    bf._apply(item, "T4")
    vals = _read(fake_data / "master" / "master.db", "agent_assets", "owner_scope_id")
    assert "__no_such_scope__" in vals, "해석 못 한 값이 지워졌다"
    assert "" not in vals


# ── ★★★ 백필 후에도 권한 판정이 동작한다 ─────────────────────────────────
def test_visible_scopes_matches_both_forms_after_backfill(ecm):
    """★★★ **이 테스트가 이 파일에서 가장 중요하다.**

    `departments.scope_node_id` 를 정본으로 바꾸면 `readable_scope_nodes` 도 `node_*` 가 된다.
    그런데 다른 표에는 아직 코드가 남아 있다(백필은 표마다 순차로 일어난다). `visible_scopes` 가
    **코드와 node_id 를 모두** 집합에 넣기 때문에 양방향 매칭이 성립한다 —
    그 사실이 깨지면 백필이 곧 «아무도 자기 자료를 못 보는» 사고가 된다.
    ⚠️ 그래서 `visible_scopes` 에서 `code` 를 넣는 부분은 **백필이 전부 끝난 뒤에만** 걷어낼 수 있다."""
    from api.deps import scope_allows_owner
    from core.enterprise_context.scoping import visible_scopes

    node = ecm["top"].node_id
    # 정본으로 시작해도 코드가 함께 들어 있다.
    s_from_node = visible_scopes(node)
    assert node in s_from_node and "LS_MNM" in s_from_node
    # 코드로 시작해도 정본이 함께 들어 있다.
    s_from_code = visible_scopes("LS_MNM")
    assert node in s_from_code and "LS_MNM" in s_from_code

    # 그래서 소유가 어느 형태로 저장돼 있어도 매칭된다 — 이행 중 어긋나지 않는다.
    for scopes in (s_from_node, s_from_code):
        assert scope_allows_owner(scopes, node) is True
        assert scope_allows_owner(scopes, "LS_MNM") is True
        assert scope_allows_owner(scopes, ecm["batt"].node_id) is False
        assert scope_allows_owner(scopes, "") is False, "소유 미기재는 보이지 않아야 한다"
