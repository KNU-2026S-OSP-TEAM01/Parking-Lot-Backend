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
    id                     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                   VARCHAR(100) NOT NULL,
    address                VARCHAR(255),
    total_spaces           INT         NOT NULL CHECK (total_spaces > 0),
    available_spaces       INT         NOT NULL CHECK (available_spaces >= 0),
    base_fee               INT         NOT NULL DEFAULT 0,   -- 기본 요금 (원)
    base_duration_minutes  INT         NOT NULL DEFAULT 0,   -- 기본 요금 적용 시간 (분)
    extra_fee_per_unit     INT         NOT NULL DEFAULT 0,   -- 단위 시간당 추가 요금 (원)
    extra_fee_unit_minutes INT         NOT NULL DEFAULT 10,  -- 추가 요금 단위 시간 (분)
    daily_max_fee          INT,                              -- 일일 최대 요금 (원). NULL이면 상한 없음
    api_key                VARCHAR(64) UNIQUE NOT NULL,      -- 클라이언트 인증키
    is_active              BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT available_lte_total CHECK (available_spaces <= total_spaces)
);
```

| 열 | 설명 |
|---|---|
| `base_fee` | 입차 후 `base_duration_minutes`까지 적용되는 고정 요금 |
| `base_duration_minutes` | 기본 요금이 적용되는 시간(분). `0`이면 기본 요금 없이 즉시 추가 요금 부과 |
| `extra_fee_per_unit` | `base_duration_minutes` 초과 후 `extra_fee_unit_minutes`마다 부과되는 요금 |
| `extra_fee_unit_minutes` | 추가 요금 부과 단위(분). 예: `10`이면 10분마다 `extra_fee_per_unit` 추가 |
| `daily_max_fee` | 하루 최대 부과 금액(원). `NULL`이면 상한 없음 |
| `api_key` | 클라이언트 프로그램이 이 주차장 서버에 연결할 때 사용하는 인증키 |

> **요금 계산 예시** (기본 30분 1,000원 / 이후 10분당 200원 / 일 최대 10,000원):  
> `base_fee = 1000`, `base_duration_minutes = 30`, `extra_fee_per_unit = 200`, `extra_fee_unit_minutes = 10`, `daily_max_fee = 10000`  
> - 20분 주차 → 1,000원  
> - 50분 주차 → 1,000 + (2 × 200) = 1,400원  
> - 무료 주차장 → 모든 요금 필드 `0`, `daily_max_fee = NULL`

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
    phone                  VARCHAR(20),
    operating_hours        VARCHAR(255),
    base_fee               INT,                              -- 기본 요금 (원)
    base_duration_minutes  INT,                              -- 기본 요금 적용 시간 (분)
    extra_fee_per_unit     INT,                              -- 단위 시간당 추가 요금 (원)
    extra_fee_unit_minutes INT,                              -- 추가 요금 단위 시간 (분)
    daily_max_fee          INT,                              -- 일일 최대 요금 (원). NULL이면 상한 없음
    lot_type               VARCHAR(20) NOT NULL
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
    id                     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
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
    phone                  VARCHAR(20),
    operating_hours        VARCHAR(255),
    base_fee               INT,
    base_duration_minutes  INT,
    extra_fee_per_unit     INT,
    extra_fee_unit_minutes INT,
    daily_max_fee          INT,
    lot_type               VARCHAR(20) NOT NULL
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

---
---
---

# 팀원별 참고 가이드

> 이 섹션은 구현 담당자가 스키마 전체를 읽지 않아도 자기 작업에 필요한 필드만 빠르게 파악할 수 있도록 정리한 요약입니다.

---

## 클라이언트 팀 (주차장 카메라)

클라이언트가 직접 읽거나 쓰는 테이블은 없습니다. 서버 API를 통해 간접적으로 아래 두 테이블에 영향을 줍니다.

### 전송해야 할 값과 그 저장 위치

| 전송 필드 | 저장 테이블 | 저장 열 | 비고 |
|-----------|------------|---------|------|
| 번호판 문자열 | `vehicles`, `entry_exit_logs` | `plate_hash`, `plate_enc` | **원본 그대로 전송.** 해시/암호화는 서버가 처리 |
| 인식 시각 | `entry_exit_logs` | `client_timestamp` | **ISO 8601 + 타임존 필수.** 예: `2026-05-03T10:00:00+09:00` |

### 요청 JSON 형식

```json
{
  "plate": "12가3456",
  "timestamp": "2026-05-03T10:00:00+09:00"
}
```

- `plate`: 공백 없이 전송. `"12 가 3456"` (X) → `"12가3456"` (O)
- `timestamp`: 타임존 생략 불가. `"2026-05-03T10:00:00"` (X) → `"2026-05-03T10:00:00+09:00"` (O)

### 인증에 필요한 값

| 값 | 출처 테이블 | 열 | 비고 |
|----|------------|-----|------|
| API 키 | `parking_lots` | `api_key` | 주차장별로 다름. 서버 관리자에게 발급받아야 함 |

### 서버가 자동으로 처리하는 것 (클라이언트가 신경 쓸 필요 없음)

- 입차/출차 판단 — `vehicles` 테이블 존재 여부로 서버가 결정
- 번호판 해시/암호화 — 서버 내부 처리
- `available_spaces` 증감 — 서버 내부 처리
- 요금 계산 — `base_fee`, `extra_fee_per_unit`, `daily_max_fee`, `entered_at` 기준으로 서버가 계산

---

## 프론트엔드 팀

담당 화면에 따라 참고할 테이블이 다릅니다.

### 일반 사용자 화면 — Hub Server의 `lots`

일반 사용자에게 보여줄 주차장 현황은 모두 이 테이블에서 옵니다.

| 열 | 표시 용도 | 비고 |
|----|----------|------|
| `name` | 주차장 이름 | |
| `address` | 주소 | |
| `phone` | 전화번호 | NULL 가능 |
| `operating_hours` | 운영 시간 | NULL 가능, 자유 형식 문자열 |
| `base_fee` | 기본 요금 | NULL 가능 |
| `base_duration_minutes` | 기본 요금 적용 시간(분) | NULL 가능 |
| `extra_fee_per_unit` | 단위 시간당 추가 요금 | NULL 가능 |
| `extra_fee_unit_minutes` | 추가 요금 단위 시간(분) | NULL 가능 |
| `daily_max_fee` | 일일 최대 요금 | NULL이면 상한 없음 |
| `total_spaces` | 전체 면수 | |
| `available_spaces` | **잔여 면수** | 폴링/웹훅으로 갱신되는 캐시 값 |
| `last_synced_at` | 데이터 갱신 시각 | 오래된 경우 "정보가 오래되었을 수 있습니다" 표시 권장 |
| `latitude`, `longitude` | 지도 마커 | NULL 가능. 3차 목표 기능 |
| `is_active` | **비활성 주차장 필터링** | `false`이면 목록에서 제외할 것 |

> `lot_type`, `pl_*`, `openapi_*` 열은 백엔드 라우팅용 내부 필드입니다. FE에서 사용하지 않습니다.

---

### 관리자 화면 — Parking Lot Server

#### 현재 주차 차량 목록 — `vehicles`

| 열 | 표시 용도 | 비고 |
|----|----------|------|
| `plate_enc` | 번호판 표시 | **복호화는 서버가 처리해서 응답.** FE는 문자열로 받음 |
| `entered_at` | 입차 시각 | 주차 경과 시간 계산 가능 |

> `plate_hash`는 내부 조회용이므로 FE에 노출할 필요 없습니다.

#### 입출차 로그 — `entry_exit_logs`

| 열 | 표시 용도 | 비고 |
|----|----------|------|
| `plate_enc` | 번호판 표시 | 복호화 후 응답 |
| `event_type` | 입차/출차 구분 | `"entry"` 또는 `"exit"` |
| `fee` | 요금 | 출차 이벤트에만 값 있음. 입차는 `null` |
| `client_timestamp` | 실제 입출차 시각 | 사용자에게 보여줄 시각 |
| `server_received_at` | 서버 수신 시각 | 일반적으로 노출 불필요. 디버깅용 |

#### 주차장 정보 — `parking_lots`

| 열 | 표시/수정 용도 | 비고 |
|----|--------------|------|
| `name`, `address` | 주차장 기본 정보 수정 | |
| `total_spaces` | 전체 면수 수정 | |
| `available_spaces` | 현재 잔여 면수 표시 | 직접 수정 불필요 (서버가 자동 관리) |
| `base_fee` | 기본 요금 수정 | |
| `base_duration_minutes` | 기본 요금 적용 시간 수정 | |
| `extra_fee_per_unit` | 단위 추가 요금 수정 | |
| `extra_fee_unit_minutes` | 추가 요금 단위 시간 수정 | |
| `daily_max_fee` | 일일 상한 요금 수정 | `null`이면 상한 없음 |
| `is_active` | 주차장 활성/비활성 토글 | |

> `api_key`는 보안 필드입니다. 관리자에게 표시할 경우 마스킹 처리(`abcd...xyz`) 권장합니다.
