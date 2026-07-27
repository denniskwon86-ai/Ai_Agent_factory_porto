# ==========================================
# 업무표준 분류 등록 + 초기 시드 (멱등)
# ==========================================
# ⚠️ `master_records.type_id` 는 `entity_types(type_id)` 를 참조하므로,
#   레코드를 넣기 전에 **분류를 먼저 등록**해야 한다.
#
# 기존 분류 10개는 전부 업무 도메인 데이터(자재·설비·KPI·품질규격…)다.
# 업무표준은 성격이 다르다 — **거버넌스/제도** 데이터이므로 별도 분류(`work_standard`)와
# 별도 도메인(`governance`)으로 구분한다.
#
# 시드 원천은 `criteria.py` 의 STAGE_RUBRICS 다. 등록 후에는 DB 가 진실원천이 되고,
# criteria.py 는 미등록/장애 시 폴백으로만 남는다.
# ==========================================
from typing import Dict, Any

from core.work_standard import (
    WORK_REGULATION_TYPE, WORK_GUIDELINE_TYPE,
    KIND_REGULATION, KIND_GUIDELINE,
    standard_code, register_standard,
)

# 어떤 단계가 '판정'이고 어떤 단계가 '생성'인가 — 이 구분이 분류를 가른다.
#   판정: 앞 단계 산출물을 받아 통과/반려를 정한다 → 규정(regulation)
#   생성: 산출물을 만든다. 판정 권한이 없다 → 지침(guideline)
_JUDGING_STAGES = {"PMO", "CODE_REVIEW", "QA", "SUPERVISOR"}

