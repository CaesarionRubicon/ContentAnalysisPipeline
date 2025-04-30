#!/usr/bin/env python3
"""
scripts/alter_tag_constraint.py

Drops the old tag_type CHECK constraint on content_tags and recreates it
to include 'object'.
"""

#!/usr/bin/env python3
"""
scripts/alter_tag_constraint.py
...
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from scripts.db_utils import get_db_connection

def main():
    conn = get_db_connection()
    cur = conn.cursor()
    print("Dropping old constraint...")
    cur.execute("""
        ALTER TABLE content_creation.content_tags
        DROP CONSTRAINT IF EXISTS content_tags_tag_type_check;
    """)
    print("Adding new constraint including 'object'...")
    cur.execute("""
        ALTER TABLE content_creation.content_tags
        ADD CONSTRAINT content_tags_tag_type_check
        CHECK (tag_type IN (
            'topic', 'action', 'object', 'face', 'scene', 'entity'
        ));
    """)
    conn.commit()
    conn.close()
    print("Constraint updated successfully.")

if __name__ == "__main__":
    main()