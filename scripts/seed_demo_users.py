"""[DEMO] 상황별 예시 사용자 20명 등록 — `hikwon@lsmnm.com` 기준 복제.

## 왜 스크립트인가 (일회성 명령이 아니라)

폐루프(CL-1~CL-4)의 절반은 **두 사람 이상이 있어야 확인할 수 있다.** 전달은 보내는 사람과
받는 사람이 다르고, 결정은 요청자·의사결정자·영향부서가 다르고, 대외 발간은 임원과 법무가
다른 사람이다. 사용자가 하나면 그 규칙들이 **작동하는지 확인할 방법이 없다.**

★ 그래서 계정을 만들되, **누가 어떤 상황을 위해 있는지**를 코드에 남긴다. 이름만 늘리면
  두 달 뒤에 "hikwon_7 은 왜 있지?"에 아무도 답할 수 없고, 그때 이 목록은 정리 대상이 된다.

## 실제 인원과 섞이지 않게

⚠️ 표시명에 **«(예시)»**를 붙인다. 조직도·전달 화면에서 실제 인원과 나란히 보이기 때문이다.
  구분이 없으면 현업이 예시 계정에 진짜 업무를 보낸다.
⚠️ `hikwon@lsmnm.com` 원본은 **건드리지 않는다.**

## 권한 설계

- `is_admin` 은 **전권**이다. 예시 계정에 함부로 주지 않는다 — 권한 경계(404 은폐·범위 필터)를
  확인해야 하는데 전원이 관리자면 아무것도 막히지 않아 **검증이 무의미해진다.**
- 그래서 관리자는 1명(IT), 임원은 2명, 나머지는 부서 `member`/`manager` 다.

사용법:
    venv\\Scripts\\python.exe scripts/seed_demo_users.py          # 등록·갱신
    venv\\Scripts\\python.exe scripts/seed_demo_users.py --list   # 현황만 출력
"""
from __future__ import annotations

import argparse
import os
import sys

# `scripts/` 에서 바로 실행해도 `core` 를 찾도록 저장소 루트를 경로에 넣는다.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ⚠️ Windows 기본 콘솔(cp949)에서는 «—»·«★» 가 인코딩되지 않아 **출력에서 죽는다.**
#   문서에 적힌 명령이 그대로 실패하면 그 문서는 지켜지지 않는다 — 여기서 한 번 막는다.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core.org_directory import org_directory  # noqa: E402

BASE = "hikwon@lsmnm.com"
ACTOR = "seed_demo_users"

