"""
Seitenmodul für Betrieb
"""
import streamlit as st
from datetime import datetime, timedelta, timezone
import pandas as pd
import time
from utils import (
    format_time_ago, get_severity_color, get_priority_color, get_risk_color,
    get_status_color, calculate_inventory_status, calculate_capacity_status,
    format_duration_minutes, get_department_color, get_system_status,
    get_metric_severity_for_load, get_metric_severity_for_count, get_metric_severity_for_free,
    get_explanation_score_color, get_department_name_mapping
)
from ui.components import render_badge, render_empty_state, render_loading_spinner


@st.cache_data(ttl=60)
def _get_audit_log_cached(_db, limit):
    """Gecachter Audit-Log"""
    return _db.get_audit_log(limit)

def render(db, sim, get_cached_alerts=None, get_cached_recommendations=None, get_cached_capacity=None):
    """Rendert die Betrieb-Seite"""
    # ===== SOFORT: STRUKTUR RENDERN =====
    # Operations page with tabs - sofort anzeigen
    tab1, tab2, tab3 = st.tabs(["🚨 Warnungen", "💡 Empfehlungen", "📝 Protokoll"])
    
    # Loading Spinner für jeden Tab
    spinner_tab1 = st.empty()
    spinner_tab2 = st.empty()
    spinner_tab3 = st.empty()
    
    # Alerts Tab
    with tab1:
        st.markdown("### Warnungen")
        with spinner_tab1.container():
            st.markdown(render_loading_spinner("Lade Warnungen..."), unsafe_allow_html=True)
        st.markdown("")  # Spacing
        
        # Filterzeile
        col1, col2, col3 = st.columns([2, 2, 2])
        
        with col1:
            # Bereich Dropdown mit deutschen Übersetzungen
            # Verwende Background-Daten oder get_cached_alerts() für sofortigen Zugriff
            if 'background_data' in st.session_state and st.session_state.background_data:
                all_alerts = st.session_state.background_data.get('alerts', [])
            else:
                all_alerts = get_cached_alerts() if get_cached_alerts else db.get_active_alerts()
            # Severity-Mapping für Filter (Deutsch -> Englisch)
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
            # Mapping für alle eindeutigen Abteilungen erstellen
            unique_depts = sorted(list(set([a.get('department', 'N/A') for a in all_alerts if a.get('department')])))
            areas_de = [dept_map.get(d, d) for d in unique_depts]
            area_map = dict(zip(areas_de, unique_depts))
            areas_de_display = ["Alle"] + areas_de
            selected_area_de = st.selectbox("Bereich", areas_de_display, key="ops_alert_area")
            selected_area = None if selected_area_de == "Alle" else area_map[selected_area_de]
        
        with col2:
            # Severity chips
            severity_options = ["Alle", "hoch", "mittel", "niedrig"]
            selected_severities = st.multiselect(
                "Schweregrad",
                severity_options,
                default=["hoch", "mittel"],
                key="ops_alert_severity"
            )
            if not selected_severities:
                selected_severities = severity_options
        
        with col3:
            # Zeitspanne
            time_range = st.selectbox(
                "Zeitraum",
                ["Letzte 1 Stunde", "Letzte 6 Stunden", "Letzte 24 Stunden"],
                index=2,
                key="ops_alert_time"
            )
            hours_map = {"Letzte 1 Stunde": 1, "Letzte 6 Stunden": 6, "Letzte 24 Stunden": 24}
            hours = hours_map[time_range]
        
        st.markdown("")  # Spacing
        
        # Leere Platzhalter für progressive Anzeige
        alerts_content_placeholder = st.empty()
        
        # Gefilterte Warnungen abrufen - verwende Background-Daten für sofortigen Zugriff
        if 'background_data' in st.session_state and st.session_state.background_data:
            alerts = st.session_state.background_data.get('alerts', [])
        else:
            alerts = get_cached_alerts() if get_cached_alerts else db.get_active_alerts()
        
        # Zeitraum-Filterung manuell anwenden (nur für nicht aufgelöste Warnungen)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        # Hilfsfunktion zum Normalisieren von Timestamps
        def normalize_timestamp(ts):
            if ts is None:
                return None
            
            # Handle pandas Timestamp
            if hasattr(ts, 'to_pydatetime'):
                ts = ts.to_pydatetime()
            
            if isinstance(ts, datetime):
                # Wenn bereits datetime, stelle sicher, dass es timezone-aware ist
                if ts.tzinfo is None:
                    return ts.replace(tzinfo=timezone.utc)
                return ts
            if isinstance(ts, str):
                try:
                    # Versuche ISO-Format
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    # Ensure timezone-aware (fromisoformat might return naive if no timezone in string)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except Exception:
                    try:
                        # Versuche anderes Format
                        dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S.%f')
                        return dt.replace(tzinfo=timezone.utc)
                    except Exception:
                        try:
                            dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                            return dt.replace(tzinfo=timezone.utc)
                        except Exception:
                            return None
            return None
        
        # Filtere nach Zeitraum
        filtered_by_time = []
        for a in alerts:
            ts = normalize_timestamp(a.get('timestamp'))
            
            # Defensive check: Ensure ts is timezone-aware before comparison
            if ts is not None:
                if isinstance(ts, datetime) and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                
                # Now safe to compare
                if ts >= cutoff_time:
                    filtered_by_time.append(a)
        alerts = filtered_by_time
        
        # Filter anwenden
        filtered_alerts = alerts
        if selected_area is not None:
            filtered_alerts = [a for a in filtered_alerts if a.get('department') == selected_area]
        if "Alle" not in selected_severities:
            # Deutsche Filterwerte in englische umwandeln für Vergleich mit Alert-Werten
            selected_severities_en = [severity_en_map.get(sev, sev) for sev in selected_severities]
            filtered_alerts = [a for a in filtered_alerts if a['severity'] in selected_severities_en]
        
        # Spinner entfernen
        spinner_tab1.empty()
        
        # Warnungen als kompakte Karten anzeigen
        with alerts_content_placeholder.container():
            if filtered_alerts:
                for i, alert in enumerate(filtered_alerts):
                    # Prüfe ob Warnung bestätigt wurde
                    is_acknowledged = alert.get('acknowledged', 0) == 1
                    
                    # Wenn bestätigt, verwende blaue Farbe, sonst normale Severity-Farbe
                    if is_acknowledged:
                        border_color = "#3B82F6"  # Blau (blue-500)
                        background_color = "#EFF6FF"  # Sehr helles Blau für Hintergrund
                    else:
                        border_color = get_severity_color(alert['severity'])
                        background_color = "white"
                    
                    # Schweregrad ins Deutsche übersetzen für Anzeige
                    severity_de = severity_de_map.get(alert['severity'], alert['severity'])
                    badge_html = render_badge(severity_de.upper(), alert['severity'])
                    
                    # Bestätigt-Badge hinzufügen wenn bestätigt
                    if is_acknowledged:
                        acknowledged_badge = '<span class="badge" style="background: #3B82F6; color: white;">✓ BESTÄTIGT</span>'  # Blau
                        badge_html = f"{badge_html} {acknowledged_badge}"
                    
                    # Abteilung für Anzeige übersetzen
                    from utils import get_department_name_mapping
                    dept_map = get_department_name_mapping()
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
                    dept_de = dept_map.get(alert.get('department', 'N/A'), alert.get('department', 'N/A'))
                    delay_class = "fade-in" if i == 0 else f"fade-in-delayed-{min(i, 3)}" if i <= 3 else "fade-in-delayed-3"
                    col1, col2 = st.columns([5, 1])
                    with col1:
                        st.html(f"""<div class="{delay_class}" style="background: {background_color}; padding: 1rem; border-radius: 8px; margin-bottom: 0.75rem; border-left: 4px solid {border_color}; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
                        <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem;">
                            {badge_html}
                            <span style="font-size: 0.75rem; color: #6b7280; font-weight: 500;">{dept_de}</span>
                            <span style="font-size: 0.75rem; color: #9ca3af;">•</span>
                            <span style="font-size: 0.75rem; color: #6b7280;">{format_time_ago(alert['timestamp'])}</span>
                        </div>
                        <div style="font-weight: 600; color: #1f2937; font-size: 0.95rem;">
                            {alert['message']}
                        </div>
                    </div>""")
                    with col2:
                        st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
                        if is_acknowledged:
                            st.button("✓ Bestätigt", key=f"ops_ack_{alert['id']}", use_container_width=True, disabled=True)
                        else:
                            if st.button("Bestätigen", key=f"ops_ack_{alert['id']}", use_container_width=True):
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
                <div class="empty-state-icon">🔍</div>
                <div class="empty-state-title">Keine Warnungen gefunden</div>
                <div class="empty-state-text">Keine Warnungen entsprechen den ausgewählten Filtern</div>
            </div>
            """, unsafe_allow_html=True)
    
    # Recommendations Tab
    with tab2:
        st.markdown("### Empfehlungen")
        with spinner_tab2.container():
            st.markdown(render_loading_spinner("Lade Empfehlungen..."), unsafe_allow_html=True)
        
        recommendations_content_placeholder = st.empty()
        
        # Empfehlungen abrufen - verwende Background-Daten für sofortigen Zugriff
        if 'background_data' in st.session_state and st.session_state.background_data:
            recommendations = st.session_state.background_data.get('recommendations', [])
        else:
            recommendations = get_cached_recommendations() if get_cached_recommendations else db.get_pending_recommendations()
        
        # Spinner entfernen
        spinner_tab2.empty()
        
        # German translation for explanation_score (trust level)
        vertrauen_map = {'high': 'hoch', 'medium': 'mittel', 'low': 'niedrig'}
        with recommendations_content_placeholder.container():
            st.markdown("")  # Abstand
            if recommendations:
                for i, rec in enumerate(recommendations):
                    priority_color = get_priority_color(rec['priority'])
                    # German translation for priority
                    priority_de_map = {'high': 'hoch', 'medium': 'mittel', 'low': 'niedrig'}
                    priority_de = priority_de_map.get(rec['priority'], rec['priority'])
                    badge_html = render_badge(priority_de.upper(), rec['priority'])

                    # Impact tags (extract from department and rec_type)
                    impact_tags = []
                    if rec.get('department'):
                        impact_tags.append(rec['department'])
                    if rec.get('rec_type'):
                        # Häufige rec_types ins Deutsche übersetzen
                        rec_type_map = {
                            'capacity': 'Kapazität',
                            'staffing': 'Personal',
                            'inventory': 'Inventar',
                            'general': 'Allgemein',
                        }
                        rec_type = rec['rec_type']
                        impact_tags.append(rec_type_map.get(rec_type, rec_type.replace('_', ' ').title()))

                    # Neues Template-Format verwenden, falls verfügbar, sonst auf altes Format zurückgreifen
                    has_new_format = rec.get('action') and rec.get('reason')

                    if has_new_format:
                        # Build impact tags HTML
                        impact_tags_html = ' '.join([f'<span class="badge" style="background: #e5e7eb; color: #4b5563;">{tag}</span>' for tag in impact_tags])
                        
                        delay_class = "fade-in" if i == 0 else f"fade-in-delayed-{min(i, 3)}" if i <= 3 else "fade-in-delayed-3"
                        st.markdown(f"""
                        <div class="{delay_class}" style="background: white; padding: 1.5rem; border-radius: 8px; margin-bottom: 1rem; border-left: 4px solid {priority_color}; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
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
                            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                                {impact_tags_html}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        # Fallback to old format
                        delay_class = "fade-in" if i == 0 else f"fade-in-delayed-{min(i, 3)}" if i <= 3 else "fade-in-delayed-3"
                        impact_tags_html = ' '.join([f'<span class="badge" style="background: #e5e7eb; color: #4b5563;">{tag}</span>' for tag in impact_tags])
                        
                        st.markdown(f"""
                        <div class="{delay_class}" style="background: white; padding: 1.5rem; border-radius: 8px; margin-bottom: 1rem; border-left: 4px solid {priority_color}; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                            <div style="display: flex; align-items: start; gap: 0.75rem; margin-bottom: 1rem;">
                                {badge_html}
                                <div style="flex: 1;">
                                    <h4 style="margin: 0 0 0.5rem 0; color: #1f2937;">{rec['title']}</h4>
                                    <p style="color: #6b7280; margin: 0; line-height: 1.6;">{rec['description']}</p>
                                </div>
                            </div>
                            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem;">
                                {impact_tags_html}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # Expandable "Why suggested?" section
                    with st.expander("Warum vorgeschlagen?", expanded=False):
                        if has_new_format:
                            # Grund und erwartete Auswirkung aus dem Template verwenden
                            explanation = f"""
                            <strong>Begründung:</strong> {rec.get('reason', 'N/A')}<br><br>
                            <strong>Erwartete Auswirkung:</strong> {rec.get('expected_impact', 'N/A')}<br><br>
                            """
                        else:
                            # Erklärung basierend auf rec_type generieren
                            rec_type = rec.get('rec_type', 'general')
                            explanations = {
                                'capacity': f"Die aktuelle Kapazitätsauslastung in {rec.get('department', 'diesem Bereich')} liegt über dem Schwellenwert. Historische Daten zeigen, dass das Öffnen von Überlaufbetten die Wartezeiten um 15-20% reduziert.",
                                'staffing': f"Die Analyse der Personalauslastung zeigt, dass {rec.get('department', 'dieser Bereich')} eine erhöhte Nachfrage erfährt. Eine Umverteilung kann die Reaktionszeiten verbessern.",
                                'inventory': f"Die Bestände kritischer Materialien in {rec.get('department', 'diesem Bereich')} liegen unter dem Optimum. Jetzt nachbestellen, um Engpässe zu vermeiden.",
                                'general': f"Die KI-Analyse der aktuellen Kennzahlen und Trends in {rec.get('department', 'diesem Bereich')} empfiehlt diese Maßnahme zur Optimierung des Betriebs."
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
                            key=f"ops_action_{rec['id']}",
                            placeholder="Bitte ergreifende Maßnahme oder Ablehnungsgrund eingeben"
                        )
                    with col2:
                        st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
                        accept_clicked = st.button("✅ Annehmen", key=f"ops_accept_{rec['id']}", use_container_width=True)
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
                                st.cache_data.clear()  # Cache leeren nach wichtiger Aktion
                                st.success("✅ Empfehlung angenommen")
                                st.rerun()
                            else:
                                st.warning("⚠️ Bitte Maßnahme eingeben")
                    with col3:
                        st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
                        reject_clicked = st.button("❌ Ablehnen", key=f"ops_reject_{rec['id']}", use_container_width=True)
                        if reject_clicked:
                            if action_text:
                                db.reject_recommendation(rec['id'], action_text)
                                st.cache_data.clear()  # Cache leeren nach wichtiger Aktion
                                st.info("❌ Empfehlung abgelehnt")
                                st.rerun()
                            else:
                                st.warning("⚠️ Bitte Ablehnungsgrund eingeben")
                    
                    st.markdown("---")
            else:
                st.markdown("""
            <div class="empty-state">
                <div class="empty-state-icon">✅</div>
                <div class="empty-state-title">Keine ausstehenden Empfehlungen</div>
                <div class="empty-state-text">Alle Empfehlungen wurden überprüft</div>
            </div>
            """, unsafe_allow_html=True)
    
    # Audit Tab
    with tab3:
        st.markdown("### Prüfprotokoll")
        with spinner_tab3.container():
            st.markdown(render_loading_spinner("Lade Protokoll..."), unsafe_allow_html=True)
        
        audit_content_placeholder = st.empty()
        
        # Filter - verwende Background-Daten für sofortigen Zugriff
        if 'background_data' in st.session_state and st.session_state.background_data:
            audit_log = st.session_state.background_data.get('audit_log', [])
        else:
            audit_log = _get_audit_log_cached(db, 100)  # Fallback: Gecacht
        
        # Spinner entfernen
        spinner_tab3.empty()
        
        with audit_content_placeholder.container():
            st.markdown("")  # Abstand
            
            # Refresh button to clear old data
            col_btn1, col_btn2 = st.columns([1, 5])
            with col_btn1:
                if st.button("🔄 Aktualisieren", use_container_width=True):
                    st.cache_data.clear()  # Cache leeren bei manueller Aktualisierung
                    st.rerun()
            
            st.markdown("")  # Abstand
        
        # Translation maps for dropdowns
        role_map_filter = {
            'system': 'System',
            'nurse': 'Pflegekraft',
            'doctor': 'Arzt/Ärztin',
            'admin': 'Leitung',
            'manager': 'Manager',
            'staff': 'Personal',
            'user': 'Benutzer',
        }
        action_map_filter = {
            'alert_acknowledged': 'Warnung bestätigt',
            'recommendation_accepted': 'Empfehlung angenommen',
            'recommendation_rejected': 'Empfehlung abgelehnt',
        }
        entity_map_filter = {
            'alert': 'Warnung',
            'recommendation': 'Empfehlung',
            'capacity': 'Kapazität',
            'transport': 'Transport',
            'inventory': 'Inventar',
            'device': 'Gerät',
            'patient': 'Patient',
        }

        col1, col2, col3 = st.columns(3)

        with col1:
            # Get unique roles and translate them
            unique_roles = sorted(list(set([a.get('user_role', 'system') for a in audit_log if a.get('user_role')])))
            roles_de = [role_map_filter.get(r, r.title()) for r in unique_roles]
            role_reverse_map = dict(zip(roles_de, unique_roles))
            roles_de_display = ["Alle"] + roles_de
            selected_role_de = st.selectbox("Rolle", roles_de_display, key="ops_audit_role")
            selected_role_audit = None if selected_role_de == "Alle" else role_reverse_map.get(selected_role_de, selected_role_de)

        with col2:
            # Get unique actions and translate them
            unique_actions = sorted(list(set([a.get('action_type', '') for a in audit_log if a.get('action_type')])))
            actions_de = [action_map_filter.get(act, act.replace('_', ' ').title()) for act in unique_actions]
            action_reverse_map = dict(zip(actions_de, unique_actions))
            actions_de_display = ["Alle"] + actions_de
            selected_action_de = st.selectbox("Aktion", actions_de_display, key="ops_audit_action")
            selected_action = None if selected_action_de == "Alle" else action_reverse_map.get(selected_action_de, selected_action_de)

        with col3:
            # Get unique entity types and translate them
            unique_entities = sorted(list(set([a.get('entity_type', '') for a in audit_log if a.get('entity_type')])))
            entities_de = [entity_map_filter.get(ent, ent.title()) for ent in unique_entities]
            entity_reverse_map = dict(zip(entities_de, unique_entities))
            entities_de_display = ["Alle"] + entities_de
            selected_area_de = st.selectbox("Bereich", entities_de_display, key="ops_audit_area")
            selected_area_audit = None if selected_area_de == "Alle" else entity_reverse_map.get(selected_area_de, selected_area_de)

        st.markdown("")  # Abstand
        
        # Filter anwenden
        filtered_audit = audit_log
        if selected_role_audit is not None:
            filtered_audit = [a for a in filtered_audit if a.get('user_role') == selected_role_audit]
        if selected_action is not None:
            filtered_audit = [a for a in filtered_audit if a.get('action_type') == selected_action]
        if selected_area_audit is not None:
            filtered_audit = [a for a in filtered_audit if a.get('entity_type') == selected_area_audit]
        
        # Als Tabelle anzeigen
        if filtered_audit:
            # Tabelle mit deutschen Spaltenüberschriften vorbereiten
            # Deutsche Übersetzungen für Rollen und Aktionen (case-insensitive)
            role_map = {
                'system': 'System',
                'nurse': 'Pflegekraft',
                'doctor': 'Arzt/Ärztin',
                'admin': 'Leitung',
                'manager': 'Manager',
                'staff': 'Personal',
                'user': 'Benutzer',
            }
            action_map = {
                'alert acknowledged': 'Warnung bestätigt',
                'alert_acknowledged': 'Warnung bestätigt',
                'acknowledge alert': 'Warnung bestätigt',
                'acknowledge_alert': 'Warnung bestätigt',
                'recommendation accepted': 'Empfehlung angenommen',
                'recommendation_accepted': 'Empfehlung angenommen',
                'accept recommendation': 'Empfehlung angenommen',
                'accept_recommendation': 'Empfehlung angenommen',
                'recommendation rejected': 'Empfehlung abgelehnt',
                'recommendation_rejected': 'Empfehlung abgelehnt',
                'reject recommendation': 'Empfehlung abgelehnt',
                'reject_recommendation': 'Empfehlung abgelehnt',
                'update': 'Aktualisiert',
                'create': 'Erstellt',
                'delete': 'Gelöscht',
                'view': 'Angesehen',
                'modify': 'Geändert',
            }
            entity_map = {
                'alert': 'Warnung',
                'recommendation': 'Empfehlung',
                'capacity': 'Kapazität',
                'transport': 'Transport',
                'inventory': 'Inventar',
                'device': 'Gerät',
                'patient': 'Patient',
            }
            dept_map = get_department_name_mapping()
            dept_map.update({
                'ER': 'Notaufnahme',
                'ED': 'Notaufnahme',
                'General Ward': 'Allgemeinstation',
                'Neurology': 'Neurologie',
                'Pediatrics': 'Pädiatrie',
                'Oncology': 'Onkologie',
                'Maternity': 'Geburtshilfe',
                'Radiology': 'Radiologie',
            })
            
            table_data = []
            for entry in filtered_audit:
                role = entry.get('user_role', 'system').lower().strip()
                action = entry.get('action_type', '').lower().strip().replace('_', ' ')
                entity = entry.get('entity_type', 'N/A').lower().strip()
                
                # Extract department from details if available
                details = entry.get('details', '')
                department = ''
                # Look for department in details
                for dept_key, dept_val in dept_map.items():
                    if dept_key in details:
                        department = f" ({dept_val})"
                        break
                
                table_data.append({
                    "Zeit": format_time_ago(entry['timestamp']),
                    "Rolle": role_map.get(role, entry.get('user_role', 'System').title()),
                    "Aktion": action_map.get(action, entry.get('action_type', 'N/A').replace('_', ' ').title()),
                    "Bereich": entity_map.get(entity, entry.get('entity_type', 'N/A').title()),
                    "Details": (details[:50] + "..." if details and len(details) > 50 else details) + department
                })
            
            df_audit = pd.DataFrame(table_data)
            st.dataframe(
                df_audit,
                use_container_width=True,
                hide_index=True,
                height=400
            )

        else:
            st.info("Keine Protokolleinträge gefunden")

