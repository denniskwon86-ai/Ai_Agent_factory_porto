"""[ECM E2] 조직 범위 가시성 — 카탈로그·용어사전·계약이 **공유하는 단 하나의** 판정 로직.

## 왜 공유 모듈인가

같은 규칙을 세 모듈에 복제하면 반드시 어긋난다. 이 프로젝트에서 이미 겪은 유형이다 —
`node_industry_code` 가 전역 리솔버를 쓰는 바람에 검증이 조용히 꺼졌고, 재시드가 바인딩을
건너뛰어 격리가 무너졌다. 권한·격리 판정은 **한 곳에만** 두고 거기서 고친다.

## 규칙 (D-003 과 동일 — 여기서 다시 정하지 않는다)

1. **상속은 `OPERATING_PARENT` 만 따른다.** 공유서비스·연결집계 관계는 읽기 권한을 주지 않는다.
   상위 조직의 것은 하위가 본다(전사 표준 → 사업부). 그 반대는 아니다.
2. **[관문 A · 2026-07-30] 범위가 빈 레코드는 기본 비노출이다(fail-closed).**
   종전 규칙("빈 값 = 전사 공용")은 폐기됐다 — 그것은 점진 도입 장치가 아니라 **유출 창구**였고,
   2026-07-29 에 기준정보에서 실제로 샜다(재시드가 바인딩을 건너뛰자 26건이 전 조직에 노출,
   LS전선 프롬프트에 MnM 기준정보가 들어갔다). 전사 공용은 **빈 값의 해석이 아니라 명시적
   상태**다:
     · `scope_type=ENTERPRISE_SHARED` + `approval_status=APPROVED` + 승인자 → 보인다
     · `scope_type=LEGACY_UNSCOPED` → 한시 예외로 보인다(**만료일 + 건수 관측 필수**)
     · 아무 표시도 없는 빈 범위 → **보이지 않는다**
   ⚠️ 승인 없는 `ENTERPRISE_SHARED` 를 통과시키면 승인 절차 자체가 장식이 된다.
3. **호출자가 범위를 주지 않으면 필터하지 않는다.** ECM 미도입 흐름을 막지 않는다.
   이 규칙이 관문 A 의 안전판이다 — 도입 전 사용자는 자기 데이터를 계속 전량 본다.
4. `entity_mode` 는 정확히 일치해야 한다 — REAL 문맥에 VIRTUAL 데이터가 섞이면 그게 곧 오염이다.

## 한시 예외(`LEGACY_UNSCOPED`)를 왜 남기는가

기존 데이터를 하루아침에 안 보이게 하면 도입이 멈춘다. 그러나 **통과시키는 것과 통과한 줄
모르는 것은 다르다** — 그래서 한시 예외에는 (ㄱ) 만료일(`LEGACY_GRANDFATHER_UNTIL`)과
(ㄴ) `coverage()` 의 별도 건수(`legacy_grandfathered`)가 붙는다. 만료 여부도 함께 보고하므로
"언제까지 봐줄 것인가"에 답하지 않은 채로 시간이 흐르는 일을 막는다.
"""
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Set

# ── §2.2 `scope_type` 열거값 ─────────────────────────────────────────────────
#: 소유 조직 + 그 하위(운영 상속). **기본값**이며, 소유 조직이 비어 있으면 아무에게도 안 보인다.
ORG_PRIVATE = "ORG_PRIVATE"
#: 소유 조직 + `scope_assignments` 에 **명시된** 조직. 조직 간 공유는 목록으로만 성립한다.
ORG_SHARED = "ORG_SHARED"
#: 전 조직. 승인(`approval_status=APPROVED` + `approved_by`) 없이는 성립하지 않는다.
ENTERPRISE_SHARED = "ENTERPRISE_SHARED"
#: 가상 문맥(Sandbox) 세션 안에서만. capability token(§4.3)이 있어야 열린다.
SANDBOX = "SANDBOX"
#: 관문 A 이전에 만들어진 미지정 레코드. 한시 통과 + 건수 관측 + **만료일** 대상.
LEGACY_UNSCOPED = "LEGACY_UNSCOPED"

