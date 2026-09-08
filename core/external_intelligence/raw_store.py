"""[DAO-1] 원문 보관소 — 「그때 원천이 실제로 뭐라고 답했나」를 지운 적이 없게 한다.

설계서 §6.2 가 요구하는 질문은 하나다.

> "2026년 12월 15일 실행한 A공장 손익 시뮬레이션은, 어떤 환율·원자재 가격·전력비 가정·
>  사내 실적을 사용했는가?"

이 질문의 마지막 고리가 여기다. `simulation_run → snapshot → observation → **raw_object** →
source` 에서 `raw_object` 가 없으면, 정규화가 틀렸을 때 무엇이 틀렸는지 **영원히 알 수 없다.**
값만 남기면 「우리 파서가 이렇게 읽었다」만 남고 「원천이 이렇게 말했다」는 사라진다.

## 내용 주소(content-addressed)로 두는 이유

파일 이름이 곧 내용의 SHA-256 이다. 그래서:

  · **재수집이 저절로 드러난다.** 같은 응답을 다시 받으면 같은 경로가 나오고, 덮어쓸 것이 없다.
    「몇 번 받았나」를 따로 세지 않아도 된다.
  · **조용한 변조가 불가능하다.** 파일을 고치면 이름과 내용이 어긋난다(`verify()` 가 잡는다).
  · 원천이 값을 **정정 공표**하면 내용이 달라지므로 새 파일이 된다 — 옛 판이 남는다.

## ★★★ 비밀키는 «적지 않기» 로 막지 않는다

지시 12 의 「API 키가 포함된 URL 로그 금지」를 주석으로 적어 두면 지켜지지 않는다. 이 저장소는
그 유형을 이미 겪었다(「고지문은 차단기가 아니다」 — 검사기는 있는데 부르는 곳이 0곳이었다).

그래서 여기서는 **값 기반으로 지우고, 지워졌는지 다시 확인한 뒤에 쓴다.** 남아 있으면
`SecretLeakError` 를 던지고 **파일을 만들지 않는다.**

⚠️⚠️ 이름 기반(`?api_key=` 를 찾아 지우기)만으로는 부족하다. 한국은행 ECOS 는 키를 **경로
  세그먼트**에 둔다: `https://ecos.bok.or.kr/api/StatisticSearch/<KEY>/json/kr/...`.
  질의 문자열만 보는 검사기는 이것을 통과시킨다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, quote, quote_plus, unquote, urlencode, urlsplit, urlunsplit

from core.paths import data_path

REDACTED = "***"

#: 이름만 보고도 비밀임을 아는 질의 인자. 값 기반 삭제의 **두 번째 그물**이다 —
#: 호출부가 비밀값 목록을 넘기지 않았을 때를 대비한다.
_SECRET_PARAM_NAMES = re.compile(
    r"(^|_)(key|apikey|api_key|servicekey|service_key|authkey|auth_key|crtfc_key|"
    r"token|access_token|secret|password|passwd|pwd|signature|sig)$",
    re.IGNORECASE,
)

#: 비밀값으로 취급할 최소 길이. 짧은 값을 지우면 URL 이 알아볼 수 없게 된다.
_MIN_SECRET_LEN = 8

_EXT_BY_TYPE = {
    "application/json": ".json",
    "text/json": ".json",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "text/csv": ".csv",
    #: ★ 다섯째 원천이 처음으로 «바이너리»를 보낸다. 없으면 `.bin` 으로 떨어져
    #:   사람이 보관된 원문을 열어 볼 수 없다(재현에는 무해하지만 불편하다).
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "text/plain": ".txt",
    "text/html": ".html",
    "application/zip": ".zip",
    "application/octet-stream": ".bin",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}


class RawStoreError(ValueError):
    """보관소 사용 오류 — 4xx 로 전달한다."""


class SecretLeakError(RawStoreError):
    """★★★ 비밀값이 기록될 뻔했다. **쓰기를 중단한다** — 경고로 넘기지 않는다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_secrets(secrets: Optional[Iterable[str]]) -> Tuple[str, ...]:
    """빈 값·너무 짧은 값을 걸러 낸다. 긴 것부터 지워야 부분 문자열이 남지 않는다."""
    out = {s for s in (str(x or "").strip() for x in (secrets or ())) if len(s) >= _MIN_SECRET_LEN}
    return tuple(sorted(out, key=len, reverse=True))


