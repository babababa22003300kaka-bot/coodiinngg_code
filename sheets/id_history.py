#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📜 ID History Manager
تسجيل الـ IDs المضافة للشيت والاحتفاظ بآخر 7 أيام فقط
✅ مع دعم الإضافة الدفعية
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# ⚙️ ثوابت
# ═══════════════════════════════════════════════════════════════

HISTORY_FILE = Path("data/id_history.json")
RETENTION_DAYS = 7  # الاحتفاظ بآخر 7 أيام فقط


# ═══════════════════════════════════════════════════════════════
# 🔧 دوال مساعدة داخلية (Private)
# ═══════════════════════════════════════════════════════════════


def _load_history() -> dict:
    """
    تحميل سجل الـ IDs (داخلي)
    """
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ Error loading history: {e}")
    return {"ids": []}


def _save_history(data: dict):
    """
    حفظ سجل الـ IDs (داخلي)
    """
    try:
        HISTORY_FILE.parent.mkdir(exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"❌ Error saving history: {e}")


def _cleanup_old_ids(data: dict) -> dict:
    """
    حذف الإدخالات القديمة (أكتر من 7 أيام) - داخلي
    """
    cutoff_date = datetime.now() - timedelta(days=RETENTION_DAYS)

    cleaned_ids = []
    removed_count = 0

    for entry in data.get("ids", []):
        try:
            added_at = datetime.fromisoformat(entry["added_at"])
            if added_at > cutoff_date:
                cleaned_ids.append(entry)
            else:
                removed_count += 1
        except:
            # احتفظ بالإدخالات اللي مش قادرين نقرأ تاريخها
            cleaned_ids.append(entry)

    if removed_count > 0:
        logger.info(
            f"🧹 Cleaned {removed_count} old entries (older than {RETENTION_DAYS} days)"
        )

    return {"ids": cleaned_ids}


# ═══════════════════════════════════════════════════════════════
# 📚 دوال عامة (Public API)
# ═══════════════════════════════════════════════════════════════


def load_history() -> dict:
    """
    تحميل سجل الـ IDs (للاستخدام الخارجي)
    """
    return _load_history()


def save_history(data: dict):
    """
    حفظ سجل الـ IDs (للاستخدام الخارجي)
    """
    _save_history(data)


def cleanup_old_entries(data: dict) -> dict:
    """
    حذف الإدخالات القديمة (للاستخدام الخارجي)
    """
    return _cleanup_old_ids(data)


def add_ids_to_history(ids_list: List[str]):
    """
    إضافة عدة IDs دفعة واحدة

    Args:
        ids_list: List من الـ IDs المراد إضافتها
    """
    if not ids_list:
        return

    try:
        # تحميل البيانات
        data = _load_history()

        # تنظيف القديم
        data = _cleanup_old_ids(data)

        # إضافة كل الـ IDs
        now = datetime.now().isoformat()
        added_count = 0

        for item_id in ids_list:
            # فلترة الـ IDs غير الصالحة
            if item_id and item_id not in ["N/A", "pending", "api", "", None]:
                data["ids"].append({"id": str(item_id), "added_at": now})
                added_count += 1

        # حفظ
        _save_history(data)

        if added_count > 0:
            logger.info(
                f"📝 Added {added_count} IDs to history (total: {len(data['ids'])})"
            )
        else:
            logger.debug("ℹ️ No valid IDs to add")

    except Exception as e:
        logger.exception(f"❌ Error adding multiple IDs: {e}")


def add_id_to_history(id_value: str):
    """
    إضافة ID واحد للسجل

    Args:
        id_value: الـ ID المراد إضافته
    """
    if not id_value or id_value in ["N/A", "pending", "api", "", None]:
        return

    try:
        # تحميل السجل الحالي
        history = _load_history()

        # إضافة الـ ID
        now = datetime.now().isoformat()
        history["ids"].append({"id": str(id_value), "added_at": now})

        # تنظيف القديم
        history = _cleanup_old_ids(history)

        # حفظ
        _save_history(history)

        logger.info(f"📜 Added ID {id_value} to history")
        logger.debug(f"📊 Total IDs in history: {len(history['ids'])}")

    except Exception as e:
        logger.error(f"❌ Error adding ID to history: {e}")


def get_history_count() -> int:
    """
    الحصول على عدد الـ IDs في السجل

    Returns:
        عدد الـ IDs المسجلة
    """
    try:
        history = _load_history()
        return len(history.get("ids", []))
    except:
        return 0


def check_id_exists(id_value: str) -> bool:
    """
    التحقق من وجود ID في السجل

    Args:
        id_value: الـ ID المراد البحث عنه

    Returns:
        True إذا كان موجود
    """
    try:
        history = _load_history()
        id_list = [entry.get("id") for entry in history.get("ids", [])]
        return str(id_value) in id_list
    except:
        return False


def get_recent_ids(days: int = 7) -> List[str]:
    """
    الحصول على الـ IDs المضافة في آخر X يوم

    Args:
        days: عدد الأيام (افتراضي: 7)

    Returns:
        قائمة بالـ IDs
    """
    try:
        history = _load_history()
        cutoff_date = datetime.now() - timedelta(days=days)

        recent_ids = []
        for entry in history.get("ids", []):
            try:
                added_at = datetime.fromisoformat(entry["added_at"])
                if added_at > cutoff_date:
                    recent_ids.append(entry["id"])
            except:
                continue

        return recent_ids

    except Exception as e:
        logger.error(f"❌ Error getting recent IDs: {e}")
        return []


def clear_history():
    """
    مسح السجل بالكامل (استخدام حذر!)
    """
    try:
        _save_history({"ids": []})
        logger.warning("⚠️ History cleared!")
    except Exception as e:
        logger.error(f"❌ Error clearing history: {e}")
