"""[D-017 §9 P4-4 · 절반] 자산 중복 탐지 — **LLM 0콜.**

## 왜 「미사용」이 여기 없는가

P4-4 는 「미사용·중복 정리 제안」이다. 그런데 **「미사용」을 판단할 근거가 없다**(2026-08-07 실측):

· `agent_assets` 에 사용 이력 필드가 **없다**(`last_used_at`·`usage_count` 모두 없음)
· 텔레메트리의 에이전트 축 관측률이 **8%**(89/1133)

이 상태에서 「호출 0건 = 미사용」이라고 제안하면 **관측되지 않았을 뿐인 자산을 지우라고
말하게 된다.** 그리고 제안을 받은 사람은 확인할 방법이 없다 — 화면이 「0건」이라고 하니까.

★ 그래서 미사용 항목을 **만들지 않는다.** 대신 «사용 이력이 없어 제공하지 않습니다» 를
  문장으로 낸다(`UNUSED_NOT_AVAILABLE`). ⚠️ **빈 목록으로 두면 「정리할 것이 없다」로 읽힌다.**

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
        "unused": {"available": False, "note": UNUSED_NOT_AVAILABLE},
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
