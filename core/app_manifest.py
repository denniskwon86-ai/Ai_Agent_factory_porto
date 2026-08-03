"""[CL-0] App-in-App Capability Manifest — **생성 앱은 자기 로그인을 갖지 않는다.**

## 이 파일이 강제하는 계약

생성된 앱은 플랫폼 안에서 도는 앱이다. 그래서:

- 인증은 **호스트에서 상속**한다(`auth_mode=PLATFORM_INHERITED`).
- 회사 문맥도 호스트가 준다(`enterprise_scope_mode=HOST_CONTEXT`).
- 감사는 플랫폼 원장에 남는다(`audit_mode=PLATFORM_LEDGER`).
- 자체 로그인·사용자 테이블·JWT 발급기는 **금지**다(`forbidden_features`).

⚠️ 왜 값을 고정하는가: 이 셋을 "권장"으로 두면 생성기가 언젠가 자체 로그인을 만든다. 그 앱은
  동작하고 화면도 그럴듯하지만, **회사 권한 체계 밖에서 사용자를 인증**한다 — 조직 범위·등급·
  감사가 전부 우회된다. 이 저장소가 권한 모델을 만드는 데 쓴 모든 통제가 앱 하나로 무력화된다.
  그래서 다른 값은 **거부**한다(경고가 아니라 거부다).

## 문서 불일치를 어떻게 다뤘나 (2026-08-03)

두 기준 문서의 Manifest 모양이 다르다:

- 작업서 §6: `capabilities: ["material_plan.read"]` · `required_data_scopes` · `forbidden_features`
- 도메인 설계 §5.3: `required_capabilities: [{resource, actions}]` · `entrypoints` ·
  `app_class` · `host_auth_required` · `standalone_auth`

작업서가 우선(§2)이므로 **작업서의 필수 필드를 정본**으로 두고, 도메인 설계의 풍부한 형태는
**입력으로 받아 정규화**한다(둘 다 받고 하나로 저장한다). 한쪽을 버리면 그 문서를 따라 만든
호출자가 조용히 실패하고, 새 필드를 지어내면 두 문서 어느 쪽도 아닌 세 번째 형태가 생긴다.
※ 이 판단은 `.agents/TEAM_BOARD.md` 에 기록했다(§13 — 임의로 UX·계약을 바꾸지 않는다).

LLM 0콜.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Tuple

MANIFEST_VERSION = "1.0"

#: 고정값 — 다른 값은 거부한다(위 docstring 의 이유).
AUTH_MODE = "PLATFORM_INHERITED"
SCOPE_MODE = "HOST_CONTEXT"
AUDIT_MODE = "PLATFORM_LEDGER"

#: 앱이 가질 수 없는 기능. **선언에서 빠져 있으면 채워 넣는다**(누락을 허용으로 읽지 않는다).
REQUIRED_FORBIDDEN = ("local_login", "local_user_store", "jwt_issuer")

#: 앱 분류(도메인 §5.3). 모르면 `departmental` 로 두지 않고 비워 둔다 — 추측한 분류는
#: 나중에 권한 판단의 근거로 쓰인다.
APP_CLASSES = ("personal", "departmental", "enterprise")


class ManifestError(ValueError):
    """Manifest 위반 — 4xx 로 전달한다."""


def canonical_json(obj: Any) -> str:
    """정렬된 canonical JSON. **fingerprint 의 입력**이다.

    ⚠️ 키 순서가 다르면 같은 내용이 다른 지문을 갖는다 — 그러면 "Manifest 가 바뀌었다"는 판정이
      거짓이 되고, 아무도 그 판정을 믿지 않게 된다."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(manifest: Dict[str, Any]) -> str:
    """내용 지문(sha256 앞 32자). 릴리스에 저장해 변경을 감지한다."""
    return hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()[:32]


