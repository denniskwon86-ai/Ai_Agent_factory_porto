"""[BDR-5] 결정론적 준비도 판정 — 「지금 무엇까지 믿고 만들 수 있는가」.

## 이 파일이 지키는 것 셋

★★★ ① **부족한 값을 0으로 채우지 않는다.** 준비되지 않은 데이터는 「0건」이 아니라
  「아직 아니다」이고, 그 둘은 화면에서 절대 같아 보이면 안 된다. 0으로 채우면
  보고서가 «완성» 되고, 그 순간 아무도 그것이 미완이라고 생각하지 않는다.

★★★ ② **같은 입력이면 같은 판정이다.** 판정은 시각(`now`)·결속·판·정책만 본다.
  전역 상태·DB 조회 순서·dict 순회 순서에 결과가 흔들리면, 두 사람이 같은 화면을
  보면서 다른 결론을 내리고 그 차이를 아무도 재현하지 못한다.
  ⚠️ 그래서 이 모듈은 **저장소를 모른다** — 호출부가 읽어서 넘겨 준다.

★★★ ③ **없음·못 읽음·승인 전·만료는 서로 다른 상태다.** 넷을 하나로 접으면
  사용자가 할 일이 정해지지 않는다. 「원천을 고르세요」와 「승인을 받으세요」와
  「다시 올리세요」는 **다른 사람이 하는 다른 일**이다.

## 상태 어휘 — 두 정본이 갈린 자리

솔로 실행 인수인계(2026-08-16) §9.1 과 상세설계(2026-08-15) §10.1 의 이름이 다르다.
**더 최근이고 MVP 범위인 인수인계 쪽을 정본으로 쓴다.** 대응은 다음과 같다.

    설계서 §10.1          여기(정본)
    UNBOUND            →  NOT_CONFIGURED
    SNAPSHOT_AVAILABLE →  DATA_AVAILABLE
    BLOCKED            →  UNAVAILABLE      (권한·계약·범위 결함 = 「못 읽음」)
    NOT_APPLICABLE     →  (MVP 밖 — 「불필요」 승인 흐름이 아직 없다)

⚠️ `NOT_APPLICABLE` 을 조용히 `READY` 로 접지 않는다. 승인 흐름이 생기기 전까지
  「해당 없음」을 표현할 방법이 없다는 사실을 **그대로 둔다** — 접으면 필요 없다고
  판단한 데이터가 준비된 데이터로 세어진다.
"""
import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

from core.data_preparation import models as m

# ── 데이터셋 준비 상태 ────────────────────────────────────────────────────
#
# ★ 목록은 **닫혀 있다.** 여기 없는 문자열이 나오면 그것은 결함이지 새 상태가 아니다.
NOT_CONFIGURED = "NOT_CONFIGURED"          # 원천을 아직 고르지 않았다
SOURCE_CONFIGURED = "SOURCE_CONFIGURED"    # 원천은 있으나 올라온 판이 없다
DATA_AVAILABLE = "DATA_AVAILABLE"          # 판은 있으나 품질·대사·승인 미완
QUALITY_FAILED = "QUALITY_FAILED"          # 표준화에서 격리됐다
RECONCILIATION_FAILED = "RECONCILIATION_FAILED"   # 원천 합계와 어긋났다
APPROVAL_PENDING = "APPROVAL_PENDING"      # 대사까지 끝났고 인증만 남았다
READY = "READY"
STALE = "STALE"                            # 인증판은 있으나 기준시점이 오래됐다
UNAVAILABLE = "UNAVAILABLE"                # 못 읽음 — 범위·계약·서버 상태 결함

