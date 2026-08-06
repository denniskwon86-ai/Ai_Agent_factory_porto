"""프로젝트 삭제 정책의 **단일 지점** (사용자 결정 2026-08-07).

## 결정 내용

> 「이미 등록된 프로젝트는 **등록자가 지울 수 있고**(삭제 플래그만 처리, 실제 삭제는 하지
>  않음, 데이터는 남겨둠), **타부서 또는 다른 사람에게 공유·전달 단계까지 된 건 admin 만**
>  삭제 처리 가능하게 하고, **실제 지울 수 있는 권한도 admin 만** 가지도록.」

세 가지가 한 문장에 들어 있어 코드로 옮길 때 갈라지기 쉽다. 그래서 여기 한 곳에 둔다.

| 무엇을 | 누가 | 결과 |
|---|---|---|
| 표시 삭제(soft) — **공유 이력 없음** | 등록자 · admin | `project_meta.json` 에 표시. 파일은 그대로 |
| 표시 삭제(soft) — **공유·전달됨** | **admin 만** | 같음 |
| 실제 삭제(hard) | **admin 만** | 디렉터리·체크포인트 제거 |

## 이 파일이 지키는 것

★ **판정과 실행을 나눈다.** `classify()` 는 «되는가/왜 안 되는가» 만 답하고 아무것도 바꾸지
  않는다. 라우트·스크립트·화면이 같은 답을 얻는다 — 「화면은 버튼을 보여 주는데 서버는
  거부한다」가 이 저장소가 반복해서 만든 모양이다.

★★ **모르면 막는다.** 소유권 기록이 없는 프로젝트는 «등록자» 를 확인할 수 없다. 종전
  `assert_project_writable` 은 그런 프로젝트를 **통과**시켰다(「소유권 미기록 프로젝트에 대한
  관대함」). 읽기라면 그 관대함이 맞지만 **되돌릴 수 없는 삭제에는 맞지 않는다** —
  실측에서 viewer 계정이 `DELETE /projects/{id}` 로 200 을 받은 원인이 바로 이것이다.
  → 등록자를 모르면 admin 만 지울 수 있다. 「모르는 것을 0으로 두지 않는다」와 같은 규칙이다.

⚠️ **공유 여부를 «조회 실패» 로 판정하지 않는다.** 공유 저장소를 못 읽으면 «공유 안 됨» 이
  아니라 **모른다**이고, 모르면 admin 만 지울 수 있다. 반대로 하면 저장소가 잠깐 죽은 사이에
  공유된 프로젝트가 지워진다.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Optional

#: `project_meta.json` 에 남기는 표시 삭제 필드. **파일은 지우지 않는다.**
DELETED_AT = "deleted_at"
DELETED_BY = "deleted_by"
DELETED_REASON = "deleted_reason"

#: 릴리스 id 형식 — `{project_id}_{YYYYMMDD}_{HHMMSS}`(`factory_control.save_release`).
#: ⚠️ 단순 `startswith(pid + "_")` 로 세지 않는다. 프로젝트 `abc` 와 `abc_2` 가 있으면
#:   `abc_2_...` 를 `abc` 의 릴리스로 오인해 **남의 프로젝트 공유 이력 때문에 삭제가 막힌다.**
_RELEASE_SUFFIX = re.compile(r"^\d{8}_\d{6}$")


class DeletionError(PermissionError):
    """삭제할 수 없다. 라우트가 403 으로 옮긴다."""


@dataclass(frozen=True)
class DeletionVerdict:
    """판정 결과. **불변**이며 `classify()` 만이 만든다."""
    #: 표시 삭제를 할 수 있는가
    may_soft_delete: bool
    #: 실제 삭제를 할 수 있는가 (admin 만)
    may_hard_delete: bool
    #: 이 프로젝트가 남에게 공유·전달된 적이 있는가. `None` = **확인하지 못했다**(0건 아님)
    shared: Optional[bool]
    #: 왜 안 되는지. 허용이면 빈 문자열
    reason: str = ""
    #: 등록자로 확인된 사용자. 빈 문자열이면 «모른다»
    owner_user_id: str = ""

    def assert_soft(self) -> None:
        if not self.may_soft_delete:
            raise DeletionError(self.reason)

    def assert_hard(self) -> None:
        if not self.may_hard_delete:
            raise DeletionError(self.reason or "실제 삭제는 관리자만 할 수 있습니다.")


def is_admin(scope, capabilities=None) -> bool:
    """여기서 말하는 admin. **한 곳에서만 정한다.**

    ⚠️ 라우트마다 「unrestricted 인가」를 따로 쓰면 어긋난다 — 이 저장소가 `_enforced()` 로
      같은 문제를 이미 겪었다(`api/deps._enforced` 주석)."""
    if getattr(scope, "unrestricted", False):
        return True
    caps = capabilities
    if caps is None:
        try:
            from core.admin_capability import resolve
            caps = resolve(scope)
        except Exception:
            return False
    return bool(getattr(caps, "is_platform_admin", False)
                or getattr(caps, "bootstrap", False))


def releases_of(project_id: str) -> Optional[list]:
    """이 프로젝트에서 나온 릴리스 id 들. `None` = **못 읽었다**(빈 목록과 다르다).

    ⚠️ 「library 를 못 읽었다」를 「릴리스가 없다」로 바꾸면, 그 순간 공유된 프로젝트가
      «공유 이력 없음» 이 되어 등록자에게 삭제 권한이 열린다."""
    # ⚠️ 경로를 상수로 import 하지 않는다 — `library_paths` 주석이 그 함정을 적어 두었다
    #   (값으로 가져오면 테스트가 경로를 바꿔도 옛 값을 본다). **호출 시점에** 읽는다.
    from core import library_paths
    try:
        root = library_paths.library_dir()
    except Exception:
        return None
    try:
        names = os.listdir(root)
    except FileNotFoundError:
        return []                      # 라이브러리 자체가 없으면 릴리스도 없다 — 확인된 0건
    except OSError:
        return None                    # 권한·잠금 등 — 모른다
    out = []
    pre = f"{project_id}_"
    for n in names:
        if n.startswith(pre) and _RELEASE_SUFFIX.match(n[len(pre):]):
            out.append(n)
    return out


def was_shared(project_id: str) -> Optional[bool]:
    """타부서·타인에게 **공유·복제·승격·전달** 된 적이 있는가. `None` = 확인하지 못했다.

    네 가지를 **모두** 본다 — 하나라도 있으면 「공유 단계까지 갔다」이다:

    · `workspace_shares`  — 다른 부서에 읽기/복제 권한을 열어 준 기록
    · `workspace_forks`   — 남이 복제해 간 기록
    · `release_promotions`— 전사 승격을 신청·완료한 기록
    · `app_deliveries`    — 사용자에게 앱으로 전달한 기록(CL-1)

    ⚠️ 넷 중 하나라도 **읽지 못하면 `None`** 을 돌려준다. 「셋은 비었고 하나는 못 읽었다」를
      «공유 안 됨» 으로 답하면 그 하나에 기록이 있을 때 그대로 삭제된다."""
    rels = releases_of(project_id)
    if rels is None:
        return None
    if not rels:
        return False                   # 릴리스가 없으면 공유될 대상 자체가 없다

    unknown = False
    try:
        from core.workspace_promotion import workspace
    except Exception:
        return None
    for rid in rels:
        for fn, kwargs in ((getattr(workspace, "list_shares", None), {"release_id": rid}),
                           (getattr(workspace, "list_forks", None), {"source_release_id": rid})):
            if fn is None:
                unknown = True
                continue
            try:
                if fn(**kwargs):
                    return True
            except Exception:
                unknown = True
        try:
            for row in (workspace.list_promotions() or []):
                if str(row.get("release_id") or "") == rid:
                    return True
        except Exception:
            unknown = True
        if _was_delivered(rid) is None:
            unknown = True
        elif _was_delivered(rid):
            return True
    return None if unknown else False


def _was_delivered(release_id: str) -> Optional[bool]:
    """CL-1 앱 전달 기록이 있는가. `None` = 확인하지 못했다.

    ⚠️ 저장소의 `_connect()` 를 그대로 쓴다 — 경로를 여기서 다시 만들면 테스트가 바꿔치기한
      DB 를 못 보고 «전달 없음» 이 되며, 그때 공유된 프로젝트가 지워진다."""
    import sqlite3
    try:
        from core.collaboration_store import collaboration_store
        if not os.path.exists(collaboration_store.db_path):
            return False               # 협업 DB 자체가 없으면 전달도 없다 — 확인된 0건
        with collaboration_store._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM app_deliveries WHERE release_id=? LIMIT 1",
                (release_id,)).fetchone()
        return bool(row)
    except sqlite3.OperationalError:
        return False                   # 테이블 미생성(기능 미사용) — 확인된 0건
    except Exception:
        return None


def classify(scope, user_id: str, project_id: str, *, capabilities=None) -> DeletionVerdict:
    """★ **삭제 판정의 유일한 지점.** 아무것도 바꾸지 않는다."""
    admin = is_admin(scope, capabilities)
    uid = (user_id or "").strip()

    if admin:
        return DeletionVerdict(may_soft_delete=True, may_hard_delete=True,
                               shared=was_shared(project_id), owner_user_id=_owner(project_id))

    if not uid:
        return DeletionVerdict(False, False, None,
                               "삭제하려면 사용자 식별이 필요합니다.")

    owner = _owner(project_id)
    if not owner:
        # ★★ 관대함을 여기서 끊는다 — 읽기의 하위호환이 삭제까지 따라오면 안 된다.
        return DeletionVerdict(
            False, False, was_shared(project_id), owner_user_id="",
            reason=(f"'{project_id}' 의 등록자 기록이 없어 본인 여부를 확인할 수 없습니다 "
                    "— 관리자에게 삭제를 요청하십시오."))
    if owner != uid:
        return DeletionVerdict(
            False, False, was_shared(project_id), owner_user_id=owner,
            reason=(f"'{project_id}' 는 {owner} 가 등록한 프로젝트입니다 "
                    "— 등록자 또는 관리자만 삭제할 수 있습니다."))

    shared = was_shared(project_id)
    if shared is None:
        return DeletionVerdict(
            False, False, None, owner_user_id=owner,
            reason=("이 프로젝트가 남에게 공유·전달됐는지 **확인하지 못했습니다** — "
                    "확인되지 않은 것을 «공유 안 됨» 으로 두고 지울 수 없습니다. "
                    "관리자에게 문의하십시오."))
    if shared:
        return DeletionVerdict(
            False, False, True, owner_user_id=owner,
            reason=("이 프로젝트는 다른 부서·사용자에게 공유 또는 전달됐습니다 "
                    "— 관리자만 삭제할 수 있습니다."))

    # 등록자 본인 + 공유 이력 없음 → 표시 삭제만. 실제 삭제는 여전히 admin 만이다.
    return DeletionVerdict(True, False, False, owner_user_id=owner,
                           reason="실제 삭제는 관리자만 할 수 있습니다.")


def _owner(project_id: str) -> str:
    """등록자. 확인할 수 없으면 빈 문자열 — **«없음» 이 아니라 «모름» 이다.**"""
    try:
        from core.org_directory import org_directory
        own = org_directory.get_ownership("project", project_id) or {}
    except Exception:
        return ""
    return str(own.get("owner_user_id") or "").strip()


# ── 표시 삭제 실행 ──────────────────────────────────────────────────────────
def meta_path(workspace_root: str) -> str:
    return os.path.join(workspace_root, "project_meta.json")


def mark_deleted(workspace_root: str, user_id: str, reason: str = "") -> dict:
    """`project_meta.json` 에 표시만 남긴다. **파일은 하나도 지우지 않는다.**"""
    from datetime import datetime
    p = meta_path(workspace_root)
    data = {}
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}
    data[DELETED_AT] = datetime.now().isoformat(timespec="seconds")
    data[DELETED_BY] = (user_id or "").strip()
    data[DELETED_REASON] = reason or ""
    os.makedirs(workspace_root, exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)                 # ⚠️ 중간에 죽어도 meta 가 반쪽으로 남지 않게
    return {"project_id": os.path.basename(os.path.normpath(workspace_root)),
            DELETED_AT: data[DELETED_AT], DELETED_BY: data[DELETED_BY]}


def restore(workspace_root: str) -> dict:
    """표시 삭제를 되돌린다. 데이터를 남겨 둔 이유가 이것이다."""
    p = meta_path(workspace_root)
    if not os.path.exists(p):
        return {"restored": False}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception:
        return {"restored": False}
    for k in (DELETED_AT, DELETED_BY, DELETED_REASON):
        data.pop(k, None)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)
    return {"restored": True}


def is_deleted(workspace_root: str) -> bool:
    """표시 삭제됐는가. 목록이 이것으로 거른다.

    ⚠️ meta 를 못 읽으면 **False** 다 — 「못 읽었으니 지워진 것으로 치자」로 하면 읽기 오류
      하나에 프로젝트가 목록에서 통째로 사라진다. 여기서는 «보이는 쪽» 이 안전한 실패다."""
    p = meta_path(workspace_root)
    if not os.path.exists(p):
        return False
    try:
        with open(p, "r", encoding="utf-8") as f:
            return bool((json.load(f) or {}).get(DELETED_AT))
    except Exception:
        return False
