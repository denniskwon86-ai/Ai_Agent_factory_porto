"""영속 체크포인트에서 HOTL 요청 회차와 질문 지문만 파생한다.

시간·UUID·메모리 카운터를 사용하지 않으므로 같은 체크포인트 재조회·재시작은
같은 토큰이다. 이 토큰은 권한 증명이 아니다. 호출자는 프로젝트에 결속된 그래프를
조회하고, 쓰기 직전 같은 함수로 두 토큰 및 현재 대기 상태를 재검증해야 한다.
질문 원문·체크포인트 원문·예외 내용은 반환하지 않는다.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
from typing import Any


_MISSING = object()


def _result(status: str, reason_code: str, *, request_id: str = "",
            questions_digest: str = "", decision_kind: str = "") -> dict:
    pending = status == "PENDING"
    return {
        "status": status, "pending": pending, "available": pending,
        "reason_code": reason_code, "request_id": request_id,
        "questions_digest": questions_digest, "decision_kind": decision_kind,
    }


def _field(values: Any, key: str, default: Any = _MISSING) -> Any:
    # LangGraph의 사전 상태와 기존 오케스트레이터의 모델 상태를 모두 읽는다.
    return values.get(key, default) if isinstance(values, Mapping) else getattr(values, key, default)


def _identifier(value: Any) -> bool:
    return (isinstance(value, str) and bool(value) and value == value.strip()
            and not any(ord(char) < 32 for char in value))


def _json_value(value: Any) -> None:
    """키 문자열화·객체 문자열화·비유한 수의 묵시 변환을 허용하지 않는다."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json_value(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _json_value(item)
        return
    raise ValueError("질문은 유한한 JSON 값이어야 합니다.")


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def hotl_context(snapshot: Any, *, project_id: str, task_id: str,
                 running: bool = False) -> dict:
    """서버가 조회한 StateSnapshot을 부작용 없이 공개 가능한 대기 문맥으로 바꾼다.

    PENDING만 available/pending이 True이며 두 토큰을 제공한다. 실행 중·쿼터 중단·
    다음 노드 없음은 NOT_PENDING, 근거 누락·손상은 UNKNOWN이다. 두 경우 모두
    토큰과 decision_kind를 비운다. parent_config·metadata의 ID로 대체하지 않는다.

    request_id의 재료는 project_id/task_id/checkpoint_id/next_nodes 네 키이다.
    질문 지문은 실제 clarification_questions 전체를 해시한다. 사전 키만 정렬하며
    노드·질문·선택지 순서는 보존한다. 명확화 단계의 명시적 빈 목록은 허용한다.
    명확화 외 단계의 질문 필드 부재만 모델 기본값인 빈 목록으로 해석한다.
    """
    if type(running) is not bool:
        return _result("UNKNOWN", "HOTL_RUNNING_INVALID")
    if running:
        return _result("NOT_PENDING", "HOTL_RUNNING")
    try:
        if snapshot is None:
            return _result("UNKNOWN", "HOTL_SNAPSHOT_UNAVAILABLE")
        next_nodes = getattr(snapshot, "next", _MISSING)
        if next_nodes is _MISSING:
            return _result("UNKNOWN", "HOTL_SNAPSHOT_INVALID")
        if next_nodes is None or (isinstance(next_nodes, (tuple, list)) and not next_nodes):
            return _result("NOT_PENDING", "HOTL_NO_NEXT_NODES")
        if not isinstance(next_nodes, (tuple, list)) or not all(_identifier(n) for n in next_nodes):
            return _result("UNKNOWN", "HOTL_NEXT_NODES_INVALID")

        values = getattr(snapshot, "values", None)
        if values is None or (isinstance(values, Mapping) and not values):
            return _result("UNKNOWN", "HOTL_STATE_UNAVAILABLE")
        mode = _field(values, "factory_mode")
        stage = _field(values, "current_stage")
        if mode == "SUSPENDED_QUOTA":
            return _result("NOT_PENDING", "HOTL_SUSPENDED_QUOTA")
        if (not isinstance(values, Mapping) and mode is _MISSING and stage is _MISSING):
            return _result("UNKNOWN", "HOTL_STATE_INVALID")
        if stage is not _MISSING and not isinstance(stage, str):
            return _result("UNKNOWN", "HOTL_STAGE_INVALID")
        if not _identifier(project_id) or not _identifier(task_id):
            return _result("UNKNOWN", "HOTL_IDENTITY_INVALID")

        config = getattr(snapshot, "config", None)
        configurable = config.get("configurable") if isinstance(config, Mapping) else None
        checkpoint_id = configurable.get("checkpoint_id") if isinstance(configurable, Mapping) else None
        if not _identifier(checkpoint_id):
            return _result("UNKNOWN", "HOTL_CHECKPOINT_ID_UNAVAILABLE")

        kind = "CLARIFICATION" if stage == "CLARIFICATION" else "GENERAL_HOTL"
        questions = _field(values, "clarification_questions")
        if questions is _MISSING and kind == "GENERAL_HOTL":
            questions = []
        if type(questions) is not list or not all(type(q) is dict for q in questions):
            return _result("UNKNOWN", "HOTL_QUESTIONS_INVALID")
        _json_value(questions)
        return _result("PENDING", "HOTL_PENDING", request_id=_digest({
            "project_id": project_id, "task_id": task_id,
            "checkpoint_id": checkpoint_id, "next_nodes": list(next_nodes),
        }), questions_digest=_digest(questions), decision_kind=kind)
    except (AttributeError, TypeError, ValueError, RecursionError, UnicodeError):
        # 입력 손상으로 계산에 실패해도 토큰 일부나 질문·예외 원문을 노출하지 않는다.
        return _result("UNKNOWN", "HOTL_SNAPSHOT_INVALID")
