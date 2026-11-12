"""
The Iron Throne RPG — Error Reporting, Aggregation & Group Alert Subsystem.
Sends sanitized, debounced system errors, exceptions, frontend reports,
and user bug tickets to the private ERROR_CHAT_ID Telegram group.
"""
import asyncio
import hashlib
import html
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List

import httpx
from sqlalchemy import select, update, desc

from config import BOT_TOKEN, ERROR_CHAT_ID
from core.sanitizer import sanitize_sensitive_data, truncate_stack_trace
from database.db import AsyncSessionLocal
from database.models import SystemErrorLog

logger = logging.getLogger(__name__)

# In-memory deduplication tracking:
# fingerprint -> {"last_notified": float, "pending_count": int, "first_seen": float}
_recent_errors_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = asyncio.Lock()

# 10 minutes debounce window in seconds
DEBOUNCE_WINDOW_SECONDS = 600

# Global bot application reference (optional shortcut)
_global_bot_app = None


def set_error_reporter_bot_app(bot_app):
    """Store running Telegram Application reference"""
    global _global_bot_app
    _global_bot_app = bot_app


def compute_error_fingerprint(source: str, error_type: str, handler_name: str, message: str) -> str:
    """Generate unique 64-char hex SHA256 identifier for a specific error kind and location"""
    norm_source = (source or "unknown").lower().strip()
    norm_type = (error_type or "Error").strip()
    norm_handler = (handler_name or "unknown").strip()
    norm_msg = (message or "").strip()[:100]
    raw_key = f"{norm_source}:{norm_type}:{norm_handler}:{norm_msg}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def send_to_error_chat(text: str, parse_mode: Optional[str] = "HTML") -> bool:
    """
    Sends message to ERROR_CHAT_ID via Telegram Bot API using httpx.
    Gracefully handles Telegram markdown/HTML formatting errors by falling back to plain text.
    """
    if not ERROR_CHAT_ID or not BOT_TOKEN:
        logger.debug("ERROR_CHAT_ID yoki BOT_TOKEN sozlanmagan, guruhga yuborilmadi.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": ERROR_CHAT_ID,
        "text": text[:3900],  # Ensure strictly within Telegram 4096 char bounds
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                return True

            # If formatting failed, retry with plain text
            if parse_mode and resp.status_code in (400, 422):
                logger.warning(f"Telegram parse_mode xatosi ({resp.text}), formatlashsiz qayta urinilmoqda...")
                payload.pop("parse_mode", None)
                retry_resp = await client.post(url, json=payload)
                return retry_resp.status_code == 200

            logger.warning(f"Telegram error chat response status {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        logger.warning(f"ERROR_CHAT_ID ga xabar yuborishda tarmoq xatoligi: {e}")
        return False


async def record_error_in_db(
    fingerprint: str,
    source: str,
    error_type: str,
    error_message: str,
    handler_name: str,
    user_telegram_id: Optional[int],
    stack_trace: str,
    should_update_notified: bool = False,
) -> Tuple[SystemErrorLog, int]:
    """
    Finds or creates a SystemErrorLog entry.
    Increments occurrence_count, updates last_seen_at and last_notified_at.
    Returns (log_record, current_occurrence_count).
    """
    now = datetime.utcnow()
    async with AsyncSessionLocal() as session:
        # Check existing unresolved record by fingerprint
        stmt = (
            select(SystemErrorLog)
            .where(
                SystemErrorLog.fingerprint == fingerprint,
                SystemErrorLog.is_resolved == False
            )
            .order_by(desc(SystemErrorLog.id))
            .limit(1)
        )
        res = await session.execute(stmt)
        record = res.scalar_one_or_none()

        if record:
            record.occurrence_count = (record.occurrence_count or 1) + 1
            record.last_seen_at = now
            if user_telegram_id and not record.user_telegram_id:
                record.user_telegram_id = user_telegram_id
            if stack_trace and not record.stack_trace:
                record.stack_trace = stack_trace
            if should_update_notified:
                record.last_notified_at = now
            await session.commit()
            await session.refresh(record)
            return record, record.occurrence_count
        else:
            new_record = SystemErrorLog(
                fingerprint=fingerprint,
                source=source[:20],
                error_type=error_type[:100],
                error_message=error_message,
                handler_name=handler_name[:100],
                user_telegram_id=user_telegram_id,
                stack_trace=stack_trace,
                occurrence_count=1,
                first_seen_at=now,
                last_seen_at=now,
                last_notified_at=now if should_update_notified else None,
                is_resolved=False,
            )
            session.add(new_record)
            await session.commit()
            await session.refresh(new_record)
            return new_record, 1


async def report_system_error(
    source: str,
    error_type: str,
    error_message: str,
    handler_name: str = "unknown",
    user_telegram_id: Optional[int] = None,
    stack_trace: Optional[str] = None,
    extra_details: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Main system entry point for reporting errors from Bot, FastAPI, or Mini App.
    Applies sanitization, deduplication (10-minute aggregation), DB logging, and Telegram alerting.
    """
    # 1. Sanitize sensitive information (tokens, passwords, card numbers)
    clean_message = sanitize_sensitive_data(error_message or "Noma'lum xatolik")
    clean_stack = truncate_stack_trace(stack_trace or "", max_lines=8)
    clean_handler = sanitize_sensitive_data(handler_name or "unknown")
    clean_type = sanitize_sensitive_data(error_type or "UnknownError")

    fingerprint = compute_error_fingerprint(source, clean_type, clean_handler, clean_message)
    now_ts = time.time()
    now_dt = datetime.utcnow()
    uz_time_str = (now_dt + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S UZT")

    should_send_telegram = False
    pending_aggregated_count = 0

    async with _cache_lock:
        cached = _recent_errors_cache.get(fingerprint)
        if cached is None:
            # First time seeing this error kind
            should_send_telegram = True
            _recent_errors_cache[fingerprint] = {
                "last_notified": now_ts,
                "pending_count": 0,
                "first_seen": now_ts,
            }
        else:
            elapsed = now_ts - cached["last_notified"]
            if elapsed >= DEBOUNCE_WINDOW_SECONDS:
                # 10 minutes have elapsed since last alert, send aggregated report
                should_send_telegram = True
                pending_aggregated_count = cached["pending_count"]
                cached["last_notified"] = now_ts
                cached["pending_count"] = 0
            else:
                # Within 10-minute suppression window: suppress telegram spam, accumulate count
                cached["pending_count"] += 1
                should_send_telegram = False

    # 2. Persist in database
    try:
        db_record, total_occurrences = await record_error_in_db(
            fingerprint=fingerprint,
            source=source,
            error_type=clean_type,
            error_message=clean_message,
            handler_name=clean_handler,
            user_telegram_id=user_telegram_id,
            stack_trace=clean_stack,
            should_update_notified=should_send_telegram,
        )
    except Exception as dbe:
        logger.error(f"Xatolikni bazaga yozishda nosozlik: {dbe}")
        total_occurrences = 1

    # 3. Format and dispatch Telegram alert if debounce allowed
    if should_send_telegram:
        source_icons = {
            "bot": "🤖 #BOT_XATOLIGI",
            "miniapp": "📱 #MINIAPP_XATOLIGI",
            "api": "🌐 #API_XATOLIGI",
            "support": "📩 #MUROJAAT_XATOLIGI",
        }
        tag = source_icons.get(source.lower(), f"⚠️ #{source.upper()}_XATOLIK")

        lines = [
            f"🚨 <b>{tag}</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"⏱ <b>Vaqt:</b> <code>{html.escape(uz_time_str)}</code>",
            f"🏷 <b>Xato turi:</b> <code>{html.escape(clean_type)}</code>",
            f"📌 <b>Manzil / Handler:</b> <code>{html.escape(clean_handler)}</code>",
            f"👤 <b>Foydalanuvchi ID:</b> <code>{user_telegram_id if user_telegram_id else 'Noma‘lum'}</code>",
        ]

        if pending_aggregated_count > 0:
            lines.append(
                f"🔁 <b>Takrorlanish:</b> So‘nggi 10 daqiqada <b>{pending_aggregated_count} marta</b> takrorlandi!"
            )
        elif total_occurrences > 1:
            lines.append(
                f"📊 <b>Jami takrorlanish:</b> <b>{total_occurrences} marta</b>"
            )

        lines.append(f"\n💬 <b>Xato matni:</b>\n<pre>{html.escape(clean_message[:500])}</pre>")

        if clean_stack:
            lines.append(f"\n📋 <b>Stack Trace:</b>\n<pre>{html.escape(clean_stack[:1200])}</pre>")

        if extra_details:
            extra_str = "\n".join(f"• {k}: {v}" for k, v in extra_details.items())
            clean_extra = sanitize_sensitive_data(extra_str)
            lines.append(f"\n🔍 <b>Qo‘shimcha tafsilotlar:</b>\n<pre>{html.escape(clean_extra[:400])}</pre>")

        telegram_msg = "\n".join(lines)
        return await send_to_error_chat(telegram_msg, parse_mode="HTML")

    return True


async def send_support_ticket_to_error_chat(
    user_telegram_id: int,
    message_text: str,
    ticket_category: str = "bug",
    username: Optional[str] = None,
) -> bool:
    """
    Sends user support tickets / bug reports from /murojaat to ERROR_CHAT_ID with dedicated tag.
    """
    clean_text = sanitize_sensitive_data(message_text)
    now_dt = datetime.utcnow()
    uz_time_str = (now_dt + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S UZT")

    cat_tags = {
        "bug": "🐛 #BAG_XABARI",
        "question": "❓ #SAVOL_MUROJAAT",
        "feedback": "💡 #TAKLIF",
    }
    tag = cat_tags.get(ticket_category.lower(), "📩 #MUROJAAT")

    # Record in DB as well
    fingerprint = compute_error_fingerprint("support", ticket_category, "user_ticket", clean_text)
    try:
        await record_error_in_db(
            fingerprint=fingerprint,
            source="support",
            error_type=f"BugReport_{ticket_category.capitalize()}",
            error_message=clean_text,
            handler_name="player_support",
            user_telegram_id=user_telegram_id,
            stack_trace="",
            should_update_notified=True,
        )
    except Exception as e:
        logger.warning(f"Support ticketni DB ga yozishda xatolik: {e}")

    uname_str = f"@{username}" if username else "yo‘q"
    lines = [
        f"{tag} <b>O‘YINCHIDAN MUROJAAT</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"⏱ <b>Vaqt:</b> <code>{html.escape(uz_time_str)}</code>",
        f"👤 <b>Foydalanuvchi ID:</b> <code>{user_telegram_id}</code> ({html.escape(uname_str)})",
        f"\n💬 <b>Murojaat matni:</b>\n<blockquote>{html.escape(clean_text[:2000])}</blockquote>",
    ]

    return await send_to_error_chat("\n".join(lines), parse_mode="HTML")


# ============================================================
# ADMIN PANEL: ERROR LOG MANAGEMENT (RESOLVE & RETRIEVE)
# ============================================================

async def get_recent_errors(limit: int = 20, only_unresolved: bool = False) -> List[Dict[str, Any]]:
    """Fetches recent errors for Admin Panel dashboard"""
    async with AsyncSessionLocal() as session:
        query = select(SystemErrorLog)
        if only_unresolved:
            query = query.where(SystemErrorLog.is_resolved == False)
        query = query.order_by(desc(SystemErrorLog.last_seen_at)).limit(limit)

        res = await session.execute(query)
        logs = res.scalars().all()

        return [
            {
                "id": l.id,
                "source": l.source,
                "error_type": l.error_type,
                "error_message": l.error_message,
                "handler_name": l.handler_name,
                "user_telegram_id": l.user_telegram_id,
                "occurrence_count": l.occurrence_count or 1,
                "first_seen_at": l.first_seen_at.isoformat() if l.first_seen_at else None,
                "last_seen_at": l.last_seen_at.isoformat() if l.last_seen_at else None,
                "is_resolved": l.is_resolved,
                "resolved_at": l.resolved_at.isoformat() if l.resolved_at else None,
            }
            for l in logs
        ]


async def resolve_system_error(error_id: int, admin_telegram_id: Optional[int] = None) -> Tuple[bool, str]:
    """Marks a specific SystemErrorLog as resolved"""
    now = datetime.utcnow()
    async with AsyncSessionLocal() as session:
        record = await session.get(SystemErrorLog, error_id)
        if not record:
            return False, f"Xato #{error_id} topilmadi."

        record.is_resolved = True
        record.resolved_at = now
        record.resolved_by = admin_telegram_id
        await session.commit()

        # Remove from debounce cache if active
        async with _cache_lock:
            _recent_errors_cache.pop(record.fingerprint, None)

        return True, f"Xato #{error_id} muvaffaqiyatli 'Hal qilindi' deb belgilandi."
