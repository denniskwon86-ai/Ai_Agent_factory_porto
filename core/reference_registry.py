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
#: 등록부 스키마·**판정 의미** 버전.
#: ★ [2026-07-30] 1.0 → 1.1: `extraction_status` 를 확장자 기준에서 **내용(시그니처) 기준**으로
#:   바꿨고, `owner_org_id` 를 `scope_code` 에서 파생시켰다. 즉 **같은 필드의 뜻이 달라졌다.**
#:   판정 의미가 바뀌면 버전을 올려야 한다 — 그러지 않으면 1.0 파일이 옛 판정을 그대로 들고
#:   살아남는다(실측: API 가 `supported 67` 을 계속 보고했고, 실제로 열리는 것은 16건이었다).
#:   `load_registry()` 가 버전 불일치를 보면 **다시 스캔한다**(아래).
REGISTRY_VERSION = "1.1"

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

#: 암호/DRM 보호 문서. **변환 대상이 아니다** — 원본에서 보호를 해제해야 한다.
ENCRYPTED = "ENCRYPTED"

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


#: 확장자별 파일 머리 시그니처. OOXML(docx·pptx·xlsx)은 zip 이고 PDF 는 `%PDF` 로 시작한다.
_MAGIC = {".docx": b"PK\x03\x04", ".pptx": b"PK\x03\x04", ".xlsx": b"PK\x03\x04",
          ".pdf": b"%PDF"}


#: OLE2 컨테이너 안에 이 스트림이 있으면 **암호화된 OOXML**이다(MS 표준 암호화 · IRM/DRM).
#: 이름은 OLE2 디렉터리에 UTF-16LE 로 적힌다.
_ENCRYPTED_MARKER = "EncryptedPackage".encode("utf-16-le")


def _is_encrypted_ooxml(path: Path) -> bool:
    """암호화된 OOXML 인가.

    ★★ [2026-07-30 실측] 이 판정이 없어서 **원인을 완전히 오진했다.** `docs/reference` 의 51건을
      "레거시 Office(OLE2)"로 보고 변환 도구를 만들었는데, 실제로는 **50건이 암호화된 OOXML**
      (`EncryptedPackage`+`DataSpaces`)이었다. 그래서:
        · LibreOffice → `Error: source file could not be loaded`
        · Office COM → 암호/DRM 프롬프트에서 무한 대기
      **변환으로는 절대 해결되지 않는다.** 원본에서 보호를 해제해 다시 저장해야 한다.
      "변환 필요"라고 표시하면 변환을 시도하게 만들고, 그 시도는 전부 실패한다 — 틀린 원인을
      가리키는 상태 표시는 틀린 숫자보다 나쁘다(사람을 잘못된 작업으로 보낸다)."""
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    return raw[:4] == b"\xd0\xcf\x11\xe0" and _ENCRYPTED_MARKER in raw


def _extraction_status(path: Path, ext: str) -> str:
    """추출 가능 여부를 **내용으로** 판정한다(확장자만 믿지 않는다).

    ★ [2026-07-30 실측] 종전에는 확장자만 봤다. 그 결과 실제 등록부에서 `SUPPORTED` 67건 중
      **실제로 열리는 것은 16건**이었다 — 51건이 확장자만 `.pptx`/`.docx` 인 레거시 바이너리
      (`.ppt`/`.doc` 를 이름만 바꾼 파일)여서 "File is not a zip file" 로 실패했다.

    ⚠️ 이 과대평가는 그냥 부정확한 숫자가 아니다. 사람이 68건을 승인하고 "지식팩에 68건이
      들어갔다"고 믿게 만든다 — 실제로는 16건이다. 그러면 답변 품질이 왜 낮은지 아무도 설명할
      수 없다. **무엇이 없는지 정확히 아는 것이 이 모듈의 산출물**이라는 원칙에 정면으로 어긋난다.

    머리 몇 바이트만 읽는다(전체 파싱은 색인 시점에 한다) — 등록 스캔은 68건을 훑는 경로이므로
    여기서 무거워지면 스캔 자체를 아무도 돌리지 않게 된다."""
    if ext not in _EXTRACTABLE:
        return "CONVERSION_REQUIRED"
    magic = _MAGIC.get(ext)
    if not magic:
        return "SUPPORTED"                     # txt·md·csv·json — 시그니처가 없다
    try:
        with path.open("rb") as f:
            head = f.read(len(magic))
    except OSError:
        return "CONVERSION_REQUIRED"
    if head == magic:
        return "SUPPORTED"
    # 암호화는 **변환으로 풀리지 않는다** — 다른 상태로 구분해 다른 조치를 요구한다.
    if _is_encrypted_ooxml(path):
        return ENCRYPTED
    return "CONVERSION_REQUIRED"


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
            # 확장자가 아니라 **내용**으로 판정한다(위 `_extraction_status` 주석의 실측 참조).
            "extraction_status": _extraction_status(path, ext),
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


