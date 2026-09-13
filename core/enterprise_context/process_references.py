"""팩 원본 참조와 미해결 요구의 엄격한 형식. 실제 자산·실행 권한이 아니다."""
from typing import Literal

from pydantic import Field

from core.enterprise_context.process_schema import StrictModel


class TemplateSource(StrictModel):
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    pack_id: str = Field(min_length=1)
    pack_version: str = Field(min_length=1)
    kit_id: str = Field(min_length=1)
    kit_version: str = Field(min_length=1)
    initial_standard_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted_standard_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    template_process_ids: dict[str, str]
    kit_instance_ref: str = Field(min_length=1)


class Requirement(StrictModel):
    kind: Literal["DATA_REQUIREMENT"]
    process_id: str = Field(min_length=1)
    requirement_key: str = Field(min_length=1)
    candidate_dataset_keys: list[str]
    mandatory: bool
    state: Literal["UNRESOLVED"] = "UNRESOLVED"


class BlueprintSuggestion(StrictModel):
    kind: Literal["BLUEPRINT_SUGGESTION"]
    process_id: str = Field(min_length=1)
    kit_id: str = Field(min_length=1)
    kit_version: str = Field(min_length=1)
    app_id: str = Field(min_length=1)
    state: Literal["CANDIDATE_ONLY"] = "CANDIDATE_ONLY"


class ShortcutRequirement(StrictModel):
    kind: Literal["SHORTCUT_REQUIREMENT"]
    from_process_id: str = Field(min_length=1)
    target_template_key: str = Field(min_length=1)
    target_business_kit_id: str = Field(min_length=1)
    target_process_id: str = ""
    state: Literal["UNINSTALLED", "RESOLVED"]


def validate_references(doc, nodes):
    seen = set()
    covered = set()
    for source in doc["template_sources"]:
        source = TemplateSource.model_validate(source).model_dump()
        if source["artifact_digest"] in seen or not source["template_process_ids"]:
            raise ValueError("duplicate/empty template source")
        seen.add(source["artifact_digest"])
        for key, pid in source["template_process_ids"].items():
            if (pid in covered or pid not in nodes or nodes[pid]["template_key"] != key or
                    nodes[pid]["origin"] != "STANDARD" or nodes[pid]["source_ref"] != source["artifact_digest"]):
                raise ValueError("template node reference")
            covered.add(pid)
    if covered != {pid for pid, node in nodes.items() if node["origin"] == "STANDARD"}:
        raise ValueError("standard node source missing")
    known = set()
    for value in doc["bindings"]:
        model = Requirement if value.get("kind") == "DATA_REQUIREMENT" else BlueprintSuggestion
        ref = model.model_validate(value).model_dump()
        if ref["process_id"] not in covered:
            raise ValueError("binding process reference")
        key = (ref["kind"], ref["process_id"], ref.get("requirement_key", ref.get("app_id")))
        if key in known:
            raise ValueError("duplicate binding")
        known.add(key)
    for value in doc["relations"]:
        ref = ShortcutRequirement.model_validate(value).model_dump()
        if ref["from_process_id"] not in nodes:
            raise ValueError("relation source")
        if ref["state"] == "UNINSTALLED" and ref["target_process_id"]:
            raise ValueError("uninstalled target")
        if ref["state"] == "RESOLVED" and (ref["target_process_id"] not in nodes or
                nodes[ref["target_process_id"]]["template_key"] != ref["target_template_key"]):
            raise ValueError("relation target")
