# -*- coding: utf-8 -*-
"""
DART 사업보고서 → 영업부문(세그먼트) 수집기
==========================================
⚠️ 검토 중인 미확정 설계다. 현재 시스템에 연결·연계하지 않는다.

**DART Open API 에 세그먼트 전용 API 가 없다.** 재무정보 API 7종은 회사 단위 계정만 준다.
그래서 사업보고서 원문(document.xml)을 받아 「영업부문」 표를 파싱한다.

인증키는 환경변수 `DART_API_KEY` 로 넣는다. **코드나 저장소에 두지 않는다.**
발급: https://opendart.fss.or.kr/  (무료, 즉시)

    export DART_API_KEY=xxxx
    python fetch_dart.py 005930        # 종목코드
    python fetch_dart.py 00126380      # 고유번호

주의
----
- DART 서버는 DH 키가 작아 Python 기본 SSL 이 거부한다. `SECLEVEL=1` 로 낮춘다
- 사업보고서 원문은 회사당 수 MB 다. 캐시를 쓴다
- **서식이 회사마다 다르다.** 표를 못 찾으면 빈 리스트를 돌려주고, 그 회사는 법인 1건으로 남는다
- `to_ksic()` 로 업종코드도 얻는다. 공정위에 없는 비집단 상장사의 유일한 KSIC 경로다
"""
from __future__ import annotations
import io
import os
import re
import ssl
import json
import zipfile
import urllib.parse
import urllib.request

API = 'https://opendart.fss.or.kr/api'
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')

_ctx = ssl.create_default_context()
_ctx.set_ciphers('DEFAULT@SECLEVEL=1')   # DART 서버의 DH 키가 작다


def _key() -> str:
    k = os.environ.get('DART_API_KEY')
    if not k:
        # 환경변수가 없으면 engine/.env 를 읽는다.
        # `.env` 는 저장소 최상단 .gitignore 에 걸려 있어 커밋되지 않는다
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        if os.path.exists(p):
            for line in open(p, encoding='utf-8'):
                if line.strip().startswith('DART_API_KEY'):
                    k = line.split('=', 1)[1].strip().strip('"').strip("'")
                    break
    if not k:
        raise RuntimeError(
            'DART_API_KEY 가 없다. 환경변수로 넣거나 engine/.env 에 '
            'DART_API_KEY=... 한 줄을 두어라. opendart.fss.or.kr 에서 무료 발급.')
    return k


def _get(path: str, **params) -> bytes:
    params['crtfc_key'] = _key()
    url = f'{API}/{path}?{urllib.parse.urlencode(params)}'
    with urllib.request.urlopen(url, timeout=180, context=_ctx) as r:
        return r.read()


def _get_json(path: str, **params) -> dict:
    return json.loads(_get(path, **params).decode('utf-8'))


# ────────────────────────────────────────────── 업종코드

# KSIC 대분류 문자는 **앞 2자리 숫자로 완전히 결정된다.** 체계가 그렇게 짜여 있다.
# DART 는 대분류 문자만 빼고 숫자는 그대로 주므로 되돌릴 수 있다
_대분류 = [(1, 3, 'A'), (5, 8, 'B'), (10, 34, 'C'), (35, 35, 'D'), (36, 39, 'E'),
           (41, 42, 'F'), (45, 47, 'G'), (49, 52, 'H'), (55, 56, 'I'), (58, 63, 'J'),
           (64, 66, 'K'), (68, 68, 'L'), (70, 73, 'M'), (74, 76, 'N'), (84, 84, 'O'),
           (85, 85, 'P'), (86, 87, 'Q'), (90, 91, 'R'), (94, 96, 'S'), (97, 98, 'T'),
           (99, 99, 'U')]


