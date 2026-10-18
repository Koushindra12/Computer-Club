# ─────────────────────────────────────────────────────────────────────────────
# SUG Computer Club – Web Craft
# Flask + MongoDB Admin Management System v2
# Three-factor auth | Multi-file upload | Rate limiting | Persistent storage
# ─────────────────────────────────────────────────────────────────────────────

import os
import uuid
import time

from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from collections import defaultdict

from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, send_from_directory, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from bson import ObjectId
from bson.errors import InvalidId

# ── Optional: Cloudinary persistent storage (required for Vercel) ───────────────
# Set CLOUDINARY_URL=cloudinary://api_key:api_secret@cloud_name in Vercel env vars.
# Without it, files are stored locally (fine for local dev; lost on Vercel restarts).
try:
    import cloudinary
    import cloudinary.uploader
    import cloudinary.api
    _CLOUDINARY_URL = os.environ.get('CLOUDINARY_URL', '')
    if _CLOUDINARY_URL:
        cloudinary.config(cloudinary_url=_CLOUDINARY_URL)
        _USE_CLOUDINARY = True
    else:
        _USE_CLOUDINARY = False
except ImportError:
    _USE_CLOUDINARY = False

# ── App setup ─────────────────────────────────────────────────────────────────
# APP_ROOT is the absolute path to the directory containing app.py.
# Used instead of '.' in send_from_directory to be safe on Vercel where
# the process CWD at invocation time may differ from the project root.
APP_ROOT = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder='templates',
    static_folder='.',
    static_url_path=''
)

app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_UPLOAD_MB', 32)) * 1024 * 1024

# ── Three-factor auth config ───────────────────────────────────────────────────
ADMIN_ACCESS_KEY = os.environ.get('ADMIN_ACCESS_KEY', '')

# ── Rate limiting (in-memory; reset on restart — acceptable for single-server) ─
# { ip: {'count': N, 'locked_until': timestamp} }
_rate_limit = defaultdict(lambda: {'count': 0, 'locked_until': 0})
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60  # 1 min after 5 failures, doubles each time

def _get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()

def _check_rate_limit(ip):
    """Return (allowed, seconds_remaining)."""
    record = _rate_limit[ip]
    now = time.time()
    if record['locked_until'] > now:
        return False, int(record['locked_until'] - now)
    return True, 0

def _record_failure(ip):
    record = _rate_limit[ip]
    record['count'] += 1
    if record['count'] >= MAX_ATTEMPTS:
        # Exponential backoff
        multiplier = 2 ** (record['count'] - MAX_ATTEMPTS)
        lock = min(LOCKOUT_SECONDS * multiplier, 3600)  # cap at 1 hour
        record['locked_until'] = time.time() + lock
    _rate_limit[ip] = record

def _reset_rate_limit(ip):
    _rate_limit[ip] = {'count': 0, 'locked_until': 0}

# ── MongoDB ───────────────────────────────────────────────────────────────────
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/computerclub')
_client = MongoClient(MONGO_URI)
_db_name = MONGO_URI.rsplit('/', 1)[-1].split('?')[0] or 'computerclub'
db = _client[_db_name]

col_events     = db['events']
col_activities = db['activities']
col_winners    = db['winners']
col_gallery    = db['gallery']
col_admins     = db['admins']
col_media      = db['media']   # individual media items (multi-upload)

# ── Upload config ──────────────────────────────────────────────────────────────
# Use env var if set; fall back to 'uploads' locally.
# On Vercel (read-only fs except /tmp), override to /tmp/uploads automatically.
_upload_folder_env = os.environ.get('UPLOAD_FOLDER', 'uploads')
_is_vercel = os.environ.get('VERCEL') == '1' or os.environ.get('VERCEL_ENV') is not None

if _is_vercel:
    UPLOAD_FOLDER = Path('/tmp/uploads')
else:
    UPLOAD_FOLDER = Path(_upload_folder_env)

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
for sub in ('events', 'activities', 'winners', 'gallery', 'media'):
    (UPLOAD_FOLDER / sub).mkdir(exist_ok=True)

ALLOWED_IMG = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
ALLOWED_VID = {'mp4', 'webm', 'ogg', 'mov'}
ALLOWED_ALL = ALLOWED_IMG | ALLOWED_VID

def _ext(filename):
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

def allowed_file(filename, allowed=ALLOWED_ALL):
    return _ext(filename) in allowed

def save_upload(file, subfolder, allowed=ALLOWED_ALL):
    """Save one uploaded file. Returns absolute URL (Cloudinary) or relative URL (local), or None."""
    if not file or file.filename == '':
        return None
    if not allowed_file(file.filename, allowed):
        return None
    ext = _ext(file.filename)
    name = f"{uuid.uuid4().hex}.{ext}"

    if _USE_CLOUDINARY:
        # Upload to Cloudinary for persistent storage (required on Vercel)
        try:
            resource_type = 'video' if ext in ALLOWED_VID else 'image' if ext in ALLOWED_IMG else 'raw'
            result = cloudinary.uploader.upload(
                file,
                public_id=f"computerclub/{subfolder}/{name.rsplit('.', 1)[0]}",
                resource_type=resource_type,
                overwrite=False,
            )
            return result.get('secure_url')
        except Exception as e:
            app.logger.error(f'Cloudinary upload failed: {e}')
            return None
    else:
        # Local filesystem storage
        file.save(str(UPLOAD_FOLDER / subfolder / name))
        return f"/uploads/{subfolder}/{name}"

