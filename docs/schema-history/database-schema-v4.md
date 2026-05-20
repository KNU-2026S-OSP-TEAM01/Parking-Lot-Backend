# OpenPark 데이터베이스 스키마 변경 이력 v4

> 작성일: 2026-05-13  
> 기준 버전: `database-schema-v3.md`  
> 배경: FE 피드백 반영 — role 기반 권한 모델에서 소유권 기반 모델로 전환

---

## 변경 요약

| 테이블 | 변경 내용 |
|--------|----------|
| `users` | `role`, `parking_lot_id` 컬럼 제거 |
| `parking_lots` | `owner_user_id` FK 컬럼 추가 |
| `vehicles` | `parking_lot_id` FK에 `ON DELETE CASCADE` 추가 |
| `entry_exit_logs` | `parking_lot_id` FK에 `ON DELETE CASCADE` 추가 |

---

## 변경 상세

### 1. `users` — `role`, `parking_lot_id` 제거

**변경 전 (v3)**

```sql
CREATE TABLE users (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    username       VARCHAR(50) UNIQUE NOT NULL,
    email          VARCHAR(100) UNIQUE NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    role           VARCHAR(20) NOT NULL DEFAULT 'admin'
                       CHECK (role IN ('superadmin', 'admin')),
    parking_lot_id UUID REFERENCES parking_lots(id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**변경 후 (v4)**

```sql
CREATE TABLE users (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    username       VARCHAR(50) UNIQUE NOT NULL,
    email          VARCHAR(100) UNIQUE NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**변경 이유**

- `superadmin`/`admin` 역할 구분을 코드에서 제거. 최고 관리자는 DB에 직접 계정을 주입하는 방식으로 운영.
- 소유권 모델 전환(`lot.owner_user_id`)으로 `parking_lot_id` 역방향 참조가 불필요해짐.

---

### 2. `parking_lots` — `owner_user_id` 추가

**변경 전 (v3)**

```sql
-- owner 식별자 없음
CREATE TABLE parking_lots (
    id UUID PRIMARY KEY ...
    -- ...
);
```

**변경 후 (v4)**

```sql
CREATE TABLE parking_lots (
    id            UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id UUID NOT NULL REFERENCES users(id),
    -- 나머지 컬럼 동일
);
```

**변경 이유**

기존에는 `users.parking_lot_id`로 역방향 참조했으나, 소유자가 직접 주차장을 생성·관리하는 구조로 전환하면서 `parking_lots.owner_user_id`(정방향 참조)로 변경. `NOT NULL` 제약으로 반드시 소유자가 있어야 한다.

---

### 3. `vehicles` — `parking_lot_id` FK에 CASCADE 추가

**변경 전 (v3)**

```sql
parking_lot_id UUID NOT NULL REFERENCES parking_lots(id)
```

**변경 후 (v4)**

```sql
parking_lot_id UUID NOT NULL REFERENCES parking_lots(id) ON DELETE CASCADE
```

**변경 이유**

`DELETE /api/v1/lots/{lot_id}`가 hard delete로 변경되면서, 주차장 삭제 시 현재 주차 중인 차량 기록도 함께 삭제되어야 한다.

---

### 4. `entry_exit_logs` — `parking_lot_id` FK에 CASCADE 추가

**변경 전 (v3)**

```sql
parking_lot_id UUID NOT NULL REFERENCES parking_lots(id)
```

**변경 후 (v4)**

```sql
parking_lot_id UUID NOT NULL REFERENCES parking_lots(id) ON DELETE CASCADE
```

**변경 이유**

주차장 hard delete 시 해당 주차장의 입출차 이력도 함께 삭제.

---

## 현재 전체 스키마 (v4 기준)

```sql
CREATE TABLE users (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    username       VARCHAR(50) UNIQUE NOT NULL,
    email          VARCHAR(100) UNIQUE NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE parking_lots (
    id                     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id          UUID        NOT NULL REFERENCES users(id),
    name                   VARCHAR(100) NOT NULL,
    address                VARCHAR(255),
    total_spaces           INT         NOT NULL CHECK (total_spaces > 0),
    available_spaces       INT         NOT NULL CHECK (available_spaces >= 0),
    base_fee               INT         NOT NULL DEFAULT 0,
    base_duration_minutes  INT         NOT NULL DEFAULT 0,
    extra_fee_per_unit     INT         NOT NULL DEFAULT 0,
    extra_fee_unit_minutes INT         NOT NULL DEFAULT 10,
    daily_max_fee          INT,
    api_key                VARCHAR(64) UNIQUE NOT NULL,
    is_active              BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_available_lte_total CHECK (available_spaces <= total_spaces)
);

CREATE TABLE vehicles (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    parking_lot_id  UUID        NOT NULL REFERENCES parking_lots(id) ON DELETE CASCADE,
    plate_hash      VARCHAR(64) NOT NULL,
    plate_enc       BYTEA       NOT NULL,
    entered_at      TIMESTAMPTZ NOT NULL,
    UNIQUE (parking_lot_id, plate_hash)
);

CREATE INDEX idx_vehicles_lookup ON vehicles (parking_lot_id, plate_hash);

CREATE TABLE entry_exit_logs (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    parking_lot_id      UUID        NOT NULL REFERENCES parking_lots(id) ON DELETE CASCADE,
    plate_hash          VARCHAR(64) NOT NULL,
    plate_enc           BYTEA       NOT NULL,
    event_type          VARCHAR(5)  NOT NULL CHECK (event_type IN ('entry', 'exit', 'admin')),
    fee                 INT,
    client_timestamp    TIMESTAMPTZ NOT NULL,
    server_received_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_logs_lot_time ON entry_exit_logs (parking_lot_id, client_timestamp DESC);
```

---

## Alembic 마이그레이션

`alembic/versions/20260513_6361c625a6af_init_redesigned_schema.py`

v3까지의 모든 마이그레이션을 통합하여 새 스키마로 초기화했다.
