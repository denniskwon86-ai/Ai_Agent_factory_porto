# ==========================================
# 한 번의 «논리적 호출» 을 관통하는 call_id (2026-08-07)
#
# ## 왜 id 를 심는가 — 추론이 세 번 틀렸기 때문이다
#
# 게이트웨이는 실패하면 `pro(retry0)` + `flash(retry1)` 로 **2줄**을, 성공하면 **1줄**을 남긴다.
# 줄 수로 성공률을 내면 실패한 호출만 분모를 두 배로 키운다(Master_PMO 12.5% → 화면 6.7%).
#
# 로그만으로 되묶으려는 시도는 전부 깨졌다:
#   - `retry_count==0` 만 세기 → 재시도로 **살아난** 호출이 실패로 남는다(실제 로그 5건)
#   - 순서로 묶기 → 동시 실행이라 로그가 교차한다(직전이 rc-1 이 아닌 기록 11건)
# → 그래서 게이트웨이가 재귀할 때 **같은 id 를 물려준다.** 집계는 추론하지 않는다.
#
# ⚠️⚠️ 이 배선은 **조용히 깨진다.** 재귀 지점을 하나만 새로 추가하고 `_call_id` 를 빠뜨리면
#   그 경로의 호출만 별개로 세어지고, 아무도 눈치채지 못한 채 성공률이 다시 낮아진다.
#   그래서 「전달했는지」를 눈으로 보지 않고 AST 로 못박는다.
# ==========================================
import ast
import inspect
import json
import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.llm_gateway as gw


def _aexecute_ast():
    # ⚠️ `inspect.cleandoc` 는 첫 줄만 다르게 다뤄 메서드 본문을 깨뜨린다 — dedent 를 쓴다.
    return ast.parse(textwrap.dedent(inspect.getsource(gw.LLMGateway.aexecute)))


# ── ① 모든 재귀 지점이 id 를 물려준다 ───────────────────────────────────────
def test_every_recursive_call_passes_the_same_call_id():
    """★★★ 재귀 지점이 하나라도 id 를 빠뜨리면 그 경로만 «새 호출» 이 된다.

    현재 3곳이다: 429 크로스티어 우회 / 429 Flash 대기 재시도 / 알 수 없는 오류 우회."""
    tree = _aexecute_ast()
    sites = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "aexecute"]
    assert sites, "재귀 지점을 찾지 못했다 — 이 테스트가 무력화됐다"
    for i, call in enumerate(sites):
        kwargs = {k.arg for k in call.keywords}
        assert "_call_id" in kwargs, (
            f"{i + 1}번째 재귀 호출이 `_call_id` 를 물려주지 않는다 — "
            f"이 경로의 재시도는 별개 호출로 세어져 성공률이 다시 낮아진다")


def test_every_log_write_carries_the_call_id():
    """★★ 로그 기록 지점도 마찬가지 — 하나라도 빠지면 그 줄은 접히지 않는다.

    현재 3곳이다: 캐시 히트 / 성공 / 실패."""
    tree = _aexecute_ast()
    logs = [n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == "_log_llm_call"]
    assert logs, "로그 기록 지점을 찾지 못했다"
    for i, call in enumerate(logs):
        assert "call_id" in {k.arg for k in call.keywords}, \
            f"{i + 1}번째 로그 기록이 `call_id` 없이 남는다"


# ── ② 첫 진입에서만 발급하고, 물려받으면 그대로 쓴다 ────────────────────────
def test_signature_defaults_to_empty_so_callers_do_not_pass_it():
    """`_call_id` 는 **내부 전용**이다. 호출부(노드)가 신경 쓸 일이 아니다."""
    sig = inspect.signature(gw.LLMGateway.aexecute)
    assert sig.parameters["_call_id"].default == ""


def test_new_id_is_minted_only_when_absent():
    """★ 물려받은 id 를 덮어쓰면 체인이 끊어져 결함이 되살아난다."""
    src = inspect.getsource(gw.LLMGateway.aexecute)
    assert "_call_id = _call_id or " in src, \
        "물려받은 id 보다 새 id 를 우선하면 재시도가 다시 별개 호출이 된다"


# ── ③ 기록에 실제로 들어간다 ────────────────────────────────────────────────
def test_call_id_is_written_to_the_log_record(tmp_path, monkeypatch):
    """★★ 배선이 맞아도 필드가 안 실리면 집계는 여전히 못 묶는다."""
    log = tmp_path / "llm_call_log.jsonl"
    monkeypatch.setattr(gw, "_LLM_CALL_LOG_PATH", str(log))
    monkeypatch.chdir(tmp_path)   # `_log_llm_call` 이 makedirs("data") 를 한다

    class _S:
        project_name, workspace_root, owner_dept_id, current_stage = "p", "", "", "PMO"

    gw._log_llm_call(_S(), "pro_router", "json", 0, ["m1"], False, 1.0, call_id="abc123")
    rec = json.loads(log.read_text(encoding="utf-8").strip())
    assert rec["call_id"] == "abc123"


def test_missing_call_id_is_empty_string_not_absent(tmp_path, monkeypatch):
    """⚠️ 필드가 아예 없으면 소비자가 `KeyError` 로 죽는다 — 계측이 본체를 죽이는 그 실수다
    (2026-07-29 `FallbackErrorCollector` 사고와 같은 종류)."""
    log = tmp_path / "llm_call_log.jsonl"
    monkeypatch.setattr(gw, "_LLM_CALL_LOG_PATH", str(log))
    monkeypatch.chdir(tmp_path)

    class _S:
        project_name, workspace_root, owner_dept_id, current_stage = "p", "", "", ""

    gw._log_llm_call(_S(), "pro_router", "json", 0, [], False, 0.0)
    rec = json.loads(log.read_text(encoding="utf-8").strip())
    assert rec["call_id"] == ""