def save_uploads(files, subfolder, allowed=ALLOWED_ALL):
    """Save multiple uploaded files. Returns list of URL paths."""
    urls = []
    for f in files:
        url = save_upload(f, subfolder, allowed)
        if url:
            urls.append(url)
    return urls

def delete_upload_file(url_path):
    if not url_path:
        return
    if _USE_CLOUDINARY and url_path.startswith('https://res.cloudinary.com/'):
        # Extract public_id from Cloudinary URL and delete
        try:
            # Cloudinary URL format: https://res.cloudinary.com/<cloud>/image/upload/v<ver>/<public_id>.<ext>
            parts = url_path.split('/upload/', 1)
            if len(parts) == 2:
                public_id_with_ext = parts[1].split('/', 1)[-1] if parts[1].startswith('v') else parts[1]
                # Remove version prefix like v1234567890/
                if '/' in public_id_with_ext:
                    public_id_with_ext = public_id_with_ext.split('/', 1)[1]
                # Remove extension
                public_id = public_id_with_ext.rsplit('.', 1)[0]
                cloudinary.uploader.destroy(public_id)
        except Exception:
            pass
        return
    if not url_path.startswith('/uploads/'):
        return
    # Resolve against UPLOAD_FOLDER, not CWD.
    # url_path is like /uploads/events/abc.jpg -> strip /uploads/ prefix
    relative = url_path[len('/uploads/'):]
    abs_path = UPLOAD_FOLDER / relative
    if abs_path.exists():
        try:
            abs_path.unlink()
        except Exception:
            pass

def _count_references(url_path):
    """Count how many DB records reference this media URL."""
    if not url_path:
        return 0
    total = 0
    q = {'$or': [{'poster': url_path}, {'video': url_path}, {'photo': url_path},
                 {'media_url': url_path}, {'videos': url_path}, {'photos': url_path}]}
    for coll in [col_events, col_activities, col_winners, col_gallery, col_media]:
        total += coll.count_documents(q)
    return total

def safe_delete_file(url_path, exclude_col=None, exclude_id=None):
    """Delete file only if no other record references it."""
    if not url_path:
        return
    # Allow local /uploads/ paths AND Cloudinary https:// URLs through.
    is_local = url_path.startswith('/uploads/')
    is_cloudinary = url_path.startswith('https://res.cloudinary.com/')
    if not is_local and not is_cloudinary:
        return
    q = {'$or': [{'poster': url_path}, {'video': url_path}, {'photo': url_path},
                 {'media_url': url_path}]}
    for coll in [col_events, col_activities, col_winners, col_gallery, col_media]:
        docs = list(coll.find(q, {'_id': 1}))
        for d in docs:
            if exclude_col == coll and str(d['_id']) == str(exclude_id):
                continue
            return  # still in use
    delete_upload_file(url_path)

def to_json(doc):
    if doc is None:
        return None
    doc = dict(doc)
    doc['_id'] = str(doc['_id'])
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
        elif isinstance(v, list):
            doc[k] = [str(i) if isinstance(i, ObjectId) else i for i in v]
    return doc

# ── Auth decorators ────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

def api_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

# ══════════════════════════════════════════════════════════════════════════════
# STATIC FILE SERVING
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(str(UPLOAD_FOLDER), filename)

@app.route('/')
@app.route('/index.html')
def serve_index():
    return send_from_directory(APP_ROOT, 'index.html')

for _p in ('about', 'activities', 'contact', 'events', 'gallery', 'members'):
    def _mk(p):
        @app.route(f'/{p}.html', endpoint=f'page_{p}')
        def _r():
            return send_from_directory(APP_ROOT, f'{p}.html')
    _mk(_p)

# ── Key-generation helper endpoint (call once, store result in .env) ──────────
@app.route('/admin/generate-key')
def generate_key_info():
    """Public info page about key generation (no real key shown)."""
    return jsonify({
        'instruction': 'Run: python -c "import secrets; print(secrets.token_urlsafe(48))" to generate a key.',
        'then': 'Set ADMIN_ACCESS_KEY=<result> in your .env file and restart the server.'
    })

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN – THREE-FACTOR LOGIN
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/admin/', methods=['GET'])
@app.route('/admin/dashboard', methods=['GET'])
@login_required
def admin_dashboard():
    stats = {
        'events':     col_events.count_documents({}),
        'activities': col_activities.count_documents({}),
        'winners':    col_winners.count_documents({}),
        'gallery':    col_gallery.count_documents({}),
        'media':      col_media.count_documents({}),
    }
    return render_template('admin/dashboard.html', stats=stats)


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))

    error = None
    lockout_remaining = 0

    if request.method == 'POST':
        ip = _get_client_ip()
        allowed, remaining = _check_rate_limit(ip)
        if not allowed:
            error = f'Too many failed attempts. Please wait {remaining} seconds.'
            return render_template('admin/login.html', error=error, lockout=remaining)

        username   = request.form.get('username', '').strip()
        password   = request.form.get('password', '')
        access_key = request.form.get('access_key', '').strip()

        # Validate access key first (timing-safe comparison)
        import hmac
        key_ok = ADMIN_ACCESS_KEY and hmac.compare_digest(access_key, ADMIN_ACCESS_KEY)

        admin = col_admins.find_one({'username': username})
        pw_ok = admin and check_password_hash(admin['password_hash'], password)

        if key_ok and pw_ok:
            session.permanent = False
            session['admin_logged_in'] = True
            session['admin_username'] = username
            _reset_rate_limit(ip)
            return redirect(url_for('admin_dashboard'))
        else:
            _record_failure(ip)
            _, remaining = _check_rate_limit(ip)
            error = 'Invalid credentials. Access denied.'
            if remaining:
                error += f' Account locked for {remaining}s.'

    return render_template('admin/login.html', error=error, lockout=lockout_remaining)


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect('/')  # always return to public homepage after logout



