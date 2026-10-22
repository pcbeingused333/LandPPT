// One state owner for outline generation. No DOM, React or global page state.
export type Outline = Record<string, any> & { slides: Record<string, any>[] };
export type OutlineState = {
  visible: boolean; loading: boolean; error: string; outline: Outline | null;
  canStart: boolean; language: string; phase: 'idle' | 'preparing' | 'streaming' | 'recovering'; statusText: string;
};
export type OutlineStream = { run: number; text: string };
export type OutlineOptions = {
  projectId: string; outline?: unknown; language?: string; confirmed: boolean;
  stageStatus: string; pptStageStatus?: string; hasOutput: boolean; unattended: boolean; readOnly?: boolean;
};
const timings = { resume: 500, stageSync: 15000, maxStageSync: 120000, recoveryPoll: 10000, recoveryTimeout: 30 * 60 * 1000, readTimeout: 15000 };
type Environment = { fetch?: typeof fetch; timings?: Partial<typeof timings> };
type Run = { controller: AbortController; signature: string | null; reader?: ReadableStreamDefaultReader<Uint8Array> };

export function validOutline(value: any): value is Outline {
  return !!value && !Array.isArray(value) && Array.isArray(value.slides) && value.slides.length > 0
    && value.slides.every((slide: unknown) => !!slide && typeof slide === 'object' && !Array.isArray(slide));
}

// Compare all content, not only titles: regeneration can keep titles and change points.
export function outlineSignature(value: unknown): string | null {
  if (!validOutline(value)) return null;
  return JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item);
}

function aborted(): DOMException { return new DOMException('Outline view detached', 'AbortError'); }
function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(aborted()); return; }
    const cancel = () => { clearTimeout(timer); reject(aborted()); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', cancel); resolve(); }, ms);
    signal.addEventListener('abort', cancel, { once: true });
  });
}
function message(reason: unknown): string { return reason instanceof Error ? reason.message : String(reason || '连接失败'); }
function networkDisconnect(reason: unknown): boolean {
  return reason instanceof TypeError || /network error|failed to fetch|load failed|body stream/i.test(message(reason));
}
function parseOutline(content: string): Outline | null {
  const fenced = content.match(/```(?:json)?\s*([\s\S]*?)```/);
  const text = (fenced ? fenced[1] : content).trim();
  for (const candidate of [text, text.match(/\{[\s\S]*\}/)?.[0]]) {
    if (!candidate) continue;
    try { const value = JSON.parse(candidate); if (validOutline(value)) return value; } catch { /* Wait for validated output. */ }
  }
  return null;
}

