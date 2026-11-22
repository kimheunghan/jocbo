// 우리의 족보·FindInside 라이선스 서버 (Cloudflare Pages Functions 에서 부릅니다).
//
// 결제는 Paddle 이 받고, 키는 여기서 만들어 D1 에 둡니다. 결제 회사가 바뀌어도 키는
// 그대로입니다. Lemon Squeezy 에서 산 키(2027-03-31 결제 종료)도 처음 들어올 때
// 이어받아, 그 뒤로는 여기서 확인합니다.
//
//   Paddle → 여기
//     POST /api/paddle/webhook          결제 완료(transaction.completed) → 키 발급·메일
//                                       환불(adjustment.*, refund·approved) → 키 막기
//   홈페이지
//     GET  /api/license/order?txn=...   구매 완료 화면에 보일 키 (알림이 늦으면 여기서 발급)
//     POST /api/license/resend          {email} → 그 메일로 산 키를 다시 보냄
//   PC 프로그램
//     POST /api/license/activate        {key, name, product} → {activated, instance, product}
//     POST /api/license/deactivate      {key, instance}
//
// 환경 값 (wrangler.toml [vars] 또는 비밀값):
//   PADDLE_ENV              'sandbox' | 'live'
//   PADDLE_PRICES           '{"pri_...":"jocbo","pri_...":"findinside"}'
//   PADDLE_API_KEY          (비밀) 읽기 권한 API 키
//   PADDLE_WEBHOOK_SECRET   (비밀) 알림 서명 키
//   LS_PRODUCTS             '{"1420186":"jocbo","1420193":"findinside"}'
//   MAIL_URL, MAIL_SECRET   (비밀) Gmail 발송 창구(Apps Script)
//   SITE_URL                'https://jocbo.pages.dev'

export const PRODUCTS = {
  jocbo: { name: '우리의 족보 정식판', prefix: 'JOCBO', pcs: 2,
           how: '우리의 족보 프로그램에 로그인한 뒤 오른쪽 위 [정식판]을 누르고, 위 키를 붙여 넣은 뒤 [등록]을 누르십시오.' },
  findinside: { name: 'FindInside 라이선스', prefix: 'FIND', pcs: 2,
                how: 'FindInside 프로그램의 라이선스 입력 칸에 위 키를 붙여 넣고 등록하십시오.' },
};
const LS_API = 'https://api.lemonsqueezy.com/v1/licenses';
const LS_KEY = /^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$/;
const TXN = /^txn_[0-9a-z]{20,40}$/;
const RESEND_GAP = 5 * 60 * 1000;

const encoder = new TextEncoder();
const hex = buffer => [...new Uint8Array(buffer)].map(b => b.toString(16).padStart(2, '0')).join('');

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
  });
}
const fail = (status, detail) => json({ detail }, status);
const parse = (text, fallback) => { try { return JSON.parse(text); } catch { return fallback; } };
const site = env => (env.SITE_URL || 'https://jocbo.pages.dev').replace(/\/$/, '');
const paddleBase = env => env.PADDLE_API_BASE || (env.PADDLE_ENV === 'live' ? 'https://api.paddle.com' : 'https://sandbox-api.paddle.com');

/** JOCBO-7K2Q-M4XD-9PRT-H3VA: 헷갈리는 글자(I·L·O·U)를 뺀 32글자로 80비트. */
export function newKey(product) {
  const letters = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  const body = [...bytes].map(b => letters[b % 32]).join('');
  return [PRODUCTS[product].prefix, body.slice(0, 4), body.slice(4, 8), body.slice(8, 12), body.slice(12, 16)].join('-');
}

const tidyKey = key => String(key || '').trim().toUpperCase();
const tidyEmail = email => String(email || '').trim().toLowerCase();

