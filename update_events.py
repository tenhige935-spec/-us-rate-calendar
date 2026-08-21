from __future__ import annotations
import json, re, sys, hashlib, os
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
                "source": m.get("source") or "",
            })
        if specs:
            e["metrics"] = merged

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
        start = (now - timedelta(days=10)).strftime("%Y-%m-%d")
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
    for m in e.get("metrics", []):
        if m.get("label") == label:
            if previous and not m.get("previous"):
                m["previous"] = previous
                m["source"] = source
            if forecast and not m.get("forecast"):
                m["forecast"] = forecast
                m["source"] = source
            if actual and not m.get("actual"):
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
                and aliases_match(str(x.get("Event", "")) + " " + str(x.get("Category", "")), aliases)
            ]
            if not matches:
                continue
            matches.sort(key=lambda x: 0 if str(x.get("Date", ""))[:10] == e["date"] else 1)
            x = matches[0]
            merge_metric(
                e, label,
                previous=x.get("Previous") or "",
                forecast=x.get("Forecast") or "",
                actual=x.get("Actual") or "",
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
                        previous=row.get("previous") if row.get("previous") != "—" else "",
                        forecast=row.get("forecast") if row.get("forecast") != "—" else "",
                        actual=row.get("actual") if row.get("actual") != "—" else "",
                        source="TradingView系公開カレンダー",
                    )
                    break

def calculate_signals(events):
    for e in events:
        score = 0
        has_actual = False
        for m in e.get("metrics", []):
            if m.get("actual"):
                has_actual = True
                score += hawkish_score(m.get("label", ""), m.get("actual"), m.get("forecast"))
        if not has_actual:
            e["rate_signal"] = "pending"
            e["rate_signal_label"] = "発表待ち"
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

def main():
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

    te = fetch_te(errors)
    qs = fetch_quotestream(errors)

    enrich_from_te(events, te)
    enrich_from_quotestream(events, qs)
    calculate_signals(events)

    payload = {
        "updated_at": datetime.now(UTC).isoformat(),
        "events": events,
        "errors": errors,
        "data_sources": {
            "schedule": ["BLS", "BEA", "Federal Reserve", "fixed fallback"],
            "market_values": ["Trading Economics", "TradingView-backed public calendar"],
        },
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(events)} events")
    print("errors:", errors)

    if not events:
        sys.exit(1)

if __name__ == "__main__":
    main()
