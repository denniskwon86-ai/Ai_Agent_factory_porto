"""업무 팩 1.2.0 의 데이터셋 계약 부품. 격리 runner 전용 — 원본 팩·스타터 키트는 읽기만 한다.

설치가 이 계약을 번들 지문째 고정하고, 인증이 판의 봉인 원문을 그것과 대조한다
(`certification_subject._conforming_contract`). 여기서는 부품 자체를 본다:

- 1.1.0(계약 없음) 번들의 지문은 **바뀌지 않는다** — 이미 설치본이 그 지문을 고정했다.
- 1.2.0 의 계약은 스타터 키트 정본 계약에서 **옮긴 것**이다(원본 sha256 이 키트 매니페스트 기록과 같다).
- 부품의 변조·누락·잘못된 업무키는 적재 단계에서 거부된다.
"""
from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from core.data_preparation import process_pack_artifacts as artifacts
from tests.test_b2_pack_artifacts import package, read_json, rehash, write_json  # noqa: F401

V110 = artifacts.CANDIDATE_MANIFEST.parents[1] / "1.1.0" / "manifest.json"
KIT = artifacts.CANDIDATE_MANIFEST.parents[3] / "starter_kits" / "KIT-MFG-NONFERROUS-PROCUREMENT" / "1.0.0"
#: 1.1.0 번들 지문 — 변경 전 코드로 계산한 값(2026-09-25). 불변 자산의 지문이라 값 자체가 계약이다.
V110_ARTIFACT_DIGEST = "670973f6c38dac8447235224d4246de1b1ce43b215ed01335102e6825b5a5f0d"


def test_the_v1_bundle_digest_that_installations_pinned_is_unchanged():
    old = artifacts.load_bundle(V110)
    assert old["schema_version"] == 1 and old["version"] == "1.1.0"
    assert old["artifact_digest"] == V110_ARTIFACT_DIGEST
    assert "dataset_contracts" not in old and set(old["raw_documents"]) == set(artifacts._PARTS)
    assert artifacts._verify(old) == old


def test_the_candidate_is_schema_two_and_carries_contracts():
    bundle = artifacts.load_bundle(artifacts.CANDIDATE_MANIFEST)
    assert bundle["schema_version"] == 2 and bundle["version"] == "1.2.0"
    assert bundle["artifact_digest"] != V110_ARTIFACT_DIGEST
    assert artifacts._verify(bundle) == bundle


def test_each_profile_dataset_has_exactly_the_starter_kit_contract():
    """★ 계약은 지어내지 않는다 — 스타터 키트 계약 파일에서 옮기고, 그 원본을 sha256 으로 가리킨다."""
    bundle = artifacts.load_bundle(artifacts.CANDIDATE_MANIFEST)
    recorded = {item["path"]: item["sha256"] for section in read_json(KIT / "manifest.json").values()
                if isinstance(section, list) for item in section
                if isinstance(item, dict) and str(item.get("path", "")).startswith("contracts/")}
    contracts = bundle["dataset_contracts"]["contracts"]
    assert [c["dataset_contract_key"] for c in contracts] == [
        d["dataset_contract_key"] for d in bundle["profile"]["datasets"]]
    for contract in contracts:
        key = contract["dataset_contract_key"]
        raw = (KIT / "contracts" / f"{key}.contract.json").read_bytes()
        assert contract["source"]["sha256"] == hashlib.sha256(raw).hexdigest() == recorded[f"contracts/{key}.contract.json"]
        source = json.loads(raw.decode("utf-8-sig"))
        assert contract["contract_version"] == source["contract_version"]
        assert contract["business_keys"] == source["business_keys"]
        assert contract["schema"]["fields"] == [
            {"name": f["name"], "type": f["type"], "required": bool(f.get("required"))}
            for f in source["schema"]["fields"]]


def test_a_changed_contract_part_is_a_digest_mismatch(package):
    path = package.parent / "dataset_contracts.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(artifacts.ProcessPackError) as error:
        artifacts.load_bundle(package)
    assert error.value.reason_code == "PROCESS_PACK_DIGEST_MISMATCH"


def _contracts(package, mutate):
    path = package.parent / "dataset_contracts.json"
    doc = read_json(path)
    mutate(doc)
    write_json(path, doc)
    rehash(package, "dataset_contracts")


@pytest.mark.parametrize("damage,code", [
    ("missing_dataset", "PROCESS_PACK_REFERENCE_INVALID"),
    ("duplicate_dataset", "PROCESS_PACK_REFERENCE_INVALID"),
    ("key_not_a_field", "PROCESS_PACK_REFERENCE_INVALID"),
    ("no_business_key", "PROCESS_PACK_INVALID"),
    ("required_not_bool", "PROCESS_PACK_INVALID"),
    ("duplicate_field", "PROCESS_PACK_INVALID"),
    ("other_kit_version", "PROCESS_PACK_REFERENCE_INVALID"),
    ("approved_status", "PROCESS_PACK_INVALID"),
])
def test_contract_part_is_validated_before_pinning(package, damage, code):
    def mutate(doc):
        first = doc["contracts"][0]
        if damage == "missing_dataset":
            doc["contracts"].pop()
        elif damage == "duplicate_dataset":
            doc["contracts"].append(dict(first))
        elif damage == "key_not_a_field":
            first["business_keys"] = ["not_a_field"]
        elif damage == "no_business_key":
            first["business_keys"] = []
        elif damage == "required_not_bool":
            first["schema"]["fields"][0]["required"] = "yes"
        elif damage == "duplicate_field":
            first["schema"]["fields"].append(dict(first["schema"]["fields"][0]))
        elif damage == "other_kit_version":
            doc["version"] = "1.1.0"
        else:
            doc["review_status"] = "APPROVED"
    _contracts(package, mutate)
    with pytest.raises(artifacts.ProcessPackError) as error:
        artifacts.load_bundle(package)
    assert error.value.reason_code == code


def test_a_schema_one_manifest_cannot_carry_contracts(package):
    manifest = read_json(package)
    manifest["schema_version"] = 1
    write_json(package, manifest)
    with pytest.raises(artifacts.ProcessPackError) as error:
        artifacts.load_bundle(package)
    assert error.value.reason_code == "PROCESS_PACK_INVALID"


def test_a_schema_two_manifest_requires_contracts(package):
    manifest = read_json(package)
    manifest.pop("dataset_contracts")
    write_json(package, manifest)
    with pytest.raises(artifacts.ProcessPackError) as error:
        artifacts.load_bundle(package)
    assert error.value.reason_code == "PROCESS_PACK_INVALID"


def test_the_contract_path_must_stay_inside_the_package(package, tmp_path):
    outside = tmp_path / "outside.json"
    shutil.copyfile(package.parent / "dataset_contracts.json", outside)
    manifest = read_json(package)
    manifest["dataset_contracts"]["path"] = "../outside.json"
    write_json(package, manifest)
    with pytest.raises(artifacts.ProcessPackError) as error:
        artifacts.load_bundle(package)
    assert error.value.reason_code == "PROCESS_PACK_PATH_INVALID"
