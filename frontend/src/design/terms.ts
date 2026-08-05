// [이관 3/10] 내부 값 → **사용자 용어** 사전
//
// ★★ 이관 완료 조건 ①: 사용자 용어만 노출하고 내부 엔티티명·슬러그는 숨긴다.
//   2/10 에서 `knowledge/packs` · `master_type` 이 화면에 그대로 나갔다. 사용자에게 그 문자열은
//   뜻이 없고, «시스템이 뭔가 잘못됐다»는 인상만 남긴다.
//
// ⚠️ 사전에 없는 값을 **조용히 통과시키지 않는다.** 단계가 하나 추가되면 그 단계만 영문 코드로
//   나가는데, 그건 아무 오류도 내지 않아 아무도 모른다. 그래서 모르는 값은 `console.error` 로
//   알린다 — 캡처 스크립트가 콘솔 오류를 수집하므로 게이트에서 걸린다(이름을 붙이기 전에는
//   화면이 통과하지 못한다).
//
// ★ 코드·식별자는 여기 대상이 아니다. `BP-GOLD-001`, `STD-QA` 같은 값은 **실제 식별자**이고,
//   사용자도 그 문자열로 찾는다. 바꾸면 오히려 소통이 끊긴다. 바꿀 것은 «분류·상태·역할»처럼
//   시스템 내부 어휘로 표현된 것들이다.

const warned = new Set<string>();

/** 사전에서 사용자 용어를 찾는다. 없으면 원문을 돌려주되 **한 번은 크게 알린다.** */
export function userTerm(dict: Record<string, string>, raw: string, dictName = '용어'): string {
  const key = String(raw ?? '').trim();
  if (!key) return '';
  const hit = dict[key];
  if (hit) return hit;
  const mark = `${dictName}:${key}`;
  if (!warned.has(mark)) {
    warned.add(mark);
    console.error(`[terms] ${dictName} 사전에 «${key}» 가 없습니다 — 내부 값이 화면에 그대로 `
      + `나갑니다. design/terms.ts 에 사용자 용어를 추가하십시오.`);
  }
  return key;
}

/** 파이프라인 단계. 영문 코드는 `criteria.STAGE_RUBRICS` 와 에이전트 레지스트리의 `stage` 다.
 *
 * ⚠️ 업무표준(3/10)은 8개 단계만 쓰지만 **에이전트 레지스트리는 15개**를 쓴다(6/10 실측).
 *   사전이 좁으면 나머지가 영문 코드로 화면에 나간다 — 실제로 `CLARIFICATION` · `UI_DESIGN` 이
 *   그렇게 노출됐다. 한 사전으로 합쳐 두면 어느 화면에서 쓰든 같은 한국어가 나온다. */
export const STAGE_KO: Record<string, string> = {
  CLARIFICATION: '요구 확인',
  RFP: '요구사항 정의',
  PLANNING: '사업 기획',
  UI_DESIGN: '화면 설계',
  VISION_QA: '화면 검증',
  ARCHITECTURE: '시스템 설계',
  PMO: '진행 관리',
  TECH_SPEC: '기술 명세',
  EXECUTION: '구현',
  BUILD: '빌드',
  CODE_REVIEW: '코드 심사',
  QA: '품질 검증',
  SUPERVISOR: '총괄 감독',
  MANUAL: '매뉴얼 작성',
};

/** 모델 등급. 사용자에게 «pro/flash»는 «무엇이 다른가»를 말하지 않는다. */
export const MODEL_TIER_KO: Record<string, string> = {
  pro: '고성능',
  flash: '경량·빠름',
  lite: '최소',
};

export const modelTierKo = (v: string) => userTerm(MODEL_TIER_KO, v, '모델 등급');

/** 표준 분류. `regulation` 은 판정 권한이 있고 `guideline` 은 없다 — 이 차이가 핵심이다. */
export const STANDARD_KIND_KO: Record<string, string> = {
  regulation: '업무규정',
  guideline: '업무지침',
};

/** 담당 에이전트. 사용자에게는 «누가 이 일을 하는가»로 읽혀야 한다. */
export const AGENT_KO: Record<string, string> = {
  RFP_Analyst: '요구 분석 담당',
  Master_PM: '기획 총괄',
  Master_PMO: '진행 관리 총괄',
  Architect: '설계 담당',
  Tech_Lead: '기술 총괄',
  Reviewer: '코드 심사 담당',
  QA: '품질 검증 담당',
  Supervisor: '총괄 감독',
};

/** 개정본의 효력 상태. ⚠️ «구판»과 «폐지»는 다르다 — 구판은 그때의 판정 근거로 계속 유효하다. */
export const RECORD_STATUS_KO: Record<string, string> = {
  active: '시행 중',
  superseded: '개정으로 대체(구판)',
  retired: '폐지',
  draft: '초안',
};

/** 표준이 어디서 왔는가. «코드 기본값»은 아직 사람이 개정하지 않았다는 뜻이다. */
export const STANDARD_SOURCE_KO: Record<string, string> = {
  registered: '등록된 개정본',
  fallback: '코드 기본값(미등록)',
  user: '사용자 등록',
  seed: '기본값 시드',
  system: '시스템 등록',
};

/** 점검 항목의 판정 방식. 사람이 이 차이를 알아야 결과를 어디까지 믿을지 정할 수 있다. */
export const CHECK_TYPE_KO: Record<string, string> = {
  deterministic: '규칙 판정',
  llm_judge: '모델 판정',
};

/** 부서 안에서의 역할. `viewer/member/manager` 는 내부 값이고 사용자에게는 «무엇을 할 수
 *  있는가»로 읽혀야 한다. ⚠️ 빈 값은 «역할 없음»이며 «권한 없음»과 같지 않다(상위 부서에서
 *  상속받을 수 있다) — 그래서 여기에 빈 값을 넣지 않고 화면이 따로 말한다. */
