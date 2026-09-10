"""[DAO-15] 연구·공공자료 추천기 — 「이 회사·이 목적이면 어디를 보라」.

## 이것이 하지 «않는» 일

★★★ **네트워크를 만지지 않는다.** 받아오는 행위는 사람이 한다(2026-09-08 결정).
★★★ **원천을 만들지 않는다.** `research_catalog.CATALOG` 에서 «고를» 뿐이다.

두 번째가 이 모듈의 존재 이유다. 「이 회사에 맞는 연구기관을 추천해」를 LLM 에게 그냥
물으면 **그럴듯한 기관명과 URL 을 지어낸다.** 그러면 사용자는 없는 사이트를 찾아 헤매고,
자동 수집을 그만두며 없앤 신뢰 문제가 추천 단계로 옮겨올 뿐이다.

    선택   결정론적 — 이 파일. KSIC 접두사·주제·용도 매칭
    설명   사람이 읽는 문장. LLM 이 «거들» 수는 있으나 **목록을 바꿀 수 없다**

`request_interpreter` 가 LLM 제안을 등록부와 대조해 거부하는 것과 같은 구조다.

## ⚠️ 회사 컨텍스트를 «주입받는다» — 직접 읽지 않는다

`industry_code` 는 `EnterpriseEntity` 에도 있고, 공개 기업정보 기반 산업분류를 별도로
정리하는 작업이 진행 중이다(2026-09-08). 어느 쪽이 정본이 되든 이 모듈은 바뀌지 않도록
**컨텍스트를 인자로 받는다.** 저장소를 직접 열면 정본이 바뀔 때 여기까지 다시 짜야 한다.

## 왜 「제외한 것과 사유」도 돌려주나

지시 3 이 원천 추천에 요구한 것이 그것이고, `ProviderRegistry.ranked()` 도 같은 모양이다.
⚠️ 조용히 빼면 화면이 「왜 KOMIR 은 안 보이나」에 답할 수 없다. 그리고 사용자는 목록에
  없는 것을 «없는 것»으로 여긴다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.external_intelligence import research_catalog as RC


class RecommenderError(ValueError):
    pass


#: 점수 배점. **한 곳에 모아 둔다** — 흩어 두면 왜 이 순서인지 설명할 수 없다.
W_INDUSTRY_EXACT = 40      # KSIC 가 세분류까지 맞는다
W_INDUSTRY_PREFIX = 8      # 접두사 한 글자당 (C24 는 24점, C 는 8점)
W_INDUSTRY_AGNOSTIC = 6    # 업종 무관 원천(거시·해외시장)의 기본점
W_TOPIC = 10               # 요청 주제 하나 맞을 때마다
W_USE_CASE = 15            # 요청 용도가 맞을 때
W_EVIDENCE = {"PUBLIC_FILING": 12, "OFFICIAL_ANNOUNCEMENT": 8,
              "VERIFIED_RESEARCH": 10, "LICENSED_INDUSTRY_DATA": 4}
W_ACCESS = {"free": 6, "free_signup": 3, "mixed": 0, "paid": -4}

#: 제외 사유 — 닫힌 어휘. 화면이 이 코드로 묶는다.
EXCLUDED_USE_CASE = "요청한 용도의 자료가 아닙니다"
EXCLUDED_INDUSTRY = "이 업종과 연결되지 않습니다"
EXCLUDED_TOPIC = "요청한 주제를 다루지 않습니다"
EXCLUDED_USER = "사용자가 제외했습니다(이미 확보했거나 쓰지 않기로 함)"
EXCLUDED_RANK = "더 잘 맞는 원천에 밀렸습니다"


@dataclass(frozen=True)
class CompanyContext:
    """추천의 입력. **주입받는다** — 이 모듈이 저장소를 열지 않는다.

    ⚠️ `industry_code` 가 비어도 동작해야 한다. 산업분류 정리가 끝나기 전이거나,
      회사가 아직 업종을 안 정했을 수 있다 — 그때는 «업종 무관» 원천과 요청 주제로만
      고르고, 그 사실을 결과에 적는다(조용히 좁히지 않는다)."""
    company_name: str = ""
    industry_code: str = ""              # KSIC. 예: "C2412"(비철금속 제련·정련)
    products: Tuple[str, ...] = ()       # "전기동", "아연괴" — 지금은 설명에만 쓴다
    regions: Tuple[str, ...] = ()        # "온산", "베트남" — 지금은 설명에만 쓴다
    source_note: str = ""                # 이 컨텍스트가 어디서 왔는가(계보)


@dataclass(frozen=True)
class Recommendation:
    """한 곳에 대한 추천. **사용자가 «가서 받아야» 하므로 행동 가능해야 한다.**"""
    source: RC.ResearchSource
    score: int
    #: 왜 이것이 이 회사에 맞는가 — **매칭된 사실에서 나온다.** 지어내지 않는다.
    why: Tuple[str, ...]
    #: 가기 전에 알아야 할 것(이용조건·한계 + 링크 미확인).
    warnings: Tuple[str, ...]

    @property
    def action(self) -> Dict[str, Any]:
        """사용자가 할 일. 기관 이름만으로는 쓸모가 없다."""
        s = self.source
        return {"open": s.listing_url, "look_for": list(s.series),
                "access": RC.ACCESS_KINDS.get(s.access, s.access), "language": s.language,
                "update_cycle": s.update_cycle}


@dataclass(frozen=True)
class Excluded:
    source_key: str
    name_ko: str
    reason: str


@dataclass(frozen=True)
class RecommendationSet:
    items: Tuple[Recommendation, ...] = ()
    excluded: Tuple[Excluded, ...] = ()
    #: 어떤 조건으로 골랐는가 — 결과만 보고 조건을 되짚을 수 있어야 한다.
    query: Mapping[str, Any] = field(default_factory=dict)
    #: ⚠️ 사람에게 알려야 할 «추천 자체의» 한계.
    notes: Tuple[str, ...] = ()

    @property
    def accounted(self) -> bool:
        """카탈로그의 모든 원천이 «추천됐거나 사유와 함께 빠졌는가».

        ⚠️ 조용히 사라지는 원천이 없어야 한다 — 그러면 카탈로그에 넣은 의미가 없다."""
        return len(self.items) + len(self.excluded) == len(RC.CATALOG)


# ── 매칭 — 전부 결정론적 ─────────────────────────────────────────────────────
def industry_match(source: RC.ResearchSource, industry_code: str) -> Tuple[bool, int, str]:
    """KSIC **접두사** 매칭. 계층 코드라 접두사가 곧 포함관계다.

    ⚠️ 문자열 일치로 하면 `C2412` 회사가 `C24` 원천을 못 만난다 — 카탈로그를 세분류마다
      다 적어야 하고, 하나만 빠뜨려도 조용히 0건이 된다."""
    code = str(industry_code or "").strip().upper()
    if not source.industry_codes:
        return True, W_INDUSTRY_AGNOSTIC, "업종을 가리지 않는 자료입니다"
    if not code:
        #: 회사 업종을 모른다 — 업종 특화 원천을 «배제»하지 않는다. 다만 가점도 없다.
        return True, 0, "회사 업종이 아직 설정되지 않아 업종 가점 없이 포함했습니다"
    best, label = -1, ""
    for tag in source.industry_codes:
        t = str(tag).strip().upper()
        if code == t:
            return True, W_INDUSTRY_EXACT, f"업종 {code} 에 정확히 해당합니다"
        if code.startswith(t) and len(t) > best:
            best, label = len(t), t
    if best < 0:
        return False, 0, ""
    return True, W_INDUSTRY_PREFIX * best, f"업종 {code} 가 {label} 계열에 속합니다"


def _topic_hits(source: RC.ResearchSource, topics: Sequence[str]) -> Tuple[str, ...]:
    want = {str(t).strip() for t in topics if str(t).strip()}
    return tuple(t for t in source.topics if t in want)


def recommend(context: CompanyContext, *, use_case: str = "",
              topics: Sequence[str] = (), exclude: Sequence[str] = (),
              include_paid: bool = True, limit: int = 8) -> RecommendationSet:
    """추천 한 벌. **네트워크를 만지지 않는다.**

    `use_case` 를 비우면 용도로 거르지 않는다. `topics` 를 비우면 주제 가점만 없다."""
    uc = str(use_case or "").strip()
    if uc and uc not in RC.USE_CASES:
        raise RecommenderError(
            f"모르는 용도입니다: {uc!r} — {sorted(RC.USE_CASES)} 중 하나여야 합니다.")
    for t in topics:
        if str(t).strip() and str(t).strip() not in RC.TOPICS:
            raise RecommenderError(f"모르는 주제입니다: {t!r}")

    dropped = {str(k).strip() for k in exclude if str(k).strip()}
    scored: List[Tuple[int, Recommendation]] = []
    excluded: List[Excluded] = []

    for s in RC.CATALOG:
        if s.source_key in dropped:
            excluded.append(Excluded(s.source_key, s.name_ko, EXCLUDED_USER))
            continue
        if uc and uc not in s.use_cases:
            excluded.append(Excluded(s.source_key, s.name_ko, EXCLUDED_USE_CASE))
            continue
        ok, ind_score, ind_why = industry_match(s, context.industry_code)
        if not ok:
            excluded.append(Excluded(s.source_key, s.name_ko, EXCLUDED_INDUSTRY))
            continue
        hits = _topic_hits(s, topics)
        if topics and not hits:
            excluded.append(Excluded(s.source_key, s.name_ko, EXCLUDED_TOPIC))
            continue
        if not include_paid and s.access == "paid":
            excluded.append(Excluded(s.source_key, s.name_ko,
                                     "유료 구독이 필요해 제외했습니다"))
            continue

        score = (ind_score + W_TOPIC * len(hits)
                 + (W_USE_CASE if uc else 0)
                 + W_EVIDENCE.get(s.evidence_level, 0)
                 + W_ACCESS.get(s.access, 0))

        why: List[str] = []
        if ind_why:
            why.append(ind_why)
        if hits:
            why.append(f"요청 주제({' · '.join(hits)})를 다룹니다")
        if uc:
            why.append(RC.USE_CASES[uc])
        why.append(s.what_it_gives)

        warnings: List[str] = list(s.caveats)
        if not s.link_verified:
            #: ★★★ 카탈로그가 낡아도 «조용히» 낡지 않게 하는 장치.
            warnings.append("⚠️ 링크를 사람이 확인한 기록이 없습니다 — 페이지가 옮겨졌을 수 "
                            "있습니다. 열리지 않으면 카탈로그를 고쳐야 합니다.")
        if s.access in ("paid", "mixed"):
            warnings.append("⚠️ 이용조건을 확인하십시오 — 사내 적재·재배포가 제한될 수 있습니다.")

        scored.append((score, Recommendation(source=s, score=score, why=tuple(why),
                                             warnings=tuple(warnings))))

    #: 점수 내림차순, 같으면 키 오름차순 — **결정론적 순서**여야 같은 질문에 같은 답이 나온다.
    scored.sort(key=lambda p: (-p[0], p[1].source.source_key))
    top = [r for _, r in scored[:max(0, int(limit))]]
    for _, r in scored[len(top):]:
        excluded.append(Excluded(r.source.source_key, r.source.name_ko, EXCLUDED_RANK))

    notes: List[str] = []
    if not str(context.industry_code or "").strip():
        notes.append("회사 업종(KSIC)이 설정되지 않아 업종 기반 순위가 적용되지 않았습니다.")
    unverified = sum(1 for r in top if not r.source.link_verified)
    if unverified:
        notes.append(f"추천 {len(top)}곳 중 {unverified}곳은 링크가 사람 확인 전입니다.")
    notes.append("이 목록은 «어디를 볼지»이며, 자료를 받아오는 것은 사용자가 직접 합니다 — "
                 "시스템이 해당 사이트에 접속하지 않습니다.")

    return RecommendationSet(
        items=tuple(top), excluded=tuple(excluded), notes=tuple(notes),
        query={"company_name": context.company_name,
               "industry_code": context.industry_code, "use_case": uc,
               "topics": list(topics), "exclude": sorted(dropped),
               "include_paid": bool(include_paid), "limit": int(limit)})


# ── LLM 에게 넘길 것 ─────────────────────────────────────────────────────────
def llm_brief(result: RecommendationSet) -> Dict[str, Any]:
    """LLM 이 설명 문장을 쓸 때 넘기는 것. **구조적으로 목록을 바꿀 수 없다.**

    ★★★ LLM 은 이 결과를 «다듬을» 수만 있다. 여기 없는 기관을 더하면 그것은 환각이고,
      호출부는 `source_key` 가 카탈로그에 있는지 다시 확인해야 한다(`verify_llm_output`).

    ⚠️ 회사 내부 레코드는 한 줄도 들어가지 않는다(지시 6) — 카탈로그는 전부 공개 정보다."""
    return {
        "query": dict(result.query),
        "sources": [{"source_key": r.source.source_key, "name_ko": r.source.name_ko,
                     "publisher": r.source.publisher, "what_it_gives": r.source.what_it_gives,
                     "series": list(r.source.series), "language": r.source.language,
                     "access": r.source.access, "update_cycle": r.source.update_cycle,
                     "why": list(r.why), "warnings": list(r.warnings)}
                    for r in result.items],
        "rules": ["여기 없는 기관을 추가하지 마십시오.",
                  "URL 을 지어내지 마십시오 — 링크는 시스템이 붙입니다.",
                  "받아오는 행위는 사용자가 합니다. 시스템이 수집한다고 쓰지 마십시오."],
    }


def verify_llm_output(source_keys: Sequence[str]) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """LLM 이 돌려준 키를 카탈로그와 대조한다. `(통과, 지어낸 것)`.

    ★★★ 「지시했으니 안 지어낼 것이다」로 두지 않는다 — 이 저장소에서 「주석이 코드를
      대신 주장」한 결함이 이미 여러 번 나왔다. **대조가 통과 조건이다.**"""
    known = set(RC.keys())
    ok, invented = [], []
    for k in source_keys:
        key = str(k or "").strip()
        (ok if key in known else invented).append(key)
    return tuple(ok), tuple(invented)
