'use strict';
// Run the unmodified production script. This deliberately models only DOM
// operations used by chat navigation; layout remains a browser acceptance test.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));

function documentFrom(html) {
  const ids = new Map();
  const document = {hidden: false, activeElement: null, addEventListener() {}};
  class Element {
    constructor(tag) {
      this.tagName = tag.toLowerCase(); this.children = []; this.dataset = {};
      this.attributes = {}; this.value = ''; this.hidden = false; this.disabled = false;
      this._text = ''; this.scrollTop = 0; this.scrollHeight = 300; this.clientHeight = 300;
      this.scrollCalls = 0;
      this.listeners = {}; this.submitCalls = 0;
    }
    set textContent(value) { this._text = String(value); this.children = []; }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
    get childElementCount() { return this.children.length; }
    append(...children) { this.children.push(...children); }
    prepend(...children) { this.children.unshift(...children); }
    replaceChildren(...children) { this._text = ''; this.children = children; }
    setAttribute(name, value) {
      value = String(value); this.attributes[name] = value;
      if (name === 'id') ids.set(value, this);
      if (name === 'value') this.value = value;
      if (name === 'hidden') this.hidden = true;
      if (name === 'disabled') this.disabled = true;
      if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = value;
    }
    querySelectorAll(selector) {
      const tags = selector.split(',');
      return this.children.flatMap(child => [ ...(tags.includes(child.tagName) ? [child] : []), ...child.querySelectorAll(selector)]);
    }
    focus() {
      if (!this.disabled && (['button', 'input', 'textarea', 'select', 'a'].includes(this.tagName)
          || Object.hasOwn(this.attributes, 'tabindex'))) document.activeElement = this;
    }
    scrollIntoView() { this.scrollCalls++; }
    addEventListener(name, listener) { this.listeners[name] = listener; }
    requestSubmit() { this.submitCalls++; }
  }
  const root = new Element('root'), stack = [root];
  // Skip executable/style text; build the hierarchy from the real response.
  html = html.replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi, '');
  const voidTags = new Set(['input', 'meta', 'link', 'br', 'hr', 'img']);
  for (const match of html.matchAll(/<(\/?)([a-z][\w:-]*)([^>]*)>/gi)) {
    const [, closing, rawTag, attributes] = match, tag = rawTag.toLowerCase();
    if (closing) { if (stack.at(-1).tagName === tag) stack.pop(); continue; }
    const element = new Element(tag);
    for (const attribute of attributes.matchAll(/([\w-]+)(?:="([^"]*)")?/g)) element.setAttribute(attribute[1], attribute[2] ?? '');
    stack.at(-1).append(element);
    if (!voidTags.has(tag)) stack.push(element);
  }
  for (const select of root.querySelectorAll('select')) {
    const options = select.querySelectorAll('option');
    select.value = (options.find(option => Object.hasOwn(option.attributes, 'selected')) || options[0])?.value || '';
  }
  document.getElementById = id => ids.get(id) || null;
  document.createElement = tag => new Element(tag);
  return document;
}

const roomA = {session_id: 'a'.repeat(32), title: 'First page room', status: 'open', latest_sequence: 0};
const roomB = {session_id: 'b'.repeat(32), title: 'Linked room beyond page one', status: 'open', latest_sequence: 0};
const roomC = {session_id: 'c'.repeat(32), title: 'Beta room', status: 'open', latest_sequence: 0};
const listing = items => ({items, has_more: false, next_after_id: null});
const reading = (room, items = []) => ({session: room, items, next_after_sequence: room.latest_sequence, has_more: false});
function deferred() { let resolve; const promise = new Promise(done => { resolve = done; }); return {promise, resolve}; }
async function settle() { for (let i = 0; i < 6; i++) await new Promise(setImmediate); }

