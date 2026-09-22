"""정본 파일의 원자 저장 — 읽는 쪽이 «반쯤 쓰인 파일»을 보지 않게 한다.

## 두 가지는 **다른 문제**다 (둘 다 여기 있다)

    부분 파일   반쯤 쓰인 파일이 읽힌다        → replace_text / replace_json
    lost update 남의 새 판본을 낡은 내용으로   → replace_text_if_unchanged /
                덮어쓴다                          replace_json_if_unchanged

~~⚠️⚠️ 이것은 부분 파일만 막는다.~~ — **2026-09-22 해소.** 처음 판은 부분 파일만 막고
lost update 는 「다른 문제」라며 남겼는데, 지시의 수용문이 「부분 파일**이나 잘못된
판본**을 읽지 않도록」이었다. 두 문제가 다르다는 것은 **「한 번에 달성했다고 쓰지 말라」**
는 뜻이지 **「하나만 해도 된다」가 아니다.** 조건부 저장을 같은 모듈에 세웠다.

⚠️ 그래도 문장은 나눠 쓴다. `replace_text` 는 **여전히 부분 파일만** 막는다 — 늦게 온
  쓰기가 이긴다. 판본 경쟁이 있는 자리는 `*_if_unchanged` 를 써야 한다.

왜 원자적인가: 임시 파일을 **대상과 같은 디렉터리**에 만들기 때문에 같은 filesystem 이고,
그래서 `os.replace` 가 원자적 교체가 된다. 다른 디렉터리(예: `%TEMP%`)에 만들면 볼륨이
달라져 교체가 복사로 떨어지고, 그 순간 부분 파일이 보인다.

`core/studio_project_files.py` 의 B3 승격 저장이 같은 방식을 먼저 썼고, 이 모듈은 그것을
정본 저장 전반이 쓸 수 있게 옮겨 놓은 것이다. 구현은 한 곳만 둔다.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
import hashlib
from pathlib import Path
import time
from typing import Optional, Tuple
import uuid

#: Windows 는 대상 파일이 다른 손에 열려 있으면 교체를 거절한다(공유 위반). 내용이 깨진 게
#: 아니라 «지금은 안 된다»여서, 짧게 몇 번 다시 해 보면 대부분 통과한다.
#: 실측(`scripts/w03_atomic_write_probe.py`): 읽는 쪽이 3초에 5천 번 여는 극단 조건에서
#: 쓰기 실패 **162/180 → 41/180**. 0 이 되지는 않으므로, 그래도 안 되면 **예외를 올린다** —
#: 실패를 성공으로 삼키지 않는다.
_RETRY_DELAYS = (0.005, 0.01, 0.02, 0.04, 0.08)


def _checked_target(path, *, root=None) -> Path:
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

    ★★ [2026-09-22 보완] ~~보는 범위는 대상과 그 부모다.~~ — **뿌리까지 올라간다.**
      처음엔 `(대상, 부모)` 만 봤고, 그러면 `연결된_상위/일반_하위/latest_state.json`
      처럼 **한 칸만 더 위에 junction 을 걸면 그대로 통과**한다. 대상과 부모가 멀쩡해도
      경로가 가리키는 실제 위치는 남의 저장소일 수 있다. 「막았다면 반대편 문을 본다」.

    ⚠️ **정식 mount 는 링크가 아니다.** Windows 의 볼륨 마운트 지점도 reparse point 라
      `is_junction()` 이 참이지만, 그것은 배포가 «의도한» 저장 구성이다. `os.path.ismount`
      로 갈라 **볼륨 마운트는 통과**시키고 디렉터리 junction 만 막는다. 이 구분이 없으면
      공유 저장을 정식 mount 로 붙인 구성에서 제품이 아예 못 쓴다.

    ⚠️ 뿌리를 **모른다고 해서 부모에서 멈추지 않는다.** `root` 가 없으면 파일시스템
      꼭대기까지 올라간다 — 모르는 것을 안전으로 바꾸지 않는다.
    """
    target = Path(os.path.abspath(path))
    #: ★ [CR-W03-2B] `root` 는 **검사 범위를 좁히는 데 쓰지 않는다.** 여기서는 「대상이
    #:   그 뿌리 안에 있는가」만 본다(담김 확인). 링크 검사는 아래에서 언제나 전체
    #:   조상을 훑는다 — 뿌리 위에 걸린 junction 이 숨지 않게.
    if root is not None:
        base = Path(os.path.abspath(root))
        if target != base and base not in target.parents:
            raise ValueError(
                f"명시한 저장 뿌리 안에 있지 않습니다: {target} (뿌리: {base})")
    for entry in _components_to_check(target, root):
        if not _is_link(entry):
            continue
        if _is_formal_mount(entry):
            continue                      # 볼륨 마운트 지점 — 배포가 의도한 구성이다
        # 읽는 쪽과 같은 예외형·같은 어조. 「연결된 …」은 이 저장소의 기존 문구다.
        raise ValueError(f"연결된 경로에는 정본을 쓰지 않습니다: {entry}")
    return target


