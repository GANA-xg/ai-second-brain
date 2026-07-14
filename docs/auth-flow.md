# Authentication Flow — AI Second Brain

## Project Overview

The AI Second Brain uses a **JWT-based authentication system** with:
- Short-lived **access tokens** (15 min default) for API authorization
- Longer-lived **refresh tokens** (30 days default) for obtaining new access tokens
- **Refresh token rotation** — each refresh invalidates the old token and issues a new pair
- **Replay attack detection** — reused refresh tokens trigger full session revocation
- **bcrypt password hashing** (12 rounds)
- **Refresh tokens stored as deterministic SHA-256 hash** for server-side lookup
- **Structured audit logging** for all auth events
- **Rate limiting** on auth endpoints

---

## Authentication Architecture

```
┌──────────────┐         ┌──────────────────┐         ┌──────────────┐
│              │  HTTPS   │                  │  HTTP   │              │
│   Client     │─────────▶│  FastAPI Backend │─────────▶│  PostgreSQL  │
│  (Browser/   │         │                  │         │              │
│   Mobile)    │◀────────│  (Nginx proxy)   │◀────────│              │
│              │  JSON    │                  │  Query   │              │
└──────────────┘         └──────────────────┘         └──────────────┘
                                  │
                                  │                     ┌──────────────┐
                                  ├────────────────────▶│  Auth Logger │
                                  │  (structured JSON)  │  (structlog) │
                                  │                     └──────────────┘
                                  │
                                  ├────────────────────▶│  Rate Limiter│
                                  │  (in-memory /w     │  (sliding     │
                                  │   Redis interface)  │   window)    │
                                  │                     └──────────────┘
```

## Token Structure

