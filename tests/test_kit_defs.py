"""[P2] 판본별 정의 — 생성기 하나로 여러 판본을 만들 수 있는가.

이 시험이 지키는 것: **1.0.0 의 재현성.** 생성기에 `KIT_VERSION` 이 박혀 있어
판본을 늘리려면 그 줄을 고쳐야 했고, 고치는 순간 1.0.0 을 다시 만들 수 없었다.
"""
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import kit_defs  # noqa: E402


def _overlay(**kw):
    o = kit_defs.KitOverlay()
    for k, v in kw.items():
        setattr(o, k, v)
    return o


# ── 판본 로더

def test_1_0_0_을_불러온다():
    o = kit_defs.load("1.0.0")
    assert o.version == "1.0.0"
    assert o.kit_id == "KIT-MFG-NONFERROUS-PROCUREMENT"


def test_없는_판본은_거부한다():
    """오타로 새 판본이 생기면 알아차리는 데 오래 걸린다."""
    with pytest.raises(SystemExit) as e:
        kit_defs.load("9.9.9")
    assert "v9_9_9.py" in str(e.value)


def test_판본_불일치를_잡는다(monkeypatch):
    """복사해서 만들 때 version 을 안 고치는 실수를 막는다 — **로더가** 잡아야 한다."""
    class Fake:
        OVERLAY = _overlay(version="1.0.0")      # 파일은 v2_0_0.py 인데 안이 1.0.0

    monkeypatch.setattr(kit_defs.importlib, "import_module", lambda name: Fake)
    with pytest.raises(SystemExit) as e:
        kit_defs.load("2.0.0")
    assert "판본 불일치" in str(e.value)


def test_OVERLAY_가_없는_정의를_거부한다(monkeypatch):
    class Fake:
        pass

    monkeypatch.setattr(kit_defs.importlib, "import_module", lambda name: Fake)
    with pytest.raises(SystemExit) as e:
        kit_defs.load("2.0.0")
    assert "OVERLAY" in str(e.value)


# ── 1.0.0 오버레이는 비어 있어야 한다

def test_1_0_0_오버레이는_비어있다():
    """★ 이것이 「생성기의 기본 정의 = 1.0.0」을 보증한다. 여기에 무엇을 더하면
    동결된 1.0.0 이 재생성 시 달라진다."""
    o = kit_defs.load("1.0.0")
    assert list(o.extra_drivers) == []
    assert list(o.extra_scenarios) == []
    assert o.company_profile_patches == {}
    assert o.manifest_patches == {}


def test_빈_오버레이는_기본을_그대로_돌려준다():
    o = kit_defs.load("1.0.0")
    base_d = [("DRV-FX", "a", "b", "c", 0, "KRW")]
    base_s = [("SCN-01", "n", "DRV-FX", 0.1, "%", "X")]
    base_p = [{"company_profile_id": "P1", "industry_code": "C2412"}]
    base_m = {"industry_codes": ["C24"]}
    assert o.apply_drivers(base_d) == base_d
    assert o.apply_scenarios(base_s) == base_s
    assert o.apply_company_profiles(base_p) == base_p
    assert o.apply_manifest(base_m) == base_m


# ── 오버레이가 실제로 얹히는가

def test_드라이버는_뒤에_붙는다():
    """앞에 끼우면 기존 판본의 행 순서가 바뀌어 지문이 달라진다."""
    base = [("DRV-FX", "a", "b", "c", 0, "KRW")]
    extra = ("DRV-TCRC", "TC", "REV", "f", 0, "USD")
    got = _overlay(extra_drivers=(extra,)).apply_drivers(base)
    assert got == base + [extra]


def test_회사프로파일은_키만_덮는다():
    base = [{"company_profile_id": "P1", "industry_code": "C2412", "name": "그대로"},
            {"company_profile_id": "P2", "industry_code": "C9999"}]
    got = _overlay(company_profile_patches={"P1": {"industry_code": "C2421"}}
                   ).apply_company_profiles(base)
    assert got[0]["industry_code"] == "C2421"
    assert got[0]["name"] == "그대로", "패치하지 않은 키는 남아야 한다"
    assert got[1]["industry_code"] == "C9999", "다른 프로파일은 건드리지 않는다"


def test_원본_리스트를_바꾸지_않는다():
    """오버레이가 기본 정의를 제자리에서 고치면, 같은 프로세스에서 두 판본을
    잇달아 만들 때 두 번째가 오염된다."""
    base = [("DRV-FX", "a", "b", "c", 0, "KRW")]
    _overlay(extra_drivers=(("X", "x", "x", "x", 0, "X"),)).apply_drivers(base)
    assert len(base) == 1

    base_p = [{"company_profile_id": "P1", "industry_code": "C2412"}]
    _overlay(company_profile_patches={"P1": {"industry_code": "C2421"}}
             ).apply_company_profiles(base_p)
    assert base_p[0]["industry_code"] == "C2412"


# ── 생성기가 판본을 갈아 끼우는가

def test_use_version_이_경로와_정의를_함께_바꾼다(tmp_path):
    import importlib
    gen = importlib.import_module("generate_sample_company_starter_kit")
    before = gen.KIT_ROOT
    try:
        gen.use_version("1.0.0", tmp_path / "여기")
        assert gen.KIT_VERSION == "1.0.0"
        assert gen.KIT_ROOT == tmp_path / "여기"
        assert gen.OVERLAY.version == "1.0.0"
    finally:
        gen.use_version("1.0.0", before)


def test_available_이_판본을_나열한다():
    assert "1.0.0" in kit_defs.available()


# ── P2-3: 새 구조가 동결된 1.0.0 을 그대로 재현하는가

@pytest.mark.slow
def test_새_구조로_재생성해도_1_0_0_데이터가_같다(tmp_path):
    """★★★ P2 의 핵심 검증. 오버레이 구조로 바꾼 뒤에도 **데이터 파일이 한 글자도
    달라지지 않아야** 한다. 달라지면 동결된 1.0.0 을 다시 만들 수 없다는 뜻이다.

    생성기가 만들지 않는 것(Excel·검증보고서)과 생성 시각에 따라 달라지는 것
    (`manifest.json`)은 비교에서 뺀다 — 그것까지 같기를 요구하면 영원히 실패한다.
    """
    import importlib
    from core.data_preparation import kit_freeze as kf

    gen = importlib.import_module("generate_sample_company_starter_kit")
    orig = os.path.join(REPO, "starter_kits", "KIT-MFG-NONFERROUS-PROCUREMENT", "1.0.0")
    out = tmp_path / "rebuild"
    before = gen.KIT_ROOT
    try:
        gen.use_version("1.0.0", out)
        gen.build(clean=True)
    finally:
        gen.use_version("1.0.0", before)

    a, b = kf.fingerprint_dir(orig), kf.fingerprint_dir(str(out))
    skip = lambda p: (p.startswith("templates/excel/") or p.startswith("validations/")
                      or p == "manifest.json")
    diff = sorted(k for k in set(a) & set(b) if not skip(k) and a[k] != b[k])
    missing = sorted(k for k in set(a) - set(b) if not skip(k))
    assert not diff, f"재생성 결과가 다르다: {diff[:10]}"
    assert not missing, f"재생성에서 빠졌다: {missing[:10]}"
    assert len(b) > 100, "재생성이 사실상 비어 있다"
