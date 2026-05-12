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
| **Parking Lot Server (PLS)** | 개별 주차장 입출차 처리. `MODE=public`일 때 Hub Server에 현황 제공 |
| **Hub Server** | 여러 주차장 현황을 통합해 외부 사용자에게 제공. PLS를 주기적으로 폴링 |

---

## 인증 키 구조

| 키 | 위치 | 용도 |
|----|------|------|
| `api_key` | PLS `parking_lots` 테이블 | 카메라 클라이언트 → PLS 입출차 요청 |
| `HUB_API_KEY` | PLS `.env` | Hub Server → PLS 모든 통신 (등록, 폴링, 삭제) |

Hub Server는 `HUB_API_KEY` 값을 `pl_hub_api_key` 필드에 저장해 사용한다.

---

## 주차장 등록 전체 흐름

```
1. 주차장 주인       → PLS에 회원가입 (POST /auth/signup)
                       role='admin', parking_lot_id=NULL 상태로 등록

2. 주차장 주인       → superadmin에게 주차장 등록 요청 (오프라인)

3. superadmin        → Hub에 주차장 정보 + 주인 user_id 입력

4. Hub Server        → POST /admin/lots on PLS
                       주차장 생성, lot_id + 카메라 api_key 반환

5. Hub Server        → PATCH /admin/users/{user_id} on PLS
                       parking_lot_id = lot_id 연결

6. 주차장 주인       → PLS에 로그인
                       GET /admin/lots 로 자신의 주차장 api_key 확인
                       카메라에 api_key 설정
```

---

## 현황 폴링 흐름

Hub Server는 `is_active=true`인 `parking_lot_server` 타입 주차장을 주기적으로 폴링한다.

```
Hub Server                          Parking Lot Server (Public Mode)
    │                                         │
    │  GET /public/status/{pl_lot_id}         │
    │  Authorization: Bearer {HUB_API_KEY}    │
    │────────────────────────────────────────►│
    │                                         │
    │◄────────────────────────────────────────│
    │  { available_spaces, total_spaces, ... }│
    │                                         │
    │ lots.available_spaces 업데이트          │
    │ lots.last_synced_at = synced_at         │
```

`is_active=false`인 주차장은 폴링 대상에서 제외하고 사용자에게 "운영 중단" 상태로 표시한다.

---

## Parking Lot Server 구현 사항

### 1. `.env`에 `HUB_API_KEY` 추가

```env
HUB_API_KEY=        # openssl rand -hex 32. MODE=private면 비워도 됨
```

`app/config.py`에 Optional 필드로 추가 (Private 모드에서는 불필요):

```python
hub_api_key: str | None = None
```

`.env.example`에도 `HUB_API_KEY=` 추가.

### 2. `POST /admin/lots`, `PATCH /admin/users/{user_id}`, `DELETE /admin/lots/{lot_id}` — Hub 인증 허용

세 엔드포인트는 현재 JWT superadmin만 허용한다. Hub Server가 `HUB_API_KEY`로 호출할 수 있도록 인증 의존성을 확장한다.

```python
async def require_superadmin_or_hub(credentials, db):
    token = credentials.credentials
    if settings.hub_api_key and token == settings.hub_api_key:
        return {"role": "hub"}
    # 기존 JWT superadmin 검증 로직 유지
```

### 3. `GET /public/status/{lot_id}` 엔드포인트 구현

`MODE=public`일 때만 마운트된다.

#### 요청

```
GET /public/status/{lot_id}
Authorization: Bearer {HUB_API_KEY}
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
| `available_spaces` | int | **현재 잔여 면수** |
| `base_fee` | int | 기본 요금 (원) |
| `base_duration_minutes` | int | 기본 요금 적용 시간 (분) |
| `extra_fee_per_unit` | int | 단위 추가 요금 (원) |
| `extra_fee_unit_minutes` | int | 추가 요금 단위 시간 (분) |
| `daily_max_fee` | int \| null | 일일 최대 요금. null이면 상한 없음 |
| `is_active` | bool | 주차장 운영 여부 |
| `synced_at` | datetime | PLS 응답 시각. Hub의 `last_synced_at` 갱신에 사용 |

#### 에러 응답

| 상태 | detail | 원인 |
|------|--------|------|
| 401 | `invalid_hub_api_key` | `HUB_API_KEY` 불일치 |
| 404 | `lot_not_found` | `lot_id`에 해당하는 주차장 없음 |

### 4. `main.py` 분기 완성

```python
if settings.mode == "public":
    from app.routers.public import status
    app.include_router(status.router, prefix="/public", tags=["public"])
