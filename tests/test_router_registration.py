"""★★★ 만든 라우터가 **앱에 붙어 있는가.**

## 왜 이 시험이 필요한가

[2026-08-19 실측] `api/routes/data_preparation_control.py` 의 10개 경로가 **`main.py`
에 등록된 적이 없었다.** BDR-2·3·5 를 세 Wave 에 걸쳐 만드는 동안 아무도 몰랐다 —
시험이 `FastAPI()` 를 새로 만들어 라우터를 직접 붙였기 때문에 전부 초록이었다.

⚠️⚠️ 화면을 만들었다면 전부 404 가 났을 것이다. 그리고 그 원인을 찾는 데 한참 걸렸을
  것이다 — 백엔드 시험은 초록이니까.

★ 이것은 이 저장소에서 **네 번째** 같은 유형이다(물질화기·후보 상태·진짜 코드 미태움·
  라우터 미등록). 「다음엔 잘 보겠다」로는 다섯 번째가 온다. 그래서 **표로 막는다.**
"""
import importlib
import pkgutil

import pytest

import api.routes
from main import app

#: 앱에 붙이지 **않는** 라우터. 이유를 함께 적는다 —
#: ⚠️ 이유 없는 면제는 「잊어버린 것」과 구별되지 않는다.
EXEMPT = {
    # (모듈명): 사유
}


def _router_modules():
    """`api/routes` 아래 `router` 를 들고 있는 모듈 전부."""
    out = []
    for info in pkgutil.iter_modules(api.routes.__path__):
        mod = importlib.import_module(f"api.routes.{info.name}")
        if hasattr(mod, "router"):
            out.append((info.name, mod))
    return out


def test_every_router_is_mounted():
    """★★★ 만든 라우터는 **앱에 붙어 있어야** 한다.

    ⚠️ 붙지 않은 라우터의 기능은 «시험에서만» 존재한다. 그 상태는 오류를 내지 않는다 —
      백엔드 시험이 자기 앱을 만들어 붙이기 때문이다."""
    mounted = {str(getattr(r, "path", "")) for r in app.routes}
    missing = []
    for name, mod in _router_modules():
        if name in EXEMPT:
            continue
        paths = {str(getattr(r, "path", "")) for r in mod.router.routes}
        if paths and not (paths & mounted):
            missing.append(f"{name} ({sorted(paths)[0]} 등 {len(paths)}개)")
    assert not missing, (
        "앱에 등록되지 않은 라우터가 있습니다 — `main.py` 에 "
        "`app.include_router(...)` 를 더하거나, 사유와 함께 이 파일의 `EXEMPT` 에 "
        "올리십시오:\n  " + "\n  ".join(sorted(missing)))


@pytest.mark.parametrize("prefix", [
    "/api/v1/data-preparation",     # BDR-2·3·5 업무 데이터 준비
    "/api/v1/baseline",             # BDR-7 / G2·G4 기준선·시뮬레이션
    "/api/v1/appdata/runtime",      # G1-B Host Runtime 데이터 평면
])
def test_the_pilot_paths_are_reachable(prefix):
    """★ 파일럿 동선이 지나는 경로들은 **실제 앱에서** 닿아야 한다.

    ⚠️ 위 시험이 「하나라도 붙었으면 통과」이므로, 시연에 필요한 접두어는 따로 못 박는다."""
    paths = [str(getattr(r, "path", "")) for r in app.routes]
    assert any(p.startswith(prefix) for p in paths), f"{prefix} 경로가 앱에 없다"
