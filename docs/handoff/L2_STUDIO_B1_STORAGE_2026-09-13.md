# L2/통합 Studio B1 — ECM v2 안전 저장 인계

- 작성/최종 갱신: Codex / 2026-09-13 01:43 KST.
- 상태: **B1 지정 안전 저장 출구 완료**. v2 읽기/쓰기·CAS·문맥·구 writer 보호를 구현하고 최종550회귀 및 독립 정적 재확인을 완료했다. B2 팩/설치·명시 이관과 L2 UI는 미완료다.
- 기준: 승인 실행 설계 revision2.1 §11 B1. 제품 헌장/최종 로드맵 권고4·7·10, G2-A/B/C → G3-B/C의 입력 기반.
- 전체 진척: **21/40=52.5%, 로컬18/28≈64% 유지**. 하위 안전성 시험을 제품 점수로 더하지 않는다.
- 브랜치 `codex/l2-unified-studio-20260912`, 시작 HEAD `58e666833`. B0와 이번 B1 변경은 로컬 미커밋·미푸시다.

## 실제 구현

1. `enterprise_profiles`에 context_root_id/entity_mode/configuration_id를 추가하는 멱등 DDL. 기존 행은 빈 문맥을 유지하며 회사·실제/가상을 추정하지 않는다. 업무 내용은 payload 한 곳에만 저장한다.
2. 같은 ECM DB의 `enterprise_process_heads/changes/outbox`. 문맥 유일키는 tenant/root/mode/scope/kind. 초안 작성 시 configuration ID를 예약하되 head_version=0은 공식 지도가 아니다.
3. Strict v2 문서와 L1/L2 정본·배치 ID 분리. ADD_NODE/RENAME/MOVE_NODE/SET_USAGE/ADD_SHORTCUT/REMOVE_SHORTCUT만 검증하여 적용한다. 일반 payload PATCH, 알 수 없는 명령/필드, L3/부모 오류, 정본 중복은 거절한다.
4. `process_config.read/propose/edit/publish`를 기존 admin_capability 등록부에 추가. viewer=read, member=read/propose, manager=네 권한이며 실제 대상 범위도 별도 검사한다. 관리자도 요청 tenant/root/mode/scope 검사를 우회하지 못한다. 활성 사용자·fresh 조직 권한을 매번 확인하고 비강제 bootstrap을 거절한다. 현재 B1은 모든 승인을 작성자와 다른 적격 승인자에게 요구한다.
5. 승인/반려는 BEGIN IMMEDIATE 안에서 현재 권한, head, 초안 지문, 기준 profile ID를 재검사한다. 승인판·head CAS·변경 상태·감사 outbox를 함께 저장하고 저장 실패 시 전부 롤백한다. head의 단일 ACTIVE/판본/문맥/본문 지문도 검증한다.
6. 승인·ARCHIVED 본문은 DB trigger로 불변. 기존 판은 보관하며 새 판 ID를 발급한다. 같은 제안 키/본문은 같은 change, 다른 본문은409. 승인·반려 재시도는 고정된 검토 결과를 반환하고 현재 접근권도 다시 확인한다.
7. 구 writer는 요청뿐 아니라 저장된 ID의 실제 행을 검사한다. tenant/identity/node 검증은 쓰기 잠금 안에서 수행한다. 최초 v2 초안 이후 v1이 먼저 저장되면 최초 승인409, v2가 먼저 승인되면 겹치는 구 writer409. 승인된 v1/ARCHIVED도 제자리 수정하지 않는다.
8. 구 profile 목록에 v2 원문을 섞지 않는다. 명시 문맥이 있는 구 화면은 승인 L1 읽기 전용 projection/editor_schema_required=2를 받는다. 구 API에서 ID를 알고 다른 문맥으로 접근해도404다. 일반 리스트 상속 및 미지원 가상기업 복제는 v2를 조용히 평면화/누락하지 않고409로 중단한다.
9. 신규 API를 기존 ECM router에 포함하고 쓰기 권한표·안정 reason_code·거부 감사와 연결했다. 로컬 감사 영속화만 완료하며 outbox 전달 상태는 **PENDING**이다. 외부 원장 송신 완료로 표시하지 않는다.

## API

모두 `/api/v1/enterprise-context` 아래이며 명시 X-Enterprise-Scope 또는 enterprise_scope가 필요하다. 클라이언트의 회사/모드/범위 값은 권한이 아니라 검사 대상이다.

- GET `/process-configurations/resolved`: 정확한 문맥/선택 승인판, payload/sources/digest/head_version.
- GET `/process-configurations/events`: 현재 범위의 감사 사건, 전달 대기 상태.
- POST `/process-configurations/changes`: 빈 문맥의 최초 제안.
- POST `/process-configurations/{configuration_id}/changes`: 기존 구성의 변경 명령.
- POST `/process-changes/{change_id}/validate`: 고정 초안 검증. 데이터/앱 준비와 분리.
- POST `/process-changes/{change_id}/approve`, `/reject`: expected_head_version/draft_digest/검토 이유 결속.

## 검증 이력 및 독립성

