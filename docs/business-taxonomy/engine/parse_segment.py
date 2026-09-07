# -*- coding: utf-8 -*-
"""
사업보고서 주석에서 영업부문 뽑기
=================================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

왜 주석인가
-----------
사업보고서 **본문**의 부문 표는 서식이 회사마다 달라 커버리지가 26% 에 그쳤다.
반면 **재무제표 주석**의 영업부문 공시는 K-IFRS 서식을 따르므로 훨씬 표준적이다.

주석에는 두 형태가 함께 실린다.

**① 세로형 — 부문이 행** (주요 재화·용역을 담는다)

    구 분   | 주요 재화 및 용역
    석유화학 | ABS, PC, PE, PP, 아크릴 …
    첨단소재 | 엔지니어링소재, 디스플레이재료, 양극재 …

**② 가로형 — 부문이 열** (수익을 담는 주 형태다)

    구 분              | 2025                                    ← 연도
                       | 석유화학   | 첨단소재  | … | 합 계      ← 부문명
    외부고객으로부터의 수익 | 17,568,310 | 2,638,526 | … | …

**둘을 합쳐야** 부문명 · 주요제품 · 매출이 다 모인다. 이름으로 잇는다.

가로형의 함정 — 열이 밀린다
---------------------------
헤더가 **2단**이다. 첫 행은 연도, 둘째 행이 부문명이다.
그런데 「구 분」 칸이 rowspan 으로 두 행을 덮으므로 **부문명 행에는 첫 열이 없다**.
셀만 뽑으면 헤더는 6칸, 데이터 행은 7칸이 되어 한 칸씩 어긋난다.

그래서 앞이 아니라 **뒤에서부터 맞춘다**. 양쪽 다 「합 계」로 끝나므로 이게 안전하다.
"""
from __future__ import annotations
import re

# 부문이 아닌 열·행 — 합계·조정·재무용어
_비부문 = re.compile(
    r'^(합계|총계|계|소계|구분|연결조정|내부거래|조정|제거|공통|미배분|기타|단위'
    r'|연결후|연결전|당기|전기|당분기|전분기|보고기간|누적'
    r'|주석|제\d'            # 「주 석」 「제 82(당) 기말」 — 재무제표 표의 열 헤더다
    r'|장부|공정가치|수준|등급|Grade|취득|잔액|평가)')
_재무행 = re.compile(
    r'(수익|매출|이익|손실|상각|자산|부채|자본|원가|비용|투자|증감|현금|법인세)')
# 수익 행은 한 표에 여럿 있다. SK이노베이션은 「총매출액·내부매출액·순매출액·
# 기타영업수익」 네 줄이다. **아무거나 잡으면 안 된다** — 「기타영업수익」은
# 배터리 부문에만 값이 있어서, 이 줄을 읽으면 부문이 1건으로 줄어든다.
# 앞선 항목이 더 정확하다. 내부거래 조정 행은 아예 뺀다
_수익우선 = [
    re.compile(r'외부고객'),                          # 내부거래가 이미 빠진 순액
    re.compile(r'(순매출액|순수익|외부매출|총수익|영업수익)'),
    re.compile(r'(총부문수익|부문수익|총매출액|매출액)'),
    re.compile(r'수익'),
]
# **금융권은 수익을 종류별로 쪼개 싣는다.** 신한지주 부문 표에는 「외부고객으로부터의
# 이자손익」과 「수수료손익」이 따로 있어, 하나만 잡으면 부분값이 된다. 종류가 붙은
# 행은 뒤로 밀어 「영업수익」·「총수익」 같은 총액 행이 있으면 그걸 쓰게 한다
_부분수익 = re.compile(r'(이자|수수료|배당|임대료|보험료|리스료)')
_후순위 = 10
# 수익이 아닌 행. **금융권에서 특히 중요하다** — 「법인세비용(수익)」과
# 「이연대출부대수익」이 「수익」이라는 글자 때문에 총액 행처럼 뽑혔다
_수익제외 = re.compile(
    r'(내부|부문간|사내|제거|조정|대체|법인세|비용|관리비|충당|상각|손상'
    r'|기초|기말|증가|감소|환입|전입|이연|배분|평가|처분|환산)')
_라벨칸 = re.compile(r'^(구분|항목|내역|과목|계정)')
_합계열 = re.compile(r'^(합계|총계|계|소계|연결후금액|연결후|전체|총액)$')

