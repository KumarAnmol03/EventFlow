"""Bearer-token authentication: maps a request's token to the one source_id it may write as."""

import hmac


class AuthError(Exception):
    """Missing, malformed, or unknown credentials -> HTTP 401."""


def authenticate(authorization: str | None, agent_tokens: dict[str, str]) -> str:
    """Return the source_id bound to the bearer token in an Authorization header."""
    if not authorization:
        raise AuthError("missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError("Authorization header must be 'Bearer <token>'")
    token = token.strip()

    # Compare against every known token with a constant-time comparison, so response timing
    # doesn't reveal how many leading characters of a guess were right.
    source_id = None
    for known_token, known_source in agent_tokens.items():
        if hmac.compare_digest(token.encode(), known_token.encode()):
            source_id = known_source
    if source_id is None:
        raise AuthError("unknown token")
    return source_id
