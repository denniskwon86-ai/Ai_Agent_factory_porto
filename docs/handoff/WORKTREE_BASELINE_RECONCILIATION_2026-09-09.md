# 2026-09-09 시험·구현 기준선 정리

> **현재 재개점 / Codex / 2026-09-11 17:22 KST:** 선행 FND-01/03·MDM-04/08·EXT-02 **5종 정렬 완료**(1,397행·6 DRAFT/RAW, 기존 55판 보존). 전체 **21/40=52.5%**, 로컬 **18/28=64%**를 사용하며 아래 과거 관리평가는 현황이 아니다. 최신 근거는 [진척 정본](../../PROGRESS.md)과 [선행 5종 체크포인트](FOUNDATION_ALIGNMENT_CHECKPOINT_2026-09-11.md). 데이터 준비 `242df882d`, 결정 생성 계약 `c4f9421fc`로 커밋 분리했고 푸시 직전 격리 회귀 **186+115=301건** 및 타입 검사가 통과했다. 다음 구현은 `readiness.py`·`scope_index.py`·`snapshot_service.py`의 가격·과거 조직 시점 사용 보류 강제다. 선행 5종 재준비·자동 인증·소유권 승인으로 우회하지 않는다. 사용자 요청에 따른 커밋·푸시는 정리 작업이며 진척 가산이 아니다. 이하 기록은 당시 이력으로 보존한다.

