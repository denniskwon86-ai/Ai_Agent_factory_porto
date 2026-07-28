"""Solution Blueprint — 마스터 명세서 §5.1 / M0 백로그 2.

Blueprint 는 단순 보고서가 아니라 **시스템 전반이 참조하는 구조화 계약**이다(§5.1). RFP·WBS·
프로젝트 생성·데이터 준비 태스크가 모두 이것을 입력으로 받는다.

★ 핵심 설계 결정: **초안을 LLM 이 아니라 플레이북에서 결정론적으로 조립한다.**
  근거 셋:
   ① 제품 바이블 §9.3 "AI 에게 진실을 맡기기" — LLM 이 판단한 데이터 매칭·숫자·권한을 승인 없이
      확정하면 안 된다. 데이터 요구사항과 준비도는 이미 플레이북이 도메인 지식으로 갖고 있다.
   ② 명세서 §0-3 — 숫자·판정은 결정론적 규칙이 담당한다.
   ③ 실용: 같은 답변이면 같은 Blueprint 가 나와야 사용자가 "왜 이렇게 나왔나"를 물었을 때
      설명할 수 있고, 테스트가 LLM 없이 돈다.
  LLM 은 나중에 **문장 다듬기·추가 위험 제안** 같은 보강 역할로 얹으며, 그때 그 항목은
  `origin="ai"` 로 표시되어 사람의 확정과 구분된다(§5.2).

⚠️ 이 모듈은 순수 로직만 담는다(저장은 `core/advisor_store.py`). 그래야 조립 규칙이 어디서
  불려도 같은 답을 주고, 테스트가 DB 없이 돈다.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core.advisor_playbook import (Playbook, active_requirement_keys,
                                   score_readiness)

# ── 제품 바이블 §7.1 — 네 종류를 섞지 않는다 ────────────────────────────────
#   같은 "환율 1,380원"이라도 실제값인지 전망인지 계획 가정인지 시나리오인지 구분해야 한다.
#   ⚠️ 바이블의 4종에 **기준정보가 없다** — 기준정보는 시점값이 아니라 참조 데이터라서
#     4종 어디에도 속하지 않는다. 섞지 않으려면 이름이 있어야 하므로 `reference` 를 더한다.
#   ⚠️ ECM 설계서 비협상 원칙 3 은 여기에 **경쟁사 추정치**를 더한다("실제·계획·예측·가상
#     시나리오·경쟁사 추정치는 절대로 혼합하지 않는다"). 값의 성격이 다르므로 `competitor` 를
#     별도 종류로 둔다 — 가상 시나리오는 `entity_mode=VIRTUAL` 로 격리되고, 경쟁사 추정치는
#     실제 문맥의 차트에도 함께 표시될 수 있어(§7.3) 값 단위의 표지가 반드시 필요하다.
DATA_KINDS = ("actual", "plan", "forecast", "scenario", "reference", "event", "competitor")

# 요구사항 종류 → 데이터 구분의 결정론적 기본값.
#   외부지표는 등급이 성격을 정한다(§7.2): Gold=확정 실제값, Silver=전망, Bronze=사건 후보.
_KIND_BY_REQ_TYPE = {"master": "reference", "actual": "actual", "driver": "plan"}
_KIND_BY_EXT_GRADE = {"gold": "actual", "silver": "forecast", "bronze": "event"}


def data_kind_of(requirement_type: str, external_grade: str = "") -> str:
    """요구사항의 데이터 구분(§7.1). 규칙이므로 저장하지 않고 언제든 재계산할 수 있다."""
    if requirement_type == "external":
        return _KIND_BY_EXT_GRADE.get((external_grade or "").lower(), "forecast")
    return _KIND_BY_REQ_TYPE.get(requirement_type, "reference")


# ══════════════════════════════════════════════════════════════════════════
# 출처 표시 — §5.2 "AI 의 추천과 사용자의 확정 결정을 구분한다"
# ══════════════════════════════════════════════════════════════════════════
class Provenance(BaseModel):
    """이 항목이 어디서 왔고 사람이 확정했는가.

    `origin` 은 **바뀌지 않는다** — AI 가 제안한 것은 승인 뒤에도 'AI 가 제안했던 것'이다.
    사람이 승인하면 `confirmed` 만 True 가 된다. 둘을 한 필드로 합치면 나중에
    "이 결정이 원래 누구 아이디어였나"를 되짚을 수 없다(§1.3 기업 의도와 결정의 보존)."""
    origin: str = "rule"        # rule | user | ai
    confirmed: bool = False     # 사람이 확정했는가
    note: str = ""


# ══════════════════════════════════════════════════════════════════════════
# §5.1 필수 필드 — 7개 영역
# ══════════════════════════════════════════════════════════════════════════
class BlueprintBusiness(BaseModel):
    """업무 — 목적, 문제, 사용자, 의사결정자, 범위, 제외 범위."""
    objective: str = ""
    problem: str = ""
    users: List[str] = Field(default_factory=list)
    decision_makers: List[str] = Field(default_factory=list)
    in_scope: List[str] = Field(default_factory=list)
    out_of_scope: List[str] = Field(default_factory=list)


class BlueprintKPI(BaseModel):
    """KPI — 지표명, 공식, 단위, 기준일, 허용 오차.

    `formula` 가 비면 `verified=False` 로 남는다 — 공식 없는 지표는 계산할 수 없고,
    §5.2 "근거가 없는 경영 수치는 검증되지 않은 추정으로 표시한다"에 해당한다."""
    name: str
    formula: str = ""
    unit: str = ""
    baseline_date: str = ""
    tolerance: str = ""
    data_kind: str = "plan"

    @property
    def verified(self) -> bool:
        return bool(self.formula and self.unit)


class BlueprintProcess(BaseModel):
    """프로세스 — 입력, 검증, 승인, 예외, 출력."""
    inputs: List[str] = Field(default_factory=list)
    validations: List[str] = Field(default_factory=list)
    approvals: List[str] = Field(default_factory=list)
    exceptions: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)


class BlueprintSystem(BaseModel):
    """시스템 — 추천 앱, 화면, API, 템플릿, 에이전트."""
    recommended_apps: List[str] = Field(default_factory=list)
    screens: List[str] = Field(default_factory=list)
    apis: List[str] = Field(default_factory=list)
    template_id: str = ""
    agents: List[str] = Field(default_factory=list)


class BlueprintSimulation(BaseModel):
    """시뮬레이션 — 가정, 변수, 제약, 기준 시나리오."""
    assumptions: List[str] = Field(default_factory=list)
    variables: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    baseline_scenario: str = ""


class BlueprintRisk(BaseModel):
    """위험 — 데이터 결손, 권한, 외부 연계, 품질, 비용."""
    category: str = "data"      # data | permission | integration | quality | cost
    description: str = ""
    mitigation: str = ""


class BlueprintDataRequirement(BaseModel):
    """Blueprint 에 고정된 데이터 요구사항(§4.5 `data_requirements`).

    플레이북의 정의를 **복사해 고정**한다 — 플레이북이 나중에 개정되어도 이미 승인된
    Blueprint 의 근거는 그때의 것이어야 한다(§5.2 이력 보존)."""
    key: str
    canonical_term: str
    requirement_type: str
    necessity: str
    data_kind: str = "reference"
    purpose: str = ""
    expected_grain: str = ""
    freshness_requirement: str = ""
    owner_department: str = ""
    source_candidates: List[str] = Field(default_factory=list)
    readiness_status: str = "missing"      # held | needs_verification | missing
    gap_impact: str = ""
    next_action: str = ""
    external: Optional[Dict[str, Any]] = None
    sensitivity: str = "internal"          # §5.1 데이터 영역의 '민감도'


class SolutionBlueprint(BaseModel):
    """§5.1 구조화 계약."""
    blueprint_id: str = ""
    consultation_id: str = ""
    title: str = ""
    business_domain: str = ""
    playbook_id: str = ""
    owner_dept_id: str = ""
    owner_user_id: str = ""

    # ── [ECM-lite] 실행 문맥 ──────────────────────────────────────────────
    # ECM 설계서 §10.2: "프로젝트는 반드시 `enterprise_scope_id` 와 `entity_mode` 를 소유한다."
    #   Blueprint 가 프로젝트를 부트스트랩(M0-d)하므로 여기서부터 실어 넘겨야 한다. 나중에
    #   붙이면 이미 승인된 Blueprint 들이 문맥 없는 상태로 남아 프로젝트 귀속을 못 한다.
    tenant_id: str = ""
    enterprise_scope_id: str = ""
    entity_mode: str = "REAL"

    business: BlueprintBusiness = Field(default_factory=BlueprintBusiness)
    kpis: List[BlueprintKPI] = Field(default_factory=list)
    data_requirements: List[BlueprintDataRequirement] = Field(default_factory=list)
    process: BlueprintProcess = Field(default_factory=BlueprintProcess)
    system: BlueprintSystem = Field(default_factory=BlueprintSystem)
    simulation: BlueprintSimulation = Field(default_factory=BlueprintSimulation)
    risks: List[BlueprintRisk] = Field(default_factory=list)

    readiness_score: float = 0.0
    readiness: Dict[str, Any] = Field(default_factory=dict)   # 산정 내역 전체(근거 보존)
    recommended_sequence: List[str] = Field(default_factory=list)

    status: str = "draft"                 # draft | approved | rejected
    provenance: Dict[str, Provenance] = Field(default_factory=dict)
    approved_by: str = ""
    approved_at: str = ""
    rejected_reason: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    # ── 판정 ──────────────────────────────────────────────────────────────
    def unverified_kpis(self) -> List[str]:
        """공식·단위가 없어 계산 불가한 지표. 승인 화면에서 반드시 보여야 한다."""
        return [k.name for k in self.kpis if not k.verified]

    def blocking_gaps(self) -> List[BlueprintDataRequirement]:
        return [r for r in self.data_requirements
                if r.necessity == "required" and r.readiness_status == "missing"]


# ══════════════════════════════════════════════════════════════════════════
# 결정론적 조립
# ══════════════════════════════════════════════════════════════════════════
def _selected_labels(pb: Playbook, answers: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """선택지 식별자 → 사람이 읽을 라벨. Blueprint 본문은 사람이 읽는 문서다."""
    out: Dict[str, List[str]] = {}
    for q in pb.questions:
        picked = {str(v) for v in (answers.get(q.id) or [])}
        labels = [o.label for o in q.options if o.key() in picked]
        if labels:
            out[q.id] = labels
    return out


def assemble_blueprint(pb: Playbook, answers: Dict[str, List[str]],
                       statuses: Optional[Dict[str, str]] = None,
                       initial_prompt: str = "",
                       free_text: Optional[Dict[str, str]] = None) -> SolutionBlueprint:
    """플레이북 + 상담 답변 → Blueprint 초안. **LLM 0콜, 같은 입력이면 같은 결과.**

    `statuses`: 요구사항별 보유 상태(없으면 전부 `missing` — 모르는 것을 보유로 치지 않는다).
    `free_text`: 질문별 '직접 입력' 응답(§4.3 F-DA-02 — 장문 입력은 선택 사항).
    """
    statuses = statuses or {}
    free_text = free_text or {}
    active = active_requirement_keys(pb, answers)
    readiness = score_readiness(pb, statuses, active_requirements=active)
    labels = _selected_labels(pb, answers)

    # ── 업무 영역: 답변을 그대로 근거로 쓴다(요약·재해석하지 않는다) ──────────
    def _joined(qid: str) -> str:
        return " / ".join(labels.get(qid, []))

    purpose_qs = [q for q in pb.questions if q.stage == "purpose"]
    scope_qs = [q for q in pb.questions if q.stage == "scope"]
    user_qs = [q for q in pb.questions if q.stage == "users"]
    decision_qs = [q for q in pb.questions if q.stage == "decision"]

    business = BlueprintBusiness(
        objective=(_joined(purpose_qs[0].id) if purpose_qs else "") or initial_prompt,
        problem=initial_prompt,
        users=[u for q in user_qs for u in labels.get(q.id, [])],
        decision_makers=[d for q in decision_qs for d in labels.get(q.id, [])],
        in_scope=[s for q in scope_qs for s in labels.get(q.id, [])],
        # 제외 범위 = 같은 질문에서 **고르지 않은** 선택지. 사용자가 명시적으로 제외한 것이므로
        #   추론이 아니라 사실이다. §5.1 이 '제외 범위'를 필수로 둔 이유가 이것이다.
        out_of_scope=[o.label for q in scope_qs for o in q.options
                      if o.label not in labels.get(q.id, [])],
    )

    # ── 데이터 요구사항: 플레이북 정의를 복사해 고정 ───────────────────────
    reqs: List[BlueprintDataRequirement] = []
    for r in pb.data_requirements:
        if r.key not in active:
            continue
        ext = r.external.model_dump() if r.external else None
        reqs.append(BlueprintDataRequirement(
            key=r.key, canonical_term=r.canonical_term,
            requirement_type=r.requirement_type, necessity=r.necessity,
            data_kind=data_kind_of(r.requirement_type,
                                  (r.external.grade if r.external else "")),
            purpose=r.purpose, expected_grain=r.expected_grain,
            freshness_requirement=r.freshness_requirement,
            owner_department=r.owner_department,
            source_candidates=list(r.source_candidates),
            readiness_status=str(statuses.get(r.key, "missing") or "missing"),
            gap_impact=r.gap_impact, next_action=r.next_action, external=ext,
        ))

    # ── 위험: 플레이북의 도메인 위험 + 준비도에서 **계산된** 위험 ────────────
    risks = [BlueprintRisk(category="data", description=t) for t in pb.risks]
    for g in readiness["blocking_gaps"]:
        risks.append(BlueprintRisk(
            category="data",
            description=f"필수 데이터 결손: {g['canonical_term']} — {g['impact']}",
            mitigation=g["next_action"]))
    if readiness["unmeasured_weight"] > 0:
        # 준비도가 100점 만점으로 측정되지 않았다는 사실 자체가 위험이다(숨기지 않는다)
        risks.append(BlueprintRisk(
            category="quality",
            description=f"준비도 {readiness['unmeasured_weight']}점 구간이 측정되지 않았습니다"
                        f"(플레이북에 해당 축 요구사항이 정의되지 않음).",
            mitigation="해당 축의 데이터 요구사항을 플레이북에 추가한 뒤 재산정하십시오."))

    bp = SolutionBlueprint(
        title=f"{pb.name_ko}",
        business_domain=pb.business_type,
        playbook_id=pb.playbook_id,
        business=business,
        data_requirements=reqs,
        system=BlueprintSystem(template_id=pb.recommended_template_id),
        risks=risks,
        readiness_score=readiness["score"],
        readiness=readiness,
        recommended_sequence=list(pb.recommended_sequence),
        # 조립은 규칙이므로 origin=rule. 사용자가 고른 답에서 나온 영역은 user.
        provenance={
            "business": Provenance(origin="user", confirmed=False,
                                   note="상담 선택형 답변에서 조립"),
            "data_requirements": Provenance(origin="rule", confirmed=False,
                                            note=f"플레이북 {pb.playbook_id} 정의를 고정"),
            "readiness": Provenance(origin="rule", confirmed=False,
                                    note="결정론 산정(LLM 0콜)"),
            "risks": Provenance(origin="rule", confirmed=False,
                                note="플레이북 위험 + 준비도 결손에서 계산"),
            "kpis": Provenance(origin="rule", confirmed=False, note="미작성"),
        },
    )
    # 자유 입력이 있으면 문제 기술에 덧붙인다(버리지 않는다 — 사용자가 쓴 것은 근거다)
    extra = [t.strip() for t in free_text.values() if (t or "").strip()]
    if extra:
        bp.business.problem = (bp.business.problem + "\n\n[추가 입력]\n" +
                               "\n".join(extra)).strip()
    return bp
