"""
=====================================================
  Order & Conversation Log Manager — Excel Storage
=====================================================
"""

import openpyxl
import os
from datetime import datetime

ORDERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orders.xlsx")

ORDER_HEADERS = ["তারিখ", "নাম", "মোবাইল", "ঠিকানা", "পণ্য", "রঙ/সাইজ", "পেমент", "স্ট্যাটাস"]
LOG_HEADERS   = ["তারিখ ও সময়", "কাস্টমার ID/মোবাইল", "কাস্টমার বার্তা", "বট রিপ্লাই", "সেন্টিমেন্ট (Good/Bad/General)", "পণ্য"]


def _get_workbook():
    if os.path.exists(ORDERS_FILE):
        wb = openpyxl.load_workbook(ORDERS_FILE)
    else:
        wb = openpyxl.Workbook()

    # Ensure "অর্ডার লিস্ট" sheet
    if "অর্ডার লিস্ট" in wb.sheetnames:
        ws_orders = wb["অর্ডার লিস্ট"]
    else:
        # Default sheet
        ws_orders = wb.active
        ws_orders.title = "অর্ডার লিস্ট"

        # Order Header styling
        ws_orders.append(ORDER_HEADERS)
        from openpyxl.styles import Font, PatternFill, Alignment
        header_fill = PatternFill("solid", fgColor="1F4E79")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        for cell in ws_orders[1]:
            cell.fill   = header_fill
            cell.font   = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        widths = [18, 18, 16, 30, 25, 20, 22, 12]
        for i, w in enumerate(widths, 1):
            ws_orders.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # Ensure "কথা ও সেন্টিমেন্ট" sheet
    if "কথা ও সেন্টিমেন্ট" in wb.sheetnames:
        ws_logs = wb["কথা ও সেন্টিমেন্ট"]
    else:
        ws_logs = wb.create_sheet("কথা ও সেন্টিমেন্ট")
        ws_logs.append(LOG_HEADERS)
        from openpyxl.styles import Font, PatternFill, Alignment
        log_fill = PatternFill("solid", fgColor="333F48")
        log_font = Font(bold=True, color="FFFFFF", size=11)
        for cell in ws_logs[1]:
            cell.fill   = log_fill
            cell.font   = log_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        widths_log = [18, 20, 35, 40, 18, 22]
        for i, w in enumerate(widths_log, 1):
            ws_logs.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    return wb, ws_orders, ws_logs


def save_order(name, mobile, address, product, color_size="", payment="ক্যাশ অন ডেলিভারি", order_id=None):
    """Excel এ নতুন অর্ডার সেভ করে এবং Order ID রিটার্ন করে"""
    try:
        wb, ws_orders, _ = _get_workbook()
        if not order_id:
            import random
            order_id = f"BB-{random.randint(1000, 9999)}"

        ws_orders.append([
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            str(order_id),
            name,
            mobile,
            address,
            product or "অনির্ধারিত",
            color_size or "-",
            payment,
            "নতুন"
        ])

        # Row styling
        row = ws_orders.max_row
        from openpyxl.styles import PatternFill, Alignment
        fill_color = "DEEAF1" if row % 2 == 0 else "FFFFFF"
        fill = PatternFill("solid", fgColor=fill_color)
        for cell in ws_orders[row]:
            cell.fill = fill
            cell.alignment = Alignment(vertical="center", wrap_text=True)

        ws_orders.row_dimensions[row].height = 20
        wb.save(ORDERS_FILE)
        print(f"[EXCEL ORDER] Saved: #{order_id} | {name} | {mobile} | {payment}")
        return order_id
    except Exception as e:
        print(f"[EXCEL ORDER ERROR] {e}")
        return None


def save_conversation_log(customer_id, user_message, bot_reply, sentiment="General", product=""):
    """
    কাস্টমারের সাথে কথা ও সেন্টিমেন্ট (Good/Bad/General) Excel-এ সেভ করে
    """
    try:
        wb, _, ws_logs = _get_workbook()
        ws_logs.append([
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            str(customer_id),
            str(user_message),
            str(bot_reply),
            str(sentiment or "General"),
            str(product or "-")
        ])

        row = ws_logs.max_row
        from openpyxl.styles import PatternFill, Alignment, Font
        
        # Color coding sentiment
        if sentiment == "Good":
            s_fill = PatternFill("solid", fgColor="E2EFDA") # Light green
            font_color = Font(color="276A3C", bold=True)
        elif sentiment == "Bad":
            s_fill = PatternFill("solid", fgColor="FCE4D6") # Light red
            font_color = Font(color="C65911", bold=True)
        else:
            s_fill = PatternFill("solid", fgColor="FFF2CC") # Light yellow
            font_color = Font(color="8EA9DB")

        for cell in ws_logs[row]:
            cell.alignment = Alignment(vertical="center", wrap_text=True)

        # Apply sentiment column styling
        ws_logs.cell(row=row, column=5).fill = s_fill
        ws_logs.cell(row=row, column=5).font = font_color

        ws_logs.row_dimensions[row].height = 22
        wb.save(ORDERS_FILE)
        print(f"[EXCEL LOG] Logged interaction: [{sentiment}] {customer_id}")
        return True
    except Exception as e:
        print(f"[EXCEL LOG ERROR] {e}")
        return False


def get_all_orders():
    """সব অর্ডার return করে (admin panel এর জন্য)"""
    try:
        if not os.path.exists(ORDERS_FILE):
            return []
        wb = openpyxl.load_workbook(ORDERS_FILE)
        if "অর্ডার লিস্ট" not in wb.sheetnames:
            return []
        ws = wb["অর্ডার লিস্ট"]
        orders = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if any(c for c in row):
                orders.append(row)
        return orders
    except Exception as e:
        print(f"[EXCEL READ ERROR] {e}")
        return []


