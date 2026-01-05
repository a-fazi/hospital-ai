"""
HospitalFlow Optimierungs-Algorithmen

Heuristische Optimierung für Wartungszeiten, Transportrouten
und Ressourcenallokation.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from database import HospitalDB


class OptimizationEngine:
    """Engine für Optimierungs-Algorithmen"""
    
    def __init__(self, db: HospitalDB):
        """
        Initialisiert die Optimierungs-Engine.
        
        Args:
            db: HospitalDB-Instanz
        """
        self.db = db
    
    def optimize_maintenance_times(self, device_id: str, duration_minutes: int, 
                                   max_suggestions: int = 5) -> List[Dict]:
        """
        Optimiert Wartungszeiten basierend auf erwarteter Auslastung.
        
        Args:
            device_id: Geräte-ID
            duration_minutes: Dauer der Wartung in Minuten
            max_suggestions: Maximale Anzahl Vorschläge
            
        Returns:
            Liste von optimierten Zeitvorschlägen
        """
        # Hole Gerät-Info
        devices = self.db.get_device_maintenance_urgencies()
        device = next((d for d in devices if d['device_id'] == device_id), None)
        if not device:
            return []
        
        department = device.get('department', 'ER')
        
        # Hole Kapazitätsdaten
        capacity = self.db.get_capacity_overview()
        dept_capacity = next((c for c in capacity if c['department'] == department), None)
        
        # Hole historische Metriken für Vorhersage
        history = self.db.get_metrics_last_n_minutes(120)
        
        suggestions = []
        now = datetime.now(timezone.utc)
        
        for i in range(max_suggestions):
            # Vorschläge für nächste 1-5 Tage
            days_ahead = i + 1
            start_hour = 14 if i == 0 else (10 + i * 2) % 24  # Verschiedene Zeiten
            start_time = now + timedelta(days=days_ahead, hours=start_hour)
            end_time = start_time + timedelta(minutes=duration_minutes)
            
            # Berechne erwartete Auslastung zu dieser Zeit
            hour = start_time.hour
            weekday = start_time.weekday()
            
            # Basis-Auslastung basierend auf Tageszeit
            if 8 <= hour <= 12 or 14 <= hour <= 18:
                base_load = 0.75  # Höhere Auslastung
            elif 22 <= hour or hour < 6:
                base_load = 0.35  # Niedrigere Auslastung
            else:
                base_load = 0.55  # Moderate Auslastung
            
            # Wochenende-Faktor
            if weekday >= 5:
                base_load *= 0.85
            
            # Abteilungs-spezifische Auslastung
            if dept_capacity:
                dept_utilization = dept_capacity.get('utilization_percent', 75) / 100
                base_load = (base_load + dept_utilization) / 2
            
            # Score: Niedrigere Auslastung = besserer Score
            score = 1.0 - base_load
            score = max(0.3, min(0.95, score))
            
            # Erwartete Patienten (vereinfacht)
            expected_patients = base_load * 10
            
            # Grund für Vorschlag
            if score > 0.8:
                reason = "Sehr niedrige erwartete Auslastung"
            elif score > 0.6:
                reason = "Moderate Auslastung, gute Zeit für Wartung"
            else:
                reason = "Akzeptable Zeit, aber nicht optimal"
            
            suggestions.append({
                'start_time': start_time,
                'end_time': end_time,
                'score': score,
                'expected_patients': expected_patients,
                'reason': reason,
                'duration_minutes': duration_minutes
            })
        
        # Sortiere nach Score
        suggestions.sort(key=lambda x: x['score'], reverse=True)
        
        return suggestions[:max_suggestions]
    
    def optimize_transport_route(self, transports: List[Dict]) -> List[Dict]:
        """
        Optimiert Transportrouten (Priorisierung).
        
        Args:
            transports: Liste von Transportanfragen
            
        Returns:
            Optimierte/priorisierte Liste
        """
        # Einfache Priorisierung: Priority + Zeit
        def priority_score(transport):
            priority_map = {'high': 3, 'hoch': 3, 'medium': 2, 'mittel': 2, 'low': 1, 'niedrig': 1}
            priority = transport.get('priority', 'medium').lower()
            priority_val = priority_map.get(priority, 1)
            
            # Zeit-Faktor (ältere = höherer Score)
            try:
                timestamp = transport.get('timestamp')
                if isinstance(timestamp, str):
                    ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                else:
                    ts = timestamp
                age_minutes = (datetime.now(timezone.utc) - ts).total_seconds() / 60
                time_factor = min(1.0, age_minutes / 60)  # Max 1.0 nach 60 Minuten
            except:
                time_factor = 0
            
            return priority_val * 10 + time_factor * 5
        
        # Sortiere nach Score
        sorted_transports = sorted(transports, key=priority_score, reverse=True)
        
        return sorted_transports
    
    def optimize_resource_allocation(self, departments: List[str], 
                                    available_resources: Dict[str, int]) -> Dict[str, int]:
        """
        Optimiert Ressourcenallokation (Greedy-Algorithmus).
        
        Args:
            departments: Liste von Abteilungen
            available_resources: Verfügbare Ressourcen (z.B. {'staff': 5, 'beds': 10})
            
        Returns:
            Optimierte Allokation pro Abteilung
        """
        # Hole Kapazitätsdaten
        capacity = self.db.get_capacity_overview()
        
        # Berechne Bedarf pro Abteilung
        department_needs = {}
        for dept in departments:
            dept_cap = next((c for c in capacity if c['department'] == dept), None)
            if dept_cap:
                utilization = dept_cap.get('utilization_percent', 75) / 100
                # Höhere Auslastung = höherer Bedarf
                department_needs[dept] = utilization
        
        # Sortiere nach Bedarf (höchster zuerst)
        sorted_depts = sorted(department_needs.items(), key=lambda x: x[1], reverse=True)
        
        # Greedy-Allokation
        allocation = {dept: 0 for dept in departments}
        remaining_resources = available_resources.copy()
        
        for dept, need in sorted_depts:
            if 'staff' in remaining_resources and remaining_resources['staff'] > 0:
                # Allokiere Personal basierend auf Bedarf
                staff_to_allocate = min(remaining_resources['staff'], int(need * 3))
                allocation[dept] = staff_to_allocate
                remaining_resources['staff'] -= staff_to_allocate
            
            if 'beds' in remaining_resources and remaining_resources['beds'] > 0:
                # Allokiere Betten basierend auf Bedarf
                beds_to_allocate = min(remaining_resources['beds'], int(need * 2))
                allocation[dept] = allocation.get(dept, 0) + beds_to_allocate
                remaining_resources['beds'] -= beds_to_allocate
        
        return allocation

