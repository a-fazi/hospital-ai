"""
Seitenmodul für Live-Metriken - Umfassende Datenübersicht
"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
import pandas as pd
import io
import json
from utils import (
    format_time_ago, get_severity_color, get_priority_color, get_risk_color,
    get_status_color, calculate_inventory_status, calculate_capacity_status,
    format_duration_minutes, get_department_color, get_system_status,
    get_metric_severity_for_load, get_metric_severity_for_count, get_metric_severity_for_free,
    get_explanation_score_color, get_department_name_mapping, get_department_display_name,
    convert_utc_to_local
)
from ui.components import render_badge, render_empty_state, render_loading_spinner


# Deutsche Übersetzungen - verwende zentrales Mapping aus utils
DEPT_MAP = get_department_name_mapping()
# Erweitere für Kompatibilität mit alten Bezeichnungen
DEPT_MAP.update({
    'General Ward': 'Allgemeinstation',
    'Neurology': 'Neurologie',
    'Pediatrics': 'Pädiatrie',
    'Oncology': 'Onkologie',
    'Maternity': 'Geburtshilfe',
    'Radiology': 'Radiologie',
    'Other': 'Andere',
    'N/A': 'N/A',
})

METRIC_TYPE_MAP = {
    'patient_count': 'Patientenzahl',
    'wait_time': 'Wartezeit',
    'occupancy': 'Auslastung',
    'throughput': 'Durchsatz',
    'waiting_count': 'Wartende Patienten',
    'ed_load': 'Notaufnahme-Auslastung',
    'or_load': 'OP-Auslastung',
    'staff_load': 'Personal-Auslastung',
    'transport_queue': 'Transport-Warteschlange',
    'rooms_free': 'Freie Räume',
    'beds_free': 'Freie Betten',
}

SEVERITY_MAP = {
    'high': 'hoch',
    'medium': 'mittel',
    'low': 'niedrig',
    'hoch': 'hoch',
    'mittel': 'mittel',
    'niedrig': 'niedrig',
}

STATUS_MAP = {
    'pending': 'ausstehend',
    'in_progress': 'in Bearbeitung',
    'completed': 'abgeschlossen',
    'accepted': 'akzeptiert',
    'rejected': 'abgelehnt',
    'resolved': 'gelöst',
    'acknowledged': 'bestätigt',
}


def get_time_range_minutes(time_range: str) -> int:
    """Konvertiere Zeitraum-String zu Minuten"""
    time_ranges = {
        '1h': 60,
        '6h': 360,
        '24h': 1440,
        '7d': 10080,
        '30d': 43200,
        'all': None,
    }
    return time_ranges.get(time_range, 10080)  # Default: 7 Tage


def filter_dataframe(df: pd.DataFrame, search_text: str = "", departments: list = None, 
                     min_value: float = None, max_value: float = None) -> pd.DataFrame:
    """Filtere DataFrame basierend auf verschiedenen Kriterien"""
    if df.empty:
        return df
    
    filtered = df.copy()
    
    # Textsuche
    if search_text:
        text_cols = filtered.select_dtypes(include=['object']).columns
        mask = pd.Series([False] * len(filtered))
        for col in text_cols:
            mask |= filtered[col].astype(str).str.contains(search_text, case=False, na=False)
        filtered = filtered[mask]
    
    # Abteilung
    if departments and 'department' in filtered.columns:
        filtered = filtered[filtered['department'].isin(departments)]
    
    # Wertebereich
    numeric_cols = filtered.select_dtypes(include=['number']).columns
    if min_value is not None and len(numeric_cols) > 0:
        # Filtere auf erste numerische Spalte
        filtered = filtered[filtered[numeric_cols[0]] >= min_value]
    if max_value is not None and len(numeric_cols) > 0:
        filtered = filtered[filtered[numeric_cols[0]] <= max_value]
    
    return filtered


def export_to_csv(df: pd.DataFrame, filename_prefix: str = "export") -> bytes:
    """Exportiere DataFrame zu CSV"""
    output = io.StringIO()
    df.to_csv(output, index=False, encoding='utf-8')
    return output.getvalue().encode('utf-8')


def prepare_export_df(df: pd.DataFrame, required_cols: list, default_values: dict = None) -> pd.DataFrame:
    """Bereitet DataFrame für Export vor, fügt fehlende Spalten mit Standardwerten hinzu"""
    export_df = df.copy()
    if default_values is None:
        default_values = {}
    
    for col in required_cols:
        if col not in export_df.columns:
            # Use provided default or infer from column name
            if col in default_values:
                export_df[col] = default_values[col]
            elif col in ['timestamp']:
                export_df[col] = pd.Timestamp.now()
            elif any(x in col.lower() for x in ['name', 'title', 'type', 'category', 'department', 'unit', 'location', 'status', 'priority', 'id']):
                export_df[col] = ''
            elif any(x in col.lower() for x in ['count', 'stock', 'threshold', 'capacity', 'value', 'minutes', 'level']):
                export_df[col] = 0
            else:
                export_df[col] = ''
    
    return export_df[required_cols]


def render_metrics_section(df: pd.DataFrame, time_range_minutes: int, search_text: str, 
                           selected_departments: list, min_value: float, max_value: float):
    """Rendert Metriken-Sektion"""
    st.markdown("### Metriken")
    
    if df.empty:
        st.info("Keine Metriken verfügbar")
        return
    
    # Filter anwenden
    filtered_df = filter_dataframe(df, search_text, selected_departments, min_value, max_value)
    
    if filtered_df.empty:
        st.warning("Keine Metriken entsprechen den Filtern")
        return
    
    # Übersichtskarten
    metric_types = filtered_df['metric_type'].unique()
    cols = st.columns(min(4, len(metric_types)))
    
    for idx, metric_type in enumerate(metric_types[:4]):
        col_idx = idx % 4
        with cols[col_idx]:
            latest = filtered_df[filtered_df['metric_type'] == metric_type].iloc[-1]
            label = METRIC_TYPE_MAP.get(metric_type, metric_type.replace('_', ' ').title())
            
            if metric_type in ['patient_count', 'waiting_count']:
                value_str = f"{int(round(latest['value']))}"
            elif metric_type in ['occupancy', 'ed_load', 'or_load', 'staff_load']:
                value_str = f"{latest['value']:.1f}%"
            elif metric_type == 'wait_time':
                value_str = f"{latest['value']:.1f} Min."
            elif metric_type == 'throughput':
                value_str = f"{latest['value']:.1f}/h"
            else:
                unit = latest.get('unit', '')
                value_str = f"{latest['value']:.1f} {unit}" if unit else f"{latest['value']:.1f}"
            
            st.metric(label, value_str)
    
    st.markdown("---")
    
    # Tabelle
    st.markdown("#### Metriken-Tabelle")
    display_df = filtered_df.copy()
    # Convert to datetime safely - handle different formats
    if 'timestamp' in display_df.columns and not display_df.empty:
        try:
            dt_series = pd.to_datetime(display_df['timestamp'], errors='coerce', infer_datetime_format=True)
            # Only use .dt if it's actually a datetime type
            if pd.api.types.is_datetime64_any_dtype(dt_series):
                # Konvertiere UTC zu lokaler Zeit für Anzeige
                # Verwende apply um convert_utc_to_local auf jeden Wert anzuwenden
                display_df['Zeitstempel'] = dt_series.apply(lambda x: convert_utc_to_local(x).strftime('%Y-%m-%d %H:%M:%S') if convert_utc_to_local(x) else str(x))
            else:
                # Fallback: convert to string as-is
                display_df['Zeitstempel'] = display_df['timestamp'].astype(str)
        except Exception:
            # Fallback: use timestamp as string
            display_df['Zeitstempel'] = display_df['timestamp'].astype(str) if 'timestamp' in display_df.columns else ''
    else:
        display_df['Zeitstempel'] = ''
    display_df['Typ'] = display_df['metric_type'].map(lambda x: METRIC_TYPE_MAP.get(x, x))
    display_df['Wert'] = display_df['value'].round(2)
    display_df['Einheit'] = display_df.get('unit', '')
    display_df['Abteilung'] = display_df.get('department', '').map(lambda x: DEPT_MAP.get(x, x) if pd.notna(x) else '')
    
    table_cols = ['Zeitstempel', 'Typ', 'Wert', 'Einheit', 'Abteilung']
    st.dataframe(display_df[table_cols], use_container_width=True, hide_index=True)
    
    # Export
    col1, col2 = st.columns([1, 4])
    with col1:
        # Fix: Use helper function to safely prepare export DataFrame
        required_cols = ['timestamp', 'metric_type', 'value', 'unit', 'department']
        export_df = prepare_export_df(filtered_df, required_cols)
        csv_data = export_to_csv(export_df, "metrics")
        st.download_button(
            "📥 CSV Export",
            csv_data,
            f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv"
        )
    
    st.markdown("---")
    
    # Diagramm
    st.markdown("#### Metrik-Trends")
    metric_type_labels = [METRIC_TYPE_MAP.get(mt, mt.replace('_', ' ').title()) for mt in metric_types]
    selected_label = st.selectbox("Metrik-Typ auswählen", metric_type_labels, key="metric_chart_select")
    selected_metric = [k for k, v in METRIC_TYPE_MAP.items() if v == selected_label][0] if selected_label in metric_type_labels else metric_types[0]
    
    metric_data = filtered_df[filtered_df['metric_type'] == selected_metric].sort_values('timestamp')
    if not metric_data.empty:
        metric_data = metric_data.copy()
        # Runde Timestamps auf Sekunden (entferne Millisekunden)
        if 'timestamp' in metric_data.columns:
            metric_data['timestamp'] = pd.to_datetime(metric_data['timestamp']).dt.floor('S')
        if 'department' in metric_data.columns:
            metric_data['Abteilung'] = metric_data['department'].map(lambda d: DEPT_MAP.get(d, d) if pd.notna(d) else '')
            color_col = 'Abteilung'
        else:
            color_col = None
        
        # Aggregiere auf 30-Sekunden-Intervalle
        from utils import aggregate_to_30_seconds
        # Wenn color_col vorhanden ist, müssen wir nach beiden gruppieren
        if color_col and color_col in metric_data.columns:
            # Aggregiere für jede Abteilung separat
            metric_data_list = []
            for dept in metric_data[color_col].unique():
                dept_data = metric_data[metric_data[color_col] == dept].copy()
                if not dept_data.empty:
                    dept_agg = aggregate_to_30_seconds(dept_data, timestamp_col='timestamp', value_col='value', agg_func='mean')
                    metric_data_list.append(dept_agg)
            if metric_data_list:
                metric_data = pd.concat(metric_data_list, ignore_index=True)
            else:
                metric_data = aggregate_to_30_seconds(metric_data, timestamp_col='timestamp', value_col='value', agg_func='mean')
        else:
            metric_data = aggregate_to_30_seconds(metric_data, timestamp_col='timestamp', value_col='value', agg_func='mean')
        
        fig = px.line(
            metric_data,
            x='timestamp',
            y='value',
            color=color_col if color_col and metric_data[color_col].nunique() > 1 else None,
            title=f"{METRIC_TYPE_MAP.get(selected_metric, selected_metric)} Verlauf",
            markers=True
        )
        fig.update_layout(
            height=400,
            xaxis_title="Zeit",
            yaxis_title="Wert",
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig, use_container_width=True)


def render_alerts_section(df: pd.DataFrame, search_text: str, selected_departments: list, 
                         selected_severities: list):
    """Rendert Alerts-Sektion"""
    st.markdown("### Warnungen/Alerts")
    
    if df.empty:
        st.info("Keine Warnungen verfügbar")
        return
    
    # Filter nach Schweregrad
    if selected_severities and 'severity' in df.columns:
        df = df[df['severity'].isin(selected_severities)]
    
    # Weitere Filter
    filtered_df = filter_dataframe(df, search_text, selected_departments)
    
    if filtered_df.empty:
        st.warning("Keine Warnungen entsprechen den Filtern")
        return
    
    # Kritische Alerts als Karten
    critical_alerts = filtered_df[filtered_df['severity'].isin(['high', 'hoch', 'critical', 'kritisch'])]
    if not critical_alerts.empty:
        st.markdown("#### Kritische Warnungen")
        for _, alert in critical_alerts.head(5).iterrows():
            # Prüfe ob Warnung bestätigt wurde
            is_acknowledged = alert.get('acknowledged', 0) == 1 if 'acknowledged' in alert else False
            if isinstance(is_acknowledged, (int, float)):
                is_acknowledged = is_acknowledged == 1
            
            # Wenn bestätigt, verwende blaue Farbe, sonst normale Severity-Farbe
            if is_acknowledged:
                border_color = "#3B82F6"  # Blau (blue-500)
                background_color = "#EFF6FF"  # Sehr helles Blau für Hintergrund
            else:
                border_color = get_severity_color(alert['severity'])
                background_color = "white"
            
            severity_de = SEVERITY_MAP.get(alert['severity'], alert['severity'])
            badge_html = render_badge(severity_de.upper(), alert['severity'])
            
            # Bestätigt-Badge hinzufügen wenn bestätigt
            if is_acknowledged:
                acknowledged_badge = '<span class="badge" style="background: #3B82F6; color: white;">✓ BESTÄTIGT</span>'  # Blau
                badge_html = f"{badge_html} {acknowledged_badge}"
            
            dept = DEPT_MAP.get(alert.get('department', 'N/A'), alert.get('department', 'N/A'))
            
            st.markdown(f"""
            <div style="background: {background_color}; padding: 1rem; border-radius: 8px; margin-bottom: 0.75rem; 
                        border-left: 4px solid {border_color}; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
                {badge_html}
                <strong style="margin-left: 0.5rem; color: #1f2937;">{alert['message']}</strong>
                <div style="color: #6b7280; font-size: 0.875rem; margin-top: 0.5rem;">
                    {dept} • {format_time_ago(alert['timestamp'])}
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Tabelle
    st.markdown("#### Alerts-Tabelle")
    display_df = filtered_df.copy()
    # Convert to datetime safely
    if 'timestamp' in display_df.columns and not display_df.empty:
        try:
            dt_series = pd.to_datetime(display_df['timestamp'], errors='coerce', infer_datetime_format=True)
            if pd.api.types.is_datetime64_any_dtype(dt_series):
                # Konvertiere UTC zu lokaler Zeit für Anzeige
                display_df['Zeitstempel'] = dt_series.apply(lambda x: convert_utc_to_local(x).strftime('%Y-%m-%d %H:%M:%S') if convert_utc_to_local(x) else str(x))
            else:
                display_df['Zeitstempel'] = display_df['timestamp'].astype(str)
        except Exception:
            display_df['Zeitstempel'] = display_df['timestamp'].astype(str) if 'timestamp' in display_df.columns else ''
    else:
        display_df['Zeitstempel'] = ''
    
    # Fix: Use column access with fallback to Series instead of .get() which returns scalar
    display_df['Typ'] = display_df['alert_type'] if 'alert_type' in display_df.columns else pd.Series([''] * len(display_df), index=display_df.index)
    display_df['Schweregrad'] = display_df['severity'].map(lambda x: SEVERITY_MAP.get(x, x))
    display_df['Nachricht'] = display_df['message']
    
    # Fix: Use column access with fallback to Series instead of .get() which returns scalar
    dept_series = display_df['department'] if 'department' in display_df.columns else pd.Series([''] * len(display_df), index=display_df.index)
    display_df['Abteilung'] = dept_series.map(lambda x: DEPT_MAP.get(x, x) if pd.notna(x) else '')
    
    # Fix: Use column access with fallback to Series instead of .get() which returns scalar
    resolved_series = display_df['resolved'] if 'resolved' in display_df.columns else pd.Series([0] * len(display_df), index=display_df.index)
    display_df['Status'] = resolved_series.map(lambda x: 'Gelöst' if x else 'Aktiv')
    
    table_cols = ['Zeitstempel', 'Typ', 'Schweregrad', 'Nachricht', 'Abteilung', 'Status']
    st.dataframe(display_df[table_cols], use_container_width=True, hide_index=True)
    
    # Export
    col1, col2 = st.columns([1, 4])
    with col1:
        # Fix: Use helper function to safely prepare export DataFrame
        required_cols = ['timestamp', 'alert_type', 'severity', 'message', 'department', 'resolved']
        default_values = {'resolved': 0, 'severity': 'medium'}
        export_df = prepare_export_df(filtered_df, required_cols, default_values)
        csv_data = export_to_csv(export_df, "alerts")
        st.download_button(
            "📥 CSV Export",
            csv_data,
            f"alerts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv"
        )


