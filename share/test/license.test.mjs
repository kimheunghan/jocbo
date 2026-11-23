// lib/license.js 시험: node --test share/test
// D1 은 Node 의 SQLite(schema.sql 그대로)로, Paddle·Lemon Squeezy·메일 창구는 가짜 fetch 로 대신합니다.
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { webhook, licenseApi, newKey, paddleSigned } from '../lib/license.js';

const schema = readFileSync(new URL('../schema.sql', import.meta.url), 'utf8');
const PRICE_JOCBO = 'pri_01m7ztfe2xx5kfn1p583cfzac9';
const PRICE_FIND = 'pri_findinside0000000000000000';
const TXN = 'txn_01h0000000000000000000000a';

/** D1 처럼 prepare().bind().first()/all()/run() 과 batch() 를 내놓는 SQLite. */
function d1() {
  const sql = new DatabaseSync(':memory:');
  sql.exec(schema);
  const prep = (text, args = []) => ({
    bind: (...a) => prep(text, a),
    first: async () => sql.prepare(text).get(...args) ?? null,
    all: async () => ({ results: sql.prepare(text).all(...args) }),
    run: async () => { const r = sql.prepare(text).run(...args); return { meta: { changes: r.changes } }; },
  });
  return { sql, prepare: text => prep(text), batch: async list => Promise.all(list.map(s => s.run())) };
}

let env, mails, lemon, paddleTxn;
const SECRET = 'whsec_test';

beforeEach(() => {
  mails = [];
  paddleTxn = { id: TXN, status: 'completed', customer_id: 'ctm_1', items: [{ price: { id: PRICE_JOCBO }, quantity: 1 }] };
  lemon = { up: true, keys: { 'A1B2C3D4-1111-4222-8333-444455556666': { product: 1420186, used: ['ls-inst-1'], limit: 2 } } };
  env = {
    DB: d1(), PADDLE_ENV: 'sandbox', PADDLE_API_KEY: 'k', PADDLE_WEBHOOK_SECRET: SECRET,
    PADDLE_PRICES: JSON.stringify({ [PRICE_JOCBO]: 'jocbo', [PRICE_FIND]: 'findinside' }),
    LS_PRODUCTS: JSON.stringify({ 1420186: 'jocbo', 1420193: 'findinside' }),
    MAIL_URL: 'https://mail.test/send', MAIL_SECRET: 'm', SITE_URL: 'https://jocbo.pages.dev',
  };
  globalThis.fetch = async (url, init = {}) => {
    const reply = (body, status = 200) => new Response(JSON.stringify(body), { status });
    if (url.startsWith('https://sandbox-api.paddle.com/transactions/')) {
      return url.endsWith(paddleTxn.id) ? reply({ data: paddleTxn }) : reply({ error: { code: 'not_found' } }, 404);
    }
    if (url === 'https://sandbox-api.paddle.com/customers/ctm_1') return reply({ data: { email: 'Buyer@Example.com', name: '홍길동' } });
    if (url === env.MAIL_URL) {
      const body = JSON.parse(init.body);
      assert.equal(body.secret, 'm');
      mails.push(body);
      return reply({ ok: true });
    }
    if (url.startsWith('https://api.lemonsqueezy.com/v1/licenses/')) {
      if (!lemon.up) throw new TypeError('fetch failed');
      const f = Object.fromEntries(new URLSearchParams(init.body));
      const k = lemon.keys[f.license_key];
      if (!k) return reply({ activated: false, error: 'license_key not found.' }, 404);
      if (url.endsWith('/activate')) {
        if (k.used.length >= k.limit) return reply({ activated: false, error: 'This license key has reached the activation limit.' }, 400);
        k.used.push(`ls-inst-${k.used.length + 1}`);
        return reply({ activated: true, instance: { id: k.used.at(-1) }, license_key: { activation_usage: k.used.length, activation_limit: k.limit },
          meta: { product_id: k.product, order_id: 4800001, customer_email: 'ls-buyer@example.com', customer_name: 'test buyer' } });
      }
      k.used = k.used.filter(i => i !== f.instance_id);
      return reply({ deactivated: true });
    }
    throw new Error('unexpected fetch ' + url);
  };
});

