from __future__ import annotations
import json, re, sys, hashlib, os, html
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from icalendar import Calendar

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "events.json"

ET = ZoneInfo("America/New_York")
JST = ZoneInfo("Asia/Tokyo")
UTC = ZoneInfo("UTC")

UA = {"User-Agent": "Mozilla/5.0 (iPhone; rate-calendar/6.0)"}

BLS_ICS = "https://www.bls.gov/schedule/news_release/bls.ics"
BEA_URL = "https://www.bea.gov/news/schedule"
FED_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
TE_URL = "https://api.tradingeconomics.com/calendar/country/united%20states"
QUOTESTREAM_URL = "https://www.tradingviewapi.com/markets/calendar"

KEEP_WORDS = {
    "Consumer Price Index": ("米CPI・コアCPI", 5, "インフレ"),
    "Employment Situation": ("米雇用統計", 5, "雇用"),
    "Producer Price Index": ("米PPI", 4, "インフレ"),
    "Job Openings and Labor Turnover Survey": ("JOLTS 求人件数", 3, "雇用"),
    "Import and Export Price Indexes": ("輸出入物価指数", 3, "インフレ"),
    "Productivity and Costs": ("生産性・単位労働コスト", 3, "雇用"),
}

DEFAULT_ANALYSIS = {
    "米CPI・コアCPI": (
        "特にコアCPI前月比が予想を上回る",
        "コアCPIが予想を下回る",
        "上振れは米長期金利上昇→SBG・NASDAQ・高PER半導体に逆風。"
    ),
    "米雇用統計": (
        "雇用者数・平均時給が強く、失業率が低下",
        "雇用・賃金が鈍化し、失業率が上昇",
        "平均時給の上振れは長期金利上昇要因。"
    ),
    "米PPI": (
        "PPI・コアPPIが予想を上回る",
        "PPIが予想を下回る",
        "CPI/PCEに先行して金利が反応することがある。"
    ),
    "JOLTS 求人件数": (
        "求人件数が予想より多い",
        "求人件数が予想より少ない",
        "求人増は賃金インフレ懸念→金利上昇要因。"
    ),
    "PCE・コアPCE / 個人所得・支出": (
        "コアPCEや個人消費が予想を上回る",
        "コアPCEが予想を下回り、消費も減速",
        "FRBが重視する物価指標。上振れはSBG・NASDAQ・半導体に逆風。"
    ),
    "米GDP": (
        "GDPが上方修正・需要が強い",
        "GDP下方修正・景気減速",
        "強すぎる成長は利下げ後ずれ観測につながる。"
    ),
    "FOMC・政策金利発表": (
        "タカ派声明・利下げ後ずれ・インフレ警戒",
        "ハト派声明・利下げ余地を示唆",
        "米長期金利とNASDAQを大きく動かす最重要イベント。"
    ),
    "FRB議長会見": (
        "インフレ警戒・引き締め長期化を示唆",
        "景気減速・利下げ余地を強調",
        "声明後に金利・株価の方向が反転することもある。"
    ),
}

DEFAULT_METRICS = {
    "米CPI・コアCPI": [
        ("コアCPI 前月比", "%"),
        ("CPI 前月比", "%"),
    ],
    "米雇用統計": [
        ("非農業部門雇用者数", "K"),
        ("平均時給 前月比", "%"),
        ("失業率", "%"),
    ],
    "米PPI": [
        ("PPI 前月比", "%"),
        ("コアPPI 前月比", "%"),
    ],
    "JOLTS 求人件数": [
        ("JOLTS求人件数", "M"),
    ],
    "PCE・コアPCE / 個人所得・支出": [
        ("コアPCE 前月比", "%"),
        ("PCE 前月比", "%"),
        ("個人消費 前月比", "%"),
    ],
    "米GDP": [
        ("GDP成長率", "%"),
        ("GDP価格指数", "%"),
    ],
}

