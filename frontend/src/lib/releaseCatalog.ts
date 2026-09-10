/** 기본 카탈로그는 사용 중단 판을 제외한다. 원본·이력은 관리 화면에 남긴다. */
export function catalogReleases(rows: any[], includeStopped = false, query = '') {
  const key = query.trim().toLowerCase();
  return rows.filter((row) => (includeStopped || row.lifecycle_status !== 'disabled')
    && (!key || String(row.project_name || '').toLowerCase().includes(key)
      || String(row.release_id || '').toLowerCase().includes(key)));
}

export function releaseLifecycleView(row: any, kitApp?: { lifecycle_state?: string }) {
  if (row.lifecycle_status === 'disabled') {
    return { label: '사용 중단 · 보관', tone: 'var(--state-error-fg)',
      detail: row.lifecycle_reason || '코드와 이력은 보존되며 실행은 중단됐습니다.', executable: false };
  }
  if (row.lifecycle_status && !['active', 'deprecated', 'candidate'].includes(row.lifecycle_status)) {
    return { label: '사용 상태 확인 필요', tone: 'var(--state-warn-fg)',
      detail: '사용 상태를 확인하지 못해 실행할 수 없습니다.', executable: false };
  }
  if (row.lifecycle_status === 'deprecated') {
    return { label: '중단 예고', tone: 'var(--state-warn-fg)',
      detail: row.lifecycle_reason || '', executable: true };
  }
  if (row.lifecycle_status === 'candidate' || kitApp?.lifecycle_state === 'candidate') {
    return { label: '운영 후보', tone: 'var(--state-warn-fg)',
      detail: '운영 앱이 아닙니다. 검토용 미리보기만 제공합니다.', executable: true };
  }
  if (kitApp?.lifecycle_state === 'active' || row.is_enterprise) {
    return { label: '운영 중', tone: 'var(--state-success-fg)',
      detail: '인증된 업무 데이터를 읽습니다.', executable: true };
  }
  return { label: row.lifecycle_recorded ? '사용 가능' : '사용 상태 미기록',
    tone: row.lifecycle_recorded ? 'var(--state-success-fg)' : 'var(--surface-text-muted)',
    detail: row.lifecycle_recorded ? '' : '기존 릴리스로, 관리자의 사용 상태 기록이 없습니다.',
    executable: true };
}
