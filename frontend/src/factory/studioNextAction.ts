import type { FactoryStudioViewModel } from './factoryViewModel';

export type StudioNextAction = {
  kind: 'refresh' | 'decision' | 'quota' | 'running' | 'heal' | 'task' | 'result' | 'planning' | 'blocked';
  title: string; description: string; label: string; taskId?: string;
};

// 표시용 안내다. 서버 권한이나 실행 가능 계약을 이 결과로 대신하지 않는다.
export function studioNextAction(vm: FactoryStudioViewModel): StudioNextAction {
  if (!vm.project.id || vm.loadState === 'forbidden') return {
    kind: 'blocked', title: '작업을 열 수 있는지 확인해 주세요',
    description: vm.loadReason || '프로젝트를 선택해야 합니다.', label: '현재 상태 확인',
  };
  if (['error', 'loading'].includes(vm.loadState) || vm.connection !== 'connected') return {
    kind: 'refresh', title: '현재 상태를 먼저 확인해 주세요',
    description: vm.loadReason || '연결이 확인되기 전에는 제작·승인을 요청하지 않습니다.', label: '상태 다시 확인',
  };
  if (vm.decisions.length) return {
    kind: 'decision', title: '확인이 필요한 내용이 있습니다',
    description: '아래 검토 영역에서 질문·계약·지원 기능을 구분해 확인하세요.', label: '검토할 내용 보기',
  };
  if (vm.inspect.suspendedTaskId) return {
    kind: 'quota', title: '사용 한도로 제작이 멈췄습니다',
    description: '한도 회복 후 저장된 지점에서 재개를 요청할 수 있습니다.', label: '한도 회복 후 재개',
  };
  if (vm.run.active) return {
    kind: 'running', title: '제작 진행 중입니다',
    description: '현재 작업과 결과를 확인할 수 있습니다. 화면을 닫아도 제작은 중단되지 않습니다.', label: '진행 결과 보기',
  };
  if (vm.inspect.failure) return {
    kind: 'heal', title: '마지막 작업에서 오류가 발생했습니다',
    description: vm.inspect.failure.error, label: '오류와 복구 방법 확인',
  };
  const selected = vm.wbs.find(t => t.id === vm.selectedWbsId);
  const next = selected || vm.wbs.find(t => t.kind === 'waiting');
  if (next && next.kind === 'waiting') return {
    kind: 'task', title: `다음 작업: ${next.title || next.id}`,
    description: '작업 내용을 확인한 뒤 이 작업의 제작을 시작하세요.', label: '선택 작업 시작', taskId: next.id,
  };
  if (vm.generated.runnable || Object.keys(vm.docs).length) return {
    kind: 'result', title: '만들어진 결과를 확인해 주세요',
    description: '검토용 버전 저장은 배포나 운영 승인과 다릅니다.', label: '결과 확인하기',
  };
  if (vm.wbs.length) return {
    kind: 'blocked', title: '작업의 선행 조건을 확인해 주세요',
    description: '작업 목록에서 차단 이유를 확인하세요. 조회만으로 실행하지 않습니다.', label: '작업 목록 보기',
  };
  return {
    kind: 'planning', title: '어떤 일을 쉽게 만들고 싶으세요?',
    description: '요구사항을 정리하고, 사람의 확인이 필요한 곳에서 멈춰 질문합니다.', label: '요구사항 정리 시작',
  };
}
