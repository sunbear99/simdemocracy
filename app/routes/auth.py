from flask import Blueprint, session, redirect, request, current_app, url_for, render_template
import requests
from app.utils import get_registered_voters, register_user_csv

bp = Blueprint('auth', __name__)

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
    
    r = requests.post(f"{current_app.config['DISCORD_API_BASE_URL']}/oauth2/token", data=data)
    token = r.json().get('access_token')
    
    user = requests.get(f"{current_app.config['DISCORD_API_BASE_URL']}/users/@me", headers={'Authorization': f'Bearer {token}'}).json()
    
    session['user_id'] = user['id']
    session['username'] = user['username']
    if user.get('avatar'):
        session['avatar_url'] = f"https://cdn.discordapp.com/avatars/{user['id']}/{user['avatar']}.png"
    else:
        session['avatar_url'] = "https://cdn.discordapp.com/embed/avatars/0.png"
        
    return redirect(url_for('main.dashboard'))

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.dashboard'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' not in session: return redirect(url_for('auth.login'))
    if session['user_id'] in get_registered_voters(): return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        if request.form.get('alt_check') == 'No':
            register_user_csv(session['user_id'])
            return render_template('message.html', title="Registered!", message="You can now vote.", type="success")
        else:
            return render_template('message.html', title="Denied", message="Tide alts are not permitted.", type="danger")
            
    return render_template('register.html')