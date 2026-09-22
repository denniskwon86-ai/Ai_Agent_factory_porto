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


def _checked_target(path) -> Path:
    """링크·junction 대상에는 **쓰지 않는다.** 읽는 쪽과 같은 방향으로 끊는다.

    ★ [CR-1 / 2026-09-22] 처음에는 **따라가도록** 만들었다. 「공유 저장을 링크로 걸어 두는
      구성이 있으니 링크를 보존해야 한다」는 근거였는데, **그 근거가 틀렸다.** 이 저장소는
      읽는 쪽에서 이미 링크를 거절한다:

          core/async_orchestrator.py:295            project_meta.json  → ValueError
          api/routes/factory_control.py:2448        latest_state.json  → 503
          api/routes/factory_control.py:2631·2662 · core/studio_project_files.py:53·56
          core/studio_pause_state.py:37 · core/studio_revision_requests.py:81·87
          core/studio_contract_reconcile.py:219·292 · api/routes/studio_input_draft_control.py:106

      따라가면 **쓰기는 성공하는데 읽기는 503** 이 된다 — W03 이 없애려던 「한쪽에서만
      열리는 자원」을 오히려 만든다. 공유 저장을 링크로 지원하려면 **읽기와 쓰기를 함께**
      바꿔야 하고, 그건 별도 결정이다. 쓰기만 먼저 바꾸는 것은 순서가 틀렸다.

    ⚠️ `scripts/session_data_snapshot.py:70 regular()` 를 재사용하려 했으나 맞지 않았다 —
      `root` 를 받아 경로 탈출까지 보는 함수라 뿌리 개념이 없는 여기서는 쓸 수 없고,
      `core/` 가 `scripts/` 를 import 하면 의존 방향이 뒤집힌다. 대신 저장소가 쓰는 같은
      판정식(`is_symlink() or is_junction()`)을 그대로 따른다.

    보는 범위는 **대상과 그 부모**다 — `factory_control.py:2631` 이 `(target_root, meta_path)`
    를 보는 것과 같은 수준이다. 더 위로 올라가면 배포에서 상위 경로를 링크로 건 정상
    구성까지 막는다.
    """
    target = Path(path)
    for entry in (target, target.parent):
        if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
            # 읽는 쪽과 같은 예외형·같은 어조. 「연결된 …」은 이 저장소의 기존 문구다.
            raise ValueError(f"연결된 경로에는 정본을 쓰지 않습니다: {entry}")
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


def _create_temporary(target: Path, encoding: str):
    """옆자리에 임시 파일을 **짧은 이름**으로 만들고 연다.

    ★★ [실측 결함 2026-09-22] 처음에는 `<원본이름>.<uuid32>.tmp` 였다. 그러면 임시 이름이
      원본보다 **37자 길어지고**, Windows MAX_PATH(260) 근처에서 **원본은 써지는데 임시만
      못 만드는** 일이 실제로 났다 — 회귀에서 `FileNotFoundError`, 경로 278자
      (`…/kitapp_ki_<32자>_APP-03/release.json.<uuid32>.tmp`). 원자 저장을 넣었더니 원래
      되던 게 안 되는 것이라 그냥 결함이다.

    그래서 **정본 이름보다 길지 않게** 유지한다: `.<hex6>.tmp` = 11자
    (`release.json` 12자 · `latest_state.json` 17자). 원본을 쓸 수 있는 경로면 임시도 쓸 수
    있다는 것이 여기서 지키려는 불변식이다. 원본 이름을 버리는 대가로 「누구의 임시인가」를
    이름으로 알 수 없게 되지만, 같은 디렉터리에 있고 `finally` 에서 바로 지운다.

    `"x"` 는 배타 생성이라 남의 임시 파일을 덮어쓰지 않는다. 짧은 난수라 이름이 겹칠 수
    있으므로 그때는 다시 고른다 — 겹침은 실패가 아니다.
    """
    for _ in range(8):
        candidate = target.with_name("." + uuid.uuid4().hex[:6] + ".tmp")
        try:
            return candidate, candidate.open("x", encoding=encoding)
        except FileExistsError:
            continue
    raise OSError(f"임시 파일 이름을 잡지 못했습니다: {target.parent}")


def replace_text(path, text: str, *, encoding: str = "utf-8") -> None:
    """다 쓰고 나서 한 번에 바꾼다. 중간에 실패하면 대상은 **이전 판본 그대로** 남는다.

    텍스트 모드를 쓰는 이유: 기존 저장들이 `open(..., "w", encoding="utf-8")` 이었고,
    바이너리로 바꾸면 줄바꿈 변환이 사라져 **같은 값인데 digest 가 달라진다.** 판본 동일성을
    digest 로 보는 소비자가 있으므로(W03.1) 그 차이를 만들지 않는다.
    """
    target = _checked_target(path)
    temporary, stream = _create_temporary(target, encoding)
    try:
        with stream:
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
