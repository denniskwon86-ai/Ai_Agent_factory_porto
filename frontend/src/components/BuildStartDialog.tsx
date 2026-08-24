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
import { useState } from 'react';

import { HubDialog } from '../design/HubDialog';

export type BuildStartResult = {
  projectId: string;
  isMega: boolean;
  templateId: string;
  packIds: string[];
  masterDomains: string;
  mcpLiveGrounding: boolean;
};

export function BuildStartDialog({
  templates, knowledgePacks, packsBlocked, onClose, onCreate,
}: {
  templates: { template_id: string; name?: string; pipeline_name?: string }[];
  knowledgePacks: any[];
  packsBlocked: string;
  onClose: () => void;
  onCreate: (r: BuildStartResult) => void;
}) {
  const [projectId, setProjectId] = useState('');
  const [isMega, setIsMega] = useState(false);
  const [templateId, setTemplateId] = useState(templates[0]?.template_id || 'default');
  const [packIds, setPackIds] = useState<string[]>([]);
  const [masterDomains, setMasterDomains] = useState('');
  const [mcp, setMcp] = useState(false);
  const [err, setErr] = useState('');

  const idOk = /^[A-Za-z0-9._-]{2,}$/.test(projectId.trim());

  const submit = () => {
    if (!idOk) {
      setErr('Project ID 는 영문·숫자·`.`·`_`·`-` 로 2자 이상이어야 합니다.');
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
        {err && (
          <div style={{ fontSize: 13, padding: '10px 14px', borderRadius: 8,
            color: 'var(--state-error-fg)', background: 'var(--state-error-bg)' }}>{err}</div>
        )}

        <div>
          <span style={label}>Project ID (영문)</span>
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
                  선택한 워크플로우를 따라 단일 목표를 수행합니다 · 추천
                </span>
              </span>
            </button>
            <button style={option(isMega)} onClick={() => setIsMega(true)}>
              <span style={{ fontSize: 20 }}>🌟</span>
              <span>
                <b style={{ fontSize: 14, color: 'var(--surface-text)' }}>메가 프로젝트</b>
                <span style={{ display: 'block', fontSize: 12,
                  color: 'var(--surface-text-muted)' }}>
                  여러 프로젝트를 묶어 상위 목표로 운영합니다
                </span>
              </span>
            </button>
          </div>
        </div>

        <div>
          <span style={label}>워크플로우 템플릿</span>
          <select style={input} value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}>
            {(templates || []).map((t) => (
              <option key={t.template_id} value={t.template_id}>
                {t.pipeline_name || t.name || t.template_id}
              </option>
            ))}
          </select>
          <p style={{ fontSize: 12, marginTop: 6, color: 'var(--surface-text-muted)' }}>
            어떤 에이전트가 어떤 순서로 일하고 어디서 사람이 확인하는지가 여기서 정해집니다.
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
          <span style={label}>기준정보 도메인 (선택)</span>
          <input style={input} value={masterDomains}
            onChange={(e) => setMasterDomains(e.target.value)}
            placeholder="콤마 구분 · 예: manufacturing, logistics" />
          <p style={{ fontSize: 12, marginTop: 6, color: 'var(--surface-text-muted)' }}>
            해당 도메인의 골든 레코드가 모든 산출물에 확정 주입됩니다.
          </p>
        </div>

        <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', cursor: 'pointer' }}>
          <input type="checkbox" checked={mcp} onChange={(e) => setMcp(e.target.checked)}
            style={{ marginTop: 3 }} />
          <span>
            <b style={{ fontSize: 14, color: 'var(--surface-text)' }}>외부 실측값(MCP) 병기</b>
            <span style={{ display: 'block', fontSize: 12, color: 'var(--surface-text-muted)' }}>
              활성 연계 시스템의 실측값을 산출물에 참고로 붙입니다 — 지연·쿼터가 늘어납니다.
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
            <li>유형 — {isMega ? '메가 프로젝트' : '독립 프로젝트'}</li>
            <li>워크플로우 — {templates.find((t) => t.template_id === templateId)?.pipeline_name
              || templateId}</li>
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
          alignItems: 'center', flexWrap: 'wrap' }}>
          {!idOk && (
            <span style={{ fontSize: 12.5, color: 'var(--surface-text-muted)',
              marginRight: 'auto' }}>
              {!projectId.trim()
                ? '맨 위 Project ID 를 입력하면 «이 조건으로 만들기» 가 켜집니다.'
                : 'Project ID 는 영문·숫자·`.`·`_`·`-` 로 2자 이상이어야 합니다 — '
                  + '지금 값으로는 만들 수 없습니다.'}
            </span>
          )}
          <button onClick={onClose} style={{
            height: 44, padding: '0 18px', fontSize: 14, borderRadius: 6, cursor: 'pointer',
            border: '1px solid var(--action-secondary-border)',
            background: 'var(--action-secondary-bg)', color: 'var(--action-secondary-fg)',
          }}>취소</button>
          <button onClick={submit} disabled={!idOk}
            title={idOk ? '' : 'Project ID 를 입력해야 만들 수 있습니다.'} style={{
            height: 46, padding: '0 22px', fontSize: 14, fontWeight: 700, borderRadius: 6,
            cursor: idOk ? 'pointer' : 'not-allowed', opacity: idOk ? 1 : .55,
            border: '1px solid var(--ls-navy)',
            background: 'var(--action-primary-bg)', color: 'var(--action-primary-fg)',
          }}>이 조건으로 만들기</button>
        </div>
      </div>
    </HubDialog>
  );
}
