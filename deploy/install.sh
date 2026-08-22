#!/usr/bin/env bash
# [WEB-1] 빈 Ubuntu 에서 AI Factory Studio 를 세운다.
#
# ⚠️ 이 스크립트는 **멱등**이어야 한다. 배포는 실패하고 다시 돌린다 — 두 번째 실행이
#   첫 번째와 다르면 그 차이가 원인 불명의 사고가 된다.
set -euo pipefail

APP_USER="${AFS_USER:-afs}"
ROOT="${AFS_ROOT:-/opt/afs}"
APP="$ROOT/app"
DATA="$ROOT/data"
PORT="${AFS_PORT:-8080}"
REPO="${AFS_REPO:-}"

say() { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31m✕ %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "root 로 실행하십시오(sudo)."

say "① 시스템 패키지"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# ⚠️ `python3-venv` 를 빠뜨리면 venv 생성이 «ensurepip 없음» 으로 죽는다 — Ubuntu 에서만
#   나는 실패라 로컬에서는 보이지 않는다.
apt-get install -y -qq python3 python3-venv python3-dev build-essential \
    ca-certificates curl git sqlite3

say "② Node.js (프런트 빌드용)"
if ! command -v node >/dev/null 2>&1; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y -qq nodejs
fi
node --version

say "③ 계정과 디렉터리"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
# ★★★ 코드와 데이터를 **다른 디렉터리**에 둔다. 한곳에 두면 배포가 데이터를 지운다.
mkdir -p "$APP" "$DATA"/{data,projects,output,backups}
chown -R "$APP_USER:$APP_USER" "$ROOT"

if [ -n "$REPO" ] && [ ! -d "$APP/.git" ]; then
    say "④ 코드 내려받기"
    sudo -u "$APP_USER" git clone "$REPO" "$APP"
fi
[ -f "$APP/main.py" ] || die "$APP 에 코드가 없습니다. AFS_REPO 를 주거나 코드를 먼저 두십시오."

say "⑤ 데이터 디렉터리 연결"
# ⚠️ 릴리스가 바뀌어도 데이터는 남아야 한다 — 링크로 잇는다.
for d in data projects output; do
    if [ -d "$APP/$d" ] && [ ! -L "$APP/$d" ]; then
        # 기존 실체 디렉터리가 있으면 **지우지 않고** 옮긴다.
        cp -an "$APP/$d/." "$DATA/$d/" 2>/dev/null || true
        mv "$APP/$d" "$APP/$d.replaced.$(date +%s)"
    fi
    ln -sfn "$DATA/$d" "$APP/$d"
done
ln -sfn "$DATA/.env" "$APP/.env"

say "⑥ Python venv"
sudo -u "$APP_USER" python3 -m venv "$APP/venv"
sudo -u "$APP_USER" "$APP/venv/bin/pip" install --upgrade -q pip wheel
if [ "${AFS_TORCH_CPU:-1}" = "1" ]; then
    # ★ 데모 VM 에서는 CPU 전용 휠을 쓴다 — CUDA 휠은 2GB 넘게 크고 GPU 도 없다.
    #   ⚠️ requirements.txt 에 색인 URL 을 박지 않는다(GPU 환경에서 잘못된 휠이 깔린다).
    say "   torch CPU 전용 휠"
    sudo -u "$APP_USER" "$APP/venv/bin/pip" install -q \
        torch --index-url https://download.pytorch.org/whl/cpu
fi
sudo -u "$APP_USER" "$APP/venv/bin/pip" install -q -r "$APP/requirements.txt"

say "⑦ 프런트 빌드"
# ★★★ API 주소를 **비워서** same-origin 으로 만든다 — 도메인이 바뀌어도 다시 빌드하지
#   않는다. 개발 기본값(127.0.0.1:8080)이 배포본에 박히면 브라우저가 자기 PC 를 부른다.
cd "$APP/frontend"
sudo -u "$APP_USER" npm ci --no-audit --no-fund
# ⚠️⚠️ **셸 환경변수로는 안 된다.** `VITE_API_BASE_URL=` 를 env 로 넘겨도 Vite 는 그것을
#   «설정 안 함» 으로 보고 소스 기본값(127.0.0.1:8080)을 번들에 박는다 — 실측으로 확인했다.
#   `.env.production` 에 **빈 값으로 적어야** 「설정된 빈 값」이 된다.
echo "VITE_API_BASE_URL=" | sudo -u "$APP_USER" tee .env.production >/dev/null
sudo -u "$APP_USER" npm run build
cd "$APP"

say "⑧ systemd"
sed -e "s|@APP@|$APP|g" -e "s|@USER@|$APP_USER|g" -e "s|@PORT@|$PORT|g" \
    "$APP/deploy/afs.service" > /etc/systemd/system/afs.service
systemctl daemon-reload
systemctl enable --now afs.service

say "⑨ 확인"
sleep 3
"$APP/deploy/check.sh" || die "점검에 실패했습니다 — journalctl -u afs -n 50 을 보십시오."
say "완료. .env 를 $DATA/.env 에 채우고 Caddy 를 설정하십시오."
