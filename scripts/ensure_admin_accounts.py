"""[ORG] 플랫폼 관리자 계정을 확실히 살려 둔다.

## 왜 스크립트인가

2026-08-04 실측에서 플랫폼 `admin` 계정이 **폐지 상태**였다. 행은 남아 있었지만 `status='retired'`
라서 사용자 목록·전환기·권한 어디에도 나타나지 않았다. 그리고 조직 변경 감사는 2026-07-30 부터
기록되기 시작해서 **누가 언제 왜 폐지했는지 기록이 없었다.**

★ 관리자 계정이 없는 상태는 조용히 지나간다. 평소에는 아무 문제가 없다가, 권한을 고쳐야 하는
  순간에 «고칠 수 있는 사람이 없다»는 것을 알게 된다. 그래서 **확인을 사람 기억에 맡기지 않고**
  다시 실행할 수 있는 스크립트로 둔다.

⚠️ 이 스크립트는 **권한을 부여**한다. 조용히 돌리지 않는다 — 무엇을 바꿨는지(또는 이미 그랬는지)
  전부 출력하고, 감사로그에도 «권한 복구»로 남는다.

사용법:
    venv\\Scripts\\python.exe scripts/ensure_admin_accounts.py          # 확인만
    venv\\Scripts\\python.exe scripts/ensure_admin_accounts.py --apply  # 실제 적용
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.org_directory import org_directory  # noqa: E402

ACTOR = "ensure_admin_accounts"

#: 플랫폼 관리자 계정. `admin` 은 2026-07-27 부터 있던 원래 계정이다 — 새 id 를 만들지 않고
#: 그것을 되살린다. 새로 만들면 옛 감사 기록의 `admin` 과 지금의 관리자가 다른 사람이 된다.
PLATFORM_ADMIN = "admin"
PLATFORM_ADMIN_NAME = "플랫폼 관리자"
PLATFORM_ADMIN_DEPT = "hq"

#: 이 계정들은 `is_admin` 을 **가지고 있어야 한다.**
MUST_BE_ADMIN = ["hikwon@lsmnm.com", PLATFORM_ADMIN]

#: [D-017 §4.2] AI 거버넌스 관리자(`is_ai_admin`). Supervisor 지시(2026-08-04)로 넉넉히 둔다.
#:
#: ★ 이 권한이 하는 일: 에이전트·워크플로우 승인/폐기, **스킬 승인**, **모델 티어·비용 한도·
#:   공급자 정책 변경**. 데이터 표준 승인(`is_data_admin`)과는 **책임이 다르다** — 묶으면
#:   "이 사람이 왜 모델 정책을 바꿀 수 있었나" 에 답할 수 없다.
#:
#: ⚠️⚠️ **전원에게 주지 않는다.** viewer·격리 대조군까지 AI 관리자가 되면 권한 경계를 확인할
#:   대상이 사라지고, 그때부터 «막힌다» 는 것을 아무도 증명할 수 없다. 아래 목록에서 빠진
#:   계정들이 곧 **경계가 살아 있다는 증거**다(특히 `hikwon_17` viewer, `hikwon_18` 대조군).
AI_ADMINS = [
    ("hikwon@lsmnm.com", "Supervisor 본인 — 정책 결정자"),
    (PLATFORM_ADMIN,     "플랫폼 관리자 — 전권 계정"),
    ("hikwon_20@lsmnm.com", "IT 관리자 — 운영 담당"),
    ("hikwon_4@lsmnm.com",  "생산 총괄 임원 — 현장 에이전트 승인 결정권자"),
    ("hikwon_12@lsmnm.com", "대외 발간 책임 임원 — 대외 산출물 정책"),
    ("hikwon_1@lsmnm.com",  "배터리소재 생산 부서장 — 현장 에이전트 요청·검토"),
    ("hikwon_9@lsmnm.com",  "재무 부서장 — 모델 비용 한도 정책"),
    ("hikwon_14@lsmnm.com", "보안 검토자 — 도구 호출·외부 연계 정책"),
    ("hikwon_5@lsmnm.com",  "품질 부서장 — 산출물 품질 게이트"),
    ("hikwon_3@lsmnm.com",  "동제련 생산 부서장 — 타 라인 대표"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="플랫폼·AI 관리자 계정 확인·복구")
    ap.add_argument("--apply", action="store_true",
                    help="실제로 적용한다. 없으면 무엇을 바꿀지 출력만 한다.")
    a = ap.parse_args()
    dry = not a.apply
    print(f"[{'확인만' if dry else '적용'}] 관리자 계정 점검\n")

    changed = 0
    for uid in MUST_BE_ADMIN:
        u = org_directory.get_user(uid)
        if not u:
            if uid != PLATFORM_ADMIN:
                # ⚠️ 없는 실계정을 여기서 만들지 않는다. 사람 계정은 조직이 등록하는 것이다.
                print(f"  ✗ {uid} — 계정이 없습니다. 조직에서 먼저 등록해야 합니다.")
                continue
            print(f"  · {uid} — 계정이 없어 새로 만듭니다({PLATFORM_ADMIN_NAME}).")
            if not dry:
                org_directory.upsert_user(uid, PLATFORM_ADMIN_NAME,
                                          primary_dept_id=PLATFORM_ADMIN_DEPT,
                                          is_admin=True, is_data_admin=True, actor=ACTOR)
                org_directory.set_user_roles(uid, {PLATFORM_ADMIN_DEPT: "manager"}, actor=ACTOR)
            changed += 1
            continue

        todo = []
        if u.get("status") != "active":
            todo.append(f"폐지 상태({u.get('status')}) → 활성")
        if not u.get("is_admin"):
            todo.append("is_admin 부여")
        if uid == PLATFORM_ADMIN and not u.get("primary_dept_id"):
            todo.append(f"소속 부서 없음 → {PLATFORM_ADMIN_DEPT}")

        if not todo:
            # ★ «이미 그렇다»를 «내가 했다»로 말하지 않는다. 바꾼 것이 없으면 없다고 쓴다.
            print(f"  ✓ {uid} — 이미 활성 관리자입니다(변경 없음).")
            continue

        print(f"  · {uid} — {' · '.join(todo)}")
        changed += 1
        if dry:
            continue

        if u.get("status") != "active":
            org_directory.restore_user(uid, actor=ACTOR)
        org_directory.upsert_user(
            uid,
            u.get("display_name") or (PLATFORM_ADMIN_NAME if uid == PLATFORM_ADMIN else uid),
            primary_dept_id=(u.get("primary_dept_id")
                             or (PLATFORM_ADMIN_DEPT if uid == PLATFORM_ADMIN else "")),
            is_executive=bool(u.get("is_executive")),
            is_admin=True,
            is_data_admin=bool(u.get("is_data_admin")) or uid == PLATFORM_ADMIN,
            actor=ACTOR)
        if uid == PLATFORM_ADMIN and not u.get("roles"):
            org_directory.set_user_roles(uid, {PLATFORM_ADMIN_DEPT: "manager"}, actor=ACTOR)

    # ── [D-017 §4.2] AI 거버넌스 관리자 ────────────────────────────────────
    print("\nAI 거버넌스 관리자(is_ai_admin):")
    for uid, why in AI_ADMINS:
        u = org_directory.get_user(uid)
        if not u:
            print(f"  ✗ {uid} — 계정이 없습니다(건너뜀).")
            continue
        if u.get("is_ai_admin"):
            print(f"  ✓ {uid:26s} 이미 부여됨 — {why}")
            continue
        print(f"  · {uid:26s} 부여 — {why}")
        changed += 1
        if dry:
            continue
        org_directory.upsert_user(
            uid, u.get("display_name") or uid,
            primary_dept_id=u.get("primary_dept_id") or "",
            is_executive=bool(u.get("is_executive")),
            is_admin=bool(u.get("is_admin")),
            is_data_admin=bool(u.get("is_data_admin")),
            is_ai_admin=True, actor=ACTOR)
        # ⚠️ `upsert_user` 는 역할을 건드리지 않는다. 그대로 두는 것이 맞다 —
        #   AI 권한 부여가 부서 역할을 조용히 바꾸면 안 된다.

    # ★ 경계가 살아 있는지 함께 보여 준다. 전원이 관리자면 «막힌다» 를 증명할 대상이 없다.
    non_admin = [u for u in org_directory.list_users()
                 if not u.get("is_ai_admin") and not u.get("is_admin")]
    print(f"\nAI 권한 없는 계정 {len(non_admin)}명 — 이들이 «경계가 살아 있다» 는 증거다.")
    for u in non_admin[:6]:
        print(f"  {u['user_id']:26s} {u['display_name']}")
    if len(non_admin) > 6:
        print(f"  … 외 {len(non_admin) - 6}명")

    print()
    if changed == 0:
        print("바꿀 것이 없습니다 — 관리자 계정은 이미 정상입니다.")
    elif dry:
        print(f"{changed}건을 바꿔야 합니다. 실제로 적용하려면 --apply 를 붙이십시오.")
    else:
        print(f"{changed}건 적용했습니다. 감사로그에 «권한 복구»로 남았습니다.")

    print("\n현재 활성 관리자:")
    for u in org_directory.list_users():
        if u.get("is_admin") or u.get("is_ai_admin"):
            flags = "".join(c for c, k in (("전권", "is_admin"), ("AI", "is_ai_admin"),
                                           ("데이터", "is_data_admin")) if u.get(k))
            print(f"  {u['user_id']:26s} {u['display_name']:16s} "
                  f"{u.get('primary_dept_id') or '(미배정)':10s} {flags}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
