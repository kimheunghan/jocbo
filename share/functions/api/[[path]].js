// 우리의 족보 - 웹 공유 서버 (Cloudflare Pages Functions).
//
// PC 프로그램은 족보를 고칠 때마다 그 사본과 사진을 여기 올리고, 가족은 공유
// 링크로 그 사본을 봅니다. 링크의 아이디(무작위 12자)가 곧 열쇠입니다. 화면(frontend)은
// PC 와 같은 것을 쓰므로 화면이 부르는 /api 중 보기에 필요한 것만 사본으로 답하고,
// 고치는 요청은 모두 거절합니다. netlify/functions/api.mts 와 같은 일을 합니다.
//
//   PC 프로그램 (Authorization: Bearer 올리기 열쇠)
//     POST   /api/share                     공유 만들기 -> { id, token }
//     PUT    /api/share/:id                 족보 사본 올리기
//     PUT    /api/share/:id/files/:fid      사진 올리기 (?size=thumb 이면 카드용 작은 사진)
//     DELETE /api/share/:id                 공유 끝내기
//   가족 (쿠키)
//     GET    /api/share/:id/info            여는 화면에 쓸 족보 이름
//     POST   /api/share/:id/view            쿠키와 족보 사본을 한 번에 (사진도 이 쿠키로 엽니다)
//     POST   /api/share/:id/open            쿠키만 (view 이전 화면용)
//     GET    /api/me, /api/books, /api/books/:bid, /api/files/:fid
//
// 저장은 D1 데이터베이스(바인딩 DB, schema.sql)에, 쿠키 서명은 비밀값 SHARE_SECRET 으로 합니다.

const COOKIE = 'jocbo_share';
const DAYS = 30;
const READ_ONLY = '공유된 족보는 볼 수만 있습니다. 고치는 것은 족보 주인의 PC 프로그램에서 합니다.';
// D1 은 한 칸에 2MB 까지 담습니다.
const LARGEST = 1_900_000;

const encoder = new TextEncoder();
const hex = buffer => [...new Uint8Array(buffer)].map(b => b.toString(16).padStart(2, '0')).join('');
const sha = async value => hex(await crypto.subtle.digest('SHA-256', encoder.encode(value)));

function json(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...headers },
  });
}

const fail = (status, detail) => json({ detail }, status);

