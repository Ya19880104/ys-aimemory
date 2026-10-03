# Multi-agent task admission and handoff

[English](FOUR_AGENT_RUNBOOK.md) | [繁體中文](FOUR_AGENT_RUNBOOK.zh-TW.md)

Give every worker its own token, clone/worktree, branch, and allowed path scope. Never share a writable checkout. Coordinator/implementer/reviewer/tester are rotating work roles, not security permissions.

## Start or resume

1. `get_worker_inbox`: discover owned, available, and assigned tasks.
2. `prepare_task`: supply actual workspace/branch/commit and obtain a fresh packet.
3. `claim_task`: obtain a valid lease and fence; only one competing claimant succeeds.
4. `read_source`: read every required source in that packet.
5. `acknowledge_context`, then `accept_handoff`.
6. `validate_task_context`: verify current packet/lease/fence before writes.

Read `skills/hub-task-start/SKILL.md`. A packet is not a claim. A read receipt is not proof of understanding. Stale revision, expired lease, or conflicting scope means stop new writes, preserve work, and revalidate. Renew during long work.

## Deliver

Use `record_checkpoint` for progress and `handoff_task` for explicit transfer. Include required-source hash evidence, result commit, changed artifacts, actual test commands/results, blockers, and nonempty next steps. The old holder stops after handoff; the recipient completes fresh admission. Use `skills/hub-task-handoff/SKILL.md`. A chat message or artifact proposal does not transfer custody.

Review/testing uses `skills/hub-review-accept/SKILL.md` and independent evidence. Pending proposals are not approved knowledge; completion declarations do not replace acceptance.

## Offline recipient

Only administrators use `recover_task` with current revision/generation/fence and a nonempty reason. Reassign to a known worker or clear assignment; old leases/packets become invalid. Completed tasks cannot be reopened. Never use recovery to silently widen scope; changed requirements require an explicit new task.

No Hub: report unavailable, not claimed/leased/validated. Authorized local bootstrap can proceed only under the user's stated scope, without fabricated server admission.