```

### 5. 실행

```env
MODE=public
HUB_API_KEY=<생성한 키>
```

```bash
uvicorn app.main:app --host 0.0.0.0 --reload
```

---

## Hub Server 구현 사항

### Hub DB (`lots` 테이블) — `parking_lot_server` 등록 시 필드

| 필드 | 값 | 설명 |
|------|----|------|
| `lot_type` | `'parking_lot_server'` | 폴링 방식 결정에 사용 |
| `pl_server_url` | `http://192.168.x.x:8000` | PLS 베이스 URL (경로 제외) |
| `pl_lot_id` | PLS `POST /admin/lots` 응답의 `lot_id` | 폴링 URL 조합에 사용 |
| `pl_hub_api_key` | PLS의 `HUB_API_KEY` 환경변수 값 | 모든 PLS 요청의 인증 키 |

### superadmin이 Hub에서 수행하는 작업

1. 주차장 정보 + 주차장 주인의 PLS `user_id` 입력
2. Hub Server가 자동으로:
   - `POST /admin/lots` on PLS → `lot_id` 확보, Hub DB에 저장
   - `PATCH /admin/users/{user_id}` on PLS → `parking_lot_id` 연결

### 폴링 로직

```
for each lot where lot_type='parking_lot_server' AND is_active=true:
    GET {pl_server_url}/public/status/{pl_lot_id}
    Authorization: Bearer {pl_hub_api_key}

    → lots.available_spaces 업데이트
    → lots.last_synced_at = synced_at (응답값)
```

---

## 테스트 단계

### 1단계. 로컬 연동 테스트

```bash
# PLS (Public 모드, 포트 8000)
cd parking_lot_server
# .env: MODE=public, HUB_API_KEY=<key>
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Hub Server (포트 8001)
cd hub_server
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

**검증 순서**

1. 주차장 주인이 PLS에 회원가입 (`POST /auth/signup`)
2. superadmin이 Hub에 lot 정보 + user_id 입력
3. Hub → PLS `POST /admin/lots` + `PATCH /admin/users/{user_id}` 자동 호출 확인
4. 주차장 주인 로그인 → `GET /admin/lots` 로 `api_key` 확인
5. 카메라 클라이언트로 입차 요청 (`POST /api/v1/plates`)
6. Hub 폴링 후 `available_spaces` 반영 확인
7. 출차 요청 후 Hub 동기화 확인

### 2단계. 실제 IP 연동 테스트

PLS를 온프레미스 서버에 배포 후 실제 IP로 변경한다.

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Hub Server의 `pl_server_url`을 `http://192.168.x.x:8000`으로 변경한다.

---

## 인터페이스 요약

| 작업 | 엔드포인트 | 인증 |
|------|-----------|------|
| 주차장 등록 | `POST /admin/lots` | `HUB_API_KEY` |
| admin 주차장 배정 | `PATCH /admin/users/{user_id}` | `HUB_API_KEY` |
| 현황 폴링 | `GET /public/status/{lot_id}` | `HUB_API_KEY` |
| 주차장 삭제 | `DELETE /admin/lots/{lot_id}` | `HUB_API_KEY` |

Hub Server는 PLS를 단방향으로 호출한다. PLS가 Hub Server를 호출하는 경우는 없다.

---

## 현재 구현 상태

| 항목 | Parking Lot Server | Hub Server |
|------|-------------------|------------|
| 입출차 처리 | ✅ 완료 | — |
| 관리자 API | ✅ 완료 | — |
| 주차장 주인 회원가입 (`POST /auth/signup`) | ✅ 완료 | — |
| `HUB_API_KEY` 환경변수 추가 | ⬜ 미구현 | — |
| `POST/PATCH/DELETE` Hub 인증 허용 | ⬜ 미구현 | — |
| `GET /public/status/{lot_id}` | ⬜ 미구현 | — |
| 주차장 등록/폴링/삭제 | — | ⬜ 미구현 |
| 로컬 연동 테스트 | ⬜ 예정 | ⬜ 예정 |
| 실제 IP 연동 테스트 | ⬜ 예정 | ⬜ 예정 |
