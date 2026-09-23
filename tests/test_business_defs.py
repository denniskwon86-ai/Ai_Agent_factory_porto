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
KIT = os.path.join(REPO, "starter_kits", "KIT-MFG-NONFERROUS-PROCUREMENT", "1.7.0")


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
        gen.use_version("1.7.0", out)
        gen.build(clean=True, businesses=businesses)
    finally:
        gen.use_version("1.7.0", before)
    return str(out)


@pytest.mark.slow
def test_둘_다_넣으면_정본과_같다(tmp_path):
    """★★★ **정본 키트가 정말 이 사업 조합에서 나오는가.**

    ⚠️ 분리(2026-09-17)에 손실이 없다는 증거는 **1.1.0 의 지문**이 갖고 있다. 그때는
      이 시험이 1.1.0 과 대조했고 한 글자도 다르지 않았다. 지금은 생성기가 1.3.0 을
      만들므로 대조 상대가 1.3.0 이다.

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


def test_파는_것은_만들거나_사야_한다():
    """★★★ **팔려면 있어야 한다.** `sellable_extra` 에 넣고 `byproduct_rates` 를
    비우면 없는 것을 파는 셈이라 재고가 마이너스로 간다 — 1.2.0 을 만들면서 실제로
    −1,203 톤까지 갔고, 검증 418 건이 그것을 못 잡았다(2026-09-17).
    """
    for d in B.load([SMELT, BATTERY]):
        made = {bp for rates in d.byproduct_rates.values() for bp, _ in rates}
        bought = {m[0] for m in d.materials if m[2] in ("RAW", "CONSUMABLE")}
        for mid in d.sellable_extra:
            assert mid in made or mid in bought,                 f"{d.code}: {mid} 를 파는데 만들지도 사지도 않는다"


def test_부산물_산출량은_그_산업의_모양을_담는다():
    """황산은 전기동보다 **많이**, 금은 **아주 적게** 나온다. 그 비대칭이 제련이다."""
    smelt = B.load([SMELT])[0]
    rates = dict(smelt.byproduct_rates["FG-CATHODE"])
    assert rates["BP-H2SO4"] > 1.0, "황산은 전기동보다 많이 나온다"
    assert rates["BP-GOLD"] < 0.1, "금은 아주 조금 나온다"


def test_실제_제품은_전체_공정을_거친다():
    """★ 공정 이름을 갈라 놓고 **제품이 그 공정을 다 거치지 않으면 반쪽이다.**
    1.2.0 초안에서 전기동이 「배소 → 전로정련」 둘뿐이었다 — 설비를 제품과 공정에
    각각 나머지 연산으로 돌린 탓에 용련·정제·전해정련이 빠졌다.
    """
    defs = B.load([SMELT, BATTERY])
    assert len(B.routing_ops_for(defs, "FG-CATHODE")) == 5
    assert len(B.routing_ops_for(defs, "FG-NISO4")) == 5


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


# ── 키트 정체성 (선반에 올리기 위한 이름표)

def test_사업은_키트_정체성을_갖는다():
    """★ 이름표가 없으면 **전지소재만 뽑아도 manifest 가 제련 키트**로 나온다.
    데이터는 맞는데 이름이 틀리면, 그대로 켐코에 「비철 조달 키트」를 주는 셈이다."""
    for d in B.load([SMELT, BATTERY]):
        assert d.kit_id.startswith("KIT-"), f"{d.code} 에 kit_id 가 없다"
        assert d.kit_name, f"{d.code} 에 kit_name 이 없다"
        assert d.use_case, f"{d.code} 에 use_case 가 없다"


def test_키트_식별자가_겹치지_않는다():
    """겹치면 선반에서 **한 칸이 다른 칸을 덮는다.**"""
    ids = [d.kit_id for d in (B.load([c])[0] for c in B.available())]
    assert len(ids) == len(set(ids)), f"겹치는 kit_id: {ids}"


def test_사업_하나면_그_사업의_이름이_나온다():
    for code, kit in ((SMELT, "KIT-MFG-SMELTING-NONFERROUS"),
                      (BATTERY, "KIT-MFG-BATTERY-MATERIALS")):
        kid, name, use = B.kit_identity(B.load([code]))
        assert kid == kit and name and use


def test_조합은_키트_이름을_명시해야_한다():
    """★ 「제련+전지소재」에 **자동으로 붙일 옳은 이름이 없다.** 앞 사업 것을 쓰거나
    이어 붙이면 그럴듯한 오답이 나온다 — 사람이 정할 일이다."""
    defs = B.load([BATTERY, SMELT])
    with pytest.raises(SystemExit) as e:
        B.kit_identity(defs)
    assert "명시" in str(e.value)
    kid, name, use = B.kit_identity(defs, "KIT-X", "엑스 키트")
    assert kid == "KIT-X" and name == "엑스 키트" and use      # use_case 는 이어 붙인다


def test_이름이_없는_사업은_거부한다(monkeypatch):
    """복사해서 새 사업을 만들 때 `kit_id` 를 안 적는 실수."""
    d = B.load([SMELT])[0]
    monkeypatch.setattr(type(d), "kit_id", "", raising=False)
    with pytest.raises(SystemExit) as e:
        B.kit_identity([d])
    assert "kit_id" in str(e.value)


@pytest.mark.slow
def test_사업_하나면_그_키트가_나온다(tmp_path):
    """★★★ **선반에 올릴 수 있는가.** manifest 의 이름표가 그 사업 것이어야 한다."""
    import json
    out = _generate(tmp_path, [SMELT])
    m = json.load(io.open(os.path.join(out, "manifest.json"), encoding="utf-8"))
    assert m["kit_id"] == "KIT-MFG-SMELTING-NONFERROUS"
    assert m["kit_name"] == "비철 제련·정련 업무키트"
    assert m["company_name"] == "AFS 메탈 주식회사"       # 그룹 이름이 아니다
    assert m["sector"] == ["B:금속>비철금속>제련·정련"]
    #: ⚠️ KSIC 는 **법인 구조가 정한다** — 켐코 C2820 vs LS MnM C24. 키트 속성이 아니다
    assert "industry_codes" not in m


# ── 주력이 매출을 만드는가 (1.4.0)

def _sales_share(kit_id: str, codes):
    """매출을 **주력과 더미로** 가른다. 주력 = 사업 정의가 아는 품목."""
    path = os.path.join(REPO, "starter_kits", kit_id, "1.7.0", "samples", "full", "SLS-01.csv")
    known = {m["code"] for m in B.materials_of(B.load(list(codes)))}
    major = rest = 0.0
    with io.open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                a = float(r["shipped_quantity"] or 0) * float(r["unit_price"] or 0)
            except (TypeError, ValueError):
                continue
            if r["product_id"] in known:
                major += a
            else:
                rest += a
    return major / (major + rest) if (major + rest) else 0.0


@pytest.mark.parametrize("kit_id,codes", [
    ("KIT-MFG-SMELTING-NONFERROUS", [SMELT]),
    ("KIT-MFG-BATTERY-MATERIALS", [BATTERY]),
    ("KIT-MFG-NONFERROUS-PROCUREMENT", [SMELT, BATTERY]),
])
def test_주력이_매출의_대부분이다(kit_id, codes):
    """★★★ 1.3.0 까지 매출의 **99% 를 볼륨용 더미**(「완제품 011」)가 차지했다.

    「이 산업은 이렇게 일한다」를 보이려는 키트인데 **산업이 1% 뿐**이었고, 검사
    420 건이 그것을 못 잡았다. 현업에 드린 문서의 매출 구성도 **더미를 빼고 센 값**
    이라 데이터와 맞지 않았다(2026-09-22 전수 재검수).

    하한만 본다 — 정확한 비중은 사업마다 다르지만 **주력이 과반도 안 되는 제조사는
    없다.**
    """
    share = _sales_share(kit_id, codes)
    assert share >= 0.70, f"{kit_id}: 주력이 매출의 {share:.1%} 뿐이다"


def test_팔_수_있는_완제품은_단가를_갖는다():
    """★★★ **단가를 빠뜨리면 더미 단가로 조용히 떨어진다.**

    1.3.0 까지 생성기가 `if product == "FG-NISO4" ... elif "FG-CATHODE"` 로 분기했고,
    거기 없는 완제품은 더미 기본값(32,000)을 썼다. `FG-LIOH` 가 실제로 그랬는데
    **그 값이 마침 그럴듯해 아무도 몰랐다.** 더미 기본값을 1,200 으로 낮추자
    수산화리튬 매출이 **57% 에서 4.5% 로 무너지면서** 드러났다.

    ⚠️ 부산물은 `sale_prices` 에 있어야 하고, 완제품도 그렇다 — **사업이 품목을 늘릴
      때 생성기를 고쳐야 하는 구조**를 없앴으므로, 빠뜨리면 여기서 걸린다.
    """
    missing = []
    for code in (SMELT, BATTERY):
        d = B.load([code])[0]
        for mat in d.materials:
            mid, _name, typ = mat[0], mat[1], mat[2]
            if typ != "FINISHED":
                continue
            if mid not in d.sale_prices:
                missing.append(f"{code}:{mid}")
        for extra in d.sellable_extra:
            if extra not in d.sale_prices:
                missing.append(f"{code}:{extra}(부산물)")
    assert not missing, "단가 없는 판매 품목: " + ", ".join(missing)


def test_주력_단가가_더미보다_비싸다():
    """부대 품목이 주력보다 비쌀 이유가 없다 — 1.3.0 에서는 **3.4 배 비쌌다**
    (더미 32,000 vs 전기동 9,500)."""
    import generate_sample_company_starter_kit as gen
    for code in (SMELT, BATTERY):
        d = B.load([code])[0]
        for mid, price in d.sale_prices.items():
            if mid.startswith("FG-"):
                assert price > gen._FILLER_PRICE, f"{mid} 단가 {price} ≤ 더미 {gen._FILLER_PRICE}"


# ── 만든 것보다 많이 팔지 않는가 (1.4.0)

def _made_and_sold(kit_id: str):
    """품목별 **산출**과 **판매**. 부산물은 배치가 아니라 부산물 입고로 들어온다."""
    root = os.path.join(REPO, "starter_kits", kit_id, "1.7.0", "samples", "full")
    made, sold = {}, {}
    with io.open(os.path.join(root, "MFG-02.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            made[r["output_material_id"]] = made.get(r["output_material_id"], 0.0) + float(r["output_quantity"] or 0)
    with io.open(os.path.join(root, "INV-02.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["movement_id"].startswith("MOV-BP-"):
                made[r["material_id"]] = made.get(r["material_id"], 0.0) + float(r["quantity"] or 0)
    with io.open(os.path.join(root, "SLS-01.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            sold[r["product_id"]] = sold.get(r["product_id"], 0.0) + float(r["shipped_quantity"] or 0)
    return made, sold


@pytest.mark.parametrize("kit_id,codes", [
    ("KIT-MFG-SMELTING-NONFERROUS", [SMELT]),
    ("KIT-MFG-BATTERY-MATERIALS", [BATTERY]),
    ("KIT-MFG-NONFERROUS-PROCUREMENT", [SMELT, BATTERY]),
])
def test_만든_것보다_많이_팔지_않는다(kit_id, codes):
    """★★★ **재고 음수 검사가 이것을 못 잡는다.**

    조정 이벤트(`MOV-ADJ`, 이동의 32%)가 재고를 채워 잔고가 양수로 남기 때문이다.
    실제로 1.4.0 을 만들다 **전기동을 6,972 톤 만들면서 12,980 톤 파는** 데이터를
    냈는데 검사 422 건이 전부 통과했다. 금도 그랬다 — 산출 197 kg, 판매 259 kg.

    ★ 그래서 현업 문서의 「금이 매출의 13.8%」가 **과잉 판매가 만든 값**이었다.
      산출대로 팔면 7% 안팎이다.
    """
    made, sold = _made_and_sold(kit_id)
    known = {m["code"] for m in B.materials_of(B.load(list(codes)))}
    over = [f"{m}: 산출 {made.get(m, 0):,.0f} < 판매 {q:,.0f}"
            for m, q in sold.items() if m in known and q > made.get(m, 0.0)]
    assert not over, "; ".join(over)


def test_그_검사가_거짓초록이_아니다():
    """산출을 **일부러 줄여** 검사가 우는지 본다 — 비교가 언제나 참이면 소용없다."""
    made, sold = _made_and_sold("KIT-MFG-SMELTING-NONFERROUS")
    assert made.get("FG-CATHODE", 0) > 0 and sold.get("FG-CATHODE", 0) > 0, "잴 것이 없다"
    broken = dict(made, **{"FG-CATHODE": sold["FG-CATHODE"] * 0.5})
    over = [m for m, q in sold.items() if q > broken.get(m, 0.0) and m == "FG-CATHODE"]
    assert over == ["FG-CATHODE"], "산출을 절반으로 줄여도 안 잡힌다 — 비교가 헛돈다"


def test_부산물도_만든_만큼만_판다():
    """부산물은 `MFG-02` 에 배치가 없다. **부산물 입고(`MOV-BP-`)를 산출로 봐야**
    한다 — 안 그러면 「산출 0 인데 판다」로 잘못 걸리거나, 반대로 검사에서 빠진다."""
    made, sold = _made_and_sold("KIT-MFG-SMELTING-NONFERROUS")
    for bp in ("BP-GOLD", "BP-H2SO4"):
        assert made.get(bp, 0) > 0, f"{bp} 산출이 0 이다 — 부산물 입고를 못 읽었다"
        assert sold.get(bp, 0) <= made[bp], f"{bp}: 산출 {made[bp]:,.1f} < 판매 {sold[bp]:,.1f}"


# ── 생산·구매에도 산업이 보이는가 (1.5.0)

def _counts(kit_id: str, dataset: str, col: str, codes):
    root = os.path.join(REPO, "starter_kits", kit_id, "1.7.0", "samples", "full")
    known = {m["code"] for m in B.materials_of(B.load(list(codes)))}
    major = total = 0
    with io.open(os.path.join(root, dataset + ".csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            total += 1
            if (r.get(col) or "") in known:
                major += 1
    return major / total if total else 0.0


@pytest.mark.parametrize("kit_id,codes", [
    ("KIT-MFG-SMELTING-NONFERROUS", [SMELT]),
    ("KIT-MFG-BATTERY-MATERIALS", [BATTERY]),
    ("KIT-MFG-NONFERROUS-PROCUREMENT", [SMELT, BATTERY]),
])
def test_사는_장면과_만드는_장면이_보인다(kit_id, codes):
    """★ 1.4.0 까지 **생산 9% · 발주 1%** 였다. 이 키트의 용도는 「원료 구매·도입
    계획에서 경영 영향과 실행 결정까지」인데, **사는 장면이 데이터에 없으면** 그
    용도가 성립하지 않는다.

    하한만 본다 — 구매 대상이 144 종(원료 72 · 소모품 72)이라 주력이 전부를
    차지할 수는 없다.
    """
    assert _counts(kit_id, "MFG-02", "output_material_id", codes) >= 0.30
    assert _counts(kit_id, "PRC-02", "material_id", codes) >= 0.15


@pytest.mark.parametrize("kit_id,codes", [
    ("KIT-MFG-SMELTING-NONFERROUS", [SMELT]),
    ("KIT-MFG-BATTERY-MATERIALS", [BATTERY]),
    ("KIT-MFG-NONFERROUS-PROCUREMENT", [SMELT, BATTERY]),
])
def test_배합대로_원료가_나간다(kit_id, codes):
    """★★★ 1.4.0 까지 배치가 **BOM 첫 줄만** 출고했다.

    「수산화리튬 = Black Mass 5.20 + 황산 0.12 + 소석회 0.05」인데 Black Mass 만
    나갔고, 부재료는 **사 놓고 쓰지 않았다** — 조합 키트에서 황산 706 톤 구매 ·
    **0 톤 소비**. 1.3.0 에서 배합비를 현업에 물으면서 정작 그 배합대로 만들지
    않고 있었다.
    """
    root = os.path.join(REPO, "starter_kits", kit_id, "1.7.0", "samples", "full")
    known = {m["code"] for m in B.materials_of(B.load(list(codes)))}
    with io.open(os.path.join(root, "MDM-05.csv"), encoding="utf-8-sig") as f:
        need = {r["input_material_id"] for r in csv.DictReader(f)
                if r["component_role"] == "INPUT" and r["input_material_id"] in known}
    with io.open(os.path.join(root, "INV-02.csv"), encoding="utf-8-sig") as f:
        issued = {r["material_id"] for r in csv.DictReader(f)
                  if r["movement_id"].startswith("MOV-ISS-")}
    assert need, "BOM 에 주력 원료가 없다 — 잴 것이 없다"
    assert not (need - issued), f"BOM 에 있는데 출고가 없다: {sorted(need - issued)}"


@pytest.mark.parametrize("kit_id,codes", [
    ("KIT-MFG-SMELTING-NONFERROUS", [SMELT]),
    ("KIT-MFG-BATTERY-MATERIALS", [BATTERY]),
    ("KIT-MFG-NONFERROUS-PROCUREMENT", [SMELT, BATTERY]),
])
def test_산_것보다_많이_쓰지_않는다(kit_id, codes):
    """⚠️ 이것도 재고 음수 검사가 못 잡았다 — 기초재고가 크고 조정 이벤트가 받쳐서
    잔고가 양수로 남는다. 1.4.0 에서 **동정광을 20,176 톤 쓰면서 612 톤만 샀다.**"""
    root = os.path.join(REPO, "starter_kits", kit_id, "1.7.0", "samples", "full")
    known = {m["code"] for m in B.materials_of(B.load(list(codes)))}
    got, spent = {}, {}
    with io.open(os.path.join(root, "INV-02.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            q = float(r["quantity"] or 0)
            if r["movement_id"].startswith("MOV-ISS-"):
                spent[r["material_id"]] = spent.get(r["material_id"], 0.0) - q
            elif r["movement_id"].startswith(("MOV-OPEN", "MOV-IN")):
                got[r["material_id"]] = got.get(r["material_id"], 0.0) + q
    with io.open(os.path.join(root, "PRC-02.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            got[r["material_id"]] = got.get(r["material_id"], 0.0) + float(r["order_quantity"] or 0)
    short = [f"{m}: 조달 {got.get(m, 0):,.0f} < 소비 {q:,.0f}"
             for m, q in spent.items() if m in known and q > got.get(m, 0.0)]
    assert not short, "; ".join(short)


# ── 사서 쓰는가, 쌓아둔 것을 쓰는가 (1.6.0)

@pytest.mark.parametrize("kit_id,codes", [
    ("KIT-MFG-SMELTING-NONFERROUS", [SMELT]),
    ("KIT-MFG-BATTERY-MATERIALS", [BATTERY]),
    ("KIT-MFG-NONFERROUS-PROCUREMENT", [SMELT, BATTERY]),
])
def test_쌓아둔_것이_아니라_사서_쓴다(kit_id, codes):
    """★★★ 「산 것보다 많이 쓰지 않는다」는 **기초재고를 넣어서** 보므로, 기초재고만
    크면 **구매가 0 이어도 통과**한다.

    1.5.0 까지 실제로 그랬다 — 입고가 소비의 **51~57%** 뿐이고 나머지를 기초재고
    (소비의 1.15 배 = 36 개월치)가 댔다. 「사는 회사」가 아니라 「쌓아둔 것을 쓰는
    회사」였고, 이 키트의 용도가 **「원료 구매·도입계획」**인데 그랬다.

    1.6.0 에서 **생산을 먼저 만들고 그 소비량으로 구매를 내도록** 순서를 바꿨다.
    """
    root = os.path.join(REPO, "starter_kits", kit_id, "1.7.0", "samples", "full")
    known = {m["code"] for m in B.materials_of(B.load(list(codes)))}
    used, recv = {}, {}
    with io.open(os.path.join(root, "INV-02.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            q = float(r["quantity"] or 0)
            mv = r["movement_id"]
            if mv.startswith("MOV-ISS-") and r["material_id"] in known:
                used[r["material_id"]] = used.get(r["material_id"], 0.0) - q
            elif mv.startswith("MOV-IN"):
                recv[r["material_id"]] = recv.get(r["material_id"], 0.0) + q
    total = sum(used.values())
    covered = sum(recv.get(m, 0.0) for m in used)
    assert total > 0, "주력 원료 소비가 없다 — 잴 것이 없다"
    assert covered / total >= 0.80, f"입고가 소비의 {covered/total:.0%} 뿐이다"


def test_손으로_맞추던_상수가_사라졌다():
    """★ 1.5.0 까지 발주량을 `purchase_qty_scale` 이라는 상수로 정했다. 사업마다
    원료 수가 다르고 판본마다 생산량이 달라져 **1.5.0 을 내면서만 네 번 고쳤다.**
    이제 소비에서 역산하므로 그 상수가 필요 없다 — 되살리지 말 것."""
    for code in (SMELT, BATTERY):
        d = B.load([code])[0]
        assert not hasattr(d, "purchase_qty_scale"), f"{code} 에 그 상수가 되살아났다"


# ── 조정이 재고를 만들지 않는가 (1.7.0)

@pytest.mark.parametrize("kit_id", [
    "KIT-MFG-SMELTING-NONFERROUS",
    "KIT-MFG-BATTERY-MATERIALS",
    "KIT-MFG-NONFERROUS-PROCUREMENT",
])
def test_조정이_재고를_만들지_않는다(kit_id):
    """★★★ 실사 조정은 **양방향**이다 — 장부보다 많을 때도 적을 때도 있다.

    1.6.0 까지 **전부 입고(양수)** 라서 재고가 저절로 늘었고(제련 +326 톤), 그것이
    「없는 것을 판다·쓴다」를 **재고 음수로 드러나지 않게 가렸다.** 이 저장소가 늦게
    발견한 결함 셋이 모두 그 뒤에 숨어 있었다 —

        과잉 판매 · 미구매 · 부재료 미소비

    ⚠️ 볼륨을 채우려고 넣은 것이 **검사를 무력화하고 있었다.**
    """
    path = os.path.join(REPO, "starter_kits", kit_id, "1.7.0", "samples", "full", "INV-02.csv")
    with io.open(path, encoding="utf-8-sig") as f:
        adj = [float(r["quantity"] or 0) for r in csv.DictReader(f)
               if r["movement_id"].startswith("MOV-ADJ")]
    if not adj:
        pytest.skip("이 키트는 실제 이동만으로 목표 행수를 채운다")
    gross = sum(abs(x) for x in adj)
    assert abs(sum(adj)) <= gross * 0.05, f"조정 순증 {sum(adj):+,.1f} / 총량 {gross:,.1f}"
    assert any(x > 0 for x in adj) and any(x < 0 for x in adj), "조정이 한 방향뿐이다"


def test_조정은_그_품목이_있는_창고에만_들어간다():
    """⚠️ 예전에는 사업의 창고를 **순환**해서 완제품이 원료 창고에 조정 입고됐다.
    전부 양수일 때는 「조금 있다」로 남았지만, 음수 조정을 넣자 **없는 재고를 줄여**
    재고가 −6,430 행이 됐다."""
    root = os.path.join(REPO, "starter_kits", "KIT-MFG-SMELTING-NONFERROUS", "1.7.0",
                        "samples", "full")
    with io.open(os.path.join(root, "MDM-01.csv"), encoding="utf-8-sig") as f:
        kind = {r["material_id"]: r["material_type"] for r in csv.DictReader(f)}
    bad = []
    with io.open(os.path.join(root, "INV-02.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if not r["movement_id"].startswith("MOV-ADJ"):
                continue
            loc = r["to_location_id"] if float(r["quantity"] or 0) > 0 else r["from_location_id"]
            t = kind.get(r["material_id"], "")
            #: 창고 이름이 유형을 말한다 — `LOC-P1-RAW` · `-FG` · `-WIP` · `-BP`
            if t == "FINISHED" and loc.endswith("-RAW"):
                bad.append((r["material_id"], loc))
    assert not bad, f"완제품이 원료 창고에 조정됐다: {bad[:3]}"
