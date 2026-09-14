# B6 프로젝트 진입 확인 — 20~30분 작업 인계

> 최신 재개 입구: [Claude Code 시작 안내](CLAUDE_CODE_START_HERE_2026-09-15.md). 이 파일 앞부분의22건 검증·DDL 예외·다음 READ 작업은 과거 기록이며, 아래 「후속 묶음: 판본 READ 초기화 제거」가 이를 갱신한다. 인계 직전312건 재검증과 코드 커밋215253f22는 시작 안내를 따른다. App 미연결·실제 브라우저 미실행은 그대로다.

작성: Codex / 권고10 / G3. 시작 2026-09-14 23:54:32 KST. 사용자 요청에 따라 B6 전체가 아닌 project 대상 연결부만 수행한다.

## 범위와 현재 제품 진척

- 기준선 `codex/l2-unified-studio-20260912` / `dd0573383`. 이전 B5 수정 및 C0 모듈의 미커밋 변경 위에서 작업했다. 이번에 원격 동기화·커밋·푸시는 하지 않았다.
- 전체 **21/40=52.5%**, 로컬 **18/28≈64.3% 유지**. 이번 결과는 B6 내부 모듈이며 전역 연결 관문 완료가 아니다.
- `App.tsx`와 `api/main.py` 미변경. 현재 앱의 사용자 진입 동작은 아직 바뀌지 않는다. kit/release/mega/draft/new 대상, 히스토리·SSE·기존 화면 통합은 이번 범위 밖이다.

## 구현

1. `api/routes/factory_control.py`: `GET /api/v1/factory/{project_id}/entry-metadata`. 기존 서버 읽기 권한·현재 회사 문맥·v2 승인 문맥 확인을 재사용한다. 이름·ID·문서 버전·소유 문맥·조회 문맥만 반환한다. 원문 상태·입력 초안·체크포인트 응답은 전달하지 않는다. 반환 직전 메타데이터 및 권한을 재확인한다.
2. `frontend/src/factory/studioProjectEntry.ts`: API 응답을 정확한 프로젝트 ID·선택 회사 문맥과 대조한다. 실패 상세를 노출하지 않고 다시 조회할 수 있게 한다. 세대 번호와 AbortController로 취소·역순 응답·회사 A→B→A 변경 후 지연 응답을 폐기한다. 회사/로그인 전환 시 기존 확인 데이터를 즉시 제거하며 자동 재조회하지 않는다.
3. `frontend/src/factory/StudioProjectEntryGate.tsx`: 로딩·조회 확인·접근 불가·재시도 상태를 제공한다. 현재 문맥의 확인된 응답이 있을 때만 자식 Studio를 구성한다. 조회 가능을 실행·게시 승인으로 표시하지 않는다.
4. 신규 집중 검사: `tests/test_b6_project_entry.py`, `frontend/scripts/check-project-entry.mjs`.

## 검증과 한계

- 프런트 신규 **26PASS/0FAIL**: 실제 모듈에 모의 HTTP를 연결한 UNIT/API/flow/SSR 검사다. 실제 DOM effect·브라우저·실서버 연동 성공의 근거는 아니다.
- 기존 C0 **25PASS**, B5 프런트 **153PASS** 재통과. B5 결과: `output/studio-contracts-c002afd0-db07-4f35-b02c-162ba1ccf976/report.json`.
- TypeScript, 신규 두 파일 ESLint, 제품 build PASS. 기존 청크 크기 및 정적/동적 import 혼용 경고는 남는다.
- 서버 최초 **12PASS/2FAIL**, pytest6.24초: `output/usage-holds-1r3jx9dz/isolation.json`. 권한 회수 시험과 SQL 무쓰기 시험의 실패를 숨기지 않는다. 이 실행의 소스·보호 자산 지문 불변, 금지 경로 쓰기 차단0.
- 서버 최종 판정과 두 실패의 원인·조치는 아래 마감 기록을 따른다. 최초 계획의 절대적인 SQL 무쓰기 여부와 업무 데이터 무변경 여부를 구분해야 한다.
- 독립 검토: Hilbert 서버 구현 → Codex 대조, Codex 프런트 구현 → Hooke 소스 검토. 프런트 최종 추가 확정 P1/P2 없음. 이는 실제 화면 수용을 대체하지 않는다.

