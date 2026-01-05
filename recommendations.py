"""
HospitalFlow Empfehlungs-Engine

Hybrid-Engine mit regelbasierten, simulierten ML-Ansätzen und Optimierung.
Generiert KI-Empfehlungen basierend auf aktuellen Metriken.
"""
from datetime import datetime, timezone
from typing import List, Dict, Optional
from database import HospitalDB


class RecommendationEngine:
    """Engine für KI-Empfehlungen"""
    
    # Hardcodierte Schwellenwerte
    THRESHOLDS = {
        'ed_load_critical': 85.0,  # ED Load > 85% = kritisch
        'ed_load_warning': 75.0,   # ED Load > 75% = Warnung
        'waiting_count_critical': 15,  # Wartende > 15 = kritisch
        'waiting_count_warning': 10,   # Wartende > 10 = Warnung
        'beds_free_critical': 5,   # Freie Betten < 5 = kritisch
        'beds_free_warning': 10,   # Freie Betten < 10 = Warnung
        'staff_load_critical': 90.0,  # Personal > 90% = kritisch
        'staff_load_warning': 80.0,   # Personal > 80% = Warnung
        'transport_queue_critical': 8,  # Transport-Warteschlange > 8 = kritisch
        'transport_queue_warning': 5,   # Transport-Warteschlange > 5 = Warnung
    }
    
    def __init__(self, db: HospitalDB):
        """
        Initialisiert die Empfehlungs-Engine.
        
        Args:
            db: HospitalDB-Instanz
        """
        self.db = db
    
    def generate_recommendations(self, sim_metrics: Dict) -> List[Dict]:
        """
        Generiert Empfehlungen basierend auf aktuellen Metriken.
        
        Args:
            sim_metrics: Aktuelle Simulationsmetriken
            
        Returns:
            Liste von Empfehlungs-Dicts
        """
        recommendations = []
        
        # 1. ED Load Analyse
        ed_load = sim_metrics.get('ed_load', 0)
        waiting_count = sim_metrics.get('waiting_count', 0)
        
        if ed_load > self.THRESHOLDS['ed_load_critical'] or waiting_count > self.THRESHOLDS['waiting_count_critical']:
            # Kritische Situation - Personal-Umschichtung
            rec = self._create_staffing_recommendation(ed_load, waiting_count, 'high')
            if rec:
                recommendations.append(rec)
        
        elif ed_load > self.THRESHOLDS['ed_load_warning'] or waiting_count > self.THRESHOLDS['waiting_count_warning']:
            # Warnung - Personal-Umschichtung (niedrigere Priorität)
            rec = self._create_staffing_recommendation(ed_load, waiting_count, 'medium')
            if rec:
                recommendations.append(rec)
        
        # 2. Bettenkapazität Analyse
        beds_free = sim_metrics.get('beds_free', 0)
        
        if beds_free < self.THRESHOLDS['beds_free_critical']:
            # Kritisch - Betten freigeben
            rec = self._create_capacity_recommendation(beds_free, 'high')
            if rec:
                recommendations.append(rec)
        
        elif beds_free < self.THRESHOLDS['beds_free_warning']:
            # Warnung - Betten freigeben
            rec = self._create_capacity_recommendation(beds_free, 'medium')
            if rec:
                recommendations.append(rec)
        
        # 3. Personal-Auslastung Analyse
        staff_load = sim_metrics.get('staff_load', 0)
        
        if staff_load > self.THRESHOLDS['staff_load_critical']:
            # Kritisch - Personal-Umschichtung
            rec = self._create_staffing_recommendation(ed_load, waiting_count, 'high', staff_focus=True)
            if rec:
                recommendations.append(rec)
        
        # 4. Transport-Warteschlange Analyse
        transport_queue = sim_metrics.get('transport_queue', 0)
        
        if transport_queue > self.THRESHOLDS['transport_queue_critical']:
            # Kritisch - Transport-Optimierung
            rec = self._create_transport_recommendation(transport_queue, 'high')
            if rec:
                recommendations.append(rec)
        
        # 5. Inventar-Analyse
        inventory = self.db.get_inventory_status()
        critical_items = [i for i in inventory if i['current_stock'] < i['min_threshold']]
        
        if len(critical_items) > 0:
            # Kritische Inventar-Artikel
            rec = self._create_inventory_recommendation(critical_items, 'high' if len(critical_items) >= 3 else 'medium')
            if rec:
                recommendations.append(rec)
        
        # Speichere Empfehlungen in DB
        self._save_recommendations(recommendations)
        
        return recommendations
    
    def _create_staffing_recommendation(self, ed_load: float, waiting_count: int, priority: str, staff_focus: bool = False) -> Optional[Dict]:
        """Erstellt Personal-Umschichtungs-Empfehlung"""
        if staff_focus:
            title = "Personal-Umschichtung zur Entlastung"
            action = "Zusätzliches Personal von Allgemeinstation zur Notaufnahme umschichten, um Personalauslastung zu reduzieren."
            reason = f"Die Personalauslastung liegt bei {ed_load:.1f}%. Eine Umschichtung kann die Belastung reduzieren."
        else:
            title = "Personal-Umschichtung empfohlen"
            action = "Zusätzliches Personal von Allgemeinstation zur Notaufnahme umschichten, um Wartezeiten zu reduzieren."
            reason = f"Die Notaufnahme-Auslastung liegt bei {ed_load:.1f}% mit {waiting_count} wartenden Patienten. Eine Personal-Umschichtung kann die Situation entspannen."
        
        expected_impact = f"Reduziert ED Load um ~8% und Warteliste um ~2 Patienten"
        
        # Simulierte ML-Konfidenz (basierend auf Regel-Erfüllungsgrad)
        rule_score = min(1.0, (ed_load / 100) * 0.7 + (waiting_count / 20) * 0.3)
        explanation_score = 'high' if rule_score > 0.8 else 'medium' if rule_score > 0.6 else 'low'
        
        return {
            'title': title,
            'description': action,
            'priority': priority,
            'department': 'ER',
            'rec_type': 'staffing',
            'status': 'pending',
            'action': action,
            'reason': reason,
            'expected_impact': expected_impact,
            'safety_note': 'Personalschichtung muss mit Abteilungsleitern abgestimmt werden. Keine Auswirkungen auf kritische Bereiche.',
            'explanation_score': explanation_score
        }
    
    def _create_capacity_recommendation(self, beds_free: int, priority: str) -> Optional[Dict]:
        """Erstellt Kapazitäts-Empfehlung"""
        beds_to_open = max(2, 5 - beds_free)
        
        title = "Zusätzliche Betten freigeben"
        action = f"Freigabe von {beds_to_open} zusätzlichen Betten in der Intensivstation zur Entlastung der Notaufnahme."
        reason = f"Nur noch {beds_free} freie Betten verfügbar. Das Öffnen zusätzlicher Betten kann Engpässe verhindern."
        expected_impact = f"Erhöht freie Betten um {beds_to_open} und reduziert ED Load um ~5%"
        
        # Simulierte ML-Konfidenz
        rule_score = min(1.0, (10 - beds_free) / 10)
        explanation_score = 'high' if rule_score > 0.8 else 'medium' if rule_score > 0.6 else 'low'
        
        return {
            'title': title,
            'description': action,
            'priority': priority,
            'department': 'ICU',
            'rec_type': 'capacity',
            'status': 'pending',
            'action': action,
            'reason': reason,
            'expected_impact': expected_impact,
            'safety_note': 'Betten müssen vor Freigabe gereinigt und vorbereitet werden. Personal muss verfügbar sein.',
            'explanation_score': explanation_score
        }
    
    def _create_transport_recommendation(self, transport_queue: int, priority: str) -> Optional[Dict]:
        """Erstellt Transport-Optimierungs-Empfehlung"""
        title = "Transport-Optimierung empfohlen"
        action = "Zusätzliche Transportressourcen bereitstellen oder Transporte priorisieren."
        reason = f"{transport_queue} Transporte in der Warteschlange. Optimierung kann Verzögerungen reduzieren."
        expected_impact = "Reduziert Transport-Wartezeiten um ~30%"
        
        rule_score = min(1.0, transport_queue / 10)
        explanation_score = 'high' if rule_score > 0.8 else 'medium' if rule_score > 0.6 else 'low'
        
        return {
            'title': title,
            'description': action,
            'priority': priority,
            'department': 'Logistics',
            'rec_type': 'transport',
            'status': 'pending',
            'action': action,
            'reason': reason,
            'expected_impact': expected_impact,
            'safety_note': 'Transport-Priorisierung muss mit medizinischem Personal abgestimmt werden.',
            'explanation_score': explanation_score
        }
    
    def _create_inventory_recommendation(self, critical_items: List[Dict], priority: str) -> Optional[Dict]:
        """Erstellt Inventar-Nachbestellungs-Empfehlung"""
        item_names = [item['item_name'] for item in critical_items[:3]]  # Max 3 nennen
        items_str = ', '.join(item_names)
        if len(critical_items) > 3:
            items_str += f" und {len(critical_items) - 3} weitere"
        
        title = "Kritische Inventar-Artikel nachbestellen"
        action = f"Nachbestellung für {items_str} einleiten."
        reason = f"{len(critical_items)} Artikel liegen unter dem Mindestbestand. Nachbestellung verhindert Engpässe."
        expected_impact = "Verhindert Versorgungsengpässe in den nächsten 24-48 Stunden"
        
        rule_score = min(1.0, len(critical_items) / 5)
        explanation_score = 'high' if rule_score > 0.8 else 'medium' if rule_score > 0.6 else 'low'
        
        return {
            'title': title,
            'description': action,
            'priority': priority,
            'department': critical_items[0].get('department', 'N/A') if critical_items else 'N/A',
            'rec_type': 'inventory',
            'status': 'pending',
            'action': action,
            'reason': reason,
            'expected_impact': expected_impact,
            'safety_note': 'Kritische Artikel müssen sofort nachbestellt werden. Transportzeit berücksichtigen.',
            'explanation_score': explanation_score
        }
    
    def _save_recommendations(self, recommendations: List[Dict]):
        """Speichert Empfehlungen in die Datenbank (thread-safe)"""
        self.db.save_recommendations_batch(recommendations)