### Access Token (JWT)
```json
{
  "sub": "uuid-of-user",
  "type": "access",
  "iat": 1718000000,
  "exp": 1718000900
}
```
- Expires in **15 minutes** (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`)
- Sent as `Authorization: Bearer <token>` header
- Validated on every protected route

### Refresh Token (JWT)
```json
{
  "sub": "uuid-of-user",
  "type": "refresh",
  "iat": 1718000000,
  "exp": 1720592000
}
```
- Expires in **30 days** (configurable via `REFRESH_TOKEN_EXPIRE_DAYS`)
- Stored as **SHA-256 hash** in `refresh_tokens` table (never plaintext; deterministic for server-side lookup)
- Used **once** — rotated on each use
- Can be revoked server-side

---

## Flow Diagrams

### 1. Login Flow

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI (/auth/login)
    participant RL as Rate Limiter
    participant AuthService
    participant DB as PostgreSQL
    participant Logger as Auth Logger

    Client->>API: POST /auth/login {email, password}
    API->>RL: Check rate limit (5/min/IP)
    RL-->>API: Allowed
    API->>AuthService: login(email, password)
    AuthService->>DB: Query user by email
    DB-->>AuthService: User (or None)

    alt User not found
        AuthService->>Logger: login_failure (invalid_email)
        AuthService-->>API: ValueError
        API-->>Client: 401 Incorrect email or password
    else Password incorrect
        AuthService->>Logger: login_failure (invalid_password)
        AuthService-->>API: ValueError
        API-->>Client: 401 Incorrect email or password
    else Account inactive
        AuthService->>Logger: login_failure (inactive)
        AuthService-->>API: ValueError
        API-->>Client: 401 Account is inactive
    else Success
        AuthService->>AuthService: create_access_token()
        AuthService->>AuthService: create_refresh_token()
        AuthService->>AuthService: hash_token(refresh_token)
        AuthService->>DB: INSERT refresh_tokens (hashed)
        DB-->>AuthService: OK
        AuthService->>Logger: login_success (user_id, email)
        AuthService-->>API: {access_token, refresh_token}
        API-->>Client: 200 {access_token, refresh_token, token_type}
    end
```

### 2. Refresh Token Rotation

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI (/auth/refresh)
    participant AuthService
    participant DB as PostgreSQL
    participant Logger as Auth Logger

    Client->>API: POST /auth/refresh {refresh_token}
    API->>AuthService: refresh_token(token)
    AuthService->>AuthService: decode_token(token)
    AuthService->>AuthService: hash_password(token)

    alt Token expired or invalid
        AuthService->>Logger: refresh_failure
        AuthService-->>API: ValueError
        API-->>Client: 401 Invalid refresh token
    else Token not in DB
        AuthService->>DB: Query by hash
        DB-->>AuthService: None
        AuthService->>DB: Query revoked tokens by hash
        DB-->>AuthService: Found (replay attack!)
        AuthService->>DB: REVOKE ALL tokens for user
        AuthService->>Logger: refresh_replay_attack
        AuthService-->>API: ValueError
        API-->>Client: 401 Suspected replay attack
    else Token valid
        AuthService->>DB: GET user
        DB-->>AuthService: User active
        AuthService->>DB: REVOKE old token (set revoked_at)
        AuthService->>AuthService: create_access_token()
        AuthService->>AuthService: create_refresh_token()
        AuthService->>AuthService: hash_password(new_token)
        AuthService->>DB: INSERT new refresh_token
        DB-->>AuthService: OK
        AuthService->>Logger: refresh_success (user_id)
        AuthService-->>API: {new_access_token, new_refresh_token}
        API-->>Client: 200 {access_token, refresh_token, token_type}
    end
```

### 3. Logout Flow

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI (/auth/logout)
    participant AuthService
    participant DB as PostgreSQL
    participant Logger as Auth Logger

    Client->>API: POST /auth/logout {refresh_token}
    API->>AuthService: logout(refresh_token)
    AuthService->>AuthService: decode_token(refresh_token)
    AuthService->>AuthService: hash_password(refresh_token)
    AuthService->>DB: Find token by hash (not revoked)
    DB-->>AuthService: Token record

    alt Token not found
        AuthService-->>API: False
        API-->>Client: 400 Invalid refresh token
    else Token found
        AuthService->>DB: SET revoked_at = now
        DB-->>AuthService: OK
        AuthService->>Logger: logout (user_id)
        AuthService-->>API: True
        API-->>Client: 200 {message: "Successfully logged out"}
    end

    note over Client,Logger: Logout-all revokes ALL active refresh tokens for the user
    Client->>API: POST /auth/logout-all (Bearer access_token)
    API->>AuthService: logout_all_devices(user_id)
    AuthService->>DB: UPDATE refresh_tokens SET revoked_at=now WHERE user_id=X AND revoked_at IS NULL
    DB-->>AuthService: count N
    AuthService->>Logger: logout_all (user_id, tokens_revoked=N)
    API-->>Client: 200 {message: "Successfully logged out from N devices"}
```

### 4. Replay Attack Detection

```mermaid
sequenceDiagram
    participant Attacker
    participant API as FastAPI (/auth/refresh)
    participant AuthService
    participant DB as PostgreSQL
    participant Logger as Auth Logger

    Note over Attacker,Logger: Attacker has an old (already-used) refresh token
    Attacker->>API: POST /auth/refresh {stolen_refresh_token}
    API->>AuthService: refresh_token(token)
    AuthService->>AuthService: decode_token → valid JWT
    AuthService->>AuthService: hash_password(token)
    AuthService->>DB: Query active token by hash
    DB-->>AuthService: None (already rotated)
    AuthService->>DB: Query REVOKED tokens by hash
    DB-->>AuthService: Found! (was previously revoked)

    Note over AuthService,Logger: Replay detected — mass revocation triggered
    AuthService->>DB: REVOKE ALL tokens for this user
    AuthService->>Logger: refresh_replay_attack (user_id)
    AuthService-->>API: ValueError
    API-->>Attacker: 401 Refresh token revoked due to suspected replay attack

    Note over Attacker,Logger: All stolen tokens for this user are now useless
```

---

## Expiration Strategy

| Token | Default TTL | Why this value |
|-------|-------------|----------------|
| Access Token | 15 minutes | Short enough to limit damage if stolen; long enough to avoid excessive refreshes |
| Refresh Token | 30 days | Balances UX (don't log in every session) with security window |

When the access token expires:
1. Client receives `401 Unauthorized` from any protected endpoint
2. Client calls `POST /auth/refresh` with its refresh token
3. Server issues a **new** access token + a **new** refresh token (rotation)
4. The old refresh token is marked as revoked in the database

---

## Security Decisions

| Decision | Rationale |
|----------|-----------|
| **bcrypt (12 rounds)** | Industry standard for password hashing; 12 rounds takes ~250ms, making brute-force impractical |
| **Refresh tokens stored as bcrypt hashes** | Even if the database is leaked, refresh tokens cannot be recovered |
| **Refresh token rotation** | Each refresh invalidates the old token; a stolen refresh token can only be used once |
| **Replay attack → full revocation** | If a rotated token is reused, all user sessions are invalidated — assumes the token was compromised |
| **Access tokens are NOT stored in DB** | Stateless JWT validation avoids DB lookups on every request |
| **X-Forwarded-For respected** | Works behind Nginx or other reverse proxies |
| **Rate limiting on auth endpoints** | Mitigates brute-force and credential stuffing attacks |
| **Structured audit logging** | All auth events logged with request_id for traceability in production incidents |

---

## Failure Scenarios

| Scenario | HTTP Status | Response |
|----------|-------------|----------|
| Invalid email format | 422 | Validation error from Pydantic |
| Email already registered | 400 | "Email already registered" |
| Wrong email or password | 401 | "Incorrect email or password" (identical message for both) |
| Account inactive | 401 | "Account is inactive" |
| Expired access token | 401 | "Could not validate credentials" |
| Expired refresh token | 401 | "Invalid refresh token" |
| Replay attack | 401 | "Refresh token revoked due to suspected replay attack" |
| Rate limit exceeded | 429 | "Too many requests. Please try again later." + Retry-After header |
| No auth header | 401 | "Could not validate credentials" |
| Logout with invalid token | 400 | "Invalid refresh token" |
| Logout-all by inactive user | 400 | "Inactive user" |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (required) | HMAC secret for JWT signing |
| `ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh token TTL |
| `BCRYPT_ROUNDS` | `12` | bcrypt cost factor |
| `LOGIN_RATE_LIMIT` | `5` | Max login attempts per IP per window |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `60` | Login rate limit window |
| `REGISTER_RATE_LIMIT` | `3` | Max registrations per IP per window |
| `REGISTER_RATE_LIMIT_WINDOW_SECONDS` | `60` | Register rate limit window |
| `REFRESH_RATE_LIMIT` | `20` | Max refresh attempts per user per window |
| `REFRESH_RATE_LIMIT_WINDOW_SECONDS` | `60` | Refresh rate limit window |
| `LOGOUT_RATE_LIMIT` | `30` | Max logout attempts per user per window |
| `LOGOUT_RATE_LIMIT_WINDOW_SECONDS` | `60` | Logout rate limit window |
| `AUTH_LOG_LEVEL` | `INFO` | Log level for auth events (DEBUG, INFO, WARNING, ERROR) |

---

## Best Practices

1. **Use HTTPS in production** — tokens are transmitted in headers
2. **Store tokens securely on the client** — httpOnly cookies preferred over localStorage for web apps
3. **Implement silent refresh** — intercept 401s, refresh in background, retry the original request
4. **Monitor auth logs** — watch for replay attacks indicating token theft
5. **Set reasonable rate limits** — tune based on your user base
6. **Rotate SECRET_KEY periodically** — invalidate all existing tokens gracefully
7. **Never log tokens or passwords** — the auth logger explicitly blocks these fields

---

## Future Extensions

- **Email verification flow** — register → send verification email → activate account
- **Password reset flow** — forgot password → email link → reset
- **OAuth2 / SSO integration** — Google, GitHub login
- **MFA / TOTP** — second factor for sensitive operations
- **Redis-backed rate limiting** — swap `InMemoryRateStore` for a Redis implementation
- **Session management UI** — view and revoke active sessions from user settings
- **Account lockout** — temporary lock after N failed login attempts
- **JWT blacklist** — immediate token invalidation via Redis for critical scenarios
