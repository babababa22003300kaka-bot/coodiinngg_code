#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 تعديل بيانات السيندر - نظام منفصل
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ زر تفاعلي في جروب "جميع الحالات" فقط
✅ نظام مرن لإدخال البيانات (email, password, backup)
✅ متوافق مع المشروع الحالي
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
import json
import re
from typing import Dict, Optional

import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ═══════════════════════════════════════════════════════════
# ⚙️ تحميل الإعدادات
# ═══════════════════════════════════════════════════════════

with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

# استخراج معلومات الجروب "جميع الحالات"
ALL_STATES_GROUP_ID = None
for group in CONFIG.get("notification_groups", {}).get("groups", []):
    if group.get("name") == "جميع الحالات":
        ALL_STATES_GROUP_ID = group.get("group_id")
        break

# معلومات الموقع
WEBSITE_CONFIG = CONFIG.get("website", {})
BASE_URL = WEBSITE_CONFIG.get("urls", {}).get("base", "https://utautotransfer.com")
COOKIES = WEBSITE_CONFIG.get("cookies", {})

# ═══════════════════════════════════════════════════════════
# 🧠 دوال التحليل الذكي (من الكود التجريبي)
# ═══════════════════════════════════════════════════════════


def convert_arabic_numbers(text: str) -> str:
    """تحويل الأرقام العربية إلى إنجليزية"""
    arabic_to_english = {
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
    }
    processed_text = text
    for ar, en in arabic_to_english.items():
        processed_text = processed_text.replace(ar, en)
    return processed_text


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

    if len(value) >= 1 and len(value) <= 4:
        return "trigger", value

    return "password", value


def clean_backup_codes(raw_codes: str) -> str:
    """
    تنظيف وتنسيق الأكواد الاحتياطية بمرونة.
    يقبل الأكواد مفصولة بـ (فاصلة, سطر جديد, مسافة) ويرجعها مفصولة بفاصلة.
    مثال: 12345678, 98765432
    """
    normalized = convert_arabic_numbers(raw_codes)
    standardized = re.sub(r"[,\n]+", " ", normalized)
    found_codes = re.findall(r"\d{8,}", standardized)
    cleaned_codes = [code[-8:] for code in found_codes]
    unique_codes = list(dict.fromkeys(cleaned_codes))
    return ",".join(unique_codes)


def parse_inputs(field1, field2, field3):
    """تحليل الـ 3 خانات"""
    data = {"email": None, "password": None, "backup": None, "has_trigger": False}

    for field in [field1, field2, field3]:
        if not field:
            continue

        field_type, field_value = detect_field_type(field)

        if field_type == "trigger":
            data["has_trigger"] = True
        elif field_type == "backup":
            cleaned_codes = clean_backup_codes(field_value)
            data["backup"] = cleaned_codes
        elif field_type and field_value:
            data[field_type] = field_value

    return data


# ═══════════════════════════════════════════════════════════
# 🔐 CSRF Token Manager (مبسط)
# ═══════════════════════════════════════════════════════════


class SimpleCSRFManager:
    """مدير CSRF Token بسيط"""

    def __init__(self, base_url: str, cookies: dict):
        self.base_url = base_url
        self.cookies = cookies
        self.token = None
        self.session = None

    async def get_token(self) -> str:
        """الحصول على CSRF Token"""
        if self.token:
            return self.token

        await self._refresh_token()
        return self.token

    async def _refresh_token(self) -> bool:
        """جلب Token جديد من الموقع"""
        print(f"\n🔄 جلب CSRF Token جديد...")

        try:
            if not self.session or self.session.closed:
                self.session = aiohttp.ClientSession(cookies=self.cookies)

            async with self.session.get(f"{self.base_url}/senderPage") as resp:
                if resp.status != 200:
                    print(f"❌ فشل الطلب: {resp.status}")
                    return False

                html = await resp.text()

                match = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
                if not match:
                    print("❌ لم يتم العثور على CSRF Token في الصفحة")
                    return False

                self.token = match.group(1)
                print(f"✅ تم جلب Token جديد")
                return True

        except Exception as e:
            print(f"❌ خطأ في جلب Token: {e}")
            return False

    async def close(self):
        """إغلاق الـ Session"""
        if self.session and not self.session.closed:
            await self.session.close()


