import os
import sqlite3
import uuid
import secrets
import json
import csv
from flask import Flask, session, redirect, request, url_for
import requests
from dotenv import load_dotenv

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Discord Credentials
DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DISCORD_REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI', 'http://localhost:5000/callback')
DISCORD_API_BASE_URL = 'https://discord.com/api/v10'

# Admin IDs (Replace with your actual ID)
ADMIN_IDS = [
    "754889302105915444", 
    "987654321098765432"
] 

# --- PATH HELPERS ---
DB_PATH = os.path.join(BASE_DIR, 'voting_system.db')
CSV_PATH = os.path.join(BASE_DIR, 'voters.csv')

def get_registered_voters():
    """Returns a list of User IDs from the CSV."""
    voters = []
    if not os.path.exists(CSV_PATH): return []
    with open(CSV_PATH, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if row: voters.append(row[0].strip())
    return voters

def register_user(user_id):
    """Appends a User ID to the CSV."""
    # check if already there to prevent duplicates
    current_voters = get_registered_voters()
    if user_id in current_voters:
        return
    
    with open(CSV_PATH, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([user_id])

# --- DESIGN SYSTEM ---
def render_page(content, title="SimDemocracy Vote"):
    user_display = ""
    if 'user_id' in session:
        user_display = f"""
        <div class="user-status">
            <span>User: <strong>{session['user_id']}</strong></span>
            <a href="/logout" class="btn btn-sm btn-outline">Logout</a>
        </div>
        """
    else:
        user_display = '<a href="/login" class="btn btn-sm btn-primary">Login with Discord</a>'

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            :root {{ --primary: #2563eb; --bg-body: #f3f4f6; --bg-card: #ffffff; --text-main: #1f2937; --text-muted: #6b7280; --border: #e5e7eb; --success: #10b981; --warning: #f59e0b; --danger: #ef4444; }}
            body {{ font-family: 'Segoe UI', sans-serif; background-color: var(--bg-body); color: var(--text-main); margin: 0; padding: 0; line-height: 1.6; }}
            .navbar {{ background-color: #1e293b; color: white; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; }}
            .container {{ max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
            .card {{ background: var(--bg-card); border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); padding: 1.5rem; margin-bottom: 1.5rem; }}
            .btn {{ display: inline-block; padding: 0.6rem 1.2rem; border-radius: 6px; font-weight: 500; text-decoration: none; cursor: pointer; border: none; }}
            .btn-primary {{ background-color: var(--primary); color: white; }}
            .btn-success {{ background-color: var(--success); color: white; }}
            .btn-danger {{ background-color: var(--danger); color: white; }}
            .btn-warning {{ background-color: var(--warning); color: #111; }}
            .btn-outline {{ background: transparent; border: 1px solid rgba(255,255,255,0.3); color: white; }}
            .btn-sm {{ padding: 0.4rem 0.8rem; font-size: 0.85rem; }}
            .badge {{ padding: 0.25rem 0.75rem; border-radius: 99px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; }}
            .badge-open {{ background: #d1fae5; color: #065f46; }}
            .badge-cfc {{ background: #fef3c7; color: #92400e; }}
            .badge-closed {{ background: #e5e7eb; color: #374151; }}
            input, select, textarea {{ width: 100%; padding: 0.75rem; border: 1px solid #d1d5db; border-radius: 6px; margin-bottom: 1rem; box-sizing: border-box; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
            th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid var(--border); }}
            .flex-between {{ display: flex; justify-content: space-between; align-items: start; }}
        </style>
    </head>
    <body>
        <nav class="navbar"><div><strong>SimDemocracy Vote</strong></div>{user_display}</nav>
        <div class="container">{content}</div>
    </body>
    </html>
    """

# --- DATABASE ---
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS elections (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, type TEXT, candidates TEXT, status TEXT DEFAULT 'CFC', results TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS candidates (id INTEGER PRIMARY KEY AUTOINCREMENT, election_id INTEGER, user_id TEXT, name TEXT, statement TEXT, UNIQUE(election_id, user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS attendance (user_id TEXT, election_id INTEGER, PRIMARY KEY (user_id, election_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS ballots (id TEXT PRIMARY KEY, election_id INTEGER, vote_choice TEXT, verification_token TEXT UNIQUE)''')
    conn.commit()
    conn.close()

init_db()

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

# --- ROUTES ---
@app.route('/')
def home():
    conn = get_db()
    c = conn.cursor()
    rows = c.execute("SELECT * FROM elections ORDER BY id DESC").fetchall()
    conn.close()
    
    current_user_id = session.get('user_id')
    is_admin = current_user_id in ADMIN_IDS
    
    # Check registration status
    is_registered = False
    if current_user_id:
        is_registered = current_user_id in get_registered_voters()
    
    def badge(status): return f"<span class='badge badge-{status.lower()}'>{status}</span>"
    
    html = ""
    
    # 1. REGISTRATION PROMPT (If logged in but not registered)
    if current_user_id and not is_registered:
        html += """
        <div class="card" style="border-left: 5px solid #2563eb; background: #eff6ff;">
            <h3>⚠️ You are not registered to vote.</h3>
            <p>You must register before you can participate in SimDemocracy Vote.</p>
            <a href="/register" class="btn btn-primary">Register to Vote</a>
        </div>
        """

    # 2. ADMIN PANEL
    if is_admin:
        html += """<div class="card" style="background:#fff7ed; border-color:#fdba74;"><h3>🛠️ Admin Panel</h3>
        <p style="font-size:0.9em; color:#666; margin-bottom:10px;">Create a new election below.</p>
        <form action="/create" method="post" class="flex-between">
            <input type="text" name="title" placeholder="Election Title" required style="flex:2; margin:0 10px 0 0;">
            <select name="type" style="flex:1; margin:0 10px 0 0;"><option value="SENATE">Senate</option><option value="STAR">Presidential</option><option value="REFERENDUM">Referendum</option></select>
            <button type="submit" class="btn btn-danger">Create</button>
        </form></div>"""
        
    # 3. ELECTIONS LIST
    if not rows:
        html += "<div class='card' style='text-align:center; padding: 40px;'><h3 style='color:#6b7280;'>📭 No Elections Found</h3><p>There are no active polls.</p></div>"
    else:
        for e in rows:
            btn = ""
            if e['status'] == 'CFC':
                style = "border-left: 5px solid #f59e0b;"
                if is_admin: btn = f"<form action='/start/{e['id']}' method='post'><button class='btn btn-success btn-sm'>Start Voting</button></form>"
                # Users can only declare if registered
                declare_btn = f"<a href='/declare/{e['id']}' class='btn btn-warning'>Declare Candidacy</a>" if is_registered else "<span style='color:gray'>Register to Declare</span>"
                html += f"<div class='card' style='{style}'><div class='flex-between'><div>{badge('CFC')} <h3>{e['title']}</h3>{declare_btn}</div>{btn}</div></div>"
            
            elif e['status'] == 'OPEN':
                style = "border-left: 5px solid #10b981;"
                if is_admin: btn = f"<form action='/close/{e['id']}' method='post' onsubmit=\"return confirm('End?');\"><button class='btn btn-danger btn-sm'>Stop & Count</button></form>"
                # Users can only vote if registered
                vote_btn = f"<a href='/vote/{e['id']}' class='btn btn-success'>Vote Now</a>" if is_registered else "<span style='color:gray'>Register to Vote</span>"
                html += f"<div class='card' style='{style}'><div class='flex-between'><div>{badge('OPEN')} <h3>{e['title']}</h3>{vote_btn}</div>{btn}</div></div>"
            
            else:
                html += f"<div class='card'><div class='flex-between'><div>{badge('CLOSED')} <strong>{e['title']}</strong></div><a href='/results/{e['id']}' class='btn btn-sm btn-outline' style='color:#2563eb; border-color:#2563eb'>Audit Results</a></div></div>"

    return render_page(html)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' not in session: return redirect('/login')
    
    # Double check they aren't already registered
    if session['user_id'] in get_registered_voters():
        return redirect('/')

    if request.method == 'POST':
        answer = request.form.get('alt_check')
        if answer == 'No':
            register_user(session['user_id'])
            return render_page("""
            <div class="card" style="text-align:center;">
                <h1 style="color:var(--success);">Registration Complete</h1>
                <p>You have been added to the voter rolls.</p>
                <a href="/" class="btn btn-primary">Return to Dashboard</a>
            </div>
            """)
        else:
            return render_page("""
            <div class="card" style="text-align:center;">
                <h1 style="color:var(--danger);">Registration Denied</h1>
                <p>Tide alts are not permitted to participate in SimDemocracy Vote.</p>
                <a href="/" class="btn btn-outline" style="color:#333;">Return Home</a>
            </div>
            """)

    return render_page("""
    <div class="card">
        <h2>Voter Registration</h2>
        <p>To prevent fraud, please answer the following security question:</p>
        <form method="post" style="margin-top:20px;">
            <label style="font-size:1.2em;">Are you a Tide alt?</label>
            <div style="margin: 15px 0;">
                <label style="display:inline-block; margin-right:20px; cursor:pointer;">
                    <input type="radio" name="alt_check" value="Yes" required> Yes
                </label>
                <label style="display:inline-block; cursor:pointer;">
                    <input type="radio" name="alt_check" value="No"> No
                </label>
            </div>
            <button type="submit" class="btn btn-primary">Submit Registration</button>
        </form>
    </div>
    """)

@app.route('/create', methods=['POST'])
def create():
    if session.get('user_id') not in ADMIN_IDS: return "Denied"
    t, typ = request.form['title'], request.form['type']
    conn = get_db()
    c = conn.cursor()
    if typ == "REFERENDUM": c.execute("INSERT INTO elections (title, type, candidates, status) VALUES (?, ?, ?, 'OPEN')", (t, typ, json.dumps(["Yes", "No"])))
    else: c.execute("INSERT INTO elections (title, type, candidates, status) VALUES (?, ?, ?, 'CFC')", (t, typ, json.dumps([])))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/declare/<int:eid>', methods=['GET', 'POST'])
def declare(eid):
    if 'user_id' not in session: return redirect('/login')
    if request.method == 'POST':
        conn = get_db()
        try:
            conn.execute("INSERT INTO candidates (election_id, user_id, name, statement) VALUES (?, ?, ?, ?)", (eid, session['user_id'], request.form['name'], request.form['stmt']))
            conn.commit()
        except: pass
        conn.close()
        return redirect('/')
    return render_page(f"<div class='card'><h2>Declare Candidacy</h2><form method='post'><label>Candidate Name</label><input name='name' placeholder='Name'><label>Statement</label><textarea name='stmt' placeholder='Manifesto'></textarea><button class='btn btn-primary'>Submit Declaration</button></form></div>")

@app.route('/start/<int:eid>', methods=['POST'])
def start(eid):
    if session.get('user_id') not in ADMIN_IDS: return "Denied"
    conn = get_db()
    c = conn.cursor()
    cands = [r[0] for r in c.execute("SELECT name FROM candidates WHERE election_id=?", (eid,)).fetchall()]
    c.execute("UPDATE elections SET status='OPEN', candidates=? WHERE id=?", (json.dumps(cands), eid))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/vote/<int:eid>', methods=['GET', 'POST'])
def vote(eid):
    if 'user_id' not in session: return redirect('/login')
    
    # CSV Check
    if session['user_id'] not in get_registered_voters():
        return redirect('/register')

    conn = get_db()
    c = conn.cursor()
    e = c.execute("SELECT * FROM elections WHERE id=?", (eid,)).fetchone()
    if not e or e['status'] != 'OPEN': return "Closed"
    
    if c.execute("SELECT 1 FROM attendance WHERE user_id=? AND election_id=?", (session['user_id'], eid)).fetchone():
        return render_page("<div class='card'><h2>Already Voted</h2><a href='/' class='btn btn-primary'>Back</a></div>")

    cands = json.loads(e['candidates'])
    
    if request.method == 'POST':
        ballot = {}
        if e['type'] == 'REFERENDUM': ballot = {'choice': request.form['choice']}
        else: 
            for ca in cands: ballot[ca] = int(request.form.get(ca, 0))
        
        token = secrets.token_hex(6)
        c.execute("INSERT INTO attendance (user_id, election_id) VALUES (?, ?)", (session['user_id'], eid))
        c.execute("INSERT INTO ballots (id, election_id, vote_choice, verification_token) VALUES (?, ?, ?, ?)", (str(uuid.uuid4()), eid, json.dumps(ballot), token))
        conn.commit()
        conn.close()
        return render_page(f"<div class='card'><h2>Vote Cast!</h2><p>Token: <code>{token}</code></p><a href='/' class='btn btn-primary'>Home</a></div>")

    form = ""
    if e['type'] == 'REFERENDUM':
        form = "<label style='cursor:pointer; display:block; padding:10px; border:1px solid #ddd; margin-bottom:5px; border-radius:5px;'><input type='radio' name='choice' value='Yes' required> <strong>YES</strong></label><label style='cursor:pointer; display:block; padding:10px; border:1px solid #ddd; border-radius:5px;'><input type='radio' name='choice' value='No'> <strong>NO</strong></label>"
    else:
        stmts = {r[0]: r[1] for r in c.execute("SELECT name, statement FROM candidates WHERE election_id=?", (eid,)).fetchall()}
        for ca in cands:
            form += f"<div style='border-top:1px solid #eee; padding:15px 0;'><h3>{ca}</h3><p style='color:#555; font-style:italic;'>\"{stmts.get(ca, '')}\"</p><label>Score (0-5)</label><input type='number' name='{ca}' min='0' max='5' value='0' style='width:80px'></div>"

    return render_page(f"<div class='card'><h1>{e['title']}</h1><form method='post'>{form}<br><br><button class='btn btn-success'>Submit Secure Ballot</button></form></div>")

@app.route('/close/<int:eid>', methods=['POST'])
def close(eid):
    if session.get('user_id') not in ADMIN_IDS: return "Denied"
    conn = get_db()
    c = conn.cursor()
    e = c.execute("SELECT * FROM elections WHERE id=?", (eid,)).fetchone()
    rows = c.execute("SELECT vote_choice FROM ballots WHERE election_id=?", (eid,)).fetchall()
    ballots = [{'id': i, 'weight': 1.0, 'scores': json.loads(r[0])} for i, r in enumerate(rows)]
    
    if e['type'] == 'REFERENDUM':
        y = sum(1 for b in ballots if b['scores'].get('choice') == 'Yes')
        n = sum(1 for b in ballots if b['scores'].get('choice') == 'No')
        res = [f"Yes: {y}", f"No: {n}", "Passed" if y > n else "Failed"]
    elif e['type'] == 'STAR': res = calculate_star(ballots)
    elif e['type'] == 'SENATE': res = calculate_tea(ballots, json.loads(e['candidates']))
    
    c.execute("UPDATE elections SET status='CLOSED', results=? WHERE id=?", (json.dumps(res), eid))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/results/<int:eid>')
def results(eid):
    conn = get_db()
    c = conn.cursor()
    e = c.execute("SELECT * FROM elections WHERE id=?", (eid,)).fetchone()
    rows = c.execute("SELECT verification_token, vote_choice FROM ballots WHERE election_id=? ORDER BY RANDOM()", (eid,)).fetchall()
    conn.close()
    
    t_rows = "".join([f"<tr><td><code>{r[0]}</code></td><td>{r[1]}</td></tr>" for r in rows])
    return render_page(f"<div class='card'><h2>{e['title']} Results</h2><div style='background:#f0f9ff; padding:15px; border-radius:5px; margin-bottom:20px;'><strong>Outcome:</strong> {', '.join(json.loads(e['results']))}</div><table><tr><th>Token</th><th>Ballot</th></tr>{t_rows}</table><a href='/' class='btn btn-primary'>Home</a></div>")

@app.route('/login')
def login(): return redirect(f"{DISCORD_API_BASE_URL}/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify")

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code: return "No code"
    data = {'client_id': DISCORD_CLIENT_ID, 'client_secret': DISCORD_CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': DISCORD_REDIRECT_URI, 'scope': 'identify'}
    r = requests.post(f'{DISCORD_API_BASE_URL}/oauth2/token', data=data)
    token = r.json().get('access_token')
    user = requests.get(f'{DISCORD_API_BASE_URL}/users/@me', headers={'Authorization': f'Bearer {token}'}).json()
    session['user_id'] = user['id']
    return redirect('/')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)