def to_ksic(induty_code: str) -> str | None:
    """
    DART `induty_code` → KSIC. 대분류 문자를 앞 2자리로 복원한다.

        264   → C264      (삼성전자)
        20111 → C20111    (LG화학)
        471   → G471      (이마트)
        58211 → J58211    (펄어비스)

    **자릿수는 회사가 신고한 수준을 따른다**(3~5자리). 공정위 KSIC 와 대조하면
    중분류(앞 2자리)는 20/22 가 맞았고, 세분류는 신고 수준이 달라 갈린다.
    그래서 **B 축 2단은 이 값만으로 단정하지 않는 게 안전하다.**

    공정위와 어긋난 2건 중 SK이노베이션은 DART 가 더 정확했다 —
    DART `C192`(석유정제)가 공정위 `K6499`(지주회사)보다 사업 실질에 가깝다.
    """
    c = (induty_code or '').strip()
    if not c.isdigit() or len(c) < 2:
        return None
    n = int(c[:2])
    for lo, hi, ch in _대분류:
        if lo <= n <= hi:
            return ch + c
    return None


# ────────────────────────────────────────────── 법인등록번호 조인

def _jurir(v: str) -> str:
    """법인등록번호를 숫자만 남긴다. 양쪽 다 13자리지만 표기가 흔들릴 수 있다"""
    return re.sub(r'\D', '', v or '')


def jurir_index(ftc_rows: list[dict]) -> dict:
    """공정위 소속회사 목록 → `{법인등록번호: 행}`"""
    idx = {}
    for r in ftc_rows:
        k = _jurir(r.get('법인등록번호'))
        if len(k) == 13:
            idx.setdefault(k, r)
    return idx


_지주코드 = re.compile(r'^(K6499|M7151|K64992)')


def resolve_ksic(corp: dict, ftc_idx: dict | None = None) -> dict:
    """
    회사 하나의 KSIC 를 정한다. **법인등록번호로 두 출처를 잇는다.**

    corp    : `fetch()` 또는 `company.json` 의 반환 (jurir_no · induty_code 필요)
    ftc_idx : `jurir_index()` 가 만든 색인

    이름 조인은 표기 때문에 새는 데가 많다(「에스케이씨(주)」와 「SKC」).
    법인등록번호는 13자리 숫자라 그런 문제가 없다.

    **공정위를 기본으로 쓴다** — 자릿수가 고르고 재무·종업원수까지 온다.
    다만 공정위가 **지주회사 코드**(K6499·M7151)인데 DART 가 사업 코드를 주면
    DART 를 쓴다. SK이노베이션이 그렇다 — 공정위 `K6499` 대 DART `C192`(석유정제)로,
    지주회사 체제라 개별 신고가 사업 실질을 가린다.
    """
    dart = to_ksic(corp.get('induty_code'))
    k = _jurir(corp.get('jurir_no'))
    row = (ftc_idx or {}).get(k) if len(k) == 13 else None
    ftc = ((row or {}).get('KSIC') or '').strip().upper() or None

    if ftc and dart and _지주코드.match(ftc) and not _지주코드.match(dart):
        return {'ksic': dart, '출처': 'DART(공정위는 지주코드)',
                'ftc_ksic': ftc, 'dart_ksic': dart, 'ftc_row': row}
    if ftc:
        return {'ksic': ftc, '출처': '공정위',
                'ftc_ksic': ftc, 'dart_ksic': dart, 'ftc_row': row}
    return {'ksic': dart, '출처': 'DART(공정위에 없음)' if dart else None,
            'ftc_ksic': None, 'dart_ksic': dart, 'ftc_row': None}


# ────────────────────────────────────────────── 고유번호