## 다음 담당자가 놓치면 안 되는 연결 조건

- `StudioProjectEntryGate`는 아직 App에 import되지 않았다. 이 모듈만으로 실제 사용자 기능 완성 또는 단일 mount 완료라고 보고하지 않는다.
- 전역 연결 전 원본 병렬 통합계획의 Gate 증거를 확인한다. App은 Codex 단독 변경 영역이다. 진행 중인 전역 통합 HOLD를 이 모듈로 임의 해제하지 않는다.
- 현재 `setActingUser()`는 직접 변경 이벤트를 발생시키지 않는다. 로그인/로그아웃은 session 이벤트를 내보내지만, 별도 사용자 교체 경로를 붙일 때는 해당 이벤트 계약을 보장해야 한다. 이벤트 없는 변경을 실시간 감지한다고 주장하지 않는다.
- URL 문법 모듈은 최대200자의 불투명 ID를 허용하지만 project reader는 기존 실행/초안 흐름에 맞춘 ASCII 영숫자·밑줄·하이픈 최대160자만 받는다. 다른 target의 문법 통과를 project 조회 성공으로 간주하지 않는다.
- 성공 응답의 소유 조직과 현재 조회 조직은 상위/하위 관계일 수 있다. 조직 ID 단순 일치로 권한 판정을 대체하지 않는다. 프런트는 서버가 검증한 문맥만 확인한다.
- 새로운 UI가 필요한 다음 묶음은 프로젝트 진입 연결 대상으로 다시 20~30분 단위로 산정한다. Gate 미해결 시 공통 초기화 부수 효과 정리부터 진행하며, 전역 연결·브라우저 수용까지 같은 시간 안에 완료한다고 약속하지 않는다.

## 재실행

저장소 루트에서 Python 소스 편집을 멈춘 뒤:

```powershell
venv/Scripts/python.exe -B scripts/verify_data_usage_holds.py --strict-writes --target tests/test_b6_project_entry.py
node frontend/scripts/check-project-entry.mjs
node frontend/scripts/check-studio-location.mjs
node frontend/scripts/check-studio-contracts.mjs
```

`frontend` 폴더에서:

```powershell
npx.cmd tsc --noEmit --incremental false
npx.cmd eslint src/factory/studioProjectEntry.ts src/factory/StudioProjectEntryGate.tsx
npm.cmd run build
```

## 보존

- 사용자 기존 `data/interaction_log.jsonl` SHA256 `7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510` 유지.
- 운영 DB·키·암호문은 수정하지 않는다. 테스트는 격리 RUN 데이터만 쓴다. ignored 출력은 재현 증거이며 커밋에 자동 포함하지 않는다.

## 마감 기록

