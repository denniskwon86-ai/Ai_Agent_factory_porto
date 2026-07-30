"""[§6.3 / §6.1] 데이터 계약 — "생산자가 소비자에게 무엇을 약속했고, 지금 지켜지고 있나".

§6.1: "시스템/앱 간 필드·형식·권한·SLA 약속 — **직접 DB 결합의 대안**".

## 이 모듈의 값어치는 저장이 아니라 검증에 있다

JSON 을 담아두는 것만으로는 계약이 아니다. 약속은 **지금 지켜지고 있는지 확인될 때** 비로소
직접 결합의 대안이 된다. 그래서 핵심은 `evaluate()` 이고, 이것이 매번 실제 카탈로그·품질
프로파일·최신성과 대조한다.

## 지키는 원칙

1. **확인하지 못한 것을 '지켜짐'이라고 하지 않는다.** 품질 프로파일이 없으면 `unverifiable`
   이지 `kept` 가 아니다. 이걸 통과로 처리하면 "계약 준수 중"이라는 거짓 안심이 생기고,
   그건 계약이 없는 것보다 나쁘다(품질·최신성 모듈과 같은 원칙).
2. **개정은 새 버전 행이다.** 덮어쓰면 소비자가 **어떤 약속을 보고 붙었는지** 사라지고,
   파기적 변경을 사후에 증명할 수 없다.
3. **파기적 변경을 자동으로 판정한다.** 필드 삭제·타입 변경·필수화는 소비자를 깨뜨린다.
   사람이 기억해서 챙기게 두면 반드시 놓친다.
4. **깨진 계약을 활성화하지 않는다.** 활성은 "이 약속으로 붙어도 된다"는 선언이므로,
   지금 이미 위반 중인 것을 활성화하면 선언이 거짓이 된다.

LLM 0콜.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.master_data import MasterData, master_data

CONTRACT_STATUS = ("draft", "active", "deprecated", "retired")
# 최신성 SLA 는 카탈로그의 갱신주기 어휘를 그대로 쓴다 — 별도 어휘를 만들면 둘이 어긋난다.
_STALENESS_ORDER = ("realtime", "hourly", "daily", "weekly", "monthly", "quarterly")


class DataContractError(ValueError):
    """검증/충돌 등 4xx 로 전달할 도메인 오류."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(raw, default):
    try:
        v = json.loads(raw) if isinstance(raw, str) else raw
        return v if isinstance(v, (dict, list)) else default
    except Exception:
        return default