# ── Admin section pages ───────────────────────────────────────────────────────
@app.route('/admin/events')
@login_required
def admin_events():
    return render_template('admin/events.html')

@app.route('/admin/activities')
@login_required
def admin_activities():
    return render_template('admin/activities.html')

@app.route('/admin/winners')
@login_required
def admin_winners():
    events = [to_json(e) for e in col_events.find({}, {'title': 1})]
    return render_template('admin/winners.html', events=events)

@app.route('/admin/gallery')
@login_required
def admin_gallery():
    return render_template('admin/gallery.html')

@app.route('/admin/media')
@login_required
def admin_media():
    events     = [to_json(e) for e in col_events.find({}, {'title': 1})]
    activities = [to_json(a) for a in col_activities.find({}, {'title': 1})]
    return render_template('admin/media.html', events=events, activities=activities)


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API (no auth)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/public/events')
def api_public_events():
    docs = list(col_events.find({'published': True}).sort('created_at', -1))
    return jsonify([to_json(d) for d in docs])

@app.route('/api/public/activities')
def api_public_activities():
    docs = list(col_activities.find({'published': True}).sort('order', 1))
    return jsonify([to_json(d) for d in docs])

@app.route('/api/public/gallery')
def api_public_gallery():
    docs = list(col_gallery.find({'published': True}).sort('created_at', -1))
    return jsonify([to_json(d) for d in docs])

@app.route('/api/public/winners')
def api_public_winners():
    docs = list(col_winners.find({'published': True}).sort('position', 1))
    result = []
    for w in docs:
        w = to_json(w)
        # Attach event title
        if w.get('event_id'):
            try:
                ev = col_events.find_one({'_id': ObjectId(w['event_id'])}, {'title': 1})
                w['event_title'] = ev['title'] if ev else 'General'
            except Exception:
                w['event_title'] = 'General'
        result.append(w)
    return jsonify(result)

@app.route('/api/public/media')
def api_public_media():
    """Return all published individual media items."""
    parent_type = request.args.get('parent_type')
    parent_id   = request.args.get('parent_id')
    q = {'published': True}
    if parent_type: q['parent_type'] = parent_type
    if parent_id:   q['parent_id']   = parent_id
    docs = list(col_media.find(q).sort('created_at', -1))
    return jsonify([to_json(d) for d in docs])

@app.route('/api/public/events/<eid>')
def api_public_event_single(eid):
    """Return a single published event by ID."""
    try:
        doc = col_events.find_one({'_id': ObjectId(eid), 'published': True})
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    if not doc:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(to_json(doc))

@app.route('/api/public/winners/<wid>')
def api_public_winner_single(wid):
    """Return a single published winner by ID."""
    try:
        doc = col_winners.find_one({'_id': ObjectId(wid), 'published': True})
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    if not doc:
        return jsonify({'error': 'Not found'}), 404
    w = to_json(doc)
    if w.get('event_id'):
        try:
            ev = col_events.find_one({'_id': ObjectId(w['event_id'])},
                                     {'title': 1, 'date': 1, 'venue': 1, 'published': 1})
            if ev:
                w['event_title'] = ev.get('title', '')
                w['event_date']  = ev.get('date', '')
                w['event_venue'] = ev.get('venue', '')
                w['event_published'] = ev.get('published', False)
        except Exception:
            pass
    return jsonify(w)

# ── Public server-rendered detail pages ───────────────────────────────────────

@app.route('/event/<eid>')
def public_event_detail(eid):
    """Server-rendered event detail page — works on direct URL and refresh."""
    try:
        ev = col_events.find_one({'_id': ObjectId(eid), 'published': True})
    except InvalidId:
        ev = None
    if not ev:
        return render_template('not_found.html',
                               message='Event not found or has been removed.',
                               back_url='/events.html', back_label='Back to Events'), 404
    ev = to_json(ev)
    # Fetch winners for this event
    winners = [to_json(w) for w in
               col_winners.find({'event_id': eid, 'published': True}).sort('position', 1)]
    # Fetch gallery media for this event
    gallery = [to_json(g) for g in
               col_gallery.find({'event_id': eid, 'published': True}).sort('created_at', -1)]
    # Fetch multi-upload media for this event
    media = [to_json(m) for m in
             col_media.find({'parent_type': 'event', 'parent_id': eid, 'published': True})
             .sort('created_at', -1)]
    return render_template('event_detail.html',
                           ev=ev, winners=winners, gallery=gallery, media=media)

