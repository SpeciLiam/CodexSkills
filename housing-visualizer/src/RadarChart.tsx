import { useRef, type CSSProperties } from "react";

/* ──────────────────────────────────────────────────────────────────────────
   RadarChart — a self-contained, interactive spider/radar chart (character-stats
   style). Pure SVG + inline styles, zero dependencies. Click anywhere along an
   axis to snap that axis to the nearest ring level (0..max) and fire onChange.

   Matches the housing-visualizer light theme: text #1c1a17, muted #8a8378,
   accent via CSS var(--accent) (#245ea8). Strict-TS clean.
   ────────────────────────────────────────────────────────────────────────── */

export type RadarAxis = { key: string; label: string };

export type RadarChartProps = {
  axes: RadarAxis[];
  values: Record<string, number>;
  onChange: (key: string, v: number) => void;
  color?: string;
  size?: number;
  max?: number;
};

const TEXT = "#1c1a17";
const MUTED = "#8a8378";
const GRID = "#e0dacd";
const GRID_FAINT = "#ece8df";

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

// Angle for axis i: start at 12 o'clock (-90°) and go clockwise.
const angleFor = (i: number, n: number) => -Math.PI / 2 + (i * 2 * Math.PI) / n;

const polar = (cx: number, cy: number, r: number, ang: number) => ({
  x: cx + r * Math.cos(ang),
  y: cy + r * Math.sin(ang),
});

