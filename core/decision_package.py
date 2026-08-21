"""[Wave G 11.4] 의사결정 패키지 — **숫자에서 «누가 무엇을 언제» 까지.**

시뮬레이션 결과 하나가 회의 안건이 되려면 세 가지가 더 필요하다.

★★★ ① **3관점 검토서.** 요청자·의사결정자·영향부서는 **같은 숫자를 다르게 읽는다.**
  한 장으로 뭉치면 각자 자기에게 필요한 것을 못 찾고, 회의가 「자료를 다시 보내
  주세요」로 끝난다.
★★★ ② **실행 책임자와 기한.** 없으면 「검토하겠습니다」로 끝나고 아무 일도 안 난다.
★★★ ③ **근거의 계보.** 어느 기준선 · 어느 산식 판 · 어떤 가정에서 나온 숫자인가.
  ⚠️ 이것이 없으면 다음 회의에서 같은 숫자를 다시 만들 수 없고, 그러면 결정을
    되짚을 수도 없다.

## LLM 이 여기서 숫자를 만들지 않는다

문장은 **표에서 조립**한다. 그럴듯한 요약을 생성하면 그 요약이 원본과 갈라지고,
사람은 요약만 읽는다.
"""
from typing import Any, Dict, List, NamedTuple, Optional

from core import calc_graph as cg

#: ★ 3관점 — **닫힌 목록.** 관점이 늘면 화면과 문서가 함께 늘어야 한다.
VIEW_REQUESTER = "요청자"
VIEW_DECIDER = "의사결정자"
VIEW_AFFECTED = "영향부서"
VIEWS = (VIEW_REQUESTER, VIEW_DECIDER, VIEW_AFFECTED)

#: 관점마다 **먼저 보는 것**이 다르다. 순서가 곧 그 사람의 관심사다.
_FOCUS: Dict[str, List[str]] = {
    VIEW_REQUESTER: ["production_qty", "ending_inventory", "purchase_payment"],
    VIEW_DECIDER: ["operating_profit", "ending_cash", "purchase_payment"],
    VIEW_AFFECTED: ["production_qty", "ending_inventory", "operating_profit"],
}
_QUESTION: Dict[str, str] = {
    VIEW_REQUESTER: "요청한 변화가 실제로 무엇을 바꾸는가",
    VIEW_DECIDER: "지금 결정하지 않으면 무엇을 잃는가",
    VIEW_AFFECTED: "우리 부서의 일이 어떻게 달라지는가",
}


class DecisionError(Exception):
    """안건을 만들 수 없다."""


class Package(NamedTuple):
    title: str
    question: str
    owner: str
    due: str
    evidence: Dict[str, Any]
    views: List[Dict[str, Any]]
    data_kind: str

    def public(self) -> Dict[str, Any]:
        return {"title": self.title, "question": self.question, "owner": self.owner,
                "due": self.due, "evidence": dict(self.evidence),
                "views": list(self.views), "data_kind": self.data_kind,
                "display_label": _label(self.data_kind)}


def _label(data_kind: Any) -> str:
    from core.baseline_build import display_label

    return display_label(data_kind)


