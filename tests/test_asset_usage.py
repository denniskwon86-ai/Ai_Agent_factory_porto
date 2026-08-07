"""[D-017 §9 P4-4 나머지 절반] 자산 사용 관측 — **「사용 기록 없음」은 「미사용」이 아니다.**

이 파일이 지키는 것은 하나로 요약된다.

  ★★★ 관측을 켠 다음 날 화면이 「자산 31개 전부 정리 대상」이라고 말하면, 그것을 본 사람은
      전부 지운다. 그리고 지운 뒤에야 그것이 「안 쓰인 것」이 아니라 **「아직 안 본 것」**
      이었음을 안다 — P4-2 의 부서 귀속률 0% 와 정확히 같은 함정이다.

그래서 관측 기간이 짧으면 **목록을 만들지 않는다**. 빈 목록도 아니고 `available=False` 다.
"""
import pytest

from core import asset_dedup as ad
from core.asset_usage import AssetUsageStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    """격리된 관측 저장소.

    ⚠️ 싱글턴 `asset_usage` 의 `db_path` 는 절대경로라 `chdir` 로 격리되지 않는다.
      돌리지 않으면 테스트가 **운영 관측 기록에 쓴다** — 그러면 「이 자산이 쓰이는가」의
      답이 테스트 때문에 바뀐다."""
    import core.asset_usage as au
    s = AssetUsageStore(db_path=str(tmp_path / "asset_usage.db"))
    monkeypatch.setattr(au, "asset_usage", s, raising=False)
    monkeypatch.setattr(au.asset_usage, "db_path", s.db_path, raising=False)
    return s


def _items(*ids):
    return [{"id": i, "kind": "file_skill", "where": f"skills/{i}", "text": i} for i in ids]


# ── ① 기록 — 누적은 더해지고, 플러시 전에도 읽힌다 ──────────────────────────
def test_record_accumulates_across_flushes(store):
    """⚠️ 플러시마다 덮어쓰면 누적이 사라진다 — 「한 번 쓰인 것」과 「백 번 쓰인 것」이
    같아 보이면 정리 판단의 근거가 준다."""
    for _ in range(3):
        store.record("a.md", "file_skill")
    store.flush()
    for _ in range(2):
        store.record("a.md", "file_skill")
    store.flush()
    assert store.usage_map()["a.md"]["use_count"] == 5


def test_pending_writes_are_visible_before_interval(store):
    """★ 방금 쓴 자산이 «사용 기록 없음» 으로 보고되면 그 오보 하나가 목록의 신뢰를 깎는다.
    `usage_map` 은 읽기 전에 스스로 내린다."""
    store.record("fresh.md", "file_skill")     # 플러시 간격 전
    assert "fresh.md" in store.usage_map()


def test_blank_key_is_ignored(store):
    store.record("", "file_skill")
    store.record(None, "file_skill")
    assert store.usage_map() == {}


def test_recording_failure_does_not_raise(store, monkeypatch, capsys):
    """⚠️ 계측 장애가 실행을 막으면 안 된다 — 자산 해석은 업무 경로다."""
    monkeypatch.setattr(store, "_connect",
                        lambda: (_ for _ in ()).throw(OSError("disk full")))
    store.record("x.md", "file_skill")
    store.flush()                              # 예외가 새어나오면 여기서 죽는다
    assert "disk full" in capsys.readouterr().out


def test_observation_start_is_not_moved(store):
    """★ 시작 시각을 갱신하면 창이 계속 짧아져 목록이 **영영** 나오지 않는다."""
    first = store.observed_since()
    assert first
    store.record("a.md")
    store.flush()
    store._ready = ""                          # 다시 초기화를 타게 만든다
    assert store.observed_since() == first


# ── ② ★★★ 관측이 짧으면 목록을 만들지 않는다 ───────────────────────────────
def test_short_observation_refuses_to_list(store):
    """★★★ 이 파일 전체의 이유. 관측 첫날에는 전부가 «사용 기록 없음» 이다."""
    u = ad.find_unused(_items("a.md", "b.md"), usage={}, days_observed=1.0,
                       observed_since="2026-08-07T00:00:00+00:00")
    assert u["available"] is False
    assert u["items"] == []


