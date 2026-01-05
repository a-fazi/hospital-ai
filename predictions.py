"""
HospitalFlow Vorhersage-Algorithmen - Verbesserte Version

Implementiert fortgeschrittene statistische und ML-simulierte Vorhersagemethoden:
- Exponential Smoothing für Trend-Erkennung
- Saisonale Muster (Tageszeit, Wochentag)
- Multi-Feature-Regression-Simulation
- Adaptive Confidence-Berechnung
- Anomalie-Erkennung
"""
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from database import HospitalDB
from collections import deque


class PredictionEngine:
    """Verbesserte Engine für Vorhersagen mit fortgeschrittenen Methoden"""
    
    def __init__(self, db: HospitalDB):
        """
        Initialisiert die Vorhersage-Engine.
        
        Args:
            db: HospitalDB-Instanz
        """
        self.db = db
        # Cache für historische Daten zur Performance-Optimierung
        self._history_cache = {}
        self._cache_timestamp = None
        self._cache_ttl = 60  # Cache für 60 Sekunden
    
    def _get_historical_data(self, minutes: int = 120) -> Dict[str, List]:
        """
        Holt und cached historische Daten für Performance.
        
        Returns:
            Dict mit Listen von Werten für verschiedene Metriken
        """
        now = datetime.now(timezone.utc)
        
        # Prüfe Cache
        if (self._cache_timestamp and 
            (now - self._cache_timestamp).total_seconds() < self._cache_ttl):
            return self._history_cache
        
        # Hole frische Daten
        history = self.db.get_metrics_last_n_minutes(minutes)
        
        # Organisiere nach Metrik-Typ
        organized = {
            'ed_load': [],
            'beds_free': [],
            'waiting_count': [],
            'staff_load': [],
            'transport_queue': [],
            'or_load': [],
            'rooms_free': []
        }
        
        for metric in history:
            metric_type = metric['metric_type']
            if metric_type in organized:
                organized[metric_type].append({
                    'timestamp': metric['timestamp'],
                    'value': metric['value'],
                    'department': metric.get('department')
                })
        
        # Sortiere chronologisch (älteste zuerst)
        for key in organized:
            organized[key] = sorted(organized[key], key=lambda x: x['timestamp'])
        
        self._history_cache = organized
        self._cache_timestamp = now
        
        return organized
    
    def _exponential_smoothing(self, values: List[float], alpha: float = 0.3) -> Tuple[float, float]:
        """
        Exponential Smoothing für Trend-Erkennung.
        
        Args:
            values: Liste von historischen Werten
            alpha: Smoothing-Parameter (0-1)
            
        Returns:
            (smoothed_value, trend)
        """
        if not values:
            return 0.0, 0.0
        
        if len(values) == 1:
            return values[0], 0.0
        
        # Simple Exponential Smoothing
        smoothed = values[0]
        for val in values[1:]:
            smoothed = alpha * val + (1 - alpha) * smoothed
        
        # Berechne Trend (Differenz zwischen letzten Werten)
        if len(values) >= 3:
            recent_window = min(5, len(values) // 3)
            recent_avg = np.mean(values[-recent_window:])
            older_avg = np.mean(values[:-recent_window] if recent_window < len(values) else values[:1])
            trend = (recent_avg - older_avg) / max(1, len(values) - recent_window)
        else:
            trend = values[-1] - values[0]
        
        return smoothed, trend
    
    def _calculate_seasonality_factor(self, hour: int, weekday: int, metric_type: str) -> float:
        """
        Berechnet Saisonalitätsfaktor basierend auf Tageszeit und Wochentag.
        
        Args:
            hour: Stunde des Tages (0-23)
            weekday: Wochentag (0=Montag, 6=Sonntag)
            metric_type: Art der Metrik
            
        Returns:
            Saisonalitätsfaktor (Multiplikator)
        """
        # Tageszeit-Muster (unterschiedlich je nach Metrik)
        if metric_type in ['patient_arrival', 'ed_load']:
            # Morgen und Nachmittag-Spitzen
            if 8 <= hour <= 11:
                time_factor = 1.35  # Morgenspitze
            elif 14 <= hour <= 17:
                time_factor = 1.25  # Nachmittagsspitze
            elif 18 <= hour <= 21:
                time_factor = 1.10  # Abend
            elif 22 <= hour or hour < 6:
                time_factor = 0.55  # Nacht (niedrig)
            else:
                time_factor = 0.95  # Übergang
        elif metric_type in ['bed_demand']:
            # Bettenbedarf ist stabiler, aber steigt abends
            if 16 <= hour <= 22:
                time_factor = 1.15  # Abends mehr Belegung
            elif 22 <= hour or hour < 7:
                time_factor = 1.05  # Nachts stabil
            else:
                time_factor = 0.95  # Tagsüber leichte Entlassungen
        else:
            time_factor = 1.0
        
        # Wochentags-Muster
        if weekday >= 5:  # Wochenende
            weekday_factor = 0.80 if metric_type in ['patient_arrival', 'ed_load'] else 0.95
        else:  # Werktag
            weekday_factor = 1.05
        
        return time_factor * weekday_factor
    
    def _calculate_confidence(self, 
                            history_length: int, 
                            trend_stability: float,
                            prediction_horizon: int,
                            data_quality: float = 1.0) -> float:
        """
        Adaptive Confidence-Berechnung basierend auf mehreren Faktoren.
        
        Args:
            history_length: Anzahl historischer Datenpunkte
            trend_stability: Stabilität des Trends (0-1)
            prediction_horizon: Vorhersagezeitraum in Minuten
            data_quality: Qualität der Daten (0-1)
            
        Returns:
            Confidence-Wert (0-1)
        """
        # Basis-Confidence basierend auf Datenmenge
        if history_length >= 24:  # 2 Stunden bei 5-Min-Intervallen
            history_confidence = 0.90
        elif history_length >= 12:  # 1 Stunde
            history_confidence = 0.75
        elif history_length >= 6:  # 30 Minuten
            history_confidence = 0.60
        else:
            history_confidence = 0.45
        
        # Trend-Stabilität beeinflusst Confidence
        stability_factor = 0.7 + (trend_stability * 0.3)
        
        # Zeitliche Degradierung (je weiter in der Zukunft, desto unsicherer)
        # 5 Min = 100%, 15 Min = 85%, 30 Min = 70%, 60 Min = 50%
        time_decay = max(0.50, 1.0 - (prediction_horizon / 120))
        
        # Datenqualität
        quality_factor = data_quality
        
        # Kombiniere alle Faktoren
        confidence = history_confidence * stability_factor * time_decay * quality_factor
        
        return max(0.30, min(0.95, confidence))
    
    def _detect_anomaly(self, current_value: float, historical_values: List[float]) -> bool:
        """
        Erkennt Anomalien in den Daten (z.B. plötzliche Spitzen).
        
        Returns:
            True wenn Anomalie erkannt
        """
        if len(historical_values) < 5:
            return False
        
        mean = np.mean(historical_values)
        std = np.std(historical_values)
        
        # Z-Score basierte Anomalie-Erkennung
        if std == 0:
            return False
        
        z_score = abs((current_value - mean) / std)
        
        # Anomalie wenn Z-Score > 2.5 (ca. 1% Wahrscheinlichkeit)
        return z_score > 2.5
    
    def predict_patient_arrival(self, time_horizon_minutes: int, department: str) -> Dict:
        """
        Verbesserte Vorhersage für Patientenzugang mit ML-simulierten Methoden.
        
        Args:
            time_horizon_minutes: Zeithorizont in Minuten (5, 10, 15)
            department: Abteilung
            
        Returns:
            Dict mit predicted_value, confidence, explanation, etc.
        """
        # Hole historische Daten
        history_data = self._get_historical_data(120)
        
        ed_load_history = [m['value'] for m in history_data['ed_load']]
        waiting_history = [m['value'] for m in history_data['waiting_count']]
        
        # Aktuelle Werte
        current_ed_load = ed_load_history[-1] if ed_load_history else 65.0
        current_waiting = waiting_history[-1] if waiting_history else 3
        
        # === Feature Engineering ===
        
        # 1. Exponential Smoothing für ED Load
        ed_smoothed, ed_trend = self._exponential_smoothing(ed_load_history[-24:] if len(ed_load_history) >= 24 else ed_load_history)
        
        # 2. Berechne Trend-Stabilität (für Confidence)
        if len(ed_load_history) >= 6:
            recent_variance = np.var(ed_load_history[-6:])
            overall_variance = np.var(ed_load_history) if len(ed_load_history) > 1 else recent_variance
            trend_stability = 1.0 - min(1.0, recent_variance / max(1.0, overall_variance))
        else:
            trend_stability = 0.5
        
        # 3. Anomalie-Erkennung
        is_anomaly = self._detect_anomaly(current_ed_load, ed_load_history[-20:] if len(ed_load_history) >= 20 else ed_load_history)
        
        # 4. Saisonalität
        now = datetime.now(timezone.utc)
        seasonality_factor = self._calculate_seasonality_factor(now.hour, now.weekday(), 'patient_arrival')
        
        # === Multi-Feature Prediction Model (simuliert ML-Regression) ===
        
        # Base: ED Load ist Hauptindikator für Patientenzugang
        # Formel: patients_per_5min ≈ 0.05 * ED_Load + 0.15 * Waiting + bias
        # Bei 70% ED Load → ~3.5 + ~0.45 = ~4 Patienten/5min
        base_patients_5min = (current_ed_load * 0.05) + (current_waiting * 0.15) + 0.5
        
        # Trend-Einfluss: Wenn ED Load steigt, erwarten wir mehr Patienten
        trend_contribution = ed_trend * 0.4
        
        # Kombiniere Features
        predicted_5min = base_patients_5min + trend_contribution
        
        # Skaliere auf Zeithorizont
        time_scale = time_horizon_minutes / 5.0
        predicted_value = predicted_5min * time_scale * seasonality_factor
        
        # Anomalie-Anpassung: Bei Anomalien vorsichtiger vorhersagen
        if is_anomaly:
            predicted_value *= 0.90  # Reduziere um 10%
            data_quality = 0.85
        else:
            data_quality = 1.0
        
        # Begrenze auf realistische Werte
        predicted_value = max(0, min(15 * time_scale, predicted_value))
        
        # === Confidence Berechnung ===
        confidence = self._calculate_confidence(
            history_length=len(ed_load_history),
            trend_stability=trend_stability,
            prediction_horizon=time_horizon_minutes,
            data_quality=data_quality
        )
        
        # === Explanation (für Transparenz) ===
        explanation = {
            'primary_factors': {
                'current_ed_load': round(current_ed_load, 1),
                'ed_trend': round(ed_trend, 2),
                'seasonality': round(seasonality_factor, 2)
            },
            'secondary_factors': {
                'waiting_count': current_waiting,
                'trend_stability': round(trend_stability, 2),
                'anomaly_detected': is_anomaly
            },
            'model_features': {
                'base_rate': round(base_patients_5min, 2),
                'trend_effect': round(trend_contribution, 2),
                'time_scale': time_scale
            }
        }
        
        return {
            'prediction_type': 'patient_arrival',
            'predicted_value': int(round(predicted_value)),
            'confidence': round(confidence, 3),
            'time_horizon_minutes': time_horizon_minutes,
            'department': department,
            'model_version': 'v2.0-advanced',
            'explanation': explanation
        }
    
    def predict_bed_demand(self, time_horizon_minutes: int, department: str) -> Dict:
        """
        Verbesserte Vorhersage für Bettenbedarf mit fortgeschrittenen Methoden.
        
        Args:
            time_horizon_minutes: Zeithorizont in Minuten (5, 10, 15)
            department: Abteilung
            
        Returns:
            Dict mit predicted_value (als %), confidence, explanation, etc.
        """
        # Hole Kapazitätsdaten
        capacity = self.db.get_capacity_overview()
        dept_capacity = next((c for c in capacity if c['department'] == department), None)
        
        if not dept_capacity:
            return {
                'prediction_type': 'bed_demand',
                'predicted_value': 75.0,
                'confidence': 0.50,
                'time_horizon_minutes': time_horizon_minutes,
                'department': department,
                'model_version': 'v2.0-advanced',
                'explanation': {'note': 'No department capacity data available'}
            }
        
        total_beds = dept_capacity.get('total_beds', 20)
        current_utilization = dept_capacity.get('utilization_percent', 75.0)
        current_occupied = dept_capacity.get('occupied_beds', 15)
        current_free = total_beds - current_occupied
        
        # Hole historische Daten
        history_data = self._get_historical_data(120)
        
        beds_free_history = [m['value'] for m in history_data['beds_free']]
        ed_load_history = [m['value'] for m in history_data['ed_load']]
        waiting_history = [m['value'] for m in history_data['waiting_count']]
        
        # === Feature Engineering ===
        
        # 1. Exponential Smoothing für Beds Free
        if beds_free_history:
            beds_smoothed, beds_trend = self._exponential_smoothing(beds_free_history[-24:] if len(beds_free_history) >= 24 else beds_free_history)
        else:
            beds_smoothed = current_free
            beds_trend = 0.0
        
        # 2. ED Load als Vorlaufindikator
        if ed_load_history:
            current_ed_load = ed_load_history[-1]
            ed_smoothed, ed_trend = self._exponential_smoothing(ed_load_history[-12:] if len(ed_load_history) >= 12 else ed_load_history)
        else:
            current_ed_load = 65.0
            ed_smoothed = 65.0
            ed_trend = 0.0
        
        # 3. Trend-Stabilität
        if len(beds_free_history) >= 6:
            recent_variance = np.var(beds_free_history[-6:])
            overall_variance = np.var(beds_free_history) if len(beds_free_history) > 1 else recent_variance
            trend_stability = 1.0 - min(1.0, recent_variance / max(1.0, overall_variance))
        else:
            trend_stability = 0.5
        
        # 4. Saisonalität
        now = datetime.now(timezone.utc)
        seasonality_factor = self._calculate_seasonality_factor(now.hour, now.weekday(), 'bed_demand')
        
        # 5. Anomalie-Erkennung
        is_anomaly = self._detect_anomaly(current_free, beds_free_history[-20:] if len(beds_free_history) >= 20 else beds_free_history)
        
        # === Multi-Feature Prediction Model ===
        
        # Basis-Modell: Kombiniere direkten Trend mit indirekten Indikatoren
        
        # A) Direkte Trend-Projektion (Betten werden weiter frei/belegt)
        hours_ahead = time_horizon_minutes / 60.0
        
        # Beds Trend ist in Betten pro Eintrag (~5 Min)
        # Konvertiere zu Betten pro Stunde
        beds_trend_per_hour = beds_trend * 12  # 12 Einträge pro Stunde
        projected_beds_change = beds_trend_per_hour * hours_ahead
        
        # B) ED Load Einfluss (hohe ED Load → mehr Aufnahmen → weniger freie Betten)
        # ED Load über Durchschnitt (65%) führt zu mehr Belegung
        ed_impact_on_beds = -(current_ed_load - 65.0) * 0.08 * hours_ahead
        
        # C) Waiting Queue Einfluss (mehr Wartende → bald mehr Aufnahmen)
        current_waiting = waiting_history[-1] if waiting_history else 3
        waiting_impact = -(current_waiting - 3) * 0.15 * hours_ahead
        
        # Kombiniere alle Effekte
        predicted_free_beds = current_free + projected_beds_change + ed_impact_on_beds + waiting_impact
        
        # Saisonalität einbeziehen (sanftere Anpassung)
        # Bei Bed Demand: Faktor > 1 bedeutet mehr Belegung → weniger freie Betten
        if seasonality_factor > 1.0:
            seasonality_adjustment = -(seasonality_factor - 1.0) * 2  # Reduziere freie Betten um bis zu 2
        else:
            seasonality_adjustment = (1.0 - seasonality_factor) * 2  # Erhöhe freie Betten um bis zu 2
        
        predicted_free_beds += seasonality_adjustment
        
        # Begrenze auf physische Grenzen
        predicted_free_beds = max(0, min(total_beds, predicted_free_beds))
        
        # Konvertiere zu Auslastung in %
        predicted_occupied = total_beds - predicted_free_beds
        predicted_utilization = (predicted_occupied / total_beds) * 100 if total_beds > 0 else current_utilization
        
        # Anomalie-Anpassung (vor dem finalen Clamping)
        if is_anomaly:
            # Bei Anomalien: Glätte Vorhersage Richtung historischem Durchschnitt
            if beds_free_history:
                historical_avg_free = np.mean(beds_free_history)
                historical_avg_util = ((total_beds - historical_avg_free) / total_beds) * 100
                # Begrenze historischen Durchschnitt auch
                historical_avg_util = max(0.0, min(100.0, historical_avg_util))
                predicted_utilization = predicted_utilization * 0.7 + historical_avg_util * 0.3
            data_quality = 0.85
        else:
            data_quality = 1.0
        
        # Finale Begrenzung auf realistische Werte (0-100%)
        predicted_utilization = max(0.0, min(100.0, predicted_utilization))
        
        # === Confidence Berechnung ===
        confidence = self._calculate_confidence(
            history_length=len(beds_free_history),
            trend_stability=trend_stability,
            prediction_horizon=time_horizon_minutes,
            data_quality=data_quality
        )
        
        # === Explanation ===
        explanation = {
            'primary_factors': {
                'current_utilization': round(current_utilization, 1),
                'beds_trend': round(beds_trend, 2),
                'ed_load': round(current_ed_load, 1)
            },
            'secondary_factors': {
                'waiting_queue': current_waiting,
                'seasonality': round(seasonality_factor, 2),
                'trend_stability': round(trend_stability, 2),
                'anomaly_detected': is_anomaly
            },
            'model_features': {
                'trend_effect': round(projected_beds_change, 2),
                'ed_impact': round(ed_impact_on_beds, 2),
                'waiting_impact': round(waiting_impact, 2)
            }
        }
        
        return {
            'prediction_type': 'bed_demand',
            'predicted_value': round(predicted_utilization, 1),
            'confidence': round(confidence, 3),
            'time_horizon_minutes': time_horizon_minutes,
            'department': department,
            'model_version': 'v2.0-advanced',
            'explanation': explanation
        }
    
    def generate_predictions(self, time_horizons: List[int] = [5, 10, 15]) -> List[Dict]:
        """
        Generiert optimierte Vorhersagen über relevante Abteilungen.
        
        Intelligente Auswahl basierend auf:
        - Aktuelle Auslastung
        - Abteilungsrelevanz
        - Datenqualität
        
        Args:
            time_horizons: Liste von Zeithorizonten in Minuten
            
        Returns:
            Liste von Vorhersagen (flexibel 9-15 Vorhersagen)
        """
        predictions = []
        
        # Hole alle Abteilungen mit Kapazitätsdaten
        capacity_data = self.db.get_capacity_overview()
        
        if not capacity_data:
            return []
        
        # Priorisiere Abteilungen nach Relevanz
        # 1. ER und ICU sind immer wichtig
        # 2. Abteilungen mit hoher Auslastung (>75%)
        # 3. Abteilungen mit Trends
        
        priority_depts = []
        high_util_depts = []
        normal_depts = []
        
        for dept_data in capacity_data:
            dept = dept_data['department']
            util = dept_data.get('utilization_percent', 0)
            
            if dept in ['ER', 'ICU']:
                priority_depts.append(dept)
            elif util >= 75:
                high_util_depts.append(dept)
            else:
                normal_depts.append(dept)
        
        # Wähle 2-3 Abteilungen für Patientenzugang
        patient_arrival_depts = []
        if 'ER' in priority_depts:
            patient_arrival_depts.append('ER')
        patient_arrival_depts.extend(high_util_depts[:1])
        if len(patient_arrival_depts) < 2 and priority_depts:
            patient_arrival_depts.extend([d for d in priority_depts if d not in patient_arrival_depts][:2-len(patient_arrival_depts)])
        if len(patient_arrival_depts) < 2:
            patient_arrival_depts.extend(normal_depts[:2-len(patient_arrival_depts)])
        
        # Wähle 2-3 Abteilungen für Bettenbedarf
        bed_demand_depts = []
        remaining_priority = [d for d in priority_depts if d not in patient_arrival_depts]
        bed_demand_depts.extend(remaining_priority[:1])
        bed_demand_depts.extend([d for d in high_util_depts if d not in patient_arrival_depts][:1])
        if len(bed_demand_depts) < 2:
            bed_demand_depts.extend([d for d in normal_depts if d not in patient_arrival_depts and d not in bed_demand_depts][:2-len(bed_demand_depts)])
        
        # Generiere Vorhersagen für verschiedene Zeithorizonte
        for dept in patient_arrival_depts[:2]:
            for horizon in time_horizons:
                pred = self.predict_patient_arrival(horizon, dept)
                predictions.append(pred)
        
        for dept in bed_demand_depts[:2]:
            for horizon in time_horizons:
                pred = self.predict_bed_demand(horizon, dept)
                predictions.append(pred)
        self._save_predictions(predictions)
        
        return predictions
    
    def _save_predictions(self, predictions: List[Dict]):
        """Speichert Vorhersagen in die Datenbank (thread-safe)"""
        self.db.save_predictions_batch(predictions)

