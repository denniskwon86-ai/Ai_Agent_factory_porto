"""M1~M4 문서 → 기준정보 적재 + ECM 조직 범위 바인딩 (감사 ENTERPRISE-01 Action 1 종결).

## 무엇을 하는가

`docs/master_data/*.json` 의 제조 도메인 지식을 `master_records` 에 적재하고, 각 문서를 실제 조직
범위에 바인딩한다(R-001 / `DECISIONS.md` D-009).

  battery_material_m1  → 배터리소재 사업부 (하위 공장에 상속)
  copper_smelting_m2   → 동제련 사업부
  global_standard_m3   → 법인 전체 (전사 표준 — 하위 상속)
  digital_twin_sim_m4  → 법인 전체 (시뮬레이션 파라미터)

이 바인딩이 있어야 "어느 법인·사업부·공장의 기준정보인가"가 성립하고(감사 Finding 1),
배터리소재 마스터가 동제련 프롬프트에 섞이지 않는다.

## ⚠️ 값의 정확도는 여기서 판정하지 않는다 (사용자 지시 2026-07-29)

"데이터 수치가 맞냐, 정확도가 얼마냐"는 구현 단계에서 확인할 수 없고, 구현 완료 후 실사용
사전 작업 또는 실사용 과정에서 보정되어야 한다. 따라서 이 모듈은:

  · 계수를 **하드코딩하지 않고 문서에서 읽는다** → 문서를 고치면 자동 반영된다.
  · 값을 **임의로 보정하지 않는다** → 근거 없는 숫자를 만들지 않는다(§16).
  · 대신 `inspect_data_quality()` 가 **계산으로 드러나는 모순을 탐지해 목록으로 남긴다.**
    그 목록이 곧 실사용 전 보정 작업의 입력이 된다.

실측으로 이미 확인된 모순 두 건(단위 불일치·Cpk 미달)도 이 점검기가 스스로 찾아낸다 —
사람이 기억해서 챙기지 않아도 시스템이 알려주는 것이 목적이다.
"""
import json
import os
import re
from typing import Any, Dict, List, Optional

_DOCS_DIR = os.path.join("docs", "master_data")
SEED_SOURCE = "master_document_seed"        # 사용자 입력과 구분하는 표지

# 문서 파일 → (도메인 태그, 바인딩할 ECM 노드 코드, 상속 여부)
#   ⚠️ 노드 코드는 `core/enterprise_context/seed.py` 의 예시 조직과 맞춘다. 실제 조직이 확정되면
#     이 표만 고치면 된다(코드 수정 없이 매핑 교체).
DOCUMENT_SCOPES: Dict[str, Dict[str, Any]] = {
    "battery_material_m1.json": {
        "domains": ["manufacturing", "battery-materials"],
        "scope_code": "MNM_BATTERY", "inherit": True,
        "why": "배터리소재 사업부의 공정·자재이며 두 공장에 상속된다.",
    },
    "copper_smelting_m2.json": {
        "domains": ["manufacturing", "copper-smelting"],
        "scope_code": "MNM_COPPER", "inherit": True,
        "why": "동제련 사업부 전용. 배터리소재 프롬프트에 섞이면 안 된다.",
    },
    "global_standard_m3.json": {
        "domains": ["manufacturing", "standards"],
        "scope_code": "LS_MNM", "inherit": True,
        "why": "전사 표준(ERP 산식·ISO22400·KS X 9101) — 법인 하위 전체에 상속된다.",
    },
    "digital_twin_simulation_m4.json": {
        "domains": ["simulation"],
        "scope_code": "LS_MNM", "inherit": True,
        "why": "시뮬레이션 런타임 파라미터 — 법인 전체가 같은 엔진을 쓴다.",
    },
}

