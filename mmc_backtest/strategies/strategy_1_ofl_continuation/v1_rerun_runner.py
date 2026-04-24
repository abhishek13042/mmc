import subprocess
import os

TIMEFRAMES = ["DAILY", "4H", "1H", "15M", "5M"]
results = []

print("="*60)
print("   RE-RUNNING ORIGINAL BACKTEST.PY (STRUCTURAL SL)")
print("="*60)

for tf in TIMEFRAMES:
    print(f"[*] Running {tf}...")
    cmd = ["python", "c:\\Users\\Admin\\OneDrive\\Desktop\\MMC\\mmc_backtest\\strategies\\strategy_1_ofl_continuation\\backtest.py", "--timeframe", tf]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
        # Find the summary line: Win Rate: 21.53% | Total RR: 199.4
        for line in output.split("\n"):
            if "Win Rate:" in line:
                results.append(f"{tf}: {line.strip()}")
                print(f"  [+] {line.strip()}")
    except Exception as e:
        print(f"  [!] Error running {tf}: {e}")

print("\n" + "="*60)
print("   FINAL CONSOLIDATED RESULTS")
print("="*60)
for r in results:
    print(r)
