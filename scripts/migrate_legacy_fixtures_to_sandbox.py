"""[G1-C1.1] 과거 시험 산출물을 **검증 샌드박스 범위**로 일괄 귀속시킨다.

## 왜 실제 부서로 배정하지 않는가

교차검증 실측: 61개 프로젝트 중 소유권 바인딩 **7** · 미바인딩 **53** · 메타 없음 **1**.
그런데 그 54개에는 `owner_user_id` 도, `latest_state.json` 의 소유 필드도 **없다**(확인 0건).
즉 소유를 유도할 근거가 어디에도 없다.

근거 없이 `hq` · `MNM_SHARED` · 구매·생산·품질 같은 **실제 조직에 배정하면** 시험 산출물이
조직 자산·경영 데이터처럼 검색되고 집계된다. 그 수치를 보고 사람이 경영 판단을 한다.
`visibility="company"` 도 같은 이유로 안 된다.

그래서 전용 가상 범위를 신설해 거기로 묶는다.

    tenant_id       tenant_default
    scope_code      AFS_TEST_SANDBOX
    entity_mode     VIRTUAL
    node_type       validation_sandbox

## ⚠️ `enterprise_scope_id` 만 채우면 실제로 막히지 않는다

현재 가시성 판정은 아직 `enterprise_scope_id` 를 보지 않는다. 그래서 `owner_user_id` 와
`visibility="private"` 까지 함께 적어야 **비관리자에게 실제로 차단된다.**
`owner_user_id` 는 실제 작성자를 뜻하지 않는다 — 소유를 유도할 수 없는 과거 산출물의
**임시 관리 책임자**이며, `ownership_basis="LEGACY_TEST_MIGRATION"` 이 그 사실을 남긴다.

## 사용

    venv/Scripts/python.exe scripts/migrate_legacy_fixtures_to_sandbox.py            # 실행 계획만
    venv/Scripts/python.exe scripts/migrate_legacy_fixtures_to_sandbox.py --apply    # 적용

⚠️ `--apply` 는 **적용 전 상태를 통째로 백업**한다(`docs/migration/`). 되돌릴 수 없는 일을
  되돌릴 수 있게 만들어 두지 않으면, 잘못 눌렀을 때 남는 것은 사과뿐이다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
#: 저장소 루트를 경로에 넣는다 — `scripts/` 에서 직접 실행해도 `core` 를 찾게 한다.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.project_visibility import (BOUND, COMPANY_PUBLIC, INVALID, LEGACY_UNBOUND,
                                     SANDBOX_ENTITY_MODE, SANDBOX_NODE_TYPE,
                                     SANDBOX_CUSTODIAN, SANDBOX_SCOPE_CODE,
                                     is_sandbox, project_meta_path, read_project_ownership)

#: 임시 관리 책임자. 정의는 `core/project_visibility` 에 있다 — 프로젝트 생성 경로도 같은
#: 값을 써야 하므로 두 곳에 적지 않는다.
CUSTODIAN = SANDBOX_CUSTODIAN

#: 검증 샌드박스로 묶을 이름 규칙. Mega 부모와 모든 하위 프로젝트를 포함한다.
FIXTURE_PATTERNS = (
    re.compile(r"^test_"),
    re.compile(r"^MEGA_0"),
    re.compile(r"^scenario-"),
    re.compile(r".*_canary.*"),
    re.compile(r"^__"),
)


def is_fixture(name: str) -> bool:
    return any(p.match(name) for p in FIXTURE_PATTERNS)


def ensure_sandbox_node() -> str:
    """검증 샌드박스 조직 노드를 만들고 **실제 node_id** 를 돌려준다. 여러 번 불러도 안전하다."""
    from core.enterprise_context.models import STATUS_ACTIVE, EnterpriseEntity, OrganizationNode
    from core.enterprise_context.repository import ecm_repository as repo

    found = repo.find_node_by_code(SANDBOX_SCOPE_CODE, tenant_id="tenant_default")
    if found:
        return found.node_id

    ent = repo.upsert_entity(EnterpriseEntity(
        tenant_id="tenant_default",
        entity_type=SANDBOX_NODE_TYPE,
        entity_mode=SANDBOX_ENTITY_MODE,
        legal_name="AI Factory Studio 검증 샌드박스",
        name_ko="AI Factory Studio 검증 샌드박스",
        status=STATUS_ACTIVE,
        source_ref="G1-C1.1 legacy fixture migration",
    ))
    node = repo.upsert_node(OrganizationNode(
        entity_id=ent.entity_id,
        tenant_id="tenant_default",
        node_type=SANDBOX_NODE_TYPE,
        code=SANDBOX_SCOPE_CODE,
        name_ko="AI Factory Studio 검증 샌드박스",
        #: ⚠️ `dept_id` 를 비운다. 실제 부서와 이으면 그 부서 권한이 이 노드에 적용되고,
        #:   그 순간 시험 산출물이 실제 조직 자산이 된다 — 이 마이그레이션의 목적과 반대다.
        dept_id="",
        status=STATUS_ACTIVE,
    ))
    return node.node_id


def plan(root: str = "projects"):
    """무엇을 바꿀지 먼저 센다. 세지 않고 쓰면 결과를 확인할 기준이 없다."""
    targets, uprooted = [], []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        own = read_project_ownership(path)
        state = own.get("binding_state")
        if state in (LEGACY_UNBOUND, INVALID):
            targets.append((name, state, own.get("binding_reason", "")))
        elif is_fixture(name) and not is_sandbox(own):
            # ⚠️ 이미 샌드박스에 있는 것은 대상이 아니다. 이 조건을 빼면 **다시 돌릴 때마다
            #   같은 59개가 «남아 있다» 고 보고**되어, 적용이 됐는지 안 됐는지 알 수 없다
            #   (실제로 첫 실행 후 「남은 59개」라는 무의미한 숫자가 나왔다).
            # ★★ 이름이 시험 산출물인데 **실제 부서에 들어가 있다.** 이것이야말로 옮겨야 할
            #   상태다 — 시험 산출물이 조직 자산·경영 데이터처럼 검색되고 집계되는 바로 그
            #   경우다(MEGA_02_quality → 품질, scenario-01 → 본사).
            #   ⚠️ 처음에는 「이미 묶여 있으니 사람이 판단할 일」로 건너뛰게 짜 놓았다. 그러면
            #     **문제가 제일 심한 것만 남는다** — 미바인딩보다 잘못 바인딩된 쪽이 더 나쁘다.
            dept = own.get("owner_dept_id", "") or "(부서없음)"
            targets.append((name, state, f"실제 부서 {dept} 에서 이동"))
            uprooted.append((name, state, dept))
    return targets, uprooted


def apply(targets, node_id: str, root: str = "projects") -> str:
    """메타를 고치고, **고치기 전 상태를 통째로 남긴다.**"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join("docs", "migration")
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, f"g1c11_fixture_migration_{stamp}.json")

    before = {}
    for name, _state, _why in targets:
        p = project_meta_path(os.path.join(root, name))
        try:
            before[name] = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
        except Exception as e:
            before[name] = {"__unreadable__": str(e)}
    json.dump({"applied_at": stamp, "sandbox_node_id": node_id, "before": before},
              open(backup_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    patch = {
        "tenant_id": "tenant_default",
        "enterprise_scope_id": node_id,
        "entity_mode": SANDBOX_ENTITY_MODE,
        "owner_user_id": CUSTODIAN,
        #: ⚠️ 부서는 **비운다.** 실제 부서에 넣지 않는 것이 이 작업의 요점이다.
        "owner_dept_id": "",
        "visibility": "private",
        "nature": "test_fixture",
        "ownership_basis": "LEGACY_TEST_MIGRATION",
        "data_origin": "SYNTHETIC",
    }
    for name, _state, _why in targets:
        d = before.get(name)
        if not isinstance(d, dict) or "__unreadable__" in d:
            d = {}                      # 메타 없음·손상 → 새로 만든다(같은 범위로 복구)
        d.update(patch)
        with open(project_meta_path(os.path.join(root, name)), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    return backup_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 쓴다(기본은 계획만)")
    ap.add_argument("--root", default="projects")
    args = ap.parse_args()

    targets, uprooted = plan(args.root)
    print(f"■ 검증 샌드박스로 귀속시킬 대상: {len(targets)}개")
    for name, state, why in targets[:8]:
        print(f"    {name:32s} {state}{('  ' + why) if why else ''}")
    if len(targets) > 8:
        print(f"    … 외 {len(targets) - 8}개")
    if uprooted:
        print(f"\n★ 이 중 {len(uprooted)}개는 **실제 부서에서 빼내어** 샌드박스로 옮깁니다 —"
              f" 시험 산출물이 조직 자산처럼 집계되던 것을 끊는 것입니다.")
        for name, state, dept in uprooted:
            print(f"    {name:32s} {state} dept={dept} → {SANDBOX_SCOPE_CODE}")

    if not args.apply:
        print("\n계획만 출력했습니다. 실제로 적용하려면 --apply 를 붙이십시오.")
        return 0

    node_id = ensure_sandbox_node()
    print(f"\n검증 샌드박스 노드: {SANDBOX_SCOPE_CODE} → {node_id}")
    backup = apply(targets, node_id, args.root)
    print(f"적용 전 상태 백업: {backup}")

    after, _ = plan(args.root)
    print(f"\n적용 후 남은 미바인딩·판독불가: {len(after)}개")
    return 0 if not after else 1


if __name__ == "__main__":
    raise SystemExit(main())
