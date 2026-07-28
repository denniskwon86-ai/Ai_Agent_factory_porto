"""업무·데이터 설계 상담 플레이북 — 마스터 명세서 §4 (기능 1) / M0 백로그 1.

플레이북은 "이 업무를 하려면 무엇을 물어보고 어떤 데이터가 필요한가"를 담은 **저작 설정**이다.
사용자 데이터(상담 세션·Blueprint)가 아니므로 DB 가 아니라 파일에 둔다 — `templates/<id>.json`
(워크플로우 템플릿)과 `skills/*.md`(에이전트 스킬)이 이미 같은 규약이고, 로더 관례도 그것을 따른다
(`_safe_id` 정규식 → 경로 조립 → 손상 시 안전 폴백). 마스터 명세서 §18-4 가 "새 저장소를 만들기
전에 현재 저장 방식을 조사하라"고 한 이유가 이것이다.

이 모듈이 담당하는 것 셋:
  ① 플레이북 스키마 (Pydantic — §18-5 "자유 텍스트가 아닌 스키마를 통과한 JSON")
  ② 레지스트리 로더 (`playbooks/*.json`)
  ③ **준비도 산정** — §4.3 F-DA-05. LLM 이 아니라 결정론적 규칙이다.
     "데이터가 준비됐나"는 주관적 판단으로 흐르기 쉬운데, 그 숫자가 프로젝트 착수 여부를
     결정하므로 재현 가능해야 한다(§0-3: 숫자는 결정론적 규칙·검증 엔진이 담당).

⚠️ 상담 세션·Blueprint 의 **저장**은 이 모듈이 하지 않는다(M0-b). 여기는 순수 함수만 둔다 —
  그래야 테스트가 서버·DB 없이 돌고, 준비도 산정이 어디서 불려도 같은 답을 준다.
"""
import json
import os
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYBOOKS_DIR = os.path.join(_ROOT, "playbooks")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")     # `agent_registry._TID_RE` 와 같은 규약


# ══════════════════════════════════════════════════════════════════════════
# 열거 값 — 문자열 상수로 둔다(Literal 로 못 박으면 플레이북 저자가 새 값을 쓸 때
#   파일 전체가 로드 실패한다. 검증은 `validate_playbook()` 이 경고로 알린다.)
# ══════════════════════════════════════════════════════════════════════════

# §4.3 F-DA-03 업무 유형 6종
BUSINESS_TYPES = ("planning_budget", "operations", "analytics_report",
                  "simulation", "data_cleanup", "software_generation")

# §4.3 F-DA-04 데이터 요구 분류
REQUIREMENT_TYPES = ("master",    # 기준정보
                     "actual",    # 실적/거래 데이터
                     "driver",    # 계획/예측 동인
                     "external")  # 외부 지표 (§12 외부환경 인텔리전스)

NECESSITIES = ("required", "recommended", "optional")

# §12.2 외부 데이터 등급. Gold 만 기준계획·공식 시뮬레이션에 쓸 수 있다.
EXTERNAL_GRADES = ("gold", "silver", "bronze")

# ── §4.3 F-DA-05 준비도 5축과 배점 (합 100) ────────────────────────────────
#   명세서가 배점을 못 박았으므로 여기가 진실원본이고, 플레이북이 덮어쓸 수 있다.
READINESS_DIMENSIONS: Dict[str, int] = {
    "master_completeness": 25,   # 기준정보 완성도
    "history_linkage":     25,   # 과거 실적 연결성
    "driver_coverage":     25,   # 계획/운영 동인 확보율
    "quality_freshness":   15,   # 품질·최신성
    "ownership":           10,   # 책임자 지정
}
READINESS_DIMENSION_KO = {
    "master_completeness": "기준정보 완성도",
    "history_linkage":     "과거 실적 연결성",
    "driver_coverage":     "계획/운영 동인 확보율",
    "quality_freshness":   "품질·최신성",
    "ownership":           "책임자 지정",
}

