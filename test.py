import json
from supabase import create_client

with open("config.public.json", encoding="utf-8") as f:
    config = json.load(f)

supabase = create_client(
    config["SUPABASE_URL"],
    config["SUPABASE_ANON_KEY"],
)

# Public SELECT policy: the query should succeed.
page_views = (
    supabase.table("page_views")
    .select("id", count="exact")
    .limit(5)
    .execute()
)
print(f"page_views: query succeeded; {page_views.count} rows are visible")

# Auth-only SELECT policy: an unauthenticated client should see no rows.
embeddings = (
    supabase.table("sentence_embeddings")
    .select("id", count="exact")
    .limit(5)
    .execute()
)
print(f"sentence_embeddings: {embeddings.count} rows are visible")