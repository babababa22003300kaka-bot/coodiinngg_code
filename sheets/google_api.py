#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📊 Google Sheets API Wrapper
التعامل مع Google Sheets
✅ ID دايماً في عمود Z (ثابت)
✅ يكتب في الأعمدة المحددة فقط بدون مسح باقي البيانات
"""

import logging
from typing import Dict, List, Tuple

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class GoogleSheetsAPI:
    """
    Wrapper للتعامل مع Google Sheets
    """

    # 🎯 تثبيت عمود الـ ID = Z (index 25)
    ID_COLUMN_INDEX = 25  # Z = العمود رقم 26 (0-based = 25)
    ID_COLUMN_LETTER = "Z"

    def __init__(self, credentials_file: str, spreadsheet_id: str, sheet_name: str):
        """
        تهيئة Google Sheets API

        Args:
            credentials_file: مسار ملف credentials.json
            spreadsheet_id: ID الشيت
            sheet_name: اسم الورقة
        """
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name

        # Authentication
        try:
            self.creds = Credentials.from_service_account_file(
                credentials_file,
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )

            self.service = build("sheets", "v4", credentials=self.creds)
            self.sheet = self.service.spreadsheets()

            logger.info(f"✅ Google Sheets API initialized: {sheet_name}")
            logger.info(f"🎯 ID column fixed at: {self.ID_COLUMN_LETTER}")

            # التأكد من وجود header في Z1
            self._ensure_id_header()

        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Sheets API: {e}")
            raise

    def _ensure_id_header(self):
        """
        التأكد من وجود header "ID" في العمود Z1
        """
        try:
            # قراءة Z1
            result = (
                self.sheet.values()
                .get(spreadsheetId=self.spreadsheet_id, range=f"{self.sheet_name}!Z1")
                .execute()
            )

            values = result.get("values", [])

            # لو Z1 فاضي أو مش "ID" → نكتب "ID"
            if not values or not values[0] or values[0][0] != "ID":
                logger.info("📝 Setting 'ID' header in column Z1")

                self.sheet.values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{self.sheet_name}!Z1",
                    valueInputOption="RAW",
                    body={"values": [["ID"]]},
                ).execute()

                logger.info("✅ Header 'ID' added to column Z1")
            else:
                logger.info("✅ Header 'ID' already exists in column Z1")

        except Exception as e:
            logger.warning(f"⚠️ Could not verify/set ID header: {e}")

    def append_emails(self, emails_data: List[Dict]) -> Tuple[bool, str]:
        """
        ✅ إضافة Email + ID للشيت (نفس سلوك الكود القديم)

        - يكتب Email في عمود A فقط
        - يكتب ID في عمود Z فقط
        - لا يمسح أو يعدل أي أعمدة أخرى نهائياً

        Args:
            emails_data: List of {"email": str, "id": str}

        Returns:
            (success: bool, message: str)
        """
        if not emails_data:
            return True, "No emails to add"

        try:
            logger.info(f"📤 Adding {len(emails_data)} rows (Email + ID only)")

            # 1️⃣ الحصول على آخر صف في العمود A (نفس الكود القديم)
            result_range = (
                self.sheet.values()
                .get(spreadsheetId=self.spreadsheet_id, range=f"{self.sheet_name}!A:A")
                .execute()
            )

            existing_values = result_range.get("values", [])
            next_row = len(existing_values) + 1

            logger.info(f"   📍 Last row: {len(existing_values)}, Next row: {next_row}")

            # 2️⃣ تجهيز البيانات لكل عمود على حدة
            email_values = []  # للـ Email (عمود A فقط)
            id_values = []  # للـ ID (عمود Z فقط)

            for item in emails_data:
                # Email في عمود A
                email = item.get("email", "")
                email_values.append([email])  # قيمة واحدة فقط

                # ID في عمود Z
                item_id = item.get("id", "")

                # ✅ تحقق: ID صالح
                if item_id and item_id not in ["N/A", "pending", "api", ""]:
                    id_values.append([str(item_id)])  # قيمة واحدة فقط
                else:
                    id_values.append([""])  # فراغ لو مافيش ID

            # 3️⃣ استخدام batchUpdate للكتابة في الأعمدة المحددة فقط
            last_row = next_row + len(emails_data) - 1

            # Range لكل عمود على حدة
            email_range = f"{self.sheet_name}!A{next_row}:A{last_row}"
            id_range = f"{self.sheet_name}!Z{next_row}:Z{last_row}"

            logger.info(f"   📧 Email range: {email_range}")
            logger.info(f"   🆔 ID range: {id_range}")

            # 4️⃣ استخدام batchUpdate - يكتب في الأعمدة المحددة فقط
            batch_data = [
                {"range": email_range, "values": email_values},
                {"range": id_range, "values": id_values},
            ]

            body = {"valueInputOption": "USER_ENTERED", "data": batch_data}

            logger.info(f"   🔧 Using batchUpdate (writes to specific columns only)")

            result = (
                self.sheet.values()
                .batchUpdate(spreadsheetId=self.spreadsheet_id, body=body)
                .execute()
            )

            # معلومات عن النتيجة
            total_updated_cells = result.get("totalUpdatedCells", 0)
            total_updated_rows = result.get("totalUpdatedRows", 0)
            responses = result.get("responses", [])

            logger.info(f"✅ Success!")
            logger.info(f"   ✅ Updated rows: {total_updated_rows}")
            logger.info(f"   ✅ Updated cells: {total_updated_cells}")
            logger.info(f"   ✅ Only Email (A) and ID (Z) columns were modified")
            logger.info(f"   ✅ Other columns in the row remain untouched")

            # عرض عينة من البيانات
            if email_values and id_values:
                sample_email = email_values[0][0]
                sample_id = id_values[0][0]
                logger.info(f"   📝 Sample: Email='{sample_email}', ID='{sample_id}'")

            return True, f"Added {len(emails_data)} rows"

        except HttpError as e:
            error_details = e.error_details if hasattr(e, "error_details") else str(e)

            # Rate Limit
            if e.resp.status == 429:
                logger.warning("⚠️ Rate limit hit, will retry later")
                return False, "Rate limit"

            # Quota exceeded
            if e.resp.status == 403:
                logger.warning("⚠️ Quota exceeded, will retry later")
                return False, "Quota exceeded"

            logger.error(f"❌ Google Sheets API error: {error_details}")
            return False, str(error_details)

        except Exception as e:
            logger.exception(f"❌ Unexpected error while adding emails: {e}")
            return False, str(e)