def test_short_observation_says_when_it_will_be_available(store):
    """★ 「아직」임을 말하고 **언제부터 볼 수 있는지**를 준다 — 그래야 다시 열 이유가 생긴다."""
    note = ad.find_unused(_items("a.md"), usage={}, days_observed=4.0,
                          observed_since="2026-08-07T00:00:00+00:00", min_days=14)["note"]
    assert "10.0일 뒤" in note
    assert "정리할 것이 없다» 는 뜻이 아닙니다" in note


def test_no_observation_at_all_is_not_an_empty_list(store):
    u = ad.find_unused(_items("a.md"), usage={}, days_observed=0.0, observed_since="")
    assert u["available"] is False and u["items"] == []
    assert "정리할 것이 없다" in u["note"]


# ── ③ 관측이 충분하면 판단한다 — 「본 적 없음」과 「오래 전」을 가른다 ────────
def test_recently_used_is_excluded(store):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    u = ad.find_unused(_items("hot.md"), usage={"hot.md": {"last_used_at": now,
                                                           "use_count": 9}},
                       days_observed=40.0, observed_since="2026-06-01T00:00:00+00:00")
    assert u["available"] is True
    assert u["items"] == []


def test_never_observed_and_stale_are_distinguished(store):
    """⚠️ 「본 적 없음」은 관측 구멍일 수도 있고, 「오래 전에 봤음」은 근거가 있는 판단이다.
    화면이 둘을 구분할 수 있어야 한다."""
    u = ad.find_unused(
        _items("never.md", "old.md"),
        usage={"old.md": {"last_used_at": "2026-01-01T00:00:00+00:00", "use_count": 2}},
        days_observed=40.0, observed_since="2026-06-01T00:00:00+00:00")
    basis = {x["id"]: x["basis"] for x in u["items"]}
    assert basis == {"never.md": "never_observed", "old.md": "stale"}


def test_stale_items_come_first(store):
    """근거가 있는 것을 위에 둔다 — 확신 낮은 항목이 목록 머리를 차지하면 신뢰가 깎인다."""
    u = ad.find_unused(
        _items("never.md", "old.md"),
        usage={"old.md": {"last_used_at": "2026-01-01T00:00:00+00:00", "use_count": 2}},
        days_observed=40.0, observed_since="2026-06-01T00:00:00+00:00")
    assert u["items"][0]["id"] == "old.md"


def test_note_never_calls_it_unused(store):
    """★★ 「미사용」이라고 쓰면 사람은 지워도 되는 것으로 읽는다."""
    u = ad.find_unused(_items("a.md"), usage={}, days_observed=40.0,
                       observed_since="2026-06-01T00:00:00+00:00")
    assert "관측되지 않음" in u["note"]
    assert "미사용» 이 아니라" in u["note"]


# ── ④ 실패는 «없음» 이 아니라 «못 읽었다» ───────────────────────────────────
def test_usage_store_failure_does_not_become_an_empty_list(monkeypatch):
    """⚠️ 관측이 죽었을 때 빈 목록을 내면 「정리할 것이 없다」로 읽힌다."""
    monkeypatch.setattr(ad, "find_unused",
                        lambda *_a, **_k: (_ for _ in ()).throw(OSError("db locked")))
    u = ad._unused_or_reason(_items("a.md"))
    assert u["available"] is False and u["items"] == []
    assert "db locked" in u["note"] and "정리할 것이 없다" in u["note"]


def test_unused_failure_does_not_kill_the_duplicate_list(monkeypatch):
    """중복은 사용 이력과 무관하게 유효하다 — 한쪽 장애가 다른 쪽을 죽이면 안 된다."""
    monkeypatch.setattr(ad, "find_unused",
                        lambda *_a, **_k: (_ for _ in ()).throw(OSError("boom")))
    same = [{"id": "a.md", "kind": "file_skill", "where": "s/a", "text": "SAME"},
            {"id": "b.md", "kind": "file_skill", "where": "s/b", "text": "SAME"}]
    d = ad.find_duplicates(same)
    assert len(d["identical"]) == 1
    assert d["unused"]["available"] is False


