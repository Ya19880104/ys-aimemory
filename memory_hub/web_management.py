"""Explicit, role-scoped management forms sharing Hub authorization and gates."""
import hmac
import json
import secrets
from urllib.parse import urlencode
from fastapi import Request
from pydantic import ValidationError
from sqlalchemy import select
from .models import Principal
from .store import HubError, projects
from .web import e, page, badge, render_handoff, render_recovery

ACTIONS = {'project':'create_project', 'source':'register_source', 'import':'import_sources',
           'task':'create_task', 'approve':'approve_memory_change', 'recover':'recover_task'}


def link(path, **query):
    return e(path+'?'+urlencode(query))


def input_field(name, label, value='', textarea=False, required=True):
    attrs=' name="'+e(name)+'" id="'+e(name)+'"'+(' required' if required else '')
    control='<textarea'+attrs+'>'+e(value)+'</textarea>' if textarea else '<input'+attrs+' value="'+e(value)+'">'
    return '<label for="'+e(name)+'">'+e(label)+'</label>'+control


def hidden(name, value):
    return '<input type="hidden" name="'+e(name)+'" value="'+e(value)+'">'


def shell(title, body, project='', role='read_only'):
    return '<main class="management"><div class="eyebrow">YS-AIMEMORY / '+e(role)+'</div><h1>'+e(title)+'</h1>'+('<p class="project-context">目前專案 <strong>'+e(project)+'</strong></p>' if project else '')+'<p><a href="'+link('/ui',project=project)+'">← 總覽</a> · <a href="'+link('/ui/manage',project=project)+'">管理</a> · <a href="'+link('/ui/search',project=project)+'">搜尋</a> · <a href="'+link('/ui/inbox',project=project)+'">收件匣</a> · <a href="'+link('/ui/chat',project=project)+'">共享對話</a> · <a href="/ui/account/password">變更密碼</a></p>'+body+'</main>'


