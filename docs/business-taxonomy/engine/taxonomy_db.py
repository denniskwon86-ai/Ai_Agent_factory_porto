# -*- coding: utf-8 -*-
"""[P4-T1] 분류 데이터 저장소 — CSV 를 대신하는 정본.

## 왜 옮기는가

⚠️ 문제는 **읽기가 아니라 제자리 쓰기**였다. `reclassify.py` 는
  `ftc-all-2026-classified.csv` 를 읽어 같은 파일에 덮고, `apply_segments.py` 는
  `instances-2026.csv` 를 덮는다. 「전체 대상 모수를 산정한 파일」에 손을 대면
  **어제 판정과 오늘 판정을 구별할 방법이 없다.**

사람이 열어 보는 편의는 내보내기로 얻을 수 있다. 덮어쓰기를 막는 일은 파일로는 못 한다.

## 세 층을 나눈다

| 층 | 어디에 | git |
|---|---|---|
| **정본** | `taxonomy.db` | ✗ (`*.db` 는 gitignore) |
| **보존** | `samples/snapshots/{id}/*.csv` | ✓ DB 가 없어도 복원된다 |
| 원천 캐시 | `.cache/*.json` | ✗ 재수집 가능 |

## 두 가지를 가른다 — 원천과 판정

`ftc-all-2026-classified.csv` 는 **공정위가 준 것과 우리가 판정한 것이 한 파일에**
있었다. 그래서 재판정이 원천을 덮어썼다. 여기서는 `src_ftc`(원천)와
`ftc_classified`(스냅샷별 결과)로 가른다 — 원천은 재수집하지 않는 한 그대로 남는다.

## 동결은 파이썬이 아니라 DB 가 막는다

★★★ 스냅샷을 얼리면 **트리거가** INSERT·UPDATE·DELETE 를 거부한다. 파이썬 가드는
  다른 경로로 접근하면 비켜 가지만, 트리거는 `sqlite3` 프롬프트에서도 막힌다.
  P1 에서 키트에 준 보호를 분류 데이터에도 같은 강도로 준다.

## 저장은 전부 TEXT 다

숫자로 바꾸면 `1234` 가 `1234.0` 이 되어 **CSV 왕복이 깨진다.** 질의는 `v_*` 뷰에서
`CAST` 해 쓴다 — 원문 보존이 질의 편의보다 앞선다.
"""
from __future__ import annotations

import datetime
import hashlib
import io
import json
import os
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)                      # docs/business-taxonomy
SAMPLES = os.path.join(BASE, 'samples')
SNAPSHOT_DIR = os.path.join(SAMPLES, 'snapshots')
DB_PATH = os.path.join(BASE, 'taxonomy.db')

_ORD = '_ord'


class FrozenSnapshotError(RuntimeError):
    """얼어 있는 스냅샷을 고치려 했다."""


class Table:
    """표 하나의 선언. **DDL·이관·내보내기가 전부 여기서 나온다** — 열을 두 곳에
    적으면 반드시 어긋난다."""

    def __init__(self, name: str, cols: Sequence[str], *, csv: str = '',
                 scoped: bool = False, key: Sequence[str] = (), note: str = ''):
        self.name = name
        self.cols = list(cols)
        self.csv = csv            #: samples/ 의 평면 CSV (이관 원본 · 내보내기 이름)
        self.scoped = scoped      #: 스냅샷별인가 (결과) · 아니면 누적인가 (원천)
        self.key = list(key)      #: 원천의 자연키 — UPSERT 로 이어 받는다
        self.note = note

    @property
    def all_cols(self) -> List[str]:
        head = ['snapshot_id'] if self.scoped else []
        return head + self.cols + [_ORD]

    def ddl(self) -> str:
        lines = []
        if self.scoped:
            lines.append('  snapshot_id TEXT NOT NULL '
                         'REFERENCES snapshots(snapshot_id) ON DELETE CASCADE')
        for c in self.cols:
            lines.append('  "%s" TEXT NOT NULL DEFAULT %s' % (c, "''"))
        lines.append('  %s INTEGER NOT NULL DEFAULT 0' % _ORD)
        if self.scoped:
            lines.append('  PRIMARY KEY (snapshot_id, %s)' % _ORD)
        elif self.key:
            lines.append('  PRIMARY KEY (%s)' % ', '.join('"%s"' % k for k in self.key))
        else:
            #: 자연키가 없는 원천. ⚠️ 없는 키를 억지로 주면 **중복 행이 조용히 사라진다** —
            #: `segments-2026.csv` 에 한솔아이원스의 완전 중복 2 행이 실제로 있었다.
            lines.append('  PRIMARY KEY (%s)' % _ORD)
        return 'CREATE TABLE IF NOT EXISTS %s (\n%s\n);' % (self.name, ',\n'.join(lines))


