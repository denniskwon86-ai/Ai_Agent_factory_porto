"""[D-017 §9 P1] 범위형 자산 저장소 — 에이전트·스킬·워크플로우를 **조직이 소유한다.**

## 왜 필요한가 (설계 §2.1·§5.3)

지금 자산은 전역 파일 하나다. `agents_registry.json` 하나를 모두가 공유하고, `templates/*.json`
도 전역이며, `skills/*.md` 도 마찬가지다. 그래서 «누가 만들었는지 · 어느 조직 것인지 · 승인은
받았는지 · 언제부터 유효한지» 를 물을 수 없다. 한 사람이 저장하면 전 사용자의 파이프라인이
바뀌고, 바뀐 뒤에는 무엇이 바뀌었는지도 알 수 없다.

★ 이 모듈은 그 네 가지 질문에 답할 수 있는 저장소다: **소유 조직 · 공개 범위 · 승인 상태 ·
  버전**. 그리고 **버전을 덮어쓰지 않는다** — 새 버전을 쌓고 이전 것은 남긴다. 과거 산출물이
  «어떤 구성으로 만들어졌는가» 에 답하려면 그때의 정의가 그대로 있어야 한다.

## 파일 저장소를 지우지 않는다 (§5.3)

기존 `DEFAULT_REGISTRY`·`templates/*.json`·`skills/*.md` 는 **`SYSTEM` 원본으로 읽기 전용**
노출한다. 지우면 지금 도는 파이프라인이 멈춘다. 새로 만드는 것만 여기 들어온다.

## 가시성 판정을 저장과 함께 둔 이유

⚠️ 저장 계층과 판정 계층을 따로 만들면, 저장은 되는데 **아무도 못 보는** 자산이 생기거나
  반대로 **전부 보이는** 자산이 생긴다. 오늘 아침에 «판정 함수만 만들고 실행 경로에서 부르지
  않아» 통제가 장식이 된 사례를 이미 겪었다. 그래서 목록 조회에 가시성 필터를 **강제로** 건다
  (`list_assets` 는 `viewer_scopes` 를 **필수 인자**로 받는다 — 빼먹을 수 없게).

LLM 0콜.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, List, Optional

from core.master_data import _DB_PATH

# ── 자산 종류 ────────────────────────────────────────────────────────────────
KIND_AGENT = "agent"
KIND_SKILL = "skill"
KIND_WORKFLOW = "workflow"
KINDS = (KIND_AGENT, KIND_SKILL, KIND_WORKFLOW)

# ── 공개 범위 (설계 §5.1) ────────────────────────────────────────────────────
#: ⚠️ 넓은 순서로 적지 않는다 — 코드가 «크면 넓다» 로 비교하기 시작하면, 새 값을 끼워 넣을 때
#:   조용히 순서가 깨진다. 판정은 항상 명시적 분기로 한다.
VIS_PERSONAL = "PERSONAL"        # 만든 사람만
VIS_SCOPE = "SCOPE"              # 소유 조직만
VIS_DESCENDANTS = "DESCENDANTS"  # 소유 조직과 그 하위
VIS_ENTERPRISE = "ENTERPRISE"    # 전사
VIS_SYSTEM = "SYSTEM"            # 제품 기본(읽기 전용)
VISIBILITIES = (VIS_PERSONAL, VIS_SCOPE, VIS_DESCENDANTS, VIS_ENTERPRISE, VIS_SYSTEM)

# ── 상태 (설계 §5.1) ─────────────────────────────────────────────────────────
ST_DRAFT = "DRAFT"
ST_REVIEW = "REVIEW"
ST_APPROVED = "APPROVED"
ST_RETIRED = "RETIRED"
STATUSES = (ST_DRAFT, ST_REVIEW, ST_APPROVED, ST_RETIRED)

#: 실행에 쓸 수 있는 상태. **`DRAFT` 를 여기 넣지 않는다** — 초안이 도는 순간 검토는 형식이 된다.
RUNNABLE = (ST_APPROVED,)


class AssetError(ValueError):
    """정책 위반 — 라우트가 400 으로 바꾼다."""


class AssetNotFound(LookupError):
    """없거나 볼 수 없다 — 라우트가 **404** 로 바꾼다(존재를 알리지 않는다)."""


_DDL = """
CREATE TABLE IF NOT EXISTS agent_assets (
    asset_id       TEXT PRIMARY KEY,
    kind           TEXT NOT NULL,
    tenant_id      TEXT NOT NULL DEFAULT 'tenant_default',
    owner_scope_id TEXT NOT NULL DEFAULT '',
    entity_mode    TEXT NOT NULL DEFAULT 'REAL',
    visibility     TEXT NOT NULL DEFAULT 'PERSONAL',
    status         TEXT NOT NULL DEFAULT 'DRAFT',
    name_ko        TEXT NOT NULL DEFAULT '',
    purpose        TEXT NOT NULL DEFAULT '',
    current_version INTEGER NOT NULL DEFAULT 0,
    created_by     TEXT NOT NULL DEFAULT '',
    approved_by    TEXT NOT NULL DEFAULT '',
    effective_from TEXT NOT NULL DEFAULT '',
    effective_to   TEXT NOT NULL DEFAULT '',
    -- [D-017 §8.6] 전사 승격 «요청». ⚠️ 요청은 **가시성을 바꾸지 않는다** — 요청한 순간
    -- 남의 조직에 우리 자산이 노출되면 그것은 요청이 아니라 공개이고, 되돌릴 방법도 없다.
    -- 실제 승격(visibility=ENTERPRISE)은 AI 거버넌스 관리자가 확정할 때 일어난다.
    promotion_requested_by TEXT NOT NULL DEFAULT '',
    promotion_requested_at TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_asset_kind ON agent_assets(kind, status);
CREATE INDEX IF NOT EXISTS idx_asset_scope ON agent_assets(tenant_id, owner_scope_id);

-- ★ 버전은 **덮어쓰지 않고 쌓는다.** 과거 산출물이 "어떤 구성으로 만들어졌는가"에 답하려면
--   그때의 정의가 그대로 남아 있어야 한다.
CREATE TABLE IF NOT EXISTS agent_asset_versions (
    version_id     TEXT PRIMARY KEY,
    asset_id       TEXT NOT NULL,
    version_no     INTEGER NOT NULL,
    body_json      TEXT NOT NULL DEFAULT '{}',
    status         TEXT NOT NULL DEFAULT 'DRAFT',
    created_by     TEXT NOT NULL DEFAULT '',
    approved_by    TEXT NOT NULL DEFAULT '',
    supersedes_version INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    UNIQUE (asset_id, version_no)
);
CREATE INDEX IF NOT EXISTS idx_assetver ON agent_asset_versions(asset_id, version_no DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentAssetStore:
    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(_DDL)
            self._migrate(conn)
            conn.commit()

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """★★ 이미 있는 표에 컬럼을 더한다.

        ⚠️ `CREATE TABLE IF NOT EXISTS` 는 **이미 존재하는 표를 바꾸지 않는다.** DDL 만 고치면
          새 환경에서는 컬럼이 생기고 기존 환경에서는 조용히 없는 상태가 되며, 그 차이는
          「내 개발 PC 에서는 되는데 서버에서는 안 된다」로 나타난다 — 원인을 찾기 가장 어려운
          형태다. 그래서 실제 컬럼 목록을 읽어 없는 것만 더한다."""
        try:
            have = {r["name"] for r in conn.execute("PRAGMA table_info(agent_assets)")}
        except Exception:                                            # pragma: no cover
            return
        for col in ("promotion_requested_by", "promotion_requested_at"):
            if col not in have:
                conn.execute(
                    f"ALTER TABLE agent_assets ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")

    # ── 생성·개정 ─────────────────────────────────────────────────────────
    def create(self, kind: str, name_ko: str, body: Dict[str, Any], created_by: str,
               owner_scope_id: str = "", visibility: str = VIS_PERSONAL,
               purpose: str = "", tenant_id: str = "tenant_default",
               entity_mode: str = "REAL") -> Dict[str, Any]:
        """자산을 만든다. **항상 `DRAFT` 로 시작한다.**

        ⚠️ 만들자마자 `APPROVED` 로 두는 지름길을 만들지 않는다 — 한 번 만들면 그 경로로만
          만들어지고, 검토 단계는 아무도 지나지 않는 문이 된다."""
        if kind not in KINDS:
            raise AssetError(f"kind 는 {KINDS} 중 하나여야 합니다: {kind}")
        if not (name_ko or "").strip():
            raise AssetError("이름(name_ko)은 필수입니다.")
        if not (created_by or "").strip():
            raise AssetError("작성자가 필요합니다 — 누가 만들었는지 모르는 자산은 승인할 수 없습니다.")
        if visibility not in VISIBILITIES:
            raise AssetError(f"visibility 는 {VISIBILITIES} 중 하나여야 합니다: {visibility}")
        if visibility == VIS_SYSTEM:
            raise AssetError(
                "SYSTEM 은 제품 기본 자산의 표시이며 새로 만들 수 없습니다 — 복사해서 쓰십시오.")
        # ★ 개인 범위가 아니면 소유 조직이 있어야 한다. 없으면 «누구 것인가» 에 답할 수 없고,
        #   답할 수 없는 자산은 회수·폐기도 할 수 없다.
        if visibility != VIS_PERSONAL and not (owner_scope_id or "").strip():
            raise AssetError(
                f"{visibility} 공개에는 소유 조직(owner_scope_id)이 필요합니다 — 소유가 없으면 "
                f"나중에 «이 자산은 누구 책임인가» 에 답할 수 없습니다.")

        aid = f"as_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO agent_assets (asset_id, kind, tenant_id, owner_scope_id, entity_mode,"
                " visibility, status, name_ko, purpose, current_version, created_by, created_at,"
                " updated_at) VALUES (?,?,?,?,?,?,?,?,?,1,?,?,?)",
                (aid, kind, tenant_id, owner_scope_id.strip(), entity_mode, visibility, ST_DRAFT,
                 name_ko.strip(), (purpose or "").strip(), created_by, now, now))
            conn.execute(
                "INSERT INTO agent_asset_versions (version_id, asset_id, version_no, body_json,"
                " status, created_by, supersedes_version, created_at) VALUES (?,?,1,?,?,?,0,?)",
                (f"av_{uuid.uuid4().hex[:12]}", aid, json.dumps(body or {}, ensure_ascii=False),
                 ST_DRAFT, created_by, now))
            conn.commit()
        return self.get(aid)

    def revise(self, asset_id: str, body: Dict[str, Any], actor: str) -> Dict[str, Any]:
        """새 버전을 **쌓는다.** 기존 버전은 그대로 둔다.

        ★ 개정하면 상태가 `DRAFT` 로 내려간다 — 승인된 자산의 내용을 바꿔 놓고 승인 상태를
          유지하면, 그 승인은 **읽지 않은 문서에 대한 승인**이 된다."""
        a = self.get(asset_id)
        if a["visibility"] == VIS_SYSTEM:
            raise AssetError("제품 기본 자산은 수정할 수 없습니다 — 복사해서 쓰십시오.")
        if a["status"] == ST_RETIRED:
            raise AssetError("폐기된 자산은 개정할 수 없습니다 — 새로 만드십시오.")
        nxt = int(a["current_version"]) + 1
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO agent_asset_versions (version_id, asset_id, version_no, body_json,"
                " status, created_by, supersedes_version, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (f"av_{uuid.uuid4().hex[:12]}", asset_id, nxt,
                 json.dumps(body or {}, ensure_ascii=False), ST_DRAFT, actor,
                 int(a["current_version"]), now))
            conn.execute(
                "UPDATE agent_assets SET current_version=?, status=?, approved_by='', updated_at=?"
                " WHERE asset_id=?", (nxt, ST_DRAFT, now, asset_id))
            conn.commit()
        return self.get(asset_id)

    # ── 승인·폐기 ─────────────────────────────────────────────────────────
    #
    # ★★ 상태 규칙을 `assert_*` 로 **꺼내 둔다.** 라우트가 「이 사람이 지금 이걸 할 수 있는가」를
    #   목록에 실어 보내야 하는데(§8.6), 규칙이 실행 메서드 안에만 있으면 화면은 **눌러 봐야**
    #   안다. 그것이 설계 §10 이 금지한 「클릭 후에야 알게 되는 403」이다.
    #   ⚠️ 실제로 그 상태였다 — 계약 테스트가 「APPROVED 인데 사유가 비어 있다」를 잡았다.
    def assert_submittable(self, a: Dict[str, Any]) -> None:
        if a["status"] not in (ST_DRAFT, ST_REVIEW):
            raise AssetError(f"{a['status']} 상태에서는 검토를 요청할 수 없습니다.")

    def assert_approvable(self, a: Dict[str, Any]) -> None:
        if a["status"] != ST_REVIEW:
            raise AssetError(
                f"{a['status']} 상태에서는 승인할 수 없습니다 — 검토 요청 후에 승인합니다.")

    def assert_retirable(self, a: Dict[str, Any]) -> None:
        if a["visibility"] == VIS_SYSTEM:
            raise AssetError("제품 기본 자산은 폐기할 수 없습니다.")
        if a["status"] == ST_RETIRED:
            raise AssetError("이미 사용 중단된 자산입니다.")

    def submit(self, asset_id: str, actor: str) -> Dict[str, Any]:
        a = self.get(asset_id)
        self.assert_submittable(a)
        return self._set_status(asset_id, ST_REVIEW, actor, approved_by="")

    def approve(self, asset_id: str, actor: str) -> Dict[str, Any]:
        """승인. ⚠️ **자기가 만든 것을 자기가 승인하는 것을 막지 않는다** — 조직이 작으면 그것이
        정상이다. 대신 `approved_by` 를 남겨 **누가 승인했는지** 항상 답할 수 있게 한다."""
        a = self.get(asset_id)
        self.assert_approvable(a)
        return self._set_status(asset_id, ST_APPROVED, actor, approved_by=actor)

    def retire(self, asset_id: str, actor: str) -> Dict[str, Any]:
        """폐기 — **행을 지우지 않는다.** 과거 산출물이 이 자산을 가리키고 있다."""
        a = self.get(asset_id)
        self.assert_retirable(a)
        return self._set_status(asset_id, ST_RETIRED, actor, approved_by=a.get("approved_by", ""))

    # ── 전사 승격 (설계 §4.2 · §8.6) ──────────────────────────────────────
    def assert_promotable(self, a: Dict[str, Any]) -> None:
        """전사로 올릴 수 있는 상태인가. **요청과 확정이 같은 조건을 쓴다** — 요청은 되는데
        확정이 안 되면 요청한 사람은 영영 답을 못 받고, 그 이유는 아무데도 안 적힌다."""
        if a["visibility"] == VIS_ENTERPRISE:
            raise AssetError("이미 전사 공용 자산입니다.")
        if a["visibility"] == VIS_SYSTEM:
            raise AssetError("제품 기본 자산은 승격 대상이 아닙니다 — 복사해서 쓰십시오.")
        if a["visibility"] == VIS_PERSONAL:
            raise AssetError(
                "개인 초안은 곧바로 전사로 올릴 수 없습니다 — 조직 자산으로 만들어 조직 승인을 "
                "받은 뒤 승격을 요청하십시오.")
        if a["status"] != ST_APPROVED:
            raise AssetError(
                "조직 승인을 먼저 받아야 전사 승격을 요청할 수 있습니다 — 검토되지 않은 정의가 "
                "전사 목록에 오르면 그 목록을 아무도 믿지 않게 됩니다.")

    def assert_publishable_to_scope(self, a: Dict[str, Any]) -> None:
        """개인 초안을 **조직 자산으로** 올릴 수 있는 상태인가."""
        if a["visibility"] != VIS_PERSONAL:
            raise AssetError("개인 초안만 조직에 공개할 수 있습니다 — 이미 개인 범위가 아닙니다.")
        if a["status"] == ST_RETIRED:
            raise AssetError("사용 중단된 자산은 공개할 수 없습니다.")

    def publish_to_scope(self, asset_id: str, owner_scope_id: str, actor: str) -> Dict[str, Any]:
        """개인 초안을 **조직 자산으로 옮긴다.**

        ★★★ 이 경로가 없어서 화면이 «복사» 로 우회하고 있었고, 그 결과 **원본 개인 초안이 그대로
          남았다.** 같은 정의가 두 벌이 되면 어느 쪽이 정본인지 아무도 모르고, 한쪽만 고쳐진
          채로 승인된다 — `assert_writable_here` 머리말이 경고한 바로 그 상태다.

        ⚠️ **승인된 개인 자산은 `REVIEW` 로 되돌린다.** 개인 자산의 «승인» 은 자기가 자기 것을
          승인한 것이고, 조직 범위에서는 조직이 다시 답해야 한다(`promote` 와 같은 사상 —
          범위가 넓어지면 승인을 다시 받는다). 초안이면 그대로 초안이다: 아직 제출도 하지
          않은 것을 검토 대기로 만들면 승인자의 목록에 아무도 요청하지 않은 항목이 쌓인다."""
        a = self.get(asset_id)
        self.assert_publishable_to_scope(a)
        scope = (owner_scope_id or "").strip()
        if not scope:
            raise AssetError(
                "소유 조직이 필요합니다 — 소유가 없으면 나중에 «이 자산은 누구 책임인가» 에 "
                "답할 수 없고, 저장소 계약상 그 자산은 아무에게도 보이지 않습니다.")
        now = _now()
        reopen = a["status"] == ST_APPROVED
        with self._lock, self._connect() as conn:
            if reopen:
                conn.execute(
                    "UPDATE agent_assets SET visibility=?, owner_scope_id=?, status=?, "
                    "approved_by='', updated_at=? WHERE asset_id=?",
                    (VIS_SCOPE, scope, ST_REVIEW, now, asset_id))
                conn.execute(
                    "UPDATE agent_asset_versions SET status=?, approved_by='' WHERE asset_id=?"
                    " AND version_no=(SELECT current_version FROM agent_assets WHERE asset_id=?)",
                    (ST_REVIEW, asset_id, asset_id))
            else:
                conn.execute(
                    "UPDATE agent_assets SET visibility=?, owner_scope_id=?, updated_at=? "
                    "WHERE asset_id=?", (VIS_SCOPE, scope, now, asset_id))
            conn.commit()
        return self.get(asset_id)

    def request_promotion(self, asset_id: str, actor: str) -> Dict[str, Any]:
        """전사 승격을 **요청**한다.

        ⚠️⚠️ **가시성도 상태도 바꾸지 않는다.** 요청한 순간 자산이 전사에 보이면 그것은 요청이
          아니라 공개이고, 되돌릴 방법도 없다. 요청은 「답해 달라」는 표시일 뿐이다."""
        a = self.get(asset_id)
        self.assert_promotable(a)
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE agent_assets SET promotion_requested_by=?, "
                         "promotion_requested_at=?, updated_at=? WHERE asset_id=?",
                         (actor, now, now, asset_id))
            conn.commit()
        return self.get(asset_id)

    def promote(self, asset_id: str, actor: str) -> Dict[str, Any]:
        """전사 공용으로 올린다.

        ★★ **상태를 `REVIEW` 로 되돌린다.** 조직 승인과 전사 승인은 다른 자격이고(설계 §4.2),
          조직 승인만 받은 정의가 전사 자산으로 «승인됨» 이 되면 **아무도 검토하지 않은 전사
          자산**이 생긴다. 승격 뒤 한 번 더 승인해야 `approved_by` 에 전사 승인자가 남는다."""
        a = self.get(asset_id)
        self.assert_promotable(a)
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE agent_assets SET visibility=?, status=?, approved_by='', "
                "promotion_requested_by='', promotion_requested_at='', updated_at=? "
                "WHERE asset_id=?", (VIS_ENTERPRISE, ST_REVIEW, now, asset_id))
            conn.execute(
                "UPDATE agent_asset_versions SET status=?, approved_by='' WHERE asset_id=?"
                " AND version_no=(SELECT current_version FROM agent_assets WHERE asset_id=?)",
                (ST_REVIEW, asset_id, asset_id))
            conn.commit()
        return self.get(asset_id)

    def _set_status(self, asset_id: str, status: str, actor: str,
                    approved_by: str) -> Dict[str, Any]:
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE agent_assets SET status=?, approved_by=?, updated_at=?"
                         " WHERE asset_id=?", (status, approved_by, now, asset_id))
            conn.execute("UPDATE agent_asset_versions SET status=?, approved_by=?"
                         " WHERE asset_id=? AND version_no=(SELECT current_version FROM"
                         " agent_assets WHERE asset_id=?)",
                         (status, approved_by, asset_id, asset_id))
            conn.commit()
        return self.get(asset_id)

    # ── 조회 ──────────────────────────────────────────────────────────────
    def get(self, asset_id: str, version_no: int = 0) -> Dict[str, Any]:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM agent_assets WHERE asset_id=?", (asset_id,)).fetchone()
            if not r:
                raise AssetNotFound(asset_id)
            d = dict(r)
            v = version_no or d["current_version"]
            vr = conn.execute(
                "SELECT * FROM agent_asset_versions WHERE asset_id=? AND version_no=?",
                (asset_id, v)).fetchone()
            hist = conn.execute(
                "SELECT version_no, status, created_by, approved_by, created_at"
                " FROM agent_asset_versions WHERE asset_id=? ORDER BY version_no DESC",
                (asset_id,)).fetchall()
        d["body"] = json.loads(vr["body_json"]) if vr else {}
        d["version_no"] = v
        d["versions"] = [dict(h) for h in hist]
        d["runnable"] = d["status"] in RUNNABLE
        return d

    def list_assets(self, kind: str, viewer_scopes: Optional[FrozenSet[str]],
                    viewer_user_id: str, tenant_id: str = "",
                    status: str = "", include_retired: bool = False,
                    entity_mode: str = "") -> List[Dict[str, Any]]:
        """가시 범위 안의 자산 목록.

        ★★ `viewer_scopes` 는 **필수 인자**다(기본값을 주지 않는다). 기본값을 두면 어느 호출부가
          그것을 빼먹고, 그 경로만 조용히 전부 보이게 된다 — 오늘 아침 목록 API 에서 겪은 실패다.
        · `None` = 필터하지 않는다(강제 OFF·unrestricted). 호출부가 **의도적으로** 그렇게 준 것이다.
        · `frozenset()` = 아무 조직도 모른다 → **개인·전사·시스템 자산만** 보인다(fail-closed).

        ## ★★★ `entity_mode` — 가상에서 만든 것이 실제에 섞이지 않게 한다

        설계 §7.1 은 **가상 조직 = 실제 조직의 복제본**이라고 정했다. 그래서 방향이 다르다:

        · `REAL` 문맥 → **`REAL` 자산만** 보인다. 연습용으로 만든 정의가 실제 실행에 섞이면
          그것으로 만든 산출물이 실적이 된다.
        · `VIRTUAL` 문맥 → 그 모드 자산 **＋ `REAL` 자산**. 복제본이므로 원본을 볼 수 있어야
          하고, 그러지 않으면 가상 조직에서는 아무것도 못 만든다(복사할 원본이 없다).
        · `""`(미지정) → 필터하지 않는다. 호출부가 문맥을 모르는 경우다.

        ⚠️ 이것은 **요청 값 해석**이지 주체의 범위 계산이 아니다(`test_role_mode_matrix` 계약).
          모드로 «더 넓게» 볼 수 있는 방향은 REAL → VIRTUAL 하나뿐이고, 가상 문맥 진입 자체가
          별도 통제(설계 §4.3 capability token)를 지난다.
        """
        if kind not in KINDS:
            raise AssetError(f"kind 는 {KINDS} 중 하나여야 합니다: {kind}")
        sql = "SELECT * FROM agent_assets WHERE kind=?"
        params: List[Any] = [kind]
        if tenant_id:
            sql += " AND tenant_id=?"
            params.append(tenant_id)
        mode = (entity_mode or "").strip().upper()
        if mode == "REAL":
            sql += " AND entity_mode=?"
            params.append("REAL")
        elif mode:
            sql += " AND entity_mode IN (?, ?)"
            params.extend([mode, "REAL"])
        if status:
            sql += " AND status=?"
            params.append(status)
        elif not include_retired:
            sql += " AND status<>?"
            params.append(ST_RETIRED)
        sql += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]
        return [r for r in rows if self._visible(r, viewer_scopes, viewer_user_id)]

    @staticmethod
    def _visible(row: Dict[str, Any], viewer_scopes: Optional[FrozenSet[str]],
                 viewer_user_id: str) -> bool:
        """이 자산이 이 사람에게 보이는가.

        ⚠️ 판정을 **명시적 분기**로 쓴다. 공개 범위를 «넓기 순서» 숫자로 비교하기 시작하면,
          값을 하나 끼워 넣을 때 순서가 조용히 깨지고 그때는 아무도 알아채지 못한다."""
        vis = row.get("visibility")
        if vis == VIS_SYSTEM or vis == VIS_ENTERPRISE:
            return True                       # 제품 기본·전사 공개는 누구나 본다
        if vis == VIS_PERSONAL:
            return bool(viewer_user_id) and row.get("created_by") == viewer_user_id
        if viewer_scopes is None:
            return True                       # 필터하지 않기로 한 요청
        owner = (row.get("owner_scope_id") or "").strip()
        if not owner:
            # ★ 소유 조직을 모르는 조직 자산은 **보이지 않는다.** «모르니까 보여 준다» 는
            #   판단이 한 번 통과하면, 그 뒤로는 아무도 소유를 채우지 않는다.
            return False
        return owner in viewer_scopes

    def count_by_status(self, kind: str) -> Dict[str, int]:
        """운영 점검용. **`0` 과 «조회 못 함» 을 구분해야 하므로** 호출부가 실패를 삼키지 말 것."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) c FROM agent_assets WHERE kind=? GROUP BY status",
                (kind,)).fetchall()
        out = {s: 0 for s in STATUSES}
        for r in rows:
            out[r["status"]] = r["c"]
        return out


agent_assets = AgentAssetStore()
