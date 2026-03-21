"""
Anomaly Detector — DeFi Protocol Risk Monitor
-----------------------------------------------
Rileva anomalie nei dati raccolti dalla pipeline usando Isolation Forest.

Monitora combinazioni anomale di:
- APY (spike improvvisi = segnale di stress o manipolazione)
- TVL (cali improvvisi = fuga di liquidità)
- Utilization rate (valori estremi = rischio di illiquidità)

Questo è il cuore del sistema di early warning che un operator DeFi
come Dialectic usa per proteggere il capitale da exploit e crisi.

ESECUZIONE:
    python models/anomaly_detector.py
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from datetime import datetime
import os

INPUT_FILE  = "data/multi_protocol.csv"
OUTPUT_FILE = "data/anomalies.csv"

# ─── Configurazione del modello ───────────────────────────────────────────────

# contamination: stima della % di anomalie attese nel dataset.
# 0.05 = ci aspettiamo che circa il 5% delle rilevazioni sia anomalo.
# In produzione questo valore si calibra sui dati storici.
CONTAMINATION = 0.05

# Feature su cui addestriamo il modello.
# Usiamo variazioni percentuali (pct_change) invece dei valori assoluti
# perché quello che conta non è il valore in sé, ma quanto cambia.
FEATURES = ["apy_total_pct_change", "tvl_usd_pct_change", "utilization_rate"]


def load_data() -> pd.DataFrame:
    """Carica il dataset storico e prepara le feature."""
    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(
            f"Dataset non trovato: {INPUT_FILE}\n"
            "Esegui prima: python pipeline/multi_protocol.py"
        )

    df = pd.read_csv(INPUT_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Costruisce le feature per il modello.

    Variazioni percentuali: catturano i cambiamenti bruschi che
    caratterizzano eventi anomali (exploit, bank run, manipolazioni).
    Un APY che passa dal 4% all'80% in un giorno è un segnale chiarissimo.
    """
    df = df.copy()

    # Calcola variazioni % per protocollo e simbolo separatamente
    for col in ["apy_total", "tvl_usd"]:
        df[f"{col}_pct_change"] = (
            df.groupby(["protocol", "symbol"])[col]
            .pct_change()
            .fillna(0)
            .clip(-5, 5)  # limita outlier estremi per stabilità numerica
        )

    return df


def run_anomaly_detection(df: pd.DataFrame) -> pd.DataFrame:
    """
    Addestra Isolation Forest e assegna un anomaly score a ogni riga.

    Isolation Forest funziona isolando le osservazioni:
    - Punti anomali sono facili da isolare (richiedono pochi tagli)
    - Punti normali sono difficili da isolare (richiedono molti tagli)
    Il risultato è un score: più negativo = più anomalo.
    """
    # Rimuovi righe con NaN nelle feature
    df_model = df.dropna(subset=FEATURES).copy()

    if len(df_model) < 10:
        print("  ⚠️  Dati insufficienti per il modello.")
        print("     Servono almeno 10 rilevazioni. Continua a raccogliere dati.")
        return pd.DataFrame()

    # Normalizza le feature (importante per Isolation Forest)
    scaler = StandardScaler()
    X = scaler.fit_transform(df_model[FEATURES])

    # Addestra il modello
    model = IsolationForest(
        contamination=CONTAMINATION,
        random_state=42,
        n_estimators=100
    )
    model.fit(X)

    # Predizioni: -1 = anomalia, 1 = normale
    df_model["anomaly_label"]  = model.predict(X)
    df_model["anomaly_score"]  = model.score_samples(X)  # più negativo = più anomalo
    df_model["is_anomaly"]     = df_model["anomaly_label"] == -1

    return df_model


def save_anomalies(df: pd.DataFrame):
    """Salva le sole righe anomale in un file separato."""
    anomalies = df[df["is_anomaly"]].copy()
    os.makedirs("data", exist_ok=True)
    anomalies.to_csv(OUTPUT_FILE, index=False)
    return anomalies


def print_report(df: pd.DataFrame, anomalies: pd.DataFrame):
    """Stampa il report del modello."""
    print("\n" + "="*65)
    print("  Anomaly Detection Report")
    print("="*65)
    print(f"\n  Rilevazioni totali analizzate:  {len(df)}")
    print(f"  Anomalie rilevate:              {len(anomalies)}")
    print(f"  Tasso di anomalia:              {len(anomalies)/len(df)*100:.1f}%")

    if len(anomalies) == 0:
        print("\n  ✅ Nessuna anomalia rilevata. Tutti i protocolli sembrano normali.")
    else:
        print("\n  ⚠️  ANOMALIE RILEVATE:")
        print("-"*65)

        # Ordina per anomaly score (più negativo = più preoccupante)
        top = anomalies.nsmallest(5, "anomaly_score")

        for _, row in top.iterrows():
            print(f"\n  [{row['timestamp']}]")
            print(f"  Protocollo:        {row['protocol']} — {row['symbol']}")
            print(f"  Anomaly score:     {row['anomaly_score']:.4f}")
            print(f"  APY:               {row['apy_total']:.2f}% "
                  f"(Δ {row['apy_total_pct_change']*100:+.1f}%)")
            print(f"  TVL:               ${row['tvl_usd']:,.0f} "
                  f"(Δ {row['tvl_usd_pct_change']*100:+.1f}%)")
            print(f"  Utilization rate:  {row['utilization_rate']*100:.1f}%")

    print("\n" + "="*65)
    print(f"  Anomalie salvate in: {OUTPUT_FILE}\n")


def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Avvio anomaly detection...")

    try:
        # 1. Carica dati
        df = load_data()
        print(f"  → {len(df)} rilevazioni caricate da {INPUT_FILE}")

        # 2. Feature engineering
        df = engineer_features(df)

        # 3. Anomaly detection
        df_results = run_anomaly_detection(df)

        if df_results.empty:
            return

        # 4. Salva anomalie
        anomalies = save_anomalies(df_results)

        # 5. Report
        print_report(df_results, anomalies)

    except FileNotFoundError as e:
        print(f"  ❌ {e}")
    except Exception as e:
        print(f"  ❌ Errore inatteso: {e}")
        raise


if __name__ == "__main__":
    main()
