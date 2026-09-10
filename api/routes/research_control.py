"""[DAO-15] 연구·공공자료 «추천» 라우트 — 어디를 볼지 알려준다. 받아오지는 않는다.

## 왜 `/acquisition` 이 아니라 `/research` 인가

이 라우트는 **수집하지 않는다.** `/external/acquisition/...` 아래 두면 「수집 작업의
일부」로 읽히고, 그러면 화면도 원장도 그렇게 취급한다. 수집 작업(job)은 상태·원장·격리
적재를 갖지만 여기는 **아무것도 저장하지 않는다.**

⚠️ **다만 `/external/research` 가 「안 가져온다」는 뜻은 아니다.** 이 네임스페이스에는
  이미 `external_research` 의 프로필·작업·후보 라우트가 있고 **그쪽은 승인된 도메인에서
  실제로 가져온다.** 즉 접두사로는 구분되지 않는다 — 구분은 라우트 단위다:

    /research/profiles · /jobs · /candidates   승인 도메인에서 «가져온다»(기존)
    /research/sources  · /recommend            아무 데도 «접속하지 않는다»(여기)

  ★ 그래서 응답의 `notice` 와 `notes` 가 그 사실을 매번 말한다. 접두사가 대신 말해 주지
    않으므로 **본문이 말해야 한다.**

## 권한

읽기 전용 조언이라 `PROJECT_RUN` 이다. 아무것도 바꾸지 않으므로 `ADMIN_DATA_ACCESS` 를
요구할 이유가 없고, 요구하면 정작 자료를 찾아야 하는 사람이 못 쓴다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import Principal, assert_identified, current_principal
from core import route_authority
from core.external_intelligence import research_catalog as RC
from core.external_intelligence import research_recommender as RR

WHAT = "연구자료 원천 추천"

router = APIRouter(prefix="/api/v1/external/research",
                   dependencies=[Depends(route_authority.guard)])


def _source_card(s: RC.ResearchSource) -> Dict[str, Any]:
    """화면이 그릴 원천 카드. **화면이 문구를 새로 지어내지 않게** 여기서 다 준다."""
    return {
        "source_key": s.source_key, "name_ko": s.name_ko, "publisher": s.publisher,
        "home_url": s.home_url, "listing_url": s.listing_url, "series": list(s.series),
        "what_it_gives": s.what_it_gives, "topics": list(s.topics),
        "use_cases": list(s.use_cases), "industry_codes": list(s.industry_codes),
        "language": s.language, "access": s.access,
        "access_label": RC.ACCESS_KINDS.get(s.access, s.access),
        "update_cycle": s.update_cycle,
        "target_contract_keys": list(s.target_contract_keys),
        "evidence_level": s.evidence_level, "trust_grade": s.trust_grade,
        "caveats": list(s.caveats),
        #: ⚠️ 링크 확인 여부를 «숨기지 않는다» — 카탈로그가 조용히 낡지 않게 하는 장치.
        "link_verified": s.link_verified, "link_checked_at": s.link_checked_at,
    }


@router.get("/sources")
async def sources(use_case: str = "", topic: str = "",
                  p: Principal = Depends(current_principal)):
    """카탈로그 전체(또는 걸러낸 것). **닫힌 목록이다** — 여기 없는 기관은 추천되지 않는다."""
    assert_identified(p, WHAT)
    if use_case and use_case not in RC.USE_CASES:
        raise HTTPException(status_code=400,
                            detail=f"용도는 {sorted(RC.USE_CASES)} 중 하나여야 합니다.")
    if topic and topic not in RC.TOPICS:
        raise HTTPException(status_code=400,
                            detail=f"주제는 {list(RC.TOPICS)} 중 하나여야 합니다.")
    rows = [s for s in RC.CATALOG
            if (not use_case or use_case in s.use_cases)
            and (not topic or topic in s.topics)]
    return {"status": "success", "data": {
        "sources": [_source_card(s) for s in rows],
        "total_in_catalog": len(RC.CATALOG),
        "use_cases": RC.USE_CASES, "topics": list(RC.TOPICS),
        "access_kinds": RC.ACCESS_KINDS,
        "unverified_links": sum(1 for s in rows if not s.link_verified),
        "notice": ("이 목록은 «어디를 볼지»입니다. 자료를 받아오는 것은 사용자가 직접 하며 "
                   "시스템이 해당 사이트에 접속하지 않습니다."),
    }}


class RecommendBody(BaseModel):
    """⚠️ 회사 컨텍스트를 **호출부가 준다.** 이 라우트가 저장소를 열지 않는다 —
    공개 기업정보 기반 산업분류가 정리되면 그쪽을 읽어 여기로 넘기면 된다."""
    company_name: str = ""
    industry_code: str = Field("", description="KSIC. 예: C2412(비철금속 제련·정련)")
    products: List[str] = Field(default_factory=list)
    regions: List[str] = Field(default_factory=list)
    use_case: str = ""
    topics: List[str] = Field(default_factory=list)
    exclude: List[str] = Field(default_factory=list,
                               description="이미 확보했거나 쓰지 않기로 한 source_key")
    include_paid: bool = True
    limit: int = 8


@router.post("/recommend")
async def recommend(body: RecommendBody, p: Principal = Depends(current_principal)):
    """「이 회사·이 목적이면 어디를 보라」. **아무것도 저장하지 않고 받아오지도 않는다.**"""
    assert_identified(p, WHAT)
    ctx = RR.CompanyContext(
        company_name=body.company_name.strip(), industry_code=body.industry_code.strip(),
        products=tuple(body.products), regions=tuple(body.regions),
        source_note="API 요청")
    try:
        out = RR.recommend(ctx, use_case=body.use_case, topics=body.topics,
                           exclude=body.exclude, include_paid=body.include_paid,
                           limit=body.limit)
    except RR.RecommenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"status": "success", "data": {
        "items": [{
            "rank": i, "score": r.score, "why": list(r.why), "warnings": list(r.warnings),
            "action": r.action, "source": _source_card(r.source),
        } for i, r in enumerate(out.items, 1)],
        #: ★ 지시 3 — 고르지 «않은» 것과 사유도 함께. 조용히 빼면 없는 것으로 읽힌다.
        "excluded": [{"source_key": e.source_key, "name_ko": e.name_ko,
                      "reason": e.reason} for e in out.excluded],
        "query": dict(out.query), "notes": list(out.notes),
        #: 추천 + 제외 = 카탈로그 전체. 화면이 이것을 확인할 수 있게 내려준다.
        "accounted": out.accounted, "total_in_catalog": len(RC.CATALOG),
    }}