function boot(handler, session = roomB.session_id, options = {}) {
  const document = documentFrom(input.html), requests = [], navigation = [];
  const location = {search: options.search ?? ('?project=alpha&session=' + session)};
  const storage = new Map(Object.entries(options.storage || {}));
  const userKey = 'ys-memory:last-chat:' + document.getElementById('room-config').dataset.user;
  if(options.saved)storage.set(userKey,JSON.stringify(options.saved));
  const context = {
    document, location, URLSearchParams, TextEncoder,
    localStorage: {getItem: key=>storage.get(key)||null, setItem: (key,value)=>storage.set(key,value), removeItem:key=>storage.delete(key)},
    history: {replaceState(_state, _title, url) { navigation.push(url); location.search = new URL(url, 'http://example.test').search; }},
    setTimeout() { /* Polling is not part of these deterministic interactions. */ },
    fetch: async (path, fetchOptions) => {
      assert.equal(fetchOptions.credentials, 'same-origin');
      assert.equal(fetchOptions.cache, 'no-store');
      assert.ok(!fetchOptions.method || fetchOptions.method === 'GET', 'Navigation must not write');
      const q = Object.fromEntries(new URL(path, 'http://example.test').searchParams);
      requests.push(q);
      if(q.op==='artifacts'&&!options.artifactsHandler)return {ok:true,status:200,json:async()=>listing([])};
      const data = await handler(q);
      return {ok: true, status: 200, json: async () => data};
    },
  };
  vm.runInNewContext(input.script, context, {filename: 'CHAT_JS', timeout: 1000});
  return {document, requests, navigation, location, storage, userKey, get: id => document.getElementById(id)};
}

async function deepLinkOutsideFirstPage() {
  const ui = boot(q => {
    assert.equal(q.project, 'alpha');
    if (q.op === 'list') return listing([roomA]);
    assert.equal(q.op, 'read'); assert.equal(q.session, roomB.session_id);
    return reading(roomB);
  });
  await settle();
  assert.equal(ui.get('active-room').textContent, roomB.title);
  assert.equal(new URLSearchParams(ui.location.search).get('session'), roomB.session_id);
  const selected = ui.get('room-list').querySelectorAll('button').filter(button => button.attributes['aria-pressed'] === 'true');
  assert.equal(selected.length, 1);
  assert.ok(selected[0].textContent.includes(roomB.title), 'Linked room must remain selectable outside the first list page');
  assert.ok(ui.requests.some(q => q.op === 'read' && q.session === roomB.session_id));
  assert.equal(ui.get('chat-error').hidden, true);
}

async function projectChangeDuringDeepLink() {
  const pending = deferred();
  const ui = boot(q => {
    if (q.op === 'list') return listing(q.project === 'alpha' ? [roomA] : [roomC]);
    assert.equal(q.op, 'read'); assert.equal(q.project, 'alpha'); assert.equal(q.session, roomB.session_id);
    return pending.promise;
  });
  await settle();
  assert.ok(ui.requests.some(q => q.op === 'read'), 'Initial read must be pending before changing project');
  ui.get('chat-project').value = 'beta';
  await ui.get('chat-project').onchange();
  pending.resolve(reading(roomB));
  await settle();
  const query = new URLSearchParams(ui.location.search);
  assert.equal(query.get('project'), 'beta'); assert.equal(query.has('session'), false);
  for (const [id, path, view] of [['project-home-link', '/ui', null], ['project-tasks-link', '/ui', 'tasks'],
    ['project-memory-link', '/ui', 'memory'], ['project-mcp-link', '/ui', 'connections'],
    ['project-settings-link','/ui/account/password',null], ['task-link', '/ui', 'tasks']]) {
    const target = new URL(ui.get(id).href, 'http://example.test');
    assert.equal(target.pathname, path); assert.equal(target.searchParams.get('project'), 'beta');
    assert.equal(target.searchParams.get('view'), view);
  }
  assert.equal(ui.get('active-room').textContent, '選擇一個對話');
  assert.ok(ui.get('room-list').textContent.includes(roomC.title));
  assert.ok(!ui.get('room-list').textContent.includes(roomB.title), 'Late response must not select the old project room');
  assert.equal(ui.get('send-message').disabled, true);
  assert.equal(ui.get('chat-error').hidden, true);
}

