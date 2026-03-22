"""Seed script for demo mode — populates the database with realistic fake data."""
import os
import sys
import json
from datetime import datetime, timedelta, date

# Ensure DEMO_MODE is set before importing app
os.environ['DEMO_MODE'] = 'true'

from app import app, db
from models import (
    Contact, Interaction, Tag, JournalEntry, GameStats, LearningInterest,
    LearningSession, LearningProgress, Highlight, WordleStats, MeditationSession,
    PortfolioBriefing, NutritionProfile, NutritionEntry, MealPlan, WeightEntry,
    NewsletterIssue, NewsletterIdea, NewsletterSubscriber, PortfolioStock,
    StockFundamentals, ApiUsageLog, Workout, TrainingPlan, TrainingWeek,
    TrainingDay, CoachConversation, CoachGoal, CoachMood, CoachSummary,
    CoachPreference, MandarinCard, MandarinReview, MandarinSession,
    GarminDailyStats, FinanceTransaction, FinanceBudget, FinanceRecurringCost,
)

TODAY = date.today()


def d(days_ago):
    """Helper: date N days ago"""
    return TODAY - timedelta(days=days_ago)


def dt(days_ago, hour=9, minute=0):
    """Helper: datetime N days ago"""
    return datetime.combine(d(days_ago), datetime.min.time().replace(hour=hour, minute=minute))


def seed_contacts():
    """8 fake contacts with interactions"""
    tags_map = {}
    for name in ['engineering', 'fitness', 'book-club', 'travel', 'family', 'startup']:
        t = Tag(name=name)
        db.session.add(t)
        tags_map[name] = t
    db.session.flush()

    contacts = [
        dict(first_name='Alice', last_name='Builder', phone='+1-555-0101', email='alice@example.com',
             relationship_category='friend', how_we_met='Met at a hackathon in 2022',
             contact_frequency=14, last_contacted_date=d(3), tags=['engineering', 'startup']),
        dict(first_name='Bob', last_name='Learner', phone='+1-555-0102', email='bob@example.com',
             relationship_category='professional', how_we_met='Former colleague at TechCorp',
             contact_frequency=30, last_contacted_date=d(12), tags=['engineering']),
        dict(first_name='Clara', last_name='Fitwell', phone='+1-555-0103', email='clara@example.com',
             relationship_category='friend', how_we_met='Running club',
             contact_frequency=7, last_contacted_date=d(2), tags=['fitness']),
        dict(first_name='David', last_name='Nomad', phone='+44-7700-0104', email='david@example.com',
             relationship_category='friend', how_we_met='Backpacking through Southeast Asia',
             contact_frequency=21, last_contacted_date=d(18), tags=['travel']),
        dict(first_name='Emma', last_name='Wise', email='emma@example.com',
             relationship_category='family', contact_frequency=7,
             last_contacted_date=d(1), birthday=date(1990, 6, 15), tags=['family', 'book-club']),
        dict(first_name='Franck', last_name='Dupont', phone='+33-6-5500-0106', email='franck@example.com',
             relationship_category='professional', how_we_met='YC batch W24',
             preferred_language='French', contact_frequency=14, last_contacted_date=d(8), tags=['startup']),
        dict(first_name='Grace', last_name='Chen', email='grace@example.com',
             relationship_category='friend', how_we_met='Meditation retreat',
             contact_frequency=30, last_contacted_date=d(25), tags=['book-club']),
        dict(first_name='Hugo', last_name='Martin', phone='+33-6-5500-0108', email='hugo@example.com',
             relationship_category='friend', how_we_met='University roommate',
             contact_frequency=60, last_contacted_date=d(45), tags=['travel', 'fitness']),
    ]

    interaction_types = ['coffee', 'call', 'dinner', 'text', 'video-call']
    interaction_notes = [
        'Caught up on their new project — really exciting stuff!',
        'Quick sync about the upcoming trip',
        'Shared book recommendations, will follow up next week',
        'Discussed career goals and next steps',
        'Celebrated their birthday over dinner',
        'Morning run together, talked about marathon prep',
        'Brainstormed startup ideas over coffee',
        'Helped debug a tricky production issue',
    ]

    import random
    random.seed(42)

    for i, c_data in enumerate(contacts):
        tag_names = c_data.pop('tags', [])
        c = Contact(**c_data)
        for tn in tag_names:
            c.tags.append(tags_map[tn])
        db.session.add(c)
        db.session.flush()

        # Add 2-4 interactions per contact
        for j in range(random.randint(2, 4)):
            db.session.add(Interaction(
                contact_id=c.id,
                interaction_date=d(random.randint(1, 60)),
                interaction_type=random.choice(interaction_types),
                notes=random.choice(interaction_notes),
            ))

    db.session.flush()
    print(f"  Seeded {len(contacts)} contacts with interactions")


def seed_journal():
    """30 journal entries with moods and reflections"""
    moods = ['great', 'good', 'okay', 'good', 'great', 'good', 'okay', 'down', 'good', 'great']
    entries = [
        ("Had an incredibly productive morning. Finished the dashboard redesign and went for a 5K run. "
         "Feeling grateful for the momentum.", "great",
         "It's wonderful to see how physical activity and creative work can feed into each other. "
         "The momentum you're building suggests a strong alignment between your daily habits and deeper goals."),
        ("Quiet day. Read a few chapters of *Meditations* by Marcus Aurelius. "
         "Journaling helps me process thoughts I didn't know I had.", "good",
         "Reading the Stoics is a powerful practice. Your observation about journaling revealing hidden thoughts "
         "shows growing self-awareness."),
        ("Tough day at work. A deployment went sideways and I spent 4 hours debugging. "
         "Learned a lot about our caching layer though.", "down",
         "Debugging marathons are exhausting, but the learning you extracted is valuable. "
         "Consider documenting what you found about the caching layer while it's fresh."),
        ("Cooked a proper meal for the first time this week — lemon herb salmon with roasted vegetables. "
         "Small wins matter.", "good",
         "Absolutely — cooking is self-care in action. The fact that you're celebrating small wins "
         "shows a healthy mindset shift."),
        ("Marathon training is getting serious. Did a 16K long run at a comfortable pace. "
         "Legs felt heavy at the end but pushed through.", "okay",
         "16K is a significant milestone! The heaviness at the end is normal as your body adapts. "
         "Trust the process — your aerobic base is building."),
        ("Great coaching session today. Set three new goals and feel clear about my priorities. "
         "Sometimes you need an outside perspective.", "great",
         "Clarity on priorities is incredibly valuable. The willingness to seek outside perspectives "
         "is a sign of growth-oriented thinking."),
        ("Started learning about Stoic philosophy through the learning roulette. "
         "Fascinating how relevant 2000-year-old ideas still are.", "good",
         "The timelessness of Stoic philosophy speaks to universal human challenges. "
         "This could be a wonderful thread to weave through your journaling practice."),
        ("Meditation session was rough — mind kept wandering. "
         "But I showed up, and that's what counts.", "okay",
         "Showing up is the entire practice! A wandering mind isn't failure — "
         "noticing the wandering IS the meditation. You're doing this right."),
        ("Met Alice for coffee. She's launching her startup next month — inspiring energy. "
         "Made me think about what I want to build next.", "great",
         "Surrounding yourself with builders and dreamers elevates your own ambitions. "
         "What a gift to have friends who inspire action."),
        ("Portfolio hit an all-time high today. Staying disciplined though — no emotional trades. "
         "DCA continues as planned.", "good",
         "Emotional discipline during highs is just as important as during lows. "
         "Your DCA strategy removes the temptation to time the market. Well done."),
    ]

    import random
    random.seed(42)

    for i in range(30):
        idx = i % len(entries)
        content, mood, reflection = entries[idx]
        # Add some variety to repeated entries
        if i >= len(entries):
            content = content + f" (Day {i + 1} of the journey.)"

        db.session.add(JournalEntry(
            date=d(30 - i),
            content=content,
            mood=mood,
            claude_reflection=reflection,
        ))

    db.session.flush()
    print("  Seeded 30 journal entries")


