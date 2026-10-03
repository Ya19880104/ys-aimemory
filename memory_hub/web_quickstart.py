"""Public, beginner-oriented walkthrough with reviewed bundled screenshots."""
from html import escape
from importlib.resources import files

from fastapi.responses import Response

IMAGES = {
    'claude-native-identity-20261003.jpg': 'image/jpeg',
    'claude-native-tool-result-20261003.jpg': 'image/jpeg',
    'claude-message-receipt-20261003.jpg': 'image/jpeg',
    'hub-create-conversation-20261003.jpg': 'image/jpeg',
    'hub-automatic-conversation-20261003.jpg': 'image/jpeg',
    'claude-automatic-reply-20261003.jpg': 'image/jpeg',
}


def walkthrough(base):
    def figure(name, caption):
        src = escape(base + '/help/images/' + name, quote=True)
        return f'<figure><a href="{src}"><img src="{src}" alt="{escape(caption)}" loading="lazy" width="960"></a><figcaption>{escape(caption)}（點圖放大）</figcaption></figure>'

    return '''<section id="automatic-chat" class="panel"><h2>目前能用到哪裡？</h2>
<p><strong>已可使用：MCP 讀寫、共享對話、網頁同步。尚未完成：新訊息自動喚醒雙方 AI 並接續對話。</strong></p>
<p>網頁顯示「已同步」只表示這個頁面拿到了訊息；寫入收據只表示 Hub 已保存。兩者都不是另一位 AI 已收到或已回覆的證明。單則訊息的「引用」只是補充上下文，直接在輸入框發言即可。</p>
<p>目標流程是：你選專案及對話、啟用參與者 → 新訊息送達已加入的 AI → AI 自動接話 → 你可隨時插話或暫停。後續才保存文件或建立任務。</p>
<p><strong>最新實測：</strong>2026-10-03 已透過背景接線程式完成有限回合的自動接話。管理員只在網頁插話，Claude Desktop 自動回第 166 則，Codex 原生 CLI 自動回第 167 則，雙方再接續回第 168、169 則。Claude 使用已登入 Desktop；Codex 是專用 CLI，尚未驗證任意 Codex 桌面對話的喚醒。測試已停止，安裝、加入及暫停介面仍待整合；不能把這次原型通過當成一般安裝已支援。</p>''' + figure('hub-automatic-conversation-20261003.jpg', '背景接線原型實測：小克與小典接續討論；圖片是當時線上版本') + '''
</section><section id="quickstart" class="panel"><h2>第一次接入與手動讀寫驗證：五個步驟</h2>
<p>以下可確認 MCP 與共享紀錄正常，尚不是自動對話教學。設定一次 MCP 後，在網頁選一個對話，把「加入指引」貼給 AI；不用先建立任務或交接。</p>
<h3>1. 拿到自己 AI 的 Token</h3><p>登入後選專案，進入「MCP 接入 → Token 與客戶端設定」。為 Claude、Codex 各產生一個身分與 Token。Token 就像這個 AI 進入專案的鑰匙，不是網頁登入密碼。</p>
<h3>2. 安裝一次，貼入 MCP 設定</h3><p>從下方「接入 MCP」下載安裝包，解壓到新資料夾，依三行安裝命令產生設定。Claude 使用專案 <code>.mcp.json</code>；合併產生的設定、保留原本其他 MCP，以及 <code>${YS_AIMEMORY_TOKEN:-}</code> 引用。不要把實際 Token 寫進共享設定檔；加入 <code>.gitignore</code> 也不會解除既有 Git 追蹤。</p>
<p>接著到 Claude「新對話的環境選單 → Local 旁齒輪 → 環境編輯器」，新增名稱 <code>YS_AIMEMORY_TOKEN</code>，值填剛取得的 Claude Token 並保存。這裡填實際值，不是引用文字。它會作用於所有新的本機工作，請勿混用不同 worker。已登入 Desktop 的 Code 分頁不需要另登入 CLI。</p>
<h3>3. 開新 Claude 對話，確認連線</h3><p>選 Local 和剛設定的專案，開新對話。依畫面核准 MCP，貼上：</p>
<pre class="path"><code>使用 YS Memory MCP，確認我指定專案的 worker 身分。
先取得 get_worker_inbox 的 schema，再呼叫並告訴我 worker_id。
請依 schema 保留 arguments 層級，不要認領任務。</code></pre><p>把自己的專案 ID 一起告訴 AI。畫面出現實際工具結果與正確身分才算接入；只有 Connected 還不夠。</p>''' + figure('claude-native-tool-result-20261003.jpg', '實測：Claude 原生 MCP 回傳 agent-b；首次參數錯誤及修正結果均保留') + '''
<h3>4. 網頁建立對話，邀請 AI 加入</h3><p>進入「共享對話」，選專案，輸入主題後按「建立對話」。先在下方發一則需求，再按右側「複製加入指引」，貼到 Claude 和 Codex 各自的對話。這份指引帶的是專案與對話 ID，不需要重貼 Token。</p>''' + figure('hub-create-conversation-20261003.jpg', '實測：網頁管理員發需求，Claude 讀取後回覆同一主題') + '''
<h3>5. 驗證 AI 回覆與人類發言</h3><p>對 AI 說：「讀取這個對話的新訊息，回覆三句，真正寫回共享對話。」網頁會同步顯示。直接在下方發補充即可；「引用」只用來指明某則訊息。目前仍要在 AI 客戶端請它讀取這一輪，這是人工讀寫驗證。</p>
<pre class="path"><code>請從上次讀取的位置繼續讀新訊息，參考另一位 AI 和管理員的補充，
整理三點共識並寫回同一對話。只討論，先不修改程式。
不需要重讀全部歷史，完成這輪便停止。</code></pre>
<p>有共識後可在右側「建立文件／提案」保存方案；需要執行時才建立正式任務。Hub 會保存和同步訊息，但不會自行喚醒 AI，仍須在客戶端請它繼續。</p>
<p>截圖取自 2026-10-03 的線上測試：Claude Desktop 使用 Sonnet 5.5 / Medium；Codex 使用已登入的原生 CLI。圖片中的名稱和 ID 是範例，使用時選自己的專案。沒有以 SDK 代替模型回覆；未量測帳單 Token 節省比例。</p></section>'''


def install_walkthrough_images(app):
    @app.api_route('/help/images/{name}', methods=['GET', 'HEAD'], include_in_schema=False)
    def tutorial_image(name: str):
        if name not in IMAGES:
            return Response(status_code=404)
        content = files('memory_hub').joinpath('help_images', name).read_bytes()
        return Response(content, media_type=IMAGES[name], headers={
            'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'public, max-age=3600'})
