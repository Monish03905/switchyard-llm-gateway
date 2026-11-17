import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 18, ...props }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.6,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    ...props,
  };
}

export function IconYard(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
    </svg>
  );
}

export function IconDispatch(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M3 12h14" />
      <path d="M13 6l6 6-6 6" />
      <path d="M3 6v12" />
    </svg>
  );
}

export function IconGauntlet(props: IconProps) {
  return (
    <svg {...base(props)}>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4.5" />
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3" />
    </svg>
  );
}

export function IconLedger(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M6 3h12v18H6z" />
      <path d="M9 7h6M9 11h6M9 15h4" />
      <path d="M6 3l-2 2v16h2" />
    </svg>
  );
}

export function IconSwitchboard(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
      <circle cx="16" cy="7" r="2" />
      <circle cx="10" cy="17" r="2" />
    </svg>
  );
}

export function IconNotes(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5z" />
      <path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H13v16h5.5a1.5 1.5 0 0 0 1.5-1.5z" />
      <path d="M7 8h2M7 11h2M15 8h2M15 11h2" />
    </svg>
  );
}

export function YardMark({ size = 42, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <rect x="1" y="1" width="46" height="46" stroke="currentColor" strokeWidth="1.5" />
      <path d="M12 42V22l12-12 12 12v20" stroke="currentColor" strokeWidth="2.4" />
      <path d="M12 34h24M12 27h24" stroke="currentColor" strokeWidth="1.2" strokeDasharray="2 4" />
      <path d="M18 42V25" stroke="var(--volt)" strokeWidth="3" />
      <path d="M30 42V18" stroke="currentColor" strokeWidth="1.4" />
      <circle cx="30" cy="18" r="3" fill="var(--volt)" stroke="currentColor" strokeWidth="1.2" />
      <path d="M6 10h8M34 6h8" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

export function ArrowGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M2 8h11M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

export function DialGlyph({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6.4" stroke="currentColor" strokeWidth="1.2" />
      <path d="M8 8l3.4-3.4" stroke="currentColor" strokeWidth="1.4" />
      <circle cx="8" cy="8" r="1.2" fill="currentColor" />
    </svg>
  );
}
