# OpenPark — Parking Lot Server 현황

> 작성일: 2026-05-08  
> 브랜치: `feat/private_parking_lot_server`

---

## 구현 완료

**Parking Lot Server (Private 모드)** 가 로컬에서 동작하며, 클라이언트(카메라) 및 관리자와 통신 가능한 상태입니다.

### 기술 스택
- FastAPI + PostgreSQL (Docker)
- JWT 인증 (관리자), API Key 인증 (카메라 클라이언트)
- 번호판 보안: HMAC-SHA256 (조회용 해시) + AES-256-GCM (복호화 가능 암호화)

### 구현된 기능

| 영역 | 내용 |
|------|------|
| 관리자 인증 | 로그인 → JWT 발급 (`POST /admin/login`) |
| 주차장 관리 | 등록·조회·수정·비활성화 |
| 관리자 계정 | superadmin이 admin 계정 생성·관리 |
| 차량 현황 | 현재 주차 중인 차량 목록, 수동 출차 |
| 입출차 로그 | 전체 이력 조회 (날짜 필터, 번호판 검색) |
| 입출차 처리 | 카메라 클라이언트로부터 번호판 수신 → 입출차 판단 → 응답 |

---

## 전체 API 목록

### 관리자 (JWT 인증 필요)

```
POST   /admin/login                  # 로그인 → access_token 반환

POST   /admin/lots                   # 주차장 등록 (superadmin)
GET    /admin/lots                   # 주차장 목록
GET    /admin/lots/{lot_id}          # 주차장 단건 조회
PATCH  /admin/lots/{lot_id}          # 주차장 정보 수정
DELETE /admin/lots/{lot_id}          # 주차장 비활성화 (superadmin)

POST   /admin/users                  # admin 계정 생성 (superadmin)
GET    /admin/users                  # 계정 목록 (superadmin)
PATCH  /admin/users/{user_id}        # 계정 수정 (본인)
DELETE /admin/users/{user_id}        # 계정 삭제 (superadmin)

GET    /admin/vehicles               # 현재 주차 중인 차량 목록
DELETE /admin/vehicles/{vehicle_id}  # 수동 출차 처리

GET    /admin/logs                   # 입출차 로그 (날짜·번호판 필터, 페이지네이션)
```

### 클라이언트 (API Key 인증 필요)

```
POST   /api/v1/plates                # 번호판 전송 → 입차/출차 응답
```

---

## 프론트엔드 팀에게

현재 구현된 관리자 API 목록은 위와 같습니다. 응답 예시는 아래를 참고해 주세요.

**`GET /admin/lots` 응답 예시**
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
    "daily_max_fee": 10000,
    "api_key": "abcd...xyz",
    "is_active": true,
    "created_at": "...",
    "updated_at": "..."
  }
]
```

**`GET /admin/vehicles` 응답 예시**
```json
[
  {
    "id": "uuid",
    "parking_lot_id": "uuid",
    "plate": "12가3456",
    "entered_at": "2026-05-08T10:00:00+09:00"
  }
]
```

**`GET /admin/logs` 응답 예시** (쿼리 파라미터: `date_from`, `date_to`, `plate`, `limit`, `offset`)
```json
[
  {
    "id": "uuid",
    "parking_lot_id": "uuid",
    "plate": "12가3456",
    "event_type": "entry",
    "fee": null,
    "client_timestamp": "2026-05-08T10:00:00+09:00",
    "server_received_at": "2026-05-08T10:00:01+09:00"
  }
]
```

> 화면 디자인 및 필요한 API 명세가 결정되면 공유해 주세요.  
> 지금 없는 기능(예: 통계, 정렬 옵션 등)이 필요하다면 요청해 주세요.

---

## 클라이언트 팀에게

카메라가 번호판을 인식하면 아래 형식으로 서버에 요청을 보내면 됩니다.

### 요청

```
POST /api/v1/plates
Authorization: Bearer {api_key}
Content-Type: application/json
```

```json
{
  "plate": "12가3456",
  "timestamp": "2026-05-08T10:00:00+09:00"
}
```

- `api_key`: 주차장별로 발급. 서버 관리자에게 받아야 함 (`POST /admin/lots` 등록 시 1회 발급)
- `timestamp`: 카메라가 번호판을 인식한 시각. **ISO 8601 + 타임존 필수**

### 응답

**입차로 처리된 경우**
```json
{
  "event": "entry",
  "entered_at": "2026-05-08T10:00:00+09:00"
}
```

**출차로 처리된 경우**
```json
{
  "event": "exit",
  "fee": 3000,
  "parked_duration_minutes": 90
}
```

**인증 실패 (잘못된 api_key 또는 비활성 주차장)**
```json
HTTP 401
{ "detail": "invalid_api_key" }
```

**주차장이 만석인 경우 (입차 불가)**
```json
HTTP 409
{ "detail": "parking_lot_full" }
```

### 입출차 판단 방식

서버가 자동으로 판단합니다. 같은 번호판을 처음 보내면 입차, 이미 있으면 출차로 처리합니다. 클라이언트가 판단할 필요 없습니다.

> 재전송 시 주의: 응답 실패 후 같은 요청을 재전송하면 입출차가 반전될 수 있습니다. 재전송 전에 현재 상태를 확인하는 절차가 필요합니다.

---

## 로컬 실행 및 테스트 방법

### 사전 요구사항
- Docker Desktop
- Python 3.12+

### 서버 실행

```bash
cd parking_lot_server

# 1. 가상환경 설정 (최초 1회)
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt

# 2. DB 실행
docker compose up -d

# 3. DB 마이그레이션 (최초 1회 또는 스키마 변경 시)
alembic upgrade head

# 4. superadmin 계정 생성 (최초 1회)
python scripts/seed.py

# 5. 서버 실행
uvicorn app.main:app --reload
```

서버가 뜨면 `http://localhost:8000/docs` 에서 Swagger UI로 API를 확인할 수 있습니다.

### API 테스트 순서

```bash
# 1. 로그인 → access_token 발급
POST /admin/login
{ "username": "superadmin", "password": "changeme" }

# 2. 주차장 등록 → api_key 발급 (이 때만 원문 반환)
POST /admin/lots
Authorization: Bearer {access_token}

# 3. 번호판 전송 (입차)
POST /api/v1/plates
Authorization: Bearer {api_key}
{ "plate": "12가3456", "timestamp": "2026-05-08T10:00:00+09:00" }

# 4. 같은 번호판 재전송 (출차)
POST /api/v1/plates
Authorization: Bearer {api_key}
{ "plate": "12가3456", "timestamp": "2026-05-08T11:30:00+09:00" }
```

### 자동화 테스트 실행

```bash
cd parking_lot_server
source .venv/Scripts/activate

# Docker DB가 실행 중이어야 함 (테스트 전용 DB: 포트 5433)
docker compose up -d

# 전체 테스트 + 커버리지
python -m pytest

# 빠르게 (커버리지 제외)
python -m pytest --no-cov

# 특정 파일만
python -m pytest tests/routers/test_plates.py
```
