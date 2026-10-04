"""Render actual delivery panel: retired bindings must not inflate current count."""
import json
import shutil
import subprocess
import pytest
from memory_hub.i18n import CATALOG, _locale
from memory_hub.web_chat_assets import chat_script
from test_queued_status import RENDER

NODE=shutil.which('node')
@pytest.mark.skipif(NODE is None,reason='Node required for shipped JavaScript')
@pytest.mark.parametrize('language',['en','zh-TW'])
@pytest.mark.parametrize('all_inactive',[True,False])
def test_current_count_and_collapsed_history(tmp_path,language,all_inactive):
    retired=['expired','disabled','disconnected','budget_exhausted','revoked','archived']*2
    people=[{'worker_id':f'old-{i}','status':status,'relay_online':True,
             'latest_delivery':{'status':'replied','through_sequence':7,'reply_sequence':8}}
            for i,status in enumerate(retired)]
    if not all_inactive:
        people += [{'worker_id':'online','status':'waiting','relay_online':True},
                   {'worker_id':'offline','status':'offline','relay_online':False},
                   {'worker_id':'paused-expired','status':'paused','enabled':True,'expires_at':1,'relay_online':True},
                   {'worker_id':'processing-last-turn','status':'processing','relay_online':True,'turns_used':3,'max_turns':3}]
    token=_locale.set(language)
    try:script=chat_script()
    finally:_locale.reset(token)
    harness=RENDER[:RENDER.index('process.stdout.write')]+r'''
function tree(n){return {tag:n.tag,text:n.textContent,open:n.open===true,children:n.children.map(tree)};}
process.stdout.write(JSON.stringify({title:$('delivery-title').textContent,panel:tree($('delivery-participants'))}));
'''
    p=tmp_path/'render.cjs';p.write_text(harness,encoding='utf8')
    r=subprocess.run([NODE,str(p)],input=json.dumps({'script':script,'people':people}),capture_output=True,text=True,encoding="utf-8",timeout=20)
    assert r.returncode==0,r.stderr
    view=json.loads(r.stdout);label=lambda k:CATALOG[k][language]
    assert view['title']==label('ui_c10d00000004')+('0' if all_inactive else '3')+' · '+label('ui_c10d00000005')+('0' if all_inactive else '2')
    history=view['panel']['children'][-1]
    assert history['tag']=='details' and not history['open']
    assert history['children'][0]['tag']=='summary'
    assert history['children'][0]['text']==label('ui_c10d00000006')+('12' if all_inactive else '13')
    assert 'old-0' in history['text'] and label('ui_a3bb7ab2cefc') in history['text']
    assert label('ui_c075b35fbea4')+'8' in history['text']
    assert all(child['tag']=='div' for child in view['panel']['children'][:-1])


@pytest.mark.skipif(NODE is None,reason='Node required for shipped JavaScript')
def test_expiry_moves_to_history_without_status_change(tmp_path):
    people=[{'worker_id':'paused-expiring','status':'paused','enabled':True,'expires_at':2,'relay_online':True}]
    token=_locale.set('en')
    try:script=chat_script()
    finally:_locale.reset(token)
    harness=RENDER[:RENDER.index('process.stdout.write')].replace("const context = vm.createContext({$, node, state, cfg: {dataset: {role: 'admin'}}});",
        "let now=1000;class Clock extends Date{static now(){return now;}};const context=vm.createContext({$,node,state,Date:Clock,cfg:{dataset:{role:'admin'}}});")
    harness += "const before=$('delivery-title').textContent;now=3000;vm.runInContext('renderDelivery();',context);process.stdout.write(JSON.stringify({before,after:$('delivery-title').textContent,history:$('delivery-participants').children[0].tag}));"
    p=tmp_path/'expiry.cjs';p.write_text(harness,encoding='utf8')
    r=subprocess.run([NODE,str(p)],input=json.dumps({'script':script,'people':people}),capture_output=True,text=True,encoding='utf8',timeout=20)
    assert r.returncode==0,r.stderr
    v=json.loads(r.stdout)
    assert 'Current receivers shown: 1' in v['before']
    assert 'Current receivers shown: 0' in v['after'] and v['history']=='details'
