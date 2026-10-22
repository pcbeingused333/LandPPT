import test from 'node:test';
import assert from 'node:assert/strict';
import { createOutlineController, outlineSignature } from '../src/controllers/outline-controller.ts';
const outline = { title: '研发协作', slides: [{ title: '目标', content_points: ['组织内容'], page_number: 1 }] };
const updated = { ...outline, slides: [{ ...outline.slides[0], content_points: ['新的内容，标题保持不变'] }] };
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(check) {
  const start = Date.now();
  while (!check()) { if (Date.now() - start > 1500) throw new Error('condition did not settle'); await sleep(1); }
}
const json = (body, status = 200) => Response.json(body, { status });

function setup(t, options = {}, handler = () => undefined, timing = {}) {
  const streams = [], requests = [], state = { cancels: 0 };
  const fetch = async (url, init = {}) => {
    requests.push({ url, ...init, at: Date.now() });
    const result = await handler(url, init);
    if (result !== undefined) return result;
    if (url.includes('/outline-stream')) {
      const body = new ReadableStream({
        start(writer) {
          streams.push(writer);
          init.signal?.addEventListener('abort', () => { try { writer.error(new DOMException('aborted', 'AbortError')); } catch {} }, { once: true });
        },
        cancel() { state.cancels++; },
      });
      return new Response(body);
    }
    if (url.endsWith('/regenerate-outline')) return json({ status: 'success', defer_generation: true });
    if (url.endsWith('/todo')) return json({ stages: [{ id: 'ppt_creation', status: 'pending' }] });
    return json({ status: 'success' });
  };
  const controller = createOutlineController({ projectId: 'project /中文', confirmed: false, stageStatus: 'pending', hasOutput: false, unattended: false, ...options }, {
    fetch, timings: { resume: 2, stageSync: 100000, recoveryPoll: 2, recoveryTimeout: 100, ...timing },
  });
  const snapshots = [];
  controller.subscribe(value => snapshots.push(value));
  t.after(() => controller.dispose());
  const send = (value, index = streams.length - 1) => streams[index].enqueue(new TextEncoder().encode('data: ' + JSON.stringify(value) + '\n\n'));
  return { controller, streams, requests, send, snapshots, state };
}

test('construction and repeated mounts do not start work for a new project', async t => {
  const h = setup(t);
  assert.equal(h.requests.length, 0);
  h.controller.mount(); h.controller.mount();
  await sleep(8);
  assert.equal(h.requests.length, 0);
  assert.equal(h.controller.snapshot().visible, false);
});

test('confirmed unfinished projects resume once; saved output and unattended runs stand down', async t => {
  const pending = setup(t, { confirmed: true, stageStatus: 'running' });
  pending.controller.mount(); pending.controller.mount();
  await until(() => pending.streams.length === 1);
  await sleep(6);
  assert.equal(pending.streams.length, 1);
  for (const options of [{ confirmed: true, outline }, { confirmed: true, hasOutput: true }, { confirmed: true, unattended: true }]) {
    const h = setup(t, options); h.controller.mount();
    await sleep(5);
    assert.equal(h.streams.length, 0);
    if (options.unattended) {
      assert.equal(h.controller.snapshot().visible, false);
      assert.equal(h.controller.snapshot().loading, false);
      await h.controller.regenerate('must not start unattended work');
      assert.equal(h.requests.length, 0);
    }
  }
});

test('complete validated output publishes immutable snapshots and enables the existing design route', async t => {
  const h = setup(t); h.controller.mount();
  const promise = h.controller.beginOutline();
  await until(() => h.streams.length === 1);
  h.send({ status: { step: 'research', message: '正在整理资料' } });
  h.send({ outline, done: true });
  await promise;
  assert.deepEqual(h.controller.snapshot().outline, outline);
  assert.equal(h.controller.snapshot().loading, false);
  assert.equal(h.controller.templateSelectionUrl(), '/projects/project%20%2F%E4%B8%AD%E6%96%87/template-selection');
  assert.equal(h.snapshots.find(value => value.phase === 'streaming').loading, true);
  assert.ok(h.state.cancels >= 1);
});

