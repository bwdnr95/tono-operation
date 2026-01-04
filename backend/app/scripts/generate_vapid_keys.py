#!/usr/bin/env python3
"""
VAPID 키 생성 스크립트

Browser Push Notification을 위한 VAPID 키 쌍 생성.
생성된 키를 환경변수에 설정해야 함.

사용법:
    pip install cryptography
    python generate_vapid_keys.py
"""

import base64

try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
except ImportError:
    print("Error: cryptography not installed")
    print("Run: pip install cryptography")
    exit(1)


def generate_vapid_keys():
    """VAPID 키 쌍 생성 (ECDSA P-256)"""
    
    # P-256 (secp256r1) 개인키 생성
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    
    # 공개키 추출
    public_key = private_key.public_key()
    
    # 개인키 → Raw bytes (32 bytes)
    private_numbers = private_key.private_numbers()
    private_key_bytes = private_numbers.private_value.to_bytes(32, byteorder='big')
    
    # 공개키 → Uncompressed point (65 bytes: 0x04 + x + y)
    public_key_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    
    # URL-safe Base64 인코딩 (padding 제거)
    private_key_b64 = base64.urlsafe_b64encode(private_key_bytes).decode('utf-8').rstrip('=')
    public_key_b64 = base64.urlsafe_b64encode(public_key_bytes).decode('utf-8').rstrip('=')
    
    print("=" * 60)
    print("VAPID Keys Generated!")
    print("=" * 60)
    print()
    print("# Add these to your .env file or server environment:")
    print()
    print(f"VAPID_PUBLIC_KEY={public_key_b64}")
    print(f"VAPID_PRIVATE_KEY={private_key_b64}")
    print("VAPID_CLAIMS_EMAIL=mailto:admin@tono.co.kr")
    print()
    print("=" * 60)
    print()
    print("# Verification:")
    print(f"# Public key length: {len(public_key_b64)} chars (expected ~87)")
    print(f"# Private key length: {len(private_key_b64)} chars (expected ~43)")
    print()


if __name__ == "__main__":
    generate_vapid_keys()
