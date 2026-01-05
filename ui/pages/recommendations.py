"""
Seitenmodul für Empfehlungen
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
from ui.components import render_badge, render_empty_state


def render(db, sim, get_cached_alerts=None, get_cached_recommendations=None, get_cached_capacity=None):
    """Rendert die Empfehlungen-Seite"""
    
    # Empfehlungen abrufen
    all_recommendations = db.get_pending_recommendations()
    
    if all_recommendations:
        # German translation maps
        priority_de_map = {'high': 'hoch', 'medium': 'mittel', 'low': 'niedrig'}
        severity_de_map = {'high': 'hoch', 'medium': 'mittel', 'low': 'niedrig'}
        vertrauen_map = {'high': 'hoch', 'medium': 'mittel', 'low': 'niedrig'}
        
        # Filter
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            # Priority filter
            unique_priorities = sorted(list(set([r.get('priority', 'medium') for r in all_recommendations])))
            priorities_de = [priority_de_map.get(p, p) for p in unique_priorities]
            priority_reverse_map = dict(zip(priorities_de, unique_priorities))
            priorities_de_display = ["Alle"] + priorities_de
            selected_priority_de = st.selectbox("Priorität", priorities_de_display, key="rec_priority")
            selected_priority = None if selected_priority_de == "Alle" else priority_reverse_map.get(selected_priority_de, selected_priority_de)
        
        with col2:
            # Department filter
            unique_depts = sorted(list(set([r.get('department', 'N/A') for r in all_recommendations if r.get('department')])))
            depts_de_display = ["Alle"] + unique_depts
            selected_dept = st.selectbox("Abteilung", depts_de_display, key="rec_dept")
            selected_dept = None if selected_dept == "Alle" else selected_dept
        
        with col3:
            # Rec type filter
            unique_rec_types = sorted(list(set([r.get('rec_type', 'general') for r in all_recommendations])))
            rec_type_map = {
                'capacity': 'Kapazität',
                'staffing': 'Personal',
                'inventory': 'Inventar',
                'general': 'Allgemein',
            }
            rec_types_de = [rec_type_map.get(rt, rt.replace('_', ' ').title()) for rt in unique_rec_types]
            rec_type_reverse_map = dict(zip(rec_types_de, unique_rec_types))
            rec_types_de_display = ["Alle"] + rec_types_de
            selected_rec_type_de = st.selectbox("Typ", rec_types_de_display, key="rec_type")
            selected_rec_type = None if selected_rec_type_de == "Alle" else rec_type_reverse_map.get(selected_rec_type_de, selected_rec_type_de)
        
        with col4:
            # Status filter (all recommendations are pending, but we can filter by explanation_score)
            unique_scores = sorted(list(set([r.get('explanation_score', 'medium') for r in all_recommendations if r.get('explanation_score')])))
            scores_de = [vertrauen_map.get(s, s) for s in unique_scores]
            score_reverse_map = dict(zip(scores_de, unique_scores))
            scores_de_display = ["Alle"] + scores_de
            selected_score_de = st.selectbox("Vertrauen", scores_de_display, key="rec_score")
            selected_score = None if selected_score_de == "Alle" else score_reverse_map.get(selected_score_de, selected_score_de)
        
        # Filter recommendations
        filtered_recommendations = all_recommendations
        if selected_priority:
            filtered_recommendations = [r for r in filtered_recommendations if r.get('priority') == selected_priority]
        if selected_dept:
            filtered_recommendations = [r for r in filtered_recommendations if r.get('department') == selected_dept]
        if selected_rec_type:
            filtered_recommendations = [r for r in filtered_recommendations if r.get('rec_type') == selected_rec_type]
        if selected_score:
            filtered_recommendations = [r for r in filtered_recommendations if r.get('explanation_score') == selected_score]
        
        st.markdown("")  # Abstand
        
        if filtered_recommendations:
            for rec in filtered_recommendations:
                priority_color = get_priority_color(rec['priority'])
                priority_de = priority_de_map.get(rec['priority'], rec['priority'])
                badge_html = render_badge(priority_de.upper(), rec['priority'])

                # Impact tags (extract from department and rec_type)
                impact_tags = []
                if rec.get('department'):
                    impact_tags.append(rec['department'])
                if rec.get('rec_type'):
                    rec_type_map = {
                        'capacity': 'Kapazität',
                        'staffing': 'Personal',
                        'inventory': 'Inventar',
                        'general': 'Allgemein',
                    }
                    rec_type = rec['rec_type']
                    impact_tags.append(rec_type_map.get(rec_type, rec_type.replace('_', ' ').title()))
                
                if rec.get('explanation_score'):
                    explanation_score_de = vertrauen_map.get(rec['explanation_score'], rec['explanation_score'])
                    explanation_color = get_explanation_score_color(rec['explanation_score'])
                    impact_tags.append(f"Vertrauen: {explanation_score_de.upper()}")

                # Neues Template-Format verwenden, falls verfügbar
                has_new_format = rec.get('action') and rec.get('reason')

                if has_new_format:
                    # Build impact tags HTML
                    impact_tags_html = ' '.join([f'<span class="badge" style="background: #e5e7eb; color: #4b5563; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem;">{tag}</span>' for tag in impact_tags])
                    
                    st.markdown(f"""
                    <div style="background: white; padding: 1.5rem; border-radius: 8px; margin-bottom: 1rem; border-left: 4px solid {priority_color}; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                        <div style="margin-bottom: 1rem;">
                            <h4 style="margin: 0 0 0.5rem 0; color: #1f2937;">{rec['title']}</h4>
                            <div style="margin-bottom: 0.75rem;">{badge_html}</div>
                        </div>
                        <div style="background: #f9fafb; padding: 1rem; border-radius: 6px; margin-bottom: 0.75rem;">
                            <div style="margin-bottom: 0.75rem;">
                                <strong style="color: #1f2937; font-size: 0.875rem;">Maßnahme:</strong>
                                <p style="margin: 0.25rem 0 0 0; color: #4b5563; line-height: 1.6;">{rec.get('action', 'N/A')}</p>
                            </div>
                            <div style="margin-bottom: 0.75rem;">
                                <strong style="color: #1f2937; font-size: 0.875rem;">Begründung:</strong>
                                <p style="margin: 0.25rem 0 0 0; color: #4b5563; line-height: 1.6;">{rec.get('reason', 'N/A')}</p>
                            </div>
                            <div style="margin-bottom: 0.75rem;">
                                <strong style="color: #1f2937; font-size: 0.875rem;">Erwartete Auswirkung:</strong>
                                <p style="margin: 0.25rem 0 0 0; color: #4b5563; line-height: 1.6;">{rec.get('expected_impact', 'N/A')}</p>
                            </div>
                            <div>
                                <strong style="color: #1f2937; font-size: 0.875rem;">Sicherheits-Hinweis:</strong>
                                <p style="margin: 0.25rem 0 0 0; color: #4b5563; line-height: 1.6;">{rec.get('safety_note', 'N/A')}</p>
                            </div>
                        </div>
                        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.75rem;">
                            {impact_tags_html}
                        </div>
                        <div style="color: #6b7280; font-size: 0.8125rem;">
                            {format_time_ago(rec['timestamp'])}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # Fallback to old format
                    impact_tags_html = ' '.join([f'<span class="badge" style="background: #e5e7eb; color: #4b5563; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem;">{tag}</span>' for tag in impact_tags])
                    
                    st.markdown(f"""
                    <div style="background: white; padding: 1.5rem; border-radius: 8px; margin-bottom: 1rem; border-left: 4px solid {priority_color}; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                        <div style="display: flex; align-items: start; gap: 0.75rem; margin-bottom: 1rem;">
                            {badge_html}
                            <div style="flex: 1;">
                                <h4 style="margin: 0 0 0.5rem 0; color: #1f2937;">{rec['title']}</h4>
                                <p style="color: #6b7280; margin: 0; line-height: 1.6;">{rec['description']}</p>
                            </div>
                        </div>
                        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.75rem;">
                            {impact_tags_html}
                        </div>
                        <div style="color: #6b7280; font-size: 0.8125rem;">
                            {format_time_ago(rec['timestamp'])}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                # Expandable "Why suggested?" section
                with st.expander("Warum vorgeschlagen?", expanded=False):
                    if has_new_format:
                        explanation = f"""
                        <strong>Begründung:</strong> {rec.get('reason', 'N/A')}<br><br>
                        <strong>Erwartete Auswirkung:</strong> {rec.get('expected_impact', 'N/A')}<br><br>
                        """
                    else:
                        rec_type = rec.get('rec_type', 'general')
                        explanations = {
                            'capacity': 'Diese Empfehlung wurde basierend auf aktueller Kapazitätsauslastung generiert. Sie berücksichtigt Bettenverfügbarkeit, erwartete Entlassungen und aktuelle Belegung.',
                            'staffing': 'Diese Empfehlung wurde basierend auf Personalauslastung und aktuellen Arbeitsbelastungen generiert. Sie berücksichtigt Schichtpläne und verfügbare Ressourcen.',
                            'inventory': 'Diese Empfehlung wurde basierend auf Inventarständen und Verbrauchsprognosen generiert. Sie berücksichtigt aktuelle Bestände und erwarteten Bedarf.',
                            'general': 'Diese Empfehlung wurde basierend auf allgemeinen Systemmetriken und Trends generiert.'
                        }
                        explanation = explanations.get(rec_type, explanations['general'])
                    
                    st.markdown(f"""
                    <div style="background: #f9fafb; padding: 1rem; border-radius: 6px; border-left: 3px solid {priority_color};">
                        <div style="color: #4b5563; line-height: 1.6;">{explanation}</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                # Annehmen/Ablehnen-Buttons
                col1, col2, col3 = st.columns([4, 1, 1])
                with col1:
                    action_text = st.text_input(
                        "Maßnahme / Begründung",
                        key=f"rec_action_{rec['id']}",
                        placeholder="Bitte ergreifende Maßnahme oder Ablehnungsgrund eingeben"
                    )
                with col2:
                    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
                    accept_clicked = st.button("✅ Annehmen", key=f"rec_accept_{rec['id']}", use_container_width=True)
                    if accept_clicked:
                        if action_text:
                            db.accept_recommendation(rec['id'], action_text)
                            # Simulationseffekt basierend auf Empfehlungstyp anwenden
                            rec_type = rec.get('rec_type', '')
                            if 'staffing' in rec_type.lower() or 'reassign' in rec.get('action', '').lower():
                                sim.apply_recommendation_effect(rec_type, 'staffing_reassignment', duration_minutes=30)
                            elif 'capacity' in rec_type.lower() or 'overflow' in rec.get('action', '').lower() or 'bed' in rec.get('action', '').lower():
                                sim.apply_recommendation_effect(rec_type, 'open_overflow_beds', duration_minutes=45)
                            elif 'room' in rec_type.lower() or 'room' in rec.get('action', '').lower():
                                sim.apply_recommendation_effect(rec_type, 'room_allocation', duration_minutes=30)
                            st.success("✅ Empfehlung angenommen")
                            st.rerun()
                        else:
                            st.warning("⚠️ Bitte Maßnahme eingeben")
                with col3:
                    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
                    reject_clicked = st.button("❌ Ablehnen", key=f"rec_reject_{rec['id']}", use_container_width=True)
                    if reject_clicked:
                        if action_text:
                            db.reject_recommendation(rec['id'], action_text)
                            st.info("❌ Empfehlung abgelehnt")
                            st.rerun()
                        else:
                            st.warning("⚠️ Bitte Ablehnungsgrund eingeben")
                
                st.markdown("---")
        else:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-state-icon">🔍</div>
                <div class="empty-state-title">Keine Empfehlungen gefunden</div>
                <div class="empty-state-text">Keine Empfehlungen entsprechen den ausgewählten Filtern</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-icon">✅</div>
            <div class="empty-state-title">Keine ausstehenden Empfehlungen</div>
            <div class="empty-state-text">Alle Empfehlungen wurden überprüft</div>
        </div>
        """, unsafe_allow_html=True)

