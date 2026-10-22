import test from 'node:test';
import assert from 'node:assert/strict';
import { createTemplateWizardController } from '../src/controllers/template-wizard-controller.ts';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(check) { const start = Date.now(); while (!check()) { if (Date.now() - start > 1500) throw new Error('condition did not settle'); await sleep(1); } }
const HTML = '<html><body>原始母版</body></html>', NEXT = '<html><body>新版母版</body></html>';
const json = (value, status = 200) => Response.json(value, { status });
function setup(t, options = {}, timings = {}) {
  const requests = [], streams = [], snapshots = [], state = { metadata: { template_mode: 'free' }, cached: { success: true, template: { html_template: HTML, template_name: '示例母版' }, status: 'ready' }, handler: null, asks: [], answer: true, navigations: [], cancels: 0 };
  const controller = createTemplateWizardController({ projectId: 'project /中文', topic: '协作', ...options }, {
    fetch: async (url, init = {}) => {
      requests.push({ url, ...init }); const result = await state.handler?.(url, init); if (result) return result;
      if (url.endsWith('/generate')) return new Response(new ReadableStream({ start(writer) { streams.push(writer); }, cancel() { state.cancels++; } }));
      if (init.method === 'POST') return json({ success: true, template: { html_template: NEXT } });
      if (url.endsWith('/free-template')) return json(state.cached);
      if (url.endsWith('/selected-global-template')) return json({ template: { template_name: 'Selected' }, is_user_selected: true });
      return json({ project_metadata: state.metadata });
    },
    ask: async text => { state.asks.push(text); return state.answer; }, navigate: path => state.navigations.push(path),
    timings: { request: 100000, ai: 100000, streamIdle: 100000, ...timings },
  });
  controller.subscribe(next => snapshots.push(next)); t.after(() => controller.dispose());
  const send = (value, index = streams.length - 1, end = false) => { streams[index].enqueue(new TextEncoder().encode('data: ' + JSON.stringify(value) + (end ? '' : '\n\n'))); if (end) streams[index].close(); };
  return { controller, requests, streams, state, snapshots, send };
}
async function open(h) { h.controller.mount(); const signal = new AbortController(); const decision = h.controller.prepare(signal.signal); decision.catch(() => {}); await until(() => h.controller.getSnapshot().open && !h.controller.getSnapshot().busy); return { signal, decision }; }

