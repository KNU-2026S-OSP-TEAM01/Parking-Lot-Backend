# Parking Lot Server 구현 계획

> 작성일: 2026-05-06  
> 참고 문서: `docs/database-schema-v2.md`, `docs/client-api-spec.md`

---

## 개요

FastAPI + PostgreSQL 기반의 Parking Lot Server를 구현한다.  
현 단계의 목표는 **로컬에서 클라이언트와 통신 가능한 Parking Lot Server** 완성이다.  
Hub Server 연동(`/public/status`)은 이번 단계에서 제외하고, 추후 확장한다.

---

## 프로젝트 구조

```
parking_lot_server/
├── app/
│   ├── main.py
│   ├── config.py               # 환경변수 (DB_URL, SECRET_KEY, AES_KEY, HMAC_KEY, MODE)
│   ├── database.py             # SQLAlchemy 비동기 엔진 및 세션
│   ├── models/                 # DB 스키마 문서 기준 SQLAlchemy 모델
│   │   ├── parking_lot.py
│   │   ├── user.py
│   │   ├── vehicle.py          # plate_enc → LargeBinary (BYTEA), entered_at → DateTime(timezone=True)
│   │   └── entry_exit_log.py   # 모든 시각 컬럼 → DateTime(timezone=True) (TIMESTAMPTZ)
│   ├── schemas/                # Pydantic 요청/응답 모델 (엔티티 단위)
│   │   ├── auth.py             # LoginRequest, TokenResponse
│   │   ├── lot.py              # LotCreate, LotOut, LotPatch
│   │   ├── user.py             # UserCreate, UserOut, UserPatch
│   │   ├── vehicle.py          # VehicleOut
│   │   ├── log.py              # LogOut
│   │   └── plate.py            # PlateRequest, EntryResponse, ExitResponse
│   ├── routers/
│   │   ├── plates.py           # POST /api/v1/plates
│   │   ├── admin/
│   │   │   ├── auth.py         # POST /admin/login
│   │   │   ├── users.py        # POST/GET /admin/users, PATCH/DELETE /admin/users/{user_id}
│   │   │   ├── vehicles.py     # GET /admin/vehicles, DELETE /admin/vehicles/{vehicle_id}
│   │   │   ├── logs.py         # GET /admin/logs
│   │   │   └── lots.py         # POST/GET /admin/lots, GET/PATCH/DELETE /admin/lots/{lot_id}
│   │   └── public/             # 추후 Hub Server 연동 시 추가
│   ├── services/
│   │   ├── crypto.py           # hmac_hash(), aes_encrypt(), aes_decrypt()
│   │   └── fee.py              # calculate_fee()
│   └── dependencies/
│       ├── api_key.py          # API Key 검증 → ParkingLot 반환
│       └── jwt_auth.py         # JWT 검증 → user 페이로드 반환
├── alembic/
├── scripts/
│   └── seed.py                 # superadmin 최초 계정 생성 (일회성)
├── docker-compose.yml          # PostgreSQL 컨테이너
├── .env
└── requirements.txt
```

**주요 패키지**

```
fastapi, uvicorn[standard]          # 웹 서버
sqlalchemy[asyncio], asyncpg        # 비동기 PostgreSQL
psycopg2-binary                     # Alembic 마이그레이션용 동기 드라이버
alembic                             # DB 마이그레이션
pydantic-settings                   # 환경변수 관리
python-jose[cryptography]           # JWT
passlib[bcrypt]                     # 비밀번호 해시
cryptography                        # AES-256-GCM

# 테스트
pytest, pytest-asyncio, pytest-cov  # 테스트 실행 및 커버리지
httpx                               # FastAPI 엔드포인트 테스트용 HTTP 클라이언트
```

---

## 테스트 전략

### 원칙

각 단계 구현 후 반드시 해당 단계의 테스트를 작성하고 통과한 뒤에 다음 단계로 진행한다.  
최종적으로 `POST /api/v1/plates` 엔드포인트까지 완성되면 통합 테스트로 전체 흐름을 검증한다.

### 환경

- `.venv` 가상환경으로 패키지 통일
- Docker PostgreSQL을 테스트 DB로 사용
- 각 테스트는 트랜잭션 롤백으로 DB를 오염시키지 않음
- CI/CD: 커버리지 기준 미달 시 실패 처리 (`--cov-fail-under`, 단계별로 기준 상향)

