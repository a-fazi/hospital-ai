# SAVE POINT - HospitalFlow Projekt

**Erstellt am:** 2025-01-XX  
**Zweck:** Vollständige Dokumentation des aktuellen Projektstands zur exakten Reproduktion

---

## 1. Projektübersicht

### Projektname
HospitalFlow - Hospital Operations Dashboard

### Version
MVP v1.0

### Beschreibung
Moderne Streamlit-Anwendung für Krankenhauspersonal mit Live-Metriken, Vorhersagen und Empfehlungen. Verwendet Mock-Daten statt echter Datenbank/Simulation.

### Technologie-Stack
- **Framework:** Streamlit >= 1.28.0
- **Visualisierung:** Plotly >= 5.17.0
- **Datenverarbeitung:** Pandas >= 2.0.0
- **Python:** 3.11+
- **Container:** Docker mit docker-compose

### Hauptfunktionalitäten
- Live-Metriken Dashboard
- 5-15 Minuten Vorhersagen
- Warnungssystem (Alerts)
- KI-Empfehlungen
- Transport-Management
- Inventar-Überwachung
- Gerätewartung
- Entlassungsplanung
- Kapazitätsübersicht
- Dienstplan-Verwaltung
- Prüfprotokoll (Audit Log)

---

## 2. Dateistruktur

```
hospital-flow-main/
├── app.py                    # Hauptanwendung (Streamlit)
├── utils.py                  # Hilfsfunktionen und Algorithmen
├── mocks.py                  # Mock-Datenbank und Mock-Simulation
├── requirements.txt          # Python-Abhängigkeiten
├── Dockerfile                # Docker-Image-Konfiguration
├── docker-compose.yml        # Docker-Compose-Konfiguration
├── README.md                 # Projekt-Dokumentation
├── SAVE_POINT.md            # Diese Datei
├── data/
│   └── hospitalflow.db      # SQLite-Datenbank (optional, wird nicht verwendet)
└── ui/
    ├── __init__.py
    ├── styling.py           # CSS-Styling
    ├── components.py        # Wiederverwendbare UI-Komponenten
    └── pages/
        ├── __init__.py
        ├── dashboard.py     # Dashboard-Seite
        ├── metrics.py       # Live-Metriken-Seite
        ├── predictions.py   # Vorhersagen-Seite
        ├── operations.py    # Betrieb-Seite (Alerts, Recommendations, Audit)
        ├── capacity.py      # Kapazitätsübersicht
        ├── transport.py     # Transport-Management
        ├── inventory.py     # Inventar-Überwachung
        ├── devices.py       # Gerätewartung
        ├── discharge_planning.py  # Entlassungsplanung
        ├── dienstplan.py    # Dienstplan-Verwaltung
        ├── alerts.py        # Warnungen-Seite
        └── recommendations.py  # Empfehlungen-Seite
```

---

## 3. Konfigurationsdateien

### 3.1 requirements.txt
```
streamlit>=1.28.0
plotly>=5.17.0
pandas>=2.0.0
```

### 3.2 Dockerfile
```dockerfile
# Use official Python runtime as base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

# Run Streamlit app
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

### 3.3 docker-compose.yml
```yaml
services:
  hospital-flow:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: hospital-flow
    ports:
      - "8501:8501"
    volumes:
      # Persist database data
      - ./data:/app/data
      # Mount code for development (Hot Reload - Code-Änderungen werden automatisch erkannt)
      - .:/app
    environment:
      - PYTHONUNBUFFERED=1
      - DB_PATH=data/hospitalflow.db
    restart: unless-stopped
    healthcheck:
      test:
        [
          "CMD",
          "python",
          "-c",
          "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')",
        ]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 5s
