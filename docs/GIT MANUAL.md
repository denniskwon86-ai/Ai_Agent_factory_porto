# Git 형상관리 매뉴얼
## Gemini 다중 에이전트 자동화 파이프라인 프로젝트 전용

---

## 1. 초기 세팅 (프로젝트 시작 시 1회만)

```powershell
cd gemini_agent_team

# 1. Git 초기화
git init

# 2. .gitignore 생성 (API 키 노출 방지 - add보다 반드시 먼저!)
# 아래 내용을 .gitignore 파일로 저장
```

**.gitignore 파일 내용:**
```
.env
__pycache__/
*.pyc
.venv/
outputs/
.langgraph/
```

```powershell
# 3. 첫 커밋
git add .
git commit -m "init: 프로젝트 초기 구조 세팅"

# 4. 브랜치 구조 생성
git checkout -b dev
```

---

## 2. 브랜치 전략

### 브랜치 구조도
```
main                  ← 최종 검증 완료본만 보관
 └── dev              ← 작업 베이스 (항상 안전한 상태 유지)
      ├── agent/tech-lead
      ├── agent/fe-dev
      ├── agent/be-dev
      ├── agent/reviewer
      └── agent/qa
```

### 브랜치 운영 규칙
| 브랜치 | 용도 | 규칙 |
|---|---|---|
| `main` | 완성본 보관 | dev에서 검증 후에만 merge |
| `dev` | 작업 베이스 | 항상 동작하는 상태 유지 |
| `agent/[이름]` | 에이전트별 작업 | AI 작업 단위로 생성/삭제 |

### 새 에이전트 작업 시작
```powershell
# dev 기준으로 새 브랜치 생성
git checkout dev
git checkout -b agent/tech-lead
```

### 작업 완료 후 dev에 병합
```powershell
git checkout dev
git merge agent/tech-lead
git branch -d agent/tech-lead    # 병합 완료된 브랜치 삭제
```

---

## 3. AI 협업 커밋 습관

### 핵심 원칙
> AI한테 코드 받고 **동작 확인될 때마다 즉시 커밋**.
> 커밋하지 않은 코드는 언제든 날아갈 수 있다.

### 커밋 메시지 규칙
```powershell
# AI가 생성한 코드
git commit -m "feat: harness 컨텍스트 압축 기능 추가 (AI 생성)"

# AI 코드를 직접 수정한 경우
git commit -m "fix: harness 델타 업데이트 버그 수정 (직접 수정)"

# 스킬 문서 추가
git commit -m "docs: tech-lead 스킬 문서 추가"

# 파이프라인 연결
git commit -m "feat: tech-lead → fe-dev 노드 연결 완료"
```

> **(AI 생성)** 태그를 붙여두면 나중에 어느 부분이 AI 산출물인지 추적이 쉬워집니다.

### 작업 흐름 예시
```powershell
# 1. AI한테 코드 받음
# 2. VS Code에서 붙여넣기
# 3. 터미널에서 동작 확인
# 4. 문제 없으면 즉시 커밋
git add harness.py
git commit -m "feat: harness 모델 티어링 라우팅 추가 (AI 생성)"
# 5. 다음 작업 계속
```

---

## 4. GitHub 원격 백업

### 최초 1회 연결
```powershell
# GitHub에서 Private 레포 생성 후
git remote add origin https://github.com/[유저명]/gemini-agent-team.git
git push -u origin dev
```

### 주기적 백업 (작업 단위마다 권장)
```powershell
git push origin dev
```

### Recovery Log도 함께 관리
```powershell
# docs 폴더에 로그 보관
mkdir docs
# recovery_log_v2.4.md를 docs 폴더에 저장 후
git add docs/
git commit -m "docs: recovery log v2.4 업데이트"
git push origin dev
```

---

## 5. 복구 시나리오별 명령어

### 🔴 시나리오 1: AI가 준 코드가 망가짐

**파일 하나만 되돌리기 (가장 많이 쓰는 케이스)**
```powershell
git checkout harness.py
```

