# -*- coding: utf-8 -*-
"""A-1 카나리 판독기 — 필수 계측 5종을 읽어 **Close 가능 여부를 판정**한다. LLM 0콜.

실행:
    venv\\Scripts\\python.exe scripts\\canary_report.py <project_name>
    venv\\Scripts\\python.exe scripts\\canary_report.py --list

## 왜 스크립트인가

2026-07-29 1차 카나리는 "완주했다"는 보고와 달리 **품질 게이트 계측이 한 건도 없었다**.
사람이 로그를 눈으로 훑어 발견하는 데 시간이 걸렸고, 그 사이 잘못된 근거로 Close 판정이
올라갈 뻔했다. 판정 기준을 코드로 고정해 두면 다음 카나리는 **결과가 나오는 즉시** 판정된다.

## 판정 기준 (2026-07-29 사용자 확정)

Close 조건 4종:
  ① 카나리 실행 ID와 최종 상태
  ② 모델·폴백·토큰·비용·지연시간 텔레메트리 원본
  ③ 품질 게이트 결과와 실패 분류 결과
  ④ UI 조회 또는 자동화 검증 증적          ← 이 스크립트가 ④의 '자동화 검증 증적'이다

필수 계측 5종:
  ⑴ 단계·에이전트별 사용 모델 및 폴백 사유
  ⑵ 호출별 입력/출력 토큰, 지연시간, 추정 비용
  ⑶ 단계별 프롬프트 컨텍스트 길이와 실제 참조된 지식 팩
  ⑷ 재작업·자가복구 횟수 및 실패 원인
  ⑸ 산출물 품질 게이트 결과와 최종 완주 여부

⚠️ **이 스크립트는 없는 것을 0 으로 채우지 않는다.** 계측이 비어 있으면 '미충족'이라고
   말한다 — 그것이 1차 카나리에서 배운 것이다.
"""
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LLM_LOG = os.path.join(ROOT, "data", "llm_call_log.jsonl")
QUALITY_LOG = os.path.join(ROOT, "data", "quality_outcomes.jsonl")
PROJECTS = os.path.join(ROOT, "projects")

OK, NO = "[충족]", "[미충족]"
PARTIAL = "[부분]"


