import { useMemo, type ReactNode } from 'react'

function makeRnd(seed: number) {
  let s = seed | 0
  return () => {
    s = (s * 9301 + 49297) % 233280
    return s / 233280
  }
}

export function Logo({ size = 22 }: { size?: number }) {
  return (
    <span className="middle" style={{ gap: 0 }}>
      <span className="serif-italic" style={{ fontSize: size, lineHeight: 1, letterSpacing: '-0.01em' }}>betto</span>
      <span className="c-acc" style={{ fontSize: size, lineHeight: 1, marginLeft: 1 }}>.</span>
    </span>
  )
}

export function Status({ kind = 'ok', children }: { kind?: string; children: ReactNode }) {
  return (
    <span className="middle" style={{ gap: 6, fontSize: 12, color: 'var(--ink-2)' }}>
      <span className={`dot ${kind}`} />
      <span>{children}</span>
    </span>
  )
}

export function Spark({ w = 240, h = 70, seed = 7, model = false, modelOffset = 0.10, grid = false, axis = false, area = true }: {
  w?: number; h?: number; seed?: number; model?: boolean; modelOffset?: number; grid?: boolean; axis?: boolean; area?: boolean
}) {
  const paths = useMemo(() => {
    const r = makeRnd(seed)
    const n = 48
    const mkt: [number, number][] = []
    let v = 0.45 + (r() - 0.5) * 0.1
    for (let i = 0; i < n; i++) {
      v += (r() - 0.5) * 0.08
      v = Math.max(0.10, Math.min(0.90, v))
      mkt.push([(i / (n - 1)) * w, h - v * h])
    }
    const d = mkt.map((p, i) => (i === 0 ? `M${p[0].toFixed(2)},${p[1].toFixed(2)}` : `L${p[0].toFixed(2)},${p[1].toFixed(2)}`)).join(' ')
    const fill = d + ` L${w},${h} L0,${h} Z`

    const r2 = makeRnd(seed + 257)
    const m: [number, number][] = []
    let mv = 0.5 + (r2() - 0.5) * 0.06
    for (let i = 0; i < n; i++) {
      mv += (r2() - 0.5) * 0.035
      mv = Math.max(0.15, Math.min(0.85, mv))
      m.push([(i / (n - 1)) * w, h - Math.min(0.95, Math.max(0.05, mv + modelOffset)) * h])
    }
    const md = m.map((p, i) => (i === 0 ? `M${p[0].toFixed(2)},${p[1].toFixed(2)}` : `L${p[0].toFixed(2)},${p[1].toFixed(2)}`)).join(' ')
    return { d, fill, md }
  }, [w, h, seed, modelOffset])

  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      {grid && (
        <g>
          <line className="grid" x1="0" x2={w} y1={h * 0.25} y2={h * 0.25} />
          <line className="grid" x1="0" x2={w} y1={h * 0.5} y2={h * 0.5} />
          <line className="grid" x1="0" x2={w} y1={h * 0.75} y2={h * 0.75} />
        </g>
      )}
      {axis && <line className="axis" x1="0" x2={w} y1={h - 0.5} y2={h - 0.5} />}
      {area && <path className="area" d={paths.fill} />}
      <path className="line" d={paths.d} />
      {model && <path className="model-line" d={paths.md} />}
    </svg>
  )
}

export function Equity({ w = 600, h = 220, seed = 9, points = 100, drawdown = false }: {
  w?: number; h?: number; seed?: number; points?: number; drawdown?: boolean; color?: string
}) {
  const path = useMemo(() => {
    const r = makeRnd(seed)
    const pts: [number, number][] = []
    let v = 0.35
    for (let i = 0; i < points; i++) {
      v += (r() - 0.42) * 0.04
      if (drawdown && i > points * 0.62 && i < points * 0.76) v -= 0.02
      v = Math.max(0.06, Math.min(0.92, v))
      pts.push([(i / (points - 1)) * w, h - v * h])
    }
    return {
      d: pts.map((p, i) => (i === 0 ? `M${p[0].toFixed(2)},${p[1].toFixed(2)}` : `L${p[0].toFixed(2)},${p[1].toFixed(2)}`)).join(' '),
      fill: pts.map((p, i) => (i === 0 ? `M${p[0].toFixed(2)},${p[1].toFixed(2)}` : `L${p[0].toFixed(2)},${p[1].toFixed(2)}`)).join(' ') + ` L${w},${h} L0,${h} Z`,
      last: pts[pts.length - 1],
    }
  }, [w, h, seed, points, drawdown])

  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <line className="grid" x1="0" x2={w} y1={h * 0.5} y2={h * 0.5} />
      <line className="grid" x1="0" x2={w} y1={h * 0.25} y2={h * 0.25} />
      <line className="grid" x1="0" x2={w} y1={h * 0.75} y2={h * 0.75} />
      <path d={path.fill} fill="rgba(122, 168, 107, 0.08)" stroke="none" />
      <path d={path.d} fill="none" stroke="var(--pos)" strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={path.last[0]} cy={path.last[1]} r="2.6" fill="var(--pos)" />
    </svg>
  )
}

