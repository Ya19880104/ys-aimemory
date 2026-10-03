# Claude delivery review follow-up: 2026-10-03

[English](CLAUDE_REVIEW_FOLLOWUP_2026-10-03.md) | [繁體中文](CLAUDE_REVIEW_FOLLOWUP_2026-10-03.zh-TW.md)

Source inspection: `f5003e6`, Windows, 2026-10-03. This maps the private original review of `f16d496` plus its uncommitted activation changes to current source. The original review did not inspect UI or i18n code, routes, installer/launcher, or other worktrees. It ran 22 SQLite tests and did not dynamically reproduce its findings. This follow-up inspects source/test definitions; it does not rerun product tests or certify native acceptance. Original private material is not copied into this guide.

**Decision: source corrections are present, two P1 findings use alternative policies, and several P2/native gates remain pending. Do not claim all eight P1 recommendations were implemented as proposed.** Current runtime evidence belongs in [validation](VALIDATION_2026-10-03.md), with its own commit/environment boundary.


## Latest native dual-client and cloud acceptance

Executor-supplied evidence against live Hub `24f317310ea6fdd66ca78da8cea3003a413d226c`; prior failures remain historical below. No private room identifiers, messages, screenshots or evidence paths are published.

| Gate | Result | Boundary |
| --- | --- | --- |
| Public Claude installer | passed | Download/hash/execution of `75a50bf` connect-chat.ps1; SHA-256 `492da745ab0629c1dd5fcceb318d22dbe31f349ec99b6b98f28ab9fb3c8099cc`. Explicit stdio type fixed reuse; earlier eddf failure preserved. Existing owned credential reused, no token reprompt |
| Live Claude + Codex dialogue | passed for observed sequence | Human event triggered both depth-1 replies, then both depth-2 follow-ups; new human event started another depth-1 exchange. Both exhausted 3/3 budgets and were disconnected |
| Native Codex CLI 0.160.0 | passed: three proof receipts | Each identity/full-read/post sequence used three native MCP calls. Operator helper reused its own DPAPI credential; this is not new interactive Codex installation UX acceptance |
| Native Claude Sonnet 5.5 Medium | passed | Actual public installer and native dialogue; watcher sources remain e24 |
| GUI language/composer | passed | English/Traditional Chinese toggles; Shift+Enter inserted newline without sending; Enter posted human message |
| ChatGPT native event action | passed: one event | Native event-triggered Automation, no cron/polling task; Hub-only human event at 23:30:49 produced ChatGPT Cloud reply at 23:31:24, without another Work prompt or SDK action |
| Cloud protocol/write-back | passed for one event | Active subscription and signed callback challenge; one outbox attempt, one delivered callback, replied receipt and processed cursor. Native unsubscribe and task paused after reply |

Initial cloud task creation failed with a generic task-service error; hostname-only gateway diagnostics identified callback_host_not_allowed while callback_hosts was empty. Only the observed exact callback hostname was added; TLS, public-DNS checks, validated-IP pinning, redirect refusal and challenge protections remained enabled. This resolved the observed refusal; it is not authority to allow arbitrary callback domains.

Cloud subscription, native action and write-back now passed for one event. Full lifecycle/expiry/offline/revocation/duplicate/burst acceptance remains pending. Earlier no-subscription/root-unresolved statements describe earlier attempts, not the current single-event result. Token counters still do not establish one prompt, billed usage or low-token optimization.


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
| P2-4 activation mismatch / project subdirectories | Source fixed at `e24b13c` | Explicit attempts record sanitized reasons; resolved project subdirectories are accepted. Native activation observed; nested-cwd native GUI case not separately exercised. |
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

Watcher `e24b13c418bad9705f86b589b1ac212145d06a71`, Hub `c4fe0f1`: a fresh official Claude Remote Control session (Sonnet 5.5 Medium) activated with the exact generated phrase and entered idle polling with zero model turns. A human browser message then triggered ToolSearch plus two native MCP calls (`chat_read`, `chat_reply`); full-text read reported `ready_to_reply=true`, reply actor was Claude and receipt was `replied`. Reply latency was approximately 16.646 seconds. No additional Claude prompt initiated the exchange. One bounded automatic exchange passed; the observed pause/resume, controlled application outage, three-turn budget and explicit disconnect sequence passed; independent STOP, full crash/restart and other lifecycle cases remain pending.

新官方 Claude Remote Control session activation 後 idle、零 model turns；人類瀏覽器訊息觸發 ToolSearch 與兩次 native MCP calls，完整 read/reply receipt 通過，約 16.646 秒。沒有額外 Claude prompt；一次有限自動 exchange passed，本次 pause/resume、controlled app outage、三輪 budget、disconnect passed；獨立 STOP、完整 crash/restart 與其他 lifecycle 仍 pending。

ChatGPT managed tunnel had stopped and was restarted ready at 22:47 +08:00. Plugin Refresh succeeded; updated notification schemas and `message.created` event discovery were visible. Fresh Work identity passed; no native event subscription was established in the tested Work conversation, and the model reported it could not subscribe. Root cause remains unresolved. Missing deferred tool names alone do not prove feature absence: `events/subscribe` is a protocol method. Acceptance requires an observed subscription request, verified callback and stored subscription, webhook `2xx`, and native action, as described in [official MCP Events testing](https://developers.openai.com/plugins/build/mcp-events#test-in-chatgpt). Idle automatic replies remain not_run. These are executor-supplied observations, with private identifiers, URLs, messages and screenshots omitted.

ChatGPT tunnel 重啟 ready，Plugin Refresh 成功，更新 schema 與 event discovery 可見；新 Work identity passed，但本次 Work 對話未建立原生 subscription，模型回報無法訂閱，根因仍未明。缺少 deferred tool 名稱不足以證明功能不存在：events/subscribe 是協定方法。需觀察訂閱請求、callback verification、保存 subscription、webhook 2xx 與原生動作；idle 自動回覆仍 not_run。以上為執行者提供的觀察，不公開私人證據內容。

## Final round-two boundary / 第二輪最終界線

[Latest validation](VALIDATION_2026-10-03.md) records runtime `24f3173` promotion and the native sequence against earlier Hub `c4fe0f1` plus watcher `e24b13c`. These are distinct version gates. Controlled outage recovery passed with the same binding and expiry; budget stopped a fourth turn for at least 37 seconds; disconnect stopped the owned watcher. This does not close parent/orphan, expiry, load, revocation or independent STOP acceptance. 新 runtime promotion 與先前 Hub 原生序列分開；有限 outage/budget/disconnect 證據不代表其餘生命週期關卡關閉。
