"""
Seitenmodul für Transport
"""
import streamlit as st
import random
import time
from datetime import datetime, timedelta, timezone, date, time as dt_time
from zoneinfo import ZoneInfo
from utils import (
    format_time_ago, get_severity_color, get_priority_color, get_risk_color,
    get_status_color, calculate_inventory_status, calculate_capacity_status,
    format_duration_minutes, get_department_color, get_system_status,
    get_metric_severity_for_load, get_metric_severity_for_count, get_metric_severity_for_free,
    get_explanation_score_color, convert_utc_to_local, LOCAL_TIMEZONE
)
from ui.components import render_badge, render_empty_state, render_loading_spinner


@st.cache_data(ttl=30)
def _get_transport_requests_cached(_db):
    """Gecachte Transportanfragen"""
    return _db.get_transport_requests()


def _update_transport_statuses(db):
    """
    Aktualisiert Transport-Statuses periodisch.
    Aktiviert geplante Transporte und schließt aktive Transporte ab.
    Batch-Update für bessere Performance.
    """
    transport = _get_transport_requests_cached(db)
    now = datetime.now(timezone.utc)
    updates_made = False
    
    # Batch: Sammle alle zu aktualisierenden Transporte
    transports_to_activate = []
    transports_to_complete = []
    transports_to_delay = []
    
    # 1. Sammle geplante Transporte, die aktiviert werden müssen
    for trans in transport:
        if trans.get('status') == 'planned':
            planned_start_time_str = trans.get('planned_start_time')
            if planned_start_time_str:
                try:
                    if isinstance(planned_start_time_str, str):
                        planned_start_time = datetime.fromisoformat(planned_start_time_str.replace('Z', '+00:00'))
                    else:
                        planned_start_time = planned_start_time_str
                    
                    if planned_start_time <= now:
                        estimated_time = trans.get('estimated_time_minutes', 15)
                        expected_completion = now + timedelta(minutes=estimated_time)
                        delay_minutes = 0
                        
                        # 10% Chance auf Verzögerung beim Aktivieren
                        if random.random() < 0.10:
                            delay_percentage = random.uniform(0.2, 0.5)
                            delay_minutes = int(estimated_time * delay_percentage)
                            expected_completion = expected_completion + timedelta(minutes=delay_minutes)
                        
                        transports_to_activate.append({
                            'id': trans['id'],
                            'expected_completion': expected_completion.isoformat(),
                            'delay_minutes': delay_minutes
                        })
                except Exception:
                    pass
    
    # 2. Sammle aktive Transporte, die aktualisiert/abgeschlossen werden müssen
    for trans in transport:
        if trans.get('status') in ['in_progress', 'in_bearbeitung']:
            expected_completion_time_str = trans.get('expected_completion_time')
            start_time_str = trans.get('start_time')
            
            if expected_completion_time_str and start_time_str:
                try:
                    if isinstance(expected_completion_time_str, str):
                        expected_completion_time = datetime.fromisoformat(expected_completion_time_str.replace('Z', '+00:00'))
                    else:
                        expected_completion_time = expected_completion_time_str
                    
                    # Prüfe auf Verzögerung während der Fahrt
                    delay_minutes = trans.get('delay_minutes', 0) or 0
                    if delay_minutes == 0 and random.random() < 0.10:
                        estimated_time = trans.get('estimated_time_minutes', 15)
                        delay_percentage = random.uniform(0.2, 0.5)
                        delay_minutes = int(estimated_time * delay_percentage)
                        expected_completion_time = expected_completion_time + timedelta(minutes=delay_minutes)
                        
                        transports_to_delay.append({
                            'id': trans['id'],
                            'expected_completion_time': expected_completion_time.isoformat(),
                            'delay_minutes': delay_minutes
                        })
                    
                    # Prüfe ob Transport abgeschlossen werden muss
                    if expected_completion_time <= now:
                        if isinstance(start_time_str, str):
                            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                        else:
                            start_time = start_time_str
                        
                        actual_time_minutes = int((now - start_time).total_seconds() / 60)
                        
                        transports_to_complete.append({
                            'id': trans['id'],
                            'actual_time_minutes': actual_time_minutes
                        })
                except Exception:
                    pass
    
    # Batch: Führe alle Updates aus
    for trans_data in transports_to_activate:
        try:
            transport_id = trans_data['id']
            # Hole Transport-Details um zu prüfen ob es ein Inventar-Transport ist
            transport = next((t for t in transport if t['id'] == transport_id), None)
            
            update_kwargs = {
                'status': 'in_progress',
                'start_time': now.isoformat(),
                'expected_completion_time': trans_data['expected_completion']
            }
            if trans_data['delay_minutes'] > 0:
                update_kwargs['delay_minutes'] = trans_data['delay_minutes']
            
            if db.update_transport_status(transport_id, **update_kwargs):
                updates_made = True
                
                # Wenn es ein Inventar-Transport ist, setze Bestellstatus auf 'in_transit'
                if transport and transport.get('related_entity_type') == 'inventory_order':
                    try:
                        order_id = transport.get('related_entity_id')
                        if order_id:
                            db.update_inventory_order_status(order_id, 'in_transit')
                    except Exception:
                        pass  # Fehler ignorieren, um UI nicht zu blockieren
        except Exception:
            pass
    
    for trans_data in transports_to_delay:
        try:
            if db.update_transport_status(
                trans_data['id'],
                expected_completion_time=trans_data['expected_completion_time'],
                delay_minutes=trans_data['delay_minutes']
            ):
                updates_made = True
        except Exception:
            pass
    
    for trans_data in transports_to_complete:
        try:
            transport_id = trans_data['id']
            # Hole Transport-Details um zu prüfen ob es ein Inventar-Transport ist
            transport = next((t for t in transport if t['id'] == transport_id), None)
            
            if db.update_transport_status(
                transport_id,
                status='completed',
                actual_time_minutes=trans_data['actual_time_minutes']
            ):
                updates_made = True
                
                # Wenn es ein Inventar-Transport ist, verarbeite die Lieferung
                if transport and transport.get('related_entity_type') == 'inventory_order':
                    try:
                        db.process_completed_inventory_transport(transport_id)
                    except Exception:
                        pass  # Fehler ignorieren, um UI nicht zu blockieren
        except Exception:
            pass
    
    # Cache nur einmal invalidieren wenn Updates gemacht wurden
    if updates_made:
        _get_transport_requests_cached.clear()
    
    return updates_made