- 1차 `output/usage-holds-qydckij1`: **150 passed / 1 failed / 26.73초**. 구 저장 API가409 대신400을 반환한 계약 실패를 수정했다. SQLite166경로 임시 루트만, 소스 불변·금지 접근0·전역 conftest 없음.
- 2차 `output/usage-holds-qdthdfob`: **160 passed / 35.86초**. SQLite184경로 임시 루트만, 소스 불변·금지 접근0·전역 conftest 없음.
- B0+B1 통합 3차 `output/usage-holds-zsv7of4f`: **543 passed / 106.43초**, SQLite656경로 임시 루트만. 이어 기준판 손상 검증/승인2개·REAL/VIRTUAL/COMPETITOR_REFERENCE 독립 head3개를 추가했다.
- B0+B1 통합 4차 `output/usage-holds-2uwgl_mj`: **548 passed / 107.99초**, SQLite666경로 임시 루트만. 소스 불변·금지 접근0·전역 conftest 없음. 손상 기준판 검증/승인과 모드별 독립 head를 동적으로 확인했다.
- **최종 B0+B1 지정 회귀 `output/usage-holds-95pftf6f/tests.xml`·`isolation.json`: 550 passed / 111.18초**, third-party deprecation warning2개. SQLite670경로 모두 신규 임시루트, 검사 소스 전후 불변·금지 접근0·전역 conftest 없음. 실행 명령 `venv/Scripts/python.exe scripts/verify_data_usage_holds.py --b0 --b1`. 이전150/160/543/548은 중간 이력이지 추가 통과 합산 대상이 아니다.
- James(`01a09668-1a60-72a1-9bb1-79746e3d6888`)는 독립 부정 시험 파일1개/25케이스를 작성했다. 시험 실행은 하지 않았으며 메인 담당자가 격리 실행했다.
- Hilbert(`01a09660-955f-7570-855e-d40b068e858e`)는 정적 교차검토만 수행했다. 구 접점7개 확인 후 구현 검토 P1 두 건(v1 상위/industry 탐지 누락, tenant 삽입 경쟁), P2 한 건(head pointer 손상)을 발견했다. 모두 수정·회귀를 추가하고 현재 승인판 본문 지문 검사까지 재확인하여 **검토 범위 한정 PASS, 추가 P1/P2 없음**으로 종료했다. 마지막 `boundary_for`의 잘못된 입력422 변환도 별도 정적 PASS를 확인했다. 실제 시험 실행·운영 승인 독립 검증으로 부르지 않는다.
- 운영 DB·실제 회사 역할·인증·실적·앱/배포·브라우저를 검증하거나 변경한 것이 아니다. SYNTHETIC 조직/.invalid 사용자만 사용했다.

## B1이 완료하지 않는 것 / B2 착수 조건

- 기존 v1이 있으면 상위/root/industry 적용 자리까지 탐지하여 `PROCESS_CONTEXT_REVIEW_REQUIRED`. **실제 v1→v2 이관은 아직 구현하지 않았다.** B2 설치 미리보기에서 key/label/note/overlay null 원형, 원본 ID/digest, 명시 회사/root/mode 대응을 보존해야 한다.
- process pack/immutable package version/template_sources, 실제 바인딩/관계 검증, installation saga/인스턴스 멱등성은 B2/B3다. 현재 해당 참조를 임의 제출해 승인할 수 없다. B2는 이 validator를 버리지 말고 종류별 검증을 추가해야 한다.
- 회사 기본 구성과 조직 변형은 각각 완전한 판으로 저장한다. **상위 판을 고정한 변형 생성/업데이트 미리보기는 후속**이며 일반 resolver의 리스트 merge로 대체하지 않는다.
- 개인 숨김, 위임된 저위험 자기 발행, 분리/통합, 외부 감사 전달 재시도 worker, 복구/표준 업데이트는 아직 없다. 실제 역할 위임/승인 정책을 자동 생성하지 않는다.
- L2 UI 편집/탐색은 B4, 생성 문맥은 B3, 단일 Studio는 B5/B6다. B1을 UI 또는 현업 수용 완료로 부르지 않는다.
- 전체 T3의 starter 원문 변이/실행 순서 문제는 별도 미종결이다. B2에서 팩·전체 회귀 전 starter/manifest 쓰기 격리를 확인한다.

## 다음 작업 및 보존 규칙

- 다음: **B2 표준 프로세스 팩·BK-01 설치/재개/실패 및 기존 구성 이관**, 예상 **90~150분**. 확인된 범위/재작업에 따라 갱신하는 추정치이며 완료 보장이 아니다. 앞으로 단계 보고마다 다음 작업 예상 시간을 포함한다.
- 첫 재개 접점: `core/data_preparation/kit_registry.py`, `docs/data-kits`, `starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0/manifest.json`. 기존1.0.0을 덮어쓰지 않고 새 불변 팩 판본/설치 서비스와 명시 v1 대응 미리보기를 설계대로 연결한다.
- B0 인계 `docs/handoff/L2_STUDIO_B0B_CERTIFICATION_2026-09-13.md`의 완료 범위는 유지한다.
- 운영 DB/RAW/승인/역할/Starter1.0.0/앱/배포를 변경하지 않는다. 새 DDL은 이번 시험의 임시 ECM에만 실행했다.
- 사용자 `data/interaction_log.jsonl` SHA256 `7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510` 불변·커밋 제외.
- 현재 소스/시험/문서만 로컬 변경. 재개 시 git status·파일 소유권·최종 회귀 증거를 확인하고 B4/B5로 건너뛰지 않는다.
