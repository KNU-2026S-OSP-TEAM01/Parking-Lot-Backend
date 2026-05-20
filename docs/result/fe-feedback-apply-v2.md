# FE 피드백 반영 작업 결과 v2

> 작성일: 2026-05-13  
> 브랜치: `feat/fe_feedback_apply`  
> 이전 문서: `docs/result/fe-feedback-apply.md`

---

## 이번 변경 사항

### 1. PLS에서 Hub 의존성 완전 제거

**배경**

기존에는 PLS가 주차장 등록/비활성화 시 Hub Server에 HTTP push를 보내는 구조였다. FE 팀 제안으로 Hub가 PLS의 DB를 직접 공유하는 방식으로 전환한다. 이에 따라 PLS → Hub push 로직이 불필요해졌다.

**제거된 것**

| 항목 | 내용 |
|------|------|
| `app/services/hub.py` | Hub HTTP push 서비스 파일 전체 삭제 |
| `app/routers/public/` | Hub 폴링용 `GET /public/status/{lot_id}` 엔드포인트 삭제 |
| `app/config.py` | `hub_url`, `mode` 환경변수 제거 |
| `app/main.py` | `MODE` 분기 및 public 라우터 마운트 코드 제거 |
| `app/routers/lots.py` | `notify_hub_lot_created`, `notify_hub_lot_deactivated` 호출 제거 |
| `.env.example` | `HUB_URL`, `MODE` 항목 제거 |

> `MODE` 환경변수는 Hub push와 `/public/status` 마운트를 제어하는 용도였으나, 두 기능 모두 제거되어 의미가 없어졌다. `ENABLE_SIGNUP`이 Private/Public 구분의 유일한 기준이다.

**변경 후 구조**

PLS는 이제 Hub와 직접 통신하지 않는다. Hub가 PLS의 DB에 직접 접근해 필요한 데이터를 읽는다.

---

### 2. `LotPatch`에서 `is_active` 필드 제거

**배경**

`is_active`를 유지할지 여부에 대한 논의가 진행 중이다. 결정 전까지 PATCH를 통한 수정을 막기 위해 `LotPatch` 스키마에서 제거했다. `LotOut` 응답과 DB 컬럼에는 유지된다.

```python
# 변경 전
class LotPatch(BaseModel):
    ...
    is_active: Optional[bool] = None  # 제거됨

# 변경 후
class LotPatch(BaseModel):
    name, address, total_spaces, 요금 필드만 수정 가능
```

---

## 추후 Hub 연동 방식

### 결정된 방향: DB 공유 (Docker 내부망)

Hub Server와 PLS는 Docker 내부 네트워크를 통해 **같은 PostgreSQL DB에 접근**한다.

```
Docker 내부망
┌──────────────────────────────────────┐
│  parking_lot_server (PLS)            │
│  hub_server                          │
│  postgres (공유 DB)                  │
└──────────────────────────────────────┘
```

- PLS와 Hub가 동일한 `parking_lots` 테이블을 읽는다
- Hub는 `owner_user_id`, `api_key` 등 민감 필드를 제외하고 공개 필드만 사용한다
- Hub가 `available_spaces`를 직접 읽으므로 폴링 불필요

**이점**

| 항목 | 기존 (폴링) | 변경 (DB 공유) |
|------|------------|--------------|
| 데이터 동기화 | 폴링 주기에 의존 | 실시간 |
| PLS 코드 복잡도 | Hub push 로직 필요 | 없음 |
| Hub 코드 복잡도 | 폴링 스케줄러 필요 | 단순 SELECT |
| 네트워크 오버헤드 | HTTP 반복 호출 | 없음 |

**Docker Compose 예시 (추후 작성)**

```yaml
services:
  db:
    image: postgres:16
    # PLS와 Hub가 공유

  pls:
    build: .
    environment:
      DATABASE_URL: postgresql+asyncpg://openpark:openpark@db/openpark

  hub:
    build: ./hub_server
    environment:
      DATABASE_URL: postgresql+asyncpg://openpark:openpark@db/openpark
```

Hub는 PLS DB의 `parking_lots` 테이블에서 일반 사용자에게 노출할 데이터만 SELECT한다.

---

## `is_active` 논의

### 현재 상태

- DB 컬럼 및 `LotOut` 응답에는 유지 중
- `LotPatch`에서는 제거 (API로 수정 불가)

### 논의 필요 사항

| 질문 | 선택지 |
|------|--------|
| 비활성 주차장을 유지할 필요가 있는가? | 유지 (soft delete) vs 제거 (hard delete만) |
| Hub에서 비활성 주차장을 어떻게 표시할 것인가? | 목록에서 제외 vs "운영 중단" 표시 |
| `is_active=false` 전환 수단은? | 현재 없음. DELETE(hard delete)만 존재 |

### 잠정 결론

현재는 `DELETE /api/v1/lots/{lot_id}`가 **hard delete**이므로 주차장을 비활성 상태로 유지하는 수단이 없다. `is_active` 컬럼을 계속 가져갈 경우 soft delete API를 별도로 추가해야 한다. 추후 운영 정책 결정 후 스키마 및 API 수정 예정.

---

## 테스트 결과

```
77 passed (변경 전후 동일)
```

Hub 의존성 제거 후에도 기존 테스트 전부 통과. Hub push 코드는 `MODE=private` 조건으로 테스트에서 실행되지 않았으므로 테스트 변경 없음.
