-- 혼인 순서(본처 1, 후처 2 …, 0은 등록 순서를 따름)와 입양 여부(1이면 양자·양녀).
ALTER TABLE relations ADD COLUMN IF NOT EXISTS marriage_order INTEGER NOT NULL DEFAULT 0;
ALTER TABLE relations ADD COLUMN IF NOT EXISTS adopted INTEGER NOT NULL DEFAULT 0;