# ── 원천 — 수집한 것. 스냅샷을 타지 않고 누적된다.
#    ⚠️ 여기에 판정 결과를 섞지 않는다. 섞었던 것이 `ftc-all-2026-classified.csv` 다.

SOURCES: Dict[str, Table] = {t.name: t for t in [
    Table('src_corp',
          ['구분', '고유번호', '종목코드', '회사명', 'induty_code', '법인등록번호'],
          csv='dart-corp-2026.csv', key=['고유번호'],
          note='DART 공시법인 — API 2 만 회'),
    Table('src_financials',
          ['법인등록번호', '회사명', '고유번호', '매출액_백만원', '매출근거',
           '종업원수', '종업원근거', '사업보고서', '오류'],
          csv='dart-financials-2026.csv', key=['고유번호'],
          note='매출·직원수 — API 7,000 회'),
    Table('src_reports',
          ['고유번호', '접수번호', '보고서명', '회사명'],
          csv='dart-reports-2026.csv', key=['고유번호', '접수번호'],
          note='사업보고서 접수번호'),
    Table('src_segments',
          ['회사명', '종목코드', '법인등록번호', 'KSIC', '묶음노드', '보고서',
           '부문명', '주요제품', '부문설명', '매출', '수익행', '상태'],
          csv='segments-2026.csv',
          note='영업부문 — ZIP 수 GB. ⚠️ (법인·보고서·부문명) 이 유일하지 않다 '
               '— 한솔아이원스가 「본사부문」·「세정부문」을 각각 두 번 신고했다'),
    Table('src_ftc',
          ['기업집단명', '소속회사명', '법인등록번호', 'KSIC', '영위업종',
           '종업원수', '매출액', '기업공개일'],
          key=['기업집단명', '소속회사명', '법인등록번호'],
          note='★ 공정위 원천만. 판정 열은 ftc_classified 로 갈랐다'),
    Table('src_ownership',
          ['고유번호', '법인등록번호', '회사명', '최대주주연도', '출자연도', '오류'],
          key=['고유번호'], note='최대주주·출자 수집 대장'),
    Table('src_ownership_holder',
          ['고유번호', '순번', '주주', '관계', '지분율'],
          key=['고유번호', '순번'],
          note='최대주주. ⚠️ 개인은 이름을 저장하지 않고 「개인」으로 적는다'),
    Table('src_ownership_invest',
          ['고유번호', '순번', '출자대상', '지분율', '장부가액'],
          key=['고유번호', '순번'], note='타법인 출자현황'),
]}

# ── 결과 — 판정이 만든 것. 스냅샷별로 쌓이고, 얼리면 못 고친다.

RESULTS: Dict[str, Table] = {t.name: t for t in [
    Table('ftc_classified',
          ['기업집단명', '소속회사명', '법인등록번호', 'KSIC', '영위업종', '종업원수',
           '매출액', '기업공개일', 'A세분류', 'A대분류', 'B1주업종', 'B1_2단',
           '묶음노드', '모수계층', '판정근거', 'B1_3단'],
          csv='ftc-all-2026-classified.csv', scoped=True,
          note='공정위 명단 판정 — universe 로 흡수되는 중간 산출물'),
    Table('universe',
          ['법인등록번호', '회사명', '종목코드', 'KSIC', 'A대분류', 'A세분류',
           'B1주업종', 'B1_2단', 'B1_3단', '밸류체인', '가치사슬단계', '묶음노드',
           '모수계층', '매출액', '매출기준', '종업원수', '상장', '출처', '기업집단명들'],
          csv='universe-2026.csv', scoped=True, note='★ 모수 — 전체 대상 산정의 근거'),
    Table('instances',
          ['단위', '계층', '소속그룹', '모법인', '이름', 'A대분류', 'A세분류',
           'B1주업종', 'B1_2단', 'B1_3단', '밸류체인', '가치사슬단계', '매출',
           '매출기준', '종업원수', '지배법인', '판정근거'],
          csv='instances-2026.csv', scoped=True, note='법인·세그먼트·묶음 인스턴스'),
    Table('ownership_edges',
          ['지배법인', '지배법인등록번호', '대상', '대상법인등록번호', '지분율',
           '장부가액', '대상계층', '대상소속그룹', '대상A세분류', '대상B1주업종',
           '대상매출', '대상묶음', '연도'],
          csv='ownership-edges-2026.csv', scoped=True, note='지배 사슬'),
    Table('longlist',
          ['키트ID', '셀', '회사명', '법인등록번호', '단위', '소속그룹', 'A세분류',
           'B1주업종', 'B1_2단', 'B1_3단', '매출', '모수계층', '선정근거'],
          csv='longlist.csv', scoped=True,
          note='[P4-T5] 업무키트 대상 — 「그때 왜 이 명단이었나」'),
]}