async function closePendingArtifact() {
  const pending = deferred(), room = {...roomB, latest_sequence: 2};
  const artifacts = ['First document', 'Pending document'].map((title, index) => ({
    type: 'artifact', sequence: index + 1, created_at: 1,
    actor: {kind: 'worker', id: 'demo', display_name: 'Demo worker'},
    artifact: {artifact_id: String(index + 1).repeat(32), kind: 'document', title, covered_through_sequence: 0},
  }));
  const content = index => ({...artifacts[index].artifact, content: 'Document text', sha256: 'f'.repeat(64), has_more: false, next_offset: 13});
  const ui = boot(q => {
    if (q.op === 'list') return listing([room]);
    if (q.op === 'read') return reading(room, artifacts);
    assert.equal(q.op, 'artifact');
    return q.artifact === artifacts[0].artifact.artifact_id ? content(0) : pending.promise;
  });
  await settle();
  assert.equal(ui.get('message-body').disabled, true, 'This scenario uses a real read-only rendered page');
  const buttons = ui.get('chat-stream').querySelectorAll('button');
  await buttons.find(button => button.textContent.includes('First document')).onclick();
  assert.equal(ui.get('artifact-detail').hidden, false);
  assert.equal(ui.document.activeElement, ui.get('artifact-detail'));
  const opening = buttons.find(button => button.textContent.includes('Pending document')).onclick();
  await settle();
  assert.ok(ui.requests.some(q => q.artifact === artifacts[1].artifact.artifact_id));
  ui.get('close-detail').onclick();
  assert.equal(ui.document.activeElement, ui.get('chat-stream'), 'Return must focus a visible, enabled element');
  pending.resolve(content(1));
  await opening;
  await settle();
  assert.equal(ui.get('artifact-detail').hidden, true, 'Late document response must not reopen the closed panel');
  assert.equal(ui.document.activeElement, ui.get('chat-stream'), 'Late response must not steal focus');
  assert.equal(ui.get('more-artifact').hidden, true);
  assert.equal(ui.get('chat-error').hidden, true);
}

async function projectChangeClearsOldRooms() {
  const pending = deferred();
  const ui = boot(q => {
    if (q.op === 'list') return q.project === 'alpha' ? listing([roomA]) : pending.promise;
    assert.fail('Changing project without choosing a room must not read messages');
  }, '');
  await settle();
  assert.equal(ui.get('room-list').querySelectorAll('button').length, 1);
  ui.get('chat-project').value = 'beta';
  const changing = ui.get('chat-project').onchange();
  await settle();
  assert.equal(ui.get('room-list').querySelectorAll('button').length, 0, 'Old project rooms must disappear before the new list arrives');
  assert.equal(ui.get('more-rooms').hidden, true);
  assert.equal(ui.get('task-link').href, '/ui?project=beta&view=tasks');
  pending.resolve(listing([roomC]));
  await changing;
  assert.ok(ui.get('room-list').textContent.includes(roomC.title));
  assert.ok(!ui.get('room-list').textContent.includes(roomA.title));
}

async function composerEnterAndIme() {
  const ui=boot(q=>q.op==='list'?listing([roomB]):reading(roomB));
  await settle();
  const body=ui.get('message-body'),form=ui.get('message-form');body.value='一則訊息';
  const key=extras=>{let prevented=false;body.listeners.keydown({key:'Enter',preventDefault(){prevented=true;},...extras});return prevented;};
  assert.equal(key({shiftKey:true}),false);assert.equal(form.submitCalls,0);
  assert.equal(key({isComposing:true}),false);assert.equal(key({keyCode:229}),false);
  body.listeners.compositionstart();assert.equal(key({}),false);body.listeners.compositionend();
  assert.equal(form.submitCalls,0,'IME confirmation must never send');
  assert.equal(key({}),true);assert.equal(form.submitCalls,1);
  key({repeat:true});assert.equal(form.submitCalls,1,'Holding Enter must not duplicate');
  ui.get('send-message').disabled=true;key({});assert.equal(form.submitCalls,1);
  ui.get('send-message').disabled=false;body.value=' \n ';key({});assert.equal(form.submitCalls,1);
}