SCOPE_TYPES = (ORG_PRIVATE, ORG_SHARED, ENTERPRISE_SHARED, SANDBOX, LEGACY_UNSCOPED)
#: 신규 데이터에 쓸 수 없는 값(§2.3-4). 이행용 표시를 신규 생성에 허용하면 이행이 끝나지 않는다.
NOT_FOR_NEW_ROWS = (LEGACY_UNSCOPED,)

#: 한시 예외의 기본 만료일. 행에 `effective_to` 가 있으면 **그 값이 우선**한다.
#: ⚠️ 만료되면 비노출이다(§2.3-2). 만료를 관측만 하고 통과시키면 "한시"가 영구가 된다 —
#:   그것이 폐기한 규칙("빈 값 = 전사 공용")이 처음 영구화된 방식이다.
LEGACY_GRANDFATHER_UNTIL = "2026-12-31"


def _fail_closed() -> bool:
    """관문 A 의 기본값을 쓰는가(§5.3 되돌림 스위치).

    ★ 값을 모듈 상수로 캐시하지 않고 **호출 시점에** 읽는다 — 캐시하면 운영 중 스위치를 내려도
      프로세스를 재시작해야 하고, 되돌릴 수 없는 되돌림 장치는 장치가 아니다."""
    try:
        import config
        return bool(getattr(config, "SCOPE_FAIL_CLOSED", True))
    except Exception:
        return True                                    # 설정을 못 읽으면 안전한 쪽


def visible_scopes(scope_node_id: str) -> Set[str]:
    """이 조직이 볼 수 있는 범위 집합 = 자기 자신 + 운영 상위 조상.

    조상 해석에 실패하면 **자기 자신만** 돌려준다(fail-closed). 실패를 '전부 보임'으로
    처리하면 리솔버 장애가 곧 전사 유출이 된다."""
    if not scope_node_id:
        return set()
    out = {scope_node_id}
    try:
        from core.enterprise_context.models import REL_OPERATING_PARENT
        from core.enterprise_context.resolver import ecm_resolver
        out |= set(ecm_resolver.ancestors(scope_node_id, REL_OPERATING_PARENT))
    except Exception as e:
        print(f"⚠️ [scoping] 조상 해석 실패 — 자기 범위만 적용(fail-closed): {e}")
    return out


def is_enterprise_shared(row: Dict[str, Any]) -> bool:
    """명시적 전사 공용 + **승인 이력**이 있는가.

    ★ `APPROVED` 라고 적혀 있는데 승인자가 비어 있으면 그것은 승인 이력이 아니다 — 누가
      승인했는지 없는 승인은 감사에서 근거가 되지 못하므로 통과시키지 않는다."""
    if (row.get("scope_type") or "").strip().upper() != ENTERPRISE_SHARED:
        return False
    if (row.get("approval_status") or "").strip().upper() != "APPROVED":
        return False
    return bool((row.get("approved_by") or "").strip())


def is_legacy_unscoped(row: Dict[str, Any]) -> bool:
    """관문 A 이전 데이터에 붙는 한시 예외 표시인가(만료 여부는 보지 않는다)."""
    return (row.get("scope_type") or "").strip().upper() == LEGACY_UNSCOPED


def legacy_deadline(row: Dict[str, Any]) -> str:
    """이 행의 한시 예외 만료일. 행에 적힌 `effective_to` 가 모듈 기본값을 이긴다.

    ★ 행별 만료일을 우선하는 이유: 이행은 한꺼번에 끝나지 않는다. 부서마다 정리 속도가
      다른데 만료일이 하나뿐이면 **가장 느린 부서 때문에 전체를 미루게** 된다."""
    return (row.get("effective_to") or "").strip() or LEGACY_GRANDFATHER_UNTIL


def is_expired(row: Dict[str, Any], today: str = "") -> bool:
    """한시 예외가 만료됐는가(§2.3-2 — 만료 후에는 비노출).

    ⚠️ 만료를 관측만 하고 통과시키면 '한시'가 영구가 된다. 폐기한 규칙("빈 값 = 전사 공용")도
      처음엔 한시 조치였다 — 만료를 강제하지 않은 것이 그것을 영구화했다."""
    return (today or date.today().isoformat()) > legacy_deadline(row)


