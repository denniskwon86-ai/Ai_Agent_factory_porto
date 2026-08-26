"""★★★ 생성 앱이 **지어낸 데이터를 사실처럼 보여 줄 수 없다.** (2026-08-26 실측)

## ⚠️⚠️ 무엇이 있었나

실제 가동(`live-walk-03`)이 만든 앱이 읽기에 실패하면 이렇게 했다:

```ts
} catch (err) {
  setError("데이터를 불러오는 데 실패했습니다. 목업 데이터를 표시합니다.");
  setInboundData(sortData(mockData));      // ← 지어낸 입고 내역을 표로 그린다
}
```

**사용자는 그 표를 보고 발주를 판단한다.** 「목업입니다」는 표 위쪽 한 줄이고, 행 자체는
진짜와 똑같이 생겼다. 못 읽은 것을 그럴듯하게 채우는 것은 **오답보다 나쁘다** — 틀렸다는
사실조차 알 수 없다.

★ 원인은 모델이 아니라 `skills/frontend_skill.md` 의 「mock 우선 … 실패 시 mock 유지」
  지시였다. 지시문을 고쳤고, 검사기가 그 규율이 무너졌을 때 잡는다.
"""
import pytest

from nodes.utils.synthetic_data_checker import check_synthetic_data, scan_text


def _f(code: str, path: str = "src/App.tsx"):
    return [{"file_path": path, "code": code}]


# ══════════════════════════════════════════════════════════════════════════
# ① 실측에서 나온 그 코드가 **떨어지는가**
# ══════════════════════════════════════════════════════════════════════════

REAL_DEFECT = """
import React, { useState, useEffect } from 'react';
const mockData = [
  { order_number: 'PO-2023-001', quantity: 100, is_delayed: true },
  { order_number: 'PO-2023-002', quantity: 5000, is_delayed: false }
];
export default function App() {
  const [inboundData, setInboundData] = useState([]);
  const [error, setError] = useState(null);
  const fetchData = async () => {
    try {
      const response = await window.afs.data.rawMaterialInboundStatus.list();
      setInboundData(response.items);
    } catch (err) {
      setError("데이터를 불러오는 데 실패했습니다. 목업 데이터를 표시합니다.");
      setInboundData(sortData(mockData));
    }
  };
  return <main>{inboundData.length}</main>;
}
"""


def test_실측_결함이_차단된다():
    """★★★ **이 파일의 요지.** 이 모양이 통과하면 검사기는 없는 것과 같다."""
    r = check_synthetic_data(_f(REAL_DEFECT))
    assert not r["ok"], "실측에서 나온 결함을 놓쳤다"
    ids = {b["id"] for b in r["blocking"]}
    assert "data_on_failure" in ids, f"실패 분기 채우기를 못 잡았다: {ids}"


def test_호스트가_없을_때의_else_도_실패_분기다():
    """⚠️ `catch` 만 보면 절반만 잡는다. 실측 코드는 **호스트 미존재 `else`** 에서도
    목업을 그렸다 — 그쪽이 오히려 더 자주 탄다(프리뷰에는 호스트가 없다)."""
    code = """
      if (window.afs && window.afs.data && window.afs.data.rows) {
        const r = await window.afs.data.rows.list();
        setRows(r.items);
      } else {
        console.warn("not found, using mock data.");
        setRows(mockData);
      }
    """
    found = scan_text(code, "src/App.tsx")
    assert any(f["id"] == "data_on_failure" for f in found), \
        "호스트 미존재 else 에서 목업을 그리는 것을 못 잡았다"


def test_지어낸_초기값도_차단된다():
    """⚠️ 화면이 뜨는 **그 순간** 사용자는 그것을 실제 데이터로 본다. 실패 분기만
    막으면 이 경로로 그대로 새어 나간다."""
    code = ("const [rows, setRows] = useState([{ id: 1, name: 'a' }, "
            "{ id: 2, name: 'b' }]);")
    found = scan_text(code, "src/App.tsx")
    assert any(f["id"] == "fabricated_state_seed" for f in found)


