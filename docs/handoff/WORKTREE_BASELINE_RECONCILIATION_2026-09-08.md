# 2026-09-08 공유 작업 트리 정리와 검증 귀속

- 작성자 / 기록 시각: Codex / 2026-09-08 15:26 KST
- 사용자 지시: Claude의 T3 진행 보고를 확인하고 작업 트리를 정리한다.
- 범위: 경영 홈 반응형 UI와 업무키트 초기 자료 후보 보강의 선별 로컬 커밋. 기능 추가·원본 재생성·DB 등록·푸시 없음.
- 시작 기준: `claude/data-acquisition-orchestrator-20260905`, `d56dfcda2`. 정리 도중 Claude가 `67646bac5`로 원천 선택 시험과 수집기 인수인계를 별도 커밋했다. 해당 파일은 Codex가 수정·스테이징하지 않았다.
- 로드맵 의미: G2-B/G2-D 자료 정합성과 경영 홈 사용성을 위한 기존 작업의 재현 가능한 기준점 보존이다. 새 제품 관문 완료 판정이 아니다.

## 1. 실제 T3 결과 — 통합 통과가 아니다

사용자가 전달한 작업 ID `bhmhiirll`의 로컬 결과 파일을 직접 읽었다.

```text
1 failed, 6445 passed, 2 skipped, 6 warnings in 869.25s (0:14:29)
FAILED tests/test_ecos_canary.py::test_catalog_ranks_both_providers_and_names_missing_credentials
```

- 실행 결과의 총계는 6,448 = 6,445 통과 + 2 건너뜀 + 1 실패다.
- 로그 끝의 `[exited with code 0]`은 pytest 실패 요약과 다르다. 실행 래퍼의 0을 T3 통과로 해석하지 않는다. 다음 실행은 pytest 자체 종료 코드를 보존해야 한다(파이프 후처리의 성공 코드로 덮지 않는다).
- 원천 선택 시험은 모든 원천이 자격증명을 요구한다고 가정했으나 World Bank 파일 원천은 그렇지 않다. Claude의 보정은 `67646bac5`에 있으며, Codex도 해당 실패 시험 한 건이 통과함을 확인했다.
- **수정 후 전체 T3를 재실행하지 않았다.** 하루 1회 예산을 추가로 소비하지 않았고 부분 회귀 통과를 전체 통과로 바꾸지 않는다.
- 결과 파일 SHA-256: `154ad432460a0f8052f2139c6b6d8a92a5c5928fab82805fb12c844e1a5bc342`.
- 로컬 결과: `C:/Users/denni/AppData/Local/Temp/claude/C--WorkSpace-gemini-agent-team-verG/41f4587b-817c-4532-bd65-4b5e919b51e6/tasks/bhmhiirll.output`. 임시 파일이므로 핵심 결과와 지문을 이 문서에 남긴다.

### 더 중요한 한계 — 검사 도중 대상 코드가 바뀌었다

결과 파일 수정 시각 15:15:50 KST와 소요 시간 869.25초로 보면 실행 시작은 약 15:01 KST다. Codex의 BOM 후보·생성기·CLI는 15:04:49, 후보 시험은 15:07:19에 수정됐다. 시작 시각은 로그 메타데이터에서 산출한 근사치지만, 실행 시간대와 파일 수정이 겹친다는 사실은 확인된다.

따라서 이번 결과는 단순히 “d56dfcda2 + 고정된 미커밋분”에 대한 검사로도 취급할 수 없다. Python이 읽은 코드의 시점과 디스크의 최종 바이트가 다를 수 있다. **최종 커밋의 통합 검증 상태는 HOLD**다. Codex가 그동안 변경한 사실도 누락하지 않는다.

보고에 적힌 “Codex 신규 시험 15건”을 현재 모수로 재사용하지 않는다. 현재 `test_kit_sample_revision.py`는 45건이며, 과거 실행이 수집한 모수와 현재 모수는 구별한다.

## 2. 정리한 변경 묶음

| 묶음 | 경로 수 | 내용 |
|---|---:|---|
| 경영 홈 UI — `aecdf1d85` | 8 | App/EnterprisePage, 전용 반응형 CSS, 실제 컴포넌트 fixture·빌더·화면 검사기, 전용 인수인계 |
| 업무키트 후보 보강 — 이 문서를 포함하는 커밋 | 8 | audit/revision 모듈, BOM 생성 중복 방지, 후보 CLI·45건 시험, 업무키트 인수인계, 이 문서, 팀 보드 기록 |

개별 명시 경로만 스테이징한다. `git add -A`, 이력 재작성, stash, 다른 팀원 변경 복구/삭제는 하지 않는다. 변경량이 경로별로 구분되므로 새 브랜치나 위험한 hunk 재조합이 필요하지 않다.

- 실행 로그 `data/interaction_log.jsonl`: 기존 추가 9행을 파일에 그대로 보존하고 커밋에서 제외한다.
- `tmp/kit-k2-bom-20260908/`, `tmp/home-responsive-layout/`: 생성 보고서·스크린샷이며 Git ignore 대상. 소스로 올리지 않는다.
- `starter_kits/` CSV·manifest·Excel: 변경하지 않는다. 후보의 PASS는 등록·인증·시연 완료가 아니다.
- 기존 인수인계의 “미커밋” 문구는 당시 상태 기록이다. 현재 정리 상태는 이 문서와 Git 이력으로 확인한다.

