"""키트 → 플랫폼 이음매.

★ 아래는 **전부 이 세션의 검증에서 실제로 드러난 것**이다. 하나도 상상해서 쓴 것이
없다. 시험이 없으면 그대로 다시 일어난다
(`docs/data-kits/KIT_PLATFORM_BRIDGE_SPEC_2026-09-16.md` 4 장).
"""
import csv
import io
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import kit_bridge as kb  # noqa: E402

KIT = os.path.join(REPO, "starter_kits", "KIT-MFG-SMELTING-NONFERROUS", "1.4.0")


def _rows(dataset, profile="quick"):
    with io.open(os.path.join(KIT, "samples", profile, f"{dataset}.csv"),
                 encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


class FakeDrivers:
    """`core.planning_drivers` 대역. **무엇을 불렀는지 그대로 남긴다.**"""

    def __init__(self, existing=()):
        self.registered = {}
        self.impacts = {}
        self._existing = [{"driver_code": c} for c in existing]

    def list_drivers(self):
        return self._existing + [{"driver_code": c} for c in self.registered]

    def register_driver(self, **kw):
        self.registered[kw["driver_code"]] = kw
        return kw

    def impacts_of(self, code):
        return self.impacts.get(code, [])


class FakeStore:
    def __init__(self):
        self.accounts = {}

    def upsert_account(self, *, account_code, name, category, sign=1, parent_code=""):
        if category not in ("REVENUE", "COGS", "SGA", "OTHER_INCOME", "OTHER_EXPENSE", "TAX"):
            raise ValueError(f"알 수 없는 계정 분류: {category}")
        self.accounts[account_code] = {"name": name, "category": category, "sign": sign}
        return self.accounts[account_code]


# ── 1 · 2 단위 — 가장 작고 가장 위험하다

def test_비율을_퍼센트_수로_옮긴다():
    """★ 키트는 `0.1`(비율), 플랫폼은 `10`(퍼센트 수). 그대로 넘기면 **오류 없이
    100 배 작게** 계산되고, 그 보고서를 이상하다고 느끼지 못한다."""
    assert kb.to_pct_change("0.1", "%") == 10.0
    assert kb.to_pct_change("-0.2", "PCT") == -20.0
    assert kb.to_pct_change(0.035, "percent") == pytest.approx(3.5)


@pytest.mark.parametrize("value,unit", [("14", "DAY"), ("48", "HOUR"), ("1.8e11", "KRW")])
def test_절대량은_조용히_넘기지_않는다(value, unit):
    """★ 키트 시나리오의 **40%** 가 여기 걸린다 — 선적 지연 14 일 · 설비 정지 48 시간 ·
    투자 1,800 억. 하필 **경영 판단에 가장 가까운 것들**이다.

    옮긴 척하면 그 시나리오는 「실행됐는데 아무 일도 안 일어난」 것이 된다.
    """
    with pytest.raises(kb.UnsupportedScenarioUnit):
        kb.to_pct_change(value, unit)


def test_퍼센트포인트를_퍼센트로_착각하지_않는다():
    """★★★ 수율 92%→90% 는 −2%p 이고 **−2.17%** 다. `%` 로 잘못 보고 ×100 하면
    −2.0 이 되어 **그럴듯하게 틀린다** — 차이가 작아 눈으로 못 잡는다."""
    with pytest.raises(kb.NeedsBaseline):
        kb.to_pct_change("-0.02", "PERCENT_POINT")
    got = kb.to_pct_change_from_baseline("-0.02", "PERCENT_POINT", baseline=0.92)
    assert got == pytest.approx(-2.17, abs=0.01)
    assert got != pytest.approx(-2.0, abs=0.01), "%p 를 % 로 읽었다"


def test_기준값이_없으면_거부한다():
    with pytest.raises(kb.NeedsBaseline):
        kb.to_pct_change_from_baseline("-0.02", "PERCENT_POINT", baseline=0)


# ── 4 · 6 대응표

def test_등록되는_이름이_업무_언어다():
    """★ `input_metric` 을 그대로 넣으면 화면에 `AR_AP_TIMING` 이 뜬다. 대응표와의
    **일치**로 잠근다 — 새 동인을 넣으면 시험이 먼저 깨지고, 그것이 의도다."""
    fake = FakeDrivers()
    kb.seed_plan_drivers(_rows("SIM-01"), drivers=fake)
    want = kb.driver_map()
    for code, kw in fake.registered.items():
        assert code in want, f"대응표에 없는 동인이 등록됐다: {code}"
        assert kw["name"] == want[code]["name"]
        assert "_" not in kw["name"], f"기계 이름이 들어갔다: {kw['name']}"
        assert kw["unit"] == want[code]["unit"]


def test_계산식은_동인으로_넣지_않는다():
    """★ `DRV-GM` 은 **동인이 아니라 계산식**이다. 「매출과 원가가 1% 변하면 GM 이
    몇 %」는 물음이 성립하지 않고, 플랫폼은 계정 부호로 **이미 계산한다.**"""
    fake = FakeDrivers()
    out = kb.seed_plan_drivers(_rows("SIM-01"), drivers=fake)
    assert "DRV-GM" not in fake.registered
    assert any(code == "DRV-GM" for code, _ in out["excluded"])


def test_대응표에_없는_동인은_기계이름으로_채우지_않는다():
    fake = FakeDrivers()
    out = kb.seed_plan_drivers([{"driver_id": "DRV-처음보는것", "input_metric": "X_Y_Z"}],
                               drivers=fake)
    assert fake.registered == {}
    assert out["excluded"][0][0] == "DRV-처음보는것"


# ── 3 · 5 · 8 심기

def test_파급_계수를_만들지_않는다():
    """★★★ 계수는 **현업이 근거·출처와 함께** 등록한다. 키트가 만들면 창작이고,
    그 숫자가 경영 판단으로 간다."""
    fake = FakeDrivers()
    kb.seed_plan_drivers(_rows("SIM-01"), drivers=fake)
    assert fake.impacts == {}
    for code in fake.registered:
        assert fake.impacts_of(code) == []


def test_이미_있는_동인을_덮지_않는다():
    """현업이 고쳐 놓았을 수 있고 승인된 판본이 딸려 있을 수 있다."""
    fake = FakeDrivers(existing=["DRV-FX"])
    out = kb.seed_plan_drivers(_rows("SIM-01"), drivers=fake)
    assert "DRV-FX" in out["skipped_existing"]
    assert "DRV-FX" not in fake.registered


def test_note_에_키트가_아는_것을_담는다():
    fake = FakeDrivers()
    kb.seed_plan_drivers(_rows("SIM-01"), drivers=fake)
    note = fake.registered["DRV-FX"]["note"]
    assert "PURCHASE_COST" in note and "계산식" in note


def test_건너뛴_것이_보고된다():
    """★ 셋을 갈라 돌려준다 — 하나로 뭉치면 「없다」와 「뺐다」와 「이미 있다」가
    같은 모양이 되고, 부른 쪽은 무엇을 확인해야 할지 모른다."""
    d = kb.seed_plan_drivers(_rows("SIM-01"), drivers=FakeDrivers())
    a = kb.seed_plan_accounts(_rows("MDM-07"), store=FakeStore())
    text = kb.summarize(d, a)
    assert "DRV-GM" in text and "건너뜀" in text
    assert d["excluded"] and a["skipped"]


# ── 7 계정

def test_손익_계정만_옮기고_재무상태표는_건너뛴다():
    """⚠️ 버릴지 `WORKING_CAPITAL` 로 보낼지 아직 정해지지 않았다 — 그때까지
    **조용히 사라지게 두지 않는다.**"""
    store = FakeStore()
    out = kb.seed_plan_accounts(_rows("MDM-07"), store=store)
    rows = _rows("MDM-07")
    want_skip = [r for r in rows if r["pnl_line"] == "BALANCE_SHEET"]
    assert len(out["skipped"]) == len(want_skip) == 4
    assert all(item[2] == "BALANCE_SHEET" for item in out["skipped"])
    assert len(out["loaded"]) == len(rows) - len(want_skip)
    assert out["failed"] == []


def test_수익만_부호가_플러스다():
    store = FakeStore()
    kb.seed_plan_accounts(_rows("MDM-07"), store=store)
    signs = {a["category"]: a["sign"] for a in store.accounts.values()}
    assert signs.get("REVENUE") == 1
    assert signs.get("COGS") == -1 and signs.get("SGA") == -1


def test_계정_분류를_플랫폼_말로_옮긴다():
    """`OPEX` 는 플랫폼에 없다 — `SGA` 다. 그대로 넣으면 등록이 거부된다."""
    store = FakeStore()
    kb.seed_plan_accounts(_rows("MDM-07"), store=store)
    assert {a["category"] for a in store.accounts.values()} <= {"REVENUE", "COGS", "SGA"}


def test_실패를_삼키지_않는다():
    class Broken(FakeStore):
        def upsert_account(self, **kw):
            raise ValueError("고장")
    out = kb.seed_plan_accounts(_rows("MDM-07"), store=Broken())
    assert out["loaded"] == [] and len(out["failed"]) > 0
    assert "고장" in out["failed"][0][1]


# ── 실제 키트로 재어 본다

def test_시나리오_열에_넷이_막힌다():
    """★★★ **키트가 주는 시나리오의 40% 가 플랫폼으로 넘어가지 않는다.**

    그리고 넘어가지 않는 것들이 하필 **경영 판단에 가장 가까운 것들**이다 —
    설비 정지 · 투자 결정 · 납기 지연. 숫자가 달라지면 이 시험이 알려 준다.
    """
    rows = _rows("SIM-02", "full")
    blocked = []
    for r in rows:
        try:
            kb.to_pct_change(r["change_value"], r["change_unit"])
        except kb.BridgeError:
            blocked.append(r["change_unit"])
    assert len(rows) == 10 and len(blocked) == 4
    assert sorted(blocked) == ["DAY", "HOUR", "KRW", "PERCENT_POINT"]


def test_사업이_달라도_같은_동인만_나온다():
    """★★★ **이음매에는 옮길 산업 특성이 없다.**

    제련·전지소재·조합 — 셋이 **완전히 같은 동인 11 개**를 준다. 키트의 동인이
    범용 제조업의 것이기 때문이다(환율·운임·수율·전력단가…). 제련수수료(TC/RC)도
    금속 회수율도 부산물 크레딧도 없다.

    ⚠️ 이 시험이 **깨지는 날**이 도메인 검토가 반영된 날이다
    (`docs/decisions/DOMAIN_REVIEW_KIT_2026-09-21.md` 1 장).
    """
    got = {}
    for kit in ("KIT-MFG-SMELTING-NONFERROUS", "KIT-MFG-BATTERY-MATERIALS",
                "KIT-MFG-NONFERROUS-PROCUREMENT"):
        path = os.path.join(REPO, "starter_kits", kit, "1.4.0", "samples", "full", "SIM-01.csv")
        with io.open(path, encoding="utf-8-sig", newline="") as f:
            fake = FakeDrivers()
            kb.seed_plan_drivers(list(csv.DictReader(f)), drivers=fake)
            got[kit] = sorted(fake.registered)
    values = list(got.values())
    assert values[0] == values[1] == values[2], f"사업별로 동인이 갈렸다: {got}"
    assert len(values[0]) == 11


# ── 실제 플랫폼 모듈과 맞물리는가 (서명만 본다)

def test_플랫폼_API_서명이_기대와_같다():
    """★ 대역(Fake)으로만 시험하면 **실제와 어긋난 채 초록불**이 된다."""
    import inspect
    from core import planning_drivers
    from core.planning_model import PlanningStore

    p = inspect.signature(planning_drivers.register_driver).parameters
    assert {"driver_code", "name", "unit", "category", "external_code", "note"} <= set(p)
    q = inspect.signature(PlanningStore.upsert_account).parameters
    assert {"account_code", "name", "category", "sign"} <= set(q)
