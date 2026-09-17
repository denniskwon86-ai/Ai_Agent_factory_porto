"""사업 정의 분리 — **키트가 회사가 아니라 사업의 조합인가.**

이 시험이 지키는 것: `KIT-MFG-NONFERROUS-PROCUREMENT` 는 **LS MnM 이라는 회사**를
모델링했고 제련과 황산니켈이 한 덩어리였다. 그래서 고려아연(제련만)·켐코(황산니켈만)
에는 줄 수가 없었다 — **같은 사업을 하는 다른 회사에 못 쓰는 키트.**
"""
import csv
import io
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import business_defs as B  # noqa: E402

SMELT = "smelting_nonferrous"
BATTERY = "battery_materials"
KIT = os.path.join(REPO, "starter_kits", "KIT-MFG-NONFERROUS-PROCUREMENT", "1.2.0")


# ── 로더

def test_사업을_불러온다():
    d = B.load([SMELT])[0]
    assert d.code == SMELT
    assert d.plant_id == "plant-afs-smelting-01"
    assert d.sector.startswith("B:")          # 필드 확장이 붙는 좌표


def test_없는_사업은_거부한다():
    """오타로 사업이 생기면 **빈 키트가 조용히 나온다.**"""
    with pytest.raises(SystemExit) as e:
        B.load(["smelting_nonferrus"])        # 오타
    assert "그런 사업 정의가 없습니다" in str(e.value)


def test_사업을_하나는_넣어야_한다():
    with pytest.raises(SystemExit):
        B.load([])


def test_코드_불일치를_잡는다(monkeypatch):
    """복사해서 만들 때 code 를 안 고치는 실수."""
    class Fake:
        BUSINESS = B.load([SMELT])[0]         # code 는 smelting_nonferrous 인데
    monkeypatch.setattr(B.importlib, "import_module", lambda name: Fake)
    with pytest.raises(SystemExit) as e:
        B.load(["wire_cable"])                # wire_cable 로 부른다
    assert "코드 불일치" in str(e.value)


# ── 사업이 서로 겹치지 않는가

def test_두_사업이_같은_품목을_주장하지_않는다():
    """겹치면 `owner_of()` 가 앞선 사업을 돌려줘 **BOM 범위가 조용히 어긋난다.**"""
    a, b = B.load([SMELT, BATTERY])
    ids_a = {m[0] for m in a.materials}
    ids_b = {m[0] for m in b.materials}
    assert not (ids_a & ids_b), f"두 사업이 함께 주장하는 품목: {ids_a & ids_b}"


def test_사업마다_원료창고와_제품창고가_있다():
    """구매·생산·판매가 그 두 곳을 쓴다. 없으면 참조가 깨진다."""
    for d in B.load([SMELT, BATTERY]):
        assert d.raw_location, f"{d.code} 에 RAW 창고가 없다"
        assert d.fg_location, f"{d.code} 에 FINISHED 창고가 없다"


def test_BOM_의_산출물은_그_사업의_품목이다():
    for d in B.load([SMELT, BATTERY]):
        for product in d.recipes:
            assert d.owns(product), f"{d.code} 가 남의 품목 {product} 의 BOM 을 갖고 있다"


# ── 역참조

def test_공장과_창고로_사업을_찾는다():
    defs = B.load([SMELT, BATTERY])
    assert B.by_plant(defs, "plant-afs-battery-02").code == BATTERY
    assert B.by_location(defs, "LOC-P1-RAW").code == SMELT
    assert B.by_material(defs, "FG-NISO4").code == BATTERY


def test_더미_품목은_사업들에_번갈아_붙는다():
    """사업이 하나면 전부 그 사업으로 가야 한다 — 예전에는 `i%2` 로 두 공장에
    나눠 붙여서, 제련만 뽑아도 배터리 공장이 섞여 나왔다."""
    one = B.load([SMELT])
    assert all(one[i % len(one)].plant_id == one[0].plant_id for i in range(10))


# ── ★ 합격 조건 (느리다 — 키트를 실제로 만든다)

def _generate(tmp_path, businesses):
    import importlib
    gen = importlib.import_module("generate_sample_company_starter_kit")
    out = tmp_path / ("-".join(businesses) or "none")
    before = gen.KIT_ROOT
    try:
        gen.use_version("1.2.0", out)
        gen.build(clean=True, businesses=businesses)
    finally:
        gen.use_version("1.2.0", before)
    return str(out)


@pytest.mark.slow
def test_둘_다_넣으면_정본과_같다(tmp_path):
    """★★★ **정본 키트가 정말 이 사업 조합에서 나오는가.**

    ⚠️ 분리(2026-09-17)에 손실이 없다는 증거는 **1.1.0 의 지문**이 갖고 있다. 그때는
      이 시험이 1.1.0 과 대조했고 한 글자도 다르지 않았다. 지금은 생성기가 1.2.0 을
      만들므로 대조 상대가 1.2.0 이다.

    생성기가 만들지 않는 것(Excel·검증보고서)과 생성 시각에 따라 달라지는 것
    (`manifest.json`)은 비교에서 뺀다.
    """
    from core.data_preparation import kit_freeze as kf
    out = _generate(tmp_path, [SMELT, BATTERY])
    a, b = kf.fingerprint_dir(KIT), kf.fingerprint_dir(out)
    skip = lambda p: (p.startswith("templates/excel/") or p.startswith("validations/")
                      or p == "manifest.json" or p in (".frozen", "fingerprint.json"))
    diff = sorted(k for k in set(a) & set(b) if not skip(k) and a[k] != b[k])
    missing = sorted(k for k in set(a) - set(b) if not skip(k))
    assert not diff, f"분리 후 내용이 달라졌다: {diff[:10]}"
    assert not missing, f"분리 후 빠졌다: {missing[:10]}"


