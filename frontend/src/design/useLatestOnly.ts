// [UI 설계서 §6.1] 「비동기 응답 적용 전 **요청 시점의 scope/project 와 현재 문맥이 같은지
// 재검증**한다.」
//
// ## 무엇을 막는가 — 늦게 온 응답이 다른 선택 위에 그려지는 일
//
// 사용자가 릴리스 A 를 고르고, 응답이 오기 전에 B 를 고른다. 서버·네트워크 사정으로 A 의
// 응답이 **나중에** 도착하면, 화면은 「B 를 보고 있다」고 말하면서 **A 의 데이터**를 그린다.
//
//   화면 제목:  release_B          ← 사용자가 고른 것
//   게이트 판정: 승격 가능          ← 실제로는 release_A 의 판정
//
// 이건 느린 화면이 아니라 **틀린 화면**이다. 승격 가능 여부·기준선 비교·권한 범위처럼 판단의
// 근거가 되는 값에서 이 일이 일어나면, 사용자는 잘못된 근거로 되돌릴 수 없는 결정을 한다.
// 조직 전환은 `location.reload()` 라 안전하지만, **화면 안에서 고르는 축**은 그렇지 않다.
//
// ## 왜 화면마다 쓰지 않고 훅으로 만드는가
//
// `let alive = true` 를 화면마다 손으로 넣으면 **반드시 빠지는 곳이 생긴다.** 이 저장소가
// `HubDialog` 에서 `role="dialog"`·포커스 트랩을 셸로 올린 것과 같은 이유다 — 규칙은 한 곳에
// 두고 화면은 쓰기만 한다.
//
// ## 쓰는 법
//
//   const claim = useLatestOnly();
//
//   const open = async (id: string) => {
//     const isCurrent = claim();          // ① 요청 직전에 표를 뽑는다
//     const data = await api.get(id);
//     if (!isCurrent()) return;           // ② 그 사이 다른 것을 골랐으면 **버린다**
//     setDetail(data);
//   };
//
// ⚠️ `claim()` 은 **요청을 시작하기 직전**에 부른다. `await` 뒤에 부르면 자기 자신을 최신으로
//   여겨 아무 것도 막지 못한다.
//
// ⚠️ 버린 응답을 오류로 표시하지 않는다 — 사용자는 이미 다른 것을 보고 있고, 그 화면에 뜬
//   오류는 **지금 보고 있는 것이 실패했다**는 뜻으로 읽힌다.
import { useCallback, useEffect, useRef } from 'react';

export function useLatestOnly() {
  const seq = useRef(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    // 화면이 사라진 뒤의 setState 도 함께 막는다 — 모달을 닫자마자 응답이 오는 경우다.
    return () => { mounted.current = false; };
  }, []);

  /** 요청 직전에 부른다. 돌려받은 함수가 `false` 면 **그 응답은 버려야 한다.** */
  return useCallback(() => {
    const mine = ++seq.current;
    return () => mounted.current && seq.current === mine;
  }, []);
}