def _show_schedule_dialog(trans, db, sim, is_edit=False):
    """Zeigt Dialog zum Planen/Bearbeiten eines Transportes"""
    transport_id = trans['id']
    dialog_key = f"schedule_dialog_{transport_id}"
    
    # Initialisiere Session State für Dialog
    if dialog_key not in st.session_state:
        st.session_state[dialog_key] = False
    
    # Wenn Dialog geöffnet ist, zeige Formular
    if st.session_state[dialog_key]:
        with st.form(key=f"schedule_form_{transport_id}"):
            st.markdown("### " + ("Transport bearbeiten" if is_edit else "Transport planen"))
            
            # Bestimme Standardwerte
            now_utc = datetime.now(timezone.utc)
            now_local = convert_utc_to_local(now_utc)
            
            # Wenn bearbeitet wird, verwende geplante Zeit (konvertiere von UTC zu lokaler Zeit)
            if is_edit and trans.get('planned_start_time'):
                try:
                    if isinstance(trans['planned_start_time'], str):
                        planned_time_utc = datetime.fromisoformat(trans['planned_start_time'].replace('Z', '+00:00'))
                    else:
                        planned_time_utc = trans['planned_start_time']
                        if planned_time_utc.tzinfo is None:
                            planned_time_utc = planned_time_utc.replace(tzinfo=timezone.utc)
                    
                    # Konvertiere UTC zu lokaler Zeit für Anzeige
                    planned_time_local = convert_utc_to_local(planned_time_utc)
                    if planned_time_local:
                        default_date = planned_time_local.date()
                        default_time = planned_time_local.time()
                    else:
                        raise ValueError("Konvertierung fehlgeschlagen")
                except Exception as e:
                    # Fallback: Verwende aktuelle lokale Zeit
                    default_date = now_local.date()
                    default_time = now_local.time()
            # Wenn Wunschzeitfenster vorhanden, verwende Mitte davon
            elif trans.get('requested_time_start') and trans.get('requested_time_end'):
                try:
                    # Parse Wunschzeitfenster (Format: "HH:MM")
                    start_parts = trans['requested_time_start'].split(':')
                    end_parts = trans['requested_time_end'].split(':')
                    start_hour = int(start_parts[0])
                    start_min = int(start_parts[1]) if len(start_parts) > 1 else 0
                    end_hour = int(end_parts[0])
                    end_min = int(end_parts[1]) if len(end_parts) > 1 else 0
                    
                    # Berechne Mitte des Zeitfensters
                    start_minutes = start_hour * 60 + start_min
                    end_minutes = end_hour * 60 + end_min
                    mid_minutes = (start_minutes + end_minutes) // 2
                    mid_hour = mid_minutes // 60
                    mid_min = mid_minutes % 60
                    
                    default_date = now_local.date()
                    default_time = dt_time(mid_hour, mid_min)
                except Exception as e:
                    default_date = now_local.date()
                    default_time = now_local.time()
            # Sonst berechne über Simulation
            else:
                estimated_time = trans.get('estimated_time_minutes', 15)
                planned_start_time_utc = sim.calculate_planned_start_time(estimated_time_minutes=estimated_time)
                
                # Konvertiere UTC zu lokaler Zeit für Anzeige
                planned_start_time_local = convert_utc_to_local(planned_start_time_utc)
                if planned_start_time_local:
                    default_date = planned_start_time_local.date()
                    default_time = planned_start_time_local.time()
                else:
                    default_date = now_local.date()
                    default_time = now_local.time()
            
            # Formularfelder
            col1, col2 = st.columns(2)
            with col1:
                selected_date = st.date_input("Datum", value=default_date, key=f"date_{transport_id}")
            with col2:
                selected_time = st.time_input("Uhrzeit", value=default_time, key=f"time_{transport_id}")
            
            estimated_time = st.number_input(
                "Dauer (Minuten)",
                min_value=5,
                max_value=300,
                value=trans.get('estimated_time_minutes', 15),
                step=5,
                key=f"duration_{transport_id}"
            )
            
            # Zeige Wunschzeitfenster wenn vorhanden
            if trans.get('requested_time_start') and trans.get('requested_time_end'):
                st.info(f"💡 Wunsch des Patienten: {trans['requested_time_start']} - {trans['requested_time_end']} Uhr")
            
            col_submit, col_cancel = st.columns(2)
            with col_submit:
                submitted = st.form_submit_button("Speichern", type="primary", use_container_width=True)
            with col_cancel:
                cancelled = st.form_submit_button("Abbrechen", use_container_width=True)
            
            if submitted:
                # Validierung: Prüfe ob Datum und Uhrzeit ausgewählt wurden
                if selected_date is None or selected_time is None:
                    st.error("Bitte wählen Sie sowohl ein Datum als auch eine Uhrzeit aus.")
                else:
                    try:
                        # Kombiniere Datum und Uhrzeit (lokale Zeit, da vom Benutzer eingegeben)
                        selected_datetime_local = datetime.combine(selected_date, selected_time)
                        
                        # Warnung wenn Zeit in der Vergangenheit liegt (aber trotzdem erlauben)
                        now_local = datetime.now(ZoneInfo(LOCAL_TIMEZONE)).replace(tzinfo=None)
                        if selected_datetime_local < now_local:
                            st.warning("⚠️ Die geplante Zeit liegt in der Vergangenheit.")
                        
                        # Interpretiere als lokale Zeit und konvertiere zu UTC
                        selected_datetime_local_tz = selected_datetime_local.replace(tzinfo=ZoneInfo(LOCAL_TIMEZONE))
                        selected_datetime_utc = selected_datetime_local_tz.astimezone(timezone.utc)
                        planned_start_time_str = selected_datetime_utc.isoformat()
                        
                        # Update Transport
                        update_kwargs = {
                            'planned_start_time': planned_start_time_str,
                            'estimated_time_minutes': estimated_time
                        }
                        
                        if is_edit:
                            # Nur planned_start_time aktualisieren, Status bleibt 'planned'
                            success = db.update_transport_status(transport_id, **update_kwargs)
                        else:
                            # Status auf 'planned' setzen
                            update_kwargs['status'] = 'planned'
                            success = db.update_transport_status(transport_id, **update_kwargs)
                        
                        if success:
                            # Cache invalidieren
                            _get_transport_requests_cached.clear()
                            # Markiere dass ein Update gemacht wurde (für sofortige Datenaktualisierung)
                            st.session_state['last_transport_update_time'] = time.time()
                            # Background-Daten Cache invalidieren, damit aktualisierte Daten geladen werden
                            if 'background_data' in st.session_state and st.session_state.background_data:
                                # Aktualisiere nur Transport-Daten im Background-Cache
                                try:
                                    updated_transport = db.get_transport_requests()
                                    st.session_state.background_data['transport'] = updated_transport
                                    st.session_state.background_data['timestamp'] = time.time()
                                except:
                                    # Falls Fehler, lösche Background-Cache komplett
                                    st.session_state.background_data_timestamp = 0
                            # Dialog schließen
                            st.session_state[dialog_key] = False
                            # Erfolgsmeldung anzeigen (wird beim nächsten Render nicht mehr angezeigt, da Dialog geschlossen)
                            st.success("✅ Transport erfolgreich geplant!" if not is_edit else "✅ Transport erfolgreich aktualisiert!")
                            # Seite neu laden
                            st.rerun()
                        else:
                            st.error("❌ Fehler beim Speichern der Änderungen. Bitte versuchen Sie es erneut.")
                    except Exception as e:
                        st.error(f"❌ Fehler beim Verarbeiten der Zeitangabe: {str(e)}")
                        # Zeige vollständige Fehlerdetails für Debugging
                        st.exception(e)
            
            if cancelled:
                st.session_state[dialog_key] = False
                st.rerun()
    
    return st.session_state[dialog_key]

