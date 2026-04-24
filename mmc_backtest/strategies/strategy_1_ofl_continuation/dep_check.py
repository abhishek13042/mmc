import sys
try:
    import pandas as pd
    print("Pandas OK")
    import numpy as np
    print("Numpy OK")
    import sklearn
    print("Sklearn OK")
    import xgboost
    print("XGBoost OK")
    import tensorflow
    print("Tensorflow OK")
    import stable_baselines3
    print("Stable Baselines 3 OK")
    import shap
    print("SHAP OK")
    import plotly
    print("Plotly OK")
    import gymnasium
    print("Gymnasium OK")
    import scipy
    print("Scipy OK")
    import pyarrow
    print("Pyarrow OK")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)
print("ALL OK")
