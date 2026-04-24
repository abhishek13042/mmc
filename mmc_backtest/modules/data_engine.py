import pandas as pd
import numpy as np
import os
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Initialize logger
logger = logging.getLogger('mmc.data_engine')

# --- CONSTANTS ---

SUPPORTED_INSTRUMENTS = ['EURUSD', 'GBPUSD', 'XAUUSD']

# MT5 file naming: {INSTRUMENT}{MINUTES}.csv
TF_MINUTE_MAP = {
    '5M':    5,
    '15M':   15,
    '1H':    60,
    '4H':    240,
    'DAILY': 1440,
    'WEEKLY': 10080,
    'MONTHLY': 43200
}

# Reverse lookup: minutes → TF name
MINUTE_TF_MAP = {v: k for k, v in TF_MINUTE_MAP.items()}

VALID_TIMEFRAMES = list(TF_MINUTE_MAP.keys())

# --- BACKWARD COMPATIBILITY ALIASES ---
VALID_INSTRUMENTS = SUPPORTED_INSTRUMENTS
VALID_TF_NAMES = VALID_TIMEFRAMES

PIP_MULTIPLIER = {
    'EURUSD': 10000,
    'GBPUSD': 10000,
    'XAUUSD': 10
}

def get_pip_multiplier(instrument: str) :
    """Returns the pip multiplier for the given instrument."""
    return PIP_MULTIPLIER.get(instrument.upper(), 10000)

RESAMPLE_RULES = {
    '5M': '5min',
    '15M': '15min',
    '1H': '1H',
    '4H': '4H',
    'DAILY': '1D'
}

DATA_DIR   = 'data/raw'     # where CSVs are stored
CACHE_DIR  = 'data/cache'   # where processed DataFrames cached as pickle

# --- GLOBAL BACKTEST STATE ---
BACKTEST_MODE = False
BACKTEST_END_DATE = None

def set_backtest_context(enabled: bool, end_date: str = None):
    """Enable/disable backtest mode to automatically truncate data."""
    global BACKTEST_MODE, BACKTEST_END_DATE
    BACKTEST_MODE = enabled
    BACKTEST_END_DATE = end_date

# Create directories on import
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

# --- IN-MEMORY CACHE ---
_DF_CACHE = {}

def get_csv_filename(instrument: str, timeframe: str) :
    """Returns the filename based on MT5 convention: {INSTRUMENT}{MINUTES}.csv"""
    tf_upper = timeframe.upper()
    if tf_upper == 'D1': tf_upper = 'DAILY'
    minutes = TF_MINUTE_MAP.get(tf_upper)
    if not minutes:
         raise ValueError(f"Invalid timeframe label: {timeframe}")
    return f"{instrument}{minutes}.csv"

def get_csv_path(instrument: str, timeframe: str) :
    """Returns the absolute path to the CSV file."""
    return os.path.join(DATA_DIR, get_csv_filename(instrument, timeframe))

def parse_mt5_csv(file_path: str, instrument: str, timeframe: str) -> pd.DataFrame:
    """Robust MT5 CSV parser. Handles both headered and headerless exports."""
    try:
        # 1. Read first few lines to detect header
        with open(file_path, 'r') as f:
            first_line = f.readline().strip()
            
        header_exists = '<DATE>' in first_line or 'DATE' in first_line.upper()
        
        if header_exists:
            df = pd.read_csv(file_path, sep=None, engine='python')
            df.columns = [c.upper().replace('<', '').replace('>', '') for c in df.columns]
        else:
            # Headerless fallback (Standard MT5: Date, [Time], Open, High, Low, Close, Vol)
            df = pd.read_csv(file_path, sep=None, engine='python', header=None)
            
            # Detect if col 0 is combined datetime or just date
            first_val = str(df.iloc[0, 0])
            if ':' in first_val and '-' in first_val: # Combined: 2024-12-16 17:10
                cols = ['datetime', 'open', 'high', 'low', 'close', 'volume']
                df.columns = cols + list(df.columns[len(cols):])
            else: # Split: 2024.12.16, 17:10
                cols = ['date', 'time', 'open', 'high', 'low', 'close', 'volume']
                df.columns = cols + list(df.columns[len(cols):])
                df['datetime'] = pd.to_datetime(df['date'].astype(str).str.replace('.', '-') + ' ' + df['time'].astype(str))
                df.set_index('datetime', inplace=True)

        if 'datetime' not in df.columns and not isinstance(df.index, pd.DatetimeIndex):
            if 'DATE' in df.columns and 'TIME' in df.columns:
                df['datetime'] = pd.to_datetime(df['DATE'].astype(str).str.replace('.', '-') + ' ' + df['TIME'].astype(str))
            elif 'DATETIME' in df.columns:
                df['datetime'] = pd.to_datetime(df['DATETIME'])
            else:
                df['datetime'] = pd.to_datetime(df.iloc[:, 0])
            df.set_index('datetime', inplace=True)
        elif 'datetime' in df.columns:
            df.set_index('datetime', inplace=True)

        # Standardize column names to lowercase OHLC
        col_map = {
            'OPEN': 'open', 'HIGH': 'high', 'LOW': 'low', 'CLOSE': 'close',
            'TICKVOL': 'tick_volume', 'VOL': 'volume', 'VOLUME': 'volume', 'SPREAD': 'spread'
        }
        df = df.rename(columns=lambda x: col_map.get(x.upper(), x.lower()))
        
        required = ['open', 'high', 'low', 'close']
        for col in required:
            if col not in df.columns:
                # If we still don't have it, try positional based on most common MT5 headerless
                # 1: Open, 2: High, 3: Low, 4: Close
                pos_map = {'open': 0, 'high': 1, 'low': 2, 'close': 3} # if date/time already index
                pass 

        # Final cleanup
        df = df[[c for c in df.columns if c in required or c in ['volume', 'tick_volume']]]
        
        # Ensure Index is Datetime and Columns are Numeric
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
            
        for col in required:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(subset=required, inplace=True)
        df.sort_index(inplace=True)
        return df
    except Exception as e:
        logger.error(f"Failed to parse MT5 CSV {file_path}: {e}")
        raise

