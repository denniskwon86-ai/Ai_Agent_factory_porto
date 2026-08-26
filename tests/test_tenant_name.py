"""★★★ 회사(tenant) 이름 · **프로필 승인**. (2026-08-25)

## 이 파일이 지키는 것

    ① 이름이 **저장소에 산다** — 클라이언트가 식별자에서 만들어 내지 않는다
    ② 빈 이름을 저장하지 않는다 — 저장되면 화면이 조용히 식별자로 되돌아간다
    ③ 없는 회사는 `None`·404 다 — **이름을 지어내지 않는다**
    ④ 이름을 세우는 것은 **조직 기준정보를 고치는 일**이다(권한 표에 있다)

⚠️⚠️ 종전에는 `tenant_id` 밖에 없었다. 그래서 상단 문맥이
  `tenant-afs-demo-materials` 라는 기계 식별자를 사람에게 그대로 보여 줬다 —
  승인 시안의 그 자리는 「LS MnM」이다.
"""
import pytest

from core.enterprise_context.models import EcmError


@pytest.fixture()
def repo(tmp_path):
    """⚠️ 격리 저장소에만 쓴다 — 운영 ECM 에 시험 회사가 들어가면 안 된다."""
    from core.enterprise_context.repository import EcmRepository

    return EcmRepository(db_path=str(tmp_path / "ecm.db"))


# ── ① 저장소가 갖는다 ────────────────────────────────────────────────────

def test_이름을_세우고_다시_읽는다(repo):
    got = repo.upsert_tenant("tenant-afs-demo-materials", "LS MnM",
                             legal_name="LS엠엔엠 주식회사")
    assert got["name_ko"] == "LS MnM"
    assert got["legal_name"] == "LS엠엔엠 주식회사"
    assert repo.get_tenant("tenant-afs-demo-materials")["name_ko"] == "LS MnM"


def test_같은_회사를_다시_세우면_덮는다(repo):
    """★ 멱등이다 — 시연 스크립트가 뜰 때마다 부른다."""
    repo.upsert_tenant("t1", "옛 이름")
    repo.upsert_tenant("t1", "새 이름")
    assert repo.get_tenant("t1")["name_ko"] == "새 이름"
    assert len(repo.list_tenants()) == 1, "덮지 않고 늘었다"


# ── ② 빈 이름 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["", "   "])
def test_빈_이름은_저장하지_않는다(repo, bad):
    """⚠️ 저장되면 화면이 「이름이 있다」고 판단하고 빈 칸을 그린다 — 그때 사용자는
    회사가 사라진 것으로 읽는다. 식별자로 되돌아가는 편이 낫다."""
    with pytest.raises(EcmError) as err:
        repo.upsert_tenant("t1", bad)
    assert "이름이 필요합니다" in str(err.value)
    assert repo.get_tenant("t1") is None


def test_tenant_id_가_없으면_거부한다(repo):
    with pytest.raises(EcmError):
        repo.upsert_tenant("", "이름")


# ── ③ 없는 회사 ──────────────────────────────────────────────────────────

def test_없는_회사는_None_이다(repo):
    """★★★ **이름을 지어내지 않는다.** 화면은 그때 식별자를 그대로 쓴다 —
    「LS…」처럼 잘라 만들면 회사 이름이 코드가 되고, 바꾸려면 배포를 해야 한다."""
    assert repo.get_tenant("nope") is None
    assert repo.list_tenants() == []


# ── ④ 권한 ───────────────────────────────────────────────────────────────

def test_이름을_세우는_것은_조직_권한이다():
    """★ 표가 지킨다 — 라우트마다 적으면 새 라우트가 생길 때 아무도 알려 주지 않는다."""
    from core.admin_capability import ADMIN_ORGANIZATION
    from core.route_authority import ROUTE_CAPS

    assert ROUTE_CAPS.get("POST /api/v1/enterprise-context/tenants") \
        == (ADMIN_ORGANIZATION,)


def test_읽기_라우트는_표에_없다():
    """⚠️ 표는 **쓰기 전용**이다(라우터 머리말). 읽기를 넣으면 표의 뜻이 흐려진다 —
    핸들러가 `assert_identified` 로 직접 요구한다."""
    from core.route_authority import ROUTE_CAPS

    assert "GET /api/v1/enterprise-context/tenants" not in ROUTE_CAPS


# ── 라우트가 실제로 서 있는가 ────────────────────────────────────────────

