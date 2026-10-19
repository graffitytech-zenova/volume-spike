import pandas as pd, requests, time, os
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
            # --- FIX YAHAN KIYA ---
            df['DATE'] = pd.to_datetime(d.date())
            df['DEL%'] = df['DELIV_QTY']/df['TTL_TRD_QNTY']*100
            all_data.append(df[['DATE','SYMBOL','CLOSE_PRICE','DELIV_QTY','TTL_TRD_QNTY','DEL%']])
    except Exception as e:
        print(f"Skip {d.date()} {e}")
    time.sleep(0.5)

full = pd.concat(all_data).sort_values(['SYMBOL','DATE'])
latest_date = full['DATE'].max()

def calc_avg(g):
    g = g.sort_values('DATE')
    g['AVG_30D'] = g['DELIV_QTY'].shift(1).rolling(30, min_periods=10).mean()
    return g

full = full.groupby('SYMBOL', group_keys=False).apply(calc_avg)
full['SPIKE'] = full['DELIV_QTY'] / full['AVG_30D']

EXCLUDE_KEYWORDS = 'BEES|ETF|GOLD|LIQUID|NIFTY|GILT|REIT|INVIT|BOND|SETF|MAMC|SENSEX|HNGSNGBEES'
full = full[~full['SYMBOL'].str.contains(EXCLUDE_KEYWORDS, case=False, na=False)]

def get_followup_stats(group):
    recent = group[group['DATE'] >= latest_date - timedelta(days=7)]
    spikes = recent[(recent['SPIKE']>=2.5) & (recent['DEL%']>=60) & (recent['DELIV_QTY']>50000) & (recent['CLOSE_PRICE']>30)]
    if spikes.empty:
        return None
    spike_row = spikes.sort_values('DATE').iloc[-1]
    spike_date = spike_row['DATE']
    spike_close = spike_row['CLOSE_PRICE']
    after = group[group['DATE'] > spike_date].sort_values('DATE')
    if after.empty:
        follow_days = 0
        hold_pct = 0.0
    else:
        follow_days = len(after[(after['DEL%']>=50) & (after['DELIV_QTY'] >= after['AVG_30D']*0.8)])
        last_close = after['CLOSE_PRICE'].iloc[-1] if not after.empty else spike_close
        hold_pct = (last_close - spike_close) / spike_close * 100
    return {
        'SYMBOL': spike_row['SYMBOL'],
        'SPIKE_DATE': spike_date,
        'SPIKE': spike_row['SPIKE'],
        'DEL%_SPIKE': spike_row['DEL%'],
        'CLOSE_SPIKE': spike_close,
        'LATEST_CLOSE': group[group['DATE']==latest_date]['CLOSE_PRICE'].values[0] if not group[group['DATE']==latest_date].empty else spike_close,
        'DELIV_QTY': spike_row['DELIV_QTY'],
        'FOLLOW_UP': follow_days,
        'HOLD%': hold_pct,
    }

results = []
for sym, g in full.groupby('SYMBOL'):
    stat = get_followup_stats(g)
    if stat:
        results.append(stat)

final_df = pd.DataFrame(results)

if not final_df.empty:
    final_df = final_df[(final_df['FOLLOW_UP']>=1) & (final_df['HOLD%']>=-2.