TABLES: Dict[str, Table] = dict(SOURCES, **RESULTS)

_SNAPSHOT_DDL = """
CREATE TABLE IF NOT EXISTS snapshots (
  snapshot_id TEXT PRIMARY KEY,
  created_at  TEXT NOT NULL,
  label       TEXT NOT NULL DEFAULT '',
  engine_sha  TEXT NOT NULL DEFAULT '',
  rules_fp    TEXT NOT NULL DEFAULT '',
  source_fp   TEXT NOT NULL DEFAULT '{}',
  row_counts  TEXT NOT NULL DEFAULT '{}',
  note        TEXT NOT NULL DEFAULT '',
  frozen      INTEGER NOT NULL DEFAULT 0,
  frozen_at   TEXT NOT NULL DEFAULT '',
  frozen_by   TEXT NOT NULL DEFAULT '',
  frozen_why  TEXT NOT NULL DEFAULT '',
  inherited_from TEXT NOT NULL DEFAULT '',
  stages      TEXT NOT NULL DEFAULT '{}'
);
-- ★ 동결은 되돌릴 수 없다. 풀 수 있으면 「한 번 풀고 고친다」로 보호가 무의미해진다.
CREATE TRIGGER IF NOT EXISTS trg_snapshot_no_unfreeze
BEFORE UPDATE ON snapshots WHEN OLD.frozen = 1 AND NEW.frozen = 0
BEGIN SELECT RAISE(ABORT, '동결은 해제할 수 없습니다 — 새 스냅샷을 뜨십시오'); END;
"""

_FREEZE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trg_frz_{t}_ins BEFORE INSERT ON {t}
WHEN (SELECT frozen FROM snapshots WHERE snapshot_id = NEW.snapshot_id) = 1
BEGIN SELECT RAISE(ABORT, '동결된 스냅샷에는 쓸 수 없습니다 — 새 스냅샷을 뜨십시오'); END;
CREATE TRIGGER IF NOT EXISTS trg_frz_{t}_upd BEFORE UPDATE ON {t}
WHEN (SELECT frozen FROM snapshots WHERE snapshot_id = OLD.snapshot_id) = 1
BEGIN SELECT RAISE(ABORT, '동결된 스냅샷은 고칠 수 없습니다 — 새 스냅샷을 뜨십시오'); END;
CREATE TRIGGER IF NOT EXISTS trg_frz_{t}_del BEFORE DELETE ON {t}
WHEN (SELECT frozen FROM snapshots WHERE snapshot_id = OLD.snapshot_id) = 1
BEGIN SELECT RAISE(ABORT, '동결된 스냅샷은 지울 수 없습니다'); END;
"""

#: 질의 편의. 저장은 TEXT 이므로 여기서 CAST 한다.
_VIEWS = """
CREATE VIEW IF NOT EXISTS v_universe AS
SELECT snapshot_id, 법인등록번호, 회사명, KSIC, A대분류, A세분류, B1주업종,
       B1_2단, B1_3단, 모수계층, 상장, 묶음노드, 기업집단명들,
       CAST(NULLIF(매출액,'') AS REAL)  AS 매출액_억,
       CAST(NULLIF(종업원수,'') AS REAL) AS 종업원수_명
FROM universe;
CREATE VIEW IF NOT EXISTS v_instances AS
SELECT snapshot_id, 단위, 계층, 소속그룹, 모법인, 이름, A대분류, A세분류,
       B1주업종, B1_2단, B1_3단, 지배법인,
       CAST(NULLIF(매출,'') AS REAL) AS 매출_억
