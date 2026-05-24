"""
seed_integration.py로 생성한 계정으로 주차장 목록/상세를 조회하는 스크립트

사용법:
    python scripts/get_lots.py               # 목록 조회 (주차 차량 + 로그 포함)
    python scripts/get_lots.py <lot_id>      # 단건 조회 (주차 차량 + 로그 포함)
"""
import sys

import httpx

DEFAULT_URL = "http://localhost:8000"

USER = {"username": "testowner", "password": "testpass123"}


def main(base_url: str, lot_id: str | None = None):
    with httpx.Client(base_url=base_url, timeout=10) as client:

        # 1. 로그인
        print("▶ 로그인 중...")
        res = client.post("/api/v1/login", json=USER)
        if res.status_code != 200:
            print(f"  ✘ 로그인 실패: {res.status_code} {res.text}")
            sys.exit(1)
        token = res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("  ✔ 토큰 발급 완료\n")

        # 2. 조회
        if lot_id:
            res = client.get(f"/api/v1/lots/{lot_id}", headers=headers)
            if res.status_code == 404:
                print("  ✘ 해당 주차장을 찾을 수 없음")
                sys.exit(1)
            elif res.status_code != 200:
                print(f"  ✘ 실패: {res.status_code} {res.text}")
                sys.exit(1)
            lots = [res.json()]
        else:
            res = client.get("/api/v1/lots", headers=headers)
            if res.status_code != 200:
                print(f"  ✘ 실패: {res.status_code} {res.text}")
                sys.exit(1)
            lots = res.json()
            print(f"▶ 주차장 총 {len(lots)}개\n")

        for lot in lots:
            lid = lot["id"]
            vehicles = _fetch(client, f"/api/v1/lots/{lid}/vehicles", headers)
            logs = _fetch(client, f"/api/v1/lots/{lid}/logs", headers)
            _print_lot(lot, vehicles, logs)


def _fetch(client: httpx.Client, url: str, headers: dict) -> list:
    res = client.get(url, headers=headers)
    return res.json() if res.status_code == 200 else []


def _print_lot(lot: dict, vehicles: list, logs: list):
    print(f"  {'═' * 50}")
    print(f"  id             : {lot['id']}")
    print(f"  name           : {lot['name']}")
    print(f"  address        : {lot['address']}")
    print(f"  latitude       : {lot['latitude']}")
    print(f"  longitude      : {lot['longitude']}")
    print(f"  spaces         : {lot['available_spaces']} 남음 / {lot['total_spaces']} 전체")
    print(f"  base_fee       : {lot['base_fee']}원 / {lot['base_duration_minutes']}분")
    print(f"  extra_fee      : {lot['extra_fee_per_unit']}원 / {lot['extra_fee_unit_minutes']}분")
    print(f"  daily_max_fee  : {lot['daily_max_fee']}원" if lot['daily_max_fee'] else "  daily_max_fee  : 없음")
    print(f"  api_key        : {lot['api_key']}")

    print(f"\n  [주차 중인 차량] {len(vehicles)}대")
    if vehicles:
        for v in vehicles:
            print(f"    • {v['plate']}  |  입차: {v['entered_at']}")
    else:
        print("    (없음)")

    print(f"\n  [입출차 로그] 최근 {len(logs)}건")
    if logs:
        for log in logs:
            fee = f"  요금: {log['fee']}원" if log['fee'] is not None else ""
            print(f"    • [{log['event_type'].upper()}] {log['plate']}  |  {log['client_timestamp']}{fee}")
    else:
        print("    (없음)")
    print()


if __name__ == "__main__":
    _lot_id = sys.argv[1] if len(sys.argv) > 1 else None
    main(DEFAULT_URL, _lot_id)
