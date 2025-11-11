#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌐 API Manager
مدير API مع Smart Cache وBurst Mode
✅ نسخة كاملة مع كل الإحصائيات
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

import aiohttp

from config import (
    BURST_MODE_DURATION,
    CACHE_TTL_MAX,
    CACHE_TTL_MIN,
    CACHE_TTL_NORMAL,
    CSRF_TOKEN_TTL,
    FINAL_STATUSES,
)
from stats import stats  # ✅ استيراد من ملف منفصل

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 🧠 Smart Cache Manager (النسخة الهجينة النهائية - الأفضل)
# ═══════════════════════════════════════════════════════════════


class SmartCacheManager:
    """
    مدير ذاكرة مؤقتة ذكي مع:
    - Smart TTL متكيف
    - ✅ Burst Mode جماعي فائق الكفاءة
    - ✅ Timeout Safety (حماية من التعليق)
    - Fallback mechanism
    """

    def __init__(self):
        self.cache: Optional[List[Dict]] = None
        self.cache_timestamp: Optional[datetime] = None
        self.cache_ttl: float = CACHE_TTL_NORMAL

        # ✅ نظام Burst Mode المحسّن
        self.burst_targets: Set[str] = set()  # قائمة IDs الحسابات النشطة
        self.burst_window_start: Optional[datetime] = None  # بداية النافذة الزمنية

        # Activity tracking for Smart TTL
        self.last_changes_count: int = 0
        self.consecutive_quiet_cycles: int = 0

        # Fallback
        self.last_successful_cache: Optional[List[Dict]] = None
        self.last_successful_timestamp: Optional[datetime] = None

    def is_cache_valid(self) -> bool:
        """✅ التحقق الذكي: طالما فيه أهداف، الكاش غير صالح"""
        if self.cache is None or self.cache_timestamp is None:
            return False

        # ✅ لو فيه حسابات في قائمة الانتظار، نحدّث باستمرار
        if self.burst_targets:
            return False

        age = (datetime.now() - self.cache_timestamp).total_seconds()
        return age < self.cache_ttl

    def activate_burst_mode(self, account_id: str):
        """✅ تفعيل Burst لحساب معين (مع تتبع البداية)"""
        global stats

        # لو دي أول إضافة، سجّل البداية
        if not self.burst_targets:
            self.burst_window_start = datetime.now()
            stats.burst_activations += 1
            logger.info(f"🚀 BURST MODE ACTIVATED (first target: {account_id})")

        self.burst_targets.add(account_id)
        logger.info(
            f"🎯 Added {account_id} to burst targets. Total: {len(self.burst_targets)}"
        )

    def deactivate_burst_target(self, account_id: str):
        """✅ إزالة حساب من قائمة الـ Burst (إزالة فردية)"""
        if account_id in self.burst_targets:
            self.burst_targets.discard(account_id)
            logger.info(
                f"✅ Deactivated burst for {account_id}. Remaining: {len(self.burst_targets)}"
            )

            # لو القائمة فضت، امسح البداية
            if not self.burst_targets:
                self.burst_window_start = None
                logger.info("⚡ BURST MODE DEACTIVATED (all targets processed)")

    def check_burst_mode(self):
        """✅ فحص الـ timeout وإلغاء الـ Burst لو تعدى الوقت المسموح"""
        if not self.burst_targets or not self.burst_window_start:
            return

        elapsed = (datetime.now() - self.burst_window_start).total_seconds()

        if elapsed >= BURST_MODE_DURATION:
            # ⚠️ Timeout - امسح كل القائمة
            logger.warning(
                f"⏱️ BURST MODE TIMEOUT after {elapsed:.1f}s - clearing {len(self.burst_targets)} targets"
            )
            self.burst_targets.clear()
            self.burst_window_start = None

    def adjust_ttl(self, changes_detected: int):
        """
        تعديل ذكي لـ TTL بناءً على النشاط

        - كثير تغييرات → TTL قصير (استجابة أسرع)
        - قليل تغييرات → TTL طويل (توفير موارد)
        """
        global stats

        old_ttl = self.cache_ttl

        if changes_detected >= 5:
            # نشاط عالي جداً
            self.cache_ttl = CACHE_TTL_MIN
            self.consecutive_quiet_cycles = 0

        elif changes_detected >= 2:
            # نشاط متوسط
            self.cache_ttl = CACHE_TTL_NORMAL
            self.consecutive_quiet_cycles = 0

        else:
            # هدوء
            self.consecutive_quiet_cycles += 1

            if self.consecutive_quiet_cycles >= 3:
                # 3 دورات هادئة متتالية → نطول الفترة
                self.cache_ttl = CACHE_TTL_MAX

        if old_ttl != self.cache_ttl:
            stats.adaptive_adjustments += 1
            logger.info(
                f"🎯 TTL adjusted: {old_ttl:.0f}s → {self.cache_ttl:.0f}s (changes={changes_detected})"
            )

    def update_cache(self, new_data: List[Dict], success: bool = True):
        """تحديث الـ cache مع fallback mechanism"""
        if success:
            self.cache = new_data
            self.cache_timestamp = datetime.now()
            self.last_successful_cache = new_data
            self.last_successful_timestamp = datetime.now()
        else:
            # فشل التحديث - نستخدم آخر نسخة ناجحة
            logger.warning("⚠️ Cache update failed, using last successful cache")
            if self.last_successful_cache:
                self.cache = self.last_successful_cache
                self.cache_timestamp = self.last_successful_timestamp

    def get_cache(self) -> Optional[List[Dict]]:
        """الحصول على الـ cache"""
        return self.cache

    def get_account_by_id(self, account_id: str) -> Optional[Dict]:
        """
        🎯 البحث بالـ ID (أكثر أماناً من البحث بالإيميل)
        """
        if not self.cache:
            return None

        for account in self.cache:
            if str(account.get("idAccount", "")) == str(account_id):
                return account

        return None

    def get_account_by_email(self, email: str) -> Optional[Dict]:
        """البحث بالإيميل (للبحث الأولي)"""
        if not self.cache:
            return None

        email = email.lower().strip()
        for account in self.cache:
            if account.get("Sender", "").lower() == email:
                return account

        return None


