import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
import time
import json
import warnings
from datetime import datetime

# Pure Python/Numpy Institutional Filter (No DLL Dependencies)
class SimpleInstitutionalFilter:
    def __init__(self, n_trees=10, max_depth=5):
        self.n_trees = n_trees
        self.max_depth = max_depth
        self.trees = []
    
    def fit(self, X, y):
        # Using a simple Stochastic Gradient Boosting approach in pure Numpy
        X_arr = X.values if hasattr(X, 'values') else X
        y_arr = y.values if hasattr(y, 'values') else y
        
        for _ in range(self.n_trees):
            # Bootstrapping
            idx = np.random.choice(len(X_arr), len(X_arr), replace=True)
            self.trees.append(self._build_tree(X_arr[idx], y_arr[idx], 0))
    
    def _build_tree(self, X, y, depth):
        if depth >= self.max_depth or len(np.unique(y)) <= 1:
            return np.mean(y)
        
        # Simple split on the best feature
        best_feat, best_val = 0, 0
        best_gain = -1
        
        for f in range(X.shape[1]):
            vals = np.unique(X[:, f])
            if len(vals) > 10: # Sample for speed
                vals = np.random.choice(vals, 10, replace=False)
            for v in vals:
                left_mask = X[:, f] <= v
                if left_mask.sum() == 0 or (~left_mask).sum() == 0: continue
                gain = self._gini_gain(y, left_mask)
                if gain > best_gain:
                    best_gain, best_feat, best_val = gain, f, v
        
        if best_gain == -1: return np.mean(y)
        
        left_mask = X[:, best_feat] <= best_val
        return {
            'feat': best_feat, 'val': best_val,
            'left': self._build_tree(X[left_mask], y[left_mask], depth + 1),
            'right': self._build_tree(X[~left_mask], y[~left_mask], depth + 1)
        }
    
    def _gini_gain(self, y, mask):
        def gini(p): return 1 - p**2 - (1-p)**2
        p_total = np.mean(y)
        p_left = np.mean(y[mask])
        p_right = np.mean(y[~mask])
        w_left = mask.sum() / len(y)
        return gini(p_total) - (w_left * gini(p_left) + (1 - w_left) * gini(p_right))

    def predict_proba(self, X):
        X_arr = X.values if hasattr(X, 'values') else X
        probs = []
        for x in X_arr:
            tree_probs = [self._traverse(x, t) for t in self.trees]
            probs.append(np.mean(tree_probs))
        return np.array(probs)

    def _traverse(self, x, node):
        if not isinstance(node, dict): return node
        if x[node['feat']] <= node['val']:
            return self._traverse(x, node['left'])
        else:
            return self._traverse(x, node['right'])

SKLEARN_AVAILABLE = False
TF_AVAILABLE = False
RL_AVAILABLE = False
ML_AVAILABLE = True # Our custom filter is available

# Suppress warnings
warnings.filterwarnings('ignore')

# Global Config
CONFIG = {
    "instrument": "EURUSD",
    "pip_mult": 10000,
    "buffer_pips": 2,
    "min_risk_pips": 3.0,
    "max_rr_cap": 10.0,
    "min_rr": 2.0,
    "win_threshold_rr": 1.0,
    "lstm_lookback": 50,
    "xgb_win_prob_threshold": 0.55,
    "data_path": r"c:\Users\Admin\OneDrive\Desktop\MMC\mmc_backtest\data\raw\EURUSD60.csv",
    "results_dir": r"c:\Users\Admin\OneDrive\Desktop\MMC\mmc_backtest\strategies\strategy_1_ofl_continuation\results"
}

# Fix Random Seeds
np.random.seed(42)
if TF_AVAILABLE:
    tf.random.set_seed(42)

# Ensure results directory exists
if not os.path.exists(CONFIG["results_dir"]):
    os.makedirs(CONFIG["results_dir"])

def get_pip_multiplier(instrument):
    if "JPY" in instrument or "XAU" in instrument:
        return 100
    return 10000

CONFIG["pip_mult"] = get_pip_multiplier(CONFIG["instrument"])

