"""[§7.1 / §7.2] 커넥터 실행 — 계약을 **요청뿐 아니라 응답에도** 적용한다.

`connector_registry` 는 Query Contract 를 등록하고 **요청**을 검사한다. 그런데 요청만 검사하면
최소 권한이 절반만 지켜진다 — 원천이 요청보다 더 준 것을 그대로 흘리면 계약이 무의미하다.
이 모듈이 그 나머지 절반이다.

## 왜 응답도 걸러야 하나

커넥터 구현은 우리가 통제하지 않는다(외부 시스템의 API·SQL 뷰·MCP 서버). 요청에 필드 3개를
적어도 응답이 12개 컬럼을 줄 수 있고, `limit=100` 을 걸어도 500행이 올 수 있다.
"우리는 정확히 요청했다"는 항변은 유출 사고에서 아무 의미가 없다. 그래서:
  · 계약에 없는 컬럼은 **버린다**(그리고 버렸다고 말한다 — 조용히 지우면 원천 결함을 못 본다)
  · 상한 초과 행은 **자른다**(그리고 잘렸다고 말한다 — 조용히 자르면 부분 데이터를 전체로 오독한다)
  · `for_prompt` 경로는 민감 필드를 한 번 더 제거한다(§7.2)

## 어댑터를 만들지 않았다

실제 원천에 붙는 어댑터는 시스템마다 다르고, 지금 승인된 원천이 없다. 그래서 **인터페이스와
등록부만** 두고 구현은 각 원천이 승인될 때 붙인다(외부 인텔리전스 수집기·Shadow Mode 실행기와
같은 판단).
⚠️ 미설정 어댑터는 **빈 결과가 아니라 명시적 실패**다. 빈 결과를 돌려주면 "조회했는데 데이터가
  없다"로 읽히고, 그건 "조회 자체를 못 했다"와 완전히 다른 사실이다.

## 목적(purpose)은 필수다

§7.2: "모든 조회에는 요청자, **목적**, 데이터 범위, 시각, 결과 요약을 감사 로그로 남긴다."
목적이 없으면 감사로그가 "누가 무엇을 봤나"만 남고 **"왜"** 가 빠진다 — 사후에 정당성을
판단할 수 없다. 거부된 조회도 남긴다(거부된 시도가 침해 시도의 신호다).

LLM 0콜.
"""
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

#: 어댑터 시그니처: (query_name, fields, params, limit) -> {"rows": [...], "source": "..."}
Adapter = Callable[[str, List[str], Dict[str, Any], int], Dict[str, Any]]

_adapters: Dict[str, Adapter] = {}