```

---

## 4. Hauptcode-Dateien

### 4.1 app.py - Struktur und Konfiguration

**Zeitzone:**
- Konfiguriert: `LOCAL_TIMEZONE = 'Europe/Berlin'`
- Funktion: `get_local_time()` gibt aktuelle Zeit in lokaler Zeitzone zurück

**Streamlit-Konfiguration:**
- `page_title`: "HospitalFlow"
- `page_icon`: "🏥"
- `layout`: "wide"
- `initial_sidebar_state`: "expanded"

**Session State:**
- `rerun_disabled`: False (Standard)
- `demo_mode`: False (Standard)
- `auto_refresh`: True (Standard)
- `refresh_interval`: '30 Sekunden' (Standard)
- `last_auto_refresh`: Zeitstempel für Auto-Refresh

**Navigation (PAGES):**
```python
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
```

**Mock-Initialisierung:**
- `db = get_mock_db()` - Mock-Datenbank
- `sim = get_mock_simulation()` - Mock-Simulation (gespeichert in `st.session_state.simulation`)

**Cached-Funktionen:**
- `get_cached_alerts()` - Gibt `db.get_active_alerts()` zurück
- `get_cached_recommendations()` - Gibt `db.get_pending_recommendations()` zurück
- `get_cached_capacity()` - Gibt `db.get_capacity_overview()` zurück

**Seiten-Routing:**
Jede Seite hat eine `render(db, sim, get_cached_alerts, get_cached_recommendations, get_cached_capacity)` Funktion.

**Auto-Refresh:**
- Aktivierbar über Toggle in Sidebar
- Intervalle: 10, 30, 60 Sekunden
- Implementierung: Prüft `elapsed >= refresh_seconds` und ruft `st.rerun()` auf

**Footer:**
- Enthält Datenschutz-, Ethik- und Datennutzungs-Informationen
- Zeigt Versionsnummer und Zeitstempel

### 4.2 utils.py - Funktionen

**Vorhersage-Funktionen:**
- `calculate_prediction_confidence(base_value, time_horizon)` - Berechnet Vertrauen (0.6-1.0)
- `calculate_patient_arrival_prediction(...)` - Berechnet Patientenzugang-Vorhersage
- `calculate_bed_demand_prediction(...)` - Berechnet Bettenbedarf-Vorhersage

**Formatierungsfunktionen:**
- `format_time_ago(timestamp)` - Formatiert relative Zeit ("vor 5 Min.")
- `format_duration_minutes(minutes)` - Formatiert Dauer ("2 Std. 15 Min.")

**Farbfunktionen:**
- `get_severity_color(severity)` - Farben für Schweregrade (hoch/mittel/niedrig)
- `get_priority_color(priority)` - Farben für Prioritäten
- `get_risk_color(risk_level)` - Farben für Risikostufen
- `get_status_color(status)` - Farben für Status
- `get_department_color(department)` - Farben für Abteilungen
- `get_explanation_score_color(score)` - Farben für Erklärungsscores

**Berechnungsfunktionen:**
- `calculate_inventory_status(current, min_threshold, max_capacity)` - Inventarstatus
- `calculate_capacity_status(utilization)` - Kapazitätsstatus
- `calculate_metric_severity(value, thresholds)` - Metrik-Schweregrad
- `get_metric_severity_for_load(load_percent)` - Schweregrad für Auslastung
- `get_metric_severity_for_count(count, thresholds)` - Schweregrad für Zählwerte
- `get_metric_severity_for_free(free, total)` - Schweregrad für freie Ressourcen
- `calculate_explanation_score(trend_strength, data_points, confidence)` - Erklärungsscore

**Gerätewartung:**
- `get_max_usage_hours(device_type)` - Maximale Betriebsstunden pro Gerätetyp
- `get_maintenance_duration(device_type)` - Standard-Wartungsdauer in Minuten
- `suggest_maintenance_times(device, predictions, days_ahead)` - Vorschläge für Wartungszeiten
- `calculate_device_urgency(days_until_maintenance, usage_hours, max_usage_hours)` - Wartungsdringlichkeit

**Inventar:**
- `calculate_daily_consumption_from_activity(...)` - Täglicher Verbrauch basierend auf Aktivität
- `calculate_operation_consumption(operation_type, department, duration_minutes)` - Verbrauch pro Operation
- `calculate_days_until_stockout(current_stock, daily_consumption_rate)` - Tage bis Engpass
- `calculate_reorder_suggestion(...)` - Nachfüllvorschlag

**System:**
- `get_system_status()` - Gibt Systemstatus zurück (immer "betriebsbereit", "#10B981")

### 4.3 mocks.py - Mock-Datenstrukturen

**MockDB-Klasse:**
Alle Methoden geben statische Mock-Daten zurück:

- `get_active_alerts()` - 3 Beispiel-Warnungen
- `get_pending_recommendations()` - 3 Beispiel-Empfehlungen
- `get_capacity_overview()` - 5 Abteilungen (ER, ICU, Surgery, Cardiology, General Ward)
- `get_transport_requests()` - 6 Transportanfragen (verschiedene Status)
- `get_inventory_status()` - 5 Inventar-Artikel
- `get_device_maintenance_urgencies()` - 4 Geräte mit Wartungsdringlichkeiten
- `get_predictions(time_horizon_minutes)` - 4 Vorhersagen
- `get_all_staff()` - Personal nach Kategorien (Pflegekräfte, Ärzte, Logistik, Orga)
- `get_staff_schedule(staff_id, week_start)` - Dienstplan für Mitarbeiter
- `get_actual_hours(staff_id, week_start)` - Tatsächliche Arbeitsstunden
- `calculate_overtime(staff_id, week_start)` - Überstunden-Berechnung
- `get_discharge_planning()` - Entlassungsplanungsdaten nach Abteilung
- `get_recent_operations(...)` - 3 Beispiel-Operationen
- `get_audit_log(limit)` - 2 Beispiel-Audit-Einträge
- `acknowledge_alert(alert_id)` - Gibt immer True zurück
- `accept_recommendation(rec_id, action_text)` - Gibt immer True zurück
- `reject_recommendation(rec_id, action_text)` - Gibt immer True zurück
- `confirm_maintenance(device_id, scheduled_time, ...)` - Gibt (True, None) zurück
- `complete_maintenance(device_id)` - Gibt True zurück
- `create_inventory_order(item_id, quantity, ...)` - Gibt {'success': True, 'order_id': random} zurück
- `update_transport_status(transport_id, ...)` - Gibt True zurück
- `suggest_optimal_maintenance_times(device_id, max_suggestions)` - Generiert 5 Vorschläge

**MockSimulation-Klasse:**
- `state`: Dictionary mit aktuellen Metriken:
  - `ed_load`: 72.5
  - `waiting_count`: 10
  - `beds_free`: 35
  - `staff_load`: 78.0
  - `rooms_free`: 8
  - `or_load`: 65.0
  - `transport_queue`: 4
  - `inventory_risk_count`: 2
- `active_events`: Liste (kann Surge-Events enthalten)
- `trends`: Dictionary mit Trend-Werten
- `get_current_metrics()` - Gibt `state.copy()` zurück
- `get_metric_history(metric_name, minutes)` - Generiert historische Daten mit Variation
- `apply_recommendation_effect(...)` - Tut nichts (Mock)
- `update()` - Tut nichts (Mock)

**Globale Instanzen:**
- `_mock_db`: Singleton MockDB-Instanz
- `_mock_sim`: Singleton MockSimulation-Instanz
- `get_mock_db()` - Gibt Singleton zurück
- `get_mock_simulation()` - Gibt Singleton zurück

### 4.4 ui/styling.py - CSS-Styling

**apply_custom_styles():**
Wendet umfassendes CSS-Styling an:

- **Typografie:** System-Fonts, Antialiasing
- **Hauptcontainer:** Padding, max-width: 1600px
- **Sticky Header:** Gradient-Hintergrund, Box-Shadow
- **Page Header:** Große Titel, Subtitel
- **Metric Cards:** Gradient-Hintergrund, Border-Left, Hover-Effekte
- **Badges:** Abgerundete Ecken, Schatten
- **Tabellen:** Abgerundete Ecken, Border
- **Empty States:** Zentriert, gestrichelter Border
- **Footer:** Gradient-Hintergrund, Grid-Layout
- **Legende:** Flex-Layout, Badge-Styling
- **Buttons:** Hover-Effekte, Schatten
- **Sidebar:** Gradient-Hintergrund
- **Eingabefelder:** Focus-States mit Border-Farbe
- **Ladezustände:** Spinner-Farben

**Farben:**
- Rot (Hoch/Kritisch): #DC2626, #991B1B
- Bernstein (Mittel): #F59E0B
- Grün (Niedrig): #10B981
- Blau (Aktiv): #3B82F6
- Grau (Standard): #6B7280, #9CA3AF
- Primary: #667EEA, #4F46E5

### 4.5 ui/components.py - UI-Komponenten

**render_badge(text, severity):**
- Erstellt Badge mit Farbe basierend auf Schweregrad
- Verwendet `get_severity_color()` aus utils

**render_empty_state(icon, title, text):**
- Erstellt konsistenten leeren Zustand
- Verwendet CSS-Klassen aus styling.py

---

## 5. Seiten-Module

### 5.1 dashboard.py

**render(db, sim, get_cached_alerts, get_cached_recommendations, get_cached_capacity):**

**Metriken (8 Karten in 4x2 Grid):**
1. Notaufnahme-Auslastung (ED Load)
2. Wartende Patienten (Waiting Count)
3. Freie Betten (Beds Free)
4. Personal-Auslastung (Staff Load)
5. Freie Räume (Rooms Free)
6. OP-Auslastung (OR Load)
7. Transport-Warteschlange (Transport Queue)
8. Bestands-/Gerätedringlichkeit (Urgency Count)

**Diagramme:**
- Wartende Anzahl (letzte 60 Minuten)
- Notaufnahme-Auslastung (letzte 60 Minuten)

**Ausblick-Panel:**
- Top 3 vorhergesagte Engpässe (nächste 15 Minuten)

**Warnungen:**
- Zeigt bis zu 5 kürzliche Warnungen als Karten

**Empfehlungen:**
- Zeigt bis zu 3 ausstehende Empfehlungen als Karten

### 5.2 metrics.py

**render(db, sim, ...):**

**Features:**
- Auto-Refresh Toggle (5 Min. Cache-TTL)
- Umfassende Filter (Zeitraum, Abteilung, Textsuche, Min/Max-Werte)
- 8 Tabs: Metriken, Alerts, Vorhersagen, Empfehlungen, Transport, Inventar, Geräte, Kapazität
- CSV-Export für alle Datentypen
- Diagramme für Metriken-Trends

**Filter:**
- Zeitraum: 1h, 6h, 24h, 7d, 30d, all
- Abteilung: Multi-Select
- Textsuche: Volltextsuche
- Min/Max-Werte: Numerische Filter
- Erweiterte Filter: Schweregrad, Status (je nach Tab)

### 5.3 predictions.py

**render(db, sim, ...):**

**Features:**
- Filter: Abteilung, Kategorie, Zeithorizont
- Smart-Filter-Logik mit "Alle"-Option
- Vorhersagen-Karten mit Wert, Konfidenz, Zeithorizont
- Scatter-Plot: Vertrauen nach Zeithorizont

**Vorhersage-Typen:**
- `patient_arrival`: Patientenzugang
- `bed_demand`: Bettenbedarf

**Zeithorizonte:**
- 5, 10, 15 Minuten

### 5.4 operations.py

**render(db, sim, ...):**

**3 Tabs:**

**1. Warnungen:**
- Filter: Bereich, Schweregrad, Zeitraum
- Warnungen als Karten mit Bestätigungs-Button
- Bestätigte Warnungen haben blaue Farbe

**2. Empfehlungen:**
- Empfehlungen als Karten
- Expandable "Warum vorgeschlagen?" Sektion
- Annehmen/Ablehnen mit Text-Eingabe
- Simulationseffekte werden angewendet bei Annahme

**3. Prüfprotokoll:**
- Filter: Rolle, Aktion, Bereich
- Tabelle mit deutschen Übersetzungen
- Refresh-Button

### 5.5 capacity.py

**render(db, sim, ...):**

**Features:**
- Gesamt-Kennzahlen: Gesamtbetten, Belegt, Verfügbar, Gesamtauslastung
- Abteilungs-Karten mit Auslastungs-Balken
- 2 Diagramme:
  - Auslastung nach Abteilung (Bar Chart)
  - Bettenverfügbarkeit nach Abteilung (Stacked Bar Chart)

### 5.6 transport.py

**render(db, sim, ...):**

**Features:**
- Zusammenfassende Kennzahlen: Anfragen, Aktiv, Geplant, Abgeschlossen
- Gruppierung nach Status:
  - Transportanfragen (pending) - mit Bestätigungs-Button
  - Aktive Transporte (in_progress)
  - Geplante Transporte (planned)
  - Abgeschlossene Transporte (completed) - in Expander

**Transport-Karten zeigen:**
- Priorität, Status, Typ
- Von → Nach
- Geschätzte/tatsächliche Zeit
- Geplante Startzeit (für planned)
- Erwartete Ankunft (für in_progress)
- Verzögerung (falls vorhanden)

### 5.7 inventory.py

**render(db, sim, ...):**

**Features:**
- Nachfüllvorschläge mit Bestell-Button
- Aktive Bestellungen mit Transport-Info
- Lagerrisiko-Übersicht:
  - Filter: Material-Suche, Abteilung
  - Tabelle mit: Aktuell, Mindestbestand, Max. Kapazität, Verbrauch/Tag, Tage bis Engpass, Risiko
  - Fortschrittsleiste mit Mindestbestand-Markierung
- Bestandsverlauf (Liniendiagramm für letzte 14 Tage)
  - Multi-Select für Materialien
  - Simulierte historische Daten

**Berechnungen:**
- Verbrauchsrate basierend auf ED Load, Bettenauslastung, Abteilung
- Tage bis Engpass (präzise)
- Nachfüllvorschläge mit Priorität und Bestelltermin

### 5.8 devices.py

**render(db, sim, ...):**

**Features:**
- Dringlichkeitszusammenfassung: Hoch, Mittel, Gesamt
- Geräte-Gruppierung:
  - Mit geplanter Wartung (bestätigt)
  - Ohne geplante Wartung
- Geräte-Karten zeigen:
  - Gerätetyp, Geräte-ID, Abteilung
  - Letzte Wartung, Betriebszeit, Tage bis fällig
  - Empfohlenes Wartungsfenster
  - Dringlichkeits-Badge
- Wartungsplanung-Expander:
  - "Zeiten vorschlagen" Button
  - Vorgeschlagene Zeiten mit Score, erwartete Patienten, Grund
  - Manuelle Zeitauswahl: Datum, Uhrzeit, Dauer
  - "Wartung bestätigen" Button
  - "Wartung abschließen" Button (falls geplant)
- Dringlichkeitsverteilung (Pie Chart)

### 5.9 discharge_planning.py

**render(db, sim, ...):**

**Features:**
- Erwartete Entlassungen (nächste 4, 8, 12 Stunden)
- Zeitstrahl für nächste 12 Stunden (Bar Chart)
- Empfehlungen basierend auf Entlassungsmustern
- Statistiken: Spitzenstunde, Durchschnitt, Gesamt, Niedrigphasen
- Entlassungsplanungs-Übersicht:
  - Abteilungs-Karten mit Entlassungsbereit, Ausstehend, Ø Verweildauer
  - 2 Diagramme: Entlassungsstatus, Ø Verweildauer

### 5.10 dienstplan.py

**render(db, sim):**

**Features:**
- 2-Spalten-Layout: Links Personal-Liste, Rechts Detail
- Personal gruppiert nach Kategorien: Pflegekräfte, Ärzte, Logistik, Orga
- Person-Auswahl mit Button
- Detailansicht:
  - Zusammenfassung: Vertragsstunden, Geplante Stunden, Tatsächliche Stunden, Überstunden
  - Wochennavigation: Vorherige/Nächste Woche
  - Kalenderansicht: 7 Tage mit geplanten/tatsächlichen Stunden
  - Heute wird hervorgehoben

### 5.11 alerts.py

**render(db, sim, ...):**

**Features:**
- Filter: Schweregrad, Bereich
- "Zurücksetzen" Button (setzt alle Warnungen zurück)
- Warnungen als Karten mit Bestätigungs-Button
- Bestätigte Warnungen haben blaue Farbe und "✓ BESTÄTIGT" Badge

### 5.12 recommendations.py

**render(db, sim, ...):**

**Features:**
- Filter: Priorität, Abteilung, Typ, Vertrauen
- Empfehlungen als Karten
- Neues Template-Format: Maßnahme, Begründung, Erwartete Auswirkung, Sicherheits-Hinweis
- Altes Format: Titel, Beschreibung
- Expandable "Warum vorgeschlagen?" Sektion
- Annehmen/Ablehnen mit Text-Eingabe
- Simulationseffekte werden angewendet bei Annahme

---

## 6. Design-System

### 6.1 Farbpalette

**Schweregrade:**
- Hoch/Kritisch: #DC2626 (rot-600), #991B1B (rot-800)
- Mittel: #F59E0B (bernstein-500)
- Niedrig: #10B981 (smaragd-500)

**Status:**
- Ausstehend/Wartung: #F59E0B (bernstein-500)
- In Bearbeitung: #3B82F6 (blau-500)
- Abgeschlossen/Akzeptiert/Betriebsbereit: #10B981 (smaragd-500)
- Abgelehnt: #EF4444 (rot-500)

**Abteilungen:**
- ER/Notaufnahme: #EF4444
- ICU/Intensivstation: #DC2626
- Surgery/Chirurgie: #3B82F6
- Cardiology/Kardiologie: #8B5CF6
- General Ward/Allgemeinstation: #10B981

**Primary:**
- #667EEA, #4F46E5

**Grays:**
- #111827 (dunkel), #6B7280 (mittel), #9CA3AF (hell)

### 6.2 Typografie

**Font-Family:**
- System-Fonts: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', Roboto, 'Helvetica Neue', Arial, sans-serif
- Antialiasing aktiviert

**Schriftgrößen:**
- Page Title: 2.25rem
- Page Subtitle: 0.9375rem
- Metric Value: 2.25rem - 2.5rem
- Metric Label: 0.8125rem
- Badge: 0.6875rem
- Body: 0.9375rem

**Font-Weights:**
- Headings: 600-700
- Body: 400-500
- Badges: 700

### 6.3 Komponenten-Stile

**Metric Cards:**
- Gradient-Hintergrund: #ffffff → #fafbfc
- Border-Left: 4px solid (Farbe basierend auf Schweregrad)
- Border-Radius: 16px
- Box-Shadow: 0 2px 8px rgba(0, 0, 0, 0.06)
- Hover: translateY(-2px), stärkerer Schatten

**Badges:**
- Padding: 0.4375rem 0.875rem
- Border-Radius: 12px
- Font-Size: 0.6875rem
- Font-Weight: 700
- Text-Transform: uppercase
- Letter-Spacing: 0.08em

**Info Cards:**
- Gradient-Hintergrund: #ffffff → #fafbfc
- Border: 1px solid #e5e7eb
- Border-Radius: 12px
- Box-Shadow: 0 2px 6px rgba(0, 0, 0, 0.05)
- Hover: translateY(-1px), stärkerer Schatten

**Empty States:**
- Zentriert
- Padding: 4rem 2rem
- Gradient-Hintergrund: #fafbfc → #f9fafb
- Border: 2px dashed #d1d5db
- Border-Radius: 16px
- Icon: 4rem, Opacity: 0.4

### 6.4 Layout-Struktur

**Hauptcontainer:**
- Max-Width: 1600px
- Padding-Top: 1.5rem
- Padding-Bottom: 3rem

**Sidebar:**
- Gradient-Hintergrund: #ffffff → #fafbfc
- Border-Right: 1px solid #e5e7eb
- Expanded by default

**Spalten:**
- Standard: 4 Spalten für Metriken
- Flexibel: 2-3 Spalten für andere Inhalte
- Gap: 1rem

---

## 7. Mock-Daten-Struktur

### 7.1 Alerts

**Format:**
```python
{
    'id': int,
    'timestamp': str (ISO-Format),
    'severity': str ('high', 'medium', 'low'),
    'message': str,
    'department': str,
    'metric_type': str,
    'value': float,
    'acknowledged': bool
}
```

**Beispielwerte:**
- 3 Alerts (1 high, 1 medium, 1 low)
- Timestamps: vor 5, 15, 30 Minuten

### 7.2 Recommendations

**Format:**
```python
{
    'id': int,
    'timestamp': str (ISO-Format),
    'title': str,
    'description': str,
    'priority': str ('high', 'medium', 'low'),
    'department': str,
    'recommendation_type': str,
    'status': str ('pending'),
    'expected_impact': str,
    # Optional (neues Format):
    'action': str,
    'reason': str,
    'safety_note': str,
    'explanation_score': str
}
```

**Beispielwerte:**
- 3 Recommendations (1 high, 1 medium, 1 low)
- Timestamps: vor 10, 25, 45 Minuten

### 7.3 Capacity

**Format:**
```python
{
    'department': str,
    'total_beds': int,
    'occupied_beds': int,
    'free_beds': int,
    'utilization_percent': float
}
```

**Beispielwerte:**
- 5 Abteilungen: ER (25/20/5/80%), ICU (15/13/2/86.7%), Surgery (40/32/8/80%), Cardiology (30/24/6/80%), General Ward (60/45/15/75%)

### 7.4 Transport Requests

**Format:**
```python
{
    'id': int,
    'timestamp': str (ISO-Format),
    'from_location': str,
    'to_location': str,
    'priority': str,
    'status': str ('pending', 'in_progress', 'completed', 'planned'),
    'request_type': str ('patient', 'equipment'),
    'estimated_time_minutes': int,
    'actual_time_minutes': int (optional),
    'start_time': str (optional),
    'expected_completion_time': str (optional),
    'delay_minutes': int (optional),
    'related_entity_type': str (optional),
    'related_entity_id': int (optional),
    'planned_start_time': str (optional)
}
```

**Beispielwerte:**
- 6 Transporte: 2 pending, 2 in_progress, 1 completed, 1 planned

### 7.5 Inventory

**Format:**
```python
{
    'id': int,
    'item_name': str,
    'department': str,
    'current_stock': int,
    'min_threshold': int,
    'max_capacity': int,
    'unit': str,
    'last_updated': str (ISO-Format)
}
```

**Beispielwerte:**
- 5 Artikel: Sauerstoffflaschen (45/50/100), OP-Masken (120/100/500), Infusionslösungen (25/30/200), Beatmungsfilter (8/10/50), OP-Handschuhe (500/200/1000)

### 7.6 Devices

**Format:**
```python
{
    'id': int,
    'device_name': str,
    'device_type': str,
    'department': str,
    'usage_hours': int,
    'max_usage_hours': int,
    'next_maintenance_due': str (YYYY-MM-DD),
    'urgency_level': str ('high', 'medium', 'low'),
    'days_until_maintenance': int (kann negativ sein),
    'scheduled_maintenance_time': str (optional, ISO-Format),
    'maintenance_confirmed': bool
}
```

**Beispielwerte:**
- 4 Geräte: 2 high urgency, 1 medium, 1 low

### 7.7 Predictions

**Format:**
```python
{
    'id': int,
    'timestamp': str (ISO-Format),
    'prediction_type': str ('patient_arrival', 'bed_demand'),
    'predicted_value': float,
    'confidence': float (0.0-1.0),
    'time_horizon_minutes': int (5, 10, 15),
    'department': str
}
```

**Beispielwerte:**
- 4 Vorhersagen: 3 patient_arrival (5/10/15 Min), 1 bed_demand (15 Min)

### 7.8 Staff

**Format:**
```python
{
    'id': int,
    'name': str,
    'role': str,
    'department': str,
    'category': str ('Pflegekräfte', 'Ärzte', 'Logistik', 'Orga'),
    'contact': str (Email)
}
```

**Beispielwerte:**
- 6 Mitarbeiter: 2 Pflegekräfte, 2 Ärzte, 1 Logistik, 1 Orga

### 7.9 Discharge Planning

**Format:**
```python
{
    'department': str,
    'ready_for_discharge_count': int,
    'pending_discharge_count': int,
    'total_patients': int
}
```

**Beispielwerte:**
- 3 Abteilungen: General Ward (8/3/45), Cardiology (5/2/24), Surgery (6/1/32)

---

## 8. Funktionalitäten

### 8.1 Auto-Refresh

**Konfiguration:**
- Toggle in Sidebar
- Intervalle: 10, 30, 60 Sekunden
- Standard: 30 Sekunden

**Implementierung:**
- Prüft `elapsed >= refresh_seconds`
- Ruft `st.rerun()` auf
- Speichert `last_auto_refresh` in Session State

### 8.2 Demo-Modus

**Konfiguration:**
- Toggle in Sidebar
- Standard: False

**Effekt:**
- Erhöht Ereignisfrequenz (wird in Mock-Simulation nicht implementiert, aber vorbereitet)

### 8.3 Filter-Systeme

**Smart-Filter (predictions.py):**
- "Alle"-Option in Multi-Select
- Logik: Wenn "Alle" + andere Optionen → entferne "Alle"
- Wenn nur "Alle" → zeige alle

**Standard-Filter:**
- Multi-Select oder Selectbox
- "Alle"-Option als erster Eintrag
- Filter werden auf Daten angewendet

### 8.4 CSV-Export

**Implementierung:**
- `export_to_csv(df, filename_prefix)` in metrics.py
- `prepare_export_df(df, required_cols, default_values)` für fehlende Spalten
- Download-Button mit Timestamp im Dateinamen

### 8.5 Simulationseffekte

**Bei Annahme von Empfehlungen:**
- `sim.apply_recommendation_effect(rec_type, effect_name, duration_minutes)`
- Mock-Implementierung tut nichts, aber vorbereitet

**Empfehlungstypen:**
- `staffing_reassignment`: 30 Minuten
- `open_overflow_beds`: 45 Minuten
- `room_allocation`: 30 Minuten

### 8.6 Wartungsplanung

**Vorschläge:**
- `suggest_optimal_maintenance_times()` in utils.py
- Berücksichtigt: Dringlichkeit, Patientenlast, Fälligkeitsdatum
- Score-Berechnung: 40% Dringlichkeit, 40% Patientenlast, 20% Timing
- Top 10 Vorschläge, sortiert nach Score

**Bestätigung:**
- Datum, Uhrzeit, Dauer auswählen
- Oder aus Vorschlägen auswählen
- `db.confirm_maintenance()` aufrufen

**Abschluss:**
- Button "Wartung abschließen" (nur wenn geplant und bestätigt)
- `db.complete_maintenance()` aufrufen

### 8.7 Inventar-Bestellungen

**Nachfüllvorschläge:**
- Berechnet basierend auf Verbrauchsrate und Tagen bis Engpass
- Priorität: hoch/mittel/niedrig
- Bestellmenge und -termin werden vorgeschlagen

**Bestellung:**
- Button "Bestellung bestätigen"
- `db.create_inventory_order()` aufrufen
- Erfolgs-/Fehlermeldung wird angezeigt
- Processing-Flag verhindert mehrfache Verarbeitung

### 8.8 Transport-Status-Updates

**Bestätigung:**
- Button für pending Transporte
- `db.update_transport_status(transport_id, status='planned')` aufrufen

**Status-Übergänge:**
- pending → planned (Bestätigung)
- planned → in_progress (automatisch)
- in_progress → completed (automatisch)

---

## 9. Abhängigkeiten

### 9.1 Python-Version
- **Erforderlich:** Python 3.11+
- **Empfohlen:** Python 3.11 (wie in Dockerfile)

### 9.2 Python-Pakete

**requirements.txt:**
```
streamlit>=1.28.0
plotly>=5.17.0
pandas>=2.0.0
```

**Zusätzliche Standard-Bibliotheken (Python stdlib):**
- `datetime` - Zeitstempel und Datumsoperationen
- `time` - Zeitoperationen
- `random` - Zufallswerte für Simulation
- `typing` - Type Hints
- `io` - StringIO für CSV-Export
- `json` - JSON-Verarbeitung (optional)
- `os` - Betriebssystem-Operationen (optional)
- `zoneinfo` - Zeitzonen (Python 3.9+)

### 9.3 System-Anforderungen

**Docker:**
- Docker Engine
- Docker Compose

**Ohne Docker:**
- Python 3.11+
- pip
- Port 8501 frei

### 9.4 Browser-Anforderungen
- Moderne Browser mit JavaScript
- Empfohlen: Chrome, Firefox, Safari, Edge (neueste Versionen)

---

## 10. Wichtige Design-Entscheidungen

### 10.1 Mock-Daten statt echter Datenbank
- **Grund:** Einfacheres Setup, keine Datenbank-Konfiguration nötig
- **Implementierung:** `mocks.py` mit MockDB und MockSimulation
- **Vorteil:** Sofort lauffähig, konsistente Testdaten

### 10.2 Zeitzone-Konfiguration
- **Standard:** Europe/Berlin
- **Konfigurierbar:** `LOCAL_TIMEZONE` in app.py
- **Verwendung:** Alle Zeitstempel werden in lokaler Zeitzone angezeigt

### 10.3 Session State Management
- **Zweck:** Verhindert unnötige Neustarts bei Widget-Interaktionen
- **Wichtig:** `rerun_disabled` Flag (aktuell nicht verwendet, aber vorbereitet)

### 10.4 Caching-Strategie
- **Mock-Daten:** Kein echtes Caching nötig (statische Daten)
- **Metrics-Seite:** `@st.cache_data(ttl=300)` für 5 Minuten
- **Vorteil:** Reduziert Flackern, verbessert Performance

### 10.5 Deutsche Übersetzungen
- **Konsistent:** Alle UI-Texte auf Deutsch
- **Daten:** Mock-Daten enthalten deutsche und englische Werte
- **Mapping:** Übersetzungs-Maps in jedem Modul

### 10.6 Responsive Design
- **Layout:** "wide" für mehr Platz
- **Spalten:** Flexibel (2-4 Spalten je nach Kontext)
- **Mobile:** Streamlit-Standard (nicht speziell optimiert)

---

## 11. Reproduktionsanleitung

### 11.1 Mit Docker

```bash
# 1. Repository klonen/herunterladen
cd hospital-flow-main

