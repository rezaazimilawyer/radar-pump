#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pump_radar.py — رادار «فعالیت غیرعادی میم‌کوین» (نسخهٔ ۶)

────────────────────────────────────────────────────────────────────────────
این ابزار چه هست و چه نیست
────────────────────────────────────────────────────────────────────────────
هست:      یک اسکنر که هر N دقیقه استخرهای نقدینگی را می‌خواند و استخرهایی را
          که «همین حالا» فعالیت غیرعادی دارند (انفجار حجم، فشار خرید، شتاب)
          با یک امتیاز ۰..۱۰۰ رتبه‌بندی می‌کند و به تلگرام می‌فرستد.
نیست:     پیش‌بینی‌کنندهٔ پامپ. هیچ بک‌تستی روی این امتیاز انجام نشده و
          «احتمال موفقیت» برایش محاسبه نشده است. امتیاز ۷۵ یعنی «فعالیت
          غیرعادی زیاد»، نه «۷۵٪ احتمال سود». نسخه‌های قبلی عددی به‌نام
          «پامپ ≈ درصد» چاپ می‌کردند؛ آن عدد از هیچ مدل آماری نمی‌آمد و حذف شد.

هیچ ادعای پژوهشی در این فایل نیست. هر آستانه یک انتخاب مهندسی قابل تنظیم
است، نه یک یافتهٔ علمی. اگر آستانه‌ای را عوض می‌کنید، امتیازها هم عوض می‌شوند.

────────────────────────────────────────────────────────────────────────────
تاریخچهٔ اصلاحات مهم (برای اینکه دیگر تکرار نشوند)
────────────────────────────────────────────────────────────────────────────
۱) باگ تقسیم نسخهٔ ۱:  spike5 = v5 / (v6h / 72)
   GeckoTerminal برای استخرهای جوان (کمتر از ۶ ساعت) مقدار m5/h1/h6/h24 را
   همه برابر «حجم کل عمر استخر» برمی‌گرداند. نتیجه: v5 == v6h و در ۱۴ استخر
   از ۲۰ استخر تازهٔ سولانا عدد ثابت 72.0 تولید می‌شد (۳۰ امتیاز رایگان).
   رفع: rvol5 در برابر baseline واقعی همان استخر سنجیده می‌شود؛ اگر baseline
   معتبر نبود، هیچ امتیازی برای «انفجار حجم» داده نمی‌شود (fix #2).

۲) باگ «سن نامعلوم = ۱ ساعت»: نسخهٔ ۵ اگر تاریخ ساخت استخر را نداشت، فرض
   می‌کرد استخر ۱ ساعت عمر دارد و از همان فرض baseline می‌ساخت. این یعنی
   ساختن داده از هوا. در v6 سن نامعلوم ⇒ rvol5 = None و بدون امتیاز.

۳) باگ تناقض رژیم (دیده‌شده در پیام واقعی تلگرام): هدر پیام می‌گفت
   «RISK-OFF» ولی همان پیام یک «🚀 سیگنال» داشت. علتش این بود که «متنِ هدر»
   و «دروازهٔ ارسال» از دو جای مختلف خوانده می‌شدند. در v6 یک سیاست واحد
   (SEND_POLICY) در یک نقطه محاسبه می‌شود و هم هدر و هم دروازه از همان
   خوانده می‌شوند؛ حالت متناقض ساختاراً غیرممکن است (fix #9).

────────────────────────────────────────────────────────────────────────────
اجرا
────────────────────────────────────────────────────────────────────────────
  python3 pump_radar.py                        # اسکن کامل، بدون ارسال
  python3 pump_radar.py --chains solana base
  python3 pump_radar.py --top 10 --send-above 65 --telegram
  python3 pump_radar.py --json out.json
  python3 pump_radar.py --loop 15              # هر ۱۵ دقیقه
  python3 pump_radar.py --allow-risk-off       # ارسال حتی در بازار نزولی
  python3 pump_radar.py --allow-unknown        # ارسال حتی وقتی رژیم نامعلوم است
  python3 pump_radar.py --no-presignal         # خاموش‌کردن طبقهٔ ⚡
  python3 pump_radar.py --new-only             # فقط توکن‌هایی که تازه وارد رادار شدند

کلید تلگرام (به‌ترتیب اولویت):
  ۱) --telegram TOKEN:CHAT_ID
  ۲) متغیرهای محیطی TG_TOKEN و TG_CHAT
  ۳) فایل‌های secrets توکن/چت
اگر هیچ‌کدام نبود، فقط در ترمینال چاپ می‌شود و ارسال انجام نمی‌شود.
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

