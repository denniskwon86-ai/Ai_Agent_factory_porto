// [UI 설계서 §5.1 Decision Drawer] 경영 홈에서 안건 하나를 **끝까지 처리하는 자리.**
//
// ## 설계가 못박은 것
//
// · 너비 **520px**
// · 순서 **Summary → Impact → Evidence → Related objects → Approval → History**
// · **주요 행동 sticky footer**
//
// ## ⚠️ 「결정할 수 없는 경우」를 결정 버튼으로 덮지 않는다
//
// §5.3 이 의사결정 화면에 대해 「사용자가 아직 결정할 수 없는 경우 `결정` CTA 대신 **부족 근거와
// 재계산·추가검토 행동**을 표시한다」고 못박았다. 같은 규칙을 여기에도 적용한다 — 누를 수 없는
// 버튼을 회색으로 두면 사용자는 화면 고장으로 읽고, 진짜 이유는 아무에게도 도달하지 않는다.
//
// ⚠️ 서버가 주지 않는 것(승인 이력·참여자·영향 수치)은 **지어내지 않고** 무엇이 없는지 적는다.
//   브리핑 항목이 들고 있는 것은 kind·severity·title·why·suggested_action·ref·ref_type 뿐이다.
import { type BriefingItem } from '../lib/briefingApi';

const SEVERITY_KO: Record<string, string> = {
  high: '긴급', medium: '확인 필요', low: '참고', info: '정보',
};

/** 안건 종류 → 사람이 읽는 말. ⚠️ 모르는 종류를 «기타» 로 뭉개지 않는다 — 원본 코드를 보여
 *  주어야 어느 경로에서 온 안건인지 되짚을 수 있다. */
const KIND_KO: Record<string, string> = {
  promotion_requested: '전사 승격 승인 대기',
  gate_fail: '게이트 차단',
  contract_breached: '데이터 계약 위반',
  approval_pending: '승인 대기',
};

