"""[P4] 분류 데이터 DB — 확정된 모수가 제자리에서 덮이지 않는지.

이 시험이 지키는 것: **「그 파일을 그대로 손을 대면 어떻게 하나」.**
`reclassify.py` 가 `ftc-all-2026-classified.csv` 를 읽어 같은 파일에 덮었고,
`apply_segments.py` 가 `instances-2026.csv` 를 덮었다. 어제 판정과 오늘 판정을
가릴 방법이 없었다.
"""
import json
import os
import sqlite3
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(REPO, "docs", "business-taxonomy", "engine")
sys.path.insert(0, ENGINE)

import taxonomy_db as T  # noqa: E402


@pytest.fixture
def db(tmp_path):
    return T.TaxonomyDB(str(tmp_path / "t.db"))


def _seed(db, sid=None):
    sid = sid or db.snapshot_new(label="시험")
    db.put_result(sid, "universe", [{"회사명": "가", "매출액": "100"},
                                    {"회사명": "나", "매출액": "200"}])
    return sid


# ── 원천과 판정을 가른다

def test_원천은_스냅샷을_타지_않는다(db):
    """수집물은 판정마다 복제되지 않는다 — 20 만 행이 판본 수만큼 늘어난다."""
    assert T.SOURCES["src_ftc"].scoped is False
    assert T.RESULTS["universe"].scoped is True


def test_공정위_원천에는_판정열이_없다():
    """★ 한 파일에 섞여 있어서 재판정이 원천을 덮었다."""
    src = set(T.SOURCES["src_ftc"].cols)
    for c in ("A세분류", "B1주업종", "B1_2단", "판정근거", "모수계층"):
        assert c not in src, f"{c} 는 판정 결과다 — ftc_classified 로 가야 한다"
    assert c in T.RESULTS["ftc_classified"].cols


# ── 동결

def test_얼지_않은_스냅샷은_쓸_수_있다(db):
    sid = _seed(db)
    assert db.put_result(sid, "universe", [{"회사명": "다"}]) == 1


def test_얼면_파이썬이_막는다(db):
    sid = _seed(db)
    db.freeze(sid, why="시험")
    with pytest.raises(T.FrozenSnapshotError) as e:
        db.put_result(sid, "universe", [{"회사명": "다"}])
    # 사람이 무엇을 해야 하는지 메시지에 있어야 한다
    assert "새 스냅샷" in str(e.value)


@pytest.mark.parametrize("sql,args", [
    ("UPDATE universe SET 회사명='몰래' WHERE snapshot_id=?", None),
    ("DELETE FROM universe WHERE snapshot_id=?", None),
    ("INSERT INTO universe (snapshot_id, 회사명, _ord) VALUES (?, '몰래', 99)", None),
])
def test_얼면_DB_트리거가_막는다(db, tmp_path, sql, args):
    """★★★ 파이썬 가드는 다른 경로로 접근하면 비켜 간다. **`sqlite3` 프롬프트에서도
    막혀야** 「확정된 것이 확정된 채로 남는다」가 성립한다."""
    sid = _seed(db)
    db.freeze(sid, why="시험")
    raw = sqlite3.connect(db.path)
    with pytest.raises(sqlite3.IntegrityError):
        raw.execute(sql, (sid,))
        raw.commit()


def test_동결은_해제할_수_없다(db):
    """풀 수 있으면 「한 번 풀고 고친다」로 보호가 통째로 무의미해진다."""
    sid = _seed(db)
    db.freeze(sid, why="시험")
    raw = sqlite3.connect(db.path)
    with pytest.raises(sqlite3.IntegrityError):
        raw.execute("UPDATE snapshots SET frozen=0 WHERE snapshot_id=?", (sid,))
        raw.commit()
    assert db.is_frozen(sid)


def test_얼린_판본은_지울_수도_없다(db):
    sid = _seed(db)
    db.freeze(sid, why="시험")
    with pytest.raises(T.FrozenSnapshotError):
        db.drop_snapshot(sid)


# ── 스냅샷

def test_같은_날_두_번_떠도_덮지_않는다(db):
    a = db.snapshot_new("2026-01-01")
    b = db.snapshot_new("2026-01-01")
    assert (a, b) == ("2026-01-01", "2026-01-01-2")


def test_새_스냅샷은_직전_결과를_상속한다(db):
    """★ 스냅샷은 **언제나 완결된 상태**여야 한다 — 한 단계만 다시 돌렸을 때
    나머지가 비어 있으면 그 판본은 아무것도 설명하지 못한다."""
    a = _seed(db)
    db.freeze(a, why="기준")
    b = db.snapshot_new(label="이어서")
    assert db.rows("universe", b) == db.rows("universe", a)
    assert db.snapshot(b)["inherited_from"] == a


