-- Fictional demo only. Optional: never load this shared account in production.
-- Login: demo@example.test / DemoFamily123!
-- Negative IDs keep demo rows separate from generated positive IDs.
INSERT INTO users (id, email, password_hash) VALUES
(-1, 'demo@example.test', '0123456789abcdef0123456789abcdef:93cfafd8c504fc83830b907059229aa08a3702a6f231ee1ad28e675e7d4039ee33ac3cb91e9e2b1329178d3e0c3c275e386c35fd30f57e1cadd2e8cd6e633182') ON CONFLICT DO NOTHING;
INSERT INTO family_books (id, user_id, title, clan_name, description) VALUES
(-1, -1, '가상 가족의 기록', '예시 김씨', '실존 인물과 무관한 샘플 데이터입니다.') ON CONFLICT DO NOTHING;
INSERT INTO persons (id, book_id, korean_name, hanja_name, generation, gender, birth_date, death_date, note) VALUES
(-1, -1, '김예시', '金例示', 1, '남', '1940-01-01', '', '가상 인물. 샘플 가족의 첫 세대.'),
(-2, -1, '이샘플', '李樣本', 1, '여', '1942-02-02', '', '가상 인물. 김예시의 배우자.'),
(-3, -1, '김가상', '金假想', 2, '남', '1970-03-03', '', '가상 인물. 가족의 이야기를 기록합니다.'),
(-4, -1, '김미래', '金未來', 3, '미상', '2000-04-04', '', '가상 인물. 다음 세대의 기록입니다.') ON CONFLICT DO NOTHING;
INSERT INTO relations (id, source_id, target_id, kind) VALUES
(-1, -2, -1, 'spouse'),
(-2, -1, -3, 'parent'),
(-3, -2, -3, 'parent'),
(-4, -3, -4, 'parent') ON CONFLICT DO NOTHING;
