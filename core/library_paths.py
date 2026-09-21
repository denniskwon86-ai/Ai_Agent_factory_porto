"""라이브러리(게시된 프로그램 보관소) 경로 — **단일 지점.**

## 왜 모듈로 분리했는가 (2026-07-30)

같은 `"library"` 가 세 곳에 각각 선언돼 있었다:
`factory_control.LIBRARY_DIR` · `release_readiness._LIBRARY_DIR` · `program_lifecycle._LIBRARY_DIR`.

⚠️ 세 값이 어긋나면 **조용한 실패**가 난다. 게시는 A 경로에 쓰고, 사용여부 제어는 B 경로를
보므로, 실제로 존재하는 프로그램을 `program_lifecycle` 이 "존재하지 않는 프로그램입니다"로
거부한다 — 그 순간 IT 관리자는 사고를 낸 프로그램을 **끌 수 없다.** 오류 메시지는 경로가
어긋났다는 사실을 말해주지 않으므로(릴리스가 없다고만 한다) 원인을 찾는 데 오래 걸린다.
`program_lifecycle` 이 `library_dir` 주입 인자를 따로 들고 있었던 것도 이 어긋남을
테스트에서 우회하려던 흔적이다 — 우회는 부채이지 해결이 아니다.

## 값이 아니라 함수로 준다

`from core.library_paths import LIBRARY_DIR` 처럼 **값을** import 하면 그 시점에 바인딩이
고정된다. 그러면 테스트가 경로를 바꿔도 소비자는 옛 값을 계속 보고, 중복이 사라진 자리에
"안 먹는 monkeypatch"가 대신 들어선다 — 증상은 같다(실제 프로그램을 없다고 한다).
그래서 소비자는 **호출 시점에** `library_dir()` 을 부른다.

테스트는 이 모듈의 `_LIBRARY_DIR` 하나만 바꾼다:

    monkeypatch.setattr(library_paths, "_LIBRARY_DIR", str(tmp_path / "library"))

LLM 0콜.
"""
import os

from core.paths import project_path

#: ★★★ [W03.1 · 2026-09-22] **저장소 루트 기준 절대경로다.**
#:
#: 종전에는 `"library"` — 프로세스 작업 디렉터리 기준 상대경로였다. 그래서 «어디서
#: 실행됐는가» 에 따라 **다른 위치**를 보았다. 실측:
#:
#:   · 저장소 루트에서 실행  → `<root>/library` (릴리스 29건)
#:   · 다른 디렉터리에서 실행 → `<그곳>/library` — **없다. 릴리스 0건으로 보인다**
#:
#: ⚠️⚠️ 「목록이 비어 보인다」로 끝나지 않는다. 게시는 A 를 보고 사용여부 제어는 B 를
#:   보게 되므로, **실제로 존재하는 프로그램을 끌 수 없다.** 그리고 `makedirs` 를 하는
#:   경로가 엉뚱한 위치에 빈 보관소를 새로 만들어, 그 뒤 게시물이 그쪽에 쌓인다.
#:   `projects/` 는 2026-08-05 에 같은 이유로 절대경로가 됐는데(`core/paths.py`)
#:   **`library/` 만 남아 있었다.** 두 저장 위치의 기준이 다르면 그 자체가 결함이다.
#:
#: ★ 기준은 `PROJECT_ROOT` 다 — «프로세스가 어디서 떴는가» 가 아니라 «이 코드가 어느
#:   저장소에 속하는가». 워크트리에서 돌린 코드는 워크트리 보관소를 본다.
#:
#: ⚠️ 테스트는 여전히 이 상수 하나만 monkeypatch 한다. 다만 **`chdir` 로는 더 이상
#:   격리되지 않는다** — cwd 를 옮겨 격리하던 시험이 있으면 이 상수를 바꾸도록 고친다.
#:   (상대경로를 절대경로로 고칠 때 깨지는 것은 격리가 «틀렸다» 는 뜻이 아니라
#:    격리 지점이 cwd 였다는 뜻이다. 지점을 여기로 옮긴다.)
_LIBRARY_DIR = project_path("library")


def library_dir() -> str:
    """게시된 프로그램 보관소의 루트. **호출 시점에** 읽는다."""
    return _LIBRARY_DIR


def release_dir(release_id: str) -> str:
    """`library/<release_id>` — 릴리스 한 건의 디렉토리."""
    return os.path.join(library_dir(), release_id)


def release_json(release_id: str) -> str:
    """`library/<release_id>/release.json` — 릴리스의 진실원본 파일.

    ★ 이 파일의 존재가 곧 "게시되었다"의 정의다. 존재 여부를 판정하는 코드가 경로를 각자
      조립하면 판정이 갈리므로, 조립은 여기서만 한다."""
    return os.path.join(release_dir(release_id), "release.json")