UA = {"User-Agent": "Mozilla/5.0 (pump-radar/6.0)", "Accept": "application/json"}
STATE = os.environ.get("PUMP_STATE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "pump_radar_state.json")

GT = "https://api.geckoterminal.com/api/v2"
CG = "https://api.coingecko.com/api/v3"
DS = "https://api.dexscreener.com"
RC = "https://api.rugcheck.xyz/v1"

# ── فیلترهای سخت (رد شود ⇒ ردیف کاملاً حذف می‌شود) ──────────────────────
MIN_LIQ = 50_000        # نقدینگی کمتر از این ⇒ اصلاً لیست نشود
MIN_AGE_MIN = 20.0      # استخر تازه‌تر از ۲۰ دقیقه ⇒ نویز محض
MIN_V24 = 20_000        # حجم ۲۴ ساعته کمتر از این ⇒ بازار مرده
MIN_TX5 = 8             # کمتر از ۸ تراکنش در ۵ دقیقه ⇒ نمونهٔ آماری بی‌معنی
MIN_V5_USD = 500        # حجم ۵ دقیقه باید مبلغ واقعی باشد، نه ۳ دلار
MIN_TRADE_USD = 8.0     # میانگین هر تراکنش کمتر از این ⇒ استخر بات‌زده

# ── طبقه‌های ارسال (داخل اسکریپت اعمال می‌شود، نه در workflow) ───────────
MIN_SEND_FLOOR = 55     # طبقهٔ ۱: سیگنال (🚀) — کف مطلق ارسال
WATCH_FLOOR = 48        # طبقهٔ ۲: زیر نظر (👀)
WATCH_MAX = 5           # حداکثر آیتم «زیر نظر» در هر پیام
PRESIGNAL_FLOOR = 40    # طبقهٔ ۳: پیش‌سیگنال (⚡) — 0 = خاموش
PRE_RVOL5 = 1.8
PRE_P5_MIN = 0.8
PRE_P5_MAX = 22.0
PRE_MIN_LIQ = 50_000
PRE_AGE_MIN = 20.0
PRE_MAX = 6
PRE_DEDUPE_H = 2.0

# ── آستانه‌های اختصاصی طبقهٔ سیگنال (fix #4) ─────────────────────────────
# چک‌لیست قبلی هیچ کف قیمتی نداشت؛ نتیجه: استخری با انفجار حجم و قیمت ۰٪
# می‌توانست «🚀 سیگنال» بگیرد در حالی که هیچ حرکتی شروع نشده بود.
SIG_P5_MIN = 0.5        # سیگنال باید حداقل این‌قدر حرکت قیمت ۵دقیقه‌ای داشته باشد
SIG_P5_MAX = 25.0       # بالاتر از این ⇒ دم قطار
SIG_RVOL5_MIN = 1.5     # کف نسبت حجم برای سیگنال
SIG_TOP_24H_MAX = 100.0 # ۲۴ساعته بالاتر از این ⇒ ارسال نمی‌شود

# ── افت نقدینگی ──────────────────────────────────────────────────────────
RUG_DROP_PCT = 35.0     # افت بیش از این بین دو اجرا ⇒ حذف (راگ محتمل)
RUG_WARN_PCT = 18.0     # افت بیش از این ⇒ جریمه + هشدار ریسک
RUG_LOOKBACK_H = 6.0    # حداکثر فاصلهٔ مجاز با رکورد قبلی برای مقایسه

# ── اسکن ────────────────────────────────────────────────────────────────
EARLY_V5_USD = 1_500
EARLY_SCAN_PAGES = 3
LATE_P5 = 18.0

# ── RugCheck (fix #7) ───────────────────────────────────────────────────
# نام‌های ریسکی که اگر RugCheck گزارش کند، ارسال بلاک می‌شود.
RUG_BLOCK_IF_RISK_NAMES = ("mint authority", "freeze authority", "transfer fee",
                           "honeypot", "cannot sell", "non-transferable")
RUG_BLOCK_SCORE = 50_000   # score خام RugCheck بالاتر از این ⇒ بلاک (عدد بزرگ = ریسک بالا)

# ── رژیم بازار (fix #9) ─────────────────────────────────────────────────
UNKNOWN_ALLOW_SEND = False  # پیش‌فرض: اگر رژیم را نتوانستیم تعیین کنیم، ارسال نکن

# ── برچسب سن استخر (fix #10) ───────────────────────────────────────────
# سقف سن: استخر کهنه‌تر از این از رادار حذف می‌شود (با دلیل شفاف، نه سکوت).
# پیش‌فرض ۳۰ روز. برای بی‌سقف کردن: --max-age-days 0
MAX_AGE_FOR_RADAR_MIN = 43200.0   # 43200 دقیقه = ۳۰ روز
NO_CANDLES = False   # با --no-candles روشن می‌شود: هیچ درخواست OHLCV نمی‌رود


# ═══════════════════════════════════════════════════════════ ابزار پایه
def _mask(s):
    """پوشاندن توکن/کلید در لاگ‌ها تا در لاگ عمومی GitHub لو نرود (fix #10)."""
    s = str(s)
    s = re.sub(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b", "<BOT_TOKEN>", s)
    s = re.sub(r"\b[A-Za-z0-9_-]{30,}\b", "<SECRET>", s)
    return s


def _log_err(msg):
    print("[err]", _mask(msg), file=sys.stderr)


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
    """برچسب مارکت‌کپ: اگر mc نامعلوم/صفر بود از FDV استفاده کن (با ذکر نامش)."""
    mc = nz(r.get("mc")) if r.get("mc") is not None else 0.0
    if mc > 0:
        return f"${mc:,.0f}"
    if nz(r.get("fdv")) > 0:
        return f"FDV ${nz(r.get('fdv')):,.0f}"
    return "نامعلوم"


def age_minutes(r):
    """سن استخر بر حسب دقیقه، یا None اگر تاریخ ساخت نداشتیم (fix #2)."""
    t = parse_dt(r.get("created"))
    if not t:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 60.0


def age_label(am):
    """برچسب خوانا برای سن استخر (fix #10) — جای چاپ «684636د»."""
    if am is None:
        return "سن نامعلوم"
    if am < 90:
        return f"{am:.0f} دقیقه"
    if am < 48 * 60:
        return f"{am / 60.0:.1f} ساعت"
    return f"{am / 1440.0:.1f} روز"


def fmt_usd(v):
    v = nz(v)
    if v <= 0:
        return "?"
    if v >= 1_000_000_000:
        return f"${v / 1e9:.2f}B"
    if v >= 1_000_000:
        return f"${v / 1e6:.1f}M"
    if v >= 1_000:
        return f"${v / 1e3:.0f}K"
    return f"${v:.0f}"


# ═══════════════════════════════════════════════════════════ رژیم کلان
def regime():
    """امتیاز ۰..۵ برای «آیا امروز روز ریسک است؟». allow = ورودیِ واحدِ دروازهٔ ارسال."""
    out = {"verdict": "UNKNOWN", "score": 0, "notes": [], "allow": None,
           "sources_ok": 0}
    btc = _get(f"{CG}/simple/price?ids=bitcoin&vs_currencies=usd"
               f"&include_24hr_change=true&include_7d_change=true")
    if btc and "bitcoin" in btc:
        out["sources_ok"] += 1
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
    glob = _get(f"{CG}/global")
    if glob and "data" in glob:
        out["sources_ok"] += 1
        d = glob["data"]
        dom = nz(d.get("market_cap_percentage", {}).get("btc"))
        mc24 = nz(d.get("market_cap_change_percentage_24h_usd"))
        out["btc_dom"] = round(dom, 2)
        out["total_mcap_24h"] = round(mc24, 2)
        if 0 < dom < 55:
            out["score"] += 2
            out["notes"].append("دامیننس BTC پایین (پول در آلت‌ها)")
        elif dom > 0:
            out["notes"].append("دامیننس BTC بالا (پول پنهان در BTC)")
        if mc24 > 1:
            out["score"] += 1
        elif mc24 < -2:
            out["notes"].append("مارکت‌کپ کل نزولی")
    fng = _get("https://api.alternative.me/fng/?limit=1")
    try:
        v = int(fng["data"][0]["value"])
        out["sources_ok"] += 1
        out["fear_greed"] = v
        out["fear_greed_txt"] = fng["data"][0]["value_classification"]
        if v >= 60:
            out["score"] += 1
    except Exception:
        pass

    # اگر هیچ منبعی جواب نداد، رژیم «نامعلوم» است (نه RISK-OFF و نه RISK-ON).
    if out["sources_ok"] == 0:
        out["verdict"] = "UNKNOWN -> دادهٔ کلان در دسترس نیست"
        out["allow"] = None
        return out

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
                         "mc": a.get("market_cap_usd"),   # خام: None = نامعلوم
                         "price": nz(a.get("base_token_price_usd")),
                         "pc": a.get("price_change_percentage", {}) or {},
                         "tx": a.get("transactions", {}) or {},
                         "vol": a.get("volume_usd", {}) or {},
                         "reserve": nz(a.get("reserve_in_usd")),
                         "dex": ((rel.get("dex") or {}).get("data") or {}).get("id", ""),
                         "src": f"gt_{kind}"})
        time.sleep(0.8)
    return rows


def ds_token_pairs(chain, addr):
    if not addr:
        return []
    d = _get(f"{DS}/latest/dex/tokens/{addr}")
    if not d:
        return []
    return [p for p in (d.get("pairs") or []) if p.get("chainId") == chain]


def ds_pair_for_pool(chain, addr, pool):
    """جفت‌کردن دقیق (fix #6): باید هم chainId و هم pairAddress بخورد.

    قبلاً فقط chainId چک می‌شد و pr[0] برداشته می‌شد؛ اگر یک توکن چند استخر
    داشتیم، دادهٔ استخر اشتباه روی ردیف ما می‌نشست.
    """
    if not pool:
        return None
    for p in ds_token_pairs(chain, addr):
        if str(p.get("pairAddress") or "").lower() == str(pool).lower():
            return p
    return None


def candle_baseline(chain, pool):
    """baseline حجم ۵دقیقه از کندل‌های واقعی GT (fix #2).

    برمی‌گرداند dict با کلیدهای: ok, avg5, n, reason.
    از ۱۲ کندل قبلی (نه کندل جاری) میانگین می‌گیریم؛ حداقل ۴ کندل معتبر لازم است.
    """
    out = {"ok": False, "avg5": 0.0, "n": 0, "reason": "no_data"}
    if not chain or not pool:
        return out
    d = _get(f"{GT}/networks/{chain}/pools/{pool}/ohlcv/minute"
             f"?aggregate=5&limit=13", tries=2)
    lst = (d or {}).get("data", {}).get("attributes", {}).get("ohlcv_list") or []
    if not lst:
        out["reason"] = "no_candles"
        return out
    # جدیدترین کندل اول است ⇒ کندل ۰ جاری است و در baseline نمی‌آید
    prev = lst[1:]
    vols = [nz(c[5]) for c in prev if isinstance(c, (list, tuple)) and len(c) >= 6]
    vols = [v for v in vols if v > 0]
    if len(vols) < 4:
        out["reason"] = "history_too_short"
        out["n"] = len(vols)
        return out
    out["avg5"] = sum(vols) / len(vols)
    out["n"] = len(vols)
    out["ok"] = out["avg5"] > 0
    out["reason"] = "ok" if out["ok"] else "zero_prior_volume"
    return out


