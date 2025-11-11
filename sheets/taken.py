#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
💰 Taken Handler - معالج الكوينز المسحوبة
✅ معالجة AMOUNT_TAKEN و DISABLED تلقائياً
✅ بسيط - بدون تعقيد - بدون retry
"""

import asyncio
import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 📂 ثوابت
# ═══════════════════════════════════════════════════════════════

TAKEN_QUEUE_FILE = Path("data/Taken.json")
ID_HISTORY_FILE = Path("data/id_history.json")


# ═══════════════════════════════════════════════════════════════
# 📝 Queue Management
# ═══════════════════════════════════════════════════════════════


def load_taken_queue() -> List[Dict]:
    """تحميل queue الكوينز المسحوبة"""
    if TAKEN_QUEUE_FILE.exists():
        try:
            with open(TAKEN_QUEUE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("items", [])
        except Exception as e:
            logger.error(f"❌ Error loading Taken.json: {e}")
    return []


def save_taken_queue(items: List[Dict]):
    """حفظ queue الكوينز المسحوبة"""
    try:
        TAKEN_QUEUE_FILE.parent.mkdir(exist_ok=True)
        with open(TAKEN_QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump({"items": items}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"❌ Error saving Taken.json: {e}")


def add_to_taken_queue(
    account_id: str, email: str, status: str, taken_value: str
) -> bool:
    """
    إضافة عملية جديدة للـ queue

    Args:
        account_id: ID الحساب
        email: البريد الإلكتروني
        status: الحالة (AMOUNT_TAKEN أو DISABLED)
        taken_value: قيمة الكوينز المسحوبة

    Returns:
        True إذا تمت الإضافة بنجاح
    """
    try:
        items = load_taken_queue()

        # تجنب التكرار - نسجل آخر قيمة فقط (overwrite)
        items = [item for item in items if item.get("id") != account_id]

        new_item = {
            "id": account_id,
            "email": email,
            "status": status,
            "taken": str(taken_value),
            "added_at": datetime.now().isoformat(),
        }

        items.append(new_item)
        save_taken_queue(items)

        logger.info(
            f"📝 Added to Taken queue: {email} (ID: {account_id}, Status: {status}, Taken: {taken_value})"
        )
        return True

    except Exception as e:
        logger.error(f"❌ Error adding to Taken queue: {e}")
        return False


def clear_taken_entry(account_id: str):
    """مسح عملية من الـ queue (نجاح أو فشل)"""
    try:
        items = load_taken_queue()
        original_count = len(items)

        items = [item for item in items if item.get("id") != account_id]

        if len(items) < original_count:
            save_taken_queue(items)
            logger.info(f"🗑️ Cleared from Taken queue: ID {account_id}")
            return True

        return False

    except Exception as e:
        logger.error(f"❌ Error clearing from Taken queue: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# 🔍 التحقق من ID History
# ═══════════════════════════════════════════════════════════════


def check_id_in_history(account_id: str) -> bool:
    """
    التحقق من وجود ID في id_history.json

    Args:
        account_id: ID الحساب

    Returns:
        True إذا كان ID موجود
    """
    try:
        if not ID_HISTORY_FILE.exists():
            logger.warning("⚠️ id_history.json not found")
            return False

        with open(ID_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            ids_list = data.get("ids", [])

            # البحث عن ID
            for entry in ids_list:
                if str(entry.get("id")) == str(account_id):
                    return True

            logger.warning(f"⚠️ ID {account_id} not in id_history.json")
            return False

    except Exception as e:
        logger.error(f"❌ Error checking ID history: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# 🔢 تحويل الكوينز
# ═══════════════════════════════════════════════════════════════


def convert_coins_to_thousands(taken_value: str) -> str:
    """
    تحويل الكوينز إلى آلاف (قسمة على 1000 بدون كسور)

    قواعد:
    - 100000 → "100"
    - 1000000 → "1000"
    - 10000 → "10"
    - 1000 → "1"
    - 500 → "" (أقل من 1000 = فاضي)

    Args:
        taken_value: قيمة الكوينز الأصلية

    Returns:
        القيمة بالآلاف (string) أو فاضي
    """
    try:
        value = float(str(taken_value).strip())

        # لو أقل من 1000 → فاضي
        if value < 1000:
            logger.debug(f"💡 Value {value} < 1000 → empty string")
            return ""

        # قسمة على 1000 بدون كسور
        result = int(value / 1000)

        logger.debug(f"💱 Converted: {value} → {result} (÷1000)")
        return str(result)

    except Exception as e:
        logger.error(f"❌ Error converting coins: {taken_value} → {e}")
        return ""


# ═══════════════════════════════════════════════════════════════
# 🔍 البحث في Google Sheet
# ═══════════════════════════════════════════════════════════════


def find_row_by_id(sheets_api, account_id: str) -> Optional[int]:
    """
    البحث عن ID في عمود Z والحصول على رقم الصف

    Args:
        sheets_api: Google Sheets API instance
        account_id: ID الحساب

    Returns:
        رقم الصف (1-based) أو None
    """
    try:
        logger.info(f"🔍 Searching for ID {account_id} in column Z...")

        # قراءة عمود Z كامل
        column_range = f"{sheets_api.sheet_name}!Z:Z"
        result = (
            sheets_api.service.spreadsheets()
            .values()
            .get(spreadsheetId=sheets_api.spreadsheet_id, range=column_range)
            .execute()
        )

        values = result.get("values", [])

        if not values:
            logger.warning("⚠️ Column Z is empty")
            return None

        # البحث عن ID
        for idx, row in enumerate(values, start=1):
            if row and str(row[0]).strip() == str(account_id).strip():
                logger.info(f"✅ Found ID {account_id} at row {idx}")
                return idx

        logger.warning(f"⚠️ ID {account_id} not found in Sheet")
        return None

    except Exception as e:
        logger.error(f"❌ Error searching Sheet: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# ✏️ تحديث الخلية في Google Sheet
# ═══════════════════════════════════════════════════════════════


def update_sheet_cell(
    sheets_api, row_number: int, column_letter: str, value: str
) -> Tuple[bool, str]:
    """
    تحديث خلية واحدة في Google Sheet

    Args:
        sheets_api: Google Sheets API instance
        row_number: رقم الصف (1-based)
        column_letter: حرف العمود (مثل "C" أو "F")
        value: القيمة المراد كتابتها

    Returns:
        (success: bool, message: str)
    """
    try:
        cell_range = f"{sheets_api.sheet_name}!{column_letter}{row_number}"

        logger.info(f"✏️ Updating {cell_range} with value: '{value}'")

        body = {"values": [[value]]}

        sheets_api.service.spreadsheets().values().update(
            spreadsheetId=sheets_api.spreadsheet_id,
            range=cell_range,
            valueInputOption="USER_ENTERED",
            body=body,
        ).execute()

        logger.info(f"✅ Successfully updated {cell_range}")
        return True, f"Updated {cell_range}"

    except Exception as e:
        logger.error(f"❌ Error updating cell {column_letter}{row_number}: {e}")
        return False, str(e)


# ═══════════════════════════════════════════════════════════════
# ⚙️ المعالج الرئيسي (Worker)
# ═══════════════════════════════════════════════════════════════


async def taken_worker(config: Dict, sheets_api):
    """
    🔄 Worker معالجة الكوينز المسحوبة

    التدفق:
    1. قراءة Taken.json كل 1-10 ثواني
    2. لكل عنصر:
       - التحقق من id_history.json
       - البحث في Sheet (عمود Z)
       - تحديث العمود المناسب (C أو F)
       - مسح من Taken.json (نجح أو فشل)

    Args:
        config: إعدادات التطبيق
        sheets_api: Google Sheets API instance
    """
    handler_config = config.get("taken_handler", {})

    # التحقق من التفعيل
    if not handler_config.get("enabled", True):
        logger.info("⚠️ Taken handler is disabled in config")
        return

    # قراءة الإعدادات
    columns = handler_config.get("columns", {})
    amount_taken_col = columns.get("AMOUNT_TAKEN", "C")
    disabled_col = columns.get("DISABLED", "F")

    interval_min = handler_config.get("interval_min", 1)
    interval_max = handler_config.get("interval_max", 10)

    logger.info(
        f"🚀 Taken Worker started (interval: {interval_min}-{interval_max}s, "
        f"AMOUNT_TAKEN→{amount_taken_col}, DISABLED→{disabled_col})"
    )

    while True:
        try:
            # قراءة Queue
            items = load_taken_queue()

            if not items:
                # لا يوجد شيء للمعالجة
                await asyncio.sleep(random.uniform(interval_min, interval_max))
                continue

            logger.info(f"📋 Processing {len(items)} items from Taken queue")

            for item in items:
                try:
                    account_id = item.get("id", "")
                    email = item.get("email", "unknown")
                    status = item.get("status", "").upper()
                    taken_value = item.get("taken", "0")

                    logger.info(
                        f"🔄 Processing: {email} (ID: {account_id}, Status: {status})"
                    )

                    # ✅ الخطوة 1: التحقق من id_history.json
                    if not check_id_in_history(account_id):
                        logger.warning(f"⚠️ ID {account_id} not in history - skipping")
                        clear_taken_entry(account_id)
                        continue

                    # ✅ الخطوة 2: البحث في Sheet
                    row_number = find_row_by_id(sheets_api, account_id)

                    if not row_number:
                        logger.warning(
                            f"⚠️ ID {account_id} not found in Sheet - skipping"
                        )
                        clear_taken_entry(account_id)
                        continue

                    # ✅ الخطوة 3: تحويل الكوينز
                    converted_value = convert_coins_to_thousands(taken_value)

                    # ✅ الخطوة 4: تحديد العمود المناسب
                    if status == "AMOUNT_TAKEN":
                        target_column = amount_taken_col
                    elif status == "DISABLED":
                        target_column = disabled_col
                    else:
                        logger.warning(f"⚠️ Unknown status: {status} - skipping")
                        clear_taken_entry(account_id)
                        continue

                    # ✅ الخطوة 5: التحديث في Sheet
                    success, message = update_sheet_cell(
                        sheets_api, row_number, target_column, converted_value
                    )

                    if success:
                        logger.info(
                            f"✅ Updated {target_column}{row_number} = '{converted_value}' "
                            f"for {email} ({status})"
                        )
                    else:
                        logger.error(
                            f"❌ Failed to update {target_column}{row_number}: {message}"
                        )

                    # ✅ الخطوة 6: مسح من Queue (نجح أو فشل - بدون retry)
                    clear_taken_entry(account_id)

                except Exception as e:
                    logger.exception(f"❌ Error processing item: {e}")
                    # مسح حتى لو حصل خطأ (بدون retry)
                    clear_taken_entry(item.get("id", ""))

            # انتظار عشوائي قبل الدورة التالية
            interval = random.uniform(interval_min, interval_max)
            logger.debug(f"💤 Next check in {interval:.1f}s")
            await asyncio.sleep(interval)

        except Exception as e:
            logger.exception(f"❌ Fatal error in Taken Worker: {e}")
            await asyncio.sleep(30)


# ═══════════════════════════════════════════════════════════════
# 🚀 تشغيل Worker (يُستدعى من worker.py)
# ═══════════════════════════════════════════════════════════════


async def start_taken_worker(config: Dict, sheets_api):
    """
    تشغيل Taken Worker

    Args:
        config: إعدادات التطبيق
        sheets_api: Google Sheets API instance
    """
    try:
        logger.info("💰 Starting Taken Worker...")
        await taken_worker(config, sheets_api)
    except Exception as e:
        logger.exception(f"❌ Fatal error in Taken Worker: {e}")
