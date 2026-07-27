# ==========================================
# 업무표준(Work Standard) — 에이전트의 '법규·사규'
# ==========================================
# ⚠️ 왜 만드는가:
#   에이전트가 "나는 어떤 기준으로 일하고 무엇을 확인한 뒤 다음으로 넘겨야 하는가"를
#   **코드에 박힌 상수**가 아니라 **관리되는 기준정보**에서 조회하게 한다.
#
#   기존에는 판정 기준이 `criteria.py` 의 파이썬 딕셔너리에 하드코딩되어 있었다. 그래서
#     · 기준을 바꾸려면 코드를 고치고 배포해야 했고
#     · 언제 누가 왜 바꿨는지 이력이 남지 않았으며
#     · 에이전트 자신은 자기 판정 기준이 무엇인지 **프롬프트에서 알 수 없었다**
#       (실측: 리뷰어가 자기 역할을 '품질 수문장'으로 알고 코드 품질로 반려했고,
#        QA·Supervisor 도 각자 임의 기준으로 판정해 완주를 막았다).
#
#   → `master.db` 의 `master_records` 에 등록한다. 이 테이블은 이미
#     PK(master_code, version) · valid_from/valid_to · supersedes · 소프트 폐지를 갖고 있어
#     **법규 개정 의미론**(개정 시 새 버전, 구판은 리니지로 보존, 시행일 관리)이 그대로 성립한다.
#     새 저장소를 만들지 않는다 — '한 판' 철학.
#
# 조회 우선순위: master.db 등록본 → 없으면 `criteria.py` 폴백(하위호환).
# ==========================================
import json
from typing import Any, Dict, Optional

# ── 분류 구분 ────────────────────────────────────────────────────────────────
# 에이전트는 두 부류이고, **따라야 할 것의 성격이 다르다.**
#
#   ① 판정 에이전트(Reviewer·QA·Supervisor·PMO) → **규정(regulation)**
#      앞 단계 산출물을 받아 통과/반려를 정한다. 필요한 것은 '무엇을 어떤 기준값으로
#      판정하는가'다. 엄격하게 따라야 하며 임의 해석의 여지를 남기면 안 된다
#      (실측: 기준이 불명확해 리뷰어가 코드 품질로, QA·Supervisor 가 각자 잣대로 반려했다).
#
#   ② 생성 에이전트(RFP·PM·Architect·Tech Lead·개발자·UI) → **지침(guideline)**
#      산출물을 만든다. 판정 권한이 없다. 필요한 것은 '어떻게 작성하는가' —
#      필수 포함 항목, 작성 원칙, 하지 말아야 할 것. 자기 산출물의 자가 점검 기준은
#      부수적이며, 통과/반려를 남에게 행사하지 않는다.
#
# 두 부류를 한 분류에 섞으면 지침을 규정처럼 강제하거나(생성이 막힘) 규정을 지침처럼
# 느슨하게 쓰게 된다(가짜 통과). 그래서 `entity_types` 를 나눈다.
WORK_REGULATION_TYPE = "work_regulation"   # 규정 — 판정 에이전트
WORK_GUIDELINE_TYPE = "work_guideline"     # 지침 — 생성 에이전트

# 하위호환: 초기 구현에서 쓰던 단일 분류명(현재는 두 분류로 분리됨)
WORK_STANDARD_TYPE = WORK_REGULATION_TYPE

KIND_REGULATION = "regulation"
KIND_GUIDELINE = "guideline"

_CODE_PREFIX = "STD-"


def standard_code(stage: str) -> str:
    """단계 키 → 표준 문서 코드. 예: CODE_REVIEW → STD-CODE_REVIEW"""
    return f"{_CODE_PREFIX}{str(stage or '').strip().upper()}"


def _fallback_rubric(stage: str) -> Optional[Dict[str, Any]]:
    """등록본이 없을 때 코드에 박힌 기본값(하위호환). 시드 전이나 DB 장애 시 경로."""
    try:
        from criteria import STAGE_RUBRICS
        return STAGE_RUBRICS.get(stage)
    except Exception:
        return None


def get_standard(stage: str) -> Optional[Dict[str, Any]]:
    """해당 단계의 **현행** 업무표준을 돌려준다(폐지된 구판은 제외).

    반환 형식은 `criteria.py` 루브릭과 호환된다 — checks/pass_threshold/hard_fail_checks 등.
    추가로 `_meta` 에 출처(registered/fallback)와 버전을 담아 호출부가 구분할 수 있게 한다."""
    try:
        from core.master_data import master_data
        rec = master_data.get_record(standard_code(stage))
    except Exception:
        rec = None

    if rec and str(rec.get("status", "")) == "active":
        try:
            attrs = rec.get("attributes")
            if isinstance(attrs, str):
                attrs = json.loads(attrs or "{}")
            if isinstance(attrs, dict) and attrs.get("checks"):
                out = dict(attrs)
                out["_meta"] = {
                    "source": "registered",
                    "master_code": rec.get("master_code"),
                    "version": rec.get("version"),
                    "valid_from": rec.get("valid_from"),
                    "name": rec.get("name"),
                }
                return out
        except Exception:
            pass   # 등록본이 깨졌으면 조용히 폴백 — 판정 자체가 멈추면 안 된다

    fb = _fallback_rubric(stage)
    if fb is None:
        return None
    out = dict(fb)
    out["_meta"] = {"source": "fallback", "master_code": standard_code(stage), "version": 0}
    return out


