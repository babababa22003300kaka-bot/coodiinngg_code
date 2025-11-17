#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚨 Google Sheets Error Notification System
In-memory error tracking with progressive retry intervals
Zero external files - Pure decorator pattern implementation
"""

import asyncio
import logging
import time
from datetime import datetime
from functools import wraps
from typing import Dict, Optional, Callable, Any
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# 🧠 IN-MEMORY STATE (No external files)
# ═══════════════════════════════════════════════════════════════════════════

# Active errors being tracked: {error_key: error_info}
_active_errors: Dict[str, Dict[str, Any]] = {}

# Cooldown tracking to prevent spam: {error_key: last_notification_timestamp}
_error_cooldown: Dict[str, float] = {}

# Global config and bot references (set by start_error_notification_worker)
_config: Optional[Dict] = None
_bot = None


# ═══════════════════════════════════════════════════════════════════════════
# 🎯 DECORATOR: Error Tracking
# ═══════════════════════════════════════════════════════════════════════════

def track_sheets_errors(operation: str, worker: str):
    """
    Decorator to track Google Sheets errors and send notifications
    
    Usage:
        @track_sheets_errors(operation="append_emails", worker="google_api")
        def some_function():
            # Your code here
    
    Args:
        operation: Name of the operation (e.g., "append_emails", "update_cell")
        worker: Worker/module name (e.g., "google_api", "pending_worker", "taken")
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            error_key = f"{worker}:{operation}"
            
            try:
                result = await func(*args, **kwargs)
                
                # ✅ Success - mark error as resolved if it was active
                _mark_error_resolved(error_key, operation, worker)
                
                return result
                
            except Exception as e:
                # 🚨 Error occurred - track and notify
                await _handle_error(error_key, operation, worker, e)
                raise  # Re-raise the exception to maintain normal error flow
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            error_key = f"{worker}:{operation}"
            
            try:
                result = func(*args, **kwargs)
                
                # ✅ Success - mark error as resolved if it was active
                _mark_error_resolved(error_key, operation, worker)
                
                return result
                
            except Exception as e:
                # 🚨 Error occurred - track and notify (sync version)
                asyncio.create_task(_handle_error(error_key, operation, worker, e))
                raise  # Re-raise the exception
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# ═══════════════════════════════════════════════════════════════════════════
# 🔧 INTERNAL: Error Handling
# ═══════════════════════════════════════════════════════════════════════════

async def _handle_error(error_key: str, operation: str, worker: str, exception: Exception):
    """Handle an error occurrence - track and notify if needed"""
    
    if not _config or not _config.get("sheets_error_notifications", {}).get("enabled", False):
        return  # System disabled
    
    current_time = time.time()
    
    # Check if this is a new error or update existing
    if error_key not in _active_errors:
        # 🆕 New error
        error_info = {
            "operation": operation,
            "worker": worker,
            "error_type": type(exception).__name__,
            "error_message": str(exception),
            "first_seen": current_time,
            "last_seen": current_time,
            "count": 1,
            "retry_count": 0,
            "last_notification": 0,  # Never notified yet
        }
        _active_errors[error_key] = error_info
        
        # Send immediate notification for new error
        await _send_error_notification(error_key, error_info, is_new=True)
        
    else:
        # 📈 Existing error - update counters
        error_info = _active_errors[error_key]
        error_info["last_seen"] = current_time
        error_info["count"] += 1
        error_info["error_message"] = str(exception)  # Update with latest message


def _mark_error_resolved(error_key: str, operation: str, worker: str):
    """Mark an error as resolved and send resolution notification"""
    
    if error_key in _active_errors:
        error_info = _active_errors[error_key]
        
        # Send resolved notification
        asyncio.create_task(_send_resolved_notification(error_key, error_info))
        
        # Remove from tracking
        del _active_errors[error_key]
        if error_key in _error_cooldown:
            del _error_cooldown[error_key]
        
        logger.info(f"✅ Error resolved: {operation} ({worker})")


# ═══════════════════════════════════════════════════════════════════════════
# 📨 TELEGRAM NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════════════════