@app.route('/winner/<wid>')
def public_winner_detail(wid):
    """Server-rendered winner detail page — works on direct URL and refresh."""
    try:
        w = col_winners.find_one({'_id': ObjectId(wid), 'published': True})
    except InvalidId:
        w = None
    if not w:
        return render_template('not_found.html',
                               message='Winner record not found or has been removed.',
                               back_url='/events.html', back_label='Back to Events'), 404
    w = to_json(w)
    event = None
    if w.get('event_id'):
        try:
            ev_doc = col_events.find_one({'_id': ObjectId(w['event_id'])},
                                         {'title': 1, 'date': 1, 'venue': 1, 'published': 1})
            if ev_doc:
                event = to_json(ev_doc)
        except Exception:
            pass
    return render_template('winner_detail.html', w=w, event=event)




# ══════════════════════════════════════════════════════════════════════════════
# ADMIN API — EVENTS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/admin/events', methods=['GET'])
@api_auth
def api_admin_events_list():
    docs = list(col_events.find({}).sort('created_at', -1))
    return jsonify([to_json(d) for d in docs])

@app.route('/api/admin/events', methods=['POST'])
@api_auth
def api_admin_events_create():
    poster_url = save_upload(request.files.get('poster'), 'events', ALLOWED_IMG)
    video_url  = save_upload(request.files.get('video'),  'events', ALLOWED_VID)
    video_link = request.form.get('video_link', '').strip()
    doc = {
        'title':        request.form.get('title', '').strip(),
        'description':  request.form.get('description', '').strip(),
        'date':         request.form.get('date', 'To Be Announced').strip() or 'To Be Announced',
        'time':         request.form.get('time', 'To Be Announced').strip() or 'To Be Announced',
        'venue':        request.form.get('venue', '').strip(),
        'reg_link':     request.form.get('reg_link', 'To Be Announced').strip() or 'To Be Announced',
        'status':       request.form.get('status', 'Upcoming'),
        'badge':        request.form.get('badge', '').strip(),
        'badge_class':  request.form.get('badge_class', '').strip(),
        'organizer':    request.form.get('organizer', '').strip(),
        'eligibility':  request.form.get('eligibility', '').strip(),
        'requirements': request.form.get('requirements', '').strip(),
        'schedule':     request.form.get('schedule', '').strip(),
        'rules':        request.form.get('rules', '').strip(),
        'poster':       poster_url,
        'video':        video_url or video_link or None,
        'published':    request.form.get('published') == 'true',
        'created_at':   datetime.now(timezone.utc),
        'updated_at':   datetime.now(timezone.utc),
    }
    if not doc['title']:
        return jsonify({'error': 'Title is required'}), 400
    result = col_events.insert_one(doc)
    return jsonify({'success': True, 'id': str(result.inserted_id)}), 201

@app.route('/api/admin/events/<eid>', methods=['GET'])
@api_auth
def api_admin_events_get(eid):
    try:
        doc = col_events.find_one({'_id': ObjectId(eid)})
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    return jsonify(to_json(doc)) if doc else (jsonify({'error': 'Not found'}), 404)

@app.route('/api/admin/events/<eid>', methods=['POST'])
@api_auth
def api_admin_events_update(eid):
    try:
        oid = ObjectId(eid)
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    doc = col_events.find_one({'_id': oid})
    if not doc:
        return jsonify({'error': 'Not found'}), 404

    upd = {
        'title':       request.form.get('title', doc.get('title', '')).strip(),
        'description': request.form.get('description', doc.get('description', '')).strip(),
        'date':        request.form.get('date', doc.get('date', 'To Be Announced')).strip() or 'To Be Announced',
        'time':        request.form.get('time', doc.get('time', 'To Be Announced')).strip() or 'To Be Announced',
        'venue':       request.form.get('venue', doc.get('venue', '')).strip(),
        'reg_link':    request.form.get('reg_link', doc.get('reg_link', 'To Be Announced')).strip() or 'To Be Announced',
        'status':      request.form.get('status', doc.get('status', 'Upcoming')),
        'badge':       request.form.get('badge', doc.get('badge', '')).strip(),
        'badge_class': request.form.get('badge_class', doc.get('badge_class', '')).strip(),
        'published':   request.form.get('published') == 'true',
        'updated_at':  datetime.now(timezone.utc),
    }
    new_poster = save_upload(request.files.get('poster'), 'events', ALLOWED_IMG)
    if new_poster:
        safe_delete_file(doc.get('poster'), col_events, oid)
        upd['poster'] = new_poster
    elif request.form.get('remove_poster') == 'true':
        safe_delete_file(doc.get('poster'), col_events, oid)
        upd['poster'] = None
    else:
        upd['poster'] = doc.get('poster')

    new_video  = save_upload(request.files.get('video'), 'events', ALLOWED_VID)
    video_link = request.form.get('video_link', '').strip()
    if new_video:
        safe_delete_file(doc.get('video'), col_events, oid)
        upd['video'] = new_video
    elif video_link:
        upd['video'] = video_link
    elif request.form.get('remove_video') == 'true':
        safe_delete_file(doc.get('video'), col_events, oid)
        upd['video'] = None
    else:
        upd['video'] = doc.get('video')

    col_events.update_one({'_id': oid}, {'$set': upd})
    return jsonify({'success': True})

