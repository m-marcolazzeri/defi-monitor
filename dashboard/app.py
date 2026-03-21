"""
DeFi Strategy Monitor — Dashboard
------------------------------------
Dashboard interattiva che visualizza i dati raccolti dalla pipeline
e i risultati del modello di anomaly detection.

ESECUZIONE LOCALE:
    streamlit run dashboard/app.py

DEPLOY:
    1. Vai su share.streamlit.io
    2. Connetti il tuo repo GitHub
    3. Seleziona questo file come entry point
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from datetime import datetime

# ─── Config ───────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="DeFi Strategy Monitor",
    page_icon="📊",
    layout="wide"
)

MULTI_PROTOCOL_FILE = "data/multi_protocol.csv"
ANOMALIES_FILE      = "data/anomalies.csv"

# Benchmark rate: T-Bill USA ~5% APY (aggiorna periodicamente)
RISK_FREE_RATE = 5.0


# ─── Data Loading ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)  # cache per 1 ora
def load_multi_protocol():
    if not os.path.exists(MULTI_PROTOCOL_FILE):
        return pd.DataFrame()
    df = pd.read_csv(MULTI_PROTOCOL_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


@st.cache_data(ttl=3600)
def load_anomalies():
    if not os.path.exists(ANOMALIES_FILE):
        return pd.DataFrame()
    df = pd.read_csv(ANOMALIES_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


# ─── Layout ───────────────────────────────────────────────────────────────────

st.title("📊 DeFi Strategy Monitor")
st.markdown(
    "Monitoring system for market-neutral stablecoin yield strategies — "
    "replicating [Dialectic's Chronograph fund](https://dialectic.ky) approach."
)

st.divider()

df = load_multi_protocol()
df_anomalies = load_anomalies()

if df.empty:
    st.warning(
        "Nessun dato trovato. Esegui prima la pipeline:\n\n"
        "```bash\npython pipeline/multi_protocol.py\n```"
    )
    st.stop()


# ─── Sidebar: Filtri ──────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Filtri")

    protocols = sorted(df["protocol"].unique())
    selected_protocols = st.multiselect(
        "Protocolli", protocols, default=protocols
    )

    symbols = sorted(df["symbol"].unique())
    selected_symbol = st.selectbox("Token", symbols, index=0)

    st.divider()
    st.metric("Benchmark (T-Bill USA)", f"{RISK_FREE_RATE:.1f}%")
    st.caption("Ogni strategia deve battere questo tasso per essere efficace.")


# ─── Filtra dati ──────────────────────────────────────────────────────────────

df_filtered = df[
    (df["protocol"].isin(selected_protocols)) &
    (df["symbol"] == selected_symbol)
]


# ─── Sezione 1: Snapshot attuale ──────────────────────────────────────────────

st.subheader("📍 Snapshot Attuale")
st.caption(f"Ultimo aggiornamento: {df_filtered['timestamp'].max()}")

latest = (
    df_filtered
    .sort_values("timestamp")
    .groupby("protocol")
    .last()
    .reset_index()
    .sort_values("apy_total", ascending=False)
)

cols = st.columns(len(latest))
for i, (_, row) in enumerate(latest.iterrows()):
    with cols[i]:
        delta_vs_benchmark = row["apy_total"] - RISK_FREE_RATE
        st.metric(
            label=row["protocol"],
            value=f"{row['apy_total']:.2f}%",
            delta=f"{delta_vs_benchmark:+.2f}% vs T-Bill"
        )
        st.caption(
            f"Util: {row['utilization_rate']*100:.1f}% | "
            f"TVL: ${row['tvl_usd']/1e6:.1f}M"
        )


# ─── Sezione 2: APY nel tempo ─────────────────────────────────────────────────

st.divider()
st.subheader("📈 APY nel Tempo")

fig_apy = px.line(
    df_filtered,
    x="timestamp",
    y="apy_total",
    color="protocol",
    title=f"APY — {selected_symbol} su Arbitrum",
    labels={"apy_total": "APY (%)", "timestamp": "Data"},
)

# Aggiungi linea benchmark
fig_apy.add_hline(
    y=RISK_FREE_RATE,
    line_dash="dash",
    line_color="gray",
    annotation_text=f"T-Bill {RISK_FREE_RATE}%",
    annotation_position="bottom right"
)

st.plotly_chart(fig_apy, use_container_width=True)


# ─── Sezione 3: Utilization Rate ──────────────────────────────────────────────

st.subheader("💧 Utilization Rate nel Tempo")
st.caption(
    "L'utilization rate misura quanta liquidità è stata presa in prestito. "
    "Valori >90% segnalano rischio di illiquidità — potresti non riuscire a ritirare i fondi."
)

fig_util = px.line(
    df_filtered,
    x="timestamp",
    y="utilization_rate",
    color="protocol",
    title=f"Utilization Rate — {selected_symbol}",
    labels={"utilization_rate": "Utilization Rate", "timestamp": "Data"},
)

fig_util.add_hline(
    y=0.90,
    line_dash="dash",
    line_color="red",
    annotation_text="Soglia rischio (90%)",
    annotation_position="bottom right"
)

fig_util.update_yaxes(tickformat=".0%")
st.plotly_chart(fig_util, use_container_width=True)


# ─── Sezione 4: TVL ───────────────────────────────────────────────────────────

st.subheader("🏦 TVL nel Tempo")
st.caption(
    "Un calo improvviso del TVL indica fuga di liquidità — "
    "spesso il primo segnale visibile di un exploit o di una crisi di fiducia."
)

fig_tvl = px.area(
    df_filtered,
    x="timestamp",
    y="tvl_usd",
    color="protocol",
    title=f"Total Value Locked — {selected_symbol}",
    labels={"tvl_usd": "TVL (USD)", "timestamp": "Data"},
)

st.plotly_chart(fig_tvl, use_container_width=True)


# ─── Sezione 5: Confronto protocolli ─────────────────────────────────────────

st.divider()
st.subheader("⚖️ Confronto Protocolli — Risk vs Yield")
st.caption(
    "Il protocollo ideale è in alto a sinistra: alto APY, bassa utilization rate. "
    "Questa è la matrice decisionale per l'allocazione del capitale."
)

if not latest.empty:
    fig_scatter = px.scatter(
        latest,
        x="utilization_rate",
        y="apy_total",
        size="tvl_usd",
        color="protocol",
        text="protocol",
        title="APY vs Utilization Rate (dimensione = TVL)",
        labels={
            "utilization_rate": "Utilization Rate (rischio liquidità)",
            "apy_total": "APY (%)"
        }
    )
    fig_scatter.update_xaxes(tickformat=".0%")
    fig_scatter.add_hline(y=RISK_FREE_RATE, line_dash="dash", line_color="gray")
    st.plotly_chart(fig_scatter, use_container_width=True)


# ─── Sezione 6: Anomalie ──────────────────────────────────────────────────────

st.divider()
st.subheader("🚨 Anomaly Detection")

if df_anomalies.empty:
    st.info(
        "Nessuna anomalia rilevata — oppure il modello non è ancora stato eseguito.\n\n"
        "```bash\npython models/anomaly_detector.py\n```"
    )
else:
    n_anomalies = len(df_anomalies[df_anomalies["symbol"] == selected_symbol])
    st.warning(f"⚠️ {n_anomalies} anomalie rilevate per {selected_symbol}")

    df_anom_filtered = df_anomalies[
        (df_anomalies["symbol"] == selected_symbol) &
        (df_anomalies["protocol"].isin(selected_protocols))
    ].sort_values("anomaly_score")

    st.dataframe(
        df_anom_filtered[[
            "timestamp", "protocol", "symbol",
            "apy_total", "tvl_usd", "utilization_rate", "anomaly_score"
        ]].head(10),
        use_container_width=True
    )


# ─── Footer ───────────────────────────────────────────────────────────────────

st.divider()
st.caption(
    "Data source: [DefiLlama](https://defillama.com) · "
    "Updated daily via GitHub Actions · "
    "Built to study institutional DeFi strategy management"
)