def _secret_forms(value: str) -> Tuple[str, ...]:
    """한 비밀값이 문자열에 나타날 수 있는 **모든 표기**.

    ⚠️⚠️ 이 함수가 없을 때 실제로 뚫렸다. 비밀값이 이미 퍼센트 인코딩된 채(`abc%2Fdef`)
      목록 밖 이름의 인자에 들어오면, 값 기반 삭제는 원문(`abc/def`)을 찾아 못 찾고
      이름 기반 삭제는 이름을 몰라 지나친다. 그대로 디스크에 적힌다."""
    forms = {value, quote(value, safe=""), quote_plus(value), quote(value)}
    return tuple(f for f in forms if f)


def redact(text: str, secrets: Optional[Iterable[str]] = None) -> str:
    """문자열에서 비밀값을 지운다. **URL 이 아닌 본문에도 쓴다**(오류 메시지가 키를 담는다)."""
    out = str(text or "")
    for s in _clean_secrets(secrets):
        for form in sorted(_secret_forms(s), key=len, reverse=True):
            out = out.replace(form, REDACTED)
    return out


def redact_url(url: str, secrets: Optional[Iterable[str]] = None) -> str:
    """URL 에서 비밀을 지운다 — **값 기반과 이름 기반을 둘 다** 적용한다.

    ⚠️ 경로 세그먼트도 본다. ECOS 처럼 키를 경로에 두는 원천이 있고, 질의 문자열만 보는
      검사기는 그것을 통과시킨다."""
    raw = str(url or "")
    if not raw:
        return ""
    # ① 값 기반 — 어디에 있든, **어느 표기로든** 지운다(원문·퍼센트 인코딩·`+` 인코딩).
    raw = redact(raw, secrets)
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw
    # ② 이름 기반(질의 인자) — 호출부가 목록을 안 줬을 때의 그물.
    if parts.query:
        pairs = [(k, REDACTED if _SECRET_PARAM_NAMES.search(k) else v)
                 for k, v in parse_qsl(parts.query, keep_blank_values=True)]
        parts = parts._replace(query=urlencode(pairs))
    return urlunsplit(parts)


def assert_no_secret(text: str, secrets: Optional[Iterable[str]], *, where: str) -> None:
    """★★★ 지웠다고 믿지 않고 **확인한다.** 이것이 이 파일의 차단기다.

    ⚠️ **디코드한 형태로도** 본다. 인코딩된 채 남은 값은 그대로 적혀도 읽는 쪽이 한 번만
      디코드하면 원래 키가 된다 — 「보이지 않으니 없다」가 아니다."""
    body = str(text or "")
    try:
        decoded = unquote(body)
    except (ValueError, UnicodeDecodeError):
        decoded = body
    for s in _clean_secrets(secrets):
        if s in body or s in decoded:
            raise SecretLeakError(
                f"{where} 에 비밀값이 남아 있어 기록을 중단했습니다. "
                f"(길이 {len(s)}자 값 — 내용은 표시하지 않습니다)")


def _as_bytes(payload: Any) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, bytearray):
        return bytes(payload)
    if isinstance(payload, str):
        return payload.encode("utf-8")
    raise RawStoreError(f"원문은 bytes 또는 str 이어야 합니다: {type(payload).__name__}")


def _safe_segment(value: str, *, field: str) -> str:
    """경로에 쓸 수 있는 조각인지 본다. `..` 이나 구분자가 들어오면 보관소 밖으로 나간다."""
    v = str(value or "").strip()
    if not v:
        raise RawStoreError(f"{field} 가 비어 있습니다.")
    if v in (".", "..") or not re.fullmatch(r"[A-Za-z0-9_.:@+-]{1,120}", v):
        raise RawStoreError(f"{field} 에 경로로 쓸 수 없는 값이 들어왔습니다: {v!r}")
    return v


