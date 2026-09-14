# 세션 간 설정·업무 데이터 전달

## 최신: 키 없이 다른 PC로 복원 — 2026-09-15

사용자가 “그냥 복호화하고 다 공유해줘요”로 기존 스냅샷 평문 공유를 승인했다.
이제 **session-data-20260913.zip을 pull로 받으면 키가 필요 없다.**
공개 저장소에서 누구나 내용을 읽을 수 있다. 암호화본과 같은 164파일(15DB·143RAW·설정6개)을
바이트 변경 없이 전달하며, 스냅샷 내부 manifest도 보존했다. 새로 추출한 최신 데이터가 아니라
**2026-09-13 시점의 데이터**다.

### 다른 Windows PC에서 실행

1. codex/l2-unified-studio-20260912 브랜치를 최신 상태로 받는다.
2. 새 checkout 경로를 C:\WorkSpace\gemini_agent_team_verG로 맞춘다.
   기존 DB가 있는 checkout은 덮어쓰지 않는다. 원본 PC에는 복원하지 않는다.
3. Python 가상환경과 저장소 의존성을 준비하고 앱을 중지한다.
4. 저장소 루트에서 다음 명령을 순서대로 실행한다. 각 명령이 성공한 뒤 다음으로 진행한다.

    venv/Scripts/python.exe -B scripts/session_data_snapshot.py verify --bundle data_sync/session-data-20260913.zip

    venv/Scripts/python.exe -B scripts/session_data_snapshot.py restore --bundle data_sync/session-data-20260913.zip --destination C:/WorkSpace/gemini_agent_team_verG

검증 기대값: verified_files=164, verified_databases=15, all_file_hashes_match=true.
평문 ZIP이므로 authenticated_decryption=false가 정상이다. SHA 검사는 손상 검사용이며
독립적인 배포자 서명/인증을 제공하지 않는다.
복원은 DB/RAW/설정을 명시적으로 채우는 단계다. **pull만 해서는 실행 DB가 자동 생성되지 않는다.**
기존 파일 때문에 거절되면 삭제로 해결하지 말고 충돌 경로를 보고한다.

다른 경로/OS에서는 DB 내부 절대 참조 때문에 아래 **검사용 사본**만 지원한다.
이 사본을 실행 환경 이관 완료로 보고하지 않는다.

    venv/Scripts/python.exe -B scripts/session_data_snapshot.py restore --bundle data_sync/session-data-20260913.zip --destination output/session-handoff/plain-inspection --copy-only

### 범위와 검증

- 암호화본에서 제외했던 .env·API 키·비밀번호·인증 DB·세션·커넥터·개인 대화·로그·생성 프로젝트·체크포인트·library는 여전히 제외다. 이를 추가로 수집한 “PC 전체 백업”이 아니다.
- 로그인 계정은 새 환경에서 별도 준비한다. 실제 화면·권한·참조 자산 확인은 복원 후 필요하다.
- 원본 암호화본/키/업무 DB는 수정하지 않았다. 키는 Git에 추가하지 않는다.
- ZIP SHA256: 9c60dccd210974fecc7a65f3945d2617371d416cb12a01153fa80d411977ab34.
- ZIP 크기: 13,671,964bytes. 164개 파일 해시 및 암호화본과의 전체 내용 일치 확인.
- 이관 도구 회귀15건 통과. 대표 자격증명 패턴 미탐지이며 전체 개인정보/DLP 무결점 보장은 아니다.
- 실제 검사 사본 복원 후164파일 해시와15DB quick_check·전체 표별 건수를 원본 manifest와 대조해 통과했다. 다른 PC 앱 실행 수용은 아직 별도다.
- 기존 암호화본은 호환성을 위해 남겨두지만 **같은 내용의 평문을 공개했으므로 그 내용의 기밀성은 더 이상 보장되지 않는다.**

## 이하: 이전 암호화본 절차 — 새 PC에서는 위 ZIP 절차 우선

아래 “키 별도 전달/평문 금지”는 이전 승인 당시 기록이다.
2026-09-15 사용자 승인으로 **이 특정 스냅샷의 평문 공유만** 변경되었다.
다른 데이터/자격증명 전체 공개나 기존 데이터 덮어쓰기를 허용하는 것은 아니다.

> **전달 상태: 사용자 명시 승인으로 암호문 Git 포함(2026-09-13 23:45 KST).** 공개 저장소에 암호화 업무 스냅샷을 추가하고 복호화 키는 별도 비공개 전달한다는 조건을 안내한 후 사용자가 “네 승인합니다”로 승인했다. 이 추가 커밋은 `session-data-20260913.aesgcm`을 포함한다. `pull`로 암호문을 받고, 별도 키를 준비한 뒤 아래 명령으로 검증·복원한다. 평문 DB·키·인증정보는 Git에 추가하지 않는다. 앞선 `58713ed1d`에서는 암호문이 제외돼 있었다.

