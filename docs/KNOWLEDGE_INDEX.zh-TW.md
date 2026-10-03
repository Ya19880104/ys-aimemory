# 知識索引、版本與檢索

[English](KNOWLEDGE_INDEX.md) | [繁體中文](KNOWLEDGE_INDEX.zh-TW.md)

## 0.2 搜尋路徑

`search_knowledge` 會使用 PostgreSQL 全文索引（simple tokenizer、plainto_tsquery 與 GIN），或測試模式的 SQLite FTS5。中文等 CJK 查詢走明確標示的字面子字串回退，並非向量或語意搜尋。其他無法交給全文 tokenizer 的查詢亦可能使用字面回退；以回應的 `search` 欄位為準。

輸入 query 是文字，不是可執行 SQL／FTS 語法。搜尋必須帶 project_id，服務端仍以登入身分的專案權限限制資料。`limit` 預設 50、上限 100；`offset` 上限 10000，後續頁使用 `next_offset`。

結果含來源或決策中繼資料、最多 500 字元摘錄、索引 revision，以及決策的狀態。待審提案只能作為非權威參考；全文命中不取代開工必須進行的 read_source、acknowledge、accept 和 validate。

## 原始資料與索引

0.1 的 JSON 專案資料仍是 canonical source；0.2 增加 SQL knowledge_documents、衍生全文索引與交易內處理的索引工作。來源／決策與索引在同一交易內一致更新。此版同步處理工作，不聲稱已有獨立背景 worker 或向量資料庫。

既有專案第一次被存取時會補建索引；資料結構變更採新增與冪等初始化，不刪除既有來源歷史、任務、封包或稽核。

`index_health` 查看 revision 與 canonical/document/FTS 筆數是否一致。這是健康指標，不是逐位元內容完整性證明。管理員可用 `reindex_project(project_id, expected_revision)` 從 canonical 資料重建衍生索引；不會憑空重新取得外部程式碼。

## 來源與任務查詢

- list_sources / list_tasks：project_id、可選 after_id、limit；回應 next_after_id 作為下一頁游標
- get_source_metadata：source_id、可選 before_version、limit；列出版本中繼資料，不返回整份來源內容
- get_project_summary：查看專案 revision、數量、稽核序號与索引狀態
- get_worker_inbox：取得目前身分待接手、持有與可認領任務

## 仍需注意

canonical JSON aggregate 仍有大規模資料量的效能限制；封包與來源版本長期增長後，需另做容量測試與正規化／保留政策。不要因新增全文索引，就宣稱整套系統已完成大量資料的效能驗收。pgvector、embedding 與自動掃描 Git repository 不在 0.2 實作範圍。
