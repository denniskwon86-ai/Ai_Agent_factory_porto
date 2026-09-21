"""키트 디렉터리를 **설정으로 받는가** — 코드 배포에서 떼어내기 위한 자리.

이 시험이 지키는 것: `deploy/update.sh` 는 `/opt/afs/app` 을 `git pull` 로 갈아
끼우고 `/opt/afs/data` 는 남긴다. 그런데 키트는 **app 쪽**에 있어 코드 릴리스에
묶여 있었다 — 산업이 늘면 **모든 고객 서버가 그 짐을 함께 받고**, 제련만 쓰는 곳도
전선·화학 키트를 받는다(키트 하나 35 MB · 20 개면 700 MB).

경로를 환경변수로 받아 두면 **지금은 아무것도 달라지지 않고**(기본값이 같다),
나중에 옮기거나 배급 시스템을 붙일 때 설정 한 줄이면 된다.
"""
import os

from core.data_preparation import kit_registry as kr
from core.paths import PROJECT_ROOT


# ── 기본값 — 지금과 같아야 한다

def test_환경변수가_없으면_지금과_같다(monkeypatch):
    """★ 이 변경이 **아무것도 바꾸지 않는다**는 증거."""
    monkeypatch.delenv(kr.KITS_DIR_ENV, raising=False)
    monkeypatch.delenv(kr.STARTER_KITS_DIR_ENV, raising=False)
    assert kr.kits_dir() == os.path.join(PROJECT_ROOT, kr.KITS_DIRNAME)
    assert kr.starter_packages_dir() == os.path.join(PROJECT_ROOT, kr.STARTER_PACKAGES_DIRNAME)


def test_기본_자리에_정말_키트가_있다(monkeypatch):
    """경로만 맞고 내용이 없으면 소용없다."""
    monkeypatch.delenv(kr.KITS_DIR_ENV, raising=False)
    monkeypatch.delenv(kr.STARTER_KITS_DIR_ENV, raising=False)
    assert os.path.isdir(kr.kits_dir())
    assert any(n.endswith(".kit.json") for n in os.listdir(kr.kits_dir()))
    assert os.path.isdir(os.path.join(kr.starter_packages_dir(),
                                      "KIT-MFG-NONFERROUS-PROCUREMENT"))


# ── 환경변수

def test_절대경로_환경변수가_자리를_바꾼다(monkeypatch, tmp_path):
    monkeypatch.setenv(kr.KITS_DIR_ENV, str(tmp_path / "kits"))
    monkeypatch.setenv(kr.STARTER_KITS_DIR_ENV, str(tmp_path / "packages"))
    assert kr.kits_dir() == str(tmp_path / "kits")
    assert kr.starter_packages_dir() == str(tmp_path / "packages")


def test_상대경로는_저장소_기준으로_읽는다(monkeypatch):
    """★ **cwd 기준으로 두면 조용히 어긋난다.**

    서비스(systemd)로 돌 때와 손으로 돌릴 때 cwd 가 다르다. 그러면 같은 설정인데
    한쪽에서만 「키트가 없다」가 나오고, 그 이유를 화면은 말해 주지 못한다.
    """
    monkeypatch.setenv(kr.KITS_DIR_ENV, "var/kits")
    assert kr.kits_dir() == os.path.join(PROJECT_ROOT, "var/kits")


def test_빈_값은_설정하지_않은_것으로_본다(monkeypatch):
    """`AFS_KITS_DIR=` 처럼 빈 값을 넘기는 배포 스크립트가 있다."""
    monkeypatch.setenv(kr.KITS_DIR_ENV, "   ")
    assert kr.kits_dir() == os.path.join(PROJECT_ROOT, kr.KITS_DIRNAME)


# ── 읽는 쪽이 모두 그 자리를 따르는가

def test_카탈로그가_그_자리를_본다(monkeypatch, tmp_path):
    """예전에는 `starter_package_catalog()` 가 `PROJECT_ROOT` 로 직접 조립했다."""
    monkeypatch.setenv(kr.STARTER_KITS_DIR_ENV, str(tmp_path / "없는곳"))
    assert kr.starter_package_catalog() == []          # 조용히 빈 목록 — 예외가 아니다


def test_시연_수직경로도_같은_자리를_쓴다(monkeypatch, tmp_path):
    """★ `demo_vertical_slice.kit_root()` 는 **파일 위치에서 직접 조립**했다.
    한 곳만 고치면 키트를 옮겼을 때 둘이 다른 곳을 본다."""
    from core import demo_vertical_slice as dv
    monkeypatch.setenv(kr.STARTER_KITS_DIR_ENV, str(tmp_path / "packages"))
    assert dv.kit_root().startswith(str(tmp_path / "packages"))
    assert dv.kit_root().endswith(os.path.join(dv.KIT_ID, dv.KIT_VERSION))
