// 우리의 족보 - 공유 화면.
// PC 와 같은 화면(app.js)을 그대로 띄우되, 링크로 들어오면 바로 열고, 고치는
// 단추를 감추고 가계도부터 보여 줍니다.
// app.js 보다 먼저 실행되어야 하므로 build.mjs 가 app.js 앞에 넣습니다.
(() => {
  const id = (location.pathname.match(/^\/s\/([a-z0-9]{12})\/?$/) || [])[1] || '';
  document.documentElement.classList.add('share-mode');

  // 족보는 링크를 여는 즉시 한 번에 받아 옵니다(쿠키도 함께 받아 사진이 열립니다).
  // 화면(app.js)이 묻는 나와 족보 목록·족보 내용은 이 하나로 바로 답해, 공유 사이트에
  // 다섯 번 차례로 묻던 것을 한 번으로 줄입니다.
  const fetchOriginal = window.fetch.bind(window);
  const view = id
    ? fetchOriginal(`/api/share/${id}/view`, { method: 'POST' }).then(async response => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw Error(body.detail || '공유가 끝났거나 없는 주소입니다.');
        return body.book;
      })
    : Promise.reject(Error('족보 주인에게 받은 공유 링크로 들어와 주십시오.'));
  view.catch(() => {});
  const reply = (data, status = 200) =>
    new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

  window.fetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : input.url;
    if (url.startsWith('/api')) {
      const path = url.split('?')[0];
      if ((init.method || 'GET').toUpperCase() === 'GET') {
        if (path === '/api/me' || path === '/api/books' || /^\/api\/books\/\d+(\/share)?$/.test(path)) {
          let book;
          try { book = await view; } catch (err) { return reply({ detail: err.message }, 401); }
          if (path === '/api/me') return reply({ email: '' });
          if (path === '/api/books') return reply([{ id: book.id, title: book.title }]);
          if (path.endsWith('/share')) return reply({ shared: false });
          return Number(path.split('/').pop()) === book.id ? reply(book) : reply({ detail: '족보를 찾을 수 없습니다.' }, 404);
        }
      }
      // 그 밖의 요청에는 지금 연 공유의 아이디를 붙입니다. 서버는 쿠키가 연 공유와
      // 다르면 거절합니다.
      const headers = new Headers(init.headers || {});
      headers.set('X-Share', id);
      init = { ...init, headers };
    }
    return fetchOriginal(input, init);
  };

  // 인물 창은 보기 전용으로 엽니다. 칸은 읽기만 되고 저장·삭제 단추는 감춥니다.
  const showModal = HTMLDialogElement.prototype.showModal;
  HTMLDialogElement.prototype.showModal = function () {
    showModal.call(this);
    if (this.id === 'personDialog') {
      // app.js 는 창을 연 다음에 제목을 적으므로 그 뒤에 바꿉니다.
      setTimeout(() => {
        const heading = this.querySelector('#personHeading');
        if (heading) heading.textContent = '인물 정보';
      });
      this.querySelectorAll('input, select, textarea').forEach(field => {
        if (field.type === 'file') return;
        field.readOnly = true;
        if (field.tagName === 'SELECT' || field.type === 'checkbox' || field.type === 'radio') field.disabled = true;
      });
      const cancel = this.querySelector('#cancelPerson');
      if (cancel) cancel.textContent = '닫기';
    }
  };

  const esc = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

  // 들어오면 가계도부터 보여 줍니다.
  function treeFirst() {
    const workspace = document.getElementById('workspace');
    let shown = false;
    new MutationObserver(() => {
      if (!workspace.hidden && !shown) {
        shown = true;
        document.querySelector('[data-view="tree"]')?.click();
        // 휴대폰처럼 좁은 화면에서는 가계도 전체가 한 화면에 들어오게 맞춰 엽니다.
        if (window.innerWidth <= 640) setTimeout(() => document.querySelector('[data-zoom="fit"]')?.click(), 300);
      }
    }).observe(workspace, { attributes: true, attributeFilter: ['hidden'] });
  }

  // 족보가 다 그려질 때까지는 "족보 여는 중" 만 보이고, 빈 화면 틀은 감춰 둡니다.
  function revealWhenDrawn() {
    const title = document.getElementById('bookTitle');
    const shown = () => document.documentElement.classList.add('share-loaded');
    new MutationObserver((_, watcher) => { shown(); watcher.disconnect(); })
      .observe(title, { childList: true, characterData: true, subtree: true });
  }

  // 링크로 들어오면 묻는 것 없이 바로 엽니다. 족보를 받아 오면 app.js 가 스스로 엽니다.
  async function openShare() {
    const form = document.getElementById('authForm');
    const title = document.querySelector('.intro-title');
    const lead = document.querySelector('.intro-lead');
    const text = document.querySelector('.intro-text');
    if (lead) lead.innerHTML = '가족이 함께 보는<br>우리 집안의 기록';
    if (text) text.textContent = '족보 주인이 공유한 가계도입니다.';
    form.classList.add('share-ready');
    form.onsubmit = event => event.preventDefault();
    if (!id) {
      form.innerHTML = '<h2>공유 주소가 아닙니다</h2><p class="muted">족보 주인에게 받은 공유 링크로 들어와 주십시오.</p>';
      return;
    }
    form.innerHTML = '<h2>족보 여는 중…</h2>';
    try {
      const book = await view;
      if (title && book.title) title.innerHTML = `<em>${esc(book.title)}</em>`;
      // app.js 는 시작할 때 이미 enter() 를 불러 두었고, 그것이 위에서 받은 족보로 열립니다.
    } catch (err) {
      form.innerHTML = `<h2>열 수 없는 공유입니다</h2><p class="muted">${esc(err.message || '공유가 끝났거나 없는 주소입니다.')}</p>`;
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    // 공유 화면은 열 때마다 가계도의 표시 항목(세대·본관·생몰일·나이·사진·기록 등)을
    // 모두 켜고 시작합니다. 보는 사람이 그 자리에서 끌 수 있습니다. treeOptions 는 app.js 것.
    for (const name of Object.keys(treeOptions)) treeOptions[name] = true;
    const header = document.querySelector('header > div');
    if (header) header.insertAdjacentHTML('beforeend', '<span class="share-badge">가족 공유 · 보기 전용</span>');
    treeFirst();
    revealWhenDrawn();
    openShare();
  });
})();