def install_management(app, hub, config, session, parse_form, redirect, auth, clock):
    def principal(current):
        identity = auth.principal(current)
        if identity is None: raise HubError('unauthorized', '登入已失效。', 401)
        if not identity.projects: raise HubError('forbidden', '尚無專案授權。', 403)
        return Principal(worker_id='human:' + identity.user_id, projects=list(identity.projects), role='admin' if identity.role=='admin' else 'worker')

    def scoped(project, current):
        identity = auth.principal(current)
        if identity is None or project not in identity.projects:
            raise HubError('forbidden','此專案不在網頁帳號授權範圍',403)

    def snapshot(project, current):
        scoped(project, current)
        with hub.store.engine.connect() as conn:
            state=conn.execute(select(projects.c.state).where(projects.c.id==project)).scalar_one_or_none()
        if state is None: raise HubError('not_found','專案尚未建立',404)
        return state

    def form_start(action, current, project, extra=None):
        token=secrets.token_urlsafe(24)
        auth.start_nonce(token,current,action,project)
        return '<form method="post" action="/ui/action/'+action+'">'+hidden('csrf',current['csrf'])+hidden('nonce',token)+hidden('project_id',project)+''.join(hidden(k,v) for k,v in (extra or {}).items())

    def flash(current):
        message=auth.pop_flash(current)
        return '<div class="alert" role="status">'+e(message)+'</div>' if message else ''

    def error(exc, project=''):
        return page(shell('無法完成請求','<div class="alert">'+e(exc.message)+'</div>',project,'read_only'),exc.status)

    def selected(request, current):
        identity = auth.principal(current)
        if identity is None: raise HubError('unauthorized', '登入已失效。', 401)
        project=request.query_params.get('project') or next(iter(identity.projects), '')
        scoped(project, current)
        return project

    @app.get('/ui/manage')
    def manage(request: Request):
        current=session(request)
        if not current: return redirect('/login')
        identity=auth.principal(current)
        if identity is None: return redirect('/login')
        try:
            project=selected(request, current)
            with hub.store.engine.connect() as conn:
                state=conn.execute(select(projects.c.state).where(projects.c.id==project)).scalar_one_or_none()
            body=flash(current)+'<form method="get"><label for="project">專案範圍</label><select id="project" name="project">'+''.join('<option'+(' selected' if p==project else '')+'>'+e(p)+'</option>' for p in identity.projects)+'</select><p><button>切換</button></p></form>'
            if identity.role!='admin':
                body+='<div class="alert">此帳號在專案管理頁為唯讀。管理表單需專案管理員角色；帳號權限由使用者管理員設定。</div>'
                return page(shell('專案管理',body,project,identity.role))
            if not state:
                body+='<section class="panel"><h2>建立專案 '+e(project)+'</h2><p>僅能建立配置中已授權的專案 ID。</p>'+form_start('project',current,project)+'<button>建立專案</button></form></section>'
                return page(shell('專案管理',body,project,identity.role))
            revision=state['revision']
            body+='<p>'+badge('目前脈絡 r'+str(revision))+' 更新來源、核准記憶或復原任務前會核對版本。</p><div class="grid">'
            body+='<section class="panel"><h2>登錄／更新來源</h2>'+form_start('source',current,project,{'expected_revision':revision})+input_field('source_id','來源 ID')+input_field('uri','來源位置（只記錄，不會自動抓取）')+input_field('commit','Commit／版本標記')+input_field('content','完整來源內容（未信任參考資料）',textarea=True)+'<p><button>儲存來源</button></p></form></section>'
            body+='<section class="panel"><h2>批次匯入來源</h2><p>貼上 JSON 陣列，每筆包含 source_id、content、uri、commit。最多 20 筆，內容合計最多 750 KB；表單 URL 編碼後仍須小於 1 MiB，中文長文請分批匯入。全部成功才提交；不會自動開啟外部網址。</p>'+form_start('import',current,project,{'expected_revision':revision})+input_field('sources_json','來源 JSON',textarea=True)+'<p><button>驗證並匯入</button></p></form></section>'
            body+='<section class="panel"><h2>建立任務</h2>'+form_start('task',current,project)+input_field('task_id','任務 ID')+input_field('goal','工作目標',textarea=True)+input_field('allowed_paths','允許路徑（每行一項）',textarea=True)+input_field('acceptance_criteria','驗收條件（每行一項）',textarea=True)+input_field('source_ids','必要來源 ID（每行一項）',textarea=True)+'<p><button>建立任務</button></p></form></section><section class="panel"><h2>待審提案</h2>'
            proposals=[d for d in state['decisions'].values() if d['status']=='proposed']
            for decision in proposals:
                body+='<div class="row"><p class="body-text">'+e(decision['text'])+'</p>'+badge('提案 r'+str(decision['binding']['context_revision']))+form_start('approve',current,project,{'decision_id':decision['decision_id'],'expected_revision':revision})+'<p><button>核准為權威記憶</button></p></form></div>'
            if not proposals: body+='<p class="muted">目前沒有待審提案</p>'
            body+='</section></div><div class="section-head"><h2>任務清單／管理復原</h2></div>'
            task_page=hub.call('list_tasks',{'project_id':project,'after_id':request.query_params.get('after') or None,'limit':20},principal(current))
            for task in task_page['items']:
                tid=task['task_id']
                body+='<div class="panel task"><a href="'+link('/ui/task',project=project,task=tid)+'">'+e(tid)+'</a> · '+e(task['goal'])+'</div>'
            if not task_page['items']: body+='<div class="empty">目前沒有任務</div>'
            body+='<p><a href="'+link('/ui/manage',project=project)+'">任務第一頁</a>'
            if task_page.get('next_after_id'): body+=' · <a href="'+link('/ui/manage',project=project,after=task_page['next_after_id'])+'">下一頁任務 →</a>'
            body+='</p>'
            return page(shell('專案管理',body,project,identity.role))
        except HubError as exc: return error(exc)
        except ValidationError: return error(HubError('invalid_page','分頁參數格式不正確',400))

    @app.post('/ui/action/{action}')
    async def mutate(action: str, request: Request):
        current=session(request)
        if not current: return redirect('/login')
        identity=auth.principal(current)
        if identity is None: return redirect('/login')
        if identity.role!='admin': return error(HubError('forbidden','此帳號沒有管理權限',403))
        if action not in ACTIONS: return error(HubError('not_found','未知的管理動作',404))
        values=await parse_form(request,max_bytes=1048576,max_fields=16)
        project=values.get('project_id','')
        try:
            scoped(project, current)
            if not hmac.compare_digest(values.get('csrf','').encode(),current['csrf'].encode()): raise HubError('csrf','表單驗證失敗，請重新載入頁面',403)
            if not auth.consume_nonce(values.get('nonce',''),current,action,project):
                raise HubError('duplicate_or_expired','表單已送出或已過期，請重新載入確認最新狀態',409)
            args={'project_id':project}
            if action=='source': args.update({k:values.get(k,'') for k in ('source_id','content','uri','commit')},expected_revision=int(values.get('expected_revision','')))
            elif action=='import':
                sources=json.loads(values.get('sources_json',''))
                if not isinstance(sources,list) or not 1<=len(sources)<=20: raise ValueError('invalid import list')
                args.update(sources=sources,expected_revision=int(values.get('expected_revision','')),idempotency_key=values['nonce'])
            elif action=='task':
                args.update(task_id=values.get('task_id',''),goal=values.get('goal',''))
                for key in ('allowed_paths','acceptance_criteria','source_ids'): args[key]=[line.strip() for line in values.get(key,'').splitlines() if line.strip()]
            elif action=='approve': args.update(decision_id=values.get('decision_id',''),expected_revision=int(values.get('expected_revision','')))
            elif action=='recover':
                args.update(task_id=values.get('task_id',''),reason=values.get('reason',''),to_worker=values.get('to_worker') or None)
                for key in ('expected_revision','expected_generation','expected_fence'): args[key]=int(values.get(key,''))
            hub.call(ACTIONS[action],args,principal(current))
            auth.set_flash(current,'操作成功，已儲存並更新最新狀態。')
        except HubError as exc:
            if exc.status==403: return error(exc,project)
            auth.set_flash(current,'未儲存：'+exc.message+'（'+exc.code+'）。請核對最新資料後重新提交。')
        except (ValueError,TypeError,ValidationError):
            auth.set_flash(current,'未儲存：表單或匯入資料格式不正確。請核對必填欄位、JSON 結構及數量限制。')
        return redirect('/ui/manage?'+urlencode({'project':project}))

    @app.get('/ui/search')
    def search(request: Request):
        current=session(request)
        if not current: return redirect('/login')
        identity=auth.principal(current)
        if identity is None: return redirect('/login')
        try:
            project=selected(request, current)
            query=request.query_params.get('q','')
            try: offset=max(0,int(request.query_params.get('offset','0')))
            except ValueError: raise HubError('invalid_page','頁碼格式不正確',400)
            if offset>10000: raise HubError('invalid_page','分頁位置超出範圍',400)
            body='<form><input type="hidden" name="project" value="'+e(project)+'">'+input_field('q','搜尋專案記憶',query)+'<p><button>搜尋</button></p></form>'
            if query:
                result=hub.call('search_knowledge',{'project_id':project,'query':query,'limit':20,'offset':offset},principal(current))
                matches=result.get('matches',[])
                body+='<p>'+badge('檢索引擎 '+str(result.get('search','unknown')))+badge('脈絡 r'+str(result.get('context_revision','?')))+'</p>'
                body+='<p class="muted">檢索結果不代表已完成 read_source 或已取得寫入資格。待審提案仍非權威記憶。</p>'
                for match in matches:
                    body+='<article class="panel task"><h3>'+e(match.get('source_id') or match.get('decision_id') or match.get('title','記憶'))+'</h3>'+badge(match.get('kind',''))+badge(match.get('status','來源參考'))+'<p class="body-text">'+e(match.get('excerpt') or match.get('text',''))+'</p><div class="path">'+e(match.get('uri',''))+'</div></article>'
                if not matches: body+='<div class="empty">沒有符合的記憶，請換個關鍵字</div>'
                body+='<p>'
                if offset: body+='<a href="'+link('/ui/search',project=project,q=query,offset=max(0,offset-20))+'">← 上一頁</a> '
                if result.get('next_offset') is not None: body+='<a href="'+link('/ui/search',project=project,q=query,offset=result['next_offset'])+'">下一頁 →</a>'
                body+='</p>'
            return page(shell('搜尋記憶',body,project,identity.role))
        except HubError as exc: return error(exc)
        except ValidationError: return error(HubError('invalid_query','搜尋詞長度必須為 1–200 字元',400))

    @app.get('/ui/inbox')
    def inbox(request: Request):
        current=session(request)
        if not current: return redirect('/login')
        identity=auth.principal(current)
        if identity is None: return redirect('/login')
        try:
            project=selected(request, current)
            state=snapshot(project, current)
            worker=request.query_params.get('worker','')
            candidates=sorted({p.worker_id for p in hub.principals if project in p.projects})
            if worker and worker not in candidates: raise HubError('not_found','找不到已設定的身分',404)
            body='<form>'+hidden('project',project)+'<label>依 AI 身分篩選</label><select name="worker"><option value="">全部身分</option>'+''.join('<option value="'+e(w)+'"'+(' selected' if worker==w else '')+'>'+e(w)+'</option>' for w in candidates)+'</select><p><button>篩選</button></p></form><p class="muted">這是管理檢視，不會代替 AI 認領或接受交接。</p>'
            groups=[('等待接手',lambda t:t.get('pending_recipient') and (not worker or t['pending_recipient']==worker)),('有效認領',lambda t:t.get('owner') and t.get('lease_until',0)>clock() and (not worker or t['owner']==worker)),('可認領／租約過期',lambda t:t.get('status')!='completed' and not t.get('pending_recipient') and (not t.get('owner') or t.get('lease_until',0)<=clock()))]
            for title,predicate in groups:
                body+='<section class="panel task"><h2>'+title+'</h2>'
                rows=[(tid,t) for tid,t in state['tasks'].items() if predicate(t)]
                for tid,t in rows: body+='<div class="row"><a href="'+link('/ui/task',project=project,task=tid)+'">'+e(tid)+'</a> · '+e(t['goal'])+'<div class="meta">'+e(t.get('pending_recipient') or t.get('owner') or '尚無持有者')+'</div></div>'
                if not rows: body+='<p class="muted">目前沒有符合項目</p>'
                body+='</section>'
            return page(shell('任務收件匣',body,project,identity.role))
        except HubError as exc: return error(exc)

    @app.get('/ui/task')
    def task_detail(request: Request):
        current=session(request)
        if not current: return redirect('/login')
        identity=auth.principal(current)
        if identity is None: return redirect('/login')
        try:
            project=selected(request, current); state=snapshot(project, current)
            tid=request.query_params.get('task',''); task=state['tasks'].get(tid)
            if not task: raise HubError('not_found','找不到任務',404)
            body='<section class="panel"><h2>'+e(tid)+'</h2><p>'+e(task['goal'])+'</p><p>'+badge(task['status'])+badge('fence '+str(task['fence']))+badge('generation '+str(task['generation']))+'</p><div class="meta">持有者 '+e(task.get('owner') or '—')+' · 指定接手 '+e(task.get('pending_recipient') or '—')+'</div><h3>允許路徑</h3><p class="path">'+e('\n'.join(task['allowed_paths']))+'</p><h3>驗收條件</h3><ul>'+''.join('<li>'+e(x)+'</li>' for x in task['acceptance_criteria'])+'</ul></section>'
            for handoff in task.get('handoffs',[]): body+=render_handoff(handoff)
            for recovery in task.get('recoveries',[]): body+=render_recovery(recovery)
            for cp in task.get('checkpoints',[]): body+='<div class="panel task"><h3>'+e(cp['kind'])+'</h3><p class="body-text">'+e(cp['summary'])+'</p><div class="path">'+e(cp['binding']['commit'])+'</div></div>'
            if identity.role=='admin':
                body+='<section class="panel"><h2>管理員復原／重新指定接手</h2><div class="alert">這會撤銷目前認領與舊 fence，讓舊持有者失去後續 Hub 寫入資格。請確認已與協作者核對。</div>'+form_start('recover',current,project,{'task_id':tid,'expected_revision':state['revision'],'expected_generation':task['generation'],'expected_fence':task['fence']})+input_field('reason','復原原因（寫入審計）',textarea=True)+'<label for="to_worker">重新指定接手者</label><select id="to_worker" name="to_worker"><option value="">開放重新認領</option>'+''.join('<option>'+e(w)+'</option>' for w in sorted({p.worker_id for p in hub.principals if project in p.projects}))+'</select><p><button>確認撤銷認領並復原</button></p></form></section>'
            return page(shell('任務詳情',body,project,identity.role))
        except HubError as exc: return error(exc)
