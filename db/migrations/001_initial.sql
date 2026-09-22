-- PostgreSQL initial schema. Apply once to an empty database.

CREATE TABLE users (
	id SERIAL NOT NULL,
	email VARCHAR(255) NOT NULL,
	password_hash VARCHAR(255) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (email)
);

CREATE TABLE family_books (
	id SERIAL NOT NULL,
	user_id INTEGER NOT NULL,
	title VARCHAR(200) NOT NULL,
	clan_name VARCHAR(200) NOT NULL,
	bon_gwan VARCHAR(200) DEFAULT '' NOT NULL,
	branch_name VARCHAR(200) DEFAULT '' NOT NULL,
	volume VARCHAR(50) DEFAULT '' NOT NULL,
	description TEXT NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE sessions (
	token_hash VARCHAR(64) NOT NULL,
	user_id INTEGER NOT NULL,
	expires INTEGER NOT NULL,
	PRIMARY KEY (token_hash),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE persons (
	id SERIAL NOT NULL,
	book_id INTEGER NOT NULL,
	korean_name VARCHAR(100) NOT NULL,
	hanja_name VARCHAR(100) NOT NULL,
	generation INTEGER NOT NULL,
	gender VARCHAR(10) NOT NULL,
	birth_date VARCHAR(10) NOT NULL,
	death_date VARCHAR(10) NOT NULL,
	note TEXT NOT NULL,
	PRIMARY KEY (id),
	CHECK (generation > 0),
	FOREIGN KEY(book_id) REFERENCES family_books (id) ON DELETE CASCADE
);

CREATE TABLE files (
	id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	name VARCHAR(255) NOT NULL,
	storage_key VARCHAR(80) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(person_id) REFERENCES persons (id) ON DELETE CASCADE,
	UNIQUE (storage_key)
);

CREATE TABLE relations (
	id SERIAL NOT NULL,
	source_id INTEGER NOT NULL,
	target_id INTEGER NOT NULL,
	kind VARCHAR(20) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (source_id, target_id, kind),
	CHECK (source_id <> target_id),
	CHECK (kind IN ('parent', 'spouse')),
	FOREIGN KEY(source_id) REFERENCES persons (id) ON DELETE CASCADE,
	FOREIGN KEY(target_id) REFERENCES persons (id) ON DELETE CASCADE
);

CREATE INDEX ix_persons_book_id ON persons (book_id);
