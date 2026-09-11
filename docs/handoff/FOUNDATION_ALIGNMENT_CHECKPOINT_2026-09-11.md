# 초기 선행 5종 정렬·RAW 사본 검증

- 작성자 / 기준 시각: Codex / 2026-09-11 17:07 KST
- 로드맵: 권고 작업 5·6, G2-D 원천 프로파일링·스냅샷·매핑·대사. 구매→물류 첫 수직 폐루프의 누락 선행자료를 준비한다.
- 결과: **선행 5종 정렬 묶음 완료, 1,397행·6개 DRAFT 결속/RAW 판 저장·재조회**. 소유권·인증·설치·계산 승인이 아니다.
- 전체: **21/40=52.5%, 로컬 18/28=64% 유지**. D04의 선행자료 공백은 해소했지만 가격/시점 보류 강제와 소유권·인증이 남아 D04 연결 단계는 진행/부분이다.
- 기계 검산: [10영역 판정·이번 증적](C:/WorkSpace/gemini_agent_team_verG/docs/handoff/FOUNDATION_ALIGNMENT_CHECKPOINT_2026-09-11.json).

## 무엇을 준비했는가

| 자료 | 원천 | 새 목표 문맥 후보 | 보존·보류 |
|---|---:|---:|---|
| FND-01 조직 | 15행 | 6행 | 원천 15행은 원문 그대로 보존. 새 후보는 사본 ECM의 그룹·회사·사업부 2·공장 2 구조 투영 |
| FND-03 달력·환산 | 1,101행 | 1,101행 | 날짜·환산값·단위 불변. 환율 선택/가격 보정에 적용하지 않음 |
| MDM-04 창고 | 8행 | 7행 | 검토된 두 공장의 site_id와 scope를 함께 연결. LOC-P3-SIM 1행은 원문째 별도 보류 |
| MDM-08 거래조건 | 43행 | 43행 | Incoterm·결제조건·항만·운송구간 업무값 불변 |
| EXT-02 가격 | 240행 | 240행 | 가격·통화·단위·관측일·공표일·vintage·출처 불변. 신규 외부 수집 아님 |

FND-01은 원천 15행을 억지로 6행에 합친 것이 아니다. 기존 조직 사본의 현재 구조를 별도 후보로 투영했다. 원천 법인 별칭/병합, 조직/권한 변경, 과거 날짜 소급 입력이 없다. 목표 조직 엔터티 문맥은 REAL이지만 후보 자료는 SYNTHETIC/UNVERIFIED_CANDIDATE다. 알고 있지 않은 effective_from/effective_to는 모두 빈 값으로 두었고 과거 유효성이 확인됐다고 하지 않는다.

## 실제 실행·검증

- 최종 사본: output/kit-logistics-review-2026-09-10/factory-rehearsal-7h8jvgww/**foundation-raw-0yag5clt**/data_preparation.db.
- 결과: [foundation-result.json](C:/WorkSpace/gemini_agent_team_verG/output/kit-logistics-review-2026-09-10/factory-rehearsal-7h8jvgww/foundation-raw-0yag5clt/foundation-result.json).
- 결과 지문: 3c0159d18b63b2b2a4abe2aa25445ba5a48d693cba913690834f3f9c57838800.
- 부모: logistics-raw-batch-eweopj4t의 55판. 기존 모든 테이블 행·스키마 보존; 새 인스턴스 0, 기존 3인스턴스 재사용, 새 결속 6/판 6만 추가. 전체 DB는 **61판**, 선택한 핵심+선행은 **13종·21판·15,557행**으로 구분한다.
- 1,397행의 실제 RAW 파일을 다시 읽어 바이트/체크섬/행수/필드값/DB 메타데이터 대사. 모두 RAW·DEMO/SYNTHETIC, 결속 DRAFT, 인증일/인증자 빈 값.
- 선택된 기존 핵심 8종 14,160행과 함께 계약 의존 13종이 모두 존재함을 확인. 구조 참조 오류 0; 운송→창고 2,400, 발주→달력 1,800, Incoterm 100, 결제조건 100, 가격코드 100건 대사.
- 등록 키트·manifest·계약 파일·원문·부모 증적과 실행 구현을 지문으로 고정하고 전후 불변 확인. 이전 원문/판 삭제·철회·재작성 없음.
- 신규 정렬/차단 시험 **32건** + 기존 RAW/가격/물류 **154건** = **186 passed, 실패 0, SKIP 0**. [JUnit](C:/WorkSpace/gemini_agent_team_verG/output/foundation-tests-9zzw6490/tests.xml), [테스트 격리](C:/WorkSpace/gemini_agent_team_verG/output/foundation-tests-9zzw6490/test-isolation.json).
- 별도 RO 검산 프로그램으로 기존 55판·신규 6판·전체 테이블 증분·1,397행을 재확인했다. [독립 프로그램 검산 결과](C:/WorkSpace/gemini_agent_team_verG/output/kit-logistics-review-2026-09-10/factory-rehearsal-7h8jvgww/foundation-raw-0yag5clt/independent-verification.json). 이는 타 팀원의 교차검토를 뜻하지 않는다.
- 최초 성공 실행 foundation-raw-5rdfga4a 및 최초 회귀 출력도 보존했다. 최종 실행은 등록 키트/계약 파일 해시 확인을 추가한 새 사본이다.

## 구현과 재현

- core/data_preparation/kit_foundation_alignment.py: 순수 정렬·조직 조상/기간/회사 경계·창고·달력·조건·가격코드 검사.
- scripts/stage_kit_foundation_batch.py: 새 SQLite 사본 하나만 쓰기 허용, 5종/6판 일괄 적재와 13종 대사.
- scripts/verify_kit_foundation_artifact.py: 결과/부모 사본의 정확한 RO URI만 허용하는 별도 검산.
- scripts/verify_kit_foundation_tests.py: 전역 conftest·자동 플러그인·모든 SQLite 연결을 차단한 집중 회귀.
- tests/test_kit_foundation_alignment.py: 원문 불변, 미매핑 행 보존, 소급 유효기간 금지, 회사/부모/시점/중복/참조 실패 대조군.

저장소 루트에서 venv/Scripts/python.exe scripts/verify_kit_foundation_tests.py를 실행한다. 새 사본 생성은 scripts/stage_kit_foundation_batch.py, 별도 검산은 scripts/verify_kit_foundation_artifact.py <새 foundation-result.json 경로>다. 검산 결과는 exclusive-create로 보존하므로 같은 출력 파일을 덮어쓰지 않는다.

## 남은 경계·다음 실행

1. 가격/환산/관측 vintage와 과거 조직 유효성의 보류를 실제 소비 경계에 연결한다. 다음 검토 위치는 core/data_preparation/readiness.py·scope_index.py·snapshot_service.py. 보류 메모가 들어갔다는 이유로 강제가 설치됐다고 하지 않는다.
2. 현재는 RAW/DRAFT이므로 승인된 입력이 아니다. 소유권·인증·계산 승인은 사용자/정식 권한 경계에서 별도 진행한다. EXT-02를 실제 외부자료 인증으로 승격하지 않는다.
3. 실제 사용자/앱/계산/전체 T3 검증은 이번 범위 밖이다. 이전 전체 회귀 원장 문제와 D07 실사용 검증도 별도 유지한다.

운영 DB 연결·원장 수정·기존 RAW 변경·회사 설정 전환·인증자 소급·외부 수집/발송은 없었다. 커밋·스테이징·푸시·병합·배포를 하지 않았다. 다른 작업자의 변경은 보존했다.