### 테스트 구조

```
tests/
├── conftest.py              # 공용 픽스처 (DB 세션 등)
├── test_config.py           # 1단계: 환경변수 검증
├── models/
│   └── test_models.py       # 2단계: 모델 구조 및 DB 제약 조건
├── services/
│   ├── test_crypto.py       # 3단계: 암호화 함수
│   └── test_fee.py          # 4단계: 요금 계산 로직
├── routers/
│   ├── test_auth.py         # 5단계: 관리자 로그인 + seed
│   ├── test_lots.py         # 6단계: 주차장 CRUD
│   ├── test_users.py        # 6단계: 관리자 계정 CRUD
│   ├── test_vehicles.py     # 6단계: 차량 목록, 수동 출차
│   ├── test_logs.py         # 6단계: 입출차 로그 조회
│   └── test_plates.py       # 7단계: 입출차 엔드포인트
└── test_integration.py      # 최종: 주차장 등록 → 입차 → 출차 전체 흐름
```

### 커버리지 기준

| 단계 완료 후 | 기준 |
|------------|------|
| 1~2단계    | 60%  |
| 3~4단계    | 70%  |
| 5~6단계    | 80%  |
| 7단계 이후  | 85%  |

---

## 단계별 구현

---

### 1단계. 프로젝트 세팅

환경변수, DB 연결, 라우터 마운트 구성. 특별한 로직은 없고 이후 모든 단계의 기반이 된다.

**Docker로 PostgreSQL 실행**

별도 PostgreSQL 설치 없이 Docker로 개발용 DB를 띄운다.

```yaml
# docker-compose.yml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: openpark
      POSTGRES_USER: openpark
      POSTGRES_PASSWORD: openpark
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

```bash
docker compose up -d   # DB 시작
docker compose down    # DB 종료 (데이터 유지)
```

`DATABASE_URL`은 위 설정 기준으로 `postgresql+asyncpg://openpark:openpark@localhost/openpark`.

**`main.py`에서 `MODE` 분기 구조를 미리 잡아둔다.**

```python
if settings.mode == "public":
    app.include_router(public_status.router, prefix="/public")
```

`.env`에 들어갈 키는 모두 `openssl rand -hex 32`로 생성한다.

---

### 2단계. DB 모델 + Alembic 마이그레이션

`docs/database-schema-v2.md`의 DDL을 SQLAlchemy 모델로 옮긴다.  
주의할 점은 `plate_enc` 컬럼이 PostgreSQL `BYTEA` 타입이므로 SQLAlchemy에서 `LargeBinary`로 선언해야 한다는 것이다. 나머지 타입 매핑은 직관적이다.

```python
# models/vehicle.py — BYTEA 매핑 예시
plate_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
```

모델 작성 후 Alembic으로 마이그레이션 파일을 자동 생성하고 적용한다.

```bash
alembic revision --autogenerate -m "init"
alembic upgrade head
```

---

### 3단계. `crypto.py` — 번호판 암호화

번호판은 두 가지 형태로 저장된다 (스키마 설계 문서 참고).  
- `plate_hash`: HMAC-SHA256. DB 조회·비교 전용. 원본 복원 불가.  
- `plate_enc`: AES-256-GCM 암호화. 관리자 화면 표시용. 복호화 가능.

**HMAC-SHA256** — 동일 입력에 항상 동일 출력이 나오므로 해시값만으로 `vehicles` 테이블 조회가 가능하다.

**AES-256-GCM** — 암호화할 때마다 랜덤 IV(12바이트)를 생성한다. 저장 형식은 `IV(12바이트) + 암호문 + 인증 태그(16바이트)`이며, 복호화 시 앞 12바이트를 IV로 분리해 사용한다.

```python
# services/crypto.py 핵심 구조

def hmac_hash(plate: str) -> str:
    """번호판 → 고정 길이 해시. vehicles 테이블 조회에 사용."""
    return hmac.new(hmac_key, plate.encode(), hashlib.sha256).hexdigest()

def aes_encrypt(plate: str) -> bytes:
    """번호판 → 암호화. 매 호출마다 다른 IV를 생성하므로 결과가 매번 달라진다."""
    iv = os.urandom(12)
    ciphertext = AESGCM(aes_key).encrypt(iv, plate.encode(), None)
    return iv + ciphertext  # IV를 앞에 붙여 함께 저장

def aes_decrypt(data: bytes) -> str:
    """저장된 바이트 → 번호판 원문. 앞 12바이트를 IV로 분리한 후 복호화."""
    iv, ciphertext = data[:12], data[12:]
    return AESGCM(aes_key).decrypt(iv, ciphertext, None).decode()
```

