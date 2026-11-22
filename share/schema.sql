-- 우리의 족보 - 웹 공유 사이트(Cloudflare D1)의 표.
-- 한 번만 실행합니다: npx wrangler d1 execute jocbo-share --remote --file schema.sql

-- 공유 하나에 하나. token 은 올리기 열쇠의 SHA-256 입니다.
CREATE TABLE IF NOT EXISTS shares (
  id TEXT PRIMARY KEY,
  token TEXT NOT NULL,
  created INTEGER NOT NULL
);

-- 공유한 족보의 사본(JSON). PC 프로그램이 고칠 때마다 덮어씁니다.
CREATE TABLE IF NOT EXISTS books (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL
);

-- 인물 사진. kind 는 files(큰 사진) 또는 thumbs(카드용 작은 사진).
CREATE TABLE IF NOT EXISTS files (
  id TEXT NOT NULL,
  fid INTEGER NOT NULL,
  kind TEXT NOT NULL,
  type TEXT NOT NULL,
  data BLOB NOT NULL,
  PRIMARY KEY (id, fid, kind)
);

-- 라이선스(lib/license.js). 결제 하나(txn)의 상품마다 수량만큼 키를 만듭니다.
-- source: paddle | lemonsqueezy(이어받은 키) | manual. status: active | refunded.
-- mailed: 키 메일을 보낸 시각(ms), 아직이면 0.
CREATE TABLE IF NOT EXISTS licenses (
  key TEXT PRIMARY KEY,
  product TEXT NOT NULL,
  email TEXT NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  txn TEXT NOT NULL,
  seq INTEGER NOT NULL DEFAULT 1,
  source TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  max_pcs INTEGER NOT NULL DEFAULT 2,
  created INTEGER NOT NULL,
  mailed INTEGER NOT NULL DEFAULT 0,
  UNIQUE (txn, product, seq)
);
CREATE INDEX IF NOT EXISTS licenses_email ON licenses (email);

-- 키를 등록한 PC. instance 가 legacy-N 이면 Lemon Squeezy 에 직접 등록되어 있던 PC 의 자리표입니다.
CREATE TABLE IF NOT EXISTS activations (
  key TEXT NOT NULL,
  instance TEXT NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  created INTEGER NOT NULL,
  PRIMARY KEY (key, instance)
);

-- 키 다시 받기를 같은 메일로 너무 자주 하지 않게 합니다.
CREATE TABLE IF NOT EXISTS mail_log (
  email TEXT PRIMARY KEY,
  last INTEGER NOT NULL
);
