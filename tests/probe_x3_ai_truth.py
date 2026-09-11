"""[X-3] §9.3 「AI 에게 진실을 맡기기」를 **일으키려는** 탐침.

## 계획이 말한 세 경로 (§6 X-3)

    ① LLM 이 제안한 «식별자·매핑» 이 대조 없이 저장되는 곳
    ② LLM 이 만든 «숫자» 가 계산 입력으로 바로 들어가는 곳
    ③ LLM 이 만든 «코드» 가 운영 프로세스에서 바로 실행되는 곳

    수용 기준: 세 경로가 **전부 막혀 있고**, 막는 것이 **결정론적 검증기**다.

★★★ 「결정론적」이 조건인 이유: LLM 에게 「지어내지 마라」고 지시하는 것은 **차단기가
  아니다.** 같은 프롬프트가 다음에 다른 답을 낼 수 있고, 그때 아무도 모른다.
  대조표가 있고 그 표에 없으면 거부되는 구조여야 한다.

## ⚠️ 이 탐침은 LLM 을 부르지 않는다

**LLM 출력을 «흉내» 낸다** — 지어낸 기관 키, 없는 원천 id, 내부 ID 가 섞인 사람용 칸,
규약 밖 가정 키. 진짜 LLM 을 부르면 (a) 쿼터를 쓰고 (b) 매번 다른 것이 나와
**재현되지 않는 시험**이 된다. 막히는지 보려는 것이지 LLM 을 평가하려는 것이 아니다.

## 운영 DB 에 쓰지 않는다

전부 순수 함수 또는 읽기다. 쓰기가 필요한 항목은 «쓰기 직전에 거부되는지»를 보므로
성공하면 애초에 쓰이지 않는다. ③ 은 **소스 트리를 세는** 정적 조사다.
"""
from __future__ import annotations

import io
import os
import re
import sys
import traceback
from typing import Any, Callable, List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

REPORT = os.path.join(PROJECT_ROOT, "docs", "test_plan", "X3_FINDINGS.md")

BLOCKED = "막힘"
REFUSED = "거부 응답"
LEAKED = "샘"
ERROR = "탐침 오류"
PASSING = (BLOCKED, REFUSED)

#: ③ 이 훑는 범위. **운영 프로세스**가 여기다 — `docs/`·`projects/`·`tests/` 는 아니다.
RUNTIME_DIRS = ("core", "api")
#: 실행 창구. `compile()` 은 정규식에도 쓰이므로 «동적 실행» 만 골라야 한다.
EXEC_SHAPES = (
    (re.compile(r"\bsubprocess\s*\.\s*(run|call|check_output|check_call|Popen)"), "subprocess 실행"),
    (re.compile(r"\bos\s*\.\s*(system|popen|exec[lv])"), "os 실행"),
    (re.compile(r"(?<![.\w])exec\s*\("), "exec()"),
    (re.compile(r"(?<![.\w])eval\s*\("), "eval()"),
    (re.compile(r"\brunpy\b"), "runpy"),
)
#: ★ 이것만은 예외다 — 인자가 «고정 리터럴»이고 LLM 이 만든 것이 아니다.
KNOWN_SAFE = {("core/golden_benchmark.py", "subprocess 실행")}


class Finding:
    def __init__(self, path: str, item: str, what: str, verdict: str, evidence: str):
        self.path, self.item, self.what = path, item, what
        self.verdict, self.evidence = verdict, evidence

    def line(self) -> str:
        mark = "OK " if self.verdict in PASSING else ("⚠️ " if self.verdict == LEAKED else "?? ")
        return "| %s | %s | %s | %s%s | %s |" % (
            self.path, self.item, self.what, mark, self.verdict,
            self.evidence.replace("|", "/")[:150])


def probe(path: str, item: str, what: str,
          fn: Callable[[], Tuple[str, str]]) -> Finding:
    try:
        verdict, evidence = fn()
    except Exception:                       # noqa: BLE001
        return Finding(path, item, what, ERROR,
                       traceback.format_exc(limit=2).strip().splitlines()[-1])
    return Finding(path, item, what, verdict, evidence)


def _one(text: Any, limit: int = 145) -> str:
    return " ".join(str(text).split())[:limit]


