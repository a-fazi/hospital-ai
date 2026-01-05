"""
Seitenmodul für Dienstplan
"""
import streamlit as st
from datetime import datetime, timedelta, date
from typing import Optional
from utils import get_severity_color
from ui.components import render_badge, render_empty_state


def get_week_start(d: date) -> date:
    """Berechne Montag der Woche für ein gegebenes Datum"""
    days_since_monday = d.weekday()
    return d - timedelta(days=days_since_monday)


def format_week_range(week_start: date) -> str:
    """Formatiere Wochenbereich (Montag - Sonntag)"""
    week_end = week_start + timedelta(days=6)
    return f"{week_start.strftime('%d.%m.%Y')} - {week_end.strftime('%d.%m.%Y')}"


def render(db, sim):
    """Rendert die Dienstplan-Seite"""
    # Initialisiere Session State
    if 'current_week_start' not in st.session_state:
        today = date.today()
        st.session_state.current_week_start = get_week_start(today)
    
    # Hole alle Mitarbeiter
    @st.cache_data(ttl=300)  # Cache für 5 Minuten (Personal ändert sich selten)
    def _get_all_staff_cached(_db):
        """Gecachte Personalübersicht"""
        return _db.get_all_staff()
    
    staff_by_category = _get_all_staff_cached(db)  # Gecacht
    
    # Wenn keine Person ausgewählt ist, wähle automatisch die erste Person aus
    if 'selected_staff_id' not in st.session_state or st.session_state.selected_staff_id is None:
        # Finde die erste Person in der Liste (nach Kategorie-Reihenfolge)
        first_staff_id = None
        category_order = ["Pflegekräfte", "Ärzte", "Logistik", "Orga"]
        for category in category_order:
            if category in staff_by_category and staff_by_category[category]:
                first_staff_id = staff_by_category[category][0]['id']
                break
        
        if first_staff_id is not None:
            st.session_state.selected_staff_id = first_staff_id
    
    # Seitenlayout: Links Liste, Rechts Detail
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("### Personal")
        st.markdown("")  # Spacing
        
        # Zeige Personal gruppiert nach Kategorien
        if not staff_by_category:
            st.info("Kein Personal gefunden")
        else:
            category_order = ["Pflegekräfte", "Ärzte", "Logistik", "Orga"]
            
            for category in category_order:
                if category not in staff_by_category:
                    continue
                
                staff_list = staff_by_category[category]
                if not staff_list:
                    continue
                
                # Kategorie-Header
                st.markdown(f"**{category}**")
                
                # Personal-Liste
                for person in staff_list:
                    staff_id = person['id']
                    is_selected = st.session_state.selected_staff_id == staff_id
                    
                    # Button-Styling basierend auf Auswahl
                    button_label = f"👤 {person['name']}"
                    if is_selected:
                        button_label = f"✓ {button_label}"
                    
                    if st.button(
                        button_label,
                        key=f"staff_{staff_id}",
                        use_container_width=True,
                        type="primary" if is_selected else "secondary"
                    ):
                        st.session_state.selected_staff_id = staff_id
                        # Setze auf aktuelle Woche wenn Person ausgewählt wird
                        today = date.today()
                        st.session_state.current_week_start = get_week_start(today)
                        # Auto-Scroll nach oben
                        st.markdown("""
                        <script>
                            window.scrollTo(0, 0);
                        </script>
                        """, unsafe_allow_html=True)
                        st.rerun()
                
                st.markdown("")  # Spacing zwischen Kategorien
    
    with col2:
        if st.session_state.selected_staff_id is None:
            st.info("👈 Wählen Sie eine Person aus der Liste aus, um den Dienstplan anzuzeigen")
        else:
            # Hole Personendaten
            all_staff = []
            for category_list in staff_by_category.values():
                all_staff.extend(category_list)
            
            # Robuster Vergleich mit Typkonvertierung
            selected_staff_id = st.session_state.selected_staff_id
            selected_person = None
            for p in all_staff:
                # Konvertiere beide zu int für Vergleich
                try:
                    p_id = int(p.get('id', 0))
                    s_id = int(selected_staff_id) if selected_staff_id is not None else None
                    if p_id == s_id:
                        selected_person = p
                        break
                except (ValueError, TypeError):
                    # Fallback: direkter Vergleich
                    if p.get('id') == selected_staff_id:
                        selected_person = p
                        break
            
            if not selected_person:
                # Person nicht gefunden - wähle automatisch die erste verfügbare Person
                if all_staff:
                    first_person = all_staff[0]
                    st.session_state.selected_staff_id = first_person.get('id')
                    selected_person = first_person
                else:
                    st.error("Person nicht gefunden und keine Alternative verfügbar")
                    return
            
            # Detailansicht
            render_staff_detail(db, selected_person, st.session_state.current_week_start)