def render_standard_brief(stage: str) -> str:
    """에이전트 프롬프트에 주입할 **자연어 업무표준 고지문**.

    "우리 시스템의 업무표준에 따르면 당신은 ~를 이런 기준으로 평가해야 한다" 형태로,
    에이전트가 자기 판정 근거를 **명시적으로** 알고 일하게 한다."""
    std = get_standard(stage)
    if not std:
        return ""
    meta = std.get("_meta", {}) or {}
    code = meta.get("master_code", standard_code(stage))
    ver = meta.get("version", 0)
    src = "등록 표준" if meta.get("source") == "registered" else "기본 표준(미등록)"

    kind = std.get("standard_kind", KIND_REGULATION)

    # ── 지침(생성 에이전트) — 판정 기준이 아니라 '어떻게 작성하는가' ──────────
    if kind == KIND_GUIDELINE:
        lines = [f"\n\n[📗 업무지침 {code} (v{ver}, {src}) — 당신이 따라야 할 작성 표준]"]
        if std.get("role_statement"):
            lines.append(f"· 당신의 역할: {std['role_statement']}")
        if std.get("inputs"):
            lines.append(f"· 입력(근거로 삼을 것): {std['inputs']}")
        if std.get("deliverable"):
            lines.append(f"· 산출물: {std['deliverable']}")
        if std.get("must_include"):
            lines.append("· 반드시 포함할 것:")
            for m in std["must_include"]:
                lines.append(f"   - {m}")
        if std.get("principles"):
            lines.append("· 작성 원칙:")
            for m in std["principles"]:
                lines.append(f"   - {m}")
        for m in (std.get("must_not") or []):
            lines.append(f"· ⚠️ 금지: {m}")
        gate = [c for c in std.get("checks", []) if not c.get("advisory")]
        if gate:
            lines.append("· 자가 점검(이 기준으로 당신의 산출물이 채점됩니다): "
                         + ", ".join(f"{c['id']}" for c in gate))
        lines.append("· ⚠️ 당신에게는 **통과/반려 권한이 없습니다.** 판정은 판정 담당 에이전트의 몫입니다.")
        return "\n".join(lines)

    # ── 규정(판정 에이전트) — 통과/반려 기준 ────────────────────────────────
    lines = [
        f"\n\n[📜 업무규정 {code} (v{ver}, {src}) — 당신이 따라야 할 판정 기준]",
    ]
    if std.get("role_statement"):
        lines.append(f"· 당신의 역할: {std['role_statement']}")
    if std.get("evaluates"):
        lines.append(f"· 평가 대상: {std['evaluates']}")

    gate = [c for c in std.get("checks", []) if not c.get("advisory")]
    adv = [c for c in std.get("checks", []) if c.get("advisory")]
    if gate:
        lines.append("· **통과/반려를 결정하는 항목**(이것만이 반려 사유입니다):")
        for c in gate:
            hard = " ⛔하드실패" if c["id"] in (std.get("hard_fail_checks") or []) else ""
            lines.append(f"   - {c['id']}(가중치 {c.get('weight', 1)}){hard}: {c.get('desc', '')}")
        gw = sum(float(c.get("weight", 1)) for c in gate)
        th = float(std.get("pass_threshold", 0.7))
        lines.append(f"   → 통과선: {th * gw:.1f}점 / {gw:.0f}점 (임계 {th})")
    else:
        lines.append("· **이 단계는 관문이 아닙니다.** 반려 권한이 없으며 권고 의견만 남깁니다.")
    if adv:
        lines.append("· 참고 항목(**반려 사유가 아님** — 리포트로만 남기십시오): "
                     + ", ".join(c["id"] for c in adv))
    for m in (std.get("must_not") or []):
        lines.append(f"· ⚠️ 금지: {m}")
    return "\n".join(lines)


def register_standard(stage: str, name: str, payload: Dict[str, Any],
                      kind: str = KIND_REGULATION,
                      valid_from: str = None, source: str = "system") -> Dict[str, Any]:
    """업무표준을 등록/개정한다. 같은 코드가 있으면 **새 버전**이 되고 구판은 리니지로 보존된다.

    kind: `regulation`(판정 에이전트의 규정) | `guideline`(생성 에이전트의 지침)"""
    from core.master_data import master_data
    body = {k: v for k, v in (payload or {}).items() if k != "_meta"}
    body["standard_kind"] = kind
    type_id = WORK_GUIDELINE_TYPE if kind == KIND_GUIDELINE else WORK_REGULATION_TYPE
    return master_data.create_or_revise_record(
        master_code=standard_code(stage),
        type_id=type_id,
        name=name,
        attributes=body,
        domains=["governance"],
        is_core=True,
        valid_from=valid_from,
        source=source,
    )