function same(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** Paddle-Signature: ts=...;h1=... — 서명 키로 `${ts}:${본문}` 을 HMAC-SHA256 한 값. */
export async function paddleSigned(env, header, body, now = Date.now()) {
  if (!env.PADDLE_WEBHOOK_SECRET || !header) return false;
  const parts = Object.fromEntries(header.split(';').map(p => p.split('=')).filter(p => p.length === 2));
  const ts = Number(parts.ts);
  if (!ts || Math.abs(now / 1000 - ts) > 300) return false;
  const key = await crypto.subtle.importKey('raw', encoder.encode(env.PADDLE_WEBHOOK_SECRET),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const mac = hex(await crypto.subtle.sign('HMAC', key, encoder.encode(`${parts.ts}:${body}`)));
  const given = header.split(';').filter(p => p.startsWith('h1=')).map(p => p.slice(3));
  return given.some(h1 => same(h1, mac));
}

async function paddle(env, path) {
  const response = await fetch(paddleBase(env) + path, { headers: { Authorization: `Bearer ${env.PADDLE_API_KEY}` } });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`Paddle ${path}: ${response.status} ${body?.error?.code || ''}`);
  return body.data;
}

// -- 메일 (사장님 Gmail 의 Apps Script 창구) ------------------------------------

function keyMail(env, rows) {
  const who = rows[0].name ? `${rows[0].name} 님, ` : '';
  const lines = rows.map(r => `${PRODUCTS[r.product]?.name || r.product}: ${r.key}`);
  const hows = [...new Set(rows.map(r => PRODUCTS[r.product]?.how).filter(Boolean))];
  const base = site(env);
  const text = [
    `${who}구매해 주셔서 감사합니다.`, '',
    '■ 라이선스 키', ...lines, '',
    '■ 등록 방법', ...hows, '등록할 때는 인터넷 연결이 필요합니다.', '',
    '■ 이용 안내',
    '・키 하나로 PC 2대까지 사용할 수 있습니다. PC를 옮길 때는 쓰지 않을 PC에서 등록을 해제한 뒤 새 PC에 키를 입력하십시오.',
    '・구매 후 14일 안에 이 메일에 회신하시면 환불해 드립니다.',
    `・키를 잃어버리셨다면: ${base}/license`,
    `・사용 안내: ${base}/guide/`, '',
    `주문 번호: ${rows[0].txn}`,
    '문의: 이 메일에 회신해 주십시오.', '',
    `우리의 족보 · ${base}`,
  ].join('\n');
  const esc = s => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]);
  const html = '<div style="font-family:\'Malgun Gothic\',sans-serif;font-size:15px;line-height:1.7;color:#1d2433">'
    + esc(text).replace(/^(.*: )([A-Z0-9-]{20,})$/gm, '$1<b style="font-size:17px;letter-spacing:.04em">$2</b>')
      .replace(/(https:\/\/[^\s<]+)/g, '<a href="$1">$1</a>').replace(/\n/g, '<br>') + '</div>';
  const subject = rows.length === 1 ? `[우리의 족보] ${PRODUCTS[rows[0].product]?.name || '라이선스'} 키 안내` : '[우리의 족보] 라이선스 키 안내';
  return { to: rows[0].email, subject, text, html };
}

/** 보냈으면 true. 창구가 아직 없거나 실패하면 false(다음 기회에 다시 보냅니다). */
export async function sendMail(env, mail) {
  if (!env.MAIL_URL || !env.MAIL_SECRET) return false;
  try {
    const response = await fetch(env.MAIL_URL, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ secret: env.MAIL_SECRET, name: '우리의 족보', ...mail }),
    });
    const body = await response.json().catch(() => ({}));
    return response.ok && body.ok === true;
  } catch {
    return false;
  }
}

async function mailKeys(env, rows) {
  const waiting = rows.filter(r => !r.mailed && r.status === 'active');
  if (!waiting.length) return true;
  if (!(await sendMail(env, keyMail(env, waiting)))) return false;
  const now = Date.now();
  await env.DB.batch(waiting.map(r => env.DB.prepare('UPDATE licenses SET mailed = ? WHERE key = ?').bind(now, r.key)));
  return true;
}