---

### 4단계. `fee.py` — 요금 계산

`parking_lots` 테이블의 요금 필드를 기준으로 출차 시 요금을 계산한다.  
`daily_max_fee`는 자정 기준이 아닌 **입차 시각 기준 24시간 단위**로 상한을 누적 적용한다.  
예) 25시간 주차 → `daily_max_fee * 2`가 상한.

```python
# services/fee.py 핵심 구조

def calculate_fee(lot, entered_at, exited_at) -> int:
    duration_minutes = ceil((exited_at - entered_at).total_seconds() / 60)

    # 기본 요금 구간 내이면 기본 요금만 부과
    if duration_minutes <= lot.base_duration_minutes:
        fee = lot.base_fee
    else:
        over = duration_minutes - lot.base_duration_minutes
        fee = lot.base_fee + ceil(over / lot.extra_fee_unit_minutes) * lot.extra_fee_per_unit

    # 일일 상한: 입차 시각 기준 24시간마다 상한이 초기화
    if lot.daily_max_fee is not None:
        days = floor((exited_at - entered_at).total_seconds() / 86400) + 1
        fee = min(fee, lot.daily_max_fee * days)

    return fee
```

---

### 5단계. 관리자 JWT 인증 + seed 스크립트

로그인 성공 시 JWT를 발급한다. 페이로드에 `role`과 `lot_id`를 포함하여 이후 모든 관리자 API에서 별도 DB 조회 없이 권한 범위를 판단할 수 있도록 한다.

```python
# JWT 페이로드 구조
{
    "sub":    "<user_id>",
    "role":   "admin" | "superadmin",
    "lot_id": "<parking_lot_id>" | None,  # superadmin은 None
    "exp":    <만료 시각>
}
```

검증 의존성은 토큰을 디코딩해 페이로드를 반환하기만 한다. 각 라우터가 `role`과 `lot_id`를 꺼내 쿼리 범위를 스스로 제한한다.

**seed 스크립트** — API로 만들 수 없는 최초 `superadmin` 계정을 생성한다. 일회성으로 실행하며 운영 환경에서는 사용하지 않는다.

```bash
python scripts/seed.py   # superadmin 계정 생성
```

---

### 6단계. 관리자 API

JWT에서 `role`을 확인하고, `admin`이면 자신의 `lot_id`로 쿼리를 제한, `superadmin`이면 제한 없이 전체 접근.

**주차장 (`/admin/lots`)**

| Method | Endpoint | 권한 | 설명 |
|--------|----------|------|------|
| POST | `/admin/lots` | superadmin | 주차장 등록, `api_key` 자동 생성 |
| GET | `/admin/lots` | 전체 | superadmin: 전체 목록 / admin: 자신의 것 |
| GET | `/admin/lots/{lot_id}` | 전체 | 단건 조회 |
| PATCH | `/admin/lots/{lot_id}` | 전체 | 정보 수정 (`available_spaces`, `api_key` 제외) |
| DELETE | `/admin/lots/{lot_id}` | superadmin | 삭제 대신 `is_active=false` 처리 |

**관리자 계정 (`/admin/users`)**

| Method | Endpoint | 권한 | 설명 |
|--------|----------|------|------|
| POST | `/admin/users` | superadmin | `admin` 계정 생성 및 주차장 할당 |
| GET | `/admin/users` | superadmin | 전체 목록 |
| PATCH | `/admin/users/{user_id}` | 전체 | 비밀번호 등 수정 |
| DELETE | `/admin/users/{user_id}` | superadmin | 계정 삭제 |

**현재 주차 차량 (`/admin/vehicles`)**

| Method | Endpoint | 권한 | 설명 |
|--------|----------|------|------|
| GET | `/admin/vehicles` | 전체 | 현재 주차 중인 차량 목록 |
| DELETE | `/admin/vehicles/{vehicle_id}` | 전체 | 예외 상황 수동 출차 처리 (카메라 오류, 강제 퇴거 등). `available_spaces += 1`, `event_type='admin'`으로 로그 기록 |

**입출차 로그 (`/admin/logs`) — 읽기 전용**

