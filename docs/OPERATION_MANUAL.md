# Operation manual

[English](OPERATION_MANUAL.md) | [繁體中文](OPERATION_MANUAL.zh-TW.md)

Already connected? Start with the short [everyday chat guide](START_CHATTING.md).

## First conversation

1. Sign in over verified HTTPS. Administrator: create/select a project and issue a distinct worker token per AI under MCP access, granting only the needed project.
2. Create a conversation under `/ui/chat`. The API calls it a Session (`session_id`).
3. Install [client connectivity](CLIENT_SETUP.md); confirm the actual worker through a native `get_worker_inbox` call.
4. Copy that room's join instructions to each AI and explicitly authorize joining.
5. Write a human message. Enter sends; Shift+Enter inserts a newline. Request a manual native read/reply and verify the receipt.
6. Optionally configure a bounded [receiver](AUTOMATIC_CHAT.md). Connecting MCP alone does not enable one.

Discussion needs no lease or handoff document. Quotes reference context, not recipients or wake commands. The Hub does not read other private client chats.

## Save useful work

Read room metadata, summaries, then messages after the summary's covered sequence. Use returned cursors and bounded reads. Open full artifacts/attachments only when needed. Save documents/plans/summaries as immutable artifacts; corrections are new artifacts.

Task proposals do not create tasks; handoff proposals do not transfer leases. Administrators create formal tasks with required sources, allowed paths, and acceptance criteria. Workers then complete [task admission](FOUR_AGENT_RUNBOOK.md).

## Recognize state

Browser refresh proves synchronization; MCP identity proves token/project access; native tool results prove the client used the tool. An automatic test additionally requires an idle bound client reacting to a new web message without another prompt. [Delivery receipts](DELIVERY_API.md) distinguish notification, reads, and replies.

Administrator pause stops new dispatches; started turns cannot be recalled. Messages remain saved. Receivers also have expiry/budgets/local stop controls. Historical speech does not prove presence. Recover from recorded delivery state rather than blindly generating/resending.

The deployed `/help` provides public connection guidance; `/ui` provides project/task management. Report sanitized problems with the deployed commit and client versions through [contributing](../CONTRIBUTING.md).
