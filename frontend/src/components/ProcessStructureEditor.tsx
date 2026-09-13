import { useSyncExternalStore } from 'react';
import type { ProcessEditFlow } from '../lib/processConfigurationEdit';

type ProcessStructureInput = ReturnType<ProcessEditFlow['getSnapshot']>['structureInput'];
type ParentChoice = ProcessStructureInput['addParent'];

/** 구조 변경도 flow의 편집 초안에만 담는다. 문서 원문·서버 참조는 수정하지 않는다. */
export function ProcessStructureEditor({ flow, locked }: { flow: ProcessEditFlow; locked: boolean }) {
  const state = useSyncExternalStore(flow.subscribe, flow.getSnapshot, flow.getSnapshot);
  // 아직 추가하지 않은 입력도 flow에 보관한다. 화면 재마운트·범위 왕복으로 초기화하지 않는다.
  const form = state.structureInput;
  const document = state.document;
  if (!document) return null;

  const selected = document.nodes.find((node) => node.process_id === state.selectedId);
  const parents = document.nodes.filter((node) => node.level === 'L1');
  const defaultParent = selected?.level === 'L1' ? selected.process_id : selected?.parent_process_id || '';
  const choice = (value: ParentChoice, fallback = '') =>
    value?.selectedId === state.selectedId ? value.parentId : fallback;
  const addParent = form.level === 'L1' ? '' : choice(form.addParent, defaultParent);
  const moveParent = choice(form.moveParent);
  const shortcutParent = choice(form.shortcutParent);
  const isParent = (id: string) => parents.some((parent) => parent.process_id === id);
  const placedUnder = (processId: string, parentId: string) => document.placements.some(
    (placement) => placement.process_id === processId && placement.parent_process_id === parentId);
  const parentLabel = (id: string) => parents.find((parent) => parent.process_id === id)?.label || '상위 업무 확인 필요';
  const label = form.label.trim();
  const duplicateName = !!label && document.nodes.some((node) => node.level === form.level
    && node.parent_process_id === addParent && node.label.trim() === label);
  const canAdd = !locked && !!label && form.label.length <= 200 && !duplicateName
    && (form.level === 'L1' || isParent(addParent));
  const destinationAllowed = (parentId: string) => !!selected && selected.level === 'L2'
    && isParent(parentId) && parentId !== selected.parent_process_id
    && !placedUnder(selected.process_id, parentId);
  const shortcuts = selected?.level === 'L2' ? document.placements.filter(
    (placement) => placement.kind === 'SHORTCUT' && placement.process_id === selected.process_id) : [];
  const availableParents = parents.filter((parent) => destinationAllowed(parent.process_id));

  function update(patch: Partial<ProcessStructureInput>) {
    if (!locked) flow.setStructureInput({ ...patch, message: '', failed: false });
  }
  function ready() {
    if (locked) return false;
    const current = flow.getSnapshot();
    if (current.document !== document || current.selectedId !== state.selectedId || current.base !== state.base) {
      flow.setStructureInput({ message: '선택하거나 수정한 업무가 바뀌었습니다. 현재 내용을 다시 확인해 주세요.', failed: true });
      return false;
    }
    return true;
  }
  function apply(work: () => void, message: string, patch: Partial<ProcessStructureInput> = {}) {
    if (!ready()) return;
    try {
      work();
      const changed = flow.getSnapshot().document !== document;
      flow.setStructureInput({ ...(changed ? patch : {}), failed: !changed,
        message: changed ? message : '변경하지 못했습니다. 현재 편집 권한과 선택 내용을 확인해 주세요.' });
    } catch (error) {
      flow.setStructureInput({ failed: true,
        message: error instanceof Error ? error.message : '변경하지 못했습니다. 입력을 보존했습니다.' });
    }
  }
  function add() {
    if (!canAdd || !ready()) return;
    try {
      const id = flow.addNode(form.level, addParent, label, form.note);
      if (id) {
        flow.setStructureInput({ label: '', note: '', addParent: null, message: '업무를 편집 초안에 추가했습니다. 변경안을 제안해야 승인 검토가 시작됩니다.', failed: false });
      } else {
        flow.setStructureInput({ message: '업무를 추가하지 못했습니다. 입력과 선택한 상위 업무를 확인해 주세요.', failed: true });
      }
    } catch (error) {
      flow.setStructureInput({ failed: true,
        message: error instanceof Error ? error.message : '업무를 추가하지 못했습니다. 입력을 보존했습니다.' });
    }
  }

  return <details className="process-install-more process-editor">
    <summary aria-disabled={locked} tabIndex={locked ? -1 : 0}
      onClick={(event) => { if (locked) event.preventDefault(); }}
      onKeyDown={(event) => { if (locked && (event.key === 'Enter' || event.key === ' ')) event.preventDefault(); }}>
      추가 설정 · 업무 추가, 사용 여부, 이동과 바로가기
    </summary>
    <p className="process-muted">아래 변경은 편집 초안에만 담깁니다. 변경안을 제안하고 다른 승인자가 검토한 뒤 적용됩니다.</p>
    {locked && <p className="process-safety">지금은 편집할 수 없습니다. 접수·승인 상태와 현재 권한을 확인해 주세요.</p>}
    <fieldset disabled={locked}>
      <legend>새 업무 추가</legend>
      <label className="process-field">업무 구분
        <select value={form.level} disabled={locked}
          onChange={(event) => update({ level: event.target.value === 'L1' ? 'L1' : 'L2', addParent: null })}>
          <option value="L2">하위 업무 (L2) — 예: 구매계획</option>
          <option value="L1">상위 업무 (L1) — 예: 원료구매</option>
        </select>
      </label>
      {form.level === 'L2' && <label className="process-field">어느 상위 업무에 추가할까요?
        <select value={isParent(addParent) ? addParent : ''} disabled={locked || !parents.length}
          onChange={(event) => update({ addParent: { selectedId: state.selectedId, parentId: event.target.value } })}>
          <option value="">상위 업무를 선택해 주세요</option>
          {parents.map((parent) => <option key={parent.process_id} value={parent.process_id}>
            {parent.label || '이름 입력 필요'}{parent.enabled ? '' : ' · 미사용'}
          </option>)}
        </select>
      </label>}
      {form.level === 'L2' && !parents.length && <p className="process-muted">상위 업무가 없습니다. 업무 구분을 ‘상위 업무’로 바꾸어 먼저 추가해 주세요.</p>}
      <label className="process-field">새 업무 이름 (최대 200자)
        <input value={form.label} maxLength={200} disabled={locked} placeholder="현업에서 사용하는 이름을 적어 주세요"
          onChange={(event) => update({ label: event.target.value })} />
      </label>
      <label className="process-field">설명 (선택)
        <textarea value={form.note} rows={3} disabled={locked} placeholder="이 업무에서 하는 일을 짧게 적어 주세요"
          onChange={(event) => update({ note: event.target.value })} />
      </label>
      {duplicateName && <p className="process-error" role="status">같은 위치에 같은 이름의 업무가 있습니다. 기존 업무를 선택하거나 이름을 구분해 주세요.</p>}
      <div className="process-actions"><button type="button" disabled={!canAdd} onClick={add}>편집 초안에 업무 추가</button></div>
    </fieldset>

    {selected ? <>
      <fieldset disabled={locked}>
        <legend>선택한 업무 · {selected.label || '이름 입력 필요'}</legend>
        <label className="process-kit"><input type="checkbox" checked={selected.enabled} disabled={locked}
          onChange={(event) => {
            const enabled = event.target.checked;
            if (enabled !== selected.enabled) apply(() => flow.setUsage(enabled),
              enabled ? '사용하도록 초안을 변경했습니다.' : '미사용으로 초안을 변경했습니다. 업무와 연결 정보는 삭제하지 않았습니다.');
          }} />이 업무 사용</label>
        <p className="process-muted">미사용은 삭제가 아닙니다. 업무 ID·연결된 앱·바로가기는 유지하며, 필요할 때 다시 사용할 수 있습니다.</p>
      </fieldset>
      {selected.level === 'L2' && <>
        <fieldset disabled={locked}>
          <legend>소속 상위 업무 변경</legend>
          <p className="process-muted">현재 소속: {parentLabel(selected.parent_process_id)}. 같은 업무를 다른 상위 업무로 옮깁니다.</p>
          <label className="process-field">옮길 상위 업무
            <select value={isParent(moveParent) ? moveParent : ''} disabled={locked || !availableParents.length}
              onChange={(event) => update({ moveParent: { selectedId: state.selectedId, parentId: event.target.value } })}>
              <option value="">옮길 곳을 선택해 주세요</option>
              {parents.map((parent) => <option key={parent.process_id} value={parent.process_id}
                disabled={!destinationAllowed(parent.process_id)}>
                {parent.label || '이름 입력 필요'}{parent.process_id === selected.parent_process_id ? ' · 현재 소속'
                  : placedUnder(selected.process_id, parent.process_id) ? ' · 이미 바로가기 있음' : parent.enabled ? '' : ' · 미사용'}
              </option>)}
            </select>
          </label>
          <p className="process-muted">현재 소속과 같은 곳은 선택할 수 없습니다. 옮길 곳에 바로가기가 있으면 아래에서 그 바로가기를 먼저 제거해 주세요.</p>
          <button type="button" disabled={locked || !destinationAllowed(moveParent)}
            onClick={() => { if (destinationAllowed(moveParent)) apply(() => flow.moveNode(moveParent), '소속 변경을 초안에 담았습니다.', { moveParent: null }); }}>
            선택한 상위 업무로 이동
          </button>
        </fieldset>
        <fieldset disabled={locked}>
          <legend>다른 상위 업무에서도 찾기 · 바로가기</legend>
          <p className="process-muted">바로가기는 같은 업무를 다른 곳에서도 보여 줍니다. 업무를 복제하거나 원래 소속을 바꾸지 않습니다.</p>
          <label className="process-field">바로가기를 둘 상위 업무
            <select value={isParent(shortcutParent) ? shortcutParent : ''} disabled={locked || !availableParents.length}
              onChange={(event) => update({ shortcutParent: { selectedId: state.selectedId, parentId: event.target.value } })}>
              <option value="">바로가기를 둘 곳을 선택해 주세요</option>
              {parents.map((parent) => <option key={parent.process_id} value={parent.process_id}
                disabled={!destinationAllowed(parent.process_id)}>
                {parent.label || '이름 입력 필요'}{parent.process_id === selected.parent_process_id ? ' · 원래 소속'
                  : placedUnder(selected.process_id, parent.process_id) ? ' · 이미 배치됨' : parent.enabled ? '' : ' · 미사용'}
              </option>)}
            </select>
          </label>
          {!availableParents.length && <p className="process-muted">추가할 수 있는 다른 상위 업무가 없습니다.</p>}
          <button type="button" disabled={locked || !destinationAllowed(shortcutParent)}
            onClick={() => { if (destinationAllowed(shortcutParent)) apply(() => flow.addShortcut(selected.process_id, shortcutParent),
              '바로가기 추가를 초안에 담았습니다.', { shortcutParent: null }); }}>바로가기 추가</button>
          {shortcuts.length > 0 ? <ul className="process-operation-list">
            {shortcuts.map((placement) => <li key={placement.placement_id}>
              <span>{parentLabel(placement.parent_process_id)}{placement.hidden ? ' · 숨겨진 바로가기' : ''}</span>
              <button type="button" disabled={locked} aria-label={`${parentLabel(placement.parent_process_id)}의 ${selected.label} 바로가기만 제거`}
                onClick={() => apply(() => flow.removeShortcut(placement.placement_id), '바로가기만 초안에서 제거했습니다. 원본 업무는 유지됩니다.')}>
                바로가기만 제거
              </button>
            </li>)}
          </ul> : <p className="process-muted">아직 바로가기가 없습니다.</p>}
        </fieldset>
      </>}
    </> : <p className="process-muted">기존 업무의 사용 여부·소속·바로가기를 바꾸려면 먼저 업무를 선택해 주세요.</p>}
    {form.message && <p className={form.failed ? 'process-error' : 'process-status'} role={form.failed ? 'alert' : 'status'}>{form.message}</p>}
  </details>;
}
