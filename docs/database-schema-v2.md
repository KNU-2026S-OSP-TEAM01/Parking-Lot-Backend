# OpenPark 데이터베이스 스키마 설계 문서 v2

> 작성일: 2026-05-03  
> 라이선스: MIT

---

## 개요

### 서버 구성

| 서버 | 설명 |
|---|---|
| **Parking Lot Server** | 번호판 수신, 입출차 판단, 주차장 관리. Private/Public 배포 모두 동일한 DB 스키마 사용. 차이는 서버 코드 설정으로 구분 |
| **Hub Server** | Public Parking Lot Server와 공용 OpenAPI 데이터를 통합해 외부 사용자에게 제공 |

> Private Parking Lot Server는 Hub Server와 무관하게 단독으로 동작한다.

### 입출차 판단 로직

클라이언트는 번호판 문자열만 전송한다. 서버가 `vehicles` 테이블을 조회해 입출차를 판단한다.

```
번호판 수신
    │
    ▼
vehicles 테이블에 해당 번호판 존재?
    │
  없음 → 입차: vehicles INSERT, available_spaces -= 1, 로그 기록
  있음 → 출차: vehicles DELETE, available_spaces += 1, 요금 계산, 로그 기록
```

---

## Parking Lot Server DB

### 테이블 관계도

```
users ──────────► parking_lots ◄──── vehicles (현재 주차 중인 차량)
                       ▲
                       └─────────── entry_exit_logs (전체 입출차 이력)
```

---

### `parking_lots`

주차장 기본 정보와 잔여 공간 카운터를 관리한다.

```sql
CREATE TABLE parking_lots (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name              VARCHAR(100) NOT NULL,
    address           VARCHAR(255),
    total_spaces      INT         NOT NULL CHECK (total_spaces > 0),
    available_spaces  INT         NOT NULL CHECK (available_spaces >= 0),
    fee_per_hour      INT         NOT NULL DEFAULT 0,  -- 시간당 요금 (원). 무료 주차장은 0
    api_key           VARCHAR(64) UNIQUE NOT NULL,     -- 클라이언트 인증키
    is_active         BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT available_lte_total CHECK (available_spaces <= total_spaces)
);
```

| 열 | 설명 |
|---|---|
| `fee_per_hour` | 요금 계산 기준. 출차 시 `(주차 시간 / 60분) * fee_per_hour`로 계산 |
| `api_key` | 클라이언트 프로그램이 이 주차장 서버에 연결할 때 사용하는 인증키 |

---

### `users`

주차장 관리자 계정.

```sql
CREATE TABLE users (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(50) UNIQUE NOT NULL,
    email           VARCHAR(100) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,              -- bcrypt 해시, 원본 저장 안 함
    role            VARCHAR(20) NOT NULL DEFAULT 'admin'
                        CHECK (role IN ('superadmin', 'admin')),
    parking_lot_id  UUID REFERENCES parking_lots(id) ON DELETE SET NULL, -- superadmin은 NULL
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

### `vehicles`

**현재 주차 중인 차량** 목록. 입차 시 행이 추가되고, 출차 시 행이 삭제된다. 이 테이블의 존재 여부가 입출차 판단의 기준이 된다.

```sql
CREATE TABLE vehicles (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    parking_lot_id  UUID        NOT NULL REFERENCES parking_lots(id),
    plate_hash      VARCHAR(64) NOT NULL,  -- HMAC-SHA256. 동일 번호판 조회에 사용. 인덱싱
    plate_enc       BYTEA       NOT NULL,  -- AES-256 암호화. 관리자 UI 표시용
    entered_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (parking_lot_id, plate_hash)    -- 같은 주차장에 동일 차량 중복 입차 방지
);

