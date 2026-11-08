#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pump_radar.py — رادار جامع میم‌کوین سولانا (پیش‌‌پامپ، پامپ و دامپ)
"""
import os
import sys
import time
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (compatible; PumpRadar/8.0)"}
GT = "https://api.geckoterminal.com/api/v2"

MIN_LIQ = 10_000          # حداقل نقدینگی به دلار
VOLUME_MULTIPLIER = 3.0   # حداقل جهش حجم ۳ برابری

def _get_safe(url):
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
    
    print("[+] شروع اسکن پیشرفته بازار (پیش‌‌پامپ، پامپ، دامپ)...")
    data = _get_safe(f"{GT}/networks/solana/trending_pools?page=1")
    
    msg_lines = [f"<b>radar هوشمند میم‌کوین (سولانا)</b>\n<code>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</code>\n"]
    sent_count = 0
    
    if data and "data" in data:
        for it in data["data"]:
            attr = it.get("attributes", {})
            name = attr.get("name", "Unknown")
            
            current_price = float(attr.get("price_in_usd") or attr.get("base_token_price_usd") or 0)
            vol = attr.get("volume_usd", {}) or {}
            v5 = float(vol.get("m5") or 0)
            v24 = float(vol.get("h24") or 0)
            reserve = float(attr.get("reserve_in_usd") or 0)
            price_change = float(attr.get("price_change_percentage", {}).get("m5") or 0)
            
            avg_5m_baseline = max(v24 / 288.0, 1.0)
            volume_ratio = v5 / avg_5m_baseline
            
            if reserve < MIN_LIQ:
                continue
                
            # تشخیص وضعیت (پیش‌پامپ، پامپ یا دامپ)
            signal_type = None
            
            if price_change <= -5.0:
                signal_type = "DUMP" # ریزش و فشار فروش سنگین
            elif volume_ratio >= VOLUME_MULTIPLIER:
                if -2.0 <= price_change <= 4.0:
                    signal_type = "PRE_PUMP" # پول هوشمند وارد شده، قیمت هنوز آرامه
                elif price_change > 4.0:
                    signal_type = "ACTIVE_PUMP" # پامپ فعال و انفجار قیمت
            
            if not signal_type:
                continue
                
            # استخراج آدرس کانترکت
            rel = it.get("relationships", {})
            base_token_id = ((rel.get("base_token") or {}).get("data") or {}).get("id", "")
            if base_token_id.startswith("solana_"):
                base_token_id = base_token_id[7:]
                
            # نمایش بر اساس نوع سیگنال
            if signal_type == "PRE_PUMP":
                msg_lines.append(f"🟢 <b>[پیش‌پامپ / پول هوشمند] {name}</b>")
                msg_lines.append(f"⚡️ جهش حجم: <b>×{volume_ratio:.1f} برابر</b> | تغییر ۵دقیقه: {price_change:+.2f}%")
            elif signal_type == "ACTIVE_PUMP":
                msg_lines.append(f"🚀 <b>[در حال پامپ ⚡️] {name}</b>")
                msg_lines.append(f"⚡️ جهش حجم: <b>×{volume_ratio:.1f} برابر</b> | رشد قیمت: <b>{price_change:+.2f}%</b>")
            elif signal_type == "DUMP":
                msg_lines.append(f"🔴 <b>[هشدار دامپ / ریزش ⚠️] {name}</b>")
                msg_lines.append(f"📉 افت قیمت ۵دقیقه: <b>{price_change:+.2f}%</b>")
                
            msg_lines.append(f"💰 نقدینگی: ${reserve:,.0f}")
            
            # پیشنهاد خرید و فروش برای حالت‌های صعودی
            if signal_type in ["PRE_PUMP", "ACTIVE_PUMP"] and current_price > 0:
                buy_price = current_price
                target_1 = current_price * 1.30  # ۳۰٪ سود
                target_2 = current_price * 1.60  # ۶۰٪ سود
                stop_loss = current_price * 0.85 # ۱۵٪ حد ضرر
                
                if current_price < 0.00001:
                    b_fmt, t1_fmt, t2_fmt, s_fmt = f"{buy_price:.10f}", f"{target_1:.10f}", f"{target_2:.10f}", f"{stop_loss:.10f}"
                elif current_price < 0.01:
                    b_fmt, t1_fmt, t2_fmt, s_fmt = f"{buy_price:.6f}", f"{target_1:.6f}", f"{target_2:.6f}", f"{stop_loss:.6f}"
                else:
                    b_fmt, t1_fmt, t2_fmt, s_fmt = f"{buy_price:.4f}", f"{target_1:.4f}", f"{target_2:.4f}", f"{stop_loss:.4f}"

                msg_lines.append(f"📥 قیمت ورود: <code>{b_fmt}</code>")
                msg_lines.append(f"🎯 تارگت ۱ (+30%): <code>{t1_fmt}</code>")
                msg_lines.append(f"🎯 تارگت ۲ (+60%): <code>{t2_fmt}</code>")
                msg_lines.append(f"🛑 حد ضرر (-15%): <code>{s_fmt}</code>")
            
            if base_token_id:
                msg_lines.append(f"📋 کانترکت: <code>{base_token_id}</code>")
            msg_lines.append("----------------------------")
            sent_count += 1
            
            if sent_count >= 4:
                break
                
    if sent_count > 0:
        msg = "\n".join(msg_lines)
        if tk and ch:
            notify_telegram(tk, ch, msg)
            print("[✓] سیگنال‌های پیش‌‌پامپ، پامپ و دامپ ارسال شدند.")
        else:
            print(msg)
    else:
        print("[-] هیچ توکنی با شرایط خاص در این بازه یافت نشد.")
