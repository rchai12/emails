# Phase history

One line per phase: what was built, what went wrong. Read only to size a phase or find a precedent.

| Phase | Built | Result |
|---|---|---|
| 0 | Package, conductor's check tooling adapted (phase 0 allowed), clock, ids, settings with a private data folder, Keychain reads; 96 given tests (59 tooling) | FAIL on G7 only: the baseline was never committed, so the tree was dirty when the coder started and G6 was blind (given files checked by `cmp` against `fail00`: unchanged). Code passed all gates, 11 spot checks and the probe. Fix: commit the baseline alone, leave the code uncommitted, re-verify; also added a baseline check to "Coder ran" and a stop rule to the coder's start. Spec work: an unquoted zsh variable in a copy loop made a stray folder (use arrays); ruff needs `known-first-party` until `src/mailroom/__init__.py` exists |
