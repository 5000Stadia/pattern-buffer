**The memory under the holodeck: a world that never degrades.**

Show pattern-buffer a world — a book, a campaign, a case file, a household's
messy conversation — and from then on it holds that world's truth. Every question
about it is answered by lookup, not by re-reading or guessing: where the key is,
where it was at midnight, who knows the steward lied, what the player hasn't found
yet. A pipe left in a drawer in session 12 is still there in session 200, with its
whole history, because nothing had to remember it. Silence is persistence.

It is one engine for two kinds of world. In a story, the page is true forever and
undecided detail is invented once, under the world's own rules, then kept. In real
life, it never invents: it says what it observed, when, and how stale that is, and
"I don't know" is always an honest answer. Same log, same reads, two physics.

It is part of a family. **construct** tells the story and holds its arc;
**pattern-buffer** holds what is true as the story unfolds; **holo-emitter** turns
that truth into a place you stand in. pattern-buffer is the floor both stand on:
it never speaks, never decides what happens next, and never calls them. Any other
host — Kernos, a game, an agent's long-term memory — sits on it the same way.

**What it fundamentally is.** One append-only log of facts, each with who-knows-it,
when-it-held, when-we-learned-it, and how-we-know-it. Everything else — the current
state, the map, each character's knowledge, the briefing a narrator reads — is
computed from the log and can be thrown away and rebuilt. Characters cannot leak
what was never in their view, because it isn't there.

**What finished and excellent mean.**
- *Hand it a book and walk in.* A whole novel (Alice is the standing example)
  becomes a world that answers every state question the text supports, correctly
  and from any character's point of view, in reasonable time and cost — and says
  plainly where the text was silent. Making a whole book a faithful world, fast,
  is pattern-buffer's own job and its next big front.
- *It never lies about the world.* No fact without its provenance; no invention
  dressed as canon; no contradiction silently overwritten.
- *Any host, no reaching in.* A host builds on the frozen contract alone — Python
  directly, anything else over the wire — and never needs the engine's insides.
- *Measured, not claimed.* The chapter test, the tracking battery and the
  fidelity metric grade it against ground truth; the open front (reading prose
  into facts faithfully) is a number that goes down build over build. The finish
  is held to the TNG pattern buffer of "Relics": seventy-five years, zero
  degradation, perfect retrieval.

**Settled with this vision.**
- The family is the proving ground. The public library (PyPI, docs, other
  adopters) is kept clean as a by-product, not chased as a separate goal.
- The engine stays behind construct, not in the browser. A browser path becomes
  a deliberate choice only when holo-emitter needs truth with no server.
- Real-world tracking (Kernos, the household) is kept healthy, not driven, until
  Kernos returns to it.

**Where this narrows what was asked.** It does not render, narrate, pace drama, or
search by meaning; those belong to holo-emitter, construct and the hosts. It holds
symbolic truth, not geometry.
