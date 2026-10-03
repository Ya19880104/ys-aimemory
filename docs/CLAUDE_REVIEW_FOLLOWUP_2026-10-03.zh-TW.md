# Claude 交付審查追蹤：2026-10-03

[English](CLAUDE_REVIEW_FOLLOWUP_2026-10-03.md) | [繁體中文](CLAUDE_REVIEW_FOLLOWUP_2026-10-03.zh-TW.md)

來源查讀：`f5003e6`，Windows，2026-10-03。原私人審查對象為 `f16d496` 與當時未提交的 activation 改動；未讀 UI/i18n、路由、安裝器/launcher 或其他 worktree，只跑 22 個 SQLite 測試，沒有動態重現缺陷。本追蹤查讀現行原始碼與測試定義，沒有重跑產品測試，也不宣稱原生驗收。私人原報告不全文公開。

**判定：已有來源修正，兩項 P1 採替代政策，部分 P2 與原生驗收仍待完成。不能宣稱八項 P1 都依原建議關閉。** 執行環境證據見[驗證記錄](VALIDATION_2026-10-03.zh-TW.md)，適用其各自版本與環境。

## P1 對照

| 項目 | 現況 | 證據與界線 |
| --- | --- | --- |
| P1-1 暫時錯誤令 listener 結束 | 來源已修正 | `client_watch.py:watch` 對 transport/5xx/408/429 有有限退避，保留原 expiry；dispatch 409 重新 claim。`test_client_watch.py` 有 outage、pause race、expiry、撤銷測試；原生無人值守復原仍需觀察。 |
| P1-2 failed batch 無法復原 | 來源已修正 | `delivery_service.py` 明確 re-enable 將同範圍設為 retry-ready、清 attempts、撤銷舊 lease；`test_failed_batch_explicit_reenable_retries_same_range_and_fences_old_lease` 檢查 cursor/range。不是自動丟棄批次。 |
| P1-3 receipt 擠爆 byte budget | 來源已修正 | `session_service.py` 分頁先預留回條；`delivery_service.py:read_reservation` 提供 reserve/ceiling；near-limit pagination 測試覆蓋。單一過大事件仍可能需加 budget；Codex 僅允許真 budget error 後一次相同 scope read retry。 |
| P1-4 AI 互回循環 | 替代有限政策 | Server 決定 depth：人類/manual root 0，自動回覆 1/2，depth 2 不再觸發。保留短 AI follow-up，不是 human-only/@mention-only。測試覆蓋 ping-pong 與 mixed batch 新人類 root；兩原生客戶端仍需驗收。 |
| P1-5 setup 重播整房歷史 | 來源已修正 | `setup-chat.py` 預設 `after_sequence=None`，fresh join 從最新開始；明確 `--after-sequence 0` 才請求歷史。Renew/rejoin cursor 與 fresh join 分開驗收。 |
| P1-6 通用寫入工具預授權 | 來源已修正 | 自動 bridge 只開 `chat_status/chat_read/chat_reply`，注入 room/delivery/lease/cursor/key；setup 僅授予三個精確專案工具，不授予通用 `memory_call`。實際安裝 permissions 仍需查核。 |
| P1-7 到期連 manual post 都阻擋 | 替代明確 disconnect 政策 | 到期/failed/budget exhausted 保留 guard；owner/admin disconnect 撤銷未完成 delivery 後才允許 manual post。到期不自動解鎖。`test_expiry_guard_disconnect_manual_and_rejoin_preserve_unprocessed_messages` 覆蓋；明確不同於原建議。 |
| P1-8 回覆寫死繁中 | 來源已修正，採明確語系 | Setup 預設 en，接受 en/zh-TW；reminder 用配置語言。不是自動偵測最新人類訊息語言；不翻譯使用者訊息內容。 |

上述檔案分別位於 `memory_hub/`、`scripts/`、`tests/`。參閱[交付契約](DELIVERY_API.zh-TW.md)、[自動聊天](AUTOMATIC_CHAT.zh-TW.md)。

## P2 對照

| 項目 | 現況 | 證據／剩餘工作 |
| --- | --- | --- |
| P2-1 提前記 dispatch／孤兒 listener | 待完成 | stderr 前仍記 `handed_to_client`，只代表 relay dispatch 意圖，不能證明 wake/read；本追蹤未證明 parent-process liveness。 |
| P2-2 read 超過 claimed range | 來源已修正 | Reservation 傳入 `through_sequence`，delta ceiling 被限制；`test_new_message_during_turn_is_not_skipped_by_successful_reply` 確認新訊息仍待處理。 |
| P2-3 polling lock/write 負載 | 待完成 | Idle 約每 3 秒 claim、15 秒 heartbeat；未驗收 long-poll/notify 或負载 benchmark。原估計次數不是現況實測。 |
| P2-4 activation mismatch 無提示／子目錄 | 待完成 | `bind_activation` 仍要求精確 phrase/project cwd，mismatch 返回 false；沒有明確 activation_mismatch 診斷。 |
| P2-5 restart 等待 Stop | 文件部分說明；生命週期待驗收 | 指南要求 activation/reload，實作仍為 Stop hook；restart/resume/orphan 需原生測試。配置不是啟動證據。 |
| P2-6 reminder 假設 compact tools | 來源已修正 | 已改 narrow chat_read/chat_reply，與 automatic bridge 相符；仍須確認實際 immutable bundle/config。 |
| P2-7 receipt 不證明自動 wake | 保留證據界線 | tool_read/replied 證明協定操作；自動驗收需人類新事件、idle receiver、無額外 prompt 的原生執行。Bearer 或 dispatch 狀態本身不足。 |

## 剩餘驗收清單

- [ ] exact source/runtime commit、native client/version、時間、命令、退出碼、去秘密 receipt；passed/failed/skipped/not_run 分開。
- [ ] Claude idle wake：人類新事件、native narrow read/reply、完整 claimed range，無額外 prompt。
- [ ] 原生 outage/pause race/re-enable/disconnect、expiry guard、舊 lease 拒絕、crash/restart 不重複不漏訊息。
- [ ] 兩原生客戶端有限 depth-2 互回；新 topic root；fresh setup 不重播整房。
- [ ] 真正 installed bundle 的 permission/config 與錯房／錯 worker 拒絕。
- [ ] Parent/orphan、activation 診斷、startup/resume 提示與 polling 負載保留為明確工程待辦。
- [ ] ChatGPT event subscription/idle wake 獨立驗收；tunnel 可達與 prompted read/write 分開。
- [ ] GUI/i18n 另行審查驗收；原審查未讀這些介面。

約 59k 的 token 觀察需按 session 累計語意解讀：input/cache/output counters 是 session/tool exchange 的觀察，不證明單一 59k prompt、價格或實際帳單。保留精確 client/version 與 counter 語意；少量樣本不能推論節費或因果。低 token 最佳化仍待完成。
