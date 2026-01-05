"""
HospitalFlow - Krankenhaus-Betriebsdashboard
Moderne Streamlit-Anwendung für Krankenhauspersonal mit Live-Metriken, Vorhersagen und Empfehlungen

Diese Datei ist der Haupteinstiegspunkt der Anwendung und enthält:
- Seitenrouting und Navigation
- Initialisierung von Datenbank und Simulation
- Periodische Updates für Simulation, Vorhersagen, Warnungen und Empfehlungen
- Auto-Refresh-Mechanismus
- UI-Grundstruktur (Sidebar, Header, Footer)
"""
import os
import sys
import streamlit as st
from datetime import datetime, timedelta, timezone
import time
import random  # Für zufällige Ereignisse in der Simulation
from zoneinfo import ZoneInfo

# Fix sys.path: remove invalid entries and ensure app directory is first
# This is necessary for proper module resolution in Streamlit/Docker environments
app_dir = os.path.dirname(os.path.abspath(__file__))
sys.path = [p for p in sys.path if p and p != "app.py" and (os.path.isdir(p) if os.path.exists(p) else True)]
if app_dir in sys.path:
    sys.path.remove(app_dir)
sys.path.insert(0, app_dir)

# Import database with fallback to importlib if standard import fails
try:
    from database import HospitalDB
