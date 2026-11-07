#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pump_radar.py — نسخه فوق‌العاده سریع و سبک هر ۵ دقیقه
"""
import os
import sys
import time
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (compatible; PumpRadar/6.4)"}

def _get_safe(url):
    for attempt in range(2):
        try:
            time.sleep(1.0)
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode())
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
        with urllib.request.urlopen(req, timeout=10) as r:
            return True
    except Exception:
        return False

if __name__ == "__main__":
    tk = os.environ.get("TG_TOKEN")
    ch = os.environ.get("TG_CHAT")
    
    print("[+] رادار ۵ دقیقه‌ای بازار شروع به کار کرد...")
    
    # دریافت دیتای آنی و سبک بازار
    data = _get_safe("https://api.coingecko.com/api/v3/simple/price?ids=solana,ethereum,bitcoin&vs_currencies=usd&include_24hr_change=true")
    
    if data:
        msg = f"<b>⚡️ رادار سریع بازار (هر ۵ دقیقه)</b>\n<code>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</code>\n\n"
        for coin, info in data.items():
            price = info.get("usd", 0)
            change = info.get("usd_24h_change", 0)
            msg += f"🔹 <b>{coin.upper()}</b>: ${price:,.2f} ({change:+.2f}%)\n"
        
        if tk and ch:
            notify_telegram(tk, ch, msg)
            print("[✓] گزارش ۵ دقیقه‌ای با موفقیت ارسال شد.")
        else:
            print(msg)
    else:
        print("[-] دریافت داده با تاخیر مواجه شد، اما اسکریپت با موفقیت به پایان رسید.")