# ══ ① 식별자·매핑 ══════════════════════════════════════════════════════════
def invented_institution_is_caught() -> Tuple[str, str]:
    """추천기: LLM 이 «없는 기관» 을 골랐다고 하면 대조표가 잡는가."""
    from core.external_intelligence import research_recommender as RR

    ok, invented = RR.verify_llm_output(
        ["KIET", "한국비철금속연구원", "LME_INSIGHT_BLOG", ""])
    if not invented:
        return LEAKED, "지어낸 키가 전부 통과했다: ok=%s" % (ok,)
    return REFUSED, "지어낸 것으로 잡음: %s (통과 %s)" % (list(invented), list(ok))


def invented_provider_id_is_rejected() -> Tuple[str, str]:
    """수집 제안: LLM 이 없는 원천을 지정하면 등록부가 거부하는가."""
    from core.external_intelligence import request_interpreter as ri

    r = ri.validate_proposal(
        {"subject_name": "LS MnM", "purpose": "시나리오", "period_from": "2024",
         "period_to": "2025", "indicators": ["구리 가격"],
         "provider_ids": ["BLOOMBERG_TERMINAL"], "target_contract_keys": ["EXT-02"]},
        known_provider_ids=["WB_PINK_SHEET"], known_contract_keys=["EXT-02"],
        scope_node_id="hq", purpose_kind="scenario", now_year=2026)
    bad = [p for p in r.problems if p.field == "provider_ids"]
    if r.ok or not bad:
        return LEAKED, "등록되지 않은 원천이 통과했다"
    return BLOCKED, _one(bad[0].reason)


def invented_contract_key_is_rejected() -> Tuple[str, str]:
    """LLM 이 그럴듯한 계약 키를 지어내면 «억지로 연결» 하지 않는가.

    ★ 이 관문은 2026-09-11 에 실제로 걸렸다 — EXT-02 가 승인 전이라 거부됐고,
      사람이 계약을 승인한 뒤에야 열렸다."""
    from core.external_intelligence import request_interpreter as ri

    r = ri.validate_proposal(
        {"subject_name": "LS MnM", "purpose": "시나리오", "period_from": "2024",
         "period_to": "2025", "indicators": ["구리 가격"],
         "provider_ids": ["WB_PINK_SHEET"], "target_contract_keys": ["EXT-99-METALS"]},
        known_provider_ids=["WB_PINK_SHEET"], known_contract_keys=["EXT-02"],
        scope_node_id="hq", purpose_kind="scenario", now_year=2026)
    bad = [p for p in r.problems if p.field == "target_contract_keys"]
    if r.ok or not bad:
        return LEAKED, "지어낸 계약 키가 통과했다"
    return BLOCKED, _one(bad[0].reason)


def internal_ids_in_human_fields_are_rejected() -> Tuple[str, str]:
    """사람이 쓰는 칸에 내부 ID 가 오면 거부한다(지시 1) — LLM 이 흔히 흘리는 모양이다."""
    from core.external_intelligence import request_interpreter as ri

    r = ri.validate_proposal(
        {"subject_name": "daq_57353e0b6e32426caef3", "purpose": "시나리오",
         "period_from": "2024", "period_to": "2025", "indicators": ["구리 가격"],
         "provider_ids": ["WB_PINK_SHEET"], "target_contract_keys": ["EXT-02"]},
        known_provider_ids=["WB_PINK_SHEET"], known_contract_keys=["EXT-02"],
        scope_node_id="hq", purpose_kind="scenario", now_year=2026)
    if r.ok:
        return LEAKED, "내부 ID 가 사람용 칸을 통과했다"
    return BLOCKED, _one(r.problems[0].reason)


