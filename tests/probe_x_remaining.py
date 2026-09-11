"""[X-1 · X-2 · X-5] 계획 6단계 — 남은 반증 셋.

    X-1 (§9.1)  기능 나열       흐름에 안 붙는 기능이 있는가
    X-2 (§9.2)  이른 범용화     첫 고객(LS MnM) 흐름에 안 쓰이는 범용 기능의 비중
    X-5 (§9.5)  성급한 외부 쓰기 읽기→검증→Shadow→승인→제한적 쓰기의 «순서를 건너뛰려» 시도

## ★ X-1 과 X-2 는 «판정» 이 수용 기준이다 — 세는 것만으로는 실패다

계획 §6: 「그런 기능이 있으면 **「기반시설」인지 「표류」인지 판정하고 기록**한다.
**판정 없이 남겨 두면 X-1 실패**」.

그래서 이 탐침은 미귀속 도메인을 세기만 하지 않고 **닫힌 어휘로 판정한다**:

    기반시설   흐름에 «직접» 안 붙지만 없으면 다른 단계가 서지 않는다(health·ws·인증…)
    표류       어느 단계에도 안 붙고 없어도 흐름이 돈다 — 지우거나 단계에 붙여야 한다
    미판정     ⚠️ 이게 남아 있으면 X-1 실패다

⚠️ 판정 표(`VERDICTS`)는 **사람이 쓴 것**이고 이 파일이 그 근거를 함께 들고 있다.
  새 도메인이 생기면 여기 없으므로 «미판정» 으로 떨어지고 X-1 이 실패한다 —
  그것이 의도다. 조용히 늘어나지 않게 한다.

## X-5 는 X-3·X-4 와 같은 «반증» 이다

순서를 건너뛰려 시도한다. 막히면 통과.
"""
from __future__ import annotations

import io
import os
import sys
import traceback
from typing import Any, Callable, Dict, List, Set, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

REPORT = os.path.join(PROJECT_ROOT, "docs", "test_plan", "X_REMAINING_FINDINGS.md")

OK = "충족"
BLOCKED = "막힘"
LEAKED = "샘"
UNJUDGED = "미판정"      # X-1 의 실패 조건
ERROR = "탐침 오류"
PASSING = (OK, BLOCKED)

# ── 판정 표 — 사람이 쓴다. 근거를 함께 적는다 ───────────────────────────────
INFRA = "기반시설"
DRIFT = "표류"

#: 계획 §2 가 「미귀속 3(health·ws·simulations)」으로 남긴 것 + 그 뒤 늘어난 것.
#: ⚠️ 여기 없는 접두사는 «미판정» 으로 떨어진다 — 그것이 X-1 의 실패 조건이다.
VERDICTS: Dict[str, Tuple[str, str]] = {
    "/health": (INFRA, "가동 확인. 흐름에 안 붙지만 없으면 배포·감시가 못 선다"),
    "/ws": (INFRA, "실시간 알림 전송로. 8단계 중 어디에도 «속하지» 않고 전 단계를 가로지른다"),
    "/api/v1/simulations": (INFRA,
                            "시뮬레이션 실행 id 로 결정 안건을 거는 접합부. "
                            "7단계(비교)와 8단계(의사결정) «사이»라 한쪽에 못 붙인다"),
    "/openapi.json": (INFRA, "API 명세. 도구용이다"),
    "/docs": (INFRA, "API 문서 화면. 도구용이다"),
    "/redoc": (INFRA, "API 문서 화면. 도구용이다"),
    "/": (INFRA, "정적 진입점"),
    #: ★ [2026-09-11] 첫 실행에서 «미판정» 으로 떨어져 X-1 이 실패했다 — 설계한 대로다.
    #:   판정: 에이전트가 «스스로 제안한» 스킬 개선안을 사람이 승인·거부하는 관문이다.
    #:   고객의 업무 흐름(8단계)이 아니라 **플랫폼 자신의 진화**를 다루므로 어느 단계에도
    #:   안 붙는다. 그리고 없으면 AI 제안이 «승인 없이» 반영되므로 X-3 의 함정이 열린다.
    "/skills": (INFRA,
                "에이전트 스킬 제안의 사람 승인 관문(승인·거부). 8단계가 아니라 "
                "플랫폼 자기 진화를 다룬다. 없으면 AI 제안이 승인 없이 반영된다 — X-3 참조"),
}

#: 8단계에 귀속된 것으로 보는 접두사. 계획 §2 의 귀속을 그대로 옮긴 것이 아니라,
#: **「어느 단계엔가 붙는다」만 판정**한다 — 몇 단계인지는 §2 가 이미 정했다.
#: ⚠️ 이 목록이 «관대하면» X-1 이 무의미해진다. 그래서 접두사는 `/api/v1/<도메인>` 까지만 본다.
STAGED_PREFIX = "/api/v1/"