def load_registry(registry_path: Path = REGISTRY_PATH,
                  reference_root: Path = REFERENCE_ROOT) -> dict[str, Any]:
    """등록부를 읽는다. **판정 의미가 바뀐 버전이면 다시 스캔한다.**

    ★ [2026-07-30 실측] 이 재스캔이 없으면 옛 판정이 영구히 살아남는다. 브라우저로 API 를
      확인하다 발견했다 — `/reference/summary` 가 `supported: 67` 을 보고하는데 실제로 열리는
      것은 16건이었다. 저장된 1.0 파일이 확장자 기준 판정을 들고 있었기 때문이다.
      숫자가 틀린 것에서 끝나지 않는다: 그 숫자를 보고 **67건을 승인**하면 "지식팩에 67건이
      들어갔다"고 믿게 된다.

    ⚠️ 재스캔은 68건의 해시를 다시 계산하므로 첫 호출이 몇 초 걸린다. 사람이 결정을 내리는
      근거를 최신으로 만드는 값으로는 싸다 — 그리고 **한 번만** 일어난다(스캔 결과에 새 버전이
      기록된다). 사람이 손으로 넣은 승인·소유·비고는 재스캔에도 보존된다."""
    if not registry_path.exists():
        return build_registry(reference_root=reference_root, registry_path=registry_path)
    try:
        doc = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️ [reference_registry] 등록부를 읽을 수 없어 다시 스캔합니다: {e}")
        return build_registry(reference_root=reference_root, registry_path=registry_path)
    if str(doc.get("registry_version", "")) != REGISTRY_VERSION:
        print(f"ℹ️ [reference_registry] 등록부 판정 버전이 다릅니다"
              f"({doc.get('registry_version')} → {REGISTRY_VERSION}) — 다시 스캔합니다. "
              f"`extraction_status` 를 확장자가 아니라 **내용**으로 판정하므로 옛 결과를 그대로 "
              f"쓰면 열리지 않는 파일을 '추출 가능'으로 보고합니다(승인·색인 판단의 근거가 "
              f"틀립니다). 승인·소유·비고는 보존됩니다.")
        try:
            return build_registry(reference_root=reference_root, registry_path=registry_path)
        except Exception as e:
            # 원본 폴더가 없는 환경(배포본만 있는 경우 등)에서는 재스캔할 수 없다.
            #   그때는 옛 등록부라도 쓰되 **그 사실을 숨기지 않는다.**
            print(f"⚠️ [reference_registry] 재스캔 실패 — 옛 판정(v{doc.get('registry_version')})을 "
                  f"그대로 사용합니다. `extraction_status` 를 신뢰하지 마십시오: {e}")
            doc["stale_judgment"] = True
    return doc


