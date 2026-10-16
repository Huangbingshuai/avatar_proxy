import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import { createHash } from 'node:crypto';
import { JSDOM, VirtualConsole } from 'jsdom';
import { build, pages, root, escapeHtml, modelCatalog, assetOperations } from './build.mjs';

const html = await build();
function reader(t, options = {}) {
  const errors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', error => errors.push(error.message));
  const dom = new JSDOM(html, {
    url: options.url || 'file:///docs/CLIENT_API.html', runScripts: 'dangerously', virtualConsole,
    beforeParse(window) {
      window.scrollTo = () => {};
      window.HTMLElement.prototype.scrollIntoView = () => {};
      options.beforeParse?.(window);
    },
  });
  t.after(() => { dom.window.close(); assert.deepEqual(errors, []); });
  return dom.window;
}

test('HTML is deterministic, self-contained, and both delivery copies are current', async () => {
  assert.equal(html, await build());
  assert.equal(html, await readFile(path.join(root, 'backend/CLIENT_API.html'), 'utf8'));
  assert.equal(html, await readFile(path.join(root, 'public/docs/client-api.html'), 'utf8'));
  const version = createHash('sha256').update(html).digest('hex').slice(0, 16);
  assert.match(await readFile(path.join(root, 'app/client-docs-manifest.ts'), 'utf8'), new RegExp('client-api\\.html\\?v=' + version));
  const dom = new JSDOM(html);
  assert.equal(dom.window.document.querySelectorAll('.docs-page').length, pages.length + modelCatalog.length + assetOperations.length);
  assert.equal(dom.window.document.querySelectorAll('script[src], link[rel="stylesheet"], iframe, form').length, 0);
  assert.match(dom.window.document.querySelector('meta[http-equiv]').content, /connect-src 'none'/);
  const ids = [...dom.window.document.querySelectorAll('[id]')].map(el => el.id);
  assert.equal(new Set(ids).size, ids.length);
  for (const link of dom.window.document.querySelectorAll('a[href^="#"]')) {
    assert.ok(dom.window.document.getElementById(decodeURIComponent(link.hash.slice(1))), link.href);
  }
  assert.match(escapeHtml('<script>"&'), /&lt;script&gt;&quot;&amp;/);
  dom.window.close();
});

test('every model and original asset operation has a dedicated navigable reference', t => {
  const window = reader(t);
  const { document } = window;
  for (const model of modelCatalog) {
    const id = 'model-' + model.id;
    const article = document.getElementById(id);
    assert.ok(article, model.id);
    assert.ok(article.querySelector('.endpoint-bar'), model.id);
    assert.match(article.textContent, /请求|参数/);
    assert.match(article.textContent, /响应|结果/);
    assert.ok([...document.querySelectorAll('.page-link')].some(link => link.dataset.page === id));
  }
  for (const [id, , , method, endpoint] of assetOperations) {
    const article = document.getElementById(id);
    assert.ok(article, id);
    assert.equal(article.querySelector('.endpoint-bar .method').textContent, method);
    assert.equal(article.querySelector('.endpoint-bar code').textContent, endpoint);
  }
  window.location.hash = '#model-gpt-image-2.5-flare';
  window.dispatchEvent(new window.HashChangeEvent('hashchange'));
  const active = document.querySelector('[aria-current="page"]');
  assert.equal(active.dataset.page, 'model-gpt-image-2.5-flare');
  assert.equal(active.closest('details').open, true);
  window.location.hash = '#asset-get';
  window.dispatchEvent(new window.HashChangeEvent('hashchange'));
  assert.equal(document.querySelector('.docs-page:not([hidden])').id, 'asset-get');
});

