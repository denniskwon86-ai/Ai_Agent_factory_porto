"""[P1-2] 파일 자산 SYSTEM·LEGACY 어댑터의 계약.

## 이 파일이 지키는 것

1. **파일을 DB 로 옮기지 않고도 같은 모양으로 읽힌다.** P1-5 가 `/agents`·`/templates` 를
   어댑터로 전환할 때 화면이 깨지지 않아야 하므로, 저장소 `get()` 과 **키가 같아야** 한다.
2. **없는 승인자를 지어내지 않는다.** 파일 자산은 `status=APPROVED`(지금 실제로 그 정의로
   실행되므로)이지만 `approved_by` 는 비어 있고 `needs_migration=True` 다.
3. **파일 자산을 저장소 API 로 고치려 하면 원인을 정확히 말한다.** `AssetNotFound`(«없다»)로
   두면 호출부가 자산을 다시 만들고 같은 정의가 두 벌이 된다.
4. **가시성 계약이 어댑터 경로에서 풀리지 않는다.** `viewer_scopes` 는 저장소와 같은 필수 인자다.
"""
import json

import pytest

from core import agent_registry as reg
from core.agent_assets import (
    KIND_AGENT, KIND_SKILL, KIND_WORKFLOW,
    ST_APPROVED, VIS_ENTERPRISE, VIS_SYSTEM, AssetError, AssetNotFound,
)
from core import agent_asset_adapter as ad


# ── 저장소와 같은 모양 ────────────────────────────────────────────────────
STORE_KEYS = {
    "asset_id", "kind", "tenant_id", "owner_scope_id", "entity_mode", "visibility", "status",
    "name_ko", "purpose", "current_version", "created_by", "approved_by", "effective_from",
    "effective_to", "created_at", "updated_at", "body", "version_no", "versions", "runnable",
}


def test_file_assets_have_every_store_key():
    """★★ 저장소 `get()` 의 키를 **하나도 빠뜨리지 않는다.**

    키가 빠지면 P1-5 로 전환한 순간 화면이 `undefined` 를 그린다 — 그때는 «권한 문제» 로
    보이지만 실제로는 모양이 다른 것이다."""
    for kind in (KIND_AGENT, KIND_WORKFLOW, KIND_SKILL):
        rows = ad.file_assets(kind)
        assert rows, f"{kind} 파일 자산이 하나도 없다 — 저장소에 기본 자산이 있어야 한다"
        for r in rows:
            missing = STORE_KEYS - set(r)
            assert not missing, f"{kind} 자산에 키가 없다: {sorted(missing)}"


def test_agents_come_from_registry():
    """에이전트는 레지스트리(파일 또는 코드 기본값)에서 온다."""
    ids = {a["native_id"] for a in ad.file_assets(KIND_AGENT)}
    expected = {a["id"] for a in reg.load_registry().get("agents") or []}
    assert ids == expected and ids, "레지스트리 에이전트와 어댑터 목록이 다르다"


def test_workflows_include_default_and_templates():
    """워크플로우는 `default`(레지스트리 자체) + `templates/*.json` 이다."""
    natives = {w["native_id"] for w in ad.file_assets(KIND_WORKFLOW)}
    assert reg.DEFAULT_TEMPLATE_ID in natives, "기본 워크플로우가 빠졌다"
    for item in reg.list_templates():
        assert item["id"] in natives, f"템플릿 {item['id']} 가 어댑터에 없다"


# ── 없는 승인자를 지어내지 않는다 ──────────────────────────────────────────
def test_file_assets_are_runnable_but_have_no_approver():
    """★★★ 파일 자산은 **실행 가능**하지만 **승인자가 없다.**

    · `APPROVED` 로 노출하는 이유: 지금 실제로 그 정의로 파이프라인이 돈다. `DRAFT` 로 두면
      P3(런타임 강제)가 붙는 순간 전 파이프라인이 실행 불가가 된다.
    · 그러나 `approved_by` 를 «관리자» 같은 값으로 채우지 않는다 — 파일에는 그 정보가 없다.
      대신 `needs_migration` 으로 «승인 이력 없이 돌고 있다» 를 드러낸다."""
    for kind in (KIND_AGENT, KIND_WORKFLOW, KIND_SKILL):
        for a in ad.file_assets(kind):
            assert a["status"] == ST_APPROVED and a["runnable"] is True
            assert a["approved_by"] == "", f"{a['asset_id']} 에 없는 승인자를 지어냈다"
            assert a["created_by"] == "", f"{a['asset_id']} 에 없는 작성자를 지어냈다"
            assert a["needs_migration"] is True, f"{a['asset_id']} 이관 필요 표시가 없다"
            assert a["migration_note"], "이관해야 하는 이유가 비어 있다"


