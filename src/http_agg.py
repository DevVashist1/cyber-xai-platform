import os
import pandas as pd

RAW_HTTP = "data/raw/Cert/r4.2/http.csv"
OUT_PARQUET = "data/intermediate/cert/agg_http.parquet"
os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)

CHUNK_SIZE = 1_000_000
# Friend's regex to extract domain, lowercase it, and strip leading www.
PATTERN = r"^(?:[a-zA-Z]+://)?(?:www\.)?([^/:?#]+)"

def run_http_agg():
    print("=== STEP 4.3e: AGGREGATING http.csv (FRIEND'S DOMAIN REGEX LOGIC) ===")
    
    unique_pairs_chunks = []
    total_raw_http = 0
    total_visits_sum = 0

    for idx, chunk in enumerate(pd.read_csv(RAW_HTTP, usecols=["date", "user", "url"], chunksize=CHUNK_SIZE), 1):
        total_raw_http += len(chunk)
        
        dt = pd.to_datetime(chunk["date"], format="%m/%d/%Y %H:%M:%S", errors="raise")
        chunk["date"] = dt.dt.date
        
        # Friend's regex domain extraction
        chunk["domain"] = chunk["url"].str.extract(PATTERN, expand=False).str.lower()
        chunk.dropna(subset=["domain", "user"], inplace=True)
        
        total_visits_sum += len(chunk)
        
        # Count total visits per user-day, and distinct websites (domains)
        # To handle both efficiently across chunks, let's capture both metrics
        agg = chunk.groupby(["user", "date"], as_index=False).agg(
            websites_visited=("domain", "nunique"),
            http_visits=("domain", "count")
        )
        unique_pairs_chunks.append(agg)
        print(f"   Chunk {idx:2d}: {total_raw_http:,} rows processed...")

    print("\nCombining chunk aggregations...")
    df_agg = pd.concat(unique_pairs_chunks, ignore_index=True).groupby(["user", "date"], as_index=False).sum()
    del unique_pairs_chunks

    df_agg.rename(columns={"user": "user_id"}, inplace=True)
    df_agg["websites_visited"] = df_agg["websites_visited"].astype("int32")
    df_agg["http_visits"] = df_agg["http_visits"].astype("int32")
    df_agg.sort_values(["user_id", "date"], inplace=True)

    df_agg.to_parquet(OUT_PARQUET, engine="pyarrow", index=False)

    print("\n--- SANITY CHECK: agg_http.parquet ---")
    print(f"Total Raw HTTP Rows Read : {total_raw_http:,}")
    print(f"Total (user, date)       : {len(df_agg):,}")
    print(f"Unique HTTP Users        : {df_agg['user_id'].nunique():,}")
    print(f"Total HTTP Visits Sum    : {df_agg['http_visits'].sum():,}")
    print(df_agg.head(5))

if __name__ == "__main__":
    run_http_agg()