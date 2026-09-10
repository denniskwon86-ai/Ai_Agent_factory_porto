import type { AppDatasetRow, AppRecords } from './kitAppViewApi';

export const KIT_APP_PAGE_SIZE = 20;

export interface KitAppPageState {
  datasets: AppDatasetRow[] | null;
  picked: string;
  offset: number;
  rows: AppRecords | null;
  busy: boolean;
  error: string;
}

export function emptyKitAppPage(): KitAppPageState {
  return { datasets: null, picked: '', offset: 0, rows: null, busy: false, error: '' };
}

export function kitAppPageInfo(state: KitAppPageState) {
  const count = state.rows?.records.length || 0;
  const total = state.rows?.total || 0;
  return {
    start: count ? state.offset + 1 : 0,
    end: count ? state.offset + count : 0,
    total,
    page: Math.floor(state.offset / KIT_APP_PAGE_SIZE) + 1,
    pages: Math.max(1, Math.ceil(total / KIT_APP_PAGE_SIZE)),
    hasPrevious: !state.busy && Boolean(state.rows) && state.offset > 0,
    hasNext: !state.busy && count > 0 && state.offset + KIT_APP_PAGE_SIZE < total,
  };
}

/** 실제 조회에 사용하는 상태 관리. 증명은 메모리에만 두고 이전 요청은 화면에 반영하지 않는다. */
export function createKitAppPager(deps: {
  listDatasets: () => Promise<AppDatasetRow[]>;
  issueProof: () => Promise<string>;
  readRecords: (proof: string, name: string, limit: number, offset: number) => Promise<AppRecords>;
  chooseDataset: (datasets: AppDatasetRow[]) => string;
  onChange: (state: KitAppPageState) => void;
}) {
  let state = emptyKitAppPage();
  let generation = 0;
  let proof = '';

  function publish(patch: Partial<KitAppPageState>) {
    state = { ...state, ...patch };
    deps.onChange(state);
  }

  function invalidate() {
    generation++;
    proof = '';
  }

  function reset() {
    invalidate();
    publish(emptyKitAppPage());
  }

  function fail(request: number, error: unknown) {
    if (request !== generation) return;
    publish({ rows: null, busy: false,
      error: error instanceof Error ? error.message : '업무 자료를 읽지 못했습니다.' });
  }

  async function readPage(request: number, name: string, offset: number) {
    let result = await deps.readRecords(proof, name, KIT_APP_PAGE_SIZE, offset);
    if (request !== generation) return;
    // 조회 사이에 자료가 줄어 마지막 페이지가 사라졌다면 현재 마지막 페이지를 다시 읽는다.
    if (offset > 0 && result.records.length === 0 && offset >= result.total) {
      offset = Math.max(0, Math.ceil(result.total / KIT_APP_PAGE_SIZE) - 1) * KIT_APP_PAGE_SIZE;
      result = await deps.readRecords(proof, name, KIT_APP_PAGE_SIZE, offset);
      if (request !== generation) return;
    }
    publish({ picked: name, offset, rows: result, busy: false, error: '' });
  }

  async function load() {
    reset();
    const request = generation;
    publish({ busy: true });
    try {
      const datasets = await deps.listDatasets();
      if (request !== generation) return;
      publish({ datasets });
      if (!datasets.length) {
        publish({ busy: false });
        return;
      }
      const issued = await deps.issueProof();
      if (request !== generation) return;
      proof = issued;
      const first = deps.chooseDataset(datasets);
      publish({ picked: first });
      await readPage(request, first, 0);
    } catch (error) { fail(request, error); }
  }

  async function select(name: string, offset = 0) {
    if (!proof || !state.datasets?.some((dataset) => dataset.name === name)) return;
    // 다른 자료를 선택할 때는 이전 자료의 페이지 번호를 가져가지 않는다.
    const nextOffset = name === state.picked
      ? Math.max(0, Math.floor(offset / KIT_APP_PAGE_SIZE)) * KIT_APP_PAGE_SIZE : 0;
    const request = ++generation;
    publish({ picked: name, offset: nextOffset, rows: null, error: '', busy: true });
    try { await readPage(request, name, nextOffset); }
    catch (error) { fail(request, error); }
  }

  async function move(direction: -1 | 1) {
    const info = kitAppPageInfo(state);
    if (direction === -1 ? !info.hasPrevious : !info.hasNext) return;
    await select(state.picked, state.offset + direction * KIT_APP_PAGE_SIZE);
  }

  async function retry() {
    if (proof && state.picked) await select(state.picked, state.offset);
    else await load();
  }

  return { load, select, move, retry, reset, invalidate };
}