def test_file_assets_have_no_owner_scope():
    """★ 소유 조직을 «전사» 로 채우지 않는다 — 그러면 «이 자산은 누구 책임인가» 에 거짓으로
    답하게 된다. 빈 값이 사실이다."""
    for kind in (KIND_AGENT, KIND_WORKFLOW, KIND_SKILL):
        for a in ad.file_assets(kind):
            assert a["owner_scope_id"] == "", f"{a['asset_id']} 에 없는 소유 조직이 붙었다"


def test_file_assets_have_no_version_history():
    """파일에는 개정 이력이 없다. `current_version=0` 은 «버전 개념이 없음» 이며,
    `1` 로 두면 «1 번째 버전이 있다» 는 거짓이 된다."""
    for a in ad.file_assets(KIND_AGENT):
        assert a["current_version"] == 0 and a["versions"] == []


# ── SYSTEM 과 LEGACY 구분 ─────────────────────────────────────────────────
def test_registry_source_follows_file_existence(tmp_path, monkeypatch):
    """레지스트리가 **파일에서 왔으면 LEGACY, 코드 기본값이면 SYSTEM.**

    `load_registry()` 가 파일이 없을 때 `DEFAULT_REGISTRY` 를 주므로 파일 존재 여부가
    그대로 이 구분이다."""
    # 파일이 있는 상태 → LEGACY
    p = tmp_path / "agents_registry.json"
    p.write_text(json.dumps({
        "id": "default", "name": "내 구성",
        "agents": [{"id": "MINE", "name_ko": "내 것", "role": "r", "enabled": True}],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(reg, "REGISTRY_PATH", str(p))
    assert ad._registry_source() == ad.SOURCE_LEGACY
    assert all(a["source"] == ad.SOURCE_LEGACY for a in ad.file_assets(KIND_AGENT))
    assert all(a["visibility"] == VIS_ENTERPRISE for a in ad.file_assets(KIND_AGENT))
    assert all(a["edit_via"] == "에이전트 통제소" for a in ad.file_assets(KIND_AGENT)), \
        "LEGACY 는 종전 화면에서 편집 가능하다 — 그 «어디서» 를 말해야 한다"

    # 파일이 없는 상태 → SYSTEM
    monkeypatch.setattr(reg, "REGISTRY_PATH", str(tmp_path / "no_such_file.json"))
    assert ad._registry_source() == ad.SOURCE_SYSTEM
    rows = ad.file_assets(KIND_AGENT)
    assert rows and all(a["source"] == ad.SOURCE_SYSTEM for a in rows)
    assert all(a["visibility"] == VIS_SYSTEM for a in rows)
    assert all(a["edit_via"] == "" for a in rows), \
        "코드 기본값은 사람이 바꿀 수 없다 — 바꿀 곳을 알려주면 거짓이 된다"


def test_templates_are_legacy_not_system():
    """★★ `templates/*.json` 은 **LEGACY** 다.

    그 디렉터리에는 제품 기본과 사용자가 `copy_template` 으로 만든 사본이 섞여 있고 코드에는
    둘을 구분할 근거가 없다. 이때 «모르는 것을 SYSTEM(수정 불가)으로» 두면 사용자가 자기가
    만든 템플릿을 못 고쳐 업무가 막힌다 — 틀렸을 때의 대가가 훨씬 크다."""
    tpl_ids = {t["id"] for t in reg.list_templates() if t["id"] != reg.DEFAULT_TEMPLATE_ID}
    if not tpl_ids:
        pytest.skip("템플릿 파일이 없어 확인할 수 없다")
    for w in ad.file_assets(KIND_WORKFLOW):
        if w["native_id"] in tpl_ids:
            assert w["source"] == ad.SOURCE_LEGACY, f"{w['native_id']} 를 SYSTEM 으로 분류했다"
            assert w["edit_via"], "편집 가능한데 바꿀 곳을 알려주지 않는다"


def test_builtin_flag_is_not_used_as_a_source_signal():
    """★★ `list_templates()` 의 `builtin` 은 «제품 배포물인가» 가 아니라 «`default` 인가» 다.

    이름에 속아 출처 판단에 쓰면 파일 템플릿 전부가 «사용자 것» 으로, `default` 는 «제품 것» 으로
    분류된다 — 둘 다 근거 없는 판단이다. 이 테스트는 그 플래그의 실제 의미를 못 박아 둔다."""
    items = {t["id"]: t for t in reg.list_templates()}
    assert items[reg.DEFAULT_TEMPLATE_ID]["builtin"] is True
    for tid, t in items.items():
        if tid != reg.DEFAULT_TEMPLATE_ID:
            assert t["builtin"] is False, \
                f"{tid} 의 builtin 이 True 다 — 이 값의 의미가 바뀌었으면 어댑터 분류를 재검토해야 한다"


# ── id 규칙 ───────────────────────────────────────────────────────────────
def test_file_ids_are_prefixed_and_never_collide_with_db_ids():
    """★ 접두사로 출처가 보인다 — id 만 보고 «파일 자산» 임을 안다.
    DB 자산은 `as_…` 이므로 겹치지 않는다."""
    for kind in (KIND_AGENT, KIND_WORKFLOW, KIND_SKILL):
        for a in ad.file_assets(kind):
            assert a["asset_id"].startswith(ad.FILE_PREFIX)
            assert ad.is_file_asset(a["asset_id"])
            assert not a["asset_id"].startswith("as_")
    assert not ad.is_file_asset("as_abcdef123456")


def test_unknown_file_id_is_not_found():
    with pytest.raises(AssetNotFound):
        ad.get_file_asset("file:agent:__no_such_agent__")
    with pytest.raises(AssetNotFound):
        ad.get_file_asset("file:nonsense:x")


# ── 스킬 본문은 get 에서만 읽는다 ──────────────────────────────────────────
def test_skill_body_is_read_only_on_get():
    """목록에서 31개 파일을 읽으면 목록 조회가 파일 I/O 로 무거워진다.
    목록은 파일명만, 본문은 `get()` 에서."""
    rows = ad.file_assets(KIND_SKILL)
    assert rows, "스킬 문서가 없다"
    assert "markdown" not in rows[0]["body"], "목록에서 본문을 읽고 있다"
    full = ad.get_file_asset(rows[0]["asset_id"])
    assert isinstance(full["body"].get("markdown"), str) and full["body"]["markdown"], \
        "본문을 읽지 못했다"


def test_skill_names_are_korean_not_slugs():
    """★★ 화면에 **내부 슬러그를 노출하지 않는다**(이관 완료 조건 1).

    `architect_skill` 같은 파일명 대신 그 스킬을 쓰는 에이전트의 한국어 이름을 준다."""
    rows = ad.file_assets(KIND_SKILL)
    slugs = [r for r in rows if r["name_ko"] == r["native_id"]]
    assert len(rows) - len(slugs) >= 30, \
        f"이름을 찾은 스킬이 {len(rows) - len(slugs)}개뿐이다 — 이름 원천 매핑이 끊겼다"
    # ⚠️ 폴백(슬러그)이 남는 것은 «이름을 못 찾았다» 는 사실의 노출이므로 허용한다. 지금
    #   남는 것은 `design_system` 하나이며, 이는 어느 에이전트도 쓰지 않는 디자인 문서라
    #   «그 스킬을 쓰는 에이전트의 이름» 이 실제로 없다. 이 수가 늘면 원천을 고쳐야 한다.
    assert len(slugs) <= 1, \
        f"슬러그로 노출되는 스킬이 {len(slugs)}개다: {[r['native_id'] for r in slugs]}"


def test_sim_skills_get_names_from_their_own_template():
    """★★ 이름 원천은 «그 스킬을 실제로 쓰는 에이전트» 이지 «기본 파이프라인» 이 아니다.

    `sim_*` 8개는 `mfg_sim` 템플릿 소속이라 기본 레지스트리에 없다. `default` 만 훑으면
    화면에 `sim_purchase` 같은 슬러그가 그대로 나간다."""
    names = {r["native_id"]: r["name_ko"] for r in ad.file_assets(KIND_SKILL)}
    sims = [n for n in names if n.startswith("sim_")]
    if not sims:
        pytest.skip("sim_* 스킬이 없다")
    unnamed = [n for n in sims if names[n] == n]
    assert not unnamed, f"템플릿 소속 스킬의 이름을 못 찾았다: {unnamed}"


def test_migration_report_counts_slug_named_assets():
    """★ 슬러그가 화면에 나가는 자산 수를 센다 — 어댑터가 이름을 지어낼 수는 없으므로
    (원천에 없다) 대신 관측 가능하게 남긴다. 숨기면 아무도 원천을 고치지 않는다."""
    rep = ad.migration_report(KIND_SKILL)
    b = rep["by_kind"][KIND_SKILL]
    assert "slug_named" in b
    assert b["slug_named"] == sum(
        1 for r in ad.file_assets(KIND_SKILL) if r["name_ko"] == r["native_id"])


def test_skill_name_is_same_in_list_and_detail():
    """★ 목록과 상세가 같은 이름을 보여야 한다 — 두 곳에서 따로 계산하면 한쪽만 고쳐졌을 때
    같은 자산이 두 이름으로 보인다."""
    for r in ad.file_assets(KIND_SKILL)[:5]:
        assert ad.get_file_asset(r["asset_id"])["name_ko"] == r["name_ko"]


def test_unreadable_skill_raises_instead_of_empty(tmp_path, monkeypatch):
    """★★ 읽기 실패를 **빈 스킬로 돌려주지 않는다.** 빈 규칙은 «규칙 없음» 으로 실행된다."""
    monkeypatch.setattr(ad, "_SKILLS_DIR", str(tmp_path))
    (tmp_path / "broken.md").write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(AssetError):
        ad.get_file_asset("file:skill:broken")


# ── 저장소 API 로 고치려 할 때 ─────────────────────────────────────────────
def test_writing_a_file_asset_says_where_to_change_it():
    """★★★ «없다» 가 아니라 «여기서 다룰 대상이 아니다» 라고 말한다.

    원인을 잘못 짚으면 호출부는 자산을 다시 만들고, 그때 같은 정의가 두 벌이 된다."""
    for aid, word in (("file:agent:RFP_Analyst", "에이전트"),
                      ("file:workflow:default", "워크플로우"),
                      ("file:skill:rfp_skill", "스킬")):
        with pytest.raises(AssetError) as e:
            ad.assert_writable_here(aid)
        msg = str(e.value)
        assert word in msg, f"어디서 바꾸는지 말하지 않는다: {msg}"
        assert "복사" in msg, f"다음 행동(복사)을 말하지 않는다: {msg}"
    # DB 자산은 통과한다 — 이 함수가 정상 경로를 막지 않는다.
    ad.assert_writable_here("as_abcdef123456")


# ── 통합 조회 ─────────────────────────────────────────────────────────────
def test_list_all_merges_db_and_file_assets():
    """DB 자산 + 파일 자산이 함께 나온다."""
    rows = ad.list_all(KIND_AGENT, None, "someone@ls")
    assert any(ad.is_file_asset(r["asset_id"]) for r in rows), "파일 자산이 빠졌다"


def test_list_all_can_exclude_files():
    """파일 자산만 따로 세야 하는 곳(이관 진척)이 있으므로 끌 수 있어야 한다."""
    rows = ad.list_all(KIND_AGENT, None, "someone@ls", include_files=False)
    assert not any(ad.is_file_asset(r["asset_id"]) for r in rows)


def test_list_all_keeps_the_store_visibility_contract():
    """★★★ 어댑터 경로에서 가시성 계약이 풀리지 않는다.

    `frozenset()` = «아무 조직도 모른다» → 개인·전사·시스템만 보인다. 파일 자산은 전사/시스템
    이므로 보이는 것이 맞다. 여기서 조직 자산이 새어 나오면 P1-3 이 무의미해진다."""
    rows = ad.list_all(KIND_AGENT, frozenset(), "nobody@ls")
    for r in rows:
        if ad.is_file_asset(r["asset_id"]):
            assert r["visibility"] in (VIS_SYSTEM, VIS_ENTERPRISE)
        else:
            # DB 자산이 보였다면 개인·전사·시스템 중 하나여야 한다.
            assert r["visibility"] != "SCOPE" or r["owner_scope_id"] == "", \
                f"조직 자산이 범위 없는 사용자에게 보였다: {r['asset_id']}"


def test_get_any_reads_both_kinds():
    a = ad.file_assets(KIND_AGENT)[0]
    got = ad.get_any(a["asset_id"])
    assert got["asset_id"] == a["asset_id"]
    with pytest.raises(AssetNotFound):
        ad.get_any("as_definitely_not_there")


# ── 이관 진척 ─────────────────────────────────────────────────────────────
def test_migration_report_counts_and_never_hides_failure():
    """★★ «0 개 남았다» 와 «못 셌다» 를 구분한다."""
    rep = ad.migration_report()
    assert rep["complete"] is True and not rep["unavailable"]
    assert rep["pending_total"] > 0, "파일 자산이 있는데 0 으로 셌다"
    for kind in (KIND_AGENT, KIND_WORKFLOW, KIND_SKILL):
        assert kind in rep["by_kind"]
        b = rep["by_kind"][kind]
        assert b["total"] == b["system"] + b["legacy"]


def test_migration_report_marks_unavailable(monkeypatch):
    """한 종류를 못 셌으면 `complete=False` 이고 그 종류가 `unavailable` 에 담긴다."""
    def boom(kind):
        if kind == KIND_SKILL:
            raise RuntimeError("디스크 오류")
        return []
    monkeypatch.setattr(ad, "file_assets", boom)
    rep = ad.migration_report()
    assert rep["complete"] is False
    assert any(u["kind"] == KIND_SKILL for u in rep["unavailable"])