export function KellyTrace({ rows, max }: { rows: { label: string; value: number; applied: boolean }[]; max: number }) {
  return (
    <div className="col" style={{ gap: 10 }}>
      {rows.map((r, i) => (
        <div key={i} className="col" style={{ gap: 4 }}>
          <div className="between">
            <span style={{ fontSize: 12, color: r.applied ? 'var(--ink)' : 'var(--muted)' }}>{r.label}</span>
            <span className="num" style={{ fontSize: 12, color: r.applied ? 'var(--acc)' : 'var(--ink-2)' }}>
              {(r.value * 100).toFixed(2)}%
            </span>
          </div>
          <div className="bar">
            <i className={r.applied ? 'acc' : ''} style={{ width: `${Math.min(100, (r.value / max) * 100)}%`, opacity: r.applied ? 1 : 0.55 }} />
          </div>
        </div>
      ))}
    </div>
  )
}

export function FeatureWaterfall({ rows, max = 0.05 }: { rows: { label: string; value: number }[]; max?: number }) {
  return (
    <div className="col" style={{ gap: 7 }}>
      {rows.map((r, i) => {
        const pct = Math.min(1, Math.abs(r.value) / max)
        return (
          <div key={i} className="row" style={{ alignItems: 'center', gap: 8 }}>
            <span style={{ flex: '1 1 auto', fontSize: 12, color: 'var(--ink-2)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.label}</span>
            <div style={{ position: 'relative', width: 110, height: 8, background: 'var(--surf-3)', borderRadius: 2 }}>
              <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: 'var(--border-2)' }} />
              <div style={{
                position: 'absolute',
                top: 0, bottom: 0,
                left: r.value >= 0 ? '50%' : `${50 - pct * 50}%`,
                width: `${pct * 50}%`,
                background: r.value >= 0 ? 'var(--pos)' : 'var(--neg)',
                borderRadius: 1,
              }} />
            </div>
            <span className="num" style={{ width: 50, textAlign: 'right', fontSize: 11.5, color: r.value >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
              {(r.value >= 0 ? '+' : '') + r.value.toFixed(3)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export function Calibration({ w = 240, h = 240 }: { w?: number; h?: number }) {
  const dots = useMemo(() => {
    const r = makeRnd(42)
    const arr: [number, number, number][] = []
    for (let i = 0; i < 10; i++) {
      const x = (i + 0.5) / 10
      const noise = (r() - 0.5) * 0.07
      const bias = x > 0.65 ? -0.02 : 0
      const y = Math.max(0.02, Math.min(0.98, x + noise + bias))
      const radius = 3 + r() * 4
      arr.push([x * w, h - y * h, radius])
    }
    return arr
  }, [w, h])

  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      {[0.25, 0.5, 0.75].map((t) => (
        <g key={t}>
          <line className="grid" x1="0" x2={w} y1={h * t} y2={h * t} />
          <line className="grid" x1={w * t} x2={w * t} y1="0" y2={h} />
        </g>
      ))}
      <line className="axis" x1="0" x2={w} y1={h - 0.5} y2={h - 0.5} />
      <line className="axis" x1="0.5" x2="0.5" y1="0" y2={h} />
      <line x1="0" y1={h} x2={w} y2="0" stroke="var(--dim)" strokeWidth="1" strokeDasharray="3 4" />
      {dots.map((d, i) => (
        <g key={i}>
          <circle cx={d[0]} cy={d[1]} r={d[2]} fill="var(--acc)" opacity="0.85" />
          <circle cx={d[0]} cy={d[1]} r={d[2]} fill="none" stroke="var(--acc)" strokeWidth="1" />
        </g>
      ))}
    </svg>
  )
}

export function Histogram({ w = 320, h = 80, seed = 5, bins = 22 }: { w?: number; h?: number; seed?: number; bins?: number }) {
  const bars = useMemo(() => {
    const r = makeRnd(seed)
    const arr: number[] = []
    const center = bins / 2 + 1
    for (let i = 0; i < bins; i++) {
      const dist = Math.abs(i - center)
      const base = Math.exp(-(dist * dist) / 20) * 0.9
      const v = Math.max(0.05, Math.min(1, base + (r() - 0.5) * 0.25))
      arr.push(v)
    }
    return arr
  }, [seed, bins])

  const barW = w / bins
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <line className="axis" x1="0" x2={w} y1={h - 0.5} y2={h - 0.5} />
      <line className="axis" x1={w / 2} x2={w / 2} y1="0" y2={h} strokeDasharray="3 4" stroke="var(--dim)" />
      {bars.map((v, i) => (
        <rect
          key={i}
          x={i * barW + 1}
          y={h - v * (h - 4)}
          width={barW - 2}
          height={v * (h - 4)}
          fill={i < bins / 2 ? 'var(--neg)' : 'var(--pos)'}
          opacity={i < bins / 2 ? 0.55 : 0.85}
        />
      ))}
    </svg>
  )
}
