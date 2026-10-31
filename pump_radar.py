#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pump_radar.py  —  رادار لحظه‌ای "میم‌کوینی که می‌خواهد پامپ کند"

منطق کار (چرا این کار می‌کند):
  پامپ واقعی همیشه با «انفجار حجم در پنجرهٔ ۵ دقیقه» شروع می‌شود، نه با قیمت.
  پس معیار اصلی = حجم ۵ دقیقهٔ اخیر نسبت به میانگین حجم ۵ دقیقه‌ای ۶ ساعت گذشته.
  اگر این نسبت بالا باشد + فشار خرید بالا باشد + نقدینگی کافی باشد =>
  توکن در «فاز بیدار شدن / شروع پامپ» است.

خروجی: لیست رتبه‌بندی‌شده با score 0..100 و دلایل.
استفاده:
  python3 pump_radar.py                 # اسکن کامل
  python3 pump_radar.py --json out.json
  python3 pump_radar.py --chains solana base
  python3 pump_radar.py --top 15
  python3 pump_radar.py --new-only      # فقط وضعیت جدید نسبت به اجرای قبل
"""
import argparse, json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (pump-radar)"}
STATE = os.environ.get("PUMP_STATE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "pump_radar_state.json")

GT = "https://api.geckoterminal.com/api/v2"
CG = "https://api.coingecko.com/api/v3"
DS = "https://api.dexscreener.com"


def _get(url, tries=3, base_sleep=1.5):
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
    return None


def nz(v, d=0.0):
    try:
        if v is None:
            return d
        return float(v)
    except Exception:
        return d


# ---------------------------------------------------------------- rژیم کلان
def regime():
    """آیا اصلاً روز پامپ است؟ (طبق قاعدهٔ پرامپت: در RISK-OFF لیست خالی)"""
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
    elif s >= 2:
        out["verdict"] = "NEUTRAL -> فقط رادار، نصف حجم"
    else:
        out["verdict"] = "RISK-OFF -> امروز روز پامپ نیست"
    return out


# ---------------------------------------------------------------- جمع‌آوری
def gt_pools(chain, kind="trending", pages=2):
    rows = []
    for p in range(1, pages + 1):
        d = _get(f"{GT}/networks/{chain}/{kind}_pools?page={p}")
        if not d:
            break
        for it in d.get("data", []):
            a = it.get("attributes", {})
            rows.append({"chain": chain, "pool": a.get("address"), "name": a.get("name"),
                         "created": a.get("pool_created_at"), "fdv": nz(a.get("fdv_usd")),
                         "mc": nz(a.get("market_cap_usd")),
                         "price": nz(a.get("base_token_price_usd")),
                         "pc": a.get("price_change_percentage", {}) or {},
                         "tx": a.get("transactions", {}) or {},
                         "vol": a.get("volume_usd", {}) or {},
                         "reserve": nz(a.get("reserve_in_usd")),
                         "dex": (it.get("relationships", {}).get("dex", {}) or {}).get("data", {}).get("id", ""),
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
    # dedupe
    seen, out = set(), []
    for r in rows:
        k = (r["chain"], r["token"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def ds_token_pairs(chain, addr):
    d = _get(f"{DS}/latest/dex/tokens/{addr}")
    if not d:
        return []
    return [p for p in (d.get("pairs") or []) if p.get("chainId") == chain]


# ---------------------------------------------------------------- امتیازدهی
def pump_score(r):
    """نمرهٔ ۰..۱۰۰ برای «در شرف پامپ بودن». دلایل هم برگردانده می‌شود."""
    reasons, risks = [], []
    s = 0.0

    liq = nz(r.get("reserve"))
    mc = nz(r.get("mc")) or nz(r.get("fdv"))
    vol = r.get("vol") or {}
    pc = r.get("pc") or {}
    tx = r.get("tx") or {}

    v5, v1h, v6h, v24 = nz(vol.get("m5")), nz(vol.get("h1")), nz(vol.get("h6")), nz(vol.get("h24"))
    p5, p1h, p6h, p24 = nz(pc.get("m5")), nz(pc.get("h1")), nz(pc.get("h6")), nz(pc.get("h24"))

    tx5 = tx.get("m5") or {}
    b5, s5 = nz(tx5.get("buys")), nz(tx5.get("sells"))
    tx1 = tx.get("h1") or {}
    b1, s1 = nz(tx1.get("buys")), nz(tx1.get("sells"))

    # --- هستهٔ رادار: انفجار حجم کوتاه‌مدت -----------------------------
    # میانگین حجم ۵ دقیقه‌ای در ۶ ساعت گذشته ≈ v6h / 72
    base5 = v6h / 72.0 if v6h > 0 else (v1h / 12.0 if v1h > 0 else 0.0)
    if base5 > 0:
        spike = v5 / base5
        r["spike5"] = round(spike, 2)
        if spike >= 20:
            s += 30; reasons.append(f"انفجار حجم ۵دقیقه‌ای ×{spike:.0f} نسبت به میانگین ۶ساعت")
        elif spike >= 8:
            s += 22; reasons.append(f"جهش حجم ۵دقیقه‌ای ×{spike:.1f}")
        elif spike >= 4:
            s += 14; reasons.append(f"حجم ۵دقیقه‌ای ×{spike:.1f} بالای نرمال")
        elif spike >= 2:
            s += 7; reasons.append(f"حجم ۵دقیقه‌ای ×{spike:.1f} (بیدار شدن)")
        elif spike < 0.5 and v6h > 0:
            s -= 10; risks.append("حجم ۵دقیقه‌ای مرده (زیر نصف نرمال)")

    # --- حجم ۱ ساعته هم پشتیبان باشد -----------------------------------
    base1 = v6h / 6.0 if v6h > 0 else 0.0
    if base1 > 0 and v1h / base1 >= 2:
        s += 10; reasons.append("حجم ۱ساعته هم بالای میانگین ۶ساعت")
    if v24 > 0 and v1h > 0 and v1h / max(v24 / 24.0, 1e-9) >= 3:
        s += 8; reasons.append("ریتم ساعتی ۳ برابر نرمال ۲۴ساعته")

    # --- فشار خرید (نه فقط قیمت) ---------------------------------------
    if b5 + s5 > 0:
        ratio = b5 / max(s5, 1)
        r["buy_ratio5"] = round(ratio, 2)
        if ratio >= 3 and b5 >= 10:
            s += 16; reasons.append(f"فشار خرید ۵دقیقه‌ای {ratio:.1f}× (خریدار غالب)")
        elif ratio >= 1.5 and b5 >= 8:
            s += 9; reasons.append(f"خرید ۵دقیقه‌ای {ratio:.1f}× فروش")
        elif ratio <= 0.6 and s5 >= 10:
            s -= 12; risks.append("فروشنده غالب در ۵ دقیقهٔ اخیر")
    if b1 + s1 > 0:
        r1 = b1 / max(s1, 1)
        if r1 >= 1.4:
            s += 6; reasons.append(f"فشار خرید ۱ساعته {r1:.1f}×")

    # --- هنوز بالا نرفته باشد (جا برای حرکت) ---------------------------
    if p5 > 0:
        if p5 <= 6:
            s += 8; reasons.append(f"قیمت ۵دقیقه‌ای فقط +{p5:.1f}% (تازه شروع شده)")
        elif p5 <= 15:
            s += 5; reasons.append(f"۵دقیقه‌ای +{p5:.1f}%")
        elif p5 > 25:
            s -= 14; risks.append(f"۵دقیقه‌ای +{p5:.0f}% (دیر شده، تعقیب نکن)")
    if p1h > 40:
        s -= 10; risks.append(f"۱ساعته +{p1h:.0f}% (بیش از حد کشیده)")
    if p24 > 100:
        s -= 20; risks.append(f"۲۴ساعته +{p24:.0f}% (قاعدهٔ ۱۰۰٪ → حذف)")
    elif 0 < p24 <= 60:
        s += 6; reasons.append(f"۲۴ساعته +{p24:.0f}% (پامپ تازه)")

    # --- نقدینگی (بتواند سفارش را حمل کند) -----------------------------
    if liq >= 1_000_000:
        s += 14; reasons.append("نقدینگی بالای $1M (خروج آسان)")
    elif liq >= 300_000:
        s += 10; reasons.append(f"نقدینگی ${liq/1000:.0f}K قابل قبول")
    elif liq >= 150_000:
        s += 5; reasons.append(f"نقدینگی ${liq/1000:.0f}K حداقلی")
    elif liq >= 50_000:
        s -= 6; risks.append(f"نقدینگی کم ${liq/1000:.0f}K")
    elif liq > 0:
        s -= 20; risks.append(f"نقدینگی خیلی کم ${liq/1000:.0f}K (گیر می‌افتی)")

    # --- نسبت حجم به نقدینگی (چرخش پول) --------------------------------
    if liq > 0 and v24 > 0:
        turn = v24 / liq
        r["turnover24"] = round(turn, 2)
        if turn >= 3:
            s += 7; reasons.append(f"چرخش ۲۴ساعته {turn:.1f}× نقدینگی (بازار داغ)")

    # --- سن استخر ------------------------------------------------------
    age_d = None
    if r.get("created"):
        try:
            t = datetime.fromisoformat(r["created"].replace("Z", "+00:00"))
            age_d = (datetime.now(timezone.utc) - t).total_seconds() / 86400
        except Exception:
            pass
    if age_d is not None:
        r["age_days"] = round(age_d, 2)
        if age_d < 0.08:
            s -= 8; risks.append("کمتر از ۲ ساعت سن (ریسک آتش‌بازی لحظه‌ای)")
        elif age_d < 1:
            s -= 3; risks.append("کمتر از ۱ روز سن")
        elif age_d < 3:
            s += 3; reasons.append("سن ۱ تا ۳ روز (تازه ولی قابل ارزیابی)")
        elif age_d > 30:
            s += 5; reasons.append("پروژه عمر کرده (نه لانچ لحظه‌ای)")

    # --- مارکت‌کپ -------------------------------------------------------
    if mc > 0:
        if 1_000_000 <= mc <= 50_000_000:
            s += 6; reasons.append("مارکت‌کپ در محدودهٔ پامپ‌پذیر ($1M–$50M)")
        elif mc < 300_000:
            s -= 8; risks.append("مارکت‌کپ زیر $300K (نازک)")

    r["score"] = int(max(0, min(100, round(s))))
    r["reasons"] = reasons
    r["risks"] = risks
    if not reasons:
        r["reasons"] = ["هیچ نشانهٔ پامپ فعالی نیست"]
    return r


def phase(r):
    sc = r.get("score", 0)
    sp = r.get("spike5", 0) or 0
    if sc >= 70 and sp >= 8:
        return "🚀 شروع پامپ (خطر بالا، سود بالا)"
    if sc >= 55:
        return "⚡ بیدار شدن (رادار فعال)"
    if sc >= 40:
        return "👀 زیر نظر"
    return "—"


def confidence(sc):
    if sc >= 85: return "S", 70, 75
    if sc >= 75: return "A", 60, 70
    if sc >= 65: return "B", 52, 60
    if sc >= 55: return "C", 45, 52
    return "D", 0, 45


def pump_prob(sc):
    """احتمال پامپ +50% در ۷ روز آینده (سقف ۷۰٪)."""
    base = 8 + max(0, sc - 30) * 0.7
    if sc < 40:
        base = max(0, base - 6)
    base = min(base, 70)
    return round(base)


# ---------------------------------------------------------------- اجرا
def collect(chains):
    pools = []
    for c in chains:
        pools += gt_pools(c, "trending", pages=2)
        pools += gt_pools(c, "new", pages=1)
    return pools


def run(chains, top=15, min_score=None, new_only=False, out_json=None):
    reg = regime()
    pools = collect(chains)

    # یک‌تا‌سازی بر اساس آدرس استخر
    seen, uniq = set(), []
    for p in pools:
        k = (p["chain"], p.get("pool"))
        if k in seen or not p.get("pool"):
            continue
        seen.add(k)
        uniq.append(p)

    # اگر استخر trend نداشت، با DexScreener کاملش کن
    for p in uniq:
        if not p.get("vol"):
            pr = ds_token_pairs(p["chain"], (p.get("name") or "").split("/")[0])
            if pr:
                x = pr[0]
                p["reserve"] = nz(x.get("liquidity", {}).get("usd"), p.get("reserve"))
                p["mc"] = nz(x.get("marketCap"), p.get("mc"))
                p["vol"] = {"h24": nz(x.get("volume", {}).get("h24")),
                            "h6": nz(x.get("volume", {}).get("h6")),
                            "h1": nz(x.get("volume", {}).get("h1")),
                            "m5": nz(x.get("volume", {}).get("m5"))}
                p["pc"] = x.get("priceChange") or {}
                p["tx"] = x.get("txns") or {}
            time.sleep(0.4)

    scored = [pump_score(p) for p in uniq]
    scored.sort(key=lambda r: r["score"], reverse=True)
    scored = [r for r in scored if r["score"] > 0]

    if min_score:
        scored = [r for r in scored if r["score"] >= min_score]

    # وضعیت قبلی → چه چیزی تازه است
    prev = {}
    if os.path.exists(STATE):
        try:
            prev = {f"{x.get('chain')}|{x.get('pool')}": x.get("score", 0)
                    for x in json.load(open(STATE)).get("rows", [])}
        except Exception:
            prev = {}

    for r in scored:
        k = f"{r.get('chain')}|{r.get('pool')}"
        old = prev.get(k)
        if old is None:
            r["status"] = "🆕 وارد رادار شد"
        elif r["score"] > old + 10:
            r["score"] += 5
            r["status"] = f"📈 صعودی (از {old} به {r['score']-5})"
        elif r["score"] < old - 10:
            r["status"] = f"📉 در حال خنک شدن (از {old})"
        else:
            r["status"] = "· پایدار"

    scored.sort(key=lambda r: r["score"], reverse=True)
    top_rows = scored[:top]

    res = {"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
           "regime": reg, "scanned_pools": len(uniq), "rows": top_rows}

    try:
        json.dump({"generated_utc": res["generated_utc"], "rows": scored[:60]},
                  open(STATE, "w"), ensure_ascii=False)
    except Exception:
        pass

    if out_json:
        json.dump(res, open(out_json, "w"), ensure_ascii=False, indent=1)
    return res


def show(res, limit=15):
    reg = res["regime"]
    print("=" * 74)
    print(f"رادار پامپ  ·  {res['generated_utc']} UTC  ·  استخرهای اسکن‌شده: {res['scanned_pools']}")
    print("=" * 74)
    print(f"رژیم بازار: {reg['verdict']}   (امتیاز {reg.get('score')}/5)")
    for n in reg.get("notes", []):
        print("   •", n)
    if "btc_price" in reg:
        print(f"   BTC ${reg['btc_price']:,} | 24h {reg.get('btc_24h')}% | 7d {reg.get('btc_7d')}%"
              f" | دامیننس {reg.get('btc_dom')}% | ترس‌وطمع {reg.get('fear_greed')}")
    print()
    if not res["rows"]:
        print("🔴 هیچ توکنی نشانهٔ پامپ فعال نداشت. امروز روز تماشا است.")
        return
    for i, r in enumerate(res["rows"][:limit], 1):
        g, lo, hi = confidence(r["score"])
        pp = pump_prob(r["score"])
        print(f"{i:2d}. {r.get('name','?')}  [{r.get('chain')}]  score={r['score']} ({g})"
              f"  پامپ۷روزه≈{pp}%  {phase(r)}")
        print(f"    liq ${nz(r.get('reserve')):,.0f} | mc ${nz(r.get('mc')):,.0f}"
              f" | 24h {nz((r.get('pc') or {}).get('h24')):.1f}%"
              f" | 1h {nz((r.get('pc') or {}).get('h1')):.1f}%"
              f" | 5m {nz((r.get('pc') or {}).get('m5')):.1f}%"
              f" | spike5 {r.get('spike5','-')}× | سن {r.get('age_days','?')}d")
        print(f"    وضعیت: {r.get('status','·')}")
        for x in r["reasons"][:4]:
            print(f"      + {x}")
        for x in r["risks"][:3]:
            print(f"      - {x}")
        print()


def notify_telegram(token, chat, text):
    """ارسال هشدار به تلگرام (اختیاری)."""
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        body = json.dumps({"chat_id": chat, "text": text,
                           "parse_mode": "HTML", "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(url, data=body,
                                     headers={**UA, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception as e:
        print("[telegram error]", e)
        return False


def alert_text(res, min_send=55):
    """متن هشدار برای توکن‌هایی که از آستانه رد شده‌اند."""
    reg = res["regime"]
    hot = [r for r in res["rows"] if r["score"] >= min_send]
    if not hot:
        return None
    L = [f"<b>🚨 رادار پامپ</b>  {res['generated_utc']} UTC",
         f"رژیم: {reg['verdict']}", ""]
    for r in hot[:6]:
        g, lo, hi = confidence(r["score"])
        L.append(f"<b>{r.get('name','?')}</b> [{r.get('chain')}] "
                 f"score={r['score']} ({g}) پامپ≈{pump_prob(r['score'])}%")
        L.append(f"  liq ${nz(r.get('reserve')):,.0f} | mc ${nz(r.get('mc')):,.0f}"
                 f" | 24h {nz((r.get('pc') or {}).get('h24')):.1f}%"
                 f" | spike5 {r.get('spike5','-')}×")
        for x in r["reasons"][:3]:
            L.append(f"  ✅ {x}")
        for x in r["risks"][:2]:
            L.append(f"  ⚠️ {x}")
        L.append("")
    L.append("❗️سیگنال آماده نیست. تحقیق شخصی و حد ضرر اجباری.")
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chains", nargs="*", default=["solana", "base", "eth", "bsc"])
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--min-score", type=int, default=None)
    ap.add_argument("--json", dest="out_json", default=None)
    ap.add_argument("--new-only", action="store_true")
    ap.add_argument("--loop", type=int, default=0,
                    help="هر N دقیقه یک‌بار تکرار کن (0 = یک‌بار)")
    ap.add_argument("--telegram", default=None,
                    help="TOKEN:CHAT_ID برای ارسال هشدار تلگرام")
    ap.add_argument("--send-above", type=int, default=55,
                    help="فقط score بالاتر از این به تلگرام برود")
    a = ap.parse_args()

    tgt = None
    if a.telegram and ":" in a.telegram:
        tk, ch = a.telegram.split(":", 1)
        tgt = (tk, ch)
    elif os.environ.get("TG_TOKEN") and os.environ.get("TG_CHAT"):
        tgt = (os.environ["TG_TOKEN"], os.environ["TG_CHAT"])

    while True:
        r = run(a.chains, a.top, a.min_score, a.new_only, a.out_json)
        show(r, a.top)
        if tgt:
            txt = alert_text(r, a.send_above)
            if txt:
                ok = notify_telegram(tgt[0], tgt[1], txt)
                print(f"[telegram] {'ارسال شد' if ok else 'ارسال نشد'}")
            else:
                print(f"[telegram] چیزی بالای {a.send_above} نبود → ارسال نشد")
        if a.loop <= 0:
            break
        print(f"\n⏳ {a.loop} دقیقه صبر... (Ctrl+C برای توقف)\n")
        time.sleep(a.loop * 60)
