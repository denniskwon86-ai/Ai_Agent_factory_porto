"""★★★ Resolver 조회 **문맥**과 **결과 상태**. (2026-08-20 §7-0 시뮬레이션 산물)

## 왜 이 파일이 생겼나

종전 계약은 이것뿐이었다:

    object_scope_resolver(ref: ObjectRef) -> ResourceScope | None

⚠️⚠️ 그래서 Resolver 는 **자기가 왜 불렸는지 몰랐다.** 사용자가 검색창에 아무 id 나
  넣어서 불린 것인지, **이미 승인된 관계의 끝점**을 그리는 중에 불린 것인지 구별할
  방법이 없었다. 같은 `ObjectRef` 가 오기 때문이다.

★ 그런데 그 둘은 **정반대의 답**이 필요하다:

    임의 조회인데 없다        → 없는 게 맞다.  빈 결과 / 404
    승인된 관계의 끝점인데 없다 → **무결성 장애.** 503

⚠️ 종전처럼 둘 다 `None` 으로 접으면, 승인된 관계가 가리키는 자료가 사라진 **사고**가
  화면에서는 「영향 경로 없음」이라는 **평온한 사실**로 보인다. 사람은 그것을 읽고
  「영향이 없구나」 하고 넘어간다.

## 두 번째 이유 — `as_of` 를 전달할 자리가 없었다

판을 고르려면 시점이 필요한데 서명에 시점이 없었다. 그래서 Resolver 는 「그냥 최신」
말고는 고를 방법이 없었고, **과거 시점 질의가 오늘의 답을 내게** 된다.

## 셋째 — 「모른다」의 종류를 하나로 뭉개고 있었다

    없다 · 못 읽었다 · 후보가 둘이다 · 아직 아무 판에도 안 묶였다

넷은 서로 다른 사실이고 **사람이 할 일도 다르다.** 하나로 뭉치면 아무도 무엇을 해야
할지 모른다.

LLM 0콜. 이 파일은 자료 구조만 담는다 — 판정 규칙은 런타임(`ontology_runtime`)에 있다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from core import app_policy

# ── 조회 목적 ────────────────────────────────────────────────────────────
#: 사용자가 고른 시작점. **없으면 없는 것**이다.
ROOT_LOOKUP = "ROOT_LOOKUP"
#: 이미 승인된 관계를 따라가는 중. **없으면 무결성 장애**다.
RELATION_ENDPOINT = "RELATION_ENDPOINT"
#: 새 관계를 제안하는 중. 끝점이 실재해야 제안을 받는다.
RELATION_PROPOSAL = "RELATION_PROPOSAL"
#: 근거를 되짚는 중. 봉인된 판과 일치해야 한다.
EVIDENCE_VALIDATION = "EVIDENCE_VALIDATION"

PURPOSES = (ROOT_LOOKUP, RELATION_ENDPOINT, RELATION_PROPOSAL, EVIDENCE_VALIDATION)

#: ★ 「없으면 없는 것」인 목적은 **하나뿐**이다. 나머지는 전부 있어야 한다.
#: ⚠️ 이 집합을 넓히는 것은 **조용한 실패를 하나 더 만드는 일**이다. 넓히려면
#:   「그 자리에서 자료가 사라져도 사람이 몰라도 되는가」에 먼저 답해야 한다.
ABSENCE_IS_NORMAL = frozenset({ROOT_LOOKUP})


# ── 결과 상태 ────────────────────────────────────────────────────────────
#: 찾았다. 범위·판·근거를 함께 돌려준다.
FOUND = "FOUND"
#: 그런 객체가 없다. **사실**이지 장애가 아니다.
NOT_FOUND = "NOT_FOUND"
#: 못 읽었다(저장소·Resolver 장애). ⚠️ **없는 것과 다르다.**
UNAVAILABLE = "UNAVAILABLE"
#: 같은 시점에 인증판 후보가 둘 이상이다. ⚠️ 아무거나 고르면 **재실행 지문이 흔들린다.**
AMBIGUOUS = "AMBIGUOUS"
#: 객체는 아는데 **어느 인증판에도 묶여 있지 않다.**
UNBOUND = "UNBOUND"

RESOLUTION_STATUSES = (FOUND, NOT_FOUND, UNAVAILABLE, AMBIGUOUS, UNBOUND)


@dataclass(frozen=True)
class ResolveContext:
    """Resolver 에게 **왜·언제·무엇을 위해** 묻는지 알려 준다.

    ⚠️ `purpose` 는 기본값을 두지 않는다. 「모르겠으면 ROOT_LOOKUP」 같은 기본값은
      곧 **「모르겠으면 없는 것으로 하라」**가 되고, 그것이 이 파일이 생긴 이유다."""

    purpose: str
    #: 판을 고르는 시점. 빈 문자열이면 「지금」 — 제안·승인처럼 시점이 없는 자리다.
    as_of: str = ""
    #: ★★★ [2026-08-21 P0] **객체 정체성**을 가르는 두 값.
    #:
    #: ⚠️⚠️ 업무 레코드 ID 는 회사마다 겹친다 — `SHP-000001` 은 어느 회사에나 있다.
    #:   이 둘이 없으면 **다른 회사의 줄이 우리 줄을 가리거나** 동점을 만든다.
    #: ★ 이것은 **권한 판정이 아니다.** 다른 tenant 의 `SHP-000001` 은 「내가 볼 수 없는
    #:   우리 배」가 아니라 **아예 다른 배**다. 그래서 PDP 보다 앞선다.
    #: ★ `entity_mode` 도 같다 — 실적의 것과 시나리오의 것은 다른 객체다.
    tenant_id: str = ""
    entity_mode: str = ""
    #: 관계를 따라가는 중이면 그 관계. 장애 메시지가 **무엇이 끊겼는지** 말할 수 있다.
    relation_id: str = ""
    #: 관계에 봉인된 근거들.
    evidence_refs: Tuple[str, ...] = ()
    #: ★ 승인 때 봉인한 판. 이것이 있으면 **그 판이어야 한다** — 다르면 무결성 장애다.
    required_snapshot_id: str = ""
    #: 어느 질의에서 비롯됐나. 계보를 잇는 데 쓴다.
    query_id: str = ""

    def __post_init__(self) -> None:
        if self.purpose not in PURPOSES:
            raise ValueError(f"purpose must be one of {PURPOSES} (got {self.purpose!r}).")

    @property
    def absence_is_normal(self) -> bool:
        """이 자리에서 「없음」이 **정상**인가."""
        return self.purpose in ABSENCE_IS_NORMAL


@dataclass(frozen=True)
class ObjectResolution:
    """Resolver 의 답. **범위·판·근거만 번역한다.**

    ⚠️⚠️ 사용자·조직 **권한은 여기서 판정하지 않는다.** 그것은 PDP(`app_policy.decide`)
      의 일이다. 두 곳에서 권한을 판정하면 규칙이 갈라지고, 갈라진 규칙은 언젠가
      한쪽만 고쳐진다."""

    status: str
    resource_scope: Optional[app_policy.ResourceScope] = None
    #: 어느 인증판에서 왔나.
    snapshot_id: str = ""
    #: 그 판의 어느 행인가.
    row_evidence: str = ""
    #: `REAL` · `DEMO` 같은 자료 성격. 계보에 성격 표시를 붙이는 데 쓴다.
    data_kind: str = ""
    #: 봉인된 업무 객체에서 파생한 사람용 표시 설명. 객체 정체성 자체는 아니다.
    display_name: str = ""
    #: 표시 설명이 어느 객체·인증판·원본 지문에서 왔는지 대조하는 지문.
    display_fingerprint: str = ""
    #: 사람이 읽을 사유. ⚠️ 장애를 «없음» 으로 접지 않으려면 **왜**가 남아야 한다.
    reason: str = ""
    #: `AMBIGUOUS` 일 때 부딪힌 후보들. 사람이 무엇을 골라야 하는지 보이게.
    candidates: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.status not in RESOLUTION_STATUSES:
            raise ValueError(
                f"status must be one of {RESOLUTION_STATUSES} (got {self.status!r}).")
        if self.status == FOUND and self.resource_scope is None:
            #: ★ `FOUND` 인데 범위가 없으면 그것은 찾은 게 아니다 — 이 모순을 **여기서**
            #:   막지 않으면 런타임이 `None` 범위로 PDP 를 부르고 조용히 거부된다.
            raise ValueError("FOUND resolutions must carry a resource scope.")
        if self.status != FOUND and self.resource_scope is not None:
            raise ValueError("only FOUND resolutions may carry a resource scope.")
        if bool(self.display_name) != bool(self.display_fingerprint):
            raise ValueError("display_name and display_fingerprint must be supplied together.")
        if self.status != FOUND and (self.display_name or self.display_fingerprint):
            raise ValueError("only FOUND resolutions may carry a display descriptor.")


def found(scope: app_policy.ResourceScope, *, snapshot_id: str = "",
          row_evidence: str = "", data_kind: str = "", display_name: str = "",
          display_fingerprint: str = "") -> ObjectResolution:
    return ObjectResolution(FOUND, resource_scope=scope, snapshot_id=snapshot_id,
                            row_evidence=row_evidence, data_kind=data_kind,
                            display_name=display_name,
                            display_fingerprint=display_fingerprint)


def not_found(reason: str = "") -> ObjectResolution:
    return ObjectResolution(NOT_FOUND, reason=reason)


def unavailable(reason: str) -> ObjectResolution:
    """⚠️ 「못 읽었다」. **절대 «없음» 으로 접지 않는다** — 그것이 P0-3 이었다."""
    return ObjectResolution(UNAVAILABLE, reason=reason)


def ambiguous(candidates: Tuple[str, ...], reason: str = "") -> ObjectResolution:
    return ObjectResolution(AMBIGUOUS, reason=reason, candidates=tuple(candidates))


def unbound(reason: str = "") -> ObjectResolution:
    return ObjectResolution(UNBOUND, reason=reason)