export default function RadarChart({
  axes,
  values,
  onChange,
  color = "var(--accent)",
  size = 420,
  max = 10,
}: RadarChartProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);

  const n = Math.max(1, axes.length);
  const rings = Math.max(1, Math.round(max));

  // Reserve room outside the outer ring for axis labels. Label gutter scales a
  // little with size so it stays readable from ~360px to ~520px.
  const labelGutter = clamp(size * 0.17, 54, 96);
  const pad = 10;
  const cx = size / 2;
  const cy = size / 2;
  const radius = Math.max(20, size / 2 - labelGutter - pad);

  const ringRadius = (level: number) => (radius * level) / rings;
  const valueAt = (key: string) => clamp(Math.round(values[key] ?? 0), 0, rings);

  // ── Click → which axis + which ring ────────────────────────────────────────
  const handleClick = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    // Map the DOM click point into the SVG's own (viewBox) coordinate space.
    const px = ((e.clientX - rect.left) / rect.width) * size;
    const py = ((e.clientY - rect.top) / rect.height) * size;

    const dx = px - cx;
    const dy = py - cy;
    const dist = Math.hypot(dx, dy);

    // Snap angle → nearest axis. Atan2 gives the same orientation we draw with
    // (0 = +x / 3 o'clock, clockwise positive because SVG y grows downward).
    const clickAng = Math.atan2(dy, dx);
    let bestAxis = 0;
    let bestDelta = Infinity;
    for (let i = 0; i < n; i++) {
      const a = angleFor(i, n);
      // Smallest absolute angular difference, wrapped to [0, π]. JS % is a SIGNED
      // remainder, so normalize (clickAng - a + π) into [0, 2π) before subtracting π;
      // otherwise negative diffs inflate d past π and snap the click to the wrong axis.
      const m = (((clickAng - a + Math.PI) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
      const d = Math.abs(m - Math.PI);
      if (d < bestDelta) {
        bestDelta = d;
        bestAxis = i;
      }
    }

    // Snap radius → nearest ring level (0..rings). A click near the center snaps
    // to 0; beyond the outer ring snaps to max.
    const level = clamp(Math.round((dist / radius) * rings), 0, rings);

    const axis = axes[bestAxis];
    if (axis) onChange(axis.key, level);
  };

  // ── Geometry ───────────────────────────────────────────────────────────────
  const axisEnds = axes.map((_, i) => polar(cx, cy, radius, angleFor(i, n)));

  // Concentric ring polygons (level 1..rings).
  const ringPolys: { level: number; points: string }[] = [];
  for (let level = 1; level <= rings; level++) {
    const r = ringRadius(level);
    const pts = axes
      .map((_, i) => {
        const p = polar(cx, cy, r, angleFor(i, n));
        return `${p.x.toFixed(2)},${p.y.toFixed(2)}`;
      })
      .join(" ");
    ringPolys.push({ level, points: pts });
  }

  // Value polygon + dots.
  const valuePts = axes.map((ax, i) => {
    const v = valueAt(ax.key);
    return polar(cx, cy, ringRadius(v), angleFor(i, n));
  });
  const valuePolygon = valuePts.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");

  // Fill at ~18% opacity. color-mix handles CSS vars (var(--accent)); for a plain
  // hex/rgb it works too. SVG fill-opacity gives a robust fallback regardless.
  const fill = `color-mix(in srgb, ${color} 18%, transparent)`;

  // Ring labels along the upward (12 o'clock) axis, just left of it.
  const ringLabelX = cx - 6;

  const dotR = clamp(size * 0.013, 4.5, 7);

  const wrap: CSSProperties = {
    width: size,
    maxWidth: "100%",
    userSelect: "none",
    WebkitUserSelect: "none",
  };

  return (
    <div style={wrap}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${size} ${size}`}
        width="100%"
        role="img"
        aria-label="Editable stats radar chart"
        onClick={handleClick}
        style={{ display: "block", cursor: "pointer", touchAction: "manipulation" }}
      >
        {/* faint ring polygons */}
        {ringPolys.map((rp) => (
          <polygon
            key={`ring-${rp.level}`}
            points={rp.points}
            fill="none"
            stroke={rp.level === rings ? GRID : GRID_FAINT}
            strokeWidth={rp.level === rings ? 1.4 : 1}
          />
        ))}

        {/* spokes */}
        {axisEnds.map((p, i) => (
          <line
            key={`spoke-${i}`}
            x1={cx}
            y1={cy}
            x2={p.x}
            y2={p.y}
            stroke={GRID}
            strokeWidth={1}
          />
        ))}

        {/* ring level labels (0..max) up the 12-o'clock axis */}
        {Array.from({ length: rings + 1 }, (_, level) => (
          <text
            key={`rlabel-${level}`}
            x={ringLabelX}
            y={cy - ringRadius(level)}
            textAnchor="end"
            dominantBaseline="middle"
            fontSize={clamp(size * 0.026, 8.5, 11)}
            fontFamily="'JetBrains Mono', ui-monospace, monospace"
            fill={MUTED}
            style={{ pointerEvents: "none" }}
          >
            {level}
          </text>
        ))}

        {/* value polygon */}
        <polygon
          points={valuePolygon}
          fill={fill}
          fillOpacity={0.18}
          stroke={color}
          strokeWidth={2}
          strokeLinejoin="round"
          style={{ pointerEvents: "none" }}
        />

        {/* draggable/clickable value dots */}
        {valuePts.map((p, i) => {
          const ax = axes[i];
          if (!ax) return null;
          return (
            <circle
              key={`dot-${ax.key}`}
              cx={p.x}
              cy={p.y}
              r={dotR}
              fill={color}
              stroke="#fffdf8"
              strokeWidth={2}
              style={{ pointerEvents: "none" }}
            />
          );
        })}

        {/* axis labels just outside the outer ring */}
        {axes.map((ax, i) => {
          const ang = angleFor(i, n);
          const lp = polar(cx, cy, radius + clamp(size * 0.035, 12, 20), ang);
          const cos = Math.cos(ang);
          // Anchor by horizontal position so labels splay outward, not overlap.
          const anchor: "start" | "middle" | "end" =
            cos > 0.25 ? "start" : cos < -0.25 ? "end" : "middle";
          // Nudge vertical baseline so top/bottom labels clear the ring.
          const sin = Math.sin(ang);
          const baseline: "auto" | "hanging" | "middle" =
            sin < -0.5 ? "auto" : sin > 0.5 ? "hanging" : "middle";
          return (
            <text
              key={`alabel-${ax.key}`}
              x={lp.x}
              y={lp.y}
              textAnchor={anchor}
              dominantBaseline={baseline}
              fontSize={clamp(size * 0.03, 10, 13)}
              fontFamily="'Space Grotesk', system-ui, sans-serif"
              fontWeight={600}
              fill={TEXT}
              style={{ pointerEvents: "none" }}
            >
              {ax.label}
            </text>
          );
        })}
      </svg>
    </div>
  );
}