// -- 발급 ---------------------------------------------------------------------

const rowsOf = (env, txn) => env.DB.prepare('SELECT * FROM licenses WHERE txn = ? ORDER BY product, seq').bind(txn).all().then(r => r.results);

/**
 * 결제 하나에 키를 발급합니다. 알림이 두 번 와도, 구매 완료 화면이 먼저 물어도 한 번만
 * 만듭니다(txn·상품·순번이 겹치면 넣지 않음). 결제 내용은 알림 본문을 믿지 않고 Paddle 에 다시 묻습니다.
 */
export async function issue(env, txn) {
  if (!TXN.test(txn)) return { rows: [], state: 'bad' };
  const have = await rowsOf(env, txn);
  if (have.length) return { rows: have, state: 'done' };
  const t = await paddle(env, `/transactions/${txn}`);
  if (!['completed', 'paid'].includes(t.status)) return { rows: [], state: 'pending' };
  const prices = parse(env.PADDLE_PRICES || '{}', {});
  const customer = t.customer_id ? await paddle(env, `/customers/${t.customer_id}`) : {};
  const email = tidyEmail(customer.email);
  const now = Date.now();
  const inserts = [];
  for (const item of t.items || []) {
    const product = prices[item.price?.id || item.price_id];
    if (!product || !PRODUCTS[product]) continue;
    for (let seq = 1; seq <= Math.max(1, Number(item.quantity) || 1); seq++) {
      inserts.push(env.DB.prepare('INSERT OR IGNORE INTO licenses (key, product, email, name, txn, seq, source, status, max_pcs, created, mailed) '
        + "VALUES (?, ?, ?, ?, ?, ?, 'paddle', 'active', ?, ?, 0)")
        .bind(newKey(product), product, email, String(customer.name || ''), txn, seq, PRODUCTS[product].pcs, now));
    }
  }
  if (inserts.length) await env.DB.batch(inserts);
  return { rows: await rowsOf(env, txn), state: 'done' };
}

async function refund(env, adjustment) {
  if (!['refund', 'chargeback', 'chargeback_warning'].includes(adjustment.action)) return;
  if (adjustment.action === 'refund' && adjustment.status !== 'approved') return;
  if (!TXN.test(adjustment.transaction_id || '')) return;
  await env.DB.prepare("UPDATE licenses SET status = 'refunded' WHERE txn = ?").bind(adjustment.transaction_id).run();
}

export async function webhook(request, env) {
  const body = await request.text();
  if (!(await paddleSigned(env, request.headers.get('paddle-signature'), body))) return fail(401, 'bad signature');
  const event = parse(body, {});
  const data = event.data || {};
  if (event.event_type === 'transaction.completed') {
    const { rows } = await issue(env, data.id);
    await mailKeys(env, rows);
  } else if (event.event_type?.startsWith('adjustment.')) {
    await refund(env, data);
  }
  return json({ ok: true });
}

// -- Lemon Squeezy 키 이어받기 ---------------------------------------------------

async function lemon(action, fields) {
  try {
    const response = await fetch(`${LS_API}/${action}`, {
      method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams(fields),
    });
    return { reached: true, status: response.status, body: await response.json().catch(() => ({})) };
  } catch {
    return { reached: false, status: 0, body: {} };
  }
}

function lemonError(error) {
  const text = String(error || '').toLowerCase();
  if (text.includes('activation limit')) return [409, '이 키는 이미 PC 2대에 등록되어 있습니다. 쓰지 않는 PC에서 먼저 등록을 풀어 주십시오.'];
  if (text.includes('expired') || text.includes('disabled')) return [403, '쓸 수 없는 키입니다(만료 또는 환불). 문의 메일로 알려 주십시오.'];
  return [404, '라이선스 키가 맞지 않습니다. 결제 확인 이메일의 키를 그대로 붙여 넣어 주십시오.'];
}

