"""patternbuffer: an append-only world-state substrate.

One append-only log of perspective-scoped, time-indexed assertions per
world; every other structure — current state, space, knowledge, history,
the rendered world — is a disposable projection over it.

The engine is host-blind: its single outside dependency is an injected
model callable ``(prompt, schema) -> json``. See docs/WHITEPAPER.md.
"""

__version__ = "0.0.1"
