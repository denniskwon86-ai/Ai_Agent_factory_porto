"""[P1] 확정 판본 동결 — 검증이 끝난 키트를 **그 자리에서 못 고치게** 한다.

## 이 파일이 막는 것 하나

★★★ **`status` 가 `VALIDATED_*`·`APPROVED_*` 인 판본은 다시 생성되지 않는다.**
  생성기를 한 번 더 돌리는 것만으로 검증이 끝난 판본이 바뀌면, 그 판본을 근거로 한
  모든 것(등록부 지문·골든 케이스·대외 자료)이 조용히 어긋난다.

⚠️ 실제로 그렇게 됐다. `KIT-MFG-NONFERROUS-PROCUREMENT 1.0.0`(`VALIDATED_FOR_DEMO`,
  `generated_at 2026-08-11`)에 드라이버를 더하려고 생성기를 돌리자 `generated_at` 이
  `2026-09-10` 이 됐다. 1.0.0 이 더 이상 원래의 1.0.0 이 아니게 된 것인데,
  **아무 오류도 나지 않았다.**

## 왜 DB 만으로는 안 되는가

⚠️ `store.upsert_kit_version` 은 같은 `(kit_id, version)` 을 **내용으로 덮는다** —
  「문서가 고쳐지면 지문이 달라지고 그 사실이 보여야 한다」는 설계다. 보여 주는 것과
  막는 것은 다르다. 등록부에 남기기 **전에** 파일 층에서 막아야 한다.

## 두 겹으로 막는다

1. **`.frozen` 표식** — 사람이 「이 판본은 확정」이라고 선언한 것. 명시적이다.
2. **`manifest.status`** — 표식을 깜빡해도 `VALIDATED_*`·`APPROVED_*` 면 거부한다.
   생성 직후 상태(`GENERATED_UNDER_VALIDATION`)는 아직 확정이 아니므로 통과시킨다.

지문은 **내용에서만** 유도한다. 파일 시각·경로를 섞으면 같은 판본을 다른 곳에
복사했을 때 달라져 「바뀌었다」는 거짓 경보가 난다.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

#: 동결 표식과 지문 대장. 지문 계산에서는 **자기 자신을 뺀다** — 넣으면 쓰는 순간
#: 지문이 달라져 영원히 대조가 실패한다.
FROZEN_MARK = ".frozen"
FINGERPRINT_FILE = "fingerprint.json"
_SELF = {FROZEN_MARK, FINGERPRINT_FILE}

#: 확정으로 보는 상태. 생성기가 직접 찍는 `GENERATED_UNDER_VALIDATION` 은 여기 없다 —
#: 아직 검증 중이라 다시 만들 수 있어야 한다.
FROZEN_STATUS_PREFIXES = ("VALIDATED", "APPROVED", "CERTIFIED", "RELEASED")


class FrozenKitError(RuntimeError):
    """확정 판본을 고치려 했다 — 새 판본으로 내야 한다."""


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_dir(root: str) -> Dict[str, str]:
    """판본 디렉터리의 **파일별 지문**. 키는 `/` 로 맞춘 상대경로다.

    ★ 경로 구분자를 `/` 로 고정한다 — Windows 에서 만든 대장을 Linux 에서 대조하면
      `\\` 와 `/` 가 달라 전부 불일치로 보인다.
    """
    out: Dict[str, str] = {}
    for base, _dirs, files in os.walk(root):
        for name in files:
            if name in _SELF:
                continue
            full = os.path.join(base, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            out[rel] = _sha256(full)
    return dict(sorted(out.items()))


def manifest_status(root: str) -> str:
    p = os.path.join(root, "manifest.json")
    if not os.path.exists(p):
        return ""
    try:
        with open(p, encoding="utf-8") as f:
            return str(json.load(f).get("status") or "")
    except (OSError, ValueError):
        return ""


def is_frozen(root: str) -> bool:
    """`.frozen` 표식이 있거나, manifest 상태가 확정이면 얼어 있는 것으로 본다."""
    if os.path.exists(os.path.join(root, FROZEN_MARK)):
        return True
    return manifest_status(root).upper().startswith(FROZEN_STATUS_PREFIXES)


def freeze_reason(root: str) -> str:
    """왜 얼어 있는지 — 오류 메시지에 그대로 실어 사람이 판단할 수 있게 한다."""
    mark = os.path.join(root, FROZEN_MARK)
    if os.path.exists(mark):
        try:
            with open(mark, encoding="utf-8") as f:
                d = json.load(f)
            return f"{FROZEN_MARK} (동결 {d.get('frozen_at', '?')} · {d.get('reason', '')})"
        except (OSError, ValueError):
            return FROZEN_MARK
    return f"manifest.status = {manifest_status(root)}"


def guard(root: str, *, force: bool = False) -> None:
    """**쓰기 전에 부른다.** 얼어 있으면 막고, 어떻게 해야 하는지 알려 준다."""
    if force or not os.path.isdir(root) or not is_frozen(root):
        return
    raise FrozenKitError(
        f"확정 판본입니다 — {os.path.basename(root)} 는 {freeze_reason(root)} 로 "
        f"동결돼 있습니다.\n"
        f"  이 판본을 근거로 등록부 지문·골든 케이스·대외 자료가 만들어져 있으므로 "
        f"그 자리에서 고치면 조용히 어긋납니다.\n"
        f"  고칠 내용이 있으면 **새 판본**으로 내십시오(예: 1.1.0).\n"
        f"  정말로 덮어써야 한다면 --force 를 주되, 왜 그래야 하는지 커밋 메시지에 "
        f"남기십시오."
    )


def write_freeze(root: str, *, reason: str = "", by: str = "") -> Dict[str, Any]:
    """지문 대장을 쓰고 동결 표식을 남긴다. **검증이 끝난 뒤에** 부른다."""
    if not os.path.isdir(root):
        raise FrozenKitError(f"판본 디렉터리가 없습니다: {root}")
    prints = fingerprint_dir(root)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(os.path.join(root, FINGERPRINT_FILE), "w", encoding="utf-8") as f:
        json.dump({"algorithm": "sha256", "file_count": len(prints),
                   "computed_at": now, "files": prints},
                  f, ensure_ascii=False, indent=2)
    mark = {"frozen_at": now, "reason": reason or "검증 완료 판본",
            "by": by or "unknown", "manifest_status": manifest_status(root),
            "file_count": len(prints)}
    with open(os.path.join(root, FROZEN_MARK), "w", encoding="utf-8") as f:
        json.dump(mark, f, ensure_ascii=False, indent=2)
    return mark


def load_fingerprints(root: str) -> Optional[Dict[str, str]]:
    p = os.path.join(root, FINGERPRINT_FILE)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return dict(json.load(f).get("files") or {})
    except (OSError, ValueError):
        return None


def verify(root: str) -> Tuple[bool, List[str]]:
    """대장과 실제 파일을 대조한다. 대장이 없으면 **검사하지 않고 통과**시킨다 —
    아직 동결하지 않은 판본까지 실패로 만들면 생성 중인 것을 못 쓴다."""
    recorded = load_fingerprints(root)
    if recorded is None:
        return True, []
    actual = fingerprint_dir(root)
    problems: List[str] = []
    for rel, want in recorded.items():
        got = actual.get(rel)
        if got is None:
            problems.append(f"사라짐: {rel}")
        elif got != want:
            problems.append(f"변경됨: {rel}")
    for rel in actual:
        if rel not in recorded:
            problems.append(f"추가됨: {rel}")
    return not problems, sorted(problems)
