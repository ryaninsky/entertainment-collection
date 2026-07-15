import os
import uuid
from PIL import Image
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-secret-key-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ryaninsky.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'change-me')

db = SQLAlchemy(app)

# ---- Cover specs per category ----
COVER_SPECS = {
    'film':   {'ratio': (2, 3),  'max_w': 400},
    'series': {'ratio': (2, 3),  'max_w': 400},
    'game':   {'ratio': (2, 3),  'max_w': 400},
    'book':   {'ratio': (2, 3),  'max_w': 400},
    'album':  {'ratio': (1, 1),  'max_w': 400},
    'clip':   {'ratio': (16, 9), 'max_w': 640},
}

def process_cover(file_obj, category):
    spec = COVER_SPECS.get(category, {'ratio': (2, 3), 'max_w': 400})
    rw, rh = spec['ratio']
    max_w = spec['max_w']
    img = Image.open(file_obj).convert('RGB')
    src_w, src_h = img.size
    target_ratio = rw / rh
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    elif src_ratio < target_ratio:
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        img = img.crop((0, top, src_w, top + new_h))
    if img.width > max_w:
        new_h = int(max_w * rh / rw)
        img = img.resize((max_w, new_h), Image.LANCZOS)
    import uuid as _uuid
    filename = str(_uuid.uuid4()) + '.webp'
    out_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    img.save(out_path, 'WEBP', quality=82, method=6)
    return filename

# ---- Models ----

class Work(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # film, series, album, game, clip, book
    cover = db.Column(db.String(300))
    description = db.Column(db.Text)
    release_year = db.Column(db.Integer)
    viewed_date = db.Column(db.Date)
    rating = db.Column(db.Float)
    review = db.Column(db.Text)
    author = db.Column(db.String(200))  # for books
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    hearts = db.relationship('Heart', backref='work', lazy=True, cascade='all, delete-orphan')
    highlights = db.relationship('Highlight', backref='work', lazy=True, cascade='all, delete-orphan')

class Heart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey('work.id'), nullable=False)
    visitor_id = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('work_id', 'visitor_id', name='uq_heart_work_visitor'),)

class Highlight(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey('work.id'), nullable=False)
    title = db.Column(db.String(300))
    episode_number = db.Column(db.String(50))
    note = db.Column(db.Text)

class Suggestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    category = db.Column(db.String(100))
    note = db.Column(db.Text)
    visitor_id = db.Column(db.String(64))
    status = db.Column(db.String(50), default='considering')  # considering, will_watch, maybe, unlikely
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ---- Helpers ----

def get_visitor_id():
    # Accept persisted id from JS localStorage (sent as header)
    client_id = request.headers.get('X-Visitor-Id', '').strip()
    # Validate: must be a UUID-like string (36 chars, alphanumeric + hyphens)
    import re
    if client_id and re.match(r'^[a-f0-9\-]{36}$', client_id):
        session['visitor_id'] = client_id
        return client_id
    # Fallback to session cookie
    if 'visitor_id' not in session:
        session['visitor_id'] = str(uuid.uuid4())
    return session['visitor_id']

CATEGORY_LABELS = {
    'film': 'Фильмы',
    'series': 'Сериалы',
    'anime': 'Аниме',
    'album': 'Музыка',
    'game': 'Игры',
    'clip': 'Клипы',
    'book': 'Книги',
}

# ---- Public routes ----

HOME_LIMIT = 7  # show 7 cards + 1 "more" block on home

@app.route('/')
def index():
    visitor_id = get_visitor_id()
    categories = ['film', 'series', 'anime', 'album', 'game', 'clip', 'book']
    sections = {}
    totals = {}
    for cat in categories:
        total = Work.query.filter_by(category=cat).count()
        totals[cat] = total
        q = Work.query.filter_by(category=cat).order_by(Work.release_year.desc())
        works = q.limit(HOME_LIMIT).all()
        sections[cat] = enrich_works(works, visitor_id)
    return render_template('index.html', sections=sections, category_labels=CATEGORY_LABELS,
                           visitor_id=visitor_id, totals=totals, home_limit=HOME_LIMIT)

@app.route('/category/<cat>')
def category_page(cat):
    if cat not in CATEGORY_LABELS:
        return redirect('/')
    visitor_id = get_visitor_id()
    sort = request.args.get('sort', 'year')
    q = Work.query.filter_by(category=cat)
    if sort == 'year':
        q = q.order_by(Work.release_year.desc())
    elif sort == 'new':
        q = q.order_by(Work.created_at.desc())
    elif sort == 'rate':
        q = q.order_by(Work.rating.desc())
    works = enrich_works(q.all(), visitor_id)
    return render_template('category.html', works=works, cat=cat, label=CATEGORY_LABELS[cat],
                           sort=sort, category_labels=CATEGORY_LABELS, visitor_id=visitor_id)

@app.route('/work/<int:work_id>')
def work_detail(work_id):
    visitor_id = get_visitor_id()
    work = Work.query.get_or_404(work_id)
    heart_count = Heart.query.filter_by(work_id=work_id).count()
    user_hearted = Heart.query.filter_by(work_id=work_id, visitor_id=visitor_id).first() is not None
    highlights = Highlight.query.filter_by(work_id=work_id).all()
    return render_template('work.html', work=work, heart_count=heart_count,
                           user_hearted=user_hearted, highlights=highlights,
                           category_labels=CATEGORY_LABELS, visitor_id=visitor_id)

