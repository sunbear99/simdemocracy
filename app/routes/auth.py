from flask import Blueprint, session, redirect, request, current_app, url_for, render_template
import requests
import secrets
from app.utils import get_registered_voters 
# REMOVED: register_user_csv (No longer needed)

bp = Blueprint('auth', __name__)

# --- DISCORD AUTH ---

@bp.route('/login')
def login():
    return redirect(f"{current_app.config['DISCORD_API_BASE_URL']}/oauth2/authorize?client_id={current_app.config['DISCORD_CLIENT_ID']}&redirect_uri={current_app.config['DISCORD_REDIRECT_URI']}&response_type=code&scope=identify")

@bp.route('/callback')
def callback():
    code = request.args.get('code')
    if not code: return "No code provided."
    
    data = {
        'client_id': current_app.config['DISCORD_CLIENT_ID'],
        'client_secret': current_app.config['DISCORD_CLIENT_SECRET'],
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': current_app.config['DISCORD_REDIRECT_URI'],
        'scope': 'identify'
    }
    
    # Exchange Code for Token
    token_url = f"{current_app.config['DISCORD_API_BASE_URL']}/oauth2/token"
    r = requests.post(token_url, data=data)
    
    if r.status_code != 200:
        return f"Discord Login Failed: {r.status_code}. Response: {r.text}"

    try:
        token = r.json().get('access_token')
        user_r = requests.get(
            f"{current_app.config['DISCORD_API_BASE_URL']}/users/@me", 
            headers={'Authorization': f'Bearer {token}'}
        )
        
        if user_r.status_code != 200: return f"Failed to fetch user: {user_r.text}"
            
        user = user_r.json()
        
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['avatar_url'] = f"https://cdn.discordapp.com/avatars/{user['id']}/{user['avatar']}.png" if user.get('avatar') else "https://cdn.discordapp.com/embed/avatars/0.png"
            
        return redirect(url_for('main.dashboard'))
        
    except Exception as e:
        return f"Login Error: {str(e)}"

# --- REDDIT AUTH ---

@bp.route('/login/reddit')
def login_reddit():
    state = secrets.token_hex(16)
    session['oauth_state'] = state
    
    client_id = current_app.config['REDDIT_CLIENT_ID']
    redirect_uri = current_app.config['REDDIT_REDIRECT_URI']
    
    url = f"https://www.reddit.com/api/v1/authorize?client_id={client_id}&response_type=code&state={state}&redirect_uri={redirect_uri}&duration=temporary&scope=identity"
    return redirect(url)

@bp.route('/callback/reddit')
def callback_reddit():
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    if error: return f"Reddit Error: {error}"
    if not code: return "No code provided."
    if state != session.get('oauth_state'): return "Invalid state parameter (CSRF detected)."
    
    client_id = current_app.config['REDDIT_CLIENT_ID']
    client_secret = current_app.config['REDDIT_CLIENT_SECRET']
    redirect_uri = current_app.config['REDDIT_REDIRECT_URI']
    
    auth = requests.auth.HTTPBasicAuth(client_id, client_secret)
    data = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': redirect_uri}
    headers = {'User-Agent': current_app.config['REDDIT_USER_AGENT']}
    
    r = requests.post('https://www.reddit.com/api/v1/access_token', auth=auth, data=data, headers=headers)
    
    if r.status_code != 200: return f"Reddit Token Error: {r.text}"
    
    token = r.json().get('access_token')
    
    headers['Authorization'] = f"bearer {token}"
    me_r = requests.get('https://oauth.reddit.com/api/v1/me', headers=headers)
    
    if me_r.status_code != 200: return f"Reddit User Fetch Error: {me_r.text}"
    
    user = me_r.json()
    username = user.get('name')
    session['user_id'] = f"reddit_{username}" 
    session['username'] = f"u/{username}"
    session['avatar_url'] = "https://www.redditstatic.com/avatars/defaults/v2/avatar_default_1.png"
    
    return redirect(url_for('main.dashboard'))

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.dashboard'))