def seed_game_stats():
    """Game stats: Level 5, streak 23"""
    achievements = [
        "first_entry", "3_day_streak", "7_day_streak", "14_day_streak",
        "100_words", "500_words", "first_reflection", "5_reflections",
        "first_learning", "learning_streak_3", "first_meditation",
    ]
    stats = GameStats(
        current_streak=23, longest_streak=23, last_entry_date=d(0),
        total_entries=30, total_words=8500, xp=1450, level=5,
        freeze_available=True, freeze_used_this_week=False,
        achievements=json.dumps(achievements),
        challenges_completed=12,
        challenge_title="Write about a lesson learned from failure",
        challenge_description="Reflect on a recent setback and what it taught you about resilience.",
        challenge_icon="\U0001f31f",
        learning_streak=8, learning_sessions_total=12, learning_xp_total=360,
        last_learning_date=d(1),
        meditation_streak=14, meditation_sessions_total=28, meditation_minutes_total=420,
        meditation_xp_total=560, last_meditation_date=d(0),
        nutrition_streak=10, nutrition_entries_total=50, nutrition_xp_total=250,
        last_nutrition_date=d(0),
        newsletter_ideas_total=15, newsletter_issues_total=3,
        activity_streak=6, activity_sessions_total=18, activity_xp_total=540,
        last_activity_date=d(1),
        mandarin_streak=5, mandarin_sessions_total=10, mandarin_xp_total=200,
        mandarin_cards_learned=30, last_mandarin_date=d(1),
    )
    db.session.add(stats)
    db.session.flush()
    print("  Seeded game stats (Level 5, streak 23)")


def seed_learning():
    """4 interests, 12 sessions with content"""
    interests = [
        dict(name='Stoic Philosophy', icon='\U0001f4da', description='Ancient wisdom for modern life',
             is_active=True, current_level='intermediate', times_selected=5),
        dict(name='Machine Learning', icon='\U0001f916', description='Neural networks and deep learning',
             is_active=True, current_level='beginner', times_selected=3),
        dict(name='Personal Finance', icon='\U0001f4b0', description='Investing, budgeting, and wealth building',
             is_active=True, current_level='intermediate', times_selected=3),
        dict(name='Astrophysics', icon='\U0001f52d', description='The physics of stars and the cosmos',
             is_active=False, current_level='beginner', times_selected=1),
    ]

    sessions_data = [
        (0, "Marcus Aurelius and the Art of Self-Discipline",
         "# Marcus Aurelius and Self-Discipline\n\n"
         "Marcus Aurelius, the last of the Five Good Emperors, wrote *Meditations* as a private journal "
         "never meant for publication. His core insight: **the only thing within our control is our own mind**.\n\n"
         "## Key Principles\n\n"
         "1. **The Dichotomy of Control** — Focus only on what you can influence\n"
         "2. **Memento Mori** — Remembering death makes each day precious\n"
         "3. **Amor Fati** — Love your fate, including obstacles\n\n"
         "## Practice\n\n"
         "Each morning, Aurelius would remind himself that he would encounter difficult people — "
         "and that their behavior was outside his control. Only his response was within it.\n\n"
         "> *You have power over your mind — not outside events. Realize this, and you will find strength.*\n",
         "intermediate", True, 30),
        (0, "Introduction to Neural Networks",
         "# Neural Networks 101\n\n"
         "A neural network is a computational model inspired by the brain's structure.\n\n"
         "## Architecture\n\n"
         "- **Input layer**: Receives raw data\n"
         "- **Hidden layers**: Transform data through weighted connections\n"
         "- **Output layer**: Produces predictions\n\n"
         "## Key Concepts\n\n"
         "- **Weights** are adjusted during training\n"
         "- **Activation functions** (ReLU, sigmoid) add non-linearity\n"
         "- **Backpropagation** computes gradients for optimization\n\n"
         "```python\nimport torch.nn as nn\n\nmodel = nn.Sequential(\n"
         "    nn.Linear(784, 128),\n    nn.ReLU(),\n    nn.Linear(128, 10)\n)\n```\n",
         "beginner", True, 25),
        (1, "The Power of Compound Interest",
         "# Compound Interest: The Eighth Wonder\n\n"
         "Einstein (allegedly) called compound interest the eighth wonder of the world.\n\n"
         "## The Math\n\n"
         "If you invest $500/month at 8% annual return:\n"
         "- After 10 years: **$91,473**\n"
         "- After 20 years: **$274,572**\n"
         "- After 30 years: **$680,191**\n\n"
         "## Key Takeaway\n\n"
         "Time in the market beats timing the market. The best time to start investing was 10 years ago. "
         "The second best time is today.\n",
         "intermediate", True, 20),
    ]

    quiz_template = json.dumps([
        {"question": "What is the main concept discussed?", "options": ["A", "B", "C", "D"], "correct": 0},
        {"question": "Which principle is most relevant?", "options": ["A", "B", "C", "D"], "correct": 1},
    ])

    interest_objs = []
    for data in interests:
        obj = LearningInterest(**data)
        db.session.add(obj)
        interest_objs.append(obj)
    db.session.flush()

    for i in range(12):
        idx = i % len(sessions_data)
        interest_idx, title, content, difficulty, completed, est_time = sessions_data[idx]
        interest = interest_objs[interest_idx]
        session = LearningSession(
            interest_id=interest.id,
            date=d(12 - i),
            topic_title=f"{title}" if i < len(sessions_data) else f"{title} (Part {i // len(sessions_data) + 1})",
            content=content,
            difficulty_level=difficulty,
            estimated_time=est_time,
            completed=completed,
            xp_earned=30 if completed else 0,
            quiz_questions=quiz_template,
            quiz_score=80 if completed else None,
        )
        db.session.add(session)
        db.session.flush()

        # Add highlights for some sessions
        if i < 4:
            db.session.add(Highlight(session_id=session.id, text="This is a key insight worth remembering."))

    # Add progress records
    for interest in interest_objs:
        sessions_count = LearningSession.query.filter_by(interest_id=interest.id, completed=True).count()
        if sessions_count > 0:
            db.session.add(LearningProgress(
                interest_id=interest.id,
                sessions_completed=sessions_count,
                total_time_minutes=sessions_count * 25,
                total_xp=sessions_count * 30,
            ))

    db.session.flush()
    print(f"  Seeded {len(interests)} interests, 12 learning sessions")


