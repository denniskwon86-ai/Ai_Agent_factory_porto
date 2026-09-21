"""키트 선반 카탈로그 — **무엇을 줄 수 있고 어디가 비었나.**

이 시험이 지키는 것: 손으로 쓴 표는 낡는다. 이 저장소에서 여러 번 겪었다 —
「사업 하나 50 줄」이 실제로는 30 줄이었고, 존재하지 않는 `wire_cable.py` 가 예시에
남아 있었다. 카탈로그가 **실측**이 아니게 되면 같은 일이 되풀이된다.
"""
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import kit_shelf  # noqa: E402
import business_defs  # noqa: E402
from core.data_preparation import kit_registry as kr  # noqa: E402


# ── 씨앗

def test_모든_사업이_씨앗에_있다():
    """빠뜨리면 **줄 수 있는데 없다고 말한다.**"""
    codes = {s["code"] for s in kit_shelf.seeds()}
    assert set(business_defs.available()) <= codes


def test_조합도_씨앗이다():
    """★ 조합을 빼면 `KIT-MFG-NONFERROUS-PROCUREMENT` 가 **「어느 사업에서 나왔는지
    모른다」로 잘못 잡힌다.** 그것은 기본 조합에서 나온다."""
    import generate_sample_company_starter_kit as gen
    ids = {s["kit_id"] for s in kit_shelf.seeds()}
    assert gen.DEFAULT_KIT[0] in ids
    combo = [s for s in kit_shelf.seeds() if s["kit_id"] == gen.DEFAULT_KIT[0]][0]
    assert len(combo["businesses"]) > 1


def test_씨앗은_키트_이름을_갖는다():
    for s in kit_shelf.seeds():
        assert s["kit_id"], f"{s['code']} 에 kit_id 가 없다"
        assert s["sector"], f"{s['code']} 에 sector 가 없다"


# ── 선반

def test_선반이_실제_디렉터리를_반영한다():
    ids = {k["kit_id"] for k in kit_shelf.shelf()}
    assert "KIT-MFG-NONFERROUS-PROCUREMENT" in ids
    kit = [k for k in kit_shelf.shelf() if k["kit_id"] == "KIT-MFG-NONFERROUS-PROCUREMENT"][0]
    assert {v["version"] for v in kit["versions"]} >= {"1.0.0", "1.1.0", "1.2.0"}
    for v in kit["versions"]:
        assert v["frozen"] and v["integrity"] == "PASS", f"{v['version']} 이 온전하지 않다"


def test_구조가_다른_manifest_에도_죽지_않는다():
    """`KIT-MFG-BATTERY-CHEMICAL-PROCUREMENT` 는 키 구성이 다르다
    (`industry`·`primary_loop`·`supported_profiles`)."""
    kits = {k["kit_id"]: k for k in kit_shelf.shelf()}
    other = kits.get("KIT-MFG-BATTERY-CHEMICAL-PROCUREMENT")
    if other is None:
        pytest.skip("그 키트가 없는 저장소")
    assert other["versions"], "판본을 하나도 못 읽었다"


def test_manifest_가_깨져도_죽지_않는다(tmp_path, monkeypatch):
    root = tmp_path / "kits" / "KIT-X" / "1.0.0"
    root.mkdir(parents=True)
    (root / "manifest.json").write_text("{깨진 json", encoding="utf-8")
    monkeypatch.setenv(kr.STARTER_KITS_DIR_ENV, str(tmp_path / "kits"))
    kit = kit_shelf.shelf()[0]
    assert kit["kit_id"] == "KIT-X" and kit["versions"][0]["version"] == "1.0.0"


def test_선반이_없어도_죽지_않는다(tmp_path, monkeypatch):
    monkeypatch.setenv(kr.STARTER_KITS_DIR_ENV, str(tmp_path / "없는곳"))
    assert kit_shelf.shelf() == []
    c = kit_shelf.catalog()
    assert c["summary"]["seed_on_shelf"] == 0        # 씨앗은 그대로 센다


def test_선반은_설정된_자리를_본다(tmp_path, monkeypatch):
    """★ A2 로 연 자리를 실제로 따르는가 — 키트를 옮기면 카탈로그도 따라가야 한다."""
    monkeypatch.setenv(kr.STARTER_KITS_DIR_ENV, str(tmp_path / "옮긴곳"))
    (tmp_path / "옮긴곳" / "KIT-Y" / "2.0.0").mkdir(parents=True)
    assert [k["kit_id"] for k in kit_shelf.shelf()] == ["KIT-Y"]


# ── 대조 — 이 도구의 산출물

def test_빈_칸을_양쪽으로_보여준다():
    """씨앗만 있으면 「뽑으면 된다」, 선반만 있으면 「재현할 수 없다」."""
    c = kit_shelf.catalog()
    assert all("on_shelf" in s for s in c["seeds"])
    assert all("from_business" in k for k in c["shelf"])
    #: 지금은 사업 단독 키트를 아직 뽑지 않았다 — 그 사실이 보여야 한다
    singles = [s for s in c["seeds"] if len(s["businesses"]) == 1]
    assert singles, "사업 단독 씨앗이 하나도 없다"


def test_json_이_직렬화된다():
    json.dumps(kit_shelf.catalog(), ensure_ascii=False)
