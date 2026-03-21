import time

import jwt


def create_jwt(subject: str, audience: str, secret: str, expires_in: int = 300) -> str:
    now = int(time.time())
    payload = {
        "sub": subject,
        "aud": audience,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def validate_jwt(token: str, audience: str, secret: str) -> dict:
    """Validates and decodes a JWT. Raises jwt.InvalidTokenError on failure."""
    return jwt.decode(
        token, secret, algorithms=["HS256"], audience=audience, leeway=5
    )