def _view(name: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """한 관점의 검토서. **같은 표에서 다른 순서로** 뽑는다.

    ⚠️ 관점마다 다른 숫자를 만들지 않는다 — 그러면 회의에서 「어느 게 맞습니까」가
      나오고, 그 순간 자료 전체의 신뢰가 무너진다."""
    by_key = {r["key"]: r for r in rows}
    focus = [by_key[k] for k in _FOCUS[name] if k in by_key]
    #: 관심 밖 항목도 **버리지 않는다** — 접어 둘 뿐이다(숨기면 나중에 「왜 안 보여
    #: 줬냐」가 된다).
    rest = [r for r in rows if r["key"] not in _FOCUS[name]]
    return {"view": name, "question": _QUESTION[name],
            "highlights": focus, "others": rest}


def build(*, title: str, owner: str, due: str, base: Any, scenario: Any,
          baseline: Any = None, path: Optional[Dict[str, Any]] = None,
          calc_binding: Optional[Dict[str, Any]] = None) -> Package:
    """시뮬레이션 두 판 → 회의 안건 하나.

    ⚠️ 책임자·기한이 없으면 만들지 않는다. 없는 안건은 「검토하겠습니다」로 끝나고
      아무 일도 안 난다 — 그것은 의사결정이 아니다."""
    if not str(title or "").strip():
        raise DecisionError("안건 제목이 필요합니다.")
    if not str(owner or "").strip():
        raise DecisionError(
            "실행 책임자가 필요합니다 — 없는 안건은 「검토하겠습니다」로 끝납니다.")
    if not str(due or "").strip():
        raise DecisionError("기한이 필요합니다 — 기한 없는 결정은 결정이 아닙니다.")
    if base is None or scenario is None:
        raise DecisionError("기준과 시나리오가 모두 필요합니다.")

    #: ★★★ [2026-08-21 B1.2-1 P0] **계산할 수 없는 경로로 숫자 안건을 만들지 않는다.**
    #:
    #: ⚠️⚠️ 종전에는 `calculation_blocked` 를 근거에 «적어 두기만» 했다. 그래서 한
    #:   패키지 안에 이 둘이 **동시에** 실렸다:
    #:
    #:       「이 경로는 아직 계산할 수 없습니다」
    #:       「영업이익이 -200,000,000원 변합니다 — 지금 무엇을 결정해야 합니까?」
    #:
    #: ★ 사람은 **숫자를 읽는다.** 옆줄의 「계산할 수 없습니다」는 각주로 읽힌다.
    #:   그리고 그 숫자는 이 경로와 아무 상관이 없다 — 기존 시나리오 엔진의 결과다.
    #: ⚠️ 「일단 만들고 화면에서 가리자」도 안 된다. 안건은 원장에 남고 발간으로 나간다.
    if path is not None:
        blocked = bool((path or {}).get("calculation_blocked", False))
        incomplete = not bool((path or {}).get("complete", False))
        #: ⚠️⚠️ **범위를 좁힌 자리다 — 확인이 필요하다.**
        #:
        #:   `calculation_blocked` 는 **언제나** 막는다.
        #:   `complete=False` 는 **런타임 경로일 때만** 막는다(`query_id` 가 있는 경우).
        #:
        #: ★ 왜 좁혔나: 고정 경로(`core/ontology_path.trace`)는 근거가 빠진 단계를
        #:   **브리핑에 드러내는** 것이 통제다(「근거가 없는 단계: …」). 미완결을
        #:   어디서나 막으면 그 통제가 **도달 불가능**해지고, 「빠진 것을 숨기지 않는다」는
        #:   장치가 조용히 사라진다.
        #: ⚠️ 두 규칙이 실제로 부딪히는 자리이므로 **한쪽을 조용히 이기게 두지 않는다** —
        #:   이 좁힘은 기록하고 확인을 받아야 한다(인수인계 §미결 1).
        from_runtime = bool(str((path or {}).get("query_id", "") or "").strip())
        if blocked or (incomplete and from_runtime):
            raise DecisionError(
                "이 경로는 아직 계산할 수 없어 숫자 안건을 만들지 않습니다 — "
                "계산되지 않은 경로 옆에 숫자를 놓으면 그 숫자가 답으로 읽힙니다.")

        #: ★★★ [2026-08-21 B1.2-1a P0] **완결된 경로라도 숫자가 그 경로에서 나왔다는
        #:   결속이 없으면 숫자 안건을 만들지 않는다.**
        #:
        #: ⚠️⚠️ B1.2-1 은 「계산 못 하는 경로」만 막았다. 그래서 이런 구멍이 남았다 —
        #:
        #:       정성 런타임 경로(`complete=True`)  +  그 경로와 **결속되지 않은**
        #:       기존 시나리오 엔진의 base/scenario   →  숫자 Decision Package 생성·발간
        #:
        #:   즉 「계산할 수 없습니다」는 사라졌지만 **숫자는 여전히 남의 것**이었다. 재감사에서
        #:   실제 발간 회귀가 바로 그 방식으로 통과하고 있던 것이 드러났다.
        #:
        #: ★ 계산 결과와 `query_id`·`path_fingerprint` 를 **대조**하는 것이 B2 이고 아직 없다.
        #:   없는 대조를 있는 척하지 않는다 — 대신 **호출자가 결속을 선언**하게 하고, 선언이
        #:   없거나 어긋나면 막는다. B2 가 오면 계산기가 그 값을 만들고 호출자는 그대로 넘긴다.
        #: ⚠️ 「일단 만들고 B2 에서 검증하자」는 안 된다. 안건은 원장에 남고 발간으로 나간다 —
        #:   나간 뒤에 틀렸다고 알아도 그 결정은 이미 내려져 있다.
        want_q = str((path or {}).get("query_id", "") or "").strip()
        want_fp = str((path or {}).get("path_fingerprint", "") or "").strip()
        if want_q or want_fp:
            b = calc_binding or {}
            got_q = str(b.get("query_id", "") or "").strip()
            got_fp = str(b.get("path_fingerprint", "") or "").strip()
            if not (got_q or got_fp):
                raise DecisionError(
                    "이 숫자가 이 경로에서 나왔다는 결속이 없어 숫자 안건을 만들지 않습니다 "
                    "— 경로 옆의 숫자는 그 경로의 답으로 읽힙니다. 계산기가 "
                    "`calc_binding={'query_id':…, 'path_fingerprint':…}` 을 함께 넘기게 "
                    "하십시오(B2 결과↔경로 대조가 오기 전까지의 계약입니다).")
            if ((want_q and got_q and got_q != want_q)
                    or (want_fp and got_fp and got_fp != want_fp)):
                raise DecisionError(
                    f"숫자와 경로가 다른 것을 가리킵니다 — 경로는 "
                    f"query_id={want_q or '(없음)'}·fp={want_fp[:12] or '(없음)'} 인데 "
                    f"계산 결과는 query_id={got_q or '(없음)'}·fp={got_fp[:12] or '(없음)'} "
                    f"입니다. 다른 경로의 숫자를 이 안건에 붙일 수 없습니다.")
    if base.baseline_fingerprint != scenario.baseline_fingerprint:
        #: ★★★ 다른 기준선으로 만든 두 결과를 나란히 놓으면, 그 차이는 **가정 때문이
        #:   아니라 데이터 때문**일 수 있다. 그리고 화면은 그것을 구분해 주지 않는다.
        raise DecisionError(
            "기준선이 다른 두 결과를 비교하지 않습니다 — 그 차이가 가정 때문인지 "
            "데이터 때문인지 구분할 수 없습니다.")

    rows = cg.compare(base, scenario)
    evidence = {
        "baseline_fingerprint": base.baseline_fingerprint,
        "baseline_id": str(getattr(baseline, "build_id", "") or ""),
        "snapshot_ids": list(getattr(baseline, "snapshot_ids", []) or []),
        "as_of": str(getattr(baseline, "as_of", "") or ""),
        "calc_version": base.calc_version,
        "assumptions": dict(scenario.assumptions),
        "result_fingerprint": scenario.fingerprint,
        #: 온톨로지 경로가 있으면 **계보**로 붙인다(없으면 없다고 적는다).
        "impact_path": (path or {}).get("path", []),
        "missing_evidence": (path or {}).get("missing_evidence", []),
        #: ★★★ [2026-08-21 B1.1-5] **경로 정체성을 싣는다.**
        #:
        #: ⚠️⚠️ 없으면 「이 안건은 어느 질의의 어느 경로에서 나왔는가」에 답할 수 없다.
        #:   결과 지문(`result_fingerprint`)은 **계산**을 재현하지만 **경로**를 재현하지
        #:   않는다 — 같은 숫자를 다른 길로도 만들 수 있다.
        #: ★ `evidence` 는 그대로 `decision_case` 에 저장되고 `evidence_hash` 에 들어가므로,
        #:   여기 실으면 **원장과 발간까지 그대로 따라간다.**
        #: ⚠️ 경로가 없으면 빈 문자열이다 — 지어내지 않는다.
        "query_id": str((path or {}).get("query_id", "") or ""),
        "path_fingerprint": str((path or {}).get("path_fingerprint", "") or ""),
        #: ⚠️ 계산이 막혔다는 사실도 근거의 일부다. 숨기면 그 보고는 «전부 계산된 것» 으로 읽힌다.
        "calculation_blocked": bool((path or {}).get("calculation_blocked", False)),
        #: ★★★ 같은 사실을 **사람이 읽는 이름**으로도 싣는다(설계 §12).
        #:   `purchase_orders` 를 경영 브리핑에 그대로 내보내면 읽는 사람은 그것이
        #:   무엇인지 모른 채 「모르는 게 있구나」로만 넘긴다.
        "missing_steps": (path or {}).get("missing_steps", []),
        #: ★ [B1.2-1a] **숫자가 어느 경로에서 나왔다고 선언됐는가.** 원장·발간까지 따라간다 —
        #:   나중에 「이 숫자는 이 경로 것이었나」를 물을 수 있어야 한다.
        "calc_binding": {
            "query_id": str((calc_binding or {}).get("query_id", "") or ""),
            "path_fingerprint": str((calc_binding or {}).get("path_fingerprint", "") or ""),
        },
    }
    #: ★ 안건의 «질문» 은 가장 크게 움직인 결과에서 뽑는다 — 지어내지 않는다.
    moved = sorted((r for r in rows if r["delta"]), key=lambda r: -abs(r["delta"]))
    question = (f"{moved[0]['label']}이(가) {moved[0]['delta']:+,.0f}"
                f"{moved[0]['unit']} 변합니다 — 지금 무엇을 결정해야 합니까?"
                if moved else "가정을 바꿔도 결과가 변하지 않습니다 — 확인이 필요합니다.")

    return Package(title=str(title).strip(), question=question,
                   owner=str(owner).strip(), due=str(due).strip(),
                   evidence=evidence, views=[_view(v, rows) for v in VIEWS],
                   data_kind=str(base.data_kind or ""))


def briefing_lines(pkg: Package) -> List[str]:
    """경영 브리핑 본문. **표에서 조립한다 — 생성하지 않는다.**

    ⚠️ 그럴듯한 요약을 만들면 그 요약이 원본과 갈라지고, 사람은 요약만 읽는다."""
    out = [f"[{_label(pkg.data_kind)}]", pkg.title, pkg.question, ""]
    decider = [v for v in pkg.views if v["view"] == VIEW_DECIDER][0]
    for row in decider["highlights"]:
        pct = "" if row["delta_pct"] is None else f" ({row['delta_pct']:+.1f}%)"
        out.append(f"· {row['label']}: {row['base']:,.0f} → {row['scenario']:,.0f}"
                   f"{row['unit']} · {row['delta']:+,.0f}{pct}")
    out += ["", f"실행 책임자: {pkg.owner} · 기한: {pkg.due}",
            f"근거: 기준선 {pkg.evidence['baseline_fingerprint'][:12]} · "
            f"산식 {pkg.evidence['calc_version']} · "
            f"기준시점 {pkg.evidence['as_of'] or '(없음)'}"]
    if pkg.evidence["missing_evidence"]:
        #: ⚠️ 근거가 빠진 칸을 브리핑에서 숨기지 않는다 — 숨기면 그 보고는 «전부
        #:   설명된 것» 으로 읽힌다.
        #: ★ 이름이 있으면 이름으로 말한다. 없으면 계약키라도 적는다 — 「빠진 것이
        #:   있다」는 사실이 이름 유무보다 먼저다.
        named = [str(st.get("label") or st.get("dataset_key") or "")
                 for st in (pkg.evidence.get("missing_steps") or [])]
        out.append("⚠️ 근거가 없는 단계: "
                   + ", ".join(named or pkg.evidence["missing_evidence"]))
    return out