def server_owned_fields_cannot_be_set_by_the_proposal() -> Tuple[str, str]:
    """★ LLM 이 «등급» 이나 «조직 범위» 를 스스로 정하면 안 된다 — 서버가 정한다."""
    from core.external_intelligence import request_interpreter as ri

    r = ri.validate_proposal(
        {"subject_name": "LS MnM", "purpose": "시나리오", "period_from": "2024",
         "period_to": "2025", "indicators": ["구리 가격"],
         "provider_ids": ["WB_PINK_SHEET"], "target_contract_keys": ["EXT-02"],
         "required_grade": "gold", "scope_node_id": "hq_other", "unrestricted": True},
        known_provider_ids=["WB_PINK_SHEET"], known_contract_keys=["EXT-02"],
        scope_node_id="hq", purpose_kind="scenario", now_year=2026)
    taken = {p.field for p in r.overridden}
    if not {"required_grade", "scope_node_id", "unrestricted"} <= taken:
        return LEAKED, "제안이 정한 서버 소유 값이 살아남았다: 덮어쓴 것 %s" % sorted(taken)
    if r.request and r.request.required_grade != "silver":
        return LEAKED, "등급을 제안이 올렸다: %s" % r.request.required_grade
    return BLOCKED, "덮어쓴 것 %s · 등급은 용도가 정함(silver)" % sorted(taken)


def vocabulary_is_not_created_silently() -> Tuple[str, str]:
    """승격이 «없는 지표» 를 만나면 말없이 만들지 않는다 — 기본값이 False 다."""
    from core.external_intelligence import observation_promotion as OP
    import inspect

    sig = inspect.signature(OP.promote)
    default = sig.parameters["register_missing"].default
    if default is not False:
        return LEAKED, "register_missing 기본값이 %r 이다 — 어휘가 자동 생성된다" % default
    return BLOCKED, "promote(register_missing=False) 가 기본 — 명시해야만 어휘를 만든다"


# ══ ② 숫자 → 계산 ══════════════════════════════════════════════════════════
def free_form_assumption_key_is_rejected() -> Tuple[str, str]:
    """LLM 이 「구리가격 10% 인상」 같은 자연어 키를 주면 규약이 거부하는가."""
    from core.enterprise_context import calc_bridge as CB

    try:
        CB.parse_assumption_key("구리가격 10% 인상")
    except CB.CalcBridgeError as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "규약 밖 가정 키가 통과했다"


def elasticity_without_rationale_is_rejected() -> Tuple[str, str]:
    """LLM 이 탄력도 숫자만 주고 근거를 안 주면 거부하는가."""
    from core import planning_drivers as PD

    try:
        PD.add_impact("COPPER_PRICE", "5000", 0.32, rationale="", source="")
    except PD.PlanningError as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "근거 없는 탄력도가 저장됐다 — 경영 보고서에 인쇄되는 숫자다"


def elasticity_without_source_is_rejected() -> Tuple[str, str]:
    """근거는 썼지만 «어디서 나온 숫자인지» 를 안 밝히면 거부하는가."""
    from core import planning_drivers as PD

    try:
        PD.add_impact("COPPER_PRICE", "5000", 0.32,
                      rationale="구리가 제조원가의 큰 축이다", source="")
    except PD.PlanningError as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "출처 없는 탄력도가 저장됐다"


def observation_without_vintage_is_rejected() -> Tuple[str, str]:
    """LLM 이 «어느 시점 발표값인지» 없이 숫자를 주면 거부하는가(§12.5)."""
    from core.external_intelligence import external_intelligence as ei, ExternalIntelligenceError

    try:
        ei.record_observation(indicator_code="WB_COPPER", observed_at="2026-08",
                              value=99999.0, source_id="WB_PINK_SHEET",
                              vintage="", grade="silver")
    except (ExternalIntelligenceError, ValueError) as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "vintage 없는 관측값이 저장됐다 — 재현 경로가 끊긴다"


def observation_from_unapproved_source_is_rejected() -> Tuple[str, str]:
    """승인되지 않은 원천 이름을 대면 거부하는가(§12.4)."""
    from core.external_intelligence import external_intelligence as ei, ExternalIntelligenceError

    try:
        ei.record_observation(indicator_code="WB_COPPER", observed_at="2026-08",
                              value=99999.0, source_id="SOME_ANALYST_BLOG",
                              vintage="2026-09", grade="silver")
    except (ExternalIntelligenceError, ValueError) as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "승인 안 된 원천의 값이 저장됐다"


