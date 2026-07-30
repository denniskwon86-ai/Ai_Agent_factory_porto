"""[§6.3 / §14 M1] 데이터 카탈로그 — 데이터 자산의 설명·위치·책임·갱신·민감도.

명세서 §6.1 은 카탈로그를 MDM 으로도 Graph RAG 로도 **대체 불가**라고 규정한다.
  · MDM(`master_records`)  = 전사 공통 '기준값' 그 자체
  · 카탈로그(여기)          = 그 값이 **어디에 있고 누가 책임지며 얼마나 자주 갱신되나**

## 왜 크로스워크와 따로 만들지 않았나

`external_schemas(system_id, entity, field)`(M2 연계 계약)와 `data_assets`/`data_asset_fields`
(거버넌스)는 **같은 물리 대상을 다른 목적으로 기술**한다. 병렬로 만들면 같은 테이블이 두 벌로
등록되고, 그건 2026-07-29 에 기준정보에서 실제로 겪은 문제다(`BOM-FG-CATHODE-001` ↔
`M2-BOM-FG-CATHODE-001`). 그래서 카탈로그는 크로스워크 **위에 얹는 계층**이고, 필드는
`sync_from_crosswalk()` 로 **단방향 임포트**한다(`origin='crosswalk'`).

## 이 모듈이 지키는 것

1. **소유자 없는 자산은 '미지정'이 아니라 결함이다.** §6.1 의 카탈로그 정의가 '책임'을 포함한다.
   소유자를 비워도 등록은 되지만 `governance_gaps()` 에 잡힌다 — 막으면 등록 자체를 안 한다.
2. **PII 가 있는데 민감도가 낮으면 자동으로 올리지 않고 불일치로 표시한다.** 조용히 바꾸면 왜
   바뀌었는지 아무도 모르고, 사람이 검토하지 않게 된다(품질 점검·중복 탐지와 같은 원칙).
3. **LLM 0콜.** §6.4 가 "LLM 은 후보 검색·설명에만" 이라고 못박았고, 등록·매칭 확정은 결정론이다.
"""
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.master_data import MasterData, MasterDataError, master_data

ASSET_TYPES = ("table", "file", "api", "report", "topic", "dashboard")
SENSITIVITY = ("public", "internal", "confidential", "restricted")
_SENS_RANK = {s: i for i, s in enumerate(SENSITIVITY)}
PII_CLASSES = ("none", "pii", "sensitive_pii")
REFRESH_CADENCES = ("realtime", "hourly", "daily", "weekly", "monthly", "quarterly", "adhoc")
QUALITY_METHODS = ("measured", "declared", "computed")

# 최신성 판정 기준(시간). `adhoc` 은 기대 주기 자체가 없으므로 판정 대상이 아니다 —
#   임의의 숫자를 넣으면 근거 없는 '오래됨' 경고가 뜬다.
_CADENCE_HOURS = {"realtime": 1, "hourly": 2, "daily": 30, "weekly": 8 * 24,
                  "monthly": 35 * 24, "quarterly": 100 * 24, "adhoc": None}

# PII 가 있으면 최소 이 등급이어야 한다. 자동 상향하지 않고 불일치로만 표시한다.
_PII_MIN_SENSITIVITY = {"pii": "confidential", "sensitive_pii": "restricted"}


