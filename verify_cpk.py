
import numpy as np

def calculate_cpk(data, usl, lsl):
    mean = np.mean(data)
    std_dev = np.std(data, ddof=1)
    
    if std_dev == 0:
        return float('inf')

    cpu = (usl - mean) / (3 * std_dev) if usl is not None else float('inf')
    cpl = (mean - lsl) / (3 * std_dev) if lsl is not None else float('inf')
    cpk = min(cpu, cpl)
    return cpk

# Test cases
data = [10, 11, 12, 10, 11]
print(f"Data: {data}")
print(f"Mean: {np.mean(data)}, Std Dev: {np.std(data, ddof=1)}")

# Case 1: Both limits
usl = 15
lsl = 5
cpk = calculate_cpk(data, usl, lsl)
print(f"Both limits (5, 15): CPK = {cpk}")

# Case 2: Only USL
usl = 15
lsl = None
cpk = calculate_cpk(data, usl, lsl)
print(f"Only USL (15): CPK = {cpk}")

# Case 3: Only LSL
usl = None
lsl = 5
cpk = calculate_cpk(data, usl, lsl)
print(f"Only LSL (5): CPK = {cpk}")
