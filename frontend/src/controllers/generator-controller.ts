// Generation owns state and network resources; React views only consume
// snapshots. Constructing a controller has no side effects.
export type GeneratorSlide = {
  page_number: number; html_content: string; title?: string;
  generation_failed?: boolean; is_user_edited?: boolean; [key: string]: unknown;
};
type Phase = 'idle' | 'preparing' | 'running' | 'reconnecting' | 'paused' | 'stopped' | 'complete' | 'error' | 'recovering';
export type GeneratorState = {
  phase: Phase; visible: boolean; state: string; message: string; percent: number;
  connection: string; connectionClass: string; total?: number; completed: number;
  activePages: number[]; slides: GeneratorSlide[]; busy: boolean; notice: string;
  startLabel: string; canStart: boolean;
};
export type GeneratorOptions = {
  projectId: string; slides?: unknown; total?: number; status?: string;
  autoStart?: boolean; unattended?: boolean; generating?: boolean;
};
type Source = Pick<EventSource, 'onopen' | 'onmessage' | 'onerror' | 'close' | 'readyState'>;
type Environment = {
  fetch?: typeof fetch; connect?: (url: string) => Source;
  prepare?: (signal: AbortSignal) => Promise<boolean>;
  confirm?: (message: string) => Promise<boolean>;
  timings?: Partial<typeof defaults>;
};
const defaults = { connectTimeout: 15000, reconnect: 1000, maxReconnect: 30000, attempts: 5, poll: 10000, request: 15000, recovery: 30 * 60 * 1000, autoStart: 500 };
const usable = (slide: GeneratorSlide) => !!slide.html_content && (!slide.generation_failed || !!slide.is_user_edited);
function slidesFrom(value: unknown): GeneratorSlide[] {
  if (!Array.isArray(value)) return [];
  const pages = new Map<number, GeneratorSlide>();
  value.forEach((item, index) => {
    if (!item || typeof item.html_content !== 'string' || !item.html_content) return;
    const number = item.page_number == null ? index + 1 : Number(item.page_number);
    if (Number.isSafeInteger(number) && number > 0) pages.set(number, { ...item, page_number: number });
  });
  return [...pages.values()].sort((a, b) => a.page_number - b.page_number);
}
function positive(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0 ? value : undefined;
}
function pageRanges(pages: number[]) {
  const ranges: string[] = [];
  for (let index = 0; index < pages.length; index++) {
    const first = pages[index]; let last = first;
    while (pages[index + 1] === last + 1) last = pages[++index];
    ranges.push(first === last ? `${first}` : `${first}-${last}`);
  }
  return ranges.join('、');
}
const reasonText = (reason: unknown) => reason instanceof Error ? reason.message : String(reason);