test('construction/mount is inert; unattended rejects preparation and writes', async t => {
  const h = setup(t, { unattended: true }); h.controller.mount();
  assert.equal(await h.controller.prepare(new AbortController().signal), false);
  await h.controller.generate(); await h.controller.confirm(); assert.equal(h.requests.length, 0);
});
test('package and confirmed free modes bypass the wizard without generation', async t => {
  for (const metadata of [{ generation_mode: 'package' }, { template_mode: 'free', free_template_confirmed: true }]) {
    const h = setup(t); h.state.metadata = metadata; h.controller.mount();
    assert.equal(await h.controller.prepare(new AbortController().signal), true); assert.equal(h.controller.getSnapshot().open, false);
    assert.equal(h.requests.length, 1);
  }
});
test('unconfirmed templates load saved HTML; cancel resolves false without writing', async t => {
  const h = setup(t), { decision } = await open(h);
  assert.equal(h.controller.getSnapshot().draft, HTML); h.controller.cancel();
  assert.equal(await decision, false); assert.ok(h.requests.every(item => item.method === 'GET'));
});
test('concurrent prepare calls share one modal and only explicit confirmation resolves true', async t => {
  const h = setup(t), { decision } = await open(h);
  assert.equal(await h.controller.prepare(new AbortController().signal), false);
  await Promise.all([h.controller.confirm(), h.controller.confirm()]);
  assert.equal(await decision, true); assert.equal(h.requests.filter(item => item.method === 'POST').length, 1);
});
test('confirmation saves current unapplied source, library choice and trimmed name', async t => {
  const h = setup(t), { decision } = await open(h);
  h.controller.editDraft(NEXT); h.controller.setSave(true); h.controller.setName(' 团队模板 ');
  await h.controller.confirm(); assert.equal(await decision, true);
  assert.deepEqual(JSON.parse(h.requests.at(-1).body), { save_to_library: true, template_name: '团队模板', html_template: NEXT });
  assert.match(h.requests.at(-1).url, /project%20%2F%E4%B8%AD%E6%96%87\/free-template\/confirm$/);
});
test('drafts, names and options survive cancel/reopen and readonly checks', async t => {
  const h = setup(t); await open(h); h.controller.editDraft(NEXT); h.controller.setSave(true); h.controller.setName('保留'); h.controller.cancel();
  await open(h); assert.equal(h.controller.getSnapshot().draft, NEXT); assert.equal(h.controller.getSnapshot().name, '保留');
  assert.equal(h.controller.getSnapshot().save, true); assert.ok(h.requests.every(item => item.method === 'GET'));
});
test('empty source cannot confirm and applying code changes only local preview', async t => {
  const h = setup(t); await open(h); h.controller.editDraft(''); await h.controller.confirm();
  assert.equal(h.requests.filter(item => item.method === 'POST').length, 0);
  h.controller.editDraft(NEXT); h.controller.applyDraft(); assert.equal(h.controller.getSnapshot().html, NEXT);
});
test('generation parses split UTF8, CRLF, final event without newline and cancels the reader', async t => {
  const h = setup(t); await open(h); const generation = h.controller.generate(true); await until(() => h.streams.length === 1);
  const bytes = new TextEncoder().encode('data: {"type":"preview","html_template":"中文预览"}\r\n\r\ndata: {"type":"complete","html_template":"完整中文母版"}');
  for (let index = 0; index < bytes.length; index++) h.streams[0].enqueue(bytes.slice(index, index + 1));
  h.streams[0].close(); await generation;
  assert.equal(h.controller.getSnapshot().html, '完整中文母版'); assert.equal(h.controller.getSnapshot().ready, true);
  assert.deepEqual(JSON.parse(h.requests.find(item => item.url.endsWith('/generate')).body), { force: true, stream: true });
});
test('partial preview cannot be confirmed; completion does not wait for EOF', async t => {
  const h = setup(t); await open(h); const generation = h.controller.generate(true); await until(() => h.streams.length === 1);
  h.send({ type: 'preview', html_template: NEXT }); await until(() => h.controller.getSnapshot().html === NEXT);
  assert.equal(h.controller.getSnapshot().ready, false); await h.controller.confirm();
  h.send({ type: 'complete', template: { html_template: NEXT } }); await generation;
  assert.equal(h.state.cancels, 1); assert.equal(h.controller.getSnapshot().ready, true);
  assert.equal(h.requests.filter(item => item.url.endsWith('/confirm')).length, 0);
});
test('fresh missing template generates once after the explicit Start action', async t => {
  const h = setup(t); h.state.cached = { status: 'pending' }; h.controller.mount();
  const decision = h.controller.prepare(new AbortController().signal); await until(() => h.streams.length === 1);
  h.send({ type: 'complete', html_template: NEXT }); await until(() => !h.controller.getSnapshot().busy);
  h.controller.cancel(); assert.equal(await decision, false);
  assert.equal(h.requests.filter(item => item.url.endsWith('/generate')).length, 1);
});
test('EOF or server error never automatically retries a paid generation', async t => {
  for (const event of [null, { type: 'error', message: '额度不足' }]) {
    const h = setup(t); await open(h); const generation = h.controller.generate(); await until(() => h.streams.length === 1);
    if (event) h.send(event); else h.streams[0].close(); await generation;
    assert.ok(h.controller.getSnapshot().error); assert.equal(h.requests.filter(item => item.url.endsWith('/generate')).length, 1);
  }
});
test('known background generation is only read and never duplicated', async t => {
  const h = setup(t); h.state.cached = { status: 'generating' }; await open(h);
  await h.controller.generate(); assert.equal(h.streams.length, 0); assert.equal(h.controller.getSnapshot().ready, false);
  assert.match(h.controller.getSnapshot().notice, /没有重复生成/);
  h.state.cached = { template: { html_template: HTML }, status: 'ready' }; await h.controller.check();
  assert.equal(h.controller.getSnapshot().ready, true);
  h.state.cached.status = 'generating'; await h.controller.check(); await h.controller.confirm();
  assert.equal(h.controller.getSnapshot().ready, false); assert.equal(h.requests.filter(item => item.method === 'POST').length, 0);
});
test('closing during generation releases reader and reopening does not automatically retry', async t => {
  const h = setup(t); await open(h); const generation = h.controller.generate(); await until(() => h.streams.length === 1);
  h.controller.cancel(); await generation; assert.equal(h.state.cancels, 1);
  await open(h); assert.equal(h.requests.filter(item => item.url.endsWith('/generate')).length, 1);
  assert.equal(h.controller.getSnapshot().draft, HTML);
});
test('source replacement requires confirmation; cancelled AI adjustment preserves code and prompt', async t => {
  const h = setup(t); await open(h); h.controller.editDraft(NEXT); h.controller.setAdjustment('改为蓝色'); h.state.answer = false;
  await h.controller.adjust(); assert.equal(h.controller.getSnapshot().draft, NEXT); assert.equal(h.controller.getSnapshot().adjustment, '改为蓝色');
  assert.equal(h.requests.filter(item => item.method === 'POST').length, 0); assert.ok(h.state.asks.length);
});
test('AI adjustment retains its request contract and only clears prompt on success', async t => {
  const h = setup(t); await open(h); h.controller.setAdjustment('  改为蓝色  '); await h.controller.adjust();
  assert.deepEqual(JSON.parse(h.requests.at(-1).body), { adjustment_request: '改为蓝色' });
  assert.equal(h.controller.getSnapshot().draft, NEXT); assert.equal(h.controller.getSnapshot().adjustment, '');
});
test('application-level confirm failure stays open and preserves all drafts', async t => {
  const h = setup(t); await open(h); h.controller.editDraft(NEXT); h.state.handler = (url, init) => init.method === 'POST' ? json({ success: false, error: '保存失败' }) : undefined;
  await h.controller.confirm(); assert.equal(h.controller.getSnapshot().open, true); assert.equal(h.controller.getSnapshot().draft, NEXT);
  assert.match(h.controller.getSnapshot().error, /保存失败/);
  assert.equal(h.controller.getSnapshot().ready, true);
  h.state.handler = null; await h.controller.confirm();
  assert.equal(h.controller.getSnapshot().open, false);
});
test('readonly verification of an ambiguous confirmation avoids a second library write', async t => {
  const h = setup(t); const { decision } = await open(h); h.controller.setSave(true);
  h.state.handler = (url) => url.endsWith('/confirm') ? Promise.reject(new TypeError('network failed')) : undefined;
  await h.controller.confirm(); assert.equal(h.controller.getSnapshot().ready, false);
  h.state.cached = { confirmed: true, saved_template_id: 9, template: { html_template: HTML } };
  await h.controller.check(); assert.equal(h.controller.getSnapshot().ready, true);
  await h.controller.confirm(); assert.equal(await decision, true);
  assert.equal(h.requests.filter(item => item.url.endsWith('/confirm')).length, 1);
});
test('aborted preflight and late confirmation cannot start a different run', async t => {
  const h = setup(t); const { signal, decision } = await open(h); let release;
  h.state.handler = (url) => url.endsWith('/confirm') ? new Promise(resolve => { release = resolve; }) : undefined;
  const confirm = h.controller.confirm(); await until(() => !!release); signal.abort(); release(json({ success: true })); await confirm;
  assert.equal(await decision, false); assert.equal(h.controller.getSnapshot().open, false);
});
test('global selection uses the existing route and permission failure does not fail open', async t => {
  const h = setup(t); h.state.metadata = { template_mode: 'global' }; h.controller.mount();
  h.state.handler = url => url.endsWith('/selected-global-template') ? json({ template: null, is_user_selected: false }) : undefined;
  assert.equal(await h.controller.prepare(new AbortController().signal), false); assert.match(h.state.navigations[0], /template-selection$/);
  h.state.handler = () => json({ detail: 'Forbidden' }, 403);
  await assert.rejects(h.controller.prepare(new AbortController().signal), /项目不可访问/);
  assert.equal(h.requests.filter(item => item.method === 'POST').length, 0);
});
test('bounded read timeout aborts the old request and disposal rejects its late response', async t => {
  const h = setup(t, {}, { request: 5 }); let release;
  h.state.handler = url => url.endsWith('/free-template') ? new Promise(resolve => { release = resolve; }) : undefined;
  await open(h); assert.match(h.controller.getSnapshot().error, /请求超时/);
  assert.ok(h.requests.at(-1).signal.aborted); h.controller.dispose(); const count = h.snapshots.length;
  release(json({ template: { html_template: NEXT } })); await sleep(5); assert.equal(h.snapshots.length, count);
});