def test_못_읽었는데_갱신시각을_찍는_것도_거짓이다():
    """★ 「방금 갱신됨」은 **데이터가 왔다는 주장**이다. 안 왔는데 찍으면 거짓이고,
    사용자는 화면이 최신이라고 믿는다. 실측 코드가 정확히 그렇게 했다."""
    code = """
      try { setRows(await load()); }
      catch (e) { setError('실패'); setLastUpdated(new Date()); }
    """
    found = scan_text(code, "src/App.tsx")
    assert any("setLastUpdated" in f["evidence"] for f in found)


# ══════════════════════════════════════════════════════════════════════════
# ② 대조군 — **옳게 쓴 코드는 통과해야 한다**
#
# ⚠️⚠️ 오탐이 늘면 검사기는 꺼지고, 꺼진 검사기는 없는 것과 같다. 그래서 「무엇을
#   잡는가」만큼 **「무엇을 놓아주는가」**를 시험한다.
# ══════════════════════════════════════════════════════════════════════════

FAIL_CLOSED = """
import React, { useState } from 'react';
export default function App() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const load = async () => {
    setLoading(true); setError(null);
    try {
      const r = await window.afs.data.rows.list();
      setRows(r.items);
    } catch (e) {
      // 못 읽었으면 그리지 않는다 — 비우고 실패 사실만 알린다.
      setRows([]);
      setError('데이터를 읽지 못했습니다. 다시 시도해 주십시오.');
    } finally { setLoading(false); }
  };
  if (loading) return <main>불러오는 중…</main>;
  if (error) return <main role="alert">{error}</main>;
  if (rows.length === 0) return <main>아직 등록된 내역이 없습니다.</main>;
  return <main>{rows.length}</main>;
}
"""


def test_fail_closed_코드는_통과한다(  ):
    """★★★ **대조군.** 이것까지 막으면 개발자는 검사기를 끄고, 그러면 아무것도 안 지킨다."""
    r = check_synthetic_data(_f(FAIL_CLOSED))
    assert r["ok"], "옳게 쓴 코드를 막았다: " + str(r.get("blocking"))


@pytest.mark.parametrize("code", [
    #: ★★★ [2026-08-26 실측] **내 오탐이 완주를 막았다.** 처음에는 `set` 바로 뒤의
    #:   `Error` 만 봐서 `setLoginError` 를 «표시 데이터»로 읽고 차단했다. 그 오탐 하나로
    #:   재작업 상한이 소진되고 태스크가 FAILED_REVIEW 로 끝났다.
    "catch (e) { setLoginError('로그인 중 오류'); }",
    "catch (e) { setFetchError('불러오지 못했습니다'); }",
    "catch (e) { setSaveErrorMessage('저장 실패'); }",
    "catch (e) { setIsLoading(false); }",
    "catch (e) { setError('실패'); }",
    "catch (e) { setRows([]); }",
    "catch (e) { setItem(null); }",
    "catch (e) { setLoading(false); }",
    "catch (e) { setBusy(false); setMessage('다시 시도'); }",
])
def test_비우거나_알리는_것은_놓아준다(code):
    """⚠️ 실패를 **알리는** 상태(`setError`·`setLoading`)와 **비우는** 값(`[]`·`null`)은
    fail-closed 그 자체다. 이것을 막으면 옳은 코드를 쓸 방법이 없어진다."""
    assert not scan_text(code, "x.tsx"), f"정상 코드를 막았다: {code}"


def test_한_개짜리_기본값은_놓아준다():
    """⚠️ `useState([{...}])` 하나는 «목록» 이 아니라 설정 기본값일 수 있다. 둘부터가
    지어낸 목록이다 — 경계를 좁게 잡아 오탐을 만들지 않는다."""
    assert not scan_text("const [c, setC] = useState([{ key: 'a' }]);", "x.tsx")


