import os
import json
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime

# 1. 自動獲取台股上市/上櫃全股票清單 (從證券交易所/櫃買中心 API)
def get_taiwan_stock_list():
    stocks = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 上市股票 API
    try:
        url_twse = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        res = requests.get(url_twse, headers=headers, timeout=10)
        if res.status_code == 200:
            for item in res.json():
                code = item.get('Code', '')
                name = item.get('Name', '')
                if len(code) == 4 and code.isdigit():
                    stocks.append({'code': code, 'name': name, 'market': 'TWSE', 'ticker': f"{code}.TW"})
    except Exception as e:
        print(f"獲取上市股票失敗: {e}")

    # 上櫃股票 API
    try:
        url_tpex = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
        res = requests.get(url_tpex, headers=headers, timeout=10)
        if res.status_code == 200:
            for item in res.json():
                code = item.get('SecuritiesCompanyCode', '')
                name = item.get('CompanyName', '')
                if len(code) == 4 and code.isdigit():
                    stocks.append({'code': code, 'name': name, 'market': 'TPEx', 'ticker': f"{code}.TWO"})
    except Exception as e:
        print(f"獲取上櫃股票失敗: {e}")

    return stocks

def run_screener():
    print("🚀 開始獲取台股上市櫃個股清單...")
    stocks = get_taiwan_stock_list()
    print(f"共獲取 {len(stocks)} 檔個股，準備分析收盤價...")

    results = []
    tickers = [s['ticker'] for s in stocks]
    
    # 批次下載歷史資料 (預設抓取近 1 年 K 線)
    batch_size = 100
    for i in range(0, len(tickers), batch_size):
        batch_tickers = tickers[i:i+batch_size]
        try:
            data = yf.download(batch_tickers, period="1y", group_by='ticker', progress=False)
            
            for stock in stocks[i:i+batch_size]:
                ticker = stock['ticker']
                try:
                    df = data[ticker] if len(batch_tickers) > 1 else data
                    df = df.dropna(subset=['Close'])
                    
                    if len(df) < 60:
                        continue
                        
                    # 計算均線
                    df['MA5'] = df['Close'].rolling(5).mean()
                    df['MA20'] = df['Close'].rolling(20).mean()
                    df['MA60'] = df['Close'].rolling(60).mean()
                    df['VolMA5'] = df['Volume'].rolling(5).mean()

                    latest = df.iloc[-1]
                    prev = df.iloc[-2]
                    
                    close_p = float(latest['Close'])
                    open_p = float(latest['Open'])
                    high_p = float(latest['High'])
                    low_p = float(latest['Low'])
                    volume = float(latest['Volume'])
                    prev_close = float(prev['Close'])
                    
                    change = close_p - prev_close
                    change_pct = (change / prev_close) * 100

                    # 判斷近 20日/60日 最高價 (不含今日)
                    past_20d_high = float(df['Close'].iloc[-21:-1].max())
                    past_60d_high = float(df['Close'].iloc[-61:-1].max())
                    
                    ma5_p = float(latest['MA5'])
                    ma20_p = float(latest['MA20'])
                    ma60_p = float(latest['MA60'])
                    vol_ma5 = float(latest['VolMA5'])

                    # 篩選核心邏輯：站上 20MA 且 創近 20 日收盤新高
                    is_above_ma20 = close_p >= ma20_p
                    is_new_high_20d = close_p > past_20d_high

                    if is_above_ma20 and is_new_high_20d:
                        results.append({
                            "code": stock["code"],
                            "name": stock["name"],
                            "market": stock["market"],
                            "close": round(close_p, 2),
                            "change": round(change, 2),
                            "change_pct": round(change_pct, 2),
                            "volume": int(volume),
                            "is_vol_breakout": volume > vol_ma5,
                            "ma5": round(ma5_p, 2),
                            "ma20": round(ma20_p, 2),
                            "ma60": round(ma60_p, 2),
                            "high_20d": round(past_20d_high, 2),
                            "high_60d": round(past_60d_high, 2),
                            "is_new_high_60d": close_p > past_60d_high,
                            "breakout_pct_20d": round(((close_p - past_20d_high) / past_20d_high) * 100, 2)
                        })
                except Exception as e:
                    continue
        except Exception as e:
            print(f"批次下載失敗 {i}: {e}")

    # 輸出資料與時間戳記
    output_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_count": len(results),
        "stocks": results
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"✅ 篩選完成！共找到 {len(results)} 檔符合條件個股，數據已寫入 data.json")

if __name__ == "__main__":
    run_screener()
