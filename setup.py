#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup.py -- One-time setup for SUG Computer Club
- Creates / updates admin account
- Seeds EXACTLY the two required upcoming events
- Removes other events (keeping winner records safe)
- Creates MongoDB indexes
- Generates and displays a new ADMIN_ACCESS_KEY if needed

Usage:  python setup.py
"""

import os, sys, secrets
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()

from werkzeug.security import generate_password_hash
from pymongo import MongoClient

MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/computerclub')
_client   = MongoClient(MONGO_URI)
_db_name  = MONGO_URI.rsplit('/', 1)[-1].split('?')[0] or 'computerclub'
db        = _client[_db_name]

col_admins     = db['admins']
col_events     = db['events']
col_activities = db['activities']
col_winners    = db['winners']
col_gallery    = db['gallery']
col_media      = db['media']

REQUIRED_EVENTS = [
    {
        'title':       'Resume Building Workshop',
        'description': (
            'A practical workshop to help students create professional, '
            'ATS-friendly resumes, highlight technical skills and projects, '
            'and prepare for internship and placement opportunities.'
        ),
        'date':        'To Be Announced',
        'time':        'To Be Announced',
        'venue':       'Shobhit University Gangoh',
        'reg_link':    'To Be Announced',
        'status':      'Upcoming',
        'badge':       'WORKSHOP',
        'badge_class': 'proj-badge',
    },
    {
        'title':       'How to Start Your Project',
        'description': (
            'A practical session to help students select a project idea, plan features, '
            'choose suitable technologies, structure the code, and begin developing '
            'a real-world project.'
        ),
        'date':        'To Be Announced',
        'time':        'To Be Announced',
        'venue':       'Shobhit University Gangoh',
        'reg_link':    'To Be Announced',
        'status':      'Upcoming',
        'badge':       'SESSION',
        'badge_class': 'css-badge',
    },
]

def setup_admin():
    username = os.environ.get('ADMIN_USERNAME', 'admin')
    password = os.environ.get('ADMIN_PASSWORD')
    if not password:
        password = input(f"Enter password for admin user '{username}': ").strip()
        if not password:
            print("ERROR: Password cannot be empty.")
            sys.exit(1)
    hashed = generate_password_hash(password)
    existing = col_admins.find_one({'username': username})
    if existing:
        col_admins.update_one({'username': username}, {'$set': {'password_hash': hashed}})
        print(f"[OK] Admin password updated for '{username}'")
    else:
        col_admins.insert_one({'username': username, 'password_hash': hashed,
                               'created_at': datetime.now(timezone.utc)})
        print(f"[OK] Admin account created: username='{username}'")


def ensure_access_key():
    existing = os.environ.get('ADMIN_ACCESS_KEY', '')
    if existing and len(existing) > 20:
        print("[OK] ADMIN_ACCESS_KEY already set in .env")
        return
    new_key = secrets.token_urlsafe(48)
    print("\n[IMPORTANT] No ADMIN_ACCESS_KEY found in .env.")
    print("Generated a new key. Add this line to your .env file:\n")
    print(f"  ADMIN_ACCESS_KEY={new_key}\n")
    print("Then restart the Flask server. Keep this key secret.\n")


def seed_required_events():
    """Ensure exactly the two required events exist. Remove others."""
    # Step 1: ensure required events exist (upsert by title)
    kept_ids = []
    for ev_data in REQUIRED_EVENTS:
        existing = col_events.find_one({'title': ev_data['title']})
        if existing:
            print(f"[OK] Event already exists: '{ev_data['title']}'")
            kept_ids.append(existing['_id'])
        else:
            doc = {**ev_data,
                   'poster': None, 'video': None, 'published': True,
                   'created_at': datetime.now(timezone.utc),
                   'updated_at': datetime.now(timezone.utc)}
            result = col_events.insert_one(doc)
            print(f"[OK] Seeded event: '{ev_data['title']}' (id={result.inserted_id})")
            kept_ids.append(result.inserted_id)

    # Step 2: find events to delete
    all_events = list(col_events.find({}, {'_id': 1, 'title': 1}))
    to_delete  = [e for e in all_events if e['_id'] not in kept_ids]

    for ev in to_delete:
        eid_str = str(ev['_id'])
        wc = col_winners.count_documents({'event_id': eid_str})
        print(f"[INFO] Removing event '{ev['title']}' (has {wc} winner records).")
        # Reassociate winners to 'general' category instead of deleting them
        if wc > 0:
            col_winners.update_many({'event_id': eid_str}, {'$set': {'event_id': '', 'event_title': ev['title']}})
            print(f"  [OK] Preserved {wc} winner record(s) — disassociated from deleted event.")
        col_media.delete_many({'parent_type': 'event', 'parent_id': eid_str})
        col_events.delete_one({'_id': ev['_id']})
        print(f"  [OK] Event deleted.")


def remove_all_activities():
    """Remove all static activities (admin will manage dynamically)."""
    count = col_activities.count_documents({})
    if count == 0:
        print("[OK] No activities to remove.")
        return
    print(f"[INFO] Removing {count} existing activity record(s).")
    for a in col_activities.find({}, {'_id': 1}):
        col_media.delete_many({'parent_type': 'activity', 'parent_id': str(a['_id'])})
    col_activities.delete_many({})
    print("[OK] All activities removed.")


def create_indexes():
    col_events.create_index([('published', 1), ('created_at', -1)])
    col_events.create_index([('title', 1)])
    col_activities.create_index([('published', 1), ('order', 1)])
    col_winners.create_index([('event_id', 1), ('position', 1)])
    col_winners.create_index([('published', 1)])
    col_gallery.create_index([('published', 1), ('created_at', -1)])
    col_gallery.create_index([('category', 1)])
    col_media.create_index([('parent_type', 1), ('parent_id', 1)])
    col_media.create_index([('published', 1)])
    print("[OK] MongoDB indexes created")


if __name__ == '__main__':
    print("=== SUG Computer Club -- Database Setup ===")
    setup_admin()
    ensure_access_key()
    seed_required_events()
    remove_all_activities()
    create_indexes()
    print("\nDone! Run: python app.py")
    print("Admin login at: http://localhost:5000/admin/login")
    print("Use Admin ID + Password + Access Key to sign in.")
