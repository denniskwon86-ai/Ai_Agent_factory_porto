// Real React server render of the new guide. This is not a browser/layout test.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const file = new URL('../src/components/KitGettingStarted.tsx', import.meta.url);
const source = fs.readFileSync(file, 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
} }).outputText;
const module = { exports: {} };
new Function('module', 'exports', 'require', compiled)(module, module.exports, createRequire(file));
const { KitGettingStarted } = module.exports;
const base = { kitId: 'KIT-MFG-NONFERROUS-PROCUREMENT', version: '1.0.0', groupId: 'BK-01' };
const render = (props) => renderToStaticMarkup(React.createElement(KitGettingStarted, props));
for (const groupId of ['FOUNDATION', 'BK-01', 'BK-02', 'BK-03', 'BK-04', 'BK-05', 'BK-06', 'BK-07', 'BK-08']) {
  const html = render({ ...base, groupId, canPrepare: true });
  for (const label of ['준비할 자료', '함께 대조할 것', '결과를 활용하는 방법', '사용 범위', '자료 준비']) assert.ok(html.includes(label));
  assert.ok(!html.includes(groupId)); // human labels, not technical IDs
}
assert.equal(render({ ...base, kitId: 'ANOTHER-PACKAGE' }), '');
assert.equal(render({ ...base, version: '2.0.0' }), '');
assert.equal(render({ ...base, groupId: 'NEW' }), '');
assert.ok(!render(base).includes('‘자료 준비’')); // no instruction to use an absent control
assert.ok(render({ ...base, groupId: 'BK-02' }).includes('조회 중심'));
assert.ok(render({ ...base, groupId: 'BK-07' }).includes('전체 손익·현금흐름 모델의 대체물이 아닙니다'));
process.stdout.write('KitGettingStarted: 15 render cases passed (not browser verification)\n');

const inputFile = new URL('../src/lib/kitInputValidation.ts', import.meta.url);
const validation = { exports: {} };
const inputCode = ts.transpileModule(fs.readFileSync(inputFile, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
new Function('module', 'exports', inputCode)(validation, validation.exports);
const { sourceRowCount } = validation.exports;
for (const value of ['', ' ', '0', '-1', '1.5', 'NaN', 'Infinity', '9007199254740992', '1e3']) {
  assert.equal(sourceRowCount(value), null);
}
assert.equal(sourceRowCount('120'), 120);
assert.equal(sourceRowCount(' 42 '), 42);
process.stdout.write('Independent source total: 11 cases passed\n');