def upload_and_process_csv(file_storage, instrument: str, timeframe: str):
    """Handler for Flask file uploads."""
    dest_path = get_csv_path(instrument, timeframe)
    file_storage.save(dest_path)
    try:
        df = load_and_cache(instrument, timeframe, force_reload=True)
        return True, f"Successfully processed {len(df)} candles for {instrument} {timeframe}"
    except Exception as e:
        return False, str(e)

def build_full_timeframe_stack(instrument: str):
    """Ensures all 5 required TFs are initialized and cached."""
    results = []
    for tf in VALID_TIMEFRAMES:
        try:
            load_and_cache(instrument, tf, force_reload=True)
            results.append(tf)
        except Exception as e:
            logger.warning(f"Build failed for {instrument} {tf}: {e}")
    return results

def load_csv_raw(instrument: str, timeframe: str) -> pd.DataFrame:
    """Fallback CSV loader for non-MT5 standard formats."""
    csv_path = get_csv_path(instrument, timeframe)
    try:
        df = pd.read_csv(csv_path)
        # Try to find a datetime column
        for col in df.columns:
            if 'date' in col.lower() or 'time' in col.lower():
                df['datetime'] = pd.to_datetime(df[col])
                df.set_index('datetime', inplace=True)
                break
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        logger.error(f"Failed to load raw CSV {csv_path}: {e}")
        return pd.DataFrame()

def load_and_cache(instrument: str, timeframe: str, force_reload: bool = False) -> pd.DataFrame:
    """Load from CSV and cache to disk (pickle) AND memory."""
    cache_key = f"{instrument}_{timeframe}"
    
    if not force_reload and cache_key in _DF_CACHE:
        return _DF_CACHE[cache_key]
        
    cache_path = os.path.join(CACHE_DIR, f"{instrument}_{timeframe}.pkl")
    
    if not force_reload and os.path.exists(cache_path):
        try:
            df = pd.read_pickle(cache_path)
            # Ensure Index is Datetime (Fix for TypeError Traceback)
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
            _DF_CACHE[cache_key] = df
            return df
        except Exception as e:
            logger.warning(f"Failed to read cache {cache_path}: {e}. Reloading from CSV.")
            
    csv_path = get_csv_path(instrument, timeframe)
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")
        
    df = parse_mt5_csv(csv_path, instrument, timeframe)
    df.to_pickle(cache_path)
    _DF_CACHE[cache_key] = df
    return df

