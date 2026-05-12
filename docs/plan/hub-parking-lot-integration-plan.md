# Hub Server ↔ Parking Lot Server 연동 계획

> 작성일: 2026-05-08  
> 대상 리포지토리: Hub Server, Parking Lot Server (공용 문서)

---

## 개요

이 문서는 Hub Server와 Parking Lot Server 간 연동을 위한 계획을 설명한다.  
두 서버는 별도 리포지토리에서 개발되며, 이 문서를 기준으로 인터페이스를 맞춘다.

### 각 서버의 역할

| 서버 | 역할 |
|------|------|
| **Parking Lot Server (PLS)** | 주차장·사용자 관리, 입출차 처리. Public 모드에서 Hub에 현황 제공 |
| **Hub Server** | 여러 주차장 현황을 통합해 외부 사용자에게 제공 |

---

## 설계 전제 및 원칙

> **현재 프로토타입 가정: Hub Server 1개, Public PLS 1개.**  
> 추후 PLS가 여러 개로 확장될 경우 Hub의 lot 등록 엔드포인트에 API 키 인증이 필요할 수 있다.

- **Hub와 PLS는 서로의 API 키를 보유하지 않는다.** (단일 PLS 가정 하에 불필요)
- PLS는 `HUB_URL` 환경변수를 가지며, Public 모드에서만 사용한다.
- Hub는 lot별로 `pl_server_url`과 `pl_lot_id`를 DB에 저장한다. (`pl_api_key`는 미사용)
- **Private PLS는 `HUB_URL` 없이도 완전히 동작한다.** Hub 관련 로직은 Public 모드에서만 실행된다.

---

## Private / Public 모드 동작 비교

| 기능 | Private | Public |
|------|---------|--------|
| 입출차 처리 | ✅ | ✅ |
| 관리자 API | ✅ | ✅ |
| Hub에 lot push (등록/비활성화) | ❌ 실행 안 함 | ✅ |
| `GET /public/status/{lot_id}` | ❌ 미노출 | ✅ |
| `HUB_URL` 필요 | ❌ | ✅ |

---

## 주차장 등록 흐름

```
1. 주차장 주인    → PLS에 회원가입 (POST /auth/signup)
                    role='admin', parking_lot_id=NULL 상태로 등록

2. 주차장 주인    → superadmin에게 주차장 등록 요청 (오프라인)

3. superadmin     → POST /admin/lots on PLS (JWT 인증)
                    주차장 생성, lot_id + 카메라 api_key 반환

         [Private 모드] → 여기서 종료
         [Public 모드]  → PLS가 Hub에 lot 정보 push

4. PLS (Public)   → POST {HUB_URL}/lots (인증 없음)
                    lot 생성 실패 시 Hub push도 롤백 (원자적 처리)

5. Hub            → lots DB에 등록

6. superadmin     → PATCH /admin/users/{user_id} on PLS (JWT 인증)
                    parking_lot_id 연결 (현재 UserPatch에 구현 필요)

7. 주차장 주인    → PLS 로그인 → GET /admin/lots
                    카메라 api_key 확인 후 카메라에 설정
```

---

## 주차장 비활성화 흐름

```
superadmin        → DELETE /admin/lots/{lot_id} on PLS (JWT 인증)
                    is_active = false 처리

         [Private 모드] → 여기서 종료
         [Public 모드]  → PLS가 Hub에 비활성화 알림

PLS (Public)      → PATCH {HUB_URL}/lots/{lot_id} (인증 없음)
                    { is_active: false }

Hub               → lots.is_active = false 업데이트
                    다음 폴링 사이클에서 해당 lot 제외
```

---

## 현황 폴링 흐름

Hub Server는 `is_active=true`인 `parking_lot_server` 타입 주차장을 주기적으로 폴링한다.  
폴링 엔드포인트는 인증이 필요 없다.

```
Hub Server                        Parking Lot Server (Public Mode)
    │                                       │
    │  GET /public/status/{pl_lot_id}       │
    │───────────────────────────────────────►│
    │                                       │
    │◄───────────────────────────────────────│
    │  { available_spaces, total_spaces, ...}│
    │                                       │
    │ lots.available_spaces 업데이트        │
    │ lots.last_synced_at = synced_at       │
```

