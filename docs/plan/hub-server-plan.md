# Hub Server 구현 계획

> 작성일: 2026-05-08  
> 참고 문서: `hub-parking-lot-integration-plan.md`

---

## 이 문서의 목적

이 문서는 Hub Server 리포지토리에서 작업하는 개발자(또는 LLM)가 다른 컨텍스트 없이도 Hub Server를 구현할 수 있도록 필요한 모든 정보를 담고 있다. Parking Lot Server(PLS)는 이미 구현 완료된 별도 서버이며, 이 문서에 명시된 인터페이스를 준수한다.

---

## 시스템 구성

```
카메라 클라이언트
    │ POST /api/v1/plates
    ▼
Parking Lot Server (PLS)  ──── POST /lots ────►  Hub Server
    │ GET /public/status/{lot_id}                     │
    ◄────────────────────────────────────────── 폴링  │
                                                       ▼
                                               일반 사용자 (FE)
```

- **PLS**: 주차장 입출차 처리, 관리자 관리. 구현 완료.
- **Hub**: PLS로부터 주차장 정보를 받아 통합·제공. 이 문서에서 구현.

---

## PLS 기술 스택 (참고용)

PLS와 동일한 스택을 권장한다.

| 항목 | 기술 |
|------|------|
| 언어 | Python 3.12 |
| 프레임워크 | FastAPI |
| DB | PostgreSQL 16 |
| ORM | SQLAlchemy 2.x (asyncio) |
| 드라이버 | asyncpg (런타임), psycopg2-binary (Alembic) |
| 마이그레이션 | Alembic |
| 인증 | JWT (python-jose) |
| 비밀번호 | bcrypt |
| 환경변수 | pydantic-settings |
| 테스트 | pytest, pytest-asyncio, pytest-cov, httpx |
| 인프라 | Docker Compose |

---

## Hub Server 역할

- PLS로부터 주차장 등록·비활성화 알림을 수신해 DB에 저장
- 등록된 주차장의 잔여 면수를 PLS에 주기적으로 폴링해 캐싱
- 일반 사용자(FE)에게 통합 주차장 현황 제공

---

## Hub DB 스키마

### `users` — Hub 관리자 계정

```sql
CREATE TABLE users (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    username       VARCHAR(50) UNIQUE NOT NULL,
    email          VARCHAR(100) UNIQUE NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    role           VARCHAR(20) NOT NULL DEFAULT 'admin'
                       CHECK (role IN ('superadmin', 'admin')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `lots` — 주차장 통합 레지스트리

```sql
CREATE TABLE lots (
    id                     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                   VARCHAR(100) NOT NULL,
    address                VARCHAR(255),
    latitude               DECIMAL(10, 8),
    longitude              DECIMAL(11, 8),
    phone                  VARCHAR(20),
    operating_hours        VARCHAR(255),
    base_fee               INT,
    base_duration_minutes  INT,
    extra_fee_per_unit     INT,
    extra_fee_unit_minutes INT,
    daily_max_fee          INT,
    lot_type               VARCHAR(20) NOT NULL
                               CHECK (lot_type IN ('parking_lot_server', 'openapi')),
    total_spaces           INT,
    available_spaces       INT,                        -- 폴링으로 갱신되는 캐시
    last_synced_at         TIMESTAMPTZ,                -- 마지막 폴링 성공 시각
    is_active              BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- lot_type = 'parking_lot_server' 전용
    pl_server_url          VARCHAR(255),               -- PLS 베이스 URL
    pl_lot_id              UUID,                       -- PLS의 parking_lots.id
    -- pl_api_key 없음 (단일 PLS 가정, 인증 불필요)

    -- lot_type = 'openapi' 전용 (추후)
    openapi_source         VARCHAR(50),
    openapi_lot_id         VARCHAR(50),

    CONSTRAINT pls_requires_url CHECK (
        lot_type != 'parking_lot_server'
        OR (pl_server_url IS NOT NULL AND pl_lot_id IS NOT NULL)
    )
);

