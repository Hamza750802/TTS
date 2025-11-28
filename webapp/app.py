"""
Web app for Cheap TTS with auth + Stripe subscriptions
"""
import asyncio
import hashlib
import os
import secrets
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
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

# Import local modified edge_tts first (for emotion support)
import sys
from pathlib import Path
webapp_dir = Path(__file__).parent
sys.path.insert(0, str(webapp_dir))  # Ensure local edge_tts is imported first
import edge_tts

# Import chunking and SSML modules from same directory
from chunk_processor import process_text
from ssml_builder import build_ssml

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

# Stripe Price IDs
STRIPE_LIFETIME_PRICE_ID = 'price_1SYORtLz6FHVmZlME0DueU5x'  # $99 lifetime web access
STRIPE_API_STARTER_PRICE_ID = 'price_1SYOzjLz6FHVmZlMyFmi6ihW'  # $9/mo API Starter
STRIPE_API_PRO_PRICE_ID = 'price_1SYP06Lz6FHVmZlM2FPE35Rm'  # $29/mo API Pro

# Password reset + email settings
try:
    RESET_TOKEN_EXPIRATION_HOURS = int(os.environ.get('RESET_TOKEN_EXPIRATION_HOURS') or 1)
except (TypeError, ValueError):
    RESET_TOKEN_EXPIRATION_HOURS = 1
SMTP_HOST = os.environ.get('SMTP_HOST')
try:
    SMTP_PORT = int(os.environ.get('SMTP_PORT') or 587)
except (TypeError, ValueError):
    SMTP_PORT = 587
SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
SMTP_USE_TLS = os.environ.get('SMTP_USE_TLS', 'true').lower() in ('true', '1', 'yes')
PASSWORD_RESET_SENDER = os.environ.get('PASSWORD_RESET_SENDER', SMTP_USERNAME or 'no-reply@cheaptts.com')

# Per-request guardrail: keep each TTS call comfortably under the service timeout
try:
    MAX_CHARS_PER_CHUNK = int(os.environ.get('MAX_CHARS_PER_CHUNK') or 900)
except (TypeError, ValueError):
    MAX_CHARS_PER_CHUNK = 900


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

# Curated hero voice presets with tuned defaults
HERO_PRESETS = [
    {
        "id": "aria_chat_bright",
        "label": "Aria (chat, bright)",
        "voice": "en-US-AriaNeural",
        "emotion": "chat",
        "intensity": 2,
        "rate": -2,
        "pitch": 4,
        "volume": 0,
        "description": "Clear, friendly delivery for narration."
    },
    {
        "id": "jenny_story_cheer",
        "label": "Jenny (cheerful, story) ⭐ MOST VERSATILE",
        "voice": "en-US-JennyNeural",
        "emotion": "cheerful",
        "intensity": 2,
        "rate": -5,
        "pitch": 3,
        "volume": 0,
        "description": "14 emotions available. Perfect for multi-speaker dialogue, storytelling, and dynamic content."
    },
    {
        "id": "guy_serious",
        "label": "Guy (serious) ⭐ RECOMMENDED",
        "voice": "en-US-GuyNeural",
        "emotion": "serious",
        "intensity": 2,
        "rate": -3,
        "pitch": -2,
        "volume": 0,
        "description": "11 emotions available. Ideal for podcasts, conversations, and professional voiceovers."
    }
]


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    stripe_customer_id = db.Column(db.String(255))
    subscription_status = db.Column(db.String(64), default='inactive')  # inactive | active | past_due | canceled | lifetime
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # API Access - separate from web subscription
    # api_tier: 'none' | 'starter' | 'pro' | 'enterprise'
    api_tier = db.Column(db.String(32), default='none')
    api_credits = db.Column(db.Integer, default=0)  # Unused - kept for future
    api_stripe_subscription_id = db.Column(db.String(255))  # Separate Stripe subscription for API
    
    # API Usage Tracking
    api_chars_used = db.Column(db.Integer, default=0)  # Characters used this billing period
    api_usage_reset_at = db.Column(db.DateTime)  # When usage resets (monthly)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_subscribed(self) -> bool:
        """Web UI subscription (TTS tool access) - includes lifetime"""
        return self.subscription_status in ('active', 'lifetime')
    
    @property
    def is_lifetime(self) -> bool:
        """Check if user has lifetime access"""
        return self.subscription_status == 'lifetime'
    
    @property
    def has_api_access(self) -> bool:
        """API access (separate from web subscription)"""
        return self.api_tier in ('starter', 'pro', 'enterprise')
    
    @property
    def api_char_limit(self) -> int:
        """Get character limit based on API tier"""
        limits = {
            'starter': 100000,      # 100k chars/month
            'pro': 500000,          # 500k chars/month
            'enterprise': 999999999  # Effectively unlimited
        }
        return limits.get(self.api_tier, 0)
    
    @property
    def api_chars_remaining(self) -> int:
        """Get remaining characters for this billing period"""
        if not self.has_api_access:
            return 0
        return max(0, self.api_char_limit - (self.api_chars_used or 0))
    
    def check_and_reset_api_usage(self):
        """Reset API usage if billing period has passed (monthly)"""
        if not self.api_usage_reset_at:
            # First time - set reset date to 30 days from now
            self.api_usage_reset_at = datetime.utcnow() + timedelta(days=30)
            self.api_chars_used = 0
            return
        
        if datetime.utcnow() >= self.api_usage_reset_at:
            # Reset usage and set new reset date
            self.api_chars_used = 0
            self.api_usage_reset_at = datetime.utcnow() + timedelta(days=30)
    
    def use_api_chars(self, char_count: int) -> bool:
        """
        Track API character usage. Returns True if within limit, False if exceeded.
        """
        if not self.has_api_access:
            return False
        
        # Check and reset if needed
        self.check_and_reset_api_usage()
        
        # Check if this request would exceed limit
        if (self.api_chars_used or 0) + char_count > self.api_char_limit:
            return False
        
        # Track usage
        self.api_chars_used = (self.api_chars_used or 0) + char_count
        return True


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


class PasswordResetToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)

    user = db.relationship('User', backref=db.backref('password_reset_tokens', lazy=True))


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_reset_token(user: User) -> str:
    """Create a one-time password reset token for a user."""
    # Remove existing tokens so only the newest link remains valid.
    PasswordResetToken.query.filter_by(user_id=user.id).delete()

    raw_token = secrets.token_urlsafe(32)
    token = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.utcnow() + timedelta(hours=RESET_TOKEN_EXPIRATION_HOURS),
    )
    db.session.add(token)
    db.session.commit()
    return raw_token


def verify_reset_token(raw_token: str):
    """Return token record if valid and unused; otherwise None."""
    token_hash = _hash_token(raw_token)
    token = PasswordResetToken.query.filter_by(token_hash=token_hash).first()
    if not token or token.used_at:
        return None
    if token.expires_at < datetime.utcnow():
        return None
    return token


