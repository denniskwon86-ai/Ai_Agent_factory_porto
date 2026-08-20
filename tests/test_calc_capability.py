"""★★★ 계산 **Capability Registry** 를 검증한다. (§7 5a)

## 이 파일이 지키는 것

    ① 계약이 요구하는 CALC.* 를 **하나도 빠뜨리지 않는다**
    ② 모르는 참조는 fail-closed
    ③ `NOT_IMPLEMENTED` 는 실행되지 않는다
    ④ 기존 `calc_graph` 로 **암묵적으로 새지 않는다**
    ⑤ 범위 밖(FINANCE)의 상태가 **명시**돼 있다
    ⑥ 단위·낟알·부호가 어휘로 고정돼 있다
    ⑦ 지문이 바뀌면 옛 실행 증명이 무효가 된다
    ⑧ 차단이 **존재나 개수를 누설하지 않는다**

⚠️⚠️ 이 파일은 「계산이 된다」를 증명하지 않는다. 지금은 넷 다 막혀 있고, **막혀
  있다는 사실**을 증명한다. 5a 완료는 「계산 연동 완료」가 아니다.
"""
import json
import re
from pathlib import Path

import pytest

from core import calc_capability as cc

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "architecture" / "g2_first_vertical_ontology_contract_v1.json"


# ── ① 계약과 레지스트리가 어긋나지 않는다 ──────────────────────────────

def _contract_refs():
    if not CONTRACT.exists():                       # pragma: no cover - 계약 파일 없음
        pytest.skip("계약 파일이 없습니다")
    raw = CONTRACT.read_text(encoding="utf-8")
    return set(re.findall(r"CALC\.[A-Z_.0-9v]+", raw))


def test_계약이_요구하는_참조를_하나도_빠뜨리지_않는다():
    """★★★ **누락 검출.** 계약에 있는데 레지스트리에 없으면, 그 계산은 아무도
    「없다」고 말해 주지 않은 채 조용히 지나간다.

    ⚠️ 실제로 §7-0 에서 내가 셋만 셌다 — 최소 경로에서 보이는 것만 봤기 때문이다.
      계약 **원문**을 훑어야 넷이 나온다."""
    missing = _contract_refs() - set(cc.known_refs())
    assert not missing, f"계약에 있는데 등록되지 않았다: {sorted(missing)}"


def test_계약에_없는_것을_지어내지_않는다():
    """⚠️ 반대쪽도 본다 — 없는 능력을 등록하면 화면이 있지도 않은 계산을 약속한다."""
    extra = set(cc.known_refs()) - _contract_refs()
    assert not extra, f"계약에 없는데 등록됐다: {sorted(extra)}"


def test_넷이고_그중_셋이_MVP_다():
    assert len(cc.known_refs()) == 4, cc.known_refs()
    assert len(cc.mvp_refs()) == 3, cc.mvp_refs()


# ── ② 모르는 참조는 fail-closed ────────────────────────────────────────

@pytest.mark.parametrize("ref", ["", "   ", "CALC.UNKNOWN.THING.v1", "calc.logistics",
                                 "CALC.LOGISTICS.ARRIVAL_DELAY.v2", None])
def test_모르는_참조는_거부한다(ref):
    """⚠️ `None` 을 돌려주면 호출부가 「없으니 건너뛰자」로 접는다 — 그러면 계약에
    없는 계산이 조용히 지나간다."""
    with pytest.raises(cc.CapabilityError):
        cc.get(ref)
    with pytest.raises(cc.CapabilityError):
        cc.assert_executable(ref)


def test_판이_다르면_다른_참조다():
    """★ `v1` 과 `v2` 는 다른 계약이다 — 산식이 바뀌면 판이 올라간다."""
    assert cc.get("CALC.LOGISTICS.ARRIVAL_DELAY.v1")
    with pytest.raises(cc.CapabilityError):
        cc.get("CALC.LOGISTICS.ARRIVAL_DELAY.v2")


