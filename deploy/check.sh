#!/usr/bin/env bash
# [WEB-1/4] 배포 점검 — **「떴다」와 「된다」를 가른다.**
#
# ⚠️ 프로세스가 살아 있는 것은 서비스가 되는 것이 아니다. 헬스·첫 화면·주요 라우트를
#   각각 확인하고, 실패를 **하나씩** 말한다(뭉치면 무엇을 고칠지 모른다).
set -uo pipefail

BASE="${AFS_BASE:-http://127.0.0.1:${AFS_PORT:-8080}}"
APP="${AFS_APP:-/opt/afs/app}"
fail=0

check() {
    local what="$1" url="$2" want="$3"
    local code
    # ⚠️ `|| echo 000` 을 붙이면 curl 이 이미 찍은 `000` 뒤에 하나 더 붙어 `000000` 이
    #   된다 — 「기대 200」 옆의 그 값이 무엇인지 아무도 못 읽는다. 실측으로 잡았다.
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$url") || true
    [ -n "$code" ] || code=000
    if [ "$code" = "$want" ]; then
        printf '  ✓ %-34s %s\n' "$what" "$code"
    else
        printf '  ✕ %-34s %s (기대 %s)\n' "$what" "$code" "$want"
        fail=1
    fi
}

printf '\n▸ 서버\n'
check "헬스" "$BASE/api/v1/health" 200
# ★ 인증이 필요한 라우트는 **401 이 정상**이다. 200 이면 통제가 빠진 것이다.
check "인증 필요 라우트(401 이어야 함)" "$BASE/api/v1/calculation/readiness" 401

printf '\n▸ 프런트 빌드 산출물\n'
if [ -f "$APP/frontend/dist/index.html" ]; then
    printf '  ✓ dist/index.html\n'
    # ⚠️⚠️ **한 문자열만 찾지 않는다.** 처음에 `127.0.0.1:8080` 만 찾았더니, 개발자
    #   `.env` 가 `localhost:8080` 을 넣은 번들을 «깨끗하다» 고 답했다 — 내가 만든
    #   검사기가 거짓 초록을 냈다. 개발 주소는 여러 모양으로 온다.
    #
    # ★ 배포 도메인이 박히는 것은 허용이다(계획이 «도메인 또는 same-origin» 이라 한다).
    #   막는 것은 **개발자 기계를 가리키는 주소**다.
    hits=$(grep -roE 'https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:[0-9]+)?' \
             "$APP/frontend/dist/assets" 2>/dev/null | sort -u | head -5)
    if [ -n "$hits" ]; then
        printf '  ✕ 번들에 개발용 주소가 박혀 있습니다:\n'
        printf '      %s\n' $hits
        printf '      → frontend/.env.production 에 VITE_API_BASE_URL= (빈 값)을 넣고 다시 빌드하십시오.\n'
        printf '      ⚠️ 셸 변수로는 안 됩니다 — Vite 가 «설정 안 함» 으로 봅니다.\n'
        fail=1
    else
        printf '  ✓ 번들에 개발용 주소 없음\n'
    fi
else
    printf '  ✕ dist/index.html 이 없습니다 — 프런트를 빌드하지 않았습니다.\n'
    fail=1
fi

printf '\n▸ 데이터 경계\n'
# ⚠️ 개발 체크아웃에서는 이 셋이 **항상** 실체 디렉터리다 — 거기서 실패로 세면 검사기가
#   늑대 소년이 되고, 늘 빨간 검사는 아무도 안 본다. 배포 배치일 때만 강제한다.
if [ -n "${AFS_ROOT:-}" ]; then
    for d in data projects output; do
        if [ -L "$APP/$d" ]; then
            printf '  ✓ %s → %s\n' "$d" "$(readlink -f "$APP/$d")"
        else
            # ⚠️ 링크가 아니면 배포가 데이터를 지운다.
            printf '  ✕ %s 가 링크가 아닙니다 — 배포가 데이터를 지웁니다.\n' "$d"
            fail=1
        fi
    done
else
    printf '  · AFS_ROOT 가 없어 배포 배치가 아닙니다 — 데이터 경계는 서버에서 확인하십시오.\n'
fi

printf '\n'
[ "$fail" -eq 0 ] && printf '점검 통과\n' || printf '점검 실패 — 위 ✕ 를 보십시오.\n'
exit "$fail"