def test_상속받은_판본을_고쳐도_기준은_그대로다(db):
    a = _seed(db)
    db.freeze(a, why="기준")
    b = db.snapshot_new()
    db.put_result(b, "universe", [{"회사명": "바뀜"}])
    assert len(db.rows("universe", a)) == 2
    assert [r["회사명"] for r in db.rows("universe", b)] == ["바뀜"]


def test_상속하지_않을_수도_있다(db):
    a = _seed(db)
    b = db.snapshot_new(inherit=False)
    assert db.rows("universe", b) == []
    assert db.snapshot(b)["inherited_from"] == ""


def test_단계를_기록한다(db):
    sid = _seed(db)
    db.mark_stage(sid, "build_universe")
    assert "build_universe" in json.loads(db.snapshot(sid)["stages"])


# ── 적재

def test_중복이_조용히_사라지면_잡는다(db):
    """★ `INSERT OR REPLACE` 는 키가 겹치면 말없이 덮는다. `segments-2026.csv` 에
    한솔아이원스의 완전 중복 2 행이 실제로 있었고, 자연키를 잘못 주자 사라졌다."""
    rows = [{"고유번호": "1", "회사명": "가"}, {"고유번호": "1", "회사명": "나"}]
    with pytest.raises(ValueError) as e:
        db.put_source("src_corp", rows)
    assert "유일하지 않" in str(e.value)


def test_자연키가_없는_원천은_중복을_받는다(db):
    """부문 표는 (법인·보고서·부문명) 이 유일하지 않다 — 억지로 키를 주면 행이 준다."""
    same = {"회사명": "한솔아이원스", "법인등록번호": "1", "보고서": "R", "부문명": "본사부문"}
    assert db.put_source("src_segments", [dict(same), dict(same)]) == 2
    assert db.count("src_segments") == 2


def test_행_순서를_보존한다(db):
    sid = db.snapshot_new()
    db.put_result(sid, "universe", [{"회사명": c} for c in "다가나"])
    assert [r["회사명"] for r in db.rows("universe", sid)] == ["다", "가", "나"]


def test_None_은_빈_문자열로_저장된다(db):
    """CSV 왕복에 `None` 은 없다 — 되돌릴 때 숫자 열만 `None` 으로 돌린다."""
    sid = db.snapshot_new()
    db.put_result(sid, "universe", [{"회사명": None, "매출액": 100}])
    r = db.rows("universe", sid)[0]
    assert r["회사명"] == "" and r["매출액"] == "100"


# ── 지문

def test_스냅샷에_원천_지문이_박힌다(db):
    """판정이 **어떤 수집물 위에서** 나왔는지. 원천이 바뀌면 값이 달라진다."""
    db.put_source("src_ftc", [{"기업집단명": "A", "소속회사명": "가", "법인등록번호": "1"}])
    a = db.snapshot_new()
    db.put_source("src_ftc", [{"기업집단명": "A", "소속회사명": "가", "법인등록번호": "1"},
                              {"기업집단명": "B", "소속회사명": "나", "법인등록번호": "2"}])
    b = db.snapshot_new()
    assert json.loads(db.snapshot(a)["source_fp"]) != json.loads(db.snapshot(b)["source_fp"])


def test_지문은_열_순서에_흔들리지_않는다():
    cols = ["a", "b"]
    assert (T.fingerprint([{"a": 1, "b": 2}], cols)
            == T.fingerprint([{"b": 2, "a": 1}], cols))


# ── CSV 왕복 (보존 층)

def test_CSV_로_내보내고_다시_읽으면_같다(db, tmp_path):
    """★ git 에 남는 것은 CSV 다. 여기서 깨지면 DB 없는 기계에서 복원이 안 된다."""
    sid = db.snapshot_new()
    rows = [{"회사명": "가, 콤마", "매출액": "1000", "출처": "따옴표\"있음"},
            {"회사명": "나\n줄바꿈", "매출액": ""}]
    db.put_result(sid, "universe", rows)
    p = str(tmp_path / "u.csv")
    cols = T.RESULTS["universe"].cols
    T.write_csv(p, cols, db.rows("universe", sid))
    got = T.read_csv(p)
    assert [{c: r[c] for c in cols} for r in got] == \
           [{c: r[c] for c in cols} for r in db.rows("universe", sid)]


# ── 실제 데이터 (있을 때만)

_REAL = os.path.exists(T.DB_PATH)


@pytest.mark.skipif(not _REAL, reason="로컬에 taxonomy.db 가 없다")
def test_기준_판본이_얼어있다():
    d = T.TaxonomyDB()
    frozen = [s for s in d.snapshots() if s["frozen"]]
    assert frozen, "동결된 기준 판본이 하나는 있어야 한다"


@pytest.mark.skipif(not _REAL, reason="로컬에 taxonomy.db 가 없다")
def test_모수와_인스턴스가_들어있다():
    d = T.TaxonomyDB()
    sid = d.latest()
    assert d.count("universe", sid) > 20000
    assert d.count("instances", sid) > 20000