def test_세_경로가_등록돼_있다():
    """⚠️ 「통제는 있는데 부르는 경로가 없다」를 다시 만들지 않는다."""
    from api.routes import enterprise_context_control as ecc

    paths = {(sorted(r.methods)[0], r.path) for r in ecc.router.routes
             if "tenant" in r.path}
    assert ("GET", "/api/v1/enterprise-context/tenants") in paths
    assert ("GET", "/api/v1/enterprise-context/tenants/{tenant_id}") in paths
    assert ("POST", "/api/v1/enterprise-context/tenants") in paths


# ══════════════════════════════════════════════════════════════════════════
# 프로필 승인 — 「통제는 있는데 부르는 경로가 없다」의 또 한 자리
# ══════════════════════════════════════════════════════════════════════════

def _seeded(repo):
    """프로필을 붙일 수 있는 최소 구성 — 법인 하나 + 노드 하나."""
    from core.enterprise_context.models import (EnterpriseEntity, EnterpriseProfile,
                                                OrganizationNode)

    e = repo.upsert_entity(EnterpriseEntity(tenant_id="t1", name_ko="LS MnM"))
    n = repo.upsert_node(OrganizationNode(
        tenant_id="t1", entity_id=e.entity_id, node_type="business_division",
        name_ko="제련"))
    pr = repo.upsert_profile(EnterpriseProfile(
        tenant_id="t1", scope_node_id=n.node_id, profile_kind="process_profile",
        payload={"nodes": [{"key": "order", "label": "수주·판매"}]}))
    return pr


def test_저장만_하면_상속에_참여하지_못한다(repo):
    """★★★ **이것이 이 통제의 요지다.**

    `is_effective` 는 `status == ACTIVE` **와** `approved_at` 을 함께 요구한다.
    ⚠️ 그런데 `ProfileIn` 은 `approved_at` 을 받지 않는다 — status 만 ACTIVE 로 보내도
      계속 False 다. 즉 **승인 경로 없이는 프로필이 영원히 안 먹었다.**"""
    pr = _seeded(repo)
    assert pr.status == "DRAFT"
    assert pr.is_effective is False


def test_승인하면_상속에_참여한다(repo):
    """★ 대조군 — 늘 막히기만 하면 그것은 기능이 아니다."""
    pr = _seeded(repo)
    got = repo.approve_profile(pr.profile_id, "approver@afs.invalid")
    assert got.status == "ACTIVE"
    assert got.approved_by == "approver@afs.invalid"
    assert got.approved_at, "승인 시각이 비었다 — is_effective 가 계속 False 다"
    assert got.is_effective is True


def test_없는_프로필은_None_이다(repo):
    """⚠️ 「찾지 못했다」를 «승인됐다» 로 읽지 않는다 — 라우트가 404 로 답한다."""
    assert repo.approve_profile("nope", "x") is None


def test_승인이_저장된_내용을_바꾸지_않는다(repo):
    """⚠️ 승인은 **상태를 올리는 일**이다. 내용까지 손대면 「승인한 것」과 「지금 있는 것」이
    갈리고, 그 갈림은 조용하다."""
    pr = _seeded(repo)
    got = repo.approve_profile(pr.profile_id, "a@afs.invalid")
    assert got.payload == {"nodes": [{"key": "order", "label": "수주·판매"}]}
    assert got.profile_id == pr.profile_id


def test_업무단계_보조정보는_같은_승인_프로필에_보존된다(repo):
    """카드가 화면 상수나 별도 저장소에 살면 회사 연결구성과 판이 갈린다."""
    from core.enterprise_context.models import EnterpriseProfile

    payload = {"nodes": [{
        "key": "sales", "label": "수주·판매", "note": "판매 업무",
        "overlay": {"layer": "DATA", "kicker": "DATA CONTRACT",
                    "body": "판매계획 인증판"},
    }]}
    pr = repo.upsert_profile(EnterpriseProfile(
        tenant_id="t1", profile_kind="process_profile", payload=payload))
    approved = repo.approve_profile(pr.profile_id, "approver@afs.invalid", tenant_id="t1")

    assert approved.payload == payload
    assert approved.payload["nodes"][0]["overlay"]["layer"] == "DATA"


def test_프로필_승인은_조직_권한이다():
    from core.admin_capability import ADMIN_ORGANIZATION
    from core.route_authority import ROUTE_CAPS

    assert ROUTE_CAPS.get(
        "POST /api/v1/enterprise-context/profiles/{profile_id}/approve")         == (ADMIN_ORGANIZATION,)


