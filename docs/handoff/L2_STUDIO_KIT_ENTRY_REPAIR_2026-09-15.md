# 업무 앱 진입 결함 수정 및 다음 작업 인계

> 후속 2026-09-15 22:30 KST: 다음 작업이던 R3도 수정했다. 현재 재개 지점은
> [릴리스 수정 인계](L2_STUDIO_RELEASE_REPAIR_2026-09-15.md)의 mega 연결이다.
> 아래 R3 미완료 표기는 이 문서 작성 당시의 이력이다.

작성: Codex · 2026-09-15 22:16 KST. 검토자: Erdos(독립 읽기 전용).
사용자 진행 승인에 따른 첫20~30분 묶음. 권고10 / G3.
기준 HEAD: 2380143ea9552bbfbe1cf59678f54a5fb53666b5.
브랜치: codex/l2-unified-studio-20260912. 이번 수정은 아직 미커밋이며 push하지 않았다.

## 1. 완료와 범위

- R1: v2 업무 앱 진입에서 기존 목록의 문맥·가시성 검사를 빠뜨린 경로를 수정.
- R2: legacy 권한 거절403과 없는 인스턴스404가 존재 여부를 구별하던 응답을 같은404/같은 문구로 통일.
- 추가: 요청 시작/응답 직전 모두 최신 대상 권한 및 선택 조직 권한 확인.
- 명시 문맥 누락422, 판독 장애503은 유지. 조회 가능은 생성·실행·게시 승인이 아니다.
- v2 읽기 전용 사용자 허용, legacy PROJECT_RUN 요구 및 unrestricted 목록 정책을 보존.
- 준비도·계약·릴리스 평가를 추가하지 않는다. 공통 reader 추출·프런트 제품 변경 없음.

변경 소스는 api/routes/data_preparation_control.py의 app_entry_metadata와
tests/test_b6_kit_app_entry.py만이다. 다른 제품 파일이나 기존 시험의 판정을 완화하지 않았다.

## 2. 구현 지점과 주의

app_entry_metadata의 내부 visible_entry를 조회 전후 호출한다.

1. OrgDirectory.resolve_scope(fresh=True)로 새 Principal.scope를 만든다.
2. requested_scope_node_id가 있으면 최신 readable_scope_nodes 또는 unrestricted를 확인한다.
3. 기존 _instance_or_404와 binding_for_instance를 호출한다.
4. v2 연결이면 _kit_review_context + kit_app_contract._visible_v2_instance로 기존 목록의 가시성을 재사용한다.
5. legacy면 기존 PROJECT_RUN과 _ctx를 유지한다.
6. 권한/부재403·404는 모두 현재 문맥에서 업무 앱을 찾을 수 없습니다.로 정규화한다.
7. 프로필/앱을 읽은 뒤 같은 검사로 재확인한다. 읽는 도중 인스턴스·결속·문맥이 달라지면503으로 재확인을 요구한다.

fresh=True는 copy.copy로 캐시 없는 객체를 만들 뿐 공유 캐시 자체를 갱신하지 않는다.
따라서 fresh Principal만 만들고 _ctx의 선택 조직 캐시를 믿으면 안 된다.
현재 guard는 기존 project entry의 선택 조직 재확인 규칙과 같다.
분산 DB의 완전한 원자적 읽기나 실제 실행 권한 보장을 주장하지 않는다.

## 3. 검증 및 실패 이력

| 시점 | 결과 | 증거(output 하위, Git ignored) |
|---|---|---|
| 기존 기준선 | 17PASS | usage-holds-510r6xpd/isolation.json |
| R1/R2 부정 검사 추가, 제품 수정 전 | 19PASS / 5FAIL | usage-holds-30y86x6x/isolation.json |
| 첫 제품 수정 후 | 24PASS | usage-holds-6s9bquwa/isolation.json |
| 선택 조직 회수 검사, 추가 guard 전 | 2FAIL(200 노출) | usage-holds-0zgsl4uj/isolation.json |
| guard 후 집중 검사 | 5PASS(기존 실패 분리 포함) | usage-holds-g4_2dp3n/isolation.json |
| 중간 통합 | 158PASS/2FAIL, 이어서160PASS/2FAIL | usage-holds-djo7wmze, usage-holds-92smisie |
| 시험 오염 제거 후 동일 순서 최종 | 162PASS / 0FAIL, pytest126.80초, wrapper132.89초 | usage-holds-9tkg_md0/isolation.json |
| 프런트 업무 앱/프로젝트/주소 계약 | 14+26+25=65PASS | 아래 명령 exit0 |

