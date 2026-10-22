import test from 'node:test';
import assert from 'node:assert/strict';
import { createGeneratorController } from '../src/controllers/generator-controller.ts';

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(check) {
  const start = Date.now();
  while (!check()) { if (Date.now() - start > 1500) throw new Error('condition did not settle'); await sleep(1); }
}
const page = (number = 1, extra = {}) => ({ page_number: number, title: `Page ${number}`, html_content: `<body>Page ${number}</body>`, ...extra });
const json = (value, status = 200) => Response.json(value, { status });
function setup(t, options = {}, environment = {}) {
  const streams = [], requests = [], snapshots = [];
  const state = { body: {}, status: 200, prepare: 0, confirm: 0, handler: null };
  const controller = createGeneratorController({ projectId: 'project /中文', total: 3, ...options }, {
    fetch: async (url, init) => {
      requests.push({ url, ...init });
      return await state.handler?.(url, init) || json(state.body, state.status);
    },
    connect: url => {
      const source = { url, readyState: 0, close() { this.readyState = 2; }, onopen: null, onmessage: null, onerror: null };
      streams.push(source); return source;
    },
    prepare: async () => { state.prepare++; return true; },
    confirm: async () => { state.confirm++; return true; },
    timings: { reconnect: 2, maxReconnect: 5, connectTimeout: 100000, poll: 5, request: 100000, recovery: 100000, autoStart: 1 },
    ...environment,
  });
  controller.subscribe(value => snapshots.push(value));
  t.after(() => controller.dispose());
  const send = (event, index = streams.length - 1) => streams[index].onmessage?.({ data: JSON.stringify(event) });
  const open = (index = streams.length - 1) => { streams[index].readyState = 1; streams[index].onopen?.({}); };
  return { controller, streams, requests, snapshots, state, send, open };
}

