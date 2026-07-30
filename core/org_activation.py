"""조직 권한 강제 **전환 전 점검** — 켜면 무엇이 어떻게 바뀌는지 먼저 센다.

## 왜 이 모듈이 필요한가 (2026-07-30 실측)

`ORG_ENFORCE=False` 인 동안 `resolve_scope()` 는 **전원 무제한**을 돌려준다
(`org_directory.py:498`). 즉 오늘까지 만든 조직 범위·등급 가림·경영진 드릴다운·관문 A 가
**하나도 작동하지 않는 상태**다. 그것을 켜는 것이 이 시스템 권한 모델의 실제 가동 스위치다.

그런데 켜는 순간 두 가지가 동시에 일어난다:
  · **미배정 사용자는 아무 부서도 읽지 못한다** — 부서가 없으면 읽을 것도 없다
  · **테스트로 만들어진 계정이 실제 권한을 갖는다** — 실측에서 실 DB 의 사용자 4명이 전부
    테스트 잔여물(`admin`·`bob`·`exec`·`bob2`)이었다. 그 상태로 강제를 켜면 `admin` 은
    is_admin=1 이라 **전권**을 갖는다

그래서 켜기 전에 이 점검을 통과해야 한다. 설계서 §5.3 이 관문 A 에 요구한 절차와 같은 규약이다 —
**"켜면 무엇이 사라지는가"를 먼저 세고 켠다.**

⚠️ 잠금 방지: 관리자 계정이 하나도 없으면 강제를 켜서는 안 된다. 켜는 순간 첫 관리자를 만들
  권한을 가진 사람이 아무도 없어 시스템이 잠긴다(`org_directory.is_bootstrap` 주석의 실측 사고).

LLM 0콜.
"""
from typing import Any, Dict, List

#: 테스트가 남긴 것으로 보이는 계정 패턴. **삭제하지 않는다** — 사람 계정을 코드가 지우면
#: 실제 사용자를 지울 위험이 있다. 표시만 하고 판단은 관리자에게 넘긴다.
_TEST_LOOKING = ("bob", "bob2", "exec", "test", "dummy", "tmp", "__")


def _looks_like_test(user_id: str, display_name: str = "") -> bool:
    uid = (user_id or "").strip().lower()
    if uid in ("bob", "bob2", "exec", "admin"):
        # `admin` 도 포함한다 — 실제 관리자라면 사람 이름·메일로 다시 만들면 되고, 테스트가
        #   만든 `admin` 이 전권을 갖는 상태가 훨씬 위험하다.
        return True
    return any(t in uid for t in _TEST_LOOKING)


def preflight(org=None) -> Dict[str, Any]:
    """강제를 켜면 무엇이 어떻게 되는가. **켜지는 않는다.**

    돌려주는 것:
      · `ready` — 켜도 되는가(관리자 존재 + 부서 존재)
      · `blockers` — 켜면 안 되는 이유(있으면 켜지 말아야 한다)
      · `warnings` — 켜도 되지만 사람이 알아야 하는 것(미배정·테스트 계정)
      · `users` — 사용자별로 **켠 뒤 무엇을 읽게 되는지**
    """
    if org is None:
        from core.org_directory import org_directory as org
    depts = org.list_departments()
    users = org.list_users()
    admins = [u for u in users if u.get("is_admin")]
    unassigned = [u for u in users
                  if not (u.get("primary_dept_id") or "").strip()
                  and not (u.get("dept_roles") or u.get("roles") or {})]
    test_like = [u for u in users if _looks_like_test(u.get("user_id", ""),
                                                     u.get("display_name", ""))]

    blockers: List[str] = []
    warnings: List[str] = []
    if not depts:
        blockers.append("부서가 하나도 없습니다 — 강제를 켜도 부트스트랩으로 무제한이 됩니다"
                        "(켜는 의미가 없습니다). 먼저 부서를 시드하십시오.")
    if not users:
        blockers.append("사용자가 하나도 없습니다 — 강제를 켜도 부트스트랩으로 무제한이 됩니다.")
    if users and not admins:
        blockers.append("**관리자 계정이 없습니다.** 이 상태로 켜면 첫 관리자를 만들 권한을 가진 "
                        "사람이 아무도 없어 시스템이 잠깁니다(실측 사고). 먼저 관리자를 "
                        "만드십시오.")
    if test_like:
        warnings.append(
            f"테스트로 만들어진 것으로 보이는 계정 {len(test_like)}건이 있습니다"
            f"({', '.join(u['user_id'] for u in test_like[:6])}). 강제를 켜면 이 계정들이 "
            f"**실제 권한을 갖습니다** — 특히 `admin` 은 전권입니다. 실 사용자로 교체하거나 "
            f"폐지(retire)하십시오.")
    if unassigned:
        warnings.append(
            f"부서 미배정 사용자 {len(unassigned)}건 — 켠 뒤 **아무 부서 자료도 읽지 못합니다** "
            f"({', '.join(u['user_id'] for u in unassigned[:6])}).")

    rows = []
    for u in users:
        uid = u.get("user_id", "")
        try:
            sc = org.resolve_scope(uid)
            readable = sorted(sc.readable_dept_ids) if not sc.unrestricted else ["(무제한)"]
        except Exception as e:                                   # pragma: no cover
            readable = [f"(해석 실패: {e})"]
        rows.append({
            "user_id": uid, "display_name": u.get("display_name", ""),
            "primary_dept_id": u.get("primary_dept_id", ""),
            "is_admin": bool(u.get("is_admin")), "is_executive": bool(u.get("is_executive")),
            "looks_like_test": _looks_like_test(uid, u.get("display_name", "")),
            "readable_now": readable,
        })

    from core.scope_policy import org_enforce
    return {
        "ready": not blockers,
        "currently_enforced": bool(org_enforce()) if org_enforce() is not None
        else _config_default(),
        "departments": len(depts), "users": len(users), "admins": len(admins),
        "unassigned": len(unassigned), "test_looking": len(test_like),
        "blockers": blockers, "warnings": warnings, "users_detail": rows,
        "note": ("켜도 됩니다. 다만 위 `warnings` 를 먼저 읽으십시오 — 켠 뒤에 놀라는 것과 "
                 "알고 켜는 것은 다릅니다."
                 if not blockers else
                 "**아직 켜지 마십시오.** `blockers` 를 먼저 해소해야 합니다 — 그대로 켜면 "
                 "시스템이 잠기거나 강제가 무의미해집니다."),
    }


def _config_default() -> bool:
    try:
        import config
        return bool(getattr(config, "ORG_ENFORCE", False))
    except Exception:
        return False
