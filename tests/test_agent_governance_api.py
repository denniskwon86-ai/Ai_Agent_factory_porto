"""★★★ [D-017 §9 P1-4] 조직별 자산 목록·복사·승인·폐기 API 의 권한 경계.

## 이 파일이 지키는 것

1. **목록은 가시 범위만.** 남의 조직·남의 개인 자산은 목록에도 상세에도 나오지 않는다.
2. **404 와 403 을 나눈다**(설계 §7.1). 안 보이는 자산의 상세는 404(존재를 알리지 않는다),
   보이는 자산의 변경 거부는 403(무엇이 부족한지 말해야 요청할 수 있다).
3. **조직 승인과 전사 승인은 다른 자격이다**(설계 §4.2). 부서 `manager` 는 자기 조직만
   승인하고 전사는 «승격 요청» 이다 — 한 부서장이 전사가 쓰는 정의를 혼자 확정하면 그 승인은
   누구도 검토하지 않은 승인이 된다.
4. **파일 자산은 복사만 된다.** 개정·승인·폐기는 «어디서 바꾸는지» 와 함께 막힌다.

## 계정은 실측해서 골랐다 (2026-08-04)

⚠️ `hikwon_1@lsmnm.com` 은 **AI 거버넌스 관리자 10명 중 하나**다. 「일반 부서원」 자리에 쓰면
  전사 공개까지 통과해 테스트가 **엉뚱한 이유로 통과**한다. 그래서 실측으로 골랐다:

  · `hikwon@lsmnm.com`    — 플랫폼 관리자(전부 가능)
  · `hikwon_4@lsmnm.com`  — AI 거버넌스 관리자(조직 범위 제한 없음, 전사 승인 가능)
  · `hikwon_7@lsmnm.com`  — 부서 manager. 관리 범위는 **`LS_MNM` 하나**, `is_ai_admin=False`
  · `hikwon_2@lsmnm.com`  — 부서 member. 관리 범위 없음, 승인·폐기 capability 없음
  · `hikwon_17@lsmnm.com` — viewer. 읽기만
"""
import pytest
from fastapi.testclient import TestClient

from core.agent_assets import (AgentAssetStore, ST_APPROVED, ST_DRAFT, ST_RETIRED, ST_REVIEW,
                               VIS_ENTERPRISE, VIS_PERSONAL, VIS_SCOPE, VIS_SYSTEM)

B = "/api/v1/agent-governance"

ADMIN = "hikwon@lsmnm.com"        # 플랫폼 관리자
AI_ADMIN = "hikwon_4@lsmnm.com"   # AI 거버넌스 관리자 (LS_MNM·MNM_BATTERY·MNM_COPPER)
MGR = "hikwon_7@lsmnm.com"        # 부서 manager, 관리 범위 = LS_MNM 만
MEMBER = "hikwon_2@lsmnm.com"     # 부서 member, 관리 범위 없음
VIEWER = "hikwon_17@lsmnm.com"    # viewer


def H(uid: str):
    return {"X-Factory-User": uid} if uid else {}


@pytest.fixture()
def client(monkeypatch, tmp_path, ecm_org_seed):
    """권한 강제를 켠 앱 + **격리된 자산 DB**.

    ⚠️⚠️ 싱글턴을 **두 곳** 갈아끼운다. 라우트와 어댑터가 각각 `from ... import agent_assets`
      로 이름을 가져갔으므로 한 곳만 패치하면 나머지 경로는 실제 개발 DB 를 계속 쓴다 —
      그러면 테스트가 실제 화면에 자산을 쌓고, 다른 테스트가 그것을 보고 깨진다.
    ⚠️ `org_directory` 는 해석한 스코프를 캐시한다. 강제를 켠 캐시가 남으면 뒤에 도는 다른
      파일의 테스트가 그것을 물려받는다 — 앞뒤로 비운다."""
    import config
    import core.paths
    from core.org_directory import org_directory
    from api.routes import agent_governance
    from core import agent_asset_adapter

    org_directory._invalidate()
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    store = AgentAssetStore(db_path=str(tmp_path / "assets.db"))
    monkeypatch.setattr(agent_governance, "agent_assets", store)
    monkeypatch.setattr(agent_asset_adapter, "agent_assets", store)
    #: ★★ 사용 집계는 **프로젝트 작업공간을 읽는다.** 격리하지 않으면 이 스위트가 사용자의
    #:   실제 프로젝트를 훑고, 그 결과 단언이 환경마다 달라진다. 격리 지점은 cwd 가 아니라
    #:   이 상수다(`core/paths.py` 머리말 — 상대경로를 절대경로로 고치며 옮긴 지점).
    monkeypatch.setattr(core.paths, "PROJECTS_DIR", str(tmp_path / "projects"))

    from main import app
    try:
        yield TestClient(app)
    finally:
        org_directory._invalidate()


def _create(client, uid, kind_path="agents", **kw):
    payload = {"name_ko": "테스트 자산", "body": {"role": "x"}, "visibility": VIS_PERSONAL}
    payload.update(kw)
    return client.post(f"{B}/{kind_path}", json=payload, headers=H(uid))


def _approved(client, uid, **kw):
    """생성 → 검토 요청 → 승인까지 마친 자산."""
    a = _create(client, uid, **kw).json()
    aid = a["asset_id"]
    client.post(f"{B}/agents/{aid}/submit", headers=H(uid))
    client.post(f"{B}/agents/{aid}/approve", headers=H(uid))
    return client.get(f"{B}/agents/{aid}", headers=H(uid)).json()


# ── 식별 (설계 §7.1) ──────────────────────────────────────────────────────
@pytest.mark.parametrize("path", ["agents", "workflows", "skills"])
def test_anonymous_cannot_list(client, path):
    """★★★ 익명은 자산 목록을 볼 수 없다. **401 이다** — 사용자가 할 일은 «로그인» 이다."""
    r = client.get(f"{B}/{path}")
    assert r.status_code == 401


def test_unregistered_user_is_refused_with_403(client):
    """★★ 등록되지 않은 사용자는 **403** 이다 — 식별은 됐고 권한이 없다.

    401 로 뭉개면 이미 이름을 밝힌 사용자가 계속 로그인을 시도한다."""
    r = client.get(f"{B}/agents", headers=H("nobody@example.com"))
    assert r.status_code == 403


def test_capabilities_needs_identification(client):
    assert client.get(f"{B}/capabilities").status_code == 401


# ── 권한 조회 (설계 §7) ───────────────────────────────────────────────────
def test_capabilities_reports_actions_per_kind(client):
    """★ 화면이 이것만 보고 버튼을 정할 수 있어야 한다 — 권한 없음만 주면 회색 버튼밖에
    만들 수 없다."""
    d = client.get(f"{B}/capabilities", headers=H(MGR)).json()
    assert set(d["asset_actions"]) == {"agents", "workflows", "skills"}
    assert d["asset_actions"]["agents"]["create"] is True
    assert d["can_publish_enterprise"] is False, "부서 manager 는 전사 승인 자격이 없다"

    v = client.get(f"{B}/capabilities", headers=H(VIEWER)).json()
    assert v["asset_actions"]["agents"]["read"] is True
    assert v["asset_actions"]["agents"]["create"] is False