# Global smart cache
smart_cache = SmartCacheManager()


# ═══════════════════════════════════════════════════════════════
# 🔐 Optimized API Manager
# ═══════════════════════════════════════════════════════════════


class OptimizedAPIManager:
    """API manager with smart cache integration"""

    def __init__(self, config: Dict):
        self.base_url = config["website"]["urls"]["base"]
        self.cookies = config["website"]["cookies"]
        self.defaults = config["website"]["defaults"]

        # CSRF Token cache
        self.csrf_token = None
        self.csrf_expires_at = None

        # aiohttp session
        self.session = None

    async def initialize(self):
        """Initialize API manager"""
        await self._ensure_session()
        logger.info("🚀 API Manager initialized (Hybrid Mode)")

    async def _ensure_session(self):
        """Ensure aiohttp session exists"""
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            timeout = aiohttp.ClientTimeout(total=30)

            self.session = aiohttp.ClientSession(
                connector=connector, timeout=timeout, cookies=self.cookies
            )

    async def get_csrf_token(self, force_refresh: bool = False) -> Optional[str]:
        """Get CSRF token with caching"""
        global stats

        if not force_refresh and self.csrf_token and self.csrf_expires_at:
            if datetime.now() < self.csrf_expires_at:
                stats.cache_hits += 1  # ✅ رجعنا التتبع
                return self.csrf_token

        logger.info("🔄 Fetching CSRF token...")
        stats.csrf_refreshes += 1  # ✅ رجعنا التتبع
        stats.total_requests += 1  # ✅ رجعنا التتبع

        await self._ensure_session()

        try:
            async with self.session.get(f"{self.base_url}/senderPage") as response:
                if response.status == 200:
                    html = await response.text()
                    match = re.search(
                        r'<meta name="csrf-token" content="([^"]+)"', html
                    )
                    if match:
                        self.csrf_token = match.group(1)
                        self.csrf_expires_at = datetime.now() + timedelta(
                            seconds=CSRF_TOKEN_TTL
                        )
                        logger.info(f"✅ CSRF cached ({CSRF_TOKEN_TTL}s)")
                        return self.csrf_token
        except Exception as e:
            logger.error(f"❌ CSRF fetch error: {e}")
            stats.errors += 1  # ✅ رجعنا التتبع

        return None

    async def fetch_all_accounts_batch(self, force_refresh: bool = False) -> List[Dict]:
        """
        🎯 جلب مركزي للحسابات مع Smart Cache
        """
        global stats

        # تحقق من صلاحية الـ cache
        if not force_refresh and smart_cache.is_cache_valid():
            stats.cache_hits += 1  # ✅ رجعنا التتبع
            cached = smart_cache.get_cache()
            if cached:
                return cached

        logger.info("🔄 Batch fetch...")
        stats.batch_fetches += 1  # ✅ رجعنا التتبع
        stats.total_requests += 1  # ✅ رجعنا التتبع

        csrf = await self.get_csrf_token()
        if not csrf:
            # استخدام Fallback
            smart_cache.update_cache([], success=False)
            return smart_cache.get_cache() or []

        await self._ensure_session()

        try:
            payload = {"date": "0", "bigUpdate": "0", "csrf_token": csrf}

            async with self.session.post(
                f"{self.base_url}/dataFunctions/updateSenderPage", data=payload
            ) as response:

                if response.status == 200:
                    data = await response.json()

                    if "data" in data:
                        accounts = data["data"]

                        INDEX_MAP = {
                            "idAccount": 0,
                            "image": 1,
                            "Sender": 2,
                            "Start": 3,
                            "Last Update": 4,
                            "Taken": 5,
                            "Status": 6,
                            "Available": 7,
                            "password": 8,
                            "backupCodes": 9,
                            "Group": 10,
                            "groupNameId": 11,
                            "Take": 12,
                            "Keep": 13,
                        }

                        parsed = []
                        for account in accounts:
                            if len(account) > INDEX_MAP["Sender"]:
                                acc = {}
                                for key, idx in INDEX_MAP.items():
                                    acc[key] = (
                                        str(account[idx])
                                        if idx < len(account) and account[idx]
                                        else ""
                                    )
                                parsed.append(acc)

                        # تحديث الـ cache
                        smart_cache.update_cache(parsed, success=True)

                        logger.info(
                            f"✅ Fetched {len(parsed)} accounts (TTL={smart_cache.cache_ttl:.0f}s)"
                        )
                        return parsed

                elif response.status in [403, 419]:
                    self.csrf_token = None
                    return await self.fetch_all_accounts_batch(force_refresh=True)

        except Exception as e:
            logger.error(f"❌ Batch fetch error: {e}")
            stats.errors += 1  # ✅ رجعنا التتبع
            # استخدام Fallback
            smart_cache.update_cache([], success=False)

        return smart_cache.get_cache() or []

    async def search_sender_by_id(self, account_id: str) -> Optional[Dict]:
        """
        🎯 البحث بالـ ID (أكثر أماناً)
        """
        # تحديث الـ cache إذا لزم الأمر
        if not smart_cache.is_cache_valid():
            await self.fetch_all_accounts_batch()

        return smart_cache.get_account_by_id(account_id)

    async def search_sender_by_email(self, email: str) -> Optional[Dict]:
        """البحث بالإيميل"""
        # تحديث الـ cache إذا لزم الأمر
        if not smart_cache.is_cache_valid():
            await self.fetch_all_accounts_batch()

        return smart_cache.get_account_by_email(email)

    async def add_sender(
        self,
        email: str,
        password: str,
        backup_codes: str = "",
        amount_take: str = "",
        amount_keep: str = "",
    ) -> Tuple[bool, str]:
        """Add sender"""
        global stats

        csrf = await self.get_csrf_token()
        if not csrf:
            return False, "No CSRF"

        stats.total_requests += 1  # ✅ رجعنا التتبع
        await self._ensure_session()

        payload = {
            "email": email,
            "password": password,
            "backupCodes": backup_codes,
            "groupName": self.defaults["group_name"],
            "accountLock": self.defaults["account_lock"],
            "amountToTake": amount_take or self.defaults.get("amount_take", ""),
            "amountToKeep": amount_keep or self.defaults.get("amount_keep", ""),
            "priority": self.defaults.get("priority", ""),
            "forceProxy": self.defaults.get("force_proxy", ""),
            "userPrice": self.defaults.get("user_price", ""),
            "csrf_token": csrf,
        }

        try:
            async with self.session.post(
                f"{self.base_url}/dataFunctions/addAccount", json=payload
            ) as response:

                if response.status == 200:
                    try:
                        data = await response.json()
                        if "success" in data:
                            # إلغاء الـ cache لإجبار تحديث
                            smart_cache.cache = None
                            smart_cache.cache_timestamp = None
                            return True, data.get("success", "Success")
                        elif "error" in data:
                            error = data.get("error", "")
                            if "already" in error.lower():
                                return True, "Exists"
                            return False, error
                    except:
                        text = await response.text()
                        if "success" in text.lower():
                            smart_cache.cache = None
                            smart_cache.cache_timestamp = None
                            return True, "Success"
                        return False, text[:100]

                elif response.status in [403, 419]:
                    self.csrf_token = None
                    return False, "CSRF expired"

                return False, f"Status {response.status}"

        except Exception as e:
            stats.errors += 1  # ✅ رجعنا التتبع
            return False, str(e)

    async def close(self):
        """Cleanup"""
        if self.session and not self.session.closed:
            await self.session.close()