# **지역은 부문이 아니다.** K-IFRS 부문 공시에는 ①영업부문 ②지역별 정보 ③주요 고객이
# 나란히 실린다. 지역 표가 부문 표보다 열이 많은 회사가 흔해서, 막지 않으면
# 삼성전자가 「국내·미주·유럽·중국」으로 쪼개진다
_지역 = re.compile(
    r'^(?:국내|국외|해외|내수|수출|직수출|로컬|대한민국|한국|중국|일본|미국|캐나다|멕시코'
    r'|미주|북미|남미|중남미|북중미|아메리카|유럽|구주|동아시아|동남아|서남아|아시아'
    r'|아프리카|중동|오세아니아|인도|베트남|브라질|러시아|기타지역|기타국가)'
    # 지역명은 단독으로 온다. 뒤에 붙어도 되는 건 괄호주석·「및~」·「외」·「지역」뿐이다.
    # 「사업」「부문」이 붙으면 지역이 아니라 부문이다 — 이마트 「해외사업」이 그렇다
    r'(?:및[가-힣]+|\(.*\)|외|지역)?$')
_제품열 = re.compile(r'(주요\s*재화|주요\s*제품|재화\s*및\s*용역|주요\s*서비스|주요\s*사업)')

# 부문을 **정의하는** 표의 열. 제품 열보다 넓다 — 금융권은 제품이 아니라
# 「주된 영업활동」·「부문의 성격」으로 부문을 설명한다
_정의열 = re.compile(
    r'(주요\s*재화|주요\s*제품|재화\s*및\s*용역|주요\s*서비스|주요\s*사업'
    # 「영업활동」 단독은 넣지 않는다 — 현금흐름표의 「영업활동으로 인한 현금흐름」을 잡는다
    r'|주된\s*영업|부문의\s*성격|주요\s*영업)')

# 종속·관계기업 목록 표. 「회사명 | 주요 영업활동 | 지분율 | 소재지」 꼴이라
# 제품 열로 오인된다 — SK하이닉스가 종속기업 18곳을 부문으로 내놓았다
_종속표 = re.compile(r'(지분율|소재지|결산월|업종|설립일)')

# 부문 섹션의 제목. 「33. 부문별 정보」 「4. 영업부문 (연결)」 형태다.
# **번호에 소수점이 있으면 회계정책 설명**이다(「2.27 영업부문」) — 표가 없으므로 뺀다
_섹션 = re.compile(
    r'(?<![\d.])\d{1,2}[.)]\s*(?:부\s*문\s*별\s*정\s*보|영\s*업\s*부\s*문|부\s*문\s*정\s*보)'
    # KB금융은 번호 없이 「사업부문별 정보는 다음과 같습니다」라 쓰고 표를 잇는다.
    # 부문 표가 회계정책 섹션에서 22 만자나 떨어져 있어 번호 제목만으로는 닿지 못한다
    r'|(?:사업)?부\s*문\s*별?\s*정\s*보는\s*다음과\s*같')
_구간 = 120000       # 제목 뒤 이만큼을 부문 섹션으로 본다


# **단일 보고부문**을 명시하는 문구. 이게 있으면 부문이 없는 게 정답이다.
# 기아가 그렇다 — 「하나의 보고부문으로 구성됩니다」라 쓰고 그 아래엔
# 「지역에 따른 부문별 매출액」 표를 싣는다. 막지 않으면 지역이 부문으로 새어든다
_단일 = re.compile(r'(하나의|단일)\s*(보고|영업)?\s*부문')


def single_segment(xml: str) -> bool:
    """주석이 「단일 보고부문」이라고 밝히는가"""
    return any(_단일.search(sec) for sec in _sections(xml))


# 표의 「(단위: 백만원)」 캡션. **회사마다 다르다** — CJ제일제당은 천원이라
# 정규화하지 않으면 다른 회사보다 1000배 큰 값이 나온다.
# 「원」으로 끝나는 것만 금액으로 본다 — 「명」·「%」·「만톤」 같은 캡션도 섞여 있다
_단위 = re.compile(r'단위\s*[:：]\s*([^)<\s]{1,12})')
_배수 = [('백만', 1.0), ('십억', 1000.0), ('천억', 100000.0), ('백억', 10000.0),
         ('천만', 10.0), ('조', 1000000.0), ('억', 100.0), ('천', 0.001),
         ('만', 0.01), ('원', 0.000001)]


def _mult(u: str) -> float | None:
    """단위 문자열 → 백만원 기준 배수"""
    u = u.replace(' ', '').rstrip(',.)')
    if not u.endswith('원'):
        return None
    for key, m in _배수:
        if u.startswith(key):
            return m
    return None


