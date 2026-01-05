"""
Seitenmodul für Dashboard

Das Dashboard ist die Hauptübersichtsseite der Anwendung und zeigt:
- Live-Metriken (ED Load, Betten, Personal, etc.)
- Aktuelle Warnungen und Empfehlungen
- Transport-Übersicht
- Inventar-Status
- Gerätewartungs-Dringlichkeiten
- Aktive Auslastungsereignisse (Surge Events)

Alle Metriken werden aus der Simulation abgerufen und sind korreliert,
um realistische Zusammenhänge zu zeigen.
"""
import streamlit as st
import plotly.express as px
from datetime import datetime, timedelta
import pandas as pd
from utils import (
    format_time_ago, get_severity_color, get_priority_color, get_risk_color,
    get_status_color, calculate_inventory_status, calculate_capacity_status,
    format_duration_minutes, get_department_color, get_system_status,
    get_metric_severity_for_load, get_metric_severity_for_count, get_metric_severity_for_free,
    get_explanation_score_color
)
from ui.components import render_badge, render_empty_state, render_loading_spinner


def _get_simulation_metrics_cached(_sim=None):
    """Gecachte Simulationsmetriken aus session_state"""
    # Verwende gecachte Metriken aus app.py session_state
    if 'cached_sim_metrics' in st.session_state:
        return st.session_state.cached_sim_metrics
    # Fallback
    if _sim:
        return _sim.get_current_metrics()
    return {}

@st.cache_data(ttl=30)
def _get_capacity_from_simulation_cached(_db, _sim_metrics):
    """Gecachte Kapazitätsdaten aus Simulation"""
    return _db.get_capacity_from_simulation(_sim_metrics)