# 단계별 '역할 서술'과 '금지 사항' — 루브릭(무엇을 채점하나)만으로는 전달되지 않는,
# **에이전트가 자기 자리를 이해하는 데 필요한 문장**. 오늘 실측된 역할 혼선을 문서화한다.
_ROLE_META: Dict[str, Dict[str, Any]] = {
    "RFP": {
        "agent_id": "RFP_Analyst",
        "role_statement": "발주 의도를 구조화한 요구사항 정의서(RFP)를 작성한다.",
        "inputs": "고객의 아이디어와 확인 인터뷰 답변",
        "deliverable": "요구사항 정의서(RFP) — 이후 모든 단계의 계약서",
        "must_include": [
            "발주 목적과 해결하려는 문제를 한 문단으로",
            "필수 구성요소(must-have)와 선택요소(nice-to-have)의 명확한 구분",
            "REQ-ID 를 붙인 비즈니스 요구 목록",
            "수용 기준 — '무엇이 되면 완료인가'를 검증 가능한 문장으로",
        ],
        "principles": [
            "고객이 말하지 않은 것을 발명하지 말 것. 추정이 필요하면 가정으로 표시할 것.",
            "구현 방법이 아니라 **요구**를 쓸 것 — 기술 선택은 아키텍트의 몫이다.",
        ],
    },
    "PLANNING": {
        "agent_id": "Master_PM",
        "role_statement": "RFP 를 근거로 실행 가능한 기획서(PRD)를 작성한다.",
        "inputs": "요구사항 정의서(RFP)",
        "deliverable": "기획서(PRD) — WBS 분할과 최종 검수의 기준",
        "must_include": [
            "FR-ID 를 붙인 기능 요구 목록(각 요구는 하나의 검증 가능한 동작)",
            "비기능 요구(성능·보안·사용성 등) 중 실제로 해당하는 것만",
            "측정 가능한 수용 기준",
            "범위 밖(out of scope) 명시",
            "RFP 의 REQ-ID 와의 추적 관계",
        ],
        "principles": [
            "FR-ID 는 이후 WBS 배정과 최종 검수에서 대조되므로 **빠짐없이, 중복 없이** 부여할 것.",
            "'~를 지원한다' 같은 모호한 표현 대신 사용자가 무엇을 하면 무엇이 되는지로 쓸 것.",
        ],
    },
    "PMO": {
        "agent_id": "Master_PMO",
        "role_statement": "PRD 를 1회 스프린트로 소화 가능한 작업 단위(WBS)로 분할하고 담당을 배정한다.",
        "evaluates": "기획서(PRD)와 아키텍처",
        "must_not": [
            "WBS 는 이진이다 — '미흡하지만 통과'는 없다. 내용이 빠졌거나 배분이 잘못됐으면 다시 분할한다.",
        ],
    },
    "ARCHITECTURE": {
        "agent_id": "Architect",
        "role_statement": "PRD·UI 를 근거로 시스템 구조와 기술 결정(ADR)을 확정한다.",
        "inputs": "기획서(PRD)와 승인된 UI 목업",
        "deliverable": "아키텍처 문서와 ADR — WBS 분할과 기술명세의 입력",
        "must_include": [
            "컴포넌트 경계와 각 컴포넌트의 책임",
            "데이터 흐름(입력 → 처리 → 저장 → 표시)",
            "기술 스택 선택과 그 근거(ADR)",
        ],
        "principles": [
            "**한 프로젝트에는 하나의 아키텍처만 존재한다.** 이미 정해진 스택이 있으면 그것을 따르고, "
            "바꿔야 한다면 기존 구조를 대체하는 것이지 나란히 두는 것이 아니다.",
            "이 규모에 필요한 만큼만 설계할 것 — 쓰지 않을 계층을 미리 만들지 말 것.",
        ],
    },
    "TECH_SPEC": {
        "agent_id": "Tech_Lead",
        "role_statement": "이번 태스크 범위의 파일 책임·인터페이스 계약을 실제 파일 경로로 명시한다.",
        "inputs": "아키텍처와 이번 WBS 태스크의 goal/scope, 그리고 워크스페이스의 실제 파일 목록",
        "deliverable": "기술명세 — 개발자가 그대로 구현할 수 있는 파일별 계약",
        "must_include": [
            "파일별 책임과 실제 상대 경로",
            "함수/컴포넌트의 입력·출력·오류 처리",
            "이번 태스크가 담당하는 FR-ID",
            "서버 API 가 필요 없으면 '서버 API 없음'을 명시",
        ],
        "principles": [
            "**워크스페이스에 실제로 있는 파일**만 근거로 삼을 것. 파일 목록이 컨텍스트에 주어진다.",
            "삭제가 필요하면 개발자가 `deleted_files` 로 지울 수 있다 — 지시만 하고 방치하지 말 것.",
        ],
        "must_not": [
            "워크스페이스에 없는 파일이나 근거 없는 서버 API 를 발명하지 말 것.",
            "이번 태스크 범위 밖의 기능을 재설계하지 말 것.",
        ],
    },
    "CODE_REVIEW": {
        "agent_id": "Reviewer",
        "role_statement": "사용자를 대리해 수용 테스트를 수행한다 — 요구된 기능이 있는가/없는가, 되는가/안되는가만 판정한다.",
        "evaluates": "워크스페이스의 실제 산출물(코드)과 이번 태스크가 담당한 요구",
        "must_not": [
            "코드 품질(가독성·구조·네이밍·타입·성능·테스트 부재)로 반려하지 말 것 — QA 의 몫이다.",
            "존재하지 않는 파일을 근거로 반려하지 말 것.",
            "동작하는데 마음에 안 드는 것은 통과시키고 의견만 남길 것.",
        ],
    },
    "QA": {
        "agent_id": "QA",
        "role_statement": "품질을 평가하되, 통과는 최소 기준선으로만 막는다.",
        "evaluates": "인도 직전의 전체 통합 산출물",
        "must_not": [
            "요구 기능이 모두 구현되고 시스템에 큰 해가 없다면 품질을 이유로 반려하지 말 것.",
            "90~100점을 요구하지 말 것 — 최소 기준만 넘으면 통과시키고 나머지는 리포트로 넘길 것.",
        ],
    },
    "SUPERVISOR": {
        "agent_id": "Supervisor",
        "role_statement": "최종고객의 대리인·관리인이다. 합부는 최종고객이 정한다 — 당신은 고객이 판단하기 쉽게 정리하고, 고객의 요구를 전문 지시로 번역해 담당자에게 전달·조율한다.",
        "evaluates": "인도된 결과물과 QA 리포트",
        "must_not": [
            "직접 합부를 판정하지 말 것 — 당신의 의견은 권고다.",
            "품질을 이유로 반려하지 말 것.",
            "고객에게 기술 용어를 쓰지 말 것.",
        ],
    },
}