# ==========================================
# SECTION 1: DATA LOADING & FORENSIC ENGINE
# ==========================================

class ForensicEngine:
    def __init__(self, df, instrument):
        self.df = df
        self.instrument = instrument
        self.pip_mult = get_pip_multiplier(instrument)

    def scan_fvgs(self):
        """3-candle FVG detection: Bullish/Bearish and variants."""
        fvgs = []
        highs = self.df['high'].values
        lows = self.df['low'].values
        closes = self.df['close'].values
        dts = self.df['datetime'].values
        
        for i in range(2, len(self.df)):
            # Bullish FVG (PFVG)
            if lows[i] > highs[i-2] and closes[i-1] > highs[i-2]:
                fvgs.append({
                    'index': i,
                    'datetime': dts[i],
                    'direction': 'BULLISH',
                    'fvg_high': lows[i],
                    'fvg_low': highs[i-2],
                    'fvg_type': 'PFVG'
                })
            # Bearish FVG (PFVG)
            elif highs[i] < lows[i-2] and closes[i-1] < lows[i-2]:
                fvgs.append({
                    'index': i,
                    'datetime': dts[i],
                    'direction': 'BEARISH',
                    'fvg_high': lows[i-2],
                    'fvg_low': highs[i],
                    'fvg_type': 'PFVG'
                })
        return fvgs

    def scan_it_points(self):
        """All Swing Highs and Lows (Protection Levels)."""
        swings = []
        highs = self.df['high'].values
        lows = self.df['low'].values
        dts = self.df['datetime'].values
        
        for i in range(1, len(self.df) - 1):
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                swings.append({'index': i, 'datetime': dts[i], 'level': highs[i], 'type': 'IT_HIGH'})
            elif lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                swings.append({'index': i, 'datetime': dts[i], 'level': lows[i], 'type': 'IT_LOW'})
        return swings

    def scan_ofls(self, it_points, fvgs):
        """OFL = IT Point with FVG left in its wake (within next 5 candles)."""
        ofls = []
        fvg_idx = 0
        for it in it_points:
            while fvg_idx < len(fvgs) and fvgs[fvg_idx]['index'] <= it['index']:
                fvg_idx += 1
            check_idx = fvg_idx
            while check_idx < len(fvgs) and fvgs[check_idx]['index'] - it['index'] <= 5:
                f = fvgs[check_idx]
                if it['type'] == 'IT_LOW' and f['direction'] == 'BULLISH':
                    ofls.append({'datetime': f['datetime'], 'direction': 'BULLISH', 'swing_point_price': it['level'], 'probability_label': 'HIGH', 'fvg': f})
                elif it['type'] == 'IT_HIGH' and f['direction'] == 'BEARISH':
                    ofls.append({'datetime': f['datetime'], 'direction': 'BEARISH', 'swing_point_price': it['level'], 'probability_label': 'HIGH', 'fvg': f})
                check_idx += 1
        return ofls

