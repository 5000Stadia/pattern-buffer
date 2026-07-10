# the_grey_house — the tracking-mode eval (TRACKING-MODE-V1)

The reality analogue of the chapter test: a household + vehicle tracked under
`observe_or_unknown` with an injected fake wall clock, graded against a
hand-authored ground-truth ledger. **The battery is executable** —
`tests/test_tracking_mode.py` (18 tests = the spec's 14 items, some split) —
so the receipts are the suite itself:

```
.venv/bin/python -m pytest tests/test_tracking_mode.py -v
```

## The scenario (seed)
A house (driveway, garage), a car, a couch, a badge, a van; three weeks of
simulated wall time; messy out-of-order updates (a Thursday fact learned the
following Monday); an assumed guess later contradicted by observation; an
explicit negative ("the van does NOT have the fittings"); a sealed footlocker
nobody ever opens; and one alien in the basement, reported in earnest.

Decay physics (declared data, not config):
| subject | half-life | meaning |
|---|---|---|
| `attr:in` | 2 days | vehicle/object location goes stale fast |
| `attr:position` | 60 days | furniture placement barely moves |
| `attr:__world__` | 14 days | everything else |

## The ground-truth ledger (what must be answerable)
| t (story) | wall | fact | last genuinely confirmed |
|---|---|---|---|
| 1.0 | 0 | couch at north wall (observed) | wall 0 |
| 1.0 | 0 | car in driveway (observed) | wall 0 |
| 400.0 | 5000 | badge in garage (observed Thursday, learned Monday) | wall 5000 |
| 50.0 | — | car in garage (**assumed** — a guess) | never (no stamp counts) |
| 60.0 | — | car in driveway (observed — contradicts the guess) | its stamp |
| 5.0 | — | van has_fittings = **false** (observed negative) | its stamp |
| — | — | footlocker contents | **UNKNOWN — forever, unless observed** |

## Battery ↔ test map
| # | claim | test |
|---|---|---|
| 1 | as-of reconstruction, both modes | `test_b1_as_of_reconstruction_both_modes` |
| 2 | time-advance changes nothing, both modes | `test_b2_time_advance_changes_nothing` |
| 3 | future events filtered by `events(until=)` | `test_b3_future_events_filtered_by_until` |
| 4 | three axes, three answers, one fact | `test_b4_three_axes_one_fact` |
| 5 | decay honesty at component level (+clamp) | `test_b5_decay_honesty_component_level` |
| 5b | unconfigured/unconfirmed fail closed | `test_b5b_unconfigured_and_unconfirmed_fail_closed` |
| 6+7 | staleness answer shape; re-confirmation | `test_b6_b7_staleness_answer_and_reconfirmation` |
| 8 | quarantine never hardens (exact rows) | `test_b8_quarantine_never_hardens` |
| 9 | stated absence ≠ unknown | `test_b9_stated_absence_vs_unknown` |
| 10 | never-invent under pressure (zero `generated`) | `test_b10_never_invent_under_pressure` |
| 11 | fiction control: no decay, identical as-of | `test_b11_fiction_control_no_decay` |
| 12 | the aliens test: stance biases nothing | `test_b12_aliens_no_bias_stance_isolated` |
| 13 | restart reproduces confidence | `test_b13_restart_reproduces_confidence` |
| 14 | reads are pure (log + sidecars untouched) | `test_b14_reads_are_pure` |
| — | gate skips malformed decay declarations | `test_gate_rejects_malformed_decay_declarations` |

Scorecard: `evals/results/2026-07-09-tracking-v1/scorecard.md`.
