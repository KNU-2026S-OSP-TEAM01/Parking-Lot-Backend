import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


def _aes_key() -> bytes:
    return bytes.fromhex(settings.aes_key)


def _hmac_key() -> bytes:
    return bytes.fromhex(settings.hmac_key)


def hmac_hash(plate: str) -> str:
    """번호판 → HMAC-SHA256 hex. vehicles 테이블 조회·비교에 사용."""
    return hmac.new(_hmac_key(), plate.encode(), hashlib.sha256).hexdigest()


def aes_encrypt(plate: str) -> bytes:
    """번호판 → AES-256-GCM 암호화. 저장 형식: IV(12) + 암호문 + 태그(16)."""
    iv = os.urandom(12)
    ciphertext = AESGCM(_aes_key()).encrypt(iv, plate.encode(), None)
    return iv + ciphertext


def aes_decrypt(data: bytes) -> str:
    """저장된 바이트 → 번호판 원문. 앞 12바이트를 IV로 분리해 복호화."""
    iv, ciphertext = data[:12], data[12:]
    return AESGCM(_aes_key()).decrypt(iv, ciphertext, None).decode()
