# Design doctrine — driftdefense.dev

A binary matrix, because the product is a binary verdict.

Leibniz published *Explication de l'Arithmétique Binaire* in 1703 and, in the
same paper, mapped his 0/1 notation onto the I Ching's broken and unbroken
lines. That is not decoration borrowed for mood — it is exactly what this
product does: take a continuous signal and reduce it to one honest verdict.
So the page is built on a yes/no matrix, and the verdict is *drawn* as a
hexagram whose six lines are six real checks.

The balance the site has to hold:

| continuous (the art) | discrete (the science) |
| --- | --- |
| the trace | the verdict |
| serif | monospace |
| the argument | the measurement |
| negative space | the grid |

Neither register is allowed to win. A page that is all trace is a mood board;
a page that is all verdict is a status dashboard. The product is the passage
between them.

---

## The matrix

Each row is a decision that was actually made, not a preference stated after
the fact. **1** is what the page does; **0** is what it refuses.

### Truth

| # | Decision | 1 — yes | 0 — no |
| --- | --- | --- | --- |
| T1 | Live figures | Real values from `/v1/weather`, fetched on a schedule | Simulated, seeded, or hand-tuned demo numbers |
| T2 | Missing data | Publishes `unknown` in amber | Rounds `unknown` up to a passing green |
| T3 | A silent leg | Drawn dashed and amber, labelled by how long it has been quiet | Drawn as a healthy flat line |
| T4 | Forecast | "% of the CUSUM decision interval consumed", labelled as a threshold distance | A percentage presented as a calibrated probability |
| T5 | Baseline | Accumulated from this site's own observations; states its own depth (`2/8 pts`) | A borrowed baseline from an unrelated model's backtest |
| T6 | Reasoning panel | Deterministic narration of the snapshot, labelled as derived | A fake "AI is thinking…" token stream |
| T7 | Claims | Only what the repository can back | Anything requiring trust without a receipt |

T2 and T3 are the load-bearing ones. The engine already encodes this:
status precedence is `DRIFTING > STALE > STABLE`, so a leg that has stopped
reporting can never publish as healthy. A monitor showing green because it
cannot hear anything is the precise failure this project exists to catch —
the site would be self-refuting if its own board did it.

### Form

| # | Decision | 1 — yes | 0 — no |
| --- | --- | --- | --- |
| F1 | Ornament | Must also be instrument — the hexagram *is* the readout | Decorative flourish that carries no data |
| F2 | Colour | One accent; hue spent only on state | Gradient washes, brand colour as mood |
| F3 | Type | Serif for argument, mono for measurement, sans for connective tissue | One neutral sans doing all three jobs |
| F4 | Space | Negative space as structure; prose capped near 68ch | Edge-to-edge text and crowded cards |
| F5 | Corners | 2px — an instrument, not a toy | Pill buttons and 14px bubble cards |
| F6 | Motion | Only where it encodes information (the trace head) | Parallax, scroll-jacking, autoplay video |
| F7 | Hero | A sentence and a working instrument | A stock gradient blob and a product screenshot |

### Cost and autonomy

| # | Decision | 1 — yes | 0 — no |
| --- | --- | --- | --- |
| C1 | Refresh | One cron job, pure-stdlib Python, free Actions minutes | A server, a queue, or a paid scheduler |
| C2 | Inference | Zero model calls in the loop | An LLM invoked per refresh to narrate the board |
| C3 | Delivery | One static document, same-origin JSON | A framework, a build step, a bundler |
| C4 | Read path | Reader's browser touches only driftdefense.dev | Reader's browser calling the gateway directly |
| C5 | Failure | Keeps the last good snapshot, marks it unreachable | Overwrites good data with an empty board |

C2 is the one people get wrong. The expensive thing about drift detection
should be the drift, not the watching. A board that burns inference to
describe itself has inverted its own economics.

### Privacy

| # | Decision | 1 — yes | 0 — no |
| --- | --- | --- | --- |
| P1 | Fonts | System stacks only | Google Fonts on a privacy product |
| P2 | Scripts | No CDN, no framework | Third-party JS for convenience |
| P3 | Analytics | Cookieless page counts | Cookie banners, session recording, pixels |
| P4 | Agents | `llms.txt` + `weather.json` as a declared interface | Forcing agents to scrape HTML |

P1 is not pedantry. A page arguing that raw data must never leave your
perimeter, which then announces every reader to a font host, has lost the
argument in its own `<head>`.

### Access

| # | Decision | 1 — yes | 0 — no |
| --- | --- | --- | --- |
| A1 | Colour alone | Never the only carrier — every state has a shape and a word | Red/green dots as the sole signal |
| A2 | Motion | `prefers-reduced-motion` disables reveal and pulse | Animation that cannot be turned off |
| A3 | Focus | Visible focus ring on every interactive element | `outline: none` |
| A4 | Canvas | Carries an `aria-label` naming the series | An unlabelled decorative canvas |

A1 is why the hexagram exists at all. Unbroken / broken / dotted is a *shape*
distinction that survives colour-blindness and greyscale printing; the colour
is a second, redundant channel rather than the only one.

---

## The six lines

Read bottom-up, as a hexagram is. Each is computed in `scripts/pulse.py`
and is strictly `yes` / `no` / `unknown`.

| Line (bottom → top) | Asks | `unknown` when |
| --- | --- | --- |
| 1 · Leg is reporting | newest sample newer than 30h | never — this one is always knowable |
| 2 · Sample depth sufficient | ≥ 8 batches in the window | never |
| 3 · JSON fidelity in band | \|z\| ≤ 3σ from baseline | baseline under 8 observations |
| 4 · Output length reported | the leg emits a length figure | the field is absent |
| 5 · CUSUM below threshold | S⁻ < h (h = 5.0) | baseline under 8 observations |
| 6 · No quorum alert in 24h | no quorum-verified alert recorded | never |

Lines 3 and 5 begin life dotted and resolve to solid or broken as the
schedule accumulates observations. The figure completing itself over time is
the honest picture of a detector earning its baseline — and it means the
board is visibly more useful next month than today, without anyone touching
it.

---

## What the trace does

`drawTrace()` plots the real observation series and nothing else. Two
observations draw two points and say so. There is no interpolation to make a
sparse series look rich, and no synthetic seismic wiggle.

A `STALE` leg is drawn **dashed and amber**, because a solid flat line is how
silence disguises itself as health.