test('construction and repeated mounts are inert for an idle project', async t => {
  const h = setup(t); assert.equal(h.requests.length + h.streams.length, 0);
  h.controller.mount(); h.controller.mount(); await sleep(5);
  assert.equal(h.requests.length + h.streams.length, 0);
  assert.equal(h.controller.getSnapshot().canStart, true);
});
test('auto-start and partial saved pages each start once; completed pages never start', async t => {
  for (const options of [{ autoStart: true }, { slides: [page()] }]) {
    const h = setup(t, options); h.controller.mount(); h.controller.mount();
    await until(() => h.streams.length === 1); await sleep(5);
    assert.equal(h.streams.length, 1);
  }
  const h = setup(t, { slides: [page(1), page(2), page(3)] }); h.controller.mount(); await sleep(5);
  assert.equal(h.streams.length, 0); assert.equal(h.controller.getSnapshot().phase, 'complete');
});
test('failed placeholder pages and duplicate page numbers do not masquerade as completion', async t => {
  for (const slides of [[page(1), page(1), page(3)], [page(1), page(2, { generation_failed: true }), page(3)]]) {
    const h = setup(t, { slides }); h.controller.mount();
    await until(() => h.streams.length === 1);
    assert.notEqual(h.controller.getSnapshot().phase, 'complete');
  }
});
test('unattended and known background runs only read results and reject manual actions', async t => {
  const h = setup(t, { unattended: true, autoStart: true }); h.controller.mount();
  await h.controller.start(); h.controller.pause(); await h.controller.resumeGeneration(); await h.controller.stop();
  await sleep(12);
  assert.equal(h.streams.length, 0); assert.equal(h.state.prepare, 0); assert.equal(h.state.confirm, 0);
  assert.ok(h.requests.length > 0); assert.ok(h.requests.every(item => item.method === 'GET'));
  const running = setup(t, { generating: true, autoStart: true }); running.controller.mount(); await sleep(5);
  assert.equal(running.streams.length, 0); assert.equal(running.controller.getSnapshot().phase, 'recovering');
});
test('concurrent clicks hold the preflight lock and create one encoded stream', async t => {
  let release;
  const h = setup(t, {}, { prepare: () => new Promise(resolve => { release = resolve; }) }); h.controller.mount();
  const first = h.controller.start(); await h.controller.start();
  assert.equal(h.controller.getSnapshot().busy, true); release(true); await first;
  assert.equal(h.streams.length, 1); assert.match(h.streams[0].url, /project%20%2F%E4%B8%AD%E6%96%87\/slides\/stream$/);
});
test('cancelled preflight releases the start button without issuing a stream', async t => {
  const h = setup(t, {}, { prepare: async () => false }); h.controller.mount(); await h.controller.start();
  assert.equal(h.streams.length, 0); assert.equal(h.controller.getSnapshot().canStart, true);
  assert.equal(h.controller.getSnapshot().busy, false);
});
test('suspended or disposed preflight cannot start a stream after late confirmation', async t => {
  for (const action of ['suspend', 'dispose']) {
    let release;
    const h = setup(t, {}, { prepare: () => new Promise(resolve => { release = resolve; }) }); h.controller.mount();
    const pending = h.controller.start(); h.controller[action](); release(true); await pending;
    assert.equal(h.streams.length, 0);
  }
});
test('progress is bounded, tracks concurrent pages and preserves server available counts', async t => {
  const h = setup(t); h.controller.mount(); await h.controller.start(); h.open();
  h.send({ type: 'progress', total: 8, current: 2 }); h.send({ type: 'progress', current: 3 });
  h.send({ type: 'progress', current: 4 }); h.send({ type: 'progress', current: 7 });
  assert.match(h.controller.getSnapshot().message, /第2-4、7页/);
  h.send({ type: 'progress', total: 8, completed: 2, message: '内容已保存' });
  assert.equal(h.controller.getSnapshot().percent, 25);
  h.send({ type: 'progress', completed: 200 }); assert.equal(h.controller.getSnapshot().percent, 100);
});
test('unknown totals do not invent progress and malformed events do not kill a stream', async t => {
  const h = setup(t, { total: 0 }); h.controller.mount(); await h.controller.start(); h.open();
  h.streams[0].onmessage({ data: 'malformed' }); h.send(null); h.send({ type: 'slide', slide_data: { page_number: '<script>', html_content: 'bad' } });
  assert.equal(h.controller.getSnapshot().slides.length, 0);
  h.send({ type: 'slide', slide_data: page() });
  assert.equal(h.controller.getSnapshot().total, undefined); assert.equal(h.controller.getSnapshot().percent, 0);
});
test('out of order pages are deduplicated and edited documents survive stale replay', async t => {
  const h = setup(t); h.controller.mount(); await h.controller.start();
  h.send({ type: 'slide', slide_data: page(3) });
  h.send({ type: 'slide', slide_data: page(1, { is_user_edited: true, html_content: '<body>Edited</body>' }) });
  h.send({ type: 'slide_skipped', slide_data: page(1) });
  h.send({ type: 'slide', slide_data: page(3, { title: 'Updated' }) });
  assert.deepEqual(h.controller.getSnapshot().slides.map(item => item.page_number), [1, 3]);
  assert.equal(h.controller.getSnapshot().slides[0].html_content, '<body>Edited</body>');
  assert.equal(h.controller.getSnapshot().slides[1].title, 'Updated');
});
test('terminal completion closes the source, ignores late packets and stops reconnection', async t => {
  for (const partial of [false, true]) {
    const h = setup(t); h.controller.mount(); await h.controller.start(); h.open();
    h.send({ type: 'slide', slide_data: page() });
    h.send({ type: 'complete', total: 3, succeeded: 1, partial, message: 'Finished' });
    h.send({ type: 'error', message: 'Late' }); h.streams[0].onerror({}); await sleep(10);
    assert.equal(h.streams[0].readyState, 2); assert.equal(h.streams.length, 1);
    assert.equal(h.controller.getSnapshot().message, 'Finished');
    assert.equal(h.controller.getSnapshot().canStart, partial);
    assert.ok(Math.abs(h.controller.getSnapshot().percent - (partial ? 100 / 3 : 100)) < 0.001);
  }
});
test('pause waits for cancellation before resume clears it; stale stream events are ignored', async t => {
  let cancelled;
  const h = setup(t); h.state.handler = (url) => url.endsWith('/cancel') ? new Promise(resolve => { cancelled = resolve; }) : undefined;
  h.controller.mount(); await h.controller.start(); h.open(); h.controller.pause();
  await h.controller.resumeGeneration(); assert.equal(h.streams.length, 1);
  h.send({ type: 'complete', message: 'Stale' }); assert.equal(h.controller.getSnapshot().phase, 'paused');
  cancelled(json({ success: true })); await until(() => !h.controller.getSnapshot().busy);
  await Promise.all([h.controller.resumeGeneration(), h.controller.resumeGeneration()]);
  assert.equal(h.streams.length, 2);
  assert.deepEqual(h.requests.map(item => item.url.split('/').at(-1)), ['cancel', 'clear-cancel']);
});
test('failed clear-cancel keeps the pause visible, never opens SSE, and permits retry', async t => {
  const h = setup(t); h.controller.mount(); await h.controller.start(); h.controller.pause();
  await until(() => !h.controller.getSnapshot().busy);
  h.state.body = { success: false, error: 'cancel service unavailable' }; await h.controller.resumeGeneration();
  assert.equal(h.streams.length, 1); assert.equal(h.controller.getSnapshot().phase, 'paused');
  assert.match(h.controller.getSnapshot().notice, /cancel service unavailable/);
  h.state.body = { success: true }; await h.controller.resumeGeneration(); assert.equal(h.streams.length, 2);
});
test('failed cancel states that the background task may still run', async t => {
  const h = setup(t); h.controller.mount(); await h.controller.start(); h.state.status = 503;
  h.controller.pause(); await until(() => !h.controller.getSnapshot().busy);
  assert.match(h.controller.getSnapshot().notice, /后台任务可能仍在运行/);
  assert.equal(h.streams[0].readyState, 2);
});
test('stopping confirms once and restarting clears cancellation before SSE', async t => {
  let answer;
  const h = setup(t, {}, { confirm: () => new Promise(resolve => { answer = resolve; }) });
  h.controller.mount(); await h.controller.start();
  const stopped = h.controller.stop(); await h.controller.stop(); answer(true); await stopped;
  await until(() => !h.controller.getSnapshot().busy);
  assert.equal(h.controller.getSnapshot().phase, 'stopped');
  await h.controller.start(); assert.equal(h.streams.length, 2);
  assert.deepEqual(h.requests.map(item => item.url.split('/').at(-1)), ['cancel', 'clear-cancel']);
});
test('confirmation does not cancel a task that completed while the dialog was open', async t => {
  let answer;
  const h = setup(t, {}, { confirm: () => new Promise(resolve => { answer = resolve; }) }); h.controller.mount(); await h.controller.start();
  const stopped = h.controller.stop(); h.send({ type: 'complete', message: 'Completed' }); answer(true); await stopped;
  assert.equal(h.requests.length, 0); assert.equal(h.controller.getSnapshot().phase, 'complete');
});
test('reconnect closes the old source and stale callbacks cannot change the new run', async t => {
  const h = setup(t); h.controller.mount(); await h.controller.start(); h.open();
  const old = h.streams[0]; old.onerror({}); assert.equal(old.readyState, 2);
  await until(() => h.streams.length === 2); h.open();
  old.onopen({}); old.onmessage({ data: JSON.stringify({ type: 'error', message: 'Old' }) }); old.onerror({});
  assert.equal(h.controller.getSnapshot().phase, 'running'); assert.equal(h.controller.getSnapshot().notice, '');
});
test('retry budget is bounded even when connections open then immediately fail', async t => {
  const h = setup(t, {}, { timings: { attempts: 2, reconnect: 1, maxReconnect: 2, connectTimeout: 100000 } }); h.controller.mount(); await h.controller.start();
  for (let index = 0; index < 3; index++) { await until(() => h.streams.length > index); h.open(index); h.streams[index].onerror({}); }
  assert.equal(h.controller.getSnapshot().phase, 'error'); assert.equal(h.controller.getSnapshot().startLabel, '重新连接');
  await sleep(8); assert.equal(h.streams.length, 3);
});
test('cached restoration reads saved pages without replaying auto-start or mutation', async t => {
  const h = setup(t, { autoStart: true }); h.controller.mount(); await until(() => h.streams.length === 1);
  h.send({ type: 'slide', slide_data: page() }); h.controller.suspend();
  assert.equal(h.streams[0].readyState, 2);
  h.state.body = { status: 'completed', slides_data: [page(1), page(2), page(3)] };
  h.controller.resume(); await until(() => h.controller.getSnapshot().phase === 'complete');
  assert.equal(h.streams.length, 1); assert.equal(h.state.prepare, 1);
  assert.equal(h.requests.length, 1); assert.equal(h.requests[0].method, 'GET');
  assert.equal(h.controller.getSnapshot().slides.length, 3);
});
test('recovery is readonly until a failed task is reported, preserving failed documents', async t => {
  const h = setup(t, { generating: true });
  h.state.body = { slides_data: [page(1), page(2, { generation_failed: true })], todo_board: { stages: [{ id: 'ppt_creation', status: 'failed' }] } };
  h.controller.mount(); await until(() => h.controller.getSnapshot().phase === 'error');
  assert.equal(h.streams.length, 0); assert.equal(h.controller.getSnapshot().canStart, true);
  assert.equal(h.controller.getSnapshot().slides.length, 2); assert.equal(h.controller.getSnapshot().completed, 1);
});
test('hidden tabs keep a live stream but pause readonly polling; aborted reads cannot overwrite resumed data', async t => {
  const h = setup(t); h.controller.mount(); await h.controller.start(); h.controller.setVisible(false);
  h.send({ type: 'slide', slide_data: page() }); assert.equal(h.controller.getSnapshot().slides.length, 1);
  h.controller.suspend(); h.controller.resume(); assert.equal(h.requests.length, 0);
  let release;
  h.state.handler = () => new Promise(resolve => { release = resolve; }); h.controller.setVisible(true);
  await until(() => !!release); h.controller.setVisible(false);
  h.state.handler = null; h.state.body = { slides_data: [page(1), page(2), page(3)], status: 'completed' }; h.controller.setVisible(true);
  await until(() => h.controller.getSnapshot().phase === 'complete');
  release(json({ slides_data: [] })); await sleep(5);
  assert.equal(h.controller.getSnapshot().slides.length, 3);
});
test('permission errors stop polling and disable new work', async t => {
  const h = setup(t, { generating: true }); h.state.status = 403; h.controller.mount();
  await until(() => h.controller.getSnapshot().phase === 'error');
  assert.equal(h.controller.getSnapshot().canStart, false); await sleep(15); assert.equal(h.requests.length, 1);
});
test('bounded recovery requests report timeout; disposal silences late results and timers', async t => {
  let release;
  const h = setup(t, { generating: true }, { timings: { request: 5, poll: 100000, recovery: 100000 } });
  h.state.handler = () => new Promise(resolve => { release = resolve; }); h.controller.mount();
  await until(() => !!h.controller.getSnapshot().notice); assert.match(h.controller.getSnapshot().notice, /请求/);
  h.controller.dispose(); const count = h.snapshots.length; release(json({ status: 'completed', slides_data: [page(1), page(2), page(3)] }));
  await sleep(10); assert.equal(h.snapshots.length, count); assert.equal(h.streams.length, 0);
});

test('cached return during cancelled template preparation restores Start without polling slides', async t => {
  let release;
  const h = setup(t, {}, { prepare: () => new Promise(resolve => { release = resolve; }) }); h.controller.mount();
  const started = h.controller.start(); h.controller.suspend(); h.controller.resume(); release(false); await started;
  assert.equal(h.controller.getSnapshot().canStart, true); assert.equal(h.controller.getSnapshot().busy, false);
  assert.equal(h.streams.length, 0); assert.equal(h.requests.length, 0);
});
