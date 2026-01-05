# HospitalFlow - Hospital Operations Dashboard

A modern, clean MVP dashboard for hospital staff built with Streamlit and SQLite. HospitalFlow provides real-time metrics, short-term predictions, alerts, recommendations, and comprehensive operational oversight—all using aggregated data only (no personal information).

## Features

### Core Functionality

- **Live Metrics**: Real-time monitoring of key hospital metrics with time-series visualization
- **5-15 Minute Predictions**: AI-powered short-term forecasts for patient arrivals, bed demand, and resource needs
- **Alerts System**: Severity-based alerts (high/medium/low) with acknowledgment workflow
- **Recommendations**: Human-in-the-loop AI recommendations with accept/reject functionality
- **Audit Log**: Complete audit trail of all system actions and changes
- **Transport Management**: Track and manage patient, equipment, and specimen transport requests
- **Inventory Monitoring**: Real-time inventory status with low-stock alerts
- **Device Maintenance Risk**: Risk assessment for medical device maintenance scheduling
- **Discharge Planning**: Aggregated discharge planning metrics by department
- **Capacity Overview**: Comprehensive bed capacity and utilization tracking

### UI/UX Highlights

- **Modern Design**: Clean, professional interface with custom styling (not default Streamlit)
- **Consistent Design System**: Unified spacing, typography, icons, and color palette
- **Top Header + Left Navigation**: Intuitive multi-page navigation
- **Metric Cards**: Visual metric cards with clear hierarchy
- **Pill Badges**: Color-coded severity/priority/status indicators
- **Plotly Charts**: Interactive, publication-quality visualizations
- **Microcopy**: Helpful hints and empty states throughout
- **Keyboard-Friendly**: Thoughtful defaults and accessible controls

## Installation

1. **Clone or download this repository**

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   streamlit run app.py
   ```

4. **Access the dashboard**:
   The app will open automatically in your browser at `http://localhost:8501`

## Project Structure

Das Projekt verwendet eine modulare Struktur mit klarer Trennung von Komponenten:

```
hospital-flow-main/
├── app.py                    # Hauptanwendung mit Routing und Navigation
├── database.py               # SQLite-Datenbankoperationen
├── simulation.py             # Simulations-Engine
├── predictions.py            # Vorhersage-Engine
├── recommendations.py        # Empfehlungs-Engine
├── optimization.py           # Optimierungs-Engine
├── utils.py                  # Hilfsfunktionen (Formatierung, Berechnungen)
├── seed_data.py              # Datenbank-Seeding
├── requirements.txt          # Python-Abhängigkeiten
├── Dockerfile                # Docker-Image-Konfiguration
├── docker-compose.yml        # Docker-Compose-Konfiguration
├── README.md                 # Diese Datei
├── SAVE_POINT.md            # Vollständige Projekt-Dokumentation
├── data/
│   └── hospitalflow.db      # SQLite-Datenbank (wird automatisch erstellt)
└── ui/                       # UI-Module
    ├── __init__.py
    ├── styling.py           # CSS-Styling
    ├── components.py        # Wiederverwendbare UI-Komponenten
    └── pages/               # Seitenmodule
        ├── __init__.py
        ├── dashboard.py     # Dashboard-Seite
        ├── metrics.py       # Live-Metriken-Seite
        ├── predictions.py   # Vorhersagen-Seite
        ├── operations.py    # Betrieb-Seite (Alerts, Recommendations, Audit)
        ├── alerts.py        # Warnungen-Seite
        ├── recommendations.py  # Empfehlungen-Seite
        ├── transport.py     # Transport-Management
        ├── inventory.py     # Inventar-Überwachung
        ├── devices.py       # Gerätewartung
        ├── discharge_planning.py  # Entlassungsplanung
        ├── capacity.py      # Kapazitätsübersicht
        └── dienstplan.py    # Dienstplan-Verwaltung
```

### Modulare Architektur

#### `ui/styling.py`
Enthält alle CSS-Styles für die Anwendung. Wird einmal beim Start geladen.

#### `ui/components.py`
Wiederverwendbare UI-Komponenten:
- `render_badge()` - Schweregrad-Badges
- `render_empty_state()` - Leere Zustände
- `render_loading_spinner()` - Ladeanzeigen

#### `ui/pages/`
Jede Seite hat ihr eigenes Modul:
- Jedes Modul exportiert eine `render()` Funktion
- Nimmt `db`, `sim`, und andere benötigte Parameter entgegen
- Rendert die komplette Seite

