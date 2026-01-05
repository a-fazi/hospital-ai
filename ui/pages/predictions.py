"""
Seitenmodul für Vorhersagen
"""
import streamlit as st
import plotly.express as px
from datetime import datetime
import pandas as pd
from utils import (
    format_time_ago, get_severity_color, get_priority_color, get_risk_color,
    get_status_color, calculate_inventory_status, calculate_capacity_status,
    format_duration_minutes, get_department_color, get_system_status,
    get_metric_severity_for_load, get_metric_severity_for_count, get_metric_severity_for_free,
    get_explanation_score_color
)
from ui.components import render_badge, render_empty_state


@st.cache_data(ttl=30)
def _get_predictions_cached(_db, time_horizon_minutes):
    """Gecachte Vorhersagen"""
    return _db.get_predictions(time_horizon_minutes)

def format_prediction_value(pred_type: str, value: float) -> tuple[str, str]:
    if pred_type == 'patient_arrival':
        return f"{int(value)}", "neue Patienten erwartet"
    elif pred_type == 'bed_demand':
        return f"{value:.1f}%", "Bettenauslastung"
    else:
        return f"{value:.1f}", ""


def get_prediction_value_color(pred_type: str, value: float) -> str:
    """Bestimmt die Farbe für den Vorhersagewert basierend auf dem Typ und Wert"""
    if pred_type == 'bed_demand':
        # Für Bettenauslastung: >= 90% = rot, >= 75% = gelb, sonst grün
        severity, _ = get_metric_severity_for_load(value)
        return get_severity_color(severity)
    elif pred_type == 'patient_arrival':
        # Für Patientenzugang: >= 8 = rot, >= 5 = gelb, sonst grün
        # Schwellenwerte angepasst an typische Werte (0-12 Patienten pro Zeithorizont)
        thresholds = {'critical': 8, 'watch': 5}
        severity, _ = get_metric_severity_for_count(int(value), thresholds)
        return get_severity_color(severity)
    else:
        return "#1f2937"  # Standard dunkelgrau


def handle_smart_filter(selected: list, previous: list, all_options: list, key: str) -> list:
    """
    Intelligente Filter-Logik für multiselect Filter mit "Alle" Option.
    
    Logik:
    - Wenn leer → ["Alle"]
    - Wenn "Alle" + andere Optionen (und vorher nur "Alle") → entferne "Alle", behalte andere
    - Wenn "Alle" ausgewählt wird (und vorher keine "Alle") → nur ["Alle"]
    - Sonst → behalte selected
    """
    # Wenn leer, setze "Alle"
    if not selected:
        return ["Alle"]
    
    # Wenn "Alle" in selected UND "Alle" war vorher auch ausgewählt UND es gibt andere Optionen
    # → Entferne "Alle", behalte die anderen
    if "Alle" in selected and "Alle" in previous and len(selected) > 1:
        result = [s for s in selected if s != "Alle"]
        # Wenn nach Entfernen leer, behalte zumindest die erste Option
        if not result:
            result = [selected[1]] if len(selected) > 1 else selected
        return result
    
    # Wenn "Alle" in selected UND "Alle" war vorher NICHT ausgewählt
    # → "Alle" ersetzt alles
    if "Alle" in selected and "Alle" not in previous:
        return ["Alle"]
    
    # Sonst behalte selected wie es ist
    return selected