#: ★★★ [4.1c-C P1-1] 구버전 소유권 결속이 **격리된** 상태. 「소유자 없음」과 다르다 —
#: 앞은 아직 정하지 않은 것이고, 이것은 **한 번 정했다고 적혀 있었으나 근거가 없는** 것이다.
#: ⚠️ 이 둘을 뭉개면 운영자는 무엇을 다시 승인해야 하는지 알 수 없고, 화면에는 그저
#:   「데이터가 안 보인다」로 나타난다.
LEGACY_OWNERSHIP_QUARANTINED = "LEGACY_OWNERSHIP_QUARANTINED"

DATASET_STATES: Tuple[str, ...] = (
    NOT_CONFIGURED, SOURCE_CONFIGURED, DATA_AVAILABLE, QUALITY_FAILED,
    RECONCILIATION_FAILED, APPROVAL_PENDING, READY, STALE, UNAVAILABLE,
    LEGACY_OWNERSHIP_QUARANTINED)

#: ★★★ **공식 결과에 쓸 수 있는 상태**는 둘뿐이다. 나머지는 전부 막는다.
#: ⚠️ `STALE` 을 여기 넣지 않는다 — 오래된 판으로 만든 공식 숫자는 「틀렸다」가 아니라
#:   「언제 것인지 모른다」가 되고, 그쪽이 더 고치기 어렵다.
OFFICIAL_STATES: Tuple[str, ...] = (READY,)

#: ★ 경고를 달고 쓸 수 있는 상태. 「쓸 수 있다」와 「믿을 수 있다」는 다르다.
WARNING_STATES: Tuple[str, ...] = (STALE,)

# ── 산출물 준비 상태 ──────────────────────────────────────────────────────
AVAILABLE = "AVAILABLE"
AVAILABLE_WITH_WARNING = "AVAILABLE_WITH_WARNING"
BLOCKED_OUTPUT = "BLOCKED"
OUTPUT_STATES: Tuple[str, ...] = (AVAILABLE, AVAILABLE_WITH_WARNING, BLOCKED_OUTPUT)

# ── 인스턴스 종합 ─────────────────────────────────────────────────────────
INSTANCE_READY = "READY"
INSTANCE_PARTIAL = "PARTIAL"
INSTANCE_BLOCKED = "BLOCKED"
INSTANCE_STATES: Tuple[str, ...] = (INSTANCE_READY, INSTANCE_PARTIAL, INSTANCE_BLOCKED)

#: ★ 사용자에게 보일 «다음 행동» 과 «그 일을 하는 사람». 상태마다 **하나씩** 정해 둔다.
#: ⚠️ 여기서 문장을 지어내지 않는다 — 상태가 늘면 표가 비고, 빈 칸은 시험이 잡는다.
_NEXT_ACTION: Dict[str, Tuple[str, str]] = {
    NOT_CONFIGURED: ("이 데이터를 어디서 가져올지 원천을 고르십시오.", "데이터 담당자"),
    SOURCE_CONFIGURED: ("정한 원천에서 파일을 올리십시오.", "데이터 담당자"),
    DATA_AVAILABLE: ("올라온 판의 품질 검사와 원천 대사를 진행하십시오.", "데이터 담당자"),
    QUALITY_FAILED: ("격리 사유를 확인하고 고친 파일을 다시 올리십시오.", "데이터 담당자"),
    RECONCILIATION_FAILED: ("원천 합계와 어긋납니다 — 원본이 잘리지 않았는지 확인하십시오.",
                            "데이터 담당자"),
    APPROVAL_PENDING: ("판을 검토하고 인증하십시오.", "데이터 오너"),
    READY: ("", ""),
    STALE: ("기준시점이 오래됐습니다 — 최신 판을 올리십시오.", "데이터 담당자"),
    UNAVAILABLE: ("이 데이터를 읽을 수 없습니다 — 관리자에게 문의하십시오.", "시스템 관리자"),
    #: ★★★ [4.1c-C P1-1] **「기다리면 된다」로 읽히지 않게 쓴다.** 이 상태는 사람이
    #:   재승인해야 풀린다 — 승인 근거 없이 옮겨진 구버전 결속이 격리된 것이다.
    #: ⚠️ 「데이터가 없습니다」로 쓰면 담당자가 파일을 다시 올리고, 그래도 안 보인다.
    LEGACY_OWNERSHIP_QUARANTINED: (
        "구버전 소유권 결속이 승인 근거가 없어 격리됐습니다 — 소유 부서를 다시 승인하십시오"
        "(파일을 다시 올려도 풀리지 않습니다).", "데이터 오너"),
}


