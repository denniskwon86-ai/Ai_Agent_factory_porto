# ==========================================
# 관대한 JSON 파서 — LLM의 비정형 JSON을 견고하게 복구한다.
# 흔한 실패 원인(코드펜스, 선행/후행 잡텍스트, 트레일링 콤마, 단일따옴표)을 단계적으로 교정.
# critic(토론 비평)·judge(채점) 응답이 파싱 실패로 '소리 없이 유실'되는 것을 방지한다.
# ==========================================
import re
import json


def loads_lenient(text) -> dict:
    """LLM 응답에서 단일 JSON 객체를 최대한 복구해 dict로 반환. 실패 시 빈 dict."""
    s = str(text or "").strip()
    if not s:
        return {}

    # 1) 마크다운 코드펜스 내부만 추출
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", s)
    if fence:
        s = fence.group(1).strip()

    # 2) 최외곽 중괄호 블록만 추출(앞뒤 인사말/부연 제거)
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        s = m.group(0)

    # 3) 원문 → 트레일링 콤마 제거본 순으로 시도
    no_trailing = re.sub(r",(\s*[}\]])", r"\1", s)
    for candidate in (s, no_trailing):
        try:
            obj = json.loads(candidate)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            continue

    # 4) 최후의 보루: 단일따옴표 → 쌍따옴표(보수적)
    try:
        obj = json.loads(no_trailing.replace("'", '"'))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}
