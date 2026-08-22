# 배포 — Ubuntu 재현 패키징 (WEB-1)

> ⚠️ **이 디렉터리는 «빈 리눅스 VM 에서 문서에 없는 수동 조작 없이 첫 화면이 열린다»를
> 목표로 한다.** 그 조건은 **실제 VM 에서만** 증명된다 — 여기 있는 것은 그 증명을 하기
> 위한 재료이지 증명 자체가 아니다.

## 무엇이 들어 있나

| 파일 | 역할 |
|---|---|
| `install.sh` | 빈 Ubuntu 에서 의존성·venv·프런트 빌드까지 |
| `update.sh` | 코드 갱신 + 백업 + 재시작 |
| `check.sh` | 배포 뒤 점검 — 헬스·첫 화면·주요 라우트 |
| `backup.sh` | SQLite 온라인 백업 + manifest (WEB-2) |
| `afs.service` | systemd 유닛 |
| `Caddyfile` | 도메인·TLS·리버스 프록시 (WEB-3) |

## ⚠️ 배포 전에 반드시 아는 것

### 1. 코드와 데이터는 **다른 디렉터리**다

    /opt/afs/app        ← 릴리스 코드(갈아 끼운다)
    /opt/afs/data       ← data/ · projects/ · output/ (남는다)

⚠️ 한 디렉터리에 두면 배포가 데이터를 지운다. `install.sh` 가 심볼릭 링크로 잇는다.

### 2. **`torch` 가 딸려 온다 (~2.5GB)**

`langchain-core` → `transformers` → `torch` 로 **기동 시점에** 끌려온다. 선택 사항이
아니다. 데모 VM 에서는 CPU 전용 휠을 쓰는 편이 낫다:

    pip install torch --index-url https://download.pytorch.org/whl/cpu

⚠️ 이것을 `requirements.txt` 에 박지 않았다 — 색인 URL 을 고정하면 GPU 환경에서
  잘못된 휠이 깔린다. **설치 스크립트가 환경 변수로 고르게** 한다(`AFS_TORCH_CPU=1`).

### 3. 프런트 API 주소는 **same-origin** 으로

개발에서는 `VITE_API_BASE_URL` 이 `127.0.0.1:8080` 을 가리킨다. 배포에서는 **비워서**
same-origin 으로 만든다 — 도메인이 바뀔 때마다 프런트를 다시 빌드하지 않기 위해서다.

⚠️⚠️ **셸 환경변수로는 안 된다.** `VITE_API_BASE_URL= npm run build` 로 넘겨도 Vite 는
  그것을 «설정 안 함» 으로 보고 소스 기본값을 번들에 박는다 — 실측으로 확인했다.
  `.env.production` 에 **빈 값으로 적어야** 「설정된 빈 값」이 된다. `install.sh` 가 한다.

⚠️ 그리고 API 주소는 `src/lib/api.ts` **한 곳**에서만 정한다. 여섯 파일이 각자
  `|| 'http://127.0.0.1:8080'` 을 선언하고 있었고, 그래서 한 곳을 고쳐도 나머지가
  개발 주소를 박았다(2026-08-23 실측).

### 4. 배포 대상은 **허용목록**이다 (WEB-0)

`data/`, `.env`, 원장 아카이브, 시험 오염 백업은 **배포에 들어가지 않는다.**
`update.sh` 가 `git archive` 로 추적된 파일만 내보낸다 — 작업 디렉터리를 통째로
복사하지 않는다.

## 순서

    ① VM 준비        Ubuntu 22.04+, sudo, 도메인 A 레코드
    ② install.sh     의존성 · venv · 프런트 빌드 · systemd 등록
    ③ .env 작성      `/opt/afs/data/.env` (템플릿은 저장소의 `.env.example`)
    ④ Caddy          `Caddyfile` 의 도메인을 실제 값으로
    ⑤ check.sh       헬스 · 첫 화면 · 주요 라우트
    ⑥ backup.sh      시연 전 기준선 백업