# مثيل عام من الـ CSRF Manager
csrf_manager = SimpleCSRFManager(BASE_URL, COOKIES)


# ═══════════════════════════════════════════════════════════
# 🌐 دوال التعامل مع الموقع
# ═══════════════════════════════════════════════════════════


async def get_account_data(session, account_id):
    """جلب بيانات الحساب الحالية"""
    try:
        csrf = await csrf_manager.get_token()
        get_data = f"idAccount={account_id}&csrf_token={csrf}"

        async with session.post(
            f"{BASE_URL}/dataFunctions/getAccountData",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=get_data,
        ) as resp:

            if resp.status != 200:
                return None

            result = await resp.json()
            account_data = result.get("data", [])

            if not account_data or len(account_data) < 3:
                return None

            return {
                "email": account_data[1] if len(account_data) > 1 else "",
                "password": account_data[2] if len(account_data) > 2 else "",
                "backup": account_data[3] if len(account_data) > 3 else "",
                "group": account_data[6] if len(account_data) > 6 else "1111",
            }

    except Exception as e:
        print(f"❌ خطأ في جلب البيانات: {e}")
        return None


async def edit_account(session, account_id, final_data):
    """إرسال طلب التعديل للسيرفر"""
    try:
        csrf = await csrf_manager.get_token()

        edit_payload = {
            "idAccount": account_id,
            "email": final_data["email"],
            "password": final_data["password"],
            "amountToTake": "",
            "amountToKeep": "",
            "backupCodes": final_data["backup"] or "",
            "groupName": final_data.get("group", "1111"),
            "priority": "0",
            "accountLock": 1,
            "forceProxy": "",
            "userPrice": "",
            "csrf_token": csrf,
        }

        async with session.post(
            f"{BASE_URL}/dataFunctions/editAccount",
            headers={"Content-Type": "application/json"},
            json=edit_payload,
        ) as resp:

            text = await resp.text()

            if resp.status == 200:
                return True, text
            else:
                return False, text

    except Exception as e:
        return False, str(e)


async def smart_edit_account(account_id, field1="", field2="", field3=""):
    """التعديل الذكي بنظام 3 خانات"""

    print("=" * 60)
    print(f"[SMART EDIT] 🎯 Starting edit for account: {account_id}")
    print("=" * 60)

    print("\n[SMART EDIT] 1️⃣ Analyzing inputs...")

    parsed = parse_inputs(field1, field2, field3)

    print("\n[SMART EDIT] 🔍 Parse results:")
    if parsed["email"]:
        print(f"[SMART EDIT]   ✅ Email found: {parsed['email']}")
    if parsed["password"]:
        print(f"[SMART EDIT]   ✅ Password found: {'*' * len(parsed['password'])}")
    if parsed["backup"]:
        codes_list = parsed["backup"].split(",")
        codes_count = len(codes_list)
        print(f"[SMART EDIT]   ✅ Backup codes found: {codes_count} code(s)")
        for i, code in enumerate(codes_list[:3], 1):
            print(f"[SMART EDIT]      • {code}")
        if codes_count > 3:
            print(f"[SMART EDIT]      ... and {codes_count - 3} more")
    if parsed["has_trigger"]:
        print(f"[SMART EDIT]   🔄 Trigger detected (will execute)")

    print("\n[SMART EDIT] 2️⃣ Fetching current account data...")

    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/senderPage",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    async with aiohttp.ClientSession(cookies=COOKIES, headers=headers) as session:

        current_data = await get_account_data(session, account_id)

        if not current_data:
            print("[SMART EDIT]   ❌ Failed to fetch current data")
            return False, "فشل جلب البيانات"

        print(f"[SMART EDIT]   ✅ Current email: {current_data['email']}")
        print(f"[SMART EDIT]   ✅ Group: {current_data['group']}")

        print("\n[SMART EDIT] 3️⃣ Preparing final data for edit...")

        final_data = {
            "email": parsed["email"] or current_data["email"],
            "password": parsed["password"] or current_data["password"],
            "backup": parsed["backup"] or current_data["backup"],
            "group": current_data["group"],
        }

        print(f"[SMART EDIT]   📧 Final email: {final_data['email']}")
        if parsed["email"]:
            print(f"[SMART EDIT]      ↪️ Changed from: {current_data['email']}")
        if parsed["password"]:
            print(f"[SMART EDIT]   🔑 Password: Will be changed")
        if parsed["backup"]:
            codes_count = len(parsed["backup"].split(","))
            print(f"[SMART EDIT]   📋 Backup codes: Will be changed ({codes_count} code(s))")

        print("\n[SMART EDIT] 4️⃣ Sending edit request to server...")

        success, response = await edit_account(session, account_id, final_data)

        print("\n" + "=" * 60)
        if success:
            print("[SMART EDIT] ✅ Edit completed successfully!")
            print(f"[SMART EDIT] 📋 Response: {response[:100]}")
        else:
            print("[SMART EDIT] ❌ Edit failed!")
            print(f"[SMART EDIT] 📋 Response: {response[:200]}")
        print("=" * 60)

        return success, response


