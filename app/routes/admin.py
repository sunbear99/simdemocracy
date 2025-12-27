from flask import Blueprint, session, redirect, request, url_for, current_app
from app.extensions import db
from app.models import Election, CandidateProfile, Ballot
from app.utils import calculate_star, calculate_tea

bp = Blueprint('admin', __name__)

# Helper function to check admin status
def is_admin():
    return session.get('user_id') in current_app.config['ADMIN_IDS']

@bp.route('/create_election', methods=['POST'])
def create_election():
    if not is_admin(): return "Access Denied"
    
    title = request.form['title']
    e_type = request.form['type']
    
    # REFERENDUM: Starts OPEN immediately with Yes/No options
    # SENATE/STAR: Starts in CFC (Call for Candidates) with empty candidate list
    if e_type == "REFERENDUM":
        candidates = ["Yes", "No"]
        status = "OPEN"
    else:
        candidates = []
        status = "CFC"
    
    new_election = Election(title=title, type=e_type, candidates=candidates, status=status)
    db.session.add(new_election)
    db.session.commit()
    
    return redirect(url_for('main.dashboard'))

@bp.route('/start_election/<int:election_id>', methods=['POST'])
def start_election(election_id):
    if not is_admin(): return "Access Denied"
    
    election = Election.query.get_or_404(election_id)
    
    # FREEZE CANDIDATES:
    # 1. Look up all profiles registered for this election
    profiles = CandidateProfile.query.filter_by(election_id=election.id).all()
    
    # 2. Extract their names into a simple list
    candidate_names = [p.name for p in profiles]
    
    # 3. Save that list to the election object and open voting
    election.candidates = candidate_names
    election.status = 'OPEN'
    db.session.commit()
    
    return redirect(url_for('main.dashboard'))

@bp.route('/close_election/<int:election_id>', methods=['POST'])
def close_election(election_id):
    if not is_admin(): return "Access Denied"
    
    election = Election.query.get_or_404(election_id)
    
    # 1. Fetch all ballots
    raw_ballots = Ballot.query.filter_by(election_id=election.id).all()
    
    # 2. Format ballots for the algorithms
    # Algorithms expect: [{'id': 1, 'weight': 1.0, 'scores': {'Alice': 5, 'Bob': 3}}]
    ballot_data = [{'id': i, 'weight': 1.0, 'scores': b.vote_choice} for i, b in enumerate(raw_ballots)]
    
    # 3. Run the correct algorithm based on Election Type
    results = []
    
    if election.type == 'REFERENDUM':
        y = sum(1 for b in ballot_data if b['scores'].get('choice') == 'Yes')
        n = sum(1 for b in ballot_data if b['scores'].get('choice') == 'No')
        outcome = "Passed" if y > n else "Failed"
        results = [f"Yes: {y}", f"No: {n}", f"Outcome: {outcome}"]
        
    elif election.type == 'STAR':
        results = calculate_star(ballot_data)
        
    elif election.type == 'SENATE':
        # TEA requires the list of candidates to process rounds
        results = calculate_tea(ballot_data, election.candidates)
        
    # 4. Save Results and Close
    election.results = results
    election.status = 'CLOSED'
    db.session.commit()
    
    return redirect(url_for('main.dashboard'))