def volume_ratios(r, use_candles=True):
    """rvol5/rvol1h با baseline معتبر. اگر baseline نبود ⇒ None (fix #2).

    ترتیب اولویت:
      ۱) کندل‌های واقعی GT (دقیق‌ترین)
      ۲) تخمین از حجم عمر استخر، فقط اگر سن معلوم و سابقهٔ کافی باشد
      ۳) هیچ‌کدام ⇒ rvol5 = None و دلیلش ذخیره می‌شود
    """
    vol = r.get("vol") or {}
    v5 = nz(vol.get("m5"))
    v1h = nz(vol.get("h1"))
    v6h = nz(vol.get("h6"))
    v24 = nz(vol.get("h24"))

    am = age_minutes(r)
    age_h = None if am is None else min(max(am / 60.0, 5.0 / 60.0), 24.0)

    basis, reason = "none", "age_unknown"
    avg5 = 0.0

    if use_candles:
        cb = candle_baseline(r.get("chain"), r.get("pool"))
        if cb["ok"]:
            avg5 = cb["avg5"]
            basis, reason = "candles", "ok"

    if basis == "none" and age_h is not None:
        life_v = max(v24, v6h, v1h, v5)
        prior_v = max(life_v - v5, 0.0)
        prior_h = max(age_h - 5.0 / 60.0, 0.0)
        if prior_h >= 0.15 and prior_v > 0:
            avg5 = (prior_v / prior_h) / 12.0
            basis, reason = "prior", "ok"
        else:
            # fix #2: اگر سابقهٔ «قبل از پنجرهٔ ۵ دقیقه» نداشته باشیم، تقسیم حجم
            # عمر بر سن، فقط همان v5 را بر ۱۲ تقسیم می‌کند و rvol5 ثابت ۱٫۲
            # می‌سازد. این عدد ساختگی است، پس هیچ baseline نمی‌سازیم.
            reason = "zero_prior_volume"

    rvol5 = None
    rvol1h = None
    if avg5 > 0:
        rvol5 = min(v5 / avg5, 60.0)
        if basis == "candles":
            # برای rvol1h فقط تخمین از حجم عمر، چون ۱۲ کندل ۵دقیقه‌ای = ۱ ساعت
            avg_h = (sum(nz(c[5]) for c in _candles_cache.get(
                (r.get("chain"), r.get("pool")), []) if nz(c[5]) > 0) or 0.0)
            if avg_h <= 0:
                avg_h = avg5 * 12.0
            rvol1h = min(v1h / avg_h, 60.0) if avg_h > 0 else None
        else:
            avg_h = avg5 * 12.0
            rvol1h = min(v1h / avg_h, 60.0)

    return {"v5": v5, "v1h": v1h, "v6h": v6h, "v24": v24,
            "age_min": am, "age_h": age_h, "age_known": am is not None,
            "avg5": avg5, "rvol5": rvol5, "rvol1h": rvol1h,
            "rvol5_source": basis, "rvol5_reason": reason,
            "history_n": _candles_n.get((r.get("chain"), r.get("pool")), 0)}


_candles_cache = {}
_candles_n = {}


def _prime_candles(rows):
    """یک‌بار کندل‌ها را می‌گیریم و هم برای baseline و هم برای rvol1h استفاده می‌کنیم."""
    _candles_cache.clear()
    if NO_CANDLES:
        _candles_n.clear()
        return
    _candles_n.clear()
    for r in rows:
        key = (r.get("chain"), r.get("pool"))
        if not all(key) or key in _candles_cache:
            continue
        d = _get(f"{GT}/networks/{key[0]}/pools/{key[1]}/ohlcv/minute"
                 f"?aggregate=5&limit=13", tries=2)
        lst = ((d or {}).get("data", {}) or {}).get("attributes", {}).get(
            "ohlcv_list") or []
        _candles_cache[key] = lst
        vols = [nz(c[5]) for c in lst[1:] if len(c) >= 6 and nz(c[5]) > 0]
        _candles_n[key] = len(vols)


