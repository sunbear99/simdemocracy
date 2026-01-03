import json
from datetime import datetime
from app.extensions import db

class Election(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150))
    type = db.Column(db.String(50))  # SENATE, STAR, REFERENDUM
    _candidates = db.Column('candidates', db.Text)
    status = db.Column(db.String(20), default='CFC') # CFC, OPEN, CLOSED
    _results = db.Column('results', db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow) # Needed for Scheduler

    @property
    def candidates(self):
        return json.loads(self._candidates) if self._candidates else []
    
    @candidates.setter
    def candidates(self, value):
        self._candidates = json.dumps(value)

    @property
    def results(self):
        return json.loads(self._results) if self._results else []
    
    @results.setter
    def results(self, value):
        self._results = json.dumps(value)

class CandidateProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey('election.id'))
    user_id = db.Column(db.String(50))
    name = db.Column(db.String(100))
    statement = db.Column(db.Text)
    avatar_url = db.Column(db.String(200))
    __table_args__ = (db.UniqueConstraint('election_id', 'user_id'),)

class Attendance(db.Model):
    user_id = db.Column(db.String(50), primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey('election.id'), primary_key=True)

class Ballot(db.Model):
    id = db.Column(db.Integer, primary_key=True) # Changed to Integer for auto-increment simplicity, or keep String(36) if you use UUIDs
    election_id = db.Column(db.Integer, db.ForeignKey('election.id'))
    _vote_choice = db.Column('vote_choice', db.Text)
    verification_token = db.Column(db.String(50), unique=True)
    
    # --- THIS WAS MISSING ---
    voter_hash = db.Column(db.String(64), index=True) 
    # ------------------------

    @property
    def vote_choice(self):
        return json.loads(self._vote_choice) if self._vote_choice else {}
    
    @vote_choice.setter
    def vote_choice(self, value):
        self._vote_choice = json.dumps(value)