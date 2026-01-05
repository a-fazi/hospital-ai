"""
Seitenmodul für Inventar
"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pandas as pd
import random
import json
import os
from utils import (
    format_time_ago, get_severity_color, get_priority_color, get_risk_color,
    get_status_color, calculate_inventory_status, calculate_capacity_status,
    format_duration_minutes, get_department_color, get_system_status,
    get_metric_severity_for_load, get_metric_severity_for_count, get_metric_severity_for_free,
    get_explanation_score_color, calculate_days_until_stockout, calculate_reorder_suggestion,
    calculate_daily_consumption_from_activity
)
from ui.components import render_badge, render_empty_state


def _get_simulation_metrics_cached(_sim=None):
    """Gecachte Simulationsmetriken aus session_state"""
    if 'cached_sim_metrics' in st.session_state:
        return st.session_state.cached_sim_metrics
    if _sim:
        return _sim.get_current_metrics()
    return {}

@st.cache_data(ttl=60)
def _get_inventory_status_cached(_db):
    """Gecachter Inventar-Status"""
    return _db.get_inventory_status()

@st.cache_data(ttl=30)
def _get_inventory_orders_cached(_db):
    """Gecachte Inventar-Bestellungen"""
    return _db.get_inventory_orders()

def render(db, sim, get_cached_alerts=None, get_cached_recommendations=None, get_cached_capacity=None):
    """Rendert die Inventar-Seite"""
    # Zeige Erfolgsmeldungen an (falls vorhanden) und lösche Processing-Flags
    if 'order_success' in st.session_state:
        st.success(st.session_state.order_success)
        # Lösche alle Processing-Flags nach erfolgreicher Bestellung
        keys_to_delete = [key for key in st.session_state.keys() if key.startswith('processing_order_')]
        
        for key in keys_to_delete:
            del st.session_state[key]
        del st.session_state.order_success
    
    # Zeige Fehlermeldungen an (falls vorhanden) und lösche Processing-Flags
    if 'order_error' in st.session_state:
        st.error(st.session_state.order_error)
        # Lösche alle Processing-Flags nach Fehler
        keys_to_delete = [key for key in st.session_state.keys() if key.startswith('processing_order_')]
        
        for key in keys_to_delete:
            del st.session_state[key]
        del st.session_state.order_error
    
    # Hole Simulationszustand für Aktivitäts-basierte Berechnungen
    sim_metrics = _get_simulation_metrics_cached(sim)  # Gecacht
    # Verwende get_cached_capacity für optimierten Zugriff (aus background_data)
    if get_cached_capacity:
        capacity_data = get_cached_capacity()
    elif 'background_data' in st.session_state and st.session_state.background_data:
        capacity_data = st.session_state.background_data.get('capacity', [])
    else:
        # Fallback: Direkter DB-Zugriff (sollte selten vorkommen)
        capacity_data = db.get_capacity_overview()
    
    # Verwende Background-Daten für sofortigen Zugriff
    if 'background_data' in st.session_state and st.session_state.background_data:
        inventory = st.session_state.background_data.get('inventory', [])
    else:
        inventory = _get_inventory_status_cached(db)  # Fallback: Gecacht
    
    if inventory:
        # 1. Nachfüllvorschläge
        st.markdown("---")
        st.markdown("#### Nachfüllvorschläge")
        st.markdown("")  # Abstand
        
        # Berechne Verbrauchsraten und Nachfüllvorschläge für alle Artikel
        restock_suggestions = []
        for item in inventory:
            # Berechne Verbrauchsrate basierend auf Historie und Aktivität
            consumption_rate_data = db.calculate_inventory_consumption_rate(
                item_id=item['id'],
                sim_state={
                    'ed_load': sim_metrics.get('ed_load', 65.0),
                    'beds_occupied': sum([c.get('occupied_beds', 0) for c in capacity_data])
                }
            )
            daily_consumption_rate = consumption_rate_data['daily_rate']
            
            # Berechne Tage bis Engpass
            days_until_stockout = calculate_days_until_stockout(
                current_stock=item['current_stock'],
                daily_consumption_rate=daily_consumption_rate
            )
            
            # Berechne Nachfüllvorschlag
            reorder_suggestion = calculate_reorder_suggestion(
                item=item,
                daily_consumption_rate=daily_consumption_rate,
                days_until_stockout=days_until_stockout
            )
            
            # Zeige Artikel an, wenn:
            # 1. Priorität hoch oder mittel ist, ODER
            # 2. Artikel unter Mindestbestand liegt, ODER
            # 3. Artikel einen Nachfüllvorschlag hat (auch bei niedriger Priorität, wenn nahe am Mindestbestand)
            should_show = (
                reorder_suggestion['priority'] in ['hoch', 'mittel'] or
                item['current_stock'] < item['min_threshold'] or
                (reorder_suggestion['suggested_qty'] > 0 and 
                 item['current_stock'] < item['min_threshold'] * 1.2)  # Innerhalb 20% des Mindestbestands
            )
            
            if should_show:
                restock_suggestions.append({
                    'item': item,
                    'consumption_rate': daily_consumption_rate,
                    'days_until_stockout': days_until_stockout,
                    'suggestion': reorder_suggestion
                })
        
        # Sortiere nach Priorität
        restock_suggestions.sort(key=lambda x: {'hoch': 1, 'mittel': 2, 'niedrig': 3}[x['suggestion']['priority']])
        
        if restock_suggestions:
            for suggestion_data in restock_suggestions:
                item = suggestion_data['item']
                suggestion = suggestion_data['suggestion']
                consumption_rate = suggestion_data['consumption_rate']
                days_until_stockout = suggestion_data['days_until_stockout']
                
                priority_color = get_severity_color(suggestion['priority'])
                
                # Formatiere Bestelltermin
                order_by_info = ""
                if suggestion['order_by_days'] is not None:
                    if suggestion['order_by_days'] == 0:
                        order_by_info = " • <span style='color: #DC2626; font-weight: 600;'>SOFORT bestellen</span>"
                    elif suggestion['order_by_days'] == 1:
                        order_by_info = f" • Bestellen bis: <span style='color: {priority_color}; font-weight: 600;'>morgen</span>"
                    else:
                        order_by_info = f" • Bestellen bis: <span style='color: {priority_color}; font-weight: 600;'>{suggestion['order_by_days']} Tage</span>"
                
                # Tage bis Engpass Info
                days_info = ""
                if days_until_stockout is not None:
                    days_info = f" • {days_until_stockout:.1f} Tage bis Engpass"
                
                # Verbrauchsrate Info
                consumption_info = f" • Verbrauch: {consumption_rate:.1f} {item['unit']}/Tag"
                
                # Bestellmenge berechnen
                order_quantity = max(0, suggestion['suggested_qty'] - item['current_stock'])
                
                # Container für Vorschlag mit Button
                col1, col2 = st.columns([4, 1])
                
                with col1:
                    st.markdown(f"""
                    <div style="background: #f9fafb; padding: 1rem; border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid {priority_color};">
                        <div style="font-weight: 600; color: #1f2937; margin-bottom: 0.25rem;">{item['item_name']}</div>
                        <div style="font-size: 0.875rem; color: #6b7280; margin-top: 0.25rem;">
                            {item.get('department', 'N/A')}{days_info}{consumption_info}
                        </div>
                        <div style="font-size: 0.875rem; color: #6b7280; margin-top: 0.25rem;">
                            Aktuell: {item['current_stock']} {item['unit']} → Vorgeschlagen: {suggestion['suggested_qty']} {item['unit']}
                        </div>
                        <div style="font-size: 0.875rem; color: #6b7280; margin-top: 0.25rem; font-style: italic;">
                            {suggestion['reasoning']}{order_by_info}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col2:
                    st.markdown("<br>", unsafe_allow_html=True)  # Spacing
                    button_key = f"order_btn_{item['id']}"
                    
                    # Prüfe ob bereits eine aktive Bestellung existiert
                    active_orders = _get_inventory_orders_cached(db)  # Gecacht
                    has_active_order = any(
                        o['item_id'] == item['id'] and o['status'] in ['ordered', 'in_transit']
                        for o in active_orders
                    )
                    
                    if has_active_order:
                        st.info("Bestellung bereits aktiv", icon="ℹ️")
                    elif order_quantity <= 0:
                        # Wenn Bestellmenge 0 oder negativ wäre, zeige Info statt Button
                        st.info("Keine Bestellung nötig", icon="ℹ️")
                    else:
                        # Button zum Bestätigen der Bestellung
                        # Verwende einen Button-spezifischen Flag, um Endlosschleifen zu vermeiden
                        processing_key = f"processing_order_{item['id']}"
                        
                        # Prüfe ob dieser spezifische Button gerade verarbeitet wird
                        if processing_key not in st.session_state or not st.session_state[processing_key]:
                            button_clicked = st.button("Bestellung bestätigen", key=button_key, type="primary", use_container_width=True)
                            
                            if button_clicked:
                                # Setze Flag für diesen Button, um mehrfache Verarbeitung zu verhindern
                                st.session_state[processing_key] = True
                                
                                try:
                                    # Berechne nächste mögliche Zeit für Transport
                                    estimated_time_minutes = 60  # Standard Transportzeit für Inventar-Lieferungen
                                    planned_start_time = sim.calculate_planned_start_time(estimated_time_minutes=estimated_time_minutes)
                                    
                                    # Verarbeite Bestellung direkt mit geplanter Startzeit
                                    order_result = db.create_inventory_order(
                                        item_id=item['id'],
                                        quantity=order_quantity,
                                        department=item.get('department'),
                                        planned_start_time=planned_start_time,
                                        estimated_time_minutes=estimated_time_minutes
                                    )
                                    
                                    # Cache für Inventory Orders invalidieren, da neue Bestellung erstellt wurde
                                    _get_inventory_orders_cached.clear()
                                    
                                    # Speichere Erfolgsmeldung für Anzeige nach Rerun
                                    # WICHTIG: Flag wird NICHT gelöscht, damit beim nächsten Rerun nicht erneut verarbeitet wird
                                    # Das Flag wird erst gelöscht, nachdem die Nachricht oben angezeigt wurde
                                    st.session_state.order_success = f"✅ Bestellung erstellt! {order_quantity} {item['unit']} {item['item_name']} werden zum Hauptlager geliefert. Transport wurde automatisch geplant."
                                    
                                    # Rerun nur einmal, um die Seite zu aktualisieren
                                    st.rerun()
                                except Exception as e:
                                    # Speichere Fehlermeldung für Anzeige nach Rerun
                                    # WICHTIG: Flag wird NICHT gelöscht, damit beim nächsten Rerun nicht erneut verarbeitet wird
                                    st.session_state.order_error = f"Fehler bei Bestellung: {str(e)}"
                                    
                                    # Rerun nur einmal, um die Fehlermeldung anzuzeigen
                                    st.rerun()
                        else:
                            # Wenn Processing-Flag gesetzt ist, zeige Button als disabled
                            st.button("Bestellung bestätigen", key=button_key, type="primary", use_container_width=True, disabled=True)
        else:
            st.markdown(render_empty_state("📦", "Keine Nachfüllvorschläge", "Alle Lagerbestände sind ausreichend"), unsafe_allow_html=True)
        
        # 1.5. Aktive Bestellungen
        st.markdown("---")
        st.markdown("#### Aktive Bestellungen")
        st.markdown("")  # Abstand
        
        active_orders = db.get_inventory_orders()
        active_orders = [o for o in active_orders if o['status'] in ['ordered', 'in_transit']]
        
        if active_orders:
            # Hole Transport-Daten aus background_data für optimierten Zugriff
            if 'background_data' in st.session_state and st.session_state.background_data:
                transports = st.session_state.background_data.get('transport', [])
            else:
                # Fallback: Direkter DB-Zugriff
                transports = db.get_transport_requests()
            
            for order in active_orders:
                # Hole Transport-Info
                transport_info = None
                if order.get('transport_id'):
                    transport_info = next((t for t in transports if t['id'] == order['transport_id']), None)
                
                status_map = {
                    'ordered': 'Bestellt',
                    'in_transit': 'In Transport',
                    'delivered': 'Geliefert'
                }
                status_display = status_map.get(order['status'], order['status'].title())
                
                status_color = "#F59E0B" if order['status'] in ['ordered', 'in_transit'] else "#10B981"
                
                # Erwartete Lieferzeit
                delivery_info = ""
                if transport_info:
                    if transport_info['status'] in ['pending', 'ausstehend']:
                        delivery_info = f" • Geschätzte Lieferzeit: {format_duration_minutes(transport_info.get('estimated_time_minutes', 0))}"
                    elif transport_info['status'] in ['in_progress', 'in_bearbeitung']:
                        if transport_info.get('expected_completion_time'):
                            try:
                                if isinstance(transport_info['expected_completion_time'], str):
                                    completion_time = datetime.fromisoformat(transport_info['expected_completion_time'].replace('Z', '+00:00'))
                                else:
                                    completion_time = transport_info['expected_completion_time']
                                
                                now = datetime.now(completion_time.tzinfo) if completion_time.tzinfo else datetime.now()
                                remaining = (completion_time - now).total_seconds() / 60
                                if remaining > 0:
                                    delivery_info = f" • Erwartete Ankunft in: {format_duration_minutes(int(remaining))}"
                                else:
                                    delivery_info = " • Erwartete Ankunft: Jetzt"
                            except:
                                delivery_info = f" • In Transport (geschätzt: {format_duration_minutes(transport_info.get('estimated_time_minutes', 0))})"
                        else:
                            delivery_info = f" • In Transport (geschätzt: {format_duration_minutes(transport_info.get('estimated_time_minutes', 0))})"
                
                st.markdown(f"""
                <div style="background: white; padding: 1rem; border-radius: 8px; margin-bottom: 0.5rem; border-left: 3px solid {status_color};">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="flex: 1;">
                            <div style="font-weight: 600; color: #1f2937; margin-bottom: 0.25rem;">{order['item_name']}</div>
                            <div style="font-size: 0.875rem; color: #6b7280; margin-top: 0.25rem;">
                                Menge: {order['quantity']} {next((i['unit'] for i in inventory if i['id'] == order['item_id']), 'Einheiten')} • 
                                Ziel-Abteilung: {order.get('department', 'N/A')} • 
                                Lieferung: Extern → Hauptlager • 
                                Status: <span style="color: {status_color}; font-weight: 600;">{status_display}</span>{delivery_info}
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown(render_empty_state("📋", "Keine aktiven Bestellungen", "Aktive Bestellungen werden hier angezeigt"), unsafe_allow_html=True)
        
        # 2. Lagerrisiko
        st.markdown("---")
        st.markdown("### Lagerrisiko")
        st.markdown("")  # Abstand
        
        # Verwende echte Inventory-Daten aus der DB mit präzisen Berechnungen
        inventory_materials = []
        for item in inventory:
            stock_percent = (item['current_stock'] / item['max_capacity']) * 100 if item['max_capacity'] > 0 else 0
            threshold_percent = (item['min_threshold'] / item['max_capacity']) * 100 if item['max_capacity'] > 0 else 0
            
            # Berechne Verbrauchsrate
            consumption_rate_data = db.calculate_inventory_consumption_rate(
                item_id=item['id'],
                sim_state={
                    'ed_load': sim_metrics.get('ed_load', 65.0),
                    'beds_occupied': sum([c.get('occupied_beds', 0) for c in capacity_data])
                }
            )
            daily_consumption_rate = consumption_rate_data['daily_rate']
            
            # Berechne Tage bis Engpass (präzise)
            days_until_stockout = calculate_days_until_stockout(
                current_stock=item['current_stock'],
                daily_consumption_rate=daily_consumption_rate
            )
            
            # Risiko auf Deutsch zuweisen basierend auf präziser Berechnung
            if days_until_stockout is not None:
                if days_until_stockout <= 2:
                    risk_level = "hoch"
                elif days_until_stockout <= 7:
                    risk_level = "mittel"
                else:
                    risk_level = "niedrig"
            elif item['current_stock'] < item['min_threshold']:
                risk_level = "mittel"
            else:
                risk_level = "niedrig"
            
            inventory_materials.append({
                'name': item['item_name'],
                'current_stock': item['current_stock'],
                'min_threshold': item['min_threshold'],
                'max_capacity': item['max_capacity'],
                'unit': item['unit'],
                'department': item.get('department', 'N/A'),
                'days_until_stockout': days_until_stockout,
                'risk_level': risk_level,
                'stock_percent': stock_percent,
                'threshold_percent': threshold_percent,
                'consumption_rate': daily_consumption_rate
            })

        # Nach Risiko sortieren (hoch zuerst)
        inventory_materials.sort(key=lambda x: {'hoch': 1, 'mittel': 2, 'niedrig': 3}[x['risk_level']])

        # Anzeige aller Materialien mit Risiko
        if inventory_materials:
            st.markdown("#### Materialien mit Risiko")
            
            # Filter: Suchfeld und Abteilungsfilter
            col1, col2 = st.columns([2, 1])
            
            with col1:
                search_query = st.text_input(
                    "🔍 Material suchen",
                    key="inventory_risk_search",
                    placeholder="Nach Materialname suchen...",
                    help="Geben Sie einen Suchbegriff ein, um die Materialien zu filtern"
                )
            
            with col2:
                # Extrahiere alle verfügbaren Abteilungen
                departments = sorted(set([mat['department'] for mat in inventory_materials if mat['department'] and mat['department'] != 'N/A']))
                departments.insert(0, "Alle Abteilungen")
                
                selected_department = st.selectbox(
                    "🏥 Abteilung filtern",
                    options=departments,
                    key="inventory_risk_department",
                    help="Wählen Sie eine Abteilung aus, um die Materialien zu filtern"
                )
            
            st.markdown("")  # Abstand
            
            # Filtere Materialien basierend auf Suchbegriff und Abteilung
            filtered_materials = inventory_materials
            
            # Filter nach Abteilung
            if selected_department and selected_department != "Alle Abteilungen":
                filtered_materials = [mat for mat in filtered_materials if mat['department'] == selected_department]
            
            # Filter nach Suchbegriff
            if search_query:
                search_lower = search_query.lower()
                filtered_materials = [
                    mat for mat in filtered_materials
                    if search_lower in mat['name'].lower()
                ]
            
            # Als formatierte Tabelle anzeigen
            for mat in filtered_materials:
                risk_color = get_severity_color(mat['risk_level'])
                risk_badge = render_badge(mat['risk_level'].upper(), mat['risk_level'])
                days_display = f"{mat['days_until_stockout']:.1f} Tage" if mat['days_until_stockout'] is not None else "N/V"
                consumption_display = f"{mat.get('consumption_rate', 0):.1f} {mat['unit']}/Tag"
                stock_percent = mat['stock_percent']
                threshold_percent = mat['threshold_percent']
                # Bestimme Farbe für Fortschrittsleiste basierend auf Risiko
                progress_color = risk_color if mat['risk_level'] in ['hoch', 'mittel'] else "#10B981"
                st.markdown(f"""
                <div style="background: white; padding: 1rem; border-radius: 8px; margin-bottom: 0.75rem; border-left: 4px solid {risk_color}; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
                    <div style="display: grid; grid-template-columns: 2fr 1fr 1fr 1fr 1fr 1fr 1fr; gap: 1rem; align-items: center;">
                        <div>
                            <div style="font-weight: 600; color: #1f2937; margin-bottom: 0.25rem;">{mat['name']}</div>
                            <div style="font-size: 0.75rem; color: #6b7280;">{mat['department']}</div>
                        </div>
                        <div>
                            <div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.25rem;">Aktuell</div>
                            <div style="font-weight: 600; color: #1f2937;">{mat['current_stock']} {mat['unit']}</div>
                        </div>
                        <div>
                            <div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.25rem;">Mindestbestand</div>
                            <div style="font-weight: 600; color: #1f2937;">{mat['min_threshold']} {mat['unit']}</div>
                        </div>
                        <div>
                            <div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.25rem;">Maximaler Bestand</div>
                            <div style="font-weight: 600; color: #1f2937;">{mat['max_capacity']} {mat['unit']}</div>
                        </div>
                        <div>
                            <div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.25rem;">Verbrauch/Tag</div>
                            <div style="font-weight: 600; color: #1f2937;">{consumption_display}</div>
                        </div>
                        <div>
                            <div style="font-size: 0.75rem; color: #6b7280; margin-bottom: 0.25rem;">Tage bis Engpass</div>
                            <div style="font-weight: 600; color: {risk_color if mat['days_until_stockout'] else '#6b7280'};">{days_display}</div>
                        </div>
                        <div>
                            {risk_badge}
                        </div>
                    </div>
                    <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid #e5e7eb;">
                        <div style="position: relative; background: #e5e7eb; height: 6px; border-radius: 3px; overflow: visible;">
                            <div style="background: {progress_color}; height: 100%; width: {min(100, stock_percent)}%; transition: width 0.3s ease; border-radius: 3px;"></div>
                            <div style="position: absolute; left: {min(100, threshold_percent)}%; top: -2px; width: 2px; height: 10px; background: #DC2626; z-index: 10; border-radius: 1px;"></div>
                        </div>
                        <div style="font-size: 0.75rem; color: #6b7280; margin-top: 0.25rem; text-align: right;">
                            {stock_percent:.1f}% des maximalen Bestands
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # Zeige Meldung wenn keine Ergebnisse gefunden wurden
            if not filtered_materials:
                if search_query or (selected_department and selected_department != "Alle Abteilungen"):
                    filter_msg = []
                    if search_query:
                        filter_msg.append(f"Suchbegriff '{search_query}'")
                    if selected_department and selected_department != "Alle Abteilungen":
                        filter_msg.append(f"Abteilung '{selected_department}'")
                    st.info(f"Keine Materialien gefunden, die {' und '.join(filter_msg)} entsprechen.")
                else:
                    st.info("Keine Materialien gefunden.")
        else:
            st.markdown(render_empty_state("📦", "Keine Materialien mit Risiko", "Alle Lagerbestände sind ausreichend"), unsafe_allow_html=True)
        
        # 3. Bestandsverlauf (als Liniendiagramm)
        st.markdown("---")
        st.markdown("### Bestandsverlauf")
        
        # Filter für Materialien
        if inventory:
            item_names = [item['item_name'] for item in inventory]
            selected_items = st.multiselect(
                "Materialien filtern",
                options=item_names,
                default=item_names[:5] if len(item_names) > 5 else item_names,  # Zeige max. 5 Materialien standardmäßig
                help="Wählen Sie die Materialien aus, die im Verlauf angezeigt werden sollen"
            )
            
            # Filtere Inventar basierend auf Auswahl
            filtered_inventory = [item for item in inventory if item['item_name'] in selected_items] if selected_items else []
        else:
            filtered_inventory = []
            selected_items = []
        
        if filtered_inventory:
            # Generiere simulierte historische Daten für die letzten 14 Tage
            dates = [datetime.now() - timedelta(days=x) for x in range(14, -1, -1)]
            
            # Erstelle Liniendiagramm für jeden Artikel
            fig = go.Figure()
            
            # Farben für verschiedene Artikel
            colors = px.colors.qualitative.Set3
            
            for idx, item in enumerate(filtered_inventory):
                # Simuliere historische Bestandsdaten
                # Starte mit einem zufälligen Wert nahe dem aktuellen Bestand
                base_stock = item['current_stock']
                historical_stocks = []
                
                # Generiere realistische Verlaufsdaten
                for i, date in enumerate(dates):
                    # Simuliere Schwankungen mit einem Trend
                    variation = random.uniform(-0.15, 0.15)  # ±15% Variation
                    trend = (14 - i) / 14 * 0.1  # Leichter Trend zum aktuellen Wert
                    stock_value = max(0, int(base_stock * (1 + variation + trend)))
                    historical_stocks.append(stock_value)
                
                # Berechne Auslastung in Prozent
                utilization = [(stock / item['max_capacity']) * 100 if item['max_capacity'] > 0 else 0 for stock in historical_stocks]
                
                fig.add_trace(go.Scatter(
                    x=dates,
                    y=utilization,
                    mode='lines+markers',
                    name=item['item_name'],
                    line=dict(color=colors[idx % len(colors)], width=2),
                    marker=dict(size=4)
                ))
            
            fig.update_layout(
                title="",
                xaxis_title="Datum",
                yaxis_title="Auslastung (%)",
                height=400,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                hovermode='x unified',
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            if selected_items is not None and len(selected_items) == 0:
                st.info("Bitte wählen Sie mindestens ein Material aus, um den Verlauf anzuzeigen.")
            else:
                st.info("Keine Materialien für den Verlauf ausgewählt.")
    else:
        st.info("Keine Bestandsdaten verfügbar")