# ── ⑤ 기록 지점 — 키 규약이 어긋나면 전부 «사용 기록 없음» 이 된다 ───────────
def test_skill_resolution_records_usage(store, monkeypatch):
    """★ `agent_skill` 이 파일 스킬의 유일한 선택 지점이다."""
    import core.agent_registry as ar
    monkeypatch.setattr(ar, "agent_meta", lambda *_a, **_k: {"skill": "writer_skill"})
    assert ar.agent_skill("Writer", template_id="default") == "writer_skill"
    # ⚠️ 반환값은 확장자 없는 이름이지만 **기록되는 키는 파일명**이다.
    assert "writer_skill.md" in store.usage_map()


def test_skill_key_matches_disk_convention():
    """규약 자체를 고정한다 — 출처는 `agent_asset_adapter` 의 `f\"{native}.md\"` 다."""
    from core.asset_usage import skill_key
    assert skill_key("rfp_skill") == "rfp_skill.md"
    assert skill_key("rfp_skill.md") == "rfp_skill.md"     # 두 번 붙이지 않는다
    assert skill_key("") == "" and skill_key(None) == ""


def test_recorded_key_matches_dedup_key_with_real_registry(store):
    """★★★ [2026-08-07 실측이 잡은 결함] **대역 없이** 실제 레지스트리·실제 `skills/` 로 본다.

    ⚠️⚠️ 이 검사가 대역(`agent_meta` 를 `"writer.md"` 로 고정)으로 되어 있었을 때는 통과했다 —
      테스트가 **자기 자신과 합의**했기 때문이다. 실제로는 `agent_skill()` 이 `rfp_skill` 을
      돌려주고 목록은 `rfp_skill.md` 를 써서 교집합이 **0건**이었고, 그 상태로 두면 매 실행마다
      쓰이는 스킬 31개가 전부 «사용 기록 없음» 으로 보고된다 — 즉 관측을 켜 놓고도 화면은
      「전부 정리 대상」이라고 말한다.

    ★ 그래서 이 검사는 무엇도 대역하지 않는다. 규약이 어긋나면 여기서 걸린다."""
    from core.agent_registry import agent_skill, load_registry

    agents = [a["id"] for a in load_registry()["agents"]]
    assert agents, "레지스트리가 비어 검사가 무의미해졌다"
    for a in agents:
        agent_skill(a, template_id="default")

    recorded = set(store.usage_map())
    collected = {i["id"] for i in ad.collect_items()["items"]}
    overlap = recorded & collected
    assert overlap, (
        f"기록 키와 목록 id 가 하나도 겹치지 않는다 — 관측이 헛돈다. "
        f"기록={sorted(recorded)[:5]} 목록={sorted(collected)[:5]}")


def test_real_skills_are_not_reported_as_unobserved(store):
    """★ 위 검사의 «그래서 무엇이 잘못되는가». 방금 해석한 스킬이 목록에 올라오면 안 된다."""
    from core.agent_registry import agent_skill, load_registry
    for a in [x["id"] for x in load_registry()["agents"]]:
        agent_skill(a, template_id="default")

    u = ad.find_unused(days_observed=40.0, observed_since="2026-06-01T00:00:00+00:00",
                       usage=store.usage_map())
    flagged = {x["id"] for x in u["items"]}
    used = set(store.usage_map())
    assert not (flagged & used), f"방금 쓴 스킬이 정리 대상에 올랐다: {sorted(flagged & used)}"


def test_unapproved_workflow_is_not_counted_as_used(store, monkeypatch):
    """★ 가드에서 막힌 자산은 **실행되지 않았다.** 거기서 세면 「승인 안 된 자산이 잘 쓰이고
    있다」는 모순된 화면이 나온다."""
    import core.agent_asset_adapter as ad_ap
    from core.agent_assets import AssetError
    monkeypatch.setattr(ad_ap.agent_assets, "get",
                        lambda _id, **_k: {"kind": "workflow", "runnable": False,
                                           "status": "DRAFT", "name_ko": "초안",
                                           "body": {"agents": [{"id": "A"}]}})
    with pytest.raises(AssetError):
        ad_ap.resolve_workflow("as_deadbeef1234")
    assert store.usage_map() == {}
