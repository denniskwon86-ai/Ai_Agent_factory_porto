# -*- coding: utf-8 -*-
"""[LE-01] Living Enterprise Canvas 읽기 모델.

## 이 파일이 존재하는 이유

승인 시안(2026-07-30 채택)과 매핑 문서는 처음부터 **단일 Read Model** 을 요구했는데
만들지 않았다. 그래서 화면이 여섯 군데를 긁어모아 조립했고, 시안의 **수주→손익 도메인
노드**를 줄 곳이 없어 **조직 트리로 대체**했다. 대체물이 굳어 「업무 흐름」이 부서
목록이 됐다.

여기서 고정하는 것:

  ① 중앙 축은 **조직도가 아니라 일곱 단계 가치사슬**이다
  ② 각 단계의 상태는 **인증판에서 나온다** — 짐작하지 않는다
  ③ 못 읽은 것을 「정상」으로 세지 않는다(`unknown`·`evidence_count: null`)
  ④ 시안 표본값(`수요 +3%`)을 **지어내지 않는다** — 근거 없으면 `primary_metric` 은 빈다
"""
import pytest

from core import enterprise_canvas as ec


def test_중앙_축은_수주에서_손익까지_일곱_단계다():
    """★★★ 승인 시안의 축. **조직도가 아니다.**

    ⚠️ 이 단언이 없으면 다음 사람이 다시 「줄 데이터가 없으니 조직 트리로」 한다."""
    labels = [n["label"] for n in ec.DOMAIN_NODES]
    assert labels == ['수주·판매', '원료조달', '생산계획', '제련·생산',
                      '품질', '물류·출하', '손익·경영'], labels
    #: 순번은 시안의 01~07 과 같아야 한다 — 화면이 그 숫자를 그린다.
    assert [n["sequence"] for n in ec.DOMAIN_NODES] == list(range(1, 8))
    #: ★ 각 단계에는 **근거가 될 계약키**가 있어야 한다. 없으면 상태를 짐작하게 된다.
    assert all(n["contract_keys"] for n in ec.DOMAIN_NODES)


def test_계약키가_업무_키트_정본에_실재한다():
    """⚠️ 계약키를 손으로 적었으므로 **오타가 곧 «자료 없음»** 이 된다.

    오타 난 키는 영영 인증되지 않고, 그 단계는 언제까지나 「막힘」으로 보인다 —
    그리고 아무 오류도 나지 않는다."""
    from core import demo_vertical_slice as dv

    known = set(dv.kit_dataset_keys())
    used = {k for n in ec.DOMAIN_NODES for k in n["contract_keys"]}
    assert used <= known, f"정본에 없는 계약키: {sorted(used - known)}"


def test_인증판을_못_읽으면_정상이_아니라_unknown(monkeypatch):
    """★★★ 「확인하지 못했다」를 「정상」으로 칠하지 않는다.

    ⚠️ 그렇게 칠하면 자료가 하나도 없는 회사의 첫 화면이 전부 초록으로 보인다."""
    got = ec._node_status(["SLS-01"], None, decisions=0)
    assert got["status"] == ec.UNKNOWN
    #: 0 이 아니라 `None` — 「0종 인증」과 「몇 종인지 못 셌다」는 다르다.
    assert got["evidence_count"] is None


def test_자료가_하나도_없으면_막힘이다():
    got = ec._node_status(["SLS-01", "MDM-03"], {}, decisions=0)
    assert got["status"] == ec.BLOCKED and got["evidence_count"] == 0
    assert got["reason"], "왜 막혔는지 말해야 한다"


def test_일부만_인증되면_확인_필요다():
    got = ec._node_status(["A", "B"], {"A": "certified"}, decisions=0)
    assert got["status"] == ec.ATTENTION and got["evidence_count"] == 1
    assert "2" in got["reason"] and "1" in got["reason"], got["reason"]


def test_전부_인증되면_정상이다():
    got = ec._node_status(["A", "B"], {"A": "certified", "B": "certified"}, decisions=0)
    assert got["status"] == ec.NORMAL and got["evidence_count"] == 2


def test_결정_대기가_있으면_그것이_먼저다():
    """★ 자료가 다 있어도 사람이 답할 것이 있으면 그 단계는 «결정 필요» 다.

    ⚠️ 순서를 뒤집으면 결정이 초록 뒤에 숨는다."""
    got = ec._node_status(["A"], {"A": "certified"}, decisions=2)
    assert got["status"] == ec.DECISION_REQUIRED and "2" in got["reason"]


def test_대표_지표를_지어내지_않는다(monkeypatch):
    """★★★ 채택 결정문: 「화면에 표시하는 수치·상태·추천은 **실제 API 근거가 있을 때만**
    노출한다.」

    시안 화면의 `수요 +3%`·`가동 94%` 는 `PROTOTYPE · SAMPLE DATA` 표기가 붙은 시안
    값이다. 근거가 생기기 전에는 비운다 — 그럴듯한 숫자가 한 번 화면에 뜨면 그것이
    실적으로 읽힌다."""
    monkeypatch.setattr(ec, "_now", lambda: "2026-08-24T00:00:00+00:00")
    got = ec.build(briefing={})
    assert len(got["domain_nodes"]) == 7
    assert all(n["primary_metric"] is None for n in got["domain_nodes"])
    #: ★ 시스템 이름이 **확인된 연결이 아니라는 것**을 응답이 스스로 말한다.
    assert got["systems_verified"] is False


def test_한_조각이_실패해도_전체를_죽이지_않는다(monkeypatch):
    """⚠️ 첫 화면이 한 조각 때문에 통째로 비면 사용자는 로그인이 깨진 줄 안다.

    ★ 대신 **무엇을 못 읽었는지** 남긴다 — 조용히 빠지는 것이 가장 위험하다."""
    def _boom(*a, **k):
        raise RuntimeError("저장소 열기 실패")

    import core.data_preparation.store as dp
    monkeypatch.setattr(dp.data_preparation_store, "transaction", _boom, raising=False)
    got = ec.build(briefing={})
    assert len(got["domain_nodes"]) == 7, "노드 골격은 남아야 한다"
    assert all(n["status"] == ec.UNKNOWN for n in got["domain_nodes"])
    assert got["unavailable"], "못 읽은 소스를 남기지 않았다"


def test_대기열은_네_섹션을_한_줄기로_모은다():
    """★ 사용자에게는 「결정」도 「막힘」도 **지금 처리할 일**이다. 성격은 `section` 으로
    구분해 화면이 갈라 보여 준다 — 응답에서 미리 나눠 버리면 화면이 다시 합쳐야 한다."""
    brief = {"sections": {
        "my_decisions": {"items": [{"title": "A"}]},
        "blocked": {"items": [{"title": "B"}]},
        "data_health": {"items": [{"title": "C"}]},
        "programs": {"items": [{"title": "D"}]},
    }}
    q = ec.build(briefing=brief)["decision_queue"]
    assert [i["title"] for i in q] == ["A", "B", "C", "D"]
    assert [i["section"] for i in q] == ["my_decisions", "blocked",
                                         "data_health", "programs"]
