// 우리의 족보 - 웹 공유 서버.
//
// PC 프로그램은 족보를 고칠 때마다 그 사본과 사진을 여기 올리고, 가족은 공유
// 링크로 그 사본을 봅니다. 링크의 아이디(무작위 12자)가 곧 열쇠입니다. 화면(frontend)은 PC 와 같은 것을 쓰므로
// 화면이 부르는 /api 중 보기에 필요한 것만 사본으로 답하고, 고치는 요청은
// 모두 거절합니다.
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
// 저장은 Netlify Blobs 의 jocbo-share 저장소에 공유 아이디별로 둡니다.
// 쿠키 서명에 SHARE_SECRET 환경 변수를 씁니다(Netlify 사이트 설정에서 넣습니다).
// 예전에 비밀번호를 정해 만든 공유도 이제 비밀번호 없이 열립니다.
import { getStore } from '@netlify/blobs';
import { createHmac, randomBytes, timingSafeEqual, createHash } from 'node:crypto';
import type { Config, Context } from '@netlify/functions';

const COOKIE = 'jocbo_share';
const DAYS = 30;
const READ_ONLY = '공유된 족보는 볼 수만 있습니다. 고치는 것은 족보 주인의 PC 프로그램에서 합니다.';

type Meta = { token: string; created: number };

const store = () => getStore({ name: 'jocbo-share', consistency: 'strong' });

function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...headers },
  });
}

const fail = (status: number, detail: string) => json({ detail }, status);
const sha = (value: string) => createHash('sha256').update(value).digest('hex');