def registry_summary(registry_path: Path = REGISTRY_PATH) -> dict[str, Any]:
    registry = load_registry(registry_path)
    assets = registry.get("assets", [])
    by_pack: dict[str, int] = {}
    for asset in assets:
        by_pack[asset["pack_id"]] = by_pack.get(asset["pack_id"], 0) + 1
    approved = [a for a in assets if a.get("approval_status") == APPROVED]
    unscoped = [a for a in assets if not _owner_of(a)]
    encrypted = [a for a in assets if a.get("extraction_status") == ENCRYPTED]
    idx = indexable(registry_path)
    return {
        **registry.get("summary", {}), "by_pack": by_pack,
        "packs": registry.get("pack_definitions", {}),
        # ★ "색인 가능한 것이 몇 건인가"를 함께 준다. 등록 건수만 보여주면 68건이 등록됐는데
        #   지식팩이 비어 있는 이유를 아무도 설명할 수 없다(실측으로 확인한 상태다).
        "approved": len(approved),
        "unscoped": len(unscoped),
        "encrypted": len(encrypted),
        "indexable": idx["total"],
        "note": ("등록은 색인이 아닙니다. 색인에는 **소유 조직 + 승인 + 추출 가능**이 모두 "
                 "필요합니다 — 색인은 되돌릴 수 없기 때문입니다(한번 프롬프트에 실려 나간 "
                 "산출물은 되돌아오지 않습니다)."
                 + (f" 승인 대기 {len(assets) - len(approved)}건은 색인되지 않습니다."
                    if len(approved) < len(assets) else "")
                 + (f" ⚠️ **암호/DRM 보호 {len(encrypted)}건은 자동 처리가 불가능합니다** — "
                    f"변환 도구로도 열리지 않으므로, 문서 소유자가 보호를 해제해 다시 올려야 "
                    f"합니다." if encrypted else "")),
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


EXTRACTION_FAILED = "EXTRACTION_FAILED"


def indexable(registry_path: Path = REGISTRY_PATH,
              include_failed: bool = False) -> dict[str, Any]:
    """**지금 색인할 수 있는** 자산과, 나머지가 왜 안 되는지.

    ★ 색인 조건이 조회 조건보다 엄격한 이유: 색인은 되돌릴 수 없다. 소유 조직·승인·추출 가능
      셋 중 하나라도 빠지면 넣지 않고, **빠진 이유를 건수로 돌려준다** — 이유를 모르면 사람은
      "색인이 고장났다"로 결론짓는다.

    ★ [2026-07-30 실측] 한 번 추출에 실패한 자산은 기본적으로 제외한다(`include_failed=False`).
      `extraction_status` 는 **확장자만 보고** 판정하는데(`.docx` → SUPPORTED) 실제 파일이 그
      형식이 아닌 경우가 있다 — 실제 등록부의 `.docx` 파일이 zip 이 아니어서 열리지 않았다.
      실패를 기록하지 않으면 이 함수가 계속 "1건 색인 가능"이라고 **지킬 수 없는 약속**을
      반복하고, 운영자는 매번 같은 실패를 다시 본다."""
    assets = load_registry(registry_path).get("assets", [])
    ready = []
    blocked = {"no_owner": 0, "not_approved": 0, "conversion_required": 0,
               "encrypted": 0, "extraction_failed": 0}
    for a in assets:
        if not _owner_of(a):
            blocked["no_owner"] += 1
            continue
        if a.get("approval_status") != APPROVED:
            blocked["not_approved"] += 1
            continue
        if a.get("extraction_status") == ENCRYPTED:
            # 변환과 **다른 조치**가 필요하다 — 변환 시도는 전부 실패한다.
            blocked["encrypted"] += 1
            continue
        if a.get("extraction_status") != "SUPPORTED":
            blocked["conversion_required"] += 1
            continue
        if a.get("ingestion_status") == EXTRACTION_FAILED and not include_failed:
            blocked["extraction_failed"] += 1
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
                 + (f"변환 필요 {blocked['conversion_required']}건 · "
                    if blocked["conversion_required"] else "")
                 + (f"**암호/DRM 보호 {blocked['encrypted']}건 — 변환으로 풀리지 않습니다.** "
                    f"원본에서 보호를 해제해 다시 저장해야 합니다(문서 소유자·DRM 권한자만 "
                    f"가능합니다) · " if blocked["encrypted"] else "")
                 + (f"추출 실패 {blocked['extraction_failed']}건(확장자는 맞지만 실제 형식이 "
                    f"다른 파일입니다 — 변환 후 `force` 로 재시도하십시오)"
                    if blocked["extraction_failed"] else "")).rstrip(" ·"),
    }


