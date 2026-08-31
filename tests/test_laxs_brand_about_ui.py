"""확정 LAXS B안과 시스템 안내 페이지의 제품 배선을 고정한다.

이미지의 미세한 색상은 시각 검토 대상이지만, 승인한 파일이 다른 시안으로 조용히 바뀌거나
안내 페이지가 제품에서 도달 불가능해지는 것은 구조 회귀로 즉시 잡는다.
"""
from hashlib import sha256
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "frontend/public/brand/laxs-logo-primary-on-navy-v2.png"
INVERSE = ROOT / "frontend/public/brand/laxs-logo-primary-on-white-v5.png"
APPROVED_B_SHA256 = "6ffc8ad1004272cbcc09ac144d8f105bbdba2879d8987971e6f84f2dde1f63b8"
INVERSE_SHA256 = "c867c197f94a0fbce5a3d3d00e2b2f46cfcc06277c79442e32e852c66ed11514"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_확정_B안_원본이_프로젝트_자산으로_고정됐다():
    assert BRAND.is_file()
    assert sha256(BRAND.read_bytes()).hexdigest() == APPROVED_B_SHA256


def test_로그인은_밝은배경형_제품셸은_어두운배경형을_쓴다():
    login = _read("frontend/src/components/LoginPage.tsx")
    shell = _read("frontend/src/components/ProductShell.tsx")
    dark = "/brand/laxs-logo-primary-on-navy-v2.png"
    light = "/brand/laxs-logo-primary-on-white-v5.png"

    assert light in login and dark not in login
    assert dark in shell and light not in shell
    assert "PRODUCT_NAME_KO" not in login
    assert "laxs-mark-64.png" not in shell


def test_밝은배경_반전형도_고정되고_안내페이지에_두_버전이_있다():
    assert INVERSE.is_file()
    assert sha256(INVERSE.read_bytes()).hexdigest() == INVERSE_SHA256
    page = _read("frontend/src/components/SystemAboutPage.tsx")
    assert "/brand/laxs-logo-primary-on-navy-v2.png" in page
    assert "/brand/laxs-logo-primary-on-white-v5.png" in page
    assert "어두운 배경 기본형" in page
    assert "밝은 배경 반전형" in page


def test_시스템_안내는_제품에서_열리고_경영홈으로_돌아갈_수_있다():
    shell = _read("frontend/src/components/ProductShell.tsx")
    app = _read("frontend/src/App.tsx")

    assert 'aria-label="LAXS 시스템 안내"' in shell
    assert "onAbout={() => setSpace('about')}" in app
    assert "space === 'about'" in app
    assert "onBack={() => setSpace('enterprise')}" in app
    assert "onCompanySetup={() => setShowCompany(true)}" in app


def test_안내페이지가_명칭_발음_지향점과_운영원칙을_설명한다():
    page = _read("frontend/src/components/SystemAboutPage.tsx")

    assert "AX embedded in LS" in page
    assert "AX at the core of LS" in page
    assert "LS의 일과 경영에 AX를 내재화하다" in page
    assert "현업의 실행과 경영의 판단을 AX로 연결하다" in page
    assert "PRODUCT_NAME_KO" in page
    assert "LAXS-M" not in page, "적용본 이름은 brand.ts 단일 정본에서 읽어야 한다"
    assert "자비스 · AI 경영비서" in page
    assert "이중 입력이 아닌 Native-first" in page
    assert "실적·가정·합성자료를 혼동하지 않음" in page