# ═══════════════════════════════════════════════════════════ هستهٔ امتیازدهی
def pump_score(r):
    """امتیاز ۰..۱۰۰ برای «فعالیت غیرعادی همین حالا». دلایل و ریسک‌ها هم برمی‌گردد."""
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
    rvol5 = vr["rvol5"]           # می‌تواند None باشد (fix #2)
    rvol1h = vr["rvol1h"]
    am = vr["age_min"]
    trades5 = b5 + s5

    # ── فیلترهای سخت ────────────────────────────────────────────────
    drop = []
    if liq < MIN_LIQ:
        drop.append(f"نقدینگی {fmt_usd(liq)} زیر کف {fmt_usd(MIN_LIQ)}")
    if am is not None and am < MIN_AGE_MIN:
        drop.append(f"سن {age_label(am)} (زیر {age_label(MIN_AGE_MIN)})")
    if v24 < MIN_V24:
        drop.append(f"حجم ۲۴ساعته {fmt_usd(v24)} (بازار مرده)")
    if trades5 < MIN_TX5:
        drop.append(f"فقط {trades5:.0f} تراکنش در ۵ دقیقه")
    if MAX_AGE_FOR_RADAR_MIN and am is not None and am > MAX_AGE_FOR_RADAR_MIN:
        drop.append(f"سن {age_label(am)} از سقف رادار گذشته")
    per_tr = v5 / max(trades5, 1.0) if trades5 > 0 else 0.0
    if trades5 >= MIN_TX5 and v5 < MIN_V5_USD:
        drop.append(f"حجم ۵دقیقه فقط {fmt_usd(v5)} (زیر کف {fmt_usd(MIN_V5_USD)})")
    elif trades5 >= MIN_TX5 and per_tr < MIN_TRADE_USD:
        drop.append(f"میانگین هر تراکنش {fmt_usd(per_tr)} (استخر بات‌زده)")

    r["dropped"] = bool(drop)
    r["drop_reasons"] = drop
    if drop:
        r["score"] = 0
        r["reasons"] = ["فیلتر سخت رد شد"]
        r["risks"] = drop
        r["sendable"] = False
        r["send_block"] = drop[:]
        return r

    # ── A) انفجار حجم ۵ دقیقه‌ای  (۰..۲۸) ────────────────────────────
    r["spike5"] = round(rvol5, 2) if rvol5 is not None else None
    if rvol5 is None:
        risks.append("baseline حجم معتبر نبود (" + vr["rvol5_reason"] +
                     ") ⇒ امتیاز انفجار حجم داده نشد")
    else:
        if rvol5 >= 8:
            s += 28
            reasons.append(f"انفجار حجم ۵دقیقه‌ای ×{rvol5:.1f} ({_src_fa(vr)})")
        elif rvol5 >= 5:
            s += 22
            reasons.append(f"جهش حجم ۵دقیقه‌ای ×{rvol5:.1f} ({_src_fa(vr)})")
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
    if am is not None and am >= 90 and rvol1h and rvol1h > 0:
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
    if trades5 > 0:
        ratio = b5 / max(s5, 1.0)
        r["buy_ratio5"] = round(ratio, 2)
        if (trades5 >= 10 and v5 >= 300 and b5 >= 8 and s5 >= 3
                and (rvol5 or 0) >= 1.0 and per_tr >= 50):
            if ratio >= 3 and b5 >= 12:
                s += 16
                reasons.append(f"فشار خرید ۵دقیقه‌ای {ratio:.1f}× (خریدار غالب)")
            elif ratio >= 1.5:
                s += 9
                reasons.append(f"خرید ۵دقیقه‌ای {ratio:.1f}× فروش")
            elif ratio <= 0.6 and s5 >= 10:
                s -= 12
                risks.append("فروشنده غالب در ۵ دقیقهٔ اخیر")
        elif trades5 >= 10 and (v5 < 300 or (rvol5 or 0) < 1.0):
            risks.append("حجم ۵دقیقه‌ای برای سنجش فشار خرید کافی نیست")
    if b1 + s1 > 0 and vr["v1h"] >= 2_000 and b1 >= 8 and s1 >= 3:
        r1 = b1 / max(s1, 1.0)
        if r1 >= 1.4:
            s += 6
            reasons.append(f"فشار خرید ۱ساعته {r1:.1f}×")

    # ── D) سرعت انباشت پول  (۰..۱۰) ────────────────────────────────
    r["usd_per_trade5"] = round(per_tr, 1)
    already_fined = any("ربات/واش‌تریدینگ" in x for x in risks)
    if trades5 >= 5:
        if per_tr >= 2000:
            s += 10
            reasons.append(f"پول درشت با تراکنش کم ({fmt_usd(per_tr)} هر تراکنش)")
        elif per_tr <= 50 and not already_fined:
            s -= 6
            risks.append(f"تریدهای ریز و رباتیک ({fmt_usd(per_tr)} هر تراکنش)")

    # ── E) کیفیت نقدینگی  (۰..۱۴) ──────────────────────────────────
    if liq >= 1_000_000:
        s += 12
        reasons.append(f"نقدینگی {fmt_usd(liq)} (خروج آسان)")
    elif liq >= 300_000:
        s += 9
        reasons.append(f"نقدینگی {fmt_usd(liq)} قابل قبول")
    elif liq >= 150_000:
        s += 5
        reasons.append(f"نقدینگی {fmt_usd(liq)} حداقلی")
    else:
        s += 1
        risks.append(f"نقدینگی فقط {fmt_usd(liq)} (کف عبور کرد ولی نازک)")

    cap = mc if mc > 0 else fdv
    if cap > 0:
        lm = liq / cap
        r["liq_to_cap"] = round(lm, 3)
        if lm >= 0.15:
            s += 6
            reasons.append(f"نقدینگی {lm * 100:.0f}٪ مارکت‌کپ (پشتوانهٔ واقعی)")
        elif lm < 0.03:
            s -= 8
            risks.append(f"نقدینگی فقط {lm * 100:.1f}٪ مارکت‌کپ (حباب نمایشی)")
    if liq > 0 and v24 > 0:
        turn = v24 / liq
        r["turnover24"] = round(turn, 2)
        if 2 <= turn <= 15:
            s += 5
            reasons.append(f"چرخش ۲۴ساعته {turn:.1f}× نقدینگی")
        elif turn > 40:
            s -= 10
            risks.append(f"چرخش {turn:.0f}× نقدینگی (احتمال واش/چرن)")

    # ── F) هنوز بالا نرفته باشد (جا برای حرکت)  (۰..۱۲) ─────────────
    if p5 >= 0.2:
        if p5 <= 6:
            s += 10
            reasons.append(f"قیمت ۵دقیقه‌ای {p5:+.1f}% (منطقهٔ شروع)")
        elif p5 <= 15:
            s += 9
            reasons.append(f"۵دقیقه‌ای {p5:+.1f}% (شروع حرکت)")
        elif p5 <= LATE_P5:
            s += 5
            reasons.append(f"۵دقیقه‌ای {p5:+.1f}% (در جریان)")
        elif p5 > 40:
            s -= 12
            risks.append(f"۵دقیقه‌ای {p5:+.0f}% (دم قطار - دیر شده)")
    if p1h > 40:
        s -= 6
        risks.append(f"یک‌ساعته {p1h:+.0f}% (بیش از حد کشیده)")
    if p24 > SIG_TOP_24H_MAX:
        s -= 20
        risks.append(f"۲۴ساعته {p24:+.0f}% (بالای سقف ارسال)")
    elif 0 < p24 <= 60:
        s += 6
        reasons.append(f"۲۴ساعته {p24:+.0f}% (حرکت تازه)")

    # ── G) مارکت‌کپ ────────────────────────────────────────────────
    if mc_raw is None or nz(mc_raw) <= 0:
        risks.append("مارکت‌کپ در API نبود — با FDV سنجیده شد")
    if cap > 0:
        if 1_000_000 <= cap <= 50_000_000:
            s += 6
            reasons.append("مارکت‌کپ در محدودهٔ مستعد حرکت (۱M–۵۰M دلار)")
        elif cap < 300_000:
            s -= 8
            risks.append("مارکت‌کپ زیر ۳۰۰K دلار (نازک و شکننده)")

    # ── H) سن استخر ────────────────────────────────────────────────
    # اصلاح: «پاداش سالمندی» حذف شد. اینکه پروژه ۴۷۵ روز عمر کرده دلیل
    # «شروع حرکت» نیست و در v5 به استخرهای بالای ۳۰ روز ۵ امتیاز رایگان
    # می‌داد (همان چیزی که در یک سیگنال واقعی دیده شد).
    if am is not None:
        r["age_days"] = round(am / 1440.0, 3)
        if am < 120:
            if (rvol5 or 0) >= 3 and v5 >= EARLY_V5_USD:
                s += 4
                reasons.append("استخر تازه + حجم واقعی (در حال شکل‌گیری)")
            else:
                s -= 4
                risks.append("کمتر از ۲ ساعت سن (ریسک آتش‌بازی لحظه‌ای)")
        elif am < 1440:
            s += 2
            reasons.append("سن ۲ تا ۲۴ ساعت")
        elif am < 4320:
            s += 2
            reasons.append("سن ۱ تا ۳ روز")
        # بالای ۳ روز: بدون پاداش. سن کهنه نه مزیت است نه جریمه.
    else:
        risks.append("سن استخر نامعلوم ⇒ rvol5 محاسبه نشد")

    r["score"] = int(max(0, min(100, round(s))))
    r["reasons"] = reasons or ["هیچ نشانهٔ فعالیت غیرعادی نیست"]
    r["risks"] = risks

    checks = {
        "نقدینگی کافی": liq >= MIN_LIQ,
        "سن معلوم و ≥ ۲۰ دقیقه": (am is not None and am >= MIN_AGE_MIN),
        "rvol5 معتبر و ≥ ۲": (rvol5 is not None and rvol5 >= 2),
        "خرید/فروش ۵دقیقه ≥ ۱.۲": (s5 >= 3 and (b5 / max(s5, 1.0)) >= 1.2),
        "۲۴ساعته ≤ +۱۰۰٪": p24 <= SIG_TOP_24H_MAX,
    }
    r["checks"] = checks
    ok = all(checks.values())
    r["sendable"] = ok
    r["send_block"] = [] if ok else [k for k, v in checks.items() if not v]
    return r


def _src_fa(vr):
    m = {"candles": "پایه: کندل‌های واقعی",
         "prior": "پایه: تخمین از عمر استخر",
         "lifetime": "پایه: حجم کل عمر"}
    return m.get(vr.get("rvol5_source"), "پایه: نامعلوم")


# ═══════════════════════════════════════════════════════════ دروازه‌های ایمنی
def safety_ok(r):
    """دروازهٔ ایمنی مشترک همهٔ طبقه‌ها (fix #4).

    ورودی: ردیف امتیازدهی‌شده.
    خروجی: (بولین, لیست دلایل مسدودیت)
    قواعد:
      • ردیف حذف‌شده (فیلتر سخت یا افت نقدینگی) هرگز ارسال نمی‌شود.
      • دادهٔ نامعتبر (rvol5 نامعلوم) نمی‌تواند سیگنال باشد.
      • RugCheck اگر ریسک بلاک‌کننده گزارش کند ⇒ مسدود.
    """
    why = []
    if r.get("dropped"):
        why.append("فیلتر سخت/افت نقدینگی")
    if r.get("rug_dropped"):
        why.append("افت نقدینگی")
    if not r.get("sendable"):
        why.extend(r.get("send_block") or ["چک‌لیست کامل نشد"])
    rg = r.get("rugcheck") or {}
    if rg.get("status") in ("blocked",):
        why.append("RugCheck: ریسک بلاک‌کننده")
    # fix #2: سن نامعلوم / rvol5 نامعلوم ⇒ دادهٔ نامعتبر، نه سیگنال.
    am = r.get("age_min")
    if am is None:
        am = age_minutes(r)
    if am is None:
        why.append("سن استخر نامعلوم")
    if r.get("rvol5") is None:
        why.append("نسبت حجم (rvol5) نامعلوم")
    if not why and MAX_AGE_FOR_RADAR_MIN:
        am = r.get("age_min")
        if am is not None and am > MAX_AGE_FOR_RADAR_MIN:
            why.append("سن بالاتر از سقف رادار")
    return (len(why) == 0), why


def sig_ok(r):
    """شرایط اختصاصی طبقهٔ 🚀 (fix #4): باید حرکت شروع شده باشد، نه فقط حجم."""
    ok, why = safety_ok(r)
    if not ok:
        return False, why
    p5 = nz((r.get("pc") or {}).get("m5"))
    rvol5 = r.get("rvol5")
    if rvol5 is None:
        return False, ["rvol5 نامعلوم"]
    if rvol5 < SIG_RVOL5_MIN:
        return False, [f"rvol5 زیر {SIG_RVOL5_MIN}"]
    if p5 < SIG_P5_MIN:
        return False, [f"قیمت ۵دقیقه‌ای زیر {SIG_P5_MIN}% (حرکت شروع نشده)"]
    if p5 > SIG_P5_MAX:
        return False, [f"قیمت ۵دقیقه‌ای بالای {SIG_P5_MAX}% (دیر شده)"]
    return True, []


