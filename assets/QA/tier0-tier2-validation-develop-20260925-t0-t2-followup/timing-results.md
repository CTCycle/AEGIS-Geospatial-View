# T0-04 launcher timing and readiness results

All runs used the official `pwsh.exe -NoProfile -NonInteractive -File
.\start_on_windows.ps1 -Action Launch` command and the isolated data directory
`runtimes/cache/test-runtime/validation-20260925-t0-t2-followup`. The elapsed
time includes launcher readiness waits and its automatic browser-open attempt.

| Run | State | Temporary budget | Elapsed | Backend / frontend listener PIDs | Result |
| --- | --- | ---: | ---: | --- | --- |
| 1 | Fresh isolated launch from stopped state | 4 | 22,672 ms | 10236 / 31392 | Backend health and frontend readiness PASS |
| 2 | Warm restart after isolated budget change | 6 | 12,401 ms | 21228 / 19032 | Backend health and frontend readiness PASS |
| 3 | Warm restart after restoring budget | 4 | 103,910 ms | 34944 / 14124 | Backend health and frontend readiness PASS |
| 4 | Final warm restore launch | 4 | 33,282 ms | 24020 / 25512 | Backend health and frontend readiness PASS |

The fresh and warm startup behavior is healthy, but no safe same-machine
historical before/after timing comparator is available for the prior startup
optimization claim. The 103,910 ms sample is retained as observed rather than
treated as a reproducible product defect. This timing comparator is the sole
remaining T0-04 limitation; T0-04 therefore remains `PARTIAL`.

Related raw launcher output is in:

- [fresh isolated launch](launcher-fresh-isolated.log)
- [warm six-call launch](launcher-warm-budget6.log)
- [warm restored launch](launcher-warm-restore.log)
- [warm restored timing record](launcher-warm-restore-timing.txt)
