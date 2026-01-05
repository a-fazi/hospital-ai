"""
Hilfsfunktionen für HospitalFlow

Diese Datei enthält:
- Vorhersage-Algorithmen (Patientenzugang, Bettenbedarf)
- Berechnungsfunktionen (Inventarstatus, Kapazitätsstatus, Verbrauch)
- Formatierungshelfer (Zeit, Dauer, Farben)
- Status- und Schweregrad-Berechnungen

Alle Funktionen sind darauf ausgelegt, realistische Krankenhausmetriken
zu berechnen und zu formatieren.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import random
from zoneinfo import ZoneInfo

# Lokale Zeitzone (UTC+1 für Berlin)
LOCAL_TIMEZONE = 'Europe/Berlin'


def calculate_prediction_confidence(base_value: float, time_horizon: int) -> float:
    """
    Berechnet das Prognose-Vertrauen basierend auf dem Zeithorizont.
    
    Das Vertrauen sinkt mit zunehmendem Zeithorizont, da kurzfristige
    Vorhersagen zuverlässiger sind als langfristige.
    
    Args:
        base_value (float): Basis-Vorhersagewert (wird hier nicht verwendet, aber für zukünftige Erweiterungen)
        time_horizon (int): Zeithorizont in Minuten (z.B. 5, 10, 15)
    
    Returns:
        float: Vertrauen zwischen 0.6 und 1.0 (gerundet auf 2 Dezimalstellen)
    """
    # Kürzere Horizonte = höheres Vertrauen
    # Formel: Mindestens 0.6, sinkt linear mit Zeithorizont
    # Bei 0 Minuten: 1.0, bei 60+ Minuten: 0.6
    confidence = max(0.6, 1.0 - (time_horizon / 60) * 0.3)
    return round(confidence, 2)


def round_timestamp_to_seconds(dt):
    """
    Rundet einen Timestamp auf Sekunden (entfernt Millisekunden/Mikrosekunden).
    
    Unterstützt:
    - datetime-Objekte
    - pandas Timestamp/Series
    - String-Timestamps
    
    Args:
        dt: Timestamp als datetime, pandas Timestamp, pandas Series oder String
    
    Returns:
        datetime oder pandas Series mit auf Sekunden gerundeten Timestamps
    """
    import pandas as pd
    
    if isinstance(dt, pd.Series):
        # Für pandas Series: runde jeden Wert auf Sekunden
        return pd.to_datetime(dt).dt.floor('S')
    elif isinstance(dt, pd.Timestamp):
        # Für pandas Timestamp: runde auf Sekunden
        return dt.floor('S')
    elif isinstance(dt, datetime):
        # Für datetime: entferne Mikrosekunden
        return dt.replace(microsecond=0)
    elif isinstance(dt, str):
        # Für String: parse und runde
        try:
            parsed = pd.to_datetime(dt)
            return parsed.floor('S').to_pydatetime()
        except:
            return dt
    else:
        # Fallback: versuche zu konvertieren
        try:
            parsed = pd.to_datetime(dt)
            return parsed.floor('S').to_pydatetime()
        except:
            return dt


def aggregate_to_30_seconds(df, timestamp_col='timestamp', value_col='value', agg_func='mean'):
    """
    Aggregiert einen DataFrame auf 30-Sekunden-Intervalle.
    
    Rundet Timestamps auf 30-Sekunden-Intervalle (z.B. 00:00:00, 00:00:30, 00:01:00)
    und aggregiert die Werte innerhalb jedes Intervalls.
    
    Args:
        df: pandas DataFrame mit Zeitreihen-Daten
        timestamp_col: Name der Timestamp-Spalte (Standard: 'timestamp')
        value_col: Name der Wert-Spalte (Standard: 'value')
        agg_func: Aggregationsfunktion ('mean', 'last', 'first', 'max', 'min')
    
    Returns:
        pandas DataFrame mit aggregierten Daten auf 30-Sekunden-Intervalle
    """
    import pandas as pd
    
    if df.empty or timestamp_col not in df.columns:
        return df
    
    # Erstelle Kopie des DataFrames
    df_agg = df.copy()
    
    # Konvertiere Timestamp-Spalte zu datetime
    df_agg[timestamp_col] = pd.to_datetime(df_agg[timestamp_col])
    
    # Runde auf 30-Sekunden-Intervalle
    # Verwende floor um auf das nächste 30-Sekunden-Intervall abzurunden
    df_agg['_30s_interval'] = df_agg[timestamp_col].dt.floor('30S')
    
    # Aggregiere nach 30-Sekunden-Intervallen
    if agg_func == 'mean':
        agg_dict = {value_col: 'mean'}
    elif agg_func == 'last':
        agg_dict = {value_col: 'last'}
    elif agg_func == 'first':
        agg_dict = {value_col: 'first'}
    elif agg_func == 'max':
        agg_dict = {value_col: 'max'}
    elif agg_func == 'min':
        agg_dict = {value_col: 'min'}
    else:
        agg_dict = {value_col: 'mean'}  # Default
    
    # Behalte alle anderen Spalten (z.B. 'department', 'Abteilung' für Farben)
    other_cols = [col for col in df_agg.columns if col not in [timestamp_col, value_col, '_30s_interval']]
    if other_cols:
        # Für andere Spalten: nimm den ersten Wert pro Intervall
        for col in other_cols:
            agg_dict[col] = 'first'
    
    # Gruppiere und aggregiere
    df_agg = df_agg.groupby('_30s_interval', as_index=False).agg(agg_dict)
    
    # Ersetze _30s_interval durch timestamp
    df_agg[timestamp_col] = df_agg['_30s_interval']
    df_agg = df_agg.drop(columns=['_30s_interval'])
    
    # Sortiere nach Timestamp
    df_agg = df_agg.sort_values(timestamp_col)
    
    return df_agg


def convert_utc_to_local(utc_timestamp):
    """
    Konvertiert einen UTC-Timestamp in lokale Zeit (Europe/Berlin).
    
    Unterstützt verschiedene Eingabeformate:
    - datetime-Objekte (mit oder ohne timezone)
    - String-Timestamps (ISO-Format oder SQLite-Format)
    
    Args:
        utc_timestamp: UTC-Timestamp als datetime, String oder pandas Timestamp
    
    Returns:
        datetime: Zeitstempel in lokaler Zeitzone (timezone-naive für einfache Anzeige)
    """
    # Handle pandas Timestamp
    if hasattr(utc_timestamp, 'to_pydatetime'):
        utc_timestamp = utc_timestamp.to_pydatetime()
    
    # Parse String zu datetime
    if isinstance(utc_timestamp, str):
        try:
            # Versuche ISO-Format (z.B. "2024-01-01T12:00:00Z" oder "2024-01-01T12:00:00+00:00")
            dt = datetime.fromisoformat(utc_timestamp.replace('Z', '+00:00'))
        except:
            try:
                # Versuche SQLite-Format mit Mikrosekunden
                dt = datetime.strptime(utc_timestamp, '%Y-%m-%d %H:%M:%S.%f')
                dt = dt.replace(tzinfo=timezone.utc)
            except:
                try:
                    # Versuche SQLite-Format ohne Mikrosekunden
                    dt = datetime.strptime(utc_timestamp, '%Y-%m-%d %H:%M:%S')
                    dt = dt.replace(tzinfo=timezone.utc)
                except:
                    # Fallback: return None wenn Parsing fehlschlägt
                    return None
    elif isinstance(utc_timestamp, datetime):
        dt = utc_timestamp
    else:
        return None
    
    # Stelle sicher, dass datetime timezone-aware ist (behandle als UTC wenn nicht gesetzt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Konvertiere zu lokaler Zeitzone
    local_dt = dt.astimezone(ZoneInfo(LOCAL_TIMEZONE))
    
    # Entferne timezone-Info für einfache Anzeige (da wir in lokaler Zeit sind)
    return local_dt.replace(tzinfo=None)


def format_time_ago(timestamp: str) -> str:
    """
    Formatiert einen Zeitstempel als relative Zeit (z.B. "vor 5 Min.", "vor 2 Std.").
    
    Unterstützt verschiedene Zeitstempelformate:
    - ISO-Format (z.B. "2024-01-01T12:00:00Z")
    - SQLite-Format mit/ohne Mikrosekunden (z.B. "2024-01-01 12:00:00.000000")
    - datetime-Objekte
    
    Die Zeitdifferenz wird korrekt berechnet, auch wenn Timestamps in UTC gespeichert sind.
    
    Args:
        timestamp (str): Zeitstempel als String oder datetime-Objekt (in UTC)
    
    Returns:
        str: Formatierte relative Zeit (z.B. "gerade eben", "vor 5 Min.", "vor 2 Std.", "vor 3 Tg.")
    """
    # ===== ZEITSTEMPEL PARSEN =====
    # Versuche verschiedene Zeitstempelformate zu parsen
    if isinstance(timestamp, str):
        try:
            # Versuche zuerst ISO-Format (z.B. "2024-01-01T12:00:00Z")
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            # Stelle sicher, dass es timezone-aware ist
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except:
            try:
                # Versuche SQLite-Datumsformat mit Mikrosekunden
                # SQLite CURRENT_TIMESTAMP gibt UTC zurück, also als UTC behandeln
                dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S.%f')
                dt = dt.replace(tzinfo=timezone.utc)
            except:
                try:
                    # Versuche SQLite-Datumsformat ohne Mikrosekunden
                    dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                    dt = dt.replace(tzinfo=timezone.utc)
                except:
                    # Fallback auf "kürzlich", wenn das Parsen fehlschlägt
                    return "kürzlich"
    else:
        dt = timestamp
        # Stelle sicher, dass es timezone-aware ist (behandle als UTC wenn nicht gesetzt)
        if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    
    # ===== ZEITDIFFERENZ BERECHNEN =====
    # Vergleiche UTC-Zeit mit UTC-Zeit für korrekte Zeitdifferenz
    now_utc = datetime.now(timezone.utc)
    diff = now_utc - dt
    
    # ===== RELATIVE ZEIT FORMATIEREN =====
    # Formatiere basierend auf der Zeitdifferenz
    if diff.total_seconds() < 60:
        return "gerade eben"  # Weniger als 1 Minute
    elif diff.total_seconds() < 3600:  # Weniger als 1 Stunde
        mins = int(diff.total_seconds() / 60)
        return f"vor {mins} Min."
    elif diff.total_seconds() < 86400:  # Weniger als 1 Tag
        hours = int(diff.total_seconds() / 3600)
        return f"vor {hours} Std."
    else:  # 1 Tag oder mehr
        days = int(diff.total_seconds() / 86400)
        return f"vor {days} Tg."


def get_severity_color(severity: str) -> str:
    """
    Ermittelt die Farbe für einen Schweregrad-Badge.
    
    Farben basieren auf der Schweregrad-Skala:
    - Kritisch/Hoch: Rot (höchste Priorität)
    - Mittel: Bernstein/Gelb (mittlere Priorität)
    - Niedrig: Smaragd/Grün (niedrige Priorität)
    
    Args:
        severity (str): Schweregrad auf Deutsch oder Englisch
                       ("hoch"/"high", "mittel"/"medium", "niedrig"/"low", "kritisch"/"critical")
    
    Returns:
        str: Hex-Farbcode (z.B. "#DC2626" für rot)
    """
    farben = {
        "hoch": "#DC2626",      # rot-600
        "mittel": "#F59E0B",    # bernstein-500
        "niedrig": "#10B981",   # smaragd-500
        "kritisch": "#991B1B",  # rot-800
        # Für Kompatibilität mit englischen Keys:
        "high": "#DC2626",
        "medium": "#F59E0B",
        "low": "#10B981",
        "critical": "#991B1B",
    }
    return farben.get(severity.lower(), "#6B7280")  # Standard: Grau


def get_priority_color(priority: str) -> str:
    """
    Ermittelt die Farbe für einen Prioritäts-Badge.
    
    Priorität verwendet dieselbe Farbcodierung wie Schweregrad.
    
    Args:
        priority (str): Priorität auf Deutsch oder Englisch
    
    Returns:
        str: Hex-Farbcode
    """
    return get_severity_color(priority)


def get_risk_color(risk_level: str) -> str:
    """
    Ermittelt die Farbe für einen Risikostufen-Badge.
    
    Risikostufen verwenden dieselbe Farbcodierung wie Schweregrad.
    Unterstützt sowohl deutsche als auch englische Bezeichnungen.
    
    Args:
        risk_level (str): Risikostufe auf Deutsch oder Englisch
    
    Returns:
        str: Hex-Farbcode
    """
    return get_severity_color(risk_level)


def get_status_color(status: str) -> str:
    """
    Ermittelt die Farbe für einen Status-Badge.
    
    Status-Farben unterscheiden sich von Schweregrad-Farben:
    - Abgeschlossen/Akzeptiert/Betriebsbereit: Grün (positiver Status)
    - In Bearbeitung: Blau (aktiver Status)
    - Ausstehend/Wartung: Bernstein/Gelb (wartend)
    - Abgelehnt/Kritisch: Rot (negativer/kritischer Status)
    
    Args:
        status (str): Status auf Deutsch oder Englisch
    
    Returns:
        str: Hex-Farbcode
    """
    farben = {
        # Deutsch
        "ausstehend": "#F59E0B",      # bernstein-500 (wartend)
        "in_bearbeitung": "#3B82F6",  # blau-500 (aktiv)
        "abgeschlossen": "#10B981",   # smaragd-500 (erfolgreich)
        "akzeptiert": "#10B981",      # smaragd-500 (erfolgreich)
        "abgelehnt": "#EF4444",       # rot-500 (negativ)
        "betriebsbereit": "#10B981",  # smaragd-500 (operativ)
        "wartung": "#F59E0B",         # bernstein-500 (wartend)
        "kritisch": "#DC2626",        # rot-600 (kritisch)
        "geplant": "#F59E0B",         # bernstein-500 (geplant)
        # Englisch (Kompatibilität)
        "pending": "#F59E0B",
        "in_progress": "#3B82F6",
        "completed": "#10B981",
        "accepted": "#10B981",
        "rejected": "#EF4444",
        "operational": "#10B981",
        "maintenance": "#F59E0B",
        "critical": "#DC2626",
        "planned": "#F59E0B",         # bernstein-500 (geplant)
    }
    return farben.get(status.lower(), "#6B7280")  # Standard: Grau


def calculate_inventory_status(current: int, min_threshold: int, max_capacity: int) -> Dict:
    """
    Berechnet den Inventarstatus basierend auf aktuellem Bestand, Mindest-Schwelle und maximaler Kapazität.
    
    Bestimmt ob der Bestand niedrig oder kritisch ist:
    - Normal: >= Mindest-Schwelle
    - Niedrig: < Mindest-Schwelle
    - Kritisch: < 50% der Mindest-Schwelle
    
    Args:
        current (int): Aktueller Bestand
        min_threshold (int): Mindest-Schwelle (Nachbestellung empfohlen)
        max_capacity (int): Maximale Kapazität (für Prozentsatz-Berechnung)
    
    Returns:
        Dict: Dictionary mit:
            - percentage: Auslastung in Prozent (0-100)
            - is_low: Boolean ob Bestand niedrig ist
            - is_critical: Boolean ob Bestand kritisch ist
            - status: Status auf Deutsch ("normal", "niedrig", "kritisch")
            - status_en: Status auf Englisch ("normal", "low", "critical")
    """
    # Berechne Auslastung in Prozent
    prozent = (current / max_capacity) * 100 if max_capacity > 0 else 0
    
    # Prüfe ob Bestand niedrig oder kritisch ist
    ist_niedrig = current < min_threshold
    ist_kritisch = current < (min_threshold * 0.5)  # Kritisch bei < 50% der Mindest-Schwelle
    
    # Status sowohl auf Deutsch als auch Englisch für Kompatibilität
    if ist_kritisch:
        status = "kritisch"
        status_en = "critical"
    elif ist_niedrig:
        status = "niedrig"
        status_en = "low"
    else:
        status = "normal"
        status_en = "normal"
    
    return {
        "percentage": round(prozent, 1),
        "is_low": ist_niedrig,
        "is_critical": ist_kritisch,
        "status": status,
        "status_en": status_en
    }


def calculate_capacity_status(utilization: float) -> Dict:
    """
    Berechnet den Kapazitätsstatus basierend auf Auslastung.
    
    Kategorisiert die Auslastung in verschiedene Stufen:
    - Niedrig: < 50% (Grün)
    - Moderat: 50-75% (Blau)
    - Hoch: 75-90% (Bernstein/Gelb)
    - Kritisch: >= 90% (Rot)
    
    Args:
        utilization (float): Auslastung als Dezimalzahl (0.0-1.0) oder Prozentsatz (0-100)
    
    Returns:
        Dict: Dictionary mit:
            - status: Status auf Deutsch
            - status_en: Status auf Englisch
            - color: Hex-Farbcode für die Anzeige
            - percentage: Auslastung in Prozent (0-100)
    """
    # Normalisiere utilization auf 0.0-1.0 falls nötig
    if utilization > 1.0:
        utilization = utilization / 100.0
    
    if utilization >= 0.9:
        # Kritisch: >= 90% Auslastung
        status = "kritisch"
        status_en = "critical"
        color = "#DC2626"  # Rot
    elif utilization >= 0.75:
        # Hoch: 75-90% Auslastung
        status = "hoch"
        status_en = "high"
        color = "#F59E0B"  # Bernstein
    elif utilization >= 0.5:
        # Moderat: 50-75% Auslastung
        status = "moderat"
        status_en = "moderate"
        color = "#3B82F6"  # Blau
    else:
        # Niedrig: < 50% Auslastung
        status = "niedrig"
        status_en = "low"
        color = "#10B981"  # Grün
    
    return {
        "status": status,
        "status_en": status_en,
        "color": color,
        "percentage": round(utilization * 100, 1)
    }


def format_duration_minutes(minutes: int) -> str:
    """
    Formatiert eine Dauer in Minuten als lesbare Zeichenkette.
    
    Beispiele:
    - 30 → "30 Min."
    - 90 → "1 Std. 30 Min."
    - 120 → "2 Std."
    
    Args:
        minutes (int): Dauer in Minuten
    
    Returns:
        str: Formatierte Dauer (z.B. "30 Min.", "2 Std. 15 Min.")
    """
    if minutes < 60:
        # Weniger als 1 Stunde: nur Minuten
        return f"{minutes} Min."
    else:
        # 1 Stunde oder mehr: Stunden und Minuten
        stunden = minutes // 60
        minuten = minutes % 60
        if minuten == 0:
            # Ganzzahlige Stunden: nur Stunden anzeigen
            return f"{stunden} Std."
        return f"{stunden} Std. {minuten} Min."


def get_department_name_mapping() -> Dict[str, str]:
    """
    Gibt das zentrale Mapping aller Abteilungen des Waldkrankenhauses Erlangen zurück.
    
    Mapping von Abteilungs-Codes (englisch) zu deutschen Vollnamen.
    Dies ist die zentrale Quelle für alle Abteilungsnamen im System.
    
    Returns:
        Dict[str, str]: Mapping von Abteilungs-Code zu deutschem Vollnamen
    """
    return {
        # Waldkrankenhaus Erlangen - 9 Fachabteilungen + Notaufnahme
        "ER": "Notaufnahme",
        "ICU": "Klinik für Anästhesie und Intensivmedizin",
        "Surgery": "Klinik für Allgemein- und Viszeralchirurgie",
        "Cardiology": "Klinik für Kardiologie und Angiologie (Medizinische Klinik I)",
        "Gastroenterology": "Klinik für Gastroenterologie und Onkologie (Medizinische Klinik II)",
        "Geriatrics": "Klinik für Akutgeriatrie (Medizinische Klinik III / Geriatrie-Zentrum Erlangen)",
        "Orthopedics": "Klinik für Orthopädie und Unfallchirurgie",
        "Urology": "Klinik für Urologie",
        "SpineCenter": "Interdisziplinäres Zentrum für Wirbelsäulen- und Skoliosetherapie",
        "ENT": "Belegabteilung für Hals-, Nasen-, Ohrenheilkunde",
        # Alte/alternative Bezeichnungen für Kompatibilität
        "ED": "Notaufnahme",
        "General Ward": "Allgemeinstation",
        "Radiology": "Radiologie",
        "Neurology": "Neurologie",
        "Pediatrics": "Pädiatrie",
        "Oncology": "Onkologie",
        "Maternity": "Geburtshilfe",
    }


def get_department_display_name(dept_code: str) -> str:
    """
    Gibt den deutschen Anzeigenamen für eine Abteilung zurück.
    
    Args:
        dept_code (str): Abteilungs-Code (z.B. "ER", "ICU", "Cardiology")
    
    Returns:
        str: Deutscher Vollname der Abteilung, oder der Code selbst falls nicht gefunden
    """
    mapping = get_department_name_mapping()
    return mapping.get(dept_code, dept_code)


def get_department_color(department: str) -> str:
    """
    Gibt eine konsistente Farbe für eine Abteilung zurück.
    
    Jede Abteilung hat eine zugewiesene Farbe für die Visualisierung
    in Diagrammen und Übersichten.
    
    Args:
        department (str): Abteilungsname (auf Deutsch oder Englisch)
    
    Returns:
        str: Hex-Farbcode für die Abteilung
    """
    farben = {
        # Waldkrankenhaus Erlangen Abteilungen (Codes)
        "ER": "#EF4444",              # Notaufnahme (Rot)
        "ED": "#EF4444",              # Notaufnahme (Rot) - Alternative
        "ICU": "#DC2626",             # Anästhesie und Intensivmedizin (Dunkelrot)
        "Surgery": "#3B82F6",         # Allgemein- und Viszeralchirurgie (Blau)
        "Cardiology": "#8B5CF6",      # Kardiologie (Lila)
        "Orthopedics": "#F59E0B",     # Orthopädie und Unfallchirurgie (Bernstein)
        "Urology": "#06B6D4",         # Urologie (Cyan)
        "Gastroenterology": "#10B981", # Gastroenterologie (Grün)
        "Geriatrics": "#84CC16",      # Akutgeriatrie (Lime)
        "SpineCenter": "#6366F1",     # Wirbelsäulen- und Skoliosetherapie (Indigo)
        "ENT": "#EC4899",             # Hals-, Nasen-, Ohrenheilkunde (Pink) - NEU
        "General Ward": "#10B981",    # Allgemeinstation (Grün)
        # Deutsche Abteilungsnamen für Kompatibilität
        "Notaufnahme": "#EF4444",
        "Anästhesie und Intensivmedizin": "#DC2626",
        "Intensivstation": "#DC2626",  # Alte Bezeichnung
        "Allgemein- und Viszeralchirurgie": "#3B82F6",
        "Chirurgie": "#3B82F6",        # Alte Bezeichnung
        "Kardiologie": "#8B5CF6",
        "Klinik für Kardiologie und Angiologie (Medizinische Klinik I)": "#8B5CF6",
        "Orthopädie und Unfallchirurgie": "#F59E0B",
        "Orthopädie": "#F59E0B",       # Alte Bezeichnung
        "Urologie": "#06B6D4",
        "Gastroenterologie": "#10B981",
        "Klinik für Gastroenterologie und Onkologie (Medizinische Klinik II)": "#10B981",
        "Akutgeriatrie": "#84CC16",
        "Klinik für Akutgeriatrie (Medizinische Klinik III / Geriatrie-Zentrum Erlangen)": "#84CC16",
        "Wirbelsäulen- und Skoliosetherapie": "#6366F1",
        "Interdisziplinäres Zentrum für Wirbelsäulen- und Skoliosetherapie": "#6366F1",
        "Belegabteilung für Hals-, Nasen-, Ohrenheilkunde": "#EC4899",
        "Hals-, Nasen-, Ohrenheilkunde": "#EC4899",
        "HNO": "#EC4899",
        "Allgemeinstation": "#10B981",
    }
    return farben.get(department, "#6B7280")  # Standard: Grau für unbekannte Abteilungen


def get_max_usage_hours(device_type: str) -> int:
    """
    Gibt die maximale Betriebsstunden für einen Gerätetyp zurück.
    
    Definiert nach wie vielen Betriebsstunden ein Gerät gewartet werden sollte.
    Verschiedene Gerätetypen haben unterschiedliche Wartungsintervalle basierend
    auf ihrer Komplexität und Nutzung.
    
    Args:
        device_type (str): Gerätetyp (z.B. "Beatmungsgerät", "Monitor")
    
    Returns:
        int: Maximale Betriebsstunden vor Wartung (Standard: 4000)
    """
    max_hours_mapping = {
        'Beatmungsgerät': 4200,      # Kritische Ausrüstung: häufige Wartung
        'Monitor': 6000,              # Standard-Monitore: längere Intervalle
        'OP-Monitor': 6000,           # OP-Monitore: ähnlich wie Standard
        'Defibrillator': 3000,        # Kritische Ausrüstung: häufige Wartung
        'CT-Gerät': 5000,             # Bildgebung: mittlere Intervalle
        'MRT-Gerät': 5500,            # Bildgebung: mittlere Intervalle
        'Röntgengerät': 4000,         # Bildgebung: häufigere Wartung
        'EKG-Gerät': 3000,            # Diagnostik: häufigere Wartung
        'Ultraschallgerät': 3500,     # Bildgebung: häufigere Wartung
    }
    return max_hours_mapping.get(device_type, 4000)  # Default: 4000 Stunden


def get_maintenance_duration(device_type: str) -> int:
    """
    Gibt die Standard-Wartungsdauer in Minuten für einen Gerätetyp zurück
    
    Args:
        device_type: Der Gerätetyp
        
    Returns:
        Wartungsdauer in Minuten
    """
    # Mapping für Wartungsdauern basierend auf Gerätetyp
    duration_mapping = {
        # Bildgebung - längere Wartung
        'CT-Gerät': 240,  # 4 Stunden
        'MRT-Gerät': 300,  # 5 Stunden
        'Röntgengerät': 180,  # 3 Stunden
        'Ultraschallgerät': 120,  # 2 Stunden
        # Lebensunterstützung - kritisch, aber schnellere Wartung
        'Beatmungsgerät': 90,  # 1.5 Stunden
        'Defibrillator': 60,  # 1 Stunde
        # Überwachung - kürzere Wartung
        'Monitor': 60,  # 1 Stunde
        'OP-Monitor': 60,  # 1 Stunde
        'EKG-Gerät': 45,  # 45 Minuten
        # Chirurgisch
        'Surgical': 120,  # 2 Stunden
        # Standard für unbekannte Typen
    }
    
    # Prüfe auch englische Bezeichnungen
    english_mapping = {
        'Imaging': 180,
        'Life Support': 90,
        'Emergency': 60,
        'Monitoring': 60,
        'Therapy': 90,
        'Surgical': 120,
        'Diagnostic': 90,
        'Other': 60,
    }
    
    # Zuerst spezifische deutsche Bezeichnungen prüfen
    if device_type in duration_mapping:
        return duration_mapping[device_type]
    
    # Dann englische Bezeichnungen
    if device_type in english_mapping:
        return english_mapping[device_type]
    
    # Default: 90 Minuten (1.5 Stunden)
    return 90


def suggest_maintenance_times(device: Dict, predictions: List[Dict], days_ahead: int = 30) -> List[Dict]:
    """
    Schlägt optimale Wartungszeiten für ein Gerät vor.
    
    Args:
        device: Gerätedaten (mit urgency_level, next_maintenance_due, department, device_type)
        predictions: Liste von Patientenvorhersagen (mit timestamp, predicted_value, department)
        days_ahead: Wie viele Tage in die Zukunft schauen (Standard: 30)
        
    Returns:
        Liste von vorgeschlagenen Zeitfenstern mit Score, sortiert nach Score (höchster zuerst)
        Jedes Element enthält: start_time, end_time, score, expected_patients, reason
    """
    from datetime import datetime, timedelta, timezone
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    suggestions = []
    
    # Bestimme Zeitfenster basierend auf Dringlichkeit
    urgency = device.get('urgency_level', '').lower()
    if urgency in ['high', 'hoch']:
        max_days = 3
        min_days = 0
    elif urgency in ['medium', 'mittel']:
        max_days = 7
        min_days = 1
    else:  # low/niedrig
        max_days = min(days_ahead, 30)
        min_days = 3
    
    # Hole next_maintenance_due
    next_due = device.get('next_maintenance_due')
    next_due_date = None
    if next_due:
        try:
            if isinstance(next_due, str):
                next_due_date = datetime.strptime(next_due, '%Y-%m-%d').date()
            elif isinstance(next_due, datetime):
                next_due_date = next_due.date()
            else:
                # Versuche als date zu behandeln
                next_due_date = next_due if hasattr(next_due, 'year') else None
            if next_due_date:
                days_until_due = (next_due_date - now.date()).days
            else:
                days_until_due = None
        except:
            days_until_due = None
    else:
        days_until_due = None
    
    # Wartungsdauer
    device_type = device.get('device_type', '')
    duration_minutes = get_maintenance_duration(device_type)
    duration_hours = duration_minutes / 60.0
    
    # Abteilung des Geräts
    department = device.get('department', '')
    
    # Filtere Vorhersagen für diese Abteilung
    dept_predictions = [p for p in predictions if p.get('department') == department and p.get('prediction_type') == 'patient_arrival']
    
    # Generiere Kandidaten-Zeiten in 3-Stunden-Schritten
    # Bevorzuge Zeiten außerhalb der Hauptarbeitszeit (weniger Patienten)
    # Ideal: 22:00-06:00 oder 12:00-14:00 (Mittagspause)
    
    current_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if min_days > 0:
        current_date += timedelta(days=min_days)
    
    end_date = current_date + timedelta(days=max_days - min_days)
    
    # Generiere Zeitfenster-Kandidaten
    candidate_times = []
    date = current_date
    
    while date <= end_date:
        # Bevorzuge verschiedene Tageszeiten
        time_slots = [
            (2, 0),   # 02:00 - Nacht (sehr niedrige Patientenlast)
            (6, 0),   # 06:00 - Früher Morgen
            (12, 0),  # 12:00 - Mittagspause
            (14, 0),  # 14:00 - Nachmittag
            (22, 0),  # 22:00 - Später Abend
        ]
        
        for hour, minute in time_slots:
            candidate_time = date.replace(hour=hour, minute=minute)
            if candidate_time > now:  # Nur zukünftige Zeiten
                candidate_times.append(candidate_time)
        
        date += timedelta(days=1)
    
    # Bewerte jeden Kandidaten
    for start_time in candidate_times:
        end_time = start_time + timedelta(hours=duration_hours)
        
        # Berechne erwartete Patientenlast für dieses Zeitfenster
        expected_patients = 0
        prediction_count = 0
        
        # Finde relevante Vorhersagen für dieses Zeitfenster
        for pred in dept_predictions:
            pred_time = pred.get('timestamp')
            if isinstance(pred_time, str):
                try:
                    pred_time = datetime.strptime(pred_time, '%Y-%m-%d %H:%M:%S')
                except:
                    try:
                        pred_time = datetime.strptime(pred_time, '%Y-%m-%d')
                    except:
                        continue
            elif not isinstance(pred_time, datetime):
                continue
            
            # Prüfe ob Vorhersage in unserem Zeitfenster liegt
            time_horizon = pred.get('time_horizon_minutes', 15)
            pred_end = pred_time + timedelta(minutes=time_horizon)
            
            # Überschneidung?
            if (pred_time <= end_time and pred_end >= start_time):
                expected_patients += pred.get('predicted_value', 0)
                prediction_count += 1
        
        # Normalisiere auf Stunden (falls mehrere Vorhersagen)
        if prediction_count > 0:
            # Skaliere basierend auf Dauer
            expected_patients = expected_patients * (duration_hours / (prediction_count * 0.25))  # 0.25 = 15min in Stunden
        
        # Score-Berechnung
        # 1. Dringlichkeit (40%): Je näher am Fälligkeitsdatum, desto besser
        urgency_score = 0.0
        if days_until_due is not None and next_due_date:
            days_diff = abs((start_time.date() - next_due_date).days)
            if days_until_due < 0:  # Überfällig
                urgency_score = 1.0 if days_diff <= 1 else max(0.7, 1.0 - (days_diff / 7))
            elif days_until_due <= 3:
                urgency_score = max(0.8, 1.0 - (days_diff / 5))
            elif days_until_due <= 7:
                urgency_score = max(0.6, 1.0 - (days_diff / 10))
            else:
                urgency_score = max(0.4, 1.0 - (days_diff / 20))
        else:
            urgency_score = 0.5  # Neutral wenn kein Fälligkeitsdatum
        
        # 2. Patientenlast (40%): Niedrigere Last = besser
        # Normalisiere auf 0-1 (0 Patienten = 1.0, 10+ Patienten = 0.0)
        patient_score = max(0.0, min(1.0, 1.0 - (expected_patients / 10.0)))
        
        # 3. Zeit bis Fälligkeit (20%): Je näher, desto besser (aber nicht überfällig)
        time_score = 0.5
        if days_until_due is not None:
            days_to_start = (start_time.date() - now.date()).days
            if days_until_due < 0:  # Überfällig - sofort ist am besten
                time_score = 1.0 if days_to_start <= 1 else 0.8
            elif days_until_due <= 3:
                time_score = 1.0 if days_to_start <= days_until_due else 0.7
            elif days_until_due <= 7:
                time_score = 0.9 if days_to_start <= days_until_due else 0.6
            else:
                time_score = 0.8 if days_to_start <= days_until_due else 0.5
        
        # Gesamt-Score (gewichtet)
        total_score = (urgency_score * 0.4) + (patient_score * 0.4) + (time_score * 0.2)
        
        # Grund für Vorschlag
        reasons = []
        if urgency_score > 0.7:
            reasons.append("Passt gut zum Fälligkeitsdatum")
        if patient_score > 0.7:
            reasons.append("Niedrige erwartete Patientenlast")
        if time_score > 0.7:
            reasons.append("Gute Timing")
        
        reason_text = "; ".join(reasons) if reasons else "Geeignete Zeit"
        
        suggestions.append({
            'start_time': start_time,
            'end_time': end_time,
            'score': round(total_score, 2),
            'expected_patients': round(expected_patients, 1),
            'reason': reason_text,
            'duration_minutes': duration_minutes
        })
    
    # Sortiere nach Score (höchster zuerst)
    suggestions.sort(key=lambda x: x['score'], reverse=True)
    
    # Gib Top 10 zurück
    return suggestions[:10]


def calculate_device_urgency(days_until_maintenance: int, usage_hours: int, max_usage_hours: int) -> str:
    """
    Berechne die Wartungsdringlichkeit eines Geräts basierend auf:
    - Tagen bis zur nächsten Wartung
    - Betriebsstunden im Verhältnis zur maximalen Betriebszeit
    
    Args:
        days_until_maintenance: Tage bis zur nächsten fälligen Wartung (kann negativ sein)
        usage_hours: Aktuelle Betriebsstunden
        max_usage_hours: Maximale Betriebsstunden für diesen Gerätetyp
    
    Returns:
        'hoch', 'mittel' oder 'niedrig'
    """
    # Berechne Dringlichkeit basierend auf Tagen bis Wartung
    days_urgency = "niedrig"
    if days_until_maintenance < 0 or days_until_maintenance < 7:
        days_urgency = "hoch"
    elif days_until_maintenance < 30:
        days_urgency = "mittel"
    
    # Berechne Dringlichkeit basierend auf Betriebsstunden
    if max_usage_hours > 0:
        hours_percentage = (usage_hours / max_usage_hours) * 100
        hours_urgency = "niedrig"
        if hours_percentage >= 95:  # >= 95% = hoch
            hours_urgency = "hoch"
        elif hours_percentage >= 85:  # >= 85% = mittel
            hours_urgency = "mittel"
    else:
        hours_urgency = "niedrig"
    
    # Nimm höchste Dringlichkeit (OR-Logik)
    if days_urgency == "hoch" or hours_urgency == "hoch":
        return "hoch"
    elif days_urgency == "mittel" or hours_urgency == "mittel":
        return "mittel"
    return "niedrig"


def get_system_status() -> tuple[str, str]:
    """Gibt den aktuellen Systemstatus zurück (Status, Farbe)"""
    # In einer echten App würde hier der Systemzustand geprüft
    # Für das MVP: immer "betriebsbereit"
    return "betriebsbereit", "#10B981"


def calculate_metric_severity(value: float, thresholds: dict) -> tuple[str, str]:
    """
    Berechne Schweregrad basierend auf Wert und Schwellenwerten
    Rückgabe: (schweregrad, hinweis_text)
    thresholds: {'critical': max, 'watch': max, 'stable': max}
    """
    if value >= thresholds.get('critical', 90):
        return 'hoch', 'Kritisch'
    elif value >= thresholds.get('watch', 70):
        return 'mittel', 'Beobachten'
    else:
        return 'niedrig', 'Stabil'


def get_metric_severity_for_load(load_percent: float) -> tuple[str, str]:
    """Gibt den Schweregrad für Auslastungsmetriken (0-100%) zurück"""
    if load_percent >= 90:
        return 'hoch', 'Kritisch'
    elif load_percent >= 75:
        return 'mittel', 'Beobachten'
    else:
        return 'niedrig', 'Stabil'


def get_metric_severity_for_count(count: int, thresholds: dict) -> tuple[str, str]:
    """Ermittle Schweregrad für zählbasierte Metriken"""
    if count >= thresholds.get('critical', 20):
        return 'high', 'Kritisch'
    elif count >= thresholds.get('watch', 10):
        return 'medium', 'Beobachten'
    else:
        return 'low', 'Stabil'


def get_metric_severity_for_free(free: int, total: int) -> tuple[str, str]:
    """Ermittle Schweregrad für freie/verfügbare Metriken (niedriger ist schlechter)"""
    if total == 0:
        return 'high', 'Kritisch'
    free_percent = (free / total) * 100
    if free_percent <= 5:
        return 'high', 'Kritisch'
    elif free_percent <= 15:
        return 'medium', 'Beobachten'
    else:
        return 'low', 'Stabil'


def calculate_explanation_score(trend_strength: float, data_points: int, confidence: float) -> str:
    """
    Erkläre den Erklärungsscore (niedrig/mittel/hoch) basierend auf Trendstärke
    trend_strength: 0-1 (wie stark ist der Trend)
    data_points: Anzahl der verwendeten Datenpunkte
    confidence: 0-1 (Prognose-Vertrauen)
    """
    # Faktoren kombinieren
    score = (trend_strength * 0.4) + (min(data_points / 20, 1.0) * 0.3) + (confidence * 0.3)
    
    if score >= 0.7:
        return "hoch"
    elif score >= 0.4:
        return "mittel"
    else:
        return "niedrig"


def get_explanation_score_color(score: str) -> str:
    """Farbe für Erklärungsscore-Badge ermitteln"""
    farben = {
        "hoch": "#10B981",    # smaragd-500
        "mittel": "#F59E0B",  # bernstein-500
        "niedrig": "#6B7280", # grau-500
        # Für Kompatibilität mit englischen Keys:
        "high": "#10B981",
        "medium": "#F59E0B",
        "low": "#6B7280",
    }
    return farben.get(score.lower(), "#6B7280")


def calculate_patient_arrival_prediction(
    ed_load: float,
    time_horizon_minutes: int,
    trend: float = 0.0,
    has_active_surge: bool = False,
    historical_arrivals: List[Dict] = None
) -> tuple[float, float]:
    """
    Berechne Vorhersage für Patientenzugang basierend auf aktuellen Daten.
    
    Args:
        ed_load: Aktuelle Notaufnahme-Auslastung (0-100%)
        time_horizon_minutes: Zeithorizont für Vorhersage (5, 10, oder 15)
        trend: Trend-Richtung (-1 bis 1, von Simulation)
        has_active_surge: Ob ein aktives Surge-Event läuft
        historical_arrivals: Historische Patientenzugänge (optional)
    
    Returns:
        tuple: (predicted_count, confidence)
    """
    # Basis: ED-Load skaliert auf Patientenzugang
    # Höherer Load → mehr erwartete Ankünfte
    # 0% Load → ~0-1 Patienten/15min, 100% Load → ~8-12 Patienten/15min
    base_rate = (ed_load / 100.0) * 10.0  # 0-10 Patienten bei 100% Load
    
    # Skaliere auf Zeithorizont (proportional)
    time_factor = time_horizon_minutes / 15.0
    base_prediction = base_rate * time_factor
    
    # Trend-Anpassung: Trend beeinflusst Vorhersage
    trend_adjustment = trend * 2.0  # Trend kann ±2 Patienten beeinflussen
    base_prediction += trend_adjustment
    
    # Surge-Event: +30-50% bei aktiven Surges
    if has_active_surge:
        surge_multiplier = random.uniform(1.3, 1.5)
        base_prediction *= surge_multiplier
    
    # Tageszeit-Muster: Mehr Ankünfte am Nachmittag (14-18 Uhr)
    current_hour = datetime.now().hour
    if 14 <= current_hour <= 18:
        time_multiplier = random.uniform(1.1, 1.3)
    elif 8 <= current_hour <= 12:
        time_multiplier = random.uniform(0.9, 1.1)
    elif 0 <= current_hour <= 6:
        time_multiplier = random.uniform(0.6, 0.8)
    else:
        time_multiplier = random.uniform(0.8, 1.0)
    base_prediction *= time_multiplier
    
    # Historische Daten berücksichtigen (falls verfügbar)
    if historical_arrivals:
        # Berechne Durchschnitt der letzten Stunde
        recent_arrivals = [a for a in historical_arrivals if a.get('value', 0) > 0]
        if recent_arrivals:
            avg_recent = sum(a['value'] for a in recent_arrivals) / len(recent_arrivals)
            # Kombiniere Basis-Vorhersage mit historischem Durchschnitt (gewichteter Durchschnitt)
            base_prediction = (base_prediction * 0.6) + (avg_recent * 0.4)
    
    # Runde auf ganze Zahl und stelle sicher, dass es nicht negativ ist
    predicted_count = max(0, round(base_prediction))
    
    # Confidence basierend auf Zeithorizont und Datenqualität
    base_confidence = calculate_prediction_confidence(base_prediction, time_horizon_minutes)
    # Höheres Vertrauen wenn historische Daten verfügbar sind
    if historical_arrivals and len(historical_arrivals) >= 5:
        confidence = min(0.95, base_confidence + 0.05)
    else:
        confidence = base_confidence
    
    return predicted_count, confidence


def calculate_bed_demand_prediction(
    current_utilization: float,
    expected_patient_arrivals: int,
    time_horizon_minutes: int,
    total_beds: int,
    ready_for_discharge: int = 0,
    trend: float = 0.0
) -> tuple[float, float]:
    """
    Berechne Vorhersage für Bettenbedarf (Auslastung in Prozent).
    
    Args:
        current_utilization: Aktuelle Bettenauslastung (0-1.0 oder 0-100%)
        expected_patient_arrivals: Erwartete Anzahl neuer Patienten
        time_horizon_minutes: Zeithorizont für Vorhersage (5, 10, oder 15)
        total_beds: Gesamtanzahl Betten in der Abteilung
        ready_for_discharge: Anzahl Patienten, die entlassen werden können
        trend: Trend-Richtung (-1 bis 1)
    
    Returns:
        tuple: (predicted_utilization_percent, confidence)
    """
    # Normalisiere current_utilization auf 0-1.0
    if current_utilization > 1.0:
        current_utilization = current_utilization / 100.0
    
    # Berechne erwartete Änderung basierend auf Patientenzugang
    # Jeder neue Patient benötigt ein Bett
    beds_needed = expected_patient_arrivals
    
    # Entlassungen reduzieren Bedarf
    beds_freed = ready_for_discharge
    
    # Netto-Änderung der belegten Betten
    net_bed_change = beds_needed - beds_freed
    
    # Aktuelle belegte Betten
    current_occupied = current_utilization * total_beds
    
    # Erwartete belegte Betten
    predicted_occupied = max(0, min(total_beds, current_occupied + net_bed_change))
    
    # Trend-Anpassung: Trend beeinflusst Auslastung
    trend_adjustment = trend * 0.05  # Trend kann ±5% Auslastung beeinflussen
    predicted_utilization = (predicted_occupied / total_beds) + trend_adjustment
    
    # Stelle sicher, dass Auslastung zwischen 0 und 1.0 bleibt
    predicted_utilization = max(0.0, min(1.0, predicted_utilization))
    
    # Konvertiere zu Prozent
    predicted_utilization_percent = predicted_utilization * 100.0
    
    # Confidence basierend auf Zeithorizont
    # Kürzere Horizonte = höheres Vertrauen
    # Mehr Entlassungsdaten = höheres Vertrauen
    base_confidence = calculate_prediction_confidence(predicted_utilization_percent, time_horizon_minutes)
    
    if ready_for_discharge > 0:
        # Höheres Vertrauen wenn Entlassungsdaten verfügbar sind
        confidence = min(0.95, base_confidence + 0.05)
    else:
        confidence = base_confidence
    
    return round(predicted_utilization_percent, 1), confidence


def calculate_daily_consumption_from_activity(
    item: Dict,
    ed_load: float,
    beds_occupied: int = 0,
    capacity_data: List[Dict] = None,
    operations_count: int = 0,
    operations_consumption: Dict[str, float] = None
) -> float:
    """
    Berechne täglichen Verbrauch basierend auf Krankenhausaktivität.
    
    Args:
        item: Inventar-Artikel-Dict mit item_name, department, min_threshold, etc.
        ed_load: Aktuelle ED-Load (0-100%)
        beds_occupied: Anzahl belegter Betten (optional, wird aus capacity_data berechnet wenn nicht gegeben)
        capacity_data: Liste von Kapazitätsdaten pro Abteilung
        operations_count: Anzahl abgeschlossener Operationen in der Abteilung (pro Tag/Tagesschnitt)
        operations_consumption: Dict mit item_name -> consumption_amount von Operationen (optional)
    
    Returns:
        Täglicher Verbrauch als float
    """
    # Basis-Verbrauchsrate basierend auf Artikel-Typ und Mindestbestand
    item_name = item.get('item_name', '').lower()
    department = item.get('department', '')
    min_threshold = item.get('min_threshold', 10)
    
    # Artikel-spezifische Basis-Verbrauchsrate (pro Tag)
    base_consumption = 1.0
    
    # Bestimme Basis-Verbrauch basierend auf Artikel-Typ
    if 'sauerstoff' in item_name or 'oxygen' in item_name:
        base_consumption = min_threshold * 0.15  # 15% des Mindestbestands pro Tag
    elif 'infusion' in item_name:
        base_consumption = min_threshold * 0.20  # 20% pro Tag
    elif 'maske' in item_name or 'mask' in item_name:
        base_consumption = min_threshold * 0.10  # 10% pro Tag
    elif 'filter' in item_name:
        base_consumption = min_threshold * 0.12  # 12% pro Tag
    else:
        # Standard: 10% des Mindestbestands pro Tag
        base_consumption = min_threshold * 0.10
    
    # ED Load Multiplikator (0.5-1.5x)
    # Höhere ED Load → mehr Verbrauch
    ed_multiplier = 0.5 + (ed_load / 100.0) * 1.0  # 0.5 bei 0% Load, 1.5 bei 100% Load
    
    # Bettenauslastung Multiplikator (0.7-1.3x)
    # Berechne Bettenauslastung wenn nicht gegeben
    if beds_occupied == 0 and capacity_data:
        # Finde Abteilung in capacity_data
        dept_capacity = next((c for c in capacity_data if c.get('department') == department), None)
        if dept_capacity:
            total_beds = dept_capacity.get('total_beds', 0)
            occupied = dept_capacity.get('occupied_beds', 0)
            if total_beds > 0:
                beds_utilization = (occupied / total_beds) * 100
                beds_multiplier = 0.7 + (beds_utilization / 100.0) * 0.6  # 0.7-1.3x
            else:
                beds_multiplier = 1.0
        else:
            beds_multiplier = 1.0
    elif beds_occupied > 0:
        # Wenn beds_occupied gegeben, schätze Multiplikator basierend auf typischer Kapazität
        # Annahme: 50 belegte Betten = 100% Auslastung für Multiplikator-Berechnung
        beds_utilization = min(100, (beds_occupied / 50.0) * 100)
        beds_multiplier = 0.7 + (beds_utilization / 100.0) * 0.6
    else:
        beds_multiplier = 1.0
    
    # Abteilungs-spezifische Faktoren
    dept_multiplier = 1.0
    if department:
        dept_lower = department.lower()
        if 'intensiv' in dept_lower or 'icu' in dept_lower:
            dept_multiplier = 1.5  # Intensivstation: 1.5x
        elif 'chirurgie' in dept_lower or 'surgery' in dept_lower:
            dept_multiplier = 1.2  # Chirurgie: 1.2x
        elif 'kardiologie' in dept_lower or 'cardiology' in dept_lower:
            dept_multiplier = 1.1  # Kardiologie: 1.1x
        elif 'notaufnahme' in dept_lower or 'er' in dept_lower:
            dept_multiplier = 1.3  # Notaufnahme: 1.3x
    
    # Operations-basierter Verbrauch
    operations_consumption_amount = 0.0
    item_name = item.get('item_name', '')
    if operations_consumption and item_name in operations_consumption:
        # Direkter Verbrauch aus Operationen (bereits berechnet)
        operations_consumption_amount = operations_consumption[item_name] * operations_count
    elif operations_count > 0:
        # Schätze Operations-Verbrauch basierend auf Artikel-Typ
        if 'maske' in item_name.lower() or 'mask' in item_name.lower():
            operations_consumption_amount = operations_count * random.uniform(2.0, 5.0)
        elif 'handschuh' in item_name.lower():
            operations_consumption_amount = operations_count * random.uniform(8.0, 15.0)
        elif 'verband' in item_name.lower() or 'kompresse' in item_name.lower():
            operations_consumption_amount = operations_count * random.uniform(3.0, 8.0)
        elif 'kittel' in item_name.lower():
            operations_consumption_amount = operations_count * random.uniform(1.0, 2.0)
        elif 'naht' in item_name.lower():
            operations_consumption_amount = operations_count * random.uniform(1.0, 3.0)
        elif 'tuch' in item_name.lower():
            operations_consumption_amount = operations_count * random.uniform(3.0, 8.0)
    
    # Kombinierte Berechnung: Basis-Verbrauch + Operations-Verbrauch
    base_daily_consumption = base_consumption * ed_multiplier * beds_multiplier * dept_multiplier
    daily_consumption = base_daily_consumption + operations_consumption_amount
    
    # Stelle sicher, dass Verbrauch mindestens 1.0 ist
    return max(1.0, round(daily_consumption, 2))


def calculate_operation_consumption(
    operation_type: str,
    department: str,
    duration_minutes: int = 60
) -> Dict[str, float]:
    """
    Berechne Materialverbrauch pro Operation basierend auf Operationstyp und Dauer.
    
    Args:
        operation_type: Typ der Operation (z.B. "Appendektomie", "Gelenkersatz")
        department: Abteilung
        duration_minutes: Dauer der Operation in Minuten
    
    Returns:
        Dict mit item_name -> consumption_amount
    """
    consumption = {}
    
    # Basis-Materialien für jede Operation
    base_materials = {
        'OP-Masken': 2.0,  # 2-5 Masken pro OP
        'OP-Handschuhe': 8.0,  # 8-15 Paare pro OP
        'OP-Tücher': 3.0,  # 3-8 Tücher
        'Desinfektionsmittel': 0.5,  # Liter
    }
    
    # Kleine Operationen (unter 60 Min)
    if duration_minutes < 60:
        for material, base_amount in base_materials.items():
            consumption[material] = base_amount * random.uniform(0.7, 1.0)
        consumption['Wundverbände'] = random.uniform(2.0, 4.0)
        consumption['Sterile Kompressen'] = random.uniform(2.0, 5.0)
    # Mittlere Operationen (60-120 Min)
    elif duration_minutes < 120:
        for material, base_amount in base_materials.items():
            consumption[material] = base_amount * random.uniform(1.0, 1.5)
        consumption['Wundverbände'] = random.uniform(4.0, 8.0)
        consumption['Sterile Kompressen'] = random.uniform(5.0, 10.0)
        consumption['Nahtmaterial'] = random.uniform(1.0, 2.0)
    # Große Operationen (über 120 Min)
    else:
        for material, base_amount in base_materials.items():
            consumption[material] = base_amount * random.uniform(1.5, 2.5)
        consumption['Wundverbände'] = random.uniform(8.0, 15.0)
        consumption['Sterile Kompressen'] = random.uniform(10.0, 20.0)
        consumption['Nahtmaterial'] = random.uniform(2.0, 4.0)
    
    # Abteilungs-spezifische Materialien
    dept_lower = department.lower()
    if 'chirurgie' in dept_lower:
        consumption['OP-Kittel'] = random.uniform(1.0, 2.0)
        if 'darm' in operation_type.lower() or 'resektion' in operation_type.lower():
            consumption['Drainagen'] = random.uniform(1.0, 3.0)
    elif 'orthopädie' in dept_lower:
        if 'gelenk' in operation_type.lower() or 'bruch' in operation_type.lower():
            consumption['Gipsbinden'] = random.uniform(2.0, 5.0)
            consumption['Schienen'] = random.uniform(0.0, 1.0)
    elif 'urologie' in dept_lower:
        consumption['Katheter'] = random.uniform(1.0, 2.0)
    elif 'kardiologie' in dept_lower:
        consumption['Katheter'] = random.uniform(1.0, 3.0)
    elif 'intensiv' in dept_lower:
        consumption['Beatmungsfilter'] = random.uniform(0.5, 1.0)
        consumption['Katheter'] = random.uniform(1.0, 2.0)
    
    return consumption


def calculate_days_until_stockout(
    current_stock: int,
    daily_consumption_rate: float
) -> Optional[float]:
    """
    Berechne präzise Tage bis Engpass basierend auf aktuellem Bestand und Verbrauchsrate.
    
    Args:
        current_stock: Aktueller Bestand
        daily_consumption_rate: Tägliche Verbrauchsrate
    
    Returns:
        Tage bis Engpass (float) oder None wenn kein Engpass erwartet
    """
    if daily_consumption_rate <= 0:
        return None
    
    days_until_stockout = current_stock / daily_consumption_rate
    
    # Runde auf 1 Dezimalstelle
    return round(days_until_stockout, 1)


def calculate_reorder_suggestion(
    item: Dict,
    daily_consumption_rate: float,
    days_until_stockout: Optional[float],
    safety_buffer_days: int = 2,
    delivery_time_days: int = 1
) -> Dict:
    """
    Berechne Nachfüllvorschlag mit Menge und Bestelltermin.
    
    Args:
        item: Inventar-Artikel-Dict
        daily_consumption_rate: Tägliche Verbrauchsrate
        days_until_stockout: Tage bis Engpass (None wenn kein Engpass)
        safety_buffer_days: Sicherheitspuffer in Tagen (Standard: 2)
        delivery_time_days: Lieferzeit in Tagen (Standard: 1)
    
    Returns:
        Dict mit 'suggested_qty', 'order_by_date', 'order_by_days', 'priority', 'reasoning'
    """
    current_stock = item.get('current_stock', 0)
    min_threshold = item.get('min_threshold', 0)
    max_capacity = item.get('max_capacity', 0)
    
    # Prüfe zuerst, ob Artikel unter Mindestbestand liegt
    is_below_threshold = current_stock < min_threshold
    is_near_threshold = min_threshold > 0 and current_stock < min_threshold * 1.2  # Innerhalb 20% des Mindestbestands
    
    # Bestimme Priorität
    if days_until_stockout is None:
        # Wenn unter Mindestbestand, auch ohne Engpass-Berechnung mindestens mittlere Priorität
        if is_below_threshold:
            priority = "mittel"
            suggested_qty = max(min_threshold * 1.5, int(daily_consumption_rate * 14)) if daily_consumption_rate > 0 else min_threshold * 1.5
            order_by_days = 3  # Bestelle innerhalb von 3 Tagen
            reasoning = f"Unter Mindestbestand ({current_stock} < {min_threshold})"
        else:
            priority = "niedrig"
            suggested_qty = 0
            order_by_days = None
            reasoning = "Kein Engpass erwartet"
    elif days_until_stockout <= safety_buffer_days + delivery_time_days:
        priority = "hoch"
        # Kritisch: Bestelle sofort, genug für mindestens 2x Mindestbestand
        suggested_qty = max(min_threshold * 2, int(daily_consumption_rate * (safety_buffer_days + delivery_time_days + 7)))
        order_by_days = 0  # Sofort bestellen
        reasoning = f"Kritisch: Engpass in {days_until_stockout:.1f} Tagen erwartet"
    elif days_until_stockout <= (safety_buffer_days + delivery_time_days) * 2:
        priority = "mittel"
        # Bestelle innerhalb der nächsten Tage
        suggested_qty = max(min_threshold * 1.5, int(daily_consumption_rate * (safety_buffer_days + delivery_time_days + 14)))
        order_by_days = max(0, int(days_until_stockout - safety_buffer_days - delivery_time_days))
        reasoning = f"Engpass in {days_until_stockout:.1f} Tagen erwartet"
    else:
        # Auch bei längerer Zeit bis Engpass: Wenn unter Mindestbestand, mindestens mittlere Priorität
        if is_below_threshold or is_near_threshold:
            priority = "mittel"
            suggested_qty = max(min_threshold * 1.5, int(daily_consumption_rate * 14)) if daily_consumption_rate > 0 else min_threshold * 1.5
            order_by_days = max(0, int(days_until_stockout - safety_buffer_days - delivery_time_days))
            reasoning = f"Unter Mindestbestand, Engpass in {days_until_stockout:.1f} Tagen erwartet"
        else:
            priority = "niedrig"
            # Planmäßige Bestellung
            suggested_qty = max(min_threshold, int(daily_consumption_rate * 14)) if daily_consumption_rate > 0 else min_threshold
            order_by_days = max(0, int(days_until_stockout - safety_buffer_days - delivery_time_days))
            reasoning = f"Planmäßige Bestellung empfohlen"
    
    # Stelle sicher, dass nicht über max_capacity hinausgegangen wird
    if max_capacity > 0:
        suggested_qty = min(suggested_qty, max_capacity)
    
    # Berechne Bestelltermin (Datum)
    from datetime import datetime, timedelta
    if order_by_days is not None:
        order_by_date = (datetime.now() + timedelta(days=order_by_days)).date()
        order_by_date_str = order_by_date.strftime('%Y-%m-%d')
    else:
        order_by_date_str = None
    
    return {
        'suggested_qty': int(suggested_qty),
        'order_by_date': order_by_date_str,
        'order_by_days': order_by_days,
        'priority': priority,
        'reasoning': reasoning,
        'daily_consumption_rate': daily_consumption_rate,
        'days_until_stockout': days_until_stockout
    }