def run_s1_backtest(df, instrument, htf_bias=None, htf_erl=None):
    print(f"[*] Starting Strategy 1 Backtest for {instrument}...")
    engine = ForensicEngine(df, instrument)
    
    print("    -> Scanning FVGs...")
    fvgs = engine.scan_fvgs()
    print(f"    -> Found {len(fvgs)} FVGs.")
    print("    -> Scanning IT Points...")
    it_points = engine.scan_it_points()
    print(f"    -> Found {len(it_points)} IT Points.")
    print("    -> Scanning OFLs...")
    ofls = engine.scan_ofls(it_points, fvgs)
    print(f"    -> Found {len(ofls)} OFLs.")
    
    # Pointer-based O(N) Scanning
    ofl_ptr = 0
    it_idx = 0
    active_ofls = []
    
    # Sort OFLs by datetime for pointer scanning
    ofls.sort(key=lambda x: x['datetime'])
    
    pip_mult = CONFIG['pip_mult']
    trades = []
    it_points.sort(key=lambda x: x['index'])
    recent_it_high = None
    recent_it_low = None
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    dts = df['datetime'].values
    
    # Debug counters
    c_fvg_touch = 0
    
    for i in range(50, len(df)):
        if i % 10000 == 0:
            print(f"    -> Progress: {i}/{len(df)} candles...")
        curr_close = closes[i]
        curr_high = highs[i]
        curr_low = lows[i]
        curr_dt = dts[i]
        
        # 1. Update IT Range and Equilibrium
        while it_idx < len(it_points) and it_points[it_idx]['index'] < i:
            it = it_points[it_idx]
            if it['type'] == 'IT_HIGH': recent_it_high = it['level']
            else: recent_it_low = it['level']
            it_idx += 1
            
        if recent_it_high is None or recent_it_low is None: continue
        equilibrium = (recent_it_high + recent_it_low) / 2
        
        # 2. Add newly formed OFLs to active list
        while ofl_ptr < len(ofls) and ofls[ofl_ptr]['datetime'] <= curr_dt:
            active_ofls.append(ofls[ofl_ptr])
            ofl_ptr += 1
            
        # 3. Check active OFLs for entry
        remaining_ofls = []
        for ofl in active_ofls:
            direction = ofl['direction']
            fvg = ofl['fvg']
            
            # Mitigation check (If price sweeps the swing point, the OFL is invalid)
            # Actually, standard mitigation is usually just FVG touch.
            # Let's say an OFL is removed once price touches it.
            
            # Entry Logic
            entry = fvg['fvg_low'] if direction == 'BULLISH' else fvg['fvg_high']
            
            # Check for touch
            if curr_low <= entry <= curr_high:
                # Potential Entry Found!
                
                # Discount/Premium Filter
                if (direction == 'BULLISH' and curr_close < equilibrium) or \
                   (direction == 'BEARISH' and curr_close > equilibrium):
                    
                    # 2.1 HTF Bias Filter
                    if htf_bias is not None:
                        current_bias = htf_bias[i]
                        # 1 = Bullish, 0 = Bearish, -1 = Neutral/None
                        if direction == 'BULLISH' and current_bias != 1: continue
                        if direction == 'BEARISH' and current_bias != 0: continue
                    
                    sl = ofl['swing_point_price'] - (CONFIG['buffer_pips'] / pip_mult) if direction == 'BULLISH' else \
                         ofl['swing_point_price'] + (CONFIG['buffer_pips'] / pip_mult)
                    
                    risk_pips = abs(entry - sl) * pip_mult
                    if risk_pips >= CONFIG['min_risk_pips']:
                        if htf_erl is not None:
                            erl = htf_erl[i]
                        else:
                            erl = recent_it_high if direction == 'BULLISH' else recent_it_low
                        
                        reward_pips = abs(erl - entry) * pip_mult
                        rr_to_erl = reward_pips / risk_pips
                        
                        if rr_to_erl >= CONFIG['min_rr']:
                            # Simulate Trade
                            outcome = None
                            rr_achieved = -1.0
                            for j in range(i + 1, min(i + 500, len(df))):
                                w_high = highs[j]; w_low = lows[j]
                                if direction == 'BULLISH':
                                    if w_low <= sl: outcome = 'LOSS'; break
                                    if w_high >= erl: outcome = 'WIN'; rr_achieved = min(rr_to_erl, CONFIG['max_rr_cap']); break
                                else:
                                    if w_high >= sl: outcome = 'LOSS'; break
                                    if w_low <= erl: outcome = 'WIN'; rr_achieved = min(rr_to_erl, CONFIG['max_rr_cap']); break
                            
                            if outcome:
                                trades.append({
                                    'datetime': curr_dt, 'index': i, 'direction': 1 if direction == 'BULLISH' else 0,
                                    'entry': entry, 'sl': sl, 'erl': erl, 'risk_pips': risk_pips, 'rr_to_erl': rr_to_erl,
                                    'rr_achieved': rr_achieved, 'win': 1 if outcome == 'WIN' else 0, 'ofl_probability': 2,
                                    'it_high': recent_it_high, 'it_low': recent_it_low, 'equilibrium': equilibrium,
                                    'fvg_high': fvg['fvg_high'], 'fvg_low': fvg['fvg_low']
                                })
                
                # Mitigation: once touched, remove from active
                continue 
            
            # If not touched, keep active
            remaining_ofls.append(ofl)
            
        active_ofls = remaining_ofls[-50:] # Limit to last 50 for performance
        
    return trades

