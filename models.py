from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# Association table for many-to-many relationship between contacts and tags
contact_tags = db.Table('contact_tags',
    db.Column('contact_id', db.Integer, db.ForeignKey('contact.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

# Association table for many-to-many relationship between journal entries and contacts
journal_mentions = db.Table('journal_mentions',
    db.Column('journal_entry_id', db.Integer, db.ForeignKey('journal_entry.id'), primary_key=True),
    db.Column('contact_id', db.Integer, db.ForeignKey('contact.id'), primary_key=True)
)


class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    birthday = db.Column(db.Date)
    address = db.Column(db.Text)
    notes = db.Column(db.Text)
    relationship_category = db.Column(db.String(50))  # family, friend, professional, etc.
    how_we_met = db.Column(db.Text)
    preferred_language = db.Column(db.String(50))  # English, French, etc.
    last_contacted_date = db.Column(db.Date)
    contact_frequency = db.Column(db.Integer)  # days between contacts
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    interactions = db.relationship('Interaction', backref='contact', lazy=True, cascade='all, delete-orphan')
    tags = db.relationship('Tag', secondary=contact_tags, backref='contacts')
    journal_entries = db.relationship('JournalEntry', secondary=journal_mentions, backref='mentioned_contacts')
    
    def __repr__(self):
        return f'<Contact {self.first_name} {self.last_name}>'
    
    @property
    def full_name(self):
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name
    
    @property
    def days_since_contact(self):
        if self.last_contacted_date:
            return (datetime.utcnow().date() - self.last_contacted_date).days
        return None


class Interaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('contact.id'), nullable=False)
    interaction_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    interaction_type = db.Column(db.String(50))  # call, coffee, dinner, text, etc.
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Interaction {self.interaction_type} on {self.interaction_date}>'


class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    
    def __repr__(self):
        return f'<Tag {self.name}>'


class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    content = db.Column(db.Text)
    mood = db.Column(db.String(50))
    claude_reflection = db.Column(db.Text)  # Store Claude's reflection
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<JournalEntry {self.date}>'


class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('contact.id'), nullable=False)
    reminder_date = db.Column(db.Date, nullable=False)
    reminder_type = db.Column(db.String(50))
    note = db.Column(db.Text)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    contact = db.relationship('Contact', backref='reminders')
    
    def __repr__(self):
        return f'<Reminder for {self.contact.full_name} on {self.reminder_date}>'


class GameStats(db.Model):
    """Track gamification stats for journal writing"""
    id = db.Column(db.Integer, primary_key=True)
    current_streak = db.Column(db.Integer, default=0)
    longest_streak = db.Column(db.Integer, default=0)
    last_entry_date = db.Column(db.Date)
    total_entries = db.Column(db.Integer, default=0)
    total_words = db.Column(db.Integer, default=0)
    xp = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    freeze_available = db.Column(db.Boolean, default=True)
    freeze_used_this_week = db.Column(db.Boolean, default=False)
    last_freeze_reset = db.Column(db.Date)
    achievements = db.Column(db.Text)  # JSON string of unlocked achievements
    challenges_completed = db.Column(db.Integer, default=0)
    current_challenge_id = db.Column(db.Integer)  # Index of today's challenge
    challenge_date = db.Column(db.Date)  # Date challenge was assigned
    challenge_completed_today = db.Column(db.Boolean, default=False)
    # Dynamic daily challenge (Claude-generated)
    challenge_title = db.Column(db.String(200))  # Generated challenge title
    challenge_description = db.Column(db.Text)  # Generated challenge description
    challenge_icon = db.Column(db.String(10))  # Generated challenge icon emoji
    challenge_history = db.Column(db.Text)  # JSON array of recent challenge titles (last 30)
    # Learning stats
    learning_streak = db.Column(db.Integer, default=0)
    learning_sessions_total = db.Column(db.Integer, default=0)
    learning_xp_total = db.Column(db.Integer, default=0)
    last_learning_date = db.Column(db.Date)
    # Meditation stats
    meditation_streak = db.Column(db.Integer, default=0)
    meditation_sessions_total = db.Column(db.Integer, default=0)
    meditation_minutes_total = db.Column(db.Integer, default=0)
    meditation_xp_total = db.Column(db.Integer, default=0)
    last_meditation_date = db.Column(db.Date)
    # Nutrition stats
    nutrition_streak = db.Column(db.Integer, default=0)
    nutrition_entries_total = db.Column(db.Integer, default=0)
    nutrition_xp_total = db.Column(db.Integer, default=0)
    last_nutrition_date = db.Column(db.Date)
    meal_plans_generated = db.Column(db.Integer, default=0)

    # Newsletter stats
    newsletter_ideas_total = db.Column(db.Integer, default=0)
    newsletter_issues_total = db.Column(db.Integer, default=0)

    # Activity/training stats
    activity_streak = db.Column(db.Integer, default=0)
    activity_sessions_total = db.Column(db.Integer, default=0)
    activity_xp_total = db.Column(db.Integer, default=0)
    last_activity_date = db.Column(db.Date)

    # Mandarin learning stats
    mandarin_streak = db.Column(db.Integer, default=0)
    mandarin_sessions_total = db.Column(db.Integer, default=0)
    mandarin_xp_total = db.Column(db.Integer, default=0)
    mandarin_cards_learned = db.Column(db.Integer, default=0)
    last_mandarin_date = db.Column(db.Date)

    def __repr__(self):
        return f'<GameStats Streak:{self.current_streak} XP:{self.xp}>'
    
    @property
    def level_name(self):
        levels = {
            1: "Apprentice",
            2: "Scribe",
            3: "Chronicler", 
            4: "Storyteller",
            5: "Historian",
            6: "Sage",
            7: "Oracle",
            8: "Legend"
        }
        return levels.get(self.level, "Legend")
    
    @property
    def xp_for_next_level(self):
        thresholds = {
            1: 100,
            2: 300,
            3: 600,
            4: 1000,
            5: 1500,
            6: 2500,
            7: 4000
        }
        return thresholds.get(self.level, 9999)


class LearningInterest(db.Model):
    """User's topics of interest for learning roulette"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(10))  # Emoji icon
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    current_level = db.Column(db.String(20), default='beginner')  # beginner/intermediate/advanced
    times_selected = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sessions = db.relationship('LearningSession', backref='interest', lazy=True)

    def __repr__(self):
        return f'<LearningInterest {self.name}>'


class LearningSession(db.Model):
    """Daily learning session records"""
    id = db.Column(db.Integer, primary_key=True)
    interest_id = db.Column(db.Integer, db.ForeignKey('learning_interest.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    topic_title = db.Column(db.String(200))
    content = db.Column(db.Text)  # Markdown content
    difficulty_level = db.Column(db.String(20))  # beginner/intermediate/advanced
    estimated_time = db.Column(db.Integer, default=30)  # minutes
    completed = db.Column(db.Boolean, default=False)
    xp_earned = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)  # User's notes
    quiz_questions = db.Column(db.Text)  # JSON string of quiz questions
    quiz_score = db.Column(db.Integer)  # User's quiz score
    feedback = db.Column(db.Text)  # User feedback on the content
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<LearningSession {self.topic_title} on {self.date}>'


class LearningProgress(db.Model):
    """Aggregate stats per topic"""
    id = db.Column(db.Integer, primary_key=True)
    interest_id = db.Column(db.Integer, db.ForeignKey('learning_interest.id'), nullable=False)
    sessions_completed = db.Column(db.Integer, default=0)
    total_time_minutes = db.Column(db.Integer, default=0)
    total_xp = db.Column(db.Integer, default=0)

    interest = db.relationship('LearningInterest', backref='progress')

    def __repr__(self):
        return f'<LearningProgress {self.interest_id}>'


class Highlight(db.Model):
    """Saved text highlights from learning sessions"""
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('learning_session.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    session = db.relationship('LearningSession', backref='highlights')

    def __repr__(self):
        return f'<Highlight {self.id}: {self.text[:40]}...>'


class WordleStats(db.Model):
    """Track LoL Wordle game stats"""
    id = db.Column(db.Integer, primary_key=True)
    current_streak = db.Column(db.Integer, default=0)
    max_streak = db.Column(db.Integer, default=0)
    games_played = db.Column(db.Integer, default=0)
    games_won = db.Column(db.Integer, default=0)
    guess_distribution = db.Column(db.Text, default='{"1":0,"2":0,"3":0,"4":0,"5":0,"6":0}')
    last_played_date = db.Column(db.Date)
    last_game_word = db.Column(db.String(10))
    last_game_guesses = db.Column(db.Text)  # JSON array of guesses
    last_game_won = db.Column(db.Boolean)

    def __repr__(self):
        return f'<WordleStats Played:{self.games_played} Won:{self.games_won}>'


class MeditationSession(db.Model):
    """Individual meditation session records"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    session_type = db.Column(db.String(30), nullable=False)  # 'timer' or 'breathing'
    breathing_pattern = db.Column(db.String(50))  # 'box', '478', 'deep', 'custom' (null for timer)
    duration_seconds = db.Column(db.Integer, nullable=False)
    target_duration_seconds = db.Column(db.Integer)
    completed = db.Column(db.Boolean, default=False)
    xp_earned = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<MeditationSession {self.session_type} {self.duration_seconds}s on {self.date}>'


class PortfolioBriefing(db.Model):
    """Cached daily portfolio news briefings"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    summary_html = db.Column(db.Text)  # Claude-generated summary
    raw_articles = db.Column(db.Text)  # JSON of raw news articles
    tickers_data = db.Column(db.Text)  # JSON of portfolio tickers used
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<PortfolioBriefing {self.date}>'


class NutritionProfile(db.Model):
    """User's body stats & calorie target (singleton like GameStats)"""
    id = db.Column(db.Integer, primary_key=True)
    height_cm = db.Column(db.Float)
    weight_kg = db.Column(db.Float)
    age = db.Column(db.Integer)
    sex = db.Column(db.String(10))  # male/female
    activity_level = db.Column(db.String(20))  # sedentary/light/moderate/active/very_active
    calorie_target = db.Column(db.Integer)
    target_weight_kg = db.Column(db.Float)
    protein_target_pct = db.Column(db.Integer, default=30)
    carbs_target_pct = db.Column(db.Integer, default=40)
    fat_target_pct = db.Column(db.Integer, default=30)
    dietary_preferences = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<NutritionProfile {self.calorie_target}cal>'


class NutritionEntry(db.Model):
    """Individual meal logs"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    meal_type = db.Column(db.String(20))  # breakfast/lunch/dinner/snack
    description = db.Column(db.Text)
    calories = db.Column(db.Integer)
    protein_grams = db.Column(db.Float)
    carbs_grams = db.Column(db.Float)
    fat_grams = db.Column(db.Float)
    xp_earned = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<NutritionEntry {self.meal_type} {self.calories}cal on {self.date}>'


class MealPlan(db.Model):
    """Weekly Claude-generated meal plans"""
    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    content = db.Column(db.Text)  # markdown
    grocery_list = db.Column(db.Text)  # markdown
    calorie_target = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<MealPlan {self.start_date} to {self.end_date}>'


class WeightEntry(db.Model):
    """Daily weight log entries"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    weight_kg = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<WeightEntry {self.date} {self.weight_kg}kg>'


class NewsletterIssue(db.Model):
    """A planned newsletter edition"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    target_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='planning')  # planning/drafting/sent
    google_doc_url = db.Column(db.String(500))
    notes = db.Column(db.Text)
    content = db.Column(db.Text)  # markdown body of the newsletter
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime, nullable=True)  # when "Mark as Sent" was clicked
    ideas = db.relationship('NewsletterIdea', backref='issue', lazy=True, order_by='NewsletterIdea.sort_order')

    def __repr__(self):
        return f'<NewsletterIssue {self.title}>'


class NewsletterIdea(db.Model):
    """A topic/idea for a newsletter"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    notes = db.Column(db.Text)
    category = db.Column(db.String(30), default='misc')  # tech/life/recommendation/story/question/misc
    status = db.Column(db.String(20), default='backlog')  # backlog/planned/used/archived
    issue_id = db.Column(db.Integer, db.ForeignKey('newsletter_issue.id'), nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<NewsletterIdea {self.title}>'


class NewsletterSubscriber(db.Model):
    """A subscriber on the newsletter mailing list"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    email = db.Column(db.String(300), nullable=False, unique=True)
    language = db.Column(db.String(5), default='en')  # en/fr
    active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)  # "why did you sign up" from public form
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<NewsletterSubscriber {self.email} ({self.language})>'


class PortfolioStock(db.Model):
    """A stock in the portfolio (holding) or watchlist"""
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(20), nullable=False, unique=True)
    company = db.Column(db.String(200), nullable=False)
    layer = db.Column(db.String(100))  # sector/category
    status = db.Column(db.String(20), default='watchlist')  # 'holding' or 'watchlist'
    value = db.Column(db.Float, default=0)  # USD value of position (holdings only)
    weight = db.Column(db.Float, default=0)  # portfolio weight % (holdings only, auto-calculated)
    shares = db.Column(db.Float, default=0)  # number of shares held
    avg_cost = db.Column(db.Float, default=0)  # average cost per share in native currency
    currency = db.Column(db.String(5), default='USD')  # trading currency (USD, EUR, DKK, GBp)
    conviction = db.Column(db.String(30))  # Very High/High/Medium/Low (holdings only)
    verdict = db.Column(db.String(50))  # BUY/HOLD/SPECULATIVE etc (watchlist only)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'ticker': self.ticker,
            'company': self.company,
            'layer': self.layer,
            'status': self.status,
            'value': self.value,
            'weight': self.weight,
            'shares': self.shares,
            'avg_cost': self.avg_cost,
            'currency': self.currency,
            'conviction': self.conviction,
            'verdict': self.verdict,
        }

    def __repr__(self):
        return f'<PortfolioStock {self.ticker} ({self.status})>'


class StockFundamentals(db.Model):
    """Cached fundamental data from yfinance for value investing analysis"""
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(20), nullable=False, unique=True)

    # Price data
    current_price = db.Column(db.Float)
    market_cap = db.Column(db.Float)
    week_52_high = db.Column(db.Float)
    week_52_low = db.Column(db.Float)

    # Valuation
    pe_trailing = db.Column(db.Float)
    pe_forward = db.Column(db.Float)
    pb_ratio = db.Column(db.Float)
    ev_ebitda = db.Column(db.Float)
    peg_ratio = db.Column(db.Float)
    fcf_yield = db.Column(db.Float)

    # Profitability
    roe = db.Column(db.Float)
    roa = db.Column(db.Float)
    gross_margin = db.Column(db.Float)
    operating_margin = db.Column(db.Float)
    net_margin = db.Column(db.Float)

    # Financial health
    debt_to_equity = db.Column(db.Float)
    current_ratio = db.Column(db.Float)
    quick_ratio = db.Column(db.Float)
    interest_coverage = db.Column(db.Float)

    # Growth
    revenue_growth = db.Column(db.Float)
    earnings_growth = db.Column(db.Float)

    # Dividends
    dividend_yield = db.Column(db.Float)
    payout_ratio = db.Column(db.Float)

    # Computed
    value_score = db.Column(db.Float)

    # Meta
    company_name = db.Column(db.String(200))
    sector = db.Column(db.String(100))
    industry = db.Column(db.String(100))
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_stale(self, max_age_hours=6):
        if not self.fetched_at:
            return True
        age = (datetime.utcnow() - self.fetched_at).total_seconds() / 3600
        return age > max_age_hours

    def to_dict(self):
        return {
            'ticker': self.ticker,
            'company_name': self.company_name,
            'sector': self.sector,
            'industry': self.industry,
            'price': {
                'current': self.current_price,
                'market_cap': self.market_cap,
                'week_52_high': self.week_52_high,
                'week_52_low': self.week_52_low,
            },
            'valuation': {
                'pe_trailing': self.pe_trailing,
                'pe_forward': self.pe_forward,
                'pb_ratio': self.pb_ratio,
                'ev_ebitda': self.ev_ebitda,
                'peg_ratio': self.peg_ratio,
                'fcf_yield': self.fcf_yield,
            },
            'profitability': {
                'roe': self.roe,
                'roa': self.roa,
                'gross_margin': self.gross_margin,
                'operating_margin': self.operating_margin,
                'net_margin': self.net_margin,
            },
            'financial_health': {
                'debt_to_equity': self.debt_to_equity,
                'current_ratio': self.current_ratio,
                'quick_ratio': self.quick_ratio,
                'interest_coverage': self.interest_coverage,
            },
            'growth': {
                'revenue_growth': self.revenue_growth,
                'earnings_growth': self.earnings_growth,
            },
            'dividends': {
                'dividend_yield': self.dividend_yield,
                'payout_ratio': self.payout_ratio,
            },
            'value_score': self.value_score,
            'fetched_at': self.fetched_at.strftime('%Y-%m-%d %H:%M') if self.fetched_at else None,
        }

    def __repr__(self):
        return f'<StockFundamentals {self.ticker} score={self.value_score}>'


class Workout(db.Model):
    """Individual training session records (run, gym, cross-training)"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    workout_type = db.Column(db.String(20), nullable=False)  # 'run', 'gym', 'cross-training'
    title = db.Column(db.String(200))
    notes = db.Column(db.Text)
    # Run fields
    distance_km = db.Column(db.Float)
    duration_minutes = db.Column(db.Float)
    pace_per_km = db.Column(db.String(10))  # e.g. "5:30" (computed on save)
    effort = db.Column(db.String(20))  # easy/moderate/hard/race
    heart_rate_avg = db.Column(db.Integer)
    # Gym fields
    exercises = db.Column(db.Text)  # JSON array of {name, sets, reps, weight_kg}
    muscle_groups = db.Column(db.Text)  # JSON array of strings
    # Garmin integration
    garmin_activity_id = db.Column(db.BigInteger, unique=True, nullable=True)
    # Gamification
    xp_earned = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Workout {self.workout_type} on {self.date}>'


class TrainingPlan(db.Model):
    """AI-generated periodized training plans"""
    id = db.Column(db.Integer, primary_key=True)
    target_event = db.Column(db.String(200))  # e.g. "Marathon"
    target_date = db.Column(db.Date)
    current_fitness_summary = db.Column(db.Text)
    goals = db.Column(db.Text)  # e.g. "Sub 4h marathon + weight loss"
    plan_content = db.Column(db.Text)  # Full markdown plan
    phase_summary = db.Column(db.Text)  # JSON [{phase, start_week, end_week, focus}]
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    weeks = db.relationship('TrainingWeek', backref='plan', lazy=True, cascade='all, delete-orphan')
    days = db.relationship('TrainingDay', backref='plan', lazy=True, cascade='all, delete-orphan', order_by='TrainingDay.date')

    def __repr__(self):
        return f'<TrainingPlan {self.target_event} ({self.target_date})>'


class TrainingWeek(db.Model):
    """Weekly snapshots for progress tracking within a training plan"""
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('training_plan.id'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date)
    phase = db.Column(db.String(20))  # base/build/peak/taper
    planned_summary = db.Column(db.Text)
    actual_summary = db.Column(db.Text)
    planned_km = db.Column(db.Float, default=0)
    actual_km = db.Column(db.Float, default=0)
    planned_gym_sessions = db.Column(db.Integer, default=0)
    actual_gym_sessions = db.Column(db.Integer, default=0)
    compliance_pct = db.Column(db.Integer, default=0)
    coach_notes = db.Column(db.Text)

    def __repr__(self):
        return f'<TrainingWeek {self.week_number} ({self.phase})>'


class TrainingDay(db.Model):
    """Individual scheduled day within a training plan — the calendar atom"""
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('training_plan.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    session_type = db.Column(db.String(20), nullable=False)  # run, gym, cross-training, rest, race
    title = db.Column(db.String(200))
    description = db.Column(db.Text)  # Watch-copyable detail: paces, intervals, distances
    phase = db.Column(db.String(20))  # base, build, peak, taper
    week_number = db.Column(db.Integer)
    effort_level = db.Column(db.String(20))  # easy, moderate, hard, race, rest
    planned_km = db.Column(db.Float)
    is_key_session = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='planned')  # planned, completed, skipped
    swap_note = db.Column(db.Text)
    ripple_adjusted = db.Column(db.Boolean, default=False)
    original_description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat(),
            'session_type': self.session_type,
            'title': self.title,
            'description': self.description,
            'phase': self.phase,
            'week_number': self.week_number,
            'effort_level': self.effort_level,
            'planned_km': self.planned_km,
            'is_key_session': self.is_key_session,
            'status': self.status,
            'ripple_adjusted': self.ripple_adjusted,
        }

    def __repr__(self):
        return f'<TrainingDay {self.date} {self.session_type} ({self.status})>'


class GarminDailyStats(db.Model):
    """Cached daily stats from Garmin Connect"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    # Steps & movement
    steps = db.Column(db.Integer)
    step_goal = db.Column(db.Integer)
    distance_meters = db.Column(db.Float)
    floors_climbed = db.Column(db.Float)
    # Calories
    calories = db.Column(db.Float)          # total burned
    active_calories = db.Column(db.Float)   # from activity only
    bmr_calories = db.Column(db.Float)      # basal metabolic rate
    # Active time
    active_minutes = db.Column(db.Integer)
    moderate_intensity_min = db.Column(db.Integer)
    vigorous_intensity_min = db.Column(db.Integer)
    intensity_minutes_goal = db.Column(db.Integer)
    sedentary_seconds = db.Column(db.Integer)
    # Heart rate
    resting_hr = db.Column(db.Integer)
    min_hr = db.Column(db.Integer)
    max_hr = db.Column(db.Integer)
    avg_resting_hr_7day = db.Column(db.Integer)
    # Stress
    avg_stress = db.Column(db.Integer)
    max_stress = db.Column(db.Integer)
    low_stress_pct = db.Column(db.Float)
    medium_stress_pct = db.Column(db.Float)
    high_stress_pct = db.Column(db.Float)
    rest_stress_pct = db.Column(db.Float)
    stress_qualifier = db.Column(db.String(30))
    # Body battery
    body_battery_high = db.Column(db.Integer)
    body_battery_low = db.Column(db.Integer)
    body_battery_at_wake = db.Column(db.Integer)
    body_battery_charged = db.Column(db.Integer)
    body_battery_drained = db.Column(db.Integer)
    # Respiration
    avg_respiration = db.Column(db.Float)
    lowest_respiration = db.Column(db.Float)
    highest_respiration = db.Column(db.Float)
    # Sleep
    sleep_seconds = db.Column(db.Integer)
    sleep_deep_seconds = db.Column(db.Integer)
    sleep_light_seconds = db.Column(db.Integer)
    sleep_rem_seconds = db.Column(db.Integer)
    sleep_awake_seconds = db.Column(db.Integer)
    sleep_score = db.Column(db.Integer)
    # Sync metadata
    synced_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<GarminDailyStats {self.date}>'


class ApiUsageLog(db.Model):
    """Tracks every Claude API call for cost monitoring"""
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    feature = db.Column(db.String(50), nullable=False)  # e.g. 'journal', 'nutrition', 'portfolio'
    endpoint = db.Column(db.String(100))  # e.g. 'reflect', 'log_meal', 'deep_dive'
    model = db.Column(db.String(80), nullable=False)
    input_tokens = db.Column(db.Integer, default=0)
    output_tokens = db.Column(db.Integer, default=0)
    cost_usd = db.Column(db.Float, default=0.0)
    duration_ms = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'feature': self.feature,
            'endpoint': self.endpoint,
            'model': self.model,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'cost_usd': self.cost_usd,
            'duration_ms': self.duration_ms,
        }


class CoachConversation(db.Model):
    """Stores chat messages for the personal AI coach, per area"""
    id = db.Column(db.Integer, primary_key=True)
    area = db.Column(db.String(30), nullable=False)  # journal/exercise/weight/meals/daily/relationships/growth
    role = db.Column(db.String(10), nullable=False)   # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<CoachConversation {self.area} {self.role} at {self.created_at}>'


class CoachGoal(db.Model):
    """Tracks personal goals set during coaching conversations"""
    id = db.Column(db.Integer, primary_key=True)
    area = db.Column(db.String(30), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    target_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default='active')  # active, completed, abandoned
    progress_notes = db.Column(db.Text, nullable=True)   # JSON list of progress updates
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<CoachGoal {self.title} ({self.status})>'


class CoachMood(db.Model):
    """Tracks mood/sentiment from coaching sessions for trend analysis"""
    id = db.Column(db.Integer, primary_key=True)
    area = db.Column(db.String(30), nullable=False)
    score = db.Column(db.Float, nullable=False)         # -1.0 to 1.0
    label = db.Column(db.String(30), nullable=True)     # positive, negative, neutral, mixed
    keywords = db.Column(db.Text, nullable=True)         # JSON list of detected themes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<CoachMood {self.area} {self.label} ({self.score})>'


class CoachSummary(db.Model):
    """Auto-generated summaries of coaching conversations per area"""
    id = db.Column(db.Integer, primary_key=True)
    area = db.Column(db.String(30), nullable=False)
    summary_text = db.Column(db.Text, nullable=False)
    message_count = db.Column(db.Integer, default=0)    # messages covered
    period_start = db.Column(db.DateTime, nullable=True)
    period_end = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<CoachSummary {self.area} ({self.message_count} msgs)>'


class CoachPreference(db.Model):
    """Stores user preferences for the coaching experience"""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), nullable=False, unique=True)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<CoachPreference {self.key}={self.value}>'


class MandarinCard(db.Model):
    """Pre-seeded vocabulary library for Mandarin learning"""
    id = db.Column(db.Integer, primary_key=True)
    english = db.Column(db.String(200), nullable=False)
    pinyin = db.Column(db.String(200), nullable=False)
    characters = db.Column(db.String(200))
    category = db.Column(db.String(50), nullable=False)
    difficulty = db.Column(db.Integer, default=1)
    sort_order = db.Column(db.Integer, default=0)
    usage_note = db.Column(db.Text)
    tone_pattern = db.Column(db.String(20))
    is_tone_drill = db.Column(db.Boolean, default=False)

    reviews = db.relationship('MandarinReview', backref='card', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<MandarinCard {self.english} ({self.pinyin})>'


class MandarinReview(db.Model):
    """Per-card spaced repetition state"""
    id = db.Column(db.Integer, primary_key=True)
    card_id = db.Column(db.Integer, db.ForeignKey('mandarin_card.id'), nullable=False)
    ease_factor = db.Column(db.Float, default=2.5)
    interval_days = db.Column(db.Integer, default=0)
    repetitions = db.Column(db.Integer, default=0)
    next_review_date = db.Column(db.Date)
    last_reviewed = db.Column(db.DateTime)
    total_reviews = db.Column(db.Integer, default=0)
    correct_count = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<MandarinReview card={self.card_id} interval={self.interval_days}d>'


class MandarinSession(db.Model):
    """Session history for Mandarin learning"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    cards_reviewed = db.Column(db.Integer, default=0)
    cards_new = db.Column(db.Integer, default=0)
    cards_correct = db.Column(db.Integer, default=0)
    cards_hard = db.Column(db.Integer, default=0)
    duration_seconds = db.Column(db.Integer, default=0)
    xp_earned = db.Column(db.Integer, default=0)
    session_type = db.Column(db.String(20), default='review')

    def __repr__(self):
        return f'<MandarinSession {self.date} reviewed={self.cards_reviewed}>'


# ===== PERSONAL FINANCE =====

class FinanceTransaction(db.Model):
    """Individual financial transaction — imported from Revolut CSV or manually entered"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(300), nullable=False)
    amount = db.Column(db.Float, nullable=False)  # negative = expense, positive = income
    fee = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(5), default='EUR')
    category = db.Column(db.String(50))
    subcategory = db.Column(db.String(50))
    transaction_type = db.Column(db.String(30))  # income/expense/transfer/investment/interest/subscription
    source = db.Column(db.String(30), default='manual')  # revolut_import / manual / recurring
    revolut_product = db.Column(db.String(50))  # Dépôt (savings) / Valeur actuelle (checking)
    state = db.Column(db.String(20))  # TERMINÉ / EN ATTENTE / RENVOYÉ
    import_hash = db.Column(db.String(64), unique=True)  # SHA256 to prevent duplicate imports
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'description': self.description,
            'amount': self.amount,
            'fee': self.fee,
            'currency': self.currency,
            'category': self.category,
            'subcategory': self.subcategory,
            'transaction_type': self.transaction_type,
            'source': self.source,
            'revolut_product': self.revolut_product,
            'state': self.state,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<FinanceTransaction {self.date} {self.description} {self.amount}>'


class FinanceBudget(db.Model):
    """Monthly budget target per category"""
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False)
    monthly_limit = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'category': self.category,
            'monthly_limit': self.monthly_limit,
            'is_active': self.is_active,
        }

    def __repr__(self):
        return f'<FinanceBudget {self.category} {self.monthly_limit}>'


class FinanceRecurringCost(db.Model):
    """Fixed monthly cost — rent, subscriptions, etc."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)  # always positive, treated as expense
    category = db.Column(db.String(50))
    frequency = db.Column(db.String(20), default='monthly')  # monthly / yearly / weekly
    day_of_month = db.Column(db.Integer)  # when it typically hits
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'amount': self.amount,
            'category': self.category,
            'frequency': self.frequency,
            'day_of_month': self.day_of_month,
            'is_active': self.is_active,
            'notes': self.notes,
        }

    def __repr__(self):
        return f'<FinanceRecurringCost {self.name} {self.amount}>'


class DCASchedule(db.Model):
    """Dollar-cost averaging plan — monthly investment target per stock"""
    id = db.Column(db.Integer, primary_key=True)
    stock_id = db.Column(db.Integer, db.ForeignKey('portfolio_stock.id'), nullable=False)
    monthly_amount = db.Column(db.Float, nullable=False)  # target amount in EUR
    currency = db.Column(db.String(5), default='EUR')
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    stock = db.relationship('PortfolioStock', backref='dca_schedules')

    def to_dict(self):
        return {
            'id': self.id,
            'stock_id': self.stock_id,
            'ticker': self.stock.ticker if self.stock else None,
            'company': self.stock.company if self.stock else None,
            'monthly_amount': self.monthly_amount,
            'currency': self.currency,
            'is_active': self.is_active,
            'notes': self.notes,
        }

    def __repr__(self):
        return f'<DCASchedule stock={self.stock_id} {self.monthly_amount}/month>'
