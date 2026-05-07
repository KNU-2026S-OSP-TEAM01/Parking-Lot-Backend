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


def test_mode_is_valid():
    assert settings.mode in ("private", "public")
