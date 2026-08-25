"""★★★ Tech Lead → 계약 초안 → 컴파일. **끊겨 있던 칸.** (2026-08-25)

## ⚠️⚠️ 무엇이 끊겨 있었나 (사용자 실측)

> SW생성기 돌려보니까 자꾸 tech리드한테 지시 내리는 부분에서 계약이 생성되지 않아서
> 전달이 실패했다면서 진행이 안되던데

`nodes/contract.load_drafts()` 는 처음부터 있었는데 **쓰는 곳이 저장소 어디에도
없었다**(전수 확인: `contracts/drafts` 를 언급하는 코드는 읽기 쪽뿐이었다).
그래서 계약 컴파일러가 언제나 이렇게 답했다:

    계약 대상 태스크인데 계약 초안이 없습니다: T-1 — … Tech Lead 가 초안을 만들어야 합니다.

그리고 `route_from_contract_compiler` 가 「지문이 비었으면 게이트로 보내지 않는다」로
`TerminalHandler` 에 보냈다 — 파이프라인이 그 자리에서 끝났다.

★ 이 파일은 그 칸이 **다시 끊기지 않게** 못박는다.
"""
import json
import os

import pytest


# ── ① 쓰는 곳이 있는가 ───────────────────────────────────────────────────

def test_초안을_저장하는_함수가_있다():
    """⚠️ 「읽는 곳은 있는데 쓰는 곳이 없다」를 다시 만들지 않는다."""
    from nodes import contract as cn

    assert hasattr(cn, "save_draft"), "계약 초안을 저장하는 경로가 없다"


def test_저장하고_다시_읽는다(tmp_path):
    from nodes import contract as cn

    draft = {"app_class": "departmental", "datasets": [], "capability_intents": []}
    path = cn.save_draft(str(tmp_path), "T-1", draft)
    assert os.path.isfile(path)
    got = cn.load_drafts(str(tmp_path))
    assert got == {"T-1": draft}


@pytest.mark.parametrize("bad", [None, "문자열", 3])
def test_객체가_아니면_저장하지_않는다(tmp_path, bad):
    """⚠️ 깨진 것을 저장하면 `load_drafts` 가 「초안이 있다」로 읽고, 합산기는 그것을
    **데이터셋 0개**로 본다 — 「안 쓴 것」이 「안 쓰는 앱」이 된다."""
    from nodes import contract as cn

    with pytest.raises(TypeError):
        cn.save_draft(str(tmp_path), "T-1", bad)


def test_어느_태스크인지_없으면_거부한다(tmp_path):
    from nodes import contract as cn

    with pytest.raises(ValueError):
        cn.save_draft(str(tmp_path), "  ", {"datasets": []})


# ── ② Tech Lead 출력에서 뽑아내는가 ──────────────────────────────────────

BT = "`" * 3


def _spec(body: str, tag: str = "json contract-draft") -> str:
    return f"1-B. CONTRACT DRAFT\n{BT}{tag}\n{body}\n{BT}\n이후 내용"


@pytest.mark.parametrize("tag", ["json contract-draft", "contract-draft",
                                 "JSON contract-draft"])
def test_언어_태그가_달라도_찾는다(tag):
    """⚠️ 모델이 ```json / ```json contract-draft 중 무엇을 쓸지 강제할 수 없다.
    **못 찾는 것보다 넓게 찾는 편이 낫다** — 못 찾으면 파이프라인이 끝난다."""
    import nodes.execution as ex

    m = ex._DRAFT_BLOCK.search(_spec('{"app_class": "departmental"}', tag))
    assert m, f"«{tag}» 를 못 찾았다"
    assert json.loads(m.group(1))["app_class"] == "departmental"


def test_블록이_없으면_저장하지_않고_말한다(tmp_path, capsys):
    """★★★ 「1-B 를 안 냈다」와 「데이터를 안 쓴다」는 **다른 사실**이다.

    ⚠️ 여기서 빈 계약을 지어내면 뒤 칸이 «아무 데이터도 안 쓰는 앱» 을 정상으로
      컴파일하고, 그 계약은 승인 가능한 대상이 된다."""
    import nodes.execution as ex
    from nodes import contract as cn

    class _S:
        workspace_root = str(tmp_path)
        current_sprint_task_id = "T-1"

    ex._save_contract_draft(_S(), "계약 초안 블록이 전혀 없는 기술명세")
    assert cn.load_drafts(str(tmp_path)) == {}, "없는 초안을 지어냈다"
    out = capsys.readouterr().out
    assert "계약 초안 블록" in out, "조용히 넘어갔다 — 다음 칸에서 막히는데 이유를 알 수 없다"


