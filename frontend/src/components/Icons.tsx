import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { size?: number }

function base({ size = 16, ...rest }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    ...rest,
  }
}

export const TractorIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M3 15V9h7l2 4h5v2" /><path d="M10 9V5h4l1 4" /><circle cx="7" cy="17" r="3" /><circle cx="18" cy="17" r="2" /></svg>
)
export const PlayIcon = (p: IconProps) => <svg {...base(p)}><path d="M7 4l13 8-13 8z" fill="currentColor" /></svg>
export const PauseIcon = (p: IconProps) => (
  <svg {...base(p)}><rect x="6" y="4" width="4" height="16" fill="currentColor" /><rect x="14" y="4" width="4" height="16" fill="currentColor" /></svg>
)
export const ResetIcon = (p: IconProps) => <svg {...base(p)}><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" /></svg>
export const ChartIcon = (p: IconProps) => <svg {...base(p)}><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></svg>
export const DownloadIcon = (p: IconProps) => <svg {...base(p)}><path d="M12 3v12M7 10l5 5 5-5M5 21h14" /></svg>
export const SparkIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" fill="currentColor" stroke="none" /></svg>
)
export const AlertIcon = (p: IconProps) => <svg {...base(p)}><path d="M12 3l10 18H2z" /><path d="M12 10v4M12 18h.01" /></svg>
export const DropIcon = (p: IconProps) => <svg {...base(p)}><path d="M12 3c4 5 6 8 6 11a6 6 0 0 1-12 0c0-3 2-6 6-11z" /></svg>
export const GrassIcon = (p: IconProps) => <svg {...base(p)}><path d="M4 21c1-5 1-9 0-13M10 21c0-6 1-10 4-14M16 21c0-4 1-7 4-9" /></svg>
export const ShieldIcon = (p: IconProps) => <svg {...base(p)}><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /><path d="M8.5 12l2.5 2.5 4.5-5" /></svg>
export const ChatIcon = (p: IconProps) => <svg {...base(p)}><path d="M4 5h16v11H9l-5 4z" /></svg>
export const ListIcon = (p: IconProps) => <svg {...base(p)}><path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" /></svg>
export const BoltIcon = (p: IconProps) => <svg {...base(p)}><path d="M13 2L4 14h7l-1 8 9-12h-7z" /></svg>
export const FuelIcon = (p: IconProps) => <svg {...base(p)}><path d="M4 21V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v16M3 21h12M14 9h2l3 3v6a1.5 1.5 0 0 1-3 0v-3" /><path d="M7 8h4" /></svg>
export const CloseIcon = (p: IconProps) => <svg {...base(p)}><path d="M6 6l12 12M18 6L6 18" /></svg>
export const UploadIcon = (p: IconProps) => <svg {...base(p)}><path d="M12 21V9M7 14l5-5 5 5M5 3h14" /></svg>
export const MapIcon = (p: IconProps) => <svg {...base(p)}><path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z" /><path d="M9 4v14M15 6v14" /></svg>
export const TimelineIcon = (p: IconProps) => <svg {...base(p)}><path d="M4 6h9M8 12h11M5 18h7" /></svg>
export const ArrowRightIcon = (p: IconProps) => <svg {...base(p)}><path d="M4 12h15M13 6l6 6-6 6" /></svg>
export const FlowIcon = (p: IconProps) => <svg {...base(p)}><circle cx="5" cy="12" r="2.5" /><circle cx="19" cy="6" r="2.5" /><circle cx="19" cy="18" r="2.5" /><path d="M7.5 12h4l3-5h2M11.5 12l3 5h2" /></svg>
export const PlusIcon = (p: IconProps) => <svg {...base(p)}><path d="M12 5v14M5 12h14" /></svg>

export function JobTypeIcon({ type, size = 14, ...rest }: IconProps & { type: string }) {
  return type === 'mow' ? <GrassIcon size={size} {...rest} /> : <DropIcon size={size} {...rest} />
}
