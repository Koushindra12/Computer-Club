#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
init_db.py -- First-time database setup for SUG Computer Club
Run this script once to:
  1. Create the admin account
  2. Seed the Resume Building Workshop event
  3. Create MongoDB indexes

Usage:
    python init_db.py

Re-running this will update the admin password without duplicating data.
"""

import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

from werkzeug.security import generate_password_hash
from pymongo import MongoClient

MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/computerclub')
_client = MongoClient(MONGO_URI)
_db_name = MONGO_URI.rsplit('/', 1)[-1].split('?')[0] or 'computerclub'
db = _client[_db_name]

col_admins = db['admins']
col_events = db['events']


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
        col_admins.insert_one({
            'username': username,
            'password_hash': hashed,
            'created_at': datetime.now(timezone.utc)
        })
        print(f"[OK] Admin account created: username='{username}'")


def seed_resume_workshop():
    existing = col_events.find_one({'title': 'Resume Building Workshop'})
    if existing:
        print("[OK] 'Resume Building Workshop' already exists -- skipping seed.")
        return

    doc = {
        'title':       'Resume Building Workshop',
        'description': (
            'A practical workshop that helps students create professional, '
            'ATS-friendly resumes, showcase technical skills and projects, '
            'and prepare for internship and placement opportunities.'
        ),
        'date':        'To Be Announced',
        'time':        'To Be Announced',
        'venue':       'Shobhit University Gangoh',
        'reg_link':    'To Be Announced',
        'status':      'Upcoming',
        'badge':       'WORKSHOP',
        'badge_class': 'proj-badge',
        'poster':      None,
        'video':       None,
        'published':   True,
        'created_at':  datetime.now(timezone.utc),
        'updated_at':  datetime.now(timezone.utc),
    }
    result = col_events.insert_one(doc)
    print(f"[OK] Seeded 'Resume Building Workshop' (id={result.inserted_id})")


def create_indexes():
    col_events.create_index([('published', 1), ('created_at', -1)])
    col_events.create_index([('title', 1)])
    db['activities'].create_index([('published', 1), ('order', 1)])
    db['winners'].create_index([('event_id', 1), ('position', 1)])
    db['gallery'].create_index([('published', 1), ('created_at', -1)])
    db['gallery'].create_index([('category', 1)])
    print("[OK] MongoDB indexes created")


if __name__ == '__main__':
    print("=== SUG Computer Club -- Database Initialisation ===")
    setup_admin()
    seed_resume_workshop()
    create_indexes()
    print("\nDone! You can now run:  python app.py")
    print("Admin login at:         http://localhost:5000/admin/login")