def corp_code_map(refresh: bool = False) -> dict[str, str]:
    """종목코드 → 고유번호. 전체 목록을 한 번 받아 캐시한다."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, 'corpcode.json')
    if os.path.exists(path) and not refresh:
        return json.load(open(path, encoding='utf-8'))

    raw = _get('corpCode.xml')
    z = zipfile.ZipFile(io.BytesIO(raw))
    xml = z.read(z.namelist()[0]).decode('utf-8', 'replace')
    out = {}
    for m in re.finditer(r'<list>(.*?)</list>', xml, re.S):
        blk = m.group(1)
        code = (re.search(r'<corp_code>(.*?)</corp_code>', blk) or [None, ''])[1]
        stock = (re.search(r'<stock_code>(.*?)</stock_code>', blk) or [None, ''])[1]
        if stock and stock.strip():
            out[stock.strip()] = code.strip()
    json.dump(out, open(path, 'w', encoding='utf-8'))
    return out


def resolve(code: str) -> str:
    """종목코드(6자리)면 고유번호로 바꾼다"""
    code = code.strip()
    if len(code) == 8 and code.isdigit():
        return code
    m = corp_code_map()
    if code in m:
        return m[code]
    raise KeyError(f'고유번호를 찾지 못했다: {code}')


# ────────────────────────────────────────────── 지배 집단 판정

def corp_name_map(refresh: bool = False) -> dict[str, str]:
    """
    **회사명 → 고유번호.** 비상장 공시법인도 이름으로 찾을 수 있다.
    `corp_code_map()` 은 상장사만(종목코드가 있는 것만) 담으므로 이것이 따로 필요하다.
    """
    import segment_rules
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, 'corpname.json')
    if os.path.exists(path) and not refresh:
        return json.load(open(path, encoding='utf-8'))

    raw = _get('corpCode.xml')
    z = zipfile.ZipFile(io.BytesIO(raw))
    xml = z.read(z.namelist()[0]).decode('utf-8', 'replace')
    out = {}
    for m in re.finditer(r'<list>(.*?)</list>', xml, re.S):
        blk = m.group(1)
        code = re.search(r'<corp_code>(.*?)</corp_code>', blk)
        name = re.search(r'<corp_name>(.*?)</corp_name>', blk)
        if not (code and name):
            continue
        for c in segment_rules._cands(name.group(1)):
            out.setdefault(c, code.group(1).strip())
    json.dump(out, open(path, 'w', encoding='utf-8'))
    return out


_종속헤더 = re.compile(r'(종속기업|연결대상|연결\s*종속|지배지분율)')
_지분법헤더 = re.compile(r'(관계기업|공동기업|공동약정|지분법적용)')


def subsidiaries(rcept_no: str) -> set:
    """
    주석의 **종속기업 목록**에서 회사 이름을 뽑는다(정규화된 형태).

    지배 집단 판정의 근거다 — K-IFRS 1110 호에 따라 종속기업으로 **연결하는** 쪽이
    지배자다. 그래서 **관계기업·공동기업 표는 뺀다** — 그건 지분법이고 지배가 아니다.
    """
    import parse_segment
    import segment_rules
    xml = note_xml(rcept_no)
    if not xml:
        try:
            xml = document_xml(rcept_no)
        except Exception:
            return set()
    out = set()
    for rows, _ in parse_segment._tables(xml):
        head = ' '.join(' '.join(r) for r in rows[:2])
        if _지분법헤더.search(head) or not _종속헤더.search(head):
            continue
        for r in rows[1:]:
            nm = parse_segment._clean(r[0] if r else '')
            if 2 <= len(nm) <= 40:
                out.update(segment_rules._cands(nm))
    return out


def group_heads(group: str, ftc_rows: list[dict], limit: int = 5) -> list[dict]:
    """
    집단의 **지배 후보들.** 종속기업 목록을 확인할 대상이다.

    **지주회사만 보면 놓친다.** 묶음노드로 잡히는 K6499 에는 PEF·벤처투자사도
    섞인다 — 태광의 「티투프라이빗에쿼티」, 카카오의 「카카오벤처스」가 그렇다.
    그래서 ① 집단명이 이름에 든 회사 ② 지주회사 ③ 매출 상위를 함께 후보로 둔다.
    애경처럼 집단명(애경)과 지주사명(에이케이홀딩스)이 다른 경우가 있어 셋이 다 필요하다.
    """
    import segment_rules
    g = segment_rules._norm_corp(group)

    def sales(r):
        try:
            return float((r.get('매출액') or '0').replace(',', ''))
        except Exception:
            return 0.0

    pool = [r for r in ftc_rows if r.get('기업집단명') == group]
    ranked = sorted(pool, key=sales, reverse=True)
    rank = {id(r): i for i, r in enumerate(ranked)}

    def score(r):
        s = 0.0
        if g and g in segment_rules._norm_corp(r.get('소속회사명', '')):
            s += 2
        if r.get('묶음노드') == 'Y':
            s += 1
        s += max(0.0, 1.0 - rank[id(r)] / max(1, len(ranked)))
        return s

    # **지주회사는 무조건 첫 후보로 넣는다.** 점수로만 뽑으면 애경에서 실패한다 —
    # 집단명이 든 회사(애경케미칼·애경산업…)가 자리를 다 차지하고, 정작 지배자인
    # 「에이케이홀딩스」는 이름에 「애경」이 없고 매출도 작아 밀린다
    holds = [r for r in pool if r.get('묶음노드') == 'Y']
    hid = {id(r) for r in holds}
    rest = [r for r in sorted(pool, key=score, reverse=True) if id(r) not in hid]
    return (holds + rest)[:limit]


def controlling_group(name: str, groups: list[str], ftc_rows: list[dict],
                      limit: int = 5) -> tuple:
    """
    여러 집단에 걸친 법인의 **지배 집단**을 가린다.

    기준은 K-IFRS 1110 호 지배력이다 — 그 법인을 **종속기업으로 연결하는** 집단이
    지배자다. 후보 집단마다 지배 후보 회사들의 주석을 훑어 이름이 종속기업 목록에
    있는지 본다.

    반환: `(집단명 또는 None, 근거 문자열)`
    어느 쪽도 연결하지 않으면 `(None, ...)` — **공동기업이므로 가르지 않는다.**
    """
    import segment_rules
    want = segment_rules._cands(name)
    nmap = corp_name_map()
    hits, checked = [], []
    for g in groups:
        n = 0
        for head in group_heads(g, ftc_rows, limit):
            hn = head.get('소속회사명', '')
            cc = next((nmap[c] for c in segment_rules._cands(hn) if c in nmap), None)
            if not cc:
                continue
            rpt = latest_annual(cc)
            if not rpt:
                continue
            try:
                subs = subsidiaries(rpt['rcept_no'])
            except Exception:
                continue
            if not subs:
                continue
            n += 1
            if want & subs:
                hits.append((g, hn))
                break
        checked.append(f'{g}:{n}곳')
    tail = ' (확인 ' + ' · '.join(checked) + ')'
    if len(hits) == 1:
        return hits[0][0], f'{hits[0][1]} 의 종속기업'
    if len(hits) > 1:
        # 양쪽이 연결한다고 나오면 가르지 않는다 — 자료가 어긋난 것이다
        return None, '양쪽이 종속기업으로 신고: ' + ', '.join(f'{g}({h})' for g, h in hits)
    # **확인한 곳이 0 이면 「공동기업」이 아니라 「확인 못 함」이다.** 둘을 섞으면
    # 자료가 없어서 못 가른 것을 공동기업이라 잘못 읽는다
    if all(c.endswith(':0곳') for c in checked):
        return None, '확인 못 함 — 종속기업 목록을 읽을 수 있는 회사가 없다' + tail
    if any(c.endswith(':0곳') for c in checked):
        # 한쪽만 확인됐다. 「그쪽이 연결하지 않는다」만 알고 반대쪽은 모른다 —
        # **공동기업이라고 단정하면 안 된다**
        return None, '한쪽을 확인하지 못했다 — 가르지 않는다' + tail
    return None, '어느 쪽도 연결하지 않는다 — 공동기업' + tail


# ────────────────────────────────────────────── 사업보고서

def latest_annual(corp_code: str, bgn: str = '20240101') -> dict | None:
    """가장 최근 사업보고서 1건"""
    d = _get_json('list.json', corp_code=corp_code, bgn_de=bgn,
                  end_de='20991231', pblntf_ty='A', page_count=50)
    if d.get('status') != '000':
        return None
    for it in (d.get('list') or []):
        if it.get('report_nm', '').startswith('사업보고서'):
            return it
    return None


def _zip(rcept_no: str) -> zipfile.ZipFile:
    """공시 원문 ZIP. 회사당 수 MB 이므로 캐시한다."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f'{rcept_no}.zip')
    if not os.path.exists(path):
        with open(path, 'wb') as f:
            f.write(_get('document.xml', rcept_no=rcept_no))
    return zipfile.ZipFile(path)


