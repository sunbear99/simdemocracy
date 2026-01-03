from flask import Blueprint, session, redirect, request, make_response, url_for, render_template, current_app
from app.extensions import db
from app.models import Election, CandidateProfile, Ballot, Attendance
from app.utils import get_registered_voters
import uuid
import json
import secrets
import requests

bp = Blueprint('main', __name__)

# --- DASHBOARD & HELP ---

@bp.route('/')
def dashboard():
    # 1. Fetch elections
    elections = Election.query.order_by(Election.id.desc()).all()
    
    user_id = session.get('user_id')
    is_registered = user_id in get_registered_voters() if user_id else False
    is_admin = user_id in current_app.config['ADMIN_IDS'] if user_id else False

    # 2. Calculate Button State for each election
    for e in elections:
        e.has_voted = False
        e.can_edit = False
        
        if user_id:
            attendance = Attendance.query.filter_by(user_id=user_id, election_id=e.id).first()
            if attendance:
                e.has_voted = True
                token_cookie = request.cookies.get(f'v_token_{e.id}')
                if token_cookie:
                    e.can_edit = True

    return render_template('dashboard.html', 
                         elections=elections, 
                         is_registered=is_registered, 
                         is_admin=is_admin)

@bp.route('/help')
def help_page():
    return render_template('help.html')

# --- VOTING LOGIC ---

@bp.route('/vote/<int:election_id>', methods=['GET', 'POST'])
def vote(election_id):
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    user_id = session['user_id']
    
    if user_id not in get_registered_voters():
        return render_template('message.html', title="Access Denied", message="You must register first.", type="danger")

    election = Election.query.get_or_404(election_id)
    if election.status != 'OPEN':
        return render_template('message.html', title="Closed", message="This election is not open.", type="warning")

    # 1. MANUAL TOKEN RECOVERY (If user lost cookie)
    if request.method == 'POST' and 'manual_token' in request.form:
        token_input = request.form['manual_token'].strip()
        ballot = Ballot.query.filter_by(verification_token=token_input).first()
        
        if ballot and ballot.election_id == election.id:
            # Success: Restore access by setting the cookie
            resp = make_response(redirect(url_for('main.vote', election_id=election_id)))
            resp.set_cookie(f'v_token_{election_id}', token_input, max_age=60*60*24*30)
            return resp
        else:
            return render_template('enter_token.html', election=election, error="That token is invalid for this election.")

    # 2. DETERMINE MODE (New vs Edit)
    attendance = Attendance.query.filter_by(user_id=user_id, election_id=election.id).first()
    cookie_token = request.cookies.get(f'v_token_{election_id}')
    
    mode = "NEW"
    ballot = None
    current_vote = {} 

    if attendance:
        if cookie_token:
            # User voted AND has the token -> EDIT MODE
            ballot = Ballot.query.filter_by(verification_token=cookie_token).first()
            if ballot:
                mode = "EDIT"
                current_vote = ballot.vote_choice 
            else:
                return render_template('message.html', title="Error", message="Invalid vote token in cookie.", type="danger")
        else:
            # User voted but MISSING cookie -> SHOW TOKEN ENTRY PAGE
            return render_template('enter_token.html', election=election)

    # 3. PROCESS VOTE SUBMISSION
    if request.method == 'POST':
        vote_data = {}
        
        # A) Handle Referendums (Yes/No)
        if election.type == 'REFERENDUM':
            vote_data = {'choice': request.form.get('choice')}
        
        # B) Handle Candidates (0-5 Scoring)
        else:
            for cand in election.candidates:
                val = request.form.get(cand)
                
                # STRICT VALIDATION Logic
                if val and val.strip():
                    try:
                        score = int(val)
                        if score < 0: score = 0
                        if score > 5: score = 5
                        vote_data[cand] = score
                    except ValueError:
                        vote_data[cand] = 0 # Invalid text becomes 0
                else:
                    vote_data[cand] = 0 # Empty/Blank becomes 0

        # --- RC ORACLE HOOK (FAIL-CLOSED SECURITY) ---
        voter_hash = None
        if mode == "NEW":
            try:
                # Default to localhost:5001 if not in config
                oracle_url = current_app.config.get('RC_ORACLE_URL', 'http://localhost:5001/api/anonymize')
                
                rc_response = requests.post(
                    oracle_url, 
                    json={'user_id': user_id, 'election_id': election.id},
                    timeout=3
                )
                
                if rc_response.status_code == 200:
                    voter_hash = rc_response.json().get('voter_hash')
                else:
                    # Oracle refused request
                    return render_template('message.html', title="Security Error", message="The Anonymity Service rejected the request.", type="danger")

            except Exception as e:
                # Oracle is OFFLINE -> BLOCK THE VOTE
                return render_template('message.html', title="System Offline", message="Critical: The Voting Authority (RC Oracle) is offline. Cannot generate secure hash.", type="danger")
        # ---------------------------------------------

        token = cookie_token if mode == "EDIT" else secrets.token_hex(6)

        if mode == "NEW":
            new_ballot = Ballot(
                election_id=election.id,
                vote_choice=vote_data,
                verification_token=token,
                voter_hash=voter_hash  # Save the hash from Oracle
            )
            new_attendance = Attendance(user_id=user_id, election_id=election.id)
            db.session.add(new_ballot)
            db.session.add(new_attendance)
        else:
            ballot.vote_choice = vote_data
        
        db.session.commit()

        action_text = "Updated" if mode == "EDIT" else "Cast"
        html = render_template('message.html', 
                             title=f"Vote {action_text}!", 
                             message=f"Your secure token is: {token}", 
                             type="success")
        
        resp = make_response(html)
        resp.set_cookie(f'v_token_{election_id}', token, max_age=60*60*24*30)
        return resp

    # 4. RENDER VOTING BOOTH
    profiles = CandidateProfile.query.filter_by(election_id=election.id).all()
    meta = {p.name: p for p in profiles}

    return render_template('vote.html', 
                         election=election, 
                         meta=meta, 
                         current_vote=current_vote, 
                         mode=mode)

# --- CANDIDATE DECLARATION ---

@bp.route('/declare/<int:election_id>', methods=['GET', 'POST'])
def declare(election_id):
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    
    existing = CandidateProfile.query.filter_by(election_id=election_id, user_id=session['user_id']).first()
    if existing:
        return render_template('message.html', title="Already Declared", message="You have already declared candidacy.", type="warning")

    if request.method == 'POST':
        profile = CandidateProfile(
            election_id=election_id,
            user_id=session['user_id'],
            name=session.get('username', 'Unknown'),
            statement=request.form['stmt'],
            avatar_url=session.get('avatar_url')
        )
        db.session.add(profile)
        db.session.commit()
        return render_template('message.html', title="Success", message="Candidacy declared.", type="success")

    return render_template('declare.html', username=session.get('username'))

@bp.route('/view_cfc/<int:election_id>')
def view_cfc(election_id):
    election = Election.query.get_or_404(election_id)
    profiles = CandidateProfile.query.filter_by(election_id=election_id).all()
    return render_template('view_cfc.html', election=election, profiles=profiles)

@bp.route('/results/<int:election_id>')
def results(election_id):
    election = Election.query.get_or_404(election_id)
    if election.status != 'CLOSED':
        return render_template('message.html', title="Not Released", message="Results pending.", type="warning")
        
    ballots = Ballot.query.filter_by(election_id=election.id).all()
    import random
    random.shuffle(ballots)
    return render_template('results.html', election=election, ballots=ballots)