def presignal_ok(r):
    """شرایط «در حال بیدار شدن». برمی‌گرداند (بولین، لیست دلایل رد)."""
    ok, why = safety_ok(r)
    if not ok:
        return False, why
    if nz(r.get("reserve")) < PRE_MIN_LIQ:
        return False, ["نقدینگی کم"]
    rvol5 = r.get("rvol5")
    if rvol5 is None:
        return False, ["rvol5 نامعلوم"]
    if rvol5 < PRE_RVOL5:
        return False, ["حجم منفجر نشده"]
    p5 = nz((r.get("pc") or {}).get("m5"))
    if p5 < PRE_P5_MIN:
        return False, ["قیمت حرکت نکرده"]
    if p5 > PRE_P5_MAX:
        return False, ["دیر شده"]
    am = r.get("age_min")
    if am is None:
        return False, ["سن نامعلوم"]
    if am < PRE_AGE_MIN:
        return False, ["استخر خیلی تازه"]
    return True, []


# ═══════════════════════════════════════════════════════════ RugCheck (fix #7)
def rugcheck(addr):
    """وضعیت RugCheck. نبود پاسخ ≠ سالم (fix #7)."""
    if not addr:
        return {"status": "unchecked", "risks": [], "score": None,
                "norm": None, "lp_locked": None,
                "note": "آدرس توکن خالی بود"}
    d = _get(f"{RC}/tokens/{addr}/report/summary", tries=1)
    if not isinstance(d, dict):
        return {"status": "failed", "risks": [], "score": None,
                "norm": None, "lp_locked": None,
                "note": "پاسخ RugCheck نیامد (سالم فرض نمی‌شود)"}
    risks = d.get("risks") or []
    names = []
    for x in risks[:6]:
        if isinstance(x, dict):
            nm = str(x.get("name") or "")[:40]
            if nm:
                names.append(nm)
        elif isinstance(x, str):
            names.append(x[:40])
    sc = d.get("score")
    sc = nz(sc) if sc is not None else None
    low = [n.lower() for n in names]
    blocked = any(any(k in n for k in RUG_BLOCK_IF_RISK_NAMES) for n in low)
    if sc is not None and sc >= RUG_BLOCK_SCORE:
        blocked = True
    if blocked:
        status = "blocked"
    elif names:
        status = "ok_with_warnings"
    else:
        status = "clean"
    return {"status": status, "risks": names, "score": sc,
            "norm": nz(d.get("score_normalised")),
            "lp_locked": nz(d.get("lpLockedPct")), "note": ""}


# ═══════════════════════════════════════════════════════════ وضعیت/حافظه
def load_state():
    if not os.path.exists(STATE):
        return {}
    try:
        with open(STATE) as f:
            return json.load(f) or {}
    except Exception as e:
        _log_err(f"state read: {e}")
        return {}


def save_state(state):
    """ذخیرهٔ اتمیک (fix #5): نوشتن در فایل موقت سپس os.replace."""
    tmp = STATE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(state, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, STATE)
    except Exception as e:
        _log_err(f"state write: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════ اجرا
def collect(chains):
    pools = []
    for c in chains:
        pools += gt_pools(c, "trending", pages=EARLY_SCAN_PAGES)
        pools += gt_pools(c, "new", pages=2)
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

    # اگر دادهٔ حجم نداشت، از DexScreener کامل کن — با جفت‌کردن دقیق استخر (fix #6)
    for p in uniq:
        if not p.get("vol"):
            x = ds_pair_for_pool(p["chain"], p.get("base_token"), p.get("pool"))
            if x:
                p["reserve"] = nz(x.get("liquidity", {}).get("usd"), p.get("reserve"))
                if p.get("mc") is None:
                    p["mc"] = x.get("marketCap")
                p["vol"] = {"h24": nz(x.get("volume", {}).get("h24")),
                            "h6": nz(x.get("volume", {}).get("h6")),
                            "h1": nz(x.get("volume", {}).get("h1")),
                            "m5": nz(x.get("volume", {}).get("m5"))}
                p["pc"] = x.get("priceChange") or {}
                p["tx"] = x.get("txns") or {}
                p["ds_matched"] = True
            time.sleep(0.4)

    _prime_candles(uniq)

    scored = [pump_score(p) for p in uniq]
    dropped = [r for r in scored if r.get("dropped")]
    alive = [r for r in scored if not r.get("dropped") and r["score"] > 0]
    alive.sort(key=lambda r: r["score"], reverse=True)

    if min_score:
        alive = [r for r in alive if r["score"] >= min_score]

    st = load_state()
    prev, prev_liq_hist = {}, {}
    for x in (st.get("rows") or []):
        kk = f"{x.get('chain')}|{x.get('pool')}"
        prev[kk] = x.get("score", 0)
    hist = st.get("liq_hist") or {}
    for kk, arr in hist.items():
        if arr:
            last = arr[-1]
            if isinstance(last, (list, tuple)) and len(last) >= 2:
                prev_liq_hist[kk] = (nz(last[1]), parse_dt(last[0]))

    now = datetime.now(timezone.utc)

    # ── دروازهٔ افت نقدینگی ─────────────────────────────────────────
    for r in alive + dropped:
        kk = f"{r.get('chain')}|{r.get('pool')}"
        pl = prev_liq_hist.get(kk)
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
                f"نقدینگی {drop:.0f}٪ آب رفت (از {fmt_usd(old_liq)} به "
                f"{fmt_usd(liq_now)}) → نشانهٔ راگ / کشیدن LP"]
            r["risks"] = r["drop_reasons"]
            r["reasons"] = ["حذف شد: افت نقدینگی"]
        elif drop >= RUG_WARN_PCT:
            r["score"] = int(max(0, r["score"] - 15))
            r["risks"].append(
                f"ریسک: نقدینگی {drop:.0f}٪ کم شده (از {fmt_usd(old_liq)} به "
                f"{fmt_usd(liq_now)})")

    alive = [r for r in alive if not r.get("dropped") and r["score"] > 0]
    if min_score:
        alive = [r for r in alive if r["score"] >= min_score]
    alive.sort(key=lambda r: r["score"], reverse=True)
    rug_dropped = [r for r in dropped if r.get("rug_dropped")]
    rug_warned = [r for r in alive if r.get("liq_drop_pct", 0) >= RUG_WARN_PCT]

    sent = {}
    for k, iso in (st.get("sent") or {}).items():
        t = parse_dt(iso)
        if t and (now - t).total_seconds() / 3600.0 <= dedupe_hours:
            sent[k] = iso
    pre_sent = {}
    for k, iso in (st.get("pre_sent") or {}).items():
        t = parse_dt(iso)
        if t and (now - t).total_seconds() / 3600.0 <= PRE_DEDUPE_H:
            pre_sent[k] = iso

    for r in alive:
        k = f"{r.get('chain')}|{r.get('pool')}"
        old = prev.get(k)
        if old is None:
            r["status"] = "🆕 وارد رادار شد"
            r["is_new"] = True
        elif r["score"] > old + 10:
            r["status"] = f"📈 صعودی (از {old} به {r['score']})"
        elif r["score"] < old - 10:
            r["status"] = f"📉 در حال خنک شدن (از {old})"
        else:
            r["status"] = "· پایدار"
        r["already_sent"] = k in sent
        r["pre_sent"] = k in pre_sent

    # fix #9: --new-only واقعاً فیلتر می‌کند (قبلاً فقط ترمینال را عوض می‌کرد)
    if new_only:
        alive = [r for r in alive if r.get("is_new")]

    alive.sort(key=lambda r: r["score"], reverse=True)
    top_rows = alive[:top]

    # ── RugCheck فقط برای کاندیدهای ارسال‌شدنی ───────────────────────
    if do_rugcheck:
        n = 0
        # fix #10: روی کل لیست کار می‌کند تا top‌شدن یک مورد نافرستادنی
        # باعث چشم‌پوشی از کاندیدهای واجد شرایط نشود.
        for r in alive:
            if n >= 6:
                break
            if r.get("already_sent"):
                continue
            if r.get("chain") != "solana":
                r["rugcheck"] = {"status": "not_solana", "risks": [], "score": None,
                                 "norm": None, "lp_locked": None, "note": ""}
                continue
            rc = rugcheck(r.get("base_token"))
            r["rugcheck"] = rc
            if rc.get("risks"):
                r["risks"].append("RugCheck: " + "، ".join(rc["risks"][:2]))
            if rc["status"] == "blocked":
                r["sendable"] = False
                r["send_block"] = (r.get("send_block") or []) + [
                    "RugCheck ریسک بلاک‌کننده گزارش کرد"]
            n += 1

    res = {"generated_utc": now.strftime("%Y-%m-%d %H:%M:%S"),
           "generated_iso": now.isoformat(),
           "regime": reg, "scanned_pools": len(uniq),
           "dropped_hard_filters": len([x for x in scored if x.get("dropped")]),
           "rug_dropped": [{"name": r.get("name"), "chain": r.get("chain"),
                            "pool": r.get("pool"), "drop": r.get("liq_drop_pct")}
                           for r in rug_dropped],
           "rug_warned": [{"name": r.get("name"), "chain": r.get("chain"),
                           "drop": r.get("liq_drop_pct")} for r in rug_warned],
           "rows": alive}          # fix #10: کل لیست، نه فقط top
    res["top_rows"] = top_rows

    # ── حافظه: rvol/liq برای همهٔ استخرهای دیده‌شده (نه فقط top) ─────
    new_hist = {}
    for r in scored:
        kk = f"{r.get('chain')}|{r.get('pool')}"
        liq = nz(r.get("reserve"))
        if liq <= 0:
            continue
        arr = list(hist.get(kk) or [])
        arr.append([now.isoformat(), round(liq, 2)])
        new_hist[kk] = arr[-8:]

    state = {"generated_utc": res["generated_utc"],
             "rows": [{"chain": r.get("chain"), "pool": r.get("pool"),
                       "score": r.get("score"),
                       "liq": r.get("reserve"),
                       "ts": res["generated_iso"]} for r in alive[:60]],
             "sent": sent,
             "pre_sent": pre_sent,
             "liq_hist": new_hist}
    save_state(state)
    res["_sent"] = sent
    res["_pre_sent"] = pre_sent

    if out_json:
        try:
            with open(out_json, "w") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
        except Exception as e:
            _log_err(f"json write: {e}")
    return res


