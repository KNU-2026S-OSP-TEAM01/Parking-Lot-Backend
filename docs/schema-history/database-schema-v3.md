# OpenPark 데이터베이스 스키마 변경 이력 v3

> 작성일: 2026-05-08  
> 기준 버전: `database-schema-v2.md`

---

## 변경 사항

### `entry_exit_logs.event_type` CHECK 제약 확장

**변경 전 (v2)**

```sql
event_type VARCHAR(5) NOT NULL CHECK (event_type IN ('entry', 'exit'))
```

**변경 후 (v3)**

```sql
event_type VARCHAR(5) NOT NULL CHECK (event_type IN ('entry', 'exit', 'admin'))
```

**변경 이유**

관리자가 예외 상황(카메라 오류, 강제 퇴거 등)에서 `DELETE /admin/vehicles/{vehicle_id}`로 수동 출차 처리할 때, 일반 출차(`exit`)와 구분하여 관리자 조치(`admin`)임을 로그에 명시하기 위함.

**Alembic 마이그레이션**: `cb4323d51ca7_add_admin_to_event_type.py`