GitHub 원격은 2026-09-13 확인 시 **public**이다. 평문 운영 DB를 강제 추적하지 않는다.
이 폴더의 `*.aesgcm`은 현재 로컬 설정·업무 데이터의 **AES-256-GCM 암호화 스냅샷**이다.
`snapshot-public.json`에는 파일 수·용량·암호문 SHA만 있고 복호화 키나 업무 본문은 없다.

키는 원본 PC의 `output/session-handoff/session-data-20260913.key`에 별도 보관한다.
Git에서 제외된 키를 **비공개 보안 경로로만** 전달한다. 저장소·이슈·공개 채팅·커밋에 넣지 않는다.
키를 분실하면 암호문에서 복구할 수 없다. 공유 PC에서는 파일 ACL도 확인한다.

상세 인수인계: [L2_STUDIO_CROSS_SESSION_HANDOFF_2026-09-13.md](../docs/handoff/L2_STUDIO_CROSS_SESSION_HANDOFF_2026-09-13.md).

## 검증·복원

Python의 `cryptography`가 필요하다(작성 환경 46.0.7). 저장소 루트에서 실행한다.

```powershell
venv/Scripts/python.exe -B scripts/session_data_snapshot.py verify --bundle data_sync/session-data-20260913.aesgcm --key-file output/session-handoff/session-data-20260913.key
```

현재 PC의 기존 데이터에는 복원하지 않는다. 이미 최신 원본이며 덮어쓰기가 거절된다.
다른 PC에서 원래와 같은 절대 경로의 새 checkout을 준비하고 앱을 중지한 후:

```powershell
venv/Scripts/python.exe -B scripts/session_data_snapshot.py restore --bundle data_sync/session-data-20260913.aesgcm --key-file output/session-handoff/session-data-20260913.key --destination C:/WorkSpace/gemini_agent_team_verG
```

기존 DB·다른 설정이 있으면 **쓰기 전 거절**한다. Git의 동일 바이트 설정 파일만 그대로 둔다.
자동 덮어쓰기·자동 DB 병합·새 승인 부여·인증계정 복원은 없다. 실패 후에는 기존 데이터를 삭제하지 말고 별도 복원 위치를 정한다.

다른 경로에서는 **검사용 사본**만 만들 수 있다:

```powershell
venv/Scripts/python.exe -B scripts/session_data_snapshot.py restore --bundle data_sync/session-data-20260913.aesgcm --key-file output/session-handoff/session-data-20260913.key --destination output/session-handoff/inspection-copy --copy-only
```

DB에 RAW·Starter 경로가 절대경로로 저장되어 있어 임의 문자열 치환은 지문·승인 결속을 깨뜨릴 수 있다.
`--copy-only`는 경로를 바꾸지 않으며 실행 가능한 복원으로 취급하지 않는다.
검사 데이터는 지정 위치의 **`inspection-files/` 아래**에만 쓰며, 먼저 검사전용 마커를 만든다. 지정 checkout의 `data/`를 채우지 않는다. RAW는 현재 데이터 형식인 CSV만 허용하고 민감 파일명은 내보내기/복원 공통으로 거절한다(본문 전체 DLP 검사라는 뜻은 아니다).
새 경로에서 제품 실행까지 동일하게 재개하려면 별도의 참조·지문 보존 이관 검증이 필요하다.

## 범위

- 포함: 회사/조직/업무 프로필, 기준정보, 키트 인스턴스·데이터 준비, 데이터 원본 RAW, 원장/앱 데이터/온톨로지/계획 등 허용한 업무 DB 15종, 인스턴스·참조·범위·모델 라우팅·워크플로우 설정. 실제 파일 수는 공개 manifest 참조.
- 승인/역할 관련 업무 기록은 **암호문 안에 원형 보존**한다. 새 환경의 인증이나 새 사용자 권한을 자동 부여하지 않는다.
- 제외: `.env`, API 키, 인증 DB/비밀번호/세션, 커넥터 DB, Advisor 개인 대화, 상호작용·접근·LLM 로그, `projects/` 생성 산출물·실행 체크포인터, library/knowledge cache, 외부 원문/백업/테스트 출력.
- DB는 read-only 연결에서 SQLite backup API로 복사한다. 원본 본체/WAL의 내보내기 전후 지문을 대조한다. 여러 DB를 하나의 분산 트랜잭션으로 동결한 것은 아니다.
- 이 자료는 **현재 업무 설정·데이터의 전달**이며, 실행 중인 LLM 작업·브라우저 메모리 초안·기존 로그인 세션의 이동이 아니다.

## 갱신

앱의 쓰기가 없는 시점에 새로운 날짜/파일명으로 `export`한다. 기존 파일/키를 자동 덮어쓰지 않는다.
암호문과 공개 manifest만 함께 커밋하고 키는 별도 보관한다.

```powershell
venv/Scripts/python.exe -B scripts/session_data_snapshot.py export --bundle data_sync/session-data-NEW.aesgcm --key-file output/session-handoff/session-data-NEW.key --report data_sync/snapshot-NEW-public.json
```
