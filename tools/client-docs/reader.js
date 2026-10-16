(() => {
  const pages = [...document.querySelectorAll('.docs-page')];
  const byId = new Map(pages.map(page => [page.id, page]));
  const sidebar = document.getElementById('sidebar');
  const menu = document.getElementById('menu');
  const toc = document.getElementById('toc');
  const search = document.getElementById('search');
  const results = document.getElementById('search-results');
  const navigation = document.getElementById('navigation');
  const status = document.getElementById('search-status');
  let active = '';
  let toastTimer;

  function navigate() {
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { id = ''; }
    const target = document.getElementById(id);
    const page = byId.get(id) || target?.closest('.docs-page') || pages[0];
    pages.forEach(item => { item.hidden = item !== page; });
    document.querySelectorAll('.page-link').forEach(link => {
      if (link.dataset.page === page.id) {
        link.setAttribute('aria-current', 'page');
        const folder = link.closest('details');
        if (folder) folder.open = true;
      }
      else link.removeAttribute('aria-current');
    });
    document.getElementById('current-page').textContent = page.dataset.label;
    document.title = `${page.dataset.label} · 星辰平台 API 文档`;
    toc.replaceChildren();
    page.querySelectorAll('h2, h3').forEach(heading => {
      const link = document.createElement('a');
      link.href = `#${heading.id}`;
      link.textContent = heading.textContent;
      if (heading.tagName === 'H3') link.className = 'sub';
      toc.append(link);
    });
    sidebar.classList.remove('open');
    menu.setAttribute('aria-expanded', 'false');
    if (target?.closest('.docs-page') && target !== page) target.scrollIntoView({ block: 'start' });
    else if (active !== page.id) window.scrollTo(0, 0);
    active = page.id;
  }

  const index = pages.flatMap(page => {
    const entries = [];
    let current;
    for (const element of page.children) {
      if (/^H[123]$/.test(element.tagName)) {
        current = { id: element.id, page: page.dataset.label, title: element.textContent, body: '' };
        entries.push(current);
      } else if (current) current.body += ' ' + element.textContent;
    }
    return entries;
  });
  search.addEventListener('input', () => {
    const terms = search.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    results.replaceChildren();
    navigation.hidden = !!terms.length;
    results.hidden = !terms.length;
    if (!terms.length) { status.textContent = ''; return; }
    const matches = index.filter(item => terms.every(term => `${item.title} ${item.body}`.toLocaleLowerCase().includes(term)));
    status.textContent = matches.length ? `找到 ${matches.length} 处，显示前 ${Math.min(matches.length, 25)} 处` : '没有匹配结果，请换一个关键词';
    matches.slice(0, 25).forEach(item => {
      const link = document.createElement('a');
      link.href = `#${item.id}`;
      const title = document.createElement('b');
      title.textContent = item.title;
      const description = document.createElement('small');
      const query = terms[0];
      const offset = Math.max(0, item.body.toLocaleLowerCase().indexOf(query) - 20);
      description.textContent = `${item.page} · ${item.body.slice(offset, offset + 90)}`;
      link.append(title, description);
      results.append(link);
    });
  });
  function toast(message) {
    const element = document.getElementById('toast');
    element.textContent = message;
    element.classList.add('visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => element.classList.remove('visible'), 2200);
  }
  document.addEventListener('click', async event => {
    const tab = event.target.closest('.code-tab');
    if (tab) {
      const block = tab.closest('.code-block');
      block.querySelectorAll('pre').forEach(pre => { pre.hidden = pre.dataset.language !== tab.dataset.language; });
      block.querySelectorAll('.code-tab').forEach(item => {
        item.setAttribute('aria-selected', String(item === tab));
        item.tabIndex = item === tab ? 0 : -1;
      });
      return;
    }
    const button = event.target.closest('.copy-code, .copy-path');
    if (!button) return;
    const value = button.dataset.path || button.closest('.code-block').querySelector('pre:not([hidden]) code').textContent;
    try {
      try { await navigator.clipboard.writeText(value); }
      catch {
        // Local file and sandboxed console readers may not have Clipboard API permission.
        const textarea = document.createElement('textarea');
        textarea.value = value;
        textarea.style.cssText = 'position:fixed;left:-9999px;top:0';
        document.body.append(textarea);
        try {
          textarea.select();
          if (!document.execCommand('copy')) throw new Error('copy denied');
        } finally { textarea.remove(); button.focus(); }
      }
      toast(button.dataset.path ? '接口路径已复制' : '代码已复制');
    } catch { toast('复制失败，请选中代码后手动复制'); }
  });
  menu.addEventListener('click', () => {
    const open = sidebar.classList.toggle('open');
    menu.setAttribute('aria-expanded', String(open));
    if (open) search.focus();
  });
  document.getElementById('print').addEventListener('click', () => window.print());
  document.addEventListener('keydown', event => {
    if (document.activeElement.classList.contains('code-tab') && ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const tabs = [...document.activeElement.closest('.code-tabs').querySelectorAll('.code-tab')];
      const index = tabs.indexOf(document.activeElement);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      tabs[next].click();
      tabs[next].focus();
      return;
    }
    if ((event.key === '/' || (event.key.toLowerCase() === 'k' && (event.ctrlKey || event.metaKey))) && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
      event.preventDefault();
      sidebar.classList.add('open');
      menu.setAttribute('aria-expanded', 'true');
      search.focus();
    }
    if (event.key === 'Escape') {
      search.value = '';
      search.dispatchEvent(new Event('input'));
      sidebar.classList.remove('open');
      menu.setAttribute('aria-expanded', 'false');
    }
  });
  window.addEventListener('hashchange', navigate);
  navigate();
})();
