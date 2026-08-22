#!/usr/bin/env bash
# [WEB-2] 배포 전 백업 — **코드 SHA 와 짝인 데이터**를 남긴다.
#
# ⚠️⚠️ 코드 롤백은 **그 코드와 짝인 데이터 백업**으로만 한다. 짝이 아니면 스키마가
#   맞지 않거나, 더 나쁘게는 맞는 척하면서 다른 값을 읽는다.
set -euo pipefail

ROOT="${AFS_ROOT:-/opt/afs}"
APP="${AFS_APP:-$ROOT/app}"
DATA="${AFS_DATA:-$ROOT/data}"
OUT="$DATA/backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"

sha=$(git -C "$APP" rev-parse HEAD 2>/dev/null || echo "unknown")

# ★ SQLite 는 **온라인 백업**으로 뜬다. 파일 복사는 쓰기 중인 DB 에서 깨진 사본을 만든다.
for db in "$DATA"/data/*.db; do
    [ -e "$db" ] || continue
    name=$(basename "$db")
    sqlite3 "$db" ".backup '$OUT/$name'"
    printf '  ✓ %s\n' "$name"
done

# 프로젝트 산출물
tar -czf "$OUT/projects.tar.gz" -C "$DATA" projects 2>/dev/null || true

# ★★★ manifest — 무엇과 짝인 백업인지 적는다. 없으면 롤백 때 짝을 못 찾는다.
{
    printf '{\n'
    printf '  "created_at": "%s",\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '  "code_sha": "%s",\n' "$sha"
    printf '  "databases": [\n'
    first=1
    for f in "$OUT"/*.db; do
        [ -e "$f" ] || continue
        [ $first -eq 0 ] && printf ',\n'
        printf '    {"file": "%s", "sha256": "%s"}' \
            "$(basename "$f")" "$(sha256sum "$f" | cut -d' ' -f1)"
        first=0
    done
    printf '\n  ]\n}\n'
} > "$OUT/manifest.json"

printf '\n백업 완료: %s\n' "$OUT"
printf '⚠️ 이 백업은 코드 %s 와 짝입니다 — 다른 코드로 복구하지 마십시오.\n' "${sha:0:12}"