| Method | Endpoint | 권한 | 설명 |
|--------|----------|------|------|
| GET | `/admin/logs` | 전체 | 날짜 필터, 번호판 검색 지원 |

**번호판 검색** (`GET /admin/logs`) — `plate_enc`는 암호화되어 있어 LIKE 검색이 불가능하다. 검색어를 HMAC 해시한 후 `plate_hash`와 비교한다.

```python
if plate:
    query = query.where(EntryExitLog.plate_hash == hmac_hash(plate))
```

**번호판 복호화** — `plate_enc`는 DB에서 꺼낸 후 `aes_decrypt()`를 거쳐 응답에 포함한다. FE는 평문 문자열을 받는다.

**`api_key` 응답 마스킹** — `GET /admin/lots` 응답 시 `api_key`는 앞뒤 4자리만 노출(`abcd...xyz`). 실제 값은 최초 `POST /admin/lots` 응답 시 한 번만 반환한다.

---

### 7단계. `POST /api/v1/plates` + API Key 인증

6단계에서 주차장이 등록되어 있어야 테스트 가능하다.

**API Key 인증 의존성** — 요청 헤더의 Bearer 토큰을 `parking_lots.api_key`와 대조해 해당 주차장 객체를 반환한다. 이후 라우터에서는 주차장이 이미 특정된 상태로 로직을 수행한다.

```python
# dependencies/api_key.py 핵심 구조

async def get_parking_lot(credentials, db) -> ParkingLot:
    lot = await db.execute(
        select(ParkingLot).where(ParkingLot.api_key == credentials.credentials)
    )
    if not lot:
        raise HTTPException(401, "invalid_api_key")
    return lot
```

**입출차 처리** — `vehicles` 테이블 조회 결과 하나로 입출차를 분기한다.  
`available_spaces` 증감과 `vehicles` 조작이 원자적으로 실행되어야 하므로 **하나의 트랜잭션** 안에서 처리한다.  
출차 시에는 `plate_enc`와 `entered_at`을 DELETE **이전에** 반드시 읽어야 한다. 삭제 후에는 로그에 기록할 수 없다.

```python
# routers/plates.py 핵심 구조

async with db.begin():  # 트랜잭션 시작
    vehicle = await db.execute(
        select(Vehicle).where(parking_lot_id == lot.id, plate_hash == hmac_hash(body.plate))
    )

    if vehicle is None:
        # 입차: INSERT + available_spaces 감소
        db.add(Vehicle(plate_hash=..., plate_enc=aes_encrypt(body.plate), entered_at=body.timestamp))
        lot.available_spaces -= 1
        db.add(EntryExitLog(event_type="entry", ...))
        return EntryResponse(...)

    else:
        # 출차: plate_enc, entered_at 선읽기 → DELETE → 요금 계산
        plate_enc  = vehicle.plate_enc   # DELETE 전에 반드시 읽기
        entered_at = vehicle.entered_at
        await db.delete(vehicle)
        lot.available_spaces += 1
        fee = calculate_fee(lot, entered_at, body.timestamp)
        db.add(EntryExitLog(event_type="exit", fee=fee, plate_enc=plate_enc, ...))
        return ExitResponse(...)
```

> `entered_at`은 클라이언트가 전송한 `timestamp`로 설정한다. 스키마의 `DEFAULT NOW()`는 사용하지 않는다.

---

## 역할(Role) 처리

| 역할 | `parking_lot_id` | 접근 범위 |
|------|-----------------|----------|
| `superadmin` | `NULL` | 모든 주차장 |
| `admin` | 특정 주차장 UUID | 자신의 주차장만 |

---

## 요금 계산 요약

```
주차 시간(분) = ceil((출차 시각 - entered_at) / 60초)

기본 구간 내  → fee = base_fee
기본 구간 초과 → fee = base_fee + ceil(초과 분 / extra_fee_unit_minutes) * extra_fee_per_unit

daily_max_fee 적용 시:
    적용 일수 = floor(총 경과 초 / 86400) + 1
    fee = min(fee, daily_max_fee × 적용 일수)
```

---

## 추후 확장 (Hub Server 연동)

`public/` 라우터 폴더는 이미 구조에 포함되어 있다.  
Hub Server 연동 단계에서 `GET /public/status`를 추가하고, `MODE=public` 환경변수로 마운트 여부를 제어한다.