def seed_wordle():
    """Wordle stats: 45 played, 40 won"""
    stats = WordleStats(
        current_streak=7, max_streak=12,
        games_played=45, games_won=40,
        guess_distribution=json.dumps({"1": 2, "2": 5, "3": 12, "4": 14, "5": 5, "6": 2}),
    )
    db.session.add(stats)
    db.session.flush()
    print("  Seeded Wordle stats (45 played, 40 won)")


def seed_meditation():
    """28 meditation sessions over the last month"""
    import random
    random.seed(42)

    session_types = ['timer', 'breathing', 'timer', 'timer']
    patterns = [None, 'box', '478', 'deep']

    for i in range(28):
        stype = session_types[i % 4]
        duration = random.choice([300, 600, 900, 1200])
        db.session.add(MeditationSession(
            date=d(28 - i),
            session_type=stype,
            breathing_pattern=patterns[i % 4] if stype == 'breathing' else None,
            duration_seconds=duration,
            target_duration_seconds=duration,
            completed=True,
            xp_earned=20,
        ))

    db.session.flush()
    print("  Seeded 28 meditation sessions")


def seed_nutrition():
    """Profile + 50 meal entries + weight trend + meal plan"""
    import random
    random.seed(42)

    # Profile
    db.session.add(NutritionProfile(
        height_cm=178, weight_kg=79.5, age=30, sex='male',
        activity_level='moderate', calorie_target=2200,
        target_weight_kg=75, protein_target_pct=30, carbs_target_pct=40, fat_target_pct=30,
        dietary_preferences='No specific restrictions. Prefer whole foods, Mediterranean-style.',
    ))

    # Meals
    meals = [
        ('breakfast', 'Greek yogurt with berries and granola', 380, 22, 48, 12),
        ('breakfast', 'Oatmeal with banana, peanut butter, and honey', 450, 15, 62, 16),
        ('breakfast', 'Scrambled eggs on whole wheat toast with avocado', 420, 24, 32, 22),
        ('lunch', 'Grilled chicken Caesar salad', 520, 42, 18, 28),
        ('lunch', 'Turkey and avocado wrap with side salad', 580, 35, 45, 25),
        ('lunch', 'Lentil soup with crusty bread', 440, 22, 58, 10),
        ('dinner', 'Lemon herb salmon with roasted vegetables', 620, 45, 30, 28),
        ('dinner', 'Chicken stir-fry with brown rice and broccoli', 580, 38, 55, 18),
        ('dinner', 'Pasta primavera with garlic bread', 650, 22, 78, 24),
        ('snack', 'Apple with almond butter', 240, 6, 28, 14),
        ('snack', 'Protein shake with banana', 280, 30, 32, 4),
        ('snack', 'Mixed nuts and dark chocolate', 320, 8, 22, 24),
    ]

    for i in range(50):
        meal = meals[i % len(meals)]
        # Add slight variation
        cal_var = random.randint(-30, 30)
        db.session.add(NutritionEntry(
            date=d(50 - i),
            meal_type=meal[0],
            description=meal[1],
            calories=meal[2] + cal_var,
            protein_grams=meal[3] + random.randint(-3, 3),
            carbs_grams=meal[4] + random.randint(-5, 5),
            fat_grams=meal[5] + random.randint(-3, 3),
            xp_earned=5,
        ))

    # Weight entries (trending down from 81 to 79.5 over 30 days)
    for i in range(30):
        weight = 81.0 - (i * 0.05) + random.uniform(-0.3, 0.3)
        db.session.add(WeightEntry(date=d(30 - i), weight_kg=round(weight, 1)))

    # Meal plan
    db.session.add(MealPlan(
        start_date=d(7), end_date=d(0),
        content=(
            "# Weekly Meal Plan\n\n"
            "## Monday\n- **Breakfast**: Oatmeal with berries\n- **Lunch**: Grilled chicken salad\n"
            "- **Dinner**: Salmon with sweet potatoes\n\n"
            "## Tuesday\n- **Breakfast**: Scrambled eggs on toast\n- **Lunch**: Turkey wrap\n"
            "- **Dinner**: Chicken stir-fry\n\n"
            "## Wednesday\n- **Breakfast**: Greek yogurt parfait\n- **Lunch**: Lentil soup\n"
            "- **Dinner**: Pasta with vegetables\n\n"
            "## Thursday - Sunday\nRepeat with variations. Focus on hitting 2200 cal target with "
            "30% protein, 40% carbs, 30% fat split."
        ),
        grocery_list=(
            "# Grocery List\n\n"
            "- Chicken breast (1kg)\n- Salmon fillets (4x)\n- Greek yogurt (1kg)\n"
            "- Mixed berries\n- Oats\n- Brown rice\n- Sweet potatoes\n"
            "- Broccoli, spinach, bell peppers\n- Whole wheat bread\n"
            "- Eggs (12)\n- Olive oil\n- Lemons"
        ),
        calorie_target=2200,
    ))

    db.session.flush()
    print("  Seeded nutrition profile, 50 meals, 30 weight entries, 1 meal plan")


