(() => {
  const menu = document.querySelector('.menu-button');
  const sidebar = document.querySelector('.sidebar');
  const closeMenu = () => {sidebar.classList.remove('open'); menu.setAttribute('aria-expanded', 'false');};
  menu.addEventListener('click', () => {
    menu.setAttribute('aria-expanded', String(sidebar.classList.toggle('open')));
  });
  document.addEventListener('click', event => {
    if (!sidebar.contains(event.target) && !menu.contains(event.target)) closeMenu();
  });
  document.addEventListener('keydown', event => {if (event.key === 'Escape') closeMenu();});

  document.querySelectorAll('pre').forEach(pre => {
    const code = pre.querySelector('code');
    const wrapper = document.createElement('div');
    wrapper.className = 'code-block';
    const toolbar = document.createElement('div');
    toolbar.className = 'code-toolbar';
    const label = document.createElement('span');
    label.textContent = code.className.replace('language-', '') || 'text';
    const button = document.createElement('button');
    button.className = 'copy-button';
    button.textContent = 'コピー';
    button.setAttribute('aria-label', 'コードをコピー');
    button.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(code.textContent);
        button.textContent = 'コピー済み';
        document.querySelector('#copy-status').textContent = 'コードをコピーしました';
      } catch {
        const range = document.createRange();
        range.selectNodeContents(code);
        const selection = window.getSelection();
        selection.removeAllRanges(); selection.addRange(range);
        button.textContent = '手動コピー';
        document.querySelector('#copy-status').textContent = 'コードを選択しました。コピーキーでコピーしてください';
      }
      setTimeout(() => {button.textContent = 'コピー';}, 2200);
    });
    pre.tabIndex = 0;
    toolbar.append(label, button);
    pre.before(wrapper); wrapper.append(toolbar, pre);
  });

  const dialog = document.querySelector('.search-dialog');
  const input = document.querySelector('#search-input');
  const results = document.querySelector('#search-results');
  const status = document.querySelector('#search-status');
  const search = () => {
    const query = input.value.trim().toLocaleLowerCase();
    const words = query.split(/\s+/).filter(Boolean);
    const matches = (window.DOC_SEARCH || []).filter(page => words.every(word => (page.title + ' ' + page.text).toLocaleLowerCase().includes(word)));
    results.replaceChildren();
    status.textContent = query ? `${matches.length} 件のページ` : 'よく使うページ';
    (query ? matches : matches.slice(0, 4)).forEach(page => {
      const link = document.createElement('a'); link.href = page.url;
      const title = document.createElement('strong'); title.textContent = page.title;
      const excerpt = document.createElement('p');
      const position = query ? page.text.toLocaleLowerCase().indexOf(words[0]) : 0;
      const start = Math.max(0, position - 30);
      excerpt.textContent = page.group + ' · ' + (start ? '…' : '') + page.text.slice(start, start + 125).replace(/[#`>*]/g, '') + '…';
      link.append(title, excerpt); results.append(link);
    });
    if (!matches.length) status.textContent = '一致するページがありません。別のキーワードをお試しください。';
  };
  const openSearch = () => {dialog.showModal(); search(); input.focus();};
  document.querySelector('.search-trigger').addEventListener('click', openSearch);
  document.querySelector('.search-close').addEventListener('click', () => dialog.close());
  input.addEventListener('input', search);
  input.addEventListener('keydown', event => {
    if (event.key === 'ArrowDown') {event.preventDefault(); results.querySelector('a')?.focus();}
    if (event.key === 'Enter') results.querySelector('a')?.click();
  });
  dialog.addEventListener('click', event => {if (event.target === dialog) {
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
  }});
  document.addEventListener('keydown', event => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault(); if (!dialog.open) openSearch(); else dialog.close();
    }
  });
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) {
        document.querySelectorAll('.outline a').forEach(a => a.classList.toggle('active', a.hash === '#' + entry.target.id));
      }
    }, {rootMargin: '-80px 0px -65% 0px'});
    document.querySelectorAll('article h2,article h3').forEach(heading => observer.observe(heading));
  }
})();
