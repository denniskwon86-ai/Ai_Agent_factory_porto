"""[CL-0] 생성 앱의 **자체 인증 생성**을 정적으로 잡는다.

## 무엇을 막는가

생성된 앱은 플랫폼 안에서 돌고 인증을 호스트에서 상속한다(`core/app_manifest.py`). 그런데
생성기는 "로그인 화면"을 아주 자연스럽게 만든다 — 대부분의 예제 코드가 그렇게 생겼기 때문이다.
그 앱은 동작하고 화면도 그럴듯하지만 **회사 권한 체계 밖에서 사용자를 인증**한다. 조직 범위·
등급·감사가 전부 우회되고, 이 저장소가 권한 모델에 들인 통제가 앱 하나로 무력화된다.

## 이 검사기의 어려운 부분은 "무엇을 잡을까"가 아니라 "무엇을 놓아줄까"다

⚠️ 업무 앱에는 인증과 무슨 상관없는 `승인`·`전자서명 확인`·`외부 API 키`·일반 입력 폼이 늘 있다.
  그것까지 결함으로 잡으면 개발자는 검사기를 **끈다.** 끈 검사기는 없는 것과 같으므로, 이 파일은
  **인증 목적 패턴만** 잡고 나머지는 명시적으로 놓아준다(`_ALLOWED_CONTEXT`).

  · 잡는다: 로그인 폼/엔드포인트 · 비밀번호 컬럼·해싱 · JWT 발급(서명) · 자체 사용자/세션 테이블
  · 놓아준다: 업무 승인(approve) · 전자서명 확인 · 외부 시스템 인증 헤더 사용 ·
    JWT **검증만** 하는 코드 · 호스트 SDK 로 현재 사용자를 읽는 코드

## 판정 방식

문자열 하나로 결정하지 않는다. 각 신호에 **근거 줄**을 함께 남기고, 허용 문맥이 같은 줄에 있으면
그 신호를 버린다. 근거 없는 판정은 개발자가 반박할 수 없고, 반박할 수 없는 판정은 신뢰받지 못한다.

LLM 0콜. 결정론적.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List

#: 검사 대상 확장자. 바이너리·잠금파일은 보지 않는다.
_EXTS = (".py", ".js", ".jsx", ".ts", ".tsx", ".sql", ".java", ".go", ".rb", ".php")

#: 이 문맥이 같은 줄에 있으면 **인증 목적이 아니라고 본다.**
#: ★ 여기가 오탐을 막는 유일한 장치다 — 목록을 줄이면 개발자가 검사기를 끈다.
_ALLOWED_CONTEXT = (
    "approve", "approval", "승인", "결재", "결재선", "전자서명", "signature_verify",
    "verify_signature", "jwt.decode", "jwt_verify", "verify_token", "decode_token",
    "external_api", "api_key", "apikey", "webhook_secret", "oauth_client",  # 외부 시스템 인증
    "host_sdk", "platform_auth", "current_user()", "useCurrentUser", "X-Factory-User",
    "test", "spec", "mock", "fixture", "example",                            # 테스트·예시
)

#: 신호 정의 — (id, 정규식, 사람이 읽는 설명, 심각도)
#: 심각도 `block` 은 릴리스를 막는 것이고 `warn` 은 검토 대상이다.
_SIGNALS = (
    ("local_login_form",
     re.compile(r"""(?ix)
        (<form[^>]*\b(login|signin|sign-in)\b) |
        (\b(login|signin)_form\b) |
        (type\s*=\s*["']password["'])
     """),
     "로그인 폼 또는 비밀번호 입력 필드", "block"),
    ("local_login_route",
     re.compile(r"""(?ix)
        (route|path|url|app\.(post|get)|@(app|router)\.(post|get))\s*\(?\s*["'][^"']*
        /(login|signin|sign-in|authenticate|auth/token)\b
     """),
     "자체 로그인·토큰 발급 엔드포인트", "block"),
    ("password_storage",
     re.compile(r"""(?ix)
        (password_hash|passwordhash|hashed_password|bcrypt|scrypt|argon2|pbkdf2) |
        (\bpassword\b\s+(varchar|text|char)\s*\() |
        (columns?\s*=\s*\[[^\]]*["']password["'])
     """),
     "비밀번호 저장·해싱", "block"),
    ("jwt_issuer",
     re.compile(r"""(?ix)
        (jwt\.(encode|sign)) | (jsonwebtoken\.sign) | (createAccessToken) |
        (issue_(access_)?token) | (SignedJWT)
     """),
     "JWT 발급기(서명)", "block"),
    ("local_user_store",
     re.compile(r"""(?ix)
        (create\s+table\s+(if\s+not\s+exists\s+)?["'`\[]?(users?|accounts?|members?|
          user_sessions?|sessions?)\b) |
        (class\s+User(Model|Account|Entity)?\s*\() |
        (models?\.User\b\s*=)
     """),
     "자체 사용자·세션 테이블", "block"),
    ("auth_library",
     re.compile(r"""(?ix)
        (passport(-local)?) | (next-auth) | (flask_login) | (django\.contrib\.auth) |
        (spring-security) | (devise)
     """),
     "앱 자체 인증 라이브러리", "warn"),
)


def scan_text(text: str, path: str = "") -> List[Dict[str, Any]]:
    """한 파일의 신호 목록. 각 신호에 **줄 번호와 원문 줄**을 붙인다.

    ★ 근거 줄이 없으면 개발자가 반박할 수 없고, 반박할 수 없는 판정은 신뢰받지 못한다."""
    out: List[Dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        low = line.lower()
        allowed = [c for c in _ALLOWED_CONTEXT if c.lower() in low]
        for sid, rx, desc, severity in _SIGNALS:
            if not rx.search(line):
                continue
            if allowed:
                # 인증 목적이 아니라고 본다 — 무엇 때문에 놓아줬는지도 남긴다(감사 가능하게).
                out.append({"signal": sid, "severity": "ignored", "description": desc,
                            "path": path, "line": lineno, "evidence": line.strip()[:200],
                            "ignored_because": allowed[:3]})
                continue
            out.append({"signal": sid, "severity": severity, "description": desc,
                        "path": path, "line": lineno, "evidence": line.strip()[:200]})
    return out


def scan_paths(paths: List[str]) -> Dict[str, Any]:
    """파일·디렉터리 목록을 검사한다.

    돌려주는 것: `blocking`(릴리스 차단) · `warnings`(검토) · `ignored`(놓아준 것과 이유) ·
    `scanned`(본 파일 수). 읽지 못한 파일은 **조용히 넘기지 않고** `unreadable` 로 센다 —
    검사하지 못한 것을 통과로 읽으면 게이트가 장식이 된다."""
    findings: List[Dict[str, Any]] = []
    scanned = 0
    unreadable: List[str] = []
    for p in paths or []:
        for f in _iter_files(p):
            try:
                with open(f, "r", encoding="utf-8", errors="strict") as fh:
                    text = fh.read()
            except Exception:
                unreadable.append(f)
                continue
            scanned += 1
            findings.extend(scan_text(text, path=f))
    blocking = [f for f in findings if f["severity"] == "block"]
    warnings = [f for f in findings if f["severity"] == "warn"]
    ignored = [f for f in findings if f["severity"] == "ignored"]
    return {
        "ok": not blocking,
        "scanned": scanned, "unreadable": unreadable,
        "blocking": blocking, "warnings": warnings, "ignored": ignored,
        "summary": {"blocking": len(blocking), "warnings": len(warnings),
                    "ignored": len(ignored)},
        "note": ("`ignored` 는 허용 문맥(업무 승인·전자서명 확인·외부 API 인증·JWT 검증만·"
                 "테스트)이 같은 줄에 있어 인증 목적이 아니라고 판단한 것입니다. 오탐을 줄이지 "
                 "않으면 개발자가 이 검사를 끄고, 꺼진 검사는 없는 것과 같습니다."),
    }


#: 검사 대상에서 빼는 디렉터리. **`.archive` 가 핵심이다** — 지난 릴리스의 코드가 그대로
#: 남아 있어서, 이미 고친 결함이 새 릴리스를 계속 막는다(G1-A02).
_SKIP_DIRS = ("node_modules", ".git", "__pycache__", "venv", "dist", "build",
              ".archive", ".backup", ".tmp", "tmp", ".cache", ".pytest_cache")

#: 임시·백업 파일 이름 규칙. 편집기가 남긴 사본이 릴리스를 막으면 안 된다.
_TEMP_SUFFIXES = (".bak", ".orig", ".rej", ".tmp", ".swp", "~")


def _is_temp(name: str) -> bool:
    low = name.lower()
    return low.startswith(("~$", ".#")) or low.endswith(_TEMP_SUFFIXES)


def _iter_files(path: str):
    if os.path.isfile(path):
        if path.lower().endswith(_EXTS):
            yield path
        return
    if not os.path.isdir(path):
        return
    for root, dirs, files in os.walk(path):
        # ★★★ [G1-A02] **이전 산출물과 임시 파일은 검사하지 않는다.**
        #
        #   `.archive` 에는 지난 릴리스의 코드가 그대로 남아 있다. 그것까지 검사하면
        #   **이미 고친 결함이 계속 새 릴리스를 막는다.** 개발자는 원인을 못 찾고, 결국
        #   검사를 끄는 쪽을 택한다 — 꺼진 검사는 없는 것과 같다.
        #   ⚠️ 이것은 검사를 느슨하게 하는 것이 아니라 **대상을 지금 릴리스로 좁히는 것**이다.
        #     지금 내보내는 파일에 자체 인증이 있으면 그대로 걸린다.
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for name in files:
            if name.lower().endswith(_EXTS) and not _is_temp(name):
                yield os.path.join(root, name)


def assert_platform_auth(paths: List[str]) -> Dict[str, Any]:
    """차단 신호가 있으면 던진다. 통과하면 검사 결과를 돌려준다.

    ⚠️ 메시지에 **무엇을 대신 써야 하는지**를 적는다. 금지만 알려주면 개발자는 우회 방법을 찾고,
      우회된 자체 인증은 검사기가 다음번엔 못 잡는다."""
    r = scan_paths(paths)
    if not r["ok"]:
        first = r["blocking"][0]
        raise RuntimeError(
            f"생성 앱에 자체 인증 코드가 있습니다: {first['description']} "
            f"({first['path']}:{first['line']}) 외 {len(r['blocking']) - 1}건. "
            f"앱은 호스트 인증을 상속합니다 — 로그인 화면 대신 현재 사용자·조직·역할을 표시하고, "
            f"데이터 접근은 플랫폼 Runtime API 를 쓰십시오.")
    return r
