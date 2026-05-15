# 카메라 클라이언트 연동 가이드

> 대상: 번호판 인식 클라이언트 개발자
> 테스트 환경: 웹캠 (Python) → 추후 라즈베리파이

---

## 1. 통신 구조

카메라가 번호판을 인식하면 PLS 서버로 HTTP POST 요청을 보낸다.
서버는 해당 번호판이 현재 주차 중인지 여부에 따라 자동으로 입차/출차를 판단해 응답한다.

```
카메라 클라이언트
    │
    │  POST /api/v1/plates
    │  Authorization: Bearer {api_key}
    │  { "plate": "12가3456", "timestamp": "..." }
    ▼
Parking Lot Server (PLS)
    │
    ├─ 차량 없음 → 입차 처리 → { "event": "entry", ... }
    └─ 차량 있음 → 출차 처리 → { "event": "exit", "fee": ..., ... }
```

---

## 2. API 명세

### `POST /api/v1/plates`

#### 요청

```
POST http://{서버_IP}:8000/api/v1/plates
Authorization: Bearer {api_key}
Content-Type: application/json
```

```json
{
  "plate": "12가3456",
  "timestamp": "2026-05-15T10:00:00+09:00"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `plate` | string | 인식된 번호판 문자열 |
| `timestamp` | string (ISO 8601) | 번호판 인식 시각. **타임존 필수** |

`api_key`는 주차장 소유자가 PLS에 주차장을 등록할 때 발급받은 키다.
카메라 설정 파일이나 환경변수에 저장해 사용한다.

#### 응답 — 입차

```json
{
  "event": "entry",
  "entered_at": "2026-05-15T10:00:00+09:00"
}
```

#### 응답 — 출차

```json
{
  "event": "exit",
  "fee": 3000,
  "parked_duration_minutes": 90
}
```

#### 에러 응답

| 상태 | detail | 원인 |
|------|--------|------|
| 401 | `invalid_api_key` | api_key가 틀리거나 주차장이 비활성 상태 |
| 409 | `parking_lot_full` | 만석 (입차 불가) |

---

## 3. 구현 예시

### 3-1. 웹캠 (Python)

**사전 설치**

```bash
pip install opencv-python requests
```

번호판 인식 라이브러리는 별도로 붙여야 한다. 아래 예시는 인식 결과(`plate_text`)를 이미 얻었다고 가정한다.

```python
import requests
from datetime import datetime, timezone, timedelta

PLS_URL = "http://192.168.0.10:8000"  # PLS 서버 IP
API_KEY = "여기에_api_key_입력"

KST = timezone(timedelta(hours=9))


def send_plate(plate_text: str) -> dict:
    timestamp = datetime.now(KST).isoformat()

    response = requests.post(
        f"{PLS_URL}/api/v1/plates",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"plate": plate_text, "timestamp": timestamp},
        timeout=5,
    )

    if response.status_code == 409:
        print("만석 — 입차 불가")
        return {}
    if response.status_code == 401:
        print("API 키 오류")
        return {}

    response.raise_for_status()
    return response.json()


# 웹캠 루프 예시
import cv2

cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # TODO: 번호판 인식 로직으로 plate_text 추출
    plate_text = recognize_plate(frame)  # 직접 구현 필요

    if plate_text:
        result = send_plate(plate_text)
        print(result)  # {"event": "entry", ...} 또는 {"event": "exit", ...}

    if cv2.waitKey(1) == ord("q"):
        break

cap.release()
```

---

### 3-2. 라즈베리파이

웹캠 코드와 동일하게 동작한다. 아래는 라즈베리파이 환경에서 달라지는 부분만 정리한다.

**카메라 모듈 사용 시 (`picamera2`)**

```bash
pip install picamera2 requests
```

```python
from picamera2 import Picamera2
import requests
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
PLS_URL = "http://192.168.0.10:8000"
API_KEY = "여기에_api_key_입력"

picam2 = Picamera2()
picam2.start()

while True:
    frame = picam2.capture_array()

    # TODO: 번호판 인식
    plate_text = recognize_plate(frame)

    if plate_text:
        timestamp = datetime.now(KST).isoformat()
        response = requests.post(
            f"{PLS_URL}/api/v1/plates",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={"plate": plate_text, "timestamp": timestamp},
            timeout=5,
        )
        print(response.json())
```

**고정 IP 권장**

라즈베리파이와 PLS 서버가 같은 네트워크에 있을 때, 라즈베리파이에 고정 IP를 할당하면 재부팅 후에도 연결이 안정적이다.

```bash
# /etc/dhcpcd.conf 에 추가
interface wlan0
static ip_address=192.168.0.50/24
static routers=192.168.0.1
```

**부팅 시 자동 실행 (systemd)**

```ini
# /etc/systemd/system/openpark-camera.service
[Unit]
Description=OpenPark Camera Client
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/camera_client.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable openpark-camera
sudo systemctl start openpark-camera
```

---

## 4. 주의 사항

**타임스탬프에 타임존을 반드시 포함해야 한다**

```python
# 잘못된 예 (타임존 없음 — 서버에서 오류)
datetime.now().isoformat()           # "2026-05-15T10:00:00"

# 올바른 예
datetime.now(timezone(timedelta(hours=9))).isoformat()  # "2026-05-15T10:00:00+09:00"
```

**같은 번호판을 연속으로 보내면 입출차가 반전된다**

서버는 상태를 보고 입/출차를 자동 판단한다. 응답 실패 후 재전송할 때는 이미 입차 처리가 됐는지 먼저 확인해야 한다.

**네트워크 오류 대비**

카메라와 서버가 같은 네트워크 안에 있더라도 일시적 오류가 생길 수 있다. `timeout`을 설정하고 재시도 로직을 넣는 것을 권장한다.

```python
import time

def send_plate_with_retry(plate_text: str, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            return send_plate(plate_text)
        except requests.exceptions.RequestException as e:
            print(f"요청 실패 ({attempt + 1}/{retries}): {e}")
            time.sleep(1)
    return {}
```
