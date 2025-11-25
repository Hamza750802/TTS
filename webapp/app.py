"""
Web app for Cheap TTS with auth + Stripe subscriptions
"""
import asyncio
import hashlib
import os
import secrets
import time
from datetime import datetime
from functools import wraps
from pathlib import Path

import stripe

# Load environment variables from .env file
from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

import edge_tts

load_dotenv()

app = Flask(__name__)

# Basic config
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-change-me')

# Database configuration - use PostgreSQL on Railway, SQLite locally
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Railway provides DATABASE_URL for PostgreSQL (persists across deploys)
    # Fix for SQLAlchemy 1.4+ which needs postgresql:// instead of postgres://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Development: use local SQLite
    basedir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(basedir, 'users.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Debug mode from environment
DEBUG_MODE = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes')

# Configure WTForms CSRF
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_TIME_LIMIT'] = None  # No timeout for CSRF tokens

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
csrf = CSRFProtect(app)

# Rate limiter for API abuse protection
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Stripe config (set env vars in production)
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_PRICE_ID = os.environ.get('STRIPE_PRICE_ID', '')  # monthly price id
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

# Admin API key (for your personal projects - free access)
ADMIN_API_KEY = os.environ.get('ADMIN_API_KEY', '')  # Set this in .env


def billing_enabled() -> bool:
    """Return True when Stripe billing is configured."""
    return bool(stripe.api_key and STRIPE_PRICE_ID)

# Create output directory for generated audio files
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def cleanup_old_files(days=7):
    """Remove generated audio files older than specified days"""
    import time
    current_time = time.time()
    days_in_seconds = days * 24 * 60 * 60
    
    for file_path in OUTPUT_DIR.glob("speech_*.mp3"):
        if current_time - file_path.stat().st_mtime > days_in_seconds:
            try:
                file_path.unlink()
            except Exception:
                pass

# Cache for voices
_voices_cache = None


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    stripe_customer_id = db.Column(db.String(255))
    subscription_status = db.Column(db.String(64), default='inactive')  # inactive | active | past_due | canceled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_subscribed(self) -> bool:
        return self.subscription_status == 'active'


class APIKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)  # User-friendly name
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime)
    
    user = db.relationship('User', backref=db.backref('api_keys', lazy=True))

    @staticmethod
    def generate_key():
        import secrets
        # Keep generating until unique to avoid rare collisions
        while True:
            candidate = f"ctts_{secrets.token_urlsafe(32)}"
            if not APIKey.query.filter_by(key=candidate).first():
                return candidate


# Initialize database tables (creates tables on app startup, works with Gunicorn)
with app.app_context():
    db.create_all()

# Cleanup old files on startup (works with Gunicorn)
cleanup_old_files()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


async def get_voices():
    """Get all available voices"""
    global _voices_cache
    if _voices_cache is None:
        voices = await edge_tts.list_voices()
        _voices_cache = voices
    return _voices_cache


async def generate_speech(text, voice, rate=None, volume=None, pitch=None, is_ssml=False):
    """Generate speech from text or SSML"""
    # Create unique filename
    unique_id = hashlib.md5(f"{text}{voice}{time.time()}".encode()).hexdigest()[:10]
    output_file = OUTPUT_DIR / f"speech_{unique_id}.mp3"

    if is_ssml:
        # For SSML, we need to bypass the escape() call in Communicate
        # We'll use the internal edge_tts module structure
        import edge_tts.communicate
        from xml.sax.saxutils import escape
        
        # Temporarily replace escape with a no-op for SSML
        original_escape = edge_tts.communicate.escape
        edge_tts.communicate.escape = lambda x: x  # Don't escape SSML tags
        
        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate="+0%",  # SSML has its own prosody
                volume="+0%",
                pitch="+0Hz"
            )
            await communicate.save(str(output_file))
        finally:
            # Restore original escape function
            edge_tts.communicate.escape = original_escape
    else:
        # Regular text-to-speech (non-SSML)
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate or "+0%",
            volume=volume or "+0%",
            pitch=pitch or "+0Hz"
        )
        await communicate.save(str(output_file))

    return output_file


