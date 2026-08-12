"""[G1-C2] 과거 시험 릴리스가 **실제 조직 문맥에 남아 있는 것**을 감사·격리한다.

## 무엇이 발견됐나 (2026-08-12 실측)

프로젝트 메타는 G1-C1.1 에서 검증 샌드박스로 옮겼다. 그런데 **릴리스와 승격은 그대로였다.**

    library/*/release.json          3건 — tenant·scope·mode 가 **전부 빈 값**
    workspace.db release_promotions 3건 — 전부 `→ enterprise`, 그중 1건은 이미 **approved**
    workspace.db workspace_shares   1건 — 실제 법인 `LS_MNM` 에 probe 공유가 **active**
    workspace.db workspace_forks    2건 — `node_copper_demo`
    workspace.db release_rollbacks  2건

⚠️⚠️ 그리고 `node_batt_demo` · `node_copper_demo` 는 **ECM 에 존재하지 않는 노드다.**
  즉 승격·공유가 「없는 조직」을 가리킨다. 빈 문맥을 기본값으로 읽는 코드에서 이것은
  `tenant_default/REAL` 이 되고, 그러면 **시험 릴리스가 실제 조직의 전사 승격 대기 항목처럼**
  경영 브리핑에 뜬다. 실제로 그렇게 뜨고 있었다.

## 왜 삭제하지 않는가

삭제하면 A-1 완주 증거와 회귀 대조군이 사라진다. 대신 **격리**한다 —
검증 샌드박스 범위로 옮기고, 승격 절차에서는 빼고, 지식 승격 불가로 표시한다.

## 사용

    venv/Scripts/python.exe scripts/audit_legacy_release_contamination.py           # 감사만
    venv/Scripts/python.exe scripts/audit_legacy_release_contamination.py --apply   # 격리 적용

⚠️ `--apply` 는 적용 전 상태를 `docs/migration/` 에 통째로 남긴다. 되돌릴 수 없는 일을
  되돌릴 수 있게 만들어 두지 않으면, 잘못 눌렀을 때 남는 것은 사과뿐이다.
⚠️ **분류하지 못한 항목은 건드리지 않고 보고한다.** 「아마 시험일 것」으로 지우면 실제
  업무 산출물을 잃는다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.paths import data_path                                     # noqa: E402
from core.project_visibility import (SANDBOX_CUSTODIAN, SANDBOX_ENTITY_MODE,  # noqa: E402
                                     SANDBOX_SCOPE_CODE, sandbox_scope_id)

#: 시험·탐침 산출물 이름 규칙.
#: ⚠️ `probe` · `demo` · `TEST####` 를 넣은 이유 — 실측에서 `probe_app` · `ui_demo_app` ·
#:   `TEST1001-copy` · `del_probe_2` 가 나왔고, 이것들은 `test_` 규칙에 걸리지 않는다.
FIXTURE_PATTERNS = (
    re.compile(r"^test_", re.I), re.compile(r"^MEGA_0"), re.compile(r"^scenario-", re.I),
    re.compile(r"_canary", re.I), re.compile(r"^__"),
    re.compile(r"probe", re.I), re.compile(r"^ui_demo", re.I), re.compile(r"^TEST\d", re.I),
    re.compile(r"^demo[-_]", re.I),
)

#: 실제 조직 범위처럼 보이는데 ECM 에 없는 노드는 **끊어진 참조**다. 따로 세어 보고한다.
DANGLING_NOTE = "ECM 에 없는 범위"


def is_fixture(*names: str) -> bool:
    for n in names:
        for p in FIXTURE_PATTERNS:
            if n and p.search(str(n)):
                return True
    return False


def _scope_exists(code: str) -> bool:
    try:
        from core.enterprise_context.repository import ecm_repository as repo
        return bool(repo.get_node(code) or repo.find_node_by_code(code)
                    or repo.find_node_by_dept(code))
    except Exception:
        return False


def audit() -> dict:
    """무엇이 오염됐는지 **세어서** 돌려준다. 아무것도 바꾸지 않는다."""
    out = {"releases": [], "promotions": [], "shares": [], "forks": [],
           "unclassified": [], "dangling_scopes": set()}

    for name in sorted(os.listdir("library")) if os.path.isdir("library") else []:
        p = os.path.join("library", name, "release.json")
        if not os.path.exists(p):
            out["unclassified"].append({"kind": "release", "id": name, "why": "release.json 없음"})
            continue
        try:
            d = json.load(open(p, encoding="utf-8")) or {}
        except Exception as e:
            out["unclassified"].append({"kind": "release", "id": name, "why": f"판독 실패: {e}"})
            continue
        own = d.get("ownership") or {}
        blank = not (str(d.get("tenant_id") or own.get("tenant_id") or "").strip())
        pid = str(d.get("project_id") or "")
        #: ⚠️ **이미 격리된 것은 대상이 아니다.** 이 조건을 빼면 다시 돌릴 때마다 같은 항목이
        #   «남아 있다» 고 보고되어, 적용이 됐는지 안 됐는지 알 수 없다(직전 마이그레이션에서
        #   같은 실수를 했다).
        quarantined = (str(d.get("scope_type") or own.get("scope_type") or "") == "SANDBOX")
        rec = {"id": name, "project_id": pid, "context_blank": blank,
               "fixture": is_fixture(name, pid) and not quarantined}
        if rec["fixture"]:
            out["releases"].append(rec)
        elif blank and not quarantined:
            out["unclassified"].append({"kind": "release", "id": name,
                                        "why": "조직 문맥이 비었지만 시험 산출물로 분류되지 않음"})

    conn = sqlite3.connect(data_path("workspace.db"))
    conn.row_factory = sqlite3.Row
    for row in conn.execute("SELECT * FROM release_promotions"):
        r = dict(row)
        scope = str(r.get("from_scope") or "")
        if scope and not _scope_exists(scope):
            out["dangling_scopes"].add(scope)
        fixture = is_fixture(r.get("release_id"), r.get("project_id"))
        if fixture and r.get("status") != "quarantined":
            out["promotions"].append(r)
        elif not fixture:
            # ⚠️ **이미 격리된 것을 «분류 안 됨» 으로 세지 않는다.** 그러면 다 끝낸 뒤에도
            #   경고가 남아, 사람이 그 경고를 읽지 않게 된다.
            out["unclassified"].append({"kind": "promotion", "id": r.get("release_id"),
                                        "why": f"시험 분류 안 됨 · status={r.get('status')}"})
    for row in conn.execute("SELECT * FROM workspace_shares"):
        r = dict(row)
        scope = str(r.get("from_scope") or "")
        if scope and not _scope_exists(scope):
            out["dangling_scopes"].add(scope)
        if is_fixture(r.get("release_id")) and scope != sandbox_scope_id():
            out["shares"].append(r)
    for row in conn.execute("SELECT * FROM workspace_forks"):
        r = dict(row)
        scope = str(r.get("owner_scope") or "")
        if scope and not _scope_exists(scope):
            out["dangling_scopes"].add(scope)
        if (is_fixture(r.get("source_release_id"), r.get("new_project_id"))
                and scope != sandbox_scope_id()):
            out["forks"].append(r)
    conn.close()
    out["dangling_scopes"] = sorted(out["dangling_scopes"])
    return out


def apply(a: dict) -> str:
    """격리한다. **적용 전 상태를 통째로 남긴다.**"""
    node_id = sandbox_scope_id()
    if not node_id:
        raise RuntimeError(
            f"{SANDBOX_SCOPE_CODE} 노드가 없습니다 — "
            f"scripts/migrate_legacy_fixtures_to_sandbox.py --apply 를 먼저 돌리십시오.")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("docs/migration", exist_ok=True)
    backup = os.path.join("docs", "migration", f"g1c2_release_quarantine_{stamp}.json")

    before = {"releases": {}, "promotions": [], "shares": [], "forks": []}
    for rec in a["releases"]:
        p = os.path.join("library", rec["id"], "release.json")
        before["releases"][rec["id"]] = json.load(open(p, encoding="utf-8"))
    before["promotions"] = a["promotions"]
    before["shares"] = a["shares"]
    before["forks"] = a["forks"]
    json.dump({"applied_at": stamp, "sandbox_node_id": node_id, "before": before},
              open(backup, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)

    ctx = {"tenant_id": "tenant_default", "enterprise_scope_id": node_id,
           "entity_mode": SANDBOX_ENTITY_MODE, "scope_type": "SANDBOX",
           "owner_user_id": SANDBOX_CUSTODIAN, "owner_dept_id": "", "visibility": "private",
           "nature": "test_fixture", "ownership_basis": "LEGACY_TEST_MIGRATION",
           "data_origin": "SYNTHETIC",
           #: ★ 지식 허브가 이것을 보고 **승격 대상에서 뺀다.**
           "knowledge_tier": "SYNTHETIC_TEST", "knowledge_promotable": False}
    for rec in a["releases"]:
        p = os.path.join("library", rec["id"], "release.json")
        d = json.load(open(p, encoding="utf-8")) or {}
        d.update({k: v for k, v in ctx.items()})
        own = dict(d.get("ownership") or {})
        own.update(ctx)
        d["ownership"] = own
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    conn = sqlite3.connect(data_path("workspace.db"))
    now = datetime.now().isoformat()
    reason = (f"[G1-C2] 검증 샌드박스 자료로 격리 — 시험 산출물이 실제 조직의 전사 승격 "
              f"대기 항목으로 읽히던 것을 끊었습니다({SANDBOX_SCOPE_CODE}).")
    for r in a["promotions"]:
        #: ⚠️ `rejected` 를 쓰지 않는다 — 그것은 「사람이 검토해서 반려했다」는 뜻이고,
        #:   여기서 일어난 일은 「애초에 승격 절차에 있어서는 안 되는 자료였다」다.
        conn.execute("UPDATE release_promotions SET status='quarantined', "
                     "from_scope=?, rejected_reason=?, updated_at=? WHERE promotion_id=?",
                     (node_id, reason, now, r["promotion_id"]))
    for r in a["shares"]:
        if str(r.get("status")) == "active":
            conn.execute("UPDATE workspace_shares SET status='revoked', revoked_at=?, "
                         "from_scope=? WHERE share_id=?", (now, node_id, r["share_id"]))
        else:
            conn.execute("UPDATE workspace_shares SET from_scope=? WHERE share_id=?",
                         (node_id, r["share_id"]))
    for r in a["forks"]:
        conn.execute("UPDATE workspace_forks SET owner_scope=? WHERE fork_id=?",
                     (node_id, r["fork_id"]))
    conn.commit()
    conn.close()
    return backup


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    a = audit()

    print(f"■ 릴리스 {len(a['releases'])}건 · 승격 {len(a['promotions'])}건 · "
          f"공유 {len(a['shares'])}건 · 복제 {len(a['forks'])}건 격리 대상")
    for r in a["releases"]:
        print(f"    릴리스  {r['id']:44s} 문맥비었음={r['context_blank']}")
    for r in a["promotions"]:
        print(f"    승격    {str(r['release_id']):44s} {r['from_scope']} → {r['target_scope']} "
              f"· status={r['status']}")
    for r in a["shares"]:
        print(f"    공유    {str(r['release_id']):44s} {r['from_scope']} → {r['to_scope']} "
              f"· status={r['status']}")
    for r in a["forks"]:
        print(f"    복제    {str(r['source_release_id']):44s} owner={r['owner_scope']}")
    if a["dangling_scopes"]:
        print(f"\n⚠️ {DANGLING_NOTE}를 가리키는 참조가 있습니다: {a['dangling_scopes']}")
        print("   빈 문맥을 기본값으로 읽는 코드에서 이것은 tenant_default/REAL 이 됩니다 —")
        print("   즉 시험 자료가 **실제 조직 항목처럼** 경영 브리핑에 뜹니다.")
    if a["unclassified"]:
        print(f"\n⚠️ 분류하지 못해 **건드리지 않은** 항목 {len(a['unclassified'])}건 "
              f"— 사람이 판단해야 합니다.")
        for u in a["unclassified"]:
            print(f"    {u['kind']:10s} {str(u['id']):44s} {u['why']}")

    if not args.apply:
        print("\n감사만 했습니다. 적용하려면 --apply 를 붙이십시오.")
        return 0
    backup = apply(a)
    print(f"\n적용 전 상태 백업: {backup}")
    after = audit()
    left = [p for p in after["promotions"] if p["status"] != "quarantined"]
    print(f"격리 후 남은 승격(비격리): {len(left)}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
