# T1-03 browser evidence

## Environment and fixture

- Browser: Codex in-app Browser, `http://127.0.0.1:4512`, 1280x720 viewport.
- App: launched with `start_on_windows.ps1 -Action Launch`; backend at `127.0.0.1:7059`.
- Data: isolated SQLite database under `runtimes/cache/test-runtime/t1-03-20260923`.
- Fixture: 31 conversations with distinct user/assistant markers and one deliberately stale history row. The seed manifest is `seed.json`.
- No provider/model request or map-render operation was made.

## Observations

1. The first history page showed 30 entries. Searching `T1-03 Conversation 15` returned only that fixture. Clearing the query restored the list.
2. Loading the next page produced 32 unique rows across both pages, with no duplicate titles.
3. Selecting Conversation 31 showed its user and assistant markers. Switching to Conversation 30 showed only marker 30; marker 31 was absent.
4. The first visual pass found the hydrated right-aligned user message behind the floating chat actions. Its bounds intersected the actions (`message y=67.48–116.80`, actions `y=63.81–96.60`). The transcript top padding was raised from `0.85rem` to `3.25rem`. After the live frontend update, a fresh in-app Browser screenshot showed the first user message clearly below the History/action controls.
5. The stale fixture was the first row before removal. Its isolated database row was deleted only after confirming the expected title and zero linked messages/runs. `GET /api/conversations/conv_aafd0374dfa74f63bf0333d7873f8b78` returned `404`. Selecting the already-loaded stale row closed history and left the chat workspace empty; Conversation 30's markers were absent.
6. The browser console had no warning or error entries during the recorded check.

The in-app Browser screenshots were visually reviewed inline. The Browser API did not provide a workspace path to export the image bytes, so this file records the observed screenshot evidence rather than claiming a saved PNG.
