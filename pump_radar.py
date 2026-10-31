#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pump_radar.py  —  رادار میم‌کوین‌هایی که «تازه» شروع به پامپ کرده‌اند
نسخهٔ ۲ (اصلاح‌شده و مبتنی بر تحقیق)

────────────────────────────────────────────────────────────────────────────
چرا نسخهٔ ۱ خراب بود (اثبات‌شده با دادهٔ زنده)
────────────────────────────────────────────────────────────────────────────
فرمول قدیمی:  spike5 = v5 / (v6h / 72)

GeckoTerminal برای استخرهای جوان (کمتر از ۶ ساعت) مقدار m5 و h1 و h6 و h24 را
همه برابر «حجم کل عمر استخر» برمی‌گرداند. پس:
    v5 == v6h  ⇒  spike5 == 72.0   همیشه
در تست واقعی، ۱۴ استخر از ۲۰ استخر تازهٔ سولانا دقیقاً عدد 72.0 دادند.
یعنی ۳۰ امتیاز از ۱۰۰ به‌خاطر یک خطای تقسیم داده می‌شد.

────────────────────────────────────────────────────────────────────────────
فرمول جدید (نرمال‌سازی با سن واقعی استخر)
────────────────────────────────────────────────────────────────────────────
    age_h  = سن استخر بر حسب ساعت (بین ۵ دقیقه و ۲۴ ساعت بسته می‌شود)
    life_v = حجم کل عمر استخر  = max(v24, v6h, v1h)
    prior_v = life_v - v5            (حجم قبل از ۵ دقیقهٔ اخیر)
    prior_h = age_h - 5/60           (ساعت‌های قبل از ۵ دقیقهٔ اخیر)
    avg5    = (prior_v / prior_h) / 12     ← میانگین حجم هر ۵ دقیقه، بدون آلودگی
    rvol5   = v5 / avg5

چرا این درست است:
  • برای استخر بالای ۶ ساعت:  prior_v/prior_h ≈ v24/age  ⇒ همان مقیاس قبلی،
    پس آستانه‌های امتیازدهی معنای خودشان را حفظ می‌کنند (سازگار با گذشته).
  • برای استخر جوان، دیگر عدد ۷۲ مصنوعی تولید نمی‌شود.
  • خودِ ۵ دقیقهٔ فعلی از میانگین حذف می‌شود تا سیگنال خودش را رقیق نکند.
  • اگر تاریخ ساخت استخر نبود ⇒ فرض می‌کنیم فقط ۱ ساعت سابقه دارد (محتاطانه).

────────────────────────────────────────────────────────────────────────────
پشتوانهٔ تحقیق (چه چیزی واقعاً پامپ را زود تشخیص می‌دهد)
────────────────────────────────────────────────────────────────────────────
1) مقالهٔ arXiv 2602.14860  «Predicting the success of new crypto-tokens:
   the Pump.fun case» (Marino, Naviglio, Tarantelli, Lillo):
     - «سرعت انباشت نقدینگی با تعداد کم تراکنش» قوی‌ترین پیش‌بینی‌کننده است
       ⇒ امتیاز D: حجم به‌ازای هر تراکنش (پول درشت، نه ربات).
     - فعالیت ربات‌محور پیش‌بینی‌کنندهٔ منفی است
       ⇒ جریمهٔ تریدهای ریز (زیر $50) و واش‌تریدینگ.
     - نرخ موفقیت (graduation) در Pump.fun حدود ۰.۶۳٪ است
       ⇒ قاعدهٔ پایه: اکثر کاندیدها نویز هستند. سقف احتمالات را پایین نگه دار.
2) LuxAlgo: «هیچ آستانهٔ جادویی ۱.۵ یا ۲ یا ۳ برابر وجود ندارد که بریک‌اوت
   واقعی را از فیک جدا کند» ⇒ آستانه‌ها نسبی و چندپنجره‌ای شدند، نه یک عدد ثابت.
3) ME2F / MEMECONOMICS: «مارکت‌کپ نمایشی می‌تواند بالا بماند در حالی که
   نقدینگی قابل‌اجرا ناچیز است» ⇒ فیلتر سخت نقدینگی + نسبت liq/mc + چرخش.

