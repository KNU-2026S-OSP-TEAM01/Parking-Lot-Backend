from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    test_database_url: str
    secret_key: str
    aes_key: str
    hmac_key: str
    mode: str = "private"

    class Config:
        env_file = ".env"


settings = Settings()