class ReadinessError(m.DataPreparationError):
    """판정 자체가 불가능한 경우 — **판정 결과가 아니다.**"""


def _fingerprint(payload: Any) -> str:
    """재현성 지문. **정렬해 직렬화한다** — dict 순회 순서가 지문을 흔들면 안 된다.

    ⚠️ [변이 검사 실측] `sort_keys=False` 로 바꿔도 지금은 시험이 잡지 못한다. 호출부가
      **이미 정렬된 키 목록**으로 payload 를 만들기 때문에 삽입 순서가 늘 정렬 순서와
      같아서다. 그래도 남겨 둔다 — 이 함수는 호출부가 정렬을 지킨다는 보장에 기대지
      않아야 하고, 언젠가 정렬되지 않은 목록으로 부르는 날 그 사실이 지문에 나타나면
      **캐시된 옛 판정이 조용히 재사용된다.**"""
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")).hexdigest()


def _age_days(as_of: str, now: str) -> Optional[float]:
    """`as_of` 부터 `now` 까지 며칠. **읽을 수 없으면 `None`** 이지 0 이 아니다.

    ⚠️ 0 으로 두면 「읽을 수 없는 시각」이 「방금 전」이 되고, 만료된 판이 신선해 보인다."""
    from datetime import datetime

    def _parse(v: str):
        try:
            return datetime.fromisoformat(str(v or "").replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    a, b = _parse(as_of), _parse(now)
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 86400.0


def latest_certified(snapshots: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """가장 최근 **인증된** 판. 없으면 `None`.

    ⚠️ 「가장 최근 판」이 아니다 — 인증되지 않은 새 판이 인증된 옛 판을 가리면,
      승인 전 데이터가 공식 화면에 오른다."""
    #: ⚠️ 종점이 둘이다(시연·원천). 하나만 보면 실물 판이 «없는 것처럼» 보인다.
    certified = [s for s in snapshots if m.is_certified(s.get("state"))]
    if not certified:
        return None
    return sorted(certified, key=lambda s: (str(s.get("certified_at") or ""),
                                            str(s.get("snapshot_id") or "")))[-1]


def _latest(snapshots: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not snapshots:
        return None
    return sorted(snapshots, key=lambda s: (str(s.get("created_at") or ""),
                                            str(s.get("snapshot_id") or "")))[-1]


def evaluate_dataset(contract_key: str, *, binding: Optional[Dict[str, Any]],
                     snapshots: List[Dict[str, Any]], now: str,
                     max_age_days: Optional[float] = None,
                     scope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """데이터셋 하나의 준비 상태. **순서가 곧 규칙이다.**

    ★★★ 검사 순서를 바꾸면 답이 달라진다. 「승인 전」보다 「대사 실패」를 먼저 보는
      이유: 대사에 실패한 판을 승인 대기로 부르면 오너가 승인 버튼을 누르게 되고,
      그러면 **틀린 판이 사람 손을 거쳐 공식이 된다.**

    ⚠️ 이 함수는 저장소를 모른다 — 넘겨받은 값만 본다(재현성)."""
    key = str(contract_key or "").strip()
    if not key:
        raise ReadinessError("dataset_contract_key 가 비었습니다 — 판정 대상이 없습니다.")

    def out(state: str, *, snapshot: Optional[Dict[str, Any]] = None,
            detail: str = "") -> Dict[str, Any]:
        action, role = _NEXT_ACTION[state]
        return {
            "dataset_contract_key": key,
            "state": state,
            "next_action": action,
            "responsible_role": role,
            "detail": detail,
            #: ★ 기준시점은 **판의 인증 시각**이지 판정 시각이 아니다. 판정 시각을 주면
            #:   화면이 매번 새로 보이고, 사용자는 데이터가 갱신됐다고 믿는다.
            "as_of": str((snapshot or {}).get("certified_at") or ""),
            "snapshot_id": str((snapshot or {}).get("snapshot_id") or ""),
            "data_kind": str((snapshot or {}).get("data_kind") or ""),
        }

    if not binding:
        return out(NOT_CONFIGURED)

    #: ⚠️ 범위가 어긋난 결속은 **못 읽음**이지 「없음」이 아니다. 없음으로 답하면
    #:   사용자가 원천을 다시 고르려 하고, 다시 골라도 같은 자리에 멈춘다.
    if scope:
        for field in ("tenant_id", "scope_node_id", "entity_mode"):
            want, got = str(scope.get(field, "")), str(binding.get(field, ""))
            if want and got and want != got:
                return out(UNAVAILABLE, detail="범위 불일치")

    if str(binding.get("state")) != m.ACTIVE:
        #: 결속은 있으나 아직 활성이 아니다 — 원천을 «고르는 중» 이다.
        return out(NOT_CONFIGURED, detail=f"결속 상태 {binding.get('state')}")

    if not snapshots:
        return out(SOURCE_CONFIGURED)

    certified = latest_certified(snapshots)
    if certified is None:
        newest = _latest(snapshots)
        state = str((newest or {}).get("state") or "")
        if state == m.QUARANTINED:
            #: 격리 사유가 대사인지 품질인지 나눠서 답한다 — 고칠 사람이 다르다.
            q = (newest or {}).get("quarantine") or {}
            #: ★ **코드로 분기한다.** 사람이 읽는 `reason` 문장으로 나누면 문구를 다듬는
            #:   순간 판정이 조용히 바뀌고, 시험은 그대로 통과한다.
            kind = str(q.get("kind") or "")
            if kind == m.QUARANTINE_RECONCILIATION:
                return out(RECONCILIATION_FAILED, snapshot=newest,
                           detail=str(q.get("reason") or ""))
            if kind == m.QUARANTINE_QUALITY:
                return out(QUALITY_FAILED, snapshot=newest, detail=str(q.get("reason") or ""))
            #: ⚠️ 종류를 모르는 격리는 **못 읽음**이다. 「품질 실패」로 접으면 사용자가
            #:   파일을 고치러 가는데, 실제 원인은 다른 곳일 수 있다.
            return out(UNAVAILABLE, snapshot=newest, detail="격리 종류를 알 수 없습니다")
        if state == m.RECONCILED:
            return out(APPROVAL_PENDING, snapshot=newest)
        if state in (m.RAW, m.PROFILED, m.STANDARDIZED):
            return out(DATA_AVAILABLE, snapshot=newest)
        #: ⚠️ 모르는 상태는 **못 읽음**이다 — 「준비됨」으로 떨어지면 안 된다.
        return out(UNAVAILABLE, snapshot=newest, detail=f"모르는 판 상태 {state}")

    if max_age_days is not None:
        age = _age_days(str(certified.get("certified_at") or ""), now)
        if age is None:
            return out(UNAVAILABLE, snapshot=certified, detail="기준시점을 읽을 수 없습니다")
        if age > float(max_age_days):
            return out(STALE, snapshot=certified, detail=f"{age:.1f}일 경과")

    return out(READY, snapshot=certified)


def evaluate_outputs(datasets: List[Dict[str, Any]],
                     outputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """산출물별 가용성. **필요한 데이터가 하나라도 막히면 산출물이 막힌다.**

    ★★★ 「일부만 있으니 일부만 계산」을 하지 않는다. 부분 계산은 화면에서 완성된
      숫자와 구별되지 않고, 그 숫자가 회의에 올라간다."""
    by_key = {d["dataset_contract_key"]: d for d in datasets}
    result: List[Dict[str, Any]] = []
    for spec in outputs:
        name = str(spec.get("output") or spec.get("name") or "").strip()
        #: ★★★ 사람이 읽을 이름. ⚠️ 세 분기 **전부**에 실어야 한다 — 하나라도 빠지면
        #:   그 상태일 때만 화면에 「APP-03」이 뜬다(실측: 셋 다 빠져 있었고, 프로파일에
        #:   「재고·생산 영향 분석」이 멀쩡히 들어 있는데 목록은 코드만 보여 줬다).
        label = str(spec.get("label") or spec.get("name_ko") or "").strip()
        needs = [str(k).strip() for k in (spec.get("requires") or []) if str(k).strip()]
        blocking, warning, missing = [], [], []
        for key in needs:
            row = by_key.get(key)
            if row is None:
                #: ⚠️ 키트가 요구하는데 판정 대상에 없다 — **막는다.** 「없으니 넘어감」이
                #:   되면 요구사항 오타 하나가 산출물을 통과시킨다.
                missing.append(key)
                continue
            if row["state"] in OFFICIAL_STATES:
                continue
            (warning if row["state"] in WARNING_STATES else blocking).append(row)

        if blocking or missing:
            first = blocking[0] if blocking else None
            result.append({
                "output": name, "label": label,
                "state": BLOCKED_OUTPUT,
                "reason_code": (f"REQUIRED_DATA_{first['state']}" if first
                                else "REQUIRED_DATA_UNKNOWN"),
                "user_message": (f"«{first['dataset_contract_key']}» 데이터가 아직 "
                                 f"준비되지 않았습니다." if first
                                 else "키트가 요구하는 데이터를 찾을 수 없습니다."),
                "next_action": first["next_action"] if first else "관리자에게 문의하십시오.",
                "responsible_role": first["responsible_role"] if first else "시스템 관리자",
                "blocking_datasets": sorted([r["dataset_contract_key"] for r in blocking]
                                            + missing),
            })
        elif warning:
            result.append({
                "output": name, "label": label, "state": AVAILABLE_WITH_WARNING,
                "reason_code": "REQUIRED_DATA_STALE",
                "user_message": (f"«{warning[0]['dataset_contract_key']}» 데이터의 "
                                 f"기준시점이 오래됐습니다 — 참고용으로만 사용하십시오."),
                "next_action": warning[0]["next_action"],
                "responsible_role": warning[0]["responsible_role"],
                "blocking_datasets": [],
            })
        else:
            result.append({"output": name, "label": label,
                           "state": AVAILABLE, "reason_code": "",
                           "user_message": "", "next_action": "", "responsible_role": "",
                           "blocking_datasets": []})
    return sorted(result, key=lambda r: r["output"])


def evaluate_instance(*, contract_keys: List[str],
                      bindings: Dict[str, Optional[Dict[str, Any]]],
                      snapshots: Dict[str, List[Dict[str, Any]]],
                      outputs: Optional[List[Dict[str, Any]]] = None,
                      now: str, max_age_days: Optional[float] = None,
                      scope: Optional[Dict[str, Any]] = None,
                      context_omitted: int = 0,
                      ownership_quarantined: Optional[Dict[str, int]] = None
                      ) -> Dict[str, Any]:
    """인스턴스 하나의 준비도 전부.

    ★★★ **권한 밖 자원의 존재도 개수도 응답에 넣지 않는다.** 호출부가 이미 보이는
      것만 넘겨야 한다. 여기서 표현할 수 있는 유일한 «빠진 수» 는 `context_omitted` —
      **권한은 있으나 지금 고른 문맥에서 빠진 수**다.
    ⚠️ 「권한 밖 3건」을 세어 주면 그 3이 곧 「그 조직에 3건이 있다」가 된다."""
    keys = sorted({str(k).strip() for k in contract_keys if str(k).strip()})
    rows = [evaluate_dataset(k, binding=bindings.get(k), snapshots=snapshots.get(k) or [],
                             now=now, max_age_days=max_age_days, scope=scope)
            for k in keys]

    #: ★★★ [4.1c-C P1-1] **격리된 계약키는 준비됐다고 말할 수 없다.**
    #:
    #: ⚠️ 격리는 「데이터가 없다」가 아니라 「소유 근거가 없어 못 쓴다」다. 그 구분을 여기서
    #:   하지 않으면 화면은 준비 완료를 띄우고, 실제로는 그 데이터가 아무에게도 안 보인다 —
    #:   그리고 이유가 화면 어디에도 없다(앞 판은 기동 로그의 `print` 뿐이었다).
    qmap = {str(k): int(v) for k, v in (ownership_quarantined or {}).items() if int(v) > 0}
    if qmap:
        rows = [({**r, "state": LEGACY_OWNERSHIP_QUARANTINED,
                  "reason": "구버전 소유권 결속이 격리됐습니다 — 소유 부서를 다시 승인해야 "
                            "이 데이터를 쓸 수 있습니다.",
                  "ownership_quarantined": qmap[str(r.get("dataset_contract_key"))]}
                 if str(r.get("dataset_contract_key")) in qmap else r)
                for r in rows]

    counts = {s: 0 for s in DATASET_STATES}
    for r in rows:
        counts[r["state"]] += 1

    out_rows = evaluate_outputs(rows, outputs or [])

    if counts[LEGACY_OWNERSHIP_QUARANTINED]:
        #: ⚠️ 하나라도 격리돼 있으면 인스턴스는 준비된 것이 아니다. 「부분 가능」으로도
        #:   두지 않는다 — 그 표현은 운영자에게 «기다리면 된다» 로 읽힌다. 이것은 사람이
        #:   재승인해야 풀리는 상태다.
        status = INSTANCE_BLOCKED
    elif rows and counts[READY] == len(rows):
        status = INSTANCE_READY
    elif counts[READY] or counts[STALE]:
        status = INSTANCE_PARTIAL
    else:
        status = INSTANCE_BLOCKED

    #: ★ 기준시점은 **가장 오래된 준비된 판**이다. 가장 최신을 주면 화면이 실제보다
    #:   신선해 보이고, 그 화면으로 「최근 데이터로 봤다」고 말하게 된다.
    as_of = sorted([r["as_of"] for r in rows if r["as_of"]]) or [""]

    return {
        "status": status,
        "as_of": as_of[0],
        "coverage": {"required": len(rows), "ready": counts[READY], "stale": counts[STALE],
                     "blocked": len(rows) - counts[READY] - counts[STALE]},
        "datasets": rows,
        "available_outputs": [r["output"] for r in out_rows
                              if r["state"] in (AVAILABLE, AVAILABLE_WITH_WARNING)],
        "blocked_outputs": [r for r in out_rows if r["state"] == BLOCKED_OUTPUT],
        "outputs": out_rows,
        "context_omitted": max(0, int(context_omitted or 0)),
        #: ★★★ [4.1c-C P1-1] 격리 건수를 **숫자로** 싣는다. 화면이 「왜 안 보이나」에
        #:   답할 수 있어야 하고, 그 답은 로그가 아니라 응답에 있어야 한다.
        "ownership_quarantined": qmap,
        #: 재현성 — 같은 지문이면 같은 판정이어야 한다(§7.4).
        "binding_set_fingerprint": _fingerprint(
            {k: {"id": str((bindings.get(k) or {}).get("binding_id") or ""),
                 "state": str((bindings.get(k) or {}).get("state") or "")} for k in keys}),
        "snapshot_set_fingerprint": _fingerprint(
            {k: sorted([f"{s.get('snapshot_id')}:{s.get('state')}"
                        for s in (snapshots.get(k) or [])]) for k in keys}),
    }