def seed_portfolio():
    """8 holdings + 5 watchlist + fundamentals + 1 briefing"""
    # Clear any existing (from app.py seed_portfolio_stocks)
    PortfolioStock.query.delete()

    holdings = [
        dict(ticker='AAPL', company='Apple Inc.', layer='Tech Giants', status='holding',
             weight=18, conviction='Very High', shares=15, avg_cost=145.0, currency='USD'),
        dict(ticker='MSFT', company='Microsoft Corp.', layer='Tech Giants', status='holding',
             weight=16, conviction='Very High', shares=8, avg_cost=320.0, currency='USD'),
        dict(ticker='GOOG', company='Alphabet Inc.', layer='Tech Giants', status='holding',
             weight=12, conviction='High', shares=12, avg_cost=130.0, currency='USD'),
        dict(ticker='AMZN', company='Amazon.com Inc.', layer='E-Commerce & Cloud', status='holding',
             weight=14, conviction='High', shares=10, avg_cost=150.0, currency='USD'),
        dict(ticker='NVDA', company='NVIDIA Corp.', layer='AI & Semiconductors', status='holding',
             weight=15, conviction='Very High', shares=3, avg_cost=450.0, currency='USD'),
        dict(ticker='BRK-B', company='Berkshire Hathaway B', layer='Value & Diversified', status='holding',
             weight=10, conviction='High', shares=5, avg_cost=350.0, currency='USD'),
        dict(ticker='GSK', company='GSK plc', layer='Healthcare', status='holding',
             weight=8, conviction='Medium', shares=40, avg_cost=1400, currency='GBp'),
        dict(ticker='NOVO-B', company='Novo Nordisk', layer='Healthcare', status='holding',
             weight=7, conviction='High', shares=10, avg_cost=750.0, currency='DKK'),
    ]
    watchlist = [
        dict(ticker='TSM', company='Taiwan Semiconductor', layer='AI & Semiconductors', status='watchlist', verdict='BUY'),
        dict(ticker='V', company='Visa Inc.', layer='Fintech', status='watchlist', verdict='HOLD'),
        dict(ticker='JNJ', company='Johnson & Johnson', layer='Healthcare', status='watchlist', verdict='BUY'),
        dict(ticker='ASML', company='ASML Holding', layer='AI & Semiconductors', status='watchlist', verdict='SPECULATIVE'),
        dict(ticker='UNH', company='UnitedHealth Group', layer='Healthcare', status='watchlist', verdict='HOLD'),
    ]

    for h in holdings:
        db.session.add(PortfolioStock(**h))
    for w in watchlist:
        db.session.add(PortfolioStock(**w))

    db.session.flush()

    # Fundamentals for all tickers
    fundamentals = [
        dict(ticker='AAPL', company_name='Apple Inc.', sector='Technology', industry='Consumer Electronics',
             current_price=178.50, market_cap=2.8e12, week_52_high=199.62, week_52_low=164.08,
             pe_trailing=28.5, pe_forward=26.2, pb_ratio=45.8, ev_ebitda=22.1, peg_ratio=2.1,
             roe=0.171, roa=0.287, gross_margin=0.458, operating_margin=0.305, net_margin=0.259,
             debt_to_equity=1.76, current_ratio=1.07, revenue_growth=0.02, earnings_growth=0.11,
             dividend_yield=0.005, payout_ratio=0.155, value_score=62,
             fetched_at=datetime.utcnow()),
        dict(ticker='MSFT', company_name='Microsoft Corp.', sector='Technology', industry='Software',
             current_price=415.20, market_cap=3.1e12, week_52_high=430.82, week_52_low=362.90,
             pe_trailing=35.2, pe_forward=30.5, pb_ratio=12.1, ev_ebitda=25.4, peg_ratio=2.4,
             roe=0.385, roa=0.195, gross_margin=0.695, operating_margin=0.445, net_margin=0.362,
             debt_to_equity=0.42, current_ratio=1.77, revenue_growth=0.13, earnings_growth=0.20,
             dividend_yield=0.007, payout_ratio=0.245, value_score=71,
             fetched_at=datetime.utcnow()),
        dict(ticker='GOOG', company_name='Alphabet Inc.', sector='Technology', industry='Internet Content',
             current_price=155.80, market_cap=1.9e12, week_52_high=170.42, week_52_low=130.67,
             pe_trailing=24.1, pe_forward=20.8, pb_ratio=6.5, ev_ebitda=16.8, peg_ratio=1.2,
             roe=0.295, roa=0.182, gross_margin=0.573, operating_margin=0.295, net_margin=0.245,
             debt_to_equity=0.11, current_ratio=2.10, revenue_growth=0.11, earnings_growth=0.28,
             dividend_yield=0.0, payout_ratio=0.0, value_score=78,
             fetched_at=datetime.utcnow()),
        dict(ticker='NVDA', company_name='NVIDIA Corp.', sector='Technology', industry='Semiconductors',
             current_price=880.50, market_cap=2.2e12, week_52_high=950.02, week_52_low=475.10,
             pe_trailing=65.0, pe_forward=38.5, pb_ratio=50.2, ev_ebitda=55.0, peg_ratio=1.5,
             roe=1.15, roa=0.55, gross_margin=0.76, operating_margin=0.62, net_margin=0.55,
             debt_to_equity=0.41, current_ratio=4.17, revenue_growth=1.22, earnings_growth=7.69,
             dividend_yield=0.0002, payout_ratio=0.01, value_score=58,
             fetched_at=datetime.utcnow()),
    ]
    for f in fundamentals:
        db.session.add(StockFundamentals(**f))

    # One portfolio briefing
    db.session.add(PortfolioBriefing(
        date=d(0),
        summary_html=(
            "<h2>Market Briefing</h2>"
            "<p><strong>Markets mixed</strong> as investors digest latest Fed minutes. "
            "Tech stocks outperform on strong AI spending forecasts.</p>"
            "<ul>"
            "<li><strong>NVDA +3.2%</strong> — New data center GPU orders exceed expectations</li>"
            "<li><strong>AAPL +0.8%</strong> — iPhone demand resilient in emerging markets</li>"
            "<li><strong>MSFT +1.1%</strong> — Azure growth accelerates for third quarter</li>"
            "<li><strong>GSK -1.5%</strong> — Pipeline setback in Phase III oncology trial</li>"
            "</ul>"
            "<p>Overall portfolio performance: <strong>+1.4%</strong> today.</p>"
        ),
        tickers_data=json.dumps(['AAPL', 'MSFT', 'GOOG', 'NVDA', 'GSK']),
    ))

    db.session.flush()
    print("  Seeded 8 holdings, 5 watchlist, 4 fundamentals, 1 briefing")


