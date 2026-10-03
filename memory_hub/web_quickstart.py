"""Public walkthrough with synthetic, code-native workflow illustrations."""
from .i18n import tr, documentation_url, locale
from html import escape
from importlib.resources import files

from fastapi.responses import Response

IMAGES = {
    'workflow-illustration.en.svg': 'image/svg+xml',
    'workflow-illustration.zh-TW.svg': 'image/svg+xml',
}


def daily_chat_guidance():
    return ('<section id="start-chatting" class="panel"><h2>'+tr('daily_chat_title')+'</h2>'
            '<ol><li>'+tr('daily_chat_connect')+'</li><li>'+tr('daily_chat_choose')+'</li>'
            '<li>'+tr('daily_chat_check')+'</li></ol><pre class="path"><code>'
            +tr('daily_chat_prompt')+'</code></pre><p>'+tr('daily_chat_limits')
            +'</p><p><a href="'+documentation_url('START_CHATTING.zh-TW.md')+'">'
            +tr('daily_chat_guide')+'</a></p></section>')


def automatic_client_guidance():
    return ('<h3>'+tr('automatic_client_setup_title')+'</h3><p>'
            +tr('automatic_claude_setup')+'</p><p>'+tr('automatic_codex_cloud_setup')
            +'</p><p><a href="'+documentation_url('AUTOMATIC_CHAT.zh-TW.md')+'">'
            +tr('automatic_setup_guide')+'</a></p><p>'+tr('automatic_recovery_upgrade')
            +'</p><p>'+tr('automatic_expired_manual')+'</p>')


def walkthrough(base):
    def figure(caption):
        name = "workflow-illustration." + locale() + ".svg"
        src = escape(base + '/help/images/' + name, quote=True)
        return f'''<figure><a href="{src}"><img src="{src}" alt="{escape(caption)}" loading="lazy" width="960"></a><figcaption>{escape(caption)}{tr('ui_6e030bf110f0') + '</figcaption></figure>'}'''

    return ('<section id="local-claude-setup" class="panel"><h2>' + tr('ui_6b817627be35') + '</h2>\n<p>' + tr('ui_fed108c9f6c0') + '</p>\n<p>' + tr('ui_9f23b3ebe161') + '</p>\n<pre class="path"><code>' + tr('ui_9e5e7a0587ab') + '</code></pre>\n<p>' + tr('ui_5cbfd5797808') + '</p>\n<p>' + tr('ui_ca6a74d7fc7b') + ('</p>\n<p><a href="' + documentation_url('CLAUDE_WINDOWS_SETUP.zh-TW.md') + '">') + tr('ui_bb247a3cecf0') + '</a>' + tr('ui_ed8d330d236a') + '</p>') + figure(tr('tutorial_workflow_illustration_caption')) + ('</section><section id="automatic-chat" class="panel"><h2>' + tr('ui_30e78e200eac') + '</h2>\n<p><strong>' + tr('ui_2b449d1e59c3') + '</strong></p>' + automatic_client_guidance() + '\n<p>' + tr('ui_4980986a0ae7') + '</p>\n<p>' + tr('ui_6b6761fdef8b') + '</p>\n<p><strong>' + tr('ui_9f7b24152d32') + '</strong>' + tr('ui_e010e1bc6bd9') + '</p>') + ('\n</section><section id="quickstart" class="panel"><h2>' + tr('ui_dce1ec683f94') + '</h2>\n<p>' + tr('ui_9416d307c981') + '</p>\n<h3>' + tr('ui_bfce900ae2c0') + '</h3><p>' + tr('ui_382f531bd0b7') + '</p>\n<h3>' + tr('ui_cf73e67ff559') + '</h3><p>' + tr('ui_83ab778e6b5b') + '<code>.mcp.json</code>' + tr('ui_513744d16031') + '<code>${YS_AIMEMORY_TOKEN:-}</code>' + tr('ui_19d2dfca51cf') + '<code>.gitignore</code>' + tr('ui_cc9383d1892f') + '</p>\n<p>' + tr('ui_f16c0a5ef9b6') + '<code>YS_AIMEMORY_TOKEN</code>' + tr('ui_2935b451b4cf') + '</p>\n<h3>' + tr('ui_c7109df93284') + '</h3><p>' + tr('ui_1fec4e9a1741') + '</p>\n<pre class="path"><code>' + tr('ui_01537db4d545') + '</code></pre><p>' + tr('ui_6aaab69721e9') + '</p>') + ('\n<h3>' + tr('ui_8d049e50bca1') + '</h3><p>' + tr('ui_e29fc18824ef') + '</p>') + ('\n<h3>' + tr('ui_1b920cfb95a4') + '</h3><p>' + tr('ui_69b7a90bae20') + '</p>\n<pre class="path"><code>' + tr('ui_be85d7e24394') + '</code></pre>\n<p>' + tr('ui_6a9f51cb0870') + '</p>\n<p>' + tr('ui_83e9e6e03b78') + '</p></section>')


def install_walkthrough_images(app):
    @app.api_route('/help/images/{name}', methods=['GET', 'HEAD'], include_in_schema=False)
    def tutorial_image(name: str):
        if name not in IMAGES:
            return Response(status_code=404)
        content = files('memory_hub').joinpath('help_images', name).read_bytes()
        return Response(content, media_type=IMAGES[name], headers={
            'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'public, max-age=3600',
            'Content-Security-Policy': "default-src 'none'; sandbox"})