# 요구사항 충족 상태 → 점수 계수.
#   ⚠️ `needs_verification` 을 0.5 로 두는 것은 **모델링 선택**이다: 검증이 필요한 데이터는
#     있는 것도 없는 것도 아니라서 어느 쪽으로 몰아도 틀린다. 절반으로 세고 결손 목록에
#     함께 올려 사람이 판단하게 한다. 값을 바꾸려면 여기 한 곳만 고치면 된다.
STATUS_CREDIT: Dict[str, float] = {
    "held":               1.0,   # 보유
    "needs_verification": 0.5,   # 검증 필요
    "missing":            0.0,   # 부족
}
# 필수/권장의 상대 가중. optional 은 준비도에 넣지 않는다 — 있으면 좋은 것은
#   '준비되지 않음'의 근거가 될 수 없다(있어야 할 것이 없을 때만 감점).
NECESSITY_WEIGHT: Dict[str, float] = {"required": 2.0, "recommended": 1.0, "optional": 0.0}


# ══════════════════════════════════════════════════════════════════════════
# 스키마
# ══════════════════════════════════════════════════════════════════════════
class QuestionOption(BaseModel):
    """선택지 하나. `nodes/clarification.py` 가 LLM 출력으로 만드는 형태와 **동일**하게 맞췄다 —
    프론트 `HOTLInput.tsx` 가 이미 이 모양을 렌더링하므로 상담 UI 가 그것을 재사용한다."""
    label: str
    description: str = ""
    recommended: bool = False
    # 안정 식별자. 비면 `label` 을 쓴다 — 라벨은 문구를 다듬으면 바뀌므로, 저장된 상담 답변이
    #   깨지지 않아야 하는 선택지에는 `value` 를 명시한다.
    value: str = ""
    # ★ 이 선택지를 고르면 켜지는 데이터 요구사항(조건부). 요구사항 쪽이 아니라 **선택지** 쪽에
    #   두는 이유: "제품 단위까지 계획한다"를 골랐을 때 제품 마스터가 필요해지는 식이라,
    #   조건은 질문이 아니라 답에 붙는다. 질문에 붙이면 아무 답이나 해도 켜져 결손이 부풀려진다.
    unlocks_requirements: List[str] = Field(default_factory=list)

    def key(self) -> str:
        return self.value or self.label


class PlaybookQuestion(BaseModel):
    """§4.3 F-DA-02 — 한 번에 하나의 결정만 묻는 선택형 질문.

    `stage` 는 물어보는 순서의 근거다(명세서: 목적·범위·시간·사용자·데이터·결정 단계를 우선).
    장문 입력은 선택이고 추천안만 눌러도 진행되어야 하므로 `options` 는 최소 2개를 요구한다."""
    id: str
    question: str
    why: str = ""                       # 왜 묻는지 — 사용자가 선택을 이해하려면 필요하다
    stage: str = ""                     # purpose | scope | time | users | data | decision
    multi: bool = False
    options: List[QuestionOption] = Field(default_factory=list)


class ExternalSpec(BaseModel):
    """외부 지표 요구의 부가 규격 — §12.

    ⚠️ 이 필드들을 M0 에 미리 넣는 이유: 외부 수집 구현은 M1 이지만, 스키마에 자리가 없으면
      플레이북을 다시 쓰고 저장분을 마이그레이션해야 한다. 값만 받아두고 소비는 M1 이 한다."""
    grade: str = "gold"                 # §12.2 — 기준계획은 gold 만 허용
    acceptable_latency: str = ""        # 예: "1개월", "1일" (§12.4 원천별 허용 지연)
    vintage_required: bool = True       # §12.5 — 당시 발표값 재현 가능해야 한다
    canonical_source_hint: str = ""     # 권장 원천(공식 API/CSV 우선, §12.4)


