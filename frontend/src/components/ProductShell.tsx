/**
 * [승인 시안] 제품 상단 셸 — **시안 마크업 그대로.**
 *
 * 원본: `uiux-prototypes/master-concept/index.html` 의 `<header class="afs-product-shell">`
 * 스타일: `uiux-prototypes/product-shell.css` (→ `design/product-shell.css` 로 가져옴)
 *
 * ## ⚠️⚠️ [2026-08-25 사용자 지적] 왜 다시 만들었는가
 *
 * > 딱 봐도 시안이랑 다르지 않나요? 상단의 메뉴도 그렇고…
 *
 * 상단 바를 우리가 따로 만들어 쓰고 있었다 — 회사문맥바 + 세션바 + 검색 메뉴를 나열한
 * 72px 짜리. 시안은 **네 칸 그리드**다:
 *
 *     [브랜드 210] [회사 문맥 270] [전역 내비 1fr] [행동 auto]
 *
 * ★ 손으로 맞추지 않고 **시안 마크업을 옮긴다.** 맞춰 그리면 그 순간부터 또 갈라진다.
 * ⚠️ 시안의 전역 내비는 **7개 목적지**(경영 홈·Factory·운영·Twin·보고서·Knowledge·Agent)
 *   다 — 화면기능정의서 §3 의 8개 메뉴와 같은 축이다. 우리가 쓰던 20개 목록은 그 아래
 *   층이므로 「전체 메뉴」로 남긴다.
 */
import { PRODUCT_NAME } from '../lib/brand';

export type ShellModule =
  | 'enterprise' | 'factory' | 'operate' | 'twin' | 'report' | 'knowledge' | 'agent';

/** 시안의 전역 내비 7칸. ★ 순서·이름을 시안에서 옮겼다. */
const NAV: { id: ShellModule; label: string }[] = [
  { id: 'enterprise', label: '경영 홈' },
  { id: 'factory', label: 'Factory' },
  { id: 'operate', label: '운영' },
  { id: 'twin', label: 'Twin' },
  { id: 'report', label: '보고서' },
  { id: 'knowledge', label: 'Knowledge' },
  { id: 'agent', label: 'Agent' },
];

export function ProductShell({
  module, company, scope, entityMode, onNav, onContext, onSettings, onNewWork, right,
}: {
  module: ShellModule;
  /** 회사 이름. ⚠️ 없으면 «확인 중» — 없는 값을 지어내지 않는다. */
  company: string;
  scope: string;
  entityMode: string;
  onNav: (id: ShellModule) => void;
  onContext: () => void;
  onSettings: () => void;
  onNewWork: () => void;
  /** 전체 메뉴처럼 앱에만 있는 것. 시안 행동 칸 **앞**에 놓는다. */
  right?: React.ReactNode;
}) {
  //: 시안의 `LS MnM · 전사공통 · 경영관리팀` 자리 — 회사 · 범위를 이어 적는다.
  const contextLine = [company || '확인 중', scope].filter(Boolean).join(' · ');
  //: 시안의 `M` 마크 — 회사 첫 글자. ⚠️ 회사를 모르면 «?» 다(빈 사각형을 남기지 않는다).
  const mark = (company || '?').trim().charAt(0).toUpperCase();

  return (
    <header className="afs-product-shell" data-module={module}>
      <button type="button" className="afs-brand"
        onClick={() => onNav('enterprise')}
        style={{ border: 0, background: 'transparent', cursor: 'pointer', font: 'inherit' }}>
        <i className="afs-brand-mark">AF</i>
        <span className="afs-brand-copy">
          <b>{PRODUCT_NAME}</b>
          <small>LIVING ENTERPRISE OS</small>
        </span>
      </button>

      <button type="button" className="afs-context" onClick={onContext}
        aria-label="회사 문맥 전환">
        <span className="afs-context-mark">{mark}</span>
        <span className="afs-context-copy">
          <small>OPERATING CONTEXT</small>
          <b>{contextLine}</b>
        </span>
        {/* ⚠️ 실행 문맥은 **항상** 보인다 — REAL 과 VIRTUAL 을 헷갈리면 시연 숫자가
            실적으로 읽힌다(시안 §1.2 ⑥ 「회사 Context 상시 노출」). */}
        <span className="afs-context-mode">{entityMode || 'REAL'}</span>
      </button>

      <nav className="afs-global-nav" aria-label="주요 기능">
        {NAV.map((n) => (
          <button key={n.id} type="button"
            className={n.id === module ? 'active' : undefined}
            onClick={() => onNav(n.id)}>
            {n.label}
          </button>
        ))}
      </nav>

      <div className="afs-shell-actions">
        {right}
        <button type="button" className="afs-icon-action" onClick={onSettings}
          aria-label="환경설정 · 관리자">⚙</button>
        <button type="button" className="afs-primary-action" onClick={onNewWork}>
          ＋ 새 업무
        </button>
      </div>
    </header>
  );
}