_REGULATION_SCHEMA = {
    "stage": "str", "agent_id": "str", "standard_kind": "str",
    "role_statement": "str", "evaluates": "str", "pass_threshold": "number",
}
_GUIDELINE_SCHEMA = {
    "stage": "str", "agent_id": "str", "standard_kind": "str",
    "role_statement": "str", "inputs": "str", "deliverable": "str",
}


def ensure_type() -> dict:
    """두 분류를 등록한다(이미 있으면 무시). {분류: 신규등록여부} 반환.

    ⚠️ 분류를 나누는 이유: 판정 에이전트와 생성 에이전트는 **따라야 할 것의 성격이 다르다.**
      한 분류에 섞으면 지침을 규정처럼 강제해 생성이 막히거나, 규정을 지침처럼 느슨하게 써서
      가짜 통과가 난다."""
    from core.master_data import master_data
    out = {}
    if not master_data.get_type(WORK_REGULATION_TYPE):
        master_data.create_type(
            type_id=WORK_REGULATION_TYPE,
            name_ko="업무규정(판정 에이전트)",
            description=(
                "앞 단계 산출물을 받아 통과/반려를 정하는 에이전트가 따르는 규정. "
                "무엇을 어떤 기준값으로 판정하는지를 정의하며 엄격히 적용된다. "
                "법규처럼 개정 시 새 버전이 생기고 구판은 리니지로 보존된다."
            ),
            attr_schema=_REGULATION_SCHEMA,
        )
        out[WORK_REGULATION_TYPE] = True
    if not master_data.get_type(WORK_GUIDELINE_TYPE):
        master_data.create_type(
            type_id=WORK_GUIDELINE_TYPE,
            name_ko="업무지침(생성 에이전트)",
            description=(
                "산출물을 만드는 에이전트가 따르는 작성 표준. 필수 포함 항목·작성 원칙·금지 사항을 "
                "정의한다. 판정 권한을 부여하지 않는다."
            ),
            attr_schema=_GUIDELINE_SCHEMA,
        )
        out[WORK_GUIDELINE_TYPE] = True
    return out


def seed_from_criteria(force: bool = False) -> Dict[str, str]:
    """`criteria.py` 의 STAGE_RUBRICS 를 업무표준으로 등록한다(멱등).

    force=False: 이미 등록된 단계는 건너뛴다(운영 중 개정본을 덮어쓰지 않기 위해).
    force=True : 전 단계를 재등록한다 — 새 버전이 되며 구판은 보존된다."""
    from criteria import STAGE_RUBRICS
    from core.master_data import master_data

    ensure_type()
    result: Dict[str, str] = {}
    for stage, rubric in STAGE_RUBRICS.items():
        code = standard_code(stage)
        existing = master_data.get_record(code)
        if existing and not force:
            result[stage] = f"skip(v{existing.get('version')})"
            continue
        meta = _ROLE_META.get(stage, {})
        is_judge = stage in _JUDGING_STAGES
        kind = KIND_REGULATION if is_judge else KIND_GUIDELINE
        payload = {
            "stage": stage,
            "agent_id": meta.get("agent_id", ""),
            "role_statement": meta.get("role_statement", ""),
            "must_not": meta.get("must_not", []),
            # 채점 루브릭은 두 부류 모두에 담는다. 규정에서는 '판정 기준'이고,
            # 지침에서는 '내 산출물이 어떻게 채점되는지'(자가 점검)로 쓰인다.
            "checks": rubric.get("checks", []),
            "pass_threshold": rubric.get("pass_threshold", 0.7),
            "hard_fail_checks": rubric.get("hard_fail_checks", []),
            "judge_heavy": rubric.get("judge_heavy", False),
            "judge_persona": rubric.get("judge_persona", ""),
        }
        if is_judge:
            payload["evaluates"] = meta.get("evaluates", "")
        else:
            payload["inputs"] = meta.get("inputs", "")
            payload["deliverable"] = meta.get("deliverable", "")
            payload["must_include"] = meta.get("must_include", [])
            payload["principles"] = meta.get("principles", [])

        label = "업무규정" if is_judge else "업무지침"
        rec = register_standard(
            stage=stage,
            name=f"{stage} {label}" + (f" ({meta['agent_id']})" if meta.get("agent_id") else ""),
            payload=payload,
            kind=kind,
            source="system",
        )
        result[stage] = f"{kind}(v{rec.get('version')})"
    return result
