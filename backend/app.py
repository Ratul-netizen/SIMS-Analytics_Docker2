from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from exa_py import Exa
import datetime
from dotenv import load_dotenv
import os
import json
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import re
from difflib import SequenceMatcher
import spacy
from collections import Counter
from sqlalchemy import text

# Ensure instance directory exists
instance_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance')
os.makedirs(instance_path, exist_ok=True)

app = Flask(__name__)
# Set up portable SQLite DB path
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'instance', 'SIMS_Analytics.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
print("Database URI:", app.config['SQLALCHEMY_DATABASE_URI'])
print("Database absolute path:", os.path.abspath('instance/SIMS_Analytics.db'))
db = SQLAlchemy(app)
migrate = Migrate(app, db)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Initialize database if it doesn't exist
with app.app_context():
    db.create_all()

load_dotenv()
EXA_API_KEY = os.getenv('EXA_API_KEY')

# Load spaCy model once at startup
nlp = spacy.load('en_core_web_sm')

class Article(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    url          = db.Column(db.String, unique=True, nullable=False)
    title        = db.Column(db.String, nullable=False)
    published_at = db.Column(db.DateTime)
    author       = db.Column(db.String)
    source       = db.Column(db.String)
    sentiment    = db.Column(db.String)
    fact_check   = db.Column(db.String)
    bd_summary   = db.Column(db.Text)
    int_summary  = db.Column(db.Text)
    image        = db.Column(db.String)
    favicon      = db.Column(db.String)
    score        = db.Column(db.Float)
    extras       = db.Column(db.Text)  # Store as JSON string
    full_text    = db.Column(db.Text)
    summary_json = db.Column(db.Text)  # Store as JSON string

class BDMatch(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    title      = db.Column(db.String, nullable=False)
    source     = db.Column(db.String, nullable=False)
    url        = db.Column(db.String)

class IntMatch(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    title      = db.Column(db.String, nullable=False)
    source     = db.Column(db.String, nullable=False)
    url        = db.Column(db.String)

def safe_capitalize(val, default='Neutral'):
    if isinstance(val, str):
        return val.capitalize()
    return default

def run_exa_ingestion():
    if not EXA_API_KEY:
        print("Error: EXA_API_KEY environment variable not set")
        return
    exa = Exa(api_key=EXA_API_KEY)
    print("Running advanced Exa ingestion for Bangladesh-related news coverage by Indian Media...")
    indian_and_bd_domains = [
        "timesofindia.indiatimes.com", "hindustantimes.com", "ndtv.com", "thehindu.com", "indianexpress.com", "indiatoday.in", "news18.com", "zeenews.india.com", "aajtak.in", "abplive.com", "jagran.com", "bhaskar.com", "livehindustan.com", "business-standard.com", "economictimes.indiatimes.com", "livemint.com", "scroll.in", "thewire.in", "wionews.com", "indiatvnews.com", "newsnationtv.com", "jansatta.com", "india.com", "bdnews24.com", "thedailystar.net", "prothomalo.com", "dhakatribune.com", "newagebd.net", "financialexpress.com.bd", "theindependentbd.com", "bbc.com", "reuters.com", "aljazeera.com", "apnews.com", "cnn.com", "nytimes.com", "theguardian.com", "france24.com", "dw.com", "factwatchbd.com", "altnews.in", "boomlive.in", "factchecker.in", "thequint.com", "factcheck.afp.com", "snopes.com", "politifact.com", "fullfact.org", "apnews.com", "factcheck.org"
    ]
    # Source categorization
    indian_sources = set([
        "timesofindia.indiatimes.com", "hindustantimes.com", "ndtv.com", "thehindu.com", "indianexpress.com", "indiatoday.in", "news18.com", "zeenews.india.com", "aajtak.in", "abplive.com", "jagran.com", "bhaskar.com", "livehindustan.com", "business-standard.com", "economictimes.indiatimes.com", "livemint.com", "scroll.in", "thewire.in", "wionews.com", "indiatvnews.com", "newsnationtv.com", "jansatta.com", "india.com"
    ])
    bd_sources = set([
        'thedailystar.net', 'bdnews24.com', 'newagebd.net', 'tbsnews.net', 'dhakatribune.com', 
        'prothomalo.com', 'jugantor.com', 'kalerkantho.com', 'banglatribune.com', 'manabzamin.com', 
        'bssnews.net', 'observerbd.com', 'daily-sun.com', 'dailyjanakantha.com', 
        'thefinancialexpress.com.bd', 'unb.com.bd', 'risingbd.com', 'bangladeshpost.net', 
        'daily-bangladesh.com', 'bhorerkagoj.com', 'dailyinqilab.com', 'samakal.com', 
        'ittefaq.com.bd', 'amardesh.com', 'dailynayadiganta.com', 'dailysangram.com'
    ])
    intl_sources = set([
        'bbc.com', 'cnn.com', 'aljazeera.com', 'reuters.com', 'apnews.com', 'theguardian.com', 
        'nytimes.com', 'washingtonpost.com', 'dw.com', 'france24.com', 'abc.net.au', 'cbc.ca', 
        'cbsnews.com', 'nbcnews.com', 'foxnews.com', 'sky.com', 'japantimes.co.jp', 
        'straitstimes.com', 'channelnewsasia.com', 'scmp.com', 'gulfnews.com', 'arabnews.com', 
        'rt.com', 'tass.com', 'sputniknews.com', 'chinadaily.com.cn', 'globaltimes.cn', 
        'lemonde.fr', 'spiegel.de', 'elpais.com', 'corriere.it', 'lefigaro.fr', 'asahi.com', 
        'mainichi.jp', 'yomiuri.co.jp', 'koreatimes.co.kr', 'joongang.co.kr', 'hankyoreh.com', 
        'latimes.com', 'usatoday.com', 'bloomberg.com', 'forbes.com', 'wsj.com', 'economist.com', 
        'ft.com', 'npr.org', 'voanews.com', 'rferl.org', 'thetimes.co.uk', 'independent.co.uk', 
        'telegraph.co.uk', 'mirror.co.uk', 'express.co.uk', 'dailymail.co.uk', 'thesun.co.uk', 
        'metro.co.uk', 'eveningstandard.co.uk', 'irishtimes.com', 'rte.ie', 'heraldscotland.com', 
        'scotsman.com', 'thejournal.ie', 'breakingnews.ie', 'irishmirror.ie', 'irishnews.com', 
        'belfasttelegraph.co.uk', 'news.com.au', 'smh.com.au', 'theage.com.au', 'theaustralian.com.au'
    ])
    result = exa.search_and_contents(
        "Bangladesh-related News coverage by Indian news media",
        category="news",
        text=True,
        num_results=100,
        livecrawl="always",
        include_domains=list(indian_and_bd_domains),
        summary={
            "query": "You are a fact-checking and media-analysis assistant specialising in India–Bangladesh coverage.  For the Indian news article at {url} complete ALL of the following tasks and reply **only** with a single JSON object that exactly matches the schema provided below (do not wrap it in Markdown):  1️⃣  **extractSummary** → In ≤3 sentences, give a concise, neutral summary of the article's topic and its main claim(s).  2️⃣  **sourceDomain** → Return only the publisher's domain, e.g. \"thehindu.com\".  3️⃣  **newsCategory** → Classify into one of: Politics • Economy • Crime • Environment • Health • Technology • Diplomacy • Sports • Culture • Other  4️⃣  **sentimentTowardBangladesh** → Positive • Negative • Neutral (base it on overall tone toward Bangladesh).  5️⃣  **factCheck** → Compare the article's main claim(s) against the latest coverage in these outlets 🇧🇩 bdnews24.com, thedailystar.net, prothomalo.com, dhakatribune.com, newagebd.net, financialexpress.com.bd, theindependentbd.com 🌍 bbc.com, reuters.com, aljazeera.com, apnews.com, cnn.com, nytimes.com, theguardian.com, france24.com, dw.com ✅ Fact-checking sites: factwatchbd.com, altnews.in, boomlive.in, factchecker.in, thequint.com, factcheck.afp.com, snopes.com, politifact.com, fullfact.org, factcheck.org Return: • **status** \"verified\" | \"unverified\" • **sources** array of URLs used for verification • **similarFactChecks** array of objects { \"title\": …, \"source\": …, \"url\": … }  6️⃣  **mediaCoverageSummary** → For both Bangladeshi and international media, give ≤2-sentence summaries of how (or if) the claim was covered. Return \"Not covered\" if nothing found.  7️⃣  **supportingArticleMatches** → Two arrays: • **bangladeshiMatches** — articles from 🇧🇩 outlets • **internationalMatches** — articles from 🌍 outlets Each item: { \"title\": …, \"source\": …, \"url\": … }",
            "schema": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "title": "IndianNewsArticleAnalysis",
                "type": "object",
                "required": ["extractSummary", "sourceDomain", "newsCategory", "sentimentTowardBangladesh", "factCheck", "mediaCoverageSummary", "supportingArticleMatches"],
                "properties": {
                    "extract_summary": {
                        "type": "string",
                        "description": "≤ 3-sentence neutral overview of the article's subject and principal claim(s)."
                    },
                    "source_domain": {
                        "type": "string",
                        "description": "Root domain of the Indian news outlet that published the story (e.g., \"thehindu.com\")."
                    },
                    "news_category": {
                        "type": "string",
                        "enum": ["Politics", "Economy", "Crime", "Environment", "Health", "Technology", "Diplomacy", "Sports", "Culture", "Other"],
                        "description": "Single topical label chosen from the fixed taxonomy."
                    },
                    "sentiment_toward_bangladesh": {
                        "type": "string",
                        "enum": ["Positive", "Negative", "Neutral"],
                        "description": "Overall tone the article conveys toward Bangladesh."
                    },
                    "fact_check": {
                        "type": "object",
                        "required": ["status", "sources", "similarFactChecks"],
                        "description": "Verification results for the article's main claim(s).",
                        "properties": {
                            "status": {
                                "type": "string",
                                "enum": ["verified", "unverified"],
                                "description": "\"verified\" if supporting evidence exists in trusted outlets; otherwise \"unverified\"."
                            },
                            "sources": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "format": "uri"
                                },
                                "description": "URLs of articles or fact-checks used for verification."
                            },
                            "similar_fact_checks": {
                                "type": "array",
                                "description": "Related fact-checking articles.",
                                "items": {
                                    "type": "object",
                                    "required": ["title", "source", "url"],
                                    "properties": {
                                        "title": {
                                            "type": "string",
                                            "description": "Headline of the fact-check article."
                                        },
                                        "source": {
                                            "type": "string",
                                            "description": "Domain or outlet that published the fact-check."
                                        },
                                        "url": {
                                            "type": "string",
                                            "format": "uri",
                                            "description": "Link to the fact-check."
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "media_coverage_summary": {
                        "type": "object",
                        "required": ["bangladeshiMedia", "internationalMedia"],
                        "description": "Short comparison of how Bangladeshi vs. international outlets covered the claim.",
                        "properties": {
                            "bangladeshi_media": {
                                "type": "string",
                                "description": "≤ 2-sentence synopsis of Bangladeshi coverage, or \"Not covered\"."
                            },
                            "international_media": {
                                "type": "string",
                                "description": "≤ 2-sentence synopsis of international coverage, or \"Not covered\"."
                            }
                        }
                    },
                    "supporting_article_matches": {
                        "type": "object",
                        "required": ["bangladeshiMatches", "internationalMatches"],
                        "description": "Lists of related articles that discuss the same claim/event.",
                        "properties": {
                            "bangladeshi_matches": {
                                "type": "array",
                                "description": "Matching articles from Bangladeshi outlets.",
                                "items": {
                                    "type": "object",
                                    "required": ["title", "source", "url"],
                                    "properties": {
                                        "title": {
                                            "type": "string",
                                            "description": "Headline of the Bangladeshi article."
                                        },
                                        "source": {
                                            "type": "string",
                                            "description": "Publishing domain."
                                        },
                                        "url": {
                                            "type": "string",
                                            "format": "uri",
                                            "description": "Link to the article."
                                        }
                                    }
                                }
                            },
                            "international_matches": {
                                "type": "array",
                                "description": "Matching articles from international outlets.",
                                "items": {
                                    "type": "object",
                                    "required": ["title", "source", "url"],
                                    "properties": {
                                        "title": {
                                            "type": "string",
                                            "description": "Headline of the international article."
                                        },
                                        "source": {
                                            "type": "string",
                                            "description": "Publishing domain."
                                        },
                                        "url": {
                                            "type": "string",
                                            "format": "uri",
                                            "description": "Link to the article."
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        extras={"links": 1}
    )
    print(f"Total results: {len(result.results)}")
    for idx, item in enumerate(result.results):
        try:
            print(f"\nProcessing item {idx + 1}:")
            print("Title:", item.title)
            print("URL:", item.url)
            summary = getattr(item, 'summary', None)
            # Robust summary parsing
            if summary and isinstance(summary, str):
                try:
                    summary = json.loads(summary)
                except Exception:
                    print("Warning: Could not parse summary as JSON.")
            if not summary:
                print("No summary available, skipping.")
                continue
            # Normalize and validate fields
            def get_field(s, *keys, default=None):
                for k in keys:
                    if k in s:
                        return s[k]
                return default
            art = Article.query.filter_by(url=item.url).first() or Article(url=item.url)
            art.title = item.title
            if item.published_date:
                art.published_at = datetime.datetime.fromisoformat(item.published_date.replace('Z','+00:00'))
            else:
                art.published_at = None
            # Author extraction: if missing, try to extract from text
            art.author = getattr(item, 'author', None)
            if not art.author and item.text:
                author_match = re.search(r'By\s+([A-Za-z\s]+)', item.text)
                if author_match:
                    art.author = author_match.group(1).strip()
            # Use Exa's category if present, otherwise infer
            category = get_field(summary, 'category', default=None)
            if not category or category == "General":
                category = infer_category(item.title, getattr(item, 'text', None))
            # Source normalization
            source = get_field(summary, 'source', default='Unknown')
            if source.lower() in indian_sources:
                art.source = source
            elif source.lower() in bd_sources:
                art.source = source
            elif source.lower() in intl_sources:
                art.source = source
            else:
                art.source = 'Other'
            # Sentiment normalization
            sentiment_val = get_field(summary, 'sentiment', default='Neutral')
            sentiment = safe_capitalize(sentiment_val, default='Neutral')
            art.sentiment = sentiment
            # Fact check normalization
            fact_check_val = get_field(summary, 'fact_check', 'factCheck', default='Unverified')
            if isinstance(fact_check_val, dict):
                fact_check_status = fact_check_val.get('status', 'Unverified')
            else:
                fact_check_status = fact_check_val
            fact_check = safe_capitalize(fact_check_status, default='Unverified')
            art.fact_check = fact_check
            # Summaries
            comp = get_field(summary, 'comparison', default={})
            art.bd_summary = get_field(comp, 'bangladeshi_media', 'bangladeshiMedia', default='Not covered')
            art.int_summary = get_field(comp, 'international_media', 'internationalMedia', default='Not covered')
            # Matches (always arrays)
            bd_matches = get_field(summary, 'bangladeshi_matches', 'bangladeshiMatches', default=[])
            intl_matches = get_field(summary, 'international_matches', 'internationalMatches', default=[])
            if not isinstance(bd_matches, list):
                bd_matches = []
            if not isinstance(intl_matches, list):
                intl_matches = []
            # Secondary fuzzy search for matches if empty
            if not bd_matches:
                bd_matches = [{'title': a.title, 'source': a.source, 'url': a.url} for a in Article.query.filter(Article.source.in_(bd_sources)).all() if SequenceMatcher(None, a.title.lower(), item.title.lower()).ratio() > 0.7][:3]
            if not intl_matches:
                intl_matches = [{'title': a.title, 'source': a.source, 'url': a.url} for a in Article.query.filter(Article.source.in_(intl_sources)).all() if SequenceMatcher(None, a.title.lower(), item.title.lower()).ratio() > 0.7][:3]
            art.image = getattr(item, 'image', None)
            art.favicon = getattr(item, 'favicon', None)
            art.score = getattr(item, 'score', None)
            # Extras normalization: if links missing, extract from text
            extras = getattr(item, 'extras', {})
            if not extras.get('links') and item.text:
                links = re.findall(r'https?://\S+', item.text)
                extras['links'] = list(set(links))  # remove duplicates
            art.extras = json.dumps(extras)
            art.full_text = getattr(item, 'text', None)
            # Store only the normalized summary
            art.summary_json = json.dumps({
                'source': art.source,
                'sentiment': art.sentiment,
                'fact_check': art.fact_check,
                'category': category,
                'comparison': {
                    'bangladeshi_media': art.bd_summary,
                    'international_media': art.int_summary
                },
                'bangladeshi_matches': bd_matches,
                'international_matches': intl_matches
            }, default=str)
            db.session.add(art)
            db.session.commit()
            # Store matches
            BDMatch.query.filter_by(article_id=art.id).delete()
            for m in bd_matches[:3]:
                db.session.add(BDMatch(article_id=art.id, title=m.get('title', ''), source=m.get('source', ''), url=m.get('url', '')))
            IntMatch.query.filter_by(article_id=art.id).delete()
            for m in intl_matches[:3]:
                db.session.add(IntMatch(article_id=art.id, title=m.get('title', ''), source=m.get('source', ''), url=m.get('url', '')))
            db.session.commit()
            print(f"Committed Article: {art.id}")
        except Exception as e:
            print(f"Error processing article {getattr(item, 'title', None)}: {e}")
            db.session.rollback()
    print("\nDone.")

# CLI command
@app.cli.command('fetch-exa')
def fetch_exa():
    run_exa_ingestion()

# Scheduler uses the ingestion logic directly
def run_exa_ingestion_with_context():
    print(f"[{datetime.datetime.now()}] Scheduled Exa ingestion running...")
    with app.app_context():
        run_exa_ingestion()

scheduler = BackgroundScheduler()
scheduler.add_job(run_exa_ingestion_with_context, 'interval', minutes=10)
scheduler.start()

@app.route('/api/articles')
def list_articles():
    # Get query params
    limit = request.args.get('limit', default=20, type=int)
    offset = request.args.get('offset', default=0, type=int)
    source = request.args.get('source')
    sentiment = request.args.get('sentiment')
    start = request.args.get('start')  # ISO date string
    end = request.args.get('end')      # ISO date string
    search = request.args.get('search')

    # Build query
    query = Article.query
    if source:
        query = query.filter(Article.source == source)
    if sentiment:
        query = query.filter(Article.sentiment == sentiment)
    if start:
        try:
            start_dt = datetime.datetime.fromisoformat(start)
            query = query.filter(Article.published_at >= start_dt)
        except Exception:
            pass
    if end:
        try:
            end_dt = datetime.datetime.fromisoformat(end)
            query = query.filter(Article.published_at <= end_dt)
        except Exception:
            pass
    if search:
        like = f"%{search}%"
        query = query.filter((Article.title.ilike(like)) | (Article.full_text.ilike(like)))

    total = query.count()
    articles = query.order_by(Article.published_at.desc()).limit(limit).offset(offset).all()

    return jsonify({
        'total': total,
        'count': len(articles),
        'results': [
            {
                'id': a.id,
                'title': a.title,
                'url': a.url,
                'publishedDate': a.published_at.isoformat() if a.published_at else None,
                'author': a.author,
                'score': a.score,
                'text': a.full_text,
                'summary': json.loads(a.summary_json) if a.summary_json else None,
                'image': a.image,
                'favicon': a.favicon,
                'extras': json.loads(a.extras) if a.extras else None,
        'source': a.source,
        'sentiment': a.sentiment,
                'fact_check': a.fact_check,
                'bangladeshi_summary': a.bd_summary,
                'international_summary': a.int_summary,
                'bangladeshi_matches': [
                    {'title': m.title, 'source': m.source, 'url': m.url}
                    for m in BDMatch.query.filter_by(article_id=a.id)
                ],
                'international_matches': [
                    {'title': m.title, 'source': m.source, 'url': m.url}
                    for m in IntMatch.query.filter_by(article_id=a.id)
                ]
            }
            for a in articles
        ]
    })

@app.route('/api/articles/<int:id>')
def get_article(id):
    a = Article.query.get_or_404(id)
    # Find related articles by fuzzy title match (excluding itself)
    def similar(a_title, b_title):
        return SequenceMatcher(None, a_title, b_title).ratio() > 0.5  # adjust threshold as needed

    all_articles = Article.query.filter(Article.id != id).all()
    related = [
        {
            'id': art.id,
            'title': art.title,
            'source': art.source,
            'category': art.summary_json and json.loads(art.summary_json).get('category', 'General'),
            'sentiment': art.sentiment,
            'url': art.url
        }
        for art in all_articles
        if similar((art.title or '').lower(), (a.title or '').lower())
    ][:5]  # limit to 5

    return jsonify({
        'id': a.id,
        'title': a.title,
        'url': a.url,
        'publishedDate': a.published_at.isoformat() if a.published_at else None,
        'author': a.author,
        'score': a.score,
        'text': a.full_text,
        'summary': json.loads(a.summary_json) if a.summary_json else None,
        'image': a.image,
        'favicon': a.favicon,
        'extras': json.loads(a.extras) if a.extras else None,
        'source': a.source,
        'sentiment': a.sentiment,
        'fact_check': a.fact_check,
        'bangladeshi_summary': a.bd_summary,
        'international_summary': a.int_summary,
        'bangladeshi_matches': [
            {'title': m.title, 'source': m.source, 'url': m.url}
            for m in BDMatch.query.filter_by(article_id=a.id)
        ],
        'international_matches': [
            {'title': m.title, 'source': m.source, 'url': m.url}
            for m in IntMatch.query.filter_by(article_id=a.id)
        ],
        'related_articles': related
    })

def infer_category(title, text):
    title = (title or "").lower()
    text = (text or "").lower()
    content = f"{title} {text}"
    category_keywords = [
        ("Health", ["covid", "health", "hospital", "doctor", "vaccine", "disease", "virus", "medicine", "medical"]),
        ("Politics", ["election", "minister", "government", "parliament", "politics", "cabinet", "bjp", "congress", "policy", "bill", "law"]),
        ("Economy", ["economy", "gdp", "trade", "export", "import", "inflation", "market", "investment", "finance", "stock", "business"]),
        ("Education", ["school", "university", "education", "student", "exam", "teacher", "college", "admission"]),
        ("Security", ["security", "terror", "attack", "military", "army", "defence", "border", "police", "crime"]),
        ("Sports", ["cricket", "football", "olympic", "match", "tournament", "player", "goal", "score", "team", "league"]),
        ("Technology", ["tech", "ai", "robot", "software", "hardware", "internet", "startup", "app", "digital", "cyber"]),
        ("Environment", ["climate", "environment", "pollution", "weather", "rain", "flood", "earthquake", "disaster", "wildlife"]),
        ("International", ["us", "china", "pakistan", "bangladesh", "united nations", "global", "foreign", "international", "world"]),
        ("Culture", ["festival", "culture", "art", "music", "movie", "film", "heritage", "tradition", "literature"]),
        ("Science", ["science", "research", "study", "experiment", "discovery", "space", "nasa", "isro"]),
        ("Business", ["business", "company", "corporate", "industry", "merger", "acquisition", "startup", "entrepreneur"]),
        ("Crime", ["crime", "theft", "murder", "fraud", "scam", "arrest", "court", "trial"]),
    ]
    for cat, keywords in category_keywords:
        for kw in keywords:
            if re.search(rf'\\b{re.escape(kw)}\\b', content):
                return cat
    return "General"

def infer_sentiment(title, text):
    # Simple rule-based sentiment inference
    positive_words = ["progress", "growth", "success", "improve", "benefit", "positive", "win", "peace", "agreement", "support", "help", "good", "boost", "advance", "resolve", "cooperate", "strong", "stable", "hope", "opportunity"]
    negative_words = ["crisis", "conflict", "tension", "attack", "negative", "problem", "loss", "decline", "fail", "violence", "threat", "bad", "weak", "unstable", "fear", "concern", "risk", "danger", "protest", "dispute", "sanction"]
    content = f"{title or ''} {text or ''}".lower()
    pos = any(word in content for word in positive_words)
    neg = any(word in content for word in negative_words)
    if pos and not neg:
        return "Positive"
    elif neg and not pos:
        return "Negative"
    elif pos and neg:
        return "Cautious"
    else:
        return "Neutral"

@app.route('/api/dashboard')
def dashboard():
    def normalize_sentiment(s):
        if not s:
            return 'Neutral'
        s = s.strip().capitalize()
        if s in ['Positive', 'Negative', 'Neutral', 'Cautious']:
            return s
        # Try to match common variants
        if s.lower() == 'positive':
            return 'Positive'
        if s.lower() == 'negative':
            return 'Negative'
        if s.lower() == 'neutral':
            return 'Neutral'
        if s.lower() == 'cautious':
            return 'Cautious'
        return 'Neutral'

    # Get category and source filter from query params
    filter_category = request.args.get('category')
    filter_source = request.args.get('source')
    show_all = request.args.get('show_all', 'false').lower() == 'true'
    
    # --- Date range filter ---
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    
    # Latest Indian News Monitoring - Indian sources only
    indian_sources = [
        "timesofindia.indiatimes.com", "hindustantimes.com", "ndtv.com", "thehindu.com", "indianexpress.com", "indiatoday.in", "news18.com", "zeenews.india.com", "aajtak.in", "abplive.com", "jagran.com", "bhaskar.com", "livehindustan.com", "business-standard.com", "economictimes.indiatimes.com", "livemint.com", "scroll.in", "thewire.in", "wionews.com", "indiatvnews.com", "newsnationtv.com", "jansatta.com", "india.com"
    ]
    
    # Show ALL articles from Indian sources (no Bangladesh filtering)
    # Use flexible source matching - check both source field and URL domain
    indian_sources_set = set(indian_sources)
    
    # Get all articles and filter by source more flexibly
    all_articles_query = Article.query
    if filter_source:
        all_articles_query = all_articles_query.filter(Article.source == filter_source)
    
    # Apply date filters
    if start_date:
        try:
            start_dt = datetime.datetime.fromisoformat(start_date)
            all_articles_query = all_articles_query.filter(Article.published_at >= start_dt)
        except Exception:
            pass
    if end_date:
        try:
            end_dt = datetime.datetime.fromisoformat(end_date) + datetime.timedelta(days=1)
            all_articles_query = all_articles_query.filter(Article.published_at < end_dt)
        except Exception:
            pass
    
    # Get all articles and filter by Indian sources flexibly
    all_articles = all_articles_query.all()
    latest_news = []
    
    def get_domain(url):
        try:
            return url.split('/')[2].replace('www.', '')
        except Exception:
            return url
    
    for article in all_articles:
        # Check if article is from Indian source (flexible matching)
        is_indian_source = False
        
        # Check source field directly
        if article.source and article.source in indian_sources_set:
            is_indian_source = True
        
        # Check URL domain
        if not is_indian_source and article.url:
            domain = get_domain(article.url)
            if domain in indian_sources_set:
                is_indian_source = True
        
        if is_indian_source:
            latest_news.append(article)
    
    # Sort by date, handling NULL dates properly
    latest_news.sort(key=lambda x: x.published_at or datetime.datetime.min, reverse=True)
    
    latest_news_data = []

    # Debug counters
    total_indian_articles = len(latest_news)
    bangladesh_filtered = 0
    category_filtered = 0
    
    # Prepare sets of Bangladeshi and International sources
    bd_sources = set([
        'thedailystar.net', 'bdnews24.com', 'newagebd.net', 'tbsnews.net', 'dhakatribune.com', 
        'prothomalo.com', 'jugantor.com', 'kalerkantho.com', 'banglatribune.com', 'manabzamin.com', 
        'bssnews.net', 'observerbd.com', 'daily-sun.com', 'dailyjanakantha.com', 
        'thefinancialexpress.com.bd', 'unb.com.bd', 'risingbd.com', 'bangladeshpost.net', 
        'daily-bangladesh.com', 'bhorerkagoj.com', 'dailyinqilab.com', 'samakal.com', 
        'ittefaq.com.bd', 'amardesh.com', 'dailynayadiganta.com', 'dailysangram.com'
    ])
    intl_sources = set([
        'bbc.com', 'cnn.com', 'aljazeera.com', 'reuters.com', 'apnews.com', 'theguardian.com', 
        'nytimes.com', 'washingtonpost.com', 'dw.com', 'france24.com', 'abc.net.au', 'cbc.ca', 
        'cbsnews.com', 'nbcnews.com', 'foxnews.com', 'sky.com', 'japantimes.co.jp', 
        'straitstimes.com', 'channelnewsasia.com', 'scmp.com', 'gulfnews.com', 'arabnews.com', 
        'rt.com', 'tass.com', 'sputniknews.com', 'chinadaily.com.cn', 'globaltimes.cn', 
        'lemonde.fr', 'spiegel.de', 'elpais.com', 'corriere.it', 'lefigaro.fr', 'asahi.com', 
        'mainichi.jp', 'yomiuri.co.jp', 'koreatimes.co.kr', 'joongang.co.kr', 'hankyoreh.com', 
        'latimes.com', 'usatoday.com', 'bloomberg.com', 'forbes.com', 'wsj.com', 'economist.com', 
        'ft.com', 'npr.org', 'voanews.com', 'rferl.org', 'thetimes.co.uk', 'independent.co.uk', 
        'telegraph.co.uk', 'mirror.co.uk', 'express.co.uk', 'dailymail.co.uk', 'thesun.co.uk', 
        'metro.co.uk', 'eveningstandard.co.uk', 'irishtimes.com', 'rte.ie', 'heraldscotland.com', 
        'scotsman.com', 'thejournal.ie', 'breakingnews.ie', 'irishmirror.ie', 'irishnews.com', 
        'belfasttelegraph.co.uk', 'news.com.au', 'smh.com.au', 'theage.com.au', 'theaustralian.com.au'
    ])

    for a in latest_news:
        # --- Category: Use summary_json category if present ---
        category = None
        if a.summary_json:
            try:
                summary_obj = json.loads(a.summary_json)
                category = summary_obj.get('category')
            except Exception:
                category = None
        if not category or category == "General":
            category = infer_category(a.title, a.full_text)
        if filter_category and category != filter_category:
            continue

        # --- Fact-checking logic ---
        # Find similar articles in BD and International sources (simple fuzzy match on title)
        def similar(a, b):
            return SequenceMatcher(None, a, b).ratio() > 0.7
        bd_matches = [art for art in latest_news if get_domain(art.url) in bd_sources and similar((art.title or '').lower(), (a.title or '').lower())]
        intl_matches = [art for art in latest_news if get_domain(art.url) in intl_sources and similar((art.title or '').lower(), (a.title or '').lower())]
        agreements = 0
        contradictions = 0
        for match in bd_matches + intl_matches:
            # Compare sentiment as a proxy for agreement
            sentiment_val = match.sentiment or ''
            sentiment = normalize_sentiment(sentiment_val)
            if sentiment == 'Neutral' and (not sentiment_val or sentiment_val.strip().lower() not in ['positive', 'negative', 'neutral', 'cautious']):
                sentiment = infer_sentiment(match.title, match.full_text)
            if sentiment and a.sentiment and sentiment.lower() == a.sentiment.lower():
                agreements += 1
            else:
                contradictions += 1
        if agreements > 0 and contradictions == 0:
            fact_check = 'True'
            reason = f"Matched with {agreements} sources, all agree."
        elif contradictions > 0 and agreements == 0:
            fact_check = 'False'
            reason = f"Matched with {contradictions} sources, all contradict."
        elif agreements > 0 and contradictions > 0:
            fact_check = 'Mixed'
            reason = f"Matched with {agreements} agreeing and {contradictions} contradicting sources."
        else:
            fact_check = 'Unverified'
            reason = 'No matching articles found in Bangladeshi or International sources.'

        # --- NER extraction ---
        text_for_ner = (a.title or '') + '\n' + (a.full_text or '')
        doc = nlp(text_for_ner)
        entities = list(set([ent.text for ent in doc.ents if ent.label_ in ['PERSON', 'ORG', 'GPE', 'LOC', 'PRODUCT', 'EVENT', 'WORK_OF_ART', 'LAW', 'LANGUAGE']]))

        # --- Media Coverage Summary ---
        media_coverage_summary = {
            'bangladeshi_media': 'Covered' if len(bd_matches) > 0 else 'Not covered',
            'international_media': 'Covered' if len(intl_matches) > 0 else 'Not covered'
        }

        # --- Language ---
        language_map = {
            'timesofindia.indiatimes.com': 'English',
            'hindustantimes.com': 'English',
            'ndtv.com': 'English',
            'thehindu.com': 'English',
            'indianexpress.com': 'English',
            'indiatoday.in': 'English',
            'news18.com': 'English',
            'zeenews.india.com': 'Hindi',
            'aajtak.in': 'Hindi',
            'abplive.com': 'Hindi',
            'jagran.com': 'Hindi',
            'bhaskar.com': 'Hindi',
            'livehindustan.com': 'Hindi',
            'business-standard.com': 'English',
            'economictimes.indiatimes.com': 'English',
            'livemint.com': 'English',
            'scroll.in': 'English',
            'thewire.in': 'English',
            'wionews.com': 'English',
            'indiatvnews.com': 'Hindi',
            'newsnationtv.com': 'Hindi',
            'jansatta.com': 'Hindi',
            'india.com': 'English',
        }
        language = language_map.get(a.source, 'Other')

        # Assign sentiment robustly
        sentiment_val = a.sentiment or ''
        sentiment = normalize_sentiment(sentiment_val)
        if sentiment == 'Neutral' and (not sentiment_val or sentiment_val.strip().lower() not in ['positive', 'negative', 'neutral', 'cautious']):
            sentiment = infer_sentiment(a.title, a.full_text)
        if not sentiment:
            sentiment = 'Neutral'

        latest_news_data.append({
            'date': a.publishedDate if hasattr(a, 'publishedDate') else (a.published_at.isoformat() if a.published_at else None),
            'headline': a.title or '',
            'source': get_domain(a.url) if a.url else (a.source if a.source and a.source.lower() != 'unknown' else 'Other'),
            'category': category or 'General',
            'sentiment': sentiment,
            'fact_check': fact_check,
            'fact_check_reason': reason,
            'detailsUrl': a.url or '',
            'id': a.id,
            'entities': entities,
            'media_coverage_summary': media_coverage_summary,
            'language': language,
            'full_text': a.full_text or ''
        })

    # Timeline of Key Events (use major headlines/dates from filtered news)
    timeline_events = [
        {
            'date': item['date'],
            'event': item['headline']
        }
        for item in latest_news_data[:20]
    ]

    # Language Press Comparison (distribution by language, from filtered news)
    lang_dist = {}
    for item in latest_news_data:
        lang = item['language']
        lang_dist[lang] = lang_dist.get(lang, 0) + 1

    # Fact-Checking: Cross-Media Comparison (from filtered news)
    agreement = sum(1 for item in latest_news_data if item['fact_check'] == 'True')
    verification_status = 'Verified' if agreement > 0 else 'Unverified'

    # Tone/Sentiment Analysis (from filtered news)
    sentiments = [item['sentiment'] for item in latest_news_data]
    sentiment_counts_raw = Counter(sentiments)
    allowed_keys = ['Negative', 'Neutral', 'Positive', 'Cautious']
    sentiment_counts = {k: sentiment_counts_raw.get(k, 0) for k in allowed_keys if sentiment_counts_raw.get(k, 0) > 0}

    # --- Fact-checking verdict counts and samples ---
    verdict_counts = {'True': 0, 'False': 0, 'Mixed': 0, 'Unverified': 0}
    verdict_samples = {'True': [], 'False': [], 'Mixed': [], 'Unverified': []}
    last_updated = None
    for item in latest_news_data:
        v = item['fact_check']
        verdict_counts[v] = verdict_counts.get(v, 0) + 1
        if len(verdict_samples[v]) < 3:
            verdict_samples[v].append({'headline': item['headline'], 'source': item['source'], 'date': item['date']})
        # Track last updated
        if not last_updated or (item['date'] and item['date'] > last_updated):
            last_updated = item['date']

    # --- Enhanced Implications & Analysis ---
    implications = []
    neg = sentiment_counts.get('Negative', 0)
    pos = sentiment_counts.get('Positive', 0)
    neu = sentiment_counts.get('Neutral', 0)
    total = sum(sentiment_counts.values())
    if total > 0:
        neg_ratio = neg / total
        pos_ratio = pos / total
        neu_ratio = neu / total
        if neg_ratio > 0.6:
            implications.append({'type': 'Political Stability', 'impact': 'Very High'})
        elif neg > pos:
            implications.append({'type': 'Political Stability', 'impact': 'High'})
        if pos_ratio > 0.5:
            implications.append({'type': 'Economic Impact', 'impact': 'Strong Positive'})
        elif pos > 0:
            implications.append({'type': 'Economic Impact', 'impact': 'Medium'})
        if neu_ratio > 0.4:
            implications.append({'type': 'Social Cohesion', 'impact': 'Balanced'})
        elif neu > 0:
            implications.append({'type': 'Social Cohesion', 'impact': 'Low'})

    # --- Data-driven Predictions ---
    trend = None
    if total > 5:
        # Compare last 5 vs previous 5
        last5 = [item['sentiment'] for item in latest_news_data[-5:]]
        prev5 = [item['sentiment'] for item in latest_news_data[-10:-5]]
        last5_neg = last5.count('Negative')
        prev5_neg = prev5.count('Negative')
        if last5_neg > prev5_neg:
            trend = 'Negative sentiment is rising.'
        elif last5_neg < prev5_neg:
            trend = 'Negative sentiment is falling.'
        else:
            trend = 'Negative sentiment is stable.'
    predictions = [
        {
            'category': 'Political Landscape',
            'likelihood': min(95, 80 + (neg_ratio * 20) if total > 0 else 80),
            'timeFrame': 'Next 3 months',
            'details': f'Political unrest likelihood: {trend or "Stable"} Based on recent sentiment.'
        },
        {
            'category': 'Economic Implications',
            'likelihood': min(95, 80 + (pos_ratio * 20) if total > 0 else 80),
            'timeFrame': 'Next 6 months',
            'details': f'Economic outlook: {"Positive" if pos_ratio > 0.5 else "Cautious"}. Based on recent sentiment.'
        }
    ]

    # Key Sources Used (all unique sources in the current filtered/latest news, sorted)
    sources_in_latest = [item['source'] for item in latest_news_data if item['source'] and item['source'].lower() != 'unknown']
    key_sources = sorted(set(sources_in_latest))

    return jsonify({
        'latestIndianNews': latest_news_data,
        'timelineEvents': timeline_events,
        'languageDistribution': lang_dist,
        'factChecking': {
            'verdictCounts': verdict_counts,
            'verdictSamples': verdict_samples,
            'lastUpdated': last_updated,
            'bangladeshiAgreement': agreement,
            'internationalAgreement': 0,  # Placeholder
            'verificationStatus': verification_status
        },
        'keySources': key_sources,
        'toneSentiment': sentiment_counts,
        'implications': implications,
        'predictions': predictions
    })

@app.route('/api/fetch-latest', methods=['POST'])
def fetch_latest_api():
    run_exa_ingestion()
    return jsonify({'status': 'success', 'message': 'Fetched latest news from Exa.'})

@app.route('/api/indian-sources')
def indian_sources_api():
    indian_sources = [
        ("timesofindia.indiatimes.com", "The Times of India"),
        ("hindustantimes.com", "Hindustan Times"),
        ("ndtv.com", "NDTV"),
        ("thehindu.com", "The Hindu"),
        ("indianexpress.com", "The Indian Express"),
        ("indiatoday.in", "India Today"),
        ("news18.com", "News18"),
        ("zeenews.india.com", "Zee News"),
        ("aajtak.in", "Aaj Tak"),
        ("abplive.com", "ABP Live"),
        ("jagran.com", "Dainik Jagran"),
        ("bhaskar.com", "Dainik Bhaskar"),
        ("livehindustan.com", "Hindustan"),
        ("business-standard.com", "Business Standard"),
        ("economictimes.indiatimes.com", "The Economic Times"),
        ("livemint.com", "Mint"),
        ("scroll.in", "Scroll.in"),
        ("thewire.in", "The Wire"),
        ("wionews.com", "WION"),
        ("indiatvnews.com", "India TV"),
        ("newsnationtv.com", "News Nation"),
        ("jansatta.com", "Jansatta"),
        ("india.com", "India.com")
    ]
    return jsonify([
        {"domain": domain, "name": name} for domain, name in indian_sources]
    )

@app.route('/api/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.datetime.now().isoformat()})

@app.route('/api/database-stats')
def database_stats():
    """Get comprehensive database statistics"""
    try:
        # Count total articles
        total_articles = Article.query.count()
        
        # Count articles by source type
        indian_sources = [
            "timesofindia.indiatimes.com", "hindustantimes.com", "ndtv.com", "thehindu.com", 
            "indianexpress.com", "indiatoday.in", "news18.com", "zeenews.india.com", 
            "aajtak.in", "abplive.com", "jagran.com", "bhaskar.com", "livehindustan.com", 
            "business-standard.com", "economictimes.indiatimes.com", "livemint.com", 
            "scroll.in", "thewire.in", "wionews.com", "indiatvnews.com", "newsnationtv.com", 
            "jansatta.com", "india.com"
        ]
        
        bd_sources = [
            "bdnews24.com", "thedailystar.net", "prothomalo.com", "dhakatribune.com", 
            "newagebd.net", "financialexpress.com.bd", "theindependentbd.com"
        ]
        
        intl_sources = [
            "bbc.com", "reuters.com", "aljazeera.com", "apnews.com", "cnn.com", 
            "nytimes.com", "theguardian.com", "france24.com", "dw.com"
        ]
        
        indian_articles = Article.query.filter(Article.source.in_(indian_sources)).count()
        bd_articles = Article.query.filter(Article.source.in_(bd_sources)).count()
        intl_articles = Article.query.filter(Article.source.in_(intl_sources)).count()
        other_articles = total_articles - (indian_articles + bd_articles + intl_articles)
        
        # Count articles with Bangladesh mentions
        bangladesh_articles = Article.query.filter(
            db.or_(
                Article.title.contains('Bangladesh'),
                Article.title.contains('bangladesh'),
                Article.full_text.contains('Bangladesh'),
                Article.full_text.contains('bangladesh')
            )
        ).count()
        
        # Count BDMatch and IntMatch records
        total_bd_matches = BDMatch.query.count()
        total_int_matches = IntMatch.query.count()
        
        # Get date range of articles
        oldest_article = Article.query.filter(Article.published_at.isnot(None)).order_by(Article.published_at.asc()).first()
        newest_article = Article.query.filter(Article.published_at.isnot(None)).order_by(Article.published_at.desc()).first()
        
        # Count articles by sentiment
        sentiment_counts = {}
        sentiments = db.session.query(Article.sentiment, db.func.count(Article.sentiment)).group_by(Article.sentiment).all()
        for sentiment, count in sentiments:
            sentiment_counts[sentiment or 'Unknown'] = count
        
        # Count articles with full text
        articles_with_text = Article.query.filter(Article.full_text.isnot(None), Article.full_text != '').count()
        
        # Count articles with summary_json
        articles_with_summary = Article.query.filter(Article.summary_json.isnot(None), Article.summary_json != '').count()
        
        return jsonify({
            'total_articles': total_articles,
            'articles_by_source_type': {
                'indian_sources': indian_articles,
                'bangladeshi_sources': bd_articles,
                'international_sources': intl_articles,
                'other_sources': other_articles
            },
            'bangladesh_related_articles': bangladesh_articles,
            'matching_records': {
                'bd_matches': total_bd_matches,
                'international_matches': total_int_matches
            },
            'date_range': {
                'oldest_article': oldest_article.published_at.isoformat() if oldest_article and oldest_article.published_at else None,
                'newest_article': newest_article.published_at.isoformat() if newest_article and newest_article.published_at else None
            },
            'sentiment_distribution': sentiment_counts,
            'content_stats': {
                'articles_with_full_text': articles_with_text,
                'articles_with_summary': articles_with_summary,
                'articles_without_text': total_articles - articles_with_text
            },
            'database_path': app.config['SQLALCHEMY_DATABASE_URI'],
            'timestamp': datetime.datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True) 