export function DecisionDrawer({ item, onClose, onOpenRef }: {
  item: BriefingItem & { section?: string };
  onClose: () => void;
  onOpenRef: (refType: string, ref: string) => void;
}) {
  const sec = (title: string, body: React.ReactNode) => (
    <section style={{ padding: '16px 20px', borderBottom: '1px solid var(--surface-border)' }}>
      <div style={{ fontSize: 11, letterSpacing: '.08em', marginBottom: 8,
        fontFamily: 'var(--font-mono, monospace)', color: 'var(--surface-text-faint)' }}>
        {title}
      </div>
      {body}
    </section>
  );

  const muted = { fontSize: 13, color: 'var(--surface-text-muted)', margin: 0, lineHeight: 1.6 };
  const body = { fontSize: 14, color: 'var(--surface-text)', margin: 0, lineHeight: 1.65 };

  return (
    <>
      {/* 배경 — 클릭으로 닫지 않는다(입력 중이던 것이 한 번의 실수로 사라진다) */}
      <div style={{ position: 'fixed', inset: 0, background: 'var(--backdrop)', zIndex: 40 }} />
      <aside role="dialog" aria-modal="true" aria-label={`안건 상세: ${item.title}`}
        style={{
          position: 'fixed', top: 0, right: 0, bottom: 0,
          width: 520, maxWidth: '96vw', zIndex: 41,          // §5.1 너비 520px
          background: 'var(--surface-card)', borderLeft: '1px solid var(--surface-border)',
          display: 'flex', flexDirection: 'column',
          boxShadow: 'var(--surface-shadow)',
        }}>
        {/* 머리 */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--surface-border)',
          display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
              {KIND_KO[item.kind] || item.kind} · {SEVERITY_KO[item.severity] || item.severity}
            </div>
            <h2 style={{ fontSize: 17, margin: '4px 0 0', lineHeight: 1.4,
              color: 'var(--surface-text)' }}>{item.title}</h2>
          </div>
          <button onClick={onClose} style={{
            height: 36, padding: '0 14px', fontSize: 13, borderRadius: 6, cursor: 'pointer',
            border: '1px solid var(--action-secondary-border)',
            background: 'var(--action-secondary-bg)', color: 'var(--action-secondary-fg)',
          }}>닫기</button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {/* ① Summary */}
          {sec('SUMMARY', <p style={body}>{item.why || '요약이 없습니다.'}</p>)}

          {/* ② Impact — ⚠️ 수치가 없다. 없는 것을 0 으로 그리지 않는다. */}
          {sec('IMPACT', (
            <>
              <p style={body}>
                {item.severity === 'high'
                  ? '지금 처리하지 않으면 관련 작업이 진행되지 않습니다.'
                  : '진행에 영향을 주지만 즉시 멈추지는 않습니다.'}
              </p>
              <p style={{ ...muted, marginTop: 6 }}>
                ⚠️ 정량 영향(금액·일정·건수)은 서버가 이 안건에 대해 계산하지 않습니다 —
                숫자를 지어내지 않았습니다.
              </p>
            </>
          ))}

          {/* ③ Evidence */}
          {sec('EVIDENCE', (
            item.ref ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ fontSize: 13, color: 'var(--surface-text)' }}>
                  {item.ref_type || '참조'}
                </div>
                <code style={{ fontSize: 12, padding: '8px 10px', borderRadius: 6,
                  fontFamily: 'var(--font-mono, monospace)', wordBreak: 'break-all',
                  background: 'var(--surface-sunken)', color: 'var(--surface-text)' }}>
                  {item.ref}
                </code>
              </div>
            ) : <p style={muted}>이 안건에는 참조가 붙어 있지 않습니다.</p>
          ))}

          {/* ④ Related objects */}
          {sec('RELATED', (
            item.ref ? (
              <button onClick={() => onOpenRef(item.ref_type || '', item.ref)} style={{
                height: 36, padding: '0 14px', fontSize: 13, borderRadius: 6, cursor: 'pointer',
                border: '1px solid var(--action-secondary-border)',
                background: 'var(--action-secondary-bg)', color: 'var(--action-secondary-fg)',
              }}>관련 화면 열기</button>
            ) : <p style={muted}>연결된 객체가 없습니다.</p>
          ))}

          {/* ⑤ Approval — 결정할 수 없으면 CTA 대신 «무엇이 부족한가» 를 적는다 */}
          {sec('APPROVAL', (
            <>
              <p style={body}>{item.suggested_action || '지정된 다음 행동이 없습니다.'}</p>
              <p style={{ ...muted, marginTop: 8 }}>
                ⚠️ 승인은 <b>해당 화면에서</b> 이뤄집니다 — 이 서랍은 무엇을 결정해야 하는지와
                그 근거를 모아 보여 줄 뿐, 승인 권한 판정을 여기서 다시 하지 않습니다.
              </p>
            </>
          ))}

          {/* ⑥ History */}
          {sec('HISTORY', (
            <p style={muted}>
              이 안건의 처리 이력은 서버가 별도로 주지 않습니다 — 감사 로그(관리자 화면)에서
              «누가 언제 무엇을 승인했는가» 를 확인할 수 있습니다.
            </p>
          ))}
        </div>

        {/* §5.1 주요 행동 sticky footer */}
        <div style={{
          position: 'sticky', bottom: 0, padding: '14px 20px',
          borderTop: '1px solid var(--surface-border)', background: 'var(--surface-card)',
          display: 'flex', gap: 10, justifyContent: 'flex-end',
        }}>
          <button onClick={onClose} style={{
            height: 44, padding: '0 18px', fontSize: 14, borderRadius: 6, cursor: 'pointer',
            border: '1px solid var(--action-secondary-border)',
            background: 'var(--action-secondary-bg)', color: 'var(--action-secondary-fg)',
          }}>나중에</button>
          <button onClick={() => onOpenRef(item.ref_type || '', item.ref)}
            disabled={!item.ref} style={{
              height: 46, padding: '0 20px', fontSize: 14, fontWeight: 700, borderRadius: 6,
              cursor: item.ref ? 'pointer' : 'not-allowed', opacity: item.ref ? 1 : .55,
              border: '1px solid var(--ls-navy)',
              background: 'var(--action-primary-bg)', color: 'var(--action-primary-fg)',
            }}>처리하러 가기</button>
        </div>
      </aside>
    </>
  );
}