def assigned_scopes(row: Dict[str, Any]) -> Set[str]:
    """`ORG_SHARED` 의 공유 대상 조직 집합.

    저장 형태는 콤마 구분 문자열(SQLite 컬럼) 또는 리스트(메모리 행) 둘 다 받는다 —
    호출자가 형태를 신경 쓰면 한 곳에서 파싱을 틀리고 그 순간 공유가 조용히 풀린다."""
    raw = row.get("scope_assignments") or ""
    if isinstance(raw, (list, tuple, set)):
        items = raw
    else:
        items = str(raw).replace("\n", ",").split(",")
    return {str(s).strip() for s in items if str(s).strip()}


def owner_of(row: Dict[str, Any]) -> str:
    """데이터 책임 조직. §2.1 은 소유(`owner_organization_id`)와 적용 범위
    (`enterprise_scope_id`)를 분리하라고 요구한다 — 소유가 적히면 그것이 1차 근거다.

    ★ 둘을 한 함수로 읽는 이유: 두 컬럼이 공존하는 이행 기간에 호출자마다 다른 쪽을 보면
      **같은 행이 화면마다 다르게 보인다.** 그 상태의 권한 판정은 아무도 신뢰하지 않는다."""
    return ((row.get("owner_organization_id") or "").strip()
            or (row.get("enterprise_scope_id") or "").strip())


def is_visible(row: Dict[str, Any], scope_node_id: str, tenant_id: str = "",
               entity_mode: str = "REAL", visible: Optional[Set[str]] = None,
               today: str = "", sandbox_token: str = "") -> bool:
    """레코드 한 건이 이 문맥에서 보이는가 — §2.2 의 다섯 상태를 그대로 판정한다.

    ★ 판정 축의 순서가 곧 규칙이다: 테넌트 → 문맥(REAL/VIRTUAL) → 범위 미지정 호출 →
      `scope_type` → 소유 조직. `scope_type` 을 소유 조직보다 **먼저** 보는 이유는, 전사
      공용·조직 공유가 "소유 조직 밖에서도 보인다"는 뜻이기 때문이다."""
    if tenant_id and (row.get("tenant_id") or "tenant_default") != tenant_id:
        return False
    if (row.get("entity_mode") or "REAL") != entity_mode:
        return False
    if not scope_node_id:
        return True                                    # 범위 미지정 호출 — 필터하지 않는다

    vis = visible if visible is not None else visible_scopes(scope_node_id)
    st = (row.get("scope_type") or "").strip().upper()
    owner = owner_of(row)

    # ── 소유 조직 밖에서도 보이는 상태들 ────────────────────────────────
    if st == ENTERPRISE_SHARED:
        # 승인 없는 전사 공용을 통과시키면 승인 절차 자체가 장식이 된다.
        return is_enterprise_shared(row)
    if st == ORG_SHARED:
        # 공유는 **명시된 목록**으로만 성립한다. 목록이 비면 소유 조직만 본다 —
        #   "공유하겠다고 표시했지만 대상을 안 적었다"를 전 조직 공유로 읽으면 안 된다.
        if assigned_scopes(row) & vis:
            return True
        return bool(owner) and owner in vis
    if st == SANDBOX:
        # 가상 문맥 전용. **capability token(§4.3) 이 있어야만** 열린다.
        #   토큰이 없으면 조직 권한이 아무리 높아도 열리지 않는다 — 그것이 "권한 승급이 아니다"의
        #   실질이다. 토큰은 REAL 데이터에 대한 권한을 한 조각도 주지 않는다.
        if not sandbox_token:
            return False
        try:
            from core.sandbox_token import sandbox_tokens
            return sandbox_tokens.allows(sandbox_token, row, scope_node_id)
        except Exception as e:
            # 토큰 저장소를 못 읽으면 **열지 않는다.** 검증 장애를 통과로 두면 그게 곧 뒷문이다.
            print(f"⚠️ [scoping] Sandbox 토큰 검증 실패 — 열지 않음(fail-closed): {e}")
            return False
    if st == LEGACY_UNSCOPED:
        # 한시 예외 — 만료되면 비노출(§2.3-2). coverage() 가 건수와 만료를 함께 보고한다.
        return not is_expired(row, today)

    # ── 여기부터는 ORG_PRIVATE(기본값) 또는 표시 없음 ────────────────────
    # [관문 A] 소유 조직이 비어 있으면 **아무에게도 보이지 않는다.** 빈 값은 설정 누락이지
    #   공유 의사가 아니다 — 이것을 "전사 공용"으로 읽던 것이 2026-07-29 유출 경로였다.
    if owner:
        return owner in vis
    # ⚠️ 되돌림 스위치(§5.3). `SCOPE_FAIL_CLOSED=False` 면 종전 규칙("미지정 = 전사 공용")로
    #   돌아간다 — 도입 중 현업이 막혔을 때 **코드 배포 없이** 되돌릴 수단이다.
    #   이 분기를 타는 것은 **유출 상태**이므로 조용히 넘기지 않고 그 사실을 로그로 남긴다.
    if not _fail_closed():
        print("⚠️ [scoping] SCOPE_FAIL_CLOSED=False — 범위 미지정 레코드를 전사 공용으로 "
              "통과시킵니다(관문 A 이전 규칙). 이것은 임시 조치이며 유출 경로입니다.")
        return True
    return False