# 2. Docker Compose starten
docker-compose up -d

# 3. Browser öffnen
# http://localhost:8501
```

### 11.2 Ohne Docker

```bash
# 1. Repository klonen/herunterladen
cd hospital-flow-main

# 2. Virtual Environment erstellen (optional)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oder
venv\Scripts\activate  # Windows

# 3. Abhängigkeiten installieren
pip install -r requirements.txt

# 4. Anwendung starten
streamlit run app.py

# 5. Browser öffnen
# http://localhost:8501
```

### 11.3 Dateien prüfen

**Wichtig:** Alle Dateien müssen vorhanden sein:
- `app.py`
- `utils.py`
- `mocks.py`
- `requirements.txt`
- `Dockerfile`
- `docker-compose.yml`
- `ui/styling.py`
- `ui/components.py`
- Alle Seiten-Module in `ui/pages/`

### 11.4 Funktionsprüfung

**Nach Start prüfen:**
1. Sidebar-Navigation funktioniert
2. Dashboard zeigt 8 Metrik-Karten
3. Alle Seiten laden ohne Fehler
4. Filter funktionieren
5. Buttons reagieren (Mock-Daten werden zurückgegeben)
6. Auto-Refresh funktioniert (Toggle in Sidebar)

---

## 12. Bekannte Einschränkungen

### 12.1 Mock-Daten
- Alle Daten sind statisch
- Keine echte Datenbank-Persistenz
- Simulationseffekte werden nicht gespeichert

### 12.2 Session State
- Daten werden bei Neustart zurückgesetzt
- Keine echte Persistenz zwischen Sessions

### 12.3 Performance
- Mock-Daten sind schnell
- Bei echten Datenbanken könnte Caching nötig sein

### 12.4 Browser-Kompatibilität
- Getestet mit modernen Browsern
- Ältere Browser könnten Probleme haben

---

## 13. Notizen für zukünftige Entwicklung

### 13.1 Datenbank-Integration
- Ersetze `get_mock_db()` durch echte Datenbank-Initialisierung
- Implementiere echte SQLite/PostgreSQL-Verbindung
- Migriere Mock-Daten in Datenbank-Schema

### 13.2 Simulation-Integration
- Ersetze `get_mock_simulation()` durch echte Simulation
- Implementiere periodische Updates
- Speichere Simulationszustand in Datenbank

### 13.3 Authentifizierung
- User-Login hinzufügen
- Rollenbasierte Zugriffe
- Session-Management

### 13.4 Echtzeit-Updates
- WebSocket-Integration für Live-Updates
- Server-Sent Events (SSE)
- Polling als Fallback

---

## 14. Versionshistorie

**v1.0 (aktueller Stand):**
- Vollständige Mock-Daten-Implementierung
- Alle Seiten-Module implementiert
- Design-System etabliert
- Docker-Setup konfiguriert
- Deutsche Übersetzungen vollständig

---

**Ende der Dokumentation**

*Diese Dokumentation erfasst den vollständigen Stand des HospitalFlow-Projekts zum Zeitpunkt der Erstellung. Sie dient als "Save Point" zur exakten Reproduktion des aktuellen Zustands.*