test('navigation and deep links show only the requested page', t => {
  const window = reader(t, { url: 'file:///docs/CLIENT_API.html#images--gpt-image-与渠道差异' });
  const { document } = window;
  assert.equal(document.querySelector('.docs-page:not([hidden])').id, 'images');
  assert.equal(document.querySelector('[aria-current="page"]').dataset.page, 'images');
  assert.ok(document.querySelector('#toc a[href="#images--创建图片"]'));
  window.location.hash = '#videos';
  window.dispatchEvent(new window.HashChangeEvent('hashchange'));
  assert.equal(document.querySelector('.docs-page:not([hidden])').id, 'videos');
  window.location.hash = '#not-a-real-page';
  window.dispatchEvent(new window.HashChangeEvent('hashchange'));
  assert.equal(document.querySelector('.docs-page:not([hidden])').id, 'start');
});

test('search covers body, model names, routes, and error codes without injecting markup', t => {
  const window = reader(t);
  const { document } = window;
  const search = document.getElementById('search');
  for (const query of ['GPT-IMAGE-2.5-FLARE', '/v1/audio/speech', 'idempotency_outcome_unknown', '30 秒']) {
    search.value = query;
    search.dispatchEvent(new window.Event('input'));
    assert.ok(document.querySelectorAll('#search-results a').length > 0, query);
    assert.equal(document.getElementById('navigation').hidden, true);
  }
  search.value = '<img src=x onerror=alert(1)>';
  search.dispatchEvent(new window.Event('input'));
  assert.equal(document.querySelectorAll('#search-results img').length, 0);
  assert.match(document.getElementById('search-status').textContent, /没有匹配/);
  search.value = '';
  search.dispatchEvent(new window.Event('input'));
  assert.equal(document.getElementById('navigation').hidden, false);
});

test('code copy preserves source exactly and reports success', async t => {
  let copied;
  const window = reader(t, { beforeParse(w) {
    Object.defineProperty(w.navigator, 'clipboard', { value: { writeText: async text => { copied = text; } } });
  }});
  const block = window.document.querySelector('.code-block');
  block.querySelector('.copy-code').click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(copied, block.querySelector('code').textContent);
  assert.equal(window.document.getElementById('toast').textContent, '代码已复制');
});

test('language tabs copy the selected example and JavaScript examples parse', async t => {
  let copied = '';
  const window = reader(t, { beforeParse(w) {
    Object.defineProperty(w.navigator, 'clipboard', { value: { writeText: async value => { copied = value; } } });
  }});
  const { document } = window;
  for (const code of document.querySelectorAll('pre[data-language="javascript"] code')) {
    assert.doesNotThrow(() => new vm.Script('(async () => {\n' + code.textContent + '\n})'));
  }
  const block = document.querySelector('.code-block:has(.code-tab)');
  block.querySelector('[data-language="python"]').click();
  assert.equal(block.querySelector('pre:not([hidden])').dataset.language, 'python');
  block.querySelector('.copy-code').click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(copied, block.querySelector('pre[data-language="python"] code').textContent);
  assert.match(copied, /urllib.request/);
  block.querySelector('.code-tab[aria-selected="true"]').focus();
  document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'ArrowLeft' }));
  assert.equal(block.querySelector('pre:not([hidden])').dataset.language, 'javascript');
});

test('offline clipboard fallback, failure feedback, menu, keyboard, and print', async t => {
  let prints = 0;
  const window = reader(t, { beforeParse(w) {
    w.print = () => { prints++; };
    w.document.execCommand = () => false;
  }});
  const { document } = window;
  document.querySelector('.copy-code').click();
  await new Promise(resolve => setImmediate(resolve));
  assert.match(document.getElementById('toast').textContent, /复制失败/);
  assert.equal(document.querySelector('textarea'), null);
  document.getElementById('menu').click();
  assert.equal(document.getElementById('menu').getAttribute('aria-expanded'), 'true');
  document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape' }));
  assert.equal(document.getElementById('menu').getAttribute('aria-expanded'), 'false');
  document.getElementById('menu').focus();
  document.dispatchEvent(new window.KeyboardEvent('keydown', { key: '/' }));
  assert.equal(document.activeElement.id, 'search');
  document.getElementById('print').click();
  assert.equal(prints, 1);
});
