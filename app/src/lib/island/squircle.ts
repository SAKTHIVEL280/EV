/**
 * Continuous-corner rectangle (superellipse corners) as an SVG path string,
 * for `clip-path: path(...)`. The point count is fixed, so consecutive shapes
 * interpolate cleanly frame to frame.
 */
const POINTS_PER_CORNER = 10;

export function squirclePath(
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
  exponent: number,
): string {
  const r = Math.max(0, Math.min(radius, width / 2, height / 2));
  const corners: [number, number, number][] = [
    // center x, center y, start angle (radians); clockwise from top-right.
    [x + width - r, y + r, -Math.PI / 2],
    [x + width - r, y + height - r, 0],
    [x + r, y + height - r, Math.PI / 2],
    [x + r, y + r, Math.PI],
  ];
  const parts: string[] = [];
  for (const [cx, cy, start] of corners) {
    for (let i = 0; i <= POINTS_PER_CORNER; i += 1) {
      const t = start + (i / POINTS_PER_CORNER) * (Math.PI / 2);
      const cos = Math.cos(t);
      const sin = Math.sin(t);
      const px = cx + r * Math.sign(cos) * Math.abs(cos) ** (2 / exponent);
      const py = cy + r * Math.sign(sin) * Math.abs(sin) ** (2 / exponent);
      parts.push(`${parts.length === 0 ? "M" : "L"}${px.toFixed(2)} ${py.toFixed(2)}`);
    }
  }
  return `${parts.join(" ")} Z`;
}