def render(db, sim, get_cached_alerts=None, get_cached_recommendations=None, get_cached_capacity=None):
    """
    Rendert die Dashboard-Seite mit allen wichtigen Metriken und Übersichten.
    
    Das Dashboard aggregiert Daten aus verschiedenen Quellen:
    - Simulation: Live-Metriken (ED Load, Betten, etc.)
    - Datenbank: Warnungen, Empfehlungen, Transporte, Inventar, Geräte
    
    Args:
        db: HospitalDB-Instanz für Datenbankzugriff
        sim: HospitalSimulation-Instanz für Simulationsdaten
        get_cached_alerts: Funktion zum Abrufen gecachter Warnungen
        get_cached_recommendations: Funktion zum Abrufen gecachter Empfehlungen
        get_cached_capacity: Funktion zum Abrufen gecachter Kapazitätsdaten
    """
    # ===== SOFORT: STRUKTUR RENDERN =====
    # Zeige sofort Überschrift und Layout-Struktur
    active_surges = [e for e in sim.active_events if e['type'] == 'surge']
    if active_surges:
        surge = active_surges[0]
        from datetime import timezone
        elapsed = (datetime.now(timezone.utc) - surge['start_time']).total_seconds() / 60
        remaining = max(0, surge['duration_minutes'] - elapsed)
        st.warning(f"⚠️ **Aktives Auslastungsereignis**: Noch {remaining:.0f} Minuten verbleibend (Intensität: {surge['intensity']:.1f})")
        st.markdown("")  # Spacing
    
    # Live Status Section - Überschrift sofort anzeigen
    st.markdown("### Live Status")
    
    # Loading Spinner
    spinner_placeholder = st.empty()
    with spinner_placeholder.container():
        st.markdown(render_loading_spinner("Lade Metriken..."), unsafe_allow_html=True)
    
    # Leere Platzhalter für progressive Anzeige vorbereiten
    metrics_row1_placeholder = st.empty()
    metrics_row2_placeholder = st.empty()
    charts_placeholder = st.empty()
    alerts_placeholder = st.empty()
    recommendations_placeholder = st.empty()
    
    # ===== DATEN ABRUFEN (AUS BACKGROUND-DATEN) =====
    # Verwende Background-Daten aus session_state für sofortigen Zugriff
    # Falls nicht verfügbar, verwende Fallback zu direkten DB-Queries
    if 'background_data' in st.session_state and st.session_state.background_data:
        # Verwende Background-Daten (bereits geladen)
        background_data = st.session_state.background_data
        alerts = background_data.get('alerts', [])
        recommendations = background_data.get('recommendations', [])
        transport = background_data.get('transport', [])
        inventory = background_data.get('inventory', [])
        devices = background_data.get('devices', [])
        predictions = background_data.get('predictions', [])
    else:
        # Fallback: Direkte DB-Queries (sollte nicht passieren, aber sicherheitshalber)
        batch_data = db.get_dashboard_data_batch()
        alerts = batch_data.get('alerts', [])
        recommendations = batch_data.get('recommendations', [])
        transport = batch_data.get('transport', [])
        inventory = batch_data.get('inventory', [])
        devices = batch_data.get('devices', [])
        predictions = batch_data.get('predictions', [])
    
    # ===== SIMULATIONSDATEN ABRUFEN =====
    # Hole aktuelle Simulationsmetriken (alle Metriken sind korreliert)
    sim_metrics = _get_simulation_metrics_cached(sim)  # Gecacht
    
    # Berechne Kapazitätsdaten basierend auf Simulationszustand
    # Dies stellt sicher, dass Kapazitätsdaten konsistent mit Simulationsmetriken sind
    capacity = _get_capacity_from_simulation_cached(db, sim_metrics)  # Gecacht
    
    # ===== METRIKEN BERECHNEN =====
    # Berechne alle Dashboard-Metriken mit entsprechenden Schweregraden
    # ED Load (Notaufnahme-Auslastung) - Hauptindikator für Krankenhausbelastung
    ed_load = sim_metrics['ed_load']
    ed_severity, ed_hint = get_metric_severity_for_load(ed_load)
    
    # Waiting count (from simulation - correlated with ED load)
    waiting_count = int(sim_metrics['waiting_count'])
    waiting_severity, waiting_hint = get_metric_severity_for_count(waiting_count, {'critical': 20, 'watch': 10})
    
    # Beds free (from simulation - konsistent mit Kapazitätsdaten)
    beds_free = int(sim_metrics['beds_free'])
    total_beds = sum([c['total_beds'] for c in capacity]) if capacity else 100
    beds_severity, beds_hint = get_metric_severity_for_free(beds_free, total_beds)
    
    # Staff load (from simulation - correlated with ED load)
    staff_load = sim_metrics['staff_load']
    staff_severity, staff_hint = get_metric_severity_for_load(staff_load)
    
    # Rooms free (from simulation - correlated with beds free)
    rooms_free = int(sim_metrics['rooms_free'])
    total_rooms = db.get_total_rooms()
    rooms_severity, rooms_hint = get_metric_severity_for_free(rooms_free, total_rooms)
    
    # OR load (from simulation)
    or_load = sim_metrics['or_load']
    or_severity, or_hint = get_metric_severity_for_load(or_load)
    
    # Transport queue (from simulation - delayed correlation with ED load)
    transport_queue = int(sim_metrics['transport_queue'])
    transport_severity, transport_hint = get_metric_severity_for_count(transport_queue, {'critical': 8, 'watch': 5})
    
    # Inventar-/Gerätedringlichkeit (Anzahl dringender Artikel)
    low_inventory = len([i for i in inventory if i['current_stock'] < i['min_threshold']])
    high_urgency_devices = len([d for d in devices if d['urgency_level'] in ['high', 'hoch']])
    urgency_count = low_inventory + high_urgency_devices
    urgency_severity, urgency_hint = get_metric_severity_for_count(urgency_count, {'critical': 5, 'watch': 3})
    
    # ===== PROGRESSIV: METRIKEN RENDERN =====
    # Erste Zeile der Metrik-Karten
    with metrics_row1_placeholder.container():
        st.markdown("")  # Abstand
        col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        severity_color = get_severity_color(ed_severity)
        badge_html = render_badge(ed_hint, ed_severity)
        st.markdown(f"""
        <div class="metric-card fade-in" style="border-left-color: {severity_color};">
            <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; margin-bottom: 0.75rem;">Notaufnahme-Auslastung</div>
            <div style="font-size: 2.5rem; font-weight: 700; color: #111827; margin: 0.75rem 0; letter-spacing: -0.02em;">{ed_load:.0f}%</div>
            <div style="margin-top: 1rem;">
                {badge_html}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        severity_color = get_severity_color(waiting_severity)
        badge_html = render_badge(waiting_hint, waiting_severity)
        st.markdown(f"""
        <div class="metric-card fade-in-delayed" style="border-left-color: {severity_color};">
            <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; margin-bottom: 0.75rem;">Wartende Patienten</div>
            <div style="font-size: 2.5rem; font-weight: 700; color: #111827; margin: 0.75rem 0; letter-spacing: -0.02em;">{waiting_count}</div>
            <div style="margin-top: 1rem;">
                {badge_html}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        severity_color = get_severity_color(beds_severity)
        badge_html = render_badge(beds_hint, beds_severity)
        st.markdown(f"""
        <div class="metric-card fade-in-delayed-2" style="border-left-color: {severity_color};">
            <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; margin-bottom: 0.75rem;">Freie Betten</div>
            <div style="font-size: 2.5rem; font-weight: 700; color: #111827; margin: 0.75rem 0; letter-spacing: -0.02em;">{beds_free}</div>
            <div style="margin-top: 1rem;">
                {badge_html}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        severity_color = get_severity_color(staff_severity)
        badge_html = render_badge(staff_hint, staff_severity)
        st.markdown(f"""
        <div class="metric-card fade-in-delayed-3" style="border-left-color: {severity_color};">
            <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; margin-bottom: 0.75rem;">Personal-Auslastung</div>
            <div style="font-size: 2.5rem; font-weight: 700; color: #111827; margin: 0.75rem 0; letter-spacing: -0.02em;">{staff_load:.0f}%</div>
            <div style="margin-top: 1rem;">
                {badge_html}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # Zweite Zeile der Metrik-Karten
    with metrics_row2_placeholder.container():
        col1, col2, col3, col4 = st.columns(4)
    
        with col1:
            severity_color = get_severity_color(rooms_severity)
            badge_html = render_badge(rooms_hint, rooms_severity)
            st.markdown(f"""
            <div class="metric-card fade-in" style="border-left-color: {severity_color};">
                <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; margin-bottom: 0.75rem;">Freie Räume</div>
                <div style="font-size: 2.5rem; font-weight: 700; color: #111827; margin: 0.75rem 0; letter-spacing: -0.02em;">{rooms_free}</div>
                <div style="margin-top: 1rem;">
                    {badge_html}
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            severity_color = get_severity_color(or_severity)
            badge_html = render_badge(or_hint, or_severity)
            st.markdown(f"""
            <div class="metric-card fade-in-delayed" style="border-left-color: {severity_color};">
                <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; margin-bottom: 0.75rem;">OP-Auslastung</div>
                <div style="font-size: 2.5rem; font-weight: 700; color: #111827; margin: 0.75rem 0; letter-spacing: -0.02em;">{or_load:.0f}%</div>
                <div style="margin-top: 1rem;">
                    {badge_html}
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            severity_color = get_severity_color(transport_severity)
            badge_html = render_badge(transport_hint, transport_severity)
            st.markdown(f"""
            <div class="metric-card fade-in-delayed-2" style="border-left-color: {severity_color};">
                <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; margin-bottom: 0.75rem;">Transport-Warteschlange</div>
                <div style="font-size: 2.5rem; font-weight: 700; color: #111827; margin: 0.75rem 0; letter-spacing: -0.02em;">{transport_queue}</div>
                <div style="margin-top: 1rem;">
                    {badge_html}
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            severity_color = get_severity_color(urgency_severity)
            badge_html = render_badge(urgency_hint, urgency_severity)
            st.markdown(f"""
            <div class="metric-card fade-in-delayed-3" style="border-left-color: {severity_color};">
                <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; margin-bottom: 0.75rem;">Bestands-/Gerätedringlichkeit</div>
                <div style="font-size: 2.5rem; font-weight: 700; color: #111827; margin: 0.75rem 0; letter-spacing: -0.02em;">{urgency_count}</div>
                <div style="margin-top: 1rem;">
                    {badge_html}
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    # Spinner entfernen
    spinner_placeholder.empty()
    
    st.markdown("---")
    
    # ===== PROGRESSIV: DIAGRAMME UND AUSBLICK =====
    with charts_placeholder.container():
        # Diagramme und Ausblick-Panel
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Diagramm-Abschnitt
            st.markdown("### Trends (Letzte 60 Minuten)")
            st.markdown("")  # Spacing
        
            # Historische Daten aus Simulation abrufen
            waiting_history = sim.get_metric_history('waiting_count', 60)
            ed_history = sim.get_metric_history('ed_load', 60)
            
            # In DataFrames konvertieren
            df_waiting = pd.DataFrame(waiting_history)
            df_waiting['timestamp'] = pd.to_datetime(df_waiting['timestamp']).dt.floor('S')
            # Aggregiere auf 30-Sekunden-Intervalle
            from utils import aggregate_to_30_seconds
            df_waiting = aggregate_to_30_seconds(df_waiting, timestamp_col='timestamp', value_col='value', agg_func='mean')
            
            df_ed = pd.DataFrame(ed_history)
            df_ed['timestamp'] = pd.to_datetime(df_ed['timestamp']).dt.floor('S')
            # Aggregiere auf 30-Sekunden-Intervalle
            df_ed = aggregate_to_30_seconds(df_ed, timestamp_col='timestamp', value_col='value', agg_func='mean')
            
            # Aktuelle Werte für Annotationen
            current_waiting = waiting_count
            current_ed_load = ed_load
            
            # Warteschlangen-Diagramm
            fig_waiting = px.line(
                df_waiting,
                x='timestamp',
                y='value',
                title="Wartende Anzahl",
                labels={'value': 'Anzahl', 'timestamp': ''}
            )
            # Füge aktuellen Wert als letzten Punkt hinzu (falls nicht bereits enthalten)
            if not df_waiting.empty:
                last_timestamp = df_waiting['timestamp'].max()
                current_time = pd.Timestamp.now(tz=last_timestamp.tz if hasattr(last_timestamp, 'tz') else None)
                # Füge aktuellen Wert hinzu, wenn er sich vom letzten unterscheidet oder zu weit in der Zukunft ist
                if (current_time - last_timestamp).total_seconds() > 30 or abs(df_waiting.iloc[-1]['value'] - current_waiting) > 0.5:
                    fig_waiting.add_scatter(
                        x=[current_time],
                        y=[current_waiting],
                        mode='markers',
                        marker=dict(size=8, color='#667eea', symbol='circle'),
                        name='Aktuell',
                        showlegend=False
                    )
            fig_waiting.update_layout(
                height=250,
                margin=dict(l=40, r=20, t=40, b=20),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False, showline=False),
                yaxis=dict(showgrid=True, gridcolor='#e5e7eb', showline=False, title=''),
                showlegend=False,
                font=dict(size=11)
            )
            fig_waiting.update_traces(line_color='#667eea', line_width=2.5, marker=dict(size=4))
            st.plotly_chart(fig_waiting, use_container_width=True)
            
            st.markdown("")  # Spacing
            
            # Notaufnahme-Auslastungs-Diagramm
            fig_ed = px.line(
                df_ed,
                x='timestamp',
                y='value',
                title="Notaufnahme-Auslastung",
                labels={'value': 'Auslastung %', 'timestamp': ''}
            )
            # Füge aktuellen Wert als letzten Punkt hinzu (falls nicht bereits enthalten)
            if not df_ed.empty:
                last_timestamp = df_ed['timestamp'].max()
                current_time = pd.Timestamp.now(tz=last_timestamp.tz if hasattr(last_timestamp, 'tz') else None)
                # Füge aktuellen Wert hinzu, wenn er sich vom letzten unterscheidet oder zu weit in der Zukunft ist
                if (current_time - last_timestamp).total_seconds() > 30 or abs(df_ed.iloc[-1]['value'] - current_ed_load) > 0.5:
                    fig_ed.add_scatter(
                        x=[current_time],
                        y=[current_ed_load],
                        mode='markers',
                        marker=dict(size=8, color='#DC2626', symbol='circle'),
                        name='Aktuell',
                        showlegend=False
                    )
            fig_ed.update_layout(
                height=250,
                margin=dict(l=40, r=20, t=40, b=20),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False, showline=False),
                yaxis=dict(showgrid=True, gridcolor='#e5e7eb', showline=False, range=[0, 100], title=''),
                showlegend=False,
                font=dict(size=11)
            )
            fig_ed.update_traces(line_color='#DC2626', line_width=2.5, marker=dict(size=4))
            st.plotly_chart(fig_ed, use_container_width=True)
        
        with col2:
            # Ausblick-Panel für nächste 15 Minuten
            st.markdown("### Ausblick: Nächste 15 Minuten")
            st.markdown("")  # Spacing
        
            # Top 3 vorhergesagte Engpässe abrufen
            bottleneck_predictions = []
            for pred in predictions:
                if pred['time_horizon_minutes'] <= 15:
                    bottleneck_predictions.append(pred)
            
            # Nach vorhergesagtem Wert sortieren (absteigend) und Top 3 nehmen
            bottleneck_predictions.sort(key=lambda x: x['predicted_value'], reverse=True)
            top_bottlenecks = bottleneck_predictions[:3]
            
            # German translation for prediction types
            pred_type_map = {
                'patient_arrival': 'Patientenzugang',
                'bed_demand': 'Bettenbedarf',
                'resource_needed': 'Ressourcenbedarf',
                'waiting_count': 'Wartende Patienten',
                'ed_load': 'Notaufnahme-Auslastung',
                'or_load': 'OP-Auslastung',
                'staff_load': 'Personal-Auslastung',
                'transport_queue': 'Transport-Warteschlange',
                'rooms_free': 'Freie Räume',
                'beds_free': 'Freie Betten',
                # Bei Bedarf weitere hinzufügen
            }
            if top_bottlenecks:
                for i, bottleneck in enumerate(top_bottlenecks, 1):
                    pred_type_key = bottleneck['prediction_type']
                    pred_type = pred_type_map.get(pred_type_key, pred_type_key.replace('_', ' ').title())
                    pred_value = bottleneck['predicted_value']
                    pred_minutes = bottleneck['time_horizon_minutes']
                    dept = bottleneck.get('department', 'N/A')
                    # German translation for department names - verwende zentrales Mapping
                    from utils import get_department_name_mapping
                    dept_map = get_department_name_mapping()
                    dept_map.update({
                        'General Ward': 'Allgemeinstation',
                        'Neurology': 'Neurologie',
                        'Pediatrics': 'Pädiatrie',
                        'Oncology': 'Onkologie',
                        'Maternity': 'Geburtshilfe',
                        'Radiology': 'Radiologie',
                        'Other': 'Andere'
                    })
                    dept_de = dept_map.get(dept, dept)
                    # German time string
                    if pred_minutes == 1:
                        time_str = f'in {pred_minutes} Minute'
                    else:
                        time_str = f'in {pred_minutes} Minuten'
                    st.markdown(f"""
                    <div class="fade-in" style="background: white; padding: 1rem; border-radius: 8px; margin-bottom: 0.75rem; border-left: 3px solid #667eea; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
                        <div style="font-size: 0.875rem; font-weight: 600; color: #1f2937; margin-bottom: 0.25rem;">
                            {i}. {pred_type}
                        </div>
                        <div style="font-size: 1.25rem; font-weight: 700; color: #667eea; margin: 0.25rem 0;">
                            {pred_value:.0f}
                        </div>
                        <div style="font-size: 0.75rem; color: #6b7280; margin-top: 0.5rem;">
                            {dept_de} • {time_str}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown(render_empty_state("📊", "Keine vorhergesagten Engpässe", "System arbeitet im normalen Bereich"), unsafe_allow_html=True)
    
    st.markdown("---")
    
    # ===== PROGRESSIV: WARNUNGEN UND EMPFEHLUNGEN =====
    with alerts_placeholder.container():
        # Kürzliche Warnungen
        st.markdown("### Kürzliche Warnungen")
        st.markdown("")  # Abstand
        if alerts:
            severity_de_map = {'high': 'hoch', 'medium': 'mittel', 'low': 'niedrig'}
            for i, alert in enumerate(alerts[:5]):
                # Prüfe ob Warnung bestätigt wurde
                is_acknowledged = alert.get('acknowledged', 0) == 1
                
                # Wenn bestätigt, verwende blaue Farbe, sonst normale Severity-Farbe
                if is_acknowledged:
                    border_color = "#3B82F6"  # Blau (blue-500)
                    background_color = "#EFF6FF"  # Sehr helles Blau für Hintergrund
                else:
                    border_color = get_severity_color(alert['severity'])
                    background_color = "white"
                
                severity_de = severity_de_map.get(alert['severity'], alert['severity'])
                badge_html = render_badge(severity_de.upper(), alert['severity'])
                
                # Bestätigt-Badge hinzufügen wenn bestätigt
                if is_acknowledged:
                    acknowledged_badge = '<span class="badge" style="background: #3B82F6; color: white;">✓ BESTÄTIGT</span>'  # Blau
                    badge_html = f"{badge_html} {acknowledged_badge}"
                
                delay_class = "fade-in" if i == 0 else f"fade-in-delayed-{min(i, 3)}" if i <= 3 else "fade-in-delayed-3"
                st.markdown(f"""
                <div class="info-card {delay_class}" style="background: {background_color}; border-left: 4px solid {border_color};">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="flex: 1;">
                            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem;">
                                {badge_html}
                                <strong style="color: #111827; font-size: 0.9375rem; font-weight: 600;">{alert['message']}</strong>
                            </div>
                            <div style="color: #6b7280; font-size: 0.8125rem; font-weight: 500;">
                                {alert.get('department', 'N/A')} • {format_time_ago(alert['timestamp'])}
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Keine aktiven Warnungen")
    
    with recommendations_placeholder.container():
        # Ausstehende Empfehlungen
        st.markdown("### Ausstehende Empfehlungen")
        st.markdown("")  # Abstand
        if recommendations:
            priority_de_map = {'high': 'hoch', 'medium': 'mittel', 'low': 'niedrig'}
            for i, rec in enumerate(recommendations[:3]):
                priority_color = get_priority_color(rec['priority'])
                priority_de = priority_de_map.get(rec['priority'], rec['priority'])
                badge_html = render_badge(priority_de.upper(), rec['priority'])
                delay_class = "fade-in" if i == 0 else f"fade-in-delayed-{min(i, 3)}" if i <= 3 else "fade-in-delayed-3"
                st.markdown(f"""
                <div class="info-card {delay_class}" style="border-left: 4px solid {priority_color};">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div style="flex: 1;">
                            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem;">
                                {badge_html}
                                <strong style="color: #111827; font-size: 1rem; font-weight: 600;">{rec['title']}</strong>
                            </div>
                            <p style="color: #4b5563; margin-top: 0.5rem; margin-bottom: 0; line-height: 1.7; font-size: 0.9375rem;">{rec['description']}</p>
                            <div style="color: #9ca3af; font-size: 0.75rem; margin-top: 1rem; font-weight: 500;">
                                {rec.get('department', 'N/A')} • {format_time_ago(rec['timestamp'])}
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown(render_empty_state("✅", "Keine ausstehenden Empfehlungen", "Alle Empfehlungen wurden überprüft"), unsafe_allow_html=True)
