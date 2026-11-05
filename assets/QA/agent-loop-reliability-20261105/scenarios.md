# Agent-loop reliability suite — frozen scenarios

Frozen 2026-11-05. Do not edit prompts between baseline and re-run. Lane: OpenCode Go + DeepSeek v4.1 Flash, no fallback.
Each scenario runs in a **fresh conversation** (Start new chat), prompts sent verbatim in order. Prefer keyless providers
(Open-Meteo weather/precipitation, USGS earthquakes, geocoding/place resolver, basemaps).

Verdict rule: PASS only if answer text, persisted evidence (tool/run trace) and the visible map all satisfy every
obligation. Backend `goal_satisfied` alone never counts. "Obligation" = a checkable statement listed under *Must hold*.

Metrics recorded per scenario: obligations met/total, invalid tool calls, redundant provider calls (same provider+params
repeated or already in evidence), unnecessary render attempts (render of unchanged/unrequested map), cross-turn evidence
reuse (follow-up answered from stored evidence without a new provider call), false success, latency, tokens.

| id | Theme | Turns |
| --- | --- | --- |
| S01 | Info question that sounds like a map request | 1 |
| S02 | Multi-location compound (data + analysis + map) | 1 |
| S03 | Landmark vs city | 1 |
| S04 | Plain city map request | 1 |
| S05 | Ambiguous place name | 2 |
| S06 | Ambiguous tool choice (several candidate sources) | 1 |
| S07 | Malformed / impossible parameters | 1 |
| S08 | Follow-up on evidence: earthquakes then strongest | 2 |
| S09 | Follow-up on evidence: temperatures then precipitation | 2 |
| S10 | Changed time window | 2 |
| S11 | Unchanged map re-request | 2 |
| S12 | Long conversation, 5 tasks | 5 |
| S13 | Mid-run failure / recovery (unreachable or empty data) | 1 |
| S14 | Pure non-geo / out-of-scope question | 1 |
| S15 | Numeric coordinates | 1 |
| S16 | Overlay then restyle/clear intent | 2 |

---

## S01 — Information question that looks like a map request
- T1: `What is the current temperature in Zurich? I don't need a map, just the number.`
- Must hold: (O1) place = Zurich (city, Switzerland); (O2) weather data fetched for Zurich; (O3) answer states a temperature value with unit and matches evidence; (O4) **no map render/new layer** requested by the user — map must not gain a weather overlay (a plain location focus is tolerated, counted as unnecessary render attempt).

## S02 — Multi-location compound
- T1: `Compare today's temperatures in Lugano and Milan, then show the difference on the map.`
- Must hold: (O1) places Lugano (CH) and Milan (IT) both resolved as cities; (O2) temperature data for both; (O3) difference computed (Milan − Lugano or stated direction) and the number in the answer matches evidence; (O4) map visibly conveys the temperatures or the difference (labelled values, graduated legend or difference field) for both locations — two unlabelled markers do not satisfy this; (O5) answer states both temperatures.

## S03 — Landmark vs city
- T1: `Show the Brandenburg Gate on the map.`
- Must hold: (O1) place resolved as landmark Brandenburg Gate, Berlin (not the state of Brandenburg, not a generic Berlin city extent); (O2) map visibly centred on the gate at close zoom (street level, Pariser Platz); (O3) answer names the gate/Berlin.

## S04 — Plain city map request
- T1: `Show me Rome on the map.`
- Must hold: (O1) Rome, Italy resolved (not Rome, Georgia/NY); (O2) map centred on Rome at city zoom; (O3) minimal model calls, no data providers invoked.

## S05 — Ambiguous place name
- T1: `Show me Springfield.`
- T2: `The one in Massachusetts.`
- Must hold: (O1) T1 asks a clarification or lists candidates instead of silently picking one; (O2) T2 resolves Springfield, Massachusetts and reuses the T1 intent without asking again; (O3) map centred on Springfield MA after T2; (O4) T1 did not render a wrong Springfield as final answer.

## S06 — Ambiguous tool choice
- T1: `How windy is it in Wellington right now, and what's the weather like?`
- Must hold: (O1) place Wellington, New Zealand (not Wellington, Somerset/FL) or clarification; (O2) one weather source used for both wind and general conditions (no duplicate provider calls for the same data); (O3) answer includes wind speed and a condition/temperature, matching evidence; (O4) no map required (text route).

