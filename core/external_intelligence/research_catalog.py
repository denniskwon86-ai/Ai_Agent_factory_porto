"""[DAO-15] 연구·공공자료 «기관 카탈로그» — 사람이 직접 받아올 곳의 닫힌 목록.

## 이것은 수집기가 아니다

★★★ **이 모듈은 네트워크를 만지지 않는다.** Provider 등록부에도 들어가지 않는다.
  하는 일은 「이 회사·이 목적이면 어느 기관을 보라」를 고르는 것뿐이고, **실제로 받아오는
  행위는 사람이 한다.**

왜 자동 수집을 하지 않기로 했나(2026-09-08 결정):

    RSS·목록 페이지는 수시로 바뀌고 유료화된다. 그때 «나오던 게 안 나오면»
    사용자는 그것을 **우리 시스템의 오류로 읽는다.** 실제로는 기관 사이트가
    개편된 것인데도. 자동 수집은 그 오해를 우리가 떠안는 구조다.

넘기면 네 가지가 동시에 사라진다:

    저작권     사용자가 «자기 자격»으로 받는다 — 우리가 크롤링해 재배포하지 않는다
    유료 구독   구독 있는 사용자가 받는다 — 우리가 구독을 관리하지 않는다
    로그인     우리가 인증을 다루지 않는다
    사이트 개편  우리 문제가 아니게 된다

## ★★★ LLM 이 기관을 «생성»하게 두지 않는다

「이 회사에 맞는 연구기관을 추천해」라고 물으면 LLM 은 **그럴듯한 기관명과 URL 을
지어낸다.** 그러면 사용자는 없는 사이트를 찾아 헤매고, 자동 수집에서 없앤 신뢰 문제가
추천 단계로 옮겨올 뿐이다.

그래서 이 파일이 **닫힌 목록**이다. 추천기는 여기서 «고를» 수만 있고 «더할» 수 없다.
`request_interpreter` 가 LLM 이 제안한 `provider_ids` 를 등록부와 대조해 거부하는 것과
같은 구조다.

## ⚠️ 링크는 «미확인» 이 기본값이다

기관 URL 과 이용조건은 낡는다. 그래서 `link_checked_at` 이 비어 있으면 추천 결과가
**「링크 미확인」을 함께 표시한다.** 사람이 가 보고 확인해야 채워진다.

★ 이것이 자동 수집보다 나은 점: 카탈로그가 낡아도 **조용히 죽지 않는다.** 사용자가
  가 보고 「링크가 죽었다」를 알 수 있고, 그러면 카탈로그가 고쳐진다.

## 업종 매칭은 KSIC 접두사다

`EnterpriseEntity.industry_code` 가 KSIC 다(`C2412` = 비철금속 제련·정련). 계층 코드라
접두사가 곧 포함관계다 — `C2412` ⊂ `C24` ⊂ `C`. 카탈로그 항목이 `C24` 를 달면
`C2412` 회사에 맞는다. **문자열 일치가 아니라 접두사 일치**여야 하는 이유다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


class ResearchCatalogError(ValueError):
    """카탈로그 자체가 잘못된 경우 — 기동 시 드러난다."""


# ── 닫힌 어휘 ────────────────────────────────────────────────────────────────
#: 무엇에 쓰는 자료인가. ⚠️ 화면·추천기가 이 목록 밖의 값을 만들지 않는다.
USE_CASES: Dict[str, str] = {
    "competitor_analysis": "경쟁사 분석 — 상대의 규모·설비·원가 구조를 가늠한다",
    "new_business": "신규 사업 시뮬레이션 — 시장·국가·수요를 가늠한다",
    "cost_driver": "원가 동인 — 에너지·환경·인건비·물류처럼 우리 원가를 움직이는 것",
    "process_intel": "공정·설비 정보 — 무엇을 어떻게 만드는가",
    "market_outlook": "시황·전망 — 가격과 수급이 어디로 가는가",
}

#: 주제 태그. 업종만으로는 안 갈리는 축이다(같은 업종도 관심사가 다르다).
TOPICS: Tuple[str, ...] = (
    "원자재가격", "광물수급", "에너지", "환경규제", "해외시장",
    "거시경제", "무역통계", "공정기술", "인건비", "물류", "산업전망",
)

#: 접근 방법. ⚠️ 「유료」는 배제 사유가 아니라 **표시**다 — 구독 있는 회사가 있다.
ACCESS_KINDS: Dict[str, str] = {
    "free": "무료·바로 열람",
    "free_signup": "무료·회원가입 필요",
    "paid": "유료 구독 필요",
    "mixed": "일부 무료·일부 유료",
}

#: `competitor_reference.EVIDENCE_LEVELS` 와 같은 어휘를 쓴다 — 새로 만들지 않는다.
#: ⚠️ 여기서 다시 정의하면 두 곳이 갈린다. 검증은 `assert_catalog_sane()` 이 한다.
_EVIDENCE_FALLBACK = ("PUBLIC_FILING", "OFFICIAL_ANNOUNCEMENT",
                      "LICENSED_INDUSTRY_DATA", "VERIFIED_RESEARCH")


@dataclass(frozen=True)
class ResearchSource:
    """사람이 찾아갈 기관 한 곳.

    ⚠️ 「기관 이름」만으로는 쓸모가 없다. 사용자가 **가서 받아와야** 하므로
      `listing_url`(발간물 목록 페이지)과 `series`(찾을 보고서 이름)가 있어야 한다.
      홈페이지 주소만 주면 사용자가 사이트 안에서 다시 헤맨다."""
    source_key: str
    name_ko: str
    publisher: str
    home_url: str
    #: ★ 발간물 «목록» 페이지. 홈이 아니다.
    listing_url: str
    #: 그 안에서 찾을 보고서·시리즈 이름.
    series: Tuple[str, ...]
    what_it_gives: str
    #: KSIC 접두사. 비면 «업종 무관»(거시·해외시장처럼 모든 업종에 맞는 것).
    industry_codes: Tuple[str, ...]
    topics: Tuple[str, ...]
    use_cases: Tuple[str, ...]
    language: str
    access: str
    update_cycle: str
    #: 받아온 자료가 흘러갈 계약. ⚠️ 지금은 «표시»다 — 적재 경로는 아직 없다.
    target_contract_keys: Tuple[str, ...]
    evidence_level: str
    trust_grade: str
    #: ⚠️ 이용조건·한계. 사용자가 가기 «전»에 알아야 하는 것.
    caveats: Tuple[str, ...] = ()
    #: 사람이 링크를 확인한 시각. **비어 있으면 미확인**이고 추천이 그렇게 표시한다.
    link_checked_at: str = ""

    @property
    def link_verified(self) -> bool:
        return bool(str(self.link_checked_at or "").strip())


def _s(**kw) -> ResearchSource:
    return ResearchSource(**kw)


# ── A. 비철·자원 — 경쟁사·원료·시황 ─────────────────────────────────────────
_A: Tuple[ResearchSource, ...] = (
    _s(source_key="KOMIR", name_ko="한국광해광업공단", publisher="한국광해광업공단",
       home_url="https://www.komir.or.kr/", listing_url="https://www.komir.or.kr/",
       series=("자원산업 동향", "광물자원 통계", "자원가격 정보"),
       what_it_gives="국내 관점의 광물 수급·가격 동향과 통계",
       industry_codes=("C24", "B"), topics=("원자재가격", "광물수급", "산업전망"),
       use_cases=("competitor_analysis", "market_outlook"),
       language="ko", access="free", update_cycle="월·분기",
       target_contract_keys=("KNW-01", "EXT-02"),
       evidence_level="VERIFIED_RESEARCH", trust_grade="silver",
       caveats=("국내 관점 요약이 많습니다 — 국제 원계열은 별도 확인이 필요합니다.",)),

    _s(source_key="KIGAM", name_ko="한국지질자원연구원", publisher="KIGAM",
       home_url="https://www.kigam.re.kr/", listing_url="https://www.kigam.re.kr/",
       series=("광물자원 브리프", "자원기술 동향"),
       what_it_gives="광물자원 기술·매장·처리 공정에 관한 국책 연구",
       industry_codes=("C24", "B"), topics=("광물수급", "공정기술"),
       use_cases=("process_intel", "competitor_analysis"),
       language="ko", access="free", update_cycle="비정기",
       target_contract_keys=("KNW-01",),
       evidence_level="VERIFIED_RESEARCH", trust_grade="gold"),

    _s(source_key="USGS_MCS", name_ko="USGS 광물자원 요약(Mineral Commodity Summaries)",
       publisher="U.S. Geological Survey",
       home_url="https://www.usgs.gov/centers/national-minerals-information-center",
       listing_url="https://www.usgs.gov/centers/national-minerals-information-center/"
                   "mineral-commodity-summaries",
       series=("Mineral Commodity Summaries (연간)", "Minerals Yearbook"),
       what_it_gives="품목별·국가별 생산량·매장량·교역. 비철 경쟁 구도의 국제 기준선",
       industry_codes=("C24", "B"), topics=("광물수급", "원자재가격", "무역통계"),
       use_cases=("competitor_analysis", "new_business", "market_outlook"),
       language="en", access="free", update_cycle="연간(1월경)",
       target_contract_keys=("KNW-01", "EXT-02"),
       evidence_level="VERIFIED_RESEARCH", trust_grade="gold",
       caveats=("국가 단위입니다 — 개별 회사 캐파가 아닙니다.",
                "추정치가 포함되며 이후 연도판에서 소급 정정됩니다.")),

    _s(source_key="AU_REQ", name_ko="호주 자원·에너지 분기전망(REQ)",
       publisher="Australian Government, Dept. of Industry Science and Resources",
       home_url="https://www.industry.gov.au/",
       listing_url="https://www.industry.gov.au/publications/"
                   "resources-and-energy-quarterly",
       series=("Resources and Energy Quarterly",),
       what_it_gives="주요 광물·에너지의 분기 가격·수급 전망. 근거와 가정이 함께 실린다",
       industry_codes=("C24", "B"), topics=("원자재가격", "광물수급", "산업전망"),
       use_cases=("market_outlook", "new_business"),
       language="en", access="free", update_cycle="분기",
       target_contract_keys=("KNW-01",),
       evidence_level="VERIFIED_RESEARCH", trust_grade="gold",
       caveats=("호주 수출 관점입니다 — 아시아 제련 마진과 관점이 다릅니다.",)),

    _s(source_key="JOGMEC", name_ko="일본 JOGMEC 금속자원정보",
       publisher="Japan Organization for Metals and Energy Security",
       home_url="https://www.jogmec.go.jp/", listing_url="https://mric.jogmec.go.jp/",
       series=("金属資源レポート", "カレント・トピックス"),
       what_it_gives="아시아 제련 산업 관점의 금속 자원 동향 — 국내와 구도가 가장 비슷하다",
       industry_codes=("C24", "B"), topics=("광물수급", "원자재가격", "공정기술"),
       use_cases=("competitor_analysis", "market_outlook", "process_intel"),
       language="ja", access="free", update_cycle="수시",
       target_contract_keys=("KNW-01",),
       evidence_level="VERIFIED_RESEARCH", trust_grade="silver",
       caveats=("일본어입니다 — 번역 시 원문을 함께 보관해야 합니다.",)),

    _s(source_key="BGS_WMS", name_ko="영국 지질조사소 세계광물통계",
       publisher="British Geological Survey",
       home_url="https://www2.bgs.ac.uk/mineralsuk/",
       listing_url="https://www2.bgs.ac.uk/mineralsuk/statistics/home.html",
       series=("World Mineral Production",),
       what_it_gives="국가별 광물 생산 장기 시계열",
       industry_codes=("C24", "B"), topics=("광물수급", "무역통계"),
       use_cases=("new_business", "competitor_analysis"),
       language="en", access="free", update_cycle="연간",
       target_contract_keys=("KNW-01", "EXT-02"),
       evidence_level="VERIFIED_RESEARCH", trust_grade="gold"),

    _s(source_key="EU_RMIS", name_ko="EU 원자재 정보시스템(RMIS)",
       publisher="European Commission Joint Research Centre",
       home_url="https://rmis.jrc.ec.europa.eu/",
       listing_url="https://rmis.jrc.ec.europa.eu/",
       series=("Raw Materials Profiles", "Critical Raw Materials 보고서"),
       what_it_gives="핵심원자재 공급망·정책. 유럽 규제 방향의 선행 지표",
       industry_codes=("C24", "B"), topics=("광물수급", "환경규제", "해외시장"),
       use_cases=("new_business", "market_outlook"),
       language="en", access="free", update_cycle="비정기",
       target_contract_keys=("KNW-01",),
       evidence_level="VERIFIED_RESEARCH", trust_grade="gold"),

    _s(source_key="KNMA", name_ko="한국비철금속협회", publisher="한국비철금속협회",
       home_url="http://www.nonferrous.or.kr/", listing_url="http://www.nonferrous.or.kr/",
       series=("비철금속 통계", "협회 자료실"),
       what_it_gives="국내 비철 업계 통계와 업계 관점",
       industry_codes=("C24",), topics=("광물수급", "산업전망"),
       use_cases=("competitor_analysis",),
       language="ko", access="free_signup", update_cycle="비정기",
       target_contract_keys=("KNW-01",),
       evidence_level="OFFICIAL_ANNOUNCEMENT", trust_grade="bronze",
       caveats=("업계 단체 자료입니다 — 회원사 이해가 반영될 수 있습니다.",)),

    _s(source_key="ICSG", name_ko="국제구리연구그룹(ICSG)",
       publisher="International Copper Study Group",
       home_url="https://icsg.org/", listing_url="https://icsg.org/copper-factbook/",
       series=("World Copper Factbook", "Monthly Bulletin"),
       what_it_gives="정련구리 생산·소비·재고의 국제 공식 통계",
       industry_codes=("C2412", "C24"), topics=("광물수급", "원자재가격"),
       use_cases=("competitor_analysis", "market_outlook"),
       language="en", access="mixed", update_cycle="월간·연간",
       target_contract_keys=("KNW-01", "EXT-02"),
       evidence_level="LICENSED_INDUSTRY_DATA", trust_grade="gold",
       caveats=("⚠️ Factbook 은 무료이나 월간 통계는 «유료 회원» 전용입니다.",
                "⚠️ 재배포 조건을 계약으로 확인해야 합니다 — 사내 적재도 조건부일 수 있습니다.")),

    _s(source_key="ILZSG", name_ko="국제납아연연구그룹(ILZSG)",
       publisher="International Lead and Zinc Study Group",
       home_url="https://ilzsg.org/", listing_url="https://ilzsg.org/statistics/",
       series=("Lead and Zinc Statistics",),
       what_it_gives="납·아연 생산·소비·재고 국제 통계",
       industry_codes=("C2412", "C24"), topics=("광물수급", "원자재가격"),
       use_cases=("competitor_analysis", "market_outlook"),
       language="en", access="paid", update_cycle="월간",
       target_contract_keys=("KNW-01", "EXT-02"),
       evidence_level="LICENSED_INDUSTRY_DATA", trust_grade="gold",
       caveats=("⚠️ 유료 구독입니다. 구독 없이 접근하지 마십시오.",
                "⚠️ 재배포 금지 조항을 확인해야 합니다.")),
)

# ── B. 산업·거시 — 신규 사업 시뮬레이션 ─────────────────────────────────────
_B: Tuple[ResearchSource, ...] = (
    _s(source_key="KIET", name_ko="산업연구원(KIET)", publisher="산업연구원",
       home_url="https://www.kiet.re.kr/", listing_url="https://www.kiet.re.kr/research",
       series=("산업경제(월간)", "산업전망", "이슈페이퍼"),
       what_it_gives="국내 업종별 경기·전망과 구조 분석",
       industry_codes=(), topics=("산업전망", "거시경제"),
       use_cases=("new_business", "market_outlook", "competitor_analysis"),
       language="ko", access="free", update_cycle="월간·수시",
       target_contract_keys=("KNW-01",),
       evidence_level="VERIFIED_RESEARCH", trust_grade="gold"),

    _s(source_key="KDI", name_ko="한국개발연구원(KDI)", publisher="KDI",
       home_url="https://www.kdi.re.kr/", listing_url="https://www.kdi.re.kr/research",
       series=("경제전망", "KDI 정책연구"),
       what_it_gives="거시 전망과 정책 분석 — 시뮬레이션의 거시 가정 근거",
       industry_codes=(), topics=("거시경제",),
       use_cases=("new_business",),
       language="ko", access="free", update_cycle="반기·수시",
       target_contract_keys=("KNW-01",),
       evidence_level="VERIFIED_RESEARCH", trust_grade="gold"),

    _s(source_key="BOK_RESEARCH", name_ko="한국은행 조사연구·지역경제보고서",
       publisher="한국은행", home_url="https://www.bok.or.kr/",
       listing_url="https://www.bok.or.kr/portal/bbs/B0000217/list.do?menuNo=200088",
       series=("지역경제보고서", "조사통계월보", "BOK 이슈노트"),
       what_it_gives="거시·지역 산업 동향. 공장 소재 지역 경기의 1차 근거",
       industry_codes=(), topics=("거시경제", "산업전망"),
       use_cases=("new_business", "cost_driver"),
       language="ko", access="free", update_cycle="분기·월간",
       target_contract_keys=("KNW-01",),
       evidence_level="OFFICIAL_ANNOUNCEMENT", trust_grade="gold",
       caveats=("수치 계열은 ECOS Provider 로 이미 받고 있습니다 — 보고서는 «해석»이 값입니다.",)),

    _s(source_key="KIEP", name_ko="대외경제정책연구원(KIEP)", publisher="KIEP",
       home_url="https://www.kiep.go.kr/", listing_url="https://www.kiep.go.kr/gallery.es?mid=a10101000000",
       series=("오늘의 세계경제", "연구보고서", "지역연구"),
       what_it_gives="해외 시장·통상 정책. 신규 진출국 검토의 출발점",
       industry_codes=(), topics=("해외시장", "거시경제", "무역통계"),
       use_cases=("new_business",),
       language="ko", access="free", update_cycle="수시",
       target_contract_keys=("KNW-01",),
       evidence_level="VERIFIED_RESEARCH", trust_grade="gold"),

    _s(source_key="KOTRA", name_ko="KOTRA 해외시장뉴스", publisher="대한무역투자진흥공사",
       home_url="https://dream.kotra.or.kr/", listing_url="https://dream.kotra.or.kr/kotranews/index.do",
       series=("국가·지역 정보", "해외시장뉴스", "투자진출 가이드"),
       what_it_gives="국가별 진출 실무 정보 — 규제·인허가·현지 비용",
       industry_codes=(), topics=("해외시장", "무역통계"),
       use_cases=("new_business",),
       language="ko", access="free_signup", update_cycle="수시",
       target_contract_keys=("KNW-01",),
       evidence_level="OFFICIAL_ANNOUNCEMENT", trust_grade="silver",
       caveats=("현지 통신원 보고가 섞입니다 — 작성 시점과 출처를 함께 남겨야 합니다.",)),

    _s(source_key="KITA_IIT", name_ko="무역협회 국제무역통상연구원",
       publisher="한국무역협회", home_url="https://www.kita.net/",
       listing_url="https://www.kita.net/board/totalTradeNews/totalTradeNewsList.do",
       series=("무역통상 리포트", "통상이슈"),
       what_it_gives="수출입 구조와 통상 현안",
       industry_codes=(), topics=("무역통계", "해외시장"),
       use_cases=("new_business", "market_outlook"),
       language="ko", access="free_signup", update_cycle="수시",
       target_contract_keys=("KNW-01",),
       evidence_level="VERIFIED_RESEARCH", trust_grade="silver"),

    _s(source_key="UNCTAD", name_ko="UNCTAD 통계·보고서", publisher="UNCTAD",
       home_url="https://unctad.org/", listing_url="https://unctad.org/publications",
       series=("Trade and Development Report", "Commodities and Development Report"),
       what_it_gives="개도국 시장·원자재 교역 구조",
       industry_codes=(), topics=("해외시장", "무역통계", "원자재가격"),
       use_cases=("new_business",),
       language="en", access="free", update_cycle="연간",
       target_contract_keys=("KNW-01",),
       evidence_level="VERIFIED_RESEARCH", trust_grade="gold"),

    _s(source_key="OECD_ILIBRARY", name_ko="OECD iLibrary", publisher="OECD",
       home_url="https://www.oecd-ilibrary.org/", listing_url="https://www.oecd-ilibrary.org/",
       series=("Economic Outlook", "Environment Working Papers"),
       what_it_gives="회원국 경제·환경 정책 비교",
       industry_codes=(), topics=("거시경제", "환경규제", "해외시장"),
       use_cases=("new_business",),
       language="en", access="mixed", update_cycle="수시",
       target_contract_keys=("KNW-01",),
       evidence_level="VERIFIED_RESEARCH", trust_grade="gold",
       caveats=("⚠️ 상당수 간행물이 유료입니다 — 무료 공개본인지 확인하십시오.",)),
)

# ── C. 원가 동인 ─────────────────────────────────────────────────────────────
_C: Tuple[ResearchSource, ...] = (
    _s(source_key="KEEI", name_ko="에너지경제연구원(KEEI)", publisher="KEEI",
       home_url="https://www.keei.re.kr/", listing_url="https://www.keei.re.kr/research",
       series=("에너지수요전망", "에너지 통계연보", "세계 에너지시장 인사이트"),
       what_it_gives="에너지 가격·수급 전망. 제련업 원가의 큰 축인 전력비의 근거",
       industry_codes=("C24", "C"), topics=("에너지", "원자재가격"),
       use_cases=("cost_driver", "new_business"),
       language="ko", access="free", update_cycle="월간·연간",
       target_contract_keys=("KNW-01", "EXT-03"),
       evidence_level="VERIFIED_RESEARCH", trust_grade="gold",
       caveats=("전망은 요금제 개편 전 가정일 수 있습니다 — 적용 시점을 확인하십시오.",)),

    _s(source_key="KEI", name_ko="한국환경연구원(KEI)", publisher="KEI",
       home_url="https://www.kei.re.kr/", listing_url="https://www.kei.re.kr/board.es?mid=a10101000000",
       series=("환경포럼", "정책보고서"),
       what_it_gives="환경 규제 방향 — 제련업은 규제가 곧 설비투자다",
       industry_codes=("C", "C24"), topics=("환경규제",),
       use_cases=("cost_driver", "new_business"),
       language="ko", access="free", update_cycle="수시",
       target_contract_keys=("KNW-01",),
       evidence_level="VERIFIED_RESEARCH", trust_grade="gold"),

    _s(source_key="KLI", name_ko="한국노동연구원(KLI)", publisher="KLI",
       home_url="https://www.kli.re.kr/", listing_url="https://www.kli.re.kr/kli/researchList.do",
       series=("노동리뷰", "임금·근로시간 연구"),
       what_it_gives="업종별 임금 구조 — 인건비 가정의 근거",
       industry_codes=(), topics=("인건비",),
       use_cases=("cost_driver", "new_business"),
       language="ko", access="free", update_cycle="월간",
       target_contract_keys=("KNW-01",),
       evidence_level="VERIFIED_RESEARCH", trust_grade="gold"),

    _s(source_key="KOTI", name_ko="한국교통연구원(KOTI)", publisher="KOTI",
       home_url="https://www.koti.re.kr/", listing_url="https://www.koti.re.kr/research/reportList.do",
       series=("물류 동향", "교통·물류 연구보고서"),
       what_it_gives="물류비 구조 — 원료 수입·제품 수출 비용 가정",
       industry_codes=(), topics=("물류",),
       use_cases=("cost_driver", "new_business"),
       language="ko", access="free", update_cycle="수시",
       target_contract_keys=("KNW-01",),
       evidence_level="VERIFIED_RESEARCH", trust_grade="silver"),

    _s(source_key="KPX_EPSIS", name_ko="전력거래소 전력통계정보시스템(EPSIS)",
       publisher="한국전력거래소", home_url="https://epsis.kpx.or.kr/",
       listing_url="https://epsis.kpx.or.kr/",
       series=("전력시장 통계", "전력수급 실적"),
       what_it_gives="전력시장 구조·실적. SMP 수치 자체는 이미 Provider 가 받는다",
       industry_codes=("C", "D"), topics=("에너지",),
       use_cases=("cost_driver",),
       language="ko", access="free", update_cycle="월간",
       target_contract_keys=("KNW-01",),
       evidence_level="OFFICIAL_ANNOUNCEMENT", trust_grade="silver",
       caveats=("SMP 일별 수치는 «공공데이터포털 KPX_SMP Provider» 가 이미 수집합니다 — "
                "여기서는 «구조·해석»만 얻습니다.",)),
)

# ── D. 규제·허가 — 경쟁사 공정 정보의 «1차 출처» ────────────────────────────
#: ★★★ 2026-09-08 논의: 「경쟁사 신규 공장 공정은 공개 자료에 없다」고 여겨지지만,
#:   실제로는 «한 곳에 정리돼 있지 않을» 뿐 조각은 공개돼 있다. 이 묶음이 그 조각들이다.
#:   개인 블로그를 믿는 대신 같은 조각을 1차 출처에서 직접 받는다.
_D: Tuple[ResearchSource, ...] = (
    _s(source_key="NIER_IEPS", name_ko="통합환경허가시스템", publisher="환경부·국립환경과학원",
       home_url="https://ieps.nier.go.kr/", listing_url="https://ieps.nier.go.kr/",
       series=("통합환경허가서", "허가배출기준 검토결과"),
       what_it_gives="★ 공정 계통·배출시설·저감설비가 «공개 문서»로 드러난다",
       industry_codes=("C", "C24"), topics=("공정기술", "환경규제"),
       use_cases=("process_intel", "competitor_analysis"),
       language="ko", access="free", update_cycle="허가 시점",
       target_contract_keys=("KNW-01",),
       evidence_level="PUBLIC_FILING", trust_grade="gold",
       caveats=("사업장 단위 문서입니다 — 회사 전체가 아닙니다.",
                "허가 시점 기준이라 이후 변경은 반영되지 않습니다.")),

    _s(source_key="EIASS", name_ko="환경영향평가 정보지원시스템", publisher="환경부",
       home_url="https://www.eiass.go.kr/", listing_url="https://www.eiass.go.kr/",
       series=("환경영향평가서", "전략환경영향평가서"),
       what_it_gives="★ 신규 공장의 공정·규모·투입물. 증설 계획의 1차 근거",
       industry_codes=("C", "C24"), topics=("공정기술", "환경규제"),
       use_cases=("process_intel", "competitor_analysis"),
       language="ko", access="free", update_cycle="사업 시점",
       target_contract_keys=("KNW-01",),
       evidence_level="PUBLIC_FILING", trust_grade="gold",
       caveats=("계획 단계 문서입니다 — 실제 준공 설비와 다를 수 있습니다.",)),

    _s(source_key="KIPRIS", name_ko="특허정보넷 KIPRIS", publisher="한국특허정보원",
       home_url="https://www.kipris.or.kr/", listing_url="https://www.kipris.or.kr/",
       series=("특허·실용신안 공보",),
       what_it_gives="★ 경쟁사가 출원한 «공정 특허» — 무엇을 하려는지가 드러난다",
       industry_codes=("C", "C24"), topics=("공정기술",),
       use_cases=("process_intel", "competitor_analysis"),
       language="ko", access="free", update_cycle="수시",
       target_contract_keys=("KNW-01",),
       evidence_level="PUBLIC_FILING", trust_grade="gold",
       caveats=("출원이 «실제 적용»을 뜻하지 않습니다 — 방어 출원이 많습니다.",)),

    _s(source_key="DART_MAJOR", name_ko="DART 주요사항보고서·설비투자 공시",
       publisher="금융감독원", home_url="https://dart.fss.or.kr/",
       listing_url="https://dart.fss.or.kr/dsab007/main.do",
       series=("주요사항보고서", "신규시설투자 등"),
       what_it_gives="경쟁사 증설·설비투자의 «금액과 시점»",
       industry_codes=(), topics=("공정기술", "산업전망"),
       use_cases=("competitor_analysis", "process_intel"),
       language="ko", access="free", update_cycle="공시 시점",
       target_contract_keys=("PUB-01", "KNW-01"),
       evidence_level="PUBLIC_FILING", trust_grade="gold",
       caveats=("재무제표는 «OPENDART Provider» 가 이미 수집합니다 — "
                "여기서는 정기보고서 밖의 «수시공시»를 봅니다.",)),
)

#: 전체 카탈로그. ★ 추천기는 여기서 «고를» 수만 있고 «더할» 수 없다.
CATALOG: Tuple[ResearchSource, ...] = _A + _B + _C + _D

BY_KEY: Dict[str, ResearchSource] = {s.source_key: s for s in CATALOG}


# ── 카탈로그 자체의 건강 검사 ────────────────────────────────────────────────
def assert_catalog_sane() -> None:
    """카탈로그가 스스로 모순되지 않는지. **기동 시·시험에서 부른다.**

    ⚠️ 닫힌 목록은 «검사되지 않으면» 닫혀 있지 않다. 오타 하나로 매칭이 조용히
      0건이 되는 것이 이 구조의 실패 양식이다."""
    seen = set()
    for s in CATALOG:
        if s.source_key in seen:
            raise ResearchCatalogError(f"중복 키: {s.source_key}")
        seen.add(s.source_key)
        if not s.listing_url or not s.series:
            raise ResearchCatalogError(
                f"{s.source_key}: 사용자가 «가서 받아야» 하므로 목록 페이지와 시리즈가 필요합니다.")
        for t in s.topics:
            if t not in TOPICS:
                raise ResearchCatalogError(f"{s.source_key}: 모르는 주제 {t!r}")
        for u in s.use_cases:
            if u not in USE_CASES:
                raise ResearchCatalogError(f"{s.source_key}: 모르는 용도 {u!r}")
        if s.access not in ACCESS_KINDS:
            raise ResearchCatalogError(f"{s.source_key}: 모르는 접근 방법 {s.access!r}")
        if s.evidence_level not in _evidence_levels():
            raise ResearchCatalogError(f"{s.source_key}: 모르는 근거 등급 {s.evidence_level!r}")
        if s.trust_grade not in _grades():
            raise ResearchCatalogError(f"{s.source_key}: 모르는 신뢰 등급 {s.trust_grade!r}")
        if s.access in ("paid", "mixed") and not s.caveats:
            #: ⚠️ 유료인데 주의사항이 없으면 사용자가 결제 화면에서 처음 안다.
            raise ResearchCatalogError(
                f"{s.source_key}: 유료·혼합 원천은 이용조건 주의사항이 있어야 합니다.")


def _evidence_levels() -> Tuple[str, ...]:
    """`competitor_reference` 의 어휘를 **읽어 온다** — 여기서 다시 정의하지 않는다."""
    try:
        from core.enterprise_context.competitor_reference import EVIDENCE_LEVELS
        return tuple(EVIDENCE_LEVELS)
    except Exception:                                   # noqa: BLE001 - 순환/부재 대비
        return _EVIDENCE_FALLBACK


def _grades() -> Tuple[str, ...]:
    from core.external_intelligence import GRADES
    return tuple(GRADES)


def get(source_key: str) -> Optional[ResearchSource]:
    return BY_KEY.get(str(source_key or "").strip())


def keys() -> Tuple[str, ...]:
    return tuple(BY_KEY)
