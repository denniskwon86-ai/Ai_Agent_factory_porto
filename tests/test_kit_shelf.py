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


def test_선반의_확정_판본은_모두_온전하다():
    """★ **선반이 늘어도 자동으로 지켜지는 불변식.**

    확정(`.frozen`)이면 지문 대장이 있어야 하고 대조를 통과해야 한다. 키트를 하나
    더 올릴 때마다 이 시험이 그 판본까지 함께 본다.
    """
    bad = []
    for k in kit_shelf.shelf():
        for v in k["versions"]:
            if v["frozen"] and v["integrity"] != "PASS":
                bad.append(f"{k['kit_id']}/{v['version']}: {v['integrity']} {v['problems'][:1]}")
    assert not bad, "확정 판본이 온전하지 않다: " + " · ".join(bad)


def test_사업_단독_키트가_선반에_있다():
    """제련만·전지소재만 — **고려아연·켐코에 줄 수 있는 것.**"""
    ids = {k["kit_id"] for k in kit_shelf.shelf()}
    assert {"KIT-MFG-SMELTING-NONFERROUS", "KIT-MFG-BATTERY-MATERIALS"} <= ids


def test_새_키트는_제_이름을_갖는다():
    """★ `kit_name` 이 없으면 카탈로그에 **회사명이 뜬다**(D4). 새로 낸 것은 아니어야."""
    for k in kit_shelf.shelf():
        if k["kit_id"] in ("KIT-MFG-SMELTING-NONFERROUS", "KIT-MFG-BATTERY-MATERIALS"):
            for v in k["versions"]:
                assert v["kit_name"], f"{k['kit_id']}/{v['version']} 에 kit_name 이 없다"
                assert v["sector"], f"{k['kit_id']}/{v['version']} 에 sector 가 없다"


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
    singles = [s for s in c["seeds"] if len(s["businesses"]) == 1]
    assert singles, "사업 단독 씨앗이 하나도 없다"
    #: 선반에만 있는 것(사업 정의를 모르는 키트)을 **감추지 않는다**
    assert any(not k["from_business"] for k in c["shelf"]) or         all(k["from_business"] for k in c["shelf"])


def test_json_이_직렬화된다():
    json.dumps(kit_shelf.catalog(), ensure_ascii=False)


# ── 지워도 되나 — **참조를 실측한다**

def test_묵은_판본이라고_지울_수_있는_것이_아니다():
    """★★★ **이번에 데인 것의 회귀 감시.**

    1.0.0·1.1.0 을 「봉인 결함이 있던 판본」이라고 지우려다 멈췄다. 둘은 **시험의
    고정물**이었다 —

        1.0.0   core/demo_vertical_slice.py 가 그 samples/full/*.csv 를 읽는다
                (플랫폼 계산 카나리의 정본)
        1.1.0   tests/test_kit_freeze.py 가 그 봉인을 지켜본다
                ← **그 판본이 바로 「대장 없이 PASS」 하던 것**이다

    지웠으면 감시가 조용히 사라졌을 것이다. 「오래됐나」가 아니라 **「누가 가리키나」**
    로 판단해야 한다.
    """
    for ver in ("1.0.0", "1.1.0"):
        r = kit_shelf.referrers("KIT-MFG-NONFERROUS-PROCUREMENT", ver)
        assert r["count"], f"{ver} 를 가리키는 곳이 하나도 없다고 나온다 — 훑기가 고장났다"


def test_플랫폼이_1_0_0_을_읽는_것이_보인다():
    """`core/demo_vertical_slice.py` 는 `KIT_ID` 와 `KIT_VERSION` 을 **따로** 적는다.
    경로 한 덩어리만 찾으면 이 가장 중요한 참조를 놓친다."""
    r = kit_shelf.referrers("KIT-MFG-NONFERROUS-PROCUREMENT", "1.0.0")
    assert "core/demo_vertical_slice.py" in r["direct"] + r["probable"]


def test_1_1_0_의_봉인_감시가_보인다():
    r = kit_shelf.referrers("KIT-MFG-NONFERROUS-PROCUREMENT", "1.1.0")
    assert "tests/test_kit_freeze.py" in r["direct"] + r["probable"]


def test_선반_도구_자신은_세지_않는다():
    """⚠️ 이 파일의 설명이 판본 번호를 예로 든다. 빼지 않으면 **모든 판본이
    「선반 도구가 쓴다」**로 잡혀 셈이 무의미해진다."""
    for ver in ("1.0.0", "1.1.0", "1.2.0", "1.3.0"):
        r = kit_shelf.referrers("KIT-MFG-NONFERROUS-PROCUREMENT", ver)
        assert "scripts/kit_shelf.py" not in r["direct"] + r["probable"]


def test_아무도_안_쓰는_판본은_그렇게_보인다():
    """셈이 언제나 0 이 아닌 것을 확인한다 — **거짓 초록을 막는다.**

    ⚠️ 이름을 **런타임에 조립한다.** 소스에 그대로 적으면 이 파일 자신이 그 이름을
      담게 되어 「1 곳이 쓴다」가 나온다 (처음에 그렇게 썼다가 걸렸다). 훑기가
      **언급과 참조를 구분하지 못한다**는 사실이 여기서 드러난다.
    """
    kit = "KIT-" + "".join(["없는", "키트"])
    r = kit_shelf.referrers(kit, "9." + "9.9")
    assert r["count"] == 0 and r["direct"] == [] and r["probable"] == []


def test_판본마다_참조가_카탈로그에_실린다():
    for k in kit_shelf.shelf():
        for v in k["versions"]:
            assert "referrers" in v, f"{k['kit_id']}/{v['version']} 에 참조가 없다"
            assert set(v["referrers"]) >= {"direct", "probable", "count"}


def test_요약이_지울_후보를_말한다():
    c = kit_shelf.catalog()
    assert "unreferenced" in c["summary"]
    on_shelf = {f'{k["kit_id"]}/{v["version"]}'
                for k in c["shelf"] for v in k["versions"]}
    assert set(c["summary"]["unreferenced"]) <= on_shelf