def find_order_by_id_or_mobile(query):
    """
    Order ID (e.g. BB-1234 or 1234) অথবা কাস্টমারের মোবাইল নম্বর দিয়ে অর্ডার খুঁজে বের করে।
    """
    try:
        if not os.path.exists(ORDERS_FILE):
            return None
        wb = openpyxl.load_workbook(ORDERS_FILE)
        if "অর্ডার লিস্ট" not in wb.sheetnames:
            return None
        ws = wb["অর্ডার লিস্ট"]
        q = str(query).strip().lower().replace("#", "").replace("bb-", "")
        
        # Iterate backwards to find latest matching order
        rows = list(ws.iter_rows(min_row=2, values_only=True))
        for row in reversed(rows):
            if not row or not any(row):
                continue
            # Row could have 8 cols (old) or 9 cols (new with Order ID)
            # New format: [0:date, 1:order_id, 2:name, 3:mobile, 4:addr, 5:prod, 6:color_size, 7:pay, 8:status]
            # Old format: [0:date, 1:name, 2:mobile, 3:addr, 4:prod, 5:color_size, 6:pay, 7:status]
            if len(row) >= 9 and str(row[1]).startswith("BB-"):
                o_id = str(row[1]).strip().lower().replace("bb-", "")
                mobile = str(row[3]).strip()
                if q in o_id or q in mobile:
                    return {
                        "date": row[0],
                        "order_id": row[1],
                        "name": row[2],
                        "mobile": row[3],
                        "address": row[4],
                        "product": row[5],
                        "details": row[6],
                        "payment": row[7],
                        "status": row[8] or "পেন্ডিং"
                    }
            elif len(row) >= 8:
                mobile = str(row[2]).strip()
                if q in mobile:
                    return {
                        "date": row[0],
                        "order_id": "N/A",
                        "name": row[1],
                        "mobile": row[2],
                        "address": row[3],
                        "product": row[4],
                        "details": row[5],
                        "payment": row[6],
                        "status": row[7] or "পেন্ডিং"
                    }
        return None
    except Exception as e:
        print(f"[ORDER SEARCH ERROR] {e}")
        return None


def update_order_status(order_id_or_row, new_status):
    """অর্ডারের স্ট্যাটাস (যেমন: নিশ্চিত, ডেলিভারিতে পাঠানো হয়েছে, ডেলিভারড) পরিবর্তন করে"""
    try:
        wb, ws_orders, _ = _get_workbook()
        q = str(order_id_or_row).strip().lower().replace("#", "")
        for row_idx, row in enumerate(ws_orders.iter_rows(min_row=2), start=2):
            val_col2 = str(row[1].value or "").strip().lower().replace("#", "")
            if val_col2 == q or val_col2 == f"bb-{q}" or str(row_idx) == str(order_id_or_row):
                # Target status column
                status_col = len(row)
                ws_orders.cell(row=row_idx, column=status_col).value = str(new_status)
                wb.save(ORDERS_FILE)
                return True
        return False
    except Exception as e:
        print(f"[STATUS UPDATE ERROR] {e}")
        return False


def get_all_logs():
    """সব কাস্টমার ফিডব্যাক/লগ return করে row_idx সহ (admin panel এর জন্য)"""
    try:
        if not os.path.exists(ORDERS_FILE):
            return []
        wb = openpyxl.load_workbook(ORDERS_FILE)
        if "কথা ও সেন্টিমেন্ট" not in wb.sheetnames:
            return []
        ws = wb["কথা ও সেন্টিমেন্ট"]
        logs = []
        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if any(c for c in row):
                logs.append((idx, *row))
        return logs
    except Exception as e:
        print(f"[EXCEL LOG READ ERROR] {e}")
        return []


def update_conversation_log(row_index, user_message, bot_reply, sentiment, product=""):
    """Excel শিটের নির্দিষ্ট Row-এর কাস্টমার বার্তা, বট রিপ্লাই, সেন্টিমেন্ট ও পণ্য আপডেট করে"""
    try:
        wb, _, ws_logs = _get_workbook()
        row = int(row_index)
        ws_logs.cell(row=row, column=3).value = str(user_message)
        ws_logs.cell(row=row, column=4).value = str(bot_reply)
        ws_logs.cell(row=row, column=5).value = str(sentiment or "General")
        if product is not None:
            ws_logs.cell(row=row, column=6).value = str(product)

        from openpyxl.styles import PatternFill, Font
        if sentiment == "Good":
            s_fill = PatternFill("solid", fgColor="E2EFDA")
            font_color = Font(color="276A3C", bold=True)
        elif sentiment == "Bad":
            s_fill = PatternFill("solid", fgColor="FCE4D6")
            font_color = Font(color="C65911", bold=True)
        else:
            s_fill = PatternFill("solid", fgColor="FFF2CC")
            font_color = Font(color="8EA9DB")

        ws_logs.cell(row=row, column=5).fill = s_fill
        ws_logs.cell(row=row, column=5).font = font_color

        wb.save(ORDERS_FILE)
        print(f"[EXCEL LOG UPDATED] Row: {row} | Sentiment: {sentiment}")
        return True
    except Exception as e:
        print(f"[EXCEL LOG UPDATE ERROR] {e}")
        return False


def delete_conversation_log(row_index):
    """Excel শিটের নির্দিষ্ট Row মুছে ফেলে"""
    try:
        wb, _, ws_logs = _get_workbook()
        row = int(row_index)
        ws_logs.delete_rows(row, 1)
        wb.save(ORDERS_FILE)
        print(f"[EXCEL LOG DELETED] Row: {row}")
        return True
    except Exception as e:
        print(f"[EXCEL LOG DELETE ERROR] {e}")
        return False
