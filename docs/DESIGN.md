# EV — Design

Expands `CLAUDE.md` §6 into an implementable system. `CLAUDE.md` wins on any conflict. Values
marked **(tune P2)** are starting points to be tuned in Phase 2 and then locked here.

## 1. Art direction: "quiet hardware"
EV is a physical object built into the screen. The island is pure black (`#000`) in every theme,
like a camera cutout. Depth comes from motion and blur, never from shadows, gradients or borders.
One accent color, used only for live states.

## 2. Tokens
Tokens are the only source of visual values. Components reference CSS custom properties; a lint
rule (Phase 2) rejects raw colors, lengths, durations and font names in component styles.

Files: `app/src/lib/tokens/base.css` (theme-independent), `app/src/lib/tokens/themes/minimal.css`
(light + dark). A new theme is one new file with zero component changes.

### 2.1 Island (fixed across themes)
| Token | Value |
|---|---|
| `--ev-island-bg` | `#000` |
| `--ev-island-fg-1` | `rgb(255 255 255 / 1)` |
| `--ev-island-fg-2` | `rgb(255 255 255 / 0.64)` |
| `--ev-island-fg-3` | `rgb(255 255 255 / 0.40)` |

### 2.2 Accent
Default: warm off-white glow (exact value chosen with the font specimen in Phase 2). Curated set of
6 user choices + "follow Windows accent". Used only for listening level and progress.

### 2.3 Typography
| Token | Value |
|---|---|
| `--ev-font-sans` | `"Instrument Sans"` (bundled variable font, OFL-1.1) |
| `--ev-font-mono` | `"Commit Mono"` (bundled, MIT) |
| `--ev-text-11/13/15/20/28` | 11, 13, 15, 20, 28 px |
| Weights | 400, 500, 600 only |
| Tracking | −1% at ≥ 20 px, 0 below |
| Numerals | `font-variant-numeric: tabular-nums` everywhere numbers appear |

Island uses 13 and 15 px only. Banned design fonts: Inter, Geist, Poppins, Roboto, Montserrat,
Open Sans, `system-ui`. Alternatives on file: Hanken Grotesk, Schibsted Grotesk. Final choice is
locked after the Phase 2 specimen (Windows, ClearType, 100/125/150% DPI) is approved by the user.

### 2.4 Shape
- Island corners: continuous squircle (superellipse) drawn as an SVG path / `clip-path`, never a
  plain `border-radius` on the island.
- Hairline: 1 px at 8% opacity of the foreground.

### 2.5 Motion
| Token | Value |
|---|---|
| `--ev-spring-default` | stiffness 400, damping 32, mass 1 **(tune P2)** |
| Reduced motion | cross-fade only, ≤ 150 ms |
| Animation strength | Full / Subtle / Reduced (scales spring displacement; Reduced = cross-fade) |

Rules: animate only `transform`, `opacity`, and `clip-path` where needed; never width, height, top
or left. Shape morph = one element morphing via `clip-path`/scale with content cross-fading above.
Every animation is interruptible and reverses from its current value without snapping. Respect the
Windows "Animation effects" setting.

## 3. Island states
| State | Shape | Content |
|---|---|---|
| `idle` | tiny pill, few px tall, low contrast | none |
| `hover` | slightly larger | hint text (13 px, fg-2) |
| `listening` | medium | live level / captions (accent) |
| `thinking` | medium | breathing / edge shimmer (no spinner) |
| `speaking` | medium | captions |
| `panel` | ~360 px wide | input, last reply, quick actions |
| `confirm` | medium | question + yes / no |

Every surface also designs: empty, loading, error, offline, permission denied, disabled.
Feedback lives in the island only — no toasts.

Exact geometry per state is defined in Phase 2. The Phase 0 spike uses `idle` ↔ `panel` only, to
measure frame times and click-through.

## 4. Icons
Custom EV set, ~30 icons, 20 px grid, 1.5 px stroke, rounded joins, stored as SVG in
`app/src/lib/icons/`. Banned: Lucide, Heroicons, Font Awesome, Material Icons, sparkle /
magic-wand / brain "AI" icons.

## 5. Earcons
wake, done, error; each < 300 ms, soft, non-musical; volume setting and off switch; silent under
Windows Focus / Do Not Disturb.

## 6. Settings window
Windows 11 layout: left nav, right content, Mica background, editorial typography, hairline
dividers, generous whitespace. Every setting: label, one-line description, default, instant apply,
reset to default. Sections per `CLAUDE.md` §6.5.

## 7. Review gate (every UI change)
- Screenshot or recording at 100% and 150% DPI, light and dark.
- Checked against the anti-slop list in `CLAUDE.md` §6.4.
- No hard-coded visual values (lint).
- Keyboard path, focus ring, screen-reader label and WCAG AA contrast verified.