def filter_visible(rows: Iterable[Dict[str, Any]], scope_node_id: str = "",
                   tenant_id: str = "", entity_mode: str = "REAL",
                   sandbox_token: str = "", viewer_clearance: str = "") -> List[Dict[str, Any]]:
    """목록에 가시성 필터를 건다. 조상 해석은 **한 번만** 한다(행마다 리솔버를 때리지 않게).

    ★ 만료 판정 기준일도 한 번만 고정한다 — 목록을 훑는 중 자정을 넘기면 같은 응답 안에서
      어떤 행은 만료 전, 어떤 행은 만료 후로 판정된다. 드물지만 그때 나온 목록은 설명할 수 없다.

    ★ [§6-2 · 2026-07-30 사용자 결정] `viewer_clearance` 를 주면 **등급이 낮은 행의 내용을
      가린다**(행은 남는다 — "제목만 보이고 내용은 차단"). 범위 필터 **뒤에** 적용되는 것이
      중요하다: 타 조직 자원은 이미 목록에서 빠졌으므로 제목도 새지 않는다.
      주지 않으면(기본) 가리지 않는다 — 내부 파이프라인처럼 등급 개념이 없는 호출을 막지 않는다."""
    vis = visible_scopes(scope_node_id) if scope_node_id else set()
    today = date.today().isoformat()
    out = [r for r in rows
           if is_visible(r, scope_node_id, tenant_id, entity_mode, vis, today,
                         sandbox_token)]
    if viewer_clearance:
        from core.enterprise_context.classification import redact_all
        out = redact_all(out, viewer_clearance)
    return out


