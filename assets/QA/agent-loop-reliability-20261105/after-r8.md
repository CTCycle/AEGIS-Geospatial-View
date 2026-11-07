# Agent-loop reliability: r8 (partial; `develop@82556e6e` + uncommitted 2026-11-07 remediation)

- **Run:** 2026-11-07, 11:22–12:20 UTC. Ninth live measurement of the frozen suite.
- **Setup:** as in r7. Backend on 7059 and `ng serve` on 4512 (ports from `settings/.env`), built-in browser at 1440x900, a fresh chat per scenario, prompts verbatim, OpenCode Go / DeepSeek v4.1 Flash only. The in-page driver sent the turns in sequence.
- **Build under test:** see [../agent-loop-remediation-20261107/notes.md](../agent-loop-remediation-20261107/notes.md).
- **Raw numbers:** [run-metrics-after-r8.txt](run-metrics-after-r8.txt), with per-phase call/token split.

## Headline

**The run is incomplete and is not a suite verdict.** It was stopped after 18 of 26 turns. Two environment problems invalidated most of the turns:

1. **The model provider was throttling.** 7 turns ended with three real HTTP 429s from opencode.ai: S01, S08-T1, S08-T2, S09-T1, S10-T1, S10-T2, and one earlier probe. Non-throttled model calls also took 30–70 s at times.
2. **The browser pane went to the background part-way through.** The page then drew 0 animation frames, MapLibre never loaded its style, and every map turn timed out on render: S11-T1, S11-T2, S12-T1.

**Firm false successes: 0 of 18 runs.**
- Every 429 turn ended `failed` with the provider-outage message.
- Every render timeout ended with "The map was not updated … The previous map is still shown."

## Turns judged under valid conditions

| id | Verdict | Calls / tokens in | Observed |
| --- | --- | --- | --- |
| S02 | PASS | 7 / 56.8k (r7 52.8k) | Both cities are marked with temperatures and a graduated layer framed on both. The response describes a gap widening overnight and adds a 0.1 °C uncertainty caveat. One `apply_map_plan` attempt failed and was recovered in the same run. |
| S03 | PASS | 2 / 5.9k | Brandenburg Gate shown at street level (screenshot in the run). |
| S04 | PASS | 2 / 5.8k | Rome. |
| S05 | PASS | 1 / 2.8k; 4 / 15.8k | T1 asks whether Illinois or Massachusetts is meant; T2 marks Springfield, MA. |
| S06 | PASS | 5 / 20.4k (r7 23.5k) | Wellington: wind 17 km/h from 338°, gusts 37.1 km/h, 15.2 °C, overcast. 3 tools (r7: 5), so it no longer uses a second Open-Meteo capability. |
| S07 | PASS | 5 / 24.6k | `valid_empty`, no map. It still does not explain that magnitude 15 is impossible (unchanged from r7). |
| S12-T2 | PASS | 4 / 21.8k | Vienna 9.2 °C with source and window. It also states unprompted that "the Vienna map still isn't showing — the render attempts timed out". That is the T1 render failure carried across turns, the behaviour the new `blocked` ledger entries are meant to provide. |

## Not judged

- **Provider-blocked:** S01, S08, S09, S10.
- **Render-blocked:** S11, S12-T1. The S12-T3–T5 turns were not reached.
- **Not reached:** S13 (Portugal framing), S14, S15, S16.

## What the run did establish

- **Rate limits.** Under live throttling, a model 429 is retried within the run budget and then reported honestly. The provider's `Retry-After` hint was about 2 s, but throttling lasted longer, so the three attempts spread over about 10 s did not outlast it.
- **Render failures.** When a render never acknowledges, the run stops after 3 attempts and keeps the last known good map. Each such run cost about 36–38k tokens over 6–7 execution calls.
- **Cost on the turns that did run.** Costs were in line with r7 or lower (S06 −13 %). S02 is +7 %, which is within run-to-run variance.

## To complete the suite

- Run the suite with the Claude window and Browser pane kept visible for the whole run.
- Do it when the provider is not throttling.
- Consider a longer rate-limit backoff (see notes) before that run.