def _is_link(entry: Path) -> bool:
    """symlink 또는 junction. ⚠️ `resolve()` 를 쓰지 않는다 — 따라가면 «링크였다» 는
    사실 자체가 지워져 검사가 성립하지 않는다."""
    try:
        return bool(entry.is_symlink()
                    or (hasattr(entry, "is_junction") and entry.is_junction()))
    except OSError:
        #: 판정할 수 없으면 «링크가 아니다» 로 넘기지 않는다 — 부르는 쪽이 막는다.
        return True


def _is_formal_mount(entry: Path) -> bool:
    try:
        return os.path.ismount(str(entry))
    except OSError:
        return False


def _components_to_check(target: Path, root=None):
    """대상에서 **파일시스템 꼭대기까지** 모든 구성요소. 예외 없다.

    ⚠️⚠️ [CR-W03-2B] 앞 판은 `root` 가 조상이면 **그 위를 잘라냈다.** 「뿌리보다 위는
      배포의 몫」이라는 주석을 달았는데, 그 주석이 곧 구멍이었다 — 실측 반례:
      `junction/projects/proj/latest_state.json` 에 `root=junction/projects` 를 넘기면
      **예외 없이 링크 너머에 저장**됐다. 제품 호출부가 바로 그 모양으로 부른다.
      주석으로 생략한 검사는 검사가 아니다.

    ★ 그래서 `root` 는 **검사 범위를 좁히지 않는다.** 아래 `_checked_target` 에서
      «담김(containment)» 확인에만 쓰고, 링크 검사는 언제나 전체 조상을 본다.
      정상 배포의 상위 링크는 `_is_formal_mount` 로만 면제된다 — 그쪽이 「의도한
      구성」과 「임의 junction」을 가르는 자리다."""
    return [target] + list(target.parents)


def ensure_directory(path, *, root=None) -> Path:
    """디렉터리를 만들되 **만들기 전에** 링크 경계를 본다.

    ★ `makedirs` 가 검사 밖에 있으면 그 자체가 우회로다 — 연결된 상위 아래에 디렉터리를
      만들어 놓고 나서 「대상은 링크가 아니다」로 통과한다. 선행 쓰기도 같은 경계 안에."""
    target = Path(os.path.abspath(path))
    _checked_target(target / "_", root=root)      # 존재하지 않아도 조상은 검사된다
    os.makedirs(target, exist_ok=True)
    _checked_target(target / "_", root=root)      # 만든 뒤에도 한 번 — 사이에 바뀌었을 수 있다
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


def _write_and_replace(target: Path, text: str, encoding: str) -> None:
    """임시로 다 쓰고 한 번에 교체한다. **조건부 저장과 같은 쓰기 구현을 쓴다** —
    두 벌이 되면 한쪽만 고쳐지는 날이 온다."""
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


def replace_text(path, text: str, *, encoding: str = "utf-8", root=None) -> None:
    """다 쓰고 나서 한 번에 바꾼다. 중간에 실패하면 대상은 **이전 판본 그대로** 남는다.

    ⚠️ **부분 파일만** 막는다. 늦게 온 쓰기가 이긴다 — 판본 경쟁이 있는 자리는
      `replace_text_if_unchanged` 를 쓴다.

    텍스트 모드를 쓰는 이유: 기존 저장들이 `open(..., "w", encoding="utf-8")` 이었고,
    바이너리로 바꾸면 줄바꿈 변환이 사라져 **같은 값인데 digest 가 달라진다.** 판본 동일성을
    digest 로 보는 소비자가 있으므로(W03.1) 그 차이를 만들지 않는다.
    """
    _write_and_replace(_checked_target(path, root=root), text, encoding)


class StaleWriteError(RuntimeError):
    """읽은 판본이 이미 바뀌었다. **덮어쓰지 않았다.**

    ⚠️ 호출자는 이것을 「저장 실패」로 다루되 **낡은 payload 를 새 판본 번호로 다시
      표기해 밀어 넣지 않는다.** 다시 읽고 다시 만들어야 한다."""

    def __init__(self, path, expected: str, actual: str):
        super().__init__(
            f"저장하려는 사이에 정본이 바뀌었습니다: {path} — 다시 읽고 다시 만드십시오.")
        self.path, self.expected, self.actual = str(path), expected, actual


class SaveBusyError(RuntimeError):
    """다른 writer 가 같은 정본을 쓰는 중이다. **아무것도 쓰지 않았다.**"""


def digest_of(path) -> str:
    """정본의 현재 판본 지문. **없으면 빈 문자열**이다.

    ⚠️ 「없음」을 `None` 이 아니라 `""` 로 둔다 — 조건부 저장의 「새로 만드는 경우」가
      `expected_digest=""` 하나로 표현되고, 호출자가 두 어휘를 안 갈라도 된다.
    ⚠️ 바이트로 읽는다. 텍스트로 읽으면 줄바꿈 변환이 끼어 같은 파일의 지문이 플랫폼마다
      달라진다."""
    try:
        with open(path, "rb") as stream:
            return hashlib.sha256(stream.read()).hexdigest()
    except FileNotFoundError:
        return ""


