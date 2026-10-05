"""Trusted static room assets; remote text is inserted through textContent only."""

CHAT_CSS = '''
/* Shared workspace: quiet dark surfaces, mint actions, conversation-first layout. */
:root{--chat-surface:#101722;--chat-nav:#0e1520;--chat-selected:#1b302d;--chat-human:#142720;--chat-error-bg:#462c28;--chat-error-text:#ffd2c7}
html,body{overflow-x:clip}
.chat-app{height:100dvh;display:flex;flex-direction:column}
.chat-app button,.chat-top nav a{white-space:nowrap}
.chat-top{display:flex;min-height:68px;padding:12px 24px;margin:0;border-bottom:1px solid var(--line);flex-shrink:0;gap:16px}
.chat-top>div{display:flex;align-items:center;gap:20px;min-width:0}
.chat-title{color:var(--muted);font-size:13px;white-space:nowrap}
.chat-top nav{display:flex;gap:3px;margin:0;flex-wrap:wrap}.chat-top nav a{font-size:12px;padding:6px 9px}
.chat-workspace{display:grid;grid-template-columns:236px minmax(0,1fr) 300px;min-height:0;flex:1}
.room-nav,.room-context{padding:24px 18px;overflow-y:auto;min-width:0}
.room-nav{border-right:1px solid var(--line);background:var(--chat-nav)}
.room-nav h1{font-size:21px;letter-spacing:0}.room-nav label{font-size:12px;color:var(--muted);margin-top:14px}
.room-nav input,.room-nav select{padding:9px 10px;font-size:13px;min-width:0}
.room-nav button{font-size:12px;padding:8px 12px;margin-top:8px}
#create-room{padding-bottom:20px;border-bottom:1px solid var(--line)}#create-room button{width:100%}
#room-list{margin-top:12px}.room-choice{display:block;width:100%;text-align:left!important;background:transparent;color:var(--text);border:1px solid transparent;border-left-width:3px;border-radius:8px;padding:12px!important;white-space:normal!important;overflow-wrap:anywhere;line-height:1.6}
.room-choice:hover{background:var(--panel)}.room-choice.selected{background:var(--chat-selected);border-color:var(--line);border-left-color:var(--accent)}
.room-choice small{display:block;font-size:11px;font-weight:400;margin-top:5px}
.room-note{font-size:12px;color:var(--muted);line-height:1.75;overflow-wrap:anywhere}
.room-main{padding:0;display:flex;flex-direction:column;min-height:0;min-width:0;background:var(--chat-surface)}
.room-heading{display:flex;padding:23px 28px 18px;margin:0;align-items:flex-start;border-bottom:1px solid var(--line);gap:14px}
.room-heading>div{min-width:0}.room-heading h2{font-size:23px;line-height:1.5;margin-top:5px;overflow-wrap:anywhere}
#room-visibility{font-size:12px;color:var(--muted);margin:7px 0 0}
.room-heading button{background:transparent;color:var(--muted);border:1px solid var(--line);font-size:12px;padding:5px 10px;flex-shrink:0}
.sync-bar{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 28px;color:var(--muted);font-size:11px}
.sync-bar button{padding:4px 0;font-size:12px;background:transparent;color:var(--accent);flex-shrink:0}
.delivery-notice{margin:0 28px 8px;padding:9px 12px;border-left:2px solid var(--accent);background:var(--panel);font-size:12px;line-height:1.6;max-height:230px;overflow:auto}
.delivery-heading{display:flex;align-items:center;justify-content:space-between;gap:8px}.delivery-heading button{padding:5px 9px;font-size:11px}
.delivery-notice p{margin:4px 0;color:var(--muted)}.delivery-notice a{font-size:11px}.delivery-notice summary{cursor:pointer;font-size:11px;color:var(--muted);margin-top:6px}
.delivery-participant{display:flex;flex-wrap:wrap;gap:3px 9px;padding:5px 0;border-top:1px solid var(--line)}.delivery-participant small{color:var(--muted)}.delivery-participant .receipt{color:var(--accent)}
#chat-error{margin:0 20px 8px;background:var(--chat-error-bg);padding:10px 13px;color:var(--chat-error-text);font-size:13px;border-radius:8px;overflow-wrap:anywhere}
#chat-stream{overflow-y:auto;flex:1;min-height:180px;padding:8px 28px 24px;scroll-behavior:auto}
.chat-empty{color:var(--muted);text-align:center;margin:60px auto;max-width:410px;font-size:15px}.chat-empty strong{display:block;color:var(--text);font-size:20px;margin-bottom:12px}.chat-empty p{font-size:13px;line-height:1.9}
.chat-event{margin:12px 0 20px;padding:15px 17px;background:var(--panel);border:1px solid var(--line);border-radius:12px}
.chat-event.human{background:var(--chat-human);border-left:3px solid var(--accent)}
.chat-event.system-event{background:transparent;border-style:dashed;padding:12px 16px}
.chat-event header{display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-start;gap:5px 9px;margin:0 0 9px}
.actor-mark{font-size:10px;background:var(--chat-selected);padding:1px 6px;border-radius:4px;color:var(--accent);white-space:nowrap}
.actor-name{font-size:13px;font-weight:650;overflow-wrap:anywhere;min-width:0}.actor-id{font-size:10px;color:var(--muted);overflow-wrap:anywhere}.chat-event time{font-size:11px;color:var(--muted);margin-left:auto}
.chat-message{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.85}
.chat-event button.reply-button{display:block;margin-top:9px;background:transparent;color:var(--muted);font-size:11px;padding:2px 0}
.chat-event .event-label{font-size:13px;color:var(--accent)}.chat-event button.event-label{background:transparent;color:var(--accent);text-align:left;white-space:normal;padding:0;overflow-wrap:anywhere}
.reply-ref{font-size:12px;color:var(--muted);border-left:2px solid var(--accent);padding-left:9px;margin:5px 0 10px}
.composer{padding:16px 26px 13px;border-top:1px solid var(--line);background:var(--chat-nav)}
.composer-by{font-size:12px;color:var(--muted);margin-bottom:9px}.composer-by strong{color:var(--text)}
.composer textarea{font-size:14px;min-height:80px;max-height:180px;padding:12px;resize:vertical}
.composer-tools{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-top:9px}
.composer-tools button{padding:8px 16px;font-size:13px;flex:0 0 auto;margin-left:auto}
.composer-tools>div{display:flex;gap:7px;align-items:center;flex-wrap:wrap;min-width:0;flex:1 1 210px}
.file-control{display:inline;color:var(--muted);font-size:12px;margin:0;white-space:nowrap}
.composer input[type=file]{width:100%;max-width:225px;min-width:0;font-size:11px;padding:3px;border:0}
#file-status{font-size:12px;color:var(--accent);overflow-wrap:anywhere;flex-basis:100%}
.composer>.room-note{margin:7px 0 0;font-size:11px}
#reply-preview{font-size:12px;margin:5px 0;color:var(--muted)}#reply-preview button{padding:0 6px;margin-left:10px;background:transparent;color:var(--accent)}
.room-context{border-left:1px solid var(--line);font-size:13px;background:var(--bg)}
.context-section{padding-bottom:23px;margin-bottom:22px;border-bottom:1px solid var(--line)}
.room-context h2{font-size:17px}.room-context h3{font-size:15px}.room-context label{font-size:12px}
.room-context input,.room-context textarea,.room-context select{font-size:12px;padding:9px;min-width:0}
.room-context button{font-size:12px;padding:7px 12px}.room-context summary{font-size:13px;margin:12px 0;min-height:24px}
.artifact-card,.attachment-card{border-bottom:1px solid var(--line);padding:12px 0;overflow-wrap:anywhere}
.artifact-card:last-child,.attachment-card:last-child{border-bottom:0}
.artifact-card button{background:transparent;color:var(--accent);text-align:left;padding:0;white-space:normal;overflow-wrap:anywhere}
.artifact-card small,.attachment-card small{display:block;margin-top:4px;font-size:11px}
.connect-tip{color:var(--muted);font-size:12px}.connect-tip h3{color:var(--text)}.connect-tip button{width:100%;border:1px solid var(--accent);background:transparent;color:var(--accent)}
#artifact-detail{padding:16px;border:1px solid var(--accent);border-radius:10px;background:var(--panel);margin-bottom:22px;scroll-margin:20px}
#detail-content{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.8 system-ui}
#detail-meta,#detail-version{overflow-wrap:anywhere}#detail-version{font-size:11px}
#close-detail{background:transparent;color:var(--accent);padding:6px 0}
.search-disclosure>summary{font-weight:650;color:var(--text)}.search-controls{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:stretch}.search-controls input{min-width:0}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}button:disabled{cursor:default;opacity:.45}#older-messages{background:transparent;color:var(--accent);font-size:12px;padding:7px}[hidden]{display:none!important}
@media(min-width:1550px){.chat-workspace{grid-template-columns:260px minmax(0,1fr) 340px}.room-heading,#chat-stream{padding-left:40px;padding-right:40px}}
@media(max-width:1100px){.chat-workspace{grid-template-columns:205px minmax(0,1fr) 250px}.room-nav,.room-context{padding:20px 14px}.chat-top{padding:12px 17px}.room-heading{padding:20px}.composer{padding:12px 16px}.chat-top nav a{padding:5px 7px}}
@media(max-width:900px){.chat-app{height:auto;min-height:100dvh}.chat-workspace{grid-template-columns:minmax(0,1fr)}.chat-top{flex-wrap:wrap;padding:14px 16px;gap:10px}.chat-top nav{gap:3px 8px}.chat-top nav a{padding:5px 0}.chat-top>div{gap:16px}.chat-title{font-size:12px}.room-nav{border-right:0;border-bottom:1px solid var(--line);padding:18px}.room-nav h1{font-size:18px}.room-filters{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}.room-filters label{margin-top:8px}.room-nav>.room-note{display:none}#room-list{display:flex;overflow-x:auto;gap:8px;padding-bottom:4px}.room-choice{flex:0 0 210px;margin-top:0}.room-choice small{margin-top:3px}#create-room{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;border:0;padding:0;margin-top:14px}#create-room label{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}#create-room button{width:auto;margin:0}.room-main{height:85dvh;min-height:660px}.room-context{border-left:0;border-top:1px solid var(--line);padding:24px 18px}.room-heading{padding:18px}.room-heading h2{font-size:20px}.sync-bar,#chat-stream{padding-left:18px;padding-right:18px}.chat-event{padding:13px}.room-heading .eyebrow{font-size:10px}.chat-event time{margin-left:0;flex-basis:100%}.context-section{padding-bottom:20px;margin-bottom:20px}}
@media(max-width:374px){.chat-top .brand{font-size:19px}.chat-top>div{gap:12px}.room-heading{gap:8px}.room-heading h2{font-size:18px}.composer-tools>div{flex-basis:100%}.composer-tools button{width:100%}.sync-bar{font-size:10px}}
'''