@app.route('/suggest')
def suggest_page():
    visitor_id = get_visitor_id()
    suggestions = Suggestion.query.order_by(Suggestion.created_at.desc()).all()
    return render_template('suggest.html', suggestions=suggestions,
                           category_labels=CATEGORY_LABELS, visitor_id=visitor_id)

@app.route('/robots.txt')
def robots():
    return app.send_static_file('robots.txt')

# ---- API ----


@app.route('/api/heart/<int:work_id>', methods=['POST'])
def toggle_heart(work_id):
    from sqlalchemy.exc import IntegrityError
    visitor_id = get_visitor_id()
    existing = Heart.query.filter_by(work_id=work_id, visitor_id=visitor_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        hearted = False
    else:
        try:
            h = Heart(work_id=work_id, visitor_id=visitor_id)
            db.session.add(h)
            db.session.commit()
            hearted = True
        except IntegrityError:
            # Race condition or duplicate attempt — already hearted
            db.session.rollback()
            hearted = True
    count = Heart.query.filter_by(work_id=work_id).count()
    return jsonify({'hearted': hearted, 'count': count})

ALLOWED_CATEGORIES = {'Фильм', 'Сериал', 'Музыка', 'Игра', 'Клип', 'Книга', ''}
ALLOWED_STATUSES = {'considering', 'will_watch', 'maybe', 'unlikely', 'in_progress'}

def sanitize(value, max_len=300):
    """Strip whitespace and truncate to max_len. Returns empty string for non-strings."""
    if not isinstance(value, str):
        return ''
    return value.strip()[:max_len]

@app.route('/api/suggest', methods=['POST'])
def add_suggestion():
    data = request.json
    if not data or not isinstance(data, dict):
        return jsonify({'error': 'Invalid request'}), 400

    title = sanitize(data.get('title', ''), 300)
    if not title:
        return jsonify({'error': 'Title required'}), 400

    category = sanitize(data.get('category', ''), 100)
    if category not in ALLOWED_CATEGORIES:
        category = ''

    note = sanitize(data.get('note', ''), 1000)

    s = Suggestion(
        title=title,
        category=category,
        note=note,
        visitor_id=get_visitor_id()
    )
    db.session.add(s)
    db.session.commit()
    return jsonify({'id': s.id, 'title': s.title, 'category': s.category,
                    'note': s.note, 'status': s.status,
                    'created_at': s.created_at.strftime('%d.%m.%Y')})

# ---- Admin ----

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin'):
        return redirect('/admin/login')
    works = Work.query.order_by(Work.created_at.desc()).all()
    suggestions = Suggestion.query.order_by(Suggestion.created_at.desc()).all()
    return render_template('admin.html', works=works, suggestions=suggestions,
                           category_labels=CATEGORY_LABELS)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/admin')
        return render_template('admin_login.html', error='Неверный пароль')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/')

@app.route('/admin/add', methods=['GET', 'POST'])
def admin_add():
    if not session.get('admin'):
        return redirect('/admin/login')
    if request.method == 'POST':
        cover_filename = None
        category = request.form.get('category', 'film')
        if 'cover' in request.files and request.files['cover'].filename:
            try:
                cover_filename = process_cover(request.files['cover'], category)
            except Exception:
                cover_filename = None

        viewed_str = request.form.get('viewed_date')
        viewed_date = datetime.strptime(viewed_str, '%Y-%m-%d').date() if viewed_str else None

        work = Work(
            title=request.form['title'],
            category=request.form.get('category', 'film'),
            cover=cover_filename,
            description=request.form.get('description', ''),
            release_year=int(request.form['release_year']) if request.form.get('release_year') else None,
            viewed_date=viewed_date,
            rating=int(float(request.form['rating'])) if request.form.get('rating') else None,
            review=request.form.get('review', ''),
            author=request.form.get('author', ''),
        )
        db.session.add(work)
        db.session.flush()

        # Highlights
        highlight_titles = request.form.getlist('highlight_title[]')
        highlight_eps = request.form.getlist('highlight_ep[]')
        highlight_notes = request.form.getlist('highlight_note[]')
        for i, ht in enumerate(highlight_titles):
            if ht.strip():
                hl = Highlight(
                    work_id=work.id,
                    title=ht.strip(),
                    episode_number=highlight_eps[i] if i < len(highlight_eps) else '',
                    note=highlight_notes[i] if i < len(highlight_notes) else '',
                )
                db.session.add(hl)

        db.session.commit()
        return redirect('/admin')
    return render_template('admin_add.html', category_labels=CATEGORY_LABELS)

@app.route('/admin/delete/<int:work_id>', methods=['POST'])
def admin_delete(work_id):
    if not session.get('admin'):
        return redirect('/admin/login')
    work = Work.query.get_or_404(work_id)
    db.session.delete(work)
    db.session.commit()
    return redirect('/admin')

@app.route('/admin/suggestion/<int:sid>/status', methods=['POST'])
def update_suggestion_status(sid):
    if not session.get('admin'):
        return jsonify({'error': 'unauthorized'}), 401
    s = Suggestion.query.get_or_404(sid)
    new_status = request.json.get('status', 'considering')
    if new_status not in ALLOWED_STATUSES:
        return jsonify({'error': 'invalid status'}), 400
    s.status = new_status
    db.session.commit()
    return jsonify({'status': s.status})

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ---- Utils ----

def enrich_works(works, visitor_id):
    result = []
    for w in works:
        heart_count = Heart.query.filter_by(work_id=w.id).count()
        user_hearted = Heart.query.filter_by(work_id=w.id, visitor_id=visitor_id).first() is not None
        result.append({'work': w, 'heart_count': heart_count, 'user_hearted': user_hearted})
    return result

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=False)
