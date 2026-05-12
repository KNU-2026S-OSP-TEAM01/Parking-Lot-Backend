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
- Hub는 lot별로 `pl_server_url`과 `pl_lot_id`를 DB에 저장한다.
- **Private PLS는 `HUB_URL` 없이도 완전히 동작한다.** Hub 관련 로직은 Public 모드에서만 실행된다.

---

## Private / Public 모드 동작 비교

| 기능 | Private | Public |
|------|---------|--------|
| 입출차 처리 | ✅ | ✅ |
| 관리자 API | ✅ | ✅ |
| Hub에 lot 등록 push | ❌ 실행 안 함 | ✅ |
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
                    { pls_url, lot_id, name, total_spaces, ... }

5. Hub            → lots DB에 등록
                    (pl_server_url = pls_url, pl_lot_id = lot_id)

6. superadmin     → PATCH /admin/users/{user_id} on PLS (JWT 인증)
                    parking_lot_id 연결

7. 주차장 주인    → PLS 로그인 → GET /admin/lots
                    카메라 api_key 확인 후 카메라에 설정
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
    │                                       │ 주차장 현황 조회
    │◄───────────────────────────────────────│
    │  { available_spaces, total_spaces, ...}│
    │                                       │
    │ lots.available_spaces 업데이트        │
    │ lots.last_synced_at = synced_at       │
```

`is_active=false`인 주차장은 폴링 대상에서 제외하고 사용자에게 "운영 중단" 상태로 표시한다.

---

## Parking Lot Server 구현 사항

### 1. 환경변수

```env
# Public 모드에서만 필요
HUB_URL=http://localhost:8001   # Hub Server 베이스 URL
```

`config.py`에 Optional 필드로 추가:

```python
hub_url: str | None = None
```

Private 모드에서는 `HUB_URL`이 없어도 서버가 정상 동작해야 한다.

### 2. `POST /admin/lots` — Public 모드 시 Hub push (원자적 처리)

lot 생성과 Hub push를 하나의 트랜잭션으로 묶는다.  
Hub push가 실패하면 lot 생성도 롤백한다. PLS와 Hub는 항상 일관성을 유지한다.

```python
async def create_lot(...):
    lot = 주차장 생성()          # DB에 flush (아직 commit 전)

    if settings.mode == "public" and settings.hub_url:
        await notify_hub(lot)    # 실패 시 HTTPException 발생 → 트랜잭션 롤백

    return lot                   # 정상 반환 시 get_db가 commit
```

Hub push 실패(연결 오류, 타임아웃 등) 시 `503 Service Unavailable`을 반환한다.  
superadmin은 Hub 상태를 확인한 후 재시도한다.

### 3. `GET /public/status/{lot_id}` — 인증 없는 공개 엔드포인트

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

### 4. `main.py` 분기

```python
if settings.mode == "public":
    from app.routers.public import status
    app.include_router(status.router, prefix="/public", tags=["public"])
```

---

## Hub Server 구현 사항

### 환경변수

Hub Server는 PLS URL을 개별 lot의 DB 필드(`pl_server_url`)로 관리하므로 별도 PLS 관련 환경변수가 없다.

### Hub DB (`lots` 테이블) — PLS push로 자동 등록되는 필드

| 필드 | 값 | 출처 |
|------|----|------|
| `lot_type` | `'parking_lot_server'` | PLS push |
| `pl_server_url` | PLS가 전송한 `pls_url` | PLS push |
| `pl_lot_id` | PLS가 전송한 `lot_id` | PLS push |
| `name`, `address`, 요금 필드 등 | PLS가 전송한 값 | PLS push |

### `POST /lots` — PLS로부터 lot 등록 수신 (인증 없음)

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

### 폴링 로직

```
for each lot where lot_type='parking_lot_server' AND is_active=true:
    GET {pl_server_url}/public/status/{pl_lot_id}

    → lots.available_spaces 업데이트
    → lots.last_synced_at = synced_at (응답값)
```

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

### 2단계. 실제 IP 연동 테스트

```bash
# PLS 배포 서버
# .env: MODE=public, HUB_URL=http://{Hub 실제 IP}:8001
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 인터페이스 요약

| 방향 | 엔드포인트 | 인증 | 시점 |
|------|-----------|------|------|
| PLS → Hub | `POST {HUB_URL}/lots` | 없음 | lot 생성 시 (Public 모드) |
| Hub → PLS | `GET /public/status/{lot_id}` | 없음 | 주기적 폴링 |

---

## 현재 구현 상태

| 항목 | Parking Lot Server | Hub Server |
|------|-------------------|------------|
| 입출차 처리 | ✅ 완료 | — |
| 관리자 API | ✅ 완료 | — |
| 주차장 주인 회원가입 | ✅ 완료 | — |
| `HUB_URL` 환경변수 | ⬜ 미구현 | — |
| Hub push (`POST /admin/lots` 시) | ⬜ 미구현 | — |
| `GET /public/status/{lot_id}` | ⬜ 미구현 | — |
| `POST /lots` (lot 등록 수신) | — | ⬜ 미구현 |
| 폴링 로직 | — | ⬜ 미구현 |
| 로컬 연동 테스트 | ⬜ 예정 | ⬜ 예정 |
| 실제 IP 연동 테스트 | ⬜ 예정 | ⬜ 예정 |