# ── ③ NOT_IMPLEMENTED 는 실행되지 않는다 ───────────────────────────────

@pytest.mark.parametrize("ref", cc.known_refs())
def test_지금은_아무것도_실행할_수_없다(ref):
    """★★★ 넷 다 막혀 있다. **이것이 지금의 사실**이고, 시험이 그것을 못 박는다.

    ⚠️ 나중에 하나가 열리면 이 시험이 빨강이 된다 — 그때 「무엇을 근거로 열었는가」를
      함께 적으라는 뜻이다. 조용히 열리지 않게."""
    cap = cc.get(ref)
    assert not cap.executable, f"{ref} 이 승인 없이 실행 가능해졌다"
    with pytest.raises(cc.CapabilityError) as err:
        cc.assert_executable(ref)
    #: ★ 사유가 붙어야 사람이 무엇을 해야 할지 안다.
    assert cap.state in str(err.value)
    assert cap.blocked_reason and cap.blocked_reason in str(err.value)


def test_실행_가능한_상태는_하나뿐이다():
    """⚠️ 이 집합을 넓히는 것은 **승인 없는 계산을 하나 허용하는 일**이다."""
    assert cc.EXECUTABLE == {cc.APPROVED}


def test_사유_없는_차단은_만들_수_없다():
    """⚠️ 사유 없는 차단은 「왜 막혔지?」에 답할 수 없고, 그러면 아무도 되돌리지 못한다."""
    with pytest.raises(ValueError):
        cc.Capability(ref="X", subject_type="a", relation="AFFECTS", object_type="b",
                      required_datasets=(), outputs=(), state=cc.NOT_IMPLEMENTED)


def test_승인_원장_없이_APPROVED_가_될_수_없다():
    """★★★ 승인 원장 없는 `APPROVED` 는 **누가 승인했는지 없는 승인**이다."""
    with pytest.raises(ValueError):
        cc.Capability(ref="X", subject_type="a", relation="AFFECTS", object_type="b",
                      required_datasets=(), outputs=(), state=cc.APPROVED,
                      model_version="1.0.0")
    with pytest.raises(ValueError):
        cc.Capability(ref="X", subject_type="a", relation="AFFECTS", object_type="b",
                      required_datasets=(), outputs=(), state=cc.APPROVED,
                      ledger_event_id="ev_1")      # 산식 판이 없다


# ── ④ 기존 엔진으로 암묵적으로 새지 않는다 ─────────────────────────────

def test_기존_calc_graph_로_흘러가지_않는다():
    """★★★ **암묵적 fallback 차단.**

    ⚠️⚠️ 「일단 기존 엔진으로라도 숫자를 내자」가 가장 위험하다. 기존 엔진은 재고를
      **반대 방향**으로 계산하므로(지연 ↑ → 재고 ↑), 그 숫자를 본 사람은 「여유가
      있다」고 읽고 실제로는 라인이 선다.
    ★ 그래서 레지스트리는 `calc_graph` 를 **부르지도, 알지도 못한다.**"""
    #: ⚠️ 첫 판은 원본에 «calc_graph» 라는 **글자**가 있는지 봤다. 그래서 「왜 안
    #:   쓰는가」를 설명하는 docstring 이 걸렸다. 설명은 남을 값어치가 있고, 막아야
    #:   하는 것은 **부르는 것**이다.
    #: ★ 그래서 산문이 아니라 **구문 나무**를 본다 — 주석·문자열은 여기 안 잡힌다.
    import ast

    tree = ast.parse(Path(cc.__file__).read_text(encoding="utf-8"))
    imported, called = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Attribute):
            called.add(node.attr)
        elif isinstance(node, ast.Name):
            called.add(node.id)
    for forbidden in ("calc_graph", "planning_engine", "planning_drivers"):
        assert not any(forbidden in name for name in imported), (
            f"레지스트리가 «{forbidden}» 를 부른다: {sorted(imported)}")
        assert forbidden not in called, f"레지스트리가 «{forbidden}» 를 참조한다"
    for forbidden in ("simulate", "run_scenario", "compute_pl"):
        assert forbidden not in called, f"레지스트리가 «{forbidden}» 를 부른다"


