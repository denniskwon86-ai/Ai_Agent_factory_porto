"""★★★ SW 생성기 **완주 걷기** — Tech Lead 에서 코드까지, 멈추는 자리를 전부 센다. (2026-08-26)

## ⚠️⚠️ 무엇을 확인하는가

사용자 실측: 「tech리드한테 전달하는 과정에서 … 생성 실패」. 앞선 회귀
(`test_sw_factory_walkthrough.py`)는 끊긴 **네 자리**를 개별로 못박았다. 그런데
칸마다 초록인 것과 **끝까지 걸어진다**는 것은 다른 사실이다 — 조각의 합이 100%
여도 관통이 0% 일 수 있다.

여기서는 **실제 그래프**를 컴파일해 실제 라우터·실제 계약 컴파일러·실제 상태
기계로 끝까지 걷는다. 대신 **`gateway.aexecute` 한 곳만** 막는다:

    · LLM 을 부르면 비용과 그날의 날씨에 따라 답이 달라져 회귀가 되지 못한다.
    · 막는 곳이 하나뿐이라 「제품 경로가 아니라 시험용 경로를 걸었다」가 되지 않는다.
      노드·라우터·컴파일러·체크포인터는 전부 제품의 그것이다.

## ⚠️ 대역이 계약을 대신 정의하지 않게 한다

대역이 **내 말로** 답하면 시험만 초록이고 제품은 안 돈다(이 저장소가 실제로 겪었다).
그래서 대역은 지어내지 않는다:

    · 심판 점수는 프롬프트가 **열거한 기준 id 를 읽어서** 채운다.
    · 계약 초안은 `test_sw_factory_walkthrough.py` 가 **실제 컴파일러로** 통과시킨 것과
      같은 모양을 쓴다.
    · 형식을 모르는 자리는 최소로 답하고 **진짜 파서가 불평하게 둔다** — 불평이 곧 발견이다.
"""
import asyncio
import json
import os
import re

import pytest


# ══════════════════════════════════════════════════════════════════════════
# LLM 대역 — 한 곳만 막는다
# ══════════════════════════════════════════════════════════════════════════

FENCE = "`" * 3

CONTRACT_DRAFT = {
    "app_class": "departmental",
    "datasets": [{
        "name": "material_arrivals", "label": "원료 도입", "purpose": "도입 추적",
        "allowed_actions": ["read"],
        "fields": [{"name": "po_id", "type": "string", "required": False,
                    "classification": "INTERNAL"}],
        "data_role": "ENTERPRISE_ACTUAL", "source_intent": "ENTERPRISE_READ",
        "duplicate_entry_policy": "DENY_IF_AUTHORITATIVE_SOURCE_EXISTS",
        "enterprise_contract_key": "PRC-02",
    }],
    "capability_intents": [],
}

TECH_SPEC = "\n".join([
    "## 1. 기술명세",
    "원료 도입 현황을 읽어 보여 주는 화면 하나를 만든다. 서버 API 없음.",
    "",
    "## 2. 파일별 책임",
    "- `src/App.tsx` — 도입 목록을 표로 그린다(FR-1).",
    "",
    "## 5. STATE_UPDATES",
    FENCE + "json",
    json.dumps({"file_index": {"src/App.tsx": "도입 목록 화면"}}, ensure_ascii=False),
    FENCE,
    "",
    FENCE + "json contract-draft",
    json.dumps(CONTRACT_DRAFT, ensure_ascii=False, indent=2),
    FENCE,
])

#: ⚠️ 키 이름을 **내가 정하지 않는다.** 정본은 `ContextEngine.get_strict_json_instruction()`
#:   이 모든 코딩 프롬프트 끝에 강제 주입하는 스키마 — `file_path` · `code` 다.
#:   처음에 `path`/`content` 로 썼더니 파일이 디스크에 하나도 안 남았고, 렌더 검증이
#:   「App 루트를 찾지 못했다」로 8회 반려했다. **제품이 아니라 대역이 틀린 것이었다.**
CODE_FILES = json.dumps({"files": [{
    "file_path": "src/App.tsx",
    "code": ("export default function App() {\n"
             "  return <main>원료 도입 목록</main>;\n"
             "}\n"),
}]}, ensure_ascii=False)


