from __future__ import annotations
import json, re, sys, hashlib
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from icalendar import Calendar

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'events.json'
ET = ZoneInfo('America/New_York')
JST = ZoneInfo('Asia/Tokyo')
UA = {'User-Agent':'Mozilla/5.0 rate-calendar/1.0'}

BLS_ICS='https://www.bls.gov/schedule/news_release/bls.ics'
BEA='https://www.bea.gov/news/schedule'
FED='https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'

KEEP_WORDS = {
    'Consumer Price Index': ('米CPI・コアCPI',5,'インフレ','CPI・コアCPIが予想を上回る','CPI・コアCPIが予想を下回る','最重要。上振れは米長期金利上昇を通じてSBG・NASDAQ・高PER半導体に逆風。'),
    'Employment Situation': ('米雇用統計',5,'雇用','雇用者数・平均時給が強く、失業率が低下','雇用・賃金が鈍化し、失業率が上昇','強い雇用は利下げ後ずれ観測を強めやすい。'),
    'Producer Price Index': ('米PPI',4,'インフレ','PPI・コアPPIが予想を上回る','PPIが予想を下回る','CPIやPCEに先行して金利が反応することがある。'),
    'Job Openings and Labor Turnover Survey': ('JOLTS 求人件数',3,'雇用','求人件数が予想より多い','求人減少・労働市場の緩み','求人増は賃金インフレ懸念を強めやすい。'),
    'Import and Export Price Indexes': ('輸出入物価指数',3,'インフレ','輸入物価が上昇','輸入物価が低下','輸入インフレの再加速は長期金利の上昇材料。'),
    'Productivity and Costs': ('生産性・単位労働コスト',3,'雇用','単位労働コストが上振れ','生産性改善・労働コスト鈍化','労働コスト上昇はサービスインフレ懸念につながる。'),
    'Real Earnings': ('実質賃金',2,'雇用','賃金が強い','賃金が弱い','消費・賃金インフレの補助材料。'),
}

def gid(*parts):
    return hashlib.sha1('|'.join(map(str,parts)).encode()).hexdigest()[:16]

def to_jst(dt):
    if not isinstance(dt, datetime):
        dt=datetime(dt.year,dt.month,dt.day,8,30,tzinfo=ET)
    elif dt.tzinfo is None:
        dt=dt.replace(tzinfo=ET)
    return dt.astimezone(JST)

def add(events, name, dt_jst, importance, category, source, url, up, down, impact):
    events.append({
        'id':gid(source,name,dt_jst.isoformat()), 'name':name,
        'date':dt_jst.strftime('%Y-%m-%d'),'time':dt_jst.strftime('%H:%M'),
        'importance':importance,'category':category,'source':source,'url':url,
        'up':up,'down':down,'impact':impact
    })

def fetch_bls(events):
    r=requests.get(BLS_ICS,headers=UA,timeout=25); r.raise_for_status()
    cal=Calendar.from_ical(r.content)
    for c in cal.walk('VEVENT'):
        summary=str(c.get('summary',''))
        matched=None
        for key,meta in KEEP_WORDS.items():
            if key.lower() in summary.lower(): matched=meta; break
        if not matched: continue
        raw=c.decoded('dtstart')
        j=to_jst(raw)
        name,imp,cat,up,down,impact=matched
        add(events,name,j,imp,cat,'BLS',BLS_ICS,up,down,impact)

def parse_bea_date(txt):
    # Examples: August 26 8:30 AM
    m=re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\s+(\d{1,2}:\d{2})\s+(AM|PM)',txt)
    if not m: return None
    year=datetime.now(ET).year
    dt=datetime.strptime(f'{year} {m.group(1)} {m.group(2)} {m.group(3)} {m.group(4)}','%Y %B %d %I:%M %p').replace(tzinfo=ET)
    return dt.astimezone(JST)

