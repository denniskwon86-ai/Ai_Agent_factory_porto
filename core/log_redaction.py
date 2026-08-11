"""★★★ [P0-1B 보정] 로그에서 비밀값을 가린다.

## 왜 필요한가 — `Referrer-Policy` 로는 못 막는다

SSE 접속표(`?ticket=...`)는 **URL 로 오간다.** EventSource 가 헤더를 붙일 수 없어서 그렇게
설계했는데, 그 대가로 값이 다음 자리에 남는다.

  · `uvicorn.access` 로그의 request line — `GET /ws/timeline?ticket=xxxx HTTP/1.1`
  · 리버스 프록시 접근 로그
  · 예외 추적의 URL

앞선 커밋에서 응답에 `Referrer-Policy: no-referrer` 를 붙였지만 **그것은 브라우저가 다음
요청에 참조자를 싣지 않게 할 뿐, 서버가 자기 로그에 적는 것은 막지 못한다.** 티켓은 30초짜리
1회용이라 위험이 작지만, 로그는 오래 남고 여러 사람이 본다.

## 무엇을 가리는가

`ticket` · `token` · `session` · `password` · `secret` · `api_key` 계열 쿼리 파라미터.
값을 `***` 로 바꾸고 **키는 남긴다** — 「무엇이 가려졌는지」는 보여야 조사할 수 있다.

⚠️ 로그를 통째로 지우지 않는다. 접근 로그는 사고 조사의 근거다.
"""
from __future__ import annotations

import logging
import re

#: 값을 가릴 쿼리 파라미터. 이름에 이 조각이 들어가면 가린다(대소문자 무시).
SENSITIVE_KEYS = ("ticket", "token", "session", "password", "passwd", "secret", "api_key", "apikey")

_PATTERN = re.compile(
    r"(?i)\b(" + "|".join(re.escape(k) for k in SENSITIVE_KEYS) + r")=([^&\s\"']+)"
)


def redact(text: str) -> str:
    """문자열에서 민감한 쿼리 값을 `***` 로 바꾼다. 키는 남긴다."""
    if not text:
        return text
    return _PATTERN.sub(lambda m: f"{m.group(1)}=***", text)


class RedactingFilter(logging.Filter):
    """로그 레코드의 메시지와 인자에서 비밀값을 가린다.

    ⚠️ `uvicorn.access` 는 메시지를 `%s` 포맷과 **인자 튜플**로 넘긴다. 그래서 `record.msg`
      만 손보면 정작 URL 이 든 `record.args` 가 그대로 나간다 — 둘 다 처리한다."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if record.args:
                if isinstance(record.args, tuple):
                    record.args = tuple(
                        redact(a) if isinstance(a, str) else a for a in record.args)
                elif isinstance(record.args, dict):
                    record.args = {k: (redact(v) if isinstance(v, str) else v)
                                   for k, v in record.args.items()}
        except Exception:
            pass            # 로그 가공 실패가 요청을 죽이지 않는다
        return True


def install() -> None:
    """접근 로그를 포함한 주요 로거에 필터를 건다. **여러 번 불러도 안전하다.**"""
    targets = ("uvicorn.access", "uvicorn.error", "uvicorn", "fastapi", "")
    for name in targets:
        lg = logging.getLogger(name)
        if not any(isinstance(f, RedactingFilter) for f in lg.filters):
            lg.addFilter(RedactingFilter())
        # ⚠️ 핸들러에도 건다 — 로거 필터는 **자식 로거로 전파된 레코드에는 적용되지 않는다.**
        for h in lg.handlers:
            if not any(isinstance(f, RedactingFilter) for f in h.filters):
                h.addFilter(RedactingFilter())
