"""[BDR-7 / Wave G] Baseline Build — **「그때 그 숫자」를 다시 만들 수 있게 한다.**

## 왜 «최신» 을 가리키면 안 되는가

보고서가 「구매주문 데이터 기준」이라고만 적혀 있으면, 한 달 뒤 같은 보고서를 다시
돌렸을 때 **다른 숫자**가 나온다. 그리고 어느 쪽이 맞는지 아무도 답할 수 없다.

★★★ 그래서 Baseline 은 **Snapshot ID 집합을 고정**한다. 「최신 판」이 아니라 「이
  판들」이다. 같은 집합이면 같은 지문이고, 같은 지문이면 같은 입력이다.

⚠️⚠️ `latest` 같은 가변 참조를 공식 결과에 쓰지 않는다(설계 §12.2). 그것 하나가
  「재현할 수 없는 경영 보고」를 만든다.

## 이 파일이 지키는 것 넷

★★★ ① **인증된 판만 들어간다.** 승인 전·격리된 판이 기준선에 들어가면, 그 위에서
  만든 숫자는 아무도 보증하지 않은 값이다.
★★★ ② **같은 집합은 같은 지문.** 순서·중복이 지문을 흔들면 「같은 기준선인가」에
  답할 수 없다.
★★★ ③ **범위가 섞이지 않는다.** 한 기준선 안에 다른 조직·다른 실행 문맥의 판이
  섞이면 그 합계는 아무 회사의 숫자도 아니다.
★★★ ④ **시연용임을 숨기지 않는다.** `DEMO/SYNTHETIC` 판으로 만든 기준선은 그
  사실을 이름표로 달고 다닌다 — 화면에서 빠지는 순간 실적으로 읽힌다.
"""
import hashlib
import json
from typing import Any, Dict, List, NamedTuple, Optional

from core.data_preparation import models as dpm


class BaselineError(Exception):
    """기준선을 만들 수 없다. **아무것도 만들지 않은 상태**로 던진다."""


class Baseline(NamedTuple):
    build_id: str
    fingerprint: str
    snapshot_ids: List[str]
    as_of: str
    data_kind: str
    label: str
    scope: Dict[str, str]

    def public(self) -> Dict[str, Any]:
        return {"build_id": self.build_id, "fingerprint": self.fingerprint,
                "snapshot_ids": list(self.snapshot_ids), "as_of": self.as_of,
                "data_kind": self.data_kind, "label": self.label,
                "scope": dict(self.scope),
                "display_label": display_label(self.data_kind)}


def display_label(data_kind: Any) -> str:
    """화면에 붙는 이름표. **성격을 먼저 말한다.**

    ⚠️ 「시연용」이 빠지면 그 숫자는 실적으로 읽힌다. 화면마다 각자 붙이게 두면
      한 화면에서 빠지고, 그 화면이 회의에 올라간다."""
    kind = str(data_kind or "")
    if kind == dpm.DATA_KIND_DEMO:
        return "시연용 합성 데이터(DEMO/SYNTHETIC) 기준선 — 실적이 아닙니다"
    if kind == dpm.DATA_KIND_REAL:
        return "실제 데이터 기준선"
    #: ⚠️ 모르는 성격을 «실제» 로 떨어뜨리지 않는다.
    return "성격을 알 수 없는 기준선 — 공식 보고에 쓰지 마십시오"


def fingerprint_for(snapshot_ids: Any) -> str:
    """Snapshot 집합의 지문. **정렬·중복 제거 후** 계산한다.

    ★★★ 같은 집합이면 같은 값이어야 한다 — 순서가 지문을 흔들면 「같은 기준선인가」에
      답할 수 없고, 그러면 재현성 주장이 통째로 무너진다."""
    ids = sorted({str(x).strip() for x in (snapshot_ids or []) if str(x).strip()})
    body = json.dumps(ids, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _assert_usable(snap: Dict[str, Any], scope: Dict[str, str]) -> None:
    """이 판이 기준선에 들어갈 수 있는가. **하나라도 어긋나면 던진다.**"""
    sid = str(snap.get("snapshot_id") or "(id 없음)")
    state = str(snap.get("state") or "")
    if state != dpm.DEMO_CERTIFIED:
        #: ⚠️ 승인 전·격리된 판이 기준선에 들어가면 그 위의 숫자는 아무도 보증하지 않는다.
        raise BaselineError(
            f"{sid}: 인증되지 않은 판은 기준선에 넣지 않습니다(현재 {state or '(모름)'}).")
    if not str(snap.get("certified_at") or ""):
        raise BaselineError(f"{sid}: 기준시점이 없습니다 — 「언제 것인가」에 답할 수 없습니다.")
    for field in ("tenant_id", "scope_node_id", "entity_mode"):
        want, got = str(scope.get(field, "")), str(snap.get(field, ""))
        if want and got and want != got:
            #: ⚠️ 한 기준선에 다른 조직의 판이 섞이면 그 합계는 **아무 회사의 숫자도 아니다.**
            raise BaselineError(
                f"{sid}: 범위가 다른 판은 한 기준선에 섞지 않습니다({field}).")


def build(snapshots: List[Dict[str, Any]], *, label: str = "",
          scope: Optional[Dict[str, str]] = None,
          build_id: str = "") -> Baseline:
    """인증된 판들을 **하나의 고정된 집합**으로 묶는다.

    ★ `build_id` 를 안 주면 지문에서 유도한다 — 같은 집합이면 같은 id 다.
    ⚠️ 판이 하나도 없으면 만들지 않는다. 빈 기준선은 「0으로 계산된 보고서」를 낳고,
      그 보고서는 오류를 내지 않는다."""
    rows = [s for s in (snapshots or []) if isinstance(s, dict)]
    if not rows:
        raise BaselineError(
            "판이 하나도 없습니다 — 빈 기준선 위에서 만든 보고서는 합계가 0이고, "
            "아무도 그것을 고장으로 보지 않습니다.")

    sc = dict(scope or {})
    for snap in rows:
        _assert_usable(snap, sc)

    kinds = {str(s.get("data_kind") or "") for s in rows}
    if len(kinds) > 1:
        #: ⚠️ 시연 데이터와 실제 데이터를 한 기준선에 섞으면, 그 결과의 성격을 말할 수 없다.
        raise BaselineError(
            f"성격이 다른 판을 한 기준선에 섞지 않습니다: {sorted(kinds)}")

    ids = sorted({str(s.get("snapshot_id") or "") for s in rows})
    fp = fingerprint_for(ids)
    #: ★ 기준시점은 **가장 오래된 판**이다 — 최신을 쓰면 기준선이 실제보다 신선해 보인다.
    as_of = sorted(str(s.get("certified_at") or "") for s in rows)[0]
    return Baseline(build_id=(build_id or f"bl_{fp[:14]}"), fingerprint=fp,
                    snapshot_ids=ids, as_of=as_of, data_kind=kinds.pop(),
                    label=(label or "").strip(), scope=sc)


def same_inputs(a: Any, b: Any) -> bool:
    """두 기준선이 **같은 입력**인가. 지문 하나로 답한다.

    ⚠️ 이름·설명이 달라도 입력이 같으면 같다 — 그리고 그 반대도 참이다."""
    return bool(a) and bool(b) and str(getattr(a, "fingerprint", "")) == \
        str(getattr(b, "fingerprint", ""))