## 3. 이번 정리의 검증 근거

T3 종료 및 다른 pytest 프로세스 부재 확인 후 아래 영향 회귀를 실행했다. 새 기능이나 시험을 수정하지 않았다.

```powershell
venv/Scripts/python.exe -m pytest tests/test_kit_sample_revision.py tests/test_kit_sample_audit.py tests/test_business_kit_catalog.py tests/test_starter_package_catalog.py tests/test_kit_app_contract.py tests/test_kit_app_builder.py tests/test_kit_app_api.py tests/test_management_home_ui_contract.py tests/test_ui_layer_order.py tests/test_ecos_canary.py::test_catalog_ranks_both_providers_and_names_missing_credentials -q -o addopts= -p tests.plugin_test_auth -p no:warnings
```

**241 passed in 68.64s**, pytest 직접 종료 코드 0. 업무키트 137 + 경영 홈/UI 계층 103 + Claude 보정 단일 시험 1이다.

검사 전후 아래 코드 12개 파일의 SHA-256이 모두 동일했다. 이 목록은 원시 작업 파일 바이트 기준이며 Git 개행 정규화 후 blob ID와는 다르다. 문서·팀 보드 기록은 시험 뒤 추가했다.

| 경로 | SHA-256 |
|---|---|
| `core/data_preparation/kit_sample_audit.py` | `d1e745cecaaca528e7d082754bb5390c23b262343d0ea5cccb2b36a2ae53031c` |
| `core/data_preparation/kit_sample_revision.py` | `1ea0283389b69b171dfdbecfad0ca8a342524d4f9635f6e2bd62e8d3993689d8` |
| `scripts/generate_sample_company_starter_kit.py` | `d2331eeff6b4e6c7c04f438a009c9ddc9078adab3387f280f084599505380c80` |
| `scripts/plan_business_kit_initial_revision.py` | `bcb074ff89f1d984111ce4a720ecfb8372e6f21d09f5ed7cb9c75e5f8aa5326c` |
| `tests/test_kit_sample_revision.py` | `3dfb850ba56886586e8ad60347f6210e51ef336431a92c7466af5ee620626e05` |
| `frontend/src/App.tsx` | `0d1c72111d4fa02263df5d5e13b00373b2d62c5928e464c3947727f294236f62` |
| `frontend/src/components/EnterprisePage.tsx` | `fe180e98c5177c7e6b7f515a146e0c4997f1e4e217f910b6f665eeb10673fdc7` |
| `frontend/src/design/enterprise-responsive.css` | `c39a064a15dfded5012971a81dc5a1335501d479aa38c067853f1da824205bfb` |
| `frontend/scripts/build-enterprise-layout-fixture.mjs` | `a217dbb30f2785908b7cd23aaa2d9e962648b4427b7d924f3d962265b9bef428` |
| `frontend/tests/enterprise-layout.fixture.html` | `54867acfefe2d9d87413d5defa8f762214154ae42c3b76df7f14d5b3be58bd33` |
| `frontend/tests/enterprise-layout.fixture.tsx` | `ce3acca3e08d21f8e48d7cda1c7fe1dc6549d237bce0d9092b35c255a4c60569` |
| `scripts/check_enterprise_responsive.py` | `b4855e3703d577051a6a07d2cd826e2a9285da14f5387b90bc5371a830478e00` |

UI의 이전 검증: 제품 빌드·TypeScript 통과, 10개 viewport × 기본/긴 12단계 화면 총 20조건 통과. 이번에는 빌드/실제 인증 브라우저/T3/운영 불변식 비교를 다시 실행하지 않았다. 상세는 [경영 홈 인수인계](HOME_RESPONSIVE_LAYOUT_2026-09-08.md)와 [업무키트 §9](BUSINESS_KIT_INITIAL_DATA_EXECUTION_2026-09-08.md#9-경영-홈-해상도-보정-후-재개--간편-샘플-bom-충돌-해소)를 따른다.

## 4. 다음 T3와 재개 조건

- 다음 일일 T3 전에 두 담당자가 코드·시험 커밋을 마치고 실행 SHA/수집 모수/환경을 기록한다. 실행 담당자만 멈추는 것은 공유 트리 동결이 아니다.
- 공유 트리 전체의 동결을 보장할 수 없으면 **정확한 커밋의 별도 검증 worktree**에서 검사한다. 미커밋분을 몰래 복사하지 않고, 격리 설정과 필요한 샘플 경로를 확인한 후 시작한다.
- 같은 설치에서 pytest를 중복 실행하지 않는다. T3 종료 코드와 수집 = 통과 + 실패 + 건너뜀을 함께 기록한다.
- 실패 수정 후 부분 회귀만 수행했으면 통합 상태는 HOLD로 유지한다. 일일 예산과 무관하게 실제 배포가 필요하면 새 검증 여부를 사용자와 먼저 결정한다.
- 다음 개발은 업무키트 K2의 INV-02 → INV-01 → MFG-02 → SLS-01 수량 대사다. 후보 원본/DB 적용과 과거 843행의 유효기간 소급은 하지 않는다.
- 이 정리 작업은 fetch/pull/push/원격 갱신을 수행하지 않는다. 남은 실행 로그 때문에 전체 작업 트리가 clean이라고 보고하지 않는다.