test('concurrent begin/regenerate clicks share one active generation', async t => {
  const h = setup(t); h.controller.mount();
  const first = h.controller.beginOutline();
  await Promise.all([h.controller.beginOutline(), h.controller.regenerate('duplicate')]);
  await until(() => h.streams.length === 1);
  h.send({ outline, done: true }); await first;
  assert.equal(h.requests.length, 1);
});

test('deferred regeneration preserves requests and holds its lock through the stream', async t => {
  const h = setup(t, { outline }); h.controller.mount();
  const promise = h.controller.regenerate('保留标题，增加要点');
  await h.controller.regenerate('duplicate');
  await until(() => h.streams.length === 1);
  assert.deepEqual(h.requests.map(item => item.method || 'GET'), ['PUT', 'POST', 'GET']);
  assert.deepEqual(JSON.parse(h.requests[1].body), { custom_requirements: '保留标题，增加要点' });
  assert.match(h.requests[2].url, /force_regenerate=1$/);
  h.send({ outline: updated, done: true }); await promise;
  assert.deepEqual(h.controller.snapshot().outline, updated);
});

test('synchronous regeneration results use the same validated completion path', async t => {
  const h = setup(t, { outline }, url => url.endsWith('/regenerate-outline') ? json({ outline_content: JSON.stringify(updated) }) : undefined);
  h.controller.mount(); await h.controller.regenerate('update');
  assert.equal(h.streams.length, 0);
  assert.deepEqual(h.controller.snapshot().outline, updated);
});

test('malformed records are ignored; split UTF-8 and an unterminated final data line survive', async t => {
  const h = setup(t); h.controller.mount(); const promise = h.controller.beginOutline();
  await until(() => h.streams.length === 1);
  const bytes = new TextEncoder().encode('data: invalid\ndata: null\ndata: ' + JSON.stringify({ outline, done: true }));
  for (let index = 0; index < bytes.length; index += 7) h.streams[0].enqueue(bytes.slice(index, index + 7));
  h.streams[0].close(); await promise;
  assert.deepEqual(h.controller.snapshot().outline, outline);
});

test('plain/fenced token output and resets remain supported without a DOM or animation frames', async t => {
  const h = setup(t); h.controller.mount(); const promise = h.controller.beginOutline();
  await until(() => h.streams.length === 1);
  h.send({ content: 'discard this draft' });
  h.send({ content_reset: true, content_header: '重新组织内容' });
  for (const char of '```json\n' + JSON.stringify(outline) + '\n```') h.send({ content: char });
  h.send({ done: true }); await promise;
  assert.deepEqual(h.controller.snapshot().outline, outline);
});

test('done without usable pages is an error and never enables design', async t => {
  const h = setup(t); h.controller.mount(); const promise = h.controller.beginOutline();
  await until(() => h.streams.length === 1);
  h.send({ outline: { slides: [] }, done: true }); await promise;
  assert.match(h.controller.snapshot().error, /未收到有效/);
  assert.equal(h.controller.templateSelectionUrl(), null);
});

test('failed regeneration releases the lock so an explicit retry can succeed', async t => {
  let failed = true;
  const h = setup(t, { outline }, url => url.endsWith('/regenerate-outline') && failed ? json({ error: '服务暂时不可用' }) : undefined);
  h.controller.mount(); await h.controller.regenerate('keep requirements');
  assert.equal(h.controller.snapshot().error, '服务暂时不可用');
  assert.equal(h.streams.length, 0);
  failed = false;
  const promise = h.controller.regenerate('keep requirements');
  await until(() => h.streams.length === 1);
  h.send({ outline: updated, done: true }); await promise;
  assert.equal(h.controller.snapshot().error, '');
});

test('recovery rejects the old outline including reordered keys and accepts changed points with unchanged titles', async t => {
  let reads = 0;
  const oldWithReorderedKeys = { slides: outline.slides.map(slide => ({ page_number: 1, content_points: slide.content_points, title: slide.title })), title: outline.title };
  const h = setup(t, { outline }, url => url.startsWith('/api/projects/') && !url.includes('/stages/') && !url.endsWith('/todo')
    ? json({ outline: ++reads === 1 ? oldWithReorderedKeys : updated }) : undefined);
  h.controller.mount(); const promise = h.controller.regenerate('new points');
  await until(() => h.streams.length === 1);
  h.streams[0].close(); await promise;
  assert.equal(reads, 2);
  assert.ok(h.snapshots.some(value => value.phase === 'recovering'));
  assert.deepEqual(h.controller.snapshot().outline, updated);
});

