# FE API 레퍼런스

> 작성일: 2026-05-08  
> 대상: 프론트엔드 개발팀

---

## 서버 구성

| 서버 | 역할 | 로컬 주소 |
|------|------|----------|
| **Parking Lot Server (PLS)** | 관리자 페이지용 API | `http://localhost:8000` |
| **Hub Server** | 일반 사용자 주차장 현황 API | `http://localhost:8001` (미구현) |

---

## 공통

### 인증

관리자 API는 모두 JWT Bearer 토큰이 필요하다.

```
Authorization: Bearer {access_token}
```

로그인(`POST /admin/login`)으로 발급받은 `access_token`을 사용한다.

### 에러 응답 형식

```json
{ "detail": "에러_코드" }
```

| HTTP 상태 | 의미 |
|----------|------|
| 400 | 잘못된 요청 |
| 401 | 인증 실패 또는 토큰 만료 |
| 403 | 권한 없음 |
| 404 | 리소스 없음 |
| 409 | 중복 리소스 |

---

## 1. 인증

### `POST /auth/signup` — 주차장 주인 회원가입

인증 불필요. 가입 후 `parking_lot_id`는 null이며, superadmin 승인 후 배정된다.

**요청**
```json
{
  "username": "parkowner1",
  "email": "owner@example.com",
  "password": "password123"
}
```

