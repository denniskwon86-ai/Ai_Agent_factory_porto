"""[D-017 §9 P4-4] 자산 정리 제안 — 중복 · 사용 기록 없음. **LLM 0콜.**

## 「미사용」이 왜 뒤늦게 들어왔는가

착수 시점(2026-08-07 오전)에는 **「미사용」을 판단할 근거가 없었다**:

· `agent_assets` 에 사용 이력 필드가 **없다**(`last_used_at`·`usage_count` 모두 없음)
· 텔레메트리의 에이전트 축 관측률이 **8%**(89/1133)

이 상태에서 「호출 0건 = 미사용」이라고 제안하면 **관측되지 않았을 뿐인 자산을 지우라고
말하게 된다.** 그리고 제안을 받은 사람은 확인할 방법이 없다 — 화면이 「0건」이라고 하니까.
그래서 그때는 항목을 만들지 않고 사유만 냈다(P4-4 = 0.5).

★ 지금은 **관측을 만들었다**(`core/asset_usage.py`). 자산이 실제로 해석되는 두 지점에서
  직접 기록하므로, 귀속률 8% 짜리 간접 추정에 기대지 않는다.

⚠️⚠️ 그런데 관측은 **켠 시점부터** 쌓인다 — 다음 날이면 전부 「사용 기록 없음」이다.
  그래서 `find_unused` 는 관측 기간이 짧으면 **목록을 만들지 않고** 언제부터 볼 수 있는지를
  문장으로 낸다. **빈 목록으로 두면 「정리할 것이 없다」로 읽힌다.**

⚠️ 이름을 「미사용」이 아니라 **「사용 기록 없음」** 으로 쓴다. 이 모듈이 아는 것은
  「관측 이후 본 적이 없다」뿐이다.

## 중복은 지금 판단할 수 있다 — 내용 비교이므로 사용 이력이 필요 없다

| 구분 | 기준 | 취급 |
|---|---|---|
| **동일** | 정규화 후 내용이 완전히 같다 | 정리 **제안** (확신 높음) |
| **유사** | 정규화 후 유사도 ≥ `SIMILAR_THRESHOLD` | **검토 대상** (확신 낮음) |

★ 둘을 **분리해서** 낸다(사용자 결정 2026-08-07, 안 B). 확신의 차이를 화면에서 지우면
  사람은 목록 전체를 같은 무게로 읽고, 한 번 잘못 지우면 다시는 이 목록을 쓰지 않는다.

⚠️ **의미까지 비교하지 않는다.** LLM 으로 「비슷한 스킬」을 판정하면 근거를 설명할 수 없고,
  설명할 수 없는 삭제 제안은 아무도 실행하지 않는다. 그리고 §6.1 이 품질 판정에 대해
  「단순 LLM 평가 금지」를 못박았다.

## ⚠️ 제안은 «지워라» 가 아니라 «둘 중 하나를 고르라» 다

어느 쪽이 정본인지는 사람이 안다. 그리고 **자동 삭제 경로를 만들지 않는다** — 스킬 파일은
에이전트 정의가 **이름으로** 참조하므로, 지우는 순간 그 에이전트는 기본 스킬로 **조용히
강등**된다(`agent_registry.agent_skill(…, default=…)`). 그 강등은 오류를 내지 않는다.
"""
from __future__ import annotations

import hashlib
import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

#: 「유사」로 볼 최소 유사도. ⚠️ 낮추면 목록이 소음이 되고, 소음이 되면 아무도 보지 않는다.
SIMILAR_THRESHOLD = 0.90

#: 비교 상한. 전량 쌍 비교는 O(n²)이라 재고가 커지면 응답이 죽는다.
MAX_ITEMS = 300

UNUSED_NOT_AVAILABLE = (
    "사용 이력이 기록되지 않아 «미사용» 판단을 제공하지 않습니다. "
    "자산 저장소에 사용 이력 필드가 없고, 실행 로그의 에이전트 귀속률이 낮습니다 — "
    "이 상태에서 «호출 0건 = 미사용» 이라고 제안하면 관측되지 않았을 뿐인 자산을 "
    "지우라고 말하게 됩니다. **«정리할 것이 없다» 는 뜻이 아닙니다.**")

