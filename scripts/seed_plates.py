"""
plate 엔드포인트를 사용해 임의 입출차 기록을 주입하는 스크립트

- 입차 후 출차 → 로그에 entry/exit 기록
- 입차만 → 현재 주차 차량으로 남음

사용법:
    python scripts/seed_plates.py <api_key>

api_key는 get_lots.py 또는 seed_integration.py 실행 후 출력된 값을 사용
"""
import sys
from datetime import datetime, timedelta, timezone

import httpx

DEFAULT_URL = "http://localhost:8000"

# 입출차 시나리오: (plate, 입차 시각 offset(분), 출차 시각 offset(분) or None)
# 출차 offset이 None이면 현재 주차 중으로 남음
NOW = datetime.now(timezone.utc)

SCENARIOS = [
    # 입출차 완료 (로그만 남음)
    ("11가1111", -120, -90),
    ("22나2222", -180, -60),
    ("33다3333", -300, -240),
    # 현재 주차 중
    ("44라4444", -50, None),
    ("55마5555", -30, None),
    ("66바6666", -10, None),
]


def send_plate(client: httpx.Client, api_key: str, plate: str, ts: datetime) -> dict:
    res = client.post(
        "/api/v1/plates",
        json={"plate": plate, "timestamp": ts.isoformat()},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if res.status_code not in (200, 201):
        print(f"    ✘ 실패: {res.status_code} {res.text}")
        sys.exit(1)
    return res.json()


def main(base_url: str, api_key: str):
    with httpx.Client(base_url=base_url, timeout=10, headers={"Connection": "close"}) as client:
        print(f"▶ 입출차 데이터 주입 (api_key={api_key[:8]}...)\n")

        for plate, entry_offset, exit_offset in SCENARIOS:
            entry_ts = NOW + timedelta(minutes=entry_offset)

            # 입차
            result = send_plate(client, api_key, plate, entry_ts)
            print(f"  [ENTRY] {plate}  |  {entry_ts.strftime('%H:%M')}  →  {result}")

            if exit_offset is not None:
                exit_ts = NOW + timedelta(minutes=exit_offset)
                result = send_plate(client, api_key, plate, exit_ts)
                print(f"  [EXIT]  {plate}  |  {exit_ts.strftime('%H:%M')}  →  요금: {result.get('fee')}원, 주차: {result.get('parked_duration_minutes')}분")
            else:
                print(f"  [주차중] {plate}  →  현재 주차 중으로 유지")

        print("\n완료. get_lots.py로 결과를 확인하세요.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python scripts/seed_plates.py <api_key>")
        sys.exit(1)
    main(DEFAULT_URL, sys.argv[1])
