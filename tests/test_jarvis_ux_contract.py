"""★ [UI 설계서 §7 Atlas UX 계약] 비서가 **넘지 말아야 할 선**을 고정한다.

## 왜 이 테스트가 필요한가

§7.3 은 한 문장으로 못박는다 — 「Atlas 가 **직접 DB 를 수정하거나 권한 검증을 우회하지
않는다**」. 비서는 자연어로 무엇이든 요청받으므로, 편의를 위해 「그럼 내가 대신 해 줄게」를
한 번 열어 주면 그 순간 **모든 도메인 통제를 우회하는 뒷문**이 된다. 권한은 각 도메인
라우터가 판정하는데, 비서 경로로 들어가면 그 판정을 지나치기 때문이다.

## 답변 형식도 계약이다 (§7.2)

「부족하거나 확인하지 못한 데이터」를 적게 하지 않으면 비서는 모르는 것도 아는 것처럼
말한다. 이 저장소가 화면 전체에서 지켜 온 «조회 실패 ≠ 0건» 이 비서 답변에서만 무너지면
아무 의미가 없다.

⚠️ 이 테스트는 **LLM 을 호출하지 않는다.** 프롬프트에 형식 지시가 실리는지, 라우터가 쓰기를
  하지 않는지만 본다 — 계약은 코드에 있고, 모델 출력에 걸어 둘 수 있는 것이 아니다.
"""
import inspect
import re

from api.routes import jarvis_control


def test_atlas_라우터는_DB_를_직접_고치지_않는다():
    """★★ §7.3 의 핵심. 비서 경로에 쓰기가 생기면 도메인 권한 판정을 통째로 우회한다."""
    src = inspect.getsource(jarvis_control)
    #: 주석·문자열이 아닌 **실제 호출**만 본다.
    code = "\n".join(
        l.split("#")[0] for l in src.split("\n") if not l.strip().startswith("#"))
    forbidden = [
        r"\.execute\(", r"\bINSERT\s+INTO\b", r"\bUPDATE\s+\w+\s+SET\b",
        r"\bDELETE\s+FROM\b", r"\.commit\(", r"\.upsert\(",
    ]
    hits = [p for p in forbidden if re.search(p, code, re.IGNORECASE)]
    assert not hits, (
        f"Jarvis 라우터에 쓰기로 보이는 호출이 있습니다: {hits}. §7.3 은 «Atlas 가 직접 DB 를 "
        f"수정하지 않는다» 고 못박았습니다 — 쓰기가 필요하면 **도메인 API 를 거쳐** 그쪽의 "
        f"권한 판정을 받아야 합니다.")


def test_모든_경로가_주체_판정을_거친다():
    """권한 검증 우회 금지(§7.3). `current_principal` 없이 열린 경로가 있으면 익명이 문맥을
    질의할 수 있게 된다."""
    src = inspect.getsource(jarvis_control)
    routes = re.findall(r"@router\.(get|post|put|delete)\(([^)]*)\)\s*\nasync def (\w+)\(([^)]*)",
                        src, re.MULTILINE)
    assert routes, "라우트를 찾지 못했습니다 — 이 테스트가 무의미해졌습니다."
    for _method, _path, name, args in routes:
        assert "current_principal" in args, (
            f"`{name}` 이 주체 판정을 거치지 않습니다 — 비서 경로는 익명에게 열리면 안 됩니다.")


def _prompt_text(fn) -> str:
    """함수 소스에서 **주석을 걷어낸** 본문.

    ⚠️ 이 헬퍼가 없으면 테스트가 «주석에만 적혀 있어도 통과» 한다. 실제로 그랬다 — 머리말을
      프롬프트에서 지워도 위쪽 설명 주석에 같은 낱말이 남아 있어 초록이었다. 계약을 지키는
      것은 주석이 아니라 **모델에게 실제로 나가는 문자열**이다."""
    src = inspect.getsource(fn)
    return "\n".join(l.split("#")[0] for l in src.split("\n"))


