---
name: procedural-motion-and-sound
description: How to build animated films, trailers, hype reels, title sequences, kinetic typography, motion graphics, explainer animations, data-driven stories, music visualizers, generative art and any other time-based audiovisual piece entirely from code in the browser (Canvas 2D, Web Audio, plus SVG/CSS/WebGL when appropriate), with zero video files, zero image assets and zero audio samples. Use this skill whenever the user asks for a "video", "film", "trailer", "animation", "hype edit", "intro", "motion piece", "visual with sound", "synced to music", "something cinematic", or an interactive/generative experience with timing, sound or effects, and no video-editing tool is available. Also use it when the user wants procedurally generated music or sound effects, beat-synced visuals, screen-shake/glitch/chromatic-aberration style effects, or wants to know how such pieces are made. Use it even if the user never says "JavaScript" or "canvas".
---

# Procedural Motion & Sound

Build time-based audiovisual pieces (films, trailers, animations, visualizers, interactive experiences) as **programs**. The piece is not a rendered file. It is code that draws every frame and synthesizes every sound at playback time.

This document is written for a model that has not done this before. It explains the mental model, the architecture, the craft, the traps, and how to verify work you cannot see. Read sections 1-4 before writing any code. Use the rest as reference.

## Table of contents

1. [The mental model](#1-the-mental-model)
2. [Decide: is this the right approach, and which tech](#2-decide-is-this-the-right-approach-and-which-tech)
3. [Workflow: from brief to shipped piece](#3-workflow-from-brief-to-shipped-piece)
4. [Architecture (the engine)](#4-architecture-the-engine)
5. [Time and animation primitives](#5-time-and-animation-primitives)
6. [Drawing toolkit](#6-drawing-toolkit)
7. [Post-processing and screen effects](#7-post-processing-and-screen-effects)
8. [Sound design and music synthesis](#8-sound-design-and-music-synthesis)
9. [Syncing picture and sound](#9-syncing-picture-and-sound)
10. [Pacing, storytelling and creative direction](#10-pacing-storytelling-and-creative-direction)
11. [Visual design rules](#11-visual-design-rules)
12. [Player shell: controls, gating, accessibility](#12-player-shell-controls-gating-accessibility)
13. [Other kinds of pieces (variants)](#13-other-kinds-of-pieces-variants)
14. [Libraries: when to use, when not to](#14-libraries-when-to-use-when-not-to)
15. [Exporting to a real video file](#15-exporting-to-a-real-video-file)
16. [Verifying work you cannot watch](#16-verifying-work-you-cannot-watch)
17. [Known traps and their fixes](#17-known-traps-and-their-fixes)
18. [Performance budget](#18-performance-budget)
19. [Content, legal and honesty rules](#19-content-legal-and-honesty-rules)
20. [Delivery](#20-delivery)
- [Appendix A: minimal complete engine](#appendix-a-minimal-complete-engine)
- [Appendix B: effect and scene recipes](#appendix-b-effect-and-scene-recipes)
- [Appendix C: reference tables](#appendix-c-reference-tables)
- [Appendix D: final checklist](#appendix-d-final-checklist)

---

## 1. The mental model

Hold these five ideas. Everything else follows.

**1. A frame is a pure function of time.** `render(T)` draws the entire picture for time `T` seconds. It reads `T` and constants, and nothing else. It does not remember the previous frame. Consequences: you can pause, replay, scrub, export frame-by-frame, and never get drift or accumulated bugs. If you catch yourself writing `x += speed` per frame, stop and write `x = x0 + speed * T` instead.

**2. One master clock.** There is exactly one source of truth for "what time is it in the piece". If the piece has sound, that clock is the **audio clock** (`AudioContext.currentTime`), because audio cannot be slowed or skipped and the eye will follow it. Visuals read the clock; they never advance it. If the piece has no sound, use `performance.now()`.

**3. Sound is scheduled, not played.** Web Audio lets you say "start this oscillator at exactly 12.4 seconds from the base time". You schedule the whole soundtrack up front (or in short look-ahead chunks) and the audio thread executes it with sample-accurate timing. You do not trigger sounds from the animation loop.

**4. Scenes are time ranges.** A piece is a list of scenes with `start` and `end`. Each scene draws with a *local* time `t = T - start`. Scene code is written in local time so it can be reordered and retimed by changing one number.

**5. Effects are global flags, applied last.** Scenes draw clean images into an off-screen buffer and set effect intensities (shake, flash, glitch, aberration, zoom). A single post-process step applies them when copying the buffer to the visible canvas. Scenes never draw effects directly onto the screen.

**What you can and cannot promise.** You can produce a piece that plays in a browser, looks and sounds the way the code describes, and is deterministic. You usually cannot *see or hear* it while building (see section 16). You can produce a downloadable video only through the routes in section 15.

---

## 2. Decide: is this the right approach, and which tech

### 2.1 When this approach is right

Use it when the user wants any of: an animated film/trailer/hype piece; motion graphics or kinetic type; an explainer or data story with timing; a music-synced visualizer; procedural art; an interactive or game-like showcase; a "video" and you have no video editor, no image generator, no network, or the user wants something shareable as a link.

### 2.2 When it is not

- User needs a photoreal or live-action video: say so; offer a storyboard, script, shot list, or an animated motion-graphics alternative.
- User needs a specific MP4 with a specific real song or footage: you cannot license or embed those. Offer a synthesized original soundtrack, and the export routes in section 15.
- The request is a static image or a document: use a different skill.

### 2.3 Choosing the rendering technology

| Need | Use | Why |
|---|---|---|
| Frame-by-frame drawn film, text, shapes, particles, effects, post-processing | **Canvas 2D** (default) | Full control per frame, deterministic, works everywhere, easiest to composite effects |
| Crisp resolution-independent diagrams, few moving parts, DOM accessibility | **SVG + CSS/WAAPI** | Vector, selectable text, easy styling, low code for simple motion |
| UI-like motion (cards, transitions, hover, page reveals) | **CSS animations / Web Animations API** | Declarative, GPU-composited |
| 3D scenes, huge particle counts, shader effects | **WebGL** (raw, or three.js if allowed) | GPU; but much more code and harder to verify blind |
| Sound of any kind | **Web Audio API** | Synthesis, scheduling, effects, analysis |
| Reading pre-recorded audio/video files the user supplied | `<audio>`/`<video>` + Web Audio | Only if the user provides assets |

Default to **Canvas 2D + Web Audio** in one HTML file. It is the most controllable and the easiest to reason about without seeing the result. Choose others only for a stated reason.

### 2.4 Environment checklist (check before you build)

Answer each. Wrong assumptions here cause silent failures.

- **Where will it run?** A hosted page in a sandbox, a local file, a chat preview, a phone? Sandboxes may block network requests, storage, or external scripts. If the environment states a content-security policy, obey it exactly. Typical allowances: scripts from a few CDNs, stylesheets and fonts from Google Fonts only. Everything else (remote images, arbitrary `fetch`) is blocked, and it fails silently.
- **Is there network at build time?** If not, you cannot `npm install`. Prefer zero-dependency code. Everything in this skill works with zero dependencies.
- **Is browser storage allowed?** Do not assume `localStorage`. Wrap in try/catch or avoid it. A film does not need it.
- **Autoplay policy.** Browsers block audio until a user gesture. You need a "Play" gate (section 12). Never design a piece that expects sound to start on page load.
- **Fonts.** If web fonts may fail to load, always give a fallback stack that produces acceptable layout (`'Anton','Impact','Arial Narrow',sans-serif`). Canvas draws with whatever is loaded *at draw time*; it will not reflow later (see trap 17.7).
- **Viewport.** Assume anything from a phone to a 4K TV. Use a fixed virtual resolution and letterbox (section 4.2).

---

## 3. Workflow: from brief to shipped piece

Do these phases in order. Do not start coding at phase 1.

### Phase 1: Interpret the brief

Extract, in writing (for yourself):

1. **Subject and message.** What is this about, and what should the viewer feel at the end?
2. **Fixed content.** Lines, names, facts, order the user gave you. **Use user-provided lines verbatim.** Bracketed text like `[Artificial General Intelligence]` is a title-card cue. "Flash quickly through X, Y and Z" is a montage cue (fast, rhythmic, accelerating). "No one could have ever expected..." followed by an ellipsis is a *pause* cue (silence, hold, then release).
3. **Creative latitude.** "Be creative / assume creative freedom" means: the user wants inventive devices you choose (section 10.6), not a literal slideshow. Spend the freedom on **two or three big ideas**, not on decorating everything.
4. **Constraints.** Length, aspect, sound on/off, audience, tone (epic, funny, calm, corporate).
5. **Unknowns.** Pick sensible defaults rather than asking. Ask at most one question, and only if the answer would change the whole approach (for example, "do you need an MP4 file?").

### Phase 2: Write the treatment (a short paragraph)

One paragraph: the arc, the tone, the palette progression, the main creative devices, the sound approach. Example shape: "Cold, grey, caged demos (act 1) give way to a warm, exploding, golden network (act 3). One recurring motif (the network) evolves across the whole piece. Silence right before the reveal. Montage at 128 BPM."

### Phase 3: Build a shot list with timestamps

A table, before code. Columns: `#`, `start`, `end`, `what is on screen`, `text`, `sound`, `effect flags`. Fix total duration. Check sums (section 9.4). This table becomes the `TS` constants and the audio schedule. Retiming later is then a one-line change.

Duration heuristics:
- Simple hype/teaser: 30-60 s. Trailer/story: 60-120 s. Beyond 2 min you must earn attention with variety.
- Do not pad. A piece should feel slightly too short.

### Phase 4: Decide the architecture

Section 4. Fix the virtual resolution, scene list, clock, audio approach, effects list.

### Phase 5: Build in this order (each step verified before the next)

1. Shell: canvas, resize, virtual-resolution letterbox, play gate, loop, master clock, progress bar. Draw a test pattern with the time printed.
2. Primitives: math helpers, text helpers, easing, RNG.
3. Post-processing: shake, flash, aberration, vignette, grain (so every scene benefits).
4. Scenes, **one at a time**, each with its own local timeline. Start with the most important scene (the reveal or the hook).
5. Audio: master chain, voice primitives, then schedule music per scene, then hit points (impacts on cuts).
6. Sync pass: line up every impact with its visual moment.
7. Polish pass: transitions between scenes, ends, edge cases (pause, replay, resize).
8. Verify (section 16), then deliver (section 20).

### Phase 6: Review as a director

Ask: Is the first 3 seconds a hook? Does every scene earn its time? Is there contrast (quiet vs loud, small vs huge, cold vs warm)? Is the ending a payoff? Cut anything that does not serve the message.

---

## 4. Architecture (the engine)

### 4.1 File layout

Single self-contained `.html` file, unless the user needs otherwise:

```
<style>      page shell (black bg, canvas fills, gate + controls)
<canvas>     the visible canvas
<script>
  constants     W, H, timeline TS, palette, font stacks
  utilities     clamp, lerp, seg, ease, rng, color helpers
  text/shape helpers
  effect state  fx = {shake, flash, ab, glitch, zoom}
  scenes        one function per scene: (t) => draw into g
  post          renderScene(T), present()
  audio         buildAudio(), voices, drums, schedule()
  player        play/pause/mute/fullscreen/restart, loop
</script>
```

Wrap everything in an IIFE `(() => { ... })();` so nothing leaks to `window`.

### 4.2 Virtual resolution and letterboxing

Design in a fixed coordinate space, for example `W = 1600, H = 900` (16:9). Every coordinate in your scenes uses it. This makes layouts identical on every device.

- Draw scenes into an **off-screen buffer** canvas of exactly `W x H` (`buf`, context `g`).
- The visible canvas is sized to its CSS box times `devicePixelRatio` (capped at 2).
- `present()` scales the buffer to fit, centered, with black bars (letterbox).

```js
const s = Math.min(cw / W, ch / H);          // uniform scale
const dw = W * s, dh = H * s;
const dx = (cw - dw) / 2, dy = (ch - dh) / 2;
ctx.fillStyle = '#000'; ctx.fillRect(0, 0, cw, ch);
ctx.drawImage(buf, dx, dy, dw, dh);
```

Lower virtual resolution = faster. 1600x900 is a good default; use 1280x720 for heavy effects, 1920x1080 only if the piece is light. For portrait/vertical pieces (phones, social), set `W = 900, H = 1600` and design for it; do not try to make one layout serve both.

### 4.3 The render loop

```js
function loop() {
  requestAnimationFrame(loop);
  const T = getT();          // master clock (audio clock if playing)
  renderScene(T);            // draw into buf using fx flags
  present();                 // copy to screen, applying post effects
}
```

`renderScene(T)` resets `fx`, clears the buffer to opaque black, picks the scene by `T`, calls it with local time, then applies buffer-level post (glitch slices, vignette, grain, flash).

### 4.4 Scene registry

```js
const TS = { intro: 0, act1: 4, act2: 15, finale: 30, end: 40 };   // start times, seconds
// in renderScene:
if (T < TS.act1) intro(T - TS.intro);
else if (T < TS.act2) act1(T - TS.act1);
...
```

Rules:
- Scenes are contiguous. Every `T` in `[0, end]` belongs to exactly one scene. No gaps (a gap draws black by accident).
- Each scene handles **its own fade-in and fade-out** at the boundaries, or you crossfade in a transition helper (section 5.5).
- Keep scene code in local time so a scene can be moved.
- After `TS.end`, hold the last frame or show an end card. Do not crash and do not loop unless asked.

### 4.5 The effect state object

```js
const fx = { shake: 0, flash: 0, ab: 0, glitch: 0, zoom: 1 };
```

Reset to zero at the top of each frame. Scenes raise values with `Math.max(fx.shake, ...)` so overlapping triggers do not cancel. `present()` reads them. Section 7 shows each effect.

### 4.6 Player state

Track `started`, `paused`, `ended`. Replay must create a **new** `AudioContext` (scheduled nodes cannot be cancelled cleanly) and close the old one. Pause with `AC.suspend()`/`AC.resume()`, which freezes `currentTime` and therefore the piece.

---

## 5. Time and animation primitives

Put these at the top of every piece. They are tiny and they are the entire animation vocabulary.

```js
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp  = (a, b, t) => a + (b - a) * t;
const seg   = (t, a, b) => clamp((t - a) / (b - a));     // progress of t through [a,b]
const env   = (t, a, b, c, d) => seg(t, a, b) * (1 - seg(t, c, d)); // fade in [a,b], hold, fade out [c,d]
const ease = {
  out3:  t => 1 - Math.pow(1 - t, 3),            // fast start, soft landing (default for entrances)
  in3:   t => t * t * t,                          // slow start, fast end (exits, collapses)
  io:    t => t < .5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3) / 2,
  outExp:t => t >= 1 ? 1 : 1 - Math.pow(2, -10 * t),  // snappy "slam" landing
  outBack: t => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3*Math.pow(t-1,3) + c1*Math.pow(t-1,2); }, // overshoot
  spring: (t, k = 8, d = 4) => 1 - Math.exp(-d * t) * Math.cos(k * t),   // damped spring, t in seconds
};
```

### 5.1 `seg` is the workhorse

`seg(t, a, b)` returns 0 before `a`, 1 after `b`, linear between. Nearly every animation is `ease(seg(t, start, end))` fed into a `lerp`, an alpha, a scale, or a length.

```js
const p = ease.out3(seg(t, 1.0, 1.6));     // 0 -> 1 over 0.6 s starting at 1.0 s
alpha  = p;
y      = lerp(startY, endY, p);
```

### 5.2 Determinism and randomness

Never call `Math.random()` for anything that must look the same every playthrough (layouts, positions, colors, glitch slices). Use a seeded generator:

```js
function rng(seed) {                      // mulberry32
  return () => {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0;
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
```

Create per-purpose generators (`rng(7)` for node layout, `rng(Math.floor(T*24)+3)` for glitch slices that change 24 times a second). Using `Math.random()` is acceptable **only** for cosmetic per-frame jitter such as screen shake and film grain, where every frame should differ and exact repeatability does not matter.

### 5.3 Motion without state (closed forms)

| Want | Write |
|---|---|
| Constant drift with wrap | `x = ((x0 + vx*T) % W + W) % W` |
| Oscillation | `y = y0 + A*Math.sin(T*w + phase)` |
| Pulse | `s = 1 + .06*Math.sin(T*8)` |
| Count-up across orders of magnitude | `v = v0 * Math.pow(v1/v0, ease.io(p))` |
| Decaying shake after impact at `t0` | `amp = A * (1 - seg(t, t0, t0+.2))` |
| Staggered entrance of item `i` | `seg(t, s + i*gap, s + i*gap + dur)` |
| Typewriter | `text.slice(0, Math.floor(p * text.length))` |

If you truly need a physics simulation (bouncing bodies, flocking), run it with a **fixed timestep** from a seeded start, step forward from the last computed time to `T`, and **reset and re-simulate if `T` goes backward** (replay/scrub). Keep sims tiny.

### 5.4 Keyframe tracks (when a value has many stops)

```js
function track(t, keys) {            // keys: [[time, value, easeFn?], ...] sorted by time
  if (t <= keys[0][0]) return keys[0][1];
  for (let i = 1; i < keys.length; i++) {
    if (t <= keys[i][0]) {
      const [t0, v0] = keys[i-1], [t1, v1, e = x => x] = keys[i];
      return lerp(v0, v1, e(seg(t, t0, t1)));
    }
  }
  return keys[keys.length-1][1];
}
// scale = track(t, [[0,1],[.2,1.4,ease.out3],[.5,1,ease.io]]);
```

### 5.5 Transitions between scenes

Hard cuts hit hardest when timed to a beat or an impact. Use these, in rough order of usefulness:

- **Hard cut on a hit**: end the scene on the exact time of a sound impact. Zero blending.
- **Flash cut**: ramp `fx.flash` to 1 at the end of scene A, start scene B with `fx.flash = 1 - seg(t, 0, .5)`.
- **Glitch out**: ramp `fx.glitch` and `fx.ab` in the last 0.5 s, then cut.
- **Black beat (silence)**: 0.2-0.5 s of pure black **and silence** before a reveal. This is the single most effective trick for impact.
- **Collapse/suck-in**: scale to 0 toward a point with `ease.in3` while rotating slightly; cut on the vanish.
- **Whip/slide**: translate the outgoing content off with `ease.in3`; incoming from the other side with `ease.out3`.
- **Crossfade**: draw both scenes with complementary alphas. Rarely needed in punchy pieces; useful in calm ones.

---

## 6. Drawing toolkit

### 6.1 Text (the most important thing you will draw)

Kinetic typography carries most pieces. Write one `txt()` helper and use it for everything.

```js
function txt(s, x, y, size, o = {}) {
  g.save();
  g.font = `${o.it ? 'italic ' : ''}${o.w || 400} ${size}px ${o.f || FONT.disp}`;
  g.textAlign = o.a || 'center'; g.textBaseline = 'middle';
  if ('letterSpacing' in g) g.letterSpacing = (o.ls || 0) + 'px';
  if (o.al != null) g.globalAlpha *= o.al;
  if (o.sh) { g.shadowColor = o.sh; g.shadowBlur = o.shb || 30; }        // glow
  if (o.sx != null || o.rot) {                                            // scale/rotate ABOUT (x,y)
    g.translate(x, y); if (o.rot) g.rotate(o.rot);
    g.scale(o.sx || 1, o.sy || o.sx || 1); g.translate(-x, -y);          // NOT x=0,y=0 (see trap 17.3)
  }
  if (o.st) { g.strokeStyle = o.st; g.lineWidth = o.sw || 2; g.strokeText(s, x, y); }
  if (!o.nofill) { g.fillStyle = o.c || '#fff'; g.fillText(s, x, y); }
  g.restore();
}
```

Companions:

```js
const mw = (s, size, f, w = 400) => { g.save(); g.font = `${w} ${size}px ${f}`; const m = g.measureText(s).width; g.restore(); return m; };
const fitSize = (s, maxW, base, f, w) => Math.min(base, base * maxW / mw(s, base, f, w));   // shrink to fit
function wrap(s, maxW, size, f, w) {                                                        // greedy word wrap -> lines[]
  const out = []; let cur = '';
  for (const wd of s.split(' ')) { const t = cur ? cur + ' ' + wd : wd;
    if (mw(t, size, f, w) > maxW && cur) { out.push(cur); cur = wd; } else cur = t; }
  if (cur) out.push(cur); return out;
}
```

Text animation patterns (all are `seg` + a property):

| Effect | Recipe |
|---|---|
| **Slam** | scale from 1.4-1.8 to 1 with `ease.outExp` over 0.2-0.3 s, plus `fx.shake` spike and `fx.ab` spike at that instant, plus an audio impact at the same time |
| **Typewriter** | slice by `seg`; add a blinking block cursor `Math.floor(t*2.6)%2`; for centered text left-align at `CX - fullWidth/2` so it does not jitter |
| **Fade + rise** | alpha `= p`, `y += (1-p)*30` |
| **Letter stagger** | draw char by char with cumulative measured width, each with its own `seg` offset |
| **Underline draw** | `fillRect(cx - w/2, y, w * ease.out3(seg(...)), 4)` with `w` growing |
| **Glitch out** | in the last 0.3 s raise `fx.glitch`, `fx.ab`; optionally jitter x with seeded random |
| **Word-per-beat** | show one word each beat/half beat (montage) |
| **Gradient text** | `c: gradient` (create the gradient in scene coordinates; see trap 17.3) |
| **Glow** | `sh` color + `shb` 20-45. Costly. Use on 1-3 elements per frame |
| **Stroke outline** | `nofill: true, st: color, sw: 3` for hollow type behind solid type |

Text sizing rules of thumb (at 1600x900): hero words 150-260 px in a condensed display face; supporting lines 34-48 px; labels/HUD 13-20 px mono; nothing under 13 px. Always `fitSize` names and titles of unknown length.

### 6.2 Shapes and paths

```js
function rr(x, y, w, h, r) {                    // rounded rect path (do not rely on ctx.roundRect; older Safari lacks it)
  g.beginPath(); g.moveTo(x + r, y);
  g.arcTo(x+w, y, x+w, y+h, r); g.arcTo(x+w, y+h, x, y+h, r);
  g.arcTo(x, y+h, x, y, r);     g.arcTo(x, y, x+w, y, r); g.closePath();
}
```

Draw-on for lines and curves: set `g.setLineDash([len * p, len * 2])` where `len` is an *over-estimate* of path length and `p` is 0..1. Approximate lengths are fine visually.

Curved connectors (attention arcs, dependency lines): `bezierCurveTo(x1, y1+d, x2, y2-d, x2, y2)` with `d` around 100-130 gives elegant S-curves between two rows.

Panels/cards: dark fill (`#0a0e14`), a 52 px header bar with a label in the accent color, corner brackets in the accent (`L`-shaped strokes at the four corners), clip demo content to the panel with `g.save(); g.beginPath(); g.rect(...); g.clip(); ...; g.restore();`.

### 6.3 Gradients and glow

- **Radial glow behind a hero**: `createRadialGradient(cx,cy,0, cx,cy,R)` from accent at alpha .3-.45 to transparent, filled over the full frame. Cheap and effective.
- **Additive light**: `g.globalCompositeOperation = 'lighter'` for rays, sparks, beams. Reset to `'source-over'` after (or wrap in `save/restore`).
- **Glow via shadow**: `shadowBlur` costs a lot on large text and many shapes. Budget it (section 18).
- **Avoid `ctx.filter = 'blur(...)'`**: not supported on older Safari. Fake blur with radial gradients, or draw small then scale up.

### 6.4 Backgrounds that carry a motif

A persistent background motif that **evolves across the piece** ties scenes together far better than new backgrounds each scene. Example: a drifting node-and-link network whose density, speed, link distance and color are parameters (`amt`, `speed`, `link`, `col`) that each scene sets (sparse and cold at the start, dense and gold at the climax).

```js
const NODES = (() => { const r = rng(7);
  return Array.from({length: 130}, () => ({x: r()*W, y: r()*H, vx: (r()-.5)*40, vy: (r()-.5)*40, s: r()})); })();
function drawNet(t, amt, col = '#7df9ff', speed = 1, link = 200) {
  const n = Math.max(2, Math.floor(NODES.length * amt)), P = [];
  for (let i = 0; i < n; i++) { const o = NODES[i];
    P.push([((o.x + o.vx*t*speed) % W + W) % W, ((o.y + o.vy*t*speed) % H + H) % H]); }   // closed-form drift
  g.save(); g.strokeStyle = col; g.lineWidth = 1;
  for (let i = 0; i < n; i++) for (let j = i+1; j < n; j++) {
    const dx = P[i][0]-P[j][0], dy = P[i][1]-P[j][1], d2 = dx*dx + dy*dy;
    if (d2 < link*link) { g.globalAlpha = (1 - Math.sqrt(d2)/link) * .5 * Math.min(1, amt*1.5);
      g.beginPath(); g.moveTo(P[i][0], P[i][1]); g.lineTo(P[j][0], P[j][1]); g.stroke(); } }
  g.fillStyle = col;
  for (let i = 0; i < n; i++) { g.globalAlpha = (.55 + .45*Math.sin(t*2 + NODES[i].s*9)) * Math.min(1, amt*2);
    g.beginPath(); g.arc(P[i][0], P[i][1], 1.6 + NODES[i].s*1.8, 0, 6.283); g.fill(); }
  g.restore();
}
```

Other motif options: dot grid, starfield, concentric rings, hex lattice, waveform stack, diagonal stripes, gradient mesh, scanning lines, particles that converge into shapes. Cheap emblems that vary per item (see Appendix B) give montages visual variety without assets.

### 6.4b Data visuals

Charts are just shapes: bars are `fillRect` with animated height, lines are paths with dash draw-on, counters are text with `v0*Math.pow(v1/v0, p)`. Format big numbers with unit suffixes (`65 M`, `1.7 T`). Animate axes and values in with a stagger. Label everything; mark illustrative data as illustrative on screen.

---

## 7. Post-processing and screen effects

Order in `renderScene` (after the scene has drawn into the buffer):

1. **Glitch slices** (buffer-level).
2. **Vignette** (pre-rendered small canvas stretched over the frame).
3. **Scanlines** (1 px dark line every 4 px at ~5% alpha).
4. **Film grain** (a pre-generated 256x256 noise tile filled with `'overlay'` at ~7% alpha and a random offset each frame).
5. **Flash** (white fill with `alpha = fx.flash`).

Then `present()` applies **shake, zoom, and chromatic aberration** when copying to the screen.

### 7.1 Screen shake

`present()` offsets the destination by a random amount up to `fx.shake` (in buffer pixels, times scale). Trigger it as a *decaying spike at impact*: `fx.shake = Math.max(fx.shake, 14 * (1 - seg(lt, 0, .16)))`. Sustained low shake (3-8) builds tension during a rise.

### 7.2 Chromatic aberration (RGB split)

Draw the opaque buffer three times, each multiplied by pure red/green/blue and composited with `'lighter'`, offset horizontally:

```js
if (fx.ab > .6) {
  const a = fx.ab * s, offs = [-a, 0, a], cols = ['#f00', '#0f0', '#00f'];
  for (let i = 0; i < 3; i++) {
    tg.globalCompositeOperation = 'source-over'; tg.drawImage(buf, 0, 0);          // tg = scratch canvas, same size
    tg.globalCompositeOperation = 'multiply';    tg.fillStyle = cols[i]; tg.fillRect(0, 0, W, H);
    ctx.globalCompositeOperation = 'lighter';    ctx.drawImage(tmp, dx + offs[i], dy, dw, dh);
  }
  ctx.globalCompositeOperation = 'source-over';
} else ctx.drawImage(buf, dx, dy, dw, dh);
```

Requirements: the buffer must be **opaque** (always fill black first), or `multiply` shows the fill color everywhere. Only pay the 3x cost when `fx.ab > .6`.

### 7.3 Glitch slices

Copy random horizontal strips of the buffer onto itself with a horizontal offset:

```js
const r = rng(Math.floor(T * 24) + 3), n = Math.floor(fx.glitch * 9);
for (let i = 0; i < n; i++) {
  const y = r()*H, h = 6 + r()*60, dx = (r() - .5) * 140 * Math.min(1.4, fx.glitch);
  g.drawImage(buf, 0, y, W, h, dx, y, W, h);           // drawing a canvas onto itself is valid
}
```

Seeding by `floor(T*24)` makes the glitch change 24 times per second and be repeatable.

### 7.4 Flash

Impact flash: `fx.flash = 1 - seg(t, 0, .55)` at the start of a scene. Build-up flash: `fx.flash = Math.pow(seg(t, a, b), 2)`. **Photosensitivity**: keep a full-frame white flash rare (a handful per piece), never faster than ~3 Hz, and warn on the start screen (section 12).

### 7.5 Zoom / camera push

`fx.zoom = 1 + .05*seg(t, 0, 6)` enlarges the presented frame about the center. A slow push on a static hold gives life. A per-beat pulse `1 + .012*Math.sin(beat * 2π)` in a montage gives rhythm.

### 7.6 Others worth knowing

- **Letterbox bars** for a cinematic look: two black rects, top and bottom.
- **Motion blur**: cheap version = draw the previous state a few times at lower alpha; or, for a whole-frame trail, fill with `rgba(0,0,0,.2)` instead of clearing (breaks determinism; avoid unless the scene is self-contained).
- **Bloom fake**: draw bright elements twice, once larger with low alpha, using `'lighter'`.
- **Scanline sweep**: a translucent horizontal bar moving down.
- **Vignette pulse** on heartbeats.
- **Color grade per act**: multiply a translucent color over the frame (`rgba(20,40,80,.15)` for cold, `rgba(80,50,10,.12)` for warm).

---

## 8. Sound design and music synthesis

Everything is synthesized. No samples. The building blocks are oscillators, filtered noise, envelopes, a compressor and a reverb.

### 8.1 Audio graph

```
voices -> [optional reverb send] -> master gain -> compressor -> destination
```

```js
function buildAudio() {
  AC = new (window.AudioContext || window.webkitAudioContext)();
  master = AC.createGain(); master.gain.value = .85;
  const comp = AC.createDynamicsCompressor();
  comp.threshold.value = -12; comp.knee.value = 20; comp.ratio.value = 5; comp.attack.value = .004; comp.release.value = .2;
  master.connect(comp); comp.connect(AC.destination);

  // reverb: generated impulse response = decaying noise
  const len = Math.floor(AC.sampleRate * 3.2), ib = AC.createBuffer(2, len, AC.sampleRate);
  for (let c = 0; c < 2; c++) { const d = ib.getChannelData(c);
    for (let i = 0; i < len; i++) d[i] = (Math.random()*2 - 1) * Math.pow(1 - i/len, 2.6); }
  const conv = AC.createConvolver(); conv.buffer = ib;
  const rg = AC.createGain(); rg.gain.value = .5; conv.connect(rg); rg.connect(master); wet = conv;

  // reusable noise buffer
  nb = AC.createBuffer(1, AC.sampleRate * 3, AC.sampleRate);
  const d = nb.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = Math.random()*2 - 1;

  base = AC.currentTime + .3;              // piece time 0 happens at AC time `base`
}
function outTo(node, send) {               // dry to master, optional wet send amount
  node.connect(master);
  if (send) { const sg = AC.createGain(); sg.gain.value = send; node.connect(sg); sg.connect(wet); }
}
```

The compressor is not optional: many voices summing will clip without it.

### 8.2 Two primitives: `voice` (oscillator) and `noise`

```js
function v(o) {   // {t, d, f, f2?, fd?, type, vol, a, lp?, lp2?, q?, det?, send?}
  const t = base + o.t, os = AC.createOscillator(); os.type = o.type || 'sine';
  os.frequency.setValueAtTime(o.f, t);
  if (o.f2) os.frequency.exponentialRampToValueAtTime(o.f2, t + (o.fd || o.d));   // pitch sweep
  if (o.det) os.detune.value = o.det;                                             // cents
  const gn = AC.createGain(), a = Math.max(.002, o.a || .005);
  gn.gain.setValueAtTime(.0001, t);
  gn.gain.exponentialRampToValueAtTime(o.vol, t + a);                             // attack
  gn.gain.exponentialRampToValueAtTime(.0001, t + o.d);                           // decay/release
  let node = os;
  if (o.lp) { const fl = AC.createBiquadFilter(); fl.type = 'lowpass'; fl.frequency.setValueAtTime(o.lp, t);
    if (o.lp2) fl.frequency.exponentialRampToValueAtTime(o.lp2, t + o.d); fl.Q.value = o.q || .7; node.connect(fl); node = fl; }
  node.connect(gn); outTo(gn, o.send); os.start(t); os.stop(t + o.d + .05);
}
function n(o) {   // {t, d, vol, type: 'bandpass'|'highpass'|'lowpass', f, f2?, q?, a?, send?}
  const t = base + o.t, s = AC.createBufferSource(); s.buffer = nb; s.loop = true;
  const fl = AC.createBiquadFilter(); fl.type = o.type || 'bandpass'; fl.frequency.setValueAtTime(o.f, t);
  if (o.f2) fl.frequency.exponentialRampToValueAtTime(o.f2, t + o.d); fl.Q.value = o.q || 1;
  const gn = AC.createGain(), a = Math.max(.002, o.a || .002);
  gn.gain.setValueAtTime(.0001, t); gn.gain.exponentialRampToValueAtTime(o.vol, t + a); gn.gain.exponentialRampToValueAtTime(.0001, t + o.d);
  s.connect(fl); fl.connect(gn); outTo(gn, o.send); s.start(t, Math.random()*1.5); s.stop(t + o.d + .05);
}
```

**Hard rules for these primitives:**
- `exponentialRampToValueAtTime` **cannot target 0** and throws. Use `.0001` as "silence".
- An oscillator **cannot be restarted**. Create a new one for every note.
- Always call `stop()` so nodes are garbage collected.
- `o.t` is *piece time*; the primitive adds `base`. Never mix absolute audio times and piece times in the same function.

### 8.3 Instrument recipes (copy these)

```js
const kick  = (t, vol = .9) => { v({t, d:.45, f:160, f2:42, fd:.14, vol, a:.001});                       // sine pitch-drop = body
                                 v({t, d:.05, f:1800, f2:200, fd:.03, type:'triangle', vol: vol*.25, a:.001}); }; // click
const hat   = (t, vol = .12) => n({t, d:.05, vol, type:'highpass', f:7500, q:.5});
const clap  = (t, vol = .35) => { [0,.012,.024].forEach(o => n({t: t+o, d:.09, vol: vol*.6, type:'bandpass', f:1600, q:.8}));
                                  n({t: t+.03, d:.22, vol, type:'bandpass', f:1400, q:.7, send:.25}); };
const snare = (t, vol = .3) => { n({t, d:.18, vol, type:'highpass', f:1800, q:.6});
                                 v({t, d:.12, f:220, f2:150, type:'triangle', vol: vol*.6, a:.001}); };
const boom  = (t, vol = 1)  => { v({t, d:3.2, f:70, f2:26, fd:2.4, vol, a:.003});                        // sub drop
                                 n({t, d:2.6, vol: vol*.7, type:'lowpass', f:3000, f2:80, q:.5, send:.5, a:.003}); // rumble tail
                                 v({t, d:2, f:2200, f2:300, fd:1.5, type:'sawtooth', vol: vol*.05, lp:2500, send:.6, a:.002}); }; // sizzle
const heart = (t, vol = .5) => { v({t, d:.35, f:80, f2:38, fd:.15, vol, a:.004});                        // lub
                                 v({t: t+.24, d:.3, f:70, f2:36, fd:.12, vol: vol*.7, a:.004}); };        // dub
const pluck = (t, f, vol = .08, d = .35, send = .6) => v({t, d, f, type:'triangle', vol, a:.004, lp:3500, lp2:600, send});
const lead  = (t, f, vol = .05, d = .16) => v({t, d, f, type:'sawtooth', vol, a:.003, lp:4500, lp2:900, send:.25});
const bass  = (t, f, d, vol = .3) => { v({t, d, f, type:'sawtooth', vol: vol*.6, a:.004, lp:700, lp2:160});
                                       v({t, d, f, type:'sine', vol, a:.004}); };
const pad   = (t, notes, d, vol = .05, a) => notes.forEach(f => [-9, 9].forEach(det =>                    // detuned saws = wide chord
                v({t, d, f, type:'sawtooth', det, vol, a: a || d*.4, lp:1100, send:.5})));
const riserN = (t, d, vol) => n({t, d, vol, type:'bandpass', f:250, f2:9000, q:1.2, a: d-.03, send:.2}); // noise sweep up
const riserT = (t, d, f0, f1, vol) => v({t, d, f:f0, f2:f1, type:'sawtooth', vol, a: d-.03, lp:600, lp2:7000, send:.3}); // pitch sweep up
```

A **drone** (long sustained tension bed) is easiest as two slightly detuned saws plus a sub sine through one lowpass whose cutoff and gain you ramp over the whole act; build it with raw nodes rather than `v()` because it lives for tens of seconds.

**Sound-effect menu** (all from the primitives above):

| Want | Recipe |
|---|---|
| Whoosh/suck-in | `n` bandpass sweep `f:200 -> 6000`, attack nearly the full duration |
| Reverse cymbal | `riserN` high-passed, ends abruptly |
| Impact/slam | `boom` + `kick` at the same time |
| UI blip | short `square` with lowpass 3000, 0.15-0.2 s |
| Error buzz | `sawtooth` 110->80 Hz + bandpassed noise, 0.3 s |
| Typing tick | `n` highpass 4000+, 0.02 s |
| Coin/success | two `triangle` notes an octave-ish apart 60 ms apart |
| Glass/shimmer | high sine 1300-2000 Hz, long decay, big reverb send |
| Laser/zap | `sawtooth` `f:2000, f2:100`, d 0.15 |
| Riser (tension) | `riserN` + `riserT` together for 4-8 s |
| Sub throb | `sine` 40 Hz with slow gain pulse |
| Heartbeat | `heart` every 0.9-1.2 s; speed up to raise stress |
| Wind/ambience | `n` lowpass 400 with slow gain LFO |
| Choir-ish swell | `pad` with 5 notes, long attack, high reverb send |

### 8.4 Music without a keyboard: notes, scales, BPM

Frequency from MIDI note: `f = 440 * 2 ** ((midi - 69) / 12)`.

Beat length: `BEAT = 60 / BPM`. At 128 BPM, `BEAT = 0.46875 s`, so 64 beats = exactly 30 s (handy for planning).

Safe, emotional building blocks:

- **A minor pentatonic** (works over almost anything): A3 220, C4 261.63, D4 293.66, E4 329.63, G4 392, A4 440.
- **Epic progression, one chord per bar**: Am - F - C - G. Roots (bass, Hz): A1 55, F1 43.65, C2 65.41, G1 49. Chord tones for arps (Hz): Am `[220, 261.63, 329.63, 440]`, F `[174.61, 220, 261.63, 349.23]`, C `[196, 261.63, 329.63, 392]`, G `[196, 246.94, 293.66, 392]`.
- **Ascending arpeggio** over the chord tones at 16th notes reads as "energy".
- **Major lift** for a hopeful ending: end on C major (C3 130.81, G3 196, C4 261.63, E4 329.63, G4 392, C5 523.25).

A sequencer is just a loop over beats:

```js
for (let bi = 0; bi < 64; bi++) {
  const tb = T0 + bi * BEAT, bar = Math.floor(bi / 4) % 4;
  kick(tb, .95);                                                    // four on the floor
  bass(tb, roots[bar], BEAT * .45); bass(tb + BEAT/2, roots[bar] * (bi % 2 ? 2 : 1), BEAT * .45);
  if (bi >= 8)  hat(tb + BEAT/2, .11);                              // layer in over time
  if (bi >= 4 && bi % 2) clap(tb, .3);
  if (bi >= 8)  for (let j = 0; j < 4; j++) lead(tb + j*BEAT/4, chords[bar][(j + bi) % 4] * 2, .045);
}
```

**Arrangement = adding and removing layers.** Start with kick + bass, add hats, then claps, then arps, then snare rolls before a drop. Layers arriving on section boundaries is what makes it feel composed.

### 8.5 The five tools that make a soundtrack feel cinematic

1. **Silence.** Cut everything 0.2-0.4 s before a reveal, then hit hard. Contrast is louder than volume.
2. **Risers.** Noise and pitch sweeps for the 4-8 s before a climax, with kicks that accelerate (`interval *= .94`, floor at ~.09 s).
3. **Impacts.** `boom` on every slam, scaled to importance.
4. **Heartbeat.** Establishes fear/tension cheaply; accelerating heartbeat = rising stakes.
5. **Reverb.** Pads and plucks with a high `send` sound big; drums stay dry so they stay punchy.

### 8.6 Mixing guardrails

- Kick ~.9, bass ~.3, clap ~.3, snare ~.2-.3, hats .06-.12, lead .04-.06, pad .03-.06 *per voice* (a pad chord has many voices; count them), risers .3-.55, booms .7-1.2.
- The compressor tames peaks, but if the result is muddy, lower pads first.
- Leave headroom: master ~.85. End with a fade (`master.gain.linearRampToValueAtTime(0, base + DURATION + 1)`).
- Do not schedule sound after the visual end; let tails ring naturally.

### 8.7 Long pieces: look-ahead scheduling

A few thousand nodes scheduled up front is fine (a 90 s piece with a dense 30 s montage is ~2,000). For pieces of several minutes or generative loops, schedule in chunks:

```js
let nextBeat = 0;
setInterval(() => { while (base + nextBeat * BEAT < AC.currentTime + 2) { scheduleBeat(nextBeat++); } }, 250);
```

### 8.8 Audio-reactive visuals

`AnalyserNode` (`fftSize = 256`, `getByteFrequencyData`) drives visuals from the actual sound. It is non-deterministic (cannot export frame-by-frame). For deterministic beat reactivity, derive pulses from the **score** instead: `beatPhase = ((T - T0) / BEAT) % 1`, then `pulse = Math.pow(1 - beatPhase, 3)`.

### 8.9 Speech, voiceover, real music

- `speechSynthesis` can narrate but voices vary per device and cannot be captured into a recording. Prefer on-screen text. If you use it, treat as optional.
- Do not attempt to reproduce a specific existing song, jingle or lyric. Compose an original synthesized cue.
- User-supplied audio: load with `fetch` + `decodeAudioData` **only if** the environment allows it; otherwise ask the user to host it or use an `<audio>` element.

---

## 9. Syncing picture and sound

### 9.1 Use the audio clock

```js
function getT() {
  const lat = AC.outputLatency || AC.baseLatency || 0;
  return Math.max(0, AC.currentTime - base - lat);      // subtract output latency so visuals match what is *heard*
}
```

`base` is chosen as `AC.currentTime + 0.3` when scheduling, so the first 0.3 s clamps to 0 (a natural lead-in).

### 9.2 Rules

- Every schedule call uses **piece time** (seconds from the start). Every scene uses **local time**. Convert with named constants (`TS.act2 + 2.2`), never hand-added literals scattered around.
- Put timing constants in one table used by both the visuals and the audio schedule. If a slam happens at local `t = 2.4` in the scene starting at `TS.s1 = 4`, the audio hit is `boom(TS.s1 + 2.4)`. Compute it; do not retype `6.4`.
- Tabs in the background pause `requestAnimationFrame` but not audio. Because visuals derive from the audio clock, they snap back in sync automatically.

### 9.3 Musical time for montages

Express montage timing in **beats**, not seconds. Each card gets a duration in beats (`2`, `1`, `.5`), and you find the current card by walking a schedule built from cumulative beat sums. Visual cuts then land exactly on the kicks scheduled with the same `BEAT`.

```js
const SCHED = []; let b = 0;
A.forEach(c => { SCHED.push({b, d: 2, ...c}); b += 2; });
B.forEach(c => { SCHED.push({b, d: 1, ...c}); b += 1; });
C.forEach(c => { SCHED.push({b, d: .5, ...c}); b += .5; });
// b is now the beat where the next section starts; assert b === expected
```

**Accelerating structure** (very effective for "flash through many things"): 2 beats each (name + tagline), then 1 beat each (name + short line), then half a beat (name + category only), then a final "wall" where everything appears at once. Each tier is faster and simpler than the last.

### 9.4 Arithmetic checks (do these on paper)

- Sum of montage beats equals the planned section length in beats. `beats * BEAT` equals the planned seconds.
- The last scene ends at `TS.end`. No scene start is later than its successor.
- Every audio hit has a matching visual moment, and vice versa.
- Silence windows in audio correspond to intentional black/hold frames.

---

## 10. Pacing, storytelling and creative direction

### 10.1 Structure that works

**Hook, escalate, reveal, explode, payoff, tag.**

1. **Hook** (0-5 s): a strong, quiet, specific image or line. Establish the "before".
2. **Establish the rule** (5-20 s): show the old world clearly enough that the change will matter.
3. **Turn** (20-32 s): tension builds; something goes right/wrong; one recurring motif starts to grow.
4. **Reveal** (a single beat): silence, then the title slam. This is the moment the piece exists for.
5. **Expansion/explosion**: rapid montage or proof; accelerate.
6. **Payoff**: the emotional statement; callback to the opening; one last hit.
7. **Tag**: title/end card; nothing after it.

### 10.2 Contrast is the engine

Alternate: quiet/loud, small/huge, slow/fast, cold/warm, sparse/dense, dark/bright. Every transition should change at least two of these. Plan a contrast table in the shot list.

### 10.3 Reading time

Viewers must read text. Minimum on-screen time = `0.35 s + 0.25 s * wordCount` for calm pieces; hype montages may go to ~`0.2 s + 0.12 s * wordCount` for **single names/short words** only. Sentences of more than 8 words need 2 s or more. If it cannot be read, cut words, not time.

### 10.4 Shot-length rhythm

- Long holds (2-4 s) for statements; medium (1-2 s) for supporting beats; short (0.25-0.5 s) for montage.
- Vary. Uniform shot length is what makes a piece feel like a slideshow.
- Land the most important word/image on a beat or an impact.

### 10.5 Text writing

Short. Declarative. Concrete. Prefer strong verbs. Use fragments and rule-of-three lists (`READ. WRITE. CODE.`). Use an ellipsis to imply a pause and then honor it with an actual pause. Do not explain jokes or emotions. Do not use hype adjectives when a specific fact hits harder.

### 10.6 Creative device menu (pick 2-4, do them well)

- **Demo-then-break**: show the old system working, then feed it something outside its domain and let it error (`ERROR: OUT OF DOMAIN`).
- **Emergence**: a counter climbs while capabilities/pills light up one by one, with the caption "nobody programmed this".
- **Diagram becomes protagonist**: a small technical diagram (attention arcs, a pipeline) grows into the piece's background motif.
- **Escalating counter**: a fake-but-labeled HUD counter that rises through a montage.
- **The wall**: end a montage by filling the screen with hundreds of tiny names/icons, then overlay a punchline ("AND A BILLION OTHERS").
- **Shockwave + brackets + rays**: for reveals, concentric expanding rings, tall brackets drawing on, and slow radial rays.
- **Callback**: return to the opening image/phrase transformed at the end.
- **Scale jump**: tiny detail to city-scale, or 1 to 1,000,000 counters.
- **Fourth-wall tag**: last line addresses the viewer or the making of the piece.
- **Fake UI chrome**: terminal, code, dashboard, notification, loading bars, but only if it serves the subject.
- **Constraint humor**: the piece's own limits as a joke ("rendered in 90 seconds of JavaScript").

### 10.7 Tone calibration

| Tone | Palette | Motion | Sound | Type |
|---|---|---|---|---|
| Epic/hype | near-black, electric cyan/gold/red | slams, shake, hard cuts | 128 BPM, sub booms, risers | condensed display, all caps |
| Calm/elegant | deep neutrals, one warm accent | slow eases, long holds | pads, sparse plucks, big reverb | serif, generous space |
| Playful | saturated multi-color | springs, overshoot, bounce | plinks, pops, light drums | rounded sans |
| Corporate/clear | white or light grey, brand color | linear-ish, restrained | gentle pulse or none | clean sans |
| Ominous | desaturated, red accents | slow creeping zoom, glitch | drones, heartbeat, silence | mono, small caps |

---

## 11. Visual design rules

- **One accent color per moment**; change accent per act or per item, not per element. Keep backgrounds dark for punch; use light backgrounds intentionally.
- **Type is the hero** in code-native pieces. Use a condensed heavy display face for slams (Anton, Bebas Neue, Impact fallback), an elegant serif italic for reflective lines (Instrument Serif, Georgia fallback), a monospace for technical labels (JetBrains Mono), and a clean grotesque for supporting lines (Space Grotesk). Two or three families, clearly distinct roles.
- **Hierarchy through scale**, not decoration. The main thing is 3-6x larger than the second thing.
- **Center-align** for slams and statements; **left-align** for typewriter and data.
- **Margins**: keep important content inside the central 90% of the frame; the corners host small HUD elements only.
- **Avoid the defaults**: tracked-out all-caps eyebrows on everything, dot-separated meta strings on everything, identical rounded cards everywhere, a gradient wash as generic decoration. Use structure (borders, brackets, labels) only where it carries information.
- **No unnecessary motion.** Motion should draw attention to what matters right now. Constant motion everywhere means nothing stands out.
- **Consistency**: same easing family, same effect vocabulary, same corner treatment across scenes.
- **Emblems instead of logos**: generated geometric patterns (rings, bursts, dot grids, hexagons, stripes, waveforms) selected per item give variety with no trademark risk.

---

## 12. Player shell: controls, gating, accessibility

### 12.1 The play gate (mandatory when there is sound)

1. Show a start screen with title, one-line premise, a **PLAY** button, and a **photosensitivity/loudness warning** if the piece flashes or has heavy bass.
2. **Preload fonts before enabling the button**, with a timeout so a failed font never blocks:

```js
await Promise.race([
  Promise.all([document.fonts.load("100px 'Anton'"), document.fonts.load("italic 40px 'Instrument Serif'")]),
  new Promise(r => setTimeout(r, 2500))
]).catch(() => {});
```

3. In the click handler, **create the AudioContext synchronously** (before any `await`) so strict browsers such as Safari accept it as user-initiated. Then schedule and resume:

```js
playBtn.onclick = () => { buildAudio(); schedule(); AC.resume(); hideGate(); started = true; };
```

4. Behind the gate, animate an idle backdrop so the page is not dead.

### 12.2 Controls

Pause/resume (`AC.suspend()`/`resume()`), mute (set `master.gain.value`), fullscreen (`stage.requestFullscreen()` with `webkit` fallback), restart (new context), thin progress bar (`T / DURATION`). Keyboard: Space = pause, `M` mute, `F` fullscreen, `R` restart. Auto-hide the controls after a couple of idle seconds; show on pointer move.

### 12.3 End state

At `T >= DURATION`: keep the final frame, show a "Watch again" button, stop advancing.

### 12.4 Accessibility and safety

- Warn about flashing lights and loud bass on the gate.
- Provide a visible mute.
- Keep flashes rare and never rapid; avoid large-area red/white alternation.
- Respect `prefers-reduced-motion` for interactive pieces by reducing shake/flash/zoom scalars (a `MOTION = matchMedia('(prefers-reduced-motion: reduce)').matches ? .3 : 1` multiplier applied to `fx`).
- Text contrast: light on dark, minimum 4.5:1 for body text.
- Add `aria-label`s to buttons; make focus rings visible.
- If speech or critical info is only in sound, also show it as text.

### 12.5 Phones and safe areas

Use `<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">`. Keep controls clear of notches with `env(safe-area-inset-*)`. iOS: Web Audio may be muted by the ring/silent switch; fullscreen on non-video elements is limited. Tell the user to rotate to landscape or design a vertical version.

---

## 13. Other kinds of pieces (variants)

The same engine adapts. What changes is the timeline and the source of `T`.

- **Music visualizer** (user supplies audio or you synthesize a loop): use `AnalyserNode` for bars/waveforms/particles; smooth values with an exponential moving average; add beat detection by comparing low-band energy to its running average.
- **Interactive/generative art**: `T` still comes from a clock, but add pointer/keyboard inputs to scene parameters; keep rendering a pure function of `(T, input state)`.
- **Data story / explainer**: scenes = "claim -> evidence -> implication"; charts animated with `seg`; annotate; always label sources/illustrative data; keep numbers in a single data object at the top so they are easy to audit and update.
- **Slideshow/keynote-style**: scenes advance on user input rather than time; each scene still uses local time since entry.
- **Looping installation/ambient**: no start/end; use closed-form periodic motion (`T % LOOP`), slow evolving audio via look-ahead scheduling.
- **Game/toy**: introduce state with a fixed-timestep loop; keep audio as event-driven one-shots (`base = AC.currentTime` at trigger time).
- **Loader/logo sting (2-6 s)**: 1-3 beats, one slam, one sound, zero excess.
- **Vertical social clip (9:16)**: `W=900, H=1600`, large type, fast pacing, first 1 s hook.
- **Slow cinematic title sequence**: long eases, letterbox bars, drones and pads, very few elements.
- **3D / shader look**: use WebGL only if the user explicitly wants it; render the WebGL canvas as the base, keep 2D text in an overlay canvas, and apply the same clock and effect flags. Budget more time; verification is harder blind.
- **SVG/CSS route**: for simple animated diagrams; drive with CSS custom properties updated from `T`, or WAAPI `animation.currentTime = T*1000` for scrubbable, deterministic timelines.

---

## 14. Libraries: when to use, when not to

Default: **none**. The engine above is a few hundred lines and has no supply-chain, CSP, version, or network risk.

| Library | Reason to add | Cost |
|---|---|---|
| **GSAP** | Very complex timelines, SVG morphing, ScrollTrigger | External script; allowed only from permitted hosts |
| **three.js** | Real 3D | Large; harder to verify blind; older-version quirks |
| **p5.js** | Users want p5 idioms | Adds indirection |
| **Tone.js** | Sophisticated musical structure/instruments | Heavier than needed for synthesized cues |
| **Howler.js** | Playing user-supplied audio files | Not needed for synthesis |
| **D3** | Complex data-driven layouts/scales | Fine for data stories |
| **Lottie** | Playing designer-made animations | Requires assets |
| **Remotion** | Proper MP4 rendering pipeline (React) | Needs Node + Chrome + ffmpeg locally |

If you do use a library from a CDN: pin an exact version, load the **UMD/browser-global build** with a plain `<script src>`, place it before your inline script, and use only hosts the environment permits. If the library needs its own CSS or fonts and only scripts are allowed, do not use it.

---

## 15. Exporting to a real video file

The browser piece is a program. To get an MP4/WebM, choose a route. State honestly which you used and what you could not test.

### Route A: Record playback in the browser (quick, real-time)

```js
const stream = cv.captureStream(60);                            // visible canvas
const dest = AC.createMediaStreamDestination(); master.connect(dest);   // capture the same audio
dest.stream.getAudioTracks().forEach(t => stream.addTrack(t));
const rec = new MediaRecorder(stream, { mimeType: 'video/webm;codecs=vp9,opus', videoBitsPerSecond: 12e6 });
const chunks = []; rec.ondataavailable = e => chunks.push(e.data);
rec.onstop = () => { const url = URL.createObjectURL(new Blob(chunks, { type: 'video/webm' })); /* offer <a download> */ };
rec.start();  // start together with playback; call rec.stop() at DURATION + tail
```

Pros: no tooling. Cons: real-time (a dropped frame is a dropped frame), WebM output, downloads may be inert in sandboxed hosts. Convert to MP4: `ffmpeg -i in.webm -c:v libx264 -crf 18 -c:a aac out.mp4`.

### Route B: Deterministic frame-by-frame render (best quality, needs local tools)

Expose `window.renderAt = T => { renderScene(T); present(); }`. Then with headless Chrome (Playwright/Puppeteer):

```js
for (let f = 0; f < FPS * DURATION; f++) {
  await page.evaluate(T => window.renderAt(T), f / FPS);
  fs.writeFileSync(`frames/${String(f).padStart(5, '0')}.png`, await canvas.screenshot());
}
```

Render audio offline: build the same `schedule()` against `new OfflineAudioContext(2, 44100 * DURATION, 44100)` (point the global `AC` at it, set `base = 0`), call `startRendering()`, write the buffer to WAV. Mux:

```
ffmpeg -framerate 60 -i frames/%05d.png -i audio.wav -c:v libx264 -crf 16 -pix_fmt yuv420p -c:a aac -shortest out.mp4
```

Requirements: `render` must be a pure function of `T` (mental model #1), and randomness that must not flicker between exports must be seeded. Per-frame `Math.random()` shake/grain will differ per frame (fine).

### Route C: Remotion

Port scenes into React components that read `useCurrentFrame()`; keep the same math helpers. Use for teams that want a maintained video pipeline.

### Route D: Screen-record

OBS, QuickTime or the OS recorder capture picture and system audio. Simplest for a non-technical user; tell them to use fullscreen and close other sounds.

If the environment has no network, no browser and no ffmpeg (typical of a chat sandbox), you cannot do Routes B-C yourself. Provide the code and instructions rather than claiming a file exists.

---

## 16. Verifying work you cannot watch

You usually cannot see or hear the output. Compensate with these checks, and **tell the user what you verified and what you did not**.

### 16.1 Syntax check

Extract the script and run `node --check`:

```bash
python3 - <<'EOF'
import re
s = open('piece.html').read()
open('/tmp/check.js','w').write(re.search(r'<script>(.*)</script>', s, re.S).group(1))
EOF
node --check /tmp/check.js && echo SYNTAX_OK
```

### 16.2 Smoke test with a mocked canvas (catches undefined variables, bad math, exceptions in any frame)

```js
// smoke.js  -- run: node smoke.js
const fs = require('fs');
let src = fs.readFileSync('/tmp/check.js', 'utf8');
const mkCtx = () => { const st = {}; return new Proxy(function(){}, {
  get(t, k) {
    if (k === 'measureText') return s => ({ width: String(s).length * 20 });
    if (k === 'createLinearGradient' || k === 'createRadialGradient') return () => ({ addColorStop() {} });
    if (k === 'createPattern') return () => ({});
    if (k === 'createImageData') return (w, h) => ({ data: new Uint8ClampedArray(w*h*4) });
    if (k in st) return st[k]; return () => {};
  }, set(t, k, v) { st[k] = v; return true; }, has() { return true; } }); };
const stub = () => ({ width: 0, height: 0, getContext: () => mkCtx(), getBoundingClientRect: () => ({ width: 1280, height: 720 }),
  addEventListener() {}, classList: { add() {}, remove() {} }, style: {}, textContent: '' });
global.document = { getElementById: stub, createElement: stub, querySelector: stub, fonts: null };
global.window = { addEventListener() {}, devicePixelRatio: 1 };
global.performance = performance; global.requestAnimationFrame = () => {};
src = src.replace('fit(); requestAnimationFrame(loop);', 'globalThis.__r = T => { renderScene(T); present(); };');   // adapt to your entry point
eval(src);
for (let T = 0; T < DURATION + 2; T += 1/30) __r(T);
console.log('all frames rendered');
```

Adapt the replaced line to your file's last statement. Any thrown error names the frame and line.

### 16.3 Audio schedule checks

Run `schedule()` against a mock `AudioContext` that records calls, or against an `OfflineAudioContext` in Node with a WebAudio polyfill if available, and assert: no `exponentialRampToValueAtTime` to `0`; no negative times; last event before `DURATION + tail`; total node count below a few thousand. If you cannot run audio, review the schedule by reading it against the shot list table line by line.

### 16.4 Sampling frames (when a browser exists)

If Playwright/Puppeteer/Chrome is available, render frames at key times (first frame of each scene, each slam, the last frame), save PNGs, and inspect them. If not, state that visuals were not visually inspected.

### 16.5 Self-review checklist

- Do all text elements fit at the smallest supported aspect (letterboxed 16:9 on a phone)?
- Any overlapping text from two timelines at once (e.g., a previous line not faded before the next)?
- Any scene where every element ends at the same instant, leaving an empty frame?
- Does every `seg` have `a < b`? (`seg` with `a == b` divides by zero.)
- Any value that could go `NaN` (`Math.pow` of negatives, divide by zero, `log(0)`)?
- Does replaying work (new AudioContext, `started=false` during setup)?
- Pause/resume? Mute persists across replay?

---

## 17. Known traps and their fixes

1. **Silent audio.** Context created outside a user gesture, or `resume()` not called. Create it synchronously in the click handler; call `AC.resume()`.
2. **`exponentialRampToValueAtTime` throws** when the target is 0 or negative. Always use `.0001`.
3. **Gradient text loses its colors after `translate/scale`.** Gradients live in user space; translating to `(x,y)` and drawing at `(0,0)` shifts the gradient. Scale about a pivot with `translate(x,y); scale(s); translate(-x,-y)` and draw at `(x,y)`. Define the gradient in scene coordinates.
4. **`letterSpacing` and centering.** Canvas letter-spacing adds trailing space, shifting centered text slightly. For exact centering left-align at `CX - measuredWidth/2` or ignore for small values. Also check `'letterSpacing' in g` (older Safari lacks it) and provide a fallback.
5. **Chromatic aberration shows a colored screen.** The buffer was not opaque. Fill it with black at the start of every frame.
6. **`ctx.roundRect` / `ctx.filter` missing.** Use your own `rr()` path; avoid blur filters.
7. **Web fonts not applied on canvas.** Canvas uses whatever is loaded at draw time. Load fonts *before* enabling playback; include a fallback stack with similar metrics.
8. **Text jitter in typewriter.** Centered typed text moves as it grows. Left-align at a position computed from the *full* string width.
9. **Jump/desync after tab switch.** Not an issue if visuals derive from the audio clock; it is an issue if you increment time per frame. Never do that.
10. **Replay glitches.** Old scheduled nodes still fire on the old context. Close it and build a new one; reset `started/ended/paused`.
11. **Pause drifts** if you use `performance.now()`. Use `AC.suspend()` and read `AC.currentTime`, or record pause offsets carefully.
12. **Audio clipping/harshness.** Too many voices without a compressor; lower pad/lead volumes; add the compressor; keep master at .85 or less.
13. **Scheduled sound after the visual end.** Compute `DURATION` from the same table as the schedule.
14. **`Math.random()` in layouts** changes every playthrough and breaks determinism. Use `rng(seed)`.
15. **Off-by-one gaps in a beat-based schedule** due to floating point (`b >= s.b && b < s.b + s.d` with accumulated halves). Use a fallback (`cur = SCHED[0]` then loop) and prefer values that are exact in binary (`.5`, `1`, `2`).
16. **Memory/perf growth**: creating new gradients/patterns every frame at large sizes. Cache what is static (vignette, grain tile, fixed gradients).
17. **CSP blocks**: remote images, fetch to other origins, inline event handlers may be blocked. Keep everything inline and data-driven.
18. **Autoplay of video/audio elements** is separately gated; synthesized Web Audio after a click is the reliable path.
19. **iOS**: silent switch mutes Web Audio; fullscreen limited. Mention this to the user if they are on a phone.
20. **High-DPI blurriness.** Size the visible canvas by `getBoundingClientRect() * devicePixelRatio` (cap at 2); the buffer stays at virtual resolution, so text may look slightly soft on 4K. Raise buffer resolution only if performance allows.
21. **`drawImage` scaled by non-integers** blurs pixel-art looks; irrelevant for vector-style pieces.
22. **Scene timing edits break audio sync** when times are duplicated as literals. Keep one table.

---

## 18. Performance budget

Target 60 fps on a mid-range laptop and 30+ on a phone.

- Virtual resolution 1600x900 or less for effect-heavy pieces.
- Per frame, aim for under ~6,000 canvas calls. Network graphs: `O(n²)` pair checks are fine up to ~150 nodes.
- `shadowBlur`: at most a few large glows per frame. Prefer radial gradients.
- Chromatic aberration is 3 full-frame passes; only enable while `fx.ab > .6`.
- Full-frame `fillRect` loops for scanlines: replace with a cached pattern if you see slowdowns.
- Cache: vignette canvas, grain tile, static gradients, measured text widths for fixed strings.
- Audio: keep total scheduled nodes below ~3,000 for up-front scheduling; use look-ahead for more.
- Avoid allocating big arrays per frame; hoist constants.
- If frames drop on phones, expose a quality flag that lowers virtual resolution, node counts and effect intensity.

---

## 19. Content, legal and honesty rules

- **Facts**: verify names, dates, numbers when a search tool is available; otherwise use conservative, well-established claims and hedge wording. Label illustrative or stylized numbers *on screen* ("illustrative").
- **Logos and marks**: do not draw real logos. Use typographic wordmarks, generated emblems and color accents.
- **Music and lyrics**: never reproduce copyrighted lyrics or melodies. Compose original synthesized cues. A style description ("driving 128 BPM minor-key synth") is fine.
- **People and likeness**: no real people's faces or fabricated quotes attributed to real people.
- **Sensitive subjects**: avoid graphic violence, sexual content, hateful content. Keep tone appropriate to the subject.
- **Claims of quality**: do not say it looks/sounds great if you have not seen or heard it. Say what you verified (syntax, every frame rendered without errors, timeline arithmetic) and what you did not (visual/aural feel, real-device performance).
- **Attribution/fonts**: Google Fonts are OK to load; mention them in the delivery notes.

---

## 20. Delivery

1. Produce **one self-contained file** (`piece.html`) unless the user asks for more. Put it where the environment expects deliverables (for example `/mnt/user-data/outputs/`). If the environment offers a hosting/publish mechanism for web pages, use it and follow its rules (fonts and scripts allow-lists, no remote images, no external fetches). If not, present the file.
2. Tell the user, briefly:
   - What it is and how to play it (sound on, fullscreen, landscape) plus controls (Space, M, F, R).
   - Content warnings (flashing, loud bass).
   - The scene-by-scene structure in a few lines.
   - What is stylized or illustrative.
   - What you verified and what you could not.
   - Limitations: it is a program, not an MP4; how to get an MP4 (section 15).
3. Offer 2-3 concrete next steps (different tone, retime, extra scenes, vertical cut, export script).
4. If asked "what did you use?", answer plainly: browser-native APIs (Canvas 2D, Web Audio), no libraries, fonts from Google Fonts, plus the tooling you actually used to build and check (file writer, Node syntax/smoke test, publishing tool).

---

## Appendix A: minimal complete engine

A tiny but complete two-scene piece with sound, gate, pause, replay, effects and end state. Start from this and grow it.

```html
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Piece</title>
<style>
  html,body{margin:0;height:100%;background:#000;overflow:hidden;font-family:system-ui,sans-serif}
  canvas{position:absolute;inset:0;width:100%;height:100%}
  #gate{position:absolute;inset:0;display:grid;place-items:center;background:rgba(0,0,0,.8);color:#fff;
        font:700 26px system-ui;letter-spacing:.1em;cursor:pointer;text-align:center}
</style></head>
<body>
<canvas id="c"></canvas>
<div id="gate">PLAY WITH SOUND<br><small style="font:400 12px system-ui;opacity:.6">contains flashing lights</small></div>
<script>
(() => {
'use strict';
const W = 1600, H = 900, CX = W/2, CY = H/2, BEAT = 60/120;
const TS = { a: 0, b: 6, end: 14 };                       // scene starts (seconds); TS.end = duration
const FONT = { disp: "'Anton','Impact',sans-serif" };

/* ---------- canvas + buffer ---------- */
const cv = document.getElementById('c'), ctx = cv.getContext('2d');
const buf = document.createElement('canvas'); buf.width = W; buf.height = H;
const g = buf.getContext('2d');
function fit() { const d = Math.min(devicePixelRatio || 1, 2), r = cv.getBoundingClientRect();
  cv.width = Math.max(2, r.width * d | 0); cv.height = Math.max(2, r.height * d | 0); }
addEventListener('resize', fit);

/* ---------- math ---------- */
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, t) => a + (b - a) * t;
const seg = (t, a, b) => clamp((t - a) / (b - a));
const ease = { out3: t => 1 - Math.pow(1 - t, 3), outExp: t => t >= 1 ? 1 : 1 - Math.pow(2, -10 * t) };

/* ---------- effects ---------- */
const fx = { shake: 0, flash: 0, ab: 0, zoom: 1 };

/* ---------- text ---------- */
function txt(s, x, y, size, o = {}) {
  g.save(); g.font = `${o.w || 400} ${size}px ${o.f || FONT.disp}`;
  g.textAlign = o.a || 'center'; g.textBaseline = 'middle';
  if (o.al != null) g.globalAlpha *= o.al;
  if (o.sh) { g.shadowColor = o.sh; g.shadowBlur = o.shb || 30; }
  if (o.sx != null) { g.translate(x, y); g.scale(o.sx, o.sx); g.translate(-x, -y); }
  g.fillStyle = o.c || '#fff'; g.fillText(s, x, y); g.restore();
}

/* ---------- scenes (local time t) ---------- */
function sceneA(t) {
  txt('BEFORE.', CX, CY, 120, { al: seg(t, .3, 1) * (1 - seg(t, 4.8, 5.6)) });
  fx.ab = Math.max(fx.ab, seg(t, 5, 6) * 8);
}
function sceneB(t) {
  const p = seg(t, 0, .25);                                    // slam
  txt('AFTER.', CX, CY, 200, { sx: lerp(1.6, 1, ease.outExp(p)), sh: '#7df9ff', al: Math.min(1, p * 3) });
  if (t < .25) { fx.shake = 16 * (1 - t / .25); fx.ab = 12 * (1 - t / .25); }
  fx.flash = Math.max(fx.flash, 1 - seg(t, 0, .5));
}

/* ---------- audio ---------- */
let AC = null, master, wet, base = 0;
function buildAudio() {
  AC = new (window.AudioContext || window.webkitAudioContext)();
  master = AC.createGain(); master.gain.value = .85;
  const comp = AC.createDynamicsCompressor(); master.connect(comp); comp.connect(AC.destination);
  base = AC.currentTime + .3;
}
function tone(t, f, d, vol = .2, type = 'sine', f2) {
  const T0 = base + t, o = AC.createOscillator(), gn = AC.createGain();
  o.type = type; o.frequency.setValueAtTime(f, T0);
  if (f2) o.frequency.exponentialRampToValueAtTime(f2, T0 + d);
  gn.gain.setValueAtTime(.0001, T0); gn.gain.exponentialRampToValueAtTime(vol, T0 + .005);
  gn.gain.exponentialRampToValueAtTime(.0001, T0 + d);
  o.connect(gn); gn.connect(master); o.start(T0); o.stop(T0 + d + .05);
}
const kick = t => tone(t, 150, .4, .9, 'sine', 42);
function schedule() {
  for (let t = 1; t < TS.b - .5; t += 1.2) kick(t);                     // heartbeat-ish pulse
  tone(TS.b - .01, 60, 2.5, 1, 'sine', 26);                             // impact exactly at the cut
  for (let i = 0; i < 16; i++) { kick(TS.b + i * BEAT); tone(TS.b + i * BEAT + BEAT / 2, 220 * (i % 4 ? 1.5 : 1), .2, .08, 'triangle'); }
  master.gain.setValueAtTime(.85, base + TS.end - 1); master.gain.linearRampToValueAtTime(0, base + TS.end);
}

/* ---------- clock ---------- */
function getT() { return AC ? Math.max(0, AC.currentTime - base - (AC.outputLatency || AC.baseLatency || 0)) : 0; }

/* ---------- render ---------- */
function renderScene(T) {
  fx.shake = fx.flash = fx.ab = 0; fx.zoom = 1;
  g.globalAlpha = 1; g.globalCompositeOperation = 'source-over';
  g.fillStyle = '#000'; g.fillRect(0, 0, W, H);                          // opaque base
  if (T < TS.b) sceneA(T - TS.a); else sceneB(T - TS.b);
  if (fx.flash > 0) { g.fillStyle = `rgba(255,255,255,${clamp(fx.flash)})`; g.fillRect(0, 0, W, H); }
}
function present() {
  const cw = cv.width, ch = cv.height, s = Math.min(cw / W, ch / H) * fx.zoom, dw = W * s, dh = H * s;
  const dx = (cw - dw) / 2 + (Math.random() - .5) * 2 * fx.shake * s, dy = (ch - dh) / 2 + (Math.random() - .5) * 2 * fx.shake * s;
  ctx.globalCompositeOperation = 'source-over'; ctx.fillStyle = '#000'; ctx.fillRect(0, 0, cw, ch);
  ctx.drawImage(buf, dx, dy, dw, dh);
}

/* ---------- player ---------- */
const gate = document.getElementById('gate'); let started = false;
async function ready() { try { await Promise.race([document.fonts.load("100px 'Anton'"), new Promise(r => setTimeout(r, 2000))]); } catch (e) {} }
gate.addEventListener('click', async () => {
  if (started) return;
  buildAudio(); schedule(); AC.resume();                                 // synchronous inside the gesture
  gate.style.display = 'none'; started = true;
});
addEventListener('keydown', e => { if (e.code === 'Space' && AC) { e.preventDefault(); AC.state === 'running' ? AC.suspend() : AC.resume(); } });
function loop() { requestAnimationFrame(loop); const T = started ? Math.min(getT(), TS.end) : 0; renderScene(T); present(); }
ready().then(() => { fit(); requestAnimationFrame(loop); });
})();
</script>
</body></html>
```

---

## Appendix B: effect and scene recipes

Each recipe uses local time `t` and the helpers above. Combine and restyle; do not copy blindly.

**Shockwave rings** (reveals): `for r in 0..3: d = t - r*.13; if d>0: stroke circle radius d*1500, alpha max(0, .85 - d*.9), lineWidth 10 - r*2`.

**Radial rays** (additive): 48 thin triangles from center, angle `k*2π/48 + t*.12`, `globalCompositeOperation='lighter'`, alpha .05-.13.

**Brackets that draw on**: two `[` shapes at the left/right edges; height `300 * ease.out3(seg(t,0,.55))` around the center; stroke 12 px with glow.

**Count-up with units**: `fmt = n => n<1e9 ? (n/1e6).toFixed(0)+' M' : n<1e12 ? (n/1e9).toFixed(1)+' B' : (n/1e12).toFixed(1)+' T'`; value `v0*Math.pow(v1/v0, ease.io(p))`.

**Emergent pills around a core**: N labels on an ellipse `(cx + cos(a)*rx, cy + sin(a)*ry)`, each appears at `start + i*gap` with `outBack` scale, a bright fill flash that settles to dark with an accent stroke, a thin line to the core, a small shake, and a matching audio pluck stepped up a scale.

**Attention arcs / connector diagram**: two rows of pills; for each target, draw a primary bezier at alpha .85 and neighbor beziers at alpha .15 with pulsing; `setLineDash` for draw-on.

**Error-state demo**: red overlay `rgba(255,30,60,.2)`, dark band with "ERROR" in display type flickering `0.75 + .25*sin(t*40)`, sub-label "OUT OF DOMAIN", the bad input in mono, panel jitter for the first 0.35 s, buzz sound.

**Collapse to a point**: `c = ease.in3(seg(t,a,b))`; per item `pos = lerp(pos0, center, c)`, `rotate(c*k)`, `scale(1-c)`, alpha `1 - .6c`, glitch ramp.

**Wall of names**: grid `8x14`, each cell has a seeded reveal threshold; reveal by global progress; newly revealed cells flash white for the first 0.25 of their age then settle to their accent at flickering alpha; a dark overlay panel with the punchline slams in on top.

**HUD chrome**: top-left title, bottom-left "label + counter", bottom-right progress bar and beat number, all in 13-26 px mono, low alpha.

**Per-item emblem (no logos)**: `kind % 6` selects: concentric expanding rings; radial burst of lines; pulsing dot grid; rotating concentric hexagons; moving diagonal stripes; stacked sine waves. Draw at alpha .3 in the item's accent color behind the text.

**Typewriter with cursor**: left-align at `CX - fullWidth/2`; draw `slice`; blinking rectangle at the end of the typed text.

**Letter stagger**: for each character compute cumulative x from measured widths; alpha `seg(t, st + i*.04, st + i*.04 + .2)`; slide `y += (1-p)*20`.

**Camera push**: `fx.zoom = 1 + .05*seg(t,0,6)`.

**Vertical wipe transition**: draw the incoming scene clipped to `rect(0, 0, W, H*p)` while the outgoing draws unclipped.

**Beat pulse on any element**: `const bp = ((T - T0) / BEAT) % 1; scale = 1 + .06 * Math.pow(1 - bp, 3)`.

**Screen-space text on a curve**: draw each glyph at `(cx + R cos θ, cy + R sin θ)` with rotation `θ + π/2`.

**Particles converge into a word**: precompute target points by drawing the word into a small offscreen canvas, sampling opaque pixels with `getImageData` on a grid, seeding each particle a start position with `rng`, and interpolating `lerp(start, target, ease.io(seg(t,a,b)))`.

**Progress-bar loader**: bar fill `ease.io(seg(...))` with number text and a glitch when it completes.

**Sound: accelerating pulse** (before a climax):
```js
let t = T0, iv = .5, vol = .55;
while (t < T1) { kick(t, vol); t += iv; iv = Math.max(.085, iv * .94); vol = Math.min(.95, vol + .02); }
```

**Sound: blips synchronized to items appearing**: `lead(TS.x + i*gap, 220 * 2 ** (semitones[i] / 12), .06, .3)` with the same `gap` as the visual stagger.

---

## Appendix C: reference tables

### C.1 Easing chooser

| Situation | Easing |
|---|---|
| Object enters and settles | `out3` |
| Slam / stamp | `outExp` (with a scale from 1.4-1.8) |
| Playful overshoot | `outBack` |
| Object leaves / collapses | `in3` |
| Smooth A-to-B move | `io` |
| Springy UI | `spring` |
| Counters | `io` on the exponent |

### C.2 Timing cheat sheet (seconds)

| Item | Duration |
|---|---|
| Slam settle | .2-.3 |
| Standard entrance | .4-.7 |
| Fade out | .3-.6 |
| Impact shake decay | .15-.3 |
| Flash decay | .5-.9 |
| Reveal silence before a hit | .2-.4 |
| Riser | 4-8 |
| Short statement hold | 1.5-3 |
| Montage card at 128 BPM | .23 (half beat), .47 (beat), .94 (two beats) |

### C.3 BPM to beat length

| BPM | Beat (s) | 64 beats (s) |
|---|---|---|
| 90 | .667 | 42.7 |
| 100 | .600 | 38.4 |
| 110 | .545 | 34.9 |
| 120 | .500 | 32.0 |
| 128 | .469 | 30.0 |
| 140 | .429 | 27.4 |
| 174 | .345 | 22.1 |

### C.4 Note frequencies (Hz, equal temperament)

C2 65.41, E2 82.41, G2 98.00, A2 110.00, C3 130.81, D3 146.83, E3 164.81, F3 174.61, G3 196.00, A3 220.00, B3 246.94, C4 261.63, D4 293.66, E4 329.63, F4 349.23, G4 392.00, A4 440.00, C5 523.25, E5 659.25, G5 783.99, A5 880.00, C6 1046.50.

### C.5 Layer entry schedule for a 64-beat drop

| Beats | Layers |
|---|---|
| 0-7 | kick, bass |
| 8-15 | + offbeat hats, arp at 16ths |
| 16-39 | + claps on 2 and 4, 16th hats |
| 40-55 | + snare on offbeats, arp up an octave |
| 56-59 | snare roll at 16ths, riser |
| 60-63 | snare roll at 32nds, riser peaks, cut to silence 0.1 s before the end |

### C.6 Palette starters

- **Cold-to-hot arc**: `#5cc8ff` (cold), `#7df9ff` (electric), `#ffd166` (gold), `#ff5470` (alarm), `#ffffff`.
- **Accent set for montage items**: `#ff5470 #ffd166 #06d6a0 #4dc9ff #a06bff #ff8a3d #e8ecf2 #3dff9a`.
- **Backgrounds**: `#000`, `#05060a`, `#0a0e14` (panels).

---

## Appendix D: final checklist

**Brief and story**
- [ ] User-supplied lines are used verbatim and in order.
- [ ] Hook in the first 3 seconds; a single unmistakable reveal moment; a payoff ending.
- [ ] Contrast plan (quiet/loud, cold/warm, small/huge) exists and is visible in the shot list.
- [ ] Nothing pads the runtime.

**Architecture**
- [ ] Virtual resolution + letterbox; buffer is opaque each frame.
- [ ] Every frame is a pure function of `T`; no per-frame accumulation.
- [ ] One timeline table drives both visuals and audio; scenes are contiguous.
- [ ] Randomness that affects layout is seeded.
- [ ] Replay creates a new `AudioContext`; pause uses `suspend/resume`.

**Visual**
- [ ] Text fits (`fitSize`), is readable for long enough, and uses 2-3 clearly distinct families with fallbacks.
- [ ] Effects vary in intensity; flash is rare; shake decays.
- [ ] No real logos; no remote assets.

**Audio**
- [ ] Compressor on master; no ramps to 0; voices stopped.
- [ ] Impacts match slams; silence before the reveal; riser before the climax.
- [ ] Mix reviewed for clipping (pad voice counts considered); fade-out at the end.

**Player**
- [ ] Gate with warning; AudioContext created synchronously in the click; fonts preloaded with timeout.
- [ ] Pause/mute/fullscreen/restart; end card; keyboard shortcuts.
- [ ] Safe areas and phone behavior considered.

**Verification and honesty**
- [ ] `node --check` passes; smoke test rendered every frame.
- [ ] Timeline arithmetic verified.
- [ ] Deliverable placed/published correctly.
- [ ] The response states what was and was not verified, and how to get an MP4.