def render(db, sim, get_cached_alerts=None, get_cached_recommendations=None, get_cached_capacity=None):
    """Rendert die Transport-Seite"""
    # ===== SOFORT: STRUKTUR RENDERN =====
    st.markdown("### Transport")
    
    # Loading Spinner
    spinner_placeholder = st.empty()
    with spinner_placeholder.container():
        st.markdown(render_loading_spinner("Lade Transportdaten..."), unsafe_allow_html=True)
    
    content_placeholder = st.empty()
    
    # ===== PERIODISCHE STATUS-UPDATES =====
    # Nur alle 10 Sekunden Status-Updates durchführen (nicht bei jedem Render)
    update_interval = 10  # Sekunden
    last_update_key = 'transport_last_status_update'
    
    if last_update_key not in st.session_state:
        st.session_state[last_update_key] = 0
    
    current_time = time.time()
    should_update = (current_time - st.session_state[last_update_key]) >= update_interval
    
    if should_update:
        # Führe Batch-Updates aus
        _update_transport_statuses(db)
        st.session_state[last_update_key] = current_time
    
    # ===== DATEN ABRUFEN =====
    # Prüfe ob kürzlich ein Update gemacht wurde (innerhalb der letzten 5 Sekunden)
    # In diesem Fall lade direkt aus DB für sofortige Aktualisierung
    last_transport_update_key = 'last_transport_update_time'
    if last_transport_update_key in st.session_state:
        time_since_update = time.time() - st.session_state[last_transport_update_key]
        if time_since_update < 5:  # Wenn Update vor weniger als 5 Sekunden
            # Lade direkt aus DB für sofortige Aktualisierung
            transport = _get_transport_requests_cached(db)
            # Aktualisiere auch Background-Cache
            if 'background_data' in st.session_state and st.session_state.background_data:
                st.session_state.background_data['transport'] = transport
                st.session_state.background_data['timestamp'] = time.time()
        else:
            # Verwende Background-Daten für sofortigen Zugriff
            if 'background_data' in st.session_state and st.session_state.background_data:
                transport = st.session_state.background_data.get('transport', [])
            else:
                transport = _get_transport_requests_cached(db)  # Fallback: Gecacht
    else:
        # Verwende Background-Daten für sofortigen Zugriff
        if 'background_data' in st.session_state and st.session_state.background_data:
            transport = st.session_state.background_data.get('transport', [])
        else:
            transport = _get_transport_requests_cached(db)  # Fallback: Gecacht
    
    # Spinner entfernen
    spinner_placeholder.empty()
    
    with content_placeholder.container():
        if transport:
            # Zusammenfassende Kennzahlen
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                pending_count = len([t for t in transport if t['status'] in ['pending', 'ausstehend']])
                st.metric("Anfragen", pending_count)
            with col2:
                in_progress_count = len([t for t in transport if t['status'] in ['in_progress', 'in_bearbeitung']])
                st.metric("Aktiv", in_progress_count)
            with col3:
                planned_count = len([t for t in transport if t['status'] == 'planned'])
                st.metric("Geplant", planned_count)
            with col4:
                completed_count = len([t for t in transport if t['status'] in ['completed', 'abgeschlossen']])
                st.metric("Abgeschlossen", completed_count)

            # Button zum Löschen aller Transportanfragen
            col_delete = st.columns([4, 1])
            with col_delete[1]:
                delete_all_key = "delete_all_transports"
                if st.button("🗑️ Alle löschen", key=delete_all_key, use_container_width=True, type="secondary"):
                    st.session_state['confirm_delete_all'] = True
            
            # Bestätigungsdialog für Löschen aller Anfragen
            if st.session_state.get('confirm_delete_all', False):
                st.warning("⚠️ Möchten Sie wirklich alle noch nicht bestätigten Transportanfragen löschen? Diese Aktion kann nicht rückgängig gemacht werden.")
                col_confirm, col_cancel = st.columns(2)
                with col_confirm:
                    if st.button("Ja, alle löschen", key="confirm_delete_all_yes", type="primary", use_container_width=True):
                        if db.delete_all_transport_requests():
                            # Cache invalidieren
                            _get_transport_requests_cached.clear()
                            # Markiere dass ein Update gemacht wurde (für sofortige Datenaktualisierung)
                            st.session_state['last_transport_update_time'] = time.time()
                            # Background-Daten Cache invalidieren, damit aktualisierte Daten geladen werden
                            if 'background_data' in st.session_state and st.session_state.background_data:
                                # Aktualisiere nur Transport-Daten im Background-Cache
                                try:
                                    updated_transport = db.get_transport_requests()
                                    st.session_state.background_data['transport'] = updated_transport
                                    st.session_state.background_data['timestamp'] = time.time()
                                except:
                                    # Falls Fehler, lösche Background-Cache komplett
                                    st.session_state.background_data_timestamp = 0
                            st.session_state['confirm_delete_all'] = False
                            st.rerun()
                        else:
                            st.error("❌ Fehler beim Löschen der Transportanfragen")
                with col_cancel:
                    if st.button("Abbrechen", key="confirm_delete_all_no", use_container_width=True):
                        st.session_state['confirm_delete_all'] = False
                        st.rerun()

            st.markdown("---")
            
            # Gruppiere Transporte nach Status
            pending_transports = [t for t in transport if t['status'] in ['pending', 'ausstehend']]
            active_transports = [t for t in transport if t['status'] in ['in_progress', 'in_bearbeitung']]
            planned_transports = [t for t in transport if t['status'] == 'planned']
            completed_transports = [t for t in transport if t['status'] in ['completed', 'abgeschlossen']]
            
            # 1. Transportanfragen (pending) - mit Bestätigungs-Button
            st.markdown("### 📋 Transportanfragen")
            if pending_transports:
                for i, trans in enumerate(pending_transports):
                    _render_transport_card(trans, db, sim, show_confirm_button=True, delay_class="fade-in" if i == 0 else f"fade-in-delayed-{min(i, 3)}" if i <= 3 else "fade-in-delayed-3")
            else:
                st.info("Keine ausstehenden Transportanfragen")
            st.markdown("---")
        
            # 2. Aktive Transporte (in_progress)
            st.markdown("### 🚑 Aktive Transporte")
            if active_transports:
                for i, trans in enumerate(active_transports):
                    _render_transport_card(trans, db, sim, delay_class="fade-in" if i == 0 else f"fade-in-delayed-{min(i, 3)}" if i <= 3 else "fade-in-delayed-3")
            else:
                st.info("Keine aktiven Transporte")
            st.markdown("---")
            
            # 3. Geplante Transporte (planned)
            st.markdown("### 📅 Geplante Transporte")
            if planned_transports:
                for i, trans in enumerate(planned_transports):
                    _render_transport_card(trans, db, sim, delay_class="fade-in" if i == 0 else f"fade-in-delayed-{min(i, 3)}" if i <= 3 else "fade-in-delayed-3")
            else:
                st.info("Keine geplanten Transporte")
            st.markdown("---")
            
            # 4. Abgeschlossene Transporte (completed) - in Expander
            with st.expander(f"✅ Abgeschlossene Transporte ({len(completed_transports)})", expanded=False):
                if completed_transports:
                    for i, trans in enumerate(completed_transports):
                        _render_transport_card(trans, db, sim, delay_class="fade-in" if i == 0 else f"fade-in-delayed-{min(i, 3)}" if i <= 3 else "fade-in-delayed-3")
                else:
                    st.info("Keine abgeschlossenen Transporte")
        else:
            st.markdown(render_empty_state("🚑", "Keine Transportanfragen", "Zurzeit keine aktiven Transportanfragen"), unsafe_allow_html=True)


