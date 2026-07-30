"""범위 정책 — **관리자가 화면에서 바꿀 수 있는 값**만 여기 둔다.

## 왜 상수가 아니라 저장소인가 (사용자 결정 2026-07-30)

> "한시 예외 만료일은 우선 설정한 대로 두고 **관리자 페이지에서 admin 이 변경 가능**하도록
>  합시다."

만료일을 코드 상수로 두면 날짜를 하루 미루는 데도 **배포가 필요하다.** 이행 기한은 현업 사정에
따라 조정되는 값이므로, 배포 없이 바꿀 수 있어야 한다 — 그러지 않으면 사람들은 만료일을 아예
없애 버린다(그게 관문 A 가 폐기한 "한시가 영구가 되는" 경로다).

## 지키는 것

1. **기본값은 코드에 남는다.** 저장소가 없거나 깨져도 동작이 멈추지 않는다(코드 기본값으로
   되돌아간다). 정책 파일이 사라졌을 때 "만료 없음"이 되면 안 된다.
2. **변경은 감사에 남는다.** 만료일을 미루는 것은 통제를 느슨하게 하는 결정이다 — 누가 언제
   무엇으로 바꿨는지 없으면 그 결정에 책임자가 없다.
3. **되돌릴 수 있다.** 이전 값을 기록으로 남긴다.
4. **형식을 검증한다.** `YYYY-MM-DD` 가 아니면 거부한다 — 잘못된 형식은 문자열 비교에서
   **조용히 항상 만료**(또는 항상 유효)로 동작한다.

LLM 0콜.
"""
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

_POLICY_PATH = os.path.join("data", "scope_policy.json")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ScopePolicyError(ValueError):
    """정책 값 검증 실패 — 4xx 로 전달한다."""


def _read() -> Dict[str, Any]:
    try:
        with open(_POLICY_PATH, "r", encoding="utf-8") as f:
            doc = json.load(f)
        return doc if isinstance(doc, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}                                  # 없거나 깨졌으면 코드 기본값으로


def _write(doc: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_POLICY_PATH) or ".", exist_ok=True)
    with open(_POLICY_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


def legacy_deadline_default() -> str:
    """코드에 박힌 기본 만료일. 저장소가 비면 이 값을 쓴다."""
    from core.enterprise_context.scoping import LEGACY_GRANDFATHER_UNTIL
    return LEGACY_GRANDFATHER_UNTIL


def legacy_deadline() -> str:
    """현재 적용 중인 한시 예외 만료일. **호출 시점에** 읽는다.

    ★ 캐시하면 관리자가 바꿔도 프로세스를 재시작해야 한다 — 화면에서 바꿀 수 있게 만든 취지가
      사라진다(되돌릴 수 없는 되돌림 장치와 같은 실수)."""
    v = str(_read().get("legacy_grandfather_until", "") or "").strip()
    return v if _DATE_RE.match(v) else legacy_deadline_default()


def set_legacy_deadline(value: str, actor: str, reason: str = "") -> Dict[str, Any]:
    """만료일을 바꾼다(관리자 전용 — 권한 검사는 API 계층).

    ⚠️ 형식을 검증한다. 만료 판정은 문자열 비교(`today > deadline`)이므로, 형식이 깨지면
      **조용히 항상 만료**(또는 항상 유효)가 된다 — 통제가 꺼진 것을 아무도 모른다."""
    v = (value or "").strip()
    if not _DATE_RE.match(v):
        raise ScopePolicyError(
            f"만료일 형식이 잘못됐습니다: {value!r} — `YYYY-MM-DD` 여야 합니다. "
            f"만료 판정은 문자열 비교라, 형식이 깨지면 통제가 조용히 꺼집니다.")
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise ScopePolicyError(f"존재하지 않는 날짜입니다: {v}")
    if not (actor or "").strip():
        raise ScopePolicyError(
            "변경자 식별 정보가 없습니다 — 만료일을 미루는 것은 통제를 느슨하게 하는 결정이고, "
            "책임자 없는 결정은 감사에서 근거가 되지 못합니다.")

    doc = _read()
    before = str(doc.get("legacy_grandfather_until", "") or "") or legacy_deadline_default()
    doc["legacy_grandfather_until"] = v
    doc.setdefault("history", []).append({
        "from": before, "to": v, "actor": actor.strip(), "reason": reason or "",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    doc["history"] = doc["history"][-50:]          # 최근 50건만(파일이 무한히 자라지 않게)
    _write(doc)

    try:
        from core.enterprise_context import audit
        audit.record(audit.SCOPE_BINDING_CHANGED, resource_type="scope_policy",
                     resource_id="legacy_grandfather_until", actor=actor.strip(),
                     outcome="allowed", reason=reason or "한시 예외 만료일 변경",
                     detail=f"{before} -> {v}")
    except Exception as e:                                       # pragma: no cover
        print(f"⚠️ [scope_policy] 감사 기록 실패: {e}")

    later = v > before
    return {
        "legacy_grandfather_until": v, "previous": before, "actor": actor.strip(),
        "default": legacy_deadline_default(),
        "note": (("⚠️ 만료일을 **미뤘습니다** — 그동안 범위 미지정 데이터가 계속 전 조직에 "
                  "보입니다. 이행이 끝나면 다시 당기십시오."
                  if later else
                  "만료일을 앞당겼습니다 — 그 날짜 이후 범위 미지정 데이터는 조회에서 "
                  "제외됩니다. 사라질 건수는 `coverage()` 로 먼저 확인하십시오.")),
    }


def policy() -> Dict[str, Any]:
    """현재 정책 + 변경 이력(관리자 화면용)."""
    doc = _read()
    cur = legacy_deadline()
    return {
        "legacy_grandfather_until": cur,
        "default": legacy_deadline_default(),
        "is_default": cur == legacy_deadline_default(),
        "history": list(reversed(doc.get("history", [])))[:20],
        "note": ("한시 예외 만료일입니다. 이 날짜가 지나면 범위 미지정(`LEGACY_UNSCOPED`) "
                 "데이터는 조회에서 제외됩니다 — 그전에 소유 조직을 지정하거나 승인된 전사 "
                 "공용으로 전환하십시오."),
    }
