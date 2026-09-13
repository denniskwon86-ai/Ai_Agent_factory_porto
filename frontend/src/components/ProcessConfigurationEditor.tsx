import { useState, useSyncExternalStore } from 'react';
import { orderedPlacements, type ProcessEditFlow } from '../lib/processConfigurationEdit';
import { ProcessStructureEditor } from './ProcessStructureEditor';

export function ProcessConfigurationEditor({ flow, busy, onReview }: {
  flow: ProcessEditFlow; busy: boolean; onReview: (id: string) => void;
}) {
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  const [confirmedAt, confirmAt] = useState('');
  const { document, base } = state;
  if (!document || !base?.payload) return null;
  const selected = document.nodes.find((node) => node.process_id === state.selectedId);
  const byId = new Map(document.nodes.map((node) => [node.process_id, node]));
  const commands = flow.getCommands();
  const confirmationKey = JSON.stringify([base.profile_id, base.digest, commands, state.reason]);
  const confirmed = confirmedAt === confirmationKey;
  const setConfirmed = (value: boolean) => confirmAt(value ? confirmationKey : '');
  const locked = busy || state.busy || !!state.attempt || !!state.receipt || !state.access?.permitted_actions.includes('propose');
  const rename = (value: string) => { setConfirmed(false); flow.setLabel(value); };
  const note = (value: string) => { setConfirmed(false); flow.setNote(value); };
  const move = (id: string, direction: -1 | 1) => { setConfirmed(false); flow.move(id, direction); };
  const placementRows = (parent: string) => {
    const rows = orderedPlacements(document, parent);
    return <ol className="process-edit-list">{rows.map((placement, index) => {
      const node = byId.get(placement.process_id);
      return <li key={placement.placement_id}>
        <button type="button" aria-pressed={state.selectedId === placement.process_id}
          onClick={() => flow.select(placement.process_id)}>{node?.label || '이름 입력 필요'}
          {placement.kind === 'SHORTCUT' ? ' · 바로가기' : ''}{placement.hidden ? ' · 숨김' : ''}{node?.enabled === false ? ' · 미사용' : ''}</button>
        <span className="process-edit-order">
          <button type="button" aria-label={`${node?.label} 위로`} disabled={locked || !flow.canReorder(parent) || index === 0}
            onClick={() => move(placement.placement_id, -1)}>↑</button>
          <button type="button" aria-label={`${node?.label} 아래로`} disabled={locked || !flow.canReorder(parent) || index === rows.length - 1}
            onClick={() => move(placement.placement_id, 1)}>↓</button>
        </span>
      </li>;
    })}</ol>;
  };
  const activeRoot = selected?.level === 'L1' ? selected.process_id : selected?.parent_process_id || '';
  return <section className="process-step process-editor" aria-label="업무 이름 설명 순서 편집">
    <h4>우리 업무에 맞게 수정하기</h4>
    <p>업무 선택 → 이름·설명·순서와 구조 수정 → 변경안 제안 → 다른 승인자 검토 순서입니다.</p>
    <p className="process-muted">편집 기준: 승인판 {base.head_version}. 업무 ID·연결된 앱은 유지되며, 제안만으로 적용되지는 않습니다.</p>
    {state.error && <div className="process-error" role="alert">{state.error.message}</div>}
    <div className="process-edit-columns">
      <nav aria-label="수정할 업무 선택"><h5>상위 업무</h5>{placementRows('')}
        {activeRoot && <><h5>{byId.get(activeRoot)?.label}의 하위 업무</h5>{placementRows(activeRoot)}</>}
      </nav>
      <div>{selected && <fieldset disabled={locked}>
        <legend>{selected.level === 'L1' ? '상위' : '하위'} 업무 수정</legend>
        <label className="process-field">업무 이름<input value={selected.label} maxLength={200}
          onChange={(event) => rename(event.target.value)} /></label>
        <label className="process-field">업무 설명<textarea value={selected.note} rows={4}
          placeholder="이 업무에서 무엇을 하는지 짧게 설명해 주세요." onChange={(event) => note(event.target.value)} /></label>
        <p className="process-muted">바로가기의 이름·설명도 같은 원본 업무에 함께 반영됩니다.</p>
      </fieldset>}
      <ProcessStructureEditor flow={flow} locked={locked} />
      {(state.structureInput.label || state.structureInput.note) && <div className="process-safety">
        <p>작성 중인 새 업무는 아직 변경안에 포함되지 않았습니다. 위에서 ‘편집 초안에 업무 추가’를 누르거나 양식을 비워 주세요.</p>
        <button type="button" disabled={locked} onClick={() => flow.setStructureInput({ label: '', note: '', addParent: null, message: '', failed: false })}>새 업무 추가 양식만 비우기</button>
      </div>}
      {document.placements.some((p) => !flow.canReorder(p.parent_process_id)) && <p className="process-safety">새 업무·바로가기가 포함된 목록의 순서 이동은 승인 후 가능합니다. 이름·설명·소속은 지금 수정할 수 있습니다.</p>}
      <div className="process-edit-preview"><h5>제안할 변경 내용 · {commands.length}건</h5>
        {!commands.length ? <p>왼쪽에서 업무를 선택해 수정해 보세요.</p> : <ul>{commands.map((command, index) => {
          if (command.op === 'ADD_NODE') return <li key={index}>{command.node.level === 'L1' ? '상위' : '하위'} 업무 추가: {command.node.label}
            {command.node.parent_process_id ? ` · ${byId.get(command.node.parent_process_id)?.label} 아래` : ''}</li>;
          if (command.op === 'REMOVE_SHORTCUT') {
            const placement = base.payload!.placements.find((p) => p.placement_id === command.placement_id);
            return <li key={index}>바로가기 제거: {byId.get(placement?.process_id || '')?.label || '기존 업무'}
              {' · '}{byId.get(placement?.parent_process_id || '')?.label || '기존 상위 업무'}에서만 제거 (원본 유지)</li>;
          }
          if (command.op === 'REORDER_PLACEMENTS') return <li key={index}>순서: {command.placement_ids.map((id) =>
            byId.get((document.placements.find((p) => p.placement_id === id)
              || base.payload!.placements.find((p) => p.placement_id === id))?.process_id || '')?.label || '기존 배치').join(' → ')}</li>;
          const before = base.payload!.nodes.find((node) => node.process_id === command.process_id);
          const label = byId.get(command.process_id)?.label || before?.label || '추가한 업무';
          if (command.op === 'SET_USAGE') return <li key={index}>{label}: {command.enabled ? '사용' : '미사용'}으로 변경 (원본·이력 유지)</li>;
          if (command.op === 'MOVE_NODE') return <li key={index}>{label}: 상위 업무를 {byId.get(command.parent_process_id)?.label}로 이동</li>;
          if (command.op === 'ADD_SHORTCUT') return <li key={index}>바로가기 추가: {label} → {byId.get(command.parent_process_id)?.label} (원래 소속 유지)</li>;
          return <li key={index}>{command.op === 'RENAME' ? `이름: ${before?.label || '추가한 업무'} → ${command.label}`
            : `설명 (${label}): ${before?.note || '(없음)'} → ${command.note || '(없음)'}`}</li>;
        })}</ul>}
        {commands.some((c) => ['ADD_NODE', 'SET_USAGE', 'MOVE_NODE', 'ADD_SHORTCUT', 'REMOVE_SHORTCUT'].includes(c.op)) && <p className="process-safety">구조 변경이 포함됩니다. 기존 업무 기록·앱 참조는 삭제하지 않으며, 서버가 참조 관계와 승인 권한을 다시 검사합니다. 바로가기는 접근 권한을 추가하지 않습니다.</p>}
      </div>
      <label className="process-field">변경 이유<textarea value={state.reason} maxLength={4000} rows={2} disabled={locked}
        placeholder="예: 현업에서 쓰는 명칭과 검토 순서에 맞췄습니다."
        onChange={(event) => { setConfirmed(false); flow.setReason(event.target.value); }} /></label>
      <label className="process-kit"><input type="checkbox" checked={confirmed} disabled={locked}
        onChange={(event) => setConfirmed(event.target.checked)} />위 변경 내용과 적용 범위를 확인했습니다.</label>
      <div className="process-actions"><button type="button" disabled={busy || state.busy || !!state.receipt || state.conflict || state.rejected
        || !!state.structureInput.label || !!state.structureInput.note
        || (!state.attempt && (!confirmed || !commands.length || !state.reason.trim() || !state.access?.permitted_actions.includes('propose')))}
        onClick={() => void flow.submit().then((receipt) => { if (receipt) onReview(receipt.change_id); })}>
        {state.attempt && !state.receipt ? '같은 요청으로 접수 확인·재시도' : '변경안 제안하기'}</button>
        {!state.attempt && <button type="button" disabled={busy || state.busy} onClick={() => { setConfirmed(false); flow.reset(); }}>수정 내용 취소</button>}
      </div>
      {state.attempt && !state.receipt && !state.conflict && !state.rejected && <p className="process-safety">입력과 요청 번호를 보존했습니다. 새 요청을 만들지 않고 같은 요청의 접수 결과를 확인합니다. 화면을 닫거나 사용자를 바꾸기 전 결과를 확인하세요.</p>}
      {state.rejected && <div className="process-safety"><p>서버가 변경 내용을 거절하여 접수되지 않았습니다. 입력을 고친 뒤 다시 검토·제안할 수 있습니다.</p>
        <button type="button" disabled={busy || state.busy} onClick={() => { setConfirmed(false); flow.revise(); }}>입력을 보존하고 수정 이어하기</button>
      </div>}
      {state.conflict && <div className="process-safety"><p>다른 승인판이 먼저 적용되었습니다. 최신 구성에 입력을 옮겨 미리보기를 다시 확인하세요. 자동 제출하지 않습니다.</p>
        <button type="button" disabled={busy || state.busy} onClick={() => { setConfirmed(false); void flow.reloadBase(); }}>입력을 유지하고 최신판과 다시 비교</button>
        <button type="button" disabled={busy || state.busy} onClick={() => { setConfirmed(false); flow.reset(); }}>기존 수정을 버리고 다시 시작</button>
      </div>}
      {state.receipt && <div className="process-success" role="status"><strong>변경안이 접수되었습니다. 승인·반영은 아직 별도입니다.</strong>
        <p>접수 번호: {state.receipt.change_id}</p>
        <button type="button" disabled={busy || state.busy} onClick={() => onReview(state.receipt!.change_id)}>접수한 변경안 검토·반영 확인</button>
        <button type="button" disabled={busy || state.busy} onClick={() => { setConfirmed(false); void flow.reloadBase(); }}>최신 승인판에서 새 편집 시작</button>
      </div>}
      </div>
    </div>
  </section>;
}
