"""
Seitenmodul für Gerätewartung
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
    get_explanation_score_color, get_maintenance_duration, convert_utc_to_local
)
from ui.components import render_badge, render_empty_state


@st.cache_data(ttl=60)
def _get_device_maintenance_urgencies_cached(_db):
    """Gecachte Geräte-Wartungsdringlichkeiten"""
    return _db.get_device_maintenance_urgencies()

def render(db, sim, get_cached_alerts=None, get_cached_recommendations=None, get_cached_capacity=None):
    """Rendert die Gerätewartung-Seite"""
    st.markdown("### Gerätewartungs-Dringlichkeitsanalyse")
    
    # Verwende Background-Daten für sofortigen Zugriff
    if 'background_data' in st.session_state and st.session_state.background_data:
        devices = st.session_state.background_data.get('devices', [])
        # Fallback wenn Liste leer ist
        if not devices:
            devices = _get_device_maintenance_urgencies_cached(db)
    else:
        devices = _get_device_maintenance_urgencies_cached(db)  # Fallback: Gecacht
    
    if devices:
        # Dringlichkeitszusammenfassung
        high_urgency = len([d for d in devices if d['urgency_level'] in ['high', 'hoch']])
        medium_urgency = len([d for d in devices if d['urgency_level'] in ['medium', 'mittel']])

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Geräte mit hoher Dringlichkeit", high_urgency, delta=None)
        with col2:
            st.metric("Geräte mit mittlerer Dringlichkeit", medium_urgency, delta=None)
        with col3:
            st.metric("Gesamtanzahl Geräte", len(devices))

        st.markdown("---")
        
        # Teile Geräte in zwei Gruppen: mit geplanter Wartung und ohne
        devices_with_scheduled = []
        devices_without_scheduled = []
        
        for device in devices:
            scheduled_maintenance = device.get('scheduled_maintenance_time')
            # SQLite gibt BOOLEAN als INTEGER (0/1) zurück, daher explizite Prüfung
            maintenance_confirmed = device.get('maintenance_confirmed', False)
            maintenance_confirmed = bool(maintenance_confirmed) if maintenance_confirmed is not None else False
            
            # Prüfe ob scheduled_maintenance nicht None/leer ist UND maintenance_confirmed True ist
            if scheduled_maintenance and scheduled_maintenance != '' and maintenance_confirmed:
                devices_with_scheduled.append(device)
            else:
                devices_without_scheduled.append(device)
        
        # Mapping für Gerätetypen ins Deutsche
        device_type_map = {
            'Imaging': 'Bildgebung',
            'Life Support': 'Lebensunterstützung',
            'Emergency': 'Notfall',
            'Monitoring': 'Überwachung',
            'Therapy': 'Therapie',
            'Surgical': 'Chirurgisch',
            'Diagnostic': 'Diagnostik',
            'Other': 'Andere',
        }
        # Mapping für Dringlichkeitsstufen ins Deutsche
        urgency_level_map = {'high': 'hoch', 'medium': 'mittel', 'low': 'niedrig', 'hoch': 'hoch', 'mittel': 'mittel', 'niedrig': 'niedrig'}
        urgency_label_map = {'hoch': 'HOCHE DRINGLICHKEIT', 'mittel': 'MITTLERE DRINGLICHKEIT', 'niedrig': 'GERINGE DRINGLICHKEIT'}
        
        # Importiere Dringlichkeitsberechnung und max hours
        from utils import get_max_usage_hours
        
        # Mapping für Abteilungsnamen ins Deutsche - verwende zentrales Mapping
        from utils import get_department_name_mapping
        department_map = get_department_name_mapping()
        department_map.update({
            'Radiology': 'Radiologie',
            'General Ward': 'Allgemeinstation',
            'Neurology': 'Neurologie',
            'Pediatrics': 'Pädiatrie',
            'Oncology': 'Onkologie',
            'Maternity': 'Geburtshilfe',
            'Other': 'Andere',
        })
        
        # Hilfsfunktion zum Rendern eines Geräts
        def render_device_card(device):
            # Berechne days_until_due aus next_maintenance_due
            days_until_due = None
            if device.get('next_maintenance_due'):
                try:
                    if isinstance(device['next_maintenance_due'], str):
                        next_due = datetime.strptime(device['next_maintenance_due'], '%Y-%m-%d')
                    else:
                        next_due = device['next_maintenance_due']
                    days_until_due = (next_due - datetime.now()).days
                except:
                    days_until_due = None
            
            # Berechne Tage seit letzter Wartung
            days_since_last = None
            last_maintenance_str = None
            if device.get('last_maintenance'):
                try:
                    if isinstance(device['last_maintenance'], str):
                        last_maintenance_date = datetime.strptime(device['last_maintenance'], '%Y-%m-%d')
                    else:
                        last_maintenance_date = device['last_maintenance']
                    days_since_last = (datetime.now() - last_maintenance_date).days
                    last_maintenance_str = last_maintenance_date.strftime('%d.%m.%Y')
                except:
                    pass
            
            # Betriebszeit seit letzter Wartung
            usage_hours = device.get('usage_hours', 0)
            max_usage_hours = get_max_usage_hours(device.get('device_type', ''))
            usage_hours_display = f"{usage_hours:,} h"
            if max_usage_hours > 0:
                usage_hours_display += f" / {max_usage_hours:,} h"
            
            # Berechne empfohlenes Wartungsfenster basierend auf days_until_due
            if days_until_due is not None:
                if days_until_due < 0:
                    recommended_window = 'Überfällig'
                elif days_until_due <= 3:
                    recommended_window = 'Innerhalb von 3 Tagen'
                elif days_until_due <= 7:
                    recommended_window = 'Innerhalb von 1 Woche'
                elif days_until_due <= 14:
                    recommended_window = 'Innerhalb von 2 Wochen'
                elif days_until_due <= 28:
                    recommended_window = 'Innerhalb von 4 Wochen'
                else:
                    recommended_window = 'Bald'
            else:
                recommended_window = 'Nicht verfügbar'
            
            urgency_level_de = urgency_level_map.get(device.get('urgency_level', ''), device.get('urgency_level', ''))
            urgency_color = get_severity_color(urgency_level_de)
            urgency_badge = render_badge(urgency_label_map.get(urgency_level_de, urgency_level_de.upper()), urgency_level_de)
            device_type_de = device_type_map.get(device.get('device_type', ''), device.get('device_type', ''))
            department_de = department_map.get(device.get('department', ''), device.get('department', ''))
            
            days_display = f"{days_until_due} Tage" if days_until_due is not None else "N/V"
            last_maintenance_display = f"{last_maintenance_str} (vor {days_since_last} Tagen)" if last_maintenance_str and days_since_last is not None else (last_maintenance_str if last_maintenance_str else "N/V")
            
            # Prüfe ob Wartung geplant ist oder aktiv ist
            scheduled_maintenance = device.get('scheduled_maintenance_time')
            # SQLite gibt BOOLEAN als INTEGER (0/1) zurück, daher explizite Prüfung
            maintenance_confirmed = device.get('maintenance_confirmed', False)
            maintenance_confirmed = bool(maintenance_confirmed) if maintenance_confirmed is not None else False
            is_in_maintenance = device.get('is_in_maintenance', False)
            maintenance_end_time_str = device.get('maintenance_end_time')
            
            scheduled_display = "Keine"
            scheduled_display_color = "#6b7280"  # Grau für "Keine"
            maintenance_status_badge = ""
            
            if is_in_maintenance:
                # Gerät ist aktuell in Wartung
                scheduled_display = "🔧 In Wartung"
                scheduled_display_color = "#F59E0B"  # Orange für aktive Wartung
                
                # Berechne verbleibende Zeit
                if maintenance_end_time_str:
                    try:
                        from datetime import timezone
                        if isinstance(maintenance_end_time_str, str):
                            maintenance_end_dt = None
                            date_formats = [
                                '%Y-%m-%dT%H:%M:%S.%f',
                                '%Y-%m-%dT%H:%M:%S',
                                '%Y-%m-%d %H:%M:%S.%f',
                                '%Y-%m-%d %H:%M:%S',
                                '%Y-%m-%d %H:%M',
                                '%Y-%m-%dT%H:%M'
                            ]
                            for fmt in date_formats:
                                try:
                                    maintenance_end_dt = datetime.strptime(maintenance_end_time_str, fmt)
                                    if maintenance_end_dt.tzinfo is None:
                                        maintenance_end_dt = maintenance_end_dt.replace(tzinfo=timezone.utc)
                                    break
                                except:
                                    continue
                            
                            if maintenance_end_dt is None:
                                try:
                                    maintenance_end_dt = datetime.fromisoformat(maintenance_end_time_str.replace('Z', '+00:00'))
                                    if maintenance_end_dt.tzinfo is None:
                                        maintenance_end_dt = maintenance_end_dt.replace(tzinfo=timezone.utc)
                                except:
                                    maintenance_end_dt = None
                        else:
                            maintenance_end_dt = maintenance_end_time_str
                            if maintenance_end_dt and maintenance_end_dt.tzinfo is None:
                                maintenance_end_dt = maintenance_end_dt.replace(tzinfo=timezone.utc)
                        
                        if maintenance_end_dt:
                            now_utc = datetime.now(timezone.utc)
                            remaining_seconds = (maintenance_end_dt - now_utc).total_seconds()
                            if remaining_seconds > 0:
                                remaining_hours = int(remaining_seconds // 3600)
                                remaining_minutes = int((remaining_seconds % 3600) // 60)
                                if remaining_hours > 0:
                                    remaining_time_str = f"{remaining_hours}h {remaining_minutes}m"
                                else:
                                    remaining_time_str = f"{remaining_minutes}m"
                                scheduled_display = f"🔧 In Wartung ({remaining_time_str})"
                    except:
                        pass
                
                maintenance_status_badge = render_badge("IN WARTUNG", "wartung")
            elif scheduled_maintenance and maintenance_confirmed:
                scheduled_dt = None
                # Versuche verschiedene Datumsformate zu parsen
                if isinstance(scheduled_maintenance, str):
                    # Versuche verschiedene Formate
                    date_formats = [
                        '%Y-%m-%d %H:%M:%S',
                        '%Y-%m-%d %H:%M',
                        '%Y-%m-%dT%H:%M:%S',
                        '%Y-%m-%dT%H:%M:%S.%f',
                        '%Y-%m-%d'
                    ]
                    for fmt in date_formats:
                        try:
                            scheduled_dt = datetime.strptime(scheduled_maintenance, fmt)
                            break
                        except:
                            continue
                else:
                    scheduled_dt = scheduled_maintenance
                
                if scheduled_dt:
                    # Konvertiere UTC zu lokaler Zeit für Anzeige
                    scheduled_dt_local = convert_utc_to_local(scheduled_dt)
                    if scheduled_dt_local:
                        scheduled_dt = scheduled_dt_local
                    hours_until_scheduled = (scheduled_dt - datetime.now()).total_seconds() / 3600
                    if hours_until_scheduled < 0:
                        scheduled_display = f"⚠️ {scheduled_dt.strftime('%d.%m.%Y %H:%M')}"
                        scheduled_display_color = "#DC2626"  # Rot für überfällig
                    elif hours_until_scheduled < 24:
                        scheduled_display = f"Heute {scheduled_dt.strftime('%H:%M')}"
                        scheduled_display_color = "#F59E0B"  # Orange für heute
                    else:
                        scheduled_display = scheduled_dt.strftime('%d.%m.%Y %H:%M')
                        scheduled_display_color = "#667eea"  # Blau für geplant
                else:
                    # Falls Parsing komplett fehlschlägt, zeige den rohen Wert
                    scheduled_display = str(scheduled_maintenance)
                    scheduled_display_color = "#667eea"
            
            # Baue HTML-Content ohne verschachtelte f-Strings
            html_content = (
                f'<div style="background: white; padding: 1rem; border-radius: 8px; margin-bottom: 0.75rem; border-left: 4px solid {urgency_color}; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">'
                f'<div style="display: grid; grid-template-columns: 1.5fr 1fr 1fr 1fr 1fr 1fr 1fr 1fr; gap: 1rem; align-items: center;">'
                f'<div>'
                f'<div style="font-weight: 600; color: #1f2937; margin-bottom: 0.25rem; display: flex; align-items: center; gap: 0.5rem;">{device.get("device_type", "N/V")} {maintenance_status_badge}</div>'
                f'<div style="font-size: 0.75rem; color: #6b7280;">{device.get("device_id", "N/V")} • {department_de}</div>'
                f'</div>'
                f'<div>'
                f'<div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.25rem;">Gerätetyp</div>'
                f'<div style="font-weight: 600; color: #1f2937;">{device_type_de}</div>'
                f'</div>'
                f'<div>'
                f'<div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.25rem;">Letzte Wartung</div>'
                f'<div style="font-weight: 600; color: #1f2937; font-size: 0.875rem;">{last_maintenance_display}</div>'
                f'</div>'
                f'<div>'
                f'<div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.25rem;">Betriebszeit</div>'
                f'<div style="font-weight: 600; color: #1f2937; font-size: 0.875rem;">{usage_hours_display}</div>'
                f'</div>'
                f'<div>'
                f'<div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.25rem;">Tage bis fällig</div>'
                f'<div style="font-weight: 600; color: {urgency_color};">{days_display}</div>'
                f'</div>'
                f'<div>'
                f'<div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.25rem;">Empfohlenes Wartungsfenster</div>'
                f'<div style="font-weight: 600; color: #667eea; font-size: 0.875rem;">{recommended_window}</div>'
                f'</div>'
                f'<div>'
                f'<div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.25rem;">Geplante Wartung</div>'
                f'<div style="font-weight: 600; color: {scheduled_display_color}; font-size: 0.875rem;">{scheduled_display}</div>'
                f'</div>'
                f'<div>'
                f'{urgency_badge}'
                f'</div>'
                f'</div>'
                f'</div>'
            )
            
            st.markdown(html_content, unsafe_allow_html=True)
            
            # Wartungsplanung-Expander
            device_id = device.get('device_id')
            if not device_id:
                st.error(f"❌ Keine device_id gefunden für Gerät: {device}")
            else:
                with st.expander(f"🔧 Wartung planen: {device_id}", expanded=False):
                    # Hole Vorschläge
                    if st.button("💡 Zeiten vorschlagen", key=f"suggest_{device_id}"):
                        with st.spinner("Berechne optimale Wartungszeiten..."):
                            suggestions = db.suggest_optimal_maintenance_times(device_id, max_suggestions=5)
                            st.session_state[f'suggestions_{device_id}'] = suggestions
                    
                    # Zeige Vorschläge falls vorhanden
                    if f'suggestions_{device_id}' in st.session_state:
                        suggestions = st.session_state[f'suggestions_{device_id}']
                        if suggestions:
                            st.markdown("#### 💡 Vorgeschlagene Zeiten")
                            for idx, suggestion in enumerate(suggestions):
                                start_time = suggestion['start_time']
                                end_time = suggestion['end_time']
                                score = suggestion['score']
                                expected_patients = suggestion['expected_patients']
                                reason = suggestion['reason']
                                
                                # Konvertiere UTC zu lokaler Zeit für Anzeige
                                start_time_local = convert_utc_to_local(start_time)
                                end_time_local = convert_utc_to_local(end_time)
                                if start_time_local:
                                    start_time = start_time_local
                                if end_time_local:
                                    end_time = end_time_local
                                
                                # Score-Farbe
                                if score >= 0.8:
                                    score_color = "#10B981"  # Grün
                                elif score >= 0.6:
                                    score_color = "#F59E0B"  # Orange
                                else:
                                    score_color = "#6B7280"  # Grau
                                
                                col1, col2, col3 = st.columns([2, 1, 1])
                                with col1:
                                    st.markdown(f"""
                                    **{start_time.strftime('%d.%m.%Y %H:%M')} - {end_time.strftime('%H:%M')}**  
                                    📊 Erwartete Patienten: {expected_patients:.1f}  
                                    💡 {reason}
                                    """)
                                with col2:
                                    st.markdown(f"""
                                    <div style="text-align: center; padding: 0.5rem; background: {score_color}20; border-radius: 4px;">
                                        <div style="font-size: 0.75rem; color: #6b7280;">Score</div>
                                        <div style="font-weight: 600; color: {score_color}; font-size: 1.25rem;">{score:.2f}</div>
                                    </div>
                                    """, unsafe_allow_html=True)
                                with col3:
                                    if st.button("✅ Auswählen", key=f"select_{device_id}_{idx}"):
                                        # Direkt Wartung bestätigen
                                        try:
                                            if not device_id:
                                                st.error("❌ Keine Geräte-ID gefunden!")
                                            else:
                                                with st.spinner("Wartung wird bestätigt..."):
                                                    success, error_msg = db.confirm_maintenance(
                                                        device_id=str(device_id),
                                                        scheduled_time=start_time,
                                                        duration_minutes=int(suggestion['duration_minutes']),
                                                        confirmed_by="System"
                                                    )
                                                    
                                                    if success:
                                                        st.success(f"✅ Wartung bestätigt für {start_time.strftime('%d.%m.%Y %H:%M')}")
                                                        # Lösche Vorschläge und ausgewählte Werte aus Session State
                                                        if f'suggestions_{device_id}' in st.session_state:
                                                            del st.session_state[f'suggestions_{device_id}']
                                                        if f'selected_time_{device_id}' in st.session_state:
                                                            del st.session_state[f'selected_time_{device_id}']
                                                        if f'selected_duration_{device_id}' in st.session_state:
                                                            del st.session_state[f'selected_duration_{device_id}']
                                                        if f'selected_date_{device_id}' in st.session_state:
                                                            del st.session_state[f'selected_date_{device_id}']
                                                        if f'selected_time_input_{device_id}' in st.session_state:
                                                            del st.session_state[f'selected_time_input_{device_id}']
                                                        st.cache_data.clear()  # Cache leeren nach wichtiger Aktion
                                                        st.rerun()
                                                    else:
                                                        error_display = error_msg if error_msg else "Unbekannter Fehler"
                                                        st.error(f"❌ Fehler beim Bestätigen der Wartung für Gerät {device_id}: {error_display}")
                                        except Exception as e:
                                            st.error(f"❌ Fehler: {str(e)}")
                                            with st.expander("🔍 Fehlerdetails anzeigen"):
                                                st.code(str(e))
                                st.markdown("---")
                        else:
                            st.info("Keine Vorschläge verfügbar. Bitte versuchen Sie es später erneut.")
                    
                    # Manuelle Zeitauswahl
                    st.markdown("#### 📅 Manuelle Zeitauswahl")
                
                    # Prüfe ob eine Zeit aus den Vorschlägen ausgewählt wurde
                    if f'selected_date_{device_id}' in st.session_state:
                        default_date = st.session_state[f'selected_date_{device_id}']
                    else:
                        default_date = datetime.now().date() + timedelta(days=1)
                    
                    if f'selected_time_input_{device_id}' in st.session_state:
                        default_time = st.session_state[f'selected_time_input_{device_id}']
                    else:
                        default_time = datetime.now().time().replace(hour=14, minute=0)
                    
                    if f'selected_duration_{device_id}' in st.session_state:
                        default_duration_value = st.session_state[f'selected_duration_{device_id}']
                    else:
                        default_duration_value = get_maintenance_duration(device.get('device_type', ''))
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        selected_date = st.date_input(
                            "Datum",
                            value=default_date,
                            min_value=datetime.now().date(),
                            key=f"date_{device_id}"
                        )
                    
                    with col2:
                        selected_time = st.time_input(
                            "Uhrzeit",
                            value=default_time,
                            key=f"time_{device_id}"
                        )
                    
                    with col3:
                        # Dauer basierend auf Gerätetyp
                        duration_options = {
                            45: "45 Minuten",
                            60: "1 Stunde",
                            90: "1.5 Stunden",
                            120: "2 Stunden",
                            180: "3 Stunden",
                            240: "4 Stunden",
                            300: "5 Stunden"
                        }
                        # Finde den Index für die ausgewählte Dauer
                        duration_index = 2  # Default (90 Minuten)
                        if default_duration_value in duration_options.keys():
                            duration_index = list(duration_options.keys()).index(default_duration_value)
                        else:
                            # Wenn der Wert nicht in den Optionen ist, finde den nächstgelegenen Wert
                            sorted_durations = sorted(duration_options.keys())
                            for i, dur in enumerate(sorted_durations):
                                if dur >= default_duration_value:
                                    duration_index = i
                                    break
                            # Falls alle Werte kleiner sind, nimm den letzten
                            if default_duration_value > max(sorted_durations):
                                duration_index = len(sorted_durations) - 1
                        
                        selected_duration = st.selectbox(
                            "Dauer",
                            options=list(duration_options.keys()),
                            index=duration_index,
                            format_func=lambda x: duration_options.get(x, f"{x} Minuten"),
                            key=f"duration_{device_id}"
                        )
                    
                    # Bestätigungs-Button
                    selected_datetime = datetime.combine(selected_date, selected_time)
                    if selected_datetime <= datetime.now():
                        st.warning("⚠️ Bitte wählen Sie eine zukünftige Zeit.")
                    else:
                        if st.button("✅ Wartung bestätigen", key=f"confirm_{device_id}", type="primary"):
                            try:
                                # Validiere Eingaben
                                if not device_id:
                                    st.error("❌ Keine Geräte-ID gefunden!")
                                    st.stop()
                                
                                if selected_datetime <= datetime.now():
                                    st.error("❌ Bitte wählen Sie eine zukünftige Zeit!")
                                    st.stop()
                                
                                with st.spinner("Wartung wird bestätigt..."):
                                    try:
                                        success, error_msg = db.confirm_maintenance(
                                            device_id=str(device_id),
                                            scheduled_time=selected_datetime,
                                            duration_minutes=int(selected_duration),
                                            confirmed_by="System"
                                        )
                                        
                                        if success:
                                            st.success(f"✅ Wartung bestätigt für {selected_datetime.strftime('%d.%m.%Y %H:%M')}")
                                            # Lösche Vorschläge und ausgewählte Werte aus Session State
                                            if f'suggestions_{device_id}' in st.session_state:
                                                del st.session_state[f'suggestions_{device_id}']
                                            if f'selected_time_{device_id}' in st.session_state:
                                                del st.session_state[f'selected_time_{device_id}']
                                            if f'selected_duration_{device_id}' in st.session_state:
                                                del st.session_state[f'selected_duration_{device_id}']
                                            if f'selected_date_{device_id}' in st.session_state:
                                                del st.session_state[f'selected_date_{device_id}']
                                            if f'selected_time_input_{device_id}' in st.session_state:
                                                del st.session_state[f'selected_time_input_{device_id}']
                                            st.cache_data.clear()  # Cache leeren nach wichtiger Aktion
                                            st.rerun()
                                        else:
                                            error_display = error_msg if error_msg else "Unbekannter Fehler"
                                            st.error(f"❌ Fehler beim Bestätigen der Wartung für Gerät {device_id}: {error_display}")
                                    except Exception as e:
                                        st.error(f"❌ Ausnahme beim Bestätigen: {str(e)}")
                                        with st.expander("🔍 Fehlerdetails anzeigen"):
                                            st.code(str(e))
                            except Exception as e:
                                st.error(f"❌ Fehler: {str(e)}")
                                with st.expander("🔍 Fehlerdetails anzeigen"):
                                    st.code(str(e))
                    
                    # Falls Wartung bereits geplant ist, zeige Option zum Abschließen
                    # SQLite gibt BOOLEAN als INTEGER (0/1) zurück, daher explizite Prüfung
                    maintenance_confirmed_check = device.get('maintenance_confirmed', False)
                    maintenance_confirmed_check = bool(maintenance_confirmed_check) if maintenance_confirmed_check is not None else False
                    if scheduled_maintenance and maintenance_confirmed_check:
                        st.markdown("---")
                        st.markdown("#### ✅ Wartung abschließen")
                        if st.button("🏁 Wartung als abgeschlossen markieren", key=f"complete_{device_id}"):
                            success = db.complete_maintenance(device_id)
                            if success:
                                st.success("✅ Wartung als abgeschlossen markiert. Neue Wartungsintervalle wurden berechnet.")
                                st.cache_data.clear()  # Cache leeren nach wichtiger Aktion
                                st.rerun()
                            else:
                                st.error("❌ Fehler beim Abschließen der Wartung.")
        
        # Zeige zuerst Geräte mit geplanter Wartung
        if devices_with_scheduled:
            st.markdown("#### 📅 Geräte mit geplanter Wartung")
            st.markdown("")  # Abstand
            for device in devices_with_scheduled:
                render_device_card(device)
        
        # Dann Geräte ohne geplante Wartung
        if devices_without_scheduled:
            if devices_with_scheduled:
                st.markdown("---")
            st.markdown("#### ⚠️ Geräte ohne geplante Wartung")
            st.markdown("")  # Abstand
            for device in devices_without_scheduled:
                render_device_card(device)
        
        # Dringlichkeitsverteilung chart
        st.markdown("---")
        st.markdown("### Dringlichkeitsverteilung")
        df_dev = pd.DataFrame(devices)
        urgency_counts = df_dev['urgency_level'].value_counts()
        
        # Map German urgency levels to display names for pie chart
        urgency_label_map_chart = {'high': 'Hoch', 'medium': 'Mittel', 'low': 'Niedrig', 'hoch': 'Hoch', 'mittel': 'Mittel', 'niedrig': 'Niedrig'}
        urgency_display_names = [urgency_label_map_chart.get(name, name) for name in urgency_counts.index]
        
        fig = px.pie(
            values=urgency_counts.values,
            names=urgency_display_names,
            color=urgency_counts.index,
            color_discrete_map={
                'high': '#DC2626',
                'medium': '#F59E0B',
                'low': '#10B981',
                'hoch': '#DC2626',
                'mittel': '#F59E0B',
                'niedrig': '#10B981'
            }
        )
        fig.update_layout(
            height=300,
            showlegend=True,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.markdown(render_empty_state("🔧", "Keine Gerätedaten verfügbar", "Es wurden noch keine Geräte in der Datenbank hinterlegt. Die Geräte werden automatisch beim nächsten App-Start generiert, falls sie fehlen."), unsafe_allow_html=True)