class DataContracts:
    def __init__(self, md: MasterData = None):
        self.md = md or master_data

    def _connect(self):
        return self.md._connect()

    # ── 등록·개정 ─────────────────────────────────────────────────────────
    def create(self, name: str, producer_asset_id: str, consumer: str,
               schema: Dict[str, Any] = None, quality_rules: Dict[str, Any] = None,
               access_policy: Dict[str, Any] = None, contract_key: str = "",
               note: str = "", catalog=None, tenant_id: str = "tenant_default",
               enterprise_scope_id: str = "", entity_mode: str = "REAL") -> dict:
        from core.data_catalog import data_catalog
        cat = catalog or data_catalog
        if not (name or "").strip():
            raise DataContractError("name 은 필수입니다.")
        if not (consumer or "").strip():
            raise DataContractError("consumer 는 필수입니다 — 누구와의 약속인지 없으면 계약이 아닙니다.")
        if not cat.get_asset(producer_asset_id, with_fields=False):
            raise DataContractError(f"존재하지 않는 생산자 자산입니다: {producer_asset_id}")

        key = contract_key or f"dck_{uuid.uuid4().hex[:10]}"
        now = _now()
        with self.md._lock, self._connect() as conn:
            row = conn.execute("SELECT MAX(version) AS v FROM data_contracts WHERE contract_key=?",
                               (key,)).fetchone()
            prev = int(row["v"] or 0)
            cid = f"dc_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO data_contracts(contract_id,contract_key,version,name,"
                "producer_asset_id,consumer,schema_json,quality_rules_json,access_policy_json,"
                "status,activated_by,activated_at,supersedes,note,tenant_id,"
                "enterprise_scope_id,entity_mode,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,'draft','','',?,?,?,?,?,?,?)",
                (cid, key, prev + 1, name.strip(), producer_asset_id, consumer.strip(),
                 json.dumps(schema or {}, ensure_ascii=False),
                 json.dumps(quality_rules or {}, ensure_ascii=False),
                 json.dumps(access_policy or {}, ensure_ascii=False),
                 f"{key}@{prev}" if prev else "", note,
                 tenant_id or "tenant_default", enterprise_scope_id, entity_mode or "REAL",
                 now, now))
        return self.get(cid)

    def revise(self, contract_key: str, **kwargs) -> dict:
        """개정 = **새 버전 행**. 이전 버전을 덮지 않는다."""
        cur = self.get_active(contract_key) or self.latest(contract_key)
        if not cur:
            raise DataContractError(f"존재하지 않는 계약입니다: {contract_key}")
        return self.create(
            name=kwargs.get("name", cur["name"]),
            producer_asset_id=kwargs.get("producer_asset_id", cur["producer_asset_id"]),
            consumer=kwargs.get("consumer", cur["consumer"]),
            schema=kwargs.get("schema", cur["schema"]),
            quality_rules=kwargs.get("quality_rules", cur["quality_rules"]),
            access_policy=kwargs.get("access_policy", cur["access_policy"]),
            contract_key=contract_key, note=kwargs.get("note", ""),
            catalog=kwargs.get("catalog"))

    def _row(self, row) -> dict:
        d = dict(row)
        d["schema"] = _loads(d.pop("schema_json", "{}"), {})
        d["quality_rules"] = _loads(d.pop("quality_rules_json", "{}"), {})
        d["access_policy"] = _loads(d.pop("access_policy_json", "{}"), {})
        return d

    def get(self, contract_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM data_contracts WHERE contract_id=?",
                             (contract_id,)).fetchone()
        return self._row(r) if r else None

    def latest(self, contract_key: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM data_contracts WHERE contract_key=? "
                             "ORDER BY version DESC LIMIT 1", (contract_key,)).fetchone()
        return self._row(r) if r else None

    def get_active(self, contract_key: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM data_contracts WHERE contract_key=? AND status='active' "
                             "ORDER BY version DESC LIMIT 1", (contract_key,)).fetchone()
        return self._row(r) if r else None

    def list(self, producer_asset_id: str = "", consumer: str = "",
             status: str = "", include_retired: bool = False, scope_node_id: str = "",
             tenant_id: str = "", entity_mode: str = "REAL",
             # [§6-2] 등급이 낮으면 제목만 남기고 내용을 가린다(빈 값 = 가리지 않는다)
             viewer_clearance: str = "",
             # [경영진 드릴다운] 하위 조직까지 볼 수 있는 주체면 True(기본은 자기+상위만)
             include_descendants: bool = False) -> List[dict]:
        sql, params = "SELECT * FROM data_contracts WHERE 1=1", []
        if not include_retired:
            sql += " AND status<>'retired'"
        for col, val in (("producer_asset_id", producer_asset_id), ("consumer", consumer),
                         ("status", status)):
            if val:
                sql += f" AND {col}=?"
                params.append(val)
        with self._connect() as conn:
            rows = [self._row(r) for r in conn.execute(
                sql + " ORDER BY contract_key, version DESC", tuple(params)).fetchall()]
        # 등급만 주어진 호출도 처리한다 — 범위 없이 등급만 거는 화면이 있다.
        if not (scope_node_id or viewer_clearance):
            return rows
        from core.enterprise_context.scoping import filter_visible
        return filter_visible(rows, scope_node_id, tenant_id, entity_mode,
                              viewer_clearance=viewer_clearance,
                              include_descendants=include_descendants)

    # ── 활성화 ────────────────────────────────────────────────────────────
    def activate(self, contract_id: str, activated_by: str, catalog=None,
                 allow_breached: bool = False) -> dict:
        """활성화 = "이 약속으로 붙어도 된다"는 선언.

        ⚠️ **이미 위반 중인 계약을 활성화하지 않는다.** 선언이 거짓이 되고, 소비자는 지켜지지
          않는 약속을 믿고 붙는다. 알면서 활성화해야 할 때만 `allow_breached=True`."""
        if not (activated_by or "").strip():
            raise DataContractError("activated_by 는 필수입니다 — 누가 이 약속을 승인했는지 없으면 "
                                    "근거가 없습니다.")
        c = self.get(contract_id)
        if not c:
            raise DataContractError(f"존재하지 않는 계약입니다: {contract_id}")
        if c["status"] == "retired":
            raise DataContractError("폐기된 계약은 활성화할 수 없습니다.")

        ev = self.evaluate(contract_id, catalog=catalog)
        if ev["state"] == "breached" and not allow_breached:
            raise DataContractError(
                "지금 위반 중인 계약은 활성화할 수 없습니다. 위반: "
                + "; ".join(f["why"] for f in ev["findings"] if f["severity"] == "high")[:400]
                + " (알면서 활성화하려면 allow_breached=true)")

        now = _now()
        with self.md._lock, self._connect() as conn:
            # 같은 키의 기존 활성본은 자동으로 deprecated — 활성이 둘이면 어느 약속이
            #   유효한지 알 수 없다.
            conn.execute("UPDATE data_contracts SET status='deprecated', updated_at=? "
                         "WHERE contract_key=? AND status='active' AND contract_id<>?",
                         (now, c["contract_key"], contract_id))
            conn.execute("UPDATE data_contracts SET status='active', activated_by=?, "
                         "activated_at=?, updated_at=? WHERE contract_id=?",
                         (activated_by, now, now, contract_id))
        out = self.get(contract_id)
        out["evaluation_at_activation"] = ev["state"]
        return out

    def retire(self, contract_id: str) -> bool:
        with self.md._lock, self._connect() as conn:
            return conn.execute(
                "UPDATE data_contracts SET status='retired', updated_at=? "
                "WHERE contract_id=? AND status<>'retired'", (_now(), contract_id)).rowcount > 0

    # ── 파기적 변경 판정 ──────────────────────────────────────────────────
    @staticmethod
    def diff_schema(old: Dict[str, Any], new: Dict[str, Any]) -> dict:
        """두 스키마를 비교해 **소비자를 깨뜨리는 변경**을 가려낸다.

        사람이 기억해서 챙기게 두면 반드시 놓친다. 파기적인 것:
          · 필드 삭제 — 소비자가 읽던 것이 사라진다
          · 타입 변경 — 파싱이 깨진다
          · 선택 → 필수 — 생산자 쪽 제약이지만 기존 데이터가 규칙을 어기게 된다
        파기적이지 않은 것: 필드 추가, 필수 → 선택."""
        def _fields(s):
            return {f["name"]: f for f in (s or {}).get("fields", []) if f.get("name")}
        o, n = _fields(old), _fields(new)
        breaking, compatible = [], []
        for name, of in o.items():
            if name not in n:
                breaking.append({"kind": "field_removed", "field": name,
                                 "why": f"'{name}' 필드가 사라졌다 — 이 필드를 읽던 소비자가 깨진다."})
                continue
            nf = n[name]
            if of.get("type") and nf.get("type") and of["type"] != nf["type"]:
                breaking.append({"kind": "type_changed", "field": name,
                                 "why": f"'{name}' 타입이 {of['type']} → {nf['type']} 로 바뀌었다."})
            if not of.get("required") and nf.get("required"):
                breaking.append({"kind": "became_required", "field": name,
                                 "why": f"'{name}' 이 선택 → 필수가 됐다."})
            elif of.get("required") and not nf.get("required"):
                compatible.append({"kind": "became_optional", "field": name})
        for name in n:
            if name not in o:
                compatible.append({"kind": "field_added", "field": name})
        return {"breaking": breaking, "compatible": compatible,
                "is_breaking": bool(breaking),
                "note": ("파기적 변경이 있으면 소비자에게 통지하고 이행 기간을 두십시오. "
                         "새 버전으로 등록하면 이전 버전은 남습니다.")}

    def preview_revision(self, contract_key: str, new_schema: Dict[str, Any]) -> dict:
        cur = self.get_active(contract_key) or self.latest(contract_key)
        if not cur:
            raise DataContractError(f"존재하지 않는 계약입니다: {contract_key}")
        d = self.diff_schema(cur["schema"], new_schema)
        d["from_version"] = cur["version"]
        d["consumer"] = cur["consumer"]
        return d

    # ── 검증 — 이 모듈의 존재 이유 ────────────────────────────────────────
    def evaluate(self, contract_id: str, catalog=None, now: str = "") -> dict:
        """약속이 **지금** 지켜지고 있는지 실제 카탈로그·품질·최신성과 대조한다.

        ⚠️ 확인하지 못한 항목은 **통과가 아니다.** 품질 프로파일이 없으면 `unverifiable` 이지
          `kept` 가 아니다. 통과로 처리하면 "계약 준수 중"이라는 거짓 안심이 생기고, 그건
          계약이 없는 것보다 나쁘다."""
        from core.data_catalog import data_catalog
        cat = catalog or data_catalog
        c = self.get(contract_id)
        if not c:
            raise DataContractError(f"존재하지 않는 계약입니다: {contract_id}")
        asset = cat.get_asset(c["producer_asset_id"])
        findings: List[dict] = []
        # ⚠️ 폐기(소프트 삭제)된 자산도 `get_asset` 은 돌려준다(상세 조회용으로는 맞다).
        #   계약 검증에서는 **폐기 = 없음**이다 — 카탈로그에서 내린 자산으로 약속을 지킬 수 없다.
        if not asset or asset.get("status") != "active":
            why = (f"생산자 자산({c['producer_asset_id']})이 카탈로그에 없다." if not asset else
                   f"생산자 자산({asset['name']})이 폐기됐다 — 약속을 지킬 원천이 사라졌다.")
            findings.append({"kind": "producer_missing", "severity": "high", "why": why})
            # ★ [2026-07-30] 이 조기 반환이 `contract_key`·`version`·`consumer`·`note` 를
            #   빼먹고 있었다 — **같은 함수가 두 가지 모양을 돌려주면** 소비자는 정상 경로에서만
            #   동작하고 위반 경로에서 KeyError 로 죽는다. 하필 그 경로가 가장 알아야 하는
            #   경로다(실측: 전사 브리핑 집계가 이 키에서 터졌다).
            return {"contract_id": contract_id, "contract_key": c["contract_key"],
                    "version": c["version"], "consumer": c["consumer"],
                    "state": "breached", "findings": findings,
                    "checked": [], "unverifiable": [],
                    "note": ("생산자 자산이 없거나 폐기됐습니다 — 나머지 항목은 검증할 대상이 "
                             "없어 확인하지 않았습니다.")}

        checked, unverifiable = [], []

        # 1) 스키마 — 약속한 필드가 실제로 있는가
        want = [f for f in (c["schema"] or {}).get("fields", []) if f.get("name")]
        have = {f["name"]: f for f in asset["fields"]}
        if want:
            checked.append("schema")
            for f in want:
                if f["name"] not in have:
                    findings.append({"kind": "field_missing", "severity": "high",
                                     "why": f"약속한 필드 '{f['name']}' 이 생산자 자산에 없다."})
                elif f.get("type") and have[f["name"]]["logical_type"] and \
                        f["type"] != have[f["name"]]["logical_type"]:
                    findings.append({
                        "kind": "type_mismatch", "severity": "high",
                        "why": (f"'{f['name']}' 타입이 약속({f['type']})과 실제"
                                f"({have[f['name']]['logical_type']})가 다르다.")})
        else:
            unverifiable.append({"kind": "schema", "why": "계약에 필드 약속이 없어 검증할 것이 없다."})

        # 2) 품질 — 프로파일이 없으면 '통과'가 아니라 '확인 불가'
        rules = c["quality_rules"] or {}
        q = cat.latest_quality_profile(c["producer_asset_id"])
        thresholds = {"min_completeness": ("completeness", "ge"),
                      "min_validity": ("validity", "ge"),
                      "max_duplicate_rate": ("duplicate_rate", "le")}
        if any(k in rules for k in thresholds):
            if not q:
                unverifiable.append({"kind": "quality", "why": (
                    "품질 규칙이 있으나 측정 프로파일이 없다. **확인하지 못한 것은 통과가 아니다.**")})
            else:
                checked.append("quality")
                if rules.get("required_method") and q["method"] != rules["required_method"]:
                    findings.append({"kind": "quality_method", "severity": "medium",
                                     "why": (f"품질 근거가 '{q['method']}' 인데 계약은 "
                                             f"'{rules['required_method']}' 를 요구한다.")})
                for rk, (col, op) in thresholds.items():
                    if rk not in rules:
                        continue
                    v = q.get(col)
                    if v is None:
                        unverifiable.append({"kind": f"quality.{col}",
                                             "why": f"'{col}' 은 측정되지 않았다(0 이 아니라 미측정)."})
                        continue
                    bad = (v < rules[rk]) if op == "ge" else (v > rules[rk])
                    if bad:
                        findings.append({"kind": f"quality_{col}", "severity": "high",
                                         "why": f"{col}={v} 가 계약 기준({rk}={rules[rk]})을 어긴다."})

        # 3) 최신성 SLA
        if rules.get("max_staleness"):
            fr = cat.assess_freshness(c["producer_asset_id"], now=now)
            if fr["state"] == "unknown":
                unverifiable.append({"kind": "freshness", "why": fr["why"]})
            else:
                checked.append("freshness")
                want_c = rules["max_staleness"]
                if want_c in _STALENESS_ORDER and asset["refresh_cadence"] in _STALENESS_ORDER \
                        and _STALENESS_ORDER.index(asset["refresh_cadence"]) > \
                        _STALENESS_ORDER.index(want_c):
                    findings.append({"kind": "cadence_slower_than_sla", "severity": "high",
                                     "why": (f"자산 갱신주기({asset['refresh_cadence']})가 계약 "
                                             f"SLA({want_c})보다 느리다 — 약속을 구조적으로 못 지킨다.")})
                if fr["state"] == "stale":
                    findings.append({"kind": "stale", "severity": "high", "why": fr["why"]})
                elif fr["state"] == "late":
                    findings.append({"kind": "late", "severity": "medium", "why": fr["why"]})

        # 4) 접근 정책
        pol = c["access_policy"] or {}
        if pol:
            checked.append("access")
            if pol.get("max_sensitivity"):
                from core.data_catalog import SENSITIVITY
                rank = {s: i for i, s in enumerate(SENSITIVITY)}
                if rank.get(asset["sensitivity"], 0) > rank.get(pol["max_sensitivity"], 0):
                    findings.append({
                        "kind": "sensitivity_exceeds_policy", "severity": "high",
                        "why": (f"자산 민감도({asset['sensitivity']})가 계약이 허용한 "
                                f"수준({pol['max_sensitivity']})을 넘는다.")})
            if pol.get("pii_allowed") is False:
                pii = [f["name"] for f in asset["fields"]
                       if f["pii_classification"] in ("pii", "sensitive_pii")]
                if pii:
                    findings.append({"kind": "pii_not_allowed", "severity": "high",
                                     "why": f"계약이 PII 를 금지하는데 PII 필드가 있다: {', '.join(pii[:5])}"})

        high = [f for f in findings if f["severity"] == "high"]
        if high:
            state = "breached"
        elif findings:
            state = "at_risk"
        elif unverifiable:
            state = "unverifiable"        # ★ 통과가 아니다
        else:
            state = "kept"
        return {
            "contract_id": contract_id, "contract_key": c["contract_key"],
            "version": c["version"], "consumer": c["consumer"], "state": state,
            "findings": findings, "checked": checked, "unverifiable": unverifiable,
            "note": ("`unverifiable` 은 통과가 아닙니다 — 확인하지 못한 항목입니다. "
                     "'계약 준수 중'이라는 거짓 안심은 계약이 없는 것보다 위험합니다."),
        }

    def evaluate_all(self, catalog=None) -> dict:
        rows = [self.evaluate(c["contract_id"], catalog=catalog)
                for c in self.list(status="active")]
        by = {}
        for r in rows:
            by[r["state"]] = by.get(r["state"], 0) + 1
        return {"total": len(rows), "by_state": by, "results": rows}


data_contracts = DataContracts()
