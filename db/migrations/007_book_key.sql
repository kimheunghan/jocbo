-- A random key written into every exported file, so the file can be brought back into the same book.
ALTER TABLE family_books ADD COLUMN IF NOT EXISTS book_key VARCHAR(32) NOT NULL DEFAULT '';