def note_xml(rcept_no: str) -> str | None:
    """
    **재무제표 주석 파일**을 ZIP 에서 골라낸다.

    부문 표는 본문이 아니라 여기 있다. 본문에도 「부문별 정보」 섹션이 있지만
    그건 XBRL 뷰어용 표라 부문명이 열 헤더가 아니라 축 레이블(「기업 전체 총계」)로
    들어가 있어 못 쓴다. 그래서 **본문은 아예 뺀다** — 본문만 접미사가 없다
    (`20260313001195.xml` 이 본문, `_00760`·`_00761` 이 주석).

    남은 주석 후보는 **실제로 파싱해서** 고른다. 키워드 빈도로 점수를 매기면
    본문이 이긴다(XBRL 태그에 「외부고객」이 잔뜩 있다). 부문이 나오는지가 기준이다.
    연결·별도 주석이 함께 오면 **연결을 쓴다** — 그게 정본이다.
    """
    import parse_segment
    from parse_segment import _섹션
    z = _zip(rcept_no)
    body = f'{rcept_no}.xml'.lower()
    best, best_score = None, 0
    for i in z.infolist():
        fn = i.filename.lower()
        if not fn.endswith('.xml') or fn.endswith(body):
            continue
        t = z.read(i.filename).decode('utf-8', 'replace')
        segs = parse_segment.parse(t)
        # 부문 섹션이 있으면 **파싱이 0건이어도** 주석으로 인정한다.
        # 단일 보고부문 회사(기아·SK하이닉스)는 0건이 정답이므로,
        # 탈락시키면 주석을 찾지 못한 것과 구분할 수 없다
        base = len(_섹션.findall(t)) if _섹션.search(t) else 0
        if not segs and not base:
            continue
        score = (base
                 + len(segs) * 3
                 + sum(1 for x in segs if x['주요제품'])
                 + (5 if '연결재무제표' in t[:20000] else 0))
        if score > best_score:
            best, best_score = t, score
    return best