// -- 프로그램: 등록·해제 ----------------------------------------------------------

const used = (env, key) => env.DB.prepare('SELECT COUNT(*) AS n FROM activations WHERE key = ?').bind(key).first().then(r => r.n);
const newInstance = () => 'ins_' + hex(crypto.getRandomValues(new Uint8Array(10)));

async function activate(env, body) {
  const key = tidyKey(body.key);
  const name = String(body.name || 'PC').slice(0, 100);
  const want = body.product || 'jocbo';
  if (!key) return fail(400, '라이선스 키를 넣어 주십시오.');
  const row = await env.DB.prepare('SELECT * FROM licenses WHERE key = ?').bind(key).first();

  // Lemon Squeezy 키: 그쪽이 살아 있는 동안은 그쪽이 PC 수를 세고, 여기에도 적어 둡니다.
  if (LS_KEY.test(key) && (!row || row.source === 'lemonsqueezy')) {
    const ls = await lemon('activate', { license_key: key, instance_name: name });
    if (ls.reached && ls.status < 500) {
      if (!ls.body.activated) {
        const [status, detail] = lemonError(ls.body.error);
        return fail(status, detail);
      }
      const products = parse(env.LS_PRODUCTS || '{}', {});
      const product = products[String(ls.body.meta?.product_id)];
      const instance = ls.body.instance?.id || newInstance();
      if (product !== want) {
        await lemon('deactivate', { license_key: key, instance_id: instance });
        return fail(400, `${PRODUCTS[want]?.name || '이 프로그램'} 키가 아닙니다.`);
      }
      const usage = Number(ls.body.license_key?.activation_usage) || 1;
      const now = Date.now();
      const writes = [env.DB.prepare("INSERT OR IGNORE INTO licenses (key, product, email, name, txn, seq, source, status, max_pcs, created, mailed) "
        + "VALUES (?, ?, ?, ?, ?, 1, 'lemonsqueezy', 'active', ?, ?, 1)")
        .bind(key, product, tidyEmail(ls.body.meta?.customer_email), String(ls.body.meta?.customer_name || ''),
          'ls:' + (ls.body.meta?.order_id || key), Number(ls.body.license_key?.activation_limit) || 2, now),
        env.DB.prepare('INSERT OR IGNORE INTO activations (key, instance, name, created) VALUES (?, ?, ?, ?)').bind(key, instance, name, now)];
      // 이 서버를 거치지 않고 Lemon Squeezy 에 직접 등록된 PC 는 자리표로 셉니다.
      for (let i = 1; i < usage; i++) writes.push(env.DB.prepare('INSERT OR IGNORE INTO activations (key, instance, name, created) VALUES (?, ?, ?, ?)').bind(key, `legacy-${i}`, '이전 등록', now));
      await env.DB.batch(writes);
      return json({ activated: true, instance, product });
    }
    if (!row) return fail(404, '라이선스 키가 맞지 않습니다. 결제 확인 이메일의 키를 그대로 붙여 넣어 주십시오.');
    // Lemon Squeezy 가 닫힌 뒤: 이어받아 둔 키는 여기서 셉니다(아래로 이어짐).
  }

  if (!row) return fail(404, '라이선스 키가 맞지 않습니다. 결제 확인 이메일의 키를 그대로 붙여 넣어 주십시오.');
  if (row.status !== 'active') return fail(403, '쓸 수 없는 키입니다(환불됨). 문의 메일로 알려 주십시오.');
  if (row.product !== want) return fail(400, `${PRODUCTS[want]?.name || '이 프로그램'} 키가 아닙니다.`);
  if ((await used(env, key)) >= row.max_pcs) return fail(409, `이 키는 이미 PC ${row.max_pcs}대에 등록되어 있습니다. 쓰지 않는 PC에서 먼저 등록을 풀어 주십시오.`);
  const instance = newInstance();
  await env.DB.prepare('INSERT INTO activations (key, instance, name, created) VALUES (?, ?, ?, ?)').bind(key, instance, name, Date.now()).run();
  return json({ activated: true, instance, product: row.product });
}

