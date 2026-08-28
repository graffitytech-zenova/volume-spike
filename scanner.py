import pandas as pd, requests, time, os
from datetime import datetime, timedelta
from io import StringIO

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

headers = {'User-Agent':'Mozilla/5.0','Referer':'https://www.nseindia.com/all-reports'}
s = requests.Session()
s.get("https://www.nseindia.com/all-reports", headers=headers)

all_data = []
for i in range(40):
    d = datetime.now() - timedelta(days=i)
    if d.weekday() >= 5: continue
    url = f"https://archives.nseindia.com/products/content/sec_bhavdata_full_{d.strftime('%d%m%Y')}.csv"
    try:
        r = s.get(url, headers=headers, timeout=15)
        if r.status_code==200 and 'SYMBOL' in r.text[:100]:
            df = pd.read_csv(StringIO(r.text))
            df.columns = [c.strip() for c in df.columns]
            df = df[df['SERIES'].astype(str).str.strip()=='EQ']
            for c in ['DELIV_QTY','TTL_TRD_QNTY','CLOSE_PRICE']:
                df[c] = pd.to_numeric(df[c].astype(str).str.replace(',',''), errors='coerce')
            df['DATE'] = d
            df['DEL%'] = df['DELIV_QTY']/df['TTL_TRD_QNTY']*100
            all_data.append(df[['DATE','SYMBOL','CLOSE_PRICE','DELIV_QTY','DEL%']])
    except: pass
    time.sleep(0.5)

full = pd.concat(all_data).sort_values('DATE')
latest_date = full['DATE'].max()

# Pichle din ka close nikalna Day Change ke liye
prev_date = full[full['DATE'] < latest_date]['DATE'].max()
latest = full[full['DATE']==latest_date]
prev = full[full['DATE']==prev_date][['SYMBOL','CLOSE_PRICE']].rename(columns={'CLOSE_PRICE':'PREV_CLOSE'})

avg_30 = full.groupby('SYMBOL')['DELIV_QTY'].mean().reset_index().rename(columns={'DELIV_QTY':'AVG_30D'})
m = pd.merge(latest, avg_30, on='SYMBOL')
m = pd.merge(m, prev, on='SYMBOL', how='left')

m['SPIKE'] = m['DELIV_QTY']/m['AVG_30D']
m['DAY_CHG%'] = (m['CLOSE_PRICE'] - m['PREV_CLOSE']) / m['PREV_CLOSE'] * 100
m = m[~m['SYMBOL'].str.contains('BEES|ETF|GOLD|LIQUID|NIFTY|GILT')]

final = m[(m['SPIKE']>=2.5) & (m['DEL%']>=60) & (m['CLOSE_PRICE']>30) & (m['DELIV_QTY']>50000)]
final = final.sort_values('SPIKE', ascending=False).head(15)

if not final.empty:
    msg = f"🔥 Accumulation Alert {latest_date.date()} (30D)\n\n"
    for _, r in final.iterrows():
        chg = r['DAY_CHG%']
        arrow = "🟢" if chg>0 else "🔴"
        msg += f"{arrow} {r['SYMBOL']} {r['SPIKE']:.1f}x | {r['DEL%']:.0f}% | {chg:+.1f}% | ₹{r['CLOSE_PRICE']:.0f}\n"
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
