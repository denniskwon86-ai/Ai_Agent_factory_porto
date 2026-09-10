"""★★★ [G2 B2 / M0-2] **경로 단위 계산 실행기** — 관문 7개와 지문 2개.

계약: `docs/handoff/G2_A_PATH_CALCULATION_CONTRACT_2026-08-21.md`

## 이 파일의 자리

    온톨로지 런타임(경로) → **여기** → G5 의사결정·브리핑

`core/calc_models.py` 는 산식이고 저장소·승인을 모른다. 이 파일은 그 산식을 **승인과
봉인 아래에서** 돌린다. 둘을 한 파일에 두면 계산을 시험하려면 DB 를 세워야 하고, 그러면
산식이 틀렸는지 배선이 틀렸는지 구분할 수 없다.

## 지문 둘 (§3)

    request_fingerprint  「이 질문은 무엇이었나」  — 언제나 만든다
    result_fingerprint   「이 숫자는 무엇으로 만들었나」 — COMPLETE 일 때만

⚠️⚠️ rev.1 은 앞엣것만 만들고 뒤엣것의 이름을 붙였다. 그러면 산식이 바뀌어 **값이
달라져도 지문이 같아서** 재현 검증이 통과한다.

⚠️⚠️ `BLOCKED` 에는 결과 지문을 만들지 않는다(§3.7). 수치가 없는데 결과 지문을 만들면
그 지문이 「계산된 결과」의 증거처럼 쓰인다.

## 부분 결과를 만들지 않는다 (§2)

한 구간이라도 막히면 **경로 전체가 `BLOCKED`** 다. 부분 수치를 내보내면 화면은 일부
숫자를 보여 주고, 사람은 그것을 전체로 읽는다.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from core import calc_capability as cc
from core import calc_models as cm
from core import calc_projection as cp

#: 경로 전체의 판 — 실행 순서·집계·반올림·기준선 비교 규칙(§4).
#: ⚠️ 구간 산식이 그대로여도 이 규칙이 바뀌면 답이 달라진다. 그것은 구간의 판이 아니다.
PATH_MODEL_VERSION = "1.0.0"

COMPLETE = "COMPLETE"
BLOCKED = "BLOCKED"

#: 일반 화면과 API가 사용하는 **닫힌 차단 사유 어휘**.
#:
#: ⚠️ 내부 관계 ID·계약키·계산 참조·건수는 여기에 들어가지 않는다. 그것들은 권한이
#: 분리된 운영 진단의 근거이지 일반 사용자가 다음 행동을 정하는 데 필요한 정보가 아니다.
RELATION_APPROVAL_REQUIRED = "RELATION_APPROVAL_REQUIRED"
CALCULATION_APPROVAL_REQUIRED = "CALCULATION_APPROVAL_REQUIRED"
DATA_NOT_READY = "DATA_NOT_READY"
DATA_CONTRACT_INCOMPLETE = "DATA_CONTRACT_INCOMPLETE"
BASELINE_NOT_READY = "BASELINE_NOT_READY"

BLOCK_REASON_CATALOG: Dict[str, Dict[str, str]] = {
    RELATION_APPROVAL_REQUIRED: {
        "category": "approval",
        "message": "이 경로의 관계 승인을 확인해야 합니다.",
        "next_action": "온톨로지 관계 검토 화면에서 승인 상태를 확인하십시오.",
    },
    CALCULATION_APPROVAL_REQUIRED: {
        "category": "approval",
        "message": "이 경로에 필요한 계산이 아직 실행 승인되지 않았습니다.",
        "next_action": "계산 실행 승인 화면에서 산식 정의와 적용 범위를 검토하십시오.",
    },
    DATA_NOT_READY: {
        "category": "data",
        "message": "이 경로에 필요한 인증 데이터가 아직 준비되지 않았습니다.",
        "next_action": "데이터 준비 상태에서 인증판과 결속 상태를 확인하십시오.",
    },
    DATA_CONTRACT_INCOMPLETE: {
        "category": "data",
        "message": "계산에 필요한 업무 데이터의 연결 조건이 충족되지 않았습니다.",
        "next_action": "데이터 준비 상태에서 필수 열과 업무 연결 상태를 점검하십시오.",
    },
    BASELINE_NOT_READY: {
        "category": "baseline",
        "message": "비교에 필요한 기준선이 아직 준비되지 않았습니다.",
        "next_action": "기준선 관리 화면에서 적용 기준선과 대상 기간을 확인하십시오.",
    },
}

#: 이 경로가 쓰는 구간 순서. **앞 구간의 결과가 뒤 구간의 입력**이다.
#: ⚠️ 순서를 바꾸면 답이 달라지므로 `PATH_MODEL_VERSION` 이 함께 올라가야 한다.
SEGMENTS: Tuple[str, ...] = (
    "CALC.LOGISTICS.ARRIVAL_DELAY.v1",
    "CALC.INVENTORY.MATERIAL_SHORTAGE.v1",
    "CALC.PRODUCTION.REVENUE_TIMING.v1",
)

#: 이 경로에 필요한 계약키 — 구간들의 합집합 **+ 투영에 필요한 것**.
#:
#: ⚠️⚠️ [P0-CALC-INPUT] `PRC-02` 가 들어간다. 계산 능력 등록부에는 없지만, **`LOG-02` 에
#:   자재 ID 가 없어서** 주문행을 거치지 않으면 「어느 자재의 선적인가」를 알 수 없다.
#:   등록부의 `required_datasets` 만 믿으면 정본으로는 한 줄도 계산되지 않는다.
REQUIRED_DATASETS: Tuple[str, ...] = tuple(sorted(
    {k for ref in SEGMENTS for k in cc.get(ref).required_datasets}
    | set(cp.PROJECTION_DATASETS)))


class PathCalculationError(Exception):
    """무결성 장애(503). ⚠️ `BLOCKED` 와 **다르다** — 저쪽은 정상적인 「아직 못 한다」다."""


@dataclass(frozen=True)
class PathCalculationRequest:
    """§5 입력 계약. ⚠️ 정체성 세 값과 `as_of` 는 **경로 전체가 하나를 쓴다.**"""

    query_id: str
    path_fingerprint: str
    tenant_id: str
    entity_mode: str
    scope_node_id: str
    as_of: str
    baseline_id: str
    baseline_fingerprint: str
    #: {계약키: snapshot_id} — 관계 승인 때 봉인된 판.
    sealed_snapshots: Mapping[str, str]
    #: {relation_id: ledger_event_id}
    relation_approvals: Mapping[str, str]
    assumptions: Mapping[str, Any] = field(default_factory=dict)
    #: ★★★ [P0-CALC-PROOF] **경로 봉투가 요구하는 관계 ID 집합.**
    #:
    #: ⚠️⚠️ 앞 판은 `relation_approvals` 가 비었는지만 봤다. 그래서 **관계 승인 하나만
    #:   제출해도 COMPLETE** 가 나왔다(실측) — 경로에 관계가 넷이든 승인 하나면 통과했다.
    #: ★ 승인은 «몇 개 냈는가» 가 아니라 «이 경로의 모든 관계가 승인됐는가» 다. 그래서
    #:   경로가 요구하는 집합을 받아 **정확히 일치**하는지 본다.
    required_relation_ids: Tuple[str, ...] = ()
    #: ⚠️ 호출자가 주장하는 판. **코드의 `PATH_MODEL_VERSION` 과 다르면 거부**한다 —
    #:   앞 판은 이 값을 그대로 지문에 실어서 `"0.0.0-fake"` 로도 COMPLETE 가 됐다(실측).
    path_model_version: str = PATH_MODEL_VERSION

    def identity_missing(self) -> List[str]:
        """비어 있으면 안 되는 값들. ⚠️ 하나라도 비면 **다른 조직 계산과 구분할 수 없다.**"""
        need = {"query_id": self.query_id, "path_fingerprint": self.path_fingerprint,
                "tenant_id": self.tenant_id, "entity_mode": self.entity_mode,
                "scope_node_id": self.scope_node_id, "as_of": self.as_of,
                "baseline_id": self.baseline_id,
                "baseline_fingerprint": self.baseline_fingerprint}
        return sorted(k for k, v in need.items() if not str(v or "").strip())


def _canon(value: Any) -> Any:
    """지문에 넣기 전 정규형. **정렬**하고, 수는 문자열로 굳힌다.

    ⚠️ dict 순회 순서가 지문을 흔들면 같은 질문이 다른 지문을 갖는다.
    ⚠️ float 을 그대로 넣으면 `0.1+0.2` 같은 표현 차이가 지문을 바꾼다."""
    if isinstance(value, Mapping):
        return {str(k): _canon(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    if isinstance(value, float):
        return f"{value:.6f}"
    if isinstance(value, bool) or value is None:
        return value
    return str(value)


def _sha(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(_canon(payload), ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _utc_iso(text: str) -> str:
    """`as_of` 를 UTC 로 정규화한다. 지문이 표기에 흔들리지 않게."""
    raw = str(text or "").strip()
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise PathCalculationError(
            f"as_of 에 시간대가 없습니다({raw!r}) — 경로 전체가 이 값 하나를 씁니다.")
    return dt.astimezone(timezone.utc).isoformat()


def request_fingerprint(req: PathCalculationRequest,
                        segment_capability_fingerprints: Mapping[str, str]) -> str:
    """§3.1 — 「이 질문은 무엇이었나」.

    ★ `segment_capability_fingerprints` 는 **실제로 쓴 참조만** 넣는다(§3.5). 전체
      Registry 를 넣으면 범위 밖 참조의 산식을 고치는 순간 MVP 결과가 전부 무효가 되고,
      관계없는 변경이 남의 증명을 깨뜨리면 사람은 지문 검증을 끄게 된다."""
    return _sha({
        "query_id": req.query_id,
        "path_fingerprint": req.path_fingerprint,
        "tenant_id": req.tenant_id,
        "entity_mode": req.entity_mode,
        "scope_node_id": req.scope_node_id,
        "as_of": _utc_iso(req.as_of),
        "baseline_id": req.baseline_id,
        "baseline_fingerprint": req.baseline_fingerprint,
        "sealed_snapshots": req.sealed_snapshots,
        "relation_approvals": req.relation_approvals,
        #: ★ 경로가 요구한 관계 집합도 질문의 일부다 — 같은 승인을 냈어도 «어느 경로의
        #:   질문이었나» 가 다르면 다른 질문이다.
        "required_relation_ids": sorted(req.required_relation_ids),
        "assumptions": req.assumptions,
        "path_model_version": req.path_model_version,
        "segment_capability_fingerprints": segment_capability_fingerprints,
    })


def result_fingerprint(*, request_fp: str, metrics: Mapping[str, Any],
                       segment_outputs: Mapping[str, Any],
                       used_snapshots: Mapping[str, str]) -> str:
    """§3.1 — 「이 숫자는 무엇으로 만들었나」. **COMPLETE 일 때만** 만든다."""
    return _sha({"request_fingerprint": request_fp, "metrics": metrics,
                 "segment_outputs": segment_outputs, "used_snapshots": used_snapshots})


def _blocked(req: PathCalculationRequest, seg_fps: Mapping[str, str], *,
             reason_code: str, internal: Sequence[str]) -> Dict[str, Any]:
    """§2.1 — 차단 사유를 **두 층**으로 낸다.

    ⚠️⚠️ 대외 사유에 내부 식별자·구간 이름·건수를 넣으면 **차단 사유가 누설이 된다**
      (「승인되지 않은 관계 3건」은 그 조직에 관계가 3건 있다는 뜻이다)."""
    definition = BLOCK_REASON_CATALOG.get(reason_code)
    if definition is None:
        raise PathCalculationError(f"unknown blocked reason code: {reason_code!r}")
    public_reason = {
        "code": reason_code,
        "category": definition["category"],
        "message": definition["message"],
        "next_action": definition["next_action"],
    }
    return {
        "status": BLOCKED,
        #: ★ 막혔어도 **어느 질문이 막혔는가**는 답할 수 있어야 한다.
        "query_id": req.query_id,
        "path_fingerprint": req.path_fingerprint,
        # 전사 시나리오와 G5가 같은 비교 기준을 증명할 수 있도록 결과에도 보존한다.
        # request_fingerprint 안에만 숨기면 저장 단계에서 원래 값을 복원할 수 없다.
        "baseline_id": req.baseline_id,
        "baseline_fingerprint": req.baseline_fingerprint,
        "required_relation_ids": sorted(req.required_relation_ids),
        "request_fingerprint": request_fingerprint(req, seg_fps),
        #: ★ 수치는 비어 있다. 빈 dict 를 0 으로 읽지 못하게 `metrics` 자체를 비운다.
        "metrics": {},
        "segment_outputs": {},
        "segment_model_versions": {},
        "used_snapshots": {},
        "blocked": {
            "reason_code": reason_code,
            #: 호환 필드도 닫힌 카탈로그의 안전한 문장만 쓴다.
            "public_reason": definition["message"],
            "reasons": [public_reason],
            #: 코어 내부 회귀·권한 분리 진단용. API 경계에서 반드시 제거한다.
            "internal_reasons": list(internal),
        },
    }


def public_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    """일반 API·화면에 내보낼 계산 결과를 만든다.

    코어의 ``internal_reasons`` 는 운영 진단과 회귀를 위해 남긴다. 그러나 관계 ID,
    데이터 계약키, 계산 참조처럼 사용자가 해석할 필요가 없는 내부 결속값이 들어 있으므로
    제품 API가 원본 결과를 그대로 반환해서는 안 된다. 원본을 변경하지 않고 새 봉투를
    만들어 진단값만 제거한다.
    """
    public = dict(result)
    blocked = result.get("blocked")
    if isinstance(blocked, Mapping):
        safe_blocked = dict(blocked)
        safe_blocked.pop("internal_reasons", None)
        public["blocked"] = safe_blocked
    return public


def calculate(req: PathCalculationRequest, *,
              datasets: Mapping[str, Sequence[Mapping[str, Any]]],
              ledger_verifier: Optional[Callable[[Any], bool]] = None,
              relation_verifier: Optional[Callable[[str, str], bool]] = None,
              capability_resolver: Optional[Callable[[str], Any]] = None,
              ) -> Dict[str, Any]:
    """경로 하나를 계산한다. 관문 7개(§6)를 **순서대로** 지난다.

    | # | 관문 | 실패하면 |
    |---|---|---|
    | 1 | 경로의 모든 관계가 승인돼 있는가 | `BLOCKED` |
    | 2 | 승인이 **지금도** 유효한가(철회 재확인) | `BLOCKED` |
    | 3 | 구간별 참조가 실행 가능한가 | `BLOCKED` |
    | 4 | 봉인된 판이 전부 있는가 | `BLOCKED` |
    | 5 | 정체성이 온전한가 | 무결성 장애(503) |
    | 6 | 읽은 판 == 봉인된 판인가 | 무결성 장애(503) |
    | 7 | 필수 계약키의 판이 전부 있는가 | `BLOCKED` |

    ★★★ **부분 결과를 만들지 않는다.** 한 구간이라도 막히면 경로 전체가 `BLOCKED` 다.
    ⚠️ `BLOCKED` 와 무결성 장애를 가른다 — 앞은 「아직 못 한다」(정상), 뒤는 「자료가
      어긋났다」(점검 필요)다. 뭉개면 고칠 것이 없는데 고치라고 말하게 된다.
    """
    #: ★★★ [M0-0] **실효 능력**을 해석기에서 얻는다. 등록부 상수는 계약이고, 「지금 이
    #:   조건에서 승인됐는가」는 저장소·원장이 답한다.
    #: ⚠️ 해석기가 없으면 등록부 그대로다 — 그래서 승인 전에는 계속 막힌다. 「해석기를
    #:   안 넘겼으니 통과」로 접지 않는다(그 문이 승인 확인을 통째로 건너뛰게 한다).
    resolve = capability_resolver or cc.get
    caps = {ref: resolve(ref) for ref in SEGMENTS}
    seg_fps = {ref: caps[ref].fingerprint() for ref in SEGMENTS}

    #: 관문 5 — 정체성. ⚠️ 이것을 `BLOCKED` 로 두면 「승인이 없다」와 「요청이 깨졌다」가
    #:   같은 답이 되고, 운영자는 승인을 찾으러 간다.
    missing = req.identity_missing()
    if missing:
        raise PathCalculationError(
            f"경로 계산 요청의 정체성이 온전하지 않습니다: {missing} — 이 값들이 없으면 "
            f"다른 조직·다른 기준선의 계산과 구분할 수 없습니다.")

    #: ★★★ [P0-CALC-PROOF] 경로 판은 **코드가 정한다.** 호출자가 주장한 값을 그대로
    #:   쓰면 `"0.0.0-fake"` 로도 계산이 지나가고(실측), 그 지문은 재현 검증을 통과한다.
    #: ⚠️ 조용히 덮어쓰지 않고 **거부**한다 — 덮어쓰면 호출자는 자기가 다른 판을 요청한
    #:   줄 모른 채 다른 규칙의 답을 받는다.
    if str(req.path_model_version) != PATH_MODEL_VERSION:
        raise PathCalculationError(
            f"경로 판이 코드와 다릅니다(요청 {req.path_model_version!r} ≠ 코드 "
            f"{PATH_MODEL_VERSION!r}) — 판은 호출자가 주장하는 값이 아닙니다.")

    #: 관문 1·2 — 관계 승인과 **지금도 유효한지**.
    if not req.relation_approvals:
        return _blocked(req, seg_fps,
                        reason_code=RELATION_APPROVAL_REQUIRED,
                        internal=["relation_approvals 가 비어 있습니다."])
    #: ★★★ [P0-CALC-PROOF] **경로의 모든 관계가 승인돼 있는가**(§6 관문 1).
    #: ⚠️ 개수만 세지 않는다 — 다른 관계의 승인을 넣어도 개수는 맞을 수 있다.
    if not req.required_relation_ids:
        return _blocked(req, seg_fps,
                        reason_code=RELATION_APPROVAL_REQUIRED,
                        internal=["경로가 요구하는 관계 집합이 비어 있습니다 — 무엇을 "
                                  "승인해야 하는지 모르는 채로 계산하지 않습니다."])
    want = set(req.required_relation_ids)
    have = set(req.relation_approvals)
    if want != have:
        return _blocked(req, seg_fps,
                        reason_code=RELATION_APPROVAL_REQUIRED,
                        internal=[f"승인 집합이 경로와 일치하지 않습니다: "
                                  f"없는 승인={sorted(want - have)}, "
                                  f"경로 밖 승인={sorted(have - want)}"])
    if relation_verifier is None:
        #: ⚠️ 검증기 없이 통과시키면 **철회된 승인으로 계산이 지나간다.** 등록부의
        #:   `assert_executable` 과 같은 규칙이다 — 「안 넘겼으니 통과」는 문이다.
        return _blocked(req, seg_fps,
                        reason_code=RELATION_APPROVAL_REQUIRED,
                        internal=["relation_verifier 가 없어 승인 유효성을 확인할 수 "
                                  "없습니다."])
    stale = []
    for rel_id in sorted(req.relation_approvals):
        try:
            ok = bool(relation_verifier(rel_id, req.relation_approvals[rel_id]))
        except Exception as e:
            #: ⚠️ 원장을 못 읽은 것은 「승인 없음」도 「있음」도 아니다 — 장애다.
            raise PathCalculationError(f"관계 승인을 확인하지 못했습니다({rel_id}): {e}")
        if not ok:
            stale.append(rel_id)
    if stale:
        return _blocked(req, seg_fps,
                        reason_code=RELATION_APPROVAL_REQUIRED,
                        internal=[f"승인이 유효하지 않습니다: {stale}"])

    #: 관문 3 — 구간별 참조가 실행 가능한가. **지금은 여기서 전부 멈춘다**(승인 전).
    blocked_segments = []
    for ref in SEGMENTS:
        try:
            cc.assert_executable(ref, ledger_verifier, capability=caps[ref])
        except cc.CapabilityError as e:
            blocked_segments.append(str(e))
    if blocked_segments:
        return _blocked(req, seg_fps,
                        reason_code=CALCULATION_APPROVAL_REQUIRED,
                        internal=blocked_segments)

    #: 관문 4·7 — 봉인된 판과 실제 판.
    missing_seals = [k for k in REQUIRED_DATASETS
                     if not str(req.sealed_snapshots.get(k, "") or "").strip()]
    if missing_seals:
        return _blocked(req, seg_fps,
                        reason_code=DATA_NOT_READY,
                        internal=[f"봉인된 판이 없습니다: {missing_seals}"])
    missing_rows = [k for k in REQUIRED_DATASETS if k not in datasets]
    if missing_rows:
        return _blocked(req, seg_fps,
                        reason_code=DATA_NOT_READY,
                        internal=[f"읽을 자료가 없습니다: {missing_rows}"])

    #: 관문 6 — 읽은 판 == 봉인된 판. ⚠️ 다르면 지문 문제가 아니라 **무결성 장애**다.
    #:
    #: ★★★ [P0-CALC-PROOF] **모든 행**을 본다. 앞 판은 첫 행만 봤고, 그래서 **두 번째
    #:   행부터 다른 판을 섞어 넣어도 COMPLETE** 가 나왔다(실측). 한 판을 봉인했다는
    #:   말은 그 판의 행만 읽었다는 뜻이어야 한다.
    #: ⚠️ 빈 데이터셋은 **BLOCKED** 다(자료가 아직 없다) — 무결성 장애가 아니다.
    #:   장애로 올리면 「데이터를 채워야 한다」가 「시스템이 고장났다」로 보인다.
    empty = [k for k in REQUIRED_DATASETS if not datasets.get(k)]
    if empty:
        return _blocked(req, seg_fps,
                        reason_code=DATA_NOT_READY,
                        internal=[f"판은 봉인됐으나 행이 0건입니다: {empty}"])
    used: Dict[str, str] = {}
    mixed: Dict[str, List[str]] = {}
    for k in REQUIRED_DATASETS:
        seen = {str(r.get("__snapshot_id__", "")) for r in datasets[k]}
        if len(seen) > 1:
            mixed[k] = sorted(seen)
        used[k] = sorted(seen)[0]
    if mixed:
        raise PathCalculationError(
            f"한 계약키에 여러 판의 행이 섞였습니다: {mixed} — 봉인은 판 하나를 가리키고, "
            f"섞인 자료로 만든 숫자는 어느 판의 것인지 말할 수 없습니다.")
    mismatch = {k: (req.sealed_snapshots[k], used[k])
                for k in REQUIRED_DATASETS if used[k] != str(req.sealed_snapshots[k])}
    if mismatch:
        raise PathCalculationError(
            f"봉인한 판이 아닌 것을 읽었습니다: {mismatch} — 지문 문제가 아니라 "
            f"무결성 장애입니다(§3.6).")

    #: ── 정본 → 계산 DTO 투영 ────────────────────────────────────────────
    #:
    #: ★★★ [P0-CALC-INPUT] 계산 모델은 **계산의 말**로 입력을 받고 정본은 **업무의 말**로
    #:   적혀 있다. 그 사이를 잇는 것이 투영 계층이고, 결합은 **승인된 관계 근거**로만 한다.
    #: ⚠️ 결합이 끊기면 그 행을 빼지 않고 **실패**한다 — 빼면 운송 중 수량이 조용히 줄고
    #:   그것은 「지연이 없다」로 읽힌다.
    try:
        dto = cp.project(
            datasets,
            sales_allocation=req.assumptions.get("sales_allocation"),
            recognition_span_days=req.assumptions.get("recognition_span_days"))
    except cp.ProjectionError as e:
        return _blocked(req, seg_fps,
                        reason_code=DATA_CONTRACT_INCOMPLETE,
                        internal=[f"{type(e).__name__}: {e}"])

    #: ── 구간 실행. 앞 구간 결과가 뒤 구간 입력이다 ──────────────────────
    try:
        arrival = cm.arrival_delay(
            shipments=dto["shipments"], milestones=dto["milestones"],
            inventory=dto["inventory"], as_of=req.as_of, assumptions=req.assumptions)
        shortage = cm.material_shortage(
            inventory=dto["inventory"], production_plan=dto["production_plan"],
            bom=dto["bom"], as_of=req.as_of, assumptions=req.assumptions,
            arrival=arrival)
        timing = cm.revenue_timing(
            sales_lines=dto["sales_lines"],
            baseline_recognition=dict(req.assumptions.get("baseline_recognition") or {}),
            producible=shortage, production_plan=dto["production_plan"],
            as_of=req.as_of)
    except (cm.CalcInputError, cm.CalcSemanticError) as e:
        #: ★★★ 자료가 계약과 다르면 **BLOCKED** 다 — 0 으로 접지 않는다.
        #: ⚠️ 이것을 무결성 장애로 올리면 「자료를 채워야 한다」가 「시스템이 고장났다」로
        #:   보이고, 운영자는 데이터가 아니라 서버를 본다.
        return _blocked(req, seg_fps,
                        reason_code=DATA_CONTRACT_INCOMPLETE,
                        internal=[f"{type(e).__name__}: {e}"])

    segment_outputs = {
        "CALC.LOGISTICS.ARRIVAL_DELAY.v1": arrival["metrics"],
        "CALC.INVENTORY.MATERIAL_SHORTAGE.v1": shortage["metrics"],
        "CALC.PRODUCTION.REVENUE_TIMING.v1": timing["metrics"],
    }
    #: ★ 경로 지표 = 구간 지표의 합집합. ⚠️ 이름이 겹치면 뒤가 앞을 덮으므로 **금지**한다.
    metrics: Dict[str, Any] = {}
    for ref in SEGMENTS:
        for name, value in segment_outputs[ref].items():
            if name in metrics:
                raise PathCalculationError(
                    f"구간 지표 이름이 겹칩니다: {name} — 뒤 구간이 앞 구간을 덮으면 "
                    f"어느 산식의 값인지 알 수 없습니다.")
            metrics[name] = value

    #: ★★ 기준선 없는 판매행은 **드러낸다.** 조용히 빼면 「이동 없음」과 구분되지 않는다.
    if timing.get("missing_baseline"):
        return _blocked(req, seg_fps,
                        reason_code=BASELINE_NOT_READY,
                        internal=[f"기준선 없는 판매행: {timing['missing_baseline']}"])

    request_fp = request_fingerprint(req, seg_fps)
    return {
        "status": COMPLETE,
        #: ★★★ [B2] **경로 정체성을 결과에 싣는다.** 결과 지문은 계산을 재현하지만
        #:   경로를 재현하지 않는다 — 같은 숫자를 다른 길로도 만들 수 있다.
        #: ⚠️ 이것이 없으면 G5 가 「이 숫자가 이 경로에서 나왔는가」를 대조할 수 없고,
        #:   그때는 호출자가 경로 id 를 복사해 붙일 수 있다(B1.2-1a 에서 지운 구멍이다).
        "query_id": req.query_id,
        "path_fingerprint": req.path_fingerprint,
        # 전사 시나리오와 G5가 같은 비교 기준을 증명할 수 있도록 결과에도 보존한다.
        # request_fingerprint 안에만 숨기면 저장 단계에서 원래 값을 복원할 수 없다.
        "baseline_id": req.baseline_id,
        "baseline_fingerprint": req.baseline_fingerprint,
        #: ★ **무엇에 기대어 계산했는가.** 경로의 관계 전부를 그대로 싣는다 — 승인이
        #:   확인된 것만 싣는 것이 아니다(승인은 `relation_approvals` 가 답한다).
        "required_relation_ids": sorted(req.required_relation_ids),
        "capability_fingerprints": dict(seg_fps),
        "request_fingerprint": request_fp,
        "result_fingerprint": result_fingerprint(
            request_fp=request_fp, metrics=metrics,
            segment_outputs=segment_outputs, used_snapshots=used),
        "metrics": metrics,
        "segment_outputs": segment_outputs,
        "segment_model_versions": {ref: cm.MODEL_VERSIONS[ref] for ref in SEGMENTS},
        "path_model_version": req.path_model_version,
        "used_snapshots": used,
        "assumptions_used": {
            **arrival.get("assumptions_used", {}),
            **shortage.get("assumptions_used", {}),
            # 매출 인식 이동을 재무 기간에 옮기려면 어떤 기준일과 비교했는지가
            # 결과에 남아야 한다. request_fingerprint만으로는 날짜를 복원할 수 없다.
            "baseline_recognition": dict(
                req.assumptions.get("baseline_recognition") or {}),
        },
        "reconciliation": shortage.get("reconciliation", []),
        "blocked": None,
    }
