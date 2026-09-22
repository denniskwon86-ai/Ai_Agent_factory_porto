"""W03.2 증거 — 정본 파일을 «독립 프로세스» 여럿이 동시에 쓸 때 읽는 쪽이 무엇을 보는가.

격리 러너는 `subprocess.Popen` 을 막는다. 그래서 두 프로세스 경쟁은 pytest 안에서 만들 수
없고, 이 probe 를 **러너 밖에서** 돌려 결과를 문서에 남긴다. 그 통제는 끄지 않는다.

무엇을 보는가
  writer 여럿이 같은 경로를 반복해서 덮어쓰는 동안, reader 가 계속 읽는다.
  · atomic  — 제품이 지금 쓰는 `core.atomic_write.replace_json`
  · legacy  — 이번에 걷어낸 옛 방식(`open(...,"w")` + `json.dump`). **음성 대조군**

⚠️ 음성 대조군이 깨지지 않으면 이 probe 는 아무것도 증명하지 못한다 — 경쟁을 재연하지
  못한 것이지 제품이 안전하다는 뜻이 아니다. W03.1 에서 얻은 교훈이다.

⚠️ **부분 파일만 본다.** 「누가 이겼는가」(낡은 판본이 새 판본을 덮는 lost update)는 다른
  문제이며 이 probe 의 판정 대상이 아니다. 마지막에 남은 값이 누구 것인지는 기록만 한다.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _payload(writer_id: int, seq: int, filler: int) -> dict:
    # 한 번에 안 써질 만큼 키운다. 작으면 경쟁이 일어나도 부분 파일이 안 보인다.
    return {"writer": writer_id, "seq": seq, "blob": [f"{writer_id}-{seq}-{i}" for i in range(filler)]}


def _write_once(mode: str, path: str, value: dict) -> None:
    if mode == "atomic":
        from core import atomic_write
        atomic_write.replace_json(path, value, indent=2)
        return
    # legacy: 이번에 걷어낸 방식 그대로. 대상 파일을 열어 놓고 조금씩 쓴다.
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def run_writer(mode: str, path: str, writer_id: int, rounds: int, filler: int) -> int:
    failures = 0
    for seq in range(rounds):
        try:
            _write_once(mode, path, _payload(writer_id, seq, filler))
        except OSError:
            # Windows 는 대상이 다른 손에 열려 있으면 교체를 거절할 수 있다. 세어서 보고한다.
            failures += 1
    print(json.dumps({"writer": writer_id, "write_os_errors": failures}))
    return 0


# ── [2026-09-22 보완] lost update — «부분 파일» 과 **다른 문제** ──────────────
#
# 위 `torn` 판정은 반쯤 쓰인 파일만 본다. 여기서 보는 것은 **남이 방금 올린 새 판본을
# 자기 낡은 내용으로 덮는 것**이다. 원자 교체는 그것을 막지 못한다 — 늦게 온 쓰기가
# 이길 뿐이다.
#
# ⚠️ 두 writer 는 **각각 다른 프로세스**다. 같은 프로세스의 스레드로 재연하면 GIL 과
#   모듈 상태를 공유해 「경쟁이 일어났다」를 말할 수 없다.

def run_conditional_writer(path: str, writer_id: int, rounds: int, mode: str) -> int:
    """기준을 **먼저 읽고**, 그 기준이 그대로일 때만 쓴다.

    `mode="uncontrolled"` 는 음성 대조군 — 같은 순서로 읽되 **조건 없이** 덮는다."""
    from core import atomic_write

    applied = refused = lost = 0
    for seq in range(rounds):
        baseline = atomic_write.digest_of(path)
        try:
            before = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            before = {}
        value = {"writer": writer_id, "seq": seq,
                 "history": list(before.get("history", []))[-20:] + [f"{writer_id}:{seq}"]}
        time.sleep(0.002)          # 읽기와 쓰기 사이를 벌린다 — 실제 처리 시간이다
        try:
            if mode == "conditional":
                atomic_write.replace_json_if_unchanged(
                    path, value, expected_digest=baseline, indent=2)
            else:
                atomic_write.replace_json(path, value, indent=2)
                #: 조건이 없으니 «졌는지» 를 스스로 알 수 없다. 대신 내가 읽은 것이
                #: 남의 판본이었는지로 **남의 것을 지웠는가**를 센다.
                if before.get("writer") not in (None, writer_id):
                    lost += 1
            applied += 1
        except atomic_write.StaleWriteError:
            refused += 1
        except Exception:
            refused += 1
    print(json.dumps({"writer": writer_id, "applied": applied,
                      "refused": refused, "overwrote_others": lost}))
    return 0


def lost_update(writers: int, rounds: int) -> int:
    """두 갈래를 나란히 돌린다. **조건부는 이력이 안 끊기고, 대조군은 끊긴다.**"""
    report = {}
    for mode in ("conditional", "uncontrolled"):
        with tempfile.TemporaryDirectory(prefix=f"w03_lost_{mode}_") as folder:
            target = os.path.join(folder, "latest_state.json")
            from core import atomic_write
            atomic_write.replace_json(target, {"writer": -1, "seq": -1, "history": []},
                                      indent=2)
            children = [_spawn(["conditional-writer", "--path", target,
                                "--writer-id", str(i), "--rounds", str(rounds),
                                "--mode", mode]) for i in range(writers)]
            lines = [child.communicate()[0].strip() for child in children]
            per_writer = [json.loads(l) for l in lines if l]
            final = json.loads(Path(target).read_text(encoding="utf-8"))
            #: ★ 이력이 **몇 번 끊겼는가** — 끊김 하나가 사라진 판본 하나다.
            history = final.get("history", [])
            report[mode] = {
                "per_writer": per_writer,
                "applied_total": sum(w["applied"] for w in per_writer),
                "refused_total": sum(w["refused"] for w in per_writer),
                "final_history_len": len(history),
            }
    verdict = {
        #: 조건부는 «졌으면 거절» 이므로 거절이 있어야 한다. 0 이면 경쟁이 없었던 것이지
        #: 통제가 증명된 것이 아니다.
        "conditional_refuses_stale_writers": report["conditional"]["refused_total"] > 0,
        #: 대조군은 아무도 거절당하지 않는다 — 그래서 남의 판본이 조용히 사라진다.
        "uncontrolled_refuses_nobody": report["uncontrolled"]["refused_total"] == 0,
    }
    print(json.dumps({"what_this_shows":
                      "낡은 판본이 새 판본을 덮는 것(lost update)만 판정한다. 부분 파일은 "
                      "위 compare 가 본다.",
                      "report": report, "verdict": verdict},
                     ensure_ascii=False, indent=2))
    return 0 if all(verdict.values()) else 2


def run_reader(path: str, seconds: float) -> int:
    """★ 실패를 **두 종류로 나눠** 센다. 섞으면 판정이 안 된다.

    · `torn` (ValueError)  — 열리긴 했는데 내용이 JSON 이 아니다. **부분 파일이다.**
    · `locked` (OSError)   — 아예 열리지 않았다. Windows 가 교체 중인 파일을 잠근 것으로,
                             내용이 깨진 것과는 **다른 현상**이다.
    처음에 둘을 한 칸에 세었다가 원자 모드가 실패한 것처럼 보였다. 그건 내 계측 잘못이었다.
    """
    seen, torn, locked, missing, values = 0, 0, 0, 0, set()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with open(path, encoding="utf-8") as stream:
                row = json.load(stream)
        except FileNotFoundError:
            missing += 1
            continue
        except ValueError:
            torn += 1
            continue
        except OSError:
            locked += 1
            continue
        seen += 1
        if isinstance(row, dict) and "writer" in row:
            values.add((row.get("writer"), row.get("seq")))
    print(json.dumps({"read_ok": seen, "torn": torn, "locked": locked, "missing": missing,
                      "distinct_versions": len(values)}))
    return 0


def _spawn(args: list[str]) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-X", "utf8", "-B", str(Path(__file__).resolve()), *args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")


def _one_mode(mode: str, writers: int, rounds: int, filler: int, seconds: float) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"w03_atomic_{mode}_") as folder:
        target = os.path.join(folder, "release.json")
        # 읽을 게 하나는 있어야 「없음」과 「깨짐」이 구분된다.
        _write_once("atomic", target, _payload(-1, -1, filler))
        reader = _spawn(["reader", "--path", target, "--seconds", str(seconds)])
        writer_procs = [_spawn(["writer", "--mode", mode, "--path", target, "--writer-id", str(i),
                                "--rounds", str(rounds), "--filler", str(filler)])
                        for i in range(writers)]
        write_errors = 0
        for proc in writer_procs:
            out, err = proc.communicate()
            if err.strip():
                print(err.strip(), file=sys.stderr)
            for line in out.splitlines():
                write_errors += json.loads(line).get("write_os_errors", 0)
        out, err = reader.communicate()
        if err.strip():
            print(err.strip(), file=sys.stderr)
        stats = json.loads(out.splitlines()[-1])
        leftovers = sorted(p.name for p in Path(folder).iterdir() if p.name != "release.json")
        final = None
        try:
            with open(target, encoding="utf-8") as stream:
                row = json.load(stream)
            final = {"writer": row.get("writer"), "seq": row.get("seq")}
        except (OSError, ValueError):
            final = "UNREADABLE"
        stats.update({"mode": mode, "write_os_errors": write_errors,
                      "leftover_files": leftovers, "final_value": final})
        return stats


def compare(writers: int, rounds: int, filler: int, seconds: float) -> int:
    atomic = _one_mode("atomic", writers, rounds, filler, seconds)
    legacy = _one_mode("legacy", writers, rounds, filler, seconds)
    verdict = {
        "atomic_never_shows_torn_file": atomic["torn"] == 0 and atomic["missing"] == 0,
        "atomic_leaves_no_temp_files": atomic["leftover_files"] == [],
        "legacy_control_does_tear": legacy["torn"] > 0,
    }
    report = {
        "what_this_shows": "부분 파일(torn)만 판정한다. 낡은 판본이 새 판본을 덮는 lost update 는 "
                           "다른 문제이며 여기서 판정하지 않는다.",
        "evidence_scope": "단일 PC 의 독립 프로세스들. 두 호스트·공유 마운트 증거가 아니다.",
        "windows_note": "locked/write_os_errors 는 Windows 가 교체 중 파일을 잠가 생긴다. "
                        "내용 손상이 아니며 쓰기 쪽에는 예외로 올라간다 — 조용히 삼키는 "
                        "호출자가 있으면 그쪽에서 저장이 사라진다(별건).",
        "atomic": atomic, "legacy_negative_control": legacy, "verdict": verdict,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not verdict["legacy_control_does_tear"]:
        print("음성 대조군이 깨지지 않았다 — 경쟁을 재연하지 못했다. 이 실행은 증거가 아니다.",
              file=sys.stderr)
        return 2
    return 0 if all(verdict.values()) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("compare", "writer", "reader", "lost-update", "conditional-writer"):
        part = sub.add_parser(name)
        part.add_argument("--path")
        part.add_argument("--mode", default="atomic")
        part.add_argument("--writer-id", type=int, default=0)
        part.add_argument("--writers", type=int, default=3)
        part.add_argument("--rounds", type=int, default=60)
        part.add_argument("--filler", type=int, default=4000)
        part.add_argument("--seconds", type=float, default=3.0)
    args = parser.parse_args()
    if args.command == "writer":
        return run_writer(args.mode, args.path, args.writer_id, args.rounds, args.filler)
    if args.command == "reader":
        return run_reader(args.path, args.seconds)
    if args.command == "conditional-writer":
        return run_conditional_writer(args.path, args.writer_id, args.rounds, args.mode)
    if args.command == "lost-update":
        return lost_update(args.writers, args.rounds)
    return compare(args.writers, args.rounds, args.filler, args.seconds)


if __name__ == "__main__":
    raise SystemExit(main())
