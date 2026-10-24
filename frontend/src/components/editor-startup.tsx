// Match the server placeholder so lazy loading keeps the same workspace shape.
export function EditorStartup() {
  return <div className="editor-startup" role="status" aria-label="正在打开编辑器">
    <div className="editor-startup-heading" aria-hidden><span /><span /></div>
    <div className="editor-startup-panels" aria-hidden>
      <div className="editor-startup-files"><span /><span /><span /></div>
      <div className="editor-startup-main"><span /><div /></div>
      <div className="editor-startup-assistant"><span /><span /><span /></div>
    </div>
  </div>;
}