def _normalize_capabilities(raw: Any) -> Tuple[List[str], List[Dict[str, Any]]]:
    """`capabilities` 를 정규화한다. 두 문서의 형태를 **모두** 받는다.

    받는 형태:
      · `["material_plan.read", "arrival.update"]`            (작업서 §6)
      · `[{"resource": "arrival_event", "actions": ["create", "update"]}]` (도메인 §5.3)

    돌려주는 것: (평면 문자열 목록, 구조화 목록). 둘 다 저장한다 — 평면 목록은 비교·검사에
    쓰고, 구조화 목록은 화면이 자원·동작을 나눠 보여줄 때 쓴다.
    ⚠️ 한쪽만 저장하면 나머지를 복원할 때 추측이 끼어든다(`a.b.c` 를 자원·동작으로 쪼개는 규칙을
      지어내게 된다)."""
    flat: List[str] = []
    structured: List[Dict[str, Any]] = []
    if raw is None:
        return flat, structured
    if not isinstance(raw, (list, tuple)):
        raise ManifestError("capabilities 는 목록이어야 합니다.")
    for item in raw:
        if isinstance(item, str):
            s = item.strip()
            if not s:
                continue
            flat.append(s)
            if "." in s:
                res, _, act = s.rpartition(".")
                structured.append({"resource": res, "actions": [act]})
            else:
                # 동작이 없으면 지어내지 않는다 — `read` 를 가정하면 없는 권한을 선언하게 된다.
                structured.append({"resource": s, "actions": []})
        elif isinstance(item, dict):
            res = str(item.get("resource", "")).strip()
            if not res:
                raise ManifestError("capability 항목에 resource 가 없습니다.")
            acts = [str(a).strip() for a in (item.get("actions") or []) if str(a).strip()]
            structured.append({"resource": res, "actions": sorted(set(acts))})
            flat.extend(f"{res}.{a}" for a in sorted(set(acts)))
            if not acts:
                flat.append(res)
        else:
            raise ManifestError(f"capability 항목은 문자열 또는 객체여야 합니다: {item!r}")
    return sorted(set(flat)), structured


def build(capabilities: Any = None, required_data_scopes: Any = None,
          entrypoints: Any = None, app_class: str = "",
          host_auth_required: bool = True, standalone_auth: bool = False,
          extra_forbidden: Any = None) -> Dict[str, Any]:
    """Manifest 를 만든다(고정값은 호출자가 바꿀 수 없다).

    ★ `standalone_auth=True` 나 `host_auth_required=False` 는 **거부**한다 — 그 조합이 바로
      "앱이 자기 로그인을 갖는다"는 선언이다."""
    if standalone_auth:
        raise ManifestError(
            "standalone_auth 는 허용되지 않습니다 — 생성 앱은 호스트 인증을 상속합니다. 앱이 "
            "자체 인증을 가지면 회사 권한 체계 밖에서 사용자를 인증하게 되고, 조직 범위·등급·"
            "감사가 모두 우회됩니다.")
    if not host_auth_required:
        raise ManifestError(
            "host_auth_required=False 는 허용되지 않습니다 — 호스트 인증 없이 도는 앱은 "
            "플랫폼 권한 밖에 있습니다.")
    if app_class and app_class not in APP_CLASSES:
        raise ManifestError(f"app_class 는 {APP_CLASSES} 중 하나여야 합니다: {app_class}")

    flat, structured = _normalize_capabilities(capabilities)
    scopes = sorted({str(s).strip() for s in (required_data_scopes or []) if str(s).strip()})
    eps = []
    for e in (entrypoints or []):
        if not isinstance(e, dict):
            raise ManifestError("entrypoints 항목은 객체여야 합니다.")
        eid = str(e.get("id", "")).strip()
        path = str(e.get("path", "")).strip()
        if not eid or not path:
            raise ManifestError("entrypoint 에는 id 와 path 가 필요합니다.")
        eps.append({"id": eid, "path": path, "purpose": str(e.get("purpose", "")).strip()})

    forbidden = sorted(set(REQUIRED_FORBIDDEN)
                       | {str(f).strip() for f in (extra_forbidden or []) if str(f).strip()})
    return {
        "version": MANIFEST_VERSION,
        "auth_mode": AUTH_MODE,
        "enterprise_scope_mode": SCOPE_MODE,
        "audit_mode": AUDIT_MODE,
        "capabilities": flat,
        "required_capabilities": structured,
        "required_data_scopes": scopes,
        "entrypoints": eps,
        "app_class": app_class,
        "host_auth_required": True,
        "standalone_auth": False,
        "forbidden_features": forbidden,
    }