def test_실행_거부는_숫자를_돌려주지_않는다():
    """⚠️ 0 이나 빈 결과로 접으면 「계산이 안 됐다」가 「영향이 없다」로 보인다."""
    for ref in cc.known_refs():
        try:
            out = cc.assert_executable(ref)
        except cc.CapabilityError:
            continue
        pytest.fail(f"{ref} 이 값을 돌려줬다: {out!r}")


# ── ⑤ 범위 밖이 명시돼 있다 ────────────────────────────────────────────

def test_재무_참조는_범위_밖으로_명시된다():
    """★★★ **「빠뜨린 것」과 「범위 밖」은 다르다.**

    ⚠️ 안 적으면 다음 사람이 「원래 안 보던 건가」와 「보다가 놓친 건가」를 구별하지
      못하고, 둘 중 하나를 골라 잘못 행동한다."""
    cap = cc.get("CALC.FINANCE.COST_MARGIN_CASH.v1")
    assert cap.state == cc.OUT_OF_SCOPE
    assert cap.mvp_scope is False
    assert "범위 밖" in cap.blocked_reason


def test_MVP_셋은_범위_안이고_미구현이다():
    for ref in cc.mvp_refs():
        cap = cc.get(ref)
        assert cap.mvp_scope is True
        assert cap.state == cc.NOT_IMPLEMENTED, f"{ref}: {cap.state}"


# ── ⑥ 단위·낟알·부호가 고정돼 있다 ─────────────────────────────────────

@pytest.mark.parametrize("ref", cc.known_refs())
def test_출력에_단위와_부호_방향이_붙어_있다(ref):
    """★★★ 부호 방향을 안 적으면 「재고 +230」이 좋은 소식인지 나쁜 소식인지 두
    사람이 다르게 읽는다.

    ⚠️ 단위도 같다 — 「+10」이 퍼센트인지 절대값인지 안 적으면 두 배 틀린다."""
    cap = cc.get(ref)
    assert cap.outputs, f"{ref}: 출력이 없다"
    for name, unit, direction in cap.outputs:
        #: ★★★ [2026-08-21] **계약 안에서는 코드를 쓴다.** 「일」·「원」을 계약에 적으면
        #:   그 문자열이 비교에 쓰이고, 표기를 다듬는 순간 판정이 조용히 바뀐다.
        assert unit in cc.UNITS, f"{ref}.{name}: 단위가 코드가 아니다 — {unit!r}"
        assert direction in cc.DIRECTIONS, (
            f"{ref}.{name}: 부호 방향이 코드가 아니다 — {direction!r}")
        assert name, f"{ref}: 지표 이름이 없다"


def test_한글_단위는_화면_표시명으로만_쓴다():
    """★ 사람이 읽을 이름은 따로 둔다 — 계약과 화면을 한 문자열로 묶으면 둘 다 못 고친다.

    ⚠️⚠️ 첫 판은 `unit in cc.UNITS` 만 봤다. `UNITS` 가 **같은 상수에서 파생**되므로
      단위를 한글로 되돌리는 변이가 그대로 살아남았다 — 값을 **자기 자신과 비교**한
      것이다. 그래서 여기서는 **글자 그대로** 못 박는다."""
    assert cc.UNITS == ("TON", "DAY", "KRW"), cc.UNITS
    assert (cc.UNIT_TON, cc.UNIT_DAY, cc.UNIT_KRW) == ("TON", "DAY", "KRW")
    assert cc.DIRECTIONS == ("UP", "DOWN")
    assert set(cc.UNIT_DISPLAY) == set(cc.UNITS)
    for ref in cc.known_refs():
        for _, unit, _ in cc.get(ref).outputs:
            #: ⚠️ 계약 값에 한글이 섞이면 즉시 잡는다.
            assert unit.isascii(), f"{ref}: 단위에 한글이 섞였다 — {unit!r}"
            assert cc.UNIT_DISPLAY[unit]