TE_PATTERNS = {
    "米CPI・コアCPI": {
        "コアCPI 前月比": ["Core Inflation Rate MoM", "Core CPI MoM"],
        "CPI 前月比": ["Inflation Rate MoM", "CPI MoM"],
    },
    "米雇用統計": {
        "非農業部門雇用者数": ["Non Farm Payrolls", "Nonfarm Payrolls"],
        "平均時給 前月比": ["Average Hourly Earnings MoM"],
        "失業率": ["Unemployment Rate"],
    },
    "米PPI": {
        "PPI 前月比": ["Producer Prices MoM", "PPI MoM"],
        "コアPPI 前月比": ["Core Producer Prices MoM", "Core PPI MoM"],
    },
    "JOLTS 求人件数": {
        "JOLTS求人件数": ["JOLTs Job Openings", "JOLTS Job Openings"],
    },
    "PCE・コアPCE / 個人所得・支出": {
        "コアPCE 前月比": ["Core PCE Price Index MoM"],
        "PCE 前月比": ["PCE Price Index MoM"],
        "個人消費 前月比": ["Personal Spending MoM"],
    },
    "米GDP": {
        "GDP成長率": ["GDP Growth Rate", "GDP Growth Rate QoQ"],
        "GDP価格指数": ["GDP Price Index", "GDP Price Index QoQ"],
    },
}

QS_PATTERNS = {
    "米CPI・コアCPI": {
        "コアCPI 前月比": ["Core CPI MoM", "Core Inflation Rate MoM"],
        "CPI 前月比": ["Inflation Rate MoM", "CPI MoM"],
    },
    "米雇用統計": {
        "非農業部門雇用者数": ["Non Farm Payrolls", "Nonfarm Payrolls"],
        "平均時給 前月比": ["Average Hourly Earnings MoM"],
        "失業率": ["Unemployment Rate"],
    },
    "米PPI": {
        "PPI 前月比": ["PPI MoM", "Producer Prices MoM"],
        "コアPPI 前月比": ["Core PPI MoM", "Core Producer Prices MoM"],
    },
    "JOLTS 求人件数": {
        "JOLTS求人件数": ["JOLTS Job Openings", "JOLTs Job Openings"],
    },
    "PCE・コアPCE / 個人所得・支出": {
        "コアPCE 前月比": ["Core PCE Price Index MoM"],
        "PCE 前月比": ["PCE Price Index MoM"],
        "個人消費 前月比": ["Personal Spending MoM"],
    },
    "米GDP": {
        "GDP成長率": ["GDP Growth Rate", "GDP Growth Rate QoQ"],
        "GDP価格指数": ["GDP Price Index QoQ", "GDP Price Index"],
    },
}

FALLBACK_EVENTS = [
    ("PCE・コアPCE / 個人所得・支出", "2026-08-26", "21:30", 5, "インフレ", "BEA", BEA_URL),
    ("米GDP", "2026-08-26", "21:30", 3, "景気", "BEA", BEA_URL),
    ("米雇用統計", "2026-09-04", "21:30", 5, "雇用", "BLS", "https://www.bls.gov/schedule/news_release/empsit.htm"),
    ("米PPI", "2026-09-10", "21:30", 4, "インフレ", "BLS", "https://www.bls.gov/schedule/news_release/ppi.htm"),
    ("米CPI・コアCPI", "2026-09-11", "21:30", 5, "インフレ", "BLS", "https://www.bls.gov/schedule/news_release/cpi.htm"),
    ("FOMC・政策金利発表", "2026-09-17", "03:00", 5, "FRB", "Federal Reserve", FED_URL),
    ("FRB議長会見", "2026-09-17", "03:30", 5, "FRB", "Federal Reserve", FED_URL),
    ("JOLTS 求人件数", "2026-09-29", "23:00", 3, "雇用", "BLS", "https://www.bls.gov/schedule/news_release/jolts.htm"),
    ("PCE・コアPCE / 個人所得・支出", "2026-09-30", "21:30", 5, "インフレ", "BEA", BEA_URL),
    ("米GDP", "2026-09-30", "21:30", 3, "景気", "BEA", BEA_URL),
]

def gid(*parts):
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:16]

def event_analysis(name):
    return DEFAULT_ANALYSIS.get(
        name,
        ("強い結果は金利上昇要因", "弱い結果は金利低下要因", "米長期金利の変化を確認。")
    )

def make_event(name, date, time, importance, category, source, url):
    up, down, impact = event_analysis(name)
    return {
        "id": gid(source, name, date, time),
        "name": name,
        "date": date,
        "time": time,
        "importance": importance,
        "category": category,
        "source": source,
        "url": url,
        "up": up,
        "down": down,
        "impact": impact,
        "metrics": [],
        "rate_signal": "pending",
        "rate_signal_label": "発表待ち",
    }