FROM instances;
"""


def _now() -> str:
    return datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')


def fingerprint(rows: Iterable[Dict[str, Any]], cols: Sequence[str]) -> str:
    """행 내용의 지문. **열 순서를 고정해** 딕셔너리 순서에 흔들리지 않게 한다."""
    h = hashlib.sha256()
    n = 0
    for r in rows:
        h.update(('\x1f'.join(str(r.get(c, '') or '') for c in cols) + '\x1e').encode('utf-8'))
        n += 1
    return '%s:%d' % (h.hexdigest()[:16], n)


class TaxonomyDB:
    """분류 데이터 정본."""

    def __init__(self, path: str = DB_PATH):
        self.path = path
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA journal_mode = WAL')
        self.conn.execute('PRAGMA foreign_keys = ON')
        self.conn.execute('PRAGMA busy_timeout = 5000')
        self._migrate()

    # ── 스키마

    def _migrate(self) -> None:
        c = self.conn
        c.executescript(_SNAPSHOT_DDL)
        #: ⚠️ 대장 자신도 같은 함정에 걸린다 — `CREATE TABLE IF NOT EXISTS` 는
        #:   이미 있는 표에 열을 넣어 주지 않는다.
        have = {r[1] for r in c.execute('PRAGMA table_info(snapshots)')}
        for col, default in [('inherited_from', "''"), ('stages', "'{}'"),
                             ('frozen_why', "''")]:
            if col not in have:
                c.execute('ALTER TABLE snapshots ADD COLUMN %s TEXT NOT NULL DEFAULT %s'
                          % (col, default))
        for t in TABLES.values():
            c.execute(t.ddl())
            #: ⚠️ `CREATE TABLE IF NOT EXISTS` 는 이미 있는 표에 열을 넣어 주지 않는다.
            have = {r[1] for r in c.execute('PRAGMA table_info(%s)' % t.name)}
            for col in t.all_cols:
                if col not in have:
                    c.execute('ALTER TABLE %s ADD COLUMN "%s" TEXT NOT NULL DEFAULT %s'
                              % (t.name, col, "''"))
        for t in RESULTS.values():
            c.executescript(_FREEZE_TRIGGER.format(t=t.name))
            c.execute('CREATE INDEX IF NOT EXISTS idx_%s_snap ON %s(snapshot_id)'
                      % (t.name, t.name))
        c.execute('CREATE INDEX IF NOT EXISTS idx_universe_brn '
                  'ON universe(snapshot_id, 법인등록번호)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_instances_par '
                  'ON instances(snapshot_id, 모법인)')
        c.executescript(_VIEWS)
        c.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    # ── 스냅샷

    def snapshot_new(self, snapshot_id: str = '', *, label: str = '', note: str = '',
                     engine_sha: str = '', rules_fp: str = '', inherit: bool = True) -> str:
        """새 스냅샷. 같은 날 두 번 뜨면 `-2`, `-3` 이 붙는다 — **덮지 않는다.**

        ★ `inherit` 이면 직전 스냅샷의 결과를 그대로 복사한다. **스냅샷은 언제나
          완결된 상태여야** 하기 때문이다 — `apply_segments` 만 다시 돌렸을 때
          universe 가 비어 있으면 그 스냅샷은 아무것도 설명하지 못한다.
        """
        base = snapshot_id or datetime.date.today().isoformat()
        sid, n = base, 1
        while self.conn.execute('SELECT 1 FROM snapshots WHERE snapshot_id=?',
                                (sid,)).fetchone():
            n += 1
            sid = '%s-%d' % (base, n)
        prev = self.latest() if inherit else None
        self.conn.execute(
            'INSERT INTO snapshots(snapshot_id, created_at, label, note, engine_sha,'
            ' rules_fp, source_fp, inherited_from) VALUES (?,?,?,?,?,?,?,?)',
            (sid, _now(), label, note, engine_sha or git_sha(),
             rules_fp or rules_fingerprint(),
             json.dumps(self.source_fingerprint(), ensure_ascii=False, sort_keys=True),
             prev or ''))
        if prev:
            for name, t in RESULTS.items():
                cols = ','.join('"%s"' % c for c in t.cols)
                self.conn.execute(
                    'INSERT INTO %s (snapshot_id, %s, %s) '
                    'SELECT ?, %s, %s FROM %s WHERE snapshot_id=?'
                    % (name, cols, _ORD, cols, _ORD, name), (sid, prev))
        self.conn.commit()
        return sid

    def mark_stage(self, sid: str, stage: str) -> None:
        """어느 단계가 이 스냅샷에서 다시 돌았는지. 상속받은 것과 새로 낸 것을 가른다."""
        s = self.snapshot(sid)
        if not s:
            return
        st = json.loads(s['stages'] or '{}')
        if not isinstance(st, dict):
            st = {}          # 이중 인코딩된 옛 값을 만나도 멈추지 않는다
        st[stage] = _now()
        self.conn.execute('UPDATE snapshots SET stages=? WHERE snapshot_id=?',
                          (json.dumps(st, ensure_ascii=False, sort_keys=True), sid))
        self.conn.commit()

    def snapshots(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.conn.execute(
            'SELECT * FROM snapshots ORDER BY created_at DESC, snapshot_id DESC')]

    def snapshot(self, sid: str) -> Optional[Dict[str, Any]]:
        r = self.conn.execute('SELECT * FROM snapshots WHERE snapshot_id=?', (sid,)).fetchone()
        return dict(r) if r else None

    def latest(self, frozen_only: bool = False) -> Optional[str]:
        q = ('SELECT snapshot_id FROM snapshots %s '
             'ORDER BY created_at DESC, snapshot_id DESC LIMIT 1')
        r = self.conn.execute(q % ('WHERE frozen=1' if frozen_only else '')).fetchone()
        return r[0] if r else None

    def is_frozen(self, sid: str) -> bool:
        r = self.conn.execute('SELECT frozen FROM snapshots WHERE snapshot_id=?',
                              (sid,)).fetchone()
        return bool(r and r[0])

    def guard(self, sid: str) -> None:
        """쓰기 전에 부른다. 트리거가 최종 방어지만, **여기서 막아야 메시지가 친절하다.**"""
        if self.is_frozen(sid):
            raise FrozenSnapshotError(
                '스냅샷 %s 는 동결돼 있습니다.\n'
                '  고치려면 새 스냅샷을 뜨십시오 — TaxonomyDB().snapshot_new()\n'
                '  확정된 모수를 제자리에서 고치면 「그때 왜 이 명단이었나」에 답할 수 없습니다.'
                % sid)

    def freeze(self, sid: str, *, why: str = '', by: str = '') -> Dict[str, Any]:
        if not self.snapshot(sid):
            raise KeyError('없는 스냅샷: %s' % sid)
        self.conn.execute(
            'UPDATE snapshots SET frozen=1, frozen_at=?, frozen_by=?, frozen_why=?,'
            ' row_counts=? WHERE snapshot_id=?',
            (_now(), by, why,
             json.dumps(self.row_counts(sid), ensure_ascii=False, sort_keys=True), sid))
        self.conn.commit()
        return self.snapshot(sid)

    def row_counts(self, sid: str) -> Dict[str, int]:
        return {n: self.conn.execute(
            'SELECT COUNT(*) FROM %s WHERE snapshot_id=?' % n, (sid,)).fetchone()[0]
            for n in sorted(RESULTS)}

    def source_fingerprint(self) -> Dict[str, str]:
        """원천의 지문. **판정 결과가 어떤 원천 위에서 나왔는지**를 스냅샷에 박는다 —
        원천까지 판본을 뜨면 20 만 행이 배로 늘어나므로, 지문으로 증명한다."""
        return {n: fingerprint(self.rows(n), t.cols) for n, t in sorted(SOURCES.items())}

    # ── 읽기·쓰기

    def rows(self, table: str, sid: Optional[str] = None) -> List[Dict[str, Any]]:
        t = TABLES[table]
        cols = ', '.join('"%s"' % c for c in t.cols)
        if t.scoped:
            if sid is None:
                sid = self.latest()
            cur = self.conn.execute(
                'SELECT %s FROM %s WHERE snapshot_id=? ORDER BY %s' % (cols, table, _ORD),
                (sid,))
        else:
            cur = self.conn.execute('SELECT %s FROM %s ORDER BY %s' % (cols, table, _ORD))
        return [dict(r) for r in cur]

    def count(self, table: str, sid: Optional[str] = None) -> int:
        t = TABLES[table]
        if t.scoped:
            sid = sid if sid is not None else self.latest()
            return self.conn.execute('SELECT COUNT(*) FROM %s WHERE snapshot_id=?'
                                     % table, (sid,)).fetchone()[0]
        return self.conn.execute('SELECT COUNT(*) FROM %s' % table).fetchone()[0]

    def put_source(self, table: str, rows: Sequence[Dict[str, Any]],
                   *, replace: bool = True) -> int:
        """원천 적재. `replace=True` 면 통째로 갈고, 아니면 자연키로 이어 받는다
        (수집이 한도에 걸려 나눠 받는 경우)."""
        t = SOURCES[table]
        cur = self.conn
        if replace:
            cur.execute('DELETE FROM %s' % table)
        cols = t.cols + [_ORD]
        sql = 'INSERT OR REPLACE INTO %s (%s) VALUES (%s)' % (
            table, ','.join('"%s"' % c for c in cols), ','.join('?' * len(cols)))
        base = 0 if replace else cur.execute(
            'SELECT COALESCE(MAX(%s),-1)+1 FROM %s' % (_ORD, table)).fetchone()[0]
        cur.executemany(sql, [tuple(_s(r.get(c)) for c in t.cols) + (base + i,)
                              for i, r in enumerate(rows)])
        cur.commit()
        #: ★ `INSERT OR REPLACE` 는 키가 겹치면 **말없이 덮는다.** 들어간 행이 준 행보다
        #:   적으면 자연키가 사실은 유일하지 않다는 뜻이고, 그것을 모르고 지나가면
        #:   원천이 조용히 줄어든다.
        got = self.count(table)
        if replace and got != len(rows):
            raise ValueError(
                '%s: %d 행을 넣었는데 %d 행만 남았습니다 — 자연키 (%s) 가 유일하지 '
                '않습니다.\n  Table 선언에서 key 를 빼거나 키를 다시 잡으십시오.'
                % (table, len(rows), got, ', '.join(t.key) or _ORD))
        return len(rows)

    def put_result(self, sid: str, table: str, rows: Sequence[Dict[str, Any]]) -> int:
        """스냅샷 결과 적재. **얼어 있으면 거부된다.**"""
        self.guard(sid)
        if not self.snapshot(sid):
            raise KeyError('없는 스냅샷: %s — 먼저 snapshot_new() 하십시오' % sid)
        t = RESULTS[table]
        cur = self.conn
        cur.execute('DELETE FROM %s WHERE snapshot_id=?' % table, (sid,))
        cols = ['snapshot_id'] + t.cols + [_ORD]
        sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
            table, ','.join('"%s"' % c for c in cols), ','.join('?' * len(cols)))
        cur.executemany(sql, [(sid,) + tuple(_s(r.get(c)) for c in t.cols) + (i,)
                              for i, r in enumerate(rows)])
        cur.commit()
        return len(rows)

    def drop_snapshot(self, sid: str) -> None:
        """얼지 않은 스냅샷만 지운다 — 작업 중 잘못 뜬 것을 치우는 용도."""
        self.guard(sid)
        for n in RESULTS:
            self.conn.execute('DELETE FROM %s WHERE snapshot_id=?' % n, (sid,))
        self.conn.execute('DELETE FROM snapshots WHERE snapshot_id=?', (sid,))
        self.conn.commit()


def _s(v: Any) -> str:
    """저장은 전부 TEXT. `None` 은 빈 문자열이다 — CSV 왕복에서 `None` 은 없다."""
    return '' if v is None else (v if isinstance(v, str) else str(v))


# ── 판정 규칙 지문 — 「어떤 규칙으로 판정했나」

_RULE_FILES = ['ksic_rules.py', 'segment_rules.py', 'valuechain_rules.py',
               'apply_segments.py', 'apply_ownership.py', 'build_universe.py']


def rules_fingerprint() -> str:
    """판정 규칙 파일들의 지문. 같은 원천에 같은 규칙이면 같은 결과가 나와야 한다."""
    h = hashlib.sha256()
    for f in _RULE_FILES:
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            h.update(f.encode('utf-8'))
            h.update(io.open(p, 'rb').read())
    return h.hexdigest()[:16]


def git_sha() -> str:
    import subprocess
    try:
        return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'],
                                       cwd=HERE, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ''


# ── CSV 왕복 — 보존 층

def read_csv(path: str) -> List[Dict[str, str]]:
    import csv
    with io.open(path, encoding='utf-8-sig', newline='') as f:
        return [dict(r) for r in csv.DictReader(f)]


def write_csv(path: str, cols: Sequence[str], rows: Iterable[Dict[str, Any]]) -> int:
    import csv
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    n = 0
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(cols), extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow({c: _s(r.get(c)) for c in cols})
            n += 1
    return n
