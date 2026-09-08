import assert from 'node:assert/strict';
import test from 'node:test';
import { createRollbackRunner } from '../src/lib/releaseRollback.ts';

const done = { release_id: 'app', outcome: 'complete', program_disabled: true,
  history_recorded: true, message: '사용 중단 완료', limitation: '원본 보관' };

test('feedback survives the refresh that clears screen messages', async () => {
  const run = createRollbackRunner(), busy = [];
  let screen = { message: 'old' };
  const result = await run({ perform: async () => done,
    refresh: async () => { screen = { message: '', result: null }; }, onBusy: b => busy.push(b) });
  screen = { ...screen, ...result };
  assert.equal(screen.result, done);
  assert.equal(screen.message, '사용 중단 완료');
  assert.deepEqual(busy, [true, false]);
});

test('partial server failure retains real disable status and refreshes', async () => {
  const partial = { ...done, outcome: 'partial', message: '승격 철회 재시도 필요' };
  const error = Object.assign(new Error(partial.message), { status: 503, rollback: partial });
  let refreshed = false;
  const out = await createRollbackRunner()({ perform: async () => { throw error; },
    refresh: async () => { refreshed = true; }, onBusy: () => {} });
  assert.equal(out.result, partial);
  assert.equal(out.message, '');
  assert.equal(out.error, partial.message);
  assert.equal(refreshed, true);
});

test('an incomplete 200 response is not displayed as success', async () => {
  const out = await createRollbackRunner()({ perform: async () => ({ ...done, program_disabled: false }),
    refresh: async () => {}, onBusy: () => {} });
  assert.equal(out.message, '');
  assert.ok(out.error);
});

test('refresh failure does not lose a completed rollback', async () => {
  const out = await createRollbackRunner()({ perform: async () => done,
    refresh: async () => { throw new Error('offline'); }, onBusy: () => {} });
  assert.equal(out.result, done);
  assert.equal(out.message, done.message);
  assert.match(out.error, /목록 갱신/);
});

test('rapid confirmation only submits once and a later attempt is possible', async () => {
  const run = createRollbackRunner();
  let finish, calls = 0;
  const options = { perform: () => { calls++; return new Promise(resolve => { finish = resolve; }); },
    refresh: async () => {}, onBusy: () => {} };
  const first = run(options);
  assert.equal(await run(options), null);
  assert.equal(calls, 1);
  finish(done);
  assert.equal((await first).result, done);
  assert.equal((await run({ ...options, perform: async () => done })).result, done);
});

test('network failure refreshes state but never claims nothing changed', async () => {
  let refreshes = 0;
  const out = await createRollbackRunner()({ perform: async () => { throw new Error('offline'); },
    refresh: async () => { refreshes++; }, onBusy: () => {} });
  assert.equal(refreshes, 1);
  assert.equal(out.message, '');
  assert.equal(out.result, null);
  assert.equal(out.error, 'offline');
});