#: 잠금을 기다리는 시간. 짧게 몇 번 — 오래 잡으면 요청이 쌓이고, 안 기다리면 평범한
#: 동시 저장이 그냥 실패한다.
_LOCK_DELAYS = (0.01, 0.02, 0.04, 0.08, 0.16)

#: 잠금 파일의 꼬리. **공개한다** — 정본 옆에 남으므로 목록을 세는 쪽이 가려내야 한다.
LOCK_SUFFIX = ".lck"


def is_lock_file(name) -> bool:
    """이 이름이 잠금 파일인가. 디렉터리를 «내용» 으로 세는 자리가 쓴다."""
    return str(getattr(name, "name", name)).endswith(LOCK_SUFFIX)


@contextmanager
def _target_lock(target: Path):
    """★★ 잠금 파일을 **정본 옆에** 둔다 — 이것이 잠금 «권위» 의 핵심이다.

    ⚠️⚠️ `studio_project_files.operation_lock` 은 잠금 파일을 `data/studio_bootstrap_locks`
      즉 **노드 로컬 경로**에 둔다. 그래서 두 노드가 같은 공유 저장에 써도 **서로의 잠금이
      보이지 않는다** — 프로세스 안 lock 과 다를 바 없어진다. 반면
      `contract_decision._workspace_lock` 은 잠금 파일을 workspace 안에 둔다. 정본이 공유
      저장에 있으면 잠금도 그 위에 있어 **같은 권위**가 된다. 여기서는 그쪽을 따른다.

    ⚠️ 잠금 파일 이름은 **짧게** 유지한다(MAX_PATH 결함을 다시 만들지 않는다).
      대상 이름의 해시 6자라 서로 다른 이름이 드물게 겹칠 수 있는데, 겹치면 **더 직렬화될
      뿐** 정확성은 깨지지 않는다.

    ⚠️ 이것은 **같은 filesystem 을 공유하는 writer 들** 사이의 잠금이다. 공유 저장이 그
      잠금을 지원하지 않는 프로토콜이면 성립하지 않는다 — 실제 공유 마운트에서 다시
      확인해야 한다(이번 증거는 단일 PC 다).
    """
    #: ⚠️⚠️ **잠금 파일은 지우지 않는다.** 놓으면서 지우면 그 사이 다른 프로세스가 같은
    #:   이름으로 새로 열어 잡은 잠금이 «다른 파일» 을 가리키게 되고, 두 writer 가 서로를
    #:   못 본다 — 상호배제가 조용히 사라진다. `contract_decision._workspace_lock` 도
    #:   같은 이유로 남긴다.
    #: ★ 그래서 정본 디렉터리에 `.<hex6>.lck` 이 **남는다.** 목록을 세는 소비자는
    #:   `LOCK_SUFFIX` 로 가려내야 한다(디렉터리를 내용으로만 보는 자리가 있다).
    name = "." + hashlib.sha256(target.name.encode("utf-8")).hexdigest()[:6] + LOCK_SUFFIX
    lock_path = target.with_name(name)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        for delay in _LOCK_DELAYS + (None,):
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                if delay is None:
                    raise SaveBusyError(
                        f"다른 저장이 진행 중입니다: {target} — 다시 시도하십시오.")
                time.sleep(delay)
        yield
    finally:
        if acquired:
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(descriptor)


def replace_text_if_unchanged(path, text: str, *, expected_digest: str,
                              root=None, encoding: str = "utf-8") -> str:
    """읽은 판본이 그대로일 때만 바꾼다. 바뀌었으면 **쓰지 않고 거절**한다.

    ★★ 비교와 교체가 **같은 상호배제 구간 안**에 있어야 한다. 잠금 밖에서 비교하고
      안에서 바꾸면(또는 그 반대) 그 사이가 곧 lost update 의 창이다 — 검사가 있는데
      막지 못하는 모양이 된다.

    돌려주는 것은 **새 판본의 지문**이다. 호출자가 이어서 쓸 때 그대로 기준이 된다.
    """
    target = _checked_target(path, root=root)
    with _target_lock(target):
        actual = digest_of(target)
        if actual != expected_digest:
            raise StaleWriteError(target, expected_digest, actual)
        _write_and_replace(target, text, encoding)
        return digest_of(target)


def replace_json_if_unchanged(path, value, *, expected_digest: str, root=None,
                              **dumps) -> str:
    dumps.setdefault("ensure_ascii", False)
    return replace_text_if_unchanged(path, json.dumps(value, **dumps),
                                     expected_digest=expected_digest, root=root)


def replace_json(path, value, *, root=None, **dumps) -> None:
    """직렬화 정책은 **호출자가 정한다.**

    `sort_keys` 를 여기서 강제하면 기존 파일의 키 순서가 바뀌고, 그러면 내용이 같은데도
    digest 가 달라진다. 호출자마다 쓰던 정책을 그대로 넘기게 둔다.
    """
    dumps.setdefault("ensure_ascii", False)
    replace_text(path, json.dumps(value, **dumps), root=root)