def _domain_of(path: str) -> str:
    """`/api/v1/acquisition/jobs/{id}` → `/api/v1/acquisition`. 그 밖은 첫 조각."""
    bits = [b for b in str(path or "").split("/") if b]
    if not bits:
        return "/"
    if path.startswith(STAGED_PREFIX) and len(bits) >= 3:
        return "/%s/%s/%s" % (bits[0], bits[1], bits[2])
    return "/" + bits[0]


class Finding:
    def __init__(self, track: str, what: str, verdict: str, evidence: str):
        self.track, self.what, self.verdict, self.evidence = track, what, verdict, evidence

    def line(self) -> str:
        mark = {OK: "OK ", BLOCKED: "OK ", LEAKED: "⚠️ ", UNJUDGED: "⚠️ "}.get(self.verdict, "?? ")
        return "| %s | %s | %s%s | %s |" % (
            self.track, self.what, mark, self.verdict, self.evidence.replace("|", "/")[:165])


def probe(track: str, what: str, fn: Callable[[], Tuple[str, str]]) -> Finding:
    try:
        verdict, evidence = fn()
    except Exception:                       # noqa: BLE001
        return Finding(track, what, ERROR,
                       traceback.format_exc(limit=2).strip().splitlines()[-1])
    return Finding(track, what, verdict, evidence)


def _one(x: Any, n: int = 160) -> str:
    return " ".join(str(x).split())[:n]


def _route_paths() -> Set[str]:
    """`main.app` 의 라우트. F-0 탐침과 **같은 방법**을 쓴다 — 두 곳이 다르게 세면
    「몇 개인가」에 답이 둘이 된다."""
    import main
    from fastapi.routing import APIRoute
    return {r.path for r in main.app.routes if isinstance(r, APIRoute)}


# ══ X-1 흐름에 안 붙는 기능 ════════════════════════════════════════════════
def every_unstaged_domain_is_judged() -> Tuple[str, str]:
    """★★★ 수용 기준은 「없다」가 아니라 「**판정돼 있다**」이다."""
    paths = _route_paths()
    unstaged = sorted({_domain_of(p) for p in paths if not p.startswith(STAGED_PREFIX)})
    unjudged = [d for d in unstaged if d not in VERDICTS]
    if unjudged:
        return UNJUDGED, ("판정 표에 없는 도메인 %d개: %s — 「기반시설」인지 「표류」인지 "
                          "적지 않으면 X-1 실패다" % (len(unjudged), unjudged))
    drifting = [d for d in unstaged if VERDICTS[d][0] == DRIFT]
    if drifting:
        return LEAKED, "표류로 판정된 도메인: %s — 단계에 붙이거나 지워야 한다" % drifting
    return OK, "단계 밖 도메인 %d개 전부 «기반시설» 로 판정됨: %s" % (len(unstaged), unstaged)


def staged_domains_are_reachable() -> Tuple[str, str]:
    """★ 「귀속됐다」와 「불린다」는 다르다 — F 시나리오가 실제로 만진 도메인을 센다.

    ⚠️ 이 탐침이 세는 것은 **이 저장소의 시험·탐침이 만진 자취**이지 «사용자가 쓴 것»이
      아니다. 후자는 여기서 알 수 없다 — 그래서 «표류» 라고 단정하지 않고 비중만 낸다."""
    paths = _route_paths()
    domains = sorted({_domain_of(p) for p in paths if p.startswith(STAGED_PREFIX)})
    #: F 트랙이 실제로 관통시킨 도메인(§9-B~9-H 에 근거가 있는 것만).
    walked = {
        "/api/v1/acquisition": "F-2·F-6 — 수집→적재→승격 실측",
        "/api/v1/external": "F-6 — 원천 승인·관측값",
        "/api/v1/advisor": "F-0·F-1 — 상담→청사진",
        "/api/v1/planning": "F-6·F-7 — 동인·시나리오",
        "/api/v1/decisions": "F-7 — 안건·결정",
        "/api/v1/baseline": "F-7 — 기준선·시뮬레이션",
        "/api/v1/delivery": "F-4 — 전달",
        "/api/v1/research": "추천기",
    }
    hit = [d for d in domains if d in walked]
    return OK, ("전체 도메인 %d개 중 F 트랙이 실제로 관통시킨 것 %d개(%.0f%%) — "
                "나머지는 «표류» 가 아니라 «아직 안 걸어 봤다» 이다"
                % (len(domains), len(hit), 100.0 * len(hit) / max(len(domains), 1)))


