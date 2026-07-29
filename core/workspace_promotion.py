"""[§9 / §14 M3] 부서 워크스페이스 — 앱 공유 · 복제 · **승격 게이트**.

## 이 모듈의 중심은 승격 게이트다

§9.3 이 못박은 것: *"부서 앱을 전사 앱으로 승격할 때 **데이터 계약·보안·품질·소유자 승인**을
요구한다."* 네 가지가 전부 이미 만든 모듈에 있으므로, 이 게이트는 **체크박스가 아니라 실제
조회**여야 한다. 사람이 "확인했음"에 체크하는 게이트는 아무것도 막지 못한다.

| §9.3 요구 | 무엇을 조회하는가 | 통과 못 하면 |
|---|---|---|
| 데이터 계약 | 이 릴리스가 쓰는 자산의 **활성 계약 평가**(`data_contracts.evaluate`) | `breached` = 차단 / `unverifiable` = 차단(통과 아님) |
| 보안 | 자산 민감도·PII 와 **승격 대상 범위** 대조 | 전사 승격에 `restricted`·PII 포함 = 차단 |
| 품질 | 릴리스의 **게이트 결과**(`quality_telemetry`) | 실패 있음 = 차단 / 기록 없음 = 차단(확인 불가) |
| 소유자 승인 | 데이터 오너의 **명시적 승인 기록** | 없음 = 차단 |

## 지키는 것

1. **확인하지 못한 것을 통과라고 하지 않는다.** 계약 평가가 `unverifiable` 이거나 품질 기록이
   없으면 `blocked` 다. 이 저장소의 관통 원칙이고, 승격은 되돌리기 가장 어려운 행위다.
2. **어떤 자산을 쓰는지 모르면 보안·계약을 검사할 수 없다.** 릴리스↔자산 연결은
   계보(`data_lineage`)의 `asset -feeds-> release` 간선으로 선언한다. 간선이 없으면
   "안전"이 아니라 **`unverifiable`** 이다 — 모르는 것을 안전으로 치면 게이트가 장식이 된다.
3. **공유는 승격이 아니다.** 공유(`share`)는 읽기 범위를 넓히는 것이고 승격(`promote`)은
   전사 앱이 되는 것이다. 둘을 한 동작으로 묶으면 "잠깐 보여주려던 것"이 전사 자산이 된다.
4. **복제는 계보를 남긴다.** 포크한 앱이 원본과 무관해지면 원본 기준이 바뀔 때 무엇이
   영향받는지 알 수 없다(§14 M3 「영향 분석」의 근거).

LLM 0콜.
"""
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_DB_PATH = os.path.join("data", "workspace.db")

SHARE_MODES = ("read", "fork")          # 읽기 공유 / 복제 허용
PROMOTION_STATUS = ("draft", "requested", "approved", "rejected", "promoted")
#: 전사 승격에 허용되지 않는 민감도. 전사에 열면 되돌릴 수 없다.
_BLOCKED_FOR_ENTERPRISE = ("confidential", "restricted")

_DDL = """
CREATE TABLE IF NOT EXISTS workspace_shares (
    share_id     TEXT PRIMARY KEY,
    release_id   TEXT NOT NULL,
    from_scope   TEXT NOT NULL,
    to_scope     TEXT NOT NULL,
    mode         TEXT NOT NULL DEFAULT 'read',
    shared_by    TEXT NOT NULL,
    reason       TEXT DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'active',
    created_at   TEXT NOT NULL,
    revoked_at   TEXT DEFAULT '',
    UNIQUE (release_id, to_scope, mode)
);
CREATE INDEX IF NOT EXISTS idx_share_release ON workspace_shares(release_id, status);
CREATE INDEX IF NOT EXISTS idx_share_to ON workspace_shares(to_scope, status);

CREATE TABLE IF NOT EXISTS workspace_forks (
    fork_id       TEXT PRIMARY KEY,
    source_release_id TEXT NOT NULL,
    new_project_id    TEXT NOT NULL,
    owner_scope   TEXT NOT NULL,
    forked_by     TEXT NOT NULL,
    reason        TEXT DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fork_source ON workspace_forks(source_release_id);

CREATE TABLE IF NOT EXISTS release_promotions (
    promotion_id  TEXT PRIMARY KEY,
    release_id    TEXT NOT NULL,
    from_scope    TEXT NOT NULL,
    target_scope  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'draft',
    project_id    TEXT DEFAULT '',      -- 품질 기록 조회 키(릴리스 id 에서 추론하지 않는다)
    requested_by  TEXT DEFAULT '',
    requested_at  TEXT DEFAULT '',
    -- §9.3 「소유자 승인」 — 데이터 오너의 명시적 승인. 없으면 승격 불가.
    data_owner_approved_by TEXT DEFAULT '',
    data_owner_approved_at TEXT DEFAULT '',
    owner_note    TEXT DEFAULT '',
    gate_json     TEXT DEFAULT '',        -- 승격 시점의 게이트 판정 스냅샷
    promoted_by   TEXT DEFAULT '',
    promoted_at   TEXT DEFAULT '',
    rejected_reason TEXT DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE (release_id, target_scope)
);
CREATE INDEX IF NOT EXISTS idx_promo_status ON release_promotions(status, updated_at DESC);
"""