**응답 (201)**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "parkowner1",
  "email": "owner@example.com",
  "role": "admin",
  "parking_lot_id": null,
  "created_at": "2026-05-08T10:00:00+09:00"
}
```

| 에러 | 원인 |
|------|------|
| `409 username_already_exists` | 이미 사용 중인 username |

---

### `POST /admin/login` — 로그인

인증 불필요.

**요청**
```json
{
  "username": "superadmin",
  "password": "changeme"
}
```

**응답 (200)**
```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer"
}
```

토큰은 **8시간** 유효하다. 만료 시 `401`이 반환되므로 재로그인 처리가 필요하다.

| 에러 | 원인 |
|------|------|
| `401 invalid_credentials` | 아이디 또는 비밀번호 불일치 |

---

## 2. 주차장 관리

### `POST /admin/lots` — 주차장 등록 (superadmin 전용)

**요청**
```json
{
  "name": "본관 주차장",
  "address": "경북대학교 북문 앞",
  "total_spaces": 100,
  "base_fee": 1000,
  "base_duration_minutes": 30,
  "extra_fee_per_unit": 200,
  "extra_fee_unit_minutes": 10,
  "daily_max_fee": 10000
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | ✅ | |
| `address` | string | | |
| `total_spaces` | int | ✅ | 양수 |
| `base_fee` | int | | 기본 요금(원). 기본값 0 |
| `base_duration_minutes` | int | | 기본 요금 적용 시간(분). 기본값 0 |
| `extra_fee_per_unit` | int | | 추가 요금(원/단위). 기본값 0 |
| `extra_fee_unit_minutes` | int | | 추가 요금 단위 시간(분). 기본값 10 |
| `daily_max_fee` | int \| null | | 일일 최대 요금(원). null이면 상한 없음 |

**응답 (200)** — `api_key`는 최초 등록 시에만 원문 반환

```json
{
  "id": "uuid",
  "name": "본관 주차장",
  "address": "경북대학교 북문 앞",
  "total_spaces": 100,
  "available_spaces": 100,
  "base_fee": 1000,
  "base_duration_minutes": 30,
  "extra_fee_per_unit": 200,
  "extra_fee_unit_minutes": 10,
  "daily_max_fee": 10000,
  "api_key": "a1b2c3d4e5f6...",
  "is_active": true,
  "created_at": "2026-05-08T10:00:00+09:00",
  "updated_at": "2026-05-08T10:00:00+09:00"
}
```

---

### `GET /admin/lots` — 주차장 목록

- **superadmin**: 전체 주차장 반환
- **admin**: 자신에게 배정된 주차장만 반환

**응답 (200)**
```json
[
  {
    "id": "uuid",
    "name": "본관 주차장",
    "address": "경북대학교 북문 앞",
    "total_spaces": 100,
    "available_spaces": 73,
    "base_fee": 1000,
    "base_duration_minutes": 30,
    "extra_fee_per_unit": 200,
    "extra_fee_unit_minutes": 10,
    "daily_max_fee": 10000,
    "api_key": "a1b2...xyz9",
    "is_active": true,
    "created_at": "2026-05-08T10:00:00+09:00",
    "updated_at": "2026-05-08T10:00:00+09:00"
  }
]
```

> `api_key`는 앞뒤 4자리만 표시된다 (`a1b2...xyz9`).

---

### `GET /admin/lots/{lot_id}` — 주차장 단건 조회

**응답 (200)** — `GET /admin/lots` 단일 항목과 동일

| 에러 | 원인 |
|------|------|
| `404 lot_not_found` | 존재하지 않는 lot_id |
| `403 forbidden` | admin이 타인의 주차장 조회 시도 |

---

### `PATCH /admin/lots/{lot_id}` — 주차장 정보 수정

수정할 필드만 포함하면 된다. `available_spaces`, `api_key`는 수정 불가.

**요청 (부분 업데이트 가능)**
```json
{
  "name": "수정된 주차장 이름",
  "base_fee": 2000,
  "is_active": false
}
```

**응답 (200)** — 수정된 주차장 정보 (`GET /admin/lots` 단일 항목과 동일)

| 에러 | 원인 |
|------|------|
| `400` | `total_spaces`를 현재 `available_spaces`보다 작게 설정 시도 |

---

### `DELETE /admin/lots/{lot_id}` — 주차장 비활성화 (superadmin 전용)

실제 삭제가 아닌 `is_active = false` 처리.

**응답 (204)** — 본문 없음

---

## 3. 관리자 계정

### `GET /admin/users` — 계정 목록 (superadmin 전용)

**응답 (200)**
```json
[
  {
    "id": "uuid",
    "username": "parkowner1",
    "email": "owner@example.com",
    "role": "admin",
    "parking_lot_id": "uuid 또는 null",
    "created_at": "2026-05-08T10:00:00+09:00"
  }
]
```

---

### `PATCH /admin/users/{user_id}` — 계정 수정

- **admin**: 본인 계정의 `email`, `password`만 수정 가능
- **superadmin**: 모든 계정 수정 + `parking_lot_id` 배정 가능

**요청**
```json
{
  "email": "new@example.com",
  "password": "newpassword",
  "parking_lot_id": "uuid"
}
```

> 수정할 필드만 포함하면 된다. `parking_lot_id`는 superadmin만 설정 가능.

**응답 (200)** — 수정된 계정 정보

---

## 4. 차량 현황

### `GET /admin/vehicles` — 현재 주차 중인 차량 목록

- **superadmin**: 전체 차량
- **admin**: 자신의 주차장 차량만

**응답 (200)**
```json
[
  {
    "id": "uuid",
    "parking_lot_id": "uuid",
    "plate": "12가3456",
    "entered_at": "2026-05-08T09:30:00+09:00"
  }
]
```

---

### `DELETE /admin/vehicles/{vehicle_id}` — 수동 출차 처리

카메라 오류 등 예외 상황에서 관리자가 강제 출차 처리.  
`available_spaces += 1` 및 `event_type='admin'`으로 로그 기록.

**응답 (204)** — 본문 없음

| 에러 | 원인 |
|------|------|
| `404 vehicle_not_found` | 존재하지 않는 vehicle_id |
| `403 forbidden` | admin이 타인 주차장 차량 처리 시도 |

---

## 5. 입출차 로그

### `GET /admin/logs` — 입출차 로그 조회

**쿼리 파라미터**

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `date_from` | date | 조회 시작일 (예: `2026-05-01`) |
| `date_to` | date | 조회 종료일 |
| `plate` | string | 번호판 검색 (완전 일치) |
| `limit` | int | 최대 반환 수 (기본 50, 최대 200) |
| `offset` | int | 페이지네이션 오프셋 (기본 0) |

**요청 예시**
```
GET /admin/logs?date_from=2026-05-01&date_to=2026-05-08&plate=12가3456&limit=20&offset=0
```

**응답 (200)**
```json
[
  {
    "id": "uuid",
    "parking_lot_id": "uuid",
    "plate": "12가3456",
    "event_type": "entry",
    "fee": null,
    "client_timestamp": "2026-05-08T09:30:00+09:00",
    "server_received_at": "2026-05-08T09:30:01+09:00"
  },
  {
    "id": "uuid",
    "parking_lot_id": "uuid",
    "plate": "12가3456",
    "event_type": "exit",
    "fee": 3000,
    "client_timestamp": "2026-05-08T11:00:00+09:00",
    "server_received_at": "2026-05-08T11:00:01+09:00"
  }
]
```

| 필드 | 설명 |
|------|------|
| `event_type` | `"entry"` (입차), `"exit"` (출차), `"admin"` (관리자 수동 출차) |
| `fee` | 출차 시에만 값 있음. 입차 및 admin 이벤트는 `null`일 수 있음 |
| `client_timestamp` | 실제 입출차 시각 (화면에 표시할 시각) |
| `server_received_at` | 서버 수신 시각 (디버깅용, 일반적으로 표시 불필요) |

---

## 6. Hub Server — 일반 사용자 주차장 현황 (미구현)

Hub Server가 구현되면 아래 API가 제공될 예정이다.  
FE는 이 API를 사용해 일반 사용자에게 주차장 현황 페이지를 구성한다.

### `GET /lots` — 주차장 목록 (예정)

```json
[
  {
    "id": "uuid",
    "name": "본관 주차장",
    "address": "경북대학교 북문 앞",
    "total_spaces": 100,
    "available_spaces": 73,
    "base_fee": 1000,
    "base_duration_minutes": 30,
    "extra_fee_per_unit": 200,
    "extra_fee_unit_minutes": 10,
    "daily_max_fee": 10000,
    "is_active": true,
    "last_synced_at": "2026-05-08T10:00:00+09:00"
  }
]
```

> `last_synced_at`이 현재 시각과 많이 차이나는 경우 "정보가 오래되었을 수 있습니다" 표시를 권장한다.

---

## Swagger UI

각 서버의 전체 API를 브라우저에서 직접 테스트할 수 있다.

| 서버 | Swagger 주소 |
|------|-------------|
| PLS | `http://localhost:8000/docs` |
| Hub | `http://localhost:8001/docs` (미구현) |