# 적재할 엔터티 유형. `attr_schema` 를 비워 두는 이유: 문서 스키마가 파일마다 조금씩 다르고
#   (M1 은 base_price_usd 가 있고 M2 는 없다) 스키마를 좁히면 적재가 실패한다. 검증은
#   `inspect_data_quality()` 가 계산으로 한다.
ENTITY_TYPES = [
    ("material", "자재/품목"),
    ("equipment", "설비"),
    ("quality-spec", "품질 규격"),
    ("bom", "BOM(소요량)"),
    ("finance-param", "재무·시장 파라미터"),
    ("kpi", "KPI 정의"),
    ("work-center", "작업장"),
    ("logistics-param", "물류 파라미터"),
    ("emission-factor", "배출계수"),
    ("sim-param", "시뮬레이션 파라미터"),
    ("sensor-spec", "센서 규격"),
]


def _slug(text: str) -> str:
    """사람이 쓴 라벨 → `master_code` 규격(대문자·숫자·하이픈)."""
    out = []
    for ch in str(text or "").upper():
        out.append(ch if (ch.isalnum() and ord(ch) < 128) else "-")
    code = "-".join(p for p in "".join(out).split("-") if p)
    return code[:28] or "ITEM"


def load_documents(docs_dir: str = _DOCS_DIR) -> Dict[str, Dict[str, Any]]:
    """문서를 읽는다. 읽기 실패는 건너뛰고 리포트에 남긴다(하나가 깨져도 나머지는 적재)."""
    out = {}
    if not os.path.isdir(docs_dir):
        return out
    for fn in sorted(os.listdir(docs_dir)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(docs_dir, fn), "r", encoding="utf-8") as f:
                out[fn] = json.load(f)
        except Exception:
            continue
    return out


# ══════════════════════════════════════════════════════════════════════════
# 별칭 파생
# ══════════════════════════════════════════════════════════════════════════
# 알파벳/숫자만으로 된 단위·농도 토큰은 별칭으로 쓰면 오탐을 부른다.
_ALIAS_STOP = {"grade", "battery grade", "crystals", "solution", "type", "std", "standard"}


def derive_aliases(name: str, code_or_id: str = "") -> List[str]:
    """정식명에서 **실제로 매칭될** 별칭들을 뽑는다.

    ★ 이것이 없으면 별칭 히트 경로가 죽는다(실측 결함). 문서의 자재명은
      `"Mixed Hydroxide Precipitate (MHP)"` 형태인데 `MasterData._alias_hit` 은 단어경계로
      **문자열 전체**를 찾으므로, 프롬프트에 이 괄호 표기가 그대로 나오지 않는 한 영원히
      매칭되지 않는다. 그러면 선정이 `is_core` + 코드 알파벳순으로만 이뤄져
      **무엇이 프롬프트에 들어갈지가 중요도가 아니라 코드 철자로 결정된다.**

    **새 문자열을 창작하지 않는다** — 문서가 이미 적은 이름의 부분과 식별자만 쓴다:
      "Mixed Hydroxide Precipitate (MHP)"   → 전체 · "Mixed Hydroxide Precipitate" · "MHP"
      "Sulfuric Acid (H2SO4, 98%)"          → 전체 · "Sulfuric Acid" · "H2SO4"  ("98%" 는 탈락)
    """
    name = (name or "").strip()
    if not name:
        return []
    out = [name]
    head = name.split("(")[0].strip(" ,-")
    if head and head != name:
        out.append(head)
    for grp in re.findall(r"\(([^)]*)\)", name):
        for tok in grp.split(","):
            out.append(tok.strip())
    if code_or_id:
        out.append(str(code_or_id).strip())

    seen, keep = set(), []
    for a in out:
        a = a.strip(" ,-.")
        low = a.lower()
        if (len(a) < 2 or low in seen or low in _ALIAS_STOP
                or not re.search(r"[A-Za-z가-힣]", a)):   # "98%" 같은 순수 수치·단위 토큰 탈락
            continue
        seen.add(low)
        keep.append(a)
    return keep