def test_capabilities_shows_migration_debt_to_admins_only(client):
    """★★ 파일 자산 이관 부채(P1-2)는 **관리자에게만** 보인다.

    일반 사용자에게 «승인 이력 없는 자산 54건» 은 자기가 할 수 있는 일이 아니다 — 알려 줘도
    행동으로 이어지지 않고 화면만 불안하게 만든다."""
    a = client.get(f"{B}/capabilities", headers=H(ADMIN)).json()
    assert a["file_asset_migration"]["pending_total"] > 0
    v = client.get(f"{B}/capabilities", headers=H(VIEWER)).json()
    assert "file_asset_migration" not in v


# ── 목록 (설계 §6.1) ──────────────────────────────────────────────────────
def test_list_marks_whether_it_is_scoped(client):
    """★ 목록이 «전부» 인지 «범위 안» 인지 화면이 알아야 한다. 이 표시가 없으면 사용자는
    자기가 보는 목록을 전사 전체로 오해한다."""
    assert client.get(f"{B}/agents", headers=H(MGR)).json()["scoped"] is True
    assert client.get(f"{B}/agents", headers=H(ADMIN)).json()["scoped"] is False


def test_list_omits_body_but_keeps_version_count(client):
    """★ 목록에 본문을 실으면 스킬 31개 전문이 따라와 응답이 수십 KB 가 된다."""
    items = client.get(f"{B}/skills", headers=H(ADMIN)).json()["items"]
    assert items and all("body" not in i for i in items)
    assert all("version_count" in i for i in items)


