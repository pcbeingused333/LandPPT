/** Geometric LP monogram; the P counter doubles as a presentation play mark. */
export function BrandSymbol() {
  return <span className="brand-symbol" aria-hidden="true">
    <svg viewBox="0 0 26 26" fill="currentColor" focusable="false">
      <path d="M3 4h4v13h4l-2 5H3V4Z" />
      <path fillRule="evenodd" clipRule="evenodd" d="M12 4h5.5a6 6 0 0 1 0 12H16v6h-4V4Zm4 4v4l4-2-4-2Z" />
    </svg>
  </span>;
}
