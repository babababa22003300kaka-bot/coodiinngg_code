#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📝 Weekly Logger
نظام لوج أسبوعي (السبت → الجمعة)
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class WeeklyLogger:
    """
    Logger يكتب في ملف أسبوعي جديد كل أسبوع
    الأسبوع: السبت → الجمعة
    """

    def __init__(self, log_dir: str = "logs"):
        """
        تهيئة Weekly Logger

        Args:
            log_dir: مجلد اللوج
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.current_file = None
        self.current_week_start = None

    def _get_week_start(self) -> datetime:
        """
        الحصول على بداية الأسبوع (السبت)

        Returns:
            datetime لبداية الأسبوع
        """
        today = datetime.now().date()

        # السبت = 5 في Python (Monday=0, Sunday=6)
        days_since_saturday = (today.weekday() - 5) % 7
        week_start = today - timedelta(days=days_since_saturday)

        return datetime.combine(week_start, datetime.min.time())

    def _get_log_filename(self) -> Path:
        """
        الحصول على اسم ملف اللوج للأسبوع الحالي

        Returns:
            Path لملف اللوج
        """
        week_start = self._get_week_start()
        week_end = week_start + timedelta(days=6)

        filename = f"bot_log_{week_start.strftime('%Y-%m-%d')}_to_{week_end.strftime('%Y-%m-%d')}.txt"
        return self.log_dir / filename

    def write(self, message: str):
        """
        كتابة رسالة في اللوج

        Args:
            message: الرسالة المراد كتابتها
        """
        try:
            # التحقق من تغيير الأسبوع
            week_start = self._get_week_start()

            if self.current_week_start != week_start:
                self.current_week_start = week_start
                self.current_file = self._get_log_filename()
                logger.info(f"📝 New log file: {self.current_file}")

            # كتابة الرسالة
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_line = f"[{timestamp}] {message}\n"

            with open(self.current_file, "a", encoding="utf-8") as f:
                f.write(log_line)

        except Exception as e:
            logger.error(f"❌ Error writing to log: {e}")
