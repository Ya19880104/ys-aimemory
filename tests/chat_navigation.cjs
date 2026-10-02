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

function boot(handler, session = roomB.session_id) {
  const document = documentFrom(input.html), requests = [], navigation = [];
  const location = {search: '?project=alpha&session=' + session};
  const context = {
    document, location, URLSearchParams, TextEncoder,
    history: {replaceState(_state, _title, url) { navigation.push(url); location.search = new URL(url, 'http://example.test').search; }},
    setTimeout() { /* Polling is not part of these deterministic interactions. */ },
    fetch: async (path, options) => {
      assert.equal(options.credentials, 'same-origin');
      assert.equal(options.cache, 'no-store');
      assert.ok(!options.method || options.method === 'GET', 'Navigation must not write');
      const q = Object.fromEntries(new URL(path, 'http://example.test').searchParams);
      requests.push(q);
      const data = await handler(q);
      return {ok: true, status: 200, json: async () => data};
    },
  };
  vm.runInNewContext(input.script, context, {filename: 'CHAT_JS', timeout: 1000});
  return {document, requests, navigation, location, get: id => document.getElementById(id)};
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
  for (const [id, path, hash] of [['project-home-link', '/ui', ''], ['project-tasks-link', '/ui/manage', ''],
    ['project-memory-link', '/ui', '#memory'], ['task-link', '/ui/manage', '']]) {
    const target = new URL(ui.get(id).href, 'http://example.test');
    assert.equal(target.pathname, path); assert.equal(target.searchParams.get('project'), 'beta');
    assert.equal(target.hash, hash);
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
  assert.equal(ui.get('task-link').href, '/ui/manage?project=beta');
  pending.resolve(listing([roomC]));
  await changing;
  assert.ok(ui.get('room-list').textContent.includes(roomC.title));
  assert.ok(!ui.get('room-list').textContent.includes(roomA.title));
}

const scenarios = {
  deep_link_outside_first_page: deepLinkOutsideFirstPage,
  project_change_during_deep_link: projectChangeDuringDeepLink,
  project_change_clears_old_rooms: projectChangeClearsOldRooms,
  close_pending_artifact: closePendingArtifact,
};
(async () => {
  assert.ok(Object.hasOwn(scenarios, input.scenario), 'Unknown test scenario');
  await scenarios[input.scenario]();
  process.stdout.write(JSON.stringify({scenario: input.scenario, status: 'passed'}));
})().catch(error => { console.error(error); process.exitCode = 1; });