class DataRequirement(BaseModel):
    """§4.5 `data_requirements` — 상담이 "이 데이터가 필요하다"고 판단하는 항목.

    `gap_impact`/`next_action` 은 필수다. §4.3 F-DA-05 가 "점수와 함께 반드시 결손 항목, 영향,
    다음 조치를 표시한다"고 못 박았는데, 그 문구를 산정 시점에 LLM 으로 만들면 매번 달라진다.
    플레이북 저자가 미리 써두면 결정론적이고 도메인 지식이 보존된다."""
    key: str                            # 플레이북 내 고유 키(질문의 unlocks_requirements 가 참조)
    canonical_term: str                 # 업무 용어(§6 business_terms 와 연결될 이름)
    requirement_type: str = "master"
    necessity: str = "required"
    purpose: str = ""
    expected_grain: str = ""            # 예: "월 × 법인 × 계정"
    freshness_requirement: str = ""     # 예: "월 마감 후 5영업일"
    owner_department: str = ""           # 데이터 소유 부서(§4.3 F-DA-04)
    source_candidates: List[str] = Field(default_factory=list)   # 일반적인 원천 시스템
    readiness_dimension: str = "master_completeness"
    starter: bool = True                # §4.3 F-DA-04 "최소 시작 데이터"인가(아니면 고도화)
    gap_impact: str = ""                # 없으면 무엇이 안 되는가
    next_action: str = ""               # 다음에 무엇을 하면 되는가
    external: Optional[ExternalSpec] = None


# ── ECM 프로필 상속 체인에서 플레이북의 자리 ──────────────────────────────
# ⚠️ `design_enterprise_context_master.md` 는 플레이북을 언급하지 않는다. 그런데 §4.4 의
#   `data_profile`/`solution_profile`/`agent_profile` 이 플레이북의 데이터 요구·추천 템플릿과
#   정면으로 겹친다. 둘 다 존재하면 무엇이 이기는지 정해야 하므로 **여기서 못 박는다**:
#
#     플레이북 = §4.4 상속 체인 **최상위(산업 공통 프로필)** 의 저작 기본값
#       → 기업집단 → 법인 → 사업부 → 사업장/공장 프로필이 순서대로 오버레이
#       → 충돌 시 가장 하위의 **승인된** 프로필이 이긴다
#
#   이렇게 두는 이유: 도메인 지식(질문 문구·데이터 요구·결손 안내)은 리뷰와 이력이 필요하므로
#   git diff 가 되는 파일에 남기고, DB(`enterprise_profiles`)는 **조직별 차이만** 담는다.
#   플레이북을 DB 로 흡수하면 도메인 지식 변경이 코드 리뷰를 우회한다.
#   ⚠️ 오버레이 해석(리솔버)은 아직 없다 — ECM 로드맵 E2 다. 지금은 자리와 규약만 선언한다.
PROFILE_LAYER_INDUSTRY_COMMON = "industry_common"


class Playbook(BaseModel):
    """업무 유형별 상담 플레이북 = 산업 공통 프로필의 저작 기본값(위 주석 참조)."""
    playbook_id: str
    name_ko: str
    description: str = ""
    business_type: str = "planning_budget"
    owner_department_hint: str = ""
    # ECM 상속 체인에서 이 플레이북이 놓이는 층. 지금은 전부 산업 공통이다.
    profile_layer: str = PROFILE_LAYER_INDUSTRY_COMMON
    # 어느 업종에 적용되는가(ECM `industry_code`). 비면 업종 무관 공통.
    #   E2 에서 조직의 `business_profile.industry_code` 와 매칭해 후보를 좁히는 데 쓴다.
    industry_codes: List[str] = Field(default_factory=list)
    # §4.7 — 상담 결과를 기존 파이프라인으로 넘길 때 추천할 워크플로우 템플릿
    recommended_template_id: str = ""
    questions: List[PlaybookQuestion] = Field(default_factory=list)
    data_requirements: List[DataRequirement] = Field(default_factory=list)
    # 배점 재정의(비우면 READINESS_DIMENSIONS 기본값)
    readiness_weights: Dict[str, int] = Field(default_factory=dict)
    recommended_sequence: List[str] = Field(default_factory=list)   # §4.4 실행 보드
    risks: List[str] = Field(default_factory=list)

    def weights(self) -> Dict[str, int]:
        w = dict(READINESS_DIMENSIONS)
        w.update({k: int(v) for k, v in (self.readiness_weights or {}).items()
                  if k in READINESS_DIMENSIONS})
        return w

    def requirement(self, key: str) -> Optional[DataRequirement]:
        return next((r for r in self.data_requirements if r.key == key), None)


