"""
PLS 연동 테스트용 더미 데이터 주입 스크립트

사용법:
    python scripts/seed_integration.py [--base-url http://localhost:8000]

실행 전 PLS가 실행 중이어야 한다:
    docker compose up db app -d
    alembic upgrade head
"""
import argparse
import sys

import httpx

DEFAULT_URL = "http://localhost:8000"

USER = {"username": "testowner", "email": "testowner@openpark.local", "password": "testpass123"}

LOTS = [
    {
        "name": "북문 주차장",
        "address": "경북대학교 북문 앞",
        "total_spaces": 100,
        "base_fee": 1000,
        "base_duration_minutes": 30,
        "extra_fee_per_unit": 200,
        "extra_fee_unit_minutes": 10,
        "daily_max_fee": 10000,
    },
    {
        "name": "남문 주차장",
        "address": "경북대학교 남문 앞",
        "total_spaces": 50,
        "base_fee": 500,
        "base_duration_minutes": 60,
        "extra_fee_per_unit": 100,
        "extra_fee_unit_minutes": 10,
        "daily_max_fee": None,
    },
]


def main(base_url: str):
    with httpx.Client(base_url=base_url, timeout=10) as client:

        # 1. 회원가입
        print("▶ 회원가입 중...")
        res = client.post("/api/v1/signup", json=USER)
        if res.status_code == 201:
            print(f"  ✔ 계정 생성: {USER['username']}")
        elif res.status_code == 409:
            print(f"  - 이미 존재하는 계정, 로그인으로 진행")
        else:
            print(f"  ✘ 실패: {res.status_code} {res.text}")
            sys.exit(1)

        # 2. 로그인
        print("▶ 로그인 중...")
        res = client.post("/api/v1/login", json={
            "username": USER["username"],
            "password": USER["password"],
        })
        if res.status_code != 200:
            print(f"  ✘ 로그인 실패: {res.status_code} {res.text}")
            sys.exit(1)
        token = res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"  ✔ 토큰 발급 완료")

        # 3. 주차장 생성
        print("▶ 주차장 생성 중...")
        for lot in LOTS:
            res = client.post("/api/v1/lots", json=lot, headers=headers)
            if res.status_code == 201:
                body = res.json()
                print(f"  ✔ [{body['name']}] id={body['id']} api_key={body['api_key']}")
            else:
                print(f"  ✘ 실패: {res.status_code} {res.text}")
                sys.exit(1)

        print("\n완료. Hub에서 확인:")
        print("  curl http://localhost:8001/api/v1/lots")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_URL)
    args = parser.parse_args()
    main(args.base_url)
