import json
from datetime import datetime
import pandas as pd
import yfinance as yf

# 監控的台股清單範例（可依需求自行擴充）
STOCK_LIST = [
    {"code": "2330", "name": "台積電", "market": "TW"},
    {"code": "2317", "name": "鴻海", "market": "TW"},
    {"code": "2454", "name": "聯發科", "market": "TW"},
    {"code": "2308", "name": "台達電", "market": "TW"},
    {"code": "2603", "name": "長榮", "market": "TW"},
]


def resample_k_bars(df, n):
  """將日K數據重採樣（Resample）為每 N 個交易日合成一根新 K 棒"""
  df = df.copy()
  df["Group"] = range(len(df)) // n
  resampled = df.groupby("Group").agg(
      {
          "Open": "first",
          "High": "max",
          "Low": "min",
          "Close": "last",
          "Volume": "sum",
      }
  )
  return resampled


def check_3d_higher_lows(df_3, count=3):
  """條件二：從 3 天 K 棒檢測「底底高 (Higher Lows)」結構"""
  if len(df_3) < count:
    return False
  lows = df_3["Low"].iloc[-count:].values
  # 檢查後一個低點是否大於前一個低點
  return all(lows[i] > lows[i - 1] for i in range(1, len(lows)))


def check_3d_bullish_engulfing(df_3):
  """條件三：從 3 天 K 棒檢測「紅吞」

  回傳：(是否紅吞, 進場價(收盤價), 出場/停損價(最低價))
  """
  if len(df_3) < 2:
    return False, 0.0, 0.0

  curr = df_3.iloc[-1]
  prev = df_3.iloc[-2]

  is_curr_green = curr["Close"] > curr["Open"]
  is_prev_red = prev["Close"] < prev["Open"]

  # 實體完全包覆邏輯
  engulfs = (
      is_curr_green
      and is_prev_red
      and curr["Open"] <= prev["Close"]
      and curr["Close"] >= prev["Open"]
  )

  if engulfs:
    entry_price = float(curr["Close"])  # 進場價：3天K棒紅吞的收盤價
    exit_price = float(curr["Low"])  # 出場價：3天K棒紅吞的最低點
    return True, entry_price, exit_price

  return False, 0.0, 0.0


def check_3d_bearish_warning(df_3):
  """警告標誌：從 3 天 K 棒檢測是否有「黑吞」出現"""
  if len(df_3) < 2:
    return False

  curr = df_3.iloc[-1]
  prev = df_3.iloc[-2]

  is_curr_red = curr["Close"] < curr["Open"]
  is_prev_green = prev["Close"] > prev["Open"]

  # 黑吞包覆邏輯
  engulfs = (
      is_curr_red
      and is_prev_green
      and curr["Open"] >= prev["Close"]
      and curr["Close"] <= prev["Open"]
  )
  return engulfs


def fetch_and_filter_stocks():
  filtered_stocks = []

  for stock in STOCK_LIST:
    symbol = f"{stock['code']}.TW"
    try:
      # 抓取近 1 年歷史數據
      df = yf.download(symbol, period="1y", progress=False)
      if df.empty or len(df) < 150:  # 確保有足夠的K棒資料計算47天與3天
        continue

      if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

      # 1. 建立 47 天 K 棒數據
      df_47 = resample_k_bars(df, 47)
      # 條件一：47天K棒的收盤價高於前一根47天K棒的最高點
      cond_47_breakout = False
      if len(df_47) >= 2:
        curr_47_close = df_47["Close"].iloc[-1]
        prev_47_high = df_47["High"].iloc[-2]
        cond_47_breakout = curr_47_close > prev_47_high

      if not cond_47_breakout:
        continue  # 若第一關 47天突破沒過，直接跳過

      # 2. 建立 3 天 K 棒數據
      df_3 = resample_k_bars(df, 3)

      # 條件二：3天K棒底底高
      is_hl = check_3d_higher_lows(df_3, count=3)
      if not is_hl:
        continue  # 必須符合 3天K棒底底高

      # 條件三：3天K棒紅吞（並取得進場價與出場價）
      is_engulf, entry_price, exit_price = check_3d_bullish_engulfing(df_3)
      if not is_engulf:
        continue  # 必須符合 3天K棒紅吞

      # 檢查是否有黑吞警告標誌
      has_bearish_warning = check_3d_bearish_warning(df_3)

      latest_daily = df.iloc[-1]
      prev_daily = df.iloc[-2]
      close = float(latest_daily["Close"])
      prev_close = float(prev_daily["Close"])
      change_pct = round(((close - prev_close) / prev_close) * 100, 2)
      volume = int(latest_daily["Volume"])

      filtered_stocks.append({
          "code": stock["code"],
          "name": stock["name"],
          "market": stock["market"],
          "close": close,
          "change_pct": change_pct,
          "volume": volume,
          "entry_price": entry_price,  # 3天K棒紅吞收盤價
          "exit_price": exit_price,  # 3天K棒紅吞最低點
          "has_warning": has_bearish_warning,  # 是否出現黑吞警告
      })

    except Exception as e:
      print(f"處理股票 {stock['code']} 時發生錯誤: {e}")

  output_data = {
      "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
      "total_count": len(filtered_stocks),
      "stocks": filtered_stocks,
  }

  with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output_data, f, ensure_ascii=False, indent=4)

  print(f"資料更新完成，共篩選出 {len(filtered_stocks)} 檔符合條件個股。")


if __name__ == "__main__":
  fetch_and_filter_stocks()
