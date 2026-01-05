"""
Seitenmodul für Kapazitätsübersicht
"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pandas as pd
import random
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
    if 'cached_sim_metrics' in st.session_state:
        return st.session_state.cached_sim_metrics
    if _sim:
        return _sim.get_current_metrics()
    return {}

@st.cache_data(ttl=30)
def _get_capacity_from_simulation_cached(_db, _sim_metrics):
    """Gecachte Kapazitätsdaten aus Simulation"""
    return _db.get_capacity_from_simulation(_sim_metrics)

def render(db, sim, get_cached_alerts=None, get_cached_recommendations=None, get_cached_capacity=None):
    """Rendert die Kapazitätsübersicht-Seite"""
    # ===== SOFORT: STRUKTUR RENDERN =====
    st.markdown("### Kapazitätsübersicht")
    
    # Loading Spinner
    spinner_placeholder = st.empty()
    with spinner_placeholder.container():
        st.markdown(render_loading_spinner("Lade Kapazitätsdaten..."), unsafe_allow_html=True)
    
    # Leere Platzhalter vorbereiten
    metrics_placeholder = st.empty()
    departments_placeholder = st.empty()
    charts_placeholder = st.empty()
    
    # ===== DATEN ABRUFEN =====
    # Simulierte Metriken abrufen für konsistente Daten
    sim_metrics = _get_simulation_metrics_cached(sim)  # Gecacht
    # Kapazitätsdaten aus Simulation berechnen (konsistent mit Dashboard)
    capacity = _get_capacity_from_simulation_cached(db, sim_metrics)  # Gecacht
    
    if capacity:
        # Dedupliziere Kapazitätsdaten: Gruppiere nach Abteilung und aggregiere Werte
        capacity_dict = {}
        for cap in capacity:
            dept = cap.get('department')
            if dept:
                if dept not in capacity_dict:
                    capacity_dict[dept] = cap.copy()
                else:
                    # Aggregiere Werte für doppelte Abteilungen
                    existing = capacity_dict[dept]
                    existing['total_beds'] = existing.get('total_beds', 0) + cap.get('total_beds', 0)
                    existing['occupied_beds'] = existing.get('occupied_beds', 0) + cap.get('occupied_beds', 0)
                    existing['available_beds'] = existing.get('available_beds', 0) + cap.get('available_beds', 0)
                    if 'free_beds' in existing:
                        existing['free_beds'] = existing.get('free_beds', 0) + cap.get('free_beds', 0)
                    
                    # WICHTIG: Für ER/ED utilization_rate aus sim_metrics beibehalten (keine Neuberechnung!)
                    if dept in ('ER', 'ED'):
                        # Für ER/ED: utilization_percent direkt aus ed_load in sim_metrics
                        ed_load = sim_metrics.get('ed_load', 65.0)
                        existing['utilization_rate'] = ed_load / 100.0
                        existing['utilization_percent'] = ed_load
                    else:
                        # Für alle anderen Abteilungen: Prüfe ob utilization_rate vorhanden ist
                        # Wenn vorhanden, beibehalten (gewichteter Durchschnitt basierend auf total_beds)
                        if 'utilization_rate' in existing and existing.get('utilization_rate') is not None and 'utilization_rate' in cap and cap.get('utilization_rate') is not None:
                            # Gewichteter Durchschnitt der utilization_rates basierend auf total_beds
                            old_total = existing['total_beds'] - cap.get('total_beds', 0)
                            new_total = cap.get('total_beds', 0)
                            if old_total > 0 and new_total > 0:
                                old_util = existing['utilization_rate']
                                new_util = cap['utilization_rate']
                                total_beds_combined = old_total + new_total
                                weighted_util = (old_util * old_total + new_util * new_total) / total_beds_combined
                                existing['utilization_rate'] = weighted_util
                                existing['utilization_percent'] = weighted_util * 100
                            elif new_total > 0:
                                existing['utilization_rate'] = cap['utilization_rate']
                                existing['utilization_percent'] = cap.get('utilization_percent', cap['utilization_rate'] * 100)
                        elif 'utilization_rate' in cap and cap.get('utilization_rate') is not None:
                            # Nur neuer Eintrag hat utilization_rate
                            existing['utilization_rate'] = cap['utilization_rate']
                            existing['utilization_percent'] = cap.get('utilization_percent', cap['utilization_rate'] * 100)
                        else:
                            # Fallback: Neuberechnung nur wenn keine utilization_rate vorhanden
                            if existing['total_beds'] > 0:
                                existing['utilization_rate'] = existing['occupied_beds'] / existing['total_beds']
                                existing['utilization_percent'] = existing['utilization_rate'] * 100
                            else:
                                existing['utilization_rate'] = 0
                                existing['utilization_percent'] = 0
        
        # Konvertiere zurück zu Liste
        capacity = list(capacity_dict.values())
        
        df_cap = pd.DataFrame(capacity)
        
        # Fix: Calculate available_beds if missing (total_beds - occupied_beds)
        if 'available_beds' not in df_cap.columns:
            if 'total_beds' in df_cap.columns and 'occupied_beds' in df_cap.columns:
                df_cap['available_beds'] = df_cap['total_beds'] - df_cap['occupied_beds']
            else:
                df_cap['available_beds'] = 0
        
        # WICHTIG: Für ER/ED utilization_rate aus sim_metrics verwenden
        if 'department' in df_cap.columns:
            er_mask = df_cap['department'].isin(['ER', 'ED'])
            if er_mask.any():
                ed_load = sim_metrics.get('ed_load', 65.0)
                df_cap.loc[er_mask, 'utilization_rate'] = ed_load / 100.0
                df_cap.loc[er_mask, 'utilization_percent'] = ed_load
        
        # Fix: Calculate utilization_rate if missing (nur für andere Abteilungen, nicht ER/ED)
        if 'utilization_rate' not in df_cap.columns:
            if 'total_beds' in df_cap.columns and 'occupied_beds' in df_cap.columns:
                df_cap['utilization_rate'] = df_cap.apply(
                    lambda row: row['occupied_beds'] / row['total_beds'] if row['total_beds'] > 0 else 0,
                    axis=1
                )
                df_cap['utilization_percent'] = df_cap['utilization_rate'] * 100
            else:
                df_cap['utilization_rate'] = 0
                df_cap['utilization_percent'] = 0
        elif 'utilization_percent' not in df_cap.columns:
            # utilization_percent aus utilization_rate berechnen, falls fehlt
            df_cap['utilization_percent'] = df_cap['utilization_rate'] * 100
        
        # Gesamte Kennzahlen
        gesamt_betten = df_cap['total_beds'].sum() if 'total_beds' in df_cap.columns else 0
        belegte_betten = df_cap['occupied_beds'].sum() if 'occupied_beds' in df_cap.columns else 0
        verfügbare_betten = df_cap['available_beds'].sum()
        gesamt_auslastung = belegte_betten / gesamt_betten if gesamt_betten > 0 else 0

        # ===== PROGRESSIV: METRIKEN RENDERN =====
        with metrics_placeholder.container():
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.markdown(f'<div class="fade-in">', unsafe_allow_html=True)
                st.metric("Gesamtbetten", gesamt_betten)
                st.markdown('</div>', unsafe_allow_html=True)
            with col2:
                st.markdown(f'<div class="fade-in-delayed">', unsafe_allow_html=True)
                st.metric("Belegt", belegte_betten)
                st.markdown('</div>', unsafe_allow_html=True)
            with col3:
                st.markdown(f'<div class="fade-in-delayed-2">', unsafe_allow_html=True)
                st.metric("Verfügbar", verfügbare_betten)
                st.markdown('</div>', unsafe_allow_html=True)
            with col4:
                st.markdown(f'<div class="fade-in-delayed-3">', unsafe_allow_html=True)
                kapazitäts_status = calculate_capacity_status(gesamt_auslastung)
                st.metric("Gesamtauslastung", f"{kapazitäts_status['percentage']}%")
                st.markdown('</div>', unsafe_allow_html=True)
        
        # Spinner entfernen
        spinner_placeholder.empty()
        
        st.markdown("---")
        
        # ===== PROGRESSIV: ABTEILUNGSKARTEN =====
        with departments_placeholder.container():
            # Department capacity cards
            # Mapping for department names (English to German) - verwende zentrales Mapping
            from utils import get_department_name_mapping
            department_map = get_department_name_mapping()
            department_map.update({
                'General Ward': 'Allgemeinstation',
                'Neurology': 'Neurologie',
                'Pediatrics': 'Pädiatrie',
                'Oncology': 'Onkologie',
                'Maternity': 'Geburtshilfe',
                'Radiology': 'Radiologie',
                'Other': 'Andere'
            })
            for i, cap in enumerate(capacity):
                # Fix: Calculate available_beds if missing
                if 'available_beds' not in cap:
                    if 'total_beds' in cap and 'occupied_beds' in cap:
                        cap['available_beds'] = cap['total_beds'] - cap['occupied_beds']
                    else:
                        cap['available_beds'] = 0
                
                # WICHTIG: Für ER/ED utilization_rate aus sim_metrics verwenden, nicht neu berechnen
                dept = cap.get('department')
                if dept in ('ER', 'ED'):
                    # Für ER/ED: utilization_percent direkt aus ed_load in sim_metrics
                    ed_load = sim_metrics.get('ed_load', 65.0)
                    cap['utilization_rate'] = ed_load / 100.0
                    cap['utilization_percent'] = ed_load
                # Fix: Calculate utilization_rate if missing (nur für andere Abteilungen, nicht ER/ED)
                elif 'utilization_rate' not in cap:
                    if 'total_beds' in cap and 'occupied_beds' in cap and cap['total_beds'] > 0:
                        cap['utilization_rate'] = cap['occupied_beds'] / cap['total_beds']
                        cap['utilization_percent'] = cap['utilization_rate'] * 100
                    else:
                        cap['utilization_rate'] = 0
                        cap['utilization_percent'] = 0
                
                cap_status = calculate_capacity_status(cap['utilization_rate'])
                dept_color = get_department_color(cap['department'])
                # Deutschen Abteilungsnamen verwenden, falls verfügbar
                german_dept = department_map.get(cap['department'], cap['department'])
                delay_class = "fade-in" if i == 0 else f"fade-in-delayed-{min(i, 3)}" if i <= 3 else "fade-in-delayed-3"
                
                st.markdown(f"""
                <div class="{delay_class}" style="background: white; padding: 1.5rem; border-radius: 8px; margin-bottom: 1rem; border-left: 4px solid {cap_status['color']};">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                        <h4 style="margin: 0; color: {dept_color};">{german_dept}</h4>
                        <span class="badge" style="background: {cap_status['color']}; color: white;">{cap_status['status'].upper()}</span>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 1rem;">
                        <div>
                            <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase;">Gesamt</div>
                            <div style="font-size: 1.5rem; font-weight: 700; color: #1f2937;">{cap.get('total_beds', 0)}</div>
                        </div>
                        <div>
                            <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase;">Belegt</div>
                            <div style="font-size: 1.5rem; font-weight: 700; color: #DC2626;">{cap.get('occupied_beds', 0)}</div>
                        </div>
                        <div>
                            <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase;">Verfügbar</div>
                            <div style="font-size: 1.5rem; font-weight: 700; color: #10B981;">{cap['available_beds']}</div>
                        </div>
                    </div>
                    <div>
                        <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                            <span style="font-size: 0.875rem; color: #6b7280;">Auslastung</span>
                            <span style="font-weight: 600; color: {cap_status['color']};">{cap_status['percentage']}%</span>
                        </div>
                        <div style="background: #e5e7eb; height: 12px; border-radius: 6px; overflow: hidden;">
                            <div style="background: {cap_status['color']}; height: 100%; width: {cap_status['percentage']}%;"></div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        # ===== PROGRESSIV: DIAGRAMME =====
        with charts_placeholder.container():
            # Capacity charts
            st.markdown("---")
            col1, col2 = st.columns(2)

            with col1:
                # Mapping for department names (English to German)
                from utils import get_department_name_mapping
                department_map = get_department_name_mapping()
                department_map.update({
                    'General Ward': 'Allgemeinstation',
                    'Neurology': 'Neurologie',
                    'Pediatrics': 'Pädiatrie',
                    'Oncology': 'Onkologie',
                    'Maternity': 'Geburtshilfe',
                    'Radiology': 'Radiologie',
                    'Other': 'Andere'
                })
                # Deutsche Abteilungsspalte für Plotting hinzufügen
                df_cap['Abteilung'] = df_cap['department'].map(department_map).fillna(df_cap['department'])
                color_map = {department_map.get(dept, dept): get_department_color(dept) for dept in df_cap['department']}
                fig = px.bar(
                    df_cap,
                    x='Abteilung',
                    y='utilization_rate',
                    title="Auslastung nach Abteilung",
                    color='Abteilung',
                    color_discrete_map=color_map,
                    labels={'utilization_rate': 'Auslastung (%)', 'Abteilung': 'Abteilung'}
                )
                fig.update_layout(
                    height=400,
                    yaxis=dict(
                        tickformat='.0%',
                        title='Auslastung (%)'
                    ),
                    xaxis=dict(title='Abteilung'),
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    showlegend=False
                )
                st.markdown('<div class="fade-in">', unsafe_allow_html=True)
                st.plotly_chart(fig, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)

            with col2:
                fig = go.Figure(data=[
                    go.Bar(name='Belegt', x=df_cap['Abteilung'], y=df_cap['occupied_beds'], marker_color='#DC2626'),
                    go.Bar(name='Verfügbar', x=df_cap['Abteilung'], y=df_cap['available_beds'], marker_color='#10B981')
                ])
                fig.update_layout(
                    title="Bettenverfügbarkeit nach Abteilung",
                    height=400,
                    barmode='stack',
                    xaxis_title="Abteilung",
                    yaxis_title="Betten",
                    legend_title_text="Status",
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    ),
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)'
                )
                st.markdown('<div class="fade-in-delayed">', unsafe_allow_html=True)
                st.plotly_chart(fig, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
    else:
        spinner_placeholder.empty()
        st.markdown(render_empty_state("📋", "Keine Kapazitätsdaten verfügbar", "Kapazitätsdaten werden hier angezeigt, sobald sie verfügbar sind"), unsafe_allow_html=True)