async def _send_error_notification(error_key: str, error_info: Dict, is_new: bool = False):
    """Send error notification to Telegram group"""
    
    if not _bot:
        return
    
    config = _config.get("sheets_error_notifications", {})
    group_id = config.get("group_id")
    
    if not group_id:
        return
    
    # Check cooldown (don't spam)
    current_time = time.time()
    if error_key in _error_cooldown:
        last_notification = _error_cooldown[error_key]
        resend_interval = _get_resend_interval(error_info["retry_count"], config)
        
        if current_time - last_notification < resend_interval:
            return  # Still in cooldown
    
    # Update notification tracking
    _error_cooldown[error_key] = current_time
    error_info["last_notification"] = current_time
    error_info["retry_count"] += 1
    
    # Format notification message
    status_emoji = "🆕" if is_new else "🔁"
    duration = int(current_time - error_info["first_seen"])
    
    message = (
        f"{status_emoji} <b>خطأ في Google Sheets</b>\n\n"
        f"🔧 <b>العملية:</b> <code>{error_info['operation']}</code>\n"
        f"⚙️ <b>Worker:</b> <code>{error_info['worker']}</code>\n"
        f"❌ <b>نوع الخطأ:</b> <code>{error_info['error_type']}</code>\n\n"
        f"📋 <b>التفاصيل:</b>\n<code>{error_info['error_message'][:200]}</code>\n\n"
        f"📊 <b>الإحصائيات:</b>\n"
        f"• عدد المحاولات: {error_info['count']}\n"
        f"• المدة: {duration}s\n"
        f"• إعادة الإرسال: #{error_info['retry_count']}\n\n"
        f"⏰ <b>الوقت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    try:
        await _bot.send_message(
            chat_id=group_id,
            text=message,
            parse_mode="HTML"
        )
        logger.info(f"📨 Error notification sent: {error_key}")
    except Exception as e:
        logger.error(f"❌ Failed to send error notification: {e}")


async def _send_resolved_notification(error_key: str, error_info: Dict):
    """Send error resolved notification"""
    
    if not _bot:
        return
    
    config = _config.get("sheets_error_notifications", {})
    group_id = config.get("group_id")
    
    if not group_id:
        return
    
    duration = int(time.time() - error_info["first_seen"])
    
    message = (
        f"✅ <b>تم حل المشكلة</b>\n\n"
        f"🔧 <b>العملية:</b> <code>{error_info['operation']}</code>\n"
        f"⚙️ <b>Worker:</b> <code>{error_info['worker']}</code>\n\n"
        f"📊 <b>الإحصائيات النهائية:</b>\n"
        f"• عدد المحاولات الفاشلة: {error_info['count']}\n"
        f"• مدة المشكلة: {duration}s\n"
        f"• عدد التنبيهات: {error_info['retry_count']}\n\n"
        f"⏰ <b>الوقت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    try:
        await _bot.send_message(
            chat_id=group_id,
            text=message,
            parse_mode="HTML"
        )
        logger.info(f"✅ Resolved notification sent: {error_key}")
    except Exception as e:
        logger.error(f"❌ Failed to send resolved notification: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# ⏰ BACKGROUND WORKER: Periodic Error Reminders
# ═══════════════════════════════════════════════════════════════════════════

async def start_error_notification_worker(config: Dict, bot):
    """
    Background worker that periodically checks and resends error notifications
    
    Args:
        config: Application configuration
        bot: Telegram Bot instance
    """
    global _config, _bot
    _config = config
    _bot = bot
    
    error_config = config.get("sheets_error_notifications", {})
    
    if not error_config.get("enabled", False):
        logger.info("⚪ Error notification system disabled")
        return
    
    logger.info("🚨 Error notification worker started")
    
    while True:
        try:
            await _check_and_resend_errors()
            await _cleanup_old_errors()
            
            # Check every 10 seconds (lightweight)
            await asyncio.sleep(10)
            
        except Exception as e:
            logger.exception(f"❌ Error in notification worker: {e}")
            await asyncio.sleep(30)


async def _check_and_resend_errors():
    """Check active errors and resend notifications if needed"""
    
    if not _active_errors:
        return  # No active errors
    
    current_time = time.time()
    config = _config.get("sheets_error_notifications", {})
    
    for error_key, error_info in list(_active_errors.items()):
        # Check if it's time to resend
        last_notification = error_info.get("last_notification", 0)
        resend_interval = _get_resend_interval(error_info["retry_count"], config)
        
        if current_time - last_notification >= resend_interval:
            await _send_error_notification(error_key, error_info, is_new=False)


async def _cleanup_old_errors():
    """Auto-resolve errors that haven't occurred recently"""
    
    if not _active_errors:
        return
    
    current_time = time.time()
    config = _config.get("sheets_error_notifications", {})
    auto_resolve_timeout = config.get("auto_resolve_timeout", 60)
    
    for error_key, error_info in list(_active_errors.items()):
        # If error hasn't occurred in X seconds, consider it resolved
        time_since_last = current_time - error_info["last_seen"]
        
        if time_since_last >= auto_resolve_timeout:
            operation = error_info["operation"]
            worker = error_info["worker"]
            _mark_error_resolved(error_key, operation, worker)


def _get_resend_interval(retry_count: int, config: Dict) -> int:
    """
    Calculate resend interval with progressive backoff
    
    First 3 retries: Fast interval (40s default)
    Subsequent retries: Slow interval (120s default)
    """
    max_fast_retries = config.get("max_fast_retries", 3)
    
    if retry_count < max_fast_retries:
        return config.get("resend_interval", 40)
    else:
        return config.get("slow_resend_interval", 120)


# ═══════════════════════════════════════════════════════════════════════════
# 🔍 UTILITY: Error Status (Optional - for debugging)
# ═══════════════════════════════════════════════════════════════════════════

def get_active_errors_count() -> int:
    """Get count of currently active errors (for monitoring)"""
    return len(_active_errors)


def get_active_errors_summary() -> Dict:
    """Get summary of active errors (for debugging)"""
    return {
        error_key: {
            "operation": info["operation"],
            "worker": info["worker"],
            "count": info["count"],
            "duration": int(time.time() - info["first_seen"]),
        }
        for error_key, info in _active_errors.items()
    }
