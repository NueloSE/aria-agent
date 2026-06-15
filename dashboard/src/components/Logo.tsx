/* ARIA "Prism Peak" mark — one market, refracted into three regime facets.
   Inline SVG so the gradient + glow render identically everywhere. */

export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      role="img"
      aria-label="ARIA logo"
      className="shrink-0"
    >
      <defs>
        <linearGradient id="aria-acc" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#B89EFF" />
          <stop offset="1" stopColor="#1AA6FF" />
        </linearGradient>
        <filter id="aria-glow" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="2.2" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <path d="M32 10 L14 52 H32 Z" fill="#433A85" />
      <path d="M32 10 L50 52 H32 Z" fill="url(#aria-acc)" />
      <path d="M32 10 L41 31 L32 52 L23 31 Z" fill="#C0C7FF" opacity="0.92" filter="url(#aria-glow)" />
      <line x1="10" y1="52" x2="54" y2="52" stroke="currentColor" strokeWidth="3" strokeLinecap="round" opacity="0.6" />
    </svg>
  );
}
