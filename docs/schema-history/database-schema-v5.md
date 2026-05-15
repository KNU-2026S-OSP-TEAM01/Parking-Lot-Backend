# OpenPark 데이터베이스 스키마 변경 이력 v5

> 작성일: 2026-05-15  
> 기준 버전: `database-schema-v4.md`  
> 배경: 팀 협의로 `is_active` 컬럼 제거 결정

---

## 변경 요약

| 테이블 | 변경 내용 |
|--------|----------|
| `parking_lots` | `is_active` 컬럼 제거 |

---

## 변경 상세

### `parking_lots` — `is_active` 제거

**변경 전 (v4)**

```sql
CREATE TABLE parking_lots (
    ...
    api_key    VARCHAR(64) UNIQUE NOT NULL,
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ...
);
```

**변경 후 (v5)**

```sql
CREATE TABLE parking_lots (
    ...
    api_key    VARCHAR(64) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ...
);
```

**변경 이유**

- v4에서 `LotPatch`에서 `is_active` 수정을 이미 막았고, `DELETE /api/v1/lots/{lot_id}`가 hard delete이므로 `is_active=false`로 전환할 수단이 없는 dead column 상태였다.
- soft delete 운영 정책을 채택하지 않기로 확정하여 컬럼 자체를 제거했다.

---

## 현재 전체 스키마 (v5 기준)

```sql
CREATE TABLE users (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    username       VARCHAR(50) UNIQUE NOT NULL,
    email          VARCHAR(100) UNIQUE NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE parking_lots (
    id                     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id          UUID         NOT NULL REFERENCES users(id),
    name                   VARCHAR(100) NOT NULL,
    address                VARCHAR(255),
    total_spaces           INT          NOT NULL CHECK (total_spaces > 0),
    available_spaces       INT          NOT NULL CHECK (available_spaces >= 0),
    base_fee               INT          NOT NULL DEFAULT 0,
    base_duration_minutes  INT          NOT NULL DEFAULT 0,
    extra_fee_per_unit     INT          NOT NULL DEFAULT 0,
    extra_fee_unit_minutes INT          NOT NULL DEFAULT 10,
    daily_max_fee          INT,
    api_key                VARCHAR(64)  UNIQUE NOT NULL,
    created_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
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

`alembic/versions/20260515_ca3ed5b9fa78_drop_is_active_from_parking_lots.py`

```python
def upgrade():
    op.drop_column('parking_lots', 'is_active')

def downgrade():
    op.add_column('parking_lots', sa.Column('is_active', sa.BOOLEAN(), nullable=False))
```