CREATE INDEX idx_lots_type ON lots (lot_type, is_active);
CREATE INDEX idx_lots_pl_lot_id ON lots (pl_lot_id);  -- PATCH /lots/{pl_lot_id} 조회용
```

---

## 환경변수

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost/hub
SECRET_KEY=                 # openssl rand -hex 32 (JWT 서명)
MODE=production             # 향후 확장 대비
```

---

## Hub가 구현해야 할 API

### 1. `POST /lots` — PLS로부터 lot 등록 수신

PLS가 `POST /admin/lots` 성공 직후 자동으로 호출한다.  
**PLS는 이 응답이 201이 아니면 lot 생성 자체를 롤백한다.** 반드시 성공 응답을 내려야 한다.

**요청**
```
POST /lots
Content-Type: application/json
(인증 없음)
```

```json
{
  "pls_url": "http://192.168.1.100:8000",
  "lot_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "본관 주차장",
  "address": "경북대학교 북문 앞",
  "total_spaces": 100,
  "base_fee": 1000,
  "base_duration_minutes": 30,
  "extra_fee_per_unit": 200,
  "extra_fee_unit_minutes": 10,
  "daily_max_fee": null
}
```

| 필드 | 타입 | Hub DB 저장 위치 |
|------|------|----------------|
| `pls_url` | string | `pl_server_url` |
| `lot_id` | UUID | `pl_lot_id` |
| `name` | string | `name` |
| `address` | string \| null | `address` |
| `total_spaces` | int | `total_spaces` |
| `base_fee` | int | `base_fee` |
| `base_duration_minutes` | int | `base_duration_minutes` |
| `extra_fee_per_unit` | int | `extra_fee_per_unit` |
| `extra_fee_unit_minutes` | int | `extra_fee_unit_minutes` |
| `daily_max_fee` | int \| null | `daily_max_fee` |

등록 시 자동으로 설정되는 값:
- `lot_type = 'parking_lot_server'`
- `is_active = true`
- `available_spaces = total_spaces` (최초값, 폴링 전)

**응답**

| 상태 | 의미 |
|------|------|
| `201 Created` | 등록 성공 |
| `409 Conflict` | 동일 `pl_lot_id`가 이미 존재 |

---

### 2. `PATCH /lots/{pl_lot_id}` — lot 비활성화 수신

PLS가 `DELETE /admin/lots/{lot_id}` 처리 시 호출한다.  
**best-effort**: PLS는 이 요청이 실패해도 PLS 측 비활성화는 유지한다.

`{pl_lot_id}`는 Hub DB의 `pl_lot_id` 필드 값으로 조회한다 (Hub 내부 `id`가 아님).

**요청**
```
PATCH /lots/{pl_lot_id}
Content-Type: application/json
(인증 없음)
```

```json
{ "is_active": false }
```

**응답**

| 상태 | 의미 |
|------|------|
| `200 OK` | 업데이트 성공 |
| `404 Not Found` | 해당 `pl_lot_id` 없음 |

---

## Hub가 PLS에 호출하는 API

### `GET /public/status/{lot_id}` — 잔여 면수 폴링

PLS가 Public 모드일 때만 노출되는 인증 없는 공개 엔드포인트.

```
GET {pl_server_url}/public/status/{pl_lot_id}
(인증 없음)
```

**응답 (200 OK)**

```json
{
  "lot_id": "uuid",
  "name": "본관 주차장",
  "address": "...",
  "total_spaces": 100,
  "available_spaces": 73,
  "base_fee": 1000,
  "base_duration_minutes": 30,
  "extra_fee_per_unit": 200,
  "extra_fee_unit_minutes": 10,
  "daily_max_fee": null,
  "is_active": true,
  "synced_at": "2026-05-08T10:00:00+09:00"
}
```

`synced_at`은 PLS의 응답 시각이다. Hub는 이 값을 `last_synced_at`에 저장한다.