def send_password_reset_email(to_email: str, reset_link: str) -> None:
    """Send the reset link via SMTP, with console fallback for local/dev."""
    message = EmailMessage()
    message['Subject'] = "Reset your Cheap TTS password"
    message['From'] = PASSWORD_RESET_SENDER
    message['To'] = to_email
    message.set_content(
        "Hi,\n\n"
        "We received a request to reset your Cheap TTS password. "
        "Use the link below to set a new password:\n\n"
        f"{reset_link}\n\n"
        "If you did not request this, you can ignore this email.\n"
    )

    if SMTP_HOST:
        try:
            import smtplib
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                if SMTP_USE_TLS:
                    server.starttls()
                if SMTP_USERNAME and SMTP_PASSWORD:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(message)
            print(f"[PASSWORD RESET] Sent reset email to {to_email}")
            return
        except Exception as exc:
            print(f"[PASSWORD RESET] Failed to send email via SMTP: {exc}")

    # Local/dev fallback
    print(f"[PASSWORD RESET] Reset link for {to_email}: {reset_link}")


# Initialize database tables (creates tables on app startup, works with Gunicorn)
with app.app_context():
    db.create_all()
    
    # Migrate: Add new API columns if they don't exist (for existing databases)
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    existing_columns = [col['name'] for col in inspector.get_columns('user')]
    
    with db.engine.connect() as conn:
        if 'api_tier' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN api_tier VARCHAR(32) DEFAULT 'none'"))
            print("[MIGRATION] Added api_tier column to user table")
        if 'api_credits' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN api_credits INTEGER DEFAULT 0"))
            print("[MIGRATION] Added api_credits column to user table")
        if 'api_stripe_subscription_id' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN api_stripe_subscription_id VARCHAR(255)"))
            print("[MIGRATION] Added api_stripe_subscription_id column to user table")
        if 'api_chars_used' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN api_chars_used INTEGER DEFAULT 0"))
            print("[MIGRATION] Added api_chars_used column to user table")
        if 'api_usage_reset_at' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN api_usage_reset_at TIMESTAMP"))
            print("[MIGRATION] Added api_usage_reset_at column to user table")
        conn.commit()

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


async def generate_speech(text, voice, rate=None, volume=None, pitch=None, is_ssml=False, cache_key=None, is_full_ssml=False, style=None, style_degree=None):
    """Generate speech from text or SSML. Optional cache_key for deterministic filenames.
    
    Args:
        is_ssml: If True, text contains SSML tags (but may not be full SSML)
        is_full_ssml: If True, text is complete SSML with <speak> wrapper (for multi-voice)
        style: Emotion/style (e.g., "cheerful") for single-voice with emotion
        style_degree: Style intensity (0.01-2.0) for single-voice with emotion
    """
    import re
    import edge_tts as tts_module  # Rename to avoid shadowing
    import edge_tts.communicate as tts_comm
    from edge_tts.data_classes import TTSConfig
    from edge_tts.exceptions import NoAudioReceived, UnexpectedResponse
    
    # Create filename (cache-aware)
    if cache_key:
        fname = f"speech_{cache_key}.mp3"
    else:
        unique_id = hashlib.md5(f"{text}{voice}{time.time()}".encode()).hexdigest()[:10]
        fname = f"speech_{unique_id}.mp3"
    output_file = OUTPUT_DIR / fname

    if cache_key and output_file.exists():
        return output_file

    if is_full_ssml:
        # Full SSML with <speak> wrapper (multi-voice) - need full passthrough
        def mkssml_passthrough(tc, escaped_text, style=None, role=None, style_degree=None):
            if isinstance(escaped_text, bytes):
                escaped_text = escaped_text.decode("utf-8")
            return escaped_text
        
        # Replace mkssml and escape temporarily
        original_mkssml = tts_comm.mkssml
        original_escape = tts_comm.escape
        tts_comm.mkssml = mkssml_passthrough
        tts_comm.escape = lambda x: x  # Don't escape SSML tags
        
        try:
            communicate = tts_module.Communicate(
                text=text,
                voice=voice,
                rate="+0%",
                volume="+0%",
                pitch="+0Hz",
                receive_timeout=600  # 10 minutes for long-form content
            )
            print(f"[TTS] Generating speech (full SSML): text_length={len(text)}, voice={voice}")
            try:
                await communicate.save(str(output_file))
                print(f"[TTS] Success: {output_file.name}, size={output_file.stat().st_size} bytes")
            except Exception as e:
                print(f"[TTS ERROR] Failed: {type(e).__name__}: {str(e)}")
                import traceback
                traceback.print_exc()
                raise
        finally:
            # Restore originals
            tts_comm.mkssml = original_mkssml
            tts_comm.escape = original_escape
    elif is_ssml:
        # Inner SSML tags (like mstts:express-as, prosody, break) 
        # Must bypass escape() to prevent double-escaping of SSML tags
        original_escape = tts_comm.escape
        tts_comm.escape = lambda x: x  # Don't escape - text already has SSML tags
        
        try:
            # Check if style parameter is supported
            import inspect
            communicate_sig = inspect.signature(tts_module.Communicate.__init__)
            supports_style = 'style' in communicate_sig.parameters
            
            if supports_style and (style is not None or style_degree is not None):
                communicate = tts_module.Communicate(
                    text=text,
                    voice=voice,
                    rate=rate or "+0%",
                    volume=volume or "+0%",
                    pitch=pitch or "+0Hz",
                    style=style,
                    style_degree=style_degree,
                    receive_timeout=600  # 10 minutes for long-form content
                )
            else:
                communicate = tts_module.Communicate(
                    text=text,
                    voice=voice,
                    rate=rate or "+0%",
                    volume=volume or "+0%",
                    pitch=pitch or "+0Hz",
                    receive_timeout=600  # 10 minutes for long-form content
                )
            print(f"[TTS] Generating speech (SSML): text_length={len(text)}, voice={voice}, style={style}")
            try:
                await communicate.save(str(output_file))
                print(f"[TTS] Success: {output_file.name}, size={output_file.stat().st_size} bytes")
            except Exception as e:
                print(f"[TTS ERROR] Failed: {type(e).__name__}: {str(e)}")
                import traceback
                traceback.print_exc()
                raise
        finally:
            tts_comm.escape = original_escape
    else:
        # Regular text-to-speech (non-SSML)
        # Check if style parameter is supported
        import inspect
        communicate_sig = inspect.signature(tts_module.Communicate.__init__)
        supports_style = 'style' in communicate_sig.parameters
        
        if supports_style and (style is not None or style_degree is not None):
            communicate = tts_module.Communicate(
                text=text,
                voice=voice,
                rate=rate or "+0%",
                volume=volume or "+0%",
                pitch=pitch or "+0Hz",
                style=style,
                style_degree=style_degree,
                receive_timeout=600  # 10 minutes for long-form content
            )
        else:
            communicate = tts_module.Communicate(
                text=text,
                voice=voice,
                rate=rate or "+0%",
                volume=volume or "+0%",
                pitch=pitch or "+0Hz",
                receive_timeout=600  # 10 minutes for long-form content
            )
        print(f"[TTS] Generating speech (regular): text_length={len(text)}, voice={voice}, style={style}")
        try:
            await communicate.save(str(output_file))
            print(f"[TTS] Success: {output_file.name}, size={output_file.stat().st_size} bytes")
        except (NoAudioReceived, UnexpectedResponse) as e:
            # If style triggers a rejection, retry once without style to avoid 500s
            if style is not None or style_degree is not None:
                print(f"[STYLE FALLBACK] Retrying without style due to: {e}")
                communicate = tts_module.Communicate(
                    text=text,
                    voice=voice,
                    rate=rate or "+0%",
                    volume=volume or "+0%",
                    pitch=pitch or "+0Hz",
                    receive_timeout=600  # 10 minutes for long-form content
                )
                await communicate.save(str(output_file))
                print(f"[TTS] Fallback success: {output_file.name}, size={output_file.stat().st_size} bytes")
            else:
                print(f"[TTS ERROR] Failed: {type(e).__name__}: {str(e)}")
                import traceback
                traceback.print_exc()
                raise

    return output_file


