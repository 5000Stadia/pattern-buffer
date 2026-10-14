#!/bin/bash
# Kabe-approved (n97dfba): library pipeline, practice book ch1-2, 3 settings x 2 runs, sequential, graded.
cd /home/k/pattern-buffer/.claude/worktrees/rerun
R=evals/results/2026-10-13-library-compare
B=$R/book
mkdir -p $B && cp evals/books/the-address-that-hummed/ch01.md evals/books/the-address-that-hummed/ch02.md $B/
for v in a_low b_medium d_haiku_low; do
  for n in 1 2; do
    out=$R/${v}_run$n
    echo "=== $v run$n start $(date +%T)"
    timeout 3600 env PYTHONPATH=src:evals/harness PB_EVAL_STAGE_MODELS=evals/stage-maps/map_$v.json \
      /home/k/pattern-buffer/.venv/bin/python evals/harness/run_book.py --book $B --out $out --pipeline library > $out.log 2>&1
    echo "=== $v run$n exit $? $(date +%T)"
    PYTHONPATH=src:evals/harness /home/k/pattern-buffer/.venv/bin/python evals/harness/profile_build.py $out > /dev/null 2>&1
    PYTHONPATH=src:evals/harness /home/k/pattern-buffer/.venv/bin/python evals/harness/grade_book.py --run $out --graded evals/results/2026-10-13-stage-compare/graded_ch2.json --book $B --through-chapter 2 > /dev/null 2>&1; echo "    graded $?"
  done
done
