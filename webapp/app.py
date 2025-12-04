"""
Web app for Cheap TTS with auth + Stripe subscriptions
"""
import asyncio
import base64
import hashlib
import os
import secrets

# Import local modified edge_tts first (for emotion support)
import sys
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from pathlib import Path

import requests
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
from flask_cors import CORS
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

webapp_dir = Path(__file__).parent
sys.path.insert(0, str(webapp_dir))  # Ensure local edge_tts is imported first
# Import chunking and SSML modules from same directory
from chunk_processor import process_text
from ssml_builder import build_ssml

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

# Enable CORS for API endpoints (mobile app needs this)
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-API-Key"]
    }
})

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
STRIPE_API_STARTER_PRICE_ID = 'price_1SYThPLz6FHVmZlMFskDh4bS'  # $5/mo API Starter (100k chars)
STRIPE_API_PRO_PRICE_ID = 'price_1SYTheLz6FHVmZlMH2wwGQ6q'  # $19/mo API Pro (500k chars)

# Premium Chatterbox TTS Stripe Price IDs (to be created in Stripe dashboard)
STRIPE_PREMIUM_PRICE_ID = os.environ.get('STRIPE_PREMIUM_PRICE_ID', '')  # $19.99/mo (100K chars)
STRIPE_PREMIUM_PLUS_PRICE_ID = os.environ.get('STRIPE_PREMIUM_PLUS_PRICE_ID', '')  # $29.99/mo (200K chars)
STRIPE_PREMIUM_PRO_PRICE_ID = os.environ.get('STRIPE_PREMIUM_PRO_PRICE_ID', '')  # $39.99/mo (300K chars)

# Chatterbox TTS Configuration (for Ultra Voices premium tier)
# Uses devnen/Chatterbox-TTS-Server as backend
# Can be Vast.ai instance, RunPod Pod URL or any hosted instance
CHATTERBOX_URL = os.environ.get('CHATTERBOX_URL', 'http://localhost:8004')

# IndexTTS2 Configuration (for IndexTTS2 premium tier - separate from Chatterbox)
# High-quality zero-shot TTS with emotion control and voice cloning
# Runs on Vast.ai GPU instance with cached voice embeddings
INDEXTTS_URL = os.environ.get('INDEXTTS_URL', '')

# Podcast TTS Configuration (Premium long-form multi-speaker TTS)
# High-quality long-form TTS (up to 90 minutes, 4 speakers)
# Runs on Vast.ai GPU instance (RTX 3060 12GB or better)
VIBEVOICE_URL = os.environ.get('VIBEVOICE_URL', '')

# All available Chatterbox predefined voices (with .wav extension required by server)
# These are the actual voice names from the Chatterbox server
CHATTERBOX_VOICES = [
    'Emily.wav', 'Michael.wav', 'Olivia.wav', 'Ryan.wav', 'Taylor.wav', 'Thomas.wav',
    'Abigail.wav', 'Adrian.wav', 'Alexander.wav', 'Alice.wav', 'Austin.wav', 'Axel.wav',
    'Connor.wav', 'Cora.wav', 'Elena.wav', 'Eli.wav', 'Everett.wav', 'Gabriel.wav',
    'Gianna.wav', 'Henry.wav', 'Ian.wav', 'Jade.wav', 'Jeremiah.wav', 'Jordan.wav',
    'Julian.wav', 'Layla.wav', 'Leonardo.wav', 'Miles.wav',
    # New voices from IndexTTS collection
    'Adam.wav', 'Grace.wav', 'Hannah.wav', 'Natalie.wav', 'Sophia.wav'
]

# Voice cloning disabled for now - use predefined voices
# Can be re-enabled later with proper reference audio setup
CHATTERBOX_CLONED_VOICES = {}
CLONED_VOICE_LOCAL_FILES = {}

# Predefined speaker voices for multi-speaker dialogue [S1]: [S2]: format
# Maps speaker numbers to distinct Chatterbox voices for variety
CHATTERBOX_SPEAKER_VOICES = {
    '1': 'Emily.wav',      # Female voice
    '2': 'Michael.wav',    # Male voice
    '3': 'Olivia.wav',     # Female voice
    '4': 'Ryan.wav',       # Male voice
    '5': 'Taylor.wav',     # Female voice
    '6': 'Thomas.wav',     # Male voice
    '7': 'Jade.wav',       # Female voice
    '8': 'Alexander.wav',  # Male voice
}

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
    
    # Mobile App Session
    mobile_session_token = db.Column(db.String(255))  # Token for mobile app auth
    mobile_session_expires = db.Column(db.DateTime)  # When mobile session expires
    
    # Character Usage Tracking (Web + Mobile - unified)
    # Free tier: 10,000 chars/month, Paid: unlimited
    chars_used = db.Column(db.Integer, default=0)  # Characters used this billing period
    chars_reset_at = db.Column(db.DateTime)  # When usage resets (monthly)
    
    # Character limit constants
    FREE_CHAR_LIMIT = 10000  # 10k chars/month for free users

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
    
    # --- Web/Mobile Character Usage (10K free, unlimited paid) ---
    
    @property
    def char_limit(self) -> int:
        """Get character limit - 10K for free users, unlimited for subscribers"""
        if self.is_subscribed:
            return 999999999  # Effectively unlimited
        return self.FREE_CHAR_LIMIT
    
    @property
    def chars_remaining(self) -> int:
        """Get remaining characters for this billing period"""
        if self.is_subscribed:
            return 999999999  # Unlimited
        self.check_and_reset_usage()
        return max(0, self.char_limit - (self.chars_used or 0))
    
    def check_and_reset_usage(self):
        """Reset usage if billing period has passed (monthly)"""
        if not self.chars_reset_at:
            # First time - set reset date to 30 days from now
            self.chars_reset_at = datetime.utcnow() + timedelta(days=30)
            self.chars_used = 0
            return
        
        if datetime.utcnow() >= self.chars_reset_at:
            # Reset usage and set new reset date
            self.chars_used = 0
            self.chars_reset_at = datetime.utcnow() + timedelta(days=30)
    
    def use_chars(self, char_count: int) -> tuple:
        """
        Track character usage for web/mobile TTS.
        Returns (success: bool, error_message: str or None)
        
        - Subscribers: Always allowed (unlimited)
        - Free users: 10K chars/month limit
        """
        # Subscribers have unlimited access
        if self.is_subscribed:
            return (True, None)
        
        # Free users - check and reset monthly usage
        self.check_and_reset_usage()
        
        # Check if this request would exceed limit
        current_used = self.chars_used or 0
        if current_used + char_count > self.FREE_CHAR_LIMIT:
            remaining = max(0, self.FREE_CHAR_LIMIT - current_used)
            return (False, f"Character limit reached. You have {remaining:,} of {self.FREE_CHAR_LIMIT:,} characters remaining this month. Upgrade for unlimited access.")
        
        # Track usage
        self.chars_used = current_used + char_count
        return (True, None)
    
    # --- Premium Chatterbox TTS (Premium tier) ---
    # Premium tiers: 'none' | 'premium' (100K) | 'premium_plus' (200K) | 'premium_pro' (300K)
    premium_tier = db.Column(db.String(32), default='none')
    premium_chars_used = db.Column(db.Integer, default=0)
    premium_chars_reset_at = db.Column(db.DateTime)
    premium_stripe_subscription_id = db.Column(db.String(255))
    premium_overage_cents = db.Column(db.Integer, default=0)  # Track overage charges
    
    # --- IndexTTS2 (Separate premium tier from Chatterbox) ---
    # Tiers: 'none' | 'indextts' (100K) | 'indextts_plus' (200K) | 'indextts_pro' (300K)
    indextts_tier = db.Column(db.String(32), default='none')
    indextts_chars_used = db.Column(db.Integer, default=0)
    indextts_chars_reset_at = db.Column(db.DateTime)
    indextts_stripe_subscription_id = db.Column(db.String(255))
    
    # IndexTTS2 tier character limits
    INDEXTTS_LIMITS = {
        'none': 0,
        'indextts': 100000,      # 100K chars
        'indextts_plus': 200000,  # 200K chars
        'indextts_pro': 300000    # 300K chars
    }
    
    @property
    def has_indextts(self) -> bool:
        """Check if user has any IndexTTS2 access"""
        return self.indextts_tier in ('indextts', 'indextts_plus', 'indextts_pro')
    
    @property
    def indextts_char_limit(self) -> int:
        """Get IndexTTS2 character limit based on tier"""
        return self.INDEXTTS_LIMITS.get(self.indextts_tier, 0)
    
    @property
    def indextts_chars_remaining(self) -> int:
        """Get remaining IndexTTS2 characters for this billing period"""
        if not self.has_indextts:
            return 0
        self.check_and_reset_indextts_usage()
        return max(0, self.indextts_char_limit - (self.indextts_chars_used or 0))
    
    def check_and_reset_indextts_usage(self):
        """Reset IndexTTS2 usage if billing period has passed (monthly)"""
        if not self.indextts_chars_reset_at:
            self.indextts_chars_reset_at = datetime.utcnow() + timedelta(days=30)
            self.indextts_chars_used = 0
            return
        
        if datetime.utcnow() >= self.indextts_chars_reset_at:
            self.indextts_chars_used = 0
            self.indextts_chars_reset_at = datetime.utcnow() + timedelta(days=30)
    
    def use_indextts_chars(self, char_count: int) -> tuple:
        """
        Track IndexTTS2 character usage.
        Returns (success: bool, error_message: str or None)
        """
        if not self.has_indextts:
            return (False, "IndexTTS2 subscription required.")
        
        self.check_and_reset_indextts_usage()
        
        current_used = self.indextts_chars_used or 0
        remaining = self.indextts_char_limit - current_used
        
        if char_count > remaining:
            return (False, f"IndexTTS2 character limit reached. {remaining:,} characters remaining.")
        
        self.indextts_chars_used = current_used + char_count
        return (True, None)
    
    # --- Podcast TTS (Premium long-form multi-speaker) ---
    # Tiers: 'none' | 'vibevoice' (100K) | 'vibevoice_plus' (200K) | 'vibevoice_pro' (300K)
    vibevoice_tier = db.Column(db.String(32), default='none')
    vibevoice_chars_used = db.Column(db.Integer, default=0)
    vibevoice_chars_reset_at = db.Column(db.DateTime)
    vibevoice_stripe_subscription_id = db.Column(db.String(255))
    
    # VibeVoice tier character limits
    VIBEVOICE_LIMITS = {
        'none': 0,
        'vibevoice': 100000,      # 100K chars
        'vibevoice_plus': 200000,  # 200K chars
        'vibevoice_pro': 300000    # 300K chars
    }
    
    @property
    def has_vibevoice(self) -> bool:
        """Check if user has any VibeVoice access"""
        return self.vibevoice_tier in ('vibevoice', 'vibevoice_plus', 'vibevoice_pro')
    
    @property
    def vibevoice_char_limit(self) -> int:
        """Get VibeVoice character limit based on tier"""
        return self.VIBEVOICE_LIMITS.get(self.vibevoice_tier, 0)
    
    @property
    def vibevoice_chars_remaining(self) -> int:
        """Get remaining VibeVoice characters for this billing period"""
        if not self.has_vibevoice:
            return 0
        self.check_and_reset_vibevoice_usage()
        return max(0, self.vibevoice_char_limit - (self.vibevoice_chars_used or 0))
    
    def check_and_reset_vibevoice_usage(self):
        """Reset VibeVoice usage if billing period has passed (monthly)"""
        if not self.vibevoice_chars_reset_at:
            self.vibevoice_chars_reset_at = datetime.utcnow() + timedelta(days=30)
            self.vibevoice_chars_used = 0
            return
        
        if datetime.utcnow() >= self.vibevoice_chars_reset_at:
            self.vibevoice_chars_used = 0
            self.vibevoice_chars_reset_at = datetime.utcnow() + timedelta(days=30)
    
    def use_vibevoice_chars(self, char_count: int) -> tuple:
        """
        Track VibeVoice character usage.
        Returns (success: bool, error_message: str or None)
        """
        if not self.has_vibevoice:
            return (False, "VibeVoice subscription required.")
        
        self.check_and_reset_vibevoice_usage()
        
        current_used = self.vibevoice_chars_used or 0
        remaining = self.vibevoice_char_limit - current_used
        
        if char_count > remaining:
            return (False, f"VibeVoice character limit reached. {remaining:,} characters remaining.")
        
        self.vibevoice_chars_used = current_used + char_count
        return (True, None)
    
    # Premium tier character limits
    PREMIUM_LIMITS = {
        'none': 0,
        'premium': 100000,      # 100K chars (~2.2 hrs)
        'premium_plus': 200000,  # 200K chars (~4.4 hrs)
        'premium_pro': 300000    # 300K chars (~6.6 hrs)
    }
    
    @property
    def has_premium(self) -> bool:
        """Check if user has any premium Chatterbox access"""
        return self.premium_tier in ('premium', 'premium_plus', 'premium_pro')
    
    @property
    def premium_char_limit(self) -> int:
        """Get premium character limit based on tier"""
        return self.PREMIUM_LIMITS.get(self.premium_tier, 0)
    
    @property
    def premium_chars_remaining(self) -> int:
        """Get remaining premium characters for this billing period"""
        if not self.has_premium:
            return 0
        self.check_and_reset_premium_usage()
        return max(0, self.premium_char_limit - (self.premium_chars_used or 0))
    
    def check_and_reset_premium_usage(self):
        """Reset premium usage if billing period has passed (monthly)"""
        if not self.premium_chars_reset_at:
            self.premium_chars_reset_at = datetime.utcnow() + timedelta(days=30)
            self.premium_chars_used = 0
            return
        
        if datetime.utcnow() >= self.premium_chars_reset_at:
            self.premium_chars_used = 0
            self.premium_overage_cents = 0
            self.premium_chars_reset_at = datetime.utcnow() + timedelta(days=30)
    
    def use_premium_chars(self, char_count: int, allow_overage: bool = True) -> tuple:
        """
        Track premium Chatterbox character usage.
        Returns (success: bool, is_overage: bool, overage_cost_cents: int, error_message: str or None)
        
        Overage rate: $0.40 per 1K chars = 0.04 cents per char
        """
        if not self.has_premium:
            return (False, False, 0, "Premium subscription required for Ultra Voices.")
        
        self.check_and_reset_premium_usage()
        
        current_used = self.premium_chars_used or 0
        remaining = self.premium_char_limit - current_used
        
        if char_count <= remaining:
            # Within limit
            self.premium_chars_used = current_used + char_count
            return (True, False, 0, None)
        
        if not allow_overage:
            return (False, False, 0, f"Premium character limit reached. {remaining:,} characters remaining. Enable overage or upgrade your plan.")
        
        # Calculate overage
        chars_over_limit = char_count - remaining if remaining > 0 else char_count
        # $0.40 per 1K chars = 40 cents per 1K = 0.04 cents per char
        overage_cents = int((chars_over_limit / 1000) * 40)
        
        self.premium_chars_used = current_used + char_count
        self.premium_overage_cents = (self.premium_overage_cents or 0) + overage_cents
        
        return (True, True, overage_cents, None)


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


