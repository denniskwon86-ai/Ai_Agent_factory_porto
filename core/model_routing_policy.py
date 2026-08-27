"""모델 라우팅 정책 — **관리자가 화면에서 바꿀 수 있는 값**만 여기 둔다. (2026-08-27)

## 왜 상수가 아니라 저장소인가

`config.OPENROUTER_ONLY` 는 **코드 상수**다. 그 말은 모드를 켜고 끄는 데 배포가 필요하다는
뜻이고, 그러면 사람들은 아예 안 끄거나(비용이 계속 나감) 아예 안 켠다(쿼터가 계속 터짐).
`core/scope_policy.py` 가 한시 예외 만료일을 두고 내린 것과 같은 결론이다.

## 우선순위 — 셋이 겹친다

    ① 환경변수 `AFS_OPENROUTER_ONLY`   ← 가장 세다(운영자가 서버 기동 시 못 박은 값)
    ② 이 저장소(화면에서 바꾼 값)
    ③ `config.OPENROUTER_ONLY`         ← 코드 기본값

⚠️⚠️ **①이 있으면 화면은 그 사실을 말해야 한다.** 그러지 않으면 관리자가 스위치를 내리고
  「껐다」고 믿는데 서버는 계속 켜진 채로 돈다 — 그리고 화면만 보고는 알 수 없다.
  그래서 `effective()` 는 값만이 아니라 **누가 이겼는지**를 함께 돌려준다.

## 지키는 것 (scope_policy 와 같은 규약)

  1. **기본값은 코드에 남는다.** 저장소가 없거나 깨져도 동작이 멈추지 않는다.
  2. **변경은 감사에 남는다.** 모델을 바꾸는 것은 비용과 품질을 함께 바꾸는 결정이다.
  3. **되돌릴 수 있다.** 이전 값을 이력으로 남긴다.
  4. **호출 시점에 읽는다.** 캐시하면 화면에서 바꿔도 재시작해야 한다.

LLM 0콜.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.paths import data_path

_PATH = data_path("model_routing_policy.json")

#: 우선순위 출처 이름 — 화면이 그대로 보여 준다.
SOURCE_ENV = "env"
SOURCE_STORE = "store"
SOURCE_CODE = "code"

_ENV_KEY = "AFS_OPENROUTER_ONLY"
_TRUE = ("1", "true", "on", "yes")
_FALSE = ("0", "false", "off", "no")


class ModelRoutingError(ValueError):
    """정책 값 검증 실패 — 4xx 로 전달한다."""


def _read() -> Dict[str, Any]:
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            doc = json.load(f)
        return doc if isinstance(doc, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}                                  # 없거나 깨졌으면 코드 기본값으로


def _write(doc: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


def _env_value() -> Optional[bool]:
    """환경변수가 정한 값. **정하지 않았으면 `None`** — `False` 와 구분한다.

    ⚠️ 여기서 `False` 로 뭉개면 「환경변수 없음」이 「환경변수가 끄라고 했음」이 되고,
      저장소 값이 영영 안 먹는다."""
    raw = (os.environ.get(_ENV_KEY) or "").strip().lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    return None


def _code_default() -> bool:
    import config
    return bool(getattr(config, "OPENROUTER_ONLY", False))


def _stored() -> Optional[bool]:
    v = _read().get("openrouter_only")
    return bool(v) if isinstance(v, bool) else None


def effective() -> Dict[str, Any]:
    """지금 실제로 적용되는 값과 **누가 이겼는지.**

    ★ 화면은 `enabled` 만이 아니라 `source` 를 함께 그려야 한다 — 안 그리면 관리자가
      스위치를 내리고 「껐다」고 믿는데 환경변수가 계속 켜 두는 상태를 볼 수 없다."""
    env, store, code = _env_value(), _stored(), _code_default()
    if env is not None:
        enabled, source = env, SOURCE_ENV
    elif store is not None:
        enabled, source = store, SOURCE_STORE
    else:
        enabled, source = code, SOURCE_CODE
    return {
        "enabled": enabled,
        "source": source,
        #: 화면이 「내가 바꾼 값이 무시되고 있다」를 그릴 수 있도록 셋을 다 준다.
        "env_value": env, "stored_value": store, "code_default": code,
        "env_key": _ENV_KEY,
        "overridden": source == SOURCE_ENV and store is not None and store != env,
    }


def enabled() -> bool:
    """`llm_gateway` 가 부르는 자리. **호출 시점에** 읽는다."""
    return bool(effective()["enabled"])


def chains() -> Dict[str, Any]:
    """전용 모드에서 쓸 체인. 지금은 코드 상수만 — 화면에서 바꾸는 것은 별건이다.

    ⚠️ 「나중에 화면에서 슬러그도 바꾸게 하자」를 미리 열어 두지 않는다. 저장 경로 없는
      입력란을 그리면 사용자는 입력하고 저장된 줄 안다(`AdminConsolePanel` 의 기존 규율)."""
    import config
    return {
        "pro": list(getattr(config, "OPENROUTER_ONLY_PRO_CHAIN", [])),
        "flash": list(getattr(config, "OPENROUTER_ONLY_FLASH_CHAIN", [])),
    }


def history(limit: int = 20) -> list:
    rows = _read().get("history") or []
    return rows[-limit:][::-1] if isinstance(rows, list) else []


def set_openrouter_only(value: bool, actor: str, reason: str = "") -> Dict[str, Any]:
    """모드를 바꾼다(관리자 전용 — 권한 검사는 API 계층).

    ⚠️ 켜는 것과 끄는 것 **둘 다** 결과가 있다:
      · 켜면 무료 쿼터를 안 쓰는 대신 **비용이 나간다.**
      · 끄면 비용이 0 이 되는 대신 **429 쿼터 소진이 돌아온다**(실측 190건 중 130건).
    ★ 그래서 어느 쪽이든 `note` 로 그 사실을 화면에 돌려준다 — 「눌렀더니 조용히 됐다」는
      결정자에게 아무것도 알려 주지 않는다."""
    if not isinstance(value, bool):
        raise ModelRoutingError(f"참/거짓이어야 합니다: {value!r}")
    if not (actor or "").strip():
        raise ModelRoutingError(
            "변경자 식별 정보가 없습니다 — 모델을 바꾸는 것은 비용과 품질을 함께 바꾸는 "
            "결정이고, 책임자 없는 결정은 감사에서 근거가 되지 못합니다.")
    #: ★★★ [2026-08-27 실측] **사유는 서버가 막는다.**
    #:
    #: ⚠️⚠️ 화면에만 `required` 를 걸어 두고 여기서 안 막았더니, API 를 직접 부르는 경로로
    #:   사유 없이 200 이 났고 **이력에 빈 사유 한 줄이 남았다**(실제로 남겼다).
    #:   화면이 지키는 통제는 화면을 거치지 않는 순간 사라진다 —
    #:   통제는 자기가 막을 것에 기대면 안 된다.
    #: ⚠️ `scope_policy.set_app_pdp_enforce` 는 **느슨해지는 방향에만** 사유를 요구한다.
    #:   여기서는 **양방향** 다 요구한다. 켜면 실제 돈이 나가고, 끄면 완주를 막던 쿼터
    #:   소진이 돌아온다 — 어느 쪽도 「기본값이라 안전한」 방향이 아니기 때문이다.
    if not (reason or "").strip():
        raise ModelRoutingError(
            "사유가 필요합니다 — 켜면 호출마다 과금되고, 끄면 완주를 반복 실패시킨 "
            "429 쿼터 소진이 돌아옵니다. 어느 쪽도 «그냥 기본값» 이 아니므로, 되돌릴 때 "
            "«왜 바꿨는가» 가 남아야 합니다.")

    before = effective()
    doc = _read()
    doc["openrouter_only"] = value
    doc.setdefault("history", []).append({
        "from": before["enabled"], "to": value, "actor": actor.strip(),
        "reason": reason or "",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    doc["history"] = doc["history"][-50:]
    _write(doc)

    try:
        from core.enterprise_context import audit
        audit.record(audit.SCOPE_BINDING_CHANGED, resource_type="model_routing_policy",
                     resource_id="openrouter_only", actor=actor.strip(),
                     outcome="allowed",
                     reason=reason or ("OpenRouter 전용 모드 켬" if value else "끔"),
                     detail=f"{before['enabled']} -> {value}")
    except Exception as e:                                       # pragma: no cover
        print(f"⚠️ [model_routing_policy] 감사 기록 실패: {e}")

    after = effective()
    #: ⚠️ [2026-08-27 화면 실측] **마크다운을 쓰지 않는다.** 화면의 `Banner` 는 평문을
    #:   그리므로 `**강조**` 가 별표째로 보인다. 눌러 보고 잡았다 — 서버가 화면의 렌더링
    #:   방식을 가정하면 그 가정이 틀렸을 때 사용자가 별표를 읽는다.
    notes = []
    if value:
        notes.append("OpenRouter 유료 모델만 씁니다 — 무료 쿼터 소진(실측 429 130건)이 "
                     "사라지는 대신 비용이 발생합니다.")
    else:
        notes.append("무료 티어 폴백 체인으로 돌아갑니다 — 비용이 0 이 되는 대신 "
                     "429 쿼터 소진이 돌아옵니다(실측 폴백 실패 190건 중 130건).")
    #: ⚠️⚠️ 저장은 됐는데 **안 먹는** 경우를 반드시 말한다.
    if after["source"] == SOURCE_ENV and after["enabled"] != value:
        notes.append(f"⚠️ 다만 지금은 적용되지 않습니다 — 환경변수 {_ENV_KEY} 가 "
                     f"«{os.environ.get(_ENV_KEY)}» 로 설정돼 있어 그쪽이 이깁니다. "
                     f"서버를 그 변수 없이 다시 띄워야 이 설정이 적용됩니다.")
    return {**after, "previous": before["enabled"], "actor": actor.strip(),
            "note": " ".join(notes)}