def test_승인_경로가_등록돼_있다():
    from api.routes import enterprise_context_control as ecc

    paths = {(sorted(r.methods)[0], r.path) for r in ecc.router.routes}
    assert ("POST",
            "/api/v1/enterprise-context/profiles/{profile_id}/approve") in paths


# ══════════════════════════════════════════════════════════════════════════
# 회사 전체 연결구성 — 현재 회사와 실제 구성을 한 저장 경계로 묶는다
# ══════════════════════════════════════════════════════════════════════════

def test_회사_전체_process_profile은_tenant를_범위로_저장한다(repo):
    from core.enterprise_context.models import EnterpriseProfile

    pr = repo.upsert_profile(EnterpriseProfile(
        tenant_id="t1", profile_kind="process_profile",
        payload={"nodes": [{"key": "sales", "label": "수주·판매"}]}))
    assert pr.scope_node_id == "" and pr.industry_code == ""
    got = repo.list_profiles(profile_kind="process_profile", tenant_id="t1",
                             company_wide=True)
    assert [x.profile_id for x in got] == [pr.profile_id]


def test_범위_없는_다른_프로필은_회사_전체로_번지지_않는다(repo):
    from core.enterprise_context.models import EnterpriseProfile

    with pytest.raises(EcmError):
        repo.upsert_profile(EnterpriseProfile(
            tenant_id="t1", profile_kind="data_profile", payload={"secret": True}))


def test_프로필_목록은_현재_회사만_돌려준다(repo):
    from core.enterprise_context.models import EnterpriseProfile

    a = repo.upsert_profile(EnterpriseProfile(
        tenant_id="t1", profile_kind="process_profile", payload={"nodes": []}))
    repo.upsert_profile(EnterpriseProfile(
        tenant_id="t2", profile_kind="process_profile", payload={"nodes": []}))
    got = repo.list_profiles(profile_kind="process_profile", tenant_id="t1",
                             company_wide=True)
    assert [x.profile_id for x in got] == [a.profile_id]


def test_다른_회사의_프로필은_승인할_수_없다(repo):
    from core.enterprise_context.models import EnterpriseProfile

    pr = repo.upsert_profile(EnterpriseProfile(
        tenant_id="t2", profile_kind="process_profile", payload={"nodes": []}))
    assert repo.approve_profile(pr.profile_id, "admin@afs.invalid", tenant_id="t1") is None
    assert repo.list_profiles(profile_kind="process_profile", tenant_id="t2",
                              company_wide=True)[0].status == "DRAFT"


def test_새_승인판은_이전_승인판을_보존하되_적용에서는_내린다(repo):
    from core.enterprise_context.models import EnterpriseProfile

    old = repo.upsert_profile(EnterpriseProfile(
        tenant_id="t1", profile_kind="process_profile", version=1,
        payload={"nodes": [{"key": "old", "label": "이전"}]}))
    repo.approve_profile(old.profile_id, "a@afs.invalid", tenant_id="t1")
    new = repo.upsert_profile(EnterpriseProfile(
        tenant_id="t1", profile_kind="process_profile", version=2,
        payload={"nodes": [{"key": "new", "label": "신규"}]}))
    repo.approve_profile(new.profile_id, "b@afs.invalid", tenant_id="t1")

    rows = repo.list_profiles(profile_kind="process_profile", tenant_id="t1",
                              company_wide=True)
    effective = [x for x in rows if x.is_effective]
    archived = [x for x in rows if x.status == "ARCHIVED"]
    assert [x.profile_id for x in effective] == [new.profile_id]
    assert [x.profile_id for x in archived] == [old.profile_id]


def test_조직별_프로필은_현재_회사의_노드에만_붙는다(repo):
    from core.enterprise_context.models import (EnterpriseEntity, EnterpriseProfile,
                                                OrganizationNode)

    e = repo.upsert_entity(EnterpriseEntity(tenant_id="t2", name_ko="다른 회사"))
    n = repo.upsert_node(OrganizationNode(
        tenant_id="t2", entity_id=e.entity_id, node_type="legal_entity", name_ko="다른 회사"))
    with pytest.raises(EcmError):
        repo.upsert_profile(EnterpriseProfile(
            tenant_id="t1", scope_node_id=n.node_id, profile_kind="process_profile",
            payload={"nodes": []}))
