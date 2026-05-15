# OpenPark — Parking Lot Backend

> KNU-2026S-OSP-TEAM01

주차장 관리 시스템의 백엔드 서버입니다.

---

## 프로젝트 구조

```
OSP_prj_pkl/
├── parking_lot_server/   # Parking Lot Server (FastAPI)
├── hub_server/           # Hub Server (별도 git repo)
└── docs/                 # 공용 설계 문서
    ├── plan/             # 구현 계획
    ├── ref/              # FE·클라이언트 참고 문서
    ├── result/           # 작업 결과 정리
    └── schema-history/   # DB 스키마 변경 이력
```

---

## Parking Lot Server

개별 주차장의 입출차 처리 및 관리자 API를 담당합니다.

### 기술 스택

- **언어/프레임워크**: Python 3.12 / FastAPI
- **DB**: PostgreSQL 16 (Docker)
- **인증**: JWT (사용자), API Key (카메라 클라이언트)
- **번호판 보안**: HMAC-SHA256 (조회) + AES-256-GCM (저장)

### 빠른 시작

```bash
cd parking_lot_server

# 환경 설정
python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일에서 SECRET_KEY, AES_KEY, HMAC_KEY 값 생성:
# openssl rand -hex 32

# DB 실행
docker compose up -d

# 마이그레이션
alembic upgrade head

# 서버 실행
uvicorn app.main:app --reload
```

Swagger UI: `http://localhost:8000/docs`

### 환경변수

| 변수 | 설명 |
|------|------|
| `DATABASE_URL` | PostgreSQL 연결 URL |
| `TEST_DATABASE_URL` | 테스트용 DB URL (포트 5433) |
| `SECRET_KEY` | JWT 서명 키 |
| `AES_KEY` | 번호판 AES-256 암호화 키 |
| `HMAC_KEY` | 번호판 HMAC-SHA256 키 |
| `ENABLE_SIGNUP` | `true`: 회원가입 허용 (Private), `false`: 차단 (Public) |

### API

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/signup` | 회원가입 |
| POST | `/api/v1/login` | 로그인 |
| POST | `/api/v1/lots` | 주차장 생성 |
| GET | `/api/v1/lots` | 내 주차장 목록 |
| PATCH | `/api/v1/lots/{lot_id}` | 주차장 수정 |
| DELETE | `/api/v1/lots/{lot_id}` | 주차장 삭제 |
| GET | `/api/v1/lots/{lot_id}/vehicles` | 현재 주차 차량 |
| DELETE | `/api/v1/lots/{lot_id}/vehicles/{vehicle_id}` | 수동 출차 |
| GET | `/api/v1/lots/{lot_id}/logs` | 입출차 로그 |
| POST | `/api/v1/plates` | 번호판 전송 (카메라용) |

### 테스트

```bash
cd parking_lot_server
docker compose up -d  # 테스트 DB(포트 5433) 포함
source .venv/Scripts/activate
python -m pytest
```

---

## Hub Server

여러 주차장 현황을 통합해 일반 사용자에게 제공합니다.  
PLS와 DB를 공유하며 Docker 내부 네트워크로 통신합니다.

> 별도 리포지토리: [Hub-Backend](https://github.com/KNU-2026S-OSP-TEAM01/Hub-Backend)  
> 구현 가이드: `docs/plan/hub-server-plan.md`

---

## 문서

| 문서 | 설명 |
|------|------|
| `docs/plan/parking-lot-server-plan.md` | PLS 초기 구현 계획 |
| `docs/plan/pls-redesign-plan.md` | FE 피드백 반영 재설계 계획 |
| `docs/plan/hub-server-plan.md` | Hub Server 구현 가이드 |
| `docs/plan/hub-parking-lot-integration-plan.md` | Hub↔PLS 연동 계획 |
| `docs/ref/fe-api-reference.md` | FE팀 API 명세 |
| `docs/schema-history/` | DB 스키마 변경 이력 (v2~v4) |

---

## 라이선스

MIT
