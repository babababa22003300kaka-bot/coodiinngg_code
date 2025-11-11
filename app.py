import json
import os
import re
import logging
import asyncio
import signal
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import traceback
from functools import wraps
from flask import Flask, request, jsonify
import requests

# إعداد الـ logging المتقدم

logging.basicConfig(

    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',

    level=logging.INFO,

    handlers=[

        logging.FileHandler('bot.log', encoding='utf-8'),

        logging.StreamHandler()

    ]

)

logger = logging.getLogger(__name__)

# إعدادات البوت

BOT_TOKEN = "7980723104:AAHU5aDxkzLcIobRGQfrz4CWpCxnV07XAXA"

ADMIN_IDS = [1124247595, 1108589010]

DB_FILE = "accounts_db.json"

BACKUP_DIR = "backups"

# الإعدادات الافتراضية

DEFAULT_PENDING_HOURS = 36

DEFAULT_COOLDOWN_HOURS = 36

DEFAULT_FIXED_PASSWORD = "PsPcXbox999"

# متغير للتحكم في إعادة التشغيل

should_restart = False

def error_handler(func):

    """ديكوريتر لمعالجة الأخطاء"""

    @wraps(func)

    async def wrapper(*args, **kwargs):

        try:

            return await func(*args, **kwargs)

        except Exception as e:

            logger.error(f"خطأ في {func.__name__}: {e}")

            logger.error(traceback.format_exc())



            try:

                if args and hasattr(args[0], 'message'):

                    await args[0].message.reply_text(

                        f"❌ **حدث خطأ:**\n`{str(e)}`\n\nتم تسجيل التفاصيل في السجل.",

                        parse_mode='Markdown'

                    )

            except:

                pass



            return None

    return wrapper