def fetch_candles(instrument: str, timeframe: str, start_date=None, end_date=None, n_candles=None) -> pd.DataFrame:
    """Main data access function used by ALL other modules."""
    # 1. Validate instrument
    if instrument not in SUPPORTED_INSTRUMENTS:
        raise ValueError(f"Invalid instrument: {instrument}. Use: {SUPPORTED_INSTRUMENTS}")
        
    # 2. Validate timeframe
    # Handle aliases (e.g. D1 -> DAILY)
    timeframe_upper = timeframe.upper()
    if timeframe_upper == 'D1': timeframe_upper = 'DAILY'
    
    if timeframe_upper not in VALID_TIMEFRAMES:
        raise ValueError(f"Invalid timeframe: {timeframe}. Use: {VALID_TIMEFRAMES}")
        
    # 3. Load from cache
    df = load_and_cache(instrument, timeframe_upper)
    
    # 4. Apply date filters
    if start_date:
        df = df[df.index >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df.index <= pd.to_datetime(end_date)]
        
    # BACKTEST PROTECTION: Truncate data at global backtest time if enabled
    if BACKTEST_MODE and BACKTEST_END_DATE:
        df = df[df.index <= pd.to_datetime(BACKTEST_END_DATE)]
        
    if n_candles:
        df = df.tail(n_candles)
        
    if len(df) == 0:
        raise ValueError(f"No data after filtering for {instrument} {timeframe}")
        
    # 5. Reset and standardize for JSON/Scanners
    df.columns = [c.lower() for c in df.columns]
    # Keep datetime as Timestamp objects for high-performance comparison
    # but ensure it exists as a column too
    if 'datetime' not in df.columns:
        df = df.reset_index()
        
    return df

def get_data_status() -> Dict:
    """Returns available data status for all instruments and TFs."""
    status = {}
    for inst in SUPPORTED_INSTRUMENTS:
        status[inst] = {}
        for tf in VALID_TIMEFRAMES:
            csv_path = get_csv_path(inst, tf)
            file_exists = os.path.exists(csv_path)
            cache_path = os.path.join(CACHE_DIR, f"{inst}_{tf}.pkl")
            cached = os.path.exists(cache_path)
            
            data_info = {
                'available': False,
                'candles': None,
                'date_from': None,
                'date_to': None,
                'file_path': csv_path,
                'file_exists': file_exists,
                'cached': cached
            }
            
            if cached:
                try:
                    df = pd.read_pickle(cache_path)
                    data_info['available'] = True
                    data_info['candles'] = len(df)
                    data_info['date_from'] = str(df.index[0].date())
                    data_info['date_to'] = str(df.index[-1].date())
                except:
                    pass
            elif file_exists:
                data_info['available'] = False # Needs loading
                
            status[inst][tf] = data_info
            
    return status

def initialize_all_data(data_directory: str = None):
    """Load ALL available CSV files into cache."""
    global DATA_DIR
    if data_directory:
        DATA_DIR = data_directory
        
    print("="*60)
    print("MMC DATA ENGINE — INITIALIZING")
    print("="*60)
    
    for inst in SUPPORTED_INSTRUMENTS:
        for tf in VALID_TIMEFRAMES:
            csv_path = get_csv_path(inst, tf)
            if os.path.exists(csv_path):
                try:
                    df = load_and_cache(inst, tf, force_reload=True)
                    print(f"OK {inst} {tf}: {len(df):,} candles")
                except Exception as e:
                    # Use ASCII symbols for better console compatibility
                    print(f"FAILED {inst} {tf}: {e}")
            else:
                print(f"  {inst} {tf}: Not found ({get_csv_filename(inst, tf)})")
                
    print("="*60)
    print("Data initialization complete")
    status = get_data_status()
    available = sum(1 for i in status.values() for t in i.values() if t['available'])
    total = len(SUPPORTED_INSTRUMENTS) * len(VALID_TIMEFRAMES)
    print(f"Available: {available}/{total} datasets")
    print("="*60)

def validate_data_for_strategy(strategy_id: str, instrument: str) -> Dict:
    """Check if all required TFs exist for a strategy."""
    from strategies.strategy_definitions import STRATEGY_MAP
    
    strategy = STRATEGY_MAP.get(strategy_id)
    if not strategy:
        return {'valid': False, 'message': 'Strategy not found'}
        
    reqs = strategy.get('data_requirements', {})
    missing_tfs = []
    available_tfs = []
    
    status = get_data_status().get(instrument, {})
    
    for tf_name in reqs.keys():
        # Handle aliasing
        tf_key = tf_name.upper()
        if tf_key == 'D1': tf_key = 'DAILY'
        
        info = status.get(tf_key, {})
        if info.get('available'):
            available_tfs.append(tf_name)
        else:
            missing_tfs.append(tf_name)
            
    valid = len(missing_tfs) == 0
    return {
        'valid': valid,
        'missing_tfs': missing_tfs,
        'available_tfs': available_tfs,
        'message': "Data OK" if valid else f"Missing timeframes: {', '.join(missing_tfs)}"
    }
