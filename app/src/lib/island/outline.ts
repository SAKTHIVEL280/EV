/**
 * The island outline: a drop of liquid hanging from the top edge of the
 * screen (docs/DESIGN.md §2.4). The body has continuous (superellipse) bottom
 * corners; where it meets the edge, concave fillets ("the neck") curve it into
 * the edge like water held by surface tension. Every size, from the idle bead
 * to the open panel, is the same outline, so one shape morphs through all.
 *
 * The point count is fixed, so consecutive frames interpolate cleanly. The
 * outline starts above y = 0 so a stroke (the rim) never shows along the
 * screen edge itself.
 */
export interface Drop {
  /** Horizontal center, px. */
  cx: number;
  /** Body width, without the neck, px. */
  width: number;
  /** Body height from the top edge, px. */
  height: number;
  /** Bottom corner radius, px. */
  radius: number;
  /** Neck fillet radius, px. */
  neck: number;
  /** Superellipse exponent for the bottom corners (2 = circle). */
  exponent: number;
}

const POINTS_PER_CURVE = 10;
/** The closing edge runs this far above the window so the rim stroke stays hidden. */
const OVERSCAN = 2;

/** Radii clamped so the outline is always valid, whatever the spring values. */
export function fitted(drop: Drop): Drop {
  const width = Math.max(drop.width, 0);
  const height = Math.max(drop.height, 0);
  const neck = Math.max(0, Math.min(drop.neck, height / 2));
  const radius = Math.max(0, Math.min(drop.radius, width / 2, height - neck));
  return { ...drop, width, height, neck, radius };
}

function arc(
  cx: number,
  cy: number,
  r: number,
  from: number,
  to: number,
  exponent: number,
): [number, number][] {
  const out: [number, number][] = [];
  for (let i = 0; i <= POINTS_PER_CURVE; i += 1) {
    const t = from + ((to - from) * i) / POINTS_PER_CURVE;
    const cos = Math.cos(t);
    const sin = Math.sin(t);
    out.push([
      cx + r * Math.sign(cos) * Math.abs(cos) ** (2 / exponent),
      cy + r * Math.sign(sin) * Math.abs(sin) ** (2 / exponent),
    ]);
  }
  return out;
}

export function dropletPoints(input: Drop): [number, number][] {
  const { cx, width, height, radius: r, neck: f, exponent } = fitted(input);
  const x0 = cx - width / 2;
  const x1 = cx + width / 2;
  const q = Math.PI / 2;
  return [
    [x0 - f, -OVERSCAN],
    // Left neck: concave, from the edge down into the body's side.
    ...arc(x0 - f, f, f, -q, 0, 2),
    // Bottom-left corner, then bottom-right (y grows downward).
    ...arc(x0 + r, height - r, r, Math.PI, q, exponent),
    ...arc(x1 - r, height - r, r, q, 0, exponent),
    // Right neck back up to the edge.
    ...arc(x1 + f, f, f, Math.PI, Math.PI + q, 2),
    [x1 + f, -OVERSCAN],
  ];
}

export function dropletPath(drop: Drop): string {
  const parts = dropletPoints(drop).map(
    ([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`,
  );
  return `${parts.join(" ")} Z`;
}

/** Bounding box of the visible outline (neck included), rounded outward. */
export function dropletBounds(drop: Drop): { x: number; y: number; width: number; height: number } {
  const { cx, width, height, neck } = fitted(drop);
  const left = Math.floor(cx - width / 2 - neck);
  const right = Math.ceil(cx + width / 2 + neck);
  return { x: left, y: 0, width: right - left, height: Math.ceil(height) };
}