test('recovery is bounded and permission loss stops it immediately', async t => {
  for (const permission of [false, true]) {
    let reads = 0;
    const h = setup(t, {}, url => url.startsWith('/api/projects/') ? (reads++, json({}, permission ? 404 : 200)) : undefined, { recoveryTimeout: 8 });
    h.controller.mount(); const promise = h.controller.beginOutline();
    await until(() => h.streams.length === 1); h.streams[0].close(); await promise;
    assert.equal(h.controller.snapshot().loading, false);
    assert.match(h.controller.snapshot().error, permission ? /项目不可访问/ : /暂未获取/);
    if (permission) assert.equal(reads, 1);
  }
});

test('disposal aborts the stream and removes subscribers without recovery or late state changes', async t => {
  const h = setup(t); h.controller.mount(); const promise = h.controller.beginOutline();
  await until(() => h.streams.length === 1);
  const last = h.controller.snapshot(), count = h.snapshots.length;
  h.controller.dispose(); await promise;
  await sleep(5);
  h.controller.saved(updated);
  assert.equal(h.requests[0].signal.aborted, true);
  assert.equal(h.requests.length, 1);
  assert.equal(h.controller.snapshot(), last);
  assert.equal(h.snapshots.length, count);
});

test('leaving while a regeneration POST is pending cannot open a late stream', async t => {
  let resolve;
  const response = new Promise(done => { resolve = done; });
  const h = setup(t, { outline }, url => url.endsWith('/regenerate-outline') ? response : undefined);
  h.controller.mount(); const promise = h.controller.regenerate('extra');
  await until(() => h.requests.some(item => item.url.endsWith('/regenerate-outline')));
  h.controller.dispose(); resolve(json({ defer_generation: true })); await promise;
  assert.equal(h.streams.length, 0);
});

test('disposal cancels recovery delays and does not issue later polls', async t => {
  let reads = 0;
  const h = setup(t, {}, url => url.startsWith('/api/projects/') ? (reads++, json({})) : undefined, { recoveryPoll: 1000 });
  h.controller.mount(); const promise = h.controller.beginOutline();
  await until(() => h.streams.length === 1); h.streams[0].close();
  await until(() => reads === 1);
  h.controller.dispose(); await promise; await sleep(8);
  assert.equal(reads, 1);
});

test('suspend/restore checks saved results and does not create a second generation', async t => {
  const h = setup(t, { outline }, url => url.startsWith('/api/projects/') && !url.includes('/stages/') && !url.endsWith('/todo') ? json({ outline: updated }) : undefined);
  h.controller.mount(); const promise = h.controller.regenerate('new');
  await until(() => h.streams.length === 1);
  h.controller.suspend(); await promise;
  h.controller.resume();
  await until(() => h.controller.snapshot().outline === updated || h.controller.snapshot().outline?.slides[0].content_points[0] === updated.slides[0].content_points[0]);
  assert.equal(h.streams.length, 1);
  assert.equal(h.requests.filter(item => item.method === 'POST').length, 1);
});

test('the preparation phase can also restore without repeating its pending POST', async t => {
  let finish;
  const response = new Promise(resolve => { finish = resolve; });
  const h = setup(t, { outline }, url => url.endsWith('/regenerate-outline') ? response
    : url.startsWith('/api/projects/') && !url.includes('/stages/') && !url.endsWith('/todo') ? json({ outline: updated }) : undefined);
  h.controller.mount(); const promise = h.controller.regenerate('new');
  await until(() => h.requests.some(item => item.url.endsWith('/regenerate-outline')));
  h.controller.suspend(); h.controller.resume();
  await until(() => h.controller.snapshot().outline?.slides[0].content_points[0] === updated.slides[0].content_points[0]);
  finish(json({ defer_generation: true })); await promise;
  assert.equal(h.streams.length, 0);
  assert.equal(h.requests.filter(item => item.method === 'POST').length, 1);
});