function same(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function sign(env, id, until) {
  if (!env.SHARE_SECRET) throw new Error('SHARE_SECRET is not set');
  const key = await crypto.subtle.importKey('raw', encoder.encode(env.SHARE_SECRET),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return hex(await crypto.subtle.sign('HMAC', key, encoder.encode(`${id}.${until}`)));
}

function newId() {
  const letters = 'abcdefghijklmnopqrstuvwxyz0123456789';
  return [...crypto.getRandomValues(new Uint8Array(12))].map(b => letters[b % 36]).join('');
}

/** 쿠키가 열어 준 공유 아이디. 없거나 기한이 지났으면 빈 문자열. */
async function viewer(request, env) {
  const cookie = (request.headers.get('cookie') || '').split(/;\s*/).find(c => c.startsWith(COOKIE + '='));
  if (!cookie) return '';
  const [id, until, mac] = cookie.slice(COOKIE.length + 1).split('.');
  if (!id || !until || !mac || Number(until) < Date.now()) return '';
  return same(mac, await sign(env, id, Number(until))) ? id : '';
}

async function share(env, id) {
  if (!/^[a-z0-9]{12}$/.test(id)) return null;
  return env.DB.prepare('SELECT id, token FROM shares WHERE id = ?').bind(id).first();
}

async function bookOf(env, id) {
  const row = await env.DB.prepare('SELECT data FROM books WHERE id = ?').bind(id).first();
  return row ? JSON.parse(row.data) : null;
}

/** PC 프로그램이 보낸 올리기 열쇠가 이 공유의 것인지. */
async function owner(request, env, id) {
  const found = await share(env, id);
  const token = (request.headers.get('authorization') || '').replace(/^Bearer\s+/i, '');
  return found && token && same(await sha(token), found.token) ? found : null;
}

export async function onRequest({ request, env, params }) {
  const url = new URL(request.url);
  const parts = [].concat(params.path || []).filter(Boolean);
  const method = request.method;
  const db = env.DB;

  // -- PC 프로그램 ------------------------------------------------------
  if (parts[0] === 'share') {
    const id = parts[1] || '';

    if (method === 'POST' && parts.length === 1) {
      const id = newId();
      const token = hex(crypto.getRandomValues(new Uint8Array(32)));
      await db.prepare('INSERT INTO shares (id, token, created) VALUES (?, ?, ?)').bind(id, await sha(token), Date.now()).run();
      return json({ id, token }, 201);
    }

    if (method === 'PUT' && parts.length === 2) {
      if (!(await owner(request, env, id))) return fail(403, '공유 열쇠가 맞지 않습니다.');
      const body = await request.json().catch(() => null);
      if (!body || typeof body.book !== 'object') return fail(400, '족보 사본이 없습니다.');
      await db.prepare('INSERT INTO books (id, data) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET data = excluded.data')
        .bind(id, JSON.stringify(body.book)).run();
      const { results } = await db.prepare("SELECT fid FROM files WHERE id = ? AND kind = 'files'").bind(id).all();
      return json({ ok: true, files: results.map(row => String(row.fid)) });
    }

    if (method === 'PUT' && parts[2] === 'files' && parts[3]) {
      if (!(await owner(request, env, id))) return fail(403, '공유 열쇠가 맞지 않습니다.');
      const kind = url.searchParams.get('size') === 'thumb' ? 'thumbs' : 'files';
      const data = await request.arrayBuffer();
      if (data.byteLength > LARGEST) return fail(413, '파일이 너무 커서 올리지 않았습니다.');
      const type = request.headers.get('content-type') || 'application/octet-stream';
      await db.prepare('INSERT INTO files (id, fid, kind, type, data) VALUES (?, ?, ?, ?, ?) '
        + 'ON CONFLICT(id, fid, kind) DO UPDATE SET type = excluded.type, data = excluded.data')
        .bind(id, Number(parts[3]), kind, type, data).run();
      return json({ ok: true });
    }

    if (method === 'DELETE' && parts.length === 2) {
      if (!(await owner(request, env, id))) return fail(403, '공유 열쇠가 맞지 않습니다.');
      await db.batch([
        db.prepare('DELETE FROM files WHERE id = ?').bind(id),
        db.prepare('DELETE FROM books WHERE id = ?').bind(id),
        db.prepare('DELETE FROM shares WHERE id = ?').bind(id),
      ]);
      return json({ ok: true });
    }

    // -- 가족: 여는 화면 --------------------------------------------------
    if (method === 'GET' && parts[2] === 'info') {
      const book = (await share(env, id)) && (await bookOf(env, id));
      if (!book) return fail(404, '공유가 끝났거나 없는 주소입니다.');
      return json({ title: book.title || '', opened: (await viewer(request, env)) === id });
    }

    // view 는 쿠키와 족보 사본을 한 번에 줍니다. 화면이 여러 번 묻던 것을 한 번으로 줄입니다.
    if (method === 'POST' && (parts[2] === 'open' || parts[2] === 'view')) {
      const book = (await share(env, id)) && (await bookOf(env, id));
      if (!book) return fail(404, '공유가 끝났거나 없는 주소입니다.');
      const until = Date.now() + DAYS * 86400000;
      const cookie = `${COOKIE}=${id}.${until}.${await sign(env, id, until)}; Path=/; HttpOnly; SameSite=Lax; `
        + `Max-Age=${DAYS * 86400}` + (url.protocol === 'https:' ? '; Secure' : '');
      return json(parts[2] === 'view' ? { book } : { ok: true }, 200, { 'Set-Cookie': cookie });
    }
    return fail(404, '없는 요청입니다.');
  }

  // -- 가족: 화면이 부르는 /api (보기만) ---------------------------------
  if (method !== 'GET') return fail(403, READ_ONLY);
  const id = await viewer(request, env);
  // 족보 내용은 화면이 붙여 보내는 공유 아이디가 쿠키의 것과 같을 때만 줍니다. 아이디
  // 없이 묻는 화면(꼬리 없는 주소)에는 전에 연 공유가 있어도 주지 않습니다. 사진(<img>)은
  // 아이디를 붙일 수 없어 쿠키만 보되, 그 족보에 있는 파일만 줍니다.
  const asked = request.headers.get('x-share') || '';
  if (!id || (parts[0] !== 'files' && asked !== id)) return fail(401, '공유 링크로 다시 들어와 주십시오.');
  const book = await bookOf(env, id);
  if (!book) return fail(404, '공유가 끝났습니다.');

  if (parts[0] === 'me') return json({ email: '' });
  if (parts[0] === 'books' && parts.length === 1) return json([{ id: book.id, title: book.title }]);
  if (parts[0] === 'books' && Number(parts[1]) === book.id) return json(book);
  if (parts[0] === 'files' && parts[1]) {
    const fid = Number(parts[1]);
    if (!book.files?.some(f => f.id === fid)) return fail(404, '파일이 없습니다.');
    const pick = kind => db.prepare('SELECT type, data FROM files WHERE id = ? AND fid = ? AND kind = ?').bind(id, fid, kind).first();
    const found = (url.searchParams.get('size') ? await pick('thumbs') : null) || (await pick('files'));
    if (!found) return fail(404, '아직 올라오지 않은 파일입니다.');
    return new Response(new Uint8Array(found.data), {
      headers: { 'Content-Type': found.type, 'Cache-Control': 'private, max-age=3600', 'X-Content-Type-Options': 'nosniff' },
    });
  }
  if (parts[0] === 'claude') return json({ available: false, configured: false });
  return fail(404, '공유 화면에서는 쓸 수 없는 기능입니다.');
}
