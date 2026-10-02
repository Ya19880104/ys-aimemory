# 公開 CA 下載目錄

部署者可在此放置 `ys-ai-memory-ca.crt`，內容必須只有一張 PEM 格式的公開 CA 憑證，且 `BasicConstraints CA=true`。不要放 leaf certificate、憑證鏈、私鑰、token 或其他檔案。

Compose 只將此目錄以唯讀方式掛入 app 的 `/app/public`；app 不會掛載 nginx 的 TLS 私鑰目錄。此目錄除本說明外的檔案均不納入 Git。沒有有效公開 CA 時，`/help` 仍可閱讀，下載回應 404。

`HUB_PUBLIC_BASE_URL` 應設定為實際 HTTPS authority，例如 `https://hub.example.test:8443`；使用非預設 HTTPS port 時須一併填入。範例主機名需替換成自己的可解析主機。HTTP bootstrap 僅提供 GET／HEAD 的 `/help` 與 `/downloads/ys-ai-memory-ca.crt`，不提供登入或 API，也不重導 POST。

請透過可信的獨立通道交付這張憑證的 DER SHA-256 指紋。HTTP 頁面和下載不能自行證明 CA 可信。不要把 PEM 檔案 SHA-256 誤當成憑證 DER 指紋，也不要要求使用者略過 TLS 驗證。
