import pandas as pd
import numpy as np

def scalar(x):
    """Convert a Pandas Series/Index or NumPy array with one element to a Python float."""
    try:
        if hasattr(x, 'item'):
            return float(x.item())
        return float(np.array(x).flatten()[0])
    except Exception:
        return 0.0
