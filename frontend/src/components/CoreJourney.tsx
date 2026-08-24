/**
 * 경영 홈 맨 위 — **이 시스템으로 하는 일 넷.**
 *
 * ## ⚠️⚠️ 왜 만들었는가 (2026-08-24 사용자 지적)
 *
 * > 들어가서 눌러서 보는 건 보는 건데… 그건 기능이 어딘가에 있어서 찾아야 보이는 거고,
 * > 핵심적인 주요 기능은 메인 화면에 꺼내져 있어야지. 상징적인 아이콘이나 버튼으로,
 * > 구구절절 설명을 달지 않더라도 알아볼 수 있도록.
 *
 * 맞다. 「전체 메뉴」를 정리한 것은 **찾을 수 있게** 한 것이지 **보이게** 한 것이 아니다.
 * 처음 여는 사람은 메뉴가 있다는 것조차 모른다.
 *
 * ★ 그래서 넷을 꺼낸다. 설명 문단을 붙이지 않는다 — **번호·아이콘·두 낱말**로 읽히게 한다.
 * ★★★ 그리고 **지금 어디까지 됐는지**를 함께 보여 준다. 「무엇을 누를 수 있나」보다
 *   「다음에 무엇을 해야 하나」가 처음 여는 사람에게 훨씬 중요하다.
 *
 * ⚠️ 상태를 **지어내지 않는다.** 준비도를 못 읽었거나 키트 인스턴스가 없으면 상태 칩을
 *   아예 그리지 않는다 — 「모른다」를 「됐다」로 칠하면 그 화면은 거짓말을 한다.
 */
import { useEffect, useState } from 'react';

import { API_BASE_URL, getSessionToken } from '../lib/api';

type Step = 'done' | 'now' | 'todo' | 'unknown';

const TILES: { id: string; no: string; icon: string; label: string }[] = [
  { id: 'dataprep', no: '1', icon: '📥', label: '자료 준비' },
  { id: 'calc-approval', no: '2', icon: '🔐', label: '계산 승인' },
  { id: 'path-calc', no: '3', icon: '🧮', label: '영향 계산' },
  { id: 'decision-pkg', no: '4', icon: '⚖️', label: '의사결정' },
];

const CHIP: Record<Exclude<Step, 'unknown'>, { text: string; fg: string; bg: string }> = {
  done: { text: '완료', fg: 'var(--state-success-fg)', bg: 'var(--state-success-bg)' },
  now: { text: '여기부터', fg: 'var(--action-primary-fg)', bg: 'var(--ls-navy)' },
  todo: { text: '대기', fg: 'var(--surface-text-muted)', bg: 'var(--surface-raised)' },
};

/** 준비도 관문 → 네 단계의 상태. ⚠️ 못 읽으면 전부 `unknown` 이다. */
function stepsFrom(gates: { gate: string; state: string }[] | null): Step[] {
  if (!gates || !gates.length) return ['unknown', 'unknown', 'unknown', 'unknown'];
  const at = (g: string) => gates.find((x) => x.gate === g)?.state || '';
  //: 1) 자료 — 인증판과 기준선이 모두 서야 «준비됨» 이다.
  const data = at('snapshots') === 'READY' && at('baseline') === 'READY';
  //: 2) 승인 — 사람이 눌러야 열리는 관문.
  const appr = at('capabilities') === 'READY';
  const out: Step[] = [
    data ? 'done' : 'now',
    !data ? 'todo' : appr ? 'done' : 'now',
    !appr ? 'todo' : 'now',
    !appr ? 'todo' : 'todo',
  ];
  return out;
}

export function CoreJourney({ onOpen }: { onOpen: (id: string) => void }) {
  const [steps, setSteps] = useState<Step[]>(['unknown', 'unknown', 'unknown', 'unknown']);

  useEffect(() => {
    let alive = true;
    const head = { 'X-Session-Token': getSessionToken() };
    //: ⚠️ 표시용이다 — 실패하면 **상태를 비운다.** 화면을 막지도, 추측하지도 않는다.
    (async () => {
      try {
        const r1 = await fetch(`${API_BASE_URL}/api/v1/data-preparation/instances`,
          { headers: head });
        if (!r1.ok) return;
        const b1 = await r1.json();
        const list = b1?.data?.instances ?? b1?.data ?? [];
        const id = Array.isArray(list) && list.length ? list[0].instance_id : '';
        if (!id) return;
        const r2 = await fetch(
          `${API_BASE_URL}/api/v1/calculation/readiness?instance_id=${encodeURIComponent(id)}`,
          { headers: head });
        if (!r2.ok) return;
        const b2 = await r2.json();
        if (alive) setSteps(stepsFrom(b2?.data?.gates || null));
      } catch {
        /* 상태를 모르는 채로 둔다 */
      }
    })();
    return () => { alive = false; };
  }, []);

  return (
    <div style={{
      display: 'grid', gap: 10, width: '100%',
      gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
    }}>
      {TILES.map((t, i) => {
        const st = steps[i];
        const chip = st === 'unknown' ? null : CHIP[st];
        const isNow = st === 'now';
        return (
          <button
            key={t.id}
            onClick={() => onOpen(t.id)}
            title={t.label}
            style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
              padding: '14px 10px 12px', borderRadius: 10, cursor: 'pointer',
              //: ★ 「지금 할 것」만 테두리로 세운다 — 넷 다 강조하면 강조가 아니다.
              border: `1px solid ${isNow ? 'var(--ls-navy)' : 'var(--surface-border)'}`,
              boxShadow: isNow ? '0 0 0 1px var(--ls-navy) inset' : 'none',
              background: 'var(--surface-card)', color: 'var(--surface-text)',
              minWidth: 0,
            }}
          >
            <span style={{
              fontSize: 11, fontWeight: 700, letterSpacing: '.04em',
              color: isNow ? 'var(--ls-navy)' : 'var(--surface-text-faint)',
            }}>
              STEP {t.no}
            </span>
            <span aria-hidden="true" style={{ fontSize: 30, lineHeight: 1 }}>{t.icon}</span>
            <span style={{ fontSize: 15, fontWeight: 700 }}>{t.label}</span>
            {/* ⚠️ 모르면 칩을 그리지 않는다 — 빈 자리가 「모른다」의 정직한 표시다. */}
            {chip ? (
              <span style={{
                fontSize: 11.5, fontWeight: 600, padding: '2px 8px', borderRadius: 999,
                color: st === 'now' ? '#fff' : chip.fg, background: chip.bg,
                border: st === 'todo' ? '1px solid var(--surface-border)' : 'none',
              }}>
                {chip.text}
              </span>
            ) : <span style={{ height: 20 }} />}
          </button>
        );
      })}
    </div>
  );
}
