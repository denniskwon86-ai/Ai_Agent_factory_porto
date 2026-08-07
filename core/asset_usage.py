"""[D-017 §9 P4-4 나머지 절반] 자산 사용 관측 — 「미사용」을 말할 수 있게 만드는 원천.

## 왜 이것이 먼저 필요했는가

P4-4 는 「미사용·중복 정리 제안」인데, 착수 시점에 **「미사용」을 판단할 근거가 없었다**
(2026-08-07 실측): `agent_assets` 에 사용 이력 필드가 없고, 텔레메트리의 에이전트 축
관측률이 7.9%(89/1133)였다. 그래서 `asset_dedup` 은 중복만 내고 미사용은
「제공하지 않습니다」로 남겨 뒀다(P4-4 = 0.5).

설계(`docs/design_p4_recommendations_2026-08-07.md` §4.1)는 선행 조건 둘을 들었다 —
① 자산 해석 시점에 사용 이력을 남긴다 ② 에이전트 귀속률을 올린다.

★ **①이 서면 ②는 이 목적에 필요 없다.** ②는 LLM 호출 로그를 통한 **간접 추정**이고,
  ①은 자산이 실제로 해석된 순간의 **직접 관측**이다. 간접 추정이 좋아지기를 기다리느라
  직접 관측을 미룰 이유가 없다. 이 모듈이 ①이다.

## ⚠️⚠️ 관측은 **지금부터** 쌓인다 — 그래서 초기에는 전부 「사용 없음」으로 보인다

이것이 이 기능의 가장 위험한 함정이며, P4-2 의 부서 귀속률 0% 와 **정확히 같은 유형**이다.
관측을 켠 다음 날 화면이 「자산 31개 전부 미사용」이라고 말하면, 그것을 본 사람은 전부
지운다. 그리고 지운 뒤에야 그것이 「안 쓰인 것」이 아니라 「아직 안 본 것」이었음을 안다.

★ 그래서 이 모듈은 값과 함께 **`observed_since`·`days_observed` 를 항상 들고 다닌다.**
  관측 기간이 `MIN_OBSERVATION_DAYS` 에 못 미치면 소비자(`asset_dedup`)는 **목록을 만들지
  않고** 사유를 문장으로 낸다. 짧은 창에서 만든 목록은 「정리 대상」이 아니라 「아직 모름」이다.

⚠️ 「사용 기록 없음」은 「미사용」이 아니다. 이 모듈은 **자기가 본 것만** 말한다 —
  관측 이전의 사용, 그리고 기록 지점을 지나지 않는 경로의 사용은 여기에 없다.

## 기록 실패는 실행을 막지 않는다

사용 관측은 계측이다. 계측 장애로 스프린트가 멈추면 안 된다 — 모든 쓰기는 예외를 삼키고,
대신 **읽기 쪽이 «못 읽었다» 를 드러낸다**(`available=False` + 사유).
"""
from __future__ import annotations

import atexit
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from core.paths import data_path

#: ⚠️ 별도 DB 다. `agent_assets` 와 같은 `master.db` 에 두면 실행 중 사용 기록 쓰기가
#:   기준정보 조회와 락을 다투게 된다 — 계측이 업무 경로를 느리게 만들면 안 된다.
#:   `.gitignore` 의 `*.db` 가 잡으므로 저장소에는 올라가지 않는다(런타임 데이터).
_DB_PATH = data_path("asset_usage.db")

#: 이 기간을 못 채우면 「사용 기록 없음」 목록을 **만들지 않는다.**
#: ⚠️ 숫자의 근거: 스프린트 한 주기(월~금)에 두 배의 여유를 둔다. 주 1회만 도는 워크플로우가
#:   한 번도 안 걸릴 확률을 낮추기 위해서다. 짧게 잡으면 「아직 안 본 것」이 「안 쓰는 것」으로
#:   보고되고, 그 오보 한 번이면 사람은 이 목록을 다시 보지 않는다.
MIN_OBSERVATION_DAYS = 14

