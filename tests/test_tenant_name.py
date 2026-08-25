"""★★★ 회사(tenant)의 **사람이 읽는 이름**. (2026-08-25)

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