def enforce_chunk_limits(chunks, max_chars=MAX_CHARS_PER_CHUNK):
    """Split any incoming chunk that is too long to keep each TTS call under the limit."""
    normalized = []
    for chunk in chunks or []:
        content = str(chunk.get('content', '') or '').strip()
        if not content:
            continue
        if len(content) <= max_chars:
            normalized.append(chunk)
            continue
        # Further split oversized chunks while preserving metadata
        sub_chunks = process_text(content, max_chars=max_chars)
        for sub in sub_chunks:
            merged = dict(chunk)  # start with original metadata
            merged['content'] = sub.get('content', '')
            for key in ('voice', 'emotion', 'intensity', 'pitch', 'speed', 'rate', 'volume'):
                if sub.get(key) is not None:
                    merged[key] = sub.get(key)
            normalized.append(merged)
    return normalized


def sanitize_chunks_with_styles(chunks, default_voice, voice_map):
    """Ensure voice defaults are set and strip unsupported styles, returning chunks + warnings."""
    sanitized = []
    style_warnings = []
    for idx, chunk in enumerate(chunks or []):
        chunk_copy = dict(chunk)
        chunk_voice = chunk_copy.get('voice') or default_voice
        chunk_copy['voice'] = chunk_voice

        emotion = chunk_copy.get('emotion')
        supported_styles = voice_map.get(chunk_voice, set())
        if emotion and supported_styles and emotion not in supported_styles:
            style_warnings.append(
                f"chunk {idx}: emotion '{emotion}' not supported by {chunk_voice}, removed"
            )
            chunk_copy['emotion'] = None

        sanitized.append(chunk_copy)
    return sanitized, style_warnings


def merge_audio_files(file_paths, job_label="speech"):
    """Concatenate mp3 parts in order without re-encoding."""
    if not file_paths:
        raise ValueError("No audio parts to merge")
    paths = [Path(p) for p in file_paths]
    if len(paths) == 1:
        return paths[0]

    unique_id = hashlib.md5("|".join(str(p) for p in paths).encode()).hexdigest()[:10]
    output_file = OUTPUT_DIR / f"{job_label}_{unique_id}.mp3"
    with open(output_file, "wb") as dest:
        for path in paths:
            with open(path, "rb") as src:
                dest.write(src.read())
    return output_file


def synthesize_and_merge_chunks(chunks, voice, auto_pauses, auto_emphasis, auto_breaths, global_controls, job_label="speech"):
    """Render chunks in batches then merge to avoid per-request limits.
    
    Batching strategy:
    - Group chunks into batches where total chars per batch < MAX_BATCH_CHARS
    - Generate audio for each batch separately
    - Merge all batch audio files together
    """
    MAX_BATCH_CHARS = 2500  # Conservative limit per batch to stay under API constraints
    MAX_CHUNKS_PER_BATCH = 5  # Also limit number of chunks per batch
    
    # Group chunks into batches
    batches = []
    current_batch = []
    current_batch_chars = 0
    
    for chunk in chunks:
        chunk_content = str(chunk.get('content', '') or '')
        chunk_len = len(chunk_content)
        
        # Check if adding this chunk would exceed limits
        would_exceed_chars = (current_batch_chars + chunk_len) > MAX_BATCH_CHARS
        would_exceed_count = len(current_batch) >= MAX_CHUNKS_PER_BATCH
        
        if current_batch and (would_exceed_chars or would_exceed_count):
            # Start new batch
            batches.append(current_batch)
            current_batch = [chunk]
            current_batch_chars = chunk_len
        else:
            # Add to current batch
            current_batch.append(chunk)
            current_batch_chars += chunk_len
    
    # Don't forget the last batch
    if current_batch:
        batches.append(current_batch)
    
    print(f"[BATCH] Processing {len(chunks)} chunks in {len(batches)} batches")
    
    # Process each batch
    all_part_files = []
    all_warnings = []
    all_chunk_map = []
    all_ssml_preview = []
    
    for batch_idx, batch_chunks in enumerate(batches):
        batch_char_count = sum(len(str(c.get('content', '') or '')) for c in batch_chunks)
        print(f"[BATCH {batch_idx + 1}/{len(batches)}] Processing {len(batch_chunks)} chunks ({batch_char_count} chars)")
        
        # Process each chunk in this batch
        for chunk in batch_chunks:
            ssml_result = build_ssml(
                voice=chunk.get('voice') or voice,
                chunks=[chunk],
                auto_pauses=auto_pauses,
                auto_emphasis=auto_emphasis,
                auto_breaths=auto_breaths,
                global_rate=global_controls.get('rate'),
                global_pitch=global_controls.get('pitch'),
                global_volume=global_controls.get('volume'),
            )
            ssml_text = ssml_result['ssml']
            all_ssml_preview.append(ssml_text)
            chunk_voice = ssml_result.get('chunk_map', [{}])[0].get('voice', chunk.get('voice') or voice)
            cache_key = hashlib.md5(f"{chunk_voice}:{ssml_text}".encode()).hexdigest()[:16]

            output_file = run_async(
                generate_speech(
                    ssml_text,
                    chunk_voice,
                    rate=None,
                    volume=None,
                    pitch=None,
                    is_ssml=True,
                    cache_key=cache_key,
                    is_full_ssml=ssml_result.get('is_full_ssml', False)
                )
            )
            all_part_files.append(output_file)
            all_warnings.extend(ssml_result.get('warnings', []))
            all_chunk_map.extend(ssml_result.get('chunk_map', []))
    
    print(f"[BATCH] Generated {len(all_part_files)} audio parts, merging...")
    merged_file = merge_audio_files(all_part_files, job_label=job_label)
    print(f"[BATCH] Merge complete: {merged_file.name}")
    
    return merged_file, all_warnings, all_chunk_map, "".join(all_ssml_preview)


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
    plan = request.args.get('plan', '')  # 'lifetime' or empty for web plans
    next_url = request.args.get('next', '')  # Where to redirect after signup
    api_plan = request.args.get('api_plan', '')  # For API plan signups
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        plan = request.form.get('plan', '')
        next_url = request.form.get('next', '')
        api_plan = request.form.get('api_plan', '')
        
        if not email or not password:
            flash('Email and password are required.', 'error')
            return redirect(url_for('signup', plan=plan, next=next_url, api_plan=api_plan))
        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'error')
            return redirect(url_for('signup', plan=plan, next=next_url, api_plan=api_plan))
        
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash('Welcome! Your account has been created.', 'success')
        
        # Handle redirects based on signup source
        if next_url:
            # Redirect back to where they came from (e.g., API pricing)
            return redirect(next_url)
        elif plan:
            # Web plan signup - go to subscribe with plan
            return redirect(url_for('subscribe', plan=plan))
        else:
            # Default - go to subscribe page
            return redirect(url_for('subscribe'))
    
    return render_template('signup.html', plan=plan, next=next_url, api_plan=api_plan)


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


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if email:
            user = User.query.filter_by(email=email).first()
            if user:
                raw_token = create_reset_token(user)
                reset_link = url_for('reset_password', token=raw_token, _external=True)
                send_password_reset_email(user.email, reset_link)
        flash('If that email is registered, a reset link is on the way.', 'success')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    token_record = verify_reset_token(token)
    if not token_record:
        flash('That reset link is invalid or has expired. Please request a new one.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not password or len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return redirect(url_for('reset_password', token=token))
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('reset_password', token=token))

        token_record.user.set_password(password)
        token_record.used_at = datetime.utcnow()
        PasswordResetToken.query.filter(
            PasswordResetToken.user_id == token_record.user_id,
            PasswordResetToken.token_hash != token_record.token_hash,
        ).delete()
        db.session.commit()

        flash('Your password has been updated. Please sign in.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html', token=token)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Signed out.', 'success')
    return redirect(url_for('login'))


