#!/bin/bash
cd /home/k/pattern-buffer
for v in a_low b_medium c_tiered; do
  echo "=== $v start $(date +%T)"
  timeout 3600 env PYTHONPATH=src:evals/harness PB_EVAL_STAGE_MODELS=evals/stage-maps/map_$v.json .venv/bin/python evals/harness/run_book.py --book /tmp/claude-1000/-home-k-pattern-buffer/cafbabcb-db1e-4e65-aed2-91e1e23dc6ff/scratchpad/compare/book --out /home/k/pattern-buffer/evals/results/2026-10-13-stage-compare/$v > /home/k/pattern-buffer/evals/results/2026-10-13-stage-compare/$v.log 2>&1
  echo "=== $v exit $? $(date +%T)"
  PYTHONPATH=src:evals/harness .venv/bin/python evals/harness/profile_build.py /home/k/pattern-buffer/evals/results/2026-10-13-stage-compare/$v > /dev/null 2>&1
done
