# -*- coding: utf-8 -*-
"""★★★ 이 저장소의 **단일 사전검증 정본(`data/`)에 시작 자료를 심는다.**

## 왜 필요한가 (2026-08-23 사용자 지적)

「샘플 데이터 넣어놓기로 하지 않았나? 업무키트도 미리 넣어놓기로 했던걸로 아는데?」

심어 놓은 것은 맞는데 **시연 뿌리(`demo_data/`)에만** 있었다. 그 뿌리는
`scripts/run_local_demo.py` 로 띄울 때만 열렸었다. 평소대로 `run.py`(8080)로 띄우면
사전검증 정본 `data/` 를 보는데 당시에는:

    업무 키트 등록본 1(낡음) · 인스턴스 0 · 원천 결속 0 · 인증판 0 · 기준선 0

즉 **앱을 열면 아무것도 없었다.**

## ⚠️ 합성 데이터를 실적으로 오인하지 않게 하는 규칙과의 관계

`scripts/pilot_demo_seed.py` 머리말이 못박은 규칙은 「표시 없는 합성 자료를 실적으로
오인하게 만들지 않는다」는 뜻이다. 현장 적용 전에는 정본을 둘로 나누지 않고, 데이터
자체의 `DEMO/SYNTHETIC`·`DEMO_CERTIFIED` 상태로 구분한다.

★ 그 규칙이 막으려던 것은 **표시 없는 합성 데이터**다. 실제로 그 스크립트는
  `MODE = "REAL"` 로 심는다 — 그러면 화면이 실적과 구분할 방법이 없다.

이 스크립트가 심는 것은 다르다. 제품에 **표시 체계가 이미 있고** 화면이 그것을 읽는다:

    키트   `mode = DEMO/SYNTHETIC`
    판     `state = DEMO_CERTIFIED` → 화면 문구 「시연용 합성 데이터(DEMO/SYNTHETIC) ·
           시연 인증됨 — **실적 인증이 아닙니다**」

⚠️ 그래도 **실제 자료가 이미 있는 설치에는 심지 않는다.** 아래 `_looks_real()` 가 그것을
  판정하고, 하나라도 걸리면 아무것도 하지 않고 멈춘다. 「덮어쓰지 않는다」를 사람의
  주의력이 아니라 코드로 지킨다.

## 파종 코드를 **두 벌로 만들지 않는다**

`run_local_demo.py` 의 `seed()`·`_top_up()`·`_seed_ontology()` 를 그대로 부른다. 두 벌이
되면 「시연에서는 되는데 실제로 띄우면 안 된다」가 다시 생긴다 — 이 저장소가 오버레이
목록에서 방금 겪은 유형이다. 다른 것은 **뿌리 하나**뿐이다.

사용:
    venv/Scripts/python.exe scripts/seed_starter_data.py            # 심는다
    venv/Scripts/python.exe scripts/seed_starter_data.py --check    # 무엇이 있는지만 본다
    venv/Scripts/python.exe scripts/seed_starter_data.py --force    # 실제 자료 판정을 무시

LLM 호출: 0건.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scripts.run_local_demo as demo  # noqa: E402

PREPROD_ROOT = os.path.join(ROOT, "data")


def _org_db() -> str:
    """앱이 **실제로 읽는** 조직 저장소 경로. 짐작하지 않고 싱글턴에게 묻는다."""
    from core.org_directory import org_directory
    return org_directory.db_path


def _count(db: str, table: str) -> int:
    """⚠️⚠️ [2026-08-24 실측] **경로를 짐작하지 않는다.**

    1차 판에서 조직을 `data/org.db` 로 세고 「부서 0 · 사용자 0」이라고 보고했다. 그런데
    앱이 실제로 읽는 조직 저장소는 **`data/master/master.db`** 다(`OrgDirectory` 의 기본값이
    `core.master_data._DB_PATH`). 거기에는 이미 **부서 13개 · 사용자 25명**이 있었다.

    ★ 그 「0」은 «없다» 가 아니라 «엉뚱한 파일을 봤다» 였다. 그리고 그 0을 근거로 조직을
      다시 심어, 아무도 읽지 않는 `data/org.db` 를 만들었다.
    ⚠️ 파일명을 손으로 적지 말고 **싱글턴이 쓰는 경로**를 물어본다."""
    p = db if os.path.isabs(db) else os.path.join(PREPROD_ROOT, db)
    if not os.path.exists(p):
        return 0
    try:
        c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        try:
            return int(c.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        finally:
            c.close()
    except sqlite3.Error:
        return 0


def inventory() -> dict:
    return {
        "업무 키트 등록본": _count("data_preparation.db", "kit_registry_versions"),
        "키트 인스턴스": _count("data_preparation.db", "kit_instances"),
        "원천 결속": _count("data_preparation.db", "source_bindings"),
        "데이터 판": _count("data_preparation.db", "dataset_snapshots"),
        "기준선": _count("data_preparation.db", "baseline_builds"),
        #: ⚠️ `departments` 는 **판(version) 표**다 — 폐지판까지 세면 13개 조직이 29로 보인다.
        #:   싱글턴에게 물어 **현재 유효한 것만** 센다.
        "부서(유효)": _org_active(),
        "사용자": _count(_org_db(), "users"),
    }


def _org_active() -> int:
    try:
        from core.org_directory import org_directory
        return len(org_directory.list_departments())
    except Exception:
        return 0


def _looks_real() -> list[str]:
    """**실제 자료로 보이는 것**을 찾는다. 하나라도 있으면 심지 않는다.

    ⚠️ 「비어 있는가」가 아니라 「실제인가」를 묻는다. 시연 표시가 붙은 자료 위에 다시
      심는 것은 안전하지만(멱등), 실적 위에 심으면 되돌릴 수 없다.
    ★ 판정 근거는 **제품의 표시 체계**다 — 우리가 새 규칙을 만들지 않는다:
        · 키트가 `DEMO/SYNTHETIC` 이 아니면 실제
        · 판이 `DEMO_CERTIFIED` 가 아닌 상태로 인증돼 있으면 실제
    """
    hits: list[str] = []
    p = os.path.join(PREPROD_ROOT, "data_preparation.db")
    if not os.path.exists(p):
        return hits
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        try:
            n = c.execute("SELECT count(*) FROM kit_registry_versions "
                          "WHERE mode IS NOT NULL AND mode <> 'DEMO/SYNTHETIC'").fetchone()[0]
            if n:
                hits.append(f"시연 표시가 없는 업무 키트 {n}개")
        except sqlite3.Error:
            pass
        try:
            n = c.execute("SELECT count(*) FROM dataset_snapshots "
                          "WHERE state = 'CERTIFIED'").fetchone()[0]
            if n:
                hits.append(f"실적 인증판(CERTIFIED) {n}개")
        except sqlite3.Error:
            pass
    finally:
        c.close()
    return hits


def _write_instance_tenant() -> str:
    """자료의 테넌트를 **설치본 설정**으로 기록한다(`data/instance.json`).

    ⚠️ 이미 다른 값이 있으면 덮지 않는다 — 실제 테넌트를 정해 둔 설치본을 시연 값으로
      바꾸면 그 설치본의 자료가 통째로 안 보이게 된다."""
    import json

    from core import demo_vertical_slice as dv

    #: ★ 반드시 `demo._slice()` — 날짜를 옮기지 않은 조각으로 심으면 계산이 막힌다.
    sl = demo._slice()
    tenant, _scope = dv.scope_of(sl)
    path = os.path.join(PREPROD_ROOT, "instance.json")
    cur = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                cur = json.load(fh) or {}
        except Exception:
            cur = {}
    have = str(cur.get("tenant_id", "") or "").strip()
    if have and have != tenant:
        print()
        print(f"⚠️ 설치본 테넌트가 «{have}» 로 기록돼 있습니다 — 덮지 않습니다.")
        print(f"   정본 자료는 «{tenant}» 소속이라 화면에 안 보일 수 있습니다.")
        return have
    if have != tenant:
        os.makedirs(PREPROD_ROOT, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({**cur, "tenant_id": tenant}, fh, ensure_ascii=False, indent=2)
    print()
    print(f"설치본 테넌트: {tenant}  ({path})")
    print("   ★ `run.py` 가 이 값을 읽습니다 — `config.py` 가 아니라 여기서 읽는 이유는")
    print("     시험이 개발자의 data/ 에 의존하지 않게 하기 위해서입니다.")
    #: 이번 프로세스에도 반영 — 파종이 그 값으로 조회한다.
    import config as cfg
    cfg.ECM_DEFAULT_TENANT_ID = tenant
    return tenant


def _top_up_ownership() -> None:
    """소유권 결속이 **하나도 없으면** 심는다.

    ⚠️ 이것이 없으면 제품 해석기가 모든 업무 객체를 `UNBOUND` 로 답하고, 경로 계산이
      한 줄도 성립하지 않는다(2026-08-24 실측). 시연은 스텁 해석기 덕에 초록이었다."""
    import sqlite3

    from core import demo_vertical_slice as dv

    dbp = os.path.join(PREPROD_ROOT, "data_preparation.db")
    have = 0
    try:
        c = sqlite3.connect(f"file:{dbp}?mode=ro", uri=True)
        try:
            have = int(c.execute(
                "SELECT count(*) FROM dataset_ownership_bindings").fetchone()[0])
        finally:
            c.close()
    except sqlite3.Error:
        have = 0
    if have:
        print(f"  소유권 결속 {have}건 — 그대로 둡니다.")
        return

    #: ★ 반드시 `demo._slice()` — 날짜를 옮기지 않은 조각으로 심으면 계산이 막힌다.
    sl = demo._slice()
    csv_tenant, scope = dv.scope_of(sl)
    tenant = demo.TENANT_OVERRIDE or csv_tenant
    #: ★ 계산 경로가 쓰는 계약키만 심는다 — 전부 심으면 시간이 늘고, 안 쓰는 결속은
    #:   나중에 「누가 왜 정했나」를 물었을 때 답할 근거가 없다.
    made = demo.seed_ownership(tenant, scope, dv.SLICE_KEYS)
    print(f"  소유권 결속 {made}건 심음 (계약키 {len(dv.SLICE_KEYS)}종)")
    #: ★ 결속을 만든 **뒤에는 색인을 다시 세워야 한다** — 색인은 인증 시점의 소유권을
    #:   봉인하므로, 결속이 없던 때에 만들어진 줄은 해석기가 거부한다.
    n = demo.rematerialize_index(tenant, scope)
    print(f"  색인 재물질화 {n}판")


def _top_up_ontology() -> None:
    """관계가 **하나도 없으면** 심는다.

    ⚠️ `_top_up()` 은 데이터 판만 보충하고 온톨로지는 건드리지 않는다. 인스턴스가 이미
      있는데 관계가 비어 있으면 「경로 찾기」가 조용히 0건을 돌려준다 — 그 0은 「관계가
      없다」가 아니라 「아직 안 심었다」인데 화면은 구분하지 못한다.
    ★ 이미 있으면 **다시 심지 않는다.** 같은 관계를 두 번 심으면 기간이 겹쳐 죽는다
      (`run_local_demo` 가 실측으로 배운 것)."""
    import sqlite3

    from core import demo_vertical_slice as dv
    from core.decision_ledger import decision_ledger

    onto_db = os.path.join(PREPROD_ROOT, "ontology.db")
    have = 0
    if os.path.exists(onto_db):
        try:
            c = sqlite3.connect(f"file:{onto_db}?mode=ro", uri=True)
            try:
                have = int(c.execute("SELECT count(*) FROM semantic_relations").fetchone()[0])
            finally:
                c.close()
        except sqlite3.Error:
            have = 0
    if have:
        print(f"  온톨로지 관계 {have}건 — 그대로 둡니다.")
        return

    #: ★ 반드시 `demo._slice()` — 날짜를 옮기지 않은 조각으로 심으면 계산이 막힌다.
    sl = demo._slice()
    _csv_tenant, scope = dv.scope_of(sl)
    tenant = demo.TENANT_OVERRIDE or _csv_tenant
    demo._seed_ontology(tenant, scope, decision_ledger)


def _ensure_scope_home() -> None:
    """심는 자료의 **조직 범위가 조직도에 존재하게** 한다.

    ## ⚠️⚠️ 왜 필요한가 (2026-08-24 실측)

    정본 스타터 키트의 자료는 `scope_node_id = plant-afs-smelting-01` 소속이다. 그런데
    이 설치본의 실제 조직이 쓰는 범위 노드는 `node_41402723bc90`·`node_36c1c7c797e0`·
    `node_a56a75e63b10` 였다 — **하나도 겹치지 않는다.**

        무제한 권한자(관리자)  → 보인다
        나머지 24명            → **아무것도 안 보인다**

    범위가 조직도에 없으면 그 자료는 «누구의 것도 아닌» 상태가 된다. 화면은 오류 없이
    그냥 비고, 사용자는 「아직 안 심었다」로 읽는다.

    ## 무엇을 하고, 무엇을 하지 않는가

    · **한다**: 그 범위를 가진 부서를 하나 **더한다**(본사 아래, 이름에 «시연» 을 박는다)
    · **하지 않는다**: 기존 부서의 범위를 바꾸지 않는다 — 그것은 그 부서 사람들이 보는
      자료를 통째로 바꾸는 일이다
    · **하지 않는다**: 사람을 옮기지 않는다 — 누가 이 자료를 볼지는 **사람이 정할 일**이다.
      부서만 만들어 두고 배치는 「조직·권한」 화면에서 하게 둔다.
    """
    from core.org_directory import org_directory

    from core import demo_vertical_slice as dv

    #: ★ 반드시 `demo._slice()` — 날짜를 옮기지 않은 조각으로 심으면 계산이 막힌다.
    sl = demo._slice()
    _tenant, scope = dv.scope_of(sl)

    have = {str(d.get("scope_node_id") or "").strip()
            for d in org_directory.list_departments()}
    if scope in have:
        return

    #: ★ **최상위로 두지 않는다.** 최상위 부서는 «별도 회사» 처럼 취급돼 범위 판정이
    #:   넓어진다(실측: 뿌리로 만들었더니 다른 뿌리 범위를 가진 사용자에게도 읽혔다).
    #:   시연 공장은 이 회사의 **하위 조직**이므로 최상위 부서 아래에 붙인다.
    roots = [d for d in org_directory.list_departments()
             if not str(d.get("parent_id") or "").strip()
             and str(d.get("dept_id") or "") != "demo_smelting"]
    parent = roots[0]["dept_id"] if roots else ""

    dept_id = "demo_smelting"
    try:
        org_directory.create_department(
            dept_id, "제련공장 (시연 자료)", parent_id=parent,
            scope_node_id=scope, actor="seed_starter_data")
        print(f"\n조직도에 «제련공장 (시연 자료)» 를 더했습니다 — 범위 {scope}")
        print("   ⚠️ 사람은 옮기지 않았습니다. 누가 이 자료를 볼지는 «조직·권한» 화면에서")
        print("     정하십시오 — 그 배치는 사람이 내릴 결정입니다.")
    except Exception as e:  # noqa: BLE001
        print(f"\n⚠️ 부서를 더하지 못했습니다: {e}")
        print(f"   그러면 범위 {scope} 의 자료는 **무제한 권한자에게만** 보입니다.")


def _show(title: str, inv: dict) -> None:
    print(f"\n{title}")
    for k, v in inv.items():
        print(f"   {k:16} {v}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="무엇이 있는지만 보고 끝낸다")
    ap.add_argument("--force", action="store_true",
                    help="실제 자료 판정을 무시하고 심는다(권하지 않는다)")
    args = ap.parse_args()

    print(f"사전검증 정본: {PREPROD_ROOT}")
    before = inventory()
    _show("지금 있는 것", before)

    real = _looks_real()
    if real:
        print("\n⚠️ 실제 자료로 보이는 것이 있습니다:")
        for r in real:
            print(f"   · {r}")
        if not args.force:
            print("\n심지 않고 멈춥니다. 이 위에 시연 자료를 얹으면 되돌리기 어렵습니다.")
            print("정말 심으려면 --force. 그 전에 백업을 두십시오.")
            return 1
        print("\n--force 가 주어져 계속합니다.")

    if args.check:
        return 0

    #: ★★★ **뿌리만 바꾸고 파종 코드는 그대로 쓴다.**
    #: ⚠️ 과거 격리용 봉인(`_seal_operational_data`)은 부르지 않는다 — 단일 정본에
    #:   의도적으로 보충하는 이 경로에서는 자기 자신을 막는다.
    demo.TARGET_ROOT = PREPROD_ROOT
    demo._point_stores_at_demo()

    #: ★★★ [2026-08-24] **자료를 설치본 설정에 맞춘다** — 반대로 하지 않는다.
    #:
    #: ⚠️ 1차 시도는 설치본 설정을 자료에 맞췄다(`data/instance.json` 에 테넌트를 적고
    #:   `config` 가 그것을 import 시점에 읽게). 그 결과 **시험 100건이 깨졌다** —
    #:   시험이 개발자의 `data/` 에 의존하게 되고, 그 파일이 있는 기계에서만 빨강이 된다.
    #:   런타임 설정을 저장소 파일로 만들면 «내 기계에서만 되는/안 되는» 상태가 생긴다.
    #: ★ 조회 필터는 `kit_instances.tenant_id` **열**을 본다(정본 CSV 의 행 내용이 아니다).
    #:   그래서 열만 설치본 값으로 심으면 정본 파일을 건드리지 않고도 화면에 보인다.
    #: ★★★ [2026-08-24 실측] **자료의 테넌트를 그대로 쓴다.** 바꿔치기하지 않는다.
    #:
    #: ⚠️ 1차 시도는 자료를 설치본 설정(`tenant_default`)으로 심었다. 그런데 정본 CSV 는
    #:   **행마다** `tenant_id` 를 담고 있고, 색인(`scope_index.plan`)이 그 행 내용과
    #:   인증판의 테넌트를 **대조해 거부한다**:
    #:
    #:       「PRC-02 2행: tenant 가 인증판과 다릅니다
    #:        (tenant-afs-demo-materials ≠ tenant_default)」
    #:
    #:   그 대조는 **옳다** — 열만 바꿔 쓰면 «행은 A 회사 것인데 판은 B 회사 것» 이 된다.
    #: ★ 그래서 반대로 한다: 자료는 자기 테넌트로 심고, **설치본이 그 테넌트를 쓰게** 한다
    #:   (`data/instance.json` → `run.py` 가 읽는다). 설정 파일을 `config` 가 import
    #:   시점에 읽게 하면 시험이 개발자의 `data/` 에 의존한다(그래서 100건이 깨졌다).
    demo.TENANT_OVERRIDE = ""
    _write_instance_tenant()

    from core.data_preparation import store as dp

    with dp.data_preparation_store.transaction() as conn:
        existing = [dict(r) for r in conn.execute(
            "SELECT instance_id FROM kit_instances WHERE status='active'")]

    #: ⚠️⚠️ **조직은 새로 만들지 않는다.** `demo._org()` 는 `<뿌리>/org.db` 에 두 단짜리
    #:   조직을 세우고 싱글턴을 그쪽으로 돌린다 — 자기 뿌리에서는 맞지만 사전검증 정본에서는
    #:   **앱이 읽는 `data/master/master.db` 를 무시한 별도 파일**이 생긴다(1차 판이 그랬다).
    #:   이미 부서 13개·사용자 25명이 있다. 그것을 덮지 않는다.
    #: ★ 대신 강제 정책만 켠다 — 그것이 `_org()` 의 나머지 절반이고, 그것 없이는 범위 경계가
    #:   화면에서 보이지 않는다.
    import core.scope_policy as sp
    sp._read = lambda: {"org_enforce": True}
    #: ★ 사전검증 정본에는 이미 조직이 있다 — 파종이 임시 조직을 만들지 못하게 한다.
    demo.SKIP_ORG = True
    _ensure_scope_home()

    if existing:
        #: 멱등 — 이미 있으면 **다시 심지 않고 모자란 것만 보충**한다.
        print(f"\n이미 인스턴스가 {len(existing)}개 있습니다 — 보충만 합니다.")
        demo._rewire_ontology_only()
        demo._top_up(existing[0]["instance_id"])
        _top_up_ownership()
        _top_up_ontology()
    else:
        demo.seed()

    _show("심은 뒤", inventory())
    print("\n★ 표시 확인: 키트는 DEMO/SYNTHETIC, 판은 DEMO_CERTIFIED 로 들어갑니다 —")
    print("  화면이 「시연용 합성 데이터 · 실적 인증이 아닙니다」로 적습니다.")
    print("\n이제 평소대로 띄우면 됩니다:  venv/Scripts/python.exe run.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