def add_event(events, name, dt_jst, importance, category, source, url):
    events.append(
        make_event(
            name,
            dt_jst.strftime("%Y-%m-%d"),
            dt_jst.strftime("%H:%M"),
            importance,
            category,
            source,
            url,
        )
    )

def to_jst(dt):
    if not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day, 8, 30, tzinfo=ET)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=ET)
    return dt.astimezone(JST)

def fetch_bls(events):
    r = requests.get(BLS_ICS, headers=UA, timeout=25)
    r.raise_for_status()
    cal = Calendar.from_ical(r.content)
    for c in cal.walk("VEVENT"):
        summary = str(c.get("summary", ""))
        for key, meta in KEEP_WORDS.items():
            if key.lower() in summary.lower():
                name, imp, cat = meta
                add_event(events, name, to_jst(c.decoded("dtstart")), imp, cat, "BLS", BLS_ICS)
                break

def parse_bea_date(text):
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        r"(\d{1,2})\s+(\d{1,2}:\d{2})\s+(AM|PM)",
        text,
    )
    if not m:
        return None
    year = datetime.now(ET).year
    dt = datetime.strptime(
        f"{year} {m.group(1)} {m.group(2)} {m.group(3)} {m.group(4)}",
        "%Y %B %d %I:%M %p",
    ).replace(tzinfo=ET)
    return dt.astimezone(JST)