def test_JSON_이_깨져도_명세를_되돌리지_않는다(tmp_path, capsys):
    """⚠️ 초안 실패가 기술명세를 통째로 무르면 사람은 명세를 다시 쓴다."""
    import nodes.execution as ex
    from nodes import contract as cn

    class _S:
        workspace_root = str(tmp_path)
        current_sprint_task_id = "T-1"

    ex._save_contract_draft(_S(), _spec('{"app_class": '))   # 닫히지 않은 JSON
    assert cn.load_drafts(str(tmp_path)) == {}
    assert "JSON" in capsys.readouterr().out


def test_실제로_저장된다(tmp_path, capsys):
    """★ 대조군 — 늘 막히기만 하면 그것은 기능이 아니다."""
    import nodes.execution as ex
    from nodes import contract as cn

    class _S:
        workspace_root = str(tmp_path)
        current_sprint_task_id = "T-1"

    body = json.dumps({
        "app_class": "departmental",
        "datasets": [{
            "name": "material_arrivals", "label": "원료 도입", "purpose": "도입 추적",
            "allowed_actions": ["read"],
            "fields": [{"name": "po_id", "type": "string", "required": False,
                        "classification": "INTERNAL"}],
            "data_role": "ENTERPRISE_ACTUAL", "source_intent": "ENTERPRISE_READ",
            "duplicate_entry_policy": "DENY_IF_AUTHORITATIVE_SOURCE_EXISTS",
            #: ⚠️ `ENTERPRISE_READ` 는 **어느 업무 데이터에서 오는지**를 요구한다.
            #:   없으면 컴파일이 막힌다 — 「원천을 특정하지 않으면 이 데이터는
            #:   만들어져도 읽히지 않습니다」. 표본을 내 말로 쓰다가 걸렸다.
            "enterprise_contract_key": "PRC-02",
        }],
        "capability_intents": [],
    }, ensure_ascii=False)
    ex._save_contract_draft(_S(), _spec(body))
    got = cn.load_drafts(str(tmp_path))
    assert list(got) == ["T-1"]
    assert got["T-1"]["datasets"][0]["name"] == "material_arrivals"
    assert "계약 초안 저장" in capsys.readouterr().out


# ── ③ 그 초안으로 **실제 계약이 컴파일되는가** ───────────────────────────

def test_초안이_있으면_계약이_컴파일된다():
    """★★★ **이 파일의 요지.** 초안 → 합산 → 계약 지문까지 실제로 나와야 한다.

    ⚠️ 종전에는 여기서 언제나 「초안이 없습니다」였고, 지문이 비어 파이프라인이 끝났다."""
    from core import project_contract_aggregator as agg

    tasks = [{"task_id": "T-1", "goal": "원료 도입 화면", "artifact_kind": "app"}]
    drafts = {"T-1": {
        "app_class": "departmental",
        "datasets": [{
            "name": "material_arrivals", "label": "원료 도입", "purpose": "도입 추적",
            "allowed_actions": ["read"],
            "fields": [{"name": "po_id", "type": "string", "required": False,
                        "classification": "INTERNAL"}],
            "data_role": "ENTERPRISE_ACTUAL", "source_intent": "ENTERPRISE_READ",
            "duplicate_entry_policy": "DENY_IF_AUTHORITATIVE_SOURCE_EXISTS",
            #: ⚠️ `ENTERPRISE_READ` 는 **어느 업무 데이터에서 오는지**를 요구한다.
            #:   없으면 컴파일이 막힌다 — 「원천을 특정하지 않으면 이 데이터는
            #:   만들어져도 읽히지 않습니다」. 표본을 내 말로 쓰다가 걸렸다.
            "enterprise_contract_key": "PRC-02",
        }],
        "capability_intents": [],
    }}
    result, a = agg.compile_project_contract(tasks, drafts, project_id="proj_x")
    assert not result.errors, result.errors
    assert result.contract.get("semantic_fingerprint"), "지문이 비었다 — 파이프라인이 끝난다"
    assert "T-1" in a.included_task_ids


def test_초안이_없으면_그_사유가_그대로_나온다():
    """★ 대조군 — 이 메시지가 사용자가 본 것이다. 사라지면 안 된다(원인이 안 보인다)."""
    from core import project_contract_aggregator as agg

    tasks = [{"task_id": "T-1", "goal": "원료 도입 화면", "artifact_kind": "app"}]
    result, _ = agg.compile_project_contract(tasks, {}, project_id="proj_x")
    assert result.errors
    assert any("계약 초안이 없습니다" in e for e in result.errors)
    assert not result.contract.get("semantic_fingerprint")