class RawStore:
    """원문 보관소. **DB 를 쓰지 않는다** — 파일과 그 옆의 메타뿐이다.

    ⚠️ 운영 DB 에 원문을 넣지 않는 것은 설계서 §5.1 의 경계다(`pipeline_state.db` 에 외부
      관측값 원문을 저장하지 않는다). 파일로 두면 크기가 DB 성능을 건드리지 않고,
      백업·보존 기간을 파일 단위로 다룰 수 있다."""

    def __init__(self, root: Optional[str] = None):
        self.root = str(root or data_path("external_raw"))

    # ── 쓰기 ─────────────────────────────────────────────────────────────
    def put(self, payload: Any, *, source_id: str, requested_url: str = "",
            content_type: str = "application/octet-stream", job_id: str = "",
            secrets: Optional[Sequence[str]] = None,
            fetched_at: str = "", note: str = "") -> Dict[str, Any]:
        """원문 한 덩이를 보관한다. 같은 내용이면 **다시 쓰지 않고** 기존 참조를 돌려준다."""
        src = _safe_segment(source_id, field="source_id")
        body = _as_bytes(payload)
        if not body:
            raise RawStoreError("빈 응답은 보관하지 않습니다 — 「자료 없음」은 상태로 기록합니다.")

        digest = hashlib.sha256(body).hexdigest()
        safe_url = redact_url(requested_url, secrets)
        safe_note = redact(note, secrets)
        # ★★★ 쓰기 직전에 확인한다. 지웠다는 믿음이 아니라 검사가 통과 조건이다.
        assert_no_secret(safe_url, secrets, where="요청 URL")
        assert_no_secret(safe_note, secrets, where="비고")

        rel_dir = f"{src}/{digest[:2]}"
        ext = _EXT_BY_TYPE.get(str(content_type or "").split(";")[0].strip().lower(), ".bin")
        rel_obj = f"{rel_dir}/{digest}{ext}"
        abs_obj = os.path.join(self.root, src, digest[:2], digest + ext)
        abs_meta = abs_obj + ".meta.json"

        duplicate = os.path.exists(abs_obj)
        if not duplicate:
            os.makedirs(os.path.dirname(abs_obj), exist_ok=True)
            tmp = abs_obj + ".part"
            with open(tmp, "wb") as f:
                f.write(body)
            os.replace(tmp, abs_obj)

        meta = {
            "raw_object_ref": rel_obj,
            "checksum": digest,
            "algorithm": "sha256",
            "source_id": src,
            "job_id": str(job_id or ""),
            "requested_url": safe_url,
            "content_type": str(content_type or ""),
            "byte_size": len(body),
            "fetched_at": str(fetched_at or _now()),
            "stored_at": _now(),
            "note": safe_note,
        }
        if duplicate:
            # 이미 있는 원문의 메타는 **덮어쓰지 않는다** — 최초 수집 시각이 계보의 근거다.
            existing = self._read_meta(abs_meta)
            if existing:
                existing["last_seen_at"] = meta["stored_at"]
                existing["seen_count"] = int(existing.get("seen_count", 1)) + 1
                self._write_meta(abs_meta, existing)
                return dict(existing, duplicate=True)
        meta["seen_count"] = 1
        self._write_meta(abs_meta, meta)
        return dict(meta, duplicate=duplicate)

    @staticmethod
    def _write_meta(path: str, meta: Dict[str, Any]) -> None:
        tmp = path + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, path)

    @staticmethod
    def _read_meta(path: str) -> Optional[Dict[str, Any]]:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    # ── 읽기 ─────────────────────────────────────────────────────────────
    def _abs(self, ref: str) -> str:
        rel = str(ref or "").strip().replace("\\", "/")
        if not rel:
            raise RawStoreError("원문 참조가 비어 있습니다.")
        root = os.path.abspath(self.root)
        target = os.path.abspath(os.path.join(root, rel))
        # ⚠️ `..` 로 보관소 밖을 읽지 못하게 한다. 참조는 DB 를 거쳐 오므로 신뢰하지 않는다.
        if os.path.commonpath([root, target]) != root:
            raise RawStoreError(f"보관소 밖의 경로입니다: {rel}")
        return target

    def read(self, ref: str) -> bytes:
        with open(self._abs(ref), "rb") as f:
            return f.read()

    def meta(self, ref: str) -> Optional[Dict[str, Any]]:
        return self._read_meta(self._abs(ref) + ".meta.json")

    def exists(self, ref: str) -> bool:
        try:
            return os.path.exists(self._abs(ref))
        except (RawStoreError, ValueError):
            return False

    def verify(self, ref: str) -> Dict[str, Any]:
        """파일 이름(=체크섬)과 내용이 여전히 일치하는지. **조용한 변조를 잡는다.**"""
        abs_obj = self._abs(ref)
        if not os.path.exists(abs_obj):
            return {"ok": False, "reason": "MISSING", "raw_object_ref": ref}
        with open(abs_obj, "rb") as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        expected = os.path.basename(abs_obj).split(".")[0]
        return {"ok": actual == expected, "raw_object_ref": ref,
                "expected": expected, "actual": actual,
                "reason": "" if actual == expected else "CHECKSUM_MISMATCH"}

    def find_by_checksum(self, source_id: str, checksum: str) -> Optional[str]:
        """이미 받아 둔 응답인가. **재수집 방지**의 판정자다."""
        src = _safe_segment(source_id, field="source_id")
        digest = str(checksum or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RawStoreError(f"sha256 체크섬이 아닙니다: {checksum!r}")
        folder = os.path.join(self.root, src, digest[:2])
        if not os.path.isdir(folder):
            return None
        for name in sorted(os.listdir(folder)):
            if name.startswith(digest) and not name.endswith((".meta.json", ".part")):
                return f"{src}/{digest[:2]}/{name}"
        return None


raw_store = RawStore()