class AccountManager:

    def __init__(self):

        self.create_backup_dir()

        self.load_database()

        self.setup_auto_backup()



    def create_backup_dir(self):

        """إنشاء مجلد النسخ الاحتياطية"""

        if not os.path.exists(BACKUP_DIR):

            os.makedirs(BACKUP_DIR)



    def setup_auto_backup(self):

        """إعداد النسخ الاحتياطي التلقائي"""

        try:

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            backup_file = os.path.join(BACKUP_DIR, f"auto_backup_{timestamp}.json")



            if os.path.exists(DB_FILE):

                import shutil

                shutil.copy2(DB_FILE, backup_file)

                logger.info(f"تم إنشاء نسخة احتياطية: {backup_file}")



                # حذف النسخ القديمة (الاحتفاظ بآخر 10)

                backup_files = [f for f in os.listdir(BACKUP_DIR) if f.startswith('auto_backup_')]

                backup_files.sort()



                if len(backup_files) > 10:

                    for old_backup in backup_files[:-10]:

                        try:

                            os.remove(os.path.join(BACKUP_DIR, old_backup))

                        except:

                            pass

        except Exception as e:

            logger.error(f"خطأ في النسخ الاحتياطي: {e}")



    def load_database(self):

        """تحميل قاعدة البيانات مع معالجة الأخطاء"""

        try:

            if os.path.exists(DB_FILE):

                with open(DB_FILE, 'r', encoding='utf-8') as f:

                    content = f.read().strip()

                    if content:

                        self.db = json.loads(content)

                        self._validate_database()

                    else:

                        self._create_default_db()

            else:

                self._create_default_db()



            logger.info(f"تم تحميل قاعدة البيانات: {len(self.db['accounts'])} حساب")



        except json.JSONDecodeError as e:

            logger.error(f"خطأ في قراءة JSON: {e}")

            self._restore_from_backup()

        except Exception as e:

            logger.error(f"خطأ في تحميل قاعدة البيانات: {e}")

            self._create_default_db()



    def _validate_database(self):

        """التحقق من صحة بنية قاعدة البيانات"""

        if not isinstance(self.db, dict):

            raise ValueError("قاعدة البيانات ليست dict")



        if "accounts" not in self.db:

            self.db["accounts"] = {}



        if "settings" not in self.db:

            self.db["settings"] = {

                "pending_hours": DEFAULT_PENDING_HOURS,

                "cooldown_hours": DEFAULT_COOLDOWN_HOURS,

                "fixed_password": DEFAULT_FIXED_PASSWORD

            }



        if "fixed_password" not in self.db["settings"]:

            self.db["settings"]["fixed_password"] = DEFAULT_FIXED_PASSWORD



        if "logs" not in self.db:

            self.db["logs"] = []



        if "stats" not in self.db:

            self.db["stats"] = {

                "total_requests": 0,

                "successful_requests": 0,

                "last_restart": datetime.now().isoformat()

            }



        # التحقق من بيانات كل حساب

        for email, data in list(self.db["accounts"].items()):

            if not isinstance(data, dict):

                del self.db["accounts"][email]

                continue



            required_fields = {

                "password": "",

                "added_at": datetime.now().isoformat(),

                "available_at": datetime.now().isoformat(),

                "status": "available",

                "last_used": None,

                "use_count": 0,

                "priority": 1

            }



            for field, default_value in required_fields.items():

                if field not in data:

                    data[field] = default_value



    def _create_default_db(self):

        """إنشاء قاعدة بيانات افتراضية"""

        self.db = {

            "accounts": {},

            "settings": {

                "pending_hours": DEFAULT_PENDING_HOURS,

                "cooldown_hours": DEFAULT_COOLDOWN_HOURS,

                "fixed_password": DEFAULT_FIXED_PASSWORD

            },

            "logs": [],

            "stats": {

                "total_requests": 0,

                "successful_requests": 0,

                "last_restart": datetime.now().isoformat()

            }

        }

        self.save_database()

        logger.info("تم إنشاء قاعدة بيانات جديدة")



    def _restore_from_backup(self):

        """استعادة من النسخة الاحتياطية"""

        try:

            backup_files = [f for f in os.listdir(BACKUP_DIR) if f.startswith('auto_backup_')]

            backup_files.sort(reverse=True)



            if backup_files:

                latest_backup = os.path.join(BACKUP_DIR, backup_files[0])

                with open(latest_backup, 'r', encoding='utf-8') as f:

                    self.db = json.load(f)

                self._validate_database()

                self.save_database()

                logger.info(f"تم الاستعادة من النسخة الاحتياطية: {backup_files[0]}")

            else:

                self._create_default_db()

        except Exception as e:

            logger.error(f"فشل في الاستعادة من النسخة الاحتياطية: {e}")

            self._create_default_db()



    def save_database(self):

        """حفظ قاعدة البيانات مع معالجة الأخطاء"""

        max_retries = 3

        for attempt in range(max_retries):

            try:

                temp_file = f"{DB_FILE}.tmp"

                with open(temp_file, 'w', encoding='utf-8') as f:

                    json.dump(self.db, f, ensure_ascii=False, indent=2)



                if os.path.exists(DB_FILE):

                    os.replace(temp_file, DB_FILE)

                else:

                    os.rename(temp_file, DB_FILE)



                return True



            except Exception as e:

                logger.error(f"محاولة {attempt + 1}: خطأ في حفظ قاعدة البيانات: {e}")

                if attempt == max_retries - 1:

                    # في حالة فشل كل المحاولات، نحفظ نسخة احتياطية طارئة

                    emergency_file = f"emergency_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

                    try:

                        with open(emergency_file, 'w', encoding='utf-8') as f:

                            json.dump(self.db, f, ensure_ascii=False, indent=2)

                        logger.info(f"تم حفظ نسخة احتياطية طارئة: {emergency_file}")

                    except:

                        pass

                    return False



        return False



    def add_log(self, action: str, details: str = ""):

        """إضافة سجل للأنشطة"""

        try:

            log_entry = {

                "timestamp": datetime.now().isoformat(),

                "action": action,

                "details": details

            }

            self.db["logs"].append(log_entry)



            if len(self.db["logs"]) > 200:

                self.db["logs"] = self.db["logs"][-200:]



            # حفظ فوري للسجلات المهمة

            if action in ["إضافة حساب", "حذف حساب", "استخدام حساب"]:

                self.save_database()



        except Exception as e:

            logger.error(f"خطأ في إضافة السجل: {e}")



    def is_valid_email(self, email: str) -> bool:

        """التحقق من صحة الإيميل"""

        if not email or not isinstance(email, str):

            return False



        email = email.strip().lower()



        if len(email) < 5 or len(email) > 100:

            return False



        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

        return re.match(pattern, email) is not None



    def extract_credentials(self, text: str) -> List[Tuple[str, str]]:

        """استخراج الإيميل والباسورد مع الحفاظ على الرموز الخاصة"""

        credentials = []



        try:

            # لا نحذف الرموز الخاصة - نحافظ على النص كما هو

            lines = text.strip().split('\n')



            # أنماط البحث عن الإيميلات

            email_patterns = [

                r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',

                r'[a-zA-Z0-9._%+-]+\[at\][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',

                r'[a-zA-Z0-9._%+-]+\(at\)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',

            ]



            # البحث في كل سطر

            for line_num, line in enumerate(lines):

                if not line.strip():

                    continue



                # البحث عن إيميلات في السطر الحالي

                found_emails = []

                for pattern in email_patterns:

                    emails = re.findall(pattern, line, re.IGNORECASE)

                    for email in emails:

                        clean_email = email.replace('[at]', '@').replace('(at)', '@').lower().strip()

                        if clean_email and clean_email not in found_emails:

                            found_emails.append(clean_email)



                # لكل إيميل، البحث عن الباسورد

                for email in found_emails:

                    password = self._find_password_comprehensive(email, line, lines, line_num)

                    if password:

                        credentials.append((email, password))



            # إذا لم نجد شيء، نجرب طريقة أخرى

            if not credentials:

                credentials = self._alternative_extraction(text)



            return credentials



        except Exception as e:

            logger.error(f"خطأ في استخراج البيانات: {e}")

            return []



    def _find_password_comprehensive(self, email: str, current_line: str, all_lines: List[str], line_index: int) -> Optional[str]:

        """البحث الشامل عن الباسورد"""

        try:

            # 1. البحث في نفس السطر مع فواصل مختلفة

            same_line_patterns = [

                rf'{re.escape(email)}\s+([^\s\n]+)',

                rf'{re.escape(email)}:([^\s\n]+)',

                rf'{re.escape(email)}\|([^\s\n]+)',

                rf'{re.escape(email)}\t+([^\s\n]+)',

                rf'{re.escape(email)}-([^\s\n]+)',

                rf'{re.escape(email)}_([^\s\n]+)',

                rf'{re.escape(email)},([^\s\n]+)',

                rf'{re.escape(email)};([^\s\n]+)',

                rf'{re.escape(email)}=([^\s\n]+)',

                rf'{re.escape(email)}\s*\(\s*([^)]+)\s*\)',

                rf'{re.escape(email)}\s*\[\s*([^\]]+)\s*\]',

            ]



            for pattern in same_line_patterns:

                match = re.search(pattern, current_line, re.IGNORECASE)

                if match:

                    password = match.group(1).strip()

                    if self._is_valid_password(password):

                        return password



            # 2. البحث بالكلمات في نفس السطر

            words = current_line.split()

            for i, word in enumerate(words):

                if email.lower() in word.lower() and i + 1 < len(words):

                    potential_password = words[i + 1]

                    if self._is_valid_password(potential_password):

                        return potential_password



            # 3. البحث في السطر التالي

            if line_index + 1 < len(all_lines):

                next_line = all_lines[line_index + 1].strip()

                next_line = re.sub(r'^[^\w]+', '', next_line)



                if next_line:

                    if self._is_valid_password(next_line):

                        return next_line



                    first_word = next_line.split()[0] if next_line.split() else next_line

                    if self._is_valid_password(first_word):

                        return first_word



            # 4. البحث في السطرين التاليين

            for offset in [2, 3]:

                if line_index + offset < len(all_lines):

                    target_line = all_lines[line_index + offset].strip()

                    if target_line and self._is_valid_password(target_line):

                        return target_line



            return None



        except Exception as e:

            logger.error(f"خطأ في البحث عن الباسورد: {e}")

            return None



    def _alternative_extraction(self, text: str) -> List[Tuple[str, str]]:

        """طريقة بديلة للاستخراج"""

        try:

            credentials = []



            blocks = re.split(r'\n\s*\n', text)



            for block in blocks:

                lines = [line.strip() for line in block.split('\n') if line.strip()]



                if len(lines) >= 2:

                    for i in range(len(lines) - 1):

                        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', lines[i])

                        if email_match:

                            email = email_match.group().lower()

                            for j in range(i + 1, min(i + 4, len(lines))):

                                potential_password = lines[j].strip()

                                if self._is_valid_password(potential_password):

                                    credentials.append((email, potential_password))

                                    break



            return credentials



        except Exception as e:

            logger.error(f"خطأ في الاستخراج البديل: {e}")

            return []



    def _is_valid_password(self, password: str) -> bool:

        """التحقق من صحة الباسورد مع السماح بكافة الرموز"""

        if not password:

            return False



        password = password.strip()



        # تحديد الطول المسموح

        if len(password) < 3 or len(password) > 50:

            return False



        # استبعاد الكلمات الشائعة

        invalid_words = {

            'email', 'password', 'pass', 'user', 'username', 'login',

            'account', 'gmail', 'yahoo', 'hotmail', 'outlook', 'mail',

            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',

            'with', 'by', 'from', 'of', 'is', 'are', 'was', 'were',

            'this', 'that', 'these', 'those', 'here', 'there'

        }



        if password.lower() in invalid_words:

            return False



        # استبعاد الإيميلات

        if '@' in password and '.' in password:

            return False



        # استبعاد الأرقام البسيطة جداً

        if password.isdigit() and len(password) < 4:

            return False



        # استبعاد الأحرف المتكررة

        if len(set(password)) == 1:

            return False



        # يجب أن يحتوي على حروف أو أرقام على الأقل

        if not re.search(r'[a-zA-Z0-9]', password):

            return False



        return True



    def is_likely_password(self, text: str) -> bool:

        """تحديد إذا كان النص باسورد"""

        if not text or not isinstance(text, str):

            return False



        text = text.strip()



        if len(text) < 3 or len(text) > 50:

            return False



        # استبعاد الإيميلات

        if '@' in text and self.is_valid_email(text):

            return False



        # استبعاد الكلمات الشائعة

        excluded = {

            'email', 'password', 'pass', 'user', 'gmail', 'yahoo', 'hotmail',

            'start', 'help', 'info', 'add', 'delete', 'اضافة', 'حذف', 'ايميل'

        }



        if text.lower() in excluded:

            return False



        if text.count(' ') > 2:

            return False



        if not re.search(r'[a-zA-Z0-9]', text):

            return False



        return True



    def detect_input_type(self, text: str) -> str:

        """تحديد نوع المدخل"""

        if not text:

            return "unknown"



        text = text.strip()



        if self.is_valid_email(text):

            return "email"



        if self.is_likely_password(text):

            return "password"



        if '@' in text and (' ' in text or ':' in text or '|' in text):

            return "mixed"



        return "unknown"



    def get_fixed_password(self) -> str:

        """الحصول على الباسورد الثابت"""

        try:

            if "settings" not in self.db:

                self.db["settings"] = {

                    "pending_hours": DEFAULT_PENDING_HOURS,

                    "cooldown_hours": DEFAULT_COOLDOWN_HOURS,

                    "fixed_password": DEFAULT_FIXED_PASSWORD

                }

                self.save_database()



            fixed_password = self.db["settings"].get("fixed_password", DEFAULT_FIXED_PASSWORD)



            if not fixed_password:

                fixed_password = DEFAULT_FIXED_PASSWORD

                self.db["settings"]["fixed_password"] = fixed_password

                self.save_database()



            return fixed_password



        except Exception as e:

            logger.error(f"خطأ في الحصول على الباسورد الثابت: {e}")

            return DEFAULT_FIXED_PASSWORD



    def update_fixed_password(self, new_password: str) -> Tuple[bool, str]:

        """تحديث الباسورد الثابت"""

        try:

            new_password = new_password.strip()



            if not new_password or len(new_password) < 3:

                return False, "الباسورد يجب أن يكون على الأقل 3 أحرف"



            old_password = self.get_fixed_password()

            self.db["settings"]["fixed_password"] = new_password

            self.add_log("تعديل باسورد ثابت", f"من {old_password} إلى {new_password}")

            self.save_database()

            return True, f"تم تحديث الباسورد الثابت من {old_password} إلى {new_password}"

        except Exception as e:

            logger.error(f"خطأ في تحديث الباسورد الثابت: {e}")

            return False, f"خطأ: {str(e)}"



    def add_account(self, email: str, password: str) -> Tuple[bool, str]:

        """إضافة حساب جديد مع معالجة محسنة"""

        try:

            email = email.lower().strip()

            password = password.strip()



            if not email or not password:

                return False, "الإيميل أو الباسورد فارغ"



            if not self.is_valid_email(email):

                return False, "صيغة الإيميل غير صحيحة"



            now = datetime.now()



            # التحقق من وجود الحساب

            if email in self.db["accounts"]:

                old_password = self.db["accounts"][email]["password"]

                if old_password != password:

                    self.db["accounts"][email]["password"] = password

                    self.add_log("تعديل باسورد", f"تم تعديل باسورد {email}")

                    self.save_database()

                    return True, f"تم تعديل الباسورد من {old_password} إلى {password}"

                else:

                    return False, "الحساب موجود بالفعل بنفس الباسورد"



            # إضافة الحساب الجديد

            self.db["accounts"][email] = {

                "password": password,

                "added_at": now.isoformat(),

                "available_at": (now + timedelta(hours=self.db["settings"]["pending_hours"])).isoformat(),

                "status": "pending",

                "last_used": None,

                "use_count": 0,

                "priority": 1

            }



            self.add_log("إضافة حساب", f"تم إضافة {email}")

            self.save_database()

            return True, "تم الإضافة بنجاح"



        except Exception as e:

            logger.error(f"خطأ في إضافة الحساب: {e}")

            return False, f"خطأ: {str(e)}"



    def add_account_with_fixed_password(self, email: str) -> Tuple[bool, str]:

        """إضافة حساب بالباسورد الثابت"""

        try:

            email = email.lower().strip()



            if not self.is_valid_email(email):

                return False, "صيغة الإيميل غير صحيحة"



            fixed_password = self.get_fixed_password()

            success, message = self.add_account(email, fixed_password)



            if success:

                if "تعديل" in message:

                    return True, f"تم تعديل الحساب ليستخدم الباسورد الثابت"

                else:

                    return True, f"تم إضافة الحساب بالباسورد الثابت بنجاح"

            else:

                return success, message



        except Exception as e:

            logger.error(f"خطأ في إضافة حساب بالباسورد الثابت: {e}")

            return False, f"خطأ: {str(e)}"



    def update_password(self, email: str, new_password: str) -> Tuple[bool, str]:

        """تعديل باسورد حساب موجود"""

        try:

            email = email.lower().strip()

            new_password = new_password.strip()



            if email not in self.db["accounts"]:

                return False, "الحساب غير موجود"



            old_password = self.db["accounts"][email]["password"]

            self.db["accounts"][email]["password"] = new_password



            self.add_log("تعديل باسورد", f"تم تعديل باسورد {email}")

            self.save_database()

            return True, f"تم تعديل الباسورد من {old_password} إلى {new_password}"



        except Exception as e:

            logger.error(f"خطأ في تعديل الباسورد: {e}")

            return False, f"خطأ: {str(e)}"



    def get_available_account(self) -> Optional[Tuple[str, str]]:

        """الحصول على حساب متاح مع تحديث الإحصائيات"""

        try:

            self.db["stats"]["total_requests"] += 1



            now = datetime.now()

            available_accounts = []



            for email, data in self.db["accounts"].items():

                available_at = datetime.fromisoformat(data["available_at"])



                if available_at <= now and data["status"] in ["pending", "available"]:

                    available_accounts.append((email, data, available_at))



            if not available_accounts:

                return None



            # ترتيب حسب الأولوية ثم الأقدم ثم الأقل استخداماً

            available_accounts.sort(key=lambda x: (

                x[1].get("priority", 1),

                x[2],

                x[1].get("use_count", 0)

            ))



            # تحديث حالة الحساب

            email, data, _ = available_accounts[0]

            data["status"] = "used"

            data["last_used"] = now.isoformat()

            data["use_count"] += 1

            data["available_at"] = (now + timedelta(hours=self.db["settings"]["cooldown_hours"])).isoformat()



            self.db["stats"]["successful_requests"] += 1

            self.add_log("استخدام حساب", f"تم استخدام {email}")

            self.save_database()



            return email, data["password"]



        except Exception as e:

            logger.error(f"خطأ في الحصول على حساب: {e}")

            return None



    def get_statistics(self) -> dict:

        """الحصول على إحصائيات شاملة"""

        try:

            now = datetime.now()

            stats = {

                "total": len(self.db["accounts"]),

                "available": 0,

                "pending": 0,

                "cooldown": 0,

                "next_available": None,

                "next_available_email": None,

                "total_requests": self.db["stats"].get("total_requests", 0),

                "successful_requests": self.db["stats"].get("successful_requests", 0),

                "success_rate": 0

            }



            next_available_time = None

            next_email = None



            for email, data in self.db["accounts"].items():

                available_at = datetime.fromisoformat(data["available_at"])



                if data["status"] == "pending" and available_at > now:

                    stats["pending"] += 1

                elif data["status"] == "used" and available_at > now:

                    stats["cooldown"] += 1

                elif available_at <= now:

                    stats["available"] += 1

                    if data["status"] != "available":

                        data["status"] = "available"



                # إيجاد أقرب حساب سيصبح متاح

                if available_at > now:

                    if next_available_time is None or available_at < next_available_time:

                        next_available_time = available_at

                        next_email = email



            if next_available_time:

                time_diff = next_available_time - now

                hours = int(time_diff.total_seconds() // 3600)

                minutes = int((time_diff.total_seconds() % 3600) // 60)

                stats["next_available"] = f"{hours} ساعة و {minutes} دقيقة"

                stats["next_available_email"] = next_email



            # حساب معدل النجاح

            if stats["total_requests"] > 0:

                stats["success_rate"] = (stats["successful_requests"] / stats["total_requests"]) * 100



            self.save_database()

            return stats



        except Exception as e:

            logger.error(f"خطأ في الإحصائيات: {e}")

            return {"total": 0, "available": 0, "pending": 0, "cooldown": 0}



    def delete_account(self, email: str) -> bool:

        """حذف حساب"""

        try:

            email = email.lower().strip()

            if email in self.db["accounts"]:

                del self.db["accounts"][email]

                self.add_log("حذف حساب", f"تم حذف {email}")

                self.save_database()

                return True

            return False

        except Exception as e:

            logger.error(f"خطأ في حذف الحساب: {e}")

            return False



    def get_account_info(self, email: str) -> Optional[dict]:

        """الحصول على معلومات حساب معين"""

        try:

            email = email.lower().strip()

            if email not in self.db["accounts"]:

                return None



            account_data = self.db["accounts"][email]

            now = datetime.now()

            available_at = datetime.fromisoformat(account_data["available_at"])

            time_diff = available_at - now



            if time_diff.total_seconds() > 0:

                hours = int(time_diff.total_seconds() // 3600)

                minutes = int((time_diff.total_seconds() % 3600) // 60)

                time_str = f"{hours}س {minutes}د"

                current_status = account_data["status"]

            else:

                time_str = "متاح الآن"

                current_status = "available"

                account_data["status"] = "available"

                self.save_database()



            return {

                "email": email,

                "password": account_data["password"],

                "status": current_status,

                "time_left": time_str,

                "use_count": account_data["use_count"],

                "added_at": account_data["added_at"],

                "priority": account_data.get("priority", 1)

            }



        except Exception as e:

            logger.error(f"خطأ في الحصول على معلومات الحساب: {e}")

            return None

# إنشاء مدير الحسابات العالمي

account_manager = AccountManager()

# دوال الكيبورد

def get_main_keyboard():

    """الكيبورد الرئيسي"""

    keyboard = [

        ["📥 طلب حساب", "📊 الإحصائيات"],

        ["➕ إضافة حساب", "📋 عرض الكل"],

        ["🔐 باسورد ثابت", "🔑 تعديل باسورد"],

        ["🗑️ حذف حساب", "👁️ عرض حساب"],

        ["⚙️ الإعدادات"]

    ]

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_fixed_password_keyboard():

    """كيبورد الباسورد الثابت"""

    keyboard = [

        [InlineKeyboardButton("🔄 تغيير الباسورد الثابت", callback_data="change_fixed_password")],

        [InlineKeyboardButton("📋 الحسابات بالباسورد الثابت", callback_data="show_fixed_accounts")]

    ]

    return InlineKeyboardMarkup(keyboard)

def get_settings_keyboard():

    """كيبورد الإعدادات"""

    settings = account_manager.db["settings"]

    keyboard = [

        [InlineKeyboardButton(f"⏰ مدة الانتظار: {settings['pending_hours']}س", callback_data="edit_pending")],

        [InlineKeyboardButton(f"🔄 مدة Cooldown: {settings['cooldown_hours']}س", callback_data="edit_cooldown")],

        [InlineKeyboardButton("💾 نسخة احتياطية", callback_data="backup")],

        [InlineKeyboardButton("🗑️ مسح كل البيانات", callback_data="clear_all")]

    ]

    return InlineKeyboardMarkup(keyboard)

# معالجات الأوامر والرسائل

@error_handler

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """الأمر /start"""

    if update.effective_user.id not in ADMIN_IDS:

        await update.message.reply_text("عذراً، هذا البوت خاص بمالكه فقط. 🔒")

        return



    # تحديث إحصائية آخر تشغيل

    account_manager.db["stats"]["last_restart"] = datetime.now().isoformat()

    account_manager.save_database()



    fixed_password = account_manager.get_fixed_password()



    welcome_message = (

        "🎯 **أهلاً بيك في بوت إدارة الحسابات الاحترافي!**\n\n"

        "🚀 **الميزات الجديدة:**\n"

        "• **إعادة تشغيل تلقائي** عند حدوث أخطاء\n"

        "• **استكمال العمل** من آخر نقطة توقف\n"

        "• **رسائل منفصلة** للإيميل والباسورد\n"

        "• **إدخال منفصل:** إيميل في رسالة وباسورد في أخرى\n"

        "• **نسخ احتياطي تلقائي** كل فترة\n"

        "• **معالجة أخطاء متقدمة** مع استعادة البيانات\n"

        "• **إحصائيات شاملة** ومعدل النجاح\n"

        "• **دعم صيغ متعددة** للحسابات\n"

        "• **استخراج ذكي محسن** للبيانات\n"

        "• **🔐 باسورد ثابت:** ابعت إيميل بس ويستخدم الباسورد الثابت\n\n"

        f"📊 **الوضع الحالي:**\n"

        f"• إجمالي الحسابات: {len(account_manager.db['accounts'])}\n"

        f"• طلبات ناجحة: {account_manager.db['stats'].get('successful_requests', 0)}\n"

        f"• الباسورد الثابت: `{fixed_password}`\n"

        f"• آخر إعادة تشغيل: {account_manager.db['stats']['last_restart'][:16].replace('T', ' ')}\n\n"

        "**🚀 طريقة الاستخدام:**\n"

        "**1️⃣ ابعت إيميل:** `user@gmail.com` (هيستخدم الباسورد الثابت)\n"

        "**2️⃣ ابعت إيميل وباسورد:** `user@gmail.com password123`\n"

        "**3️⃣ أو في سطرين منفصلين**\n\n"

        "استخدم الأزرار بالأسفل للبدء! 👇"

    )



    await update.message.reply_text(

        welcome_message,

        parse_mode='Markdown',

        reply_markup=get_main_keyboard()

    )

@error_handler

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """معالجة الرسائل الرئيسية مع دعم الرسائل المنفصلة"""

    if update.effective_user.id not in ADMIN_IDS:

        return



    text = update.message.text



    # أولاً: معالجة حالات الانتظار (دولة المستخدم)

    if context.user_data.get('waiting_for_account'):

        await add_accounts(update, context)

        context.user_data['waiting_for_account'] = False

        return



    elif context.user_data.get('waiting_for_email_only'):

        await handle_email_input(update, context)

        return



    elif context.user_data.get('waiting_for_password_only'):

        await handle_password_input(update, context)

        return



    elif context.user_data.get('waiting_for_delete'):

        await delete_account_handler(update, context)

        context.user_data['waiting_for_delete'] = False

        return



    elif context.user_data.get('waiting_for_edit_email'):

        await start_edit_password(update, context)

        context.user_data['waiting_for_edit_email'] = False

        return



    elif context.user_data.get('waiting_for_new_password'):

        await complete_edit_password(update, context)

        context.user_data['waiting_for_new_password'] = False

        return



    elif context.user_data.get('waiting_for_view_account'):

        await view_account_handler(update, context)

        context.user_data['waiting_for_view_account'] = False

        return



    elif context.user_data.get('waiting_for_fixed_password'):

        await update_fixed_password_handler(update, context)

        context.user_data['waiting_for_fixed_password'] = False

        return



    elif context.user_data.get('waiting_for_pending'):

        await update_pending_hours(update, context)

        context.user_data['waiting_for_pending'] = False

        return



    elif context.user_data.get('waiting_for_cooldown'):

        await update_cooldown_hours(update, context)

        context.user_data['waiting_for_cooldown'] = False

        return



    # ثانياً: معالجة الأزرار الرئيسية

    if text == "📥 طلب حساب":

        await get_account_handler(update, context)

    elif text == "📊 الإحصائيات":

        await show_stats_handler(update, context)

    elif text == "➕ إضافة حساب":

        await start_add_accounts(update, context)

    elif text == "📋 عرض الكل":

        await show_all_accounts_handler(update, context)

    elif text == "🔐 باسورد ثابت":

        await show_fixed_password_handler(update, context)

    elif text == "🔑 تعديل باسورد":

        await update.message.reply_text(

            "🔑 **تعديل باسورد حساب:**\n\n"

            "ابعت الإيميل اللي عايز تعدل الباسورد بتاعه:"

        )

        context.user_data['waiting_for_edit_email'] = True

    elif text == "🗑️ حذف حساب":

        await update.message.reply_text("📧 ابعت الإيميل اللي عايز تحذفه:")

        context.user_data['waiting_for_delete'] = True

    elif text == "👁️ عرض حساب":

        await update.message.reply_text("👁️ ابعت الإيميل اللي عايز تشوف بياناته:")

        context.user_data['waiting_for_view_account'] = True

    elif text == "⚙️ الإعدادات":

        await show_settings_handler(update, context)

    elif text == "🔄 إعادة تشغيل البوت":

        await restart_bot(update, context)



    # ثالثاً: المعالجة الذكية التلقائية

    else:

        await smart_account_handler(update, context, text)

@error_handler

async def start_add_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """بداية عملية إضافة الحسابات مع دعم الطرق المنفصلة"""

    message = (

        "📝 **إضافة حسابات جديدة - الطرق المتاحة:**\n\n"

        "🔥 **🎯 طريقة الرسائل المنفصلة (الجديدة!):**\n"

        "• ابعت الإيميل لوحده في رسالة\n"

        "• هابعتلك تأكيد وأطلب الباسورد\n"

        "• ابعت الباسورد في الرسالة التالية\n"

        "• مثال: `user@gmail.com` ثم `password123`\n\n"

        "🚀 **طريقة متعددة (كل الصيغ):**\n"

        "• `email@example.com password123`\n"

        "• `email@example.com:password123`\n"

        "• `email@example.com | password123`\n"

        "• `email@example.com-password123`\n"

        "• `email@example.com_password123`\n"

        "• `email@example.com,password123`\n"

        "• `email@example.com;password123`\n"

        "• `email@example.com=password123`\n"

        "• الإيميل في سطر والباسورد في السطر اللي تحته\n"

        "• أو حتى الإيميل والباسورد منفصلين بمسافات\n\n"

        "**💪 مميزات الاستخراج الذكي:**\n"

        "• استخراج تلقائي من أي تنسيق\n"

        "• دعم عدة حسابات في رسالة واحدة\n"

        "• تجاهل النصوص الزائدة\n"

        "• البحث في عدة سطور\n\n"

        "**📋 أمثلة متنوعة:**\n"

        "`user1@gmail.com pass123`\n"

        "`user2@gmail.com:pass456`\n"

        "`user3@gmail.com`\n"

        "`mypassword789`\n\n"

        "🎯 **ابعت الحسابات بأي طريقة دلوقتي:**"

    )



    await update.message.reply_text(message, parse_mode='Markdown')

    context.user_data['waiting_for_account'] = True

@error_handler

async def add_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """إضافة حسابات مع دعم الطريقة المنفصلة والمتعددة"""

    text = update.message.text.strip()



    # التحقق إذا كان إيميل لوحده (طريقة منفصلة)

    if account_manager.is_valid_email(text) and len(text.split()) == 1:

        await handle_single_email_input(update, context, text)

        return



    # معالجة متعددة كالطريقة العادية

    await add_accounts_multiple(update, context)

@error_handler

async def handle_single_email_input(update: Update, context: ContextTypes.DEFAULT_TYPE, email: str):

    """معالجة إدخال إيميل واحد فقط"""

    email = email.lower().strip()



    # التحقق من صحة الإيميل

    if not account_manager.is_valid_email(email):

        await update.message.reply_text(

            f"❌ **صيغة الإيميل غير صحيحة:**\n`{email}`\n\n"

            "💡 **جرب إيميل صحيح أو ابعت حساب كامل بالطريقة العادية.**"

        )

        context.user_data['waiting_for_account'] = False

        return



    # حفظ الإيميل وطلب الباسورد

    context.user_data['pending_email'] = email

    context.user_data['waiting_for_account'] = False

    context.user_data['waiting_for_password_only'] = True



    # التحقق إذا كان الحساب موجود

    account_info = account_manager.get_account_info(email)



    if account_info:

        message = (

            f"📧 **تم استلام الإيميل:**\n`{email}`\n\n"

            f"⚠️ **الحساب موجود بالفعل!**\n"

            f"🔑 **الباسورد الحالي:** `{account_info['password']}`\n"

            f"📊 **الحالة:** {account_info['status']}\n"

            f"⏱️ **الوقت المتبقي:** {account_info['time_left']}\n\n"

            f"🔄 **هل عايز تحديث الباسورد؟**\n"

            f"ابعت الباسورد الجديد أو ابعت /cancel للإلغاء:"

        )

    else:

        message = (

            f"✅ **تم استلام الإيميل بنجاح:**\n`{email}`\n\n"

            f"🔑 **دلوقتي ابعت الباسورد في الرسالة التالية:**\n\n"

            f"💡 **مثال:** `password123` أو `mypass456`\n"

            f"📝 **ملاحظة:** ابعت الباسورد لوحده بدون أي كلام إضافي"

        )



    await update.message.reply_text(message, parse_mode='Markdown')

@error_handler

async def handle_password_input(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """معالجة إدخال الباسورد بعد الإيميل"""

    password = update.message.text.strip()

    email = context.user_data.get('pending_email')



    if not email:

        await update.message.reply_text(

            "❌ **خطأ:** مفيش إيميل مؤقت محفوظ.\n"

            "ابدأ العملية من جديد بإرسال الإيميل أول."

        )

        context.user_data['waiting_for_password_only'] = False

        return



    # إزالة البيانات المؤقتة

    del context.user_data['pending_email']

    context.user_data['waiting_for_password_only'] = False



    # التحقق من صحة الباسورد

    if not password or len(password) < 3:

        await update.message.reply_text(

            f"❌ **الباسورد غير صالح:**\n`{password}`\n\n"

            "💡 **الباسورد يجب أن يكون:**\n"

            "• أطول من 3 أحرف\n"

            "• لا يحتوي على مسافات\n"

            "• ليس كلمة عامة\n\n"

            "🔄 **ابدأ العملية من جديد أو استخدم الطريقة العادية.**"

        )

        return



    # محاولة إضافة الحساب

    success, message = account_manager.add_account(email, password)



    if success:

        await update.message.reply_text(

            f"🎉 **تم إضافة الحساب بنجاح!**\n\n"

            f"📧 **الإيميل:** `{email}`\n"

            f"🔑 **الباسورد:** `{password}`\n\n"

            f"💡 **التفاصيل:** {message}\n"

            f"⏰ **سيكون متاح بعد {account_manager.db['settings']['pending_hours']} ساعة**\n\n"

            f"📊 **الإحصائيات المحدثة:**\n"

            f"• إجمالي الحسابات: **{len(account_manager.db['accounts'])}**"

        )



        # حفظ فوري للبيانات

        account_manager.save_database()



    else:

        await update.message.reply_text(

            f"❌ **فشل في إضافة الحساب:**\n{message}\n\n"

            f"📧 **الإيميل:** `{email}`\n"

            f"🔑 **الباسورد:** `{password}`\n\n"

            "🔄 **جرب مرة تانية أو استخدم طريقة مختلفة.**"

        )

@error_handler

async def handle_email_input(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """معالجة إدخال إيميل منفصل - يستخدم في حالات خاصة"""

    pass

@error_handler

async def add_accounts_multiple(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """إضافة حسابات متعددة بالطريقة العادية"""

    text = update.message.text



    # إرسال رسالة معالجة

    processing_msg = await update.message.reply_text("🔄 **جاري المعالجة بالذكاء الاصطناعي...**", parse_mode='Markdown')



    try:

        # تحديث رسالة المعالجة

        await processing_msg.edit_text("🧠 **تحليل النص واستخراج البيانات...**", parse_mode='Markdown')



        credentials = account_manager.extract_credentials(text)



        if not credentials:

            await processing_msg.edit_text(

                "❌ **فشل في استخراج الحسابات من النص.**\n\n"

                "🔍 **جرب الطرق دي:**\n\n"

                "**1️⃣ الطريقة المنفصلة الجديدة:**\n"

                "• ابعت الإيميل لوحده: `email@domain.com`\n"

                "• بعدين الباسورد لوحده: `password123`\n\n"

                "**2️⃣ صيغة بسيطة:**\n"

                "`email@domain.com password123`\n\n"

                "**3️⃣ مع فواصل:**\n"

                "`email@domain.com:password123`\n"

                "`email@domain.com|password123`\n\n"

                "**4️⃣ متعدد:**\n"

                "`email1@domain.com pass1`\n"

                "`email2@domain.com pass2`\n\n"

                "🎯 **نصيحة:** الطريقة المنفصلة أدق وأسهل!",

                parse_mode='Markdown'

            )

            return



        # تحديث رسالة المعالجة

        await processing_msg.edit_text(f"✅ **تم استخراج {len(credentials)} حساب!**\n🔄 **جاري الإضافة...**", parse_mode='Markdown')



        added_count = 0

        updated_count = 0

        failed_count = 0

        details = []



        for email, password in credentials:

            success, message = account_manager.add_account(email, password)

            if success:

                if "تعديل" in message:

                    updated_count += 1

                    details.append(f"🔄 `{email}` - تم تعديل الباسورد")

                else:

                    added_count += 1

                    details.append(f"✅ `{email}` - أُضيف بنجاح")

            else:

                failed_count += 1

                details.append(f"❌ `{email}` - {message}")



        # إعداد رسالة النتائج الشاملة

        result_message = f"📊 **نتائج المعالجة الذكية:**\n\n"



        if added_count > 0:

            result_message += f"✅ **تم إضافة {added_count} حساب جديد!**\n"

            result_message += f"⏰ **سيكونوا متاحين بعد {account_manager.db['settings']['pending_hours']} ساعة.**\n\n"



        if updated_count > 0:

            result_message += f"🔄 **تم تعديل {updated_count} حساب موجود.**\n\n"



        if failed_count > 0:

            result_message += f"❌ **فشل في إضافة {failed_count} حساب.**\n\n"



        # إضافة الإحصائيات المحدثة

        stats = account_manager.get_statistics()

        result_message += f"📈 **الإحصائيات المحدثة:**\n"

        result_message += f"• إجمالي الحسابات: **{stats['total']}**\n"

        result_message += f"• المتاح الآن: **{stats['available']}**\n"

        result_message += f"• في الانتظار: **{stats['pending']}**\n"

        result_message += f"• في Cooldown: **{stats['cooldown']}**\n\n"



        result_message += "**🔍 التفاصيل:**\n" + "\n".join(details[:15])



        if len(details) > 15:

            result_message += f"\n... **و {len(details) - 15} حساب آخر**"



        await processing_msg.edit_text(result_message, parse_mode='Markdown')



        # حفظ فوري للبيانات

        account_manager.save_database()



    except Exception as e:

        await processing_msg.edit_text(f"❌ **حدث خطأ في المعالجة:** {str(e)}")

        logger.error(f"خطأ في إضافة الحسابات: {e}")

@error_handler

async def smart_account_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):

    """المعالج الذكي المُصحح - يعطي أولوية للباسورد الثابت"""



    # رسالة تحليل

    analysis_msg = await update.message.reply_text("🧠 **جاري التحليل...**", parse_mode='Markdown')



    # تحديد نوع المدخل

    input_type = account_manager.detect_input_type(text)



    if input_type == "email":

        # **الحل الصحيح: إيميل فقط = استخدام الباسورد الثابت**

        await handle_email_only(update, context, text, analysis_msg)



    elif input_type == "password":

        # باسورد فقط = حفظه ومطالبة بالإيميل

        await handle_password_only(update, context, text, analysis_msg)



    elif input_type == "mixed":

        # نص مختلط = محاولة استخراج

        await handle_mixed_input(update, context, text, analysis_msg)



    else:

        # غير معروف

        await analysis_msg.edit_text(

            f"❓ **مش قادر أحلل النص ده:**\n`{text}`\n\n"

            f"💡 **جرب كده:**\n"

            f"• `user@gmail.com` (للباسورد الثابت)\n"

            f"• `user@gmail.com password123`\n"

            f"• أو استخدم الأزرار",

            parse_mode='Markdown'

        )

@error_handler

async def handle_email_only(update: Update, context: ContextTypes.DEFAULT_TYPE, email: str, analysis_msg):

    """معالجة إيميل فقط - استخدام الباسورد الثابت فوراً"""

    try:

        email = email.lower().strip()



        if not account_manager.is_valid_email(email):

            await analysis_msg.edit_text(

                f"❌ **الإيميل غير صحيح:** `{email}`\n\n"

                f"💡 **مثال صحيح:** `user@gmail.com`",

                parse_mode='Markdown'

            )

            return



        # **الحل الصحيح**: إضافة الحساب بالباسورد الثابت

        success, message = account_manager.add_account_with_fixed_password(email)

        fixed_password = account_manager.get_fixed_password()



        if success:

            await analysis_msg.edit_text(

                f"✅ **تم إضافة الحساب بالباسورد الثابت!**\n\n"

                f"📧 **الإيميل:** `{email}`\n"

                f"🔐 **الباسورد الثابت:** `{fixed_password}`\n\n"

                f"💡 **التفاصيل:** {message}\n"

                f"⏰ **سيكون متاح بعد {account_manager.db['settings']['pending_hours']} ساعة**\n\n"

                f"📊 **إجمالي الحسابات:** {len(account_manager.db['accounts'])}\n\n"

                f"🚀 **ابعت إيميل آخر لإضافة المزيد!**",

                parse_mode='Markdown'

            )

        else:

            await analysis_msg.edit_text(

                f"❌ **فشل في الإضافة:** {message}\n\n"

                f"📧 **الإيميل:** `{email}`\n"

                f"🔐 **الباسورد الثابت:** `{fixed_password}`",

                parse_mode='Markdown'

            )



    except Exception as e:

        logger.error(f"خطأ في معالجة إيميل فقط: {e}")

        await analysis_msg.edit_text(f"❌ **خطأ:** `{str(e)}`", parse_mode='Markdown')

@error_handler

async def handle_password_only(update: Update, context: ContextTypes.DEFAULT_TYPE, password: str, analysis_msg):

    """معالجة باسورد فقط"""

    password = password.strip()

    context.user_data['pending_password'] = password



    await analysis_msg.edit_text(

        f"✅ **تم حفظ الباسورد:** `{password}`\n\n"

        f"📧 **دلوقتي ابعت الإيميل:**\n"

        f"💡 **مثال:** `user@gmail.com`",

        parse_mode='Markdown'

    )

@error_handler

async def handle_mixed_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, analysis_msg):

    """معالجة نص مختلط"""

    credentials = account_manager.extract_credentials(text)



    if credentials:

        await analysis_msg.edit_text(f"🎯 **تم اكتشاف {len(credentials)} حساب - جاري الإضافة...**")

        await add_multiple_accounts(update, context, credentials, analysis_msg)

    else:

        await analysis_msg.edit_text(

            f"❓ **مش قادر أستخرج حسابات من النص ده:**\n`{text}`\n\n"

            f"💡 **جرب كده:**\n"

            f"• `user@gmail.com password123`\n"

            f"• أو في سطرين منفصلين",

            parse_mode='Markdown'

        )

@error_handler

async def add_multiple_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE, credentials: List[Tuple[str, str]], analysis_msg):

    """إضافة حسابات متعددة"""

    added_count = 0

    updated_count = 0

    failed_count = 0

    details = []



    for email, password in credentials:

        success, message = account_manager.add_account(email, password)

        if success:

            if "تعديل" in message:

                updated_count += 1

                details.append(f"🔄 `{email}` - تم التعديل")

            else:

                added_count += 1

                details.append(f"✅ `{email}` - تم الإضافة")

        else:

            failed_count += 1

            details.append(f"❌ `{email}` - {message}")



    result_message = f"📊 **نتائج الإضافة:**\n\n"



    if added_count > 0:

        result_message += f"✅ **أُضيف {added_count} حساب جديد**\n"



    if updated_count > 0:

        result_message += f"🔄 **تم تعديل {updated_count} حساب**\n"



    if failed_count > 0:

        result_message += f"❌ **فشل في {failed_count} حساب**\n"



    result_message += f"\n📈 **إجمالي الحسابات:** {len(account_manager.db['accounts'])}\n\n"



    result_message += "**🔍 التفاصيل:**\n" + "\n".join(details[:5])



    if len(details) > 5:

        result_message += f"\n... **و {len(details) - 5} آخرين**"



    await analysis_msg.edit_text(result_message, parse_mode='Markdown')

@error_handler

async def get_account_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """طلب حساب متاح مع إرسال في رسائل منفصلة تماماً"""

    try:

        # رسالة انتظار

        wait_msg = await update.message.reply_text("🔍 **جاري البحث عن حساب متاح...**", parse_mode='Markdown')



        result = account_manager.get_available_account()



        if not result:

            stats = account_manager.get_statistics()

            message = "❌ **مفيش حسابات متاحة دلوقتي.**\n\n"



            if stats["next_available"]:

                message += f"⏰ **أقرب حساب هيكون متاح:**\n"

                message += f"📧 `{stats['next_available_email']}`\n"

                message += f"🕒 **بعد:** {stats['next_available']}\n\n"



            message += f"📊 **الإحصائيات الحالية:**\n"

            message += f"• ✅ المتاح: **{stats['available']}**\n"

            message += f"• ⏳ في الانتظار: **{stats['pending']}**\n"

            message += f"• 🔄 في Cooldown: **{stats['cooldown']}**\n"

            message += f"• 📈 معدل النجاح: **{stats.get('success_rate', 0):.1f}%**"



            await wait_msg.edit_text(message, parse_mode='Markdown')

            return



        email, password = result



        # حذف رسالة الانتظار

        await wait_msg.delete()



        # رسالة تأكيد إيجاد الحساب

        confirm_msg = await update.message.reply_text(

            "✅ **تم إيجاد حساب متاح!**\n🔄 **جاري إرسال البيانات في رسائل منفصلة...**",

            parse_mode='Markdown'

        )



        # انتظار ثانيتين

        await asyncio.sleep(0)



        # حذف رسالة التأكيد

        await confirm_msg.delete()



        # **الرسالة الأولى: الإيميل فقط**

        email_message = (

            f"✅✅✅✅✅✅✅ ****\n\n"

            f"`{email}`\n\n"

            f"✅✅✅✅✅✅✅ ****"

        )



        await update.message.reply_text(email_message, parse_mode='Markdown')



        # انتظار 3 ثوان للفصل التام

        await asyncio.sleep(4)



        # **الرسالة الثانية: الباسورد فقط**

        password_message = (

            f"🚀🚀🚀🚀🚀🚀 **:**\n\n"

            f"`{password}`\n\n"

            f"🚀🚀🚀🚀🚀🚀 **  **"

        )



        await update.message.reply_text(password_message, parse_mode='Markdown')

    except Exception as e:

        logger.error(f"خطأ في طلب الحساب: {e}")

        await update.message.reply_text(f"❌ **حدث خطأ:** {str(e)}")

@error_handler

async def show_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """عرض الإحصائيات الشاملة"""

    try:

        stats = account_manager.get_statistics()

        fixed_password = account_manager.get_fixed_password()



        # حساب الحسابات بالباسورد الثابت

        fixed_count = sum(1 for email, data in account_manager.db["accounts"].items()

                         if data["password"] == fixed_password)



        # حساب النسب المئوية

        total = stats['total']

        if total > 0:

            available_percent = (stats['available'] / total) * 100

            pending_percent = (stats['pending'] / total) * 100

            cooldown_percent = (stats['cooldown'] / total) * 100

        else:

            available_percent = pending_percent = cooldown_percent = 0



        # إنشاء شريط تقدم بصري

        progress_bar = ""

        bar_length = 10

        if total > 0:

            available_bars = max(1, int((stats['available'] / total) * bar_length)) if stats['available'] > 0 else 0

            pending_bars = max(1, int((stats['pending'] / total) * bar_length)) if stats['pending'] > 0 else 0

            cooldown_bars = bar_length - available_bars - pending_bars

            cooldown_bars = max(0, cooldown_bars)



            progress_bar = "🟢" * available_bars + "🟡" * pending_bars + "🔴" * cooldown_bars



        message = (

            f"📊 **الإحصائيات التفصيلية:**\n\n"

            f"📈 **إجمالي الحسابات:** {stats['total']}\n\n"

            f"✅ **متاح الآن:** {stats['available']} ({available_percent:.1f}%)\n"

            f"⏳ **في الانتظار:** {stats['pending']} ({pending_percent:.1f}%)\n"

            f"🔄 **في Cooldown:** {stats['cooldown']} ({cooldown_percent:.1f}%)\n\n"

        )



        if progress_bar:

            message += f"📊 **التوزيع البصري:**\n{progress_bar}\n"

            message += f"🟢 متاح | 🟡 انتظار | 🔴 cooldown\n\n"



        message += f"🔐 **الباسورد الثابت:** `{fixed_password}`\n"

        message += f"📊 **حسابات بالباسورد الثابت:** {fixed_count}\n\n"



        if stats["next_available"]:

            message += f"⏰ **أقرب حساب متاح:**\n"

            message += f"📧 `{stats['next_available_email']}`\n"

            message += f"🕒 بعد: **{stats['next_available']}**\n\n"



        # إحصائيات الاستخدام

        message += f"🎯 **إحصائيات الاستخدام:**\n"

        message += f"• 📈 إجمالي الطلبات: **{stats['total_requests']}**\n"

        message += f"• ✅ طلبات ناجحة: **{stats['successful_requests']}**\n"

        message += f"• 📊 معدل النجاح: **{stats.get('success_rate', 0):.1f}%**\n"



        # معلومات النظام

        last_restart = account_manager.db['stats'].get('last_restart', '')

        if last_restart:

            restart_time = last_restart[:16].replace('T', ' ')

            message += f"• 🔄 آخر إعادة تشغيل: **{restart_time}**"



        await update.message.reply_text(message, parse_mode='Markdown')



    except Exception as e:

        logger.error(f"خطأ في عرض الإحصائيات: {e}")

        await update.message.reply_text("❌ حدث خطأ في عرض الإحصائيات")

@error_handler

async def show_all_accounts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """عرض كل الحسابات مع تجميع ذكي"""

    try:

        accounts = []

        now = datetime.now()



        for email, data in account_manager.db["accounts"].items():

            available_at = datetime.fromisoformat(data["available_at"])

            time_diff = available_at - now



            if time_diff.total_seconds() > 0:

                hours = int(time_diff.total_seconds() // 3600)

                minutes = int((time_diff.total_seconds() % 3600) // 60)

                time_str = f"{hours}س {minutes}د"

                current_status = data["status"]

            else:

                time_str = "متاح الآن"

                current_status = "available"

                data["status"] = "available"



            accounts.append({

                "email": email,

                "password": data["password"],

                "status": current_status,

                "time_left": time_str,

                "use_count": data["use_count"]

            })



        if not accounts:

            await update.message.reply_text(

                "❌ **مفيش حسابات مضافة**\n\n"

                "💡 **ابعت إيميل جديد لإضافة حساب!**",

                parse_mode='Markdown'

            )

            return



        # تقسيم الحسابات حسب الحالة

        available_accounts = [acc for acc in accounts if acc['time_left'] == "متاح الآن"]

        pending_accounts = [acc for acc in accounts if acc['status'] == "pending"]

        cooldown_accounts = [acc for acc in accounts if acc['status'] == "used"]



        message = f"📋 **كل الحسابات ({len(accounts)}):**\n\n"



        if available_accounts:

            message += f"✅ **المتاحة ({len(available_accounts)}):**\n"

            for i, acc in enumerate(available_accounts[:5], 1):

                message += f"{i}. `{acc['email']}` (استُخدم {acc['use_count']} مرة)\n"

            if len(available_accounts) > 5:

                message += f"... و {len(available_accounts) - 5} حساب آخر\n"

            message += "\n"



        if pending_accounts:

            message += f"⏳ **في الانتظار ({len(pending_accounts)}):**\n"

            for i, acc in enumerate(pending_accounts[:3], 1):

                message += f"{i}. `{acc['email']}` - متبقي: {acc['time_left']}\n"

            if len(pending_accounts) > 3:

                message += f"... و {len(pending_accounts) - 3} حساب آخر\n"

            message += "\n"



        if cooldown_accounts:

            message += f"🔄 **في Cooldown ({len(cooldown_accounts)}):**\n"

            for i, acc in enumerate(cooldown_accounts[:3], 1):

                message += f"{i}. `{acc['email']}` - متبقي: {acc['time_left']}\n"

            if len(cooldown_accounts) > 3:

                message += f"... و {len(cooldown_accounts) - 3} حساب آخر\n"



        message += f"\n🚀 **ابعت إيميل جديد لإضافة المزيد!**"



        await update.message.reply_text(message, parse_mode='Markdown')

        account_manager.save_database()



    except Exception as e:

        logger.error(f"خطأ في عرض الحسابات: {e}")

        await update.message.reply_text("❌ حدث خطأ في عرض الحسابات")

@error_handler

async def show_fixed_password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """عرض إدارة الباسورد الثابت"""

    fixed_password = account_manager.get_fixed_password()



    # حساب الحسابات بالباسورد الثابت

    fixed_count = sum(1 for email, data in account_manager.db["accounts"].items()

                     if data["password"] == fixed_password)



    message = (

        f"🔐 **إدارة الباسورد الثابت:**\n\n"

        f"🔑 **الباسورد الحالي:** `{fixed_password}`\n"

        f"📊 **الحسابات التي تستخدمه:** {fixed_count} حساب\n\n"

        f"💡 **طريقة الاستخدام:**\n"

        f"• ابعت إيميل لوحده ← سيُضاف بالباسورد الثابت\n"

        f"• مثال: `user@gmail.com` ← باسورد: `{fixed_password}`\n\n"

        f"🔧 **اختر عملية:**"

    )



    await update.message.reply_text(

        message,

        parse_mode='Markdown',

        reply_markup=get_fixed_password_keyboard()

    )

@error_handler

async def show_settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """عرض الإعدادات المتقدمة"""

    settings = account_manager.db["settings"]



    settings_text = (

        f"⚙️ **الإعدادات الحالية:**\n\n"

        f"⏰ **مدة الانتظار للحسابات الجديدة:** {settings['pending_hours']} ساعة\n"

        f"🔄 **مدة Cooldown بعد الاستخدام:** {settings['cooldown_hours']} ساعة\n"

        f"🔐 **الباسورد الثابت:** `{settings['fixed_password']}`\n\n"

        f"📊 **معلومات قاعدة البيانات:**\n"

        f"• إجمالي الحسابات: {len(account_manager.db['accounts'])}\n"

        f"• سجلات الأنشطة: {len(account_manager.db['logs'])}\n"

        f"• حجم الملف: {os.path.getsize(DB_FILE) if os.path.exists(DB_FILE) else 0} بايت\n\n"

        f"🔧 **اختر إعداد للتعديل:**"

    )



    await update.message.reply_text(

        settings_text,

        parse_mode='Markdown',

        reply_markup=get_settings_keyboard()

    )

@error_handler

async def start_edit_password(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """بداية عملية تعديل الباسورد"""

    email = update.message.text.strip()



    account_info = account_manager.get_account_info(email)

    if not account_info:

        await update.message.reply_text(f"❌ **الحساب غير موجود:**\n`{email}`", parse_mode='Markdown')

        return



    # عرض معلومات الحساب الحالية

    await update.message.reply_text(

        f"🔍 **معلومات الحساب الحالية:**\n\n"

        f"📧 **الإيميل:** `{account_info['email']}`\n"

        f"🔑 **الباسورد الحالي:** `{account_info['password']}`\n"

        f"📊 **الحالة:** {account_info['status']}\n"

        f"⏱️ **الوقت المتبقي:** {account_info['time_left']}\n"

        f"📈 **عدد الاستخدامات:** {account_info['use_count']}\n\n"

        f"🔑 **ابعت الباسورد الجديد:**",

        parse_mode='Markdown'

    )



    context.user_data['edit_email'] = email

    context.user_data['waiting_for_new_password'] = True

@error_handler

async def complete_edit_password(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """إتمام عملية تعديل الباسورد"""

    new_password = update.message.text.strip()

    email = context.user_data.get('edit_email')



    if not email:

        await update.message.reply_text("❌ حدث خطأ، ابدأ العملية من جديد.")

        return



    del context.user_data['edit_email']



    success, message = account_manager.update_password(email, new_password)



    if success:

        await update.message.reply_text(

            f"✅ **تم تعديل الباسورد بنجاح!**\n\n"

            f"📧 **الإيميل:** `{email}`\n"

            f"🔑 **الباسورد الجديد:** `{new_password}`\n\n"

            f"💡 **التفاصيل:** {message}",

            parse_mode='Markdown'

        )

    else:

        await update.message.reply_text(f"❌ **فشل في تعديل الباسورد:** {message}")

@error_handler

async def delete_account_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """حذف حساب مع تأكيد"""

    email = update.message.text.strip()



    # التحقق من وجود الحساب أولاً

    account_info = account_manager.get_account_info(email)

    if not account_info:

        await update.message.reply_text(f"❌ **الحساب غير موجود:**\n`{email}`", parse_mode='Markdown')

        return



    if account_manager.delete_account(email):

        await update.message.reply_text(

            f"✅ **تم حذف الحساب بنجاح!**\n\n"

            f"📧 **الإيميل المحذوف:** `{email}`\n"

            f"📊 **كان مستخدم:** {account_info['use_count']} مرة\n"

            f"🗑️ **تم الحذف نهائياً من قاعدة البيانات**",

            parse_mode='Markdown'

        )

    else:

        await update.message.reply_text(f"❌ **فشل في حذف الحساب:** {email}")

@error_handler

async def view_account_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """عرض تفاصيل حساب معين"""

    email = update.message.text.strip()



    account_info = account_manager.get_account_info(email)

    if not account_info:

        await update.message.reply_text(f"❌ **الحساب غير موجود:**\n`{email}`", parse_mode='Markdown')

        return



    status_emoji = {

        "available": "✅",

        "pending": "⏳",

        "used": "🔄"

    }



    # حساب الوقت منذ الإضافة

    try:

        added_date = datetime.fromisoformat(account_info['added_at'])

        days_old = (datetime.now() - added_date).days

        age_str = f"{days_old} يوم" if days_old > 0 else "اليوم"

    except:

        age_str = "غير معروف"



    details_message = (

        f"👁️ **تفاصيل الحساب الكاملة:**\n\n"

        f"📧 **الإيميل:** `{account_info['email']}`\n"

        f"🔑 **الباسورد:** `{account_info['password']}`\n"

        f"{status_emoji.get(account_info['status'], '❓')} **الحالة:** {account_info['status']}\n"

        f"⏱️ **الوقت المتبقي:** {account_info['time_left']}\n"

        f"📊 **عدد مرات الاستخدام:** {account_info['use_count']}\n"

        f"🏆 **الأولوية:** {account_info['priority']}\n"

        f"📅 **تاريخ الإضافة:** {account_info['added_at'][:10]}\n"

        f"⌛ **عمر الحساب:** {age_str}"

    )



    await update.message.reply_text(details_message, parse_mode='Markdown')

@error_handler

async def update_fixed_password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """تحديث الباسورد الثابت"""

    new_password = update.message.text.strip()



    success, message = account_manager.update_fixed_password(new_password)



    if success:

        await update.message.reply_text(

            f"✅ **تم تحديث الباسورد الثابت!**\n\n"

            f"💡 **التفاصيل:** {message}\n\n"

            f"📝 **سيتم استخدامه للحسابات الجديدة التي تُضاف بإيميل فقط**",

            parse_mode='Markdown'

        )

    else:

        await update.message.reply_text(f"❌ **فشل في التحديث:** {message}")

@error_handler

async def update_pending_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """تحديث مدة الانتظار"""

    try:

        hours = int(update.message.text.strip())

        if hours < 0 or hours > 168:

            await update.message.reply_text("❌ المدة يجب أن تكون بين 0 و 168 ساعة.")

            return



        old_hours = account_manager.db["settings"]["pending_hours"]

        account_manager.db["settings"]["pending_hours"] = hours

        account_manager.add_log("تعديل الإعدادات", f"تم تغيير مدة الانتظار من {old_hours} إلى {hours} ساعة")

        account_manager.save_database()



        await update.message.reply_text(

            f"✅ **تم تحديث مدة الانتظار!**\n\n"

            f"🔄 **من:** {old_hours} ساعة\n"

            f"✅ **إلى:** {hours} ساعة\n\n"

            f"📝 **ملاحظة:** سيتم تطبيقها على الحسابات الجديدة فقط.",

            parse_mode='Markdown'

        )

    except ValueError:

        await update.message.reply_text("❌ من فضلك ادخل رقم صحيح.")

@error_handler

async def update_cooldown_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """تحديث مدة Cooldown"""

    try:

        hours = int(update.message.text.strip())

        if hours < 0 or hours > 168:

            await update.message.reply_text("❌ المدة يجب أن تكون بين 0 و 168 ساعة.")

            return



        old_hours = account_manager.db["settings"]["cooldown_hours"]

        account_manager.db["settings"]["cooldown_hours"] = hours

        account_manager.add_log("تعديل الإعدادات", f"تم تغيير مدة Cooldown من {old_hours} إلى {hours} ساعة")

        account_manager.save_database()



        await update.message.reply_text(

            f"✅ **تم تحديث مدة Cooldown!**\n\n"

            f"🔄 **من:** {old_hours} ساعة\n"

            f"✅ **إلى:** {hours} ساعة\n\n"

            f"📝 **ملاحظة:** سيتم تطبيقها على الاستخدامات القادمة.",

            parse_mode='Markdown'

        )

    except ValueError:

        await update.message.reply_text("❌ من فضلك ادخل رقم صحيح.")

@error_handler

async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """إعادة تشغيل البوت"""

    global should_restart



    await update.message.reply_text(

        "🔄 **جاري إعادة تشغيل البوت...**\n\n"

        "⏳ انتظر لحظات وجرب مرة تانية.",

        parse_mode='Markdown'

    )



    # حفظ البيانات قبل إعادة التشغيل

    account_manager.add_log("إعادة تشغيل يدوي", "تم طلب إعادة التشغيل من المستخدم")

    account_manager.save_database()



    should_restart = True

    context.application.stop_running()

@error_handler

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """معالجة أزرار Inline المتقدمة"""

    query = update.callback_query

    await query.answer()



    try:

        if query.data == "change_fixed_password":

            current_password = account_manager.get_fixed_password()

            await query.message.reply_text(

                f"🔐 **تغيير الباسورد الثابت:**\n\n"

                f"🔑 **الحالي:** `{current_password}`\n\n"

                f"💡 **ابعت الباسورد الجديد (3 أحرف على الأقل):**",

                parse_mode='Markdown'

            )

            context.user_data['waiting_for_fixed_password'] = True



        elif query.data == "show_fixed_accounts":

            fixed_password = account_manager.get_fixed_password()

            fixed_accounts = []



            for email, data in account_manager.db["accounts"].items():

                if data["password"] == fixed_password:

                    account_info = account_manager.get_account_info(email)

                    if account_info:

                        fixed_accounts.append(account_info)



            if not fixed_accounts:

                await query.message.reply_text(

                    f"📋 **مفيش حسابات بالباسورد الثابت**\n\n"

                    f"🔐 **الباسورد الثابت:** `{fixed_password}`\n"

                    f"💡 **ابعت إيميل لإضافة حساب بالباسورد الثابت!**",

                    parse_mode='Markdown'

                )

            else:

                message = f"📋 **حسابات بالباسورد الثابت ({len(fixed_accounts)}):**\n\n"

                message += f"🔐 **الباسورد:** `{fixed_password}`\n\n"



                for i, acc in enumerate(fixed_accounts[:8], 1):

                    status_emoji = {"available": "✅", "pending": "⏳", "used": "🔄"}.get(acc['status'], "❓")

                    message += f"{i}. {status_emoji} `{acc['email']}`\n"

                    message += f"   ⏱️ {acc['time_left']} | استُخدم {acc['use_count']} مرة\n\n"



                if len(fixed_accounts) > 8:

                    message += f"... و {len(fixed_accounts) - 8} حساب آخر\n\n"



                message += f"🚀 **ابعت إيميل جديد لإضافة المزيد!**"



                await query.message.reply_text(message, parse_mode='Markdown')



        elif query.data == "edit_pending":

            await query.message.reply_text("⏰ ادخل مدة الانتظار الجديدة بالساعات (0-168):")

            context.user_data['waiting_for_pending'] = True



        elif query.data == "edit_cooldown":

            await query.message.reply_text("🔄 ادخل مدة Cooldown الجديدة بالساعات (0-168):")

            context.user_data['waiting_for_cooldown'] = True



        elif query.data == "backup":

            # إنشاء نسخة احتياطية مخصصة

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            backup_filename = f"manual_backup_{timestamp}.json"



            # نسخ الملف الأساسي

            import shutil

            backup_path = os.path.join(BACKUP_DIR, backup_filename)

            shutil.copy2(DB_FILE, backup_path)



            # إرسال الملف

            with open(backup_path, 'rb') as backup_file:

                await query.message.reply_document(

                    document=backup_file,

                    filename=backup_filename,

                    caption=(

                        f"💾 **نسخة احتياطية من قاعدة البيانات**\n\n"

                        f"📅 التاريخ: {datetime.now().strftime('%Y/%m/%d %H:%M')}\n"

                        f"📊 الحسابات: {len(account_manager.db['accounts'])}\n"

                        f"📜 السجلات: {len(account_manager.db['logs'])}\n"

                        f"💾 الحجم: {os.path.getsize(backup_path)} بايت"

                    ),

                    parse_mode='Markdown'

                )



        elif query.data == "clear_all":

            # تأكيد الحذف المتقدم

            stats = account_manager.get_statistics()

            confirm_keyboard = [

                [

                    InlineKeyboardButton("✅ نعم، احذف كل شيء", callback_data="confirm_clear"),

                    InlineKeyboardButton("❌ إلغاء", callback_data="cancel_clear")

                ]

            ]

            await query.message.reply_text(

                f"⚠️ **تحذير خطير!**\n\n"

                f"أنت على وشك حذف:\n"

                f"• {stats['total']} حساب\n"

                f"• {len(account_manager.db['logs'])} سجل نشاط\n"

                f"• جميع الإعدادات المخصصة\n\n"

                f"❗ **هذا الإجراء لا يمكن التراجع عنه!**\n"

                f"تأكد من وجود نسخة احتياطية قبل المتابعة.",

                parse_mode='Markdown',

                reply_markup=InlineKeyboardMarkup(confirm_keyboard)

            )



        elif query.data == "confirm_clear":

            # إنشاء نسخة احتياطية طارئة قبل الحذف

            emergency_backup = f"emergency_before_clear_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

            try:

                import shutil

                shutil.copy2(DB_FILE, emergency_backup)

            except:

                pass



            # حذف كل البيانات

            account_manager.db = {

                "accounts": {},

                "settings": {

                    "pending_hours": DEFAULT_PENDING_HOURS,

                    "cooldown_hours": DEFAULT_COOLDOWN_HOURS,

                    "fixed_password": DEFAULT_FIXED_PASSWORD

                },

                "logs": [],

                "stats": {

                    "total_requests": 0,

                    "successful_requests": 0,

                    "last_restart": datetime.now().isoformat()

                }

            }

            account_manager.save_database()



            await query.message.reply_text(

                f"✅ **تم حذف جميع البيانات بنجاح!**\n\n"

                f"💾 تم إنشاء نسخة احتياطية طارئة: `{emergency_backup}`\n"

                f"🔄 البوت جاهز للاستخدام من جديد.",

                parse_mode='Markdown'

            )



        elif query.data == "cancel_clear":

            await query.message.reply_text("❌ **تم إلغاء عملية الحذف.**", parse_mode='Markdown')



    except Exception as e:

        logger.error(f"خطأ في معالجة الأزرار: {e}")

        await query.answer("❌ حدث خطأ", show_alert=True)

def handle_signals():

    """معالجة إشارات النظام"""

    def signal_handler(signum, frame):

        global should_restart

        logger.info(f"تم استلام إشارة {signum}")



        # حفظ البيانات قبل الإغلاق

        account_manager.add_log("إيقاف النظام", f"تم استلام إشارة {signum}")

        account_manager.save_database()



        if signum == signal.SIGUSR1:  # إعادة التشغيل

            should_restart = True



        raise KeyboardInterrupt()



    # تسجيل معالجات الإشارات

    signal.signal(signal.SIGINT, signal_handler)

    signal.signal(signal.SIGTERM, signal_handler)



    # إشارة مخصصة لإعادة التشغيل (في Linux)

    if hasattr(signal, 'SIGUSR1'):

        signal.signal(signal.SIGUSR1, signal_handler)

# إنشاء Flask App
app = Flask(__name__)

@app.route('/')
def home():
    """الصفحة الرئيسية"""
    stats = account_manager.get_statistics()
    return f"""
    <html>
    <head><title>Telegram Bot Status</title></head>
    <body style="font-family: Arial; padding: 20px; background: #f5f5f5;">
        <h1>✅ البوت شغال!</h1>
        <div style="background: white; padding: 15px; border-radius: 8px; margin-top: 20px;">
            <h2>📊 الإحصائيات:</h2>
            <p>📈 إجمالي الحسابات: <strong>{stats['total']}</strong></p>
            <p>✅ المتاح الآن: <strong>{stats['available']}</strong></p>
            <p>⏳ في الانتظار: <strong>{stats['pending']}</strong></p>
            <p>🔄 في Cooldown: <strong>{stats['cooldown']}</strong></p>
        </div>
    </body>
    </html>
    """, 200

@app.route('/health')
def health():
    """فحص صحة البوت"""
    stats = account_manager.get_statistics()
    return {
        "status": "running",
        "total_accounts": stats['total'],
        "available": stats['available'],
        "pending": stats['pending'],
        "cooldown": stats['cooldown']
    }, 200

@app.route('/stats')
def stats_json():
    """إحصائيات JSON"""
    return account_manager.get_statistics(), 200


def main():
    """الدالة الرئيسية - Web Service فقط"""
    logger.info("🌐 بدء تشغيل Web Service مع Webhook...")

    # تشغيل Flask مباشرة بدون threading
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🌐 Flask يعمل على المنفذ {port}")

    # محاولة تعيين webhook تلقائياً
    try:
        webhook_url = "https://zizo32332.pythonanywhere.com/webhook"
        telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        response = requests.post(telegram_url, data={'url': webhook_url}, timeout=15)
        logger.info(f"✅ Webhook auto-setup: {response.json()}")
    except Exception as e:
        logger.warning(f"⚠️ Webhook auto-setup failed: {e}")

    app.run(host='0.0.0.0', port=port, debug=False)

# ============ Webhook Routes (محسّنة) ============
# تم حذف النسخة البسيطة واستبدالها بالنسخة المحسّنة في آخر الملف
# ============ إضافة Flask للـ Webhook (مع دعم الأزرار الكامل) ============
from flask import Flask, request, jsonify
import requests

flask_app = Flask(__name__)

# متغير عام للـ Application
telegram_app = None

@flask_app.route('/')
def home():
    """الصفحة الرئيسية"""
    stats = account_manager.get_statistics()
    return f"""
    <html>
    <head><title>Telegram Bot Status</title><meta charset="UTF-8"></head>
    <body style="font-family: Arial; padding: 20px; background: #f5f5f5;">
        <h1>✅ البوت شغال!</h1>
        <div style="background: white; padding: 15px; border-radius: 8px; margin-top: 20px;">
            <h2>📊 الإحصائيات:</h2>
            <p>📈 إجمالي الحسابات: <strong>{stats['total']}</strong></p>
            <p>✅ المتاح الآن: <strong>{stats['available']}</strong></p>
            <p>⏳ في الانتظار: <strong>{stats['pending']}</strong></p>
            <p>🔄 في Cooldown: <strong>{stats['cooldown']}</strong></p>
        </div>
    </body>
    </html>
    """

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    """استقبال تحديثات Telegram ومعالجتها بنفس طريقة الكود القديم"""
    global telegram_app

    try:
        update_data = request.get_json()
        logger.info(f"📨 WEBHOOK: {json.dumps(update_data, ensure_ascii=False)[:200]}")

        if not telegram_app:
            logger.error("❌ Telegram app not initialized")
            return jsonify({'status': 'error', 'message': 'App not ready'}), 500

        # تحويل JSON لـ Update object
        from telegram import Update
        update = Update.de_json(update_data, telegram_app.bot)

        # تشغيل المعالجة
        async def process():
            """معالجة التحديث بنفس handlers القديمة"""
            try:
                # إنشاء context فارغ (هيتملى تلقائي)
                from telegram.ext import ContextTypes

                # استخدام الـ Application لمعالجة الـ Update
                await telegram_app.process_update(update)

            except Exception as e:
                logger.error(f"❌ Process error: {e}")
                logger.error(traceback.format_exc())

        # تشغيل async في thread منفصل
        import asyncio
        asyncio.run(process())

        return jsonify({'status': 'ok'}), 200

    except Exception as e:
        logger.error(f"❌ WEBHOOK ERROR: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)}), 500

@flask_app.route('/set_webhook')
def set_webhook():
    """تعيين webhook"""
    try:
        webhook_url = "https://zizo32332.pythonanywhere.com/webhook"
        telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"

        response = requests.post(telegram_url, data={'url': webhook_url}, timeout=15)
        result = response.json()

        logger.info(f"✅ Webhook setup: {result}")

        return f"""
        <html>
        <head><title>Webhook Setup</title><meta charset="UTF-8"></head>
        <body style="padding:20px; font-family:Arial;">
            <h2>🔗 تعيين Webhook</h2>
            <p><strong>URL:</strong> {webhook_url}</p>
            <p><strong>النتيجة:</strong></p>
            <pre>{json.dumps(result, indent=2, ensure_ascii=False)}</pre>
            <div style="margin-top:20px;">
                <a href="/">🏠 الصفحة الرئيسية</a>
            </div>
            <div style="margin-top:20px; padding:10px; background:#d4edda; border-radius:5px;">
                <p>✅ <strong>لو النتيجة "ok": true</strong> يبقى البوت شغال دلوقتي!</p>
                <p>💬 جرب تبعت رسالة للبوت على تليجرام</p>
            </div>
        </body>
        </html>
        """
    except Exception as e:
        logger.error(f"❌ Webhook setup error: {e}")
        return f"<h2>❌ خطأ:</h2><p>{str(e)}</p>", 500

@flask_app.route('/webhook_info')
def webhook_info():
    """عرض معلومات webhook"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
        response = requests.get(url, timeout=15)
        info = response.json()

        return f"""
        <html>
        <head><title>Webhook Info</title><meta charset="UTF-8"></head>
        <body style="padding:20px; font-family:Arial;">
            <h2>📊 معلومات Webhook</h2>
            <pre style="background:#f5f5f5; padding:15px; border-radius:5px;">{json.dumps(info, indent=2, ensure_ascii=False)}</pre>
            <div style="margin-top:20px;">
                <a href="/set_webhook">🔄 إعادة تعيين Webhook</a> |
                <a href="/">🏠 الصفحة الرئيسية</a>
            </div>
        </body>
        </html>
        """
    except Exception as e:
        return f"<h2>❌ خطأ:</h2><p>{str(e)}</p>", 500

def main_webhook():
    """تشغيل البوت بوضع Webhook"""
    global telegram_app

    logger.info("🌐 بدء تشغيل Webhook mode...")

    # إنشاء Application
    telegram_app = Application.builder().token(BOT_TOKEN).build()

    # إضافة handlers القديمة
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    telegram_app.add_handler(CallbackQueryHandler(button_callback))

    # تهيئة Application
    import asyncio
    asyncio.run(telegram_app.initialize())

    logger.info("✅ Telegram Application initialized")

    # محاولة تعيين webhook تلقائياً
    try:
        webhook_url = "https://zizo32332.pythonanywhere.com/webhook"
        telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        response = requests.post(telegram_url, data={'url': webhook_url}, timeout=15)
        logger.info(f"✅ Webhook auto-setup: {response.json()}")
    except Exception as e:
        logger.warning(f"⚠️ Webhook auto-setup failed: {e}")

    # تشغيل Flask
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🌐 Flask يعمل على المنفذ {port}")
    flask_app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == '__main__':
    # اختيار الوضع تلقائياً
    import sys

    if '--webhook' in sys.argv or os.environ.get('PYTHONANYWHERE_DOMAIN'):
        main_webhook()
    else:
        main()
