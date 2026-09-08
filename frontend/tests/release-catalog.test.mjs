import assert from 'node:assert/strict';
import test from 'node:test';
import { catalogReleases, releaseLifecycleView } from '../src/lib/releaseCatalog.ts';

const rows = [
  { release_id: 'one', project_name: 'Same app', lifecycle_status: 'active' },
  { release_id: 'two', project_name: 'Same app', lifecycle_status: 'candidate' },
  { release_id: 'three', project_name: 'Stopped app', lifecycle_status: 'disabled' },
];

test('default list excludes disabled releases but preserves valid revisions', () => {
  const before = structuredClone(rows);
  assert.deepEqual(catalogReleases(rows).map(row => row.release_id), ['one', 'two']);
  assert.deepEqual(rows, before);
});

test('archive opt-in and search are both honored', () => {
  assert.equal(catalogReleases(rows, true).length, 3);
  assert.equal(catalogReleases(rows, false, 'Stopped').length, 0);
  assert.equal(catalogReleases(rows, true, ' stopped ').length, 1);
  assert.equal(catalogReleases(rows, false, 'TWO')[0].release_id, 'two');
});

test('disabled state always prevents running, including enterprise and kit entries', () => {
  const view = releaseLifecycleView({ lifecycle_status: 'disabled', is_enterprise: true }, { lifecycle_state: 'active' });
  assert.equal(view.executable, false);
  assert.match(view.label, /보관/);
});

test('an unknown lifecycle cannot be rescued by a kit candidate label', () => {
  assert.equal(releaseLifecycleView({ lifecycle_status: 'broken' }, { lifecycle_state: 'candidate' }).executable, false);
});

test('generic candidates are not described as operational', () => {
  const view = releaseLifecycleView({ lifecycle_status: 'candidate', lifecycle_recorded: true });
  assert.equal(view.label, '운영 후보');
  assert.match(view.detail, /미리보기/);
});

test('active kit apps remain usable without compiled frontend code in metadata', () => {
  const view = releaseLifecycleView({ lifecycle_status: 'active', frontend_code_summary: '' }, { lifecycle_state: 'active' });
  assert.equal(view.executable, true);
  assert.equal(view.label, '운영 중');
});

test('existing unrecorded releases are distinguished without silently disabling them', () => {
  const view = releaseLifecycleView({});
  assert.equal(view.label, '사용 상태 미기록');
  assert.equal(view.executable, true);
});
