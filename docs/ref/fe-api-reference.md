# FE API 레퍼런스

> 작성일: 2026-05-12
> 대상: 프론트엔드/백엔드 개발팀
> 기준: `/admin/*`, `superadmin`, `role` 구조를 제거하고, 일반 사용자가 본인 소유 주차장만 관리하는 구조로 재정리

---

## 0. 변경 요약

### 기존 구조

* `/auth/signup`, `/admin/login`, `/admin/lots`, `/admin/vehicles`, `/admin/logs` 중심
* `admin` / `superadmin` 권한 분리
* `superadmin`이 주차장을 생성하고 `admin`에게 주차장을 배정

### 변경 구조

* API prefix를 `/api/v1`로 통일
* `/admin` 경로 제거
* `superadmin` 역할 제거
* `role` 필드 제거
* 계정은 일반 사용자 계정으로 통일
* 로그인한 사용자가 직접 주차장을 생성, 조회, 수정, 삭제
* 주차장 수정/삭제/차량/로그 조회는 **본인이 소유한 주차장만 가능**
* 주차장 삭제는 **hard delete**로 처리
* 회원가입 API는 환경변수로 활성화 여부를 제어

---

## 1. 서버 구성

| 서버                           | 역할              | 로컬 주소                   |
| ---------------------------- | --------------- | ----------------------- |
| **Parking Lot Server (PLS)** | 주차장 소유자용 관리 API | `http://localhost:8000` |

### Base URL

```text
http://localhost:8000/api/v1
```

> `/api/v1//signup`, `/api/v1//login`처럼 이중 슬래시를 사용하지 않는다.
> 모든 API는 `/api/v1/signup`, `/api/v1/login`처럼 단일 슬래시 경로를 사용한다.

---

## 2. 공통 정책

### 인증

`/signup`, `/login`을 제외한 모든 API는 JWT Bearer 토큰이 필요하다.

```http
Authorization: Bearer {access_token}
```

로그인 성공 시 발급받은 `access_token`을 사용한다.

### 회원가입 활성화 정책

회원가입 API는 환경변수로 활성화 여부를 제어한다.

| 환경변수            | 값       | 설명                          |
| --------------- | ------- | --------------------------- |
| `ENABLE_SIGNUP` | `true`  | `POST /api/v1/signup` 사용 가능 |
| `ENABLE_SIGNUP` | `false` | `POST /api/v1/signup` 사용 불가 |

운영 방식은 아래를 기준으로 한다.

| 환경      | 회원가입 노출 | 권장 설정                 |
| ------- | ------- | --------------------- |
| Public  | 비공개     | `ENABLE_SIGNUP=false` |
| Private | 공개 가능   | `ENABLE_SIGNUP=true`  |

`ENABLE_SIGNUP=false` 상태에서 회원가입 요청이 들어오면 아래 에러를 반환한다.

```json
{ "detail": "signup_disabled" }
```

### 권한 정책

| 리소스                                           | 권한                      |
| --------------------------------------------- | ----------------------- |
| `POST /lots`                                  | 로그인한 사용자 누구나 생성 가능      |
| `GET /lots`                                   | 본인이 생성한 주차장 목록만 조회 가능   |
| `GET /lots/{lot_id}`                          | 본인 소유 주차장만 조회 가능        |
| `PATCH /lots/{lot_id}`                        | 본인 소유 주차장만 수정 가능        |
| `DELETE /lots/{lot_id}`                       | 본인 소유 주차장만 삭제 가능        |
| `GET /lots/{lot_id}/vehicles`                 | 본인 소유 주차장의 현재 차량만 조회 가능 |
| `DELETE /lots/{lot_id}/vehicles/{vehicle_id}` | 본인 소유 주차장의 차량만 수동 출차 가능 |
| `GET /lots/{lot_id}/logs`                     | 본인 소유 주차장의 로그만 조회 가능    |

### 소유권 검증 기준

각 주차장에는 소유자 식별자가 저장된다.

```text
lot.owner_user_id == current_user.id
```

위 조건을 만족하지 않으면 `403 forbidden`을 반환한다.

### 에러 응답 형식

```json
{ "detail": "에러_코드" }
```

| HTTP 상태 | 의미                    |
| ------- | --------------------- |
| 400     | 잘못된 요청                |
| 401     | 인증 실패 또는 토큰 만료        |
| 403     | 권한 없음 또는 타인 소유 리소스 접근 |
| 404     | 리소스 없음                |
| 409     | 중복 리소스                |

---

## 3. 인증

## `POST /api/v1/signup` — 회원가입

주차장 소유자 계정을 생성한다.

인증은 필요하지 않다.

