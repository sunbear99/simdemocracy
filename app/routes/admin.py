from flask import Blueprint, session, redirect, request, url_for, current_app, render_template
from app.extensions import db
from app.models import Election, CandidateProfile, Ballot, Attendance
from app.utils import calculate_star, calculate_tea
import requests
import os

bp = Blueprint('admin', __name__)

def is_admin():
    return session.get('user_id') in current_app.config['ADMIN_IDS']

@bp.route('/create_election', methods=['POST'])
def create_election():
    if not is_admin(): return "Access Denied"
    title = request.form['title']
    e_type = request.form['type']
    
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
    profiles = CandidateProfile.query.filter_by(election_id=election.id).all()
    election.candidates = [p.name for p in profiles]
    election.status = 'OPEN'
    db.session.commit()
    return redirect(url_for('main.dashboard'))

@bp.route('/close_election/<int:election_id>', methods=['POST'])
def close_election(election_id):
    if not is_admin(): return "Access Denied"
    election = Election.query.get_or_404(election_id)
    raw_ballots = Ballot.query.filter_by(election_id=election.id).all()
    ballot_data = [{'id': i, 'weight': 1.0, 'scores': b.vote_choice} for i, b in enumerate(raw_ballots)]
    
    results = []
    if election.type == 'REFERENDUM':
        y = sum(1 for b in ballot_data if b['scores'].get('choice') == 'Yes')
        n = sum(1 for b in ballot_data if b['scores'].get('choice') == 'No')
        outcome = "Passed" if y > n else "Failed"
        results = [f"Yes: {y}", f"No: {n}", f"Outcome: {outcome}"]
    elif election.type == 'STAR':
        results = calculate_star(ballot_data)
    elif election.type == 'SENATE':
        results = calculate_tea(ballot_data, election.candidates)
        
    election.results = results
    election.status = 'CLOSED'
    db.session.commit()
    return redirect(url_for('main.dashboard'))

# --- NEW: VOTER LIST UPLOAD ---

# --- NEW: STRIKE VOTE (RC ORACLE) ---
@bp.route('/strike_vote', methods=['GET', 'POST'])
def strike_vote():
    if not is_admin(): return "Access Denied"
    
    msg = ""
    if request.method == 'POST':
        target_user = request.form.get('user_id')
        election_id = request.form.get('election_id')
        
        # 1. Ask RC Oracle for the Hash
        try:
            # Assumes RC Oracle is running on localhost:5001 or defined in config
            oracle_url = current_app.config.get('RC_ORACLE_URL', 'http://localhost:5001/anonymize')
            response = requests.post(
                oracle_url,
                json={'user_id': target_user, 'election_id': election_id},
                timeout=5
            )
            
            if response.status_code == 200:
                target_hash = response.json().get('voter_hash')
                
                # 2. Find and Delete Ballot
                ballot = Ballot.query.filter_by(election_id=election_id, voter_hash=target_hash).first()
                if ballot:
                    db.session.delete(ballot)
                    db.session.commit()
                    msg = f"✅ SUCCESS: Vote for {target_user} removed."
                else:
                    msg = f"⚠️ NOT FOUND: No ballot for {target_user} in Election {election_id}."
            else:
                msg = "❌ RC Oracle returned an error."
                
        except Exception as e:
            msg = f"❌ Connection Error: {e}"

    return render_template('admin_strike.html', msg=msg)
# ... existing imports ...

@bp.route('/audit_election/<int:election_id>')
def audit_election(election_id):
    if not is_admin(): return "Access Denied"
    
    election = Election.query.get_or_404(election_id)
    ballots = Ballot.query.filter_by(election_id=election.id).all()
    
    return render_template('admin_results.html', election=election, ballots=ballots)