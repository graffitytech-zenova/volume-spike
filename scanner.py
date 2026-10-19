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
            df['DATE'] = pd.to_datetime(d.date())
            df['DEL%'] = df['DELIV_QTY']/df['TTL_TRD_QNTY']*100
            all_data.append(df[['DATE','SYMBOL','CLOSE_PRICE','DELIV_QTY','TTL_TRD_QNTY','DEL%']])
    except Exception as e:
        print(f"Skip {d.date()} {e}")
    time.sleep(0.5)

if not all_data:
    print("No data fetched")
    exit()

full = pd.concat(all_data).sort_values(['SYMBOL','DATE'])
latest_date = full['DATE'].max()

def calc_avg(g):
    g = g.sort_values('DATE')
    g['AVG_30D'] = g['DELIV_QTY'].shift(1).rolling(30, min_periods=10).mean()
    return g

full = full.groupby('SYMBOL', group_keys=False).