class DataCatalogError(ValueError):
    """검증/충돌 등 4xx 로 전달할 도메인 오류."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", " ", (s or "").lower()).strip()


class DataCatalog:
    def __init__(self, md: MasterData = None):
        # 크로스워크와 같은 판단 — 스키마·연결은 M1 소유를 재사용하고 여기서는 로직만 담당한다.
        self.md = md or master_data

    def _connect(self):
        return self.md._connect()

    # ── 자산 ──────────────────────────────────────────────────────────────
    def create_asset(self, name: str, asset_type: str = "table", system_id: str = "",
                     entity: str = "", location: str = "", owner_dept_id: str = "",
                     owner_user_id: str = "", sensitivity: str = "internal",
                     refresh_cadence: str = "", description: str = "",
                     origin: str = "user", asset_id: str = "",
                     tenant_id: str = "tenant_default", enterprise_scope_id: str = "",
                     entity_mode: str = "REAL") -> dict:
        if not (name or "").strip():
            raise DataCatalogError("name 은 필수입니다.")
        if asset_type not in ASSET_TYPES:
            raise DataCatalogError(f"asset_type 은 {list(ASSET_TYPES)} 중 하나여야 합니다.")
        if sensitivity not in SENSITIVITY:
            raise DataCatalogError(f"sensitivity 는 {list(SENSITIVITY)} 중 하나여야 합니다.")
        if refresh_cadence and refresh_cadence not in REFRESH_CADENCES:
            raise DataCatalogError(f"refresh_cadence 는 {list(REFRESH_CADENCES)} 중 하나여야 합니다.")
        if bool(system_id) != bool(entity):
            # 반쪽 링크는 조인도 안 되고 중복 방지 인덱스도 안 걸린다 — 조용히 두면 나중에
            #   같은 엔터티가 두 자산으로 등록된다.
            raise DataCatalogError("system_id 와 entity 는 함께 지정해야 합니다(외부 엔터티 링크).")

        aid = asset_id or f"da_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self.md._lock, self._connect() as conn:
            # 폐기된 자산은 충돌로 보지 않는다 — 그러면 한 번 폐기한 테이블을 영원히 다시
            #   등록할 수 없다(실측으로 확인한 결함).
            if system_id and conn.execute(
                    "SELECT asset_id FROM data_assets "
                    "WHERE system_id=? AND entity=? AND status='active'",
                    (system_id, entity)).fetchone():
                raise DataCatalogError(
                    f"이미 등록된 외부 엔터티입니다: {system_id}.{entity}. "
                    f"중복 자산을 만들지 말고 기존 자산을 수정하십시오.")
            conn.execute(
                "INSERT INTO data_assets(asset_id,name,asset_type,system_id,entity,location,"
                "owner_dept_id,owner_user_id,sensitivity,refresh_cadence,last_refreshed_at,"
                "description,status,origin,tenant_id,enterprise_scope_id,entity_mode,"
                "created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,'',?,'active',?,?,?,?,?,?)",
                (aid, name.strip(), asset_type, system_id, entity, location, owner_dept_id,
                 owner_user_id, sensitivity, refresh_cadence, description, origin,
                 tenant_id or "tenant_default", enterprise_scope_id, entity_mode or "REAL",
                 now, now))
        return self.get_asset(aid)

    def update_asset(self, asset_id: str, **fields) -> dict:
        allowed = {"name", "asset_type", "location", "owner_dept_id", "owner_user_id",
                   "sensitivity", "refresh_cadence", "last_refreshed_at", "description", "status"}
        sets, params = [], []
        for k, v in fields.items():
            if v is None:
                continue
            if k not in allowed:
                raise DataCatalogError(f"수정할 수 없는 항목입니다: {k}")
            if k == "sensitivity" and v not in SENSITIVITY:
                raise DataCatalogError(f"sensitivity 는 {list(SENSITIVITY)} 중 하나여야 합니다.")
            if k == "asset_type" and v not in ASSET_TYPES:
                raise DataCatalogError(f"asset_type 은 {list(ASSET_TYPES)} 중 하나여야 합니다.")
            if k == "refresh_cadence" and v and v not in REFRESH_CADENCES:
                raise DataCatalogError(f"refresh_cadence 는 {list(REFRESH_CADENCES)} 중 하나여야 합니다.")
            sets.append(f"{k}=?")
            params.append(v)
        if not sets:
            return self.get_asset(asset_id)
        params += [_now(), asset_id]
        with self.md._lock, self._connect() as conn:
            cur = conn.execute(
                f"UPDATE data_assets SET {', '.join(sets)}, updated_at=? WHERE asset_id=?", params)
            if not cur.rowcount:
                raise DataCatalogError(f"존재하지 않는 자산입니다: {asset_id}")
        return self.get_asset(asset_id)

    def get_asset(self, asset_id: str, with_fields: bool = True) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM data_assets WHERE asset_id=?", (asset_id,)).fetchone()
            if not row:
                return None
            out = dict(row)
            if with_fields:
                out["fields"] = [dict(r) for r in conn.execute(
                    "SELECT * FROM data_asset_fields WHERE asset_id=? ORDER BY name",
                    (asset_id,)).fetchall()]
        return out

    def list_assets(self, owner_dept_id: str = "", sensitivity: str = "",
                    system_id: str = "", include_inactive: bool = False,
                    scope_node_id: str = "", tenant_id: str = "",
                    entity_mode: str = "REAL",
                    # [§6-2] 등급이 낮으면 제목만 남기고 내용을 가린다(빈 값 = 가리지 않는다)
                    viewer_clearance: str = "") -> List[dict]:
        """[ECM E2] `scope_node_id` 를 주면 그 조직에 보이는 자산만 돌려준다.

        판정은 `enterprise_context.scoping` 한 곳에서만 한다 — 같은 규칙을 모듈마다 복제하면
        반드시 어긋난다(이 프로젝트에서 겪은 유형)."""
        sql = "SELECT * FROM data_assets WHERE 1=1"
        params: List[Any] = []
        if not include_inactive:
            sql += " AND status='active'"
        for col, val in (("owner_dept_id", owner_dept_id), ("sensitivity", sensitivity),
                         ("system_id", system_id)):
            if val:
                sql += f" AND {col}=?"
                params.append(val)
        sql += " ORDER BY name"
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]
        # 등급만 주어진 호출도 처리한다 — 범위 없이 등급만 거는 화면이 있다.
        if not (scope_node_id or viewer_clearance):
            return rows
        from core.enterprise_context.scoping import filter_visible
        return filter_visible(rows, scope_node_id, tenant_id, entity_mode,
                              viewer_clearance=viewer_clearance)

    def retire_asset(self, asset_id: str) -> bool:
        """소프트 삭제 — 어떤 앱·보고서가 이 자산을 썼는지가 계보의 근거라 지우지 않는다."""
        with self.md._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE data_assets SET status='retired', updated_at=? "
                "WHERE asset_id=? AND status='active'", (_now(), asset_id))
            return cur.rowcount > 0

    # ── 필드 ──────────────────────────────────────────────────────────────
    def upsert_field(self, asset_id: str, name: str, logical_type: str = None,
                     term_id: str = None, master_code: str = None,
                     pii_classification: str = None, is_key: bool = None,
                     description: str = None, origin: str = "user") -> dict:
        """필드 등록/수정.

        ⚠️ `origin='crosswalk'` 인 필드의 **스키마 속성(logical_type·is_key)은 바꿀 수 없다.**
          바꿔도 다음 동기화에서 되돌아가므로, 되돌아가는 편집을 허용하면 사용자는 이유를 모른 채
          같은 수정을 반복한다. 거버넌스 속성(term_id·master_code·pii·description)은 편집 가능하다."""
        if not (name or "").strip():
            raise DataCatalogError("필드 name 은 필수입니다.")
        if pii_classification is not None and pii_classification not in PII_CLASSES:
            raise DataCatalogError(f"pii_classification 은 {list(PII_CLASSES)} 중 하나여야 합니다.")
        now = _now()
        with self.md._lock, self._connect() as conn:
            if not conn.execute("SELECT 1 FROM data_assets WHERE asset_id=?",
                                (asset_id,)).fetchone():
                raise DataCatalogError(f"존재하지 않는 자산입니다: {asset_id}")
            cur = conn.execute(
                "SELECT * FROM data_asset_fields WHERE asset_id=? AND name=?",
                (asset_id, name)).fetchone()
            if cur is None:
                conn.execute(
                    "INSERT INTO data_asset_fields(asset_id,name,logical_type,term_id,master_code,"
                    "pii_classification,is_key,description,origin,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (asset_id, name, logical_type or "", term_id or "", master_code or "",
                     pii_classification or "none", 1 if is_key else 0, description or "",
                     origin, now))
            else:
                locked = cur["origin"] == "crosswalk" and origin != "crosswalk"
                if locked and (logical_type is not None or is_key is not None):
                    raise DataCatalogError(
                        f"'{name}' 은 연계 스키마에서 가져온 필드라 타입·키 여부를 여기서 바꿀 수 "
                        f"없습니다(다음 동기화에서 되돌아갑니다). 원천 시스템 스키마를 고치거나 "
                        f"거버넌스 속성(용어·기준정보·PII)만 수정하십시오.")
                sets, params = [], []
                for col, val in (("logical_type", logical_type), ("term_id", term_id),
                                 ("master_code", master_code),
                                 ("pii_classification", pii_classification),
                                 ("description", description)):
                    if val is not None:
                        sets.append(f"{col}=?")
                        params.append(val)
                if is_key is not None:
                    sets.append("is_key=?")
                    params.append(1 if is_key else 0)
                if origin == "crosswalk":
                    sets.append("origin=?")
                    params.append(origin)
                if sets:
                    params += [now, asset_id, name]
                    conn.execute(f"UPDATE data_asset_fields SET {', '.join(sets)}, updated_at=? "
                                 f"WHERE asset_id=? AND name=?", params)
        return self.get_asset(asset_id)

    # ── 크로스워크 임포트 ─────────────────────────────────────────────────
    def sync_from_crosswalk(self, system_id: str, owner_dept_id: str = "",
                            sensitivity: str = "internal") -> dict:
        """연계 시스템의 스키마를 카탈로그 자산으로 **단방향 임포트**한다(멱등).

        엔터티 하나가 자산 하나가 된다. 이미 링크된 자산이 있으면 새로 만들지 않고 필드만
        맞춘다 — 이것이 없으면 동기화할 때마다 같은 테이블이 새 자산으로 쌓인다."""
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM external_systems WHERE system_id=?",
                                (system_id,)).fetchone():
                raise DataCatalogError(f"등록되지 않은 연계 시스템입니다: {system_id}")
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM external_schemas WHERE system_id=? ORDER BY entity, field",
                (system_id,)).fetchall()]

        report = {"system_id": system_id, "assets_created": [], "assets_reused": [],
                  "assets_reactivated": [], "fields_upserted": 0, "entities": 0}
        by_entity: Dict[str, List[dict]] = {}
        for r in rows:
            by_entity.setdefault(r["entity"], []).append(r)
        report["entities"] = len(by_entity)

        for entity, fields in by_entity.items():
            with self._connect() as conn:
                exist = conn.execute(
                    "SELECT asset_id, status FROM data_assets WHERE system_id=? AND entity=?",
                    (system_id, entity)).fetchone()
            if exist:
                aid = exist["asset_id"]
                if exist["status"] != "active":
                    # 원천에 다시 나타났다 = 카탈로그에 되살아난 것이다. 폐기 상태로 두면
                    #   목록에 안 보이는 자산에 필드만 써넣고 성공했다고 보고하게 된다.
                    self.update_asset(aid, status="active")
                    report["assets_reactivated"].append(aid)
                else:
                    report["assets_reused"].append(aid)
            else:
                aid = self.create_asset(
                    name=f"{system_id}.{entity}", asset_type="table", system_id=system_id,
                    entity=entity, location=f"{system_id}:{entity}",
                    owner_dept_id=owner_dept_id, sensitivity=sensitivity,
                    origin="crosswalk")["asset_id"]
                report["assets_created"].append(aid)
            for f in fields:
                self.upsert_field(aid, f["field"], logical_type=f.get("field_type") or "",
                                  master_code=f.get("mapped_type") or None,
                                  is_key=bool(f.get("is_key")), origin="crosswalk")
                report["fields_upserted"] += 1
        report["note"] = ("연계 스키마 → 카탈로그 **단방향** 임포트입니다. 가져온 필드의 타입·키 "
                          "여부는 카탈로그에서 수정할 수 없습니다(원천에서 고치십시오).")
        return report

    # ── 거버넌스 점검 ─────────────────────────────────────────────────────
    def governance_gaps(self, scope_node_id: str = "", tenant_id: str = "",
                        entity_mode: str = "REAL") -> List[dict]:
        """카탈로그가 '책임·갱신·민감도'를 담지 못한 지점.

        ⚠️ 자동으로 채우지 않는다. 소유자를 시스템이 추측해 넣으면 **아무도 책임지지 않는 자산이
          책임자가 있는 것처럼 보인다** — 없는 것보다 나쁘다."""
        gaps: List[dict] = []
        for a in self.list_assets(scope_node_id=scope_node_id, tenant_id=tenant_id,
                                 entity_mode=entity_mode):
            aid, nm = a["asset_id"], a["name"]
            if not (a["owner_dept_id"] or a["owner_user_id"]):
                gaps.append({"kind": "no_owner", "severity": "high", "asset_id": aid, "asset": nm,
                             "why": "책임자가 없다. 품질 문제·접근 요청이 발생해도 갈 곳이 없다.",
                             "suggested_action": "소유 부서 또는 담당자를 지정하십시오."})
            if not a["refresh_cadence"]:
                gaps.append({"kind": "no_refresh_cadence", "severity": "medium", "asset_id": aid,
                             "asset": nm,
                             "why": "갱신주기가 없으면 이 데이터가 최신인지 판단할 근거가 없다.",
                             "suggested_action": "갱신주기를 지정하거나 adhoc 으로 명시하십시오."})
            fields = self.get_asset(aid)["fields"]
            if not fields:
                gaps.append({"kind": "no_fields", "severity": "medium", "asset_id": aid,
                             "asset": nm,
                             "why": "필드가 없으면 업무 용어와 매칭할 수 없다(§6.4).",
                             "suggested_action": "필드를 등록하거나 연계 스키마에서 동기화하십시오."})
            worst = max((f["pii_classification"] for f in fields),
                        key=lambda p: list(PII_CLASSES).index(p) if p in PII_CLASSES else 0,
                        default="none")
            need = _PII_MIN_SENSITIVITY.get(worst)
            if need and _SENS_RANK[a["sensitivity"]] < _SENS_RANK[need]:
                pii_fields = [f["name"] for f in fields if f["pii_classification"] == worst]
                gaps.append({
                    "kind": "sensitivity_below_pii", "severity": "high", "asset_id": aid,
                    "asset": nm,
                    "why": (f"'{worst}' 필드({', '.join(pii_fields[:5])})가 있는데 자산 민감도가 "
                            f"'{a['sensitivity']}' 다. 최소 '{need}' 여야 한다."),
                    "suggested_action": (f"민감도를 '{need}' 이상으로 올리거나, PII 분류가 잘못됐다면 "
                                         f"필드 분류를 정정하십시오. **자동으로 올리지 않습니다** — "
                                         f"조용히 바뀌면 사람이 검토하지 않습니다."),
                })
        order = {"high": 0, "medium": 1, "low": 2}
        gaps.sort(key=lambda g: (order.get(g["severity"], 3), g["asset"], g["kind"]))
        return gaps

    # ── 품질 프로파일 (§6.3 / §6.1 "단순 LLM 평가 금지") ──────────────────
    def record_quality_profile(self, asset_id: str, method: str = "declared",
                               completeness: float = None, validity: float = None,
                               duplicate_rate: float = None, freshness: float = None,
                               row_count: int = None, evidence_ref: str = "",
                               measured_by: str = "", note: str = "",
                               measured_at: str = "") -> dict:
        """품질 측정치를 기록한다.

        ★ 이 함수의 핵심 인자는 점수가 아니라 `method` 다. §6.1 이 "단순 LLM 평가 금지"라고
          못박은 이유는, 읽지도 않은 데이터에 그럴듯한 점수가 붙으면 **"품질 확인함"으로 읽히기**
          때문이다. 그래서:
            · `measured` 는 `evidence_ref` 없이 기록할 수 없다 — 무엇을 실행해 얻은 값인가
            · 측정하지 않은 항목은 0.0 이 아니라 **NULL** 로 둔다(0점과 미측정은 다르다)
        """
        if method not in QUALITY_METHODS:
            raise DataCatalogError(f"method 는 {list(QUALITY_METHODS)} 중 하나여야 합니다.")
        if method == "measured" and not (evidence_ref or "").strip():
            raise DataCatalogError(
                "measured 프로파일에는 evidence_ref 가 필수입니다 — 무엇을 실행해 얻은 값인지 "
                "없으면 '측정했다'는 주장을 검증할 수 없습니다.")
        for nm, v in (("completeness", completeness), ("validity", validity),
                      ("duplicate_rate", duplicate_rate), ("freshness", freshness)):
            if v is not None and not (0.0 <= float(v) <= 1.0):
                raise DataCatalogError(f"{nm} 은 0.0~1.0 이어야 합니다.")
        if not self.get_asset(asset_id, with_fields=False):
            raise DataCatalogError(f"존재하지 않는 자산입니다: {asset_id}")

        pid = f"dqp_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self.md._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO data_quality_profiles(profile_id,asset_id,measured_at,method,"
                "completeness,validity,duplicate_rate,freshness,row_count,evidence_ref,"
                "measured_by,note,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, asset_id, measured_at or now, method, completeness, validity,
                 duplicate_rate, freshness, row_count, evidence_ref, measured_by, note, now))
        return self.latest_quality_profile(asset_id)

    def latest_quality_profile(self, asset_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM data_quality_profiles WHERE asset_id=? "
                "ORDER BY measured_at DESC, created_at DESC LIMIT 1", (asset_id,)).fetchone()
        return dict(row) if row else None

    def list_quality_profiles(self, asset_id: str, limit: int = 20) -> List[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM data_quality_profiles WHERE asset_id=? "
                "ORDER BY measured_at DESC, created_at DESC LIMIT ?",
                (asset_id, int(limit))).fetchall()]

    def assess_freshness(self, asset_id: str, now: str = "") -> dict:
        """최신성을 **계산한다**(추정하지 않는다).

        `last_refreshed_at` 과 `refresh_cadence` 만으로 결정론적으로 판정한다 — 이 둘은 우리가
        실제로 가진 사실이므로 계산에 근거가 있다. 둘 중 하나라도 없으면 'unknown' 이고,
        **unknown 을 'fresh' 로 낙관하지 않는다** — 모르는 것을 좋게 치면 §6.4 의 최신성 확인이
        형식만 남는다."""
        a = self.get_asset(asset_id, with_fields=False)
        if not a:
            raise DataCatalogError(f"존재하지 않는 자산입니다: {asset_id}")
        cadence, last = a["refresh_cadence"], a["last_refreshed_at"]
        if not cadence or not last:
            return {"asset_id": asset_id, "state": "unknown", "age_hours": None,
                    "allowed_hours": _CADENCE_HOURS.get(cadence),
                    "why": ("갱신주기 또는 마지막 갱신 시각이 없어 판정할 수 없다. "
                            "모르는 것을 최신으로 치지 않는다.")}
        allowed = _CADENCE_HOURS.get(cadence)
        if allowed is None:                       # adhoc — 기준 자체가 없다
            return {"asset_id": asset_id, "state": "unknown", "age_hours": None,
                    "allowed_hours": None,
                    "why": "갱신주기가 adhoc 이라 기대 주기가 없다. 최신성을 기계적으로 판정할 수 없다."}
        try:
            t_last = datetime.fromisoformat(last)
            t_now = datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
            if t_last.tzinfo is None:
                t_last = t_last.replace(tzinfo=timezone.utc)
            if t_now.tzinfo is None:
                t_now = t_now.replace(tzinfo=timezone.utc)
        except ValueError:
            return {"asset_id": asset_id, "state": "unknown", "age_hours": None,
                    "allowed_hours": allowed, "why": f"갱신 시각을 해석할 수 없다: {last}"}
        age = (t_now - t_last).total_seconds() / 3600.0
        # 주기의 2배를 넘기면 '지연'이 아니라 '오래됨'으로 본다 — 1배 초과는 흔한 지연이다.
        state = "fresh" if age <= allowed else ("late" if age <= allowed * 2 else "stale")
        return {"asset_id": asset_id, "state": state, "age_hours": round(age, 2),
                "allowed_hours": allowed,
                "why": f"마지막 갱신 후 {age:.1f}시간 경과, 기대 주기 {allowed}시간({cadence})."}

    # ── 검색 (§6.4 3단계 「데이터 카탈로그 후보 검색」) ────────────────────
    def search_assets(self, query: str, limit: int = 20, scope_node_id: str = "",
                      tenant_id: str = "", entity_mode: str = "REAL") -> List[dict]:
        """업무 용어로 후보 자산을 찾는다. **결정론적 문자열 매칭**(LLM 0콜).

        점수 근거를 함께 돌려준다 — 왜 이게 후보인지 모르면 데이터 오너가 확정할 수 없고,
        §6.4 는 최종 매칭 확정을 사람 또는 승인된 규칙의 몫으로 못박았다."""
        q = _norm(query)
        if not q:
            return []
        tokens = [t for t in q.split() if len(t) >= 2] or [q]
        out = []
        for a in self.list_assets(scope_node_id=scope_node_id, tenant_id=tenant_id,
                                  entity_mode=entity_mode):
            full = self.get_asset(a["asset_id"])
            hay_asset = _norm(f"{a['name']} {a['description']} {a['entity']} {a['location']}")
            score, why = 0, []
            for t in tokens:
                if t in hay_asset:
                    score += 3
                    why.append(f"자산명/설명에 '{t}'")
            matched_fields = []
            for f in full["fields"]:
                hay_f = _norm(f"{f['name']} {f['description']} {f['term_id']} {f['master_code']}")
                if any(t in hay_f for t in tokens):
                    score += 2
                    matched_fields.append(f["name"])
            if matched_fields:
                why.append(f"필드 일치: {', '.join(matched_fields[:5])}")
            if score:
                out.append({
                    "asset_id": a["asset_id"], "name": a["name"], "score": score,
                    "asset_type": a["asset_type"], "owner_dept_id": a["owner_dept_id"],
                    "sensitivity": a["sensitivity"], "refresh_cadence": a["refresh_cadence"],
                    "matched_fields": matched_fields, "why": why,
                    # §6.4 는 품질·최신성·권한 확인을 매칭의 일부로 규정한다. 후보만 던지고
                    #   이 정보를 빼면 오너가 확정 판단을 할 수 없다.
                    "governance_ready": bool(a["owner_dept_id"] or a["owner_user_id"])
                                        and bool(a["refresh_cadence"]),
                })
        out.sort(key=lambda r: (-r["score"], r["name"]))
        return out[:limit]


data_catalog = DataCatalog()
