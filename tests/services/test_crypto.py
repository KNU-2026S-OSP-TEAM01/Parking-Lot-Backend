from app.services.crypto import hmac_hash, aes_encrypt, aes_decrypt


# ── hmac_hash ─────────────────────────────────────────────────────────────────

def test_hmac_hash_returns_64_hex_chars():
    result = hmac_hash("12가3456")
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_hmac_hash_same_input_same_output():
    assert hmac_hash("12가3456") == hmac_hash("12가3456")


def test_hmac_hash_different_inputs_different_output():
    assert hmac_hash("12가3456") != hmac_hash("99나9999")


# ── aes_encrypt / aes_decrypt ─────────────────────────────────────────────────

def test_aes_decrypt_recovers_original():
    plate = "12가3456"
    assert aes_decrypt(aes_encrypt(plate)) == plate


def test_aes_encrypt_different_each_time():
    """랜덤 IV로 인해 같은 입력이라도 매번 다른 암호문이 생성된다."""
    plate = "12가3456"
    assert aes_encrypt(plate) != aes_encrypt(plate)


def test_aes_encrypt_output_length():
    """저장 형식: IV(12) + 암호문 + 태그(16) = 최소 28바이트 초과."""
    enc = aes_encrypt("12가3456")
    assert len(enc) > 28


def test_aes_decrypt_wrong_data_raises():
    """손상된 데이터 복호화 시 예외가 발생해야 한다."""
    import pytest
    with pytest.raises(Exception):
        aes_decrypt(b"corrupted_data_that_is_not_valid_ciphertext_at_all!!")