중간 통합 실패 원인: 내가 추가한 장애 주입 시험이 singleton의 resolve_scope를 인스턴스 수준에서
monkeypatch했다. 복구 시 원본 객체에 결속된 bound method가 인스턴스 속성으로 남아 copy.copy의
fresh가 공유 캐시를 읽게 됐다. 기존 프로젝트의 직접SQL 권한 이동, B2 설치 권한 회수 검사에서 드러났다.
제품의 기존 두 경로를 수정하거나 시험을 약화하지 않고, OrgDirectory 클래스 수준의 self를 보존하는
대역을 monkeypatch.context 안에서 사용하도록 수정했다. 종료 후 클래스 함수 동일성과
singleton.__dict__의 resolve_scope 부재도 검증한다. 전체 동일 순서162PASS가 종결 증거다.

최종 업무 앱 시험은17→31건(+14). 조직 불일치·legacy 허용/거절·문맥 누락·읽기 전용 사용자·
조회 중 사용자 회수·선택 조직만 회수·판독 장애·정상 조회 데이터 불변·준비도/계약 미호출을 포함한다.
격리 결과: sources_unchanged=true, protected_assets_unchanged=true,
blocked_file_writes=[], blocked_sqlite_paths=[], repository_conftest_loaded=false.

재실행(저장소 루트 PowerShell, 운영 DB로 직접 pytest 실행 금지):

    venv/Scripts/python.exe -B scripts/verify_data_usage_holds.py --strict-writes --target tests/test_b6_kit_app_entry.py --target tests/test_b6_project_entry.py --target tests/test_b6_revision_reads.py --target tests/test_b2_installation.py --target tests/test_b2_installation_api.py --target tests/test_b3_execution_context.py --target tests/test_b5_hotl_submission_api.py
    node frontend/scripts/check-kit-app-entry.mjs
    node frontend/scripts/check-project-entry.mjs
    node frontend/scripts/check-studio-location.mjs

프런트 검사는 메모리/모의통신·정적 계약이다. 이번 턴 실제 브라우저·서버 기동·제품 build는 NOT_RUN.
build는 이전 동기화 검토 때 통과했고 이번에는 프런트 소스가 바뀌지 않았다.
Erdos는 수정 전 선택 조직 캐시와 시험 격리 P2를 지적했고 최종 diff에서 둘 모두 정적 종결,
추가 P1/P2 없음으로 판정했다. 실행 결과는 Codex가 위162건으로 별도 확인했다.

## 4. 진척 및 다음 작업

- 전체21/40=52.5%, 로컬18/28≈64.3% 유지. 과거 관리평가 분모로 재계산하지 않는다.
- G3의 기존 진입 기능 결함을 닫았지만 새 관문 완료 항목을 추가하지 않았다.
- B6 전체, Gate5, 실제 사용자 수용 완료로 가산하지 않는다.
- 다음20~30분: R3 release 요청 수명 수정. frontend/src/store/useFactoryStore.ts의
  viewRelease/closeRelease가 시작점. 요청 세대 또는 동등한 무효화로 닫은 뒤 늦은 응답 재등장,
  A→B 역순응답 덮기, 새 요청 중 이전 값 표시, 회사/사용자 전환 중 응답 수용을 막는다.
- 실제 store 동작의 시간순 검사를 먼저 만들고 기존 오류/재시도 표시를 보존한다.
  단순 소스 문자열 배선 검사만으로 완료 판정하지 않는다.
- 그 다음 mega 부모-자식 확인 및 draft 선택 문맥 진입. 상세 선택지는 기존 동기화 검토 §6 참고.
- kit_app releaseId 미소비, Gate5 글자 크기·실제 LLM/전체 히스토리 수용은 여전히 잔여다.

## 5. 보존과 전달 상태

- 사용자 data/interaction_log.jsonl은 기존 미커밋 변경이므로 수정·커밋 대상에서 제외한다.
  SHA256: 7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510.
- data_sync/session-data-20260913.zip은 변경 없음.
  SHA256: 9c60dccd210974fecc7a65f3945d2617371d416cb12a01153fa80d411977ab34.
- 운영 DB·RAW·키·암호문·데이터 복원·원격 Git 변경 없음. 테스트는 격리 폴더에서 수행.
- 이번 미커밋 코드/문서는 다른 PC에서 pull해도 아직 받지 못한다. 별도 커밋·push 요청이 있을 때
  관련 파일만 명시적으로 stage하고 사용자 로그를 섞지 않는다.