export function createOutlineController(options: OutlineOptions, environment: Environment = {}) {
  const fetcher = environment.fetch || globalThis.fetch.bind(globalThis);
  const clock = { ...timings, ...environment.timings };
  const base = `/projects/${encodeURIComponent(options.projectId)}`;
  const api = `/api/projects/${encodeURIComponent(options.projectId)}`;
  const listeners = new Set<(value: OutlineState) => void>();
  const streamListeners = new Set<(value: OutlineStream) => void>();
  let lastOutline = validOutline(options.outline) ? options.outline : null;
  let pptStatus = options.pptStageStatus || '';
  let active = false, mounted = false, visible = true, interrupted = false;
  let run: Run | null = null, pollController: AbortController | null = null;
  let resumeTimer: ReturnType<typeof setTimeout> | undefined;
  let stageTimer: ReturnType<typeof setTimeout> | undefined;
  let stageBackoff = clock.stageSync;
  let stream: OutlineStream = { run: 0, text: '' };
  let hasStreamContent = false;
  const language = (outline: Outline | null) => {
    const candidates: unknown[] = [options.language, outline?.metadata?.language, outline?.language];
    return candidates.find((value): value is string => typeof value === 'string' && !!value.trim())?.trim() || 'zh';
  };
  const mayStart = () => !!lastOutline && !options.hasOutput && !options.unattended && !options.readOnly && (!pptStatus || ['pending', 'failed'].includes(pptStatus));
  const shouldResume = () => !options.unattended && !options.readOnly && options.confirmed && !lastOutline && !options.hasOutput && ['pending', 'running', ''].includes(options.stageStatus);
  let state: OutlineState = {
    visible: !!lastOutline || options.confirmed && !options.unattended && !options.readOnly,
    loading: shouldResume(), error: '', outline: lastOutline, canStart: mayStart(),
    language: language(lastOutline), phase: shouldResume() ? 'preparing' : 'idle', statusText: '',
  };
  if (state.visible && !lastOutline && !shouldResume()) {
    state.error = options.stageStatus === 'failed' ? '上次大纲生成失败，请重新生成大纲。' : '尚未生成大纲，请点击重新生成。';
  }

  function publish(next: Partial<OutlineState>) {
    if (!active) return;
    state = { ...state, ...next };
    listeners.forEach(listener => listener(state));
  }
  function publishStream(text: string) {
    stream = { ...stream, text };
    streamListeners.forEach(listener => listener(stream));
  }
  function current(job: Run) { return active && run === job && !job.controller.signal.aborted; }
  function startRun(phase: OutlineState['phase'], preserveStream = false): Run | null {
    if (!active || run || options.unattended || options.readOnly) return null;
    clearTimeout(resumeTimer);
    const job = { controller: new AbortController(), signature: outlineSignature(lastOutline) };
    run = job;
    if (!preserveStream) {
      stream = { run: stream.run + 1, text: '' }; hasStreamContent = false;
      publishStream('');
    }
    publish({ visible: true, loading: true, error: '', outline: null, canStart: false, phase, statusText: '' });
    return job;
  }
  function complete(job: Run, outline: unknown) {
    if (!current(job)) return;
    if (!validOutline(outline)) throw new Error('大纲生成已结束，但未收到有效的大纲内容，请重新生成大纲。');
    lastOutline = outline;
    publish({ loading: false, error: '', outline, canStart: mayStart(), language: language(outline), phase: 'idle', statusText: '' });
  }
  function fail(job: Run, reason: unknown) {
    if (current(job)) publish({ loading: false, error: message(reason), canStart: false, phase: 'idle', statusText: '' });
  }
  async function jsonRequest(url: string, job: Run, init: RequestInit = {}) {
    const response = await fetcher(url, { ...init, credentials: 'same-origin', signal: job.controller.signal });
    if (!current(job)) throw aborted();
    const result = await response.json().catch(() => ({}));
    if (!current(job)) throw aborted();
    if (!response.ok || result.error || result.status === 'error') {
      throw new Error(result.error || result.detail || result.message || `HTTP ${response.status}`);
    }
    return result;
  }

  async function persisted(job: Run): Promise<Outline | null> {
    const { response, payload } = await readJson(api, job.controller.signal);
    if (!current(job)) throw aborted();
    if ([401, 403, 404].includes(response.status)) throw new Error('项目不可访问，请返回项目列表后重试。');
    if (!response.ok) return null;
    const outline = payload?.outline || payload?.project?.outline;
    if (!validOutline(outline) || job.signature !== null && outlineSignature(outline) === job.signature) return null;
    return outline;
  }
  async function recover(job: Run) {
    if (!current(job)) return;
    publish({ phase: 'recovering', statusText: '连接已中断，正在检查后台结果，请勿重复生成。' });
    const started = Date.now();
    while (current(job) && Date.now() - started < clock.recoveryTimeout) {
      try {
        const outline = await persisted(job);
        if (outline) { complete(job, outline); return; }
      } catch (reason) {
        if (!current(job)) return;
        if (/项目不可访问/.test(message(reason))) throw reason;
      }
      await delay(clock.recoveryPoll, job.controller.signal);
    }
    if (current(job)) throw new Error('流式连接中断，暂未获取到后台生成结果，请稍后刷新页面查看或重试。');
  }
  function status(step: string, text: string) {
    publish({ statusText: text || '' });
    if (!hasStreamContent) publishStream(`[${step || 'status'}] ${text || ''}\n`);
  }
  function section(header: string) {
    hasStreamContent = true;
    publishStream(`${stream.text.trimEnd()}${stream.text.trim() ? '\n\n' : ''}# ${header}\n\n`);
  }
  async function consume(job: Run, force: boolean) {
    try {
      publish({ phase: 'streaming' });
      const response = await fetcher(`${base}/outline-stream${force ? '?force_regenerate=1' : ''}`, { credentials: 'same-origin', signal: job.controller.signal });
      if (!current(job)) return;
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if (!response.body) throw new TypeError('outline stream ended before completion');
      const reader = response.body.getReader(); job.reader = reader;
      const decoder = new TextDecoder();
      let buffer = '', content = '', done = false, validated: unknown = null, count = 0;
      async function line(value: string) {
        if (!current(job) || !value.trim().startsWith('data:')) return;
        let data;
        try { data = JSON.parse(value.trim().slice(5).trim()); } catch { return; }
        if (!data || typeof data !== 'object') return;
        if (data.error) throw new Error(String(data.error));
        if (data.outline) validated = data.outline;
        if (data.status) status(data.status.step, data.status.message);
        if (data.content_reset) { content = ''; section(data.content_header || 'LLM 实时输出'); }
        if (data.content) {
          if (!hasStreamContent) section('实时输出');
          content += data.content; publishStream(stream.text + data.content);
          if (++count % 80 === 0) await delay(0, job.controller.signal); // Hidden tabs must continue reading.
        }
        if (data.done) done = true;
      }
      while (current(job) && !done) {
        const chunk = await reader.read();
        if (!current(job)) return;
        buffer += decoder.decode(chunk.value, { stream: !chunk.done });
        const lines = buffer.split('\n'); buffer = lines.pop() || '';
        for (const value of lines) { await line(value); if (done) break; }
        if (chunk.done) { if (!done && buffer) await line(buffer); break; }
      }
      if (!current(job)) return;
      if (!done) throw new TypeError('outline stream ended before completion');
      complete(job, validOutline(validated) ? validated : parseOutline(content));
    } catch (reason) {
      if (!current(job)) return;
      if (networkDisconnect(reason)) await recover(job);
      else throw reason;
    } finally {
      const reader = job.reader;
      if (reader) {
        await reader.cancel().catch(() => {});
        reader.releaseLock(); job.reader = undefined;
      }
    }
  }
  async function beginOutline() {
    if (lastOutline) return;
    const job = startRun('streaming'); if (!job) return;
    try { await consume(job, false); }
    catch (reason) { fail(job, reason); }
    finally { if (run === job) run = null; }
  }
  async function regenerate(requirements: string) {
    const job = startRun('preparing'); if (!job) return;
    try {
      // Preserve the existing best-effort stage update and deferred generation contract.
      await jsonRequest(`${api}/stages/outline_generation`, job, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'running', progress: 0 }) }).catch(() => {});
      if (!current(job)) return;
      const result = await jsonRequest(`${base}/regenerate-outline`, job, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ custom_requirements: requirements || '' }),
      });
      if (result.defer_generation) await consume(job, true);
      else complete(job, result.outline || parseOutline(result.outline_content || ''));
    } catch (reason) { fail(job, reason); }
    finally { if (run === job) run = null; }
  }

  function shouldPoll() { return active && visible && !options.unattended && !options.readOnly && !options.hasOutput && (!!lastOutline || options.confirmed); }
  function scheduleStageSync(ms: number) {
    clearTimeout(stageTimer);
    if (shouldPoll()) stageTimer = setTimeout(syncStage, ms);
  }
  async function syncStage() {
    if (!shouldPoll()) return;
    const owner = new AbortController(); pollController = owner;
    try {
      const { response, payload } = await readJson(`${api}/todo`, owner.signal);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if (!shouldPoll() || owner.signal.aborted || pollController !== owner) return;
      const stage = payload.stages?.find((item: any) => item?.id === 'ppt_creation');
      if (stage) { pptStatus = stage.status; if (!run && !state.error) publish({ canStart: mayStart() }); }
      stageBackoff = clock.stageSync;
    } catch {
      if (owner.signal.aborted || !active) return;
      stageBackoff = Math.min(stageBackoff * 2, clock.maxStageSync);
    } finally {
      if (pollController === owner) { pollController = null; if (!owner.signal.aborted) scheduleStageSync(stageBackoff); }
    }
  }
  async function readJson(url: string, signal: AbortSignal) {
    const owner = new AbortController();
    const cancel = () => owner.abort();
    signal.addEventListener('abort', cancel, { once: true });
    if (signal.aborted) owner.abort();
    const timer = setTimeout(cancel, clock.readTimeout);
    let rejectAbort: (() => void) | undefined;
    const interruption = new Promise<never>((_, reject) => {
      rejectAbort = () => reject(aborted());
      owner.signal.addEventListener('abort', rejectAbort, { once: true });
      if (owner.signal.aborted) rejectAbort();
    });
    try {
      return await Promise.race([interruption, (async () => {
        const response = await fetcher(url, { credentials: 'same-origin', cache: 'no-store', signal: owner.signal });
        const payload = await response.json();
        return { response, payload };
      })()]);
    } finally {
      clearTimeout(timer); signal.removeEventListener('abort', cancel);
      if (rejectAbort) owner.signal.removeEventListener('abort', rejectAbort);
    }
  }
  function stopWork() {
    interrupted = !!run;
    active = false;
    clearTimeout(resumeTimer); clearTimeout(stageTimer);
    const previous = run; run = null;
    previous?.controller.abort();
    void previous?.reader?.cancel().catch(() => {});
    pollController?.abort(); pollController = null;
  }
  function activate() {
    if (active) return;
    active = true;
    if (interrupted) {
      interrupted = false;
      const job = startRun('recovering', true);
      if (job) void recover(job).catch(reason => fail(job, reason)).finally(() => { if (run === job) run = null; });
    } else if (shouldResume()) {
      resumeTimer = setTimeout(() => { void beginOutline(); }, clock.resume);
    }
    scheduleStageSync(clock.stageSync);
  }
  return {
    snapshot: () => state,
    subscribe(listener: (value: OutlineState) => void) { listeners.add(listener); listener(state); return () => { listeners.delete(listener); }; },
    subscribeStream(listener: (value: OutlineStream) => void) { streamListeners.add(listener); listener(stream); return () => { streamListeners.delete(listener); }; },
    mount() { mounted = true; activate(); },
    suspend: stopWork,
    resume() { if (mounted) activate(); },
    setVisible(next: boolean) {
      visible = next;
      if (!visible) { clearTimeout(stageTimer); pollController?.abort(); }
      else scheduleStageSync(0);
    },
    beginOutline, regenerate,
    saved(outline: unknown) {
      if (!active || run || options.unattended || options.readOnly || !validOutline(outline)) return;
      lastOutline = outline;
      publish({ visible: true, loading: false, error: '', outline, canStart: mayStart(), language: language(outline), phase: 'idle', statusText: '' });
    },
    templateSelectionUrl: () => active && state.canStart && !run ? `${base}/template-selection` : null,
    dispose() { mounted = false; stopWork(); listeners.clear(); streamListeners.clear(); },
  };
}
export type OutlineController = ReturnType<typeof createOutlineController>;
