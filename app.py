import yfinance as yf
import pandas as pd
from datetime import datetime
import json

# 目標股票清單（可自行擴充）
STOCK_LIST = ["2330.TW", "2317.TW", "2454.TW", "2308.TW", "2603.TW", "2382.TW", "3231.TW", "2376.TW"]

def fetch_and_analyze():
    results = []
    
    for symbol in STOCK_LIST:
        try:
            # 抓取足夠的日 K 歷史數據
            df = yf.download(symbol, period="2y", interval="1d", progress=False)
            if df.empty or len(df) < 150:
                continue
                
            # 處理 MultiIndex 欄位問題
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            # 確保欄位名稱正確
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
            
            # -------------------------------------------------------------
            # 第一關：47 天 K 棒重採樣與突破判定
            # -------------------------------------------------------------
            df_47 = df.resample('47D').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()
            
            if len(df_47) < 2:
                continue
                
            # 檢查倒數第二根的 47 天 K 收盤價是否有高於更前一根的最高點（或依需求調整對應索引）
            # 這裡我們檢查最新完整或進行中的 47 天週期間關係
            prev_47_high = df_47['High'].iloc[-2]
            curr_47_close = df_47['Close'].iloc[-1]
            
            if curr_47_close <= prev_47_high:
                continue
                
            # -------------------------------------------------------------
            # 第二關：3 天 K 棒重採樣與底底高結構檢測
            # -------------------------------------------------------------
            df_3 = df.resample('3D').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()
            
            if len(df_3) < 4:
                continue
                
            # 檢查最近 3 個 3 天 K 棒是否呈現底底高 (Low 逐步墊高)
            l1 = df_3['Low'].iloc[-4]
            l2 = df_3['Low'].iloc[-3]
            l3 = df_3['Low'].iloc[-2]
            l4 = df_3['Low'].iloc[-1]
            
            is_higher_lows = (l4 > l3) and (l3 > l2)
            if not is_higher_lows:
                continue
                
            # -------------------------------------------------------------
            # 第三關：最新 3 天 K 收盤價高於前一根 3 天 K 的最高點
            # -------------------------------------------------------------
            prev_3_high = df_3['High'].iloc[-2]
            curr_3_close = df_3['Close'].iloc[-1]
            curr_3_low = df_3['Low'].iloc[-1]
            
            if curr_3_close <= prev_3_high:
                continue
                
            # -------------------------------------------------------------
            # 第四關：決定進場與出場價位
            # -------------------------------------------------------------
            entry_price = float(curr_3_close)
            exit_price = float(curr_3_low)
            
            latest_close = float(df['Close'].iloc[-1])
            prev_close = float(df['Close'].iloc[-2])
            change_pct = round(((latest_close - prev_close) / prev_close) * 100, 2)
            volume = int(df['Volume'].iloc[-1]) / 1000  # 轉換為張數
            
            # 嘗試取得股票名稱
            ticker = yf.Ticker(symbol)
            info = ticker.info
            name = info.get('shortName', symbol)
            
            results.append({
                "code": symbol.split('.')[0],
                "name": name,
                "close": latest_close,
                "change_pct": change_pct,
                "volume": int(volume),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "has_warning": False  # 符合突破與底底高，無黑吞警報
            })
            
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue
            
    # 輸出結果至 data.json
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_count": len(results),
        "stocks": results
    }
    
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    fetch_and_analyze()