def render(db, sim, get_cached_alerts=None, get_cached_recommendations=None, get_cached_capacity=None):
    """Rendert die Vorhersagen-Seite"""
    st.markdown("### 5-15 Minuten Vorhersagen")
    
    # Hole alle Vorhersagen - verwende Background-Daten für sofortigen Zugriff
    if 'background_data' in st.session_state and st.session_state.background_data:
        all_predictions = st.session_state.background_data.get('predictions', [])
    else:
        all_predictions = _get_predictions_cached(db, 15)  # Fallback: Gecacht
    all_predictions = [p for p in all_predictions if p['prediction_type'] in ['patient_arrival', 'bed_demand'] and 5 <= p['time_horizon_minutes'] <= 15]
    
    predictions = []
    
    if all_predictions:
        # Bereite Daten für Filter vor - verwende zentrales Mapping
        from utils import get_department_name_mapping
        dept_map_base = get_department_name_mapping()
        # Erstelle Reverse-Mapping (Deutsch -> Code) für Filter
        dept_map = {}
        for code, de_name in dept_map_base.items():
            dept_map[de_name] = code
            dept_map[code] = code  # Auch Code selbst als Key
        # Erweitere für Kompatibilität
        dept_map.update({
            'Kardiologie': 'Cardiology',
            'Gastroenterologie': 'Gastroenterology',
            'Akutgeriatrie': 'Geriatrics',
            'Chirurgie': 'Surgery',
            'Intensivstation': 'ICU',
            'Orthopädie': 'Orthopedics',
            'Urologie': 'Urology',
            'Wirbelsäule': 'SpineCenter',
            'HNO': 'ENT',
            'Notaufnahme': 'ER',
            'General Ward': 'General Ward',
            'Neurology': 'Neurology',
            'Pediatrics': 'Pediatrics',
            'Oncology': 'Oncology',
            'Orthopedics': 'Orthopädie',
            'Maternity': 'Geburtshilfe',
            'Radiology': 'Radiologie',
            'Other': 'Andere',
            'N/A': 'N/A'
        })
        
        pred_type_map = {
            'patient_arrival': 'Patientenzugang',
            'bed_demand': 'Bettenbedarf',
        }
        
        # Extrahiere eindeutige Werte für Filter
        unique_departments = sorted(list(set([p.get('department', 'N/A') for p in all_predictions])))
        departments_de = [dept_map.get(d, d) for d in unique_departments]
        department_display_map = dict(zip(departments_de, unique_departments))
        
        unique_types = sorted(list(set([p['prediction_type'] for p in all_predictions])))
        types_de = [pred_type_map.get(t, t.replace('_', ' ').title()) for t in unique_types]
        type_display_map = dict(zip(types_de, unique_types))
        
        unique_times = sorted(list(set([p['time_horizon_minutes'] for p in all_predictions])))
        times_display = [f"{t} Minuten" for t in unique_times]
        time_display_map = dict(zip(times_display, unique_times))
        
        # Session State Initialisierung für Filter
        dept_key = "pred_filter_dept"
        type_key = "pred_filter_type"
        time_key = "pred_filter_time"
        
        if dept_key not in st.session_state:
            st.session_state[dept_key] = ["Alle"]
        if type_key not in st.session_state:
            st.session_state[type_key] = ["Alle"]
        if time_key not in st.session_state:
            st.session_state[time_key] = ["Alle"]
        
        # Initialisiere previous values falls nicht vorhanden
        if f"{dept_key}_prev" not in st.session_state:
            st.session_state[f"{dept_key}_prev"] = st.session_state[dept_key].copy()
        if f"{type_key}_prev" not in st.session_state:
            st.session_state[f"{type_key}_prev"] = st.session_state[type_key].copy()
        if f"{time_key}_prev" not in st.session_state:
            st.session_state[f"{time_key}_prev"] = st.session_state[time_key].copy()
        
        # Filter-Spalten
        col1, col2, col3 = st.columns(3)
        with col1:
            selected_depts_de = st.multiselect(
                "Abteilung",
                options=["Alle"] + departments_de,
                default=st.session_state[dept_key],
                key=dept_key
            )
            # Smart-Filter-Logik anwenden
            previous_depts = st.session_state[f"{dept_key}_prev"]
            processed_depts = handle_smart_filter(
                selected_depts_de, 
                previous_depts, 
                ["Alle"] + departments_de, 
                dept_key
            )
            if processed_depts != selected_depts_de:
                st.session_state[dept_key] = processed_depts
                st.session_state[f"{dept_key}_prev"] = processed_depts.copy()
                st.rerun()
            else:
                st.session_state[f"{dept_key}_prev"] = selected_depts_de.copy()
            selected_depts_de = st.session_state[dept_key]
            
        with col2:
            selected_types_de = st.multiselect(
                "Kategorie",
                options=["Alle"] + types_de,
                default=st.session_state[type_key],
                key=type_key
            )
            # Smart-Filter-Logik anwenden
            previous_types = st.session_state[f"{type_key}_prev"]
            processed_types = handle_smart_filter(
                selected_types_de, 
                previous_types, 
                ["Alle"] + types_de, 
                type_key
            )
            if processed_types != selected_types_de:
                st.session_state[type_key] = processed_types
                st.session_state[f"{type_key}_prev"] = processed_types.copy()
                st.rerun()
            else:
                st.session_state[f"{type_key}_prev"] = selected_types_de.copy()
            selected_types_de = st.session_state[type_key]
            
        with col3:
            selected_times_display = st.multiselect(
                "Zeithorizont",
                options=["Alle"] + times_display,
                default=st.session_state[time_key],
                key=time_key
            )
            # Smart-Filter-Logik anwenden
            previous_times = st.session_state[f"{time_key}_prev"]
            processed_times = handle_smart_filter(
                selected_times_display, 
                previous_times, 
                ["Alle"] + times_display, 
                time_key
            )
            if processed_times != selected_times_display:
                st.session_state[time_key] = processed_times
                st.session_state[f"{time_key}_prev"] = processed_times.copy()
                st.rerun()
            else:
                st.session_state[f"{time_key}_prev"] = selected_times_display.copy()
            selected_times_display = st.session_state[time_key]
        
        st.markdown("")  # Spacing
        
        # Filter anwenden
        predictions = all_predictions.copy()
        
        # Abteilungsfilter
        if "Alle" not in selected_depts_de:
            selected_depts = [department_display_map[d] for d in selected_depts_de]
            predictions = [p for p in predictions if p.get('department', 'N/A') in selected_depts]
        
        # Kategoriefilter
        if "Alle" not in selected_types_de:
            selected_types = [type_display_map[t] for t in selected_types_de]
            predictions = [p for p in predictions if p['prediction_type'] in selected_types]
        
        # Zeitfilter
        if "Alle" not in selected_times_display:
            selected_times = [time_display_map[t] for t in selected_times_display]
            predictions = [p for p in predictions if p['time_horizon_minutes'] in selected_times]
        
        # Sortiere nach Zeithorizont: 5 Minuten zuerst, dann 10, dann 15
        predictions.sort(key=lambda x: x['time_horizon_minutes'])
        
        # Dedupliziere: Nur eine Vorhersage pro Kategorie, Abteilung und Zeit
        # Bevorzuge die erste (mit kürzestem Zeithorizont, bereits sortiert)
        seen = set()
        unique_predictions = []
        for pred in predictions:
            key = (pred['prediction_type'], pred.get('department', 'N/A'), pred['time_horizon_minutes'])
            if key not in seen:
                seen.add(key)
                unique_predictions.append(pred)
        predictions = unique_predictions
    
        capacity_data = get_cached_capacity() if get_cached_capacity else db.get_capacity_overview()
        capacity_by_dept = {c['department']: c for c in capacity_data}
        
        if predictions:
            st.markdown("#### Bevorstehende Vorhersagen")
            for pred in predictions:
                confidence_color = "#10B981" if pred['confidence'] > 0.8 else "#F59E0B" if pred['confidence'] > 0.7 else "#EF4444"
                pred_type_key = pred['prediction_type']
                pred_type = pred_type_map.get(pred_type_key, pred_type_key.replace('_', ' ').title())
                dept = pred.get('department', 'N/A')
                dept_de = dept_map.get(dept, dept)
                minutes = pred['time_horizon_minutes']
                if minutes == 1:
                    time_str = f'in {minutes} Minute'
                else:
                    time_str = f'in {minutes} Minuten'
                
                formatted_value, value_description = format_prediction_value(pred_type_key, pred['predicted_value'])
                value_color = get_prediction_value_color(pred_type_key, pred['predicted_value'])
                
                html_before = f"""<div style="background: white; padding: 1rem; border-radius: 8px; margin-bottom: 0.5rem;">
<div style="display: flex; justify-content: space-between; align-items: flex-start;">
<div style="flex: 1;">
<strong>{pred_type}</strong>
<div style="color: #6b7280; font-size: 0.875rem; margin-top: 0.25rem;">{dept_de} • {time_str}</div>
</div>
<div style="text-align: right; margin-left: 1rem;">
<div style="font-size: 1.5rem; font-weight: 700; color: {value_color};">{formatted_value}</div>
<div style="font-size: 0.75rem; color: #6b7280; margin-top: 0.25rem;">{value_description}</div>
<div style="font-size: 0.75rem; color: {confidence_color}; margin-top: 0.25rem;">{pred['confidence']*100:.0f}% Vertrauen</div>
</div>
</div>
</div>"""
                
                st.markdown(html_before, unsafe_allow_html=True)
            
            st.markdown("### Prognose-Vertrauen nach Zeithorizont")
            
            df = pd.DataFrame(predictions)
            if len(df) > 0:
                df_plot = df.copy()
                df_plot['Vorhersagetyp'] = df_plot['prediction_type'].map(lambda x: pred_type_map.get(x, x.replace('_', ' ').title()))
                fig = px.scatter(
                    df_plot,
                    x='time_horizon_minutes',
                    y='confidence',
                    size='predicted_value',
                    color='Vorhersagetyp',
                    hover_data=['department'],
                    title=""
                )
                fig.update_layout(
                    height=400,
                    xaxis_title="Zeithorizont (Minuten)",
                    yaxis_title="Vertrauen",
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.markdown(render_empty_state("🔮", "Keine Vorhersagen gefunden", "Bitte passen Sie die Filter an, um Vorhersagen anzuzeigen"), unsafe_allow_html=True)
    else:
        st.markdown(render_empty_state("🔮", "Keine Vorhersagen verfügbar", "Vorhersagen werden hier angezeigt, sobald sie verfügbar sind"), unsafe_allow_html=True)