# ═══════════════════════════════════════════════════════════ نمایش ترمینال
def show(res, limit=15):
    reg = res["regime"]
    print("=" * 78)
    print(f"رادار فعالیت غیرعادی میم‌کوین  ·  {res['generated_utc']} UTC  ·  "
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
        print(f"⚠️ هشدار ریسک نقدینگی: {w0.get('name')} [{w0.get('chain')}] "
              f"— {nz(w0.get('drop')):.0f}٪ کم شده (−۱۵ امتیاز)")
    if res.get("rug_dropped") or res.get("rug_warned"):
        print()
    rows = res.get("top_rows") or res["rows"][:limit]
    if not rows:
        print("🔴 هیچ توکنی از فیلترها و آستانهٔ امتیاز عبور نکرد. امروز روز تماشا است.")
        return
    n_hot = len([r for r in res["rows"] if r["score"] >= MIN_SEND_FLOOR])
    n_watch = len([r for r in res["rows"]
                   if WATCH_FLOOR <= r["score"] < MIN_SEND_FLOOR])
    print(f"🚀 سیگنال (≥{MIN_SEND_FLOOR}): {n_hot}   |   "
          f"👀 زیر نظر ({WATCH_FLOOR}–{MIN_SEND_FLOOR - 1}): {n_watch}")
    print()
    for i, r in enumerate(rows[:limit], 1):
        g = grade(r["score"])
        tier = ("🚀" if r["score"] >= MIN_SEND_FLOOR else
                ("👀" if r["score"] >= WATCH_FLOOR else
                 ("⚡" if r["score"] >= PRESIGNAL_FLOOR else "  ")))
        rv = r.get("rvol5")
        rv_txt = f"{rv:.2f}×" if rv is not None else "نامعلوم"
        print(f"{i:2d}. {tier} {r.get('name', '?')}  [{r.get('chain')}]  "
              f"score={r['score']} ({g})  {phase(r)}")
        print(f"    liq {fmt_usd(r.get('reserve'))} | mc {cap_label(r)}"
              f" | 24h {nz((r.get('pc') or {}).get('h24')):.1f}%"
              f" | 1h {nz((r.get('pc') or {}).get('h1')):.1f}%"
              f" | 5m {nz((r.get('pc') or {}).get('m5')):.1f}%")
        print(f"    rvol5 {rv_txt} ({r.get('rvol5_source')})"
              f" | سن {age_label(r.get('age_min'))}"
              f" | {fmt_usd(r.get('usd_per_trade5'))}/تراکنش")
        print(f"    وضعیت: {r.get('status', '·')}"
              f"{'  (قبلاً ارسال شده)' if r.get('already_sent') else ''}")
        for x in r["reasons"][:4]:
            print(f"      + {x}")
        for x in r["risks"][:3]:
            print(f"      - {x}")
        print()


def phase(r):
    sc = r.get("score", 0)
    sp = r.get("rvol5") or 0
    if sc >= 70 and sp >= 5:
        return "فعالیت غیرعادی شدید"
    if sc >= 55:
        return "بیدار شدن"
    if sc >= 40:
        return "زیر نظر"
    return "—"


def grade(sc):
    """نمرهٔ حرفی. توجه: این «احتمال موفقیت» نیست — فقط رتبهٔ نسبی است."""
    if sc >= 85:
        return "S"
    if sc >= 75:
        return "A"
    if sc >= 65:
        return "B"
    if sc >= 55:
        return "C"
    return "D"


# ═══════════════════════════════════════════════════════════ تلگرام
def split_html(text, limit=3800):
    """تقسیم متن HTML در مرز خط، با بستن/بازکردن تگ‌ها (fix #8).

    تلگرام سقف ۴۰۹۶ کاراکتر دارد و HTML ناقص را رد می‌کند. این تابع:
      ۱) خط‌به‌خط جلو می‌رود و هرجا از limit گذشت، تکه می‌کند؛
      ۲) تگ‌های بازِ هر تکه را در انتها می‌بندد و در تکهٔ بعد باز می‌کند.
    """
    if not text:
        return []
    lines = text.split("\n")
    tag_re = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)[^>]*?(/?)>")
    chunks, cur, open_tags = [], [], []
    cur_len = 0
    for ln in lines:
        add = len(ln) + 1
        if cur_len + add > limit and cur:
            closing = "".join(f"</{t}>" for t in reversed(open_tags))
            chunks.append("\n".join(cur) + closing)
            cur = []
            cur_len = 0
            if open_tags:
                reopen = "".join(f"<{t}>" for t in open_tags)
                cur.append(reopen)
                cur_len = len(reopen) + 1
        cur.append(ln)
        cur_len += add
        for m in tag_re.finditer(ln):
            name = m.group(1).lower()
            is_close = m.group(0).startswith("</")
            self_closing = m.group(2) == "/"
            if name in ("br", "hr") or self_closing:
                continue
            if is_close:
                if open_tags and open_tags[-1] == name:
                    open_tags.pop()
                elif name in open_tags:
                    open_tags.remove(name)
            else:
                open_tags.append(name)
    if cur:
        closing = "".join(f"</{t}>" for t in reversed(open_tags))
        chunks.append("\n".join(cur) + closing)
    return [c for c in chunks if c.strip()]


def notify_telegram(token, chat, text):
    """ارسال با تقسیم خودکار + مدیریت ۴۲۹. True فقط وقتی همهٔ تکه‌ها ارسال شد."""
    if not token or not chat:
        print("[telegram] توکن یا chat_id خالی است → ارسال انجام نشد")
        return False
    if re.search(r"\bsecret-[0-9a-f]{4,}\b", str(token)) or "secret-" in str(token):
        print("[telegram] مقدار توکن شبیه placeholder است (secret-...) → "
              "ارسال انجام نشد. توکن واقعی BotFather را در TG_TOKEN بگذارید.")
        return False
    ok_all = True
    for part in split_html(text):
        ok = _send_one(token, chat, part)
        if not ok:
            ok_all = False
            break
    return ok_all