---

## Parking Lot Server 구현 사항

### 1. 환경변수

```env
# Public 모드에서만 필요
HUB_URL=http://localhost:8001   # Hub Server 베이스 URL
```

`config.py`:
```python
hub_url: str | None = None
```

### 2. `POST /admin/lots` — Public 모드 시 Hub push (원자적 처리)

lot 생성과 Hub push를 하나의 트랜잭션으로 묶는다.  
Hub push 실패 시 lot 생성도 롤백하고 `503`을 반환한다.

```python
async def create_lot(...):
    lot = 주차장 생성()

    if settings.mode == "public" and settings.hub_url:
        await notify_hub(lot)    # 실패 시 HTTPException → 트랜잭션 롤백

    return lot
```

### 3. `DELETE /admin/lots/{lot_id}` — Public 모드 시 Hub 비활성화 알림

```python
async def deactivate_lot(...):
    lot.is_active = False

    if settings.mode == "public" and settings.hub_url:
        await notify_hub_deactivate(lot.id)   # PATCH {HUB_URL}/lots/{lot_id}
```

### 4. `PATCH /admin/users/{user_id}` — `parking_lot_id` 배정

현재 `UserPatch` 스키마에 `parking_lot_id` 필드가 없어 구현이 필요하다.  
superadmin이 이 엔드포인트로 주차장 주인과 lot을 연결한다.

### 5. `GET /public/status/{lot_id}` — 인증 없는 공개 엔드포인트

`MODE=public`일 때만 마운트된다.

#### 요청
```
GET /public/status/{lot_id}
(인증 헤더 없음)
```

#### 응답 (200 OK)

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
  "daily_max_fee": 10000,
  "is_active": true,
  "synced_at": "2026-05-08T10:00:00+09:00"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `lot_id` | UUID | PLS 내 주차장 식별자 |
| `name` | string | 주차장 이름 |
| `address` | string \| null | 주소 |
| `total_spaces` | int | 전체 면수 |
| `available_spaces` | int | 현재 잔여 면수 |
| `base_fee` | int | 기본 요금 (원) |
| `base_duration_minutes` | int | 기본 요금 적용 시간 (분) |
| `extra_fee_per_unit` | int | 단위 추가 요금 (원) |
| `extra_fee_unit_minutes` | int | 추가 요금 단위 시간 (분) |
| `daily_max_fee` | int \| null | 일일 최대 요금. null이면 상한 없음 |
| `is_active` | bool | 주차장 운영 여부 |
| `synced_at` | datetime | 응답 시각. Hub의 `last_synced_at` 갱신에 사용 |

#### 에러 응답

| 상태 | detail | 원인 |
|------|--------|------|
| 404 | `lot_not_found` | `lot_id`에 해당하는 주차장 없음 |

### 6. `main.py` 분기

```python
if settings.mode == "public":
    from app.routers.public import status
    app.include_router(status.router, prefix="/public", tags=["public"])
```

---

## Hub Server 구현 사항

### Hub DB (`lots` 테이블) — PLS push로 채워지는 필드

| 필드 | 값 | 비고 |
|------|----|------|
| `lot_type` | `'parking_lot_server'` | 폴링 방식 결정 |
| `pl_server_url` | PLS가 전송한 `pls_url` | 폴링 URL 조합에 사용 |
| `pl_lot_id` | PLS가 전송한 `lot_id` | 폴링 URL 조합에 사용 |
| `pl_api_key` | — | **미사용** (단일 PLS 가정으로 인증 불필요) |
| `name`, `address`, 요금 필드 등 | PLS가 전송한 값 | |

### `POST /lots` — lot 등록 수신

- 인증: 없음
- 호출 시점: PLS의 `POST /admin/lots` 성공 직후 (원자적 처리)

**요청 (PLS → Hub)**

```json
{
  "pls_url": "http://192.168.1.100:8000",
  "lot_id": "uuid",
  "name": "본관 주차장",
  "address": "...",
  "total_spaces": 100,
  "base_fee": 1000,
  "base_duration_minutes": 30,
  "extra_fee_per_unit": 200,
  "extra_fee_unit_minutes": 10,
  "daily_max_fee": null
}
```