#### `app.py`
Hauptanwendung:
- Initialisiert Datenbank und Simulation
- Lädt Styling und Komponenten
- Routet zu den entsprechenden Seitenmodulen
- Verwaltet Sidebar-Navigation

### Vorteile der modularen Struktur

- **Bessere Wartbarkeit**: Jede Seite ist isoliert
- **Einfacheres Testen**: Module können einzeln getestet werden
- **Wiederverwendbarkeit**: Komponenten können überall verwendet werden
- **Klarere Organisation**: Logische Trennung von Styling, Komponenten und Seiten

## Usage

### Navigation

Use the left sidebar to navigate between different sections:

- **Dashboard**: Overview with key metrics and recent alerts/recommendations
- **Live Metrics**: Real-time metrics with time-series charts
- **Predictions**: 5-15 minute forecasts with confidence scores
- **Alerts**: Active alerts with severity filtering and acknowledgment
- **Recommendations**: Review and accept/reject AI recommendations
- **Transport**: Manage transport requests by status
- **Inventory**: Monitor inventory levels with low-stock alerts
- **Device Maintenance**: Risk assessment for medical devices
- **Discharge Planning**: Aggregated discharge metrics by department
- **Capacity Overview**: Bed capacity and utilization tracking
- **Audit Log**: Complete system activity log

### Key Interactions

1. **Accepting/Rejecting Recommendations**:
   - Navigate to "Recommendations"
   - Enter action taken or rejection reason
   - Click "Accept" or "Reject"
   - Action is logged in audit trail

2. **Acknowledging Alerts**:
   - Navigate to "Alerts"
   - Click "Acknowledge" on any alert
   - Alert status updates immediately

3. **Filtering Data**:
   - Most pages include filter options (severity, department, status)
   - Use dropdowns to narrow down views

4. **Refreshing Data**:
   - Click the "🔄 Refresh Data" button in the sidebar
   - Or refresh the browser page

## Data Model

All data is **aggregated only**—no personal information is stored or displayed. The database includes:

- Metrics (counts, averages, percentages)
- Predictions (forecasted values)
- Alerts (system-generated notifications)
- Recommendations (AI-suggested actions)
- Transport requests (location-to-location)
- Inventory (item counts and thresholds)
- Device maintenance (equipment status)
- Discharge planning (department-level aggregates)
- Capacity (bed counts and utilization)
- Audit log (action history)

## Technical Details

- **Framework**: Streamlit 1.28+
- **Database**: SQLite (file-based, no setup required)
- **Visualization**: Plotly Express and Graph Objects
- **Data Processing**: Pandas
- **Python Version**: 3.11+ (recommended: 3.11 as in Dockerfile)
- **Architecture**: Modular structure with separated UI components and pages
- **Language**: All code comments, docstrings, and UI texts are in German

## Customization

### Adding New Metrics

Edit `database.py` to add new metric types or modify the schema. Update the corresponding page module in `ui/pages/` to display new metrics in the UI.

### Modifying Predictions

Adjust prediction logic in `predictions.py` (PredictionEngine class) or utility functions in `utils.py`.

### Styling

Custom CSS is defined in `ui/styling.py`. Modify the `apply_custom_styles()` function to change colors, spacing, or typography.

### Adding New Pages

1. Create a new module in `ui/pages/` (e.g., `new_page.py`)
2. Implement a `render(db, sim, ...)` function
3. Add the page to the `PAGES` dictionary in `app.py`
4. The page will automatically appear in the sidebar navigation

## Limitations

This is an MVP with the following constraints:

- **Sample Data**: Database is seeded with sample data on first run
- **No Real-time Updates**: Data refreshes on page reload or manual refresh
- **Local Only**: SQLite database is file-based (not suitable for multi-user production)
- **No Authentication**: No user authentication or role-based access control
- **Static Predictions**: Predictions are based on simple algorithms (not ML models)

## Future Enhancements

Potential improvements for production:

- Real-time data integration (APIs, message queues)
- Machine learning models for predictions
- User authentication and authorization
- Multi-user support with PostgreSQL
- Email/SMS notifications for critical alerts
- Export functionality (PDF reports, CSV exports)
- Mobile-responsive design improvements

## License

This project is provided as-is for demonstration purposes.

## Support

For issues or questions, please refer to the code comments or Streamlit documentation.

---

**Built with ❤️ for hospital staff**

# Updated Tue Dec 23 15:43:36 CET 2025
