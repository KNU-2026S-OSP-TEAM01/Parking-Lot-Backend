# 주차장 위경도 자동 입력 계획

> 작성일: 2026-05-23  
> 배경: 주차장 생성 시 address를 기반으로 카카오맵 API를 통해 위경도를 서버에서 자동으로 추출·저장

---

## 개요

사용자가 `POST /api/v1/lots` 시 `address`를 입력하면, 서버가 카카오 로컬 REST API를 호출해 위도(`latitude`)·경도(`longitude`)를 자동으로 추출하여 저장한다. 사용자는 위경도를 직접 입력하지 않는다.

주소 geocoding 실패 시 실패 이유를 구분한 에러 코드를 반환하고 lot 생성을 중단한다.

---

## 변경 범위

### 1. 모델 (`app/models/parking_lot.py`)

`parking_lots` 테이블에 컬럼 추가:

| 컬럼 | 타입 | 제약 |
|------|------|------|
| `latitude` | `Float` | NOT NULL |
| `longitude` | `Float` | NOT NULL |

### 2. 스키마 (`app/schemas/lot.py`)

- `LotCreate`: 변경 없음 (사용자 입력 대상 아님)
- `LotPatch`: 변경 없음
- `LotOut`: `latitude: float`, `longitude: float` 추가

### 3. 서비스 (`app/services/kakao.py`) — 신규 생성

카카오 로컬 REST API(`/v2/local/search/address.json`) 호출 함수 모듈화.

```python
async def geocode(address: str) -> tuple[float, float]:
    ...
```

- 정상: `(latitude, longitude)` 반환
- 실패: 아래 에러 코드로 `HTTPException` raise

| 상황 | HTTP 상태 | `detail` |
|------|-----------|---------|
| API 키 미설정 | 503 | `geocoding_not_configured` |
| 주소 검색 결과 없음 | 422 | `address_not_found` |
| 카카오 API 오류 (4xx/5xx) | 502 | `geocoding_upstream_error` |
| 네트워크 타임아웃 등 | 502 | `geocoding_upstream_error` |

**API 명세**

- URL: `https://dapi.kakao.com/v2/local/search/address.json`
- 인증 헤더: `Authorization: KakaoAK {KAKAO_REST_API_KEY}`
- 쿼리 파라미터: `query={address}`

**응답 파싱**

`documents[0]`의 최상위 `x`(경도), `y`(위도)를 사용한다.

```json
{
  "documents": [
    {
      "y": "35.97664845766847",
      "x": "126.99597295767953",
      ...
    }
  ]
}
```

> 주의: 카카오 API에서 `x` = 경도(longitude), `y` = 위도(latitude)이므로 파싱 시 반드시 구분한다.

`documents`가 빈 배열이면 `address_not_found` 에러.

### 4. 라우터 (`app/routers/lots.py`)

`POST /api/v1/lots` 처리 흐름:

```
1. kakao.geocode(body.address) 호출
2. 실패 시 HTTPException → lot 생성 중단
3. 성공 시 (latitude, longitude) 추출
4. ParkingLot 생성 시 latitude, longitude 함께 저장
```

`PATCH /api/v1/lots/{lot_id}` 처리 흐름 (address 변경 시 추가):

```
1. patch에 address 포함된 경우 → kakao.geocode(new_address) 호출
2. 실패 시 HTTPException → 수정 중단
3. 성공 시 latitude, longitude도 patch에 포함하여 갱신
```

### 5. 설정 (`app/config.py` / `.env.example`)

`config.py`에 추가:
```python
kakao_rest_api_key: str = ""
```

`.env.example`에 추가:
```
KAKAO_REST_API_KEY=
```

키가 빈 문자열이면 geocoding 시도 없이 `503 geocoding_not_configured` 반환.

### 6. Alembic 마이그레이션

`alembic/versions/20260523_*_add_lat_lng_to_parking_lots.py` 신규 생성.

```sql
ALTER TABLE parking_lots ADD COLUMN latitude DOUBLE PRECISION;
ALTER TABLE parking_lots ADD COLUMN longitude DOUBLE PRECISION;
```

### 7. 테스트 (`tests/services/test_kakao.py`) — 신규 생성

카카오 HTTP 응답을 mock으로 대체한 단위 테스트.

| 케이스 | 기대 결과 |
|--------|----------|
| 정상 응답 | 위경도 올바르게 파싱하여 반환 |
| 결과 없음 (`documents` 빈 배열) | `422 address_not_found` |
| 카카오 API 4xx/5xx | `502 geocoding_upstream_error` |
| 네트워크 오류 | `502 geocoding_upstream_error` |
| API 키 미설정 | `503 geocoding_not_configured` |

---

## 미결 사항

없음.
