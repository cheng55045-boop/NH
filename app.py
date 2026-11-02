import yfinance as yf
import pandas as pd
from datetime import datetime
import json
import requests
import io

def get_all_taiwan_stocks():
    """自動從公開來源取得上市櫃股票代號清單"""
    stock_list = []
    try:
        # 抓取臺灣證券交易所上市股票代號 (TWSE)
        url_twse = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = requests.get(url_twse, timeout=10)
        res.encoding = 'big5'
        df_twse = pd.read_html(io.StringIO(res.text))[0]
        df_twse.columns = df_twse.iloc[0]
        df_twse = df_twse.iloc[1:]
        
        for row in df_twse['有價證券代號及名稱']:
            if pd.notna(row) and '\u3000' in row:
                code = row.split('\u3000')[0].strip()
                if len(code) == 4 and code.isdigit():
                    stock_list.append(code + ".TW")
                    
        # 抓取櫃買中心上櫃股票代號 (TPEX)
        url_tpex = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
        res_t = requests.get(url_tpex, timeout=10)
        res_t.encoding = 'big5'
        df_tpex = pd.read_html(io.StringIO(res_t.text))[0]
        df_tpex.columns = df_tpex.iloc[0]
        df_tpex = df_tpex.iloc[1:]
        
        for row in df_tpex['有價證券代號及名稱']:
            if pd.notna(row) and '\u3000' in row:
                code = row.split('\u3000')[0].strip()
                if len(code) == 4 and code.isdigit():
                    stock_list.append(code + ".TWO")
    except Exception as e:
        print(f"自動取得股票清單失敗，將使用預設核心清單: {e}")
        stock_list = ["2330.TW", "2317.TW", "2454.TW", "2308.TW", "2603.TW", "2382.TW", "3231.TW", "2881.TW", "2882.TW", "3034.TW"]
        
    return list(set(stock_list))

def fetch_and_analyze():
    results = []
    stock_symbols = get_all_taiwan_stocks()
    print(f"總共取得 {len(stock_symbols)} 檔台股標的，開始進行全市場三日 K 波段篩選...")
    
    for symbol in stock_symbols:
        try:
            # 抓取足夠的日 K 歷史數據
            df = yf.download(symbol, period="2y", interval="1d", progress=False)
            if df.empty or len(df) < 150:
                continue
                
            # 處理 MultiIndex 欄位問題
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
            
            # -------------------------------------------------------------
            # 第一關：47 天 K 棒重採樣與巨型突破判定
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
                
            prev_47_high = df_47['High'].iloc[-2]
            curr_47_close = df_47['Close'].iloc[-1]
            
            if curr_47_close <= prev_47_high:
                continue
                
            # -------------------------------------------------------------
            # 第二關：3 天 K 棒 (3D) 重採樣與波段底底高結構檢測
            # -------------------------------------------------------------
            df_3 = df.resample('3D').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()
            
            if len(df_3) < 10:
                continue
                
            # 取最近 8 根 3D K 棒來檢視波段回檔結構
            recent_lows = df_3['Low'].iloc[-8:].values
            mid = len(recent_lows) // 2
            early_low = recent_lows[:mid].min()
            late_low = recent_lows[mid:-1].min()
            
            # 條件 A：回檔低點墊高（底底高結構）
            is_higher_lows = late_low > early_low
            if not is_higher_lows:
                continue
                
            # -------------------------------------------------------------
            # 第三關：最新 3D K 棒收盤價高於前一根 3D K 棒的最高點 (突破確認)
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
            exit_price = float(curr_3_low) # 防守價：突破當根 3D K 棒的最低點
            
            latest_close = float(df['Close'].iloc[-1])
            prev_close = float(df['Close'].iloc[-2])
            change_pct = round(((latest_close - prev_close) / prev_close) * 100, 2)
            volume = int(df['Volume'].iloc[-1]) / 1000  # 轉換為張數
            
            # 略過成交量過低的殭屍股（小於 100 張）
            if volume < 100:
                continue
                
            # 嘗試取得股票名稱
            ticker = yf.Ticker(symbol)
            info = ticker.info
            name = info.get('shortName', symbol.split('.')[0])
            
            results.append({
                "code": symbol.split('.')[0],
                "name": name,
                "close": latest_close,
                "change_pct": change_pct,
                "volume": int(volume),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "has_warning": False
            })
            
        except Exception as e:
            continue
            
    # 輸出結果至 data.json
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_count": len(results),
        "stocks": results
    }
    
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
    
    print(f"台股三日 K 掃描完成！共找到 {len(results)} 檔符合條件標的。")

if __name__ == "__main__":
    fetch_and_analyze()