def subscription_required(func):
    """Decorator to require active web subscription (TTS tool access)"""
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


def api_access_required(func):
    """Decorator to require API access (separate from web subscription)"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # If billing is disabled, allow access without API subscription
        if not billing_enabled():
            return func(*args, **kwargs)
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if not current_user.has_api_access:
            flash('API access required. Please subscribe to an API plan.', 'error')
            return redirect(url_for('api_pricing'))
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


@app.route('/api/presets', methods=['GET'])
def api_presets():
    """Return curated hero voice presets"""
    return jsonify({"success": True, "presets": HERO_PRESETS})


# -------- API Pricing --------

@app.route('/api-pricing')
def api_pricing():
    """Show API pricing page"""
    return render_template('api_pricing.html')


# -------- Stripe billing --------

@app.route('/subscribe')
@login_required
def subscribe():
    """Show the subscription options page with both Monthly and Lifetime plans"""
    # If already subscribed, redirect to dashboard
    if current_user.is_subscribed:
        flash('You already have an active subscription!', 'info')
        return redirect(url_for('index'))
    
    # Just render the template - let the user choose their plan
    # The template has JS that calls /create-checkout-session with the plan_type
    return render_template('subscribe.html')


@app.route('/create-checkout-session', methods=['POST'])
@login_required
@csrf.exempt  # Exempting because this is an API endpoint called from JS
def create_checkout_session():
    # Support both query args and JSON body
    data = request.get_json() or {}
    plan_type = data.get('plan_type') or request.args.get('plan', 'monthly')
    
    app.logger.info(f"Creating checkout session for plan_type: {plan_type}")
    
    # Determine price ID and mode based on plan type
    if plan_type == 'lifetime':
        if not stripe.api_key:
            return jsonify({'error': 'Stripe not configured'}), 500
        price_id = STRIPE_LIFETIME_PRICE_ID
        mode = 'payment'  # One-time payment
        app.logger.info(f"Using LIFETIME price_id: {price_id}")
    elif plan_type == 'api_starter':
        if not stripe.api_key:
            return jsonify({'error': 'Stripe not configured'}), 500
        price_id = STRIPE_API_STARTER_PRICE_ID
        mode = 'subscription'
        app.logger.info(f"Using API_STARTER price_id: {price_id}")
    elif plan_type == 'api_pro':
        if not stripe.api_key:
            return jsonify({'error': 'Stripe not configured'}), 500
        price_id = STRIPE_API_PRO_PRICE_ID
        mode = 'subscription'
        app.logger.info(f"Using API_PRO price_id: {price_id}")
    else:  # monthly web subscription
        if not stripe.api_key or not STRIPE_PRICE_ID:
            return jsonify({'error': 'Stripe not configured'}), 500
        price_id = STRIPE_PRICE_ID
        mode = 'subscription'
        app.logger.info(f"Using MONTHLY price_id: {price_id}")

    try:
        success_url = url_for('subscription_success', _external=True) + f'?session_id={{CHECKOUT_SESSION_ID}}&plan_type={plan_type}'
        cancel_url = url_for('subscription_cancel', _external=True)

        # For one-time payments (lifetime), don't attach to existing customer
        # to avoid Stripe showing "manage subscription" instead of new purchase
        if mode == 'payment':
            # One-time payment - create fresh checkout without existing customer
            session = stripe.checkout.Session.create(
                mode=mode,
                line_items=[{'price': price_id, 'quantity': 1}],
                success_url=success_url,
                cancel_url=cancel_url,
                customer_email=current_user.email,
                automatic_tax={'enabled': True},
            )
        else:
            # Subscription - can use existing customer if they have one
            customer = current_user.stripe_customer_id if current_user.stripe_customer_id else None
            session = stripe.checkout.Session.create(
                mode=mode,
                line_items=[{'price': price_id, 'quantity': 1}],
                success_url=success_url,
                cancel_url=cancel_url,
                customer=customer,
                customer_email=(None if customer else current_user.email),
                automatic_tax={'enabled': True},
            )

        app.logger.info(f"Checkout session created: {session.id}, URL: {session.url}")
        return jsonify({'url': session.url})
    except Exception as e:
        app.logger.error(f"Checkout session error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/subscription/success')
@login_required
def subscription_success():
    session_id = request.args.get('session_id')
    plan_type = request.args.get('plan_type', 'monthly')
    
    if stripe.api_key and session_id:
        try:
            cs = stripe.checkout.Session.retrieve(session_id)
            if cs.get('customer') and not current_user.stripe_customer_id:
                current_user.stripe_customer_id = cs['customer']
                db.session.commit()
            
            # Handle different plan types
            if plan_type == 'lifetime':
                current_user.is_lifetime = True
                current_user.subscription_status = 'lifetime'
                db.session.commit()
                flash('Lifetime access activated. Enjoy forever!', 'success')
                return redirect(url_for('index'))
            elif plan_type.startswith('api_'):
                # API plan purchase
                tier = plan_type.replace('api_', '')  # 'starter' or 'pro'
                current_user.api_tier = tier
                current_user.api_chars_used = 0  # Reset usage
                current_user.api_usage_reset_at = datetime.utcnow() + timedelta(days=30)
                db.session.commit()
                flash(f'API {tier.title()} plan activated! Create your first API key below.', 'success')
                return redirect(url_for('api_keys_page'))  # Redirect to API keys page
            else:
                # Regular monthly subscription
                current_user.subscription_status = 'active'
                db.session.commit()
                flash('Subscription activated. Enjoy!', 'success')
                return redirect(url_for('index'))
        except Exception as e:
            app.logger.error(f"Subscription success error: {e}")
            flash('Payment received! Your access should be active shortly.', 'success')
    else:
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
        is_ssml = bool(data.get('is_ssml'))
        chunk = data.get('chunk')  # optional chunk preview payload
        
        # Ensure proper formatting for rate, volume, and pitch
        if not rate.startswith(('+', '-')):
            rate = '+' + rate
        if not volume.startswith(('+', '-')):
            volume = '+' + volume
        if not pitch.startswith(('+', '-')):
            pitch = '+' + pitch
        
        if not text and not chunk:
            return jsonify({'success': False, 'error': 'No text provided'}), 400
        
        # Enforce 150 character limit for preview (count only actual text, not SSML markup)
        char_count = 0
        ssml_text = None
        warnings_out = []
        if chunk:
            # Build SSML for single chunk
            if not isinstance(chunk, dict) or not chunk.get('content'):
                return jsonify({'success': False, 'error': 'chunk must include content'}), 400
            char_count = len(chunk.get('content', ''))
            try:
                voices = run_async(get_voices())
                allowed_styles = []
                for v in voices:
                    if v.get('ShortName') == voice:
                        allowed_styles = v.get('StyleList') or []
                        break
            except Exception:
                allowed_styles = []
            if chunk.get('emotion') and allowed_styles and chunk['emotion'] not in allowed_styles:
                chunk['emotion'] = None
                warnings_out.append(f"emotion not supported by {voice}, removed")
            ssml_result = build_ssml(
                voice=voice,
                chunks=[chunk],
                auto_pauses=data.get('auto_pauses', True),
                auto_emphasis=data.get('auto_emphasis', True),
                auto_breaths=data.get('auto_breaths', False),
                global_rate=data.get('global_rate'),
                global_pitch=data.get('global_pitch'),
                global_volume=data.get('global_volume'),
            )
            ssml_text = ssml_result['ssml']
            warnings_out = ssml_result['warnings']
            is_ssml = True
        else:
            if is_ssml:
                import re
                text_only = re.sub(r'<[^>]+>', '', text)
                char_count = len(text_only)
            else:
                char_count = len(text)
                ssml_text = text
        
        limit = 220 if chunk else 150
        if char_count > limit:
            return jsonify({
                'success': False, 
                'error': f'Preview limited to {limit} characters. You entered {char_count}. Sign up for unlimited!'
            }), 400
        
        # Generate speech
        try:
            if ssml_text and is_ssml:
                cache_key = hashlib.md5(f"preview:{voice}:{ssml_text}".encode()).hexdigest()[:16]
                output_file = run_async(generate_speech(ssml_text, voice, None, None, None, is_ssml=True, cache_key=cache_key))
            elif is_ssml:
                output_file = run_async(generate_speech(text, voice, rate, volume, pitch, is_ssml=True))
            else:
                output_file = run_async(generate_speech(text, voice, rate, volume, pitch))
        except Exception as gen_error:
            return jsonify({'success': False, 'error': f'Speech generation failed: {str(gen_error)}'}), 500
        
        return jsonify({
            'success': True,
            'audioUrl': f'/api/audio/{output_file.name}',
            'warnings': warnings_out
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
        raw_text = data.get('text', '') or ''
        text = raw_text.strip()
        voice = data.get('voice', 'en-US-EmmaMultilingualNeural')
        is_ssml = bool(data.get('is_ssml')) or raw_text.strip().lower().startswith('<speak')
        chunks = data.get('chunks')

        # Auto flags / global controls for SSML builder
        auto_pauses = data.get('auto_pauses', True)
        auto_emphasis = data.get('auto_emphasis', True)
        auto_breaths = data.get('auto_breaths', False)
        global_controls = data.get('global_controls', {}) or {}

        # Legacy params for plain text mode
        rate = data.get('rate', '+0%')
        volume = data.get('volume', '+0%')
        pitch = data.get('pitch', '+0Hz')

        # Ensure proper formatting for rate, volume, and pitch (legacy path)
        if not rate.startswith(('+', '-')):
            rate = '+' + rate
        if not volume.startswith(('+', '-')):
            volume = '+' + volume
        if not pitch.startswith(('+', '-')):
            pitch = '+' + pitch

        # --- Chunked SSML path ---
        if chunks is not None:
            if not isinstance(chunks, list) or not chunks:
                return jsonify({'success': False, 'error': 'chunks must be a non-empty list'}), 400

            normalized_chunks = enforce_chunk_limits(chunks, max_chars=MAX_CHARS_PER_CHUNK)
            if not normalized_chunks:
                return jsonify({'success': False, 'error': 'No valid chunk content provided'}), 400

            try:
                voices = run_async(get_voices())
                voice_map = {
                    v.get('ShortName'): set(v.get('StyleList') or []) for v in voices
                }
            except Exception as e:
                print(f"[STYLE VALIDATION ERROR] failed to load voices: {e}")
                voice_map = {}

            sanitized_chunks, style_warnings = sanitize_chunks_with_styles(normalized_chunks, voice, voice_map)

            # If we have exactly one chunk with an emotion that matches the global voice, use native style param
            is_single_emotion = (
                len(sanitized_chunks) == 1
                and sanitized_chunks[0].get('emotion')
                and sanitized_chunks[0].get('voice') == voice
            )

            if is_single_emotion:
                import inspect
                import edge_tts as tts_module
                communicate_sig = inspect.signature(tts_module.Communicate.__init__)
                supports_style = 'style' in communicate_sig.parameters

                if supports_style:
                    chunk = sanitized_chunks[0]
                    emotion = chunk.get('emotion')
                    # If voice_map is populated and emotion is unsupported, fail fast
                    supported_styles = voice_map.get(voice, set())
                    if supported_styles and emotion not in supported_styles:
                        return jsonify({
                            'success': False,
                            'error': f"Style '{emotion}' is not supported by voice {voice}. Supported styles: {sorted(supported_styles) if supported_styles else 'none'}"
                        }), 400

                    plain_text = chunk.get('content', '')
                    intensity = chunk.get('intensity', 2)
                    style_degree = {1: 0.7, 2: 1.0, 3: 1.3}.get(intensity, 1.0)

                    chunk_rate = chunk.get('speed', chunk.get('rate', global_controls.get('rate', 0)))
                    chunk_pitch = chunk.get('pitch', global_controls.get('pitch', 0))
                    chunk_volume = chunk.get('volume', global_controls.get('volume', 0))

                    cache_key = hashlib.md5(f"{voice}:{plain_text}:{emotion}:{style_degree}:{chunk_rate}:{chunk_pitch}:{chunk_volume}".encode()).hexdigest()[:16]

                    output_file = run_async(
                        generate_speech(
                            plain_text,
                            voice,
                            rate=chunk_rate,
                            volume=chunk_volume,
                            pitch=chunk_pitch,
                            is_ssml=False,
                            cache_key=cache_key,
                            style=emotion,
                            style_degree=style_degree
                        )
                    )

                    return jsonify({
                        'success': True,
                        'audioUrl': f'/api/audio/{output_file.name}',
                        'warnings': style_warnings,
                        'chunk_map': [{
                            'content': plain_text,
                            'voice': voice,
                            'emotion': emotion,
                            'intensity': intensity,
                            'rate': chunk_rate,
                            'pitch': chunk_pitch,
                            'volume': chunk_volume,
                        }],
                        'ssml_used': plain_text,  # For compatibility in tests/logs
                    })

            # Multi-chunk or multi-voice path: render and merge parts
            merged_file, chunk_warnings, chunk_map_out, ssml_preview = synthesize_and_merge_chunks(
                sanitized_chunks,
                voice,
                auto_pauses,
                auto_emphasis,
                auto_breaths,
                global_controls,
                job_label="speech"
            )
            return jsonify({
                'success': True,
                'audioUrl': f'/api/audio/{merged_file.name}',
                'ssml_used': ssml_preview,
                'chunk_map': chunk_map_out,
                'warnings': (style_warnings + chunk_warnings),
            })

        # --- Auto-chunk path when plain text provided ---
        if text and data.get('auto_chunk', True) and not is_ssml:
            chunk_map = process_text(text, max_chars=MAX_CHARS_PER_CHUNK)
            try:
                voices = run_async(get_voices())
                allowed_styles = []
                for v in voices:
                    if v.get('ShortName') == voice:
                        allowed_styles = v.get('StyleList') or []
                        break
            except Exception:
                allowed_styles = []
            style_warnings = []
            sanitized_chunks = []
            for idx, chunk in enumerate(chunk_map):
                chunk_copy = dict(chunk)
                emotion = chunk_copy.get('emotion')
                if emotion and allowed_styles and emotion not in allowed_styles:
                    style_warnings.append(f"chunk {idx}: emotion '{emotion}' not supported by {voice}, removed")
                    chunk_copy['emotion'] = None
                sanitized_chunks.append(chunk_copy)

            if not sanitized_chunks:
                return jsonify({'success': False, 'error': 'No text provided after chunking'}), 400

            merged_file, chunk_warnings, chunk_map_out, ssml_preview = synthesize_and_merge_chunks(
                sanitized_chunks,
                voice,
                auto_pauses,
                auto_emphasis,
                auto_breaths,
                global_controls,
                job_label="speech"
            )
            return jsonify({
                'success': True,
                'audioUrl': f'/api/audio/{merged_file.name}',
                'ssml_used': ssml_preview,
                'chunk_map': chunk_map_out,
                'warnings': (style_warnings + chunk_warnings),
            })

        # --- Legacy plain text / direct SSML path ---
        if not text:
            return jsonify({'success': False, 'error': 'No text provided'}), 400

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


@app.route('/api/pro/generate', methods=['POST'])
@login_required
@subscription_required
@csrf.exempt
def api_generate_pro():
    """
    Placeholder for Pro Engine (e.g., CosyVoice-2 CPU).
    Currently not enabled; returns a clear message.
    """
    return jsonify({
        'success': False,
        'error': 'Pro engine not enabled yet. This endpoint is reserved for CosyVoice-2 CPU mode.'
    }), 501


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
            return render_template('embed_error.html', 
                error_message="Invalid API key. Please check your key and try again.",
                help_link="/api-keys"), 401
    else:
        return render_template('embed_error.html',
            error_message="API key required to use the widget.",
            help_link="/api-keys"), 401
    
    return render_template('embed.html', api_key=api_key)


@app.route('/widget')
def public_widget():
    """Public demo widget - no authentication required"""
    return render_template('widget_public.html')


@app.route('/api/widget/generate', methods=['POST'])
@csrf.exempt
def widget_generate():
    """Public endpoint for widget - no authentication required"""
    import traceback
    
    try:
        print(f"[WIDGET] Received request from {request.remote_addr}")
        print(f"[WIDGET] Content-Type: {request.content_type}")
        
        data = request.get_json(silent=True) or {}
        print(f"[WIDGET] Parsed JSON data: {data}")
        voice = data.get('voice', 'en-US-AriaNeural')
        chunks = data.get('chunks')
        auto_pauses = data.get('auto_pauses', True)
        auto_emphasis = data.get('auto_emphasis', False)
        auto_breaths = data.get('auto_breaths', False)
        global_controls = data.get('global_controls', {}) or {}
        
        if not chunks or not isinstance(chunks, list):
            return jsonify({'success': False, 'error': 'chunks required'}), 400

        normalized_chunks = enforce_chunk_limits(chunks, max_chars=MAX_CHARS_PER_CHUNK)
        if not normalized_chunks:
            return jsonify({'success': False, 'error': 'No chunk content provided'}), 400

        try:
            voices = run_async(get_voices())
            voice_map = {
                v.get('ShortName'): set(v.get('StyleList') or []) for v in voices
            }
        except Exception as e:
            print(f"[STYLE VALIDATION ERROR] failed to load voices: {e}")
            voice_map = {}

        sanitized_chunks, style_warnings = sanitize_chunks_with_styles(normalized_chunks, voice, voice_map)

        is_single_emotion = (
            len(sanitized_chunks) == 1
            and sanitized_chunks[0].get('emotion')
        )

        if is_single_emotion:
            import inspect
            import edge_tts as tts_module
            communicate_sig = inspect.signature(tts_module.Communicate.__init__)
            supports_style = 'style' in communicate_sig.parameters

            if supports_style:
                chunk = sanitized_chunks[0]
                chunk_voice = chunk.get('voice') or voice
                emotion = chunk.get('emotion')

                supported_styles = voice_map.get(chunk_voice, set())
                if supported_styles and emotion not in supported_styles:
                    return jsonify({
                        'success': False,
                        'error': f"Style '{emotion}' not supported by {chunk_voice}. Supported: {sorted(supported_styles) if supported_styles else 'none'}"
                    }), 400

                plain_text = chunk.get('content', '')
                intensity = chunk.get('intensity', 2)
                style_degree = {1: 0.7, 2: 1.0, 3: 1.3}.get(intensity, 1.0)

                chunk_rate = chunk.get('speed', chunk.get('rate', global_controls.get('rate', 0)))
                chunk_pitch = chunk.get('pitch', global_controls.get('pitch', 0))
                chunk_volume = chunk.get('volume', global_controls.get('volume', 0))

                cache_key = hashlib.md5(f"{chunk_voice}:{plain_text}:{emotion}:{style_degree}:{chunk_rate}:{chunk_pitch}:{chunk_volume}".encode()).hexdigest()[:16]

                output_file = run_async(
                    generate_speech(
                        plain_text,
                        chunk_voice,
                        rate=chunk_rate,
                        volume=chunk_volume,
                        pitch=chunk_pitch,
                        is_ssml=False,
                        cache_key=cache_key,
                        style=emotion,
                        style_degree=style_degree
                    )
                )

                return jsonify({
                    'success': True,
                    'audioUrl': f'/api/audio/{output_file.name}',
                    'warnings': style_warnings
                })

        merged_file, chunk_warnings, _, _ = synthesize_and_merge_chunks(
            sanitized_chunks,
            voice,
            auto_pauses,
            auto_emphasis,
            auto_breaths,
            global_controls,
            job_label="widget"
        )

        return jsonify({
            'success': True,
            'audioUrl': f'/api/audio/{merged_file.name}',
            'warnings': (style_warnings + chunk_warnings)
        })
        
    except Exception as e:
        print(f"[WIDGET ERROR] Exception type: {type(e).__name__}")
        print(f"[WIDGET ERROR] Exception message: {str(e)}")
        print(f"[WIDGET ERROR] Full traceback:")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api-keys')
@login_required
@api_access_required
def api_keys_page():
    """Show user's API keys"""
    return render_template('api_keys.html', keys=current_user.api_keys)