@app.route('/api/admin/events/<eid>/publish', methods=['POST'])
@api_auth
def api_admin_events_publish(eid):
    try:
        oid = ObjectId(eid)
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    state = request.json.get('published', True) if request.is_json else True
    col_events.update_one({'_id': oid}, {'$set': {'published': state, 'updated_at': datetime.now(timezone.utc)}})
    return jsonify({'success': True})

@app.route('/api/admin/events/<eid>', methods=['DELETE'])
@api_auth
def api_admin_events_delete(eid):
    try:
        oid = ObjectId(eid)
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    doc = col_events.find_one({'_id': oid})
    if not doc:
        return jsonify({'error': 'Not found'}), 404
    wc = col_winners.count_documents({'event_id': str(oid)})
    if wc > 0 and request.args.get('force') != 'true':
        return jsonify({'error': f'This event has {wc} winner record(s). Pass ?force=true to delete all.'}), 409
    for w in col_winners.find({'event_id': str(oid)}):
        safe_delete_file(w.get('photo'), col_winners, w['_id'])
    col_winners.delete_many({'event_id': str(oid)})
    col_media.delete_many({'parent_type': 'event', 'parent_id': str(oid)})
    safe_delete_file(doc.get('poster'), col_events, oid)
    if doc.get('video', '').startswith('/uploads/'):
        safe_delete_file(doc.get('video'), col_events, oid)
    col_events.delete_one({'_id': oid})
    return jsonify({'success': True})


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN API — ACTIVITIES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/admin/activities', methods=['GET'])
@api_auth
def api_admin_activities_list():
    return jsonify([to_json(d) for d in col_activities.find({}).sort('order', 1)])

@app.route('/api/admin/activities', methods=['POST'])
@api_auth
def api_admin_activities_create():
    photo_url  = save_upload(request.files.get('photo'), 'activities', ALLOWED_IMG)
    video_url  = save_upload(request.files.get('video'), 'activities', ALLOWED_VID)
    video_link = request.form.get('video_link', '').strip()
    try:
        order_val = int(request.form.get('order', 99))
    except ValueError:
        order_val = 99
    doc = {
        'title':       request.form.get('title', '').strip(),
        'description': request.form.get('description', '').strip(),
        'date':        request.form.get('date', '').strip(),
        'category':    request.form.get('category', '').strip(),
        'badge':       request.form.get('badge', '').strip(),
        'badge_class': request.form.get('badge_class', '').strip(),
        'ext_link':    request.form.get('ext_link', '').strip(),
        'photo':       photo_url,
        'video':       video_url or video_link or None,
        'published':   request.form.get('published') == 'true',
        'order':       order_val,
        'created_at':  datetime.now(timezone.utc),
        'updated_at':  datetime.now(timezone.utc),
    }
    if not doc['title']:
        return jsonify({'error': 'Title is required'}), 400
    result = col_activities.insert_one(doc)
    return jsonify({'success': True, 'id': str(result.inserted_id)}), 201

@app.route('/api/admin/activities/<aid>', methods=['GET'])
@api_auth
def api_admin_activities_get(aid):
    try:
        doc = col_activities.find_one({'_id': ObjectId(aid)})
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    return jsonify(to_json(doc)) if doc else (jsonify({'error': 'Not found'}), 404)

@app.route('/api/admin/activities/<aid>', methods=['POST'])
@api_auth
def api_admin_activities_update(aid):
    try:
        oid = ObjectId(aid)
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    doc = col_activities.find_one({'_id': oid})
    if not doc:
        return jsonify({'error': 'Not found'}), 404
    try:
        order_val = int(request.form.get('order', doc.get('order', 99)))
    except ValueError:
        order_val = doc.get('order', 99)
    upd = {
        'title':       request.form.get('title', doc.get('title', '')).strip(),
        'description': request.form.get('description', doc.get('description', '')).strip(),
        'date':        request.form.get('date', doc.get('date', '')).strip(),
        'category':    request.form.get('category', doc.get('category', '')).strip(),
        'badge':       request.form.get('badge', doc.get('badge', '')).strip(),
        'badge_class': request.form.get('badge_class', doc.get('badge_class', '')).strip(),
        'ext_link':    request.form.get('ext_link', doc.get('ext_link', '')).strip(),
        'published':   request.form.get('published') == 'true',
        'order':       order_val,
        'updated_at':  datetime.now(timezone.utc),
    }
    new_photo = save_upload(request.files.get('photo'), 'activities', ALLOWED_IMG)
    if new_photo:
        safe_delete_file(doc.get('photo'), col_activities, oid)
        upd['photo'] = new_photo
    elif request.form.get('remove_photo') == 'true':
        safe_delete_file(doc.get('photo'), col_activities, oid)
        upd['photo'] = None
    else:
        upd['photo'] = doc.get('photo')
    new_video  = save_upload(request.files.get('video'), 'activities', ALLOWED_VID)
    video_link = request.form.get('video_link', '').strip()
    if new_video:
        safe_delete_file(doc.get('video'), col_activities, oid)
        upd['video'] = new_video
    elif video_link:
        upd['video'] = video_link
    elif request.form.get('remove_video') == 'true':
        safe_delete_file(doc.get('video'), col_activities, oid)
        upd['video'] = None
    else:
        upd['video'] = doc.get('video')
    col_activities.update_one({'_id': oid}, {'$set': upd})
    return jsonify({'success': True})