────────────────────────────────────────────────────────────────────────────
خروجی
────────────────────────────────────────────────────────────────────────────
  python3 pump_radar.py                      # اسکن کامل
  python3 pump_radar.py --chains solana base
  python3 pump_radar.py --top 10 --send-above 65
  python3 pump_radar.py --json out.json
  python3 pump_radar.py --loop 15            # هر ۱۵ دقیقه
  python3 pump_radar.py --allow-risk-off     # ارسال حتی در بازار نزولی (پیش‌فرض: نه)
  python3 pump_radar.py --allow-low          # اجازهٔ آستانهٔ زیر ۶۵ (پیش‌فرض: نه)
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (pump-radar/2.0)", "Accept": "application/json"}
STATE = os.environ.get("PUMP_STATE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "pump_radar_state.json")

GT = "https://api.geckoterminal.com/api/v2"
CG = "https://api.coingecko.com/api/v3"
DS = "https://api.dexscreener.com"
RC = "https://api.rugcheck.xyz/v1"

# ── فیلترهای سخت (اگر رد شود، ردیف کاملاً حذف می‌شود، نه اینکه امتیاز کم بگیرد)
MIN_LIQ = 50_000        # نقدینگی کمتر از این ⇒ اصلاً لیست نشود
MIN_AGE_MIN = 20.0      # استخر تازه‌تر از ۲۰ دقیقه ⇒ نویز محض
MIN_V24 = 20_000        # حجم ۲۴ ساعته کمتر از این ⇒ بازار مرده
MIN_TX5 = 8             # کمتر از ۸ تراکنش در ۵ دقیقه ⇒ نمونهٔ آماری بی‌معنی
MIN_V5_USD = 1_500      # حجم ۵ دقیقه باید مبلغ واقعی باشد، نه ۳ دلار

# ── دو طبقهٔ ارسال (داخل خود اسکریپت اعمال می‌شود، نه در فایل workflow)
MIN_SEND_FLOOR = 65     # طبقهٔ ۱: سیگنال واقعی (🚀)
WATCH_FLOOR = 55        # طبقهٔ ۲: فقط زیر نظر (👀) — نه سیگنال، فقط اطلاع
WATCH_MAX = 5           # حداکثر چند آیتم «زیر نظر» در هر پیام

# ── تشخیص راگ با افت نقدینگی (TVL-drop) ────────────────────────────
# مقالهٔ arXiv 2608.20271v1: قوی‌ترین برچسب راگ، افت ~۹۹٪ TVL است.
# ما نسخهٔ نرم‌ترش را بین دو اجرا می‌سنجیم (چون هر ۱۵ دقیقه اجرا می‌شویم).
RUG_DROP_PCT = 35.0     # افت نقدینگی بیش از این ⇒ حذف کامل (راگ محتمل)
RUG_WARN_PCT = 18.0     # افت بیش از این ⇒ جریمهٔ سنگین + هشدار
RUG_LOOKBACK_H = 6.0    # حداکثر فاصلهٔ مجاز با اجرای قبلی برای مقایسه
# با کرون */5 پنجرهٔ واقعی مقایسه ≈ ۵ دقیقه می‌شود ⇒ راگ زودتر گیر می‌افتد.


# ═══════════════════════════════════════════════════════════ ابزار پایه
def _get(url, tries=3, base_sleep=1.5):
    """GET با تلاش مجدد. در ۴۲۹ (محدودیت نرخ) صبر می‌کند."""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
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
    if last:
        pass
    return None


def cap_label(r):
    """برچسب مارکت‌کپ: اگر mc نامعلوم/صفر بود از FDV استفاده کن (با ذکر نامش)."""
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
    """سن استخر بر حسب دقیقه، یا None اگر تاریخ ساخت نداشتیم."""
    t = parse_dt(r.get("created"))
    if not t:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 60.0


# ═══════════════════════════════════════════════════════════ رژیم کلان
def regime():
    """آیا اصلاً روز پامپ است؟ (قاعدهٔ پرامپت: در RISK-OFF لیست خالی)"""
    out = {"verdict": "UNKNOWN", "score": 0, "notes": []}
    btc = _get(f"{CG}/simple/price?ids=bitcoin&vs_currencies=usd"
               f"&include_24hr_change=true&include_7d_change=true")
    glob = _get(f"{CG}/global")
    if btc and "bitcoin" in btc:
        b = btc["bitcoin"]
        p = nz(b.get("usd"))
        c24 = nz(b.get("usd_24h_change"))
        c7 = nz(b.get("usd_7d_change"))
        out["btc_price"] = round(p, 2)
        out["btc_24h"] = round(c24, 2)
        out["btc_7d"] = round(c7, 2)
        if c7 > 3:
            out["score"] += 2
            out["notes"].append("BTC 7d صعودی")
        elif c7 < -3:
            out["notes"].append("BTC 7d نزولی")
        if c24 > 1:
            out["score"] += 1
            out["notes"].append("BTC 24h سبز")
        elif c24 < -1:
            out["notes"].append("BTC 24h قرمز")
    if glob and "data" in glob:
        d = glob["data"]
        dom = nz(d.get("market_cap_percentage", {}).get("btc"))
        mc24 = nz(d.get("market_cap_change_percentage_24h_usd"))
        out["btc_dom"] = round(dom, 2)
        out["total_mcap_24h"] = round(mc24, 2)
        if dom < 55:
            out["score"] += 2
            out["notes"].append("دامیننس BTC پایین (پول در آلت‌ها)")
        else:
            out["notes"].append("دامیننس BTC بالا (پول پنهان در BTC)")
        if mc24 > 1:
            out["score"] += 1
        elif mc24 < -2:
            out["notes"].append("مارکت‌کپ کل نزولی")
    try:
        fng = _get("https://api.alternative.me/fng/?limit=1")
        v = int(fng["data"][0]["value"])
        out["fear_greed"] = v
        out["fear_greed_txt"] = fng["data"][0]["value_classification"]
        if v >= 60:
            out["score"] += 1
    except Exception:
        pass
    s = out["score"]
    if s >= 4:
        out["verdict"] = "RISK-ON -> شکار پامپ مجاز"
        out["allow"] = True
    elif s >= 2:
        out["verdict"] = "NEUTRAL -> فقط رادار، نصف حجم"
        out["allow"] = True
    else:
        out["verdict"] = "RISK-OFF -> امروز روز پامپ نیست"
        out["allow"] = False
    return out


# ═══════════════════════════════════════════════════════════ جمع‌آوری داده
def gt_pools(chain, kind="trending", pages=2):
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
            rows.append({"chain": chain,
                         "pool": a.get("address"),
                         "name": a.get("name"),
                         "base_token": base,
                         "created": a.get("pool_created_at"),
                         "fdv": nz(a.get("fdv_usd")),
                         "mc": a.get("market_cap_usd"),        # خام می‌ماند: None = نامعلوم
                         "price": nz(a.get("base_token_price_usd")),
                         "pc": a.get("price_change_percentage", {}) or {},
                         "tx": a.get("transactions", {}) or {},
                         "vol": a.get("volume_usd", {}) or {},
                         "reserve": nz(a.get("reserve_in_usd")),
                         "dex": ((rel.get("dex") or {}).get("data") or {}).get("id", ""),
                         "src": f"gt_{kind}"})
        time.sleep(1.0)
    return rows


def ds_boosts():
    rows = []
    for u in (f"{DS}/token-boosts/top/v1", f"{DS}/token-boosts/latest/v1"):
        d = _get(u)
        if not isinstance(d, list):
            continue
        for it in d:
            rows.append({"chain": it.get("chainId"), "token": it.get("tokenAddress"),
                         "desc": (it.get("description") or "")[:60], "src": "ds_boost"})
    seen, out = set(), []
    for r in rows:
        k = (r["chain"], r["token"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def ds_token_pairs(chain, addr):
    if not addr:
        return []
    d = _get(f"{DS}/latest/dex/tokens/{addr}")
    if not d:
        return []
    return [p for p in (d.get("pairs") or []) if p.get("chainId") == chain]


def rugcheck(addr):
    """فقط برای کاندیدهای نهایی صدا زده می‌شود (کند است)."""
    if not addr:
        return None
    d = _get(f"{RC}/tokens/{addr}/report/summary", tries=1)
    if not isinstance(d, dict) or "score" not in d:
        return None
    risks = d.get("risks") or []
    names = []
    for x in risks[:4]:
        if isinstance(x, dict):
            names.append(str(x.get("name") or "")[:40])
        elif isinstance(x, str):
            names.append(x[:40])
    return {"score": nz(d.get("score")), "norm": nz(d.get("score_normalised")),
            "lp_locked": nz(d.get("lpLockedPct")), "risks": [n for n in names if n]}


# ═══════════════════════════════════════════════════════════ هستهٔ ریاضی
def volume_ratios(r):
    """
    محاسبهٔ rvol5 (نسبت حجم ۵ دقیقه به میانگین واقعی همان استخر)
    و rvol1h.  این تابع قلب اصلاح است.
    """
    vol = r.get("vol") or {}
    v5 = nz(vol.get("m5"))
    v1h = nz(vol.get("h1"))
    v6h = nz(vol.get("h6"))
    v24 = nz(vol.get("h24"))

    am = age_minutes(r)
    age_known = am is not None
    if am is None:
        am = 60.0  # فرض محتاطانه: یک ساعت سابقه

    age_h = min(max(am / 60.0, 5.0 / 60.0), 24.0)

    # برای استخرهای جوان، m5/h1/h6/h24 همه برابر حجم کل عمر است ⇒ بیشترین را بگیر
    life_v = max(v24, v6h, v1h, v5)

    prior_v = max(life_v - v5, 0.0)
    prior_h = max(age_h - 5.0 / 60.0, 0.0)

    if prior_h >= 0.15 and prior_v > 0:
        avg_h = prior_v / prior_h
        basis = "prior"
    elif age_h > 0 and life_v > 0:
        avg_h = life_v / age_h
        basis = "lifetime"
    else:
        avg_h = 0.0
        basis = "none"

    avg5 = avg_h / 12.0 if avg_h > 0 else 0.0
    rvol5 = (v5 / avg5) if avg5 > 0 else 0.0
    rvol1h = (v1h / avg_h) if avg_h > 0 else 0.0

    # سقف منطقی: یک تراکنش غول‌آسا نباید همه‌چیز را منفجر کند
    rvol5 = min(rvol5, 60.0)

    return {"v5": v5, "v1h": v1h, "v6h": v6h, "v24": v24,
            "age_min": am, "age_h": age_h, "age_known": age_known,
            "avg5": avg5, "rvol5": rvol5, "rvol1h": rvol1h, "basis": basis}


# ═══════════════════════════════════════════════════════════ امتیازدهی
def pump_score(r):
    """نمرهٔ ۰..۱۰۰ برای «تازه شروع شدن پامپ». دلایل و ریسک‌ها هم برگردانده می‌شود."""
    reasons, risks = [], []
    s = 0.0

    liq = nz(r.get("reserve"))
    mc_raw = r.get("mc")
    mc = nz(mc_raw) if mc_raw is not None else 0.0
    fdv = nz(r.get("fdv"))
    pc = r.get("pc") or {}
    tx = r.get("tx") or {}

    p5, p1h, p24 = nz(pc.get("m5")), nz(pc.get("h1")), nz(pc.get("h24"))

    tx5 = tx.get("m5") or {}
    b5, s5 = nz(tx5.get("buys")), nz(tx5.get("sells"))
    tx1 = tx.get("h1") or {}
    b1, s1 = nz(tx1.get("buys")), nz(tx1.get("sells"))

    vr = volume_ratios(r)
    r.update(vr)
    v5, v24 = vr["v5"], vr["v24"]
    rvol5, rvol1h = vr["rvol5"], vr["rvol1h"]
    am = vr["age_min"]
    trades5 = b5 + s5

    # ── فیلترهای سخت ────────────────────────────────────────────────
    drop = []
    if liq < MIN_LIQ:
        drop.append(f"نقدینگی ${liq:,.0f} زیر کف ${MIN_LIQ:,.0f}")
    if am is not None and am < MIN_AGE_MIN:
        drop.append(f"سن {am:.0f} دقیقه (زیر {MIN_AGE_MIN:.0f} دقیقه)")
    if v24 < MIN_V24:
        drop.append(f"حجم ۲۴ساعته ${v24:,.0f} (بازار مرده)")
    if trades5 < MIN_TX5:
        drop.append(f"فقط {trades5:.0f} تراکنش در ۵ دقیقه")
    # ضدِ artifact: استخری که هر تراکنشش چند دلار است، «فشار خرید» واقعی ندارد؛
    # فقط بات‌ها با هم معامله می‌کنند. قبلاً چنین استخری با نسبت ۱۲× امتیاز می‌گرفت.
    _pt = v5 / max(trades5, 1.0) if trades5 > 0 else 0.0
    if trades5 >= MIN_TX5 and v5 < MIN_V5_USD:
        drop.append(f"حجم ۵دقیقه فقط ${v5:,.0f} (ناچیز — زیر کف ${MIN_V5_USD:,.0f})")
    elif trades5 >= MIN_TX5 and _pt < 15:
        drop.append(f"میانگین هر تراکنش ${_pt:.0f} (استخر بات‌زده)")
    r["dropped"] = bool(drop)
    r["drop_reasons"] = drop
    if drop:
        r["score"] = 0
        r["reasons"] = ["فیلتر سخت رد شد"]
        r["risks"] = drop
        r["spike5"] = round(rvol5, 2)
        return r

    # ── A) انفجار حجم ۵ دقیقه‌ای  (۰..۲۸) ────────────────────────────
    r["spike5"] = round(rvol5, 2)      # برای سازگاری با نسخهٔ قبل
    r["rvol5"] = round(rvol5, 2)
    if v5 < MIN_V5_USD:
        risks.append(f"حجم ۵دقیقه فقط ${v5:,.0f} (ناچیز)")
    else:
        if rvol5 >= 8:
            s += 28
            reasons.append(f"انفجار حجم ۵دقیقه‌ای ×{rvol5:.1f} نسبت به میانگین واقعی خودش")
        elif rvol5 >= 5:
            s += 22
            reasons.append(f"جهش حجم ۵دقیقه‌ای ×{rvol5:.1f}")
        elif rvol5 >= 3:
            s += 16
            reasons.append(f"حجم ۵دقیقه‌ای ×{rvol5:.1f} بالای نرمال")
        elif rvol5 >= 2:
            s += 9
            reasons.append(f"حجم ۵دقیقه‌ای ×{rvol5:.1f} (بیدار شدن)")
        elif rvol5 >= 1.3:
            s += 3
            reasons.append(f"حجم ۵دقیقه‌ای ×{rvol5:.1f} (کمی بالاتر از نرمال)")
        elif rvol5 < 0.4:
            s -= 10
            risks.append("حجم ۵دقیقه‌ای مرده (زیر نصف نرمال)")

    # ── B) تأیید با پنجرهٔ ۱ ساعته  (۰..۱۴) ─────────────────────────
    # فقط اگر استخر واقعاً بیش از ۹۰ دقیقه عمر کرده باشد معنا دارد،
    # وگرنه h1 همان حجم کل عمر است و نسبت، مصنوعی می‌شود.
    if am is not None and am >= 90 and rvol1h > 0:
        if rvol1h >= 3:
            s += 14
            reasons.append(f"حجم ۱ساعته ×{rvol1h:.1f} نرمال (تأیید پنجرهٔ دوم)")
        elif rvol1h >= 2:
            s += 10
            reasons.append(f"حجم ۱ساعته ×{rvol1h:.1f}")
        elif rvol1h >= 1.5:
            s += 5
            reasons.append(f"حجم ۱ساعته ×{rvol1h:.1f}")
        elif rvol1h < 0.6:
            s -= 8
            risks.append("حجم ۱ساعته زیر نرمال (انفجار ۵دقیقه‌ای پشتوانه ندارد)")

    # ── C) فشار خرید واقعی  (۰..۱۶) ────────────────────────────────
    # نکتهٔ مهم: نسبت خرید/فروش فقط وقتی معنا دارد که حجم و تعداد ترید کافی باشد.
    # قبلاً استخری با حجم ۵دقیقه‌ای ۴ دلار و فروش صفر، «فشار خرید ۸۴×» می‌گرفت
    # و ۱۶ امتیاز رایگان می‌برد. حالا حداقل حجم و حداقل خریدار لازم است.
    if trades5 > 0:
        ratio = b5 / max(s5, 1.0)
        r["buy_ratio5"] = round(ratio, 2)
        # s5 >= 3  : اگر فروش صفر/۱ باشد نسبت بی‌معنا می‌شود (b5/max(s5,1) = b5)
        #            و همان artifact قبلی «۳۰× / ۵۲×» را می‌سازد.
        # per_trade: استخری که هر تراکنشش ۱۰ دلار است نمی‌تواند «فشار خرید» واقعی
        #            داشته باشد؛ فقط بات‌ها با هم معامله می‌کنند. (سه/SOL: ۱۲.۲× با $10)
        per_trade_now = v5 / max(trades5, 1.0)
        if (trades5 >= 10 and v5 >= 300 and b5 >= 8 and s5 >= 3
                and rvol5 >= 1.0 and per_trade_now >= 50):
            if ratio >= 3 and b5 >= 12:
                s += 16
                reasons.append(f"فشار خرید ۵دقیقه‌ای {ratio:.1f}× (خریدار غالب)")
            elif ratio >= 1.5:
                s += 9
                reasons.append(f"خرید ۵دقیقه‌ای {ratio:.1f}× فروش")
            elif ratio <= 0.6 and s5 >= 10:
                s -= 12
                risks.append("فروشنده غالب در ۵ دقیقهٔ اخیر")
        elif trades5 >= 10 and (v5 < 300 or rvol5 < 1.0):
            risks.append("حجم ۵دقیقه‌ای برای سنجش فشار خرید کافی نیست (فعالیت زیر نرمال)")
    if b1 + s1 > 0 and vr["v1h"] >= 2_000 and b1 >= 8 and s1 >= 3:
        r1 = b1 / max(s1, 1.0)
        if r1 >= 1.4:
            s += 6
            reasons.append(f"فشار خرید ۱ساعته {r1:.1f}×")

    # ── D) سرعت انباشت پول  (۰..۱۰)  ← قوی‌ترین یافتهٔ مقالهٔ arXiv ──
    # جریمهٔ «ترید ریز» فقط یک‌بار و فقط اگر در بخش C هم جریمه نشده باشد.
    per_tr = v5 / max(trades5, 1.0) if trades5 > 0 else 0.0
    r["usd_per_trade5"] = round(per_tr, 1)
    already_fined = any("ربات/واش‌تریدینگ" in x for x in risks)
    if trades5 >= 5:
        if per_tr >= 2000:
            s += 10
            reasons.append(f"پول درشت با تراکنش کم (${per_tr:,.0f} به‌ازای هر تراکنش)")
        elif per_tr <= 50 and not already_fined:
            s -= 6
            risks.append(f"تریدهای ریز و رباتیک (${per_tr:,.0f} هر تراکنش)")

    # ── E) کیفیت نقدینگی  (۰..۱۴) ──────────────────────────────────
    if liq >= 1_000_000:
        s += 12
        reasons.append("نقدینگی بالای $1M (خروج آسان)")
    elif liq >= 300_000:
        s += 9
        reasons.append(f"نقدینگی ${liq/1000:.0f}K قابل قبول")
    elif liq >= 150_000:
        s += 5
        reasons.append(f"نقدینگی ${liq/1000:.0f}K حداقلی")
    else:
        s += 1
        risks.append(f"نقدینگی فقط ${liq/1000:.0f}K (کف عبور کرد ولی نازک)")

    cap = mc if mc > 0 else fdv
    if cap > 0:
        lm = liq / cap
        r["liq_to_cap"] = round(lm, 3)
        if lm >= 0.15:
            s += 6
            reasons.append(f"نقدینگی {lm*100:.0f}٪ مارکت‌کپ (پشتوانهٔ واقعی)")
        elif lm < 0.03:
            s -= 8
            risks.append(f"نقدینگی فقط {lm*100:.1f}٪ مارکت‌کپ (حباب نمایشی)")
    if liq > 0 and v24 > 0:
        turn = v24 / liq
        r["turnover24"] = round(turn, 2)
        if 2 <= turn <= 15:
            s += 5
            reasons.append(f"چرخش ۲۴ساعته {turn:.1f}× نقدینگی (بازار داغ و سالم)")
        elif turn > 40:
            s -= 10
            risks.append(f"چرخش {turn:.0f}× نقدینگی (احتمال واش/چرن)")

    # ── F) هنوز بالا نرفته باشد (جا برای حرکت)  (۰..۱۲) ─────────────
    # p5 >= 0.2 : استخر مرده با تغییر ۰.۰٪ «تازه شروع‌شده» نیست.
    if p5 >= 0.2:
        if p5 <= 6:
            s += 8
            reasons.append(f"قیمت ۵دقیقه‌ای فقط +{p5:.1f}% (تازه شروع شده)")
        elif p5 <= 15:
            s += 5
            reasons.append(f"۵دقیقه‌ای +{p5:.1f}%")
        elif p5 > 25:
            s -= 14
            risks.append(f"۵دقیقه‌ای +{p5:.0f}% (دیر شده، تعقیب نکن)")
    if p1h > 40:
        s -= 10
        risks.append(f"۱ساعته +{p1h:.0f}% (بیش از حد کشیده)")
    if p24 > 100:
        s -= 20
        risks.append(f"۲۴ساعته +{p24:.0f}% (قاعدهٔ ۱۰۰٪ → حذف از ارسال)")
    elif 0 < p24 <= 60:
        s += 6
        reasons.append(f"۲۴ساعته +{p24:.0f}% (پامپ تازه)")

    # ── G) مارکت‌کپ ────────────────────────────────────────────────
    if mc_raw is None or nz(mc_raw) <= 0:
        risks.append("مارکت‌کپ در API نبود — با FDV سنجیده شد")
    if cap > 0:
        if 1_000_000 <= cap <= 50_000_000:
            s += 6
            reasons.append("مارکت‌کپ در محدودهٔ پامپ‌پذیر ($1M–$50M)")
        elif cap < 300_000:
            s -= 8
            risks.append("مارکت‌کپ زیر $300K (نازک و شکننده)")

    # ── H) سن استخر ────────────────────────────────────────────────
    if am is not None:
        r["age_days"] = round(am / 1440.0, 3)
        if am < 120:
            s -= 4
            risks.append("کمتر از ۲ ساعت سن (ریسک آتش‌بازی لحظه‌ای)")
        elif am < 1440:
            s += 2
            reasons.append("سن ۲ تا ۲۴ ساعت (تازه ولی قابل ارزیابی)")
        elif am < 4320:
            s += 3
            reasons.append("سن ۱ تا ۳ روز (تازه ولی جا افتاده)")
        elif am > 43200:
            s += 5
            reasons.append("پروژه عمر کرده (نه لانچ لحظه‌ای)")

    r["score"] = int(max(0, min(100, round(s))))
    r["reasons"] = reasons or ["هیچ نشانهٔ پامپ فعالی نیست"]
    r["risks"] = risks

    # ── چک‌لیست اجباری برای ارسال (مستقل از امتیاز) ─────────────────
    checks = {
        "نقدینگی ≥ $50K": liq >= MIN_LIQ,
        "سن ≥ ۲۰ دقیقه": (am is None) or (am >= MIN_AGE_MIN),
        "rvol5 ≥ ۲": rvol5 >= 2,
        "خرید/فروش ۵دقیقه ≥ ۱.۲": (s5 >= 3 and (b5 / max(s5, 1.0)) >= 1.2),
        "۲۴ساعته ≤ +۱۰۰٪": p24 <= 100,
    }
    r["checks"] = checks
    r["sendable"] = all(checks.values())
    return r


def phase(r):
    sc = r.get("score", 0)
    sp = r.get("rvol5", r.get("spike5", 0)) or 0
    if sc >= 70 and sp >= 5:
        return "🚀 شروع پامپ (خطر بالا، سود بالا)"
    if sc >= 55:
        return "⚡ بیدار شدن (رادار فعال)"
    if sc >= 40:
        return "👀 زیر نظر"
    return "—"


def confidence(sc):
    if sc >= 85:
        return "S", 70, 75
    if sc >= 75:
        return "A", 60, 70
    if sc >= 65:
        return "B", 52, 60
    if sc >= 55:
        return "C", 45, 52
    return "D", 0, 45


def pump_prob(sc):
    """احتمال پامپ +۵۰٪ در ۷ روز آینده.

    نکتهٔ مهم: این عدد یک «تخمین درون‌باندی» است و همیشه داخل همان بازه‌ای
    می‌افتد که confidence() برای همان امتیاز می‌دهد. قبلاً این دو ناسازگار
    بودند (امتیاز ۸۳ هم‌زمان «A = ۶۰–۷۰٪» و «۴۵٪» نشان می‌داد).
    هیچ بک‌تستی برای این عدد وجود ندارد — فقط رتبه‌بندی نسبی است.
    """
    g, lo, hi = confidence(sc)
    if g == "D":
        return round(min(hi, max(0.0, sc * 45.0 / 55.0)))
    floors = {"C": 55, "B": 65, "A": 75, "S": 85}
    f0 = floors[g]
    span = max(1, 100 - f0)
    frac = min(1.0, max(0.0, (sc - f0) / span))
    return round(min(hi, max(lo, lo + frac * (hi - lo))))


# ═══════════════════════════════════════════════════════════ وضعیت/حافظه
def load_state():
    if not os.path.exists(STATE):
        return {}
    try:
        with open(STATE) as f:
            return json.load(f) or {}
    except Exception:
        return {}


def save_state(state):
    try:
        with open(STATE, "w") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════ اجرا
def collect(chains):
    pools = []
    for c in chains:
        pools += gt_pools(c, "trending", pages=2)
        pools += gt_pools(c, "new", pages=1)
    return pools


def run(chains, top=15, min_score=None, new_only=False, out_json=None,
        dedupe_hours=6.0, do_rugcheck=True):
    reg = regime()
    pools = collect(chains)

    seen, uniq = set(), []
    for p in pools:
        k = (p["chain"], p.get("pool"))
        if k in seen or not p.get("pool"):
            continue
        seen.add(k)
        uniq.append(p)

    # اگر دادهٔ حجم نداشت، از DexScreener کامل کن (با آدرس واقعی توکن)
    for p in uniq:
        if not p.get("vol"):
            pr = ds_token_pairs(p["chain"], p.get("base_token"))
            if pr:
                x = pr[0]
                p["reserve"] = nz(x.get("liquidity", {}).get("usd"), p.get("reserve"))
                if p.get("mc") is None:
                    p["mc"] = x.get("marketCap")
                p["vol"] = {"h24": nz(x.get("volume", {}).get("h24")),
                            "h6": nz(x.get("volume", {}).get("h6")),
                            "h1": nz(x.get("volume", {}).get("h1")),
                            "m5": nz(x.get("volume", {}).get("m5"))}
                p["pc"] = x.get("priceChange") or {}
                p["tx"] = x.get("txns") or {}
            time.sleep(0.4)

    scored = [pump_score(p) for p in uniq]
    dropped = [r for r in scored if r.get("dropped")]
    scored = [r for r in scored if not r.get("dropped") and r["score"] > 0]
    scored.sort(key=lambda r: r["score"], reverse=True)

    if min_score:
        scored = [r for r in scored if r["score"] >= min_score]

    # ── وضعیت قبلی + حافظهٔ ارسال‌شده‌ها ─────────────────────────────
    st = load_state()
    prev, prev_liq = {}, {}
    for x in (st.get("rows") or []):
        kk = f"{x.get('chain')}|{x.get('pool')}"
        prev[kk] = x.get("score", 0)
        if x.get("liq"):
            prev_liq[kk] = (nz(x.get("liq")), parse_dt(x.get("ts")))

    now = datetime.now(timezone.utc)

    # ── دروازهٔ افت نقدینگی: قوی‌ترین یافتهٔ مقالهٔ arXiv ─────────────
    for r in scored:
        kk = f"{r.get('chain')}|{r.get('pool')}"
        pl = prev_liq.get(kk)
        if not pl:
            continue
        old_liq, old_t = pl
        if old_liq <= 0:
            continue
        if old_t is not None:
            if old_t.tzinfo is None:
                old_t = old_t.replace(tzinfo=timezone.utc)
            if (now - old_t).total_seconds() / 3600.0 > RUG_LOOKBACK_H:
                continue
        liq_now = nz(r.get("reserve"))
        drop = (old_liq - liq_now) / old_liq * 100.0
        r["liq_drop_pct"] = round(drop, 1)
        if drop >= RUG_DROP_PCT:
            r["dropped"] = True
            r["rug_dropped"] = True
            r["score"] = 0
            r["sendable"] = False
            r["drop_reasons"] = [
                f"نقدینگی {drop:.0f}٪ آب رفت (از ${old_liq:,.0f} به ${liq_now:,.0f}) "
                f"→ نشانهٔ راگ / کشیدن LP"]
            r["risks"] = r["drop_reasons"]
            r["reasons"] = ["حذف شد: افت نقدینگی"]
            dropped.append(r)
        elif drop >= RUG_WARN_PCT:
            r["score"] = int(max(0, r["score"] - 15))
            r["risks"].append(
                f"نقدینگی {drop:.0f}٪ کم شده (از ${old_liq:,.0f} به ${liq_now:,.0f})")
            if drop >= RUG_WARN_PCT * 1.5:
                r["sendable"] = False

    scored = [r for r in scored if not r.get("dropped") and r["score"] > 0]
    scored.sort(key=lambda r: r["score"], reverse=True)
    rug_dropped = [r for r in dropped if r.get("rug_dropped")]
    rug_warned = [r for r in scored if r.get("liq_drop_pct", 0) >= RUG_WARN_PCT]

    sent = {}
    for k, iso in (st.get("sent") or {}).items():
        t = parse_dt(iso)
        if t and (now - t).total_seconds() / 3600.0 <= dedupe_hours:
            sent[k] = iso

    for r in scored:
        k = f"{r.get('chain')}|{r.get('pool')}"
        old = prev.get(k)
        if old is None:
            r["status"] = "🆕 وارد رادار شد"
        elif r["score"] > old + 10:
            r["status"] = f"📈 صعودی (از {old} به {r['score']})"
        elif r["score"] < old - 10:
            r["status"] = f"📉 در حال خنک شدن (از {old})"
        else:
            r["status"] = "· پایدار"
        r["already_sent"] = k in sent

    scored.sort(key=lambda r: r["score"], reverse=True)
    top_rows = scored[:top]

    # ── RugCheck فقط برای کاندیدهای واقعاً ارسال‌شدنی ────────────────
    if do_rugcheck:
        n = 0
        for r in top_rows:
            if n >= 6:
                break
            if r["score"] >= MIN_SEND_FLOOR and r.get("sendable") and not r.get("already_sent"):
                if r.get("chain") == "solana":
                    rc = rugcheck(r.get("base_token"))
                    if rc:
                        r["rugcheck"] = rc
                        if rc["risks"]:
                            r["risks"].append("RugCheck: " + "، ".join(rc["risks"][:2]))
                n += 1

    res = {"generated_utc": now.strftime("%Y-%m-%d %H:%M:%S"),
           "generated_iso": now.isoformat(),
           "regime": reg, "scanned_pools": len(uniq),
           "dropped_hard_filters": len([x for x in dropped if not x.get("rug_dropped")]),
           "rug_dropped": [{"name": r.get("name"), "chain": r.get("chain"),
                            "pool": r.get("pool"), "drop": r.get("liq_drop_pct")}
                           for r in rug_dropped],
           "rug_warned": [{"name": r.get("name"), "chain": r.get("chain"),
                           "drop": r.get("liq_drop_pct")} for r in rug_warned],
           "rows": top_rows}

    state = {"generated_utc": res["generated_utc"],
             "rows": [{"chain": r.get("chain"), "pool": r.get("pool"),
                       "score": r.get("score"),
                       "liq": r.get("reserve"),
                       "ts": res["generated_iso"]} for r in scored[:60]],
             "sent": sent}
    save_state(state)
    res["_sent"] = sent

    if out_json:
        try:
            with open(out_json, "w") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
        except Exception:
            pass
    return res


def show(res, limit=15):
    reg = res["regime"]
    print("=" * 78)
    print(f"رادار پامپ v2  ·  {res['generated_utc']} UTC  ·  "
          f"استخر اسکن‌شده: {res['scanned_pools']}  ·  "
          f"رد شده با فیلتر سخت: {res.get('dropped_hard_filters', 0)}")
    print("=" * 78)
    print(f"رژیم بازار: {reg['verdict']}   (امتیاز {reg.get('score')}/5)")
    for n in reg.get("notes", []):
        print("   •", n)
    if "btc_price" in reg:
        print(f"   BTC ${reg['btc_price']:,} | 24h {reg.get('btc_24h')}% | "
              f"7d {reg.get('btc_7d')}% | دامیننس {reg.get('btc_dom')}% | "
              f"ترس‌وطمع {reg.get('fear_greed')}")
    print()
    for d0 in (res.get("rug_dropped") or []):
        print(f"🛑 حذف شد (راگ): {d0.get('name')} [{d0.get('chain')}] "
              f"— نقدینگی {nz(d0.get('drop')):.0f}٪ آب رفت")
    for w0 in (res.get("rug_warned") or []):
        print(f"⚠️ هشدار نقدینگی: {w0.get('name')} [{w0.get('chain')}] "
              f"— {nz(w0.get('drop')):.0f}٪ کم شده (−۱۵ امتیاز)")
    if res.get("rug_dropped") or res.get("rug_warned"):
        print()
    if not res["rows"]:
        print("🔴 هیچ توکنی از فیلترها و آستانهٔ امتیاز عبور نکرد. امروز روز تماشا است.")
        return
    n_hot = len([r for r in res["rows"] if r["score"] >= MIN_SEND_FLOOR])
    n_watch = len([r for r in res["rows"] if WATCH_FLOOR <= r["score"] < MIN_SEND_FLOOR])
    print(f"🚀 سیگنال (≥{MIN_SEND_FLOOR}): {n_hot}   |   "
          f"👀 زیر نظر ({WATCH_FLOOR}–{MIN_SEND_FLOOR - 1}): {n_watch}")
    print()
    for i, r in enumerate(res["rows"][:limit], 1):
        g, lo, hi = confidence(r["score"])
        tier = "🚀" if r["score"] >= MIN_SEND_FLOOR else (
            "👀" if r["score"] >= WATCH_FLOOR else "  ")
        print(f"{i:2d}. {tier} {r.get('name','?')}  [{r.get('chain')}]  score={r['score']} ({g})"
              f"  پامپ۷روزه≈{pump_prob(r['score'])}%  {phase(r)}")
        print(f"    liq ${nz(r.get('reserve')):,.0f} | mc {cap_label(r)}"
              f" | 24h {nz((r.get('pc') or {}).get('h24')):.1f}%"
              f" | 1h {nz((r.get('pc') or {}).get('h1')):.1f}%"
              f" | 5m {nz((r.get('pc') or {}).get('m5')):.1f}%")
        print(f"    rvol5 {r.get('rvol5', 0):.2f}× | rvol1h {r.get('rvol1h', 0):.2f}×"
              f" | سن {r.get('age_min', 0):.0f} دقیقه"
              f" | ${r.get('usd_per_trade5', 0):,.0f}/تراکنش")
        print(f"    وضعیت: {r.get('status','·')}"
              f"{'  (قبلاً ارسال شده)' if r.get('already_sent') else ''}")
        for x in r["reasons"][:4]:
            print(f"      + {x}")
        for x in r["risks"][:3]:
            print(f"      - {x}")
        print()


def notify_telegram(token, chat, text):
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        body = json.dumps({"chat_id": chat, "text": text,
                           "parse_mode": "HTML",
                           "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(url, data=body,
                                     headers={**UA, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception as e:
        print("[telegram error]", e)
        return False


def alert_text(res, min_send=MIN_SEND_FLOOR, allow_risk_off=False,
               watch_floor=WATCH_FLOOR):
    """
    متن هشدار دوطبقه. دروازه‌ها:
      ۱) رژیم بازار (در RISK-OFF چیزی ارسال نمی‌شود)
      ۲) طبقهٔ 🚀 سیگنال: score ≥ min_send (هرگز زیر MIN_SEND_FLOOR)
      ۳) طبقهٔ 👀 زیر نظر: WATCH_FLOOR ≤ score < min_send  (علامت ارسال نمی‌گیرد)
      ۴) چک‌لیست اجباری + قبلاً ارسال نشده باشد
    """
    reg = res["regime"]
    risk_off = (not reg.get("allow", True)) and not allow_risk_off

    ok = lambda r: r.get("sendable") and not r.get("already_sent")
    hot = [r for r in res["rows"] if r["score"] >= min_send and ok(r)]
    watch = [r for r in res["rows"]
             if watch_floor <= r["score"] < min_send and ok(r)]

    # در RISK-OFF طبقهٔ 🚀 کامل خاموش می‌شود (قاعدهٔ آهنین)، ولی طبقهٔ 👀
    # که صریحاً «سیگنال نیست» است باقی می‌ماند تا کاربر بداند رادار زنده است.
    if risk_off:
        if hot:
            print(f"[gate] رژیم {reg['verdict']} → {len(hot)} سیگنال 🚀 سانسور شد")
        hot = []
    if not hot and not watch:
        return None

    L = [f"<b>🚨 رادار پامپ</b>  {res['generated_utc']} UTC",
         f"رژیم: {reg['verdict']}", ""]
    if risk_off:
        L.append("<b>🔴 RISK-OFF</b> — بازار منفی است. هیچ سیگنال خریدی صادر نشد.")
        L.append("<i>فقط لیست «زیر نظر» برای اطلاع است.</i>")
        L.append("")
    keys = []
    rugs = res.get("rug_dropped") or []
    if rugs:
        L.append("<b>🛑 حذف‌شده به‌دلیل افت نقدینگی</b>")
        for d0 in rugs[:4]:
            L.append(f"  • {d0.get('name')} [{d0.get('chain')}] — "
                     f"نقدینگی {nz(d0.get('drop')):.0f}٪ آب رفت")
        L.append("")
    warns = res.get("rug_warned") or []
    if warns:
        L.append("<b>⚠️ هشدار افت نقدینگی</b>")
        for w0 in warns[:4]:
            L.append(f"  • {w0.get('name')} [{w0.get('chain')}] — "
                     f"نقدینگی {nz(w0.get('drop')):.0f}٪ کم شده")
        L.append("")

    # ── طبقهٔ ۱: سیگنال ──────────────────────────────────────
    if hot:
        L.append(f"<b>🚀 سیگنال ({len(hot)} مورد، امتیاز ≥{min_send})</b>")
        L.append("")
        for r in hot[:5]:
            g, lo, hi = confidence(r["score"])
            L.append(f"<b>{r.get('name','?')}</b> [{r.get('chain')}] "
                     f"score={r['score']} ({g}) پامپ≈{pump_prob(r['score'])}%")
            L.append(f"  liq ${nz(r.get('reserve')):,.0f} | mc {cap_label(r)}"
                     f" | 24h {nz((r.get('pc') or {}).get('h24')):.1f}%"
                     f" | rvol5 {r.get('rvol5', 0):.1f}×"
                     f" | سن {r.get('age_min', 0):.0f}د")
            bt = r.get("base_token") or ""
            if bt:
                L.append(f"  <code>{bt}</code>")
            for x in r["reasons"][:3]:
                L.append(f"  ✅ {x}")
            for x in r["risks"][:2]:
                L.append(f"  ⚠️ {x}")
            if r.get("rugcheck") and r["rugcheck"].get("risks"):
                L.append(f"  🛑 {', '.join(r['rugcheck']['risks'][:2])}")
            L.append("")
            keys.append(f"{r.get('chain')}|{r.get('pool')}")

    # ── طبقهٔ ۲: فقط زیر نظر (بدون علامت ارسال) ───────────────
    if watch:
        L.append(f"<b>👀 زیر نظر ({len(watch)} مورد، {watch_floor}–{min_send - 1})</b>")
        L.append("  <i>این‌ها سیگنال نیستند — فقط بیدار شدن. ورود نزن.</i>")
        for r in watch[:WATCH_MAX]:
            L.append(f"  • {r.get('name','?')} [{r.get('chain')}] "
                     f"score={r['score']} | rvol5 {r.get('rvol5', 0):.1f}×"
                     f" | 24h {nz((r.get('pc') or {}).get('h24')):.0f}%"
                     f" | liq ${nz(r.get('reserve')):,.0f}")
        L.append("")

    L.append("❗️سیگنال آماده نیست. تحقیق شخصی و حد ضرر اجباری. حداکثر ۲٪ سرمایه.")
    res["_hot_keys"] = keys
    return "\n".join(L)


def mark_sent(res):
    keys = res.get("_hot_keys") or []
    if not keys:
        return
    st = load_state()
    sent = st.get("sent") or {}
    now_iso = datetime.now(timezone.utc).isoformat()
    for k in keys:
        sent[k] = now_iso
    st["sent"] = sent
    save_state(st)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chains", nargs="*",
                    default=["solana", "base", "eth", "bsc"])
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--min-score", type=int, default=None)
    ap.add_argument("--json", dest="out_json", default=None)
    ap.add_argument("--new-only", action="store_true")
    ap.add_argument("--loop", type=int, default=0,
                    help="هر N دقیقه یک‌بار تکرار کن (0 = یک‌بار)")
    # نکته: در ورک‌فلو به شکل خالی «--telegram» استفاده می‌شود تا کلیدها از
    # متغیرهای محیطی TG_TOKEN/TG_CHAT خوانده شوند. بدون nargs="?" این حالت
    # با خطای «expected one argument» کرش می‌کرد.
    ap.add_argument("--telegram", nargs="?", const="env", default=None,
                    help="TOKEN:CHAT_ID برای ارسال هشدار تلگرام "
                         "(بدون مقدار ⇒ از TG_TOKEN و TG_CHAT)")
    ap.add_argument("--send-above", type=int, default=MIN_SEND_FLOOR,
                    help=f"فقط score بالاتر از این سیگنال (🚀) حساب شود (کف مجاز: {MIN_SEND_FLOOR})")
    ap.add_argument("--watch-floor", type=int, default=WATCH_FLOOR,
                    help=f"کف طبقهٔ «زیر نظر» (👀). پیش‌فرض {WATCH_FLOOR}")
    ap.add_argument("--no-watch", action="store_true",
                    help="طبقهٔ «زیر نظر» را کامل خاموش کن (فقط سیگنال بفرست)")
    ap.add_argument("--allow-risk-off", action="store_true",
                    help="ارسال حتی وقتی رژیم بازار RISK-OFF است")
    ap.add_argument("--allow-low", action="store_true",
                    help=f"اجازهٔ آستانهٔ زیر {MIN_SEND_FLOOR} (توصیه نمی‌شود)")
    ap.add_argument("--dedupe-hours", type=float, default=6.0,
                    help="هر استخر تا این تعداد ساعت دوباره ارسال نشود")
    ap.add_argument("--no-rugcheck", action="store_true",
                    help="بررسی RugCheck را خاموش کن (سریع‌تر)")
    a = ap.parse_args()

    threshold = a.send_above
    if threshold < MIN_SEND_FLOOR and not a.allow_low:
        print(f"[gate] آستانهٔ {threshold} زیر کف {MIN_SEND_FLOOR} بود → "
              f"به {MIN_SEND_FLOOR} بالا برده شد (برای عبور: --allow-low)")
        threshold = MIN_SEND_FLOOR

    wfloor = threshold if a.no_watch else min(a.watch_floor, threshold)
    if wfloor < threshold:
        print(f"[tier] دو طبقه فعال: 🚀 سیگنال ≥{threshold}  |  👀 زیر نظر {wfloor}–{threshold - 1}")

    tgt = None
    if a.telegram and ":" in a.telegram:
        tk, ch = a.telegram.split(":", 1)
        tgt = (tk, ch)
    elif os.environ.get("TG_TOKEN") and os.environ.get("TG_CHAT"):
        tgt = (os.environ["TG_TOKEN"], os.environ["TG_CHAT"])

    while True:
        r = run(a.chains, a.top, a.min_score, a.new_only, a.out_json,
                dedupe_hours=a.dedupe_hours, do_rugcheck=not a.no_rugcheck)
        show(r, a.top)
        if tgt:
            txt = alert_text(r, threshold, allow_risk_off=a.allow_risk_off,
                             watch_floor=wfloor)
            if txt:
                ok = notify_telegram(tgt[0], tgt[1], txt)
                print(f"[telegram] {'ارسال شد' if ok else 'ارسال نشد'}")
                if ok:
                    mark_sent(r)
            else:
                print(f"[telegram] چیزی بالای {wfloor} نبود → ارسال نشد")
        if a.loop <= 0:
            break
        print(f"\n⏳ {a.loop} دقیقه صبر... (Ctrl+C برای توقف)\n")
        time.sleep(a.loop * 60)