def grade_cannot_exceed_the_source() -> Tuple[str, str]:
    """LLM 이 silver 원천 값에 gold 를 붙여 오면 거부하는가."""
    from core.external_intelligence import external_intelligence as ei, ExternalIntelligenceError

    try:
        ei.record_observation(indicator_code="WB_COPPER", observed_at="2026-08",
                              value=99999.0, source_id="WB_PINK_SHEET",
                              vintage="2026-09", grade="gold")
    except (ExternalIntelligenceError, ValueError) as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "출처보다 높은 등급이 붙었다 — 등급 정책이 무의미해진다"


# ══ ③ 코드 실행 ════════════════════════════════════════════════════════════
def _scan_execution_windows() -> List[Tuple[str, str, str]]:
    hits: List[Tuple[str, str, str]] = []
    for root_name in RUNTIME_DIRS:
        for base, _dirs, files in os.walk(os.path.join(PROJECT_ROOT, root_name)):
            if "__pycache__" in base:
                continue
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                full = os.path.join(base, fn)
                rel = os.path.relpath(full, PROJECT_ROOT).replace("\\", "/")
                try:
                    text = io.open(full, encoding="utf-8").read()
                except OSError:
                    continue
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith('"'):
                        continue        # 주석·문서에 적힌 «금지» 문구는 창구가 아니다
                    for pattern, label in EXEC_SHAPES:
                        if pattern.search(line):
                            hits.append((rel, label, stripped[:80]))
    return hits


def runtime_has_no_execution_window() -> Tuple[str, str]:
    """운영 코드(`core/`·`api/`)에 동적 실행 창구가 몇 개인가. **0 이어야 한다.**"""
    hits = _scan_execution_windows()
    unexpected = [h for h in hits if (h[0], h[1]) not in KNOWN_SAFE]
    if unexpected:
        return LEAKED, "창구 %d곳: %s" % (
            len(unexpected), ["%s(%s)" % (h[0], h[1]) for h in unexpected[:4]])
    known = sorted({h[0] for h in hits})
    return BLOCKED, "동적 실행 창구 0곳 (알려진 예외: %s — 인자가 고정 리터럴)" % (known or "없음")


def risky_change_detector_flags_execution_code() -> Tuple[str, str]:
    """★ 창구가 «생기는» 것도 감시되는가 — 위험 변경 탐지기가 이 모양을 잡는가.

    ⚠️ [2026-09-11] 첫 판에서 나는 `RA._RISK_PATTERNS` 라는 **있지도 않은 이름**을
      `getattr` 기본값과 함께 읽었다. 없으면 빈 목록이 돼 **탐침이 «샘» 이라고
      보고했다** — 제품이 아니라 내 계측기가 틀린 것이었다(네 번째다).
      그래서 지금은 **제품이 실제로 부르는 함수**(`classify_file`)를 쓴다.
      비공개 상수를 들여다보면 이름이 바뀌는 날 시험이 조용히 무의미해진다."""
    from core import risk_analyzer as RA

    sample = "def run(cmd):" + chr(10) + "    import subprocess" + chr(10) + "    return subprocess.run(cmd)" + chr(10)
    verdict = RA.classify_file("core/some_new_module.py", sample)
    quiet = RA.classify_file("core/some_new_module.py", "X = 1" + chr(10))
    if verdict.get("level") != RA.HIGH:
        return LEAKED, "실행 코드가 %s 로 분류됐다 — 창구가 조용히 생길 수 있다" % verdict.get("level")
    if quiet.get("level") == RA.HIGH:
        return LEAKED, "평범한 코드도 HIGH 다 — 늘 HIGH 면 경보가 아니다"
    return REFUSED, "%s (대조군 'X = 1' 은 %s)" % (_one(verdict.get("reason"), 70), quiet.get("level"))