def test_list_reports_real_version_count_and_runnable(client):
    """★★★ `list_assets` 행에는 `versions`·`runnable` 이 **없다**(그 둘은 `get()` 이 붙인다).

    그 사실을 모르고 `len(row.get("versions"))` 로 세면 `version_count` 가 항상 0 이 되고
    `runnable` 은 항상 `None` 이 된다 — 화면은 그것을 «버전 없음, 실행 불가» 로 읽는다.
    실제로 그렇게 만들었다가 P1-5 에서 같은 원인으로 조직 워크플로우가 목록에서 통째로
    사라진 것을 발견했다. 두 값을 여기서 잠근다."""
    a = _approved(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM")
    client.put(f"{B}/agents/{a['asset_id']}", json={"body": {"v": 2}}, headers=H(MGR))
    row = next(i for i in client.get(f"{B}/agents?include_files=false",
                                     headers=H(MGR)).json()["items"]
               if i["asset_id"] == a["asset_id"])
    assert row["version_count"] == 2, "개정 이력이 목록에서 0 으로 보인다"
    assert row["runnable"] is False, "개정으로 승인이 풀렸는데 실행 가능으로 보인다"

    b = _approved(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM")
    row_b = next(i for i in client.get(f"{B}/agents?include_files=false",
                                       headers=H(MGR)).json()["items"]
                 if i["asset_id"] == b["asset_id"])
    assert row_b["runnable"] is True and row_b["version_count"] == 1


def test_list_includes_file_assets_and_can_exclude_them(client):
    rows = client.get(f"{B}/agents", headers=H(ADMIN)).json()["items"]
    assert any(i["asset_id"].startswith("file:") for i in rows)
    off = client.get(f"{B}/agents?include_files=false", headers=H(ADMIN)).json()["items"]
    assert not any(i["asset_id"].startswith("file:") for i in off)


def test_list_hides_other_peoples_personal_drafts(client):
    """★★★ 개인 초안은 **플랫폼 관리자에게도** 보이지 않는다(저장소 계약 P1-1).

    ⚠️ 이것은 관리자 권한의 결함이 아니라 개인 초안의 정의다. 관리자가 남의 초안을 들여다볼
      수 있어야 한다면 그것은 설계 결정이 필요한 별개 사안이다."""
    mine = _create(client, MEMBER, visibility=VIS_PERSONAL).json()["asset_id"]
    for uid in (ADMIN, AI_ADMIN, MGR):
        ids = [i["asset_id"] for i in client.get(f"{B}/agents", headers=H(uid)).json()["items"]]
        assert mine not in ids, f"{uid} 에게 남의 개인 초안이 보인다"
    ids = [i["asset_id"] for i in client.get(f"{B}/agents", headers=H(MEMBER)).json()["items"]]
    assert mine in ids, "본인에게는 보여야 한다"


def test_status_filter(client):
    a = _approved(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM")
    got = client.get(f"{B}/agents?status={ST_APPROVED}", headers=H(MGR)).json()["items"]
    assert a["asset_id"] in [i["asset_id"] for i in got]
    drafts = client.get(f"{B}/agents?status={ST_DRAFT}", headers=H(MGR)).json()["items"]
    assert a["asset_id"] not in [i["asset_id"] for i in drafts]


# ── 가려진 자산 (설계 §8.3 「현재 보는 범위와 숨겨진 자산 수」) ──────────────
#
# ★★ `scoped` 는 «걸렀다» 만 말하고 «얼마나» 를 말하지 않는다. 사용자는 3건을 보면서 그것이
#   전부인지 30건 중 3건인지 알 수 없고, **숫자가 있으면 사람은 그것을 전부라고 읽는다**
#   (P4-1 에서 총비용의 8%만 보이던 대시보드와 같은 유형이다).
#
# ⚠️ 계약은 `api.deps.hidden_envelope` 한 곳에 있다 — **존재는 누구에게나, 정확한 건수는 자료를
#   관리할 사람에게만.** 아래는 그 계약이 이 라우트에서 실제로 지켜지는지를 본다. 규칙 자체의
#   자격 판정은 `test_listing_visibility_gate.test_agent_exact_count_rule_covers_ai_admin`.
#
# 실측으로 고른 자리(2026-08-08): 플랫폼 관리자는 `scoped=False` 라 애초에 가려지는 것이 없고,
# `hikwon_4` 만이 **걸러지면서 셀 수 있는** 유일한 계정이다. 그래서 그 계정이 규칙에서 빠지면
# 이 기능은 아무에게도 도달하지 않는다.
UNSEEN_ORG = "ORG_NO_ONE_MANAGES"   # 어느 시드 계정의 관리 범위에도 없는 조직


def _hidden_assets(client, n=1, **kw):
    """**어느 시드 계정에도 보이지 않는** 조직 자산. 무제한 권한자만 만들 수 있다."""
    out = []
    for _ in range(n):
        r = _create(client, ADMIN, visibility=VIS_SCOPE, owner_scope_id=UNSEEN_ORG, **kw)
        assert r.status_code == 200, r.text
        out.append(r.json())
    return out


def test_scoped_list_says_something_is_hidden_without_leaking_how_many(client):
    """★★★ 가려진 것이 «있다» 는 사실은 누구에게나, 건수는 아니다.

    남의 조직에 에이전트가 몇 개 있는가는 **그 자체로 정보다.** 부서 manager 가 그 수를 알면
    「우리보다 저쪽이 30개 많다」를 근거 없이 읽게 되고, 그것은 목록 API 가 할 일이 아니다."""
    _hidden_assets(client, 2)
    for uid in (MGR, MEMBER, VIEWER):
        d = client.get(f"{B}/agents", headers=H(uid)).json()
        assert d["scoped"] is True
        assert d["hidden_present"] is True, f"{uid} 에게 목록이 전량처럼 보인다"
        assert "hidden_count" not in d, f"{uid} 에게 남의 조직 자산 규모가 샌다"


def test_ai_admin_sees_the_exact_hidden_count(client):
    """★★ AI 관리자에게는 정확한 수를 준다 — 「전사에 에이전트가 몇 개인가」는 그가 답해야
    하는 질문이고, 규모를 모르면 정비 계획을 세울 수 없다."""
    _hidden_assets(client, 3)
    d = client.get(f"{B}/agents", headers=H(AI_ADMIN)).json()
    assert d["hidden_present"] is True and d["hidden_count"] == 3


def test_unscoped_list_carries_no_hidden_envelope(client):
    """★ 범위 필터가 걸리지 않은 목록에는 봉투를 붙이지 않는다 — 전량이므로 가려진 것이 없고,
    거기에 «가려진 자산 0건» 을 적으면 화면이 없는 위험을 그린다."""
    _hidden_assets(client, 2)
    d = client.get(f"{B}/agents", headers=H(ADMIN)).json()
    assert d["scoped"] is False
    assert "hidden_present" not in d and "hidden_count" not in d


def test_hidden_present_is_false_when_nothing_is_hidden(client):
    """★★ 이 값이 **항상 True** 면 아무 뜻이 없다. 화면은 늘 「가려진 것이 있다」를 띄우고,
    사용자는 그 문구를 배경으로 읽게 된다 — 그러면 진짜로 가려진 날에도 아무도 안 본다."""
    _create(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM")
    d = client.get(f"{B}/agents", headers=H(MGR)).json()
    assert d["hidden_present"] is False and "hidden_count" not in d


def test_hidden_count_uses_the_same_filters_as_the_list(client):
    """★★★ 분모는 목록과 **같은 조건**으로 세어야 한다.

    `?status=DRAFT` 로 초안을 보는 사람에게 전체 상태의 가려진 수를 주면, 그는 「초안이 그만큼
    더 있다」로 읽는다. 필터가 좁을수록 이 거짓말은 커진다 — 조건을 두 곳에 적는 순간
    한쪽만 고쳐지기 때문에, 여기서 두 축(`status`·`include_files`)을 함께 잠근다."""
    _hidden_assets(client, 2)                                   # DRAFT 2건
    _approved(client, ADMIN, visibility=VIS_SCOPE, owner_scope_id=UNSEEN_ORG)   # APPROVED 1건

    whole = client.get(f"{B}/agents", headers=H(AI_ADMIN)).json()
    assert whole["hidden_count"] == 3

    drafts = client.get(f"{B}/agents?status={ST_DRAFT}", headers=H(AI_ADMIN)).json()
    assert drafts["hidden_count"] == 2, "상태로 거른 목록에 전체 상태의 가려진 수가 붙었다"

    #: ⚠️ 파일 자산은 제품 기본(SYSTEM)이라 **누구에게나 보인다.** 목록에서 뺀 것을 분모에만
    #   남기면 「수십 건이 가려졌다」가 되고, 그 수는 조직과 아무 상관이 없다.
    nofiles = client.get(f"{B}/agents?include_files=false", headers=H(AI_ADMIN)).json()
    assert nofiles["hidden_count"] == 3, "목록에서 뺀 파일 자산이 «가려진 것»으로 세어졌다"


def test_my_own_personal_draft_does_not_shrink_the_hidden_count(client):
    """★★★ 분모와 분자의 **모집단이 같아야 한다.**

    전량 조회에 요청자 신원을 넘기지 않으면 «내 개인 초안» 이 분모에서만 빠지고, 가려진 수가
    그만큼 **조용히 줄어든다.** 화면에는 여전히 그럴듯한 숫자가 있으므로 아무도 이상을 느끼지
    못한다 — 틀린 숫자는 숫자가 없는 것보다 나쁘다(P4-1 에서 같은 유형을 겪었다).

    ⚠️ 이 결함은 목록이 «맞게» 보이는 동안에도 성립한다. 그래서 목록 내용만 보는 테스트로는
      절대 잡히지 않는다."""
    _hidden_assets(client, 2)
    r = _create(client, AI_ADMIN, visibility=VIS_PERSONAL)
    assert r.status_code == 200, r.text
    d = client.get(f"{B}/agents", headers=H(AI_ADMIN)).json()
    assert r.json()["asset_id"] in [i["asset_id"] for i in d["items"]], "전제가 깨졌다"
    assert d["hidden_count"] == 2, "내 개인 초안이 분모에서만 빠져 가려진 수가 줄었다"


def test_other_peoples_personal_drafts_are_never_counted_as_hidden(client):
    """★★★ 개인 초안은 **가려진 것으로도 세지 않는다.**

    「가려진 자산 2건」에 남의 개인 초안이 섞이면 관리자는 그것을 «요청하면 볼 수 있는 자산»
    으로 읽는다. 그러나 개인 초안은 플랫폼 관리자에게도 보이지 않는 것이 저장소 계약이고
    (`test_list_hides_other_peoples_personal_drafts`), 규모조차 남의 것이 아니다."""
    _create(client, MEMBER, visibility=VIS_PERSONAL)
    _create(client, MEMBER, visibility=VIS_PERSONAL)
    d = client.get(f"{B}/agents", headers=H(AI_ADMIN)).json()
    assert d["hidden_present"] is False, "남의 개인 초안이 «가려진 자산»으로 세어졌다"


@pytest.mark.parametrize("path", ["agents", "workflows", "skills"])
def test_hidden_envelope_is_on_every_kind(client, path):
    """★ 종류마다 따로 적으면 한 종류에서만 빠진다 — 그리고 빠진 쪽에서 사용자는 목록을
    전량으로 읽는다. 세 종류가 같은 계약을 쓰는지 여기서 본다."""
    kind_kw = {"skills": {"kind_path": "skills"}, "workflows": {"kind_path": "workflows"}}
    r = _create(client, ADMIN, visibility=VIS_SCOPE, owner_scope_id=UNSEEN_ORG,
                **kind_kw.get(path, {}))
    assert r.status_code == 200, r.text
    d = client.get(f"{B}/{path}", headers=H(MGR)).json()
    assert d["hidden_present"] is True and "hidden_count" not in d


# ── 상세는 안 보이면 404 (설계 §7.1) ──────────────────────────────────────
def test_invisible_asset_detail_is_404_not_403(client):
    """★★★ 다른 사람의 개인 자산은 **404** 다. 403 은 «그런 자산이 있다» 를 알려 준다."""
    mine = _create(client, MEMBER, visibility=VIS_PERSONAL).json()["asset_id"]
    assert client.get(f"{B}/agents/{mine}", headers=H(MGR)).status_code == 404


def test_unknown_kind_and_id_are_404(client):
    assert client.get(f"{B}/foos", headers=H(ADMIN)).status_code == 404
    assert client.get(f"{B}/agents/as_nope", headers=H(ADMIN)).status_code == 404


def test_kind_mismatch_is_404(client):
    """★ 종류를 바꿔 가며 존재를 탐색할 수 없다 — 스킬 id 를 `/agents` 로 물으면 404 다."""
    assert client.get(f"{B}/agents/file:skill:rfp_skill", headers=H(ADMIN)).status_code == 404


# ── 생성 자격 (설계 §4.2) ─────────────────────────────────────────────────
def test_viewer_cannot_create(client):
    assert _create(client, VIEWER).status_code == 403


def test_member_can_create_personal_but_not_org_asset(client):
    """★★ 관리 범위가 없는 부서원은 **개인 초안까지만** 만든다."""
    assert _create(client, MEMBER, visibility=VIS_PERSONAL).status_code == 200
    r = _create(client, MEMBER, visibility=VIS_SCOPE, owner_scope_id="LS_MNM")
    assert r.status_code == 403 and "관리 범위" in r.json()["detail"]


def test_manager_cannot_create_outside_managed_scope(client):
    """★★★ 부서 manager 의 관리 범위는 `LS_MNM` 하나다. 다른 조직 자산을 만들 수 없다."""
    r = _create(client, MGR, visibility=VIS_SCOPE, owner_scope_id="MNM_BATTERY")
    assert r.status_code == 403 and "MNM_BATTERY" in r.json()["detail"]


def test_enterprise_visibility_is_blocked_at_creation(client):
    """★★★ 전사 공개를 **생성 시점에** 막는다.

    승인만 막으면 부서원이 만든 초안이 목록에 «전사» 로 올라앉는다 — 실행은 안 되지만 목록은
    그것을 전사 자산으로 보여 주고, 사람은 목록을 믿는다."""
    for uid in (MGR, MEMBER):
        r = _create(client, uid, visibility=VIS_ENTERPRISE, owner_scope_id="LS_MNM")
        assert r.status_code == 403 and "전사" in r.json()["detail"]
    ok = _create(client, AI_ADMIN, visibility=VIS_ENTERPRISE, owner_scope_id="LS_MNM")
    assert ok.status_code == 200, "AI 거버넌스 관리자는 전사 자산을 만들 수 있다"


def test_system_visibility_cannot_be_created(client):
    """★★ SYSTEM 은 제품 기본 자산의 **표시**이며 만들 수 없다 — 복사해서 쓴다."""
    r = _create(client, ADMIN, visibility=VIS_SYSTEM, owner_scope_id="LS_MNM")
    assert r.status_code == 403 and "복사" in r.json()["detail"]


def test_skills_propose_alias_works(client):
    """설계 §7 은 스킬 초안을 `POST /skills/propose` 로 적었다 — 그대로 불러도 동작해야 한다."""
    r = client.post(f"{B}/skills/propose",
                    json={"name_ko": "새 규칙", "body": {"markdown": "# 규칙"},
                          "visibility": VIS_PERSONAL}, headers=H(MGR))
    assert r.status_code == 200 and r.json()["kind"] == "skill"


# ── 승인 흐름 ─────────────────────────────────────────────────────────────
def test_draft_cannot_be_approved_without_review(client):
    """★★ 검토 요청을 거치지 않은 초안은 승인되지 않는다 — 지름길이 있으면 검토는 형식이 된다."""
    a = _create(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM").json()
    r = client.post(f"{B}/agents/{a['asset_id']}/approve", headers=H(MGR))
    assert r.status_code == 403 and "검토 요청" in r.json()["detail"]


def test_approve_records_who_approved_it(client):
    a = _approved(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM")
    assert a["status"] == ST_APPROVED and a["approved_by"] == MGR and a["runnable"] is True


def test_revision_drops_approval(client):
    """★★★ 개정하면 승인이 풀린다 — 내용이 바뀐 뒤에도 승인이 남으면 그 승인은
    **읽지 않은 문서에 대한 승인**이다."""
    a = _approved(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM")
    r = client.put(f"{B}/agents/{a['asset_id']}", json={"body": {"role": "바뀜"}}, headers=H(MGR))
    d = r.json()
    assert d["status"] == ST_DRAFT and d["approved_by"] == "" and d["runnable"] is False
    assert d["current_version"] == 2, "버전을 덮어쓰지 않고 쌓아야 한다"


def test_other_orgs_asset_is_invisible_so_approval_is_404(client):
    """★★★ 다른 조직 자산은 애초에 **보이지 않는다** — 승인 시도는 403 이 아니라 **404** 다.

    실측(2026-08-04): `hikwon_7` 의 읽기 범위는 `LS_MNM` 하나이고 `MNM_BATTERY` 는 그 하위지만
    **하향 열람은 경영진에게만** 준다(`viewer_visible_scopes`). 그러니 존재를 알리지 않는 것이
    맞다. 403 을 주면 «MNM_BATTERY 에 그런 자산이 있다» 를 알려 준다."""
    a = _create(client, AI_ADMIN, visibility=VIS_SCOPE, owner_scope_id="MNM_BATTERY").json()
    client.post(f"{B}/agents/{a['asset_id']}/submit", headers=H(AI_ADMIN))
    assert client.post(f"{B}/agents/{a['asset_id']}/approve", headers=H(MGR)).status_code == 404
    assert client.get(f"{B}/agents/{a['asset_id']}", headers=H(MGR)).status_code == 404


def _narrow_manage_scope(monkeypatch, uid: str):
    """이 사용자만 **관리 범위를 비운다**(읽기 범위는 그대로).

    ⚠️ 왜 인위적으로 만드는가: 실측해 보니 지금 조직 데이터에는 «읽기 범위는 넓고 관리 범위는
      좁으면서 승인 capability 가 있는» 계정이 **하나도 없다** — capability 와 범위가 정렬돼
      있다. 그 정렬은 **부서 역할 데이터가 만든 우연**이고 코드가 보장하는 것이 아니다.
      역할이 한 번 바뀌면 그 조합이 생기고, 그때 범위 판정이 없으면 남의 조직 자산이 승인된다.
      그래서 그 상황을 만들어 두고 막히는지 확인한다."""
    import dataclasses
    from api import deps
    orig = deps.capabilities_of

    def patched(p):
        c = orig(p)
        if (p.user_id or "") == uid:
            # AI 관리자·플랫폼 관리자 플래그도 내린다 — 그것이 있으면 범위 판정을 건너뛴다.
            return dataclasses.replace(c, manageable_scope_nodes=frozenset(),
                                       is_ai_admin=False, is_platform_admin=False)
        return c

    monkeypatch.setattr(deps, "capabilities_of", patched)


def test_visible_but_unmanaged_asset_cannot_be_approved(client, monkeypatch):
    """★★★ **조직 범위 판정 경로.** 자산이 보이고 승인 capability 도 있지만, 그 조직의
    관리자가 아니면 승인할 수 없다.

    이 경계가 없으면 «볼 수 있으면 승인할 수 있다» 가 되고, 그것은 열람 권한이 승인 권한으로
    승격되는 것이다."""
    a = _create(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM").json()
    client.post(f"{B}/agents/{a['asset_id']}/submit", headers=H(MGR))
    _narrow_manage_scope(monkeypatch, MGR)
    assert client.get(f"{B}/agents/{a['asset_id']}", headers=H(MGR)).status_code == 200, \
        "자산은 여전히 보여야 한다 — 안 보이면 이 테스트는 범위 판정을 확인하지 못한다"
    r = client.post(f"{B}/agents/{a['asset_id']}/approve", headers=H(MGR))
    assert r.status_code == 403
    # ★★ [D-018 ③] 오류 메시지는 **사람이 읽는 이름**을 보여준다. 정본 해시(`node_4140…`)를
    #   그대로 노출하면 사용자는 무슨 조직 때문에 막혔는지 알 수 없고 관리자에게 무엇을
    #   요청해야 하는지도 모른다 — 백필 후 실제로 그런 메시지가 나가고 있었다.
    detail = r.json()["detail"]
    assert "LS_MNM" in detail or "LS MnM" in detail, f"조직을 식별할 수 없는 메시지: {detail}"
    assert "node_" not in detail, f"정본 해시가 사용자에게 노출됐다: {detail}"
    assert client.post(f"{B}/agents/{a['asset_id']}/retire", headers=H(MGR)).status_code == 403


def test_manager_cannot_approve_enterprise_asset(client):
    """★★★ 전사 공개 자산의 승인은 부서 manager 의 자격이 아니다(설계 §4.2 «승격 요청만»)."""
    a = _create(client, AI_ADMIN, visibility=VIS_ENTERPRISE, owner_scope_id="LS_MNM").json()
    client.post(f"{B}/agents/{a['asset_id']}/submit", headers=H(AI_ADMIN))
    r = client.post(f"{B}/agents/{a['asset_id']}/approve", headers=H(MGR))
    assert r.status_code == 403 and "전사" in r.json()["detail"]


def test_member_cannot_approve_or_retire(client):
    """부서 member 는 승인·폐기 capability 자체가 없다.

    ⚠️ 자산은 **member 에게 보이는 조직**(`MNM_BATTERY` — 실측한 읽기 범위)에 둔다. 안 보이는
      조직에 두면 404 가 나고, 그러면 이 테스트는 «capability 가 없어서 막혔다» 를 확인하지
      못한 채 통과한다."""
    a = _create(client, AI_ADMIN, visibility=VIS_SCOPE, owner_scope_id="MNM_BATTERY").json()
    client.post(f"{B}/agents/{a['asset_id']}/submit", headers=H(AI_ADMIN))
    assert client.get(f"{B}/agents/{a['asset_id']}", headers=H(MEMBER)).status_code == 200, \
        "member 에게 보이는 자산이어야 한다"
    assert client.post(f"{B}/agents/{a['asset_id']}/approve", headers=H(MEMBER)).status_code == 403
    assert client.post(f"{B}/agents/{a['asset_id']}/retire", headers=H(MEMBER)).status_code == 403


def test_member_cannot_revise_org_asset(client):
    """member 는 자기 조직 자산도 **고칠 수 없다** — 볼 수 있다고 바꿀 수 있는 것이 아니다."""
    a = _create(client, AI_ADMIN, visibility=VIS_SCOPE, owner_scope_id="MNM_BATTERY").json()
    r = client.put(f"{B}/agents/{a['asset_id']}", json={"body": {}}, headers=H(MEMBER))
    assert r.status_code == 403 and "관리 범위" in r.json()["detail"]


def test_author_can_keep_revising_own_draft(client):
    """★ 작성자 본인은 자기 초안을 계속 고칠 수 있다 — 그러지 않으면 관리자가 아닌 사람은
    자기가 만든 것을 한 번 저장한 뒤 손댈 수 없다."""
    a = _create(client, MEMBER, visibility=VIS_PERSONAL).json()
    r = client.put(f"{B}/agents/{a['asset_id']}", json={"body": {"v": 2}}, headers=H(MEMBER))
    assert r.status_code == 200 and r.json()["current_version"] == 2


def test_cannot_revise_someone_elses_personal_asset(client):
    """남의 개인 자산은 애초에 보이지 않으므로 **404** 다(403 이면 존재를 알린다)."""
    a = _create(client, MEMBER, visibility=VIS_PERSONAL).json()
    assert client.put(f"{B}/agents/{a['asset_id']}", json={"body": {}},
                      headers=H(MGR)).status_code == 404


def test_retire_keeps_the_row_and_hides_it_from_default_list(client):
    """★★ 폐기는 행을 지우지 않는다 — 과거 산출물이 이 자산을 가리키고 있다."""
    a = _approved(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM")
    aid = a["asset_id"]
    r = client.post(f"{B}/agents/{aid}/retire", headers=H(MGR))
    assert r.status_code == 200 and r.json()["status"] == ST_RETIRED
    assert r.json()["runnable"] is False, "폐기된 자산이 실행되면 안 된다"
    ids = [i["asset_id"] for i in client.get(f"{B}/agents", headers=H(MGR)).json()["items"]]
    assert aid not in ids
    ids2 = [i["asset_id"] for i in
            client.get(f"{B}/agents?include_retired=true", headers=H(MGR)).json()["items"]]
    assert aid in ids2, "폐기 이력은 조회할 수 있어야 한다"
    assert client.get(f"{B}/agents/{aid}", headers=H(MGR)).status_code == 200


# ── 파일 자산 (P1-2 연동) ─────────────────────────────────────────────────
@pytest.mark.parametrize("action", ["submit", "approve", "retire"])
def test_file_asset_cannot_be_changed_here(client, action):
    """★★★ 파일 자산은 여기서 바꾸는 것이 아니다. **어디서 바꾸는지 말한다.**

    ⚠️ 404(«없다»)로 두면 호출부는 자산을 다시 만들고, 그때 같은 정의가 두 벌이 된다."""
    r = client.post(f"{B}/agents/file:agent:RFP_Analyst/{action}", headers=H(ADMIN))
    assert r.status_code == 403
    assert "에이전트 통제소" in r.json()["detail"] and "복사" in r.json()["detail"]


def test_file_asset_cannot_be_revised_here(client):
    r = client.put(f"{B}/agents/file:agent:RFP_Analyst", json={"body": {}}, headers=H(ADMIN))
    assert r.status_code == 403 and "에이전트 통제소" in r.json()["detail"]


def test_file_asset_detail_shows_migration_state(client):
    """★ 파일 자산은 `APPROVED` 이지만 **승인자가 없다** — 그 사실이 상세에 드러나야 한다."""
    d = client.get(f"{B}/agents/file:agent:RFP_Analyst", headers=H(MGR)).json()
    assert d["source"] == "LEGACY" and d["status"] == ST_APPROVED
    assert d["approved_by"] == "" and d["needs_migration"] is True
    assert d["edit_via"] == "에이전트 통제소"


def test_file_asset_can_be_copied_into_an_org_asset(client):
    """★★★ 복사는 막지 않는다 — 막으면 «제품 기본은 복사해서 쓰십시오» 를 따를 방법이 없다."""
    r = client.post(f"{B}/agents/file:agent:RFP_Analyst/copy",
                    json={"visibility": VIS_SCOPE, "owner_scope_id": "LS_MNM"}, headers=H(MGR))
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == ST_DRAFT, "복사본이 승인 상태로 시작하면 검토를 건너뛴다"
    assert d["copied_from"] == "file:agent:RFP_Analyst" and d["copied_from_source"] == "LEGACY"
    # ★ [D-018 ⑥] 코드로 보내도 **정본 `node_id` 로 저장된다.** 그래야 백필로 정리한 컬럼에
    #   코드가 다시 들어오지 않는다(신규 쓰기 강제).
    assert d["owner_scope_id"].startswith("node_"),         f"소유 조직이 정본으로 저장되지 않았다: {d['owner_scope_id']}"
    assert d["approved_by"] == ""
    assert d["body"].get("id") == "RFP_Analyst", "원본 정의가 복사돼야 한다"


def test_copied_skill_carries_the_document_body(client):
    """★★★ 스킬 목록의 본문은 파일명만 있다. 그대로 복사하면 **빈 규칙**이 된다 —
    빈 규칙은 «규칙 없음» 으로 실행된다."""
    r = client.post(f"{B}/skills/file:skill:rfp_skill/copy",
                    json={"visibility": VIS_PERSONAL}, headers=H(MGR))
    assert r.status_code == 200
    body = client.get(f"{B}/skills/{r.json()['asset_id']}", headers=H(MGR)).json()["body"]
    assert len(body.get("markdown") or "") > 100, "복사본이 빈 규칙이다"


def test_copy_requires_being_able_to_read_the_source(client):
    """★★★ 원본을 읽을 수 없으면 복사도 못 한다 — 그러지 않으면 id 를 아는 사람이 남의
    조직 자산을 복사해 내용을 들여다볼 수 있다."""
    src = _create(client, MEMBER, visibility=VIS_PERSONAL).json()["asset_id"]
    r = client.post(f"{B}/agents/{src}/copy", json={"visibility": VIS_PERSONAL}, headers=H(MGR))
    assert r.status_code == 404


def test_copy_target_scope_is_checked(client):
    """복사도 **생성**이다 — 만들 수 없는 범위로는 복사할 수 없다."""
    r = client.post(f"{B}/agents/file:agent:RFP_Analyst/copy",
                    json={"visibility": VIS_SCOPE, "owner_scope_id": "MNM_BATTERY"},
                    headers=H(MGR))
    assert r.status_code == 403 and "MNM_BATTERY" in r.json()["detail"]


def test_viewer_cannot_copy(client):
    r = client.post(f"{B}/agents/file:agent:RFP_Analyst/copy",
                    json={"visibility": VIS_PERSONAL}, headers=H(VIEWER))
    assert r.status_code == 403


# ── 감사 (설계 §7.1) ──────────────────────────────────────────────────────
def test_changes_and_denials_are_audited(client, monkeypatch):
    """★★ «누가 무엇을 시도했는가» 를 나중에 물을 수 있어야 한다.

    ⚠️ 승인은 `APPROVAL_GRANTED`, 정의 변경은 `AGENT_ASSET_CHANGED` 로 나눈다. 한 상수로
      묶으면 «무엇이 바뀌어 결과가 달라졌는가» 를 되짚을 수 없다."""
    from core.enterprise_context import audit
    seen = []
    monkeypatch.setattr(audit, "record",
                        lambda event, **kw: seen.append((event, kw.get("outcome"))) or True)

    a = _create(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM").json()
    client.post(f"{B}/agents/{a['asset_id']}/submit", headers=H(MGR))
    client.post(f"{B}/agents/{a['asset_id']}/approve", headers=H(MGR))
    client.post(f"{B}/agents/{a['asset_id']}/retire", headers=H(MEMBER))     # 거부

    events = [e for e, _ in seen]
    assert audit.AGENT_ASSET_CHANGED in events, "정의 변경이 기록되지 않았다"
    assert audit.APPROVAL_GRANTED in events, "승인이 기록되지 않았다"
    assert ("denied" in [o for _, o in seen]), "거부가 기록되지 않았다"


def test_hidden_detail_lookup_is_audited(client, monkeypatch):
    """★ 404 로 은폐하는 것은 **응답**이지 기록이 아니다 — 시도는 남아야 한다."""
    from core.enterprise_context import audit
    seen = []
    monkeypatch.setattr(audit, "record",
                        lambda event, **kw: seen.append((event, kw.get("resource_id"))) or True)
    mine = _create(client, MEMBER, visibility=VIS_PERSONAL).json()["asset_id"]
    seen.clear()
    client.get(f"{B}/agents/{mine}", headers=H(MGR))
    assert any(e == audit.ACCESS_DENIED_SCOPE_MISMATCH and rid == mine for e, rid in seen)


# ── 사용 중인 프로젝트 수 (설계 §8.4) ────────────────────────────────────
def _snapshot(tmp_path, project: str, **current):
    """프로젝트 작업공간에 구성 스냅샷을 만든다."""
    import json
    from core.config_snapshot import SNAPSHOT_FILE
    d = tmp_path / "projects" / project
    d.mkdir(parents=True, exist_ok=True)
    (d / SNAPSHOT_FILE).write_text(json.dumps({"current": current}), encoding="utf-8")


def test_usage_route_is_not_swallowed_by_the_asset_id_route(client):
    """★★★ `/{kind_path}/{asset_id}` 가 먼저 등록돼 있으면 `/agents/usage` 가
    `asset_id="usage"` 로 잡혀 **404** 가 된다.

    그 404 는 화면에서 「사용 현황이 없다」로 읽히고, 화면은 그것을 「아무도 안 쓴다」로
    그린다 — 라우트 등록 순서 하나가 폐기 판단을 뒤집는다."""
    r = client.get(f"{B}/agents/usage", headers=H(ADMIN))
    assert r.status_code == 200, "라우트가 asset_id 로 잡혔다(등록 순서)"
    assert "usage" in r.json() and r.json()["kind"] == "agent"


@pytest.mark.parametrize("path", ["agents", "workflows", "skills"])
def test_usage_needs_identification(client, path):
    assert client.get(f"{B}/{path}/usage").status_code == 401


def test_usage_says_not_countable_when_nothing_recorded(client):
    """★★★ 프로젝트가 구성을 기록하기 전에는 **0 이 답이 아니다.**

    2026-08-08 실측 상태가 바로 이것이었다(56개 프로젝트 중 기록 0개). `countable` 없이
    숫자만 내보내면 화면은 「전부 미사용」을 그리고, 사람은 그것을 근거로 자산을 지운다."""
    d = client.get(f"{B}/agents/usage", headers=H(ADMIN)).json()
    assert d["projects_observed"] == 0
    assert all(v["countable"] is False for v in d["usage"].values())


def test_usage_counts_projects_that_reference_the_asset(client, tmp_path):
    _snapshot(tmp_path, "p1", template_id="default", agents=["RFP_Analyst"], skills=[])
    _snapshot(tmp_path, "p2", template_id="default", agents=["RFP_Analyst"], skills=[])
    d = client.get(f"{B}/agents/usage", headers=H(ADMIN)).json()
    assert d["projects_observed"] == 2
    hit = d["usage"].get("file:agent:RFP_Analyst")
    assert hit and hit["project_count"] == 2 and hit["countable"] is True


def test_project_names_go_only_to_those_who_manage_the_assets(client, tmp_path):
    """★★ 「몇 개」와 「어느 프로젝트」는 다른 자격이다.

    자산을 볼 수 있다고 해서 그것이 **어느 프로젝트에 쓰이는지**까지 알아야 하는 것은 아니다 —
    프로젝트 이름은 그 자체로 무엇을 만들고 있는지 알려준다. 판정은 `hidden_envelope` 과
    같은 규칙을 쓴다(`may_see_exact_count`) — 여기서 새로 만들면 두 규칙이 갈라진다."""
    _snapshot(tmp_path, "secret_project", template_id="default", agents=["RFP_Analyst"])
    for uid in (ADMIN, AI_ADMIN):
        d = client.get(f"{B}/agents/usage", headers=H(uid)).json()
        assert "projects" in d["usage"]["file:agent:RFP_Analyst"], f"{uid} 가 이름을 못 본다"
    for uid in (MGR, MEMBER, VIEWER):
        d = client.get(f"{B}/agents/usage", headers=H(uid)).json()
        v = d["usage"]["file:agent:RFP_Analyst"]
        assert "projects" not in v, f"{uid} 에게 프로젝트 이름이 샌다"
        assert v["project_count"] == 1, "수까지 가리면 폐기 판단을 아무도 못 한다"


# ── 전사 승격 (설계 §4.2 · §8.6) ─────────────────────────────────────────
def test_promotion_request_does_not_widen_visibility(client):
    """★★★ **요청은 공개가 아니다.**

    요청한 순간 자산이 전사에 보이면 그것은 요청이 아니라 공개이고, 되돌릴 방법도 없다.
    부서 manager 가 「승격 요청」을 눌렀을 때 남의 조직에 우리 정의가 노출되면 아무도 그
    버튼을 두 번 누르지 않는다."""
    a = _approved(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM")
    r = client.post(f"{B}/agents/{a['asset_id']}/promote", headers=H(MGR))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["promotion_outcome"] == "요청"
    assert d["visibility"] == VIS_SCOPE, "요청만 했는데 전사로 공개됐다"
    assert d["status"] == ST_APPROVED, "요청이 조직 승인을 풀어 버렸다"
    assert d["promotion_requested_by"] == MGR and d["promotion_requested_at"]


def test_ai_admin_promotion_reopens_review(client):
    """★★★ 승격은 **승인을 다시 받게 한다.**

    조직 승인과 전사 승인은 다른 자격이다(설계 §4.2). 조직 승인만 받은 정의가 전사 자산으로
    «승인됨» 이 되면 **아무도 검토하지 않은 전사 자산**이 생기고, `approved_by` 는 전사 승인을
    한 적 없는 사람을 가리킨다."""
    a = _approved(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM")
    d = client.post(f"{B}/agents/{a['asset_id']}/promote", headers=H(AI_ADMIN)).json()
    assert d["promotion_outcome"] == "확정"
    assert d["visibility"] == VIS_ENTERPRISE
    assert d["status"] == ST_REVIEW, "전사 자산이 검토 없이 승인 상태로 올라갔다"
    assert not d["approved_by"], "조직 승인자가 전사 승인자로 남았다"


def test_promotion_requires_org_approval_first(client):
    """★★ 검토되지 않은 초안이 전사 목록에 오르면 그 목록을 아무도 믿지 않게 된다."""
    a = _create(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM").json()
    r = client.post(f"{B}/agents/{a['asset_id']}/promote", headers=H(MGR))
    assert r.status_code == 403 and "조직 승인" in r.json()["detail"]


def test_personal_draft_cannot_jump_straight_to_enterprise(client):
    a = _create(client, MEMBER, visibility=VIS_PERSONAL).json()
    r = client.post(f"{B}/agents/{a['asset_id']}/promote", headers=H(MEMBER))
    assert r.status_code == 403


def test_file_asset_promotion_tells_you_what_to_do_instead(client):
    """★ 막기만 하면 사용자는 규칙을 따를 방법을 모른다 — 무엇을 하면 되는지 함께 말한다."""
    r = client.post(f"{B}/agents/file:agent:RFP_Analyst/promote", headers=H(ADMIN))
    assert r.status_code == 403 and "복사" in r.json()["detail"]


def test_member_without_approval_rights_cannot_even_request(client):
    """★ 자기 조직 자산을 승인할 수도 없는 사람이 그것을 전사로 올려 달라고 요청하는 것은
    순서가 뒤집힌 것이다 — 조직 승인 자격을 먼저 요구한다."""
    a = _approved(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM")
    assert client.post(f"{B}/agents/{a['asset_id']}/promote",
                       headers=H(MEMBER)).status_code == 403
    assert client.post(f"{B}/agents/{a['asset_id']}/promote",
                       headers=H(VIEWER)).status_code == 403


def test_already_enterprise_asset_is_refused(client):
    #: ⚠️ 전사 공개도 **소유 조직을 요구한다**(저장소 계약) — 소유가 없으면 나중에 «이 자산은
    #:   누구 책임인가» 에 답할 수 없다. 그래서 승격 경로도 조직 자산에서만 출발한다.
    r0 = _create(client, AI_ADMIN, visibility=VIS_ENTERPRISE, owner_scope_id="LS_MNM")
    assert r0.status_code == 200, r0.text          # 전제가 깨지면 이유를 보여 준다
    a = r0.json()
    client.post(f"{B}/agents/{a['asset_id']}/submit", headers=H(AI_ADMIN))
    client.post(f"{B}/agents/{a['asset_id']}/approve", headers=H(AI_ADMIN))
    r = client.post(f"{B}/agents/{a['asset_id']}/promote", headers=H(AI_ADMIN))
    assert r.status_code == 403 and "이미 전사" in r.json()["detail"]


def test_promotion_of_invisible_asset_is_404(client):
    """★ 안 보이는 자산에 대한 승격 시도는 **404** 다 — 403 은 «그런 자산이 있다» 를 알려준다."""
    mine = _create(client, MEMBER, visibility=VIS_PERSONAL).json()["asset_id"]
    assert client.post(f"{B}/agents/{mine}/promote", headers=H(MGR)).status_code == 404


# ── 「누르기 전에 안다」 (설계 §8.6 · §10 UI) ────────────────────────────
#
# ★★★ 설계 §10 은 「API 403 을 **버튼 클릭 후 처음 알게 되는 경로가 없어야 한다**」고 못박았다.
# 화면이 그것을 지키려면 자산마다 «내가 이걸 할 수 있는가» 를 알아야 하는데, 화면이 그 규칙을
# 다시 구현하면 서버와 서서히 갈라진다. 그래서 **서버가 자산마다 답한다**(`blocked`).
#
# ⚠️ 2026-08-08 역할별 화면 감사에서 실제로 어긋난 상태를 발견했다: 부서원에게 남의 조직 자산의
#   «승인 요청» 이 **활성으로** 보였고, 누르면 403 이었다. 아래 테스트가 그 유형을 막는다.
def test_list_carries_a_reason_for_every_action(client):
    a = _approved(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM")
    row = next(i for i in client.get(f"{B}/agents?include_files=false",
                                     headers=H(MGR)).json()["items"]
               if i["asset_id"] == a["asset_id"])
    assert set(row["blocked"]) == {"update", "submit", "approve", "retire", "promote", "copy"}


def test_member_is_told_before_clicking_that_someone_elses_org_asset_is_off_limits(client):
    """★★★ 감사가 잡은 바로 그 결함. 부서원에게 남의 조직 자산은 **누르기 전에** 막혀야 한다."""
    a = _approved(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM")
    row = next(i for i in client.get(f"{B}/agents?include_files=false",
                                     headers=H(MEMBER)).json()["items"]
               if i["asset_id"] == a["asset_id"])
    assert row["blocked"]["submit"], "부서원에게 «승인 요청» 이 열려 보인다(누르면 403 이다)"
    #: 그리고 그 사유가 **사실**인지 확인한다 — 문구만 있고 서버가 허용하면 그것도 거짓말이다.
    assert client.post(f"{B}/agents/{a['asset_id']}/submit",
                       headers=H(MEMBER)).status_code == 403


@pytest.mark.parametrize("uid", [MGR, MEMBER, VIEWER, AI_ADMIN])
def test_the_reason_and_the_real_answer_agree(client, uid):
    """★★★ **화면이 본 사유와 서버의 실제 답이 일치해야 한다.**

    이 테스트가 없으면 두 방향으로 어긋날 수 있고 둘 다 나쁘다:
      · 사유는 비었는데 서버가 거부 → 「버튼은 보이는데 안 된다」(통제가 고장난 것으로 읽힌다)
      · 사유는 있는데 서버는 허용   → 할 수 있는 일을 못 하게 막는다(사용자는 권한을 요청한다)

    ⚠️ 행동마다 **새 자산**으로 검사한다. 한 자산에 이어서 하면 앞 행동이 상태를 바꿔
      뒤 행동의 사유가 달라지고, 그러면 무엇을 검사했는지 알 수 없게 된다."""
    def row_for(asset_id, who):
        items = client.get(f"{B}/agents?include_files=false", headers=H(who)).json()["items"]
        return next((i for i in items if i["asset_id"] == asset_id), None)

    for verb, path in (("approve", "approve"), ("retire", "retire"), ("promote", "promote")):
        a = _approved(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM")
        r = row_for(a["asset_id"], uid)
        if r is None:
            continue                       # 안 보이는 자산은 애초에 버튼도 없다
        reason = r["blocked"][verb]
        got = client.post(f"{B}/agents/{a['asset_id']}/{path}", headers=H(uid))
        if reason:
            assert got.status_code in (403, 404), (
                f"{uid} 의 {verb}: 사유(«{reason}»)가 있는데 서버는 {got.status_code} 로 허용했다")
        else:
            assert got.status_code == 200, (
                f"{uid} 의 {verb}: 사유가 없는데 서버는 {got.status_code} 로 거부했다 — "
                f"«{got.text}» 이것이 「누르고 나서야 아는 403」이다")


def test_copy_is_never_blocked_by_the_file_asset_rule(client):
    """★★ 「기본 제공은 복사해서 쓰십시오」라는 안내의 **도착지**가 막히면 안 된다.

    종전 화면은 모든 행동에 그 문구를 붙였고, 그래서 복사 버튼 자체에 「복사해서 쓰십시오」가
    사유로 달렸다 — 아무 데도 갈 수 없는 안내다."""
    row = next(i for i in client.get(f"{B}/agents", headers=H(MEMBER)).json()["items"]
               if i["asset_id"].startswith("file:"))
    assert row["blocked"]["copy"] == "", "복사가 막혀 있으면 규칙을 따를 방법이 없다"
    assert row["blocked"]["update"], "기본 제공 정의를 직접 고칠 수 있는 것으로 보인다"
    r = client.post(f"{B}/agents/{row['asset_id']}/copy",
                    json={"visibility": VIS_PERSONAL}, headers=H(MEMBER))
    assert r.status_code == 200, r.text


def test_viewer_is_blocked_on_everything_with_distinct_reasons(client):
    """★ 사유가 전부 같은 문장이면 사용자는 무엇이 다른지 모른다 — 행동마다 다른 답이어야 한다."""
    a = _approved(client, MGR, visibility=VIS_SCOPE, owner_scope_id="LS_MNM")
    row = next(i for i in client.get(f"{B}/agents?include_files=false",
                                     headers=H(VIEWER)).json()["items"]
               if i["asset_id"] == a["asset_id"])
    b = row["blocked"]
    assert all(b[k] for k in ("update", "submit", "approve", "retire", "promote", "copy"))
    assert len({b["approve"], b["copy"]}) == 2, "승인과 복사가 같은 이유로 막혀 있다"
