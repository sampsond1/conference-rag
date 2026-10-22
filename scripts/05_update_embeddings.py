"""
Step 5: Import Embeddings to Database
=========================================
Reads scripts/output/sentences_with_embeddings.json and imports
all records (text + embeddings) to Supabase, replacing any
existing data.

After this step, SEMANTIC SEARCH will light up green on your site!

Usage:
    python scripts/05_update_embeddings.py

Input:
    scripts/output/sentences_with_embeddings.json  — from Step 4

Prerequisites:
    - config.public.json with Supabase URL and anon key
    - config.secret.json with Supabase service key
    - Database schema created (Step 1)
    - Embeddings generated (Step 4)
"""

import json
import os
import sys
import time
import uuid

import requests
from supabase import create_client
from tqdm import tqdm


INPUT_FILE = os.path.join('scripts', 'output', 'sentences_with_embeddings.json')
BATCH_SIZE = 100
MAX_BATCH_RETRIES = 5


def load_config():
    with open('config.public.json', 'r') as f:
        public_config = json.load(f)
    with open('config.secret.json', 'r') as f:
        secrets = json.load(f)
    return public_config, secrets


def run_management_query(secrets, query):
    """Run administrative SQL through the Supabase Management API."""
    project_ref = secrets.get('SUPABASE_PROJECT_REF')
    access_token = secrets.get('SUPABASE_ACCESS_TOKEN')
    if not project_ref or not access_token:
        raise RuntimeError(
            "SUPABASE_PROJECT_REF and SUPABASE_ACCESS_TOKEN are required "
            "to safely clear and verify the table."
        )

    response = requests.post(
        f"https://api.supabase.com/v1/projects/{project_ref}/database/query",
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        },
        json={'query': query},
        timeout=60,
    )
    response.raise_for_status()
    return response.json() if response.content else None


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ {INPUT_FILE} not found. Run scripts/04_embed_data.py first.")
        sys.exit(1)

    # Load embedded records
    print("Loading embeddings data...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        records = json.load(f)

    # Verify embeddings are present
    with_embeddings = sum(1 for r in records if r.get('embedding'))
    without_embeddings = len(records) - with_embeddings

    print(f"   Loaded {len(records):,} records")
    print(f"   With embeddings:    {with_embeddings:,}")
    if without_embeddings:
        print(f"   Without embeddings: {without_embeddings:,} (will be imported without)")

    # Connect to Supabase
    public_config, secrets = load_config()
    client = create_client(public_config['SUPABASE_URL'], secrets['SUPABASE_SERVICE_KEY'])

    # Truncate existing data and re-import everything
    print("\n" + "=" * 60)
    print("Replacing database contents (truncate + re-import)")
    print("=" * 60)

    try:
        # TRUNCATE avoids a slow row-by-row delete when vectors already exist.
        run_management_query(secrets, 'TRUNCATE TABLE public.sentence_embeddings;')
        remaining = client.table('sentence_embeddings').select('id').limit(1).execute()
        if remaining.data:
            raise RuntimeError("The table still contains rows after truncation.")
        print("   Table truncated and verified empty.")
    except Exception as e:
        print(f"   ❌ Could not clear and verify the table: {e}")
        print("   Stopping without importing to avoid duplicate or mixed data.")
        sys.exit(1)

    # Batch import (much faster than individual updates!)
    print(f"\n   Importing {len(records):,} records in batches of {BATCH_SIZE}...\n")

    success = 0
    errors = 0

    for i in tqdm(range(0, len(records), BATCH_SIZE), desc="Importing"):
        batch = records[i:i + BATCH_SIZE]
        # Stable primary keys make retries safe if Supabase committed a request
        # but the connection dropped before the client received its response.
        batch_with_ids = []
        for record in batch:
            record_with_id = dict(record)
            record_with_id['id'] = str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"conference-rag:{record['talk_id']}:{record['sentence_num']}"
            ))
            batch_with_ids.append(record_with_id)

        for attempt in range(MAX_BATCH_RETRIES + 1):
            try:
                client.table('sentence_embeddings').upsert(
                    batch_with_ids, on_conflict='id'
                ).execute()
                success += len(batch)
                break
            except Exception as e:
                if attempt < MAX_BATCH_RETRIES:
                    delay = min(2 ** attempt, 30)
                    print(
                        f"\nBatch {i // BATCH_SIZE} failed; retry "
                        f"{attempt + 1}/{MAX_BATCH_RETRIES} in {delay}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    print(f"\nError at batch {i // BATCH_SIZE} after retries: {e}")
                    errors += len(batch)
        time.sleep(0.1)

    print(f"\n✅ Import complete!")
    print(f"   Success: {success:,}")
    if errors:
        print(f"   Errors:  {errors:,}")

    # Verify
    count_result = run_management_query(
        secrets,
        "SELECT COUNT(*)::int AS total, "
        "COUNT(embedding)::int AS with_embeddings "
        "FROM public.sentence_embeddings;",
    )
    if not count_result or not isinstance(count_result, list):
        raise RuntimeError(f"Unexpected database verification response: {count_result}")
    total = count_result[0]['total']
    with_emb = count_result[0]['with_embeddings']

    print(f"\n   Total rows:          {total:,}")
    print(f"   Rows with embeddings: {with_emb:,}")

    if errors or total != len(records) or with_emb != len(records):
        print("\n❌ Import verification failed. Re-run the script to retry safely.")
        sys.exit(1)

    print(f"\n🎉 Semantic Search is now ready!")
    print(f"   Refresh your site — the 🧠 Semantic Search panel should turn GREEN.")
    print(f"\nNext: Deploy edge functions to light up 🤖 RAG!")


if __name__ == '__main__':
    main()
