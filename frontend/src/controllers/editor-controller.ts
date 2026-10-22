// The workspace owns subscriptions, save state and document-panel feedback.
// Native engines own artwork and requests; DOM compatibility is limited to their
// specialized surfaces. Construction only reads injected snapshots; subscriptions
// and editing actions begin on mount.
type Snapshot = Record<string, any>;
export type EditorPort = { read(): Snapshot; subscribe(listener: (state: Snapshot) => void): () => void; call(name: string, ...args: any[]): any; applyDocument(key: string, value: Snapshot): void; openSpeechDocument(language: string, preview: boolean): void };
export type EditorSurfaces = { read(): Snapshot; subscribe(listener: (state: Snapshot) => void): () => void; close(record: any): void; runContextAction(action: string): void; dismissContextMenu(): void; cancelExport(): void; dismissExport(): void; runShareAction(record: any, action: any): void };
export function createEditorController(engine: EditorPort, surfaces: EditorSurfaces) {
  let active = false, disposed = false, epoch = 0;
  let release: (() => void)[] = [], listeners = new Set<(value: Snapshot) => void>();
  let documentState = { documentPanel: 'slides', documentDirty: false, documentSaving: false };
  let state: Snapshot = { ...engine.read(), ...surfaces.read(), ...documentState, commandError: '', savePending: false };
  let saving: Promise<unknown> | undefined;
  function refresh(extra: Snapshot = {}) {
    if (!active || disposed) return;
    state = { ...state, ...engine.read(), ...surfaces.read(), ...documentState, ...extra };
    listeners.forEach(listener => listener(state));
  }
  function mount() {
    if (active || disposed) return;
    active = true; ++epoch;
    release = [engine.subscribe(() => refresh()), surfaces.subscribe(() => refresh())]; refresh({ savePending: !!saving });
  }
  function suspend() { if (!active) return; active = false; ++epoch; release.forEach(stop => stop()); release = []; }
  const controller = {
    getSnapshot: () => state,
    subscribe(listener: (value: Snapshot) => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    mount, suspend, resume: mount,
    dispose() { suspend(); disposed = true; listeners.clear(); },
    call(name: string, ...args: any[]) {
      if (!active) return;
      const token = epoch;
      const failed = (error: unknown) => { if (active && token === epoch) refresh({ commandError: error instanceof Error ? error.message : String(error) }); return false; };
      try { const result = engine.call(name, ...args); refresh(); return result?.then ? result.catch(failed) : result; } catch (error) { return failed(error); }
    },
    setDocumentState(next: Partial<typeof documentState>) {
      if (Object.entries(next).every(([key, value]) => documentState[key as keyof typeof documentState] === value)) return;
      documentState = { ...documentState, ...next }; refresh();
    },
    saveDocument: null as (() => Promise<void>) | null,
    save() {
      if (!active) return Promise.resolve(false);
      if (saving) return saving;
      const token = epoch;
      const documentSave = controller.saveDocument;
      refresh({ savePending: true, commandError: '' });
      saving = Promise.resolve().then(() => documentSave ? documentSave() : engine.call('saveSlide'))
        .then(result => { if (result === false) throw new Error('保存未完成，请检查错误提示后重试。'); return result; })
        .catch(error => { if (active && token === epoch) refresh({ commandError: error instanceof Error ? error.message : String(error) }); return false; })
        .finally(() => { saving = undefined; if (active) refresh({ savePending: false }); });
      return saving;
    },
    applyDocument: engine.applyDocument, openSpeechDocument: engine.openSpeechDocument,
    close: surfaces.close, runContextAction: surfaces.runContextAction,
    dismissContextMenu: surfaces.dismissContextMenu, cancelExport: surfaces.cancelExport,
    dismissExport: surfaces.dismissExport, runShareAction: surfaces.runShareAction,
  };
  return controller;
}
