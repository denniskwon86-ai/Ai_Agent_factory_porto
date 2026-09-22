"""정본 파일의 원자 저장 — 읽는 쪽이 «반쯤 쓰인 파일»을 보지 않게 한다.

⚠️⚠️ **이것은 부분 파일만 막는다.** 동시 writer 가 남이 방금 올린 새 판본을 자기 낡은
  내용으로 덮어쓰는 것(lost update)은 **다른 문제**이며 여기서 풀지 않는다 —
  `os.replace` 는 늦게 도착한 쓰기를 이기게 할 뿐이다. 그 방지가 필요하면 판본 조건부
  쓰기(읽은 판본과 다르면 거절)를 따로 세워야 한다. 이 파일이 있다고 해서
  「동시 쓰기 안전」이라고 적지 말 것.

왜 원자적인가: 임시 파일을 **대상과 같은 디렉터리**에 만들기 때문에 같은 filesystem 이고,
그래서 `os.replace` 가 원자적 교체가 된다. 다른 디렉터리(예: `%TEMP%`)에 만들면 볼륨이
달라져 교체가 복사로 떨어지고, 그 순간 부분 파일이 보인다.

`core/studio_project_files.py` 의 B3 승격 저장이 같은 방식을 먼저 썼고, 이 모듈은 그것을
정본 저장 전반이 쓸 수 있게 옮겨 놓은 것이다. 구현은 한 곳만 둔다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
import uuid

#: Windows 는 대상 파일이 다른 손에 열려 있으면 교체를 거절한다(공유 위반). 내용이 깨진 게
#: 아니라 «지금은 안 된다»여서, 짧게 몇 번 다시 해 보면 대부분 통과한다.
#: 실측(`scripts/w03_atomic_write_probe.py`): 읽는 쪽이 3초에 5천 번 여는 극단 조건에서
#: 쓰기 실패 **162/180 → 41/180**. 0 이 되지는 않으므로, 그래도 안 되면 **예외를 올린다** —
#: 실패를 성공으로 삼키지 않는다.
_RETRY_DELAYS = (0.005, 0.01, 0.02, 0.04, 0.08)


def _resolved_target(path) -> Path:
    """대상이 링크면 **따라간다** — 링크를 일반 파일로 바꾸지 않는다.

    공유 저장을 심볼릭 링크·junction 으로 걸어 두는 구성이 있다(W03 이 노리는 바로 그
    구성이다). 링크 자체를 `os.replace` 로 갈아치우면 그 공유가 조용히 끊긴다.
    """
    target = Path(path)
    if target.is_symlink() or (hasattr(target, "is_junction") and target.is_junction()):
        return Path(os.path.realpath(target))
    return target


def _replace_with_retry(temporary: Path, target: Path) -> None:
    """교체는 원자적이다. 다만 Windows 에서는 «지금 못 한다»가 나올 수 있어 짧게 다시 건다.

    재시도는 **교체 실패만** 다룬다. 그 사이 다른 writer 가 먼저 바꿔 놓아도 막지 않는다 —
    그건 lost update 이고 이 모듈이 푸는 문제가 아니다(모듈 머리말 참조).
    """
    for delay in _RETRY_DELAYS:
        try:
            os.replace(temporary, target)
            return
        except PermissionError:
            time.sleep(delay)
    os.replace(temporary, target)  # 마지막 시도의 예외는 그대로 호출자에게 간다


def replace_text(path, text: str, *, encoding: str = "utf-8") -> None:
    """다 쓰고 나서 한 번에 바꾼다. 중간에 실패하면 대상은 **이전 판본 그대로** 남는다.

    텍스트 모드를 쓰는 이유: 기존 저장들이 `open(..., "w", encoding="utf-8")` 이었고,
    바이너리로 바꾸면 줄바꿈 변환이 사라져 **같은 값인데 digest 가 달라진다.** 판본 동일성을
    digest 로 보는 소비자가 있으므로(W03.1) 그 차이를 만들지 않는다.
    """
    target = _resolved_target(path)
    temporary = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        # "x" = 배타 생성. 남의 임시 파일을 덮어쓰지 않는다.
        with temporary.open("x", encoding=encoding) as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())  # 교체 전에 내용이 디스크에 닿게 한다
        _replace_with_retry(temporary, target)
    finally:
        # 성공하면 이미 옮겨졌고, 실패했으면 반쪽짜리가 남아선 안 된다.
        if temporary.exists():
            temporary.unlink()


def replace_json(path, value, **dumps) -> None:
    """직렬화 정책은 **호출자가 정한다.**

    `sort_keys` 를 여기서 강제하면 기존 파일의 키 순서가 바뀌고, 그러면 내용이 같은데도
    digest 가 달라진다. 호출자마다 쓰던 정책을 그대로 넘기게 둔다.
    """
    dumps.setdefault("ensure_ascii", False)
    replace_text(path, json.dumps(value, **dumps))
