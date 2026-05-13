from app.config import settings


def test_database_url_is_postgresql():
    assert "postgresql" in settings.database_url


def test_secret_key_is_hex_64():
    assert len(settings.secret_key) == 64
    assert all(c in "0123456789abcdef" for c in settings.secret_key)


def test_aes_key_is_hex_64():
    assert len(settings.aes_key) == 64
    assert all(c in "0123456789abcdef" for c in settings.aes_key)


def test_hmac_key_is_hex_64():
    assert len(settings.hmac_key) == 64
    assert all(c in "0123456789abcdef" for c in settings.hmac_key)


def test_test_database_url_is_different_from_database_url():
    """테스트 DB와 개발 DB가 분리되어 있는지 확인."""
    assert settings.test_database_url != settings.database_url


def test_enable_signup_is_bool():
    assert isinstance(settings.enable_signup, bool)
