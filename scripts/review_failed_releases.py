"""불량 릴리즈 감사 및 기존 인증 API를 통한 사용 중단. 삭제·승격·권한 변경 없음."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.release_catalog_audit import inspect_release


def write_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply-plan", type=Path)
    parser.add_argument("--user")
    args = parser.parse_args()
    rows = [inspect_release(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted((ROOT / "library").glob("*/release.json"))]
    planned = [r for r in rows if r["reasons"]]
    if not args.apply_plan:
        write_new(args.report, {"mode": "READ_ONLY", "population": len(rows), "targets": planned,
                                "preserved": [r for r in rows if not r["reasons"]]})
        print(json.dumps({"population": len(rows), "targets": len(planned),
                          "by_project": {p: sum(r["project_id"] == p for r in planned)
                                         for p in sorted({r["project_id"] for r in planned})}}))
        return
    saved = json.loads(args.apply_plan.read_text(encoding="utf-8"))
    if saved.get("mode") != "READ_ONLY" or saved["targets"] != planned:
        raise RuntimeError("감사 이후 대상 내용이 바뀌었습니다. 다시 검토해야 합니다.")
    if not args.user or not os.environ.get("LAXS_REVIEW_PASSWORD"):
        raise RuntimeError("기존 계정의 명시적 인증이 필요합니다.")
    import requests
    session = requests.Session()
    base = "http://127.0.0.1:8080/api/v1"
    def call(method, path, **kwargs):
        response = session.request(method, base + path, timeout=60, **kwargs)
        response.raise_for_status()
        return response.json()
    token = call("POST", "/auth/login", json={"user_id": args.user,
                                            "password": os.environ["LAXS_REVIEW_PASSWORD"]})["data"]["token"]
    session.headers["X-Session-Token"] = token
    try:
        before = []
        for row in planned:
            state = call("GET", "/programs/" + row["release_id"])["data"]
            dep = state["dependents"]
            if dep.get("count") or dep.get("unmeasured"):
                raise RuntimeError("의존 대상 또는 확인하지 못한 영향이 있어 중단합니다: " + row["release_id"])
            before.append({"release": row, "state": state})
        # 쓰기 전에 전체 대상·이력을 새 파일에 보존한다. 중간 실패해도 원상태가 남는다.
        write_new(args.report, {"mode": "BEFORE_DISABLE", "actor": args.user, "targets": before})
        changed = []
        for item in before:
            row = item["release"]
            rid = row["release_id"]
            reason = ("사용자 요청에 따른 미완성 앱 정리. "
                      + ("작업 실패·미완료 상태에서 반복 게시됨. " if "INCOMPLETE_FAILED_BUILD" in row["reasons"] else "")
                      + ("호스트 인증과 별개인 자체 로그인·비밀번호 저장으로 업무 확인 불가. " if "APP_LOCAL_LOGIN" in row["reasons"] else "")
                      + "Codex가 기존 관리 API로 사용만 중단. 코드·업무 데이터·게시 이력은 보존.")
            if item["state"]["status"] != "disabled":
                call("POST", "/programs/" + rid + "/disable", json={"reason": reason})
            after = call("GET", "/programs/" + rid)["data"]
            if after["status"] != "disabled":
                raise RuntimeError("사용 중단 재조회 불일치: " + rid)
            changed.append({"release_id": rid, "status": after["status"], "history_count": len(after["history"])})
        # 원본 게시물은 해시도 같아야 한다.
        after_rows = [inspect_release(json.loads(p.read_text(encoding="utf-8")))
                      for p in sorted((ROOT / "library").glob("*/release.json"))]
        if after_rows != rows:
            raise RuntimeError("게시물 내용이 변경되었습니다. 별도 검토가 필요합니다.")
        write_new(args.report.with_suffix(".result.json"), {"disabled": changed, "release_files_unchanged": True})
        print(json.dumps({"disabled": len(changed), "release_files_unchanged": True}))
    finally:
        call("POST", "/auth/logout")


if __name__ == "__main__":
    main()

