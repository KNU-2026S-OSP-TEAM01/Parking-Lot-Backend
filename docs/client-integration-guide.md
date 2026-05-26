# 클라이언트 연동 테스트 가이드

카메라 클라이언트 팀원이 PLS(Parking Lot Server)와 연동 테스트를 수행하기 위한 가이드.

---

## 전제 조건

서버가 실행 중이어야 한다.

```bash
docker compose up db app -d
```

Python 의존성 설치 (스크립트 실행 시):

```bash
pip install httpx
```

---

## 1. 초기 데이터 세팅

계정과 주차장이 없는 경우 아래 스크립트로 생성한다.

```bash
python scripts/seed_integration.py
```

실행하면 다음을 자동으로 수행한다:

- `testowner` 계정 생성 (이미 있으면 로그인만)
- `북문 주차장` 생성
- 생성된 주차장의 `id`와 `api_key` 출력

출력 예시:

```
▶ 회원가입 중...
  ✔ 계정 생성: testowner
▶ 로그인 중...
  ✔ 토큰 발급 완료
▶ 주차장 생성 중...
  ✔ [북문 주차장] id=xxxxxxxx-... api_key=abcd1234...
```

> **`api_key`를 메모해둔다.** 이후 모든 카메라 요청에 사용된다.

---

## 2. API Key 및 주차장 현황 조회

아래 스크립트로 주차장 정보, 현재 주차 차량, 입출차 로그를 한 번에 확인할 수 있다.

```bash
# 전체 목록 조회
python scripts/get_lots.py

# 특정 주차장 단건 조회
python scripts/get_lots.py <lot_id>
```

출력 예시:

```
▶ 로그인 중...
  ✔ 토큰 발급 완료

▶ 주차장 총 1개

  ══════════════════════════════════════════════════
  id             : xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  name           : 북문 주차장
  address        : 대구광역시 북구 대학로 80
  latitude       : 35.8895
  longitude      : 128.6105
  spaces         : 96 남음 / 100 전체
  base_fee       : 1000원 / 30분
  extra_fee      : 200원 / 10분
  daily_max_fee  : 10000원
  api_key        : abcd1234efgh5678...   ← 카메라 요청에 사용

  [주차 중인 차량] 4대
    • 44라4444  |  입차: 2026-05-24T10:30:00+00:00
    ...

  [입출차 로그] 최근 N건
    • [ENTRY] 11가1111  |  2026-05-24T08:00:00+00:00
    • [EXIT]  11가1111  |  2026-05-24T08:30:00+00:00  요금: 1000원
    ...
```

---

## 3. 카메라 → 서버 번호판 전송 (핵심 연동 엔드포인트)

### 엔드포인트

```
POST /api/v1/plates
```

### 인증

`Authorization` 헤더에 주차장 `api_key`를 Bearer 토큰으로 전달한다.

```
Authorization: Bearer <api_key>
```

### 요청 바디

```json
{
  "plate": "12가3456",
  "timestamp": "2026-05-24T10:00:00+00:00"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `plate` | string | 번호판 원문 (예: `12가3456`) |
| `timestamp` | datetime (ISO 8601) | 카메라가 촬영한 시각. **반드시 타임존 포함** |

### 응답

**입차 (해당 번호판이 현재 주차 중이 아닌 경우)**

```json
{
  "event": "entry",
  "entered_at": "2026-05-24T10:00:00+00:00"
}
```

**출차 (해당 번호판이 현재 주차 중인 경우)**

```json
{
  "event": "exit",
  "fee": 1000,
  "parked_duration_minutes": 35
}
```

### 동작 로직

- 같은 번호판이 **현재 주차 중이 아니면 → 입차** 처리
- 같은 번호판이 **이미 주차 중이면 → 출차** 처리 (요금 정산)
- 같은 번호판을 두 번 연속 보내면 입차 → 출차가 자동으로 처리된다

### curl 예시

```bash
API_KEY="여기에_api_key_입력"

# 입차
curl -X POST http://localhost:8000/api/v1/plates \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"plate": "12가3456", "timestamp": "2026-05-24T10:00:00+00:00"}'

# 출차 (같은 번호판을 다시 전송)
curl -X POST http://localhost:8000/api/v1/plates \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"plate": "12가3456", "timestamp": "2026-05-24T10:40:00+00:00"}'
```

### 에러 코드

| HTTP | detail | 의미 |
|------|--------|------|
| 401 | `invalid_api_key` | api_key가 없거나 잘못됨 |
| 409 | `parking_lot_full` | 주차 가능 공간 없음 |

---

## 4. 더미 입출차 데이터 주입 (스크립트)

실제 카메라 없이 번호판 데이터를 빠르게 주입하려면 `seed_plates.py`를 사용한다.

```bash
python scripts/seed_plates.py <api_key>
```

스크립트가 주입하는 시나리오:

| 번호판 | 동작 | 결과 |
|--------|------|------|
| 11가1111 | 입차 → 출차 | 로그에만 기록 |
| 22나2222 | 입차 → 출차 | 로그에만 기록 |
| 33다3333 | 입차 → 출차 | 로그에만 기록 |
| 44라4444 | 입차만 | 현재 주차 중 |
| 55마5555 | 입차만 | 현재 주차 중 |
| 66바6666 | 입차만 | 현재 주차 중 |

출력 예시:

```
▶ 입출차 데이터 주입 (api_key=abcd1234...)

  [ENTRY] 11가1111  |  08:00  →  {'event': 'entry', ...}
  [EXIT]  11가1111  |  08:30  →  요금: 1000원, 주차: 30분
  ...
  [주차중] 44라4444  →  현재 주차 중으로 유지

완료. get_lots.py로 결과를 확인하세요.
```

주입 후 결과 확인:

```bash
python scripts/get_lots.py
```

---

## 5. 전체 테스트 플로우 요약

```
1. python scripts/seed_integration.py    # 계정 + 주차장 생성, api_key 확인
2. python scripts/get_lots.py            # api_key 재확인, 현재 상태 확인
3. python scripts/seed_plates.py <api_key>   # 더미 입출차 데이터 주입
4. python scripts/get_lots.py            # 주차 차량 및 로그 확인
5. (실제 카메라 연동) POST /api/v1/plates 로 번호판 전송
6. python scripts/get_lots.py            # 결과 확인
```
