/**
 * [LE-01 §4.3–4.4] **Enterprise Digital Thread** — 승인 시안의 중앙 축.
 *
 * ## ⚠️⚠️ 왜 다시 만들었는가 (2026-08-24)
 *
 * 승인 시안(`uiux-prototypes/master-concept/index.html`, 2026-07-30 채택)의 중앙 축은
 * **수주→손익 일곱 단계**다:
 *
 *     01 수주·판매 · 02 원료조달 · 03 생산계획 · 04 제련·생산
 *     05 품질 · 06 물류·출하 · 07 손익·경영
 *
 * 구현은 그것을 줄 API 가 없어서 **조직 트리**(본사·제련공장)로 대체했고, 노드 안에는
 * 「도메인 0 · 템플릿 미지정 · 에이전트 0」이라는 **조직 설정 목록**을 그렸다. 그것은
 * 업무 상태가 아니고, 사용자는 보고 할 수 있는 일이 없었다.
 *
 * ★ 이제 `GET /api/v1/briefing/canvas` 가 일곱 단계를 **업무 키트 계약키에 근거해서**
 *   준다. 각 단계의 상태는 그 단계가 쓰는 자료가 인증됐는지에서 나온다 — 짐작이 아니다.
 * ⚠️ 시안의 `수요 +3%`·`가동 94%` 같은 대표 지표는 시안 표본값이다(`PROTOTYPE · SAMPLE
 *   DATA`). 채택 결정문이 「실제 API 근거가 있을 때만 노출」을 못박았으므로, 근거가
 *   생기기 전에는 그 자리를 **비운다.**
 */
import type { DomainNode } from '../lib/canvasApi';

const STATUS: Record<string, { label: string; fg: string; bg: string; dot: string }> = {
  normal: { label: '정상', fg: 'var(--state-success-fg)', bg: 'var(--state-success-bg)',
    dot: 'var(--state-success-fg)' },
  attention: { label: '확인 필요', fg: 'var(--state-warn-fg)', bg: '#fffbeb',
    dot: 'var(--state-warn-fg)' },
  decision_required: { label: '결정 필요', fg: '#fff', bg: 'var(--ls-navy)',
    dot: 'var(--ls-navy)' },
  blocked: { label: '막힘', fg: 'var(--state-error-fg)', bg: 'var(--state-error-bg)',
    dot: 'var(--state-error-fg)' },
  unknown: { label: '확인 못 함', fg: 'var(--surface-text-muted)',
    bg: 'var(--surface-raised)', dot: 'var(--surface-text-faint)' },
};

export function EnterpriseThread({ nodes, selected, onSelect, systemsVerified }: {
  nodes: DomainNode[];
  selected: string;
  onSelect: (id: string) => void;
  /** 노드 아래 시스템 이름이 **실제 연결 확인을 거친 값인가.** 아니면 그렇게 적는다. */
  systemsVerified: boolean;
}) {
  return (
    <div>
      {/* §4.3 「줌/팬보다 업무 단계 선택 → 관련 레이어/결정 보기를 우선」 */}
      <div style={{
        display: 'grid', gap: 8,
        gridTemplateColumns: 'repeat(auto-fit, minmax(132px, 1fr))',
      }}>
        {nodes.map((n) => {
          const st = STATUS[n.status] || STATUS.unknown;
          const on = selected === n.id;
          return (
            <button
              key={n.id}
              onClick={() => onSelect(on ? '' : n.id)}
              title={n.reason || n.label}
              style={{
                /* §4.4 노드 선택 면적 최소 64×64px */
                minHeight: 92, padding: '10px 12px', cursor: 'pointer', textAlign: 'left',
                borderRadius: 8, display: 'flex', flexDirection: 'column', gap: 4,
                border: `1px solid ${on ? 'var(--ls-navy)' : 'var(--surface-border)'}`,
                boxShadow: on ? '0 0 0 1px var(--ls-navy) inset' : 'none',
                background: 'var(--surface-card)', color: 'var(--surface-text)',
                minWidth: 0,
              }}
            >
              <span style={{
                fontSize: 11, fontFamily: 'var(--font-mono, monospace)',
                color: 'var(--surface-text-faint)',
              }}>
                {String(n.sequence).padStart(2, '0')}
              </span>
              <span style={{ fontSize: 14, fontWeight: 700 }}>{n.label}</span>
              <span style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
                {n.systems}
              </span>
              {/* ★ 시안의 세 번째 줄은 그 단계의 **지금 신호**다. 대표 지표가 없으면
                  상태로 답한다 — 빈 줄로 두면 무엇을 못 보여 주는지도 알 수 없다. */}
              <span style={{
                marginTop: 'auto', fontSize: 12, fontWeight: 600,
                display: 'inline-flex', alignItems: 'center', gap: 5,
                color: n.status === 'decision_required' ? 'var(--ls-navy)' : st.fg,
              }}>
                <span aria-hidden="true" style={{
                  width: 7, height: 7, borderRadius: 999, background: st.dot,
                  flex: '0 0 auto',
                }} />
                {n.primary_metric
                  ? `${n.primary_metric.label} ${n.primary_metric.value}`
                  : st.label}
              </span>
              {/* §4.4 evidence_count — ⚠️ `null` 은 「못 셌다」이지 0 이 아니다. */}
              <span style={{ fontSize: 11, color: 'var(--surface-text-faint)' }}>
                {n.evidence_count === null || n.evidence_count === undefined
                  ? '근거 확인 못 함'
                  : `인증 자료 ${n.evidence_count}종`}
              </span>
            </button>
          );
        })}
      </div>
      {!systemsVerified && (
        /* ⚠️ 시스템 이름은 시안이 적은 **표시 문구**다. 실제 연결 확인은 연계·크로스워크가
            한다 — 둘을 같은 것으로 읽으면 「연결됐다」는 오해가 생긴다. */
        <p style={{ fontSize: 11.5, color: 'var(--surface-text-faint)', marginTop: 8 }}>
          노드 아래 시스템 이름은 이 단계가 보통 쓰는 시스템을 적은 것입니다 — 실제 연결
          여부는 «연계/크로스워크»에서 확인하십시오.
        </p>
      )}
    </div>
  );
}