def ensure_pack(pack_id: str, kb=None) -> dict[str, Any]:
    """색인 대상 지식팩이 없으면 **선언된 정보로 만든다.**

    ★ [2026-07-30 실측] 등록부는 팩 7개를 선언하는데 디스크에는 `core-m3-standards` 하나뿐이었다.
      그 상태로 색인하면 `add_document` 가 "지식팩이 없습니다"로 전부 실패한다 — 승인까지 해
      놓고 색인이 안 되는 막다른 길이다.

    ★ 만들 때 **선언된 소유 조직(`scope_code`)을 매니페스트에 적는다.** 그래야 청크가 범위를
      물려받고(`add_document`), 이후 사람이 직접 올리는 문서도 같은 범위로 들어간다.

    ⚠️ 등급값은 **검증해서** 쓴다. `PACKS` 에는 `INTERNAL_REFERENCE` 처럼 등급 열거값이 아닌
      값이 섞여 있는데(실측), 그것을 그대로 심으면 알 수 없는 등급이 되어 **아무에게도 내용이
      보이지 않는다**(해석 실패는 최고 등급으로 처리하므로). 조용히 강등하지도 않는다 — 바꿨다는
      사실을 로그로 남긴다."""
    if kb is None:
        from core.knowledge_base import knowledge_base as kb
    decl = PACKS.get(pack_id, {})
    if not kb.pack_exists(pack_id):
        kb.create_pack(pack_id, decl.get("name") or pack_id, decl.get("description", ""))
    manifest = kb.get_pack(pack_id) or {}
    changed = False
    owner = (decl.get("scope_code") or "").strip()
    if owner and not (manifest.get("owner_org_id") or "").strip():
        manifest["owner_org_id"] = owner
        changed = True
    if not (manifest.get("classification") or "").strip():
        from core.enterprise_context.classification import (CLEARANCES,
                                                            DEFAULT_CLASSIFICATION)
        raw = (decl.get("classification") or "").strip().upper()
        if raw and raw not in CLEARANCES:
            print(f"⚠️ [reference_registry] 팩 '{pack_id}' 의 선언 등급 '{raw}' 는 정의된 "
                  f"등급이 아닙니다(허용: {', '.join(CLEARANCES)}) — "
                  f"'{DEFAULT_CLASSIFICATION}' 로 기록합니다. 그대로 두면 알 수 없는 등급이 되어 "
                  f"**아무에게도 내용이 보이지 않습니다.** 의도한 등급이 있으면 PACKS 정의를 "
                  f"고치십시오.")
            raw = DEFAULT_CLASSIFICATION
        manifest["classification"] = raw or DEFAULT_CLASSIFICATION
        changed = True
    if changed:
        kb._write_manifest(pack_id, manifest)
    return manifest