# ══════════════════════════════════════════════════════════════════════════
# 레지스트리
# ══════════════════════════════════════════════════════════════════════════
def _safe_id(playbook_id: str) -> str:
    if not _ID_RE.match(playbook_id or ""):
        raise ValueError("잘못된 playbook_id 형식입니다(허용: 영숫자/_/-).")
    return playbook_id


def _path(playbook_id: str) -> str:
    return os.path.join(PLAYBOOKS_DIR, f"{_safe_id(playbook_id)}.json")


def load_playbook(playbook_id: str) -> Optional[Playbook]:
    """플레이북 1건 로드. 파일이 없거나 스키마 불일치면 None.

    ⚠️ 두 실패를 **구분한다**:
      · 잘못된 `playbook_id`(경로 이탈 등) → `ValueError` 를 올린다. 이건 요청 입력 오류이므로
        라우트가 400 으로 바꿔야 한다(`agent_registry._safe_tid` 와 같은 규약).
      · 파일 부재·손상·스키마 불일치 → `None`. 플레이북 하나가 깨졌다고 상담 기능 전체가
        500 이 되면 안 된다. 왜 깨졌는지는 `validate_playbook()` 이 알려준다."""
    path = _path(playbook_id)          # 여기서 나는 ValueError 는 삼키지 않는다
    try:
        with open(path, "r", encoding="utf-8") as f:
            return Playbook.model_validate(json.load(f))
    except Exception:
        return None


def list_playbooks() -> List[Dict[str, Any]]:
    """플레이북 요약 목록(상담 진입 화면용). 손상된 파일은 건너뛴다."""
    out = []
    if not os.path.isdir(PLAYBOOKS_DIR):
        return out
    for fn in sorted(os.listdir(PLAYBOOKS_DIR)):
        if not fn.endswith(".json"):
            continue
        pb = load_playbook(fn[:-5])
        if not pb:
            continue
        out.append({
            "playbook_id": pb.playbook_id,
            "name_ko": pb.name_ko,
            "description": pb.description,
            "business_type": pb.business_type,
            "question_count": len(pb.questions),
            "requirement_count": len(pb.data_requirements),
            "recommended_template_id": pb.recommended_template_id,
        })
    return out