def seed_activity():
    """18 workouts + training plan with calendar days"""
    import random
    random.seed(42)

    workout_data = [
        ('run', 'Easy Recovery Run', 5.0, 30, 'easy', 135, None, None),
        ('run', 'Tempo Run', 8.0, 42, 'moderate', 155, None, None),
        ('run', 'Long Run', 16.0, 90, 'moderate', 148, None, None),
        ('run', 'Interval Training', 6.0, 35, 'hard', 168, None, None),
        ('gym', 'Upper Body Strength', None, 55, None, None,
         json.dumps([
             {"name": "Bench Press", "sets": [{"set": 1, "weight_kg": 70, "reps": 8, "failed": False},
                                               {"set": 2, "weight_kg": 70, "reps": 8, "failed": False},
                                               {"set": 3, "weight_kg": 75, "reps": 6, "failed": False}]},
             {"name": "Overhead Press", "sets": [{"set": 1, "weight_kg": 40, "reps": 10, "failed": False},
                                                  {"set": 2, "weight_kg": 40, "reps": 10, "failed": False}]},
             {"name": "Pull-ups", "sets": [{"set": 1, "weight_kg": 0, "reps": 12, "failed": False},
                                            {"set": 2, "weight_kg": 0, "reps": 10, "failed": False}]},
         ]),
         json.dumps(["chest", "shoulders", "back", "arms"])),
        ('gym', 'Lower Body Strength', None, 50, None, None,
         json.dumps([
             {"name": "Squat", "sets": [{"set": 1, "weight_kg": 90, "reps": 8, "failed": False},
                                         {"set": 2, "weight_kg": 95, "reps": 6, "failed": False},
                                         {"set": 3, "weight_kg": 100, "reps": 5, "failed": False}]},
             {"name": "Romanian Deadlift", "sets": [{"set": 1, "weight_kg": 80, "reps": 10, "failed": False},
                                                     {"set": 2, "weight_kg": 80, "reps": 10, "failed": False}]},
             {"name": "Leg Press", "sets": [{"set": 1, "weight_kg": 150, "reps": 12, "failed": False},
                                             {"set": 2, "weight_kg": 160, "reps": 10, "failed": False}]},
         ]),
         json.dumps(["quads", "hamstrings", "glutes"])),
    ]

    for i in range(18):
        idx = i % len(workout_data)
        w = workout_data[idx]
        wtype, title, dist, dur, effort, hr, exercises, muscles = w
        pace = None
        if dist and dur:
            total_secs = dur * 60
            pace_secs = total_secs / dist
            pace = f"{int(pace_secs // 60)}:{int(pace_secs % 60):02d}"
        db.session.add(Workout(
            date=d(18 - i),
            workout_type=wtype,
            title=title,
            distance_km=dist,
            duration_minutes=dur,
            pace_per_km=pace,
            effort=effort,
            heart_rate_avg=hr,
            exercises=exercises,
            muscle_groups=muscles,
            xp_earned=30,
        ))

    # Training plan
    plan = TrainingPlan(
        target_event='Spring Half Marathon',
        target_date=d(-42),  # 6 weeks from now
        current_fitness_summary='Running 25-30km/week comfortably. Recent 10K in 52:00.',
        goals='Finish half marathon in under 1:55. Maintain gym work.',
        plan_content=(
            "# Spring Half Marathon Plan\n\n"
            "## 12-Week Build\n\n"
            "**Phase 1 (Weeks 1-4): Base Building**\n"
            "- 3 runs/week, 1 gym session\n"
            "- Weekly volume: 25-35km\n\n"
            "**Phase 2 (Weeks 5-8): Build**\n"
            "- 4 runs/week, 1 gym session\n"
            "- Weekly volume: 35-45km\n"
            "- Introduce tempo runs and intervals\n\n"
            "**Phase 3 (Weeks 9-11): Peak**\n"
            "- Peak mileage: 45-50km\n"
            "- Race-pace efforts\n\n"
            "**Phase 4 (Week 12): Taper**\n"
            "- Reduce volume by 40%\n"
            "- Easy runs + strides"
        ),
        phase_summary=json.dumps([
            {"phase": "Base", "start_week": 1, "end_week": 4, "focus": "Aerobic base building"},
            {"phase": "Build", "start_week": 5, "end_week": 8, "focus": "Speed and endurance"},
            {"phase": "Peak", "start_week": 9, "end_week": 11, "focus": "Race-specific fitness"},
            {"phase": "Taper", "start_week": 12, "end_week": 12, "focus": "Recovery and sharpening"},
        ]),
        is_active=True,
    )
    db.session.add(plan)
    db.session.flush()

    # Training weeks
    for week_num in range(1, 7):
        phase = 'base' if week_num <= 2 else 'build'
        db.session.add(TrainingWeek(
            plan_id=plan.id,
            week_number=week_num,
            start_date=d(42 - (week_num - 1) * 7),
            phase=phase,
            planned_summary=f"Week {week_num}: {'Base building' if phase == 'base' else 'Speed work'}",
            planned_km=30 + week_num * 3,
            actual_km=(28 + week_num * 2.5) if week_num <= 4 else 0,
            planned_gym_sessions=1,
            actual_gym_sessions=1 if week_num <= 4 else 0,
            compliance_pct=85 if week_num <= 4 else 0,
        ))

    # Training days for the next 14 days
    day_schedule = [
        ('run', 'Easy Run', 'Easy 5K at conversational pace', 'easy', 5.0, False),
        ('rest', 'Rest Day', 'Active recovery: walk or stretch', 'rest', None, False),
        ('run', 'Tempo Run', '2K warm-up, 4K at tempo pace, 2K cool-down', 'moderate', 8.0, True),
        ('gym', 'Strength Session', 'Full body: squats, deadlifts, press, pull-ups', 'moderate', None, False),
        ('run', 'Easy Run', 'Recovery run, keep heart rate low', 'easy', 6.0, False),
        ('rest', 'Rest Day', 'Full rest or light yoga', 'rest', None, False),
        ('run', 'Long Run', 'Progressive long run: start easy, finish at marathon pace', 'moderate', 16.0, True),
    ]

    for i in range(14):
        idx = i % 7
        stype, title, desc, effort, km, key = day_schedule[idx]
        db.session.add(TrainingDay(
            plan_id=plan.id,
            date=d(7 - i),  # 7 days ago through 7 days from now
            session_type=stype,
            title=title,
            description=desc,
            phase='build',
            week_number=5 + (i // 7),
            effort_level=effort,
            planned_km=km,
            is_key_session=key,
            status='completed' if i < 7 else 'planned',
        ))

    db.session.flush()
    print("  Seeded 18 workouts + training plan + 14 calendar days")


def seed_coach():
    """30 coaching messages + goals + summaries"""
    conversations = [
        ('daily', 'user', "I've been feeling scattered this week. Too many things pulling my attention."),
        ('daily', 'assistant', "That's a really common feeling, especially when you're juggling multiple projects. "
         "Let's try to bring some clarity. If you could only accomplish ONE thing this week that would make "
         "everything else easier, what would it be?"),
        ('daily', 'user', "Probably finishing the dashboard redesign. Everything else is waiting on it."),
        ('daily', 'assistant', "Great insight! That's your **keystone task**. Here's my suggestion:\n\n"
         "1. Block 2-3 hours tomorrow morning for deep work on the dashboard\n"
         "2. Put your phone in another room during that block\n"
         "3. Tell anyone who needs you that you're unavailable until noon\n\n"
         "The scattered feeling often dissolves once the most important domino starts falling. "
         "What do you think about protecting tomorrow morning?"),
        ('exercise', 'user', "My long run yesterday was tough. Legs felt like concrete after 12K."),
        ('exercise', 'assistant', "Heavy legs at 12K could mean a few things:\n\n"
         "- **Under-fueled**: Did you eat enough carbs the night before?\n"
         "- **Under-recovered**: How's your sleep been this week?\n"
         "- **Too fast too soon**: Were you running faster than your easy pace?\n\n"
         "For your marathon training, heavy legs are actually a normal part of the adaptation process. "
         "The key is that they happen on EASY runs, not on race day. Make sure today is a full rest day."),
        ('exercise', 'user', "Good point — I think I went out too fast. My first km was way under my easy pace."),
        ('exercise', 'assistant', "Classic! It's so tempting to go out fast when you feel good. Here's a trick: "
         "**start every run 10-15 seconds per km SLOWER than your target pace**. Your body will naturally "
         "speed up as you warm up. If you feel good at km 10, THEN you can pick it up. Never before.\n\n"
         "I'm setting a goal for you: practice negative splits on your next 3 easy runs."),
        ('growth', 'user', "I've been thinking about starting a newsletter about personal development and tech."),
        ('growth', 'assistant', "That's exciting! A newsletter can be a powerful vehicle for both sharing ideas "
         "and clarifying your own thinking. A few questions to help shape this:\n\n"
         "1. **Who is your ideal reader?** (Someone like you 2 years ago?)\n"
         "2. **What's your unique angle?** The intersection of tech + personal growth is broad — what's YOUR take?\n"
         "3. **What frequency feels sustainable?** Start with biweekly rather than weekly.\n\n"
         "The best newsletters start before they're \"ready.\" Ship issue #1 within a week, even if it's imperfect."),
        ('growth', 'user', "My ideal reader is someone in tech who cares about building good habits but finds "
         "most self-help advice too generic."),
        ('growth', 'assistant', "Perfect — that's a very specific and underserved niche! Your Life Manager app "
         "is actually living proof of your approach: **building systems, not following generic advice**.\n\n"
         "Here's a content strategy:\n"
         "- Share what you're actually doing (your training, nutrition, journaling data)\n"
         "- Show the tools and systems you've built\n"
         "- Be honest about what works and what doesn't\n\n"
         "Authenticity + specificity will be your competitive advantage. I'd read that newsletter!"),
    ]

    # Add more filler messages
    areas = ['daily', 'exercise', 'weight', 'meals', 'relationships', 'growth']
    filler_user = [
        "How should I think about this?",
        "That makes sense, I'll try it.",
        "What about when I feel unmotivated?",
        "Can we revisit the goals we set last time?",
        "I made progress on the goal we discussed!",
    ]
    filler_assistant = [
        "Great question. Let's break this down step by step...",
        "I'm glad that resonated! Consistency over intensity is the key.",
        "Motivation is overrated — what you need is a system. Here's what I recommend...",
        "Absolutely! Looking at your goals, you've made solid progress on 2 out of 3. Let's dig in.",
        "That's fantastic progress! Let's celebrate that win and build on it.",
    ]

    import random
    random.seed(42)

    # Seed the specific conversations first
    for i, (area, role, content) in enumerate(conversations):
        db.session.add(CoachConversation(
            area=area, role=role, content=content,
            created_at=dt(30 - i, hour=10 + (i % 8)),
        ))

    # Add filler to reach ~30 total
    for i in range(18):
        area = random.choice(areas)
        db.session.add(CoachConversation(
            area=area, role='user', content=random.choice(filler_user),
            created_at=dt(random.randint(1, 25), hour=random.randint(8, 20)),
        ))
        db.session.add(CoachConversation(
            area=area, role='assistant', content=random.choice(filler_assistant),
            created_at=dt(random.randint(1, 25), hour=random.randint(8, 20)),
        ))

    # Goals
    goals = [
        ('exercise', 'Run half marathon under 1:55', 'Complete spring half marathon at target pace', d(-42), 'active'),
        ('daily', 'Meditate daily for 30 days', 'Build a consistent meditation habit', d(5), 'active'),
        ('growth', 'Launch newsletter', 'Publish first issue and get 50 subscribers', d(-14), 'active'),
        ('weight', 'Reach 75kg', 'Gradual weight loss through nutrition and exercise', d(-60), 'active'),
    ]
    for area, title, desc, target, status in goals:
        db.session.add(CoachGoal(area=area, title=title, description=desc, target_date=target, status=status))

    # Moods
    for i in range(15):
        area = random.choice(areas)
        score = random.uniform(-0.3, 0.9)
        label = 'positive' if score > 0.3 else ('negative' if score < -0.1 else 'neutral')
        db.session.add(CoachMood(
            area=area, score=round(score, 2), label=label,
            keywords=json.dumps(random.sample(['motivation', 'focus', 'energy', 'stress', 'progress', 'clarity'], 2)),
            created_at=dt(random.randint(1, 30)),
        ))

    # Summaries
    for area in ['daily', 'exercise', 'growth']:
        db.session.add(CoachSummary(
            area=area,
            summary_text=f"Over the past two weeks, conversations in {area} have focused on building consistency "
                         f"and maintaining momentum. Key themes: setting clear priorities, trusting the process, "
                         f"and celebrating small wins.",
            message_count=8,
            period_start=dt(30),
            period_end=dt(1),
        ))

    # Preferences
    db.session.add(CoachPreference(key='coaching_style', value='direct'))
    db.session.add(CoachPreference(key='focus_areas', value=json.dumps(['exercise', 'growth', 'daily'])))

    db.session.flush()
    print("  Seeded 30+ coach messages, 4 goals, 15 moods, 3 summaries")


def seed_newsletter():
    """3 issues, 15 ideas, 5 subscribers"""
    issues = [
        dict(title='Building Systems, Not Habits', target_date=d(60), status='sent',
             notes='First issue — intro to the philosophy behind Life Manager',
             content=(
                 "# Building Systems, Not Habits\n\n"
                 "Most productivity advice tells you to build habits. But habits are fragile — "
                 "they break when life gets chaotic.\n\n"
                 "What if you built **systems** instead?\n\n"
                 "A system is a set of tools and processes that make the right thing the easy thing. "
                 "That's why I built Life Manager: a personal operating system that tracks what matters "
                 "and reduces friction for everything else.\n\n"
                 "In this issue:\n"
                 "- Why I stopped using habit trackers\n"
                 "- The compound effect of daily journaling\n"
                 "- How I use AI as a personal coach (and why it works)\n"
             ),
             sent_at=dt(60)),
        dict(title='The Marathon Mindset', target_date=d(30), status='sent',
             notes='Training insights + the mental game of long-distance running',
             content=(
                 "# The Marathon Mindset\n\n"
                 "I'm 6 weeks into marathon training, and the biggest lesson isn't physical — it's mental.\n\n"
                 "Running long teaches you that **discomfort is not the same as danger**. "
                 "Your legs screaming at km 25 is not your body breaking down. It's your body adapting.\n\n"
                 "The same applies to every ambitious goal: the discomfort in the middle is where growth happens.\n"
             ),
             sent_at=dt(30)),
        dict(title='AI as a Thinking Partner', target_date=d(-7), status='planning',
             notes='How I use Claude for journaling, coaching, and learning — draft in progress',
             content=None),
    ]

    issue_objs = []
    for data in issues:
        issue = NewsletterIssue(**data)
        db.session.add(issue)
        issue_objs.append(issue)
    db.session.flush()

    ideas = [
        ('How daily journaling changed my decision-making', 'life', 'used', issue_objs[0].id),
        ('The compound effect of 1% daily improvement', 'life', 'used', issue_objs[0].id),
        ('Why I track everything (and what I learned)', 'tech', 'used', issue_objs[0].id),
        ('Negative splits: a metaphor for life', 'life', 'used', issue_objs[1].id),
        ('Heart rate zone training explained', 'life', 'used', issue_objs[1].id),
        ('Building an AI coaching app with Claude', 'tech', 'planned', issue_objs[2].id),
        ('The best books I read this quarter', 'recommendation', 'backlog', None),
        ('How I use spaced repetition to learn Mandarin', 'tech', 'backlog', None),
        ('The investor mindset: patience as a superpower', 'life', 'backlog', None),
        ('Mediterranean diet on a budget', 'life', 'backlog', None),
        ('My morning routine (and why it keeps changing)', 'life', 'backlog', None),
        ('Tools I use every day', 'tech', 'backlog', None),
        ('The meditation experiment: 30 days in', 'life', 'backlog', None),
        ('Open source and building in public', 'tech', 'backlog', None),
        ('What I wish I knew about personal finance at 25', 'life', 'backlog', None),
    ]

    for i, (title, category, status, issue_id) in enumerate(ideas):
        db.session.add(NewsletterIdea(
            title=title, category=category, status=status,
            issue_id=issue_id, sort_order=i,
        ))

    subscribers = [
        ('Alex Rivera', 'alex@example.com', 'en', 'Love the intersection of tech and self-improvement'),
        ('Marie Dubois', 'marie@example.com', 'fr', 'Interested in the AI coaching angle'),
        ('James Park', 'james@example.com', 'en', 'Found you through HN, excited to follow along'),
        ('Sofia Martinez', 'sofia@example.com', 'en', 'Runner + developer, this is my niche!'),
        ('Yuki Tanaka', 'yuki@example.com', 'en', 'Building something similar, want to learn from your approach'),
    ]
    for name, email, lang, notes in subscribers:
        db.session.add(NewsletterSubscriber(name=name, email=email, language=lang, notes=notes))

    db.session.flush()
    print("  Seeded 3 newsletter issues, 15 ideas, 5 subscribers")


def seed_garmin():
    """14 days of daily stats"""
    import random
    random.seed(42)

    for i in range(14):
        steps = random.randint(6000, 14000)
        db.session.add(GarminDailyStats(
            date=d(14 - i),
            steps=steps,
            step_goal=10000,
            distance_meters=steps * 0.75,
            floors_climbed=random.randint(3, 15),
            calories=random.randint(2000, 2800),
            active_calories=random.randint(400, 900),
            bmr_calories=1700,
            active_minutes=random.randint(30, 120),
            moderate_intensity_min=random.randint(15, 60),
            vigorous_intensity_min=random.randint(0, 40),
            intensity_minutes_goal=150,
            resting_hr=random.randint(52, 60),
            min_hr=random.randint(45, 55),
            max_hr=random.randint(140, 175),
            avg_stress=random.randint(25, 45),
            max_stress=random.randint(60, 90),
            stress_qualifier='low' if random.random() > 0.3 else 'medium',
            body_battery_high=random.randint(80, 100),
            body_battery_low=random.randint(15, 40),
            body_battery_at_wake=random.randint(70, 95),
            sleep_seconds=random.randint(25200, 32400),  # 7-9 hours
            sleep_deep_seconds=random.randint(3600, 7200),
            sleep_light_seconds=random.randint(10800, 16200),
            sleep_rem_seconds=random.randint(5400, 9000),
            sleep_awake_seconds=random.randint(900, 3600),
            sleep_score=random.randint(65, 95),
            avg_respiration=random.uniform(14.0, 17.0),
        ))

    db.session.flush()
    print("  Seeded 14 days of Garmin stats")


def seed_finance():
    """30 transactions + budgets + recurring costs"""
    import random
    random.seed(42)

    categories = {
        'Food & Groceries': (-80, -15),
        'Restaurants': (-60, -10),
        'Transport': (-50, -5),
        'Entertainment': (-40, -8),
        'Shopping': (-120, -20),
        'Health': (-60, -15),
        'Subscriptions': (-15, -8),
    }

    descriptions = {
        'Food & Groceries': ['Carrefour', 'Monoprix', 'Bio c\' Bon', 'Picard'],
        'Restaurants': ['La Brasserie', 'Sushi House', 'Cafe de Flore', 'Pizza Roma'],
        'Transport': ['Uber', 'RATP Metro', 'Lime Scooter', 'TGV Ticket'],
        'Entertainment': ['Netflix', 'Cinema UGC', 'Spotify', 'Book Purchase'],
        'Shopping': ['Amazon', 'Decathlon', 'Uniqlo', 'IKEA'],
        'Health': ['Pharmacy', 'Gym Membership', 'Physio Session'],
        'Subscriptions': ['Claude Pro', 'iCloud', 'Notion', 'Strava Premium'],
    }

    for i in range(30):
        cat = random.choice(list(categories.keys()))
        lo, hi = categories[cat]
        amount = round(random.uniform(lo, hi), 2)
        desc = random.choice(descriptions[cat])
        db.session.add(FinanceTransaction(
            date=d(30 - i),
            description=desc,
            amount=amount,
            currency='EUR',
            category=cat,
            transaction_type='expense',
            source='revolut_import',
            state='COMPLETED',
            import_hash=f'demo_{i}_{desc}',
        ))

    # Add 2 income transactions
    db.session.add(FinanceTransaction(
        date=d(28), description='Salary', amount=4200.0, currency='EUR',
        category='Income', transaction_type='income', source='revolut_import',
        state='COMPLETED', import_hash='demo_salary_1',
    ))
    db.session.add(FinanceTransaction(
        date=d(1), description='Salary', amount=4200.0, currency='EUR',
        category='Income', transaction_type='income', source='revolut_import',
        state='COMPLETED', import_hash='demo_salary_2',
    ))

    # Budgets
    for cat, limit in [('Food & Groceries', 400), ('Restaurants', 250), ('Transport', 150),
                        ('Entertainment', 100), ('Shopping', 200), ('Health', 100)]:
        db.session.add(FinanceBudget(category=cat, monthly_limit=limit, is_active=True))

    # Recurring costs
    recurring = [
        ('Rent', 1200, 'Housing', 'monthly', 1),
        ('Electricity', 65, 'Utilities', 'monthly', 5),
        ('Internet', 30, 'Utilities', 'monthly', 10),
        ('Phone Plan', 20, 'Utilities', 'monthly', 15),
        ('Gym', 45, 'Health', 'monthly', 1),
        ('Netflix', 13.49, 'Entertainment', 'monthly', 15),
        ('Spotify', 10.99, 'Entertainment', 'monthly', 15),
        ('Claude Pro', 20, 'Subscriptions', 'monthly', 1),
        ('iCloud 200GB', 2.99, 'Subscriptions', 'monthly', 1),
    ]
    for name, amount, cat, freq, day in recurring:
        db.session.add(FinanceRecurringCost(
            name=name, amount=amount, category=cat, frequency=freq,
            day_of_month=day, is_active=True,
        ))

    db.session.flush()
    print("  Seeded 32 transactions, 6 budgets, 9 recurring costs")


def seed_api_usage():
    """35 API usage log entries"""
    import random
    random.seed(42)

    features = [
        ('journal', 'reflect', 'claude-sonnet-4-20250514'),
        ('nutrition', 'log_meal', 'claude-haiku-4-5-20251001'),
        ('learning', 'generate_session', 'claude-sonnet-4-20250514'),
        ('coach', 'chat', 'claude-sonnet-4-20250514'),
        ('portfolio', 'briefing', 'claude-sonnet-4-20250514'),
        ('newsletter', 'draft', 'claude-sonnet-4-20250514'),
        ('activity', 'generate_plan', 'claude-sonnet-4-20250514'),
        ('nutrition', 'meal_plan', 'claude-sonnet-4-20250514'),
    ]

    for i in range(35):
        feat, endpoint, model = random.choice(features)
        input_tok = random.randint(500, 4000)
        output_tok = random.randint(200, 2000)
        pricing = CLAUDE_PRICING.get(model, (3.0, 15.0))
        cost = (input_tok * pricing[0] + output_tok * pricing[1]) / 1_000_000
        db.session.add(ApiUsageLog(
            timestamp=dt(35 - i, hour=random.randint(8, 22), minute=random.randint(0, 59)),
            feature=feat,
            endpoint=endpoint,
            model=model,
            input_tokens=input_tok,
            output_tokens=output_tok,
            cost_usd=round(cost, 6),
            duration_ms=random.randint(800, 5000),
        ))

    db.session.flush()
    print("  Seeded 35 API usage log entries")


def seed_mandarin():
    """Flashcard deck with review history"""
    cards_data = [
        ('Hello', 'ni hao', '\u4f60\u597d', 'greetings', 1, 'tone2-tone3'),
        ('Thank you', 'xie xie', '\u8c22\u8c22', 'greetings', 1, 'tone4-tone4'),
        ('Goodbye', 'zai jian', '\u518d\u89c1', 'greetings', 1, 'tone4-tone4'),
        ('How are you?', 'ni hao ma', '\u4f60\u597d\u5417', 'greetings', 1, 'tone2-tone3-tone5'),
        ('I', 'wo', '\u6211', 'pronouns', 1, 'tone3'),
        ('You', 'ni', '\u4f60', 'pronouns', 1, 'tone3'),
        ('Good morning', 'zao shang hao', '\u65e9\u4e0a\u597d', 'greetings', 1, 'tone3-tone4-tone3'),
        ('Water', 'shui', '\u6c34', 'food & drink', 1, 'tone3'),
        ('Coffee', 'ka fei', '\u5496\u5561', 'food & drink', 2, 'tone1-tone1'),
        ('Rice', 'mi fan', '\u7c73\u996d', 'food & drink', 1, 'tone3-tone4'),
        ('To eat', 'chi', '\u5403', 'verbs', 1, 'tone1'),
        ('To drink', 'he', '\u559d', 'verbs', 1, 'tone1'),
        ('To go', 'qu', '\u53bb', 'verbs', 1, 'tone4'),
        ('To come', 'lai', '\u6765', 'verbs', 1, 'tone2'),
        ('One', 'yi', '\u4e00', 'numbers', 1, 'tone1'),
        ('Two', 'er', '\u4e8c', 'numbers', 1, 'tone4'),
        ('Three', 'san', '\u4e09', 'numbers', 1, 'tone1'),
        ('Very', 'hen', '\u5f88', 'adverbs', 1, 'tone3'),
        ('Not', 'bu', '\u4e0d', 'adverbs', 1, 'tone4'),
        ('Big', 'da', '\u5927', 'adjectives', 1, 'tone4'),
        ('Small', 'xiao', '\u5c0f', 'adjectives', 1, 'tone3'),
        ('Beautiful', 'piao liang', '\u6f02\u4eae', 'adjectives', 2, 'tone4-tone4'),
        ('Friend', 'peng you', '\u670b\u53cb', 'people', 2, 'tone2-tone3'),
        ('Family', 'jia ren', '\u5bb6\u4eba', 'people', 2, 'tone1-tone2'),
        ('Teacher', 'lao shi', '\u8001\u5e08', 'people', 1, 'tone3-tone1'),
        ('How much?', 'duo shao qian', '\u591a\u5c11\u94b1', 'shopping', 2, 'tone1-tone3-tone2'),
        ('Today', 'jin tian', '\u4eca\u5929', 'time', 1, 'tone1-tone1'),
        ('Tomorrow', 'ming tian', '\u660e\u5929', 'time', 1, 'tone2-tone1'),
        ('Yesterday', 'zuo tian', '\u6628\u5929', 'time', 1, 'tone2-tone1'),
        ('Where?', 'na li', '\u54ea\u91cc', 'questions', 1, 'tone3-tone3'),
    ]

    import random
    random.seed(42)

    for i, (eng, pinyin, chars, cat, diff, tone) in enumerate(cards_data):
        card = MandarinCard(
            english=eng, pinyin=pinyin, characters=chars,
            category=cat, difficulty=diff, sort_order=i,
            tone_pattern=tone,
        )
        db.session.add(card)
        db.session.flush()

        # Add review state for first 20 cards
        if i < 20:
            repetitions = random.randint(1, 8)
            correct = max(1, repetitions - random.randint(0, 2))
            interval = min(repetitions * 2, 14)
            db.session.add(MandarinReview(
                card_id=card.id,
                ease_factor=round(2.5 + random.uniform(-0.3, 0.3), 2),
                interval_days=interval,
                repetitions=repetitions,
                next_review_date=d(-random.randint(0, 3)),
                last_reviewed=dt(random.randint(1, 10)),
                total_reviews=repetitions + random.randint(0, 3),
                correct_count=correct,
            ))

    # Sessions
    for i in range(10):
        reviewed = random.randint(8, 20)
        correct = max(5, reviewed - random.randint(1, 5))
        db.session.add(MandarinSession(
            date=d(10 - i),
            cards_reviewed=reviewed,
            cards_new=random.randint(2, 5) if i < 5 else 0,
            cards_correct=correct,
            cards_hard=reviewed - correct,
            duration_seconds=random.randint(300, 900),
            xp_earned=20,
            session_type='review',
        ))

    db.session.flush()
    print("  Seeded 30 Mandarin cards, 20 reviews, 10 sessions")


# Import pricing for API usage seed
from app import CLAUDE_PRICING


def run_seed():
    """Main seed function"""
    with app.app_context():
        # Drop and recreate all tables for a clean start
        db.drop_all()
        db.create_all()

        print("Seeding demo data...")
        seed_contacts()
        seed_journal()
        seed_game_stats()
        seed_learning()
        seed_wordle()
        seed_meditation()
        seed_nutrition()
        seed_portfolio()
        seed_activity()
        seed_coach()
        seed_newsletter()
        seed_garmin()
        seed_finance()
        seed_api_usage()
        seed_mandarin()

        db.session.commit()
        print("\nDemo data seeded successfully!")


if __name__ == '__main__':
    run_seed()