#: 「최근 사용」으로 볼 기간. 이보다 오래 전이면 «사용 기록 없음» 후보다.
STALE_AFTER_DAYS = 30

#: 메모리 누적을 디스크로 내리는 간격(초).
#: ⚠️ `agent_skill()` 은 노드마다 불린다 — 호출마다 DB 를 쓰면 그래프 실행이 느려진다.
#:   누적은 메모리에서 하고 주기적으로 한 번에 내린다(정확한 횟수는 보존된다).
FLUSH_INTERVAL_SEC = 30

_DDL = """
CREATE TABLE IF NOT EXISTS asset_usage (
    asset_key    TEXT PRIMARY KEY,
    kind         TEXT NOT NULL DEFAULT '',
    use_count    INTEGER NOT NULL DEFAULT 0,
    first_used_at TEXT NOT NULL DEFAULT '',
    last_used_at TEXT NOT NULL DEFAULT ''
);
-- 관측이 «언제부터» 인지를 남긴다. 이 한 줄이 없으면 「사용 기록 없음」이
-- 「안 쓰인다」인지 「아직 안 봤다」인지 구분할 수 없다.
CREATE TABLE IF NOT EXISTS asset_usage_meta (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL DEFAULT ''
);
"""

_OBSERVED_SINCE = "observed_since"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AssetUsageStore:
    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        #: asset_key -> {"kind": str, "count": int, "last": iso}
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._last_flush = 0.0
        self._ready = ""

    # ── 인프라 ────────────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """스키마와 **관측 시작 시각**을 만든다. 시작 시각은 한 번 쓰면 갱신하지 않는다 —
        갱신하면 창이 계속 짧아져서 목록이 영영 나오지 않는다."""
        if self._ready == self.db_path:
            return
        with self._connect() as conn:
            conn.executescript(_DDL)
            conn.execute("INSERT OR IGNORE INTO asset_usage_meta (k, v) VALUES (?, ?)",
                         (_OBSERVED_SINCE, _now()))
        self._ready = self.db_path

    # ── 기록 ──────────────────────────────────────────────────────────────
    def record(self, asset_key: str, kind: str = "") -> None:
        """자산이 **해석된** 순간을 남긴다.

        ⚠️ 예외를 삼킨다 — 계측 장애가 실행을 막으면 안 된다. 대신 읽기 쪽이
          «관측이 없다» 를 드러내므로 조용히 사라지지는 않는다."""
        asset_key = str(asset_key or "").strip()
        if not asset_key:
            return
        try:
            with self._lock:
                p = self._pending.setdefault(
                    asset_key, {"kind": kind, "count": 0, "last": ""})
                if kind:
                    p["kind"] = kind
                p["count"] += 1
                p["last"] = _now()
                due = (time.time() - self._last_flush) >= FLUSH_INTERVAL_SEC
            if due:
                self.flush()
        except Exception as e:                                   # pragma: no cover
            print(f"⚠️ [asset_usage] 사용 기록 실패(실행은 계속): {asset_key}: {e}")

    def flush(self) -> int:
        """메모리 누적을 디스크로 내린다. 내린 건수를 돌려준다."""
        try:
            with self._lock:
                batch, self._pending = self._pending, {}
                self._last_flush = time.time()
            if not batch:
                return 0
            self._init_db()
            with self._connect() as conn:
                for key, p in batch.items():
                    conn.execute(
                        "INSERT INTO asset_usage "
                        "  (asset_key, kind, use_count, first_used_at, last_used_at) "
                        "VALUES (?, ?, ?, ?, ?) "
                        "ON CONFLICT(asset_key) DO UPDATE SET "
                        # ⚠️ 덮어쓰지 않고 **더한다** — 플러시마다 덮으면 누적이 사라진다.
                        "  use_count = use_count + excluded.use_count, "
                        "  last_used_at = excluded.last_used_at, "
                        "  kind = CASE WHEN excluded.kind <> '' "
                        "              THEN excluded.kind ELSE asset_usage.kind END",
                        (key, p["kind"], p["count"], p["last"], p["last"]))
            return len(batch)
        except Exception as e:                                   # pragma: no cover
            print(f"⚠️ [asset_usage] 사용 기록 플러시 실패(실행은 계속): {e}")
            return 0

    # ── 읽기 ──────────────────────────────────────────────────────────────
    def observed_since(self) -> str:
        try:
            self._init_db()
            with self._connect() as conn:
                r = conn.execute("SELECT v FROM asset_usage_meta WHERE k=?",
                                 (_OBSERVED_SINCE,)).fetchone()
            return str(r["v"]) if r else ""
        except Exception:
            return ""

    def days_observed(self) -> float:
        since = self.observed_since()
        if not since:
            return 0.0
        try:
            t = datetime.fromisoformat(since)
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - t).total_seconds() / 86400.0)
        except Exception:
            return 0.0

    def usage_map(self) -> Dict[str, Dict[str, Any]]:
        """asset_key -> {kind, use_count, first_used_at, last_used_at}.

        ⚠️ 아직 디스크로 안 내려간 누적을 **먼저 내린다.** 그러지 않으면 방금 쓴 자산이
          「사용 기록 없음」으로 보고된다 — 그 오보 한 번이 목록의 신뢰를 깎는다."""
        self.flush()
        try:
            self._init_db()
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT asset_key, kind, use_count, first_used_at, last_used_at "
                    "FROM asset_usage").fetchall()
            return {r["asset_key"]: {"kind": r["kind"], "use_count": r["use_count"],
                                     "first_used_at": r["first_used_at"],
                                     "last_used_at": r["last_used_at"]} for r in rows}
        except Exception as e:
            print(f"⚠️ [asset_usage] 사용 기록 조회 실패: {e}")
            return {}

    def stale_before(self, days: int = STALE_AFTER_DAYS) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


asset_usage = AssetUsageStore()

# 프로세스가 끝날 때 남은 누적을 내린다 — 마지막 30초가 통째로 사라지지 않게 한다.
atexit.register(asset_usage.flush)


def record(asset_key: str, kind: str = "") -> None:
    """모듈 수준 단축 호출 — 기록 지점에서 한 줄로 쓰기 위해서다."""
    asset_usage.record(asset_key, kind)


def skill_key(skill_name: str) -> str:
    """파일 스킬의 **관측 키**. 레지스트리의 스킬 이름을 디스크 파일명으로 맞춘다.

    ⚠️⚠️ [2026-08-07 실측] 이 함수가 없어서 관측이 **통째로 헛돌았다.**
      `agent_registry.agent_skill()` 은 `rfp_skill` 을 돌려주는데 `asset_dedup.collect_items()`
      는 파일명 `rfp_skill.md` 를 id 로 쓴다. 두 키가 달라 교집합이 **0건**이었고, 그 결과
      실제로 매 실행마다 쓰이는 스킬 31개가 전부 «사용 기록 없음» 으로 보고될 참이었다 —
      즉 관측을 켜 놓고도 「전부 정리 대상」이라는 화면이 나온다.

    ⚠️ 단위 테스트는 이것을 **잡지 못했다.** `agent_meta` 를 `"writer.md"` 로 대역해 뒀더니
      테스트가 자기 자신과 합의했다. 그래서 이 규약은 대역 없이 실제 레지스트리·실제
      `skills/` 로 고정한다(`tests/test_asset_usage.py`).

    ★ 디스크 규약의 출처는 `agent_asset_adapter._SKILLS_DIR` 아래 `f"{native}.md"` 다
      (같은 파일 282·320행). 여기서 새로 정하지 않고 그 규약을 따른다."""
    name = str(skill_name or "").strip()
    if not name:
        return ""
    return name if name.endswith(".md") else f"{name}.md"