def render_predictions_section(df: pd.DataFrame, search_text: str, selected_departments: list):
    """Rendert Vorhersagen-Sektion"""
    st.markdown("### Vorhersagen")
    
    if df.empty:
        st.info("Keine Vorhersagen verfügbar")
        return
    
    filtered_df = filter_dataframe(df, search_text, selected_departments)
    
    if filtered_df.empty:
        st.warning("Keine Vorhersagen entsprechen den Filtern")
        return
    
    # Tabelle
    st.markdown("#### Vorhersagen-Tabelle")
    display_df = filtered_df.copy()
    # Convert to datetime safely
    if 'timestamp' in display_df.columns and not display_df.empty:
        try:
            dt_series = pd.to_datetime(display_df['timestamp'], errors='coerce', infer_datetime_format=True)
            if pd.api.types.is_datetime64_any_dtype(dt_series):
                # Konvertiere UTC zu lokaler Zeit für Anzeige
                display_df['Zeitstempel'] = dt_series.apply(lambda x: convert_utc_to_local(x).strftime('%Y-%m-%d %H:%M:%S') if convert_utc_to_local(x) else str(x))
            else:
                display_df['Zeitstempel'] = display_df['timestamp'].astype(str)
        except Exception:
            display_df['Zeitstempel'] = display_df['timestamp'].astype(str) if 'timestamp' in display_df.columns else ''
    else:
        display_df['Zeitstempel'] = ''
    display_df['Typ'] = display_df.get('prediction_type', '').map(lambda x: METRIC_TYPE_MAP.get(x, x))
    display_df['Vorhergesagter Wert'] = display_df['predicted_value'].round(2)
    display_df['Konfidenz'] = (display_df.get('confidence', 0) * 100).round(1).astype(str) + '%'
    display_df['Zeithorizont'] = display_df.get('time_horizon_minutes', 0).astype(str) + ' Min.'
    display_df['Abteilung'] = display_df.get('department', '').map(lambda x: DEPT_MAP.get(x, x) if pd.notna(x) else '')
    
    table_cols = ['Zeitstempel', 'Typ', 'Vorhergesagter Wert', 'Konfidenz', 'Zeithorizont', 'Abteilung']
    st.dataframe(display_df[table_cols], use_container_width=True, hide_index=True)
    
    # Visualisierung
    if not filtered_df.empty:
        st.markdown("#### Vorhersagen nach Zeithorizont")
        fig = px.bar(
            filtered_df,
            x='time_horizon_minutes',
            y='predicted_value',
            color='prediction_type',
            title="Vorhergesagte Werte nach Zeithorizont",
            labels={'time_horizon_minutes': 'Zeithorizont (Minuten)', 'predicted_value': 'Vorhergesagter Wert'}
        )
        fig.update_layout(height=400, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)
    
    # Export
    col1, col2 = st.columns([1, 4])
    with col1:
        # Fix: Use helper function to safely prepare export DataFrame
        required_cols = ['timestamp', 'prediction_type', 'predicted_value', 'confidence', 'time_horizon_minutes', 'department']
        export_df = prepare_export_df(filtered_df, required_cols)
        csv_data = export_to_csv(export_df, "predictions")
        st.download_button(
            "📥 CSV Export",
            csv_data,
            f"predictions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv"
        )