async function signed(body, ts = Math.floor(Date.now() / 1000)) {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(SECRET), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const mac = [...new Uint8Array(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${ts}:${body}`)))].map(b => b.toString(16).padStart(2, '0')).join('');
  return `ts=${ts};h1=${mac}`;
}
const hook = async (event, signature) => {
  const body = JSON.stringify(event);
  return webhook(new Request('https://x/api/paddle/webhook', { method: 'POST', body, headers: { 'paddle-signature': signature ?? await signed(body) } }), env);
};
const call = (path, body) => licenseApi(new Request('https://x/api/' + path, body ? { method: 'POST', body: JSON.stringify(body) } : {}), env, path.split('?')[0].split('/'));
const read = async response => ({ status: response.status, ...(await response.json()) });

test('키 모양: 상품 머리글 + 4자리 네 묶음, 헷갈리는 글자 없음', () => {
  const key = newKey('jocbo');
  assert.match(key, /^JOCBO-[0-9A-HJKMNP-TV-Z]{4}(-[0-9A-HJKMNP-TV-Z]{4}){3}$/);
  assert.match(newKey('findinside'), /^FIND-/);
});

test('결제 완료 알림 → 키 하나 발급, 메일 한 통', async () => {
  const r = await hook({ event_type: 'transaction.completed', data: { id: TXN } });
  assert.equal(r.status, 200);
  const rows = env.DB.sql.prepare('SELECT * FROM licenses').all();
  assert.equal(rows.length, 1);
  assert.equal(rows[0].email, 'buyer@example.com');
  assert.equal(rows[0].product, 'jocbo');
  assert.ok(rows[0].mailed > 0);
  assert.equal(mails.length, 1);
  assert.equal(mails[0].to, 'buyer@example.com');
  assert.ok(mails[0].text.includes(rows[0].key));
  assert.ok(mails[0].text.includes('홍길동 님'));
  assert.ok(mails[0].text.includes('https://jocbo.pages.dev/license'));
});

test('같은 알림이 두 번 와도 키는 하나, 메일도 한 통', async () => {
  await hook({ event_type: 'transaction.completed', data: { id: TXN } });
  await hook({ event_type: 'transaction.completed', data: { id: TXN } });
  assert.equal(env.DB.sql.prepare('SELECT COUNT(*) n FROM licenses').get().n, 1);
  assert.equal(mails.length, 1);
});

test('결제 알림과 구매 완료 화면 조회가 동시에 와도 메일은 한 통, 보낸 이는 흥한소프트', async () => {
  await Promise.all([
    hook({ event_type: 'transaction.completed', data: { id: TXN } }),
    call(`license/order?txn=${TXN}`),
    call(`license/order?txn=${TXN}`),
  ]);
  assert.equal(env.DB.sql.prepare('SELECT COUNT(*) n FROM licenses').get().n, 1);
  assert.equal(mails.length, 1);
  assert.equal(mails[0].name, '흥한소프트 (우리의 족보)');
  assert.ok(mails[0].text.includes('흥한소프트(K Software)'));
  assert.ok(mails[0].text.includes(`주문 번호: ${TXN}`));
});

test('서명이 틀리거나 오래된 알림은 거절', async () => {
  assert.equal((await hook({ event_type: 'transaction.completed', data: { id: TXN } }, 'ts=1;h1=00')).status, 401);
  const body = '{}';
  assert.equal(await paddleSigned(env, await signed(body, Math.floor(Date.now() / 1000) - 3600), body), false);
  assert.equal(env.DB.sql.prepare('SELECT COUNT(*) n FROM licenses').get().n, 0);
});

test('수량 2, 두 상품을 함께 사면 키 3개를 한 메일로', async () => {
  paddleTxn.items = [{ price: { id: PRICE_JOCBO }, quantity: 2 }, { price: { id: PRICE_FIND }, quantity: 1 }];
  await hook({ event_type: 'transaction.completed', data: { id: TXN } });
  const rows = env.DB.sql.prepare('SELECT product FROM licenses ORDER BY product').all().map(r => r.product);
  assert.deepEqual(rows, ['findinside', 'jocbo', 'jocbo']);
  assert.equal(mails.length, 1);
  assert.equal((mails[0].text.match(/(JOCBO|FIND)-/g) || []).length, 3);
});

test('모르는 가격만 있는 결제에는 키를 만들지 않음', async () => {
  paddleTxn.items = [{ price: { id: 'pri_other' }, quantity: 1 }];
  await hook({ event_type: 'transaction.completed', data: { id: TXN } });
  assert.equal(env.DB.sql.prepare('SELECT COUNT(*) n FROM licenses').get().n, 0);
  assert.equal(mails.length, 0);
});

test('구매 완료 화면: 알림보다 먼저 물어도 발급해 보여 주고, 아직 결제 전이면 기다림', async () => {
  paddleTxn.status = 'ready';
  assert.equal((await call(`license/order?txn=${TXN}`)).status, 202);
  paddleTxn.status = 'completed';
  const r = await read(await call(`license/order?txn=${TXN}`));
  assert.equal(r.status, 200);
  assert.equal(r.keys.length, 1);
  assert.equal(r.email, 'b****@example.com');
  assert.equal(r.mailed, true);
  await hook({ event_type: 'transaction.completed', data: { id: TXN } });
  assert.equal(mails.length, 1);
  assert.equal((await call('license/order?txn=nope')).status, 400);
});

test('메일 창구가 없으면 키는 만들고 나중에 보냄', async () => {
  const url = env.MAIL_URL; delete env.MAIL_URL;
  await hook({ event_type: 'transaction.completed', data: { id: TXN } });
  assert.equal(env.DB.sql.prepare('SELECT mailed FROM licenses').get().mailed, 0);
  env.MAIL_URL = url;
  const r = await read(await call(`license/order?txn=${TXN}`));
  assert.equal(r.mailed, true);
  assert.equal(mails.length, 1);
});

test('PC 2대까지 등록, 3대째 거절, 해제하면 다시 자리', async () => {
  await hook({ event_type: 'transaction.completed', data: { id: TXN } });
  const key = env.DB.sql.prepare('SELECT key FROM licenses').get().key;
  const a = await read(await call('license/activate', { key: key.toLowerCase(), name: 'PC-1', product: 'jocbo' }));
  assert.equal(a.activated, true);
  assert.equal(a.product, 'jocbo');
  assert.equal((await call('license/activate', { key, name: 'PC-2', product: 'jocbo' })).status, 200);
  const third = await read(await call('license/activate', { key, name: 'PC-3', product: 'jocbo' }));
  assert.equal(third.status, 409);
  assert.match(third.detail, /PC 2대/);
  assert.equal((await read(await call('license/deactivate', { key, instance: a.instance }))).deactivated, true);
  assert.equal((await call('license/activate', { key, name: 'PC-3', product: 'jocbo' })).status, 200);
});

test('다른 상품 키, 없는 키, 환불된 키는 거절', async () => {
  await hook({ event_type: 'transaction.completed', data: { id: TXN } });
  const key = env.DB.sql.prepare('SELECT key FROM licenses').get().key;
  assert.equal((await call('license/activate', { key, product: 'findinside' })).status, 400);
  assert.equal((await call('license/activate', { key: 'JOCBO-AAAA-BBBB-CCCC-DDDD', product: 'jocbo' })).status, 404);
  await hook({ event_type: 'adjustment.created', data: { action: 'refund', status: 'pending_approval', transaction_id: TXN } });
  assert.equal((await call('license/activate', { key, product: 'jocbo' })).status, 200);
  await hook({ event_type: 'adjustment.updated', data: { action: 'refund', status: 'approved', transaction_id: TXN } });
  const r = await read(await call('license/activate', { key, product: 'jocbo' }));
  assert.equal(r.status, 403);
  assert.match(r.detail, /환불/);
});

test('Lemon Squeezy 키: 처음 들어오면 이어받고, 이미 쓰던 PC 1대도 셈', async () => {
  const key = 'a1b2c3d4-1111-4222-8333-444455556666';
  const a = await read(await call('license/activate', { key, name: 'PC-2', product: 'jocbo' }));
  assert.equal(a.activated, true);
  const row = env.DB.sql.prepare('SELECT * FROM licenses').get();
  assert.equal(row.source, 'lemonsqueezy');
  assert.equal(row.email, 'ls-buyer@example.com');
  assert.equal(env.DB.sql.prepare('SELECT COUNT(*) n FROM activations').get().n, 2);
  // Lemon Squeezy 가 PC 수를 세는 동안: 3대째는 그쪽이 거절
  assert.equal((await call('license/activate', { key, product: 'jocbo' })).status, 409);
});

test('Lemon Squeezy 가 닫힌 뒤에도 이어받은 키는 여기서 셈, 옛 PC 해제도 됨', async () => {
  const key = 'A1B2C3D4-1111-4222-8333-444455556666';
  const first = await read(await call('license/activate', { key, name: 'PC-2', product: 'jocbo' }));
  lemon.up = false;
  assert.equal((await call('license/activate', { key, product: 'jocbo' })).status, 409);
  // 이 서버를 거치지 않고 등록했던 옛 PC(ls-inst-1)를 풀면 자리표 하나가 비워짐
  assert.equal((await read(await call('license/deactivate', { key, instance: 'ls-inst-1' }))).deactivated, true);
  assert.equal((await call('license/activate', { key, name: 'PC-3', product: 'jocbo' })).status, 200);
  assert.ok(first.instance);
});

test('Lemon Squeezy 가 닫힌 뒤 처음 보는 Lemon Squeezy 키는 거절', async () => {
  lemon.up = false;
  assert.equal((await call('license/activate', { key: 'A1B2C3D4-1111-4222-8333-444455556666', product: 'jocbo' })).status, 404);
});

test('FindInside 의 Lemon Squeezy 키를 우리의 족보에 넣으면 거절하고 자리를 돌려줌', async () => {
  lemon.keys['11111111-2222-3333-4444-555555555555'] = { product: 1420193, used: [], limit: 2 };
  assert.equal((await call('license/activate', { key: '11111111-2222-3333-4444-555555555555', product: 'jocbo' })).status, 400);
  assert.equal(lemon.keys['11111111-2222-3333-4444-555555555555'].used.length, 0);
});

test('키 다시 받기: 산 메일이면 보내고, 아니면 조용히, 5분 안에 또 누르면 보내지 않음', async () => {
  await hook({ event_type: 'transaction.completed', data: { id: TXN } });
  mails = [];
  const r = await read(await call('license/resend', { email: ' BUYER@example.com ' }));
  assert.equal(r.ok, true);
  assert.equal(mails.length, 1);
  await call('license/resend', { email: 'buyer@example.com' });
  assert.equal(mails.length, 1);
  assert.equal((await read(await call('license/resend', { email: 'nobody@example.com' }))).ok, true);
  assert.equal(mails.length, 1);
  assert.equal((await call('license/resend', { email: 'not-an-email' })).status, 400);
});
