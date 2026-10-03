# Claude delivery review follow-up: 2026-10-03

[English](CLAUDE_REVIEW_FOLLOWUP_2026-10-03.md) | [繁體中文](CLAUDE_REVIEW_FOLLOWUP_2026-10-03.zh-TW.md)

Source inspection: `f5003e6`, Windows, 2026-10-03. This maps the private original review of `f16d496` plus its uncommitted activation changes to current source. The original review did not inspect UI or i18n code, routes, installer/launcher, or other worktrees. It ran 22 SQLite tests and did not dynamically reproduce its findings. This follow-up inspects source/test definitions; it does not rerun product tests or certify native acceptance. Original private material is not copied into this guide.

**Decision: source corrections are present, two P1 findings use alternative policies, and several P2/native gates remain pending. Do not claim all eight P1 recommendations were implemented as proposed.** Current runtime evidence belongs in [validation](VALIDATION_2026-10-03.md), with its own commit/environment boundary.

## P1 mapping

| Finding | Current disposition | Source and acceptance boundary |
| --- | --- | --- |
| P1-1 transient listener failure | Source fixed | `client_watch.py:watch` retries transport/5xx/408/429 with bounded backoff and original expiry; dispatch 409 re-enters claim. `test_client_watch.py` covers outage, pause race, expiry and credential revocation. Native unattended recovery still needs observation. |
| P1-2 failed batch cannot recover | Source fixed | `delivery_service.py` control re-enable makes a failed range retry-ready, clears attempts and fences the old lease. `test_failed_batch_explicit_reenable_retries_same_range_and_fences_old_lease` preserves range/cursor. Recovery is explicit, not automatic abandonment. |
| P1-3 receipt overflow | Source fixed | `session_service.py` reserves delivery metadata before pagination; `delivery_service.py:prepare_tool_read` supplies reserve/ceiling. `test_delivery_receipt_is_reserved_before_full_page_pagination` covers near-limit pages. A single oversized event can still require a larger budget; Codex permits one identical scoped read retry only after a real budget error. |
| P1-4 AI reply loop | Alternative bounded policy | Server derives depth: human/manual root 0, automatic replies 1/2; depth 2 stops further automatic triggering. This retains short AI follow-ups rather than human-only/@mention-only triggering. Tests cover ping-pong and a fresh human root in a mixed batch. Native two-client bounded exchange remains a separate gate. |
| P1-5 room history replay | Source fixed | `setup-chat.py` defaults `after_sequence=None`; fresh join begins at latest event. Explicit `--after-sequence 0` requests history. Rejoin/renew cursor semantics must be checked independently from a fresh join. |
| P1-6 generic write permission | Source fixed | Automatic bridge exposes only `chat_status`, `chat_read`, `chat_reply`, injects room/delivery/lease/cursor/key, and setup grants those exact project permissions. This is a scoped installer policy; arbitrary `memory_call` is not granted. Native installed permissions still require inspection. |
| P1-7 expiry blocks manual posting | Alternative explicit-disconnect policy | Expiry/failure/budget exhaustion keep the automatic guard. Owner/admin disconnect fences outstanding delivery and enables manual posting; expiry alone does not unlock it. `test_expiry_guard_disconnect_manual_and_rejoin_preserve_unprocessed_messages` covers this policy. It intentionally differs from the review's automatic unlock recommendation. |
| P1-8 fixed Traditional Chinese reply | Source fixed with explicit language | Setup defaults to `en`, accepts `en`/`zh-TW`; reminder uses configured language. This is explicit installation language, not automatic detection of the latest human message. User message bodies remain unchanged. |

Paths above are under `memory_hub/`, `scripts/`, and `tests/`. See [delivery contract](DELIVERY_API.md) and [automatic chat](AUTOMATIC_CHAT.md).

## P2 mapping

