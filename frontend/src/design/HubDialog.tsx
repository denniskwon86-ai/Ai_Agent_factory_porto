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
import { createContext, useCallback, useContext, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

import { useOperatingContext } from '../lib/operatingContext';
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

/** ★★★ [설계 §10 UI 3항] 「현재 회사·조직·모드가 화면에서 **항상** 확인 가능하다」.
 *
 * ## 왜 셸에 넣는가 — 화면마다 넣으면 반드시 빠진다
 *
 * 2026-08-08 역할별 감사 실측: 허브 화면 11개 중 **조직·모드를 함께 보여주는 것은 Agent
 * Governance 하나**뿐이었다(6개는 둘 다 없고, 4개는 조직만). 화면마다 각자 그리게 두면 새
 * 화면이 생길 때마다 하나씩 빠진다 — 이 파일 머리말이 `role="dialog"` 에 대해 말한 것과
 * **같은 이유**로 셸에 넣는다.
 *
 * ## ⚠️⚠️ 모드를 모르면 «가상» 을 «실제» 로 읽는다
 *
 * `VIRTUAL`(가상 조직/샌드박스)에서는 같은 화면이 **다른 데이터**를 보여준다. 모드 표시가
 * 없으면 사용자는 연습용 숫자를 실적으로 읽고, 그 위에서 결정한다. 그래서 REAL 은 조용히
 * 적고 **VIRTUAL 은 눈에 띄게** 표시한다 — 둘을 같은 무게로 그리면 경고가 되지 않는다.
 *
 * ⚠️ 문맥을 **읽기만** 한다. 여기서 바꾸는 수단을 주면 모달 안에서 범위를 바꾼 뒤 그 사실을
 *   잊은 채 다른 화면으로 넘어가게 된다 — 전환은 상단 전환기 한 곳에서만 한다. */
/** 「처음 화면으로」 손잡이. **한 곳**이다.
 *
 * ⚠️ `null` 이면 버튼을 그리지 않는다 — 눌러도 아무 일 없는 버튼은 고장으로 읽힌다.
 *   App 이 `HomeNavContext.Provider` 로 실제 동작을 넘겨줄 때만 나타난다. */
export const HomeNavContext = createContext<(() => void) | null>(null);

function ContextFooter() {
  const goHome = useContext(HomeNavContext);
  const ctx = useOperatingContext();
  const mode = (ctx.entityMode || 'REAL').toUpperCase();
  const virtual = mode !== 'REAL';
  const companyLabel = ctx.companyName || '회사 연결 필요';
  return (
    <div className="afs-dialog-context"
      style={{
        display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap',
        padding: '7px 16px', fontSize: 12,
        borderBottom: '1px solid var(--surface-border)',
        background: 'var(--surface-sunken)',
      }}>
      {/* ★★★ [2026-08-25 사용자 지적] 「각 화면에서 홈으로 돌아가는 버튼이 없다」.
          ⚠️⚠️ 「닫기」는 있었지만 그것은 «이 창을 닫는다» 로 읽힌다 — 사용자가 찾는 것은
            «처음 화면으로 간다» 다. 그리고 화면 24개가 **각자** 머리 바를 그리므로,
            버튼을 화면마다 달면 반드시 빠뜨리는 곳이 생긴다.
          ★ 셸이 그리는 이 문맥 띠에 둔다 — `HubDialog` 를 쓰는 **모든** 화면이 한 번에 받는다.
          ⚠️ 손잡이가 없으면(App 이 안 넘겨주면) 그리지 않는다 — 눌러도 아무 일 없는
            버튼은 고장으로 읽힌다. */}
      {goHome && (
        <button type="button" className="secondary-button"
          onClick={goHome}
          title="경영 홈으로 — 처음 화면으로 돌아갑니다"
          style={{ fontSize: 12, padding: '2px 10px', minHeight: 24, fontWeight: 700 }}>
          ⌂ 경영 홈
        </button>
      )}
      <span className="afs-muted">실행 문맥</span>
      <b className={virtual ? 'afs-warn-fg' : 'afs-muted'}>
        {virtual ? `⚠️ ${mode} — 가상 문맥입니다` : 'REAL'}
      </b>
      <span className="afs-muted">·</span>
      {/* ⚠️ [2026-08-23] **모르는 것을 지어내지 않는다.** 종전에는 조직을 안 고르면
          「조직 미지정」, 회사를 모르면 `tenant_default` 라는 **없는 값**을 찍었다.
          문맥이 비면 서버는 «권한 범위 전체» 로 동작하므로 「미지정」은 사실이 아니다
          (`CompanyContextBar` 에 같은 수정을 했다 — 여기만 남으면 두 곳이 다른 말을 한다). */}
      <span className="afs-muted">조직 범위 — {ctx.scopeLabel}</span>
      <span className="afs-muted">·</span>
      <span className="afs-muted">{companyLabel}</span>
    </div>
  );
}

export function HubDialog({ label, subtitle, barActions, onClose, children, page = false }: {
  /** 스크린리더가 읽는 이름. 비우면 "대화상자"로만 읽혀 무엇인지 알 수 없다. */
  label: string;
  /** ★★★ [2026-08-23 실측] 이 값을 주면 **셸이 머리 바를 그린다**(제목 + 「닫기 (Esc)」).
   *
   * ## 왜 셸로 올렸는가 — 두 화면이 실제로 빠뜨렸다
   *
   * 머리 바(`afs-dialog-bar`)는 지금까지 **화면마다 각자** 그렸다. 그 결과
   * `CalcApprovalPanel` 과 `PathCalcPanel` 이 그것을 빠뜨렸고, **제목도 「닫기」도 없는
   * 전체화면 창**이 됐다 — 닫는 방법은 Escape 뿐인데 화면 어디에도 그렇게 적혀 있지 않다.
   *
   * ⚠️ 이 파일 머리말이 이미 같은 결론을 적어 두었다: 「화면 4개를 같은 방식으로 더 만들면
   *   같은 결함이 5개로 복제된다. 그래서 화면이 아니라 **셸**에 넣는다.」 `role="dialog"`·
   *   포커스 덫·배경 차단을 셸로 올린 것과 **같은 이유**로 머리 바도 올린다.
   * ★ 이미 자기 바를 그리는 화면은 이 값을 주지 않으면 된다 — 바가 둘이 되지 않는다.
   *   아래 개발용 점검이 «둘 다 없는» 경우만 잡는다. */
  subtitle?: string;
  /** 머리 바 오른쪽에 놓을 것(진행 표시 등). 닫기 버튼은 셸이 항상 붙인다. */
  barActions?: React.ReactNode;
  /** 공통 ProductShell 아래의 독립 페이지로 렌더링할 때 portal·dialog 동작을 사용하지 않는다. */
  page?: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  // 열릴 때: 포커스 원위치 기억 → 배경 차단 → 첫 요소로 포커스
  useEffect(() => {
    if (page) return;
    restoreRef.current = (document.activeElement as HTMLElement) || null;

    const root = document.getElementById('root');
    root?.setAttribute('inert', '');

    // ★ 배경 스크롤 잠금. 이것이 **문서 기준 가로 오버플로도 함께 막는다**(지적 2) —
    //   기존 헤더가 넘치더라도 모달이 열린 동안 사용자에게 스크롤바가 보이지 않는다.
    const prev = { overflow: document.body.style.overflow };
    document.body.style.overflow = 'hidden';

    // ★★★ [2026-08-23] **닫는 방법이 화면에 없는 창을 만들지 못하게 한다.**
    //   Escape 는 동작하지만 «어디에도 그렇게 적혀 있지 않으면» 사용자에게는 없는 기능이다.
    //   실제로 두 화면이 머리 바를 빠뜨려 제목도 닫기도 없는 전체화면 창이 됐다.
    //   ⚠️ 조용히 넘어가지 않는다 — 조용하면 다음 화면도 똑같이 빠뜨린다.
    if (import.meta.env?.DEV) {
      queueMicrotask(() => {
        const box = boxRef.current;
        if (!box) return;
        const hasBar = !!box.querySelector('.afs-dialog-bar');
        const hasClose = [...box.querySelectorAll('button')]
          .some((b) => /닫기|✕|×/.test(b.textContent || ''));
        if (!hasBar && !hasClose) {
          console.error(
            `[HubDialog] «${label}» 에 머리 바도 닫기 버튼도 없습니다 — 사용자는 이 창을 `
            + '닫을 방법을 화면에서 찾을 수 없습니다. `subtitle` 을 넘겨 셸이 바를 그리게 '
            + '하거나, 화면이 직접 `.afs-dialog-bar` 를 그리십시오.');
        }
      });
    }

    const first = boxRef.current ? focusables(boxRef.current)[0] : null;
    // 포커스 대상이 없으면 상자 자체에 준다 — 어디에도 포커스가 없으면 Escape 도 안 먹는다.
    (first || boxRef.current)?.focus?.();

    return () => {
      root?.removeAttribute('inert');
      document.body.style.overflow = prev.overflow;
      // 닫은 뒤 **열었던 버튼으로 돌아간다.** 없으면 사용자는 문서 맨 위로 튕긴다.
      restoreRef.current?.focus?.();
    };
  }, [label, page]);

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

  if (page) return <>{children}</>;

  return createPortal(
    <div className="afs-scope afs-dialog-backdrop" onKeyDown={onKeyDown}
      // 배경 클릭으로 닫지 않는다 — 입력 중이던 거절 사유가 한 번의 실수로 사라진다.
      // 닫기는 명시적 버튼과 Escape 로만 한다.
      role="presentation">
      <div ref={boxRef} className="afs-dialog" role="dialog" aria-modal="true"
        aria-label={label} tabIndex={-1}>
        {/* ★ [설계 §5.3] 「**상단** Context Bar 에는 회사·업무 범위·REAL/VIRTUAL 상태를
            표시한다」 — 처음에는 하단에 뒀는데, 문맥은 **작업을 시작하기 전에** 읽어야
            의미가 있다. 아래에 있으면 스크롤해야 보이고, 그때는 이미 누른 뒤다. */}
        <ContextFooter />
        {subtitle !== undefined && (
          <div className="afs-dialog-bar">
            <b>{label}</b>
            <span>{subtitle}</span>
            <div className="bar-actions">
              {barActions}
              <button onClick={onClose} className="secondary-button" style={{ minHeight: 32 }}>
                닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
              </button>
            </div>
          </div>
        )}
        {children}
      </div>
    </div>,
    document.body,
  );
}
