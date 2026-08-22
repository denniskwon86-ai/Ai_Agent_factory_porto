#!/usr/bin/env bash
# [WEB-1/2] 코드 갱신 — **백업이 먼저다.**
#
# ⚠️ 배포 대상은 **허용목록**이다(WEB-0). 작업 디렉터리를 통째로 복사하지 않는다 —
#   `data/`·`.env`·원장 아카이브·시험 오염 백업이 딸려 간다.
set -euo pipefail

ROOT="${AFS_ROOT:-/opt/afs}"
APP="${AFS_APP:-$ROOT/app}"
REF="${1:-}"

say() { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }

say "① 배포 전 백업"
"$APP/deploy/backup.sh"

say "② 코드 갱신"
cd "$APP"
git fetch --all --prune
if [ -n "$REF" ]; then
    git checkout --detach "$REF"
else
    git pull --ff-only
fi
git rev-parse HEAD

say "③ 의존성"
./venv/bin/pip install -q -r requirements.txt

say "④ 프런트 빌드"
cd frontend
echo "VITE_API_BASE_URL=" > .env.production   # same-origin (셸 변수로는 안 된다)
npm ci --no-audit --no-fund && npm run build
cd ..

say "⑤ 재시작"
systemctl restart afs.service
sleep 3

say "⑥ 점검"
./deploy/check.sh