function same(a: string, b: string) {
  const x = Buffer.from(a), y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

function secret() {
  const value = Netlify.env.get('SHARE_SECRET');
  if (!value) throw new Error('SHARE_SECRET is not set');
  return value;
}

function sign(id: string, until: number) {
  return createHmac('sha256', secret()).update(`${id}.${until}`).digest('hex');
}

/** 쿠키가 열어 준 공유 아이디. 없거나 기한이 지났으면 빈 문자열. */
function viewer(req: Request) {
  const cookie = (req.headers.get('cookie') || '').split(/;\s*/).find(c => c.startsWith(COOKIE + '='));
  if (!cookie) return '';
  const [id, until, mac] = cookie.slice(COOKIE.length + 1).split('.');
  if (!id || !until || !mac || Number(until) < Date.now()) return '';
  return same(mac, sign(id, Number(until))) ? id : '';
}

async function meta(id: string) {
  if (!/^[a-z0-9]{12}$/.test(id)) return null;
  return (await store().get(`${id}/meta`, { type: 'json' })) as Meta | null;
}

/** PC 프로그램이 보낸 올리기 열쇠가 이 공유의 것인지. */
async function owner(req: Request, id: string) {
  const found = await meta(id);
  const token = (req.headers.get('authorization') || '').replace(/^Bearer\s+/i, '');
  return found && token && same(sha(token), found.token) ? found : null;
}

export default async (req: Request, context: Context) => {
  const url = new URL(req.url);
  const parts = url.pathname.replace(/^\/api\/?/, '').split('/').filter(Boolean);
  const method = req.method;
  const blobs = store();

  // -- PC 프로그램 ------------------------------------------------------
  if (parts[0] === 'share') {
    const id = parts[1] || '';

    if (method === 'POST' && parts.length === 1) {
      const newId = randomBytes(9).toString('base64url').toLowerCase().replace(/[^a-z0-9]/g, '').padEnd(12, '0').slice(0, 12);
      const token = randomBytes(32).toString('hex');
      await blobs.setJSON(`${newId}/meta`, { token: sha(token), created: Date.now() });
      return json({ id: newId, token }, 201);
    }

    if (method === 'PUT' && parts.length === 2) {
      const found = await owner(req, id);
      if (!found) return fail(403, '공유 열쇠가 맞지 않습니다.');
      const body = await req.json().catch(() => null);
      if (!body || typeof body.book !== 'object') return fail(400, '족보 사본이 없습니다.');
      await blobs.setJSON(`${id}/book`, body.book);
      return json({ ok: true, files: (await blobs.list({ prefix: `${id}/files/` })).blobs.map(b => b.key.split('/').pop()) });
    }

    if (method === 'PUT' && parts[2] === 'files' && parts[3]) {
      if (!(await owner(req, id))) return fail(403, '공유 열쇠가 맞지 않습니다.');
      const kind = url.searchParams.get('size') === 'thumb' ? 'thumbs' : 'files';
      const type = req.headers.get('content-type') || 'application/octet-stream';
      await blobs.set(`${id}/${kind}/${Number(parts[3])}`, await req.arrayBuffer(), { metadata: { type } });
      return json({ ok: true });
    }

    if (method === 'DELETE' && parts.length === 2) {
      if (!(await owner(req, id))) return fail(403, '공유 열쇠가 맞지 않습니다.');
      const { blobs: all } = await blobs.list({ prefix: `${id}/` });
      await Promise.all(all.map(b => blobs.delete(b.key)));
      return json({ ok: true });
    }

    // -- 가족: 비밀번호 화면 ---------------------------------------------
    if (method === 'GET' && parts[2] === 'info') {
      const book = await blobs.get(`${id}/book`, { type: 'json' });
      if (!(await meta(id)) || !book) return fail(404, '공유가 끝났거나 없는 주소입니다.');
      return json({ title: book.title || '', opened: viewer(req) === id });
    }

    // view 는 쿠키와 족보 사본을 한 번에 줍니다. 화면이 여러 번 묻던 것을 한 번으로
    // 줄여, 링크를 연 뒤 족보가 뜨기까지 걸리던 4초 남짓을 1초 안팎으로 줄입니다.
    // open 은 view 이전의 화면을 위해 남겨 둡니다.
    if (method === 'POST' && (parts[2] === 'open' || parts[2] === 'view')) {
      const [found, book] = await Promise.all([meta(id), blobs.get(`${id}/book`, { type: 'json' })]);
      if (!found || !book) return fail(404, '공유가 끝났거나 없는 주소입니다.');
      const until = Date.now() + DAYS * 86400000;
      const cookie = `${COOKIE}=${id}.${until}.${sign(id, until)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${DAYS * 86400}`
        + (url.protocol === 'https:' ? '; Secure' : '');
      return json(parts[2] === 'view' ? { book } : { ok: true }, 200, { 'Set-Cookie': cookie });
    }
    return fail(404, '없는 요청입니다.');
  }

  // -- 가족: 화면이 부르는 /api (보기만) ---------------------------------
  if (method !== 'GET') return fail(403, READ_ONLY);
  const id = viewer(req);
  // 족보 내용은 화면이 붙여 보내는 공유 아이디가 쿠키의 것과 같을 때만 줍니다. 아이디
  // 없이 묻는 화면(꼬리 없는 주소)에는 전에 연 공유가 있어도 주지 않습니다. 사진(<img>)은
  // 아이디를 붙일 수 없어 쿠키만 보되, 그 족보에 있는 파일만 줍니다.
  const asked = req.headers.get('x-share') || '';
  if (!id || (parts[0] !== 'files' && asked !== id)) return fail(401, '공유 링크로 다시 들어와 주십시오.');
  const book = (await blobs.get(`${id}/book`, { type: 'json' })) as Record<string, any> | null;
  if (!book) return fail(404, '공유가 끝났습니다.');

  if (parts[0] === 'me') return json({ email: '' });
  if (parts[0] === 'books' && parts.length === 1) return json([{ id: book.id, title: book.title }]);
  if (parts[0] === 'books' && Number(parts[1]) === book.id) return json(book);
  if (parts[0] === 'files' && parts[1]) {
    const fid = Number(parts[1]);
    if (!book.files?.some((f: { id: number }) => f.id === fid)) return fail(404, '파일이 없습니다.');
    const small = url.searchParams.get('size') ? await blobs.getWithMetadata(`${id}/thumbs/${fid}`, { type: 'arrayBuffer' }) : null;
    const found = small || (await blobs.getWithMetadata(`${id}/files/${fid}`, { type: 'arrayBuffer' }));
    if (!found) return fail(404, '아직 올라오지 않은 파일입니다.');
    return new Response(found.data, {
      headers: { 'Content-Type': String(found.metadata.type || 'application/octet-stream'),
                 'Cache-Control': 'private, max-age=3600', 'X-Content-Type-Options': 'nosniff' },
    });
  }
  if (parts[0] === 'claude') return json({ available: false, configured: false });
  return fail(404, '공유 화면에서는 쓸 수 없는 기능입니다.');
};

export const config: Config = { path: '/api/*' };
