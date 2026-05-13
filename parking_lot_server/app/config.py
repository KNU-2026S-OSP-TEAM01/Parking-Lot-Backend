from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    database_url: str
    test_database_url: str
    secret_key: str
    aes_key: str
    hmac_key: str
    mode: str = "private"
    hub_url: str | None = None      # Public 모드에서만 필요
    enable_signup: bool = True      # false면 POST /api/v1/signup 비활성화


settings = Settings()