def render_recommendations_section(df: pd.DataFrame, search_text: str, selected_departments: list, 
                                  selected_statuses: list):
    """Rendert Empfehlungen-Sektion"""
    st.markdown("### Empfehlungen")
    
    if df.empty:
        st.info("Keine Empfehlungen verfügbar")
        return
    
    # Filter nach Status
    if selected_statuses and 'status' in df.columns:
        df = df[df['status'].isin(selected_statuses)]
    
    filtered_df = filter_dataframe(df, search_text, selected_departments)
    
    if filtered_df.empty:
        st.warning("Keine Empfehlungen entsprechen den Filtern")
        return
    
    # Hohe Priorität als Karten
    high_priority = filtered_df[filtered_df['priority'].isin(['high', 'hoch'])]
    if not high_priority.empty:
        st.markdown("#### Hohe Priorität")
        for _, rec in high_priority.head(3).iterrows():
            priority_color = get_priority_color(rec['priority'])
            priority_de = SEVERITY_MAP.get(rec['priority'], rec['priority'])
            badge_html = render_badge(priority_de.upper(), rec['priority'])
            dept = DEPT_MAP.get(rec.get('department', 'N/A'), rec.get('department', 'N/A'))
            
            st.markdown(f"""
            <div style="background: white; padding: 1rem; border-radius: 8px; margin-bottom: 0.75rem; 
                        border-left: 4px solid {priority_color}; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
                {badge_html}
                <strong style="margin-left: 0.5rem; color: #1f2937;">{rec.get('title', 'N/A')}</strong>
                <p style="color: #4b5563; margin-top: 0.5rem; margin-bottom: 0;">{rec.get('description', '')[:200]}...</p>
                <div style="color: #9ca3af; font-size: 0.75rem; margin-top: 0.5rem;">
                    {dept} • {format_time_ago(rec['timestamp'])}
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Tabelle
    st.markdown("#### Empfehlungen-Tabelle")
    display_df = filtered_df.copy()
    # Convert to datetime safely
    if 'timestamp' in display_df.columns and not display_df.empty:
        try:
            dt_series = pd.to_datetime(display_df['timestamp'], errors='coerce', infer_datetime_format=True)
            if pd.api.types.is_datetime64_any_dtype(dt_series):
                # Konvertiere UTC zu lokaler Zeit für Anzeige
                display_df['Zeitstempel'] = dt_series.apply(lambda x: convert_utc_to_local(x).strftime('%Y-%m-%d %H:%M:%S') if convert_utc_to_local(x) else str(x))
            else:
                display_df['Zeitstempel'] = display_df['timestamp'].astype(str)
        except Exception:
            display_df['Zeitstempel'] = display_df['timestamp'].astype(str) if 'timestamp' in display_df.columns else ''
    else:
        display_df['Zeitstempel'] = ''
    display_df['Titel'] = display_df.get('title', '')
    display_df['Priorität'] = display_df['priority'].map(lambda x: SEVERITY_MAP.get(x, x))
    display_df['Abteilung'] = display_df.get('department', '').map(lambda x: DEPT_MAP.get(x, x) if pd.notna(x) else '')
    display_df['Status'] = display_df.get('status', '').map(lambda x: STATUS_MAP.get(x, x) if pd.notna(x) else '')
    
    table_cols = ['Zeitstempel', 'Titel', 'Priorität', 'Abteilung', 'Status']
    st.dataframe(display_df[table_cols], use_container_width=True, hide_index=True)
    
    # Export
    col1, col2 = st.columns([1, 4])
    with col1:
        # Fix: Use helper function to safely prepare export DataFrame
        required_cols = ['timestamp', 'title', 'priority', 'department', 'status']
        export_df = prepare_export_df(filtered_df, required_cols)
        csv_data = export_to_csv(export_df, "recommendations")
        st.download_button(
            "📥 CSV Export",
            csv_data,
            f"recommendations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv"
        )


def render_transport_section(df: pd.DataFrame, search_text: str, selected_departments: list, 
                            selected_statuses: list):
    """Rendert Transport-Sektion"""
    st.markdown("### Transport")
    
    if df.empty:
        st.info("Keine Transportanfragen verfügbar")
        return
    
    # Filter nach Status
    if selected_statuses and 'status' in df.columns:
        df = df[df['status'].isin(selected_statuses)]
    
    filtered_df = filter_dataframe(df, search_text, selected_departments)
    
    if filtered_df.empty:
        st.warning("Keine Transportanfragen entsprechen den Filtern")
        return
    
    # Tabelle
    st.markdown("#### Transport-Tabelle")
    display_df = filtered_df.copy()
    # Convert to datetime safely
    if 'timestamp' in display_df.columns and not display_df.empty:
        try:
            dt_series = pd.to_datetime(display_df['timestamp'], errors='coerce', infer_datetime_format=True)
            if pd.api.types.is_datetime64_any_dtype(dt_series):
                # Konvertiere UTC zu lokaler Zeit für Anzeige
                display_df['Zeitstempel'] = dt_series.apply(lambda x: convert_utc_to_local(x).strftime('%Y-%m-%d %H:%M:%S') if convert_utc_to_local(x) else str(x))
            else:
                display_df['Zeitstempel'] = display_df['timestamp'].astype(str)
        except Exception:
            display_df['Zeitstempel'] = display_df['timestamp'].astype(str) if 'timestamp' in display_df.columns else ''
    else:
        display_df['Zeitstempel'] = ''
    display_df['Typ'] = display_df.get('request_type', '')
    display_df['Von'] = display_df.get('from_location', '')
    display_df['Nach'] = display_df.get('to_location', '')
    display_df['Priorität'] = display_df['priority'].map(lambda x: SEVERITY_MAP.get(x, x))
    display_df['Status'] = display_df.get('status', '').map(lambda x: STATUS_MAP.get(x, x) if pd.notna(x) else '')
    display_df['Geschätzte Zeit'] = display_df.get('estimated_time_minutes', 0).astype(str) + ' Min.'
    
    table_cols = ['Zeitstempel', 'Typ', 'Von', 'Nach', 'Priorität', 'Status', 'Geschätzte Zeit']
    st.dataframe(display_df[table_cols], use_container_width=True, hide_index=True)
    
    # Export
    col1, col2 = st.columns([1, 4])
    with col1:
        # Fix: Use helper function to safely prepare export DataFrame
        required_cols = ['timestamp', 'request_type', 'from_location', 'to_location', 'priority', 'status', 'estimated_time_minutes']
        export_df = prepare_export_df(filtered_df, required_cols)
        csv_data = export_to_csv(export_df, "transport")
        st.download_button(
            "📥 CSV Export",
            csv_data,
            f"transport_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv"
        )


def render_inventory_section(df: pd.DataFrame, search_text: str, selected_departments: list):
    """Rendert Inventar-Sektion"""
    st.markdown("### Inventar")
    
    if df.empty:
        st.info("Keine Inventardaten verfügbar")
        return
    
    filtered_df = filter_dataframe(df, search_text, selected_departments)
    
    if filtered_df.empty:
        st.warning("Keine Inventardaten entsprechen den Filtern")
        return
    
    # Hervorhebung kritischer Bestände
    critical_items = filtered_df[filtered_df['current_stock'] < filtered_df['min_threshold']]
    if not critical_items.empty:
        st.markdown("#### ⚠️ Kritische Bestände")
        for _, item in critical_items.iterrows():
            st.warning(f"**{item['item_name']}** ({item.get('department', 'N/A')}): {item['current_stock']} {item.get('unit', '')} (Mindest: {item['min_threshold']})")
    
    st.markdown("---")
    
    # Tabelle
    st.markdown("#### Inventar-Tabelle")
    display_df = filtered_df.copy()
    
    # Fix: Use column access with fallback to Series instead of .get() which returns scalar
    display_df['Artikel'] = display_df['item_name'] if 'item_name' in display_df.columns else pd.Series([''] * len(display_df), index=display_df.index)
    display_df['Kategorie'] = display_df['category'] if 'category' in display_df.columns else pd.Series([''] * len(display_df), index=display_df.index)
    display_df['Aktueller Bestand'] = display_df['current_stock'] if 'current_stock' in display_df.columns else pd.Series([0] * len(display_df), index=display_df.index)
    display_df['Mindestschwelle'] = display_df['min_threshold'] if 'min_threshold' in display_df.columns else pd.Series([0] * len(display_df), index=display_df.index)
    display_df['Max. Kapazität'] = display_df['max_capacity'] if 'max_capacity' in display_df.columns else pd.Series([0] * len(display_df), index=display_df.index)
    
    # Fix: Use column access with fallback to Series instead of .get() which returns scalar
    dept_series = display_df['department'] if 'department' in display_df.columns else pd.Series([''] * len(display_df), index=display_df.index)
    display_df['Abteilung'] = dept_series.map(lambda x: DEPT_MAP.get(x, x) if pd.notna(x) else '')
    
    display_df['Einheit'] = display_df['unit'] if 'unit' in display_df.columns else pd.Series([''] * len(display_df), index=display_df.index)
    
    table_cols = ['Artikel', 'Kategorie', 'Aktueller Bestand', 'Mindestschwelle', 'Max. Kapazität', 'Abteilung', 'Einheit']
    st.dataframe(display_df[table_cols], use_container_width=True, hide_index=True)
    
    # Export
    col1, col2 = st.columns([1, 4])
    with col1:
        # Fix: Use helper function to safely prepare export DataFrame
        required_cols = ['item_name', 'category', 'current_stock', 'min_threshold', 'max_capacity', 'department', 'unit']
        export_df = prepare_export_df(filtered_df, required_cols)
        csv_data = export_to_csv(export_df, "inventory")
        st.download_button(
            "📥 CSV Export",
            csv_data,
            f"inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv"
        )


def render_devices_section(df: pd.DataFrame, search_text: str, selected_departments: list):
    """Rendert Geräte-Sektion"""
    st.markdown("### Geräte")
    
    if df.empty:
        st.info("Keine Gerätedaten verfügbar")
        return
    
    filtered_df = filter_dataframe(df, search_text, selected_departments)
    
    if filtered_df.empty:
        st.warning("Keine Gerätedaten entsprechen den Filtern")
        return
    
    # Tabelle
    st.markdown("#### Geräte-Tabelle")
    display_df = filtered_df.copy()
    
    # Fix: Use column access with fallback to Series instead of .get() which returns scalar
    display_df['Gerät'] = display_df['device_type'] if 'device_type' in display_df.columns else pd.Series([''] * len(display_df), index=display_df.index)
    display_df['Geräte-ID'] = display_df['device_id'] if 'device_id' in display_df.columns else pd.Series([''] * len(display_df), index=display_df.index)
    
    # Fix: Use column access with fallback to Series instead of .get() which returns scalar
    urgency_series = display_df['urgency_level'] if 'urgency_level' in display_df.columns else pd.Series([''] * len(display_df), index=display_df.index)
    display_df['Dringlichkeit'] = urgency_series.map(lambda x: SEVERITY_MAP.get(x, x) if pd.notna(x) else '')
    
    # Fix: Use column access with fallback to Series instead of .get() which returns scalar
    maintenance_series = display_df['next_maintenance_due'] if 'next_maintenance_due' in display_df.columns else pd.Series([pd.NaT] * len(display_df), index=display_df.index)
    # Convert to datetime safely
    try:
        dt_series = pd.to_datetime(maintenance_series, errors='coerce', infer_datetime_format=True)
        if pd.api.types.is_datetime64_any_dtype(dt_series):
            display_df['Nächste Wartung'] = dt_series.dt.strftime('%Y-%m-%d')
        else:
            display_df['Nächste Wartung'] = maintenance_series.astype(str)
    except Exception:
        display_df['Nächste Wartung'] = maintenance_series.astype(str)
    
    # Fix: Use column access with fallback to Series instead of .get() which returns scalar
    dept_series = display_df['department'] if 'department' in display_df.columns else pd.Series([''] * len(display_df), index=display_df.index)
    display_df['Abteilung'] = dept_series.map(lambda x: DEPT_MAP.get(x, x) if pd.notna(x) else '')
    
    table_cols = ['Gerät', 'Geräte-ID', 'Dringlichkeit', 'Nächste Wartung', 'Abteilung']
    st.dataframe(display_df[table_cols], use_container_width=True, hide_index=True)
    
    # Export
    col1, col2 = st.columns([1, 4])
    with col1:
        # Fix: Use helper function to safely prepare export DataFrame
        required_cols = ['device_type', 'device_id', 'urgency_level', 'next_maintenance_due', 'department']
        export_df = prepare_export_df(filtered_df, required_cols)
        csv_data = export_to_csv(export_df, "devices")
        st.download_button(
            "📥 CSV Export",
            csv_data,
            f"devices_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv"
        )


def render_capacity_section(df: pd.DataFrame, search_text: str, selected_departments: list):
    """Rendert Kapazität-Sektion"""
    st.markdown("### Kapazität")
    
    if df.empty:
        st.info("Keine Kapazitätsdaten verfügbar")
        return
    
    filtered_df = filter_dataframe(df, search_text, selected_departments)
    
    if filtered_df.empty:
        st.warning("Keine Kapazitätsdaten entsprechen den Filtern")
        return
    
    # Visualisierung
    if not filtered_df.empty and 'utilization_rate' in filtered_df.columns:
        st.markdown("#### Auslastung nach Abteilung")
        fig = px.bar(
            filtered_df,
            x='department',
            y='utilization_rate',
            title="Kapazitätsauslastung",
            labels={'department': 'Abteilung', 'utilization_rate': 'Auslastung (%)'},
            color='utilization_rate',
            color_continuous_scale='RdYlGn_r'
        )
        fig.update_layout(height=400, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Tabelle
    st.markdown("#### Kapazitäts-Tabelle")
    display_df = filtered_df.copy()
    display_df['Abteilung'] = display_df.get('department', '').map(lambda x: DEPT_MAP.get(x, x) if pd.notna(x) else '')
    display_df['Belegte Betten'] = display_df.get('occupied_beds', 0)
    display_df['Freie Betten'] = display_df.get('available_beds', 0)
    display_df['Gesamt'] = display_df.get('total_beds', 0)
    display_df['Auslastung %'] = (display_df.get('utilization_rate', 0) * 100).round(1) if 'utilization_rate' in display_df.columns else 0
    
    table_cols = ['Abteilung', 'Belegte Betten', 'Freie Betten', 'Gesamt', 'Auslastung %']
    st.dataframe(display_df[table_cols], use_container_width=True, hide_index=True)
    
    # Export
    col1, col2 = st.columns([1, 4])
    with col1:
        export_cols = ['department', 'occupied_beds', 'available_beds', 'total_beds', 'utilization_rate']
        available_cols = [col for col in export_cols if col in filtered_df.columns]
        csv_data = export_to_csv(filtered_df[available_cols], "capacity")
        st.download_button(
            "📥 CSV Export",
            csv_data,
            f"capacity_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv"
        )


# ===== LAZY DATA FETCHING FUNCTIONS =====
# Jede Funktion lädt Daten nur bei Bedarf (wenn Tab geöffnet wird)
# Mit Caching für bessere Performance

@st.cache_data(ttl=300)
def get_metrics_data_lazy(_db, time_range_minutes: int):
    """Lädt Metriken-Daten lazy"""
    try:
        if time_range_minutes:
            return _db.get_metrics_last_n_minutes(time_range_minutes)
        else:
            return _db.get_recent_metrics(1000)
    except Exception as e:
        return []

@st.cache_data(ttl=300)
def get_alerts_data_lazy(_db, time_range_minutes: int):
    """Lädt Alerts-Daten lazy"""
    try:
        hours = (time_range_minutes // 60) if time_range_minutes else 168  # Default: 7 Tage
        return _db.get_alerts_by_time_range(hours)
    except Exception as e:
        return []

@st.cache_data(ttl=300)
def get_predictions_data_lazy(_db):
    """Lädt Vorhersagen-Daten lazy"""
    try:
        return _db.get_predictions(60)  # Nächste 60 Minuten
    except Exception as e:
        return []

@st.cache_data(ttl=300)
def get_recommendations_data_lazy(_db):
    """Lädt Empfehlungen-Daten lazy"""
    try:
        return _db.get_pending_recommendations()
    except Exception as e:
        return []

@st.cache_data(ttl=300)
def get_transport_data_lazy(_db):
    """Lädt Transport-Daten lazy"""
    try:
        return _db.get_transport_requests()
    except Exception as e:
        return []

@st.cache_data(ttl=300)
def get_inventory_data_lazy(_db):
    """Lädt Inventar-Daten lazy"""
    try:
        return _db.get_inventory_status()
    except Exception as e:
        return []

@st.cache_data(ttl=300)
def get_devices_data_lazy(_db):
    """Lädt Geräte-Daten lazy"""
    try:
        return _db.get_device_maintenance_urgencies()
    except Exception as e:
        return []

@st.cache_data(ttl=300)
def get_capacity_data_lazy(_db, _sim):
    """Lädt Kapazitäts-Daten lazy"""
    try:
        # Verwende gecachte Metriken aus session_state
        if 'cached_sim_metrics' in st.session_state:
            sim_metrics = st.session_state.cached_sim_metrics
        else:
            sim_metrics = _sim.get_current_metrics() if _sim else {}
        if sim_metrics and isinstance(sim_metrics, dict) and len(sim_metrics) > 0:
            return _db.get_capacity_from_simulation(sim_metrics)
        else:
            return _db.get_capacity_overview()
    except Exception as e:
        try:
            return _db.get_capacity_overview()
        except:
            return []


def render(db, sim, get_cached_alerts=None, get_cached_recommendations=None, get_cached_capacity=None):
    """Rendert die Live-Metriken-Seite mit umfassender Datenübersicht"""
    # ===== SOFORT: STRUKTUR RENDERN =====
    st.markdown("### Live-Metriken - Umfassende Datenübersicht")
    
    # Loading Spinner
    spinner_placeholder = st.empty()
    with spinner_placeholder.container():
        st.markdown(render_loading_spinner("Lade Datenübersicht..."), unsafe_allow_html=True)
    
    # Auto-Refresh Toggle
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        auto_refresh = st.checkbox("🔄 Auto-Refresh (5 Min.)", value=False, key="auto_refresh_metrics")
    with col2:
        if st.button("🔄 Jetzt aktualisieren"):
            st.cache_data.clear()  # Cache leeren bei manueller Aktualisierung
            st.rerun()
    
    # Leere Platzhalter vorbereiten
    filters_placeholder = st.empty()
    tabs_placeholder = st.empty()
    
    # ===== DATEN ABRUFEN =====
    # ===== PROGRESSIV: FILTER UND TABS =====
    with filters_placeholder.container():
        # Filter-Bereich
        with st.expander("🔍 Filter", expanded=True):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                time_range = st.selectbox(
                    "Zeitraum",
                    ['1h', '6h', '24h', '7d', '30d', 'all'],
                    index=3,  # Default: 7d
                    key="time_range_filter"
                )
                time_range_minutes = get_time_range_minutes(time_range)
            
            with col2:
                # Alle verfügbaren Abteilungen sammeln
                all_departments = set()
                # Aus Metriken
                metrics_sample = db.get_recent_metrics(100)
                if metrics_sample:
                    depts = [m.get('department') for m in metrics_sample if m.get('department')]
                    all_departments.update(depts)
                # Aus Kapazität (verwende get_cached_capacity für optimierten Zugriff)
                if get_cached_capacity:
                    capacity_sample = get_cached_capacity()
                elif 'background_data' in st.session_state and st.session_state.background_data:
                    capacity_sample = st.session_state.background_data.get('capacity', [])
                else:
                    capacity_sample = db.get_capacity_overview()  # Fallback
                if capacity_sample:
                    depts = [c.get('department') for c in capacity_sample if c.get('department')]
                    all_departments.update(depts)
                
                department_list = sorted([d for d in all_departments if d])
                selected_departments = st.multiselect(
                    "Abteilung",
                    department_list,
                    key="department_filter"
                )
            
            with col3:
                search_text = st.text_input("🔍 Textsuche", key="search_filter", placeholder="Suche in allen Feldern...")
                
                # Zusätzliche Filter
                col4, col5 = st.columns(2)
                with col4:
                    min_value = st.number_input("Min. Wert", value=None, key="min_value_filter", placeholder="Optional")
                with col5:
                    max_value = st.number_input("Max. Wert", value=None, key="max_value_filter", placeholder="Optional")
    
    # Spinner entfernen
    spinner_placeholder.empty()
    
    # Daten werden lazy geladen - nur wenn Tab geöffnet wird
    # Initialisiere leere DataFrames für Filter
    alerts_df = pd.DataFrame()
    recommendations_df = pd.DataFrame()
    transport_df = pd.DataFrame()
    
    # Lade nur Daten für Filter-Tabs (Alerts, Recommendations, Transport) vorab
    # Verwende Background-Daten für sofortigen Zugriff
    if 'background_data' in st.session_state and st.session_state.background_data:
        background_data = st.session_state.background_data
        alerts_data = background_data.get('alerts', [])
        recommendations_data = background_data.get('recommendations', [])
        transport_data = background_data.get('transport', [])
    else:
        # Fallback: Lazy Loading
        try:
            alerts_data = get_alerts_data_lazy(db, time_range_minutes)
        except Exception as e:
            alerts_data = []
        try:
            recommendations_data = get_recommendations_data_lazy(db)
        except Exception as e:
            recommendations_data = []
        try:
            transport_data = get_transport_data_lazy(db)
        except Exception as e:
            transport_data = []
    
    alerts_df = pd.DataFrame(alerts_data) if alerts_data else pd.DataFrame()
    recommendations_df = pd.DataFrame(recommendations_data) if recommendations_data else pd.DataFrame()
    transport_df = pd.DataFrame(transport_data) if transport_data else pd.DataFrame()
    
    # Zusätzliche Filter in einem Expander
    with st.expander("🔧 Erweiterte Filter", expanded=False):
        col1, col2, col3 = st.columns(3)
        
        selected_severities = None
        with col1:
            if not alerts_df.empty and 'severity' in alerts_df.columns:
                severity_options = alerts_df['severity'].unique().tolist()
                selected_severities = st.multiselect(
                    "Schweregrad (Alerts)",
                    severity_options,
                    key="severity_filter_alerts"
                )
        
        selected_rec_statuses = None
        with col2:
            if not recommendations_df.empty and 'status' in recommendations_df.columns:
                rec_status_options = recommendations_df['status'].unique().tolist()
                selected_rec_statuses = st.multiselect(
                    "Status (Empfehlungen)",
                    rec_status_options,
                    key="status_filter_recommendations"
                )
        
        selected_transport_statuses = None
        with col3:
            if not transport_df.empty and 'status' in transport_df.columns:
                transport_status_options = transport_df['status'].unique().tolist()
                selected_transport_statuses = st.multiselect(
                    "Status (Transport)",
                    transport_status_options,
                    key="status_filter_transport"
                )
    
    # Tabs für verschiedene Datentypen
    with tabs_placeholder.container():
        tabs = st.tabs([
            "📊 Metriken",
            "⚠️ Alerts",
            "🔮 Vorhersagen",
            "💡 Empfehlungen",
            "🚑 Transport",
            "📦 Inventar",
            "🔧 Geräte",
            "🏥 Kapazität"
        ])
    
    # Rendere Sektionen mit Lazy Loading
    # Daten werden erst geladen wenn Tab tatsächlich gerendert wird
    with tabs[0]:
        # Metriken-Tab: Zeige zuerst aktuelle Werte aus sim_metrics (konsistent mit Dashboard)
        if sim:
            sim_metrics = None
            if 'cached_sim_metrics' in st.session_state:
                sim_metrics = st.session_state.cached_sim_metrics
            else:
                sim_metrics = sim.get_current_metrics() if sim else {}
            
            if sim_metrics:
                st.markdown("#### Aktuelle Werte (Live)")
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    ed_load = sim_metrics.get('ed_load', 0)
                    st.metric("Notaufnahme-Auslastung", f"{ed_load:.0f}%")
                with col2:
                    waiting_count = int(sim_metrics.get('waiting_count', 0))
                    st.metric("Wartende Patienten", waiting_count)
                with col3:
                    beds_free = int(sim_metrics.get('beds_free', 0))
                    st.metric("Freie Betten", beds_free)
                with col4:
                    staff_load = sim_metrics.get('staff_load', 0)
                    st.metric("Personal-Auslastung", f"{staff_load:.0f}%")
                
                col5, col6, col7 = st.columns(3)
                with col5:
                    rooms_free = int(sim_metrics.get('rooms_free', 0))
                    st.metric("Freie Räume", rooms_free)
                with col6:
                    or_load = sim_metrics.get('or_load', 0)
                    st.metric("OP-Auslastung", f"{or_load:.0f}%")
                with col7:
                    transport_queue = int(sim_metrics.get('transport_queue', 0))
                    st.metric("Transport-Warteschlange", transport_queue)
                
                st.markdown("---")
                st.markdown("#### Historische Daten")
        
        # Lade historische Daten lazy
        try:
            metrics_data = get_metrics_data_lazy(db, time_range_minutes)
            metrics_df = pd.DataFrame(metrics_data) if metrics_data else pd.DataFrame()
        except Exception as e:
            metrics_df = pd.DataFrame()
        render_metrics_section(
            metrics_df,
            time_range_minutes,
            search_text,
            selected_departments,
            min_value,
            max_value
        )
    
    with tabs[1]:
        # Alerts-Tab: Daten bereits geladen für Filter
        render_alerts_section(
            alerts_df,
            search_text,
            selected_departments,
            selected_severities
        )
    
    with tabs[2]:
        # Vorhersagen-Tab: Verwende Background-Daten
        if 'background_data' in st.session_state and st.session_state.background_data:
            predictions_data = st.session_state.background_data.get('predictions', [])
        else:
            try:
                predictions_data = get_predictions_data_lazy(db)
            except Exception as e:
                predictions_data = []
        predictions_df = pd.DataFrame(predictions_data) if predictions_data else pd.DataFrame()
        render_predictions_section(
            predictions_df,
            search_text,
            selected_departments
        )
    
    with tabs[3]:
        # Empfehlungen-Tab: Daten bereits geladen für Filter
        render_recommendations_section(
            recommendations_df,
            search_text,
            selected_departments,
            selected_rec_statuses
        )
    
    with tabs[4]:
        # Transport-Tab: Daten bereits geladen für Filter
        render_transport_section(
            transport_df,
            search_text,
            selected_departments,
            selected_transport_statuses
        )
    
    with tabs[5]:
        # Inventar-Tab: Verwende Background-Daten
        if 'background_data' in st.session_state and st.session_state.background_data:
            inventory_data = st.session_state.background_data.get('inventory', [])
        else:
            try:
                inventory_data = get_inventory_data_lazy(db)
            except Exception as e:
                inventory_data = []
        inventory_df = pd.DataFrame(inventory_data) if inventory_data else pd.DataFrame()
        render_inventory_section(
            inventory_df,
            search_text,
            selected_departments
        )
    
    with tabs[6]:
        # Geräte-Tab: Verwende Background-Daten
        if 'background_data' in st.session_state and st.session_state.background_data:
            devices_data = st.session_state.background_data.get('devices', [])
        else:
            try:
                devices_data = get_devices_data_lazy(db)
            except Exception as e:
                devices_data = []
        devices_df = pd.DataFrame(devices_data) if devices_data else pd.DataFrame()
        render_devices_section(
            devices_df,
            search_text,
            selected_departments
        )
    
    with tabs[7]:
        # Kapazitäts-Tab: Verwende Background-Daten
        if 'background_data' in st.session_state and st.session_state.background_data:
            capacity_data = st.session_state.background_data.get('capacity', [])
        else:
            try:
                capacity_data = get_capacity_data_lazy(db, sim)
            except Exception as e:
                capacity_data = []
        capacity_df = pd.DataFrame(capacity_data) if capacity_data else pd.DataFrame()
        render_capacity_section(
            capacity_df,
            search_text,
            selected_departments
        )
    
    # Auto-Refresh Info
    if auto_refresh:
        st.info("ℹ️ Auto-Refresh ist aktiv. Daten werden alle 5 Minuten automatisch aktualisiert (Cache-TTL).")