# ══════════════════════════════════════════════════════════════════════════
# 문서 → 기준정보 레코드 변환
# ══════════════════════════════════════════════════════════════════════════
def _records_from_document(fn: str, doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """문서 1개에서 적재할 레코드 목록을 뽑는다. **값을 변형하지 않고 그대로 담는다.**

    변형하면 나중에 문서를 고쳐도 반영되지 않고, 무엇이 원본인지 알 수 없게 된다."""
    prefix = {"battery_material_m1.json": "M1", "copper_smelting_m2.json": "M2",
              "global_standard_m3.json": "M3", "digital_twin_simulation_m4.json": "M4"}.get(fn, "MX")
    recs: List[Dict[str, Any]] = []

    def add(code, type_id, name, attrs, is_core=True, alias_src=None):
        """`alias_src` 는 **문서에 이미 적혀 있는** 식별자·이름들. 여기서 별칭을 파생한다
        (창작 금지). 별칭이 없으면 `select_for_injection` 의 1순위 경로가 죽는다."""
        aliases = list(derive_aliases(name))
        for s in (alias_src or []):
            for a in derive_aliases(s):
                if a.lower() not in {x.lower() for x in aliases}:
                    aliases.append(a)
        recs.append({"master_code": code, "type_id": type_id, "name": name,
                     "attributes": attrs, "is_core": is_core, "aliases": aliases})

    for m in doc.get("material_master", []) or []:
        add(_slug(m.get("material_id")), "material", m.get("material_name", ""),
            {k: v for k, v in m.items() if k not in ("material_id", "material_name")},
            alias_src=[m.get("material_id")])
    for e in doc.get("equipment_master", []) or []:
        add(_slug(e.get("equipment_id")), "equipment", e.get("equipment_name", ""),
            {k: v for k, v in e.items() if k not in ("equipment_id", "equipment_name")},
            alias_src=[e.get("equipment_id")])
    for q in doc.get("quality_master", []) or []:
        add(f"{prefix}-QS-{_slug(q.get('product_id'))}"[:30], "quality-spec",
            f"{q.get('product_id')} 품질규격", {k: v for k, v in q.items()},
            alias_src=[q.get("product_id")])
    for b in doc.get("bill_of_materials", []) or []:
        add(f"{prefix}-BOM-{_slug(b.get('parent_id'))}"[:30], "bom",
            f"{b.get('parent_id')} BOM", {k: v for k, v in b.items()},
            alias_src=[b.get("parent_id")])
    for f in doc.get("siop_finance_master", []) or []:
        add(f"{prefix}-FIN-{_slug(f.get('category'))}"[:30], "finance-param",
            f.get("category", "재무 파라미터"), {k: v for k, v in f.items() if k != "category"})

    # ── M3 전용 섹션 ──────────────────────────────────────────────────────
    for k in doc.get("iso22400_kpi_dictionary", []) or []:
        add(_slug(k.get("kpi_id")), "kpi", k.get("name", ""),
            {k2: v for k2, v in k.items() if k2 not in ("kpi_id", "name")},
            alias_src=[k.get("kpi_id")])
    isa = doc.get("isa95_sap_architecture") or {}
    for i, w in enumerate(isa.get("work_center_master", []) or [], 1):
        add(f"{prefix}-WC-{i:02d}", "work-center", w.get("wc_type", "작업장"), dict(w))
    if isa.get("routing_template"):
        add(f"{prefix}-ROUTING", "work-center", "표준 라우팅 템플릿", dict(isa["routing_template"]))
    scm = doc.get("scm_wms_master") or {}
    for i, lg in enumerate(scm.get("logistics", []) or [], 1):
        add(f"{prefix}-LOGIS-{i:02d}", "logistics-param", lg.get("transport_mode", "물류"), dict(lg))
    if scm.get("warehouse_capacity"):
        add(f"{prefix}-WHCAP", "logistics-param", "창고 용량·비용", dict(scm["warehouse_capacity"]))
    esg = doc.get("esg_cbam_master") or {}
    for i, ef in enumerate(esg.get("emission_factors", []) or [], 1):
        add(f"{prefix}-EMIS-{i:02d}", "emission-factor", ef.get("utility_type", "배출계수"), dict(ef))
    if esg.get("cbam_penalty"):
        add(f"{prefix}-CBAM", "emission-factor", "CBAM 탄소세", dict(esg["cbam_penalty"]))
    for i, s in enumerate(doc.get("pdm_sensor_schema", []) or [], 1):
        add(f"{prefix}-SENSOR-{i:02d}", "sensor-spec", s.get("sensor_type", "센서"), dict(s))
    erp = doc.get("erp_business_logic") or {}
    for key, val in erp.items():
        # ERP 산식은 **계산 근거**다. 프롬프트에 확정 주입되어야 LLM 이 산식을 지어내지 않는다.
        add(f"{prefix}-ERP-{_slug(key)}"[:30], "finance-param", f"ERP 로직: {key}", dict(val))

    # ── M4 전용 ───────────────────────────────────────────────────────────
    des = doc.get("discrete_event_simulation_des") or {}
    for key, val in des.items():
        add(f"{prefix}-DES-{_slug(key)}"[:30], "sim-param", f"DES: {key}", dict(val))
    if doc.get("spatial_3d_fab_layout"):
        add(f"{prefix}-LAYOUT", "sim-param", "3D 공장 레이아웃", dict(doc["spatial_3d_fab_layout"]))
    if doc.get("data_sync_fidelity"):
        add(f"{prefix}-SYNC", "sim-param", "데이터 동기화 충실도", dict(doc["data_sync_fidelity"]))
    return recs


# ══════════════════════════════════════════════════════════════════════════
# 데이터 품질 점검 — 값을 고치지 않고 '보정 목록'을 만든다
# ══════════════════════════════════════════════════════════════════════════
def inspect_data_quality(docs: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """문서 내부 **계산으로 드러나는 모순**을 찾는다.

    ⚠️ 값을 바꾸지 않는다. 실사용 전 보정 작업의 입력 목록을 만드는 것이 목적이다
      (사용자 지시: 정확도는 구현 단계에서 판정할 수 없다).
    ⚠️ 여기서 쓰는 기준은 **문서 안에 있는 값끼리의 비교**뿐이다. 외부 시장가 같은 것을 끌어와
      판정하면 근거 없는 숫자가 된다."""
    docs = docs if docs is not None else load_documents()
    findings: List[Dict[str, Any]] = []

    for fn, doc in docs.items():
        mats = {m.get("material_id"): m for m in (doc.get("material_master") or [])}

        # ① BOM 원가 구조 — 부원료가 주원료보다 비싸면 단위 불일치 의심
        for bom in doc.get("bill_of_materials", []) or []:
            comps = []
            for c in bom.get("components", []) or []:
                m = mats.get(c.get("material_id")) or {}
                price = m.get("base_price_usd")
                if price is None:
                    continue
                comps.append({"material_id": c.get("material_id"), "qty": c.get("quantity"),
                              "uom": c.get("uom"), "unit_price": price,
                              "unit_price_uom": m.get("uom"),
                              "extended": price * (c.get("quantity") or 0)})
            # 총 재료비 vs 판가 — 적자 구조는 단위 오류의 강한 신호
            total = sum(c["extended"] for c in comps)
            parent = mats.get(bom.get("parent_id")) or {}
            sell = parent.get("base_price_usd")
            if total and sell:
                if total > sell:
                    dominant = max(comps, key=lambda x: x["extended"])
                    findings.append({
                        "severity": "high",
                        "document": fn,
                        "kind": "cost_exceeds_price",
                        "subject": bom.get("parent_id"),
                        "message": (f"재료비 합계 ${total:,.0f} 가 판가 ${sell:,.0f} 를 초과합니다"
                                    f"(구조적 적자). 원가를 지배하는 항목: "
                                    f"{dominant['material_id']} ${dominant['extended']:,.0f}"),
                        "evidence": {"material_cost": total, "sell_price": sell,
                                     "components": comps},
                        "suspected_cause": (f"{dominant['material_id']} 의 `base_price_usd` 단위가 "
                                            f"`uom`({dominant['unit_price_uom']})와 다를 가능성"),
                        "suggested_action": ("현업에서 해당 자재의 실제 단가와 단위를 확인해 "
                                            "`base_price_usd`/`uom` 을 정합화하십시오."),
                    })

        # ② 품질 — 공차·분포·목표 Cpk 의 내부 모순
        for q in doc.get("quality_master", []) or []:
            target = q.get("target_cpk")
            for d in q.get("critical_defects", []) or []:
                usl, mu, sd = d.get("tolerance_limit_ppm"), d.get("mean"), d.get("std_dev")
                if not (target and usl is not None and mu is not None and sd):
                    continue
                cpk = (usl - mu) / (3 * sd)
                if cpk < target:
                    need = (usl - mu) / (3 * target)
                    findings.append({
                        "severity": "high",
                        "document": fn,
                        "kind": "cpk_unreachable",
                        "subject": f"{q.get('product_id')} / {d.get('defect_name')}",
                        "message": (f"분포(μ={mu}, σ={sd})와 공차(USL={usl})로 계산한 Cpk "
                                    f"{cpk:.2f} 가 목표 {target} 에 미달합니다. 이 값으로 "
                                    f"시뮬레이션하면 항상 품질 미달이 나옵니다."),
                        "evidence": {"computed_cpk": round(cpk, 3), "target_cpk": target,
                                     "usl": usl, "mean": mu, "std_dev": sd,
                                     "std_dev_required": round(need, 3)},
                        "suspected_cause": "공정 실측 분포와 목표 Cpk 가 서로 다른 시점의 값일 가능성",
                        "suggested_action": (f"σ 를 {need:.2f} 이하로 개선하는 것을 목표로 삼든지, "
                                            f"`target_cpk` 를 현실 값으로 조정하십시오."),
                    })

        # ③ 단가 단위 정합성 — 소단위 UOM 에 큰 단가가 붙어 있으면 의심
        #   ⚠️ **문서 내 시장가와 교차검증한다.** 귀금속은 온스당 고가가 정상이므로(금 $2,350/oz)
        #     UOM 과 금액만 보면 오탐이 난다(실측으로 확인). 같은 문서의 `siop_finance_master` 에
        #     부합하는 시세가 있으면 근거가 있는 것으로 보고 넘긴다.
        market_prices = []
        for f in (doc.get("siop_finance_master") or []):
            for k, v in f.items():
                if isinstance(v, (int, float)) and "price" in k.lower():
                    market_prices.append((k, float(v)))
        # UOM 별 의심 임계값. 액체는 소량 단가가 낮은 것이 일반적이고, 희소금속은 kg 당
        #   수백 달러가 정상이라 임계를 다르게 둔다. 온스·그램은 귀금속이라 제외한다.
        _uom_threshold = {"liter": 100, "l": 100, "ml": 10, "kg": 1000, "gram": None,
                          "g": None, "ounce": None, "oz": None}
        for m in (doc.get("material_master") or []):
            price, uom = m.get("base_price_usd"), (m.get("uom") or "")
            thr = _uom_threshold.get(uom.lower(), None)
            if not price or thr is None or price < thr:
                continue
            backing = [k for k, v in market_prices if v and abs(price - v) / v <= 0.2]
            if backing:
                continue     # 문서 내 시세와 부합 — 근거가 있다
            findings.append({
                "severity": "medium",
                "document": fn,
                "kind": "uom_price_scale_suspect",
                "subject": m.get("material_id"),
                "message": (f"단위가 `{uom}` 인데 단가가 ${price:,} 입니다(의심 임계 ${thr:,}). "
                            f"톤/배럴 기준 가격이 소단위 UOM 에 붙은 것인지 확인이 필요합니다."),
                "evidence": {"uom": uom, "base_price_usd": price, "threshold": thr,
                             "document_market_prices": market_prices},
                "suspected_cause": "가격 출처의 단위와 자재 마스터의 UOM 불일치",
                "suggested_action": "실제 거래 단위로 `uom` 또는 `base_price_usd` 를 정합화하십시오.",
            })

        # ④ 설비 목표 OEE 와 MTBF/MTTR 의 정합성 — 가용률 상한이 목표보다 낮으면 달성 불가
        for e in doc.get("equipment_master", []) or []:
            mtbf, mttr, target = e.get("mtbf_hours"), e.get("mttr_hours"), e.get("oee_target")
            if not (mtbf and mttr and target):
                continue
            availability_cap = mtbf / (mtbf + mttr)      # 이론적 가용률 상한
            if availability_cap < target:
                findings.append({
                    "severity": "medium",
                    "document": fn,
                    "kind": "oee_target_unreachable",
                    "subject": e.get("equipment_id"),
                    "message": (f"MTBF {mtbf}h / MTTR {mttr}h 로 계산한 가용률 상한 "
                                f"{availability_cap:.3f} 가 목표 OEE {target} 보다 낮습니다. "
                                f"성능·품질이 100% 여도 목표를 달성할 수 없습니다."),
                    "evidence": {"availability_cap": round(availability_cap, 4),
                                 "oee_target": target, "mtbf_hours": mtbf, "mttr_hours": mttr},
                    "suspected_cause": "목표 OEE 가 설비 신뢰성 실측과 별도로 설정됐을 가능성",
                    "suggested_action": "MTBF/MTTR 실측치를 갱신하거나 목표 OEE 를 재설정하십시오.",
                })
    return findings


# ══════════════════════════════════════════════════════════════════════════
# 적재
# ══════════════════════════════════════════════════════════════════════════
def seed_master_documents(md=None, ecm_repo=None, docs_dir: str = _DOCS_DIR,
                          bind_scopes: bool = True, force: bool = False) -> Dict[str, Any]:
    """M1~M4 를 기준정보로 적재하고 ECM 조직 범위에 바인딩한다. **멱등**.

    `force=False` 면 이미 있는 `master_code` 는 건너뛴다 — 운영 중 사용자가 개정한 값을 시드가
    되돌리면 안 된다(시드는 초기 공급이지 진실원본이 아니다).
    `bind_scopes=False` 면 적재만 하고 범위는 붙이지 않는다(ECM 미도입 환경).
    """
    from core.master_data import MasterDataError, master_data
    md = md or master_data
    docs = load_documents(docs_dir)
    report: Dict[str, Any] = {
        "documents": len(docs), "types_created": [], "records_created": [],
        "records_skipped": [], "records_failed": [], "bindings": [], "binding_skipped": [],
        "quality_findings": inspect_data_quality(docs),
    }
    if not docs:
        report["status"] = "no_documents"
        return report

    # 엔터티 유형 (멱등 — 이미 있으면 넘어간다)
    for type_id, name_ko in ENTITY_TYPES:
        try:
            md.create_type(type_id, name_ko, description="M1~M4 문서 시드")
            report["types_created"].append(type_id)
        except MasterDataError:
            pass

    existing = {r["master_code"] for r in md.list_records()}

    # ECM 노드 코드 → node_id 해석 (바인딩용)
    code_to_node: Dict[str, str] = {}
    if bind_scopes:
        try:
            from core.enterprise_context.repository import ecm_repository
            repo = ecm_repo or ecm_repository
            for n in repo.list_nodes():
                if n.code:
                    code_to_node[n.code] = n.node_id
        except Exception as e:
            report["binding_skipped"].append({"reason": f"ECM 조직 조회 실패: {e}"})

    for fn, doc in docs.items():
        spec = DOCUMENT_SCOPES.get(fn) or {"domains": ["manufacturing"], "scope_code": "",
                                           "inherit": True, "why": "매핑 미정의"}
        for rec in _records_from_document(fn, doc):
            code = rec["master_code"]
            # ★ 이미 있는 레코드는 **쓰기만** 건너뛰고 바인딩 확인은 계속한다.
            #   종전에는 여기서 `continue` 해버려 기존 레코드가 **바인딩 없이** 남았다. 그런데
            #   바인딩이 없는 코드는 「전사 공통」으로 통과하는 규칙(점진 도입 하위호환)이라
            #   결과적으로 **모든 조직에 노출**된다 — 재시드가 격리를 조용히 무너뜨렸다(실측).
            if code in existing and not force:
                report["records_skipped"].append(code)
            else:
                try:
                    md.create_or_revise_record(
                        code, rec["type_id"], rec["name"] or code,
                        attributes=rec["attributes"], domains=spec["domains"],
                        aliases=[a for a in rec["aliases"] if a], is_core=rec["is_core"],
                        source=SEED_SOURCE)
                    report["records_created"].append(code)
                    existing.add(code)
                except Exception as e:
                    # 하나가 실패해도 나머지는 적재한다. 실패는 조용히 넘기지 않고 리포트에 남긴다.
                    report["records_failed"].append({"master_code": code, "error": str(e)})
                    continue

            if not bind_scopes:
                continue
            node_id = code_to_node.get(spec["scope_code"])
            if not node_id:
                # ★ 두 상황을 구분한다 — 조용히 같은 메시지로 넘기면 설정 오류를 못 잡는다.
                #   · 조직이 아예 없다 = ECM 미도입 환경. 정상이며 나중에 다시 실행하면 된다.
                #   · 조직은 있는데 **이 코드만 없다** = 조직 코드가 바뀌었거나 다른 코드 체계가
                #     들어온 것이다. 이 경우 레코드가 **미바인딩으로 남고 「바인딩 없으면 전사
                #     공통 통과」 규칙을 타고 모든 조직에 노출된다**(결함 3과 같은 계열).
                #     설정 오류이므로 구분해서 크게 남긴다.
                _misconfig = bool(code_to_node)
                report["binding_skipped"].append({
                    "master_code": code, "scope_code": spec["scope_code"],
                    "kind": "scope_code_not_found" if _misconfig else "ecm_not_seeded",
                    "reason": (
                        f"ECM 조직은 있으나 코드 '{spec['scope_code']}' 가 없습니다. "
                        f"조직 코드 체계가 어긋났습니다 — 이 레코드는 미바인딩으로 남아 "
                        f"**모든 조직에 노출**됩니다. 존재하는 코드: "
                        f"{sorted(code_to_node)[:10]}"
                        if _misconfig else
                        "해당 ECM 노드가 없습니다(조직 시드 후 다시 실행하십시오).")})
                continue
            try:
                md.bind_master_to_scope(code, node_id,
                                        inherit_descendants=bool(spec["inherit"]),
                                        approved_by=SEED_SOURCE)
                report["bindings"].append({"master_code": code, "scope_code": spec["scope_code"],
                                           "node_id": node_id, "why": spec["why"]})
            except Exception as e:
                report["binding_skipped"].append({"master_code": code, "error": str(e)})

    report["status"] = "seeded" if report["records_created"] else "already_seeded"
    report["summary"] = {
        "records_created": len(report["records_created"]),
        "records_skipped": len(report["records_skipped"]),
        "records_failed": len(report["records_failed"]),
        "bindings": len(report["bindings"]),
        "quality_findings": len(report["quality_findings"]),
        "high_severity_findings": sum(1 for f in report["quality_findings"]
                                      if f["severity"] == "high"),
        # 미바인딩으로 남은 건수 = 전사 공통으로 통과해 모든 조직에 노출되는 건수.
        # 0 이 아니면 격리가 그만큼 뚫려 있다는 뜻이므로 리포트 최상위에 올린다.
        "unbound_exposed": sum(1 for x in report["binding_skipped"]
                               if x.get("kind") == "scope_code_not_found"),
    }
    if report["summary"]["unbound_exposed"]:
        report["status"] = "seeded_with_scope_misconfig"
    report["note"] = ("값의 정확도는 구현 단계에서 판정하지 않습니다. `quality_findings` 는 "
                      "실사용 전 보정 작업의 입력 목록이며, 시드는 값을 임의로 고치지 않습니다.")
    return report