@app.route('/api/admin/activities/<aid>/publish', methods=['POST'])
@api_auth
def api_admin_activities_publish(aid):
    try:
        oid = ObjectId(aid)
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    state = request.json.get('published', True) if request.is_json else True
    col_activities.update_one({'_id': oid}, {'$set': {'published': state, 'updated_at': datetime.now(timezone.utc)}})
    return jsonify({'success': True})

@app.route('/api/admin/activities/<aid>', methods=['DELETE'])
@api_auth
def api_admin_activities_delete(aid):
    try:
        oid = ObjectId(aid)
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    doc = col_activities.find_one({'_id': oid})
    if not doc:
        return jsonify({'error': 'Not found'}), 404
    safe_delete_file(doc.get('photo'), col_activities, oid)
    if doc.get('video', '').startswith('/uploads/'):
        safe_delete_file(doc.get('video'), col_activities, oid)
    col_media.delete_many({'parent_type': 'activity', 'parent_id': str(oid)})
    col_activities.delete_one({'_id': oid})
    return jsonify({'success': True})


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN API — WINNERS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/admin/winners', methods=['GET'])
@api_auth
def api_admin_winners_list():
    eid = request.args.get('event_id')
    q   = {'event_id': eid} if eid else {}
    return jsonify([to_json(d) for d in col_winners.find(q).sort('position', 1)])

@app.route('/api/admin/winners', methods=['POST'])
@api_auth
def api_admin_winners_create():
    photo_url = save_upload(request.files.get('photo'), 'winners', ALLOWED_IMG)
    try:
        pos = int(request.form.get('position', 1))
    except ValueError:
        pos = 1
    doc = {
        'event_id':        request.form.get('event_id', '').strip(),
        'name':            request.form.get('name', '').strip(),
        'position':        pos,
        'department':      request.form.get('department', '').strip(),
        'year':            request.form.get('year', '').strip(),
        'achievement':     request.form.get('achievement', '').strip(),
        'project_link':    request.form.get('project_link', '').strip(),
        'project_title':   request.form.get('project_title', '').strip(),
        'project_desc':    request.form.get('project_desc', '').strip(),
        'prize_amount':    request.form.get('prize_amount', '').strip(),
        'prize_desc':      request.form.get('prize_desc', '').strip(),
        'team_name':       request.form.get('team_name', '').strip(),
        'teammates':       request.form.get('teammates', '').strip(),
        'certificate_url': request.form.get('certificate_url', '').strip(),
        'photo':           photo_url,
        'published':       request.form.get('published') == 'true',
        'created_at':      datetime.now(timezone.utc),
        'updated_at':      datetime.now(timezone.utc),
    }
    if not doc['name']:
        return jsonify({'error': 'Winner name is required'}), 400
    result = col_winners.insert_one(doc)
    return jsonify({'success': True, 'id': str(result.inserted_id)}), 201

@app.route('/api/admin/winners/<wid>', methods=['GET'])
@api_auth
def api_admin_winners_get(wid):
    try:
        doc = col_winners.find_one({'_id': ObjectId(wid)})
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    return jsonify(to_json(doc)) if doc else (jsonify({'error': 'Not found'}), 404)

@app.route('/api/admin/winners/<wid>', methods=['POST'])
@api_auth
def api_admin_winners_update(wid):
    try:
        oid = ObjectId(wid)
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    doc = col_winners.find_one({'_id': oid})
    if not doc:
        return jsonify({'error': 'Not found'}), 404
    try:
        pos = int(request.form.get('position', doc.get('position', 1)))
    except ValueError:
        pos = doc.get('position', 1)
    upd = {
        'event_id':        request.form.get('event_id', doc.get('event_id', '')).strip(),
        'name':            request.form.get('name', doc.get('name', '')).strip(),
        'position':        pos,
        'department':      request.form.get('department', doc.get('department', '')).strip(),
        'year':            request.form.get('year', doc.get('year', '')).strip(),
        'achievement':     request.form.get('achievement', doc.get('achievement', '')).strip(),
        'project_link':    request.form.get('project_link', doc.get('project_link', '')).strip(),
        'project_title':   request.form.get('project_title', doc.get('project_title', '')).strip(),
        'project_desc':    request.form.get('project_desc', doc.get('project_desc', '')).strip(),
        'prize_amount':    request.form.get('prize_amount', doc.get('prize_amount', '')).strip(),
        'prize_desc':      request.form.get('prize_desc', doc.get('prize_desc', '')).strip(),
        'team_name':       request.form.get('team_name', doc.get('team_name', '')).strip(),
        'teammates':       request.form.get('teammates', doc.get('teammates', '')).strip(),
        'certificate_url': request.form.get('certificate_url', doc.get('certificate_url', '')).strip(),
        'published':       request.form.get('published') == 'true',
        'updated_at':      datetime.now(timezone.utc),
    }
    new_photo = save_upload(request.files.get('photo'), 'winners', ALLOWED_IMG)
    if new_photo:
        safe_delete_file(doc.get('photo'), col_winners, oid)
        upd['photo'] = new_photo
    elif request.form.get('remove_photo') == 'true':
        safe_delete_file(doc.get('photo'), col_winners, oid)
        upd['photo'] = None
    else:
        upd['photo'] = doc.get('photo')
    col_winners.update_one({'_id': oid}, {'$set': upd})
    return jsonify({'success': True})

