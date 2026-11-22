"""Official 2026/27 course catalogue, independent of student-submitted text."""
import csv
import hashlib
import os

CATALOGUE = os.path.join(os.path.dirname(__file__), 'data', 'course_catalogue.csv')

# The source documents combine the international and regular programmes.
ALIASES = {
    'Management': ('Master in Management', 'International Master in Management'),
    'Finance': ('Master in Finance', 'International Master in Finance'),
    'Economics': ('Master in Economics',),
    'Business Analytics': ('Master in Business Analytics',),
    'Impact Entrepreneurship & Innovation': ('Master in Impact Entrepreneurship and Innovation',),
    'International Development & Public Policy': ('Master in International Development and Public Policy',),
    'Bachelor in Management': ('Bachelor in Management',),
    'Bachelor in Economics': ('Bachelor in Economics',),
    'Bachelor in Ocean Studies': ('Bachelor in Ocean Studies',),
}

TYPE_PRIORITY = {'MANDATORY': 0, 'EXCLUSIVE_ELECTIVE': 1, 'ELECTIVE': 2, 'OUT_PROGRAM': 3}


def import_courses(conn):
    """Upsert official courses; leave existing listings/enrolments untouched."""
    # Older databases did not have this display-only column.
    columns = {row['name'] for row in conn.execute('PRAGMA table_info(courses)')}
    if 'official_code' not in columns:
        conn.execute('ALTER TABLE courses ADD COLUMN official_code TEXT')
    with open(CATALOGUE, encoding='utf-8', newline='') as stream:
        records = list(csv.DictReader(stream))

    # The supplied 2743 code identifies TWO different IDPP courses.
    # Keep its official display code but use a unique internal key for the second.
    # TBD also gets an internal key rather than pretending TBD is a unique code.
    seen = set()
    for record in records:
        original = record['code'].strip()
        name = record['name'].strip()
        if original == '2743' and name == 'Policy Analysis Exercise':
            key = '2743-POLICY-ANALYSIS-EXERCISE'
        elif original == 'TBD':
            key = 'TBD-SOCIAL-ENTREPRENEURSHIP'
        elif original in ('XXXX', '-'):  # Pending official Bachelor codes must not collide.
            digest = hashlib.sha1((record['programme'] + ':' + name).encode('utf-8')).hexdigest()[:12]
            key = 'PENDING-' + digest
        else:
            key = original
        if key not in seen:
            conn.execute('INSERT OR IGNORE INTO courses (code,name,programme,official_code) VALUES (?,?,?,?)',
                         (key, name, '', original))
            conn.execute('UPDATE courses SET name=?, official_code=? WHERE code=?', (name, original, key))
            seen.add(key)
        course_id = conn.execute('SELECT id FROM courses WHERE code=?', (key,)).fetchone()['id']
        for full_programme in ALIASES[record['programme']]:
            existing = conn.execute('SELECT type FROM course_offerings WHERE course_id=? AND programme=?',
                                    (course_id, full_programme)).fetchone()
            chosen_type = record['type']
            if existing and TYPE_PRIORITY[existing['type']] < TYPE_PRIORITY[chosen_type]:
                chosen_type = existing['type']
            conn.execute('INSERT INTO course_offerings(course_id,programme,type) VALUES(?,?,?) '
                         'ON CONFLICT(course_id,programme) DO UPDATE SET type=excluded.type',
                         (course_id, full_programme, chosen_type))
    conn.commit()