def _render_transport_card(trans, db, sim, show_confirm_button=False, delay_class="fade-in"):
    """Rendert eine einzelne Transportkarte"""
    priority_color = get_priority_color(trans['priority'])
    status_color = get_status_color(trans['status'])
    
    # Translate priority, status, and request_type to German
    priority_map = {'high': 'HOCH', 'medium': 'MITTEL', 'low': 'NIEDRIG', 'hoch': 'HOCH', 'mittel': 'MITTEL', 'niedrig': 'NIEDRIG'}
    status_map = {
        'pending': 'AUSSTEHEND',
        'in_progress': 'IN BEARBEITUNG',
        'completed': 'ABGESCHLOSSEN',
        'planned': 'GEPLANT',
        'ausstehend': 'AUSSTEHEND',
        'in_bearbeitung': 'IN BEARBEITUNG',
        'abgeschlossen': 'ABGESCHLOSSEN'
    }
    request_type_map = {
        'patient': 'Patient',
        'equipment': 'Gerät',
        'specimen': 'Probe',
        'Patient': 'Patient',
        'Gerät': 'Gerät',
        'Probe': 'Probe'
    }
    priority_display = priority_map.get(trans['priority'].lower(), trans['priority'].upper())
    status_display = status_map.get(trans['status'].lower().replace(' ', '_'), trans['status'].replace('_', ' ').upper())
    request_type_display = request_type_map.get(trans['request_type'], trans['request_type'].title())
    
    # Hole Details basierend auf related_entity_type
    details_info = ""
    related_type = trans.get('related_entity_type')
    if related_type == 'inventory_order':
        # Hole Bestellungs-Details
        order_id = trans.get('related_entity_id')
        if order_id:
            # Hole Bestellungs-Details über Mock-Datenbank
            order = None
            try:
                orders = db.get_inventory_orders()
                order = next((o for o in orders if o['id'] == order_id), None)
            except Exception:
                pass
            if order:
                details_info = f" • <strong>{order['quantity']}x {order['item_name']}</strong>"
    elif related_type == 'patient_transfer':
        details_info = " • <strong>Patiententransfer</strong>"
    
    # Geplante Startzeit - immer anzeigen, wenn vorhanden
    planned_time_info = ""
    planned_time_display = ""  # Für prominente Anzeige
    planned_start = trans.get('planned_start_time')
    if planned_start:
        try:
            # Konvertiere UTC zu lokaler Zeit
            planned_time = convert_utc_to_local(planned_start)
            if planned_time:
                formatted_date = planned_time.strftime('%d.%m.%Y')
                formatted_time = planned_time.strftime('%H:%M')
            else:
                # Fallback falls Konvertierung fehlschlägt
                if isinstance(planned_start, str):
                    planned_time = datetime.fromisoformat(planned_start.replace('Z', '+00:00'))
                else:
                    planned_time = planned_start
                if planned_time.tzinfo:
                    planned_time = planned_time.replace(tzinfo=None)
                formatted_date = planned_time.strftime('%d.%m.%Y')
                formatted_time = planned_time.strftime('%H:%M')
            
            # Prominente Anzeige für alle Status mit geplanter Zeit
            planned_time_display = f"<div style='color: {status_color}; font-weight: 600; font-size: 0.9375rem; margin-top: 0.25rem;'>📅 Geplant: {formatted_date} um {formatted_time} Uhr</div>"
            
            # Zusätzliche Info in der Detailzeile (nur wenn nicht bereits prominent angezeigt)
            # planned_time_info wird nicht mehr verwendet, da wir planned_time_display immer zeigen
        except:
            pass
    elif trans['status'] == 'planned':
        # Wenn Status 'planned' aber keine geplante Zeit vorhanden
        planned_time_display = "<div style='color: #F59E0B; font-weight: 600; font-size: 0.9375rem; margin-top: 0.25rem;'>⚠️ Geplante Startzeit noch nicht festgelegt</div>"
    
    # Erwartete Abschlusszeit für in_progress Transporte
    completion_info = ""
    if trans['status'] in ['in_progress', 'in_bearbeitung']:
        expected_completion = trans.get('expected_completion_time')
        if expected_completion:
            try:
                # Konvertiere UTC zu lokaler Zeit
                completion_time = convert_utc_to_local(expected_completion)
                if completion_time:
                    now = datetime.now()
                    remaining = (completion_time - now).total_seconds() / 60
                else:
                    # Fallback falls Konvertierung fehlschlägt
                    if isinstance(expected_completion, str):
                        completion_time = datetime.fromisoformat(expected_completion.replace('Z', '+00:00'))
                    else:
                        completion_time = expected_completion
                    if completion_time.tzinfo:
                        completion_time = completion_time.replace(tzinfo=None)
                    now = datetime.now()
                    remaining = (completion_time - now).total_seconds() / 60
                if remaining > 0:
                    completion_info = f" • Erwartete Ankunft in: <span style='color: {status_color}; font-weight: 600;'>{format_duration_minutes(int(remaining))}</span>"
                else:
                    completion_info = " • Erwartete Ankunft: <span style='color: #DC2626; font-weight: 600;'>Jetzt</span>"
            except:
                pass
    
    # Verzögerung/Stau anzeigen
    delay_info = ""
    delay_minutes = trans.get('delay_minutes')
    if delay_minutes and delay_minutes > 0:
        delay_info = f" • <span style='color: #DC2626;'>⚠️ Verzögerung: +{format_duration_minutes(delay_minutes)} (Stau)</span>"
    
    # Wunschzeitfenster für pending Transporte anzeigen
    requested_time_info = ""
    if trans['status'] in ['pending', 'ausstehend']:
        requested_start = trans.get('requested_time_start')
        requested_end = trans.get('requested_time_end')
        if requested_start and requested_end:
            requested_time_info = f"<div style='color: #4f46e5; font-size: 0.875rem; margin-top: 0.25rem;'>💡 Wunsch: {requested_start} - {requested_end} Uhr</div>"
    
    # Container für Karte und Button (nur wenn Button benötigt wird)
    show_button = show_confirm_button and trans['status'] in ['pending', 'ausstehend']
    show_edit_button = trans['status'] == 'planned'
    
    if show_button or show_edit_button:
        col_card, col_button = st.columns([5, 1])
        card_col = col_card
    else:
        card_col = st.container()
    
    with card_col:
        st.html(f"""
        <div class="{delay_class}" style="background: white; padding: 1rem; border-radius: 8px; margin-bottom: 0.5rem;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="flex: 1;">
                    <div>
                        <span class="badge" style="background: {priority_color}; color: white;">{priority_display}</span>
                        <span class="badge" style="background: {status_color}; color: white; margin-left: 0.5rem;">{status_display}</span>
                        <strong style="margin-left: 0.5rem;">{request_type_display}</strong>
                        {details_info}
                    </div>
                    {planned_time_display}
                    {requested_time_info}
                    <div style="color: #6b7280; font-size: 0.875rem; margin-top: 0.25rem;">
                        {trans['from_location']} → {trans['to_location']}
                        {f"• Geschätzt: {format_duration_minutes(trans['estimated_time_minutes'])}" if trans['estimated_time_minutes'] else ""}
                        {f"• Tatsächlich: {format_duration_minutes(trans['actual_time_minutes'])}" if trans['actual_time_minutes'] else ""}
                        {completion_info}
                        {delay_info}
                        • {format_time_ago(trans['timestamp'])}
                    </div>
                </div>
            </div>
        </div>
        """)
    
    # Bestätigungs- und Ablehnungs-Buttons für pending Transporte
    if show_button:
        with col_button:
            transport_id = trans['id']
            button_key = f"confirm_transport_{transport_id}"
            reject_button_key = f"reject_transport_{transport_id}"
            dialog_key = f"schedule_dialog_{transport_id}"
            if st.button("✅ Bestätigen", key=button_key, type="primary", use_container_width=True):
                st.session_state[dialog_key] = True
                st.rerun()
            if st.button("❌ Ablehnen", key=reject_button_key, use_container_width=True):
                if db.delete_transport_request(transport_id):
                    # Cache invalidieren
                    _get_transport_requests_cached.clear()
                    # Markiere dass ein Update gemacht wurde (für sofortige Datenaktualisierung)
                    st.session_state['last_transport_update_time'] = time.time()
                    # Background-Daten Cache invalidieren, damit aktualisierte Daten geladen werden
                    if 'background_data' in st.session_state and st.session_state.background_data:
                        # Aktualisiere nur Transport-Daten im Background-Cache
                        try:
                            updated_transport = db.get_transport_requests()
                            st.session_state.background_data['transport'] = updated_transport
                            st.session_state.background_data['timestamp'] = time.time()
                        except:
                            # Falls Fehler, lösche Background-Cache komplett
                            st.session_state.background_data_timestamp = 0
                    st.rerun()
                else:
                    st.error("Fehler beim Löschen der Anfrage")
    
    # Bearbeitungs-Button für geplante Transporte
    if show_edit_button:
        with col_button:
            transport_id = trans['id']
            button_key = f"edit_transport_{transport_id}"
            dialog_key = f"schedule_dialog_{transport_id}"
            if st.button("✏️ Bearbeiten", key=button_key, use_container_width=True):
                st.session_state[dialog_key] = True
                st.rerun()
    
    # Zeige Dialog wenn geöffnet (nach den Buttons, damit Formular nach Button-Klick erscheint)
    transport_id = trans['id']
    dialog_key = f"schedule_dialog_{transport_id}"
    if st.session_state.get(dialog_key, False):
        _show_schedule_dialog(trans, db, sim, is_edit=show_edit_button)
