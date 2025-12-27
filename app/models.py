from app.extensions import db
import json
import uuid

# Helper to handle JSON storage in SQLite
class JsonType(db.TypeDecorator):
    impl = db.Text
    def process_bind_param(self, value, dialect):
        return json.dumps(value) if value is not None else None
    def process_result_value(self, value, dialect):
        return json.loads(value) if value is not None else None

class Election(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # SENATE, STAR, REFERENDUM
    status = db.Column(db.String(20), default='CFC') # CFC, OPEN, CLOSED
    
    # Store candidates/results as JSON lists
    candidates = db.Column(JsonType, default=[])
    results = db.Column(JsonType, default=[])

    # Relationship to link actual Candidate profiles
    profiles = db.relationship('CandidateProfile', backref='election', lazy=True)

class CandidateProfile(db.Model):
    __tablename__ = 'candidate_profile'
    id = db.Column(db.Integer, primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey('election.id'), nullable=False)
    user_id = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    statement = db.Column(db.Text, nullable=False)
    avatar_url = db.Column(db.String(200))
    
    # Ensure one candidacy per user per election
    __table_args__ = (db.UniqueConstraint('election_id', 'user_id'),)

class Ballot(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    election_id = db.Column(db.Integer, db.ForeignKey('election.id'), nullable=False)
    vote_choice = db.Column(JsonType, nullable=False) # {'Alice': 5, 'Bob': 3}
    verification_token = db.Column(db.String(12), unique=True, nullable=False)

class Attendance(db.Model):
    # Composite Primary Key: User + Election
    user_id = db.Column(db.String(50), primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey('election.id'), primary_key=True)