def index_approved(reference_root: Path = REFERENCE_ROOT,
                   registry_path: Path = REGISTRY_PATH, dry_run: bool = True,
                   kb=None, asset_ids: list[str] | None = None,
                   force: bool = False) -> dict[str, Any]:
    """승인된 자산을 **실제로 지식팩에 색인한다.**

    ★ 이것이 없으면 승인은 아무 일도 일으키지 않는다 — "승인했는데 검색이 안 된다"가 되고,
      사람들은 승인 절차를 신뢰하지 않게 된다.

    지키는 것:
      · **색인은 되돌릴 수 없다** — 프롬프트에 실려 나간 산출물은 지워도 돌아오지 않는다.
        그래서 `dry_run` 이 기본이고, `indexable()` 의 세 조건(소유·승인·추출 가능)을 통과한
        것만 넣는다.
      · **조직 범위를 청크에 함께 심는다**(`owner_org_id`·`classification`). 이것이 없으면
        등록부에서 통제한 문서가 색인되는 순간 통제 밖으로 나간다.
      · **해시로 멱등**하다. 같은 내용을 다시 넣지 않고, 파일이 바뀌면(sha 변경) 다시 넣는다 —
        `filename` 기준으로 기존 청크를 교체하므로 중복이 쌓이지 않는다.
      · **실패를 조용히 넘기지 않는다.** 추출 실패·빈 텍스트·임베딩 오류를 자산별로 돌려준다.
        빈 문서를 색인하면 검색은 되는데 내용이 없다 — 가장 나쁜 상태다.
    """
    if kb is None:
        from core.knowledge_base import knowledge_base as kb
    registry = load_registry(registry_path)
    assets = {a["asset_id"]: a for a in registry.get("assets", [])}
    # `force` 는 이전에 추출 실패한 자산도 다시 시도한다 — 파일을 변환해 올린 뒤 재시도하는
    #   경로가 있어야 실패 기록이 영구 사망 선고가 되지 않는다.
    ready = indexable(registry_path, include_failed=force)["items"]
    if asset_ids:
        want = set(asset_ids)
        ready = [i for i in ready if i["asset_id"] in want]

    indexed, skipped, failed = [], [], []
    for item in ready:
        asset = assets[item["asset_id"]]
        # 이미 같은 내용이 들어가 있으면 다시 넣지 않는다(임베딩은 비용이고 시간이다).
        if not force and asset.get("indexed_sha256") == asset.get("sha256"):
            skipped.append({"asset_id": asset["asset_id"], "reason": "이미 색인됨(내용 동일)"})
            continue
        path = Path(reference_root) / asset["relative_path"]
        if not path.exists():
            failed.append({"asset_id": asset["asset_id"],
                           "reason": f"원본 파일이 없습니다: {asset['relative_path']} "
                                     f"(등록 후 이동·삭제된 경우 재스캔이 필요합니다)"})
            continue
        if dry_run:
            indexed.append({"asset_id": asset["asset_id"], "pack_id": asset["pack_id"],
                            "filename": asset["filename"], "chunks": None})
            continue
        try:
            from core.knowledge_base import extract_text
            # 팩이 없으면 만든다(선언된 소유 조직·등급을 매니페스트에 적는다) — 승인까지 해 놓고
            #   "지식팩이 없습니다"로 막히는 막다른 길을 없앤다.
            ensure_pack(asset["pack_id"], kb)
            raw = path.read_bytes()
            text = extract_text(asset["filename"], raw)
            if not (text or "").strip():
                # 빈 텍스트를 넣으면 검색 결과에는 뜨는데 근거가 없다 — 넣지 않는다.
                raise ValueError("추출된 텍스트가 비어 있습니다(스캔 PDF 등은 OCR 이 필요합니다).")
            chunks = kb.add_document(
                asset["pack_id"], asset["filename"], text, source="reference-registry",
                raw=raw,
                # ★ 조직 범위·등급을 청크마다 심는다. 색인은 통제의 끝이 아니라 통제가 따라가야
                #   하는 지점이다.
                extra_meta={"owner_org_id": _owner_of(asset),
                            "classification": asset.get("classification", "INTERNAL"),
                            "asset_id": asset["asset_id"],
                            "sha256": asset.get("sha256", ""),
                            "approved_by": asset.get("approved_by", "")})
            asset["ingestion_status"] = "INDEXED"
            asset["indexed_at"] = _now()
            asset["indexed_sha256"] = asset.get("sha256", "")
            asset["indexed_chunks"] = int(chunks)
            indexed.append({"asset_id": asset["asset_id"], "pack_id": asset["pack_id"],
                            "filename": asset["filename"], "chunks": int(chunks),
                            "owner_org_id": _owner_of(asset)})
        except Exception as e:
            # ★ 실패를 **등록부에 남긴다.** 남기지 않으면 `indexable()` 이 계속 "색인 가능"이라고
            #   지킬 수 없는 약속을 반복하고, 운영자는 매번 같은 실패를 다시 본다.
            #   `INDEXED` 로는 절대 표시하지 않는다 — 실패한 색인을 성공으로 적으면 그 문서가
            #   지식팩에 있다고 믿게 된다.
            asset["ingestion_status"] = EXTRACTION_FAILED
            asset["extraction_error"] = str(e)[:300]
            asset["extraction_failed_at"] = _now()
            failed.append({"asset_id": asset["asset_id"],
                           "filename": asset["filename"], "reason": str(e)})
    if not dry_run and (indexed or failed):
        _save(registry, registry_path)
    return {
        "dry_run": bool(dry_run), "ran_at": _now(),
        "indexed": len(indexed), "skipped": len(skipped), "failed": len(failed),
        "items": indexed, "skipped_items": skipped, "failed_items": failed,
        "note": (("[예행] 실제로 색인하지 않았습니다. " if dry_run else "")
                 + f"색인 {len(indexed)}건 · 건너뜀 {len(skipped)}건 · 실패 {len(failed)}건."
                 + (" 실패 항목은 `failed_items` 의 이유를 확인하십시오 — 빈 문서를 색인하지 "
                    "않습니다(검색은 되는데 내용이 없는 상태가 가장 나쁩니다)."
                    if failed else "")
                 + (" 색인된 청크에는 `owner_org_id`·`classification` 이 함께 심겨 있어 "
                    "검색 측에서 조직 범위로 걸러낼 수 있습니다." if indexed and not dry_run
                    else "")),
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
