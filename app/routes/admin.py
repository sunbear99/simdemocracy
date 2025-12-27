from flask import Blueprint, session, redirect, request, url_for, current_app, flash
from app.extensions import db
from app.models import Election, CandidateProfile, Ballot
from app.utils import calculate_star, calculate_tea
import pandas as pd
import os
import secrets
import random

bp = Blueprint('admin', __name__, url_prefix='/admin')

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
    profiles = CandidateProfile.query.filter_by(election_id=election.id).all()
    candidate_names = [p.name for p in profiles]
    
    election.candidates = candidate_names
    election.status = 'OPEN'
    db.session.commit()
    
    return redirect(url_for('main.dashboard'))

@bp.route('/seed_election/<int:election_id>')
def seed_election(election_id):
    """
    TESTING TOOL: 
    1. If CFC: Creates 7 Bot Candidates and Opens the Election.
    2. Seeds 30 Random Ballots.
    """
    if not is_admin(): return "Access Denied"
    
    election = Election.query.get_or_404(election_id)

    # --- Step 1: Seed Candidates (Only if in CFC) ---
    if election.status == 'CFC' and election.type != 'REFERENDUM':
        # Create 7 Dummy Candidates
        for i in range(1, 8):
            user_id = f"bot_user_{i}"
            name = f"Bot Candidate {i}"
            
            # Check for duplicates
            exists = CandidateProfile.query.filter_by(election_id=election.id, user_id=user_id).first()
            if not exists:
                profile = CandidateProfile(
                    election_id=election.id,
                    user_id=user_id,
                    name=name,
                    statement="I am a simulation bot designed to test the voting system.",
                    avatar_url=""
                )
                db.session.add(profile)
        
        db.session.commit()
        
        # Auto-Start the Election
        profiles = CandidateProfile.query.filter_by(election_id=election.id).all()
        election.candidates = [p.name for p in profiles]
        election.status = 'OPEN'
        db.session.commit()
        flash("Seeded 7 candidates and opened the election.", "info")

    if election.status != 'OPEN':
        flash("Election must be OPEN (or in CFC) to seed data.", "error")
        return redirect(url_for('main.dashboard'))

    # --- Step 2: Seed 30 Votes ---
    # Ensure there are candidates to vote for
    candidates = election.candidates
    if not candidates and election.type != 'REFERENDUM':
        return "Error: No candidates found to vote for!"

    for _ in range(30):
        vote_choice = {}
        
        if election.type == 'REFERENDUM':
            vote_choice = {'choice': random.choice(['Yes', 'No'])}
        else:
            # TEA/STAR: Score each candidate 0-5
            for cand in candidates:
                # Use a weighted random to make it look realistic (mostly 0s-4s, some 5s)
                # or just pure uniform random
                vote_choice[cand] = random.randint(0, 5)
        
        token = secrets.token_hex(6)
        
        new_ballot = Ballot(
            election_id=election.id,
            vote_choice=vote_choice,
            verification_token=token
        )
        db.session.add(new_ballot)
    
    db.session.commit()
    flash(f"Successfully added 30 random ballots to '{election.title}'", "success")
    return redirect(url_for('main.dashboard'))

@bp.route('/close_election/<int:election_id>', methods=['POST'])
def close_election(election_id):
    if not is_admin(): return "Access Denied"
    
    election = Election.query.get_or_404(election_id)
    
    # 1. Fetch all ballots
    raw_ballots = Ballot.query.filter_by(election_id=election.id).all()
    
    # 2. Generate and Save Downloadable XLSX
    download_msg = ""
    try:
        # Define export path: app/static/exports/
        export_dir = os.path.join(current_app.root_path, 'static', 'exports')
        os.makedirs(export_dir, exist_ok=True)
        
        # Prepare data for DataFrame
        export_data = []
        for b in raw_ballots:
            row = b.vote_choice.copy()
            # Ensure 0s for missing candidates
            if election.type != 'REFERENDUM':
                for c in election.candidates:
                    if c not in row: row[c] = 0
            
            # Add token for audit
            row['token'] = b.verification_token
            export_data.append(row)
            
        df = pd.DataFrame(export_data)
        
        # Reorder columns: Token first, then Candidates
        cols = ['token'] + (election.candidates if election.candidates else [])
        # Filter cols to only those that exist in df
        existing_cols = [c for c in cols if c in df.columns]
        # Add any remaining columns (like 'choice' for referendums)
        remaining = [c for c in df.columns if c not in existing_cols]
        df = df[existing_cols + remaining]
            
        filename = f"election_{election_id}_results.xlsx"
        save_path = os.path.join(export_dir, filename)
        
        # Save to Excel
        df.to_excel(save_path, index=False)
        
        # Create a relative link string to display in results
        download_msg = f"Download Votes: /static/exports/{filename}"
        
    except Exception as e:
        print(f"Failed to generate Excel export: {e}")

    # 3. Format ballots for the algorithms
    ballot_data = [{'id': i, 'weight': 1.0, 'scores': b.vote_choice} for i, b in enumerate(raw_ballots)]
    
    # 4. Run the correct algorithm based on Election Type
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
        
    # Append download link if generated
    if download_msg:
        results.append(download_msg)

    # 5. Save Results and Close
    election.results = results
    election.status = 'CLOSED'
    db.session.commit()
    
    return redirect(url_for('main.dashboard'))