PROBES: List[Tuple[str, str, str, Callable[[], Tuple[str, str]]]] = [
    ("① 식별자", "추천기", "LLM 이 «없는 기관» 을 골랐다고 한다", invented_institution_is_caught),
    ("① 식별자", "수집 제안", "등록 안 된 원천 id 를 지정한다", invented_provider_id_is_rejected),
    ("① 식별자", "수집 제안", "그럴듯한 계약 키를 지어낸다", invented_contract_key_is_rejected),
    ("① 식별자", "수집 제안", "사람용 칸에 내부 ID 를 넣는다", internal_ids_in_human_fields_are_rejected),
    ("① 식별자", "수집 제안", "제안이 «등급·범위» 를 스스로 정한다", server_owned_fields_cannot_be_set_by_the_proposal),
    ("① 매핑", "승격", "없는 지표를 만나면 말없이 만드는가", vocabulary_is_not_created_silently),
    ("② 숫자", "가정 번역", "자연어 가정 키를 준다", free_form_assumption_key_is_rejected),
    ("② 숫자", "탄력도", "근거 없이 계수만 준다", elasticity_without_rationale_is_rejected),
    ("② 숫자", "탄력도", "출처를 안 밝히고 계수를 준다", elasticity_without_source_is_rejected),
    ("② 숫자", "관측값", "vintage 없이 값을 넣는다", observation_without_vintage_is_rejected),
    ("② 숫자", "관측값", "승인 안 된 원천 이름을 댄다", observation_from_unapproved_source_is_rejected),
    ("② 숫자", "관측값", "출처보다 높은 등급을 붙인다", grade_cannot_exceed_the_source),
    ("③ 코드", "운영 트리", "동적 실행 창구를 센다", runtime_has_no_execution_window),
    ("③ 코드", "위험 탐지", "창구가 «생기는» 것을 잡는가", risky_change_detector_flags_execution_code),
]


def main() -> int:
    findings = [probe(path, item, what, fn) for path, item, what, fn in PROBES]
    leaked = [f for f in findings if f.verdict == LEAKED]
    errors = [f for f in findings if f.verdict == ERROR]

    b = io.StringIO()
    b.write("# X-3 결과 — 「AI 에게 진실을 맡기기」를 일으키려 했다\n\n")
    b.write("> 자동 생성: `tests/probe_x3_ai_truth.py`. **고쳐 쓰지 말 것** — 다시 돌리면 덮인다.\n")
    b.write("> ⚠️ 이 탐침은 **LLM 을 부르지 않는다.** LLM 출력을 «흉내» 낸다 — "
            "진짜로 부르면 매번 다른 것이 나와 재현되지 않는 시험이 된다.\n\n")
    b.write("    시도 %d건 · 막힘/거부 %d건 · **샘 %d건** · 탐침 오류 %d건\n\n"
            % (len(findings), len(findings) - len(leaked) - len(errors), len(leaked), len(errors)))
    b.write("| 경로 | 어디 | 무엇을 시켰나 | 결과 | 막은 문장 |\n|---|---|---|---|---|\n")
    for f in findings:
        b.write(f.line() + "\n")
    b.write("\n---\n\n## 판정\n\n")
    if errors:
        b.write("⚠️ **탐침 자신이 %d건 실패했다** — 그 항목은 「모른다」이지 「통과」가 아니다.\n\n"
                % len(errors))
    if leaked:
        b.write("### ⚠️⚠️ X-3 **실패** — 함정이 재현됐다\n\n")
        for f in leaked:
            b.write("- **%s / %s** — %s → %s\n" % (f.path, f.item, f.what, f.evidence))
    else:
        b.write("### X-3 **통과** — 세 경로가 전부 막혀 있다\n\n")
        b.write("★ 수용 기준의 핵심은 「막혔다」가 아니라 **「막는 것이 결정론적 검증기인가」** 다.\n")
        b.write("  위 항목은 전부 **대조표·정규식·필수 인자**가 막았다 — 프롬프트의 지시가 아니다.\n")
        b.write("  LLM 에게 「지어내지 마라」고 적는 것은 차단기가 아니다. "
                "같은 프롬프트가 다음에 다른 답을 낼 수 있고, 그때 아무도 모른다.\n")
    b.write("\n⚠️ 이 결과가 «주장하지 않는» 것\n\n")
    b.write("- LLM 을 **실제로 부르지 않았다.** 「이 관문들이 LLM 출력 모양을 막는다」까지가 주장이다.\n")
    b.write("- ③ 은 **정적 조사**다. 소스에 창구가 없다는 것이지 런타임에 "
            "플러그인·의존 라이브러리가 무엇을 하는지는 여기서 알 수 없다.\n")
    b.write("- 화면이 LLM 제안을 **사람에게 확인시키는지**는 Codex 레인이다.\n")

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with io.open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(b.getvalue())
    print(b.getvalue())
    print("기록:", REPORT)
    return 1 if leaked or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
