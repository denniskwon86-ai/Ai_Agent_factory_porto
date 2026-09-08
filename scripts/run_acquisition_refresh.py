"""[DAO-11] 운영 스케줄러가 부르는 진입점 — 수집 작업 정기 갱신 한 바퀴.

## 쓰는 법

    # 무엇이 돌지 보기만 한다 (아무것도 바꾸지 않는다)
    venv/Scripts/python.exe scripts/run_acquisition_refresh.py --dry

    # 한 바퀴 돈다
    venv/Scripts/python.exe scripts/run_acquisition_refresh.py

    # cron (매일 06:10)
    10 6 * * *  cd /path/to/repo && venv/bin/python scripts/run_acquisition_refresh.py

    # Windows 작업 스케줄러
    schtasks /create /tn "LAXS 수집 갱신" /tr "...\\venv\\Scripts\\python.exe ...\\scripts\\run_acquisition_refresh.py" /sc daily /st 06:10

## ⚠️ 프로세스 안에 타이머를 두지 않는다(지시 9)

이 스크립트는 **한 번 돌고 끝난다.** 반복은 운영 스케줄러의 일이다. 프로세스 안에 타이머를
두면 웹 서버가 4개 뜰 때 같은 수집이 4번 돈다.

## ⚠️ 겹쳐 도는 것을 막는다

앞 실행이 아직 돌고 있는데 다음이 시작하면 같은 작업을 둘이 받는다. 파일 잠금으로 막고,
잠겨 있으면 **조용히 끝낸다**(오류가 아니다 — 다음 주기에 다시 온다).

## 종료 코드

    0  정상 (자료 없음·검토 대기 포함 — 그것은 실패가 아니다)
    1  실행기 자체가 못 돌았다
    2  개별 작업에 실패·격리가 있었다 (스케줄러가 알림을 걸 수 있게 가른다)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LOCK_NAME = "acquisition_refresh.lock"


def _lock_path() -> str:
    from core.paths import data_path
    return data_path(LOCK_NAME)


def _acquire_lock() -> "object | None":
    """겹쳐 돌지 않게 한다. 이미 돌고 있으면 `None`.

    ⚠️ `O_EXCL` 로 만들되 **PID 를 적어 둔다** — 프로세스가 죽어 잠금이 남으면 사람이
      무엇을 지워야 하는지 알아야 한다."""
    path = _lock_path()
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None
    os.write(fd, f"pid={os.getpid()}\n".encode("utf-8"))
    return fd


def _release_lock(fd) -> None:
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.remove(_lock_path())
    except OSError:
        pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="수집 작업 정기 갱신 한 바퀴")
    parser.add_argument("--dry", action="store_true",
                        help="무엇이 돌지 보기만 한다 — 아무것도 바꾸지 않는다")
    parser.add_argument("--limit", type=int, default=25, help="한 바퀴에 도는 최대 작업 수")
    parser.add_argument("--now", default="", help="기준 시각(ISO). 비우면 지금")
    parser.add_argument("--as-of", default="", help="이 시점 이후 발표된 값을 뺀다")
    parser.add_argument("--json", action="store_true", help="결과를 JSON 으로 출력")
    args = parser.parse_args(argv)

    from core.external_intelligence import providers as P
    from core.external_intelligence import refresh_runner as RR
    from core.external_intelligence.acquisition_store import acquisition_store
    from core.external_intelligence.orchestrator import AcquisitionOrchestrator
    from core.external_intelligence.raw_store import raw_store
    #: Provider 등록 — import 만으로 등록부에 들어간다.
    from core.external_intelligence.providers import ecos as _ecos  # noqa: F401
    from core.external_intelligence.providers import datagokr as _datagokr  # noqa: F401
    from core.external_intelligence.providers import kosis as _kosis  # noqa: F401
    from core.external_intelligence.providers import worldbank as _wb  # noqa: F401
    from core.external_intelligence.providers import opendart as _opendart  # noqa: F401

    if args.dry:
        #: ★ 아무것도 바꾸지 않는다 — 목록만 읽는다.
        due = acquisition_store.due_for_refresh(now=args.now, limit=args.limit)
        payload = {"considered": len(due), "jobs": [
            {"job_id": j["job_id"], "provider_id": j["provider_id"],
             "contract_key": j["target_contract_key"], "next_run_at": j["next_run_at"],
             "auto_apply": j["auto_apply"], "schedule_rule": j["schedule_rule"]}
            for j in due]}
        print(json.dumps(payload, ensure_ascii=False, indent=1) if args.json
              else f"돌 차례인 수집 작업 {len(due)}건" + "".join(
                  f"\n  {j['job_id']}  {j['provider_id']:10} → {j['target_contract_key']:8}"
                  f"  다음 {j['next_run_at']}  자동적용 {'켬' if j['auto_apply'] else '끔'}"
                  for j in due))
        return 0

    lock = _acquire_lock()
    if lock is None:
        #: 겹침은 오류가 아니다 — 다음 주기에 다시 온다.
        print(f"앞 실행이 아직 돌고 있습니다({_lock_path()}). 이번 주기는 건너뜁니다.")
        return 0

    try:
        orchestrator = AcquisitionOrchestrator(
            store=acquisition_store, raw_store=raw_store, registry=P.provider_registry)
        report = RR.run_once(orchestrator, now=args.now, limit=args.limit, as_of=args.as_of)
    except Exception as exc:                  # noqa: BLE001
        print(f"실행기가 돌지 못했습니다: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        _release_lock(lock)

    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=1))
    else:
        print(report.summary_line())
        for outcome in report.outcomes:
            mark = "적용" if outcome.applied else outcome.status
            line = f"  {outcome.job_id}  {outcome.provider_id:10} {mark}"
            if outcome.inserted or outcome.duplicate:
                line += f"  신규 {outcome.inserted} · 중복 {outcome.duplicate}"
            if outcome.blocked:
                line += f"  ← {RR.BLOCK_REASONS.get(outcome.blocked, outcome.blocked)}"
                if outcome.blocked_detail:
                    line += f" ({outcome.blocked_detail[:80]})"
            if outcome.error:
                line += f"  오류: {outcome.error[:120]}"
            print(line)

    #: ★ 「자료 없음」과 「검토 대기」는 실패가 아니다 — 종료 코드를 가른다.
    return 2 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