export const DEPT_ROLE_KO: Record<string, string> = {
  viewer: '열람',
  member: '작업',
  manager: '관리',
};

/** 부서·계정의 효력 상태. */
export const ORG_STATUS_KO: Record<string, string> = {
  active: '운영 중',
  retired: '폐지',
  draft: '초안',
  superseded: '개정으로 대체(구판)',
};

/** 데이터 계약의 상태. ⚠️ «확인 불가»를 «지켜짐»과 같은 것으로 읽으면 «계약 준수 중»이라는
 *  거짓 안심이 생긴다 — 이 화면에서 가장 조심해야 하는 오독이다. */
export const CONTRACT_STATE_KO: Record<string, string> = {
  kept: '지켜짐',
  at_risk: '주의',
  breached: '위반',
  unverifiable: '확인 불가',
};

/** 심각도. */
export const SEVERITY_KO: Record<string, string> = {
  high: '높음', medium: '보통', low: '낮음',
};

/** 외부 자료의 신뢰 등급. 원문(bronze/silver/gold)은 사용자에게 뜻이 약하다. */
export const DATA_GRADE_KO: Record<string, string> = {
  gold: '확정치(최상)',
  silver: '잠정치(중간)',
  bronze: '참고치(하)',
};

/** 카탈로그·품질 점검이 지적하는 결손 종류. */
export const FINDING_KIND_KO: Record<string, string> = {
  owner_missing: '책임자 미지정',
  refresh_missing: '갱신 주기 미지정',
  sensitivity_missing: '민감도 미지정',
  producer_missing: '생산자 자산 없음',
  freshness_unknown: '최신성 확인 불가',
  schema_missing: '스키마 미등록',
  scope_missing: '조직 범위 미지정',
  duplicate_code: '코드 중복',
  alias_conflict: '별칭 충돌',
  same_name: '같은 명칭',
  same_alias: '같은 별칭',
  near_name: '유사 명칭',
  no_source: '출처 없음',
  stale: '오래됨',
  low_quality: '품질 미달',
  // ★ 아래 셋은 사전에 없던 값이다. 캡처 게이트가 콘솔 오류로 잡아 냈다(2026-08-04) —
  //   `userTerm` 이 «모르는 값을 조용히 통과시키지 않는다»가 실제로 작동한 결과다.
  //   뜻은 `core/master_data_seed.py` 의 생성 지점에서 확인해 옮겼다.
  cost_exceeds_price: '원가가 판가를 초과(구조적 적자)',
  cpk_unreachable: '공정능력이 목표에 미달(항상 품질 미달)',
  uom_price_scale_suspect: '단위와 단가의 배율 불일치 의심',
};

/** 파이프라인이 최종적으로 무엇을 내놓는가. 내부 값은 영문 슬러그다. */
export const DELIVERABLE_TYPE_KO: Record<string, string> = {
  software_app: '실행 가능한 애플리케이션',
  document_report: '분석·보고서 문서',
  hybrid_simulation: '복합 시뮬레이터(화면 + 보고서)',
};

/** [트랙 E] 제작 단계의 상태. `factory/factoryViewModel.ts` 의 `FactoryStageStatus` 와 1:1 이다.
 *
 * ⚠️ **낱말이 색을 대신한다**(구현 명세 §6: 상태를 색상만으로 표현하지 않는다). 그래서 여기
 *   문구가 비면 색맹인 사용자에게는 모든 칸이 같아진다 — 빈 문자열을 넣지 않는다.
 * ⚠️ «대기» 와 «차단» 을 나눈다. 순서를 기다리는 것과 선행 조건이 막힌 것은 사용자가 해야 할
 *   일이 다르다(앞의 것은 기다리면 되고, 뒤의 것은 무엇이 막혔는지 봐야 한다). */
export const STAGE_STATUS_KO: Record<string, string> = {
  waiting: '대기',
  running: '진행',
  decision_required: '사용자 결정 대기',
  completed: '완료',
  reworking: '재작업',
  failed: '실패',
  blocked: '차단',
  stopped: '중지',
};

export const stageStatusKo = (v: string) => userTerm(STAGE_STATUS_KO, v, '제작 단계 상태');
export const deliverableTypeKo = (v: string) => userTerm(DELIVERABLE_TYPE_KO, v, '산출물 유형');
export const contractStateKo = (v: string) => userTerm(CONTRACT_STATE_KO, v, '계약 상태');
export const severityKo = (v: string) => userTerm(SEVERITY_KO, v, '심각도');
export const dataGradeKo = (v: string) => userTerm(DATA_GRADE_KO, v, '자료 등급');
export const findingKindKo = (v: string) => userTerm(FINDING_KIND_KO, v, '결손 종류');
export const deptRoleKo = (v: string) => userTerm(DEPT_ROLE_KO, v, '부서 역할');
export const orgStatusKo = (v: string) => userTerm(ORG_STATUS_KO, v, '조직 상태');
export const stageKo = (v: string) => userTerm(STAGE_KO, v, '업무표준 단계');
export const standardKindKo = (v: string) => userTerm(STANDARD_KIND_KO, v, '표준 분류');
export const agentKo = (v: string) => userTerm(AGENT_KO, v, '담당 에이전트');
export const recordStatusKo = (v: string) => userTerm(RECORD_STATUS_KO, v, '효력 상태');
export const standardSourceKo = (v: string) => userTerm(STANDARD_SOURCE_KO, v, '표준 출처');
export const checkTypeKo = (v: string) => userTerm(CHECK_TYPE_KO, v, '판정 방식');