test('stage polling pauses in hidden views, backs off and ignores delayed replies after disposal', async t => {
  let fail = true;
  const h = setup(t, { outline }, url => url.endsWith('/todo') ? json({ stages: [] }, fail ? 503 : 200) : undefined, { stageSync: 5, maxStageSync: 40 });
  h.controller.mount();
  await until(() => h.requests.length >= 2);
  assert.ok(h.requests[1].at - h.requests[0].at >= 9);
  h.controller.setVisible(false);
  const count = h.requests.length; await sleep(25); assert.equal(h.requests.length, count);
  fail = false; h.controller.setVisible(true); await until(() => h.requests.length > count);
  h.controller.dispose(); const stopped = h.requests.length; await sleep(15); assert.equal(h.requests.length, stopped);
});

test('separate projects retain separate snapshots, requests and cancellation handles', async t => {
  const first = setup(t, { projectId: 'first' }), second = setup(t, { projectId: 'second' });
  first.controller.mount(); second.controller.mount();
  const a = first.controller.beginOutline(), b = second.controller.beginOutline();
  await until(() => first.streams.length && second.streams.length);
  first.controller.dispose(); second.send({ outline, done: true }); await Promise.all([a, b]);
  assert.deepEqual(second.controller.snapshot().outline, outline);
  assert.equal(second.requests[0].signal.aborted, false);
  assert.match(second.requests[0].url, /\/second\//);
});

test('full signatures detect point changes and remain independent of JSON key ordering', () => {
  assert.notEqual(outlineSignature(outline), outlineSignature(updated));
  assert.equal(outlineSignature(outline), outlineSignature({ slides: outline.slides, title: outline.title }));
});

test('a hung recovery read times out without leaving loading stuck or accepting a late response', async t => {
  let finish;
  const h = setup(t, {}, url => url.startsWith('/api/projects/') ? new Promise(resolve => { finish = resolve; }) : undefined,
    { recoveryPoll: 2, recoveryTimeout: 9, readTimeout: 3 });
  h.controller.mount(); const promise = h.controller.beginOutline();
  await until(() => h.streams.length === 1); h.streams[0].close(); await promise;
  assert.equal(h.controller.snapshot().loading, false);
  assert.match(h.controller.snapshot().error, /暂未获取/);
  finish(json({ outline })); await sleep(2);
  assert.equal(h.controller.snapshot().outline, null);
});

test('a delayed stage reply cannot publish into a disposed view', async t => {
  let finish;
  const h = setup(t, { outline }, url => url.endsWith('/todo') ? new Promise(resolve => { finish = resolve; }) : undefined, { stageSync: 2 });
  h.controller.mount(); await until(() => finish);
  const count = h.snapshots.length;
  h.controller.dispose(); finish(json({ stages: [{ id: 'ppt_creation', status: 'running' }] }));
  await sleep(5);
  assert.equal(h.snapshots.length, count);
});

test('rapid visibility changes resume polling immediately and ignore the cancelled previous reply', async t => {
  let finish;
  const h = setup(t, { outline }, url => url.endsWith('/todo') && !finish ? new Promise(resolve => { finish = resolve; }) : undefined);
  h.controller.mount(); h.controller.setVisible(true);
  await until(() => h.requests.length === 1);
  h.controller.setVisible(false); h.controller.setVisible(true);
  await until(() => h.requests.length === 2);
  finish(json({ stages: [{ id: 'ppt_creation', status: 'running' }] })); await sleep(3);
  assert.equal(h.controller.snapshot().canStart, true);
});

test('read-only planning during a background generation shows saved content without starting or editing work', async t => {
  const h = setup(t, { outline, confirmed: true, readOnly: true }); h.controller.mount();
  await h.controller.beginOutline(); await h.controller.regenerate('must not run');
  h.controller.saved(updated); await sleep(5);
  assert.deepEqual(h.controller.snapshot().outline, outline);
  assert.equal(h.controller.templateSelectionUrl(), null);
  assert.equal(h.requests.length, 0);
});