@pytest.mark.parametrize("ref", cc.mvp_refs())
def test_입력_계약키가_붙어_있다(ref):
    """⚠️ 어느 인증판을 봐야 하는지 없으면, 나중에 아무 판으로나 계산할 수 있다."""
    cap = cc.get(ref)
    assert cap.required_datasets, f"{ref}: 입력 계약키가 없다"
    assert all(re.fullmatch(r"[A-Z]{3}-\d{2}", k) for k in cap.required_datasets), (
        f"{ref}: 계약키 모양이 아니다 {cap.required_datasets}")


def test_같은_지표_어휘를_쓴다():
    """★ §5-0 §2 에서 확정한 여섯 지표 밖의 이름을 쓰지 않는다 — 어휘가 갈라지면
    같은 것을 두 이름으로 부르게 된다."""
    allowed = {"available_qty", "in_transit_qty", "shortage_qty", "producible_qty",
               "revenue_shift_days", "margin_delta", "cash_delta"}
    for ref in cc.known_refs():
        for name, _, _ in cc.get(ref).outputs:
            assert name in allowed, f"{ref}: 어휘 밖의 지표 {name!r}"


# ── ⑦ 지문이 바뀌면 옛 증명이 무효다 ───────────────────────────────────

def test_능력_지문은_결정론적이다():
    a = cc.get("CALC.LOGISTICS.ARRIVAL_DELAY.v1").fingerprint()
    b = cc.get("CALC.LOGISTICS.ARRIVAL_DELAY.v1").fingerprint()
    assert a == b and len(a) == 64


def test_계약이_바뀌면_지문이_바뀐다():
    """★★★ 실행 증명이 이 값을 함께 실으므로, 산식이 바뀌면 **옛 증명이 스스로
    무효**임을 드러낸다. 「같은 판인데 다른 답」을 막는 축이다."""
    base = cc.get("CALC.LOGISTICS.ARRIVAL_DELAY.v1")
    for change in ({"model_version": "1.0.1"},
                   {"required_datasets": ("LOG-02",)},
                   {"outputs": (("available_qty", "KG", "내린다"),)},
                   {"state": cc.IMPLEMENTED_UNAPPROVED},
                   {"effective_from": "2026-09-01"}):
        kw = {**base.__dict__, **change}
        kw.setdefault("blocked_reason", base.blocked_reason or "사유")
        moved = cc.Capability(**kw)
        assert moved.fingerprint() != base.fingerprint(), f"{change} 가 지문을 안 바꿨다"


def test_레지스트리_지문이_전체를_덮는다():
    fp = cc.registry_fingerprint()
    assert len(fp) == 64
    assert fp == cc.registry_fingerprint()
    #: ★ 개별 지문이 전부 들어가야 한다 — 하나가 빠지면 그 항목이 조용히 바뀔 수 있다.
    joined = "".join(cc.get(r).fingerprint() for r in cc.known_refs())
    assert len(set(joined)) > 1


# ── ⑧ 차단이 존재나 개수를 누설하지 않는다 ─────────────────────────────

def test_거부_메시지가_업무_내용을_누설하지_않는다():
    """★★★ 차단 사유는 **우리 쪽 미완성**을 말할 뿐, 자료의 존재·개수를 말하지 않는다.

    ⚠️ 「관계 3건이 막혔습니다」 같은 문구는 **관계가 3건 있다는 사실**을 알려 준다.
      권한이 없는 사람에게 그것은 이미 정보다."""
    for ref in cc.known_refs():
        cap = cc.get(ref)
        text = cap.blocked_reason
        assert not re.search(r"\d+\s*건", text), f"{ref}: 개수를 누설한다 — {text}"
        for leak in ("SHP-", "STK-", "PO-", "MPS-", "SO-", "tenant-", "plant-", "ds_"):
            assert leak not in text, f"{ref}: 식별자를 누설한다 — {text}"