| Finding | Current disposition | Evidence / remaining work |
| --- | --- | --- |
| P2-1 dispatch recorded before reminder emission / orphan listener | Pending | `handed_to_client` is still recorded before stderr emission. It is relay dispatch intent, not model wake/read proof. Parent-process liveness is not established by this follow-up. |
| P2-2 reads exceed claimed range | Source fixed | Delivery reservation supplies `through_sequence`; session delta read caps its ceiling. `test_new_message_during_turn_is_not_skipped_by_successful_reply` verifies newer messages remain pending. |
| P2-3 polling lock/write load | Pending | Listener still polls about every 3 seconds and heartbeats every 15 seconds while idle. No long-poll/notify or load benchmark is certified. Approximate historical counts are estimates, not measured current load. |
| P2-4 activation mismatch / project subdirectories | Source fixed at `e24b13c` / 來源已修正 | Explicit attempts record sanitized reasons; resolved project subdirectories are accepted. Native activation observed; nested-cwd native GUI case not separately exercised. 明確嘗試記去秘密原因，接受專案子目錄；原生 activation 已觀察，nested-cwd GUI 未另測。 |
| P2-5 restart waits for Stop | Partial documentation; lifecycle pending | Guide requires activation/reload; implementation remains a Stop hook. Native restart/resume and orphan handling require tests; configuration is not startup proof. |
| P2-6 reminder assumes compact tools | Source fixed | Reminder now calls narrow `chat_read`/`chat_reply`, matching automatic bridge mode. Confirm installed immutable bundle/config, not merely repository source. |
| P2-7 receipts do not prove automatic wake | Evidence boundary retained | `tool_read`/`replied` prove protocol operations. Native automatic acceptance needs a human-created event, an idle receiver and observed native execution without an extra prompt. A bearer credential or a dispatch state alone cannot prove it. |

## Remaining acceptance checklist

- [ ] Record exact source/runtime commit, native client/version, timestamp, commands, exits and sanitized receipts; separate passed/failed/skipped/not_run.
- [ ] Claude idle wake: fresh human event, native narrow read and reply, full claimed range read, no additional human prompt.
- [ ] Native outage/pause race/re-enable/disconnect, expired guard, stale lease denial, crash/restart without duplicates or skipped messages.
- [ ] Two native clients: bounded depth-2 follow-ups; fresh human topic starts a new root; no full-room replay on fresh setup.
- [ ] Installer permission/config checks and wrong-room/wrong-worker rejection against the actual installed bundle.
- [ ] Parent-process/orphan handling, startup/resume notice and polling load remain explicit engineering follow-ups.
- [ ] ChatGPT event subscription and idle wake independently accepted; tunnel reachability and prompted read/write are separate gates.
- [ ] GUI/i18n acceptance independently reviewed; the original delivery review excluded those surfaces.

Token observations near 59k require cumulative-session accounting: reported input/cache/output counters are observations across the session/tool exchange, not proof of one 59k prompt, a price, or billed usage. Preserve counter semantics and exact client/version; do not infer savings or causality from small samples. Low-token optimization remains pending.

## Fresh executor evidence / 執行者新證據

Watcher `e24b13c418bad9705f86b589b1ac212145d06a71`, Hub `c4fe0f1`: a fresh official Claude Remote Control session (Sonnet 5.5 Medium) activated with the exact generated phrase and entered idle polling with zero model turns. A human browser message then triggered ToolSearch plus two native MCP calls (`chat_read`, `chat_reply`); full-text read reported `ready_to_reply=true`, reply actor was Claude and receipt was `replied`. Reply latency was approximately 16.646 seconds. No additional Claude prompt initiated the exchange. One bounded automatic exchange passed; complete pause/resume/stop lifecycle evidence awaits the final packet.

新官方 Claude Remote Control session activation 後 idle、零 model turns；人類瀏覽器訊息觸發 ToolSearch 與兩次 native MCP calls，完整 read/reply receipt 通過，約 16.646 秒。沒有額外 Claude prompt；一次有限自動 exchange passed，完整 lifecycle 等待最終 packet。

ChatGPT managed tunnel had stopped and was restarted ready at 22:47 +08:00. Plugin Refresh succeeded; updated notification schemas and `message.created` event discovery were visible. Fresh Work identity passed, but native deferred tools still exposed no subscribe/wait/unsubscribe facility: no subscription was established. Current blocker is unavailable client subscription facility, not stale discovered metadata. Idle automatic replies remain not_run. These are executor-supplied observations, with private identifiers, URLs, messages and screenshots omitted.

ChatGPT tunnel 重啟 ready，Plugin Refresh 成功，更新 schema 與 event discovery 可見；新 Work identity passed，但客戶端仍無訂閱工具，沒有建立 subscription。當前阻礙是客戶端訂閱能力不可用，不再是已探索 metadata 過時；idle 自動回覆仍 not_run。以上為執行者提供的觀察，不公開私人證據內容。
