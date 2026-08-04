// [UIUX-AUDIT-30 §3] 글로벌 내비게이션 — **16개 동급 버튼을 나열하지 않는다.**
//
// 감사 실측: 런처 상단의 기능 버튼 15개가 1280·1440 **양쪽에서** 세로로 압축되고 우측이
// 잘렸다. 가로 스크롤로 숨어 있어서, 화면 오른쪽 끝의 기능은 **존재 자체가 보이지 않았다.**
//
// ★ 원인은 폭이 아니라 위계다. 16개가 전부 같은 무게로 놓이면 «지금 무엇을 해야 하는가»를
//   화면이 말하지 못하고, 결국 사용자는 아는 버튼만 계속 쓴다. 그래서 구조를 바꾼다:
//     · 1차 영역 — 매일 쓰는 진입점 3개만 상단에 남긴다.
//     · 전체 메뉴 — 나머지는 **업무 영역별로 묶어** 한 번의 클릭 안에 전부 보이게 한다.
//       (숨기는 것이 아니다. 가로 스크롤로 잘려 안 보이던 것을 오히려 한 화면에 모은다.)
//
// ⚠️ 접근성: 실제 `aria-expanded`/`aria-controls`, Escape 닫기, 바깥 클릭 닫기, 열릴 때 첫
//   항목으로 포커스 이동. 드롭다운을 흉내만 내면 키보드 사용자는 나머지 13개 기능에 영원히
//   도달하지 못한다.
import { useEffect, useRef, useState } from 'react';

export type NavItem = {
  id: string;
  label: string;
  icon: string;
  /** 이 기능이 무엇을 하는지 — 툴팁이 아니라 메뉴에 **본문으로** 쓴다. 툴팁은 키보드·터치에서 안 보인다. */
  desc: string;
  onSelect: () => void;
};

export type NavGroup = { title: string; hint: string; items: NavItem[] };

export function GlobalNav({ primary, groups, right }: {
  /** 매일 쓰는 진입점. **3개를 넘기지 않는다** — 넘기는 순간 다시 «나열»이 된다. */
  primary: NavItem[];
  groups: NavGroup[];
  right?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setOpen(false); btnRef.current?.focus(); }
    };
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    // 열리면 첫 항목으로 포커스를 옮긴다 — 그러지 않으면 키보드로 메뉴에 들어갈 수 없다.
    panelRef.current?.querySelector<HTMLButtonElement>('button')?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onDown);
    };
  }, [open]);

  const total = groups.reduce((n, g) => n + g.items.length, 0);

  return (
    <div className="flex items-center gap-3 min-w-0">
      {/* ── 1차 영역 ────────────────────────────────────────────────────── */}
      {primary.map((it, i) => (
        <button
          key={it.id}
          onClick={it.onSelect}
          title={it.desc}
          className={i === 0
            ? 'shrink-0 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-500 border border-indigo-500 px-4 py-2 rounded-lg transition-all'
            : 'shrink-0 text-sm font-bold text-gray-200 bg-white/5 hover:bg-white/10 border border-white/10 px-4 py-2 rounded-lg transition-all'}
        >
          {it.icon} {it.label}
        </button>
      ))}

      {/* ── 전체 메뉴 ───────────────────────────────────────────────────── */}
      <div className="relative shrink-0" ref={wrapRef}>
        <button
          ref={btnRef}
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls="global-nav-panel"
          aria-haspopup="true"
          title="나머지 기능을 업무 영역별로 모아 봅니다"
          className="text-sm font-bold text-gray-200 bg-white/5 hover:bg-white/10 border border-white/10 px-4 py-2 rounded-lg transition-all flex items-center gap-2"
        >
          ☰ 전체 메뉴
          <span className="text-xs font-semibold text-gray-400">{total}</span>
        </button>

        {open && (
          <div
            id="global-nav-panel"
            ref={panelRef}
            role="menu"
            aria-label="전체 기능"
            className="absolute right-0 top-full mt-2 w-[min(92vw,860px)] max-h-[70vh] overflow-y-auto
                       bg-gray-900 border border-gray-700 rounded-xl shadow-2xl p-5 z-50
                       grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5"
          >
            {groups.map((g) => (
              <section key={g.title}>
                <h3 className="text-sm font-bold text-gray-200 mb-1">{g.title}</h3>
                {/* 그룹 설명을 둔다 — 이름만으로는 «왜 여기 묶였는지» 알 수 없다. */}
                <p className="text-xs text-gray-400 mb-3 leading-relaxed">{g.hint}</p>
                <div className="flex flex-col gap-1">
                  {g.items.map((it) => (
                    <button
                      key={it.id}
                      role="menuitem"
                      onClick={() => { setOpen(false); it.onSelect(); }}
                      className="text-left px-3 py-2 rounded-lg hover:bg-white/10 focus:bg-white/10
                                 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 transition-colors"
                    >
                      <span className="block text-sm font-semibold text-gray-100">
                        {it.icon} {it.label}
                      </span>
                      {/* 설명을 본문으로 쓴다 — 툴팁은 키보드·터치 사용자에게 보이지 않는다. */}
                      <span className="block text-xs text-gray-400 mt-0.5 leading-relaxed">
                        {it.desc}
                      </span>
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>

      {right}
    </div>
  );
}