@pytest.mark.slow
@pytest.mark.parametrize("biz,mine,theirs", [
    (SMELT, "plant-afs-smelting-01", "plant-afs-battery-02"),
    (BATTERY, "plant-afs-battery-02", "plant-afs-smelting-01"),
])
def test_하나만_넣으면_그_사업만_나온다(tmp_path, biz, mine, theirs):
    """★★★ **이것이 분리의 목적이다.** 제련만 넣었는데 `FG-NISO4` 가 있으면
    고려아연에 줄 수 없다."""
    out = _generate(tmp_path, [biz])
    hits = []
    for prof in ("quick", "full"):
        d = os.path.join(out, "samples", prof)
        #: `samples/full/quarantine/` 은 디렉터리다 — 파일만 연다
        for name in sorted(n for n in os.listdir(d) if n.endswith(".csv")):
            with io.open(os.path.join(d, name), encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    if r.get("scope_node_id") == theirs:
                        hits.append(f"{prof}/{name}")
                        break
    assert not hits, f"{biz} 만 넣었는데 남의 공장({theirs}) 범위가 남아 있다: {hits[:6]}"


# ── 산업의 의미 (1.2.0)

def test_실제_품목은_그_산업의_등급을_갖는다():
    """1.1.0 까지 실제 품목 12 개가 **전부 `DEMO_STANDARD`** 였고, 정작 더미 품목에만
    `G1~G4` 가 있었다. 거꾸로였다."""
    smelt, battery = B.load([SMELT, BATTERY])
    assert smelt.grade_of("FG-CATHODE") == "LME_GRADE_A"      # 전기동은 LME 등록 등급
    assert battery.grade_of("FG-NISO4") == "BATTERY_GRADE"
    assert smelt.grade_of("MAT-FI-0017") == "DEMO_STANDARD"   # 모르는 것은 모른다고


def test_제련은_부산물을_팔고_전지소재는_팔_것이_없다():
    """★ **제련사는 부산물로 번다.** 1.1.0 까지 황산도 금도 한 톤 안 팔렸다."""
    smelt, battery = B.load([SMELT, BATTERY])
    assert set(smelt.sellable_extra) == {"BP-H2SO4", "BP-GOLD"}
    assert battery.sellable_extra == ()
    sellable = B.sellable_of([smelt, battery], ["FG-CATHODE", "FG-NISO4"])
    assert "BP-GOLD" in sellable and "BP-H2SO4" in sellable


def test_금은_킬로그램으로_판다():
    """1.1.0 까지 판매 단위가 전부 `TON` 이라 **금을 톤으로 팔았다.**"""
    defs = B.load([SMELT])
    assert B.uom_of(defs, "BP-GOLD") == "KG"
    assert B.uom_of(defs, "FG-CATHODE") == "TON"


def test_두_사업의_공정이_다르다():
    """건식 제련(배소·용련·전해정련) ≠ 습식 정제(침출·결정화). 1.1.0 까지는
    **전기동도 습식으로** 만들어졌다."""
    defs = B.load([SMELT, BATTERY])
    smelting = B.routing_ops_for(defs, "FG-CATHODE")
    wet = B.routing_ops_for(defs, "FG-NISO4")
    assert smelting != wet
    assert "전해정련" in smelting and "결정화" in wet


def test_기초재고는_유형에_맞는_창고로_간다():
    """1.1.0 까지 공장마다 규칙이 달라 **공정재고 창고가 비어 있었다.**"""
    smelt = B.load([SMELT])[0]
    assert smelt.opening_location("RAW") == "LOC-P1-RAW"
    assert smelt.opening_location("WIP") == "LOC-P1-WIP"
    assert smelt.opening_location("FINISHED") == "LOC-P1-FG"
    assert smelt.opening_location("BYPRODUCT") == "LOC-P1-FG"
    #: quick 에는 공정재고 창고가 없다 — 원료창고로 떨어진다
    assert smelt.opening_location("WIP", ["LOC-P1-RAW", "LOC-P1-FG"]) == "LOC-P1-RAW"


@pytest.mark.slow
def test_하나만_넣으면_남의_품목도_없다(tmp_path):
    """★★★ 기존 `test_하나만_넣으면_그_사업만_나온다` 는 **`scope_node_id` 만** 봤다.
    그런데 재고 스냅샷은 창고가 범위를 정하므로, 제련 창고 행 안에 **황산니켈이 섞여
    있어도 통과했다** — 고려아연 담당자가 열면 「우리 안 만드는데」가 된다.
    """
    out = _generate(tmp_path, [SMELT])
    theirs = {m[0] for m in B.load([BATTERY])[0].materials}
    hits = []
    for prof in ("quick", "full"):
        d = os.path.join(out, "samples", prof)
        for name in sorted(n for n in os.listdir(d) if n.endswith(".csv")):
            with io.open(os.path.join(d, name), encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    if theirs & {v for k, v in r.items() if k.endswith("material_id") or k == "product_id"}:
                        hits.append(f"{prof}/{name}")
                        break
    assert not hits, f"제련만 넣었는데 전지소재 품목이 남아 있다: {hits[:6]}"
