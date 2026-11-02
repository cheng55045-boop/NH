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

def make_candles_from_present(df, n):
    """將日K從最新一天（現在）倒數回來，每 n 天打包成一根複合 K 棒"""
    df_rev = df.iloc[::-1].reset_index(drop=True)
    df_rev['group'] = df_rev.index // n
    
    df_agg = df_rev.groupby('group', sort=False).agg({
        'Open': 'last',   
        'High': 'max',
        'Low': 'min',
        'Close': 'first', 
        'Volume': 'sum'
    })
    return df_agg.iloc[::-1].reset_index(drop=True)

def fetch_and_analyze():
    results = []
    stock_symbols = get_all_taiwan_stocks()
    print(f"總共取得 {len(stock_symbols)} 檔台股標的，開始進行三日 K 策略篩選...")
    
    for symbol in stock_symbols:
        try:
            df = yf.download(symbol, period="2y", interval="1d", progress=False)
            if df.empty or len(df) < 150:
                continue
                
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
            
            # -------------------------------------------------------------
            # 第一關：從現在回推 47 個交易日大週期打包與突破判定
            # -------------------------------------------------------------
            df_47 = make_candles_from_present(df, 47)
            if len(df_47) < 2:
                continue
                
            prev_47_high = df_47['High'].iloc[-2]
            curr_47_close = df_47['Close'].iloc[-1]
            
            if curr_47_close <= prev_47_high:
                continue
                
            # -------------------------------------------------------------
            # 第二關：從現在回推每 3 根日 K 打包合成 3D 三日 K 棒，檢測底底高結構
            # -------------------------------------------------------------
            df_3 = make_candles_from_present(df, 3)
            if len(df_3) < 10:
                continue
                
            # 取最近 8 根 3D K 棒來檢視波段回檔結構
            recent_lows = df_3['Low'].iloc[-8:].values
            mid = len(recent_lows) // 2
            early_low = recent_lows[:mid].min()
            late_low = recent_lows[mid:-1].min()
            
            is_higher_lows = late_low > early_low
            if not is_higher_lows:
                continue
                
            # -------------------------------------------------------------
            # 第三關：最新 3D K 棒收盤價高於前一根 3D K 棒的最高點 (突破確認)
            # -------------------------------------------------------------
            prev_3_high = df_3['High'].iloc[-2]
            curr_3_close = df_3['Close'].iloc[-1]
            
            if curr_3_close <= prev_3_high:
                continue
                
            # -------------------------------------------------------------
            # 第四關：進場價與出場價（以突破當根 3D K 棒為準）
            # -------------------------------------------------------------
            entry_price = float(curr_3_close)
            # 防守價：抓「那根收盤後高於前一根三日K高點」的該根三日K棒之最低點
            exit_price = float(df_3['Low'].iloc[-1])
            
            latest_close = float(df['Close'].iloc[-1])
            prev_close = float(df['Close'].iloc[-2])
            change_pct = round(((latest_close - prev_close) / prev_close) * 100, 2)
            volume = int(df['Volume'].iloc[-1]) / 1000  # 轉換為張數
            
            if volume < 100:
                continue
                
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
