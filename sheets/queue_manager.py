#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📦 Queue Manager
إدارة الـ 3 ملفات JSON (pending, retry, failed)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")


def load_queue(filename: str) -> Dict:
    """
    تحميل ملف queue

    Args:
        filename: اسم الملف (مثل: pending.json)

    Returns:
        Dict مع key "emails" يحتوي على list
    """
    file_path = DATA_DIR / filename

    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ Error loading {filename}: {e}")

    return {"emails": []}


def save_queue(filename: str, data: Dict):
    """
    حفظ ملف queue

    Args:
        filename: اسم الملف
        data: البيانات للحفظ
    """
    DATA_DIR.mkdir(exist_ok=True)
    file_path = DATA_DIR / filename

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"❌ Error saving {filename}: {e}")


def move_to_retry(email_data: Dict):
    """
    نقل من pending إلى retry

    Args:
        email_data: بيانات الإيميل
    """
    # تحديث عدد المحاولات
    email_data["attempts"] = email_data.get("attempts", 0) + 1
    email_data["last_attempt"] = datetime.now().isoformat()

    # إضافة لـ retry
    retry_data = load_queue("retry.json")
    retry_data["emails"].append(email_data)
    save_queue("retry.json", retry_data)

    logger.info(
        f"📝 Moved {email_data['email']} to retry queue (attempt {email_data['attempts']})"
    )


def move_to_failed(email_data: Dict):
    """
    نقل من retry إلى failed

    Args:
        email_data: بيانات الإيميل
    """
    email_data["failed_at"] = datetime.now().isoformat()

    # إضافة لـ failed
    failed_data = load_queue("failed.json")
    failed_data["emails"].append(email_data)
    save_queue("failed.json", failed_data)

    logger.warning(f"❌ Moved {email_data['email']} to failed queue")


def get_pending_batch() -> List[Dict]:
    """
    الحصول على batch من pending

    Returns:
        List من الإيميلات
    """
    data = load_queue("pending.json")
    return data.get("emails", [])


def get_retry_batch() -> List[Dict]:
    """
    الحصول على batch من retry

    Returns:
        List من الإيميلات
    """
    data = load_queue("retry.json")
    return data.get("emails", [])


def clear_batch(filename: str, processed_emails: List[str]):
    """
    مسح الإيميلات اللي اتعالجت بنجاح

    Args:
        filename: اسم الملف
        processed_emails: List من الإيميلات اللي تمت معالجتها
    """
    data = load_queue(filename)

    # إزالة الإيميلات الناجحة
    data["emails"] = [
        item for item in data["emails"] if item.get("email") not in processed_emails
    ]

    save_queue(filename, data)

    logger.info(f"✅ Cleared {len(processed_emails)} emails from {filename}")