class Recorder:
    """대역이 **무엇을 요구받았는지** 남긴다 — 답을 못 만든 자리가 곧 끊긴 칸이다."""

    def __init__(self):
        self.calls = []
        self.unknown = []


def make_stub(rec: Recorder):
    from core.run_context import current_agent

    async def stub(state, skill_prompt, is_heavy=True, retry_count=0,
                   output_mode="code", light=False, full_file_exts=None,
                   cacheable=True, _call_id=""):
        agent = current_agent()
        p = str(skill_prompt)
        rec.calls.append((agent, output_mode, len(p)))

        #: ① 비평가 — 프롬프트가 요구하는 형식을 그대로 돌려준다(치명 결함 없음 = 합의).
        if '"verdict_blocking"' in p:
            return json.dumps({"checks": [], "verdict_blocking": False})

        #: ② 심판 — ★ 점수를 지어내지 않는다. **프롬프트가 열거한 기준 id** 를 읽어서 채운다.
        #:    내가 아는 id 를 쓰면 rubric 이 바뀌어도 시험은 계속 초록이다.
        if '"scores"' in p:
            ids = re.findall(r"^- ([^:\n]+):", p, re.MULTILINE)
            return json.dumps({"scores": {i.strip(): 1.0 for i in ids},
                               "rationale": "대역 채점(만점)"}, ensure_ascii=False)

        #: ③ 리뷰어 수용 판정 — 키 이름은 `nodes/execution.py` 의 **파서에서** 읽어 온다
        #:    (`data.get("decision")` · `data.get("feedback")`).
        #: ⚠️ 여기서 빈 `{}` 를 주면 파서가 **PASS 로 읽는다**(기본값). 그래서 대역이
        #:   판정을 명시한다 — 「대역이 침묵해서 통과했다」와 「통과 판정을 받았다」를
        #:   섞으면 이 걷기가 무엇을 증명했는지 알 수 없다.
        if agent == "Reviewer" and output_mode == "json":
            return json.dumps({"decision": "PASS", "feedback": ""}, ensure_ascii=False)

        #: ④ 코드 — 파일 스키마
        if output_mode == "code":
            return CODE_FILES

        #: ⑤ 문서 — 단계별
        if output_mode == "document":
            if agent == "Tech_Lead":
                return TECH_SPEC
            return "[" + agent + "] 대역 산출물."

        #: ⑥ 그 밖의 JSON — **지어내지 않는다.** 빈 객체를 주고 진짜 파서가 불평하게 둔다.
        rec.unknown.append((agent, p[:160]))
        return "{}"

    return stub


# ══════════════════════════════════════════════════════════════════════════
# 걷기
# ══════════════════════════════════════════════════════════════════════════

MAX_LEGS = 12          # 사람이 「계속」을 누르는 횟수 상한 — 무한 왕복을 시험이 떠안지 않는다