@app.route('/api/admin/winners/<wid>/publish', methods=['POST'])
@api_auth
def api_admin_winners_publish(wid):
    try:
        oid = ObjectId(wid)
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    state = request.json.get('published', True) if request.is_json else True
    col_winners.update_one({'_id': oid}, {'$set': {'published': state, 'updated_at': datetime.now(timezone.utc)}})
    return jsonify({'success': True})

@app.route('/api/admin/winners/<wid>', methods=['DELETE'])
@api_auth
def api_admin_winners_delete(wid):
    try:
        oid = ObjectId(wid)
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    doc = col_winners.find_one({'_id': oid})
    if not doc:
        return jsonify({'error': 'Not found'}), 404
    safe_delete_file(doc.get('photo'), col_winners, oid)
    col_winners.delete_one({'_id': oid})
    return jsonify({'success': True})


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN API — GALLERY
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/admin/gallery', methods=['GET'])
@api_auth
def api_admin_gallery_list():
    return jsonify([to_json(d) for d in col_gallery.find({}).sort('created_at', -1)])

@app.route('/api/admin/gallery', methods=['POST'])
@api_auth
def api_admin_gallery_create():
    media_url  = save_upload(request.files.get('media'), 'gallery', ALLOWED_ALL)
    ext_link   = request.form.get('ext_link', '').strip()
    if not media_url and not ext_link:
        return jsonify({'error': 'File or external link required'}), 400
    url_used   = media_url or ext_link
    ext        = url_used.rsplit('.', 1)[-1].lower() if '.' in url_used else ''
    mtype      = 'video' if ext in ALLOWED_VID or 'youtube' in url_used or 'youtu.be' in url_used else 'photo'
    doc = {
        'caption':    request.form.get('caption', '').strip(),
        'description':request.form.get('description', '').strip(),
        'media_url':  url_used,
        'media_type': mtype,
        'category':   request.form.get('category', 'General').strip(),
        'event_id':   request.form.get('event_id', '').strip(),
        'activity_id':request.form.get('activity_id', '').strip(),
        'published':  request.form.get('published') == 'true',
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }
    result = col_gallery.insert_one(doc)
    return jsonify({'success': True, 'id': str(result.inserted_id)}), 201

@app.route('/api/admin/gallery/<gid>', methods=['GET'])
@api_auth
def api_admin_gallery_get(gid):
    try:
        doc = col_gallery.find_one({'_id': ObjectId(gid)})
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    return jsonify(to_json(doc)) if doc else (jsonify({'error': 'Not found'}), 404)

@app.route('/api/admin/gallery/<gid>', methods=['POST'])
@api_auth
def api_admin_gallery_update(gid):
    try:
        oid = ObjectId(gid)
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    doc = col_gallery.find_one({'_id': oid})
    if not doc:
        return jsonify({'error': 'Not found'}), 404
    upd = {
        'caption':    request.form.get('caption', doc.get('caption', '')).strip(),
        'description':request.form.get('description', doc.get('description', '')).strip(),
        'category':   request.form.get('category', doc.get('category', 'General')).strip(),
        'event_id':   request.form.get('event_id', doc.get('event_id', '')).strip(),
        'activity_id':request.form.get('activity_id', doc.get('activity_id', '')).strip(),
        'published':  request.form.get('published') == 'true',
        'updated_at': datetime.now(timezone.utc),
    }
    new_media  = save_upload(request.files.get('media'), 'gallery', ALLOWED_ALL)
    ext_link   = request.form.get('ext_link', '').strip()
    if new_media:
        safe_delete_file(doc.get('media_url'), col_gallery, oid)
        ext     = new_media.rsplit('.', 1)[-1].lower()
        upd['media_url']  = new_media
        upd['media_type'] = 'video' if ext in ALLOWED_VID else 'photo'
    elif ext_link:
        upd['media_url']  = ext_link
        upd['media_type'] = 'video' if ('youtube' in ext_link or 'youtu.be' in ext_link) else 'photo'
    elif request.form.get('remove_media') == 'true':
        safe_delete_file(doc.get('media_url'), col_gallery, oid)
        upd['media_url'] = None
    else:
        upd['media_url']  = doc.get('media_url')
        upd['media_type'] = doc.get('media_type', 'photo')
    col_gallery.update_one({'_id': oid}, {'$set': upd})
    return jsonify({'success': True})

@app.route('/api/admin/gallery/<gid>/publish', methods=['POST'])
@api_auth
def api_admin_gallery_publish(gid):
    try:
        oid = ObjectId(gid)
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    state = request.json.get('published', True) if request.is_json else True
    col_gallery.update_one({'_id': oid}, {'$set': {'published': state, 'updated_at': datetime.now(timezone.utc)}})
    return jsonify({'success': True})