def fetch_bea(events):
    r=requests.get(BEA,headers=UA,timeout=25); r.raise_for_status()
    soup=BeautifulSoup(r.text,'html.parser')
    text=soup.get_text('\n',strip=True)
    # Search line-oriented text for release rows.
    lines=[re.sub(r'\s+',' ',x).strip() for x in text.splitlines() if x.strip()]
    for i,line in enumerate(lines):
        dt=parse_bea_date(line)
        if not dt: continue
        title=' '.join(lines[i+1:i+5])
        if 'Personal Income and Outlays' in title:
            add(events,'PCE・コアPCE / 個人所得・支出',dt,5,'インフレ','BEA',BEA,
                'コアPCEや個人消費が予想を上回る','コアPCEが予想を下回り、消費も減速','FRBが重視する物価指標。上振れはSBG・NASDAQ・半導体に逆風。')
        elif 'GDP' in title:
            add(events,'米GDP',dt,3,'景気','BEA',BEA,
                'GDPが上方修正・需要が強い','GDP下方修正・景気減速','強すぎる成長は利下げ後ずれ観測につながる。')
        elif 'International Trade in Goods and Services' in title:
            add(events,'米貿易収支',dt,2,'景気','BEA',BEA,
                '需要の強さや輸入物価圧力が意識される','景気減速が意識される','補助材料。単独での金利インパクトは通常小さめ。')

def fetch_fed(events):
    r=requests.get(FED,headers=UA,timeout=25); r.raise_for_status()
    soup=BeautifulSoup(r.text,'html.parser')
    text=' '.join(soup.stripped_strings)
    year=datetime.now(ET).year
    # Parse known meeting date patterns from 2026/2027 section conservatively.
    months='January|February|March|April|May|June|July|August|September|October|November|December'
    section=text[text.find(str(year)):]
    if str(year+1) in section: section=section[:section.find(str(year+1))]
    pat=re.compile(rf'({months})\s+(\d{{1,2}})-(\d{{1,2}})\*?')
    for m in pat.finditer(section):
        month,_,endday=m.groups()
        # Standard statement time 2:00 p.m. ET on second day; JST date shifts to next day in DST/standard time.
        dt=datetime.strptime(f'{year} {month} {endday} 14:00','%Y %B %d %H:%M').replace(tzinfo=ET).astimezone(JST)
        add(events,'FOMC 政策金利・声明',dt,5,'FRB','Federal Reserve',FED,
            'タカ派声明・利下げ後ずれ・インフレ警戒','ハト派声明・利下げ余地を示唆','米長期金利とNASDAQを大きく動かす最重要イベント。')
        add(events,'FRB議長会見',dt+timedelta(minutes=30),5,'FRB','Federal Reserve',FED,
            'インフレ警戒・引き締め長期化を示唆','景気減速・利下げ余地を強調','声明後に金利・株価の方向が反転することもある。')


TE_CAL = "https://api.tradingeconomics.com/calendar/country/united%20states"

TE_PATTERNS = {
    "米CPI・コアCPI": [
        ("コアCPI 前月比", ["Core Inflation Rate MoM", "Core CPI MoM"]),
        ("CPI 前月比", ["Inflation Rate MoM", "CPI MoM"]),
    ],
    "米雇用統計": [
        ("非農業部門雇用者数", ["Non Farm Payrolls", "Nonfarm Payrolls"]),
        ("平均時給 前月比", ["Average Hourly Earnings MoM"]),
        ("失業率", ["Unemployment Rate"]),
    ],
    "米PPI": [
        ("PPI 前月比", ["Producer Prices MoM", "PPI MoM"]),
        ("コアPPI 前月比", ["Core Producer Prices MoM", "Core PPI MoM"]),
    ],
    "JOLTS 求人件数": [
        ("JOLTS求人件数", ["JOLTs Job Openings", "JOLTS Job Openings"]),
    ],
    "PCE・コアPCE / 個人所得・支出": [
        ("コアPCE 前月比", ["Core PCE Price Index MoM"]),
        ("PCE 前月比", ["PCE Price Index MoM"]),
        ("個人消費 前月比", ["Personal Spending MoM"]),
    ],
    "米GDP": [
        ("GDP成長率", ["GDP Growth Rate", "GDP Growth Rate QoQ"]),
    ],
    "輸出入物価指数": [
        ("輸入物価 前月比", ["Import Prices MoM"]),
    ],
    "生産性・単位労働コスト": [
        ("単位労働コスト", ["Unit Labour Costs", "Unit Labor Costs"]),
        ("非農業部門生産性", ["Nonfarm Productivity", "Non Farm Productivity"]),
    ],
}

