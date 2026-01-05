"""
HospitalFlow Initialdaten-Generierung

Generiert realistische Beispieldaten für 4-6 Wochen Historie.
Nur normaler Betrieb (keine speziellen Ereignisse).
"""
import random
from datetime import datetime, timedelta, timezone, date
from database import HospitalDB


def generate_devices_only(db: HospitalDB):
    """
    Generiert nur Geräte für die Datenbank, falls sie fehlen.
    Verwendet INSERT OR IGNORE um Duplikate zu vermeiden.
    
    Args:
        db: HospitalDB-Instanz
    """
    print("Generiere Geräte...")
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        devices = [
            {'device_id': 'VENT-001', 'device_name': 'Beatmungsgerät #12', 'device_type': 'Life Support', 'department': 'ICU', 'usage_hours': 3500, 'max_usage_hours': 4200, 'last_maintenance': (date.today() - timedelta(days=80)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=10)).isoformat(), 'urgency_level': 'medium'},
            {'device_id': 'CT-003', 'device_name': 'CT-Gerät #3', 'device_type': 'Imaging', 'department': 'Radiology', 'usage_hours': 4500, 'max_usage_hours': 5000, 'last_maintenance': (date.today() - timedelta(days=70)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=20)).isoformat(), 'urgency_level': 'low'},
            {'device_id': 'MON-008', 'device_name': 'Monitor #8', 'device_type': 'Monitoring', 'department': 'ER', 'usage_hours': 5500, 'max_usage_hours': 6000, 'last_maintenance': (date.today() - timedelta(days=60)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=30)).isoformat(), 'urgency_level': 'low'},
            {'device_id': 'DEF-005', 'device_name': 'Defibrillator #5', 'device_type': 'Emergency', 'department': 'ER', 'usage_hours': 2500, 'max_usage_hours': 3000, 'last_maintenance': (date.today() - timedelta(days=90)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=0)).isoformat(), 'urgency_level': 'high'},
            {'device_id': 'ECG-012', 'device_name': 'EKG-Gerät #12', 'device_type': 'Monitoring', 'department': 'Cardiology', 'usage_hours': 3200, 'max_usage_hours': 4000, 'last_maintenance': (date.today() - timedelta(days=75)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=15)).isoformat(), 'urgency_level': 'medium'},
            {'device_id': 'ENDO-004', 'device_name': 'Endoskop #4', 'device_type': 'Diagnostic', 'department': 'Gastroenterology', 'usage_hours': 2800, 'max_usage_hours': 3500, 'last_maintenance': (date.today() - timedelta(days=65)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=25)).isoformat(), 'urgency_level': 'low'},
            {'device_id': 'URO-006', 'device_name': 'Urologisches System #6', 'device_type': 'Surgical', 'department': 'Urology', 'usage_hours': 2100, 'max_usage_hours': 3000, 'last_maintenance': (date.today() - timedelta(days=85)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=5)).isoformat(), 'urgency_level': 'high'},
            {'device_id': 'SPINE-002', 'device_name': 'Wirbelsäulen-Navigationssystem', 'device_type': 'Surgical', 'department': 'SpineCenter', 'usage_hours': 1800, 'max_usage_hours': 2500, 'last_maintenance': (date.today() - timedelta(days=50)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=40)).isoformat(), 'urgency_level': 'low'},
            {'device_id': 'ENT-001', 'device_name': 'HNO-Mikroskop', 'device_type': 'Diagnostic', 'department': 'ENT', 'usage_hours': 2200, 'max_usage_hours': 3000, 'last_maintenance': (date.today() - timedelta(days=55)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=35)).isoformat(), 'urgency_level': 'low'},
            {'device_id': 'ENT-002', 'device_name': 'HNO-Endoskop-System', 'device_type': 'Diagnostic', 'department': 'ENT', 'usage_hours': 1900, 'max_usage_hours': 2800, 'last_maintenance': (date.today() - timedelta(days=45)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=45)).isoformat(), 'urgency_level': 'low'},
        ]
        
        for device in devices:
            cursor.execute("""
                INSERT OR IGNORE INTO devices (device_id, device_name, device_type, department, usage_hours, max_usage_hours, last_maintenance, next_maintenance_due, urgency_level, maintenance_confirmed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                device['device_id'],
                device['device_name'],
                device['device_type'],
                device['department'],
                device['usage_hours'],
                device['max_usage_hours'],
                device['last_maintenance'],
                device['next_maintenance_due'],
                device['urgency_level']
            ))
        
        conn.commit()
        print(f"Geräte erfolgreich generiert ({len(devices)} Geräte)")
        
    except Exception as e:
        print(f"Fehler beim Generieren der Geräte: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def generate_seed_data(db: HospitalDB):
    """
    Generiert Initialdaten für die Datenbank.
    
    Args:
        db: HospitalDB-Instanz
    """
    print("Generiere Initialdaten...")
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Inventar-Artikel
        print("  - Inventar-Artikel...")
        inventory_items = [
            {'item_name': 'Sauerstoffflaschen', 'department': 'ICU', 'current_stock': 55, 'min_threshold': 50, 'max_capacity': 100, 'unit': 'Stück', 'category': 'Medizinisch'},
            {'item_name': 'OP-Masken', 'department': 'Surgery', 'current_stock': 150, 'min_threshold': 100, 'max_capacity': 500, 'unit': 'Stück', 'category': 'Schutzausrüstung'},
            {'item_name': 'Infusionslösungen', 'department': 'ER', 'current_stock': 35, 'min_threshold': 30, 'max_capacity': 200, 'unit': 'Liter', 'category': 'Medizinisch'},
            {'item_name': 'Beatmungsfilter', 'department': 'ICU', 'current_stock': 12, 'min_threshold': 10, 'max_capacity': 50, 'unit': 'Stück', 'category': 'Medizinisch'},
            {'item_name': 'OP-Handschuhe', 'department': 'Surgery', 'current_stock': 600, 'min_threshold': 200, 'max_capacity': 1000, 'unit': 'Paar', 'category': 'Schutzausrüstung'},
            {'item_name': 'Herzkatheter', 'department': 'Cardiology', 'current_stock': 25, 'min_threshold': 20, 'max_capacity': 60, 'unit': 'Stück', 'category': 'Medizinisch'},
            {'item_name': 'Endoskope', 'department': 'Gastroenterology', 'current_stock': 8, 'min_threshold': 5, 'max_capacity': 15, 'unit': 'Stück', 'category': 'Medizinisch'},
            {'item_name': 'Urologische Instrumente', 'department': 'Urology', 'current_stock': 18, 'min_threshold': 15, 'max_capacity': 40, 'unit': 'Stück', 'category': 'Medizinisch'},
            {'item_name': 'Wirbelsäulenimplantate', 'department': 'SpineCenter', 'current_stock': 12, 'min_threshold': 10, 'max_capacity': 30, 'unit': 'Stück', 'category': 'Medizinisch'},
            {'item_name': 'Mobilitätshilfen', 'department': 'Geriatrics', 'current_stock': 30, 'min_threshold': 25, 'max_capacity': 60, 'unit': 'Stück', 'category': 'Hilfsmittel'},
            {'item_name': 'HNO-Endoskope', 'department': 'ENT', 'current_stock': 6, 'min_threshold': 4, 'max_capacity': 12, 'unit': 'Stück', 'category': 'Medizinisch'},
            {'item_name': 'HNO-Instrumente', 'department': 'ENT', 'current_stock': 15, 'min_threshold': 12, 'max_capacity': 30, 'unit': 'Stück', 'category': 'Medizinisch'},
        ]
        
        for item in inventory_items:
            cursor.execute("""
                INSERT INTO inventory (item_name, department, current_stock, min_threshold, max_capacity, unit, last_updated, category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item['item_name'],
                item['department'],
                item['current_stock'],
                item['min_threshold'],
                item['max_capacity'],
                item['unit'],
                datetime.now(timezone.utc).isoformat(),
                item['category']
            ))
        
        # 2. Geräte
        print("  - Geräte...")
        devices = [
            {'device_id': 'VENT-001', 'device_name': 'Beatmungsgerät #12', 'device_type': 'Life Support', 'department': 'ICU', 'usage_hours': 3500, 'max_usage_hours': 4200, 'last_maintenance': (date.today() - timedelta(days=80)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=10)).isoformat(), 'urgency_level': 'medium'},
            {'device_id': 'CT-003', 'device_name': 'CT-Gerät #3', 'device_type': 'Imaging', 'department': 'Radiology', 'usage_hours': 4500, 'max_usage_hours': 5000, 'last_maintenance': (date.today() - timedelta(days=70)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=20)).isoformat(), 'urgency_level': 'low'},
            {'device_id': 'MON-008', 'device_name': 'Monitor #8', 'device_type': 'Monitoring', 'department': 'ER', 'usage_hours': 5500, 'max_usage_hours': 6000, 'last_maintenance': (date.today() - timedelta(days=60)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=30)).isoformat(), 'urgency_level': 'low'},
            {'device_id': 'DEF-005', 'device_name': 'Defibrillator #5', 'device_type': 'Emergency', 'department': 'ER', 'usage_hours': 2500, 'max_usage_hours': 3000, 'last_maintenance': (date.today() - timedelta(days=90)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=0)).isoformat(), 'urgency_level': 'high'},
            {'device_id': 'ECG-012', 'device_name': 'EKG-Gerät #12', 'device_type': 'Monitoring', 'department': 'Cardiology', 'usage_hours': 3200, 'max_usage_hours': 4000, 'last_maintenance': (date.today() - timedelta(days=75)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=15)).isoformat(), 'urgency_level': 'medium'},
            {'device_id': 'ENDO-004', 'device_name': 'Endoskop #4', 'device_type': 'Diagnostic', 'department': 'Gastroenterology', 'usage_hours': 2800, 'max_usage_hours': 3500, 'last_maintenance': (date.today() - timedelta(days=65)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=25)).isoformat(), 'urgency_level': 'low'},
            {'device_id': 'URO-006', 'device_name': 'Urologisches System #6', 'device_type': 'Surgical', 'department': 'Urology', 'usage_hours': 2100, 'max_usage_hours': 3000, 'last_maintenance': (date.today() - timedelta(days=85)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=5)).isoformat(), 'urgency_level': 'high'},
            {'device_id': 'SPINE-002', 'device_name': 'Wirbelsäulen-Navigationssystem', 'device_type': 'Surgical', 'department': 'SpineCenter', 'usage_hours': 1800, 'max_usage_hours': 2500, 'last_maintenance': (date.today() - timedelta(days=50)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=40)).isoformat(), 'urgency_level': 'low'},
            {'device_id': 'ENT-001', 'device_name': 'HNO-Mikroskop', 'device_type': 'Diagnostic', 'department': 'ENT', 'usage_hours': 2200, 'max_usage_hours': 3000, 'last_maintenance': (date.today() - timedelta(days=55)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=35)).isoformat(), 'urgency_level': 'low'},
            {'device_id': 'ENT-002', 'device_name': 'HNO-Endoskop-System', 'device_type': 'Diagnostic', 'department': 'ENT', 'usage_hours': 1900, 'max_usage_hours': 2800, 'last_maintenance': (date.today() - timedelta(days=45)).isoformat(), 'next_maintenance_due': (date.today() + timedelta(days=45)).isoformat(), 'urgency_level': 'low'},
        ]
        
        for device in devices:
            cursor.execute("""
                INSERT INTO devices (device_id, device_name, device_type, department, usage_hours, max_usage_hours, last_maintenance, next_maintenance_due, urgency_level, maintenance_confirmed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                device['device_id'],
                device['device_name'],
                device['device_type'],
                device['department'],
                device['usage_hours'],
                device['max_usage_hours'],
                device['last_maintenance'],
                device['next_maintenance_due'],
                device['urgency_level']
            ))
        
        # 3. Personal
        print("  - Personal...")
        staff_members = [
            {'name': 'Maria Schmidt', 'role': 'Krankenschwester', 'department': 'ER', 'category': 'Pflegekräfte', 'contact': 'maria.schmidt@waldkrankenhaus.de'},
            {'name': 'Thomas Müller', 'role': 'Krankenpfleger', 'department': 'ICU', 'category': 'Pflegekräfte', 'contact': 'thomas.mueller@waldkrankenhaus.de'},
            {'name': 'Dr. Anna Weber', 'role': 'Oberärztin', 'department': 'Surgery', 'category': 'Ärzte', 'contact': 'anna.weber@waldkrankenhaus.de'},
            {'name': 'Dr. Peter Fischer', 'role': 'Facharzt', 'department': 'Cardiology', 'category': 'Ärzte', 'contact': 'peter.fischer@waldkrankenhaus.de'},
            {'name': 'Dr. Lisa Hoffmann', 'role': 'Fachärztin', 'department': 'Gastroenterology', 'category': 'Ärzte', 'contact': 'lisa.hoffmann@waldkrankenhaus.de'},
            {'name': 'Dr. Markus Schneider', 'role': 'Oberarzt', 'department': 'Urology', 'category': 'Ärzte', 'contact': 'markus.schneider@waldkrankenhaus.de'},
            {'name': 'Dr. Julia Wagner', 'role': 'Fachärztin', 'department': 'Orthopedics', 'category': 'Ärzte', 'contact': 'julia.wagner@waldkrankenhaus.de'},
            {'name': 'Dr. Robert Klein', 'role': 'Facharzt', 'department': 'SpineCenter', 'category': 'Ärzte', 'contact': 'robert.klein@waldkrankenhaus.de'},
            {'name': 'Dr. Sandra Bauer', 'role': 'Fachärztin', 'department': 'Geriatrics', 'category': 'Ärzte', 'contact': 'sandra.bauer@waldkrankenhaus.de'},
            {'name': 'Dr. Christian Meyer', 'role': 'Facharzt', 'department': 'ENT', 'category': 'Ärzte', 'contact': 'christian.meyer@waldkrankenhaus.de'},
            {'name': 'Michael Becker', 'role': 'Transportkoordinator', 'department': 'Logistics', 'category': 'Logistik', 'contact': 'michael.becker@waldkrankenhaus.de'},
            {'name': 'Sabine Klein', 'role': 'Sekretärin', 'department': 'Verwaltung', 'category': 'Orga', 'contact': 'sabine.klein@waldkrankenhaus.de'},
        ]
        
        staff_ids = {}
        for staff in staff_members:
            cursor.execute("""
                INSERT INTO staff (name, role, department, category, contact)
                VALUES (?, ?, ?, ?, ?)
            """, (
                staff['name'],
                staff['role'],
                staff['department'],
                staff['category'],
                staff['contact']
            ))
            staff_ids[staff['name']] = cursor.lastrowid
        
        # 4. Historische Metriken (4 Wochen)
        print("  - Historische Metriken (4 Wochen)...")
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(weeks=4)
        
        current_date = start_date
        while current_date <= now:
            # Tageszeit-Faktor
            hour = current_date.hour
            if 8 <= hour <= 12:
                time_factor = 1.2
            elif 14 <= hour <= 18:
                time_factor = 1.15
            elif 22 <= hour or hour < 6:
                time_factor = 0.7
            else:
                time_factor = 0.9
            
            # Wochentags-Faktor
            weekday = current_date.weekday()
            weekday_factor = 0.85 if weekday >= 5 else 1.0
            
            base_factor = time_factor * weekday_factor
            
            # Generiere Metriken
            ed_load = max(20, min(95, 60.0 * base_factor + random.uniform(-5, 5)))
            waiting_count = max(0, int(3 + (ed_load / 100 * 15) + random.uniform(-2, 2)))
            beds_free = max(5, int(50 * (1 - ed_load/100 * 0.3) * base_factor + random.uniform(-3, 3)))
            staff_load = max(40, min(90, ed_load * 0.9 + random.uniform(-5, 5)))
            rooms_free = max(2, int(15 * (beds_free / 50) + random.uniform(-2, 2)))
            or_load = max(30, min(85, 55.0 * base_factor + random.uniform(-5, 5)))
            transport_queue = max(0, int(2 + (ed_load / 100 * 8 * 0.7) + random.uniform(-1, 1)))
            
            # Speichere Metriken (alle 5 Minuten)
            if (current_date.minute % 5 == 0):
                # Generiere zusätzliche Metriken für verschiedene Abteilungen
                cardiology_load = max(30, min(85, 55.0 * base_factor + random.uniform(-5, 5)))
                orthopedics_load = max(35, min(80, 60.0 * base_factor + random.uniform(-5, 5)))
                urology_load = max(25, min(75, 50.0 * base_factor + random.uniform(-5, 5)))
                
                metrics = [
                    ('ed_load', ed_load, '%', 'ER'),
                    ('waiting_count', waiting_count, '', 'ER'),
                    ('beds_free', beds_free, '', None),
                    ('staff_load', staff_load, '%', None),
                    ('rooms_free', rooms_free, '', None),
                    ('or_load', or_load, '%', 'Surgery'),
                    ('transport_queue', transport_queue, '', None),
                    ('department_load', cardiology_load, '%', 'Cardiology'),
                    ('department_load', orthopedics_load, '%', 'Orthopedics'),
                    ('department_load', urology_load, '%', 'Urology'),
                ]
                
                for metric_type, value, unit, department in metrics:
                    cursor.execute("""
                        INSERT INTO metrics (timestamp, metric_type, value, unit, department)
                        VALUES (?, ?, ?, ?, ?)
                    """, (current_date.isoformat(), metric_type, value, unit, department))
            
            # Nächste Minute
            current_date += timedelta(minutes=1)
        
        # 5. Kapazitätsdaten (täglich für 4 Wochen)
        print("  - Kapazitätsdaten...")
        # Waldkrankenhaus Erlangen: 290 Betten verteilt auf 9 Fachabteilungen + Notaufnahme + HNO (Belegabteilung)
        # Anpassung: ENT als Belegabteilung mit 20 Betten hinzugefügt, Gesamt jetzt 310 Betten
        departments = [
            {'department': 'ER', 'total_beds': 25},                    # Notaufnahme
            {'department': 'ICU', 'total_beds': 15},                   # Anästhesie und Intensivmedizin
            {'department': 'Surgery', 'total_beds': 50},               # Allgemein- und Viszeralchirurgie
            {'department': 'Cardiology', 'total_beds': 40},             # Kardiologie
            {'department': 'Orthopedics', 'total_beds': 45},            # Orthopädie und Unfallchirurgie
            {'department': 'Urology', 'total_beds': 35},                 # Urologie
            {'department': 'Gastroenterology', 'total_beds': 30},       # Gastroenterologie
            {'department': 'Geriatrics', 'total_beds': 30},             # Akutgeriatrie
            {'department': 'SpineCenter', 'total_beds': 20},            # Wirbelsäulen- und Skoliosetherapie
            {'department': 'ENT', 'total_beds': 20},                    # Belegabteilung für Hals-, Nasen-, Ohrenheilkunde (NEU)
        ]
        # Gesamt: 310 Betten (290 Hauptbetten + 20 ENT-Belegbetten)
        
        cap_date = start_date
        while cap_date <= now:
            for dept_info in departments:
                # Berechne Auslastung basierend auf Tageszeit
                hour = cap_date.hour
                if 8 <= hour <= 12 or 14 <= hour <= 18:
                    utilization = random.uniform(0.75, 0.90)
                else:
                    utilization = random.uniform(0.60, 0.80)
                
                total = dept_info['total_beds']
                occupied = int(total * utilization)
                available = total - occupied
                
                cursor.execute("""
                    INSERT INTO capacity (timestamp, department, total_beds, occupied_beds, available_beds, utilization_rate)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    cap_date.isoformat(),
                    dept_info['department'],
                    total,
                    occupied,
                    available,
                    utilization
                ))
            
            cap_date += timedelta(hours=1)
        
        # 6. Entlassungsplanung (täglich)
        print("  - Entlassungsplanung...")
        discharge_date = start_date
        while discharge_date <= now:
            for dept_info in departments:
                dept = dept_info['department']
                ready = random.randint(3, 10)
                pending = random.randint(1, 4)
                total = random.randint(20, 50)
                avg_los = random.uniform(48, 120)  # Stunden
                capacity_util = random.uniform(0.6, 0.85)
                
                cursor.execute("""
                    INSERT INTO discharge_planning 
                    (timestamp, department, ready_for_discharge_count, pending_discharge_count, total_patients, avg_length_of_stay_hours, discharge_capacity_utilization)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    discharge_date.isoformat(),
                    dept,
                    ready,
                    pending,
                    total,
                    avg_los,
                    capacity_util
                ))
            
            discharge_date += timedelta(hours=6)
        
        conn.commit()
        print("Initialdaten erfolgreich generiert!")
        
    except Exception as e:
        print(f"Fehler beim Generieren der Initialdaten: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