CHAT_JS = r'''
(() => {
  'use strict';
  const $ = id => document.getElementById(id), cfg = $('room-config');
  const state = {project:$('chat-project').value, room:null, cursor:0, rooms:new Map(), events:new Map(), artifacts:new Map(), latestArtifacts:[], artifactsMore:false, artifactsLoaded:false, delivery:null, files:new Map(), generation:0, stopped:false, busy:false, pendingFiles:[], reply:null, drafts:new Map(), nextRooms:null, lastList:0, olderFloor:0, olderRange:null, loadingOlder:false, pendingWrites:new Map()};
  const kindNames = {document:uiText('ui_39932f24fe11'),plan:uiText('ui_6f949ac3522d'),summary:uiText('ui_21c04b2eeeb4'),task_proposal:uiText('ui_33170e67f6ba'),handoff_proposal:uiText('ui_37f02eade9df')};
  function node(tag, text, cls) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; }
  function fail(error) { $('chat-error').textContent=error.message||String(error); $('chat-error').hidden=false; }
  function clearError() { $('chat-error').hidden=true; }
  let setupScope='';
  function controls() { const scope=JSON.stringify([state.project,state.room&&state.room.session_id]); if(scope!==setupScope){setupScope=scope;$('auto-instructions').hidden=true;$('auto-instructions').value='';$('auto-setup-status').textContent='';} $('pause-delivery').disabled=!state.delivery||state.busy||state.stopped; $('copy-invite').disabled=!state.room||state.stopped; $('copy-auto-setup').disabled=!state.room||state.stopped||cfg.dataset.role==='read_only'; $('auto-worker-link').href='/ui/mcp?project='+encodeURIComponent(state.project); $('sync-now').disabled=!state.room||state.stopped; const write=!!state.room&&!state.stopped&&state.room.status==='open'&&cfg.dataset.role!=='read_only'; $('send-message').disabled=!write||state.busy; $('message-body').disabled=!write||state.busy; for(const input of $('artifact-form').querySelectorAll('input,textarea,select,button'))input.disabled=!write||state.busy; $('message-file').disabled=!write||state.busy; $('artifact-editor').hidden=!write; $('create-room').hidden=cfg.dataset.role!=='admin'; $('archive-room').hidden=!state.room||cfg.dataset.role!=='admin'; $('archive-room').textContent=state.room&&state.room.status==='archived'?uiText('ui_d82e4e5145df'):uiText('ui_d594d0ff9a4b'); $('chat-project').disabled=state.busy; $('room-status').disabled=state.busy; $('archive-room').disabled=state.busy||state.stopped; for(const b of $('room-list').querySelectorAll('button'))b.disabled=state.busy; for(const b of $('create-room').querySelectorAll('button'))b.disabled=state.busy||state.stopped; }
  async function request(path, options) {
    const r=await fetch(path,{credentials:'same-origin',cache:'no-store',...options});
    let data; try { data=await r.json(); } catch { throw new Error(uiText('ui_a4694e3787df')); }
    if(r.status===401) {state.stopped=true;$('sync-status').textContent=uiText('ui_afdf85f8476e');controls();throw new Error(uiText('ui_e4723c61253c'));}
    if(!r.ok){if(r.status===403&&data.error==='csrf'){saveDraft();const error=new Error(uiText('ui_bacf10000001'));error.code='csrf';throw error;}throw new Error(data.message||data.error||uiText('ui_bd88f7ea6aa5'));} return data;
  }
  function data(op, fields={}) { return request('/ui/chat/data?'+new URLSearchParams({op,project:state.project,...fields})); }
  async function write(action, args) {
    if(state.stopped)throw new Error(uiText('ui_48dfe30a58eb'));
    const payloadKey=JSON.stringify([action,args]);
    if(action==='post_session_message')for(const [key] of state.pendingWrites){const [oldAction,oldArgs]=JSON.parse(key);if(oldAction===action&&oldArgs.project_id===args.project_id&&oldArgs.session_id===args.session_id&&oldArgs.body===args.body&&key!==payloadKey)throw new Error(uiText('ui_bacf10000004'));}
    if(!state.pendingWrites.has(payloadKey))state.pendingWrites.set(payloadKey,crypto.randomUUID());
    const idempotency_key=state.pendingWrites.get(payloadKey);
    saveDraft();
    const nonce=await data('nonce',{action,project:args.project_id,session:args.session_id||''});
    let answer;try{answer=await request('/ui/chat/action',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':cfg.dataset.csrf},body:JSON.stringify({action,arguments:{...args,idempotency_key},nonce:nonce.nonce})});}catch(error){if(error.code==='csrf'){state.pendingWrites.delete(payloadKey);saveDraft();}throw error;}
    state.pendingWrites.delete(payloadKey); return answer;
  }
  function roomFields(){return {project_id:state.project,session_id:state.room.session_id};}
  const lastRoomKey='ys-memory:last-chat:'+cfg.dataset.user;
  function savedRoom(){try{const saved=JSON.parse(localStorage.getItem(lastRoomKey));return saved&&typeof saved.project==='string'&&/^[a-f0-9]{32}$/.test(saved.session)?saved:null;}catch{return null;}}
  function rememberRoom(){try{localStorage.setItem(lastRoomKey,JSON.stringify({project:state.project,session:state.room.session_id}));}catch{/* Disabled browser storage must not prevent chat. */}}
  function forgetRoom(){try{localStorage.removeItem(lastRoomKey);}catch{}}
  const deliveryNames={disconnected:uiText('ui_de0237e92b37'),waiting:uiText('ui_fc8170d79b79'),offline:uiText('ui_458d710c8651'),processing:uiText('ui_c6bfc7ae370d'),failed:uiText('ui_4d95c10d81dd'),budget_exhausted:uiText('ui_5196d864fcd3'),paused:uiText('ui_30d72ffb8690'),disabled:uiText('ui_a8c3698b5b8c'),expired:uiText('ui_a3bb7ab2cefc'),archived:uiText('ui_e6f1be2983ca'),revoked:uiText('ui_f46283d40781')};
  const receiptNames={retry_ready:uiText('ui_642fcc1b1e7f'),leased:uiText('ui_fa2386a4a00e'),dispatched:uiText('ui_558ebda656f2'),tool_read:uiText('ui_7526bccb9e0e'),replied:uiText('ui_c2d242f57244'),no_reply:uiText('ui_c10d00000008'),failed:uiText('ui_4d95c10d81dd'),superseded:uiText('ui_6b865761f9a9')};
  // Hub admission state only: never an accepted notification, a tool read or a reply.
  function queuedReservation(person){const q=person.queued_reservation;return q&&(person.status==='waiting'||person.status==='offline')&&Number.isInteger(q.through_sequence)&&Number.isFinite(q.queued_until)?q:null;}
  let lastDeliveryView='',lastHistory=null,lastDeliveryRoom=null;
  function currentReceiver(person){return ['waiting','offline','processing','failed','paused'].includes(person.status)&&person.enabled!==false&&person.released_at==null&&(!Number.isFinite(person.expires_at)||person.expires_at>Date.now()/1000)&&(person.status==='processing'||!Number.isInteger(person.turns_used)||!Number.isInteger(person.max_turns)||person.turns_used<person.max_turns);}
  function renderDelivery(error=''){
    const button=$('pause-delivery'),panel=$('delivery-participants'),current=state.delivery;
    if(lastDeliveryRoom!==state.room?.session_id){lastHistory=null;lastDeliveryRoom=state.room?.session_id;}
    button.hidden=!state.room||cfg.dataset.role!=='admin';button.disabled=!current||state.busy||state.stopped;button.textContent=current?.control.paused?uiText('ui_815c0f56f85a'):uiText('ui_e7efcf8dd0ba');
    const active=current?.participants.filter(currentReceiver)||[],activeSet=new Set(active);
    const signature=JSON.stringify([state.room?.session_id,current,error,active]);if(signature===lastDeliveryView)return;lastDeliveryView=signature;
    panel.replaceChildren();
    if(!state.room){$('delivery-title').textContent=uiText('ui_7cd33c58c2e3');$('delivery-explanation').textContent=uiText('ui_d21cf4bd524b');return;}
    if(!current){$('delivery-title').textContent=error?uiText('ui_2e75037f1419'):uiText('ui_392eab34af05');$('delivery-explanation').textContent=error||uiText('ui_0831a8f883ea');return;}
    const people=current.participants;
    const inactive=people.filter(person=>!activeSet.has(person));
    $('delivery-title').textContent=(current.control.paused?uiText('ui_6725cf10d281')+' · ':'')+uiText('ui_c10d00000004')+active.length+' · '+uiText('ui_c10d00000005')+active.filter(person=>person.relay_online===true).length;
    $('delivery-explanation').textContent=current.control.paused?uiText('ui_e8665732f856'):uiText('ui_c10d00000007');
    let history=null;if(inactive.length){history=node('details',undefined,'delivery-history');history.open=lastHistory?.open===true;lastHistory=history;history.append(node('summary',uiText('ui_c10d00000006')+inactive.length));}
    for(const person of people){const row=node('div',undefined,'delivery-participant'),queued=queuedReservation(person);row.append(node('strong',person.display_name||person.worker_id),node('small',person.worker_id),node('span',queued&&person.status==='waiting'?uiText('ui_c10d00000001'):deliveryNames[person.status]||uiText('ui_f44ca1217931')));row.append(node('small',person.relay_online?uiText('ui_54e4388750a4'):uiText('ui_5f54815bbdc7')));if(Number.isInteger(person.turns_used)&&Number.isInteger(person.max_turns))row.append(node('small',uiText('ui_996daae10b4d')+person.turns_used+'/'+person.max_turns));if(queued){if(person.status!=='waiting')row.append(node('span',uiText('ui_c10d00000001'),'receipt'));const detail=node('small',uiText('ui_c10d00000002')+new Date(queued.queued_until*1000).toLocaleTimeString(UI_LANGUAGE)+uiText('ui_8d77a3826a46')+queued.through_sequence);detail.title=uiText('ui_c10d00000003');row.append(detail);}const receipt=person.latest_delivery;if(receipt){row.append(node('span',(receiptNames[receipt.status]||uiText('ui_7af3ec8211a9'))+uiText('ui_8d77a3826a46')+receipt.through_sequence,'receipt'));if(receipt.status==='replied'&&receipt.reply_sequence)row.append(node('small',uiText('ui_c075b35fbea4')+receipt.reply_sequence));}else row.append(node('small',uiText('ui_923dad25d70c')));(activeSet.has(person)?panel:history).append(row);}
    if(history)panel.append(history);
    if(current.has_more)panel.append(node('small',uiText('ui_956590f6b35e')));
  }
  async function refreshDelivery(){if(!state.room||state.stopped)return;const gen=state.generation,sid=state.room.session_id;try{const value=await data('delivery',{session:sid});if(gen!==state.generation)return;state.delivery=value;renderDelivery();}catch(error){if(gen!==state.generation)return;state.delivery=null;renderDelivery(error.message||uiText('ui_4b1c87aa735c'));}}
  function linkFile(file){const a=node('a',file.filename);a.href='/ui/chat/file?'+new URLSearchParams({project:state.project,session:state.room.session_id,attachment:file.attachment_id});return a;}
  function setReply(message) {state.reply=message;const p=$('reply-preview');p.replaceChildren();p.hidden=!message;if(message){p.append(node('span',uiText('ui_ee665829e3da')+message.sequence+' · '+message.actor.display_name));const x=node('button',uiText('ui_4bfc8056a1e4'));x.type='button';x.onclick=()=>setReply(null);p.append(x);}}
  function appendEvent(item) {
    const article=node('article',undefined,'chat-event '+(item.actor?.kind||'system')+(item.type==='message'?'':' system-event'));article.dataset.sequence=item.sequence;
    const header=node('header'), actor=item.actor||{kind:'system',display_name:uiText('ui_6df543c4a401')};
    if(actor.kind!=='human')header.append(node('span',actor.kind==='worker'?'AI':uiText('ui_6df543c4a401'),'actor-mark '+actor.kind));
    header.append(node('span',actor.display_name||actor.id,'actor-name'));
    if(actor.kind==='worker'&&actor.display_name!==actor.id)header.append(node('span',actor.id,'actor-id'));
    const when=node('time',new Date(item.created_at*1000).toLocaleString(UI_LANGUAGE));header.append(when);article.append(header);
    if(item.type==='message') {
      if(item.reply_to_message_id){const parent=[...state.events.values()].find(e=>e.message_id===item.reply_to_message_id);article.append(node('div',parent?uiText('ui_ee665829e3da')+parent.sequence+' · '+parent.actor.display_name:uiText('ui_aa2eecfd61cf'),'reply-ref'));}
      article.append(node('div',item.body,'chat-message'));
      if(item.body_truncated)article.append(node('small',uiText('ui_812bd215047c')));
      const reply=node('button',uiText('ui_ee665829e3da')+item.sequence,'reply-button');reply.type='button';reply.onclick=()=>{$('message-body').focus();setReply(item);};article.append(reply);
      for(const f of item.attachments||[]){article.append(linkFile(f));state.files.set(f.attachment_id,f);}
    } else if(item.type==='artifact') {
      const record=item.artifact||item;state.artifacts.set(record.artifact_id,record);
      const button=node('button',(kindNames[record.kind]||uiText('ui_eb15c869d0a8'))+'：'+record.title,'event-label');button.type='button';button.onclick=()=>showArtifact(record.artifact_id).catch(fail);article.append(button);
    } else if(item.type==='attachment') {
      const file=item.attachment||item;state.files.set(file.attachment_id,file);article.append(node('span',uiText('ui_f3444d8bb54a'),'event-label'),linkFile(file));
    } else article.append(node('span',uiText('ui_9217fb441af5'),'event-label'));
    return article;
  }
  function renderEvents(keepPosition=false) {
    const stream=$('chat-stream'), oldHeight=stream.scrollHeight, oldTop=stream.scrollTop, nearEnd=oldHeight-oldTop-stream.clientHeight<100;
    stream.replaceChildren();state.artifacts.clear();state.files.clear();
    for(const item of [...state.events.values()].sort((a,b)=>a.sequence-b.sequence))stream.append(appendEvent(item));
    if(!state.events.size)stream.append(node('div',uiText('ui_d32cfb93695a'),'chat-empty'));
    if(keepPosition)stream.scrollTop=oldTop+(stream.scrollHeight-oldHeight);else if(nearEnd)stream.scrollTop=stream.scrollHeight;else stream.scrollTop=oldTop;
    $('artifact-list').replaceChildren();
    const indexed=new Map(state.latestArtifacts.map(a=>[a.artifact_id,a]));for(const a of state.artifacts.values())indexed.set(a.artifact_id,a);
    for(const artifact of [...indexed.values()].sort((a,b)=>b.sequence-a.sequence).slice(0,10)) {const card=node('div',undefined,'artifact-card'),b=node('button',artifact.title);b.type='button';b.onclick=()=>showArtifact(artifact.artifact_id).catch(fail);card.append(b,node('small',(kindNames[artifact.kind]||artifact.kind)+' · #'+artifact.sequence+uiText('ui_db599ae19e8d')+artifact.covered_through_sequence));if(artifact.created_at)card.append(node('small',new Date(artifact.created_at*1000).toLocaleString(UI_LANGUAGE)+' · '+(artifact.actor?.display_name||'')));$('artifact-list').append(card);}
    if(state.artifactsMore)$('artifact-list').append(node('p',uiText('ui_edf70e18414d'),'room-note'));
    $('attachment-list').replaceChildren();for(const file of state.files.values()){const card=node('div',undefined,'attachment-card');card.append(linkFile(file),node('small',Math.ceil(file.size/1024)+' KiB'));$('attachment-list').append(card);}
    if(!$('artifact-list').childElementCount)$('artifact-list').append(node('p',state.artifactsLoaded?uiText('ui_999caf91d31f'):uiText('ui_8be5ea2870ac'),'room-note'));if(!state.files.size)$('attachment-list').append(node('p',uiText('ui_38ca06647563'),'room-note'));$('older-messages').hidden=state.olderFloor<=0;
  }
  let refreshInFlight=null;
  async function refreshRoom() {
    const gen=state.generation;
    if(refreshInFlight&&refreshInFlight.gen===gen)return refreshInFlight.promise;
    const promise=refreshRoomData();refreshInFlight={gen,promise};
    try{return await promise;}finally{if(refreshInFlight?.promise===promise)refreshInFlight=null;}
  }
  async function refreshRoomData() {
    if(!state.room||state.stopped)return;
    const gen=state.generation,sid=state.room.session_id;
    await refreshDelivery();if(gen!==state.generation||state.stopped)return;
    let pages=0, more, updateArtifacts=!state.artifactsLoaded;
    do {const r=await data('read',{session:sid,after:state.cursor});if(gen!==state.generation)return;
      state.room=r.session;for(const item of r.items){state.events.set(item.sequence,item);if(item.type==='artifact')updateArtifacts=true;}state.cursor=Math.max(state.cursor,r.next_after_sequence);more=r.has_more;
      if(r.items.length)renderEvents();controls();
    } while(more&&++pages<5);
    if(updateArtifacts){const index=await data('artifacts',{session:sid});if(gen!==state.generation)return;state.latestArtifacts=index.items;state.artifactsMore=index.has_more;state.artifactsLoaded=true;renderEvents();}
    $('sync-status').textContent=uiText('ui_79b4ba1048d8')+state.cursor+' · '+new Date().toLocaleTimeString(UI_LANGUAGE)+(more?uiText('ui_c0e14630a2b9'):'');
  }
  function draftKey(){return 'ys-memory:draft:'+JSON.stringify([cfg.dataset.user,state.project,state.room.session_id]);}
  function saveDraft(){if(!state.room)return;const draft={body:$('message-body').value,reply:state.reply,files:[...state.pendingFiles]};state.drafts.set(JSON.stringify([state.project,state.room.session_id]),draft);try{const pending=[...state.pendingWrites].filter(([key])=>{const [action,args]=JSON.parse(key);return action==='post_session_message'&&args.project_id===state.project&&args.session_id===state.room.session_id;});sessionStorage.setItem(draftKey(),JSON.stringify({body:draft.body,reply:draft.reply?{message_id:draft.reply.message_id,sequence:draft.reply.sequence,actor:{display_name:draft.reply.actor.display_name}}:null,hadAttachments:draft.files.length>0,pending}));}catch{/* Storage unavailable must not prevent chat. */}}
  function restoreDraft(){try{const raw=sessionStorage.getItem(draftKey());if(!raw||raw.length>65536)return null;const d=JSON.parse(raw);if(!d||typeof d.body!=='string'||new TextEncoder().encode(d.body).length>8000)return null;const reply=d.reply;if(reply!==null&&(!reply||typeof reply.message_id!=='string'||!Number.isInteger(reply.sequence)||typeof reply.actor?.display_name!=='string'))return null;if(!Array.isArray(d.pending)||d.pending.length>20)return null;for(const pair of d.pending){if(!Array.isArray(pair)||pair.length!==2||typeof pair[0]!=='string'||typeof pair[1]!=='string'||pair[1].length>128)return null;const [action,args]=JSON.parse(pair[0]);if(action!=='post_session_message'||args.project_id!==state.project||args.session_id!==state.room.session_id||typeof args.body!=='string'||!Array.isArray(args.attachment_ids))return null;}for(const pair of d.pending)state.pendingWrites.set(...pair);return {body:d.body,reply,files:[],recovered:true,hadAttachments:d.hadAttachments===true};}catch{return null;}}
  async function selectRoom(room) {
    saveDraft();const gen=++state.generation;state.room=room;state.delivery=null;renderDelivery();updateLocation();$('copy-invite').textContent=uiText('ui_8fbd48234a05');state.cursor=Math.max(0,room.latest_sequence-50);state.olderFloor=state.cursor;state.olderRange=null;state.loadingOlder=false;state.events.clear();state.artifacts.clear();state.latestArtifacts=[];state.artifactsLoaded=false;state.artifactsMore=false;state.files.clear();
    const draft=state.drafts.get(JSON.stringify([state.project,room.session_id]))||restoreDraft()||{body:'',reply:null,files:[]};$('message-body').value=draft.body;state.pendingFiles=draft.files;setReply(draft.reply);fileStatus();
    $('active-room').textContent=room.title;$('chat-stream').replaceChildren(node('div',uiText('ui_15749b2fa8b0'),'chat-empty'));$('artifact-detail').hidden=true;
    renderRoomList();controls();clearError();if(draft.recovered&&(draft.body||draft.reply||draft.hadAttachments))fail(new Error((draft.hadAttachments?uiText('ui_bacf10000003'):uiText('ui_bacf10000002'))));await refreshRoom();if(gen!==state.generation)return;rememberRoom();renderEvents();$('chat-stream').scrollTop=$('chat-stream').scrollHeight;
  }
  function renderRoomList(){const list=$('room-list');list.replaceChildren();for(const room of [...(state.room&&!state.rooms.has(state.room.session_id)?[state.room]:[]),...state.rooms.values()]){const b=node('button',room.title,'room-choice'+(state.room&&room.session_id===state.room.session_id?' selected':''));b.type='button';b.setAttribute('aria-pressed',String(!!state.room&&room.session_id===state.room.session_id));b.append(node('small','#'+room.latest_sequence+' · '+(room.status==='archived'?uiText('ui_1499cf5a6a80'):uiText('ui_e7e5869de581'))));b.disabled=state.busy;b.onclick=()=>{if(!state.busy)selectRoom(room).catch(fail);};list.append(b);}if(!state.rooms.size&&!state.room)list.append(node('p',uiText('ui_8cba477b06d1'),'room-note'));}
  async function loadRooms(more=false){const gen=state.generation,fields={status:$('room-status').value};if(more&&state.nextRooms)fields.after_id=state.nextRooms;const r=await data('list',fields);if(gen!==state.generation)return;if(!more)state.rooms.clear();for(const room of r.items)state.rooms.set(room.session_id,room);state.nextRooms=r.next_after_id;$('more-rooms').hidden=!r.has_more;renderRoomList();state.lastList=Date.now();}
  async function resetRooms(){saveDraft();state.generation++;state.project=$('chat-project').value;state.room=null;state.delivery=null;renderDelivery();state.rooms.clear();state.nextRooms=null;renderRoomList();$('more-rooms').hidden=true;updateLocation();state.events.clear();state.cursor=0;$('active-room').textContent=uiText('ui_67babec0d58d');$('chat-stream').replaceChildren(emptyState());$('sync-status').textContent=uiText('ui_38bb242511a3');$('artifact-list').replaceChildren();$('attachment-list').replaceChildren();$('artifact-detail').hidden=true;$('search-results').replaceChildren();$('more-search').hidden=true;$('message-body').value='';setReply(null);state.pendingFiles=[];fileStatus();controls();await loadRooms();}
  function emptyState(){const box=node('div',undefined,'chat-empty');box.append(node('strong',uiText('ui_b625ad120af4')),node('p',uiText('ui_46e32ddd1d72')));return box;}
  function updateProjectLinks(){for(const [id,path,view] of [['project-home-link','/ui',''],['project-tasks-link','/ui','tasks'],['project-memory-link','/ui','memory'],['project-mcp-link','/ui','connections'],['project-settings-link','/ui/account/password',''],['task-link','/ui','tasks']]){const a=$(id),q=new URLSearchParams({project:state.project});if(view)q.set('view',view);if(a)a.href=path+'?'+q;}}
  function updateLocation(){updateProjectLinks();const q=new URLSearchParams({project:state.project});if(state.room)q.set('session',state.room.session_id);history.replaceState(null,'','/ui/chat?'+q);}
  function focusDetail(){const panel=$('artifact-detail');panel.focus({preventScroll:true});panel.scrollIntoView({block:'nearest'});}
  let detail=null,detailRequest=0;
  async function showArtifact(id,more=false){const ticket=++detailRequest;const gen=state.generation;if(!more){detail=null;$('more-artifact').hidden=true;}const r=await data('artifact',{session:state.room.session_id,artifact:id,offset:more&&detail?detail.next_offset:0});if(gen!==state.generation||ticket!==detailRequest)return;detail=r;$('artifact-detail').hidden=false;$('detail-title').textContent=r.title;$('detail-meta').textContent=(kindNames[r.kind]||r.kind)+uiText('ui_db599ae19e8d')+r.covered_through_sequence;$('detail-version').textContent='SHA-256 '+r.sha256;$('version-info').hidden=false;$('detail-content').textContent=(more?$('detail-content').textContent:'')+r.content;$('more-artifact').hidden=!r.has_more;if(!more)focusDetail();}
  $('close-detail').onclick=()=>{++detailRequest;detail=null;$('more-artifact').hidden=true;$('artifact-detail').hidden=true;$('chat-stream').focus({preventScroll:true});$('chat-stream').scrollIntoView({block:'nearest'});};
  $('more-artifact').onclick=()=>detail&&showArtifact(detail.artifact_id,true).catch(fail);
  $('chat-project').onchange=()=>resetRooms().catch(fail);$('room-status').onchange=()=>resetRooms().catch(fail);$('more-rooms').onclick=()=>loadRooms(true).catch(fail);
  $('sync-now').onclick=()=>refreshRoom().catch(fail);
  $('pause-delivery').onclick=async()=>{if(state.busy||state.stopped||!state.room||!state.delivery||cfg.dataset.role!=='admin')return;const gen=state.generation,args={...roomFields(),paused:!state.delivery.control.paused,expected_version:state.delivery.control.version};state.busy=true;controls();renderDelivery();try{clearError();await write('set_session_delivery_paused',args);}catch(error){if(gen===state.generation)fail(error);}finally{state.busy=false;controls();if(gen===state.generation)await refreshRoom().catch(fail);}};
  let composing=false;
  $('message-body').addEventListener('input',saveDraft);
  if(typeof globalThis.addEventListener==='function')globalThis.addEventListener('pagehide',saveDraft);
  $('message-body').addEventListener('compositionstart',()=>{composing=true;});
  $('message-body').addEventListener('compositionend',()=>{composing=false;});
  $('message-body').addEventListener('keydown',event=>{if(event.key!=='Enter'||event.shiftKey||event.ctrlKey||event.altKey||event.metaKey||event.isComposing||composing||event.keyCode===229)return;event.preventDefault();if(!event.repeat&&!$('send-message').disabled&&$('message-body').value.trim())$('message-form').requestSubmit();});
  $('create-room').onsubmit=async event=>{event.preventDefault();if(state.busy)return;state.busy=true;controls();try{clearError();const r=await write('create_session',{project_id:state.project,title:$('room-title').value});$('room-title').value='';await loadRooms();await selectRoom(r);}catch(e){fail(e);}finally{state.busy=false;controls();}};
  $('message-form').onsubmit=async event=>{event.preventDefault();if(state.busy||!state.room)return;const body=$('message-body').value;if(new TextEncoder().encode(body).length>8000){fail(new Error(uiText('ui_57b2715ef10b')));return;}state.busy=true;controls();const gen=state.generation;try{clearError();const args={...roomFields(),body,attachment_ids:state.pendingFiles.map(x=>x.attachment_id)};if(state.reply)args.reply_to_message_id=state.reply.message_id;await write('post_session_message',args);if(gen!==state.generation)return;$('message-body').value='';state.pendingFiles=[];setReply(null);fileStatus();saveDraft();await refreshRoom();$('chat-stream').scrollTop=$('chat-stream').scrollHeight;}catch(e){fail(e);}finally{state.busy=false;controls();}};
  function fileStatus(){$('file-status').textContent=state.pendingFiles.map(x=>x.filename).join('、');}
  $('message-file').onchange=async()=>{const file=$('message-file').files[0];if(!file||!state.room)return;if(state.pendingFiles.length>=10){fail(new Error(uiText('ui_6ec1c2342de6')));return;}if(file.size>524288){fail(new Error(uiText('ui_e51a116c5fff')));return;}state.busy=true;controls();const target=roomFields(),gen=state.generation;try{const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));const r=await write('upload_session_attachment',{...target,filename:file.name,content_base64:btoa(binary)});if(gen!==state.generation)return;state.pendingFiles.push(r);fileStatus();$('message-file').value='';await refreshRoom();}catch(e){fail(e);}finally{state.busy=false;controls();}};
  $('artifact-form').onsubmit=async event=>{event.preventDefault();if(state.busy||!state.room)return;state.busy=true;controls();const gen=state.generation;try{clearError();await write('create_session_artifact',{...roomFields(),kind:$('artifact-kind').value,title:$('artifact-title').value,content:$('artifact-content').value,covered_through_sequence:state.cursor,reference_message_ids:state.reply?[state.reply.message_id]:[],attachment_ids:state.pendingFiles.map(f=>f.attachment_id)});if(gen!==state.generation)return;$('artifact-title').value='';$('artifact-content').value='';state.pendingFiles=[];fileStatus();await refreshRoom();}catch(e){fail(e);}finally{state.busy=false;controls();}};
  $('archive-room').onclick=async()=>{if(!state.room||state.busy)return;state.busy=true;controls();try{await write('archive_session',{...roomFields(),archived:state.room.status!=='archived',expected_version:state.room.version});await refreshRoom();await loadRooms();}catch(e){fail(e);}finally{state.busy=false;controls();}};
  $('older-messages').onclick=async()=>{
    if(!state.room||state.loadingOlder)return;const gen=state.generation;state.loadingOlder=true;$('older-messages').disabled=true;
    if(!state.olderRange){const before=state.olderFloor+1,start=Math.max(0,before-201);state.olderRange={before,start,after:start};}
    const range=state.olderRange;
    try{let pages=0;while(pages++<12){const r=await data('read',{session:state.room.session_id,after:range.after});if(gen!==state.generation)return;
      for(const item of r.items)if(item.sequence<range.before)state.events.set(item.sequence,item);
      const previous=range.after;range.after=r.next_after_sequence;
      if(!r.has_more||range.after>=range.before-1){state.olderFloor=range.start;state.olderRange=null;break;}
      if(range.after<=previous)throw new Error(uiText('ui_19f2243514d1'));
    }renderEvents(true);}catch(e){if(gen===state.generation){renderEvents(true);fail(e);}}
    finally{if(gen===state.generation){state.loadingOlder=false;$('older-messages').disabled=false;$('older-messages').textContent=state.olderRange?uiText('ui_3bc770005441'):uiText('ui_8c685baf48dd');}}
  };
  let search={query:'',after:0},searchRequest=0;
  async function searchRecords(more=false){const gen=state.generation,ticket=++searchRequest;if(!more){search={query:$('search-query').value,after:0};$('search-results').replaceChildren();}const query=search.query,after=search.after;const r=await data('search',{query,after});if(gen!==state.generation||ticket!==searchRequest)return;search.after=r.next_after_sequence;$('more-search').hidden=!r.has_more;for(const hit of r.items){const card=node('div',undefined,'artifact-card'),b=node('button','#'+hit.sequence+' · '+hit.snippet);b.type='button';b.onclick=async()=>{if(state.busy)return;const selectedGen=state.generation,selectedProject=state.project;try{const selected=await data('read',{session:hit.session_id,after:Math.max(0,hit.sequence-2)});if(selectedGen!==state.generation||selectedProject!==state.project||state.busy)return;await selectRoom(selected.session);if(state.project!==selectedProject||!state.room||state.room.session_id!==hit.session_id)return;for(const event of selected.items)state.events.set(event.sequence,event);renderEvents();const el=$('chat-stream').querySelector('[data-sequence="'+hit.sequence+'"]');if(el)el.scrollIntoView({block:'center'});if(hit.artifact_id)await showArtifact(hit.artifact_id);}catch(e){fail(e);}};card.append(b);$('search-results').append(card);}if(!more&&!r.items.length)$('search-results').append(node('p',uiText('ui_6d046453ad62'),'room-note'));}
  $('search-form').onsubmit=e=>{e.preventDefault();searchRecords().catch(fail);};$('more-search').onclick=()=>searchRecords(true).catch(fail);
  $('auto-client').onchange=()=>{ $('auto-project-hint').hidden=$('auto-client').value!=='claude'; $('auto-instructions').hidden=true; $('auto-instructions').value=''; $('auto-setup-status').textContent=''; };
  const psComment=value=>String(value).split(/\r?\n/).map(line=>'# '+line).join('\n');
  const psQuote=value=>"'"+String(value).replace(/'/g,"''")+"'";
  $('copy-auto-setup').onclick=async()=>{
    const worker=$('auto-worker').value.trim(), hours=Number($('auto-hours').value), turns=Number($('auto-turns').value);
    if(!state.room||!cfg.dataset.setupBase||!cfg.dataset.setupCa||!worker||worker.length>128||/[\x00-\x1f\x7f]/.test(worker)||!Number.isInteger(hours)||hours<1||hours>8||!Number.isInteger(turns)||turns<1||turns>100){$('auto-setup-status').textContent=uiText('ui_aa001009');return;}
    const claude=$('auto-client').value==='claude';
    const url=claude?'https://raw.githubusercontent.com/Ya19880104/ys-aimemory/07d575a3bce654bf572b430609a467d1879c6fc9/scripts/connect-chat.ps1':'https://raw.githubusercontent.com/Ya19880104/ys-aimemory/a9d7f87d452336b890071e0332a4dd8077bfc58b/scripts/connect-codex-chat.ps1';
    const hash=claude?'B0CCE4E737381DB1594531F721F6E6334C4E0CD57D970F79C419BD94A42C5FB2':'D842FFD109B601B3626A5C97034F0F3B3473E5F07128AD31891914C4F218EAF3';
    const command='powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Installer -Url '+psQuote(cfg.dataset.setupBase)+' -ExpectedCa '+psQuote(cfg.dataset.setupCa)+' -ProjectId '+psQuote(state.project)+' -SessionId '+psQuote(state.room.session_id)+(claude?" -Project 'REPLACE_WITH_EXACT_LOCAL_PROJECT'":' -WorkerId '+psQuote(worker))+' -Language '+psQuote(UI_LANGUAGE)+' -Hours '+hours+' -MaxTurns '+turns;
    const text=psComment(uiText('ui_aa001010'))+'\n'+psComment('Worker ID: '+worker)+'\n\n'+psComment(uiText('ui_aa001015'))+'\n'+"$Installer = Join-Path $env:TEMP ('ys-memory-chat-' + [Guid]::NewGuid().ToString('N') + '.ps1')\nInvoke-WebRequest -Uri "+psQuote(url)+" -OutFile $Installer\nif ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash -ne "+psQuote(hash)+") { throw 'Installer hash mismatch' }\nnotepad $Installer\n\n"+psComment(uiText('ui_aa001016'))+'\n'+psComment(command)+'\n\n'+psComment((claude?uiText('ui_aa001011'):uiText('ui_aa001012')))+'\n'+psComment(new URL(claude?cfg.dataset.claudeGuide:cfg.dataset.codexGuide,location.href).href)+'\n\n'+psComment(uiText('ui_aa001002'));
    $('auto-instructions').value=text;$('auto-instructions').hidden=false;
    try{await navigator.clipboard.writeText(text);$('auto-setup-status').textContent=uiText('ui_872bc28ee946');}catch{$('auto-instructions').focus();$('auto-instructions').select();$('auto-setup-status').textContent=uiText('ui_ce0fe4db3088');}
  };
  $('copy-invite').onclick=async()=>{if(!state.room){fail(new Error(uiText('ui_5008c89712c5')));return;}const text=uiText('ui_17c72f8483e5')+state.project+'，session_id='+state.room.session_id+uiText('ui_0540860e598a');try{await navigator.clipboard.writeText(text);$('copy-invite').textContent=uiText('ui_872bc28ee946');}catch{$('detail-title').textContent=uiText('ui_a009ff4e10f9');$('detail-content').textContent=text;$('detail-meta').textContent=uiText('ui_ce0fe4db3088');$('artifact-detail').hidden=false;$('more-artifact').hidden=true;$('version-info').hidden=true;focusDetail();}};
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!state.stopped)refreshRoom().catch(fail);});
  async function tick(){if(state.stopped)return;try{if(!document.hidden){await refreshRoom();if(Date.now()-state.lastList>15000)await loadRooms();}}catch(e){fail(e);$('sync-status').textContent=uiText('ui_24cfc69d094c');}finally{if(!state.stopped)setTimeout(tick,document.hidden?10000:1000);}}
  async function start(){const query=new URLSearchParams(location.search),saved=savedRoom();let target=query.get('session'),restore=false;
    if(!target&&saved&&(!query.has('project')||query.get('project')===saved.project)&&[...$('chat-project').querySelectorAll('option')].some(o=>o.value===saved.project)){state.project=saved.project;$('chat-project').value=saved.project;updateProjectLinks();target=saved.session;restore=true;}
    const gen=state.generation;await loadRooms();if(!target||gen!==state.generation)return;if(!/^[a-f0-9]{32}$/.test(target))throw new Error(uiText('ui_202d8880f776'));let r;try{r=await data('read',{session:target});}catch(error){if(restore)forgetRoom();throw error;}if(gen!==state.generation)return;if(r.session.status!==$('room-status').value){$('room-status').value=r.session.status;await loadRooms();if(gen!==state.generation)return;}await selectRoom(r.session);}
  updateProjectLinks();controls();start().catch(fail).finally(()=>setTimeout(tick,1000));
})();
'''


def chat_script():
    from .i18n import script_catalog
    return script_catalog(CHAT_JS) + CHAT_JS
