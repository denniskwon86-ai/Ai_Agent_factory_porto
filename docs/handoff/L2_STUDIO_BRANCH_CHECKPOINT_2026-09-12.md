# L2·통합 제작 화면 착수 전 체크포인트

- 작성자 / 기록 시각: Codex / 2026-09-12 19:56 KST
- 사용자 지시: 현재 작업 커밋·푸시 → 새 브랜치 → 상세 설계·계획 → 객관적 이중검토 → 구현.
- 기존 브랜치: `claude/data-acquisition-orchestrator-20260905`, 시작 HEAD `335a8759f`.
- 후속 브랜치 예정: `codex/l2-unified-studio-20260912`.
- 성격: **현재 작업 보존용 체크포인트. 정상 제품 기준선·릴리스·배포 승인이 아니다.**

## 보존 범위와 기여

Codex의 사용 보류 소비 경계와 Claude Code의 회사 실적 인증 M0가
`models.py`, `store.py`, `snapshot_service.py`에 함께 존재한다.
사용자가 현재 작업의 커밋·푸시를 지시했으므로, 공통 파일을 임의로 분해하지 않고
의존 API·시험을 포함한 공동 작업 보존 커밋으로 기록한다. Codex 단독 구현으로 귀속하지 않는다.
코드 체크포인트와 설계·인계 문서 커밋은 분리하며, 디렉터리 전체가 아닌 명시한 파일만 스테이징한다.

- Codex: `usage_policy.py`, 보류 투영·인증/교체 잠금, readiness/scope index/앱/계산 소비 차단,
  격리 검증 도구, 관련 회귀, L2 상세 설계.
- Claude Code: OWNER_CERTIFIED, 실적 서명·용도·기간 저장과 API, 실적 인증 시험·제안·검증계획.
- `core/actual_certification_policy.py` 등 기존 HEAD의 정책 구현은 이미 추적된 자산이다.
- `data/interaction_log.jsonl`은 로컬 실행 기록이므로 스테이징하지 않고 원문을 보존한다.
  확인 지문: `7720cc456594ee3f3d5387d16c35ca26ec303fd177e0cb1eee05538223dcf510`.
- 운영 DB·RAW·인증·권한·회사 구성·생성 앱은 변경하지 않았다.

## 이번 턴의 재검증

1. `venv/Scripts/python.exe scripts/verify_data_usage_holds.py`: **234 passed**.
   증거: `output/usage-holds-7gwrk_3i/tests.xml`, `isolation.json`.
   새 실행 폴더 내 SQLite 168개 경로만 허용, 금지 접근 0, 소스 지문 불변, 전역 conftest 미로드.
2. 실적 인증 + 프로젝트 데이터 문맥 시험: **29 passed / 7 failed**.
   실적 인증 28건 통과, 프로젝트 데이터 문맥은 1건 통과·7건 실패.
   새 임시 폴더 밖 SQLite를 audit hook으로 차단하고 `--noconftest`로 실행했다.
   증거: `C:/Users/denni/AppData/Local/Temp/afs-checkpoint-646553vg/tests.xml`.
3. 실패 7건은 모두 `FakeStore.transaction` 부재. 위치는
   `core/data_preparation/usage_policy.py:73`이며 선행 Claude 인계와 같은 증상이다.
   **테스트를 삭제·SKIP하거나 정책을 완화해 통과시키지 않았다.**
4. 전체 T3, 브라우저, 실제 사용자 인증·실사용은 이번 턴 미실행.

## 새 브랜치의 구현 진입 조건

- 지금은 상세 설계·계획 문서 작업만 허용한다. 위 실패를 정상 기준선으로 간주해 L2 구현을 쌓지 않는다.
- 이중검토에서 소비 경계 계약을 결정한 후 G0에서 7건을 먼저 해소한다.
  후보는 저장소가 투영한 `usage_holds`를 fail-closed로 검사하는 방식이다.
  미확인/누락을 빈 보류 목록으로 바꾸거나 `transaction` 부재를 허용하는 방식은 금지한다.
- 실적 인증의 기존 28건 통과를 모든 경쟁 안전성 증명으로 확대하지 않는다.
  잠금 밖 마지막 서명 판정과 동시 서명 fallback의 별도 트랜잭션 경로를 독립 검토·시험한다.
- L2 최소 구조·생성기 단일화 상세 설계와 두 독립 검토의 P0/P1 해결 후에만 관련 구현을 시작한다.
- 최종 제품 통합은 기존 통합 계획의 별도 clean worktree·단계별 Gate를 유지한다.
  이번 작업은 다른 브랜치 merge/cherry-pick 또는 dev 승격이 아니다.

## 진척과 다음 행동

- 전체 **21/40=52.5%**, 로컬 **18/28≈64%** 유지.
- 이번 보존·설계·검토는 제품 연결·실사용 완료 점수로 가산하지 않는다.
- 담당 Codex: 커밋·원격 일치 확인 → 새 브랜치 → 상세 설계·실행 계획 → 독립 이중검토.
- 실제 커밋 ID·푸시 결과는 후속 설계/검토 인계에서 기록한다. 이 문서 작성 시 아직 미실행이다.
