"""docs/reference 원본을 통제 가능한 데이터 자산으로 전환하는 등록부.

원본 문서를 곧바로 MDM 또는 전사 RAG에 넣지 않는다. 먼저 출처·해시·조직 범위·분류·승인
상태를 등록하고, 승인된 자산만 지식팩에 색인한다. 이 파일은 LLM 호출 없이 동작한다.
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
            "approval_status": previous.get("approval_status", "PENDING_REVIEW"),
            "owner_org_id": previous.get("owner_org_id", ""),
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
    by_pack: dict[str, int] = {}
    for asset in registry.get("assets", []):
        by_pack[asset["pack_id"]] = by_pack.get(asset["pack_id"], 0) + 1
    return {**registry.get("summary", {}), "by_pack": by_pack, "packs": registry.get("pack_definitions", {})}
