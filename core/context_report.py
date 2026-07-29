"""프롬프트 컨텍스트 구성 계측 — **"무엇이 얼마나 들어갔나"를 호출 단위로 남긴다.**

## 왜 필요한가 (2026-07-29, A-1 카나리 선행)

D-010 으로 기준정보를 전수 주입하기로 하면서 프롬프트의 기준정보 블록이 ≈2,200자 →
≈5,300자가 됐다. 그런데 **그 판단이 옳았는지 판정할 데이터가 없다.** 지금 남는 것은
`input_tokens` 총량뿐이라 "토큰이 늘었다"까지만 알 수 있고, 늘어난 것이 기준정보인지
지식팩인지 파일인지, 그래서 **기술 명세가 밀려났는지**는 알 수 없다.

실제로 2026-07-29 에 그 일이 일어났다 — 기준정보 블록 하나가 예산 20,000자를 전부 삼켜
코더가 API 계약을 못 봤다. 그때는 사람이 눈으로 발견했다. 같은 것을 **자동으로** 보려면
블록별 길이가 남아야 한다.

## 설계

- **contextvars 를 쓴다.** 스웜은 에이전트 3개를 같은 프로세스에서 병렬로 돌린다. 모듈 전역
  변수에 담으면 서로의 컨텍스트 보고서를 덮어써 **엉뚱한 호출에 붙는다**. contextvar 는
  async task 단위로 격리되므로 생산자(ContextEngine)와 소비자(게이트웨이)가 같은 호출에서만 만난다.
- **길이는 문자 수로 남긴다.** 토큰은 모델마다 다르고, 여기서 재추정하면 게이트웨이의
  실측 토큰과 어긋난 두 개의 숫자가 생긴다. 문자 수는 우리가 직접 만든 값이라 정확하다.
- **참조된 지식팩은 팩 id·파일명·거리까지** 남긴다. "지식팩을 연결했다"와 "그 지식이 실제로
  주입됐다"는 다르다 — 후자를 못 보면 그라운딩이 됐는지 알 수 없다.
"""
from contextvars import ContextVar
from typing import Any, Dict, List

_ctx_report: ContextVar[Dict[str, Any]] = ContextVar("_ctx_report", default=None)


def start() -> Dict[str, Any]:
    """이번 호출의 컨텍스트 보고서를 연다(ContextEngine 이 조립을 시작할 때)."""
    rep: Dict[str, Any] = {"blocks": {}, "total_chars": 0, "clipped": False,
                           "knowledge_packs": [], "knowledge_hits": []}
    _ctx_report.set(rep)
    return rep


def add_block(name: str, text: str) -> None:
    """블록 하나의 길이를 기록한다. 빈 블록은 남기지 않는다(0 이 줄지어 있으면 읽기 어렵다)."""
    rep = _ctx_report.get()
    if rep is None or not text:
        return
    rep["blocks"][name] = rep["blocks"].get(name, 0) + len(text)


def note_knowledge(hits: List[Dict[str, Any]]) -> None:
    """실제로 주입된 지식 청크의 출처. **연결된 팩 목록이 아니라 주입된 것**이다."""
    rep = _ctx_report.get()
    if rep is None or not hits:
        return
    for h in hits:
        meta = h.get("metadata", {}) or {}
        pid = meta.get("pack_id", "?")
        if pid not in rep["knowledge_packs"]:
            rep["knowledge_packs"].append(pid)
        rep["knowledge_hits"].append({
            "pack_id": pid,
            "filename": meta.get("filename", "?"),
            "page": meta.get("page"),
            "distance": round(float(h.get("distance", 0.0)), 4),
        })


def finish(total_text: str, budget: int) -> None:
    """조립 완료. 총량과 **절단 여부**를 남긴다.

    절단은 그 자체가 사건이다 — 예산을 넘겼다는 것은 뒤쪽 블록(보통 기술 명세·파일)이
    잘렸다는 뜻이고, 그게 2026-07-29 회귀의 정확한 형태였다."""
    rep = _ctx_report.get()
    if rep is None:
        return
    rep["total_chars"] = len(total_text or "")
    rep["budget_chars"] = budget
    rep["clipped"] = rep["total_chars"] >= budget


def current() -> Dict[str, Any]:
    """게이트웨이가 로그를 쓸 때 읽는다. 없으면 빈 dict(계측 부재를 0 으로 위장하지 않는다)."""
    return _ctx_report.get() or {}
