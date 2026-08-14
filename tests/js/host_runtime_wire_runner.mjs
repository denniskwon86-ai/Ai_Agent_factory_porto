/**
 * [I-3] 프론트 계약 사본을 **실제로 실행해서** 결과를 내놓는다.
 *
 * `tests/test_host_runtime_wire_parity.py` 가 같은 입력을 파이썬 정본에 넣고 결과를 대조한다.
 * 소스 검사는 「그 줄이 있는가」만 보지만 이것은 **무엇을 답하는가**를 본다.
 *
 * 사용: node host_runtime_wire_runner.mjs <wire.ts 절대경로> <cases.json 경로>
 */
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const wire = await import(pathToFileURL(process.argv[2]).href);
const cases = JSON.parse(readFileSync(process.argv[3], 'utf8'));

const out = {
  cursors: cases.cursors.map((c) => wire.decodeCursor(c)),
  pages: cases.pages.map((p) => {
    const r = wire.normalizePage(p);
    return [r.limit, r.offset];
  }),
  requests: cases.requests.map((c) => {
    const v = wire.validateRequest(c.msg, c.sid, new Set(c.inflight || []));
    return [v.verdict, v.code];
  }),
  datasets: cases.rows.map((r) => wire.projectDataset(r)),
  records: cases.rows.map((r) => wire.projectRecord(r)),
  //: ★ 「다음에 무엇을 할까」 판단도 **실제로 돌린다.** 이 판단이 틀렸을 때 낡은 앱이
  //:   새 증명으로 계속 돌았다 — 소스 검사로는 못 잡던 칸이다(교차검토 84).
  steps: cases.steps.map((c) => wire.nextStep(c)),
  statuses: cases.statuses.map((n) => wire.errorCodeForStatus(n)),
  responses: cases.responses.map(
    (r) => wire.buildResponse(r.sid, r.request_id, r.ok, r.data, r.error_code || ''),
  ),
};
process.stdout.write(JSON.stringify(out));
