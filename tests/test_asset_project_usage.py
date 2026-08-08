"""★★★ [D-017 §9 P2-2 / 설계 §8.4] 「이 자산을 쓰는 프로젝트가 몇 개인가」의 계약.

## 이 파일이 지키는 것 — 전부 **같은 하나의 위험**에서 나온다

착수 시점 실측(2026-08-08): 56개 프로젝트 중 `config_snapshot.json` 을 가진 것이 **0개**다.
그 상태에서 순진하게 집계하면 **모든 자산이 「0개 프로젝트에서 사용」** 으로 나오고, 그 화면을
본 사람은 전부 폐기해도 된다고 읽는다. 지운 뒤에야 그것이 「안 쓰인 것」이 아니라
**「아직 기록이 없는 것」** 이었음을 안다.

그래서 이 모듈의 계약은 「정확히 센다」가 아니라 **「셀 수 없을 때 셀 수 없다고 말한다」** 다.

1. 관측이 없으면 `countable=False` — 0 은 답이 아니다
2. 분모(`projects_total`·`projects_observed`·`axis_observed`)를 항상 함께 낸다
3. 스캔 실패를 «프로젝트 0개» 로 돌려주지 않는다
4. 매칭 키가 어긋나면 교집합이 통째로 0 이 된다 — `usage_keys` 를 못박는다
   (`asset_usage.skill_key` 가 정확히 그 실패를 겪었다: `rfp_skill` vs `rfp_skill.md`)
"""
import json
import os

import pytest

from core import asset_project_usage as apu
from core.config_snapshot import SNAPSHOT_FILE