async def _walk(ws: str):
    """실제 그래프를 끝까지 걷는다. 멈출 때마다 **왜 멈췄는지**를 함께 모은다."""
    from core.agent_graph import create_factory_graph
    from nodes.contract import _wbs_tasks

    app = create_factory_graph()
    config = {"configurable": {"thread_id": "full-walk"}}

    first_payload = {
        "project_name": "완주점검",
        "workspace_root": ws,
        "factory_mode": "EXECUTION",
        "current_sprint_task_id": "T-1",
        "runtime_contract_profile": "v1",
        #: ★ 기획은 이미 끝난 자리에서 출발한다 — 이 시험이 보는 것은 **Tech Lead 이후**다.
        "architecture_summary": "단일 화면. 서버 API 없음.",
        #: ⚠️ 투입 명단을 여기 적지 않는다 — `_get_required_agents` 는 **WBS 태스크의
        #:   `required_agents`** 를 읽는다(없으면 기본 명단으로 떨어진다). 상태에 적으면
        #:   조용히 무시되고 기본값이 그 사실을 가린다. 명단은 `_wbs()` 에 있다.
    }

    trace, stops = [], []
    vals = {}
    payload = dict(first_payload)
    for _leg in range(MAX_LEGS):
        async for event in app.astream(payload, config=config):
            for node in event:
                trace.append(node)
        snap = await app.aget_state(config)
        vals = snap.values if isinstance(snap.values, dict) else {}
        nxt = list(snap.next or ())

        term = (vals.get("terminal_status") or "").strip()
        req = (vals.get("contract_review_request_event_id") or "").strip()

        if nxt:                                   # HOTL 중단점 — 사람이 「계속」을 누른다
            stops.append(("HOTL", "다음 " + str(nxt)))
            payload = None
            continue
        if req and not term:                      # 계약 승인 대기 — 사람이 승인한다
            stops.append(("계약승인대기", str(vals.get("app_runtime_contract_summary", ""))))
            #: ★★★ 승인을 **내 말로 흉내내지 않는다.** 제품이 승인할 때 실제로 하는 일을
            #:   그대로 부른다 — 흉내내면 「제품에는 없는 절차」가 시험 안에서만 성립하고,
            #:   바로 그것 때문에 승인 도장이 정본에 안 찍히는 결함이 숨어 있었다.
            from core import contract_review_gate as _gate
            from nodes.contract import stamp_approval

            gate_decision, _req_ids = _gate.evaluate_project(_wbs_tasks(ws), vals)
            note = stamp_approval(ws, fingerprint=gate_decision.compiled_fingerprint,
                                  actor_id="walk@example.invalid",
                                  ledger_event_id="dle_walk")
            assert not note, "승인을 계약 정본에 남기지 못했다: " + note
            upd = _gate.state_updates_for_approval(gate_decision)
            upd["contract_review_request_event_id"] = ""
            await app.aupdate_state(config, upd)
            #: ★★★ **`None` 으로 재개하지 않는다.** `ContractReviewPending` 은 `END` 로 끝나므로
            #:   이어서 돌 것이 남아 있지 않다 — 제품도 그렇게 설계돼 있고, 승인 화면이
            #:   「다시 가동하면 이 계약으로 이어서 만듭니다」라고 말하는 이유가 이것이다.
            #:   그래서 사람이 하는 그대로 **스프린트를 다시 가동**한다.
            payload = dict(first_payload)
            continue
        stops.append(("종료", term or "(종료 상태 없음)"))
        return trace, stops, vals

    stops.append(("걸음 상한", "%d 번 재개해도 끝나지 않았다" % MAX_LEGS))
    return trace, stops, vals


def _wbs(ws: str):
    with open(os.path.join(ws, "00_wbs_master_plan.json"), "w", encoding="utf-8") as f:
        json.dump({"tasks": [{
            "task_id": "T-1", "goal": "원료 도입 화면",
            "artifact_kind": "app", "scope": ["도입 목록"],
            #: ★ 「끝까지」의 끝은 매뉴얼이다. Supervisor 가 명단에 없으면 QA 에서
            #:   스프린트가 끝나(제품 동작) 수용검수·매뉴얼 칸을 한 번도 못 본다.
            "required_agents": ["Tech_Lead", "Frontend", "QA", "Supervisor"],
        }]}, f, ensure_ascii=False)


@pytest.fixture()
def walked(tmp_path, monkeypatch):
    """★ 한 번만 걷고 여러 시험이 나눠 본다 — 같은 걷기를 다섯 번 반복할 이유가 없다."""
    from core.llm_gateway import gateway

    ws = str(tmp_path / "ws")
    os.makedirs(ws, exist_ok=True)
    _wbs(ws)
    rec = Recorder()
    #: ⚠️ `from core.llm_gateway import gateway` 로 **이름을 가져간** 모듈이 많다.
    #:   모듈 속성을 갈아 끼우면 그 모듈들은 옛 객체를 계속 본다 — 그래서 **인스턴스의
    #:   메서드**를 바꾼다(모두가 같은 객체를 공유한다).
    monkeypatch.setattr(gateway, "aexecute", make_stub(rec), raising=True)
    trace, stops, vals = asyncio.run(_walk(ws))
    print("\n걸음: " + " → ".join(trace))
    print("멈춘 자리: " + json.dumps(stops, ensure_ascii=False))
    return {"trace": trace, "stops": stops, "vals": vals, "rec": rec, "ws": ws}


