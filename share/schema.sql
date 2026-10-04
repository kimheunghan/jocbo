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
