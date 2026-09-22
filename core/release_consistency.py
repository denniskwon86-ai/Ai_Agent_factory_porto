"""[W03.3] 릴리스 **정본 파일**과 **사용여부 DB** 가 서로 다른 말을 하는 곳을 찾는다.

## 왜 갈라지는가

한 릴리스의 사실이 두 곳에 나뉘어 있다.

```
library/<release_id>/release.json   정본 — 무엇인가 · 누구 것인가(소유문맥)
data/program_lifecycle.db           사용여부 — 켜져 있는가 · 왜 껐는가 · 누가 껐는가
```

`program_lifecycle._release_exists()` 는 **파일만** 보고, `get_status()` 는 **DB 만** 본다.
대조하는 곳이 없다. 그래서 둘이 어긋나면 «같은 질문에 두 답» 이 된다.

## ⚠️ 이 모듈은 **고치지 않는다**

읽기만 한다. 복구는 다음 둘 중 하나를 골라야 하는데 **둘 다 자료를 잃는다**:

- DB 행을 지운다 → 「관리자가 이 프로그램을 껐다」는 **결정 기록이 사라진다.**
  껐던 릴리스가 다시 게시되면 **켜진 채로 돌아온다.**
- 파일을 되살린다 → **내용을 알 수 없다.** DB 에는 상태만 있고 정본이 없다.

그래서 무엇을 정본으로 삼을지는 **사람이 정할 일**이고, 이 모듈은 사실만 넘긴다.
(W03.3 지시: 「자료삭제/정본선택이 필요한 충돌은 임의로 덮어쓰지 말고 주요결정으로 올린다」)

## 무엇이 불일치인가 — 「파일 없는데 DB 에 행이 있다」 하나다

★ **「파일 있고 DB 행 없음」은 불일치가 아니다.** `get_status()` 가 미기록을
  `active` + `recorded=False` 로 답하도록 **설계돼 있다**(이 기능 이전에 게시된 것들).
  그것까지 불일치로 세면 정상 상태가 매번 경보로 뜬다.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from core import library_paths

#: 파일을 읽어 소유문맥을 얻을 때 쓰는 필드. `project_visibility` 의 판정 재료와 맞춘다.
_CONTEXT_FIELDS = ("tenant_id", "entity_mode", "enterprise_scope_id",
                   "owner_dept_id", "project_id")


def _safe_id(release_id: str) -> bool:
    """`program_lifecycle._release_exists` 와 **같은 판정**을 쓴다. 여기서 더 느슨하면
    저 쪽이 「없다」고 한 것을 여기서 「있다」고 하게 된다."""
    return bool(release_id) and not any(c in release_id for c in ("/", "\\", ".."))


def _artifact_present(release_id: str) -> bool:
    if not _safe_id(release_id):
        return False
    return os.path.exists(library_paths.release_json(release_id))


def scan(lifecycle=None) -> Dict[str, Any]:
    """DB 행과 보관소 파일을 대조한다. **읽기 전용.**

    돌려주는 것:
      `orphaned_status` — ⚠️ 불일치다. DB 에 행이 있는데 정본 파일이 없다.
      `unrecorded_artifacts` — 파일은 있고 DB 행이 없다. **설계상 정상**이며 수만 센다.
      `context_unavailable` — 파일이 없어 **소유문맥을 판정할 수 없는** 릴리스.
                              「다른 문맥 노출 차단」이 성립하지 않는 자리다.
    """
    if lifecycle is None:
        from core.program_lifecycle import program_lifecycle as lifecycle

    recorded = {str(row.get("release_id") or ""): row for row in lifecycle.list_statuses()}
    orphaned: List[Dict[str, Any]] = []
    for release_id, row in recorded.items():
        if _artifact_present(release_id):
            continue
        orphaned.append({
            "release_id": release_id,
            "status": row.get("status"),
            "recorded_by": row.get("changed_by", ""),
            "recorded_at": row.get("changed_at", ""),
            "reason": row.get("reason", ""),
            #: ★ 파일이 없으므로 **이 릴리스가 누구 것인지 알 수 없다.** 그래서 문맥으로
            #:   거르지도 못한다 — 상태를 그대로 답하면 그 자체가 노출이다.
            "ownership": None,
        })

    present: List[str] = []
    library_root = library_paths.library_dir()
    if os.path.isdir(library_root):
        for entry in sorted(os.listdir(library_root)):
            if _artifact_present(entry):
                present.append(entry)

    return {
        "checked_status_rows": len(recorded),
        "checked_artifacts": len(present),
        "orphaned_status": sorted(orphaned, key=lambda row: row["release_id"]),
        "unrecorded_artifacts": sorted(r for r in present if r not in recorded),
        "context_unavailable": sorted(row["release_id"] for row in orphaned),
        "consistent": not orphaned,
        #: 이 모듈이 무엇을 하지 «않는지» 를 결과가 스스로 말하게 한다.
        "note": ("식별만 한다. 복구는 DB 결정 기록이나 정본 중 하나를 잃으므로 "
                 "사람이 정할 일이다."),
    }


def ownership_of(release_id: str) -> Optional[Dict[str, Any]]:
    """정본 파일에서 소유문맥을 읽는다. 파일이 없거나 깨졌으면 **`None`** — 「판정 불가」다.

    ⚠️ `None` 을 「제한 없음」으로 읽으면 안 된다. `project_visibility.ownership_visible`
      이 `own is None` 을 **차단**으로 다루는 것과 같은 계약이다.
    """
    if not _artifact_present(release_id):
        return None
    try:
        from core.studio_project_files import read_json

        row = read_json(library_paths.release_json(release_id))
    except Exception:
        return None
    return {field: row.get(field) for field in _CONTEXT_FIELDS}
