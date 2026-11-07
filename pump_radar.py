#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pump_radar.py — رادار فعالیت غیرعادی میم‌کوین (نسخه ایمن در برابر نرخ محدودیت API)
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (pump-radar/6.2-safe)", "Accept": "application/json"}
STATE = os.environ.get("PUMP_STATE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "pump_radar_state.json")

GT = "https://api.geckoterminal.com/api/v2"
DS = "https://api.dexscreener.com"

# ── تنظیمات آستانه سریع و امن ──────────────────────────────────────
MIN_LIQ = 15_000        
MIN_AGE_MIN = 3.0       
MIN_V24 = 5_000         
MIN_TX5 = 3             
MIN_SEND_FLOOR = 40     
WATCH_FLOOR = 35        
PRESIGNAL_FLOOR = 30    

def _mask(s):
    s = str(s)
    s = re.sub(r"\b\d{6,}[A-Za-z0-9_-]{30,}\b", "<BOT_TOKEN>", s)
    return s

def _log_err(msg):
    print("[err]", _mask(msg), file=sys.stderr)

def _get(url, tries=4, base_sleep=3.0):
    """تابع امن برای جلوگیری از خطای ۴۲۹ با مکث هوشمند"""
    last = None
    for i in range(tries):
        try:
            time.sleep(1.2)  # مکث اجباری بین هر درخواست برای رعایت قوانین API
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                wait_time = base_sleep * (i + 2)
                print(f"[warning] خطای ۴۲۹ (محدودیت نرخ). صبر کردن به مدت {wait_time} ثانیه...", file=sys.stderr)
                time.sleep(wait_time)
                continue
            return None
        except Exception as e:
            last = e
            time.sleep(base_sleep)
    if last:
        _log_err(f"GET failed {url.split('?')[0]}: {last}")
    return None

def nz(v, d=0.0):
    try:
        if v is None:
            return d
        return float(v)
    except Exception:
        return d

def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None

def cap_label(r):
    mc = nz(r.get("mc")) if r.get("mc") is not None else 0.0
    if mc > 0:
        return f"${mc:,.0f}"
    if nz(r.get("fdv")) > 0:
        return f"FDV ${nz(r.get('fdv')):,.0f}"
    return "نامعلوم"

def age_minutes(r):
    t = parse_dt(r.get("created"))
    if not t:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 60.0

def fmt_usd(v):
    v = nz(v)
    if v <= 0:
        return "?"
    if v >= 1_000_000:
        return f"${v / 1e6:.1f}M"
    if v >= 1_000:
        return f"${v / 1e3:.0f}K"
    return f"${v:.0f}"

def gt_pools(chain, kind="trending", pages=1):
    rows = []
    for p in range(1, pages + 1):
        d = _get(f"{GT}/networks/{chain}/{kind}_pools?page={p}")
        if not d:
            break
        for it in d.get("data", []):
            a = it.get("attributes", {})
            rel = it.get("relationships", {}) or {}
            base = ((rel.get("base_token") or {}).get("data") or {}).get("id", "") or ""
            if base.startswith(chain + "_"):
                base = base[len(chain) + 1:]
            rows.append({
                "chain": chain,
                "pool": a.get("address"),
                "name": a.get("name"),
                "base_token": base,
                "created": a.get("pool_created_at"),
                "fdv": nz(a.get("fdv_usd")),
                "mc": a.get("market_cap_usd"),
                "pc": a.get("price_change_percentage", {}) or {},
                "tx": a.get("transactions", {}) or {},
                "vol": a.get("volume_usd", {}) or {},
                "reserve": nz(a.get("reserve_in_usd")),
            })
    return rows

def volume_ratios(r):
    vol = r.get("vol") or {}
    v5 = nz(vol.get("m5"))
    v24 = nz(vol.get("h24"))
    am = age_minutes(r)
    age_h = None if am is None else min(max(am / 60.0, 0.08), 24.0)
    
    avg5 = max(v24 / 288.0, 10.0) if age_h else 10.0
    rvol5 = (v5 / avg5) if avg5 > 0 else 1.0
    return {"v5": v5, "v24": v24, "age_min": am, "rvol5": min(rvol5, 50.0)}

def pump_score(r):
    reasons = []
    s = 0.0
    liq = nz(r.get("reserve"))
    pc = r.get("pc") or {}
    p5 = nz(pc.get("m5"))
    vr = volume_ratios(r)
    r.update(vr)
    
    if liq < MIN_LIQ or vr["v24"] < 5000:
        r["dropped"] = True
        return r

    if vr["rvol5"] >= 2.0:
        s += 40
        reasons.append(f"جهش حجم ×{vr['rvol5']:.1f}")
    if p5 > 0.2:
        s += 30
        reasons.append(f"رشد قیمت ۵دقیقه: {p5:+.1f}%")
    if liq >= 20_000:
        s += 20
        reasons.append(f"نقدینگی خوب {fmt_usd(liq)}")

    r["score"] = int(max(0, min(100, s)))
    r["reasons"] = reasons
    r["dropped"] = False
    return r

def run(chains):
    pools = []
    for c in chains:
        pools += gt_pools(c, "trending", pages=1)
        time.sleep(1.0) # استراحت بین درخواست زنجیره‌ها
    
    scored = [pump_score(p) for p in pools if not p.get("dropped")]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored

def notify_telegram(token, chat, text):
    if not token or not chat:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={**UA, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return True
    except Exception as e:
        _log_err(f"telegram: {e}")
        return False

if __name__ == "__main__":
    tk = os.environ.get("TG_TOKEN")
    ch = os.environ.get("TG_CHAT")
    
    print("[+] شروع اسکن ایمن بازار...")
    rows = run(["solana", "base"])
    
    top_hits = [r for r in rows if r["score"] >= MIN_SEND_FLOOR]
    if top_hits:
        msg = "<b>🚀 سیگنال‌های سریع میم‌کوین</b>\n\n"
        for r in top_hits[:5]:
            msg += f"<b>🔹 {html.escape(str(r.get('name')))}</b> [{r.get('chain')}]\n"
            msg += f"   نقدینگی: {fmt_usd(r.get('reserve'))} | امتیاز: {r['score']}\n"
            msg += f"   آدرس کانترکت: <code>{r.get('base_token')}</code>\n\n"
        
        if tk and ch:
            notify_telegram(tk, ch, msg)
            print("[✓] پیام با موفقیت ارسال شد.")
        else:
            print(msg)
    else:
        print("[-] هیچ موردی با امتیاز بالا یافت نشد.")