class WorkspaceError(ValueError):
    """검증/정책 위반 등 4xx 로 전달할 도메인 오류."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkspacePromotion:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or _DB_PATH
        self._lock = threading.RLock()
        self._initialized_path = ""
        with self._connect():
            pass

    def _connect(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
        except sqlite3.Error:
            pass
        # 경로가 런타임에 바뀌면 스키마가 없다(테스트 격리). shadow_mode 와 같은 처리.
        if self._initialized_path != self.db_path:
            conn.executescript(_DDL)
            conn.commit()
            self._initialized_path = self.db_path
        return conn

    # ── 공유 (승격이 아니다) ──────────────────────────────────────────────
    def share(self, release_id: str, from_scope: str, to_scope: str, shared_by: str,
              mode: str = "read", reason: str = "") -> dict:
        """다른 부서에 **읽기 또는 복제 권한**을 연다.

        ⚠️ 공유는 승격이 아니다. 승격은 전사 앱이 되는 것이고 공유는 지정한 조직만 본다.
          둘을 한 동작으로 묶으면 "잠깐 보여주려던 것"이 전사 자산이 된다."""
        if mode not in SHARE_MODES:
            raise WorkspaceError(f"mode 는 {list(SHARE_MODES)} 중 하나여야 합니다.")
        for nm, v in (("release_id", release_id), ("from_scope", from_scope),
                      ("to_scope", to_scope), ("shared_by", shared_by)):
            if not (v or "").strip():
                raise WorkspaceError(f"{nm} 은 필수입니다.")
        if from_scope == to_scope:
            raise WorkspaceError("같은 조직에는 공유할 수 없습니다(이미 소유 조직입니다).")
        sid = f"ws_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO workspace_shares(share_id,release_id,from_scope,to_scope,mode,"
                "shared_by,reason,status,created_at) VALUES(?,?,?,?,?,?,?,'active',?) "
                "ON CONFLICT(release_id,to_scope,mode) DO UPDATE SET status='active', "
                "shared_by=excluded.shared_by, reason=excluded.reason, revoked_at=''",
                (sid, release_id, from_scope, to_scope, mode, shared_by, reason, now))
            r = conn.execute("SELECT * FROM workspace_shares WHERE release_id=? AND to_scope=? "
                             "AND mode=?", (release_id, to_scope, mode)).fetchone()
        return dict(r)

    def revoke_share(self, share_id: str) -> bool:
        """공유 회수. 물리 삭제하지 않는다 — "누가 언제 무엇을 봤나"가 감사 대상이다."""
        with self._lock, self._connect() as conn:
            return conn.execute(
                "UPDATE workspace_shares SET status='revoked', revoked_at=? "
                "WHERE share_id=? AND status='active'", (_now(), share_id)).rowcount > 0

    def list_shares(self, release_id: str = "", to_scope: str = "",
                    include_revoked: bool = False) -> List[dict]:
        sql, params = "SELECT * FROM workspace_shares WHERE 1=1", []
        if not include_revoked:
            sql += " AND status='active'"
        for col, val in (("release_id", release_id), ("to_scope", to_scope)):
            if val:
                sql += f" AND {col}=?"
                params.append(val)
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(sql + " ORDER BY created_at DESC",
                                                  tuple(params)).fetchall()]

    def can_access(self, release_id: str, scope_node_id: str, owner_scope: str = "") -> dict:
        """이 조직이 이 릴리스를 볼 수 있는가 — 소유 · 공유 · 상위 상속 중 하나."""
        if owner_scope and scope_node_id == owner_scope:
            return {"allowed": True, "via": "owner"}
        for s in self.list_shares(release_id=release_id):
            if s["to_scope"] == scope_node_id:
                return {"allowed": True, "via": f"share:{s['mode']}", "share_id": s["share_id"]}
        return {"allowed": False, "via": "",
                "why": "소유 조직도 아니고 공유받지도 않았습니다."}

    # ── 복제 (계보를 남긴다) ──────────────────────────────────────────────
    def fork(self, source_release_id: str, new_project_id: str, owner_scope: str,
             forked_by: str, reason: str = "", lineage=None) -> dict:
        """릴리스를 복제해 새 프로젝트로 만든다. **계보를 반드시 남긴다.**

        ⚠️ 포크한 앱이 원본과 무관해지면 원본 기준이 바뀔 때 무엇이 영향받는지 알 수 없다
          (§14 M3 「영향 분석」의 근거). 그래서 계보 간선을 함께 만든다."""
        for nm, v in (("source_release_id", source_release_id),
                      ("new_project_id", new_project_id),
                      ("owner_scope", owner_scope), ("forked_by", forked_by)):
            if not (v or "").strip():
                raise WorkspaceError(f"{nm} 은 필수입니다.")
        fid = f"fk_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO workspace_forks(fork_id,source_release_id,new_project_id,"
                "owner_scope,forked_by,reason,created_at) VALUES(?,?,?,?,?,?,?)",
                (fid, source_release_id, new_project_id, owner_scope, forked_by, reason, now))
        edge_id = ""
        try:
            from core.data_lineage import DataLineage, data_lineage
            lin = lineage or data_lineage
            edge_id = lin.add_edge("release", source_release_id, "project", new_project_id,
                                   "derives_from", evidence_ref=f"fork by {forked_by}",
                                   origin="user")["edge_id"]
        except Exception as e:
            # 계보 기록 실패가 포크를 되돌리지는 않지만 조용히 넘기지 않는다.
            print(f"⚠️ [Workspace] 포크 계보 기록 실패(포크 자체는 완료): {e}")
        return {"fork_id": fid, "source_release_id": source_release_id,
                "new_project_id": new_project_id, "owner_scope": owner_scope,
                "lineage_edge_id": edge_id, "created_at": now,
                "note": "원본이 바뀌면 이 프로젝트가 영향을 받습니다(계보에 기록됨)."}

    def list_forks(self, source_release_id: str = "") -> List[dict]:
        sql, params = "SELECT * FROM workspace_forks", []
        if source_release_id:
            sql += " WHERE source_release_id=?"
            params.append(source_release_id)
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(sql + " ORDER BY created_at DESC",
                                                  tuple(params)).fetchall()]

    # ── 승격 게이트 (§9.3) — 이 모듈의 중심 ───────────────────────────────
    def evaluate_gate(self, release_id: str, target_scope: str = "enterprise",
                      catalog=None, contracts=None, lineage=None,
                      project_id: str = "") -> dict:
        """§9.3 네 가지를 **실제로 조회해** 판정한다.

        체크박스가 아니다. 사람이 "확인했음"에 체크하는 게이트는 아무것도 막지 못한다."""
        checks: List[dict] = []

        def add(key: str, state: str, why: str, action: str = ""):
            checks.append({"check": key, "state": state, "why": why,
                           "suggested_action": action})

        # 0) 이 릴리스가 어떤 자산을 쓰는가 — 모르면 계약·보안을 검사할 수 없다.
        assets: List[str] = []
        try:
            from core.data_lineage import data_lineage
            lin = lineage or data_lineage
            for e in lin.edges_of("release", release_id, "in"):
                if e["from_type"] == "asset":
                    assets.append(e["from_id"])
        except Exception as e:
            add("asset_linkage", "unverifiable",
                f"계보를 읽을 수 없습니다: {e}", "계보 저장소 상태를 확인하십시오.")

        if not assets:
            add("asset_linkage", "unverifiable",
                "이 릴리스가 어떤 데이터 자산을 쓰는지 등록돼 있지 않습니다.",
                "계보에 `asset -feeds-> release` 간선을 등록하십시오. "
                "모르는 것을 안전으로 치면 게이트가 장식이 됩니다.")
        else:
            add("asset_linkage", "pass", f"사용 자산 {len(assets)}건이 계보에 등록돼 있습니다.")

        # 1) 데이터 계약 (§9.3)
        from core.data_contract import data_contracts as _dc
        dc = contracts or _dc
        if not assets:
            add("data_contract", "unverifiable",
                "사용 자산을 모르므로 계약을 검사할 수 없습니다.",
                "먼저 자산 계보를 등록하십시오.")
        else:
            bad, unver, checked = [], [], 0
            for aid in assets:
                for c in dc.list(producer_asset_id=aid, status="active"):
                    checked += 1
                    ev = dc.evaluate(c["contract_id"], catalog=catalog)
                    if ev["state"] == "breached":
                        bad.append(f"{c['name']}({ev['state']})")
                    elif ev["state"] in ("unverifiable", "at_risk"):
                        unver.append(f"{c['name']}({ev['state']})")
            if bad:
                add("data_contract", "fail", f"위반 중인 계약이 있습니다: {', '.join(bad[:5])}",
                    "계약 위반을 해소한 뒤 다시 요청하십시오.")
            elif unver:
                add("data_contract", "unverifiable",
                    f"검증하지 못한 계약이 있습니다: {', '.join(unver[:5])}",
                    "품질 프로파일을 기록해 계약을 검증 가능하게 만드십시오 — "
                    "확인하지 못한 것은 통과가 아닙니다.")
            elif checked:
                add("data_contract", "pass", f"활성 계약 {checked}건이 모두 지켜지고 있습니다.")
            else:
                add("data_contract", "unverifiable",
                    "사용 자산에 활성 데이터 계약이 없습니다.",
                    "전사 승격은 소비자와의 약속을 전제로 합니다. 계약을 먼저 맺으십시오.")

        # 2) 보안 (§9.3) — 민감도·PII 대조
        from core.data_catalog import data_catalog as _cat
        cat = catalog or _cat
        if not assets:
            add("security", "unverifiable", "사용 자산을 모르므로 보안을 검사할 수 없습니다.")
        else:
            risky, pii_hits, missing = [], [], []
            for aid in assets:
                a = cat.get_asset(aid)
                if not a:
                    missing.append(aid)
                    continue
                if target_scope == "enterprise" and a["sensitivity"] in _BLOCKED_FOR_ENTERPRISE:
                    risky.append(f"{a['name']}({a['sensitivity']})")
                pii = [f["name"] for f in a["fields"]
                       if f["pii_classification"] in ("pii", "sensitive_pii")]
                if pii and target_scope == "enterprise":
                    pii_hits.append(f"{a['name']}: {', '.join(pii[:3])}")
            if missing:
                add("security", "unverifiable",
                    f"카탈로그에 없는 자산이 있습니다: {missing[:3]}",
                    "자산을 카탈로그에 등록하십시오.")
            elif risky or pii_hits:
                add("security", "fail",
                    ("전사 승격에 부적합: "
                     + ("민감도 " + "; ".join(risky) + " " if risky else "")
                     + ("PII " + "; ".join(pii_hits) if pii_hits else "")).strip(),
                    "범위를 좁혀 공유하거나(share), 민감 필드를 제외한 뷰를 만드십시오. "
                    "전사에 한 번 열면 되돌릴 수 없습니다.")
            else:
                add("security", "pass", "민감도·PII 기준으로 전사 공개에 문제가 없습니다.")

        # 3) 품질 (§9.3) — 릴리스의 게이트 결과
        #    프로젝트명은 명시로 받는다. `release_id` 에서 문자열로 추론하면 프로젝트명에
        #    밑줄이 있거나 명명 규칙이 바뀌는 순간 **조용히 남의 기록을 보거나 0건이 된다.**
        proj = (project_id or "").strip()
        if not proj:
            add("quality", "unverifiable",
                "품질 기록을 찾을 프로젝트를 알 수 없습니다(project_id 미지정).",
                "승격 신청 시 project_id 를 함께 넘기십시오 — 릴리스 id 에서 이름을 추론하면 "
                "명명 규칙이 바뀔 때 조용히 틀립니다.")
        else:
            try:
                from core import quality_telemetry as qt
                outcomes = qt.resolve_outcomes(qt.read_events(project=proj))
                if not outcomes:
                    add("quality", "unverifiable",
                        f"'{proj}' 의 품질 게이트 기록이 없습니다.",
                        "게이트 결과 없이 전사 승격하면 '검증했다'는 근거가 없습니다.")
                else:
                    failed = [o for o in outcomes
                              if str(o.get("pass_fail", "")).upper() == "FAIL"]
                    if failed:
                        add("quality", "fail",
                            f"실패한 품질 게이트가 {len(failed)}/{len(outcomes)}건 있습니다.",
                            "실패 원인을 해소하고 다시 게이트를 통과시키십시오.")
                    else:
                        add("quality", "pass", f"품질 게이트 {len(outcomes)}건 전부 통과했습니다.")
            except Exception as e:
                add("quality", "unverifiable", f"품질 기록을 읽을 수 없습니다: {e}")

        # 4) 소유자 승인 (§9.3)
        promo = self.get_promotion(release_id, target_scope)
        if promo and promo["data_owner_approved_by"]:
            add("data_owner_approval", "pass",
                f"데이터 오너 승인: {promo['data_owner_approved_by']}")
        else:
            add("data_owner_approval", "fail",
                "데이터 오너의 명시적 승인이 없습니다.",
                "데이터 오너가 `/promotions/{id}/owner-approve` 로 승인해야 합니다.")

        failed = [c for c in checks if c["state"] == "fail"]
        unver = [c for c in checks if c["state"] == "unverifiable"]
        return {
            "release_id": release_id, "target_scope": target_scope,
            "linked_assets": assets, "checks": checks,
            "failed": [c["check"] for c in failed],
            "unverifiable": [c["check"] for c in unver],
            # ★ unverifiable 도 차단이다. 확인 못 한 것을 통과로 두면 게이트가 장식이 된다.
            "promotable": not failed and not unver,
            "note": ("`unverifiable` 은 통과가 아니라 **확인하지 못한 것**이며 승격을 막습니다. "
                     "승격은 되돌리기 가장 어려운 행위라 '아마 괜찮다'로 넘기지 않습니다."),
        }

    # ── 승격 신청 · 오너 승인 · 승격 ──────────────────────────────────────
    def request_promotion(self, release_id: str, from_scope: str, requested_by: str,
                          target_scope: str = "enterprise", project_id: str = "") -> dict:
        for nm, v in (("release_id", release_id), ("from_scope", from_scope),
                      ("requested_by", requested_by)):
            if not (v or "").strip():
                raise WorkspaceError(f"{nm} 은 필수입니다.")
        pid = f"pr_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO release_promotions(promotion_id,release_id,from_scope,target_scope,"
                "status,project_id,requested_by,requested_at,created_at,updated_at) "
                "VALUES(?,?,?,?,'requested',?,?,?,?,?) "
                "ON CONFLICT(release_id,target_scope) DO UPDATE SET status='requested', "
                "project_id=excluded.project_id, requested_by=excluded.requested_by, "
                "requested_at=excluded.requested_at, rejected_reason='', "
                "updated_at=excluded.updated_at",
                (pid, release_id, from_scope, target_scope, project_id, requested_by,
                 now, now, now))
        return self.get_promotion(release_id, target_scope)

    def owner_approve(self, release_id: str, approved_by: str, target_scope: str = "enterprise",
                      note: str = "") -> dict:
        """§9.3 「소유자 승인」. 데이터 오너가 명시적으로 승인한다."""
        if not (approved_by or "").strip():
            raise WorkspaceError(
                "approved_by 는 필수입니다 — 누가 데이터 공개를 승인했는지 없으면 근거가 없습니다.")
        p = self.get_promotion(release_id, target_scope)
        if not p:
            raise WorkspaceError("승격 신청이 없습니다. 먼저 신청하십시오.")
        if p["status"] == "promoted":
            raise WorkspaceError("이미 승격된 릴리스입니다.")
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE release_promotions SET data_owner_approved_by=?, "
                "data_owner_approved_at=?, owner_note=?, status='approved', updated_at=? "
                "WHERE release_id=? AND target_scope=?",
                (approved_by, now, note, now, release_id, target_scope))
        return self.get_promotion(release_id, target_scope)

    def reject_promotion(self, release_id: str, rejected_by: str, reason: str,
                         target_scope: str = "enterprise") -> dict:
        if not (reason or "").strip():
            raise WorkspaceError("reason 은 필수입니다 — 사유 없는 반려는 신청자가 무엇을 "
                                 "고쳐야 할지 알 수 없습니다.")
        now = _now()
        with self._lock, self._connect() as conn:
            if not conn.execute(
                "UPDATE release_promotions SET status='rejected', rejected_reason=?, "
                "updated_at=? WHERE release_id=? AND target_scope=? AND status<>'promoted'",
                    (f"{rejected_by}: {reason}", now, release_id, target_scope)).rowcount:
                raise WorkspaceError("반려할 승격 신청이 없습니다(또는 이미 승격됨).")
        return self.get_promotion(release_id, target_scope)

    def promote(self, release_id: str, promoted_by: str, target_scope: str = "enterprise",
                catalog=None, contracts=None, lineage=None) -> dict:
        """전사 승격. **게이트를 통과하지 못하면 거절한다.**

        ⚠️ 강제 승격 우회로를 만들지 않았다. Shadow Mode 의 `allow_breached` 와 다른 판단인데,
          거기서는 "나쁜 후보를 알고 쓰는 것"이 정당할 수 있지만 여기서는 **데이터 계약 위반·
          PII 전사 공개**라 되돌릴 수 없기 때문이다. 예외가 필요하면 게이트 항목 자체를
          고쳐야 하고, 그 변경은 기록에 남는다."""
        if not (promoted_by or "").strip():
            raise WorkspaceError("promoted_by 는 필수입니다.")
        p = self.get_promotion(release_id, target_scope)
        if not p:
            raise WorkspaceError("승격 신청이 없습니다.")
        if p["status"] == "rejected":
            raise WorkspaceError(f"반려된 신청입니다: {p['rejected_reason']}")

        gate = self.evaluate_gate(release_id, target_scope, catalog, contracts, lineage,
                                  project_id=p.get("project_id", ""))
        if not gate["promotable"]:
            raise WorkspaceError(
                "승격 게이트를 통과하지 못했습니다 — 실패: "
                f"{gate['failed']} / 확인 불가: {gate['unverifiable']}. "
                "확인하지 못한 항목도 통과가 아닙니다(§9.3).")
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE release_promotions SET status='promoted', promoted_by=?, promoted_at=?, "
                "gate_json=?, updated_at=? WHERE release_id=? AND target_scope=?",
                (promoted_by, now, json.dumps(gate, ensure_ascii=False), now,
                 release_id, target_scope))
        return self.get_promotion(release_id, target_scope)

    def get_promotion(self, release_id: str, target_scope: str = "enterprise") -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM release_promotions WHERE release_id=? AND "
                             "target_scope=?", (release_id, target_scope)).fetchone()
        if not r:
            return None
        d = dict(r)
        try:
            d["gate_snapshot"] = json.loads(d.pop("gate_json") or "null")
        except Exception:
            d["gate_snapshot"] = None
        return d

    def list_promotions(self, status: str = "") -> List[dict]:
        sql, params = "SELECT release_id, target_scope FROM release_promotions", []
        if status:
            sql += " WHERE status=?"
            params.append(status)
        with self._connect() as conn:
            keys = [(r["release_id"], r["target_scope"])
                    for r in conn.execute(sql + " ORDER BY updated_at DESC",
                                          tuple(params)).fetchall()]
        return [self.get_promotion(a, b) for a, b in keys]


workspace = WorkspacePromotion()
