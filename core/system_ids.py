"""LAXS 내부 객체 식별자 단일 발급 규칙.

사용자는 이름·목적·업무 내용을 정하고, 내부 ID는 시스템이 발급한다. 이 ID는 API·DB·원장
결속용이며 일반 화면의 표시명이 아니다. 기존 식별자는 그대로 보존하고 신규 객체부터 이
규칙을 적용한다.

형식: ``<객체 접두어>_<80비트 난수(소문자 16진수)>``

시간·회사명·사용자 입력을 넣지 않는다. 이름을 바꿔도 정체성이 바뀌지 않고, 조직 정보가 ID를
통해 새지 않으며, 여러 프로세스가 중앙 카운터 없이 발급해도 충돌 가능성이 충분히 낮다.
"""
from __future__ import annotations

import re
import secrets
from typing import Final


OBJECT_PREFIXES: Final[dict[str, str]] = {
    "agent": "agt",
    "workflow": "wfl",
    "project": "prj",
    "company": "ent",
    "department": "dep",
    "knowledge_pack": "kpk",
    "dataset": "dst",
    "decision": "dcs",
    "release": "rel",
    "scenario": "scn",
    "scenario_release": "scr",
    "driver_release": "drr",
    "simulation_run": "sim",
    "baseline": "bln",
    "external_source": "src",
    "external_indicator": "xid",
    "external_system": "xsy",
    "research_profile": "rsp",
    "master_type": "mtp",
    "master_record": "mrc",
    "output_format": "fmt",
    "process_stage": "stg",
}

_SYSTEM_ID = re.compile(r"^[a-z]{3}_[0-9a-f]{20}$")


def allocate(object_type: str, count: int = 1) -> list[str]:
    """객체 유형에 맞는 내부 ID를 발급한다. 발급은 영속 상태를 만들지 않는다."""
    kind = str(object_type or "").strip().lower()
    if kind not in OBJECT_PREFIXES:
        raise ValueError(f"지원하지 않는 객체 유형입니다: {kind or '(비어 있음)'}")
    if not 1 <= int(count) <= 20:
        raise ValueError("한 번에 발급할 수 있는 ID는 1~20개입니다.")
    prefix = OBJECT_PREFIXES[kind]
    return [f"{prefix}_{secrets.token_hex(10)}" for _ in range(int(count))]


def is_system_id(value: str, object_type: str = "") -> bool:
    """신규 발급 규칙의 ID인지 확인한다. 레거시 ID의 유효성을 판정하는 함수가 아니다."""
    text = str(value or "").strip()
    if not _SYSTEM_ID.fullmatch(text):
        return False
    if object_type:
        prefix = OBJECT_PREFIXES.get(str(object_type).strip().lower())
        return bool(prefix and text.startswith(f"{prefix}_"))
    return True
