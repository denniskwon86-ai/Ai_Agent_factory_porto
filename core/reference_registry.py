"""docs/reference 원본을 통제 가능한 데이터 자산으로 전환하는 등록부.

원본 문서를 곧바로 MDM 또는 전사 RAG에 넣지 않는다. 먼저 출처·해시·조직 범위·분류·승인
상태를 등록하고, 승인된 자산만 지식팩에 색인한다. 이 파일은 LLM 호출 없이 동작한다.

## [2026-07-30] M2 범위 계약과 연결 — 두 가지 문을 열었다

이 모듈은 "M2 권한 모델이 완성된 뒤 승인된 범위만 색인한다"고 적어 두고 그 문을 만들지
않았다. 그 결과 실측에서 자산 68건이 **전부** `PENDING_REVIEW` · 색인 0 · 승인 경로 없음
이었다 — 즉 **아무것도 지식팩에 들어갈 수 없는 상태**였다.

### ① 소유 조직이 두 필드로 갈려 있었다

`scope_code` 는 분류기가 채운다(실측: LS_MNM 46 · MNM_BATTERY 6 · MNM_COPPER 16).
그런데 `owner_org_id` 는 **68건 전부 공백**이었다. 같은 사실("이 자산은 누구 것인가")이 두
칸에 나뉘어 하나만 채워진 상태다. 관문 A 이후 빈 소유는 **비노출**이므로, 빈 쪽을 읽는
소비자에게는 68건이 통째로 사라진다 — 라이브러리 경로에서 닫은 것과 같은 유형의 중복이다.
→ `owner_org_id` 를 `scope_code` 에서 파생시킨다(명시 지정은 그대로 존중).

### ② 승인 문이 없었다

`approval_status` 는 `PENDING_REVIEW` 로만 쓰였고 승인 함수가 없었다. 전사 공용 전환 경로가
없어 한시 예외로 버티던 것과 같은 상황이다 → `approve_asset()` / `reject_asset()`.

## 색인은 되돌릴 수 없다 — 그래서 색인 조건이 조회 조건보다 엄격하다

한번 지식팩에 들어간 문서는 프롬프트에 실려 산출물에 반영된다. 지우더라도 **이미 나간 산출물은
되돌아오지 않는다.** 기준정보 주입에 한시 예외를 두지 않은 것과 같은 이유로, `indexable()` 은
**소유 조직 + 승인 + 추출 가능**을 모두 요구한다.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REFERENCE_ROOT = Path("docs/reference")
REGISTRY_PATH = Path("data/reference_registry.json")
REGISTRY_VERSION = "1.0"

PACKS: dict[str, dict[str, Any]] = {
    "manufacturing-standards": {
        "name": "제조·데이터 표준",
        "description": "스마트제조 참조모델, 국가·국제 표준, 데이터 카탈로그 표준",
        "scope_code": "LS_MNM", "classification": "INTERNAL_REFERENCE",
        "tags": ["manufacturing", "standard", "data-governance"],
    },
    "battery-materials-operations": {
        "name": "배터리소재 운영 지식",
        "description": "배터리소재 스마트공장, SIOP, ISP, 사업부 운영 참조자료",
        "scope_code": "MNM_BATTERY", "classification": "INTERNAL",
        "tags": ["battery-materials", "manufacturing", "siop"],
    },
    "copper-smelting-operations": {
        "name": "동제련·생산통합 운영 지식",
        "description": "제련, 귀금속, 화성, 원료, 생산통합 운영 참조자료",
        "scope_code": "MNM_COPPER", "classification": "INTERNAL",
        "tags": ["copper-smelting", "production", "raw-material"],
    },
    "corporate-management-finance": {
        "name": "경영관리·재무 지식",
        "description": "사업전략, 경영관리, 회계, 자금, Hedge 교육·업무 자료",
        "scope_code": "LS_MNM", "classification": "INTERNAL",
        "tags": ["management", "finance", "accounting", "hedge"],
    },
    "scm-procurement-logistics": {
        "name": "SCM·구매·물류 지식",
        "description": "SCM, 구매, 물류, 영업 연계 업무 자료",
        "scope_code": "LS_MNM", "classification": "INTERNAL",
        "tags": ["scm", "procurement", "logistics", "sales"],
    },
    "quality-esg-safety": {
        "name": "품질·ESG·안전 지식",
        "description": "품질, 안전, 환경, 지속가능경영, Compliance 자료",
        "scope_code": "LS_MNM", "classification": "INTERNAL",
        "tags": ["quality", "esg", "safety", "environment", "compliance"],
    },
    "innovation-rnd-people": {
        "name": "혁신·R&D·지원부서 지식",
        "description": "Biz혁신, 기술연구소, 인사, 법인관리 자료",
        "scope_code": "LS_MNM", "classification": "INTERNAL",
        "tags": ["innovation", "rnd", "hr", "corporate"],
    },
}

PENDING_REVIEW = "PENDING_REVIEW"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
APPROVAL_STATES = (PENDING_REVIEW, APPROVED, REJECTED)

_EXTRACTABLE = {".pdf", ".docx", ".pptx", ".txt", ".md", ".csv", ".json"}
# 등록부 설명서는 원본 자료가 아니라 이 스캐너의 산출물이다. 다시 자산으로 넣으면 매 스캔마다
# 자기 자신을 집계하는 순환이 생긴다.
_GENERATED_REFERENCE_FILES = {"REFERENCE_DATASET_REGISTER.md"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _classify(relative_path: str) -> tuple[str, str, list[str], str]:
    """파일명·경로만으로 보수적으로 분류한다. 내용의 진실성 판정은 하지 않는다."""
    path = relative_path.replace("\\", "/")
    text = path.lower()
    if any(token in text for token in ("x9101", "표준화", "카탈로그 표준", "스마트공장 보급", "cpps", "인공지능 기반 연구기술", "업무 프로세스 정의서")):
        return "manufacturing-standards", "LS_MNM", ["standard", "manufacturing"], "STANDARD_REFERENCE"
    if any(token in text for token in ("배터리", "battery")):
        return "battery-materials-operations", "MNM_BATTERY", ["battery-materials", "manufacturing"], "BUSINESS_REFERENCE"
    if any(token in text for token in ("제련", "귀금속", "화성", "원료", "ods", "생산통합", "psa")):
        return "copper-smelting-operations", "MNM_COPPER", ["copper-smelting", "production"], "BUSINESS_REFERENCE"
    if any(token in text for token in ("경영관리", "사업전략", "회계", "자금", "hedge")):
        return "corporate-management-finance", "LS_MNM", ["management", "finance"], "TRAINING_OR_GUIDE"
    if any(token in text for token in ("scm", "구매", "물류", "영업")):
        return "scm-procurement-logistics", "LS_MNM", ["scm", "procurement", "logistics"], "TRAINING_OR_GUIDE"
    if any(token in text for token in ("품질", "안전", "환경", "지속가능", "compliance")):
        return "quality-esg-safety", "LS_MNM", ["quality", "esg", "safety"], "TRAINING_OR_GUIDE"
    return "innovation-rnd-people", "LS_MNM", ["innovation", "rnd", "corporate"], "TRAINING_OR_GUIDE"


def _asset_id(relative_path: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "-" for ch in relative_path.upper())
    normalized = "-".join(part for part in normalized.split("-") if part)
    return f"REF-{normalized[:72]}"


def build_registry(reference_root: Path = REFERENCE_ROOT, registry_path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """원본 전체를 재스캔해 멱등 등록부를 만든다. 기존 사람 승인·비고는 동일 해시 자산에 보존한다."""
    existing: dict[str, dict[str, Any]] = {}
    if registry_path.exists():
        try:
            existing = {a["relative_path"]: a for a in json.loads(registry_path.read_text(encoding="utf-8")).get("assets", [])}
        except Exception:
            existing = {}

    assets = []
    for path in sorted(reference_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(reference_root).as_posix()
        if path.name in _GENERATED_REFERENCE_FILES:
            continue
        pack_id, scope_code, tags, asset_kind = _classify(relative)
        previous = existing.get(relative, {})
        ext = path.suffix.lower()
        assets.append({
            "asset_id": previous.get("asset_id", _asset_id(relative)),
            "relative_path": relative,
            "filename": path.name,
            "extension": ext,
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "source_kind": asset_kind,
            "pack_id": previous.get("pack_id", pack_id),
            "scope_code": previous.get("scope_code", scope_code),
            "classification": previous.get("classification", "INTERNAL"),
            "tags": previous.get("tags", tags),
            "extraction_status": "SUPPORTED" if ext in _EXTRACTABLE else "CONVERSION_REQUIRED",
            "ingestion_status": previous.get("ingestion_status", "REGISTERED"),
            "approval_status": previous.get("approval_status", PENDING_REVIEW),
            # ★ 소유 조직은 `scope_code` 에서 **파생**한다. 종전에는 빈 문자열이 기본이어서
            #   실측 68건이 전부 공백이었고, 관문 A 이후 빈 소유는 비노출이므로 그 상태로
            #   색인·조회 경로에 올리면 자산이 통째로 사라진다. 같은 사실을 두 칸에 두고 한 칸만
            #   채우는 것이 원인이었다 — 명시 지정이 있으면 그것을 존중하고, 없으면 분류 결과를 쓴다.
            "owner_org_id": previous.get("owner_org_id") or scope_code,
            "approved_by": previous.get("approved_by", ""),
            "approved_at": previous.get("approved_at", ""),
            "notes": previous.get("notes", ""),
        })
    registry = {
        "registry_version": REGISTRY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_root": reference_root.as_posix(),
        "pack_definitions": PACKS,
        "summary": {
            "total": len(assets),
            "supported": sum(a["extraction_status"] == "SUPPORTED" for a in assets),
            "conversion_required": sum(a["extraction_status"] == "CONVERSION_REQUIRED" for a in assets),
            "pending_review": sum(a["approval_status"] == "PENDING_REVIEW" for a in assets),
        },
        "assets": assets,
    }
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return registry


def load_registry(registry_path: Path = REGISTRY_PATH) -> dict[str, Any]:
    if not registry_path.exists():
        return build_registry(registry_path=registry_path)
    return json.loads(registry_path.read_text(encoding="utf-8"))


def registry_summary(registry_path: Path = REGISTRY_PATH) -> dict[str, Any]:
    registry = load_registry(registry_path)
    assets = registry.get("assets", [])
    by_pack: dict[str, int] = {}
    for asset in assets:
        by_pack[asset["pack_id"]] = by_pack.get(asset["pack_id"], 0) + 1
    approved = [a for a in assets if a.get("approval_status") == APPROVED]
    unscoped = [a for a in assets if not _owner_of(a)]
    idx = indexable(registry_path)
    return {
        **registry.get("summary", {}), "by_pack": by_pack,
        "packs": registry.get("pack_definitions", {}),
        # ★ "색인 가능한 것이 몇 건인가"를 함께 준다. 등록 건수만 보여주면 68건이 등록됐는데
        #   지식팩이 비어 있는 이유를 아무도 설명할 수 없다(실측으로 확인한 상태다).
        "approved": len(approved),
        "unscoped": len(unscoped),
        "indexable": idx["total"],
        "note": ("등록은 색인이 아닙니다. 색인에는 **소유 조직 + 승인 + 추출 가능**이 모두 "
                 "필요합니다 — 색인은 되돌릴 수 없기 때문입니다(한번 프롬프트에 실려 나간 "
                 "산출물은 되돌아오지 않습니다)."
                 + (f" 승인 대기 {len(assets) - len(approved)}건은 색인되지 않습니다."
                    if len(approved) < len(assets) else "")),
    }


# ══════════════════════════════════════════════════════════════════════════
# M2 범위 계약 연결 (2026-07-30)
# ══════════════════════════════════════════════════════════════════════════
def _owner_of(asset: dict[str, Any]) -> str:
    """이 자산의 소유 조직. 두 칸 중 채워진 쪽을 **한 곳에서** 읽는다.

    ★ 호출자마다 다른 칸을 읽으면 같은 자산이 화면마다 다르게 보인다 — 그 상태의 권한 판정은
      아무도 신뢰하지 않는다(`scoping.owner_of` 와 같은 이유의 같은 조치)."""
    return ((asset.get("owner_org_id") or "").strip()
            or (asset.get("scope_code") or "").strip())


def contract_row(asset: dict[str, Any]) -> dict[str, Any]:
    """등록부 자산을 **범위 계약 어휘**로 옮긴다(판정 로직을 복제하지 않기 위한 유일한 변환점).

    승인되지 않은 자산은 `scope_type` 을 비워 둔다 — 관문 A 기본값(`ORG_PRIVATE`)으로 소유
    조직에게만 보이고, 승인 전에 다른 조직으로 새지 않는다."""
    return {
        "owner_organization_id": _owner_of(asset),
        "enterprise_scope_id": _owner_of(asset),
        "scope_type": "ORG_PRIVATE",
        "classification": (asset.get("classification") or "INTERNAL"),
        "tenant_id": "tenant_default", "entity_mode": "REAL",
        **{k: v for k, v in asset.items() if k not in ("classification",)},
    }


def visible_assets(scope_node_id: str = "", viewer_clearance: str = "",
                   registry_path: Path = REGISTRY_PATH) -> list[dict[str, Any]]:
    """이 조직 문맥에서 보이는 자산 목록.

    ★ 판정은 `scoping.filter_visible` 단일 지점에 맡긴다. 여기서 다시 구현하면 카탈로그·용어
      사전과 규칙이 어긋나고, 어긋난 권한 판정은 유출이거나 실명이다.
    ⚠️ 범위를 주지 않으면 필터하지 않는다 — ECM 미도입 흐름을 막지 않는다(전 저장소 공통 규약)."""
    assets = load_registry(registry_path).get("assets", [])
    rows = [contract_row(a) for a in assets]
    if not (scope_node_id or viewer_clearance):
        return rows
    from core.enterprise_context.scoping import filter_visible
    return filter_visible(rows, scope_node_id=scope_node_id,
                          viewer_clearance=viewer_clearance)


def _save(registry: dict[str, Any], registry_path: Path) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2),
                             encoding="utf-8")


def _set_approval(asset_id: str, state: str, actor: str, note: str,
                  registry_path: Path) -> dict[str, Any]:
    if state not in APPROVAL_STATES:
        raise ValueError(f"approval_status 는 {list(APPROVAL_STATES)} 중 하나여야 합니다.")
    if not (actor or "").strip():
        raise ValueError(
            "승인자 식별 정보가 없습니다 — 누가 이 문서를 전사 지식으로 승인했는지 없으면 "
            "감사에서 근거가 되지 못합니다.")
    registry = load_registry(registry_path)
    assets = registry.get("assets", [])
    target = next((a for a in assets if a.get("asset_id") == asset_id), None)
    if not target:
        raise ValueError(f"등록되지 않은 자산입니다: {asset_id}")
    if state == APPROVED and not _owner_of(target):
        # 소유 조직 없는 자산을 승인하면, 승인은 됐는데 아무에게도 안 보이는 상태가 된다.
        raise ValueError(
            f"소유 조직이 없어 승인할 수 없습니다: {asset_id}. 관문 A 이후 소유가 빈 자산은 "
            f"아무에게도 보이지 않으므로, 승인해도 쓰이지 않습니다 — 먼저 소유 조직을 "
            f"지정하십시오.")
    before = target.get("approval_status", PENDING_REVIEW)
    target["approval_status"] = state
    target["approved_by"] = actor.strip() if state == APPROVED else ""
    target["approved_at"] = _now() if state == APPROVED else ""
    if note:
        target["notes"] = note
    registry["summary"]["pending_review"] = sum(
        a["approval_status"] == PENDING_REVIEW for a in assets)
    _save(registry, registry_path)
    _audit_approval(asset_id, before, state, actor, note, _owner_of(target))
    return target


def approve_asset(asset_id: str, approved_by: str, note: str = "",
                  registry_path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """이 문서를 지식팩 색인 대상으로 승인한다.

    ⚠️ 승인은 "이 문서를 사내 지식으로 쓴다"는 결정이다. 색인은 되돌릴 수 없으므로(프롬프트에
      실려 나간 산출물은 되돌아오지 않는다) 승인자를 반드시 남긴다."""
    return _set_approval(asset_id, APPROVED, approved_by, note, registry_path)


def reject_asset(asset_id: str, actor: str, reason: str,
                 registry_path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """색인 대상에서 제외한다. **사유 필수** — 없으면 같은 문서가 계속 다시 올라온다."""
    if not (reason or "").strip():
        raise ValueError(
            "반려 사유는 필수입니다 — 없으면 무엇이 문제였는지 알 수 없어 같은 문서가 계속 "
            "다시 올라옵니다.")
    return _set_approval(asset_id, REJECTED, actor, reason, registry_path)


def indexable(registry_path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """**지금 색인할 수 있는** 자산과, 나머지가 왜 안 되는지.

    ★ 색인 조건이 조회 조건보다 엄격한 이유: 색인은 되돌릴 수 없다. 소유 조직·승인·추출 가능
      셋 중 하나라도 빠지면 넣지 않고, **빠진 이유를 건수로 돌려준다** — 이유를 모르면 사람은
      "색인이 고장났다"로 결론짓는다."""
    assets = load_registry(registry_path).get("assets", [])
    ready, blocked = [], {"no_owner": 0, "not_approved": 0, "conversion_required": 0}
    for a in assets:
        if not _owner_of(a):
            blocked["no_owner"] += 1
            continue
        if a.get("approval_status") != APPROVED:
            blocked["not_approved"] += 1
            continue
        if a.get("extraction_status") != "SUPPORTED":
            blocked["conversion_required"] += 1
            continue
        ready.append({"asset_id": a["asset_id"], "relative_path": a["relative_path"],
                      "pack_id": a["pack_id"], "owner_org_id": _owner_of(a),
                      "classification": a.get("classification", "INTERNAL"),
                      "approved_by": a.get("approved_by", "")})
    return {
        "total": len(ready), "items": ready, "blocked": blocked,
        "note": ("색인에는 소유 조직 + 승인 + 추출 가능이 모두 필요합니다(색인은 되돌릴 수 "
                 "없습니다). "
                 + (f"승인 대기 {blocked['not_approved']}건 · " if blocked["not_approved"] else "")
                 + (f"소유 미지정 {blocked['no_owner']}건 · " if blocked["no_owner"] else "")
                 + (f"변환 필요 {blocked['conversion_required']}건"
                    if blocked["conversion_required"] else "")).rstrip(" ·"),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit_approval(asset_id: str, before: str, after: str, actor: str, reason: str,
                    owner: str) -> None:
    """승인·반려를 감사에 남긴다 — 전사 공용 전환과 같은 급의 결정이다."""
    try:
        from core.enterprise_context import audit
        audit.record(audit.APPROVAL_GRANTED, resource_type="reference_asset",
                     resource_id=asset_id, actor=actor or audit.ANONYMOUS,
                     actor_scopes=[owner] if owner else [],
                     outcome="allowed" if after == APPROVED else "denied",
                     reason=reason or "", detail=f"{before}->{after} owner={owner}")
    except Exception as e:                                           # pragma: no cover
        print(f"⚠️ [reference_registry] 감사 기록 실패: {e}")