# ══ X-2 이른 범용화 ════════════════════════════════════════════════════════
#: 첫 고객(LS MnM)이 **지금** 쓰는 것. 실측 근거가 있는 것만 넣는다.
FIRST_CUSTOMER_EVIDENCE = {
    "비철금속 제련 산업분류": "core/external_intelligence/research_catalog.py — KSIC C2412",
    "구리·아연 국제가": "external_observations 240행(WB_COPPER·WB_ZINC)",
    "동제련·배터리소재 사업부": "organization_nodes — MNM_COPPER·MNM_BATTERY",
    "실제 결정 안건": "decision_cases 실계정 7건",
}


def generic_features_do_not_slow_the_first_customer() -> Tuple[str, str]:
    """수용 기준은 「범용 기능이 없다」가 아니라 **「첫 고객 흐름을 느리게·헷갈리게
    하지 않는다」** 이다. 그래서 «첫 고객 경로에 범용 선택지가 강제되는가» 를 본다."""
    from core.external_intelligence import providers as P
    from core.external_intelligence import research_recommender as RR

    #: ① 원천 — 5종이 있는데 첫 고객이 «고르도록 강요» 받는가?
    ids = list(P.descriptors())
    #: ② 추천기 — 27곳 카탈로그가 첫 고객(C2412 비철금속 제련)에게 몇 곳으로 좁혀지는가?
    #: ⚠️ [2026-09-11] 첫 판에서 `sources`·`recommended` 라는 **없는 필드**를 읽어
    #:   「0곳」이라 보고했다(계측기 오류 7번째). 실제 필드는 `items` 다.
    #:   ★ 그래서 지금은 **먼저 물어본 뒤** 쓴다 — `accounted` 로 카탈로그 정산까지 확인한다.
    total = len(RR.RC.CATALOG)
    ls_mnm = RR.recommend(RR.CompanyContext(
        company_name="LS MnM", industry_code="C2412",
        products=("전기동", "아연괴"), source_note="probe_x2"))
    if not ls_mnm.accounted:
        return LEAKED, ("추천 %d + 제외 %d ≠ 카탈로그 %d — 조용히 사라진 원천이 있다"
                        % (len(ls_mnm.items), len(ls_mnm.excluded), total))
    picked = list(ls_mnm.items)
    if not picked:
        return LEAKED, "첫 고객 업종으로 추천이 0곳이다 — 범용 카탈로그가 첫 고객에게 안 맞는다"
    if len(picked) == total:
        return LEAKED, ("카탈로그 %d곳이 그대로 나온다 — 좁히지 않으면 사용자가 27곳을 "
                        "손으로 훑어야 한다(§9.2 이른 범용화)" % total)
    return OK, ("원천 %d종은 요청 지표로 «자동» 선택(사람이 목록을 안 고른다) · "
                "추천 기관 %d/%d 곳(제외 %d곳은 «사유와 함께» 빠짐, 정산 일치) — "
                "범용 목록이 첫 고객에게 그대로 노출되지 않는다"
                % (len(ids), len(picked), total, len(ls_mnm.excluded)))


# ══ X-5 성급한 외부 쓰기 ═══════════════════════════════════════════════════
def connector_default_is_read_only() -> Tuple[str, str]:
    """★★★ 수용 기준이 명시한 것 — **기본값이 읽기 전용**이다."""
    import inspect
    from core.connector_registry import connector_registry, ACCESS_MODES

    reg = getattr(connector_registry, "register", None)
    if reg is None:
        return ERROR, "connector_registry.register 를 못 찾았다"
    default = inspect.signature(reg).parameters["access_mode"].default
    if default != "read":
        return LEAKED, "커넥터 기본 access_mode 가 %r 이다 — 기본이 쓰기면 실수로 쓴다" % (default,)
    return BLOCKED, "기본 access_mode='read' · 닫힌 목록 %s" % (ACCESS_MODES,)


def acquisition_cannot_jump_to_active() -> Tuple[str, str]:
    """DRAFT 에서 곧바로 ACTIVE 로 갈 수 있는가 — dry-run·검토를 건너뛰는 경로."""
    from core.external_intelligence import acquisition_models as am

    try:
        am.assert_transition(am.DRAFT, "ACTIVE")
    except am.AcquisitionStateError as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "DRAFT → ACTIVE 로 곧바로 갈 수 있다 — dry-run 과 검토를 건너뛴다"