class ConnectorExecutionError(ValueError):
    """검증/정책 위반 등 4xx 로 전달할 도메인 오류."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_adapter(connector_id: str, adapter: Adapter) -> None:
    """원천 어댑터를 등록한다. 승인된 원천이 생길 때 그 형태에 맞춰 붙인다."""
    if not callable(adapter):
        raise ConnectorExecutionError("adapter 는 호출 가능해야 합니다.")
    _adapters[connector_id] = adapter


def unregister_adapter(connector_id: str) -> bool:
    return _adapters.pop(connector_id, None) is not None


def registered_adapters() -> List[str]:
    return sorted(_adapters)


def _audit(event: str, connector_id: str, query_name: str, actor: str, purpose: str,
           outcome: str, reason: str, detail: str) -> None:
    """감사 기록. 실패해도 조회를 죽이지 않지만 조용히 넘기지도 않는다."""
    try:
        from core.enterprise_context import audit
        audit.record(event, resource_type="connector_query",
                     resource_id=f"{connector_id}/{query_name}",
                     actor=actor or audit.ANONYMOUS, outcome=outcome,
                     reason=reason, detail=detail)
    except Exception as e:                                        # pragma: no cover
        print(f"⚠️ [connector] 감사 기록 실패: {e}")


def execute(connector_id: str, query_name: str, fields: List[str], actor: str,
            purpose: str, params: Optional[Dict[str, Any]] = None, limit: int = 0,
            for_prompt: bool = False, registry=None) -> Dict[str, Any]:
    """Query Contract 를 지켜 조회하고, **응답에도 계약을 적용**한다.

    반환의 `enforcement` 를 무시하지 말 것 — 원천이 계약을 어겼다는 사실이 거기 담긴다."""
    from core.connector_registry import connector_registry as _reg
    reg = registry or _reg
    from core.enterprise_context import audit

    if not (actor or "").strip():
        raise ConnectorExecutionError(
            "actor 는 필수입니다 — 요청자 없는 조회는 감사 대상이 될 수 없습니다(§7.2).")
    if not (purpose or "").strip():
        # 목적을 옵션으로 두면 아무도 적지 않고, 감사로그에 "왜"가 영구히 빠진다.
        raise ConnectorExecutionError(
            "purpose 는 필수입니다 — §7.2 는 목적을 감사 항목으로 규정합니다. 목적이 없으면 "
            "사후에 이 조회가 정당했는지 판단할 수 없습니다.")

    v = reg.validate_request(connector_id, query_name, fields, params, limit, for_prompt)
    if not v.get("allowed"):
        _audit(audit.CONNECTOR_QUERY_DENIED, connector_id, query_name, actor, purpose,
               "denied", "; ".join(v.get("errors", []))[:300], f"purpose={purpose}")
        return {"executed": False, "rows": [], "errors": v.get("errors", []),
                "note": ("계약 위반으로 실행하지 않았습니다. 거부 기록이 감사로그에 남습니다 — "
                         "거부된 시도가 침해 시도의 신호입니다.")}

    eff_fields: List[str] = list(v["effective_fields"])
    eff_limit = int(v["limit"])

    if not eff_fields:
        # 필드가 하나도 없으면 응답 필터가 모든 컬럼을 지워 `[{}, {}, ...]` 가 된다 —
        # "행은 있는데 값이 없는" 결과는 데이터 부재로 오독된다. 실행 전에 막는다.
        removed = v.get("removed_sensitive", [])
        raise ConnectorExecutionError(
            ("요청한 필드가 모두 민감 필드로 제거되어 조회할 컬럼이 없습니다"
             f"(제거: {', '.join(removed)}). 프롬프트 주입 경로에서는 이 값을 쓸 수 없습니다(§7.2)."
             if removed else
             "조회할 필드가 없습니다 — fields 를 지정하십시오. 빈 fields 로 실행하면 "
             "값 없는 빈 행이 돌아와 데이터 부재로 오독됩니다."))

    adapter = _adapters.get(connector_id)
    if adapter is None:
        # ★ 빈 결과가 아니라 실패다. 빈 결과는 "데이터가 없다"로 읽히고, 그건 "조회를 못 했다"와
        #   완전히 다른 사실이다.
        _audit(audit.CONNECTOR_QUERY_DENIED, connector_id, query_name, actor, purpose,
               "denied", "어댑터 미설정", f"purpose={purpose}")
        raise ConnectorExecutionError(
            f"'{connector_id}' 에 실행 어댑터가 없습니다. 계약은 통과했지만 조회를 수행할 수 "
            f"없습니다 — 빈 결과로 돌려주면 '데이터가 없다'로 오독됩니다. "
            f"등록된 어댑터: {registered_adapters() or '없음'}")

    try:
        raw = adapter(query_name, eff_fields, dict(params or {}), eff_limit) or {}
    except Exception as e:
        _audit(audit.CONNECTOR_QUERY_DENIED, connector_id, query_name, actor, purpose,
               "denied", f"어댑터 오류: {e}"[:300], f"purpose={purpose}")
        raise ConnectorExecutionError(f"원천 조회에 실패했습니다: {e}")

    rows_in = list(raw.get("rows") or [])

    # ── 응답에 계약을 적용한다 ───────────────────────────────────────────
    allowed = set(eff_fields)
    extra_cols, kept_rows = set(), []
    for r in rows_in:
        if not isinstance(r, dict):
            # 형태가 다르면 필드 단위 통제가 불가능하다 — 통과시키면 계약이 무의미해진다.
            extra_cols.add("<non-dict row>")
            continue
        extra_cols |= (set(r) - allowed)
        kept_rows.append({k: v2 for k, v2 in r.items() if k in allowed})

    truncated = max(0, len(kept_rows) - eff_limit)
    rows = kept_rows[:eff_limit]

    enforcement = {
        "requested_fields": list(fields or []),
        "effective_fields": eff_fields,
        "removed_sensitive": v.get("removed_sensitive", []),
        # ★ 원천이 계약에 없는 컬럼을 줬다는 것은 **원천 쪽 결함**이다. 조용히 지우면
        #   그 결함이 영원히 안 고쳐진다.
        "dropped_columns": sorted(extra_cols),
        "rows_from_source": len(rows_in),
        "rows_returned": len(rows),
        "rows_truncated": truncated,
        "limit": eff_limit,
        "contract_violations_by_source": (
            (["계약에 없는 컬럼 반환: " + ", ".join(sorted(extra_cols))] if extra_cols else [])
            + ([f"상한 초과 행 반환: {len(rows_in)} > {eff_limit}"] if truncated else [])),
    }
    _audit(audit.CONNECTOR_QUERY_EXECUTED, connector_id, query_name, actor, purpose,
           "allowed", "",
           f"purpose={purpose} fields={len(eff_fields)} rows={len(rows)}/{len(rows_in)} "
           f"dropped_cols={len(extra_cols)} truncated={truncated}")

    return {
        "executed": True, "connector_id": connector_id, "query_name": query_name,
        "actor": actor, "purpose": purpose, "at": _now(),
        "rows": rows, "enforcement": enforcement, "source": raw.get("source", ""),
        "note": ("계약은 요청과 **응답 양쪽**에 적용됩니다. `enforcement."
                 "contract_violations_by_source` 가 비어 있지 않으면 원천이 계약을 어긴 것이며, "
                 "그것은 원천 쪽에서 고쳐야 합니다."),
    }


def fetch_for_prompt(connector_id: str, query_name: str, fields: List[str], actor: str,
                     purpose: str, params: Optional[Dict[str, Any]] = None,
                     limit: int = 0, registry=None) -> Dict[str, Any]:
    """프롬프트 주입용 조회 — 민감 필드를 제거한다(§7.2).

    ⚠️ 제거는 오류가 아니지만 **말하지 않으면** LLM 도 사람도 값이 왜 없는지 모른다."""
    out = execute(connector_id, query_name, fields, actor, purpose, params, limit,
                  for_prompt=True, registry=registry)
    removed = out.get("enforcement", {}).get("removed_sensitive", [])
    if removed:
        out["prompt_note"] = (f"민감 필드 {', '.join(removed)} 는 프롬프트에 전달되지 "
                              f"않았습니다(§7.2). 이 값을 추정하지 마십시오.")
    return out
