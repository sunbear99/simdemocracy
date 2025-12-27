import csv
import os
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
    seats = 3
    elected = []
    rem = list(cands)
    quota = len(ballots) / seats
    thresh = 5
    while len(elected) < seats and rem:
        pot = []
        for c in rem:
            sup = [b for b in ballots if b['scores'].get(c,0) >= thresh]
            if sum(b['weight'] for b in sup) >= quota:
                n = solve_for_n([b['weight'] for b in sup], quota)
                pot.append({'name': c, 'n': n, 'sup': sup})
        if pot:
            win = min(pot, key=lambda x: x['n'])
            elected.append(win['name'])
            rem.remove(win['name'])
            for b in win['sup']:
                b['weight'] -= min(b['weight'], win['n'])
                if b['weight'] < 0: b['weight'] = 0
        else:
            if thresh > 1: thresh -= 1
            else:
                best = max(rem, key=lambda c: sum(b['weight'] for b in ballots if b['scores'].get(c,0)>0))
                elected.append(best)
                rem.remove(best)
                for b in ballots:
                    if b['scores'].get(best,0)>0: b['weight'] = 0
    return elected