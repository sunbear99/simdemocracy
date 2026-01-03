import pandas as pd
import math
import random

def solve_for_n(weights, quota):
    """
    Calculates n such that sum(min(w, n) for w in weights) == quota.
    """
    if not weights:
        return 0
        
    sorted_weights = sorted(weights)
    k = len(sorted_weights)
    current_sum = 0
    
    if sum(weights) < quota:
        return sorted_weights[-1]

    for i, w in enumerate(sorted_weights):
        remaining_count = k - i
        required_n = (quota - current_sum) / remaining_count
        
        if required_n <= w:
            return required_n
        
        current_sum += w
        
    return sorted_weights[-1]

def calculate_tea(file_path):
    # --- 1. Robust File Loading ---
    try:
        if file_path.endswith('.xlsx'):
            df = pd.read_excel(file_path)
        else:
            # Try default UTF-8 first, fallback to latin-1 (common for Excel CSVs)
            try:
                df = pd.read_csv(file_path, encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(file_path, encoding='latin-1')
    except Exception as e:
        return f"Error reading file: {e}"

    # Clean Data
    # Drop Timestamp if exists
    if 'Timestamp' in df.columns:
        df = df.drop(columns=['Timestamp'])
        
    # Fill blanks with 0
    df = df.fillna(0)
    
    cands = df.columns.tolist()
    ballots = []
    
    # Parse DataFrame
    for index, row in df.iterrows():
        scores = {}
        for c in cands:
            try:
                val = float(row[c])
            except:
                val = 0.0
            scores[c] = val
            
        ballots.append({'scores': scores, 'weight': 1.0, 'id': index})

    # --- 2. Calculate Seats ---
    x = len(ballots)
    seats = min(int(math.floor(3.5 + x / 11)), 40)
    print(f"Total Ballots: {x}")
    print(f"Seats to fill: {seats}")
    
    if seats == 0:
        return []

    # --- 3. Run TEA Algorithm ---
    elected = []
    rem = list(cands)
    quota = x / seats
    thresh = 5

    while len(elected) < seats and rem:
        pot = []
        
        # §1.1.2 Identify candidates
        for c in rem:
            sup = [b for b in ballots if b['scores'].get(c, 0) >= thresh]
            current_weight_sum = sum(b['weight'] for b in sup)
            
            if current_weight_sum >= quota:
                n = solve_for_n([b['weight'] for b in sup], quota)
                
                # Tiebreaker Metrics
                tb_1 = current_weight_sum
                tb_2 = sum(b['weight'] * b['scores'].get(c, 0) for b in ballots)
                tb_3 = sum(b['scores'].get(c, 0) for b in ballots)
                tb_4 = random.random()

                pot.append({
                    'name': c, 
                    'n': n, 
                    'sup': sup,
                    'tb_1': tb_1,
                    'tb_2': tb_2,
                    'tb_3': tb_3,
                    'tb_4': tb_4
                })

        if pot:
            # Sort: Min n, Max TB1, Max TB2, Max TB3
            pot.sort(key=lambda x: (x['n'], -x['tb_1'], -x['tb_2'], -x['tb_3'], x['tb_4']))
            
            win = pot[0]
            elected.append(win['name'])
            rem.remove(win['name'])
            
            # Reweight
            for b in win['sup']:
                reduction = min(b['weight'], win['n'])
                b['weight'] -= reduction
                if b['weight'] < 1e-9: b['weight'] = 0.0
        
        else:
            if thresh > 1:
                thresh -= 1
            else:
                # Fallback
                fallback_pot = []
                for c in rem:
                    pos_sup = [b for b in ballots if b['scores'].get(c, 0) > 0]
                    primary_weight = sum(b['weight'] for b in pos_sup)
                    
                    tb_1 = primary_weight
                    tb_2 = sum(b['weight'] * b['scores'].get(c, 0) for b in ballots)
                    tb_3 = sum(b['scores'].get(c, 0) for b in ballots)
                    tb_4 = random.random()
                    
                    fallback_pot.append({
                        'name': c,
                        'primary': primary_weight,
                        'tb_1': tb_1,
                        'tb_2': tb_2,
                        'tb_3': tb_3,
                        'tb_4': tb_4
                    })
                
                if not fallback_pot:
                    break

                fallback_pot.sort(key=lambda x: (-x['primary'], -x['tb_1'], -x['tb_2'], -x['tb_3'], x['tb_4']))
                
                best = fallback_pot[0]
                elected.append(best['name'])
                rem.remove(best['name'])
                
                for b in ballots:
                    if b['scores'].get(best['name'], 0) > 0:
                        b['weight'] = 0.0

    return elected

if __name__ == "__main__":
    # Update the filename below to match your actual file
    filename = 'elections_data.xlsx'
    print(f"Processing {filename}...")
    results = calculate_tea(filename)
    print("Elected candidates:", results)