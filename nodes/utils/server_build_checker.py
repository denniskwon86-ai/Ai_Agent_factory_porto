"""★★★ 앱이 **자기 서버를 만들었는가** — 계약 프로필 프로젝트의 하드 차단기. (2026-08-27)

## ⚠️⚠️ 무엇이 있었나 — 두 번째다

`app_runtime_brief` 의 머리말은 이 사고로 시작한다:

    실제 가동(`live-walk-02`)에서 Architect 가 «경량 백엔드 프레임워크(예: Spring Boot)»
    로 설계했고, 공장은 `InboundApplication.java`·`schema.sql` 을 만들었다.
    → 프론트 렌더 검증 8회 반려 → FAILED_REVIEW. **앱이 한 줄도 안 나왔다.**

그래서 고지문을 썼다. 그런데 `CRM002` 에서 **또 났다** — 이번에는 FastAPI 로:

    main.py · backend/routers.py · backend/models.py · backend/database.py
    backend/services.py · backend/schemas.py     (SQLAlchemy + FastAPI)

★ 고지문은 **설득**이고 이것은 **차단**이다. 안 들으면 아무 일도 일어나지 않는다 —
  실제로 두 번 다 안 들었다.

## 계약이 금지하는 것과의 대응

    server.custom_logic   HOST_SERVICE_REQUIRED   앱이 서버 로직을 두지 않는다
    api.direct_call       PROHIBITED              앱이 임의 API 를 부르지 않는다
    storage.local_db      PROHIBITED              앱이 자체 DB 를 두지 않는다

⚠️ 계약 프로필이 **꺼진** 레거시 프로젝트에는 적용하지 않는다. 그 프로젝트들은 자유
  형식 앱을 만들어 왔고, 소급하면 이미 도는 것들이 깨진다(저장소의 다른 경계와 같은 규칙).

LLM 0콜.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

#: 서버 프레임워크·ORM·자체 DB 의 **결정적 신호**. 이름이 아니라 **호출 형태**로 잡는다.
#: ⚠️ 파일 이름(`backend/…`)으로 잡지 않는다 — 이름을 바꾸면 그대로 우회로가 된다.
_SIGNALS = (
    ("server_framework",
     re.compile(r"""(?ix)
        (\bFastAPI\s*\() | (\bAPIRouter\s*\() |
        (\bflask\s*\.\s*Flask\s*\() | (\bexpress\s*\(\s*\)) |
        (@(app|router)\.(get|post|put|patch|delete)\s*\() |
        (\bapp\.(get|post|put|delete)\s*\(\s*["'][^"']*["']\s*,)
     """),
     "서버 프레임워크·라우트 정의"),
    ("orm_or_local_db",
     re.compile(r"""(?ix)
        (\bsqlalchemy\b) | (\bcreate_engine\s*\() | (\bsessionmaker\s*\() |
        (\bdeclarative_base\s*\() | (\bsqlite3\s*\.\s*connect\s*\() |
        (\bmongoose\s*\.) | (\bprisma\s*\.) | (\bTypeORM\b)
     """),
     "ORM·자체 데이터베이스"),
    ("server_entrypoint",
     re.compile(r"""(?ix)
        (\buvicorn\s*\.\s*run\s*\() | (\bapp\.run\s*\() |
        (\bapp\.listen\s*\() | (\bhttp\.createServer\s*\()
     """),
     "서버 기동 진입점"),
)


def scan_text(text: str, path: str = "") -> List[Dict[str, Any]]:
    """한 파일의 신호. **줄 번호와 원문 줄**을 붙인다 — 근거 없는 판정은 신뢰받지 못한다."""
    out: List[Dict[str, Any]] = []
    if not text:
        return out
    lines = text.splitlines()
    for sid, rx, desc in _SIGNALS:
        for m in rx.finditer(text):
            n = text[: m.start()].count("\n")
            out.append({"signal": sid, "description": desc, "path": path,
                        "line": n + 1,
                        "evidence": (lines[n].strip() if n < len(lines) else "")[:160]})
            break                       # 파일당 신호 종류별 1건이면 충분하다
    return out


def check_server_build(files: Any) -> Dict[str, Any]:
    """생성 파일 목록에서 **서버를 만들었는지** 본다.

    ⚠️ 빈 목록은 `skipped` 다 — 「볼 것이 없었다」와 「봤는데 깨끗했다」는 다르다.
      전자를 통과로 읽으면 이 게이트는 장식이 된다(`release_promotion` 과 같은 규칙)."""
    items = [f for f in (files or []) if isinstance(f, dict)]
    if not items:
        return {"ok": True, "skipped": True, "blocking": [], "scanned": 0}
    hits: List[Dict[str, Any]] = []
    for f in items:
        code = f.get("code", "") or ""
        if code:
            hits.extend(scan_text(code, path=f.get("file_path", "")))
    return {"ok": not hits, "skipped": False, "blocking": hits, "scanned": len(items)}


def render_report(result: Dict[str, Any]) -> str:
    return "\n".join(
        f"  · {h.get('path', '')}:{h.get('line', '')} — {h.get('description', '')}"
        f"  ({h.get('evidence', '')})"
        for h in (result.get("blocking") or [])[:12])
