# 인증 설계 문서

> 대상: Parking Lot Server 관리자 API

---

## 개요

클라이언트(카메라)와 관리자는 인증 방식이 다르다.

| 대상 | 방식 | 위치 |
|------|------|------|
| 카메라 클라이언트 | API Key | `parking_lots.api_key` |
| 관리자 | JWT | 로그인 후 발급 |

이 문서는 관리자 JWT 인증을 다룬다.

---

## 비밀번호 저장 — bcrypt

비밀번호는 원문을 저장하지 않는다. `bcrypt`로 해시한 값만 DB에 저장한다.

```
"changeme"  →  bcrypt.hashpw()  →  "$2b$12$abc...xyz"  (60자 문자열)
```

**bcrypt의 특성:**
- 같은 비밀번호를 해시해도 매번 다른 결과가 나온다 (salt가 자동으로 포함됨)
- 따라서 저장된 해시와 비교할 때는 `bcrypt.checkpw()`를 써야 한다 — 직접 `==` 비교 불가
- 연산이 의도적으로 느리다 (brute force 방어)

**로그인 검증 흐름:**
```
입력: "changeme"
DB의 hash: "$2b$12$..."

bcrypt.checkpw("changeme", "$2b$12$...") → True/False
```

---

## JWT 발급 — 로그인

`POST /admin/login`이 성공하면 JWT(JSON Web Token)를 반환한다.

### 페이로드 구조

```json
{
  "sub":    "550e8400-e29b-...",   // user_id
  "role":   "superadmin",          // 또는 "admin"
  "lot_id": null,                  // admin이면 UUID, superadmin이면 null
  "exp":    1746700000             // 만료 시각 (Unix timestamp, 8시간 후)
}
```

`lot_id`를 페이로드에 포함하는 이유: 매 요청마다 DB에서 사용자를 조회하지 않고 토큰만으로 권한 범위를 결정하기 위해서다.

### 서명

페이로드는 `HMAC-SHA256`으로 서명된다. 서명 키는 `.env`의 `SECRET_KEY`다.

```
Header.Payload.Signature
```

서버는 요청을 받을 때 Signature를 검증해 토큰이 위조되지 않았음을 확인한다. 페이로드 자체는 Base64로 인코딩된 것이라 **누구나 디코딩할 수 있다** — 민감한 정보를 담으면 안 된다.

---

## JWT 검증 — 보호된 엔드포인트

관리자 API 요청 시 헤더에 토큰을 포함해야 한다.

```
Authorization: Bearer eyJhbGci...
```

FastAPI 의존성 `get_current_user()`가 모든 관리자 라우터에서 실행된다.

```
요청 수신
    ↓
Authorization 헤더에서 토큰 추출
    ↓
SECRET_KEY로 서명 검증 + 만료 확인
    ↓
실패 → 401 Unauthorized
성공 → payload dict 반환 (sub, role, lot_id, exp)
    ↓
라우터가 role/lot_id로 쿼리 범위 결정
```

---

## 역할별 접근 제어

토큰 페이로드의 `role`과 `lot_id`로 접근 범위를 결정한다.

```python
# admin이면 자신의 lot_id로만 쿼리
if user["role"] == "admin":
    query = query.where(ParkingLot.id == user["lot_id"])

# superadmin이면 제한 없음
```

`require_superadmin()` 의존성은 `role != "superadmin"`이면 즉시 403을 반환한다.

---

## 보안 고려사항

| 항목 | 결정 | 이유 |
|------|------|------|
| 토큰 만료 | 8시간 | refresh token 없이 단순하게 유지 |
| 알고리즘 | HS256 | 단일 서버 구조에서 충분 |
| 비밀번호 해시 | bcrypt | 검증된 표준, 느린 연산으로 brute force 방어 |
| Refresh Token | 미구현 | 현 단계 범위 밖 |
| HTTPS | 서버 배포 시 필수 | JWT가 헤더에 평문으로 전달되므로 TLS 없이는 탈취 가능 |
