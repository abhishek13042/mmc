from modules.data_engine import fetch_candles
df_d = fetch_candles('EURUSD', 'DAILY')
df_h = fetch_candles('EURUSD', '1H')
print(f"Daily: {len(df_d)}, 1H: {len(df_h)}")
