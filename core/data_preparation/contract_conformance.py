"""인증 전 계약 대조 — 판의 열·업무키가 **데이터셋 계약**과 맞는가.

## 왜 필요한가 (2026-09-24 Codex §16 검토, 실측)

인증(수집·프로파일·표준화·대사·서명)은 판의 열을 데이터셋 계약과 대조하지 않았다. 앱 계약의
필드는 인증판 스키마에서 그대로 오므로(`kit_app_builder.fields_from_certified`), 정본
INV-01 에 없는 `amount` 한 칸짜리 판이 인증 → 계약 승인 → 게시 → 운영 조회까지 통과했다.

## 무엇을 보는가 — 세 가지만

1. `MISSING_FIELD` — 계약의 필수 필드·업무키 열이 판에 없다.
2. `EMPTY_BUSINESS_KEY` — 어떤 행의 업무키 값이 비었다(공백만 있어도 빈 것이다).
3. `DUPLICATE_BUSINESS_KEY` — 두 행이 같은 업무키를 갖는다(복합 키는 전체 튜플로 본다).

⚠️ 합성 표본 점검(`kit_sample_audit.inspect_rows`)과 다르다. 그쪽은 표본의 합성 출처·교차
  참조까지 보는 **읽기 전용 점검**이고 «통과가 인증이 아니다». 여기는 인증을 막는 관문이라
  실제 자료에 맞지 않는 검사(합성 출처 요구 등)를 넣지 않는다. 코드 이름과 «머리글 포함 줄
  번호» 관례는 그쪽과 같게 둔다.
⚠️ 결과에 **값을 싣지 않는다** — 줄 번호와 필드 이름만. 업무키 값은 자료다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from core.data_preparation import models as m

MISSING_FIELD = "MISSING_FIELD"
EMPTY_BUSINESS_KEY = "EMPTY_BUSINESS_KEY"
DUPLICATE_BUSINESS_KEY = "DUPLICATE_BUSINESS_KEY"


class ContractShapeError(m.DataPreparationError):
    """계약 자체를 읽을 수 없다. **대조를 건너뛰지 않는다** — 모르는 계약은 통과 근거가 아니다."""


def requirements(contract: Any) -> Tuple[List[str], List[str]]:
    """계약 → (반드시 있어야 할 열, 업무키). 업무키는 필수 열에도 들어간다.

    ⚠️ 업무키가 없는 계약은 받지 않는다. 키가 없으면 «빈 키»·«중복» 을 물을 수 없고, 그러면
      이 관문은 열 이름만 보는 절반짜리가 된다."""
    if not isinstance(contract, dict):
        raise ContractShapeError("데이터셋 계약을 읽을 수 없습니다.")
    schema = contract.get("schema")
    fields = schema.get("fields") if isinstance(schema, dict) else None
    if not isinstance(fields, list) or not fields:
        raise ContractShapeError("데이터셋 계약에 필드 목록이 없습니다.")
    names: List[str] = []
    required: List[str] = []
    for field in fields:
        name = str(field.get("name") or "").strip() if isinstance(field, dict) else ""
        if not name or name in names:
            raise ContractShapeError("데이터셋 계약의 필드 이름이 비었거나 중복됩니다.")
        names.append(name)
        if field.get("required") is True:
            required.append(name)
    keys = contract.get("business_keys")
    if (not isinstance(keys, list) or not keys
            or any(not isinstance(k, str) or k not in names for k in keys)
            or len(set(keys)) != len(keys)):
        raise ContractShapeError("데이터셋 계약의 업무키가 없거나 필드 목록에 없습니다.")
    return required + [k for k in keys if k not in required], list(keys)


def inspect(contract: Any, columns: Sequence[str],
            rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """계약과 표를 대조해 **어긋남 목록**을 돌려준다. 비어 있으면 통과다.

    ★ 필수 열이 하나라도 없으면 행 검사는 하지 않는다 — 없는 열의 값은 전부 «빈 것» 으로
      보여 같은 사실이 행 수만큼 반복된다."""
    required, keys = requirements(contract)
    present = set(columns or [])
    missing = [name for name in required if name not in present]
    if missing:
        return [{"code": MISSING_FIELD, "fields": missing}]
    issues: List[Dict[str, Any]] = []
    first_seen: Dict[Tuple[str, ...], int] = {}
    for line, row in enumerate(rows, 2):
        identity = tuple(str(row.get(k) or "").strip() for k in keys)
        empty = [k for k, value in zip(keys, identity) if not value]
        if empty:
            issues.append({"code": EMPTY_BUSINESS_KEY, "line": line, "fields": empty})
            continue
        if identity in first_seen:
            issues.append({"code": DUPLICATE_BUSINESS_KEY, "line": line,
                           "first_line": first_seen[identity], "fields": list(keys)})
            continue
        first_seen[identity] = line
    return issues


def sealed_table(snapshot: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, str]]]:
    """판이 **봉인한 원문**을 읽는다 — 지문을 먼저 대조하고, 파싱한 바이트의 지문도 다시 본다.

    ★ 대조는 호출자가 넘기는 행이 아니라 이 원문으로 한다. 프로파일·대사 단계의 행은 호출자가
      준 것이라, 그것으로 보면 «검사한 것» 과 «인증한 것» 이 다를 수 있다.
    ⚠️ 원문이 없거나 바뀌었으면 대조하지 않고 막는다 — 못 본 것을 통과로 세지 않는다."""
    from core.data_preparation import certification_authority as auth
    from core.data_preparation import snapshot_service as ss

    path = str(snapshot.get("raw_path") or "")
    expected = str(snapshot.get("checksum") or "")
    if not path or not expected:
        raise auth.CertificationError("RAW_UNAVAILABLE",
                                      "인증할 원문이 없습니다 — 계약 대조 없이 서명하지 않습니다.")
    try:
        with open(path, "rb") as stream:
            payload = stream.read()
    except OSError as exc:
        raise auth.CertificationError("RAW_UNAVAILABLE", "인증할 원문을 읽지 못했습니다.", 503) from exc
    if ss.checksum_bytes(payload) != expected:
        raise auth.CertificationError("RAW_CHECKSUM_MISMATCH",
                                      "원문이 수집 때와 다릅니다 — 새 Snapshot 이 필요합니다.")
    parsed = ss.parse_csv(payload, file_name=path)
    if parsed.checksum != expected:
        raise auth.CertificationError("RAW_CHECKSUM_MISMATCH",
                                      "원문이 수집 때와 다릅니다 — 새 Snapshot 이 필요합니다.")
    return list(parsed.columns), list(parsed.rows)
