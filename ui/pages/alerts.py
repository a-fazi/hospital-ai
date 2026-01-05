"""
Seitenmodul für Warnungen
"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pandas as pd
import random
import time
from utils import (
    format_time_ago, get_severity_color, get_priority_color, get_risk_color,
    get_status_color, calculate_inventory_status, calculate_capacity_status,
    format_duration_minutes, get_department_color, get_system_status,
    get_metric_severity_for_load, get_metric_severity_for_count, get_metric_severity_for_free,
    get_explanation_score_color
)
from ui.components import render_badge, render_empty_state


def render(db, sim, get_cached_alerts=None, get_cached_recommendations=None, get_cached_capacity=None):
    """Rendert die Warnungen-Seite"""
    # Verwende get_cached_alerts falls verfügbar, sonst direkt aus DB
    alerts = get_cached_alerts() if get_cached_alerts else db.get_active_alerts()
    
    # Debug: Zeige Anzahl der Warnungen (kann später entfernt werden)
    if st.sidebar.checkbox("🔍 Debug-Info anzeigen", key="alerts_debug"):
        st.sidebar.write(f"Anzahl Warnungen: {len(alerts) if alerts else 0}")
        if alerts:
            st.sidebar.json([{"id": a.get('id'), "message": a.get('message'), "severity": a.get('severity')} for a in alerts[:3]])
    
    if alerts:

        # German translation for severity and departments
        from utils import get_department_name_mapping
        severity_de_map = {'high': 'hoch', 'medium': 'mittel', 'low': 'niedrig'}
        severity_en_map = {v: k for k, v in severity_de_map.items()}
        dept_map = get_department_name_mapping()
        # Erweitere für Kompatibilität
        dept_map.update({
            'ED': 'Notaufnahme',
            'General Ward': 'Allgemeinstation',
            'Neurology': 'Neurologie',
            'Pediatrics': 'Pädiatrie',
            'Oncology': 'Onkologie',
            'Maternity': 'Geburtshilfe',
            'Radiology': 'Radiologie',
            'Ward': 'Station',
            'Other': 'Andere',
            'N/A': 'Bereich',
        })
        # Build mapping for all unique departments
        unique_depts = sorted(list(set([a.get('department', 'N/A') for a in alerts if a.get('department')])))
        areas_de = [dept_map.get(d, d) for d in unique_depts]
        area_map = dict(zip(areas_de, unique_depts))
        areas_de_display = ["Alle"] + areas_de
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            severity_options = ["Alle", "hoch", "mittel", "niedrig"]
            selected_severity_de = st.selectbox("Schweregrad", severity_options, key="alert_severity")
        with col2:
            selected_area_de = st.selectbox("Bereich", areas_de_display, key="alert_dept")
            selected_area = None if selected_area_de == "Alle" else area_map[selected_area_de]
        with col3:
            st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
            if st.button("🔄 Zurücksetzen", key="reset_alerts", use_container_width=True, help="Setzt alle Warnungen zurück (nicht mehr bestätigt)"):
                count = db.reset_all_alerts()
                st.success(f"✅ {count} Warnungen zurückgesetzt")
                st.rerun()

        filtered_alerts = alerts
        if selected_severity_de != "Alle":
            selected_severity = severity_en_map[selected_severity_de]
            filtered_alerts = [a for a in filtered_alerts if a['severity'] == selected_severity]
        if selected_area is not None:
            filtered_alerts = [a for a in filtered_alerts if a.get('department') == selected_area]
        
        st.markdown("")  # Abstand
        st.markdown("### Aktive Warnungen")
        st.markdown("")  # Abstand
        
        if not filtered_alerts:
            st.info(f"Keine Warnungen gefunden für die ausgewählten Filter. ({len(alerts)} Warnung(en) insgesamt vorhanden)")
        
        for alert in filtered_alerts:
            # Prüfe ob Warnung bestätigt wurde
            is_acknowledged = alert.get('acknowledged', 0) == 1
            
            # Wenn bestätigt, verwende blaue Farbe, sonst normale Severity-Farbe
            if is_acknowledged:
                border_color = "#2563EB"  # Blau (blue-600) - deutlicher
                background_color = "#DBEAFE"  # Helles Blau für Hintergrund - deutlicher
            else:
                border_color = get_severity_color(alert['severity'])
                background_color = "white"
            
            severity_de = severity_de_map.get(alert['severity'], alert['severity'])
            badge_html = render_badge(severity_de.upper(), alert['severity'])
            
            # Bestätigt-Badge hinzufügen wenn bestätigt
            if is_acknowledged:
                acknowledged_badge = '<span class="badge" style="background: #3B82F6; color: white;">✓ BESTÄTIGT</span>'  # Blau
                badge_html = f"{badge_html} {acknowledged_badge}"
            
            # German translation for alert_type/category
            alert_type_map = {
                'capacity': 'Kapazität',
                'staffing': 'Personal',
                'inventory': 'Inventar',
                'device': 'Gerät',
                'general': 'Allgemein',
                'transport': 'Transport',
                'patient': 'Patient',
                'system': 'System',
                'risk': 'Risiko',
                'other': 'Andere',
            }
            alert_type_de = alert_type_map.get(alert.get('alert_type', 'general'), alert.get('alert_type', 'Allgemein'))
            # Since all alert messages are now in German, just use the message as is
            message_de = alert['message']
            col1, col2 = st.columns([4, 1])
            with col1:
                dept_de = dept_map.get(alert.get('department', 'N/A'), alert.get('department', 'N/A'))
                st.markdown(f"""
                <div style="background: {background_color}; padding: 1.25rem; border-radius: 8px; margin-bottom: 0.75rem; border-left: 4px solid {border_color}; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
                    {badge_html}
                    <strong style="margin-left: 0.5rem; color: #1f2937;">{message_de}</strong>
                    <div style="color: #6b7280; font-size: 0.875rem; margin-top: 0.75rem;">
                        {dept_de} • {alert_type_de} • {format_time_ago(alert['timestamp'])}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
                if is_acknowledged:
                    st.button("✓ Bestätigt", key=f"ack_{alert['id']}", use_container_width=True, disabled=True)
                else:
                    if st.button("Bestätigen", key=f"ack_{alert['id']}", use_container_width=True):
                        db.acknowledge_alert(alert['id'])
                        # Cache invalidieren, damit die Seite aktualisiert wird
                        if 'background_data' in st.session_state:
                            # Aktualisiere die Alerts direkt im Cache
                            updated_alerts = db.get_active_alerts()
                            st.session_state.background_data['alerts'] = updated_alerts
                            st.session_state.background_data['timestamp'] = time.time()
                        # Cache-Timestamp zurücksetzen, damit Background-Daten sofort aktualisiert werden
                        if 'background_data_timestamp' in st.session_state:
                            st.session_state.background_data_timestamp = 0
                        st.rerun()
    else:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-icon">✅</div>
            <div class="empty-state-title">Zurzeit keine kritischen Warnungen</div>
            <div class="empty-state-text">Alle Systeme arbeiten normal</div>
        </div>
        """, unsafe_allow_html=True)

