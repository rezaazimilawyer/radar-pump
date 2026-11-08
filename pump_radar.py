#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pump_radar.py — رادار میم‌کوین سولانا مجهز به تحلیل هوش مصنوعی Gemini
"""
import os
import sys
import time
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (compatible; PumpRadar/11.0)"}
GT = "https://api.geckoterminal.com/api/v2"

# کلید API جمنای شما که مستقیماً در کد قرار گرفت
GEMINI_KEY = "AQ.Ab8RN6KZemLT8PmoOSA_XyqyBkI2-KqTxLwuA5-TKOR2rSYIPg"

MIN_LIQ = 10_000          # حداقل نقدینگی ($10,000)
VOLUME_MULTIPLIER = 3.0   # حداقل جهش حجم ۳ برابری

def _get_safe(url, headers=UA, data=None):
    for attempt in range(3):
        try:
            time.sleep(2.0)
            req = urllib.request.Request(url, headers=headers, data=data)
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

def analyze_with_gemini(name, price_change, volume_ratio, reserve):
    """تحلیل هوشمند توکن با Google Gemini API"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {"Content-Type": "application/json"}
    
    prompt = (
        f"توکن {name} در شبکه سولانا با مشخصات زیر شناسایی شده:\n"
        f"- جهش حجم ۵ دقیقه: {volume_ratio:.1f} برابر\n"
        f"- تغییر قیمت ۵ دقیقه: {price_change:+.2f}%\n"
        f"- نقدینگی: ${reserve:,.0f}\n\n"
        f"پاسخ بده در یک جمله بسیار کوتاه فارسی (حداکثر ۱۵ کلمه): ریسک این ورود چطوره؟"
    )
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    res = _get_safe(url, headers=headers, data=json.dumps(payload).encode('utf-8'))
    try:
        text = res['candidates'][0]['content']['parts'][0]['text']
        return text.strip()
    except Exception:
        return "تحلیلی ثبت نشد."

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
    
    print("[+] اسکن بازار مجهز به Gemini API...")
    data = _get_safe(f"{GT}/networks/solana/trending_pools?page=1")
    
    msg_lines = [f"<b>🤖 رادار هوش مصنوعی Gemini (سولانا)</b>\n<code>{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC</code>\n"]
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
                
            signal_type = None
            if price_change <= -5.0:
                signal_type = "DUMP"
            elif volume_ratio >= VOLUME_MULTIPLIER:
                if -2.0 <= price_change <= 4.0:
                    signal_type = "PRE_PUMP"
                elif price_change > 4.0:
                    signal_type = "ACTIVE_PUMP"
            
            if not signal_type:
                continue
                
            rel = it.get("relationships", {})
            base_token_id = ((rel.get("base_token") or {}).get("data") or {}).get("id", "")
            if base_token_id.startswith("solana_"):
                base_token_id = base_token_id[7:]
                
            # دریافت نظر هوش مصنوعی Gemini
            ai_comment = analyze_with_gemini(name, price_change, volume_ratio, reserve)
            
            if signal_type == "PRE_PUMP":
                msg_lines.append(f"🟢 <b>[پیش‌پامپ / پول هوشمند] {name}</b>")
            elif signal_type == "ACTIVE_PUMP":
                msg_lines.append(f"🚀 <b>[در حال پامپ ⚡️] {name}</b>")
            elif signal_type == "DUMP":
                msg_lines.append(f"🔴 <b>[هشدار دامپ ⚠️] {name}</b>")
                
            msg_lines.append(f"⚡️ جهش حجم: <b>×{volume_ratio:.1f} برابر</b> | تغییر ۵دقیقه: {price_change:+.2f}%")
            msg_lines.append(f"💰 نقدینگی: ${reserve:,.0f}")
            msg_lines.append(f"🧠 <b>تحلیل Gemini:</b> <i>{ai_comment}</i>")
            
            if signal_type in ["PRE_PUMP", "ACTIVE_PUMP"] and current_price > 0:
                buy_price = current_price
                target_1 = current_price * 1.30
                target_2 = current_price * 1.60
                stop_loss = current_price * 0.85
                
                if current_price < 0.00001:
                    b_fmt, t1_fmt, t2_fmt, s_fmt = f"{buy_price:.10f}", f"{target_1:.10f}", f"{target_2:.10f}", f"{stop_loss:.10f}"
                elif current_price < 0.01:
                    b_fmt, t1_fmt, t2_fmt, s_fmt = f"{buy_price:.6f}", f"{target_1:.6f}", f"{target_2:.6f}", f"{stop_loss:.6f}"
                else:
                    b_fmt, t1_fmt, t2_fmt, s_fmt = f"{buy_price:.4f}", f"{target_1:.4f}", f"{target_2:.4f}", f"{stop_loss:.4f}"

                msg_lines.append(f"📥 ورود: <code>{b_fmt}</code>")
                msg_lines.append(f"🎯 تارگت ۱ (+30%): <code>{t1_fmt}</code>")
                msg_lines.append(f"🎯 تارگت ۲ (+60%): <code>{t2_fmt}</code>")
                msg_lines.append(f"🛑 حد ضرر (-15%): <code>{s_fmt}</code>")
            
            if base_token_id:
                msg_lines.append(f"📋 کانترکت: <code>{base_token_id}</code>")
            msg_lines.append("----------------------------")
            sent_count += 1
            
            if sent_count >= 3:
                break
                
    if sent_count > 0:
        msg = "\n".join(msg_lines)
        if tk and ch:
            notify_telegram(tk, ch, msg)
            print("[✓] سیگنال‌ها همراه با تحلیل Gemini ارسال شدند.")
        else:
            print(msg)
    else:
        print("[-] هیچ توکنی با شرایط خاص یافت نشد.")