def _num(v):
    if v in (None, "", "N/A", "NaN"): return None
    s=str(v).strip().replace(",", "")
    mult=1
    if s.endswith("K"): mult=1_000; s=s[:-1]
    elif s.endswith("M"): mult=1_000_000; s=s[:-1]
    elif s.endswith("B"): mult=1_000_000_000; s=s[:-1]
    s=s.replace("%","")
    try: return float(s)*mult
    except Exception: return None

def _hawkish_for_metric(event_name, metric_label, actual, forecast):
    a,f=_num(actual),_num(forecast)
    if a is None or f is None: return 0
    # Higher values are normally more hawkish, except unemployment/jobless claims.
    inverse = any(k in metric_label.lower() for k in ["失業率","失業保険","jobless","unemployment"])
    # Productivity is generally disinflationary when stronger.
    if "生産性" in metric_label:
        inverse=True
    if abs(a-f) < 1e-12: return 0
    higher = a > f
    return (-1 if higher else 1) if inverse else (1 if higher else -1)

def fetch_te_calendar():
    # guest:guest is intentionally used as a no-signup fallback.
    # If Trading Economics limits the guest feed, the app simply shows "未取得".
    params={"c":"guest:guest","f":"json"}
    r=requests.get(TE_CAL,params=params,headers=UA,timeout=25)
    r.raise_for_status()
    data=r.json()
    return data if isinstance(data,list) else []

def enrich_with_market_data(events, errors):
    try:
        te=fetch_te_calendar()
    except Exception as ex:
        errors.append(f"MarketData: {ex}")
        return

    def matches(te_item, aliases):
        hay=(" ".join([
            str(te_item.get("Event","")),
            str(te_item.get("Category","")),
        ])).lower()
        return any(a.lower() in hay for a in aliases)

    for e in events:
        specs=TE_PATTERNS.get(e["name"], [])
        metrics=[]
        score=0
        for label,aliases in specs:
            candidates=[x for x in te if matches(x,aliases)]
            if not candidates: continue
            # Prefer the calendar item closest to the official release date.
            target=e["date"]
            candidates.sort(key=lambda x: (0 if str(x.get("Date",""))[:10]==target else 1, str(x.get("Date",""))))
            x=candidates[0]
            metric={
                "label": label,
                "actual": x.get("Actual") or "",
                "forecast": x.get("Forecast") or "",
                "previous": x.get("Previous") or "",
                "te_forecast": x.get("TEForecast") or "",
                "reference": x.get("Reference") or "",
            }
            metrics.append(metric)
            score += _hawkish_for_metric(e["name"], label, metric["actual"], metric["forecast"])
        if metrics:
            e["metrics"]=metrics
            if any(m.get("actual") for m in metrics):
                e["rate_signal"] = "up" if score>0 else ("down" if score<0 else "neutral")
                e["rate_signal_label"] = "金利上昇警戒" if score>0 else ("金利低下方向" if score<0 else "中立・まちまち")
            else:
                e["rate_signal"]="pending"
                e["rate_signal_label"]="発表待ち"
            e["market_data_source"]="Trading Economics consensus / official-source actuals"

def dedupe(events):
    seen=set(); out=[]
    for e in sorted(events,key=lambda x:(x['date'],x['time'],x['name'])):
        k=(e['name'],e['date'],e['time'])
        if k not in seen:
            seen.add(k);out.append(e)
    return out

def main():
    events=[]; errors=[]
    for label,fn in [('BLS',fetch_bls),('BEA',fetch_bea),('Fed',fetch_fed)]:
        try: fn(events)
        except Exception as ex: errors.append(f'{label}: {ex}')
    # Preserve previous events if one source fails, but replace successful-source data.
    if OUT.exists():
        try:
            old=json.loads(OUT.read_text())['events']
            failed={x.split(':',1)[0] for x in errors}
            source_map={'BLS':'BLS','BEA':'BEA','Fed':'Federal Reserve'}
            for fail in failed:
                src=source_map.get(fail)
                events.extend([e for e in old if e.get('source')==src])
        except Exception: pass
    enrich_with_market_data(events, errors)
    events=dedupe(events)
    payload={'updated_at':datetime.now(tz=ZoneInfo('UTC')).isoformat(),'events':events,'errors':errors}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'wrote {len(events)} events; errors={errors}')
    if not events: sys.exit(1)

if __name__=='__main__': main()
