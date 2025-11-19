#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 Engine: Get & Edit Account
ملف منفصل لمعالجة التعديل الذكي - مستقل تماماً عن باقي المشروع
"""

import re
import logging
import asyncio

logger = logging.getLogger(__name__)

# 🔒 تحديد عدد العمليات المتزامنة (2 فقط عشان الموارد)
edit_semaphore = asyncio.Semaphore(2)

# ═══════════════════════════════════════════════════════════════
# 🧠 أدوات التحليل الذكي (نسخ/لصق من الكود التجريبي)
# ═══════════════════════════════════════════════════════════════

def convert_arabic_numbers(text: str) -> str:
    """تحويل الأرقام العربية إلى إنجليزية"""
    if not text: return ""
    arabic_to_english = {"٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9"}
    processed_text = text
    for ar, en in arabic_to_english.items():
        processed_text = processed_text.replace(ar, en)
    return processed_text

def clean_backup_codes(raw_codes: str) -> str:
    """تنظيف وتنسيق الأكواد الاحتياطية"""
    if not raw_codes: return ""
    normalized = convert_arabic_numbers(raw_codes)
    standardized = re.sub(r'[,\n]+', ' ', normalized)
    found_codes = re.findall(r'\d{8,}', standardized)
    cleaned_codes = [code[-8:] for code in found_codes]
    unique_codes = list(dict.fromkeys(cleaned_codes))
    return ",".join(unique_codes)

def detect_field_type(value):
    """كشف نوع الخانة تلقائياً"""
    if not value or not value.strip():
        return None, None
    value = value.strip()
    if "@" in value and "." in value:
        return "email", value
    value_normalized = convert_arabic_numbers(value)
    if "," in value_normalized:
        return "backup", value_normalized
    eight_digit_codes = re.findall(r"\d{8,}", value_normalized)
    if eight_digit_codes:
        return "backup", value_normalized
    digits_only = re.sub(r"\D", "", value_normalized)
    if len(digits_only) >= 16:
        return "backup", value_normalized
    if 1 <= len(value) <= 4:
        return "trigger", value
    return "password", value

def parse_smart_inputs(text_block: str):
    """تحليل النص المدخل بذكاء"""
    lines = [line.strip() for line in text_block.split("\n") if line.strip()]
    field1 = lines[0] if len(lines) > 0 else ""
    field2 = lines[1] if len(lines) > 1 else ""
    field3 = "\n".join(lines[2:]) if len(lines) > 2 else ""

    data = {"email": None, "password": None, "backup": None, "has_trigger": False}
    for field in [field1, field2, field3]:
        if not field: continue
        field_type, field_value = detect_field_type(field)
        if field_type == "trigger":
            data["has_trigger"] = True
        elif field_type == "backup":
            cleaned_codes = clean_backup_codes(field_value)
            data["backup"] = cleaned_codes
        elif field_type and field_value:
            data[field_type] = field_value
    return data

# ═══════════════════════════════════════════════════════════════
# 🚀 وظائف التنفيذ (Get & Edit)
# ═══════════════════════════════════════════════════════════════

async def execute_smart_edit(api_manager, account_id: str, input_text: str):
    """
    الدالة الرئيسية: تجيب البيانات، تدمج، وتبعت التعديل
    تعمل داخل Semaphore عشان منضغطش ع السيرفر
    """
    # استخدام الـ Semaphore لتقييد العدد (خيط منفصل)
    async with edit_semaphore:
        logger.info(f"🔧 Smart Edit started for Account {account_id}")

        # 1️⃣ تحليل المدخلات
        parsed = parse_smart_inputs(input_text)

        # 2️⃣ جلب البيانات الحالية (Get Data)
        current_data = None
        for attempt in range(2):
            try:
                csrf = await api_manager.get_csrf_token()
                await api_manager._ensure_session()
                
                # استخدام Form Data كما في التجريبي
                async with api_manager.session.post(
                    f"{api_manager.base_url}/dataFunctions/getAccountData",
                    data={"idAccount": account_id, "csrf_token": csrf}
                ) as resp:
                    if resp.status in [403, 419]:
                        api_manager.csrf_token = None
                        continue
                    
                    if resp.status == 200:
                        result = await resp.json()
                        raw_list = result.get("data", [])
                        # التأكد من وجود بيانات كافية
                        if raw_list and len(raw_list) >= 4:
                            current_data = {
                                "email": raw_list[1],
                                "password": raw_list[2],
                                "backup": raw_list[3],
                                "group": raw_list[6] if len(raw_list) > 6 else "1111"
                            }
                            break
            except Exception as e:
                logger.error(f"❌ Edit error (Get Data): {e}")

        if not current_data:
            return False, "❌ فشل جلب بيانات الحساب الحالية. تأكد أن الحساب موجود."

        # 3️⃣ دمج البيانات (الجديد يغطي القديم)
        final_data = {
            "email": parsed["email"] or current_data["email"],
            "password": parsed["password"] or current_data["password"],
            "backup": parsed["backup"] or current_data["backup"],
            "group": current_data["group"],
        }

        # 4️⃣ إرسال التعديل (Edit Account)
        for attempt in range(2):
            try:
                csrf = await api_manager.get_csrf_token()
                
                # البايلود زي الكود التجريبي بالظبط
                payload = {
                    "idAccount": account_id,
                    "email": final_data["email"],
                    "password": final_data["password"],
                    "amountToTake": "", 
                    "amountToKeep": "",
                    "backupCodes": final_data["backup"],
                    "groupName": final_data["group"],
                    "priority": "0", "accountLock": 1,
                    "forceProxy": "", "userPrice": "",
                    "csrf_token": csrf
                }
                
                async with api_manager.session.post(
                    f"{api_manager.base_url}/dataFunctions/editAccount",
                    json=payload
                ) as resp:
                    text = await resp.text()
                    if resp.status in [403, 419]:
                        api_manager.csrf_token = None
                        continue
                    
                    if resp.status == 200:
                        # تفريغ الكاش عشان التعديل يسمع
                        from api_manager import smart_cache
                        smart_cache.cache = None
                        
                        return True, (
                            f"✅ *تم تعديل السيندر بنجاح!*\n\n"
                            f"📧 `{final_data['email']}`\n"
                            f"🔑 `{final_data['password']}`\n"
                            f"🔢 الأكواد: تم التحديث"
                        )
                    else:
                        return False, f"❌ رفض الموقع التعديل: {text[:100]}"

            except Exception as e:
                logger.error(f"❌ Edit error (Submit): {e}")
                return False, str(e)
                
        return False, "❌ فشل غير معروف"