# ══════════════════════════════════════════════════════════════════════════
# 무엇을 단언하는가
# ══════════════════════════════════════════════════════════════════════════

def test_계약_컴파일과_승인_게이트를_지난다(walked):
    """★★★ 사용자가 막힌 바로 그 자리."""
    t = walked["trace"]
    assert "Tech_Lead" in t, "Tech Lead 가 돌지 않았다: %s" % t
    assert "HostContractCompiler" in t, "계약 컴파일러에 닿지 못했다: %s / %s" % (t, walked["stops"])
    assert "ContractReviewGate" in t, "승인 게이트에 닿지 못했다: %s / %s" % (t, walked["stops"])


def test_승인_뒤에_코드까지_간다(walked):
    """★★★ **완주의 요지** — 승인하면 실제로 코드를 만드는 자리까지 간다."""
    t = walked["trace"]
    assert "CodeBuilder" in t, (
        "승인했는데 코드 생성에 닿지 못했다.\n걸음: %s\n멈춘 자리: %s" % (t, walked["stops"]))


def test_매뉴얼까지_가서_끝난다(walked):
    """★★★ **완주의 정의.** 「코드가 나왔다」가 끝이 아니다 — 수용검수를 지나 사용자
    매뉴얼까지 나와야 사람이 받아 쓸 수 있는 앱이다."""
    t = walked["trace"]
    for node in ("Reviewer", "QA", "Supervisor", "ManualWriter"):
        assert node in t, "«%s» 를 지나지 못했다.\n걸음: %s\n멈춘 자리: %s" % (
            node, t, walked["stops"])


def test_사람이_멈추는_자리가_늘지_않았다(walked):
    """⚠️ 완주를 막는 것은 실패만이 아니다 — **말없이 늘어난 대기 자리**도 막는다.

    지금 사람이 개입하는 자리는 둘이고, 둘 다 그래야 할 이유가 있다:

        ① 계약 승인 — 검토 없이 권한이 DB 에 들어가면 안 된다
        ② 수용검수 뒤 HOTL — 사람이 결과를 받아 본다

    ★ 여기에 하나가 더 붙으면 **그 자리에 화면이 있는지**부터 확인해야 한다. 화면
      없이 멈추는 자리가 곧 「생성 실패」로 보이던 그 결함이다."""
    kinds = [k for k, _ in walked["stops"] if k != "종료"]
    assert kinds == ["계약승인대기", "HOTL"], (
        "사람이 멈추는 자리가 달라졌다: %s\n걸음: %s" % (walked["stops"], walked["trace"]))


def test_끝이_실패가_아니다(walked):
    """⚠️ 「끝났다」와 「완주했다」는 다르다. 종료 상태가 실패면 완주가 아니다."""
    term = (walked["vals"].get("terminal_status") or "").strip()
    assert term in ("", "COMPLETED"), (
        "실패로 끝났다: %s — %s\n걸음: %s" % (
            term, walked["vals"].get("terminal_reason", ""), walked["trace"]))


def test_대역이_모르는_출력계약이_없다(walked):
    """⚠️ 대역이 «모르겠다»로 답한 자리는 **형식이 문서화되지 않은 관문**이다.
    거기서 실제 LLM 이 헛디디면 사용자는 원인을 알 수 없다."""
    unknown = walked["rec"].unknown
    assert not unknown, "출력 형식을 알 수 없는 LLM 호출: " + json.dumps(
        unknown, ensure_ascii=False, indent=2)
