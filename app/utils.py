import csv
import os
import math
import random
from app.extensions import db

# --- CSV HELPER ---
def get_registered_voters():
    # Looks for voters.csv one level up from the app folder
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    csv_path = os.path.join(base_dir, 'voters.csv')
    
    voters = []
    if not os.path.exists(csv_path): return []
    
    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if row: voters.append(row[0].strip())
    return voters

def register_user_csv(user_id):
    current = get_registered_voters()
    if user_id in current: return
    
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    csv_path = os.path.join(base_dir, 'voters.csv')
    
    with open(csv_path, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([user_id])

# --- ALGORITHMS ---
def solve_for_n(weights, quota):
    weights.sort()
    k = len(weights)
    prefix_sum = 0
    for i in range(k):
        remaining = k - i
        if remaining == 0: break
        n = (quota - prefix_sum) / remaining
        if abs(sum(min(w, n) for w in weights) - quota) < 0.0001: return n
        prefix_sum += weights[i]
    return (quota - prefix_sum) / 1.0 if k > 0 else 0

def calculate_star(ballots):
    scores = {}
    for b in ballots:
        for c, s in b['scores'].items(): scores[c] = scores.get(c, 0) + s
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if len(ranked) < 2: return [ranked[0][0]] if ranked else []
    f1, f2 = ranked[0][0], ranked[1][0]
    v1 = sum(1 for b in ballots if b['scores'].get(f1,0) > b['scores'].get(f2,0))
    v2 = sum(1 for b in ballots if b['scores'].get(f2,0) > b['scores'].get(f1,0))
    winner = f1 if v1 > v2 else (f2 if v2 > v1 else (f1 if scores[f1] > scores[f2] else f2))
    return [f"Winner: {winner}", f"Runoff: {f1} ({v1}) vs {f2} ({v2})"]

def calculate_tea(ballots, cands):
    """
    Implements TEA (Threshold Equal Approval) with:
    1. Dynamic seat calculation: min(floor(3.5 + x/11), 40)
    2. 4-step Tiebreaker: Weight Sum > Weighted Score > Unweighted Score > Random
    """
    # 1. Calculate Seats
    x = len(ballots)
    seats = min(int(math.floor(3.5 + x / 11)), 40)
    
    # If no seats or no candidates, return empty
    if seats == 0 or not cands:
        return []

    elected = []
    rem = list(cands)
    quota = len(ballots) / seats
    thresh = 5

    while len(elected) < seats and rem:
        pot = []
        
        # §1.1.2 Identify candidates meeting quota at current threshold
        for c in rem:
            # Get supporters (score >= thresh)
            sup = [b for b in ballots if b['scores'].get(c, 0) >= thresh]
            current_weight_sum = sum(b['weight'] for b in sup)
            
            if current_weight_sum >= quota:
                n = solve_for_n([b['weight'] for b in sup], quota)
                
                # --- Tiebreaker Metrics (§1.2) ---
                # TB1: Sum of weights for scores >= thresh (The support weight)
                tb_1 = current_weight_sum
                
                # TB2: Sum of weighted scores (Using current ballot weights)
                tb_2 = sum(b['weight'] * b['scores'].get(c, 0) for b in ballots)
                
                # TB3: Sum of unweighted scores
                tb_3 = sum(b['scores'].get(c, 0) for b in ballots)
                
                # TB4: Random
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
            # Sort candidates to find the winner.
            # Priority: Min n -> Max TB1 -> Max TB2 -> Max TB3 -> Random
            # Python sorts ascending, so we negate (-) the "Max" criteria.
            pot.sort(key=lambda x: (x['n'], -x['tb_1'], -x['tb_2'], -x['tb_3'], x['tb_4']))
            
            win = pot[0]
            elected.append(win['name'])
            rem.remove(win['name'])
            
            # Reweight ballots for the winner
            for b in win['sup']:
                reduction = min(b['weight'], win['n'])
                b['weight'] -= reduction
                # Prevent floating point underflow errors
                if b['weight'] < 1e-9: b['weight'] = 0.0
        
        else:
            # If no one qualifies, try lowering the threshold
            if thresh > 1:
                thresh -= 1
            else:
                # §1.1.5 Fallback: Elect based on greatest sum of positive weights
                fallback_pot = []
                for c in rem:
                    # Primary Metric: Sum of weights for scores > 0
                    pos_sup = [b for b in ballots if b['scores'].get(c, 0) > 0]
                    primary_weight = sum(b['weight'] for b in pos_sup)
                    
                    # Tiebreakers apply here as well
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
                
                # If no candidates have any positive scores left, we stop (or elect remaining randomly?)
                # Usually implies end of viable election.
                if not fallback_pot:
                    break

                # Sort Fallback: Max Primary -> Max TB1 -> Max TB2...
                fallback_pot.sort(key=lambda x: (-x['primary'], -x['tb_1'], -x['tb_2'], -x['tb_3'], x['tb_4']))
                
                best = fallback_pot[0]
                elected.append(best['name'])
                rem.remove(best['name'])
                
                # Exhaust ballots for the winner
                for b in ballots:
                    if b['scores'].get(best['name'], 0) > 0:
                        b['weight'] = 0.0

    return elected