#: (번호, 표시명, 주부서, 부서역할, 임원, 관리자, 데이터관리자, 이 계정이 존재하는 상황)
#: ★ 마지막 칸이 이 파일의 핵심이다 — 상황이 없으면 계정도 없어야 한다.
USERS = [
    (1,  "정민수", "production_battery", "manager", False, False, False,
     "CL-2 요청자 — 배터리소재 생산 현장에서 시뮬레이션을 돌리고 안건을 올리는 사람"),
    (2,  "김도영", "production_battery", "member",  False, False, False,
     "CL-2 영향부서 — 같은 부서에서 실제로 업무가 바뀌는 담당자"),
    (3,  "박서준", "production_copper",  "manager", False, False, False,
     "CL-2 영향부서(타 라인) — 동제련 쪽 자원 경합을 답하는 사람"),
    (4,  "이하늘", "production",         "manager", True,  False, False,
     "CL-2 의사결정자 — 생산 총괄 임원. 결정을 기록할 권한이 있는 유일한 역할"),
    (5,  "최지우", "quality",            "manager", False, False, False,
     "CL-2 영향부서 — 품질 기준 변경 여부를 답한다"),
    (6,  "한예린", "quality",            "member",  False, False, False,
     "CL-2 «정보 부족» 응답자 — 모르는 상태의 동의를 막는 경로를 확인한다"),
    (7,  "오세훈", "procurement",        "manager", False, False, False,
     "CL-2 영향부서 — 원료 조달 리드타임 제약을 답한다"),
    (8,  "윤가람", "logistics",          "manager", False, False, False,
     "CL-2 영향부서 — 출하·재고 영향을 답한다"),
    (9,  "장미르", "finance",            "manager", False, False, False,
     "CL-3 재무 검토 — 손익·현금 영향 확인"),
    (10, "신동우", "finance",            "member",  False, False, False,
     "CL-2 실행과제 담당 — 결정 후 과제의 담당·기한을 받는 사람"),
    (11, "구본희", "accounting",         "manager", False, False, False,
     "CL-3 DATA_OWNER 검토 — 회계 원천 데이터의 소유자"),
    (12, "임재현", "hq",                 "manager", True,  False, False,
     "CL-3 EXECUTIVE 검토 — 대외 발간의 책임 임원(임원 2명을 둔 이유: 승인자와 결정자를 분리해 확인)"),
    (13, "송하린", "hq",                 "member",  False, False, False,
     "CL-3 LEGAL_DISCLOSURE 검토 — 법무·공시 검토자"),
    (14, "배준영", "hq",                 "member",  False, False, False,
     "CL-3 SECURITY 검토 — 보안 검토자"),
    (15, "노아름", "sales",              "manager", False, False, False,
     "CL-3 대외 제한 보고 독자 대리 — 고객·파트너 대상 문서의 사내 확인자"),
    (16, "문태경", "marketing",          "member",  False, False, False,
     "CL-1 앱 수신자 — 전달받아 수락하는 쪽. 수락 후에도 자료 권한이 안 늘어남을 확인한다"),
    (17, "강수빈", "marketing",          "viewer",  False, False, False,
     "CL-1 권한 경계 — 읽기만 가능한 사용자. 이 사람에게 막히는 것이 있어야 경계가 있는 것이다"),
    (18, "전민아", "t_admin",            "viewer",  False, False, False,
     "CL-1/CL-4 격리 대조군 — **어떤 안건에도 참여시키지 않는다.** 이 사람에게 무언가 보이면 유출이다"),
    (19, "황시온", "sales",              "member",  False, False, False,
     "CL-4 알림 대조군 — 참여자와 비참여자를 같은 부서 안에서 구분해 확인한다"),
    (20, "서지호", "hq",                 "manager", False, True,  True,
     "IT 관리자 — 조직·권한·감사 화면 확인용. 예시 중 **유일한 전권 계정**"),
]


def user_id(n: int) -> str:
    return f"hikwon_{n}@lsmnm.com"


def seed() -> int:
    base = org_directory.get_user(BASE)
    if not base:
        print(f"기준 사용자 {BASE} 가 없습니다. 먼저 조직을 세우십시오.", file=sys.stderr)
        return 1
    print(f"기준: {BASE} ({base['display_name']}) — 원본은 변경하지 않습니다.\n")

    depts = {d["dept_id"] for d in org_directory.list_departments()}
    made = 0
    for n, name, dept, role, execu, admin, data_admin, why in USERS:
        if dept not in depts:
            # ⚠️ 없는 부서에 배정하지 않는다. 조용히 빈 부서로 두면 권한이 «전부 안 보임»이 되고,
            #   그 계정으로 하는 모든 검증이 잘못된 결론을 낸다.
            print(f"  ✗ {user_id(n)} — 부서 '{dept}' 가 없어 건너뜁니다.")
            continue
        uid = user_id(n)
        org_directory.upsert_user(
            uid, f"{name} (예시)", primary_dept_id=dept,
            is_executive=execu, is_admin=admin, is_data_admin=data_admin, actor=ACTOR)
        org_directory.set_user_roles(uid, {dept: role}, actor=ACTOR)
        flags = "".join(c for c, v in (("임", execu), ("관", admin), ("데", data_admin)) if v)
        print(f"  ✓ {uid:26s} {name} (예시)  {dept}/{role} {flags:3s} — {why}")
        made += 1

    print(f"\n등록·갱신 {made}명. 실제 인원과 구분되도록 표시명에 «(예시)»가 붙어 있습니다.")
    return 0


def show() -> int:
    users = org_directory.list_users()
    print(f"등록된 사용자 {len(users)}명")
    for u in users:
        flags = "".join(c for c, k in (("임", "is_executive"), ("관", "is_admin"),
                                       ("데", "is_data_admin")) if u.get(k))
        print(f"  {u['user_id']:26s} {u['display_name']:14s} "
              f"{u.get('primary_dept_id') or '(미배정)':20s} {u.get('roles')} {flags}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="상황별 예시 사용자 20명 등록")
    ap.add_argument("--list", action="store_true", help="현황만 출력하고 아무것도 바꾸지 않는다")
    a = ap.parse_args()
    return show() if a.list else seed()


if __name__ == "__main__":
    sys.exit(main())