# ═══════════════════════════════════════════════════════════
# 🔧 دوال مساعدة للبوت
# ═══════════════════════════════════════════════════════════


def is_all_states_group(chat_id: int) -> bool:
    """التحقق إذا كان الجروب هو 'جميع الحالات'"""
    return chat_id == ALL_STATES_GROUP_ID


def create_edit_sender_button(account_id: str) -> InlineKeyboardMarkup:
    """
    إنشاء زر 'تعديل سيندر' مرتبط بالحساب
    
    Callback data format: edit_sender:{account_id}
    """
    keyboard = [
        [
            InlineKeyboardButton(
                "🔧 تعديل بيانات السيندر", callback_data=f"edit_sender:{account_id}"
            )
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# ═══════════════════════════════════════════════════════════
# 🤖 معالجات البوت
# ═══════════════════════════════════════════════════════════

# سنحفظ حالة المستخدمين هنا (account_id اللي بيتعدل)
user_editing_state: Dict[int, str] = {}


async def handle_edit_sender_button(update, context):
    """
    معالج زر 'تعديل سيندر'
    يظهر زر التنفيذ و إرشادات الإدخال
    """
    query = update.callback_query
    await query.answer()

    # استخراج account_id من callback_data
    # Format: edit_sender:580127
    account_id = query.data.split(":")[1] if ":" in query.data else None

    if not account_id:
        await query.message.reply_text("❌ خطأ: لم يتم العثور على معرف الحساب")
        return

    # حفظ الحساب في حالة المستخدم
    user_id = query.from_user.id
    user_editing_state[user_id] = account_id
    
    print(f"\n[EDIT MODE] 🎯 User {user_id} started editing account {account_id}")
    print(f"[EDIT MODE] 📊 Current editing users: {list(user_editing_state.keys())}")

    # إنشاء زر التنفيذ
    keyboard = [
        [
            InlineKeyboardButton(
                "🔄 تنفيذ التعديل", callback_data=f"execute_edit:{account_id}"
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(
        f"✅ تم اختيار الحساب: `{account_id}`\n\n"
        f"📝 الآن:\n"
        f"• اكتب البيانات الجديدة (كل معلومة في سطر)\n"
        f"• أو اضغط على زر التنفيذ المباشر\n\n"
        f"╔═══════════════════════════════╗\n"
        f"║  📧 الإيميل (سطر 1)          ║\n"
        f"║  🔑 الباسورد (سطر 2)         ║\n"
        f"║  🔢 الأكواد (سطر 3، 4، ...) ║\n"
        f"╚═══════════════════════════════╝",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


async def handle_execute_edit_button(update, context):
    """
    معالج زر 'تنفيذ التعديل'
    ينفذ التعديل بدون إدخال بيانات جديدة
    """
    query = update.callback_query
    await query.answer()

    # استخراج account_id
    account_id = query.data.split(":")[1] if ":" in query.data else None

    if not account_id:
        await query.message.reply_text("❌ خطأ: لم يتم العثور على معرف الحساب")
        return

    print(f"\n🔄 تنفيذ مباشر للحساب: {account_id}")

    await query.message.reply_text("⏳ جاري التنفيذ بالبيانات الحالية...")

    # تنفيذ التعديل
    success, response = await smart_edit_account(account_id)

    if success:
        await query.message.reply_text(
            f"✅ تم التنفيذ بنجاح!\n\n"
            f"📊 ملخص العملية:\n"
            f"├─ 🎯 الحساب: `{account_id}`\n"
            f"├─ 📌 نوع العملية: تنفيذ مباشر\n"
            f"└─ 🔄 Trigger: تم التشغيل ✓",
            parse_mode="Markdown",
        )
    else:
        await query.message.reply_text(
            f"❌ فشل التنفيذ\n\n"
            f"📋 الرد: {response[:200]}\n\n"
            f"💡 تحقق من:\n"
            f"• الكوكيز في config.json\n"
            f"• CSRF Token\n"
            f"• اتصال الإنترنت"
        )

    # مسح الحالة
    user_id = query.from_user.id
    if user_id in user_editing_state:
        del user_editing_state[user_id]


async def process_edit_input(update, context):
    """
    [EDIT MODE] معالج الإدخال النصي للبيانات - يُستدعى فقط من main.py
    """
    user_id = update.effective_user.id

    # التحقق إذا كان المستخدم في وضع التعديل
    if user_id not in user_editing_state:
        print(f"[EDIT MODE] ⚠️ User {user_id} not in editing state. Ignoring.")
        return

    account_id = user_editing_state[user_id]
    text = update.message.text
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    print(f"\n[EDIT MODE] 📝 Received data for account: {account_id}")
    print(f"[EDIT MODE] 📊 Number of lines: {len(lines)}")

    field1 = lines[0] if len(lines) > 0 else ""
    field2 = lines[1] if len(lines) > 1 else ""
    field3 = "\n".join(lines[2:]) if len(lines) > 2 else ""

    print(f"[EDIT MODE] 🔄 Starting smart edit process...")
    await update.message.reply_text("⏳ جاري تحليل البيانات...")

    # تنفيذ التعديل
    success, response = await smart_edit_account(account_id, field1, field2, field3)
    
    print(f"[EDIT MODE] 📋 Edit result: {'✅ SUCCESS' if success else '❌ FAILED'}")

    if success:
        await update.message.reply_text(
            f"✅ تم التعديل بنجاح!\n\n"
            f"📊 ملخص العملية:\n"
            f"├─ 🎯 الحساب: `{account_id}`\n"
            f"└─ ⏱ تم التنفيذ",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            f"❌ فشل التعديل\n\n" f"📋 الرد: {response[:200]}"
        )

    # مسح الحالة
    del user_editing_state[user_id]
    print(f"[EDIT MODE] 🧹 Cleared editing state for user {user_id}")


# ═══════════════════════════════════════════════════════════
# 🔌 دوال التكامل مع المشروع الرئيسي
# ═══════════════════════════════════════════════════════════


def register_handlers(application):
    """
    تسجيل معالجات البوت في التطبيق الرئيسي
    
    يُستدعى من main.py
    ⚠️ ملاحظة: MessageHandler تم نقله إلى main.py (State-Based Routing)
    """
    from telegram.ext import CallbackQueryHandler

    # معالج زر "تعديل سيندر"
    application.add_handler(
        CallbackQueryHandler(handle_edit_sender_button, pattern="^edit_sender:")
    )

    # معالج زر "تنفيذ التعديل"
    application.add_handler(
        CallbackQueryHandler(handle_execute_edit_button, pattern="^execute_edit:")
    )

    print("✅ [EDIT MODE] Registered button handlers (edit_sender, execute_edit)")
    print("✅ [EDIT MODE] Text input routing handled by main.py")


async def cleanup():
    """تنظيف الموارد عند إغلاق البوت"""
    await csrf_manager.close()