def fetch_bea(events):
    r = requests.get(BEA_URL, headers=UA, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    blocks = []
    for node in soup.select("tr, .views-row, article"):
        txt = re.sub(r"\s+", " ", " ".join(node.stripped_strings)).strip()
        if txt:
            blocks.append(txt)
    whole = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    months = "January|February|March|April|May|June|July|August|September|October|November|December"
    pat = re.compile(rf"({months})\s+(\d{{1,2}})\s+(\d{{1,2}}:\d{{2}})\s+(AM|PM)")
    ms = list(pat.finditer(whole))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else min(len(whole), m.end() + 260)
        blocks.append(whole[m.start():end])

    seen = set()
    for txt in blocks:
        dt = parse_bea_date(txt)
        if not dt:
            continue
        key = (dt.strftime("%Y-%m-%d %H:%M"), txt[:120])
        if key in seen:
            continue
        seen.add(key)
        if "Personal Income and Outlays" in txt:
            add_event(events, "PCE・コアPCE / 個人所得・支出", dt, 5, "インフレ", "BEA", BEA_URL)
        if ("Gross Domestic Product" in txt or re.search(r"\bGDP\b", txt)) and (
            "Estimate" in txt or "Gross Domestic Product" in txt
        ):
            add_event(events, "米GDP", dt, 3, "景気", "BEA", BEA_URL)

def fetch_fed(events):
    r = requests.get(FED_URL, headers=UA, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = " ".join(soup.stripped_strings)
    year = datetime.now(ET).year
    section = text[text.find(str(year)):]
    if str(year + 1) in section:
        section = section[:section.find(str(year + 1))]
    months = "January|February|March|April|May|June|July|August|September|October|November|December"
    for m in re.finditer(rf"({months})\s+(\d{{1,2}})-(\d{{1,2}})\*?", section):
        month, _, endday = m.groups()
        dt = datetime.strptime(
            f"{year} {month} {endday} 14:00", "%Y %B %d %H:%M"
        ).replace(tzinfo=ET).astimezone(JST)
        add_event(events, "FOMC・政策金利発表", dt, 5, "FRB", "Federal Reserve", FED_URL)
        add_event(events, "FRB議長会見", dt + timedelta(minutes=30), 5, "FRB", "Federal Reserve", FED_URL)

def ensure_fallbacks(events):
    existing = {(e["name"], e["date"]) for e in events}
    for name, date, time, imp, cat, src, url in FALLBACK_EVENTS:
        if (name, date) not in existing:
            events.append(make_event(name, date, time, imp, cat, src, url))

def ensure_metric_placeholders(events):
    for e in events:
        specs = DEFAULT_METRICS.get(e["name"], [])
        existing = {m.get("label"): m for m in e.get("metrics", []) if isinstance(m, dict)}
        merged = []
        for label, unit in specs:
            m = existing.get(label, {})
            merged.append({
                "label": label,
                "unit": unit,
                "previous": m.get("previous") or "",
                "forecast": m.get("forecast") or "",
                "actual": m.get("actual") or "",
                "actual_first_seen": m.get("actual_first_seen") or "",
                "source": m.get("source") or "",
            })
        if specs:
            e["metrics"] = merged


def clean_market_value(value):
    """Accept only plausible numeric economic-calendar values; reject mojibake/text."""
    if value is None:
        return ""
    s = html.unescape(str(value)).strip()
    s = s.replace("\u2212", "-").replace("\xa0", " ")
    s = re.sub(r"\s+", "", s)
    if not s or s in {"—", "-", "N/A", "NA", "null", "None"}:
        return ""
    # Allow common economic values: -0.1%, 123K, 7.2M, 4.5B, 150,000 etc.
    if not re.fullmatch(r"[+-]?\d[\d,]*(?:\.\d+)?(?:%|K|M|B|T)?", s, flags=re.I):
        return ""
    return s

def event_has_occurred(e):
    """Only permit Actual after the scheduled JST release time has passed."""
    try:
        t = e.get("time") or "23:59"
        dt = datetime.fromisoformat(f'{e["date"]}T{t}').replace(tzinfo=JST)
        return datetime.now(JST) >= dt
    except Exception:
        return False

def source_date_matches(event_date, raw_date):
    """Require exact release-date match for market-value feeds."""
    try:
        d = str(raw_date or "")[:10]
        return bool(d) and d == event_date
    except Exception:
        return False

def safe_num(value):
    if value in (None, "", "—", "N/A"):
        return None
    s = str(value).strip().replace(",", "").replace("%", "")
    mult = 1.0
    if s.endswith("K"):
        mult, s = 1_000.0, s[:-1]
    elif s.endswith("M"):
        mult, s = 1_000_000.0, s[:-1]
    elif s.endswith("B"):
        mult, s = 1_000_000_000.0, s[:-1]
    try:
        return float(s) * mult
    except Exception:
        return None

def hawkish_score(label, actual, forecast):
    a, f = safe_num(actual), safe_num(forecast)
    if a is None or f is None:
        return 0
    if abs(a - f) < 1e-12:
        return 0
    higher = a > f
    inverse = ("失業率" in label) or ("生産性" in label)
    return (-1 if higher else 1) if inverse else (1 if higher else -1)

def fetch_te(errors):
    try:
        now = datetime.now(ET)
        start = (now - timedelta(days=180)).strftime("%Y-%m-%d")
        end = (now + timedelta(days=45)).strftime("%Y-%m-%d")
        key = os.environ.get("TE_API_KEY", "").strip() or "guest:guest"
        url = f"{TE_URL}/{start}/{end}"
        r = requests.get(url, params={"c": key, "f": "json"}, headers=UA, timeout=25)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as ex:
        errors.append(f"TradingEconomics: {ex}")
        return []

def fetch_quotestream(errors):
    try:
        r = requests.get(QUOTESTREAM_URL, headers=UA, timeout=25)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        rows = []
        for tr in soup.select("table tr"):
            cols = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)).strip() for c in tr.select("th,td")]
            if len(cols) >= 7:
                rows.append({
                    "time": cols[0],
                    "country": cols[1],
                    "event": cols[2],
                    "importance": cols[3],
                    "actual": cols[4],
                    "forecast": cols[5],
                    "previous": cols[6],
                })
        return rows
    except Exception as ex:
        errors.append(f"QuoteStream: {ex}")
        return []

def aliases_match(text, aliases):
    low = text.lower()
    return any(a.lower() in low for a in aliases)

def merge_metric(e, label, previous="", forecast="", actual="", source=""):
    previous = clean_market_value(previous)
    forecast = clean_market_value(forecast)
    actual = clean_market_value(actual) if event_has_occurred(e) else ""
    for m in e.get("metrics", []):
        if m.get("label") == label:
            if previous and not m.get("previous"):
                m["previous"] = previous
                m["source"] = source
            if forecast and not m.get("forecast"):
                m["forecast"] = forecast
                m["source"] = source
            if actual:
                # Save the first value this app ever observed.
                if not m.get("actual_first_seen"):
                    m["actual_first_seen"] = actual
                # Current official value can change after revisions.
                m["actual"] = actual
                m["source"] = source
            return

