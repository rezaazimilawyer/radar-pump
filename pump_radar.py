#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pump_radar.py — رادار «فعالیت غیرعادی میم‌کوین» (نسخهٔ نهایی بهینه‌شده برای سرعت)
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

UA = {"User-Agent": "Mozilla/5.0 (pump-radar/6.1-speed)", "Accept": "application/json"}
STATE = os.environ.get("PUMP_STATE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "pump_radar_state.json")

GT = "https://api.geckoterminal.com/api/v2"
CG = "https://api.coingecko.com/api/v3"
DS = "https://api.dexscreener.com"
RC = "https://api.rugcheck.xyz/v1"

# ── فیلترهای سرعت بالا (برای جام نماندن از بازار) ──────────────────────
MIN_LIQ = 15_000        # کاهش از ۵۰k به ۱۵k دلار (شکار توکن‌های تازه متولد شده)
MIN_AGE_MIN = 3.0       # کاهش از ۲۰ دقیقه به ۳ دقیقه 
MIN_V24 = 5_000         # حجم ۲۴ ساعته 
MIN_TX5 = 3             # حداقل تراکنش در ۵ دقیقه
MIN_V5_USD = 200        
MIN_TRADE_USD = 5.0     

# ── طبقه‌های ارسال ───────────────────────────────────────────
MIN_SEND_FLOOR = 40     # کف امتیاز سیگنال برای ارسال سریع‌تر
WATCH_FLOOR = 35        
WATCH_MAX = 5           
PRESIGNAL_FLOOR = 30    
PRE_RVOL5 = 1.5
PRE_P5_MIN = 0.5
PRE_P5_MAX = 25.0
PRE_MIN_LIQ = 15_000
PRE_AGE_MIN = 3.0
PRE_MAX = 6
PRE_DEDUPE_H = 2.0

SIG_P5_MIN = 0.2        
SIG_P5_MAX = 30.0       
SIG_RVOL5_MIN = 1.3     
SIG_TOP_24H_MAX = 150.0 

RUG_DROP_PCT = 40.0     
RUG_WARN_PCT = 20.0     
RUG_LOOKBACK_H = 6.0    

EARLY_V5_USD = 800
EARLY_SCAN_PAGES = 3
LATE_P5 = 20.0

RUG_BLOCK_IF_RISK_NAMES = ("mint authority", "freeze authority", "transfer fee",
                           "honeypot", "cannot sell", "non-transferable")
RUG_BLOCK_SCORE = 60_000   

UNKNOWN_ALLOW_SEND = True   # پیش‌فرض: در صورت نامعلوم بودن رژیم، ارسال مجاز باشد
MAX_AGE_FOR_RADAR_MIN = 43200.0   
NO_CANDLES = True   # پیش‌فرض روی حالت سریع (بدون درخواست سنگین OHLCV)


def _mask(s):
    s = str(s)
    s = re.sub(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b", "<BOT_TOKEN>", s)
    s = re.sub(r"\b[A-Za-z0-9_-]{30,}\b", "<SECRET>", s)
    return s


def _log_err(msg):
    print("[err]", _mask(msg), file=sys.stderr)


def _get(url, tries=2, base_sleep=1.0):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                time.sleep(base_sleep * (i + 1))
                continue
            return None
        except Exception as e:
            last = e
            time.sleep(base_sleep)
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


def age_label(am):
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


def regime():
    out = {"verdict": "RISK-ON (سریع)", "score": 3, "notes": ["حالت سرعت بالا فعال"], "allow": True, "sources_ok": 1}
    return out


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
            rows.append({"chain": chain,
                         "pool": a.get("address"),
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
                         "src": f"gt_{kind}"})
    return rows


def ds_token_pairs(chain, addr):
    if not addr:
        return []
    d = _get(f"{DS}/latest/dex/tokens/{addr}")
    if not d:
        return []
    return [p for p in (d.get("pairs") or []) if p.get("chainId") == chain]


def ds_pair_for_pool(chain, addr, pool):
    if not pool:
        return None
    for p in ds_token_pairs(chain, addr):
        if str(p.get("pairAddress") or "").lower() == str(pool).lower():
            return p
    return None


def volume_ratios(r, use_candles=False):
    vol = r.get("vol") or {}
    v5 = nz(vol.get("m5"))
    v1h = nz(vol.get("h1"))
    v6h = nz(vol.get("h6"))
    v24 = nz(vol.get("h24"))

    am = age_minutes(r)
    age_h = None if am is None else min(max(am / 60.0, 5.0 / 60.0), 24.0)

    basis, reason = "prior", "ok"
    avg5 = 0.0

    if age_h is not None:
        life_v = max(v24, v6h, v1h, v5)
        prior_v = max(life_v - v5, 0.0)
        prior_h = max(age_h - 5.0 / 60.0, 0.0)
        if prior_h >= 0.1 and prior_v > 0:
            avg5 = (prior_v / prior_h) / 12.0
        else:
            avg5 = max(v24 / 288.0, 10.0)

    rvol5 = (v5 / avg5) if avg5 > 0 else 2.0
    rvol1h = (v1h / (avg5 * 12.0)) if avg5 > 0 else 1.5

    return {"v5": v5, "v1h": v1h, "v6h": v6h, "v24": v24,
            "age_min": am, "age_h": age_h, "age_known": am is not None,
            "avg5": avg5, "rvol5": min(rvol5, 50.0), "rvol1h": min(rvol1h, 50.0),
            "rvol5_source": basis, "rvol5_reason": reason, "history_n": 5}


def _prime_candles(rows):
    pass


def pump_score(r):
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
    
    vr = volume_ratios(r)
    r.update(vr)
    v5, v24 = vr["v5"], vr["v24"]
    rvol5 = vr["rvol5"]
    am = vr["age_min"]
    trades5 = b5 + s5

    drop = []
    if liq < MIN_LIQ:
        drop.append(f"نقدینگی پایین: {fmt_usd(liq)}")
    if am is not None and am < MIN_AGE_MIN:
        drop.append(f"سن کمتر از حد مجاز")
    if v24 < MIN_V24:
        drop.append(f"حجم کم")

    r["dropped"] = bool(drop)
    r["drop_reasons"] = drop
    if drop:
        r["score"] = 0
        r["reasons"] = ["رد شده"]
        r["risks"] = drop
        r["sendable"] = False
        r["send_block"] = drop[:]
        return r

    # امتیازدهی سریع به حجم و مومنتوم
    if rvol5 >= 3:
        s += 35
        reasons.append(f"انفجار حجم ۵دقیقه ×{rvol5:.1f}")
    elif rvol5 >= 1.5:
        s += 20
        reasons.append(f"رشد حجم ۵دقیقه ×{rvol5:.1f}")

    if p5 > 0.5:
        s += 25
        reasons.append(f"شروع مثبت قیمت ۵دقیقه: {p5:+.1f}%")

    if trades5 >= 3:
        s += 20
        reasons.append(f"تراکنش‌های فعال: {trades5} ترید")

    if liq >= 30_000:
        s += 15
        reasons.append(f"نقدینگی مناسب {fmt_usd(liq)}")

    r["score"] = int(max(0, min(100, round(s))))
    r["reasons"] = reasons or ["فعالیت عادی"]
    r["risks"] = risks

    checks = {
        "نقدینگی کافی": liq >= MIN_LIQ,
        "رول حجم مناسب": rvol5 >= 1.2
    }
    r["checks"] = checks
    ok = all(checks.values())
    r["sendable"] = ok
    r["send_block"] = [] if ok else ["چک‌لیست کامل نشد"]
    return r


def _src_fa(vr):
    return "محاسبه سریع"


def safety_ok(r):
    why = []
    if r.get("dropped"):
        why.append("فیلتر سخت")
    if not r.get("sendable"):
        why.append("امتیاز کافی نیست")
    return (len(why) == 0), why


def sig_ok(r):
    ok, why = safety_ok(r)
    if not ok:
        return False, why
    return True, []


def presignal_ok(r):
    ok, why = safety_ok(r)
    if not ok:
        return False, why
    return True, []


def rugcheck(addr):
    return {"status": "skipped", "risks": [], "score": 0, "note": "غیرفعال برای سرعت"}


def load_state():
    if not os.path.exists(STATE):
        return {}
    try:
        with open(STATE) as f:
            return json.load(f) or {}
    except Exception:
        return {}


def save_state(state):
    tmp = STATE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, STATE)
    except Exception:
        pass


def collect(chains):
    pools = []
    for c in chains:
        pools += gt_pools(c, "trending", pages=1)
        pools += gt_pools(c, "new", pages=1)
    return pools


def run(chains, top=15, min_score=None, new_only=False, out_json=None,
        dedupe_hours=2.0, do_rugcheck=False):
    reg = regime()
    pools = collect(chains)

    seen, uniq = set(), []
    for p in pools:
        k = (p["chain"], p.get("pool"))
        if k in seen or not p.get("pool"):
            continue
        seen.add(k)
        uniq.append(p)

    scored = [pump_score(p) for p in uniq]
    alive = [r for r in scored if not r.get("dropped") and r["score"] >= 30]
    alive.sort(key=lambda r: r["score"], reverse=True)

    st = load_state()
    sent = {}
    for k, iso in (st.get("sent") or {}).items():
        t = parse_dt(iso)
        if t and (datetime.now(timezone.utc) - t).total_seconds() / 3600.0 <= dedupe_hours:
            sent[k] = iso

    for r in alive:
        k = f"{r.get('chain')}|{r.get('pool')}"
        r["already_sent"] = k in sent

    top_rows = alive[:top]
    res = {"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
           "regime": reg, "scanned_pools": len(uniq), "top_rows": top_rows, "rows": alive}

    state = {"sent": sent}
    save_state(state)
    return res


def show(res, limit=10):
    print(f"=== اسکن سریع انجام شد | استخرها: {res['scanned_pools']} | سیگنال‌ها: {len(res['top_rows'])} ===")
    for i, r in enumerate(res["top_rows"][:limit], 1):
        print(f"{i}. {r.get('name')} [{r.get('chain')}] score={r['score']} | liq: {fmt_usd(r.get('reserve'))} | 5m: {nz((r.get('pc') or {}).get('m5'))}%")


def split_html(text, limit=3800):
    return [text[i:i+limit] for i in range(0, len(text), limit)]


def notify_telegram(token, chat, text):
    if not token or not chat:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={**UA, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return True
    except Exception as e:
        _log_err(f"telegram: {e}")
        return False


def alert_text(res, min_send=MIN_SEND_FLOOR, allow_risk_off=True,
               watch_floor=WATCH_FLOOR, presignal_floor=PRESIGNAL_FLOOR,
               allow_unknown=True):
    hot = [r for r in res["rows"] if r["score"] >= min_send and not r.get("already_sent")]
    if not hot:
        return ""

    L = [f"<b>🚀 سیگنال سریع میم‌کوین</b> <code>{res.get('generated_utc')}</code>\n"]
    for r in hot[:5]:
        L.append(f"<b>🔹 {html.escape(str(r.get('name', '')))}</b> [{r.get('chain')}] (Score: <b>{r['score']}</b>)")
        L.append(<code>{r.get('base_token')}</code>)
        L.append(f"💰 نقدینگی: {fmt_usd(r.get('reserve'))} | 5 دقیقه: {nz((r.get('pc') or {}).get('m5'))}%")
        L.append("----------------------------")
    
    res["_hot_keys"] = [f"{r.get('chain')}|{r.get('pool')}" for r in hot[:5]]
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
    ap.add_argument("--chains", nargs="*", default=["solana", "base"])
    ap.add_argument("--loop", type=int, default=2, help="اجرای مداوم هر N دقیقه")
    ap.add_argument("--telegram", nargs="?", const="env", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    tk = os.environ.get("TG_TOKEN")
    ch = os.environ.get("TG_CHAT")

    print(f"[+] رادار سریع میم‌کوین شروع به کار کرد (حلقه: هر {a.loop} دقیقه)")

    while True:
        try:
            r = run(a.chains, top=10)
            show(r)
            txt = alert_text(r)
            if a.dry_run:
                print(txt)
            elif tk and ch and txt:
                ok = notify_telegram(tk, ch, txt)
                if ok:
                    mark_sent(r)
                    print("[✓] پیام با موفقیت به تلگرام ارسال شد.")
        except Exception as e:
            _log_err(f"Main loop error: {e}")

        if a.loop <= 0:
            break
        time.sleep(a.loop * 60)
