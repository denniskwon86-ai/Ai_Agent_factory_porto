"""★★★ [MVP-P0 ①-A] 온톨로지 런타임의 **배선 계약**을 고정한다.

## 왜 이 파일이 생겼나 (2026-08-20 Supervisor 지적)

정식 G2 온톨로지 런타임을 이식하면서 두 가지를 어겼다.

★★★ ① **import 만으로 운영 폴더에 DB 를 만들었다.** 모듈 끝의 전역 인스턴스가
  `__init__` 에서 곧바로 `_init_db()` 를 불렀고, 전체 회귀를 한 번 돌리자
  `data/ontology.db`(73,728바이트)가 생겼다. 행은 0이었지만 **시험이 운영 데이터
  영역에 저장소를 만든 것**이고, 그것은 원장 오염과 같은 종류의 격리 결함이다.

★★★ ② **Resolver 없는 런타임의 라우터를 제품에 붙였다.** 그 파일 머리말이
  「Not mounted in main.py until a product Object Scope Resolver is wired」라고
  적어 두었는데 그대로 등록했다. 그 상태에서는 관계 제안·영향 질의가 503 으로 막히고,
  화면은 **고정 `ontology_path` 를 보여 주면서** 「정식 온톨로지가 돈다」는 오해를 만든다.

## 이 시험이 막는 것

⚠️ 시험 23건이 이것을 못 잡은 이유는 **가짜 Resolver 를 주입한 시험용 앱**을 보기
  때문이다 — 「올바른 Resolver 가 주어지면 동작한다」는 증명했지만 「제품에 올라간
  것이 회사·조직·승인 원장과 연결됐다」는 증명하지 않았다. 여기서 그 축을 본다.
"""
import os
import subprocess
import sys

import core.ontology_runtime as ontology_runtime


def test_모듈을_읽는_것만으로_저장소_파일을_만들지_않는다(tmp_path):
    """★★★ **여는 것은 만드는 것이 아니다.**

    ⚠️ 별도 프로세스에서 import 만 한다 — 같은 프로세스에서 하면 이미 만들어진
      상태를 보고 지나칠 수 있다."""
    probe = tmp_path / "probe.py"
    target = tmp_path / "data" / "ontology.db"
    probe.write_text(
        "import os, sys\n"
        f"sys.path.insert(0, {str(os.getcwd())!r})\n"
        "import core.paths as paths\n"
        f"paths.PROJECT_ROOT = {str(tmp_path)!r}\n"
        "import core.ontology_runtime as r\n"
        "rt = r.OntologyRuntime()\n"
        f"print('EXISTS', os.path.exists({str(target)!r}))\n",
        encoding="utf-8")
    out = subprocess.run([sys.executable, str(probe)], capture_output=True,
                         text=True, errors="replace", timeout=180)
    assert "EXISTS False" in out.stdout, (
        "import·생성만으로 저장소 파일이 생겼습니다:\n" + out.stdout + out.stderr)


def test_제품_전역_런타임은_기본_경로를_지연해_정한다():
    """⚠️ 기본 인자에 `data_path(...)` 를 쓰면 **모듈을 읽는 순간** 운영 경로가
    확정되고, 시험이 경로를 갈아끼울 자리가 사라진다."""
    import inspect

    src = inspect.getsource(ontology_runtime.OntologyRuntime.__init__)
    assert 'db_path: str = ""' in src, (
        "생성자 기본 인자가 여전히 경로를 계산합니다 — import 시점에 운영 경로가 굳습니다")


def test_경로를_바꾸면_새_경로에_스키마가_생긴다(tmp_path):
    """★ 지연 초기화가 «한 번 만들고 끝» 이면 시험 격리가 깨진다."""
    rt = ontology_runtime.OntologyRuntime(str(tmp_path / "a.db"))
    rt.model_status()                       # 첫 사용 — 여기서 만들어진다
    assert os.path.exists(tmp_path / "a.db")
    rt.db_path = str(tmp_path / "b.db")
    rt.model_status()
    assert os.path.exists(tmp_path / "b.db"), "경로를 바꿨는데 새 저장소가 준비되지 않았다"


def test_Resolver_가_없으면_제품에_붙이지_않는다():
    """★★★ **주석과 배선이 어긋나지 않게 한다.**

    제품 전역 런타임에 `object_scope_resolver` 와 `approval_resolver` 가 **둘 다**
    있을 때만 `main.py` 가 라우터를 등록할 수 있다.

    ⚠️ 이 규칙이 없으면 「정식 온톨로지가 돈다」고 오해하는 화면이 다시 생긴다 —
      실제로는 503 이거나, 조용히 고정 경로를 보여 준다."""
    with open("main.py", encoding="utf-8") as f:
        main_src = f.read()
    #: 주석이 아닌 **실제 등록**만 센다.
    registered = any(
        line.strip().startswith("app.include_router(ontology_control.router)")
        for line in main_src.splitlines())

    rt = ontology_runtime.ontology_runtime
    wired = bool(rt.object_scope_resolver) and bool(rt.approval_resolver)

    assert registered == wired, (
        "온톨로지 라우터 등록 여부와 Resolver 배선 여부가 어긋납니다.\n"
        f"  main.py 등록={registered} · 제품 런타임 Resolver 배선={wired}\n"
        "  · Resolver 없이 등록하면 관계 제안·영향 질의가 503 이고, 화면은 고정 "
        "`ontology_path` 를 보여 주면서 「정식 온톨로지가 돈다」는 오해를 만듭니다.\n"
        "  · Resolver 를 붙였으면 등록도 함께 켜십시오 — 만들어 놓고 안 붙이면 "
        "그 기능은 «시험에서만» 존재합니다.")


def test_모듈을_두_번_읽어도_운영_저장소를_만들지_않는다(tmp_path):
    """⚠️ 모듈 재읽기가 운영 파일을 만들면 위 ①이 되돌아온다.

    ★★★ **`importlib.reload` 를 이 프로세스에서 쓰지 않는다.** 그렇게 하면 이 파일이
      막으려는 바로 그 일(격리 깨짐)을 내가 저지른다 — 재읽기가 클래스 객체를 갈아
      끼워서, 같은 회귀 안의 **다른 시험 6건이 무너졌다**(2026-08-20 실측).
      그래서 별도 프로세스에서 두 번 읽는다."""
    probe = tmp_path / "twice.py"
    target = tmp_path / "data" / "ontology.db"
    probe.write_text(
        "import importlib, os, sys\n"
        f"sys.path.insert(0, {str(os.getcwd())!r})\n"
        "import core.paths as paths\n"
        f"paths.PROJECT_ROOT = {str(tmp_path)!r}\n"
        "import core.ontology_runtime as r\n"
        "importlib.reload(r)\n"
        f"print('EXISTS', os.path.exists({str(target)!r}))\n",
        encoding="utf-8")
    out = subprocess.run([sys.executable, str(probe)], capture_output=True,
                         text=True, errors="replace", timeout=180)
    assert "EXISTS False" in out.stdout, (
        "모듈을 다시 읽자 운영 저장소 파일이 생겼습니다:\n" + out.stdout + out.stderr)