def enrich_from_te(events, te):
    for e in events:
        specs = TE_PATTERNS.get(e["name"], {})
        if not specs:
            continue
        for label, aliases in specs.items():
            matches = [
                x for x in te
                if isinstance(x, dict)
                and str(x.get("Country", "")).lower().startswith("united states")
                and source_date_matches(e["date"], x.get("Date", ""))
                and aliases_match(str(x.get("Event", "")) + " " + str(x.get("Category", "")), aliases)
            ]
            if not matches:
                continue
            x = matches[0]
            previous = clean_market_value(x.get("Previous"))
            forecast = clean_market_value(x.get("Forecast"))
            actual = clean_market_value(x.get("Actual")) if event_has_occurred(e) else ""
            merge_metric(
                e, label,
                previous=previous,
                forecast=forecast,
                actual=actual,
                source="Trading Economics",
            )

def enrich_from_quotestream(events, qs):
    for e in events:
        specs = QS_PATTERNS.get(e["name"], {})
        if not specs:
            continue
        for label, aliases in specs.items():
            for row in qs:
                if str(row.get("country", "")).upper() != "US":
                    continue
                if aliases_match(str(row.get("event", "")), aliases):
                    merge_metric(
                        e, label,
                        previous=clean_market_value(row.get("previous")),
                        forecast=clean_market_value(row.get("forecast")),
                        actual="",
                        source="公開経済カレンダー（補助）",
                    )
                    break

def calculate_signals(events):
    for e in events:
        if not event_has_occurred(e):
            e["rate_signal"] = "pending"
            e["rate_signal_label"] = "発表待ち"
            for m in e.get("metrics", []):
                m["actual"] = ""
            continue

        comparable = 0
        score = 0
        has_actual = False

        for m in e.get("metrics", []):
            actual = clean_market_value(m.get("actual"))
            forecast = clean_market_value(m.get("forecast"))

            if actual:
                has_actual = True
                m["actual"] = actual
                if not m.get("actual_first_seen"):
                    m["actual_first_seen"] = actual

            # Only compare when both Actual and Forecast are available.
            if actual and forecast:
                comparable += 1
                score += hawkish_score(m.get("label", ""), actual, forecast)

        if not has_actual:
            e["rate_signal"] = "missing"
            e["rate_signal_label"] = "結果未取得"
        elif comparable == 0:
            e["rate_signal"] = "no_forecast"
            e["rate_signal_label"] = "予想未取得・判定保留"
        elif score > 0:
            e["rate_signal"] = "up"
            e["rate_signal_label"] = "金利上昇警戒"
        elif score < 0:
            e["rate_signal"] = "down"
            e["rate_signal_label"] = "金利低下方向"
        else:
            e["rate_signal"] = "neutral"
            e["rate_signal_label"] = "中立・まちまち"

def merge_duplicates(events):
    out = {}
    for e in sorted(events, key=lambda x: (x["date"], x["time"], x["name"])):
        key = (e["name"], e["date"], e["time"])
        if key not in out:
            out[key] = e
        else:
            cur = out[key]
            if not cur.get("metrics") and e.get("metrics"):
                cur["metrics"] = e["metrics"]
            if cur.get("source") == "固定バックアップ" and e.get("source") != "固定バックアップ":
                cur["source"] = e["source"]
                cur["url"] = e["url"]
    return list(out.values())



BLS_API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

BLS_SERIES = {
    "cpi": "CUSR0000SA0",
    "core_cpi": "CUSR0000SA0L1E",
    "nonfarm": "CES0000000001",
    "ahe": "CES0500000003",
    "unemployment": "LNS14000000",
    "ppi": "WPSFD4",
}

def _month_shift(year, month, delta):
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1

def _period_key(year, month):
    return (int(year), int(month))

