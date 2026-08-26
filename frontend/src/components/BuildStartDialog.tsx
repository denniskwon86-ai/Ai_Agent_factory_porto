// [UI 설계서 §5.2 `/build/start`] **새 업무 만들기.**
//
// 설계는 목록면(`/build`)과 생성(`/build/start`)을 나눈다. 종전에는 생성 폼이 목록 위에
// 상시 펼쳐져 있어, 「이미 있는 것을 여는」 흔한 일보다 「새로 만드는」 드문 일이 화면을
// 차지했다.
//
// ## 설계가 못박은 것
//
// · 선택 옵션 **높이 56px 이상**, 추천안은 첫 번째이되 **사용자가 쉽게 변경 가능**
// · 「준비율 숫자보다 **확인된 조건·부족 데이터·다음 전환**을 설명한다」
//
// ⚠️ 아직 없는 것을 만들어 넣지 않는다. 설계 §5.2 의 «전체 Workflow Map + 앞으로 생성될
//   단계·산출물·승인 계약» 은 서버가 그 목록을 주지 않으므로, **무엇이 정해지고 무엇이 아직
//   정해지지 않았는지**를 적는 데서 멈춘다.
import { useEffect, useState } from 'react';

import { HubDialog } from '../design/HubDialog';
import { DataPrepError, listInstances } from '../lib/dataPrepApi';
import { KitAppPanel } from './KitAppPanel';

export type BuildStartResult = {
  projectId: string;
  isMega: boolean;
  templateId: string;
  packIds: string[];
  masterDomains: string;
  mcpLiveGrounding: boolean;
};