| 필드 | Hub DB 저장 위치 |
|------|----------------|
| `pls_url` | `pl_server_url` |
| `lot_id` | `pl_lot_id` |
| 나머지 필드 | 동일한 이름의 컬럼 |

**응답**

| 상태 | 의미 |
|------|------|
| 201 Created | 등록 성공 |
| 409 Conflict | 동일 `lot_id`가 이미 등록됨 |

PLS는 201이 아닌 경우 HTTPException을 발생시켜 lot 생성 트랜잭션을 롤백한다.

---

### `PATCH /lots/{pl_lot_id}` — lot 비활성화 수신

- 인증: 없음
- `{pl_lot_id}`: PLS의 `parking_lots.id` (Hub의 `pl_lot_id` 필드로 조회)
- 호출 시점: PLS의 `DELETE /admin/lots/{lot_id}` 처리 시 (best-effort, 실패해도 PLS 비활성화는 유지)

**요청 (PLS → Hub)**

```json
{ "is_active": false }
```

**응답**

| 상태 | 의미 |
|------|------|
| 200 OK | 업데이트 성공 |
| 404 Not Found | 해당 `pl_lot_id`가 Hub에 없음 |

### 폴링 로직

```
for each lot where lot_type='parking_lot_server' AND is_active=true:
    GET {pl_server_url}/public/status/{pl_lot_id}

    → lots.available_spaces 업데이트
    → lots.last_synced_at = synced_at (응답값)
```

---

## 인터페이스 요약

| 방향 | 엔드포인트 | 인증 | 시점 | 원자성 |
|------|-----------|------|------|--------|
| PLS → Hub | `POST {HUB_URL}/lots` | 없음 | lot 생성 시 (Public 모드) | 원자적 (실패 시 lot 롤백) |
| PLS → Hub | `PATCH {HUB_URL}/lots/{pl_lot_id}` | 없음 | lot 비활성화 시 (Public 모드) | best-effort |
| Hub → PLS | `GET /public/status/{lot_id}` | 없음 | 주기적 폴링 | — |

---

## 테스트 단계

### 1단계. 로컬 연동 테스트

```bash
# PLS (Public 모드, 포트 8000)
# .env: MODE=public, HUB_URL=http://localhost:8001
cd parking_lot_server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Hub Server (포트 8001)
cd hub_server
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

**검증 순서**

1. 주차장 주인 PLS 회원가입 (`POST /auth/signup`)
2. superadmin → `POST /admin/lots` on PLS → Hub에 자동 push 확인
3. superadmin → `PATCH /admin/users/{user_id}` on PLS → `parking_lot_id` 연결
4. 주차장 주인 로그인 → `GET /admin/lots`로 `api_key` 확인
5. 카메라 클라이언트로 입차 요청 (`POST /api/v1/plates`)
6. Hub 폴링 후 `available_spaces` 반영 확인
7. `DELETE /admin/lots/{lot_id}` → Hub 비활성화 반영 확인

### 2단계. 실제 IP 연동 테스트

```bash
# .env: MODE=public, HUB_URL=http://{Hub 실제 IP}:8001
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 현재 구현 상태

| 항목 | Parking Lot Server | Hub Server |
|------|-------------------|------------|
| 입출차 처리 | ✅ 완료 | — |
| 관리자 API | ✅ 완료 | — |
| 주차장 주인 회원가입 | ✅ 완료 | — |
| `UserPatch`에 `parking_lot_id` 추가 | ✅ 완료 | — |
| `HUB_URL` 환경변수 | ✅ 완료 | — |
| Hub push — lot 등록 (`POST /admin/lots` 시) | ✅ 완료 | — |
| Hub push — lot 비활성화 (`DELETE /admin/lots` 시) | ✅ 완료 | — |
| `GET /public/status/{lot_id}` | ✅ 완료 | — |
| `POST /lots` — lot 등록 수신 | — | ⬜ 미구현 |
| `PATCH /lots/{pl_lot_id}` — 비활성화 수신 | — | ⬜ 미구현 |
| 폴링 로직 | — | ⬜ 미구현 |
| 로컬 연동 테스트 | ⬜ 예정 | ⬜ 예정 |
| 실제 IP 연동 테스트 | ⬜ 예정 | ⬜ 예정 |
