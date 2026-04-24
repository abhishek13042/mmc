import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from modules.data_engine import fetch_candles, SUPPORTED_INSTRUMENTS as VALID_INSTRUMENTS

# --- CONSTANTS ---
BIG_THREE_EVENTS = [
    'Non-Farm Employment Change',
    'FOMC Statement',
    'CPI y/y',
    'Core CPI m/m'
]

FOREX_KILLZONE = {
    'start': '02:00',
    'end':   '10:00',
    'timezone': 'America/New_York',
    'note': 'Highest forex volatility window'
}

INDICES_SESSION = {
    'start': '09:30',
    'end':   '16:00',
    'timezone': 'America/New_York',
    'note': 'Equities open to bond close'
}

INSTRUMENT_CURRENCIES = {
    'EURUSD': ['EUR', 'USD'],
    'GBPUSD': ['GBP', 'USD'],
    'XAUUSD': ['USD'] # Gold moves on USD news
}

DAYS_OF_WEEK = ['MONDAY','TUESDAY','WEDNESDAY','THURSDAY','FRIDAY']

VOLATILITY_SCORES = {
    'HIGH':   100,
    'MEDIUM': 60,
    'LOW':    20
}

def is_big_three_event(event_name, event_datetime_str):
    name_lower = event_name.lower()
    
    # NFP Check: contains 'Non-Farm Employment', on Friday, NOT 'ADP'
    if 'non-farm employment' in name_lower and 'adp' not in name_lower:
        dt = datetime.strptime(event_datetime_str, '%Y-%m-%d %H:%M:%S')
        if dt.weekday() == 4: # Friday
            return True
            
    # FOMC Check: contains 'FOMC Statement', NOT 'Minutes'
    if 'fomc statement' in name_lower and 'minutes' not in name_lower:
        return True
        
    # CPI Check: contains 'CPI' and is USD
    if 'cpi' in name_lower:
        # Currency check is usually handled by the caller, 
        # but the prompt says "CPI: contains 'CPI' AND currency is USD"
        # We'll assume the caller passes USD events here or handle it in add_news_event
        return True
        
    return False

def get_day_of_week(date_string):
    dt = datetime.strptime(date_string.split(' ')[0], '%Y-%m-%d')
    days = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY']
    day = days[dt.weekday()]
    if day in ['SATURDAY', 'SUNDAY']:
        return 'WEEKEND'
    return day

def affects_instrument(currency, instrument):
    curr_list = INSTRUMENT_CURRENCIES.get(instrument, [])
    return currency in curr_list

def classify_news_volatility(impact, is_big_three):
    if is_big_three or impact == "HIGH":
        return "HIGH"
    if impact == "MEDIUM":
        return "MEDIUM"
    return "LOW"

def add_news_event(event_name, currency, impact, event_datetime_str):
    is_bt = is_big_three_event(event_name, event_datetime_str)
    day = get_day_of_week(event_datetime_str)
    
    return {
        "event_name": event_name,
        "currency": currency,
        "impact": impact,
        "event_datetime": event_datetime_str,
        "is_big_three": is_bt,
        "day_of_week": day,
        "affects_eurusd": affects_instrument(currency, "EURUSD"),
        "affects_gbpusd": affects_instrument(currency, "GBPUSD"),
        "affects_xauusd": affects_instrument(currency, "XAUUSD"),
        "volatility_expected": classify_news_volatility(impact, is_bt)
    }

def get_weekly_news_schedule(news_events_list):
    schedule = {day: [] for day in DAYS_OF_WEEK}
    high_impact_days = set()
    bt_day = None
    
    for ev in news_events_list:
        day = ev['day_of_week']
        if day in schedule:
            schedule[day].append(ev)
            if ev['volatility_expected'] == "HIGH":
                high_impact_days.add(day)
            if ev['is_big_three']:
                bt_day = day
                
    # Calculate day before Big Three
    day_before_bt = None
    if bt_day:
        idx = DAYS_OF_WEEK.index(bt_day)
        if idx > 0:
            day_before_bt = DAYS_OF_WEEK[idx-1]
            
    return {
        "schedule": schedule,
        "high_impact_days": list(high_impact_days),
        "big_three_day": bt_day,
        "day_before_big_three": day_before_bt
    }

def determine_weekly_profile(weekly_schedule):
    high_days = weekly_schedule['high_impact_days']
    bt_day = weekly_schedule['big_three_day']
    
    if not high_days:
        return "MINIMAL"
        
    if len(high_days) >= 3:
        return "BALANCED"
        
    if bt_day == "FRIDAY" or "FRIDAY" in high_days:
        return "VOLATILE_LATE"
        
    if any(d in high_days for d in ["WEDNESDAY", "THURSDAY"]):
        return "VOLATILE_MID"
        
    if any(d in high_days for d in ["MONDAY", "TUESDAY"]):
        return "VOLATILE_EARLY"
        
    return "BALANCED"

