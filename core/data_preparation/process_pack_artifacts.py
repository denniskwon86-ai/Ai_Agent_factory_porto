"""B2: 업무 팩의 원문·참조를 검증하고 설치 기준선을 불변으로 보관한다.

기존 키트 등록부를 갱신하지 않는다. 이 모듈은 회사·데이터·앱·서명을
생성하지 않으며 DOMAIN_REVIEW_REQUIRED는 도메인 승인이나 실행권한이 아니다.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from core.enterprise_context.process_schema import ProcessError


# 서버 allowlist용 후보 하나. 요청 경로를 이 값에 덧붙여 해석하지 않는다.
#: ★ [2026-09-25] 1.2.0 은 데이터셋 계약(필드·필수·업무키)을 싣는다 — 인증이 그 계약과
#:   대조한다(`contract_conformance`). 1.1.0 은 지우지 않는다: 이미 고정된 설치본이 그 원문을
#:   가리키고, 그 지문은 바뀌면 안 된다(아래 v1 계산은 그대로다).
CANDIDATE_MANIFEST = (Path(__file__).resolve().parents[2] / "process_packs"
                      / "afs.manufacturing.materials-processes" / "1.2.0" / "manifest.json")


class ProcessPackError(ProcessError):
    def __init__(self, reason_code: str, message: str, status_code: int = 422):
        super().__init__(reason_code, message, status_code)


_HEX = re.compile(r"[0-9a-f]{64}\Z")
_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}\Z")
_MAX_BYTES = 8 * 1024 * 1024
_PARTS = ("manifest", "profile", "pack", "blueprints")
#: manifest schema 2 에만 있는 구성요소. schema 1 번들의 필드·지문 계산은 그대로 둔다.
_CONTRACTS = "dataset_contracts"
_MANIFEST_SCHEMAS = (1, 2)
_TEMPLATE_FIELDS = {
    "template_key", "template_revision", "level", "parent_template_key",
    "business_kit_id", "label", "description", "purpose", "trigger", "input_roles",
    "output_roles", "suggested_responsible_roles", "default_selected", "applicability_tags",
    "data_requirements", "suggested_blueprint_refs", "relations", "shortcut_refs",
    "source_refs", "review_status",
}
_BUNDLE_FIELDS = {
    "schema_version", "kit_id", "version", "artifact_digest", "manifest", "profile",
    "pack", "blueprints", "manifest_digest", "profile_digest", "pack_digest",
    "blueprints_digest", "raw_documents",
}


def _parts(schema_version: int) -> tuple:
    return _PARTS + ((_CONTRACTS,) if schema_version == 2 else ())


def _bundle_fields(schema_version: int) -> set:
    extra = {_CONTRACTS, f"{_CONTRACTS}_digest"} if schema_version == 2 else set()
    return _BUNDLE_FIELDS | extra


def _fail(message: str, code: str = "PROCESS_PACK_INVALID", status: int = 422):
    raise ProcessPackError(code, message, status)


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                          allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ProcessPackError("PROCESS_PACK_INVALID", "JSON 정규화에 실패했습니다.") from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _object(value: Any, required: set[str], optional: set[str] | None = None) -> dict:
    if not isinstance(value, dict) or not required <= value.keys():
        _fail("필수 필드가 없는 객체입니다.")
    if value.keys() - required - (optional or set()):
        _fail("지원하지 않는 필드가 있습니다.")
    return value


def _text(value: Any, *, key: bool = False, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        _fail("비어 있거나 문자열이 아닌 값입니다.")
    if any(char == "\x00" or 0xD800 <= ord(char) <= 0xDFFF for char in value):
        _fail("문자열에 지원하지 않는 제어·대체 문자가 있습니다.")
    if key and not _KEY.fullmatch(value):
        _fail("안정 식별자 형식이 잘못되었습니다.")
    return value


def _strings(value: Any, *, nonempty: bool = False, keys: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        _fail("문자열 목록이 필요합니다.")
    for item in value:
        _text(item, key=keys)
    if len(value) != len(set(value)):
        _fail("중복된 목록 항목입니다.")
    return value


def _version(value: Any):
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        _fail("판본은 major.minor.patch 형식이어야 합니다.")


def _schema(value: Any, expected: int):
    if type(value) is not int or value != expected:
        _fail("지원하지 않는 schema 판본입니다.", "PROCESS_PACK_SCHEMA_UNSUPPORTED")


def _decode(raw: bytes, *, max_bytes: int = _MAX_BYTES) -> Any:
    if len(raw) > max_bytes:
        _fail("아티팩트 구성요소가 크기 제한을 넘었습니다.")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                _fail("JSON의 중복 필드는 허용하지 않습니다.")
            out[key] = value
        return out

    def constant(_value):
        _fail("유한하지 않은 JSON 숫자는 허용하지 않습니다.")

    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs,
                          parse_constant=constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, ProcessPackError):
            raise
        raise ProcessPackError("PROCESS_PACK_INVALID", "UTF-8 JSON 원문을 해석할 수 없습니다.") from exc


def _relative(value: Any) -> str:
    _text(value)
    path = PurePosixPath(value)
    if (path.is_absolute() or path.as_posix() != value or "\\" in value
            or any(part in {".", ".."} or not _KEY.fullmatch(part)
                   or part.endswith(".")
                   or part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(
                       f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10))}
                   for part in path.parts)):
        _fail("팩 경로는 패키지 내부의 안전한 상대 경로여야 합니다.", "PROCESS_PACK_PATH_INVALID")
    return value


def _descriptor(value: Any, *, process: bool = False) -> dict:
    fields = {"path", "sha256"}
    if process:
        fields |= {"pack_id", "version", "schema_version", "requires_process_profile_schema", "setup_policy"}
    ref = _object(value, fields)
    _relative(ref["path"])
    if not isinstance(ref["sha256"], str) or not _HEX.fullmatch(ref["sha256"]):
        _fail("원문 SHA-256이 필요합니다.", "PROCESS_PACK_HASH_INVALID")
    if process:
        _text(ref["pack_id"], key=True)
        _version(ref["version"])
        _schema(ref["schema_version"], 1)
        _schema(ref["requires_process_profile_schema"], 2)
        if ref["setup_policy"] != "INCLUDED_REVIEW_REQUIRED":
            _fail("업무 팩은 검토 후 적용해야 합니다.")
    return ref


def _manifest(value: Any) -> dict:
    schema = value.get("schema_version") if isinstance(value, dict) else None
    if type(schema) is not int or schema not in _MANIFEST_SCHEMAS:
        _fail("지원하지 않는 schema 판본입니다.", "PROCESS_PACK_SCHEMA_UNSUPPORTED")
    row = _object(value, {"schema_version", "artifact_kind", "kit_id", "version", "name",
                          "status", "setup_only", "data_class", "profile", "process_pack",
                          "blueprints", "source_refs"} | ({_CONTRACTS} if schema == 2 else set()))
    _text(row["kit_id"], key=True)
    _version(row["version"])
    _text(row["name"])
    if (row["artifact_kind"] != "PROCESS_REFERENCE_CANDIDATE"
            or row["status"] != "DOMAIN_REVIEW_REQUIRED" or row["setup_only"] is not True
            or row["data_class"] != "NO_DATA"):
        _fail("이 판본은 데이터 없는 검토 후보 팩만 지원합니다.")
    _strings(row["source_refs"], nonempty=True)
    _descriptor(row["profile"])
    _descriptor(row["blueprints"])
    _descriptor(row["process_pack"], process=True)
    names = ("profile", "blueprints", "process_pack") + ((_CONTRACTS,) if schema == 2 else ())
    if schema == 2:
        _descriptor(row[_CONTRACTS])
    if len({row[name]["path"] for name in names}) != len(names):
        _fail("구성요소별 원본 경로가 중복되었습니다.")
    return row


def _catalogs(profile: Any, blueprints: Any) -> tuple[set[str], set[tuple[str, str, str]]]:
    row = _object(profile, {"kit_id", "version", "name", "mode", "data_class", "setup_only",
                            "status", "datasets", "outputs", "source_refs"})
    _text(row["kit_id"], key=True)
    _version(row["version"])
    _text(row["name"])
    if (row["mode"] not in {"REAL", "DEMO/SYNTHETIC"} or row["data_class"] != "NO_DATA"
            or row["setup_only"] is not True or row["status"] != "DOMAIN_REVIEW_REQUIRED"):
        _fail("프로필은 미인증·무데이터 골격 후보여야 합니다.")
    _strings(row["source_refs"], nonempty=True)
    if not isinstance(row["datasets"], list) or not row["datasets"]:
        _fail("데이터 계약 후보 목록이 없습니다.")
    keys = set()
    for dataset in row["datasets"]:
        _object(dataset, {"dataset_contract_key", "label", "required", "reference_status"})
        key = _text(dataset["dataset_contract_key"], key=True)
        _text(dataset["label"])
        if (key in keys or type(dataset["required"]) is not bool
                or dataset["reference_status"] != "CONTRACT_CANDIDATE"):
            _fail("중복되었거나 잘못된 데이터 계약 후보입니다.")
        keys.add(key)
    catalog = _object(blueprints, {"schema_version", "kit_id", "version", "review_status",
                                  "blueprints", "source_refs"})
    _schema(catalog["schema_version"], 1)
    if (catalog["kit_id"], catalog["version"]) != (row["kit_id"], row["version"]):
        _fail("프로필과 앱 후보의 키트 판본이 다릅니다.", "PROCESS_PACK_REFERENCE_INVALID")
    if catalog["review_status"] != "DOMAIN_REVIEW_REQUIRED":
        _fail("앱 후보가 승인된 실행 계약으로 표시되었습니다.")
    _strings(catalog["source_refs"], nonempty=True)
    if not isinstance(catalog["blueprints"], list):
        _fail("앱 후보 목록이 필요합니다.")
    apps = {}
    for bp in catalog["blueprints"]:
        _object(bp, {"app_id", "name", "datasets", "reference_status", "source_refs"})
        app_id = _text(bp["app_id"], key=True)
        _text(bp["name"])
        needs = _strings(bp["datasets"], nonempty=True, keys=True)
        _strings(bp["source_refs"], nonempty=True)
        if app_id in apps or not set(needs) <= keys or bp["reference_status"] != "REFERENCE_ONLY":
            _fail("앱 후보의 데이터 참조가 잘못되었습니다.", "PROCESS_PACK_REFERENCE_INVALID")
        apps[app_id] = set(needs)
    if not isinstance(row["outputs"], list):
        _fail("산출물 후보 목록이 필요합니다.")
    seen = set()
    for output in row["outputs"]:
        _object(output, {"output", "label", "requires", "reference_status"})
        app_id = _text(output["output"], key=True)
        _text(output["label"])
        needs = set(_strings(output["requires"], nonempty=True, keys=True))
        if (app_id in seen or app_id not in apps or needs != apps[app_id]
                or output["reference_status"] != "REFERENCE_ONLY"):
            _fail("프로필 산출물과 고정 앱 후보가 일치하지 않습니다.", "PROCESS_PACK_REFERENCE_INVALID")
        seen.add(app_id)
    if seen != apps.keys():
        _fail("프로필 산출물과 고정 앱 후보의 집합이 다릅니다.", "PROCESS_PACK_REFERENCE_INVALID")
    return keys, {(row["kit_id"], row["version"], app_id) for app_id in apps}


def _validate_pack(pack: dict, profile: dict, blueprints: dict) -> dict:
    known_data, known_apps = _catalogs(profile, blueprints)
    _object(pack, {"schema_version", "pack_id", "version", "requires_process_profile_schema",
                   "review_status", "templates", "source_refs"})
    _schema(pack["schema_version"], 1)
    _schema(pack["requires_process_profile_schema"], 2)
    _text(pack["pack_id"], key=True)
    _version(pack["version"])
    if pack["review_status"] != "DOMAIN_REVIEW_REQUIRED":
        _fail("도메인 검토되지 않은 팩을 승인된 표준으로 표시할 수 없습니다.")
    _strings(pack["source_refs"], nonempty=True)
    if not isinstance(pack["templates"], list) or not pack["templates"]:
        _fail("업무 템플릿 목록이 없습니다.")
    by_key = {}
    for template in pack["templates"]:
        _object(template, _TEMPLATE_FIELDS)
        key = _text(template["template_key"], key=True)
        if key in by_key:
            _fail("정본 업무 template_key가 중복되었습니다.")
        by_key[key] = template
        if type(template["template_revision"]) is not int or template["template_revision"] < 1:
            _fail("업무 개정은 양의 정수여야 합니다.")
        for field in ("business_kit_id", "label", "description", "purpose", "trigger"):
            _text(template[field], key=field == "business_kit_id")
        if (template["level"] not in {"L1", "L2"}
                or type(template["default_selected"]) is not bool
                or template["review_status"] != "DOMAIN_REVIEW_REQUIRED"):
            _fail("업무 수준·기본 선택·도메인 검토 상태가 잘못되었습니다.")
        _text(template["parent_template_key"], key=bool(template["parent_template_key"]), empty=True)
        for field in ("input_roles", "output_roles", "suggested_responsible_roles",
                      "applicability_tags", "source_refs"):
            _strings(template[field], nonempty=True)
        requirements = template["data_requirements"]
        if not isinstance(requirements, list):
            _fail("데이터 요구 목록이 필요합니다.")
        requirement_keys = set()
        for requirement in requirements:
            _object(requirement, {"logical_requirement_key", "logical_requirement", "candidate_dataset_keys",
                                  "mandatory", "unresolved_requirement"})
            req_key = _text(requirement["logical_requirement_key"], key=True)
            _text(requirement["logical_requirement"])
            candidates = _strings(requirement["candidate_dataset_keys"], keys=True)
            unresolved = requirement["unresolved_requirement"]
            if (req_key in requirement_keys or type(requirement["mandatory"]) is not bool
                    or type(unresolved) is not bool or not set(candidates) <= known_data
                    or (not candidates and not unresolved)):
                _fail("미해결 요구 또는 데이터 계약 참조가 잘못되었습니다.", "PROCESS_PACK_REFERENCE_INVALID")
            requirement_keys.add(req_key)
        if not isinstance(template["suggested_blueprint_refs"], list):
            _fail("앱 후보 참조 목록이 필요합니다.")
        refs = set()
        for ref in template["suggested_blueprint_refs"]:
            _object(ref, {"kit_id", "version", "app_id"})
            identity = tuple(_text(ref[name]) for name in ("kit_id", "version", "app_id"))
            if identity not in known_apps or identity in refs:
                _fail("존재하지 않거나 중복된 앱 판본 참조입니다.", "PROCESS_PACK_REFERENCE_INVALID")
            refs.add(identity)
    for template in by_key.values():
        parent = by_key.get(template["parent_template_key"])
        if template["level"] == "L1":
            if template["parent_template_key"]:
                _fail("L1은 정본 부모가 없어야 합니다.")
        elif (not parent or parent["level"] != "L1"
              or parent["business_kit_id"] != template["business_kit_id"]):
            _fail("L2는 같은 업무키트의 L1 정본 부모 하나를 가져야 합니다.")
        if not isinstance(template["relations"], list):
            _fail("의미 관계 목록이 필요합니다.")
        relations = set()
        for relation in template["relations"]:
            _object(relation, {"kind", "target_template_key"})
            target = _text(relation["target_template_key"], key=True)
            kind = _text(relation["kind"])
            if (kind not in {"informs", "handoff_to", "related_to"} or target not in by_key
                    or target == template["template_key"] or (kind, target) in relations):
                _fail("정의되지 않은 의미 관계입니다.", "PROCESS_PACK_REFERENCE_INVALID")
            relations.add((kind, target))
        if not isinstance(template["shortcut_refs"], list):
            _fail("바로가기 참조 목록이 필요합니다.")
        shortcuts = set()
        for shortcut in template["shortcut_refs"]:
            _object(shortcut, {"target_template_key", "target_business_kit_id"})
            target = _text(shortcut["target_template_key"], key=True)
            _text(shortcut["target_business_kit_id"], key=True)
            node = by_key.get(target)
            if (template["level"] != "L1" or not node or node["level"] != "L2"
                    or node["parent_template_key"] == template["template_key"]
                    or node["business_kit_id"] != shortcut["target_business_kit_id"]
                    or target in shortcuts):
                _fail("바로가기는 다른 L1의 기존 L2 정본을 참조해야 합니다.", "PROCESS_PACK_REFERENCE_INVALID")
            shortcuts.add(target)
    return json.loads(_canonical(pack))


def validate_pack(pack: dict, profile: dict, blueprints: dict) -> dict:
    """정본·부모·논리 요구·정확한 판본 참조를 검증한다. 권한을 판정하지 않는다."""
    try:
        return _validate_pack(pack, profile, blueprints)
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        if isinstance(exc, ProcessPackError):
            raise
        raise ProcessPackError("PROCESS_PACK_INVALID", "업무 팩의 값·자료형이 잘못되었습니다.") from exc


def _validate_contracts(doc: Any, profile: dict) -> None:
    """★ [2026-09-25] 설치가 고정하는 **데이터셋 계약**. 인증이 이것과 판을 대조한다.

    ⚠️ 프로필의 데이터셋 **전부**에 계약이 있어야 한다. 빠진 키가 있으면 그 데이터셋의 인증은
      «대조할 계약 없음» 으로 막히는데, 그 사실이 설치 때가 아니라 서명 때 처음 드러난다.
    ⚠️ 업무키가 없는 계약은 받지 않는다 — 빈 키·중복을 물을 수 없다."""
    row = _object(doc, {"schema_version", "kit_id", "version", "review_status", "source_refs", "contracts"})
    _schema(row["schema_version"], 1)
    if (row["kit_id"], row["version"]) != (profile["kit_id"], profile["version"]):
        _fail("데이터셋 계약과 프로필의 키트 판본이 다릅니다.", "PROCESS_PACK_REFERENCE_INVALID")
    if row["review_status"] != "DOMAIN_REVIEW_REQUIRED":
        _fail("도메인 검토되지 않은 계약을 승인된 표준으로 표시할 수 없습니다.")
    _strings(row["source_refs"], nonempty=True)
    if not isinstance(row["contracts"], list):
        _fail("데이터셋 계약 목록이 필요합니다.")
    seen = set()
    for contract in row["contracts"]:
        _object(contract, {"dataset_contract_key", "contract_version", "source", "schema", "business_keys"})
        key = _text(contract["dataset_contract_key"], key=True)
        if key in seen:
            _fail("데이터셋 계약이 중복되었습니다.", "PROCESS_PACK_REFERENCE_INVALID")
        seen.add(key)
        _version(contract["contract_version"])
        source = _object(contract["source"], {"path", "sha256"})
        _text(source["path"])
        if not isinstance(source["sha256"], str) or not _HEX.fullmatch(source["sha256"]):
            _fail("계약 원본 SHA-256이 필요합니다.", "PROCESS_PACK_HASH_INVALID")
        fields = _object(contract["schema"], {"fields"})["fields"]
        if not isinstance(fields, list) or not fields:
            _fail("데이터셋 계약에 필드 목록이 없습니다.")
        names = []
        for field in fields:
            _object(field, {"name", "type", "required"})
            names.append(_text(field["name"], key=True))
            _text(field["type"])
            if type(field["required"]) is not bool:
                _fail("필드의 필수 여부는 참/거짓이어야 합니다.")
        if len(names) != len(set(names)):
            _fail("데이터셋 계약의 필드 이름이 중복되었습니다.")
        keys = _strings(contract["business_keys"], nonempty=True, keys=True)
        if not set(keys) <= set(names):
            _fail("업무키가 필드 목록에 없습니다.", "PROCESS_PACK_REFERENCE_INVALID")
    if seen != {d["dataset_contract_key"] for d in profile["datasets"]}:
        _fail("데이터셋 계약이 프로필의 데이터셋과 하나씩 대응하지 않습니다.", "PROCESS_PACK_REFERENCE_INVALID")


def _assemble(raws: dict[str, bytes]) -> dict:
    manifest = _manifest(_decode(raws["manifest"]))
    parts = _parts(manifest["schema_version"])
    if set(raws) != set(parts):
        _fail("아티팩트 구성요소가 manifest 판본과 다릅니다.")
    docs = {name: _decode(raws[name]) for name in parts}
    pairs = (("profile", "profile"), ("pack", "process_pack"), ("blueprints", "blueprints"))
    if manifest["schema_version"] == 2:
        pairs += ((_CONTRACTS, _CONTRACTS),)
    for part, field in pairs:
        if _sha(raws[part]) != manifest[field]["sha256"]:
            _fail("선언한 원문 SHA-256과 파일이 다릅니다.", "PROCESS_PACK_DIGEST_MISMATCH")
    validate_pack(docs["pack"], docs["profile"], docs["blueprints"])
    if manifest["schema_version"] == 2:
        try:
            _validate_contracts(docs[_CONTRACTS], docs["profile"])
        except (KeyError, TypeError, ValueError, RecursionError) as exc:
            if isinstance(exc, ProcessPackError):
                raise
            raise ProcessPackError("PROCESS_PACK_INVALID", "데이터셋 계약의 값·자료형이 잘못되었습니다.") from exc
    if (manifest["kit_id"], manifest["version"]) != (docs["profile"]["kit_id"], docs["profile"]["version"]):
        _fail("manifest와 프로필의 판본이 다릅니다.", "PROCESS_PACK_REFERENCE_INVALID")
    for field in ("pack_id", "version", "schema_version", "requires_process_profile_schema"):
        if manifest["process_pack"][field] != docs["pack"][field]:
            _fail("manifest와 업무 팩의 식별자가 다릅니다.", "PROCESS_PACK_REFERENCE_INVALID")
    #: ⚠️ schema 1 의 identity 는 종전과 **같은 값**이어야 한다 — 고정된 설치본의 지문이다.
    digests = {f"{part}_digest": _sha(raws[part]) for part in parts}
    identity = {"schema_version": manifest["schema_version"], "kit_id": manifest["kit_id"],
                "version": manifest["version"], **digests}
    return {**identity, "artifact_digest": _sha(_canonical(identity).encode("utf-8")), **docs,
            "raw_documents": {part: base64.b64encode(raws[part]).decode("ascii") for part in parts}}


def load_bundle(manifest_path: Path) -> dict:
    """로컬의 독립 reference manifest를 읽는다. 원문 bytes가 지문·스냅샷의 기준이다."""
    try:
        manifest_path = Path(manifest_path).resolve(strict=True)
        if not manifest_path.is_file() or manifest_path.stat().st_size > _MAX_BYTES:
            _fail("manifest가 파일이 아니거나 크기 제한을 넘었습니다.")
        raw = manifest_path.read_bytes()
        manifest = _manifest(_decode(raw))
        root = manifest_path.parent
        raws = {"manifest": raw}
        pairs = (("profile", "profile"), ("pack", "process_pack"), ("blueprints", "blueprints"))
        if manifest["schema_version"] == 2:
            pairs += ((_CONTRACTS, _CONTRACTS),)
        for part, field in pairs:
            path = (root / _relative(manifest[field]["path"])).resolve(strict=True)
            if not path.is_relative_to(root) or path == manifest_path or not path.is_file():
                _fail("원본 경로가 패키지 밖으로 나가거나 파일이 아닙니다.", "PROCESS_PACK_PATH_INVALID")
            if path.stat().st_size > _MAX_BYTES:
                _fail("아티팩트 구성요소가 크기 제한을 넘었습니다.")
            raws[part] = path.read_bytes()
        return _assemble(raws)
    except OSError as exc:
        raise ProcessPackError("PROCESS_PACK_FILE_UNAVAILABLE", "아티팩트 원본을 읽을 수 없습니다.", 503) from exc


def _verify(bundle: Any) -> dict:
    schema = bundle.get("schema_version") if isinstance(bundle, dict) else None
    if type(schema) is not int or schema not in _MANIFEST_SCHEMAS:
        #: 모르는 판본은 schema 1 규칙으로 대조한다 — 종전과 같은 자리(필드·재조립 대조)에서
        #: 거부된다. 여기서 새 사유로 갈라 답하지 않는다.
        schema = 1
    _object(bundle, _bundle_fields(schema))
    encoded = _object(bundle["raw_documents"], set(_parts(schema)))
    raws = {}
    for part in _parts(schema):
        text = encoded[part]
        if not isinstance(text, str) or len(text) > ((_MAX_BYTES + 2) // 3) * 4:
            _fail("아티팩트 원문 인코딩이 잘못되었습니다.")
        try:
            raws[part] = base64.b64decode(text, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ProcessPackError("PROCESS_PACK_INVALID", "아티팩트 원문 인코딩이 잘못되었습니다.") from exc
    rebuilt = _assemble(raws)
    if _canonical(bundle) != _canonical(rebuilt):
        _fail("불변 아티팩트의 원문과 해석 결과가 다릅니다.", "PROCESS_PACK_DIGEST_MISMATCH")
    return rebuilt


def _ensure_table(conn):
    # executescript는 호출자의 트랜잭션을 조기 commit할 수 있어 사용하지 않는다.
    conn.execute("""CREATE TABLE IF NOT EXISTS kit_process_artifacts (
        artifact_digest TEXT PRIMARY KEY, kit_id TEXT NOT NULL, version TEXT NOT NULL,
        bundle_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(kit_id, version))""")
    for operation in ("UPDATE", "DELETE"):
        conn.execute(f"""CREATE TRIGGER IF NOT EXISTS kit_process_artifacts_no_{operation.lower()}
            BEFORE {operation} ON kit_process_artifacts BEGIN
            SELECT RAISE(ABORT, 'PROCESS_ARTIFACT_IMMUTABLE'); END""")
    # SQLite REPLACE가 DELETE trigger를 건너뛰는 설정에서도 기존 정본 교체를 막는다.
    conn.execute("""CREATE TRIGGER IF NOT EXISTS kit_process_artifacts_no_replace
        BEFORE INSERT ON kit_process_artifacts WHEN EXISTS (
            SELECT 1 FROM kit_process_artifacts WHERE artifact_digest=NEW.artifact_digest
            OR (kit_id=NEW.kit_id AND version=NEW.version)) BEGIN
        SELECT RAISE(ABORT, 'PROCESS_ARTIFACT_IMMUTABLE'); END""")


def _stored(row: Any) -> dict:
    try:
        row = dict(row)
        bundle = _verify(_decode(row["bundle_json"].encode("utf-8"), max_bytes=12 * _MAX_BYTES))
        if any(row[key] != bundle[key] for key in ("artifact_digest", "kit_id", "version")):
            _fail("아티팩트 인덱스와 원문이 다릅니다.")
        return bundle
    except (ProcessPackError, KeyError, TypeError, ValueError) as exc:
        raise ProcessPackError("PROCESS_ARTIFACT_CORRUPT", "고정 아티팩트 무결성을 확인할 수 없습니다.", 503) from exc


def pin_bundle(store: Any, bundle: dict) -> dict:
    """같은 키트/판본은 같은 원문만 허용한다. 기존 registry는 충돌 조회만 한다."""
    verified = _verify(bundle)
    try:
        with store.transaction() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            # 최초 표 생성과 레거시 등록도 같은 DB 쓰기 잠금 아래 직렬화한다.
            # 이미 고정한 동일 원문의 재시도라도 레거시 판본과 공존하면 차단한다.
            legacy_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='kit_registry_versions'"
            ).fetchone()
            if legacy_exists and conn.execute(
                "SELECT 1 FROM kit_registry_versions WHERE kit_id=? AND version=?",
                (verified["kit_id"], verified["version"]),
            ).fetchone():
                _fail("기존 키트 등록부와 같은 판번입니다. 별도 판번을 사용하십시오.",
                      "IMMUTABLE_VERSION_CONFLICT", 409)
            _ensure_table(conn)
            row = conn.execute("SELECT * FROM kit_process_artifacts WHERE kit_id=? AND version=?",
                               (verified["kit_id"], verified["version"])).fetchone()
            if row:
                previous = _stored(row)
                if previous["artifact_digest"] != verified["artifact_digest"]:
                    _fail("같은 키트 판번의 다른 원본입니다. 새 판번이 필요합니다.", "IMMUTABLE_VERSION_CONFLICT", 409)
                return previous
            conn.execute("INSERT INTO kit_process_artifacts VALUES (?, ?, ?, ?, ?)",
                         (verified["artifact_digest"], verified["kit_id"], verified["version"],
                          _canonical(verified), datetime.now(timezone.utc).isoformat()))
        return verified
    except sqlite3.Error as exc:
        raise ProcessPackError("PROCESS_ARTIFACT_STORAGE_UNAVAILABLE", "아티팩트를 고정할 수 없습니다.", 503) from exc


def stored_bundle(conn: Any, artifact_digest: str) -> dict | None:
    """**호출자의 연결**로 고정 원문을 읽는다. 없으면 `None`.

    ★ 인증은 자기 트랜잭션 안에서 계약을 읽어야 한다 — `store.transaction()` 을 다시 열면
      잠금을 한 번 더 잡고 다른 연결로 읽게 된다. 무결성 검증(`_stored`)은 같다."""
    if not isinstance(artifact_digest, str) or not _HEX.fullmatch(artifact_digest):
        _fail("정확한 아티팩트 SHA-256이 필요합니다.", "PROCESS_PACK_HASH_INVALID")
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='kit_process_artifacts'").fetchone():
        return None
    row = conn.execute("SELECT * FROM kit_process_artifacts WHERE artifact_digest=?", (artifact_digest,)).fetchone()
    return _stored(row) if row is not None else None


def get_bundle(store: Any, artifact_digest: str) -> dict:
    """설치 당시 고정된 원문만 읽는다. 현재 등록부/파일로 대체하지 않는다."""
    if not isinstance(artifact_digest, str) or not _HEX.fullmatch(artifact_digest):
        _fail("정확한 아티팩트 SHA-256이 필요합니다.", "PROCESS_PACK_HASH_INVALID")
    try:
        with store.transaction() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN")
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='kit_process_artifacts'").fetchone()
            row = conn.execute("SELECT * FROM kit_process_artifacts WHERE artifact_digest=?",
                               (artifact_digest,)).fetchone() if exists else None
            if row is None:
                _fail("고정 아티팩트가 없습니다.", "PROCESS_ARTIFACT_NOT_FOUND", 404)
            return _stored(row)
    except sqlite3.Error as exc:
        raise ProcessPackError("PROCESS_ARTIFACT_STORAGE_UNAVAILABLE", "고정 아티팩트를 읽을 수 없습니다.", 503) from exc