**폴링 구현 지침**

- `is_active=true`인 `lot_type='parking_lot_server'` lot만 폴링
- 폴링 주기: Hub에서 결정 (권장 30초 ~ 5분)
- PLS 응답이 404이거나 연결 오류 시: `last_synced_at`만 갱신하지 않고 넘어감 (기존 캐시 유지)
- `is_active=false` 응답 시: Hub DB의 `is_active`도 `false`로 업데이트

---

## Hub가 FE에 제공하는 API (예시)

FE 팀 요구사항에 따라 구체적으로 결정되지만, 최소한 아래를 제공한다.

### `GET /lots` — 주차장 목록

```json
[
  {
    "id": "uuid",
    "name": "본관 주차장",
    "address": "...",
    "total_spaces": 100,
    "available_spaces": 73,
    "base_fee": 1000,
    "base_duration_minutes": 30,
    "extra_fee_per_unit": 200,
    "extra_fee_unit_minutes": 10,
    "daily_max_fee": null,
    "is_active": true,
    "last_synced_at": "2026-05-08T10:00:00+09:00"
  }
]
```

- `is_active=false`인 lot은 기본적으로 제외
- `last_synced_at`이 오래된 경우 FE에서 "정보가 오래되었을 수 있습니다" 표시 권장

---

## 구현 순서

| 단계 | 작업 |
|------|------|
| 1 | 프로젝트 세팅 (FastAPI, PostgreSQL, Docker Compose) |
| 2 | DB 모델 + Alembic 마이그레이션 |
| 3 | superadmin seed 스크립트 + JWT 인증 |
| 4 | `POST /lots` — PLS lot 등록 수신 |
| 5 | `PATCH /lots/{pl_lot_id}` — PLS lot 비활성화 수신 |
| 6 | 폴링 로직 — `GET /public/status/{lot_id}` 주기적 호출 |
| 7 | `GET /lots` — FE용 주차장 목록 API |
| 8 | 로컬 PLS와 연동 테스트 |

---

## 로컬 연동 테스트 환경

PLS와 Hub를 같은 머신에서 포트를 다르게 실행한다.

```bash
# PLS (포트 8000, Public 모드)
# PLS .env: MODE=public, HUB_URL=http://localhost:8001
cd parking_lot_server
docker compose up -d
uvicorn app.main:app --port 8000 --reload

# Hub (포트 8001)
cd hub_server
docker compose up -d
uvicorn app.main:app --port 8001 --reload
```

**검증 순서**

1. PLS Swagger(`http://localhost:8000/docs`)에서 `POST /admin/login` → superadmin JWT 발급
2. `POST /admin/lots` → Hub에 자동 push 확인 (`http://localhost:8001/lots` 조회)
3. Hub 폴링 시작 → `available_spaces` 갱신 확인
4. PLS에서 입차(`POST /api/v1/plates`) → Hub 폴링 후 `available_spaces` 감소 확인
5. `DELETE /admin/lots/{lot_id}` → Hub `is_active=false` 확인

---

## 현재 PLS 구현 완료 항목

Hub Server 개발 시 아래 PLS 엔드포인트를 그대로 사용할 수 있다.

| 엔드포인트 | 설명 |
|-----------|------|
| `POST /auth/signup` | 주차장 주인 회원가입 (인증 없음) |
| `POST /admin/login` | 관리자 로그인 → JWT |
| `POST /admin/lots` | 주차장 등록 (Public 모드에서 Hub push 포함) |
| `DELETE /admin/lots/{lot_id}` | 주차장 비활성화 (Public 모드에서 Hub 알림 포함) |
| `GET /public/status/{lot_id}` | 잔여 면수 폴링 (Public 모드에서만 노출) |
| `PATCH /admin/users/{user_id}` | 주차장 주인에게 lot 배정 |

PLS는 `http://localhost:8000`에서 실행되며, Swagger UI는 `http://localhost:8000/docs`에서 확인 가능하다.