@app.route('/')
def index():
    """Serve the landing page"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')


@app.route('/dashboard')
@login_required
def dashboard():
    """Serve the TTS tool page"""
    return render_template('index.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if not email or not password:
            flash('Email and password are required.', 'error')
            return redirect(url_for('signup'))
        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'error')
            return redirect(url_for('signup'))
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash('Welcome! Your account has been created.', 'success')
        return redirect(url_for('index'))
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        # Admin bypass for testing - if password is the admin key, auto-login
        if password == ADMIN_API_KEY:
            user = User.query.filter_by(email=email).first()
            if user:
                login_user(user)
                flash('Admin login successful.', 'success')
                return redirect(url_for('index'))
        
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash('Invalid email or password.', 'error')
            return redirect(url_for('login'))
        login_user(user)
        flash('Signed in successfully.', 'success')
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Signed out.', 'success')
    return redirect(url_for('login'))


def subscription_required(func):
    """Decorator to require active subscription"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # If billing is disabled, allow access without subscription
        if not billing_enabled():
            return func(*args, **kwargs)
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if not current_user.is_subscribed:
            flash('Active subscription required to access this feature.', 'error')
            return redirect(url_for('subscribe'))
        return func(*args, **kwargs)
    return wrapper


def run_async(coro):
    """Helper to run async functions in sync context"""
    return asyncio.run(coro)


def refresh_subscription_from_stripe(user) -> bool:
    """
    Best-effort refresh of a user's subscription status from Stripe.
    Returns True if the user ends up active after refresh.
    """
    if not billing_enabled():
        return True
    if not user.stripe_customer_id:
        return False
    try:
        subs = stripe.Subscription.list(customer=user.stripe_customer_id, status='all', limit=1)
        sub = subs.data[0] if subs.data else None
        if sub:
            status = sub.status
            user.subscription_status = 'active' if status in ('active', 'trialing') else status
            db.session.commit()
        return user.is_subscribed
    except Exception:
        return False

@app.route('/api/voices', methods=['GET'])
def api_voices():
    """Get list of available voices (public endpoint for preview)"""
    try:
        voices = run_async(get_voices())
        
        # Format voices for frontend
        formatted_voices = []
        for voice in voices:
            styles = voice.get('StyleList', []) or []
            formatted_voices.append({
                'name': voice['Name'],
                'shortName': voice['ShortName'],
                'gender': voice['Gender'],
                'locale': voice['Locale'],
                'localName': voice.get('LocalName', voice['ShortName']),
                'styles': styles,
                'has_styles': bool(styles),
            })
        
        return jsonify({'success': True, 'voices': formatted_voices})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# -------- Stripe billing --------

