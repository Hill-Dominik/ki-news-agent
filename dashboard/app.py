import streamlit as st
from supabase import create_client
import pandas as pd

st.set_page_config(page_title="KI-News-Agent Dashboard", page_icon="🤖", layout="wide")


@st.cache_resource
def get_client():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


@st.cache_data(ttl=300)  # 5 Minuten Cache, damit nicht bei jedem Klick neu geladen wird
def lade_daten() -> pd.DataFrame:
    client = get_client()
    result = (
        client.table("news_eintraege")
        .select("titel, kernaussage, artikel_url, datum, relevanz, quellen(name), kategorien(name)")
        .order("datum", desc=True)
        .execute()
    )
    df = pd.DataFrame(result.data)
    if df.empty:
        return df
    df["quelle"] = df["quellen"].apply(lambda x: x["name"] if x else "Unbekannt")
    df["kategorie"] = df["kategorien"].apply(lambda x: x["name"] if x else "Unbekannt")
    df["datum"] = pd.to_datetime(df["datum"])
    return df


st.title("🤖 KI-News-Agent Dashboard")
st.caption("Automatisch gesammelte und bewertete KI-News – täglich aktualisiert")


@st.cache_data(ttl=300)
def lade_wochenrueckblick():
    client = get_client()
    result = (
        client.table("wochenrueckblicke")
        .select("datum_von, datum_bis, text")
        .order("erstellt_am", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


rueckblick = lade_wochenrueckblick()
if rueckblick:
    von = pd.to_datetime(rueckblick["datum_von"]).strftime("%d.%m.%Y")
    bis = pd.to_datetime(rueckblick["datum_bis"]).strftime("%d.%m.%Y")
    with st.container(border=True):
        st.subheader(f"📋 Wochenrückblick ({von} – {bis})")
        st.markdown(rueckblick["text"])
    st.divider()

df = lade_daten()

if df.empty:
    st.info("Noch keine Einträge in der Datenbank.")
    st.stop()

# --- KPIs ---
letzte_7_tage = df[df["datum"] >= pd.Timestamp.now() - pd.Timedelta(days=7)]

col1, col2, col3 = st.columns(3)
col1.metric("Einträge (7 Tage)", len(letzte_7_tage))
col2.metric("Hoch relevant (7 Tage)", int((letzte_7_tage["relevanz"] == "Hoch").sum()))
top_thema = letzte_7_tage["kategorie"].value_counts().idxmax() if not letzte_7_tage.empty else "-"
col3.metric("Top-Thema (7 Tage)", top_thema)

st.divider()

# --- Filter ---
col_a, col_b = st.columns(2)
kategorien_auswahl = col_a.multiselect("Kategorie", sorted(df["kategorie"].unique()))
relevanz_auswahl = col_b.multiselect("Relevanz", ["Hoch", "Mittel", "Niedrig"])

gefiltert = df.copy()
if kategorien_auswahl:
    gefiltert = gefiltert[gefiltert["kategorie"].isin(kategorien_auswahl)]
if relevanz_auswahl:
    gefiltert = gefiltert[gefiltert["relevanz"].isin(relevanz_auswahl)]

# --- Chart ---
st.subheader("Einträge nach Kategorie")
st.bar_chart(gefiltert["kategorie"].value_counts())

# --- Liste (Pflicht: Link zur Originalquelle bei jedem Eintrag) ---
st.subheader(f"Einträge ({len(gefiltert)})")

anzeige = gefiltert[["datum", "titel", "kernaussage", "relevanz", "kategorie", "quelle", "artikel_url"]].copy()
anzeige["datum"] = anzeige["datum"].dt.strftime("%d.%m.%Y")
anzeige = anzeige.rename(columns={"artikel_url": "Quelle-Link"})

st.dataframe(
    anzeige,
    column_config={
        "Quelle-Link": st.column_config.LinkColumn("Quelle", display_text="Öffnen"),
    },
    hide_index=True,
    use_container_width=True,
)
