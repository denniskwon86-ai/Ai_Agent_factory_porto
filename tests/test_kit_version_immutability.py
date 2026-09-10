"""[P3] 등록부의 불변 판본 보호 — 동결된 판본의 지문이 바뀌면 거부한다.

## 왜 파일 층(P1)만으로 부족한가

`kit_freeze` 는 **같은 저장소 안의 실수**를 막는다. 그러나 대장(`fingerprint.json`)까지
함께 바뀐 경우나 다른 머신에서 온 파일은 파일만 봐서는 알 수 없다 — DB 에 박힌 지문만이
잡는다. 종전에는 `upsert_kit_version` 이 지문이 달라져도 그대로 덮었다.
"""
import os
import tempfile

import pytest

from core.data_preparation import models as m
from core.data_preparation.store import DataPreparationStore

COMMON = dict(kit_id="K", version="1.0.0", name="n", mode="DEMO/SYNTHETIC",
              source_path="p", profile={})


@pytest.fixture()
def store(tmp_path):
    return DataPreparationStore(str(tmp_path / "t.db"))


def test_미동결_판본은_덮어쓴다(store):
    """아직 확정 전인 판본까지 막으면 개발 중에 아무것도 못 한다."""
    store.upsert_kit_version(fingerprint_value="aaa", frozen=False, **COMMON)
    row = store.upsert_kit_version(fingerprint_value="bbb", frozen=False, **COMMON)
    assert row["fingerprint"] == "bbb"


def test_동결_판본도_지문이_같으면_멱등이다(store):
    """등록은 서버가 뜰 때마다 돈다 — 같은 내용이면 통과해야 한다."""
    store.upsert_kit_version(fingerprint_value="bbb", frozen=True, **COMMON)
    store.upsert_kit_version(fingerprint_value="bbb", frozen=True, **COMMON)


def test_동결_판본의_지문이_달라지면_거부한다(store):
    store.upsert_kit_version(fingerprint_value="bbb", frozen=True, **COMMON)
    with pytest.raises(m.StateConflict) as e:
        store.upsert_kit_version(fingerprint_value="ccc", frozen=True, **COMMON)
    assert "동결된 판본이 바뀌었습니다" in str(e.value)
    assert "새 판본" in str(e.value)


def test_frozen_False_로는_동결이_풀리지_않는다(store):
    """★ 풀린다면 「frozen=False 로 한 번 등록」이 보호를 통째로 무력화한다."""
    store.upsert_kit_version(fingerprint_value="bbb", frozen=True, **COMMON)
    with pytest.raises(m.StateConflict):
        store.upsert_kit_version(fingerprint_value="ddd", frozen=False, **COMMON)


def test_다른_판본은_서로_막지_않는다(store):
    store.upsert_kit_version(fingerprint_value="bbb", frozen=True, **COMMON)
    other = {**COMMON, "version": "1.1.0"}
    store.upsert_kit_version(fingerprint_value="zzz", frozen=True, **other)


def test_frozen_열이_없는_기존_DB도_열린다(tmp_path):
    """이 열이 생기기 전에 만들어진 DB 가 있다 — 마이그레이션이 멱등이어야 한다."""
    import sqlite3
    p = str(tmp_path / "old.db")
    conn = sqlite3.connect(p)
    conn.executescript("""
        CREATE TABLE kit_registry_versions (
            kit_version_id TEXT PRIMARY KEY, kit_id TEXT NOT NULL, version TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '', mode TEXT NOT NULL DEFAULT 'DEMO/SYNTHETIC',
            source_path TEXT NOT NULL DEFAULT '', fingerprint TEXT NOT NULL,
            profile_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE (kit_id, version));
    """)
    conn.execute("INSERT INTO kit_registry_versions VALUES "
                 "('kv1','K','1.0.0','n','DEMO/SYNTHETIC','p','old','{}','active','t','t')")
    conn.commit()
    conn.close()

    st = DataPreparationStore(p)
    # 옛 행은 미동결로 남는다 — 없던 사실을 만들어 내지 않는다
    row = st.upsert_kit_version(fingerprint_value="new", frozen=False, **COMMON)
    assert row["fingerprint"] == "new"
