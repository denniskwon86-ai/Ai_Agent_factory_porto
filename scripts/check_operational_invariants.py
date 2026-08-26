"""★★★ 운영 데이터 영역이 **회귀 전후로 그대로인가**를 기준선 비교로 확인한다.

## 왜 «존재 검사» 가 아니라 «전후 비교» 인가 (2026-08-20 Supervisor 지적)

첫 판은 특정 파일을 **무조건 금지**했다. 그런데 `data/ontology.db` 와
`data/data_preparation.db` 는 **이미 존재하고 보존하기로 한 것**이다. 그래서 메인 작업
공간에서 돌리면 원인이 새 오염이 아니어도 **항상 실패**했다 — 늘 빨강인 검사는 아무도
보지 않게 되고, 그러면 진짜 오염이 났을 때도 못 본다.

★ 그래서 「무엇이 있으면 안 된다」가 아니라 **「돌리기 전과 달라졌는가」**를 본다.

## SQLite 를 `immutable=1` 로 연다

⚠️⚠️ `mode=ro` 는 **읽기만 해도 WAL 모드 DB 의 SHM 을 만들 수 있다**(원장 사고 때 확인).
  불변식을 확인하는 행위가 스스로 파일을 만들면 그 검사는 자기 자신을 오염시킨다.
  `immutable=1` 은 WAL 을 보지 않으므로 아무것도 만들지 않는다.

## ⚠️⚠️ 그런데 «WAL 을 보지 않는다» 가 곧 맹점이다 (2026-08-20 Supervisor 지적)

종전 머리말은 「WAL 내용이 안 보이는 편이 목적에 맞다」고 적어 놓고, 정작 browser
모드에서는 **WAL 파일 변경을 허용**했다. 임시 DB 로 실측한 결과는 이렇다:

    WAL 에만 있는 행 1건
      file:t.db?immutable=1  →  OperationalError: no such table: r
      file:t.db?mode=ro      →  1행

★ `immutable=1` 은 행은커녕 **표조차 못 본다.** 그러면 `_rows`·`_content` 가
  `"unreadable"` 을 돌려주고, 전후 **둘 다** `"unreadable"` 이면 값이 같으므로
  **통과한다.** 없는 표 `kits` 를 세던 때와 **완전히 같은 사고**다.

⚠️ 체크포인트를 여기서 하면 안 된다 — 이 검사는 아무것도 쓰지 않는다는 것이 전제다.
★ 그래서 **비어 있지 않은 WAL 을 보면 검사를 중단한다.** 서버를 내리고 다시 부르라고
  말하는 것이, 못 보는 것을 봤다고 하는 것보다 낫다.

## 기준선에 «못 읽음» 이 있으면 그것도 실패다

전후가 둘 다 `"unreadable"` 이면 «같다». 그 «같다» 는 아무것도 지키지 않는다.
기준선에 `"unreadable"` 이 하나라도 있으면 그 기준선은 못 믿는다 — 비교를 거부한다.

## 모드

    --mode tests     시험만 돌린 상태. `data_preparation.db` 도 새로 생기면 안 된다.
    --mode browser   화면 검증까지 한 상태. 키트 레지스트리 생성이 **예상된다**.

사용:
    python scripts/check_operational_invariants.py capture   # 회귀 전
    …전체 회귀…
    python scripts/check_operational_invariants.py compare   # 회귀 후

LLM 0콜. 읽기 전용 — **아무것도 지우지 않는다**(지우면 증거가 사라진다).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / ".invariant_baseline.json"

#: 지켜보는 파일. WAL·SHM 도 본다 — 본체만 보면 「읽기만 했는데 파일이 늘었다」를 놓친다.
WATCH = [
    "data/ontology.db", "data/ontology.db-wal", "data/ontology.db-shm",
    "data/data_preparation.db", "data/data_preparation.db-wal",
    "data/data_preparation.db-shm",
    "data/decision_ledger.db", "data/decision_ledger.db-wal",
    "data/decision_ledger.db-shm",
    #: ★★★ [2026-08-20] 조직 데이터가 여기 있는데 감시 밖이었다. 「남의 조직 데이터가
    #:   우리 것으로 보인다」는 바로 이 표에서 일어나는 일이고, ECM Resolver 가 읽는
    #:   것도 이 파일이다 — 지켜야 할 것을 안 보고 있었다.
    "data/enterprise_context.db", "data/enterprise_context.db-wal",
    "data/enterprise_context.db-shm",
    #: ★★★ [2026-08-23 실측] **결정 안건·발간물이 감시 밖이었다.**
    #:   운영 `collaboration.db` 에 안건 253행·발간 76행이 쌓여 있었고 그중 237행이
    #:   시험 계정이 만든 것이었다. 그런데 이 검사기는 초록을 냈다 — 안 보고 있었으니까.
    #: ⚠️ 격리 목록과 감시 목록이 **같은 자리를 비워 두면** 그 자리는 아무도 안 본다.
    "data/collaboration.db", "data/collaboration.db-wal", "data/collaboration.db-shm",
    #: ⚠️ LLM 캐시는 import 시점에 파일을 만든다 — 그 사실이 보이게 감시한다.
    "data/llm_cache.db",
    "data/app_data.db", "data/app_data_preview.db",
    "data/program_lifecycle.db",
]

#: WAL 이 있는지 물어볼 본체들(‑wal·‑shm 을 뺀 것).
DBS = tuple(rel for rel in WATCH if not rel.endswith(("-wal", "-shm")))

#: 행 수를 함께 보는 표. ⚠️ 파일 크기는 VACUUM 등으로 변할 수 있어 행 수가 더 정확하다.
TABLES = [
    ("data/decision_ledger.db", "decision_ledger_events"),
    ("data/ontology.db", "semantic_relations"),
    ("data/ontology.db", "semantic_model_contracts"),
    #: ★★★ [2026-08-20 Supervisor 지적] **실제 표 이름을 쓴다.** 종전에는 존재하지
    #:   않는 `kits` 를 셌고, 전후 모두 `unreadable` 이라 비교가 **조용히 초록**이었다 —
    #:   없는 표를 세는 검사는 아무것도 지키지 않으면서 지키는 것처럼 보인다.
    ("data/data_preparation.db", "kit_instances"),
    ("data/data_preparation.db", "dataset_snapshots"),
    ("data/data_preparation.db", "source_bindings"),
    ("data/data_preparation.db", "readiness_evaluations"),
    ("data/data_preparation.db", "baseline_builds"),
    #: ★ 키트 레지스트리는 화면 검증이 만든다 — 그 사실을 «보고» 넘어가려면 세야 한다.
    ("data/data_preparation.db", "kit_registry_versions"),
    ("data/enterprise_context.db", "organization_nodes"),
    ("data/enterprise_context.db", "organization_edges"),
    ("data/enterprise_context.db", "enterprise_entities"),
    #: ★ 결정 안건과 발간물은 **업무 산출물**이다 — 회귀가 만들 이유가 없다.
    ("data/collaboration.db", "decision_cases"),
    ("data/collaboration.db", "publications"),
    ("data/collaboration.db", "publication_versions"),
]

#: 화면 검증 뒤에 **파일이 생기는 것**까지만 봐준다(§5.2 에 이미 적혀 있던 사실:
#: 「업무 데이터 준비」 패널을 열면 `GET /kits` 가 키트를 등록하며 파일을 만든다).
BROWSER_ALLOWED_FILES = {"data/data_preparation.db", "data/data_preparation.db-wal",
                         "data/data_preparation.db-shm"}

#: ★★★ [2026-08-20 실측] **읽기만 해도 생기는 파일.** 어느 모드에서나 «생김» 은 봐준다.
#:
#: `tests/conftest.py` 의 `ecm_org_seed` 는 운영 조직도를 `mode=ro` 로 연다 — 격리가
#: 반쪽이라(`org_directory` 는 운영 DB 를 읽는다) **노드 id 가 실제와 같아야** 하기
#: 때문이고, 그 사실은 그 자리에 이미 적혀 있다.
#:
#: ⚠️ `mode=ro` 는 읽기만 해도 WAL 모드 DB 의 `-shm`·`-wal` 을 만든다. 이것을 위반으로
#:   세면 검사가 **매번 빨강**이 되고, 늘 빨강인 검사는 아무도 보지 않는다.
#: ★★ 면제는 **파일 존재까지만**이다. 조직 표의 행 수와 내용 지문은 그대로 지킨다 —
#:   실제로 지켜야 할 것은 「조직 데이터가 바뀌었는가」이지 「파일이 생겼는가」가 아니다.
#: ⚠️⚠️ 그러니 이 면제를 «조직 DB 는 안 본다» 로 읽으면 안 된다. 내용이 바뀌면 여전히
#:   빨강이고, 그 시험이 `test_조직_트리_변조를_잡는다` 이다.
READ_ARTIFACT_FILES = {"data/enterprise_context.db-wal",
                       "data/enterprise_context.db-shm"}

#: ★★★ [2026-08-20 Supervisor 지적 P0-4] **파일 허용이 곧 내용 허용이 아니다.**
#:
#: ⚠️⚠️ 종전 browser 모드는 `data_preparation.db` 의 **모든 변화**를 봐줬다. 그러면
#:   키트 레지스트리뿐 아니라 `kit_instances`·`dataset_snapshots` **오염까지 통과**한다 —
#:   화면 검증 한 번으로 업무 데이터가 운영 영역에 들어와도 초록이 뜬다.
#: ★ 그래서 표 단위로 못박는다: 화면 검증이 만들어도 되는 것은 **키트 레지스트리뿐**이고,
#:   업무 행(인스턴스·판)은 **0 이어야 한다.**
#: ⚠️⚠️ 「상한 0」이 아니라 **「전후 같아야 한다」**이다. 상한만 보면 기준선 1건 → 0건
#:   **삭제도 통과**한다 — 사라진 것도 이상한 일이고, 누가 지웠는지 물어야 한다.
PROTECTED_ROWS = (
    "data/data_preparation.db:kit_instances",
    "data/data_preparation.db:dataset_snapshots",
    "data/data_preparation.db:source_bindings",
    "data/data_preparation.db:readiness_evaluations",
    "data/data_preparation.db:baseline_builds",
    #: ★ 조직 트리와 실행 문맥은 **회귀가 건드릴 이유가 없다.** 바뀌었다면 격리가 깨진 것이다.
    "data/enterprise_context.db:organization_nodes",
    "data/enterprise_context.db:organization_edges",
    "data/enterprise_context.db:enterprise_entities",
    "data/collaboration.db:decision_cases",
    "data/collaboration.db:publications",
    "data/collaboration.db:publication_versions",
)


def _file_state(rel: str) -> dict | None:
    """존재·크기·해시. 없으면 `None` — 「없음」과 「0바이트」는 다르다."""
    path = ROOT / rel
    if not path.exists():
        return None
    data = path.read_bytes()
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()[:16]}


def _rows(rel: str, table: str) -> int | str | None:
    """행 수. 파일이 없으면 `None`, 못 읽으면 `"unreadable"`.

    ⚠️ 셋을 구분한다 — 「없다」·「못 읽었다」·「0행이다」는 서로 다른 사실이다.
    ⚠️ `immutable=1` — 읽기가 SHM 을 만들지 않게."""
    path = ROOT / rel
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
        try:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        finally:
            conn.close()
    except Exception:
        return "unreadable"


def _content(rel: str, table: str) -> str | None:
    """보호 표의 **정렬된 내용 지문.** 없으면 `None`, 못 읽으면 `"unreadable"`.

    ★★★ [2026-08-20 Supervisor 지적 P0-2] **행 수만 비교하면 변조를 놓친다.**
      browser 모드는 `data_preparation.db` 의 파일 변경을 허용하므로, 행 수가 같은
      다음 변조가 그대로 통과한다:

        · `source_bindings.state` 를 바꾼다        · Snapshot checksum 을 바꾼다
        · readiness 판정값을 고친다                 · baseline fingerprint 를 갈아끼운다
        · 기존 레코드의 **조직 범위**를 바꾼다

    ⚠️ 마지막 것이 특히 나쁘다 — 남의 조직 데이터가 우리 것으로 보이게 되는데
      **행 수는 그대로**다.

    ★ 그래서 전 행을 정렬해 한 줄로 잇고 해시한다. 열 순서는 `PRAGMA table_info` 의
      순서를 쓰되 **이름순으로 고정**한다 — 열이 추가돼도 기존 열의 비교가 흔들리지
      않게.
    ⚠️ `immutable=1` — 읽기가 SHM 을 만들지 않게(이 검사가 자기를 오염시키지 않게)."""
    path = ROOT / rel
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
        try:
            cols = sorted(str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})"))
            if not cols:
                return "unreadable"
            picked = ", ".join(f'"{c}"' for c in cols)
            rows = conn.execute(f"SELECT {picked} FROM {table}").fetchall()
        finally:
            conn.close()
    except Exception:
        return "unreadable"
    #: ★ 행 순서는 저장소가 정한다 — 우리가 **정렬**해야 비교가 안정된다.
    canon = "\n".join(sorted(repr(tuple(r)) for r in rows))
    return hashlib.sha256((",".join(cols) + "\n" + canon).encode("utf-8")).hexdigest()[:16]


def snapshot() -> dict:
    return {
        "files": {rel: _file_state(rel) for rel in WATCH},
        "rows": {f"{rel}:{tab}": _rows(rel, tab) for rel, tab in TABLES},
        #: ★ 보호 표만 내용까지 본다 — 전 표를 해시하면 느리고, 지켜야 할 것은 업무 행이다.
        "content": {key: _content(*key.split(":", 1)) for key in PROTECTED_ROWS},
    }


def _dirty_wal() -> list[tuple[str, int]]:
    """**비어 있지 않은 WAL** 을 가진 DB 들. 비어 있으면 빈 목록.

    ★★★ [2026-08-20 Supervisor 지적] 이 검사는 `immutable=1` 로 읽는다 — 그래서
      **WAL 에만 있는 내용은 보이지 않는다.** 실측:

        WAL 에만 있는 행 1건 → immutable=1 은 «no such table» 로 실패한다

      실패하면 `_rows`·`_content` 가 `"unreadable"` 을 돌려주고, 전후 둘 다
      `"unreadable"` 이면 **값이 같으므로 통과한다.**

    ⚠️⚠️ 즉 «서버가 떠 있는 채로 돌린 검사» 는 아무것도 지키지 않으면서 초록을 준다.
      화면 검증(browser 모드) 직후가 정확히 그 상황이다.

    ★ 체크포인트는 **하지 않는다** — 이 검사가 무언가를 쓰기 시작하면 그때부터는
      「검사 때문에 바뀐 것」과 「오염」을 구별할 수 없다. 대신 멈추고 사람에게 말한다.

    ⚠️ 크기 0 인 WAL 은 정상이다(깨끗하게 닫힌 상태). 파일이 없는 것도 정상이다."""
    dirty = []
    for db in DBS:
        wal = ROOT / (db + "-wal")
        try:
            size = wal.stat().st_size if wal.exists() else 0
        except OSError:                                   # pragma: no cover - 방어
            size = -1
        if size != 0:
            dirty.append((db + "-wal", size))
    return dirty


def _wal_gate() -> int:
    """WAL 이 깨끗하지 않으면 **검사를 중단한다.** 0 이면 계속해도 좋다."""
    dirty = _dirty_wal()
    if not dirty:
        return 0
    print("✗ 비어 있지 않은 WAL 이 있어 검사를 중단합니다.")
    for rel, size in dirty:
        print(f"    {size:>12,} B  {rel}")
    print()
    print("  · 이 검사는 `immutable=1` 로 읽으므로 **WAL 안의 내용을 보지 못합니다.**")
    print("    그대로 진행하면 «못 읽음» 이 전후로 같아서 **거짓 초록**이 됩니다.")
    print("  · 서버(uvicorn·vite 백엔드)를 내린 뒤 다시 부르십시오.")
    print("  · 이 검사는 체크포인트를 하지 않습니다 — 아무것도 쓰지 않는 것이 전제입니다.")
    return 2


def _head() -> str:
    """지금 HEAD. 못 읽으면 빈 문자열 — **추측하지 않는다.**"""
    import subprocess

    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def cmd_capture(mode: str, force: bool) -> int:
    """기준선을 기록한다. ★★★ **덮어쓰지 않는다.**

    ⚠️⚠️ [2026-08-20 Supervisor 지적 P0-4] 종전에는 조용히 덮어썼다. 그러면 오염이 난
      뒤에 `capture` 를 다시 돌리는 순간 **오염된 상태가 새 «정상»** 이 되고, 그 뒤로는
      아무리 비교해도 초록이다 — 증거가 사라진 줄도 모른다.
    ★ 그래서 이미 있으면 거부한다. 정말 새로 잡으려면 `--force` 를 **사람이** 준다."""
    #: ★ 기준선 자체가 WAL 때문에 «못 읽음» 으로 잡히면 그 기준선은 처음부터 못 믿는다.
    if _wal_gate():
        return 2
    if BASELINE.exists() and not force:
        print(f"✗ 기준선이 이미 있습니다: {BASELINE.name}")
        print("  · 비교를 먼저 하십시오 — 덮어쓰면 **오염된 상태가 새 정상**이 됩니다.")
        print("  · 정말 새로 잡으려면 `--force` 를 주십시오(그 결정은 사람이 합니다).")
        return 2
    state = snapshot()
    state["_meta"] = {"head": _head(), "workspace": str(ROOT), "mode": mode,
                      "at": __import__("datetime").datetime.now().isoformat(timespec="seconds")}
    BASELINE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    have = sum(1 for v in state["files"].values() if v)
    print(f"· 기준선 기록 — 파일 {have}/{len(WATCH)}개 존재, 표 {len(state['rows'])}개")
    print(f"  HEAD {state['_meta']['head'][:12] or '(모름)'} · mode={mode}")
    print(f"  {BASELINE.name}")
    return 0


def _why(rel: str) -> str:
    """왜 봐줬는지 **줄마다 적는다** — 면제는 이유가 보여야 다시 판단할 수 있다."""
    if rel in READ_ARTIFACT_FILES:
        return " (읽기만 해도 생기는 파일 — 내용은 여전히 지킨다)"
    return " (화면 검증에서 예상됨)"


def cmd_compare(mode: str) -> int:
    if _wal_gate():
        return 2
    if not BASELINE.exists():
        print("✗ 기준선이 없습니다 — 회귀 **전에** `capture` 를 먼저 돌리십시오.")
        return 2
    before = json.loads(BASELINE.read_text(encoding="utf-8"))
    after = snapshot()
    bad: list[str] = []

    #: ★★★ 다른 HEAD·다른 모드의 기준선과 비교하지 않는다.
    #: ⚠️ 코드가 바뀌면 만들어지는 파일도 바뀐다 — 그 차이를 「오염」으로 읽으면
    #:   검사가 늑대를 외치고, 그러면 아무도 안 본다.
    meta = before.get("_meta") or {}
    if meta.get("head") and meta["head"] != _head():
        print(f"✗ 기준선은 HEAD {meta['head'][:12]} 에서 잡혔고 지금은 {_head()[:12]} 입니다.")
        print("  · 같은 HEAD 에서 다시 잡고 비교하십시오.")
        return 2
    if meta.get("mode") and meta["mode"] != mode:
        print(f"✗ 기준선 모드는 «{meta['mode']}» 인데 «{mode}» 로 비교하려 합니다.")
        return 2

    #: ★★★ [2026-08-20] **기준선에 «못 읽음» 이 있으면 비교를 거부한다.**
    #: ⚠️⚠️ 전후가 둘 다 `"unreadable"` 이면 «같다» 가 되어 통과한다. 그것이 없는 표
    #:   `kits` 를 세던 사고였고, WAL 이 더러울 때 다시 일어나는 사고다. 두 번 같은
    #:   방식으로 속았으면 **그 값 자체를 실패로 못박는** 것이 맞다.
    unread = sorted(k for k, v in (before.get("rows") or {}).items() if v == "unreadable")
    unread += sorted(f"{k}(내용)" for k, v in (before.get("content") or {}).items()
                     if v == "unreadable")
    if unread:
        print(f"✗ 기준선에 «못 읽음» 이 {len(unread)}건 있어 비교를 거부합니다.")
        for k in unread:
            print(f"    {k}")
        print("  · 전후가 둘 다 «못 읽음» 이면 «같다» 가 되어 **거짓 초록**이 됩니다.")
        print("  · 서버를 내리고 `capture --force` 로 기준선을 다시 잡으십시오.")
        return 2

    allowed = (BROWSER_ALLOWED_FILES if mode == "browser" else set()) | READ_ARTIFACT_FILES

    print("=== 파일 ===")
    for rel in WATCH:
        b, a = before["files"].get(rel), after["files"].get(rel)
        if b == a:
            continue
        if b is None and a is not None:
            note = _why(rel) if rel in allowed else ""
            print(f"  {'●' if rel in allowed else '✗'} {rel} **새로 생김** "
                  f"{a['size']}바이트{note}")
            if rel not in allowed:
                bad.append(rel)
        elif a is None:
            #: ⚠️ 사라진 것도 이상하다 — 누가 지웠는지 물어야 한다.
            print(f"  ✗ {rel} **사라짐**")
            bad.append(rel)
        else:
            note = _why(rel) if rel in allowed else ""
            print(f"  {'●' if rel in allowed else '✗'} {rel} 바뀜 "
                  f"{b['size']}→{a['size']}바이트{note}")
            if rel not in allowed:
                bad.append(rel)

    print("=== 행 수 ===")
    for key in after["rows"]:
        b, a = before["rows"].get(key), after["rows"][key]
        if b == a:
            continue
        #: ⚠️ 「못 읽음」으로 바뀐 것도 위반이다 — 통과로 세지 않는다.
        rel = key.split(":", 1)[0]
        #: ★★★ [P0-4] **파일 허용과 표 허용을 분리한다.** browser 모드라도 업무 행이
        #:   늘면 실패다 — 화면 검증이 만들어도 되는 것은 키트 레지스트리뿐이다.
        if mode == "browser" and key in PROTECTED_ROWS:
            #: ★★★ 보호 표는 **증감 둘 다** 실패다(여기 온 것 자체가 이미 달라진 것).
            print(f"  ✗ {key} {b} → {a} (browser 에서도 업무 행은 그대로여야 한다)")
            bad.append(key)
            continue
        file_ok = rel in allowed and key not in PROTECTED_ROWS
        note = " (화면 검증에서 예상됨)" if file_ok else ""
        print(f"  {'●' if file_ok else '✗'} {key} {b} → {a}{note}")
        if not file_ok:
            bad.append(key)

    print("=== 보호 표 내용 ===")
    for key in PROTECTED_ROWS:
        b = (before.get("content") or {}).get(key)
        a = (after.get("content") or {}).get(key)
        if b == a:
            continue
        #: ★★★ 행 수가 같아도 내용이 바뀌면 위반이다 — browser 모드도 예외가 아니다.
        print(f"  ✗ {key} 내용이 바뀜 {b} → {a}")
        bad.append(f"{key}(내용)")

    print()
    if bad:
        print(f"=== 운영 불변식 위반 {len(bad)}건 ===")
        for x in bad:
            print("  -", x)
        print()
        print("⚠️ **아무것도 지우지 마십시오.** 상태를 기록하고 원인부터 찾습니다 —")
        print("   지우면 증거가 사라지고, 같은 일이 다시 나도 처음처럼 보입니다.")
        return 1
    print("=== 운영 데이터 영역이 회귀 전과 같습니다 ===")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("capture", "compare"))
    ap.add_argument("--mode", choices=("tests", "browser"), default="tests",
                    help="browser 는 화면 검증까지 한 상태 — 키트 레지스트리 «파일» 만 허용하고 "
                         "업무 행(인스턴스·판)은 여전히 0 이어야 한다")
    ap.add_argument("--force", action="store_true",
                    help="기준선을 덮어쓴다. ⚠️ 오염된 상태를 새 «정상» 으로 만들 수 있다")
    args = ap.parse_args()
    if args.command == "capture":
        return cmd_capture(args.mode, args.force)
    return cmd_compare(args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
