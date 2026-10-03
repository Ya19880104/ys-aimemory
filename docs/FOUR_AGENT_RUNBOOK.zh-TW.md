# 四 AI 開工、交接、驗收手冊

[English](FOUR_AGENT_RUNBOOK.md) | [繁體中文](FOUR_AGENT_RUNBOOK.zh-TW.md)

## 首次分配

人類確認四個固定 worker ID、各自允許的 project、使用的客戶端、clone 目錄與 branch。不要共享登入憑證或共用一枚 worker token。設定安全權限時需人類另行核准；分配工作角色不變更安全權限。

每個任務的上下文至少包含：目標、不做的事、允許改動路徑、基底 commit、輸入 source IDs、驗收條件、目前工作角色、交接對象。先把這些寫成可追溯來源；不要只放在其中一個聊天視窗。資料庫快照以專案 revision/hash 追蹤，Git 有 commit，兩者都要核對。

## 四個角色讀什麼

| 角色 | 共同必讀之外的輸入 | 交付 |
|---|---|---|
| coordinator | 需求、任務依賴、已核准決策、前次交接 | 小而完整的任務切分、唯一寫入者、驗收路徑 |
| implementer | 介面契約、允許路徑、現行原始碼與測試 | 最小變更、確切 commit、測試證據、限制 |
| reviewer | 原需求、基底與提交 diff、風險、實作證據 | 具檔案位置的發現、嚴重度、可重現步驟 |
| tester | 驗收條件、待驗 commit、執行環境、已知限制 | 實際命令、退出碼、日誌位置與未測項 |

共同必讀：本手冊、最新任務封包列出的所有 required sources、目前 scope、最近 checkpoint/handoff。reviewer 不因職稱自動有核准記憶或合併的權限；tester 也不能自行批准部署。

## 每次開工必經

1. 確認目前工具連的是正確 Hub/project，列出工具 schema。若沒有連線，不宣稱取得有效租約；可閱讀本機資料，不能假裝通過中央門檻。
2. 呼叫 `get_worker_inbox(project_id)` 查看自己的待接手／持有／可用任務，選取本次授權的 task。再檢查工作區路徑、branch、HEAD、dirty 狀態。使用自己的 clone。發現他人的未提交變更就停下釐清。
3. `prepare_task` 建立綁定自己身分、task、workspace、branch、commit 的封包。
4. `claim_task` 取得租約與 fence。已有別人有效租約時不搶寫；等交接或向負責人回報。
5. 對封包列出的每一份來源呼叫 `read_source`，閱讀實際內容，比對 revision/hash；不能只讀摘要或宣稱讀過。
6. `acknowledge_context`，再 `accept_handoff`。首次任務也需明確接受；交接後的新 worker 必須重新 prepare/read/ack/accept，不能沿用前人的 packet。
7. `validate_task_context` 成功後才開始自己 scope 內的工作。有效期內以 `renew_lease` 續租；每次準備寫入中央紀錄、恢復中斷、收到來源變更或交接前再驗證；長工作在有效期內用 `renew_lease` 續租。
8. 被拒絕時保留本機成果但停止新的協作寫入。重新準備最新封包、重讀變更來源與重新認領，逐項比對舊工作是否仍符合需求；不能只替換 revision 數字繞過檢查。

來源修訂後，即使本機 Markdown 看似相同，也不要沿用舊讀取確認。封包中的 workspace/commit 是客戶端申報資料，Hub 不會替你執行 `git status`；必須實際核對。

## Checkpoint 與交接內容

每個 checkpoint 應有可供接手的摘要：

```text
task / worker / 工作角色：
packet / context revision / fence：
repo / workspace / branch / base SHA / current SHA：
目標與允許路徑：
已完成：
修改檔案與原因：
測試：命令、環境、退出碼、時間、日誌／artifact URI
未執行的測試與原因：
已知問題、未核准提案、阻塞：
下一步與接手者：
驗收條件對照：
依據：source_id + sha256
```

`evidence[]` 是來源 hash 參照，不能證明測試真的跑過。測試輸出另存去除秘密的日誌／artifact，在摘要標明位置與 commit；如要成為 Hub 的版本化證據，請有權限者登錄為 task 已要求的 source（更新會讓舊封包失效），或建立新的驗收 task。不得用「預期會通過」冒充已通過。

交接另填 `changed_artifacts`、`result_commit`、`test_results`（command/status/details）、`blockers`、`next_steps`。test status 只用 passed、failed、not_run；至少一個 test_results，未測就明確填 not_run 與原因。next_steps 至少一項。

呼叫 `record_checkpoint` 保存階段成果，`handoff_task` 明確指定下一個 worker。交接釋放持有者並更新 fence；原 worker 不再有權沿用舊 fence 寫入。接手者讀目前任務與交接後走完整開工流程。

## 最終驗收與回退

接收交接不是最終驗收。人類或獲授權負責人將需求逐項對照實作、審查、測試的同一 commit；確認範圍、未解決風險、部署是否另需授權，再決定接受／退回。Hub 的 checkpoint／`complete_task` 可記錄此結果；complete 只代表持有者宣告完成，但不要把它宣稱為受保護分支已合併或已上線。

退回時寫清楚具體缺口、重現方式與下一位唯一寫入者，重新交接。核准記憶變更只透過 `propose_memory_change` → 有權限者 `approve_memory_change`；工作 AI 不能把自身推測覆蓋正式文件。

## 任務開始提示詞

「請使用 hub-task-start。你的 worker 身分由連線設定決定；本次工作角色是 implementer。先確認 project/task、工作區、branch、HEAD 與 scope，prepare/claim/read/acknowledge/accept/validate 通過再工作。只改允許的路徑。任何來源過期、租約失效或 scope 衝突都停止並回報。交付確切 commit、測試證據與下一步；未核准提案不可當正式需求。」

## 原型復原限制

已完成任務沒有重開工具；任務定義沒有編輯工具。若需重做已完成任務或調整任務定義，先保留原紀錄，以新 task 記錄替代與關聯；新任務不能掩蓋原任務仍未驗收。尚未完成但指定接手者無法回應的任務，可由 admin 依下節使用 `recover_task` 重新指定或解除指定，不需要直接改資料庫，也不得共用他人 token 繞過流程。

## 接手者離線或退役

不要用另一位 worker 假裝接手身分，也不要修改資料庫狀態。交由 admin 取得最新 task generation/fence 與專案 revision，以 `recover_task` 附原因重新指定或解除指定。舊持有者不可繼續提交；新接手者重做完整閱讀與接受流程。此工具不會重新開啟已完成任務，完整欄位見 API 文件。
