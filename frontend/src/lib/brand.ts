/**
 * 제품 정체성 — **단일 지점.**
 *
 * ## LAXS(랙스)
 *
 * > **AX embedded in LS** — LS 의 일과 경영에 AX 를 내재화한다는 뜻.
 * > 지향점은 **AX at the core of LS** — 현업의 실행과 경영의 판단을 AX 로 연결한다.
 * > (`docs/official/current/internal/01_executive_decision_request.html` §00)
 *
 * LS MnM 에 적용한 첫 번째 시스템은 **LAXS-M(랙스-엠)** 이다. 제품 이름은 `LAXS`,
 * 특정 회사 적용본은 `LAXS-M` 처럼 접미사로 구분한다.
 *
 * ⚠️ 화면마다 이름을 손으로 적지 않는다 — 종전 이름(`AI Factory Studio`)이 상단바·로그인·
 *   탭 제목에 각각 박혀 있어서 한 곳만 바꾸면 화면마다 다른 이름이 보인다.
 */
export const PRODUCT_NAME = 'LAXS';

/** 한글 발음. 처음 보는 사람에게 읽는 법을 알려 준다. */
export const PRODUCT_NAME_KO = '랙스';

/** 이 설치본의 이름. ⚠️ 회사가 정해지면 `LAXS-M` 처럼 접미사가 붙는다. */
export const PRODUCT_EDITION = 'LAXS-M';

/** 상단 셸처럼 자리가 좁은 곳에서 쓰는 제품 역할 설명. 발음 표기는 안내 페이지에서만 한다. */
export const PRODUCT_DESCRIPTOR = '업무·경영 AX 운영체계';

/** AI 비서의 제품 표시명. **한 곳**이다.
 *
 * 현재 사용자 호출명은 `자비스` 다. 기능 설명에서는 «AI 경영비서»라는 역할명을 쓰되,
 * 실제 대화 레일의 고유명은 여기서만 관리한다.
 */
export const ASSISTANT_NAME = '자비스';

/** 별도 한글 음역은 쓰지 않는다. */
export const ASSISTANT_NAME_KO = '';
