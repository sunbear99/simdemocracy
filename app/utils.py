import requests
import csv
import io
from flask import current_app

# --- 1. VOTER REGISTRY (RC INTEGRATION) ---

def get_registered_voters():
    """
    Fetches the voter registry from the external RC App.
    """
    # URL of the RC Website API
    # In production use real URL. Locally use localhost:5001
    rc_url = current_app.config.get('RC_API_URL', 'http://localhost:5001')
    
    try:
        response = requests.get(f"{rc_url}/api/voters", timeout=3)
        if response.status_code == 200:
            # Parse the CSV string returned by the API
            voters = []
            # We use io.StringIO to treat the string response like a file
            f = io.StringIO(response.text)
            reader = csv.reader(f)
            for row in reader:
                if row: voters.append(row[0].strip())
            return voters
    except:
        print("⚠️ Could not contact RC Server for voter list.")
        return [] # Fail safe
    
    return []

# --- 2. ELECTION MATH (REQUIRED FOR ADMIN) ---

def calculate_star(ballots):
    """
    STAR Voting: Score then Automatic Runoff
    ballots = [{'scores': {'Alice': 5, 'Bob': 4}}, ...]
    """
    if not ballots: return ["No votes cast."]
    
    # Phase 1: Scoring
    scores = {}
    candidates = ballots[0]['scores'].keys()
    
    for c in candidates:
        scores[c] = sum(b['scores'].get(c, 0) for b in ballots)
        
    # Find Top 2
    sorted_cand = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if len(sorted_cand) < 2:
        return [f"Winner: {sorted_cand[0][0]} (Uncontested)"]
        
    top_two = [sorted_cand[0][0], sorted_cand[1][0]]
    
    # Phase 2: Runoff
    c1, c2 = top_two[0], top_two[1]
    votes_c1, votes_c2 = 0, 0
    
    for b in ballots:
        s1 = b['scores'].get(c1, 0)
        s2 = b['scores'].get(c2, 0)
        if s1 > s2: votes_c1 += 1
        elif s2 > s1: votes_c2 += 1
        
    winner = c1 if votes_c1 > votes_c2 else c2
    if votes_c1 == votes_c2: winner = c1 # Tie-breaker (higher score)
    
    results = [
        "--- SCORES ---",
        *[f"{c}: {s}" for c, s in sorted_cand],
        "--- RUNOFF ---",
        f"{c1}: {votes_c1} votes",
        f"{c2}: {votes_c2} votes",
        f"WINNER: {winner}"
    ]
    return results

def calculate_tea(ballots, candidates):
    """
    TEA (Tied Electorate Allocation) - Simplified Proportional
    Similar to Reweighted Range Voting.
    """
    if not ballots: return ["No votes."]
    
    # Setup
    seats = 5 # Example senate size
    winners = []
    
    # Convert simple dicts to working copies
    # ballot['weight'] starts at 1.0
    current_ballots = []
    for b in ballots:
        current_ballots.append({
            'weight': 1.0,
            'scores': {c: float(b['scores'].get(c, 0)) for c in candidates}
        })

    logs = []
    
    for r in range(seats):
        # Calculate weighted sums
        sums = {c: 0.0 for c in candidates if c not in winners}
        if not sums: break # No more candidates
        
        for b in current_ballots:
            for c in sums:
                sums[c] += b['scores'][c] * b['weight']
        
        # Pick winner
        best_cand = max(sums, key=sums.get)
        winners.append(best_cand)
        logs.append(f"Seat {r+1}: {best_cand} (Score: {sums[best_cand]:.1f})")
        
        # Reweight ballots
        # If you voted high for the winner, your weight goes down
        for b in current_ballots:
            score = b['scores'][best_cand]
            # TEA Formula: new_weight = old_weight / (1 + score/max_score)
            # Assuming max score is 5
            b['weight'] = b['weight'] / (1 + (score / 5.0))
            
    return logs