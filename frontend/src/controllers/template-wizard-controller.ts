// Template preparation owns its requests and drafts; the Ant view owns no
// generation state. No DOM or React dependencies, and no work at construction.
export type TemplateWizardState = {
  open: boolean; busy: boolean; ready: boolean; blocked: boolean;
  phase: 'idle' | 'loading' | 'generating' | 'adjusting' | 'confirming' | 'ready' | 'error';
  status: string; error: string; notice: string; html: string; draft: string;
  save: boolean; name: string; adjustment: string;
};
type Options = { projectId: string; topic?: string; templateMode?: string; unattended?: boolean };
type Environment = {
  fetch?: typeof fetch;
  ask?: (text: string, signal: AbortSignal) => Promise<boolean>;
  navigate?: (path: string) => void;
  timings?: { request?: number; ai?: number; streamIdle?: number };
};
type Job = { abort: AbortController; reader?: ReadableStreamDefaultReader<Uint8Array> };
const text = (value: unknown) => value instanceof Error ? value.message : String(value);
const validHtml = (value: unknown): value is string => typeof value === 'string' && !!value.trim();
const rejected = (message: string) => Object.assign(new Error(message), { definitive: true });

export function createTemplateWizardController(options: Options, environment: Environment = {}) {
  const fetcher = environment.fetch || globalThis.fetch.bind(globalThis);
  const api = `/api/projects/${encodeURIComponent(options.projectId)}`;
  const clock = { request: 15000, ai: 300000, streamIdle: 120000, ...environment.timings };
  const listeners = new Set<(value: TemplateWizardState) => void>();
  let state: TemplateWizardState = { open: false, busy: false, ready: false, blocked: false, phase: 'idle', status: '', error: '', notice: '', html: '', draft: '', save: false, name: '', adjustment: '' };
  let active = false, job: Job | null = null, serverHtml = '', uncertain = false;
  let confirmationIntent: { html: string; save: boolean; name: string } | null = null;
  let confirmedIntent = false;
  let pending: { resolve(value: boolean): void; detach(): void } | null = null;
  let preparing = false, preparation = 0;
  const current = (value: Job) => active && job === value && !value.abort.signal.aborted;
  function publish(next: Partial<TemplateWizardState>) {
    if (!active) return;
    state = { ...state, ...next }; listeners.forEach(listener => listener(state));
  }
  function releaseJob() {
    const old = job; job = null;
    old?.abort.abort(); void old?.reader?.cancel().catch(() => {});
  }
  function begin(phase: TemplateWizardState['phase'], status: string): Job | null {
    if (!active || state.busy || state.blocked || options.unattended) return null;
    releaseJob(); const next = { abort: new AbortController() }; job = next;
    publish({ busy: true, error: '', phase, status }); return next;
  }
  function settled(value: Job) { if (current(value)) { releaseJob(); publish({ busy: false }); } }
  function failure(value: Job, reason: unknown) {
    if (!current(value)) return;
    const message = text(reason);
    publish({ phase: 'error', error: message, status: '操作未完成', ready: uncertain ? false : state.ready, blocked: /项目不可访问/.test(message), notice: uncertain ? '请求结果尚未确认，请先检查后台结果，避免重复生成。' : state.notice });
  }
  async function bounded<T>(work: Promise<T>, value: Job, timeout: number): Promise<T> {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let abort: () => void = () => {};
    try {
      return await Promise.race([work, new Promise<never>((_, reject) => {
        abort = () => reject(new Error('请求已中断'));
        if (value.abort.signal.aborted) { abort(); return; }
        value.abort.signal.addEventListener('abort', abort, { once: true });
        timer = setTimeout(() => reject(new Error('请求超时，请检查后台结果后重试。')), timeout);
      })]);
    } finally { clearTimeout(timer); value.abort.signal.removeEventListener('abort', abort); }
  }
  async function request(path: string, value: Job, body?: Record<string, unknown>, timeout = clock.request) {
    const response = await bounded(fetcher(path, { method: body ? 'POST' : 'GET', credentials: 'same-origin', signal: value.abort.signal,
      ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}),
    }), value, timeout);
    if ([401, 403, 404].includes(response.status)) throw rejected('项目不可访问，请返回项目列表。');
    const result = await bounded(response.json(), value, timeout);
    if (!response.ok || result?.success === false || result?.error || result?.status === 'error') {
      const message = result?.detail || result?.error || result?.message || `HTTP ${response.status}`;
      throw result?.success === false || [400, 409, 422].includes(response.status) ? rejected(message) : new Error(message);
    }
    return result;
  }
  function accept(html: string, name?: string, preserveDraft = false) {
    const changed = serverHtml !== html;
    const dirty = !!serverHtml && state.draft !== serverHtml;
    serverHtml = html;
    if (changed) uncertain = false;
    publish({ html: preserveDraft && dirty ? state.html : html, draft: preserveDraft && dirty ? state.draft : html,
      ready: !uncertain, phase: 'ready', status: `模板已就绪：${name || '自由模板'}`,
      notice: preserveDraft && dirty ? '已保留未确认的源码修改，确认时会使用当前源码。' : uncertain ? '上次请求的结果尚未确认。请核对预览；不要重复发起生成。' : '', error: '' });
  }
  async function consume(response: Response, value: Job) {
    if (!response.body) throw new Error('未收到流式响应，请检查后台结果。');
    const reader = response.body.getReader(); value.reader = reader;
    const decoder = new TextDecoder(); let buffer = '', complete = false;
    function event(raw: string) {
      const data = raw.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
      if (!data.trim() || !current(value)) return;
      let item; try { item = JSON.parse(data); } catch { return; }
      if (item?.type === 'status') publish({ status: typeof item.message === 'string' ? item.message : '正在生成模板…' });
      if (item?.type === 'thinking') publish({ status: 'AI 正在生成模板内容…' });
      if (item?.type === 'preview' && validHtml(item.html_template)) publish({ html: item.html_template, status: '正在生成模板预览…' });
      if (item?.type === 'error') { uncertain = false; throw new Error(item.message || '模板生成失败'); }
      if (item?.type === 'complete') {
        const template = item.template || item;
        if (!validHtml(template.html_template)) { uncertain = false; throw new Error('模板生成结束，但未收到有效模板。'); }
        uncertain = false; complete = true; accept(template.html_template, template.template_name);
      }
    }
    try {
      while (current(value) && !complete) {
        const { value: chunk, done } = await bounded(reader.read(), value, clock.streamIdle);
        buffer += decoder.decode(chunk, { stream: !done });
        buffer = buffer.replace(/\r\n/g, '\n');
        let boundary;
        while (!complete && (boundary = buffer.indexOf('\n\n')) >= 0) { const raw = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2); event(raw); }
        if (done) { if (!complete && buffer.trim()) event(buffer); break; }
      }
      if (current(value) && !complete) throw new Error('连接已中断，尚未确认完整模板，请检查后台结果。');
    } finally { void reader.cancel().catch(() => {}); }
  }
  async function generate(force = true) {
    const value = begin('generating', '正在准备生成模板…'); if (!value) return;
    const backup = { html: state.html, draft: state.draft, ready: state.ready };
    try {
      if ((uncertain || state.draft !== serverHtml && state.draft.trim()) && environment.ask) {
        if (!await environment.ask(uncertain ? '上次请求可能仍在后台运行。重新生成可能重复调用 AI，是否继续？' : '重新生成会替换尚未确认的源码修改，是否继续？', value.abort.signal)) return;
      }
      if (!current(value)) return;
      const cached = await request(`${api}/free-template`, value);
      if (!current(value)) return;
      if (cached.status === 'generating') { publish({ ready: false, status: '后台模板正在生成，请稍后检查结果。', notice: '已有模板任务在运行，本次没有重复生成。' }); return; }
      if (!force && validHtml(cached.template?.html_template)) { uncertain = false; accept(cached.template.html_template, cached.template.template_name, true); return; }
      uncertain = true; publish({ ready: false, notice: '', status: '正在生成模板…' });
      const response = await bounded(fetcher(`${api}/free-template/generate`, { method: 'POST', credentials: 'same-origin', signal: value.abort.signal,
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' }, body: JSON.stringify({ force, stream: true }),
      }), value, clock.request);
      if (!current(value)) return;
      if (!response.ok) {
        const result = await bounded(response.json().catch(() => ({})), value, clock.request);
        if ([401, 403, 404].includes(response.status)) throw new Error('项目不可访问，请返回项目列表。');
        uncertain = false; throw new Error(result.detail || result.error || `HTTP ${response.status}`);
      }
      await consume(response, value);
    } catch (reason) { if (current(value)) { publish(backup); failure(value, reason); } }
    finally { if (current(value)) { value.abort.abort(); job = null; publish({ busy: false }); } }
  }
  async function check(autoGenerate = false) {
    const value = begin('loading', '正在读取模板…'); if (!value) return;
    let missing = false;
    try {
      const result = await request(`${api}/free-template`, value);
      if (!current(value)) return;
      if (confirmationIntent && result.confirmed && result.template?.html_template === confirmationIntent.html && (!confirmationIntent.save || result.saved_template_id)) { uncertain = false; confirmedIntent = true; }
      if (result.status === 'generating') { publish({ ready: false, status: '后台模板正在生成，请稍后检查结果。', notice: '检查只读取结果，不会重新生成模板。' }); return; }
      if (validHtml(result.template?.html_template)) accept(result.template.html_template, result.template.template_name, true);
      else { missing = true; publish({ ready: false, status: '尚未生成模板', notice: uncertain ? '上次请求尚未确认，请稍后检查后台结果。' : '生成模板后，可预览、调整并确认使用。' }); }
    } catch (reason) { failure(value, reason); }
    finally { settled(value); }
    if (active && missing && autoGenerate && !uncertain && !state.blocked) await generate(false);
  }
  async function adjust() {
    const requirement = state.adjustment.trim(); if (!requirement || !state.ready) return;
    const value = begin('adjusting', '正在调整模板…'); if (!value) return;
    try {
      if (state.draft !== serverHtml && environment.ask && !await environment.ask('AI 调整使用服务器保存的模板，将替换未确认的源码修改，是否继续？', value.abort.signal)) return;
      if (!current(value)) return;
      uncertain = true;
      const result = await request(`${api}/free-template/adjust`, value, { adjustment_request: requirement }, clock.ai);
      if (!current(value)) return;
      if (!validHtml(result.template?.html_template)) throw new Error('调整未返回有效模板');
      uncertain = false; accept(result.template.html_template, result.template.template_name);
      publish({ adjustment: '' });
    } catch (reason) { if (reason instanceof Error && 'definitive' in reason) uncertain = false; failure(value, reason); }
    finally { settled(value); }
  }
  function finish(result: boolean) { const previous = pending; pending = null; previous?.detach(); previous?.resolve(result); }
  async function confirm() {
    if (!active || state.busy || state.blocked || !state.ready || !validHtml(state.draft)) return;
    if (confirmedIntent && confirmationIntent?.html === state.draft && confirmationIntent.save === state.save && confirmationIntent.name === state.name.trim()) { publish({ open: false, status: '模板已确认' }); finish(true); return; }
    const value = begin('confirming', '正在确认模板…'); if (!value) return;
    try {
      uncertain = true;
      confirmationIntent = { html: state.draft, save: state.save, name: state.name.trim() }; confirmedIntent = false;
      await request(`${api}/free-template/confirm`, value, { save_to_library: state.save, template_name: state.name.trim(), html_template: state.draft });
      if (!current(value)) return;
      uncertain = false; serverHtml = state.draft;
      publish({ html: state.draft, open: false, status: '模板已确认', error: '' }); finish(true);
    } catch (reason) { if (reason instanceof Error && 'definitive' in reason) uncertain = false; failure(value, reason); }
    finally { settled(value); }
  }
  function cancel() {
    if (!active) return;
    ++preparation; preparing = false;
    releaseJob(); publish({ open: false, busy: false }); finish(false);
  }
  async function prepare(signal: AbortSignal) {
    if (!active || signal.aborted || preparing || options.unattended) return false;
    preparing = true; const version = ++preparation;
    let abort = () => {};
    try {
      const value = begin('loading', '正在检查模板…'); if (!value) return false;
      abort = () => cancel(); signal.addEventListener('abort', abort, { once: true });
      const project = await request(api, value);
      if (!current(value) || signal.aborted) return false;
      const metadata = project.project_metadata || {};
      settled(value);
      if (metadata.template_mode === 'package' || metadata.generation_mode === 'package') return true;
      const free = metadata.template_mode === 'free';
      if (free) {
        if (metadata.free_template_confirmed && (!state.draft || state.draft === serverHtml) && !uncertain) return true;
        publish({ open: true });
        const answer = new Promise<boolean>(resolve => { pending = { resolve, detach: () => signal.removeEventListener('abort', abort) }; });
        void check(!uncertain && !state.ready);
        return await answer;
      }
      const selectionJob = begin('loading', '正在检查已选模板…'); if (!selectionJob) return false;
      const selected = await request(`${api}/selected-global-template`, selectionJob);
      if (!current(selectionJob) || signal.aborted) return false;
      settled(selectionJob);
      if (selected.template && selected.is_user_selected) return true;
      if (environment.ask && await environment.ask('检测到您还未选择全局模板，需要先选择模板才能开始生成PPT。是否跳转到模板选择页面？', signal) && active && !signal.aborted) environment.navigate?.(`/projects/${encodeURIComponent(options.projectId)}/template-selection`);
      return false;
    } finally { signal.removeEventListener('abort', abort); if (version === preparation) { preparing = false; if (job && !state.open) { releaseJob(); publish({ busy: false }); } } }
  }
  return {
    getSnapshot: () => state,
    subscribe(listener: (value: TemplateWizardState) => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    mount() { active = true; },
    prepare, generate, check: () => check(false), adjust, confirm, cancel,
    editDraft(draft: string) { if (!state.busy) publish({ draft }); },
    applyDraft() { if (!state.busy && validHtml(state.draft)) publish({ html: state.draft }); },
    setAdjustment(adjustment: string) { if (!state.busy) publish({ adjustment }); },
    setSave(save: boolean) { if (!state.busy) publish({ save, name: state.name || `自由模板-${(options.topic || 'PPT').slice(0, 20)}-${new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '')}` }); },
    setName(name: string) { if (!state.busy) publish({ name }); },
    dispose() { cancel(); active = false; releaseJob(); listeners.clear(); },
  };
}
export type TemplateWizardController = ReturnType<typeof createTemplateWizardController>;
