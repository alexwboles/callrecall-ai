# REDESIGN-AUDIT — callrecall-ai demo page (2026-10-13)

Web-facing surface: `demo/index.html` — the project's developer demo page
(the library itself is Python; the page is the first thing an evaluator sees).

Competitors researched (developer-tool docs/demo pages):
1. **Twilio** — tutorial-first: "In five minutes you will…" → prerequisites →
   numbered steps with runnable code → verify success → where-next. The
   business use case is named before implementation details. Multi-language,
   copy-paste code samples are central.
2. **Stripe** — three-panel reference layout (nav left, content center, code
   right), the interactivity benchmark; persistent section navigation.
3. **Plaid / WorkOS** — interactive sandbox/try-it panels embedded in docs;
   visual-led auth-flow diagrams.

## Visual gaps (current vs. competitors)
1. **No section navigation.** Single scrolling column; Stripe/Twilio keep a
   persistent left nav so a developer can jump to the API reference.
2. **Generic hero.** "Your voice agent should remember the caller" is fine
   copy, but there's no Twilio-style five-minute path (numbered steps).
3. **Code samples lack affordances.** Only the install bar has a copy button;
   the Pipecat snippet — the most-copied block — has none.
4. **Helvetica + teal is pleasant but anonymous.** Nothing says "voice
   developer tool"; Twilio's signal red is the category's iconic accent.
5. **The extraction playground is good but buried** — it should read as the
   interactive sandbox (Plaid pattern), with a clearer transcript → brief
   split.

## Functional / flow gaps
1. No numbered quickstart path (install → record → inject → verify).
2. No scrollspy/active-section feedback in any nav (there is no nav).
3. Playground has one fixed transcript; a second sample (e.g. the
   preferences + follow-up call) would show memory across calls.
4. `navigator.clipboard` copy has no fallback and no "copied" feedback.

## In scope for this redesign
1. Twilio/Stripe-docs layout: sticky left section nav (collapses to a
   horizontal bar on mobile), content column, dark code panels.
2. Twilio-style quickstart hero: "In five minutes" + 3 numbered steps
   (pip install → record_call → context_block injection) with copy buttons.
3. Signal-red accent (#e02a3c), dark ink code blocks, sharp corners, mono
   for code/labels, system grotesk for prose.
4. Extraction playground elevated: transcript/brief side-by-side, second
   sample transcript button, redact toggle, "copied" feedback on copy
   buttons, clipboard fallback.
5. Keep all existing content: live brief preview, Pipecat snippet,
   comparison table, API table, badges.

## Out of scope
- The Python library (unchanged); the page's extraction JS keeps the original
  rules behavior-identical on the original transcript, plus two additive
  patterns ("morning callbacks only", "charged twice") that power the new
  billing sample.
- Multi-language tabs (the library is Python-only; one language is honest).

## Regression contract
- Playground still extracts preferences/facts/open/resolved identically.
- PII redaction toggle still works; no `border-radius` anywhere.