- 마감 검증 시각: 2026-09-15 00:16:36 KST(시작 후22분04초). 이후 문서·보존 확인만 수행하고 다음 묶음은 착수하지 않는다.
- 서버 최종 독립 재실행 **22PASS/0FAIL**, pytest10.09초·wrapper16.55초. 근거: output/usage-holds-ckd38t6i/isolation.json. 소스·보호자산 지문 불변, 금지 파일/SQLite 경로 쓰기0, repository conftest 미적재. Hilbert의 선행 최종 실행도22PASS/9.93초(output/usage-holds-z4o_v_fd)다.
- 최초 권한 실패는 실제 선택 문맥 캐시 경계였다. 새 GET의 전·후에 공유 판정과 동일한 선택 조직 규칙을 fresh scope로 추가 확인해 이 경로를 닫았다. 타 연결에서 SQL로 부서·주 소속을 변경하는 최초 회귀와 정상 계정 폐지 회귀를 모두 보존해 통과했다. 공유 함수와 다른 API가 같은 방식으로 수정됐다는 뜻은 아니다. 후속 공통화 시 이중 규칙의 드리프트를 방지해야 한다.
- 손상된 project_name 객체·배열·숫자·불리언·과대 문자열을 문자열화해 전달하지 않고503으로 거절한다. 이름 누락/빈 문자열은 기존 ID 대체를 유지한다. 403/404와 ProcessError 비가시 응답도 일반 은폐 문구로 정리했다.
- **절대 SQL 무쓰기 출구는 미완료다.** 공유 RevisionStore가 조회에서도 알려진 CREATE TABLE/TRIGGER IF NOT EXISTS 초기화를 실행한다. 시험은 그 정확한 DDL 원문의 SHA256을 고정하고 해당 문장만 예외로 추적한다. 업무 INSERT/UPDATE/DELETE, 알려지지 않은 DDL 및 프로젝트 파일 쓰기는 허용하지 않는다. 사전 예열로 쓰기를 숨긴 결과가 아니며, 거절 감사 기록의 쓰기까지 제거했다고 주장하지 않는다.
- 관리형 v2 시험은 for_principal의 검증된 DTO를 명시 대역으로 공급한다. 실제 v2 승격·정책·DB·파일 전체 연결을 이번22건으로 증명하지 않는다. 성공 무업무쓰기 검사는 실제 legacy reader 경로다.
- 최종 판정: 프로젝트 진입 API와 프런트 확인 모듈 구현·집중검증 완료. **App 통합·실제 브라우저·절대 SQL 무쓰기·B6 전체 수용 미완료.** 전체52.5%/로컬64.3% 유지. 다음20~30분은 공유 reader 초기화 부수효과 정리의 좁은 구현부터 진행하고, 전역 연결은 통합 Gate 조건 확인 후 별도 묶음으로 둔다.

## 후속 묶음: 판본 READ 초기화 제거 — 2026-09-15 00:33 KST

### 범위와 구현 결과

- 작성 Codex / 권고10 / G3. 사용자 「다음 진행」 승인으로 00:18:42 KST 시작, 20~30분 이내의 제한 묶음. 위 마감 기록의 RevisionStore 잔여를 해결했다. 전체21/40=52.5%, 로컬18/28≈64.3% 유지.
- core/advisor_revision_store.py: 명시적인 read_only=True 모드 추가. 기존 파일을 정규 SQLite URI mode=ro로 열고 기존 쓰기용 _connect·_ensure를 호출하지 않는다. _ensure와 쓰기 transaction은 연결 전에 ADVISOR_READ_ONLY/503으로 거절한다. 기본 모드는 그대로이므로 기존 저장·승인·승격 명령의 초기화 계약을 유지한다.
- read-only cohort 판정: DB가 없거나 손상됐으면503. v2 스키마가 전혀 없고 기존 consultations/solution_blueprints 실제 테이블이 함께 있는 경우만 legacy로 판정한다. 일부 v2 테이블만 있거나 필수 열이 빠졌으면503. 조회가 테이블을 보수하거나 새 DB/부모 폴더를 만들지 않는다.
- core/studio_project_context.py: 기본 저장소를 구성하는 READ 경로에만 읽기 전용 모드를 연결했다. 명시적으로 주입한 revisions 객체는 변경하지 않는다. legacy 판정 후에만 ProcessContextService를 구성하도록 이동했다. 승인·이력·소유 문맥·현재 PDP 검증은 제거하지 않았다.
- tests/test_b3_studio_drafts.py: 기존 fixture가 모든 URI를 차단하던 부분에 현재 시험 root의 기존 정규 파일과 정확한 mode=ro 옵션만 허용했다. 쓰기 URI, 추가 옵션, VFS, 메모리 URI는 별도 회귀로 거절한다. 전역 격리 런너는 변경하지 않았다.

### 검증 근거