def test_보고는_계약_정보만_담는다():
    """★ `report()` 는 화면이 그대로 보여 주는 값이다 — 업무 자료가 새면 안 된다."""
    body = json.dumps(cc.report(), ensure_ascii=False)
    for leak in ("SHP-", "STK-", "MPS-", "SO-0", "tenant-afs", "plant-afs", "ds_"):
        assert leak not in body, f"보고가 «{leak}» 를 누설한다"


def test_보고가_무엇이_왜_막혔는지_말한다():
    """⚠️ 「왜 숫자가 없나」에 답할 수 없으면 사람은 화면을 믿지 못하거나, 더 나쁘게는
    없는 것을 «영향 없음» 으로 읽는다."""
    rep = cc.report()
    assert set(rep) == set(cc.known_refs())
    for ref, item in rep.items():
        assert item["executable"] is False
        assert item["blocked_reason"]
        assert item["relation"] and "->" in item["relation"]
        assert item["fingerprint"]


# ══════════════════════════════════════════════════════════════════════════
# 5-0 감사 보정 (2026-08-21) — 낟알·데이터셋·승인 재검증
# ══════════════════════════════════════════════════════════════════════════

def test_부족량_계산에_BOM_이_필요하다():
    """★★★ [감사 ②③] **낟알이 맞지 않는다.**

    `INV-01` 은 자재×창고×일자인데 `MFG-01.material_requirement` 는 여러 BOM 투입을
    합친 **계획행 총량**이다. 단일 자재 재고와 바로 뺄 수 없다.

    ⚠️ BOM 없이 빼면 「부족 66톤」 같은 숫자가 나오는데, 그것은 **어느 자재의 부족도
      아니다.** 단위는 톤이고 계산은 되고 아무도 못 알아챈다."""
    cap = cc.get("CALC.INVENTORY.MATERIAL_SHORTAGE.v1")
    assert "MDM-05" in cap.required_datasets, cap.required_datasets
    assert {"INV-01", "MFG-01"} <= set(cap.required_datasets)


def test_운송_중_판정에_실제_도착_사건이_필요하다():
    """★★★ [감사 ④] `eta` 는 **예정** 시점이다.

    ⚠️ 실측: `LOG-02.status` 는 120건 **전부 DELIVERED** 이고 실제 도착은 `LOG-03` 의
      `ATA` 사건에만 있다. 예정으로 판정하면 **이미 도착한 배를 «운송 중»** 으로 센다."""
    cap = cc.get("CALC.LOGISTICS.ARRIVAL_DELAY.v1")
    assert "LOG-03" in cap.required_datasets, cap.required_datasets


def test_매출_이연과_납기_지연_실적을_섞지_않는다():
    """★★★ [감사 ⑤] `actual_ship_date − due_date` 는 **이미 일어난 실적**이다.

    ⚠️ 그것을 「시뮬레이션 결과」로 내보내면, 화면은 예측이라며 **과거를 보여 준다.**
    ★ `revenue_shift_days` 는 시나리오와 **기준선**의 예상 인식일 차이다."""
    cap = cc.get("CALC.PRODUCTION.REVENUE_TIMING.v1")
    names = {n for n, _, _ in cap.outputs}
    assert "revenue_shift_days" in names
    assert "delivery_delay_days" not in names, (
        "실적 지연을 시뮬레이션 출력으로 내보내고 있다")
    assert "기준선" in cap.blocked_reason


