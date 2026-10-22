"""
Step 4: Generate Embeddings
===============================
Reads scripts/output/sentences.json and generates Gemini embeddings
for each sentence. Saves the result to scripts/output/sentences_with_embeddings.json.

This is the most API-intensive step. The output is saved to disk so you
won't lose your work if the next step fails or hits a quota limit.

Usage:
    python scripts/04_embed_data.py

Input:
    scripts/output/sentences.json  — from Step 3 (import)

Output:
    scripts/output/sentences_with_embeddings.json  — sentence records with embedding vectors

Prerequisites:
    - config.secret.json with GEMINI_API_KEY
    - scripts/output/sentences.json from the import step
"""

import json
import os
import sys
import time

from google import genai
from google.genai import types
from tqdm import tqdm


INPUT_FILE = os.path.join('scripts', 'output', 'sentences.json')
OUTPUT_FILE = os.path.join('scripts', 'output', 'sentences_with_embeddings.json')
BATCH_SIZE = 100
EMBEDDING_MODEL = 'gemini-embedding-2'
EMBEDDING_DIMENSIONS = 1536
RATE_LIMIT_RETRY_SECONDS = 60
SECONDS_BETWEEN_BATCHES = 2


def load_secrets():
    with open('config.secret.json', 'r') as f:
        return json.load(f)


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ {INPUT_FILE} not found. Run scripts/03_import_data.py first.")
        sys.exit(1)

    # Load sentences
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        records = json.load(f)

    print("=" * 60)
    print(f"Generating Embeddings for {len(records):,} Sentences")
    print("=" * 60)
    print(f"   Model: {EMBEDDING_MODEL} ({EMBEDDING_DIMENSIONS:,} dimensions)")
    print(f"   Batch size: {BATCH_SIZE}\n")

    # Check if there's a partial result we can resume from
    already_embedded = 0
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        already_embedded = len(existing)
        if already_embedded >= len(records):
            print(f"✅ All {len(records):,} sentences already have embeddings in {OUTPUT_FILE}")
            print(f"   Delete {OUTPUT_FILE} to re-generate.")
            return
        print(f"   ⏩ Resuming from sentence {already_embedded:,} (found partial output)")
        records_to_embed = records[already_embedded:]
    else:
        existing = []
        records_to_embed = records

    # Generate embeddings
    secrets = load_secrets()
    api_key = secrets.get('GEMINI_API_KEY')
    if not api_key:
        print("❌ GEMINI_API_KEY is missing from config.secret.json")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    embedded_records = list(existing)  # Start from any partial results
    errors = 0

    for i in tqdm(range(0, len(records_to_embed), BATCH_SIZE), desc="Embedding"):
        batch = records_to_embed[i:i + BATCH_SIZE]
        # Gemini Embedding 2 uses the same retrieval-document format that the
        # query Edge Function pairs with its question-answering query format.
        batch_contents = [
            types.Content(parts=[
                types.Part.from_text(
                    text=f"title: {record.get('title') or 'none'} | text: {record['text']}"
                )
            ])
            for record in batch
        ]

        while True:
            try:
                response = client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=batch_contents,
                    config=types.EmbedContentConfig(
                        output_dimensionality=EMBEDDING_DIMENSIONS
                    )
                )

                if not response.embeddings or len(response.embeddings) != len(batch):
                    raise ValueError("Gemini returned a different number of embeddings than inputs")

                for record, item in zip(batch, response.embeddings):
                    record_with_embedding = dict(record)
                    record_with_embedding['embedding'] = item.values
                    embedded_records.append(record_with_embedding)
                break

            except Exception as e:
                # Preserve prefix-only checkpoints so resume-by-count never skips records.
                if '429' in str(e) or 'RESOURCE_EXHAUSTED' in str(e):
                    print(
                        f"\n   ⏳ Gemini rate limit reached; retrying this batch "
                        f"in {RATE_LIMIT_RETRY_SECONDS} seconds."
                    )
                    time.sleep(RATE_LIMIT_RETRY_SECONDS)
                    continue

                print(f"\n   ❌ Batch error; stopping so this batch can be retried: {e}")
                errors += len(batch)
                raise

        # Save progress every 10 batches (in case of crash)
        if (i // BATCH_SIZE + 1) % 10 == 0:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(embedded_records, f, ensure_ascii=False)

        time.sleep(SECONDS_BETWEEN_BATCHES)

    # Final save
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(embedded_records, f, ensure_ascii=False)

    file_size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"\n✅ Embedding complete!")
    print(f"   Embedded: {len(embedded_records):,} sentences")
    if errors:
        print(f"   Errors:   {errors:,}")

    print("   Check Google AI Studio for current quota and usage details.")

    print(f"\n💾 Saved to {OUTPUT_FILE} ({file_size_mb:.1f} MB)")
    print(f"   This file is your safety net — embeddings are preserved on disk.")
    print(f"\nNext: python scripts/05_update_embeddings.py")


if __name__ == '__main__':
    main()
