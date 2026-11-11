"""
Telegram Mini App HMAC-SHA256 Authentication Middleware & Dependency.
Strict server-side validation according to Telegram WebApp specifications.
"""
import hmac
import hashlib
import json
import time
import urllib.parse
from typing import Dict, Any, Optional, Tuple
from fastapi import Request, Header, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from config import BOT_TOKEN
from database import AsyncSessionLocal, crud, models
from api.rate_limiter import SlidingWindowRateLimiter

# Player-level rate limiter: 20 requests per 5 seconds per player
player_rate_limiter = SlidingWindowRateLimiter(max_requests=20, window_seconds=5)


def validate_telegram_init_data(
    init_data_raw: str,
    bot_token: Optional[str] = None,
    max_age_seconds: int = 86400,
) -> Dict[str, Any]:
    """
    Validates Telegram WebApp initData string using HMAC-SHA256.

    Telegram Spec:
    1. Parse raw query string into key-value pairs.
    2. Extract 'hash'.
    3. Filter out 'hash', sort remaining keys alphabetically, build 'key=value\\n'.
    4. Compute secret_key = HMAC_SHA256(b"WebAppData", bot_token.encode()).
    5. Compute signature = HMAC_SHA256(secret_key, data_check_string).
    6. Verify signature match with constant-time compare.
    7. Verify auth_date freshness against replay attacks.
    """
    if not init_data_raw or not isinstance(init_data_raw, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autentifikatsiya ma'lumotlari mavjud emas (Missing initData)."
        )

    token = bot_token or BOT_TOKEN
    if not token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Serverda Telegram Bot Token sozlanmagan."
        )

    # 1. Parse URL query string
    try:
        parsed_pairs = urllib.parse.parse_qsl(init_data_raw.strip(), keep_blank_values=True)
        data_dict = dict(parsed_pairs)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="initData formati noto'g'ri."
        )

    # 2. Extract hash
    received_hash = data_dict.pop("hash", None)
    if not received_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="initData imzosi (hash) topilmadi."
        )

    # 3. Build data check string sorted alphabetically
    check_items = [f"{k}={v}" for k, v in sorted(data_dict.items())]
    data_check_string = "\n".join(check_items)

    # 4. Generate secret key
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()

    # 5. Calculate HMAC signature
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    # 6. Compare hash in constant time
    if not hmac.compare_digest(calculated_hash.lower(), received_hash.lower()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Soxta yoki yaroqsiz initData imzosi (Invalid HMAC signature)."
        )

    # 7. Check auth_date expiration
    try:
        auth_date = int(data_dict.get("auth_date", 0))
    except (ValueError, TypeError):
        auth_date = 0

    if auth_date <= 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="initData auth_date sanasi yaroqsiz."
        )

    now = int(time.time())
    if max_age_seconds > 0 and (now - auth_date > max_age_seconds):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="initData autentifikatsiya muddati tugagan (Expired session)."
        )

    # 8. Parse and validate user JSON
    user_raw = data_dict.get("user")
    if not user_raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="initData tarkibida foydalanuvchi ma'lumoti (user) yo'q."
        )

    try:
        user_info = json.loads(user_raw)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user JSON formati noto'g'ri."
        )

    if "id" not in user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user ma'lumotida Telegram ID mavjud emas."
        )

    data_dict["user"] = user_info
    data_dict["auth_date"] = auth_date
    return data_dict


def generate_test_init_data(
    telegram_id: int,
    username: str = "testlord",
    first_name: str = "Lord",
    bot_token: Optional[str] = None,
    auth_date: Optional[int] = None,
) -> str:
    """
    Testlar va integratsiya uchun qonuniy imzolangan initData yaratuvchi yordamchi funksiya.
    """
    token = bot_token or BOT_TOKEN
    now = auth_date if auth_date is not None else int(time.time())
    user_payload = {
        "id": telegram_id,
        "first_name": first_name,
        "username": username,
        "language_code": "uz",
    }
    params = {
        "auth_date": str(now),
        "query_id": "AAHk_test_query",
        "user": json.dumps(user_payload, separators=(",", ":")),
    }
    check_str = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    sig = hmac.new(secret_key, check_str.encode("utf-8"), hashlib.sha256).hexdigest()
    params["hash"] = sig
    return urllib.parse.urlencode(params)


async def get_db_session():
    """FastAPI dependency for yielding database session."""
    async with AsyncSessionLocal() as session:
        yield session


def extract_init_data_from_request(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
) -> str:
    """Extract initData string from standard headers."""
    if x_telegram_init_data:
        return x_telegram_init_data.strip()
    if authorization:
        auth_val = authorization.strip()
        if auth_val.lower().startswith("tma "):
            return auth_val[4:].strip()
        if auth_val.lower().startswith("bearer "):
            return auth_val[7:].strip()
        return auth_val
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Telegram autentifikatsiya sarlavhasi (Authorization yoki X-Telegram-Init-Data) yetishmayapti."
    )


async def get_current_player(
    raw_init_data: str = Depends(extract_init_data_from_request),
    session: AsyncSession = Depends(get_db_session),
) -> Tuple[models.User, Dict[str, Any]]:
    """
    FastAPI Dependency:
    1. Validates initData cryptographically.
    2. Applies player-specific rate limiting.
    3. Resolves User from database strictly by verified telegram_id.
    4. Ignores any request body ID to prevent spoofing.
    """
    validated = validate_telegram_init_data(raw_init_data)
    user_info = validated["user"]
    telegram_id = int(user_info["id"])

    # Enforce per-player rate limiting
    player_rate_limiter.check(f"player_{telegram_id}")

    # Fetch user from DB
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Lord ro'yxatdan o'tmagan! Avval Telegram botimizda /start buyrug'ini bosing."
        )

    if getattr(user, "is_banned", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sizning hisobingiz bloklangan."
        )

    return user, validated


async def get_current_player_or_none(
    raw_init_data: str = Depends(extract_init_data_from_request),
    session: AsyncSession = Depends(get_db_session),
) -> Tuple[Optional[models.User], Dict[str, Any]]:
    """
    FastAPI Dependency:
    HMAC initData ni tekshiradi.
    Foydalanuvchi DB da bo'lsa (user, validated), bo'lmasa (None, validated) qaytaradi.
    Bu yangi o'yinchilar Mini Appda to'g'ridan-to'g'ri ro'yxatdan o'tishi uchun imkon beradi.
    """
    validated = validate_telegram_init_data(raw_init_data)
    user_info = validated["user"]
    telegram_id = int(user_info["id"])

    # Enforce per-player rate limiting
    player_rate_limiter.check(f"player_{telegram_id}")

    # Fetch user from DB
    user = await crud.get_user_by_telegram_id(session, telegram_id)
    if user and getattr(user, "is_banned", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sizning hisobingiz bloklangan."
        )

    return user, validated


async def require_admin_player(
    auth: Tuple[models.User, Dict[str, Any]] = Depends(get_current_player),
) -> Tuple[models.User, Dict[str, Any]]:
    """
    Faqat ADMIN_IDS ro'yxatidagi bosh adminlar uchun ruxsat beruvchi dependency.
    """
    user, validated = auth
    from config import ADMIN_IDS
    if user.telegram_id not in ADMIN_IDS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ushbu amal faqat Vesteros Bosh Administratorlari uchun ruxsat etilgan."
        )
    return user, validated
