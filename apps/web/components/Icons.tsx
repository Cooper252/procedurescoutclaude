// Small inline icons (no icon font, no network). Decorative unless labeled.

type P = { size?: number; className?: string };
const base = (size = 20) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
});

export const Search = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
);
export const Pin = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21Z" /><circle cx="12" cy="9.5" r="2.5" /></svg>
);
export const Locate = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /><circle cx="12" cy="12" r="7" /></svg>
);
export const Heart = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M12 20s-7.5-4.6-9.2-9.4C1.6 7.2 3.9 4 7.2 4c2 0 3.4 1.1 4.8 2.9C13.4 5.1 14.8 4 16.8 4c3.3 0 5.6 3.2 4.4 6.6C19.5 15.4 12 20 12 20Z" /></svg>
);
export const Receipt = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3Z" /><path d="M9 8h6M9 12h6M9 16h3" /></svg>
);
export const Shield = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M12 3 4.5 6v6c0 4.4 3.2 7.7 7.5 9 4.3-1.3 7.5-4.6 7.5-9V6L12 3Z" /><path d="m9 12 2 2 4-4" /></svg>
);
export const Lock = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>
);
export const FileCheck = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" /><path d="M14 3v5h5" /><path d="m9 14 2 2 4-4" /></svg>
);
export const Arrow = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
);
export const Chevron = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="m6 9 6 6 6-6" /></svg>
);
export const Phone = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z" /></svg>
);
export const Alert = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="M12 3 2 20h20L12 3Z" /><path d="M12 10v4M12 17h.01" /></svg>
);
export const Globe = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3Z" /></svg>
);
export const TrendDown = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="m3 7 7 7 4-4 7 7" /><path d="M21 11v6h-6" /></svg>
);
export const TrendUp = ({ size, className }: P) => (
  <svg {...base(size)} className={className}><path d="m3 17 7-7 4 4 7-7" /><path d="M21 13V7h-6" /></svg>
);

export function Logo({ size = 30 }: { size?: number }) {
  // original mark (2026-11-12): a price tag with a medical cross, in the brand
  // teal; the same drawing is the browser-tab icon (app/icon.svg, favicon.ico)
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <rect width="64" height="64" rx="15" fill="var(--brand)" />
      <path
        d="M11 29.4V14a3 3 0 0 1 3-3h15.4a3 3 0 0 1 2.1.9l20.6 20.6a3 3 0 0 1 0 4.2L36.7 52.1a3 3 0 0 1-4.2 0L11.9 31.5a3 3 0 0 1-.9-2.1Z"
        fill="#fff"
      />
      <circle cx="21.5" cy="21.5" r="4" fill="var(--brand)" />
      <path d="M34.5 28.5v13M28 35h13" stroke="var(--brand)" strokeWidth="4.6" strokeLinecap="round" />
    </svg>
  );
}