@app.route('/api/admin/gallery/<gid>', methods=['DELETE'])
@api_auth
def api_admin_gallery_delete(gid):
    try:
        oid = ObjectId(gid)
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    doc = col_gallery.find_one({'_id': oid})
    if not doc:
        return jsonify({'error': 'Not found'}), 404
    safe_delete_file(doc.get('media_url'), col_gallery, oid)
    col_gallery.delete_one({'_id': oid})
    return jsonify({'success': True})


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN API — MULTI-UPLOAD MEDIA (individual items attached to parents)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/admin/media', methods=['GET'])
@api_auth
def api_admin_media_list():
    parent_type = request.args.get('parent_type')
    parent_id   = request.args.get('parent_id')
    q = {}
    if parent_type: q['parent_type'] = parent_type
    if parent_id:   q['parent_id']   = parent_id
    return jsonify([to_json(d) for d in col_media.find(q).sort('created_at', -1)])

@app.route('/api/admin/media/upload', methods=['POST'])
@api_auth
def api_admin_media_upload():
    """Upload multiple files at once. Returns list of created media doc IDs."""
    parent_type = request.form.get('parent_type', 'general')
    parent_id   = request.form.get('parent_id', '')
    caption     = request.form.get('caption', '')
    published   = request.form.get('published') == 'true'
    # Map singular parent_type values to plural subfolder names.
    # 'event' -> 'events', 'activity' -> 'activities', 'general' -> 'media'
    _subfolder_map = {'event': 'events', 'activity': 'activities',
                      'events': 'events', 'activities': 'activities',
                      'winners': 'winners', 'gallery': 'gallery'}
    subfolder = _subfolder_map.get(parent_type, 'media')

    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No files provided'}), 400

    created = []
    errors  = []
    for f in files:
        url = save_upload(f, subfolder, ALLOWED_ALL)
        if not url:
            errors.append(f.filename)
            continue
        ext   = url.rsplit('.', 1)[-1].lower()
        mtype = 'video' if ext in ALLOWED_VID else 'photo'
        doc = {
            'parent_type': parent_type,
            'parent_id':   parent_id,
            'media_url':   url,
            'media_type':  mtype,
            'caption':     caption,
            'original_name': secure_filename(f.filename),
            'published':   published,
            'created_at':  datetime.now(timezone.utc),
        }
        r = col_media.insert_one(doc)
        created.append({'id': str(r.inserted_id), 'url': url, 'type': mtype})

    return jsonify({'success': True, 'created': created, 'errors': errors}), 201

@app.route('/api/admin/media/<mid>', methods=['GET'])
@api_auth
def api_admin_media_get(mid):
    try:
        doc = col_media.find_one({'_id': ObjectId(mid)})
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    return jsonify(to_json(doc)) if doc else (jsonify({'error': 'Not found'}), 404)

@app.route('/api/admin/media/<mid>', methods=['POST'])
@api_auth
def api_admin_media_update(mid):
    try:
        oid = ObjectId(mid)
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    doc = col_media.find_one({'_id': oid})
    if not doc:
        return jsonify({'error': 'Not found'}), 404
    upd = {
        'caption':   request.form.get('caption', doc.get('caption', '')),
        'published': request.form.get('published') == 'true',
    }
    new_file = save_upload(request.files.get('file'), doc.get('parent_type', 'media'), ALLOWED_ALL)
    if new_file:
        safe_delete_file(doc.get('media_url'), col_media, oid)
        ext = new_file.rsplit('.', 1)[-1].lower()
        upd['media_url']  = new_file
        upd['media_type'] = 'video' if ext in ALLOWED_VID else 'photo'
    col_media.update_one({'_id': oid}, {'$set': upd})
    return jsonify({'success': True})

@app.route('/api/admin/media/<mid>/publish', methods=['POST'])
@api_auth
def api_admin_media_publish(mid):
    try:
        oid = ObjectId(mid)
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    state = request.json.get('published', True) if request.is_json else True
    col_media.update_one({'_id': oid}, {'$set': {'published': state}})
    return jsonify({'success': True})

@app.route('/api/admin/media/<mid>', methods=['DELETE'])
@api_auth
def api_admin_media_delete(mid):
    try:
        oid = ObjectId(mid)
    except InvalidId:
        return jsonify({'error': 'Invalid ID'}), 400
    doc = col_media.find_one({'_id': oid})
    if not doc:
        return jsonify({'error': 'Not found'}), 404
    safe_delete_file(doc.get('media_url'), col_media, oid)
    col_media.delete_one({'_id': oid})
    return jsonify({'success': True})

@app.route('/api/admin/media/bulk-delete', methods=['POST'])
@api_auth
def api_admin_media_bulk_delete():
    ids = request.json.get('ids', []) if request.is_json else []
    if not ids:
        return jsonify({'error': 'No IDs provided'}), 400
    deleted = 0
    for mid in ids:
        try:
            oid = ObjectId(mid)
        except Exception:
            continue
        doc = col_media.find_one({'_id': oid})
        if doc:
            safe_delete_file(doc.get('media_url'), col_media, oid)
            col_media.delete_one({'_id': oid})
            deleted += 1
    return jsonify({'success': True, 'deleted': deleted})


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
