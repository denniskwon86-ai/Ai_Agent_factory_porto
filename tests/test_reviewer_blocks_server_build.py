"""★★★ 앱이 **자기 서버를 만들면 빌드 중에 막힌다.** (2026-08-27 실측 — 두 번째)

## ⚠️⚠️ 같은 사고가 두 번 났다

`core/app_runtime_brief.py` 의 머리말이 이 사고로 시작한다 — `live-walk-02` 에서
Architect 가 Spring Boot 로 설계했고 공장이 `InboundApplication.java` 를 만들었다.
그래서 고지문을 썼다. 그런데 `CRM002` 에서 **또 났다**, 이번에는 FastAPI 로:

    main.py                 app = FastAPI(title="CRM Backend Simulator")
    backend/routers.py      router = APIRouter()  /  from sqlalchemy.orm import Session
    backend/database.py     from sqlalchemy import create_engine

계약이 금지하는 셋에 정면으로 걸린다 — `server.custom_logic`(호스트 기능 필요) ·
`api.direct_call`(금지) · `storage.local_db`(금지). 그런데 **차단 신호 0건**이었다:
인증 검사기는 «인증» 만 보지 «서버를 만들었나» 는 보지 않는다.

★ 고지문은 설득이고 이 게이트는 차단이다. 안 들으면 아무 일도 일어나지 않는다 —
  두 번 다 안 들었다([[notice-is-not-a-blocker]]).

## ⚠️ 왜 파일 이름으로 잡지 않는가

`backend/` 라는 이름으로 잡으면 이름을 바꾸는 순간 우회로가 된다. **호출 형태**로 잡는다.
"""
import inspect

import pytest

from nodes.utils.server_build_checker import check_server_build, scan_text

#: 실제 가동이 만든 코드에서 **그대로** 가져온 줄들. 바꾸지 않는다.
_REAL_MAIN = (
    "from fastapi import FastAPI\n"
    "from backend.routers import router\n"
    "app = FastAPI(title=\"CRM Backend Simulator\")\n"
    "app.include_router(router)\n")
_REAL_ROUTER = (
    "from fastapi import APIRouter, Depends\n"
    "from sqlalchemy.orm import Session\n"
    "router = APIRouter()\n"
    "@router.post(\"/customers\")\n"
    "def create_customer_endpoint(customer, db: Session = Depends(get_db)):\n"
    "    return service.create_customer(customer)\n")
_REAL_DB = (
    "from sqlalchemy import create_engine\n"
    "engine = create_engine(SQLALCHEMY_DATABASE_URL)\n"
    "SessionLocal = sessionmaker(bind=engine)\n")


def _blocks(code: str, path: str = "main.py"):
    return scan_text(code, path=path)


# ── 잡아야 하는 것 ───────────────────────────────────────────────────────

def test_실제로_생성된_FastAPI_서버를_잡는다():
    """★★★ **이 파일의 요지.** 제품이 실제로 만든 것을 잡아야 게이트다."""
    sigs = {h["signal"] for h in _blocks(_REAL_MAIN)}
    assert "server_framework" in sigs, sigs


def test_실제로_생성된_라우터와_ORM_을_잡는다():
    sigs = {h["signal"] for h in _blocks(_REAL_ROUTER, "backend/routers.py")}
    assert "server_framework" in sigs and "orm_or_local_db" in sigs, sigs


def test_자체_DB_연결을_잡는다():
    sigs = {h["signal"] for h in _blocks(_REAL_DB, "backend/database.py")}
    assert "orm_or_local_db" in sigs, sigs


@pytest.mark.parametrize("code,sig", [
    ("uvicorn.run(app, host='0.0.0.0')", "server_entrypoint"),
    ("app.listen(3000)", "server_entrypoint"),
    ("const app = express()", "server_framework"),
    ("conn = sqlite3.connect('app.db')", "orm_or_local_db"),
])
def test_다른_스택도_잡는다(code, sig):
    """⚠️ 파이썬만 잡으면 Node 로 옮겨 적는 순간 우회로가 된다."""
    assert sig in {h["signal"] for h in _blocks(code, "server.js")}, code


