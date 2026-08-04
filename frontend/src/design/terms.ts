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

/** 업무표준 단계 — 파이프라인의 각 관문. 영문 코드는 `criteria.STAGE_RUBRICS` 의 키다. */
export const STAGE_KO: Record<string, string> = {
  RFP: '요구사항 정의',
  PLANNING: '사업 기획',
  PMO: '진행 관리',
  ARCHITECTURE: '시스템 설계',
  TECH_SPEC: '기술 명세',
  CODE_REVIEW: '코드 심사',
  QA: '품질 검증',
  SUPERVISOR: '총괄 감독',
};

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

export const stageKo = (v: string) => userTerm(STAGE_KO, v, '업무표준 단계');
export const standardKindKo = (v: string) => userTerm(STANDARD_KIND_KO, v, '표준 분류');
export const agentKo = (v: string) => userTerm(AGENT_KO, v, '담당 에이전트');
export const recordStatusKo = (v: string) => userTerm(RECORD_STATUS_KO, v, '효력 상태');
export const standardSourceKo = (v: string) => userTerm(STANDARD_SOURCE_KO, v, '표준 출처');
export const checkTypeKo = (v: string) => userTerm(CHECK_TYPE_KO, v, '판정 방식');