def acquisition_cannot_skip_review() -> Tuple[str, str]:
    """dry-run 까지 왔어도 «검토 없이» 적용으로 못 간다."""
    from core.external_intelligence import acquisition_models as am

    try:
        am.assert_transition(am.DRY_RUN, "ACTIVE")
    except am.AcquisitionStateError as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "DRY_RUN → ACTIVE 로 곧바로 갈 수 있다 — 검토를 건너뛴다"


def auto_apply_is_not_the_default() -> Tuple[str, str]:
    """★ 사람 승인 없이 적용하는 스위치가 «기본으로 켜져» 있으면 안 된다."""
    import sqlite3
    path = os.path.join(PROJECT_ROOT, "data", "external_intelligence.db")
    conn = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True)
    try:
        rows = conn.execute("SELECT auto_apply, COUNT(*) FROM data_acquisition_jobs "
                            "GROUP BY auto_apply").fetchall()
        ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name='data_acquisition_jobs'"
                           ).fetchone()[0]
    finally:
        conn.close()
    on = sum(n for v, n in rows if v)
    default_on = "auto_apply" in ddl and "DEFAULT 1" in ddl.replace("  ", " ")
    if default_on:
        return LEAKED, "스키마 기본값이 auto_apply=1 이다"
    if on:
        return LEAKED, "auto_apply 가 켜진 작업 %d건 — 누가 언제 켰는지 확인해야 한다" % on
    return BLOCKED, "스키마 기본값 꺼짐 · 켜진 작업 0건(분포 %s)" % dict(rows)


def shadow_promote_needs_review() -> Tuple[str, str]:
    """Shadow → 운영 승격을 «검토 없이» 시도한다."""
    import sqlite3
    import tempfile
    from core.shadow_mode import ShadowMode, ShadowModeError

    sm = ShadowMode(db_path=os.path.join(tempfile.mkdtemp(), "shadow_probe.db"))
    assert "WorkSpace" not in sm.db_path, "운영 DB 다! 중단"
    run = sm.create_run(name="probe", candidate_kind="planning_scenario",
                        enterprise_scope_id="hq", evaluation_period="2026-08")
    try:
        sm.promote(run["run_id"], promotion_scope="전사", promoted_by="probe")
    except ShadowModeError as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "검토 없이 승격됐다 — §7.3 의 5단계를 건너뛴다"


def shadow_promote_needs_a_scope() -> Tuple[str, str]:
    """★ 「전체 적용」을 기본값으로 두면 «제한적 적용» 이라는 개념이 사라진다."""
    import tempfile
    from core.shadow_mode import ShadowMode, ShadowModeError

    sm = ShadowMode(db_path=os.path.join(tempfile.mkdtemp(), "shadow_probe2.db"))
    run = sm.create_run(name="probe", candidate_kind="planning_scenario",
                        enterprise_scope_id="hq", evaluation_period="2026-08")
    try:
        sm.promote(run["run_id"], promotion_scope="", promoted_by="probe")
    except ShadowModeError as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "범위 없는 승격이 됐다 — 제한적 적용이 아니라 전면 적용이다"


def shadow_review_needs_a_named_reviewer() -> Tuple[str, str]:
    import tempfile
    from core.shadow_mode import ShadowMode, ShadowModeError

    sm = ShadowMode(db_path=os.path.join(tempfile.mkdtemp(), "shadow_probe3.db"))
    run = sm.create_run(name="probe", candidate_kind="planning_scenario",
                        enterprise_scope_id="hq", evaluation_period="2026-08")
    try:
        sm.review(run["run_id"], decision="approved", reviewed_by="")
    except ShadowModeError as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "검토자 없이 승인됐다"


def shadow_cannot_approve_an_incomparable_run() -> Tuple[str, str]:
    """★ 같은 입력이 아니면 비교가 아니다 — 그것을 승인하면 «없는 효과» 를 승격한다."""
    import tempfile
    from core.shadow_mode import ShadowMode, ShadowModeError

    sm = ShadowMode(db_path=os.path.join(tempfile.mkdtemp(), "shadow_probe4.db"))
    run = sm.create_run(name="probe", candidate_kind="planning_scenario",
                        enterprise_scope_id="hq", evaluation_period="2026-08")
    sm.record_side(run["run_id"], "baseline", {"error_count": 1}, input_hash="AAA")
    sm.record_side(run["run_id"], "candidate", {"error_count": 0}, input_hash="BBB")
    try:
        sm.review(run["run_id"], decision="approved", reviewed_by="probe@afs.invalid")
    except ShadowModeError as exc:
        return BLOCKED, _one(exc)
    return LEAKED, "입력이 다른 run 을 승인했다 — 그 차이는 후보의 효과가 아니다"


