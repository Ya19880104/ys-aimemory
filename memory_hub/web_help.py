"""Public onboarding and a strictly validated public CA download."""
from dataclasses import dataclass
import ipaddress
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from fastapi.responses import Response

from .web import e, page


CA_DOWNLOAD = "/downloads/ys-ai-memory-ca.crt"
BUNDLE_DOWNLOAD = "/downloads/ys-memory-stdio-1.1.0.zip"
MAX_CA_BYTES = 65536
_PEM_CERT = re.compile(rb"-----BEGIN CERTIFICATE-----\r?\n[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----")
_DNS_NAME = re.compile(r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


def public_base_url(value=None):
    """Return a configured HTTPS authority, never a request-derived origin."""
    value = os.getenv("HUB_PUBLIC_BASE_URL", "") if value is None else value
    if value == "":
        return "https://localhost"
    error = "HUB_PUBLIC_BASE_URL must be an HTTPS authority without credentials, path, query or fragment"
    if not isinstance(value, str) or any(ord(char) <= 32 or ord(char) == 127 for char in value):
        raise ValueError(error)
    try:
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
        if (parsed.scheme != "https" or not host or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or "?" in value or "#" in value
                or (port is not None and not 1 <= port <= 65535)):
            raise ValueError(error)
        try:
            address = ipaddress.ip_address(host)
            host = "[" + str(address) + "]" if address.version == 6 else str(address)
        except ValueError:
            if not _DNS_NAME.fullmatch(host):
                raise ValueError(error) from None
            host = host.lower()
        # Explicit empty ports and malformed bracket suffixes are not authorities.
        authority = host + (":" + str(port) if port is not None else "")
        if parsed.netloc.lower() != authority.lower():
            raise ValueError(error)
        return "https://" + authority
    except ValueError:
        raise ValueError(error) from None


@dataclass(frozen=True)
class PublicCA:
    pem: bytes
    fingerprint: str


def _public_ca(path):
    """A misconfigured private key, chain or leaf is never downloadable."""
    try:
        with Path(path).open("rb") as stream:
            content = stream.read(MAX_CA_BYTES + 1)
        if len(content) > MAX_CA_BYTES or not _PEM_CERT.fullmatch(content.strip()):
            return None
        certificate = x509.load_pem_x509_certificate(content)
        if not certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            return None
        fingerprint = ":".join(f"{byte:02X}" for byte in certificate.fingerprint(hashes.SHA256()))
        return PublicCA(certificate.public_bytes(serialization.Encoding.PEM), fingerprint)
    except (OSError, ValueError, x509.ExtensionNotFound, x509.DuplicateExtension):
        return None


def _manual(base, ca):
    codex = '[mcp_servers.ys_memory]\nurl = "' + base + '/mcp"\nbearer_token_env_var = "YS_AIMEMORY_TOKEN"'
    claude = json.dumps({"mcpServers": {"ys_memory": {"type": "http", "url": base + "/mcp",
                       "headers": {"Authorization": "Bearer ${YS_AIMEMORY_TOKEN}"}}}}, ensure_ascii=False, indent=2)
    send_example = json.dumps({"project_id": "conversation-sandbox", "recipient_worker_id": "agent-b",
                               "thread_id": "hello-20261002", "body": "你好，請回覆你收到的驗收碼 A-123。",
                               "idempotency_key": "a-hello-001", "reply_to_message_id": None},
                              ensure_ascii=False, indent=2)
    list_example = json.dumps({"project_id": "conversation-sandbox", "thread_id": "hello-20261002",
                               "after_sequence": 0, "limit": 20}, ensure_ascii=False, indent=2)
    ca_status = (f'<p><a class="button" href="{CA_DOWNLOAD}">下載公開 CA 憑證</a></p>'
                 f'<p>憑證 DER 的 SHA-256 指紋：</p><p class="path">{e(ca.fingerprint)}</p>') if ca else (
                 '<p class="alert">公開 CA 尚未提供。手冊仍可閱讀；請向管理者取得經確認的公開 CA，下載暫不可用。</p>')
    bundle_status = (f'<p><a id="stdio-bundle-download" class="button" href="{e(base + BUNDLE_DOWNLOAD)}">下載 Codex／Claude stdio 安裝包 1.1.0（HTTPS）</a></p>') if ca else (
                    '<p class="alert">公開 CA 尚未提供，stdio 安裝包暫不可用。請先聯絡管理者。</p>')
    bundle_download_command = 'curl.exe --cacert .\\ys-ai-memory-ca.crt --fail --output .\\ys-memory-stdio-1.1.0.zip "' + base + BUNDLE_DOWNLOAD + '"'
    bundle_install_command = r'''py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe .\bridge.py --compact --print-claude-config'''
    bundle_start_command = r'''$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Worker token' -AsSecureString)).Password
try { claude } finally { Remove-Item Env:YS_AIMEMORY_TOKEN -ErrorAction SilentlyContinue }'''
    fingerprint_command = r'''$pem = Get-Content .\ys-ai-memory-ca.crt -Raw
$der = [Convert]::FromBase64String(($pem -replace '-----BEGIN CERTIFICATE-----|-----END CERTIFICATE-----|\s',''))
$sha = [Security.Cryptography.SHA256]::Create()
([BitConverter]::ToString($sha.ComputeHash($der))).Replace('-', ':')
$sha.Dispose()'''
    process_command = r'''$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Worker token' -AsSecureString)).Password
$env:NODE_EXTRA_CA_CERTS = (Resolve-Path .\ys-ai-memory-ca.crt).Path
claude'''
    codex_command = r'''$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Worker token' -AsSecureString)).Password
$env:CODEX_CA_CERTIFICATE = (Resolve-Path .\ys-ai-memory-ca.crt).Path
codex'''
    return f'''<main class="management manual"><header><div><div class="eyebrow">YS AIMEMORY / 操作手冊</div>
<h1>建立記憶庫，讓每個 AI 明確接手</h1><p class="muted">先確認連線信任，再登入管理。此公開頁面不顯示 token，也不需要登入。</p></div>
<a class="button" href="{e(base)}/ui/mcp">開啟 HTTPS 記憶庫與 MCP 管理</a></header>
<nav class="panel" aria-label="手冊目錄"><a href="#trust">1. 憑證與安全連線</a><a href="#project">2. 建立記憶庫與身分</a><a href="#clients">3. 設定 AI 客戶端</a><a href="#memory">4. 登錄來源與任務</a><a href="#handoff">5. 接手與交接</a><a href="#messages">6. AI 私訊</a><a href="#tokens">7. Token 輪替</a><a href="#sessions">8. 共享聊天室</a><a href="#efficient">9. 按需接入與省 Token</a><a href="#accounts">10. 線上帳號管理</a></nav>
<section id="trust" class="panel"><h2>1. 先確認私有 CA</h2>
<p>目前連線使用私有 CA，客戶端需信任這個簽發者；這並非單純因為沒有網域名稱。HTTPS 也會核對憑證中的 IP 或主機名稱。若核對指紋後仍有憑證錯誤，請依錯誤確認效期、名稱與客戶端相容性，不要略過驗證。</p>
{ca_status}
<p class="alert">請透過可信通道向管理者取得 SHA-256 指紋，再比對下載的憑證。若本頁與下載經 HTTP 取得，本頁指紋也可能被替換，不能單靠同一個 HTTP 頁面建立信任。HTTP 只提供手冊與公開 CA；登入、token 與 API 一律走 HTTPS。</p>
<details><summary>Windows：計算同一種 DER SHA-256 指紋</summary><p>在下載目錄開啟 PowerShell，執行下列命令。這是憑證 DER 指紋，與直接對 PEM 檔案執行 Get-FileHash 的結果不同。</p><pre class="path"><code>{e(fingerprint_command)}</code></pre></details>
<p>不必為了使用工具先將 CA 安裝至整台 Windows。支援程序 CA 的客戶端可在啟動時指定這份公開檔案；下方提供 Codex CLI 與 Claude Code 的方式。瀏覽器若仍警告，先完成核對，再由你手動雙擊憑證 → 安裝憑證 → 目前使用者 → 受信任的根憑證授權單位。這會改變該使用者的信任，僅匯入已確認的 CA。</p>
<p>驗證成功後使用 <a href="{e(base)}/ui">{e(base)}/ui</a> 登入。若 URL、指紋或憑證效期不符，請向管理者確認後再連線。</p></section>
<section id="project" class="panel"><h2>2. 建立記憶庫與獨立 worker</h2>
<ol><li>在 HTTPS 登入後開啟 <a href="{e(base)}/ui/mcp">記憶庫與 MCP 管理</a>。管理者需先啟用此功能；未啟用時請聯絡管理者。</li>
<li>建立記憶庫（project），使用清楚的專案 ID。只有加入該記憶庫範圍的身分可以讀取或操作它。</li>
<li>為每個 AI 建立獨立 worker 身分和最小專案範圍。四個 AI 使用四個身分，各自使用自己的 clone/worktree 與 branch。</li>
<li>新 token 只顯示一次，請在當下存入自己的秘密儲存位置。不要貼到聊天、來源文件、版本庫或與其他 AI 共用。</li></ol>
<p>初始網頁帳號由部署者建立；後續使用<a href="#accounts">線上帳號管理</a>新增成員、調整範圍及管理密碼。網頁 cookie 與 AI 的 MCP token 是不同憑證。</p></section>
<section id="clients" class="panel"><h2>3. 設定 Codex／Claude Code</h2>
<p>MCP 位址：<code>{e(base)}/mcp</code>，伺服器傳輸為 Streamable HTTP。Codex 可直接連 HTTPS；Claude Code 可使用下方保留完整 TLS 驗證的 stdio 安裝包。先完成 CA 信任，範例皆不含可用 token。</p>
<h3>Codex：專案 HTTP 設定</h3><p>把此段合併到你選擇並信任的專案 <code>.codex/config.toml</code>；已有 <code>ys_memory</code> 時更新原項目，不要建立重複項目。讓啟動 Codex 的程序具有自己的 <code>YS_AIMEMORY_TOKEN</code>，不要把 token 明文寫入設定檔。本安裝流程不修改全域設定。</p><pre class="path"><code>{e(codex)}</code></pre>
<p>在自己的 PowerShell 視窗，指定已核對的公開 CA，再從同一視窗啟動 Codex CLI：</p><pre class="path"><code>{e(codex_command)}</code></pre>
<p>此設定只影響目前程序及其子程序，不會替另一個已開啟的桌面應用程式載入 CA。設定完成後仍須實測這個 MCP 端點。詳見 <a href="https://learn.chatgpt.com/docs/extend/mcp?surface=cli">Codex 官方 MCP 文件</a>與 <a href="https://learn.chatgpt.com/docs/auth#custom-ca-bundles">官方自訂 CA 說明</a>。</p>
<h3>Claude Code：安裝 stdio → HTTPS 轉接器</h3>
<p>本環境的 Claude CLI 2.1.278 直接 HTTP 連線曾回報 <code>UNSUPPORTED_CONSTRAINT_TYPE</code>（CA name constraints 相容錯誤）。<code>NODE_EXTRA_CA_CERTS</code> 可指定信任的 CA，不能修復 TLS runtime 對憑證限制的相容問題。不要關閉 TLS 或主機名驗證。</p>
{bundle_status}
<p>安裝包包含 <code>bridge.py</code>、<code>connection.json</code>、公開 CA、<code>requirements.lock</code> 與 <code>README.txt</code>。連線設定只記錄此伺服器 HTTPS 位址與 CA DER SHA-256，不含 token、私鑰或模型登入。轉接器核對 CA pin、憑證鏈與主機名，不跟隨轉址，不自動重試寫入。</p>
<details><summary>瀏覽器尚未信任 CA 時，使用已核對的公開 CA 下載</summary><p>先依第 1 節從可信通道核對 CA 指紋，再於放有該憑證的 PowerShell 目錄執行。ZIP 僅從 HTTPS 提供：</p><pre class="path"><code>{e(bundle_download_command)}</code></pre></details>
<ol><li>選擇自己的新目錄解壓 ZIP，保留檔案在同一層。不要覆寫既有安裝；目錄與虛擬環境不加入專案 Git。</li>
<li>安裝 Windows Python 3.12，在解壓目錄開啟 PowerShell，依序執行下方命令；依賴只安裝到此目錄的 <code>.venv</code>。</li>
<li>最後一個命令只顯示 Claude 設定，不連線、不需 token。把輸出的 <code>ys_memory</code> 項目手動合併到你要使用的專案 <code>.mcp.json</code>，保留其他 MCP 設定與 <code>${{YS_AIMEMORY_TOKEN}}</code> 引用；已有同名項目就更新它。</li>
<li>輸出使用本機 Python、bridge 與 connection 的絕對路徑。移動目錄或換電腦時，在新位置重新建環境、產生設定；不要沿用另一台電腦的路徑。</li></ol>
<pre class="path"><code id="stdio-install-example">{e(bundle_install_command)}</code></pre>
<p>接著在已合併 <code>.mcp.json</code> 的專案目錄開啟自己的 PowerShell，輸入該 AI 的 worker token 後啟動 Claude。token 僅存本次程序環境，結束後清除：</p><pre class="path"><code>{e(bundle_start_command)}</code></pre>
<p>由你審閱客戶端的專案信任與工具權限提示；安裝包不會自動核可工具、啟動模型或喚醒另一個 AI。已開啟的客戶端不會自動取得新環境；先保存工作，再依該客戶端方式重新載入此專案。模型供應商登入由各自官方客戶端管理，不能拿訂閱 cookie 或模型 API key 充當 Hub token。</p>
<p>CA 輪替時重新取得安裝包與可信通道的指紋，核對後在新目錄安裝；不自動更新 pin。Windows Python 3.12 是此流程的主要目標，Linux／macOS 的原生客戶端仍須各自驗收。</p>
<details><summary>其他已確認相容的 Claude HTTP 環境</summary><p>僅在該客戶端已證實支援此 CA 時，才在專案 <code>.mcp.json</code> 合併以下 HTTP 範例；不要與同名 stdio 項目並存：</p><pre class="path"><code>{e(claude)}</code></pre>
<p>在本機互動式 Claude Code 啟動前指定 CA：</p><pre class="path"><code>{e(process_command)}</code></pre>
<p><code>${{VAR}}</code> 可用於設定的 env／URL／header；未設定時不會取得有效身分。請核對 <a href="https://code.claude.com/docs/en/mcp#environment-variable-expansion-in-mcpjson">官方 MCP 設定</a>及 <a href="https://code.claude.com/docs/en/network-config#custom-ca-certificates">官方自訂 CA 說明</a>；背景或桌面託管環境的設定範圍另行確認。</p></details>
<p>一般模式以連線後的 <code>tools/list</code> 確認伺服器工具；省 Token 模式初始只有 <code>memory_tools</code> 與 <code>memory_call</code>，先搜尋需要的工具。設定成功不等於已通過原生模型端到端驗收。<a href="#efficient">按需接入方式</a>。</p></section>
<section id="memory" class="panel"><h2>4. 登錄來源、匯入記憶、建立任務</h2>
<ol><li>到 <a href="{e(base)}/ui/manage">專案管理</a> 選擇記憶庫。管理員可登錄來源或批次匯入；唯讀身分不能寫入。</li>
<li>每份來源填寫 <code>source_id</code>、完整 <code>content</code>、追溯用的 <code>uri</code> 與 <code>commit</code>。排除密碼、token、私鑰與不應共享的資料；系統不會自行抓取 URI 或掃描你的資料夾。</li>
<li>批次匯入使用來源 JSON 陣列，一批 1–20 份、內容合計最多 750,000 UTF-8 bytes。更新既有資料要以目前版本為準，遇到版本過期先重新讀取再決定。</li>
<li>建立任務，填寫目標、可改路徑、驗收條件與必要來源。路徑範圍是協作約定，不能替代作業系統權限。</li></ol>
<p>來源更新會讓舊 context 失效。搜尋摘錄不是完整來源；AI 必須重新取得並讀取必要來源快照。</p></section>
<section id="handoff" class="panel"><h2>5. 每一棒都重新開工與交接</h2>
<p>先查看 <code>get_worker_inbox</code>，再依序執行：</p><p class="path">prepare_task → claim_task → read_source（每份必要來源）→ acknowledge_context → accept_handoff → validate_task_context</p>
<p>完成這些步驟後才開始修改自己的工作區。租約或 context 失效時，先重新核對；長任務需續租。工作中保存 checkpoint，完成交接時填入指定接手者、摘要、來源雜湊、修改項目、結果 commit、真實測試結果、阻礙與下一步。</p>
<p>呼叫 <code>handoff_task</code> 後，舊持有者停止寫入；下一位使用自己的身分重新走完整流程。最後一位呼叫 <code>complete_task</code>，完成聲明仍須經獨立驗收。可在 <a href="{e(base)}/ui/inbox">收件匣</a> 和任務明細查看紀錄。</p>
<p>Hub 保存共同狀態，不會自行喚醒其他 AI，也不代表客戶端一直在線；由人類在下一個客戶端下達接手指示。</p></section>
<section id="messages" class="panel"><h2>6. 讓兩個 AI 實際收發訊息</h2>
<p>兩個 AI 使用同一記憶庫、各自的 worker token，透過 <code>send_message</code> 傳送、<code>list_messages</code> 收取持久化訊息。寄件者由 token 決定，不能在參數冒填其他身分，也不能寄給自己。worker、approver、admin 都只能看到本人寄出或收到的正文；同一 thread_id 不會讓旁人取得內容。audit 仍可保存寄收件人、thread、訊息 ID 等操作中繼資料，供有該專案 audit 權限的人查看。</p>
<ol><li>管理者先準備測試記憶庫 <code>conversation-sandbox</code> 與 <code>agent-a</code>、<code>agent-b</code> 兩個有效身分，兩者都需有該 project 權限。每次演練換新的 thread_id、驗收碼與 idempotency_key。</li>
<li>在 A 自己的 AI 客戶端要求它使用 MCP 的 <code>send_message</code>，傳送下方範例，記下回應的 <code>message_id</code>。</li>
<li>在 B 自己的客戶端要求它用 <code>list_messages</code> 讀取相同 project／thread。B 確認寄件者與驗收碼，再自行產生回覆，使用 <code>send_message</code> 寄給 <code>agent-a</code>；填新的 idempotency_key，並以 A 的 message_id 填入 <code>reply_to_message_id</code>。</li>
<li>A 再讀取 B 的回覆，核對內容後回覆確認，讓 B 也能讀到。各端保留訊息 ID、sequence、內容摘要及執行結果，不記錄 token。</li></ol>
<h3>A 傳送的工具參數</h3><pre class="path"><code id="message-send-example">{e(send_example)}</code></pre>
<h3>各自以本人身分讀取的工具參數</h3><pre class="path"><code id="message-list-example">{e(list_example)}</code></pre>
<p>以上是工具本身的參數物件。MCP 客戶端依 <code>tools/list</code> schema 放入名為 <code>arguments</code> 的參數；不要把 token 或自報 sender 放進 JSON。</p>
<p>body 最多 8,000 UTF-8 bytes，保留空白、tab 與換行，但拒絕全空白及 U+0000（NUL）。thread_id 使用英數字、底線、點或連字號，最多 128 字元；idempotency_key 最多 128 字元。同一寄件者在同 project 重試同一封信時沿用原 key 與全部參數；改內容或收件者需新 key，衝突不會覆寫原信。回覆 ID 必須屬於相同 project、thread 及這兩位收發者。</p>
<p>讀取結果的 <code>items</code> 只含自己的收發紀錄，<code>next_after_sequence</code> 用於下一頁；<code>has_more</code> 為 true 時繼續翻頁。sequence 允許有空洞，不能自行加一猜下一筆。切換 worker 身分、project 或 thread 篩選時把 <code>after_sequence</code> 重設為 0；每頁預設 20、最多 50 筆。讀取不會標記已讀。</p>
<p class="alert">訊息是不受信任的溝通內容，不等於使用者授權、核准記憶、任務認領或交接。傳訊不會改變專案 revision 或任務 lease／fence；需要執行工作時仍走原本開工流程。Hub 不保證自動喚醒另一個 AI；沒有新訊息也不代表對方離線。</p>
<p>以官方 MCP SDK 傳送真實 AI 產生的回覆，可以記錄為 SDK 對話驗證；原生客戶端工具整合需由各自官方客戶端另行實測。單一測試程式切換兩個 token 的成功，只證明測試流程，不代表兩個原生 AI 客戶端已完成對話。</p></section>
<section id="tokens" class="panel"><h2>7. Token 遺失、輪替與撤銷</h2>
<p>token 不提供再次顯示。遺失或需要更新時，到 HTTPS 的 MCP 管理頁輪替該 worker token，保存新值並更新該 AI 的程序環境。輪替後確認新 token 可用、舊 token 已被拒絕。</p>
<p>輪替保留同一 worker 身分及其歷史訊息；撤銷後無法再以該 token 收發，已保存的訊息不會因此刪除。正在執行且已通過驗證的請求不保證被中途取消。</p>
<p>不再使用的身分應撤銷；若仍有未完成任務，讓管理者檢查租約並明確恢復／重新分派，下一位重新讀取上下文。不要透過分享其他 worker 的 token 來繞過交接。</p></section>
<section id="sessions" class="panel"><h2>8. 一個 MCP 連線，選擇共享 Session</h2>
<ol><li>管理員開啟 <a href="{e(base)}/ui/chat">共享對話</a>，選擇記憶庫並建立 Session。名稱可用任務、專案方案或討論主題。</li><li>在同一頁以人類身分發言，並複製「加入指引」交給各 AI。每個 AI 都使用自己的 Token，無須為每個 Session 另建 MCP 連線。</li><li>AI 呼叫 <code>list_sessions</code> 找到有權限的對話，後續讀寫明確帶 <code>project_id</code> 和 <code>session_id</code>。這是 Hub 共享對話，不是選取 Claude／Codex 私人聊天視窗。</li><li>呼叫 <code>read_session</code> 取得新訊息，記住 <code>next_after_sequence</code>；下次填入 <code>after_sequence</code>。<code>post_session_message</code> 傳訊；回覆帶原訊息 ID，同一內容重試沿用相同 idempotency_key。</li><li>管理員畫面約每秒同步新訊息，不呼叫模型。AI 需在有工作時主動讀取；系統不會自動喚醒、代登入或無限循環呼叫模型。</li></ol>
<h3>把討論整理成共同成果</h3><p>右側可保存文件、方案、對話摘要、任務提案或交接提案，內容保留來源訊息及「涵蓋至」序號。這些成果不會自動成為已核准記憶或正式交接；正式任務仍從管理頁建立，AI 仍需通過原有讀取、認領與交接流程。</p>
<p>檔案上傳後立即對該專案授權成員及管理員可見，每檔最多 512 KiB、每 Session 最多 25 MiB。AI 透過 <code>read_session_attachment</code> 明確分段讀取；網頁以附件下載，不直接執行 HTML／SVG，也不解壓。附件隨資料庫備份保存。請勿上傳秘密。</p>
<p>既有 <code>send_message</code>／<code>list_messages</code> 維持私人收發可見性，不會自動搬進共享聊天室。</p></section>
<section id="efficient" class="panel"><h2>9. 有需要才接入，減少 Token</h2>
<p>安裝包以 <code>--compact --print-claude-config</code> 產生省 Token 模式：初始提供兩個小工具，不連 Hub、不讀任何對話；第一次實際工具呼叫才用自己的 Token 建立經完整 TLS 驗證的連線。此模式顯示 Connected 只代表本機 adapter 就緒，須實際呼叫確認 Hub 認證與連線。</p>
<ol><li><code>memory_tools</code> 搜尋 Session／任務相關工具，預設只回少量名稱與簡述；指定工具名稱才讀該工具 schema。</li><li><code>memory_call</code> 依剛讀到的 schema 呼叫。先列 Session，再讀最新摘要或增量紀錄；完整來源與附件需要時再取。</li><li>預設對話回傳每頁 20 則、每則最多 512 UTF-8 bytes 片段，總量也有限制。需要全文時用該訊息前一序號、<code>limit=1</code>、<code>full_text=true</code> 精讀，不反覆載入整段歷史。</li><li>摘要是有來源及涵蓋序號的共同文件；新訊息保留在摘要之後，系統不會每則呼叫模型自動重寫。空輪詢沒有新內容也仍有請求成本，AI 不應無限輪詢。</li></ol>
<p>若要平常連兩個小工具都不載入：Codex 的專案設定使用 <code>enabled=false</code>，需要時於該專案以 <code>codex -c 'mcp_servers.ys_memory.enabled=true'</code> 啟動。Claude 將配置保存為非自動載入的 <code>.mcp.ys-memory.json</code>，需要時用 <code>claude --strict-mcp-config --mcp-config .\\.mcp.ys-memory.json</code>。strict 模式只載入指定配置，若要其他 MCP 必須自行合併；兩種方式都不修改全域設定。</p>
<p>自然語言提到服務不保證會自動啟用一個已停用的 MCP。客戶端可能延後工具 schema，但仍預先連線；本機 adapter 的按需連線與「完全未載入」需分開看待。實際 Token 取決於模型 tokenizer，這裡用可驗證的筆數、UTF-8 bytes 與載入次數控制，不承諾固定節省比例。</p></section>
<section id="accounts" class="panel"><h2>10. 線上帳號管理</h2><p>具帳號管理能力的管理員到 <a href="{e(base)}/ui/users">帳號管理</a> 建立使用者、設定可見專案、角色、啟用／停用與重設密碼；使用者可到 <a href="{e(base)}/ui/account/password">我的密碼</a> 自行修改。</p><p>角色為管理員、成員、唯讀；成員可參與共享對話，唯讀不能發言。管理帳號的能力與專案資料權限分開，不能因此讀取所有記憶庫。停用、密碼、角色或範圍更新會使舊登入失效；保留歷史作者，不刪除身分。系統防止停用最後一位有效帳號管理員。</p><p>第一次升級會將原環境帳號匯入資料庫；後續以線上帳號為準，重啟服務不會用舊環境密碼覆蓋新密碼。AI worker Token 的輪替與撤銷仍在 MCP 產生器中獨立管理。</p></section>
<p class="foot">公開操作手冊 · 僅下載經驗證的公開 CA · 登入與所有操作使用 HTTPS</p></main>'''


def install_help(app):
    base = public_base_url()
    ca_path = os.getenv("HUB_PUBLIC_CA_FILE") or "/app/public/ys-ai-memory-ca.crt"

    @app.api_route("/help", methods=["GET", "HEAD"], include_in_schema=False)
    def help_page():
        return page(_manual(base, _public_ca(ca_path)))

    @app.api_route(CA_DOWNLOAD, methods=["GET", "HEAD"], include_in_schema=False)
    def download_ca():
        ca = _public_ca(ca_path)
        headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        if ca is None:
            return Response("Public CA unavailable", status_code=404, media_type="text/plain", headers=headers)
        headers["Content-Disposition"] = 'attachment; filename="ys-ai-memory-ca.crt"'
        return Response(ca.pem, media_type="application/x-x509-ca-cert", headers=headers)
