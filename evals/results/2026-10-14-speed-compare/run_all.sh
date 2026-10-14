#!/bin/bash
# Prepared 2026-10-14; RUNS ONLY UNDER KABE'S YES ON GATE g460a1c (paid, his Claude plan).
# Library pipeline, Sonnet 4.6 at low effort, practice book chapters 1-2, three settings x two
# runs, sequential, profiled and graded with --through-chapter 2; then one full 6-chapter build
# at the setting named in $FULL (default iii), graded against the full key.
#   (i)   today's settings
#   (ii)  --classify-workers 4                       (BUILD-SPEED-V1: parallel classification)
#   (iii) --max-words 750 --extract-workers 8 --classify-workers 4   (smaller chunks, more workers)
# Run from a worktree pinned at the commit under test, so main can move while it runs:
#   git worktree add --detach .claude/worktrees/speed <sha> && cd .claude/worktrees/speed
#   evals/results/2026-10-14-speed-compare/run_all.sh
set -u
PY=/home/k/pattern-buffer/.venv/bin/python
R=evals/results/2026-10-14-speed-compare
B2=$R/book_ch2
mkdir -p "$B2" && cp evals/books/the-address-that-hummed/ch01.md evals/books/the-address-that-hummed/ch02.md "$B2"/
MAP=evals/stage-maps/map_a_low.json
declare -A SETTING=(
  [i]=""
  [ii]="--classify-workers 4"
  [iii]="--max-words 750 --extract-workers 8 --classify-workers 4"
)
run() {  # run <name> <book dir> <graded key> <through-chapter or empty> <extra args>
  local out=$R/$1 book=$2 key=$3 through=$4; shift 4
  echo "=== $(basename "$out") start $(date +%T)"
  timeout 3600 env PYTHONPATH=src:evals/harness PB_EVAL_STAGE_MODELS=$MAP \
    $PY evals/harness/run_book.py --book "$book" --out "$out" --pipeline library "$@" > "$out.log" 2>&1
  echo "=== $(basename "$out") exit $? $(date +%T)"
  PYTHONPATH=src:evals/harness $PY evals/harness/profile_build.py "$out" > /dev/null 2>&1
  if [ -n "$through" ]; then
    PYTHONPATH=src:evals/harness $PY evals/harness/grade_book.py --run "$out" --graded "$key" \
      --book "$book" --through-chapter "$through" > /dev/null 2>&1
  else
    PYTHONPATH=src:evals/harness $PY evals/harness/grade_book.py --run "$out" --graded "$key" \
      --book "$book" > /dev/null 2>&1
  fi
  echo "    graded $?"
}
for s in i ii iii; do
  for n in 1 2; do
    # shellcheck disable=SC2086
    run "${s}_run$n" "$B2" evals/results/2026-10-13-stage-compare/graded_ch2.json 2 ${SETTING[$s]}
  done
done
FULL=${FULL:-iii}
# shellcheck disable=SC2086
run "full_${FULL}" evals/books/the-address-that-hummed evals/books/the-address-that-hummed/graded.json "" ${SETTING[$FULL]}