def render_staff_detail(db, person: dict, week_start: date):
    """Rendert Detailansicht für eine Person"""
    staff_id = person['id']
    week_start_str = week_start.strftime('%Y-%m-%d')
    
    # Person-Info Header
    st.markdown(f"### {person['name']}")
    st.markdown(f"**{person['role']}** • {person['department']} • {person['category']}")
    if person.get('contact'):
        st.markdown(f"📧 {person['contact']}")
    
    st.markdown("---")
    
    # Hole Daten für diese Woche
    @st.cache_data(ttl=300)  # Cache für 5 Minuten
    def _get_staff_schedule_cached(_db, _staff_id, _week_start):
        """Gecachter Dienstplan"""
        return _db.get_staff_schedule(_staff_id, _week_start)
    
    @st.cache_data(ttl=300)  # Cache für 5 Minuten
    def _get_actual_hours_cached(_db, _staff_id, _week_start):
        """Gecachte tatsächliche Stunden"""
        return _db.get_actual_hours(_staff_id, _week_start)
    
    @st.cache_data(ttl=300)  # Cache für 5 Minuten
    def _calculate_overtime_cached(_db, _staff_id, _week_start):
        """Gecachte Überstunden-Berechnung"""
        return _db.calculate_overtime(_staff_id, _week_start)
    
    schedule = _get_staff_schedule_cached(db, staff_id, week_start_str)  # Gecacht
    actual_hours_list = _get_actual_hours_cached(db, staff_id, week_start_str)  # Gecacht
    overtime_data = _calculate_overtime_cached(db, staff_id, week_start_str)  # Gecacht
    
    # Berechne ob Woche in Vergangenheit, Zukunft oder aktuell
    today = date.today()
    week_end = week_start + timedelta(days=6)
    is_past = week_end < today
    is_future = week_start > today
    is_current = not is_past and not is_future
    
    # Zusammenfassung
    st.markdown("### Zusammenfassung")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        # Fix: Use safe access for contract_hours
        contract_hours = overtime_data.get('contract_hours', 0)
        st.markdown(f"""
        <div style="background: white; padding: 1rem; border-radius: 8px; border-left: 3px solid #667eea;">
            <div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.5rem;">Vertragsstunden</div>
            <div style="font-size: 1.5rem; font-weight: 700; color: #111827;">{contract_hours:.0f}h</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        # Fix: Use safe access for planned_hours
        planned_hours = overtime_data.get('planned_hours', 0)
        st.markdown(f"""
        <div style="background: white; padding: 1rem; border-radius: 8px; border-left: 3px solid #3b82f6;">
            <div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.5rem;">Geplante Stunden</div>
            <div style="font-size: 1.5rem; font-weight: 700; color: #111827;">{planned_hours:.1f}h</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        if is_past or is_current:
            # Fix: Use safe access for actual_hours
            actual_hours = overtime_data.get('actual_hours', 0)
            actual_color = "#10b981" if actual_hours > 0 else "#6b7280"
            st.markdown(f"""
            <div style="background: white; padding: 1rem; border-radius: 8px; border-left: 3px solid {actual_color};">
                <div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.5rem;">Tatsächliche Stunden</div>
                <div style="font-size: 1.5rem; font-weight: 700; color: #111827;">{actual_hours:.1f}h</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background: white; padding: 1rem; border-radius: 8px; border-left: 3px solid #9ca3af;">
                <div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.5rem;">Tatsächliche Stunden</div>
                <div style="font-size: 1.5rem; font-weight: 700; color: #9ca3af;">-</div>
            </div>
            """, unsafe_allow_html=True)
    
    with col4:
        if is_past or is_current:
            # Fix: Use safe access for overtime, calculate if missing
            overtime = overtime_data.get('overtime')
            if overtime is None:
                # Calculate overtime from other fields if available
                planned_hours = overtime_data.get('planned_hours', 0)
                contract_hours = overtime_data.get('contract_hours', 0)
                overtime = planned_hours - contract_hours
            overtime_color = "#dc2626" if overtime > 0 else "#10b981" if overtime < 0 else "#6b7280"
            overtime_label = "Überstunden" if overtime > 0 else "Minusstunden" if overtime < 0 else "Ausgeglichen"
            st.markdown(f"""
            <div style="background: white; padding: 1rem; border-radius: 8px; border-left: 3px solid {overtime_color};">
                <div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.5rem;">{overtime_label}</div>
                <div style="font-size: 1.5rem; font-weight: 700; color: #111827;">{overtime:+.1f}h</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background: white; padding: 1rem; border-radius: 8px; border-left: 3px solid #9ca3af;">
                <div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.5rem;">Überstunden</div>
                <div style="font-size: 1.5rem; font-weight: 700; color: #9ca3af;">-</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Wochennavigation
    st.markdown("### Wochenplan")
    
    nav_col1, nav_col2, nav_col3 = st.columns([1, 3, 1])
    
    with nav_col1:
        if st.button("◀ Vorherige Woche", use_container_width=True):
            st.session_state.current_week_start = week_start - timedelta(weeks=1)
            st.rerun()
    
    with nav_col2:
        week_range = format_week_range(week_start)
        week_label = "Aktuelle Woche" if is_current else "Vergangene Woche" if is_past else "Zukünftige Woche"
        st.markdown(f"<div style='text-align: center; padding: 0.5rem; font-weight: 600;'>{week_label}<br/>{week_range}</div>", unsafe_allow_html=True)
    
    with nav_col3:
        if st.button("Nächste Woche ▶", use_container_width=True):
            st.session_state.current_week_start = week_start + timedelta(weeks=1)
            st.rerun()
    
    st.markdown("")  # Spacing
    
    # Kalenderansicht: 7 Tage
    day_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    cols = st.columns(7)
    
    # Erstelle Dictionary für schnellen Zugriff
    # Fix: Calculate day_of_week from date if missing
    schedule_dict = {}
    for entry in schedule:
        if 'day_of_week' in entry:
            day_of_week = entry['day_of_week']
        elif 'date' in entry:
            # Calculate day_of_week from date
            entry_date_str = entry['date']
            if isinstance(entry_date_str, str):
                entry_date = datetime.strptime(entry_date_str, '%Y-%m-%d').date()
            else:
                entry_date = entry_date_str
            day_of_week = (entry_date - week_start).days
        else:
            # Skip entries without date or day_of_week
            continue
        
        if 0 <= day_of_week <= 6:
            schedule_dict[day_of_week] = entry
    actual_dict = {}
    for entry in actual_hours_list:
        # Fix: Use safe access for date, skip if missing
        entry_date_str = entry.get('date')
        if entry_date_str is None:
            # Skip entries without date
            continue
        
        # Handle date - could be string or date object
        if isinstance(entry_date_str, str):
            try:
                entry_date = datetime.strptime(entry_date_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                # Skip entries with invalid date format
                continue
        else:
            entry_date = entry_date_str
        
        day_of_week = (entry_date - week_start).days
        if 0 <= day_of_week <= 6:
            actual_dict[day_of_week] = entry
    
    for i, (col, day_name) in enumerate(zip(cols, day_names)):
        with col:
            day_date = week_start + timedelta(days=i)
            day_str = day_date.strftime('%d.%m')
            
            # Ist heute?
            is_today = day_date == today
            
            # Border-Styling für heute
            border_style = "border: 2px solid #667eea;" if is_today else "border: 1px solid #e5e7eb;"
            
            st.markdown(f"""
            <div style="background: white; padding: 0.75rem; border-radius: 8px; {border_style} margin-bottom: 0.5rem;">
                <div style="font-size: 0.75rem; color: #6b7280; font-weight: 600; margin-bottom: 0.5rem;">{day_name}</div>
                <div style="font-size: 0.7rem; color: #9ca3af; margin-bottom: 0.75rem;">{day_str}</div>
            </div>
            """, unsafe_allow_html=True)
            
            # Geplante Stunden oder Urlaub
            if i in schedule_dict:
                entry = schedule_dict[i]
                is_vacation = entry.get('is_vacation', False)
                
                if is_vacation:
                    # Urlaub anzeigen
                    st.markdown(f"""
                    <div style="background: #fef3c7; padding: 0.5rem; border-radius: 4px; margin-bottom: 0.5rem; border-left: 3px solid #f59e0b;">
                        <div style="font-size: 0.7rem; color: #92400e; margin-bottom: 0.25rem;">Urlaub</div>
                        <div style="font-size: 0.9rem; font-weight: 600; color: #d97706;">🏖️ Frei</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # Normale Schicht
                    planned_hours = entry.get('planned_hours', 0.0)
                    shift_info = ""
                    if entry.get('shift_start') and entry.get('shift_end'):
                        shift_info = f"<div style='font-size: 0.65rem; color: #9ca3af; margin-top: 0.25rem;'>{entry['shift_start']} - {entry['shift_end']}</div>"
                    
                    st.markdown(f"""
                    <div style="background: #eff6ff; padding: 0.5rem; border-radius: 4px; margin-bottom: 0.5rem;">
                        <div style="font-size: 0.7rem; color: #6b7280; margin-bottom: 0.25rem;">Geplant</div>
                        <div style="font-size: 1rem; font-weight: 700; color: #3b82f6;">{planned_hours:.1f}h</div>
                        {shift_info}
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background: #f9fafb; padding: 0.5rem; border-radius: 4px; margin-bottom: 0.5rem;">
                    <div style="font-size: 0.7rem; color: #9ca3af;">Frei</div>
                </div>
                """, unsafe_allow_html=True)
            
            # Tatsächliche Stunden (nur für Vergangenheit und aktuelle Woche bis heute)
            if (is_past or (is_current and day_date <= today)) and i in actual_dict:
                entry = actual_dict[i]
                actual_hours = entry['actual_hours']
                st.markdown(f"""
                <div style="background: #ecfdf5; padding: 0.5rem; border-radius: 4px;">
                    <div style="font-size: 0.7rem; color: #6b7280; margin-bottom: 0.25rem;">Tatsächlich</div>
                    <div style="font-size: 1rem; font-weight: 700; color: #10b981;">{actual_hours:.1f}h</div>
                </div>
                """, unsafe_allow_html=True)
            elif is_future or (is_current and day_date > today):
                # Für zukünftige Tage keine tatsächlichen Stunden
                pass