> **최신 실행 완료 / Codex / 2026-09-11:** K1-c7j **6종·12그룹·13,900행 새 사본 RAW 적재·독립 대사 완료**. 사본 `logistics-raw-batch-eweopj4t/data_preparation.db`, 결과 지문 `c093c836c4f51c89e12311345e29dbe383361393ffc16eeefb82398804c04e5c`. 핵심 RAW 증적 **4/8→8/8종**, 이번 적재 **6/6종**, 선택한 핵심 **15판·14,160행**. 기존 43개 스냅숏의 23개 열·7개 RAW 보존, 제품의 빈 `certified_by` 열 추가만 격리 사본에서 검증 후 허용. 첫 중단 사본 `logistics-raw-batch-vrito97e`는 적재 0으로 보존. 신규 DRAFT/RAW 각각 12개, 인스턴스 추가 0, 승인/인증/운영 DB 접근 없음. 순수 함수 **154/154**, 상세 [K1-c5 §19](K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md#19-k1-c7j--6종13900행-일괄-raw-적재-완료-2026-09-11-kst). 다음은 선행 **FND-01/03·MDM-04/08·EXT-02 5종 문맥·참조 정렬** 한 묶음이다. 상위 연결 **2/4(50%)**, 과거 관리평가 **45%·로컬 54%**는 별도이며 RAW 완료를 실사용 완료로 표시하지 않는다. 전체 회귀 원장 감시 오류 미해결. 아래 기록은 당시 이력이다.

> **최신 재개점·진척 정정 / Codex / 2026-09-11:** K1-c7i **112행 통합 점검 완료**, 핵심 8종 14,160행 메모리 참조/수량/날짜·AP/GL 대사 통과. 다음은 **PRC-01/02 새 개정+LOG-02~05, 6종·12그룹·13,900행을 새 격리 사본에 일괄 RAW 적재·대사**하는 하나의 실행 묶음이다. 재무 69행의 판매/생산 의존성을 RAW 물류 적재의 선행조건으로 두지 않는다. 원본·기존 사본 보존, 설치·승인·인증 없음. 상세 [K1-c5 §18](K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md#18-k1-c7i--112행-통합실행-묶음-확정과-진척-산정-정정-2026-09-11-kst), `integration-batch-plan.json`, 순수 함수 **120/120**. **45%는 9월 8일의 10영역 관리평가이지 최신 전사 완성률이 아니다. 원표 로컬 합은 16이 아니라 15이므로 15/28(54%)로 정정한다.** 과거 기록은 보존하되 이 정정을 우선한다. 핵심 RAW 증적 4/8종, 다음 적재 0/6종, 상위 연결 2/4. 전체 회귀 원장 감시 오류는 미해결.

> **최신 재개점 / Codex / 2026-09-11:** K1-c7h 사용자 승인 규칙으로 **통관 5+AP 23+GL 46=74행 비설치 금액 후보 생성·전수 대사 완료**. `raw-stage-5rsqiaph/financial-candidate.json`, 지문 `5a01920bff187d69ca9090b4ee9f67bbf42cda0f69c97e12bce824728050a039`. AP/통관을 전표별 HALF_EVEN 0.01로 계산하고 GL 양쪽은 AP와 일치. 금액 74필드·후보 상태 138필드만 변경; 원천 tenant/scope·비금액 업무값·과거 인증 근거 보존, 목표 문맥 설치 아님. 순수 함수 **104/104**, 별도 금액/ID/보존 검증 통과. DB 연결·원본/RAW 수정·승인·인증 없음; 전체 회귀 원장 감시 오류 미해결. [K1-c5 §17](K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md#17-k1-c7h--승인된-후속금액-74행-비설치-후보-2026-09-11-kst)의 **가격 38+후속 74행 통합 문맥·선행자료·사본 적재 순서 점검(5~10분)**으로 재개. 전체 18/40(45%), 로컬 16/28(57%), 상위 2/4 유지. 아래 기록은 당시 이력이다.

> **최신 재개점 / Codex / 2026-09-11:** K1-c7g 가격 영향 읽기 전용 조사 완료. 36발주→23선적/통관→23AP→46GL 연결, 금액 보정 검토 **통관 5+AP 23+GL 46=74행**. 미선적 13행에는 전표 없음. 기존 금액 대사 오류 0이나 AP 2행에서 float 대비 Decimal HALF_EVEN 0.01 차이 발견. 지급/세금 정책은 미검증. 결과 `raw-stage-5rsqiaph/price-impact-review.json`, 순수 함수 **79/79**. DB 접속 전면 금지; 새 금액·설치·인증·승인 없음. [K1-c5 §16](K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md#16-k1-c7g--후속-통관매입회계-금액-영향-조사-2026-09-11-kst)의 **후속 74행 비설치 보정 시연 규칙 선택** 후 재개. 전체 18/40(45%), 로컬 16/28(57%), 상위 2/4 유지. 전체 회귀 원장 감시 오류 미해결. 아래 기록은 당시 이력이다.

> **보고 규칙·산정 정정 / 사용자 요청·Codex 감사 / 2026-09-11:** 이후 중간·완료 보고에 **9월 8일 관리평가 18/40(45%) · 로컬 산식 정정 15/28(54%) · 상위 연결 2/4 · 현재 실행 묶음 실측**을 구분한다. 과거 평가를 최신 제품 전체 완성률로 표시하지 않는다. 이전 16/28(57%) 표기는 합산 오류다. 검증된 영역 종료 조건이 충족되면 증거로 재평가하고 소단계를 중복 가산하지 않는다.

> **최신 재개점 / Codex / 2026-09-11:** K1-c7f 사용자 승인 시연 규칙의 **비설치 가격 후보 2계약+36발주 생성·대사 완료**. 단가 후보 MHP 21,363.34 / 황산 102.67 USD/TON, 가격 외 값·기존 RAW/사본 보존. 98계약/1,764발주는 후보 명세상 가격계산 보류(제품 차단 설치 아님). 결과 `raw-stage-5rsqiaph/price-candidate.json`, 순수 함수 **61/61**, 전체 회귀 원장 감시 오류는 미해결. [K1-c5 §15](K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md#15-k1-c7f--승인된-시연-규칙의-비설치-가격-후보-2026-09-11-kst)에서 **후속 가격 사용처·파생 금액 영향 읽기 전용 점검(5~10분)**으로 재개. 실제 설치/소유권/인증/계산 승인은 하지 않았다.

> **최신 재개점 / Codex / 2026-09-11:** K1-c7e 가격 보정 **방안 검토만 완료**, 수치/RAW/DB 변경 없음. 시점 문제 **100계약/1,800발주 전체**(2026-08-07 공표가격을 이전 발주에 사용), 자재 지표는 96건 미지정·2건 불일치·2건 일치. 권고는 **계약 시작일까지 알려진 가격을 고정하는 미승인 시연 규칙으로 2건·36행의 비설치 후보부터**, 나머지 98건은 RAW 보존·가격계산 보류. [K1-c5 §14](K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md#14-k1-c7e--가격-기준-보정-방안-검토-2026-09-11-kst)의 사용자 정책 선택 후 재개한다. 결과 `raw-stage-5rsqiaph/price-policy-review.json`. DB 접근 전면 금지 순수 함수 **42/42** 통과, 전체 회귀 미재실행·기존 원장 감시 오류 미해결. 자동 적용/인증 가능 판정은 0건이다.

> **최신 재개점 / Codex / 2026-09-11:** K1-c7d RAW 7판·2,160행 품질 점검 완료, **미해결 있음**. 필수 누락/중복/자료형 오류 0이나 가격 통화·수량단위 환산 근거 미확인 **계약 66 / 발주 1,188**, 목표 선행자료 4종 판 0. [K1-c5 §13](K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md#13-k1-c7d--raw-품질-점검과-가격-기준-미해결-2026-09-11-kst) 참조. 결과는 기존 raw-stage-5rsqiaph의 `quality-result.json` 및 `quality-verification-notes.json`. 전체 회귀는 **83 passed + 원장 감시 teardown error 1**로 미통과; 시험 중 원장 149→155, 이후 외부 데이터 연결 이벤트 증가 169 관측, 기록 프로세스 미확정. DB 접근 전면 차단 순수 함수 32/32만 별도 통과. 다음은 **가격 단위·통화·관측시점 보정 방안 검토(5~10분)**, 원문/RAW/승인 상태는 변경 금지. 추가 전체 회귀는 공유 원장과 분리된 실행 환경에서 수행한다.

> **최신 재개점 / Codex / 2026-09-11:** K1-c7c **4종·2,160행 사본 RAW 저장 완료**. 신규 인스턴스 3개·DRAFT 결속 7개·RAW 판 7개, 인증/승인 없음. 전수 왕복·지문·원본/기존 사본 불변성 및 독립 RO 재조회 통과, 회귀 **71/71**. 사본은 `output/kit-logistics-review-2026-09-10/factory-rehearsal-7h8jvgww/raw-stage-5rsqiaph/`, 결과 `raw-result.json`. 다음은 [K1-c5 §12](K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md#12-k1-c7c--사본-raw-적재-완료-2026-09-11-kst)의 **RAW 품질·의존성 읽기 전용 점검(5~10분)**. 사본을 재생성하지 말고 지정된 7개 RAW에서 재개한다. G2-D RAW 단계만 전진했으며 실사용 준비·관문 전체 완료는 아니다.

> **최신 재개점 / Codex / 2026-09-11:** K1-c7b 계약·자재·공급사 360행 비설치 연결 후보 완료. 공급사 25/40이 두 공장에 공통 사용됨을 확인해 MDM-02만 기존 법인 공통 기준정보로 재구성하는 후보를 만들었고 원래 가상 법인 출처를 보존했다(법인 동일성/권한 부여 아님). 새 문맥에서 발주 1,800행과의 한정 대사 0건 불일치, 부정 대조 6/6. 다음은 [K1-c5 §11](K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md#11-k1-c7b--선행자료-360행-새-문맥-연결-후보-2026-09-11)의 **4종·2,160행 사본 RAW 적재만(5~10분)**. 인증·승인·기존판 철회는 금지하고 남은 계약 의존성은 별도 관리한다.

> **최신 재개점 / Codex / 2026-09-11:** K1-c7a PRC-02 1,800행의 비설치 전환 후보 생성. 회사·공장 두 열만 변경, 업무값 보존. 원천 참조 보정 대사는 0건 불일치지만 새 문맥 참조·소유권은 아직 미완이다. 회사가 달라 기존 인증판 교체 API를 사용할 수 없으므로 옛 판 보존+새 문맥 판 생성으로 준비한다. 다음은 [K1-c5 §10](K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md#10-k1-c7a--발주-1종-전환-후보와-선행-조건-2026-09-11)의 **선행 참조 3종·360행 연결 정리(5~10분)**, 공급사 40행의 회사 범위부터 확인. 설치 화면/DB·승인 변경 없음.

> **최신 재개점 / Codex / 2026-09-11:** K1-c6c 기존 일반 사용자 권한 대조 완료. 동일 사본에서 실제 resolve_scope·주체 차단·PDP로 계획 자원 60판정(허용 10/거부 50), 운영 계층 4판정 일치. 계정·권한·설치 변경 없음. **실제 인증 데이터/HTTP 세션 검증은 아니며**, 동제련 직접 역할의 일반 사용자 0건은 잔여다. 다음은 [K1-c5 §9](K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md#9-k1-c6c--기존-일반-사용자-권한-대조-2026-09-11)의 **PRC-02 1종 사본 전환 준비(5~10분)**. 승인/인증을 정책 대조 결과로 대체하지 않는다.

> **최신 재개점 / Codex / 2026-09-11:** K1-c6b 격리 사본 연결 완료. 제품 저장소로 공장 2개·관계 2개만 생성했고 기존 부서·사용자 역할은 유지했다. 설치 DB 두 개의 논리 행 및 회사 설정 전후 동일, 새 ID는 설치본에 0건. 다음은 **2-c 접근 대조만(5~10분)**이다. [K1-c5 §8](K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md#8-k1-c6b--격리-사본의-공장-연결-완료-2026-09-11-kst)의 기존 사본을 사용한다. 전체 완료율은 유지하며 화면 반영·승인·데이터 이관은 아직 하지 않았다.

> **최신 재개점 / Codex / 2026-09-10:** 사용자 요청으로 작업을 5~10분 단위로 분리했다. K1-c6a 공장 2곳 재사용 조사를 완료했으며 설치본 변경은 없다. 동제련 공장 노드는 없고 배터리 기존 공장은 설계 예시로 동일성 근거가 없다. 다음에는 **격리 사본의 공장 연결(2-b)만** 진행하고, 접근 대조(2-c)는 분리한다. [K1-c5 §7 체크포인트](K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md#7-k1-c6a--공장-재사용-조사-체크포인트-2026-09-10)를 따른다.

> **후속 진행 / Codex / 2026-09-10:** 사용자가 기존 부서 기반 연결을 확정했다. K1-c5에서 기존 구매·물류·생산 부서를 유지하는 5종·두 공장·13,800행의 전환 계획을 생성하고 59건 회귀를 통과했다. 사업부와 공장을 같은 범위로 합치지 않는다. **실제 설치 전환은 아직 하지 않았다.** [K1-c5 인계](K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md)의 공장 2곳 격리 리허설부터 재개한다. 같은 방향 승인을 다시 묻지 않는다.

> **후속 진행 / Codex / 2026-09-10:** K1-c4에서 기존 배터리 부서와 업무키트 공장의 tenant/조직 문맥이 다름을 확인했다. 5종·7,138행 결속 초안은 책임 부서·시행일을 비워 두고 결정 대기로 남겼다. 최신 상태는 [K1-c4 인계](K1_C4_OWNERSHIP_CONTEXT_REVIEW_2026-09-10.md). 기존 구매·물류 부서를 활용하는 문맥 정리 방향을 사용자에게 확인한다. 실제 등록·이관·승인은 하지 않았다.

> **후속 진행 / Codex / 2026-09-10:** K1-c3 계약 100건·공급사 40건의 비설치 보정 후보를 완료했다. 기간 밖 발주 261건·공급 자재 밖 발주 1,782건이 후보 대입에서 0이 됐다. 실제 적용·소유권·계산 준비도는 그대로 HOLD. 최신 재개점은 [K1-c3 인계](K1_C3_PROCUREMENT_REFERENCE_CANDIDATE_2026-09-10.md)의 **K1-c4 조직 소유권 후보**다.

> **후속 진행 / Codex / 2026-09-10:** K1-c2 설치 영향 검토를 완료했다. 물류·입고 1,200묶음 일치 효과와 계약 261행·소유권 7,138행·기존 계산판/안건 영향을 확인했다. 설치는 HOLD이며 다음은 PRC-01·MDM-02 비설치 보정 후보다. 최신 재개점은 [K1-c2 인계](K1_C2_LOGISTICS_APPLICATION_IMPACT_2026-09-10.md)를 따른다. 아래 기록은 당시 이력으로 보존한다.

> **후속 진행 / Codex / 2026-09-10:** K1-c1 물류 5종 13,800행 비설치 후보·집중 회귀를 완료했다. 최신 상태와 다음 **K1-c2** 재개점은 [K1-c1 인계](K1_C1_LOGISTICS_REVIEW_CANDIDATE_2026-09-10.md)를 따른다. 아래 K1-c1 착수 전 기록은 당시 이력으로 보존한다. 설치 DB·화면은 변경하지 않았다.

- 작성: Codex / 2026-09-09 00:24 KST
- 사용자 지시: Claude 인계 감사 결과를 전달했으며 다음 단계인 기준선 정리를 진행.
- 시작: `claude/data-acquisition-orchestrator-20260905@d6ccb91dc`.
- 목적: 먼저 커밋된 시험 5개와 미커밋 구현의 분리를 해소한다. 새 기능·업무 데이터 등록·운영 앱 중단은 이번 범위가 아니다.
- 관문: G2 초기자료 정합성·G3 업무 앱 사용성 작업의 재현 가능한 코드 기준점 보존. 관리 단계 점수를 올리는 기능 완료 판정이 아니다.

## 1. 실제로 발생한 공유 색인 경합

Codex가 31개 코드·시험 경로를 명시해 스테이징한 뒤 형식 검사에서 끝의 빈줄 3건을 발견했다. 이를 정리하는 사이 Claude가 **2026-09-09 00:18:36 KST** `bb638ce2f`를 커밋했다. 이 커밋은 F-6 5개 파일뿐 아니라 **Codex가 색인에 올린 31개 전부**를 포함한다(총 36개).

새 파일 6개를 잘못 담았던 이전 사고와 달리 이번 31개는 Codex가 실제로 검증·선택한 구현/시험이다. 그러나 담당별 커밋 귀속은 다시 섞였다. 파일을 명시해 `git add`하는 것만으로는 **공유 색인에 이미 올라간 남의 변경을 일반 commit이 함께 담는 것**을 막을 수 없다. Codex가 공유 폴더의 색인에 변경을 올린 동안 다른 커밋이 실행된 경합도 이번 기록에 포함한다.

이력을 reset/revert/강제 푸시로 재작성하지 않는다. 31개가 검증한 내용과 같은지 독립 대조해 보존하고, 이 문서에서 귀속을 정정한다. `bb638ce2f`의 설명에 남은 “HEAD는 구현 미포함”은 **그 커밋 직전에는 맞지만 그 커밋의 트리에는 맞지 않는다.**

- 31개 중 28개는 HEAD와 작업본이 개행 정규화 후 동일하다.
- 나머지 3개는 마지막 빈줄 1개씩만 다르고 Python AST 지문이 동일하다.
- 전 턴 HEAD에서 실패했던 `test_app_panel_passes_identity_and_uses_business_view`를 **HEAD 파일 내용만** 넣어 재실행하여 통과했다. 전체 clean-checkout 시험을 실행했다는 의미는 아니다.
- 확인 당시 로컬 원격 추적 참조도 `bb638ce2f`였다. Codex는 이번 턴에 fetch/pull/push를 실행하지 않았다. 코드가 계속 미푸시 상태라고 보고하지 않는다.

후속 확인: Claude는 `9d8793c00`에서 이 경합을 인계 문서에 기록했고, 로컬 원격 추적 참조도 해당 커밋까지 전진했다. 그 문서가 인용한 Codex의 “검토만 했으며 Git 상태는 변경하지 않았다”는 **이전 감사 턴**의 설명이다. 이번 턴에는 사용자 진행 지시에 따라 집중 회귀 후 31개를 직접 스테이징했다. 두 시점을 혼동하지 않는다. Claude가 별도 HEAD worktree에서 436건 통과했다고 기록했지만, 이는 Claude의 검증 보고이며 이번 Codex 독립 실측 413건에 합산하지 않는다.

재발 방지: 병렬 개발의 Git 작업은 **작업자별 worktree/index를 분리**하는 것이 원칙이다. 같은 폴더를 계속 쓸 경우 스테이징~커밋 구간을 교대로 점유하고, 커밋 시에도 `git commit --only -- <명시 경로>`로 범위를 한정한다. 커밋 전후 변경 경로와 blob을 검증한다. 다른 세션의 색인을 비우거나 임의 초기화하지 않는다.

## 2. 검증 결과와 한계

| 검사 | 결과 | 범위 |
|---|---|---|
| Python 집중 회귀 | **413/413 통과**, pytest exit 0 | 먼저 커밋된 5개 파일 210건 + 복원된 신규 6개 파일 203건 |
| Node 실제 함수 시험 | **28/28 통과**, exit 0 | 페이지 조회 15 + 릴리스 목록 7 + 롤백 6 |
| TypeScript | exit 0 | `npm exec tsc -- -b` |
| 제품 빌드 | exit 0 | `npm run build`. 기존 대형 청크·정적/동적 import 중복 경고는 남음 |
| 검증 전후 파일 SHA256 | 선택 34개 전부 동일 | 코드 31개 + 기존 인계/계획 3개. 형식 보정 전 비교 |
| 형식 보정 | 끝의 빈줄 3개 제거 | `production_inputs.py`, `release_catalog_audit.py`, `review_failed_releases.py`. 전후 AST 동일 |
| 전체 T3 / 별도 checkout 전체 시험 / 브라우저 | **미실행** | 집중 통과를 통합 완료로 확대하지 않음 |
| 운영 불변식 전체 비교 | 미실행 | 실행 전 capture 없이 사후 불변을 주장하지 않음 |

`pytest.ini`의 `-q`와 실행의 `-q`가 겹쳐 마지막 통과 요약 문장이 생략되었다. pytest 프로세스 종료 코드 0과 실패 없는 진행 출력을 확인하고, 같은 11개 파일의 collect-only 결과로 분모 413을 별도 확인했다. 수집 검사만으로 통과를 판정한 것이 아니다.

| 시험 파일 | 건수 |
|---|---:|
| test_kit_business_view_ui.py | 16 |
| test_kit_production_revision.py | 49 |
| test_kit_quantity_audit.py | 55 |
| test_kit_sample_audit.py | 25 |
| test_kit_sample_revision.py | 46 |
| test_kit_stock_revision.py | 34 |
| test_kit_warehouse_revision.py | 36 |
| test_management_home_ui_contract.py | 99 |
| test_release_catalog_cleanup.py | 14 |
| test_release_readiness.py | 24 |
| test_release_rollback_api.py | 15 |

실행:

```powershell
venv/Scripts/python.exe -m pytest tests/test_kit_sample_audit.py tests/test_kit_sample_revision.py tests/test_kit_business_view_ui.py tests/test_management_home_ui_contract.py tests/test_release_readiness.py tests/test_kit_production_revision.py tests/test_kit_quantity_audit.py tests/test_kit_stock_revision.py tests/test_kit_warehouse_revision.py tests/test_release_catalog_cleanup.py tests/test_release_rollback_api.py -q -x -p no:warnings
# frontend 작업 폴더
node --experimental-vm-modules --test tests/kit-app-paging.test.mjs tests/release-catalog.test.mjs tests/release-rollback.test.mjs
npm exec tsc -- -b
npm run build
```

Python 회귀는 기존 격리 fixture를 사용했다. 정상 앱의 실제 사용 중단·새 인증판 등록·시드 재실행·기준 자료 덮어쓰기는 실행하지 않았다. `starter_kits/`와 `frontend/public/` 추적 파일 변경 0이다. 실행 로그 `data/interaction_log.jsonl`의 기존 추가 10행은 유지하며 커밋에서 제외한다.

## 3. bb638ce2f 안의 Codex 코드 귀속

기능상 세 묶음이지만 시험 5개는 먼저 커밋되어 있었으므로, 대응 구현이 모두 있어야 해당 기준선 결함이 해소된다. 아래 코드 31개가 모두 `bb638ce2f`에 들어갔다. Claude가 직접 작성한 F-6 파일로 오인하지 않는다.

### 업무키트 데이터 검사·후보 13개

- `core/data_preparation/kit_sample_audit.py`
- `core/data_preparation/kit_sample_revision.py`
- `core/data_preparation/kit_production_revision.py`
- `core/data_preparation/kit_quantity_audit.py`
- `core/data_preparation/kit_stock_revision.py`
- `core/data_preparation/production_inputs.py`
- `scripts/generate_sample_company_starter_kit.py`
- `scripts/plan_business_kit_initial_revision.py`
- `scripts/validate_sample_company_starter_kit.py`
- `tests/test_kit_production_revision.py`
- `tests/test_kit_quantity_audit.py`
- `tests/test_kit_stock_revision.py`
- `tests/test_kit_warehouse_revision.py`

### 릴리스·롤백 14개

- `api/routes/readiness_control.py`
- `core/release_readiness.py`
- `core/release_catalog_audit.py`
- `frontend/src/components/BuildPage.tsx`
- `frontend/src/components/WorkspacePanel.tsx`
- `frontend/src/lib/workspaceApi.ts`
- `frontend/src/lib/releaseCatalog.ts`
- `frontend/src/lib/releaseRollback.ts`
- `frontend/tests/release-catalog.test.mjs`
- `frontend/tests/release-rollback.test.mjs`
- `scripts/review_failed_releases.py`
- `scripts/verify_disabled_releases.py`
- `tests/test_release_catalog_cleanup.py`
- `tests/test_release_rollback_api.py`

### 페이지 조회 4개

- `frontend/src/components/KitAppPanel.tsx`
- `frontend/src/lib/kitAppViewApi.ts`
- `frontend/src/lib/kitAppPaging.ts`
- `frontend/tests/kit-app-paging.test.mjs`

## 4. 문서와 기존 기록 정정

- `BUSINESS_KIT_INITIAL_DATA_EXECUTION_2026-09-08.md`: 창고·재고·다중 생산투입 후보의 기존 상세 기록을 보존한다. 후보는 **REVIEW_ONLY / FAIL**이며 설치 완료가 아니다.
- `RELEASE_CATALOG_CLEANUP_2026-09-08.md`: 릴리스 정리·롤백·페이지 조회 및 K1-b 4종 대사까지의 기존 기록을 보존한다.
- `EXTERNAL_ACQUISITION_UI_REFRESH_PLAN_2026-09-08.md`: Claude가 지적한 미추적 계획을 이 정리의 문서 범위에 포함한다. 계획 커밋이 UI 구현 완료라는 뜻은 아니다.
- 09-08 기준선 문서의 “푸시 없음”은 작성 당시 상태다. `aecdf1d85`·`b2e1b5f17`은 현재 원격 추적 참조의 조상임을 확인했다. 이 문서가 최신 정정 기록이다. 읽기 전용 관리 대상인 `.agents/TEAM_BOARD.md`의 과거 원문은 이번에 수정하지 않는다.
- Claude의 새 F-6 구현·시험·F0 탐침·인계 수정은 손대지 않는다. 그 변경은 이번 413건 회귀의 완료 판정 대상이 아니다. 별도 감사 없이 F-6 인수 완료로 바꾸지 않는다.

## 5. 재개 지점

1. **다음 Codex 작업: K1-c1**. 발주·선적·운송 사건·통관·입고 운송 5종의 비설치 보정 후보와 참조·날짜 회귀 5~6건. 예상 15~20분. 원본/설치 DB는 바꾸지 않는다.
2. 이어 K1-c2는 계약·입고·조직·기존 계산/봉인 영향 확인이며, 추가 의존 발견 시 범위를 재산정한다.
3. Claude F-6 보정은 별도 교차검토 후 UI 연결한다. 승인·탄력도를 임의 생성하지 않는다.
4. R3 실제 롤백 브라우저 확인과 K1-a 실제 페이지 버튼 확인은 여전히 미확인이다.
5. 다음 일일 T3는 변경 커밋을 고정한 별도 검증 worktree 또는 양쪽 담당자의 실제 동결이 필요하다. 같은 폴더에서 한 사람만 멈춰 놓고 “동결”이라고 부르지 않는다.

전체 관리 단계 **18/40=45%**, 로컬 우선 범위 **16/28=57%**, 업무키트 사전 점검 **2/7앱** 유지. 이번 성과는 시험/구현의 Git 누락 복구이지 데이터 정합성 문제나 브라우저 사용 검증 완료가 아니다.

## 6. 세션 마감·최신 재개 안내 — 2026-09-09 00:30 KST

작성: Codex. 사용자 지시: Claude의 세션 인계를 확인하고 인수인계 작성·커밋·푸시. 이번 마감은 문서만 변경한다. 새 업무 데이터 후보 생성, 운영 자료 변경, 원천 호출, 승격 실행 및 T3 실행은 하지 않는다.

### 6.1 현재 Git 사실과 정정

- `bb638ce2f`: Codex 코드·시험 31개와 Claude F-6 파일 5개가 함께 들어간 커밋. §1~3의 귀속·검증 기록을 따른다. 되돌리거나 재작성하지 않는다.
- `1194dccd7`: Codex 인계/계획 4개와 Python 파일 끝 빈줄 3개 정리. 이전 보고 당시에는 로컬뿐이었지만 이후 Claude의 푸시에 포함되었다.
- `e38d95993`: Claude 세션 인계와 수집기 주 인계 업데이트. 이번 시작 시 HEAD와 실제 `git ls-remote` 결과가 모두 `e38d9599306062892e35936af854233e6f2462bb`였다.
- 따라서 전달된 보고의 “Codex 기준선 문서 등 미커밋”은 현재 상태와 다르다. **시험·구현 기준선 정리는 완료됐고 해당 문서도 이미 원격에 있다.**
- 이번 시작 시 미커밋은 `data/interaction_log.jsonl` 추가 10행뿐이다. 실행 로그는 삭제하지 않고 보존하며 문서 커밋·푸시 범위에서 제외한다. 깨끗한 작업 트리라고 보고하지 않는다.
- 이번 새 커밋은 본 문서와 Claude 세션 인계의 최신 상태 안내만 포함한다. 푸시 대상은 기존 `origin/claude/data-acquisition-orchestrator-20260905` 하나이며 `dev`·`main`·태그는 변경하지 않는다.

### 6.2 인계 자료와 검증 판정

| 자료 | 재개 시 용도 |
|---|---|
| [본 문서 §1~3](WORKTREE_BASELINE_RECONCILIATION_2026-09-09.md) | 코드 31개 귀속, 413건·28건 검증 명세, 지문과 검증 한계 |
| [Claude 세션 인계](SESSION_2026-09-09_VERIFICATION_AND_PROMOTION.md) | 수집기·추천기·F-0/F-3/F-4/F-6/F-7 진행과 미확인 사항 |
| [수집기 주 인계](DATA_ACQUISITION_ORCHESTRATOR_V0_1_2026-09-05.md) | Provider 5종, 승격 API, 원천·계약·갱신 규칙 |
| [릴리스·업무키트 인계 §14](RELEASE_CATALOG_CLEANUP_2026-09-08.md) | K1-b 설치본 4종 대사와 K1-c1 보정 후보 설계 |
| [업무키트 초기자료 인계](BUSINESS_KIT_INITIAL_DATA_EXECUTION_2026-09-08.md) | 재고·생산·수량/단위 후보 및 남은 의존 관계 |
| [공개자료 UI·갱신 계획](EXTERNAL_ACQUISITION_UI_REFRESH_PLAN_2026-09-08.md) | 1회 확보·정기 추가·변경 갱신, 과거 정정과 적용본 보존 |

Codex 독립 검증은 **Python 413건·Node 28건·타입 검사·제품 빌드 통과**다. Claude가 기록한 HEAD worktree 436건은 별도 주체의 검증이며 합산하지 않는다. T3 6,445 기록은 최신 커밋의 통합 통과 증거가 아니며, 수집기 주 인계에는 실패 후 전체 재실행 미실시도 적혀 있다. **최신 통합 T3·실제 원천 수집·브라우저 확인은 미완**으로 유지한다. 이번 문서 마감으로 해당 상태를 바꾸지 않는다.

### 6.3 다음 작업을 작은 단위로 재개한다

1. **Codex K1-c1: 비설치 물류 보정 후보 — 15~20분 예상.** `PRC-02`, `LOG-02`, `LOG-03`, `LOG-04`, `LOG-05` 5종을 full 원본의 공통 시간축으로 묶어 후보를 만든다. 부모 일부 누락·부모만 +84일 이동·중복 부모키·다른 tenant의 같은 ID·날짜 누락과 정상 대조군을 집중 회귀 5~6건으로 구분한다. 설치 DB·기존 인증판은 변경하지 않는다. 검사 보고와 미해결 의존성을 남기는 곳에서 한 번 끊는다.
2. **Codex K1-c2: 적용 영향·복구 단위 확정 — 15~20분 예상.** 계약 기간·조직/소유권·입고 연결·기존 계산 4종과 봉인 영향을 확인한다. 추가 의존이 나오면 시간을 재산정하고, 기존 판 덮어쓰기를 자동 실행하지 않는다.
3. **공동 통합 확인:** 검사 대상 SHA를 고정한 별도 검증 worktree 또는 공동 동결 후 일일 T3를 실행한다. 한 담당자가 멈춘 것만으로 공유 트리 동결을 선언하지 않는다. 다음 적용·릴리스의 통합 완료 주장은 이 검증 뒤에 한다.
4. **Claude/도메인 담당:** F-6 보정 교차검토와 탄력도 정의, F-3의 인증 공통 자료→앱 계약 합의, 원천 사용 결정과 실제 소량 수집 확인. Codex가 승인이나 탄력도 값을 임의로 채우지 않는다. 사람 판단만 남았다고 확정하지 않는다.
5. **사용자 화면 확인:** R3 운영에서 내리기, K1-a 업무키트 페이지 이동, 보정된 승격·전달 화면과 갱신 정책을 차례로 확인한다. 함수/API 시험을 브라우저 검증으로 계산하지 않는다. 내부 ID 입력 강요, 업로드 범위 임의 추가, `.invalid` 일괄 제외는 하지 않는다.

예상 시간은 각 작은 작업의 준비 추정이며 완료 약속이 아니다. 환경 복구나 새 결함으로 범위가 늘면 중간 결과와 재개 지점을 먼저 남긴다.

### 6.4 전체 진척과 종료 경계

```text
전체 관리 단계  █████████░░░░░░░░░░░ 45% · 18/40
로컬 우선 범위  ███████████░░░░░░░░░ 57% · 16/28
업무키트 사전 점검                    2/7 앱
```

이는 기존 관리 단계 집계이며 최종 제품 수용 시험 통과율이 아니다. G2 초기자료 정합성·G3 업무 앱 사용성의 재현 가능한 코드 기준선은 보존했지만, 문서 마감만으로 기능 관문을 추가 통과하지 않았으므로 수치는 유지한다. 재개 시 새 세션은 Git 상태와 대상 데이터 지문부터 다시 확인한다.

## 부록: 집중 회귀 전 코드 지문

Git 개행 정규화 전 디스크 SHA256이다. 회귀 후에도 전부 같았고, 이후 위의 세 파일 끝줄만 보정했다.

| 경로 | SHA256 |
|---|---|
| `core/data_preparation/kit_sample_audit.py` | `5ba38883cd1273a0b6f8d5168bacabd7a234332247a8d980fc4f26486d2641ee` |
| `core/data_preparation/kit_sample_revision.py` | `1cc7f6fda66bdda53d3cfb7f3c8e7e749347a2815eedfb37f7bcf90f38a6d1f0` |
| `core/data_preparation/kit_production_revision.py` | `e03c16da0fba437c01bbb0737a69617b5f2c6dd1116f9a273738edb93281b641` |
| `core/data_preparation/kit_quantity_audit.py` | `a1c3552ca647a46adcbfd4ce77e6033fb2536023254ebbed5dd7580ff49cd22a` |
| `core/data_preparation/kit_stock_revision.py` | `5dbf683de1a487ce1bff71c42baf27f27c629d652e0923afe11e14a551bdd94f` |
| `core/data_preparation/production_inputs.py` | `a3115d07a40047814cb9af220c61d1c7c2ef53a16c5d30e3562fb2257de81726` |
| `scripts/generate_sample_company_starter_kit.py` | `2939afa8d63ea4439e75dfa0a20a717a00d5c66fbbd54d9ea9c9b21e93c902b5` |
| `scripts/plan_business_kit_initial_revision.py` | `f40585a08546207429243163144b3aabc747bc6c62e70abd06e9e96b581bca8d` |
| `scripts/validate_sample_company_starter_kit.py` | `82591fcd4058be171991ec20b8f59981643ac40f6c09022a7fb54275705f84f7` |
| `tests/test_kit_production_revision.py` | `338c4f16cacc51905c80e802bf3eeb9aaee8b64ca5532a6569f1b0b05c8ba55e` |
| `tests/test_kit_quantity_audit.py` | `2ff0c01a58e34c39758241ab1cb86236ff5edf852b511dfb1d5ae4a8c86096c7` |
| `tests/test_kit_stock_revision.py` | `2e9df5ae3970517404ca6aa2148f4ea70ee04afadbff9415cdf4baea11e39a59` |
| `tests/test_kit_warehouse_revision.py` | `35c6f6b7bc902f00f923622aef1e803f50429fa5c9a66448f5913c6f6dd6671f` |
| `api/routes/readiness_control.py` | `2e0af1b9acf8dc79c6144ff2c0b7dd96b37885d1fa2148657fd9174eecd3a118` |
| `core/release_readiness.py` | `70ac4330f359b23f59c47a57dbcf4784c241bb37d1ba48a1675e8cbbbe34aa8a` |
| `core/release_catalog_audit.py` | `e138cb2041020b69d980d82572c75fe87b39b5f042fafd9ea27337da4013f06f` |
| `frontend/src/components/BuildPage.tsx` | `e4643e4c15bd79048d81ba3b4f15668242f6b6939cbced81fe48f32f534799a3` |
| `frontend/src/components/WorkspacePanel.tsx` | `210f10127d9a99a8bfc4e9cd673eb859c6f7379fa901604df604b067bbc3229a` |
| `frontend/src/lib/workspaceApi.ts` | `557fa6bccd731d534de71f63950a9c3b5927d69f5ec9c192a3f81757f0603722` |
| `frontend/src/lib/releaseCatalog.ts` | `e9cf9eae5a95cd6941e79cdf7f06267388fcc4c5b46e612bed336152ceb4dea3` |
| `frontend/src/lib/releaseRollback.ts` | `5b346c7c50946db4f402686d2ae9b5fe30cb0adf81c3a94c1e57b8e61b3b2bd3` |
| `frontend/tests/release-catalog.test.mjs` | `d2b62a1910027eb7f428f5f6f5614be0673da61fcd9d754a2d6032328251fd40` |
| `frontend/tests/release-rollback.test.mjs` | `6481c0102145b2d741c057ff88160b6aa9a397f62b5dfd8b6361d6da4f539ee0` |
| `scripts/review_failed_releases.py` | `d1a50bb67e41a748830f70a10341623a5254329e42d4dd758b762aca891fa2c4` |
| `scripts/verify_disabled_releases.py` | `3dde5880cb18f609d985db4d650e614d8f69254b0e90d9c48bae50c2d820bc6e` |
| `tests/test_release_catalog_cleanup.py` | `29f4a25208544e3bbc38d4ba0d6364c6095573779574bf970e51127d11ddddff` |
| `tests/test_release_rollback_api.py` | `d4eb5bac0d35b388dafcade724181b2fa66723b8d38ab61d279073faa97092b5` |
| `frontend/src/components/KitAppPanel.tsx` | `1611a46be04c5c5fde967935c28f5f35deedcaf4155e09aca7c17bab9f45c58c` |
| `frontend/src/lib/kitAppViewApi.ts` | `4ccc29781c6fa5c8831b37b403ba67d53e4365b18284594d184d37fe433514b4` |
| `frontend/src/lib/kitAppPaging.ts` | `a8c32ee479143b0e53f8d43b429efd41bf0ec5879ce023bcd2655ca312858300` |
| `frontend/tests/kit-app-paging.test.mjs` | `0b8200aa4c004ccdbcb65630ac43429f8441d3be6bfaaa5e25fbd6c3bb3e0eb6` |