@app.route('/subscribe')
@login_required
def subscribe():
    # If already subscribed, redirect to dashboard
    if current_user.is_subscribed:
        flash('You already have an active subscription!', 'info')
        return redirect(url_for('index'))
    
    # Check Stripe configuration
    if not stripe.api_key:
        print("ERROR: STRIPE_SECRET_KEY not configured!")
        flash('Payment system not configured. Please contact support.', 'error')
        return redirect(url_for('index'))
    
    if not STRIPE_PRICE_ID:
        print("ERROR: STRIPE_PRICE_ID not configured!")
        flash('Subscription pricing not configured. Please contact support.', 'error')
        return redirect(url_for('index'))
    
    try:
        print(f"Creating Stripe checkout session for user {current_user.email}")
        success_url = url_for('subscription_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}'
        cancel_url = url_for('subscription_cancel', _external=True)

        customer = None
        if current_user.stripe_customer_id:
            customer = current_user.stripe_customer_id
            print(f"Using existing Stripe customer: {customer}")

        session = stripe.checkout.Session.create(
            mode='subscription',
            line_items=[{'price': STRIPE_PRICE_ID, 'quantity': 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            customer=customer,
            customer_email=(None if customer else current_user.email),
            automatic_tax={'enabled': True},
        )

        print(f"Stripe session created: {session.id}, redirecting to: {session.url}")
        return redirect(session.url)
    except Exception as e:
        print(f"ERROR creating Stripe checkout session: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Error creating checkout session: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/create-checkout-session', methods=['POST'])
@login_required
@csrf.exempt  # Exempting because this is an API endpoint called from JS
def create_checkout_session():
    if not stripe.api_key or not STRIPE_PRICE_ID:
        return jsonify({'error': 'Stripe not configured'}), 500

    try:
        success_url = url_for('subscription_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}'
        cancel_url = url_for('subscription_cancel', _external=True)

        customer = None
        if current_user.stripe_customer_id:
            customer = current_user.stripe_customer_id

        session = stripe.checkout.Session.create(
            mode='subscription',
            line_items=[{'price': STRIPE_PRICE_ID, 'quantity': 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            customer=customer,
            customer_email=(None if customer else current_user.email),
            automatic_tax={'enabled': True},
        )

        return jsonify({'url': session.url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/subscription/success')
@login_required
def subscription_success():
    session_id = request.args.get('session_id')
    if stripe.api_key and session_id:
        try:
            cs = stripe.checkout.Session.retrieve(session_id, expand=['subscription'])
            if cs.get('customer') and not current_user.stripe_customer_id:
                current_user.stripe_customer_id = cs['customer']
                db.session.commit()
            # Optimistically mark active; webhook will keep it in sync
            current_user.subscription_status = 'active'
            db.session.commit()
        except Exception:
            pass
    flash('Subscription activated. Enjoy!', 'success')
    return redirect(url_for('index'))


@app.route('/subscription/cancel')
@login_required
def subscription_cancel():
    flash('Subscription checkout canceled.', 'error')
    return redirect(url_for('subscribe'))


@app.route('/billing-portal')
@login_required
def billing_portal():
    if not stripe.api_key:
        flash('Payments are not configured. Please contact support.', 'error')
        return redirect(url_for('index'))

    try:
        customer_id = current_user.stripe_customer_id
        
        print(f"Billing portal request for user {current_user.email}, customer_id: {customer_id}")

        # Fallback: look up the customer in Stripe by email if we didn't store the id
        if not customer_id:
            print(f"No customer_id stored, looking up by email in Stripe...")
            customers = stripe.Customer.list(email=current_user.email, limit=1)
            if customers and customers.data:
                customer_id = customers.data[0].id
                current_user.stripe_customer_id = customer_id
                db.session.commit()
                print(f"Found customer in Stripe: {customer_id}")

        if not customer_id:
            print(f"ERROR: No Stripe customer found for {current_user.email}")
            flash('No Stripe customer found for your account. Please contact support.', 'error')
            return redirect(url_for('index'))

        print(f"Creating billing portal session for customer: {customer_id}")
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=url_for('index', _external=True),
        )
        print(f"Billing portal session created: {session.url}")
        return redirect(session.url)
    except stripe.error.InvalidRequestError as e:
        print(f"Stripe InvalidRequestError: {str(e)}")
        flash(f'Invalid Stripe customer. Error: {str(e)}', 'error')
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Billing portal error: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Unable to open the billing portal: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/stripe/webhook', methods=['POST'])
@csrf.exempt  # Webhooks don't include CSRF tokens
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature', '')
    event = None

    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        else:
            event = stripe.Event.construct_from(request.get_json(force=True), stripe.api_key)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 400

    et = event['type']

    try:
        if et == 'checkout.session.completed':
            obj = event['data']['object']
            customer_id = obj.get('customer')
            email = obj.get('customer_details', {}).get('email')
            if email:
                user = User.query.filter_by(email=email).first()
            else:
                user = User.query.filter_by(stripe_customer_id=customer_id).first()
            if user:
                if customer_id:
                    user.stripe_customer_id = customer_id
                user.subscription_status = 'active'
                db.session.commit()
        elif et in ('customer.subscription.updated', 'customer.subscription.created'):
            sub = event['data']['object']
            customer_id = sub.get('customer')
            status = sub.get('status')  # 'active', 'past_due', 'canceled', etc.
            user = User.query.filter_by(stripe_customer_id=customer_id).first()
            if user:
                # Map Stripe status -> our status
                user.subscription_status = 'active' if status in ('active', 'trialing') else status
                db.session.commit()
        elif et == 'customer.subscription.deleted':
            sub = event['data']['object']
            customer_id = sub.get('customer')
            user = User.query.filter_by(stripe_customer_id=customer_id).first()
            if user:
                user.subscription_status = 'canceled'
                db.session.commit()
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

    return jsonify(success=True)


@app.route('/api/preview', methods=['POST'])
@csrf.exempt
@limiter.limit("10 per minute")  # Rate limit for abuse protection
def api_preview():
    """Generate preview speech (max 150 chars, no auth required)"""
    try:
        data = request.get_json(silent=True) or {}
        if not data:
            return jsonify({'success': False, 'error': 'Invalid JSON'}), 400
            
        text = data.get('text', '')
        voice = data.get('voice', 'en-US-EmmaMultilingualNeural')
        rate = data.get('rate', '+0%')
        volume = data.get('volume', '+0%')
        pitch = data.get('pitch', '+0Hz')
        
        # Ensure proper formatting for rate, volume, and pitch
        if not rate.startswith(('+', '-')):
            rate = '+' + rate
        if not volume.startswith(('+', '-')):
            volume = '+' + volume
        if not pitch.startswith(('+', '-')):
            pitch = '+' + pitch
        
        if not text:
            return jsonify({'success': False, 'error': 'No text provided'}), 400
        
        # Enforce 150 character limit for preview
        if len(text) > 150:
            return jsonify({
                'success': False, 
                'error': f'Preview limited to 150 characters. You entered {len(text)}. Sign up for unlimited!'
            }), 400
        
        # Generate speech
        try:
            output_file = run_async(generate_speech(text, voice, rate, volume, pitch))
        except Exception as gen_error:
            return jsonify({'success': False, 'error': f'Speech generation failed: {str(gen_error)}'}), 500
        
        return jsonify({
            'success': True,
            'audioUrl': f'/api/audio/{output_file.name}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/generate', methods=['POST'])
@login_required
@subscription_required
@csrf.exempt
def api_generate():
    """Generate speech from text"""
    try:
        data = request.get_json(silent=True) or {}
        raw_text = data.get('text', '')
        text = raw_text.strip()
        voice = data.get('voice', 'en-US-EmmaMultilingualNeural')
        rate = data.get('rate', '+0%')
        volume = data.get('volume', '+0%')
        pitch = data.get('pitch', '+0Hz')
        is_ssml = bool(data.get('is_ssml')) or raw_text.strip().lower().startswith('<speak')
        
        # Ensure proper formatting for rate, volume, and pitch
        if not rate.startswith(('+', '-')):
            rate = '+' + rate
        if not volume.startswith(('+', '-')):
            volume = '+' + volume
        if not pitch.startswith(('+', '-')):
            pitch = '+' + pitch
        
        if not text:
            return jsonify({'success': False, 'error': 'No text provided'}), 400

        # Generate speech (SSML uses embedded prosody; skip rate/volume/pitch overrides)
        output_file = run_async(
            generate_speech(
                text,
                voice,
                None if is_ssml else rate,
                None if is_ssml else volume,
                None if is_ssml else pitch,
                is_ssml=is_ssml
            )
        )
        
        return jsonify({
            'success': True,
            'audioUrl': f'/api/audio/{output_file.name}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/audio/<filename>')
def api_audio(filename):
    """Serve audio file (public for previews)"""
    try:
        file_path = OUTPUT_DIR / filename
        if file_path.exists():
            return send_file(file_path, mimetype='audio/mpeg')
        else:
            return jsonify({'success': False, 'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# -------- API Key Management --------

@app.route('/embed')
def embed_widget():
    """Embeddable TTS widget"""
    api_key = request.args.get('key', '')
    
    # Validate API key if provided
    if api_key:
        auth_result = verify_api_key(api_key)
        if not auth_result.get('valid'):
            return f"Invalid API key. Please check your key and try again.", 401
    else:
        return "API key required. Add ?key=your_api_key to the URL.", 401
    
    return render_template('embed.html', api_key=api_key)


@app.route('/api-keys')
@login_required
@subscription_required
def api_keys_page():
    """Show user's API keys"""
    return render_template('api_keys.html', keys=current_user.api_keys)


@app.route('/api/keys/create', methods=['POST'])
@login_required
@subscription_required
@csrf.exempt
def create_api_key():
    """Create a new API key"""
    payload = request.get_json(silent=True) or {}
    name = str(payload.get('name', 'Unnamed Key')).strip()
    if not name:
        return jsonify({'success': False, 'error': 'Key name required'}), 400
    
    # Generate new key
    new_key = APIKey(
        user_id=current_user.id,
        key=APIKey.generate_key(),
        name=name
    )
    db.session.add(new_key)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'key': new_key.key,
        'name': new_key.name,
        'created_at': new_key.created_at.isoformat()
    })


@app.route('/api/keys/<int:key_id>/delete', methods=['POST'])
@login_required
@subscription_required
@csrf.exempt
def delete_api_key(key_id):
    """Delete an API key"""
    api_key = APIKey.query.filter_by(id=key_id, user_id=current_user.id).first()
    if not api_key:
        return jsonify({'success': False, 'error': 'Key not found'}), 404
    
    db.session.delete(api_key)
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/keys/<int:key_id>/toggle', methods=['POST'])
@login_required
@subscription_required
@csrf.exempt
def toggle_api_key(key_id):
    """Enable/disable an API key"""
    api_key = APIKey.query.filter_by(id=key_id, user_id=current_user.id).first()
    if not api_key:
        return jsonify({'success': False, 'error': 'Key not found'}), 404
    
    api_key.is_active = not api_key.is_active
    db.session.commit()
    
    return jsonify({'success': True, 'is_active': api_key.is_active})


# -------- API Endpoint (for external use) --------

def verify_api_key(api_key_string):
    """Verify API key and return user if valid"""
    api_key_string = (api_key_string or '').strip()
    if not api_key_string:
        return {'valid': False, 'error': 'API key required'}

    # Check if it's the admin key (FREE for your personal use)
    if ADMIN_API_KEY and api_key_string == ADMIN_API_KEY:
        return {'is_admin': True, 'valid': True}
    
    # Check regular user API keys
    api_key = APIKey.query.filter_by(key=api_key_string, is_active=True).first()
    if not api_key:
        return {'valid': False, 'error': 'Invalid API key'}
    
    # Update last used timestamp
    api_key.last_used_at = datetime.utcnow()
    db.session.commit()
    
    # Check if user's subscription is active
    if billing_enabled() and not api_key.user.is_subscribed:
        # Try to refresh from Stripe in case webhook missed an update
        if not refresh_subscription_from_stripe(api_key.user):
            return {'valid': False, 'error': 'Subscription expired'}
    
    return {'valid': True, 'is_admin': False, 'user': api_key.user}


@app.route('/api/v1/synthesize', methods=['POST'])
@csrf.exempt  # API endpoint - no CSRF needed
@limiter.limit("100 per hour")  # Rate limit for API endpoint
def api_synthesize():
    """
    API endpoint for text-to-speech synthesis
    
    Headers:
        X-API-Key: Your API key
    
    Body (JSON):
        {
            "text": "Text to convert to speech",
            "voice": "en-US-AriaNeural" (optional),
            "rate": "+0%" (optional),
            "volume": "+0%" (optional),
            "pitch": "+0Hz" (optional)
        }
    
    Returns:
        {
            "success": true,
            "audio_url": "URL to download the audio file",
            "filename": "speech_xxxxx.mp3"
        }
    """
    # Get API key from header
    api_key = (request.headers.get('X-API-Key') or '').strip()
    if not api_key:
        return jsonify({'success': False, 'error': 'API key required. Provide X-API-Key header.'}), 401
    
    # Verify API key
    auth_result = verify_api_key(api_key)
    if not auth_result.get('valid'):
        return jsonify({'success': False, 'error': auth_result.get('error', 'Invalid API key')}), 401
    
    try:
        data = request.get_json(silent=True) or {}
        raw_text = data.get('text', '')
        text = raw_text.strip()
        voice = data.get('voice', 'en-US-AriaNeural')
        rate = data.get('rate', '+0%')
        volume = data.get('volume', '+0%')
        pitch = data.get('pitch', '+0Hz')
        is_ssml = bool(data.get('is_ssml')) or raw_text.strip().lower().startswith('<speak')
        
        # Ensure proper formatting
        if not rate.startswith(('+', '-')):
            rate = '+' + rate
        if not volume.startswith(('+', '-')):
            volume = '+' + volume
        if not pitch.startswith(('+', '-')):
            pitch = '+' + pitch
        
        if not text:
            return jsonify({'success': False, 'error': 'Text is required'}), 400
        
        # Generate speech (SSML uses embedded prosody; skip rate/volume/pitch overrides)
        output_file = run_async(
            generate_speech(
                text,
                voice,
                None if is_ssml else rate,
                None if is_ssml else volume,
                None if is_ssml else pitch,
                is_ssml=is_ssml
            )
        )
        
        # Return the audio URL
        audio_url = request.url_root.rstrip('/') + f'/api/audio/{output_file.name}'
        
        return jsonify({
            'success': True,
            'audio_url': audio_url,
            'filename': output_file.name
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/v1/voices', methods=['GET'])
def api_list_voices():
    """
    API endpoint to list all available voices
    
    Headers:
        X-API-Key: Your API key (optional for this endpoint)
    
    Returns:
        {
            "success": true,
            "voices": [...]
        }
    """
    try:
        voices = run_async(get_voices())
        
        formatted_voices = []
        for voice in voices:
            styles = voice.get('StyleList', []) or []
            formatted_voices.append({
                'name': voice['Name'],
                'short_name': voice['ShortName'],
                'gender': voice['Gender'],
                'locale': voice['Locale'],
                'local_name': voice.get('LocalName', voice['ShortName']),
                'styles': styles,
                'has_styles': bool(styles),
            })
        
        return jsonify({'success': True, 'voices': formatted_voices, 'count': len(formatted_voices)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/grant-access/<email>')
def admin_grant_access(email):
    """Admin route to grant unlimited access to a user"""
    # Security check - only accessible with admin password
    admin_pass = request.args.get('key')
    if admin_pass != ADMIN_API_KEY:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        # Check if we should simulate a Stripe customer (for testing billing portal)
        simulate_stripe = request.args.get('stripe', '').lower() == 'true'
        custom_password = request.args.get('password', None)
        
        user = User.query.filter_by(email=email).first()
        if not user:
            # Auto-create the user if they don't exist
            user = User(email=email, subscription_status='active')
            if simulate_stripe:
                # Set a fake Stripe customer ID for testing
                user.stripe_customer_id = 'cus_test_' + email.split('@')[0]
            # Set password
            import secrets
            password = custom_password if custom_password else secrets.token_urlsafe(16)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'message': f'User created and unlimited access granted to {email}' + (' (with Stripe simulation)' if simulate_stripe else ''),
                'user': {
                    'email': user.email,
                    'password': password if custom_password else 'Random password set - use forgot password to reset',
                    'subscription_status': user.subscription_status,
                    'stripe_customer_id': user.stripe_customer_id,
                    'created_at': user.created_at.isoformat()
                }
            })
        
        # Grant unlimited access to existing user
        user.subscription_status = 'active'
        if simulate_stripe and not user.stripe_customer_id:
            user.stripe_customer_id = 'cus_test_' + email.split('@')[0]
        if custom_password:
            user.set_password(custom_password)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Unlimited access granted to {email}' + (' (with Stripe simulation)' if simulate_stripe else ''),
            'user': {
                'email': user.email,
                'password_updated': bool(custom_password),
                'subscription_status': user.subscription_status,
                'stripe_customer_id': user.stripe_customer_id,
                'created_at': user.created_at.isoformat()
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Initialize DB if needed
    with app.app_context():
        db.create_all()
    
    # Cleanup old files on startup
    cleanup_old_files()
    
    # Run the app
    debug_mode = os.environ.get('DEBUG_MODE', 'False').lower() == 'true'
    print("Starting Cheap TTS web interface...")
    print("Open your browser and go to: http://localhost:5000")
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
