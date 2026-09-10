import guides from '../content/kitGettingStarted.json';

/** 업무 안내는 실제 준비도나 실행 권한을 판정하지 않는다. 정본 패키지와 개정이 맞을 때만 표시한다. */
export function KitGettingStarted({ kitId, version, groupId, canPrepare = false }: {
  kitId: string; version: string; groupId: string; canPrepare?: boolean;
}) {
  if (kitId !== guides.kit_id || version !== guides.version) return null;
  const guide = guides.groups.find((item) => item.id === groupId);
  if (!guide) return null;
  return (
    <section aria-label="이 업무 시작하기" style={{ padding: '6px 14px 14px', fontSize: 14,
      lineHeight: 1.65, wordBreak: 'keep-all', overflowWrap: 'anywhere' }}>
      <p style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>{guide.question}</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 240px), 1fr))', gap: 12 }}>
        {[
          ['준비할 자료', guide.bring],
          ['함께 대조할 것', guide.check],
          ['결과를 활용하는 방법', guide.handoff],
        ].map(([title, body]) => (
          <div key={title} style={{ background: 'var(--surface-raised)', borderRadius: 8, padding: 12 }}>
            <strong>{title}</strong>
            <p style={{ margin: '6px 0 0' }}>{body}</p>
          </div>
        ))}
      </div>
      <p style={{ margin: '12px 0 0', color: 'var(--surface-text-muted)' }}>
        <strong>사용 범위 · </strong>{guide.limit}
      </p>
      {canPrepare && <p style={{ margin: '8px 0 0', color: 'var(--surface-text-muted)' }}>
        아래 준비도는 현재 데이터의 실제 상태입니다. 자료를 추가하려면 해당 업무 데이터의 ‘자료 준비’를 선택하십시오.
      </p>}
    </section>
  );
}