def document_xml(rcept_no: str) -> str:
    """공시 원문. 회사당 수 MB 이므로 캐시한다."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f'{rcept_no}.xml')
    if os.path.exists(path):
        return open(path, encoding='utf-8').read()
    z = _zip(rcept_no)
    # ZIP 안에 XML 이 여럿이고 **순서가 회사마다 다르다** (삼성전자는 첫째, LG화학은 둘째).
    # 나머지는 XBRL 주석이라 재무 표가 많아 오탐을 만든다 — **가장 큰 파일이 본문**이다
    biggest = max(z.infolist(), key=lambda i: i.file_size)
    xml = z.read(biggest.filename).decode('utf-8', 'replace')
    open(path, 'w', encoding='utf-8').write(xml)
    return xml


# ────────────────────────────────────────────── 세그먼트 파싱

_제외행 = re.compile(
    r'^(총계|합계|계|소계|기타|연결조정|내부거래|조정|차감|공통|미배분'
    r'|영업이익|영업손실|총자산|자산총액|부채총액|자본총액|당기순이익|감가상각|매출액|매출총이익'
    r'|손익|자산|부채|자본)$')


_재무용어 = re.compile(
    r'(수익|이익|손실|상각|지분|자산|부채|자본|현금|원가|비용|세액|법인세|충당|평가|'
    r'배분|기술|요소|기준|정책|측정|공시|증가|감소|취득|처분|기초|기말|누계|환산)')


_판매경로 = re.compile(r'^(내수|수출|국내|해외|직수출|로컬|기타지역)$')


def is_region_row(name: str) -> bool:
    return bool(_판매경로.match((name or '').replace(' ', '')))


def _text(t: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', t)).strip()


def _num(s: str):
    s = (s or '').replace(',', '').replace('△', '-').replace('(', '-').replace(')', '').strip()
    try:
        return int(float(s))
    except Exception:
        return None


def parse_segments(xml: str) -> list[dict]:
    """
    「부문 / 주요 제품 / 매출액」 형태의 표를 찾아 세그먼트를 뽑는다.

    **주요 제품 열이 중요하다.** 부문명이 약어(DX·DS)여도 제품 서술로 판정할 수 있다.
    """
    best: list[dict] = []
    for tbl in re.findall(r'<TABLE[^>]*>.*?</TABLE>', xml, re.S):
        if '부문' not in tbl:
            continue
        rows = []
        for tr in re.findall(r'<TR[^>]*>(.*?)</TR>', tbl, re.S):
            cells = [_text(c) for c in re.findall(r'<T[DEHU][^>]*>(.*?)</T[DEHU]>', tr, re.S)]
            cells = [c for c in cells if c]
            if cells:
                rows.append(cells)
        if len(rows) < 3:
            continue
        # 헤더 행을 찾는다. 「부 문」처럼 공백이 낀 표기가 흔하므로 공백을 지우고 본다
        hi = None
        for i, r in enumerate(rows[:4]):
            h = ' '.join(r).replace(' ', '')
            if '부문' in h and re.search(r'매출|수익', h):
                hi = i
                break
        if hi is None:
            continue
        head_cells = [c.replace(' ', '') for c in rows[hi]]
        if re.search(r'유형자산|감가상각|취득원가|장부금액', ' '.join(head_cells)):
            continue

        i_prod = next((i for i, h in enumerate(head_cells) if '제품' in h or '서비스' in h), None)
        i_sale = next((i for i, h in enumerate(head_cells) if '매출' in h or '수익' in h), None)
        # 「주요 제품」 열이 없으면 세그먼트 표가 아닐 가능성이 크다.
        # 억지로 채우지 않는다 — 오탐보다 미검출이 안전하다
        if i_prod is None:
            continue

        segs = []
        for r in rows[hi + 1:]:
            name = r[0].strip()
            if not name or _제외행.match(name.replace(' ', '')):
                continue
            # 재무 용어 행을 걸러낸다 — XBRL 주석 표가 본문에 섞여 든다
            if _재무용어.search(name) or len(name) > 25:
                continue
            if is_region_row(name):      # 「내 수」 「수 출」 같은 판매경로 행
                continue
            prod = r[i_prod] if (i_prod is not None and i_prod < len(r)) else ''
            if prod.strip() == name:      # 주요제품 열이 부문명과 같으면 무효
                prod = ''
            sale = _num(r[i_sale]) if (i_sale is not None and i_sale < len(r)) else None
            if sale is None:
                sale = next((v for v in (_num(c) for c in r[1:]) if v is not None), None)
            segs.append({'명칭': name, '주요제품': prod, '매출': sale})
        if segs and len(segs) > len(best):
            best = segs
    return best


def fetch(code: str) -> dict:
    """종목코드 또는 고유번호 → 회사 개황 + 세그먼트"""
    cc = resolve(code)
    comp = _get_json('company.json', corp_code=cc)
    rpt = latest_annual(cc)
    segs, via = [], None
    if rpt:
        # **주석 우선.** 본문 표는 서식이 제각각이라 커버리지가 26% 였다
        import parse_segment
        note = note_xml(rpt['rcept_no'])
        if note:
            segs = parse_segment.parse(note)
            via = '주석'
        if not segs:                     # 주석에서 못 찾으면 본문으로 물러선다
            segs = parse_segments(document_xml(rpt['rcept_no']))
            via = '본문' if segs else None
    return {
        'corp_code': cc,
        'corp_name': comp.get('corp_name'),
        'stock_code': comp.get('stock_code'),
        'corp_cls': comp.get('corp_cls'),
        # DART 의 induty_code 는 대분류 문자가 없고 자릿수도 제각각이지만
        # (삼성전자 264 · LG화학 20111 · 이마트 471) **되돌릴 수 있다** —
        # to_ksic() 참조. 공정위에 없는 비집단 상장사는 이게 유일한 경로다
        'induty_code': comp.get('induty_code'),
        'ksic': to_ksic(comp.get('induty_code')),
        'jurir_no': comp.get('jurir_no'),         # 공정위 데이터와 조인하는 키
        'report': rpt.get('report_nm') if rpt else None,
        'rcept_no': rpt.get('rcept_no') if rpt else None,
        'source': via,
        'segments': segs,
    }


if __name__ == '__main__':
    import sys
    for code in (sys.argv[1:] or ['005930']):
        d = fetch(code)
        print(f"\n■ {d['corp_name']} ({d['stock_code']}) · KSIC {d['induty_code']} · {d['report']}")
        if not d['segments']:
            print('   세그먼트 표를 찾지 못했다 — 법인 1건으로 둔다')
            continue
        for seg in d['segments']:
            print(f"   · {seg['명칭']:<14} {str(seg['매출'] or '-'):>14}  {seg['주요제품'][:44]}")