def _text(t: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', t)).strip()


def _num(s: str):
    s = (s or '').replace(',', '').replace('△', '-').replace('(', '-').replace(')', '').strip()
    if not s or s in ('-', '—'):
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def _tables(xml: str) -> list[tuple[list[list[str]], float]]:
    """(표, 백만원 배수) 목록. 단위는 **표 바로 앞의 캡션**을 쓴다"""
    out, mult, pos = [], 1.0, 0
    for m in re.finditer(r'<TABLE[^>]*>.*?</TABLE>', xml, re.S):
        for chunk in (xml[pos:m.start()], m.group(0)):   # 표 앞 · 표 안
            for u in _단위.finditer(chunk):
                v = _mult(u.group(1))
                if v is not None:
                    mult = v
        pos = m.end()
        rows = []
        for tr in re.findall(r'<TR[^>]*>(.*?)</TR>', m.group(0), re.S):
            cells = [_text(c) for c in re.findall(r'<T[DEHU][^>]*>(.*?)</T[DEHU]>', tr, re.S)]
            if any(cells):
                rows.append(cells)
        if len(rows) >= 2:
            out.append((rows, mult))
    return out


def _clean(name: str) -> str:
    """부문명 정리 — 각주 표시((*)·(*3)·*1)와 공백을 턴다"""
    n = re.sub(r'\(\s*\*+\s*\d*\s*\)|\*+\d*', '', name or '').strip()
    return re.sub(r'\s+', ' ', n)


def _부문명(n: str) -> bool:
    """이 칸이 부문 이름일 수 있는가"""
    n = (n or '').strip()
    if not n or len(n) > 20:
        return False
    if _비부문.match(n.replace(' ', '')):
        return False
    if not re.search(r'[가-힣A-Za-z]', n):       # 숫자·기호뿐이면 이름이 아니다
        return False
    if re.fullmatch(r'\d{4}(년|기)?', n):        # 연도 행
        return False
    if _재무행.search(n):
        return False
    if _지역.match(n.replace(' ', '')):         # 지역별 정보 표
        return False
    return True


def _products(tables) -> dict[str, str]:
    """세로형 표에서 {부문명: 주요제품}"""
    out = {}
    for rows, _ in tables:
        hi = next((i for i, r in enumerate(rows[:2]) if _제품열.search(' '.join(r))), None)
        if hi is None:
            continue
        if _종속표.search(' '.join(rows[hi])):        # 종속기업 목록이다
            continue
        for r in rows[hi + 1:]:
            if len(r) < 2:
                continue
            nm = _clean(r[0])
            if not nm or not _부문명(nm):
                continue
            if nm not in out and r[1].strip():
                out[nm] = r[1].strip()
    return out


def _align(header: list[str], pick: list[str], mult: float = 1.0) -> dict[str, int]:
    """
    헤더 칸과 데이터 값을 맞춘다.

    부문마다 **당기·전기 두 칸**을 쓰는 표가 있다(에쓰오일). 헤더 4칸에 데이터
    8칸이 되어 1:1 로 맞출 수 없다. 그래서 stride 1·2 를 모두 시도하고
    **합계 열이 나머지 열의 합과 맞는 쪽**을 택한다 — 이 검증이 정렬을 보증한다.
    """
    fallback: dict[str, int] = {}
    for stride in (1, 2):
        need = len(header) * stride
        if len(pick) < need:
            continue
        vals = pick[-need:][::stride]
        got, parts, total = {}, [], None
        for nm, cell in zip(header, vals):
            v = _num(cell)
            if v is None:
                continue
            if _합계열.match(nm.replace(' ', '')):
                total = v
            else:
                parts.append(v)
                if _부문명(nm):
                    got[nm] = v
        # 합계가 맞으면 이 정렬이 옳다. 오차 1% 는 표시 단위 반올림을 감싼다
        # 합계 검증은 **원값으로** 한다. 배수는 마지막에 곱한다
        if got and total is not None and abs(sum(parts) - total) <= max(2, abs(total) // 100):
            return {k: round(v * mult) for k, v in got.items()}
        if not fallback:
            fallback = {k: round(v * mult) for k, v in got.items()}
    return fallback


def _revenues(tables) -> tuple[dict[str, int], str]:
    """가로형 표에서 {부문명: 매출}. 부문이 열에 있다."""
    best: dict[str, int] = {}
    best_label = ''
    for rows, mult in tables:
        # 부문명이 늘어선 헤더 행을 찾는다. 2단 헤더면 첫 셀부터 부문명이므로
        # r[1:] 이 아니라 **행 전체**를 봐야 한다
        hi = None
        for i, r in enumerate(rows[:4]):
            if len([c for c in (_clean(x) for x in r) if _부문명(c)]) >= 2:
                hi = i
                break
        if hi is None:
            continue
        header = [_clean(c) for c in rows[hi]]
        # 「구 분」 같은 라벨 칸은 부문이 아니다. 떼어내야 데이터와 칸 수가 맞는다
        if header and _라벨칸.match(header[0].replace(' ', '')):
            header = header[1:]

        # 수익 행을 찾는다. 우선순위가 높은 행을 만나면 갈아탄다
        pick, rank = None, len(_수익우선)
        for r in rows[hi + 1:]:
            if not r:
                continue
            label = _clean(r[0]).replace(' ', '')
            if _수익제외.search(label):
                continue
            # 「매출액:」처럼 값이 없는 라벨 행이 있다. 이걸 고르면 표가 통째로
            # 날아간다 — LG생활건강의 실제 값은 아래 「총매출액」 행에 있다
            if not any(_num(c) is not None for c in r[1:]):
                continue
            for k, pat in enumerate(_수익우선):
                if pat.search(label):
                    if _부분수익.search(label):
                        k += _후순위          # 이자·수수료 등 종류별 수익
                    if k < rank:
                        pick, rank = r, k
                    break
            if rank == 0:            # 「외부고객」보다 나은 건 없다
                break
        if not pick:
            continue

        got = _align(header, pick, mult)
        # 같은 표가 당기·전기 두 번 나온다. 먼저 나온 쪽(당기)을 남긴다
        if len(got) > len(best):
            best, best_label = got, _clean(pick[0])
    return best, best_label


def _sections(xml: str) -> list[str]:
    """
    부문 섹션 구간만 잘라낸다.

    **이게 정확도의 핵심이다.** 사업보고서 본문은 12MB 에 표가 수천 개라
    문서 전체를 훑으면 엉뚱한 재무 표가 이긴다. 제목으로 범위를 좁힌다.
    제목이 없으면(주석만 담긴 파일) 문서 전체를 쓴다.
    """
    at = [m.start() for m in _섹션.finditer(xml)]
    return [xml[s:s + _구간] for s in at] if at else [xml]


def _수익먼저(head: list[str]) -> bool:
    """헤더의 첫 금액 항목이 매출인가 — 「매출 | 손익」 순서라야 첫 숫자 칸이 매출이다"""
    txt = [_clean(c).replace(' ', '') for c in head if c.strip()]
    ri = next((i for i, c in enumerate(txt)
               if re.search(r'(매출|수익)', c) and not _수익제외.search(c)), None)
    ii = next((i for i, c in enumerate(txt)
               if re.search(r'(이익|손익|자산|부채|상각)', c)), None)
    return ri is not None and (ii is None or ri < ii)


def _revenues_vertical(tables) -> dict[str, int]:
    """
    부문이 **행**에 있는 표. LS·LS일렉트릭이 이 서식이다.

        영업부문   | 매 출               | 법인세비용차감전순손익
                   | 당기      | 전기    | 당기    | 전기
        전력부문   | 5,023,408 | 4,067,572 | 404,087 | 358,467

    부문명은 **숫자가 아닌 마지막 칸**이고 당기 매출은 **그 다음 칸**이다.
    LS 처럼 「보고부문 | 영업부문」 두 단이고 rowspan 으로 앞 칸이 빠지는 행이
    섞여도(6칸·5칸 혼재) 이 규칙은 견딘다.
    """
    best: dict[str, int] = {}
    for rows, mult in tables:
        head = rows[0] if rows else []
        h0 = _clean(head[0]).replace(' ', '') if head else ''
        if not re.match(r'^(영업부문|보고부문|사업부문|부문)', h0):
            continue
        if not _수익먼저(head):
            continue
        got = {}
        for r in rows[1:]:
            ni = None
            for i, c in enumerate(r):
                if _num(c) is None and _clean(c):
                    ni = i
            if ni is None or ni + 1 >= len(r):
                continue
            nm, v = _clean(r[ni]), _num(r[ni + 1])
            if v is None or not _부문명(nm):
                continue
            got.setdefault(nm, round(v * mult))
        if len(got) > len(best):
            best = got
    return best


def _names_only(tables) -> list[str]:
    """
    매출을 못 구할 때 **부문명만** 건진다.

    금융권 부문 표에는 총수익 행이 없다 — 신한지주는 순이자손익과 순수수료손익을
    따로 싣는다. 종류별 수익을 하나 골라 쓰면 부분값이고(수수료만 잡으면 은행
    부문이 1.25 조가 된다), 합산은 회계 판단이라 파서가 할 일이 아니다.
    사업 분류에 필요한 건 이름이므로 이름만 담는다.

    **교차 확인으로 안전을 잡는다** — 세로형 부문 정의 표와 가로형 표 헤더에
    **둘 다** 나오는 이름만 인정한다. 종속기업 목록은 가로형 헤더로 다시
    나오지 않으므로 이 문턱을 넘지 못한다.
    """
    defs, heads = [], set()
    for rows, _ in tables:
        hi = next((i for i, r in enumerate(rows[:2]) if _정의열.search(' '.join(r))), None)
        if hi is not None and not _종속표.search(' '.join(rows[hi])):
            for r in rows[hi + 1:]:
                if len(r) >= 2 and r[1].strip():
                    nm = _clean(r[0])
                    if _부문명(nm) and nm not in defs:
                        defs.append(nm)
        for r in rows[:4]:
            cand = [_clean(c) for c in r]
            if len([c for c in cand if _부문명(c)]) >= 2:
                heads.update(c for c in cand if _부문명(c))
                break
    both = [d for d in defs
            if d in heads or any(d in h or h in d for h in heads)]
    if len(both) >= 2:
        return both

    # 정의 표가 아예 없는 회사도 있다(신한지주·기업은행). 그러면 가로형 헤더만
    # 쓰되 **세 가지 조건**을 건다 — 부문명이 3개 이상이고, 「합 계」 열이 있고,
    # 표 본문에 손익·수익 행이 있어야 한다. 종속기업 목록은 이 문턱을 넘지 못한다
    for rows, _ in tables:
        for r in rows[:4]:
            cand = [_clean(c) for c in r]
            names = [c for c in cand if _부문명(c)]
            if len(names) < 3:
                continue
            if not any(_합계열.match(c.replace(' ', '')) for c in cand):
                continue
            body = ' '.join(' '.join(x) for x in rows[1:])
            if not re.search(r'(손익|수익|매출)', body):
                continue
            return names
    return []


def parse(xml: str) -> list[dict]:
    """주석·본문 XML → [{'명칭','주요제품','매출'}]"""
    # **단일 보고부문은 문서 단위로 판단한다.** 섹션별로 보면, 그 문구가 없는
    # 다른 섹션에서 엉뚱한 표를 읽는다 — SK하이닉스가 공정가치 서열 표를
    # 「수준 1·2·3」 부문으로 내놓았다
    if single_segment(xml):
        return []
    best, score = [], -1
    for sec in _sections(xml):
        got = _parse_one(sec)
        # 부문이 많고 주요제품까지 붙은 쪽이 낫다
        sc = len(got) + sum(1 for g in got if g['주요제품'])
        if sc > score:
            best, score = got, sc
    return best


def _parse_one(xml: str) -> list[dict]:
    tables = _tables(xml)
    prods = _products(tables)
    # 가로형(부문이 열)이 주 서식이지만 세로형(부문이 행)도 있다. 많이 잡는 쪽을 쓴다
    revs, label = _revenues(tables)
    vert = _revenues_vertical(tables)
    if len(vert) > len(revs):
        revs, label = vert, '세로형'

    # **매출이 있는 것만 부문으로 인정한다.** 이름만 있는 표는 종속기업 목록일
    # 위험이 크고, 부문 판정에 쓸 값도 없다
    names = list(revs.keys())
    if not names:
        names = _names_only(tables)
        if names:
            label = '없음(부문명만)'
    out = []
    for nm in names:
        # 이름이 정확히 같지 않을 수 있어 부분 일치로도 잇는다
        prod = prods.get(nm, '')
        if not prod:
            for k, v in prods.items():
                if k in nm or nm in k:
                    prod = v
                    break
        # 「수익행」은 매출을 어느 행에서 읽었는지다. 금융권은 총액 행이 없어
        # 「이자손익」 같은 부분값이 담길 수 있으니 판단 근거로 함께 남긴다
        out.append({'명칭': nm, '주요제품': prod, '매출': revs.get(nm), '수익행': label})
    return out


if __name__ == '__main__':
    import os
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ.get('TMP', '.'), 'lg_note.xml')
    for s in parse(open(p, encoding='utf-8').read()):
        print(f"  {s['명칭']:<18} {str(s['매출'] or '-'):>14}  {s['주요제품'][:44]}")