def validate_playbook(pb: Playbook) -> List[str]:
    """저작 실수를 찾아 사람이 읽을 경고 목록으로 돌려준다(로드를 막지는 않는다).

    스키마로 못 박지 않고 경고로 두는 이유: 열거 값이 늘어날 때 파일이 통째로 로드 실패하면
    플레이북을 늘리는 일 자체가 위험해진다. 대신 여기서 반드시 눈에 띄게 한다."""
    warns: List[str] = []
    if pb.business_type not in BUSINESS_TYPES:
        warns.append(f"알 수 없는 business_type: {pb.business_type}")
    if pb.recommended_sequence == []:
        warns.append("recommended_sequence 가 비어 있습니다(§4.4 실행 보드에 표시할 권장 단계).")

    q_ids, r_keys = set(), {r.key for r in pb.data_requirements}
    for q in pb.questions:
        if q.id in q_ids:
            warns.append(f"질문 id 중복: {q.id}")
        q_ids.add(q.id)
        if len(q.options) < 2:
            warns.append(f"[{q.id}] 선택지가 2개 미만입니다(선택형 대화가 성립하지 않습니다).")
        if sum(1 for o in q.options if o.recommended) != 1:
            # clarification.py 도 같은 규칙으로 정규화한다 — 프론트 기본 선택값을 보장하려면 정확히 1개.
            warns.append(f"[{q.id}] 추천 선택지가 정확히 1개여야 합니다(프론트 기본 선택값).")
        _okeys = set()
        for o in q.options:
            if o.key() in _okeys:
                warns.append(f"[{q.id}] 선택지 식별자 중복: {o.key()}")
            _okeys.add(o.key())
            for k in o.unlocks_requirements:
                if k not in r_keys:
                    warns.append(f"[{q.id}/{o.key()}] 존재하지 않는 요구사항 키를 참조합니다: {k}")

    # ★ 저작 불변식: **조건부 요구사항은 `required` 일 수 없다.**
    #   `required` 인데 특정 선택지에서만 켜지면, 추천안만 고른 사용자에게는 플레이북이 스스로
    #   "필수"라 선언한 데이터가 활성화되지 않는다 — 준비도가 실제보다 높게 나오고 결손 안내도
    #   안 뜬다(실제로 이 플레이북 초안에서 21건 중 7건만 활성화됐다).
    #   범위에 따라 달라지는 항목은 `recommended` 로 두고, 정말 항상 필요한 것만 `required` 로 둔다.
    _conditional = {k for q in pb.questions for o in q.options for k in o.unlocks_requirements}
    for r in pb.data_requirements:
        if r.key in _conditional and r.necessity == "required":
            warns.append(f"[{r.key}] required 인데 조건부입니다 — 항상 적용되게 하거나 "
                         f"necessity 를 recommended 로 낮추십시오.")

    seen = set()
    for r in pb.data_requirements:
        if r.key in seen:
            warns.append(f"요구사항 key 중복: {r.key}")
        seen.add(r.key)
        if r.requirement_type not in REQUIREMENT_TYPES:
            warns.append(f"[{r.key}] 알 수 없는 requirement_type: {r.requirement_type}")
        if r.necessity not in NECESSITIES:
            warns.append(f"[{r.key}] 알 수 없는 necessity: {r.necessity}")
        if r.readiness_dimension not in READINESS_DIMENSIONS:
            warns.append(f"[{r.key}] 알 수 없는 readiness_dimension: {r.readiness_dimension}")
        if r.necessity != "optional" and not (r.gap_impact and r.next_action):
            # §4.3 F-DA-05 의 강제 요구 — 점수만 주고 조치를 못 알려주면 쓸모가 없다
            warns.append(f"[{r.key}] gap_impact/next_action 이 비었습니다(결손 시 안내 불가).")
        if r.requirement_type == "external":
            if r.external is None:
                warns.append(f"[{r.key}] external 타입인데 external 규격이 없습니다(§12 등급·지연).")
            elif r.external.grade not in EXTERNAL_GRADES:
                warns.append(f"[{r.key}] 알 수 없는 외부 데이터 등급: {r.external.grade}")
    return warns


