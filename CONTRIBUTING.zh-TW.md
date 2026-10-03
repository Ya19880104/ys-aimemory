# 參與 ys-aimemory

[English](CONTRIBUTING.md) | [繁體中文](CONTRIBUTING.zh-TW.md)

歡迎提出 Issue、功能建議及 Pull Request。先讀 `README.md`、`AGENTS.md` 與任務相關文件；專案是獨立的記憶／MCP Hub，不包含模型登入代理。

## 問題回報

在 [Issues](https://github.com/Ya19880104/ys-aimemory/issues) 提供 commit、OS／Python／客戶端版本、最小重現、預期與實際行為。標明測試是 SDK 還是原生模型工具呼叫；不要只以 Connected 作為成功證據。

不要附上 SSH／TLS 私鑰、token、cookie、`.env`、真實 DB／備份、含私密內容的聊天或完整主機設定。測試資料使用可拋棄合成值。疑似憑證外洩或安全漏洞請使用 repository 的私人漏洞回報入口，不在公開 Issue 貼秘密。

## 分支與 PR

```sh
git clone https://github.com/Ya19880104/ys-aimemory.git
cd ys-aimemory
git switch -c feat/your-change
```

分支可使用 `feat/`、`fix/`、`docs/`。保留工作區未提交變更，不覆寫別人的 branch。PR 說明具體行為、相容性、實際驗證及未測項；不自動部署或改動使用者資料。

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-tested.txt
python -m pip install --no-deps .
python -m pytest -q
python scripts/test-deployment.py
```

Windows 使用 `.venv\Scripts\python.exe`，無須 activate。PostgreSQL 測試只使用隔離資料庫，見部署文件及 GitHub Actions。skip 不算通過，Windows 測試不能代替 Linux／PostgreSQL 或瀏覽器驗收。

送出前檢查 `git diff --cached`；`.gitignore` 不能移除已加入歷史的秘密。不要提交個人 MCP 配置或機器專屬路徑。原交付 manifest 是歷史基線，不要重寫來掩蓋修改。
