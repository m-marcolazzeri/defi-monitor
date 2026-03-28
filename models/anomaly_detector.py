"""
anomaly_detector.py
-------------------
Detects anomalies in collected DeFi protocol data using Isolation Forest.

Features: day-over-day pct changes in APY and TVL, plus current utilization rate.
Anomalies typically correspond to sudden TVL outflows, APY spikes or extreme
utilization — early signals of exploits, liquidity crises or market stress.

Usage:
    python models/anomaly_detector.py
"""

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from datetime import datetime
import os

INPUT_FILE    = "data/multi_protocol.csv"
OUTPUT_FILE   = "data/anomalies.csv"
CONTAMINATION = 0.05  # expected anomaly rate — tune once more data is available
FEATURES      = ["apy_total_pct_change", "tvl_usd_pct_change", "utilization_rate"]
MIN_SAMPLES   = 10

# Exclude snapshots collected before the pipeline was stable (hardcoded protocol
# list, no pool_id, only 7 protocols). These cause spurious delta+500% changes
# that would poison the model. Only data with pool_id and 19 protocols is reliable.
DATA_QUALITY_CUTOFF = "2026-03-22 10:46:00"


def load_data() -> pd.DataFrame:
    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(
            f"{INPUT_FILE} not found. Run pipeline/multi_protocol.py first."
        )
    df = pd.read_csv(INPUT_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df[df["timestamp"] >= DATA_QUALITY_CUTOFF].copy()
    print(f"  Data after quality cutoff ({DATA_QUALITY_CUTOFF}): {len(df)} rows")
    return df.sort_values("timestamp")


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    group_key = "pool_id" if "pool_id" in df.columns else "protocol"
    for col in ["apy_total", "tvl_usd"]:
        df[f"{col}_pct_change"] = (
            df.groupby(group_key)[col]
            .pct_change()
            .fillna(0)
            .clip(-5, 5)
        )
    return df


def detect(df: pd.DataFrame) -> pd.DataFrame:
    df_model = df.dropna(subset=FEATURES).copy()

    if len(df_model) < MIN_SAMPLES:
        print(f"  Not enough data ({len(df_model)} rows, need {MIN_SAMPLES}). Collect more first.")
        return pd.DataFrame()

    X = StandardScaler().fit_transform(df_model[FEATURES])

    model = IsolationForest(contamination=CONTAMINATION, random_state=42, n_estimators=100)
    model.fit(X)

    df_model["anomaly_score"] = model.score_samples(X)
    df_model["is_anomaly"]    = model.predict(X) == -1

    return df_model


def save_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    anomalies = df[df["is_anomaly"]].copy()
    os.makedirs("data", exist_ok=True)
    anomalies.to_csv(OUTPUT_FILE, index=False)
    return anomalies


def print_report(df: pd.DataFrame, anomalies: pd.DataFrame):
    print(f"\n{'='*55}")
    print("  Anomaly Detection Report")
    print(f"{'='*55}")
    print(f"  Samples analyzed : {len(df)}")
    print(f"  Anomalies found  : {len(anomalies)} ({len(anomalies)/len(df)*100:.1f}%)")

    if anomalies.empty:
        print("\n  No anomalies detected.")
    else:
        print("\n  Top anomalies (lowest score = most anomalous):\n")
        for _, row in anomalies.nsmallest(5, "anomaly_score").iterrows():
            util = row.get("utilization_rate")
            util_str = f"{util*100:.1f}%" if util is not None and util == util else "N/A"
            print(
                f"  [{row['timestamp']}] {row['protocol']} — {row['symbol']}"
                f"\n    score={row['anomaly_score']:.4f}"
                f"  APY={row['apy_total']:.2f}% (Δ{row['apy_total_pct_change']*100:+.1f}%)"
                f"  TVL=${row['tvl_usd']:,.0f} (Δ{row['tvl_usd_pct_change']*100:+.1f}%)"
                f"  util={util_str}\n"
            )

    print(f"  Saved to: {OUTPUT_FILE}\n")


def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Running anomaly detection...")
    try:
        df        = engineer_features(load_data())
        results   = detect(df)
        if results.empty:
            return
        anomalies = save_anomalies(results)
        print_report(results, anomalies)
    except FileNotFoundError as e:
        print(f"  [error] {e}")
    except Exception as e:
        print(f"  [error] {e}")
        raise


if __name__ == "__main__":
    main()
