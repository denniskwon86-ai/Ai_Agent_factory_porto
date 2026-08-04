// [UIUX] 허브 3열 셸 — 승인 시안(Living Enterprise Canvas)의 공용 레이아웃
//
// `238px Rail / 가변 작업면(최소 680px) / 300px Jarvis`(작업서 §CL-FE-02).
//
// ★ CL-2~5 화면이 모두 이 셸 위에 올라간다. 그래서 **CL-1 을 먼저 여기 얹어 검증**했다 —
//   한 번도 실제 화면을 그려보지 않은 셸 위에 화면 4개를 쌓은 뒤 틀린 것을 발견하면, 그때는
//   "새로 만드는 일"이 아니라 "되던 걸 고치는 일"이 된다.
//
// ⚠️ 스타일은 `.afs-scope` 안에서만 적용된다(`afs.css` 상단 주석 참조). 기존 다크 테마 화면에
//   토큰이 새면 15개 화면의 색이 동시에 바뀐다 — 그것부터 막았다.
import './afs.css';

export type RailItem = {
  id: string;
  label: string;
  hint?: string;
  /** 아이콘 자리에 넣을 짧은 글자(1~2자). 이미지 의존을 만들지 않는다. */
  mark?: string;
  /** 대기 건수 등. 0이면 표시하지 않는다 — 항상 뜨는 배지는 읽히지 않는다. */
  count?: number;
  /** 배지가 뜻하는 것. 지정하지 않으면 중립적인 «N건»으로 읽는다. */
  countLabel?: string;
};

export function HubShell({
  title, subtitle, kicker,
  items, activeId, onSelect,
  footer, jarvis, children,
}: {
  title: string;
  subtitle?: string;
  kicker?: string;
  items: RailItem[];
  activeId: string;
  onSelect: (id: string) => void;
  /** Rail 하단 고정 영역(예: 플랫폼 인증 상속 안내 카드). */
  footer?: React.ReactNode;
  /** 300px 우측 레일. 좁은 창(<1330px)에서는 CSS 가 접는다. */
  jarvis?: React.ReactNode;
  children: React.ReactNode;
}) {
  // ⚠️ `afs-scope` 와 `hub-layout` 을 **같은 요소에 두지 않는다.** 스타일 규칙이
  //   `.afs-scope .hub-layout`(자손 선택자)이므로 같은 요소면 매치되지 않는다 —
  //   실측에서 `display: block` 으로 떨어져 3열이 무너졌다. 스코프는 감싸는 요소가 갖는다.
  return (
    <div className="afs-scope" style={{ height: '100%' }}>
    <div className={`hub-layout ${jarvis ? '' : 'no-jarvis'}`} style={{ height: '100%' }}>
      {/* 좌: 모듈 레일 — 역할 기반 진입점(채택 결정 1항) */}
      <nav className="module-rail" aria-label="협업 모듈">
        <div className="module-intro">
          {kicker && <small>{kicker}</small>}
          <h1>{title}</h1>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <div className="module-menu" role="tablist" aria-orientation="vertical">
          {items.map((it) => (
            <button key={it.id} role="tab" aria-selected={activeId === it.id}
              className={activeId === it.id ? 'active' : ''}
              onClick={() => onSelect(it.id)}>
              <i aria-hidden="true">{it.mark || it.label.slice(0, 1)}</i>
              <span>
                <b>{it.label}</b>
                {it.hint && <small>{it.hint}</small>}
              </span>
              {/* 0 은 표시하지 않는다 — 항상 뜨는 숫자는 아무도 읽지 않는다. */}
              {!!it.count && <span className="count" aria-label={it.countLabel || `${it.count}건`}>{it.count}</span>}
            </button>
          ))}
        </div>
        {footer}
      </nav>

      {/* 중: 가변 작업면 */}
      <main className="hub-main">{children}</main>

      {/* 우: Jarvis — 없으면 열을 만들지 않는다(빈 열은 작업면을 좁힌다) */}
      {jarvis}
    </div>
    </div>
  );
}

/** 화면 머리 — 무엇을 하는 화면인지와 현재 상태를 함께 말한다. */
/** 상태 칩 색. **문자열을 그대로 받지 않는다** — 오타가 나면 색만 빠진 채 조용히 렌더링되고,
 *  «위험»으로 보여야 할 상태가 회색으로 나간다. */
export type ChipTone = 'success' | 'warn' | 'data' | 'danger' | 'muted';

export function ScreenHead({ kicker, title, description, chip }: {
  kicker?: string;
  title: string;
  description?: string;
  chip?: { label: string; tone?: ChipTone };
}) {
  return (
    <header className="screen-head">
      <div>
        {kicker && <small>{kicker}</small>}
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {chip && <span className={`state-chip ${chip.tone || 'data'}`}>{chip.label}</span>}
    </header>
  );
}

/** 흰 카드. `title` 이 있으면 머리를 붙인다. */
export function Panel({ kicker, title, action, children, className = '' }: {
  kicker?: string;
  title?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || action) && (
        <div className="panel-head">
          <div>
            {kicker && <small>{kicker}</small>}
            {title && <h3>{title}</h3>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

/** 화면 안 알림. **브라우저 `alert`/`prompt` 를 쓰지 않는다** — 승인 시안에 없고, 키보드
 *  접근·스크린리더 대응이 되지 않으며, 스타일을 입힐 수 없다. */
export function Banner({ tone = 'info', title, children }: {
  tone?: 'info' | 'warn' | 'error';
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={`afs-banner ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      {title && <b>{title}</b>}
      <div>{children}</div>
    </div>
  );
}