def should_trade_today(instrument, date_string, news_events_list):
    day = get_day_of_week(date_string)
    schedule_data = get_weekly_news_schedule(news_events_list)
    
    relevant_events = [e for e in news_events_list if e['day_of_week'] == day and affects_instrument(e['currency'], instrument)]
    has_bt_today = any(e['is_big_three'] for e in relevant_events)
    has_high_today = any(e['volatility_expected'] == "HIGH" for e in relevant_events)
    
    # Rule: Day Before Big Three
    if day == schedule_data['day_before_big_three']:
        return {
            "should_trade": False,
            "volatility_rating": "LOW",
            "reason": "Day before Big Three = consolidation expected",
            "warnings": ["MMC Rule: Do not trade day before Big Three"]
        }
        
    # Rule: Big Three Day
    if has_bt_today:
        return {
            "should_trade": True,
            "volatility_rating": "HIGH",
            "reason": "Big Three day - trade ONLY after release",
            "warnings": [
                "Wait minimum 5 minutes after release",
                "Do not trade at exact release — slippage risk"
            ]
        }
        
    # Rule: High Impact news day
    if has_high_today:
        return {
            "should_trade": True,
            "volatility_rating": "HIGH",
            "reason": "High impact news supports volatility for trade ID",
            "warnings": []
        }
        
    # Rule: No news day
    if not relevant_events:
        return {
            "should_trade": False,
            "volatility_rating": "LOW",
            "reason": "No news = no volatility = consolidation likely",
            "warnings": []
        }
        
    return {
        "should_trade": True,
        "volatility_rating": "MEDIUM",
        "reason": "Normal trading day",
        "warnings": []
    }

def is_in_killzone(current_time_str, instrument):
    # current_time_str format: "HH:MM" (New York time)
    t = datetime.strptime(current_time_str, "%H:%M")
    
    is_fx = instrument in ["EURUSD", "GBPUSD", "XAUUSD"]
    
    if is_fx:
        start = datetime.strptime(FOREX_KILLZONE['start'], "%H:%M")
        end = datetime.strptime(FOREX_KILLZONE['end'], "%H:%M")
        in_kz = start <= t <= end
        return {
            "in_killzone": in_kz,
            "session_name": "FOREX_KILLZONE",
            "time_remaining_mins": int((end - t).total_seconds() / 60) if in_kz else 0
        }
    else: # Indices
        start = datetime.strptime(INDICES_SESSION['start'], "%H:%M")
        end = datetime.strptime(INDICES_SESSION['end'], "%H:%M")
        in_kz = start <= t <= end
        return {
            "in_killzone": in_kz,
            "session_name": "INDICES_SESSION",
            "time_remaining_mins": int((end - t).total_seconds() / 60) if in_kz else 0
        }

def get_volatility_for_day(instrument, day_of_week, news_events_list):
    relevant = [e for e in news_events_list if e['day_of_week'] == day_of_week and affects_instrument(e['currency'], instrument)]
    
    score = 0
    for e in relevant:
        score += VOLATILITY_SCORES.get(e['volatility_expected'], 20)
        
    score = min(score, 100)
    label = "LOW"
    if score >= 80: label = "HIGH"
    elif score >= 40: label = "MEDIUM"
    
    return {
        "volatility_score": score,
        "volatility_label": label,
        "supporting_news": [e['event_name'] for e in relevant]
    }

def does_time_support_id(instrument, current_datetime_str, news_events_list):
    # current_datetime_str format: "YYYY-MM-DD HH:MM:SS" (NY)
    dt = datetime.strptime(current_datetime_str, '%Y-%m-%d %H:%M:%S')
    time_str = dt.strftime("%H:%M")
    date_str = dt.strftime("%Y-%m-%d")
    
    kz = is_in_killzone(time_str, instrument)
    day_rec = should_trade_today(instrument, date_str, news_events_list)
    vol = get_volatility_for_day(instrument, get_day_of_week(date_str), news_events_list)
    
    supports = kz['in_killzone'] and day_rec['should_trade'] and vol['volatility_label'] != "LOW"
    
    reasons = []
    if kz['in_killzone']: reasons.append(f"Inside {kz['session_name']}")
    else: reasons.append(f"OUTSIDE session killzone")
    
    reasons.append(day_rec['reason'])
    
    return {
        "time_supports": supports,
        "reason": ". ".join(reasons),
        "volatility_rating": vol['volatility_label'],
        "in_killzone": kz['in_killzone'],
        "news_warning": day_rec['warnings']
    }

def analyze_weekly_time(instrument, news_events_list):
    schedule = get_weekly_news_schedule(news_events_list)
    profile = determine_weekly_profile(schedule)
    
    daily_vol = {}
    trading_days = []
    avoid_days = []
    
    for day in DAYS_OF_WEEK:
        v = get_volatility_for_day(instrument, day, news_events_list)
        daily_vol[day] = v
        
        # Simple recommendation logic
        if day == schedule['day_before_big_three']:
            avoid_days.append({"day": day, "reason": "Pre-Big Three consolidation"})
        elif v['volatility_label'] == "LOW":
            avoid_days.append({"day": day, "reason": "No significant news volatility"})
        else:
            trading_days.append(day)
            
    return {
        "instrument": instrument,
        "weekly_profile": profile,
        "trading_days_recommended": trading_days,
        "avoid_days": avoid_days,
        "big_three_warnings": [f"Big Three on {schedule['big_three_day']}"] if schedule['big_three_day'] else [],
        "daily_volatility": daily_vol,
        "overall_volatility": "HIGH" if profile != "MINIMAL" else "LOW"
    }
