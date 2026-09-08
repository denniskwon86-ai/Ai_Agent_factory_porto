"""게시물의 명시적 실패 근거만 분류한다. 이름·중복·빈 코드만으로 폐기하지 않는다."""
from collections import Counter
import hashlib
import json


def inspect_release(release):
    tasks = release.get("wbs_tasks") or []
    counts = Counter(str(t.get("status") or "UNKNOWN") for t in tasks if isinstance(t, dict))
    reasons = []
    if str(release.get("terminal_status") or "").startswith("FAILED") or counts.get("FAILED"):
        reasons.append("INCOMPLETE_FAILED_BUILD")
    scan = release.get("platform_auth_scan") or {}
    signals = sorted({h.get("signal") for h in scan.get("blocking", [])
                      if isinstance(h, dict) and h.get("signal") in {
                          "local_login_form", "password_storage", "local_login_route", "jwt_issuer"}})
    if "local_login_form" in signals and any(s in signals for s in ("password_storage", "local_login_route", "jwt_issuer")):
        reasons.append("APP_LOCAL_LOGIN")
    return {"release_id": release.get("release_id"), "project_id": release.get("project_id"),
            "project_name": release.get("project_name"), "created_at": release.get("created_at"),
            "task_counts": dict(counts), "terminal_status": release.get("terminal_status"),
            "auth_signals": signals, "reasons": reasons,
            "content_fingerprint": hashlib.sha256(json.dumps(release, sort_keys=True,
                ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()}

