#!/usr/bin/env bash
# [WEB-2] 백업에서 **별도 디렉터리로** 복구한다.
#
# ## ⚠️⚠️ 왜 «별도 디렉터리» 인가
#
# 운영 데이터 위에 바로 덮으면, 복구가 잘못됐을 때 **돌아갈 곳이 없다.** 먼저 옆에
# 펼쳐 놓고 확인한 뒤 사람이 바꿔 끼운다 — 이 스크립트는 **바꿔 끼우지 않는다.**
#
# ## ⚠️ 코드와 짝을 확인한다
#
# manifest 의 `code_sha` 와 지금 코드가 다르면 **경고하고 멈춘다.** 짝이 아닌 복구는
# 스키마가 맞지 않거나, 더 나쁘게는 맞는 척하면서 다른 값을 읽는다.
#
# 사용:
#     deploy/restore.sh <백업디렉터리> [복구할곳]
set -euo pipefail

SRC="${1:-}"
DEST="${2:-}"
APP="${AFS_APP:-/opt/afs/app}"

die() { printf '\n\033[1;31m✕ %s\033[0m\n' "$*" >&2; exit 1; }
say() { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }

[ -n "$SRC" ] || die "사용법: restore.sh <백업디렉터리> [복구할곳]"
[ -d "$SRC" ] || die "백업 디렉터리가 없습니다: $SRC"
[ -f "$SRC/manifest.json" ] || die "manifest.json 이 없습니다 — 무엇과 짝인 백업인지 알 수 없습니다."

DEST="${DEST:-$SRC/restored}"

say "① manifest"
cat "$SRC/manifest.json"

want_sha=$(grep -o '"code_sha": *"[^"]*"' "$SRC/manifest.json" | head -1 | sed 's/.*: *"//; s/"//')
now_sha=$(git -C "$APP" rev-parse HEAD 2>/dev/null || echo "unknown")
if [ "$want_sha" != "$now_sha" ]; then
    # ⚠️ 멈춘다. 「경고만 하고 진행」은 사람이 그 줄을 안 읽는다는 뜻이다.
    printf '\n\033[1;31m✕ 코드 SHA 가 다릅니다\033[0m\n'
    printf '   백업: %s\n   지금: %s\n' "$want_sha" "$now_sha"
    printf '   이 백업은 그 코드와 짝입니다. 먼저 코드를 그 시점으로 되돌리거나,\n'
    printf '   정말 진행하려면 AFS_RESTORE_FORCE=1 을 주십시오.\n'
    [ "${AFS_RESTORE_FORCE:-0}" = "1" ] || exit 1
    printf '   ⚠️ AFS_RESTORE_FORCE=1 — 짝이 아닌 복구를 강행합니다.\n'
fi

say "② 무결성 확인"
fail=0
while read -r name want; do
    [ -n "$name" ] || continue
    f="$SRC/$name"
    [ -f "$f" ] || { printf '  ✕ %s 없음\n' "$name"; fail=1; continue; }
    # ⚠️ 표준입력으로 넣는다 — 파일명 이스케이프(\\ 접두)를 피한다(backup.sh 와 짝).
    got=$(sha256sum < "$f" | cut -d' ' -f1)
    if [ "$got" = "$want" ]; then
        printf '  ✓ %s\n' "$name"
    else
        # ⚠️ 체크섬이 다르면 **복구하지 않는다.** 깨진 사본으로 복구하면 그 사실이
        #   한참 뒤 «데이터가 이상하다» 로만 드러난다.
        printf '  ✕ %s 체크섬 불일치\n' "$name"
        fail=1
    fi
done < <(grep -o '"file": *"[^"]*", *"sha256": *"[^"]*"' "$SRC/manifest.json" \
         | sed 's/"file": *"//; s/", *"sha256": *"/ /; s/"$//')
[ "$fail" -eq 0 ] || die "무결성 확인에 실패했습니다 — 복구하지 않습니다."

say "③ 별도 디렉터리로 펼치기"
mkdir -p "$DEST/data"
for f in "$SRC"/*.db; do
    [ -e "$f" ] || continue
    cp "$f" "$DEST/data/"
    printf '  ✓ %s\n' "$(basename "$f")"
done
[ -f "$SRC/projects.tar.gz" ] && tar -xzf "$SRC/projects.tar.gz" -C "$DEST" && printf '  ✓ projects\n'

say "④ 펼친 DB 가 실제로 열리는가"
for f in "$DEST"/data/*.db; do
    [ -e "$f" ] || continue
    n=$(sqlite3 "$f" "SELECT count(*) FROM sqlite_master WHERE type='table'" 2>&1) \
        || die "$(basename "$f") 를 열지 못했습니다: $n"
    printf '  ✓ %-28s 표 %s개\n' "$(basename "$f")" "$n"
done

printf '\n복구본: %s\n' "$DEST"
printf '⚠️ **바꿔 끼우지 않았습니다.** 확인한 뒤 사람이 %s/data 를 운영 자리로 옮기십시오.\n' "$DEST"
