# On-demand MCP and efficient context

[English](EFFICIENT_MCP.md) | [繁體中文](EFFICIENT_MCP.zh-TW.md)

Keep MCP disabled for unrelated work using the official client's project controls. Mentioning memory does not enable a disabled server. Preserve other servers and avoid global changes as a shortcut.

Compact stdio initially exposes `memory_tools` for schema discovery and `memory_call` for forwarding. Adapter readiness does not prove upstream connectivity. Forwarded calls may write according to token authority; compact is not inherently read-only. Automatic room mode uses separate scoped tools.

Retrieve one schema, project/room metadata, relevant summaries, then bounded new messages. Open full messages, artifact sections, and attachment chunks only when needed. Use returned read cursors, never your own posted reply sequence. A summary covers only its explicit covered sequence.

Required-source admission remains complete read → acknowledge → accept → validate; search snippets and summaries do not replace it. Schema bytes, returned bytes, and billed model tokens are different measurements. Fewer initial schemas do not guarantee a fixed savings percentage or zero overhead. Background waiting should avoid model polling of empty rooms; provider platform costs remain outside the Hub's guarantees.

Record discovery, upstream identity, native invocation, and room read/write separately. SDK helpers prove protocol behavior rather than native model behavior. See [client setup](CLIENT_SETUP.md) and [native checks](NATIVE_CLIENT_CHECK.md).
