import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

user = os.getenv("POSTGRES_USER")
password = os.getenv("POSTGRES_PASSWORD")
host = os.getenv("POSTGRES_HOST")
port = os.getenv("POSTGRES_PORT")
db = os.getenv("POSTGRES_DB")

db_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
engine = create_engine(db_url)

def run_checkpoint():
    print("1. Connecting to PostgreSQL 15 in Docker...")
    df_test = pd.DataFrame({
        "module": [1, 2],
        "status": ["setup_verified", "pending"]
    })
    
    df_test.to_sql("setup_test_table", engine, if_exists="replace", index=False)
    print("2. Successfully wrote test table to Postgres!")

    df_read = pd.read_sql("SELECT * FROM setup_test_table", engine)
    print("3. Read back from Postgres:")
    print(df_read)

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE setup_test_table;"))
    print("4. Cleaned up test table. CHECKPOINT PASSED!")

if __name__ == "__main__":
    run_checkpoint()