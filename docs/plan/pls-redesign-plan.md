# Parking Lot Server 재설계 계획

> 작성일: 2026-05-13  
> 배경: FE 팀 피드백 반영 — `docs/ref/fe-api-reference.md` 기준  
> 참고: `docs/plan/parking-lot-server-plan.md` (기존 계획)

---

## 재설계 배경

FE 팀과의 협의를 통해 아래 두 가지를 결정했다.

1. **superadmin을 코드에서 제거한다.** 최고 관리자 계정은 외부 프로그램(SQL, DB 클라이언트 등)으로 직접 DB에 주입하는 방식을 사용한다. 코드로 관리할 필요가 없다.
2. **API 구조를 FE 요구사항 기준으로 전면 재설계한다.** 주요 변경은 아래와 같다.

---

## 변경 요약

| 항목 | 기존 | 변경 |
|------|------|------|
| API prefix | `/auth/*`, `/admin/*` 혼재 | `/api/v1/*` 통일 |
| 권한 모델 | `superadmin` / `admin` role 기반 | `owner_user_id` 소유권 기반 |
| 주차장 생성 | superadmin 전용 | 로그인한 사용자 누구나 |
| 주차장 삭제 | soft delete (`is_active=false`) | hard delete |
| 차량·로그 경로 | `/admin/vehicles`, `/admin/logs` | `/api/v1/lots/{lot_id}/vehicles`, `…/logs` |
| 회원가입 | 항상 열림 | `ENABLE_SIGNUP` 환경변수로 제어 |
| 최고 관리자 생성 | `seed.py` 스크립트 | 직접 DB 주입 (SQL) |
| Private/Public 구분 | `MODE` 환경변수 | `ENABLE_SIGNUP` 환경변수 |

---

## 새 API 구조

```
POST   /api/v1/signup                                # 회원가입 (ENABLE_SIGNUP=true 시만)
POST   /api/v1/login                                 # 로그인

POST   /api/v1/lots                                  # 주차장 생성
GET    /api/v1/lots                                  # 내 주차장 목록
GET    /api/v1/lots/{lot_id}                         # 내 주차장 단건
PATCH  /api/v1/lots/{lot_id}                         # 내 주차장 수정
DELETE /api/v1/lots/{lot_id}                         # 내 주차장 삭제 (hard delete)

GET    /api/v1/lots/{lot_id}/vehicles                # 현재 주차 중인 차량
DELETE /api/v1/lots/{lot_id}/vehicles/{vehicle_id}   # 차량 수동 출차

GET    /api/v1/lots/{lot_id}/logs                    # 입출차 로그
```

> 기존 `/api/v1/plates` (카메라 클라이언트용)와 `/public/status/{lot_id}` (Hub 폴링용)는 변경 없이 유지.

---

## 권한 모델 변경

### 기존: role 기반

```
superadmin → 전체 접근
admin      → 배정된 주차장만 접근
```

### 변경: 소유권 기반

```python
# 모든 주차장 관련 엔드포인트에서 소유권 검증
lot.owner_user_id == current_user.id
```

- 주차장 생성 시 `owner_user_id = current_user.id` 자동 저장
- 소유권 불일치 시 `403 forbidden`

---

## DB 스키마 변경

### `users` 테이블

| 변경 | 내용 |
|------|------|
| `role` 컬럼 제거 | superadmin/admin 구분 불필요 |
| `parking_lot_id` 컬럼 제거 | 소유권은 `parking_lots.owner_user_id`로 역방향 관리 |

