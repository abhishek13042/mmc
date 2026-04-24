import sys, os
import pandas as pd
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../../..')))

from mmc_backtest.modules.video1_pd_arrays import (
    scan_candles_for_fvgs, get_pip_multiplier
)
from mmc_backtest.modules.video3_4_order_flow import (
    scan_candles_for_ofls
)
from mmc_backtest.backtest.data_loader import fetch_candles

def scan_pch_pcl_sweep(df, instrument, timeframe) -> list[dict]:
    """
    Scan for PCH/PCL candle science sweep setups.
    Walk-forward: uses df.iloc[:i] at each position.
    Minimum window: 50 candles.
    """
    results  = []
    pip_mult = get_pip_multiplier(instrument)

    MIN_WICK = {
        'EURUSD': 0.0002,
        'GBPUSD': 0.0002,
        'XAUUSD': 0.20
    }
    min_wick = MIN_WICK.get(instrument, 0.0002)

    print(f"Scanning {len(df)} candles for Strategy 9: PCH/PCL Sweep...")

    # We need at least 2 candles ahead (i+1, i+2) to check for rejection and sweep
    # So we loop until len(df) - 2
    for i in range(50, len(df) - 2):
        window  = df.iloc[:i]
        c_curr  = df.iloc[i]     # current candle (first entry into FVG)
        c_next  = df.iloc[i + 1] # next candle (potential sweep)
        # Note: we check for rejection FVG in i+1 and i+2
        
        curr_dt = str(c_curr['datetime']) if 'datetime' in c_curr else str(df.index[i])

        try:
            # Step 1: Get FVGs in window
            fvgs = scan_candles_for_fvgs(window, instrument)
            if not fvgs:
                continue

            # Step 2: Find active context FVG (unmitigated)
            active_fvg = None
            for fvg in reversed(fvgs):
                if fvg.get('is_mitigated', True):
                    continue
                if fvg.get('fvg_type', 'RFVG') not in ['PFVG', 'BFVG']:
                    continue
                active_fvg = fvg
                break

            if not active_fvg:
                continue

            context_direction = active_fvg['direction']
            fvg_high = active_fvg['fvg_high']
            fvg_low  = active_fvg['fvg_low']

            # Step 3: Check if current candle is inside FVG zone
            if context_direction == 'BULLISH':
                in_zone = (c_curr['low'] <= fvg_high
                           and c_curr['high'] >= fvg_low)
            else:
                in_zone = (c_curr['high'] >= fvg_low
                           and c_curr['low'] <= fvg_high)

            if not in_zone:
                continue

            # Step 4: Check first candle did NOT reject
            # Look at 2 candles starting from current (i, i+1, i+2)
            # A rejection FVG would form if i+2's low > i's high (bullish)
            check_window = df.iloc[i:i+3]
            check_fvgs = scan_candles_for_fvgs(check_window, instrument)
            rejection_fvg_found = any(
                f['direction'] == context_direction
                for f in check_fvgs
            )
            if rejection_fvg_found:
                continue  # First candle DID reject — not this pattern

            # Step 5: Check if next candle sweeps PCH/PCL
            swept_level = None
            wick_size   = 0.0
            sweep_confirmed = False

            if context_direction == 'BULLISH':
                # PCL sweep: next candle goes below curr low then closes above
                if (c_next['low'] < c_curr['low']
                        and c_next['close'] > c_curr['low']):
                    swept_level     = c_curr['low']
                    wick_size       = c_curr['low'] - c_next['low']
                    sweep_confirmed = wick_size >= min_wick
            else:
                # PCH sweep: next candle goes above curr high then closes below
                if (c_next['high'] > c_curr['high']
                        and c_next['close'] < c_curr['high']):
                    swept_level     = c_curr['high']
                    wick_size       = c_next['high'] - c_curr['high']
                    sweep_confirmed = wick_size >= min_wick

            if not sweep_confirmed or swept_level is None:
                continue

            # Step 6: Find OFL in context direction
            ofls = scan_candles_for_ofls(window, instrument)
            supporting_ofl = None
            for ofl in reversed(ofls):
                if ofl['direction'] != context_direction:
                    continue
                if ofl['probability_label'] not in ['HIGH', 'MEDIUM']:
                    continue
                supporting_ofl = ofl
                break

            if not supporting_ofl:
                continue

            # Step 7: Calculate entry, SL, TP
            if context_direction == 'BULLISH':
                entry_price = fvg_low
                stop_loss   = supporting_ofl['swing_point_price']
            else:
                entry_price = fvg_high
                stop_loss   = supporting_ofl['swing_point_price']

            risk = abs(entry_price - stop_loss)
            if risk <= 0:
                continue

            risk_pips = risk * pip_mult

            if context_direction == 'BULLISH':
                tp_1r = entry_price + risk
                tp_2r = entry_price + risk * 2
                tp_4r = entry_price + risk * 4
            else:
                tp_1r = entry_price - risk
                tp_2r = entry_price - risk * 2
                tp_4r = entry_price - risk * 4

            # Minimum TP check
            if abs(tp_2r - entry_price) <= 0:
                continue

            results.append({
                'strategy':         'PCH_PCL_SWEEP',
                'instrument':       instrument,
                'timeframe':        timeframe,
                'signal_datetime':  curr_dt,
                'direction':        context_direction,
                'entry_price':      round(entry_price, 5),
                'stop_loss':        round(stop_loss, 5),
                'tp_1r':            round(tp_1r, 5),
                'tp_2r':            round(tp_2r, 5),
                'tp_4r':            round(tp_4r, 5),
                'risk_pips':        round(risk_pips, 2),
                'wick_size_pips':   round(wick_size * pip_mult, 2),
                'swept_level':      round(swept_level, 5),
                'sweep_type':       ('PCL' if context_direction == 'BULLISH'
                                     else 'PCH'),
                'context_fvg_type': active_fvg.get('fvg_type', 'UNKNOWN'),
                'context_fvg_high': round(fvg_high, 5),
                'context_fvg_low':  round(fvg_low, 5),
                'ofl_probability':  supporting_ofl['probability_label'],
                'conditions_met':   ['CONTEXT_ACTIVE', 'NO_REJECTION', 'SWEEP_CONFIRMED', 'OFL_SUPPORTED']
            })

        except Exception:
            continue

    return results