export function createGeneratorController(options: GeneratorOptions, environment: Environment = {}) {
  const fetcher = environment.fetch || globalThis.fetch.bind(globalThis);
  const connect = environment.connect || ((url: string) => new EventSource(url));
  const clock = { ...defaults, ...environment.timings };
  const api = `/api/projects/${encodeURIComponent(options.projectId)}`;
  const initialSlides = slidesFrom(options.slides);
  const total = positive(options.total) || (initialSlides.length || undefined);
  const initialComplete = !!initialSlides.length && (positive(options.total)
    ? Array.from({ length: options.total! }, (_, index) => index + 1).every(number => initialSlides.some(slide => slide.page_number === number && usable(slide)))
    : options.status === 'completed' && initialSlides.every(usable));
  let state: GeneratorState = {
    phase: initialComplete ? 'complete' : 'idle', visible: initialComplete,
    state: initialComplete ? 'complete' : '', message: initialComplete ? 'PPT已生成完成' : '',
    percent: initialComplete ? 100 : 0, connection: initialComplete ? '生成完成' : '未连接',
    connectionClass: initialComplete ? 'completed' : 'disconnected', total,
    completed: initialSlides.filter(usable).length, activePages: [], slides: initialSlides,
    busy: false, notice: '', startLabel: '开始生成', canStart: !options.unattended && !initialComplete,
  };
  const listeners = new Set<(value: GeneratorState) => void>();
  let active = false, mounted = false, visible = true, suspended = false;
  let source: Source | null = null, epoch = 0, operation: AbortController | null = null;
  let pollRequest: AbortController | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  let connectionTimer: ReturnType<typeof setTimeout> | undefined;
  let pollTimer: ReturnType<typeof setTimeout> | undefined;
  let autoTimer: ReturnType<typeof setTimeout> | undefined;
  let attempts = 0, phaseMessage = '', recoveryStarted = 0;
  let cancelPending: Promise<void> | null = null;
  let needsClearCancel = false;
  const current = (token: number) => active && !suspended && token === epoch;
  function publish(next: Partial<GeneratorState>) {
    if (!active || suspended) return;
    state = { ...state, ...next };
    listeners.forEach(listener => listener(state));
  }
  function connection(connectionClass: string, message: string) {
    publish({ connectionClass, connection: message });
  }
  function closeStream() {
    const previous = source; source = null;
    previous?.close();
    clearTimeout(reconnectTimer); clearTimeout(connectionTimer);
  }
  function clearResources() {
    closeStream(); clearTimeout(pollTimer); clearTimeout(autoTimer);
    operation?.abort(); operation = null;
    pollRequest?.abort(); pollRequest = null;
  }
  async function jsonRequest(path: string, signal: AbortSignal, method = 'GET') {
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) controller.abort();
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      return await Promise.race([
        (async () => {
          const response = await fetcher(path, { method, credentials: 'same-origin', signal: controller.signal });
          if ([401, 403, 404].includes(response.status)) throw new Error('项目不可访问，请返回项目列表。');
          const payload = await response.json();
          if (!response.ok || payload.success === false || payload.error || payload.status === 'error') throw new Error(payload.detail || payload.error || payload.message || `HTTP ${response.status}`);
          return payload;
        })(),
        new Promise<never>((_, reject) => {
          timer = setTimeout(() => { reject(new Error('请求超时，请稍后重试。')); controller.abort(); }, clock.request);
          controller.signal.addEventListener('abort', () => reject(new Error('请求已中断。')), { once: true });
        }),
      ]);
    } finally { clearTimeout(timer); signal.removeEventListener('abort', abort); }
  }
  function progress(totalValue?: unknown, completedValue?: unknown) {
    const total = positive(totalValue) || state.total;
    const completed = typeof completedValue === 'number' && Number.isInteger(completedValue) && completedValue >= 0
      ? Math.min(completedValue, total || completedValue) : state.slides.filter(usable).length;
    const activePages = state.activePages.filter(number => !state.slides.some(slide => slide.page_number === number && usable(slide))).sort((a, b) => a - b);
    const detail = activePages.length ? `，正在生成第${pageRanges(activePages)}页` : phaseMessage && completed < (total || Infinity) ? `，${phaseMessage}` : '';
    publish({ total, completed, activePages, percent: total ? Math.min(completed / total * 100, 100) : 0,
      state: 'progress', message: `PPT生成中... (${total ? `${completed}/${total} 页已完成` : `已完成 ${completed} 页`}${detail})` });
  }
  function terminal(message: string, failed: boolean, label = '重新开始') {
    closeStream(); clearTimeout(pollTimer);
    phaseMessage = '';
    publish({ phase: failed ? 'error' : 'complete', visible: true, state: failed ? 'error' : 'complete',
      message, activePages: [], busy: false, canStart: failed && !options.unattended,
      startLabel: label, ...(failed ? {} : { percent: 100 }), notice: '' });
    connection(failed ? 'error' : 'completed', failed ? '生成过程出错' : '生成完成');
  }
  function receive(data: Record<string, any>) {
    if (!data || typeof data !== 'object') return;
    switch (data.type) {
      case 'progress': {
        if (typeof data.completed === 'number') phaseMessage = typeof data.message === 'string' ? data.message : '';
        else if (positive(data.current)) publish({ activePages: [...new Set([...state.activePages, data.current])] });
        progress(data.total, data.completed); break;
      }
      case 'slide': case 'slide_skipped': {
        const slide = slidesFrom(data.slide_data ? [data.slide_data] : [])[0];
        if (!slide || !positive(data.slide_data?.page_number)) break;
        const previous = state.slides.find(value => value.page_number === slide.page_number);
        if (!previous?.is_user_edited || slide.is_user_edited) {
          publish({ slides: [...state.slides.filter(value => value.page_number !== slide.page_number), slide].sort((a, b) => a.page_number - b.page_number) });
        }
        progress(data.total); break;
      }
      case 'complete': {
        progress(data.total, data.succeeded);
        terminal(typeof data.message === 'string' ? data.message : '生成完成', !!data.partial, '补生成失败页');
        if (data.partial) connection('error', '部分页面待重新生成');
        break;
      }
      case 'error': terminal(typeof data.message === 'string' ? data.message : '生成失败，请重试。', true); break;
    }
  }
  function reconnect(token: number) {
    if (!current(token) || !['running', 'reconnecting'].includes(state.phase)) return;
    if (attempts >= clock.attempts) {
      terminal('连接失败，请点击重新连接按钮重试', true, '重新连接');
      connection('failed', `连接失败，已尝试 ${clock.attempts} 次重连`); return;
    }
    const delay = Math.min(clock.reconnect * 2 ** attempts++, clock.maxReconnect);
    publish({ phase: 'reconnecting' });
    connection('reconnecting', `第 ${attempts} 次重连中... (${Math.ceil(delay / 1000)}秒后)`);
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => openStream(token), delay);
  }
  function openStream(token: number) {
    if (!current(token) || options.unattended) return;
    closeStream();
    connection('connecting', '正在连接服务器...');
    let stream: Source;
    try { stream = connect(`${api}/slides/stream`); source = stream; }
    catch { reconnect(token); return; }
    const valid = () => current(token) && source === stream;
    connectionTimer = setTimeout(() => { if (valid() && stream.readyState !== 1) { closeStream(); reconnect(token); } }, clock.connectTimeout);
    stream.onopen = () => {
      if (!valid()) return;
      clearTimeout(connectionTimer);
      publish({ phase: 'running' }); connection('connected', '正在生成');
    };
    stream.onmessage = event => {
      if (!valid()) return;
      let data;
      try { data = JSON.parse(event.data); } catch { return; }
      attempts = 0;
      receive(data);
    };
    stream.onerror = () => {
      if (!valid()) return;
      closeStream(); reconnect(token);
    };
  }
  async function start() {
    if (!active || suspended || options.unattended || state.busy || !state.canStart) return;
    const token = ++epoch; operation?.abort(); operation = new AbortController();
    const signal = operation.signal;
    clearTimeout(pollTimer); clearTimeout(autoTimer); pollRequest?.abort();
    publish({ busy: true, notice: '', canStart: false });
    try {
      if (environment.prepare && !await environment.prepare(signal)) return;
      if (!current(token)) return;
      await cancelPending;
      if (!current(token)) return;
      if (needsClearCancel) { await jsonRequest(`${api}/slides/clear-cancel`, signal, 'POST'); needsClearCancel = false; }
      if (!current(token)) return;
      // Start/retry rehydrates saved previews through slide_skipped events.
      publish({ phase: 'running', visible: true, state: 'progress', slides: initialSlides,
        activePages: [], notice: '', busy: false });
      phaseMessage = ''; attempts = 0;
      progress(); openStream(token);
    } catch (reason) {
      if (current(token)) publish({ notice: `无法开始生成：${reasonText(reason)}`, canStart: true });
    } finally {
      if (current(token)) publish({ busy: false, canStart: !['running', 'reconnecting'].includes(state.phase) });
    }
  }
  function requestCancel(token: number) {
    operation?.abort(); operation = new AbortController();
    needsClearCancel = true;
    publish({ busy: true });
    const request = jsonRequest(`${api}/slides/cancel`, operation.signal, 'POST').then(() => undefined).catch(reason => {
      if (current(token)) publish({ notice: `停止请求尚未确认：${reasonText(reason)} 后台任务可能仍在运行。` });
    }).finally(() => {
      if (cancelPending === request) cancelPending = null;
      if (current(token)) publish({ busy: false });
    });
    cancelPending = request;
  }
  function pause() {
    if (!active || suspended || options.unattended || state.busy || !['running', 'reconnecting'].includes(state.phase)) return;
    const token = ++epoch; closeStream();
    publish({ phase: 'paused', notice: '', message: '生成已暂停，点击"继续"按钮恢复生成' });
    connection('paused', '已暂停生成'); requestCancel(token);
  }
  async function resumeGeneration() {
    if (!active || suspended || options.unattended || state.busy || state.phase !== 'paused') return;
    const token = ++epoch; operation?.abort(); operation = new AbortController();
    publish({ busy: true, notice: '' });
    connection('paused', '正在清除暂停状态...');
    try {
      await cancelPending;
      await jsonRequest(`${api}/slides/clear-cancel`, operation.signal, 'POST');
      if (!current(token)) return;
      needsClearCancel = false; attempts = 0;
      publish({ phase: 'running', busy: false, message: '正在恢复生成...' });
      openStream(token);
    } catch (reason) {
      if (current(token)) { publish({ notice: `恢复失败：${reasonText(reason)}`, busy: false }); connection('paused', '恢复失败，尚未继续生成'); }
    }
  }
  let confirming = false;
  async function stop() {
    if (!active || suspended || confirming || options.unattended || state.busy || !['running', 'reconnecting', 'paused', 'recovering'].includes(state.phase)) return;
    const token = epoch; confirming = true;
    try {
      const count = state.completed;
      const message = count ? `已生成 ${count}${state.total ? '/' + state.total : ''} 页。确定要停止生成吗？\n\n已生成的幻灯片将被保留，您可以稍后继续生成。` : '确定要停止PPT生成吗？';
      if (!environment.confirm || !await environment.confirm(message) || !current(token) || !['running', 'reconnecting', 'paused', 'recovering'].includes(state.phase)) return;
      ++epoch; closeStream(); clearTimeout(pollTimer); pollRequest?.abort();
      publish({ phase: 'stopped', state: 'error', message: count ? `生成已停止（已完成 ${count} 页）` : '生成已停止', activePages: [], canStart: true, startLabel: '继续生成', notice: '' });
      connection('stopped', '已停止生成'); requestCancel(epoch);
    } finally { confirming = false; }
  }
  function recover() {
    closeStream(); recoveryStarted = Date.now();
    publish({ phase: 'recovering', visible: true, state: 'progress', busy: false, canStart: false, notice: '',
      message: '正在读取后台生成结果，已生成页面会继续保留。' });
    connection('reconnecting', '正在检查后台结果');
    void poll();
  }
  async function poll() {
    if (!active || suspended || !visible || state.phase !== 'recovering' || pollRequest) return;
    const request = new AbortController(), token = epoch; pollRequest = request;
    try {
      const payload = await jsonRequest(api, request.signal);
      if (!current(token) || request.signal.aborted) return;
      const project = payload.project || payload;
      if (Array.isArray(project.slides_data)) {
        publish({ slides: slidesFrom(project.slides_data) }); progress();
      }
      const stage = project.todo_board?.stages?.find((item: { id: string }) => item.id === 'ppt_creation');
      const savedComplete = state.total && state.slides.filter(usable).length >= state.total;
      if (stage?.status === 'completed' || savedComplete && project.status === 'completed') terminal('PPT已生成完成', false);
      else if (['failed', 'cancelled'].includes(stage?.status) || ['failed', 'cancelled'].includes(project.status)) terminal(stage?.error_message || '后台生成暂未完成，已保留页面，可继续生成。', true, '继续生成');
      else if (Date.now() - recoveryStarted >= clock.recovery) terminal('暂未获取到完整结果，请返回项目详情检查后台任务后重试。', true, '检查后继续生成');
      else publish({ message: '正在读取后台生成结果，请勿重复生成。', notice: '' });
    } catch (reason) {
      if (!current(token) || request.signal.aborted) return;
      if (/项目不可访问/.test(reasonText(reason))) { terminal(reasonText(reason), true); publish({ canStart: false }); }
      else if (Date.now() - recoveryStarted >= clock.recovery) terminal('后台结果暂不可用，请返回项目详情检查后重试。', true, '检查后继续生成');
      else publish({ notice: `暂未读到后台结果：${reasonText(reason)} 将自动重试。` });
    } finally {
      if (pollRequest === request) pollRequest = null;
      if (current(token) && !request.signal.aborted && visible && state.phase === 'recovering') pollTimer = setTimeout(() => void poll(), clock.poll);
    }
  }
  return {
    getSnapshot: () => state,
    subscribe(listener: (value: GeneratorState) => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    start, pause, resumeGeneration, stop,
    mount() {
      if (mounted) return;
      mounted = active = true;
      if (initialComplete) return;
      if (options.unattended || options.generating) recover();
      else if (options.autoStart || initialSlides.length) autoTimer = setTimeout(() => void start(), clock.autoStart);
    },
    suspend() {
      if (!active || suspended) return;
      // Cancelling preparation has not started a slide task. A cached return
      // restores its Start button rather than polling for nonexistent output.
      if (state.busy && ['idle', 'error', 'stopped'].includes(state.phase)) publish({ busy: false, canStart: !options.unattended });
      suspended = true; ++epoch; clearResources();
    },
    resume() {
      if (!active || !suspended) return;
      suspended = false;
      // A stream GET can start work. Restoring a cached document only reads;
      // it never repeats auto-start, template preparation or clear-cancel.
      if (!['complete', 'idle', 'error', 'stopped', 'paused'].includes(state.phase) || state.busy) recover();
    },
    setVisible(next: boolean) {
      visible = next;
      if (!next) { clearTimeout(pollTimer); pollRequest?.abort(); pollRequest = null; }
      else if (state.phase === 'recovering') void poll();
    },
    dispose() {
      active = false; mounted = false; suspended = false; ++epoch; clearResources(); listeners.clear();
    },
  };
}