**마지막 커밋 전체 취소 (커밋 자체를 없앰)**
```powershell
git reset --hard HEAD~1
```

**마지막 커밋 취소하되 변경사항은 유지 (코드는 남기고 커밋만 취소)**
```powershell
git reset --soft HEAD~1
```

---

### 🔴 시나리오 2: 여러 번 작업 후 특정 시점으로 돌아가고 싶음

```powershell
# 1. 커밋 목록 확인
git log --oneline

# 출력 예시:
# a1b2c3d feat: qa 노드 연결 완료 (AI 생성)
# e4f5g6h feat: reviewer 노드 연결 완료 (AI 생성)
# i7j8k9l feat: harness 델타 업데이트 추가 (AI 생성)  ← 이 시점으로 돌아가고 싶다면

# 2. 해당 시점으로 이동 (코드 확인용 - 파일만 변경, 브랜치 유지)
git checkout i7j8k9l

# 3. 이 시점을 기준으로 새 브랜치 만들어 재작업
git checkout -b recovery/from-harness-delta
```

---

### 🔴 시나리오 3: 브랜치 작업이 완전히 꼬임

```powershell
# 꼬인 브랜치 버리고 dev 기준으로 재시작
git checkout dev
git branch -D agent/tech-lead     # 강제 삭제
git checkout -b agent/tech-lead   # 깨끗하게 재시작
```

---

### 🔴 시나리오 4: 실수로 .env 파일을 커밋해버림 (API 키 노출 위험)

```powershell
# 즉시 실행 - 커밋 기록에서 .env 제거
git rm --cached .env
git commit -m "fix: .env 파일 추적 제거"
git push origin dev

# GitHub에 이미 push했다면 API 키를 즉시 재발급 받아야 합니다.
# Google AI Studio: https://aistudio.google.com/app/apikey
```

---

### 🔴 시나리오 5: 제미나이가 잘못된 맥락으로 소스를 덮어씌움

```powershell
# 1. 현재 망가진 상태 확인
git diff

# 2. 어떤 파일이 바뀌었는지 확인
git status

# 3. 특정 파일만 선택적으로 복구
git checkout agent_graph.py
git checkout harness.py

# 4. 전부 다 되돌리기
git reset --hard HEAD
```

---

### 🔴 시나리오 6: 로컬 전체가 날아감 (PC 포맷 등)

```powershell
# GitHub에서 전체 복구
git clone https://github.com/[유저명]/gemini-agent-team.git
cd gemini-agent-team
git checkout dev

# .env 파일은 GitHub에 없으므로 직접 재생성
# (API 키는 별도로 메모해둘 것)
```

---

## 6. 자주 쓰는 명령어 치트시트

```powershell
# 현재 상태 확인
git status

# 변경 내용 확인
git diff

# 커밋 히스토리 확인
git log --oneline

# 브랜치 목록 확인
git branch

# 원격 저장소 동기화 (GitHub → 로컬)
git pull origin dev

# 스테이징 취소 (add 실수했을 때)
git restore --staged [파일명]
```

---

## 7. 권장 워크플로우 요약

```
새 에이전트 작업 시작
  │
  ├─ git checkout dev
  ├─ git checkout -b agent/[이름]
  │
  │  [AI와 작업 반복]
  ├─ 코드 받음 → 동작 확인 → git add → git commit
  ├─ 코드 받음 → 동작 확인 → git add → git commit
  │
  ├─ 완성되면 git checkout dev
  ├─ git merge agent/[이름]
  ├─ git push origin dev          ← GitHub 백업
  └─ git branch -d agent/[이름]  ← 브랜치 정리
```

---

## 8. 비상 연락망 (참고 링크)

- Git 공식 문서: https://git-scm.com/doc
- GitHub 레포 생성: https://github.com/new
- Google API 키 재발급: https://aistudio.google.com/app/apikey
- LangSmith 키 확인: https://smith.langchain.com/settings
