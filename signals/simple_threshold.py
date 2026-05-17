import numpy as np

THRESHOLD = 0.475

def generate_signals(probs: np.ndarray) -> np.ndarray:
    signals = np.zeros(len(probs), dtype=np.int8)
    signals[probs[:, 2] > THRESHOLD] =  1
    signals[probs[:, 0] > THRESHOLD] = -1
    return signals