async function deactivate(env, body) {
  const key = tidyKey(body.key);
  const instance = String(body.instance || '');
  const row = await env.DB.prepare('SELECT * FROM licenses WHERE key = ?').bind(key).first();
  if (LS_KEY.test(key) && (!row || row.source === 'lemonsqueezy') && instance) {
    const ls = await lemon('deactivate', { license_key: key, instance_id: instance });
    if (!row) {
      if (ls.reached && ls.body.deactivated) return json({ deactivated: true });
      return fail(404, '등록을 풀지 못했습니다. 문의 메일로 알려 주십시오.');
    }
  }
  if (!row) return fail(404, '라이선스 키가 맞지 않습니다.');
  const gone = await env.DB.prepare('DELETE FROM activations WHERE key = ? AND instance = ?').bind(key, instance).run();
  if (!gone.meta?.changes) {
    // 이 서버가 모르는 자리(이전에 Lemon Squeezy 에서 직접 등록한 PC)면 자리표 하나를 비웁니다.
    await env.DB.prepare("DELETE FROM activations WHERE rowid = (SELECT rowid FROM activations WHERE key = ? AND instance LIKE 'legacy-%' LIMIT 1)").bind(key).run();
  }
  return json({ deactivated: true });
}

// -- 홈페이지: 구매 완료·다시 받기 -------------------------------------------------

const masked = email => email.replace(/^(.)(.*)(@.*)$/, (_, a, b, c) => a + '*'.repeat(Math.min(b.length, 6)) + c);

async function order(env, txn) {
  if (!TXN.test(txn || '')) return fail(400, '주문 번호가 맞지 않습니다.');
  let result;
  try {
    result = await issue(env, txn);
  } catch {
    return json({ pending: true }, 202);
  }
  if (result.state === 'pending' || !result.rows.length) return json({ pending: true }, 202);
  await mailKeys(env, result.rows);
  const rows = await rowsOf(env, txn);
  return json({
    email: masked(rows[0].email || ''),
    mailed: rows.every(r => r.mailed),
    keys: rows.map(r => ({ key: r.key, product: r.product, name: PRODUCTS[r.product]?.name || r.product, status: r.status })),
  });
}

async function resend(env, body) {
  const email = tidyEmail(body.email);
  const done = json({ ok: true, detail: '구매하신 메일 주소라면 키를 다시 보냈습니다. 몇 분 안에 오지 않으면 스팸함을 확인해 주십시오.' });
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return fail(400, '메일 주소를 확인해 주십시오.');
  const last = await env.DB.prepare('SELECT last FROM mail_log WHERE email = ?').bind(email).first();
  if (last && Date.now() - last.last < RESEND_GAP) return done;
  await env.DB.prepare('INSERT INTO mail_log (email, last) VALUES (?, ?) ON CONFLICT(email) DO UPDATE SET last = excluded.last').bind(email, Date.now()).run();
  const { results } = await env.DB.prepare("SELECT * FROM licenses WHERE email = ? AND status = 'active' ORDER BY created").bind(email).all();
  if (results.length) await sendMail(env, keyMail(env, results));
  return done;
}

/** /api/license/* */
export async function licenseApi(request, env, parts) {
  const method = request.method;
  const body = method === 'POST' ? await request.json().catch(() => ({})) : {};
  if (method === 'GET' && parts[1] === 'order') return order(env, new URL(request.url).searchParams.get('txn'));
  if (method === 'POST' && parts[1] === 'resend') return resend(env, body);
  if (method === 'POST' && parts[1] === 'activate') return activate(env, body);
  if (method === 'POST' && parts[1] === 'deactivate') return deactivate(env, body);
  return fail(404, '없는 요청입니다.');
}
