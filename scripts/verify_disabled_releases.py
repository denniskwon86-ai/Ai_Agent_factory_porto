"""사용 중단 적용 결과를 기존 HTTP API로 재조회한다. 업무 데이터 변경은 없다."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import quote

import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--user", required=True)
    args = parser.parse_args()
    applied = json.loads(args.result.read_text(encoding="utf-8"))["disabled"]
    password = os.environ.get("LAXS_REVIEW_PASSWORD")
    if not password or not applied or args.report.exists():
        raise RuntimeError("인증 입력·적용 명세·새 보고서 경로를 확인하십시오.")
    session = requests.Session()
    base = "http://127.0.0.1:8080/api/v1"

    def call(method, path, **kwargs):
        response = session.request(method, base + path, timeout=30, **kwargs)
        response.raise_for_status()
        return response.json()["data"]

    session.headers["X-Session-Token"] = call("POST", "/auth/login", json={
        "user_id": args.user, "password": password})["token"]
    try:
        checked = []
        for row in applied:
            rid = row["release_id"]
            path = quote(rid, safe="")
            state = call("GET", "/programs/" + path)
            item = call("GET", "/factory/library/item/" + path)
            if state["status"] != "disabled" or len(state["history"]) != row["history_count"]:
                raise RuntimeError("적용 결과와 현재 상태·이력이 다릅니다: " + rid)
            if (item["lifecycle"].get("usable") is not False or not item.get("payload_withheld")
                    or any(key in item for key in ("frontend_code_summary", "backend_code_summary",
                                                   "artifacts", "artifact_summaries"))):
                raise RuntimeError("실행용 코드 차단 검증 실패: " + rid)
            checked.append({"release_id": rid, "status": state["status"], "payload_withheld": True})
        catalog = call("GET", "/factory/library/list")
        # 토큰·실행 코드·업무 행은 증적 파일에 적지 않는다.
        catalog = [{key: row.get(key) for key in ("release_id", "project_name", "lifecycle_status")}
                   for row in catalog]
        result = {"checked": checked, "server_catalog": catalog,
                  "kit_apps": [row for row in catalog if str(row["release_id"]).startswith("kitapp_")]}
        with args.report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps({"disabled_payloads_verified": len(checked), "catalog_rows": len(catalog),
                          "kit_apps": len(result["kit_apps"])}))
    finally:
        response = session.post(base + "/auth/logout", timeout=30)
        response.raise_for_status()
        session.close()


if __name__ == "__main__":
    main()