def coverage(rows: Iterable[Dict[str, Any]], label: str = "레코드") -> Dict[str, Any]:
    """범위 미지정 건수를 **상태별로** 센다.

    ★ [관문 A] 이제 미지정은 노출이 아니라 **비노출**이다. 그래서 세는 목적이 바뀌었다:
      종전엔 "조용히 새는 건수"였고, 지금은 **"조용히 사라진 건수"** 다. 둘 다 조용하면
      위험하다 — 안 보이는 이유를 모르면 사용자는 데이터가 지워진 줄 안다.

    한시 예외(`legacy_grandfathered`)를 별도로 세는 이유: 통과시키는 것과 통과한 줄 모르는
    것은 다르다. 만료일이 지났는지(`legacy_expired`)도 함께 보고해, 결정하지 않은 채로
    시간이 흐르지 않게 한다."""
    rows = list(rows)
    total = len(rows)
    today = date.today().isoformat()

    def _st(r):
        return (r.get("scope_type") or "").strip().upper()

    unscoped = [r for r in rows if not owner_of(r)]
    shared = [r for r in rows if is_enterprise_shared(r)]
    pending = [r for r in rows if _st(r) == ENTERPRISE_SHARED and not is_enterprise_shared(r)]
    org_shared = [r for r in rows if _st(r) == ORG_SHARED]
    # 공유하겠다고 표시했으나 **대상을 안 적은** 행. 소유 조직만 보게 되므로, 공유했다고
    #   믿는 쪽과 실제 동작이 갈린다 — 조용한 미공유다.
    org_shared_empty = [r for r in org_shared if not assigned_scopes(r)]
    legacy_all = [r for r in rows if is_legacy_unscoped(r)]
    legacy = [r for r in legacy_all if not is_expired(r, today)]
    legacy_expired = [r for r in legacy_all if is_expired(r, today)]
    sandbox = [r for r in rows if _st(r) == SANDBOX]
    # 표시도 없고 소유도 없는 행 = 설정 누락으로 가려진 것.
    hidden = [r for r in unscoped
              if _st(r) not in (ENTERPRISE_SHARED, ORG_SHARED, SANDBOX, LEGACY_UNSCOPED)]
    return {
        "total": total,
        "scoped": total - len(unscoped),
        "unscoped": len(unscoped),
        "coverage_ratio": round((total - len(unscoped)) / total, 4) if total else 1.0,
        # ── 관문 A 이후의 상태별 내역 ──
        "enterprise_shared": len(shared),
        "enterprise_shared_pending": len(pending),
        "org_shared": len(org_shared),
        "org_shared_without_targets": len(org_shared_empty),
        "sandbox": len(sandbox),
        "legacy_grandfathered": len(legacy),
        "legacy_expired": len(legacy_expired),
        "hidden_unscoped": len(hidden),
        "legacy_grandfather_until": LEGACY_GRANDFATHER_UNTIL,
        "note": (
            f"범위가 지정되지 않은 {label} 는 **기본적으로 보이지 않습니다**(관문 A · "
            f"fail-closed). 전사 공용으로 쓰려면 `scope_type=ENTERPRISE_SHARED` + 승인 "
            f"이력이 필요하고, 그렇지 않으면 소유 조직을 지정하십시오."
            + (f" 한시 예외 {len(legacy)}건은 만료일(기본 {LEGACY_GRANDFATHER_UNTIL}) 까지만 "
               f"통과합니다." if legacy else "")
            + (f" ⚠️ **한시 예외 {len(legacy_expired)}건은 만료되어 이미 비노출입니다** — "
               f"소유 조직을 지정하거나 승인된 전사 공용으로 전환하십시오."
               if legacy_expired else "")
            + (f" ⚠️ 승인 대기 중인 전사 공용 {len(pending)}건은 보이지 않습니다."
               if pending else "")
            + (f" ⚠️ 조직 공유 {len(org_shared_empty)}건은 **공유 대상이 비어** 소유 조직만 "
               f"봅니다 — 공유했다고 믿는 쪽과 실제가 갈립니다." if org_shared_empty else "")
            + (f" ⚠️ 아무 표시도 없는 미지정 {len(hidden)}건은 보이지 않습니다 — 데이터가 "
               f"지워진 것이 아니라 범위 미지정으로 가려진 것입니다." if hidden else "")),
    }


def resolve_scope_ref(scope_ref: str) -> str:
    """부서 id 든 ECM node_id 든 노드로 정규화한다(D-005 — 두 형태 공존).

    해석 실패는 빈 문자열이다. 원본을 그대로 쓰면 존재하지 않는 범위에 갇혀 아무것도 안 보인다."""
    if not scope_ref:
        return ""
    try:
        from core.enterprise_context.resolver import ecm_resolver
        return ecm_resolver.resolve_scope_ref(scope_ref).get("node_id", "") or ""
    except Exception as e:
        print(f"⚠️ [scoping] 범위 해석 실패 '{scope_ref}': {e}")
        return ""