# ══════════════════════════════════════════════════════════════════════════
# 준비도 산정 — §4.3 F-DA-05 (LLM 0콜, 결정론)
# ══════════════════════════════════════════════════════════════════════════
def score_readiness(pb: Playbook, statuses: Dict[str, str],
                    active_requirements: Optional[List[str]] = None) -> Dict[str, Any]:
    """플레이북 + 요구사항별 보유 상태 → 준비도 점수와 결손 안내.

    `statuses`: {요구사항 key: held|needs_verification|missing}. 없는 키는 `missing` 으로 본다 —
      **모르는 것을 보유로 치지 않는다**(낙관 편향이 프로젝트 착수 판단을 망친다).
    `active_requirements`: 조건부 요구사항 필터(질문 답변으로 켜진 것만). None 이면 전량.

    반환의 `score` 는 100점 만점이며, 플레이북이 어떤 차원의 요구사항을 아예 정의하지 않았으면
    그 배점은 **얻을 수 없는 점수로 남긴다**(만점 처리하지 않는다). 정의가 없는 것이 준비됐다는
    뜻은 아니기 때문이다. 그 경우를 사람이 알 수 있게 `measurable_max` 를 함께 준다.
    """
    weights = pb.weights()
    reqs = [r for r in pb.data_requirements
            if active_requirements is None or r.key in set(active_requirements)]

    dims: Dict[str, Dict[str, Any]] = {
        d: {"dimension": d, "name_ko": READINESS_DIMENSION_KO.get(d, d),
            "weight": weights.get(d, 0), "earned": 0.0, "possible": 0.0,
            "measured": False, "score": 0.0}
        for d in READINESS_DIMENSIONS
    }
    gaps: List[Dict[str, Any]] = []

    for r in reqs:
        status = str(statuses.get(r.key, "missing") or "missing").lower()
        credit = STATUS_CREDIT.get(status, 0.0)
        nw = NECESSITY_WEIGHT.get(r.necessity, 0.0)
        d = dims.get(r.readiness_dimension)
        if d is not None and nw > 0:
            d["possible"] += nw
            d["earned"] += nw * credit
            d["measured"] = True
        # 결손 안내 — optional 도 '검증 필요/부족'이면 알려준다(점수엔 반영하지 않되 숨기지 않는다)
        if credit < 1.0:
            gaps.append({
                "key": r.key, "canonical_term": r.canonical_term,
                "requirement_type": r.requirement_type, "necessity": r.necessity,
                "status": status,
                "owner_department": r.owner_department,
                "impact": r.gap_impact,
                "next_action": r.next_action,
                "counts_toward_score": nw > 0,
            })

    score = 0.0
    measurable_max = 0
    for d in dims.values():
        if d["possible"] > 0:
            d["score"] = round(d["weight"] * (d["earned"] / d["possible"]), 2)
            measurable_max += d["weight"]
        d["earned"] = round(d["earned"], 2)
        d["possible"] = round(d["possible"], 2)
        score += d["score"]

    # 결손은 '필수 → 권장 → 선택' 순, 같은 등급이면 부족 → 검증 필요 순으로 보여준다.
    _n_order = {"required": 0, "recommended": 1, "optional": 2}
    _s_order = {"missing": 0, "needs_verification": 1}
    gaps.sort(key=lambda g: (_n_order.get(g["necessity"], 3), _s_order.get(g["status"], 2),
                             g["key"]))

    return {
        "score": round(score, 1),
        "measurable_max": measurable_max,
        "unmeasured_weight": 100 - measurable_max,
        "dimensions": [dims[d] for d in READINESS_DIMENSIONS],
        "gaps": gaps,
        "blocking_gaps": [g for g in gaps if g["necessity"] == "required"
                          and g["status"] == "missing"],
        "evaluated_requirements": len(reqs),
    }


def active_requirement_keys(pb: Playbook, answers: Dict[str, List[str]]) -> List[str]:
    """선택된 답에 따라 켜진 요구사항 키 목록.

    어떤 선택지도 참조하지 않는 요구사항은 **항상 적용**된다(무조건 필요한 것). 조건부는 그
    선택지가 실제로 선택됐을 때만 켠다 — 고르지도 않은 범위의 데이터를 요구사항으로 세우면
    결손이 부풀려지고 준비도가 실제보다 낮게 나온다.

    `answers`: {질문 id: [선택지 식별자]}. 식별자는 `value`(없으면 `label`)로 맞춘다."""
    conditional = {k for q in pb.questions for o in q.options for k in o.unlocks_requirements}
    active = {r.key for r in pb.data_requirements if r.key not in conditional}
    for q in pb.questions:
        picked = {str(v) for v in (answers.get(q.id) or [])}
        if not picked:
            continue
        for o in q.options:
            if o.key() in picked:
                active.update(o.unlocks_requirements)
    return sorted(active)
