#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pump_radar.py — نسخه نهایی اسکن میم‌کوین‌های سولانا (ضد خطای ۴۲۹)
"""
import os
import sys
import time
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (compatible; PumpRadar/6.5)"}
GT = "https://api.geckoterminal.com/api/v2"

def _get_safe(url):
    """درخواست امن با مکث برای جلوگیری از خطای ۴۲۹"""
    for attempt in range(3):
        try:
            time.sleep(2.0)  # مکث برای جلوگیری از بلاک شدن IP
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(5.0 * (attempt + 1))
                continue
            return None
        except Exception:
            time.sleep(2.0)
    return None

def notify_telegram(token, chat, text):
    if not token or not chat:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={**UA, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return True
    except Exception:
        return False

if __name__ == "__main__":
    tk = os.environ.get("TG_TOKEN")
    ch = os.environ.get("TG_CHAT")
    
    print("[+] شروع اسکن استخرهای ترند سولانا...")
    
    # دریافت استخرهای پرطرفدار سولانا از جی‌کوترمینال
    data = _get_safe(f"{GT}/networks/solana/trending_pools?page=1")
    
    msg_lines = [f"<b>🚀 رادار میم‌کوین‌های سولانا</b>\n<code>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</code>\n"]
    found = 0
    
    if data and "data" in data:
        for it in data["data"][:5]: # ۵ مورد برتر
            attr = it.get("attributes", {})
            name = attr.get("name", "Unknown")
            price_change = attr.get("price_change_percentage", {}).get("m5", 0)
            reserve = float(attr.get("reserve_in_usd") or 0)
            
            # استخراج آدرس توکن از رابطه
            rel = it.get("relationships", {})
            base_token_id = ((rel.get("base_token") or {}).get("data") or {}).get("id", "")
            if base_token_id.startswith("solana_"):
                base_token_id = base_token_id[7:]
                
            msg_lines.append(f"🔹 <b>{name}</b>")
            msg_lines.append(f"💰 نقدینگی: ${reserve:,.0f} | تغییر ۵ دقیقه: {float(price_change or 0):+.2f}%")
            if base_token_id:
                msg_lines.append(f"<code>{base_token_id}</code>")
            msg_lines.append("----------------------------")
            found += 1
            
    if found > 0:
        msg = "\n".join(msg_lines)
        if tk and ch:
            notify_telegram(tk, ch, msg)
            print("[✓] سیگنال میم‌کوین‌ها ارسال شد.")
        else:
            print(msg)
    else:
        print("[-] هیچ استخری یافت نشد یا محدودیت API اعمال شد.")
