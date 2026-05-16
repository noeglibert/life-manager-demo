from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, session, make_response
from markupsafe import Markup
from models import db, Contact, Interaction, Tag, JournalEntry, Reminder, GameStats, LearningInterest, LearningSession, LearningProgress, Highlight, WordleStats, PortfolioBriefing, MeditationSession, NutritionProfile, NutritionEntry, MealPlan, WeightEntry, NewsletterIssue, NewsletterIdea, NewsletterSubscriber, PortfolioStock, StockFundamentals, ApiUsageLog, Workout, TrainingPlan, TrainingWeek, CoachConversation, CoachGoal, CoachMood, CoachSummary, CoachPreference, MandarinCard, MandarinReview, MandarinSession, GarminDailyStats, TrainingDay, FinanceTransaction, FinanceBudget, FinanceRecurringCost, DCASchedule, SurveyResponse, Trip, Ticker, TradeLot, TradeSale, LotConsumption, Dividend, EntryZone, Catalyst, Risk, TickerChatMessage
import hashlib
import csv
import io
import urllib.request
from datetime import datetime, timedelta, date
import re
import json
import os
import time
import random
from dotenv import load_dotenv
import anthropic
import markdown

# Load environment variables from .env file (override=True ensures .env values take precedence)
basedir_env = os.path.abspath(os.path.dirname(__file__))
load_dotenv(dotenv_path=os.path.join(basedir_env, '.env'), override=True)

# Demo mode: read-only showcase with no external API calls
DEMO_MODE = os.getenv('DEMO_MODE', '').lower() in ('1', 'true', 'yes')

# Initialize Anthropic client (skip in demo mode)
claude_client = None
if not DEMO_MODE and os.getenv('ANTHROPIC_API_KEY'):
    claude_client = anthropic.Anthropic()

# Claude API pricing per million tokens: (input_price, output_price)
CLAUDE_PRICING = {
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-sonnet-4-5-20250929": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-7": (15.0, 75.0),
}


def call_claude(feature, endpoint, **kwargs):
    """Wrapper around claude_client.messages.create() that logs usage and cost.

    Args:
        feature: Feature category (e.g. 'journal', 'nutrition', 'portfolio')
        endpoint: Specific action (e.g. 'reflect', 'log_meal', 'deep_dive')
        **kwargs: All arguments passed to messages.create()

    Returns:
        The Anthropic message response object
    """
    if DEMO_MODE:
        raise RuntimeError("call_claude() is disabled in DEMO_MODE")
    start = time.time()
    response = claude_client.messages.create(**kwargs)
    duration_ms = int((time.time() - start) * 1000)

    model = kwargs.get('model', 'unknown')
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    # Prompt caching: cache writes cost 1.25x, cache reads cost 0.1x of normal input
    cache_creation = getattr(response.usage, 'cache_creation_input_tokens', 0) or 0
    cache_read = getattr(response.usage, 'cache_read_input_tokens', 0) or 0

    # Calculate cost
    pricing = CLAUDE_PRICING.get(model, (3.0, 15.0))  # default to Sonnet pricing
    cost = (
        input_tokens * pricing[0]
        + cache_creation * pricing[0] * 1.25
        + cache_read * pricing[0] * 0.1
        + output_tokens * pricing[1]
    ) / 1_000_000

    # Log to database
    try:
        log = ApiUsageLog(
            feature=feature,
            endpoint=endpoint,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost, 6),
            duration_ms=duration_ms,
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print(f"API usage logging error: {e}")
        db.session.rollback()

    return response


# Achievement definitions
ACHIEVEMENTS = [
    # Streak achievements
    {"id": "first_entry", "name": "First Steps", "description": "Write your first journal entry", "icon": "pencil", "category": "streaks", "condition": {"type": "entries", "target": 1}},
    {"id": "streak_7", "name": "Week Warrior", "description": "Maintain a 7-day writing streak", "icon": "fire", "category": "streaks", "condition": {"type": "streak", "target": 7}},
    {"id": "streak_14", "name": "Fortnight Force", "description": "Maintain a 14-day writing streak", "icon": "fire", "category": "streaks", "condition": {"type": "streak", "target": 14}},
    {"id": "streak_30", "name": "Monthly Master", "description": "Maintain a 30-day writing streak", "icon": "calendar", "category": "streaks", "condition": {"type": "streak", "target": 30}},
    {"id": "streak_100", "name": "Centurion", "description": "Maintain a 100-day writing streak", "icon": "trophy", "category": "streaks", "condition": {"type": "streak", "target": 100}},

    # Word count achievements
    {"id": "words_1k", "name": "Wordsmith", "description": "Write 1,000 total words", "icon": "scroll", "category": "writing", "condition": {"type": "words", "target": 1000}},
    {"id": "words_10k", "name": "Storyteller", "description": "Write 10,000 total words", "icon": "book", "category": "writing", "condition": {"type": "words", "target": 10000}},
    {"id": "words_50k", "name": "Novelist", "description": "Write 50,000 total words (NaNoWriMo!)", "icon": "books", "category": "writing", "condition": {"type": "words", "target": 50000}},

    # Entry count achievements
    {"id": "entries_10", "name": "Getting Started", "description": "Write 10 journal entries", "icon": "notebook", "category": "entries", "condition": {"type": "entries", "target": 10}},
    {"id": "entries_50", "name": "Regular Writer", "description": "Write 50 journal entries", "icon": "notebook", "category": "entries", "condition": {"type": "entries", "target": 50}},
    {"id": "entries_100", "name": "Dedicated Journaler", "description": "Write 100 journal entries", "icon": "star", "category": "entries", "condition": {"type": "entries", "target": 100}},
    {"id": "entries_365", "name": "Year in Review", "description": "Write 365 journal entries", "icon": "crown", "category": "entries", "condition": {"type": "entries", "target": 365}},

    # Social achievements
    {"id": "mentions_5", "name": "Social Butterfly", "description": "Mention 5 different people", "icon": "people", "category": "social", "condition": {"type": "unique_mentions", "target": 5}},
    {"id": "mentions_20", "name": "Connector", "description": "Mention 20 different people", "icon": "network", "category": "social", "condition": {"type": "unique_mentions", "target": 20}},
    {"id": "mentions_50", "name": "Relationship Master", "description": "Mention 50 different people", "icon": "heart", "category": "social", "condition": {"type": "unique_mentions", "target": 50}},

    # Challenge achievements
    {"id": "challenges_1", "name": "Challenge Accepted", "description": "Complete your first daily challenge", "icon": "target", "category": "challenges", "condition": {"type": "challenges", "target": 1}},
    {"id": "challenges_10", "name": "Challenger", "description": "Complete 10 daily challenges", "icon": "medal", "category": "challenges", "condition": {"type": "challenges", "target": 10}},
    {"id": "challenges_50", "name": "Challenge Champion", "description": "Complete 50 daily challenges", "icon": "trophy", "category": "challenges", "condition": {"type": "challenges", "target": 50}},

    # Level achievements
    {"id": "level_3", "name": "Rising Star", "description": "Reach Level 3 (Chronicler)", "icon": "star", "category": "levels", "condition": {"type": "level", "target": 3}},
    {"id": "level_5", "name": "Dedicated", "description": "Reach Level 5 (Historian)", "icon": "gem", "category": "levels", "condition": {"type": "level", "target": 5}},
    {"id": "level_8", "name": "Legend", "description": "Reach Level 8 (Legend)", "icon": "crown", "category": "levels", "condition": {"type": "level", "target": 8}},

    # Learning achievements
    {"id": "curious_mind", "name": "Curious Mind", "description": "Complete your first learning session", "icon": "lightbulb", "category": "learning", "condition": {"type": "learning_sessions", "target": 1}},
    {"id": "knowledge_seeker", "name": "Knowledge Seeker", "description": "Complete 10 learning sessions", "icon": "book", "category": "learning", "condition": {"type": "learning_sessions", "target": 10}},
    {"id": "scholar", "name": "Scholar", "description": "Complete 25 learning sessions", "icon": "graduation", "category": "learning", "condition": {"type": "learning_sessions", "target": 25}},
    {"id": "learning_streak_7", "name": "Learning Streak", "description": "Maintain a 7-day learning streak", "icon": "brain", "category": "learning", "condition": {"type": "learning_streak", "target": 7}},
    # Meditation achievements
    {"id": "first_breath", "name": "First Breath", "description": "Complete your first meditation session", "icon": "lotus", "category": "meditation", "condition": {"type": "meditation_sessions", "target": 1}},
    {"id": "meditation_10", "name": "Inner Peace", "description": "Complete 10 meditation sessions", "icon": "lotus", "category": "meditation", "condition": {"type": "meditation_sessions", "target": 10}},
    {"id": "meditation_50", "name": "Zen Master", "description": "Complete 50 meditation sessions", "icon": "lotus", "category": "meditation", "condition": {"type": "meditation_sessions", "target": 50}},
    {"id": "meditation_streak_7", "name": "Mindful Week", "description": "Maintain a 7-day meditation streak", "icon": "brain", "category": "meditation", "condition": {"type": "meditation_streak", "target": 7}},
    {"id": "meditation_streak_30", "name": "Monk Mode", "description": "Maintain a 30-day meditation streak", "icon": "calendar", "category": "meditation", "condition": {"type": "meditation_streak", "target": 30}},
    {"id": "meditation_minutes_60", "name": "Hour of Calm", "description": "Meditate for a total of 60 minutes", "icon": "clock", "category": "meditation", "condition": {"type": "meditation_minutes", "target": 60}},
    {"id": "meditation_minutes_600", "name": "Deep Focus", "description": "Meditate for a total of 10 hours", "icon": "star", "category": "meditation", "condition": {"type": "meditation_minutes", "target": 600}},
    # Nutrition achievements
    {"id": "first_bite", "name": "First Bite", "description": "Log your first meal", "icon": "apple", "category": "nutrition", "condition": {"type": "nutrition_entries", "target": 1}},
    {"id": "week_tracker", "name": "Week Tracker", "description": "Log meals for 7 consecutive days", "icon": "calendar", "category": "nutrition", "condition": {"type": "nutrition_streak", "target": 7}},
    {"id": "nutrition_nut", "name": "Nutrition Nut", "description": "Log 50 total meals", "icon": "salad", "category": "nutrition", "condition": {"type": "nutrition_entries", "target": 50}},
    {"id": "meal_prep_master", "name": "Meal Prep Master", "description": "Generate your first weekly meal plan", "icon": "chef", "category": "nutrition", "condition": {"type": "meal_plans", "target": 1}},
    {"id": "calorie_sensei", "name": "Calorie Sensei", "description": "Log 200 total meals", "icon": "trophy", "category": "nutrition", "condition": {"type": "nutrition_entries", "target": 200}},
    # Newsletter achievements
    {"id": "first_draft", "name": "First Draft", "description": "Add your first newsletter idea", "icon": "lightbulb", "category": "newsletter", "condition": {"type": "newsletter_ideas", "target": 1}},
    {"id": "idea_machine", "name": "Idea Machine", "description": "Add 25 newsletter ideas", "icon": "brain", "category": "newsletter", "condition": {"type": "newsletter_ideas", "target": 25}},
    {"id": "newsletter_regular", "name": "Newsletter Regular", "description": "Plan 5 newsletter issues", "icon": "envelope", "category": "newsletter", "condition": {"type": "newsletter_issues", "target": 5}},
    # Activity achievements
    {"id": "first_run", "name": "First Steps", "description": "Log your first run", "icon": "shoe", "category": "activity", "condition": {"type": "first_run", "target": 1}},
    {"id": "first_gym", "name": "Iron Starter", "description": "Log your first gym session", "icon": "dumbbell", "category": "activity", "condition": {"type": "first_gym", "target": 1}},
    {"id": "activity_streak_7", "name": "Active Week", "description": "7-day activity streak", "icon": "fire", "category": "activity", "condition": {"type": "activity_streak", "target": 7}},
    {"id": "activity_streak_30", "name": "Fitness Habit", "description": "30-day activity streak", "icon": "calendar", "category": "activity", "condition": {"type": "activity_streak", "target": 30}},
    {"id": "marathon_ready", "name": "Marathon Ready", "description": "Complete a 30km+ long run", "icon": "medal", "category": "activity", "condition": {"type": "long_run", "target": 30}},
    {"id": "century_km", "name": "Century Club", "description": "Log 100km total running distance", "icon": "trophy", "category": "activity", "condition": {"type": "total_run_km", "target": 100}},
    {"id": "activity_50", "name": "Consistent Athlete", "description": "Log 50 total workouts", "icon": "star", "category": "activity", "condition": {"type": "activity_sessions", "target": 50}},
]

# Daily Challenge definitions
DAILY_CHALLENGES = [
    {
        "id": 0,
        "title": "Poet's Soul",
        "description": "Write your entry as a poem (rhyming or free verse)",
        "icon": "poem",
        "xp_bonus": 30,
        "check_type": "manual"
    },
    {
        "id": 1,
        "title": "No Work Zone",
        "description": "Write about anything except work or professional life",
        "icon": "palm",
        "xp_bonus": 20,
        "check_type": "manual"
    },
    {
        "id": 2,
        "title": "Precision Writer",
        "description": "Write exactly 100 words (within 5 words)",
        "icon": "target",
        "xp_bonus": 25,
        "check_type": "word_count",
        "target": 100,
        "tolerance": 5
    },
    {
        "id": 3,
        "title": "Social Butterfly",
        "description": "Mention at least 3 different people in your entry",
        "icon": "people",
        "xp_bonus": 25,
        "check_type": "mention_count",
        "target": 3
    },
    {
        "id": 4,
        "title": "Gratitude Journal",
        "description": "List 5 things you're grateful for today",
        "icon": "heart",
        "xp_bonus": 20,
        "check_type": "manual"
    },
    {
        "id": 5,
        "title": "Memory Lane",
        "description": "Write about a favorite memory from your past",
        "icon": "clock",
        "xp_bonus": 20,
        "check_type": "manual"
    },
    {
        "id": 6,
        "title": "Future Self",
        "description": "Write a letter to yourself 5 years from now",
        "icon": "letter",
        "xp_bonus": 25,
        "check_type": "manual"
    },
    {
        "id": 7,
        "title": "Sensory Experience",
        "description": "Describe your day using all 5 senses",
        "icon": "eye",
        "xp_bonus": 25,
        "check_type": "manual"
    },
    {
        "id": 8,
        "title": "Mini Story",
        "description": "Write a short fictional story (beginning, middle, end)",
        "icon": "book",
        "xp_bonus": 30,
        "check_type": "manual"
    },
    {
        "id": 9,
        "title": "Question Explorer",
        "description": "Answer a deep question: What would you do if you couldn't fail?",
        "icon": "question",
        "xp_bonus": 20,
        "check_type": "manual"
    },
    {
        "id": 10,
        "title": "Marathon Writer",
        "description": "Write at least 500 words",
        "icon": "marathon",
        "xp_bonus": 35,
        "check_type": "word_count_min",
        "target": 500
    },
    {
        "id": 11,
        "title": "Haiku Master",
        "description": "Include at least one haiku (5-7-5 syllables)",
        "icon": "flower",
        "xp_bonus": 25,
        "check_type": "manual"
    }
]

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-this')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max request body
# Use absolute path to ensure correct database location
basedir = os.path.abspath(os.path.dirname(__file__))
_db_file = 'demo.db' if DEMO_MODE else 'contacts.db'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, _db_file)}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Expose DEMO_MODE to all templates
@app.context_processor
def demo_mode_processor():
    return dict(DEMO_MODE=DEMO_MODE)

# Security headers (especially important for public demo)
@app.after_request
def security_headers(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

# Block all write operations in demo mode
@app.before_request
def demo_block_writes():
    if not DEMO_MODE:
        return
    if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
        # Whitelist Wordle guess so the game stays playable
        if request.path == '/api/wordle/guess':
            return
        return jsonify({'error': 'This is a read-only demo. Changes are disabled.'}), 403

# Markdown filter for templates
@app.template_filter('duration_fmt')
def duration_fmt_filter(minutes):
    """Format float minutes as mm:ss string"""
    if not minutes:
        return '0:00'
    mins = int(minutes)
    secs = int(round((minutes - mins) * 60))
    return f"{mins}:{secs:02d}"

@app.template_filter('markdown')
def markdown_filter(text):
    if text:
        return Markup(markdown.markdown(text, extensions=['extra', 'nl2br']))
    return ''

@app.template_filter('parse_exercises')
def parse_exercises_filter(exercises_json):
    """Parse exercises JSON string for display in templates. Handles both old and new format."""
    if not exercises_json:
        return []
    try:
        exercises = json.loads(exercises_json) if isinstance(exercises_json, str) else exercises_json
        return exercises
    except (json.JSONDecodeError, TypeError):
        return []

# ===== SVG Icon Helper =====
ICON_MAP = {
    # Core
    'flame': 'icon-flame.svg', 'fire': 'icon-flame.svg',
    'star': 'icon-star.svg', 'check': 'icon-check.svg',
    'clock': 'icon-clock.svg', 'target': 'icon-target.svg',
    'heart': 'icon-heart.svg', 'brain': 'icon-brain.svg',
    'muscle': 'icon-muscle.svg', 'sun': 'icon-sun.svg',
    'seedling': 'icon-seedling.svg', 'scale': 'icon-scale.svg',
    'writing': 'icon-writing.svg',
    # Feature
    'beads': 'icon-beads.svg', 'dumbbell': 'icon-dumbbell.svg',
    'cycling': 'icon-cycling.svg', 'flag': 'icon-flag.svg',
    'chart': 'icon-chart.svg', 'clipboard': 'icon-clipboard.svg',
    'scroll': 'icon-scroll.svg', 'book': 'icon-book.svg',
    'books': 'icon-book.svg', 'notebook': 'icon-book.svg',
    'trophy': 'icon-trophy.svg', 'snowflake': 'icon-snowflake.svg',
    'moon': 'icon-moon.svg', 'lock': 'icon-lock.svg',
    'pin': 'icon-pin.svg', 'sparkle': 'icon-sparkle.svg',
    'phone': 'icon-phone.svg', 'envelope': 'icon-envelope.svg',
    'skull': 'icon-skull.svg', 'lightbulb': 'icon-lightbulb.svg',
    'save': 'icon-save.svg', 'pencil': 'icon-pencil.svg',
    'robot': 'icon-robot.svg', 'spin': 'icon-spin.svg',
    # Achievement / challenge
    'crown': 'icon-crown.svg', 'medal': 'icon-medal.svg',
    'gem': 'icon-gem.svg', 'graduation': 'icon-graduation.svg',
    'palm': 'icon-palm.svg', 'eye': 'icon-eye.svg',
    'flower': 'icon-flower.svg', 'question': 'icon-question.svg',
    'calendar': 'icon-clock.svg', 'people': 'icon-heart.svg',
    'network': 'icon-heart.svg', 'poem': 'icon-writing.svg',
    'letter': 'icon-envelope.svg', 'marathon': 'icon-muscle.svg',
    'lotus': 'icon-lotus.svg',
    # Mood faces
    'mood-great': 'mood-great.svg', 'mood-good': 'mood-good.svg',
    'mood-okay': 'mood-okay.svg', 'mood-down': 'mood-down.svg',
    'mood-sad': 'mood-sad.svg',
}

# Emoji → SVG icon name mapping (for learning interests stored as emoji in DB)
EMOJI_ICON_MAP = {
    '\U0001f9e0': 'brain', '\U0001f4bb': 'robot', '\U0001f4da': 'book', '\U0001f4d6': 'book',
    '\U0001f4d3': 'book', '\U0001f4d5': 'book', '\U0001f4d7': 'book', '\U0001f4d8': 'book',
    '\U0001f4d9': 'book', '\U0001f4dd': 'writing', '\u270f\ufe0f': 'pencil', '\u270f': 'pencil',
    '\U0001f3a8': 'flower', '\U0001f3b5': 'beads', '\U0001f3b6': 'beads',
    '\U0001f52c': 'eye', '\U0001f52d': 'eye', '\U0001f30d': 'seedling', '\U0001f30e': 'seedling',
    '\U0001f30f': 'seedling', '\u2697\ufe0f': 'sparkle', '\u269b\ufe0f': 'sparkle',
    '\U0001f4c8': 'chart', '\U0001f4c9': 'chart', '\U0001f4ca': 'chart',
    '\U0001f4a1': 'lightbulb', '\U0001f3d7\ufe0f': 'flag', '\U0001f3d7': 'flag',
    '\U0001f4b0': 'gem', '\U0001f4b8': 'gem', '\U0001f48e': 'gem',
    '\U0001f680': 'flag', '\u2764\ufe0f': 'heart', '\u2764': 'heart',
    '\U0001f525': 'flame', '\u2b50': 'star', '\U0001f31f': 'star',
    '\U0001f3c6': 'trophy', '\U0001f3af': 'target', '\U0001f4aa': 'muscle',
    '\U0001f331': 'seedling', '\U0001f332': 'seedling', '\U0001f333': 'seedling',
    '\U0001f3eb': 'graduation', '\U0001f393': 'graduation',
    '\U0001f4f7': 'eye', '\U0001f4f8': 'eye', '\U0001f3ac': 'eye',
    '\U0001f4e1': 'sparkle', '\U0001f916': 'robot', '\U0001f5a5\ufe0f': 'robot',
    '\U0001f5a5': 'robot', '\u2328\ufe0f': 'robot', '\u2328': 'robot',
    '\U0001f3b9': 'beads', '\U0001f3b8': 'beads', '\U0001f3bb': 'beads',
    '\U0001f9ea': 'sparkle', '\U0001f9ec': 'sparkle', '\U0001f9eb': 'sparkle',
    '\U0001f4d0': 'scale', '\U0001f4cf': 'scale',
    '\u2708\ufe0f': 'palm', '\U0001f30a': 'palm', '\U0001f334': 'palm',
    '\U0001f373': 'seedling', '\U0001f372': 'seedling', '\U0001f355': 'seedling',
    '\U0001f3ae': 'spin', '\U0001f579\ufe0f': 'spin',
    '\U0001f4f0': 'scroll', '\U0001f5de\ufe0f': 'scroll',
}

@app.context_processor
def icon_processor():
    def svg_icon(name, css_class='inline-icon'):
        filename = ICON_MAP.get(name, f'icon-{name}.svg')
        return Markup(f'<img class="{css_class}" src="/static/images/{filename}" alt="">')
    def svg_icon_file(name):
        return ICON_MAP.get(name, f'icon-{name}.svg')
    def learn_icon(emoji_or_name, css_class='inline-icon'):
        """Convert an emoji or icon name to an SVG img tag. Falls back to book icon."""
        if not emoji_or_name:
            return svg_icon('book', css_class)
        # If it's already an icon name in ICON_MAP, use it directly
        if emoji_or_name in ICON_MAP:
            return svg_icon(emoji_or_name, css_class)
        # Try emoji mapping
        icon_name = EMOJI_ICON_MAP.get(emoji_or_name.strip(), None)
        if icon_name:
            return svg_icon(icon_name, css_class)
        # Default fallback
        return svg_icon('book', css_class)
    def learn_icon_name(emoji_or_name):
        """Convert an emoji to an icon name string (for JS use)."""
        if not emoji_or_name:
            return 'book'
        if emoji_or_name in ICON_MAP:
            return emoji_or_name
        return EMOJI_ICON_MAP.get(emoji_or_name.strip(), 'book')
    return dict(svg_icon=svg_icon, svg_icon_file=svg_icon_file, learn_icon=learn_icon, learn_icon_name=learn_icon_name)

# Create tables
with app.app_context():
    db.create_all()


def seed_portfolio_stocks():
    """Seed portfolio stocks from static lists on first run"""
    if PortfolioStock.query.count() == 0:
        for h in PORTFOLIO_HOLDINGS:
            db.session.add(PortfolioStock(
                ticker=h['ticker'], company=h['company'], layer=h['layer'],
                status='holding', weight=h['weight'], conviction=h['conviction'],
                value=h.get('value', 0), shares=h.get('shares', 0),
                avg_cost=h.get('avg_cost', 0), currency=h.get('currency', 'USD')
            ))
        for w in AI_WATCHLIST:
            db.session.add(PortfolioStock(
                ticker=w['ticker'], company=w['company'], layer=w['layer'],
                status='watchlist', verdict=w.get('verdict')
            ))
        db.session.commit()
        print(f"Seeded {len(PORTFOLIO_HOLDINGS)} holdings + {len(AI_WATCHLIST)} watchlist stocks")


# ===== PASSWORD PROTECTION =====

APP_PASSWORD = os.getenv('APP_PASSWORD')

@app.before_request
def require_login():
    """Require password for all pages except login and static files"""
    if DEMO_MODE:
        session['authenticated'] = True
        return
    if not APP_PASSWORD:
        # No password set, skip protection
        return
    allowed_endpoints = ('login', 'static', 'newsletter_signup')
    if request.endpoint in allowed_endpoints:
        return
    if not session.get('authenticated'):
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if not APP_PASSWORD:
        return redirect(url_for('index'))
    if session.get('authenticated'):
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == APP_PASSWORD:
            session['authenticated'] = True
            session.permanent = True
            app.permanent_session_lifetime = timedelta(days=30)
            return redirect(url_for('index'))
        else:
            error = 'Incorrect password. Please try again.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# ===== GAMIFICATION HELPERS =====

def get_or_create_game_stats():
    """Get the game stats singleton or create if doesn't exist"""
    stats = GameStats.query.first()
    if not stats:
        stats = GameStats()
        db.session.add(stats)
        db.session.commit()
    return stats


def generate_daily_challenge_with_claude():
    """Generate a unique daily writing challenge using Claude"""
    if not claude_client:
        return None

    # Get recent challenge history to avoid repetition
    recent_titles = []
    try:
        from models import GameStats as GS
        stats = GS.query.first()
        if stats and stats.challenge_history:
            recent_titles = json.loads(stats.challenge_history)
        elif stats and stats.challenge_title:
            recent_titles = [stats.challenge_title]
    except Exception:
        pass

    prompt = f"""You are generating a creative daily writing challenge for a personal journal app.
The challenge should inspire the user to write something meaningful, creative, or reflective in their journal entry today.

{"Previously used challenges (DO NOT repeat any of these): " + ", ".join(recent_titles) if recent_titles else ""}

Generate ONE unique writing challenge. Be creative and varied — it could be:
- A creative writing constraint (style, format, perspective)
- A reflective prompt (self-discovery, gratitude, growth)
- A fun exercise (storytelling, world-building, observation)
- A mindfulness activity (sensory awareness, emotional check-in)
- A social/relationship focus (appreciation, connection, memories with people)

Return ONLY valid JSON in this exact format:
{{
    "title": "Short catchy title (2-4 words)",
    "description": "Clear, engaging description of the challenge (1-2 sentences)",
    "icon": "single emoji that fits the challenge theme",
    "xp_bonus": 25
}}"""

    try:
        message = call_claude('journal', 'daily_challenge',
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = message.content[0].text
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            challenge_data = json.loads(json_match.group())
            return challenge_data
    except Exception as e:
        print(f"Error generating daily challenge: {e}")
    return None


def get_daily_challenge(stats):
    """Get today's challenge, assigning a new one if needed"""
    today = datetime.now().date()

    # Check if we need to assign a new challenge
    if stats.challenge_date != today:
        # Try to generate a unique challenge with Claude
        generated = generate_daily_challenge_with_claude()

        if generated:
            # Store the Claude-generated challenge
            stats.challenge_title = generated.get('title', 'Daily Challenge')
            stats.challenge_description = generated.get('description', 'Write something meaningful today.')
            gen_icon = generated.get('icon', 'writing')
            # Sanitize: if Claude returned an emoji, map it; otherwise use as-is
            if gen_icon not in ICON_MAP:
                gen_icon = EMOJI_ICON_MAP.get(gen_icon, 'writing')
            stats.challenge_icon = gen_icon
            stats.current_challenge_id = -1  # -1 indicates a generated challenge
        else:
            # Fallback to static challenges
            available_challenges = [i for i in range(len(DAILY_CHALLENGES))
                                  if i != stats.current_challenge_id]
            stats.current_challenge_id = random.choice(available_challenges)
            stats.challenge_title = None
            stats.challenge_description = None
            stats.challenge_icon = None

        stats.challenge_date = today
        stats.challenge_completed_today = False

        # Add to challenge history (keep last 30 to avoid repeats)
        history = []
        if stats.challenge_history:
            try:
                history = json.loads(stats.challenge_history)
            except Exception:
                history = []
        new_title = stats.challenge_title if stats.current_challenge_id == -1 else (
            DAILY_CHALLENGES[stats.current_challenge_id]["title"] if 0 <= (stats.current_challenge_id or 0) < len(DAILY_CHALLENGES) else None
        )
        if new_title and new_title not in history:
            history.append(new_title)
            history = history[-30:]  # Keep last 30
        stats.challenge_history = json.dumps(history)

        db.session.commit()

    # Return the challenge as a dict
    if stats.current_challenge_id == -1 and stats.challenge_title:
        # Sanitize icon: if it's an emoji (not in ICON_MAP), map it or fallback
        raw_icon = stats.challenge_icon or "writing"
        if raw_icon not in ICON_MAP:
            raw_icon = EMOJI_ICON_MAP.get(raw_icon, "writing")
        # Return Claude-generated challenge
        return {
            "id": -1,
            "title": stats.challenge_title,
            "description": stats.challenge_description,
            "icon": raw_icon,
            "xp_bonus": 25,
            "check_type": "manual"
        }
    else:
        # Return static challenge
        idx = stats.current_challenge_id if stats.current_challenge_id is not None else 0
        if 0 <= idx < len(DAILY_CHALLENGES):
            return DAILY_CHALLENGES[idx]
        return DAILY_CHALLENGES[0]


def get_unlocked_achievements(stats):
    """Get list of unlocked achievement IDs from stats"""
    if not stats.achievements:
        return []
    try:
        return json.loads(stats.achievements)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def save_unlocked_achievements(stats, unlocked_list):
    """Save list of unlocked achievement IDs to stats"""
    stats.achievements = json.dumps(unlocked_list)


def check_achievements(stats):
    """Check for newly unlocked achievements and return list of new ones"""
    unlocked = get_unlocked_achievements(stats)
    newly_unlocked = []

    # Count unique people mentioned across all entries
    unique_mentions = db.session.query(db.func.count(db.distinct(Contact.id))).join(
        JournalEntry.mentioned_contacts
    ).scalar() or 0

    for achievement in ACHIEVEMENTS:
        if achievement["id"] in unlocked:
            continue  # Already unlocked

        condition = achievement["condition"]
        achieved = False

        if condition["type"] == "streak":
            achieved = stats.current_streak >= condition["target"] or stats.longest_streak >= condition["target"]
        elif condition["type"] == "entries":
            achieved = stats.total_entries >= condition["target"]
        elif condition["type"] == "words":
            achieved = stats.total_words >= condition["target"]
        elif condition["type"] == "challenges":
            achieved = stats.challenges_completed >= condition["target"]
        elif condition["type"] == "level":
            achieved = stats.level >= condition["target"]
        elif condition["type"] == "unique_mentions":
            achieved = unique_mentions >= condition["target"]
        elif condition["type"] == "learning_sessions":
            achieved = (stats.learning_sessions_total or 0) >= condition["target"]
        elif condition["type"] == "learning_streak":
            achieved = (stats.learning_streak or 0) >= condition["target"]
        elif condition["type"] == "meditation_sessions":
            achieved = (stats.meditation_sessions_total or 0) >= condition["target"]
        elif condition["type"] == "meditation_streak":
            achieved = (stats.meditation_streak or 0) >= condition["target"]
        elif condition["type"] == "meditation_minutes":
            achieved = (stats.meditation_minutes_total or 0) >= condition["target"]
        elif condition["type"] == "nutrition_entries":
            achieved = (stats.nutrition_entries_total or 0) >= condition["target"]
        elif condition["type"] == "nutrition_streak":
            achieved = (stats.nutrition_streak or 0) >= condition["target"]
        elif condition["type"] == "meal_plans":
            achieved = (stats.meal_plans_generated or 0) >= condition["target"]
        elif condition["type"] == "newsletter_ideas":
            achieved = (stats.newsletter_ideas_total or 0) >= condition["target"]
        elif condition["type"] == "newsletter_issues":
            achieved = (stats.newsletter_issues_total or 0) >= condition["target"]
        elif condition["type"] == "activity_streak":
            achieved = (stats.activity_streak or 0) >= condition["target"]
        elif condition["type"] == "activity_sessions":
            achieved = (stats.activity_sessions_total or 0) >= condition["target"]
        elif condition["type"] == "first_run":
            achieved = Workout.query.filter_by(workout_type='run').first() is not None
        elif condition["type"] == "first_gym":
            achieved = Workout.query.filter_by(workout_type='gym').first() is not None
        elif condition["type"] == "long_run":
            achieved = Workout.query.filter(Workout.workout_type == 'run', Workout.distance_km >= condition["target"]).first() is not None
        elif condition["type"] == "total_run_km":
            total_km = db.session.query(db.func.sum(Workout.distance_km)).filter(Workout.workout_type == 'run').scalar() or 0
            achieved = total_km >= condition["target"]

        if achieved:
            unlocked.append(achievement["id"])
            newly_unlocked.append(achievement)

    if newly_unlocked:
        save_unlocked_achievements(stats, unlocked)

    return newly_unlocked


def check_challenge_completion(challenge, content, mentions_count):
    """Check if a challenge is completed based on entry content"""
    check_type = challenge.get("check_type", "manual")
    word_count = len(content.split())

    if check_type == "word_count":
        target = challenge.get("target", 100)
        tolerance = challenge.get("tolerance", 5)
        return abs(word_count - target) <= tolerance

    elif check_type == "word_count_min":
        target = challenge.get("target", 500)
        return word_count >= target

    elif check_type == "mention_count":
        target = challenge.get("target", 3)
        return mentions_count >= target

    # Manual challenges are always considered "completable" - user claims completion
    return None  # None means can't auto-check


def update_streak(stats, entry_date):
    """Update the writing streak based on entry date"""
    if stats.last_entry_date is None:
        # First entry ever
        stats.current_streak = 1
        stats.longest_streak = 1
    else:
        days_diff = (entry_date - stats.last_entry_date).days
        
        if days_diff == 1:
            # Consecutive day - increase streak
            stats.current_streak += 1
            if stats.current_streak > stats.longest_streak:
                stats.longest_streak = stats.current_streak
        elif days_diff == 0:
            # Same day - no change to streak
            pass
        else:
            # Missed days - check if freeze available
            if days_diff == 2 and stats.freeze_available and not stats.freeze_used_this_week:
                # Can use freeze for 1 missed day
                stats.freeze_used_this_week = True
                stats.current_streak += 1
                if stats.current_streak > stats.longest_streak:
                    stats.longest_streak = stats.current_streak
                flash('🧊 Streak Freeze used! Your streak continues!', 'info')
            else:
                # Streak broken
                if stats.current_streak >= 7:
                    flash(f'💔 Streak broken! You had {stats.current_streak} days. Start fresh!', 'warning')
                stats.current_streak = 1
    
    stats.last_entry_date = entry_date

    # Reset freeze weekly — reset if 7+ days have passed since last reset
    if stats.last_freeze_reset is None or (entry_date - stats.last_freeze_reset).days >= 7:
        stats.freeze_used_this_week = False
        stats.last_freeze_reset = entry_date


def calculate_xp(content, mentions_count):
    """Calculate XP earned for a journal entry"""
    xp = 10  # Base XP for writing
    
    word_count = len(content.split())
    
    # Bonus for word count
    if word_count >= 500:
        xp += 25
    
    # Bonus for mentions
    xp += mentions_count * 5
    
    return xp, word_count


def check_level_up(stats):
    """Check if player leveled up and return True if so (handles multiple level ups)"""
    leveled_up = False
    while stats.xp >= stats.xp_for_next_level and stats.level < 8:
        stats.level += 1
        leveled_up = True
    return leveled_up


@app.route('/')
def index():
    """Dashboard/Home page"""
    today = datetime.now().date()
    recent_entries = JournalEntry.query.order_by(JournalEntry.date.desc()).limit(5).all()

    # Game stats
    game_stats = get_or_create_game_stats()

    # Get daily challenge
    daily_challenge = get_daily_challenge(game_stats)

    # Today's habits status
    journaled_today = game_stats.last_entry_date == today
    today_entry = JournalEntry.query.filter_by(date=today).first() if journaled_today else None
    today_word_count = len(today_entry.content.split()) if today_entry and today_entry.content else 0

    meditated_today = game_stats.last_meditation_date == today
    meditation_minutes_today = 0
    if meditated_today:
        meditation_seconds = db.session.query(db.func.sum(MeditationSession.duration_seconds)).filter_by(date=today).scalar() or 0
        meditation_minutes_today = meditation_seconds // 60

    learned_today = game_stats.last_learning_date == today
    today_learning = LearningSession.query.filter_by(date=today).first() if learned_today else None

    nutrition_profile = NutritionProfile.query.first()
    logged_meals_today = game_stats.last_nutrition_date == today
    nutrition_today = 0
    nutrition_target = 0
    if nutrition_profile:
        nutrition_today = db.session.query(db.func.sum(NutritionEntry.calories)).filter_by(date=today).scalar() or 0
        nutrition_target = nutrition_profile.calorie_target

    # Activity
    worked_out_today = game_stats.last_activity_date == today
    today_workouts = Workout.query.filter_by(date=today).all() if worked_out_today else []
    today_workout_count = len(today_workouts)

    habits_today = {
        'journal': {'done': journaled_today, 'detail': f'{today_word_count} words' if journaled_today else 'Not yet', 'streak': game_stats.current_streak},
        'meditate': {'done': meditated_today, 'detail': f'{meditation_minutes_today} min' if meditated_today else 'Not yet', 'streak': game_stats.meditation_streak or 0},
        'learn': {'done': learned_today, 'detail': today_learning.interest.name if today_learning and today_learning.interest else 'Not yet', 'streak': game_stats.learning_streak or 0},
        'nutrition': {'done': logged_meals_today, 'detail': f'{nutrition_today} / {nutrition_target} cal' if nutrition_target else ('Logged' if logged_meals_today else 'Not yet'), 'streak': game_stats.nutrition_streak or 0},
        'activity': {'done': worked_out_today, 'detail': f'{today_workout_count} session{"s" if today_workout_count != 1 else ""}' if worked_out_today else 'Not yet', 'streak': game_stats.activity_streak or 0},
    }

    # Contacts (optimized — only fetch what we need)
    total_contacts = db.session.query(db.func.count(Contact.id)).scalar()
    contacts_needing_attention_list = [c for c in Contact.query.all() if c.days_since_contact and c.days_since_contact > 30]
    contacts_needing_attention_list.sort(key=lambda c: c.days_since_contact or 0, reverse=True)
    contacts_needing_attention = len(contacts_needing_attention_list)

    # Get achievements
    unlocked_ids = get_unlocked_achievements(game_stats)
    all_achievements = ACHIEVEMENTS
    unlocked_achievements = [a for a in ACHIEVEMENTS if a["id"] in unlocked_ids]

    # Recent highlights for dashboard
    recent_highlights = Highlight.query.order_by(Highlight.created_at.desc()).limit(5).all()

    return render_template('index.html',
                         recent_entries=recent_entries,
                         total_contacts=total_contacts,
                         contacts_needing_attention=contacts_needing_attention,
                         contacts_needing_attention_list=contacts_needing_attention_list[:5],
                         game_stats=game_stats,
                         daily_challenge=daily_challenge,
                         habits_today=habits_today,
                         all_achievements=all_achievements,
                         unlocked_achievements=unlocked_achievements,
                         unlocked_ids=unlocked_ids,
                         recent_highlights=recent_highlights,
                         nutrition_today=nutrition_today,
                         nutrition_target=nutrition_target)


# ===== CONTACT ROUTES =====

@app.route('/contacts')
def contacts_list():
    """View all contacts"""
    search_query = request.args.get('search', '')
    category = request.args.get('category', '')
    
    query = Contact.query
    
    if search_query:
        search_lower = search_query.lower()
        query = query.filter(
            (db.func.lower(Contact.first_name).contains(search_lower)) |
            (db.func.lower(Contact.last_name).contains(search_lower)) |
            (db.func.lower(Contact.email).contains(search_lower))
        )
    
    if category:
        query = query.filter(Contact.relationship_category == category)
    
    contacts = query.order_by(Contact.first_name).all()
    categories = db.session.query(Contact.relationship_category).distinct().all()
    
    # Get recent journal mentions for each contact
    contact_mentions = {}
    for contact in contacts:
        # Get most recent journal entry mentioning this contact
        recent_entry = None
        if contact.journal_entries:
            recent_entry = sorted(contact.journal_entries, key=lambda e: e.date, reverse=True)[0]
            # Extract sentence mentioning the contact
            sentences = re.split(r'[.!?]+', recent_entry.content)
            mention_sentence = None
            for sentence in sentences:
                if f"@{contact.first_name}" in sentence or (contact.last_name and f"@{contact.first_name} {contact.last_name}" in sentence):
                    mention_sentence = sentence.strip()
                    break
            contact_mentions[contact.id] = {
                'date': recent_entry.date,
                'sentence': mention_sentence or recent_entry.content[:100]
            }
    
    return render_template('contacts.html', 
                         contacts=contacts, 
                         categories=[c[0] for c in categories if c[0]],
                         contact_mentions=contact_mentions)


@app.route('/contact/new', methods=['GET', 'POST'])
def contact_new():
    """Add new contact"""
    if request.method == 'POST':
        contact = Contact(
            first_name=request.form['first_name'],
            last_name=request.form.get('last_name', ''),
            phone=request.form.get('phone', ''),
            email=request.form.get('email', ''),
            birthday=datetime.strptime(request.form['birthday'], '%Y-%m-%d').date() if request.form.get('birthday') else None,
            address=request.form.get('address', ''),
            notes=request.form.get('notes', ''),
            relationship_category=request.form.get('relationship_category', ''),
            how_we_met=request.form.get('how_we_met', ''),
            preferred_language=request.form.get('preferred_language', ''),
            contact_frequency=int(request.form['contact_frequency']) if request.form.get('contact_frequency') else None
        )
        
        db.session.add(contact)
        db.session.commit()
        
        flash(f'Contact {contact.full_name} added successfully!', 'success')
        return redirect(url_for('contact_detail', contact_id=contact.id))
    
    return render_template('contact_form.html', contact=None)


@app.route('/contact/<int:contact_id>')
def contact_detail(contact_id):
    """View contact details"""
    contact = Contact.query.get_or_404(contact_id)
    interactions = Interaction.query.filter_by(contact_id=contact_id).order_by(Interaction.interaction_date.desc()).all()
    journal_entries = contact.journal_entries
    
    # Extract mention contexts - sentences containing @mentions of this contact
    mention_contexts = []
    for entry in journal_entries:
        # Split content into sentences (rough split by periods, exclamation, question marks)
        sentences = re.split(r'[.!?]+', entry.content)
        for sentence in sentences:
            # Check if this sentence mentions the contact
            if f"@{contact.first_name}" in sentence or (contact.last_name and f"@{contact.first_name} {contact.last_name}" in sentence):
                mention_contexts.append({
                    'entry': entry,
                    'sentence': sentence.strip()
                })
    
    return render_template('contact_detail.html', 
                         contact=contact, 
                         interactions=interactions,
                         journal_entries=journal_entries,
                         mention_contexts=mention_contexts)


@app.route('/contact/<int:contact_id>/edit', methods=['GET', 'POST'])
def contact_edit(contact_id):
    """Edit contact"""
    contact = Contact.query.get_or_404(contact_id)
    
    if request.method == 'POST':
        contact.first_name = request.form['first_name']
        contact.last_name = request.form.get('last_name', '')
        contact.phone = request.form.get('phone', '')
        contact.email = request.form.get('email', '')
        contact.birthday = datetime.strptime(request.form['birthday'], '%Y-%m-%d').date() if request.form.get('birthday') else None
        contact.address = request.form.get('address', '')
        contact.notes = request.form.get('notes', '')
        contact.relationship_category = request.form.get('relationship_category', '')
        contact.how_we_met = request.form.get('how_we_met', '')
        contact.preferred_language = request.form.get('preferred_language', '')
        contact.contact_frequency = int(request.form['contact_frequency']) if request.form.get('contact_frequency') else None
        contact.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        flash(f'Contact {contact.full_name} updated successfully!', 'success')
        return redirect(url_for('contact_detail', contact_id=contact.id))
    
    return render_template('contact_form.html', contact=contact)


@app.route('/contact/<int:contact_id>/delete', methods=['POST'])
def contact_delete(contact_id):
    """Delete contact"""
    contact = Contact.query.get_or_404(contact_id)
    name = contact.full_name
    
    db.session.delete(contact)
    db.session.commit()
    
    flash(f'Contact {name} deleted successfully!', 'success')
    return redirect(url_for('contacts_list'))


@app.route('/contact/<int:contact_id>/interaction/new', methods=['POST'])
def interaction_new(contact_id):
    """Add new interaction"""
    contact = Contact.query.get_or_404(contact_id)

    interaction_date = datetime.strptime(request.form['interaction_date'], '%Y-%m-%d').date()

    # Prevent future dates
    if interaction_date > datetime.now().date():
        flash('Interaction date cannot be in the future.', 'error')
        return redirect(url_for('contact_detail', contact_id=contact_id))

    interaction = Interaction(
        contact_id=contact_id,
        interaction_date=interaction_date,
        interaction_type=request.form.get('interaction_type', ''),
        notes=request.form.get('notes', '')
    )

    db.session.add(interaction)

    # Update last_contacted_date to the most recent interaction date
    most_recent = db.session.query(db.func.max(Interaction.interaction_date)).filter_by(contact_id=contact_id).scalar()
    contact.last_contacted_date = max(interaction_date, most_recent) if most_recent else interaction_date

    db.session.commit()

    flash('Interaction added successfully!', 'success')
    return redirect(url_for('contact_detail', contact_id=contact_id))


@app.route('/contact/<int:contact_id>/interaction/<int:interaction_id>/delete', methods=['POST'])
def interaction_delete(contact_id, interaction_id):
    """Delete an interaction"""
    interaction = Interaction.query.get_or_404(interaction_id)
    if interaction.contact_id != contact_id:
        flash('Invalid interaction.', 'error')
        return redirect(url_for('contact_detail', contact_id=contact_id))

    db.session.delete(interaction)

    # Recalculate last_contacted_date from remaining interactions
    contact = Contact.query.get_or_404(contact_id)
    most_recent = db.session.query(db.func.max(Interaction.interaction_date)).filter_by(contact_id=contact_id).scalar()
    contact.last_contacted_date = most_recent

    db.session.commit()
    flash('Interaction deleted.', 'success')
    return redirect(url_for('contact_detail', contact_id=contact_id))


# ===== JOURNAL ROUTES =====

@app.route('/journal')
def journal_list():
    """View journal entries"""
    entries = JournalEntry.query.order_by(JournalEntry.date.desc()).all()
    return render_template('journal.html', entries=entries)


@app.route('/journal/<date_str>')
def journal_entry(date_str):
    """View/edit specific journal entry"""
    try:
        entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format', 'error')
        return redirect(url_for('journal_list'))

    entry = JournalEntry.query.filter_by(date=entry_date).first()

    # Get all contacts for @mention autocomplete
    contacts = Contact.query.order_by(Contact.first_name).all()

    # Get daily challenge if this is today's entry
    daily_challenge = None
    game_stats = None
    is_today = entry_date == datetime.now().date()
    if is_today:
        game_stats = get_or_create_game_stats()
        daily_challenge = get_daily_challenge(game_stats)

    return render_template('journal_entry.html',
                         entry=entry,
                         date=entry_date,
                         today=datetime.now().date(),
                         timedelta=timedelta,
                         contacts=contacts,
                         daily_challenge=daily_challenge,
                         game_stats=game_stats,
                         is_today=is_today)


@app.route('/journal/save', methods=['POST'])
def journal_save():
    """Save journal entry"""
    date_str = request.form['date']
    entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    content = request.form.get('content', '')
    mood = request.form.get('mood', '')
    claim_challenge = request.form.get('claim_challenge') == 'true'

    is_new_entry = False
    old_word_count = 0
    entry = JournalEntry.query.filter_by(date=entry_date).first()

    if entry:
        # Track old word count for delta calculation
        old_word_count = len(entry.content.split()) if entry.content else 0
        entry.content = content
        entry.mood = mood
        entry.updated_at = datetime.utcnow()
    else:
        entry = JournalEntry(
            date=entry_date,
            content=content,
            mood=mood
        )
        db.session.add(entry)
        is_new_entry = True

    # Parse @mentions and link to contacts
    # Find all @mentions in format @FirstName or @FirstName LastName
    mentions = re.findall(r'@([A-Za-zÀ-ÖØ-öø-ÿ]+(?:\s+[A-Za-zÀ-ÖØ-öø-ÿ]+)?)', content)

    # Clear existing mentions
    entry.mentioned_contacts = []

    # Add new mentions
    for mention in mentions:
        mention_parts = mention.strip().split()
        if len(mention_parts) == 1:
            # Just first name
            contact = Contact.query.filter_by(first_name=mention_parts[0]).first()
        else:
            # First and last name
            contact = Contact.query.filter_by(
                first_name=mention_parts[0],
                last_name=mention_parts[1]
            ).first()

        if contact and contact not in entry.mentioned_contacts:
            entry.mentioned_contacts.append(contact)

    # ===== GAMIFICATION =====
    game_stats = get_or_create_game_stats()

    if is_new_entry and content.strip():  # Only for new entries with content
        # Update streak
        update_streak(game_stats, entry_date)

        # Calculate and add XP
        xp_earned, word_count = calculate_xp(content, len(entry.mentioned_contacts))

        # Check daily challenge completion
        challenge_bonus = 0
        challenge_name = None
        if entry_date == datetime.now().date() and not game_stats.challenge_completed_today:
            daily_challenge = get_daily_challenge(game_stats)
            auto_complete = check_challenge_completion(daily_challenge, content, len(entry.mentioned_contacts))

            # Auto-complete if check passed, or manual claim if user checked the box
            if auto_complete is True or (auto_complete is None and claim_challenge):
                challenge_bonus = daily_challenge.get('xp_bonus', 20)
                game_stats.challenge_completed_today = True
                game_stats.challenges_completed += 1
                challenge_name = daily_challenge["title"]

        game_stats.xp += xp_earned + challenge_bonus
        game_stats.total_entries += 1
        game_stats.total_words += word_count

        # Check for level up
        leveled_up = check_level_up(game_stats)

        db.session.commit()

        # Check for new achievements
        new_achievements = check_achievements(game_stats)

        db.session.commit()

        # Build a single consolidated flash message
        total_xp = xp_earned + challenge_bonus
        summary_parts = [f'Journal entry saved! +{total_xp} XP']

        if challenge_name:
            summary_parts.append(f'🎯 Challenge Complete: {challenge_name}! +{challenge_bonus} bonus XP')

        if game_stats.current_streak % 7 == 0 and game_stats.current_streak > 0:
            summary_parts.append(f'🔥 {game_stats.current_streak} day streak!')

        if leveled_up:
            summary_parts.append(f'⭐ LEVEL UP! You\'re now a {game_stats.level_name}! (Level {game_stats.level})')

        for achievement in new_achievements:
            summary_parts.append(f'🏆 Achievement Unlocked: {achievement["name"]}!')

        flash(' | '.join(summary_parts), 'success')
    else:
        # Update word count delta for edits
        new_word_count = len(content.split()) if content else 0
        word_delta = new_word_count - old_word_count
        if word_delta != 0:
            game_stats.total_words = max(0, (game_stats.total_words or 0) + word_delta)

        # For updates, still allow claiming challenge if not completed
        if claim_challenge and entry_date == datetime.now().date() and not game_stats.challenge_completed_today:
            daily_challenge = get_daily_challenge(game_stats)
            auto_complete = check_challenge_completion(daily_challenge, content, len(entry.mentioned_contacts))

            if auto_complete is True or auto_complete is None:
                challenge_bonus = daily_challenge.get('xp_bonus', 20)
                game_stats.challenge_completed_today = True
                game_stats.challenges_completed += 1
                game_stats.xp += challenge_bonus
                flash(f'🎯 Challenge Complete: {daily_challenge["title"]}! +{challenge_bonus} bonus XP', 'success')

        db.session.commit()
        flash('Journal entry updated!', 'success')

    return redirect(url_for('journal_entry', date_str=date_str))


@app.route('/journal/today')
def journal_today():
    """Redirect to today's journal entry"""
    today = datetime.now().date().strftime('%Y-%m-%d')
    return redirect(url_for('journal_entry', date_str=today))


@app.route('/journal/export')
def journal_export():
    """Export all journal entries"""
    format_type = request.args.get('format', 'markdown')
    entries = JournalEntry.query.order_by(JournalEntry.date.desc()).all()

    if format_type == 'markdown':
        content = "# My Journal\n\n"
        content += f"*Exported on {datetime.now().strftime('%B %d, %Y')}*\n\n---\n\n"

        for entry in entries:
            content += f"## {entry.date.strftime('%A, %B %d, %Y')}\n\n"
            if entry.mood:
                content += f"**Mood:** {entry.mood}\n\n"
            if entry.mentioned_contacts:
                names = [c.full_name for c in entry.mentioned_contacts]
                content += f"**People mentioned:** {', '.join(names)}\n\n"
            content += f"{entry.content}\n\n---\n\n"

        return Response(
            content,
            mimetype='text/markdown',
            headers={'Content-Disposition': 'attachment; filename=journal_export.md'}
        )

    elif format_type == 'txt':
        content = "MY JOURNAL\n"
        content += f"Exported on {datetime.now().strftime('%B %d, %Y')}\n"
        content += "=" * 50 + "\n\n"

        for entry in entries:
            content += f"{entry.date.strftime('%A, %B %d, %Y')}\n"
            content += "-" * 30 + "\n"
            if entry.mood:
                content += f"Mood: {entry.mood}\n"
            if entry.mentioned_contacts:
                names = [c.full_name for c in entry.mentioned_contacts]
                content += f"People mentioned: {', '.join(names)}\n"
            content += f"\n{entry.content}\n\n"
            content += "=" * 50 + "\n\n"

        return Response(
            content,
            mimetype='text/plain',
            headers={'Content-Disposition': 'attachment; filename=journal_export.txt'}
        )

    elif format_type == 'html':
        content = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<title>My Journal</title>
<style>
body { font-family: Georgia, serif; max-width: 800px; margin: 40px auto; padding: 20px; line-height: 1.8; }
h1 { color: #2D3748; border-bottom: 2px solid #3182CE; padding-bottom: 10px; }
h2 { color: #4A5568; margin-top: 40px; }
.mood { color: #718096; font-style: italic; }
.mentions { color: #3182CE; font-size: 0.9em; }
.entry-content { margin: 20px 0; white-space: pre-wrap; }
hr { border: none; border-top: 1px solid #E2E8F0; margin: 30px 0; }
</style></head><body>
"""
        content += f"<h1>My Journal</h1>\n<p><em>Exported on {datetime.now().strftime('%B %d, %Y')}</em></p>\n"

        for entry in entries:
            content += f"<h2>{entry.date.strftime('%A, %B %d, %Y')}</h2>\n"
            if entry.mood:
                content += f'<p class="mood">{entry.mood}</p>\n'
            if entry.mentioned_contacts:
                names = [c.full_name for c in entry.mentioned_contacts]
                content += f'<p class="mentions">People mentioned: {", ".join(names)}</p>\n'
            escaped_content = entry.content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            content += f'<div class="entry-content">{escaped_content}</div>\n<hr>\n'

        content += "</body></html>"

        return Response(
            content,
            mimetype='text/html',
            headers={'Content-Disposition': 'attachment; filename=journal_export.html'}
        )

    return redirect(url_for('journal_list'))


# ===== API ROUTES =====

@app.route('/api/contacts/search')
def api_contacts_search():
    """API endpoint for contact search (for autocomplete)"""
    query = request.args.get('q', '')
    contacts = Contact.query.filter(
        (Contact.first_name.contains(query)) |
        (Contact.last_name.contains(query))
    ).limit(10).all()

    return jsonify([{
        'id': c.id,
        'name': c.full_name
    } for c in contacts])


# ===== CLAUDE AI ROUTES =====

@app.route('/api/claude/reflect', methods=['POST'])
def claude_reflect():
    """Get Claude's reflection on a journal entry and save it"""
    if not claude_client:
        return jsonify({'error': 'Claude API not configured'}), 500

    data = request.json
    content = data.get('content', '')
    mood = data.get('mood', '')
    date_str = data.get('date', '')
    save = data.get('save', True)  # Save by default

    if not content.strip():
        return jsonify({'error': 'No content to reflect on'}), 400

    # Fetch recent journal entries for historical context
    history_context = ""
    try:
        current_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
        past_entries = JournalEntry.query.filter(
            JournalEntry.date < current_date,
            JournalEntry.content.isnot(None),
            JournalEntry.content != ''
        ).order_by(JournalEntry.date.desc()).limit(14).all()

        if past_entries:
            history_parts = []
            for e in reversed(past_entries):  # chronological order
                entry_mood = f" | Mood: {e.mood}" if e.mood else ""
                history_parts.append(f"[{e.date.strftime('%Y-%m-%d')}{entry_mood}]\n{e.content}")
            history_context = "\n\n---\n\n".join(history_parts)
    except Exception:
        pass  # Continue without history if query fails

    prompt = f"""You are a licensed psychologist serving as this person's ongoing therapist. You have been reading their journal over the past weeks and today they share a new entry with you.

{"== PREVIOUS JOURNAL ENTRIES (for context — do NOT summarize these) ==" + chr(10) + history_context + chr(10) + chr(10) if history_context else ""}== TODAY'S ENTRY ==
Date: {date_str}
Mood: {mood}

{content}

== YOUR TASK ==
Write a personal, thoughtful reflection as their psychologist. Key principles:

1. CONTINUITY: Reference specific things from their previous entries when relevant. Notice evolution — are they making progress on something? Is a worry from last week resolving? Has their mood shifted? Don't treat today in isolation.
2. PATTERNS: Gently surface recurring themes, behaviors, or emotional patterns you've noticed across entries. Name them specifically rather than being vague.
3. PERSONAL: Use details from THEIR life — names they mention, projects, relationships, struggles. Never give generic advice that could apply to anyone.
4. DEPTH: Go beyond surface observations. Connect dots they might not see. A good therapist notices what's unsaid as much as what's said.
5. ONE QUESTION: End with one precise, thought-provoking question rooted in what you've observed across their entries — not a generic "how does that make you feel?" but something that shows you've been paying attention.

Tone: Warm but professional. Insightful, not preachy. Speak as someone who genuinely knows them and their story. 2-3 paragraphs."""

    try:
        message = call_claude('journal', 'reflect',
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        reflection = message.content[0].text

        # Save reflection to database if requested
        if save and date_str:
            try:
                entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                entry = JournalEntry.query.filter_by(date=entry_date).first()
                if entry:
                    entry.claude_reflection = reflection
                    db.session.commit()
            except Exception:
                pass  # Don't fail if saving doesn't work

        return jsonify({'reflection': reflection})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/claude/improve', methods=['POST'])
def claude_improve():
    """Get Claude's suggestions to improve writing"""
    if not claude_client:
        return jsonify({'error': 'Claude API not configured'}), 500

    data = request.json
    content = data.get('content', '')

    if not content.strip():
        return jsonify({'error': 'No content to improve'}), 400

    prompt = f"""You are a gentle writing coach. The user has written this journal entry:

{content}

Please suggest improvements while keeping their voice and meaning intact. You might:
- Fix any grammar or spelling issues
- Suggest more vivid or specific words
- Help clarify confusing sentences
- Add sensory details where appropriate

Return your response in this format:
1. First, give 2-3 brief, specific suggestions
2. Then provide an "Enhanced version:" that incorporates your suggestions while maintaining their personal voice

Be encouraging and respectful - this is their personal journal."""

    try:
        message = call_claude('journal', 'improve',
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        return jsonify({'suggestions': message.content[0].text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/claude/verify-challenge', methods=['POST'])
def claude_verify_challenge():
    """Have Claude verify if a challenge was completed"""
    if not claude_client:
        return jsonify({'error': 'Claude API not configured'}), 500

    data = request.json
    content = data.get('content', '')
    challenge_title = data.get('challenge_title', '')
    challenge_description = data.get('challenge_description', '')

    if not content.strip():
        return jsonify({'error': 'No content to verify'}), 400

    prompt = f"""You are a fair but encouraging judge for a journaling challenge.

The challenge was:
Title: {challenge_title}
Description: {challenge_description}

The user's journal entry:
{content}

Did the user complete this challenge? Consider:
- Be generous - if they made a genuine attempt, that counts
- Look for the spirit of the challenge, not just the letter
- If it's close but not quite, give them credit anyway

Respond with JSON only:
{{"completed": true/false, "reason": "Brief encouraging explanation (1-2 sentences)"}}"""

    try:
        message = call_claude('journal', 'verify_challenge',
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = message.content[0].text
        # Parse JSON from response
        try:
            result = json.loads(response_text)
        except (json.JSONDecodeError, ValueError):
            # Try to extract JSON if wrapped in other text
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = {"completed": True, "reason": "Great effort on the challenge!"}
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/claude/chat', methods=['POST'])
def claude_chat():
    """Have a conversation with Claude about the journal entry"""
    if not claude_client:
        return jsonify({'error': 'Claude API not configured'}), 500

    data = request.json
    content = data.get('content', '')
    user_message = data.get('message', '')
    chat_history = data.get('history', [])

    system_prompt = f"""You are a warm, thoughtful journal companion. The user is reflecting on their journal entry with you.

Their journal entry for context:
{content}

Be conversational, empathetic, and insightful. Ask follow-up questions when appropriate. Keep responses concise (2-3 sentences usually). You're like a wise friend who's genuinely interested in their life."""

    messages = []
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    try:
        message = call_claude('journal', 'chat',
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=system_prompt,
            messages=messages
        )
        return jsonify({'response': message.content[0].text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ===== LEARNING ROULETTE ROUTES =====

# Learning content templates by topic and level
LEARNING_TOPICS = {
    "Space & Astronomy": {
        "beginner": [
            {"title": "The Solar System Basics", "content": "Our solar system consists of the Sun and everything that orbits it...\n\n## Key Facts\n- 8 planets orbit our Sun\n- The inner planets (Mercury, Venus, Earth, Mars) are rocky\n- The outer planets (Jupiter, Saturn, Uranus, Neptune) are gas giants\n\n## Activity\nTry to memorize the order of planets using: **My Very Eager Mother Just Served Us Nachos**"},
            {"title": "What is a Star?", "content": "Stars are massive balls of hot gas that produce light and heat through nuclear fusion...\n\n## How Stars Work\n- Hydrogen atoms fuse to form helium\n- This releases enormous amounts of energy\n- Our Sun is a medium-sized yellow dwarf star\n\n## Fun Fact\nThe Sun contains 99.86% of all mass in our solar system!"},
            {"title": "The Moon and Its Phases", "content": "The Moon is Earth's only natural satellite...\n\n## Moon Phases\n1. New Moon\n2. Waxing Crescent\n3. First Quarter\n4. Waxing Gibbous\n5. Full Moon\n6. Waning Gibbous\n7. Last Quarter\n8. Waning Crescent\n\n## Activity\nStep outside tonight and identify the current moon phase!"},
        ],
        "intermediate": [
            {"title": "Black Holes Explained", "content": "Black holes are regions where gravity is so strong that nothing can escape...\n\n## Types of Black Holes\n- **Stellar black holes**: Formed from collapsed stars\n- **Supermassive black holes**: Found at galaxy centers\n- **Primordial black holes**: Theoretical, from the Big Bang\n\n## The Event Horizon\nThe point of no return around a black hole is called the event horizon."},
            {"title": "Exoplanets: Worlds Beyond", "content": "Exoplanets are planets that orbit stars outside our solar system...\n\n## Detection Methods\n- Transit method (dimming of starlight)\n- Radial velocity (stellar wobble)\n- Direct imaging\n\n## Notable Exoplanets\n- Proxima Centauri b: Closest to Earth\n- TRAPPIST-1 system: 7 Earth-sized planets"},
        ],
        "advanced": [
            {"title": "Dark Matter and Dark Energy", "content": "The universe is mostly made of things we cannot see...\n\n## Dark Matter (~27%)\n- Doesn't emit light but has gravitational effects\n- Holds galaxies together\n- Detected through gravitational lensing\n\n## Dark Energy (~68%)\n- Causes the universe to expand faster\n- Discovered in 1998\n- One of physics' greatest mysteries"},
        ]
    },
    "Robotics & AI": {
        "beginner": [
            {"title": "What is a Robot?", "content": "A robot is a machine that can carry out tasks automatically...\n\n## Key Components\n- **Sensors**: Eyes and ears of the robot\n- **Actuators**: Muscles that create movement\n- **Controller**: The brain that processes information\n\n## Types of Robots\n- Industrial robots (manufacturing)\n- Service robots (vacuums, assistants)\n- Exploratory robots (Mars rovers)"},
            {"title": "Introduction to AI", "content": "Artificial Intelligence is the simulation of human intelligence by machines...\n\n## AI Categories\n- **Narrow AI**: Specialized tasks (like Siri)\n- **General AI**: Human-level intelligence (theoretical)\n- **Super AI**: Beyond human intelligence (sci-fi)\n\n## AI in Daily Life\nYou interact with AI through recommendations, voice assistants, and autocorrect!"},
        ],
        "intermediate": [
            {"title": "Machine Learning Basics", "content": "Machine Learning is how computers learn from data...\n\n## Types of Learning\n- **Supervised**: Learning from labeled examples\n- **Unsupervised**: Finding patterns in unlabeled data\n- **Reinforcement**: Learning through trial and error\n\n## Applications\n- Image recognition\n- Language translation\n- Game playing (like chess)"},
        ],
        "advanced": [
            {"title": "Neural Networks Deep Dive", "content": "Neural networks are inspired by the human brain...\n\n## Architecture\n- Input layer (receives data)\n- Hidden layers (process information)\n- Output layer (produces results)\n\n## Deep Learning\nNetworks with many hidden layers can learn complex patterns like faces and speech."},
        ]
    },
    "Finance & Investing": {
        "beginner": [
            {"title": "Budgeting 101", "content": "A budget is a plan for your money...\n\n## The 50/30/20 Rule\n- **50%** Needs (rent, food, utilities)\n- **30%** Wants (entertainment, dining)\n- **20%** Savings and debt repayment\n\n## Getting Started\n1. Track your spending for a month\n2. Categorize expenses\n3. Set realistic limits"},
            {"title": "Understanding Compound Interest", "content": "Compound interest is interest on interest...\n\n## The Magic Formula\n**A = P(1 + r/n)^(nt)**\n\n## Example\n$1,000 at 7% for 30 years = $7,612!\n\n## Key Insight\nStart investing early - time is your greatest asset."},
        ],
        "intermediate": [
            {"title": "Stock Market Fundamentals", "content": "The stock market is where shares of companies are bought and sold...\n\n## Key Concepts\n- **Stock**: Ownership in a company\n- **Dividend**: Share of profits paid to shareholders\n- **Index**: Basket of stocks (S&P 500, NASDAQ)\n\n## Investment Strategies\n- Buy and hold\n- Dollar-cost averaging\n- Diversification"},
        ],
        "advanced": [
            {"title": "Portfolio Theory", "content": "Modern Portfolio Theory optimizes risk vs. return...\n\n## Key Principles\n- Diversification reduces risk\n- Risk and return are related\n- The efficient frontier maximizes return for given risk\n\n## Asset Allocation\nBalance stocks, bonds, and alternatives based on goals and risk tolerance."},
        ]
    },
    "Psychology & Mind": {
        "beginner": [
            {"title": "Introduction to Psychology", "content": "Psychology is the scientific study of mind and behavior...\n\n## Major Perspectives\n- **Behavioral**: Focus on observable actions\n- **Cognitive**: Mental processes and thinking\n- **Biological**: Brain and nervous system\n- **Social**: How others influence us\n\n## Fun Fact\nThe term 'psychology' comes from Greek: psyche (soul) + logos (study)"},
            {"title": "Understanding Emotions", "content": "Emotions are complex psychological states...\n\n## Basic Emotions (Paul Ekman)\n- Happiness\n- Sadness\n- Fear\n- Anger\n- Surprise\n- Disgust\n\n## Emotional Intelligence\nRecognizing and managing emotions is key to well-being and relationships."},
        ],
        "intermediate": [
            {"title": "Cognitive Biases", "content": "Our brains take mental shortcuts that can lead to errors...\n\n## Common Biases\n- **Confirmation bias**: Seeking info that confirms beliefs\n- **Anchoring**: Over-relying on first information\n- **Availability heuristic**: Judging by easy examples\n\n## Why It Matters\nAwareness of biases helps make better decisions."},
        ],
        "advanced": [
            {"title": "The Science of Habits", "content": "Habits are automatic behaviors formed through repetition...\n\n## The Habit Loop\n1. **Cue**: Trigger for the behavior\n2. **Routine**: The behavior itself\n3. **Reward**: Benefit that reinforces it\n\n## Changing Habits\n- Keep the cue and reward\n- Change only the routine\n- Use implementation intentions"},
        ]
    },
    "History & Civilization": {
        "beginner": [
            {"title": "Ancient Egypt Overview", "content": "Ancient Egypt flourished along the Nile for 3,000 years...\n\n## Key Achievements\n- Pyramids of Giza\n- Hieroglyphic writing\n- Mummification\n- Advanced medicine\n\n## The Nile\nThe annual flooding brought fertile soil, enabling agriculture in the desert."},
            {"title": "The Roman Empire", "content": "Rome grew from a small city to a vast empire...\n\n## Timeline\n- 753 BC: Rome founded (legend)\n- 509 BC: Roman Republic begins\n- 27 BC: Empire begins with Augustus\n- 476 AD: Western Empire falls\n\n## Legacy\nLaw, architecture, language (Latin), and governance still influence us today."},
        ],
        "intermediate": [
            {"title": "The Renaissance", "content": "The Renaissance was a cultural rebirth in Europe (14th-17th century)...\n\n## Key Features\n- Humanism: Focus on human potential\n- Art: Perspective and realism\n- Science: Observation and experiment\n\n## Notable Figures\n- Leonardo da Vinci\n- Michelangelo\n- Galileo Galilei"},
        ],
        "advanced": [
            {"title": "Industrial Revolution Impact", "content": "The Industrial Revolution transformed human society...\n\n## Changes\n- **Economic**: Factory system, capitalism\n- **Social**: Urbanization, new classes\n- **Technological**: Steam power, machines\n\n## Long-term Effects\nSet the stage for modern economy, but also environmental challenges."},
        ]
    },
    "Esports & Gaming": {
        "beginner": [
            {"title": "What is Esports?", "content": "Esports is competitive video gaming at a professional level...\n\n## Popular Games\n- League of Legends\n- Counter-Strike\n- Dota 2\n- Valorant\n- Fortnite\n\n## The Scene\n- Professional teams and leagues\n- Millions in prize money\n- Global audience of 500M+"},
        ],
        "intermediate": [
            {"title": "Game Strategy Fundamentals", "content": "Winning in competitive games requires strategic thinking...\n\n## Key Concepts\n- **Macro**: Big-picture decisions\n- **Micro**: Mechanical execution\n- **Meta**: Current optimal strategies\n\n## Improvement Tips\n- Review your replays\n- Focus on one thing at a time\n- Practice deliberately"},
        ],
        "advanced": [
            {"title": "The Business of Esports", "content": "Esports is a billion-dollar industry...\n\n## Revenue Streams\n- Sponsorships\n- Media rights\n- Merchandise\n- Ticket sales\n\n## Career Paths\n- Pro player\n- Coach/analyst\n- Caster/host\n- Content creator"},
        ]
    },
    "Video Game Design": {
        "beginner": [
            {"title": "Game Design Fundamentals", "content": "Game design is the art of creating interactive experiences...\n\n## Core Elements\n- **Mechanics**: Rules and systems\n- **Dynamics**: How mechanics create experiences\n- **Aesthetics**: Emotional responses\n\n## The Fun Factor\nGames should provide challenge, discovery, and satisfaction."},
        ],
        "intermediate": [
            {"title": "Level Design Principles", "content": "Good level design guides and challenges players...\n\n## Key Principles\n- **Flow**: Natural progression\n- **Pacing**: Tension and release\n- **Teaching**: Show, don't tell\n\n## Tools\n- Paper prototyping\n- Blockout/graybox\n- Playtesting"},
        ],
        "advanced": [
            {"title": "Narrative in Games", "content": "Games tell stories through interactivity...\n\n## Storytelling Methods\n- **Environmental**: World tells the story\n- **Emergent**: Player-created narratives\n- **Embedded**: Written/scripted content\n\n## Player Agency\nBalance story control with player freedom."},
        ]
    },
    "Science & Discovery": {
        "beginner": [
            {"title": "The Scientific Method", "content": "Science is a systematic way of learning about the world...\n\n## Steps\n1. Observation\n2. Question\n3. Hypothesis\n4. Experiment\n5. Analysis\n6. Conclusion\n\n## Key Principle\nHypotheses must be testable and falsifiable."},
        ],
        "intermediate": [
            {"title": "DNA and Genetics", "content": "DNA contains the instructions for life...\n\n## Structure\n- Double helix shape\n- 4 bases: A, T, G, C\n- Base pairs encode information\n\n## Genes to Traits\nGenes are sections of DNA that code for proteins, which determine traits."},
        ],
        "advanced": [
            {"title": "Quantum Mechanics Intro", "content": "Quantum mechanics describes the very small...\n\n## Key Concepts\n- **Wave-particle duality**: Light acts as both\n- **Uncertainty principle**: Can't know position and momentum precisely\n- **Superposition**: Particles in multiple states\n\n## Applications\nQuantum computing, cryptography, and sensing."},
        ]
    }
}


def get_learning_content(interest_name, level):
    """Get random learning content for an interest and level"""
    topics = LEARNING_TOPICS.get(interest_name, {})
    level_topics = topics.get(level, [])

    if not level_topics:
        # Fallback to beginner if level not available
        level_topics = topics.get('beginner', [])

    if level_topics:
        return random.choice(level_topics)

    # Default fallback content
    return {
        "title": f"Exploring {interest_name}",
        "content": f"Today we'll explore an interesting aspect of {interest_name}.\n\n## Your Task\nSpend 30 minutes researching this topic online and write down 3 new things you learned.\n\n## Reflection\nHow does this connect to what you already know?"
    }


@app.route('/learn')
def learn():
    """Learning dashboard with roulette"""
    game_stats = get_or_create_game_stats()
    interests = LearningInterest.query.filter_by(is_active=True).all()

    # Check if already spun today
    today = datetime.now().date()
    today_session = LearningSession.query.filter_by(date=today).first()

    # Get all sessions
    recent_sessions = LearningSession.query.filter(LearningSession.content.isnot(None)).order_by(LearningSession.date.desc()).all()

    # Get achievements related to learning
    unlocked_ids = get_unlocked_achievements(game_stats)

    return render_template('learning.html',
                         game_stats=game_stats,
                         interests=interests,
                         today_session=today_session,
                         recent_sessions=recent_sessions,
                         unlocked_ids=unlocked_ids)


def generate_learning_content_with_claude(topic_name, level, description="", length="full"):
    """Generate learning content using Claude. length='full' (~5000 words, 30 min) or 'half' (~2500 words, 15 min)"""
    if not claude_client:
        return None

    level_context = {
        'beginner': {
            'tone': 'welcoming and encouraging, assuming no prior knowledge',
            'depth': 'foundational concepts explained from scratch with lots of analogies and real-world parallels',
            'vocab': 'simple language, define all technical terms when first introduced',
            'sources_style': 'introductory books, popular science articles, accessible YouTube channels, beginner-friendly courses',
            'go_further': 'Recommend beginner-friendly resources: popular science books, short YouTube explainer series, introductory online courses (Coursera, Khan Academy), and accessible articles.'
        },
        'intermediate': {
            'tone': 'collegial and engaging, assuming basic familiarity with the fundamentals',
            'depth': 'deeper exploration with nuance, technical detail, and analysis of underlying mechanisms',
            'vocab': 'can use domain terminology with brief reminders of definitions',
            'sources_style': 'academic overviews, well-regarded textbooks, established university courses, and reputable publications',
            'go_further': 'Recommend intermediate resources: university-level textbooks, academic review articles, specialized online courses (MIT OCW, edX), conference talks, and in-depth essays.'
        },
        'advanced': {
            'tone': 'intellectual peer discussion, assuming solid foundation and familiarity with core concepts',
            'depth': 'cutting-edge concepts, recent research findings, complex analysis, and open questions in the field',
            'vocab': 'full technical vocabulary, focus on novel insights and frontier knowledge',
            'sources_style': 'research papers, expert talks, specialized journals, and advanced monographs',
            'go_further': 'Recommend advanced resources: seminal research papers, PhD-level textbooks, specialist journals, expert lectures, and cutting-edge preprints (arXiv, SSRN).'
        }
    }

    ctx = level_context.get(level, level_context['beginner'])

    # Adjust structure based on length
    if length == 'half':
        word_target = '2,500-3,000 words'
        time_target = '15-20 minutes'
        min_words = '2,500'
        structure_block = f"""### 1. Opening Hook (150-200 words)
Start with something captivating - a surprising fact, a thought-provoking question, or a counterintuitive insight. Briefly preview what they'll learn.

### 2. Why This Matters (200-300 words)
Explain the significance of this topic. How does it connect to the bigger picture? Reference trustworthy sources.

### 3. Core Content: Deep Dive (1,500-1,800 words)
The meat of the article. Organize into **3-4 major sections**, each exploring a key aspect:

For each section:
- Start with the main concept
- Explain the "why" behind it, not just the "what"
- Use concrete examples or analogies
- **Cite trustworthy sources**: reference specific researchers, institutions, studies, books, or publications by name
- Connect ideas to what came before

Cover the most important angles:
- The fundamental principles or mechanisms
- Real-world applications and examples
- Current developments or recent discoveries
- Practical implications for everyday life

### 4. Key Takeaways (200-300 words)
Synthesize the most important points. Frame these as insights, not just facts. Make them memorable and actionable.

### 5. Go Further: Resources & Links (200-300 words)
Provide **3-5 specific resources** for the reader to continue learning, matched to their level ({level}). For each resource include:
- The exact name/title
- The author or institution
- A one-sentence description of why it's valuable
- The URL if it's an online resource

{ctx['go_further']}

Format this section as a numbered list with markdown links where applicable."""
        max_tokens = 6000
    else:
        word_target = '5,000-6,000 words'
        time_target = '30-40 minutes'
        min_words = '5,000'
        structure_block = f"""### 1. Opening Hook (300-400 words)
Start with something captivating - a surprising fact, a thought-provoking question, a brief story, or a counterintuitive insight. Make the reader immediately curious. Then briefly preview what they'll learn in this session.

### 2. Foundation: "Why This Matters" (400-500 words)
Explain the significance of this topic. How does it connect to the bigger picture? Why should someone invest time learning about it? Include real-world relevance and practical implications. Reference trustworthy sources (institutions, researchers, books) to ground the importance.

### 3. Core Content: Deep Dive (3,000-3,500 words)
This is the meat of the article. Organize into **5-7 major sections**, each exploring a key aspect in depth:

For each section:
- Start with the main concept
- Explain the "why" behind it, not just the "what"
- Use concrete examples, analogies, or mini case studies
- **Cite trustworthy sources**: reference specific researchers, institutions, studies, books, or publications by name (e.g., "According to Dr. Jane Smith at Stanford...", "A 2024 Nature study found...", "As described in [Book Title] by [Author]...")
- Connect ideas to what came before
- Include interesting tangents or "did you know" moments

Cover a diverse range of angles:
- Historical context / how we got here
- The fundamental principles or mechanisms
- Common misconceptions and the truth behind them
- Real-world applications and examples
- Current developments or recent discoveries
- Different perspectives or ongoing debates in the field
- Practical implications for everyday life
- Connections to adjacent fields or disciplines

### 4. Expert Insights & Nuances (500-600 words)
Share deeper knowledge that goes beyond surface-level understanding:
- Nuances that most explanations miss
- Surprising connections to other fields
- Predictions about future developments
- Thought experiments or hypotheticals
- Open questions researchers are still debating

### 5. Key Takeaways (300-400 words)
Synthesize the most important points. What should stick with the reader? Frame these as insights, not just facts. Make them memorable and actionable.

### 6. Go Further: Resources & Links (300-400 words)
This section is critical. Provide **6-10 specific resources** for the reader to continue learning, matched to their level ({level}). For each resource include:
- The exact name/title
- The author or institution
- A one-sentence description of why it's valuable
- The URL if it's an online resource (use real, well-known URLs like Wikipedia articles, Khan Academy lessons, MIT OCW courses, YouTube channels, official websites, etc.)

{ctx['go_further']}

Format this section as a numbered list with markdown links where applicable."""
        max_tokens = 12000

    prompt = f"""You are creating an in-depth educational article about **{topic_name}** for a personal learning app.

{"Context: " + description if description else ""}
Reader Level: {level.upper()} - {ctx['tone']}

## Your Task

Write a comprehensive, engaging educational piece of approximately **{word_target}**. This should feel like an enlightening deep-dive with a knowledgeable friend who's passionate about this subject. The reader should need {time_target} to read it thoughtfully.

## Structure Requirements

{structure_block}

## Writing Style

- **Conversational but substantive**: Write like you're explaining to a curious friend, not lecturing
- **Use {ctx['vocab']}**
- **Depth level**: {ctx['depth']}
- **Include vivid examples**: Abstract concepts need concrete illustrations
- **Vary your rhythm**: Mix shorter punchy sentences with longer explanatory ones
- **Use markdown well**: Headers (##, ###), **bold** for key terms, bullet points for lists, > blockquotes for important insights or quotes
- **Add "mental hooks"**: Surprising facts, memorable analogies, relatable scenarios
- **Cite sources naturally throughout**: When mentioning research, studies, or expert opinions, name the source. Use {ctx['sources_style']}.

## Critical Requirements

- This must be SUBSTANTIAL - a real {time_target} read, **at least {min_words} words**
- Every paragraph should teach something or provide value
- Avoid fluff, repetition, or padding - make every sentence count
- The reader should finish feeling like they genuinely learned something significant
- Sources must be real and trustworthy - do not invent fake studies or authors
- The "Go Further" section must contain real, accessible resources with working URLs where possible

Begin the article with a compelling title formatted as: # [Title]"""

    try:
        message = call_claude('learning', 'generate_article',
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        print(f"Error generating content: {e}")
        return None


@app.route('/learn/spin', methods=['POST'])
def learn_spin():
    """Spin the roulette and create a session - instant response, content generated later"""
    today = datetime.now().date()

    # Check if already spun today
    existing_session = LearningSession.query.filter_by(date=today).first()

    # If existing session has no content and isn't completed, delete it so user can retry
    if existing_session and not existing_session.content and not existing_session.completed:
        db.session.delete(existing_session)
        db.session.commit()
        existing_session = None

    if existing_session:
        return jsonify({
            'success': True,
            'interest': existing_session.interest.name,
            'icon': existing_session.interest.icon,
            'session_id': existing_session.id,
            'topic': existing_session.topic_title,
            'level': existing_session.difficulty_level,
            'existing': True
        })

    # Get active interests
    interests = LearningInterest.query.filter_by(is_active=True).all()
    if not interests:
        return jsonify({'success': False, 'error': 'No active interests'})

    # Pick a random interest with weighted randomization (less selected = higher chance)
    total_selections = sum(i.times_selected + 1 for i in interests)
    weights = [(total_selections - i.times_selected) for i in interests]
    selected = random.choices(interests, weights=weights, k=1)[0]
    selected.times_selected += 1

    # Calculate XP based on level
    xp_map = {'beginner': 25, 'intermediate': 40, 'advanced': 60}
    xp_reward = xp_map.get(selected.current_level, 25)

    # Create session with placeholder - content generated when viewing
    session = LearningSession(
        interest_id=selected.id,
        date=today,
        topic_title=f"Loading: {selected.name}",
        content=None,  # Will be generated lazily
        difficulty_level=selected.current_level,
        estimated_time=30,
        xp_earned=xp_reward
    )
    db.session.add(session)
    db.session.commit()

    return jsonify({
        'success': True,
        'interest': selected.name,
        'icon': selected.icon,
        'session_id': session.id,
        'topic': f"Exploring {selected.name}",
        'level': selected.current_level
    })


@app.route('/learn/session/<int:session_id>')
def learn_session(session_id):
    """View/start a learning session - shows loading page if content not yet generated"""
    session = LearningSession.query.get_or_404(session_id)
    interest = session.interest
    game_stats = get_or_create_game_stats()

    # If content not yet generated, show the loading page
    if not session.content:
        return render_template('learning_loading.html',
                             session=session,
                             interest=interest)

    return render_template('learning_session.html',
                         session=session,
                         interest=interest,
                         game_stats=game_stats)


@app.route('/api/learn/set-length/<int:session_id>', methods=['POST'])
def learn_set_length(session_id):
    """Set session length (full or half) before content generation"""
    session = LearningSession.query.get_or_404(session_id)
    data = request.get_json() or {}
    length = data.get('length', 'full')
    if length == 'half':
        session.estimated_time = 15
    else:
        session.estimated_time = 30
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/learn/generate/<int:session_id>', methods=['POST'])
def learn_generate_content(session_id):
    """API endpoint to trigger content generation for a session"""
    session = LearningSession.query.get_or_404(session_id)
    interest = session.interest

    # Already generated
    if session.content:
        return jsonify({'status': 'ready'})

    # Generate content
    length = 'half' if session.estimated_time == 15 else 'full'
    generated_content = generate_learning_content_with_claude(
        interest.name,
        session.difficulty_level,
        interest.description,
        length=length
    )

    if generated_content:
        lines = generated_content.strip().split('\n')
        title = lines[0].replace('#', '').strip() if lines else f"Exploring {interest.name}"
        session.topic_title = title
        session.content = generated_content
    else:
        # Fallback content
        session.topic_title = f"Introduction to {interest.name}"
        session.content = f"""# Introduction to {interest.name}

Welcome to today's learning session! We'll explore the fascinating world of {interest.name}.

## Overview

{interest.description or f'{interest.name} is a rich topic with many interesting aspects to discover.'}

## Key Concepts

This content is being generated. If you see this message, there may have been an issue with content generation. Please try refreshing the page or spinning again tomorrow.

## Next Steps

- Explore online resources about {interest.name}
- Take notes on what interests you most
- Come back tomorrow for a new topic!
"""
    db.session.commit()
    return jsonify({'status': 'ready'})


@app.route('/api/learn/status/<int:session_id>')
def learn_check_status(session_id):
    """Check if content generation is complete"""
    session = LearningSession.query.get_or_404(session_id)
    if session.content:
        return jsonify({'status': 'ready'})
    return jsonify({'status': 'generating'})


@app.route('/learn/complete/<int:session_id>', methods=['POST'])
def learn_complete(session_id):
    """Mark session as complete and award XP"""
    session = LearningSession.query.get_or_404(session_id)

    if session.completed:
        flash('Session already completed!', 'info')
        return redirect(url_for('learn'))

    # Mark complete
    session.completed = True
    session.completed_at = datetime.utcnow()
    session.notes = request.form.get('notes', '')

    # Update game stats
    game_stats = get_or_create_game_stats()
    game_stats.xp += session.xp_earned
    game_stats.learning_sessions_total = (game_stats.learning_sessions_total or 0) + 1
    game_stats.learning_xp_total = (game_stats.learning_xp_total or 0) + session.xp_earned

    # Update learning streak
    today = datetime.now().date()
    if game_stats.last_learning_date:
        days_diff = (today - game_stats.last_learning_date).days
        if days_diff == 1:
            game_stats.learning_streak = (game_stats.learning_streak or 0) + 1
        elif days_diff > 1:
            game_stats.learning_streak = 1
    else:
        game_stats.learning_streak = 1
    game_stats.last_learning_date = today

    # Update interest progress
    interest = session.interest
    progress = LearningProgress.query.filter_by(interest_id=interest.id).first()
    if not progress:
        progress = LearningProgress(
            interest_id=interest.id,
            sessions_completed=0,
            total_time_minutes=0,
            total_xp=0
        )
        db.session.add(progress)
    progress.sessions_completed = (progress.sessions_completed or 0) + 1
    progress.total_time_minutes = (progress.total_time_minutes or 0) + session.estimated_time
    progress.total_xp = (progress.total_xp or 0) + session.xp_earned

    # Note: Topic level progression is now handled by quiz pass/fail (66% threshold)
    # No longer based on session count

    db.session.commit()

    # Check for achievements
    new_achievements = check_achievements(game_stats)
    for achievement in new_achievements:
        flash(f'Achievement Unlocked: {achievement["name"]}!', 'success')
    db.session.commit()

    # Check for overall level up
    if check_level_up(game_stats):
        flash(f'LEVEL UP! You are now a {game_stats.level_name}! (Level {game_stats.level})', 'success')
        db.session.commit()

    flash(f'Session complete! +{session.xp_earned} XP', 'success')
    return redirect(url_for('learn'))


@app.route('/learn/interests')
def learn_interests():
    """Manage interests page"""
    interests = LearningInterest.query.all()
    return render_template('learning_interests.html', interests=interests)


@app.route('/learn/interests/add', methods=['POST'])
def learn_interests_add():
    """Add a new interest"""
    name = request.form.get('name', '').strip()
    icon = request.form.get('icon', '').strip() or '📚'
    description = request.form.get('description', '').strip()

    if not name:
        flash('Please enter a topic name.', 'error')
        return redirect(url_for('learn_interests'))

    # Check for duplicate
    existing = LearningInterest.query.filter_by(name=name).first()
    if existing:
        flash('This topic already exists!', 'warning')
        return redirect(url_for('learn_interests'))

    interest = LearningInterest(
        name=name,
        icon=icon,
        description=description,
        is_active=True,
        current_level='beginner'
    )
    db.session.add(interest)
    db.session.commit()

    flash(f'Added "{name}" to your learning interests!', 'success')
    return redirect(url_for('learn_interests'))


@app.route('/learn/interests/<int:interest_id>/toggle', methods=['POST'])
def learn_interests_toggle(interest_id):
    """Enable/disable an interest"""
    interest = LearningInterest.query.get_or_404(interest_id)
    interest.is_active = not interest.is_active
    db.session.commit()

    status = 'enabled' if interest.is_active else 'disabled'
    flash(f'{interest.name} {status}!', 'success')
    return redirect(url_for('learn_interests'))


@app.route('/api/learn/quiz/<int:session_id>', methods=['POST'])
def learn_generate_quiz(session_id):
    """Generate mixed quiz (MCQ + open questions) for a learning session"""
    if not claude_client:
        return jsonify({'error': 'Claude API not configured'}), 500

    session = LearningSession.query.get_or_404(session_id)

    # Check if quiz already exists
    if session.quiz_questions:
        return jsonify({'questions': json.loads(session.quiz_questions)})

    prompt = f"""Based on this learning content, create a knowledge test with mostly multiple-choice and one open-ended question.

Content:
{session.content[:4000]}

Create exactly 5 questions:
- 4 multiple-choice questions (type: "mcq") testing key concepts and understanding
- 1 open-ended question (type: "open") at the end, requiring the reader to synthesize and explain concepts in their own words

For MCQ questions: provide 4 options and include an explanation. IMPORTANT: vary the position of the correct answer — do NOT always put the correct answer in the same position. Spread correct answers across positions 0, 1, 2, and 3 randomly.
For the open question: provide 2-4 key points that a good answer should cover, and a max_score of 4.

The scoring works as follows:
- Each MCQ is worth 1 point (4 points total)
- The open question is worth up to 4 points
- Total: 8 points. The reader needs 66% (approximately 5.3/8) to pass.

Make questions that test genuine understanding, not trivial details. The open question should require synthesis and explanation, not just recall.

Return ONLY valid JSON in this exact format:
{{
    "questions": [
        {{
            "type": "mcq",
            "question": "The question text",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct": 2,
            "explanation": "Brief explanation of the correct answer"
        }},
        {{
            "type": "open",
            "question": "Explain in your own words...",
            "key_points": ["key point 1 a good answer should cover", "key point 2", "key point 3"],
            "max_score": 4
        }}
    ]
}}"""

    try:
        message = call_claude('learning', 'generate_quiz',
            model="claude-sonnet-4-20250514",
            max_tokens=2500,
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = message.content[0].text

        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            quiz_data = json.loads(json_match.group())
            # Shuffle MCQ answer positions to ensure randomization
            for q in quiz_data['questions']:
                if q.get('type') == 'mcq':
                    options = q['options']
                    correct_text = options[q['correct']]
                    random.shuffle(options)
                    q['correct'] = options.index(correct_text)
            session.quiz_questions = json.dumps(quiz_data['questions'])
            db.session.commit()
            return jsonify({'questions': quiz_data['questions']})
        else:
            return jsonify({'error': 'Failed to parse quiz'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/learn/quiz/<int:session_id>/submit', methods=['POST'])
def learn_submit_quiz(session_id):
    """Submit quiz answers (MCQ + open) and calculate score with Claude evaluation"""
    session = LearningSession.query.get_or_404(session_id)
    data = request.json
    answers = data.get('answers', [])  # Mixed: int for MCQ, string for open

    if not session.quiz_questions:
        return jsonify({'error': 'No quiz found'}), 400

    questions = json.loads(session.quiz_questions)
    results = []
    total_points = 0
    earned_points = 0

    # Separate MCQ and open questions for processing
    open_questions_to_evaluate = []

    for i, q in enumerate(questions):
        user_answer = answers[i] if i < len(answers) else ('' if q.get('type') == 'open' else -1)

        if q.get('type', 'mcq') == 'mcq':
            # MCQ: score instantly (1 point each)
            total_points += 1
            is_correct = user_answer == q['correct']
            if is_correct:
                earned_points += 1
            results.append({
                'type': 'mcq',
                'correct': is_correct,
                'user_answer': user_answer,
                'correct_answer': q['correct'],
                'explanation': q.get('explanation', ''),
                'points_earned': 1 if is_correct else 0,
                'max_points': 1
            })
        else:
            # Open: collect for batch Claude evaluation
            max_score = q.get('max_score', 3)
            total_points += max_score
            open_questions_to_evaluate.append({
                'index': i,
                'question': q['question'],
                'key_points': q.get('key_points', []),
                'max_score': max_score,
                'user_answer': str(user_answer)
            })
            # Placeholder result, will be updated after Claude eval
            results.append({
                'type': 'open',
                'user_answer': str(user_answer),
                'key_points': q.get('key_points', []),
                'points_earned': 0,
                'max_points': max_score,
                'feedback': 'Evaluating...'
            })

    # Evaluate open questions with Claude
    if open_questions_to_evaluate and claude_client:
        eval_prompt = "You are evaluating open-ended quiz answers from a learning session. Score each answer fairly.\n\n"
        for oq in open_questions_to_evaluate:
            eval_prompt += f"""---
Question: {oq['question']}
Key points a good answer should cover: {', '.join(oq['key_points'])}
Maximum score: {oq['max_score']}
Student's answer: "{oq['user_answer']}"
---

"""
        eval_prompt += f"""For each answer, evaluate how well it covers the key points. Be fair but rigorous.
An empty or irrelevant answer gets 0. A partial answer gets partial credit. A thorough answer covering all key points gets full marks.

Return ONLY valid JSON:
{{
    "evaluations": [
        {{
            "score": <number from 0 to max_score>,
            "feedback": "Brief specific feedback explaining the score and what was good or missing"
        }}
    ]
}}

Return exactly {len(open_questions_to_evaluate)} evaluations in the same order as the questions above."""

        try:
            eval_message = call_claude('learning', 'grade_quiz',
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                messages=[{"role": "user", "content": eval_prompt}]
            )
            eval_text = eval_message.content[0].text
            eval_match = re.search(r'\{[\s\S]*\}', eval_text)
            if eval_match:
                eval_data = json.loads(eval_match.group())
                evaluations = eval_data.get('evaluations', [])

                for j, oq in enumerate(open_questions_to_evaluate):
                    if j < len(evaluations):
                        ev = evaluations[j]
                        score_val = min(ev.get('score', 0), oq['max_score'])
                        earned_points += score_val
                        results[oq['index']]['points_earned'] = score_val
                        results[oq['index']]['feedback'] = ev.get('feedback', 'No feedback available.')
        except Exception as e:
            print(f"Error evaluating open questions: {e}")
            # If Claude eval fails, give partial credit (1 point) for non-empty answers
            for oq in open_questions_to_evaluate:
                if oq['user_answer'].strip():
                    earned_points += 1
                    results[oq['index']]['points_earned'] = 1
                    results[oq['index']]['feedback'] = 'Could not evaluate automatically. Partial credit awarded for providing an answer.'

    # Calculate overall score as percentage
    score_pct = int((earned_points / total_points) * 100) if total_points > 0 else 0
    session.quiz_score = score_pct
    passed = score_pct >= 66

    # Level progression: pass at 66% unlocks next level for this subject
    leveled_up = False
    new_level = None
    interest = session.interest
    if passed:
        if interest.current_level == 'beginner':
            interest.current_level = 'intermediate'
            leveled_up = True
            new_level = 'intermediate'
        elif interest.current_level == 'intermediate':
            interest.current_level = 'advanced'
            leveled_up = True
            new_level = 'advanced'
        # advanced stays advanced

    db.session.commit()

    return jsonify({
        'score': score_pct,
        'earned_points': earned_points,
        'total_points': total_points,
        'results': results,
        'passed': passed,
        'leveled_up': leveled_up,
        'new_level': new_level,
        'interest_name': interest.name if leveled_up else None
    })


@app.route('/api/learn/feedback/<int:session_id>', methods=['POST'])
def learn_submit_feedback(session_id):
    """Submit feedback on learning content"""
    session = LearningSession.query.get_or_404(session_id)
    data = request.json
    feedback = data.get('feedback', '')
    rating = data.get('rating', 0)

    session.feedback = json.dumps({'text': feedback, 'rating': rating})
    db.session.commit()

    return jsonify({'success': True})


# ===== HIGHLIGHTS =====

@app.route('/api/learn/highlight/<int:session_id>', methods=['POST'])
def save_highlight(session_id):
    """Save a text highlight from a learning session"""
    session = LearningSession.query.get_or_404(session_id)
    data = request.json
    text = data.get('text', '').strip()

    if not text:
        return jsonify({'error': 'No text provided'}), 400

    highlight = Highlight(session_id=session.id, text=text)
    db.session.add(highlight)
    db.session.commit()

    return jsonify({
        'id': highlight.id,
        'text': highlight.text,
        'created_at': highlight.created_at.isoformat()
    })


@app.route('/api/learn/highlight/<int:highlight_id>', methods=['DELETE'])
def delete_highlight(highlight_id):
    """Delete a saved highlight"""
    highlight = Highlight.query.get_or_404(highlight_id)
    db.session.delete(highlight)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/learn/highlights/<int:session_id>')
def get_session_highlights(session_id):
    """Get all highlights for a specific session (used by JS to restore marks)"""
    highlights = Highlight.query.filter_by(session_id=session_id).order_by(Highlight.created_at).all()
    return jsonify({
        'highlights': [{'id': h.id, 'text': h.text, 'created_at': h.created_at.isoformat()} for h in highlights]
    })


@app.route('/highlights')
def highlights_list():
    """Full page listing all saved highlights grouped by subject, then by session"""
    highlights = (Highlight.query
                  .join(LearningSession)
                  .join(LearningInterest)
                  .order_by(LearningInterest.name, LearningSession.date.desc(), Highlight.created_at)
                  .all())

    # Group by interest (subject), preserving session ordering within each group
    grouped = {}
    for h in highlights:
        interest = h.session.interest
        key = interest.id
        if key not in grouped:
            grouped[key] = {
                'interest': interest,
                'highlights': []
            }
        grouped[key]['highlights'].append(h)

    return render_template('highlights.html', grouped=grouped, total=len(highlights))


@app.route('/api/learn/enhance-interest', methods=['POST'])
def learn_enhance_interest():
    """Use Claude to enhance a new interest with description and icon"""
    if not claude_client:
        return jsonify({'error': 'Claude API not configured'}), 500

    data = request.json
    name = data.get('name', '').strip()

    if not name:
        return jsonify({'error': 'Topic name required'}), 400

    prompt = f"""For the learning topic "{name}", suggest:
1. A brief description (1-2 sentences) explaining what this topic covers
2. The best emoji icon to represent it

Return ONLY valid JSON:
{{"description": "Your description here", "icon": "emoji"}}"""

    try:
        message = call_claude('learning', 'enhance_interest',
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = message.content[0].text
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            result = json.loads(json_match.group())
            return jsonify(result)
        return jsonify({'description': '', 'icon': '📚'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ===== LOL WORDLE =====

# Curated list of 5-letter League of Legends words
LOL_WORDS = [
    # Champion names (5 letters)
    "teemo", "yasuo", "jayce", "janna", "kayle", "quinn", "nasus",
    "brand", "braum", "poppy", "garen", "senna", "sivir", "akali",
    "annie", "fiora", "vayne", "viego", "nasus", "corki", "darius",
    "diana", "draven", "elise", "evelynn", "ezreal",
    # Filter to exactly 5 letters only
    "ahri", "zyra", "bard", "gnar", "jhin", "kled", "lulu",
    "nami", "olaf", "ornn", "pyke", "rakan", "riven", "shaco",
    "senna", "sylas", "talon", "thresh", "twitch", "urgot",
    "varus", "xayah", "yuumi", "ziggs",
    # Game terms & slang
    "stomp", "ganks", "baron", "drake", "split", "tower", "nexus",
    "spawn", "flank", "carry", "siege", "penta", "smite", "flash",
    "fight", "build", "climb", "combo", "crush", "throw", "toxic",
    "dodge", "reset", "tempo", "feast", "trade", "scale", "draft",
    "macro", "micro", "elder", "kills", "death", "creep", "leash",
    "chill", "ahead", "tanks", "mages", "roams", "feeds", "wards",
    "plate", "grubs", "swarm", "first", "blood", "turbo", "hyper",
    "queue", "clash", "brawl", "arena", "lanes", "level", "items",
    "stuns", "roots", "heals", "armor", "magic", "power", "speed",
    "crest", "ocean", "cloud", "flame", "earth", "steel", "chemm",
    "force", "valor", "blitz", "mundo", "karma", "kennn", "leona",
    "lucin", "morde", "nauti", "renek", "sejua", "singe", "swain",
    "trund", "twstd", "veiga", "xerat", "yoric",
    # Items
    "boots", "blade", "staff", "cloak", "chain", "crown", "hydra",
    "spear", "armor", "sting",
]

# Filter to only valid 5-letter words, remove duplicates, lowercase
LOL_WORDS = sorted(set(w.lower() for w in LOL_WORDS if len(w) == 5))

# Also accept common English 5-letter words as valid guesses (but they won't be answers)
EXTRA_VALID_GUESSES = [
    "about", "above", "after", "again", "angel", "anger", "angle",
    "basic", "beach", "begin", "being", "below", "black", "blank",
    "blast", "blaze", "block", "board", "bonus", "boost", "bound",
    "break", "bring", "broad", "brush", "burst", "catch", "cause",
    "chain", "chair", "chase", "cheap", "check", "chest", "chief",
    "child", "claim", "class", "clean", "clear", "click", "climb",
    "close", "color", "count", "cover", "crack", "craft", "crash",
    "crazy", "cross", "crowd", "dance", "death", "delay", "depth",
    "dirty", "doubt", "draft", "drain", "dream", "dress", "drink",
    "drive", "early", "earth", "empty", "enemy", "enjoy", "enter",
    "equal", "error", "event", "every", "exact", "extra", "faith",
    "false", "fancy", "fatal", "favor", "fence", "fewer", "field",
    "final", "fixed", "flame", "flash", "fleet", "flesh", "float",
    "flood", "floor", "fluid", "focus", "force", "found", "frame",
    "fresh", "front", "fruit", "giant", "given", "glass", "gleam",
    "globe", "going", "grace", "grade", "grain", "grand", "grant",
    "grass", "grave", "great", "green", "grind", "gross", "group",
    "guard", "guess", "guide", "happy", "heart", "heavy", "hello",
    "horse", "hotel", "house", "human", "humor", "hurry", "ideal",
    "image", "imply", "index", "inner", "input", "issue", "ivory",
    "joint", "judge", "juice", "knock", "known", "label", "large",
    "laser", "later", "laugh", "layer", "learn", "least", "leave",
    "legal", "light", "limit", "links", "lives", "local", "logic",
    "loose", "lover", "lower", "lucky", "lunch", "magic", "major",
    "maker", "march", "match", "maybe", "mayor", "media", "mercy",
    "metal", "might", "minor", "minus", "mixed", "model", "money",
    "month", "moral", "motor", "mount", "mouse", "mouth", "movie",
    "music", "naked", "nerve", "never", "night", "noble", "noise",
    "north", "noted", "novel", "nurse", "occur", "ocean", "offer",
    "often", "order", "other", "outer", "owner", "paint", "panel",
    "paper", "party", "patch", "pause", "peace", "penny", "phase",
    "phone", "photo", "piano", "piece", "pilot", "pitch", "pixel",
    "place", "plain", "plane", "plant", "plate", "plaza", "plead",
    "pluck", "point", "pound", "power", "press", "price", "pride",
    "prime", "print", "prior", "prize", "proof", "proud", "prove",
    "pulse", "punch", "purse", "queen", "quest", "quick", "quiet",
    "quite", "quote", "radar", "radio", "raise", "range", "rapid",
    "ratio", "reach", "ready", "realm", "rebel", "reign", "relax",
    "reply", "rider", "right", "rival", "river", "robin", "robot",
    "rocky", "roger", "rough", "round", "route", "royal", "rural",
    "sadly", "saint", "salad", "sauce", "scene", "scope", "score",
    "sense", "serve", "seven", "shake", "shall", "shame", "shape",
    "share", "sharp", "shelf", "shell", "shift", "shine", "shirt",
    "shock", "shoot", "shore", "short", "shout", "sight", "since",
    "sixth", "sixty", "skill", "sleep", "slide", "slope", "small",
    "smart", "smell", "smile", "smoke", "snake", "solar", "solid",
    "solve", "sorry", "sound", "south", "space", "spare", "speak",
    "spend", "spine", "split", "spoke", "sport", "spray", "squad",
    "stack", "staff", "stage", "stake", "stale", "stall", "stamp",
    "stand", "stark", "start", "state", "stays", "steal", "steam",
    "steep", "steer", "stick", "stiff", "still", "stock", "stone",
    "store", "storm", "story", "stove", "strip", "stuck", "study",
    "stuff", "style", "sugar", "suite", "super", "surge", "swear",
    "sweet", "swept", "swing", "sword", "table", "taste", "teach",
    "terms", "thank", "theme", "thick", "thing", "think", "third",
    "those", "three", "threw", "thumb", "tiger", "tight", "tired",
    "title", "today", "token", "topic", "total", "touch", "tough",
    "trace", "track", "trail", "train", "trait", "trash", "treat",
    "trend", "trial", "tribe", "trick", "tried", "truck", "truly",
    "trunk", "trust", "truth", "tumor", "twice", "twist", "ultra",
    "uncle", "under", "union", "unite", "unity", "until", "upper",
    "upset", "urban", "usage", "usual", "utter", "valid", "value",
    "video", "viral", "virus", "visit", "vital", "vivid", "vocal",
    "voice", "voter", "wages", "waste", "watch", "water", "weigh",
    "weird", "whale", "wheat", "wheel", "where", "which", "while",
    "white", "whole", "whose", "wider", "woman", "works", "world",
    "worry", "worse", "worst", "worth", "would", "wound", "write",
    "wrong", "wrote", "yield", "young", "youth",
]

ALL_VALID_GUESSES = set(LOL_WORDS + EXTRA_VALID_GUESSES)


def get_wordle_word_of_day():
    """Get today's LoL Wordle word deterministically"""
    today = datetime.now().date().isoformat()
    h = int(hashlib.md5(today.encode()).hexdigest(), 16)
    return LOL_WORDS[h % len(LOL_WORDS)]


def evaluate_wordle_guess(guess, answer):
    """Evaluate a Wordle guess against the answer. Returns list of statuses.
    Handles duplicate letters correctly per official Wordle rules."""
    result = ['absent'] * 5
    answer_chars = list(answer)

    # First pass: mark correct (exact matches)
    for i in range(5):
        if guess[i] == answer[i]:
            result[i] = 'correct'
            answer_chars[i] = None  # Mark as used

    # Second pass: mark present (right letter, wrong position)
    for i in range(5):
        if result[i] == 'correct':
            continue
        if guess[i] in answer_chars:
            result[i] = 'present'
            answer_chars[answer_chars.index(guess[i])] = None  # Mark as used

    return result


def get_or_create_wordle_stats():
    """Get the wordle stats singleton or create if doesn't exist"""
    stats = WordleStats.query.first()
    if not stats:
        stats = WordleStats()
        db.session.add(stats)
        db.session.commit()
    return stats


@app.route('/wordle')
def wordle():
    """LoL Wordle game page"""
    stats = get_or_create_wordle_stats()
    today = datetime.now().date()

    # Check if there's an in-progress or completed game today
    game_state = None
    if stats.last_played_date == today and stats.last_game_guesses:
        guesses = json.loads(stats.last_game_guesses)
        word = get_wordle_word_of_day()
        # Rebuild evaluation for each guess
        evaluated = []
        for g in guesses:
            evaluated.append({
                'word': g,
                'result': evaluate_wordle_guess(g, word)
            })
        game_state = {
            'guesses': evaluated,
            'won': stats.last_game_won,
            'finished': stats.last_game_won or len(guesses) >= 6
        }

    # Parse guess distribution
    dist = json.loads(stats.guess_distribution) if stats.guess_distribution else {"1":0,"2":0,"3":0,"4":0,"5":0,"6":0}

    return render_template('wordle.html',
                         stats=stats,
                         game_state=game_state,
                         guess_distribution=dist,
                         word_count=len(LOL_WORDS))


@app.route('/api/wordle/guess', methods=['POST'])
def wordle_guess():
    """Submit a guess for today's Wordle"""
    data = request.json
    guess = data.get('guess', '').lower().strip()

    if len(guess) != 5:
        return jsonify({'error': 'Guess must be 5 letters'}), 400

    if not guess.isalpha():
        return jsonify({'error': 'Guess must be letters only'}), 400

    if guess not in ALL_VALID_GUESSES:
        return jsonify({'error': 'Not in word list'}), 400

    stats = get_or_create_wordle_stats()
    today = datetime.now().date()
    word = get_wordle_word_of_day()

    # Load existing guesses for today
    if stats.last_played_date == today and stats.last_game_guesses:
        guesses = json.loads(stats.last_game_guesses)
    else:
        guesses = []
        stats.last_played_date = today
        stats.last_game_word = word
        stats.last_game_won = False

    # Check if game is already over
    if len(guesses) >= 6 or stats.last_game_won:
        return jsonify({'error': 'Game already finished'}), 400

    # Evaluate guess
    result = evaluate_wordle_guess(guess, word)
    guesses.append(guess)
    stats.last_game_guesses = json.dumps(guesses)

    won = guess == word
    finished = won or len(guesses) >= 6

    if finished:
        stats.games_played = (stats.games_played or 0) + 1
        if won:
            stats.last_game_won = True
            stats.games_won = (stats.games_won or 0) + 1
            stats.current_streak = (stats.current_streak or 0) + 1
            if stats.current_streak > (stats.max_streak or 0):
                stats.max_streak = stats.current_streak

            # Update guess distribution
            dist = json.loads(stats.guess_distribution) if stats.guess_distribution else {"1":0,"2":0,"3":0,"4":0,"5":0,"6":0}
            dist[str(len(guesses))] = dist.get(str(len(guesses)), 0) + 1
            stats.guess_distribution = json.dumps(dist)
        else:
            stats.current_streak = 0

    db.session.commit()

    response = {
        'result': result,
        'guess': guess,
        'won': won,
        'finished': finished,
        'guess_number': len(guesses),
    }
    if finished and not won:
        response['answer'] = word

    return jsonify(response)


@app.route('/api/wordle/stats')
def wordle_stats():
    """Get Wordle stats"""
    stats = get_or_create_wordle_stats()
    dist = json.loads(stats.guess_distribution) if stats.guess_distribution else {"1":0,"2":0,"3":0,"4":0,"5":0,"6":0}

    return jsonify({
        'games_played': stats.games_played or 0,
        'games_won': stats.games_won or 0,
        'current_streak': stats.current_streak or 0,
        'max_streak': stats.max_streak or 0,
        'guess_distribution': dist,
        'win_pct': round((stats.games_won or 0) / max(stats.games_played or 1, 1) * 100)
    })


# ===== PORTFOLIO NEWS BRIEFING =====

# Portfolio holdings - actual positions
PORTFOLIO_HOLDINGS = [
    # Tech / AI
    {"ticker": "GOOG", "company": "Alphabet", "layer": "Tech / AI", "weight": 29.8, "conviction": "Very High", "value": 13905, "shares": 45, "avg_cost": 179.42, "currency": "USD"},
    {"ticker": "AMZN", "company": "Amazon", "layer": "Tech / Cloud AI", "weight": 8.6, "conviction": "High", "value": 4000, "shares": 20, "avg_cost": 102.08, "currency": "USD"},
    {"ticker": "META", "company": "Meta Platforms", "layer": "Tech / AI", "weight": 4.2, "conviction": "Very High", "value": 1950, "shares": 3, "avg_cost": 192.00, "currency": "USD"},
    {"ticker": "MSFT", "company": "Microsoft", "layer": "Tech / AI", "weight": 2.6, "conviction": "Very High", "value": 1203, "shares": 3, "avg_cost": 255.88, "currency": "USD"},
    {"ticker": "AAPL", "company": "Apple", "layer": "Tech / Consumer", "weight": 4.5, "conviction": "Medium", "value": 2096, "shares": 8, "avg_cost": 100.62, "currency": "USD"},
    # Semiconductors
    {"ticker": "NVDA", "company": "NVIDIA", "layer": "Semiconductors", "weight": 12.0, "conviction": "Very High", "value": 5610, "shares": 30, "avg_cost": 18.36, "currency": "USD"},
    {"ticker": "AMD", "company": "AMD", "layer": "Semiconductors", "weight": 2.2, "conviction": "High", "value": 1035, "shares": 5, "avg_cost": 61.99, "currency": "USD"},
    # Aerospace & Defence
    {"ticker": "AIR.PA", "company": "Airbus", "layer": "Aerospace & Defence", "weight": 9.7, "conviction": "High", "value": 4531, "shares": 20, "avg_cost": 201.45, "currency": "EUR"},
    {"ticker": "EUDF", "company": "WisdomTree EU Defence ETF", "layer": "Defence ETF", "weight": 8.4, "conviction": "High", "value": 3906, "shares": 100, "avg_cost": 32.54, "currency": "EUR"},
    {"ticker": "CSG", "company": "Czechoslovak Group", "layer": "Defence", "weight": 5.6, "conviction": "High", "value": 2602, "shares": 75, "avg_cost": 31.09, "currency": "EUR"},
    # Healthcare
    {"ticker": "NOVO-B", "company": "Novo Nordisk", "layer": "Healthcare", "weight": 5.2, "conviction": "High", "value": 2425, "shares": 50, "avg_cost": 304.29, "currency": "DKK"},
    {"ticker": "GSK", "company": "GSK", "layer": "Healthcare", "weight": 4.3, "conviction": "Medium", "value": 2013, "shares": 75, "avg_cost": 1819.27, "currency": "GBp"},
    # Other
    {"ticker": "SOF.BR", "company": "Sofina", "layer": "Investment Holding", "weight": 2.4, "conviction": "Medium", "value": 1138, "shares": 4, "avg_cost": 202.58, "currency": "EUR"},
    {"ticker": "MU", "company": "Micron", "layer": "Semiconductors", "weight": 3.0, "conviction": "High", "value": 1985, "shares": 5, "avg_cost": 400.00, "currency": "USD"},
]

# AI watchlist - stocks from the AI Bull Market spreadsheet not in current portfolio
AI_WATCHLIST = [
    # Semiconductors
    {"ticker": "AVGO", "company": "Broadcom", "layer": "Semiconductors", "verdict": "BUY"},
    {"ticker": "TSM", "company": "TSMC", "layer": "Semiconductors", "verdict": "BUY"},
    {"ticker": "MU", "company": "Micron", "layer": "Semiconductors", "verdict": "STRONG BUY"},
    {"ticker": "ARM", "company": "Arm Holdings", "layer": "Semiconductors", "verdict": "HOLD"},
    {"ticker": "ANET", "company": "Arista Networks", "layer": "Networking", "verdict": "BUY"},
    {"ticker": "ASML", "company": "ASML Holding", "layer": "Semicon Equipment", "verdict": "BUY"},
    # Cloud & Infra
    {"ticker": "ORCL", "company": "Oracle", "layer": "Cloud & Infra", "verdict": "HOLD"},
    {"ticker": "CRWV", "company": "CoreWeave", "layer": "Cloud & Infra", "verdict": "SPECULATIVE"},
    # AI Applications
    {"ticker": "PLTR", "company": "Palantir", "layer": "AI Applications", "verdict": "SPECULATIVE"},
    {"ticker": "CRM", "company": "Salesforce", "layer": "AI Applications", "verdict": "CONTRARIAN BUY"},
    {"ticker": "SNOW", "company": "Snowflake", "layer": "AI Applications", "verdict": "AVOID"},
    {"ticker": "NOW", "company": "ServiceNow", "layer": "AI Applications", "verdict": "BUY"},
    {"ticker": "SAP", "company": "SAP SE", "layer": "AI Applications", "verdict": "CONTRARIAN BUY"},
    {"ticker": "DDOG", "company": "Datadog", "layer": "AI Applications", "verdict": "HOLD"},
    # AI Security
    {"ticker": "PANW", "company": "Palo Alto Networks", "layer": "AI Security", "verdict": "HOLD"},
    {"ticker": "CRWD", "company": "CrowdStrike", "layer": "AI Security", "verdict": "HOLD"},
    # Energy & Power
    {"ticker": "VST", "company": "Vistra Energy", "layer": "Energy & Power", "verdict": "BUY"},
    {"ticker": "ENR.DE", "company": "Siemens Energy", "layer": "Energy & Power", "verdict": "BUY"},
    # Robotics & Physical AI
    {"ticker": "TSLA", "company": "Tesla", "layer": "Robotics & Physical AI", "verdict": "SPECULATIVE"},
    {"ticker": "ISRG", "company": "Intuitive Surgical", "layer": "Robotics & Physical AI", "verdict": "HOLD"},
    # AI Healthcare
    {"ticker": "VEEV", "company": "Veeva Systems", "layer": "AI Healthcare", "verdict": "HOLD"},
    {"ticker": "TEM", "company": "Tempus AI", "layer": "AI Healthcare", "verdict": "SPECULATIVE"},
]

GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1IowxOM1NFHDBJ7fkaWjUQ2GbKLjxGiLq/export?format=csv"

# Seed portfolio DB on first run (skip in demo — seed_demo.py handles it)
if not DEMO_MODE:
    with app.app_context():
        seed_portfolio_stocks()


def fetch_portfolio_from_sheet():
    """Try to fetch latest portfolio from Google Sheet, fall back to static list"""
    try:
        req = urllib.request.Request(GOOGLE_SHEET_URL, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=10)
        # Handle redirects
        csv_data = response.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(csv_data))

        holdings = []
        for row in reader:
            ticker = row.get('Ticker', '').strip()
            company = row.get('Company', '').strip()
            if ticker and company:
                weight_str = row.get('Portfolio Weight (%)', '0').replace('%', '').strip()
                try:
                    weight = float(weight_str)
                except (ValueError, TypeError):
                    weight = 0
                holdings.append({
                    "ticker": ticker,
                    "company": company,
                    "layer": row.get('AI Stack Layer', ''),
                    "weight": weight,
                    "conviction": row.get('Conviction', ''),
                })
        if holdings:
            return holdings
    except Exception as e:
        print(f"Error fetching sheet: {e}")

    return PORTFOLIO_HOLDINGS


# ===== VALUE INVESTING FUNDAMENTALS (yfinance) =====

VALUE_THRESHOLDS = {
    # metric: (green_threshold, yellow_threshold, direction)
    # 'lower' = lower is better (valuation ratios), 'higher' = higher is better
    'pe_trailing':      (15, 25, 'lower'),
    'pe_forward':       (12, 20, 'lower'),
    'pb_ratio':         (1.5, 3.0, 'lower'),
    'ev_ebitda':        (10, 15, 'lower'),
    'peg_ratio':        (1.0, 2.0, 'lower'),
    'fcf_yield':        (8, 4, 'higher'),
    'roe':              (15, 10, 'higher'),
    'roa':              (7, 4, 'higher'),
    'gross_margin':     (40, 20, 'higher'),
    'operating_margin': (20, 10, 'higher'),
    'net_margin':       (15, 5, 'higher'),
    'debt_to_equity':   (50, 100, 'lower'),
    'current_ratio':    (2.0, 1.0, 'higher'),
    'quick_ratio':      (1.5, 0.8, 'higher'),
    'interest_coverage': (5, 2, 'higher'),
    'revenue_growth':   (15, 5, 'higher'),
    'earnings_growth':  (15, 5, 'higher'),
    'dividend_yield':   (3, 1, 'higher'),
    'payout_ratio':     (60, 80, 'lower'),
}

METRIC_WEIGHTS = {
    # Valuation: 35%
    'pe_trailing': 8, 'pe_forward': 7, 'pb_ratio': 6,
    'ev_ebitda': 6, 'peg_ratio': 4, 'fcf_yield': 4,
    # Profitability: 25%
    'roe': 7, 'roa': 4, 'gross_margin': 5,
    'operating_margin': 5, 'net_margin': 4,
    # Financial Health: 20%
    'debt_to_equity': 6, 'current_ratio': 5,
    'quick_ratio': 4, 'interest_coverage': 5,
    # Growth: 15%
    'revenue_growth': 8, 'earnings_growth': 7,
    # Dividends: 5%
    'dividend_yield': 3, 'payout_ratio': 2,
}

METRIC_LABELS = {
    'pe_trailing': 'P/E (Trailing)', 'pe_forward': 'P/E (Forward)',
    'pb_ratio': 'Price / Book', 'ev_ebitda': 'EV / EBITDA',
    'peg_ratio': 'PEG Ratio', 'fcf_yield': 'FCF Yield',
    'roe': 'Return on Equity', 'roa': 'Return on Assets',
    'gross_margin': 'Gross Margin', 'operating_margin': 'Operating Margin',
    'net_margin': 'Net Margin', 'debt_to_equity': 'Debt / Equity',
    'current_ratio': 'Current Ratio', 'quick_ratio': 'Quick Ratio',
    'interest_coverage': 'Interest Coverage',
    'revenue_growth': 'Revenue Growth', 'earnings_growth': 'Earnings Growth',
    'dividend_yield': 'Dividend Yield', 'payout_ratio': 'Payout Ratio',
}


def _safe_pct(value):
    """Convert yfinance ratio (0.15) to percentage (15.0), or None"""
    if value is None:
        return None
    return round(value * 100, 2)


def fetch_yfinance_data(ticker):
    """Fetch fundamental data from yfinance. Returns dict of metrics or None on failure."""
    import re
    import yfinance as yf

    # Validate ticker format (letters, digits, dots, hyphens only, max 10 chars)
    if not re.match(r'^[A-Z0-9.\-]{1,10}$', ticker):
        return None

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        # yfinance returns sparse dicts for invalid tickers
        if not info or len(info) < 5:
            return None

        # Price: allow 0 (penny stocks), only reject None
        price = info.get('currentPrice')
        if price is None:
            price = info.get('regularMarketPrice')
        if price is None:
            return None

        data = {
            'current_price': price,
            'market_cap': info.get('marketCap'),
            'week_52_high': info.get('fiftyTwoWeekHigh'),
            'week_52_low': info.get('fiftyTwoWeekLow'),
            'pe_trailing': info.get('trailingPE'),
            'pe_forward': info.get('forwardPE'),
            'pb_ratio': info.get('priceToBook'),
            'ev_ebitda': info.get('enterpriseToEbitda'),
            'peg_ratio': info.get('pegRatio'),
            'roe': _safe_pct(info.get('returnOnEquity')),
            'roa': _safe_pct(info.get('returnOnAssets')),
            'gross_margin': _safe_pct(info.get('grossMargins')),
            'operating_margin': _safe_pct(info.get('operatingMargins')),
            'net_margin': _safe_pct(info.get('profitMargins')),
            'debt_to_equity': info.get('debtToEquity'),
            'current_ratio': info.get('currentRatio'),
            'quick_ratio': info.get('quickRatio'),
            'revenue_growth': _safe_pct(info.get('revenueGrowth')),
            'earnings_growth': _safe_pct(info.get('earningsGrowth')),
            'dividend_yield': round(info.get('dividendYield'), 2) if info.get('dividendYield') is not None else None,  # yfinance returns this already in pct form
            'payout_ratio': _safe_pct(info.get('payoutRatio')),
            'company_name': info.get('longName') or info.get('shortName'),
            'sector': info.get('sector'),
            'industry': info.get('industry'),
        }

        # Derived: FCF yield = freeCashflow / marketCap * 100
        fcf = info.get('freeCashflow')
        mcap = info.get('marketCap')
        data['fcf_yield'] = round((fcf / mcap) * 100, 2) if fcf is not None and mcap and mcap > 0 else None

        # Derived: Interest coverage = operatingIncome / |interestExpense|
        op_income = info.get('operatingIncome')
        if op_income is None:
            op_income = info.get('ebitda')
        interest = info.get('interestExpense')
        if op_income is not None and interest and interest != 0:
            data['interest_coverage'] = round(abs(op_income / interest), 2)
        else:
            data['interest_coverage'] = None

        return data
    except Exception as e:
        print(f"yfinance error for {ticker}: {e}")
        return None


def rate_metric(value, metric_name):
    """Rate a single metric. Returns ('green'|'yellow'|'red'|'gray', score 0-100|None)."""
    if value is None:
        return ('gray', None)
    thresholds = VALUE_THRESHOLDS.get(metric_name)
    if not thresholds:
        return ('gray', None)
    green_t, yellow_t, direction = thresholds
    if direction == 'lower':
        if value <= green_t:
            return ('green', 100)
        elif value <= yellow_t:
            return ('yellow', 50)
        else:
            return ('red', 0)
    else:
        if value >= green_t:
            return ('green', 100)
        elif value >= yellow_t:
            return ('yellow', 50)
        else:
            return ('red', 0)


def compute_value_score(data_dict):
    """Compute composite value score (0-100) and per-metric color ratings."""
    ratings = {}
    total_score = 0
    total_weight = 0
    for metric, weight in METRIC_WEIGHTS.items():
        value = data_dict.get(metric)
        color, score = rate_metric(value, metric)
        ratings[metric] = color
        if score is not None:
            total_score += score * weight
            total_weight += weight
    value_score = round(total_score / total_weight, 1) if total_weight > 0 else 0
    return value_score, ratings


def determine_winners(stocks_data):
    """Given list of {ticker, ...metric_values}, return {metric: winning_ticker}."""
    winners = {}
    for metric in VALUE_THRESHOLDS:
        _, _, direction = VALUE_THRESHOLDS[metric]
        valid = [(s['ticker'], s.get(metric)) for s in stocks_data if s.get(metric) is not None]
        if not valid:
            continue
        if direction == 'lower':
            winner = min(valid, key=lambda x: x[1])
        else:
            winner = max(valid, key=lambda x: x[1])
        winners[metric] = winner[0]
    return winners


def get_or_fetch_fundamentals(ticker):
    """Get cached fundamentals or fetch fresh from yfinance. Returns (StockFundamentals, ratings) or (None, None)."""
    ticker = ticker.upper().strip()
    record = StockFundamentals.query.filter_by(ticker=ticker).first()

    if record and not record.is_stale():
        # Return cached
        flat = {k: getattr(record, k) for k in METRIC_WEIGHTS}
        _, ratings = compute_value_score(flat)
        return record, ratings

    # Fetch fresh
    data = fetch_yfinance_data(ticker)
    if data is None:
        # If we have stale data, return it with a warning
        if record:
            flat = {k: getattr(record, k) for k in METRIC_WEIGHTS}
            _, ratings = compute_value_score(flat)
            return record, ratings
        return None, None

    # Compute score
    value_score, ratings = compute_value_score(data)
    data['value_score'] = value_score

    # Upsert
    if not record:
        record = StockFundamentals(ticker=ticker)
        db.session.add(record)

    for key, val in data.items():
        if hasattr(record, key):
            setattr(record, key, val)
    record.fetched_at = datetime.utcnow()

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"DB commit error for {ticker}: {e}")
        return None, None

    return record, ratings


def fetch_news_for_portfolio(holdings):
    """Fetch news from NewsAPI.org for portfolio companies"""
    api_key = os.getenv('NEWSAPI_KEY')
    if not api_key:
        return None

    all_articles = []

    # Build query in batches — combine company names for efficiency
    # NewsAPI allows OR queries
    for i in range(0, len(holdings), 5):
        batch = holdings[i:i+5]
        query = ' OR '.join(f'"{h["company"]}"' for h in batch)

        try:
            url = f"https://newsapi.org/v2/everything?q={urllib.request.quote(query)}&language=en&sortBy=publishedAt&pageSize=10&apiKey={api_key}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req, timeout=15)
            data = json.loads(response.read().decode('utf-8'))

            if data.get('status') == 'ok':
                for article in data.get('articles', []):
                    # Tag which companies this article is about
                    related_tickers = []
                    title_desc = (article.get('title', '') + ' ' + article.get('description', '')).lower()
                    for h in holdings:
                        if h['company'].lower() in title_desc or h['ticker'].lower() in title_desc:
                            related_tickers.append(h['ticker'])

                    all_articles.append({
                        'title': article.get('title', ''),
                        'description': article.get('description', ''),
                        'url': article.get('url', ''),
                        'source': article.get('source', {}).get('name', ''),
                        'published_at': article.get('publishedAt', ''),
                        'related_tickers': related_tickers or [batch[0]['ticker']],
                    })
        except Exception as e:
            print(f"NewsAPI error for batch: {e}")
            continue

    return all_articles


def generate_portfolio_briefing(articles, holdings):
    """Use Claude to generate a concise 10-minute daily briefing"""
    if not claude_client or not articles:
        return None

    # Build portfolio context
    portfolio_context = "Portfolio Holdings (by weight):\n"
    for h in sorted(holdings, key=lambda x: x['weight'], reverse=True):
        portfolio_context += f"- {h['ticker']} ({h['company']}) - {h['weight']}% - {h['layer']} - {h['conviction']} conviction\n"

    # Build news context (limit to avoid token overflow)
    news_context = "Today's News Articles:\n\n"
    for i, article in enumerate(articles[:40]):
        tickers = ', '.join(article['related_tickers'])
        news_context += f"[{i+1}] [{tickers}] {article['title']}\n"
        if article['description']:
            news_context += f"    {article['description'][:200]}\n"
        news_context += f"    Source: {article['source']} | {article['published_at'][:10] if article['published_at'] else 'Today'}\n\n"

    prompt = f"""You are a portfolio analyst preparing a daily briefing for an investor holding an AI-focused portfolio.

{portfolio_context}

{news_context}

## Your Task

Write a **concise daily portfolio briefing** that takes about 10 minutes to read. Structure it as follows:

### 1. Executive Summary (2-3 sentences)
The most important thing the investor needs to know today. What moved? What matters?

### 2. Key Stories (3-5 stories max)
For each major story:
- **Headline** with the relevant ticker(s) in brackets
- 2-3 sentence summary of what happened and why it matters for the portfolio
- **Impact**: Brief assessment (Bullish/Bearish/Neutral) and which holdings are affected

### 3. Sector Watch
Quick scan across the portfolio sectors (Semiconductors, Cloud, AI Apps, Security, Energy):
- Which sectors had news today?
- Any sector-wide trends?

### 4. Action Items
- Anything requiring attention? (earnings coming up, analyst upgrades/downgrades, unusual activity)
- Keep to 2-3 bullet points max

### 5. Quick Links
List the 3-5 most important articles the investor should read if they want to dig deeper. Format: [Title](URL) - Source

## Style Guidelines
- Be concise and direct — this is a busy investor
- Focus on what's NEW and ACTIONABLE, not background info
- Prioritize by portfolio weight — NVDA/MSFT/GOOGL/META news matters more than VST news
- Use markdown formatting for clean readability
- If there's genuinely no news for some holdings, don't pad with filler — just skip them
- Be honest about impact — not everything is bullish"""

    try:
        message = call_claude('portfolio', 'generate_briefing',
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        print(f"Error generating briefing: {e}")
        return None


@app.route('/portfolio')
def portfolio():
    """Portfolio news briefing page"""
    today = datetime.now().date()

    # Load from DB
    db_holdings = PortfolioStock.query.filter_by(status='holding').order_by(PortfolioStock.weight.desc()).all()
    db_watchlist = PortfolioStock.query.filter_by(status='watchlist').order_by(PortfolioStock.layer).all()

    holdings = [h.to_dict() for h in db_holdings]
    watchlist = [w.to_dict() for w in db_watchlist]

    # Check for cached briefing
    briefing = PortfolioBriefing.query.filter_by(date=today).first()

    # Group holdings by layer
    layers = {}
    for h in holdings:
        layer = h['layer']
        if layer not in layers:
            layers[layer] = []
        layers[layer].append(h)

    has_newsapi = bool(os.getenv('NEWSAPI_KEY'))

    # DCA schedules
    dca_schedules = DCASchedule.query.filter_by(is_active=True).all()
    dca_list = [d.to_dict() for d in dca_schedules]
    dca_total_target = sum(d.monthly_amount for d in dca_schedules)

    # This month's investment spending (from finance)
    month_start = date(today.year, today.month, 1)
    if today.month == 12:
        month_end = date(today.year + 1, 1, 1)
    else:
        month_end = date(today.year, today.month + 1, 1)

    investment_txns = FinanceTransaction.query.filter(
        FinanceTransaction.date >= month_start,
        FinanceTransaction.date < month_end,
        FinanceTransaction.transaction_type == 'investment',
    ).all()
    invested_this_month = sum(abs(t.amount) for t in investment_txns)

    # Finance summary for this month
    all_month_txns = FinanceTransaction.query.filter(
        FinanceTransaction.date >= month_start,
        FinanceTransaction.date < month_end,
        FinanceTransaction.state != 'RENVOYÉ',
    ).all()
    month_income = sum(t.amount for t in all_month_txns if t.transaction_type == 'income')
    month_expenses = sum(abs(t.amount) + t.fee for t in all_month_txns if t.transaction_type in ('expense', 'subscription'))
    month_net = month_income - month_expenses

    return render_template('portfolio.html',
                         holdings=holdings,
                         watchlist=watchlist,
                         layers=layers,
                         briefing=briefing,
                         has_newsapi=has_newsapi,
                         today=today,
                         dca_schedules=dca_list,
                         dca_total_target=round(dca_total_target, 2),
                         invested_this_month=round(invested_this_month, 2),
                         month_income=round(month_income, 2),
                         month_expenses=round(month_expenses, 2),
                         month_net=round(month_net, 2))


@app.route('/api/portfolio/generate', methods=['POST'])
def portfolio_generate_briefing():
    """Generate today's portfolio briefing"""
    today = datetime.now().date()

    # Check if already generated today
    existing = PortfolioBriefing.query.filter_by(date=today).first()
    if existing and existing.summary_html:
        return jsonify({'status': 'ready', 'html': existing.summary_html})

    # Fetch portfolio from DB (includes both holdings and watchlist for news coverage)
    all_stocks = PortfolioStock.query.all()
    holdings = [s.to_dict() for s in all_stocks]

    # Fetch news
    articles = fetch_news_for_portfolio(holdings)
    if not articles:
        return jsonify({'error': 'No news articles found. Check your NEWSAPI_KEY in .env'}), 400

    # Generate briefing with Claude
    summary = generate_portfolio_briefing(articles, holdings)
    if not summary:
        return jsonify({'error': 'Failed to generate briefing. Check your ANTHROPIC_API_KEY.'}), 500

    # Convert markdown to HTML
    summary_html = markdown.markdown(summary, extensions=['extra', 'nl2br'])

    # Cache it
    if existing:
        existing.summary_html = summary_html
        existing.raw_articles = json.dumps(articles[:40])
        existing.tickers_data = json.dumps([h['ticker'] for h in holdings])
    else:
        briefing = PortfolioBriefing(
            date=today,
            summary_html=summary_html,
            raw_articles=json.dumps(articles[:40]),
            tickers_data=json.dumps([h['ticker'] for h in holdings])
        )
        db.session.add(briefing)

    db.session.commit()
    return jsonify({'status': 'ready', 'html': summary_html})


@app.route('/api/portfolio/deep-dive/<ticker>', methods=['POST'])
def portfolio_deep_dive(ticker):
    """Get a deeper analysis for a specific ticker"""
    if not claude_client:
        return jsonify({'error': 'Claude API not configured'}), 500

    # Find stock in DB
    stock = PortfolioStock.query.filter_by(ticker=ticker.upper()).first()
    if not stock:
        return jsonify({'error': 'Ticker not found'}), 404
    holding = stock.to_dict()
    is_watchlist = stock.status == 'watchlist'
    is_pre_ipo = stock.verdict == 'Pre-IPO'

    # Get today's cached articles
    today = datetime.now().date()
    briefing = PortfolioBriefing.query.filter_by(date=today).first()
    articles_context = ""
    if briefing and briefing.raw_articles:
        articles = json.loads(briefing.raw_articles)
        relevant = [a for a in articles if ticker.upper() in a.get('related_tickers', [])]
        if relevant:
            articles_context = "\n\nRecent articles about this company:\n"
            for a in relevant[:10]:
                articles_context += f"- {a['title']} ({a['source']})\n  {a.get('description', '')[:200]}\n"

    if is_pre_ipo:
        prompt = f"""You are a private-markets / IPO analyst. The user is tracking {holding['company']} as a pre-IPO company they want to buy on or shortly after IPO.

Sector: {holding['layer']}
{articles_context}

Write a concise IPO watch brief (3-4 paragraphs) covering:
1. Current IPO status — has the company filed an S-1, hired underwriters, or signaled timing? What's the latest reported expected window? If still private with no filing, say so directly.
2. Latest known valuation (most recent funding round or secondary-market mark) and headline financials if disclosed (revenue run-rate, growth, profitability).
3. Key catalysts and risks specific to IPO timing and post-listing performance — regulatory, market conditions, governance, competitive dynamics.
4. Concrete next steps for the user: what filings/news to watch for, where to monitor (SEC EDGAR, specific publications), and any pre-IPO access mechanisms (e.g. secondary marketplaces, brokerage IPO access programs) if relevant.

Be specific. Acknowledge uncertainty when information is not public. No generic filler."""
    else:
        if is_watchlist:
            context_line = f"- Status: Watchlist (not currently held)\n- Sector: {holding['layer']}\n- Verdict: {holding.get('verdict', 'N/A')}"
        else:
            context_line = f"- Weight: {holding['weight']}%\n- Sector: {holding['layer']}\n- Conviction: {holding['conviction']}"

        prompt = f"""You are a portfolio analyst. Give a focused deep-dive on {holding['company']} ({holding['ticker']}).

Portfolio context:
{context_line}
{articles_context}

Write a concise deep-dive (3-4 paragraphs) covering:
1. What's happening with this company right now (based on recent news if available)
2. Key risks and catalysts to watch
3. {'Whether it deserves a position in the portfolio and at what entry point' if is_watchlist else 'How it fits in the broader AI portfolio thesis'}

Be specific and actionable. No generic filler."""

    try:
        message = call_claude('portfolio', 'deep_dive',
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        response_html = markdown.markdown(message.content[0].text, extensions=['extra', 'nl2br'])
        return jsonify({'html': response_html})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolio/stock', methods=['POST'])
def portfolio_add_stock():
    """Add a stock to the watchlist"""
    data = request.get_json()
    ticker = data.get('ticker', '').strip().upper()
    company = data.get('company', '').strip()
    if not ticker or not company:
        return jsonify({'error': 'Ticker and company are required'}), 400

    existing = PortfolioStock.query.filter_by(ticker=ticker).first()
    if existing:
        return jsonify({'error': f'{ticker} is already in your {existing.status} list'}), 400

    stock = PortfolioStock(
        ticker=ticker,
        company=company,
        layer=data.get('layer', '').strip() or 'Other',
        status='watchlist',
        verdict=data.get('verdict', 'HOLD')
    )
    db.session.add(stock)
    db.session.commit()
    return jsonify({'success': True, 'stock': stock.to_dict()})


@app.route('/api/portfolio/stock/<int:stock_id>/promote', methods=['PUT'])
def portfolio_promote_stock(stock_id):
    """Move a watchlist stock to portfolio holdings"""
    stock = PortfolioStock.query.get_or_404(stock_id)
    data = request.get_json()

    position_value = float(data.get('value', 0))
    stock.status = 'holding'
    stock.value = position_value
    stock.verdict = None  # Clear watchlist verdict

    # Auto-calculate weights for all holdings based on dollar values
    db.session.flush()  # Make sure the status change is visible in query
    all_holdings = PortfolioStock.query.filter_by(status='holding').all()
    total_value = sum(h.value for h in all_holdings) or 1
    for h in all_holdings:
        h.weight = round((h.value / total_value) * 100, 1)

    # Use AI to determine conviction level
    conviction = 'Medium'  # default
    if claude_client:
        try:
            resp = call_claude('portfolio', 'conviction',
                model="claude-haiku-4-5-20251001",
                max_tokens=50,
                messages=[{
                    "role": "user",
                    "content": f'For the stock {stock.ticker} ({stock.company}), sector: {stock.layer}, determine an investment conviction level. Return ONLY one of these exact strings: "Very High", "High", "Medium", or "Low". Base it on the company\'s market position, growth prospects, and sector strength.'
                }]
            )
            ai_conviction = resp.content[0].text.strip().strip('"')
            if ai_conviction in ['Very High', 'High', 'Medium', 'Low']:
                conviction = ai_conviction
        except Exception as e:
            print(f"AI conviction error: {e}")

    stock.conviction = conviction
    db.session.commit()
    return jsonify({'success': True, 'stock': stock.to_dict()})


@app.route('/api/portfolio/stock/<int:stock_id>', methods=['DELETE'])
def portfolio_delete_stock(stock_id):
    """Remove a stock from watchlist or portfolio"""
    stock = PortfolioStock.query.get_or_404(stock_id)
    db.session.delete(stock)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/portfolio/tickers')
def portfolio_tickers():
    """Return all portfolio/watchlist tickers for dropdowns"""
    holdings = PortfolioStock.query.filter_by(status='holding').order_by(PortfolioStock.weight.desc()).all()
    watchlist = PortfolioStock.query.filter_by(status='watchlist').order_by(PortfolioStock.layer).all()
    return jsonify({
        'holdings': [{'ticker': s.ticker, 'company': s.company} for s in holdings],
        'watchlist': [{'ticker': s.ticker, 'company': s.company} for s in watchlist],
    })


@app.route('/api/portfolio/live-prices')
def portfolio_live_prices():
    """Fetch live prices for all holdings and compute P&L"""
    if DEMO_MODE:
        # Return hardcoded demo data — no yfinance calls
        _DEMO_LIVE_PRICES = {
            'AAPL': {'live_price': 178.50, 'currency': 'USD'},
            'MSFT': {'live_price': 415.20, 'currency': 'USD'},
            'GOOG': {'live_price': 155.80, 'currency': 'USD'},
            'AMZN': {'live_price': 185.30, 'currency': 'USD'},
            'NVDA': {'live_price': 880.50, 'currency': 'USD'},
            'BRK-B': {'live_price': 410.75, 'currency': 'USD'},
            'GSK': {'live_price': 1580.0, 'currency': 'GBp'},
            'NOVO-B': {'live_price': 850.0, 'currency': 'DKK'},
        }
        fx_rates = {'USD': 1.0, 'GBP': 1.27, 'DKK': 0.145, 'EUR': 1.08}
        holdings = PortfolioStock.query.filter_by(status='holding').all()
        stock_results = []
        total_value = 0
        total_cost = 0
        for h in holdings:
            demo = _DEMO_LIVE_PRICES.get(h.ticker)
            shares = h.shares or 0
            avg_cost = h.avg_cost or 0
            currency = h.currency or 'USD'
            if demo:
                live_price = demo['live_price']
                if currency == 'GBp':
                    fx = fx_rates.get('GBP', 1.0) / 100.0
                else:
                    fx = fx_rates.get(currency, 1.0)
                live_value_usd = shares * live_price * fx
                cost_basis_usd = shares * avg_cost * fx
                pnl_usd = live_value_usd - cost_basis_usd
                pnl_pct = (pnl_usd / cost_basis_usd * 100) if cost_basis_usd > 0 else 0
                total_value += live_value_usd
                total_cost += cost_basis_usd
                stock_results.append({
                    'ticker': h.ticker, 'live_price': round(live_price, 2),
                    'currency': currency, 'shares': shares,
                    'live_value_usd': round(live_value_usd, 2),
                    'cost_basis_usd': round(cost_basis_usd, 2),
                    'pnl_usd': round(pnl_usd, 2), 'pnl_pct': round(pnl_pct, 1),
                })
            else:
                total_value += h.value or 0
                total_cost += h.value or 0
                stock_results.append({'ticker': h.ticker, 'error': 'Price unavailable', 'live_value_usd': h.value or 0})
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
        return jsonify({
            'success': True, 'stocks': stock_results,
            'totals': {'total_value': round(total_value, 2), 'total_cost': round(total_cost, 2),
                       'total_pnl': round(total_pnl, 2), 'total_pnl_pct': round(total_pnl_pct, 1)},
            'fx_rates': {k: round(v, 4) for k, v in fx_rates.items()},
        })
    import yfinance as yf

    holdings = PortfolioStock.query.filter_by(status='holding').all()
    if not holdings:
        return jsonify({'success': True, 'stocks': [], 'totals': {}})

    # Map DB tickers to yfinance tickers (some EU stocks need exchange suffix)
    YF_TICKER_MAP = {
        'GSK': 'GSK.L',        # London Stock Exchange (GBp)
        'NOVO-B': 'NOVO-B.CO', # Copenhagen
        'CSG': 'CSG.AS',       # Amsterdam (EUR)
        'EUDF': 'EUDF.DE',     # Xetra (EUR)
    }

    # Fetch live prices individually (more reliable than batch for mixed exchanges)
    prices = {}
    for h in holdings:
        yf_ticker = YF_TICKER_MAP.get(h.ticker, h.ticker)
        try:
            info = yf.Ticker(yf_ticker).info
            p = info.get('currentPrice') or info.get('regularMarketPrice')
            if p is not None:
                prices[h.ticker] = float(p)
        except Exception:
            pass

    # Fetch exchange rates for non-USD currencies
    fx_rates = {'USD': 1.0}
    needed_currencies = set()
    for h in holdings:
        cur = h.currency or 'USD'
        if cur == 'GBp':
            needed_currencies.add('GBP')
        elif cur != 'USD':
            needed_currencies.add(cur)

    for cur in needed_currencies:
        try:
            fx_ticker = yf.Ticker(f'{cur}USD=X')
            rate = fx_ticker.info.get('regularMarketPrice') or fx_ticker.info.get('previousClose')
            if rate:
                fx_rates[cur] = float(rate)
        except Exception:
            fx_rates[cur] = 1.0  # fallback

    # Compute per-stock data
    stock_results = []
    total_value = 0
    total_cost = 0

    for h in holdings:
        ticker = h.ticker
        shares = h.shares or 0
        avg_cost = h.avg_cost or 0
        currency = h.currency or 'USD'
        live_price = prices.get(ticker)

        if live_price is None:
            stock_results.append({
                'ticker': ticker,
                'error': 'Price unavailable',
                'live_value_usd': h.value or 0,
            })
            total_value += h.value or 0
            total_cost += h.value or 0
            continue

        # Convert to USD
        if currency == 'GBp':
            # GBp = pence; price from yfinance is in GBp, divide by 100 for GBP
            fx = fx_rates.get('GBP', 1.0) / 100.0
        else:
            fx = fx_rates.get(currency, 1.0)

        live_value_usd = shares * live_price * fx
        cost_basis_usd = shares * avg_cost * fx
        pnl_usd = live_value_usd - cost_basis_usd
        pnl_pct = (pnl_usd / cost_basis_usd * 100) if cost_basis_usd > 0 else 0

        total_value += live_value_usd
        total_cost += cost_basis_usd

        # Update DB value for fallback
        h.value = round(live_value_usd, 2)

        stock_results.append({
            'ticker': ticker,
            'live_price': round(live_price, 2),
            'currency': currency,
            'shares': shares,
            'live_value_usd': round(live_value_usd, 2),
            'cost_basis_usd': round(cost_basis_usd, 2),
            'pnl_usd': round(pnl_usd, 2),
            'pnl_pct': round(pnl_pct, 1),
        })

    # Recalculate weights
    for h in holdings:
        h.weight = round((h.value / total_value) * 100, 1) if total_value > 0 else 0

    db.session.commit()

    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    return jsonify({
        'success': True,
        'stocks': stock_results,
        'totals': {
            'total_value': round(total_value, 2),
            'total_cost': round(total_cost, 2),
            'total_pnl': round(total_pnl, 2),
            'total_pnl_pct': round(total_pnl_pct, 1),
        },
        'fx_rates': {k: round(v, 4) for k, v in fx_rates.items()},
    })


@app.route('/api/portfolio/fundamentals/<ticker>')
def portfolio_fundamentals(ticker):
    """Return cached or fresh fundamental data for a single ticker"""
    record, ratings = get_or_fetch_fundamentals(ticker)
    if record is None:
        return jsonify({'success': False, 'error': f'Could not fetch data for {ticker.upper()}'}), 404

    result = record.to_dict()
    result['ratings'] = ratings
    result['labels'] = METRIC_LABELS
    result['success'] = True
    return jsonify(result)


@app.route('/api/portfolio/compare')
def portfolio_compare():
    """Return fundamentals for 2-4 tickers with per-metric winners"""
    tickers_param = request.args.get('tickers', '')
    tickers = list(dict.fromkeys(  # deduplicate while preserving order
        t.strip().upper() for t in tickers_param.split(',') if t.strip()
    ))

    if len(tickers) < 2:
        return jsonify({'success': False, 'error': 'Need at least 2 tickers to compare'}), 400
    if len(tickers) > 4:
        tickers = tickers[:4]

    stocks = []
    failed = []
    for ticker in tickers:
        record, ratings = get_or_fetch_fundamentals(ticker)
        if record:
            entry = record.to_dict()
            entry['ratings'] = ratings
            # Flatten metrics for winner comparison
            flat = {}
            for category in ['valuation', 'profitability', 'financial_health', 'growth', 'dividends']:
                flat.update(entry.get(category, {}))
            flat['ticker'] = ticker
            entry['_flat'] = flat
            stocks.append(entry)
        else:
            failed.append(ticker)

    if len(stocks) < 2:
        return jsonify({'success': False, 'error': 'Could not fetch data for enough tickers'}), 404

    # Determine winners
    flat_list = [s['_flat'] for s in stocks]
    winners = determine_winners(flat_list)

    # Remove internal flat data before sending
    for s in stocks:
        del s['_flat']

    result = {
        'success': True,
        'stocks': stocks,
        'winners': winners,
        'labels': METRIC_LABELS,
    }
    if failed:
        result['warnings'] = [f'Could not fetch data for {t}' for t in failed]

    return jsonify(result)


# ===== DCA / INVESTING =====

@app.route('/api/portfolio/dca', methods=['POST'])
def portfolio_add_dca():
    """Add or update a DCA schedule for a stock"""
    data = request.get_json()
    stock_id = data.get('stock_id')
    monthly_amount = float(data.get('monthly_amount', 0))

    if not stock_id or monthly_amount <= 0:
        return jsonify({'error': 'Stock and amount required'}), 400

    stock = PortfolioStock.query.get_or_404(stock_id)

    # Check if DCA already exists for this stock
    existing = DCASchedule.query.filter_by(stock_id=stock_id, is_active=True).first()
    if existing:
        existing.monthly_amount = monthly_amount
        existing.notes = data.get('notes', existing.notes)
    else:
        dca = DCASchedule(
            stock_id=stock_id,
            monthly_amount=monthly_amount,
            currency=data.get('currency', 'EUR'),
            notes=data.get('notes', ''),
        )
        db.session.add(dca)

    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/portfolio/dca/<int:id>', methods=['DELETE'])
def portfolio_delete_dca(id):
    """Delete a DCA schedule"""
    dca = DCASchedule.query.get_or_404(id)
    db.session.delete(dca)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/portfolio/dca/<int:id>', methods=['PUT'])
def portfolio_update_dca(id):
    """Update a DCA schedule"""
    dca = DCASchedule.query.get_or_404(id)
    data = request.get_json()
    if 'monthly_amount' in data:
        dca.monthly_amount = float(data['monthly_amount'])
    if 'is_active' in data:
        dca.is_active = data['is_active']
    if 'notes' in data:
        dca.notes = data['notes']
    db.session.commit()
    return jsonify({'success': True, 'dca': dca.to_dict()})


# ===== MEDITATION =====

@app.route('/meditate')
def meditate():
    """Meditation dashboard - timer, breathing, and stats"""
    game_stats = get_or_create_game_stats()
    today = datetime.now().date()

    # Today's sessions
    today_sessions = MeditationSession.query.filter_by(date=today).order_by(MeditationSession.created_at.desc()).all()
    today_minutes = sum(s.duration_seconds for s in today_sessions) // 60

    # Recent sessions (last 7 days for chart)
    week_ago = today - timedelta(days=6)
    recent_sessions = MeditationSession.query.filter(
        MeditationSession.date >= week_ago
    ).order_by(MeditationSession.date).all()

    # Aggregate by day for weekly chart data
    weekly_data = {}
    for i in range(7):
        d = week_ago + timedelta(days=i)
        weekly_data[d.strftime('%a')] = 0
    for s in recent_sessions:
        key = s.date.strftime('%a')
        weekly_data[key] = weekly_data.get(key, 0) + s.duration_seconds // 60

    return render_template('meditation.html',
                         game_stats=game_stats,
                         today_sessions=today_sessions,
                         today_minutes=today_minutes,
                         weekly_data=weekly_data)


@app.route('/api/meditate/complete', methods=['POST'])
def meditate_complete():
    """Record a completed meditation session and award XP"""
    data = request.get_json()
    session_type = data.get('type', 'timer')
    breathing_pattern = data.get('pattern')
    duration = int(data.get('duration', 0))
    target = int(data.get('target', duration))
    completed = data.get('completed', True)

    today = datetime.now().date()

    # Calculate XP: base 10 + 1 per minute, bonuses
    minutes = duration // 60
    xp = 10 + minutes
    if completed and duration >= target:
        xp += 5  # completion bonus
    if session_type == 'breathing':
        xp += 5  # breathing exercise bonus

    med_session = MeditationSession(
        date=today,
        session_type=session_type,
        breathing_pattern=breathing_pattern,
        duration_seconds=duration,
        target_duration_seconds=target,
        completed=completed,
        xp_earned=xp
    )
    db.session.add(med_session)

    # Update GameStats
    game_stats = get_or_create_game_stats()
    game_stats.xp += xp
    game_stats.meditation_sessions_total = (game_stats.meditation_sessions_total or 0) + 1
    game_stats.meditation_minutes_total = (game_stats.meditation_minutes_total or 0) + minutes
    game_stats.meditation_xp_total = (game_stats.meditation_xp_total or 0) + xp

    # Update streak
    if game_stats.last_meditation_date:
        days_diff = (today - game_stats.last_meditation_date).days
        if days_diff == 1:
            game_stats.meditation_streak = (game_stats.meditation_streak or 0) + 1
        elif days_diff > 1:
            game_stats.meditation_streak = 1
        # days_diff == 0: same day, no streak change
    else:
        game_stats.meditation_streak = 1
    game_stats.last_meditation_date = today

    db.session.commit()

    # Check achievements
    new_achievements = check_achievements(game_stats)
    for a in new_achievements:
        flash(f'🏆 Achievement Unlocked: {a["name"]}!', 'success')

    leveled_up = check_level_up(game_stats)
    if leveled_up:
        flash(f'🎉 Level Up! You are now {game_stats.level_name}!', 'success')

    db.session.commit()

    return jsonify({
        'success': True,
        'xp_earned': xp,
        'total_xp': game_stats.xp,
        'streak': game_stats.meditation_streak,
        'total_sessions': game_stats.meditation_sessions_total,
        'total_minutes': game_stats.meditation_minutes_total,
        'achievements': [a['name'] for a in new_achievements],
        'leveled_up': leveled_up
    })


@app.route('/api/meditate/stats')
def meditate_stats():
    """Return meditation stats as JSON"""
    game_stats = get_or_create_game_stats()
    today = datetime.now().date()
    week_ago = today - timedelta(days=6)

    sessions = MeditationSession.query.filter(
        MeditationSession.date >= week_ago
    ).all()

    weekly = {}
    for i in range(7):
        d = (week_ago + timedelta(days=i))
        weekly[d.strftime('%a')] = 0
    for s in sessions:
        key = s.date.strftime('%a')
        weekly[key] = weekly.get(key, 0) + s.duration_seconds // 60

    return jsonify({
        'streak': game_stats.meditation_streak or 0,
        'total_sessions': game_stats.meditation_sessions_total or 0,
        'total_minutes': game_stats.meditation_minutes_total or 0,
        'total_xp': game_stats.meditation_xp_total or 0,
        'weekly': weekly
    })


##############################################
# NUTRITION ROUTES
##############################################

@app.route('/nutrition')
def nutrition():
    """Nutrition dashboard - daily log, calorie progress, macros, weekly chart"""
    profile = NutritionProfile.query.first()
    if not profile:
        return redirect(url_for('nutrition_setup'))

    game_stats = get_or_create_game_stats()
    today = datetime.now().date()

    # Today's entries
    today_entries = NutritionEntry.query.filter_by(date=today).order_by(NutritionEntry.created_at).all()
    today_calories = sum(e.calories or 0 for e in today_entries)
    today_protein = sum(e.protein_grams or 0 for e in today_entries)
    today_carbs = sum(e.carbs_grams or 0 for e in today_entries)
    today_fat = sum(e.fat_grams or 0 for e in today_entries)

    # Calculate macro targets in grams
    protein_target_g = round(profile.calorie_target * (profile.protein_target_pct / 100) / 4)
    carbs_target_g = round(profile.calorie_target * (profile.carbs_target_pct / 100) / 4)
    fat_target_g = round(profile.calorie_target * (profile.fat_target_pct / 100) / 9)

    # Weekly data for chart (last 7 days)
    week_ago = today - timedelta(days=6)
    recent_entries = NutritionEntry.query.filter(NutritionEntry.date >= week_ago).all()
    weekly_data = {}
    for i in range(7):
        d = week_ago + timedelta(days=i)
        weekly_data[d.strftime('%a')] = 0
    for e in recent_entries:
        key = e.date.strftime('%a')
        weekly_data[key] = weekly_data.get(key, 0) + (e.calories or 0)

    # Latest meal plan
    latest_plan = MealPlan.query.order_by(MealPlan.created_at.desc()).first()

    # Weight tracking data
    today_weight = WeightEntry.query.filter_by(date=today).first()
    latest_weight = WeightEntry.query.order_by(WeightEntry.date.desc()).first()

    return render_template('nutrition.html',
                         profile=profile,
                         game_stats=game_stats,
                         today_entries=today_entries,
                         today_calories=today_calories,
                         today_protein=today_protein,
                         today_carbs=today_carbs,
                         today_fat=today_fat,
                         protein_target_g=protein_target_g,
                         carbs_target_g=carbs_target_g,
                         fat_target_g=fat_target_g,
                         weekly_data=weekly_data,
                         latest_plan=latest_plan,
                         today_weight=today_weight,
                         latest_weight=latest_weight,
                         today=today)


@app.route('/nutrition/setup')
def nutrition_setup():
    """Nutrition profile setup page"""
    profile = NutritionProfile.query.first()
    return render_template('nutrition_setup.html', profile=profile)


@app.route('/nutrition/plan')
def nutrition_plan():
    """View meal plan page"""
    profile = NutritionProfile.query.first()
    if not profile:
        return redirect(url_for('nutrition_setup'))
    latest_plan = MealPlan.query.order_by(MealPlan.created_at.desc()).first()
    # Convert stored markdown to HTML for rendering
    plan_content_html = None
    plan_grocery_html = None
    if latest_plan:
        plan_content_html = markdown.markdown(latest_plan.content) if latest_plan.content else ''
        plan_grocery_html = markdown.markdown(latest_plan.grocery_list) if latest_plan.grocery_list else ''
    return render_template('meal_plan.html', profile=profile, plan=latest_plan,
                         plan_content_html=plan_content_html, plan_grocery_html=plan_grocery_html)


@app.route('/api/nutrition/setup', methods=['POST'])
def nutrition_setup_save():
    """Save nutrition profile and calculate TDEE"""
    data = request.get_json()

    profile = NutritionProfile.query.first()
    if not profile:
        profile = NutritionProfile()
        db.session.add(profile)

    profile.height_cm = float(data.get('height_cm', 170))
    profile.weight_kg = float(data.get('weight_kg', 70))
    profile.age = int(data.get('age', 25))
    profile.sex = data.get('sex', 'male')
    profile.activity_level = data.get('activity_level', 'moderate')
    profile.dietary_preferences = data.get('dietary_preferences', '')
    if data.get('target_weight_kg'):
        profile.target_weight_kg = float(data['target_weight_kg'])
    profile.protein_target_pct = int(data.get('protein_pct', 30))
    profile.carbs_target_pct = int(data.get('carbs_pct', 40))
    profile.fat_target_pct = int(data.get('fat_pct', 30))

    # Mifflin-St Jeor formula
    if profile.sex == 'male':
        bmr = 10 * profile.weight_kg + 6.25 * profile.height_cm - 5 * profile.age + 5
    else:
        bmr = 10 * profile.weight_kg + 6.25 * profile.height_cm - 5 * profile.age - 161

    multipliers = {
        'sedentary': 1.2,
        'light': 1.375,
        'moderate': 1.55,
        'active': 1.725,
        'very_active': 1.9
    }
    tdee = round(bmr * multipliers.get(profile.activity_level, 1.55))

    # Allow manual override
    manual = data.get('calorie_target')
    if manual and int(manual) > 0:
        profile.calorie_target = int(manual)
    else:
        profile.calorie_target = tdee

    db.session.commit()

    return jsonify({
        'success': True,
        'bmr': round(bmr),
        'tdee': tdee,
        'calorie_target': profile.calorie_target
    })


@app.route('/api/nutrition/log', methods=['POST'])
def nutrition_log():
    """Log a meal - Claude estimates calories and macros from text description"""
    data = request.get_json()
    description = data.get('description', '').strip()
    meal_type = data.get('meal_type', 'snack')

    today = datetime.now().date()

    if not description:
        return jsonify({'error': 'Please describe your meal'}), 400

    profile = NutritionProfile.query.first()
    if not profile:
        return jsonify({'error': 'Please set up your nutrition profile first'}), 400

    # Use Claude to estimate calories and macros
    estimated = {'calories': 300, 'protein': 15, 'carbs': 35, 'fat': 10, 'name': description}

    if claude_client:
        try:
            response = call_claude('nutrition', 'log_meal',
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                messages=[{
                    "role": "user",
                    "content": f"""Estimate calories and macros for this meal: "{description}".

IMPORTANT RULES:
1. If the user provides exact values (e.g. "150cal", "20g protein"), use those numbers directly.
2. For homemade meals, estimate GENEROUS realistic portions (a plate of pasta is typically 400-500g cooked, not 200g). A homemade pasta dish with sauce and meat is typically 700-1100 calories.
3. Account for cooking oils, butter, cheese, sauces — these add significant calories that are often overlooked.
4. When in doubt, estimate HIGHER rather than lower. Underestimating calories is worse than overestimating for tracking purposes.
5. Think step by step: list the likely ingredients and their calorie contributions, then sum.

Return ONLY valid JSON with no extra text: {{"calories": int, "protein": float, "carbs": float, "fat": float, "name": "clean short name"}}"""
                }]
            )
            text = response.content[0].text.strip()
            # Extract JSON from response
            if '{' in text:
                json_str = text[text.index('{'):text.rindex('}') + 1]
                estimated = json.loads(json_str)
        except Exception as e:
            print(f"Claude estimation error: {e}")

    meal_date_str = data.get('date', '')
    if meal_date_str:
        try:
            meal_date = datetime.strptime(meal_date_str, '%Y-%m-%d').date()
        except ValueError:
            meal_date = datetime.now().date()
    else:
        meal_date = datetime.now().date()
    xp = 5  # base XP per meal log

    entry = NutritionEntry(
        date=meal_date,
        meal_type=meal_type,
        description=estimated.get('name', description),
        calories=int(estimated.get('calories', 300)),
        protein_grams=round(float(estimated.get('protein', 15)), 1),
        carbs_grams=round(float(estimated.get('carbs', 35)), 1),
        fat_grams=round(float(estimated.get('fat', 10)), 1),
        xp_earned=xp
    )
    db.session.add(entry)

    # Update GameStats
    game_stats = get_or_create_game_stats()
    game_stats.xp += xp
    game_stats.nutrition_entries_total = (game_stats.nutrition_entries_total or 0) + 1
    game_stats.nutrition_xp_total = (game_stats.nutrition_xp_total or 0) + xp

    # Update nutrition streak
    if game_stats.last_nutrition_date:
        days_diff = (today - game_stats.last_nutrition_date).days
        if days_diff == 1:
            game_stats.nutrition_streak = (game_stats.nutrition_streak or 0) + 1
        elif days_diff > 1:
            game_stats.nutrition_streak = 1
    else:
        game_stats.nutrition_streak = 1
    game_stats.last_nutrition_date = today

    # Check for daily bonus: logged all 3 main meals today
    today_entries = NutritionEntry.query.filter_by(date=today).all()
    today_types = [e.meal_type for e in today_entries]
    if all(m in today_types for m in ['breakfast', 'lunch', 'dinner']):
        bonus = 10
        game_stats.xp += bonus
        game_stats.nutrition_xp_total = (game_stats.nutrition_xp_total or 0) + bonus
        xp += bonus

    # Check calorie target bonus
    today_total = sum(e.calories or 0 for e in today_entries)
    if profile.calorie_target and abs(today_total - profile.calorie_target) <= profile.calorie_target * 0.1:
        bonus = 5
        game_stats.xp += bonus
        game_stats.nutrition_xp_total = (game_stats.nutrition_xp_total or 0) + bonus
        xp += bonus

    db.session.commit()

    # Check achievements
    new_achievements = check_achievements(game_stats)
    leveled_up = check_level_up(game_stats)
    db.session.commit()

    return jsonify({
        'success': True,
        'entry': {
            'id': entry.id,
            'meal_type': entry.meal_type,
            'description': entry.description,
            'calories': entry.calories,
            'protein': entry.protein_grams,
            'carbs': entry.carbs_grams,
            'fat': entry.fat_grams
        },
        'xp_earned': xp,
        'total_xp': game_stats.xp,
        'streak': game_stats.nutrition_streak or 0,
        'achievements': [a['name'] for a in new_achievements],
        'leveled_up': leveled_up
    })


@app.route('/api/nutrition/entry/<int:entry_id>', methods=['DELETE'])
def nutrition_delete(entry_id):
    """Delete a nutrition entry"""
    entry = NutritionEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/nutrition/generate-plan', methods=['POST'])
def nutrition_generate_plan():
    """Generate a weekly meal plan using Claude"""
    profile = NutritionProfile.query.first()
    if not profile:
        return jsonify({'error': 'Please set up your nutrition profile first'}), 400

    if not claude_client:
        return jsonify({'error': 'Claude API not configured'}), 500

    try:
        prompt = f"""Generate a 7-day meal plan for someone targeting {profile.calorie_target} calories per day.
Dietary preferences: {profile.dietary_preferences or 'None specified'}
Macro split: {profile.protein_target_pct}% protein, {profile.carbs_target_pct}% carbs, {profile.fat_target_pct}% fat

For each day, include: breakfast, lunch, dinner, and 1 snack.
For each meal, include estimated calories and a brief description.

Format as markdown with clear day headers (## Monday, ## Tuesday, etc.)
After all 7 days, add a section: ## Grocery List
with a consolidated, organized grocery list grouped by category (Produce, Protein, Dairy, Pantry, etc.)."""

        response = call_claude('nutrition', 'generate_plan',
            model="claude-sonnet-4-5-20250929",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )

        content = response.content[0].text

        # Split content and grocery list
        grocery_list = ''
        if '## Grocery List' in content:
            parts = content.split('## Grocery List', 1)
            content = parts[0]
            grocery_list = '## Grocery List' + parts[1]
        elif '## grocery list' in content.lower():
            idx = content.lower().index('## grocery list')
            grocery_list = content[idx:]
            content = content[:idx]

        today = datetime.now().date()
        # Start from next Monday
        days_ahead = (7 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        start = today + timedelta(days=days_ahead)
        end = start + timedelta(days=6)

        plan = MealPlan(
            start_date=start,
            end_date=end,
            content=content,
            grocery_list=grocery_list,
            calorie_target=profile.calorie_target
        )
        db.session.add(plan)

        # Update stats
        game_stats = get_or_create_game_stats()
        game_stats.meal_plans_generated = (game_stats.meal_plans_generated or 0) + 1
        xp = 15
        game_stats.xp += xp
        game_stats.nutrition_xp_total = (game_stats.nutrition_xp_total or 0) + xp

        db.session.commit()

        new_achievements = check_achievements(game_stats)
        leveled_up = check_level_up(game_stats)
        db.session.commit()

        return jsonify({
            'success': True,
            'plan': {
                'content': markdown.markdown(content),
                'grocery_list': markdown.markdown(grocery_list),
                'start_date': start.isoformat(),
                'end_date': end.isoformat(),
                'calorie_target': profile.calorie_target
            },
            'xp_earned': xp,
            'achievements': [a['name'] for a in new_achievements],
            'leveled_up': leveled_up
        })
    except Exception as e:
        print(f"Meal plan generation error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/nutrition/stats')
def nutrition_stats():
    """Return nutrition stats as JSON"""
    game_stats = get_or_create_game_stats()
    today = datetime.now().date()
    profile = NutritionProfile.query.first()

    today_entries = NutritionEntry.query.filter_by(date=today).all()
    today_calories = sum(e.calories or 0 for e in today_entries)

    return jsonify({
        'streak': game_stats.nutrition_streak or 0,
        'total_entries': game_stats.nutrition_entries_total or 0,
        'total_xp': game_stats.nutrition_xp_total or 0,
        'today_calories': today_calories,
        'calorie_target': profile.calorie_target if profile else 2000
    })


@app.route('/api/nutrition/weight', methods=['POST'])
def nutrition_weight_log():
    """Log a weight entry for today (or update if already exists)"""
    data = request.get_json()
    weight = data.get('weight_kg')
    date_str = data.get('date')

    if not weight:
        return jsonify({'error': 'Weight is required'}), 400

    try:
        weight = float(weight)
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid weight value'}), 400

    target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.now().date()

    existing = WeightEntry.query.filter_by(date=target_date).first()
    if existing:
        existing.weight_kg = weight
    else:
        existing = WeightEntry(date=target_date, weight_kg=weight)
        db.session.add(existing)

    # Also update NutritionProfile current weight
    profile = NutritionProfile.query.first()
    if profile:
        profile.weight_kg = weight

    db.session.commit()

    return jsonify({
        'success': True,
        'entry': {
            'id': existing.id,
            'date': existing.date.isoformat(),
            'weight_kg': existing.weight_kg
        }
    })


@app.route('/api/nutrition/weight', methods=['GET'])
def nutrition_weight_data():
    """Get weight history. ?range=week|month|3month|6month|year|all"""
    range_param = request.args.get('range', 'month')
    today = datetime.now().date()

    if range_param == 'week':
        start = today - timedelta(days=6)
    elif range_param == 'month':
        start = today - timedelta(days=29)
    elif range_param == '3month':
        start = today - timedelta(days=89)
    elif range_param == '6month':
        start = today - timedelta(days=179)
    elif range_param == 'year':
        start = today - timedelta(days=364)
    else:
        start = None

    query = WeightEntry.query.order_by(WeightEntry.date.asc())
    if start:
        query = query.filter(WeightEntry.date >= start)

    entries = query.all()

    return jsonify({
        'entries': [{'date': e.date.isoformat(), 'weight_kg': e.weight_kg} for e in entries],
        'target_weight': NutritionProfile.query.first().target_weight_kg if NutritionProfile.query.first() else None
    })


@app.route('/api/nutrition/weight/<int:entry_id>', methods=['DELETE'])
def nutrition_weight_delete(entry_id):
    """Delete a weight entry"""
    entry = WeightEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({'success': True})


##############################################
# ACTIVITY ROUTES
##############################################

@app.route('/activity')
def activity():
    """Activity dashboard — weekly summary, recent workouts, progress chart"""
    game_stats = get_or_create_game_stats()
    today = datetime.now().date()

    # This week's workouts (Monday to Sunday)
    week_start = today - timedelta(days=today.weekday())
    week_workouts = Workout.query.filter(Workout.date >= week_start).order_by(Workout.date.desc()).all()

    week_runs = [w for w in week_workouts if w.workout_type == 'run']
    week_gym = [w for w in week_workouts if w.workout_type == 'gym']
    week_cross = [w for w in week_workouts if w.workout_type == 'cross-training']

    total_km_week = sum(w.distance_km or 0 for w in week_runs)
    total_duration_week = sum(w.duration_minutes or 0 for w in week_workouts)

    # Gym muscle groups hit this week
    muscle_groups_week = set()
    for w in week_gym:
        if w.muscle_groups:
            try:
                groups = json.loads(w.muscle_groups)
                muscle_groups_week.update(groups)
            except (json.JSONDecodeError, TypeError):
                pass

    # Recent workouts (last 10)
    recent_workouts = Workout.query.order_by(Workout.date.desc(), Workout.created_at.desc()).limit(10).all()

    # Weekly volume chart (last 8 weeks)
    eight_weeks_ago = today - timedelta(weeks=8)
    all_recent = Workout.query.filter(Workout.date >= eight_weeks_ago).all()
    weekly_volume = {}
    for i in range(8):
        ws = today - timedelta(weeks=7-i, days=today.weekday())
        we = ws + timedelta(days=6)
        label = ws.strftime('%b %d')
        runs_km = sum(w.distance_km or 0 for w in all_recent if w.workout_type == 'run' and ws <= w.date <= we)
        gym_count = sum(1 for w in all_recent if w.workout_type == 'gym' and ws <= w.date <= we)
        weekly_volume[label] = {'runs_km': round(runs_km, 1), 'gym': gym_count}

    # Active training plan
    active_plan = TrainingPlan.query.filter_by(is_active=True).first()
    current_phase = None
    plan_week_number = None
    if active_plan and active_plan.target_date:
        days_until = (active_plan.target_date - today).days
        if active_plan.phase_summary:
            try:
                phases = json.loads(active_plan.phase_summary)
                weeks_since_start = (today - active_plan.created_at.date()).days // 7 + 1
                plan_week_number = weeks_since_start
                for p in phases:
                    if p.get('start_week', 0) <= weeks_since_start <= p.get('end_week', 999):
                        current_phase = p.get('phase', 'Unknown')
                        break
            except (json.JSONDecodeError, TypeError):
                pass
    else:
        days_until = None

    # Weekly compliance (if plan exists)
    compliance = None
    if active_plan:
        current_week = TrainingWeek.query.filter_by(plan_id=active_plan.id, week_number=plan_week_number).first() if plan_week_number else None
        if current_week:
            compliance = current_week.compliance_pct

    # Garmin daily stats (today + yesterday)
    garmin_today = GarminDailyStats.query.filter_by(date=today).first()
    garmin_yesterday = GarminDailyStats.query.filter_by(date=today - timedelta(days=1)).first()
    garmin_available = bool(os.getenv('GARMIN_EMAIL') and os.getenv('GARMIN_PASSWORD'))

    return render_template('activity.html',
                         game_stats=game_stats,
                         week_runs=week_runs,
                         week_gym=week_gym,
                         week_cross=week_cross,
                         total_km_week=round(total_km_week, 1),
                         total_duration_week=total_duration_week,
                         muscle_groups_week=sorted(muscle_groups_week),
                         recent_workouts=recent_workouts,
                         weekly_volume=json.dumps(weekly_volume),
                         active_plan=active_plan,
                         current_phase=current_phase,
                         plan_week_number=plan_week_number,
                         days_until=days_until,
                         compliance=compliance,
                         garmin_today=garmin_today,
                         garmin_yesterday=garmin_yesterday,
                         garmin_available=garmin_available)


@app.route('/activity/log')
def activity_log():
    """Log workout form"""
    return render_template('activity_log.html')


@app.route('/activity/plan')
def activity_plan():
    """Marathon Training Calendar — monthly grid view"""
    active_plan = TrainingPlan.query.filter_by(is_active=True).first()
    today = datetime.now().date()

    days_until = None
    current_phase = None
    plan_week_number = None
    calendar_data = None
    has_schedule = False

    if active_plan:
        if active_plan.target_date:
            days_until = (active_plan.target_date - today).days

        if active_plan.phase_summary:
            try:
                phases = json.loads(active_plan.phase_summary)
                weeks_since_start = (today - active_plan.created_at.date()).days // 7 + 1
                plan_week_number = weeks_since_start
                for p in phases:
                    if p.get('start_week', 0) <= weeks_since_start <= p.get('end_week', 999):
                        current_phase = p.get('phase', 'Unknown')
                        break
            except (json.JSONDecodeError, TypeError):
                pass

        has_schedule = TrainingDay.query.filter_by(plan_id=active_plan.id).count() > 0

        if has_schedule:
            import calendar as cal_module
            year = request.args.get('year', today.year, type=int)
            month = request.args.get('month', today.month, type=int)
            if not (1 <= month <= 12):
                month = today.month
            if not (2020 <= year <= 2035):
                year = today.year

            first_day = date(year, month, 1)
            last_day = date(year, month, cal_module.monthrange(year, month)[1])

            month_days = TrainingDay.query.filter(
                TrainingDay.plan_id == active_plan.id,
                TrainingDay.date >= first_day,
                TrainingDay.date <= last_day
            ).order_by(TrainingDay.date).all()

            days_by_date = {d.date.isoformat(): d.to_dict() for d in month_days}

            # Build calendar grid (weeks starting Monday)
            cal_grid = []
            week = [None] * first_day.weekday()
            current = first_day
            while current <= last_day:
                week.append(current.isoformat())
                if len(week) == 7:
                    cal_grid.append(week)
                    week = []
                current += timedelta(days=1)
            if week:
                week += [None] * (7 - len(week))
                cal_grid.append(week)

            # Week km totals
            week_totals = {}
            for d in month_days:
                wn = d.date.isocalendar()[1]
                if wn not in week_totals:
                    week_totals[wn] = {'km': 0, 'gym': 0}
                if d.session_type == 'run' and d.planned_km:
                    week_totals[wn]['km'] += d.planned_km
                elif d.session_type == 'gym':
                    week_totals[wn]['gym'] += 1

            if month == 1:
                prev_year, prev_month = year - 1, 12
            else:
                prev_year, prev_month = year, month - 1
            if month == 12:
                next_year, next_month = year + 1, 1
            else:
                next_year, next_month = year, month + 1

            calendar_data = {
                'year': year,
                'month': month,
                'month_name': first_day.strftime('%B %Y'),
                'cal_grid': cal_grid,
                'days_by_date': days_by_date,
                'week_totals': week_totals,
                'prev_year': prev_year, 'prev_month': prev_month,
                'next_year': next_year, 'next_month': next_month,
                'today': today.isoformat(),
            }

    all_plans = TrainingPlan.query.order_by(TrainingPlan.created_at.desc()).all()

    # Parse phase summary safely for template JS
    phase_data = []
    if active_plan and active_plan.phase_summary:
        try:
            phase_data = json.loads(active_plan.phase_summary)
        except (json.JSONDecodeError, TypeError):
            pass

    return render_template('activity_plan.html',
                         active_plan=active_plan,
                         has_schedule=has_schedule,
                         calendar_data=calendar_data,
                         days_until=days_until,
                         current_phase=current_phase,
                         plan_week_number=plan_week_number,
                         phase_data=phase_data,
                         all_plans=all_plans)


@app.route('/activity/expert')
def activity_expert():
    """Sport expert AI coach chat"""
    game_stats = get_or_create_game_stats()
    today = datetime.now().date()

    # Context for sidebar
    active_plan = TrainingPlan.query.filter_by(is_active=True).first()
    days_until = (active_plan.target_date - today).days if active_plan and active_plan.target_date else None

    week_start = today - timedelta(days=today.weekday())
    week_workouts = Workout.query.filter(Workout.date >= week_start).all()
    week_km = sum(w.distance_km or 0 for w in week_workouts if w.workout_type == 'run')
    week_sessions = len(week_workouts)

    current_phase = None
    if active_plan and active_plan.phase_summary:
        try:
            phases = json.loads(active_plan.phase_summary)
            weeks_since_start = (today - active_plan.created_at.date()).days // 7 + 1
            for p in phases:
                if p.get('start_week', 0) <= weeks_since_start <= p.get('end_week', 999):
                    current_phase = p.get('phase', 'Unknown')
                    break
        except (json.JSONDecodeError, TypeError):
            pass

    # Chat history from session
    chat_history = session.get('coach_chat', [])

    return render_template('activity_expert.html',
                         game_stats=game_stats,
                         active_plan=active_plan,
                         days_until=days_until,
                         week_km=round(week_km, 1),
                         week_sessions=week_sessions,
                         current_phase=current_phase,
                         chat_history=chat_history)


@app.route('/activity/history')
def activity_history():
    """Full workout history with filters"""
    workout_type = request.args.get('type', 'all')
    page = request.args.get('page', 1, type=int)

    query = Workout.query.order_by(Workout.date.desc(), Workout.created_at.desc())
    if workout_type != 'all':
        query = query.filter_by(workout_type=workout_type)

    workouts = query.paginate(page=page, per_page=20, error_out=False)

    # Summary stats
    total_workouts = Workout.query.count()
    total_runs = Workout.query.filter_by(workout_type='run').count()
    total_gym = Workout.query.filter_by(workout_type='gym').count()
    total_km = db.session.query(db.func.sum(Workout.distance_km)).filter(Workout.workout_type == 'run').scalar() or 0

    return render_template('activity_history.html',
                         workouts=workouts,
                         workout_type=workout_type,
                         total_workouts=total_workouts,
                         total_runs=total_runs,
                         total_gym=total_gym,
                         total_km=round(total_km, 1))


@app.route('/api/activity/log', methods=['POST'])
def activity_log_save():
    """Save a workout and award XP"""
    data = request.get_json()
    today = datetime.now().date()

    workout_type = data.get('type', 'run')
    workout_date = datetime.strptime(data.get('date', today.isoformat()), '%Y-%m-%d').date()

    # Build workout
    workout = Workout(
        date=workout_date,
        workout_type=workout_type,
        notes=data.get('notes', ''),
    )

    # Type-specific fields
    if workout_type == 'run':
        workout.distance_km = float(data.get('distance_km', 0) or 0)
        workout.duration_minutes = round(float(data.get('duration_minutes', 0) or 0), 2)
        workout.effort = data.get('effort', 'easy')
        workout.heart_rate_avg = int(data.get('heart_rate_avg', 0) or 0) or None
        # Compute pace
        if workout.distance_km and workout.duration_minutes:
            pace_total_sec = (workout.duration_minutes * 60) / workout.distance_km
            pace_min = int(pace_total_sec // 60)
            pace_sec = int(pace_total_sec % 60)
            workout.pace_per_km = f"{pace_min}:{pace_sec:02d}"
        workout.title = data.get('title') or f"{workout.effort.capitalize()} Run — {workout.distance_km}km"
    elif workout_type == 'gym':
        exercises = data.get('exercises', [])
        workout.exercises = json.dumps(exercises)
        workout.muscle_groups = json.dumps(data.get('muscle_groups', []))
        workout.duration_minutes = round(float(data.get('duration_minutes', 0) or 0), 2)
        exercise_names = [e.get('name', '') for e in exercises[:3]]
        workout.title = data.get('title') or (f"Gym — {', '.join(exercise_names)}" if exercise_names else "Gym Session")
    else:  # cross-training
        workout.duration_minutes = round(float(data.get('duration_minutes', 0) or 0), 2)
        workout.title = data.get('title') or data.get('activity_name', 'Cross-training')

    # Calculate XP
    if workout_type == 'run':
        xp = 15 + int((workout.distance_km or 0) * 2)
        if workout.effort == 'hard':
            xp += 5
        elif workout.effort == 'race':
            xp += 10
    elif workout_type == 'gym':
        exercises_list = json.loads(workout.exercises) if workout.exercises else []
        # Count total sets: new format has sets as array, old format has sets as int
        total_sets = 0
        for ex in exercises_list:
            s = ex.get('sets', [])
            total_sets += len(s) if isinstance(s, list) else (int(s) if s else 0)
        xp = 15 + total_sets
    else:
        xp = 10 + (workout.duration_minutes or 0) // 10

    workout.xp_earned = xp
    db.session.add(workout)

    # Update GameStats
    game_stats = get_or_create_game_stats()
    game_stats.xp += xp
    game_stats.activity_sessions_total = (game_stats.activity_sessions_total or 0) + 1
    game_stats.activity_xp_total = (game_stats.activity_xp_total or 0) + xp

    # Update streak
    if game_stats.last_activity_date:
        days_diff = (workout_date - game_stats.last_activity_date).days
        if days_diff == 1:
            game_stats.activity_streak = (game_stats.activity_streak or 0) + 1
        elif days_diff > 1:
            game_stats.activity_streak = 1
        # days_diff == 0: same day, no streak change
    else:
        game_stats.activity_streak = 1
    if workout_date >= (game_stats.last_activity_date or workout_date):
        game_stats.last_activity_date = workout_date

    db.session.commit()

    # Check achievements
    new_achievements = check_achievements(game_stats)
    for a in new_achievements:
        flash(f'🏆 Achievement Unlocked: {a["name"]}!', 'success')

    leveled_up = check_level_up(game_stats)
    if leveled_up:
        flash(f'🎉 Level Up! You are now {game_stats.level_name}!', 'success')

    db.session.commit()

    flash(f'💪 Workout logged! +{xp} XP', 'success')

    return jsonify({
        'success': True,
        'xp_earned': xp,
        'total_xp': game_stats.xp,
        'streak': game_stats.activity_streak,
        'total_sessions': game_stats.activity_sessions_total,
        'achievements': [a['name'] for a in new_achievements],
        'leveled_up': leveled_up
    })


@app.route('/api/activity/<int:workout_id>', methods=['DELETE'])
def activity_delete(workout_id):
    """Delete a workout entry"""
    workout = Workout.query.get_or_404(workout_id)
    db.session.delete(workout)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/activity/generate-plan', methods=['POST'])
def activity_generate_plan():
    """Generate a periodized training plan using Claude"""
    if not claude_client:
        return jsonify({'error': 'Claude API not configured'}), 500

    data = request.get_json()
    today = datetime.now().date()
    target_date = datetime.strptime(data.get('target_date', '2026-10-10'), '%Y-%m-%d').date()
    target_event = data.get('target_event', 'Marathon')
    goals = data.get('goals', 'Complete the marathon + weight loss')
    notes = data.get('notes', '')

    # Gather context: recent 4 weeks of workouts
    four_weeks_ago = today - timedelta(weeks=4)
    recent_workouts = Workout.query.filter(Workout.date >= four_weeks_ago).order_by(Workout.date).all()
    workout_summary = []
    for w in recent_workouts:
        if w.workout_type == 'run':
            workout_summary.append(f"  {w.date}: Run — {w.distance_km}km in {w.duration_minutes}min ({w.effort}), pace {w.pace_per_km}/km")
        elif w.workout_type == 'gym':
            workout_summary.append(f"  {w.date}: Gym — {w.title}")
        else:
            workout_summary.append(f"  {w.date}: Cross-training — {w.title} ({w.duration_minutes}min)")

    workout_context = '\n'.join(workout_summary) if workout_summary else '  No workouts logged yet.'

    # Get body stats from nutrition profile
    profile = NutritionProfile.query.first()
    body_context = ''
    if profile:
        body_context = f"\nBody stats: {profile.weight_kg}kg, {profile.height_cm}cm, age {profile.age}, {profile.sex}, activity level: {profile.activity_level}"

    weeks_until = (target_date - today).days // 7

    try:
        response = call_claude('activity', 'generate_plan',
            model='claude-sonnet-4-20250514',
            max_tokens=4000,
            system="""You are an expert running coach and sport scientist. Create a detailed, periodized training plan.
Output the plan in TWO sections separated by ---JSON---:
1. The full training plan in markdown
2. A JSON array of phases: [{"phase": "Base", "start_week": 1, "end_week": 6, "focus": "..."}]""",
            messages=[{
                'role': 'user',
                'content': f"""Create a training plan for me:

Target: {target_event} on {target_date.strftime('%B %d, %Y')} ({weeks_until} weeks away)
Goals: {goals}
{body_context}
Additional notes: {notes}

Recent training (last 4 weeks):
{workout_context}

Today's date: {today.strftime('%B %d, %Y')}

Create a periodized plan with Base Building, Build, Peak, and Taper phases.
Include weekly running schedule + 1-2 gym sessions per week.
Use specific paces, distances, and effort zones.
Account for weight loss goal (moderate caloric deficit compatible with training).
End with ---JSON--- followed by the phases JSON array."""
            }]
        )

        plan_text = response.content[0].text

        # Parse plan content and phase JSON
        plan_content = plan_text
        phase_summary = '[]'
        if '---JSON---' in plan_text:
            parts = plan_text.split('---JSON---')
            plan_content = parts[0].strip()
            try:
                phase_json = parts[1].strip()
                json.loads(phase_json)  # Validate JSON
                phase_summary = phase_json
            except (json.JSONDecodeError, IndexError):
                phase_summary = '[]'

        # Deactivate any existing active plans
        TrainingPlan.query.filter_by(is_active=True).update({'is_active': False})

        plan = TrainingPlan(
            target_event=target_event,
            target_date=target_date,
            goals=goals,
            current_fitness_summary=workout_context,
            plan_content=plan_content,
            phase_summary=phase_summary,
            is_active=True
        )
        db.session.add(plan)
        db.session.commit()

        return jsonify({
            'success': True,
            'plan_id': plan.id,
            'plan_html': markdown.markdown(plan_content)
        })
    except Exception as e:
        print(f"Training plan generation error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/activity/coach', methods=['POST'])
def activity_coach():
    """Chat with the Sport Expert AI coach"""
    if not claude_client:
        return jsonify({'error': 'Claude API not configured'}), 500

    data = request.get_json()
    user_message = data.get('message', '')
    if not user_message.strip():
        return jsonify({'error': 'Empty message'}), 400

    today = datetime.now().date()

    # Build context
    active_plan = TrainingPlan.query.filter_by(is_active=True).first()
    plan_context = ''
    if active_plan:
        days_until = (active_plan.target_date - today).days if active_plan.target_date else '?'
        plan_context = f"\nActive plan: {active_plan.target_event} on {active_plan.target_date} ({days_until} days away)\nGoals: {active_plan.goals}"
        if active_plan.phase_summary:
            try:
                phases = json.loads(active_plan.phase_summary)
                weeks_since_start = (today - active_plan.created_at.date()).days // 7 + 1
                for p in phases:
                    if p.get('start_week', 0) <= weeks_since_start <= p.get('end_week', 999):
                        plan_context += f"\nCurrent phase: {p.get('phase')} (week {weeks_since_start}) — {p.get('focus', '')}"
                        break
            except (json.JSONDecodeError, TypeError):
                pass

        # Upcoming 3 weeks of scheduled sessions
        week_start = today - timedelta(days=today.weekday())  # Monday
        three_weeks_end = week_start + timedelta(days=20)  # 3 weeks
        upcoming_days = TrainingDay.query.filter(
            TrainingDay.plan_id == active_plan.id,
            TrainingDay.date >= week_start,
            TrainingDay.date <= three_weeks_end,
        ).order_by(TrainingDay.date).all()
        if upcoming_days:
            plan_context += f"\n\nUpcoming training schedule ({week_start.strftime('%b %d')} – {three_weeks_end.strftime('%b %d')}):"
            current_week_label = None
            for d in upcoming_days:
                # Add week separator
                d_week_start = d.date - timedelta(days=d.date.weekday())
                week_label = d_week_start.strftime('%b %d')
                if week_label != current_week_label:
                    current_week_label = week_label
                    plan_context += f"\n  Week of {week_label}:"

                status_icon = '✅' if d.status == 'completed' else '⏭️' if d.status == 'skipped' else '📋'
                km_str = f" — {d.planned_km}km" if d.planned_km else ""
                key_str = " ⭐KEY" if d.is_key_session else ""
                plan_context += f"\n    {status_icon} {d.date.strftime('%a %b %d')}: {d.session_type.upper()} — {d.title or 'No title'}{km_str} [{d.effort_level or '?'}]{key_str}"
                if d.description:
                    plan_context += f"\n        Detail: {d.description[:200]}"

        # Tomorrow + today specifically highlighted
        tomorrow = today + timedelta(days=1)
        today_session = TrainingDay.query.filter_by(plan_id=active_plan.id, date=today).first()
        tomorrow_session = TrainingDay.query.filter_by(plan_id=active_plan.id, date=tomorrow).first()
        if today_session and today_session.status == 'planned':
            plan_context += f"\n\n📌 TODAY's planned session: {today_session.session_type.upper()} — {today_session.title or ''}"
            if today_session.description:
                plan_context += f"\n   {today_session.description[:300]}"
        if tomorrow_session and tomorrow_session.status == 'planned':
            plan_context += f"\n📌 TOMORROW's planned session: {tomorrow_session.session_type.upper()} — {tomorrow_session.title or ''}"
            if tomorrow_session.description:
                plan_context += f"\n   {tomorrow_session.description[:300]}"

    # Recent 2 weeks of workouts
    two_weeks_ago = today - timedelta(weeks=2)
    recent = Workout.query.filter(Workout.date >= two_weeks_ago).order_by(Workout.date).all()
    workout_lines = []
    for w in recent:
        if w.workout_type == 'run':
            workout_lines.append(f"  {w.date}: Run — {w.distance_km}km, {w.duration_minutes}min, {w.effort}, pace {w.pace_per_km}/km" +
                                 (f", HR:{w.heart_rate_avg}" if w.heart_rate_avg else "") +
                                 (f" — {w.notes[:100]}" if w.notes else ""))
        elif w.workout_type == 'gym':
            gym_detail = f"  {w.date}: Gym"
            if w.exercises:
                try:
                    exercises = json.loads(w.exercises) if isinstance(w.exercises, str) else w.exercises
                    if exercises:
                        ex_parts = []
                        for ex in exercises:
                            name = ex.get('name', 'Unknown')
                            sets = ex.get('sets', [])
                            if isinstance(sets, list):
                                # New per-set format
                                set_strs = []
                                for s in sets:
                                    w_kg = s.get('weight_kg', 0)
                                    reps = s.get('reps', 0)
                                    failed = ' FAIL' if s.get('failed') else ''
                                    set_strs.append(f"{w_kg}kg×{reps}{failed}")
                                ex_str = f"{name}: {', '.join(set_strs)}"
                            else:
                                # Old flat format
                                reps = ex.get('reps', '')
                                weight = ex.get('weight_kg', '') or ex.get('weight', '')
                                ex_str = name
                                if sets and reps:
                                    ex_str += f" {sets}x{reps}"
                                if weight:
                                    ex_str += f" @{weight}kg"
                            ex_parts.append(ex_str)
                        gym_detail += f" — {', '.join(ex_parts)}"
                except (json.JSONDecodeError, TypeError):
                    if w.title:
                        gym_detail += f" — {w.title}"
            elif w.title:
                gym_detail += f" — {w.title}"
            if w.muscle_groups:
                try:
                    groups = json.loads(w.muscle_groups) if isinstance(w.muscle_groups, str) else w.muscle_groups
                    if groups:
                        gym_detail += f" [muscles: {', '.join(groups)}]"
                except (json.JSONDecodeError, TypeError):
                    pass
            if w.duration_minutes:
                gym_detail += f" ({w.duration_minutes}min)"
            if w.notes:
                gym_detail += f" — {w.notes[:100]}"
            workout_lines.append(gym_detail)
        else:
            workout_lines.append(f"  {w.date}: {w.title} — {w.duration_minutes}min" +
                                 (f" — {w.notes[:100]}" if w.notes else ""))
    workout_context = '\n'.join(workout_lines) if workout_lines else '  No recent workouts.'

    game_stats = get_or_create_game_stats()

    # Garmin health data (last 7 days)
    garmin_context = ''
    garmin_stats = GarminDailyStats.query.filter(
        GarminDailyStats.date >= today - timedelta(days=7),
        GarminDailyStats.steps > 0,
    ).order_by(GarminDailyStats.date.desc()).all()
    if garmin_stats:
        garmin_lines = ["Garmin health data (last 7 days):"]
        for g in garmin_stats:
            sleep_str = f"{g.sleep_seconds // 3600}h{(g.sleep_seconds % 3600) // 60}m" if g.sleep_seconds else "—"
            garmin_lines.append(
                f"  {g.date.strftime('%b %d')}: Steps {g.steps or 0}, RHR {g.resting_hr or '—'}bpm, "
                f"Body Battery {g.body_battery_high or '—'}/{g.body_battery_low or '—'} (wake: {g.body_battery_at_wake or '—'}), "
                f"Stress {g.avg_stress or '—'} ({g.stress_qualifier or ''}), "
                f"Sleep {sleep_str}" + (f" (score: {g.sleep_score})" if g.sleep_score else "")
            )
        garmin_context = '\n' + '\n'.join(garmin_lines)

    # Nutrition & weight context
    nutrition_context = ''
    profile = NutritionProfile.query.first()
    if profile:
        nutrition_lines = ["\nNutrition & Body:"]
        nutrition_lines.append(f"  Profile: {profile.weight_kg}kg, {profile.height_cm}cm, age {profile.age}, {profile.sex}")
        if profile.target_weight_kg:
            nutrition_lines.append(f"  Target weight: {profile.target_weight_kg}kg (delta: {round((profile.weight_kg or 0) - profile.target_weight_kg, 1)}kg)")
        if profile.calorie_target:
            nutrition_lines.append(f"  Daily calorie target: {profile.calorie_target} kcal (P:{profile.protein_target_pct}% C:{profile.carbs_target_pct}% F:{profile.fat_target_pct}%)")

        # Recent weight trend
        recent_weights = WeightEntry.query.filter(
            WeightEntry.date >= today - timedelta(days=30)
        ).order_by(WeightEntry.date.desc()).limit(10).all()
        if recent_weights:
            nutrition_lines.append(f"  Weight trend (last 30d):")
            for w in recent_weights:
                nutrition_lines.append(f"    {w.date.strftime('%b %d')}: {w.weight_kg}kg")

        # Recent nutrition (last 7 days avg)
        week_entries = NutritionEntry.query.filter(NutritionEntry.date >= today - timedelta(days=7)).all()
        if week_entries:
            days_with_data = len(set(e.date for e in week_entries))
            total_cal = sum(e.calories or 0 for e in week_entries)
            total_protein = sum(e.protein_grams or 0 for e in week_entries)
            avg_cal = round(total_cal / days_with_data) if days_with_data else 0
            avg_protein = round(total_protein / days_with_data) if days_with_data else 0
            nutrition_lines.append(f"  Last 7 days avg: {avg_cal} kcal/day, {avg_protein}g protein/day ({days_with_data} days tracked)")

        nutrition_context = '\n'.join(nutrition_lines)

    # Chat history
    chat_history = session.get('coach_chat', [])
    messages = []
    for msg in chat_history[-10:]:  # Keep last 10 exchanges
        messages.append({'role': msg['role'], 'content': msg['content']})
    messages.append({'role': 'user', 'content': user_message})

    try:
        response = call_claude('activity', 'coach',
            model='claude-sonnet-4-20250514',
            max_tokens=1500,
            system=f"""You are a sport expert and running coach. You're helping a user who is training for a marathon and pursuing weight loss.

Context:
- Today: {today.strftime('%B %d, %Y')}
- Activity streak: {game_stats.activity_streak or 0} days
- Total sessions: {game_stats.activity_sessions_total or 0}
{plan_context}

Recent workouts (last 2 weeks):
{workout_context}
{garmin_context}
{nutrition_context}

Be encouraging, specific, and evidence-based. Use paces, distances, and heart rate zones. Factor in the Garmin health data (sleep, stress, body battery, resting HR) when recommending training intensity and recovery. Consider the user's nutrition, calorie intake, and weight trend when giving advice on fueling, recovery, and weight loss goals. Keep responses concise and actionable. Reference the marathon countdown when relevant.""",
            messages=messages,
        )

        reply = response.content[0].text

        # Save to session
        chat_history.append({'role': 'user', 'content': user_message})
        chat_history.append({'role': 'assistant', 'content': reply})
        session['coach_chat'] = chat_history[-20:]  # Keep last 20 messages

        return jsonify({
            'success': True,
            'reply': reply,
            'reply_html': markdown.markdown(reply)
        })
    except Exception as e:
        print(f"Coach chat error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/activity/coach/clear', methods=['POST'])
def activity_coach_clear():
    """Clear the activity coach chat history"""
    session.pop('coach_chat', None)
    return jsonify({'success': True})


@app.route('/api/activity/stats')
def activity_stats():
    """Return activity stats as JSON for charts"""
    game_stats = get_or_create_game_stats()
    today = datetime.now().date()

    # Weekly volume (last 8 weeks)
    eight_weeks_ago = today - timedelta(weeks=8)
    workouts = Workout.query.filter(Workout.date >= eight_weeks_ago).all()

    weekly = {}
    for i in range(8):
        ws = today - timedelta(weeks=7-i, days=today.weekday())
        we = ws + timedelta(days=6)
        label = ws.strftime('%b %d')
        km = sum(w.distance_km or 0 for w in workouts if w.workout_type == 'run' and ws <= w.date <= we)
        gym = sum(1 for w in workouts if w.workout_type == 'gym' and ws <= w.date <= we)
        weekly[label] = {'runs_km': round(km, 1), 'gym': gym}

    return jsonify({
        'streak': game_stats.activity_streak or 0,
        'total_sessions': game_stats.activity_sessions_total or 0,
        'total_xp': game_stats.activity_xp_total or 0,
        'weekly': weekly
    })


##############################################
# TRAINING CALENDAR API
##############################################

@app.route('/api/activity/generate-schedule', methods=['POST'])
def activity_generate_schedule():
    """Generate day-by-day TrainingDay records from active plan using Claude"""
    if not claude_client:
        return jsonify({'error': 'Claude API not configured'}), 500

    active_plan = TrainingPlan.query.filter_by(is_active=True).first()
    if not active_plan:
        return jsonify({'error': 'No active training plan'}), 400

    today = datetime.now().date()
    target_date = active_plan.target_date or date(2026, 10, 10)
    total_days = (target_date - today).days + 1

    # Gather recent workout context
    four_weeks_ago = today - timedelta(weeks=4)
    recent_workouts = Workout.query.filter(Workout.date >= four_weeks_ago).order_by(Workout.date).all()
    workout_lines = []
    for w in recent_workouts:
        if w.workout_type == 'run':
            workout_lines.append(f"  {w.date}: Run — {w.distance_km}km in {w.duration_minutes}min ({w.effort}), pace {w.pace_per_km}/km")
        elif w.workout_type == 'gym':
            workout_lines.append(f"  {w.date}: Gym — {w.title}")
        else:
            workout_lines.append(f"  {w.date}: Cross-training — {w.title} ({w.duration_minutes}min)")
    workout_context = '\n'.join(workout_lines) if workout_lines else '  No workouts logged yet.'

    profile = NutritionProfile.query.first()
    body_context = ''
    if profile:
        body_context = f"\nBody stats: {profile.weight_kg}kg, {profile.height_cm}cm, age {profile.age}, {profile.sex}, activity level: {profile.activity_level}"

    phase_info = active_plan.phase_summary or '[]'

    try:
        # Generate schedule in chunks if needed (split at ~100 days to avoid truncation)
        all_days_data = []
        chunk_start = today
        chunk_size = 56

        while chunk_start <= target_date:
            chunk_end = min(chunk_start + timedelta(days=chunk_size - 1), target_date)
            days_in_chunk = (chunk_end - chunk_start).days + 1

            response = call_claude('activity', 'generate_schedule',
                model='claude-sonnet-4-20250514',
                max_tokens=16000,
                system="""You are an expert running coach creating a day-by-day marathon training schedule.
You MUST respond with ONLY a valid JSON array. No prose, no markdown, no explanation, no code fences.""",
                messages=[{
                    'role': 'user',
                    'content': f"""Create a day-by-day training schedule for a marathon.

Plan context:
- Event: {active_plan.target_event or 'Marathon'}
- Race date: {target_date.strftime('%B %d, %Y')}
- Start date: {chunk_start.strftime('%B %d, %Y')}
- End date: {chunk_end.strftime('%B %d, %Y')} ({days_in_chunk} days)
- Goals: {active_plan.goals or 'Complete the marathon'}
- Phases: {phase_info}
{body_context}

Recent training (last 4 weeks):
{workout_context}

Output a JSON array from {chunk_start.strftime('%Y-%m-%d')} to {chunk_end.strftime('%Y-%m-%d')} inclusive. Every single date MUST be included.
Each object must have exactly these keys:
{{
  "date": "YYYY-MM-DD",
  "session_type": "run|gym|cross-training|rest|race",
  "title": "Short title (max 40 chars)",
  "description": "Detailed session. For runs: warm-up, main set with paces in min/km, cool-down. For gym: exercises with sets/reps. For rest: short recovery note.",
  "phase": "base|build|peak|taper",
  "week_number": <integer>,
  "effort_level": "easy|moderate|hard|race|rest",
  "planned_km": <float or null>,
  "is_key_session": <true|false>
}}

Rules:
- Key sessions: long runs (16km+), tempo runs, interval sessions, the race itself
- 1 gym session per week (vary upper/lower/full body)
- 1 rest/recovery day per week on WEDNESDAY
- Long run on TUESDAY
- VERY gradual mileage build-up: increase weekly volume by no more than 10% per week. Long runs should start at 10-12km and only reach 16km after at least 6-8 weeks. No run over 15km in the first 6 weeks from today.
- Peak mileage around weeks 20-24, then taper
- Include specific paces: easy 7:00-7:30/km, tempo 5:45-6:00/km, long run 6:45-7:00/km, intervals 5:15-5:30/km
- Race day ({target_date.strftime('%Y-%m-%d')}): session_type "race", title "MARATHON RACE DAY"
"""
                }]
            )

            raw = response.content[0].text.strip()
            if raw.startswith('```'):
                raw = raw.split('\n', 1)[1].rsplit('```', 1)[0].strip()
            chunk_data = json.loads(raw)
            all_days_data.extend(chunk_data)

            chunk_start = chunk_end + timedelta(days=1)

        # Delete existing schedule for this plan
        TrainingDay.query.filter_by(plan_id=active_plan.id).delete()

        # Bulk insert
        for day_data in all_days_data:
            day = TrainingDay(
                plan_id=active_plan.id,
                date=datetime.strptime(day_data['date'], '%Y-%m-%d').date(),
                session_type=day_data.get('session_type', 'rest'),
                title=day_data.get('title', ''),
                description=day_data.get('description', ''),
                phase=day_data.get('phase', 'base'),
                week_number=day_data.get('week_number', 1),
                effort_level=day_data.get('effort_level', 'easy'),
                planned_km=day_data.get('planned_km'),
                is_key_session=day_data.get('is_key_session', False),
            )
            db.session.add(day)

        db.session.commit()

        return jsonify({'success': True, 'count': len(all_days_data)})
    except json.JSONDecodeError as e:
        print(f"Schedule generation JSON parse error: {e}")
        db.session.rollback()
        return jsonify({'error': f'Failed to parse AI response: {e}'}), 500
    except Exception as e:
        print(f"Schedule generation error: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/activity/export-training-pdf')
def export_training_pdf():
    """Export recent runs and Garmin stats as a PDF for external planning"""
    from fpdf import FPDF
    import unicodedata

    def _ascii(text):
        """Normalize unicode to ASCII-safe string for PDF"""
        if not text:
            return ''
        return unicodedata.normalize('NFKD', str(text)).encode('ascii', 'replace').decode('ascii')

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, 'Training & Fitness Summary', new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(0, 6, f'Exported: {datetime.now().strftime("%B %d, %Y")}', new_x='LMARGIN', new_y='NEXT')
    pdf.ln(4)

    # --- Active plan context ---
    active_plan = TrainingPlan.query.filter_by(is_active=True).first()
    if active_plan:
        pdf.set_font('Helvetica', 'B', 13)
        pdf.cell(0, 8, 'Active Training Plan', new_x='LMARGIN', new_y='NEXT')
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 6, _ascii(f'Event: {active_plan.target_event or "N/A"}  |  Target date: {active_plan.target_date}'), new_x='LMARGIN', new_y='NEXT')
        pdf.cell(0, 6, _ascii(f'Goals: {active_plan.goals or "N/A"}'), new_x='LMARGIN', new_y='NEXT')
        if active_plan.target_date:
            days_left = (active_plan.target_date - date.today()).days
            pdf.cell(0, 6, f'Days to race: {days_left}', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(4)

    # --- Body stats ---
    profile = NutritionProfile.query.first()
    if profile:
        pdf.set_font('Helvetica', 'B', 13)
        pdf.cell(0, 8, 'Body Stats', new_x='LMARGIN', new_y='NEXT')
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 6, f'Weight: {profile.weight_kg}kg  |  Height: {profile.height_cm}cm  |  Age: {profile.age}  |  Sex: {profile.sex}', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(4)

    # --- Recent weight trend ---
    recent_weights = WeightEntry.query.order_by(WeightEntry.date.desc()).limit(14).all()
    if recent_weights:
        pdf.set_font('Helvetica', 'B', 13)
        pdf.cell(0, 8, 'Recent Weight (last 14 entries)', new_x='LMARGIN', new_y='NEXT')
        pdf.set_font('Helvetica', '', 9)
        for w in reversed(recent_weights):
            pdf.cell(0, 5, f'{w.date}: {w.weight_kg}kg', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(4)

    # --- All runs (last 12 weeks) ---
    twelve_weeks_ago = date.today() - timedelta(weeks=12)
    runs = Workout.query.filter(
        Workout.workout_type == 'run',
        Workout.date >= twelve_weeks_ago
    ).order_by(Workout.date).all()

    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(0, 8, f'Runs - Last 12 Weeks ({len(runs)} runs)', new_x='LMARGIN', new_y='NEXT')

    if runs:
        # Summary stats
        total_km = sum(r.distance_km or 0 for r in runs)
        total_min = sum(r.duration_minutes or 0 for r in runs)
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 6, f'Total: {total_km:.1f}km  |  {total_min:.0f} minutes  |  Avg per run: {total_km/len(runs):.1f}km', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(2)

        # Table header
        pdf.set_font('Helvetica', 'B', 9)
        col_widths = [22, 55, 18, 18, 18, 22, 15, 22]
        headers = ['Date', 'Title', 'Dist(km)', 'Time(min)', 'Pace/km', 'Effort', 'Avg HR', 'Source']
        for i, h in enumerate(headers):
            pdf.cell(col_widths[i], 6, h, border=1)
        pdf.ln()

        # Table rows
        pdf.set_font('Helvetica', '', 8)
        for r in runs:
            source = 'Garmin' if r.garmin_activity_id else 'Manual'
            vals = [
                str(r.date),
                _ascii((r.title or '')[:30]),
                f'{r.distance_km:.1f}' if r.distance_km else '-',
                f'{r.duration_minutes:.0f}' if r.duration_minutes else '-',
                _ascii(r.pace_per_km or '-'),
                _ascii(r.effort or '-'),
                str(r.heart_rate_avg) if r.heart_rate_avg else '-',
                source,
            ]
            for i, v in enumerate(vals):
                pdf.cell(col_widths[i], 5, v, border=1)
            pdf.ln()
    else:
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 6, 'No runs logged in the last 12 weeks.', new_x='LMARGIN', new_y='NEXT')
    pdf.ln(4)

    # --- Gym sessions (last 12 weeks) ---
    gym_sessions = Workout.query.filter(
        Workout.workout_type == 'gym',
        Workout.date >= twelve_weeks_ago
    ).order_by(Workout.date).all()

    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(0, 8, f'Gym Sessions - Last 12 Weeks ({len(gym_sessions)} sessions)', new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Helvetica', '', 9)
    for g in gym_sessions:
        muscles = ''
        if g.muscle_groups:
            try:
                muscles = ', '.join(json.loads(g.muscle_groups))
            except Exception:
                muscles = g.muscle_groups
        pdf.cell(0, 5, _ascii(f'{g.date}: {g.title or "Gym"} [{muscles}]'), new_x='LMARGIN', new_y='NEXT')
    pdf.ln(4)

    # --- Garmin daily stats (last 4 weeks) ---
    four_weeks_ago = date.today() - timedelta(weeks=4)
    garmin_days = GarminDailyStats.query.filter(
        GarminDailyStats.date >= four_weeks_ago
    ).order_by(GarminDailyStats.date).all()

    if garmin_days:
        pdf.add_page()
        pdf.set_font('Helvetica', 'B', 13)
        pdf.cell(0, 8, f'Garmin Daily Stats - Last 4 Weeks ({len(garmin_days)} days)', new_x='LMARGIN', new_y='NEXT')

        # Averages
        avg_steps = sum(d.steps or 0 for d in garmin_days) / len(garmin_days)
        avg_rhr = [d.resting_hr for d in garmin_days if d.resting_hr]
        avg_stress = [d.avg_stress for d in garmin_days if d.avg_stress]
        avg_sleep = [d.sleep_seconds for d in garmin_days if d.sleep_seconds]
        avg_bb = [d.body_battery_high for d in garmin_days if d.body_battery_high]

        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 6, f'Avg steps/day: {avg_steps:.0f}', new_x='LMARGIN', new_y='NEXT')
        if avg_rhr:
            pdf.cell(0, 6, f'Avg resting HR: {sum(avg_rhr)/len(avg_rhr):.0f} bpm', new_x='LMARGIN', new_y='NEXT')
        if avg_stress:
            pdf.cell(0, 6, f'Avg stress: {sum(avg_stress)/len(avg_stress):.0f}', new_x='LMARGIN', new_y='NEXT')
        if avg_sleep:
            avg_sleep_hrs = (sum(avg_sleep) / len(avg_sleep)) / 3600
            pdf.cell(0, 6, f'Avg sleep: {avg_sleep_hrs:.1f} hours', new_x='LMARGIN', new_y='NEXT')
        if avg_bb:
            pdf.cell(0, 6, f'Avg body battery peak: {sum(avg_bb)/len(avg_bb):.0f}', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(2)

        # Daily table
        pdf.set_font('Helvetica', 'B', 8)
        gcols = [22, 14, 14, 14, 16, 16, 14, 14, 14, 16, 16]
        gheaders = ['Date', 'Steps', 'RHR', 'Stress', 'Sleep(h)', 'Score', 'BB Hi', 'BB Lo', 'BB Wake', 'Act Min', 'Cal']
        for i, h in enumerate(gheaders):
            pdf.cell(gcols[i], 5, h, border=1)
        pdf.ln()

        pdf.set_font('Helvetica', '', 7)
        for d in garmin_days:
            sleep_h = f'{d.sleep_seconds/3600:.1f}' if d.sleep_seconds else '-'
            vals = [
                str(d.date),
                str(d.steps or '-'),
                str(d.resting_hr or '-'),
                str(d.avg_stress or '-'),
                sleep_h,
                str(d.sleep_score or '-'),
                str(d.body_battery_high or '-'),
                str(d.body_battery_low or '-'),
                str(d.body_battery_at_wake or '-'),
                str(d.active_minutes or '-'),
                str(int(d.calories) if d.calories else '-'),
            ]
            for i, v in enumerate(vals):
                pdf.cell(gcols[i], 4.5, v, border=1)
            pdf.ln()

    # Output
    pdf_bytes = pdf.output()
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={'Content-Disposition': 'attachment; filename=training_summary.pdf'}
    )


@app.route('/api/activity/days/<int:day_id>')
def training_day_detail(day_id):
    """Get full detail for a single training day"""
    day = TrainingDay.query.get_or_404(day_id)
    active_plan = TrainingPlan.query.filter_by(is_active=True).first()
    if not active_plan or day.plan_id != active_plan.id:
        return jsonify({'error': 'Day does not belong to active plan'}), 400
    return jsonify(day.to_dict())


@app.route('/api/activity/days/<int:day_id>/complete', methods=['POST'])
def training_day_complete(day_id):
    """Mark a training day as completed and create a Workout entry"""
    day = TrainingDay.query.get_or_404(day_id)
    active_plan = TrainingPlan.query.filter_by(is_active=True).first()
    if not active_plan or day.plan_id != active_plan.id:
        return jsonify({'error': 'Day does not belong to active plan'}), 400
    if day.status == 'completed':
        return jsonify({'error': 'Already completed'}), 400

    data = request.get_json() or {}
    feedback = data.get('feedback', 'as_expected')  # easy, as_expected, tough, couldnt_finish
    actual_km = data.get('actual_km', day.planned_km)
    actual_duration = data.get('actual_duration_minutes')
    notes = data.get('notes', '')
    followed_plan = data.get('followed_plan', True)

    # Map effort feedback to workout effort
    effort_map = {'easy': 'easy', 'as_expected': 'moderate', 'tough': 'hard', 'couldnt_finish': 'hard'}
    effort = effort_map.get(feedback, 'moderate')

    workout_type = day.session_type if day.session_type != 'race' else 'run'

    # Dedup: check if a Garmin-imported workout already exists for this date+type
    # If so, keep the Garmin data (more detailed) and just mark the day as completed
    existing_garmin = Workout.query.filter(
        Workout.date == day.date,
        Workout.workout_type == workout_type,
        Workout.garmin_activity_id.isnot(None)
    ).first()

    if existing_garmin:
        # Garmin data is richer — just append the plan feedback to its notes
        plan_note = f"{'Followed plan' if followed_plan else 'Modified'} — Felt: {feedback}. {notes}".strip()
        existing_garmin.notes = (existing_garmin.notes or '') + f" | {plan_note}"
        xp = existing_garmin.xp_earned or 0
        workout = existing_garmin
        created_new = False
    else:
        # No Garmin data yet — create a manual Workout entry
        workout = Workout(
            date=day.date,
            workout_type=workout_type,
            title=day.title,
            notes=f"{'Followed plan' if followed_plan else 'Modified'} — Felt: {feedback}. {notes}".strip(),
        )

        if day.session_type in ('run', 'race'):
            workout.distance_km = float(actual_km or 0)
            workout.duration_minutes = round(float(actual_duration or 0), 2) if actual_duration else None
            workout.effort = effort
            if workout.distance_km and workout.duration_minutes:
                pace_total_sec = (workout.duration_minutes * 60) / workout.distance_km
                pace_min = int(pace_total_sec // 60)
                pace_sec = int(pace_total_sec % 60)
                workout.pace_per_km = f"{pace_min}:{pace_sec:02d}"
        elif day.session_type == 'gym':
            workout.duration_minutes = round(float(actual_duration or 45), 2)
        else:
            workout.duration_minutes = round(float(actual_duration or 30), 2)

        # XP calculation (same logic as activity_log_save)
        if day.session_type in ('run', 'race'):
            xp = 15 + int((workout.distance_km or 0) * 2)
            if effort == 'hard':
                xp += 5
            if day.session_type == 'race':
                xp += 10
        elif day.session_type == 'gym':
            xp = 15 + 8  # estimate ~8 sets for a planned gym session
        else:
            xp = 10 + int((workout.duration_minutes or 0) // 10)

        workout.xp_earned = xp
        db.session.add(workout)
        created_new = True

    # Update GameStats only if we created a new workout
    game_stats = get_or_create_game_stats()
    if created_new:
        game_stats.xp += xp
        game_stats.activity_sessions_total = (game_stats.activity_sessions_total or 0) + 1
        game_stats.activity_xp_total = (game_stats.activity_xp_total or 0) + xp

    workout_date = day.date
    if game_stats.last_activity_date:
        days_diff = (workout_date - game_stats.last_activity_date).days
        if days_diff == 1:
            game_stats.activity_streak = (game_stats.activity_streak or 0) + 1
        elif days_diff > 1:
            game_stats.activity_streak = 1
    else:
        game_stats.activity_streak = 1
    if workout_date >= (game_stats.last_activity_date or workout_date):
        game_stats.last_activity_date = workout_date

    # Mark training day as completed
    day.status = 'completed'
    db.session.commit()

    new_achievements = check_achievements(game_stats)
    leveled_up = check_level_up(game_stats)
    db.session.commit()

    return jsonify({
        'success': True,
        'xp_earned': xp,
        'streak': game_stats.activity_streak,
        'achievements': [a['name'] for a in new_achievements],
        'leveled_up': leveled_up,
    })


@app.route('/api/activity/days/<int:day_id>/skip', methods=['POST'])
def training_day_skip(day_id):
    """Mark a training day as skipped"""
    day = TrainingDay.query.get_or_404(day_id)
    active_plan = TrainingPlan.query.filter_by(is_active=True).first()
    if not active_plan or day.plan_id != active_plan.id:
        return jsonify({'error': 'Day does not belong to active plan'}), 400

    day.status = 'skipped'
    db.session.commit()

    return jsonify({
        'success': True,
        'is_key_session': day.is_key_session,
    })


@app.route('/api/activity/days/swap', methods=['POST'])
def training_day_swap():
    """Swap sessions between two training days. Supports swapping with empty (rest) dates."""
    data = request.get_json() or {}
    active_plan = TrainingPlan.query.filter_by(is_active=True).first()
    if not active_plan:
        return jsonify({'error': 'No active plan'}), 400

    # Support both day IDs and date strings for swap targets
    day_a = None
    day_b = None

    if 'day_a' in data:
        day_a = TrainingDay.query.get_or_404(data['day_a'])
    if 'day_b' in data:
        day_b = TrainingDay.query.get_or_404(data['day_b'])

    # If day_b is not provided but a target date is, create a rest day for that date
    if not day_b and 'date_b' in data:
        target_date = date.fromisoformat(data['date_b'])
        # Check if a training day already exists for this date
        day_b = TrainingDay.query.filter_by(plan_id=active_plan.id, date=target_date).first()
        if not day_b:
            # Create a rest day placeholder so we can swap with it
            day_b = TrainingDay(
                plan_id=active_plan.id,
                date=target_date,
                session_type='rest',
                title='Rest Day',
                description='Rest day.',
                effort_level='rest',
                phase=day_a.phase if day_a else 'Base',
                week_number=day_a.week_number if day_a else 1,
            )
            db.session.add(day_b)
            db.session.flush()

    if not day_a or not day_b:
        return jsonify({'error': 'day_a and (day_b or date_b) required'}), 400

    if day_a.plan_id != active_plan.id or day_b.plan_id != active_plan.id:
        return jsonify({'error': 'Days do not belong to active plan'}), 400

    # Swap session content (not dates or status)
    for attr in ['session_type', 'title', 'description', 'effort_level', 'planned_km', 'is_key_session']:
        val_a = getattr(day_a, attr)
        val_b = getattr(day_b, attr)
        setattr(day_a, attr, val_b)
        setattr(day_b, attr, val_a)

    day_a.swap_note = f"Swapped with {day_b.date.isoformat()}"
    day_b.swap_note = f"Swapped with {day_a.date.isoformat()}"

    db.session.commit()

    return jsonify({
        'success': True,
        'day_a': day_a.to_dict(),
        'day_b': day_b.to_dict(),
    })


@app.route('/api/activity/days/<int:day_id>/ripple', methods=['POST'])
def training_day_ripple(day_id):
    """Claude adjusts the 7 days surrounding a skipped key session"""
    if not claude_client:
        return jsonify({'error': 'Claude API not configured'}), 500

    skipped = TrainingDay.query.get_or_404(day_id)
    active_plan = TrainingPlan.query.filter_by(is_active=True).first()
    if not active_plan or skipped.plan_id != active_plan.id:
        return jsonify({'error': 'Day does not belong to active plan'}), 400

    window_start = skipped.date - timedelta(days=3)
    window_end = skipped.date + timedelta(days=3)
    window_days = TrainingDay.query.filter(
        TrainingDay.plan_id == active_plan.id,
        TrainingDay.date >= window_start,
        TrainingDay.date <= window_end,
        TrainingDay.id != day_id,
        TrainingDay.status != 'skipped',
    ).order_by(TrainingDay.date).all()

    context = json.dumps([d.to_dict() for d in window_days])
    skipped_summary = f"{skipped.date}: {skipped.title} ({skipped.planned_km}km, {skipped.effort_level})"

    try:
        response = call_claude('activity', 'ripple_adjust',
            model='claude-sonnet-4-20250514',
            max_tokens=1500,
            system="You are a running coach adjusting a training schedule after a missed session. Respond ONLY with a valid JSON array. No prose.",
            messages=[{'role': 'user', 'content': f"""
A key session was skipped: {skipped_summary}

Nearby sessions (the ones you can adjust):
{context}

Return a JSON array of adjustments. Only include days that need changes.
Each object: {{"id": <day_id>, "title": "<new title>", "description": "<new description>", "planned_km": <float or null>}}
Make modest adjustments — redistribute load gently, do not overload any single day.
If no adjustment is needed for a day, omit it.
"""}]
        )

        raw = response.content[0].text.strip()
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        adjustments = json.loads(raw)

        adjusted_ids = []
        for adj in adjustments:
            d = TrainingDay.query.get(adj['id'])
            if d and d.plan_id == active_plan.id:
                d.original_description = d.original_description or d.description
                d.description = adj.get('description', d.description)
                d.title = adj.get('title', d.title)
                if adj.get('planned_km') is not None:
                    d.planned_km = adj['planned_km']
                d.ripple_adjusted = True
                adjusted_ids.append(d.id)

        db.session.commit()

        # Return updated days for UI refresh
        updated_days = {d.date.isoformat(): d.to_dict() for d in window_days if d.id in adjusted_ids}

        return jsonify({'success': True, 'adjusted_count': len(adjusted_ids), 'updated_days': updated_days})
    except Exception as e:
        print(f"Ripple adjust error: {e}")
        return jsonify({'error': str(e)}), 500


##############################################
# GARMIN CONNECT INTEGRATION
##############################################

_garmin_rate_limited_until = None


def get_garmin_client():
    """Create and authenticate a Garmin Connect client, reusing cached tokens when possible."""
    global _garmin_rate_limited_until
    from garminconnect import Garmin

    # Don't retry if we were recently rate-limited (cooldown: 1 hour)
    if _garmin_rate_limited_until and datetime.utcnow() < _garmin_rate_limited_until:
        remaining = int((_garmin_rate_limited_until - datetime.utcnow()).total_seconds() / 60)
        raise Exception(f"Garmin rate-limited. Try again in ~{remaining} minutes.")

    email = os.getenv('GARMIN_EMAIL')
    password = os.getenv('GARMIN_PASSWORD')
    if not email or not password:
        return None

    tokenstore = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.garmin_tokens')

    client = Garmin(email, password)
    # Override default mobile app user agent to avoid Garmin SSO rate limits
    client.garth.sess.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    })
    try:
        # Try loading cached tokens first (avoids SSO login and rate limits)
        client.login(tokenstore)
    except Exception:
        # Tokens missing or expired — do a fresh login
        try:
            client.login()
        except Exception as e:
            if '429' in str(e):
                _garmin_rate_limited_until = datetime.utcnow() + timedelta(hours=1)
                raise Exception(
                    "Garmin rate-limited (too many login attempts). "
                    "The app will automatically retry in 1 hour. "
                    "Do NOT click sync again before then — it extends the ban."
                )
            raise

    # Save/refresh tokens for next time
    client.garth.dump(tokenstore)
    _garmin_rate_limited_until = None

    return client


def sync_garmin_daily(target_date=None, client=None):
    """Sync daily stats from Garmin Connect for a given date."""
    if client is None:
        client = get_garmin_client()
    if not client:
        return None

    if target_date is None:
        target_date = datetime.now().date()

    date_str = target_date.isoformat()

    # Get daily stats
    stats = client.get_stats(date_str)
    if not stats or not stats.get('calendarDate'):
        return None

    # Get sleep data
    sleep_data = {}
    try:
        sleep = client.get_sleep_data(date_str)
        if sleep and sleep.get('dailySleepDTO'):
            s = sleep['dailySleepDTO']
            sleep_data = {
                'sleep_seconds': s.get('sleepTimeSeconds'),
                'sleep_deep_seconds': s.get('deepSleepSeconds'),
                'sleep_light_seconds': s.get('lightSleepSeconds'),
                'sleep_rem_seconds': s.get('remSleepSeconds'),
                'sleep_awake_seconds': s.get('awakeSleepSeconds'),
                'sleep_score': (s.get('sleepScores') or {}).get('overall', {}).get('value'),
            }
    except Exception:
        pass

    # Upsert
    daily = GarminDailyStats.query.filter_by(date=target_date).first()
    if not daily:
        daily = GarminDailyStats(date=target_date)
        db.session.add(daily)

    # Steps & movement
    daily.steps = stats.get('totalSteps')
    daily.step_goal = stats.get('dailyStepGoal')
    daily.distance_meters = stats.get('totalDistanceMeters')
    daily.floors_climbed = stats.get('floorsAscended')

    # Calories
    daily.calories = stats.get('totalKilocalories')
    daily.active_calories = stats.get('activeKilocalories')
    daily.bmr_calories = stats.get('bmrKilocalories')

    # Active time
    active_sec = stats.get('activeSeconds')
    daily.active_minutes = active_sec // 60 if active_sec else None
    daily.moderate_intensity_min = stats.get('moderateIntensityMinutes')
    daily.vigorous_intensity_min = stats.get('vigorousIntensityMinutes')
    daily.intensity_minutes_goal = stats.get('intensityMinutesGoal')
    daily.sedentary_seconds = stats.get('sedentarySeconds')

    # Heart rate
    daily.resting_hr = stats.get('restingHeartRate')
    daily.min_hr = stats.get('minHeartRate')
    daily.max_hr = stats.get('maxHeartRate')
    daily.avg_resting_hr_7day = stats.get('lastSevenDaysAvgRestingHeartRate')

    # Stress
    daily.avg_stress = stats.get('averageStressLevel')
    daily.max_stress = stats.get('maxStressLevel')
    daily.low_stress_pct = stats.get('lowStressPercentage')
    daily.medium_stress_pct = stats.get('mediumStressPercentage')
    daily.high_stress_pct = stats.get('highStressPercentage')
    daily.rest_stress_pct = stats.get('restStressPercentage')
    daily.stress_qualifier = stats.get('stressQualifier')

    # Body battery
    daily.body_battery_high = stats.get('bodyBatteryHighestValue')
    daily.body_battery_low = stats.get('bodyBatteryLowestValue')
    daily.body_battery_at_wake = stats.get('bodyBatteryAtWakeTime')
    daily.body_battery_charged = stats.get('bodyBatteryChargedValue')
    daily.body_battery_drained = stats.get('bodyBatteryDrainedValue')

    # Respiration
    daily.avg_respiration = stats.get('avgWakingRespirationValue')
    daily.lowest_respiration = stats.get('lowestRespirationValue')
    daily.highest_respiration = stats.get('highestRespirationValue')

    # Sleep
    for k, v in sleep_data.items():
        setattr(daily, k, v)

    daily.synced_at = datetime.utcnow()
    db.session.commit()

    return daily


def sync_garmin_backfill(days=14):
    """Backfill multiple days of Garmin data."""
    client = get_garmin_client()
    if not client:
        return 0

    today = datetime.now().date()
    synced = 0
    for i in range(days):
        target = today - timedelta(days=i)
        # Always re-fetch all days to get complete data
        try:
            result = sync_garmin_daily(target, client=client)
            if result:
                synced += 1
        except Exception:
            continue

    return synced


def import_garmin_activities(days_back=7):
    """Import recent Garmin activities as Workouts, skipping duplicates."""
    client = get_garmin_client()
    if not client:
        return []

    activities = client.get_activities(0, 20)
    cutoff = datetime.now().date() - timedelta(days=days_back)
    imported = []

    for a in activities:
        activity_id = a.get('activityId')
        if not activity_id:
            continue

        # Parse date
        start_str = a.get('startTimeLocal', '')
        try:
            activity_date = datetime.strptime(start_str[:10], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            continue

        if activity_date < cutoff:
            continue

        # Skip if already imported
        if Workout.query.filter_by(garmin_activity_id=activity_id).first():
            continue

        type_key = (a.get('activityType') or {}).get('typeKey', '')
        activity_name = a.get('activityName', '')
        distance = a.get('distance', 0) or 0
        duration_sec = a.get('duration', 0) or 0
        duration_min = round(duration_sec / 60, 1)
        avg_hr = a.get('averageHR')
        calories = a.get('calories')

        # Determine workout type for dedup check
        if type_key in ('running', 'trail_running', 'treadmill_running', 'track_running'):
            mapped_type = 'run'
        elif type_key in ('strength_training', 'indoor_cardio'):
            mapped_type = 'gym'
        else:
            mapped_type = 'cross-training'

        # Dedup: check for a manual entry on the same day with the same type
        # (no garmin_activity_id). Watch data is more detailed, so replace it.
        existing = Workout.query.filter(
            Workout.date == activity_date,
            Workout.workout_type == mapped_type,
            Workout.garmin_activity_id.is_(None)
        ).first()

        if existing:
            # Remember XP from manual entry so we don't double-count
            old_xp = existing.xp_earned or 0
            db.session.delete(existing)
            db.session.flush()
            replacing = True
        else:
            old_xp = 0
            replacing = False

        # Map Garmin types to our workout types
        if mapped_type == 'run':
            distance_km = round(distance / 1000, 2)
            pace_sec = (duration_sec / (distance / 1000)) if distance > 0 else 0
            pace_min = int(pace_sec // 60)
            pace_remaining = int(pace_sec % 60)
            pace_str = f"{pace_min}:{pace_remaining:02d}" if distance > 0 else None

            # Map effort from training effect
            te = a.get('aerobicTrainingEffect', 0) or 0
            if te >= 4.0:
                effort = 'hard'
            elif te >= 3.0:
                effort = 'moderate'
            else:
                effort = 'easy'

            workout = Workout(
                date=activity_date,
                workout_type='run',
                title=activity_name,
                distance_km=distance_km,
                duration_minutes=duration_min,
                pace_per_km=pace_str,
                effort=effort,
                heart_rate_avg=int(avg_hr) if avg_hr else None,
                garmin_activity_id=activity_id,
                notes=f"Imported from Garmin. Calories: {int(calories) if calories else '?'}. Elevation: {a.get('elevationGain', 0)}m.",
            )
        elif mapped_type == 'gym':
            workout = Workout(
                date=activity_date,
                workout_type='gym',
                title=activity_name,
                duration_minutes=duration_min,
                heart_rate_avg=int(avg_hr) if avg_hr else None,
                garmin_activity_id=activity_id,
                notes=f"Imported from Garmin. Calories: {int(calories) if calories else '?'}.",
            )
        else:
            workout = Workout(
                date=activity_date,
                workout_type='cross-training',
                title=activity_name or type_key.replace('_', ' ').title(),
                duration_minutes=duration_min,
                heart_rate_avg=int(avg_hr) if avg_hr else None,
                garmin_activity_id=activity_id,
                notes=f"Imported from Garmin ({type_key}). Calories: {int(calories) if calories else '?'}. Distance: {round(distance/1000, 2)}km.",
            )

        # XP calculation
        if workout.workout_type == 'run':
            xp = 15 + int((workout.distance_km or 0) * 2)
            if effort == 'hard':
                xp += 5
        elif workout.workout_type == 'gym':
            xp = 15
        else:
            xp = 10 + int(duration_min // 10)
        workout.xp_earned = xp

        db.session.add(workout)

        # If we replaced a manual entry, adjust game stats to avoid double-counting XP
        if replacing:
            game_stats = get_or_create_game_stats()
            xp_diff = xp - old_xp
            game_stats.xp = (game_stats.xp or 0) + xp_diff
            game_stats.activity_xp_total = (game_stats.activity_xp_total or 0) + xp_diff
            # Don't increment activity_sessions_total since it's a replacement
        imported.append({
            'name': activity_name,
            'type': workout.workout_type,
            'date': str(activity_date),
            'distance_km': round(distance / 1000, 2),
            'duration_min': duration_min,
            'replaced': replacing,
        })

    if imported:
        # Update game stats — only count truly new entries, not replacements
        new_count = sum(1 for i in imported if not i.get('replaced'))
        game_stats = get_or_create_game_stats()
        if new_count:
            game_stats.activity_sessions_total = (game_stats.activity_sessions_total or 0) + new_count
        game_stats.activity_xp_total = db.session.query(db.func.coalesce(db.func.sum(Workout.xp_earned), 0)).scalar()
        db.session.commit()

    return imported


@app.route('/api/garmin/sync', methods=['POST'])
def garmin_sync():
    """Sync daily stats + import activities from Garmin Connect."""
    if 'authenticated' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json() or {}
    days_back = data.get('days_back', 14)

    try:
        # Backfill daily stats
        synced_days = sync_garmin_backfill(days=days_back)

        # Import activities
        imported = import_garmin_activities(days_back=days_back)

        # Get today's data for response
        today = datetime.now().date()
        daily = GarminDailyStats.query.filter_by(date=today).first()
        daily_data = None
        if daily:
            daily_data = {
                'steps': daily.steps,
                'calories': daily.calories,
                'active_minutes': daily.active_minutes,
                'resting_hr': daily.resting_hr,
                'body_battery_high': daily.body_battery_high,
                'body_battery_low': daily.body_battery_low,
                'avg_stress': daily.avg_stress,
                'sleep_score': daily.sleep_score,
                'sleep_hours': round(daily.sleep_seconds / 3600, 1) if daily.sleep_seconds else None,
            }

        return jsonify({
            'success': True,
            'daily': daily_data,
            'imported': imported,
            'imported_count': len(imported),
            'synced_days': synced_days,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/activity/garmin')
def garmin_dashboard():
    """Garmin Connect day-by-day dashboard."""
    if 'authenticated' not in session:
        return redirect(url_for('login'))

    today = datetime.now().date()
    days_back = request.args.get('days', 14, type=int)
    cutoff = today - timedelta(days=days_back)

    stats = GarminDailyStats.query.filter(
        GarminDailyStats.date >= cutoff,
        GarminDailyStats.steps > 0,
    ).order_by(GarminDailyStats.date.desc()).all()

    # Prepare chart data
    chart_data = []
    for s in reversed(stats):
        chart_data.append({
            'date': s.date.strftime('%b %d'),
            'date_full': str(s.date),
            'steps': s.steps or 0,
            'step_goal': s.step_goal or 0,
            'calories': int(s.calories or 0),
            'active_calories': int(s.active_calories or 0),
            'resting_hr': s.resting_hr,
            'avg_resting_hr_7day': s.avg_resting_hr_7day,
            'body_battery_high': s.body_battery_high,
            'body_battery_low': s.body_battery_low,
            'body_battery_at_wake': s.body_battery_at_wake,
            'avg_stress': s.avg_stress,
            'stress_qualifier': s.stress_qualifier,
            'sleep_hours': round(s.sleep_seconds / 3600, 1) if s.sleep_seconds else None,
            'sleep_deep_min': s.sleep_deep_seconds // 60 if s.sleep_deep_seconds else None,
            'sleep_light_min': s.sleep_light_seconds // 60 if s.sleep_light_seconds else None,
            'sleep_rem_min': s.sleep_rem_seconds // 60 if s.sleep_rem_seconds else None,
            'sleep_score': s.sleep_score,
            'active_minutes': s.active_minutes or 0,
            'moderate_intensity_min': s.moderate_intensity_min or 0,
            'vigorous_intensity_min': s.vigorous_intensity_min or 0,
            'floors_climbed': round(s.floors_climbed, 1) if s.floors_climbed else 0,
            'distance_km': round(s.distance_meters / 1000, 1) if s.distance_meters else 0,
        })

    garmin_available = bool(os.getenv('GARMIN_EMAIL') and os.getenv('GARMIN_PASSWORD'))

    return render_template('garmin_dashboard.html',
                         stats=stats,
                         chart_data=json.dumps(chart_data),
                         days_back=days_back,
                         garmin_available=garmin_available)


##############################################
# PERSONAL COACH ROUTES
##############################################

COACH_AREAS = [
    {"id": "journal", "label": "Journal", "icon": "writing", "color": "#E8D5B7", "accent": "#8B6914"},
    {"id": "exercise", "label": "Exercise", "icon": "muscle", "color": "#B7D5C8", "accent": "#1A6B47"},
    {"id": "weight", "label": "Weight", "icon": "scale", "color": "#D5B7E8", "accent": "#6B1A8B"},
    {"id": "meals", "label": "Meals", "icon": "seedling", "color": "#B7E8C8", "accent": "#1A8B47"},
    {"id": "daily", "label": "Daily Life", "icon": "sun", "color": "#E8E8B7", "accent": "#8B8B1A"},
    {"id": "relationships", "label": "Relationships", "icon": "heart", "color": "#E8B7B7", "accent": "#8B1A1A"},
    {"id": "growth", "label": "Growth", "icon": "seedling", "color": "#B7D5E8", "accent": "#1A478B"},
]


def build_coach_context(area_id=None):
    """Build a rich context summary of the user's recent activity across all tracked areas."""
    today = datetime.now().date()
    seven_days_ago = today - timedelta(days=7)
    thirty_days_ago = today - timedelta(days=30)
    fourteen_days_ago = today - timedelta(days=14)
    game_stats = get_or_create_game_stats()
    lines = []

    # Journal
    journal_count_7d = JournalEntry.query.filter(JournalEntry.date >= seven_days_ago).count()
    last_journal = JournalEntry.query.order_by(JournalEntry.date.desc()).first()
    last_journal_str = f"Last entry: {(today - last_journal.date).days} day(s) ago" if last_journal else "No entries yet"
    lines.append(f"- Journaling: {journal_count_7d}/7 days this week. Streak: {game_stats.current_streak or 0} days. {last_journal_str}")

    # Meditation
    med_count_7d = MeditationSession.query.filter(MeditationSession.date >= seven_days_ago, MeditationSession.completed == True).count()
    med_minutes_7d = db.session.query(db.func.sum(MeditationSession.duration_seconds)).filter(
        MeditationSession.date >= seven_days_ago, MeditationSession.completed == True
    ).scalar() or 0
    lines.append(f"- Meditation: {med_count_7d} sessions this week ({int(med_minutes_7d / 60)} min total). Streak: {game_stats.meditation_streak or 0} days.")

    # Exercise / Activity
    workouts_7d = Workout.query.filter(Workout.date >= seven_days_ago).all()
    runs = [w for w in workouts_7d if w.workout_type == 'run']
    gyms = [w for w in workouts_7d if w.workout_type == 'gym']
    total_km = sum(w.distance_km or 0 for w in runs)
    lines.append(f"- Exercise: {len(workouts_7d)} sessions this week ({len(runs)} runs / {round(total_km, 1)}km, {len(gyms)} gym). Streak: {game_stats.activity_streak or 0} days.")

    # Training plan schedule
    active_plan = TrainingPlan.query.filter_by(is_active=True).first()
    if active_plan:
        days_until = (active_plan.target_date - today).days if active_plan.target_date else '?'
        lines.append(f"- Training plan: {active_plan.target_event} on {active_plan.target_date} ({days_until} days away). Goals: {active_plan.goals}")
        if active_plan.phase_summary:
            try:
                phases = json.loads(active_plan.phase_summary)
                weeks_since_start = (today - active_plan.created_at.date()).days // 7 + 1
                for p in phases:
                    if p.get('start_week', 0) <= weeks_since_start <= p.get('end_week', 999):
                        lines.append(f"  Current phase: {p.get('phase')} (week {weeks_since_start}) — {p.get('focus', '')}")
                        break
            except (json.JSONDecodeError, TypeError):
                pass
        week_start = today - timedelta(days=today.weekday())
        three_weeks_end = week_start + timedelta(days=20)
        upcoming_days = TrainingDay.query.filter(
            TrainingDay.plan_id == active_plan.id,
            TrainingDay.date >= week_start,
            TrainingDay.date <= three_weeks_end,
        ).order_by(TrainingDay.date).all()
        if upcoming_days:
            lines.append(f"  Upcoming schedule ({week_start.strftime('%b %d')} – {three_weeks_end.strftime('%b %d')}):")
            current_week_label = None
            for d in upcoming_days:
                d_week_start = d.date - timedelta(days=d.date.weekday())
                week_label = d_week_start.strftime('%b %d')
                if week_label != current_week_label:
                    current_week_label = week_label
                    lines.append(f"    Week of {week_label}:")
                status_icon = '✅' if d.status == 'completed' else '⏭️' if d.status == 'skipped' else '📋'
                km_str = f" {d.planned_km}km" if d.planned_km else ""
                lines.append(f"      {status_icon} {d.date.strftime('%a %b %d')}: {d.session_type} — {d.title or ''}{km_str} [{d.effort_level or '?'}]")
                if d.description:
                    lines.append(f"        {d.description[:150]}")
        today_session = TrainingDay.query.filter_by(plan_id=active_plan.id, date=today).first()
        if today_session and today_session.status == 'planned':
            lines.append(f"  📌 Today's session: {today_session.session_type} — {today_session.title or ''}")
            if today_session.description:
                lines.append(f"     {today_session.description[:200]}")

    # Nutrition & Weight
    nutrition_count_7d = NutritionEntry.query.filter(NutritionEntry.date >= seven_days_ago).count()
    nutrition_profile = NutritionProfile.query.first()
    weight_str = f"Current weight: {nutrition_profile.weight_kg}kg" if nutrition_profile and nutrition_profile.weight_kg else "No weight data"
    lines.append(f"- Nutrition: {nutrition_count_7d} meals logged this week. Streak: {game_stats.nutrition_streak or 0} days. {weight_str}")
    if nutrition_profile:
        if nutrition_profile.target_weight_kg:
            lines.append(f"  Target weight: {nutrition_profile.target_weight_kg}kg (delta: {round((nutrition_profile.weight_kg or 0) - nutrition_profile.target_weight_kg, 1)}kg)")
        if nutrition_profile.calorie_target:
            lines.append(f"  Daily calorie target: {nutrition_profile.calorie_target} kcal (P:{nutrition_profile.protein_target_pct}% C:{nutrition_profile.carbs_target_pct}% F:{nutrition_profile.fat_target_pct}%)")
        # Weekly nutrition averages
        week_entries = NutritionEntry.query.filter(NutritionEntry.date >= seven_days_ago).all()
        if week_entries:
            days_with_data = len(set(e.date for e in week_entries))
            total_cal = sum(e.calories or 0 for e in week_entries)
            total_protein = sum(e.protein_grams or 0 for e in week_entries)
            avg_cal = round(total_cal / days_with_data) if days_with_data else 0
            avg_protein = round(total_protein / days_with_data) if days_with_data else 0
            lines.append(f"  Last 7 days avg: {avg_cal} kcal/day, {avg_protein}g protein/day ({days_with_data} days tracked)")
        # Detailed meal logs (what was actually eaten)
        if week_entries:
            lines.append("\n  Detailed meal log (last 7 days):")
            entries_by_date = {}
            for e in sorted(week_entries, key=lambda x: (x.date, x.meal_type or '')):
                date_str = e.date.strftime('%b %d (%a)')
                if date_str not in entries_by_date:
                    entries_by_date[date_str] = []
                entries_by_date[date_str].append(e)
            for date_str, entries in entries_by_date.items():
                lines.append(f"    {date_str}:")
                for e in entries:
                    meal_label = e.meal_type.capitalize() if e.meal_type else "Meal"
                    desc = e.description or "no description"
                    macros = f"{e.calories or '?'}cal"
                    if e.protein_grams:
                        macros += f", {e.protein_grams}g P"
                    if e.carbs_grams:
                        macros += f", {e.carbs_grams}g C"
                    if e.fat_grams:
                        macros += f", {e.fat_grams}g F"
                    lines.append(f"      {meal_label}: {desc} ({macros})")
    # Weight trend
    recent_weights = WeightEntry.query.filter(
        WeightEntry.date >= thirty_days_ago
    ).order_by(WeightEntry.date.desc()).limit(10).all()
    if recent_weights:
        lines.append(f"  Weight trend (last 30d): " + ", ".join(f"{w.date.strftime('%b %d')}: {w.weight_kg}kg" for w in recent_weights))

    # Learning
    learning_count_7d = LearningSession.query.filter(LearningSession.date >= seven_days_ago, LearningSession.completed == True).count()
    lines.append(f"- Learning: {learning_count_7d} sessions this week. Streak: {game_stats.learning_streak or 0} days.")

    # Overall gamification
    lines.append(f"- Overall: Level {game_stats.level} ({game_stats.level_name}), {game_stats.xp} XP total.")

    # Enhanced: Recent journal excerpts (last 3 entries, brief)
    recent_journals = JournalEntry.query.filter(JournalEntry.date >= seven_days_ago).order_by(JournalEntry.date.desc()).limit(3).all()
    if recent_journals:
        lines.append("\nRecent journal highlights:")
        for j in recent_journals:
            mood_str = f" [{j.mood}]" if j.mood else ""
            snippet = j.content[:200].replace('\n', ' ') if j.content else ""
            lines.append(f"  - {j.date.strftime('%b %d')}{mood_str}: \"{snippet}...\"")

    # Enhanced: Weight trend (last 30 days)
    weight_entries = NutritionEntry.query.filter(
        NutritionEntry.date >= thirty_days_ago
    ).order_by(NutritionEntry.date).all()
    if nutrition_profile and nutrition_profile.weight_kg:
        lines.append(f"\nWeight: Current {nutrition_profile.weight_kg}kg" +
                     (f", goal {nutrition_profile.target_weight_kg}kg" if nutrition_profile.target_weight_kg else ""))

    # Enhanced: Workout details (last 5 workouts)
    recent_workouts = Workout.query.order_by(Workout.date.desc()).limit(5).all()
    if recent_workouts:
        lines.append("\nRecent workouts:")
        for w in recent_workouts:
            detail = f"  - {w.date.strftime('%b %d')}: {w.workout_type}"
            if w.workout_type == 'run' and w.distance_km:
                detail += f" {w.distance_km}km"
                if w.pace_per_km:
                    detail += f" @ {w.pace_per_km}/km"
                if w.effort:
                    detail += f" [{w.effort}]"
                if w.heart_rate_avg:
                    detail += f" HR:{w.heart_rate_avg}"
            elif w.workout_type == 'gym' and w.exercises:
                try:
                    exercises = json.loads(w.exercises) if isinstance(w.exercises, str) else w.exercises
                    if exercises:
                        ex_parts = []
                        for ex in exercises:
                            name = ex.get('name', 'Unknown')
                            sets = ex.get('sets', [])
                            if isinstance(sets, list):
                                # New per-set format
                                set_strs = []
                                for s in sets:
                                    w_kg = s.get('weight_kg', 0)
                                    reps = s.get('reps', 0)
                                    failed = ' FAIL' if s.get('failed') else ''
                                    set_strs.append(f"{w_kg}kg×{reps}{failed}")
                                ex_str = f"{name}: {', '.join(set_strs)}"
                            else:
                                # Old flat format
                                reps = ex.get('reps', '')
                                weight = ex.get('weight_kg', '') or ex.get('weight', '')
                                ex_str = name
                                if sets and reps:
                                    ex_str += f" {sets}x{reps}"
                                if weight:
                                    ex_str += f" @{weight}kg"
                            ex_parts.append(ex_str)
                        detail += f" — {', '.join(ex_parts)}"
                except (json.JSONDecodeError, TypeError):
                    pass
                if w.muscle_groups:
                    try:
                        groups = json.loads(w.muscle_groups) if isinstance(w.muscle_groups, str) else w.muscle_groups
                        if groups:
                            detail += f" [muscles: {', '.join(groups)}]"
                    except (json.JSONDecodeError, TypeError):
                        pass
            if w.duration_minutes:
                detail += f" ({w.duration_minutes}min)"
            if w.title:
                detail += f" — {w.title}"
            if w.notes:
                detail += f" Note: {w.notes[:100]}"
            lines.append(detail)

    # Enhanced: Garmin health data (last 7 days)
    garmin_stats = GarminDailyStats.query.filter(
        GarminDailyStats.date >= seven_days_ago,
        GarminDailyStats.steps > 0,
    ).order_by(GarminDailyStats.date.desc()).all()
    if garmin_stats:
        lines.append("\nGarmin health data (last 7 days):")
        for g in garmin_stats:
            sleep_str = f"{g.sleep_seconds // 3600}h{(g.sleep_seconds % 3600) // 60}m" if g.sleep_seconds else "—"
            lines.append(
                f"  - {g.date.strftime('%b %d')}: Steps {g.steps or 0}, RHR {g.resting_hr or '—'}bpm, "
                f"Battery {g.body_battery_high or '—'}/{g.body_battery_low or '—'}, "
                f"Stress {g.avg_stress or '—'} ({g.stress_qualifier or ''}), "
                f"Sleep {sleep_str}" + (f" (score: {g.sleep_score})" if g.sleep_score else "")
            )

    # Enhanced: Active goals
    active_goals = CoachGoal.query.filter_by(status='active').order_by(CoachGoal.created_at.desc()).all()
    if active_goals:
        lines.append("\nActive goals:")
        for g in active_goals:
            target_str = f" (target: {g.target_date.strftime('%b %d')})" if g.target_date else ""
            lines.append(f"  - [{g.area}] {g.title}{target_str}")

    # Enhanced: Mood trend from coaching sessions
    recent_moods = CoachMood.query.filter(CoachMood.created_at >= seven_days_ago).order_by(CoachMood.created_at.desc()).limit(10).all()
    if recent_moods:
        avg_mood = sum(m.score for m in recent_moods) / len(recent_moods)
        mood_label = "positive" if avg_mood > 0.3 else "negative" if avg_mood < -0.3 else "mixed/neutral"
        lines.append(f"\nRecent coaching mood trend: {mood_label} (avg score: {avg_mood:.2f})")

    # Enhanced: Cross-area summaries
    if area_id:
        summaries = CoachSummary.query.filter_by(area=area_id).order_by(CoachSummary.created_at.desc()).limit(1).all()
        if summaries:
            lines.append(f"\nPrevious {area_id} conversation summary: {summaries[0].summary_text[:300]}")

    return "Recent activity summary (last 7 days):\n" + "\n".join(lines)


def get_coach_system_prompt(area_id):
    """Build the dynamic system prompt for the personal coach with persona customization."""
    area = next((a for a in COACH_AREAS if a["id"] == area_id), COACH_AREAS[0])
    today = datetime.now().date()
    context = build_coach_context(area_id)

    # Load persona preference
    persona_pref = CoachPreference.query.filter_by(key='persona_style').first()
    persona = persona_pref.value if persona_pref else 'balanced'

    persona_styles = {
        'balanced': "Warm but honest — you celebrate wins AND gently call out patterns.",
        'motivational': "High-energy and encouraging — you pump him up, celebrate every small win, and push him to believe in himself.",
        'analytical': "Data-driven and precise — you focus on numbers, trends, and evidence-based advice. Less emotion, more analysis.",
        'tough': "Direct and no-nonsense — you challenge excuses, push harder, and hold him accountable with tough love.",
        'empathetic': "Deeply compassionate and understanding — you prioritize emotional support, validate feelings first, then gently guide."
    }
    style_desc = persona_styles.get(persona, persona_styles['balanced'])

    return f"""You are Noé's personal life coach — deeply invested in his growth.

Your coaching style: {style_desc}

Core behaviors:
- Ask powerful questions that spark reflection
- Remember context from past messages in this conversation
- When he shares data (weight, workouts, meals), acknowledge it and draw insights
- Suggest concrete next actions, not vague advice
- Connect dots between different life areas (e.g., sleep affecting workouts, stress affecting eating)
- Use his name "Noé" naturally
- Reference his active goals when relevant
- Notice mood patterns and address them proactively

Current date: {today.strftime('%A, %B %d, %Y')}
Current area focus: {area['label']}

{context}

Keep responses concise but meaningful — no walls of text. Use line breaks for readability. Be conversational."""


def maybe_summarize_area(area_id, threshold=25, keep_recent=10):
    """Auto-summarize old messages when conversation gets long.
    Keeps the most recent `keep_recent` messages and summarizes the rest.
    """
    if not claude_client:
        return

    msg_count = CoachConversation.query.filter_by(area=area_id).count()
    if msg_count <= threshold:
        return

    # Get all messages for this area, oldest first
    all_msgs = CoachConversation.query.filter_by(area=area_id).order_by(
        CoachConversation.created_at
    ).all()

    # Split: older messages to summarize, recent to keep
    to_summarize = all_msgs[:-keep_recent]
    if len(to_summarize) < 5:
        return  # Not enough old messages to bother

    # Build text for summarization
    text_parts = []
    for m in to_summarize:
        prefix = "User" if m.role == 'user' else "Coach"
        text_parts.append(f"{prefix}: {m.content[:200]}")
    convo_text = "\n".join(text_parts)

    try:
        response = call_claude('coach', f'summarize_{area_id}',
            model='claude-sonnet-4-20250514',
            max_tokens=400,
            system="You are a summarization assistant. Summarize the coaching conversation below into a concise paragraph capturing: key topics discussed, goals mentioned, progress made, mood/tone, and any commitments. Keep it under 200 words.",
            messages=[{'role': 'user', 'content': f"Summarize this coaching conversation:\n\n{convo_text}"}]
        )
        summary_text = response.content[0].text

        # Save the summary
        db.session.add(CoachSummary(
            area=area_id,
            summary_text=summary_text,
            message_count=len(to_summarize),
            period_start=to_summarize[0].created_at,
            period_end=to_summarize[-1].created_at
        ))

        # Delete the old messages
        for m in to_summarize:
            db.session.delete(m)

        db.session.commit()
        print(f"Summarized {len(to_summarize)} messages in {area_id}, kept {keep_recent} recent")
    except Exception as e:
        db.session.rollback()
        print(f"Auto-summarize error for {area_id}: {e}")


@app.route('/coach')
def coach():
    """Personal AI Coach page"""
    # Count messages per area for sidebar badges
    area_counts = {}
    for a in COACH_AREAS:
        area_counts[a['id']] = CoachConversation.query.filter_by(area=a['id'], role='user').count()
    total_messages = sum(area_counts.values())
    active_areas = sum(1 for c in area_counts.values() if c > 0)

    return render_template('coach.html',
                         areas=COACH_AREAS,
                         area_counts=area_counts,
                         total_messages=total_messages,
                         active_areas=active_areas)


@app.route('/api/coach/history/<area>')
def coach_history(area):
    """Get conversation history for a coach area"""
    valid_areas = [a['id'] for a in COACH_AREAS]
    if area not in valid_areas:
        return jsonify({'error': 'Invalid area'}), 400

    messages = CoachConversation.query.filter_by(area=area).order_by(CoachConversation.created_at).all()
    return jsonify({
        'messages': [{'role': m.role, 'content': m.content} for m in messages]
    })


@app.route('/api/coach/message', methods=['POST'])
def coach_message():
    """Send a message to the personal coach and get a response"""
    if not claude_client:
        return jsonify({'error': 'Claude API not configured'}), 500

    data = request.get_json(silent=True) or {}
    area = data.get('area', 'journal')
    user_message = data.get('message', '')

    valid_areas = [a['id'] for a in COACH_AREAS]
    if area not in valid_areas:
        return jsonify({'error': 'Invalid area'}), 400
    if not user_message.strip():
        return jsonify({'error': 'Empty message'}), 400

    # Load recent conversation history for context (before adding new message)
    recent = CoachConversation.query.filter_by(area=area).order_by(
        CoachConversation.created_at
    ).limit(20).all()

    # Prepend summary context if available (so Claude has memory of older conversations)
    api_messages = []
    summaries = CoachSummary.query.filter_by(area=area).order_by(CoachSummary.created_at.desc()).limit(2).all()
    if summaries:
        summary_ctx = "\n".join([s.summary_text for s in reversed(summaries)])
        api_messages.append({'role': 'user', 'content': f"[Previous conversation summary for context]\n{summary_ctx}"})
        api_messages.append({'role': 'assistant', 'content': "I remember our previous conversations. Let's continue."})

    api_messages += [{'role': m.role, 'content': m.content} for m in recent]
    api_messages.append({'role': 'user', 'content': user_message.strip()})

    try:
        response = call_claude('coach', area, model='claude-sonnet-4-20250514', max_tokens=1000, system=get_coach_system_prompt(area), messages=api_messages)
        reply = response.content[0].text

        # Save both user message and assistant reply atomically
        db.session.add(CoachConversation(area=area, role='user', content=user_message.strip()))
        db.session.add(CoachConversation(area=area, role='assistant', content=reply))
        db.session.commit()

        # Auto-summarize if conversation is getting long
        maybe_summarize_area(area)

        return jsonify({'reply': reply, 'reply_html': markdown.markdown(reply)})
    except Exception as e:
        db.session.rollback()
        print(f"Coach message error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/coach/history/<area>', methods=['DELETE'])
def coach_clear(area):
    """Clear conversation history for a coach area"""
    valid_areas = [a['id'] for a in COACH_AREAS]
    if area not in valid_areas:
        return jsonify({'error': 'Invalid area'}), 400

    CoachConversation.query.filter_by(area=area).delete()
    db.session.commit()
    return jsonify({'success': True})


# ---- Coach Goals CRUD ----

@app.route('/api/coach/goals', methods=['GET'])
def coach_goals_list():
    """List all coaching goals, optionally filtered by area"""
    area = request.args.get('area')
    q = CoachGoal.query
    if area:
        valid_areas = [a['id'] for a in COACH_AREAS]
        if area not in valid_areas:
            return jsonify({'error': 'Invalid area'}), 400
        q = q.filter_by(area=area)
    goals = q.order_by(CoachGoal.created_at.desc()).all()
    return jsonify({'goals': [{
        'id': g.id,
        'area': g.area,
        'title': g.title,
        'description': g.description,
        'target_date': g.target_date.strftime('%Y-%m-%d') if g.target_date else None,
        'status': g.status,
        'progress_notes': json.loads(g.progress_notes) if g.progress_notes else [],
        'created_at': g.created_at.strftime('%Y-%m-%d'),
        'updated_at': g.updated_at.strftime('%Y-%m-%d') if g.updated_at else None,
    } for g in goals]})


@app.route('/api/coach/goals', methods=['POST'])
def coach_goals_create():
    """Create a new coaching goal"""
    data = request.get_json(silent=True) or {}
    title = data.get('title', '').strip()
    area = data.get('area', 'daily')
    if not title:
        return jsonify({'error': 'Title is required'}), 400

    valid_areas = [a['id'] for a in COACH_AREAS]
    if area not in valid_areas:
        return jsonify({'error': 'Invalid area'}), 400

    target_date = None
    if data.get('target_date'):
        try:
            target_date = datetime.strptime(data['target_date'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid target_date format. Use YYYY-MM-DD.'}), 400

    goal = CoachGoal(
        area=area,
        title=title,
        description=data.get('description', '').strip() or None,
        target_date=target_date,
        status='active'
    )
    db.session.add(goal)
    db.session.commit()
    return jsonify({'success': True, 'id': goal.id}), 201


@app.route('/api/coach/goals/<int:goal_id>', methods=['PUT'])
def coach_goals_update(goal_id):
    """Update a coaching goal (status, progress, details)"""
    goal = CoachGoal.query.get_or_404(goal_id)
    data = request.get_json(silent=True) or {}

    if 'title' in data:
        goal.title = data['title'].strip()
    if 'description' in data:
        goal.description = data['description'].strip() or None
    if 'status' in data:
        if data['status'] not in ('active', 'completed', 'abandoned'):
            return jsonify({'error': "Invalid status. Must be 'active', 'completed', or 'abandoned'."}), 400
        goal.status = data['status']
    if 'target_date' in data:
        if data['target_date']:
            try:
                goal.target_date = datetime.strptime(data['target_date'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Invalid target_date format. Use YYYY-MM-DD.'}), 400
        else:
            goal.target_date = None
    if 'progress_note' in data:
        # Append a new progress note
        notes = json.loads(goal.progress_notes) if goal.progress_notes else []
        notes.append({
            'text': data['progress_note'].strip(),
            'date': datetime.utcnow().strftime('%Y-%m-%d')
        })
        goal.progress_notes = json.dumps(notes)

    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/coach/goals/<int:goal_id>', methods=['DELETE'])
def coach_goals_delete(goal_id):
    """Delete a coaching goal"""
    goal = CoachGoal.query.get_or_404(goal_id)
    db.session.delete(goal)
    db.session.commit()
    return jsonify({'success': True})


# ---- Coach Export ----

@app.route('/api/coach/export/<area>')
def coach_export(area):
    """Export coaching conversation as markdown"""
    valid_areas = [a['id'] for a in COACH_AREAS]
    if area not in valid_areas:
        return jsonify({'error': 'Invalid area'}), 400

    area_label = next((a['label'] for a in COACH_AREAS if a['id'] == area), area)
    messages = CoachConversation.query.filter_by(area=area).order_by(
        CoachConversation.created_at
    ).all()

    # Build markdown
    lines = [f"# Coaching Journal — {area_label}", ""]
    if not messages:
        lines.append("_No conversations yet._")
    else:
        current_date = None
        for m in messages:
            msg_date = m.created_at.strftime('%B %d, %Y')
            if msg_date != current_date:
                current_date = msg_date
                lines.append(f"\n## {msg_date}\n")
            prefix = "**You:**" if m.role == 'user' else "**Coach:**"
            lines.append(f"{prefix} {m.content}\n")

    # Include goals for this area
    goals = CoachGoal.query.filter_by(area=area).order_by(CoachGoal.created_at).all()
    if goals:
        lines.append("\n---\n## Goals\n")
        for g in goals:
            status_mark = '✓' if g.status == 'completed' else '○' if g.status == 'active' else '✗'
            lines.append(f"- [{status_mark}] **{g.title}**" +
                        (f" — {g.description}" if g.description else "") +
                        (f" (target: {g.target_date.strftime('%b %d, %Y')})" if g.target_date else ""))
            if g.progress_notes:
                for note in json.loads(g.progress_notes):
                    lines.append(f"  - {note['date']}: {note['text']}")

    md_content = "\n".join(lines)
    return jsonify({'markdown': md_content, 'area': area, 'area_label': area_label})


# ---- Coach Preferences ----

@app.route('/api/coach/preferences', methods=['GET'])
def coach_preferences_get():
    """Get all coaching preferences"""
    prefs = CoachPreference.query.all()
    # Reverse map stored keys to frontend-friendly keys
    reverse_map = {'persona_style': 'persona', 'focus_areas': 'focus_areas', 'name': 'name'}
    result = {}
    for p in prefs:
        friendly_key = reverse_map.get(p.key, p.key)
        result[friendly_key] = p.value
    return jsonify({'preferences': result})


@app.route('/api/coach/preferences', methods=['PUT'])
def coach_preferences_set():
    """Update coaching preferences"""
    data = request.get_json(silent=True) or {}
    # Map frontend keys to stored keys
    key_map = {'persona': 'persona_style', 'focus_areas': 'focus_areas', 'name': 'name'}
    allowed_keys = set(key_map.keys())

    for key, value in data.items():
        if key not in allowed_keys:
            continue
        store_key = key_map[key]
        pref = CoachPreference.query.filter_by(key=store_key).first()
        if pref:
            pref.value = str(value)
        else:
            db.session.add(CoachPreference(key=store_key, value=str(value)))

    db.session.commit()
    return jsonify({'success': True})


##############################################
# NEWSLETTER ROUTES
##############################################

@app.route('/newsletter')
def newsletter():
    """Newsletter idea board"""
    game_stats = get_or_create_game_stats()
    backlog_ideas = NewsletterIdea.query.filter(
        NewsletterIdea.status != 'archived'
    ).order_by(NewsletterIdea.created_at.desc()).all()
    total_ideas = NewsletterIdea.query.filter(NewsletterIdea.status != 'archived').count()

    issues = NewsletterIssue.query.order_by(NewsletterIssue.created_at.desc()).all()

    subscribers = NewsletterSubscriber.query.filter_by(active=True).order_by(NewsletterSubscriber.name).all()
    subs_en = [s for s in subscribers if s.language == 'en']
    subs_fr = [s for s in subscribers if s.language == 'fr']

    survey_count = SurveyResponse.query.filter_by(survey_name='arc-2').count()

    return render_template('newsletter.html',
                         game_stats=game_stats,
                         backlog_ideas=backlog_ideas,
                         total_ideas=total_ideas,
                         issues=issues,
                         subscribers=subscribers,
                         subs_en=subs_en,
                         subs_fr=subs_fr,
                         survey_count=survey_count)


@app.route('/api/newsletter/idea', methods=['POST'])
def newsletter_add_idea():
    """Add a new newsletter idea"""
    data = request.get_json()
    title = data.get('title', '').strip()
    if not title:
        return jsonify({'error': 'Title is required'}), 400

    idea = NewsletterIdea(
        title=title,
        notes=data.get('notes', '').strip(),
        category=data.get('category', 'misc'),
        status='backlog'
    )
    db.session.add(idea)

    game_stats = get_or_create_game_stats()
    game_stats.newsletter_ideas_total = (game_stats.newsletter_ideas_total or 0) + 1
    xp = 3
    game_stats.xp += xp

    db.session.commit()

    new_achievements = check_achievements(game_stats)
    leveled_up = check_level_up(game_stats)
    db.session.commit()

    return jsonify({
        'success': True,
        'idea': {
            'id': idea.id,
            'title': idea.title,
            'notes': idea.notes,
            'category': idea.category,
            'status': idea.status,
            'created_at': idea.created_at.strftime('%b %d')
        },
        'xp_earned': xp,
        'achievements': [a['name'] for a in new_achievements]
    })


@app.route('/api/newsletter/idea/<int:idea_id>', methods=['PUT'])
def newsletter_update_idea(idea_id):
    """Update an idea (edit, assign to issue, change status)"""
    idea = NewsletterIdea.query.get_or_404(idea_id)
    data = request.get_json()

    if 'title' in data:
        idea.title = data['title'].strip()
    if 'notes' in data:
        idea.notes = data['notes'].strip()
    if 'category' in data:
        idea.category = data['category']
    if 'status' in data:
        idea.status = data['status']
    if 'issue_id' in data:
        issue_id = data['issue_id']
        idea.issue_id = int(issue_id) if issue_id else None
        idea.status = 'planned' if issue_id else 'backlog'
    if 'sort_order' in data:
        idea.sort_order = int(data['sort_order'])

    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/newsletter/idea/<int:idea_id>', methods=['DELETE'])
def newsletter_delete_idea(idea_id):
    """Delete a newsletter idea"""
    idea = NewsletterIdea.query.get_or_404(idea_id)
    db.session.delete(idea)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/newsletter/issue', methods=['POST'])
def newsletter_add_issue():
    """Create a new newsletter issue"""
    data = request.get_json()
    title = data.get('title', '').strip()
    if not title:
        return jsonify({'error': 'Title is required'}), 400

    target_date = None
    if data.get('target_date'):
        try:
            target_date = datetime.strptime(data['target_date'], '%Y-%m-%d').date()
        except ValueError:
            pass

    issue = NewsletterIssue(
        title=title,
        target_date=target_date,
        notes=data.get('notes', '').strip(),
        status='planning'
    )
    db.session.add(issue)

    game_stats = get_or_create_game_stats()
    game_stats.newsletter_issues_total = (game_stats.newsletter_issues_total or 0) + 1
    xp = 5
    game_stats.xp += xp

    db.session.commit()

    new_achievements = check_achievements(game_stats)
    leveled_up = check_level_up(game_stats)
    db.session.commit()

    return jsonify({
        'success': True,
        'issue': {
            'id': issue.id,
            'title': issue.title,
            'target_date': issue.target_date.isoformat() if issue.target_date else None,
            'status': issue.status,
            'notes': issue.notes
        },
        'xp_earned': xp,
        'achievements': [a['name'] for a in new_achievements]
    })


@app.route('/api/newsletter/issue/<int:issue_id>', methods=['PUT'])
def newsletter_update_issue(issue_id):
    """Update a newsletter issue"""
    issue = NewsletterIssue.query.get_or_404(issue_id)
    data = request.get_json()

    if 'title' in data:
        issue.title = data['title'].strip()
    if 'status' in data:
        issue.status = data['status']
    if 'notes' in data:
        issue.notes = data['notes'].strip()
    if 'google_doc_url' in data:
        issue.google_doc_url = data['google_doc_url'].strip()
    if 'target_date' in data:
        try:
            issue.target_date = datetime.strptime(data['target_date'], '%Y-%m-%d').date() if data['target_date'] else None
        except ValueError:
            pass

    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/newsletter/export/<int:issue_id>')
def newsletter_export(issue_id):
    """Export an issue's ideas as formatted markdown for Google Docs"""
    issue = NewsletterIssue.query.get_or_404(issue_id)
    ideas = NewsletterIdea.query.filter_by(issue_id=issue_id).order_by(NewsletterIdea.sort_order).all()

    lines = [f"# {issue.title}"]
    if issue.target_date:
        lines[0] += f" — {issue.target_date.strftime('%B %d, %Y')}"
    lines.append("")
    lines.append("## Ideas & Topics")
    lines.append("")

    for i, idea in enumerate(ideas, 1):
        lines.append(f"{i}. **{idea.title}**")
        if idea.notes:
            lines.append(f"   {idea.notes}")
        lines.append("")

    if issue.notes:
        lines.append("---")
        lines.append(f"Notes: {issue.notes}")

    return jsonify({
        'success': True,
        'markdown': '\n'.join(lines),
        'title': issue.title
    })


@app.route('/api/newsletter/subscriber', methods=['POST'])
def newsletter_add_subscriber():
    """Add a subscriber to the mailing list"""
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    name = data.get('name', '').strip()
    language = data.get('language', 'en')

    if not email:
        return jsonify({'error': 'Email is required'}), 400

    # Check for existing
    existing = NewsletterSubscriber.query.filter_by(email=email).first()
    if existing:
        if not existing.active:
            existing.active = True
            existing.name = name or existing.name
            existing.language = language
            db.session.commit()
            return jsonify({'success': True, 'reactivated': True, 'subscriber': {
                'id': existing.id, 'name': existing.name, 'email': existing.email, 'language': existing.language
            }})
        return jsonify({'error': 'Already on the list'}), 400

    sub = NewsletterSubscriber(name=name, email=email, language=language)
    db.session.add(sub)
    db.session.commit()

    return jsonify({
        'success': True,
        'subscriber': {'id': sub.id, 'name': sub.name, 'email': sub.email, 'language': sub.language}
    })


@app.route('/api/newsletter/subscriber/<int:sub_id>', methods=['DELETE'])
def newsletter_remove_subscriber(sub_id):
    """Soft-remove a subscriber from the mailing list"""
    sub = NewsletterSubscriber.query.get_or_404(sub_id)
    sub.active = False
    db.session.commit()
    return jsonify({'success': True})


@app.route('/newsletter/edit/<int:issue_id>')
def newsletter_editor(issue_id):
    """Newsletter content editor for a specific issue"""
    issue = NewsletterIssue.query.get_or_404(issue_id)
    ideas = NewsletterIdea.query.filter_by(issue_id=issue_id).order_by(NewsletterIdea.sort_order).all()
    all_ideas = NewsletterIdea.query.filter(
        NewsletterIdea.status != 'archived'
    ).order_by(NewsletterIdea.created_at.desc()).all()
    subscribers = NewsletterSubscriber.query.filter_by(active=True).all()
    subs_en = [s for s in subscribers if s.language == 'en']
    subs_fr = [s for s in subscribers if s.language == 'fr']
    game_stats = get_or_create_game_stats()
    return render_template('newsletter_editor.html',
                         issue=issue,
                         ideas=ideas,
                         all_ideas=all_ideas,
                         subscribers=subscribers,
                         subs_en=subs_en,
                         subs_fr=subs_fr,
                         game_stats=game_stats)


@app.route('/api/newsletter/issue/<int:issue_id>/content', methods=['PUT'])
def newsletter_save_content(issue_id):
    """Save newsletter content (auto-save endpoint)"""
    issue = NewsletterIssue.query.get_or_404(issue_id)
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON body'}), 400
    if 'content' in data:
        issue.content = data['content']
    if 'title' in data:
        stripped = data['title'].strip()
        if stripped:
            issue.title = stripped
    if issue.status == 'planning' and data.get('content', '').strip():
        issue.status = 'drafting'
    db.session.commit()
    return jsonify({'success': True, 'status': issue.status})


@app.route('/api/newsletter/issue/<int:issue_id>/preview')
def newsletter_preview(issue_id):
    """Render newsletter content as HTML email preview"""
    issue = NewsletterIssue.query.get_or_404(issue_id)
    content_html = markdown.markdown(issue.content or '', extensions=['extra', 'nl2br'])
    return render_template('newsletter_email.html',
                         title=issue.title,
                         issue_date=issue.target_date.strftime('%B %d, %Y') if issue.target_date else None,
                         content_html=content_html,
                         preview=True,
                         issue_id=issue.id)


@app.route('/api/newsletter/issue/<int:issue_id>/export-html')
def newsletter_export_html(issue_id):
    """Get the built HTML for clipboard copy"""
    issue = NewsletterIssue.query.get_or_404(issue_id)
    content_html = markdown.markdown(issue.content or '', extensions=['extra', 'nl2br'])
    full_html = render_template('newsletter_email.html',
                               title=issue.title,
                               issue_date=issue.target_date.strftime('%B %d, %Y') if issue.target_date else None,
                               content_html=content_html,
                               preview=False)
    return jsonify({'success': True, 'html': full_html, 'title': issue.title})


@app.route('/api/newsletter/issue/<int:issue_id>/export-mailto')
def newsletter_export_mailto(issue_id):
    """Get mailto link data with subscribers"""
    issue = NewsletterIssue.query.get_or_404(issue_id)
    lang = request.args.get('lang', 'en')
    if lang not in ('en', 'fr'):
        lang = 'en'
    subscribers = NewsletterSubscriber.query.filter_by(active=True, language=lang).all()
    emails = [s.email for s in subscribers]
    return jsonify({
        'success': True,
        'emails': emails,
        'subject': issue.title,
        'bcc_string': ','.join(emails),
        'count': len(emails)
    })


@app.route('/api/newsletter/issue/<int:issue_id>/mark-sent', methods=['POST'])
def newsletter_mark_sent(issue_id):
    """Mark a newsletter issue as sent, award XP, and archive as HTML"""
    issue = NewsletterIssue.query.get_or_404(issue_id)
    issue.status = 'sent'
    issue.sent_at = datetime.utcnow()

    # --- Archive as clean HTML file ---
    archive_path = None
    try:
        content_html = markdown.markdown(issue.content or '', extensions=['extra', 'nl2br'])
        full_html = render_template('newsletter_email.html',
                                    title=issue.title,
                                    issue_date=issue.target_date.strftime('%B %d, %Y') if issue.target_date else None,
                                    content_html=content_html,
                                    preview=False)

        # Build filename: slugified-title_YYYY-MM-DD.html
        slug = re.sub(r'[^a-z0-9]+', '-', issue.title.lower()).strip('-')
        date_str = issue.target_date.strftime('%Y-%m-%d') if issue.target_date else datetime.utcnow().strftime('%Y-%m-%d')
        filename = f"{slug}_{date_str}.html"

        archive_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'newsletters')
        os.makedirs(archive_dir, exist_ok=True)
        filepath = os.path.join(archive_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_html)

        archive_path = f"newsletters/{filename}"
    except Exception as e:
        print(f"Warning: Could not archive newsletter: {e}")

    game_stats = get_or_create_game_stats()
    xp = 100
    game_stats.xp += xp

    db.session.commit()

    new_achievements = check_achievements(game_stats)
    check_level_up(game_stats)
    db.session.commit()

    return jsonify({
        'success': True,
        'xp_earned': xp,
        'achievements': [a['name'] for a in new_achievements],
        'archive_path': archive_path
    })


@app.route('/api/newsletter/upload-image', methods=['POST'])
def newsletter_upload_image():
    """Upload an image for newsletter content, mirror to Cloudinary for permanent hosting"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400

    # Validate file type
    allowed_ext = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed_ext:
        return jsonify({'error': f'File type .{ext} not allowed. Use: {", ".join(allowed_ext)}'}), 400

    # Save locally with unique name
    import uuid
    filename = f"{uuid.uuid4().hex[:12]}.{ext}"
    upload_dir = os.path.join(app.static_folder, 'uploads', 'newsletter')
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)

    local_url = f"/static/uploads/newsletter/{filename}"

    # Try uploading to Cloudinary for permanent hosting
    cloud_url = None
    cloudinary_name = os.getenv('CLOUDINARY_CLOUD_NAME')
    if cloudinary_name:
        try:
            import cloudinary
            import cloudinary.uploader
            cloudinary.config(
                cloud_name=cloudinary_name,
                api_key=os.getenv('CLOUDINARY_API_KEY'),
                api_secret=os.getenv('CLOUDINARY_API_SECRET')
            )
            resource_type = 'video' if ext == 'mp4' else 'image'
            result = cloudinary.uploader.upload(
                filepath,
                folder='newsletter',
                resource_type=resource_type
            )
            cloud_url = result.get('secure_url')
        except Exception as e:
            print(f"Cloudinary upload failed: {e}")

    return jsonify({
        'success': True,
        'local_url': local_url,
        'cloud_url': cloud_url,
        'url': cloud_url or local_url,
        'filename': filename
    })


@app.route('/api/newsletter/sync-netlify', methods=['POST'])
def sync_netlify_subscribers():
    """Pull new newsletter signups from Netlify Forms API into local database"""
    netlify_token = os.getenv('NETLIFY_ACCESS_TOKEN')
    form_id = os.getenv('NETLIFY_SIGNUP_FORM_ID')
    if not netlify_token or not form_id:
        return jsonify({'error': 'Netlify credentials not configured. Add NETLIFY_ACCESS_TOKEN and NETLIFY_SIGNUP_FORM_ID to .env'}), 400

    try:
        req = urllib.request.Request(
            f'https://api.netlify.com/api/v1/forms/{form_id}/submissions?per_page=100',
            headers={'Authorization': f'Bearer {netlify_token}'}
        )
        with urllib.request.urlopen(req) as resp:
            submissions = json.loads(resp.read().decode())
    except Exception as e:
        return jsonify({'error': f'Failed to fetch from Netlify: {e}'}), 500

    added = 0
    skipped = 0
    for sub in submissions:
        data = sub.get('data', {})
        email = (data.get('email') or '').strip().lower()
        name = (data.get('name') or '').strip()
        reason = (data.get('reason') or '').strip()
        if not email:
            continue
        existing = NewsletterSubscriber.query.filter_by(email=email).first()
        if existing:
            if not existing.active:
                existing.active = True
                existing.name = name or existing.name
                existing.notes = reason or existing.notes
                added += 1
            else:
                skipped += 1
        else:
            new_sub = NewsletterSubscriber(name=name, email=email, language='en', notes=reason)
            db.session.add(new_sub)
            added += 1

    db.session.commit()
    return jsonify({'success': True, 'added': added, 'skipped': skipped, 'total_checked': len(submissions)})


@app.route('/api/newsletter/sync-survey', methods=['POST'])
def sync_survey_responses():
    """Pull survey responses from Netlify Forms API into local database"""
    if 'authenticated' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    netlify_token = os.getenv('NETLIFY_ACCESS_TOKEN')
    survey_form_id = os.getenv('NETLIFY_SURVEY_FORM_ID')
    if not netlify_token or not survey_form_id:
        return jsonify({'error': 'Add NETLIFY_SURVEY_FORM_ID to .env'}), 400

    try:
        req = urllib.request.Request(
            f'https://api.netlify.com/api/v1/forms/{survey_form_id}/submissions?per_page=200',
            headers={'Authorization': f'Bearer {netlify_token}'}
        )
        with urllib.request.urlopen(req) as resp:
            submissions = json.loads(resp.read().decode())
    except Exception as e:
        return jsonify({'error': f'Failed to fetch from Netlify: {e}'}), 500

    added = 0
    for sub in submissions:
        netlify_id = sub.get('id')
        if SurveyResponse.query.filter_by(netlify_id=str(netlify_id)).first():
            continue

        data = sub.get('data', {})
        q1 = (data.get('q1') or '').strip()
        if not q1:
            continue

        response = SurveyResponse(
            survey_name='arc-2',
            email=(data.get('email') or '').strip().lower() or None,
            q1=q1,
            q2=(data.get('q2') or '').strip(),
            q3=(data.get('q3') or '').strip(),
            q4=(data.get('q4') or '').strip(),
            netlify_id=str(netlify_id),
            submitted_at=datetime.fromisoformat(sub['created_at'].replace('Z', '+00:00')) if sub.get('created_at') else datetime.utcnow(),
        )
        db.session.add(response)
        added += 1

    db.session.commit()
    total = SurveyResponse.query.filter_by(survey_name='arc-2').count()
    return jsonify({'success': True, 'added': added, 'total': total})


@app.route('/api/newsletter/survey-results')
def survey_results():
    """Get aggregated survey results"""
    if 'authenticated' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    responses = SurveyResponse.query.filter_by(survey_name='arc-2').order_by(SurveyResponse.submitted_at.desc()).all()

    # Aggregate
    q1_counts = {}
    q2_counts = {}
    q3_counts = {}
    q4_counts = {}
    individual = []

    for r in responses:
        if r.q1:
            q1_counts[r.q1] = q1_counts.get(r.q1, 0) + 1
        if r.q2:
            q2_counts[r.q2] = q2_counts.get(r.q2, 0) + 1
        if r.q3:
            for item in r.q3.split(' | '):
                item = item.strip()
                if item:
                    q3_counts[item] = q3_counts.get(item, 0) + 1
        if r.q4:
            q4_counts[r.q4] = q4_counts.get(r.q4, 0) + 1

        # Match email to subscriber name
        name = None
        if r.email:
            sub = NewsletterSubscriber.query.filter_by(email=r.email).first()
            if sub:
                name = sub.name

        individual.append({
            'email': r.email,
            'name': name,
            'q1': r.q1,
            'q2': r.q2,
            'q3': r.q3,
            'q4': r.q4,
            'submitted_at': r.submitted_at.strftime('%b %d, %H:%M') if r.submitted_at else None,
        })

    return jsonify({
        'total': len(responses),
        'q1': sorted(q1_counts.items(), key=lambda x: -x[1]),
        'q2': sorted(q2_counts.items(), key=lambda x: -x[1]),
        'q3': sorted(q3_counts.items(), key=lambda x: -x[1]),
        'q4': sorted(q4_counts.items(), key=lambda x: -x[1]),
        'individual': individual,
    })


# ===== API USAGE DASHBOARD =====

@app.route('/api-usage')
def api_usage_dashboard():
    """Dashboard showing Claude API usage and costs"""
    if 'authenticated' not in session:
        return redirect(url_for('login'))

    today = datetime.now().date()
    first_of_month = today.replace(day=1)

    # Summary stats
    total_cost = db.session.query(db.func.sum(ApiUsageLog.cost_usd)).scalar() or 0
    month_cost = db.session.query(db.func.sum(ApiUsageLog.cost_usd)).filter(
        db.func.date(ApiUsageLog.timestamp) >= first_of_month
    ).scalar() or 0
    today_cost = db.session.query(db.func.sum(ApiUsageLog.cost_usd)).filter(
        db.func.date(ApiUsageLog.timestamp) == today
    ).scalar() or 0
    total_calls = ApiUsageLog.query.count()

    # Cost by feature
    feature_costs = db.session.query(
        ApiUsageLog.feature,
        db.func.sum(ApiUsageLog.cost_usd),
        db.func.count(ApiUsageLog.id)
    ).group_by(ApiUsageLog.feature).all()
    feature_data = [{'feature': f, 'cost': round(c, 4), 'calls': n} for f, c, n in feature_costs]

    # Cost by model
    model_costs = db.session.query(
        ApiUsageLog.model,
        db.func.sum(ApiUsageLog.cost_usd),
        db.func.count(ApiUsageLog.id)
    ).group_by(ApiUsageLog.model).all()
    model_data = [{'model': m.split('-')[1] if '-' in m else m, 'cost': round(c, 4), 'calls': n} for m, c, n in model_costs]

    # Daily costs (last 30 days)
    thirty_days_ago = today - timedelta(days=30)
    daily_costs = db.session.query(
        db.func.date(ApiUsageLog.timestamp),
        db.func.sum(ApiUsageLog.cost_usd),
        db.func.count(ApiUsageLog.id)
    ).filter(
        db.func.date(ApiUsageLog.timestamp) >= thirty_days_ago
    ).group_by(db.func.date(ApiUsageLog.timestamp)).order_by(db.func.date(ApiUsageLog.timestamp)).all()
    daily_data = [{'date': str(d), 'cost': round(c, 4), 'calls': n} for d, c, n in daily_costs]

    # Recent calls
    recent = ApiUsageLog.query.order_by(ApiUsageLog.timestamp.desc()).limit(50).all()
    recent_data = [l.to_dict() for l in recent]

    return render_template('api_usage.html',
        total_cost=round(total_cost, 4),
        month_cost=round(month_cost, 4),
        today_cost=round(today_cost, 4),
        total_calls=total_calls,
        feature_data=json.dumps(feature_data),
        model_data=json.dumps(model_data),
        daily_data=json.dumps(daily_data),
        recent_calls=recent_data
    )


# ===== MANDARIN LEARNING =====

MANDARIN_CATEGORIES = [
    {"id": "tones", "name": "Pinyin & Tones", "icon": "🎵", "order": 0},
    {"id": "greetings", "name": "Greetings & Politeness", "icon": "👋", "order": 1},
    {"id": "numbers", "name": "Numbers & Prices", "icon": "🔢", "order": 2},
    {"id": "survival", "name": "Survival Phrases", "icon": "🆘", "order": 3},
    {"id": "food_dining", "name": "Food & Dining", "icon": "🍜", "order": 4},
    {"id": "shopping", "name": "Shopping & Prices", "icon": "🛍️", "order": 5},
    {"id": "directions", "name": "Directions & Navigation", "icon": "🧭", "order": 6},
    {"id": "transportation", "name": "Transportation", "icon": "🚇", "order": 7},
    {"id": "hotel", "name": "Hotel & Accommodation", "icon": "🏨", "order": 8},
    {"id": "emergencies", "name": "Emergencies", "icon": "🚨", "order": 9},
]


def get_mandarin_unlocked_categories():
    """Determine which categories are unlocked based on learning progress."""
    unlocked = ["tones"]  # Always unlocked
    cat_ids = [c["id"] for c in MANDARIN_CATEGORIES]

    for i in range(1, len(cat_ids)):
        prev_cat = cat_ids[i - 1]
        # Count cards in previous category with interval >= 3
        total_cards = MandarinCard.query.filter_by(category=prev_cat).count()
        if total_cards == 0:
            break
        learned = db.session.query(MandarinReview).join(MandarinCard).filter(
            MandarinCard.category == prev_cat,
            MandarinReview.interval_days >= 3
        ).count()
        if learned / total_cards >= 0.7:
            unlocked.append(cat_ids[i])
        else:
            break

    return unlocked


def mandarin_srs_update(review, rating):
    """SM-2 variant: update review based on rating (hard/good/easy)."""
    review.total_reviews += 1
    review.last_reviewed = datetime.utcnow()

    if rating == 'hard':
        review.repetitions = 0
        review.interval_days = 1
        review.ease_factor = max(1.3, review.ease_factor - 0.2)
    elif rating == 'good':
        review.correct_count += 1
        review.repetitions += 1
        if review.repetitions == 1:
            review.interval_days = 1
        elif review.repetitions == 2:
            review.interval_days = 3
        else:
            review.interval_days = int(review.interval_days * review.ease_factor)
    elif rating == 'easy':
        review.correct_count += 1
        review.repetitions += 1
        if review.repetitions == 1:
            review.interval_days = 2
        elif review.repetitions == 2:
            review.interval_days = 4
        else:
            review.interval_days = int(review.interval_days * review.ease_factor * 1.3)
        review.ease_factor += 0.15

    review.next_review_date = (datetime.utcnow().date() + timedelta(days=review.interval_days))


@app.route('/mandarin')
def mandarin():
    """Mandarin learning dashboard."""
    if 'authenticated' not in session:
        return redirect(url_for('login'))

    game_stats = get_or_create_game_stats()
    unlocked = get_mandarin_unlocked_categories()

    # Category progress
    categories = []
    for cat in MANDARIN_CATEGORIES:
        total = MandarinCard.query.filter_by(category=cat["id"]).count()
        learned = db.session.query(MandarinReview).join(MandarinCard).filter(
            MandarinCard.category == cat["id"],
            MandarinReview.interval_days >= 3
        ).count()
        categories.append({
            **cat,
            "total": total,
            "learned": learned,
            "unlocked": cat["id"] in unlocked,
        })

    # Today's review count
    today = datetime.now().date()
    due_count = MandarinReview.query.filter(
        MandarinReview.next_review_date <= today
    ).count()

    # Total accuracy
    total_reviews_count = db.session.query(db.func.sum(MandarinReview.total_reviews)).scalar() or 0
    total_correct = db.session.query(db.func.sum(MandarinReview.correct_count)).scalar() or 0
    accuracy = int((total_correct / total_reviews_count * 100)) if total_reviews_count > 0 else 0

    return render_template('mandarin.html',
        game_stats=game_stats,
        categories=categories,
        due_count=due_count,
        accuracy=accuracy,
    )


@app.route('/api/mandarin/session')
def mandarin_session():
    """Build today's deck: due reviews (max 25) + new cards (max 5)."""
    if 'authenticated' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    today = datetime.now().date()
    unlocked = get_mandarin_unlocked_categories()

    # Due reviews (capped at 25), only from unlocked categories
    due_reviews = db.session.query(MandarinCard).join(MandarinReview).filter(
        MandarinReview.next_review_date <= today,
        MandarinCard.category.in_(unlocked)
    ).order_by(MandarinReview.next_review_date).limit(25).all()

    # New cards: cards without a review record, from unlocked categories (max 5)
    reviewed_ids = db.session.query(MandarinReview.card_id).subquery()
    new_cards = MandarinCard.query.filter(
        MandarinCard.category.in_(unlocked),
        ~MandarinCard.id.in_(reviewed_ids)
    ).order_by(
        db.case(
            *[(MandarinCard.category == cat_id, i) for i, cat_id in enumerate([c["id"] for c in MANDARIN_CATEGORIES])]
        ),
        MandarinCard.sort_order
    ).limit(5).all()

    deck = []
    for card in due_reviews:
        review = MandarinReview.query.filter_by(card_id=card.id).first()
        deck.append({
            'id': card.id,
            'english': card.english,
            'pinyin': card.pinyin,
            'characters': card.characters,
            'category': card.category,
            'usage_note': card.usage_note or '',
            'tone_pattern': card.tone_pattern or '',
            'is_tone_drill': card.is_tone_drill,
            'is_new': False,
            'interval': review.interval_days if review else 0,
        })

    for card in new_cards:
        deck.append({
            'id': card.id,
            'english': card.english,
            'pinyin': card.pinyin,
            'characters': card.characters,
            'category': card.category,
            'usage_note': card.usage_note or '',
            'tone_pattern': card.tone_pattern or '',
            'is_tone_drill': card.is_tone_drill,
            'is_new': True,
            'interval': 0,
        })

    return jsonify({'deck': deck, 'due_count': len(due_reviews), 'new_count': len(new_cards)})


@app.route('/api/mandarin/review', methods=['POST'])
def mandarin_review():
    """Submit a card rating (hard/good/easy) and update SRS."""
    if 'authenticated' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    card_id = data.get('card_id')
    rating = data.get('rating')  # hard, good, easy

    if not card_id or rating not in ('hard', 'good', 'easy'):
        return jsonify({'error': 'Invalid card_id or rating'}), 400

    card = MandarinCard.query.get(card_id)
    if not card:
        return jsonify({'error': 'Card not found'}), 404

    # Get or create review
    review = MandarinReview.query.filter_by(card_id=card_id).first()
    is_new = review is None
    if is_new:
        review = MandarinReview(
            card_id=card_id,
            ease_factor=2.5,
            interval_days=0,
            repetitions=0,
            total_reviews=0,
            correct_count=0,
        )
        db.session.add(review)

    mandarin_srs_update(review, rating)
    db.session.commit()

    return jsonify({
        'success': True,
        'is_new': is_new,
        'next_review': str(review.next_review_date),
        'interval': review.interval_days,
        'ease': round(review.ease_factor, 2),
    })


@app.route('/api/mandarin/complete', methods=['POST'])
def mandarin_complete():
    """End session, record stats, award XP, update streak."""
    if 'authenticated' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    cards_reviewed = data.get('cards_reviewed', 0)
    cards_new = data.get('cards_new', 0)
    cards_correct = data.get('cards_correct', 0)
    cards_hard = data.get('cards_hard', 0)
    duration_seconds = data.get('duration_seconds', 0)
    session_type = data.get('session_type', 'review')

    today = datetime.now().date()

    # Record session
    ms = MandarinSession(
        date=today,
        cards_reviewed=cards_reviewed,
        cards_new=cards_new,
        cards_correct=cards_correct,
        cards_hard=cards_hard,
        duration_seconds=duration_seconds,
        session_type=session_type,
    )

    # Calculate XP
    xp = 15  # base
    xp += cards_reviewed * 2  # per card
    xp += cards_new * 3  # per new card
    if cards_reviewed > 0 and (cards_correct / cards_reviewed) >= 0.8:
        xp += 10  # accuracy bonus

    game_stats = get_or_create_game_stats()

    # Streak
    if game_stats.last_mandarin_date == today - timedelta(days=1):
        game_stats.mandarin_streak = (game_stats.mandarin_streak or 0) + 1
    elif game_stats.last_mandarin_date != today:
        game_stats.mandarin_streak = 1

    if (game_stats.mandarin_streak or 0) >= 7:
        xp += 5  # streak bonus

    ms.xp_earned = xp
    db.session.add(ms)

    game_stats.last_mandarin_date = today
    game_stats.mandarin_sessions_total = (game_stats.mandarin_sessions_total or 0) + 1
    game_stats.mandarin_xp_total = (game_stats.mandarin_xp_total or 0) + xp
    game_stats.xp = (game_stats.xp or 0) + xp

    # Count total cards learned (interval >= 3)
    game_stats.mandarin_cards_learned = MandarinReview.query.filter(
        MandarinReview.interval_days >= 3
    ).count()

    db.session.commit()
    check_level_up(game_stats)
    db.session.commit()

    return jsonify({
        'success': True,
        'xp_earned': xp,
        'streak': game_stats.mandarin_streak,
        'total_xp': game_stats.mandarin_xp_total,
        'cards_learned': game_stats.mandarin_cards_learned,
    })


@app.route('/api/mandarin/explain', methods=['POST'])
def mandarin_explain():
    """Use Claude Haiku to explain a Mandarin phrase."""
    if 'authenticated' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    if not claude_client:
        return jsonify({'error': 'Claude API not configured'}), 500

    data = request.get_json()
    card_id = data.get('card_id')
    if not card_id or not isinstance(card_id, int):
        return jsonify({'error': 'Invalid card_id'}), 400
    card = MandarinCard.query.get(card_id)
    if not card:
        return jsonify({'error': 'Card not found'}), 404

    prompt = f"""Explain this Mandarin phrase for a beginner tourist:

English: {card.english}
Pinyin: {card.pinyin}
Characters: {card.characters}
Tone pattern: {card.tone_pattern}

Provide:
1. Tone-by-tone pronunciation guide (describe how to say each syllable)
2. One cultural or usage tip
3. Two example sentences using this phrase (with pinyin and English translation)

Keep it concise and practical for a traveler."""

    response = call_claude(
        feature='mandarin',
        endpoint='explain',
        model='claude-haiku-4-5-20251001',
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    return jsonify({
        'success': True,
        'explanation': response.content[0].text,
    })


@app.route('/api/mandarin/stats')
def mandarin_stats():
    """JSON stats for AJAX updates."""
    if 'authenticated' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    game_stats = get_or_create_game_stats()
    today = datetime.now().date()

    due_count = MandarinReview.query.filter(
        MandarinReview.next_review_date <= today
    ).count()

    total_reviews_count = db.session.query(db.func.sum(MandarinReview.total_reviews)).scalar() or 0
    total_correct = db.session.query(db.func.sum(MandarinReview.correct_count)).scalar() or 0
    accuracy = int((total_correct / total_reviews_count * 100)) if total_reviews_count > 0 else 0

    # Recent sessions
    recent = MandarinSession.query.order_by(MandarinSession.date.desc()).limit(7).all()
    recent_data = [{
        'date': str(s.date),
        'cards_reviewed': s.cards_reviewed,
        'cards_correct': s.cards_correct,
        'xp_earned': s.xp_earned,
    } for s in recent]

    return jsonify({
        'streak': game_stats.mandarin_streak or 0,
        'total_xp': game_stats.mandarin_xp_total or 0,
        'cards_learned': game_stats.mandarin_cards_learned or 0,
        'sessions_total': game_stats.mandarin_sessions_total or 0,
        'accuracy': accuracy,
        'due_count': due_count,
        'recent_sessions': recent_data,
    })


@app.route('/api/mandarin/categories')
def mandarin_categories():
    """Category progress data."""
    if 'authenticated' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    unlocked = get_mandarin_unlocked_categories()
    categories = []
    for cat in MANDARIN_CATEGORIES:
        total = MandarinCard.query.filter_by(category=cat["id"]).count()
        learned = db.session.query(MandarinReview).join(MandarinCard).filter(
            MandarinCard.category == cat["id"],
            MandarinReview.interval_days >= 3
        ).count()
        cards = []
        if cat["id"] in unlocked:
            card_objs = MandarinCard.query.filter_by(category=cat["id"]).order_by(MandarinCard.sort_order).all()
            for c in card_objs:
                review = MandarinReview.query.filter_by(card_id=c.id).first()
                cards.append({
                    'id': c.id,
                    'english': c.english,
                    'pinyin': c.pinyin,
                    'characters': c.characters,
                    'learned': review.interval_days >= 3 if review else False,
                })
        categories.append({
            **cat,
            'total': total,
            'learned': learned,
            'unlocked': cat["id"] in unlocked,
            'cards': cards,
        })

    return jsonify({'categories': categories})


# ===== PERSONAL FINANCE =====

FINANCE_CATEGORIES = {
    'Rent / Housing': {
        'keywords': [],
        'icon': 'home', 'color': '#5D4037'
    },
    'Groceries': {
        'keywords': ['okay', 'intermarché', 'delhaize', 'carrefour', 'whole foods', 'safeway', 'colruyt', 'aldi', 'lidl', 'albert heijn', 'spirigros'],
        'icon': 'cart', 'color': '#4CAF50'
    },
    'Dining Out': {
        'keywords': ['burger', 'kitchen', 'restaurant', 'sushi', 'tataki', 'sebastia', 'taretata', 'green mango', 'panos', 'aichinger',
                     'chou sando', "l'aperitivo", 'le montmartre', 'les brassins', 'la mie', 'traiteur', 'panda express',
                     'menya', 'aspromonte', 'seniores pizza', 'rt rotisserie', 'okane', 'la frontaliere', 'imanor',
                     'wobbles', 'uber eats', "o'tacos", 'patybread', 'le saint-aulaye', 'holy bagel', 'boma',
                     'boulangerie', 'sandwicherie', 'smoothiebar', 'boucherie', 'panymas', 'le gauguin',
                     'bulbuly', 'au soleil', 'tacos', 'alarji'],
        'icon': 'utensils', 'color': '#FF9800'
    },
    'Coffee & Drinks': {
        'keywords': ['kaffabar', 'blue bottle', 'coffee project', 'cafe suspiro', 'doppio', 'souvenir coffee', 'wide awake',
                     'friedhats', 'oak gourmet', "q's sandwich", 'black point cof',
                     'dak coffee', 'plamkafe', 'café circus', 'cafe circus'],
        'icon': 'coffee', 'color': '#795548'
    },
    'Transport': {
        'keywords': ['stib', 'mivb', 'sncb', 'uber', 'bolt', 'lime', 'bc ferries'],
        'icon': 'bus', 'color': '#2196F3',
        'exclude': ['uber eats']
    },
    'Nightlife': {
        'keywords': ['cercle', 'beer bar', 'ratabar', 'le snap', 'au bassin', 'night and day', "a'alps",
                     'le supra', '1030 café', 'le tavernier', 'dia company',
                     'barabar', '14 stars', 'loft', 'la frontaliere'],
        'icon': 'moon', 'color': '#9C27B0'
    },
    'Subscriptions': {
        'keywords': ['apple', 'patreon', 'anthropic', 'amazon prime', 'netflix', 'spotify', 'riot games', 'abonnement metal'],
        'icon': 'repeat', 'color': '#607D8B',
        'exclude': ['apple pay', 'recharge']
    },
    'Travel': {
        'keywords': ['air canada', 'british airways', 'brussels airlines', 'ryanair', 'easyjet', 'booking.com',
                     'airbnb', 'munich airport', 'whsmith', 'q8', 'scandinavian airlines'],
        'icon': 'plane', 'color': '#00BCD4'
    },
    'Health & Fitness': {
        'keywords': ['fitness', 'pharmacy', 'pharma', 'gym', 'ulb sports', 'golazo sports'],
        'icon': 'heart', 'color': '#F44336'
    },
    'Shopping': {
        'keywords': ['amazon', 'media gsm', 'fnac', 'zara', 'h&m'],
        'icon': 'bag', 'color': '#E91E63',
        'exclude': ['amazon prime']
    },
    'Investments': {
        'keywords': ['trade republic', 'bolero', 'degiro'],
        'icon': 'trending-up', 'color': '#3F51B5'
    },
    'Salary': {
        'keywords': ['deel belgium', 'deel be'],
        'icon': 'briefcase', 'color': '#4CAF50'
    },
    'Family Transfer': {
        'keywords': [],
        'icon': 'users', 'color': '#8BC34A'
    },
    'Savings': {
        'keywords': ['compte d\'épargne', 'savings'],
        'icon': 'piggy-bank', 'color': '#FFC107'
    },
    'Interest': {
        'keywords': ['interest earned'],
        'icon': 'trending-up', 'color': '#009688'
    },
    'Bank Transfer': {
        'keywords': ['kbc bank', 'belfius', 'bnp', 'ing'],
        'icon': 'arrow-right', 'color': '#78909C'
    },
    'SF Trip (Mar)': {
        'keywords': [],
        'icon': 'map-pin', 'color': '#FF5722'
    },
    'SF Trip (Apr)': {
        'keywords': [],
        'icon': 'map-pin', 'color': '#E64A19'
    },
    'Vancouver Trip': {
        'keywords': [],
        'icon': 'map-pin', 'color': '#D32F2F'
    },
    'Other': {
        'keywords': [],
        'icon': 'more-horizontal', 'color': '#9E9E9E'
    },
}

FINANCE_CATEGORY_LIST = list(FINANCE_CATEGORIES.keys())


def auto_categorize_transaction(description, transaction_type, revolut_type=None):
    """Auto-categorize a transaction based on description keywords"""
    desc_lower = description.lower()

    # Handle Revolut-specific types
    if revolut_type == 'Intérêts':
        return 'Interest', 'interest'
    if 'abonnement metal' in desc_lower or 'frais d\'abonnement' in desc_lower:
        return 'Subscriptions', 'subscription'

    # Check for savings transfers
    if 'compte d\'épargne' in desc_lower or 'savings' in desc_lower:
        return 'Savings', 'transfer'

    # Person-to-person transfers (Virement de/à: NAME)
    if 'virement de' in desc_lower or 'virement à' in desc_lower or 'virement ' in desc_lower:
        if revolut_type == 'Virement':
            return 'Family Transfer', 'transfer'

    # Check each category with exclude logic
    for cat_name, cat_info in FINANCE_CATEGORIES.items():
        if cat_name in ('Other', 'Family Transfer', 'Savings', 'Interest', 'Investments'):
            continue
        excludes = [e.lower() for e in cat_info.get('exclude', [])]
        for keyword in cat_info['keywords']:
            if keyword.lower() in desc_lower:
                # Check excludes
                if any(ex in desc_lower for ex in excludes):
                    continue
                # Determine transaction type
                if cat_name == 'Salary':
                    return cat_name, 'income'
                elif cat_name == 'Bank Transfer':
                    return cat_name, 'transfer'
                elif cat_name == 'Investments':
                    return cat_name, 'investment'
                else:
                    return cat_name, 'expense'

    # Default
    if transaction_type == 'income' or (transaction_type is None and revolut_type in ('Ajout de fonds',)):
        return 'Other', 'income'
    return 'Other', 'expense'


def parse_revolut_csv(file_content):
    """Parse Revolut CSV (French locale) and return list of transaction dicts"""
    transactions = []

    # Try to detect encoding and delimiter
    reader = csv.DictReader(io.StringIO(file_content))
    fieldnames = reader.fieldnames

    # Map French headers to our fields
    header_map = {
        'Type': 'revolut_type',
        'Produit': 'product',
        'Date de début': 'date_start',
        'Date de fin': 'date_end',
        'Description': 'description',
        'Montant': 'amount',
        'Frais': 'fee',
        'Devise': 'currency',
        'État': 'state',
        'Solde': 'balance',
        # English headers (in case locale is EN)
        'Product': 'product',
        'Started Date': 'date_start',
        'Completed Date': 'date_end',
        'Amount': 'amount',
        'Fee': 'fee',
        'Currency': 'currency',
        'State': 'state',
        'Balance': 'balance',
    }

    for row in reader:
        mapped = {}
        for csv_col, our_col in header_map.items():
            if csv_col in row:
                mapped[our_col] = row[csv_col]

        # Skip reversed transactions
        state = mapped.get('state', '')
        if state in ('RENVOYÉ', 'REVERTED', 'DECLINED'):
            continue

        # Parse date
        date_str = mapped.get('date_start', '')
        if not date_str:
            continue
        try:
            tx_date = datetime.strptime(date_str.split(' ')[0], '%Y-%m-%d').date()
        except (ValueError, IndexError):
            continue

        # Parse amount and fee
        try:
            amount = float(mapped.get('amount', '0').replace(',', '.'))
        except ValueError:
            amount = 0.0
        try:
            fee = float(mapped.get('fee', '0').replace(',', '.'))
        except ValueError:
            fee = 0.0

        description = mapped.get('description', row.get('Description', ''))
        revolut_type = row.get('Type', '')
        product = mapped.get('product', '')
        currency = mapped.get('currency', 'EUR')

        # Determine transaction type
        if revolut_type == 'Intérêts':
            tx_type = 'interest'
        elif revolut_type == 'Virement':
            tx_type = 'transfer'
        elif revolut_type == 'Ajout de fonds':
            tx_type = 'income'
        elif revolut_type == 'Valider le paiement':
            tx_type = 'subscription'
        else:
            tx_type = 'income' if amount > 0 else 'expense'

        category, final_type = auto_categorize_transaction(description, tx_type, revolut_type)

        # For subscription fees where amount is 0 but fee > 0
        effective_amount = amount
        if amount == 0 and fee > 0:
            effective_amount = -fee
            fee = 0

        # Create hash for dedup (date + description + amount + product)
        hash_input = f"{tx_date}|{description}|{effective_amount}|{fee}|{product}|{date_str}"
        import_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        transactions.append({
            'date': tx_date,
            'description': description,
            'amount': effective_amount,
            'fee': fee,
            'currency': currency,
            'category': category,
            'transaction_type': final_type,
            'revolut_product': product,
            'state': state,
            'import_hash': import_hash,
            'source': 'revolut_import',
        })

    return transactions


@app.route('/finance')
def finance():
    """Personal Finance dashboard"""
    today = date.today()
    current_month = request.args.get('month', today.strftime('%Y-%m'))
    try:
        year, month = map(int, current_month.split('-'))
        month_start = date(year, month, 1)
    except (ValueError, TypeError):
        year, month = today.year, today.month
        month_start = date(year, month, 1)
        current_month = today.strftime('%Y-%m')

    if month == 12:
        month_end = date(year + 1, 1, 1)
    else:
        month_end = date(year, month + 1, 1)

    # Get transactions for this month
    transactions = FinanceTransaction.query.filter(
        FinanceTransaction.date >= month_start,
        FinanceTransaction.date < month_end,
        FinanceTransaction.state != 'RENVOYÉ',
    ).order_by(FinanceTransaction.date.desc()).all()

    # Compute summary
    total_income = sum(t.amount for t in transactions if t.transaction_type == 'income')
    total_interest = sum(t.amount for t in transactions if t.transaction_type == 'interest')
    total_expenses = sum(abs(t.amount) + t.fee for t in transactions if t.transaction_type in ('expense', 'subscription'))
    total_transfers = sum(t.amount for t in transactions if t.transaction_type == 'transfer')
    total_invested = sum(abs(t.amount) for t in transactions if t.transaction_type == 'investment')

    # Category breakdown (expenses only)
    category_totals = {}
    for t in transactions:
        if t.transaction_type in ('expense', 'subscription'):
            cat = t.category or 'Other'
            cost = abs(t.amount) + (t.fee or 0)
            category_totals[cat] = category_totals.get(cat, 0) + cost

    budgets = FinanceBudget.query.filter_by(is_active=True).all()

    # Recurring costs — fold into expense totals & category breakdown so the dashboard
    # reflects fixed costs (rent, etc.) alongside imported transactions.
    recurring = FinanceRecurringCost.query.filter_by(is_active=True).all()
    freq_to_monthly = {'monthly': 1.0, 'yearly': 1.0 / 12, 'weekly': 52.0 / 12}
    recurring_total = 0.0
    for r in recurring:
        monthly_amt = r.amount * freq_to_monthly.get(r.frequency, 1.0)
        recurring_total += monthly_amt
        cat = r.category or 'Other'
        category_totals[cat] = category_totals.get(cat, 0) + monthly_amt
    total_expenses += recurring_total

    # Re-sort category breakdown after adding recurring
    category_breakdown = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)

    # Re-compute budget progress against the new category_totals
    budget_progress = []
    for b in budgets:
        spent = category_totals.get(b.category, 0)
        budget_progress.append({
            **b.to_dict(),
            'spent': spent,
            'percentage': round((spent / b.monthly_limit) * 100, 1) if b.monthly_limit > 0 else 0,
        })

    # Monthly history (last 6 months)
    # Find the earliest transaction to know where to start the trend
    earliest_tx = FinanceTransaction.query.order_by(FinanceTransaction.date.asc()).first()
    if earliest_tx:
        trend_start_month = max(earliest_tx.date.month + (earliest_tx.date.year * 12),
                                (today.year * 12 + today.month) - 5)
    else:
        trend_start_month = today.year * 12 + today.month

    monthly_history = []
    current_month_num = today.year * 12 + today.month
    for m_num in range(trend_start_month, current_month_num + 1):
        y = (m_num - 1) // 12
        m = (m_num - 1) % 12 + 1
        m_start = date(y, m, 1)
        if m == 12:
            m_end = date(y + 1, 1, 1)
        else:
            m_end = date(y, m + 1, 1)

        m_txns = FinanceTransaction.query.filter(
            FinanceTransaction.date >= m_start,
            FinanceTransaction.date < m_end,
            FinanceTransaction.state != 'RENVOYÉ',
        ).all()

        m_income = sum(t.amount for t in m_txns if t.transaction_type == 'income')
        m_expenses = sum(abs(t.amount) + t.fee for t in m_txns if t.transaction_type in ('expense', 'subscription'))
        m_expenses += recurring_total

        # Skip months with no data at all
        if not m_txns and m_num < current_month_num:
            continue

        monthly_history.append({
            'month': m_start.strftime('%Y-%m'),
            'label': m_start.strftime('%b %Y'),
            'income': round(m_income, 2),
            'expenses': round(m_expenses, 2),
            'net': round(m_income - m_expenses, 2),
        })

    # Trips dashboard — aggregate spending per trip across all months
    trips = Trip.query.order_by(Trip.start_date.asc().nullslast()).all()
    trip_data = []
    for trip in trips:
        d = trip.to_dict()
        if trip.category:
            t_txns = FinanceTransaction.query.filter(
                FinanceTransaction.category == trip.category,
                FinanceTransaction.transaction_type.in_(('expense', 'subscription')),
                FinanceTransaction.state != 'RENVOYÉ',
            ).all()
            d['total_spent'] = round(sum(abs(t.amount) + (t.fee or 0) for t in t_txns), 2)
            d['txn_count'] = len(t_txns)
        else:
            d['total_spent'] = 0.0
            d['txn_count'] = 0
        if trip.start_date and trip.end_date:
            d['duration_days'] = (trip.end_date - trip.start_date).days + 1
            d['daily_avg'] = round(d['total_spent'] / d['duration_days'], 2) if d['duration_days'] > 0 else 0
        else:
            d['duration_days'] = None
            d['daily_avg'] = None
        if trip.budget and trip.budget > 0:
            d['budget_pct'] = round((d['total_spent'] / trip.budget) * 100, 1)
        else:
            d['budget_pct'] = None
        trip_data.append(d)

    return render_template('finance.html',
        current_month=current_month,
        month_label=month_start.strftime('%B %Y'),
        transactions=[t.to_dict() for t in transactions],
        total_income=round(total_income, 2),
        total_interest=round(total_interest, 2),
        total_expenses=round(total_expenses, 2),
        total_transfers=round(total_transfers, 2),
        net_savings=round(total_income - total_expenses, 2),
        total_invested=round(total_invested, 2),
        leftover=round(total_income - total_expenses - total_invested, 2),
        category_breakdown=category_breakdown,
        category_info=FINANCE_CATEGORIES,
        budget_progress=budget_progress,
        recurring_costs=[r.to_dict() for r in recurring],
        monthly_history=monthly_history,
        categories=FINANCE_CATEGORY_LIST,
        trips=trip_data,
        today=today,
    )


@app.route('/api/trips', methods=['POST'])
def trips_create():
    """Create a new trip"""
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    try:
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date() if data.get('start_date') else None
        end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date() if data.get('end_date') else None
    except ValueError:
        return jsonify({'error': 'Invalid date'}), 400
    category = (data.get('category') or '').strip() or name
    trip = Trip(
        name=name,
        destination=(data.get('destination') or '').strip() or None,
        start_date=start_date,
        end_date=end_date,
        category=category,
        status=data.get('status') or 'planned',
        budget=float(data['budget']) if data.get('budget') else None,
        notes=(data.get('notes') or '').strip() or None,
        color=data.get('color') or '#FF5722',
    )
    db.session.add(trip)
    db.session.commit()
    return jsonify({'success': True, 'trip': trip.to_dict()})


@app.route('/api/trips/<int:trip_id>', methods=['PUT'])
def trips_update(trip_id):
    """Update a trip"""
    trip = Trip.query.get_or_404(trip_id)
    data = request.get_json()
    if 'name' in data: trip.name = (data['name'] or '').strip() or trip.name
    if 'destination' in data: trip.destination = (data['destination'] or '').strip() or None
    if 'start_date' in data:
        trip.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date() if data['start_date'] else None
    if 'end_date' in data:
        trip.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date() if data['end_date'] else None
    if 'category' in data: trip.category = (data['category'] or '').strip() or trip.category
    if 'status' in data: trip.status = data['status']
    if 'budget' in data:
        trip.budget = float(data['budget']) if data['budget'] not in ('', None) else None
    if 'notes' in data: trip.notes = (data['notes'] or '').strip() or None
    if 'color' in data: trip.color = data['color']
    db.session.commit()
    return jsonify({'success': True, 'trip': trip.to_dict()})


@app.route('/api/trips/<int:trip_id>', methods=['DELETE'])
def trips_delete(trip_id):
    """Delete a trip (does not affect transactions)"""
    trip = Trip.query.get_or_404(trip_id)
    db.session.delete(trip)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/finance/import-csv', methods=['POST'])
def finance_import_csv():
    """Import transactions from Revolut CSV"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400

    raw = file.read()
    content = None
    for encoding in ('utf-8-sig', 'utf-8', 'latin-1'):
        try:
            content = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        return jsonify({'error': 'Could not decode file'}), 400

    transactions = parse_revolut_csv(content)

    imported = 0
    skipped = 0
    for tx in transactions:
        # Check for duplicate
        existing = FinanceTransaction.query.filter_by(import_hash=tx['import_hash']).first()
        if existing:
            skipped += 1
            continue

        new_tx = FinanceTransaction(
            date=tx['date'],
            description=tx['description'],
            amount=tx['amount'],
            fee=tx['fee'],
            currency=tx['currency'],
            category=tx['category'],
            transaction_type=tx['transaction_type'],
            revolut_product=tx['revolut_product'],
            state=tx['state'],
            import_hash=tx['import_hash'],
            source='revolut_import',
        )
        db.session.add(new_tx)
        imported += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'imported': imported,
        'skipped': skipped,
        'total': len(transactions),
    })


@app.route('/api/finance/import-folder', methods=['POST'])
def finance_import_folder():
    """Import all CSV files from data/revolut-imports/ folder"""
    import_dir = os.path.join(os.path.dirname(__file__), 'data', 'revolut-imports')
    if not os.path.exists(import_dir):
        return jsonify({'error': 'Import folder not found'}), 404

    csv_files = [f for f in os.listdir(import_dir) if f.lower().endswith('.csv')]
    if not csv_files:
        return jsonify({'success': True, 'message': 'No CSV files found in data/revolut-imports/', 'files': []})

    results = []
    total_imported = 0
    total_skipped = 0

    for filename in sorted(csv_files):
        filepath = os.path.join(import_dir, filename)
        content = None
        for encoding in ('utf-8-sig', 'utf-8', 'latin-1'):
            try:
                with open(filepath, encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            results.append({'file': filename, 'error': 'Could not decode'})
            continue

        transactions = parse_revolut_csv(content)
        imported = 0
        skipped = 0
        for tx in transactions:
            existing = FinanceTransaction.query.filter_by(import_hash=tx['import_hash']).first()
            if existing:
                skipped += 1
                continue
            new_tx = FinanceTransaction(
                date=tx['date'],
                description=tx['description'],
                amount=tx['amount'],
                fee=tx['fee'],
                currency=tx['currency'],
                category=tx['category'],
                transaction_type=tx['transaction_type'],
                revolut_product=tx['revolut_product'],
                state=tx['state'],
                import_hash=tx['import_hash'],
                source='revolut_import',
            )
            db.session.add(new_tx)
            imported += 1

        total_imported += imported
        total_skipped += skipped
        results.append({'file': filename, 'imported': imported, 'skipped': skipped})

    db.session.commit()
    return jsonify({
        'success': True,
        'total_imported': total_imported,
        'total_skipped': total_skipped,
        'files': results,
    })


@app.route('/api/finance/transaction', methods=['POST'])
def finance_add_transaction():
    """Add a manual transaction"""
    data = request.get_json()
    try:
        tx_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
    except (KeyError, ValueError):
        return jsonify({'error': 'Invalid date'}), 400

    amount = float(data.get('amount', 0))
    tx_type = data.get('transaction_type', 'expense')
    if tx_type == 'expense' and amount > 0:
        amount = -amount

    tx = FinanceTransaction(
        date=tx_date,
        description=data.get('description', ''),
        amount=amount,
        fee=float(data.get('fee', 0)),
        currency=data.get('currency', 'EUR'),
        category=data.get('category', 'Other'),
        transaction_type=tx_type,
        source='manual',
        state='TERMINÉ',
        notes=data.get('notes', ''),
    )
    db.session.add(tx)
    db.session.commit()
    return jsonify({'success': True, 'transaction': tx.to_dict()})


@app.route('/api/finance/transaction/<int:id>', methods=['PUT'])
def finance_update_transaction(id):
    """Update a transaction (mainly for re-categorizing)"""
    tx = FinanceTransaction.query.get_or_404(id)
    data = request.get_json()

    if 'category' in data:
        tx.category = data['category']
    if 'transaction_type' in data:
        tx.transaction_type = data['transaction_type']
    if 'description' in data:
        tx.description = data['description']
    if 'notes' in data:
        tx.notes = data['notes']
    if 'amount' in data:
        tx.amount = float(data['amount'])

    db.session.commit()
    return jsonify({'success': True, 'transaction': tx.to_dict()})


@app.route('/api/finance/transaction/<int:id>', methods=['DELETE'])
def finance_delete_transaction(id):
    """Delete a transaction"""
    tx = FinanceTransaction.query.get_or_404(id)
    db.session.delete(tx)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/finance/budget', methods=['POST'])
def finance_add_budget():
    """Add or update a budget for a category"""
    data = request.get_json()
    category = data.get('category')
    limit = float(data.get('monthly_limit', 0))

    existing = FinanceBudget.query.filter_by(category=category, is_active=True).first()
    if existing:
        existing.monthly_limit = limit
    else:
        budget = FinanceBudget(category=category, monthly_limit=limit)
        db.session.add(budget)

    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/finance/budget/<int:id>', methods=['DELETE'])
def finance_delete_budget(id):
    """Delete a budget"""
    budget = FinanceBudget.query.get_or_404(id)
    db.session.delete(budget)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/finance/recurring', methods=['POST'])
def finance_add_recurring():
    """Add a recurring cost"""
    data = request.get_json()
    rc = FinanceRecurringCost(
        name=data.get('name', ''),
        amount=float(data.get('amount', 0)),
        category=data.get('category', 'Other'),
        frequency=data.get('frequency', 'monthly'),
        day_of_month=data.get('day_of_month'),
        notes=data.get('notes', ''),
    )
    db.session.add(rc)
    db.session.commit()
    return jsonify({'success': True, 'recurring': rc.to_dict()})


@app.route('/api/finance/recurring/<int:id>', methods=['DELETE'])
def finance_delete_recurring(id):
    """Delete a recurring cost"""
    rc = FinanceRecurringCost.query.get_or_404(id)
    db.session.delete(rc)
    db.session.commit()
    return jsonify({'success': True})


# ============================================================================
# Investing feature (replaces Portfolio)
# ============================================================================

@app.route('/investing')
def investing():
    """Dashboard: YTD P&L, alerts, upcoming catalysts, top holdings, watchlist."""
    today = date.today()
    year = today.year

    # --- Owned tickers + cost basis aggregates ---
    owned = Ticker.query.filter_by(status='owned').all()
    holdings = []
    for t in owned:
        shares = 0.0
        cost_basis_eur = 0.0
        for lot in t.lots:
            if lot.remaining_shares > 1e-6:
                shares += lot.remaining_shares
                if lot.shares > 0:
                    cost_basis_eur += lot.cost_basis_eur * (lot.remaining_shares / lot.shares)
        if shares < 1e-6:
            continue
        holdings.append({
            'id': t.id,
            'symbol': t.symbol,
            'company_name': t.company_name,
            'layer': t.layer or 'Uncategorized',
            'shares': shares,
            'cost_basis_eur': cost_basis_eur,
            'avg_cost_eur_per_share': (cost_basis_eur / shares) if shares > 0 else 0,
            'currency': t.currency,
        })

    total_cost_eur = sum(h['cost_basis_eur'] for h in holdings)

    # Top 5 by cost basis (client re-ranks by live value once prices arrive)
    top_holdings = sorted(holdings, key=lambda h: h['cost_basis_eur'], reverse=True)[:5]

    # Allocation by layer (cost basis %)
    layer_totals = {}
    for h in holdings:
        layer_totals[h['layer']] = layer_totals.get(h['layer'], 0.0) + h['cost_basis_eur']
    layer_alloc = [
        {
            'layer': lyr,
            'cost_basis_eur': v,
            'pct': (v / total_cost_eur * 100) if total_cost_eur > 0 else 0,
        }
        for lyr, v in sorted(layer_totals.items(), key=lambda x: x[1], reverse=True)
    ]

    # --- YTD realized gains (LotConsumption via TradeSale) ---
    ytd_sales = (
        TradeSale.query
        .filter(db.extract('year', TradeSale.trade_date) == year)
        .all()
    )
    ytd_realized = 0.0
    gains_only = 0.0
    losses_only = 0.0
    for sale in ytd_sales:
        for cons in sale.consumptions:
            ytd_realized += cons.gain_eur
            if cons.gain_eur >= 0:
                gains_only += cons.gain_eur
            else:
                losses_only += cons.gain_eur

    EXEMPTION = 10000.0
    TAX_RATE = 0.10
    taxable = max(0.0, ytd_realized - EXEMPTION)
    tax_owed = taxable * TAX_RATE
    # Clamp to [0, EXEMPTION]: net losses don't grow headroom above the €10K cap.
    exemption_remaining = max(0.0, min(EXEMPTION, EXEMPTION - ytd_realized))
    pct_used = min(100.0, max(0.0, ytd_realized / EXEMPTION * 100)) if ytd_realized > 0 else 0.0

    # --- YTD dividends (net) ---
    ytd_dividends = (
        db.session.query(db.func.sum(Dividend.net_eur))
        .filter(db.extract('year', Dividend.payment_date) == year)
        .scalar() or 0.0
    )

    # --- Upcoming catalysts (next 30 days) ---
    in_30 = today + timedelta(days=30)
    upcoming_q = (
        db.session.query(Catalyst, Ticker)
        .join(Ticker, Catalyst.ticker_id == Ticker.id)
        .filter(
            Catalyst.catalyst_date >= today,
            Catalyst.catalyst_date <= in_30,
            Catalyst.resolved.is_(False),
        )
        .order_by(Catalyst.catalyst_date.asc())
        .all()
    )
    upcoming_catalysts = [
        {
            'symbol': t.symbol,
            'ticker_status': t.status,
            'date': c.catalyst_date.isoformat(),
            'days_until': (c.catalyst_date - today).days,
            'type': c.catalyst_type or '',
            'title': c.title,
        }
        for c, t in upcoming_q
    ]

    # --- Top watchlist by conviction ---
    top_ideas_q = (
        Ticker.query
        .filter(Ticker.status.in_(['idea', 'researching', 'ready_to_buy']))
        .filter(Ticker.conviction.isnot(None))
        .order_by(Ticker.conviction.desc())
        .limit(5)
        .all()
    )
    top_ideas = []
    for t in top_ideas_q:
        buy_z = t.entry_zones.filter_by(zone_type='buy', active=True).first()
        top_ideas.append({
            'id': t.id,
            'symbol': t.symbol,
            'company_name': t.company_name,
            'conviction': t.conviction,
            'horizon': t.horizon,
            'status': t.status,
            'buy_zone': f"{buy_z.price_low}–{buy_z.price_high} {buy_z.currency}" if buy_z else None,
        })

    # --- Active entry zones (client compares to live prices) ---
    zones_q = (
        db.session.query(EntryZone, Ticker)
        .join(Ticker, EntryZone.ticker_id == Ticker.id)
        .filter(EntryZone.active.is_(True))
        .all()
    )
    alert_zones = [
        {
            'symbol': t.symbol,
            'zone_type': z.zone_type,
            'price_low': z.price_low,
            'price_high': z.price_high,
            'currency': z.currency,
            'ticker_status': t.status,
        }
        for z, t in zones_q
    ]

    # --- Owned tickers without a thesis (server-side actionable signal) ---
    missing_thesis = [
        {'symbol': t.symbol, 'company_name': t.company_name}
        for t in owned
        if (not t.thesis or not t.thesis.strip()) and t.current_shares() > 1e-6
    ]

    # --- Recent activity (merged: buys + sells + dividends, newest first) ---
    recent_events = []
    recent_lots = (
        db.session.query(TradeLot, Ticker)
        .join(Ticker, TradeLot.ticker_id == Ticker.id)
        .order_by(TradeLot.trade_date.desc(), TradeLot.id.desc())
        .limit(10)
        .all()
    )
    for lot, t in recent_lots:
        if lot.source == 'migrated_pre_2026':
            continue  # synthetic step-up lots aren't real activity
        recent_events.append({
            'kind': 'buy',
            'symbol': t.symbol,
            'date': lot.trade_date,
            'detail': f"{lot.shares:g} shares @ {lot.price_native:.2f} {lot.currency}",
            'amount_eur': -lot.net_eur,  # debit
        })
    recent_sales = (
        db.session.query(TradeSale, Ticker)
        .join(Ticker, TradeSale.ticker_id == Ticker.id)
        .order_by(TradeSale.trade_date.desc(), TradeSale.id.desc())
        .limit(10)
        .all()
    )
    for sale, t in recent_sales:
        recent_events.append({
            'kind': 'sell',
            'symbol': t.symbol,
            'date': sale.trade_date,
            'detail': f"{sale.shares:g} shares @ {sale.price_native:.2f} {sale.currency}",
            'amount_eur': sale.proceeds_eur,
            'gain_eur': sale.realized_gain_eur,
        })
    recent_divs = (
        db.session.query(Dividend, Ticker)
        .join(Ticker, Dividend.ticker_id == Ticker.id)
        .order_by(Dividend.payment_date.desc(), Dividend.id.desc())
        .limit(10)
        .all()
    )
    for div, t in recent_divs:
        recent_events.append({
            'kind': 'dividend',
            'symbol': t.symbol,
            'date': div.payment_date,
            'detail': f"{div.shares_at_record:g} × {div.dividend_per_share_native:.4f} {div.currency}",
            'amount_eur': div.net_eur,
        })
    recent_events.sort(key=lambda e: e['date'], reverse=True)
    recent_events = recent_events[:7]
    for e in recent_events:
        e['date_iso'] = e['date'].isoformat()
        e['days_ago'] = (today - e['date']).days
        del e['date']

    return render_template(
        'investing.html',
        active_tab='dashboard',
        dash_year=year,
        dash_owned_count=len(holdings),
        dash_total_cost_eur=round(total_cost_eur, 2),
        dash_ytd_realized=round(ytd_realized, 2),
        dash_realized_gains_only=round(gains_only, 2),
        dash_realized_losses_only=round(losses_only, 2),
        dash_ytd_dividends=round(ytd_dividends, 2),
        dash_exemption=EXEMPTION,
        dash_exemption_remaining=round(exemption_remaining, 2),
        dash_tax_owed=round(tax_owed, 2),
        dash_pct_used=round(pct_used, 1),
        dash_top_holdings=top_holdings,
        dash_layer_alloc=layer_alloc,
        dash_upcoming=upcoming_catalysts,
        dash_top_ideas=top_ideas,
        dash_alert_zones=alert_zones,
        dash_missing_thesis=missing_thesis,
        dash_recent_events=recent_events,
    )


@app.route('/investing/holdings')
def investing_holdings():
    """Owned tickers with cost basis in EUR. Live prices fetched async."""
    owned = (
        Ticker.query
        .filter_by(status='owned')
        .order_by(Ticker.layer.asc().nullslast(), Ticker.symbol.asc())
        .all()
    )

    holdings = []
    for t in owned:
        shares = 0.0
        cost_basis_eur = 0.0
        for lot in t.lots:
            if lot.remaining_shares > 1e-6:
                shares += lot.remaining_shares
                # Proportional cost basis for remaining shares
                if lot.shares > 0:
                    cost_basis_eur += lot.cost_basis_eur * (lot.remaining_shares / lot.shares)
        if shares < 1e-6:
            continue  # fully sold; not a current holding

        avg_cost_eur = cost_basis_eur / shares if shares > 0 else 0
        holdings.append({
            'id': t.id,
            'symbol': t.symbol,
            'company_name': t.company_name,
            'isin': t.isin,
            'currency': t.currency,
            'layer': t.layer or 'Uncategorized',
            'shares': round(shares, 6),
            'cost_basis_eur': round(cost_basis_eur, 2),
            'avg_cost_eur_per_share': round(avg_cost_eur, 4),
            'step_up_basis_eur_per_share': t.step_up_basis_eur_per_share,
        })

    # Group by layer
    layers = {}
    for h in holdings:
        layers.setdefault(h['layer'], []).append(h)

    return render_template(
        'investing.html',
        active_tab='holdings',
        holdings=holdings,
        layers=layers,
    )


# 30-min TTL cache for live-prices response. Module-level dict shared across requests.
# Avoids re-hitting yfinance on every tab switch. Force-refresh via ?force=1.
_LIVE_PRICES_CACHE = {'data': None, 'fetched_at': None}
_LIVE_PRICES_TTL = timedelta(minutes=30)


@app.route('/api/investing/live-prices')
def investing_live_prices():
    """Fetch live prices for all owned tickers and compute EUR P&L. Cached 30 min."""
    import yfinance as yf

    now = datetime.utcnow()
    force = request.args.get('force') == '1'
    if (not force
            and _LIVE_PRICES_CACHE['data'] is not None
            and _LIVE_PRICES_CACHE['fetched_at'] is not None
            and (now - _LIVE_PRICES_CACHE['fetched_at']) < _LIVE_PRICES_TTL):
        cached_resp = dict(_LIVE_PRICES_CACHE['data'])
        cached_resp['cached'] = True
        cached_resp['cached_age_sec'] = int((now - _LIVE_PRICES_CACHE['fetched_at']).total_seconds())
        return jsonify(cached_resp)

    YF_TICKER_MAP = {
        'GSK': 'GSK.L',
        'NOVO-B': 'NOVO-B.CO',
        'CSG': 'CSG.AS',
        'EUDF': 'EUDF.DE',
    }

    owned = Ticker.query.filter_by(status='owned').all()
    if not owned:
        return jsonify({'success': True, 'stocks': [], 'totals': {}})

    # Build per-ticker aggregates from lots
    agg = {}
    for t in owned:
        shares = 0.0
        cost_basis_eur = 0.0
        for lot in t.lots:
            if lot.remaining_shares > 1e-6:
                shares += lot.remaining_shares
                if lot.shares > 0:
                    cost_basis_eur += lot.cost_basis_eur * (lot.remaining_shares / lot.shares)
        if shares > 1e-6:
            agg[t.symbol] = {
                'ticker': t,
                'shares': shares,
                'cost_basis_eur': cost_basis_eur,
            }

    # Fetch live prices + previous close in native currency
    prices = {}
    prev_closes = {}
    for symbol, data in agg.items():
        yf_symbol = YF_TICKER_MAP.get(symbol, symbol)
        try:
            info = yf.Ticker(yf_symbol).info
            p = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
            if p is not None:
                prices[symbol] = float(p)
            pc = info.get('regularMarketPreviousClose') or info.get('previousClose')
            if pc is not None:
                prev_closes[symbol] = float(pc)
        except Exception:
            pass

    # Fetch EUR/X FX rates for non-EUR currencies (1 EUR = X currency)
    fx_rates = {'EUR': 1.0}
    needed = set()
    for data in agg.values():
        cur = data['ticker'].currency or 'USD'
        base = 'GBP' if cur == 'GBp' else cur
        if base != 'EUR':
            needed.add(base)

    for base in needed:
        try:
            r = yf.Ticker(f'EUR{base}=X').info.get('regularMarketPrice') or yf.Ticker(f'EUR{base}=X').info.get('previousClose')
            if r:
                fx_rates[base] = float(r)
        except Exception:
            fx_rates[base] = None

    stock_results = []
    total_value_eur = 0.0
    total_cost_eur = 0.0
    total_with_live_price = 0.0  # for pnl_pct denominator (only tickers we got prices for)
    total_prev_value_eur = 0.0  # for today's-change aggregation (denominator + delta)
    total_today_change_eur = 0.0

    for symbol, data in agg.items():
        t = data['ticker']
        shares = data['shares']
        cost_basis_eur = data['cost_basis_eur']
        currency = t.currency or 'USD'
        live_price = prices.get(symbol)
        prev_close = prev_closes.get(symbol)

        # EUR per unit of native currency
        if currency == 'EUR':
            eur_per_unit = 1.0
        elif currency == 'GBp':
            gbp_rate = fx_rates.get('GBP')
            eur_per_unit = (1.0 / gbp_rate / 100.0) if gbp_rate else None
        else:
            r = fx_rates.get(currency)
            eur_per_unit = (1.0 / r) if r else None

        row = {
            'symbol': symbol,
            'company_name': t.company_name,
            'currency': currency,
            'shares': round(shares, 6),
            'cost_basis_eur': round(cost_basis_eur, 2),
            'avg_cost_eur_per_share': round(cost_basis_eur / shares, 4) if shares > 0 else 0,
            'live_price_native': live_price,
            'prev_close_native': prev_close,
            'layer': t.layer,
        }
        if live_price is not None and eur_per_unit is not None:
            live_value_eur = shares * live_price * eur_per_unit
            pnl_eur = live_value_eur - cost_basis_eur
            pnl_pct = (pnl_eur / cost_basis_eur * 100) if cost_basis_eur > 0 else 0
            row['live_value_eur'] = round(live_value_eur, 2)
            row['pnl_eur'] = round(pnl_eur, 2)
            row['pnl_pct'] = round(pnl_pct, 1)
            total_value_eur += live_value_eur
            total_cost_eur += cost_basis_eur
            total_with_live_price += cost_basis_eur

            # Today's change vs previous close
            if prev_close is not None:
                today_change_native = live_price - prev_close
                today_change_eur = shares * today_change_native * eur_per_unit
                prev_value_eur = shares * prev_close * eur_per_unit
                today_change_pct = (today_change_native / prev_close * 100) if prev_close > 0 else 0
                row['today_change_eur'] = round(today_change_eur, 2)
                row['today_change_pct'] = round(today_change_pct, 2)
                total_today_change_eur += today_change_eur
                total_prev_value_eur += prev_value_eur
        else:
            row['error'] = 'Price unavailable' if live_price is None else 'FX unavailable'
            # Still count cost basis in total cost
            total_cost_eur += cost_basis_eur

        stock_results.append(row)

    # Sort by value descending
    stock_results.sort(key=lambda r: r.get('live_value_eur', 0), reverse=True)

    total_pnl_eur = total_value_eur - total_with_live_price
    total_pnl_pct = (total_pnl_eur / total_with_live_price * 100) if total_with_live_price > 0 else 0
    total_today_change_pct = (total_today_change_eur / total_prev_value_eur * 100) if total_prev_value_eur > 0 else 0

    response_data = {
        'success': True,
        'stocks': stock_results,
        'totals': {
            'total_value_eur': round(total_value_eur, 2),
            'total_cost_eur': round(total_cost_eur, 2),
            'total_pnl_eur': round(total_pnl_eur, 2),
            'total_pnl_pct': round(total_pnl_pct, 1),
            'total_today_change_eur': round(total_today_change_eur, 2),
            'total_today_change_pct': round(total_today_change_pct, 2),
        },
        'fx_rates': {k: round(v, 6) if v else None for k, v in fx_rates.items()},
    }
    _LIVE_PRICES_CACHE['data'] = response_data
    _LIVE_PRICES_CACHE['fetched_at'] = now
    fresh = dict(response_data)
    fresh['cached'] = False
    fresh['cached_age_sec'] = 0
    return jsonify(fresh)


@app.route('/investing/watchlist')
def investing_watchlist():
    """Ideas / watchlist tickers, grouped by layer, sorted by conviction."""
    ideas = (
        Ticker.query
        .filter(Ticker.status.in_(['idea', 'researching', 'ready_to_buy']))
        .order_by(
            Ticker.conviction.desc().nullslast(),
            Ticker.layer.asc().nullslast(),
            Ticker.symbol.asc(),
        )
        .all()
    )

    # Group by layer
    layers = {}
    for t in ideas:
        layer = t.layer or 'Uncategorized'
        layers.setdefault(layer, []).append({
            'id': t.id,
            'symbol': t.symbol,
            'company_name': t.company_name,
            'conviction': t.conviction,
            'horizon': t.horizon,
            'status': t.status,
            'currency': t.currency,
            'has_thesis': bool(t.thesis),
            'next_catalyst': None,  # filled in below
            'buy_zone': None,
        })

    # Attach next catalyst + active buy zone per ticker
    from datetime import date as _date
    today_d = _date.today()
    for t in ideas:
        next_c = (
            t.catalysts.filter(Catalyst.catalyst_date >= today_d, Catalyst.resolved.is_(False))
            .order_by(Catalyst.catalyst_date.asc())
            .first()
        )
        buy_z = (
            t.entry_zones.filter_by(zone_type='buy', active=True)
            .order_by(EntryZone.price_low.asc())
            .first()
        )
        # find the dict we already built and patch it
        for h in layers.get(t.layer or 'Uncategorized', []):
            if h['id'] == t.id:
                if next_c:
                    h['next_catalyst'] = {'date': next_c.catalyst_date.isoformat(), 'title': next_c.title}
                if buy_z:
                    h['buy_zone'] = f"{buy_z.price_low}–{buy_z.price_high} {buy_z.currency}"
                break

    return render_template(
        'investing.html',
        active_tab='watchlist',
        watchlist_layers=layers,
        watchlist_count=len(ideas),
    )


# SPY close-price cache for retrospective grading. Daily prices never change, so this
# can grow indefinitely without staleness issues. Keyed by ISO date string.
_SPY_CLOSE_CACHE = {}


def _get_spy_close(d):
    """Return SPY close (USD) on or just before date d. None if unavailable."""
    import yfinance as yf
    from datetime import timedelta as _td
    key = d.isoformat()
    if key in _SPY_CLOSE_CACHE:
        return _SPY_CLOSE_CACHE[key]
    # Fetch a small window around the date — handles weekends/holidays
    try:
        start = d - _td(days=5)
        end = d + _td(days=2)
        hist = yf.Ticker('SPY').history(start=start.isoformat(), end=end.isoformat())
        if hist.empty:
            _SPY_CLOSE_CACHE[key] = None
            return None
        # Take the last close on or before d
        hist = hist[hist.index.date <= d]
        if hist.empty:
            _SPY_CLOSE_CACHE[key] = None
            return None
        close = float(hist['Close'].iloc[-1])
        _SPY_CLOSE_CACHE[key] = close
        return close
    except Exception:
        _SPY_CLOSE_CACHE[key] = None
        return None


@app.route('/investing/journal')
def investing_journal():
    """Chronological feed of every buy/sell/dividend with reasoning."""
    today = date.today()
    requested_year = request.args.get('year', type=int) or today.year
    symbol_filter = request.args.get('symbol', '').strip().upper() or None

    def _within(d):
        return d.year == requested_year

    # Collect events from all three tables
    events = []
    cashflow_in = 0.0
    cashflow_out = 0.0

    lot_q = (
        db.session.query(TradeLot, Ticker)
        .join(Ticker, TradeLot.ticker_id == Ticker.id)
    )
    if symbol_filter:
        lot_q = lot_q.filter(Ticker.symbol == symbol_filter)
    for lot, t in lot_q.all():
        if lot.source == 'migrated_pre_2026':
            continue  # synthetic step-up lots aren't real journal entries
        if not _within(lot.trade_date):
            continue
        events.append({
            'kind': 'buy',
            'event_id': lot.id,
            'symbol': t.symbol,
            'company_name': t.company_name,
            'date': lot.trade_date,
            'shares': lot.shares,
            'price_native': lot.price_native,
            'currency': lot.currency,
            'amount_eur': lot.net_eur,
            'gain_eur': None,
            'reasoning': lot.reasoning or '',
        })
        cashflow_out += lot.net_eur

    sale_q = (
        db.session.query(TradeSale, Ticker)
        .join(Ticker, TradeSale.ticker_id == Ticker.id)
    )
    if symbol_filter:
        sale_q = sale_q.filter(Ticker.symbol == symbol_filter)
    for sale, t in sale_q.all():
        if not _within(sale.trade_date):
            continue
        events.append({
            'kind': 'sell',
            'event_id': sale.id,
            'symbol': t.symbol,
            'company_name': t.company_name,
            'date': sale.trade_date,
            'shares': sale.shares,
            'price_native': sale.price_native,
            'currency': sale.currency,
            'amount_eur': sale.proceeds_eur,
            'gain_eur': sale.realized_gain_eur,
            'reasoning': sale.reasoning or '',
        })
        cashflow_in += sale.proceeds_eur

    div_q = (
        db.session.query(Dividend, Ticker)
        .join(Ticker, Dividend.ticker_id == Ticker.id)
    )
    if symbol_filter:
        div_q = div_q.filter(Ticker.symbol == symbol_filter)
    for d, t in div_q.all():
        if not _within(d.payment_date):
            continue
        events.append({
            'kind': 'dividend',
            'event_id': d.id,
            'symbol': t.symbol,
            'company_name': t.company_name,
            'date': d.payment_date,
            'shares': d.shares_at_record,
            'price_native': d.dividend_per_share_native,
            'currency': d.currency,
            'amount_eur': d.net_eur,
            'gain_eur': None,
            'reasoning': '',  # dividends have no reasoning field
        })
        cashflow_in += d.net_eur

    # Sort newest first
    events.sort(key=lambda e: (e['date'], e['kind']), reverse=True)
    for e in events:
        e['date_iso'] = e['date'].isoformat()

    # Counts by kind
    counts = {'buy': 0, 'sell': 0, 'dividend': 0}
    for e in events:
        counts[e['kind']] += 1

    # Year list — every year that has any event
    all_years = set()
    for lot in TradeLot.query.filter(TradeLot.source != 'migrated_pre_2026').all():
        all_years.add(lot.trade_date.year)
    for s in TradeSale.query.all():
        all_years.add(s.trade_date.year)
    for d in Dividend.query.all():
        all_years.add(d.payment_date.year)
    years = sorted(all_years, reverse=True) or [today.year]

    # Symbols list for filter dropdown (tickers active in any year)
    all_symbols = sorted({t.symbol for t in Ticker.query.filter(
        Ticker.status.in_(['owned', 'sold'])
    ).all()})

    # Retrospective grading vs SPY for every sale in the requested year.
    # Comparison period: from the earliest consumed lot's trade_date to the sale_date.
    # Returns are computed in EUR for "your return" and converted SPY into EUR using
    # the lot's fx_rate (best available; falls back to USD-only if absent).
    grading_rows = []
    grading_sales = (
        db.session.query(TradeSale, Ticker)
        .join(Ticker, TradeSale.ticker_id == Ticker.id)
        .filter(db.extract('year', TradeSale.trade_date) == requested_year)
    )
    if symbol_filter:
        grading_sales = grading_sales.filter(Ticker.symbol == symbol_filter)
    for sale, t in grading_sales.all():
        consumptions = list(sale.consumptions)
        if not consumptions:
            continue
        cost_total = sum(c.cost_basis_eur for c in consumptions)
        proceeds = sale.proceeds_eur or 0
        your_return_eur = proceeds - cost_total
        your_return_pct = (your_return_eur / cost_total * 100) if cost_total > 0 else 0
        # Buy reference date = earliest consumed lot
        buy_dates = []
        for c in consumptions:
            lot = TradeLot.query.get(c.lot_id)
            if lot:
                buy_dates.append(lot.trade_date)
        if not buy_dates:
            continue
        buy_date = min(buy_dates)
        sell_date = sale.trade_date
        days_held = (sell_date - buy_date).days

        spy_buy = _get_spy_close(buy_date)
        spy_sell = _get_spy_close(sell_date)
        spy_return_pct = None
        alpha_pct = None
        if spy_buy and spy_sell and spy_buy > 0:
            spy_return_pct = (spy_sell - spy_buy) / spy_buy * 100
            alpha_pct = your_return_pct - spy_return_pct

        grading_rows.append({
            'symbol': t.symbol,
            'buy_date': buy_date.isoformat(),
            'sell_date': sell_date.isoformat(),
            'days_held': days_held,
            'cost_eur': round(cost_total, 2),
            'proceeds_eur': round(proceeds, 2),
            'your_return_eur': round(your_return_eur, 2),
            'your_return_pct': round(your_return_pct, 2),
            'spy_buy': round(spy_buy, 2) if spy_buy else None,
            'spy_sell': round(spy_sell, 2) if spy_sell else None,
            'spy_return_pct': round(spy_return_pct, 2) if spy_return_pct is not None else None,
            'alpha_pct': round(alpha_pct, 2) if alpha_pct is not None else None,
        })
    grading_rows.sort(key=lambda r: r['sell_date'], reverse=True)

    return render_template(
        'investing.html',
        active_tab='journal',
        jrn_events=events,
        jrn_year=requested_year,
        jrn_years=years,
        jrn_symbol=symbol_filter,
        jrn_all_symbols=all_symbols,
        jrn_counts=counts,
        jrn_cashflow_in=round(cashflow_in, 2),
        jrn_cashflow_out=round(cashflow_out, 2),
        jrn_cashflow_net=round(cashflow_in - cashflow_out, 2),
        jrn_grading_rows=grading_rows,
    )


@app.route('/api/investing/journal/reasoning/<kind>/<int:event_id>', methods=['PATCH'])
def investing_journal_reasoning(kind, event_id):
    """Update the reasoning field on a buy lot or sell. Dividends have no reasoning."""
    if kind not in ('buy', 'sell'):
        return jsonify({'error': 'reasoning only supported for buy/sell'}), 400
    data = request.get_json() or {}
    text = (data.get('reasoning') or '').strip() or None
    if kind == 'buy':
        obj = TradeLot.query.get_or_404(event_id)
    else:
        obj = TradeSale.query.get_or_404(event_id)
    obj.reasoning = text
    db.session.commit()
    return jsonify({'success': True})


@app.route('/investing/dividends')
def investing_dividends():
    """Dividend tracker: totals, per-ticker breakdown, monthly view."""
    today = date.today()

    # All dividends, joined with ticker for display
    rows = (
        db.session.query(Dividend, Ticker)
        .join(Ticker, Dividend.ticker_id == Ticker.id)
        .order_by(Dividend.payment_date.desc(), Dividend.id.desc())
        .all()
    )

    all_divs = [
        {
            'id': d.id,
            'symbol': t.symbol,
            'company_name': t.company_name,
            'payment_date': d.payment_date,
            'ex_date': d.ex_date,
            'shares': d.shares_at_record,
            'dps_native': d.dividend_per_share_native,
            'currency': d.currency,
            'gross_eur': d.gross_eur,
            'belgian_withholding_eur': d.belgian_withholding_eur or 0,
            'foreign_withholding_eur': d.foreign_withholding_eur or 0,
            'fees_eur': d.fees_eur or 0,
            'net_eur': d.net_eur,
        }
        for d, t in rows
    ]

    # YTD vs lifetime totals
    ytd_total = sum(d['net_eur'] for d in all_divs if d['payment_date'].year == today.year)
    lifetime_total = sum(d['net_eur'] for d in all_divs)
    ytd_gross = sum(d['gross_eur'] for d in all_divs if d['payment_date'].year == today.year and d['gross_eur'])
    ytd_belgian_wh = sum(d['belgian_withholding_eur'] for d in all_divs if d['payment_date'].year == today.year)
    ytd_foreign_wh = sum(d['foreign_withholding_eur'] for d in all_divs if d['payment_date'].year == today.year)

    # Per-ticker breakdown (sorted by total net descending)
    by_ticker = {}
    for d in all_divs:
        slot = by_ticker.setdefault(d['symbol'], {
            'symbol': d['symbol'],
            'company_name': d['company_name'],
            'count': 0,
            'total_net_eur': 0.0,
            'total_gross_eur': 0.0,
            'last_payment': None,
            'first_payment': None,
        })
        slot['count'] += 1
        slot['total_net_eur'] += d['net_eur']
        slot['total_gross_eur'] += d['gross_eur'] or 0
        if slot['last_payment'] is None or d['payment_date'] > slot['last_payment']:
            slot['last_payment'] = d['payment_date']
        if slot['first_payment'] is None or d['payment_date'] < slot['first_payment']:
            slot['first_payment'] = d['payment_date']
    ticker_breakdown = sorted(by_ticker.values(), key=lambda r: r['total_net_eur'], reverse=True)

    # Yield-on-cost per ticker (annualized if we have ≥6 months of payments; otherwise raw)
    cost_basis_by_ticker = {}
    for t in Ticker.query.all():
        cost = 0.0
        for lot in t.lots:
            if lot.remaining_shares > 1e-6 and lot.shares > 0:
                cost += lot.cost_basis_eur * (lot.remaining_shares / lot.shares)
        if cost > 0:
            cost_basis_by_ticker[t.symbol] = cost
    for tb in ticker_breakdown:
        cost = cost_basis_by_ticker.get(tb['symbol'])
        if cost and cost > 0:
            tb['cost_basis_eur'] = cost
            tb['yield_on_cost_pct'] = (tb['total_net_eur'] / cost) * 100
        else:
            tb['cost_basis_eur'] = None
            tb['yield_on_cost_pct'] = None

    # Monthly breakdown (YYYY-MM -> total net) for the current year
    monthly = {}
    for d in all_divs:
        if d['payment_date'].year != today.year:
            continue
        key = d['payment_date'].strftime('%Y-%m')
        monthly[key] = monthly.get(key, 0.0) + d['net_eur']
    monthly_list = [{'month': k, 'total_net_eur': v} for k, v in sorted(monthly.items())]
    monthly_max = max((m['total_net_eur'] for m in monthly_list), default=0)

    # Years that have any dividend data (for context)
    years = sorted({d['payment_date'].year for d in all_divs}, reverse=True)

    return render_template(
        'investing.html',
        active_tab='dividends',
        div_year=today.year,
        div_years=years,
        div_ytd_net=round(ytd_total, 2),
        div_lifetime_net=round(lifetime_total, 2),
        div_ytd_gross=round(ytd_gross, 2),
        div_ytd_belgian_wh=round(ytd_belgian_wh, 2),
        div_ytd_foreign_wh=round(ytd_foreign_wh, 2),
        div_ytd_count=sum(1 for d in all_divs if d['payment_date'].year == today.year),
        div_payers_ytd=len({d['symbol'] for d in all_divs if d['payment_date'].year == today.year}),
        div_ticker_breakdown=ticker_breakdown,
        div_monthly=monthly_list,
        div_monthly_max=monthly_max,
        div_recent=all_divs[:20],
    )


@app.route('/investing/tax')
def investing_tax():
    """Belgian capital gains: YTD realized gains, €10K exemption, 10% tax estimate."""
    today = date.today()
    requested_year = request.args.get('year', type=int) or today.year

    # All sales in the requested year, with their consumptions
    sales = (
        TradeSale.query
        .filter(db.extract('year', TradeSale.trade_date) == requested_year)
        .order_by(TradeSale.trade_date.asc(), TradeSale.id.asc())
        .all()
    )

    # Build flat per-consumption rows for the table
    detail_rows = []
    total_proceeds = 0.0
    total_cost = 0.0
    total_gain = 0.0
    realized_gains_only = 0.0  # sum of positive gains
    realized_losses_only = 0.0  # sum of negative gains (kept negative)
    for sale in sales:
        ticker = Ticker.query.get(sale.ticker_id)
        for cons in sale.consumptions:
            lot = TradeLot.query.get(cons.lot_id)
            detail_rows.append({
                'sale_id': sale.id,
                'ticker': ticker.symbol if ticker else '?',
                'isin': ticker.isin if ticker else None,
                'sale_date': sale.trade_date,
                'lot_acq_date': lot.trade_date if lot else None,
                'lot_source': lot.source if lot else None,
                'shares': cons.shares_consumed,
                'cost_basis_eur': cons.cost_basis_eur,
                'proceeds_eur': cons.proceeds_eur,
                'gain_eur': cons.gain_eur,
                'lot_id': lot.id if lot else None,
            })
            total_proceeds += cons.proceeds_eur
            total_cost += cons.cost_basis_eur
            total_gain += cons.gain_eur
            if cons.gain_eur >= 0:
                realized_gains_only += cons.gain_eur
            else:
                realized_losses_only += cons.gain_eur

    # Belgian tax math (Jan 1 2026 rules)
    EXEMPTION = 10000.0
    TAX_RATE = 0.10
    taxable = max(0.0, total_gain - EXEMPTION)
    tax_owed = taxable * TAX_RATE
    pct_used = min(100.0, max(0.0, total_gain / EXEMPTION * 100)) if total_gain > 0 else 0.0

    # Years that have sales (for the year selector)
    years = sorted({
        s.trade_date.year for s in TradeSale.query.all()
    }, reverse=True) or [today.year]

    # Loss-harvesting candidates: owned tickers, cost-basis side computed server-side,
    # live prices filled in by JS so we don't block on yfinance during page render.
    owned = Ticker.query.filter_by(status='owned').all()
    harvest_rows = []
    for t in owned:
        shares = 0.0
        cost_basis_eur = 0.0
        for lot in t.lots:
            if lot.remaining_shares > 1e-6:
                shares += lot.remaining_shares
                if lot.shares > 0:
                    cost_basis_eur += lot.cost_basis_eur * (lot.remaining_shares / lot.shares)
        if shares < 1e-6:
            continue
        harvest_rows.append({
            'symbol': t.symbol,
            'company_name': t.company_name,
            'shares': round(shares, 6),
            'cost_basis_eur': round(cost_basis_eur, 2),
            'avg_cost': round(cost_basis_eur / shares, 4) if shares > 0 else 0,
            'currency': t.currency,
        })

    # Exemption headroom: how much realized gain you can still book tax-free this year
    exemption_headroom = max(0.0, EXEMPTION - total_gain)

    return render_template(
        'investing.html',
        active_tab='tax',
        tax_year=requested_year,
        tax_years=years,
        tax_detail_rows=detail_rows,
        tax_total_proceeds=round(total_proceeds, 2),
        tax_total_cost=round(total_cost, 2),
        tax_total_gain=round(total_gain, 2),
        tax_gains_only=round(realized_gains_only, 2),
        tax_losses_only=round(realized_losses_only, 2),
        tax_exemption=EXEMPTION,
        tax_rate=TAX_RATE,
        tax_exemption_headroom=round(exemption_headroom, 2),
        tax_harvest_rows=harvest_rows,
        tax_taxable=round(taxable, 2),
        tax_owed=round(tax_owed, 2),
        tax_pct_used=round(pct_used, 1),
    )


@app.route('/investing/import', methods=['GET', 'POST'])
def investing_import():
    """Upload Bolero PDFs and import as trades/dividends."""
    import_results = None
    if request.method == 'POST':
        from scripts.bolero_import import import_pdf
        import tempfile
        import shutil

        bolero_dir = os.path.join(os.path.dirname(__file__), 'Investing', 'Bolero reports')
        os.makedirs(bolero_dir, exist_ok=True)

        files = request.files.getlist('pdfs')
        results = []
        for f in files:
            if not f.filename:
                continue
            if not f.filename.lower().endswith('.pdf'):
                results.append({'file': f.filename, 'status': 'error', 'reason': 'not a PDF'})
                continue

            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                f.save(tmp.name)
                tmp_path = tmp.name
            try:
                r = import_pdf(tmp_path, dry_run=False)
                r['file'] = f.filename
                # Save a copy to the Bolero reports folder if import was successful (not duplicate or error)
                if r.get('status') == 'imported':
                    dest = os.path.join(bolero_dir, f.filename)
                    if not os.path.exists(dest):
                        shutil.copy2(tmp_path, dest)
                results.append(r)
            except Exception as e:
                results.append({'file': f.filename, 'status': 'error', 'reason': str(e)})
                db.session.rollback()
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            results.append({'status': 'error', 'reason': f'commit failed: {e}'})
        import_results = results

    return render_template('investing.html', active_tab='import', import_results=import_results)


@app.route('/investing/ticker/<symbol>')
def investing_ticker_detail(symbol):
    """Per-ticker research + journal + chat page."""
    ticker = Ticker.query.filter_by(symbol=symbol).first_or_404()

    # Aggregate position info
    lots = list(ticker.lots.order_by(TradeLot.trade_date.asc(), TradeLot.id.asc()))
    sales = list(ticker.sales.order_by(TradeSale.trade_date.desc(), TradeSale.id.desc()))
    dividends = list(ticker.dividends.order_by(Dividend.payment_date.desc()))
    zones = list(ticker.entry_zones.order_by(EntryZone.price_low.asc()))
    catalysts = list(ticker.catalysts.order_by(Catalyst.catalyst_date.asc()))
    risks = list(ticker.risks.filter_by(active=True).order_by(Risk.severity.desc()))

    open_shares = sum(l.remaining_shares for l in lots if l.remaining_shares > 1e-6)
    total_cost_basis_eur = sum(
        (l.cost_basis_eur * l.remaining_shares / l.shares) if l.shares > 0 else 0
        for l in lots if l.remaining_shares > 1e-6
    )
    avg_cost_eur = (total_cost_basis_eur / open_shares) if open_shares > 0 else 0

    realized_gain_eur = sum((s.realized_gain_eur or 0) for s in sales)
    total_dividends_eur = sum((d.net_eur or 0) for d in dividends)

    # YTD realized across ALL tickers (used by the unrealized-PnL card to compute
    # what selling this position would do to the user's total tax position).
    today = date.today()
    ytd_realized_total_eur = (
        db.session.query(db.func.coalesce(db.func.sum(TradeSale.realized_gain_eur), 0))
        .filter(db.extract('year', TradeSale.trade_date) == today.year)
        .scalar()
    ) or 0.0

    return render_template(
        'ticker_detail.html',
        ticker=ticker,
        lots=lots,
        sales=sales,
        dividends=dividends,
        zones=zones,
        catalysts=catalysts,
        risks=risks,
        open_shares=round(open_shares, 6),
        total_cost_basis_eur=round(total_cost_basis_eur, 2),
        avg_cost_eur=round(avg_cost_eur, 4),
        realized_gain_eur=round(realized_gain_eur, 2),
        total_dividends_eur=round(total_dividends_eur, 2),
        ytd_realized_total_eur=round(ytd_realized_total_eur, 2),
    )


@app.route('/api/investing/ticker/<int:ticker_id>', methods=['PATCH'])
def investing_ticker_update(ticker_id):
    """Update editable ticker fields."""
    t = Ticker.query.get_or_404(ticker_id)
    data = request.get_json() or {}
    for field in ('thesis', 'conviction', 'horizon', 'layer', 'status'):
        if field in data:
            setattr(t, field, data[field] or None)
    db.session.commit()
    return jsonify({'success': True, 'ticker': t.to_dict()})


@app.route('/api/investing/ticker/<int:ticker_id>/zone', methods=['POST'])
def investing_zone_create(ticker_id):
    Ticker.query.get_or_404(ticker_id)
    data = request.get_json() or {}
    z = EntryZone(
        ticker_id=ticker_id,
        zone_type=data.get('zone_type', 'buy'),
        price_low=float(data.get('price_low', 0)),
        price_high=float(data.get('price_high', 0)),
        currency=data.get('currency', 'USD'),
        notes=data.get('notes'),
    )
    db.session.add(z)
    db.session.commit()
    return jsonify({'success': True, 'zone': z.to_dict()})


@app.route('/api/investing/zone/<int:zone_id>', methods=['DELETE'])
def investing_zone_delete(zone_id):
    z = EntryZone.query.get_or_404(zone_id)
    db.session.delete(z)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/investing/ticker/<int:ticker_id>/risk', methods=['POST'])
def investing_risk_create(ticker_id):
    Ticker.query.get_or_404(ticker_id)
    data = request.get_json() or {}
    r = Risk(
        ticker_id=ticker_id,
        description=data.get('description', ''),
        severity=data.get('severity', 'medium'),
    )
    db.session.add(r)
    db.session.commit()
    return jsonify({'success': True, 'risk': r.to_dict()})


@app.route('/api/investing/risk/<int:risk_id>', methods=['DELETE'])
def investing_risk_delete(risk_id):
    r = Risk.query.get_or_404(risk_id)
    db.session.delete(r)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/investing/ticker/<int:ticker_id>/catalyst', methods=['POST'])
def investing_catalyst_create(ticker_id):
    Ticker.query.get_or_404(ticker_id)
    data = request.get_json() or {}
    date_str = (data.get('catalyst_date') or '').strip()
    if not date_str:
        return jsonify({'error': 'catalyst_date required (YYYY-MM-DD)'}), 400
    try:
        catalyst_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': f'invalid catalyst_date format: {date_str!r} (expected YYYY-MM-DD)'}), 400
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'title required'}), 400
    c = Catalyst(
        ticker_id=ticker_id,
        catalyst_date=catalyst_date,
        catalyst_type=data.get('catalyst_type'),
        title=title,
        description=data.get('description'),
    )
    db.session.add(c)
    db.session.commit()
    return jsonify({'success': True, 'catalyst': c.to_dict()})


@app.route('/api/investing/catalyst/<int:catalyst_id>', methods=['DELETE'])
def investing_catalyst_delete(catalyst_id):
    c = Catalyst.query.get_or_404(catalyst_id)
    db.session.delete(c)
    db.session.commit()
    return jsonify({'success': True})


# ----------------------------------------------------------------------------
# Chat-per-ticker with Claude (prompt caching enabled)
# ----------------------------------------------------------------------------

CHAT_SYSTEM_INSTRUCTION = """You are Noé's personal investing assistant for a specific stock he's tracking in his app.

Noé is an experienced retail investor based in Belgium. He's subject to the new Belgian capital gains tax (effective Jan 1, 2026): 10% on net realized gains above €10,000 per year. Cost basis for pre-2026 holdings is the Dec 31, 2025 close.

Be direct and concise. Reference his thesis and risks below when relevant — don't repeat them back to him. Don't hedge with generic financial-advice disclaimers unless something is genuinely speculative. Build on what he already knows.

Format responses in markdown when useful (lists, bold for key numbers). Keep replies focused on this specific ticker unless he asks otherwise.

---
## Ticker context
"""


def build_ticker_context(ticker):
    """Build a markdown context block for the chat system prompt."""
    parts = []
    parts.append(f"### {ticker.symbol} — {ticker.company_name}")
    meta = []
    if ticker.isin:
        meta.append(f"ISIN {ticker.isin}")
    if ticker.exchange:
        meta.append(f"exchange {ticker.exchange}")
    meta.append(f"currency {ticker.currency}")
    meta.append(f"status {ticker.status}")
    parts.append(' · '.join(meta))
    parts.append("")

    # Position
    open_lots = [l for l in ticker.lots if l.remaining_shares > 1e-6]
    if open_lots:
        open_shares = sum(l.remaining_shares for l in open_lots)
        cost_basis = sum(
            (l.cost_basis_eur * l.remaining_shares / l.shares) if l.shares > 0 else 0
            for l in open_lots
        )
        avg = cost_basis / open_shares if open_shares > 0 else 0
        parts.append("**Position:**")
        parts.append(f"- Open shares: {open_shares:g}")
        parts.append(f"- Avg cost (EUR): €{avg:,.2f}/share")
        parts.append(f"- Total cost basis (EUR): €{cost_basis:,.2f}")
        if ticker.step_up_basis_eur_per_share:
            parts.append(f"- Step-up basis (Dec 31, 2025 EUR/share): €{ticker.step_up_basis_eur_per_share:.2f} — used for tax cost basis on shares owned at year-end 2025")
        parts.append("")

    # User's view
    if ticker.thesis:
        parts.append("**Thesis:**")
        parts.append(ticker.thesis)
        parts.append("")
    view_meta = []
    if ticker.conviction:
        view_meta.append(f"conviction {ticker.conviction}/10")
    if ticker.horizon:
        view_meta.append(f"horizon {ticker.horizon}")
    if ticker.layer:
        view_meta.append(f"sector {ticker.layer}")
    if view_meta:
        parts.append(' · '.join(view_meta))
        parts.append("")

    # Entry zones
    zones = list(ticker.entry_zones.filter_by(active=True))
    if zones:
        parts.append("**Entry zones (active):**")
        for z in zones:
            line = f"- {z.zone_type.upper()}: {z.price_low}–{z.price_high} {z.currency}"
            if z.notes:
                line += f" — {z.notes}"
            parts.append(line)
        parts.append("")

    # Active risks
    risks = list(ticker.risks.filter_by(active=True))
    if risks:
        parts.append("**Risks (active):**")
        for r in risks:
            parts.append(f"- [{r.severity}] {r.description}")
        parts.append("")

    # Upcoming catalysts
    today_d = date.today()
    upcoming = ticker.catalysts.filter(Catalyst.catalyst_date >= today_d).order_by(Catalyst.catalyst_date.asc()).limit(8).all()
    if upcoming:
        parts.append("**Upcoming catalysts:**")
        for c in upcoming:
            parts.append(f"- {c.catalyst_date.isoformat()} ({c.catalyst_type or 'other'}): {c.title}")
        parts.append("")

    # Recent sales (with realized gains)
    recent_sales = ticker.sales.order_by(TradeSale.trade_date.desc()).limit(5).all()
    if recent_sales:
        parts.append("**Recent sales:**")
        for s in recent_sales:
            gain = s.realized_gain_eur or 0
            sign = '+' if gain >= 0 else ''
            parts.append(
                f"- {s.trade_date.isoformat()}: sold {s.shares:g} @ {s.price_native:g} {s.currency} "
                f"(proceeds €{s.proceeds_eur:.2f}, realized {sign}€{gain:.2f})"
            )
        parts.append("")

    # Recent dividends
    recent_divs = ticker.dividends.order_by(Dividend.payment_date.desc()).limit(3).all()
    if recent_divs:
        parts.append("**Recent dividends:**")
        for d in recent_divs:
            parts.append(f"- {d.payment_date.isoformat()}: net €{d.net_eur or 0:.2f}")
        parts.append("")

    return "\n".join(parts)


@app.route('/api/investing/ticker/<int:ticker_id>/chat', methods=['POST'])
def investing_ticker_chat(ticker_id):
    """Send a message to Claude with the ticker as context. Uses prompt caching."""
    if not claude_client:
        return jsonify({'error': 'Claude API not configured'}), 500

    ticker = Ticker.query.get_or_404(ticker_id)
    data = request.get_json() or {}
    user_message = (data.get('message') or '').strip()
    if not user_message:
        return jsonify({'error': 'Empty message'}), 400

    # Build cacheable system context
    context_text = CHAT_SYSTEM_INSTRUCTION + build_ticker_context(ticker)

    # Cap context sent to Claude to the last N messages (15 user+assistant pairs).
    # The full history stays in the DB and is still shown in the UI via the GET endpoint;
    # only the API call's context window is bounded so a long-running conversation
    # can't grow unbounded and eventually 500 from token-limit errors.
    MAX_CHAT_CONTEXT = 30
    prior = (
        TickerChatMessage.query
        .filter_by(ticker_id=ticker.id)
        .order_by(TickerChatMessage.created_at.desc())
        .limit(MAX_CHAT_CONTEXT)
        .all()
    )
    prior.reverse()  # back to chronological order
    # Persist code always adds messages as (user, assistant) pairs, so the trimmed
    # window will start with a user message and end with an assistant message.
    messages = [{"role": m.role, "content": m.content} for m in prior]
    messages.append({"role": "user", "content": user_message})

    try:
        response = call_claude(
            'investing', 'ticker_chat',
            model='claude-sonnet-4-6',
            max_tokens=1024,
            system=[
                {"type": "text", "text": context_text, "cache_control": {"type": "ephemeral"}}
            ],
            messages=messages,
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    assistant_text = response.content[0].text

    # Persist both messages
    db.session.add(TickerChatMessage(ticker_id=ticker.id, role='user', content=user_message))
    db.session.add(TickerChatMessage(ticker_id=ticker.id, role='assistant', content=assistant_text))
    db.session.commit()

    return jsonify({
        'success': True,
        'reply': assistant_text,
        'usage': {
            'input_tokens': response.usage.input_tokens,
            'output_tokens': response.usage.output_tokens,
            'cache_creation_input_tokens': getattr(response.usage, 'cache_creation_input_tokens', 0) or 0,
            'cache_read_input_tokens': getattr(response.usage, 'cache_read_input_tokens', 0) or 0,
        },
    })


@app.route('/api/investing/ticker/<int:ticker_id>/chat', methods=['GET'])
def investing_ticker_chat_history(ticker_id):
    """Return the chat history for a ticker."""
    Ticker.query.get_or_404(ticker_id)
    messages = (
        TickerChatMessage.query
        .filter_by(ticker_id=ticker_id)
        .order_by(TickerChatMessage.created_at.asc())
        .all()
    )
    return jsonify({'messages': [m.to_dict() for m in messages]})


@app.route('/api/investing/ticker/<int:ticker_id>/chat/clear', methods=['POST'])
def investing_ticker_chat_clear(ticker_id):
    """Wipe chat history for a ticker."""
    Ticker.query.get_or_404(ticker_id)
    TickerChatMessage.query.filter_by(ticker_id=ticker_id).delete()
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/investing/ticker/<int:ticker_id>/second-opinion-prompt')
def investing_ticker_second_opinion(ticker_id):
    """Build a copy-paste-ready prompt for claude.ai to critique this position."""
    t = Ticker.query.get_or_404(ticker_id)
    shares = sum(l.remaining_shares for l in t.lots if l.remaining_shares > 1e-6)
    cost = sum(
        l.cost_basis_eur * l.remaining_shares / l.shares
        for l in t.lots
        if l.remaining_shares > 1e-6 and l.shares > 0
    )

    out = []
    out.append(
        "You are a senior investment analyst. I hold the following position and want "
        "a critical, skeptical second opinion. Your job is NOT to validate my thinking — "
        "push back on weak assumptions, identify what I am missing, and tell me what a smart "
        "bear on this stock would say."
    )
    out.append("")
    out.append(f"=== POSITION: {t.symbol} ({t.company_name}) ===")
    out.append(
        f"Status: {t.status} | Native currency: {t.currency} | "
        f"Exchange: {t.exchange or '?'} | ISIN: {t.isin or '?'}"
    )
    out.append(f"Shares held: {shares:g}")
    if shares > 0:
        out.append(f"EUR cost basis: EUR {cost:,.2f} (EUR {cost/shares:.2f}/share avg)")
    out.append(f"Sector/layer (my tag): {t.layer or '(not set)'}")
    out.append(
        f"Conviction: {t.conviction if t.conviction is not None else '(not set)'}/10  |  "
        f"Horizon: {t.horizon or '(not set)'}"
    )
    out.append("")
    out.append("=== MY THESIS ===")
    out.append(t.thesis or "(not written)")
    out.append("")

    zones = t.entry_zones.filter_by(active=True).order_by(EntryZone.price_low).all()
    if zones:
        out.append("=== MY ENTRY/EXIT ZONES ===")
        for z in zones:
            line = f"  {z.zone_type.upper()}: {z.price_low}-{z.price_high} {z.currency}"
            if z.notes:
                line += f" ({z.notes})"
            out.append(line)
        out.append("")

    risks = t.risks.filter_by(active=True).all()
    if risks:
        out.append("=== RISKS I HAVE IDENTIFIED ===")
        for r in risks:
            out.append(f"  [{r.severity}] {r.description}")
        out.append("")

    cats = t.catalysts.filter_by(resolved=False).order_by(Catalyst.catalyst_date).all()
    if cats:
        out.append("=== UPCOMING CATALYSTS I AM WATCHING ===")
        for c in cats:
            out.append(f"  {c.catalyst_date.isoformat()} [{c.catalyst_type or 'other'}] {c.title}")
        out.append("")

    lots = list(t.lots)
    if lots:
        out.append("=== MY BUY HISTORY ===")
        for l in lots:
            tag = " [Dec 31 2025 step-up basis, not original purchase]" if l.source == 'migrated_pre_2026' else ""
            out.append(
                f"  {l.trade_date.isoformat()}: {l.shares:g} sh @ {l.price_native:g} {l.currency} "
                f"-> EUR {l.cost_basis_eur:,.2f} cost ({l.remaining_shares:g} remaining){tag}"
            )
        out.append("")

    sales = list(t.sales)
    if sales:
        out.append("=== MY SELL HISTORY ===")
        for s in sales:
            gain = s.realized_gain_eur or 0
            out.append(
                f"  {s.trade_date.isoformat()}: {s.shares:g} sh @ {s.price_native:g} {s.currency} "
                f"-> EUR {s.proceeds_eur:,.2f} proceeds, realized {gain:+,.2f} EUR"
            )
        out.append("")

    divs = list(t.dividends)
    if divs:
        out.append("=== DIVIDEND HISTORY ===")
        for d in divs:
            out.append(
                f"  {d.payment_date.isoformat()}: {d.shares_at_record:g} sh x "
                f"{d.dividend_per_share_native:.4f} {d.currency}/sh -> EUR {d.net_eur:,.2f} net"
            )
        out.append("")

    out.append("=== WHAT I WANT FROM YOU ===")
    out.append("1. Is my thesis logically sound? What are its weakest assumptions?")
    out.append("2. What is a smart bear case on this stock that I have not considered?")
    out.append("3. Are my risks complete, or are there major ones I have missed?")
    out.append("4. Do my entry/exit zones make sense given the current price and historical valuation?")
    out.append("5. Are my catalyst dates realistic? Any major upcoming catalysts I have missed?")
    out.append("6. Given my conviction and horizon, is the current position sizing reasonable, or should I trim/add?")
    out.append("7. What is the ONE thing about this company that I should be tracking that I am probably not?")
    out.append("")
    out.append("Be specific. Use concrete numbers. Push back where I am weak. Do not flatter me.")

    return jsonify({'prompt': '\n'.join(out)})


@app.route('/investing/tax/export')
def investing_tax_export():
    """CSV export of per-trade tax detail. Belgian declaration audit trail."""
    year = request.args.get('year', type=int) or date.today().year

    sales = (
        TradeSale.query
        .filter(db.extract('year', TradeSale.trade_date) == year)
        .order_by(TradeSale.trade_date.asc(), TradeSale.id.asc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'ticker', 'isin', 'company_name',
        'sale_date', 'sale_bordereau', 'shares_consumed',
        'lot_acq_date', 'lot_source', 'lot_id',
        'cost_basis_eur', 'proceeds_eur', 'gain_eur',
        'method',
    ])

    for sale in sales:
        ticker = Ticker.query.get(sale.ticker_id)
        for cons in sale.consumptions:
            lot = TradeLot.query.get(cons.lot_id)
            writer.writerow([
                ticker.symbol if ticker else '',
                ticker.isin if ticker else '',
                ticker.company_name if ticker else '',
                sale.trade_date.isoformat(),
                sale.bordereau or '',
                f'{cons.shares_consumed:.6g}',
                lot.trade_date.isoformat() if lot and lot.trade_date else '',
                lot.source if lot else '',
                lot.id if lot else '',
                f'{cons.cost_basis_eur:.4f}',
                f'{cons.proceeds_eur:.4f}',
                f'{cons.gain_eur:.4f}',
                cons.method,
            ])

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename=tax_detail_{year}.csv'
    return response


if __name__ == '__main__':
    # Prevent Windows from sleeping while the app is running
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    app.run(debug=True, port=5000)