async function restoreLastRoom() {
  const ui=boot(q=>{assert.equal(q.project,'beta');return q.op==='list'?listing([roomC]):reading(roomC);},'',
    {search:'',saved:{project:'beta',session:roomC.session_id}});
  await settle();assert.equal(ui.get('active-room').textContent,roomC.title);
  assert.equal(ui.get('chat-project').value,'beta');
  assert.deepEqual(JSON.parse(ui.storage.get(ui.userKey)),{project:'beta',session:roomC.session_id});
  assert.equal(ui.get('chat-error').hidden,true);
}

async function restoreAuthorizationAndExplicitUrl() {
  const forbidden=boot(q=>{assert.equal(q.op,'list');assert.equal(q.project,'alpha');return listing([roomA]);},'',
    {search:'',saved:{project:'unauthorized',session:roomC.session_id}});
  await settle();assert.ok(!forbidden.requests.some(q=>q.op==='read'));
  const explicit=boot(q=>{assert.equal(q.project,'alpha');return q.op==='list'?listing([roomA]):reading(roomA);},roomA.session_id,
    {saved:{project:'beta',session:roomC.session_id}});
  await settle();assert.equal(explicit.get('active-room').textContent,roomA.title);
  const otherUser=boot(q=>{assert.equal(q.op,'list');return listing([roomA]);},'',
    {search:'',storage:{'ys-memory:last-chat:another-user':JSON.stringify({project:'alpha',session:roomB.session_id})}});
  await settle();assert.ok(!otherUser.requests.some(q=>q.op==='read'));
}

async function latestArtifactsOutsideMessageWindow() {
  const recent={artifact_id:'1'.repeat(32),kind:'plan',title:'Recent reviewed plan',sequence:75,covered_through_sequence:74,created_at:2,actor:{display_name:'Codex'}};
  const older={...recent,artifact_id:'2'.repeat(32),title:'Previous plan',sequence:12};
  const room={...roomB,latest_sequence:150};
  const ui=boot(q=>{if(q.op==='list')return listing([room]);if(q.op==='artifacts')return {items:[recent,older],has_more:false};assert.equal(q.op,'read');return reading(room);},room.session_id,{artifactsHandler:true});
  await settle();
  assert.equal(ui.get('artifact-list').querySelectorAll('button').length,2);
  assert.ok(ui.get('artifact-list').textContent.includes(recent.title));
  assert.ok(ui.get('artifact-list').textContent.includes(older.title));
  assert.equal(ui.requests.filter(q=>q.op==='artifacts').length,1);
  await ui.get('sync-now').onclick();
  assert.equal(ui.requests.filter(q=>q.op==='artifacts').length,1,'Idle sync must not reload the same index');
  assert.ok(!ui.requests.some(q=>q.op==='artifact'),'Index must not download document bodies');
}

const scenarios = {
  deep_link_outside_first_page: deepLinkOutsideFirstPage,
  project_change_during_deep_link: projectChangeDuringDeepLink,
  project_change_clears_old_rooms: projectChangeClearsOldRooms,
  close_pending_artifact: closePendingArtifact,
  composer_enter_and_ime: composerEnterAndIme,
  restore_last_room: restoreLastRoom,
  restore_authorization_and_explicit_url: restoreAuthorizationAndExplicitUrl,
  latest_artifacts_outside_message_window: latestArtifactsOutsideMessageWindow,
};
(async () => {
  assert.ok(Object.hasOwn(scenarios, input.scenario), 'Unknown test scenario');
  await scenarios[input.scenario]();
  process.stdout.write(JSON.stringify({scenario: input.scenario, status: 'passed'}));
})().catch(error => { console.error(error); process.exitCode = 1; });
