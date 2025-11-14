#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚠️ Google Sheets Error Notification System
نظام إشعارات أخطاء Google Sheets

✅ Pure in-memory (بدون ملفات خارجية)
✅ Decorator pattern (نظيف ومرن)
✅ Progressive retry intervals
✅ Auto-resolve detection
✅ Direct Telegram notifications
"""

import asyncio
import logging
import time
from datetime import datetime
from functools import wraps
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 📊 In-Memory Error Tracking
# ═══════════════════════════════════════════════════════════════

# {error_key: {"first_seen": float, "last_sent": float, "count": int, "details": str}}
_active_errors: Dict[str, Dict] = {}

# Last notification time for each error (spam prevention)
_last_notification: Dict[str, float] = {}

# Global telegram bot instance (set by worker)
_telegram_bot = None
_config = None


# ═══════════════════════════════════════════════════════════════
# 🎯 Configuration Helpers
# ═══════════════════════════════════════════════════════════════


def is_enabled() -> bool:
    """Check if error notifications are enabled"""
    if not _config:
        return False
    return _config.get("sheets_error_notifications", {}).get("enabled", False)


def get_resend_interval() -> int:
    """Get the resend interval from config (مرن)"""
    if not _config:
        return 40
    return _config.get("sheets_error_notifications", {}).get("resend_interval", 40)


def get_max_fast_retries() -> int:
    """Get max fast retries before slowing down"""
    if not _config:
        return 3
    return _config.get("sheets_error_notifications", {}).get("max_fast_retries", 3)


def get_slow_resend_interval() -> int:
    """Get slow resend interval (after max fast retries)"""
    if not _config:
        return 120
    return _config.get("sheets_error_notifications", {}).get("slow_resend_interval", 120)


def get_auto_resolve_timeout() -> int:
    """Get auto-resolve timeout (seconds of silence before considering resolved)"""
    if not _config:
        return 60
    return _config.get("sheets_error_notifications", {}).get("auto_resolve_timeout", 60)


def get_target_group_id() -> Optional[int]:
    """Get target Telegram group ID"""
    if not _config:
        return None
    return _config.get("sheets_error_notifications", {}).get("group_id")


# ═══════════════════════════════════════════════════════════════
# 📧 Notification Sending
# ═══════════════════════════════════════════════════════════════


async def send_error_notification(
    error_key: str,
    worker: str,
    operation: str,
    error_type: str,
    details: str,
    attempt: int,
    duration: Optional[float] = None,
    is_resolved: bool = False,
):
    """
    إرسال إشعار خطأ للتليجرام

    Args:
        error_key: مفتاح الخطأ الفريد
        worker: اسم الـ Worker
        operation: اسم العملية
        error_type: نوع الخطأ
        details: تفاصيل الخطأ
        attempt: رقم المحاولة
        duration: مدة الخطأ (للرسائل resolved)
        is_resolved: هل تم حل المشكلة؟
    """
    if not _telegram_bot or not is_enabled():
        return

    group_id = get_target_group_id()
    if not group_id:
        logger.warning("⚠️ No target group ID configured for error notifications")
        return

    try:
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S")

        if is_resolved:
            # ✅ Resolved notification
            duration_str = f"{int(duration)} ثانية" if duration < 60 else f"{int(duration/60)} دقيقة"
            
            message = (
                f"✅ *تم حل المشكلة!*\n\n"
                f"🔧 Worker: `{worker}`\n"
                f"⚙️ العملية: `{operation}`\n"
                f"✓ الخطأ: `{error_type}`\n\n"
                f"⏱️ استمرت: {duration_str}\n"
                f"🔄 عدد المحاولات: {attempt}\n"
                f"⏰ الوقت: {time_str}"
            )
        else:
            # ⚠️ Error notification
            if attempt == 1:
                # First notification
                message = (
                    f"⚠️ *خطأ في Google Sheets*\n\n"
                    f"🔧 Worker: `{worker}`\n"
                    f"⚙️ العملية: `{operation}`\n"
                    f"❌ النوع: `{error_type}`\n"
                    f"📝 التفاصيل: `{details}`\n\n"
                    f"⏰ الوقت: {time_str}\n"
                    f"🔄 المحاولة: {attempt}\n\n"
                    f"💡 سأعيد المحاولة بعد {get_resend_interval()} ثانية"
                )
            else:
                # Retry notification
                duration_str = f"{int(duration)} ثانية" if duration < 60 else f"{int(duration/60)} دقيقة"
                
                message = (
                    f"⚠️ *المشكلة مستمرة*\n\n"
                    f"🔧 Worker: `{worker}`\n"
                    f"❌ الخطأ: `{error_type}`\n"
                    f"🔄 المحاولة: {attempt}\n"
                    f"⏱️ مستمرة منذ: {duration_str}\n\n"
                )
                
                # Determine next interval
                if attempt >= get_max_fast_retries():
                    next_interval = get_slow_resend_interval()
                else:
                    next_interval = get_resend_interval()
                
                message += f"💡 سأعيد المحاولة بعد {next_interval} ثانية"

        # Send notification
        await _telegram_bot.send_message(
            chat_id=group_id,
            text=message,
            parse_mode="Markdown",
        )

        logger.info(f"✅ Error notification sent to group {group_id}: {error_key}")

    except Exception as e:
        logger.error(f"❌ Failed to send error notification: {e}")


# ═══════════════════════════════════════════════════════════════
# 🎯 Error Tracking Logic
# ═══════════════════════════════════════════════════════════════


def generate_error_key(worker: str, operation: str, error_type: str) -> str:
    """Generate unique error key"""
    return f"{worker}:{operation}:{error_type}"


async def track_error(worker: str, operation: str, error_type: str, details: str):
    """
    Track an error occurrence

    Args:
        worker: Worker name
        operation: Operation name
        error_type: Error type
        details: Error details
    """
    if not is_enabled():
        return

    error_key = generate_error_key(worker, operation, error_type)
    now = time.time()

    # Check if this is a new error or existing
    if error_key not in _active_errors:
        # New error - send immediate notification
        _active_errors[error_key] = {
            "first_seen": now,
            "last_sent": now,
            "last_occurrence": now,
            "count": 1,
            "worker": worker,
            "operation": operation,
            "error_type": error_type,
            "details": details,
        }

        # Send first notification
        await send_error_notification(
            error_key=error_key,
            worker=worker,
            operation=operation,
            error_type=error_type,
            details=details,
            attempt=1,
        )
    else:
        # Existing error - update last occurrence
        _active_errors[error_key]["last_occurrence"] = now
        _active_errors[error_key]["details"] = details  # Update details


async def check_resolved_errors():
    """
    Check if any errors have been resolved (no occurrence for X seconds)
    """
    if not is_enabled():
        return

    now = time.time()
    timeout = get_auto_resolve_timeout()
    resolved_keys = []

    for error_key, info in list(_active_errors.items()):
        last_occurrence = info["last_occurrence"]
        
        # If no occurrence for timeout seconds, consider resolved
        if now - last_occurrence >= timeout:
            resolved_keys.append(error_key)
            
            # Send resolved notification
            duration = now - info["first_seen"]
            await send_error_notification(
                error_key=error_key,
                worker=info["worker"],
                operation=info["operation"],
                error_type=info["error_type"],
                details=info["details"],
                attempt=info["count"],
                duration=duration,
                is_resolved=True,
            )

    # Remove resolved errors
    for key in resolved_keys:
        del _active_errors[key]
        logger.info(f"✅ Error auto-resolved: {key}")


async def resend_notifications():
    """
    Resend notifications for active errors based on intervals
    """
    if not is_enabled():
        return

    now = time.time()

    for error_key, info in list(_active_errors.items()):
        last_sent = info["last_sent"]
        count = info["count"]
        
        # Determine interval based on attempt count
        if count >= get_max_fast_retries():
            interval = get_slow_resend_interval()
        else:
            interval = get_resend_interval()
        
        # Check if it's time to resend
        if now - last_sent >= interval:
            # Increment count and update last_sent
            info["count"] += 1
            info["last_sent"] = now
            
            # Calculate duration
            duration = now - info["first_seen"]
            
            # Resend notification
            await send_error_notification(
                error_key=error_key,
                worker=info["worker"],
                operation=info["operation"],
                error_type=info["error_type"],
                details=info["details"],
                attempt=info["count"],
                duration=duration,
            )


# ═══════════════════════════════════════════════════════════════
# 🎨 Decorator
# ═══════════════════════════════════════════════════════════════


def track_sheets_errors(operation: str, worker: str):
    """
    Decorator to track Google Sheets errors

    Args:
        operation: Operation name (e.g., "append_emails")
        worker: Worker name (e.g., "google_api", "pending_worker")

    Usage:
        @track_sheets_errors(operation="append_emails", worker="google_api")
        async def append_emails(self, emails_data):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                
                # Check if result indicates failure
                if isinstance(result, tuple) and len(result) >= 2:
                    success, message = result[0], result[1]
                    if not success:
                        # Operation failed
                        error_type = "Operation Failed"
                        if "rate limit" in message.lower():
                            error_type = "Rate Limit"
                        elif "quota" in message.lower():
                            error_type = "Quota Exceeded"
                        elif "auth" in message.lower():
                            error_type = "Authentication Error"
                        
                        await track_error(worker, operation, error_type, message)
                
                return result
                
            except Exception as e:
                # Exception occurred
                error_type = type(e).__name__
                details = str(e)
                
                await track_error(worker, operation, error_type, details)
                
                # Re-raise exception
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                
                # Check if result indicates failure
                if isinstance(result, tuple) and len(result) >= 2:
                    success, message = result[0], result[1]
                    if not success:
                        # Operation failed
                        error_type = "Operation Failed"
                        if "rate limit" in message.lower():
                            error_type = "Rate Limit"
                        elif "quota" in message.lower():
                            error_type = "Quota Exceeded"
                        elif "auth" in message.lower():
                            error_type = "Authentication Error"
                        
                        # Can't await in sync function, so we schedule it
                        asyncio.create_task(track_error(worker, operation, error_type, message))
                
                return result
                
            except Exception as e:
                # Exception occurred
                error_type = type(e).__name__
                details = str(e)
                
                # Schedule async tracking
                asyncio.create_task(track_error(worker, operation, error_type, details))
                
                # Re-raise exception
                raise
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# ═══════════════════════════════════════════════════════════════
# 🔄 Background Worker
# ═══════════════════════════════════════════════════════════════