def _read(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue          # 실행 중 append 로 잘린 줄은 건너뛴다(전체 폐기 금지)
    return out


def _pct(n, d):
    return f"{round(100 * n / d)}%" if d else "-"


def measure_1_models_and_fallbacks(calls):
    """⑴ 단계·에이전트별 모델 + 폴백 사유."""
    blank_stage = sum(1 for c in calls if not (c.get("stage") or ""))
    have_agent = sum(1 for c in calls if c.get("agent"))
    fb_calls = [c for c in calls if len(c.get("attempts") or []) > 1]
    fb_reasons = sum(1 for c in fb_calls if c.get("fallback_errors"))

    lines = [f"  - 호출 {len(calls)}건 · 단계 미상 {blank_stage}건({_pct(blank_stage, len(calls))})"
             f" · 에이전트 식별 {have_agent}건({_pct(have_agent, len(calls))})",
             f"  - 폴백 발생 {len(fb_calls)}건 · 그중 사유 기록 {fb_reasons}건"]
    for c in fb_calls[:5]:
        who = c.get("agent") or c.get("stage") or "?"
        why = "; ".join(f"{e.get('model')}→{e.get('error', '')[:60]}"
                        for e in (c.get("fallback_errors") or [])) or "사유 없음"
        lines.append(f"      · {who}: {len(c['attempts'])}개 모델 walk — {why}")

    # 판정: 단계·주체를 알 수 없는 호출이 있거나, 폴백 사유가 비면 미충족.
    if not calls:
        return NO, lines
    identified = all((c.get("stage") or c.get("agent")) for c in calls)
    if identified and (not fb_calls or fb_reasons == len(fb_calls)):
        return OK, lines
    return (PARTIAL if identified else NO), lines


def measure_2_cost(calls):
    """⑵ 토큰·지연·비용."""
    tin = sum(c.get("input_tokens") or 0 for c in calls)
    tout = sum(c.get("output_tokens") or 0 for c in calls)
    dur = sum(c.get("duration_s") or 0 for c in calls)
    priced = [c for c in calls if c.get("cost_basis") not in (None, "unpriced")]
    cost = sum(c.get("cost_estimate_usd") or 0 for c in calls)
    unpriced = len(calls) - len(priced)
    lines = [f"  - 토큰 in {tin:,} / out {tout:,} · 소요 {dur:.1f}s",
             f"  - 비용 {'≥ ' if unpriced else ''}${cost:.4f}"
             f" (산정 {len(priced)}건 / 미산정 {unpriced}건)",
             f"  - 비용 근거: {dict(Counter(c.get('cost_basis') for c in calls))}"]
    return (OK if calls and tin else NO), lines


def measure_3_context(calls):
    """⑶ 컨텍스트 길이와 **실제 참조된** 지식팩 — D-010(전수 주입) 판정의 유일한 근거."""
    with_ctx = [c for c in calls if c.get("context_chars")]
    if not with_ctx:
        return NO, ["  - 컨텍스트 계측 없음 — D-010(전수 주입) 판정 불가"]

    agg = defaultdict(int)
    for c in with_ctx:
        for k, v in (c.get("context_blocks") or {}).items():
            agg[k] += v
    total = sum(agg.values()) or 1
    clipped = sum(1 for c in with_ctx if c.get("context_clipped"))
    packs = sorted({p for c in with_ctx for p in (c.get("knowledge_packs") or [])})
    hits = sum(len(c.get("knowledge_hits") or []) for c in with_ctx)

    lines = [f"  - 컨텍스트 계측 {len(with_ctx)}/{len(calls)}건 · 절단 발생 {clipped}건",
             "  - 블록 비중(누계): " + ", ".join(
                 f"{k} {v:,}자({_pct(v, total)})"
                 for k, v in sorted(agg.items(), key=lambda x: -x[1])),
             f"  - 실제 주입된 지식팩: {packs or '없음'} (청크 {hits}건)"]

    # ★ D-010 판정 재료 — 기준정보가 기술 명세를 밀어냈는가.
    master = agg.get("master_data", 0)
    tech = agg.get("tech_spec", 0)
    if master and not tech:
        lines.append("      ⚠️ 기준정보는 주입됐는데 기술 명세가 0자다 — 밀려났을 가능성(2026-07-29 회귀 유형)")
    if clipped:
        lines.append(f"      ⚠️ 예산 초과 절단 {clipped}건 — 뒤쪽 블록(기술명세·파일)이 잘렸다")
    if not packs:
        lines.append("      ⚠️ 참조된 지식팩 0 — 그라운딩 없이 실행됐다(D-010 실증 불가)")

    ok = bool(with_ctx) and len(with_ctx) == len(calls) and bool(packs)
    return (OK if ok else PARTIAL), lines


def measure_4_rework(outcomes, state):
    """⑷ 재작업·자가복구 횟수와 실패 원인."""
    fails = [o for o in outcomes if o.get("pass_fail") == "FAIL"]
    causes = Counter(o.get("root_cause") or "unclassified" for o in fails)
    lines = [f"  - 상태값: 개발 재시도 {state.get('developer_retry_count', '?')} ·"
             f" 검수 왕복 {state.get('supervisor_hops', '?')}",
             f"  - 실패 기록 {len(fails)}건 · 원인 분포 {dict(causes)}"]
    if fails and causes.get("unclassified"):
        lines.append(f"      · 미분류 {causes['unclassified']}건 — 사람이 사후 분류해야 한다(D-015)")
    return (OK if outcomes else NO), lines


def measure_5_gates(outcomes, state, tasks):
    """⑸ 품질 게이트 결과와 최종 완주 여부."""
    by_gate = defaultdict(lambda: [0, 0])
    for o in outcomes:
        by_gate[o.get("gate_name") or "-"][0 if o.get("pass_fail") == "PASS" else 1] += 1
    done = sum(1 for t in tasks if (t.get("status") or "").upper() == "DONE")
    lines = [f"  - WBS {done}/{len(tasks)} DONE · build={state.get('build_status')}"
             f" · qa={state.get('qa_verdict')} · release_id={state.get('release_id') or '없음'}"]
    if by_gate:
        lines.append("  - 게이트별 통과/실패: " + ", ".join(
            f"{g} {v[0]}/{v[0] + v[1]}" for g, v in sorted(by_gate.items())))
    else:
        lines.append("  - 게이트 계측 없음 — 최종 상태값만으로는 '어떻게 통과했는지' 알 수 없다")
    ok = bool(by_gate) and tasks and done == len(tasks)
    return (OK if ok else (PARTIAL if tasks else NO)), lines


def report(project: str) -> int:
    calls = [c for c in _read(LLM_LOG) if c.get("project") == project]
    events = [e for e in _read(QUALITY_LOG) if e.get("project") == project]
    try:
        from core import quality_telemetry as qt
        outcomes = qt.resolve_outcomes(events)
    except Exception:
        outcomes = [e for e in events if e.get("event") == "gate"]

    pdir = os.path.join(PROJECTS, project)
    state, tasks = {}, []
    try:
        with open(os.path.join(pdir, "latest_state.json"), "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        pass
    try:
        with open(os.path.join(pdir, "00_wbs_master_plan.json"), "r", encoding="utf-8") as f:
            tasks = json.load(f).get("tasks", [])
    except Exception:
        pass

    if not calls and not state:
        print(f"프로젝트 '{project}' 의 기록을 찾지 못했습니다. --list 로 목록을 보십시오.")
        return 2

    print("=" * 72)
    print(f"A-1 카나리 판독 — {project}")
    if calls:
        print(f"  기간: {calls[0]['ts']} → {calls[-1]['ts']}")
    print("=" * 72)

    results = []
    for title, (verdict, lines) in [
        ("⑴ 단계·에이전트별 모델 / 폴백 사유", measure_1_models_and_fallbacks(calls)),
        ("⑵ 토큰·지연·비용", measure_2_cost(calls)),
        ("⑶ 컨텍스트 길이 / 참조 지식팩", measure_3_context(calls)),
        ("⑷ 재작업·자가복구·실패 원인", measure_4_rework(outcomes, state)),
        ("⑸ 품질 게이트 결과·완주 여부", measure_5_gates(outcomes, state, tasks)),
    ]:
        print(f"\n{verdict} {title}")
        for l in lines:
            print(l)
        results.append(verdict)

    print("\n" + "-" * 72)
    unmet = [i + 1 for i, v in enumerate(results) if v == NO]
    partial = [i + 1 for i, v in enumerate(results) if v == PARTIAL]
    if unmet:
        print(f"판정: **Close 불가** — 계측 {unmet} 미충족"
              + (f", {partial} 부분 충족" if partial else ""))
        print("  → 갭을 메우고 재카나리해야 QUALITY-TEL-01 을 닫을 수 있습니다.")
        return 1
    if partial:
        print(f"판정: **조건부** — 계측 {partial} 부분 충족. 남은 항목을 확인하고 판단하십시오.")
        return 1
    print("판정: **계측 5종 전부 충족** — 이 출력을 QUALITY-TEL-01 Close 증적으로 첨부하십시오.")
    print("  ⚠️ 단 UI 조회 증적(스크린샷 등)은 별도입니다 — 이 스크립트는 자동화 검증 증적입니다.")
    return 0


def list_projects():
    seen = {}
    for c in _read(LLM_LOG):
        p = c.get("project") or ""
        if p:
            seen.setdefault(p, [c["ts"], c["ts"]])
            seen[p][1] = c["ts"]
    if not seen:
        print("기록된 프로젝트가 없습니다.")
        return
    print("기록된 프로젝트:")
    for p, (a, b) in sorted(seen.items(), key=lambda x: x[1][1], reverse=True):
        print(f"  - {p}   ({a} → {b})")


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    if args[0] == "--list":
        list_projects()
        sys.exit(0)
    sys.exit(report(args[0]))
