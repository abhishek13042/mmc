import pandas as pd
import os
import glob
from datetime import datetime

# --- CONFIGURATION ---
DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw')

# Timeframe mapping from Arjo prompt
# Timeframe mapping to minute-based suffix for filenames
TIMEFRAME_MAP = {
    'DAILY':   '1440',
    '4H':      '240',
    '1H':      '60',
    '15M':     '15',
    '5M':      '5',
    '1M':      '1',
    'WEEKLY':  '10080',
    'MONTHLY': '43200'
}

def load_csv(filepath: str) -> pd.DataFrame:
    """
    Load a single MT5 CSV file. Returns clean DataFrame.
    Supports comma and tab delimiters and both 6-column and 9-column formats.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"MT5 CSV file not found at: {filepath}")

    # 1. Detect delimiter and schema
    # Read the first few lines to detect format
    with open(filepath, 'r') as f:
        first_line = f.readline()
        delimiter = '\t' if '\t' in first_line else ','
    
    # 2. Read the data
    try:
        # We don't use names yet as we want to detect the number of columns
        df = pd.read_csv(filepath, sep=delimiter, header=None)
    except Exception as e:
        raise ValueError(f"Failed to read CSV: {e}")

    col_count = len(df.columns)

    # 3. Handle specific formats
    if col_count >= 9:
        # Standard MT5 format: <DATE>, <TIME>, <OPEN>, <HIGH>, <LOW>, <CLOSE>, <TICKVOL>, <VOL>, <SPREAD>
        df = df.iloc[:, [0, 1, 2, 3, 4, 5]]
        df.columns = ['date', 'time', 'open', 'high', 'low', 'close']
        # Combine date and time
        df['datetime'] = pd.to_datetime(df['date'].astype(str) + ' ' + df['time'].astype(str)).dt.strftime('%Y-%m-%d %H:%M:%S')
    elif col_count >= 5:
        # Simplified/Newer format: <DATETIME>, <OPEN>, <HIGH>, <LOW>, <CLOSE>, (VOL)
        # Check if first column is combined datetime
        first_val = str(df.iloc[0, 0])
        if len(first_val.split()) >= 2 or '-' in first_val or '/' in first_val or '.' in first_val:
            # Looks like a combined datetime
            df = df.iloc[:, [0, 1, 2, 3, 4]]
            df.columns = ['datetime', 'open', 'high', 'low', 'close']
            # Standardize datetime format
            df['datetime'] = pd.to_datetime(df['datetime']).dt.strftime('%Y-%m-%d %H:%M:%S')
        else:
            raise ValueError(f"Unknown CSV format in {filepath}. Detected {col_count} columns but first column is not a recognized datetime.")
    else:
        raise ValueError(f"Invalid column count in {filepath}. Expected at least 5 columns, found {col_count}.")

    # 4. Clean up
    df = df[['datetime', 'open', 'high', 'low', 'close']].copy()
    for col in ['open', 'high', 'low', 'close']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df = df.dropna()

    # 5. Filter weekends (0=Monday, 6=Sunday)
    df['dt_obj'] = pd.to_datetime(df['datetime'])
    df = df[df['dt_obj'].dt.dayofweek < 5]
    df = df.drop(columns=['dt_obj'])

    # 6. Sort and reset index
    df = df.sort_values('datetime').reset_index(drop=True)

    return df

def get_available_data(data_dir: str = None) -> dict:
    """
    Scan data_dir for all CSV files.
    Returns dict like: {'EURUSD': ['1440', '240', '60', '15', '5', '1', 'D1', 'H4', 'H1', 'M15', 'M5', 'M1']}
    """
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR
    
    if not os.path.exists(data_dir):
        return {}

    files = glob.glob(os.path.join(data_dir, "*.csv"))
    inventory = {}

    for f in files:
        filename = os.path.basename(f).replace('.csv', '')
        # Try to split by common patterns like EURUSD1440 or EURUSD_D1
        # If it contains an underscore
        if '_' in filename:
            parts = filename.split('_')
            inst = parts[0]
            tf = parts[1]
        else:
            # Fallback: assume first 6 chars are instrument name (e.g. EURUSD)
            inst = filename[:6]
            tf = filename[6:]
        
        if inst not in inventory:
            inventory[inst] = []
        if tf not in inventory[inst]:
            inventory[inst].append(tf)
    
    return inventory

def fetch_candles(instrument: str, timeframe: str, data_dir: str = None) -> pd.DataFrame:
    """
    Load data for instrument + timeframe.
    Filename format: {INSTRUMENT}{MINUTES}.csv
    """
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR
    
    if timeframe not in TIMEFRAME_MAP:
        raise ValueError(f"Unsupported timeframe: {timeframe}. Use: {list(TIMEFRAME_MAP.keys())}")

    suffix = TIMEFRAME_MAP[timeframe]
    filepath = os.path.join(data_dir, f"{instrument}{suffix}.csv")
    
    if not os.path.exists(filepath):
        # Try a fallback with underscore just in case, but prioritize direct
        alt_path = os.path.join(data_dir, f"{instrument}_{suffix}.csv")
        if os.path.exists(alt_path):
            filepath = alt_path
        else:
            raise FileNotFoundError(f"No data found for {instrument} {timeframe} at {filepath}")

    print(f"Loading data from: {os.path.basename(filepath)}")
    return load_csv(filepath)

if __name__ == "__main__":
    # Test block
    print("--- MMC Data Loader Test ---")
    try:
        inv = get_available_data()
        print(f"Inventory: {inv}")
        
        if 'EURUSD' in inv:
            print("\nAttempting to load EURUSD DAILY...")
            df = fetch_candles('EURUSD', 'DAILY')
            print(f"Success! Loaded {len(df)} candles.")
            print("First 5 rows:")
            print(df.head())
            print("\nVerification: No weekends present?")
            df['day'] = pd.to_datetime(df['datetime']).dt.day_name()
            weekends = df[df['day'].isin(['Saturday', 'Sunday'])]
            if weekends.empty:
                print("[OK] Success: No Saturday or Sunday rows found.")
            else:
                print(f"[ERROR] Found {len(weekends)} weekend rows.")
        else:
            print("[ERROR] EURUSD data not found in inventory. Cannot run load test.")
            
    except Exception as e:
        print(f"[ERROR] Test Failed: {e}")