def test_답변_형식_여섯_단이_프롬프트에_실린다():
    """§7.2 답변 패턴. 형식을 요구하지 않으면 «핵심 답변» 만 있는 검증 불가능한 답이 온다."""
    body = _prompt_text(jarvis_control.ask)
    for label in ["핵심 답변", "왜 그렇게 판단했는가", "근거와 기준시각",
                  "부족하거나 확인하지 못한 데이터", "선택 가능한 다음 행동",
                  "실행 시 영향과 승인 필요 여부"]:
        assert label in body, (
            f"답변 형식에 «{label}» 이 빠졌습니다(§7.2). 주석이 아니라 **프롬프트 문자열**에 "
            f"있어야 합니다 — 모델에게 나가지 않는 규칙은 규칙이 아닙니다.")


def test_모르는_것을_말하라는_지시가_남아_있다():
    """★ 여섯 중 **④** 가 이 계약의 핵심이다.

    ⚠️ 추측 금지 지시가 사라지면 비서는 문맥에 없는 수치를 지어내고, 사용자는 그것을 근거로
      되돌릴 수 없는 결정을 한다."""
    body = _prompt_text(jarvis_control.ask)
    assert "추측하지" in body, "문맥 밖 추측을 금지하는 지시가 사라졌습니다."
    assert "확인할 수 없다" in body, "«확인할 수 없다» 고 말하라는 지시가 사라졌습니다."


def test_화면이_보낸_범위를_그대로_믿지_않는다():
    """비서 문맥에 회사·부서 범위가 실리는데, 그것을 화면 값으로 채우면 화면을 조작해
    남의 범위를 조회할 수 있게 된다 — 서버 판정(`p.scope`)을 써야 한다."""
    src = inspect.getsource(jarvis_control.ask)
    assert "p.scope" in src, "요청자 범위를 서버가 판정하지 않고 있습니다(§7.3 권한 우회 금지)."


def test_엔진이_삼킨_실패가_success_로_나가지_않는다():
    """★★★ [2026-08-20 실측] **엔진은 예외를 던지지 않는다.**

    `supervisor_daemon.handle_user_chat` 은 LLM 실패를 잡아서
    `{"status": "error", "reply": "…오류가 발생했습니다"}` 를 **돌려준다.** 그래서 라우트의
    `except` 는 한 번도 돌지 않았고, API 키가 없어 답을 못 만든 상황이 그대로
    **HTTP 200 «success»** 로 나갔다.

    ⚠️ 이 파일이 지키려는 것과 같은 종류의 사고다 — 비서가 «답한 것처럼» 보이면 사용자는
      그 내용을 근거로 판단한다. 봉투의 `status` 를 보는 호출부는 «성공» 으로 읽는다.
    ⚠️ LLM 을 부르지 않는다. 소스에 그 분기가 있는지만 본다."""
    src = inspect.getsource(jarvis_control.ask)
    assert 'get("status", "")) == "error"' in src, (
        "엔진이 돌려준 error 상태를 라우트가 보지 않는다 — 실패가 success 로 나간다")
    #: ★ 그리고 **502** 여야 한다. 200 으로 답하면 화면이 그것을 답으로 그린다.
    m = re.search(r'== "error"[\s\S]{0,400}?status_code=502', src)
    assert m, "엔진 실패를 502 로 바꾸지 않는다"


def test_비서_실패_사유를_사용자에게_전달한다():
    """⚠️ 「받지 못했습니다」만 남으면 사용자는 무엇이 문제인지 알 수 없다 — 엔진이 준
    사유를 그대로 싣는다(그 사유는 사용자에게 보일 문장이다)."""
    src = inspect.getsource(jarvis_control.ask)
    assert 'get("reply")' in src, "실패 사유를 버리고 고정 문장만 돌려준다"