def test_범위_변경이_지문을_바꾼다():
    """★★★ [감사 ⑦] `mvp_scope` 를 지문에서 빼면 「범위 밖이던 것을 안으로 옮긴」
    변경이 **옛 실행 증명을 그대로 유효하게** 만든다."""
    base = cc.get("CALC.FINANCE.COST_MARGIN_CASH.v1")
    moved = cc.Capability(**{**base.__dict__, "mvp_scope": True})
    assert moved.fingerprint() != base.fingerprint()


def test_승인_이벤트가_바뀌면_지문이_바뀐다():
    """⚠️ 승인 이벤트가 다른 것은 **다른 승인**이다."""
    base = cc.get("CALC.LOGISTICS.ARRIVAL_DELAY.v1")
    other = cc.Capability(**{**base.__dict__, "ledger_event_id": "ev_다른것"})
    assert other.fingerprint() != base.fingerprint()


def _approved(ref="CALC.LOGISTICS.ARRIVAL_DELAY.v1"):
    """승인된 능력 하나(시험용). ⚠️ 등록부는 건드리지 않는다."""
    base = cc.get(ref)
    return cc.Capability(**{**base.__dict__, "state": cc.APPROVED,
                            "model_version": "1.0.0", "ledger_event_id": "ev_1",
                            "blocked_reason": ""})


def test_승인은_실행할_때마다_원장에서_다시_확인한다(monkeypatch):
    """★★★ [감사 ⑦] 등록부의 상태는 «그때 그랬다» 이지 «지금도 그렇다» 가 아니다.

    ⚠️⚠️ 승인은 **철회될 수 있고**, 철회는 등록부를 고치지 않는다. 다시 안 보면
      철회된 승인으로 계산이 계속 돈다."""
    cap = _approved()
    monkeypatch.setitem(cc._REGISTRY, cap.ref, cap)

    #: ① 검증기가 없으면 실행하지 않는다 — 「안 넘겼으니 통과」는 문을 통째로 여는 것이다.
    with pytest.raises(cc.CapabilityError) as no_verifier:
        cc.assert_executable(cap.ref)
    #: ⚠️⚠️ 사유를 **구체적으로** 본다. 첫 판은 «원장» 이라는 낱말만 봤는데, 가드를
    #:   지워도 `None(cap)` 이 `TypeError` 를 내고 그것이 「원장을 확인하지 못했습니다」로
    #:   잡혀서 **변이가 살아남았다** — 우연히 같은 낱말이 들어 있었을 뿐이다.
    assert "확인할 방법 없이" in str(no_verifier.value), no_verifier.value

    #: ② 철회됐으면 막는다.
    with pytest.raises(cc.CapabilityError) as revoked:
        cc.assert_executable(cap.ref, lambda c: False)
    assert "확인되지 않았" in str(revoked.value)

    #: ③ 원장을 못 읽으면 **장애**다 — 「승인 없음」으로 접지 않는다.
    def boom(_c):
        raise RuntimeError("원장이 응답하지 않습니다")

    with pytest.raises(cc.CapabilityError) as broken:
        cc.assert_executable(cap.ref, boom)
    assert "확인하지 못했" in str(broken.value)

    #: ④ 대조군 — 확인되면 통과한다. 늘 막히면 통제가 아니라 고장이다.
    assert cc.assert_executable(cap.ref, lambda c: True).ref == cap.ref


def test_검증기는_능력을_받아_대상을_확인할_수_있다(monkeypatch):
    """★ 검증기가 **무엇을 승인했는지** 볼 수 있어야 한다 — 대상이 다른 승인을
    재사용하는 것이 이 저장소에서 실제로 났던 사고다."""
    cap = _approved()
    monkeypatch.setitem(cc._REGISTRY, cap.ref, cap)
    seen = []
    cc.assert_executable(cap.ref, lambda c: seen.append(c) or True)
    assert seen and seen[0].ref == cap.ref
    assert seen[0].ledger_event_id == "ev_1"