def load_data(path):
    print(f"[*] Loading data from {path}...")
    df = pd.read_csv(path, sep='\t', header=None, names=['datetime', 'open', 'high', 'low', 'close', 'tick_volume'])
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values('datetime').reset_index(drop=True)
    print(f"[+] Loaded {len(df)} candles.")
    return df

# ==========================================
# SECTION 2: AI FEATURE FACTORY
# ==========================================

def build_ai_dataset(df, trades):
    print("[*] Building AI Feature Dataset...")
    features = []
    pip_mult = CONFIG['pip_mult']
    for t in trades:
        idx = t['index']
        lb = df.iloc[idx-10 : idx]; lb20 = df.iloc[idx-20 : idx]
        dt = pd.to_datetime(t['datetime'])
        feat = {
            'datetime': dt, 'hour_of_day': dt.hour, 'day_of_week': dt.dayofweek,
            'month': dt.month, 'quarter': (dt.month - 1) // 3 + 1,
            'london_session': 1 if 10 <= dt.hour <= 14 else 0, # Adjusted for MT5 (UTC+2/3)
            'ny_session': 1 if 15 <= dt.hour <= 19 else 0,     # Adjusted for MT5 (UTC+2/3)
            'asian_session': 1 if (dt.hour >= 22 or dt.hour <= 9) else 0,
            'direction': t['direction'], 'ofl_probability': t['ofl_probability'],
            'risk_pips': t['risk_pips'], 'rr_to_erl': t['rr_to_erl'],
            'rr_to_erl_capped': min(t['rr_to_erl'], CONFIG['max_rr_cap']),
            'range_size_pips': (t['it_high'] - t['it_low']) * pip_mult,
            'position_in_range': (t['entry'] - t['it_low']) / (t['it_high'] - t['it_low']) if (t['it_high'] - t['it_low']) != 0 else 0.5,
            'distance_from_eq_pips': abs(t['entry'] - t['equilibrium']) * pip_mult,
            'erl_distance_pips': abs(t['erl'] - t['entry']) * pip_mult,
            'fvg_size_pips': abs(t['fvg_high'] - t['fvg_low']) * pip_mult,
            'avg_candle_body_pips': lb.apply(lambda r: abs(r['close'] - r['open']), axis=1).mean() * pip_mult,
            'avg_range_pips': lb.apply(lambda r: (r['high'] - r['low']), axis=1).mean() * pip_mult,
            'directional_momentum': (lb['close'] > lb['open']).sum() - (lb['close'] < lb['open']).sum(),
            'volatility_ratio': ((df.iloc[idx]['high'] - df.iloc[idx]['low']) * pip_mult) / (lb20.apply(lambda r: (r['high'] - r['low']), axis=1).mean() * pip_mult + 1e-6),
            'dist_to_equilibrium': abs(t['entry'] - t['equilibrium']) * pip_mult,
            'is_in_discount': 1 if (t['direction'] == 1 and t['entry'] < t['equilibrium']) else 0,
            'win': t['win'], 'rr_achieved': t['rr_achieved'],
        }
        rr = t['rr_achieved']
        if rr < 1.0: feat['momentum_class'] = 0
        elif 1.0 <= rr < 5.0: feat['momentum_class'] = 1
        else: feat['momentum_class'] = 2
        features.append(feat)
    ai_df = pd.DataFrame(features)
    print(f"[+] Dataset created with shape {ai_df.shape}")
    ai_df.to_csv(os.path.join(CONFIG["results_dir"], "ai_training_dataset_s1.csv"), index=False)
    return ai_df

# ==========================================
# SECTION 3-6: ML/DL/RL FUNCTIONS
# ==========================================