async def error_notification_worker():
    """
    Background worker that periodically:
    1. Resends notifications for active errors
    2. Checks for resolved errors
    """
    logger.info("🚀 Error Notification Worker started")
    
    check_interval = 10  # Check every 10 seconds
    
    while True:
        try:
            # Resend notifications for active errors
            await resend_notifications()
            
            # Check for auto-resolved errors
            await check_resolved_errors()
            
            # Sleep
            await asyncio.sleep(check_interval)
            
        except Exception as e:
            logger.exception(f"❌ Error in notification worker: {e}")
            await asyncio.sleep(30)


async def start_error_notification_worker(config: Dict, telegram_bot):
    """
    Start the error notification worker

    Args:
        config: Application configuration
        telegram_bot: Telegram bot instance
    """
    global _telegram_bot, _config
    
    _config = config
    _telegram_bot = telegram_bot
    
    if not is_enabled():
        logger.info("⚠️ Error notification system is disabled")
        return
    
    group_id = get_target_group_id()
    if not group_id:
        logger.error("❌ No target group ID configured!")
        return
    
    logger.info(f"📱 Error notifications will be sent to group: {group_id}")
    logger.info(f"⏱️ Resend interval: {get_resend_interval()}s")
    logger.info(f"🔄 Max fast retries: {get_max_fast_retries()}")
    logger.info(f"⏱️ Slow interval: {get_slow_resend_interval()}s")
    logger.info(f"🕐 Auto-resolve timeout: {get_auto_resolve_timeout()}s")
    
    # Start worker
    await error_notification_worker()
