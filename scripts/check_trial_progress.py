"""Read-only, evidence-gated incremental progress calculator (not product tests)."""
from __future__ import annotations
import argparse
import copy
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/roadmap/OPERATIONAL_TRIAL_GAP_BASELINE.json"
STEPS = ROOT / "docs/roadmap/OPERATIONAL_TRIAL_DELIVERY_STEPS.json"

def require(ok, message):
    if not ok:
        raise ValueError(message)

def check_evidence(paths, check_paths):
    require(bool(paths), "accepted result has no evidence")
    if check_paths:
        for evidence in paths:
            path = (ROOT / evidence).resolve()
            require(path.is_relative_to(ROOT) and path.is_file(), "missing/outside evidence: " + evidence)

def calculate(base, ledger, check_paths=True):
    require(base["baseline_id"] == ledger["baseline_id"], "mixed baseline versions")
    require(base["status"] == "ACTIVE", "inactive baseline")
    goals = {r["id"]: r for r in base["work_items"]}
    require(len(goals) == len(base["work_items"]), "duplicate goal")
    budgets = ledger["parent_budgets"]
    require(set(goals) == set(budgets), "goal/budget coverage")
    require(len(goals) == ledger["accounting"]["original_goals"], "goal scope changed")
    require(sum(budgets.values()) == ledger["accounting"]["total_points"], "budget total")
    require(all(isinstance(n, int) and n > 0 and n % 5 == 0 for n in budgets.values()), "bad budget")
    rows = ledger["steps"]
    by_id = {r["id"]: r for r in rows}
    require(len(by_id) == len(rows) == ledger["accounting"]["step_count"], "duplicate/missing step")
    grouped = {key: [] for key in goals}
    for row in rows:
        require(row["parent"] in goals, "unknown parent")
        grouped[row["parent"]].append(row)
        require(row["status"] in {"planned", "accepted", "blocked", "reopened"}, "bad status")
        require(isinstance(row["points"], int) and row["points"] > 0, "bad points")
        require(bool(row["title"].strip()) and bool(row["acceptance"].strip()), "missing exit")
        require(all(dep in by_id and dep != row["id"] for dep in row["prerequisites"]), "bad dependency")
        require(all(key in ledger["approvals"] for key in row["approval_ids"]), "unknown approval")
        if row["status"] == "accepted":
            require(row["review_status"] == "accepted", "review not accepted")
            check_evidence(row["evidence"], check_paths)
            require(all(by_id[dep]["status"] == "accepted" for dep in row["prerequisites"]), "unmet prerequisite")
            for key in row["approval_ids"]:
                approval = ledger["approvals"][key]
                require(approval["status"] == "approved", "required approval missing")
                check_evidence(approval["evidence"], check_paths)
    visiting, seen = set(), set()
    def visit(key):
        require(key not in visiting, "dependency cycle")
        if key in seen:
            return
        visiting.add(key)
        for dep in by_id[key]["prerequisites"]:
            visit(dep)
        visiting.remove(key)
        seen.add(key)
    for key in by_id:
        visit(key)
    last = {}
    for key, items in grouped.items():
        require(bool(items), "goal without steps")
        require(sum(r["points"] for r in items) == budgets[key], "parent allocation changed")
        ordered = sorted(items, key=lambda r: int(r["id"].split(".")[1]))
        require([r["id"] for r in ordered] == [key + "." + str(i+1) for i in range(len(ordered))], "step numbering")
        last[key] = ordered[-1]
    for key, row in last.items():
        # Goal-level prerequisites guard closure, not every early increment.
        needed = {last[dep]["id"] for dep in goals[key]["depends_on"]}
        require(needed.issubset(set(row["prerequisites"])), "final closure prerequisite missing")
    accepted = [r for r in rows if r["status"] == "accepted"]
    earned = sum(r["points"] for r in accepted)
    total = sum(budgets.values())
    closed = sum(all(r["status"] == "accepted" for r in items) for items in grouped.values())
    ready, blocked = [], []
    for row in rows:
        if row["status"] == "accepted":
            continue
        deps = [d for d in row["prerequisites"] if by_id[d]["status"] != "accepted"]
        approvals = [a for a in row["approval_ids"] if ledger["approvals"][a]["status"] != "approved"]
        if not deps and not approvals:
            ready.append(row["id"])
        blocked.append({"id": row["id"], "prerequisites": deps, "approvals": approvals})
    # 담당은 목표 정본에서 가져온다. 선행 충족 목록은 개인 업무 배정이 아니다.
    ready_work = [{"id": key, "title": by_id[key]["title"],
                   "owner": goals[by_id[key]["parent"]]["owner"]} for key in ready]
    return {"baseline": ledger["baseline_id"], "earned_points": earned, "total_points": total,
            "percent": round(earned/total*100, 1), "closed_goals": closed, "total_goals": len(goals),
            "accepted_steps": len(accepted), "total_steps": len(rows),
            "remaining_points": total-earned, "ready_steps": ready, "ready_work": ready_work,
            "blockers": blocked,
            "warning": "수용 배점이며 가동/배포 승인이 아님. 선행·승인 충족 목록은 개인 업무 배정이 아니며 담당·현행 지시·승인 범위를 함께 확인."}