def train_institutional_filter(ai_df):
    print("[*] Training Tier 1 Institutional Filter (Pure Python)...")
    exclude = ['datetime', 'win', 'rr_achieved', 'momentum_class']
    X = ai_df.drop(columns=exclude); y = ai_df['win']
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    # Simple Split
    split = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]
    
    model = SimpleInstitutionalFilter(n_trees=10, max_depth=4)
    model.fit(X_train, y_train)
    
    ai_df['ai_win_prob'] = model.predict_proba(X)
    
    print(f"[DEBUG] AI Training Complete. Max_Prob={ai_df['ai_win_prob'].max():.4f}, Sample Size={len(ai_df)}")
    return model, None, ai_df
    plt.savefig(os.path.join(CONFIG["results_dir"], "xgb_shap_summary.png")); plt.close()
    print(f"[+] XGBoost Training Complete. Best CV Accuracy: {best_score:.4f}")
    return model, scaler

def build_lstm_sequences(df, trades_df):
    print("[*] Building LSTM Sequences (Lookback: 50)...")
    X_seq = []; y_rr = []; y_class = []
    for _, t in trades_df.iterrows():
        idx = int(t['index'])
        if idx < CONFIG['lstm_lookback']: continue
        seq_df = df.iloc[idx - CONFIG['lstm_lookback'] : idx].copy()
        seq_df['body'] = abs(seq_df['close'] - seq_df['open']); seq_df['range'] = seq_df['high'] - seq_df['low']; seq_df['is_bullish'] = (seq_df['close'] > seq_df['open']).astype(int)
        cols = ['open', 'high', 'low', 'close', 'tick_volume', 'body', 'range']
        if 'tick_volume' not in seq_df.columns and 'volume' in seq_df.columns: seq_df.rename(columns={'volume': 'tick_volume'}, inplace=True)
        seq_data = seq_df[cols].values; seq_min = seq_data.min(axis=0); seq_max = seq_data.max(axis=0); seq_norm = (seq_data - seq_min) / (seq_max - seq_min + 1e-8)
        X_seq.append(seq_norm); y_rr.append(t['rr_achieved']); y_class.append(int(t['momentum_class']))
    return np.array(X_seq), np.array(y_rr), np.array(y_class)

def train_lstm_models(X_seq, y_rr, y_class):
    if not ML_AVAILABLE: return None, None
    print("[*] Training Tier 2 LSTM Models...")
    reg_model = Sequential([Input(shape=(X_seq.shape[1], X_seq.shape[2])), LSTM(128, return_sequences=True), Dropout(0.2), LSTM(64), Dropout(0.2), Dense(32, activation='relu'), Dense(1, activation='linear')])
    reg_model.compile(optimizer='adam', loss='huber')
    clf_model = Sequential([Input(shape=(X_seq.shape[1], X_seq.shape[2])), LSTM(128, return_sequences=True), Dropout(0.2), LSTM(64), Dropout(0.2), Dense(32, activation='relu'), Dense(3, activation='softmax')])
    clf_model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])
    es = EarlyStopping(monitor='val_loss', patience=15, restore_best_weights=True)
    reg_model.fit(X_seq, y_rr, validation_split=0.2, epochs=50, batch_size=32, callbacks=[es], verbose=0)
    clf_model.fit(X_seq, y_class, validation_split=0.2, epochs=50, batch_size=32, callbacks=[es], verbose=0)
    print("[+] LSTM Models Training Complete.")
    return reg_model, clf_model

