"""
HospitalFlow Vorhersage-Algorithmen

Algorithmen-basierte Vorhersagen, die KI-Verhalten simulieren.
Verwendet statistische Methoden und simulierte ML-Ansätze.
"""
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from database import HospitalDB


class PredictionEngine:
    """Engine für Vorhersagen mit algorithmen-basierten Methoden"""
    
    def __init__(self, db: HospitalDB):
        """
        Initialisiert die Vorhersage-Engine.
        
        Args:
            db: HospitalDB-Instanz
        """
        self.db = db
    
    def predict_patient_arrival(self, time_horizon_minutes: int, department: str) -> Dict:
        """
        Vorhersage für Patientenzugang.
        
        Args:
            time_horizon_minutes: Zeithorizont in Minuten (5, 10, 15)
            department: Abteilung
            
        Returns:
            Dict mit predicted_value, confidence, etc.
        """
        # Hole historische ED Load Daten (besserer Indikator für Patientenzugang)
        history = self.db.get_metrics_last_n_minutes(60)
        ed_load_history = [m for m in history if m['metric_type'] == 'ed_load']
        
        # Basis-Vorhersage basierend auf ED Load Trend
        if len(ed_load_history) >= 3:
            recent_ed_loads = [m['value'] for m in ed_load_history[-12:]]  # Letzte 12 Einträge (1 Stunde)
            current_ed_load = recent_ed_loads[-1] if recent_ed_loads else 65.0
            
            # Berechne Trend der ED Load (steigende Load = mehr Patienten)
            if len(recent_ed_loads) >= 2:
                ed_trend = (recent_ed_loads[-1] - recent_ed_loads[0]) / len(recent_ed_loads)
            else:
                ed_trend = 0
            
            # Konvertiere ED Load Trend zu erwarteten Patientenzugängen
            # Annahme: ED Load von 50% = ~3 Patienten/5min, 75% = ~6 Patienten/5min, 100% = ~10 Patienten/5min
            # Formel: Patienten pro 5min ≈ (ED_Load / 10) * 0.6
            base_patients_per_5min = (current_ed_load / 10) * 0.6
            
            # Trend-Korrektur: Wenn ED Load steigt, erwarten wir mehr Patienten
            trend_adjustment = (ed_trend / 10) * 0.3  # Anpassung basierend auf Trend
            
            # Tageszeit-Faktor
            now = datetime.now(timezone.utc)
            hour = now.hour
            if 8 <= hour <= 12:
                time_factor = 1.3  # Morgen-Spitze
            elif 14 <= hour <= 18:
                time_factor = 1.2  # Nachmittag
            elif 22 <= hour or hour < 6:
                time_factor = 0.6  # Nacht
            else:
                time_factor = 0.9  # Standard
            
            # Wochentags-Faktor
            weekday = now.weekday()
            weekday_factor = 0.85 if weekday >= 5 else 1.0  # Wochenende weniger
            
            # Vorhergesagter Wert für den Zeithorizont
            # Skaliere von 5-Minuten-Basis auf gewünschten Zeithorizont
            time_scale = time_horizon_minutes / 5.0
            base_prediction = base_patients_per_5min * time_scale
            trend_effect = trend_adjustment * time_scale
            predicted_value = (base_prediction + trend_effect) * time_factor * weekday_factor
            
            # Konfidenz basierend auf Datenqualität
            confidence = min(0.95, 0.6 + (len(ed_load_history) / 20) * 0.35)
            
            # Anpassung für Zeithorizont (länger = weniger Konfidenz)
            confidence *= (1 - (time_horizon_minutes / 60) * 0.2)
        else:
            # Fallback ohne Historie - konservative Schätzung
            predicted_value = 3.0 * (time_horizon_minutes / 5.0)
            confidence = 0.5
        
        return {
            'prediction_type': 'patient_arrival',
            'predicted_value': max(0, int(round(predicted_value))),
            'confidence': max(0.3, confidence),
            'time_horizon_minutes': time_horizon_minutes,
            'department': department,
            'model_version': 'v1.0-statistical'
        }
    
    def predict_bed_demand(self, time_horizon_minutes: int, department: str) -> Dict:
        """
        Vorhersage für Bettenbedarf.
        
        Args:
            time_horizon_minutes: Zeithorizont in Minuten (15, 30, 60)
            department: Abteilung
            
        Returns:
            Dict mit predicted_value (als %), confidence, etc.
        """
        # Hole Kapazitätsdaten
        capacity = self.db.get_capacity_overview()
        dept_capacity = next((c for c in capacity if c['department'] == department), None)
        
        if not dept_capacity:
            return {
                'prediction_type': 'bed_demand',
                'predicted_value': 75.0,
                'confidence': 0.5,
                'time_horizon_minutes': time_horizon_minutes,
                'department': department,
                'model_version': 'v1.0-statistical'
            }
        
        total_beds = dept_capacity.get('total_beds', 20)
        current_utilization = dept_capacity.get('utilization_percent', 75.0)
        
        # Hole historische Metriken für Betten
        history = self.db.get_metrics_last_n_minutes(120)  # 2 Stunden
        bed_history = [m for m in history if m['metric_type'] == 'beds_free']
        
        # Berechne Trend basierend auf aktueller Auslastung und historischen Daten
        if len(bed_history) >= 3:
            recent_beds = [m['value'] for m in bed_history[-24:]]  # Letzte 24 Einträge
            current_free = recent_beds[-1] if recent_beds else total_beds * (1 - current_utilization / 100)
            current_occupied = total_beds - current_free
            
            # Berechne Trend: Wie ändert sich die Anzahl freier Betten?
            # Positiver Trend = mehr Betten werden frei, negativer = mehr werden belegt
            if len(recent_beds) >= 2:
                # Trend pro Eintrag (ca. 5 Minuten pro Eintrag)
                beds_trend_per_entry = (recent_beds[-1] - recent_beds[0]) / max(1, len(recent_beds) - 1)
                # Skaliere auf Stunden (12 Einträge pro Stunde bei 5-Min-Intervallen)
                beds_trend_per_hour = beds_trend_per_entry * 12
            else:
                beds_trend_per_hour = 0
            
            # Vorhersage: Wie viele Betten werden in X Minuten belegt sein?
            # Wenn Trend negativ (weniger frei), werden mehr Betten belegt
            hours_ahead = time_horizon_minutes / 60.0
            predicted_free_change = beds_trend_per_hour * hours_ahead
            predicted_free = max(0, min(total_beds, current_free + predicted_free_change))
            predicted_occupied = total_beds - predicted_free
            predicted_utilization = (predicted_occupied / total_beds) * 100 if total_beds > 0 else current_utilization
            
            # Begrenze auf realistische Werte
            predicted_utilization = max(5, min(98, predicted_utilization))
            
            # Konfidenz basierend auf Datenqualität und Zeithorizont
            confidence = min(0.9, 0.5 + (len(bed_history) / 30) * 0.4)
            confidence *= (1 - (time_horizon_minutes / 120) * 0.15)  # Länger = weniger Konfidenz
        else:
            # Fallback: Verwende aktuelle Auslastung mit kleiner Anpassung basierend auf ED Load
            # Wenn ED Load hoch ist, erwarten wir mehr Bettenbedarf
            ed_load_history = [m for m in history if m['metric_type'] == 'ed_load']
            if ed_load_history:
                current_ed_load = ed_load_history[-1]['value']
                # ED Load beeinflusst Bettenbedarf mit Verzögerung
                ed_impact = (current_ed_load - 65) * 0.15  # 65% ist Normal
                predicted_utilization = current_utilization + ed_impact
            else:
                predicted_utilization = current_utilization
            
            predicted_utilization = max(5, min(98, predicted_utilization))
            confidence = 0.5
        
        return {
            'prediction_type': 'bed_demand',
            'predicted_value': round(predicted_utilization, 1),
            'confidence': max(0.3, confidence),
            'time_horizon_minutes': time_horizon_minutes,
            'department': department,
            'model_version': 'v1.0-statistical'
        }
    
    def generate_predictions(self, time_horizons: List[int] = [5, 10, 15]) -> List[Dict]:
        """
        Generiert genau 12 Vorhersagen über alle Abteilungen hinweg.
        
        Verteilung:
        - 6 Patientenzugang-Vorhersagen: 2 Abteilungen × 3 Zeithorizonte (5, 10, 15 Min)
        - 6 Bettenbedarf-Vorhersagen: 2 Abteilungen × 3 Zeithorizonte (5, 10, 15 Min)
        
        Args:
            time_horizons: Liste von Zeithorizonten in Minuten (Standard: [5, 10, 15])
            
        Returns:
            Liste von genau 12 Vorhersage-Dicts
        """
        predictions = []
        
        # Hole alle verfügbaren Abteilungen aus der Datenbank
        capacity_data = self.db.get_capacity_overview()
        all_departments = [c['department'] for c in capacity_data if c.get('department')]
        
        # Falls keine Abteilungen gefunden, kann keine Vorhersage generiert werden
        if not all_departments:
            return []
        
        # Wähle Abteilungen für Patientenzugang-Vorhersagen
        # Verwende die ersten verfügbaren Abteilungen aus der Datenbank
        patient_arrival_depts = []
        for dept in all_departments:
            if len(patient_arrival_depts) < 2:
                patient_arrival_depts.append(dept)
        
        # Falls nur eine Abteilung vorhanden, verwende sie zweimal
        if len(patient_arrival_depts) == 1:
            patient_arrival_depts.append(patient_arrival_depts[0])
        
        # Wähle Abteilungen für Bettenbedarf-Vorhersagen
        # Verwende die ersten verfügbaren Abteilungen, die noch nicht für Patientenzugang verwendet wurden
        bed_demand_depts = []
        # Versuche zuerst andere Abteilungen zu verwenden
        for dept in all_departments:
            if dept not in patient_arrival_depts and len(bed_demand_depts) < 2:
                bed_demand_depts.append(dept)
        
        # Falls nicht genug verschiedene Abteilungen vorhanden, verwende auch die bereits verwendeten
        remaining_depts = [d for d in all_departments if d not in bed_demand_depts]
        while len(bed_demand_depts) < 2 and remaining_depts:
            bed_demand_depts.append(remaining_depts.pop(0))
        
        # Falls immer noch nicht genug, verwende die ersten Abteilungen erneut
        if len(bed_demand_depts) < 2:
            for dept in all_departments:
                if len(bed_demand_depts) < 2:
                    bed_demand_depts.append(dept)
        
        # Generiere 6 Patientenzugang-Vorhersagen (2 Abteilungen × 3 Zeithorizonte)
        for dept in patient_arrival_depts[:2]:  # Sicherstellen, dass nur 2 verwendet werden
            for horizon in time_horizons:
                if horizon <= 15:  # Nur für kurze Zeithorizonte
                    pred = self.predict_patient_arrival(horizon, dept)
                    predictions.append(pred)
        
        # Generiere 6 Bettenbedarf-Vorhersagen (2 Abteilungen × 3 Zeithorizonte)
        for dept in bed_demand_depts[:2]:  # Sicherstellen, dass nur 2 verwendet werden
            for horizon in time_horizons:
                if horizon <= 15:  # Verwende die gleichen Zeithorizonte
                    pred = self.predict_bed_demand(horizon, dept)
                    predictions.append(pred)
        
        # Sicherstellen, dass genau 12 Vorhersagen generiert wurden
        # Falls weniger, füge fehlende hinzu
        while len(predictions) < 12:
            # Füge fehlende Patientenzugang-Vorhersagen hinzu
            if len([p for p in predictions if p['prediction_type'] == 'patient_arrival']) < 6:
                dept = patient_arrival_depts[0]
                horizon = time_horizons[len([p for p in predictions if p['prediction_type'] == 'patient_arrival']) % len(time_horizons)]
                pred = self.predict_patient_arrival(horizon, dept)
                predictions.append(pred)
            # Füge fehlende Bettenbedarf-Vorhersagen hinzu
            elif len([p for p in predictions if p['prediction_type'] == 'bed_demand']) < 6:
                dept = bed_demand_depts[0]
                horizon = time_horizons[len([p for p in predictions if p['prediction_type'] == 'bed_demand']) % len(time_horizons)]
                pred = self.predict_bed_demand(horizon, dept)
                predictions.append(pred)
            else:
                break
        
        # Falls mehr als 12, begrenze auf 12 (bevorzuge die ersten)
        if len(predictions) > 12:
            predictions = predictions[:12]
        
        # Speichere in DB
        self._save_predictions(predictions)
        
        return predictions
    
    def _save_predictions(self, predictions: List[Dict]):
        """Speichert Vorhersagen in die Datenbank (thread-safe)"""
        self.db.save_predictions_batch(predictions)