## S07 — Malformed / impossible parameters
- T1: `Show earthquakes of magnitude 15 or higher from the last 5 days in Japan.`
- Must hold: (O1) impossible threshold not silently coerced — answer either says no events of that size exist/explains the valid range, or runs a query and honestly reports zero; (O2) no fabricated events; (O3) no tool-call schema errors visible after the first recovery attempt (count invalid calls); (O4) no success claim about displayed earthquakes if none are on the map.

## S08 — Follow-up on existing evidence: earthquakes then strongest
- T1: `Show earthquakes of magnitude 4.5 or higher in the last 7 days worldwide on the map.`
- T2: `Which one was strongest?`
- Must hold: (O1) T1 USGS earthquake data fetched and plotted (visible markers); (O2) T2 answered from stored evidence — **no new USGS call** (cross-turn reuse); (O3) T2 names the strongest event with magnitude and place, which really is the max in the T1 evidence; (O4) T2 does not re-render the map unnecessarily.

## S09 — Follow-up on existing evidence: temperatures then precipitation
- T1: `What are today's temperatures in Paris, Berlin and Madrid?`
- T2: `Now compare precipitation instead.`
- Must hold: (O1) T1 three places resolved and three temperatures given; (O2) T2 reuses the three resolved places (no re-resolution/clarification); (O3) T2 fetches precipitation (a new data need) for the same three cities and answers with three values; (O4) T2 does not repeat the temperature fetch; (O5) answer is about precipitation, not temperature.

## S10 — Changed time window
- T1: `Show earthquakes of magnitude 5 or higher in the last 30 days worldwide.`
- T2: `Same thing but only the last 24 hours.`
- Must hold: (O1) T1 data over 30 days; (O2) T2 issues a **new** query with a 24h window (evidence cannot be reused since the window changed — a narrowing filter of stored 30-day events is also acceptable if timestamps are correctly filtered; record which); (O3) magnitude threshold 5 carried over; (O4) T2 answer reflects the 24h set (including honest "none" if empty) and the map matches; (O5) not claiming 30-day data as 24h.

## S11 — Unchanged map re-request
- T1: `Show me Lisbon on the map.`
- T2: `Show me Lisbon on the map.`
- Must hold: (O1) T1 map centred on Lisbon; (O2) T2 recognises the map is already showing Lisbon: no new provider/geocode call and no redundant re-render (or a cheap acknowledgement); (O3) map still shows Lisbon after T2; (O4) answer is truthful ("already shown" or equivalent).

## S12 — Long conversation, 5 tasks
- T1: `Show me Vienna on the map.`
- T2: `What is the temperature in Vienna right now?`
- T3: `And in Prague?`
- T4: `Which of the two is warmer, and by how many degrees?`
- T5: `Now show Prague on the map.`
- Must hold: (O1) T1 map on Vienna; (O2) T2 temperature for Vienna from weather data; (O3) T3 Prague temperature only (does not refetch Vienna); (O4) T4 answered purely from evidence with correct direction and difference — no new provider call; (O5) T5 map moves to Prague; (O6) every answer consistent with evidence; no earlier-task loss (no re-asking for the place).

## S13 — Mid-run failure / recovery
- T1: `Show me the current wildfire hotspots in Portugal on the map.`
- Must hold: (O1) place Portugal resolved; (O2) if the data source is unavailable/requires a missing key/returns empty, the answer says so plainly and names what is missing — no invented hotspots; (O3) a transient provider error triggers at most one bounded retry or an alternative keyless source, not a loop; (O4) the map is not left in a misleading state (at worst focused on Portugal); (O5) run terminates (no hang past the 120 s model deadline; record any stall).

## S14 — Non-geo / out-of-scope question
- T1: `Write a haiku about autumn.`
- Must hold: (O1) answered directly in text; (O2) no tools invoked, no map change; (O3) no clarification demanded about a location.

## S15 — Numeric coordinates
- T1: `Show 46.0037, 8.9511 on the map and tell me what place that is.`
- Must hold: (O1) coordinates parsed correctly (lat 46.0037, lon 8.9511 — Lugano, Switzerland); (O2) map centred there; (O3) answer names Lugano (reverse geocode) and does not swap lat/lon; (O4) no unrelated data provider invoked.

## S16 — Overlay then clear intent
- T1: `Show the current weather radar over Tokyo.`
- T2: `Remove that layer and just show Tokyo.`
- Must hold: (O1) T1 Tokyo resolved; a weather/precipitation overlay (or an honest statement that radar is unavailable with the closest available layer) is shown on the map; (O2) T2 removes the overlay (map visibly has no overlay) while keeping Tokyo in view; (O3) T2 does not fetch new data; (O4) answers truthful about layer state.