- 첫 실행 **193PASS/8FAIL**, pytest36.51초: output/usage-holds-02m5xq02/isolation.json. 실패8건은 DB 본체가 아니라 새 WAL/SHM 보조파일 때문에 전체 파일 해시 비교가 실패한 것이었다. 원기록을 보존하며 「첫 실행도 통과」로 고치지 않는다.
- SQLite mode=ro도 WAL 공유메모리 보조파일을 생성할 수 있다. 검사를 DB 본체·비보조파일 보존과 정확히 지정한 DB의 WAL/SHM 관찰로 분리했다. 다른 파일명/고아 sidecar/링크/외부 경로를 면제하지 않는다. 보조파일을 숨기려고 immutable 모드나 사본 읽기를 사용하지 않았다.
- tests/test_b6_revision_reads.py 신규18건: 차가운 legacy 조회의 DDL/DML0·DB 본체 해시 보존, SQL 수준 쓰기 거절, 없는/손상/부분/축약 스키마 차단, 기존 승인·예약·완료판·경계·무결성 유지, 특수문자 URI, WAL 보조파일 관찰. 열린 snapshot으로 checkpoint를 막은 상태에서 두 독립 커밋을 새 READ transaction이 모두 읽고, 읽기 구간의 DB 본체와 기존 WAL 해시가 그대로임을 검증했다.
- tests/test_b6_project_entry.py: 이전 알려진 DDL 예외를 제거했다. legacy 성공 GET의 DDL·DML0, 유실 Advisor DB의503·미생성, URI 옵션 우회 거절을 검사했다. 실제 v2 승인판·승격·ECM·PDP를 거치는 READ에서도 세 판본 조회가 읽기 전용 연결을 사용함을 확인했다. 이 managed fixture에는 인증 데이터·표준 팩이 없다.
- 최종 **251PASS/0FAIL**, pytest43.30초·wrapper49.73초: output/usage-holds-iucppa6_/isolation.json. 신규18건/프로젝트 진입28건/기존 판본 저장·실행 문맥·상담 초안 회귀를 포함한다. 소스·보호자산 지문 불변, 금지 파일·SQLite 경로0, repository conftest 미적재.
- 프런트 프로젝트 진입 계약26PASS 재확인(모의 네트워크/SSR). 프런트 소스 무변경이므로 제품 build/TypeScript는 이번에 반복하지 않았다. 실제 브라우저 NOT_RUN.
- 교차검토: Codex 제품 수정 → Hilbert 독립검토. 테이블명만으로 손상 스키마가 통과하는 P2를 지적받아 필수 열 검사와 회귀로 수정했다. 추가 확정 P1/P2 없음. Hooke 신규 시험 구현 → Codex 대조·실행; 보조파일/SQL 관측 경계도 Hilbert 검토를 반영했다.

### 남은 경계와 다음 작업

- **완료: RevisionStore READ의 schema 초기화와 업무 DML 제거. 미완료: 모든 저장소·모든 파일에 대한 물리적 무쓰기.** DB 본체와 SQLite 보조파일은 구분한다. 애플리케이션 시작 시 singleton 초기화와 접근 거절 감사 기록까지 제거한 것이 아니다.
- 관리형 프로젝트의 표준 팩·인증 데이터 조회에는 DP Store의 _ready/마이그레이션, OWNER_CERTIFIED 정책의 DecisionLedger 초기화, ECM의 RW 연결이 별도로 남아 있다. 실제 데이터가 연결된 managed READ 전체를 무쓰기라고 보고하지 않는다. 이 영역을 이번 승인 범위로 전부 확대하지 않았다.
- App/main, 전역 URL·SSE·히스토리는 그대로다. B6 전체 관문 완료로 가산하지 않는다. 다음 묶음은 프로젝트 진입 화면 연결의 Gate 확인 및 첫 연결 범위를20~30분으로 산정한다. 다른 저장소의 부수효과가 해당 경로에 영향을 주면 먼저 명시하고 무시하지 않는다.
- 기존 B5/C0/진입 모듈 dirty 및 사용자 로그를 보존했다. 로그 SHA256 7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510. 운영 DB·키·암호문·원격 무변경, commit/push 미실행.

재실행(저장소 루트, Python 소스 동결 후):

    venv/Scripts/python.exe -B scripts/verify_data_usage_holds.py --strict-writes --target tests/test_b6_revision_reads.py --target tests/test_b6_project_entry.py --target tests/test_b3_advisor_revisions.py --target tests/test_b3_execution_context.py --target tests/test_b3_studio_drafts.py

    node frontend/scripts/check-project-entry.mjs