except (ImportError, ModuleNotFoundError):
    import importlib.util
    database_path = os.path.join(app_dir, "database.py")
    spec = importlib.util.spec_from_file_location("database", database_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec from {database_path}")
    database_module = importlib.util.module_from_spec(spec)
    sys.modules["database"] = database_module
    spec.loader.exec_module(database_module)
    HospitalDB = database_module.HospitalDB

# Helper function to import modules with fallback to importlib
def safe_import(module_name, class_or_func_name=None):
    """Import a module with fallback to importlib if standard import fails"""
    try:
        if class_or_func_name:
            module = __import__(module_name, fromlist=[class_or_func_name])
            return getattr(module, class_or_func_name)
        else:
            return __import__(module_name)
    except (ImportError, ModuleNotFoundError):
        import importlib.util
        app_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Handle package imports (e.g., "ui.styling")
        if "." in module_name:
            parts = module_name.split(".")
            module_path = os.path.join(app_dir, *parts[:-1], f"{parts[-1]}.py")
            actual_module_name = parts[-1]
        else:
            module_path = os.path.join(app_dir, f"{module_name}.py")
            actual_module_name = module_name
        
        if not os.path.exists(module_path):
            raise ImportError(f"Module {module_name} not found at {module_path}")
        
        spec = importlib.util.spec_from_file_location(actual_module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load spec from {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        if class_or_func_name:
            return getattr(module, class_or_func_name)
        return module

# Import modules with fallback
HospitalSimulation = safe_import("simulation", "HospitalSimulation")
PredictionEngine = safe_import("predictions", "PredictionEngine")
RecommendationEngine = safe_import("recommendations", "RecommendationEngine")
generate_seed_data = safe_import("seed_data", "generate_seed_data")
generate_devices_only = safe_import("seed_data", "generate_devices_only")

# Import utils with fallback
try:
    from utils import (
        format_time_ago, get_severity_color, get_priority_color, get_risk_color,
        get_status_color, calculate_inventory_status, calculate_capacity_status,
        format_duration_minutes, get_department_color, get_system_status,
        get_metric_severity_for_load, get_metric_severity_for_count, get_metric_severity_for_free,
        get_explanation_score_color
    )
except (ImportError, ModuleNotFoundError):
    utils_module = safe_import("utils")
    format_time_ago = getattr(utils_module, "format_time_ago")
    get_severity_color = getattr(utils_module, "get_severity_color")
    get_priority_color = getattr(utils_module, "get_priority_color")
    get_risk_color = getattr(utils_module, "get_risk_color")
    get_status_color = getattr(utils_module, "get_status_color")
    calculate_inventory_status = getattr(utils_module, "calculate_inventory_status")
    calculate_capacity_status = getattr(utils_module, "calculate_capacity_status")
    format_duration_minutes = getattr(utils_module, "format_duration_minutes")
    get_department_color = getattr(utils_module, "get_department_color")
    get_system_status = getattr(utils_module, "get_system_status")
    get_metric_severity_for_load = getattr(utils_module, "get_metric_severity_for_load")
    get_metric_severity_for_count = getattr(utils_module, "get_metric_severity_for_count")
    get_metric_severity_for_free = getattr(utils_module, "get_metric_severity_for_free")
    get_explanation_score_color = getattr(utils_module, "get_explanation_score_color")

# Import ui.styling with fallback
try:
    from ui.styling import apply_custom_styles
except (ImportError, ModuleNotFoundError, AttributeError):
    import importlib.util
    styling_path = os.path.join(app_dir, "ui", "styling.py")
    if os.path.exists(styling_path):
        spec = importlib.util.spec_from_file_location("ui.styling", styling_path)
        if spec and spec.loader:
            styling_module = importlib.util.module_from_spec(spec)
            sys.modules["ui.styling"] = styling_module
            spec.loader.exec_module(styling_module)
            apply_custom_styles = getattr(styling_module, "apply_custom_styles")
        else:
            raise ImportError(f"Could not load spec from {styling_path}")
    else:
        raise ImportError(f"ui/styling.py not found at {styling_path}")

# ===== TIMEZONE CONFIGURATION =====
# Zeitzonenkonfiguration: Setze hier deine lokale Zeitzone
# Beispiele: 'Europe/Berlin', 'Europe/Vienna', 'America/New_York', 'Asia/Tokyo'
# Für Mitteleuropäische Zeit (CET/CEST) verwende 'Europe/Berlin' oder 'Europe/Zurich'
LOCAL_TIMEZONE = 'Europe/Berlin'  # Ändere dies auf deine Zeitzone

def get_local_time():
    """
    Gibt die aktuelle Zeit in der konfigurierten lokalen Zeitzone zurück.
    
    Returns:
        datetime: Aktueller Zeitstempel in lokaler Zeitzone (UTC wird konvertiert)
    """
    return datetime.now(timezone.utc).astimezone(ZoneInfo(LOCAL_TIMEZONE))
# ===================================

# ===== STREAMLIT SEITENKONFIGURATION =====
# Konfiguriert die grundlegenden Streamlit-Seiteneinstellungen
st.set_page_config(
    page_title="HospitalFlow",
    page_icon="🏥",
    layout="wide",  # Weites Layout für mehr Platz
    initial_sidebar_state="expanded"  # Sidebar standardmäßig geöffnet
)

# ===== SESSION STATE INITIALISIERUNG =====
# Leistungsoptimierung: Verhindert unnötige Neustarts bei Widget-Interaktionen
# Dies reduziert Flackern und verbessert die User Experience
if 'rerun_disabled' not in st.session_state:
    st.session_state.rerun_disabled = False

# ===== STYLING ANWENDEN =====
# Wende das benutzerdefinierte CSS-Styling an (siehe ui/styling.py)
apply_custom_styles()

# ===== DATENBANK INITIALISIERUNG =====
# Initialisiere echte Datenbank
if 'db' not in st.session_state:
    st.session_state.db = HospitalDB()
    db = st.session_state.db
    
    # Prüfe ob Datenbank leer ist und generiere Initialdaten
    # Verwende connection_context() für effiziente Verbindungswiederverwendung
    with db.connection_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM metrics")
        metric_count = cursor.fetchone()[0]
        if metric_count == 0:
            # Datenbank ist leer - generiere Initialdaten
            with st.spinner("Initialisiere Datenbank mit Beispieldaten..."):
                generate_seed_data(db)
        else:
            # Prüfe ob Geräte fehlen und generiere sie nachträglich
            cursor.execute("SELECT COUNT(*) FROM devices")
            device_count = cursor.fetchone()[0]
            if device_count == 0:
                # Geräte fehlen - generiere sie nachträglich
                with st.spinner("Generiere fehlende Geräte..."):
                    generate_devices_only(db)
else:
    db = st.session_state.db

# Navigation mit Icons
PAGES = {
    "📊 Dashboard": "dashboard",
    "📈 Live-Metriken": "metrics",
    "🔮 Vorhersagen": "predictions",
    "⚙️ Betrieb": "operations",
    "📋 Kapazitätsübersicht": "capacity",
    "📅 Dienstplan": "dienstplan",

    "🚑 Transport": "transport",
    "📦 Inventar": "inventory",
    "🔧 Gerätewartung": "devices",
    "🏥 Entlassungsplanung": "discharge"
}

# Systemstatus abrufen
system_status, status_color = get_system_status()


# ===== SIDEBAR UI =====
# Zeigt den HospitalFlow-Titel in der Sidebar (oben links)
st.sidebar.markdown("""
<div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem;">
    <span style="font-size: 2rem;">🏥</span>
    <span style="font-size: 1.5rem; font-weight: 700; color: #4f46e5; letter-spacing: -0.025em;">HospitalFlow</span>
</div>
""", unsafe_allow_html=True)

# Navigation-Header in der Sidebar mit professionellem Styling
st.sidebar.markdown("""
<div style="padding: 0.5rem 0 1.5rem 0; border-bottom: 1px solid #e5e7eb; margin-bottom: 1rem;">
    <h3 style="color: #667eea; margin: 0; font-size: 1.125rem; font-weight: 600; letter-spacing: -0.01em;">Navigation</h3>
</div>
""", unsafe_allow_html=True)

# ===== SEITENAUSWAHL =====
# Radio-Button für die Seitenauswahl (Label verborgen, da der Text in PAGES enthalten ist)
page_key = st.sidebar.radio(
    "Seite auswählen",
    list(PAGES.keys()),
    label_visibility="collapsed",
    key="nav_radio"
)

# Extrahiere den Seitennamen ohne Icon für das Routing
# Format: "📊 Dashboard" -> "Dashboard"
page = page_key.split(" ", 1)[1] if " " in page_key else page_key

# ===== SCHWEREGRAD-LEGENDE =====
# Kompakte Legende für die verschiedenen Schweregrade (Hoch/Mittel/Niedrig)
# Wird in der Sidebar unter der Seitenauswahl angezeigt
st.sidebar.markdown("---")
st.sidebar.markdown("""
<div class="legend" style="margin-bottom: 1rem;">
    <div style="font-size: 0.7rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; font-weight: 600;">Schweregrad</div>
    <div class="legend-item">
        <span class="badge" style="background: #DC2626; color: white; width: 10px; height: 10px; padding: 0; border-radius: 50%; display: inline-block;"></span>
        <span style="font-size: 0.75rem;">Hoch</span>
    </div>
    <div class="legend-item">
        <span class="badge" style="background: #F59E0B; color: white; width: 10px; height: 10px; padding: 0; border-radius: 50%; display: inline-block;"></span>
        <span style="font-size: 0.75rem;">Mittel</span>
    </div>
    <div class="legend-item">
        <span class="badge" style="background: #10B981; color: white; width: 10px; height: 10px; padding: 0; border-radius: 50%; display: inline-block;"></span>
        <span style="font-size: 0.75rem;">Niedrig</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ===== DEMO-MODUS UND AUTO-REFRESH KONFIGURATION =====
# Lade Einstellungen aus dem Session State (werden später in der Sidebar angezeigt)
demo_mode = st.session_state.get('demo_mode', False)  # Demo-Modus: Erhöht Ereignisfrequenz
auto_refresh = st.session_state.get('auto_refresh', True)  # Auto-Refresh: Automatische Seitenaktualisierung
refresh_interval_key = st.session_state.get('refresh_interval', '30 Sekunden')  # Aktualisierungsintervall
# Mapping von Intervall-Strings zu Sekunden
interval_map = {"10 Sekunden": 10, "30 Sekunden": 30, "60 Sekunden": 60}
refresh_seconds = interval_map.get(refresh_interval_key, 30)

# ===== SEITEN-HEADER =====
# Zeigt einen professionellen Header mit Seitentitel und Zeitstempel
page_timestamp = get_local_time().strftime('%H:%M:%S')
st.markdown(f"""
<div class="page-header">
    <h1 class="page-title">{page}</h1>
    <p class="page-subtitle">Zuletzt aktualisiert: {page_timestamp}</p>
</div>
""", unsafe_allow_html=True)

# ===== SIMULATION INITIALISIERUNG =====
# Initialisiere echte Simulation
# demo_mode wird später aus session_state geladen (siehe unten bei DEMO-MODUS TOGGLE)

if 'simulation' not in st.session_state:
    # Initialisiere mit Demo-Modus aus session_state
    initial_demo_mode = st.session_state.get('demo_mode', False)
    st.session_state.simulation = HospitalSimulation(db, demo_mode=initial_demo_mode)

sim = st.session_state.simulation

# ===== SIMULATION METRIKEN CACHING =====
# Rufe Simulation-Metriken einmalig ab und cache sie in session_state
# Verhindert mehrfache Aufrufe von sim.get_current_metrics()
if 'cached_sim_metrics' not in st.session_state or 'sim_metrics_timestamp' not in st.session_state:
    st.session_state.cached_sim_metrics = sim.get_current_metrics()
    st.session_state.sim_metrics_timestamp = time.time()
else:
    # Aktualisiere Cache alle 10 Sekunden (Simulation ändert sich häufig)
    if time.time() - st.session_state.sim_metrics_timestamp > 10:
        st.session_state.cached_sim_metrics = sim.get_current_metrics()
        st.session_state.sim_metrics_timestamp = time.time()

# ===== MAINTENANCE WINDOWS PROCESSING =====
# Prüfe und verarbeite Wartungsfenster bei jedem App-Lauf
# Schließt abgelaufene Wartungen automatisch ab
if 'last_maintenance_check' not in st.session_state or time.time() - st.session_state.last_maintenance_check > 5:
    try:
        changed_devices = db.check_and_process_maintenance_windows()
        if changed_devices:
            # Cache invalidieren wenn Geräte geändert wurden
            st.cache_data.clear()
        st.session_state.last_maintenance_check = time.time()
    except Exception as e:
        # Fehler beim Maintenance-Processing ignorieren, um UI nicht zu blockieren
        pass

# ===== KI-ENGINES INITIALISIERUNG =====
# Initialisiere Vorhersage- und Empfehlungs-Engines
if 'prediction_engine' not in st.session_state:
    st.session_state.prediction_engine = PredictionEngine(db)

if 'recommendation_engine' not in st.session_state:
    st.session_state.recommendation_engine = RecommendationEngine(db)

# ===== AI-GENERIERUNG (DEFERRED) =====
# Generiere Vorhersagen und Empfehlungen nur bei Bedarf oder im Hintergrund mit längerem Intervall
# Dies verbessert die Performance, da AI-Generierung nicht bei jedem Seitenaufruf läuft

if 'last_ai_update' not in st.session_state:
    st.session_state.last_ai_update = 0

# Prüfe ob AI-Generierung benötigt wird (nur auf relevanten Seiten)
needs_ai = page in ["Vorhersagen", "Empfehlungen", "Dashboard", "Betrieb"]

current_time = time.time()
# Längeres Intervall: 300 Sekunden (5 Minuten) statt 60 Sekunden
# Oder sofort wenn auf relevanter Seite und letztes Update > 60 Sekunden
ai_update_interval = 300  # 5 Minuten für Hintergrund-Updates
if needs_ai:
    ai_update_interval = 60  # 1 Minute wenn auf relevanter Seite

if current_time - st.session_state.last_ai_update > ai_update_interval:
    # Generiere Vorhersagen nur wenn benötigt
    if needs_ai or page == "Vorhersagen":
        try:
            st.session_state.prediction_engine.generate_predictions([5, 10, 15])
        except Exception as e:
            pass  # Fehler ignorieren, um UI nicht zu blockieren
    
    # Generiere Empfehlungen nur wenn benötigt
    if needs_ai or page == "Empfehlungen":
        try:
            # Verwende gecachte Simulation-Metriken falls verfügbar
            if 'cached_sim_metrics' in st.session_state:
                sim_metrics = st.session_state.cached_sim_metrics
            else:
                sim_metrics = sim.get_current_metrics()
                st.session_state.cached_sim_metrics = sim_metrics
            st.session_state.recommendation_engine.generate_recommendations(sim_metrics)
        except Exception as e:
            pass  # Fehler ignorieren
    
    st.session_state.last_ai_update = current_time

# ===== BACKGROUND DATA PRE-FETCHING =====
# Pre-fetch alle wichtigen Daten im Hintergrund für sofortige Verfügbarkeit
# Daten werden in st.session_state gespeichert und periodisch aktualisiert

def fetch_background_data(_db, _sim):
    """
    Lädt alle wichtigen Daten im Hintergrund für alle Tabs.
    Wird periodisch aufgerufen um Daten aktuell zu halten.
    
    Args:
        _db: HospitalDB-Instanz
        _sim: HospitalSimulation-Instanz
    """
    try:
        # Verwende erweiterte Batch-Query für alle Daten (alerts, recommendations, transport, inventory, devices, predictions, metrics_recent, audit_log)
        batch_data = _db.get_dashboard_data_batch()
        
        # Hole Simulationsmetriken (verwende gecachte falls verfügbar, sonst hole neu)
        if 'cached_sim_metrics' in st.session_state:
            sim_metrics = st.session_state.cached_sim_metrics
        else:
            sim_metrics = _sim.get_current_metrics()
            st.session_state.cached_sim_metrics = sim_metrics
        
        # Berechne capacity aus Simulation (keine DB-Query nötig)
        capacity = _db.get_capacity_from_simulation(sim_metrics)
        
        # Speichere in session_state für sofortigen Zugriff
        st.session_state.background_data = {
            'alerts': batch_data.get('alerts', []),
            'recommendations': batch_data.get('recommendations', []),
            'transport': batch_data.get('transport', []),
            'inventory': batch_data.get('inventory', []),
            'devices': batch_data.get('devices', []),
            'predictions': batch_data.get('predictions', []),
            'capacity': capacity,  # Aus Simulation berechnet (keine DB-Query)
            'metrics_recent': batch_data.get('metrics_recent', []),  # Aus Batch-Query
            'audit_log': batch_data.get('audit_log', []),  # Aus Batch-Query
            'timestamp': time.time()
        }
    except Exception as e:
        # Bei Fehler: Verwende leere Datenstruktur
        if 'background_data' not in st.session_state:
            st.session_state.background_data = {
                'alerts': [],
                'recommendations': [],
                'transport': [],
                'inventory': [],
                'devices': [],
                'predictions': [],
                'capacity': [],
                'metrics_recent': [],
                'audit_log': [],
                'timestamp': time.time()
            }

# Initialisiere Background-Daten beim ersten Start
if 'background_data' not in st.session_state:
    fetch_background_data(db, sim)
    st.session_state.background_data_timestamp = time.time()

# Update Background-Daten periodisch (alle 30 Sekunden)
background_update_interval = 30
if 'background_data_timestamp' not in st.session_state:
    st.session_state.background_data_timestamp = 0

if time.time() - st.session_state.background_data_timestamp > background_update_interval:
    # Update im Hintergrund (nicht-blockierend)
    try:
        fetch_background_data(db, sim)
        st.session_state.background_data_timestamp = time.time()
    except Exception as e:
        # Fehler ignorieren, um UI nicht zu blockieren
        pass

# ===== DATENABRUF FUNKTIONEN =====
# Funktionen für häufige Datenabrufe mit Caching für bessere Performance
# Verwenden jetzt Background-Daten aus session_state für sofortigen Zugriff

def get_cached_alerts(_db=None):
    """
    Gibt aktive Warnungen zurück (aus Background-Daten oder direkt aus DB).
    
    Args:
        _db: HospitalDB-Instanz (optional, für Fallback)
    
    Returns:
        List[Dict]: Liste von aktiven Warnungen
    """
    # Verwende Background-Daten falls verfügbar
    if 'background_data' in st.session_state and st.session_state.background_data:
        return st.session_state.background_data.get('alerts', [])
    # Fallback: Direkt aus DB
    if _db:
        return _db.get_active_alerts()
    return []

def get_cached_recommendations(_db=None):
    """
    Gibt ausstehende Empfehlungen zurück (aus Background-Daten oder direkt aus DB).
    
    Args:
        _db: HospitalDB-Instanz (optional, für Fallback)
    
    Returns:
        List[Dict]: Liste von ausstehenden Empfehlungen
    """
    # Verwende Background-Daten falls verfügbar
    if 'background_data' in st.session_state and st.session_state.background_data:
        return st.session_state.background_data.get('recommendations', [])
    # Fallback: Direkt aus DB
    if _db:
        return _db.get_pending_recommendations()
    return []

def get_cached_capacity(_db=None):
    """
    Gibt Kapazitätsübersicht zurück (aus Background-Daten oder direkt aus DB).
    
    Args:
        _db: HospitalDB-Instanz (optional, für Fallback)
    
    Returns:
        List[Dict]: Liste von Kapazitätsdaten pro Abteilung
    """
    # Verwende Background-Daten falls verfügbar
    if 'background_data' in st.session_state and st.session_state.background_data:
        return st.session_state.background_data.get('capacity', [])
    # Fallback: Direkt aus DB
    if _db:
        return _db.get_capacity_overview()
    return []

def get_cached_simulation_metrics(_sim=None):
    """
    Gibt aktuelle Simulationsmetriken zurück (aus session_state Cache).
    Verwendet gecachte Metriken um mehrfache Aufrufe zu vermeiden.
    
    Args:
        _sim: HospitalSimulation-Instanz (wird ignoriert, verwendet session_state)
    
    Returns:
        Dict: Aktuelle Simulationsmetriken
    """
    # Verwende gecachte Metriken aus session_state
    if 'cached_sim_metrics' in st.session_state:
        return st.session_state.cached_sim_metrics
    # Fallback falls Cache nicht existiert
    if _sim:
        return _sim.get_current_metrics()
    return {}

# Wrapper-Funktionen für Kompatibilität mit bestehenden Seiten-Aufrufen
def get_cached_alerts_wrapper():
    """Wrapper für get_cached_alerts() ohne Parameter"""
    return get_cached_alerts(db)

def get_cached_recommendations_wrapper():
    """Wrapper für get_cached_recommendations() ohne Parameter"""
    return get_cached_recommendations(db)

def get_cached_capacity_wrapper():
    """Wrapper für get_cached_capacity() ohne Parameter"""
    return get_cached_capacity(db)

# ===== LAZY LOADING FÜR SEITENMODULE =====
# Lade Seitenmodule nur bei Bedarf für bessere Performance
# Verhindert unnötige Imports beim Start

# Mapping von Seitennamen zu Modulnamen
PAGE_MODULE_MAP = {
    "Dashboard": "dashboard",
    "Betrieb": "operations",
    "Live-Metriken": "metrics",
    "Vorhersagen": "predictions",
    "Transport": "transport",
    "Inventar": "inventory",
    "Gerätewartung": "devices",
    "Entlassungsplanung": "discharge_planning",
    "Kapazitätsübersicht": "capacity",
    "Dienstplan": "dienstplan"
}

def load_page_module(page_name: str):
    """
    Lädt ein Seitenmodul lazy (nur bei Bedarf).
    
    Args:
        page_name: Name der Seite (z.B. "Dashboard")
    
    Returns:
        Modul-Objekt oder None
    """
    if page_name not in PAGE_MODULE_MAP:
        return None
    
    mod_name = PAGE_MODULE_MAP[page_name]
    module_key = f"page_module_{mod_name}"
    
    # Prüfe ob Modul bereits geladen ist
    if module_key in st.session_state:
        return st.session_state[module_key]
    
    # Lade Modul lazy
    try:
        # Versuche Standard-Import
        module = __import__(f"ui.pages.{mod_name}", fromlist=[mod_name])
        page_module = getattr(module, mod_name) if hasattr(module, mod_name) else module
    except (ImportError, ModuleNotFoundError, AttributeError):
        # Fallback: importlib
        import importlib.util
        module_path = os.path.join(app_dir, 'ui', 'pages', f'{mod_name}.py')
        if not os.path.exists(module_path):
            return None
        
        spec = importlib.util.spec_from_file_location(f"ui.pages.{mod_name}", module_path)
        if spec is None or spec.loader is None:
            return None
        
        page_module = importlib.util.module_from_spec(spec)
        sys.modules[f"ui.pages.{mod_name}"] = page_module
        spec.loader.exec_module(page_module)
    
    # Cache Modul in session_state
    st.session_state[module_key] = page_module
    return page_module

# ===== SEITEN-ROUTING =====
# Routet zur entsprechenden Seite basierend auf der Benutzerauswahl
# Jede Seite hat eine render()-Funktion, die die Datenbank- und Simulations-Instanzen erhält
page_module = load_page_module(page)

if page_module:
    if page == "Dashboard":
        page_module.render(db, sim, get_cached_alerts_wrapper, get_cached_recommendations_wrapper, get_cached_capacity_wrapper)
    elif page == "Betrieb":
        page_module.render(db, sim, get_cached_alerts_wrapper, get_cached_recommendations_wrapper, get_cached_capacity_wrapper)
    elif page in ["Live-Metriken", "Vorhersagen", "Transport", "Inventar", "Gerätewartung", "Entlassungsplanung", "Kapazitätsübersicht", "Dienstplan"]:
        page_module.render(db, sim)
else:
    st.error(f"Seitenmodul für '{page}' konnte nicht geladen werden.")

# ===== SIDEBAR-FOOTER UND EINSTELLUNGEN =====
# Zeigt Einstellungen und Footer-Informationen in der Sidebar

st.sidebar.markdown("---")
st.sidebar.markdown("")  # Spacing

# ===== DEMO-MODUS TOGGLE =====
# Ermöglicht es Benutzern, den Demo-Modus zu aktivieren
# Demo-Modus erhöht die Ereignisfrequenz für bessere Demonstration
demo_mode_new = st.sidebar.toggle("🎬 Demo-Modus", value=demo_mode, help="Erhöht die Ereignisfrequenz für Demonstrationszwecke", key="demo_mode_toggle")
st.session_state['demo_mode'] = demo_mode_new
demo_mode = demo_mode_new

# Update Simulation mit neuem Demo-Modus
if 'simulation' in st.session_state:
    old_demo_mode = st.session_state.simulation.demo_mode
    if old_demo_mode != demo_mode_new:
        st.session_state.simulation.set_demo_mode(demo_mode_new)

if demo_mode:
    st.sidebar.info("Demo-Modus: Ereignisse treten häufiger auf")

# ===== AUTO-REFRESH TOGGLE =====
# Ermöglicht es Benutzern, automatische Seitenaktualisierung zu aktivieren/deaktivieren
auto_refresh_new = st.sidebar.toggle("🔄 Auto-Refresh", value=auto_refresh, help="Aktualisiert die Seite automatisch alle 30 Sekunden", key="auto_refresh_toggle")
st.session_state['auto_refresh'] = auto_refresh_new
auto_refresh = auto_refresh_new

# ===== AKTUALISIERUNGSINTERVALL AUSWAHL =====
# Ermöglicht es Benutzern, das Auto-Refresh-Intervall zu wählen
refresh_interval_options = ["10 Sekunden", "30 Sekunden", "60 Sekunden"]
refresh_interval_index = refresh_interval_options.index(refresh_interval_key) if refresh_interval_key in refresh_interval_options else 1
refresh_interval = st.sidebar.selectbox("Aktualisierungsintervall", refresh_interval_options, index=refresh_interval_index, key="refresh_interval_selectbox", disabled=not auto_refresh)
st.session_state['refresh_interval'] = refresh_interval
refresh_seconds = interval_map[refresh_interval]
if auto_refresh:
    st.sidebar.info(f"Auto-Refresh: Alle {refresh_seconds} Sekunden")

st.sidebar.markdown("")  # Spacing

# ===== MANUELLER REFRESH BUTTON =====
# Button für manuelle Seitenaktualisierung
if st.sidebar.button("🔄 Daten aktualisieren", use_container_width=True):
    # Cache leeren für alle gecachten Funktionen
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("")  # Spacing

# ===== VERSION UND DATENSCHUTZ INFO =====
# Zeigt Versionsinformationen und Datenschutzhinweise
st.sidebar.markdown("""
<div style="font-size: 0.75rem; color: #9ca3af; padding: 0.5rem 0; line-height: 1.6;">
    <p style="margin: 0.25rem 0;"><strong>HospitalFlow MVP v1.0</strong></p>
    <p style="margin: 0.25rem 0;">Nur aggregierte Daten</p>
    <p style="margin: 0.25rem 0;">Keine personenbezogenen Daten</p>
</div>
""", unsafe_allow_html=True)

# ===== FOOTER MIT DATENSCHUTZ & ETHIK =====
# Professioneller Footer mit wichtigen Informationen zu Datenschutz, Ethik und Datennutzung
footer_timestamp = get_local_time().strftime('%Y-%m-%d %H:%M:%S')
st.markdown(f"""
<div class="footer">
    <div class="footer-content">
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 2.5rem; margin-bottom: 2rem;">
            <div>
                <h4 style="color: #111827; font-size: 0.9375rem; font-weight: 700; margin-bottom: 1rem; letter-spacing: -0.01em;">Datenschutz</h4>
                <p style="color: #4b5563; font-size: 0.8125rem; line-height: 1.7; margin: 0;">
                    Alle angezeigten Daten sind aggregiert und anonymisiert. Es werden keine personenbezogenen Gesundheitsdaten (PHI) oder Patientenkennungen gespeichert oder angezeigt. Die Daten dienen ausschließlich operativen Einblicken.
                </p>
            </div>
            <div>
                <h4 style="color: #111827; font-size: 0.9375rem; font-weight: 700; margin-bottom: 1rem; letter-spacing: -0.01em;">Ethik</h4>
                <p style="color: #4b5563; font-size: 0.8125rem; line-height: 1.7; margin: 0;">
                    KI-Empfehlungen sind lediglich Vorschläge. Alle Entscheidungen verbleiben beim Menschen. Das Personal behält die volle Kontrolle über Entscheidungen zur Patientenversorgung. Das System unterstützt, ersetzt aber niemals das klinische Urteilsvermögen.
                </p>
            </div>
            <div>
                <h4 style="color: #111827; font-size: 0.9375rem; font-weight: 700; margin-bottom: 1rem; letter-spacing: -0.01em;">Datennutzung</h4>
                <p style="color: #4b5563; font-size: 0.8125rem; line-height: 1.7; margin: 0;">
                    Kennzahlen, Prognosen und Empfehlungen basieren auf Mustern operativer Daten. Alle Aktionen werden im Prüfprotokoll für Transparenz und Nachvollziehbarkeit protokolliert.
                </p>
            </div>
        </div>
        <div style="text-align: center; padding-top: 1.5rem; border-top: 1px solid #e5e7eb;">
            <p style="color: #9ca3af; font-size: 0.75rem; margin: 0; font-weight: 500;">
                HospitalFlow MVP v1.0 • Entwickelt für den Krankenhausbetrieb • Letzte Aktualisierung: {footer_timestamp}
            </p>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ===== AUTO-REFRESH IMPLEMENTIERUNG =====
# Implementiert die automatische Seitenaktualisierung basierend auf konfiguriertem Intervall
if auto_refresh:
    # Prüfe ob genug Zeit vergangen ist seit dem letzten Refresh
    if 'last_auto_refresh' not in st.session_state:
        st.session_state.last_auto_refresh = time.time()
    
    # Berechne vergangene Zeit seit letztem Refresh
    elapsed = time.time() - st.session_state.last_auto_refresh
    if elapsed >= refresh_seconds:
        # Zeit ist abgelaufen: Aktualisiere Seite
        st.session_state.last_auto_refresh = time.time()
        st.rerun()  # Neuladen der gesamten Streamlit-Seite