def minimal() -> Dict[str, Any]:
    """선언이 없는 릴리스에 붙일 **가장 좁은** Manifest.

    ⚠️ 능력을 추측해 채우지 않는다. 빈 `capabilities` 는 "아무 데이터도 요구하지 않는다"는
      뜻이고, 그것이 안전한 방향이다. 반대로 그럴듯한 값을 채우면 **선언하지 않은 권한이 선언된
      것으로** 남고, 이후 판정은 그 거짓 선언을 근거로 삼는다."""
    return build()


def validate(manifest: Any) -> List[str]:
    """위반 목록. **비어 있으면 통과**다(예외를 던지지 않는 판정 — 목록 화면용)."""
    errs: List[str] = []
    if not isinstance(manifest, dict):
        return ["Manifest 가 객체가 아닙니다."]
    for key, want, why in (
        ("auth_mode", AUTH_MODE, "앱은 호스트 인증을 상속해야 합니다"),
        ("enterprise_scope_mode", SCOPE_MODE, "회사 문맥은 호스트가 정합니다"),
        ("audit_mode", AUDIT_MODE, "감사는 플랫폼 원장에 남아야 합니다"),
    ):
        got = manifest.get(key)
        if got != want:
            errs.append(f"{key} 는 '{want}' 여야 합니다(현재 {got!r}) — {why}.")
    if manifest.get("standalone_auth"):
        errs.append("standalone_auth 가 켜져 있습니다 — 앱 자체 인증은 금지입니다.")
    if manifest.get("host_auth_required") is False:
        errs.append("host_auth_required 가 꺼져 있습니다 — 호스트 인증은 필수입니다.")
    missing = [f for f in REQUIRED_FORBIDDEN
               if f not in (manifest.get("forbidden_features") or [])]
    if missing:
        errs.append(f"forbidden_features 에 {missing} 가 없습니다 — 누락은 허용이 아닙니다.")
    if not manifest.get("version"):
        errs.append("version 이 없습니다 — 버전 없는 선언은 비교할 수 없습니다.")
    ac = manifest.get("app_class")
    if ac and ac not in APP_CLASSES:
        errs.append(f"app_class 가 허용값이 아닙니다: {ac!r}")
    # 평면·구조화 능력 목록이 서로 어긋나면 어느 쪽이 진짜인지 알 수 없다.
    flat = set(manifest.get("capabilities") or [])
    from_struct = set()
    for c in (manifest.get("required_capabilities") or []):
        res = str((c or {}).get("resource", "")).strip()
        acts = [str(a).strip() for a in ((c or {}).get("actions") or []) if str(a).strip()]
        from_struct |= ({f"{res}.{a}" for a in acts} if acts else ({res} if res else set()))
    if flat != from_struct:
        errs.append(
            f"capabilities 와 required_capabilities 가 일치하지 않습니다 "
            f"(평면만: {sorted(flat - from_struct)} · 구조화만: {sorted(from_struct - flat)}) — "
            f"두 표현이 갈라지면 어느 쪽이 실제 요구인지 알 수 없습니다.")
    return errs


def assert_valid(manifest: Any) -> Dict[str, Any]:
    """위반이 있으면 던진다. 통과하면 그 Manifest 를 그대로 돌려준다."""
    errs = validate(manifest)
    if errs:
        raise ManifestError(" / ".join(errs))
    return manifest


def snapshot(manifest: Any = None) -> Dict[str, Any]:
    """릴리스에 저장할 형태 — Manifest + 지문 + 검증 결과.

    ★ 지문을 함께 저장하는 이유: 나중에 "전달 시점의 Manifest 와 지금이 같은가"를 물을 수 있어야
      한다. 앱 전달(CL-1)은 이 지문을 복사해 두고, 실행 시점에 릴리스의 지문과 비교한다 —
      다르면 사용자가 수락한 것과 다른 앱이다."""
    m = manifest if isinstance(manifest, dict) and manifest else minimal()
    errs = validate(m)
    return {"manifest": m, "fingerprint": fingerprint(m), "valid": not errs, "errors": errs}