```sql
-- 변경 후
CREATE TABLE users (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    username       VARCHAR(50) UNIQUE NOT NULL,
    email          VARCHAR(100) UNIQUE NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `parking_lots` 테이블

| 변경 | 내용 |
|------|------|
| `owner_user_id` 컬럼 추가 | 주차장 소유자 식별자 |

```sql
owner_user_id UUID NOT NULL REFERENCES users(id)
```

### 연관 데이터 cascade 정책 (hard delete 대응)

`DELETE /api/v1/lots/{lot_id}` 시 연관 데이터 처리:

| 테이블 | 정책 |
|--------|------|
| `vehicles` | CASCADE DELETE |
| `entry_exit_logs` | CASCADE DELETE 또는 `parking_lot_id` SET NULL 검토 |

---

## 수정 파일 목록

### DB / 마이그레이션
- `app/models/user.py` — `role`, `parking_lot_id` 컬럼 제거
- `app/models/parking_lot.py` — `owner_user_id` FK 추가
- `app/models/vehicles.py`, `app/models/entry_exit_log.py` — cascade 설정
- Alembic 마이그레이션 파일 추가
- `docs/schema-history/` — 새 버전 문서

### Pydantic 스키마
- `app/schemas/auth.py` — `SignupRequest` 유지, `SignupResponse`에서 `role` 제거
- `app/schemas/user.py` — `role`, `parking_lot_id` 제거
- `app/schemas/lot.py` — `LotOut`에 `owner_user_id` 추가

### 라우터 (전면 재구성)
- `app/routers/auth.py` (신규) — `/api/v1/signup`, `/api/v1/login`
- `app/routers/lots.py` (신규) — 주차장 CRUD + 차량 + 로그 중첩
- `app/routers/admin/` 폴더 전체 제거

### 의존성
- `app/dependencies/jwt_auth.py` — `require_superadmin`, role 관련 제거. 소유권 검증 헬퍼로 대체

### Private / Public 구분

`ENABLE_SIGNUP`이 Private/Public의 실질적 구분 기준이다.  
`MODE`는 Hub 연동 여부를 제어하는 별개 설정이다.

| 배포 유형 | `ENABLE_SIGNUP` | `MODE` |
|----------|-----------------|--------|
| Private | `true` | `private` |
| Public | `false` | `public` |

Public 환경에서 최초 계정은 SQL로 직접 주입한다 (`scripts/seed.sql` 참고).

### 설정 / 인프라
- `app/config.py` — `ENABLE_SIGNUP: bool = True` 추가
- `app/main.py` — 라우터 재구성
- `.env.example` — `ENABLE_SIGNUP=true` 추가
- `scripts/seed.py` — 제거 또는 SQL 예시 파일로 대체

### 테스트
- `tests/conftest.py` — superadmin/admin 픽스처 제거, owner 기반 픽스처로 교체
- `tests/routers/test_auth.py` — signup/login 경로 변경
- `tests/routers/test_lots.py` — 소유권 기반으로 전면 재작성
- `tests/routers/test_vehicles.py` — 경로 변경 및 소유권 검증 추가
- `tests/routers/test_logs.py` — 경로 변경 및 소유권 검증 추가
- `tests/routers/test_users.py` — 제거

### 문서
- `docs/plan/parking-lot-server-plan.md` — 업데이트
- `docs/plan/hub-parking-lot-integration-plan.md` — superadmin 관련 흐름 수정
- `docs/plan/hub-server-plan.md` — PLS API 경로 변경 반영

---

## 구현 순서

| 단계 | 작업 |
|------|------|
| 1 | DB 모델 변경 + Alembic 마이그레이션 |
| 2 | `app/schemas/` 수정 |
| 3 | `app/dependencies/` 소유권 검증 헬퍼 구현 |
| 4 | `app/routers/auth.py` — signup, login |
| 5 | `app/routers/lots.py` — CRUD + 차량 + 로그 |
| 6 | `app/main.py` 라우터 재구성 |
| 7 | 테스트 전면 재작성 |
| 8 | Hub 연동 엔드포인트 (`/public/status`, Hub push) 경로 유지 확인 |

---

## 유지되는 것

변경 없이 그대로 사용하는 엔드포인트:

| 엔드포인트 | 이유 |
|-----------|------|
| `POST /api/v1/plates` | 카메라 클라이언트용. FE 범위 밖 |
| `GET /public/status/{lot_id}` | Hub 폴링용. FE 범위 밖 |

서비스 레이어도 변경 없음:

| 파일 | 이유 |
|------|------|
| `app/services/crypto.py` | 번호판 암호화 로직 변경 없음 |
| `app/services/fee.py` | 요금 계산 로직 변경 없음 |
| `app/services/hub.py` | Hub push 로직 변경 없음 |
