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
  /**
   * 이 기능이 무엇을 하는지.
   *
   * ⚠️⚠️ [2026-08-24 사용자 지적] 종전에는 이것을 **항목마다 본문으로** 깔았다. 그래서
   *   메뉴를 열면 20개가 설명문까지 달고 통째로 쏟아졌다 — 「음식 메뉴판 같다」.
   *   그렇다고 툴팁으로만 두면 키보드·터치 사용자는 영영 못 본다(그래서 본문에 깔았던 것).
   * ★ 지금은 **지금 가리키는 것 하나**만 패널 아래 고정된 칸에 보여 준다. 마우스를 올려도,
   *   ↑↓ 로 옮겨도 같은 자리에서 읽힌다. 찾기 칸의 검색 대상이기도 하다.
   */
  desc: string;
  onSelect: () => void;
  /** 지금 이 사람이 쓸 수 없다면 **그 이유**. 값이 있으면 비활성이 되고 이유가 본문에 붙는다.
   *
   *  ★★★ [2026-08-08 P2-4 역할별 실측] 설계 §10 수용 기준: **「API 403 을 버튼 클릭 후
   *    처음 알게 되는 경로가 없어야 한다」.** 실측에서 viewer 에게 「데이터 거버넌스」가
   *    활성으로 보였고, 눌러야 403 을 알았다. 열어 보고 나서 「권한 없음」을 읽는 것은
   *    통제가 아니라 **헛걸음**이다.
   *  ⚠️ 이유 없이 회색으로만 두지 않는다 — 회색 버튼만 보이면 사용자는 화면 고장으로 읽고,
   *    진짜 이유는 아무에게도 도달하지 않는다(`factory/RunControls` 가 같은 규칙을 쓴다). */
  disabledReason?: string;
};

