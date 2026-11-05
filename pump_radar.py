#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pump_radar.py — رادار میم‌کوین‌هایی که «تازه» شروع به پامپ کرده‌اند
نسخهٔ ۳ (مخصوص شکار لحظه‌ای و بدون تاخیر)
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (pump-radar/3.0)", "Accept": "application/json"}
STATE = os.environ.get("PUMP_STATE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "pump_radar_state.json")

GT = "https://api.geckoterminal.com/api/v2"
CG = "https://api.coingecko.com/api/v3"
DS = "https://api.dexscreener.com"
RC = "https://api.rugcheck.xyz/v1"

# ── فیلترهای سخت (برای حذف نویزهای مطلق، با انعطاف بیشتر برای شکار سریع‌تر)
MIN_LIQ = 20_000        # کاهش کف نقدینگی برای شکار استخرهای نطفه‌دار
MIN_AGE_MIN = 5.0       # کاهش سن به ۵ دقیقه (برای از دست ندادن ثانیه‌های اول)
MIN_V24 = 5_000         # کاهش کف حجم برای توکن‌های تازه متولد شده
MIN_TX5 = 4             # حداقل تراکنش در ۵ دقیقه اول
MIN_V5_USD = 500        # حداقل حجم ۵ دقیقه اول

MIN_SEND_FLOOR = 60     # کف امتیاز برای ارسال سیگنال فوری
WATCH_FLOOR = 45        # طبقهٔ زیر نظر

def _get(url, tries=3, base_sleep=1.0):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                time.sleep(base_sleep * (i + 1) * 2)
                continue
            return None
        except Exception as e:
            last = e
            time.sleep(base_sleep * (i + 1))
    return None

def cap_label(r):
    mc = nz(r.get("mc")) if r.get("mc") is not None else 0.0
    if mc > 0:
        return f"${mc:,.0f}"
    if nz(r.get("fdv")) > 0:
        return f"FDV ${nz(r.get('fdv')):,.0f}"
    return "نامعلوم"

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

def age_minutes(r):
    t = parse_dt(r.get("created"))
    if not t:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 60.0

def regime():
    out = {"verdict": "UNKNOWN", "score": 0, "notes": []}
    btc = _get(f"{CG}/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true")
    if btc and "bitcoin" in btc:
        b = btc["bitcoin"]
        p24 = nz(b.get("usd_24h_change"))
        out["btc_24h"] = round(p24, 2)
        if p24 > -2:
            out["score"] += 2
            out["notes"].append("وضعیت بازار مناسب برای پامپ")
        else:
            out["notes"].append("بازار بیت‌کوین کمی منفی است")
    out["allow"] = True # در حالت اسنایپر سریع، فیلتر کلان را نرم‌تر می‌کنیم
    return out

# ── دریافت استخرها از چند منبع مختلف (برای جلوگیری از تاخیر ترندینگ)
def gt_pools_multi(chain):
    rows = []
    # ۱. استخرهای ترندینگ
    for p in range(1, 2):
        d = _get(f"{GT}/networks/{chain}/trending_pools?page={p}")
        if d:
            for it in d.get("data", []):
                rows.append((it, "trending"))
        time.sleep(0.5)
    
    # ۲. استخرهای تازه ایجاد شده (کلید اصلی حل مشکل تاخیر)
    d_new = _get(f"{GT}/networks/{chain}/new_pools?page=1")
    if d_new:
        for it in d_new.get("data", []):
            rows.append((it, "new"))

    parsed = []
    seen = set()
    for it, src_type in rows:
        a = it.get("attributes", {})
        addr = a.get("address")
        if not addr or addr in seen:
            continue
        seen.add(addr)
        
        rel = it.get("relationships", {}) or {}
        base = ((rel.get("base_token") or {}).get("data") or {}).get("id", "") or ""
        if base.startswith(chain + "_"):
            base = base[len(chain) + 1:]
            
        parsed.append({
            "chain": chain,
            "pool": addr,
            "name": a.get("name"),
            "base_token": base,
            "created": a.get("pool_created_at"),
            "fdv": nz(a.get("fdv_usd")),
            "mc": a.get("market_cap_usd"),
            "price": nz(a.get("base_token_price_usd")),
            "pc": a.get("price_change_percentage", {}) or {},
            "tx": a.get("transactions", {}) or {},
            "vol": a.get("volume_usd", {}) or {},
            "reserve": nz(a.get("reserve_in_usd")),
            "dex": ((rel.get("dex") or {}).get("data") or {}).get("id", ""),
            "src": f"gt_{src_type}"
        })
    return parsed

def volume_ratios(r):
    vol = r.get("vol") or {}
    v5 = nz(vol.get("m5"))
    v1h = nz(vol.get("h1"))
    v24 = nz(vol.get("h24"))
    am = age_minutes(r)
    if am is None:
        am = 30.0
    age_h = min(max(am / 60.0, 5.0 / 60.0), 24.0)
    life_v = max(v24, v1h, v5)
    prior_v = max(life_v - v5, 0.0)
    prior_h = max(age_h - 5.0 / 60.0, 0.0)
    
    if prior_h >= 0.1 and prior_v > 0:
        avg5 = (prior_v / prior_h) / 12.0
    else:
        avg5 = (life_v / age_h) / 12.0 if age_h > 0 else 1.0

    rvol5 = (v5 / avg5) if avg5 > 0 else 1.0
    return {"v5": v5, "v1h": v1h, "v24": v24, "age_min": am, "rvol5": min(rvol5, 100.0)}

def pump_score(r):
    reasons, risks = [], []
    s = 0.0
    liq = nz(r.get("reserve"))
    v24 = nz(r.get("vol", {}).get("h24"))
    am = age_minutes(r)
    vr = volume_ratios(r)
    r.update(vr)
    v5, rvol5 = vr["v5"], vr["rvol5"]
    
    tx = r.get("tx", {}).get("m5", {})
    b5, s5 = nz(tx.get("buys")), nz(tx.get("sells"))
    trades5 = b5 + s5

    # فیلترهای سخت بازنگری‌شده برای سرعت بالا
    drop = []
    if liq < MIN_LIQ:
        drop.append(f"نقدینگی پایین (${liq:,.0f})")
    if am is not None and am < MIN_AGE_MIN:
        drop.append(f"سن خیلی کم ({am:.1f} دقیقه)")
    if v24 < MIN_V24:
        drop.append(f"حجم پایین (${v24:,.0f})")
    
    r["dropped"] = bool(drop)
    if drop:
        r["score"] = 0
        return r

    # سیستم امتیازدهی تهاجمی‌تر برای شکار سریع
    if rvol5 >= 5:
        s += 35
        reasons.append(f"شتاب انفجاری حجم ۵ دقیقه: {rvol5:.1f}x")
    elif rvol5 >= 2.5:
        s += 25
        reasons.append(f"جهش سریع حجم ۵ دقیقه: {rvol5:.1f}x")
    
    if trades5 >= 10:
        s += 20
        reasons.append(f"تراکنش‌های فشرده (${trades5} ترید در ۵ دقیقه)")

    if am is not None and am <= 120: # پاداش به توکن‌های تازه متولد شده (زیر ۲ ساعت)
        s += 20
        reasons.append(f"توکن تازه متولد شده ({am:.0f} دقیقه قبل)")

    r["score"] = min(s, 100)
    r["reasons"] = reasons
    r["risks"] = risks
    return r
