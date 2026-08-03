// [UIUX 공통] 허브 모달 기반 — **CL-2~5 가 모두 이것을 쓴다.**
//
// ## 왜 셸에 넣는가 (2026-08-03 교차검토 지적 1)
//
// CL-1 을 "모달처럼 보이는 div" 로 만들었더니 실제로는 모달이 아니었다:
//   · `role="dialog"` · `aria-modal` 없음 → 스크린리더에 그냥 문서 일부로 읽힌다
//   · 배경 화면의 포커스 요소 29개가 **Tab 순서에 그대로 남아** 있었다 — 사용자가 Tab 을
//     누르면 보이지 않는 뒤쪽 버튼으로 포커스가 사라진다
//   · Escape 닫기 · 닫은 뒤 포커스 복귀 · 배경 스크롤 잠금 전부 없음
//
// ⚠️ 이건 CL-1 만의 문제가 아니다. 화면 4개를 같은 방식으로 더 만들면 **같은 결함이 5개로
//   복제**된다. 그래서 화면이 아니라 셸에 넣는다.
//
// ## 구현 방식
//
// `createPortal` 로 `document.body` 에 붙이고 `#root` 에 `inert` 를 건다. 이렇게 하면 배경 전체가
// 접근성 트리·포커스·클릭에서 한 번에 빠진다 — 요소를 하나씩 `tabindex=-1` 로 막는 방식은
// 반드시 누락이 생긴다(이 저장소가 `fetch` 78곳에서 배운 것과 같은 이유).
import { useCallback, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

import './afs.css';

/** 포커스 가능한 요소 — 숨겨진 것·disabled 는 제외한다. */
function focusables(root: HTMLElement): HTMLElement[] {
  const sel = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),'
    + 'textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
  return Array.from(root.querySelectorAll<HTMLElement>(sel))
    .filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    });
}

export function HubDialog({ label, onClose, children }: {
  /** 스크린리더가 읽는 이름. 비우면 "대화상자"로만 읽혀 무엇인지 알 수 없다. */
  label: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  // 열릴 때: 포커스 원위치 기억 → 배경 차단 → 첫 요소로 포커스
  useEffect(() => {
    restoreRef.current = (document.activeElement as HTMLElement) || null;

    const root = document.getElementById('root');
    root?.setAttribute('inert', '');

    // ★ 배경 스크롤 잠금. 이것이 **문서 기준 가로 오버플로도 함께 막는다**(지적 2) —
    //   기존 헤더가 넘치더라도 모달이 열린 동안 사용자에게 스크롤바가 보이지 않는다.
    const prev = { overflow: document.body.style.overflow };
    document.body.style.overflow = 'hidden';

    const first = boxRef.current ? focusables(boxRef.current)[0] : null;
    // 포커스 대상이 없으면 상자 자체에 준다 — 어디에도 포커스가 없으면 Escape 도 안 먹는다.
    (first || boxRef.current)?.focus?.();

    return () => {
      root?.removeAttribute('inert');
      document.body.style.overflow = prev.overflow;
      // 닫은 뒤 **열었던 버튼으로 돌아간다.** 없으면 사용자는 문서 맨 위로 튕긴다.
      restoreRef.current?.focus?.();
    };
  }, []);

  // Escape 닫기 + 포커스 트랩
  const onKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== 'Tab' || !boxRef.current) return;
    const list = focusables(boxRef.current);
    if (list.length === 0) return;
    const firstEl = list[0];
    const lastEl = list[list.length - 1];
    const active = document.activeElement as HTMLElement | null;
    // 상자 밖으로 나가려는 Tab 을 되돌린다 — 배경이 inert 여도 브라우저 UI 로는 빠질 수 있다.
    if (!e.shiftKey && active === lastEl) {
      e.preventDefault();
      firstEl.focus();
    } else if (e.shiftKey && (active === firstEl || !boxRef.current.contains(active))) {
      e.preventDefault();
      lastEl.focus();
    }
  }, [onClose]);

  return createPortal(
    <div className="afs-scope afs-dialog-backdrop" onKeyDown={onKeyDown}
      // 배경 클릭으로 닫지 않는다 — 입력 중이던 거절 사유가 한 번의 실수로 사라진다.
      // 닫기는 명시적 버튼과 Escape 로만 한다.
      role="presentation">
      <div ref={boxRef} className="afs-dialog" role="dialog" aria-modal="true"
        aria-label={label} tabIndex={-1}>
        {children}
      </div>
    </div>,
    document.body,
  );
}
