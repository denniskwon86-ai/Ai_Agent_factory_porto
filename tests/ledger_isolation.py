"""결정 원장 격리 경로의 **안전성 판정** — conftest 와 회귀가 같은 함수를 쓴다.

⚠️ 이 함수를 conftest 안에만 두면 시험이 그것을 부를 수 없고, 그러면 「경로가 운영
  `data/` 아래로 해석되면 멈춘다」는 규칙이 **한 번도 검사되지 않은 채** 살아 있게
  된다. 실제로 변이 검사에서 그 자리를 지워도 아무 시험도 깨지지 않았다 — 규칙이
  있는 것과 규칙이 지켜지는 것을 확인할 수 있는 것은 다르다.
"""
import os


def live_ledger_path() -> str:
    """운영 결정 원장의 절대 경로. **움직이지 않는 기준**이다.

    ⚠️⚠️ [2026-08-23 실측] 종전에는 `core.paths.data_path()` 를 썼다. 그런데 conftest 가
      격리를 위해 `paths.DATA_DIR` 을 tmp 로 돌리자 **이 감시자가 그대로 따라갔다** —
      즉 「운영 원장」이 tmp 를 가리키게 되고, 감시자는

          · tmp 경로를 「운영 원장이다」라며 **거부**하고
          · 진짜 `data/decision_ledger.db` 를 「격리 경로다」라며 **통과**시켰다.

      감시자가 완전히 뒤집혔는데 이름은 그대로였다. 시험 4건이 그것을 잡았다.

    ★★★ **통제는 자기가 막을 것에 기대면 안 된다.** 운영 뿌리는 «사실» 이지
      «변수» 가 아니다 — `PROJECT_ROOT/data` 로 고정한다(캐너리 시험에서 같은 결함을
      같은 방식으로 고쳤다)."""
    from core.paths import PROJECT_ROOT
    return os.path.realpath(os.path.join(PROJECT_ROOT, "data", "decision_ledger.db"))


def isolation_path_error(candidate: str) -> str:
    """격리 경로로 쓸 수 없으면 **사유 문자열**, 쓸 수 있으면 빈 문자열.

    ★ 「운영 파일 자체」만 막지 않는다. **운영 `data/` 디렉터리 아래 어디든** 막는다 —
      경로 계산이 틀어졌을 때 흔한 결과가 `data/tmp0/decision_ledger.db` 처럼
      운영 뿌리 안쪽에 만드는 것이고, 그것도 운영 폴더를 더럽힌다."""
    #: ⚠️ **원값을 먼저 본다.** `os.path.realpath("")` 는 빈 문자열이 아니라 **현재
    #:   작업 디렉터리**를 돌려준다 — 정규화한 뒤에 비었는지 물으면 영원히 참이
    #:   아니고, 빈 경로가 조용히 cwd 로 바뀌어 통과한다.
    raw = str(candidate or "").strip()
    if not raw:
        return "격리 경로가 비어 있습니다."
    live = live_ledger_path()
    resolved = os.path.realpath(raw)
    if resolved == live:
        return f"격리 경로가 운영 원장 자체입니다: {resolved}"
    live_dir = os.path.dirname(live)
    if resolved.startswith(live_dir + os.sep) or resolved == live_dir:
        return f"격리 경로가 운영 data/ 아래로 해석됐습니다: {resolved}"
    return ""


def read_sentinel(path: str):
    """어떤 원장 파일이든 **논리적 상태**를 읽는다. 없으면 `None`.

    ⚠️⚠️ `immutable=1` 만 쓰면 안 된다. 그 모드는 WAL 을 아예 보지 않으므로, 활성
      WAL 에 최신 행이 있으면 **못 본 채로 「안 변했다」** 고 말한다 — 확인 도구가
      거짓 안심을 준다.
    ★ 그래서 `-wal` 이 있으면 평범한 읽기 전용(`mode=ro`)으로 연다. 그때는 `-shm` 이
      생길 수 있지만, `-wal` 이 이미 있다는 것은 다른 프로세스가 쓰는 중이라는 뜻이라
      `-shm` 도 대개 이미 있다. `-wal` 이 없을 때만 `immutable=1` 로 **아무 파일도 안
      만들고** 읽는다.
    """
    import sqlite3

    live = str(path)
    if not os.path.exists(live):
        return None
    quoted = live.replace("?", "%3f").replace("#", "%23")
    mode = "?mode=ro" if os.path.exists(live + "-wal") else "?mode=ro&immutable=1"
    conn = sqlite3.connect("file:" + quoted + mode, uri=True)
    try:
        rows, max_seq = conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(seq), 0) FROM decision_ledger_events").fetchone()
        tail = conn.execute("SELECT event_hash FROM decision_ledger_events "
                            "ORDER BY seq DESC LIMIT 1").fetchone()
        return {"rows": rows, "max_seq": max_seq, "tail_hash": tail[0] if tail else ""}
    except Exception as e:      # 스키마가 없는 새 원장도 «상태» 다 — 숨기지 않는다
        return {"error": str(e)[:120]}
    finally:
        conn.close()


def live_sentinel():
    """운영 원장의 논리적 상태."""
    return read_sentinel(live_ledger_path())


def live_side_files():
    """운영 원장 본체와 `-wal`·`-shm` 의 존재 여부."""
    live = live_ledger_path()
    return {suffix: os.path.exists(live + suffix) for suffix in ("", "-wal", "-shm")}
