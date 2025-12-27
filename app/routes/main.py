from flask import Blueprint, session, redirect, request, url_for, render_template, current_app
from app.extensions import db
from app.models import Election, CandidateProfile, Ballot, Attendance
from app.utils import get_registered_voters
import uuid
import secrets
import json

bp = Blueprint('main', __name__)

@bp.route('/')
def dashboard():
    elections = Election.query.order_by(Election.id.desc()).all()
    
    is_admin = session.get('user_id') in current_app.config['ADMIN_IDS']
    is_registered = session.get('user_id') in get_registered_voters()
    
    return render_template('dashboard.html', 
                           elections=elections, 
                           is_admin=is_admin, 
                           is_registered=is_registered)

@bp.route('/declare/<int:election_id>', methods=['GET', 'POST'])
def declare(election_id):
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    
    # Check duplicate
    existing = CandidateProfile.query.filter_by(election_id=election_id, user_id=session['user_id']).first()
    if existing:
        return render_template('message.html', title="Already Declared", message="You are already running.", type="warning")
        
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
        return render_template('message.html', title="Declared", message="Good luck!", type="success")
        
    return render_template('declare.html', username=session.get('username'))

@bp.route('/vote/<int:election_id>', methods=['GET', 'POST'])
def vote(election_id):
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    if session['user_id'] not in get_registered_voters(): return redirect(url_for('auth.register'))
    
    election = Election.query.get_or_404(election_id)
    if election.status != 'OPEN': return "Election Closed"
    
    # Check double vote
    if Attendance.query.filter_by(user_id=session['user_id'], election_id=election_id).first():
        return render_template('message.html', title="Already Voted", message="You cannot vote twice.", type="warning")
        
    # Get Metadata (Avatars/Statements) for the ballot
    profiles = CandidateProfile.query.filter_by(election_id=election_id).all()
    # Convert list to dict for easy lookup: meta['SenatorName'] = profile_object
    meta = {p.name: p for p in profiles}
    
    if request.method == 'POST':
        vote_data = {}
        if election.type == 'REFERENDUM':
            vote_data = {'choice': request.form['choice']}
        else:
            for cand in election.candidates:
                vote_data[cand] = int(request.form.get(cand, 0))
        
        token = secrets.token_hex(6)
        
        # Save Vote
        ballot = Ballot(election_id=election_id, vote_choice=vote_data, verification_token=token)
        attendance = Attendance(user_id=session['user_id'], election_id=election_id)
        
        db.session.add(ballot)
        db.session.add(attendance)
        db.session.commit()
        
        return render_template('message.html', title="Vote Cast", message=f"Token: {token}", type="success")

    return render_template('vote.html', election=election, meta=meta)

@bp.route('/results/<int:election_id>')
def results(election_id):
    election = Election.query.get_or_404(election_id)
    # Random order for anonymity
    ballots = Ballot.query.filter_by(election_id=election_id).order_by(db.func.random()).all()
    return render_template('results.html', election=election, ballots=ballots)

@bp.route('/view_cfc/<int:election_id>')
def view_cfc(election_id):
    election = Election.query.get_or_404(election_id)
    profiles = CandidateProfile.query.filter_by(election_id=election_id).all()
    return render_template('view_cfc.html', election=election, profiles=profiles)