if RL_AVAILABLE:
    class TradingEnv(gym.Env):
        def __init__(self, ai_df):
            super(TradingEnv, self).__init__()
            self.df = ai_df.copy().reset_index(drop=True); self.current_step = 0
            self.observation_space = spaces.Box(low=-10, high=10, shape=(15,), dtype=np.float32)
            self.action_space = spaces.Discrete(4)
            self.obs_cols = ['hour_of_day', 'day_of_week', 'direction', 'ofl_probability', 'risk_pips', 'rr_to_erl', 'range_size_pips', 'position_in_range', 'distance_from_eq_pips', 'fvg_size_pips', 'avg_candle_body_pips', 'volatility_ratio', 'directional_momentum', 'xgb_win_prob', 'lstm_momentum_class']
            # Fill missing with 0
            for col in self.obs_cols:
                if col not in self.df.columns: self.df[col] = 0
            self.scaler = StandardScaler(); self.normalized_obs = self.scaler.fit_transform(self.df[self.obs_cols])
        def reset(self, seed=None, options=None):
            super().reset(seed=seed); self.current_step = 0; return self.normalized_obs[self.current_step], {}
        def step(self, action):
            trade = self.df.iloc[self.current_step]; reward = 0; win = trade['win']; rr = trade['rr_achieved']
            if action == 0: # SKIP
                if win == 1: reward = -0.5
                else: reward = 0.3
            elif action == 1: reward = rr if win == 1 else -1.0 # ENTER FULL
            elif action == 2: reward = (rr * 0.5) if win == 1 else -0.5 # ENTER HALF
            elif action == 3: # ENTER BE
                if win == 1: reward = rr
                else: reward = 0 if np.random.random() < 0.3 else -1.0
            self.current_step += 1; done = self.current_step >= len(self.df) - 1
            return self.normalized_obs[self.current_step], reward, done, False, {}

    def train_ppo_agent(ai_df):
        print("[*] Training Tier 3 PPO Agent...")
        env = TradingEnv(ai_df); model = PPO("MlpPolicy", env, learning_rate=3e-4, n_steps=512, batch_size=64, n_epochs=10, gamma=0.99, verbose=0)
        model.learn(total_timesteps=50000); print("[+] PPO Agent Training Complete."); return model, env

def plot_visuals(ai_df):
    print("[*] Generating Performance Visuals...")
    plt.style.use('dark_background')
    if 'ppo_reward' in ai_df.columns:
        plt.figure(figsize=(12, 6))
        plt.plot(ai_df['rr_achieved'].cumsum().values, label='Original Strategy', color='cyan')
        plt.plot(ai_df['ppo_reward'].cumsum().values, label='PPO Managed Agent', color='gold', linewidth=2)
        plt.title(f"Cumulative RR - {CONFIG['instrument']}"); plt.legend(); plt.savefig(os.path.join(CONFIG["results_dir"], "equity_curves.png")); plt.close()

# ==========================================
# MAIN EXECUTION
# ==========================================

if __name__ == "__main__":
    start_time = time.time()
    df = load_data(CONFIG["data_path"])
    trades = run_s1_backtest(df, CONFIG["instrument"])
    
    if not trades:
        print("[!] No trades found.")
    else:
        ai_df = build_ai_dataset(df, trades)
        if ML_AVAILABLE:
            xgb_model, scaler = train_xgb_classifier(ai_df)
            X_seq, y_rr, y_class = build_lstm_sequences(df, ai_df)
            lstm_reg, lstm_clf = train_lstm_models(X_seq, y_rr, y_class)
            
            # Pad LSTM results for alignment
            pad = len(ai_df) - len(X_seq)
            ai_df['lstm_predicted_rr'] = [0]*pad + list(lstm_reg.predict(X_seq).flatten())
            ai_df['lstm_momentum_class'] = [0]*pad + list(np.argmax(lstm_clf.predict(X_seq), axis=1))
            
            ppo_model, env = train_ppo_agent(ai_df)
            obs, _ = env.reset(); actions = []; rewards = []
            for i in range(len(ai_df)):
                action, _ = ppo_model.predict(obs, deterministic=True)
                obs, reward, done, _, _ = env.step(action); actions.append(action); rewards.append(reward)
                if done: break
            ai_df['ppo_action'] = actions + [0]*(len(ai_df)-len(actions))
            ai_df['ppo_reward'] = rewards + [0]*(len(ai_df)-len(rewards))
            
            plot_visuals(ai_df)
            print(f"\nPPO Total RR: {ai_df['ppo_reward'].sum():.2f}")
        else:
            print(f"\nBaseline Win Rate: {ai_df['win'].mean()*100:.2f}%")
            print(f"Baseline Total RR: {ai_df['rr_achieved'].sum():.2f}")
            
        print(f"\n[+] Complete in {time.time() - start_time:.2f}s. Results in {CONFIG['results_dir']}")