def forecast(ledger, current):
    accepted = {r["id"] for r in ledger["steps"] if r["status"] == "accepted"}
    by_id = {r["id"]: r for r in ledger["steps"]}
    points = current["earned_points"]
    out = []
    for item in ledger["next_sequence"]:
        row = by_id[item["id"]]
        increase = 0 if row["id"] in accepted else row["points"]
        points += increase
        accepted.add(row["id"])
        out.append({"id": row["id"], "title": row["title"], "new_points": increase,
                    "projected_percent": round(points/current["total_points"]*100, 1),
                    "condition": "All listed preceding steps are accepted; approvals/environments still required."})
    return out

def self_test(base, ledger):
    start = calculate(base, ledger, check_paths=False)
    goals = {row["id"]: row for row in base["work_items"]}
    steps = {row["id"]: row for row in ledger["steps"]}
    require([row["id"] for row in start["ready_work"]] == start["ready_steps"], "ready view mismatch")
    require(all(row["owner"] == goals[steps[row["id"]]["parent"]]["owner"]
                for row in start["ready_work"]), "ready owner mismatch")
    # A valid intermediate delivery must earn points before its parent closes.
    positive = copy.deepcopy(ledger)
    row = next(r for r in positive["steps"] if r["id"] == "C02.1")
    delta = row["points"]
    row.update(status="accepted", review_status="accepted", evidence=["synthetic-proof"])
    after = calculate(base, positive, check_paths=False)
    require(after["earned_points"] == start["earned_points"] + delta, "intermediate credit withheld")
    require(after["closed_goals"] == start["closed_goals"], "parent closed too early")
    require(forecast(positive, after)[0]["new_points"] == 0, "double forecast credit")
    cases = []
    bad = copy.deepcopy(ledger); bad["steps"].append(copy.deepcopy(bad["steps"][0])); cases.append(bad)
    bad = copy.deepcopy(ledger); bad["steps"][0]["points"] += 5; cases.append(bad)
    bad = copy.deepcopy(positive); next(r for r in bad["steps"] if r["id"] == "C02.1")["evidence"] = []; cases.append(bad)
    bad = copy.deepcopy(positive); next(r for r in bad["steps"] if r["id"] == "C02.1")["review_status"] = "not_reviewed"; cases.append(bad)
    bad = copy.deepcopy(ledger); next(r for r in bad["steps"] if r["id"] == "C02.2").update(status="accepted", review_status="accepted", evidence=["proof"]); cases.append(bad)
    bad = copy.deepcopy(ledger)
    for key in ("P03.1", "P03.2"):
        next(r for r in bad["steps"] if r["id"] == key).update(status="accepted", review_status="accepted", evidence=["proof"])
    # 현재 승인 상태와 독립적으로 미승인 반례를 구성한다.
    bad["approvals"]["ENV-PG"].update(status="pending", evidence=[])
    cases.append(bad)
    bad = copy.deepcopy(ledger); bad["steps"][0]["prerequisites"] = [bad["steps"][0]["id"]]; cases.append(bad)
    bad = copy.deepcopy(ledger); next(r for r in bad["steps"] if r["id"] == "C02.3")["prerequisites"] = ["C02.2"]; cases.append(bad)
    for index, bad in enumerate(cases, 1):
        try:
            calculate(base, bad, check_paths=False)
        except ValueError:
            continue
        raise ValueError("negative test accepted: " + str(index))
    return {"negative_cases_rejected": len(cases), "increment_without_parent_close": delta,
            "double_credit_rejected": True}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--forecast", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    ledger = json.loads(STEPS.read_text(encoding="utf-8"))
    result = calculate(base, ledger)
    if args.self_test:
        result["checks"] = self_test(base, ledger)
    if args.forecast:
        result["conditional_forecast"] = forecast(ledger, result)
    if args.markdown:
        print(f"전체 진척 {result['earned_points']}/{result['total_points']}점 = {result['percent']:.1f}%")
        print(f"목표 종결 {result['closed_goals']}/{result['total_goals']}; 수용 단계 {result['accepted_steps']}/{result['total_steps']}")
        print("선행·승인 충족 단계(담당 배정 아님):")
        for row in result["ready_work"]:
            print(f"- {row['id']} | {row['owner']} | {row['title']}")
        if args.forecast:
            for row in result["conditional_forecast"]:
                print(f"- {row['id']} {row['title']}: +{row['new_points']}점, 조건부 누적 {row['projected_percent']:.1f}%")
        print(result["warning"])
    else:
        result.pop("blockers", None)
        print(json.dumps(result, ensure_ascii=False))
if __name__ == "__main__":
    main()