PROBES: List[Tuple[str, str, Callable[[], Tuple[str, str]]]] = [
    ("X-1", "단계 밖 도메인이 전부 «판정»돼 있는가", every_unstaged_domain_is_judged),
    ("X-1", "F 트랙이 실제로 만진 도메인 비중", staged_domains_are_reachable),
    ("X-2", "범용 기능이 첫 고객에게 강요되는가", generic_features_do_not_slow_the_first_customer),
    ("X-5", "커넥터 기본값이 읽기 전용인가", connector_default_is_read_only),
    ("X-5", "DRAFT 에서 곧바로 ACTIVE 로 간다", acquisition_cannot_jump_to_active),
    ("X-5", "DRY_RUN 에서 검토를 건너뛴다", acquisition_cannot_skip_review),
    ("X-5", "auto_apply 가 기본으로 켜져 있는가", auto_apply_is_not_the_default),
    ("X-5", "검토 없이 Shadow 를 승격한다", shadow_promote_needs_review),
    ("X-5", "범위 없이 Shadow 를 승격한다", shadow_promote_needs_a_scope),
    ("X-5", "검토자 없이 승인한다", shadow_review_needs_a_named_reviewer),
    ("X-5", "입력이 다른 run 을 승인한다", shadow_cannot_approve_an_incomparable_run),
]


def main() -> int:
    findings = [probe(t, w, f) for t, w, f in PROBES]
    bad = [f for f in findings if f.verdict in (LEAKED, UNJUDGED)]
    errors = [f for f in findings if f.verdict == ERROR]

    b = io.StringIO()
    b.write("# X-1 · X-2 · X-5 결과 — 계획 6단계\n\n")
    b.write("> 자동 생성: `tests/probe_x_remaining.py`. **고쳐 쓰지 말 것** — 다시 돌리면 덮인다.\n")
    b.write("> ★ X-1 의 수용 기준은 「없다」가 아니라 **「판정돼 있다」** 다 — "
            "판정 없이 남겨 두면 그 자체가 실패다(계획 §6).\n\n")
    b.write("    항목 %d건 · 충족/막힘 %d건 · **샘·미판정 %d건** · 탐침 오류 %d건\n\n"
            % (len(findings), len(findings) - len(bad) - len(errors), len(bad), len(errors)))
    b.write("| 트랙 | 무엇을 봤나 | 결과 | 근거 |\n|---|---|---|---|\n")
    for f in findings:
        b.write(f.line() + "\n")

    b.write("\n---\n\n## X-1 판정표 — 단계에 안 붙는 도메인을 어떻게 봤나\n\n")
    b.write("| 도메인 | 판정 | 근거 |\n|---|---|---|\n")
    for d, (v, why) in sorted(VERDICTS.items()):
        b.write("| `%s` | %s | %s |\n" % (d, v, why))
    b.write("\n⚠️ **이 표에 없는 도메인이 새로 생기면 «미판정» 으로 떨어지고 X-1 이 실패한다.** "
            "조용히 늘어나지 않게 하려는 것이다 — 새 도메인을 만든 사람이 "
            "「기반시설인지 표류인지」를 여기 적어야 한다.\n")

    b.write("\n## 판정\n\n")
    if errors:
        b.write("⚠️ **탐침 자신이 %d건 실패했다** — 「모른다」이지 「통과」가 아니다.\n\n" % len(errors))
    if bad:
        b.write("### ⚠️⚠️ 실패\n\n")
        for f in bad:
            b.write("- **%s %s** → %s\n" % (f.track, f.what, f.evidence))
    else:
        b.write("### 통과 — X-1·X-2·X-5 전부\n\n")
        b.write("★ X-5 가 특히 촘촘하다: 상태 전이표가 건너뛰기를 막고, 그 «위» 에\n")
        b.write("  Shadow 의 검토자·범위·입력동일 세 관문이 따로 선다. 한 겹이 아니다.\n")
    b.write("\n⚠️ 이 결과가 «주장하지 않는» 것\n\n")
    b.write("- X-1 의 「F 트랙이 만진 도메인」은 **이 저장소의 시험·탐침 자취**이지 "
            "«사용자가 쓴 것» 이 아니다. 안 걸어 본 도메인을 «표류» 라고 단정하지 않았다.\n")
    b.write("- X-2 는 「범용 목록이 첫 고객에게 강요되는가」까지만 봤다. "
            "화면이 실제로 어떻게 좁혀 보여 주는지는 Codex 레인이다.\n")

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with io.open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(b.getvalue())
    print(b.getvalue())
    print("기록:", REPORT)
    return 1 if bad or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