def _project(root, name, *, current=None, history=None):
    d = os.path.join(str(root), name)
    os.makedirs(d, exist_ok=True)
    if current is None and history is None:
        return d                                   # 스냅샷 없는 프로젝트
    payload = {}
    if current is not None:
        payload["current"] = current
    if history is not None:
        payload["history"] = history
    with open(os.path.join(d, SNAPSHOT_FILE), "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return d


# ── 매칭 키 (교집합 0 을 막는 유일한 지점) ────────────────────────────────
def test_usage_keys_accepts_every_name_a_snapshot_might_use():
    """★★★ 스냅샷이 자산을 **어떤 이름으로 적었는지는 경로마다 다르다.**

    파일 자산은 `file:agent:RFP_Analyst` 인데 스냅샷에는 `RFP_Analyst` 만 남는다. 그 둘을
    맞추지 못하면 교집합이 0 이 되고, 증상은 「이 자산은 아무도 안 쓴다」라는 **그럴듯한
    거짓말**이다 — 목록도 화면도 멀쩡해 보이므로 아무도 의심하지 않는다."""
    k = apu.usage_keys({"asset_id": "file:agent:RFP_Analyst"})
    assert "file:agent:RFP_Analyst" in k and "RFP_Analyst" in k

    k = apu.usage_keys({"asset_id": "file:skill:rfp_skill"})
    assert "rfp_skill" in k, "스킬 native 가 키에 없으면 스킬 사용은 영원히 0 이다"

    #: DB 자산은 `as_…` 인데 레지스트리로 펼쳐질 때는 본문의 `id` 로 남는다 — 둘 다 받는다.
    k = apu.usage_keys({"asset_id": "as_abc", "body": {"id": "My_Agent"}})
    assert {"as_abc", "My_Agent"} <= k

    assert apu.usage_keys({"asset_id": ""}) == set()


def test_usage_keys_matches_the_real_file_asset_id_convention():
    """★★ 규약을 여기서 **지어내지 않는다.** 어댑터가 실제로 만드는 id 로 확인한다 —
    두 곳에 각자 적으면 한쪽이 바뀔 때 조용히 어긋난다."""
    from core.agent_asset_adapter import file_asset_id
    aid = file_asset_id("skill", "rfp_skill")
    assert "rfp_skill" in apu.usage_keys({"asset_id": aid})


# ── 관측이 없을 때 (이 파일의 존재 이유) ──────────────────────────────────
def test_no_snapshots_means_not_countable_not_zero(tmp_path):
    """★★★ 프로젝트는 있는데 **기록이 하나도 없는** 상태. 착수 시점의 실제 상태다.

    `project_count == 0` 이지만 그 0 은 답이 아니다. `countable=False` 가 함께 나가지 않으면
    화면은 「아무도 안 쓴다」를 그리고, 그 화면을 근거로 사람이 자산을 지운다."""
    root = tmp_path / "projects"
    for n in ("p1", "p2", "p3"):
        _project(root, n)
    out = apu.usage_for([{"asset_id": "file:agent:A"}], "agent", projects_dir=str(root))
    assert out["projects_total"] == 3
    assert out["projects_observed"] == 0
    assert out["usage"]["file:agent:A"]["project_count"] == 0
    assert out["usage"]["file:agent:A"]["countable"] is False, \
        "셀 수 없는데 0 을 «답» 으로 내보내고 있다"


def test_missing_projects_dir_is_a_real_zero_not_a_failure(tmp_path):
    """★ 「프로젝트 폴더가 없다」는 **정상적인 0** 이다. 이것까지 `available=False` 로 두면
    새 환경에서 화면이 늘 「집계 실패」를 띄운다."""
    out = apu.usage_for([{"asset_id": "x"}], "agent",
                        projects_dir=str(tmp_path / "nope"))
    assert out["available"] is True and out["projects_total"] == 0


def test_scan_failure_is_not_reported_as_zero_projects(tmp_path, monkeypatch):
    """★★★ 스캔 실패를 «프로젝트 0개» 로 돌려주면 **모든 자산이 미사용으로 보인다.**
    이 기능에서 가장 비싼 거짓말이므로 실패는 실패로 남긴다."""
    def boom(_):
        raise PermissionError("권한 없음")
    monkeypatch.setattr(apu.os, "listdir", boom)
    out = apu.scan_projects(projects_dir=str(tmp_path))
    assert out["available"] is False and out["error"]


# ── 실제로 셀 때 ──────────────────────────────────────────────────────────
def test_counts_projects_that_reference_the_asset(tmp_path):
    root = tmp_path / "projects"
    _project(root, "uses_a", current={"template_id": "default", "agents": ["A", "B"],
                                      "skills": ["s1"]})
    _project(root, "uses_b", current={"template_id": "default", "agents": ["B"],
                                      "skills": []})
    _project(root, "no_snapshot")

    out = apu.usage_for([{"asset_id": "file:agent:A"}, {"asset_id": "file:agent:B"}],
                        "agent", projects_dir=str(root))
    assert out["projects_total"] == 3 and out["projects_observed"] == 2
    assert out["usage"]["file:agent:A"]["project_count"] == 1
    assert out["usage"]["file:agent:A"]["projects"] == ["uses_a"]
    assert out["usage"]["file:agent:B"]["project_count"] == 2
    assert out["usage"]["file:agent:B"]["countable"] is True


def test_workflow_axis_matches_template_id(tmp_path):
    root = tmp_path / "projects"
    _project(root, "p", current={"template_id": "as_wf1", "agents": []})
    out = apu.usage_for([{"asset_id": "as_wf1"}, {"asset_id": "as_wf2"}],
                        "workflow", projects_dir=str(root))
    assert out["usage"]["as_wf1"]["project_count"] == 1
    assert out["usage"]["as_wf2"]["project_count"] == 0


def test_history_is_not_counted_as_current_use(tmp_path):
    """★★★ **한때 썼던** 것을 「쓰는 중」으로 세면 폐기 판단이 영원히 막힌다.

    질문은 「지금 무엇으로 도는가」이고, 이력은 「무엇으로 만들어졌는가」에 답하는 다른 자료다."""
    root = tmp_path / "projects"
    _project(root, "p", current={"template_id": "t", "agents": ["NOW"]},
             history=[{"template_id": "t", "agents": ["OLD"]},
                      {"template_id": "t", "agents": ["NOW"]}])
    out = apu.usage_for([{"asset_id": "file:agent:OLD"}, {"asset_id": "file:agent:NOW"}],
                        "agent", projects_dir=str(root))
    assert out["usage"]["file:agent:NOW"]["project_count"] == 1
    assert out["usage"]["file:agent:OLD"]["project_count"] == 0, "이력이 «사용 중»으로 세어졌다"


def test_broken_snapshot_is_not_counted_as_observed(tmp_path):
    """★ 읽지 못한 스냅샷을 «참조 없음» 으로 두면 **분모만 늘어** 사용률이 낮아 보인다.
    그러면 실제로 쓰이는 자산이 「거의 안 쓰인다」로 보고된다."""
    root = tmp_path / "projects"
    d = _project(root, "broken", current={"template_id": "t"})
    with open(os.path.join(d, SNAPSHOT_FILE), "w", encoding="utf-8") as f:
        f.write("{ 깨진 JSON")
    _project(root, "ok", current={"template_id": "t", "agents": ["A"]})
    out = apu.usage_for([{"asset_id": "file:agent:A"}], "agent", projects_dir=str(root))
    assert out["projects_total"] == 2 and out["projects_observed"] == 1


def test_empty_current_is_not_observed(tmp_path):
    """스냅샷 파일은 있는데 `current` 가 비었다 — 기록을 시작만 하고 못 채운 상태다."""
    root = tmp_path / "projects"
    _project(root, "p", current={})
    out = apu.usage_for([{"asset_id": "a"}], "agent", projects_dir=str(root))
    assert out["projects_observed"] == 0


# ── 스킬 축은 늦게 생겼다 ─────────────────────────────────────────────────
def test_old_snapshots_without_skills_do_not_make_skills_look_unused(tmp_path):
    """★★★ `skills` 축은 2026-08-08 에 생겼다. 그 이전 스냅샷에는 키가 **없다.**

    없음을 «스킬 0개» 로 읽으면, 매 실행마다 쓰이는 스킬 31개가 전부 미사용으로 보고된다 —
    `asset_usage.skill_key` 가 겪은 것과 **같은 사고**이며 원인만 다르다. 그래서 스킬을
    실제로 셀 수 있는 스냅샷 수(`axis_observed`)를 따로 본다."""
    root = tmp_path / "projects"
    _project(root, "old", current={"template_id": "t", "agents": ["A"]})     # skills 키 없음
    out = apu.usage_for([{"asset_id": "file:skill:s1"}], "skill", projects_dir=str(root))
    assert out["projects_observed"] == 1
    assert out["axis_observed"] == 0, "옛 스냅샷을 스킬 관측으로 세고 있다"
    assert out["usage"]["file:skill:s1"]["countable"] is False, \
        "스킬을 셀 수 없는데 0 을 답으로 내보내고 있다"

    #: 축을 가진 스냅샷이 하나라도 생기면 그때부터 셀 수 있다.
    _project(root, "new", current={"template_id": "t", "agents": ["A"], "skills": ["s1"]})
    out2 = apu.usage_for([{"asset_id": "file:skill:s1"}], "skill", projects_dir=str(root))
    assert out2["axis_observed"] == 1
    assert out2["usage"]["file:skill:s1"]["countable"] is True
    assert out2["usage"]["file:skill:s1"]["project_count"] == 1


# ── 경로 격리 (cwd 가 아니라 PROJECTS_DIR 이 관문이다) ────────────────────
def test_default_path_goes_through_workspace_path(tmp_path, monkeypatch):
    """★★ 기본 경로가 `core.paths` 를 지나야 테스트가 격리된다.

    `PROJECTS_DIR` 을 모듈 상단에서 값으로 복사하면 그 순간 값이 고정돼 이 덮어쓰기가 먹지
    않는다(`core/paths.py` 머리말의 규칙). 그 상태에서는 이 테스트가 **실제 사용자 프로젝트**
    를 읽는다."""
    import core.paths
    root = tmp_path / "projects"
    _project(root, "p", current={"template_id": "t", "agents": ["A"]})
    monkeypatch.setattr(core.paths, "PROJECTS_DIR", str(root))
    out = apu.usage_for([{"asset_id": "file:agent:A"}], "agent")
    assert out["usage"]["file:agent:A"]["project_count"] == 1


def test_unknown_kind_counts_nothing_rather_than_everything(tmp_path):
    """★ 모르는 종류에 대해 «전부 사용 중» 을 내면 폐기가 막히고, «전부 미사용» 을 내면
    폐기가 부추겨진다. 축을 모르면 **셀 수 없다**(`countable` 은 관측 여부와 별개로 축이
    없으면 매칭이 0 이다)."""
    root = tmp_path / "projects"
    _project(root, "p", current={"template_id": "t", "agents": ["A"]})
    out = apu.usage_for([{"asset_id": "file:agent:A"}], "nope", projects_dir=str(root))
    assert out["axis"] == "" and out["usage"]["file:agent:A"]["project_count"] == 0
