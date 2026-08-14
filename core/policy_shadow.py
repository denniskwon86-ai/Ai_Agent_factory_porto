"""★★★ [G1-B P0 / B05] **이중 판정 관측과 전환 게이트** — 기존 판정을 강제하면서 신규 PDP 를
나란히 돌리고, 「전환해도 되는가」를 **표본으로** 판정한다.

교차검토 `[G1-B-P0-REVIEW-75]` 의 지시:

> 기존 `assert_release_*` 를 곧바로 제거하지 않는다. 신규 PDP 가 기존보다 동등하거나 더
> 엄격하다는 것이 **종단 부정 테스트로 입증된 뒤** 원자적으로 전환한다.

`tests/test_app_policy_equivalence.py` 는 **판정기 단위**로 그것을 증명했다. 그러나 단위
동등성은 «실제 요청에서도 같은 사실이 먹인다» 를 증명하지 못한다 — 이 저장소는 그 차이로
여러 번 다쳤다(「테스트가 실제 배선을 타지 않으면 그 초록은 거짓이다」).

## 세 가지 결과

| 결과 | 뜻 | 취급 |
|---|---|---|
| `match` | 두 판정이 같다 | 정상 |
| `stricter` | 기존 허용 · PDP 거부 | 예상된 강화. 세되 막지 않는다 — **사유가 예상 목록에 있어야** 한다 |
| `looser` | 기존 거부 · PDP 허용 | ★★★ **절대 있어서는 안 된다.** 전환하면 권한이 넓어지는 칸이다 |

## ⚠️ 관측이 동작을 바꾸지 않는다

- 강제하는 것은 **기존 판정**이다. PDP 결과는 기록만 한다.
- PDP 판정 중 예외가 나도 **요청을 죽이지 않는다** — 관측 장애가 기능 장애가 되면 안 된다.
  다만 그 실패를 **센다**(조용한 유실 금지).
- 기록 저장소가 죽어도 요청은 산다. 대신 표본이 남지 않으므로 **게이트가 닫힌 채로 있다**.

## ★★★ 왜 «어긋남 0» 만으로는 전환할 수 없는가 (교차검토 B05 지적)

    looser == 0 and error == 0 and total > 0

이 조건은 **읽기 요청 한 건**만 일치해도 참이 된다. 그러면 「전환해도 안전하다」가
「한 번 눌러 봤다」와 같은 말이 된다. 실제로 위험한 칸(만료된 증명 · 다른 앱 · 다른 조직 ·
문맥 불일치)은 **눌러 보지 않으면 표본이 아예 생기지 않는다** — 그리고 표본이 없는 것은
«안전하다» 가 아니라 **«모른다»** 다.

그래서 게이트는 **덮인 칸**을 요구한다(§`switch_gate`).

## ★★ 시나리오 라벨을 «부르는 쪽» 이 붙이지 않는다

「이번 요청은 다른-앱 시나리오다」를 호출자가 선언하게 두면, 그 라벨은 하니스가 자기
자신과 합의한 값이 된다. 대신 **PDP 가 낸 거부 사유**에서 시나리오를 읽는다 — 라벨을
만들려면 실제로 그 판정을 통과시켜야 한다.

## ⚠️ 무엇을 기록하지 않는가

- **데이터 내용**(payload·레코드 값)을 기록하지 않는다. 텔레메트리는 접근 통제의 관측이지
  업무 데이터의 사본이 아니다.
- **토큰 전문**을 기록하지 않는다.
- 사유는 **알려진 `DENY_*` 코드만** 저장한다. 모르는 문자열은 `UNKNOWN` 이 된다 —
  이것이 「예외 메시지에 값이 섞여 들어오는」 경로를 원천 차단한다(예외는 자주 입력값을
  그대로 문자열에 담는다).

LLM 0콜.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.app_policy import (ACTIONS, DENY_CONTEXT, DENY_MANIFEST_CAPABILITY, DENY_NO_SUBJECT,
                             DENY_PERSONAL, DENY_PRINCIPAL_BLOCKED, DENY_RETIRED, DENY_SCOPE,
                             DENY_TOKEN_ACTOR_MISMATCH, DENY_TOKEN_APP_MISMATCH,
                             DENY_TOKEN_CAPABILITY, DENY_TOKEN_CONTEXT_MISMATCH,
                             DENY_TOKEN_EXPIRED, DENY_TOKEN_MANIFEST_MISMATCH,
                             DENY_TOKEN_SCOPE_MISMATCH,
                             DENY_TOKEN_SESSION_MISMATCH, DENY_UNBOUND, DENY_UNIDENTIFIED,
                             DENY_UNKNOWN_ACTION)
from core.host_runtime_sdk import OPS
from core.paths import data_path

MATCH = "match"
STRICTER = "stricter"
LOOSER = "looser"
ERROR = "error"

#: 최근 어긋남 보관 개수(메모리). 전부 들고 있으면 장시간 운영에서 메모리를 먹는다.
_KEEP = 50

_DB_PATH = data_path("policy_shadow.db")

#: ★ 카나리 회차를 구분한다. 격리 카나리의 표본과 평상 트래픽을 섞어 세면 「그 시나리오를
#:   정말 눌러 봤는가」에 답할 수 없다.
_RUN_ENV = "AFS_SHADOW_RUN"


# ── 무엇을 기록해도 되는가 ────────────────────────────────────────────────
#
# ⚠️ 허용목록이다. 모르는 사유는 `UNKNOWN` 으로 접힌다 — 예외 메시지가 그대로 들어오는
#   경로를 없앤다(예외는 자주 입력값을 문자열에 담는다).
KNOWN_REASONS: Tuple[str, ...] = (
    DENY_UNIDENTIFIED, DENY_NO_SUBJECT, DENY_PRINCIPAL_BLOCKED,
    DENY_TOKEN_EXPIRED, DENY_TOKEN_ACTOR_MISMATCH, DENY_TOKEN_SESSION_MISMATCH,
    DENY_TOKEN_APP_MISMATCH, DENY_TOKEN_CONTEXT_MISMATCH, DENY_TOKEN_SCOPE_MISMATCH,
    DENY_TOKEN_CAPABILITY, DENY_MANIFEST_CAPABILITY, DENY_TOKEN_MANIFEST_MISMATCH,
    DENY_CONTEXT, DENY_UNBOUND, DENY_SCOPE, DENY_PERSONAL, DENY_RETIRED,
    DENY_UNKNOWN_ACTION,
)
UNKNOWN_REASON = "UNKNOWN"

#: 식별자류에 남길 수 있는 글자. 그 밖은 지운다 — 「사유 자리에 값이 들어오는」 것과 같은
#: 경로가 경로·주체 자리에도 있다.
_SAFE_CHARS = re.compile(r"[^0-9A-Za-z가-힣@._/{}:\- ]")

#: ★★★ **끊기지 않는 긴 문자열은 가린다.** 이 저장소의 비밀은 전부 그 모양이다 —
#:   앱 증명 `app_<urlsafe24>` · 세션 토큰 `token_urlsafe(32)`.
#:   반면 여기 정상적으로 실리는 식별자는 짧거나 구분자가 있다(`rel_x` · `ds_<hex12>` · 이메일).
#: ⚠️ 「토큰은 안 들어올 것이다」로 두지 않는다. 자리를 하나만 막으면 다음 사고는 다른 자리다.
_SECRET_RUN = re.compile(r"[A-Za-z0-9_\-]{24,}")
REDACTED = "«가림»"


def _scrub(value: Any, cap: int = 96) -> str:
    return _SECRET_RUN.sub(REDACTED, _SAFE_CHARS.sub("", str(value or ""))[:cap])


def _scrub_reason(reason: Any) -> str:
    """사유는 **알려진 코드만** 남는다."""
    r = str(reason or "")
    return r if r in KNOWN_REASONS else (UNKNOWN_REASON if r else "")


def _scrub_op(op: Any) -> str:
    """작업도 **닫힌 목록**이다. 게이트가 세는 이름이 자유 문자열이면 표본을 지어낼 수 있다."""
    o = str(op or "")
    return o if o in OPS else ""


# ── 전환 게이트가 요구하는 것 ─────────────────────────────────────────────
#
# ★★★ 여섯 작업 × 허용·거부 양쪽. 읽기만 눌러 보고 전환하면 쓰기 통제는 **한 번도 대조되지
#   않은 채** 새 판정기로 넘어간다.
REQUIRED_OPS: Tuple[str, ...] = tuple(OPS)

#: 부정 시나리오 → **그것을 증거하는 PDP 거부 사유**.
#: ⚠️ 라벨을 호출자가 붙이지 않는다. 이 사유를 내려면 실제로 그 판정을 통과시켜야 한다.
REQUIRED_SCENARIOS: Dict[str, Tuple[str, ...]] = {
    "만료된 증명": (DENY_TOKEN_EXPIRED,),
    "다른 세션에서 재사용": (DENY_TOKEN_SESSION_MISMATCH,),
    "다른 사용자의 증명": (DENY_TOKEN_ACTOR_MISMATCH,),
    "다른 앱의 데이터": (DENY_TOKEN_APP_MISMATCH,),
    "다른 조직 범위": (DENY_TOKEN_SCOPE_MISMATCH, DENY_SCOPE),
    "문맥 불일치": (DENY_TOKEN_CONTEXT_MISMATCH, DENY_CONTEXT),
}

#: **예상된 강화**의 사유. 여기 없는 사유로 강화가 나면 그것은 «설명되지 않은 강화» 이고,
#: 전환하면 **지금 되던 일이 안 되게 된다.** 권한 확대만 사고인 것이 아니다.
EXPLAINED_STRICTER: Tuple[str, ...] = (
    DENY_UNBOUND,               # D-014 — 범위 없는 자원은 비노출 (릴리스 판독 실패도 여기다)
    DENY_CONTEXT,               # 지금 고른 문맥과 자원 문맥이 다르다
    DENY_SCOPE,                 # 조직 권한 밖
    DENY_PRINCIPAL_BLOCKED,     # 계정 상태
    DENY_UNIDENTIFIED, DENY_NO_SUBJECT,
    DENY_RETIRED, DENY_PERSONAL,
    #: ★★★ [G1-B 3.5] **앱 증명 축은 예정된 강화다.** 런타임 경로(`/appdata/runtime/*`)에서
    #:   기존 판정은 사람만 보므로 허용하고, PDP 는 증명까지 본다 — 만료·다른 세션·다른 앱·
    #:   다른 조직·문맥 불일치가 전부 여기로 나온다. 그것이 이 전환의 **목적**이므로
    #:   「설명되지 않은 강화」로 세면 게이트가 영원히 닫힌다.
    DENY_TOKEN_EXPIRED, DENY_TOKEN_ACTOR_MISMATCH, DENY_TOKEN_SESSION_MISMATCH,
    DENY_TOKEN_APP_MISMATCH, DENY_TOKEN_CONTEXT_MISMATCH, DENY_TOKEN_SCOPE_MISMATCH,
    DENY_TOKEN_CAPABILITY, DENY_MANIFEST_CAPABILITY, DENY_TOKEN_MANIFEST_MISMATCH,
)
#: ⚠️⚠️ `UNKNOWN_REASON` 은 **일부러 넣지 않았다.** 새 거부 코드가 `KNOWN_REASONS` 에 등록되지
#:   않은 채 생기면 `UNKNOWN` 으로 저장되는데, 그것까지 «설명됨» 으로 두면 이 검사가 잡을 것이
#:   하나도 남지 않는다. 이 목록에 이름을 더하는 것은 **검토 결정**이다.
#: ★ 릴리스 판독 실패(`binding_state=INVALID`)는 `DENY_UNBOUND` 로 나온다 — 확인했다.

#: 게이트가 요구하는 최소 표본. 한두 건으로 「덮였다」고 말하지 않는다.
MIN_TOTAL = 24


_DDL = """
CREATE TABLE IF NOT EXISTS shadow_observations (
    obs_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TEXT NOT NULL,
    run_label   TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL,
    op          TEXT NOT NULL DEFAULT '',
    action      TEXT NOT NULL DEFAULT '',
    path        TEXT NOT NULL DEFAULT '',
    old         TEXT NOT NULL DEFAULT '',
    new         TEXT NOT NULL DEFAULT '',
    reason      TEXT NOT NULL DEFAULT '',
    actor       TEXT NOT NULL DEFAULT '',
    resource_id TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_shadow_kind ON shadow_observations(kind);
CREATE INDEX IF NOT EXISTS idx_shadow_run ON shadow_observations(run_label);
"""


class _ShadowObserver:
    """관측 + 전환 게이트.

    ⚠️ 메모리 계수와 영구 기록을 **둘 다** 둔다. 메모리는 지금 이 프로세스의 빠른 확인이고,
      게이트 판정은 **영구 기록**으로 한다 — 재시작하면 사라지는 근거로 전환을 결정하면,
      배포 직후 표본 0 인 상태가 「어긋남 0」으로 읽힌다."""

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._lock = threading.RLock()
        self._counts: Counter = Counter()
        self._recent: List[Dict[str, Any]] = []
        self.db_path = db_path
        self._ready = ""

    # ── 저장소 ────────────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        if self._ready == self.db_path:
            return
        with self._connect() as conn:
            conn.executescript(_DDL)
            conn.commit()
        self._ready = self.db_path

    def _persist(self, row: Dict[str, Any]) -> None:
        """⚠️ 실패해도 요청을 죽이지 않는다. 대신 표본이 남지 않아 **게이트가 닫힌 채** 있다 —
        「기록이 안 되니 그냥 전환」이 되지 않는 방향이다."""
        try:
            self._init_db()
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO shadow_observations (at, run_label, kind, op, action, path, "
                    "old, new, reason, actor, resource_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (row["at"], row["run_label"], row["kind"], row["op"], row["action"],
                     row["path"], row["old"], row["new"], row["reason"], row["actor"],
                     row["resource_id"]))
                conn.commit()
        except Exception:
            with self._lock:
                self._counts["persist_failed"] += 1

    # ── 관측 ──────────────────────────────────────────────────────────────
    def observe(self, *, path: str, action: str, old_allowed: bool,
                new_allowed: bool, new_reason: str = "",
                actor: str = "", resource_id: str = "", op: str = "") -> str:
        """한 요청의 두 판정을 기록하고 결과 종류를 돌려준다."""
        if old_allowed and new_allowed:
            kind = MATCH
        elif not old_allowed and not new_allowed:
            kind = MATCH
        elif old_allowed and not new_allowed:
            kind = STRICTER
        else:
            kind = LOOSER

        row = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "run_label": _scrub(os.environ.get(_RUN_ENV, ""), 48),
            "kind": kind,
            "op": _scrub_op(op),
            "action": _scrub(action, 16),
            "path": _scrub(path, 64),
            "old": "allow" if old_allowed else "deny",
            "new": "allow" if new_allowed else "deny",
            #: ★ 알려진 코드만 남는다 — 값이 사유 자리로 흘러드는 경로를 막는다.
            "reason": _scrub_reason(new_reason),
            "actor": _scrub(actor, 96),
            "resource_id": _scrub(resource_id, 96),
        }

        with self._lock:
            self._counts[kind] += 1
            if kind != MATCH:
                self._recent.append(dict(row))
                del self._recent[:-_KEEP]

        self._persist(row)

        if kind == LOOSER:
            # ★★★ 이것만은 감사에도 남긴다. 「전환하면 권한이 넓어진다」는 사실이
            #   프로세스 재시작으로 사라지면 안 된다.
            try:
                from core.enterprise_context import audit
                audit.record(event=audit.ACCESS_DENIED_SCOPE_MISMATCH,
                             resource_type="policy_shadow",
                             resource_id=row["resource_id"] or row["path"],
                             actor=row["actor"], outcome="denied",
                             reason="PDP 가 기존 판정보다 느슨하다 — 전환 금지",
                             detail=f"{row['path']} {row['action']} old=deny new=allow")
            except Exception:
                pass
        return kind

    def error(self, action: str = "", exc_type: str = "") -> None:
        """PDP 판정 자체가 실패했다. **요청은 죽이지 않되 세어서 드러낸다.**

        ★★★ 인자가 «자유 문장» 이 아니라 **행동 + 예외 종류**다. 예외는 자주 입력값을 그대로
          문자열에 담고(`ValueError(f"…{payload}…")`), 그러면 업무 데이터가 텔레메트리로
          흘러든다. 호출부에 「메시지는 넣지 마세요」라고 부탁하는 대신 **넣을 자리를 없앴다.**

        ⚠️ `exc_type` 은 영문자만 남는다 — 숫자·한글이 통과하면 그 자리로 값이 들어온다."""
        act = str(action or "").strip()
        kind_name = re.sub(r"[^A-Za-z]", "", str(exc_type or ""))[:40]
        row = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "run_label": _scrub(os.environ.get(_RUN_ENV, ""), 48),
            "kind": ERROR, "op": "", "action": act if act in ACTIONS else "",
            "path": kind_name, "old": "", "new": "", "reason": "", "actor": "",
            "resource_id": "",
        }
        with self._lock:
            self._counts[ERROR] += 1
            self._recent.append(dict(row))
            del self._recent[:-_KEEP]
        self._persist(row)

    # ── 집계 ──────────────────────────────────────────────────────────────
    def _rows(self, run_label: str = "") -> List[Dict[str, Any]]:
        try:
            self._init_db()
            with self._connect() as conn:
                if run_label:
                    cur = conn.execute(
                        "SELECT * FROM shadow_observations WHERE run_label=?", (run_label,))
                else:
                    cur = conn.execute("SELECT * FROM shadow_observations")
                return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []

    def stats(self, run_label: str = "") -> Dict[str, Any]:
        """지금 프로세스의 계수 + **영구 기록 기반 전환 게이트**."""
        with self._lock:
            c = dict(self._counts)
            recent = list(self._recent[-10:])
        gate = self.switch_gate(run_label)
        return {
            "total": gate["counts"]["total"],
            "match": gate["counts"]["match"],
            "stricter": gate["counts"]["stricter"],
            "looser": gate["counts"]["looser"],
            "error": gate["counts"]["error"],
            #: ★ 전환 가능 판정은 **여기 하나**로 읽는다 — 여러 숫자를 사람이 보고
            #:   해석하게 두면 판단이 갈린다. 다만 그 하나는 «어긋남 0» 이 아니라
            #:   **덮인 칸까지** 본다(§switch_gate).
            "safe_to_switch": gate["safe_to_switch"],
            "blockers": gate["blockers"],
            "in_process": {"total": sum(v for k, v in c.items() if k != "persist_failed"),
                           "persist_failed": c.get("persist_failed", 0)},
            "recent": recent,
        }

    def switch_gate(self, run_label: str = "") -> Dict[str, Any]:
        """**「전환해도 되는가」의 단일 판정.** 막는 이유를 사람이 읽을 문장으로 함께 준다.

        ★ 「안전하다」는 «어긋남이 없었다» 가 아니라 **«위험한 칸을 눌러 봤고 어긋나지
          않았다»** 여야 한다. 표본이 없는 칸은 안전한 것이 아니라 **모르는** 칸이다."""
        rows = self._rows(run_label)
        counts = {
            "total": len(rows),
            "match": sum(1 for r in rows if r["kind"] == MATCH),
            "stricter": sum(1 for r in rows if r["kind"] == STRICTER),
            "looser": sum(1 for r in rows if r["kind"] == LOOSER),
            "error": sum(1 for r in rows if r["kind"] == ERROR),
        }

        op_coverage: Dict[str, Dict[str, int]] = {
            op: {"allow": 0, "deny": 0} for op in REQUIRED_OPS}
        for r in rows:
            slot = op_coverage.get(r["op"])
            if slot is None or r["kind"] == ERROR:
                continue
            #: ★ 「기존이 무엇으로 판정했는가」가 아니라 **PDP 가 무엇을 답했는가**로 센다 —
            #:   전환 후에 실제로 쓰일 판정이 그쪽이기 때문이다.
            slot["allow" if r["new"] == "allow" else "deny"] += 1

        seen_reasons = {r["reason"] for r in rows if r["reason"]}
        scenario_coverage = {
            name: sum(1 for r in rows if r["reason"] in reasons)
            for name, reasons in REQUIRED_SCENARIOS.items()}

        unexplained = sorted({r["reason"] for r in rows
                              if r["kind"] == STRICTER and r["reason"] not in EXPLAINED_STRICTER})

        blockers: List[str] = []
        if counts["total"] < MIN_TOTAL:
            blockers.append(
                f"표본이 {counts['total']}건입니다(최소 {MIN_TOTAL}건). "
                f"«어긋남 0» 은 «눌러 보지 않았다» 와 구분되지 않습니다.")
        if counts["looser"]:
            blockers.append(
                f"PDP 가 기존보다 느슨한 칸이 {counts['looser']}건 있습니다 — "
                f"전환하면 그만큼 권한이 넓어집니다.")
        if counts["error"]:
            blockers.append(
                f"관측 자체가 {counts['error']}건 실패했습니다 — 그 요청들에서 두 판정이 "
                f"같았는지 아무도 모릅니다.")
        missing_ops = [op for op, s in op_coverage.items()
                       if s["allow"] == 0 or s["deny"] == 0]
        if missing_ops:
            blockers.append(
                "허용·거부 양쪽 표본이 없는 작업: " + ", ".join(missing_ops) +
                " — 눌러 보지 않은 통제는 전환 대상이 아닙니다.")
        missing_scn = [n for n, c in scenario_coverage.items() if c == 0]
        if missing_scn:
            blockers.append(
                "부정 시나리오 표본이 없습니다: " + ", ".join(missing_scn) +
                " — 이 칸들은 «안전» 이 아니라 «모름» 입니다.")
        if unexplained:
            blockers.append(
                "설명되지 않은 강화: " + ", ".join(unexplained) +
                " — 전환하면 지금 되던 일이 안 되게 됩니다(권한 확대만 사고가 아닙니다).")
        if self._counts.get("persist_failed"):
            blockers.append(
                f"관측 기록이 {self._counts['persist_failed']}건 저장되지 않았습니다 — "
                f"게이트가 보는 표본이 실제보다 적습니다.")

        return {
            "safe_to_switch": not blockers,
            "blockers": blockers,
            "counts": counts,
            "op_coverage": op_coverage,
            "scenario_coverage": scenario_coverage,
            "unexplained_stricter": unexplained,
            "reasons_seen": sorted(seen_reasons),
            "run_label": run_label,
        }

    def reset(self) -> None:
        """시험 전용. 운영에서 부르면 **관측 이력이 사라지고 게이트가 처음으로 돌아간다.**"""
        with self._lock:
            self._counts.clear()
            self._recent.clear()
        try:
            self._init_db()
            with self._connect() as conn:
                conn.execute("DELETE FROM shadow_observations")
                conn.commit()
        except Exception:
            pass


policy_shadow = _ShadowObserver()
