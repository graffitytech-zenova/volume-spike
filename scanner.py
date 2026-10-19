import pandas as pd
import requests
import time
import os
from datetime import datetime, timedelta
from io import StringIO

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

headers = {'User-Agent':'Mozilla/5.0','Referer':'https://www.nseindia.com/all-reports'}
s = requests.Session()
s.get("https://www.nseindia.com/all-reports", headers=headers)

all_data = []
for i in range(45):
    d = datetime.now() - timedelta(days=i)
    if d.weekday() >= 5:
        continue
    url = "https://archives.nseindia.com/products/content/sec_bhavdata_full_%s.csv" % d.strftime('%d%m%Y')
    try:
        r = s.get(url, headers=headers, timeout=15)
        if r.status_code == 200 and 'SYMBOL' in r.text[:100]:
            df = pd.read_csv(StringIO(r.text))
            df.columns = [c.strip() for c in df.columns]
            df = df[df['SERIES'].astype(str).str.strip() == 'EQ']
            for c in ['DELIV_QTY','TTL_TRD_QNTY','CLOSE_PRICE']:
                df[c] = pd.to_numeric(df[c].astype(str).str.replace(',',''), errors='coerce')
            df['DATE'] = pd.to_datetime(d.date())
            df['DEL%'] = df['DELIV_QTY'] / df['TTL_TRD_QNTY'] * 100
            cols = ['DATE','SYMBOL','CLOSE_PRICE','DELIV_QTY','TTL_TRD_QNTY','DEL%']
            all_data.append(df[cols])
    except:
        print("Skip")
    time.sleep(0.5)

full = pd.concat(all_data)
full = full.sort_values(['SYMBOL','DATE'])
latest_date = full['DATE'].max()

full['AVG_30D'] = 0.0
for sym in full['SYMBOL'].unique():
    mask = full['SYMBOL'] == sym
    sub = full[mask].sort_values('DATE')
    avg_vals = sub['DELIV_QTY'].shift(1).rolling(30, min_periods=10).mean()
    full.loc[mask, 'AVG_30D'] = avg_vals.values

full['SPIKE'] = full['DELIV_QTY'] / full['AVG_30D']

EXCLUDE = 'BEES|ETF|GOLD|LIQUID|NIFTY|GILT|REIT|INVIT|BOND|SETF|MAMC|SENSEX|HNGSNGBEES|BSE500|NIF100|NIF50|NEXT50'
full = full[~full['SYMBOL'].str.contains(EXCLUDE, case=False, na=False)]

# 1. ACCUMULATION ALERT - Aaj ka spike
latest = full[full['DATE'] == latest_date]
acc = latest[(latest['SPIKE'] >= 4) & (latest['DEL%'] >= 60) & (latest['DELIV_QTY'] > 30000) & (latest['CLOSE_PRICE'] > 30)]
acc = acc.sort_values('SPIKE', ascending=False).head(15)

# 2. MOMENTUM ALERT - Follow up buying
results = []
for sym, g in full.groupby('SYMBOL'):
    g = g.sort_values('DATE')
    recent = g[g['DATE'] >= latest_date - timedelta(days=7)]
    cond = (recent['SPIKE'] >= 2.5) & (recent['DEL%'] >= 60) & (recent['DELIV_QTY'] > 50000) & (recent['CLOSE_PRICE'] > 30)
    spikes = recent[cond]
    if spikes.empty:
        continue
    spike_row = spikes.sort_values('DATE').iloc[-1]
    spike_date = spike_row['DATE']
    spike_close = spike_row['CLOSE_PRICE']
    after = g[g['DATE'] > spike_date].sort_values('DATE')
    if after.empty:
        continue
    cond2 = (after['DEL%'] >= 50) & (after['DELIV_QTY'] >= after['AVG_30D'] * 0.8)
    follow_days = len(after[cond2])
    latest_close = after['CLOSE_PRICE'].iloc[-1]
    hold_pct = (latest_close - spike_close) / spike_close * 100
    if follow_days >= 1 and hold_pct >= -2.5:
        results.append({
            'SYMBOL': sym,
            'SPIKE': spike_row['SPIKE'],
            'FOLLOW_UP': follow_days,
            'HOLD%': hold_pct,
            'LATEST_CLOSE': latest_close
        })

mom_df = pd.DataFrame(results)
if not mom_df.empty:
    mom_df = mom_df.sort_values(['FOLLOW_UP','SPIKE'], ascending=[False, False]).head(10)

# 3. SINGLE TELEGRAM MESSAGE
msg = ""
if not acc.empty:
    msg = msg + "🔥 Accumulation Alert %s (30D)\n\n" % str(latest_date.date())
    for _, r in acc.iterrows():
        # Calculate day change
        try:
            prev_close = full[(full['SYMBOL']==r['SYMBOL']) & (full['DATE']<latest_date)].sort_values('DATE').iloc[-1]['CLOSE_PRICE']
            chg = (r['CLOSE_PRICE'] - prev_close) / prev_close * 100
        except:
            chg = 0
        dot = "🟢" if chg >= 0 else "🔴"
        msg = msg + "%s %s %.1fx | %.0f%% | %+.1f%% | Rs%.0f\n" % (dot, r['SYMBOL'], r['SPIKE'], r['DEL%'], chg, r['CLOSE_PRICE'])

if not mom_df.empty:
    msg = msg + "\n💪 Momentum Alert %s (Follow-up)\n\n" % str(latest_date.date())
    for _, r in mom_df.iterrows():
        dot = "🟢" if r['HOLD%'] >= 0 else "🔴"
        msg = msg + "%s %s Spike %.1fx Follow %s/3 Hold %+.1f%% Rs%.0f\n" % (dot, r['SYMBOL'], r['SPIKE'], r['FOLLOW_UP'], r['HOLD%'], r['LATEST_CLOSE'])

if msg == "":
    msg = "No accumulation/momentum today"

print(msg)
if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
    requests.post("https://api.telegram.org/bot%s/sendMessage" % TELEGRAM_TOKEN, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