단, `ENABLE_SIGNUP=false`인 환경에서는 사용할 수 없다.

### 요청

```json
{
  "username": "parkowner1",
  "email": "owner@example.com",
  "password": "password123"
}
```

### 요청 필드

| 필드         | 타입     | 필수 | 설명             |
| ---------- | ------ | -- | -------------- |
| `username` | string | ✅  | 로그인 ID. 고유해야 함 |
| `email`    | string | ✅  | 사용자 이메일        |
| `password` | string | ✅  | 비밀번호           |

### 응답 `201 Created`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "parkowner1",
  "email": "owner@example.com",
  "created_at": "2026-05-12T10:00:00+09:00"
}
```

### 에러

| 상태  | 에러 코드                     | 원인                |
| --- | ------------------------- | ----------------- |
| 403 | `signup_disabled`         | 회원가입이 비활성화된 환경    |
| 409 | `username_already_exists` | 이미 사용 중인 username |
| 409 | `email_already_exists`    | 이미 사용 중인 email    |

---

## `POST /api/v1/login` — 로그인

인증은 필요하지 않다.

### 요청

```json
{
  "username": "parkowner1",
  "password": "password123"
}
```

### 응답 `200 OK`

```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer"
}
```

토큰 유효 시간은 기존 정책과 동일하게 **8시간**으로 유지한다. 만료 시 `401`이 반환되므로 클라이언트는 재로그인 처리를 해야 한다.

### 에러

| 상태  | 에러 코드                 | 원인              |
| --- | --------------------- | --------------- |
| 401 | `invalid_credentials` | 아이디 또는 비밀번호 불일치 |

---

## 4. 주차장 관리

## `POST /api/v1/lots` — 주차장 생성

로그인한 사용자가 새 주차장을 생성한다.

생성된 주차장의 `owner_user_id`는 현재 로그인한 사용자 ID로 자동 저장된다.

### 요청

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

### 요청 필드

| 필드                       | 타입         | 필수 | 설명                       |
| ------------------------ | ---------- | -- | ------------------------ |
| `name`                   | string     | ✅  | 주차장 이름                   |
| `address`                | string     |    | 주소                       |
| `total_spaces`           | int        | ✅  | 전체 주차면 수. 양수             |
| `base_fee`               | int        |    | 기본 요금. 기본값 `0`           |
| `base_duration_minutes`  | int        |    | 기본 요금 적용 시간. 기본값 `0`     |
| `extra_fee_per_unit`     | int        |    | 추가 요금. 기본값 `0`           |
| `extra_fee_unit_minutes` | int        |    | 추가 요금 단위 시간. 기본값 `10`    |
| `daily_max_fee`          | int | null |    | 일일 최대 요금. `null`이면 상한 없음 |

### 응답 `201 Created`

`api_key`는 최초 생성 시에만 원문으로 반환한다.

```json
{
  "id": "uuid",
  "owner_user_id": "550e8400-e29b-41d4-a716-446655440000",
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
  "created_at": "2026-05-12T10:00:00+09:00",
  "updated_at": "2026-05-12T10:00:00+09:00"
}
```

### 에러

| 상태  | 에러 코드                  | 원인                   |
| --- | ---------------------- | -------------------- |
| 400 | `invalid_total_spaces` | `total_spaces`가 0 이하 |
| 401 | `unauthorized`         | 인증 토큰 없음 또는 만료       |

---

## `GET /api/v1/lots` — 내 주차장 목록 조회

현재 로그인한 사용자가 소유한 주차장 목록만 반환한다.

### 응답 `200 OK`

```json
[
  {
    "id": "uuid",
    "owner_user_id": "550e8400-e29b-41d4-a716-446655440000",
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
    "created_at": "2026-05-12T10:00:00+09:00",
    "updated_at": "2026-05-12T10:00:00+09:00"
  }
]
```

> 목록/단건 조회에서 `api_key`는 보안상 앞뒤 4자리만 표시한다.

---

## `GET /api/v1/lots/{lot_id}` — 내 주차장 단건 조회

현재 로그인한 사용자가 소유한 주차장만 조회할 수 있다.

### 응답 `200 OK`

```json
{
  "id": "uuid",
  "owner_user_id": "550e8400-e29b-41d4-a716-446655440000",
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
  "created_at": "2026-05-12T10:00:00+09:00",
  "updated_at": "2026-05-12T10:00:00+09:00"
}
```

### 에러

| 상태  | 에러 코드           | 원인           |
| --- | --------------- | ------------ |
| 403 | `forbidden`     | 타인 소유 주차장 접근 |
| 404 | `lot_not_found` | 존재하지 않는 주차장  |

---

## `PATCH /api/v1/lots/{lot_id}` — 내 주차장 정보 수정

현재 로그인한 사용자가 소유한 주차장만 수정할 수 있다.

수정할 필드만 포함하면 된다.

`available_spaces`, `api_key`, `owner_user_id`는 직접 수정할 수 없다.

### 요청

```json
{
  "name": "수정된 주차장 이름",
  "base_fee": 2000,
  "is_active": false
}
```

### 수정 가능 필드

| 필드                       | 타입         | 설명          |
| ------------------------ | ---------- | ----------- |
| `name`                   | string     | 주차장 이름      |
| `address`                | string     | 주소          |
| `total_spaces`           | int        | 전체 주차면 수    |
| `base_fee`               | int        | 기본 요금       |
| `base_duration_minutes`  | int        | 기본 요금 적용 시간 |
| `extra_fee_per_unit`     | int        | 추가 요금       |
| `extra_fee_unit_minutes` | int        | 추가 요금 단위 시간 |
| `daily_max_fee`          | int | null | 일일 최대 요금    |
| `is_active`              | boolean    | 주차장 활성 여부   |

### 응답 `200 OK`

수정된 주차장 정보를 반환한다.

```json
{
  "id": "uuid",
  "owner_user_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "수정된 주차장 이름",
  "address": "경북대학교 북문 앞",
  "total_spaces": 100,
  "available_spaces": 73,
  "base_fee": 2000,
  "base_duration_minutes": 30,
  "extra_fee_per_unit": 200,
  "extra_fee_unit_minutes": 10,
  "daily_max_fee": 10000,
  "api_key": "a1b2...xyz9",
  "is_active": false,
  "created_at": "2026-05-12T10:00:00+09:00",
  "updated_at": "2026-05-12T11:00:00+09:00"
}
```

### 에러

| 상태  | 에러 코드                  | 원인                                       |
| --- | ---------------------- | ---------------------------------------- |
| 400 | `invalid_total_spaces` | `total_spaces`를 현재 주차 중인 차량 수보다 작게 설정 시도 |
| 403 | `forbidden`            | 타인 소유 주차장 수정 시도                          |
| 404 | `lot_not_found`        | 존재하지 않는 주차장                              |

---

## `DELETE /api/v1/lots/{lot_id}` — 내 주차장 삭제

현재 로그인한 사용자가 소유한 주차장만 삭제할 수 있다.

삭제 정책은 **hard delete**로 정의한다.

### 처리 방식

* `{lot_id}`가 존재하는지 확인
* `{lot_id}`가 현재 로그인한 사용자의 소유인지 확인
* 주차장 데이터를 실제 삭제
* 관련 차량/로그/API key 등 연관 데이터 처리 방식은 DB 관계 정책에 따른다

> 구현 시 FK 제약 조건 때문에 삭제가 실패하지 않도록, 연관 데이터 cascade delete 또는 사전 삭제 정책을 명확히 설정해야 한다.

### 응답 `204 No Content`

본문 없음.

### 에러

| 상태  | 에러 코드           | 원인              |
| --- | --------------- | --------------- |
| 403 | `forbidden`     | 타인 소유 주차장 삭제 시도 |
| 404 | `lot_not_found` | 존재하지 않는 주차장     |

---

## 5. 차량 현황

## `GET /api/v1/lots/{lot_id}/vehicles` — 현재 주차 중인 차량 목록 조회

현재 로그인한 사용자가 소유한 주차장의 현재 주차 차량만 조회한다.

### 응답 `200 OK`

```json
[
  {
    "id": "uuid",
    "parking_lot_id": "uuid",
    "plate": "12가3456",
    "entered_at": "2026-05-12T09:30:00+09:00"
  }
]
```

### 에러

| 상태  | 에러 코드           | 원인                 |
| --- | --------------- | ------------------ |
| 403 | `forbidden`     | 타인 소유 주차장 차량 조회 시도 |
| 404 | `lot_not_found` | 존재하지 않는 주차장        |

---

## `DELETE /api/v1/lots/{lot_id}/vehicles/{vehicle_id}` — 차량 수동 출차 처리

카메라 오류 등 예외 상황에서 소유자가 차량을 강제 출차 처리한다.

### 요청 예시

```http
DELETE /api/v1/lots/{lot_id}/vehicles/{vehicle_id}
```

### Path Parameters

| 파라미터         | 타입     | 필수 | 설명           |
| ------------ | ------ | -- | ------------ |
| `lot_id`     | string | ✅  | 주차장 ID       |
| `vehicle_id` | string | ✅  | 출차 처리할 차량 ID |

### 처리 방식

* `{lot_id}`가 현재 로그인한 사용자의 소유인지 확인
* `{vehicle_id}` 차량이 존재하는지 확인
* 해당 차량이 현재 주차 중인지 확인
* 해당 차량이 `{lot_id}`에 속하는지 확인
* 차량을 현재 주차 목록에서 제거
* `available_spaces += 1`
* `event_type = "admin"` 로그 기록

### 응답 `204 No Content`

본문 없음.

### 에러

| 상태  | 에러 코드               | 원인                 |
| --- | ------------------- | ------------------ |
| 403 | `forbidden`         | 타인 소유 주차장 차량 처리 시도 |
| 404 | `lot_not_found`     | 존재하지 않는 주차장        |
| 404 | `vehicle_not_found` | 존재하지 않거나 이미 출차된 차량 |

---

## 6. 입출차 로그

## `GET /api/v1/lots/{lot_id}/logs` — 내 주차장 입출차 로그 조회

현재 로그인한 사용자가 소유한 주차장의 입출차 로그만 조회한다.

### 쿼리 파라미터

| 파라미터         | 타입     | 설명                            |
| ------------ | ------ | ----------------------------- |
| `date_from`  | date   | 조회 시작일. 예: `2026-05-01`       |
| `date_to`    | date   | 조회 종료일. 예: `2026-05-12`       |
| `plate`      | string | 번호판 검색. 완전 일치                 |
| `event_type` | string | `entry`, `exit`, `admin` 중 하나 |
| `limit`      | int    | 최대 반환 수. 기본 `50`, 최대 `200`    |
| `offset`     | int    | 페이지네이션 오프셋. 기본 `0`            |

### 요청 예시

```http
GET /api/v1/lots/{lot_id}/logs?date_from=2026-05-01&date_to=2026-05-12&plate=12가3456&limit=20&offset=0
```

### 응답 `200 OK`

```json
[
  {
    "id": "uuid",
    "parking_lot_id": "uuid",
    "plate": "12가3456",
    "event_type": "entry",
    "fee": null,
    "client_timestamp": "2026-05-12T09:30:00+09:00",
    "server_received_at": "2026-05-12T09:30:01+09:00"
  },
  {
    "id": "uuid",
    "parking_lot_id": "uuid",
    "plate": "12가3456",
    "event_type": "exit",
    "fee": 3000,
    "client_timestamp": "2026-05-12T11:00:00+09:00",
    "server_received_at": "2026-05-12T11:00:01+09:00"
  }
]
```

### 응답 필드

| 필드                   | 설명                                              |
| -------------------- | ----------------------------------------------- |
| `event_type`         | `entry`: 입차, `exit`: 출차, `admin`: 관리자/소유자 수동 출차 |
| `fee`                | 출차 시 요금. 입차 및 수동 출차 이벤트는 `null` 가능              |
| `client_timestamp`   | 실제 입출차 시각. 화면 표시 기준                             |
| `server_received_at` | 서버 수신 시각. 디버깅용                                  |

### 에러

| 상태  | 에러 코드           | 원인                 |
| --- | --------------- | ------------------ |
| 403 | `forbidden`     | 타인 소유 주차장 로그 조회 시도 |
| 404 | `lot_not_found` | 존재하지 않는 주차장        |

---

## 7. 최종 API 목록

| Method | Path                                          | 인증  | 설명             |
| ------ | --------------------------------------------- | --- | -------------- |
| POST   | `/api/v1/signup`                              | 불필요 | 회원가입           |
| POST   | `/api/v1/login`                               | 불필요 | 로그인            |
| POST   | `/api/v1/lots`                                | 필요  | 내 주차장 생성       |
| GET    | `/api/v1/lots`                                | 필요  | 내 주차장 목록 조회    |
| GET    | `/api/v1/lots/{lot_id}`                       | 필요  | 내 주차장 단건 조회    |
| PATCH  | `/api/v1/lots/{lot_id}`                       | 필요  | 내 주차장 정보 수정    |
| DELETE | `/api/v1/lots/{lot_id}`                       | 필요  | 내 주차장 삭제       |
| GET    | `/api/v1/lots/{lot_id}/vehicles`              | 필요  | 현재 주차 중인 차량 조회 |
| DELETE | `/api/v1/lots/{lot_id}/vehicles/{vehicle_id}` | 필요  | 차량 수동 출차 처리    |
| GET    | `/api/v1/lots/{lot_id}/logs`                  | 필요  | 입출차 로그 조회      |

---

## 8. Swagger UI

| 서버  | Swagger 주소                   |
| --- | ---------------------------- |
| PLS | `http://localhost:8000/docs` |