@app.route('/api/keys/create', methods=['POST'])
@login_required
@api_access_required
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
@api_access_required
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
@api_access_required
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

def verify_api_key(api_key_string, char_count=0):
    """Verify API key and return user if valid. Optionally check usage limits."""
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
    
    # Check if user has API access (separate from web subscription)
    if billing_enabled() and not api_key.user.has_api_access:
        db.session.commit()
        return {'valid': False, 'error': 'API access required. Please subscribe to an API plan at cheaptts.com/api-pricing'}
    
    # Check usage limits if char_count provided
    if char_count > 0 and billing_enabled():
        user = api_key.user
        user.check_and_reset_api_usage()  # Reset if new billing period
        
        if user.api_chars_remaining < char_count:
            db.session.commit()
            return {
                'valid': False, 
                'error': f'API usage limit exceeded. You have {user.api_chars_remaining:,} characters remaining this month. Upgrade your plan at cheaptts.com/api-pricing',
                'usage': {
                    'used': user.api_chars_used,
                    'limit': user.api_char_limit,
                    'remaining': user.api_chars_remaining,
                    'tier': user.api_tier
                }
            }
    
    db.session.commit()
    return {'valid': True, 'is_admin': False, 'user': api_key.user, 'api_key': api_key}


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
    import traceback
    import re
    
    # Get API key from header
    api_key_str = (request.headers.get('X-API-Key') or '').strip()
    if not api_key_str:
        return jsonify({'success': False, 'error': 'API key required. Provide X-API-Key header.'}), 401
    
    try:
        data = request.get_json(silent=True) or {}
        raw_text = data.get('text', '')
        text = raw_text.strip()
        chunks = data.get('chunks')
        
        # Calculate total character count for usage tracking
        total_chars = 0
        if chunks:
            for chunk in chunks:
                content = chunk.get('content', '')
                # Strip SSML tags for accurate char count
                plain_text = re.sub(r'<[^>]+>', '', content)
                total_chars += len(plain_text)
        elif text:
            # Strip SSML tags for accurate char count
            plain_text = re.sub(r'<[^>]+>', '', text)
            total_chars = len(plain_text)
        
        # Verify API key WITH usage check
        auth_result = verify_api_key(api_key_str, char_count=total_chars)
        if not auth_result.get('valid'):
            error_response = {'success': False, 'error': auth_result.get('error', 'Invalid API key')}
            if auth_result.get('usage'):
                error_response['usage'] = auth_result['usage']
            return jsonify(error_response), 401 if 'API access required' in auth_result.get('error', '') else 429
        
        # Track usage for non-admin users
        is_admin = auth_result.get('is_admin', False)
        user = auth_result.get('user')
        
        print(f"[API V1] Received request from {request.remote_addr}")
        print(f"[API V1] Content-Type: {request.content_type}")
        print(f"[API V1] Characters: {total_chars}, Admin: {is_admin}")
        
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
        
        # --- Chunked SSML path (multi-speaker dialogue) ---
        if chunks is not None:
            if not isinstance(chunks, list) or not chunks:
                return jsonify({'success': False, 'error': 'chunks must be a non-empty list'}), 400

            # Check if client sent single-voice with emotion BEFORE processing
            is_client_single_voice_emotion = (
                len(chunks) == 1
                and chunks[0].get('emotion')
                and (not chunks[0].get('voice') or chunks[0].get('voice') == voice)  # No voice override or matches global
            )

            # If client sent single chunk with emotion, validate and use native style parameter
            if is_client_single_voice_emotion:
                import inspect
                import edge_tts as tts_module
                communicate_sig = inspect.signature(tts_module.Communicate.__init__)
                supports_style = 'style' in communicate_sig.parameters
                
                if supports_style:
                    chunk = chunks[0]
                    emotion = chunk.get('emotion')
                    
                    # Validate emotion against voice's StyleList
                    try:
                        voices = run_async(get_voices())
                        voice_obj = next((v for v in voices if v.get('ShortName') == voice), None)
                        supported_styles = set(voice_obj.get('StyleList', []) if voice_obj else [])
                        
                        if emotion and emotion not in supported_styles:
                            # Style not supported - return clear error
                            return jsonify({
                                'success': False,
                                'error': f"Style '{emotion}' is not supported by voice {voice}. Supported styles: {sorted(supported_styles) if supported_styles else 'none'}"
                            }), 400
                    except Exception as e:
                        # If validation fails, log but proceed
                        print(f"[VALIDATION ERROR] {e}")
                        pass
                    
                    # Use native style parameter - bypass SSML building
                    plain_text = chunk.get('content', '')
                    intensity = chunk.get('intensity', 2)
                    style_degree = {1: 0.7, 2: 1.0, 3: 1.3}.get(intensity, 1.0)
                    
                    # Use chunk-specific prosody settings if provided
                    chunk_rate = chunk.get('speed', chunk.get('rate', rate))
                    chunk_pitch = chunk.get('pitch', pitch)
                    chunk_volume = chunk.get('volume', volume)
                    
                    cache_key = hashlib.md5(f"{voice}:{plain_text}:{emotion}:{style_degree}:{chunk_rate}:{chunk_pitch}:{chunk_volume}".encode()).hexdigest()[:16]
                    
                    output_file = run_async(
                        generate_speech(
                            plain_text,
                            voice,
                            rate=chunk_rate,
                            volume=chunk_volume,
                            pitch=chunk_pitch,
                            is_ssml=False,
                            cache_key=cache_key,
                            style=emotion,
                            style_degree=style_degree
                        )
                    )
                    
                    audio_url = request.url_root.rstrip('/') + f'/api/audio/{output_file.name}'
                    return jsonify({
                        'success': True,
                        'audio_url': audio_url,
                        'filename': output_file.name
                    })

            # Otherwise, continue with SSML building path
            sanitized_chunks = []
            try:
                voices = run_async(get_voices())
                voice_map = {
                    v.get('ShortName'): set(v.get('StyleList') or []) for v in voices
                }
            except Exception as e:
                print(f"[STYLE VALIDATION ERROR] failed to load voices: {e}")
                voice_map = {}

            for idx, chunk in enumerate(chunks):
                chunk_copy = dict(chunk)
                chunk_voice = chunk_copy.get('voice') or voice
                chunk_copy['voice'] = chunk_voice

                emotion = chunk_copy.get('emotion')
                supported_styles = voice_map.get(chunk_voice, set())
                if emotion and supported_styles and emotion not in supported_styles:
                    chunk_copy['emotion'] = None

                sanitized_chunks.append(chunk_copy)

            ssml_result = build_ssml(
                voice=voice,
                chunks=sanitized_chunks,
                auto_pauses=True,
                auto_emphasis=True,
            )
            ssml_text = ssml_result['ssml']
            is_full_ssml = ssml_result.get('is_full_ssml', False)
            
            # Multi-voice or complex SSML - use SSML building
            primary_voice = sanitized_chunks[0].get('voice') if sanitized_chunks else voice
            cache_key = hashlib.md5(f"{primary_voice}:{ssml_text}".encode()).hexdigest()[:16]

            output_file = run_async(
                generate_speech(
                    ssml_text,
                    primary_voice,
                    rate=None,
                    volume=None,
                    pitch=None,
                    is_ssml=True,
                    cache_key=cache_key,
                    is_full_ssml=is_full_ssml
                )
            )
            
            audio_url = request.url_root.rstrip('/') + f'/api/audio/{output_file.name}'
            
            # Track API usage for non-admin users
            if user and not is_admin and billing_enabled():
                user.use_api_chars(total_chars)
                db.session.commit()
            
            return jsonify({
                'success': True,
                'audio_url': audio_url,
                'filename': output_file.name,
                'chunks_processed': len(sanitized_chunks)
            })
        
        # --- Single voice path ---
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
        
        # Track API usage for non-admin users
        if user and not is_admin and billing_enabled():
            user.use_api_chars(total_chars)
            db.session.commit()
        
        # Return the audio URL
        audio_url = request.url_root.rstrip('/') + f'/api/audio/{output_file.name}'
        
        return jsonify({
            'success': True,
            'audio_url': audio_url,
            'filename': output_file.name
        })
    
    except Exception as e:
        print(f"[API V1 ERROR] Exception type: {type(e).__name__}")
        print(f"[API V1 ERROR] Exception message: {str(e)}")
        print(f"[API V1 ERROR] Full traceback:")
        traceback.print_exc()
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
    """Admin route to grant unlimited access to a user
    
    Query params:
        key: Admin API key (required)
        stripe: 'true' to simulate Stripe customer
        password: Custom password to set
        api_tier: 'starter' | 'pro' | 'enterprise' to grant API access
    """
    # Security check - only accessible with admin password
    admin_pass = request.args.get('key')
    if admin_pass != ADMIN_API_KEY:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        # Check if we should simulate a Stripe customer (for testing billing portal)
        simulate_stripe = request.args.get('stripe', '').lower() == 'true'
        custom_password = request.args.get('password', None)
        api_tier = request.args.get('api_tier', None)  # Grant API access
        
        user = User.query.filter_by(email=email).first()
        if not user:
            # Auto-create the user if they don't exist
            user = User(email=email, subscription_status='active')
            if simulate_stripe:
                # Set a fake Stripe customer ID for testing
                user.stripe_customer_id = 'cus_test_' + email.split('@')[0]
            if api_tier in ('starter', 'pro', 'enterprise'):
                user.api_tier = api_tier
            # Set password
            import secrets
            password = custom_password if custom_password else secrets.token_urlsafe(16)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'message': f'User created and unlimited access granted to {email}' + (' (with Stripe simulation)' if simulate_stripe else '') + (f' (API: {api_tier})' if api_tier else ''),
                'user': {
                    'email': user.email,
                    'password': password if custom_password else 'Random password set - use forgot password to reset',
                    'subscription_status': user.subscription_status,
                    'api_tier': user.api_tier,
                    'stripe_customer_id': user.stripe_customer_id,
                    'created_at': user.created_at.isoformat()
                }
            })
        
        # Grant unlimited access to existing user
        user.subscription_status = 'active'
        if simulate_stripe and not user.stripe_customer_id:
            user.stripe_customer_id = 'cus_test_' + email.split('@')[0]
        if api_tier in ('starter', 'pro', 'enterprise'):
            user.api_tier = api_tier
        if custom_password:
            user.set_password(custom_password)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Unlimited access granted to {email}' + (' (with Stripe simulation)' if simulate_stripe else '') + (f' (API: {api_tier})' if api_tier else ''),
            'user': {
                'email': user.email,
                'password_updated': bool(custom_password),
                'subscription_status': user.subscription_status,
                'api_tier': user.api_tier,
                'stripe_customer_id': user.stripe_customer_id,
                'created_at': user.created_at.isoformat()
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/revoke-legacy-api-keys')
def admin_revoke_legacy_api_keys():
    """
    Revoke all API keys for users who don't have an API plan.
    This handles users who got free API keys with the old $7.99 web-only plan.
    
    Query params:
        key: Admin API key (required)
        dry_run: 'true' to preview without making changes (default: true)
    """
    admin_pass = request.args.get('key')
    if admin_pass != ADMIN_API_KEY:
        return jsonify({'error': 'Unauthorized'}), 403
    
    dry_run = request.args.get('dry_run', 'true').lower() != 'false'
    
    try:
        # Find all users with API keys but no API access
        affected_users = []
        revoked_keys = []
        
        # Get all API keys
        all_keys = APIKey.query.all()
        
        for api_key in all_keys:
            user = api_key.user
            # Check if user does NOT have API access (only has web subscription or nothing)
            if not user.has_api_access:
                affected_users.append({
                    'email': user.email,
                    'subscription_status': user.subscription_status,
                    'api_tier': user.api_tier,
                })
                revoked_keys.append({
                    'key_id': api_key.id,
                    'key_name': api_key.name,
                    'key_prefix': api_key.key[:15] + '...',
                    'user_email': user.email,
                    'was_active': api_key.is_active,
                    'last_used': api_key.last_used_at.isoformat() if api_key.last_used_at else None,
                })
                
                if not dry_run:
                    # Deactivate the key
                    api_key.is_active = False
        
        if not dry_run:
            db.session.commit()
        
        # Get unique affected users
        unique_users = {u['email']: u for u in affected_users}.values()
        
        return jsonify({
            'success': True,
            'dry_run': dry_run,
            'message': f"{'Would revoke' if dry_run else 'Revoked'} {len(revoked_keys)} API keys from {len(list(unique_users))} users without API plans",
            'summary': {
                'total_keys_affected': len(revoked_keys),
                'unique_users_affected': len(list(unique_users)),
            },
            'affected_users': list(unique_users),
            'revoked_keys': revoked_keys,
            'next_step': 'Run with ?dry_run=false to execute' if dry_run else 'Done! Keys have been deactivated.',
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/admin/delete-legacy-api-keys')
def admin_delete_legacy_api_keys():
    """
    Permanently DELETE all API keys for users who don't have an API plan.
    More aggressive than revoke - completely removes the keys.
    
    Query params:
        key: Admin API key (required)
        dry_run: 'true' to preview without making changes (default: true)
    """
    admin_pass = request.args.get('key')
    if admin_pass != ADMIN_API_KEY:
        return jsonify({'error': 'Unauthorized'}), 403
    
    dry_run = request.args.get('dry_run', 'true').lower() != 'false'
    
    try:
        # Find all users with API keys but no API access
        affected_users = []
        deleted_keys = []
        
        # Get all API keys
        all_keys = APIKey.query.all()
        keys_to_delete = []
        
        for api_key in all_keys:
            user = api_key.user
            # Check if user does NOT have API access
            if not user.has_api_access:
                affected_users.append({
                    'email': user.email,
                    'subscription_status': user.subscription_status,
                    'api_tier': user.api_tier,
                })
                deleted_keys.append({
                    'key_id': api_key.id,
                    'key_name': api_key.name,
                    'key_prefix': api_key.key[:15] + '...',
                    'user_email': user.email,
                    'last_used': api_key.last_used_at.isoformat() if api_key.last_used_at else None,
                })
                keys_to_delete.append(api_key)
        
        if not dry_run:
            for key in keys_to_delete:
                db.session.delete(key)
            db.session.commit()
        
        # Get unique affected users
        unique_users = {u['email']: u for u in affected_users}.values()
        
        return jsonify({
            'success': True,
            'dry_run': dry_run,
            'message': f"{'Would delete' if dry_run else 'Deleted'} {len(deleted_keys)} API keys from {len(list(unique_users))} users without API plans",
            'summary': {
                'total_keys_deleted': len(deleted_keys),
                'unique_users_affected': len(list(unique_users)),
            },
            'affected_users': list(unique_users),
            'deleted_keys': deleted_keys,
            'next_step': 'Run with ?dry_run=false to execute' if dry_run else 'Done! Keys have been permanently deleted.',
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
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