CREATE INDEX idx_vehicles_lookup ON vehicles (parking_lot_id, plate_hash);
```

| 열 | 설명 |
|---|---|
| `plate_hash` | 번호판을 HMAC-SHA256으로 해시한 값. 원본 복원 불가. 조회·비교에 사용 |
| `plate_enc` | 번호판을 AES-256으로 암호화한 값. 관리자 화면에서 복호화해 표시 |
| `entered_at` | 요금 계산 기준 시각 |

> **왜 hash와 enc를 둘 다 쓰나?**  
> hash는 빠른 조회를 위해, enc는 관리자가 실제 번호판을 확인할 수 있도록 하기 위해 둘 다 필요하다.  
> hash만 쓰면 원본 복원이 불가능해 관리자 UI에서 번호판을 표시할 수 없다.

---

### `entry_exit_logs`

모든 입출차 이벤트의 **불변 이력**. 한 번 기록된 행은 수정·삭제하지 않는다.

```sql
CREATE TABLE entry_exit_logs (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    parking_lot_id      UUID        NOT NULL REFERENCES parking_lots(id),
    plate_hash          VARCHAR(64) NOT NULL,  -- 번호판 HMAC-SHA256
    plate_enc           BYTEA       NOT NULL,  -- 번호판 AES-256 암호화
    event_type          VARCHAR(5)  NOT NULL CHECK (event_type IN ('entry', 'exit')),
    fee                 INT,                   -- 출차 시 계산된 요금 (원). 입차 시 NULL
    client_timestamp    TIMESTAMPTZ NOT NULL,  -- 클라이언트 인식 시각
    server_received_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_logs_lot_time ON entry_exit_logs (parking_lot_id, client_timestamp DESC);
```

| 열 | 설명 |
|---|---|
| `event_type` | 서버가 `vehicles` 테이블 조회 후 결정. 클라이언트가 판단하지 않음 |
| `fee` | 출차 이벤트에만 기록. 입차는 NULL |
| `client_timestamp` | 실제 인식 시각. 네트워크 지연 시 `server_received_at`과 차이가 생길 수 있음 |

---

## Hub Server DB

Public Parking Lot Server와 공용 OpenAPI 주차장을 통합 관리한다.  
번호판 데이터는 일절 저장하지 않는다.

### `lots`

등록된 모든 주차장의 메타데이터와 라우팅 정보.

```sql
CREATE TABLE lots (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name             VARCHAR(100) NOT NULL,
    address          VARCHAR(255),
    latitude         DECIMAL(10, 8),   -- 지도 API 연동(3차 목표)을 위해 미리 확보
    longitude        DECIMAL(11, 8),
    phone            VARCHAR(20),
    operating_hours  VARCHAR(255),
    fee_info         TEXT,
    lot_type         VARCHAR(20) NOT NULL
                        CHECK (lot_type IN ('parking_lot_server', 'openapi')),

    total_spaces     INT,
    available_spaces INT,              -- polling 또는 webhook으로 갱신되는 캐시 값
    last_synced_at   TIMESTAMPTZ,      -- 마지막 동기화 시각. 오래된 데이터 여부 판단용

    is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- lot_type = 'parking_lot_server' 전용
    pl_server_url    VARCHAR(255),     -- Public Parking Lot Server API 엔드포인트
    pl_lot_id        UUID,             -- 해당 서버 내 parking_lots.id
    pl_api_key       VARCHAR(64),      -- Hub → Parking Lot Server 인증키

    -- lot_type = 'openapi' 전용
    openapi_source   VARCHAR(50),      -- 공공 OpenAPI 제공처 식별자 (예: 'daegu_v1')
    openapi_lot_id   VARCHAR(50),      -- 해당 OpenAPI 내 주차장 ID

    CONSTRAINT parking_lot_server_requires_url CHECK (
        lot_type != 'parking_lot_server'
        OR (pl_server_url IS NOT NULL AND pl_lot_id IS NOT NULL)
    ),
    CONSTRAINT openapi_requires_id CHECK (
        lot_type != 'openapi' OR openapi_lot_id IS NOT NULL
    )
);

CREATE INDEX idx_lots_type ON lots (lot_type, is_active);
```

| `lot_type` 값 | 의미 | 라우팅 대상 |
|---|---|---|
| `parking_lot_server` | Public 모드로 배포된 Parking Lot Server | `pl_server_url`의 Public API |
| `openapi` | 대구광역시 등 공공 OpenAPI 주차장 | `openapi_source`에 맞는 외부 API |

---

## 전체 DDL

### Parking Lot Server

```sql
CREATE TABLE parking_lots (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name              VARCHAR(100) NOT NULL,
    address           VARCHAR(255),
    total_spaces      INT         NOT NULL CHECK (total_spaces > 0),
    available_spaces  INT         NOT NULL CHECK (available_spaces >= 0),
    fee_per_hour      INT         NOT NULL DEFAULT 0,
    api_key           VARCHAR(64) UNIQUE NOT NULL,
    is_active         BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT available_lte_total CHECK (available_spaces <= total_spaces)
);

CREATE TABLE users (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(50) UNIQUE NOT NULL,
    email           VARCHAR(100) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'admin'
                        CHECK (role IN ('superadmin', 'admin')),
    parking_lot_id  UUID REFERENCES parking_lots(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE vehicles (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    parking_lot_id  UUID        NOT NULL REFERENCES parking_lots(id),
    plate_hash      VARCHAR(64) NOT NULL,
    plate_enc       BYTEA       NOT NULL,
    entered_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (parking_lot_id, plate_hash)
);

CREATE INDEX idx_vehicles_lookup ON vehicles (parking_lot_id, plate_hash);

CREATE TABLE entry_exit_logs (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    parking_lot_id      UUID        NOT NULL REFERENCES parking_lots(id),
    plate_hash          VARCHAR(64) NOT NULL,
    plate_enc           BYTEA       NOT NULL,
    event_type          VARCHAR(5)  NOT NULL CHECK (event_type IN ('entry', 'exit')),
    fee                 INT,
    client_timestamp    TIMESTAMPTZ NOT NULL,
    server_received_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_logs_lot_time ON entry_exit_logs (parking_lot_id, client_timestamp DESC);
```

### Hub Server

```sql
CREATE TABLE lots (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name             VARCHAR(100) NOT NULL,
    address          VARCHAR(255),
    latitude         DECIMAL(10, 8),
    longitude        DECIMAL(11, 8),
    phone            VARCHAR(20),
    operating_hours  VARCHAR(255),
    fee_info         TEXT,
    lot_type         VARCHAR(20) NOT NULL
                         CHECK (lot_type IN ('parking_lot_server', 'openapi')),
    total_spaces     INT,
    available_spaces INT,
    last_synced_at   TIMESTAMPTZ,
    is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pl_server_url    VARCHAR(255),
    pl_lot_id        UUID,
    pl_api_key       VARCHAR(64),
    openapi_source   VARCHAR(50),
    openapi_lot_id   VARCHAR(50),
    CONSTRAINT parking_lot_server_requires_url CHECK (
        lot_type != 'parking_lot_server'
        OR (pl_server_url IS NOT NULL AND pl_lot_id IS NOT NULL)
    ),
    CONSTRAINT openapi_requires_id CHECK (
        lot_type != 'openapi' OR openapi_lot_id IS NOT NULL
    )
);

CREATE INDEX idx_lots_type ON lots (lot_type, is_active);
```