export function BuildStartDialog({
  templates, knowledgePacks, packsBlocked, onClose, onCreate, onOpenDataPrep,
}: {
  templates: { template_id: string; name?: string; pipeline_name?: string }[];
  knowledgePacks: any[];
  packsBlocked: string;
  onClose: () => void;
  onCreate: (r: BuildStartResult) => void;
  onOpenDataPrep: () => void;
}) {
  const [startMode, setStartMode] = useState<'kit' | 'general'>('kit');
  const [projectId, setProjectId] = useState('');
  const [isMega, setIsMega] = useState(false);
  const [templateId, setTemplateId] = useState(templates[0]?.template_id || 'default');
  const [packIds, setPackIds] = useState<string[]>([]);
  const [masterDomains, setMasterDomains] = useState('');
  const [mcp, setMcp] = useState(false);
  const [err, setErr] = useState('');

  const idOk = /^[A-Za-z0-9._-]{2,}$/.test(projectId.trim());
  const selectedTemplate = templates.find((t) => t.template_id === templateId);
  const selectedTemplateName = selectedTemplate?.pipeline_name || selectedTemplate?.name
    || '선택한 업무 절차';

  // 템플릿은 화면이 열린 뒤 비동기로 도착할 수 있다. 보이는 첫 옵션과 실제 제출값이
  // 갈라지지 않도록 현재 값이 목록에 없을 때만 첫 정본 값으로 맞춘다.
  useEffect(() => {
    if (templates.length && !templates.some((t) => t.template_id === templateId)) {
      setTemplateId(templates[0].template_id);
    }
  }, [templates, templateId]);

  const submit = () => {
    if (!idOk) {
      setErr('업무 식별자는 영문·숫자·`.`·`_`·`-` 로 2자 이상이어야 합니다.');
      return;
    }
    onCreate({
      projectId: projectId.trim(), isMega, templateId, packIds,
      masterDomains, mcpLiveGrounding: mcp,
    });
  };

  /** §5.2 «선택 옵션 높이 56px 이상» */
  const option = (on: boolean): React.CSSProperties => ({
    minHeight: 56, display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer',
    padding: '10px 16px', borderRadius: 8, textAlign: 'left', width: '100%',
    border: `1px solid ${on ? 'var(--ls-navy)' : 'var(--surface-border)'}`,
    background: on ? 'var(--surface-raised)' : 'var(--surface-card)',
    borderLeft: `4px solid ${on ? 'var(--ls-navy)' : 'transparent'}`,
  });

  const label: React.CSSProperties = {
    fontSize: 13, fontWeight: 600, color: 'var(--surface-text)', display: 'block',
    marginBottom: 6,
  };
  const input: React.CSSProperties = {
    height: 40, width: '100%', padding: '0 12px', fontSize: 14, borderRadius: 6,
    border: '1px solid var(--surface-border)', background: 'var(--surface-card)',
    color: 'var(--surface-text)',
  };

  return (
    <HubDialog label="새 업무 만들기" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>새 업무 만들기</b>
        <span>무엇을 만들지 정하면 그에 맞는 단계와 승인 지점이 준비됩니다</span>
        <div className="bar-actions">
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>

      <div className="afs-dialog-body" style={{ padding: 24, display: 'flex',
        flexDirection: 'column', gap: 20 }}>
        <div>
          <span style={label}>시작 방식</span>
          <div style={{ display: 'grid', gap: 10,
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>
            <button style={option(startMode === 'kit')} onClick={() => setStartMode('kit')}>
              <span style={{ fontSize: 20 }}>▦</span>
              <span>
                <b style={{ fontSize: 14, color: 'var(--surface-text)' }}>업무키트 기반 앱</b>
                <span style={{ display: 'block', fontSize: 12,
                  color: 'var(--surface-text-muted)' }}>
                  이 조직에 적용된 패키지의 준비도·계약을 확인하고 시작합니다 · 추천
                </span>
              </span>
            </button>
            <button style={option(startMode === 'general')} onClick={() => setStartMode('general')}>
              <span style={{ fontSize: 20 }}>＋</span>
              <span>
                <b style={{ fontSize: 14, color: 'var(--surface-text)' }}>일반 앱 제작</b>
                <span style={{ display: 'block', fontSize: 12,
                  color: 'var(--surface-text-muted)' }}>
                  업무 절차·지식·기준정보를 직접 골라 새 프로젝트를 만듭니다
                </span>
              </span>
            </button>
          </div>
        </div>

        {startMode === 'kit' ? (
          <KitStartFlow onOpenDataPrep={onOpenDataPrep} />
        ) : (<>
        {err && (
          <div style={{ fontSize: 13, padding: '10px 14px', borderRadius: 8,
            color: 'var(--state-error-fg)', background: 'var(--state-error-bg)' }}>{err}</div>
        )}

        <div>
          <span style={label}>업무 식별자 (영문)</span>
          <input style={input} value={projectId} autoFocus
            onChange={(e) => { setProjectId(e.target.value); setErr(''); }}
            placeholder="예: smart-life-app" />
          <p style={{ fontSize: 12, marginTop: 6, color: 'var(--surface-text-muted)' }}>
            작업공간 폴더 이름이 됩니다 — 나중에 바꾸기 어렵습니다.
          </p>
        </div>

        <div>
          <span style={label}>프로젝트 유형</span>
          <div style={{ display: 'grid', gap: 10,
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
            {/* 추천안이 첫 번째 — 그러나 바꾸기 쉬워야 한다(§5.2) */}
            <button style={option(!isMega)} onClick={() => setIsMega(false)}>
              <span style={{ fontSize: 20 }}>📄</span>
              <span>
                <b style={{ fontSize: 14, color: 'var(--surface-text)' }}>독립 프로젝트</b>
                <span style={{ display: 'block', fontSize: 12,
                  color: 'var(--surface-text-muted)' }}>
                  선택한 업무 절차를 따라 단일 목표를 수행합니다 · 추천
                </span>
              </span>
            </button>
            <button style={option(isMega)} onClick={() => setIsMega(true)}>
              <span style={{ fontSize: 20 }}>🌟</span>
              <span>
                <b style={{ fontSize: 14, color: 'var(--surface-text)' }}>통합 프로젝트</b>
                <span style={{ display: 'block', fontSize: 12,
                  color: 'var(--surface-text-muted)' }}>
                  여러 프로젝트를 묶어 상위 목표로 운영합니다
                </span>
              </span>
            </button>
          </div>
        </div>

        <div>
          <span style={label}>업무 진행 절차</span>
          <select style={input} value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}>
            {(templates || []).map((t) => (
              <option key={t.template_id} value={t.template_id}>
                {t.pipeline_name || t.name || t.template_id}
              </option>
            ))}
          </select>
          <p style={{ fontSize: 12, marginTop: 6, color: 'var(--surface-text-muted)' }}>
            어떤 역할이 어떤 순서로 일하고 어디서 사람이 확인하는지가 여기서 정해집니다.
          </p>
        </div>

        <div>
          <span style={label}>연결할 지식팩 (선택)</span>
          {packsBlocked ? (
            <p style={{ fontSize: 13, color: 'var(--state-warn-fg)' }}>{packsBlocked}</p>
          ) : (knowledgePacks || []).length === 0 ? (
            <p style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>
              등록된 지식팩이 없습니다 — 지식 허브에서 표준·논문 등을 먼저 등록하십시오.
            </p>
          ) : (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {knowledgePacks.map((p: any) => {
                const on = packIds.includes(p.pack_id);
                return (
                  <button key={p.pack_id}
                    onClick={() => setPackIds((prev) => on
                      ? prev.filter((x) => x !== p.pack_id) : [...prev, p.pack_id])}
                    style={{
                      height: 36, padding: '0 14px', fontSize: 13, borderRadius: 6,
                      cursor: 'pointer',
                      border: `1px solid ${on ? 'var(--ls-cyan)' : 'var(--surface-border)'}`,
                      background: on ? 'var(--state-info-bg)' : 'var(--surface-card)',
                      color: on ? 'var(--state-info-fg)' : 'var(--surface-text-muted)',
                    }}>
                    {on ? '✓ ' : ''}{p.name || p.pack_id}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div>
          <span style={label}>연결할 기준정보 분야 (선택)</span>
          <input style={input} value={masterDomains}
            onChange={(e) => setMasterDomains(e.target.value)}
            placeholder="콤마 구분 · 예: manufacturing, logistics" />
          <p style={{ fontSize: 12, marginTop: 6, color: 'var(--surface-text-muted)' }}>
            선택한 분야의 승인된 기준정보가 모든 산출물에 일관되게 반영됩니다.
          </p>
        </div>

        <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', cursor: 'pointer' }}>
          <input type="checkbox" checked={mcp} onChange={(e) => setMcp(e.target.checked)}
            style={{ marginTop: 3 }} />
          <span>
            <b style={{ fontSize: 14, color: 'var(--surface-text)' }}>외부 연계 실측값 함께 보기</b>
            <span style={{ display: 'block', fontSize: 12, color: 'var(--surface-text-muted)' }}>
              활성 연계 시스템의 실측값을 산출물에 참고로 붙입니다 — 처리 시간과 호출 한도가 늘어납니다.
            </span>
          </span>
        </label>

        {/* §5.2 «준비율 숫자보다 확인된 조건·부족 데이터·다음 전환» */}
        <div style={{ background: 'var(--surface-raised)',
          border: '1px solid var(--surface-border)', borderRadius: 8, padding: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--surface-text)' }}>
            지금 정해진 것
          </div>
          <ul style={{ margin: '8px 0 0', paddingLeft: 18, fontSize: 13, lineHeight: 1.7,
            color: 'var(--surface-text-muted)' }}>
            <li>유형 — {isMega ? '통합 프로젝트' : '독립 프로젝트'}</li>
            <li>업무 절차 — {selectedTemplateName}</li>
            <li>지식팩 — {packIds.length ? `${packIds.length}개 연결` : '연결 없음'}</li>
            <li>기준정보 — {masterDomains.trim() || '지정 없음'}</li>
          </ul>
          <div style={{ fontSize: 12, marginTop: 10, color: 'var(--surface-text-faint)' }}>
            다음 전환: 만들면 요구 확인 단계부터 시작하며, 사람이 확인해야 하는 지점에서 멈춥니다.
          </div>
        </div>

        {/* ⚠️⚠️ [2026-08-24 사용자 지적] **못 누르는 이유를 화면에 적는다**(설계 §8.6).
            종전에는 `disabled={!idOk}` 뿐이었다. Project ID 가 비면 버튼이 죽어 있는데
            **아무 문구도 없어서**, 사용자는 눌러 보고 「안 넘어간다」고 읽는다.
            ★ `submit()` 안의 `setErr(...)` 는 도달하지 못하는 코드였다 — 버튼이 죽어 있으면
              `submit` 자체가 불리지 않는다. 그래서 안내는 **여기서** 한다. */}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end',
          alignItems: 'center', flexWrap: 'wrap', position: 'sticky', bottom: 0, zIndex: 2,
          margin: '0 -2px -2px', padding: '12px 2px 2px',
          borderTop: '1px solid var(--surface-border)', background: 'var(--surface-page)' }}>
          {!idOk && (
            <span style={{ fontSize: 12.5, color: 'var(--surface-text-muted)',
              marginRight: 'auto' }}>
              {!projectId.trim()
                ? '맨 위 업무 식별자를 입력하면 «이 조건으로 만들기»가 켜집니다.'
                : '업무 식별자는 영문·숫자·`.`·`_`·`-` 로 2자 이상이어야 합니다 — '
                  + '지금 값으로는 만들 수 없습니다.'}
            </span>
          )}
          <button onClick={onClose} style={{
            height: 44, padding: '0 18px', fontSize: 14, borderRadius: 6, cursor: 'pointer',
            border: '1px solid var(--action-secondary-border)',
            background: 'var(--action-secondary-bg)', color: 'var(--action-secondary-fg)',
          }}>취소</button>
          <button onClick={submit} disabled={!idOk}
            title={idOk ? '' : '업무 식별자를 입력해야 만들 수 있습니다.'} style={{
            height: 46, padding: '0 22px', fontSize: 14, fontWeight: 700, borderRadius: 6,
            cursor: idOk ? 'pointer' : 'not-allowed', opacity: idOk ? 1 : .55,
            border: '1px solid var(--ls-navy)',
            background: 'var(--action-primary-bg)', color: 'var(--action-primary-fg)',
          }}>이 조건으로 만들기</button>
        </div>
        </>)}
      </div>
    </HubDialog>
  );
}

/** 현재 사용자가 **볼 수 있는 조직 적용본**에서만 앱 생성 흐름을 시작한다.
 *
 * 임의 `kit_instance_id` 입력을 받지 않는다. 적용본을 골라도 서버가 내려 준 준비도와
 * 계약 상태를 `KitAppPanel`이 다시 확인하며, 승인된 계약 전에는 앱 만들기 행동이 열리지 않는다.
 */
function KitStartFlow({ onOpenDataPrep }: { onOpenDataPrep: () => void }) {
  const [instances, setInstances] = useState<any[] | null>(null);
  const [selected, setSelected] = useState('');
  const [error, setError] = useState<{ message: string; status: number } | null>(null);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let alive = true;
    setInstances(null);
    setError(null);
    listInstances()
      .then((d) => {
        if (!alive) return;
        const rows = d.instances || [];
        setInstances(rows);
        if (rows.length === 1) setSelected(String(rows[0].instance_id || ''));
      })
      .catch((e: unknown) => {
        if (!alive) return;
        const err = e as DataPrepError;
        setError({ message: err?.message || '적용된 업무키트를 확인하지 못했습니다.',
          status: err?.status || 0 });
      });
    return () => { alive = false; };
  }, [revision]);

  if (error) {
    return (
      <div style={{ padding: 14, borderRadius: 8, border: '1px solid var(--state-error-fg)',
        background: 'var(--state-error-bg)' }}>
        <strong style={{ color: 'var(--state-error-fg)' }}>업무키트를 확인하지 못했습니다</strong>
        <div style={{ fontSize: 13, marginTop: 5 }}>{error.message}</div>
        <div style={{ fontSize: 12, marginTop: 5, color: 'var(--surface-text-muted)' }}>
          {error.status === 404 ? '현재 회사·조직 범위를 다시 확인하십시오.'
            : '적용본이 없는 것이 아니라 지금 조회하지 못한 상태입니다.'}
        </div>
        <button type="button" className="secondary-button" style={{ marginTop: 10 }}
          onClick={() => setRevision((value) => value + 1)}>
          다시 확인
        </button>
      </div>
    );
  }

  if (instances === null) {
    return <div style={{ color: 'var(--surface-text-muted)', fontSize: 14 }}>
      이 조직에 적용된 업무키트를 확인하는 중…
    </div>;
  }

  if (instances.length === 0) {
    return (
      <div style={{ padding: 16, borderRadius: 8, border: '1px solid var(--surface-border)',
        background: 'var(--surface-raised)' }}>
        <strong>이 회사·조직에 적용된 업무키트가 없습니다.</strong>
        <p style={{ margin: '7px 0 12px', fontSize: 13, color: 'var(--surface-text-muted)' }}>
          먼저 업무 데이터 준비에서 샘플 패키지를 조직에 적용하고 필요한 데이터 판을 인증하십시오.
        </p>
        <button className="secondary-button" onClick={onOpenDataPrep}>업무 데이터 준비 열기</button>
      </div>
    );
  }

  return (
    <div style={{ display: 'grid', gap: 14 }}>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 7 }}>조직 적용본</div>
        <div style={{ display: 'grid', gap: 8 }}>
          {instances.map((row: any) => {
            const on = selected === row.instance_id;
            return (
              <button key={row.instance_id} type="button" onClick={() => setSelected(row.instance_id)}
                aria-pressed={on} style={{
                  minHeight: 58, padding: '10px 13px', textAlign: 'left', borderRadius: 8,
                  border: `1px solid ${on ? 'var(--ls-navy)' : 'var(--surface-border)'}`,
                  borderLeft: `4px solid ${on ? 'var(--ls-navy)' : 'transparent'}`,
                  background: on ? 'var(--surface-raised)' : 'var(--surface-card)',
                  color: 'var(--surface-text)', cursor: 'pointer',
                }}>
                <strong style={{ display: 'block', fontSize: 14 }}>
                  {row.label || row.kit_id || '이름 없는 적용본'}
                </strong>
                <span style={{ display: 'block', marginTop: 3, fontSize: 12,
                  color: 'var(--surface-text-muted)' }}>
                  {row.entity_mode || '문맥 확인 필요'} · {row.status || '상태 확인 필요'}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {selected ? (
        <div style={{ border: '1px solid var(--surface-border)', borderRadius: 8,
          background: 'var(--surface-card)' }}>
          <KitAppPanel instanceId={selected} />
        </div>
      ) : (
        <div style={{ padding: 13, borderRadius: 8, background: 'var(--surface-raised)',
          color: 'var(--surface-text-muted)', fontSize: 13 }}>
          적용본을 고르면 만들 수 있는 업무 앱, 데이터 준비 상태, 계약 승인 여부가 표시됩니다.
        </div>
      )}
    </div>
  );
}