/** ⚠️ `hint` 는 이제 **화면에 그리지 않는다.** 묶음마다 문단을 두면 그것만 6개다 —
 *   묶음 이름이 스스로 설명하도록 짧게 짓는 편이 낫다. 값은 남겨 둔다(문서 생성에 쓴다). */
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
  //: ★ 찾기 — 20개를 훑어 읽게 하지 않는다. 두세 글자로 좁힌다.
  const [q, setQ] = useState('');
  //: 지금 가리키는 줄(마우스·키보드 공통). 설명은 이 하나만 아래 칸에 보여 준다.
  const [cursor, setCursor] = useState(0);
  const searchRef = useRef<HTMLInputElement>(null);
  const rowRefs = useRef<(HTMLButtonElement | null)[]>([]);

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

  //: ★ 열면 **찾기 칸**으로 간다. 키보드 사용자는 바로 치기 시작하면 되고, ↑↓ 로
  //:   목록을 옮긴다. (종전에는 첫 항목에 포커스를 줬는데, 그러면 20개를 Tab 으로
  //:   지나야 마지막에 닿았다.)
  //: ⚠️ `preventScroll` 은 유지한다 — sticky 조상이 메뉴를 밀어 올리던 결함의 해법이다.
  useEffect(() => {
    if (!open || !pos) return;
    searchRef.current?.focus({ preventScroll: true });
  }, [open, pos]);

  //: 닫으면 다음에 깨끗한 상태로 열린다 — 지난 검색어가 남아 「기능이 없다」로 보이면 안 된다.
  useEffect(() => { if (!open) { setQ(''); setCursor(0); } }, [open]);

  //: ★ 개수는 **패널이 실제로 담는 것**을 센다 — 1차 셋을 넣었으므로 함께 센다.
  //: ⚠️ 세는 것과 보여 주는 것이 갈리면 「20이라 적혀 있는데 23개」가 된다.
  const total = groups.reduce((n, g) => n + g.items.length, 0) + primary.length;

  /** 검색어로 좁힌 뒤, 화면에 그릴 줄(그룹 머리 + 항목)로 편다.
   *
   *  ★ 이름과 설명 **양쪽**을 본다 — 사용자는 「승인」처럼 하는 일로 찾지, 우리가 붙인
   *    이름으로 찾지 않는다.
   *  ⚠️ 걸린 것이 없는 그룹은 머리도 그리지 않는다. 빈 제목만 남으면 「여기 뭔가 있는데
   *    안 보인다」로 읽힌다. */
  const needle = q.trim().toLowerCase();
  //: ★ 그룹째로 그린다(열 나눔이 그룹을 쪼개지 않게). 커서는 **항목 통번호**로 센다 —
  //:   ↑↓ 는 그룹을 넘어 이어져야 한다.
  const sections: { title: string; rows: { item: NavItem; idx: number }[] }[] = [];
  const flat: NavItem[] = [];
  //: ★★★ [2026-08-25] **1차 항목을 패널에 넣는다.**
  //:
  //: ⚠️⚠️ 종전에는 1차 셋(상담·협업·브리핑)이 **상단 바에만** 있었다. 그 상태로 바를
  //:   접으면 그 셋으로 가는 길이 화면에서 사라진다 — 「접는 것」과 「없애는 것」은
  //:   다르다. 그래서 접기 전에 갈 곳을 먼저 만든다.
  //: ★ 검색·↑↓·Enter 도 그대로 걸린다(같은 `flat` 에 들어가므로).
  for (const g of [{ title: '자주 쓰는 입구', items: primary }, ...groups]) {
    const hit = needle
      ? g.items.filter((it) => (it.label + ' ' + it.desc).toLowerCase().includes(needle))
      : g.items;
    if (!hit.length) continue;
    sections.push({ title: g.title, rows: hit.map((it) => ({ item: it, idx: flat.push(it) - 1 })) });
  }
  const itemIdx = flat.map((_, i) => i);
  const active = flat[cursor] ?? null;

  /** 찾기 칸에서의 ↑↓·Enter. ★ 손을 자판에서 떼지 않고 끝까지 간다. */
  const onSearchKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp' && e.key !== 'Enter') return;
    if (!itemIdx.length) return;
    e.preventDefault();
    if (e.key === 'Enter') {
      const it = flat[cursor];
      if (it && !it.disabledReason) { setOpen(false); it.onSelect(); }
      return;
    }
    const next = e.key === 'ArrowDown'
      ? Math.min(flat.length - 1, cursor + 1)
      : Math.max(0, cursor - 1);
    setCursor(next);
    rowRefs.current[next]?.scrollIntoView({ block: 'nearest' });
  };

  //: 검색 결과가 바뀌면 커서를 첫 항목으로 — 그룹 머리에 놓이면 설명 칸이 빈다.
  useEffect(() => {
    if (open) setCursor(0);
  }, [q, open]);

  return (
    <div className="flex items-center gap-2 min-w-0">
      {/* ── 1차 영역 ────────────────────────────────────────────────────── */}
      {/* ★ [설계 §9.2] 좁은 폭에서 **라벨을 접는다.** `shrink-0` 이라 줄지 않아 1024px 에서
          문서가 1205px 로 넘쳐 **가로 스크롤**이 생겼다(실측). 가로 스크롤은 «조금 불편» 이
          아니라 오른쪽 내용이 화면 밖으로 나가 버리는 것이다.
          ⚠️ 처음에 `xl`(1280)로 잡았더니 **정확히 1280px 에서 다시 넘쳤다** — 그 폭이 라벨을
            펼치기에 딱 모자라는 경계였기 때문이다. 브레이크포인트는 «디자인 눈금» 이 아니라
            **내용이 실제로 들어가는 폭**에서 정해야 한다. 재 보고 `2xl`(1536)로 올렸다.
          ⚠️ 아이콘만 남으면 무슨 버튼인지 알 수 없으므로 `aria-label` 로 이름을 남긴다 —
            보이지 않게 하는 것과 **없애는 것**은 다르다(스크린리더·키보드 사용자). */}
      {/* ★★★ [2026-08-25] 1차 아이콘 셋을 **바에서 뺐다.** 승인 시안의 행동 칸은
          `[⚙][＋ 새 업무]` 뿐인데, 우리는 여기에 사용자 정보·전체 메뉴·1차 셋까지
          밀어 넣어 **713px** 을 썼다(시안 125px). 그 결과 전역 내비가 828 → 470 으로
          눌렸다 — 시안과 「딱 봐도 다른」 것의 절반이 이것이었다.
          ★ 없앤 것이 아니라 **패널로 옮겼다**(위 `자주 쓰는 입구`). */}

      {/* ── 전체 메뉴 ───────────────────────────────────────────────────── */}
      <button
        ref={btnRef}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="global-nav-panel"
        aria-haspopup="true"
        title="나머지 기능을 업무 영역별로 모아 봅니다"
        aria-label="전체 메뉴"
        className="shrink-0 text-[13px] font-bold text-gray-200 bg-white/10 hover:bg-white/20 border border-white/20 px-2 py-2 rounded-lg transition-all flex items-center gap-2"
      >
        ☰ <span className="hidden 2xl:inline">전체 메뉴</span>
        <span className="text-xs font-semibold text-gray-300">{total}</span>
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
          className="afs-palette afs-global-menu flex flex-col overflow-hidden
                     bg-gray-900 border border-gray-700 rounded-xl shadow-2xl"
        >
          {/* ── 찾기 ─────────────────────────────────────────────────────
              ★ 20개를 «훑어 읽게» 하지 않는다. 두세 글자만 치면 남는다. */}
          <div className="flex-none p-3 border-b border-gray-700">
            <input
              ref={searchRef}
              value={q}
              onChange={(e) => { setQ(e.target.value); setCursor(0); }}
              onKeyDown={onSearchKey}
              placeholder="기능 찾기 — 예: 승인, 계산, 조직"
              aria-label="기능 찾기"
              className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2
                         text-[13px] text-gray-100 placeholder:text-gray-500
                         focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            />
          </div>

          {/* ── 목록 — 한 줄에 하나, 넓으면 2열. 설명은 아래 한 칸에서만. ────
              ⚠️ 그룹째로 열을 나눈다(`break-inside-avoid`). 줄 단위로 나누면 그룹
                머리가 1열 맨 아래에, 그 항목들이 2열 맨 위에 떨어져 남남이 된다. */}
          {/* ⚠️ `flex-1` 을 쓰지 않는다 — `flex:1 1 0` 은 남은 높이를 **다 차지해서**
              항목이 20개든 3개든 패널이 화면 끝까지 내려온다(실측: 700px 창에서 700px).
              `min-h-0` 만 두면 내용만큼만 잡고, 넘칠 때만 스크롤한다. */}
          <div className="min-h-0 overflow-y-auto py-2 px-1 sm:columns-2 sm:gap-2">
            {!itemIdx.length && (
              <p className="px-4 py-6 text-[13px] text-gray-400">
                «{q}» 와 맞는 기능이 없습니다.
              </p>
            )}
            {sections.map((sec) => (
              <section key={sec.title} className="break-inside-avoid mb-2">
                <div className="px-3 pt-1 pb-0.5 text-[11px] font-bold tracking-wider
                                text-gray-500">
                  {sec.title}
                </div>
                {sec.rows.map(({ item, idx }) => (
                  <button
                    key={item.id}
                    role="menuitem"
                    ref={(el) => { rowRefs.current[idx] = el; }}
                    disabled={Boolean(item.disabledReason)}
                    aria-disabled={Boolean(item.disabledReason) || undefined}
                    onMouseEnter={() => setCursor(idx)}
                    onFocus={() => setCursor(idx)}
                    onClick={() => {
                      if (item.disabledReason) return;
                      setOpen(false);
                      item.onSelect();
                    }}
                    className={`w-full text-left px-3 py-[5px] rounded-md flex items-center gap-2.5
                                focus:outline-none transition-colors
                                ${item.disabledReason
                        ? 'opacity-55 cursor-not-allowed'
                        : idx === cursor ? 'bg-white/10' : 'hover:bg-white/10'}`}
                  >
                    <span className="w-5 shrink-0 text-center text-[14px] leading-none">
                      {item.icon}
                    </span>
                    <span className="text-[13px] font-medium text-gray-100 truncate">
                      {item.label}
                    </span>
                    {item.disabledReason && (
                      <span className="ml-auto shrink-0 text-[11px] text-amber-300/90">🔒</span>
                    )}
                  </button>
                ))}
              </section>
            ))}
          </div>

          {/* ── 지금 가리키는 것 하나만 설명한다 ──────────────────────────
              ⚠️⚠️ 설명을 항목마다 붙였더니 **20개가 통째로 쏟아졌다**(2026-08-24 지적).
                그렇다고 툴팁으로만 두면 키보드·터치 사용자는 영영 못 본다.
              ★ 그래서 «가리키는 것 하나»의 설명을 고정된 자리에 둔다 — 마우스를 올려도,
                ↑↓ 로 옮겨도 같은 자리에서 읽힌다. */}
          <div className="flex-none border-t border-gray-700 px-4 py-2.5 min-h-[52px]">
            {active ? (
              <>
                <p className="text-xs text-gray-300 leading-relaxed">{active.desc}</p>
                {active.disabledReason && (
                  <p className="text-xs text-amber-300/90 mt-1 leading-relaxed">
                    🔒 {active.disabledReason}
                  </p>
                )}
              </>
            ) : (
              <p className="text-xs text-gray-500">
                ↑↓ 로 고르고 Enter 로 엽니다 · Esc 로 닫습니다
              </p>
            )}
          </div>
        </div>,
        document.body,
      )}

      {right}
    </div>
  );
}
