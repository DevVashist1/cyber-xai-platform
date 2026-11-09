import os
import glob
import pandas as pd

R42_DIR = "data/raw/Cert/r4.2"
ANS_FILE = "data/raw/Cert/answers/insiders.csv"
FILES_TO_CHECK = ["logon.csv", "device.csv", "file.csv", "email.csv", "http.csv"]

def inspect_cert():
    print("=== STEP 4.1: CERT r4.2 RAW DATA INSPECTION ===\n")
    
    for fname in FILES_TO_CHECK:
        fpath = os.path.join(R42_DIR, fname)
        size_mb = os.path.getsize(fpath) / (1024 * 1024)
        
        df = pd.read_csv(fpath, nrows=1000)
        print(f"FILE: {fname} ({size_mb:.2f} MB)")
        print(f"  Columns      : {list(df.columns)}")
        print(f"  Sample Date  : '{df['date'].iloc[0]}' -> '{df['date'].iloc[-1]}'")
        if "activity" in df.columns:
            print(f"  Activity vals: {df['activity'].unique().tolist()}")
        print(f"  Row 0 sample : {df.iloc[0].to_dict()}\n")

    ldap_files = sorted(glob.glob(os.path.join(R42_DIR, "LDAP", "*.csv")))
    if ldap_files:
        df_ldap = pd.read_csv(ldap_files[0], nrows=5)
        print(f"LDAP SAMPLE ({os.path.basename(ldap_files[0])}, total {len(ldap_files)} monthly files):")
        print(f"  Columns      : {list(df_ldap.columns)}")
        print(f"  Row 0 sample : {df_ldap.iloc[0].to_dict()}\n")

    df_ans = pd.read_csv(ANS_FILE)
    df_ans_42 = df_ans[df_ans["dataset"].astype(str) == "4.2"]
    print(f"GROUND TRUTH (insiders.csv filtered to dataset == 4.2):")
    print(f"  Columns            : {list(df_ans.columns)}")
    print(f"  Malicious r4.2 rows: {len(df_ans_42)}")
    print(f"  First 5 r4.2 insiders:\n{df_ans_42[['dataset', 'scenario', 'user', 'start', 'end']].head(5)}\n")

if __name__ == "__main__":
    inspect_cert()