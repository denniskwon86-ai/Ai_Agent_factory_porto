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
import { useEffect, useRef } from 'react';

import './afs.css';
import { RailIcon, type RailIconName } from './RailIcon';

export type RailItem = {
  id: string;
  label: string;
  hint?: string;
  /** 기능별 **고정 아이콘**(`RailIcon.tsx` 등록부). 자동 생성하지 않는다 —
   *  한글 첫 글자를 쓰던 종전 방식은 「받은 앱」과 「대내외 발간」을 둘 다 «발»로 만들었다. */
  icon: RailIconName;
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
  // ★★ 같은 화면에서 아이콘이 겹치면 아이콘은 구별에 쓸모가 없어진다(2026-08-04 «발» 충돌).
  //   등록부로 바꾼 뒤에도 사람이 같은 이름을 두 번 적을 수 있으므로 여기서 확인한다.
  //   ⚠️ 던지지 않는다 — 화면 전체가 사라지면 정작 무엇이 겹쳤는지 볼 수 없다. 콘솔에 남기고
  //     캡처 스크립트가 `data-icon` 중복과 콘솔 오류를 함께 검사한다.
  // ★★ [2026-08-04 실측] 720px 에서 레일이 스크롤될 때 **활성 항목이 화면 밖에 있었다** —
  //   지금 보고 있는 화면이 메뉴에서 안 보이면 사용자는 자기가 어디 있는지 알 수 없다.
  //   스크롤바를 보이게 한 것만으로는 부족했다(스크롤은 «할 수 있다»일 뿐 «되어 있다»가 아니다).
  const activeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'nearest' });
  }, [activeId]);

  const dupIcons = items.map((i) => i.icon)
    .filter((v, idx, all) => all.indexOf(v) !== idx);
  if (dupIcons.length) {
    console.error(`[HubShell] 레일 아이콘이 겹쳤습니다: ${[...new Set(dupIcons)].join(', ')} `
      + `— «${title}» 화면. RailIcon 등록부에서 서로 다른 아이콘을 지정하십시오.`);
  }

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
              ref={activeId === it.id ? activeRef : undefined}
              className={activeId === it.id ? 'active' : ''}
              /* 아이콘은 `aria-hidden` 이므로 버튼이 **전체 기능명**을 말해야 한다.
                 힌트와 대기 건수까지 넣는다 — 화면을 못 보는 사용자에게 «받은 앱»만 들리면
                 대기 2건이 있다는 사실이 사라진다. */
              aria-label={[it.label, it.hint, it.count ? (it.countLabel || `${it.count}건`) : '']
                .filter(Boolean).join(' · ')}
              onClick={() => onSelect(it.id)}>
              <RailIcon name={it.icon} />
              <span>
                <b>{it.label}</b>
                {it.hint && <small>{it.hint}</small>}
              </span>
              {/* 0 은 표시하지 않는다 — 항상 뜨는 숫자는 아무도 읽지 않는다. */}
              {!!it.count && <span className="count" aria-hidden="true">{it.count}</span>}
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
