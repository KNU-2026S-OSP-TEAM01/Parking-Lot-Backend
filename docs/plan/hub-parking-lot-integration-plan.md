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
| **Parking Lot Server** | 개별 주차장 입출차 처리. `MODE=public`일 때 Hub Server에 현황 제공 |
| **Hub Server** | 여러 주차장 현황을 통합해 외부 사용자에게 제공. PLS를 주기적으로 폴링 |

---

## 연동 흐름

```
Hub Server                          Parking Lot Server (Public Mode)
    │                                         │
    │  GET /public/status                     │
    │  Authorization: Bearer {pl_api_key}     │
    │────────────────────────────────────────►│
    │                                         │ 주차장 현황 조회
    │◄────────────────────────────────────────│
    │  { available_spaces, total_spaces, ... }│
    │                                         │
    │ lots.available_spaces 업데이트          │
    │ lots.last_synced_at = now()             │
```

Hub Server는 등록된 `parking_lot_server` 타입 주차장을 주기적으로 폴링해 `available_spaces`를 캐싱한다.

---

## Parking Lot Server 구현 사항

### 추가할 것

**1. `.env`에 `HUB_API_KEY` 추가**

Hub Server 전용 인증키. PLS 인스턴스 단위로 관리하므로 환경변수가 적합하다.  
카메라 클라이언트 `api_key`는 주차장마다 달라 DB에 저장하지만, Hub Server는 PLS 하나와 통신하므로 환경변수로 충분하다.

```env
HUB_API_KEY=            # openssl rand -hex 32
```

`app/config.py`에 `hub_api_key: str` 필드 추가. Hub Server의 `pl_api_key`는 이 값을 사용한다.

**2. `GET /public/status` 엔드포인트 구현**

`MODE=public`일 때만 마운트된다.

- 인증: `Authorization: Bearer {HUB_API_KEY}`  
  → `settings.hub_api_key`와 비교해 검증
- 응답:

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
  "is_active": true
}
```

**3. `.env.example`에도 `HUB_API_KEY=` 추가**

**4. `main.py` 분기 완성**

```python
if settings.mode == "public":
    from app.routers.public import status
    app.include_router(status.router, prefix="/public", tags=["public"])
```

**5. `MODE=public` 실행**

```env
MODE=public
```

```bash
uvicorn app.main:app --host 0.0.0.0 --reload
```

---

## Hub Server 구현 사항

### Hub Server DB (`lots` 테이블)

`parking_lot_server` 타입으로 주차장을 등록할 때 아래 필드를 채운다.

| 필드 | 값 |
|------|----|
| `lot_type` | `'parking_lot_server'` |
| `pl_server_url` | PLS의 `GET /public/status` 기본 URL (예: `http://localhost:8000`) |
| `pl_lot_id` | PLS의 `parking_lots.id` |
| `pl_api_key` | PLS의 `HUB_API_KEY` 환경변수 값 |

### 폴링 로직

Hub Server는 주기적으로 각 `parking_lot_server` 타입 주차장의 `pl_server_url`을 호출해 현황을 동기화한다.

```
GET {pl_server_url}/public/status
Authorization: Bearer {pl_api_key}

→ available_spaces, total_spaces 등 업데이트
→ last_synced_at = now()
```

폴링 주기는 Hub Server에서 결정한다. `last_synced_at`이 오래된 경우 일반 사용자에게 "정보가 오래되었을 수 있습니다"를 표시하도록 FE에 안내한다.

---

## 테스트 단계

### 1단계. 로컬 연동 테스트

두 서버를 같은 머신에서 포트를 다르게 실행해 연동을 검증한다.

```bash
# Parking Lot Server (Public 모드)
# .env에서 MODE=public 설정
cd parking_lot_server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Hub Server
cd hub_server
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Hub Server의 `pl_server_url`은 `http://localhost:8000`으로 등록한다.

**검증 순서**

1. PLS `.env`에서 `HUB_API_KEY` 확인 (seed 또는 관리자에게 전달)
2. Hub Server에 해당 주차장 등록 (`pl_server_url`, `pl_lot_id`, `pl_api_key=HUB_API_KEY 값` 입력)
3. PLS에 카메라 클라이언트로 입차 요청 (`POST /api/v1/plates`)
4. Hub Server 폴링 후 `available_spaces` 반영 확인
5. PLS에 출차 요청 후 Hub Server 동기화 확인

### 2단계. 실제 IP 연동 테스트

PLS를 온프레미스 서버에 배포한 후 실제 IP로 연동한다.

```bash
# PLS 배포 서버에서
MODE=public uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Hub Server의 `pl_server_url`을 실제 IP로 변경한다.  
예: `http://192.168.x.x:8000`

---

## 인터페이스 요약

### PLS가 Hub Server에 제공하는 것

| 항목 | 내용 |
|------|------|
| 엔드포인트 | `GET /public/status` |
| 인증 | `Authorization: Bearer {HUB_API_KEY}` (PLS 환경변수) |
| 응답 | 주차장 현황 (이름, 주소, 면수, 요금 정보, 잔여 면수) |
| 활성 조건 | `MODE=public`일 때만 노출 |

### Hub Server가 PLS에 제공해야 하는 것

없음. Hub Server는 PLS를 단방향으로 폴링한다.

---

## 현재 구현 상태

| 항목 | Parking Lot Server | Hub Server |
|------|-------------------|------------|
| 입출차 처리 | ✅ 완료 | — |
| 관리자 API | ✅ 완료 | — |
| `HUB_API_KEY` 환경변수 | ⬜ 미구현 | — |
| `GET /public/status` | ⬜ 미구현 | — |
| 주차장 등록/폴링 | — | ⬜ 미구현 |
| 로컬 연동 테스트 | ⬜ 예정 | ⬜ 예정 |
| 실제 IP 연동 테스트 | ⬜ 예정 | ⬜ 예정 |