def send_welcome_email(to_email: str) -> None:
    """Send a welcome email when a user signs up."""
    message = EmailMessage()
    message['Subject'] = "Welcome to Cheap TTS! 🎉"
    message['From'] = PASSWORD_RESET_SENDER
    message['To'] = to_email
    message.set_content(
        "Welcome to Cheap TTS!\n\n"
        "Thanks for creating an account. You're now ready to convert text to natural-sounding speech.\n\n"
        "Here's what you can do:\n"
        "• Generate unlimited voice-overs with 500+ premium voices\n"
        "• Use emotion control for more expressive audio\n"
        "• Create multi-speaker dialogues for podcasts\n"
        "• Access 153 languages and accents\n\n"
        "Get started: https://cheaptts.com\n\n"
        "Questions? Just reply to this email.\n\n"
        "Happy creating!\n"
        "The Cheap TTS Team"
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
            print(f"[WELCOME EMAIL] Sent welcome email to {to_email}")
            return
        except Exception as exc:
            print(f"[WELCOME EMAIL] Failed to send email via SMTP: {exc}")

    # Local/dev fallback
    print(f"[WELCOME EMAIL] Would send welcome email to {to_email}")


def send_subscription_email(to_email: str, plan_type: str) -> None:
    """Send a confirmation email when a user subscribes."""
    if plan_type == 'lifetime':
        subject = "🎉 Lifetime Access Activated - Cheap TTS"
        plan_name = "Lifetime"
        plan_details = "You now have unlimited access to Cheap TTS forever. No monthly payments, no limits."
    elif plan_type.startswith('api_'):
        tier = plan_type.replace('api_', '').title()
        subject = f"🚀 API {tier} Plan Activated - Cheap TTS"
        plan_name = f"API {tier}"
        char_limit = "100,000" if "starter" in plan_type else "500,000"
        plan_details = f"Your API {tier} plan is now active with {char_limit} characters per month.\n\nGet your API keys: https://cheaptts.com/api-keys"
    else:
        subject = "✨ Subscription Activated - Cheap TTS"
        plan_name = "Monthly"
        plan_details = "You now have unlimited access to Cheap TTS. Generate as much audio as you need!"
    
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = PASSWORD_RESET_SENDER
    message['To'] = to_email
    message.set_content(
        f"Your {plan_name} plan is now active!\n\n"
        f"{plan_details}\n\n"
        "What's included:\n"
        "• 500+ natural-sounding voices\n"
        "• Emotion control for expressive audio\n"
        "• Multi-speaker dialogue support\n"
        "• 153 languages and accents\n\n"
        "Start creating: https://cheaptts.com\n\n"
        "Need help? Just reply to this email.\n\n"
        "Thanks for subscribing!\n"
        "The Cheap TTS Team"
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
            print(f"[SUBSCRIPTION EMAIL] Sent {plan_type} confirmation to {to_email}")
            return
        except Exception as exc:
            print(f"[SUBSCRIPTION EMAIL] Failed to send email via SMTP: {exc}")

    # Local/dev fallback
    print(f"[SUBSCRIPTION EMAIL] Would send {plan_type} confirmation to {to_email}")


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
        # Mobile app session columns
        if 'mobile_session_token' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN mobile_session_token VARCHAR(255)"))
            print("[MIGRATION] Added mobile_session_token column to user table")
        if 'mobile_session_expires' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN mobile_session_expires TIMESTAMP"))
            print("[MIGRATION] Added mobile_session_expires column to user table")
        # Character usage tracking columns (10K free, unlimited paid)
        if 'chars_used' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN chars_used INTEGER DEFAULT 0"))
            print("[MIGRATION] Added chars_used column to user table")
        if 'chars_reset_at' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN chars_reset_at TIMESTAMP"))
            print("[MIGRATION] Added chars_reset_at column to user table")
        # Premium Chatterbox TTS tier columns
        if 'premium_tier' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN premium_tier VARCHAR(32) DEFAULT 'none'"))
            print("[MIGRATION] Added premium_tier column to user table")
        if 'premium_chars_used' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN premium_chars_used INTEGER DEFAULT 0"))
            print("[MIGRATION] Added premium_chars_used column to user table")
        if 'premium_chars_reset_at' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN premium_chars_reset_at TIMESTAMP"))
            print("[MIGRATION] Added premium_chars_reset_at column to user table")
        if 'premium_stripe_subscription_id' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN premium_stripe_subscription_id VARCHAR(255)"))
            print("[MIGRATION] Added premium_stripe_subscription_id column to user table")
        if 'premium_overage_cents' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN premium_overage_cents INTEGER DEFAULT 0"))
            print("[MIGRATION] Added premium_overage_cents column to user table")
        # IndexTTS2 tier columns
        if 'indextts_tier' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN indextts_tier VARCHAR(32) DEFAULT 'none'"))
            print("[MIGRATION] Added indextts_tier column to user table")
        if 'indextts_chars_used' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN indextts_chars_used INTEGER DEFAULT 0"))
            print("[MIGRATION] Added indextts_chars_used column to user table")
        if 'indextts_chars_reset_at' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN indextts_chars_reset_at TIMESTAMP"))
            print("[MIGRATION] Added indextts_chars_reset_at column to user table")
        if 'indextts_stripe_subscription_id' not in existing_columns:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN indextts_stripe_subscription_id VARCHAR(255)"))
            print("[MIGRATION] Added indextts_stripe_subscription_id column to user table")
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


async def generate_speech_with_srt(text, voice, rate=None, volume=None, pitch=None, style=None, style_degree=None, cache_key=None):
    """Generate speech from text and also generate SRT subtitles.
    
    This is a simpler version that works for single-voice, non-SSML text.
    Returns tuple: (audio_file_path, srt_file_path)
    """
    import inspect
    import edge_tts as tts_module
    from edge_tts import SubMaker
    
    # Create filenames
    if cache_key:
        audio_fname = f"speech_{cache_key}.mp3"
        srt_fname = f"speech_{cache_key}.srt"
    else:
        unique_id = hashlib.md5(f"{text}{voice}{time.time()}".encode()).hexdigest()[:10]
        audio_fname = f"speech_{unique_id}.mp3"
        srt_fname = f"speech_{unique_id}.srt"
    
    audio_file = OUTPUT_DIR / audio_fname
    srt_file = OUTPUT_DIR / srt_fname
    
    # Check cache
    if cache_key and audio_file.exists() and srt_file.exists():
        return audio_file, srt_file
    
    # Check if style parameter is supported
    communicate_sig = inspect.signature(tts_module.Communicate.__init__)
    supports_style = 'style' in communicate_sig.parameters
    
    # Create communicate instance with WordBoundary for better subtitles
    if supports_style and style is not None:
        communicate = tts_module.Communicate(
            text=text,
            voice=voice,
            rate=rate or "+0%",
            volume=volume or "+0%",
            pitch=pitch or "+0Hz",
            style=style,
            style_degree=style_degree,
            boundary="WordBoundary",  # Get word-level timing for subtitles
            receive_timeout=600
        )
    else:
        communicate = tts_module.Communicate(
            text=text,
            voice=voice,
            rate=rate or "+0%",
            volume=volume or "+0%",
            pitch=pitch or "+0Hz",
            boundary="WordBoundary",  # Get word-level timing for subtitles
            receive_timeout=600
        )
    
    submaker = SubMaker()
    
    # Stream and collect audio + metadata
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
        elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
            submaker.feed(chunk)
    
    # Write audio file
    with open(audio_file, "wb") as f:
        f.write(audio_data)
    
    # Write SRT file
    srt_content = submaker.get_srt()
    with open(srt_file, "w", encoding="utf-8") as f:
        f.write(srt_content)
    
    print(f"[TTS+SRT] Generated: {audio_fname} ({len(audio_data)} bytes), {srt_fname} ({len(srt_content)} chars)")
    
    return audio_file, srt_file


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


@app.route('/about')
def about():
    """Serve the About page"""
    return render_template('about.html')


@app.route('/storytelling')
def storytelling():
    """Showcase page for Ultra Voices storytelling/audiobook capabilities"""
    return render_template('storytelling.html')


@app.route('/dashboard')
@login_required
def dashboard():
    """Serve the TTS tool page"""
    from datetime import datetime
    from calendar import monthrange
    
    # Check and reset usage if needed
    if hasattr(current_user, 'check_and_reset_usage'):
        current_user.check_and_reset_usage()
    
    # Get character usage info
    chars_used = getattr(current_user, 'chars_used', 0) or 0
    chars_limit = getattr(current_user, 'char_limit', User.FREE_CHAR_LIMIT)
    is_unlimited = current_user.is_subscribed  # Subscribers have unlimited
    chars_remaining = max(0, chars_limit - chars_used) if not is_unlimited else -1  # -1 means unlimited
    
    # Calculate next reset date (1st of next month)
    now = datetime.utcnow()
    if now.month == 12:
        next_reset = datetime(now.year + 1, 1, 1)
    else:
        next_reset = datetime(now.year, now.month + 1, 1)
    chars_reset_date = next_reset.strftime('%b 1, %Y')
    
    return render_template('index.html', 
                           chars_used=chars_used,
                           chars_limit=chars_limit,
                           chars_remaining=chars_remaining,
                           chars_reset_date=chars_reset_date,
                           is_unlimited=is_unlimited)


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
        
        # Send welcome email
        send_welcome_email(email)
        
        flash('Welcome! Your account has been created. You have 10,000 free characters per month.', 'success')
        
        # Handle redirects based on signup source
        if next_url:
            # Redirect back to where they came from (e.g., API pricing)
            return redirect(next_url)
        elif plan == 'lifetime' or api_plan:
            # User explicitly wants to purchase a plan - go to subscribe
            return redirect(url_for('subscribe', plan=plan))
        else:
            # Default - go directly to dashboard (free plan)
            return redirect(url_for('dashboard'))
    
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
                return redirect(url_for('dashboard'))
        
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash('Invalid email or password.', 'error')
            return redirect(url_for('login'))
        login_user(user)
        flash('Signed in successfully.', 'success')
        return redirect(url_for('dashboard'))
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
                send_subscription_email(current_user.email, plan_type)
                flash('Lifetime access activated. Enjoy forever!', 'success')
                return redirect(url_for('index'))
            elif plan_type.startswith('api_'):
                # API plan purchase
                tier = plan_type.replace('api_', '')  # 'starter' or 'pro'
                current_user.api_tier = tier
                current_user.api_chars_used = 0  # Reset usage
                current_user.api_usage_reset_at = datetime.utcnow() + timedelta(days=30)
                db.session.commit()
                send_subscription_email(current_user.email, plan_type)
                flash(f'API {tier.title()} plan activated! Create your first API key below.', 'success')
                return redirect(url_for('api_keys_page'))  # Redirect to API keys page
            else:
                # Regular monthly subscription
                current_user.subscription_status = 'active'
                db.session.commit()
                send_subscription_email(current_user.email, plan_type)
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
                cache_key = hashlib.md5(
                    f"preview:{voice}:{ssml_text}".encode()
                ).hexdigest()[:16]
                # Check if full SSML with <speak> wrapper (emotion on landing)
                is_full = ssml_text.strip().lower().startswith("<speak")
                output_file = run_async(
                    generate_speech(
                        ssml_text, voice, None, None, None,
                        is_ssml=True, cache_key=cache_key, is_full_ssml=is_full
                    )
                )
            elif is_ssml:
                # Check if this is full SSML with <speak> wrapper
                is_full = text.strip().lower().startswith("<speak")
                output_file = run_async(
                    generate_speech(
                        text, voice, rate, volume, pitch,
                        is_ssml=True, is_full_ssml=is_full
                    )
                )
            else:
                output_file = run_async(
                    generate_speech(text, voice, rate, volume, pitch)
                )
        except Exception as gen_error:
            return jsonify(
                {"success": False, "error": f"Speech generation failed: {str(gen_error)}"}
            ), 500
        
        return jsonify({
            'success': True,
            'audioUrl': f'/api/audio/{output_file.name}',
            'warnings': warnings_out
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/generate', methods=['POST'])
@login_required
@csrf.exempt
def api_generate():
    """Generate speech from text - with character limit enforcement"""
    import re
    
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
        generate_srt = data.get('generate_srt', False)  # NEW: SRT generation flag
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

        # --- Calculate total characters for limit checking ---
        total_chars = 0
        if chunks is not None:
            for chunk in chunks:
                content = chunk.get('content', '')
                # Strip SSML tags to get plain text char count
                plain_text = re.sub(r'<[^>]+>', '', str(content))
                total_chars += len(plain_text)
        else:
            # Plain text mode
            plain_text = re.sub(r'<[^>]+>', '', text) if is_ssml else text
            total_chars = len(plain_text)
        
        # --- Enforce character limit ---
        success, error_msg = current_user.use_chars(total_chars)
        if not success:
            return jsonify({
                'success': False,
                'error': error_msg,
                'limit_reached': True,
                'chars_used': current_user.chars_used or 0,
                'chars_limit': current_user.char_limit,
                'chars_remaining': current_user.chars_remaining,
                'upgrade_url': '/subscribe'
            }), 402  # Payment Required
        
        # Save the usage
        db.session.commit()

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

                    # Generate with SRT if requested (single chunk, single voice)
                    srt_url = None
                    if generate_srt:
                        try:
                            audio_file, srt_file = run_async(
                                generate_speech_with_srt(
                                    plain_text,
                                    voice,
                                    rate=f"{chunk_rate:+d}%" if isinstance(chunk_rate, int) else chunk_rate,
                                    volume=f"{chunk_volume:+d}%" if isinstance(chunk_volume, int) else chunk_volume,
                                    pitch=f"{chunk_pitch:+d}Hz" if isinstance(chunk_pitch, int) else chunk_pitch,
                                    style=emotion,
                                    style_degree=style_degree,
                                    cache_key=cache_key
                                )
                            )
                            output_file = audio_file
                            srt_url = f'/api/srt/{srt_file.name}'
                        except Exception as srt_err:
                            print(f"[SRT ERROR] Failed to generate SRT, falling back to audio-only: {srt_err}")
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
                    else:
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

                    response_data = {
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
                        'ssml_used': plain_text,
                        'chars_used': current_user.chars_used or 0,
                        'chars_limit': current_user.char_limit,
                        'chars_remaining': current_user.chars_remaining,
                    }
                    if srt_url:
                        response_data['srtUrl'] = srt_url
                    return jsonify(response_data)

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
                'chars_used': current_user.chars_used or 0,
                'chars_limit': current_user.char_limit,
                'chars_remaining': current_user.chars_remaining,
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
                'chars_used': current_user.chars_used or 0,
                'chars_limit': current_user.char_limit,
                'chars_remaining': current_user.chars_remaining,
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
            'audioUrl': f'/api/audio/{output_file.name}',
            'chars_used': current_user.chars_used or 0,
            'chars_limit': current_user.char_limit,
            'chars_remaining': current_user.chars_remaining,
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


# -------- Premium Ultra TTS Endpoints --------

# ===== TEXT PREPROCESSING FOR BETTER TTS QUALITY =====
def preprocess_text_for_tts(text):
    """
    Preprocess text to match HuggingFace Chatterbox quality.
    - Expands contractions
    - Normalizes numbers
    - Adds natural pauses via punctuation
    - Cleans up whitespace
    """
    import re
    
    # Expand common contractions for clearer speech
    contractions = {
        "don't": "do not", "doesn't": "does not", "didn't": "did not",
        "won't": "will not", "wouldn't": "would not", "couldn't": "could not",
        "shouldn't": "should not", "can't": "cannot", "isn't": "is not",
        "aren't": "are not", "wasn't": "was not", "weren't": "were not",
        "haven't": "have not", "hasn't": "has not", "hadn't": "had not",
        "I'm": "I am", "you're": "you are", "we're": "we are", "they're": "they are",
        "he's": "he is", "she's": "she is", "it's": "it is", "that's": "that is",
        "what's": "what is", "who's": "who is", "there's": "there is",
        "I've": "I have", "you've": "you have", "we've": "we have", "they've": "they have",
        "I'll": "I will", "you'll": "you will", "we'll": "we will", "they'll": "they will",
        "he'll": "he will", "she'll": "she will", "it'll": "it will",
        "I'd": "I would", "you'd": "you would", "we'd": "we would", "they'd": "they would",
        "he'd": "he would", "she'd": "she would", "it'd": "it would",
        "let's": "let us", "that'll": "that will", "who'll": "who will",
    }
    
    for contraction, expansion in contractions.items():
        # Case-insensitive replacement
        text = re.sub(re.escape(contraction), expansion, text, flags=re.IGNORECASE)
    
    # Convert common number patterns to words (basic)
    number_words = {
        '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four',
        '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine',
        '10': 'ten', '11': 'eleven', '12': 'twelve', '100': 'one hundred',
        '1000': 'one thousand', '2024': 'twenty twenty four', '2025': 'twenty twenty five',
    }
    for num, word in number_words.items():
        text = re.sub(r'\b' + num + r'\b', word, text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    # Ensure sentences end with proper punctuation for natural pauses
    # Add period if text doesn't end with punctuation
    if text and text[-1] not in '.!?':
        text += '.'
    
    # Add slight pause markers (extra space) after major punctuation
    # This helps the model understand pause points
    text = re.sub(r'\.(\s)', '.  \\1', text)  # Period: longer pause
    text = re.sub(r'\!(\s)', '!  \\1', text)  # Exclamation: longer pause
    text = re.sub(r'\?(\s)', '?  \\1', text)  # Question: longer pause
    
    # Remove emojis (they can confuse TTS)
    text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', '', text)
    
    return text.strip()


def split_into_sentences(text, max_chars=180):
    """
    Split text into semantic chunks at sentence boundaries.
    Better than arbitrary character splits for natural speech.
    """
    import re
    
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        # If adding this sentence exceeds max, save current and start new
        if len(current_chunk) + len(sentence) + 1 > max_chars and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = sentence
        else:
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence
    
    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    # If no chunks created, return original as single chunk
    if not chunks:
        chunks = [text]
    
    return chunks


def parse_speaker_segments(text):
    """
    Parse text with speaker tags into segments.
    Supports both formats:
    - [S1]: [S2]: speaker number tags
    - [Emily]: [Michael]: direct voice name tags
    Returns list of (speaker_id_or_name, text) tuples.
    """
    import re
    
    # First try voice name format [VoiceName]:
    voice_pattern = r'\[([A-Za-z]+)\]:\s*'
    voice_parts = re.split(voice_pattern, text)
    
    if len(voice_parts) > 1:
        # Voice name tags found
        segments = []
        # First part before any tag (if exists)
        if voice_parts[0].strip():
            segments.append(('Emily', voice_parts[0].strip()))  # Default voice
        
        # Process voice:text pairs
        for i in range(1, len(voice_parts), 2):
            voice_name = voice_parts[i]
            if i + 1 < len(voice_parts):
                seg_text = voice_parts[i + 1].strip()
                if seg_text:
                    segments.append((voice_name, seg_text))
        return segments
    
    # Try speaker number format [S1]: [S2]:
    pattern = r'\[S(\d+)\]:\s*'
    parts = re.split(pattern, text, flags=re.IGNORECASE)
    
    if len(parts) == 1:
        # No speaker tags - single speaker
        return [('1', text.strip())]
    
    segments = []
    # First part before any tag (if exists)
    if parts[0].strip():
        segments.append(('1', parts[0].strip()))
    
    # Process speaker:text pairs
    for i in range(1, len(parts), 2):
        speaker_id = parts[i]
        if i + 1 < len(parts):
            seg_text = parts[i + 1].strip()
            if seg_text:
                segments.append((speaker_id, seg_text))
    
    return segments


def upload_reference_audio_to_chatterbox(file_path, filename=None):
    """
    Upload a reference audio file to the Chatterbox server for voice cloning.
    
    Parameters:
    - file_path: Local path to the audio file
    - filename: Optional filename to use on server (defaults to original filename)
    
    Returns:
    - The actual filename on the server (may have spaces replaced with underscores)
    """
    if filename is None:
        filename = os.path.basename(file_path)
    
    print(f"[ULTRA TTS] Uploading reference audio from {file_path} as {filename}...")
    
    with open(file_path, 'rb') as f:
        # Note: Chatterbox server expects 'files' key, not 'file'
        files = {'files': (filename, f, 'audio/wav')}
        response = requests.post(
            f'{CHATTERBOX_URL}/upload_reference',
            files=files,
            timeout=120  # Increased timeout for large files
        )
    
    if response.status_code != 200:
        error_detail = response.text[:500] if response.text else f'HTTP {response.status_code}'
        print(f"[ULTRA TTS] Upload failed: {error_detail}")
        raise Exception(f'Failed to upload reference audio: {error_detail}')
    
    # Server may rename file (e.g., replace spaces with underscores)
    result = response.json()
    uploaded_files = result.get('uploaded_files', [])
    if uploaded_files:
        actual_filename = uploaded_files[0]
        print(f"[ULTRA TTS] Successfully uploaded reference audio as: {actual_filename}")
        return actual_filename
    
    print(f"[ULTRA TTS] Successfully uploaded reference audio: {filename}")
    return filename


def get_chatterbox_reference_files():
    """
    Get list of reference audio files available on the Chatterbox server.
    
    Returns:
    - List of filenames available for voice cloning
    """
    try:
        response = requests.get(
            f'{CHATTERBOX_URL}/get_reference_files',
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            files = data.get('files', [])
            print(f"[ULTRA TTS] Reference files on server: {files}")
            return files
        else:
            print(f"[ULTRA TTS] Error getting reference files: HTTP {response.status_code}")
    except Exception as e:
        print(f"[ULTRA TTS] Error getting reference files: {e}")
    return []


def ensure_reference_audio_uploaded(local_path, filename):
    """
    Ensure a reference audio file is uploaded to the Chatterbox server.
    Checks if it already exists, uploads if not.
    
    Parameters:
    - local_path: Local path to the audio file
    - filename: Filename to use on the server
    
    Returns:
    - True if file is available on server, False otherwise
    """
    print(f"[ULTRA TTS] Ensuring reference audio is uploaded: {filename}")
    
    # Check if local file exists
    if not os.path.exists(local_path):
        print(f"[ULTRA TTS] ERROR: Local file not found: {local_path}")
        return False
    
    # Check if file already exists on server
    existing_files = get_chatterbox_reference_files()
    if filename in existing_files:
        print(f"[ULTRA TTS] Reference audio already on server: {filename}")
        return True
    
    # Upload if not exists
    try:
        upload_reference_audio_to_chatterbox(local_path, filename)
        return True
    except Exception as e:
        print(f"[ULTRA TTS] Failed to upload reference audio: {e}")
        return False
        return True
    except Exception as e:
        print(f"[ULTRA TTS] Failed to upload reference audio: {e}")
        return False


def generate_chatterbox_audio(text, voice_mode='predefined', predefined_voice_id='Emily', 
                               reference_audio_filename=None, 
                               exaggeration=0.6, cfg_weight=0.3, temperature=0.4, 
                               speed_factor=1.0, split_text=True, chunk_size=180):
    """
    Call the devnen/Chatterbox-TTS-Server /tts endpoint.
    Returns audio bytes (WAV) or raises exception.
    
    Parameters:
    - text: The text to synthesize
    - voice_mode: 'predefined' or 'clone'
    - predefined_voice_id: Voice name (e.g., 'Emily', 'Michael', 'Olivia')
    - reference_audio_filename: Filename of reference audio for voice cloning (when voice_mode='clone')
    - exaggeration: Emotion intensity (0.0-2.0, default 0.6 for natural speech)
    - cfg_weight: Classifier-free guidance (0.0-1.0, default 0.3 for slower pacing)
    - temperature: Randomness (0.1-1.5, default 0.4 for HF-quality)
    - speed_factor: Speech speed (0.5-2.0, default 1.0)
    - split_text: Whether to split long text into chunks
    - chunk_size: Characters per chunk when splitting (default 180 for semantic chunks)
    
    NOTE: Defaults tuned to match HuggingFace demo quality.
    Lower temperature (0.35-0.45) = more stable, natural speech
    Lower cfg_weight (0.3) = slower, more deliberate pacing
    """
    # Preprocess text for better TTS quality
    processed_text = preprocess_text_for_tts(text)
    
    payload = {
        'text': processed_text,
        'voice_mode': voice_mode,
        'exaggeration': exaggeration,
        'cfg_weight': cfg_weight,
        'temperature': temperature,
        'speed_factor': speed_factor,
        'split_text': split_text,
        'chunk_size': chunk_size,
        'output_format': 'wav'
    }
    
    # Add voice-specific parameters
    if voice_mode == 'clone' and reference_audio_filename:
        payload['reference_audio_filename'] = reference_audio_filename
        print(f"[ULTRA TTS] Using cloned voice: {reference_audio_filename}")
    else:
        payload['predefined_voice_id'] = predefined_voice_id
    
    print(f"[ULTRA TTS] Generating: mode={voice_mode}, temp={temperature}, exag={exaggeration}, cfg={cfg_weight}, text_len={len(processed_text)}")
    
    response = requests.post(
        f'{CHATTERBOX_URL}/tts',
        json=payload,
        timeout=600,  # 10 min for long texts
        stream=True
    )
    
    if response.status_code != 200:
        error_msg = 'Unknown error'
        try:
            error_msg = response.json().get('detail', response.text[:200])
        except:
            error_msg = response.text[:200] if response.text else f'HTTP {response.status_code}'
        raise Exception(f'Ultra TTS error: {error_msg}')
    
    # Response is streaming audio
    return response.content


def concatenate_wav_files_with_crossfade(audio_chunks, crossfade_ms=30, silence_ms=200):
    """
    Concatenate WAV audio chunks with crossfade for smooth transitions.
    Uses HuggingFace-style merging to avoid robotic stitching.
    
    Parameters:
    - audio_chunks: List of WAV bytes
    - crossfade_ms: Crossfade duration in milliseconds (20-40ms recommended)
    - silence_ms: Additional silence between chunks (for speaker changes)
    """
    import io
    import wave
    import struct
    import array
    
    if not audio_chunks:
        raise ValueError("No audio chunks to concatenate")
    
    if len(audio_chunks) == 1:
        return audio_chunks[0]
    
    # Parse all WAV files into sample arrays
    all_samples = []
    params = None
    sample_rate = None
    sample_width = None
    n_channels = None
    
    for i, chunk in enumerate(audio_chunks):
        wav_io = io.BytesIO(chunk)
        try:
            with wave.open(wav_io, 'rb') as w:
                if params is None:
                    params = w.getparams()
                    sample_rate = w.getframerate()
                    sample_width = w.getsampwidth()
                    n_channels = w.getnchannels()
                
                frames = w.readframes(w.getnframes())
                
                # Convert bytes to samples based on sample width
                if sample_width == 2:  # 16-bit
                    samples = array.array('h', frames)
                elif sample_width == 1:  # 8-bit
                    samples = array.array('b', frames)
                else:
                    # Fallback: treat as raw bytes
                    samples = list(frames)
                
                all_samples.append(samples)
        except Exception as e:
            print(f"[CROSSFADE] Error reading chunk {i}: {e}")
            continue
    
    if not all_samples:
        raise ValueError("No valid audio chunks")
    
    # Calculate crossfade and silence in samples
    crossfade_samples = int(sample_rate * crossfade_ms / 1000) * n_channels
    silence_samples = int(sample_rate * silence_ms / 1000) * n_channels
    
    # Create silence array
    silence = array.array('h', [0] * silence_samples) if sample_width == 2 else array.array('b', [0] * silence_samples)
    
    # Merge with crossfade
    result = array.array('h') if sample_width == 2 else array.array('b')
    
    for i, samples in enumerate(all_samples):
        if i == 0:
            # First chunk: add all samples
            result.extend(samples)
        else:
            # Apply crossfade between end of result and start of new chunk
            if len(result) >= crossfade_samples and len(samples) >= crossfade_samples:
                # Crossfade region
                for j in range(crossfade_samples):
                    # Linear crossfade: fade out old, fade in new
                    fade_out = 1.0 - (j / crossfade_samples)
                    fade_in = j / crossfade_samples
                    
                    old_idx = len(result) - crossfade_samples + j
                    old_sample = result[old_idx]
                    new_sample = samples[j]
                    
                    # Blend samples
                    blended = int(old_sample * fade_out + new_sample * fade_in)
                    
                    # Clamp to prevent overflow
                    if sample_width == 2:
                        blended = max(-32768, min(32767, blended))
                    else:
                        blended = max(-128, min(127, blended))
                    
                    result[old_idx] = blended
                
                # Add remaining samples after crossfade region
                result.extend(samples[crossfade_samples:])
            else:
                # Chunks too short for crossfade, just add silence and append
                result.extend(silence)
                result.extend(samples)
        
        # Add small silence between chunks (not after last)
        if i < len(all_samples) - 1:
            result.extend(silence)
    
    # Write combined WAV
    output = io.BytesIO()
    with wave.open(output, 'wb') as w:
        w.setparams(params)
        w.writeframes(result.tobytes())
    
    return output.getvalue()


def concatenate_wav_files(audio_chunks, silence_ms=300):
    """
    Concatenate multiple WAV audio chunks with silence between them.
    Returns combined WAV bytes.
    """
    import io
    import wave
    import struct
    
    if not audio_chunks:
        raise ValueError("No audio chunks to concatenate")
    
    if len(audio_chunks) == 1:
        return audio_chunks[0]
    
    # Parse first WAV to get format
    first_wav = io.BytesIO(audio_chunks[0])
    with wave.open(first_wav, 'rb') as w:
        params = w.getparams()
        sample_rate = w.getframerate()
        sample_width = w.getsampwidth()
        n_channels = w.getnchannels()
    
    # Generate silence
    silence_samples = int(sample_rate * silence_ms / 1000)
    silence_bytes = b'\x00' * (silence_samples * sample_width * n_channels)
    
    # Collect all audio frames
    all_frames = []
    for i, chunk in enumerate(audio_chunks):
        wav_io = io.BytesIO(chunk)
        try:
            with wave.open(wav_io, 'rb') as w:
                frames = w.readframes(w.getnframes())
                all_frames.append(frames)
                # Add silence between chunks (not after last)
                if i < len(audio_chunks) - 1:
                    all_frames.append(silence_bytes)
        except Exception as e:
            print(f"[CONCAT] Error reading chunk {i}: {e}")
            continue
    
    # Write combined WAV
    output = io.BytesIO()
    with wave.open(output, 'wb') as w:
        w.setparams(params)
        for frames in all_frames:
            w.writeframes(frames)
    
    return output.getvalue()


@app.route('/api/chatterbox-voices', methods=['GET'])
@login_required
def api_chatterbox_voices():
    """
    Return available Chatterbox voices for the Premium TTS dropdown.
    """
    # Return our predefined list of voices
    # Categorize by typical gender for better UX
    voices_data = {
        'voices': CHATTERBOX_VOICES,
        'speaker_mapping': CHATTERBOX_SPEAKER_VOICES,
        'categories': {
            'female': ['Emily', 'Olivia', 'Taylor', 'Abigail', 'Alice', 'Cora', 'Elena', 'Gianna', 'Jade', 'Layla'],
            'male': ['Michael', 'Ryan', 'Thomas', 'Adrian', 'Alexander', 'Austin', 'Axel', 'Connor', 'Eli', 'Everett', 'Gabriel', 'Henry', 'Ian', 'Jeremiah', 'Jordan', 'Julian', 'Leonardo', 'Miles']
        }
    }
    return jsonify(voices_data)


@app.route('/api/generate-premium', methods=['POST'])
@login_required
@csrf.exempt
def api_generate_premium():
    """
    Generate premium audio using Chatterbox TTS (devnen/Chatterbox-TTS-Server).
    Supports:
    - Multi-speaker dialogue with [Emily]: [Michael]: format
    - Per-chunk settings via chunks[] array
    Requires premium subscription tier.
    """
    import re
    
    try:
        # Check if Chatterbox is configured
        if not CHATTERBOX_URL:
            return jsonify({
                'success': False,
                'error': 'Premium TTS service is not configured. Please contact support.'
            }), 503
        
        data = request.get_json(silent=True) or {}
        
        # Check if using chunks mode (per-segment settings) or text mode
        chunks = data.get('chunks', None)
        use_chunks_mode = chunks is not None and len(chunks) > 0
        
        if use_chunks_mode:
            # Chunks mode - each chunk has its own voice and settings
            voice = data.get('voice', 'Emily.wav')  # fallback
        else:
            # Standard text mode
            text = (data.get('text', '') or '').strip()
            exaggeration = float(data.get('exaggeration', 0.5))
            cfg_weight = float(data.get('cfg_weight', 0.5))
            temperature = float(data.get('temperature', 0.8))
            speed_factor = float(data.get('speed_factor', 1.0))
            voice = data.get('voice', 'Emily')
        
        allow_overage = data.get('allow_overage', True)
        
        # Detect if using cloned voice format (clone:VoiceName)
        is_cloned_voice_main = str(voice).startswith('clone:')
        
        # Validation
        if not use_chunks_mode:
            # Accept predefined voices OR cloned voice format
            if not is_cloned_voice_main and voice not in CHATTERBOX_VOICES:
                voice = 'Emily'
            if not text:
                return jsonify({'success': False, 'error': 'No text provided'}), 400
            if len(text) > 100000:
                return jsonify({'success': False, 'error': 'Text too long (max 100,000 chars)'}), 400
        
        # Calculate character count
        if use_chunks_mode:
            char_count = sum(len(chunk.get('text', '')) for chunk in chunks)
        else:
            plain_text = re.sub(r'\[S\d+\]:\s*', '', text, flags=re.IGNORECASE)
            char_count = len(plain_text)
        
        # Check premium subscription and usage
        if not current_user.has_premium:
            return jsonify({
                'success': False,
                'error': 'Premium subscription required for Ultra Voices. Upgrade to Premium for ultra-realistic AI voices.',
                'upgrade_url': '/subscribe',
                'premium_required': True
            }), 402
        
        # Check and track usage
        success, is_overage, overage_cents, error_msg = current_user.use_premium_chars(char_count, allow_overage)
        if not success:
            return jsonify({
                'success': False,
                'error': error_msg,
                'limit_reached': True,
                'premium_chars_used': current_user.premium_chars_used or 0,
                'premium_chars_limit': current_user.premium_char_limit,
                'premium_chars_remaining': current_user.premium_chars_remaining,
                'upgrade_url': '/subscribe'
            }), 402
        
        db.session.commit()
        
        audio_chunks = []
        segment_stats = []
        
        if use_chunks_mode:
            # ===== CHUNKS MODE: Per-segment Chatterbox settings =====
            print(f"[PREMIUM TTS] CHUNKS MODE: {len(chunks)} chunks with per-segment settings")
            
            for idx, chunk in enumerate(chunks):
                chunk_text = chunk.get('text', '').strip()
                chunk_voice = chunk.get('voice', 'Emily.wav')
                chunk_temp = float(chunk.get('temperature', 0.8))
                chunk_exag = float(chunk.get('exaggeration', 0.4))
                chunk_cfg = float(chunk.get('cfg_weight', 0.5))
                chunk_speed = float(chunk.get('speed_factor', 1.0))
                
                if not chunk_text:
                    continue
                
                # Detect if using cloned voice (format: "clone:VoiceName")
                is_cloned_voice = str(chunk_voice).startswith('clone:')
                reference_filename = None
                
                if is_cloned_voice:
                    # Extract the voice name and get the reference audio filename
                    clone_name = chunk_voice.replace('clone:', '')
                    reference_filename = CHATTERBOX_CLONED_VOICES.get(clone_name)  # Server filename (with underscores)
                    local_filename = CLONED_VOICE_LOCAL_FILES.get(clone_name, reference_filename)  # Local filename (may have spaces)
                    if reference_filename:
                        # Ensure reference audio is uploaded to server
                        local_path = os.path.join(app.static_folder, local_filename)
                        upload_success = ensure_reference_audio_uploaded(local_path, reference_filename)
                        if not upload_success:
                            print(f"[PREMIUM TTS] Warning: Failed to upload cloned voice '{clone_name}', falling back to Emily")
                            is_cloned_voice = False
                            chunk_voice = 'Emily.wav'
                        else:
                            print(f"[PREMIUM TTS] Chunk {idx+1}/{len(chunks)}: CLONED Voice={clone_name} (ref={reference_filename}), Exag={chunk_exag}, {len(chunk_text)} chars")
                    else:
                        print(f"[PREMIUM TTS] Warning: Unknown cloned voice '{clone_name}', falling back to Emily")
                        is_cloned_voice = False
                        chunk_voice = 'Emily.wav'
                else:
                    print(f"[PREMIUM TTS] Chunk {idx+1}/{len(chunks)}: Voice={chunk_voice}, Exag={chunk_exag}, {len(chunk_text)} chars")
                
                try:
                    if is_cloned_voice and reference_filename:
                        # Use voice cloning mode
                        audio_data = generate_chatterbox_audio(
                            text=chunk_text,
                            voice_mode='clone',
                            reference_audio_filename=reference_filename,
                            exaggeration=chunk_exag,
                            cfg_weight=chunk_cfg,
                            temperature=chunk_temp,
                            speed_factor=chunk_speed,
                            split_text=True,
                            chunk_size=200
                        )
                    else:
                        # Use predefined voice mode
                        audio_data = generate_chatterbox_audio(
                            text=chunk_text,
                            voice_mode='predefined',
                            predefined_voice_id=chunk_voice,
                            exaggeration=chunk_exag,
                            cfg_weight=chunk_cfg,
                            temperature=chunk_temp,
                            speed_factor=chunk_speed,
                            split_text=True,
                            chunk_size=200
                        )
                    audio_chunks.append(audio_data)
                    segment_stats.append({
                        'voice': chunk_voice,
                        'chars': len(chunk_text),
                        'audio_size': len(audio_data)
                    })
                except Exception as e:
                    print(f"[PREMIUM TTS] Chunk {idx+1} failed: {e}")
                    current_user.premium_chars_used = max(0, (current_user.premium_chars_used or 0) - char_count)
                    if is_overage:
                        current_user.premium_overage_cents = max(0, (current_user.premium_overage_cents or 0) - overage_cents)
                    db.session.commit()
                    return jsonify({
                        'success': False,
                        'error': f'Failed to generate chunk {idx+1}: {str(e)}'
                    }), 500
            
            has_multiple_speakers = len(set(chunk.get('voice', '') for chunk in chunks)) > 1
        else:
            # ===== STANDARD MODE: Parse multi-speaker segments =====
            segments = parse_speaker_segments(text)
            has_multiple_speakers = len(set(s[0] for s in segments)) > 1
            
            print(f"[PREMIUM TTS] STANDARD MODE: {len(segments)} segments, multi-speaker={has_multiple_speakers}, voice={voice}")
            
            for idx, (speaker_id, segment_text) in enumerate(segments):
                if has_multiple_speakers:
                    # Check if speaker_id is a voice name (e.g., "Emily") or a number
                    if speaker_id in CHATTERBOX_VOICES:
                        voice_name = speaker_id  # Direct voice name from [Emily]: format
                    else:
                        voice_name = CHATTERBOX_SPEAKER_VOICES.get(speaker_id, 'Emily')  # Mapped from [S1]: format
                    use_clone_for_segment = False
                else:
                    voice_name = voice
                    use_clone_for_segment = is_cloned_voice_main
                
                # Handle cloned voice for single-speaker mode
                reference_filename = None
                if use_clone_for_segment:
                    clone_name = voice.replace('clone:', '')
                    reference_filename = CHATTERBOX_CLONED_VOICES.get(clone_name)  # Server filename
                    local_filename = CLONED_VOICE_LOCAL_FILES.get(clone_name, reference_filename)  # Local filename
                    if reference_filename:
                        local_path = os.path.join(app.static_folder, local_filename)
                        upload_success = ensure_reference_audio_uploaded(local_path, reference_filename)
                        if not upload_success:
                            print(f"[PREMIUM TTS] Warning: Failed to upload cloned voice '{clone_name}', falling back to Emily")
                            use_clone_for_segment = False
                            voice_name = 'Emily'
                        else:
                            print(f"[PREMIUM TTS] Segment {idx+1}/{len(segments)}: CLONED Voice={clone_name}, {len(segment_text)} chars")
                    else:
                        print(f"[PREMIUM TTS] Warning: Unknown cloned voice '{clone_name}', falling back to Emily")
                        use_clone_for_segment = False
                        voice_name = 'Emily'
                else:
                    print(f"[PREMIUM TTS] Segment {idx+1}/{len(segments)}: Speaker {speaker_id} ({voice_name}), {len(segment_text)} chars")
                
                try:
                    if use_clone_for_segment and reference_filename:
                        # Use voice cloning mode
                        audio_data = generate_chatterbox_audio(
                            text=segment_text,
                            voice_mode='clone',
                            reference_audio_filename=reference_filename,
                            exaggeration=exaggeration,
                            cfg_weight=cfg_weight,
                            temperature=temperature,
                            speed_factor=speed_factor,
                            split_text=True,
                            chunk_size=200
                        )
                    else:
                        # Use predefined voice mode
                        audio_data = generate_chatterbox_audio(
                            text=segment_text,
                            voice_mode='predefined',
                            predefined_voice_id=voice_name,
                            exaggeration=exaggeration,
                            cfg_weight=cfg_weight,
                            temperature=temperature,
                            speed_factor=speed_factor,
                            split_text=True,
                            chunk_size=200
                        )
                    audio_chunks.append(audio_data)
                    segment_stats.append({
                        'speaker': speaker_id,
                        'voice': voice_name if not use_clone_for_segment else f"clone:{clone_name}",
                        'chars': len(segment_text),
                        'audio_size': len(audio_data)
                    })
                except Exception as e:
                    print(f"[PREMIUM TTS] Segment {idx+1} failed: {e}")
                    current_user.premium_chars_used = max(0, (current_user.premium_chars_used or 0) - char_count)
                    if is_overage:
                        current_user.premium_overage_cents = max(0, (current_user.premium_overage_cents or 0) - overage_cents)
                    db.session.commit()
                    return jsonify({
                        'success': False,
                        'error': f'Failed to generate segment {idx+1}: {str(e)}'
                    }), 500
        
        # Concatenate all audio chunks with crossfade for smooth transitions
        if len(audio_chunks) > 1:
            print(f"[PREMIUM TTS] Concatenating {len(audio_chunks)} audio chunks with crossfade...")
            # Use crossfade for same-speaker, silence for speaker changes
            if has_multiple_speakers:
                final_audio = concatenate_wav_files_with_crossfade(audio_chunks, crossfade_ms=30, silence_ms=300)
            else:
                final_audio = concatenate_wav_files_with_crossfade(audio_chunks, crossfade_ms=40, silence_ms=100)
        else:
            final_audio = audio_chunks[0] if audio_chunks else b''
        
        if not final_audio:
            return jsonify({
                'success': False,
                'error': 'No audio data generated'
            }), 500
        
        # Save the audio file
        if use_chunks_mode:
            file_hash = hashlib.md5(f"chunks:{len(chunks)}:{time.time()}".encode()).hexdigest()[:12]
        else:
            file_hash = hashlib.md5(f"{text[:50]}:{exaggeration}:{time.time()}".encode()).hexdigest()[:12]
        output_file = OUTPUT_DIR / f"premium_{file_hash}.wav"
        
        with open(output_file, 'wb') as f:
            f.write(final_audio)
        
        print(f"[PREMIUM TTS] Saved {output_file.name}, {len(final_audio)} bytes")
        
        return jsonify({
            'success': True,
            'audioUrl': f'/api/audio/{output_file.name}',
            'stats': {
                'total_chars': char_count,
                'segments': len(chunks) if use_chunks_mode else len(segments),
                'multi_speaker': has_multiple_speakers,
                'segment_details': segment_stats,
                'audio_size': len(final_audio)
            },
            'is_overage': is_overage,
            'overage_cents': overage_cents if is_overage else 0,
            'premium_chars_used': current_user.premium_chars_used or 0,
            'premium_chars_limit': current_user.premium_char_limit,
            'premium_chars_remaining': current_user.premium_chars_remaining
        })
        
    except requests.Timeout:
        return jsonify({
            'success': False,
            'error': 'Premium TTS generation timed out. Please try with shorter text.'
        }), 504
    except Exception as e:
        print(f"[PREMIUM TTS ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/preview-chunk', methods=['POST'])
@login_required
@csrf.exempt
def api_preview_chunk():
    """
    Preview a single chunk with Chatterbox TTS.
    This is a free preview (doesn't count against usage) for short samples.
    Max 100 characters.
    """
    try:
        if not CHATTERBOX_URL:
            return jsonify({
                'success': False,
                'error': 'Premium TTS service is not configured.'
            }), 503
        
        data = request.get_json(silent=True) or {}
        
        text = (data.get('text', '') or '').strip()
        voice = data.get('voice', 'Emily.wav')
        temperature = float(data.get('temperature', 0.8))
        exaggeration = float(data.get('exaggeration', 0.4))
        cfg_weight = float(data.get('cfg_weight', 0.5))
        speed_factor = float(data.get('speed_factor', 1.0))
        
        if not text:
            return jsonify({'success': False, 'error': 'No text provided'}), 400
        
        # Limit preview to 100 characters
        if len(text) > 100:
            text = text[:100]
        
        print(f"[PREVIEW CHUNK] Voice={voice}, Exag={exaggeration}, Text: {text[:30]}...")
        
        try:
            audio_data = generate_chatterbox_audio(
                text=text,
                voice_mode='predefined',
                predefined_voice_id=voice,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                temperature=temperature,
                speed_factor=speed_factor,
                split_text=False,
                chunk_size=200
            )
            
            # Save preview file
            file_hash = hashlib.md5(f"preview:{text[:20]}:{time.time()}".encode()).hexdigest()[:12]
            output_file = OUTPUT_DIR / f"preview_{file_hash}.wav"
            
            with open(output_file, 'wb') as f:
                f.write(audio_data)
            
            return jsonify({
                'success': True,
                'audioUrl': f'/api/audio/{output_file.name}'
            })
            
        except Exception as e:
            print(f"[PREVIEW CHUNK ERROR] {e}")
            return jsonify({
                'success': False,
                'error': f'Preview failed: {str(e)}'
            }), 500
            
    except Exception as e:
        print(f"[PREVIEW CHUNK ERROR] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/generate-premium/async', methods=['POST'])
@login_required
@csrf.exempt
def api_generate_premium_async():
    """
    Async endpoint - not needed for Chatterbox.
    Chatterbox handles requests synchronously. For long texts, use the regular endpoint
    which has a 10-minute timeout for CPU mode.
    """
    return jsonify({
        'success': False,
        'error': 'Async mode not available. Use /api/generate-premium for all requests. CPU mode may take 30-60 seconds.'
    }), 501


@app.route('/api/premium-status/<job_id>')
@login_required
def api_premium_status(job_id):
    """Job status - not needed (sync only)"""
    return jsonify({
        'success': False,
        'error': 'Job status not available. Ultra TTS processes requests synchronously.'
    }), 501


@app.route('/api/premium-voices')
def api_premium_voices():
    """Get available speaker presets for Ultra Voices"""
    voices = [
        {'id': '1', 'name': 'Speaker 1 (Calm)', 'exaggeration': 0.3, 'description': 'Calm, neutral tone'},
        {'id': '2', 'name': 'Speaker 2 (Moderate)', 'exaggeration': 0.5, 'description': 'Balanced expression'},
        {'id': '3', 'name': 'Speaker 3 (Expressive)', 'exaggeration': 0.7, 'description': 'More emotional range'},
        {'id': '4', 'name': 'Speaker 4', 'exaggeration': 0.4, 'description': 'Slightly expressive'},
        {'id': '5', 'name': 'Speaker 5', 'exaggeration': 0.6, 'description': 'Expressive'},
        {'id': '6', 'name': 'Speaker 6', 'exaggeration': 0.35, 'description': 'Calm'},
        {'id': '7', 'name': 'Speaker 7', 'exaggeration': 0.55, 'description': 'Moderate'},
        {'id': '8', 'name': 'Speaker 8', 'exaggeration': 0.65, 'description': 'Expressive'},
    ]
    
    return jsonify({
        'success': True,
        'voices': voices,
        'multi_speaker_format': {
            'description': 'Use [S1]: [S2]: tags for multi-speaker dialogue',
            'example': '[S1]: Hello! How are you? [S2]: I am doing great, thanks for asking!',
            'supported_speakers': ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8']
        },
        'exaggeration': {
            'description': 'Controls emotional expressiveness (0.0 = flat, 1.0 = very expressive)',
            'default': 0.5,
            'range': [0.0, 1.0]
        }
    })


# ==================== IndexTTS2 API Endpoints ====================

def generate_indextts_audio(text, voice, emo_vector=None, use_random=False):
    """
    Call the IndexTTS2 server /generate endpoint.
    Returns audio bytes (WAV) or raises exception.
    
    Parameters:
    - text: The text to synthesize
    - voice: Voice name (e.g., 'Emily', 'Michael')
    - emo_vector: [happy, angry, sad, afraid, disgusted, melancholic, surprised, calm]
    - use_random: Enable stochastic sampling
    """
    payload = {
        'text': text,
        'voice': voice,
        'use_random': use_random
    }
    
    if emo_vector:
        payload['emo_vector'] = emo_vector
    
    print(f"[IndexTTS2] Generating: voice={voice}, text_len={len(text)}, emo_vector={emo_vector is not None}")
    
    response = requests.post(
        f'{INDEXTTS_URL}/generate',
        json=payload,
        timeout=300,  # 5 min timeout
        stream=True
    )
    
    if response.status_code != 200:
        error_msg = 'Unknown error'
        try:
            error_msg = response.json().get('detail', response.text[:200])
        except:
            error_msg = response.text[:200] if response.text else f'HTTP {response.status_code}'
        raise Exception(f'IndexTTS2 error: {error_msg}')
    
    return response.content


def generate_indextts_batch(segments, silence_ms=200):
    """
    Call the IndexTTS2 server /batch-generate endpoint.
    Much faster for multi-segment generation.
    
    Parameters:
    - segments: List of {text, voice, emo_vector}
    - silence_ms: Silence between segments
    
    Returns audio bytes (WAV) or raises exception.
    """
    payload = {
        'segments': segments,
        'silence_ms': silence_ms,
        'crossfade_ms': 30
    }
    
    print(f"[IndexTTS2] Batch generating {len(segments)} segments...")
    
    response = requests.post(
        f'{INDEXTTS_URL}/batch-generate',
        json=payload,
        timeout=600,  # 10 min timeout for batch
        stream=True
    )
    
    if response.status_code != 200:
        error_msg = 'Unknown error'
        try:
            error_msg = response.json().get('detail', response.text[:200])
        except:
            error_msg = response.text[:200] if response.text else f'HTTP {response.status_code}'
        raise Exception(f'IndexTTS2 batch error: {error_msg}')
    
    gen_time = response.headers.get('X-Generation-Time', 'unknown')
    audio_duration = response.headers.get('X-Audio-Duration', 'unknown')
    print(f"[IndexTTS2] Batch done: gen_time={gen_time}s, audio_duration={audio_duration}s")
    
    return response.content


@app.route('/api/indextts/voices', methods=['GET'])
def api_indextts_voices():
    """
    Get available IndexTTS2 voices from the server.
    """
    try:
        if not INDEXTTS_URL:
            return jsonify({
                'success': False,
                'error': 'IndexTTS2 service is not configured.'
            }), 503
        
        response = requests.get(f'{INDEXTTS_URL}/voices', timeout=30)
        if response.status_code == 200:
            data = response.json()
            return jsonify({
                'success': True,
                'voices': data.get('voices', []),
                'count': data.get('count', 0),
                'cached_count': data.get('cached_count', 0)
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Failed to fetch voices: HTTP {response.status_code}'
            }), 500
    except requests.Timeout:
        return jsonify({
            'success': False,
            'error': 'IndexTTS2 service is not responding.'
        }), 504
    except Exception as e:
        print(f"[IndexTTS2] Error fetching voices: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/indextts/generate', methods=['POST'])
@login_required
@csrf.exempt
def api_indextts_generate():
    """
    Generate audio using IndexTTS2.
    Supports:
    - Single voice generation
    - Emotion control via emo_alpha, emo_text, or emo_vector
    - Multi-speaker dialogue with [Emily]: [Michael]: format
    
    Requires IndexTTS2 subscription tier.
    """
    import re
    
    try:
        # Check if IndexTTS2 is configured
        if not INDEXTTS_URL:
            return jsonify({
                'success': False,
                'error': 'IndexTTS2 service is not configured. Please contact support.'
            }), 503
        
        data = request.get_json(silent=True) or {}
        
        text = (data.get('text', '') or '').strip()
        voice = data.get('voice', 'Emily')
        emo_vector = data.get('emo_vector')  # Global emotion vector (for non-chunked)
        use_random = bool(data.get('use_random', False))
        
        # Support for pre-chunked segments with per-chunk emotions
        # Each segment: { voice, text, emo_vector (optional) }
        pre_segments = data.get('segments')
        
        if not text and not pre_segments:
            return jsonify({'success': False, 'error': 'No text provided'}), 400
        
        # Calculate character count
        if pre_segments:
            char_count = sum(len(s.get('text', '')) for s in pre_segments)
        else:
            plain_text = re.sub(r'\[([\w]+)\]:\s*', '', text)
            char_count = len(plain_text)
        
        if char_count > 100000:
            return jsonify({'success': False, 'error': 'Text too long (max 100,000 chars)'}), 400
        
        # Check IndexTTS2 subscription and usage
        if not current_user.has_indextts:
            return jsonify({
                'success': False,
                'error': 'IndexTTS2 subscription required. Upgrade for high-quality voice cloning.',
                'upgrade_url': '/subscribe',
                'indextts_required': True
            }), 402
        
        # Check and track usage
        success, error_msg = current_user.use_indextts_chars(char_count)
        if not success:
            return jsonify({
                'success': False,
                'error': error_msg,
                'limit_reached': True,
                'indextts_chars_used': current_user.indextts_chars_used or 0,
                'indextts_chars_limit': current_user.indextts_char_limit,
                'indextts_chars_remaining': current_user.indextts_chars_remaining,
                'upgrade_url': '/subscribe'
            }), 402
        
        db.session.commit()
        
        # Build segments list
        segments = []
        
        if pre_segments:
            # Use pre-chunked segments with per-chunk emotions
            for seg in pre_segments:
                seg_voice = seg.get('voice', voice)
                seg_text = (seg.get('text', '') or '').strip()
                seg_emo_vector = seg.get('emo_vector')  # Per-chunk emotion
                if seg_text:
                    segments.append({
                        'voice': seg_voice,
                        'text': seg_text,
                        'emo_vector': seg_emo_vector
                    })
        else:
            # Parse multi-speaker segments [Emily]: [Michael]: format
            speaker_pattern = r'\[(\w+)\]:\s*'
            parts = re.split(speaker_pattern, text)
            
            # First part before any tag
            if parts[0].strip():
                segments.append({
                    'voice': voice,
                    'text': parts[0].strip(),
                    'emo_vector': emo_vector
                })
            
            # Process speaker:text pairs
            for i in range(1, len(parts), 2):
                speaker_voice = parts[i]
                if i + 1 < len(parts):
                    seg_text = parts[i + 1].strip()
                    if seg_text:
                        segments.append({
                            'voice': speaker_voice,
                            'text': seg_text,
                            'emo_vector': emo_vector
                        })
        
        # If no segments parsed, treat as single-voice
        if not segments:
            segments = [{'voice': voice, 'text': text, 'emo_vector': emo_vector}]
        
        has_multiple_speakers = len(set(s['voice'] for s in segments)) > 1
        
        print(f"[IndexTTS2] Processing {len(segments)} segments, multi-speaker={has_multiple_speakers}")
        
        # Use batch endpoint for multiple segments (much faster)
        if len(segments) > 1:
            try:
                print(f"[IndexTTS2] Using batch generation for {len(segments)} segments")
                
                # Prepare batch request
                batch_segments = []
                for seg in segments:
                    batch_segments.append({
                        'text': seg['text'],
                        'voice': seg['voice'],
                        'emo_vector': seg.get('emo_vector')
                    })
                
                silence_ms = 300 if has_multiple_speakers else 150
                final_audio = generate_indextts_batch(batch_segments, silence_ms=silence_ms)
                
                segment_stats = [{'voice': s['voice'], 'chars': len(s['text'])} for s in segments]
                
            except Exception as e:
                print(f"[IndexTTS2] Batch generation failed: {e}, falling back to sequential")
                # Fallback to sequential generation
                final_audio = None
        else:
            final_audio = None
        
        # Sequential generation (single segment or batch fallback)
        if final_audio is None:
            audio_chunks = []
            segment_stats = []
            
            for idx, seg in enumerate(segments):
                seg_voice = seg['voice']
                seg_text = seg['text']
                seg_emo_vector = seg.get('emo_vector')
                
                print(f"[IndexTTS2] Segment {idx+1}/{len(segments)}: Voice={seg_voice}, {len(seg_text)} chars")
                
                try:
                    audio_data = generate_indextts_audio(
                        text=seg_text,
                        voice=seg_voice,
                        emo_vector=seg_emo_vector,
                        use_random=use_random
                    )
                    audio_chunks.append(audio_data)
                    segment_stats.append({
                        'voice': seg_voice,
                        'chars': len(seg_text),
                        'audio_size': len(audio_data)
                    })
                except Exception as e:
                    print(f"[IndexTTS2] Segment {idx+1} failed: {e}")
                    # Rollback usage
                    current_user.indextts_chars_used = max(0, (current_user.indextts_chars_used or 0) - char_count)
                    db.session.commit()
                    return jsonify({
                        'success': False,
                        'error': f'Failed to generate segment {idx+1}: {str(e)}'
                    }), 500
            
            # Concatenate audio chunks
            if len(audio_chunks) > 1:
                print(f"[IndexTTS2] Concatenating {len(audio_chunks)} audio chunks...")
                if has_multiple_speakers:
                    final_audio = concatenate_wav_files_with_crossfade(audio_chunks, crossfade_ms=30, silence_ms=300)
                else:
                    final_audio = concatenate_wav_files_with_crossfade(audio_chunks, crossfade_ms=40, silence_ms=100)
            else:
                final_audio = audio_chunks[0] if audio_chunks else b''
        else:
            final_audio = audio_chunks[0] if audio_chunks else b''
        
        if not final_audio:
            return jsonify({
                'success': False,
                'error': 'No audio data generated'
            }), 500
        
        # Save the audio file
        file_hash = hashlib.md5(f"indextts:{voice}:{text[:50]}:{time.time()}".encode()).hexdigest()[:12]
        output_file = OUTPUT_DIR / f"indextts_{file_hash}.wav"
        
        with open(output_file, 'wb') as f:
            f.write(final_audio)
        
        print(f"[IndexTTS2] Saved {output_file.name}, {len(final_audio)} bytes")
        
        return jsonify({
            'success': True,
            'audioUrl': f'/api/audio/{output_file.name}',
            'stats': {
                'total_chars': char_count,
                'segments': len(segments),
                'multi_speaker': has_multiple_speakers,
                'segment_details': segment_stats,
                'audio_size': len(final_audio)
            },
            'indextts_chars_used': current_user.indextts_chars_used or 0,
            'indextts_chars_limit': current_user.indextts_char_limit,
            'indextts_chars_remaining': current_user.indextts_chars_remaining
        })
        
    except requests.Timeout:
        return jsonify({
            'success': False,
            'error': 'IndexTTS2 generation timed out. Please try with shorter text.'
        }), 504
    except Exception as e:
        print(f"[IndexTTS2 ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/indextts/preview', methods=['POST'])
@csrf.exempt
@limiter.limit("10 per minute")
def api_indextts_preview():
    """
    Preview IndexTTS2 voice (max 100 chars, no auth required).
    """
    try:
        if not INDEXTTS_URL:
            return jsonify({
                'success': False,
                'error': 'IndexTTS2 service is not configured.'
            }), 503
        
        data = request.get_json(silent=True) or {}
        
        text = (data.get('text', '') or '').strip()
        voice = data.get('voice', 'Emily')
        emo_alpha = float(data.get('emo_alpha', 0.6))
        
        if not text:
            return jsonify({'success': False, 'error': 'No text provided'}), 400
        
        # Limit preview to 100 characters
        if len(text) > 100:
            text = text[:100]
        
        print(f"[IndexTTS2 Preview] Voice={voice}, Text: {text[:30]}...")
        
        try:
            audio_data = generate_indextts_audio(
                text=text,
                voice=voice,
                emo_alpha=emo_alpha
            )
            
            # Save preview file
            file_hash = hashlib.md5(f"indextts_preview:{text[:20]}:{time.time()}".encode()).hexdigest()[:12]
            output_file = OUTPUT_DIR / f"indextts_preview_{file_hash}.wav"
            
            with open(output_file, 'wb') as f:
                f.write(audio_data)
            
            return jsonify({
                'success': True,
                'audioUrl': f'/api/audio/{output_file.name}'
            })
            
        except Exception as e:
            print(f"[IndexTTS2 Preview ERROR] {e}")
            return jsonify({
                'success': False,
                'error': f'Preview failed: {str(e)}'
            }), 500
            
    except Exception as e:
        print(f"[IndexTTS2 Preview ERROR] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/indextts/health', methods=['GET'])
def api_indextts_health():
    """Check IndexTTS2 server health."""
    try:
        if not INDEXTTS_URL:
            return jsonify({
                'success': False,
                'status': 'not_configured'
            })
        
        response = requests.get(f'{INDEXTTS_URL}/health', timeout=10)
        if response.status_code == 200:
            data = response.json()
            return jsonify({
                'success': True,
                'status': data.get('status', 'unknown'),
                'model_loaded': data.get('model_loaded', False),
                'cached_voices': data.get('cached_voices', 0)
            })
        else:
            return jsonify({
                'success': False,
                'status': 'unhealthy'
            }), 503
    except Exception as e:
        return jsonify({
            'success': False,
            'status': 'unreachable',
            'error': str(e)
        }), 503


# ==================== VibeVoice API Endpoints ====================

def generate_vibevoice_audio(text, voice, cfg_scale=1.5, inference_steps=5):
    """
    Call the Podcast TTS server /generate endpoint.
    Returns audio bytes (WAV) or raises exception.
    
    Parameters:
    - text: The text to synthesize
    - voice: Voice name (e.g., 'Wayne', 'Carter')
    - cfg_scale: Classifier-free guidance scale (default 1.5)
    - inference_steps: Diffusion steps (default 5 for realtime)
    """
    payload = {
        'text': text,
        'voice': voice,
        'cfg_scale': cfg_scale,
        'inference_steps': inference_steps
    }
    
    print(f"[VibeVoice] Generating: voice={voice}, text_len={len(text)}, cfg={cfg_scale}")
    
    response = requests.post(
        f'{VIBEVOICE_URL}/generate',
        json=payload,
        timeout=600,  # 10 min timeout for long-form
        stream=True
    )
    
    if response.status_code != 200:
        error_msg = 'Unknown error'
        try:
            error_msg = response.json().get('detail', response.text[:200])
        except:
            error_msg = response.text[:200] if response.text else f'HTTP {response.status_code}'
        raise Exception(f'VibeVoice error: {error_msg}')
    
    return response.content


def generate_vibevoice_batch(segments, silence_ms=300):
    """
    Call the Podcast TTS server /batch-generate endpoint.
    Much faster for multi-segment generation.
    
    Parameters:
    - segments: List of {text, voice}
    - silence_ms: Silence between segments
    
    Returns audio bytes (WAV) or raises exception.
    """
    payload = {
        'segments': segments,
        'silence_ms': silence_ms,
        'crossfade_ms': 30
    }
    
    print(f"[VibeVoice] Batch generating {len(segments)} segments...")
    
    response = requests.post(
        f'{VIBEVOICE_URL}/batch-generate',
        json=payload,
        timeout=900,  # 15 min timeout for batch
        stream=True
    )
    
    if response.status_code != 200:
        error_msg = 'Unknown error'
        try:
            error_msg = response.json().get('detail', response.text[:200])
        except:
            error_msg = response.text[:200] if response.text else f'HTTP {response.status_code}'
        raise Exception(f'VibeVoice batch error: {error_msg}')
    
    gen_time = response.headers.get('X-Generation-Time', 'unknown')
    audio_duration = response.headers.get('X-Audio-Duration', 'unknown')
    print(f"[VibeVoice] Batch done: gen_time={gen_time}s, audio_duration={audio_duration}s")
    
    return response.content


@app.route('/api/vibevoice/voices', methods=['GET'])
def api_vibevoice_voices():
    """
    Get available Podcast TTS voices from the server.
    """
    try:
        if not VIBEVOICE_URL:
            return jsonify({
                'success': False,
                'error': 'Podcast TTS service is not configured.'
            }), 503
        
        response = requests.get(f'{VIBEVOICE_URL}/voices', timeout=30)
        if response.status_code == 200:
            data = response.json()
            return jsonify({
                'success': True,
                'voices': data.get('voices', []),
                'count': data.get('count', 0),
                'default': data.get('default')
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Failed to fetch voices: HTTP {response.status_code}'
            }), 500
    except requests.Timeout:
        return jsonify({
            'success': False,
            'error': 'VibeVoice service is not responding.'
        }), 504
    except Exception as e:
        print(f"[VibeVoice] Error fetching voices: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/vibevoice/generate', methods=['POST'])
@login_required
@csrf.exempt
def api_vibevoice_generate():
    """
    Generate audio using Podcast TTS.
    Supports:
    - Single voice generation
    - Multi-speaker dialogue
    
    Requires Podcast TTS subscription tier.
    """
    import re
    
    try:
        # Check if Podcast TTS is configured
        if not VIBEVOICE_URL:
            return jsonify({
                'success': False,
                'error': 'Podcast TTS service is not configured. Please contact support.'
            }), 503
        
        data = request.get_json(silent=True) or {}
        
        text = (data.get('text', '') or '').strip()
        voice = data.get('voice', 'Wayne')
        cfg_scale = float(data.get('cfg_scale', 1.5))
        inference_steps = int(data.get('inference_steps', 5))
        
        # Support for pre-chunked segments
        pre_segments = data.get('segments')
        
        if not text and not pre_segments:
            return jsonify({'success': False, 'error': 'No text provided'}), 400
        
        # Calculate character count
        if pre_segments:
            char_count = sum(len(s.get('text', '')) for s in pre_segments)
        else:
            # Remove speaker tags for counting
            plain_text = re.sub(r'\[[\w]+\]:\s*', '', text)
            char_count = len(plain_text)
        
        if char_count > 200000:
            return jsonify({'success': False, 'error': 'Text too long (max 200,000 chars)'}), 400
        
        # Check VibeVoice subscription and usage
        if not current_user.has_vibevoice:
            return jsonify({
                'success': False,
                'error': 'VibeVoice subscription required. Upgrade for frontier-quality long-form TTS.',
                'upgrade_url': '/subscribe',
                'vibevoice_required': True
            }), 402
        
        # Check and track usage
        success, error_msg = current_user.use_vibevoice_chars(char_count)
        if not success:
            return jsonify({
                'success': False,
                'error': error_msg,
                'limit_reached': True,
                'vibevoice_chars_used': current_user.vibevoice_chars_used or 0,
                'vibevoice_chars_limit': current_user.vibevoice_char_limit,
                'vibevoice_chars_remaining': current_user.vibevoice_chars_remaining,
                'upgrade_url': '/subscribe'
            }), 402
        
        db.session.commit()
        
        # Build segments list
        segments = []
        
        if pre_segments:
            # Use pre-chunked segments
            for seg in pre_segments:
                seg_voice = seg.get('voice', voice)
                seg_text = (seg.get('text', '') or '').strip()
                if seg_text:
                    segments.append({
                        'voice': seg_voice,
                        'text': seg_text
                    })
        else:
            # Parse multi-speaker segments [Wayne]: [Carter]: format
            speaker_pattern = r'\[(\w+)\]:\s*'
            parts = re.split(speaker_pattern, text)
            
            # First part before any tag
            if parts[0].strip():
                segments.append({
                    'voice': voice,
                    'text': parts[0].strip()
                })
            
            # Process speaker:text pairs
            for i in range(1, len(parts), 2):
                speaker_voice = parts[i]
                if i + 1 < len(parts):
                    seg_text = parts[i + 1].strip()
                    if seg_text:
                        segments.append({
                            'voice': speaker_voice,
                            'text': seg_text
                        })
        
        # If no segments parsed, treat as single-voice
        if not segments:
            segments = [{'voice': voice, 'text': text}]
        
        has_multiple_speakers = len(set(s['voice'] for s in segments)) > 1
        
        print(f"[VibeVoice] Processing {len(segments)} segments, multi-speaker={has_multiple_speakers}")
        
        # Use batch endpoint for multiple segments
        if len(segments) > 1:
            try:
                print(f"[VibeVoice] Using batch generation for {len(segments)} segments")
                
                batch_segments = []
                for seg in segments:
                    batch_segments.append({
                        'text': seg['text'],
                        'voice': seg['voice']
                    })
                
                silence_ms = 400 if has_multiple_speakers else 200
                final_audio = generate_vibevoice_batch(batch_segments, silence_ms=silence_ms)
                
                segment_stats = [{'voice': s['voice'], 'chars': len(s['text'])} for s in segments]
                
            except Exception as e:
                print(f"[VibeVoice] Batch generation failed: {e}, falling back to sequential")
                final_audio = None
        else:
            final_audio = None
        
        # Sequential generation (single segment or batch fallback)
        if final_audio is None:
            audio_chunks = []
            segment_stats = []
            
            for idx, seg in enumerate(segments):
                seg_voice = seg['voice']
                seg_text = seg['text']
                
                print(f"[VibeVoice] Segment {idx+1}/{len(segments)}: Voice={seg_voice}, {len(seg_text)} chars")
                
                try:
                    audio_data = generate_vibevoice_audio(
                        text=seg_text,
                        voice=seg_voice,
                        cfg_scale=cfg_scale,
                        inference_steps=inference_steps
                    )
                    audio_chunks.append(audio_data)
                    segment_stats.append({
                        'voice': seg_voice,
                        'chars': len(seg_text),
                        'audio_size': len(audio_data)
                    })
                except Exception as e:
                    print(f"[VibeVoice] Segment {idx+1} failed: {e}")
                    # Rollback usage
                    current_user.vibevoice_chars_used = max(0, (current_user.vibevoice_chars_used or 0) - char_count)
                    db.session.commit()
                    return jsonify({
                        'success': False,
                        'error': f'Failed to generate segment {idx+1}: {str(e)}'
                    }), 500
            
            # Concatenate audio chunks
            if len(audio_chunks) > 1:
                print(f"[VibeVoice] Concatenating {len(audio_chunks)} audio chunks...")
                if has_multiple_speakers:
                    final_audio = concatenate_wav_files_with_crossfade(audio_chunks, crossfade_ms=30, silence_ms=400)
                else:
                    final_audio = concatenate_wav_files_with_crossfade(audio_chunks, crossfade_ms=40, silence_ms=150)
            else:
                final_audio = audio_chunks[0] if audio_chunks else b''
        
        if not final_audio:
            return jsonify({
                'success': False,
                'error': 'No audio data generated'
            }), 500
        
        # Save the audio file
        file_hash = hashlib.md5(f"vibevoice:{voice}:{text[:50]}:{time.time()}".encode()).hexdigest()[:12]
        output_file = OUTPUT_DIR / f"vibevoice_{file_hash}.wav"
        
        with open(output_file, 'wb') as f:
            f.write(final_audio)
        
        print(f"[VibeVoice] Saved {output_file.name}, {len(final_audio)} bytes")
        
        return jsonify({
            'success': True,
            'audioUrl': f'/api/audio/{output_file.name}',
            'stats': {
                'total_chars': char_count,
                'segments': len(segments),
                'multi_speaker': has_multiple_speakers,
                'segment_details': segment_stats,
                'audio_size': len(final_audio)
            },
            'vibevoice_chars_used': current_user.vibevoice_chars_used or 0,
            'vibevoice_chars_limit': current_user.vibevoice_char_limit,
            'vibevoice_chars_remaining': current_user.vibevoice_chars_remaining
        })
        
    except requests.Timeout:
        return jsonify({
            'success': False,
            'error': 'VibeVoice generation timed out. Please try with shorter text.'
        }), 504
    except Exception as e:
        print(f"[VibeVoice ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/vibevoice/preview', methods=['POST'])
@login_required
@csrf.exempt
def api_vibevoice_preview():
    """Preview a Podcast voice (short sample, no usage tracking)."""
    try:
        if not VIBEVOICE_URL:
            return jsonify({
                'success': False,
                'error': 'Podcast TTS service is not configured.'
            }), 503
        
        data = request.get_json(silent=True) or {}
        voice = data.get('voice', 'Wayne')
        
        # Use the server's preview endpoint
        try:
            response = requests.get(
                f'{VIBEVOICE_URL}/preview/{voice}',
                timeout=60
            )
            
            if response.status_code == 200:
                # Save preview file
                file_hash = hashlib.md5(f"vibevoice_preview:{voice}:{time.time()}".encode()).hexdigest()[:12]
                output_file = OUTPUT_DIR / f"vibevoice_preview_{file_hash}.wav"
                
                with open(output_file, 'wb') as f:
                    f.write(response.content)
                
                return jsonify({
                    'success': True,
                    'audioUrl': f'/api/audio/{output_file.name}'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': f'Preview failed: HTTP {response.status_code}'
                }), 500
                
        except Exception as e:
            print(f"[VibeVoice Preview ERROR] {e}")
            return jsonify({
                'success': False,
                'error': f'Preview failed: {str(e)}'
            }), 500
            
    except Exception as e:
        print(f"[VibeVoice Preview ERROR] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/vibevoice/health', methods=['GET'])
def api_vibevoice_health():
    """Check VibeVoice server health."""
    try:
        if not VIBEVOICE_URL:
            return jsonify({
                'success': False,
                'status': 'not_configured'
            })
        
        response = requests.get(f'{VIBEVOICE_URL}/health', timeout=10)
        if response.status_code == 200:
            data = response.json()
            return jsonify({
                'success': True,
                'status': data.get('status', 'unknown'),
                'model_loaded': data.get('model_loaded', False),
                'voices_loaded': data.get('voices_loaded', 0)
            })
        else:
            return jsonify({
                'success': False,
                'status': 'unhealthy'
            }), 503
    except Exception as e:
        return jsonify({
            'success': False,
            'status': 'unreachable',
            'error': str(e)
        }), 503


@app.route('/api/audio/<filename>')
def api_audio(filename):
    """Serve audio file (public for previews)"""
    try:
        file_path = OUTPUT_DIR / filename
        if file_path.exists():
            # Determine correct mimetype based on extension
            if filename.endswith('.wav'):

                mimetype = 'audio/wav'
            elif filename.endswith('.mp3'):
                mimetype = 'audio/mpeg'
            elif filename.endswith('.ogg'):
                mimetype = 'audio/ogg'
            else:
                mimetype = 'audio/mpeg'
            
            # Add cache headers for faster playback
            response = send_file(file_path, mimetype=mimetype)
            response.headers['Accept-Ranges'] = 'bytes'
            response.headers['Cache-Control'] = 'public, max-age=3600'
            return response
        else:
            return jsonify({'success': False, 'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/srt/<filename>')
def api_srt(filename):
    """Serve SRT subtitle file"""
    try:
        file_path = OUTPUT_DIR / filename
        if file_path.exists():
            return send_file(file_path, mimetype='text/plain', as_attachment=True, download_name=filename)
        else:
            return jsonify({'success': False, 'error': 'SRT file not found'}), 404
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


# ============================================
# MOBILE APP API ENDPOINTS
# ============================================

@app.route('/api/v1/auth/login', methods=['POST'])
@csrf.exempt  # API endpoint - no CSRF needed
@limiter.limit("10 per minute")
def api_auth_login():
    """
    Mobile app login endpoint
    
    Body (JSON):
        {
            "email": "user@example.com",
            "password": "password123"
        }
    
    Returns:
        {
            "success": true,
            "user": {
                "id": 1,
                "email": "user@example.com",
                "is_subscriber": true,
                "subscription_tier": "lifetime",
                "api_tier": "enterprise",
                "api_chars_remaining": 10000000
            },
            "token": "session_token_here"
        }
    """
    try:
        data = request.get_json(silent=True) or {}
        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''
        
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password required'}), 400
        
        user = User.query.filter_by(email=email).first()
        
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
        
        # Generate a simple session token
        session_token = secrets.token_urlsafe(32)
        
        # Try to save session token (may fail if columns don't exist yet)
        try:
            user.mobile_session_token = session_token
            user.mobile_session_expires = datetime.utcnow() + timedelta(days=30)
            # Also reset usage if needed
            user.check_and_reset_usage()
            db.session.commit()
        except Exception as db_err:
            print(f"[API Auth] Could not save session token (migration pending): {db_err}")
            db.session.rollback()
            # Continue anyway - token won't persist but login will work
        
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'email': user.email,
                'is_subscribed': user.is_subscribed,
                'subscription_status': user.subscription_status,
                'api_tier': user.api_tier,
                'api_chars_remaining': user.api_chars_remaining if user.api_tier else 0,
                # Character usage info for web/mobile
                'chars_used': user.chars_used or 0,
                'chars_limit': user.char_limit,
                'chars_remaining': user.chars_remaining,
            },
            'token': session_token
        })
        
    except Exception as e:
        import traceback
        print(f"[API Auth] Login error: {e}")
        print(f"[API Auth] Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500


@app.route('/api/v1/auth/signup', methods=['POST'])
@csrf.exempt
@limiter.limit("5 per hour")
def api_auth_signup():
    """
    Mobile app signup endpoint
    """
    try:
        data = request.get_json(silent=True) or {}
        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''
        
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password required'}), 400
        
        if len(password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
        
        # Check if user exists
        existing = User.query.filter_by(email=email).first()
        if existing:
            return jsonify({'success': False, 'error': 'Email already registered'}), 409
        
        # Create user
        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            subscription_status='inactive'
        )
        db.session.add(user)
        db.session.commit()
        
        # Auto-login
        session_token = secrets.token_urlsafe(32)
        user.mobile_session_token = session_token
        user.mobile_session_expires = datetime.utcnow() + timedelta(days=30)
        # Initialize character usage
        user.chars_used = 0
        user.chars_reset_at = datetime.utcnow() + timedelta(days=30)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'email': user.email,
                'is_subscriber': False,
                'subscription_status': 'inactive',
                'api_tier': None,
                'api_chars_remaining': 0,
                # Character usage info
                'chars_used': 0,
                'chars_limit': User.FREE_CHAR_LIMIT,
                'chars_remaining': User.FREE_CHAR_LIMIT,
            },
            'token': session_token
        })
        
    except Exception as e:
        print(f"[API Auth] Signup error: {e}")
        return jsonify({'success': False, 'error': 'Server error'}), 500


@app.route('/api/v1/auth/forgot-password', methods=['POST'])
@csrf.exempt
@limiter.limit("3 per hour")
def api_auth_forgot_password():
    """
    Mobile app forgot password endpoint
    """
    try:
        data = request.get_json(silent=True) or {}
        email = (data.get('email') or '').strip().lower()
        
        if not email:
            return jsonify({'success': False, 'error': 'Email required'}), 400
        
        user = User.query.filter_by(email=email).first()
        
        # Always return success to prevent email enumeration
        if user:
            # Generate reset token
            token = secrets.token_urlsafe(32)
            user.reset_token = token
            user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            
            # Send email (if configured)
            try:
                reset_url = f"https://cheaptts.com/reset-password?token={token}"
                send_password_reset_email(user.email, reset_url)
            except Exception as e:
                print(f"[API Auth] Failed to send reset email: {e}")
        
        return jsonify({
            'success': True,
            'message': 'If an account exists with that email, a reset link has been sent.'
        })
        
    except Exception as e:
        print(f"[API Auth] Forgot password error: {e}")
        return jsonify({'success': False, 'error': 'Server error'}), 500


@app.route('/api/v1/auth/me', methods=['GET'])
@csrf.exempt
def api_auth_me():
    """
    Get current user info from mobile session token
    """
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not token:
        return jsonify({'success': False, 'error': 'No token provided'}), 401
    
    user = User.query.filter_by(mobile_session_token=token).first()
    
    if not user or (user.mobile_session_expires and user.mobile_session_expires < datetime.utcnow()):
        return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
    
    # Reset usage if needed
    user.check_and_reset_usage()
    
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'email': user.email,
            'is_subscribed': user.is_subscribed,
            'subscription_status': user.subscription_status,
            'api_tier': user.api_tier,
            'api_chars_remaining': user.api_chars_remaining if user.api_tier else 0,
            'chars_used': user.chars_used or 0,
            'chars_limit': user.char_limit,
            'chars_remaining': user.chars_remaining,
        }
    })


@app.route('/api/v1/auth/logout', methods=['POST'])
@csrf.exempt
def api_auth_logout():
    """
    Mobile app logout - invalidate session token
    """
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if token:
        user = User.query.filter_by(mobile_session_token=token).first()
        if user:
            user.mobile_session_token = None
            user.mobile_session_expires = None
            db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/v1/mobile/synthesize', methods=['POST'])
@csrf.exempt
@limiter.limit("200 per hour")  # Higher limit for mobile app users
def api_mobile_synthesize():
    """
    Mobile app text-to-speech synthesis endpoint
    Uses session token instead of API key
    
    Headers:
        Authorization: Bearer <session_token>
    
    Body (JSON) - Single voice mode:
        {
            "text": "Text to convert to speech",
            "voice": "en-US-AriaNeural",
            "rate": 0,
            "pitch": 0,
            "style": "cheerful" (optional - for emotional voices),
            "style_degree": 1.0 (optional - 0.0 to 2.0),
            "chunk_mode": false (optional - for long text)
        }
    
    Body (JSON) - Multi-speaker dialogue mode:
        {
            "voice": "en-US-AriaNeural",  // global voice fallback
            "chunks": [
                {
                    "content": "Hello there!",
                    "voice": "en-US-GuyNeural",  // optional override
                    "emotion": "cheerful",  // optional
                    "intensity": 2,  // 1-3 scale
                    "speed": 0,  // -50 to +50
                    "pitch": 0,  // -50 to +50
                    "volume": 0  // -50 to +50
                },
                ...
            ],
            "global_controls": {"rate": 0, "pitch": 0, "volume": 0},
            "auto_pauses": true,
            "auto_emphasis": true,
            "auto_breaths": false
        }
    """
    import re
    import traceback

    # Authenticate with session token
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not token:
        return jsonify({'success': False, 'error': 'No token provided'}), 401
    
    try:
        user = User.query.filter_by(mobile_session_token=token).first()
    except Exception as e:
        # Fallback if mobile_session_token column doesn't exist yet
        print(f"[Mobile API] Token lookup failed (migration pending?): {e}")
        return jsonify({'success': False, 'error': 'Authentication system not ready. Please try again later.'}), 503
    
    if not user or (user.mobile_session_expires and user.mobile_session_expires < datetime.utcnow()):
        return jsonify({'success': False, 'error': 'Invalid or expired token. Please login again.'}), 401
    
    try:
        data = request.get_json(silent=True) or {}
        voice = data.get('voice', 'en-US-AriaNeural')
        chunks = data.get('chunks')
        
        # --- Multi-speaker dialogue mode (chunks array) ---
        if chunks is not None:
            if not isinstance(chunks, list) or not chunks:
                return jsonify({'success': False, 'error': 'chunks must be a non-empty list'}), 400
            
            # Calculate total character count
            total_chars = 0
            for chunk in chunks:
                content = chunk.get('content', '')
                plain_text = re.sub(r'<[^>]+>', '', content)
                total_chars += len(plain_text)
            
            if total_chars > 10000:
                return jsonify({'success': False, 'error': 'Total text too long. Maximum 10,000 characters per request.'}), 400
            
            # --- Enforce character limit ---
            success, error_msg = user.use_chars(total_chars)
            if not success:
                return jsonify({
                    'success': False,
                    'error': error_msg,
                    'limit_reached': True,
                    'chars_used': user.chars_used or 0,
                    'chars_limit': user.char_limit,
                    'chars_remaining': user.chars_remaining,
                    'upgrade_url': 'https://cheaptts.com/subscribe'
                }), 402  # Payment Required
            
            # Save character usage
            db.session.commit()
            
            print(f"[Mobile API] Multi-speaker request from {user.email}: {len(chunks)} chunks, {total_chars} chars")
            
            # Get global controls
            global_controls = data.get('global_controls', {})
            global_rate = global_controls.get('rate', 0)
            global_pitch = global_controls.get('pitch', 0)
            global_volume = global_controls.get('volume', 0)
            auto_pauses = data.get('auto_pauses', True)
            auto_emphasis = data.get('auto_emphasis', True)
            
            # Handle single chunk with emotion - use native style parameter
            if len(chunks) == 1:
                chunk = chunks[0]
                emotion = chunk.get('emotion')
                chunk_voice = chunk.get('voice') or voice
                
                if emotion:
                    import inspect

                    import edge_tts as tts_module
                    communicate_sig = inspect.signature(tts_module.Communicate.__init__)
                    supports_style = 'style' in communicate_sig.parameters
                    
                    if supports_style:
                        # Validate emotion against voice's StyleList
                        try:
                            voices_list = run_async(get_voices())
                            voice_obj = next((v for v in voices_list if v.get('ShortName') == chunk_voice), None)
                            supported_styles = set(voice_obj.get('StyleList', []) if voice_obj else [])
                            
                            if emotion and emotion not in supported_styles:
                                return jsonify({
                                    'success': False,
                                    'error': f"Style '{emotion}' is not supported by voice {chunk_voice}. Supported styles: {sorted(supported_styles) if supported_styles else 'none'}"
                                }), 400
                        except Exception as e:
                            print(f"[Mobile API] Style validation error: {e}")
                        
                        # Use native style parameter
                        plain_text = chunk.get('content', '')
                        intensity = chunk.get('intensity', 2)
                        style_degree = {1: 0.7, 2: 1.0, 3: 1.3}.get(intensity, 1.0)
                        
                        # Get prosody settings
                        chunk_rate = chunk.get('speed', global_rate)
                        chunk_pitch = chunk.get('pitch', global_pitch)
                        chunk_volume = chunk.get('volume', global_volume)
                        
                        # Format prosody values
                        rate_str = f"+{int(chunk_rate)}%" if chunk_rate >= 0 else f"{int(chunk_rate)}%"
                        pitch_str = f"+{int(chunk_pitch)}Hz" if chunk_pitch >= 0 else f"{int(chunk_pitch)}Hz"
                        volume_str = f"+{int(chunk_volume)}%" if chunk_volume >= 0 else f"{int(chunk_volume)}%"
                        
                        output_file = run_async(
                            generate_speech(
                                plain_text,
                                chunk_voice,
                                rate=rate_str,
                                volume=volume_str,
                                pitch=pitch_str,
                                is_ssml=False,
                                style=emotion,
                                style_degree=style_degree
                            )
                        )
                        
                        audio_url = request.url_root.rstrip('/') + f'/api/audio/{output_file.name}'
                        return jsonify({
                            'success': True,
                            'audio_url': audio_url,
                            'filename': output_file.name,
                            'chars_used': user.chars_used,  # Cumulative total this month
                            'chars_remaining': user.chars_remaining,
                            'chars_limit': user.char_limit,
                        })
            
            # Multi-voice SSML path
            sanitized_chunks = []
            try:
                voices_list = run_async(get_voices())
                voice_map = {
                    v.get('ShortName'): set(v.get('StyleList') or []) for v in voices_list
                }
            except Exception as e:
                print(f"[Mobile API] Voice validation error: {e}")
                voice_map = {}
            
            for chunk in chunks:
                chunk_copy = dict(chunk)
                chunk_voice = chunk_copy.get('voice') or voice
                chunk_copy['voice'] = chunk_voice
                
                # Validate emotion against voice's supported styles
                emotion = chunk_copy.get('emotion')
                supported_styles = voice_map.get(chunk_voice, set())
                if emotion and supported_styles and emotion not in supported_styles:
                    chunk_copy['emotion'] = None  # Clear unsupported emotion
                
                sanitized_chunks.append(chunk_copy)
            
            # Build SSML for multi-speaker dialogue
            ssml_result = build_ssml(
                voice=voice,
                chunks=sanitized_chunks,
                auto_pauses=auto_pauses,
                auto_emphasis=auto_emphasis,
            )
            ssml_text = ssml_result['ssml']
            is_full_ssml = ssml_result.get('is_full_ssml', False)
            
            # Use primary voice for synthesis
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
            
            return jsonify({
                'success': True,
                'audio_url': audio_url,
                'filename': output_file.name,
                'chars_used': user.chars_used,  # Cumulative total this month
                'chunks_processed': len(sanitized_chunks),
                'chars_remaining': user.chars_remaining,
                'chars_limit': user.char_limit,
            })
        
        # --- Single voice mode (text string) ---
        text = (data.get('text') or '').strip()
        
        if not text:
            return jsonify({'success': False, 'error': 'Text is required'}), 400
        
        if len(text) > 10000:
            return jsonify({'success': False, 'error': 'Text too long. Maximum 10,000 characters per request.'}), 400
        
        # --- Enforce character limit ---
        char_count = len(text)
        success, error_msg = user.use_chars(char_count)
        if not success:
            return jsonify({
                'success': False,
                'error': error_msg,
                'limit_reached': True,
                'chars_used': user.chars_used or 0,
                'chars_limit': user.char_limit,
                'chars_remaining': user.chars_remaining,
                'upgrade_url': 'https://cheaptts.com/subscribe'
            }), 402  # Payment Required
        
        # Save character usage
        db.session.commit()
        
        # Handle numeric rate/pitch from mobile (e.g., -50 to +50)
        rate_val = data.get('rate', 0)
        pitch_val = data.get('pitch', 0)
        
        if isinstance(rate_val, (int, float)):
            rate = f"+{int(rate_val)}%" if rate_val >= 0 else f"{int(rate_val)}%"
        else:
            rate = str(rate_val) if rate_val else '+0%'
            
        if isinstance(pitch_val, (int, float)):
            pitch = f"+{int(pitch_val)}Hz" if pitch_val >= 0 else f"{int(pitch_val)}Hz"
        else:
            pitch = str(pitch_val) if pitch_val else '+0Hz'
        
        volume = '+0%'
        
        # Style/emotion support
        style = data.get('style')
        style_degree = data.get('style_degree')
        
        if style_degree is not None:
            try:
                style_degree = float(style_degree)
                if not 0.0 <= style_degree <= 2.0:
                    style_degree = 1.0
            except:
                style_degree = 1.0
        
        # Chunk mode for long text
        chunk_mode = data.get('chunk_mode', False)
        
        print(f"[Mobile API] Synthesize request from {user.email}: voice={voice}, style={style}, chars={len(text)}")
        
        # Validate style against voice's supported styles
        if style:
            try:
                voices_list = run_async(get_voices())
                voice_obj = next((v for v in voices_list if v.get('ShortName') == voice), None)
                supported_styles = voice_obj.get('StyleList', []) if voice_obj else []
                
                if supported_styles and style not in supported_styles:
                    return jsonify({
                        'success': False,
                        'error': f"Style '{style}' not supported by {voice}. Available styles: {', '.join(sorted(supported_styles)) if supported_styles else 'none'}"
                    }), 400
            except Exception as e:
                print(f"[Mobile API] Style validation error: {e}")
                # Continue anyway
        
        # Generate speech
        output_file = run_async(
            generate_speech(
                text,
                voice,
                rate,
                volume,
                pitch,
                is_ssml=False,
                style=style,
                style_degree=style_degree
            )
        )
        
        # Return the audio URL
        audio_url = request.url_root.rstrip('/') + f'/api/audio/{output_file.name}'
        
        return jsonify({
            'success': True,
            'audio_url': audio_url,
            'filename': output_file.name,
            'chars_used': user.chars_used,  # Cumulative total this month
            'chars_remaining': user.chars_remaining,
            'chars_limit': user.char_limit,
        })
        
    except Exception as e:
        print(f"[Mobile API] Synthesize error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/v1/mobile/preview', methods=['POST'])
@csrf.exempt
@limiter.limit("30 per minute")
def api_mobile_preview():
    """
    Mobile app chunk preview endpoint - preview a single chunk before full generation
    Uses session token for authentication
    
    Headers:
        Authorization: Bearer <session_token>
    
    Body (JSON):
        {
            "voice": "en-US-AriaNeural",  // global voice
            "chunk": {
                "content": "Hello there!",
                "voice": "en-US-GuyNeural",  // optional override
                "emotion": "cheerful",  // optional
                "intensity": 2,  // 1-3 scale
                "speed": 0,  // -50 to +50
                "pitch": 0,  // -50 to +50
                "volume": 0  // -50 to +50
            },
            "global_rate": 0,
            "global_pitch": 0,
            "global_volume": 0
        }
    """
    import re
    import traceback

    # Authenticate with session token
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not token:
        return jsonify({'success': False, 'error': 'No token provided'}), 401
    
    try:
        user = User.query.filter_by(mobile_session_token=token).first()
    except Exception as e:
        print(f"[Mobile Preview] Token lookup failed: {e}")
        return jsonify({
            'success': False,
            'error': 'Authentication system not ready'
        }), 503
    
    if not user or (
        user.mobile_session_expires
        and user.mobile_session_expires < datetime.utcnow()
    ):
        return jsonify({
            'success': False,
            'error': 'Invalid or expired token'
        }), 401
    
    if not user.is_subscribed:
        return jsonify({
            'success': False,
            'error': 'Subscription required for mobile app'
        }), 403
    
    try:
        data = request.get_json(silent=True) or {}
        voice = data.get('voice', 'en-US-AriaNeural')
        chunk = data.get('chunk')
        
        if not chunk or not isinstance(chunk, dict):
            return jsonify({
                'success': False,
                'error': 'chunk object is required'
            }), 400
        
        content = chunk.get('content', '').strip()
        if not content:
            return jsonify({
                'success': False,
                'error': 'chunk content is required'
            }), 400
        
        # Limit preview to 300 characters
        if len(content) > 300:
            return jsonify({
                'success': False,
                'error': 'Preview limited to 300 characters'
            }), 400
        
        chunk_voice = chunk.get('voice') or voice
        emotion = chunk.get('emotion')
        intensity = chunk.get('intensity', 2)
        chunk_speed = chunk.get('speed', data.get('global_rate', 0))
        chunk_pitch = chunk.get('pitch', data.get('global_pitch', 0))
        chunk_volume = chunk.get('volume', data.get('global_volume', 0))
        
        print(f"[Mobile Preview] {user.email}: voice={chunk_voice}, emotion={emotion}")
        
        # If emotion is specified, use native style parameter
        if emotion:
            import inspect
            import edge_tts as tts_module

            communicate_sig = inspect.signature(tts_module.Communicate.__init__)
            supports_style = 'style' in communicate_sig.parameters
            
            if supports_style:
                # Validate emotion against voice
                try:
                    voices_list = run_async(get_voices())
                    voice_obj = next(
                        (v for v in voices_list if v.get('ShortName') == chunk_voice),
                        None
                    )
                    supported = set(voice_obj.get('StyleList', []) if voice_obj else [])
                    
                    if emotion not in supported:
                        return jsonify({
                            'success': False,
                            'error': f"Style '{emotion}' not supported by {chunk_voice}"
                        }), 400
                except Exception as e:
                    print(f"[Mobile Preview] Style validation error: {e}")
                
                style_degree = {1: 0.7, 2: 1.0, 3: 1.3}.get(intensity, 1.0)
                rate_str = f"+{int(chunk_speed)}%" if chunk_speed >= 0 else f"{int(chunk_speed)}%"
                pitch_str = f"+{int(chunk_pitch)}Hz" if chunk_pitch >= 0 else f"{int(chunk_pitch)}Hz"
                volume_str = f"+{int(chunk_volume)}%" if chunk_volume >= 0 else f"{int(chunk_volume)}%"
                
                cache_key = hashlib.md5(
                    f"mpreview:{chunk_voice}:{content}:{emotion}:{intensity}".encode()
                ).hexdigest()[:16]
                
                output_file = run_async(
                    generate_speech(
                        content,
                        chunk_voice,
                        rate=rate_str,
                        volume=volume_str,
                        pitch=pitch_str,
                        is_ssml=False,
                        cache_key=cache_key,
                        style=emotion,
                        style_degree=style_degree
                    )
                )
            else:
                # Fall back to SSML
                ssml_chunk = {
                    'content': content,
                    'voice': chunk_voice,
                    'emotion': emotion,
                    'intensity': intensity,
                    'speed': chunk_speed,
                    'pitch': chunk_pitch,
                    'volume': chunk_volume
                }
                ssml_result = build_ssml(voice=voice, chunks=[ssml_chunk])
                ssml_text = ssml_result['ssml']
                
                cache_key = hashlib.md5(
                    f"mpreview:{chunk_voice}:{ssml_text}".encode()
                ).hexdigest()[:16]
                
                output_file = run_async(
                    generate_speech(
                        ssml_text, chunk_voice, None, None, None,
                        is_ssml=True, cache_key=cache_key, is_full_ssml=True
                    )
                )
        else:
            # No emotion - simple generation
            rate_str = f"+{int(chunk_speed)}%" if chunk_speed >= 0 else f"{int(chunk_speed)}%"
            pitch_str = f"+{int(chunk_pitch)}Hz" if chunk_pitch >= 0 else f"{int(chunk_pitch)}Hz"
            volume_str = f"+{int(chunk_volume)}%" if chunk_volume >= 0 else f"{int(chunk_volume)}%"
            
            cache_key = hashlib.md5(
                f"mpreview:{chunk_voice}:{content}:{chunk_speed}:{chunk_pitch}".encode()
            ).hexdigest()[:16]
            
            output_file = run_async(
                generate_speech(
                    content,
                    chunk_voice,
                    rate=rate_str,
                    volume=volume_str,
                    pitch=pitch_str,
                    is_ssml=False,
                    cache_key=cache_key
                )
            )
        
        audio_url = request.url_root.rstrip('/') + f'/api/audio/{output_file.name}'
        
        return jsonify({
            'success': True,
            'audio_url': audio_url,
            'filename': output_file.name
        })
        
    except Exception as e:
        print(f"[Mobile Preview] Error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


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
    import re
    import traceback

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
        indextts: 'indextts' | 'indextts_plus' | 'indextts_pro' to grant IndexTTS access
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
        indextts_tier = request.args.get('indextts', None)  # Grant IndexTTS access
        
        user = User.query.filter_by(email=email).first()
        if not user:
            # Auto-create the user if they don't exist
            user = User(email=email, subscription_status='active')
            if simulate_stripe:
                # Set a fake Stripe customer ID for testing
                user.stripe_customer_id = 'cus_test_' + email.split('@')[0]
            if api_tier in ('starter', 'pro', 'enterprise'):
                user.api_tier = api_tier
            if indextts_tier in ('indextts', 'indextts_plus', 'indextts_pro'):
                user.indextts_tier = indextts_tier
                user.indextts_chars_used = 0
            # Set password
            import secrets
            password = custom_password if custom_password else secrets.token_urlsafe(16)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'message': f'User created and unlimited access granted to {email}' + (' (with Stripe simulation)' if simulate_stripe else '') + (f' (API: {api_tier})' if api_tier else '') + (f' (IndexTTS: {indextts_tier})' if indextts_tier else ''),
                'user': {
                    'email': user.email,
                    'password': password if custom_password else 'Random password set - use forgot password to reset',
                    'subscription_status': user.subscription_status,
                    'api_tier': user.api_tier,
                    'indextts_tier': user.indextts_tier,
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
        if indextts_tier in ('indextts', 'indextts_plus', 'indextts_pro'):
            user.indextts_tier = indextts_tier
            user.indextts_chars_used = 0
        if custom_password:
            user.set_password(custom_password)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Unlimited access granted to {email}' + (' (with Stripe simulation)' if simulate_stripe else '') + (f' (API: {api_tier})' if api_tier else '') + (f' (IndexTTS: {indextts_tier})' if indextts_tier else ''),
            'user': {
                'email': user.email,
                'password_updated': bool(custom_password),
                'subscription_status': user.subscription_status,
                'api_tier': user.api_tier,
                'indextts_tier': user.indextts_tier,
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
