import jwt


def validate_jwt(token: str, audience: str, secret: str) -> dict:
    """Validates and decodes a JWT. Raises jwt.InvalidTokenError on failure."""
    return jwt.decode(
        token, secret, algorithms=["HS256"], audience=audience, leeway=5
    )