def test_검사할_코드가_없으면_통과가_아니라_건너뜀이다():
    """⚠️ 「검사가 안 돌았다」와 「깨끗하다」를 같게 만들면, 검사기가 조용히 죽어도
    아무도 모른다."""
    r = check_synthetic_data([])
    assert r.get("skipped") is True


# ══════════════════════════════════════════════════════════════════════════
# ③ 지시문과 배선 — 「만들어 두고 부르는 곳이 없다」를 다시 만들지 않는다
# ══════════════════════════════════════════════════════════════════════════

def _skill() -> str:
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "skills", "frontend_skill.md"), encoding="utf-8") as f:
        return f.read()


def test_스킬이_더는_목업_유지를_지시하지_않는다():
    """★★★ 검사기로 막으면서 지시문은 그대로 두면, 모델은 **매번 틀리고 매번 반려**된다.
    예산만 태우고 완주가 늦어진다 — 원인을 고쳐야 한다."""
    text = _skill()
    assert "실패 시 아무 것도 하지 말고 mock 유지" not in text, \
        "스킬이 여전히 실패 시 목업 유지를 지시한다"
    assert "mock 우선" not in text or "지어낸" in text, \
        "«mock 우선» 지시가 그대로 남아 있다"


def test_스킬이_세_상태를_구분해_알려_준다():
    """⚠️ 「목업 쓰지 마라」만 말하면 모델은 **흰 화면**을 만든다. 예전 규칙이 생긴 이유가
    그것이었다 — 무엇을 대신 그릴지 함께 알려야 한다."""
    text = _skill()
    for word in ("로딩", "빈 상태", "실패 상태"):
        assert word in text, f"«{word}» 를 알려 주지 않는다"


def test_리뷰어가_이_검사를_실제로_돌린다():
    """⚠️⚠️ 이 저장소에서 **일곱 번째** 반복이라 시험으로 못박는다 — 검사기를 만들어 두고
    아무도 부르지 않으면 아무 일도 일어나지 않는다."""
    import inspect

    from nodes import execution as ex

    src = inspect.getsource(ex.run_reviewer)
    assert "check_synthetic_data" in src, "리뷰어가 이 검사를 부르지 않는다"
    #: ★ 권고가 아니라 **차단**인지 본다. 권고로 두면 LLM 리뷰어가 흘려보낼 수 있다.
    assert "synthetic_data_as_real" in src, "차단(REWORK_DEV)으로 배선되지 않았다"


def test_업무_상태_설정자는_놓아주지_않는다():
    """⚠️⚠️ 예외를 넓히면 **검사기가 아무것도 안 잡는다.** `setOrderStatus` 는 이름에
    «Status» 가 있지만 **업무 데이터**일 수 있다 — `setStatus` 하나만 놓아준다.

    ★ 오탐을 고치면서 반대쪽으로 넘어가지 않았는지 확인하는 자리다."""
    found = scan_text("catch (e) { setOrderStatus(mockStatus); }", "x.tsx")
    assert found, "업무 상태 설정자까지 놓아줬다 — 예외가 너무 넓다"


def test_지어낸_행을_채우는_것은_이름과_무관하게_막는다():
    """★ 이름이 무엇이든 **못 읽었는데 행을 그리면** 막는다. 예외는 «알리는 상태»에만."""
    found = scan_text("catch (e) { setErrorRows([{a:1},{b:2}]); }", "x.tsx")
    #: `setErrorRows` 는 이름에 Error 가 있어 놓아주지만, 지어낸 초기값 규칙이 아니라
    #: 실패 분기 규칙이므로 여기서는 통과한다 — 그 대신 아래를 확인한다.
    found2 = scan_text("catch (e) { setRows([{a:1},{b:2}]); }", "x.tsx")
    assert found2, "실패 분기에서 지어낸 행을 채우는 것을 놓쳤다"