# ── ⚠️ 잡으면 안 되는 것 — 오탐이 나면 개발자가 검사를 끈다 ─────────────

def test_정상_업무_화면은_걸리지_않는다():
    """★★★ 대조군. 오탐이 나면 이 게이트는 꺼지고, 꺼진 게이트는 없는 것과 같다."""
    ok = (
        "import { list, create } from './generated/afs-contract';\n"
        "const [rows, setRows] = useState([]);\n"
        "useEffect(() => { list('customers').then(setRows)\n"
        "  .catch(() => setError('데이터를 불러오지 못했습니다')); }, []);\n"
        "const onSubmit = (v) => create('customers', v).then(() => list('customers'));\n"
        "return <table>{rows.map(r => <tr key={r.id}><td>{r.name}</td></tr>)}</table>;\n")
    assert _blocks(ok, "src/App.tsx") == [], _blocks(ok, "src/App.tsx")


def test_생성된_어댑터는_걸리지_않는다():
    """⚠️ 어댑터는 `window.afs.data.*` 를 부르는 것이 일이다 — 막으면 아무도 못 쓴다."""
    adapter = (
        "export async function list(dataset: string, page?: number) {\n"
        "  return window.afs.data.list(dataset, page);\n"
        "}\n"
        "export async function create(dataset: string, payload: unknown) {\n"
        "  return window.afs.data.create(dataset, payload);\n"
        "}\n")
    assert _blocks(adapter, "src/generated/afs-contract.ts") == []


def test_빈_목록은_통과가_아니라_건너뜀이다():
    """★★★ 「볼 것이 없었다」와 「봤는데 깨끗했다」는 다르다."""
    out = check_server_build([])
    assert out["skipped"] is True and out["scanned"] == 0


# ── 게이트가 실제로 걸려 있는가 ─────────────────────────────────────────

def test_리뷰어가_빌드_중에_이_검사를_부른다():
    """⚠️⚠️ 결함의 본체는 정규식이 아니라 **부르는 곳이 없었다**는 것이다."""
    import nodes.execution as ex

    src = inspect.getsource(ex.run_reviewer)
    assert "server_build_checker" in src, (
        "리뷰어가 자체 서버 검사를 부르지 않는다 — 검사기가 있어도 소용없다")


def test_차단이면_재작업으로_돌려보낸다():
    import nodes.execution as ex

    #: ⚠️ [2026-08-28] 종전에는 `run_reviewer` 소스에서 게이트 이름 주변 N자 안에
    #:   "REWORK_DEV" 가 있는지 **문자열로** 찾았다. 판정을 공통 반환부
    #:   (`_deterministic_rework`)로 모으자 그 문자열이 사라져 시험이 깨졌다 —
    #:   기전은 그대로인데 시험만 깨진 것이다. 그래서 **행동으로** 확인한다.
    src = inspect.getsource(ex.run_reviewer)
    i = src.index("app_builds_server")
    assert "_deterministic_rework" in src[max(0, i - 1200):i + 400], (
        "차단 신호를 재작업 반환부로 보내지 않는다")

    class _S:
        rework_history = ()

    d, _t, _h = ex._rework_ladder(_S(), "앱이 자기 서버를 만들었습니다", hops=1,
                                  deterministic=True)
    assert d == "REWORK_DEV", "차단 신호가 개발자에게 돌아가지 않는다"


def test_레거시_프로젝트에는_소급하지_않는다():
    """★★★ 계약 프로필이 꺼진 프로젝트는 자유 형식 앱을 만들어 왔다.

    ⚠️ 소급하면 이미 도는 것들이 전부 깨진다 — 이 저장소의 다른 경계와 같은 규칙."""
    import nodes.execution as ex

    src = inspect.getsource(ex.run_reviewer)
    i = src.index("server_build_checker")
    assert "profile_enforces_contract" in src[max(0, i - 900):i], (
        "계약 프로필 검사 없이 서버 차단기를 돌린다 — 레거시 앱이 깨진다")