def _send_one(token, chat, text, attempt=0):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({"chat_id": chat, "text": text,
                       "parse_mode": "HTML",
                       "disable_web_page_preview": True}).encode()
    try:
        req = urllib.request.Request(url, data=body,
                                     headers={**UA, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
            return bool(d.get("ok"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:300]
        except Exception:
            pass
        _log_err(f"telegram HTTP {e.code}: {detail}")
        if e.code == 429 and attempt < 2:
            wait = 3
            try:
                wait = int(json.loads(detail).get("parameters", {})
                           .get("retry_after", 3))
            except Exception:
                pass
            time.sleep(min(wait, 30) + 1)
            return _send_one(token, chat, text, attempt + 1)
        return False
    except Exception as e:
        _log_err(f"telegram: {e}")
        return False


# ═══════════════════════════════════════════════════════════ سیاست ارسال (fix #9)
def send_policy(reg, allow_risk_off=False, allow_unknown=False):
    """یک نقطهٔ واحد تصمیم. هم هدر پیام و هم دروازهٔ ارسال از همین می‌خوانند.

    خروجی dict با کلیدهای:
      allow_signal  : آیا طبقهٔ 🚀 مجاز است؟
      allow_soft    : آیا 👀 و ⚡ مجاز است؟
      reason_fa     : دلیل، برای چاپ در پیام (هیچ‌وقت با allow در تناقض نیست)
    """
    allow = reg.get("allow")
    if allow is True:
        return {"allow_signal": True, "allow_soft": True, "reason_fa": ""}
    if allow is False:
        if allow_risk_off:
            return {"allow_signal": True, "allow_soft": True,
                    "reason_fa": "RISK-OFF ولی با --allow-risk-off مجاز شد"}
        return {"allow_signal": False, "allow_soft": True,
                "reason_fa": "بازار منفی است — هیچ سیگنال خریدی صادر نشد"}
    # allow is None ⇒ رژیم نامعلوم
    if allow_unknown:
        return {"allow_signal": True, "allow_soft": True,
                "reason_fa": "رژیم نامعلوم ولی با --allow-unknown مجاز شد"}
    return {"allow_signal": False, "allow_soft": True,
            "reason_fa": "رژیم بازار نامعلوم است (دادهٔ کلان نیامد) — "
                         "سیگنال صادر نشد"}


def alert_text(res, min_send=MIN_SEND_FLOOR, allow_risk_off=False,
               watch_floor=WATCH_FLOOR, presignal_floor=PRESIGNAL_FLOOR,
               allow_unknown=UNKNOWN_ALLOW_SEND):
    """
    متن هشدار سه‌طبقه. تنها منبع تصمیم: send_policy().
    ترتیب: 🚀 سیگنال، ⚡ پیش‌سیگنال، 👀 زیر نظر.
    """
    reg = res["regime"]
    pol = send_policy(reg, allow_risk_off=allow_risk_off,
                      allow_unknown=allow_unknown)

    def ok(r):
        return safety_ok(r)[0] and not r.get("already_sent")

    # fix #9: دو طبقهٔ نرم مستقل‌اند.
    #   watch_floor == 0   ⇒ طبقهٔ 👀 خاموش
    #   presignal_floor==0 ⇒ طبقهٔ ⚡ خاموش
    # سقف ⚡ هرگز از کف 👀 بالاتر نمی‌رود (وگرنه دو طبقه روی هم می‌افتند).
    watch_on = bool(watch_floor) and watch_floor < min_send
    pre_top = (watch_floor - 1) if watch_on else (min_send - 1)
    pre_on = bool(presignal_floor) and presignal_floor <= pre_top

    hot = [r for r in res["rows"]
           if r["score"] >= min_send and ok(r) and sig_ok(r)[0]]
    if not pol["allow_signal"]:
        if hot:
            print(f"[gate] {reg['verdict']} → {len(hot)} سیگنال 🚀 سانسور شد")
        hot = []

    watch = []
    pre = []
    if pol["allow_soft"]:
        if watch_on:
            watch = [r for r in res["rows"]
                     if watch_floor <= r["score"] < min_send and ok(r)]
        if pre_on:
            pre = [r for r in res["rows"]
                   if presignal_floor <= r["score"] <= pre_top
                   and ok(r) and not r.get("pre_sent")
                   and presignal_ok(r)[0]]

    if not hot and not watch and not pre:
        best = max([r["score"] for r in res["rows"]], default=0)
        hb = [f"<b>🚨 رادار فعالیت غیرعادی</b>  "
              f"{res.get('generated_utc', '?')} UTC",
              f"رژیم: {html.escape(reg['verdict'])}", ""]
        if pol["reason_fa"]:
            hb.append(f"<b>🔴 توجه</b> — {html.escape(pol['reason_fa'])}")
        hb.append(f"💤 بیدارم — بالاترین امتیاز این اسکن: {best} "
                  f"(حداقل لازم {int(min_send)})")
        hb.append("")
        hb.append("❗️این پیام سیگنال نیست. تحقیق شخصی و حد ضرر اجباری.")
        return "\n".join(hb)

    L = [f"<b>🚨 رادار فعالیت غیرعادی</b>  "
         f"{res.get('generated_utc', '?')} UTC",
         f"رژیم: {html.escape(reg['verdict'])}", ""]
    if not pol["allow_signal"]:
        L.append(f"<b>🔴 {html.escape(pol['reason_fa'])}</b>")
        L.append("<i>فقط لیست «زیر نظر» برای اطلاع است.</i>")
        L.append("")

    keys = []
    rugs = res.get("rug_dropped") or []
    if rugs:
        L.append("<b>🛑 حذف‌شده به‌دلیل افت نقدینگی</b>")
        for d0 in rugs[:4]:
            L.append(f"  • {html.escape(str(d0.get('name')))} "
                     f"[{html.escape(str(d0.get('chain')))}] — "
                     f"نقدینگی {nz(d0.get('drop')):.0f}٪ آب رفت")
        L.append("")
    warns = res.get("rug_warned") or []
    if warns:
        L.append("<b>⚠️ هشدار ریسک نقدینگی</b>")
        for w0 in warns[:4]:
            L.append(f"  • {html.escape(str(w0.get('name')))} "
                     f"[{html.escape(str(w0.get('chain')))}] — "
                     f"نقدینگی {nz(w0.get('drop')):.0f}٪ کم شده")
        L.append("")

    if hot:
        L.append(f"<b>🚀 سیگنال ({len(hot)} مورد، امتیاز ≥{min_send})</b>")
        L.append("<i>امتیاز = شدت فعالیت غیرعادی. احتمال موفقیت نیست.</i>")
        L.append("")
        for r in hot[:5]:
            g = grade(r["score"])
            L.append(f"<b>{html.escape(str(r.get('name', '?')))}</b> "
                     f"[{html.escape(str(r.get('chain')))}] "
                     f"score={r['score']} ({g})")
            rv = r.get("rvol5")
            rv_txt = f"{rv:.1f}×" if rv is not None else "نامعلوم"
            L.append(f"  liq {fmt_usd(r.get('reserve'))} | mc {cap_label(r)}"
                     f" | 24h {nz((r.get('pc') or {}).get('h24')):.1f}%"
                     f" | rvol5 {rv_txt}"
                     f" | سن {age_label(r.get('age_min'))}")
            bt = r.get("base_token") or ""
            if bt:
                L.append(f"  <code>{html.escape(str(bt))}</code>")
            for x in r["reasons"][:3]:
                L.append(f"  ✅ {html.escape(str(x))}")
            for x in r["risks"][:2]:
                L.append(f"  ⚠️ {html.escape(str(x))}")
            rc = r.get("rugcheck") or {}
            if rc.get("risks"):
                L.append(f"  🛑 {html.escape(', '.join(rc['risks'][:2]))}")
            elif rc.get("status") in ("failed", "unchecked"):
                L.append("  ❔ RugCheck بررسی نشد (به‌معنای سالم بودن نیست)")
            L.append("")
            keys.append(f"{r.get('chain')}|{r.get('pool')}")

    if pre:
        L.append(f"<b>⚡ پیش‌سیگنال ({len(pre)} مورد، "
                 f"{presignal_floor}–{pre_top})</b>")
        L.append("  <i>در حال بیدار شدن — هنوز حرکت اصلی شروع نشده. "
                 "ورود نزن، فقط زیر نظر بگیر.</i>")
        for r in pre[:PRE_MAX]:
            p5 = nz((r.get("pc") or {}).get("m5"))
            rv = r.get("rvol5")
            rv_txt = f"{rv:.1f}×" if rv is not None else "نامعلوم"
            L.append(f"  • {html.escape(str(r.get('name', '?')))} "
                     f"[{html.escape(str(r.get('chain')))}] score={r['score']}"
                     f" | ۵د {p5:+.1f}% | rvol5 {rv_txt}"
                     f" | liq {fmt_usd(r.get('reserve'))}")
            bt = r.get("base_token") or ""
            if bt:
                L.append(f"    <code>{html.escape(str(bt))}</code>")
        L.append("")

    if watch:
        L.append(f"<b>👀 زیر نظر ({len(watch)} مورد، "
                 f"{watch_floor}–{min_send - 1})</b>")
        L.append("  <i>این‌ها سیگنال نیستند — فقط بیدار شدن. ورود نزن.</i>")
        for r in watch[:WATCH_MAX]:
            rv = r.get("rvol5")
            rv_txt = f"{rv:.1f}×" if rv is not None else "نامعلوم"
            L.append(f"  • {html.escape(str(r.get('name', '?')))} "
                     f"[{html.escape(str(r.get('chain')))}] "
                     f"score={r['score']} | rvol5 {rv_txt}"
                     f" | 24h {nz((r.get('pc') or {}).get('h24')):.0f}%"
                     f" | liq {fmt_usd(r.get('reserve'))}")
        L.append("")

    L.append("❗️این پیام سیگنال خرید نیست. تحقیق شخصی و حد ضرر اجباری. "
             "حداکثر ۲٪ سرمایه.")
    res["_hot_keys"] = keys
    res["_pre_keys"] = [f"{r.get('chain')}|{r.get('pool')}"
                        for r in pre[:PRE_MAX]]
    return "\n".join(L)


def mark_sent(res):
    # fix #5: کلیدهای ارسال‌شده ممکن است با نام _hot_keys یا _keys بیایند.
    keys = res.get("_hot_keys") or res.get("_keys") or []
    pkeys = res.get("_pre_keys") or []
    if not keys and not pkeys:
        return
    st = load_state()
    sent = st.get("sent") or {}
    pre_sent = st.get("pre_sent") or {}
    now_iso = datetime.now(timezone.utc).isoformat()
    for k in keys:
        sent[k] = now_iso
    for k in pkeys:
        pre_sent[k] = now_iso
    st["sent"] = sent
    st["pre_sent"] = pre_sent
    save_state(st)


# ═══════════════════════════════════════════════════════════ main
def build_target(a):
    """تعیین مقصد تلگرام + پیام راهنما اگر کلید نبود (fix #1)."""
    if a.telegram and ":" in a.telegram and a.telegram != "env":
        tk, ch = a.telegram.split(":", 1)
        if "secret-" in tk:
            print("[telegram] توکن placeholder است (secret-...) → ارسال خاموش شد.")
            return None
        return (tk, ch)
    tk = a.telegram_token or os.environ.get("TG_TOKEN")
    ch = a.telegram_chat or os.environ.get("TG_CHAT")
    if tk and ch:
        if "secret-" in tk:
            print("[telegram] TG_TOKEN شبیه placeholder است (secret-...) → "
                  "ارسال خاموش شد. توکن واقعی BotFather را در Secrets بگذارید.")
            return None
        return (tk, ch)
    print("[telegram] کلید پیدا نشد. راه‌ها:")
    print("   ۱) --telegram TOKEN:CHAT_ID")
    print("   ۲) متغیر محیطی TG_TOKEN و TG_CHAT")
    print("   ۳) در GitHub: Settings → Secrets → TG_TOKEN و TG_CHAT")
    return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chains", nargs="*",
                    default=["solana", "base", "eth", "bsc"])
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--min-score", type=int, default=None)
    ap.add_argument("--json", dest="out_json", default=None)
    ap.add_argument("--new-only", action="store_true",
                    help="فقط ردیف‌هایی که تازه وارد رادار شده‌اند")
    ap.add_argument("--loop", type=int, default=0,
                    help="هر N دقیقه یک‌بار تکرار کن (0 = یک‌بار)")
    ap.add_argument("--telegram", nargs="?", const="env", default=None,
                    help="TOKEN:CHAT_ID (بدون مقدار ⇒ از TG_TOKEN و TG_CHAT)")
    ap.add_argument("--telegram-token", default=None)
    ap.add_argument("--telegram-chat", default=None)
    ap.add_argument("--send-above", type=int, default=MIN_SEND_FLOOR,
                    help=f"کف امتیاز سیگنال 🚀 (کف مجاز: {MIN_SEND_FLOOR})")
    ap.add_argument("--watch-floor", type=int, default=WATCH_FLOOR)
    ap.add_argument("--no-presignal", action="store_true",
                    help="طبقهٔ ⚡ را خاموش کن")
    ap.add_argument("--no-watch", action="store_true",
                    help="طبقهٔ 👀 را خاموش کن")
    ap.add_argument("--allow-risk-off", action="store_true",
                    help="ارسال حتی وقتی رژیم RISK-OFF است")
    ap.add_argument("--allow-unknown", action="store_true",
                    help="ارسال حتی وقتی رژیم نامعلوم است")
    ap.add_argument("--allow-low", action="store_true",
                    help=f"اجازهٔ آستانهٔ زیر {MIN_SEND_FLOOR}")
    ap.add_argument("--no-candles", action="store_true",
                    help="baseline کندلی را نخوان (سریع‌تر، ولی rvol5 کم‌دقت‌تر)")
    ap.add_argument("--max-age-days", type=float, default=None,
                    help="سقف سن استخر به روز (0 = بی‌سقف، پیش‌فرض ۳۰)")
    ap.add_argument("--dedupe-hours", type=float, default=6.0)
    ap.add_argument("--no-rugcheck", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="متن پیام را چاپ کن ولی نفرست")
    a = ap.parse_args()

    # سقف سن استخر از خط فرمان (پیش‌فرض همان ثابت بالاست)
    if a.max_age_days is not None:
        MAX_AGE_FOR_RADAR_MIN = max(0.0, a.max_age_days) * 1440.0
    NO_CANDLES = bool(a.no_candles)
    if NO_CANDLES:
        print("[candles] خاموش → هیچ درخواست OHLCV نمی‌رود (rvol5 از عمر استخر تخمین زده می‌شود)")
    print(f"[age] سقف سن استخر: {age_label(MAX_AGE_FOR_RADAR_MIN) if MAX_AGE_FOR_RADAR_MIN else 'بی‌سقف'}")

    threshold = a.send_above
    if threshold < MIN_SEND_FLOOR and not a.allow_low:
        print(f"[gate] آستانهٔ {threshold} زیر کف {MIN_SEND_FLOOR} بود → "
              f"به {MIN_SEND_FLOOR} بالا برده شد (برای عبور: --allow-low)")
        threshold = MIN_SEND_FLOOR

    # fix #9: هر پرچم فقط طبقهٔ خودش را خاموش می‌کند.
    wsig_floor = 0 if a.no_watch else min(a.watch_floor, threshold)
    pfloor = 0 if a.no_presignal else PRESIGNAL_FLOOR
    # سقف طبقهٔ ⚡: باید از کف 👀 یکی کمتر باشد و هرگز منفی نشود.
    pre_top_lbl = max(wsig_floor - 1, pfloor)
    parts = [f"🚀 ≥{threshold}"]
    parts.append("👀 خاموش" if not wsig_floor
                 else f"👀 {wsig_floor}-{threshold - 1}")
    parts.append("⚡ خاموش" if not pfloor
                 else f"⚡ {pfloor}-{pre_top_lbl}")
    print("[tier] " + " | ".join(parts))

    tgt = build_target(a)

    while True:
        r = run(a.chains, a.top, a.min_score, a.new_only, a.out_json,
                dedupe_hours=a.dedupe_hours, do_rugcheck=not a.no_rugcheck)
        show(r, a.top)
        if a.new_only:
            print("[new-only] فقط ردیف‌های «🆕 وارد رادار شد» بررسی شدند.")
        txt = alert_text(r, threshold, allow_risk_off=a.allow_risk_off,
                         watch_floor=wsig_floor,
                         presignal_floor=pfloor,
                         allow_unknown=a.allow_unknown)
        if a.dry_run:
            print("\n──────── متن تلگرام (dry-run) ────────")
            print(txt)
            print("─────────────────────────────────────")
        elif tgt and txt:
            ok = notify_telegram(tgt[0], tgt[1], txt)
            print(f"[telegram] {'ارسال شد' if ok else 'ارسال نشد'}")
            if ok:
                mark_sent(r)
        else:
            print("[telegram] مقصد تنظیم نشده یا متنی نبود → ارسال نشد")
        if a.loop <= 0:
            break
        print(f"\n⏳ {a.loop} دقیقه صبر... (Ctrl+C برای توقف)\n")
        time.sleep(a.loop * 60)
