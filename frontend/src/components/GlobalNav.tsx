// [UIUX-AUDIT-30 §3 · AUDIT-33 §1] 글로벌 내비게이션 — **16개 동급 버튼을 나열하지 않는다.**
//
// 감사 실측(30): 런처 상단의 기능 버튼 15개가 1280·1440 **양쪽에서** 세로로 압축되고 우측이
// 잘렸다. 가로 스크롤로 숨어 있어서, 화면 오른쪽 끝의 기능은 **존재 자체가 보이지 않았다.**
//
// ★ 원인은 폭이 아니라 위계다. 16개가 전부 같은 무게로 놓이면 «지금 무엇을 해야 하는가»를
//   화면이 말하지 못하고, 결국 사용자는 아는 버튼만 계속 쓴다. 그래서 구조를 바꿨다:
//     · 1차 영역 — 매일 쓰는 진입점 3개만 상단에 남긴다.
//     · 전체 메뉴 — 나머지는 **업무 영역별로 묶어** 한 번의 클릭 안에 전부 보이게 한다.
//       (숨기는 것이 아니다. 가로 스크롤로 잘려 안 보이던 것을 오히려 한 화면에 모은다.)
//
// ⚠️⚠️ 감사 실측(33 §1): 메뉴를 헤더 안에 `absolute` 로 두었더니 **위로 잘렸다.** 첫 항목으로
//   포커스를 옮기는 순간 브라우저가 그 요소를 보이게 하려고 **sticky header 내부를 161.5px
//   스크롤**했고, 메뉴 버튼이 `-149px`, 메뉴 상단이 `-103px` 까지 밀려 올라갔다.
//   → 자동 포커스를 없애지 않는다(없애면 키보드로 메뉴에 들어갈 수 없다). 대신 메뉴를
//     **`body` 로 portal 해 `position: fixed` popover** 로 띄운다. 조상이 스크롤돼도 메뉴는
//     화면 좌표에 고정되므로 잘릴 자리가 없다.
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

export type NavItem = {
  id: string;
  label: string;
  icon: string;
  /** 이 기능이 무엇을 하는지 — 툴팁이 아니라 메뉴에 **본문으로** 쓴다. 툴팁은 키보드·터치에서 안 보인다. */
  desc: string;
  onSelect: () => void;
};

export type NavGroup = { title: string; hint: string; items: NavItem[] };

const PANEL_MAX_W = 860;
const GAP = 8;
const EDGE = 12;

export function GlobalNav({ primary, groups, right }: {
  /** 매일 쓰는 진입점. **3개를 넘기지 않는다** — 넘기는 순간 다시 «나열»이 된다. */
  primary: NavItem[];
  groups: NavGroup[];
  right?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; width: number; maxH: number } | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  /** 버튼의 **화면 좌표**를 읽어 fixed 위치를 계산한다. 조상 스크롤과 무관해진다. */
  const place = useCallback(() => {
    const b = btnRef.current?.getBoundingClientRect();
    if (!b) return;
    const width = Math.min(PANEL_MAX_W, window.innerWidth - EDGE * 2);
    const left = Math.min(Math.max(EDGE, b.right - width), window.innerWidth - width - EDGE);
    const top = b.bottom + GAP;
    // 아래로 남은 공간 안에서만 펼친다 — 넘치면 패널이 화면 밖으로 나가 아래쪽 항목이 사라진다.
    const maxH = Math.max(200, window.innerHeight - top - EDGE);
    setPos({ top, left, width, maxH });
  }, []);

  useLayoutEffect(() => { if (open) place(); }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setOpen(false); btnRef.current?.focus(); }
    };
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (panelRef.current?.contains(t) || btnRef.current?.contains(t)) return;
      setOpen(false);
    };
    // 창 크기·스크롤이 바뀌면 좌표를 다시 잡는다(fixed 는 자동으로 따라오지 않는다).
    const onMove = () => place();
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    window.addEventListener('resize', onMove);
    window.addEventListener('scroll', onMove, true);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onDown);
      window.removeEventListener('resize', onMove);
      window.removeEventListener('scroll', onMove, true);
    };
  }, [open, place]);

  // ★ 자동 포커스는 **유지한다.** 없애면 키보드 사용자는 나머지 12개 기능에 도달할 수 없다.
  //   위치를 잡은 **뒤에** 옮겨야 브라우저가 스크롤로 «보이게» 만들려 하지 않는다.
  useEffect(() => {
    if (!open || !pos) return;
    const first = panelRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]');
    // `preventScroll` 이 이 결함의 직접적인 해법이다 — portal 과 함께 이중으로 막는다.
    first?.focus({ preventScroll: true });
  }, [open, pos]);

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
            ? 'shrink-0 text-[13px] font-bold text-white bg-indigo-600 hover:bg-indigo-500 border border-indigo-500 px-4 py-2 rounded-lg transition-all'
            : 'shrink-0 text-[13px] font-bold text-gray-200 bg-white/5 hover:bg-white/10 border border-white/10 px-4 py-2 rounded-lg transition-all'}
        >
          {it.icon} {it.label}
        </button>
      ))}

      {/* ── 전체 메뉴 ───────────────────────────────────────────────────── */}
      <button
        ref={btnRef}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="global-nav-panel"
        aria-haspopup="true"
        title="나머지 기능을 업무 영역별로 모아 봅니다"
        className="shrink-0 text-[13px] font-bold text-gray-200 bg-white/5 hover:bg-white/10 border border-white/10 px-4 py-2 rounded-lg transition-all flex items-center gap-2"
      >
        ☰ 전체 메뉴
        <span className="text-xs font-semibold text-gray-400">{total}</span>
      </button>

      {/* ⚠️ `body` 로 portal 한다. 헤더 안에 두면 sticky 조상이 스크롤되면서 메뉴가 잘린다. */}
      {open && pos && createPortal(
        <div
          id="global-nav-panel"
          ref={panelRef}
          role="menu"
          aria-label="전체 기능"
          style={{
            position: 'fixed', top: pos.top, left: pos.left, width: pos.width,
            maxHeight: pos.maxH, zIndex: 70,
          }}
          className="overflow-y-auto bg-gray-900 border border-gray-700 rounded-xl shadow-2xl p-5
                     grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5"
        >
          {groups.map((g) => (
            <section key={g.title}>
              <h3 className="text-[13px] font-bold text-gray-200 mb-1">{g.title}</h3>
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
                    <span className="block text-[13px] font-semibold text-gray-100">
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
        </div>,
        document.body,
      )}

      {right}
    </div>
  );
}
