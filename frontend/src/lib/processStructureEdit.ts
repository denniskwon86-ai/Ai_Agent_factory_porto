import { ProcessApiError, type ProcessCommand, type ProcessDocument } from './processInstallationApi';

// placementId는 화면 미리보기 전용이다. 서버에는 command 필드만 전송한다.
export type ProcessEditStep = { command: ProcessCommand; placementId?: string };
const invalid = (message: string): never => { throw new ProcessApiError(422, message, 'CLIENT_STRUCTURE_INVALID'); };

/** 현재 명령 순서대로 미리보기를 만든다. 권한/참조/승인은 서버가 최종 검증한다. */
export function applyProcessStep(source: ProcessDocument, step: ProcessEditStep): ProcessDocument {
  const document = structuredClone(source), command = step.command;
  const nodeById = (id: string) => document.nodes.find((node) => node.process_id === id);
  const requireParent = (id: string) => {
    if (nodeById(id)?.level !== 'L1') invalid('하위 업무를 둘 상위 업무를 선택해 주세요.');
  };
  const placementId = () => {
    if (!step.placementId || document.placements.some((p) => p.placement_id === step.placementId)) {
      return invalid('새 배치의 미리보기 ID가 중복되었습니다. 기존 입력을 확인해 주세요.');
    }
    return step.placementId;
  };
  if (command.op === 'ADD_NODE') {
    const node = command.node;
    if (!node.process_id || nodeById(node.process_id) || !node.label.trim() || node.label.length > 200) {
      invalid('중복되지 않는 업무와 200자 이내 이름이 필요합니다.');
    }
    if (node.level === 'L2') requireParent(node.parent_process_id);
    else if (node.level !== 'L1' || node.parent_process_id) invalid('상위 업무는 최상위에만 추가할 수 있습니다.');
    document.nodes.push({ ...node, enabled: true });
    document.placements.push({ placement_id: placementId(), process_id: node.process_id,
      parent_process_id: node.parent_process_id, kind: 'CANONICAL', hidden: false, position: document.placements.length });
  } else if (command.op === 'REORDER_PLACEMENTS') {
    const siblings = document.placements.filter((p) => p.parent_process_id === command.parent_process_id);
    if (new Set(command.placement_ids).size !== command.placement_ids.length
      || siblings.length !== command.placement_ids.length || siblings.some((p) => !command.placement_ids.includes(p.placement_id))) {
      invalid('형제 업무의 배치가 변경되었습니다. 순서를 다시 확인해 주세요.');
    }
    for (const placement of siblings) placement.position = command.placement_ids.indexOf(placement.placement_id);
  } else if (command.op === 'REMOVE_SHORTCUT') {
    const placement = document.placements.find((p) => p.placement_id === command.placement_id && p.kind === 'SHORTCUT');
    if (!placement) invalid('삭제할 바로가기가 최신 구성에 없습니다. 기존 입력을 보존했습니다.');
    document.placements = document.placements.filter((p) => p !== placement);
  } else {
    const node = nodeById(command.process_id);
    if (!node) return invalid('수정할 업무가 최신 구성에 없습니다. 기존 입력을 보존했습니다.');
    if (command.op === 'RENAME') {
      if (!command.label.trim() || command.label.length > 200) invalid('업무 이름은 1~200자로 입력해 주세요.');
      node.label = command.label;
    } else if (command.op === 'SET_NOTE') node.note = command.note;
    else if (command.op === 'SET_USAGE') node.enabled = command.enabled;
    else if (command.op === 'MOVE_NODE') {
      if (node.level !== 'L2') invalid('하위 업무만 다른 상위 업무로 이동할 수 있습니다.');
      requireParent(command.parent_process_id);
      if (document.placements.some((p) => p.kind === 'SHORTCUT' && p.process_id === node.process_id
        && p.parent_process_id === command.parent_process_id)) {
        invalid('이동할 상위 업무에 같은 업무의 바로가기가 있습니다. 바로가기를 먼저 제거해 주세요.');
      }
      node.parent_process_id = command.parent_process_id;
      for (const placement of document.placements) {
        if (placement.kind === 'CANONICAL' && placement.process_id === node.process_id) placement.parent_process_id = command.parent_process_id;
      }
    } else {
      if (node.level !== 'L2') invalid('바로가기는 하위 업무에만 만들 수 있습니다.');
      requireParent(command.parent_process_id);
      if (node.parent_process_id === command.parent_process_id || document.placements.some((p) =>
        p.process_id === node.process_id && p.parent_process_id === command.parent_process_id)) {
        invalid('원래 소속 또는 이미 바로가기가 있는 상위 업무에는 중복 추가하지 않습니다.');
      }
      document.placements.push({ placement_id: placementId(), process_id: node.process_id,
        parent_process_id: command.parent_process_id, kind: 'SHORTCUT', hidden: false, position: document.placements.length });
    }
  }
  return document;
}

export function replayProcessSteps(base: ProcessDocument, steps: ProcessEditStep[]): ProcessDocument {
  return steps.reduce((document, step) => applyProcessStep(document, step), structuredClone(base));
}
