from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    database_url: str
    test_database_url: str
    secret_key: str
    aes_key: str
    hmac_key: str
    enable_signup: bool = True      # false면 POST /api/v1/signup 비활성화
    frontend_url: str = ""          # CORS 허용할 FE 출처. 빈 문자열이면 CORS 미들웨어 미등록


settings = Settings()