def fetch_bls_series(series_ids, start_year, end_year, errors):
    try:
        payload = {
            "seriesid": list(series_ids),
            "startyear": str(start_year),
            "endyear": str(end_year),
        }
        r = requests.post(BLS_API, json=payload, headers=UA, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "REQUEST_SUCCEEDED":
            errors.append("BLS API: " + "; ".join(data.get("message", [])))
            return {}
        out = {}
        for s in data.get("Results", {}).get("series", []):
            sid = s.get("seriesID")
            vals = {}
            for row in s.get("data", []):
                period = str(row.get("period", ""))
                if not period.startswith("M") or period == "M13":
                    continue
                try:
                    month = int(period[1:])
                    year = int(row.get("year"))
                    value = float(str(row.get("value")).replace(",", ""))
                except Exception:
                    continue
                vals[(year, month)] = value
            out[sid] = vals
        return out
    except Exception as ex:
        errors.append(f"BLS API: {ex}")
        return {}

def _pct_change(cur, prev):
    if cur is None or prev in (None, 0):
        return ""
    return f"{((cur / prev) - 1) * 100:.2f}%"

def _fmt_pct(v):
    if v is None:
        return ""
    return f"{v:.1f}%"

def _fmt_k(v):
    if v is None:
        return ""
    return f"{v:.0f}K"

def enrich_from_bls_official(events, errors):
    # Fetch enough monthly history to backfill the last 365 days.
    now = datetime.now(JST)
    data = fetch_bls_series(BLS_SERIES.values(), now.year - 2, now.year, errors)
    if not data:
        return

    def val(series_name, year, month):
        return data.get(BLS_SERIES[series_name], {}).get((year, month))

    for e in events:
        if not event_has_occurred(e):
            continue

        try:
            release = datetime.fromisoformat(e["date"])
        except Exception:
            continue

        # CPI / Employment / PPI releases normally describe the previous calendar month.
        ry, rm = _month_shift(release.year, release.month, -1)
        py, pm = _month_shift(ry, rm, -1)
        ppy, ppm = _month_shift(ry, rm, -2)

        if e.get("name") == "米CPI・コアCPI":
            cpi = val("cpi", ry, rm)
            cpi_prev = val("cpi", py, pm)
            cpi_prev2 = val("cpi", ppy, ppm)

            core = val("core_cpi", ry, rm)
            core_prev = val("core_cpi", py, pm)
            core_prev2 = val("core_cpi", ppy, ppm)

            merge_metric(
                e, "CPI 前月比",
                previous=_pct_change(cpi_prev, cpi_prev2),
                actual=_pct_change(cpi, cpi_prev),
                source="BLS公式API",
            )
            merge_metric(
                e, "コアCPI 前月比",
                previous=_pct_change(core_prev, core_prev2),
                actual=_pct_change(core, core_prev),
                source="BLS公式API",
            )

        elif e.get("name") == "米雇用統計":
            nf = val("nonfarm", ry, rm)
            nf_prev = val("nonfarm", py, pm)
            nf_prev2 = val("nonfarm", ppy, ppm)

            ahe = val("ahe", ry, rm)
            ahe_prev = val("ahe", py, pm)
            ahe_prev2 = val("ahe", ppy, ppm)

            ur = val("unemployment", ry, rm)
            ur_prev = val("unemployment", py, pm)

            # CES employment levels are in thousands; report monthly change in K.
            actual_nf = _fmt_k(nf - nf_prev) if nf is not None and nf_prev is not None else ""
            previous_nf = _fmt_k(nf_prev - nf_prev2) if nf_prev is not None and nf_prev2 is not None else ""

            merge_metric(
                e, "非農業部門雇用者数",
                previous=previous_nf,
                actual=actual_nf,
                source="BLS公式API",
            )
            merge_metric(
                e, "平均時給 前月比",
                previous=_pct_change(ahe_prev, ahe_prev2),
                actual=_pct_change(ahe, ahe_prev),
                source="BLS公式API",
            )
            merge_metric(
                e, "失業率",
                previous=_fmt_pct(ur_prev),
                actual=_fmt_pct(ur),
                source="BLS公式API",
            )

        elif e.get("name") == "米PPI":
            ppi = val("ppi", ry, rm)
            ppi_prev = val("ppi", py, pm)
            ppi_prev2 = val("ppi", ppy, ppm)

            merge_metric(
                e, "PPI 前月比",
                previous=_pct_change(ppi_prev, ppi_prev2),
                actual=_pct_change(ppi, ppi_prev),
                source="BLS公式API",
            )

def load_previous_payload():
    try:
        if not OUT.exists():
            return {"events": []}
        data = json.loads(OUT.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"events": []}
    except Exception:
        return {"events": []}

def merge_saved_history(events, previous_payload):
    """Keep any previously captured Previous/Forecast/Actual values permanently."""
    old_events = previous_payload.get("events", []) if isinstance(previous_payload, dict) else []
    old_map = {}
    for e in old_events:
        if not isinstance(e, dict):
            continue
        key = (e.get("name"), e.get("date"), e.get("time"))
        old_map[key] = e

    for e in events:
        key = (e.get("name"), e.get("date"), e.get("time"))
        old = old_map.get(key)
        if not old:
            continue

        old_metrics = {
            m.get("label"): m
            for m in old.get("metrics", [])
            if isinstance(m, dict) and m.get("label")
        }

        for m in e.get("metrics", []):
            om = old_metrics.get(m.get("label"))
            if not om:
                continue

            # Never erase values already captured in prior runs.
            for fld in ("previous", "forecast", "actual", "actual_first_seen"):
                if not m.get(fld) and om.get(fld):
                    m[fld] = om.get(fld)

            if not m.get("source") and om.get("source"):
                m["source"] = om.get("source")

        # Preserve a completed rate signal as historical record.
        if old.get("rate_signal") in {"up", "down", "neutral"}:
            e["rate_signal"] = old.get("rate_signal")
            e["rate_signal_label"] = old.get("rate_signal_label") or e.get("rate_signal_label")

def append_historical_only_events(events, previous_payload):
    """Keep old calendar events that have rolled outside current source windows."""
    existing = {(e.get("name"), e.get("date"), e.get("time")) for e in events}
    for old in previous_payload.get("events", []) if isinstance(previous_payload, dict) else []:
        if not isinstance(old, dict):
            continue
        key = (old.get("name"), old.get("date"), old.get("time"))
        if key in existing:
            continue
        try:
            d = datetime.fromisoformat(str(old.get("date")))
            age = (datetime.now(JST).date() - d.date()).days
        except Exception:
            continue
        # Retain the last 365 days in the app even if upstream calendars stop returning them.
        if 0 <= age <= 365:
            events.append(old)
            existing.add(key)

def set_missing_result_status(events):
    now = datetime.now(JST)
    for e in events:
        try:
            t = e.get("time") or "23:59"
            dt = datetime.fromisoformat(f'{e["date"]}T{t}').replace(tzinfo=JST)
        except Exception:
            continue

        has_actual = any(clean_market_value(m.get("actual")) for m in e.get("metrics", []))
        if dt <= now and not has_actual and e.get("metrics"):
            e["rate_signal"] = "missing"
            e["rate_signal_label"] = "結果未取得"

def main():
    previous_payload = load_previous_payload()
    events = []
    errors = []

    for label, fn in [("BLS", fetch_bls), ("BEA", fetch_bea), ("Fed", fetch_fed)]:
        try:
            fn(events)
        except Exception as ex:
            errors.append(f"{label}: {ex}")

    ensure_fallbacks(events)
    events = merge_duplicates(events)
    ensure_metric_placeholders(events)

    # Keep previously captured historical data before trying today's sources.
    merge_saved_history(events, previous_payload)
    append_historical_only_events(events, previous_payload)

    # Official historical actual/previous values first.
    enrich_from_bls_official(events, errors)

    te = fetch_te(errors)
    qs = fetch_quotestream(errors)

    # Market sources mainly supplement forecasts; official BLS actuals are retained.
    enrich_from_te(events, te)
    enrich_from_quotestream(events, qs)

    # Re-merge to make sure transient upstream gaps never erase saved values.
    ensure_metric_placeholders(events)
    merge_saved_history(events, previous_payload)

    calculate_signals(events)
    set_missing_result_status(events)

    events = sorted(events, key=lambda e: (e.get("date",""), e.get("time",""), e.get("name","")))

    payload = {
        "updated_at": datetime.now(UTC).isoformat(),
        "events": events,
        "errors": errors,
        "data_sources": {
            "schedule": ["BLS", "BEA", "Federal Reserve", "fixed fallback"],
            "market_values": ["BLS official API (historical actual/previous)", "Trading Economics", "public economic-calendar fallback"],
            "history_policy": "Captured values are retained for 365 days and are never erased by a later failed fetch.",
        },
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(events)} events")
    print("errors:", errors)

    if not events:
        sys.exit(1)

if __name__ == "__main__":
    main()
