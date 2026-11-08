# Routing slice 1: DeepSeek / MiMo comparison

Status: completed 2026-10-18; candidate A (DeepSeek V4.1 Flash) selected as the
provisional primary for this frontend slice.

## Reproducible setup

- Baseline: `bd7bc82` for both worktrees; OpenCode `2.0.32`.
- Identical [slice-1 brief](web-routing-slice-1.md), fresh sessions, model defaults,
  existing locked dependencies copied independently to each worktree.
- Models: `opencode/deepseek-v4.1-flash-free` and `opencode/mimo-v2.6-flash-free`.
- Worktrees: `.pino/worktrees/routing-deepseek` and `.pino/worktrees/routing-mimo`.
- Branches: `experiment/routing-deepseek` and `experiment/routing-mimo`.
- Logs and session manifest: `.pino/routing-comparison/` (local, ignored by Git).
- Baseline verification: 21 frontend tests pass; production build passes with the
  existing bundle-size warning.

Both sessions were started through `opencode run --standalone --auto --model MODEL
--format json` with the same instruction to implement the brief, run checks, remain
in scope, and leave changes uncommitted. No human operated OpenCode manually.

Astra's preflight review identified ambiguity around maximum-year date fallback,
semantic no-op URL normalization, and the order of category normalization. The brief
was clarified while initial runs were active. Both candidates receive the same
explicit follow-up before final comparison; record that separately from any later
candidate-specific repair.

## Review criteria, fixed before seeing completed results

1. Correctness gate: direct URL and reload, control/request agreement, safe parsing,
   Back/Forward, preserved unrelated parameters/hash, Reset, Next month, no-op history.
2. Evidence: meaningful router integration tests and independent tests/build results.
3. Maintainability: one authoritative applied state, no effect feedback loop, no
   unnecessary framework or form abstractions, understandable date validation.
4. Scope: frontend source only, unchanged dependencies and visual design.
5. Reliability: accurate completion report, necessary supervisor repair, elapsed time.

A correctness failure outweighs faster completion or a smaller diff. Vendor benchmark
rankings are not part of the score. Astra receives anonymized candidate snapshots.
Provider failure is an availability observation, not a coding-quality score. This
single frontend task supports only a provisional default; repeat on backend work.

## Results

| | Candidate A: DeepSeek V4.1 Flash | Candidate B: MiMo V2.6 Flash |
| --- | --- | --- |
| First-pass tests | 57 passed; 21 pre-existing | 75 passed; 21 pre-existing; repeated runs reported stable |
| Clarified-turn tests | 64 passed | Not completed; one added equivalent-input test could not trigger React's value-change handler |
| Build / diff check | Passed | Passed |
| Astra recommendation | Preferred after two small repairs | Rejected due to state and date safety issues |

Astra found that A's URL-derived state and simpler navigation were safer foundations.
The initial implementation missed a reset across local midnight and retained a
user-supplied end if an extreme start date could not form a valid default window.
Both were repaired in the kept implementation. We added clock-controlled coverage,
a regression for the extreme-date combination, and real From, To, and score control
tests with history/API assertions. Final local verification is recorded in the
implementation's worktree status and test results; the repository suite passes 69
frontend tests and builds.

B had stronger initial date-picker interaction coverage, which informed the added
tests. Its separate form state could retain more than 200 query characters while the
URL and request were capped. Its Reset path pushed when an unchanged default filter
was expressed explicitly, and its extreme start-date fallback could send year 9999,
which the API rejects. The clarification turn used the same instruction as A. Its
added equivalent-score test could not trigger the input component's change handler
for an unchanged value, so the comparison turn was stopped before the full suite
passed. B's original 75-test snapshot is immutable at
`.pino/routing-comparison/review/final-b/`; its worktree retains the partial attempt
and logs.

This comparison favors DeepSeek for the next scoped UI task. MiMo's first pass took
several hours compared with about ten minutes for DeepSeek, and its stronger calendar
tests were a useful contribution. One frontend task does not establish a general
model ranking; compare again on the first backend identity or city slice.