#: 마크다운 주석 머리말·YAML front matter — 내용이 같아도 여기만 다른 경우가 흔하다.
_FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def normalize(text: str) -> str:
    """비교용 정규화. **의미를 바꾸지 않는 차이만** 지운다.

    ⚠️ 지나치게 지우면 서로 다른 스킬이 «동일» 로 묶인다 — 그 오탐 하나가 목록 전체의
      신뢰를 깎는다. 그래서 공백·주석·front matter 까지만 건드린다."""
    t = text or ""
    t = _FRONT_MATTER.sub("", t)
    t = _HTML_COMMENT.sub("", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip()


def _digest(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()[:16]


def collect_items() -> Dict[str, Any]:
    """비교 대상. 각 원천은 **읽었는지**를 함께 들고 온다."""
    items: List[Dict[str, str]] = []
    errors: List[str] = []

    # ── 파일 스킬 ──────────────────────────────────────────────────────────
    try:
        root = "skills"
        for name in sorted(os.listdir(root))[:MAX_ITEMS]:
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    items.append({"id": name, "kind": "file_skill", "where": path,
                                  "text": f.read()})
            except Exception as e:
                errors.append(f"{path}: {e}")
    except FileNotFoundError:
        pass                            # 스킬 폴더가 없다 — 확인된 0건
    except OSError as e:
        errors.append(f"skills/: {e}")

    # ── DB 자산 ────────────────────────────────────────────────────────────
    try:
        import json as _json

        from core.agent_assets import agent_assets
        for kind in ("agent", "skill", "workflow"):
            for a in (agent_assets.list_assets(kind, None, "", include_retired=False) or []):
                body = a.get("body")
                items.append({
                    "id": str(a.get("asset_id") or a.get("id") or ""),
                    "kind": f"asset_{kind}",
                    "where": f"agent_assets/{kind}",
                    "text": body if isinstance(body, str) else _json.dumps(
                        body or {}, sort_keys=True, ensure_ascii=False),
                })
    except Exception as e:
        errors.append(f"agent_assets: {e}")

    return {"items": items[:MAX_ITEMS], "errors": errors}


def find_unused(items: Optional[List[Dict[str, str]]] = None,
                usage: Optional[Dict[str, Any]] = None,
                days_observed: Optional[float] = None,
                observed_since: str = "",
                min_days: Optional[int] = None,
                stale_days: Optional[int] = None) -> Dict[str, Any]:
    """[P4-4 나머지 절반] 「관측 이후 사용 기록이 없는」 자산.

    ★★ **«미사용» 이라고 부르지 않는다.** 이 함수가 아는 것은 「관측을 켠 뒤로 이 자산이
      해석되는 것을 본 적이 없다」뿐이다. 관측 이전의 사용과, 기록 지점을 지나지 않는 경로의
      사용은 여기에 없다. 그 차이를 이름에서 지우면 사람은 목록을 «지워도 되는 것» 으로 읽는다.

    ⚠️⚠️ **관측 기간이 `MIN_OBSERVATION_DAYS` 에 못 미치면 목록을 만들지 않는다.**
      관측을 켠 다음 날이면 자산 전부가 여기 오르고, 화면은 「31개 전부 정리 대상」이라고
      말한다. 그것을 본 사람은 전부 지우고, 지운 뒤에야 그것이 「안 쓰인 것」이 아니라
      「아직 안 본 것」이었음을 안다 — P4-2 의 부서 귀속률 0% 와 같은 함정이다.
      그때는 목록 대신 **언제부터 볼 수 있는지**를 문장으로 낸다.

    ⚠️ 빈 목록을 「정리할 것이 없다」로 읽히게 두지 않는다 — `note` 가 항상 이유를 말한다."""
    from core.asset_usage import (
        MIN_OBSERVATION_DAYS, STALE_AFTER_DAYS, asset_usage,
    )
    min_days = MIN_OBSERVATION_DAYS if min_days is None else min_days
    stale_days = STALE_AFTER_DAYS if stale_days is None else stale_days

    rows = collect_items()["items"] if items is None else items
    if usage is None:
        usage = asset_usage.usage_map()
    if days_observed is None:
        days_observed = asset_usage.days_observed()
    observed_since = observed_since or asset_usage.observed_since()

    window = {
        "observed_since": observed_since,
        "days_observed": round(float(days_observed), 2),
        "min_observation_days": min_days,
        "stale_after_days": stale_days,
    }

    if not observed_since:
        return {"available": False, "items": [], "window": window,
                "note": ("사용 관측이 아직 시작되지 않았습니다 — «사용 기록 없음» 판단을 "
                         "제공하지 않습니다. **«정리할 것이 없다» 는 뜻이 아닙니다.**")}

    if days_observed < min_days:
        _left = max(0.0, min_days - days_observed)
        return {
            "available": False, "items": [], "window": window,
            # ★ 「아직」임을 분명히 하고 **언제부터 볼 수 있는지**를 말한다. 그래야 사람이
            #   이 화면을 다시 열 이유를 갖는다.
            "note": (f"사용 관측을 시작한 지 {days_observed:.1f}일밖에 되지 않아 «사용 기록 없음» "
                     f"목록을 만들지 않습니다(최소 {min_days}일). 지금 목록을 만들면 아직 한 번도 "
                     f"돌지 않았을 뿐인 자산이 전부 정리 대상으로 보입니다 — 약 {_left:.1f}일 뒤에 "
                     f"제공됩니다. **«정리할 것이 없다» 는 뜻이 아닙니다.**"),
        }

    stale_before = asset_usage.stale_before(stale_days)
    out: List[Dict[str, Any]] = []
    for it in rows:
        u = usage.get(it["id"]) or {}
        last = str(u.get("last_used_at") or "")
        if last and last >= stale_before:
            continue                       # 최근에 쓰였다
        out.append({
            "id": it["id"], "kind": it["kind"], "where": it["where"],
            # ⚠️ 「본 적 없음」과 「오래 전에 봤음」은 다르다 — 후자는 근거가 있는 판단이고
            #   전자는 관측 구멍일 수도 있다. 화면이 둘을 구분할 수 있어야 한다.
            "last_used_at": last,
            "use_count": int(u.get("use_count") or 0),
            "basis": "never_observed" if not last else "stale",
        })
    out.sort(key=lambda x: (x["basis"] != "stale", x["last_used_at"] or "", x["id"]))

    never = sum(1 for x in out if x["basis"] == "never_observed")
    return {
        "available": True,
        "items": out,
        "window": window,
        "note": (
            f"관측 시작({observed_since[:10]}) 이후 {days_observed:.0f}일간 "
            f"{len(rows)}개 중 {len(out)}개가 최근 {stale_days}일 내 사용 기록이 없습니다"
            f"(그중 {never}개는 관측 이후 한 번도 보이지 않았습니다). "
            f"⚠️ 이것은 «미사용» 이 아니라 «관측되지 않음» 입니다 — 관측 이전의 사용과 "
            f"기록 지점을 지나지 않는 경로의 사용은 여기에 잡히지 않습니다."),
    }


def _unused_or_reason(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    """`find_unused` 를 부르되, 실패를 **«없음» 이 아니라 «못 읽었다»** 로 낸다.

    ⚠️ 관측 저장소가 죽었을 때 빈 목록을 내면 「정리할 것이 없다」로 읽힌다 —
      `org_operations.Metric` 이 세운 규칙과 같다."""
    try:
        return find_unused(rows)
    except Exception as e:
        return {"available": False, "items": [], "window": {},
                "note": (f"사용 관측을 읽지 못해 «사용 기록 없음» 판단을 제공하지 않습니다"
                         f"({type(e).__name__}: {e}). "
                         f"**«정리할 것이 없다» 는 뜻이 아닙니다.**")}


def find_duplicates(items: Optional[List[Dict[str, str]]] = None,
                    threshold: float = SIMILAR_THRESHOLD) -> Dict[str, Any]:
    """동일·유사 묶음. **둘을 분리해서** 돌려준다(사용자 결정 2026-08-07 안 B)."""
    src = collect_items() if items is None else {"items": items, "errors": []}
    rows = src["items"]

    # ── 동일 — 해시가 같다 ────────────────────────────────────────────────
    by_hash: Dict[str, List[Dict[str, str]]] = {}
    for it in rows:
        by_hash.setdefault(_digest(it["text"]), []).append(it)
    identical = [
        {"fingerprint": h,
         "members": [{"id": m["id"], "kind": m["kind"], "where": m["where"]} for m in ms]}
        for h, ms in by_hash.items() if len(ms) > 1
    ]
    dup_ids = {m["id"] for g in identical for m in g["members"]}

    # ── 유사 — 동일로 이미 묶인 것은 제외한다 ─────────────────────────────
    # ⚠️ 같은 항목을 두 목록에 올리면 사용자가 두 번 판단하게 되고, 목록의 신뢰가 깎인다.
    rest = [it for it in rows if it["id"] not in dup_ids]
    similar: List[Dict[str, Any]] = []
    for i in range(len(rest)):
        for j in range(i + 1, len(rest)):
            a, b = rest[i], rest[j]
            ratio = SequenceMatcher(None, normalize(a["text"]), normalize(b["text"])).ratio()
            if ratio >= threshold:
                similar.append({
                    "similarity": round(ratio, 4),
                    "members": [{"id": x["id"], "kind": x["kind"], "where": x["where"]}
                                for x in (a, b)],
                })
    similar.sort(key=lambda x: -x["similarity"])

    return {
        # ★ 확신이 높은 것 — «정리 제안»
        "identical": identical,
        # ★ 확신이 낮은 것 — «검토 대상». 같은 목록에 섞지 않는다.
        "similar": similar,
        # [P4-4 나머지 절반] 관측이 섰으므로 이제 판단한다 — 다만 관측 기간이 짧으면
        #   `find_unused` 가 스스로 `available=False` 와 사유를 낸다.
        #   ⚠️ 실패해도 중복 목록까지 죽이지 않는다(중복은 사용 이력과 무관하게 유효하다).
        "unused": _unused_or_reason(rows),
        "coverage": {
            "compared": len(rows),
            "errors": src["errors"],
            "threshold": threshold,
            "note": (f"{len(src['errors'])}개 원천을 읽지 못해 비교에서 빠졌습니다 — "
                     f"«중복이 없다» 는 뜻이 아닙니다." if src["errors"] else ""),
        },
        "action_note": ("제안은 «지우십시오» 가 아니라 «둘 중 어느 쪽이 정본인지 고르십시오» "
                        "입니다. ⚠️ 스킬 파일을 지우면 그것을 이름으로 참조하던 에이전트는 "
                        "**기본 스킬로 조용히 강등**되며, 그 강등은 오류를 내지 않습니다."),
    }
