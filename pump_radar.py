#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pump_radar.py — رادار میم‌کوین سولانا با فیلتر هوشمند جهش حجم (۳ برابری)
"""
import os
import sys
import time
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (compatible; PumpRadar/7.0)"}
GT = "https://api.geckoterminal.com/api/v2"

# تنظیمات آستانه نقدینگی و جهش حجم
MIN_LIQ = 10_000          # حداقل نقدینگی به دلار
VOLUME_MULTIPLIER = 3.0   # حجم ۵ دقیقه حداقل ۳ برابر میانگین بازه

def _get_safe(url):
    """درخواست امن با مکث برای جلوگیری از خطای ۴۲۹"""
    for attempt in range(3):
        try:
            time.sleep(2.0)
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
    
    print("[+] اسکن بازار با فیلتر جهش حجم ۳ برابری...")
    data = _get_safe(f"{GT}/networks/solana/trending_pools?page=1")
    
    msg_lines = [f"<b>🔥 رادار شکارچی پول هوشمند (سولانا)</b>\n<code>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</code>\n"]
    sent_count = 0
    
    if data and "data" in data:
        for it in data["data"]:
            attr = it.get("attributes", {})
            name = attr.get("name", "Unknown")
            
            # استخراج حجم‌ها
            vol = attr.get("volume_usd", {}) or {}
            v5 = float(vol.get("m5") or 0)
            v24 = float(vol.get("h24") or 0)
            reserve = float(attr.get("reserve_in_usd") or 0)
            price_change = float(attr.get("price_change_percentage", {}).get("m5") or 0)
            
            # محاسبه میانگین حجم ۵ دقیقه‌ای در ۲۴ ساعت گذشته (۲۸۸ بازه ۵ دقیقه‌ای در روز)
            avg_5m_baseline = max(v24 / 288.0, 1.0)
            volume_ratio = v5 / avg_5m_baseline
            
            # ── اعمال فیلترهای سخت‌گیرانه ──────────────────
            if reserve < MIN_LIQ:
                continue
            
            # شرط اصلی: حجم ۵ دقیقه حداقل ۳ برابر میانگین باشد
            if volume_ratio < VOLUME_MULTIPLIER:
                continue
            
            # استخراج آدرس کانترکت
            rel = it.get("relationships", {})
            base_token_id = ((rel.get("base_token") or {}).get("data") or {}).get("id", "")
            if base_token_id.startswith("solana_"):
                base_token_id = base_token_id[7:]
                
            msg_lines.append(f"🔹 <b>{name}</b>")
            msg_lines.append(f"⚡️ جهش حجم: <b>×{volume_ratio:.1f} برابر</b> (۵دقیقه: ${v5:,.0f})")
            msg_lines.append(f"💰 نقدینگی: ${reserve:,.0f} | تغییر ۵دقیقه: {price_change:+.2f}%")
            if base_token_id:
                msg_lines.append(f"<code>{base_token_id}</code>")
            msg_lines.append("----------------------------")
            sent_count += 1
            
            if sent_count >= 5: # حداکثر ۵ مورد برتر در هر ارسال
                break
                
    if sent_count > 0:
        msg = "\n".join(msg_lines)
        if tk and ch:
            notify_telegram(tk, ch, msg)
            print("[✓] سیگنال‌های دارای جهش حجم ارسال شدند.")
        else:
            print(msg)
    else:
        print("[-] هیچ توکنی با شرط جهش ۳ برابری حجم در این بازه یافت نشد.")
