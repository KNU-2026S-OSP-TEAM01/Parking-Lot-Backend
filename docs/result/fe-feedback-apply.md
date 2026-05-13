# FE 피드백 반영 작업 결과

> 작성일: 2026-05-13  
> 브랜치: `feat/fe_feedback_apply`  
> 참고: `docs/plan/pls-redesign-plan.md`, `docs/ref/fe-api-reference.md`

---

## 배경

FE 팀과의 협의를 통해 아래 두 가지를 결정하여 PLS를 재설계했다.

1. **superadmin 코드 제거**: 최고 관리자 계정은 SQL로 DB에 직접 주입. 코드로 관리하지 않는다.
2. **API 구조 전면 변경**: FE 요구사항 기준으로 권한 모델·경로·삭제 정책을 재설계했다.

---

## 변경 내용

### 권한 모델

| 항목 | 기존 | 변경 |
|------|------|------|
| 권한 기준 | `role` (superadmin / admin) | `owner_user_id` (소유권) |
| 주차장 생성 | superadmin 전용 | 로그인한 누구나 |
| 주차장 조회 | role에 따라 전체 / 일부 | 본인 소유 주차장만 |
| 수정 / 삭제 | role 체크 | 소유자 여부 체크 |

### API 경로

| 항목 | 기존 | 변경 |
|------|------|------|
| prefix | `/auth/*`, `/admin/*` 혼재 | `/api/v1/*` 통일 |
| 차량 목록 | `GET /admin/vehicles` | `GET /api/v1/lots/{lot_id}/vehicles` |
| 입출차 로그 | `GET /admin/logs` | `GET /api/v1/lots/{lot_id}/logs` |
| 주차장 삭제 | soft delete (`is_active=false`) | hard delete |

### 전체 API 목록

| Method | Path | 인증 | 설명 |
|--------|------|------|------|
| POST | `/api/v1/signup` | 없음 | 회원가입 (`ENABLE_SIGNUP` 제어) |
| POST | `/api/v1/login` | 없음 | 로그인 → JWT |
| POST | `/api/v1/lots` | 필요 | 주차장 생성 |
| GET | `/api/v1/lots` | 필요 | 내 주차장 목록 |
| GET | `/api/v1/lots/{lot_id}` | 필요 | 내 주차장 단건 |
| PATCH | `/api/v1/lots/{lot_id}` | 필요 | 내 주차장 수정 |
| DELETE | `/api/v1/lots/{lot_id}` | 필요 | 내 주차장 삭제 (hard delete) |
| GET | `/api/v1/lots/{lot_id}/vehicles` | 필요 | 현재 주차 차량 |
| DELETE | `/api/v1/lots/{lot_id}/vehicles/{vehicle_id}` | 필요 | 차량 수동 출차 |
| GET | `/api/v1/lots/{lot_id}/logs` | 필요 | 입출차 로그 |

> 카메라용 `POST /api/v1/plates`, Hub 폴링용 `GET /public/status/{lot_id}`는 변경 없이 유지.

### DB 스키마 변경 (v4)

| 테이블 | 변경 내용 |
|--------|----------|
| `users` | `role`, `parking_lot_id` 컬럼 제거 |
| `parking_lots` | `owner_user_id` FK 추가 (NOT NULL) |
| `vehicles` | `parking_lot_id` FK에 `ON DELETE CASCADE` 추가 |
| `entry_exit_logs` | `parking_lot_id` FK에 `ON DELETE CASCADE` 추가 |

> 상세 DDL: `docs/schema-history/database-schema-v4.md`

### 삭제된 것

| 항목 | 이유 |
|------|------|
| `app/routers/admin/` 디렉토리 전체 | `/api/v1/*` 구조로 통합 |
| `app/schemas/user.py` | `UserOut`이 `SignupResponse`로 대체 |
| `scripts/seed.py` | role 제거로 broken → `scripts/seed.sql`로 교체 |
| `tests/routers/test_users.py` | 사용자 관리 API 제거에 따라 삭제 |

---

## 구조 변화

### 코드 구조

```
app/routers/
  auth.py          ← 신규: /api/v1/signup, /api/v1/login
  lots.py          ← 신규: /api/v1/lots/* (차량·로그 포함)
  plates.py        ← 유지
  public/status.py ← 유지 (Hub 폴링용)
  admin/           ← 삭제
```

### 의존성 구조

```
기존: JWT → role 확인 → superadmin/admin 분기
변경: JWT → sub(user_id) 추출 → lot.owner_user_id 비교
```

```python
# jwt_auth.py
async def get_owned_lot(lot_id, current_user, db) -> ParkingLot:
    lot = DB에서 lot 조회
    if lot.owner_user_id != current_user["sub"]:
        raise 403
    return lot
```

### 환경변수 추가

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ENABLE_SIGNUP` | `true` | `false`이면 회원가입 API 비활성화 (403 반환) |

---

## 테스트

### 테스트 전략 (변경 없음)

- pytest + `ASGITransport` (실제 HTTP 미사용, 인-프로세스)
- 테스트 DB 분리 (포트 5433) — 개발 DB 오염 없음
- 트랜잭션 롤백으로 테스트 간 격리

### 픽스처 변화

| 기존 픽스처 | 변경 |
|------------|------|
| `superadmin`, `superadmin_token` | 제거 |
| `admin`, `admin_token` | 제거 |
| `lot` (superadmin 소유) | `user` + `lot` (user 소유)로 대체 |
| — | `other_user`, `other_token` 추가 (소유권 침범 테스트용) |

### 주요 테스트 케이스

- 소유권 검증: 타인 소유 주차장 접근 시 403
- hard delete: 삭제 후 DB에서 실제 제거 확인
- `total_spaces` 수정: 현재 주차 중인 차량 수 기준 400 검증
- `ENABLE_SIGNUP=false`: 회원가입 시 403 반환

### 결과

```
77 passed, 커버리지 71%
```

---

## 남은 작업

| 항목 | 상태 |
|------|------|
| Hub Server 구현 | ⬜ 별도 리포지토리 |
| Hub 연동 로컬 테스트 | ⬜ Hub 구현 후 |
| `scripts/seed.sql` 실제 해시값 입력 | ⬜ 배포 시 |
