# 安全匯入與更新記憶

## 匯入的資料

每份來源使用明確 source_id、原始 content、uri 與 commit。服務不會自行抓取 URI，也不會依 URI 讀伺服器檔案；這些欄位用於追溯。請先挑選需要共享的規格、架構決策與交接文件，排除密碼、token、私鑰、客戶個資與不需共享的資料。

原始 content 的空白與換行會保留，SHA-256 依實際字元的 UTF-8 bytes 計算。不要把搜尋摘錄當成完整來源。

## 批次匯入

管理員呼叫 `import_sources`：

- project_id：已獲授權的專案
- expected_revision：目前專案 revision
- idempotency_key：這一次批次的唯一識別
- sources：1–20 份來源，每份包含 source_id/content/uri/commit

所有來源內容合計最多 750,000 UTF-8 bytes，HTTP 完整 JSON 另有 1 MiB 上限（JSON escaping 也計入）。過大批次應拆分；每批重新取得目前 revision 和使用新的 key。批次內不能有重複 source_id。

整批會先驗證，再於同一交易更新資料與索引；失敗不留下半套匯入。相同身分、專案、key 與完全相同請求重試，返回原結果，不重複增加來源版本、revision 或稽核。key 相同但資料不同會被拒絕。若要修改內容，使用新的 key 與最新 revision。

不要在 key 中放秘密；它是去重識別，並非授權憑證。

## 單份更新與比較門檻

`register_source` 建立新來源時可省略 expected_revision；修改已有來源內容／追溯欄位時需要它。完全相同的 upsert 回報 changed:false，不建立重複版本。過期 revision 應重新讀取最新資料、判斷差異後再提交，不能無限盲目重試。

來源變動使舊 task context 失效。工作中的 AI 必須重新 prepare、讀取必要來源並接受最新脈絡；不要用「只是更新文件」略過驗證。

## 網頁使用

網頁 admin 可新增單份來源，或貼上上述 sources JSON 陣列進行批次匯入。網頁仍套用相同服務端權限、revision 與交易驗證，並有 CSRF 及重送保護。唯讀角色不能匯入。0.2 不會自動掃描本機資料夾或遠端儲存庫；檔案來源選擇由操作者負責。
