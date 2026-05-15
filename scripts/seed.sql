-- 최초 관리자 계정 직접 주입 예시
-- password_hash는 bcrypt로 생성한 값을 사용한다.
-- 아래는 비밀번호 "changeme"에 해당하는 예시 해시값이다.
-- 운영 환경에서는 반드시 비밀번호를 변경해야 한다.

-- Python으로 해시 생성:
--   import bcrypt
--   bcrypt.hashpw(b"yourpassword", bcrypt.gensalt()).decode()

INSERT INTO users (id, username, email, password_hash, created_at)
VALUES (
    gen_random_uuid(),
    'admin',
    'admin@openpark.local',
    '$2b$12$examplehashexamplehashexamplehashexamplehashexamplehash',
    NOW()
);
