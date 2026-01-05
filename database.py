"""
HospitalFlow Datenbank-Implementierung

SQLite-Datenbank-Implementierung für HospitalFlow.
Implementiert alle Datenbankoperationen mit echten SQL-Abfragen.
"""
import sqlite3
import json
import random
from datetime import datetime, timedelta, timezone, date
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import threading
from contextlib import contextmanager
import os
import time
import queue
import queue


class HospitalDB:
    """Datenbankklasse für HospitalFlow mit SQLite"""
    
    def __init__(self, db_path: str = "data/hospitalflow.db", lock_timeout: float = 5.0):
        """
        Initialisiert die Datenbankverbindung und erstellt das Schema.
        
        Args:
            db_path: Pfad zur SQLite-Datenbankdatei
            lock_timeout: Timeout in Sekunden für Lock-Acquisition (Standard: 5.0)
        """
        self.db_path = db_path
        self.lock = threading.RLock()  # Use reentrant lock to allow nested calls
        self.lock_timeout = lock_timeout  # Timeout für Lock-Acquisition
        self._migration_run = False  # Track if migration has been run
        self._thread_local = threading.local()  # Thread-local storage für Connection Reuse
        self._force_delete_mode = False  # Flag to force DELETE journal mode if WAL causes issues
        
        # Erstelle Verzeichnis falls nicht vorhanden
        try:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        except Exception as dir_err:
            raise
        
        # Check database integrity and fix corrupted files
        try:
            wal_path = db_path + "-wal"
            shm_path = db_path + "-shm"
            wal_exists = os.path.exists(wal_path)
            
            if wal_exists:
                wal_size = os.path.getsize(wal_path)
                # If WAL file is 0 bytes or suspiciously small, it's likely corrupted
                if wal_size == 0:
                    # Try to checkpoint WAL first (in case there's valid data)
                    try:
                        temp_conn = sqlite3.connect(db_path, timeout=5.0)
                        try:
                            temp_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                            temp_conn.close()
                        except Exception as checkpoint_err:
                            try:
                                temp_conn.close()
                            except:
                                pass
                            # Checkpoint failed, remove corrupted WAL and SHM files
                            try:
                                if os.path.exists(wal_path):
                                    os.remove(wal_path)
                            except Exception as rm_err:
                                pass
                            try:
                                if os.path.exists(shm_path):
                                    os.remove(shm_path)
                            except Exception as rm_err:
                                pass
                    except Exception as conn_err:
                        # Can't connect, remove corrupted WAL and SHM files
                        try:
                            if os.path.exists(wal_path):
                                os.remove(wal_path)
                        except Exception as rm_err:
                            pass
                        try:
                            if os.path.exists(shm_path):
                                os.remove(shm_path)
                        except Exception as rm_err:
                            pass
        except Exception as wal_recovery_err:
            pass  # Continue anyway, let the connection attempt handle it
        
        # Check database integrity if database exists
        if os.path.exists(db_path):
            try:
                # Try to check integrity with DELETE journal mode (more reliable for corrupted databases)
                try:
                    temp_conn = sqlite3.connect(db_path, timeout=5.0)
                except Exception as connect_err:
                    # Can't even connect - database is severely corrupted
                    error_str = str(connect_err).lower()
                    if "disk i/o error" in error_str or "i/o error" in error_str or "unable to open" in error_str:
                        # Backup and remove corrupted database
                        try:
                            import shutil
                            backup_path = db_path + ".corrupted." + str(int(time.time()))
                            shutil.copy2(db_path, backup_path)
                        except:
                            pass
                        try:
                            if os.path.exists(db_path):
                                os.remove(db_path)
                        except:
                            pass
                        try:
                            wal_path = db_path + "-wal"
                            if os.path.exists(wal_path):
                                os.remove(wal_path)
                        except:
                            pass
                        try:
                            shm_path = db_path + "-shm"
                            if os.path.exists(shm_path):
                                os.remove(shm_path)
                        except:
                            pass
                        self._force_delete_mode = True
                    raise  # Re-raise to be caught by outer handler
                try:
                    # Switch to DELETE mode to avoid WAL issues
                    temp_conn.execute("PRAGMA journal_mode=DELETE")
                    # Check integrity
                    result = temp_conn.execute("PRAGMA integrity_check").fetchone()
                    integrity_ok = result and result[0] == "ok"
                    if not integrity_ok:
                        # Database is corrupted, try to recover
                        # Backup corrupted database
                        backup_path = db_path + ".corrupted." + str(int(time.time()))
                        try:
                            import shutil
                            shutil.copy2(db_path, backup_path)
                        except Exception as backup_err:
                            pass
                        # Try to recover using .recover() (SQLite 3.31+)
                        try:
                            temp_conn.close()
                            recovered_path = db_path + ".recovered"
                            recovered_conn = sqlite3.connect(recovered_path)
                            temp_conn = sqlite3.connect(db_path)
                            # Use recover to extract data
                            recovered_conn.backup(temp_conn)
                            recovered_conn.close()
                            temp_conn.close()
                            # Replace corrupted database with recovered one
                            import shutil
                            shutil.move(recovered_path, db_path)
                        except Exception as recover_err:
                            # Recovery failed, remove corrupted database and let schema creation recreate it
                            try:
                                temp_conn.close()
                            except:
                                pass
                            # Remove corrupted database and WAL files
                            try:
                                if os.path.exists(db_path):
                                    os.remove(db_path)
                            except:
                                pass
                            try:
                                if os.path.exists(wal_path):
                                    os.remove(wal_path)
                            except:
                                pass
                            try:
                                if os.path.exists(shm_path):
                                    os.remove(shm_path)
                            except:
                                pass
                    else:
                        temp_conn.close()
                except Exception as integrity_err:
                    # Check if it's an I/O error - if so, database is severely corrupted
                    error_str = str(integrity_err).lower()
                    if "disk i/o error" in error_str or "i/o error" in error_str or "unable to open" in error_str:
                        try:
                            temp_conn.close()
                        except:
                            pass
                        # Backup corrupted database
                        try:
                            import shutil
                            backup_path = db_path + ".corrupted." + str(int(time.time()))
                            shutil.copy2(db_path, backup_path)
                        except:
                            pass
                        # Remove corrupted database and WAL files
                        try:
                            if os.path.exists(db_path):
                                os.remove(db_path)
                        except:
                            pass
                        try:
                            wal_path = db_path + "-wal"
                            if os.path.exists(wal_path):
                                os.remove(wal_path)
                        except:
                            pass
                        try:
                            shm_path = db_path + "-shm"
                            if os.path.exists(shm_path):
                                os.remove(shm_path)
                        except:
                            pass
                        # Force DELETE mode for new database
                        self._force_delete_mode = True
                    else:
                        try:
                            temp_conn.close()
                        except:
                            pass
            except Exception as db_check_err:
                # If we can't even check the database due to I/O errors, it's severely corrupted
                error_str = str(db_check_err).lower()
                if "disk i/o error" in error_str or "i/o error" in error_str or "unable to open" in error_str:
                    # Backup corrupted database
                    try:
                        import shutil
                        backup_path = db_path + ".corrupted." + str(int(time.time()))
                        shutil.copy2(db_path, backup_path)
                    except:
                        pass
                    # Remove corrupted database and WAL files
                    try:
                        if os.path.exists(db_path):
                            os.remove(db_path)
                    except:
                        pass
                    try:
                        wal_path = db_path + "-wal"
                        if os.path.exists(wal_path):
                            os.remove(wal_path)
                    except:
                        pass
                    try:
                        shm_path = db_path + "-shm"
                        if os.path.exists(shm_path):
                            os.remove(shm_path)
                    except:
                        pass
                    # Force DELETE mode for new database
                    self._force_delete_mode = True
        
        # Erstelle Schema
        self._create_schema()
        
        # Führe Migrationen aus
        self._migrate_schema()
        self._migration_run = True
    
    @contextmanager
    def _lock_with_timeout(self, timeout: float = None):
        """
        Context Manager für Lock mit Timeout.
        
        Args:
            timeout: Timeout in Sekunden (None = verwendet self.lock_timeout)
        
        Raises:
            TimeoutError: Wenn Lock nicht innerhalb des Timeouts erworben werden kann
        """
        if timeout is None:
            timeout = self.lock_timeout
        
        acquired = False
        start_time = time.time()
        
        # Versuche Lock zu erwerben mit Timeout
        while not acquired:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Could not acquire database lock within {timeout} seconds")
            
            # Versuche Lock zu erwerben (non-blocking)
            acquired = self.lock.acquire(blocking=False)
            if not acquired:
                time.sleep(0.01)  # Kurze Pause bevor erneuter Versuch
        
        try:
            yield
        finally:
            self.lock.release()
    
    def get_connection(self, reuse: bool = False):
        """
        Gibt eine Datenbankverbindung zurück (mit WAL-Mode).
        
        Args:
            reuse: Wenn True, versucht eine wiederverwendbare Verbindung zu nutzen
        
        Returns:
            sqlite3.Connection: Datenbankverbindung
        """
        # Wenn Reuse aktiviert und bereits eine Verbindung im Thread-Local existiert
        if reuse and hasattr(self._thread_local, 'connection'):
            conn = self._thread_local.connection
            # Prüfe ob Verbindung noch gültig ist
            try:
                conn.execute("SELECT 1")
                return conn
            except (sqlite3.ProgrammingError, sqlite3.OperationalError, sqlite3.DatabaseError) as e:
                # Verbindung ist ungültig, erstelle neue
                # Clear the invalid connection from thread-local storage
                try:
                    delattr(self._thread_local, 'connection')
                except:
                    pass
                pass
        
        # Erstelle neue Verbindung
        pragmas_set = False  # Track if PRAGMAs were set in recovery
        try:
            # Try to open connection - this can fail if WAL file is corrupted
            try:
                conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
            except sqlite3.DatabaseError as open_err:
                # Try to checkpoint and recover WAL file
                try:
                    recovery_conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
                    try:
                        recovery_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    except:
                        pass
                    recovery_conn.close()
                except:
                    pass
                # Now try opening again, but force DELETE mode to avoid WAL issues
                conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
                try:
                    conn.execute("PRAGMA journal_mode=DELETE")
                    pragmas_set = True
                    conn.execute("PRAGMA foreign_keys=ON")
                    conn.execute("PRAGMA busy_timeout=10000")
                except:
                    pass
                # Skip the rest of WAL setup since we're in DELETE mode now
                if reuse:
                    self._thread_local.connection = conn
                return conn
            
            # Check current journal_mode before setting
            try:
                current_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            except Exception as e:
                current_mode = None
            
            # Only set WAL mode if not already in WAL mode and not forced to DELETE mode
            if current_mode != "wal" and not self._force_delete_mode:
                try:
                    conn.execute("PRAGMA journal_mode=WAL")
                except sqlite3.DatabaseError as wal_err:
                    # If setting WAL mode fails, fall back to DELETE mode
                    self._force_delete_mode = True  # Remember to use DELETE mode from now on
                    try:
                        conn.execute("PRAGMA journal_mode=DELETE")
                    except:
                        pass
            elif self._force_delete_mode:
                # Force DELETE mode if we've had issues with WAL
                try:
                    conn.execute("PRAGMA journal_mode=DELETE")
                except:
                    pass
        except sqlite3.DatabaseError as e:
            # Try to close the connection and recover
            try:
                conn.close()
            except:
                pass
            # Try to checkpoint WAL file to recover from corruption
            try:
                recovery_conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
                try:
                    recovery_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except:
                    pass
                recovery_conn.close()
            except:
                pass
            # Now try to create connection again - skip WAL mode to avoid the issue
            try:
                conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
                # Don't try to set WAL mode if it caused an error - use DELETE mode instead
                try:
                    conn.execute("PRAGMA journal_mode=DELETE")
                except:
                    pass  # Ignore if this also fails
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA busy_timeout=10000")
                pragmas_set = True  # Mark that PRAGMAs were set
            except Exception as retry_err:
                raise e  # Raise original error if recovery fails
        except Exception as e:
            raise
        
        # Set PRAGMAs (if not already set in recovery path)
        if not pragmas_set:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=10000")  # 10 Sekunden Timeout für locked database
        
        # Speichere für Reuse
        if reuse:
            self._thread_local.connection = conn
        
        return conn
    
    @contextmanager
    def connection_context(self):
        """
        Context Manager für wiederverwendbare Datenbankverbindungen (thread-safe).
        Verbindungen werden innerhalb des Contexts wiederverwendet.
        Der DB-Lock wird für die gesamte Dauer des Contexts gehalten.
        
        Usage:
            with db.connection_context() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ...")
        """
        with self.lock:
            conn = self.get_connection(reuse=True)
            try:
                yield conn
            finally:
                # Verbindung wird nicht geschlossen, sondern für weitere Queries wiederverwendet
                # Sie wird automatisch geschlossen wenn Thread endet oder neue erstellt wird
                pass
    
    def close_reused_connection(self):
        """Schließt eine wiederverwendete Verbindung explizit"""
        if hasattr(self._thread_local, 'connection'):
            try:
                self._thread_local.connection.close()
            except:
                pass
            delattr(self._thread_local, 'connection')
    
    def _create_schema(self):
        """Erstellt das Datenbank-Schema"""
        max_retries = 5
        retry_delay = 0.5  # 500ms
        
        
        for attempt in range(max_retries):
            conn = None
            try:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                # 1. metrics - Historische Metriken
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    metric_type TEXT NOT NULL,
                    value REAL NOT NULL,
                    unit TEXT,
                    department TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_type ON metrics(metric_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_department ON metrics(department)")
            
                # 2. alerts - Warnungen
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    department TEXT,
                    metric_type TEXT,
                    value REAL,
                    acknowledged INTEGER DEFAULT 0,
                    resolved_at TEXT,
                    alert_type TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_department ON alerts(department)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_acknowledged ON alerts(acknowledged)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_resolved_at ON alerts(resolved_at)")  # Für WHERE resolved_at IS NULL
            
                # 3. recommendations - KI-Empfehlungen
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    priority TEXT NOT NULL,
                    department TEXT,
                    rec_type TEXT,
                    status TEXT DEFAULT 'pending',
                    action TEXT,
                    reason TEXT,
                    expected_impact TEXT,
                    safety_note TEXT,
                    explanation_score TEXT,
                    accepted_at TEXT,
                    rejected_at TEXT,
                    action_text TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_recommendations_status ON recommendations(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_recommendations_priority ON recommendations(priority)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_recommendations_department ON recommendations(department)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_recommendations_rec_type ON recommendations(rec_type)")
            
                # 4. predictions - Vorhersagen
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    prediction_type TEXT NOT NULL,
                    predicted_value REAL NOT NULL,
                    confidence REAL NOT NULL,
                    time_horizon_minutes INTEGER NOT NULL,
                    department TEXT,
                    model_version TEXT,
                    features_json TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_timestamp ON predictions(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_type ON predictions(prediction_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_department ON predictions(department)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_time_horizon ON predictions(time_horizon_minutes)")  # Für WHERE time_horizon_minutes <= X
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_timestamp_horizon ON predictions(timestamp, time_horizon_minutes)")  # Composite für ORDER BY
            
                # 5. capacity - Kapazitätsdaten
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS capacity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    department TEXT NOT NULL,
                    total_beds INTEGER NOT NULL,
                    occupied_beds INTEGER NOT NULL,
                    available_beds INTEGER NOT NULL,
                    utilization_rate REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_capacity_timestamp ON capacity(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_capacity_department ON capacity(department)")
            
                # 6. transport_requests - Transportanfragen
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS transport_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    from_location TEXT NOT NULL,
                    to_location TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_type TEXT NOT NULL,
                    estimated_time_minutes INTEGER,
                    actual_time_minutes INTEGER,
                    start_time TEXT,
                    expected_completion_time TEXT,
                    delay_minutes INTEGER,
                    related_entity_type TEXT,
                    related_entity_id INTEGER,
                    planned_start_time TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_transport_status ON transport_requests(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_transport_priority ON transport_requests(priority)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_transport_timestamp ON transport_requests(timestamp)")
            
                # 7. inventory - Inventar-Status
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_name TEXT NOT NULL,
                    department TEXT NOT NULL,
                    current_stock INTEGER NOT NULL,
                    min_threshold INTEGER NOT NULL,
                    max_capacity INTEGER NOT NULL,
                    unit TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    category TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventory_department ON inventory(department)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventory_stock ON inventory(current_stock)")
            
                # 8. inventory_orders - Bestellungen
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventory_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    order_date TEXT NOT NULL,
                    expected_delivery TEXT,
                    transport_id INTEGER,
                    department TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (item_id) REFERENCES inventory(id)
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON inventory_orders(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_item_id ON inventory_orders(item_id)")
            
                # 9. inventory_consumption - Verbrauchshistorie
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventory_consumption (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    consumption_amount REAL NOT NULL,
                    ed_load REAL,
                    beds_occupied INTEGER,
                    activity_factor REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (item_id) REFERENCES inventory(id)
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_consumption_item_id ON inventory_consumption(item_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_consumption_timestamp ON inventory_consumption(timestamp)")
            
                # 10. devices - Geräte
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL UNIQUE,
                    device_name TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    department TEXT NOT NULL,
                    usage_hours INTEGER DEFAULT 0,
                    max_usage_hours INTEGER,
                    last_maintenance TEXT,
                    next_maintenance_due TEXT,
                    urgency_level TEXT,
                    scheduled_maintenance_time TEXT,
                    maintenance_confirmed INTEGER DEFAULT 0,
                    maintenance_duration_minutes INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_devices_department ON devices(department)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_devices_urgency ON devices(urgency_level)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_devices_maintenance ON devices(next_maintenance_due)")
            
                # 11. operations - Operationen
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS operations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_type TEXT NOT NULL,
                    department TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_minutes INTEGER NOT NULL,
                    planned_start_time TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    timestamp TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_operations_status ON operations(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_operations_department ON operations(department)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_operations_timestamp ON operations(timestamp)")
            
                # 12. discharge_planning - Entlassungsplanung
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS discharge_planning (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    department TEXT NOT NULL,
                    ready_for_discharge_count INTEGER DEFAULT 0,
                    pending_discharge_count INTEGER DEFAULT 0,
                    total_patients INTEGER DEFAULT 0,
                    avg_length_of_stay_hours REAL DEFAULT 0,
                    discharge_capacity_utilization REAL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_discharge_timestamp ON discharge_planning(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_discharge_department ON discharge_planning(department)")
            
                # 13. staff - Personal
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS staff (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    department TEXT NOT NULL,
                    category TEXT NOT NULL,
                    contact TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_staff_department ON staff(department)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_staff_category ON staff(category)")
            
                # 14. staff_schedule - Dienstpläne
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS staff_schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    staff_id INTEGER NOT NULL,
                    week_start TEXT NOT NULL,
                    day TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    hours REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (staff_id) REFERENCES staff(id)
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedule_staff_id ON staff_schedule(staff_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedule_week_start ON staff_schedule(week_start)")
            
                # 15. audit_log - Prüfprotokoll
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    user TEXT NOT NULL,
                    user_role TEXT,
                    entity_type TEXT,
                    entity_id INTEGER,
                    details TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_user_role ON audit_log(user_role)")
            
                # 16. simulation_events - Simulationsereignisse
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS simulation_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    duration_minutes INTEGER NOT NULL,
                    intensity REAL,
                    affected_departments TEXT,
                    description TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON simulation_events(event_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_start_time ON simulation_events(start_time)")
            
                # 17. model_versions - KI-Modell-Versionen
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS model_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_type TEXT NOT NULL,
                    version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    parameters_json TEXT,
                    performance_metrics_json TEXT
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_models_type ON model_versions(model_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_models_created_at ON model_versions(created_at)")
            
                # 18. patient_events - Anonymisierte Patientenevents
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS patient_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    department TEXT NOT NULL,
                    patient_category TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_patient_events_timestamp ON patient_events(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_patient_events_type ON patient_events(event_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_patient_events_department ON patient_events(department)")
                
                conn.commit()
                # Success - break out of retry loop
                break
            except sqlite3.OperationalError as e:
                error_str = str(e).lower()
                if "database is locked" in error_str:
                    if conn:
                        try:
                            conn.close()
                        except:
                            pass
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                        continue  # Retry
                    else:
                        raise
                elif "disk i/o error" in error_str or "i/o error" in error_str or "disk i/o" in error_str:
                    # Disk I/O error - force DELETE mode and remove WAL files
                    self._force_delete_mode = True
                    if conn:
                        try:
                            conn.close()
                        except:
                            pass
                    # Remove WAL and SHM files
                    try:
                        wal_path = self.db_path + "-wal"
                        shm_path = self.db_path + "-shm"
                        if os.path.exists(wal_path):
                            os.remove(wal_path)
                        if os.path.exists(shm_path):
                            os.remove(shm_path)
                    except:
                        pass
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))
                        continue  # Retry with DELETE mode
                    else:
                        raise
                else:
                    if conn:
                        try:
                            conn.close()
                        except:
                            pass
                    raise
            except Exception as e:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
                raise
    
    def _migrate_schema(self):
        """Führt Schema-Migrationen aus, um fehlende Spalten hinzuzufügen"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Prüfe ob alerts Tabelle existiert und hole ihre Spalten
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alerts'")
            table_exists = cursor.fetchone()
            
            if table_exists:
                # Hole aktuelle Spalten der alerts Tabelle
                cursor.execute("PRAGMA table_info(alerts)")
                existing_columns = [row[1] for row in cursor.fetchall()]
                
                # Define all columns that should exist in alerts table
                required_columns = {
                    'metric_type': 'TEXT',
                    'value': 'REAL',
                    'resolved_at': 'TEXT',
                    'acknowledged': 'INTEGER DEFAULT 0',
                    'department': 'TEXT',
                    'alert_type': 'TEXT',
                    'created_at': 'TEXT DEFAULT CURRENT_TIMESTAMP'
                }
                
                # Add any missing columns
                for col_name, col_def in required_columns.items():
                    if col_name not in existing_columns:
                        try:
                            cursor.execute(f"ALTER TABLE alerts ADD COLUMN {col_name} {col_def}")
                            conn.commit()
                        except Exception as e:
                            # Don't raise - continue with other columns
                            pass
            
            # Migrate recommendations table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='recommendations'")
            rec_table_exists = cursor.fetchone()
            
            if rec_table_exists:
                cursor.execute("PRAGMA table_info(recommendations)")
                existing_rec_columns = [row[1] for row in cursor.fetchall()]
                
                # Define all columns that should exist in recommendations table
                required_rec_columns = {
                    'accepted_at': 'TEXT',
                    'rejected_at': 'TEXT',
                    'action_text': 'TEXT',
                    'created_at': 'TEXT DEFAULT CURRENT_TIMESTAMP',
                    'explanation_score': 'TEXT',
                    'safety_note': 'TEXT',
                    'expected_impact': 'TEXT',
                    'reason': 'TEXT',
                    'action': 'TEXT',
                    'rec_type': 'TEXT'
                }
                
                # Add any missing columns
                for col_name, col_def in required_rec_columns.items():
                    if col_name not in existing_rec_columns:
                        try:
                            cursor.execute(f"ALTER TABLE recommendations ADD COLUMN {col_name} {col_def}")
                            conn.commit()
                        except Exception as e:
                            # Don't raise - continue with other columns
                            pass
            
            # Migrate inventory table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory'")
            inv_table_exists = cursor.fetchone()
            
            if inv_table_exists:
                cursor.execute("PRAGMA table_info(inventory)")
                existing_inv_columns = [row[1] for row in cursor.fetchall()]
                
                # Define all columns that should exist in inventory table
                # Note: Can't use NOT NULL when adding to existing table, so use TEXT with default
                required_inv_columns = {
                    'last_updated': 'TEXT',
                    'category': 'TEXT',
                    'created_at': 'TEXT DEFAULT CURRENT_TIMESTAMP'
                }
                
                # Add any missing columns
                for col_name, col_def in required_inv_columns.items():
                    if col_name not in existing_inv_columns:
                        try:
                            cursor.execute(f"ALTER TABLE inventory ADD COLUMN {col_name} {col_def}")
                            conn.commit()
                        except Exception as e:
                            # Don't raise - continue with other columns
                            pass
            
            # Migrate predictions table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='predictions'")
            pred_table_exists = cursor.fetchone()
            
            if pred_table_exists:
                cursor.execute("PRAGMA table_info(predictions)")
                existing_pred_columns = [row[1] for row in cursor.fetchall()]
                
                # Define all columns that should exist in predictions table
                required_pred_columns = {
                    'model_version': 'TEXT',
                    'features_json': 'TEXT',
                    'created_at': 'TEXT DEFAULT CURRENT_TIMESTAMP'
                }
                
                # Add any missing columns
                for col_name, col_def in required_pred_columns.items():
                    if col_name not in existing_pred_columns:
                        try:
                            cursor.execute(f"ALTER TABLE predictions ADD COLUMN {col_name} {col_def}")
                            conn.commit()
                        except Exception as e:
                            # Don't raise - continue with other columns
                            pass
            
            # Migrate audit_log table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
            audit_table_exists = cursor.fetchone()
            
            if audit_table_exists:
                cursor.execute("PRAGMA table_info(audit_log)")
                existing_audit_columns = [row[1] for row in cursor.fetchall()]
                
                # Define all columns that should exist in audit_log table
                # Note: Can't use NOT NULL when adding to existing table, so use TEXT
                required_audit_columns = {
                    'user': 'TEXT',
                    'user_role': 'TEXT',
                    'entity_type': 'TEXT',
                    'entity_id': 'INTEGER',
                    'details': 'TEXT',
                    'created_at': 'TEXT DEFAULT CURRENT_TIMESTAMP'
                }
                
                # Add any missing columns
                for col_name, col_def in required_audit_columns.items():
                    if col_name not in existing_audit_columns:
                        try:
                            cursor.execute(f"ALTER TABLE audit_log ADD COLUMN {col_name} {col_def}")
                            conn.commit()
                        except Exception as e:
                            # Don't raise - continue with other columns
                            pass
            
            # Migrate inventory_consumption table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_consumption'")
            inv_cons_table_exists = cursor.fetchone()
            
            if inv_cons_table_exists:
                cursor.execute("PRAGMA table_info(inventory_consumption)")
                existing_inv_cons_columns = [row[1] for row in cursor.fetchall()]
                
                # Define all columns that should exist in inventory_consumption table
                required_inv_cons_columns = {
                    'ed_load': 'REAL',
                    'beds_occupied': 'INTEGER',
                    'activity_factor': 'REAL',
                    'created_at': 'TEXT DEFAULT CURRENT_TIMESTAMP'
                }
                
                # Add any missing columns
                for col_name, col_def in required_inv_cons_columns.items():
                    if col_name not in existing_inv_cons_columns:
                        try:
                            cursor.execute(f"ALTER TABLE inventory_consumption ADD COLUMN {col_name} {col_def}")
                            conn.commit()
                        except Exception as e:
                            # Don't raise - continue with other columns
                            pass
            
            # Migrate inventory_orders table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_orders'")
            inv_orders_table_exists = cursor.fetchone()
            
            if inv_orders_table_exists:
                cursor.execute("PRAGMA table_info(inventory_orders)")
                existing_inv_orders_columns = [row[1] for row in cursor.fetchall()]
                
                # Define all columns that should exist in inventory_orders table
                required_inv_orders_columns = {
                    'order_date': 'TEXT',
                    'expected_delivery': 'TEXT',
                    'transport_id': 'INTEGER',
                    'department': 'TEXT'
                }
                
                # Add any missing columns
                for col_name, col_def in required_inv_orders_columns.items():
                    if col_name not in existing_inv_orders_columns:
                        try:
                            cursor.execute(f"ALTER TABLE inventory_orders ADD COLUMN {col_name} {col_def}")
                            conn.commit()
                        except Exception as e:
                            # Don't raise - continue with other columns
                            pass
            
            # Migrate discharge_planning table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='discharge_planning'")
            discharge_table_exists = cursor.fetchone()
            
            if discharge_table_exists:
                cursor.execute("PRAGMA table_info(discharge_planning)")
                existing_discharge_columns = [row[1] for row in cursor.fetchall()]
                
                # Define all columns that should exist in discharge_planning table
                required_discharge_columns = {
                    'total_patients': 'INTEGER DEFAULT 0',
                    'avg_length_of_stay_hours': 'REAL DEFAULT 0',
                    'discharge_capacity_utilization': 'REAL DEFAULT 0',
                    'created_at': 'TEXT DEFAULT CURRENT_TIMESTAMP'
                }
                
                # Add any missing columns
                for col_name, col_def in required_discharge_columns.items():
                    if col_name not in existing_discharge_columns:
                        try:
                            cursor.execute(f"ALTER TABLE discharge_planning ADD COLUMN {col_name} {col_def}")
                            conn.commit()
                        except Exception as e:
                            # Don't raise - continue with other columns
                            pass
            
            # Migrate transport_requests table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transport_requests'")
            transport_table_exists = cursor.fetchone()
            
            if transport_table_exists:
                cursor.execute("PRAGMA table_info(transport_requests)")
                existing_transport_columns = [row[1] for row in cursor.fetchall()]
                
                # Define all columns that should exist in transport_requests table
                required_transport_columns = {
                    'requested_time_start': 'TEXT',
                    'requested_time_end': 'TEXT'
                }
                
                # Add any missing columns
                for col_name, col_def in required_transport_columns.items():
                    if col_name not in existing_transport_columns:
                        try:
                            cursor.execute(f"ALTER TABLE transport_requests ADD COLUMN {col_name} {col_def}")
                            conn.commit()
                        except Exception as e:
                            # Don't raise - continue with other columns
                            pass
            
            # Migrate staff_schedule table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='staff_schedule'")
            schedule_table_exists = cursor.fetchone()
            
            if schedule_table_exists:
                cursor.execute("PRAGMA table_info(staff_schedule)")
                existing_schedule_columns = [row[1] for row in cursor.fetchall()]
                
                # Define all columns that should exist in staff_schedule table
                required_schedule_columns = {
                    'is_vacation': 'INTEGER DEFAULT 0'
                }
                
                # Add any missing columns
                for col_name, col_def in required_schedule_columns.items():
                    if col_name not in existing_schedule_columns:
                        try:
                            cursor.execute(f"ALTER TABLE staff_schedule ADD COLUMN {col_name} {col_def}")
                            conn.commit()
                        except Exception as e:
                            # Don't raise - continue with other columns
                            pass
            
            # Migrate devices table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='devices'")
            devices_table_exists = cursor.fetchone()
            
            if devices_table_exists:
                cursor.execute("PRAGMA table_info(devices)")
                existing_devices_columns = [row[1] for row in cursor.fetchall()]
                
                # Define all columns that should exist in devices table
                required_devices_columns = {
                    'maintenance_duration_minutes': 'INTEGER'
                }
                
                # Add any missing columns
                for col_name, col_def in required_devices_columns.items():
                    if col_name not in existing_devices_columns:
                        try:
                            cursor.execute(f"ALTER TABLE devices ADD COLUMN {col_name} {col_def}")
                            conn.commit()
                        except Exception as e:
                            # Don't raise - continue with other columns
                            pass
        except Exception as e:
            raise
        finally:
            conn.close()
    
    # ===== ALERTS =====
    
    def get_active_alerts(self) -> List[Dict]:
        """Gibt aktive Warnungen zurück"""
        # Always run migration (idempotent - safe to call multiple times)
        # This ensures migration runs even if database object was created before migration code was added
        try:
            self._migrate_schema()
        except Exception as e:
            # Continue anyway - defensive query will handle missing columns
            pass
        
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Check if columns exist before querying
                cursor.execute("PRAGMA table_info(alerts)")
                columns = [row[1] for row in cursor.fetchall()]
                
                # Build query based on available columns
                # Check for all required columns
                has_resolved_at = 'resolved_at' in columns
                has_metric_type = 'metric_type' in columns
                has_value = 'value' in columns
                has_acknowledged = 'acknowledged' in columns
                has_department = 'department' in columns
                has_alert_type = 'alert_type' in columns
                
                # Build SELECT clause based on available columns
                select_parts = ['id', 'timestamp', 'severity', 'message']
                if has_alert_type:
                    select_parts.append('alert_type')
                else:
                    select_parts.append('NULL as alert_type')
                
                if has_department:
                    select_parts.append('department')
                else:
                    select_parts.append('NULL as department')
                
                if has_metric_type:
                    select_parts.append('metric_type')
                else:
                    select_parts.append('NULL as metric_type')
                
                if has_value:
                    select_parts.append('value')
                else:
                    select_parts.append('NULL as value')
                
                if has_acknowledged:
                    select_parts.append('acknowledged')
                else:
                    select_parts.append('0 as acknowledged')
                
                if has_resolved_at:
                    select_parts.append('resolved_at')
                else:
                    select_parts.append('NULL as resolved_at')
                
                select_clause = ', '.join(select_parts)
                
                # Build WHERE clause - only filter by resolved_at if column exists
                where_clause = "WHERE resolved_at IS NULL" if has_resolved_at else ""
                
                query = f"""
                    SELECT {select_clause}
                    FROM alerts
                    {where_clause}
                    ORDER BY timestamp DESC
                """
                
                try:
                    cursor.execute(query)
                    rows = cursor.fetchall()
                except Exception as query_error:
                    # If query failed, try a simpler query without resolved_at filter
                    if has_resolved_at:
                        # Try again without resolved_at filter - maybe column was added but not committed properly
                        simple_query = f"""
                            SELECT {select_clause}
                            FROM alerts
                            ORDER BY timestamp DESC
                        """
                        try:
                            cursor.execute(simple_query)
                            rows = cursor.fetchall()
                        except Exception as fallback_error:
                            raise query_error  # Raise original error
                    else:
                        raise query_error  # Re-raise if we don't have resolved_at
                
                # Map results to dict based on column positions
                result = []
                for row in rows:
                    row_dict = {
                        'id': row[0],
                        'timestamp': row[1],
                        'severity': row[2],
                        'message': row[3],
                    }
                    
                    idx = 4
                    if has_alert_type:
                        row_dict['alert_type'] = row[idx]
                        idx += 1
                    else:
                        row_dict['alert_type'] = None
                    
                    if has_department:
                        row_dict['department'] = row[idx]
                        idx += 1
                    else:
                        row_dict['department'] = None
                    
                    if has_metric_type:
                        row_dict['metric_type'] = row[idx]
                        idx += 1
                    else:
                        row_dict['metric_type'] = None
                    
                    if has_value:
                        row_dict['value'] = row[idx]
                        idx += 1
                    else:
                        row_dict['value'] = None
                    
                    if has_acknowledged:
                        row_dict['acknowledged'] = bool(row[idx])
                        idx += 1
                    else:
                        row_dict['acknowledged'] = False
                    
                    if has_resolved_at:
                        row_dict['resolved_at'] = row[idx]
                    else:
                        row_dict['resolved_at'] = None
                    
                    result.append(row_dict)
                
                return result
            finally:
                conn.close()
    
    def acknowledge_alert(self, alert_id: int) -> bool:
        """Bestätigt eine Warnung"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    UPDATE alerts
                    SET acknowledged = 1
                    WHERE id = ?
                """, (alert_id,))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()
    
    def reset_all_alerts(self) -> int:
        """Setzt alle Warnungen zurück"""
        # Ensure migration has run
        if not getattr(self, '_migration_run', False):
            try:
                self._migrate_schema()
                self._migration_run = True
            except Exception:
                pass  # Continue anyway
        
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Check if resolved_at column exists
                cursor.execute("PRAGMA table_info(alerts)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if 'resolved_at' in columns:
                    cursor.execute("UPDATE alerts SET resolved_at = ? WHERE resolved_at IS NULL", 
                                 (datetime.now(timezone.utc).isoformat(),))
                    conn.commit()
                    return cursor.rowcount
                else:
                    # Column doesn't exist - can't reset, return 0
                    return 0
            finally:
                conn.close()
    
    def get_alerts_by_time_range(self, hours: int) -> List[Dict]:
        """Gibt Warnungen nach Zeitbereich zurück"""
        # Ensure migration has run
        if not getattr(self, '_migration_run', False):
            try:
                self._migrate_schema()
                self._migration_run = True
            except Exception:
                pass  # Continue anyway
        
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Check if columns exist before querying
                cursor.execute("PRAGMA table_info(alerts)")
                columns = [row[1] for row in cursor.fetchall()]
                
                # Check for all required columns
                has_resolved_at = 'resolved_at' in columns
                has_metric_type = 'metric_type' in columns
                has_value = 'value' in columns
                has_acknowledged = 'acknowledged' in columns
                has_department = 'department' in columns
                
                # Build SELECT clause based on available columns
                select_parts = ['id', 'timestamp', 'severity', 'message']
                if has_department:
                    select_parts.append('department')
                else:
                    select_parts.append('NULL as department')
                
                if has_metric_type:
                    select_parts.append('metric_type')
                else:
                    select_parts.append('NULL as metric_type')
                
                if has_value:
                    select_parts.append('value')
                else:
                    select_parts.append('NULL as value')
                
                if has_acknowledged:
                    select_parts.append('acknowledged')
                else:
                    select_parts.append('0 as acknowledged')
                
                if has_resolved_at:
                    select_parts.append('resolved_at')
                else:
                    select_parts.append('NULL as resolved_at')
                
                select_clause = ', '.join(select_parts)
                
                query = f"""
                    SELECT {select_clause}
                    FROM alerts
                    WHERE timestamp >= ?
                    ORDER BY timestamp DESC
                """
                
                cursor.execute(query, (cutoff,))
                rows = cursor.fetchall()
                
                # Map results to dict based on column positions
                result = []
                for row in rows:
                    row_dict = {
                        'id': row[0],
                        'timestamp': row[1],
                        'severity': row[2],
                        'message': row[3],
                    }
                    
                    idx = 4
                    if has_department:
                        row_dict['department'] = row[idx]
                        idx += 1
                    else:
                        row_dict['department'] = None
                    
                    if has_metric_type:
                        row_dict['metric_type'] = row[idx]
                        idx += 1
                    else:
                        row_dict['metric_type'] = None
                    
                    if has_value:
                        row_dict['value'] = row[idx]
                        idx += 1
                    else:
                        row_dict['value'] = None
                    
                    if has_acknowledged:
                        row_dict['acknowledged'] = bool(row[idx])
                        idx += 1
                    else:
                        row_dict['acknowledged'] = False
                    
                    if has_resolved_at:
                        row_dict['resolved_at'] = row[idx]
                    else:
                        row_dict['resolved_at'] = None
                    
                    result.append(row_dict)
                
                return result
            finally:
                conn.close()
    
    # ===== RECOMMENDATIONS =====
    
    def get_pending_recommendations(self) -> List[Dict]:
        """Gibt ausstehende Empfehlungen zurück"""
        # Ensure migration has run
        try:
            self._migrate_schema()
        except Exception:
            pass  # Continue anyway
        
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Check if columns exist before querying
                cursor.execute("PRAGMA table_info(recommendations)")
                columns = [row[1] for row in cursor.fetchall()]
                
                # Check for all required columns
                has_accepted_at = 'accepted_at' in columns
                has_rejected_at = 'rejected_at' in columns
                has_action_text = 'action_text' in columns
                has_explanation_score = 'explanation_score' in columns
                has_safety_note = 'safety_note' in columns
                has_expected_impact = 'expected_impact' in columns
                has_reason = 'reason' in columns
                has_action = 'action' in columns
                has_rec_type = 'rec_type' in columns
                
                # Build SELECT clause based on available columns
                select_parts = ['id', 'timestamp', 'title', 'description', 'priority']
                
                if 'department' in columns:
                    select_parts.append('department')
                else:
                    select_parts.append('NULL as department')
                
                if has_rec_type:
                    select_parts.append('rec_type')
                else:
                    select_parts.append('NULL as rec_type')
                
                select_parts.append('status')
                
                if has_action:
                    select_parts.append('action')
                else:
                    select_parts.append('NULL as action')
                
                if has_reason:
                    select_parts.append('reason')
                else:
                    select_parts.append('NULL as reason')
                
                if has_expected_impact:
                    select_parts.append('expected_impact')
                else:
                    select_parts.append('NULL as expected_impact')
                
                if has_safety_note:
                    select_parts.append('safety_note')
                else:
                    select_parts.append('NULL as safety_note')
                
                if has_explanation_score:
                    select_parts.append('explanation_score')
                else:
                    select_parts.append('NULL as explanation_score')
                
                if has_accepted_at:
                    select_parts.append('accepted_at')
                else:
                    select_parts.append('NULL as accepted_at')
                
                if has_rejected_at:
                    select_parts.append('rejected_at')
                else:
                    select_parts.append('NULL as rejected_at')
                
                if has_action_text:
                    select_parts.append('action_text')
                else:
                    select_parts.append('NULL as action_text')
                
                select_clause = ', '.join(select_parts)
                
                query = f"""
                    SELECT {select_clause}
                    FROM recommendations
                    WHERE status = 'pending'
                    ORDER BY 
                        CASE priority
                            WHEN 'high' THEN 1
                            WHEN 'hoch' THEN 1
                            WHEN 'medium' THEN 2
                            WHEN 'mittel' THEN 2
                            ELSE 3
                        END,
                        timestamp DESC
                """
                
                cursor.execute(query)
                rows = cursor.fetchall()
                
                # Map results to dict based on column positions
                result = []
                for row in rows:
                    row_dict = {
                        'id': row[0],
                        'timestamp': row[1],
                        'title': row[2],
                        'description': row[3],
                        'priority': row[4],
                    }
                    
                    idx = 5
                    if 'department' in columns:
                        row_dict['department'] = row[idx]
                        idx += 1
                    else:
                        row_dict['department'] = None
                    
                    if has_rec_type:
                        row_dict['rec_type'] = row[idx]
                        idx += 1
                    else:
                        row_dict['rec_type'] = None
                    
                    row_dict['status'] = row[idx]
                    idx += 1
                    
                    if has_action:
                        row_dict['action'] = row[idx]
                        idx += 1
                    else:
                        row_dict['action'] = None
                    
                    if has_reason:
                        row_dict['reason'] = row[idx]
                        idx += 1
                    else:
                        row_dict['reason'] = None
                    
                    if has_expected_impact:
                        row_dict['expected_impact'] = row[idx]
                        idx += 1
                    else:
                        row_dict['expected_impact'] = None
                    
                    if has_safety_note:
                        row_dict['safety_note'] = row[idx]
                        idx += 1
                    else:
                        row_dict['safety_note'] = None
                    
                    if has_explanation_score:
                        row_dict['explanation_score'] = row[idx]
                        idx += 1
                    else:
                        row_dict['explanation_score'] = None
                    
                    if has_accepted_at:
                        row_dict['accepted_at'] = row[idx]
                        idx += 1
                    else:
                        row_dict['accepted_at'] = None
                    
                    if has_rejected_at:
                        row_dict['rejected_at'] = row[idx]
                        idx += 1
                    else:
                        row_dict['rejected_at'] = None
                    
                    if has_action_text:
                        row_dict['action_text'] = row[idx]
                    else:
                        row_dict['action_text'] = None
                    
                    result.append(row_dict)
                
                return result
            finally:
                conn.close()
    
    def accept_recommendation(self, rec_id: int, action_text: str = "") -> bool:
        """Akzeptiert eine Empfehlung"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    UPDATE recommendations
                    SET status = 'accepted',
                        accepted_at = ?,
                        action_text = ?
                    WHERE id = ?
                """, (datetime.now(timezone.utc).isoformat(), action_text, rec_id))
                conn.commit()
                
                # Audit log
                cursor.execute("""
                    INSERT INTO audit_log (timestamp, action_type, user, user_role, entity_type, entity_id, details)
                    VALUES (?, 'recommendation_accepted', 'System', 'system', 'recommendation', ?, ?)
                """, (datetime.now(timezone.utc).isoformat(), rec_id, f"Empfehlung {rec_id} akzeptiert: {action_text}"))
                conn.commit()
                
                return cursor.rowcount > 0
            finally:
                conn.close()
    
    def reject_recommendation(self, rec_id: int, action_text: str = "") -> bool:
        """Lehnt eine Empfehlung ab"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    UPDATE recommendations
                    SET status = 'rejected',
                        rejected_at = ?,
                        action_text = ?
                    WHERE id = ?
                """, (datetime.now(timezone.utc).isoformat(), action_text, rec_id))
                conn.commit()
                
                # Audit log
                cursor.execute("""
                    INSERT INTO audit_log (timestamp, action_type, user, user_role, entity_type, entity_id, details)
                    VALUES (?, 'recommendation_rejected', 'System', 'system', 'recommendation', ?, ?)
                """, (datetime.now(timezone.utc).isoformat(), rec_id, f"Empfehlung {rec_id} abgelehnt: {action_text}"))
                conn.commit()
                
                return cursor.rowcount > 0
            finally:
                conn.close()
    
    # ===== CAPACITY =====
    
    def get_capacity_overview(self) -> List[Dict]:
        """Gibt Kapazitätsübersicht zurück"""
        with self.lock:
            conn = self.get_connection()
            # Try to recover from corrupted WAL file before creating cursor
            try:
                import os
                journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                if journal_mode == "wal":
                    wal_path = self.db_path + "-wal"
                    if os.path.exists(wal_path) and os.path.getsize(wal_path) == 0:
                        # Try to checkpoint and truncate the WAL
                        try:
                            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                        except:
                            # If checkpoint fails, switch to DELETE mode
                            try:
                                conn.execute("PRAGMA journal_mode=DELETE")
                            except:
                                pass
            except:
                pass
            try:
                cursor = conn.cursor()
            except sqlite3.OperationalError as cursor_err:
                raise
            try:
                # Hole neueste Kapazitätsdaten pro Abteilung
                cursor.execute("""
                    SELECT department, total_beds, occupied_beds, available_beds, utilization_rate
                    FROM capacity
                    WHERE id IN (
                        SELECT MAX(id) FROM capacity GROUP BY department
                    )
                    ORDER BY department
                """)
                rows = cursor.fetchall()
                return [{
                    'department': row[0],
                    'total_beds': row[1],
                    'occupied_beds': row[2],
                    'available_beds': row[3],
                    'free_beds': row[3],
                    'utilization_percent': row[4] * 100
                } for row in rows]
            finally:
                conn.close()
    
    def get_capacity_from_simulation(self, sim_metrics: Dict) -> List[Dict]:
        """Gibt Kapazitätsdaten basierend auf Simulationsmetriken zurück"""
        # Prüfe ob abteilungsbezogene Bettbelegung vorhanden ist
        department_beds = sim_metrics.get('department_beds')
        
        if department_beds:
            # Verwende abteilungsbezogene Daten direkt
            capacity = []
            
            for dept, dept_data in department_beds.items():
                total_beds = dept_data.get('total_beds', 0)
                
                if total_beds > 0:
                    # Für ER/ED-Abteilung: Verwende ed_load aus sim_metrics für Konsistenz mit Dashboard
                    # WICHTIG: utilization_percent direkt aus ed_load, nicht neu berechnen!
                    if dept in ('ER', 'ED'):
                        ed_load = sim_metrics.get('ed_load', 65.0)  # Fallback auf 65% wenn nicht vorhanden
                        utilization = ed_load / 100.0  # ed_load ist in Prozent (0-100), utilization ist 0.0-1.0
                        # occupied_beds wird aus utilization berechnet, nicht umgekehrt
                        occupied_beds = int(total_beds * utilization)
                        available_beds = total_beds - occupied_beds
                        # utilization_percent direkt aus ed_load, um Rundungsfehler zu vermeiden
                        utilization_percent = ed_load
                    else:
                        # Für alle anderen Abteilungen: Prüfe ob utilization_rate bereits vorhanden ist
                        if 'utilization_rate' in dept_data and dept_data['utilization_rate'] is not None:
                            # Verwende vorhandene utilization_rate (keine Neuberechnung)
                            utilization = dept_data['utilization_rate']
                            utilization_percent = utilization * 100
                            # Berechne occupied_beds aus utilization_rate
                            occupied_beds = int(total_beds * utilization)
                            available_beds = total_beds - occupied_beds
                        else:
                            # Fallback: Verwende Werte aus department_beds und berechne utilization
                            occupied_beds = dept_data.get('occupied_beds', 0)
                            available_beds = dept_data.get('available_beds', 0)
                            if total_beds > 0:
                                utilization = occupied_beds / total_beds
                                utilization_percent = utilization * 100
                            else:
                                utilization = 0.0
                                utilization_percent = 0.0
                    
                    capacity.append({
                        'department': dept,
                        'total_beds': total_beds,
                        'occupied_beds': occupied_beds,
                        'available_beds': available_beds,
                        'free_beds': available_beds,
                        'utilization_rate': utilization,
                        'utilization_percent': utilization_percent
                    })
            
            # Füge zusätzliche Abteilungen hinzu, die nicht in department_beds sind
            # (für Rückwärtskompatibilität)
            # Erstelle Set der bereits vorhandenen Abteilungen, um Duplikate zu vermeiden
            existing_depts = {cap['department'] for cap in capacity}
            
            additional_depts = {
                'General Ward': 12,
                'Radiology': 0,
                'Neurology': 6,
                'Pediatrics': 5,
                'Oncology': 5,
                'Maternity': 0
            }
            
            beds_free = int(sim_metrics.get('beds_free', 0))
            total_beds_all = sum(d.get('total_beds', 0) for d in department_beds.values()) + sum(additional_depts.values())
            
            for dept, dept_total in additional_depts.items():
                # Nur hinzufügen, wenn Abteilung noch nicht vorhanden ist
                if dept_total > 0 and dept not in existing_depts:
                    # Verwende proportionale Verteilung für zusätzliche Abteilungen
                    dept_occupied = max(0, dept_total - int(beds_free * (dept_total / total_beds_all) if total_beds_all > 0 else 0))
                    dept_available = dept_total - dept_occupied
                    utilization = dept_occupied / dept_total if dept_total > 0 else 0
                    
                    capacity.append({
                        'department': dept,
                        'total_beds': dept_total,
                        'occupied_beds': dept_occupied,
                        'available_beds': dept_available,
                        'free_beds': dept_available,
                        'utilization_rate': utilization,
                        'utilization_percent': utilization * 100
                    })
            
            return capacity
        
        # Fallback: Alte Logik (proportionale Verteilung)
        beds_free = int(sim_metrics.get('beds_free', 0))
        total_beds = 170  # Standard-Gesamtbetten
        
        # Alle Abteilungen des Krankenhauses mit realistischer Bettenverteilung
        departments = [
            'ER', 'ICU', 'Surgery', 'Cardiology', 'General Ward',
            'Orthopedics', 'Urology', 'Gastroenterology', 'Geriatrics',
            'SpineCenter', 'ENT', 'Radiology', 'Neurology', 'Pediatrics',
            'Oncology', 'Maternity'
        ]
        
        # Bettenverteilung pro Abteilung (Summe = 170)
        dept_beds = {
            'ER': 25,
            'ICU': 15,
            'Surgery': 40,
            'Cardiology': 30,
            'General Ward': 12,
            'Orthopedics': 10,
            'Urology': 6,
            'Gastroenterology': 6,
            'Geriatrics': 5,
            'SpineCenter': 3,
            'ENT': 2,
            'Radiology': 0,  # Radiologie hat keine Betten (nur Untersuchungen)
            'Neurology': 6,
            'Pediatrics': 5,
            'Oncology': 5,
            'Maternity': 0  # Geburtshilfe wird separat verwaltet
        }
        
        capacity = []
        
        for dept in departments:
            dept_total = dept_beds.get(dept, 0)
            # Nur Abteilungen mit Betten anzeigen
            if dept_total > 0:
                # Für ER/ED-Abteilung: Verwende ed_load aus sim_metrics für Konsistenz mit Dashboard
                if dept in ('ER', 'ED'):
                    ed_load = sim_metrics.get('ed_load', 65.0)  # Fallback auf 65% wenn nicht vorhanden
                    utilization = ed_load / 100.0  # ed_load ist in Prozent (0-100), utilization ist 0.0-1.0
                    dept_occupied = int(dept_total * utilization)
                    dept_available = dept_total - dept_occupied
                    # utilization_percent direkt aus ed_load, um Rundungsfehler zu vermeiden
                    utilization_percent = ed_load
                else:
                    # Für alle anderen Abteilungen: Proportionale Verteilung basierend auf beds_free
                    dept_occupied = max(0, dept_total - int(beds_free * (dept_total / total_beds)))
                    dept_available = dept_total - dept_occupied
                    utilization = dept_occupied / dept_total if dept_total > 0 else 0
                    utilization_percent = utilization * 100
                
                capacity.append({
                    'department': dept,
                    'total_beds': dept_total,
                    'occupied_beds': dept_occupied,
                    'available_beds': dept_available,
                    'free_beds': dept_available,
                    'utilization_rate': utilization,
                    'utilization_percent': utilization_percent
                })
        
        return capacity
    
    def get_total_rooms(self) -> int:
        """Gibt Gesamtanzahl Räume zurück"""
        return 50
    
    # ===== TRANSPORT =====
    
    def get_transport_requests(self) -> List[Dict]:
        """Gibt Transportanfragen zurück"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT id, timestamp, from_location, to_location, priority, status, request_type,
                           estimated_time_minutes, actual_time_minutes, start_time, expected_completion_time,
                           delay_minutes, related_entity_type, related_entity_id, planned_start_time,
                           requested_time_start, requested_time_end
                    FROM transport_requests
                    ORDER BY 
                        CASE priority
                            WHEN 'high' THEN 1
                            WHEN 'hoch' THEN 1
                            WHEN 'medium' THEN 2
                            WHEN 'mittel' THEN 2
                            ELSE 3
                        END,
                        timestamp DESC
                """)
                rows = cursor.fetchall()
                return [{
                    'id': row[0],
                    'timestamp': row[1],
                    'from_location': row[2],
                    'to_location': row[3],
                    'priority': row[4],
                    'status': row[5],
                    'request_type': row[6],
                    'estimated_time_minutes': row[7],
                    'actual_time_minutes': row[8],
                    'start_time': row[9],
                    'expected_completion_time': row[10],
                    'delay_minutes': row[11],
                    'related_entity_type': row[12],
                    'related_entity_id': row[13],
                    'planned_start_time': row[14],
                    'requested_time_start': row[15] if len(row) > 15 else None,
                    'requested_time_end': row[16] if len(row) > 16 else None
                } for row in rows]
            finally:
                conn.close()
    
    def update_transport_status(self, transport_id: int, **kwargs) -> bool:
        """Aktualisiert Transport-Status"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                updates = []
                values = []
                for key, value in kwargs.items():
                    if key in ['status', 'start_time', 'expected_completion_time', 'planned_start_time', 
                              'actual_time_minutes', 'delay_minutes', 'requested_time_start', 'requested_time_end',
                              'estimated_time_minutes']:
                        updates.append(f"{key} = ?")
                        values.append(value)
                
                if not updates:
                    return False
                
                values.append(transport_id)
                query = f"UPDATE transport_requests SET {', '.join(updates)} WHERE id = ?"
                cursor.execute(query, values)
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()
    
    def delete_transport_request(self, transport_id: int) -> bool:
        """Löscht eine Transportanfrage"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM transport_requests WHERE id = ?", (transport_id,))
                conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                # Log error but don't raise - return False instead
                import traceback
                print(f"Error deleting transport request {transport_id}: {e}")
                traceback.print_exc()
                return False
            finally:
                conn.close()
    
    def delete_all_transport_requests(self) -> bool:
        """Löscht alle noch nicht bestätigten Transportanfragen (pending/ausstehend)"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM transport_requests WHERE status IN ('pending', 'ausstehend')")
                conn.commit()
                return True
            except Exception as e:
                # Log error but don't raise - return False instead
                import traceback
                print(f"Error deleting all pending transport requests: {e}")
                traceback.print_exc()
                return False
            finally:
                conn.close()
    
    def complete_inventory_transport(self, transport_id: int) -> bool:
        """Schließt Inventar-Transport ab"""
        return self.update_transport_status(transport_id, status='completed')
    
    def process_completed_inventory_transport(self, transport_id: int) -> bool:
        """
        Verarbeitet einen abgeschlossenen Inventar-Transport:
        - Findet die zugehörige Bestellung
        - Fügt Material zum Inventar hinzu
        - Löscht die Bestellung
        
        Args:
            transport_id: ID des abgeschlossenen Transportes
        
        Returns:
            bool: True wenn erfolgreich, False bei Fehler
        """
        # Zuerst Daten sammeln (mit Lock)
        order_id = None
        item_id = None
        quantity = None
        
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Hole Transport-Details
                cursor.execute("""
                    SELECT related_entity_type, related_entity_id 
                    FROM transport_requests 
                    WHERE id = ? AND related_entity_type = 'inventory_order'
                """, (transport_id,))
                transport_result = cursor.fetchone()
                
                if not transport_result:
                    # Kein Inventar-Transport oder bereits verarbeitet
                    return False
                
                order_id = transport_result[1]
                
                # Hole Bestellungs-Details
                cursor.execute("""
                    SELECT item_id, quantity 
                    FROM inventory_orders 
                    WHERE id = ?
                """, (order_id,))
                order_result = cursor.fetchone()
                
                if not order_result:
                    # Bestellung nicht gefunden (möglicherweise bereits gelöscht)
                    return False
                
                item_id = order_result[0]
                quantity = order_result[1]
            except Exception as e:
                import traceback
                print(f"Error fetching data for inventory transport {transport_id}: {e}")
                traceback.print_exc()
                return False
            finally:
                conn.close()
        
        # Jetzt außerhalb des Locks: Füge Material zum Inventar hinzu
        if not self.increase_inventory_stock(item_id, quantity):
            return False
        
        # Lösche die Bestellung (mit neuem Lock)
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM inventory_orders WHERE id = ?", (order_id,))
                conn.commit()
                return True
            except Exception as e:
                import traceback
                print(f"Error deleting inventory order {order_id}: {e}")
                traceback.print_exc()
                return False
            finally:
                conn.close()
    
    def create_patient_transport(self, from_location: str, to_location: str, priority: str, **kwargs) -> Dict:
        """Erstellt Patiententransport"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO transport_requests 
                    (timestamp, from_location, to_location, priority, status, request_type, estimated_time_minutes)
                    VALUES (?, ?, ?, ?, 'pending', 'patient', ?)
                """, (
                    datetime.now(timezone.utc).isoformat(),
                    from_location,
                    to_location,
                    priority,
                    kwargs.get('estimated_time_minutes', 15)
                ))
                conn.commit()
                return {'success': True, 'transport_id': cursor.lastrowid}
            finally:
                conn.close()
    
    def get_pending_transports(self) -> List[Dict]:
        """Gibt ausstehende Transporte zurück"""
        transports = self.get_transport_requests()
        return [t for t in transports if t['status'] in ['pending', 'ausstehend']]
    
    # ===== INVENTORY =====
    
    def get_inventory_status(self) -> List[Dict]:
        """Gibt Inventar-Status zurück"""
        # Ensure migration has run
        try:
            self._migrate_schema()
        except Exception as e:
            pass  # Continue anyway
        
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Check if columns exist before querying
                cursor.execute("PRAGMA table_info(inventory)")
                columns = [row[1] for row in cursor.fetchall()]
                
                # Check for all required columns
                has_last_updated = 'last_updated' in columns
                has_category = 'category' in columns
                
                # Build SELECT clause based on available columns
                select_parts = ['id', 'item_name', 'department', 'current_stock', 'min_threshold', 'max_capacity', 'unit']
                
                if has_last_updated:
                    select_parts.append('last_updated')
                else:
                    select_parts.append('NULL as last_updated')
                
                if has_category:
                    select_parts.append('category')
                else:
                    select_parts.append('NULL as category')
                
                select_clause = ', '.join(select_parts)
                
                query = f"""
                    SELECT {select_clause}
                    FROM inventory
                    ORDER BY department, item_name
                """
                
                cursor.execute(query)
                rows = cursor.fetchall()
                
                # Map results to dict based on column positions
                result = []
                for row in rows:
                    row_dict = {
                        'id': row[0],
                        'item_name': row[1],
                        'department': row[2],
                        'current_stock': row[3],
                        'min_threshold': row[4],
                        'max_capacity': row[5],
                        'unit': row[6],
                    }
                    
                    idx = 7
                    if has_last_updated:
                        row_dict['last_updated'] = row[idx]
                        idx += 1
                    else:
                        row_dict['last_updated'] = None
                    
                    if has_category:
                        row_dict['category'] = row[idx]
                    else:
                        row_dict['category'] = None
                    
                    result.append(row_dict)
                
                return result
            finally:
                conn.close()
    
    def update_inventory_consumption(self, item_id: int, consumption_amount: int, activity_factor: float = 1.0) -> bool:
        """
        Aktualisiert Inventory-Bestand nach Verbrauch und speichert Verbrauch in Historie.
        Thread-safe Methode die den DB-Lock verwendet.
        
        Args:
            item_id: ID des Inventory-Items
            consumption_amount: Verbrauchte Menge (wird vom current_stock abgezogen)
            activity_factor: Aktivitätsfaktor für Verbrauchshistorie (optional)
        
        Returns:
            bool: True wenn Update erfolgreich, False wenn Item nicht gefunden
        """
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Hole aktuellen Bestand
                cursor.execute("SELECT current_stock FROM inventory WHERE id = ?", (item_id,))
                result = cursor.fetchone()
                if not result:
                    return False
                
                current_stock = result[0]
                new_stock = max(0, int(current_stock - consumption_amount))
                
                # Update Bestand
                cursor.execute("""
                    UPDATE inventory 
                    SET current_stock = ?, last_updated = ?
                    WHERE id = ?
                """, (
                    new_stock,
                    datetime.now(timezone.utc).isoformat(),
                    item_id
                ))
                
                # Speichere Verbrauch in Historie
                cursor.execute("""
                    INSERT INTO inventory_consumption 
                    (item_id, timestamp, consumption_amount, activity_factor)
                    VALUES (?, ?, ?, ?)
                """, (
                    item_id,
                    datetime.now(timezone.utc).isoformat(),
                    consumption_amount,
                    activity_factor
                ))
                
                conn.commit()
                return True
            finally:
                conn.close()
    
    def increase_inventory_stock(self, item_id: int, amount: int) -> bool:
        """
        Erhöht den Inventory-Bestand (z.B. nach Lieferung).
        Thread-safe Methode die den DB-Lock verwendet.
        
        Args:
            item_id: ID des Inventory-Items
            amount: Menge die hinzugefügt wird (wird zum current_stock addiert)
        
        Returns:
            bool: True wenn Update erfolgreich, False wenn Item nicht gefunden
        """
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Hole aktuellen Bestand und max_capacity
                cursor.execute("SELECT current_stock, max_capacity FROM inventory WHERE id = ?", (item_id,))
                result = cursor.fetchone()
                if not result:
                    return False
                
                current_stock = result[0]
                max_capacity = result[1] if result[1] else float('inf')
                
                # Berechne neuen Bestand (nicht über max_capacity hinaus)
                new_stock = min(int(current_stock + amount), int(max_capacity))
                
                # Update Bestand
                cursor.execute("""
                    UPDATE inventory 
                    SET current_stock = ?, last_updated = ?
                    WHERE id = ?
                """, (
                    new_stock,
                    datetime.now(timezone.utc).isoformat(),
                    item_id
                ))
                
                conn.commit()
                return True
            finally:
                conn.close()
    
    def get_inventory_consumption(self, item_id: int, hours: int = 24) -> List[Dict]:
        """Gibt Inventar-Verbrauchsdaten zurück"""
        # Ensure migration has run
        try:
            self._migrate_schema()
        except Exception:
            pass  # Continue anyway - defensive query will handle missing columns
        
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Check if columns exist before querying
                cursor.execute("PRAGMA table_info(inventory_consumption)")
                columns = [row[1] for row in cursor.fetchall()]
                
                # Check for all required columns
                has_ed_load = 'ed_load' in columns
                has_beds_occupied = 'beds_occupied' in columns
                has_activity_factor = 'activity_factor' in columns
                
                # Build SELECT clause based on available columns
                select_parts = ['timestamp', 'consumption_amount']
                
                if has_ed_load:
                    select_parts.append('ed_load')
                else:
                    select_parts.append('NULL as ed_load')
                
                if has_beds_occupied:
                    select_parts.append('beds_occupied')
                else:
                    select_parts.append('NULL as beds_occupied')
                
                if has_activity_factor:
                    select_parts.append('activity_factor')
                else:
                    select_parts.append('NULL as activity_factor')
                
                select_clause = ', '.join(select_parts)
                
                query = f"""
                    SELECT {select_clause}
                    FROM inventory_consumption
                    WHERE item_id = ? AND timestamp >= ?
                    ORDER BY timestamp
                """
                
                try:
                    cursor.execute(query, (item_id, cutoff))
                    rows = cursor.fetchall()
                except Exception as query_error:
                    # If query failed, try a minimal query with only required columns
                    try:
                        minimal_query = """
                            SELECT timestamp, consumption_amount
                            FROM inventory_consumption
                            WHERE item_id = ? AND timestamp >= ?
                            ORDER BY timestamp
                        """
                        cursor.execute(minimal_query, (item_id, cutoff))
                        rows = cursor.fetchall()
                        # Return minimal results
                        return [{
                            'timestamp': row[0],
                            'consumption_amount': row[1],
                            'ed_load': None,
                            'beds_occupied': None,
                            'activity_factor': None
                        } for row in rows]
                    except Exception as fallback_error:
                        raise query_error  # Raise original error
                
                # Map results to dict based on column positions
                result = []
                for row in rows:
                    row_dict = {
                        'timestamp': row[0],
                        'consumption_amount': row[1],
                    }
                    
                    idx = 2
                    if has_ed_load:
                        row_dict['ed_load'] = row[idx]
                        idx += 1
                    else:
                        row_dict['ed_load'] = None
                    
                    if has_beds_occupied:
                        row_dict['beds_occupied'] = row[idx]
                        idx += 1
                    else:
                        row_dict['beds_occupied'] = None
                    
                    if has_activity_factor:
                        row_dict['activity_factor'] = row[idx]
                    else:
                        row_dict['activity_factor'] = None
                    
                    result.append(row_dict)
                
                return result
            finally:
                conn.close()
    
    def calculate_inventory_consumption_rate(self, item_id: int, sim_state: Dict) -> Dict:
        """Berechnet Verbrauchsrate für Inventar-Artikel"""
        # Algorithmus-basierte Berechnung
        consumption = self.get_inventory_consumption(item_id, hours=24)
        
        if consumption:
            total_consumption = sum(c['consumption_amount'] for c in consumption)
            daily_rate = total_consumption * (24 / len(consumption)) if consumption else 0
            hourly_rate = daily_rate / 24
            
            # Trend-Berechnung
            if len(consumption) > 1:
                recent = sum(c['consumption_amount'] for c in consumption[-6:])
                older = sum(c['consumption_amount'] for c in consumption[:-6]) if len(consumption) > 6 else recent
                trend = 'increasing' if recent > older else 'decreasing' if recent < older else 'stable'
            else:
                trend = 'stable'
        else:
            # Verbesserter Fallback: Verwende calculate_daily_consumption_from_activity
            # Hole Item-Daten aus der Datenbank
            item = None
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        SELECT id, item_name, department, current_stock, min_threshold, max_capacity, unit
                        FROM inventory
                        WHERE id = ?
                    """, (item_id,))
                    row = cursor.fetchone()
                    if row:
                        item = {
                            'id': row[0],
                            'item_name': row[1],
                            'department': row[2],
                            'current_stock': row[3],
                            'min_threshold': row[4],
                            'max_capacity': row[5],
                            'unit': row[6]
                        }
                finally:
                    conn.close()
            
            if item:
                # Verwende calculate_daily_consumption_from_activity für realistischere Berechnung
                from utils import calculate_daily_consumption_from_activity
                
                ed_load = sim_state.get('ed_load', 65.0)
                beds_occupied = sim_state.get('beds_occupied', 0)
                capacity_data = self.get_capacity_overview() if beds_occupied == 0 else None
                
                daily_rate = calculate_daily_consumption_from_activity(
                    item=item,
                    ed_load=ed_load,
                    beds_occupied=beds_occupied,
                    capacity_data=capacity_data
                )
                hourly_rate = daily_rate / 24
                trend = 'stable'
            else:
                # Fallback auf einfache Berechnung, wenn Item nicht gefunden
                ed_load = sim_state.get('ed_load', 65.0)
                beds_occupied = sim_state.get('beds_occupied', 100)
                activity_factor = (ed_load / 100) * (beds_occupied / 200)
                daily_rate = 10.0 * activity_factor
                hourly_rate = daily_rate / 24
                trend = 'stable'
        
        return {
            'daily_rate': daily_rate,
            'hourly_rate': hourly_rate,
            'trend': trend
        }
    
    def get_inventory_orders(self) -> List[Dict]:
        """Gibt aktive Inventar-Bestellungen zurück"""
        # Ensure migration has run
        try:
            self._migrate_schema()
        except Exception:
            pass  # Continue anyway - defensive query will handle missing columns
        
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Check if columns exist before querying
                cursor.execute("PRAGMA table_info(inventory_orders)")
                columns = [row[1] for row in cursor.fetchall()]
                
                # Check for all required columns
                has_order_date = 'order_date' in columns
                has_expected_delivery = 'expected_delivery' in columns
                has_transport_id = 'transport_id' in columns
                has_department = 'department' in columns
                
                # Build SELECT clause based on available columns
                select_parts = ['o.id', 'o.item_id', 'i.item_name', 'o.quantity', 'o.status']
                
                if has_order_date:
                    select_parts.append('o.order_date')
                else:
                    select_parts.append('NULL as order_date')
                
                if has_expected_delivery:
                    select_parts.append('o.expected_delivery')
                else:
                    select_parts.append('NULL as expected_delivery')
                
                if has_transport_id:
                    select_parts.append('o.transport_id')
                else:
                    select_parts.append('NULL as transport_id')
                
                if has_department:
                    select_parts.append('o.department')
                else:
                    select_parts.append('NULL as department')
                
                select_clause = ', '.join(select_parts)
                
                # Build ORDER BY clause - use order_date if available, otherwise use id
                order_by_clause = 'o.order_date DESC' if has_order_date else 'o.id DESC'
                
                query = f"""
                    SELECT {select_clause}
                    FROM inventory_orders o
                    JOIN inventory i ON o.item_id = i.id
                    WHERE o.status IN ('ordered', 'in_transit', 'pending')
                    ORDER BY {order_by_clause}
                """
                
                try:
                    cursor.execute(query)
                    rows = cursor.fetchall()
                except Exception as query_error:
                    # If query failed, try a minimal query with only required columns
                    try:
                        minimal_query = """
                            SELECT o.id, o.item_id, i.item_name, o.quantity, o.status
                            FROM inventory_orders o
                            JOIN inventory i ON o.item_id = i.id
                            WHERE o.status IN ('ordered', 'in_transit', 'pending')
                            ORDER BY o.id DESC
                        """
                        cursor.execute(minimal_query)
                        rows = cursor.fetchall()
                        # Return minimal results
                        return [{
                            'id': row[0],
                            'item_id': row[1],
                            'item_name': row[2],
                            'quantity': row[3],
                            'status': row[4],
                            'order_date': None,
                            'expected_delivery': None,
                            'transport_id': None,
                            'department': None
                        } for row in rows]
                    except Exception as fallback_error:
                        raise query_error  # Raise original error
                
                # Map results to dict based on column positions
                result = []
                for row in rows:
                    row_dict = {
                        'id': row[0],
                        'item_id': row[1],
                        'item_name': row[2],
                        'quantity': row[3],
                        'status': row[4],
                    }
                    
                    idx = 5
                    if has_order_date:
                        row_dict['order_date'] = row[idx]
                        idx += 1
                    else:
                        row_dict['order_date'] = None
                    
                    if has_expected_delivery:
                        row_dict['expected_delivery'] = row[idx]
                        idx += 1
                    else:
                        row_dict['expected_delivery'] = None
                    
                    if has_transport_id:
                        row_dict['transport_id'] = row[idx]
                        idx += 1
                    else:
                        row_dict['transport_id'] = None
                    
                    if has_department:
                        row_dict['department'] = row[idx]
                    else:
                        row_dict['department'] = None
                    
                    result.append(row_dict)
                
                return result
            finally:
                conn.close()
    
    def create_inventory_order(self, item_id: int, quantity: int, **kwargs) -> Dict:
        """Erstellt eine neue Inventar-Bestellung"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Hole item_name aus der inventory Tabelle
                cursor.execute("SELECT item_name FROM inventory WHERE id = ?", (item_id,))
                item_result = cursor.fetchone()
                if not item_result:
                    raise ValueError(f"Item mit ID {item_id} nicht gefunden")
                item_name = item_result[0]
                
                # Validiere dass item_name nicht None oder leer ist
                if not item_name or not item_name.strip():
                    raise ValueError(f"Item mit ID {item_id} hat keinen gültigen item_name")
                
                # Erstelle Transport
                planned_start_time = kwargs.get('planned_start_time')
                transport_status = 'planned' if planned_start_time else 'pending'
                
                # Konvertiere planned_start_time zu datetime falls vorhanden
                planned_start_time_dt = None
                planned_start_time_str = None
                if planned_start_time:
                    if isinstance(planned_start_time, datetime):
                        planned_start_time_dt = planned_start_time
                        planned_start_time_str = planned_start_time.isoformat()
                    elif isinstance(planned_start_time, str):
                        planned_start_time_str = planned_start_time
                        try:
                            planned_start_time_dt = datetime.fromisoformat(planned_start_time.replace('Z', '+00:00'))
                        except:
                            pass
                
                # Berechne expected_delivery basierend auf planned_start_time + estimated_time_minutes
                estimated_time_minutes = kwargs.get('estimated_time_minutes', 60)
                if planned_start_time_dt:
                    expected_delivery = planned_start_time_dt + timedelta(minutes=estimated_time_minutes)
                else:
                    # Fallback: 4 Stunden ab jetzt
                    expected_delivery = datetime.now(timezone.utc) + timedelta(hours=4)
                
                # Erstelle Bestellung mit korrekter expected_delivery
                cursor.execute("""
                    INSERT INTO inventory_orders 
                    (item_id, quantity, status, order_date, expected_delivery, department)
                    VALUES (?, ?, 'ordered', ?, ?, ?)
                """, (
                    item_id,
                    quantity,
                    datetime.now(timezone.utc).isoformat(),
                    expected_delivery.isoformat(),
                    kwargs.get('department')
                ))
                order_id = cursor.lastrowid
                
                # estimated_time_minutes für Transport (Standard: 60 Minuten)
                transport_estimated_time = kwargs.get('estimated_time_minutes', 60)
                
                if planned_start_time_str:
                    cursor.execute("""
                        INSERT INTO transport_requests 
                        (timestamp, from_location, to_location, priority, status, request_type, 
                         estimated_time_minutes, related_entity_type, related_entity_id, planned_start_time)
                        VALUES (?, 'Extern', 'Hauptlager', 'medium', ?, 'equipment', ?, 'inventory_order', ?, ?)
                    """, (datetime.now(timezone.utc).isoformat(), transport_status, transport_estimated_time, order_id, planned_start_time_str))
                else:
                    cursor.execute("""
                        INSERT INTO transport_requests 
                        (timestamp, from_location, to_location, priority, status, request_type, 
                         estimated_time_minutes, related_entity_type, related_entity_id)
                        VALUES (?, 'Extern', 'Hauptlager', 'medium', ?, 'equipment', ?, 'inventory_order', ?)
                    """, (datetime.now(timezone.utc).isoformat(), transport_status, transport_estimated_time, order_id))
                transport_id = cursor.lastrowid
                
                # Update Bestellung mit Transport-ID
                # Hinweis: FOREIGN KEY verweist auf transport(id), aber wir verwenden transport_requests
                # Versuche transport_id zu setzen, ignoriere FOREIGN KEY Fehler falls vorhanden
                try:
                    cursor.execute("UPDATE inventory_orders SET transport_id = ? WHERE id = ?", (transport_id, order_id))
                except sqlite3.IntegrityError as fk_error:
                    # FOREIGN KEY Fehler ignorieren - transport_id bleibt NULL
                    # Die Verknüpfung funktioniert trotzdem über related_entity_id in transport_requests
                    pass
                
                conn.commit()
                return {'success': True, 'order_id': order_id}
            finally:
                conn.close()
    
    def update_inventory_order_status(self, order_id: int, status: str) -> bool:
        """
        Aktualisiert den Status einer Inventar-Bestellung.
        
        Args:
            order_id: ID der Bestellung
            status: Neuer Status ('ordered', 'in_transit', 'delivered')
        
        Returns:
            bool: True wenn erfolgreich, False bei Fehler
        """
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    UPDATE inventory_orders 
                    SET status = ? 
                    WHERE id = ?
                """, (status, order_id))
                conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                import traceback
                print(f"Error updating inventory order status: {e}")
                traceback.print_exc()
                return False
            finally:
                conn.close()
    
    # ===== DEVICES =====
    
    def get_device_maintenance_urgencies(self) -> List[Dict]:
        """Gibt Geräte-Wartungsdringlichkeiten zurück"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Try to checkpoint WAL file before query to avoid I/O issues
                try:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except:
                    pass  # Ignore checkpoint errors
                now = datetime.now(timezone.utc)
                cursor.execute("""
                    SELECT id, device_id, device_name, device_type, department, usage_hours, max_usage_hours,
                           last_maintenance, next_maintenance_due, urgency_level, scheduled_maintenance_time, 
                           maintenance_confirmed, maintenance_duration_minutes
                    FROM devices
                    ORDER BY 
                        CASE urgency_level
                            WHEN 'high' THEN 1
                            WHEN 'hoch' THEN 1
                            WHEN 'medium' THEN 2
                            WHEN 'mittel' THEN 2
                            ELSE 3
                        END,
                        next_maintenance_due
                """)
                rows = cursor.fetchall()
                result = []
                for row in rows:
                    device_dict = {
                        'id': row[0],
                        'device_id': row[1],
                        'device_name': row[2],
                        'device_type': row[3],
                        'department': row[4],
                        'usage_hours': row[5],
                        'max_usage_hours': row[6],
                        'last_maintenance': row[7],
                        'next_maintenance_due': row[8],
                        'urgency_level': row[9],
                        'scheduled_maintenance_time': row[10],
                        'maintenance_confirmed': bool(row[11]),
                        'maintenance_duration_minutes': row[12]
                    }
                    
                    # Berechne is_in_maintenance und maintenance_end_time
                    scheduled_time_str = row[10]
                    duration_minutes = row[12]
                    is_in_maintenance = False
                    maintenance_end_time = None
                    
                    if scheduled_time_str and bool(row[11]):
                        try:
                            # Fallback: Wenn keine Dauer gespeichert ist, verwende Standarddauer basierend auf Gerätetyp
                            if duration_minutes is None:
                                try:
                                    from utils import get_maintenance_duration
                                    device_type = row[3]  # device_type ist das 4. Element (Index 3)
                                    duration_minutes = get_maintenance_duration(device_type)
                                except:
                                    duration_minutes = 60  # Default: 1 Stunde
                            
                            # Parse scheduled_maintenance_time
                            # WICHTIG: Naive Zeiten (ohne Zeitzone) werden als lokale Zeit interpretiert
                            if isinstance(scheduled_time_str, str):
                                scheduled_time = None
                                date_formats = [
                                    '%Y-%m-%d %H:%M:%S.%f',
                                    '%Y-%m-%d %H:%M:%S',
                                    '%Y-%m-%dT%H:%M:%S.%f',
                                    '%Y-%m-%dT%H:%M:%S',
                                    '%Y-%m-%d %H:%M',
                                    '%Y-%m-%dT%H:%M'
                                ]
                                for fmt in date_formats:
                                    try:
                                        scheduled_time = datetime.strptime(scheduled_time_str, fmt)
                                        # Wenn naive Zeit, interpretiere als lokale Zeit und konvertiere zu UTC
                                        if scheduled_time.tzinfo is None:
                                            local_tz = datetime.now().astimezone().tzinfo
                                            scheduled_time = scheduled_time.replace(tzinfo=local_tz).astimezone(timezone.utc)
                                        break
                                    except:
                                        continue
                                
                                if scheduled_time is None:
                                    try:
                                        scheduled_time = datetime.fromisoformat(scheduled_time_str.replace('Z', '+00:00'))
                                        # Wenn immer noch naive Zeit, interpretiere als lokale Zeit
                                        if scheduled_time.tzinfo is None:
                                            local_tz = datetime.now().astimezone().tzinfo
                                            scheduled_time = scheduled_time.replace(tzinfo=local_tz).astimezone(timezone.utc)
                                    except:
                                        scheduled_time = None
                            else:
                                scheduled_time = scheduled_time_str
                                if scheduled_time and scheduled_time.tzinfo is None:
                                    # Naive Zeit als lokale Zeit interpretieren
                                    local_tz = datetime.now().astimezone().tzinfo
                                    scheduled_time = scheduled_time.replace(tzinfo=local_tz).astimezone(timezone.utc)
                            
                            if scheduled_time:
                                maintenance_end_time = scheduled_time + timedelta(minutes=duration_minutes)
                                is_in_maintenance = scheduled_time <= now < maintenance_end_time
                        except Exception:
                            pass
                    
                    device_dict['is_in_maintenance'] = is_in_maintenance
                    device_dict['maintenance_end_time'] = maintenance_end_time.isoformat() if maintenance_end_time else None
                    
                    result.append(device_dict)
                
                return result
            except Exception as e:
                raise
            finally:
                conn.close()
    
    def suggest_optimal_maintenance_times(self, device_id: str, max_suggestions: int = 5) -> List[Dict]:
        """Schlägt optimale Wartungszeiten vor"""
        # Verwende Optimization Engine wenn verfügbar
        try:
            from optimization import OptimizationEngine
            opt_engine = OptimizationEngine(self)
            devices = self.get_device_maintenance_urgencies()
            device = next((d for d in devices if d['device_id'] == device_id), None)
            if device:
                # Hole Standard-Wartungsdauer
                from utils import get_maintenance_duration
                duration = get_maintenance_duration(device.get('device_type', ''))
                return opt_engine.optimize_maintenance_times(device_id, duration, max_suggestions)
        except:
            pass
        
        # Fallback: Algorithmus-basierte Vorschläge
        suggestions = []
        now = datetime.now(timezone.utc)
        
        # Hole Gerät-Info
        devices = self.get_device_maintenance_urgencies()
        device = next((d for d in devices if d['device_id'] == device_id), None)
        if not device:
            return []
        
        # Hole Kapazitätsdaten für optimale Zeiten
        capacity = self.get_capacity_overview()
        dept_capacity = next((c for c in capacity if c['department'] == device['department']), None)
        
        for i in range(max_suggestions):
            # Vorschläge für nächste 1-5 Tage
            days_ahead = i + 1
            start_time = now + timedelta(days=days_ahead, hours=random.randint(2, 6))
            end_time = start_time + timedelta(hours=2)
            
            # Score basierend auf erwarteter Auslastung
            hour = start_time.hour
            if 8 <= hour <= 12 or 14 <= hour <= 18:
                expected_patients = random.uniform(3, 8)  # Höhere Auslastung
                score = random.uniform(0.5, 0.7)
            else:
                expected_patients = random.uniform(0, 3)  # Niedrigere Auslastung
                score = random.uniform(0.7, 0.95)
            
            # Bessere Scores wenn Abteilung niedrige Auslastung hat
            if dept_capacity and dept_capacity.get('utilization_percent', 100) < 70:
                score = min(0.95, score + 0.1)
            
            suggestions.append({
                'start_time': start_time,
                'end_time': end_time,
                'score': score,
                'expected_patients': expected_patients,
                'reason': 'Niedrige erwartete Patientenlast' if score > 0.7 else 'Moderate Auslastung',
                'duration_minutes': 120
            })
        
        return sorted(suggestions, key=lambda x: x['score'], reverse=True)
    
    def confirm_maintenance(self, device_id: str, scheduled_time: datetime, duration_minutes: int, confirmed_by: str = "System") -> Tuple[bool, Optional[str]]:
        """Bestätigt eine Wartung"""
        max_retries = 3
        retry_delay = 0.1  # 100ms
        for attempt in range(max_retries):
            conn = None
            try:
                with self.lock:
                    conn = self.get_connection()
                    cursor = conn.cursor()
                    # Try to checkpoint WAL file before update to avoid I/O issues
                    try:
                        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    except:
                        pass  # Ignore checkpoint errors
                    
                    cursor.execute("""
                        UPDATE devices
                        SET scheduled_maintenance_time = ?,
                            maintenance_confirmed = 1,
                            maintenance_duration_minutes = ?
                        WHERE device_id = ?
                    """, (scheduled_time.isoformat(), duration_minutes, device_id))
                    conn.commit()
                    
                    if cursor.rowcount == 0:
                        return False, f"Gerät {device_id} nicht gefunden"
                    
                    return True, None
            except sqlite3.OperationalError as e:
                error_str = str(e).lower()
                # Handle database locked errors
                if "database is locked" in error_str and attempt < max_retries - 1:
                    if conn:
                        try:
                            conn.close()
                        except:
                            pass
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    continue
                # Handle disk I/O errors with checkpoint retry
                elif ("disk i/o error" in error_str or "i/o error" in error_str) and attempt < max_retries - 1:
                    if conn:
                        try:
                            # Try to checkpoint WAL file to recover from I/O error
                            try:
                                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                            except:
                                pass
                            conn.close()
                        except:
                            pass
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    if conn:
                        try:
                            conn.close()
                        except:
                            pass
                    return False, str(e)
            except Exception as e:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
                if attempt == max_retries - 1:
                    return False, str(e)
                time.sleep(retry_delay * (attempt + 1))
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
        return False, "Max retries exceeded"
    
    def complete_maintenance(self, device_id: str) -> bool:
        """Schließt eine Wartung ab"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Hole Gerät
                cursor.execute("SELECT usage_hours, max_usage_hours FROM devices WHERE device_id = ?", (device_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                
                usage_hours, max_usage_hours = row
                
                # Update Wartungsdaten
                now = datetime.now(timezone.utc)
                next_maintenance = now + timedelta(days=90)  # Standard: 90 Tage
                
                cursor.execute("""
                    UPDATE devices
                    SET last_maintenance = ?,
                        next_maintenance_due = ?,
                        scheduled_maintenance_time = NULL,
                        maintenance_confirmed = 0,
                        maintenance_duration_minutes = NULL,
                        usage_hours = 0
                    WHERE device_id = ?
                """, (now.isoformat(), next_maintenance.isoformat(), device_id))
                conn.commit()
                
                return cursor.rowcount > 0
            finally:
                conn.close()
    
    def check_and_process_maintenance_windows(self) -> List[str]:
        """
        Prüft alle Geräte mit bestätigten Wartungen und verarbeitet die Wartungsfenster.
        - Wenn aktuelle Zeit >= Startzeit UND < Endzeit: Gerät ist in Wartung
        - Wenn aktuelle Zeit >= Endzeit: Wartung wird automatisch abgeschlossen
        
        Returns:
            List[str]: Liste von device_ids, bei denen Statusänderungen vorgenommen wurden
        """
        changed_devices = []
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                now = datetime.now(timezone.utc)
                
                # Hole alle Geräte mit bestätigten Wartungen
                cursor.execute("""
                    SELECT device_id, scheduled_maintenance_time, maintenance_duration_minutes, device_type
                    FROM devices
                    WHERE maintenance_confirmed = 1
                    AND scheduled_maintenance_time IS NOT NULL
                """)
                rows = cursor.fetchall()
                
                for row in rows:
                    device_id, scheduled_time_str, duration_minutes, device_type = row
                    
                    # Fallback: Wenn keine Dauer gespeichert ist, verwende Standarddauer
                    if duration_minutes is None:
                        try:
                            from utils import get_maintenance_duration
                            duration_minutes = get_maintenance_duration(device_type)
                        except:
                            duration_minutes = 60  # Default: 1 Stunde
                    
                    try:
                        # Parse scheduled_maintenance_time
                        # WICHTIG: Naive Zeiten (ohne Zeitzone) werden als lokale Zeit interpretiert
                        if isinstance(scheduled_time_str, str):
                            # Versuche verschiedene Formate
                            scheduled_time = None
                            date_formats = [
                                '%Y-%m-%d %H:%M:%S.%f',
                                '%Y-%m-%d %H:%M:%S',
                                '%Y-%m-%dT%H:%M:%S.%f',
                                '%Y-%m-%dT%H:%M:%S',
                                '%Y-%m-%d %H:%M',
                                '%Y-%m-%dT%H:%M'
                            ]
                            for fmt in date_formats:
                                try:
                                    scheduled_time = datetime.strptime(scheduled_time_str, fmt)
                                    # Wenn naive Zeit, interpretiere als lokale Zeit und konvertiere zu UTC
                                    if scheduled_time.tzinfo is None:
                                        local_tz = datetime.now().astimezone().tzinfo
                                        scheduled_time = scheduled_time.replace(tzinfo=local_tz).astimezone(timezone.utc)
                                    break
                                except:
                                    continue
                            
                            if scheduled_time is None:
                                # Versuche ISO-Format mit fromisoformat
                                try:
                                    scheduled_time = datetime.fromisoformat(scheduled_time_str.replace('Z', '+00:00'))
                                    # Wenn immer noch naive Zeit, interpretiere als lokale Zeit
                                    if scheduled_time.tzinfo is None:
                                        local_tz = datetime.now().astimezone().tzinfo
                                        scheduled_time = scheduled_time.replace(tzinfo=local_tz).astimezone(timezone.utc)
                                except:
                                    continue
                        else:
                            scheduled_time = scheduled_time_str
                            if scheduled_time.tzinfo is None:
                                # Naive Zeit als lokale Zeit interpretieren
                                local_tz = datetime.now().astimezone().tzinfo
                                scheduled_time = scheduled_time.replace(tzinfo=local_tz).astimezone(timezone.utc)
                        
                        if scheduled_time is None:
                            continue
                        
                        # Berechne Endzeitpunkt
                        end_time = scheduled_time + timedelta(minutes=duration_minutes)
                        
                        # Prüfe ob Wartung abgeschlossen werden sollte
                        if now >= end_time:
                            # Wartung automatisch abschließen
                            if self.complete_maintenance(device_id):
                                changed_devices.append(device_id)
                        # Wenn now >= scheduled_time aber < end_time, ist das Gerät in Wartung
                        # (Status wird in get_device_maintenance_urgencies() berechnet)
                        
                    except Exception as e:
                        # Fehler beim Parsen ignorieren, weiter mit nächstem Gerät
                        continue
                
                return changed_devices
            finally:
                conn.close()
    
    def is_device_in_maintenance(self, device_id: str) -> bool:
        """
        Prüft ob ein Gerät aktuell in einem Wartungsfenster ist.
        
        Args:
            device_id: ID des Geräts
            
        Returns:
            bool: True wenn Gerät aktuell in Wartung ist, False sonst
        """
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                now = datetime.now(timezone.utc)
                
                cursor.execute("""
                    SELECT scheduled_maintenance_time, maintenance_duration_minutes, device_type
                    FROM devices
                    WHERE device_id = ?
                    AND maintenance_confirmed = 1
                    AND scheduled_maintenance_time IS NOT NULL
                """, (device_id,))
                row = cursor.fetchone()
                
                if not row:
                    return False
                
                scheduled_time_str, duration_minutes, device_type = row
                
                # Fallback: Wenn keine Dauer gespeichert ist, verwende Standarddauer
                if duration_minutes is None:
                    try:
                        from utils import get_maintenance_duration
                        duration_minutes = get_maintenance_duration(device_type)
                    except:
                        duration_minutes = 60  # Default: 1 Stunde
                
                try:
                    # Parse scheduled_maintenance_time
                    # WICHTIG: Naive Zeiten (ohne Zeitzone) werden als lokale Zeit interpretiert
                    if isinstance(scheduled_time_str, str):
                        scheduled_time = None
                        date_formats = [
                            '%Y-%m-%d %H:%M:%S.%f',
                            '%Y-%m-%d %H:%M:%S',
                            '%Y-%m-%dT%H:%M:%S.%f',
                            '%Y-%m-%dT%H:%M:%S',
                            '%Y-%m-%d %H:%M',
                            '%Y-%m-%dT%H:%M'
                        ]
                        for fmt in date_formats:
                            try:
                                scheduled_time = datetime.strptime(scheduled_time_str, fmt)
                                # Wenn naive Zeit, interpretiere als lokale Zeit und konvertiere zu UTC
                                if scheduled_time.tzinfo is None:
                                    local_tz = datetime.now().astimezone().tzinfo
                                    scheduled_time = scheduled_time.replace(tzinfo=local_tz).astimezone(timezone.utc)
                                break
                            except:
                                continue
                        
                        if scheduled_time is None:
                            try:
                                scheduled_time = datetime.fromisoformat(scheduled_time_str.replace('Z', '+00:00'))
                                # Wenn immer noch naive Zeit, interpretiere als lokale Zeit
                                if scheduled_time.tzinfo is None:
                                    local_tz = datetime.now().astimezone().tzinfo
                                    scheduled_time = scheduled_time.replace(tzinfo=local_tz).astimezone(timezone.utc)
                            except:
                                return False
                    else:
                        scheduled_time = scheduled_time_str
                        if scheduled_time.tzinfo is None:
                            # Naive Zeit als lokale Zeit interpretieren
                            local_tz = datetime.now().astimezone().tzinfo
                            scheduled_time = scheduled_time.replace(tzinfo=local_tz).astimezone(timezone.utc)
                    
                    if scheduled_time is None:
                        return False
                    
                    # Berechne Endzeitpunkt
                    end_time = scheduled_time + timedelta(minutes=duration_minutes)
                    
                    # Prüfe ob aktuell innerhalb des Wartungsfensters
                    return scheduled_time <= now < end_time
                    
                except Exception:
                    return False
            finally:
                conn.close()
    
    # ===== OPERATIONS =====
    
    def get_recent_operations(self, hours: int = 24, status: Optional[str] = None) -> List[Dict]:
        """Gibt kürzliche Operationen zurück"""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                if status:
                    cursor.execute("""
                        SELECT id, operation_type, department, status, duration_minutes,
                               planned_start_time, start_time, end_time, timestamp
                        FROM operations
                        WHERE timestamp >= ? AND status = ?
                        ORDER BY timestamp DESC
                    """, (cutoff, status))
                else:
                    cursor.execute("""
                        SELECT id, operation_type, department, status, duration_minutes,
                               planned_start_time, start_time, end_time, timestamp
                        FROM operations
                        WHERE timestamp >= ?
                        ORDER BY timestamp DESC
                    """, (cutoff,))
                rows = cursor.fetchall()
                return [{
                    'id': row[0],
                    'operation_type': row[1],
                    'department': row[2],
                    'status': row[3],
                    'duration_minutes': row[4],
                    'planned_start_time': row[5],
                    'start_time': row[6],
                    'end_time': row[7],
                    'timestamp': row[8]
                } for row in rows]
            finally:
                conn.close()
    
    def get_operations_consumption(self, hours: int = 24) -> Dict[str, int]:
        """Gibt Operations-Verbrauch pro Abteilung zurück"""
        operations = self.get_recent_operations(hours=hours)
        consumption = {}
        for op in operations:
            dept = op['department']
            consumption[dept] = consumption.get(dept, 0) + 1
        return consumption
    
    # ===== DISCHARGE PLANNING =====
    
    def get_discharge_planning(self) -> List[Dict]:
        """Gibt Entlassungsplanungsdaten zurück"""
        # Ensure migration has run
        try:
            self._migrate_schema()
        except Exception:
            pass  # Continue anyway - defensive query will handle missing columns
        
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Check if table exists first
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='discharge_planning'")
                table_exists = cursor.fetchone()
                
                if not table_exists:
                    return []
                
                # Check if columns exist before querying
                cursor.execute("PRAGMA table_info(discharge_planning)")
                columns = [row[1] for row in cursor.fetchall()]
                
                # Check for all required columns
                has_total_patients = 'total_patients' in columns
                has_avg_length_of_stay_hours = 'avg_length_of_stay_hours' in columns
                has_discharge_capacity_utilization = 'discharge_capacity_utilization' in columns
                
                # Build SELECT clause based on available columns
                select_parts = ['department', 'ready_for_discharge_count', 'pending_discharge_count']
                
                if has_total_patients:
                    select_parts.append('total_patients')
                else:
                    select_parts.append('NULL as total_patients')
                
                if has_avg_length_of_stay_hours:
                    select_parts.append('avg_length_of_stay_hours')
                else:
                    select_parts.append('NULL as avg_length_of_stay_hours')
                
                if has_discharge_capacity_utilization:
                    select_parts.append('discharge_capacity_utilization')
                else:
                    select_parts.append('NULL as discharge_capacity_utilization')
                
                select_clause = ', '.join(select_parts)
                
                query = f"""
                    SELECT {select_clause}
                    FROM discharge_planning
                    WHERE id IN (
                        SELECT MAX(id) FROM discharge_planning GROUP BY department
                    )
                    ORDER BY department
                """
                
                try:
                    cursor.execute(query)
                    rows = cursor.fetchall()
                except Exception as query_error:
                    # If query failed, try a minimal query with only required columns
                    try:
                        minimal_query = """
                            SELECT department, ready_for_discharge_count, pending_discharge_count
                            FROM discharge_planning
                            WHERE id IN (
                                SELECT MAX(id) FROM discharge_planning GROUP BY department
                            )
                            ORDER BY department
                        """
                        cursor.execute(minimal_query)
                        rows = cursor.fetchall()
                        # Return minimal results
                        return [{
                            'department': row[0],
                            'ready_for_discharge_count': row[1],
                            'pending_discharge_count': row[2],
                            'total_patients': None,
                            'avg_length_of_stay_hours': None,
                            'discharge_capacity_utilization': None
                        } for row in rows]
                    except Exception as fallback_error:
                        raise query_error  # Raise original error
                
                # Map results to dict based on column positions
                result = []
                for row in rows:
                    row_dict = {
                        'department': row[0],
                        'ready_for_discharge_count': row[1],
                        'pending_discharge_count': row[2],
                    }
                    
                    idx = 3
                    if has_total_patients:
                        row_dict['total_patients'] = row[idx]
                        idx += 1
                    else:
                        row_dict['total_patients'] = None
                    
                    if has_avg_length_of_stay_hours:
                        row_dict['avg_length_of_stay_hours'] = row[idx]
                        idx += 1
                    else:
                        row_dict['avg_length_of_stay_hours'] = None
                    
                    if has_discharge_capacity_utilization:
                        row_dict['discharge_capacity_utilization'] = row[idx]
                    else:
                        row_dict['discharge_capacity_utilization'] = None
                    
                    result.append(row_dict)
                
                return result
            finally:
                conn.close()
    
    # ===== STAFF =====
    
    def get_all_staff(self) -> Dict[str, List[Dict]]:
        """Gibt alle Mitarbeiter nach Kategorie zurück"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT id, name, role, department, category, contact
                    FROM staff
                    ORDER BY category, department, name
                """)
                rows = cursor.fetchall()
                
                staff_dict = {}
                for row in rows:
                    category = row[4]
                    if category not in staff_dict:
                        staff_dict[category] = []
                    staff_dict[category].append({
                        'id': row[0],
                        'name': row[1],
                        'role': row[2],
                        'department': row[3],
                        'category': row[4],
                        'contact': row[5]
                    })
                return staff_dict
            finally:
                conn.close()
    
    def _generate_realistic_schedule(self, staff_id: int, week_start: str):
        """Generiert einen realistischen Dienstplan für einen Mitarbeiter"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Hole Mitarbeiter-Info
                cursor.execute("""
                    SELECT category, department, role FROM staff WHERE id = ?
                """, (staff_id,))
                staff_row = cursor.fetchone()
                if not staff_row:
                    return
                
                category = staff_row[0]
                department = staff_row[1]
                role = staff_row[2]
                
                # Parse week_start
                week_start_date = datetime.strptime(week_start, '%Y-%m-%d').date()
                
                # Tagesnamen
                day_names = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
                
                # Bestimme Schichtmuster basierend auf Kategorie
                if category == 'Pflegekräfte':
                    # Meist Früh- oder Spätschicht, selten Nachtschicht
                    shift_patterns = [
                        ('07:00', '15:00', 8.0),  # Frühschicht
                        ('14:00', '22:00', 8.0),  # Spätschicht
                        ('22:00', '06:00', 8.0),  # Nachtschicht (selten)
                    ]
                    # 70% Früh, 25% Spät, 5% Nacht
                    shift_weights = [0.70, 0.25, 0.05]
                    work_days_per_week = random.choice([4, 5])  # 4-5 Arbeitstage
                elif category == 'Ärzte':
                    # Längere Schichten, unregelmäßiger
                    shift_patterns = [
                        ('07:00', '19:00', 12.0),  # Langschicht
                        ('08:00', '16:00', 8.0),   # Standardschicht
                        ('14:00', '22:00', 8.0),   # Spätschicht
                    ]
                    shift_weights = [0.40, 0.40, 0.20]
                    work_days_per_week = random.choice([4, 5, 6])  # 4-6 Arbeitstage
                else:  # Logistik, Orga
                    # Standard 8h Schichten
                    shift_patterns = [
                        ('07:00', '15:00', 8.0),
                        ('09:00', '17:00', 8.0),
                    ]
                    shift_weights = [0.60, 0.40]
                    work_days_per_week = 5  # Standard 5 Tage
                
                # Urlaub-Logik: 10-15% der Tage, mehr im Sommer
                month = week_start_date.month
                is_summer = 6 <= month <= 8  # Juni-August
                vacation_week_probability = 0.20 if is_summer else 0.15  # 15-20% Chance für Urlaub in dieser Woche
                
                # Generiere Urlaub-Tage (in Blöcken von 2-5 Tagen)
                vacation_days = set()
                if random.random() < vacation_week_probability:
                    vacation_start = random.randint(0, 5)  # Nicht am Sonntag beginnen
                    vacation_length = random.randint(2, min(5, 7 - vacation_start))
                    for i in range(vacation_length):
                        if vacation_start + i < 7:
                            vacation_days.add(vacation_start + i)
                
                # Generiere Dienstplan für die Woche
                work_days = []
                for i in range(7):
                    if i in vacation_days:
                        continue
                    
                    # Wochenende: weniger Arbeit
                    if i >= 5:  # Samstag, Sonntag
                        if random.random() < 0.3:  # 30% Chance am Wochenende zu arbeiten
                            work_days.append(i)
                    else:  # Wochentag
                        if len(work_days) < work_days_per_week:
                            work_days.append(i)
                
                # Füge Schichten hinzu
                for day_idx in work_days:
                    # Wähle Schicht basierend auf Gewichtung
                    shift_idx = random.choices(range(len(shift_patterns)), weights=shift_weights)[0]
                    shift_start, shift_end, hours = shift_patterns[shift_idx]
                    
                    day_name = day_names[day_idx]
                    
                    cursor.execute("""
                        INSERT INTO staff_schedule (staff_id, week_start, day, start_time, end_time, hours, is_vacation)
                        VALUES (?, ?, ?, ?, ?, ?, 0)
                    """, (staff_id, week_start, day_name, shift_start, shift_end, hours))
                
                # Füge Urlaub-Tage hinzu
                for day_idx in vacation_days:
                    day_name = day_names[day_idx]
                    cursor.execute("""
                        INSERT INTO staff_schedule (staff_id, week_start, day, start_time, end_time, hours, is_vacation)
                        VALUES (?, ?, ?, ?, ?, ?, 1)
                    """, (staff_id, week_start, day_name, '00:00', '00:00', 0.0))
                
                conn.commit()
            finally:
                conn.close()
    
    def get_staff_schedule(self, staff_id: int, week_start: str) -> List[Dict]:
        """Gibt Dienstplan für einen Mitarbeiter zurück"""
        with self.lock:
            # Stelle sicher, dass Migration ausgeführt wurde
            try:
                self._migrate_schema()
            except Exception:
                pass  # Continue anyway
            
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Prüfe ob Daten vorhanden sind, sonst generiere sie
                cursor.execute("""
                    SELECT COUNT(*) FROM staff_schedule
                    WHERE staff_id = ? AND week_start = ?
                """, (staff_id, week_start))
                count = cursor.fetchone()[0]
                
                if count == 0:
                    # Generiere realistischen Dienstplan
                    self._generate_realistic_schedule(staff_id, week_start)
                
                # Hole Mitarbeiter-Info für Urlaub-Logik
                cursor.execute("""
                    SELECT category, department FROM staff WHERE id = ?
                """, (staff_id,))
                staff_info = cursor.fetchone()
                category = staff_info[0] if staff_info else None
                department = staff_info[1] if staff_info else None
                
                # Mapping von Tagesnamen zu Wochentagen
                day_name_to_num = {
                    'Montag': 0, 'Dienstag': 1, 'Mittwoch': 2, 'Donnerstag': 3,
                    'Freitag': 4, 'Samstag': 5, 'Sonntag': 6
                }
                
                cursor.execute("""
                    SELECT day, start_time, end_time, hours, is_vacation
                    FROM staff_schedule
                    WHERE staff_id = ? AND week_start = ?
                    ORDER BY 
                        CASE day
                            WHEN 'Montag' THEN 1
                            WHEN 'Dienstag' THEN 2
                            WHEN 'Mittwoch' THEN 3
                            WHEN 'Donnerstag' THEN 4
                            WHEN 'Freitag' THEN 5
                            WHEN 'Samstag' THEN 6
                            WHEN 'Sonntag' THEN 7
                            ELSE 8
                        END
                """, (staff_id, week_start))
                rows = cursor.fetchall()
                
                # Parse week_start to date
                week_start_date = datetime.strptime(week_start, '%Y-%m-%d').date()
                
                result = []
                for row in rows:
                    day_name = row[0]
                    day_num = day_name_to_num.get(day_name, 0)
                    entry_date = week_start_date + timedelta(days=day_num)
                    
                    result.append({
                        'date': entry_date.strftime('%Y-%m-%d'),
                        'day_of_week': day_num,
                        'planned_hours': float(row[3]) if row[4] != 1 else 0.0,
                        'shift_start': row[1],
                        'shift_end': row[2],
                        'is_vacation': bool(row[4]) if len(row) > 4 else False
                    })
                
                return result
            finally:
                conn.close()
    
    def _get_active_events(self) -> List[Dict]:
        """Gibt aktive Events zurück"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                now = datetime.now(timezone.utc)
                cursor.execute("""
                    SELECT event_type, start_time, duration_minutes, intensity, affected_departments, description
                    FROM simulation_events
                    WHERE start_time <= ? AND datetime(start_time, '+' || duration_minutes || ' minutes') >= ?
                    ORDER BY start_time DESC
                """, (now.isoformat(), now.isoformat()))
                rows = cursor.fetchall()
                
                events = []
                for row in rows:
                    try:
                        start_time_str = row[1]
                        duration = row[2]
                        
                        # Parse start_time - handle different formats
                        if 'Z' in start_time_str:
                            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                        elif '+' in start_time_str or start_time_str.endswith('UTC'):
                            start_time = datetime.fromisoformat(start_time_str.replace('UTC', '+00:00'))
                        else:
                            # Try parsing without timezone
                            start_time = datetime.fromisoformat(start_time_str)
                            if start_time.tzinfo is None:
                                start_time = start_time.replace(tzinfo=timezone.utc)
                        
                        end_time = start_time + timedelta(minutes=duration)
                        
                        # Prüfe ob Event noch aktiv
                        if now >= start_time and now <= end_time:
                            affected_depts = row[4].split(',') if row[4] else []
                            events.append({
                                'type': row[0],
                                'intensity': float(row[3]) if row[3] else 1.0,
                                'affected_departments': [d.strip() for d in affected_depts if d.strip()],
                                'description': row[5] if row[5] else ''
                            })
                    except (ValueError, TypeError) as e:
                        # Skip invalid entries
                        continue
                
                return events
            finally:
                conn.close()
    
    def get_actual_hours(self, staff_id: int, week_start: str) -> List[Dict]:
        """Gibt tatsächliche Arbeitsstunden zurück mit Event-basierten Überstunden"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Hole Mitarbeiter-Abteilung
                cursor.execute("SELECT department FROM staff WHERE id = ?", (staff_id,))
                staff_row = cursor.fetchone()
                department = staff_row[0] if staff_row else None
                
                # Hole geplanten Dienstplan
                schedule = self.get_staff_schedule(staff_id, week_start)
                
                # Hole aktive Events
                active_events = self._get_active_events()
                
                # Bestimme Überstunden-Faktor basierend auf Events
                overtime_factor = 0.0
                for event in active_events:
                    event_type = event['type']
                    affected_depts = event.get('affected_departments', [])
                    
                    # Prüfe ob Mitarbeiter-Abteilung betroffen ist
                    is_affected = department and department in affected_depts
                    
                    if event_type in ['surge', 'manv']:
                        if is_affected:
                            overtime_factor += random.uniform(2.0, 3.0)  # +2-3h für betroffene Abteilungen
                        else:
                            overtime_factor += random.uniform(0.5, 1.5)  # +0.5-1.5h für andere
                    elif event_type == 'staffing_shortage':
                        if is_affected:
                            overtime_factor += random.uniform(1.0, 2.0)  # +1-2h
                        else:
                            overtime_factor += random.uniform(0.3, 1.0)  # +0.3-1h
                    elif event_type == 'equipment_failure':
                        if is_affected:
                            overtime_factor += random.uniform(0.5, 1.0)  # +0.5-1h
                
                # Generiere tatsächliche Stunden
                result = []
                for entry in schedule:
                    if entry.get('is_vacation', False):
                        # Urlaub: 0h tatsächlich
                        result.append({
                            'date': entry['date'],
                            'actual_hours': 0.0
                        })
                    else:
                        # Normale Variation: ±0.5h
                        base_hours = entry.get('planned_hours', 0.0)
                        variation = random.uniform(-0.5, 0.5)
                        
                        # Füge Event-Überstunden hinzu (nur wenn geplant war)
                        if base_hours > 0:
                            actual_hours = base_hours + variation + overtime_factor
                            actual_hours = max(0.0, actual_hours)  # Nicht negativ
                        else:
                            actual_hours = 0.0
                        
                        result.append({
                            'date': entry['date'],
                            'actual_hours': round(actual_hours, 1)
                        })
                
                return result
            finally:
                conn.close()
    
    def calculate_overtime(self, staff_id: int, week_start: str) -> Dict:
        """Berechnet Überstunden"""
        schedule = self.get_staff_schedule(staff_id, week_start)
        actual = self.get_actual_hours(staff_id, week_start)
        
        planned_hours = sum(s.get('planned_hours', 0.0) for s in schedule)
        actual_hours = sum(a.get('actual_hours', 0.0) for a in actual)
        
        # Berechne Überstunden (tatsächlich - geplant)
        overtime = actual_hours - planned_hours
        
        return {
            'contract_hours': 40.0,
            'planned_hours': round(planned_hours, 1),
            'actual_hours': round(actual_hours, 1),
            'overtime': round(overtime, 1)
        }
    
    # ===== PREDICTIONS =====
    
    def get_predictions(self, time_horizon_minutes: int = 15) -> List[Dict]:
        """Gibt Vorhersagen zurück"""
        # Ensure migration has run
        try:
            self._migrate_schema()
        except Exception:
            pass  # Continue anyway
        
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Check if columns exist before querying
                cursor.execute("PRAGMA table_info(predictions)")
                columns = [row[1] for row in cursor.fetchall()]
                
                # Check for all required columns
                has_model_version = 'model_version' in columns
                has_features_json = 'features_json' in columns
                
                # Build SELECT clause based on available columns
                select_parts = ['id', 'timestamp', 'prediction_type', 'predicted_value', 'confidence', 'time_horizon_minutes']
                
                if 'department' in columns:
                    select_parts.append('department')
                else:
                    select_parts.append('NULL as department')
                
                if has_model_version:
                    select_parts.append('model_version')
                else:
                    select_parts.append('NULL as model_version')
                
                if has_features_json:
                    select_parts.append('features_json')
                else:
                    select_parts.append('NULL as features_json')
                
                select_clause = ', '.join(select_parts)
                
                query = f"""
                    SELECT {select_clause}
                    FROM predictions
                    WHERE timestamp >= ? AND time_horizon_minutes <= ?
                    ORDER BY time_horizon_minutes, timestamp DESC
                """
                
                cursor.execute(query, (cutoff, time_horizon_minutes))
                rows = cursor.fetchall()
                
                # Map results to dict based on column positions
                result = []
                for row in rows:
                    row_dict = {
                        'id': row[0],
                        'timestamp': row[1],
                        'prediction_type': row[2],
                        'predicted_value': row[3],
                        'confidence': row[4],
                        'time_horizon_minutes': row[5],
                    }
                    
                    idx = 6
                    if 'department' in columns:
                        row_dict['department'] = row[idx]
                        idx += 1
                    else:
                        row_dict['department'] = None
                    
                    if has_model_version:
                        row_dict['model_version'] = row[idx]
                        idx += 1
                    else:
                        row_dict['model_version'] = None
                    
                    if has_features_json:
                        row_dict['features_json'] = row[idx]
                    else:
                        row_dict['features_json'] = None
                    
                    result.append(row_dict)
                
                return result
            finally:
                conn.close()
    
    # ===== METRICS =====
    
    def get_metrics_last_n_minutes(self, minutes: int) -> List[Dict]:
        """Gibt Metriken der letzten N Minuten zurück"""
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT timestamp, metric_type, value, unit, department
                    FROM metrics
                    WHERE timestamp >= ?
                    ORDER BY timestamp DESC
                """, (cutoff,))
                rows = cursor.fetchall()
                # Handle DatabaseError when accessing row data (corruption detected during read)
                result = []
                for row in rows:
                    try:
                        result.append({
                            'timestamp': row[0],
                            'metric_type': row[1],
                            'value': row[2],
                            'unit': row[3],
                            'department': row[4]
                        })
                    except (sqlite3.DatabaseError, IndexError, TypeError):
                        # Skip corrupted rows
                        continue
                return result
            except sqlite3.DatabaseError:
                # Return empty list on corruption
                return []
            finally:
                conn.close()
    
    def get_recent_metrics(self, limit: int = 100) -> List[Dict]:
        """Gibt kürzliche Metriken zurück"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT timestamp, metric_type, value, unit, department
                    FROM metrics
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
                rows = cursor.fetchall()
                # Handle DatabaseError when accessing row data (corruption detected during read)
                result = []
                for row in rows:
                    try:
                        result.append({
                            'timestamp': row[0],
                            'metric_type': row[1],
                            'value': row[2],
                            'unit': row[3],
                            'department': row[4]
                        })
                    except (sqlite3.DatabaseError, IndexError, TypeError):
                        # Skip corrupted rows
                        continue
                return result
            except sqlite3.DatabaseError:
                # Return empty list on corruption
                return []
            finally:
                conn.close()
    
    def save_metric(self, metric_type: str, value: float, unit: str = None, department: str = None):
        """Speichert eine Metrik"""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO metrics (timestamp, metric_type, value, unit, department)
                    VALUES (?, ?, ?, ?, ?)
                """, (datetime.now(timezone.utc).isoformat(), metric_type, value, unit, department))
                conn.commit()
            finally:
                conn.close()
    
    def save_metrics_batch(self, metrics: List[Tuple[str, float, str, Optional[str]]]):
        """
        Speichert mehrere Metriken in einem Batch (effizienter als einzelne Aufrufe).
        
        Args:
            metrics: Liste von Tupeln (metric_type, value, unit, department)
                    unit und department können None sein
        """
        if not metrics:
            return
        
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                timestamp = datetime.now(timezone.utc).isoformat()
                cursor.executemany("""
                    INSERT INTO metrics (timestamp, metric_type, value, unit, department)
                    VALUES (?, ?, ?, ?, ?)
                """, [(timestamp, metric_type, value, unit, department) 
                       for metric_type, value, unit, department in metrics])
                conn.commit()
            finally:
                conn.close()
    
    def save_predictions_batch(self, predictions: List[Dict]) -> None:
        """
        Speichert mehrere Vorhersagen in einem Batch (thread-safe).
        
        Args:
            predictions: Liste von Dictionaries mit Keys:
                - prediction_type: str
                - predicted_value: float
                - confidence: float
                - time_horizon_minutes: int
                - department: Optional[str]
                - model_version: Optional[str] (default: 'v1.0')
        """
        if not predictions:
            return
        
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                now = datetime.now(timezone.utc).isoformat()
                for pred in predictions:
                    cursor.execute("""
                        INSERT INTO predictions 
                        (timestamp, prediction_type, predicted_value, confidence, time_horizon_minutes, department, model_version)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        now,
                        pred['prediction_type'],
                        pred['predicted_value'],
                        pred['confidence'],
                        pred['time_horizon_minutes'],
                        pred.get('department'),
                        pred.get('model_version', 'v1.0')
                    ))
                conn.commit()
            finally:
                conn.close()
    
    def save_recommendations_batch(self, recommendations: List[Dict]) -> None:
        """
        Speichert mehrere Empfehlungen in einem Batch (thread-safe).
        Überspringt Duplikate (ähnliche Empfehlung in letzter Stunde).
        
        Args:
            recommendations: Liste von Dictionaries mit Keys:
                - title: str
                - description: Optional[str]
                - priority: str
                - department: Optional[str]
                - rec_type: Optional[str] (default: 'general')
                - status: Optional[str] (default: 'pending')
                - action: Optional[str]
                - reason: Optional[str]
                - expected_impact: Optional[str]
                - safety_note: Optional[str]
                - explanation_score: Optional[str] (default: 'medium')
        """
        if not recommendations:
            return
        
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                now = datetime.now(timezone.utc).isoformat()
                for rec in recommendations:
                    # Prüfe ob ähnliche Empfehlung bereits existiert
                    cursor.execute("""
                        SELECT id FROM recommendations
                        WHERE title = ? AND status = 'pending' AND timestamp > datetime('now', '-1 hour')
                    """, (rec['title'],))
                    if cursor.fetchone():
                        continue  # Überspringe Duplikate
                    
                    cursor.execute("""
                        INSERT INTO recommendations 
                        (timestamp, title, description, priority, department, rec_type, status,
                         action, reason, expected_impact, safety_note, explanation_score)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        now,
                        rec['title'],
                        rec.get('description', rec.get('action', '')),
                        rec['priority'],
                        rec.get('department'),
                        rec.get('rec_type', 'general'),
                        rec.get('status', 'pending'),
                        rec.get('action'),
                        rec.get('reason'),
                        rec.get('expected_impact'),
                        rec.get('safety_note'),
                        rec.get('explanation_score', 'medium')
                    ))
                conn.commit()
            finally:
                conn.close()
    
    def create_simulation_event(self, event_type: str, start_time: datetime, duration_minutes: int, 
                                affected_departments: List[str], description: str, intensity: float = None) -> int:
        """
        Erstellt ein Simulation-Event in der Datenbank (thread-safe).
        
        Args:
            event_type: Typ des Events (z.B. 'surge', 'equipment_failure', 'staffing_shortage', 'manv')
            start_time: Startzeit des Events
            duration_minutes: Dauer in Minuten
            affected_departments: Liste der betroffenen Abteilungen
            description: Beschreibung des Events
            intensity: Optional: Intensität des Events
        
        Returns:
            int: ID des erstellten Events
        """
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                if intensity is not None:
                    cursor.execute("""
                        INSERT INTO simulation_events (event_type, start_time, duration_minutes, intensity, affected_departments, description)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        event_type,
                        start_time.isoformat(),
                        duration_minutes,
                        intensity,
                        ','.join(affected_departments),
                        description
                    ))
                else:
                    cursor.execute("""
                        INSERT INTO simulation_events (event_type, start_time, duration_minutes, affected_departments, description)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        event_type,
                        start_time.isoformat(),
                        duration_minutes,
                        ','.join(affected_departments),
                        description
                    ))
                conn.commit()
                return cursor.lastrowid
            finally:
                conn.close()
    
    def update_simulation_event_end_time(self, event_type: str, start_time: datetime, end_time: datetime) -> bool:
        """
        Aktualisiert das End-Datum eines Simulation-Events (thread-safe).
        
        Args:
            event_type: Typ des Events
            start_time: Startzeit des Events (für Identifikation)
            end_time: Endzeit des Events
        
        Returns:
            bool: True wenn Update erfolgreich
        """
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    UPDATE simulation_events
                    SET end_time = ?
                    WHERE event_type = ? AND start_time = ?
                """, (end_time.isoformat(), event_type, start_time.isoformat()))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()
    
    def create_operation(self, operation_type: str, department: str, status: str, 
                        duration_minutes: int, timestamp: datetime, start_time: datetime) -> int:
        """
        Erstellt eine Operation in der Datenbank (thread-safe).
        
        Args:
            operation_type: Typ der Operation
            department: Abteilung
            status: Status (z.B. 'completed')
            duration_minutes: Dauer in Minuten
            timestamp: Zeitstempel
            start_time: Startzeit
        
        Returns:
            int: ID der erstellten Operation
        """
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO operations (operation_type, department, status, duration_minutes, timestamp, start_time)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    operation_type,
                    department,
                    status,
                    duration_minutes,
                    timestamp.isoformat(),
                    start_time.isoformat()
                ))
                conn.commit()
                return cursor.lastrowid
            finally:
                conn.close()
    
    def save_patient_event(self, event_type: str, department: str, patient_category: str = None) -> int:
        """
        Speichert ein anonymisiertes Patientenevent in der Datenbank (thread-safe).
        
        Args:
            event_type: Typ des Events (z.B. 'admission', 'discharge')
            department: Abteilung
            patient_category: Optional: Kategorie des Patienten
        
        Returns:
            int: ID des erstellten Events
        """
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO patient_events (timestamp, event_type, department, patient_category)
                    VALUES (?, ?, ?, ?)
                """, (
                    datetime.now(timezone.utc).isoformat(),
                    event_type,
                    department,
                    patient_category
                ))
                conn.commit()
                return cursor.lastrowid
            finally:
                conn.close()
    
    def create_alert_safe(self, timestamp: datetime, severity: str, message: str, 
                         department: str, metric_type: str, value: float) -> bool:
        """
        Erstellt einen Alert (thread-safe, nur wenn nicht bereits vorhanden).
        
        Args:
            timestamp: Zeitstempel
            severity: Schweregrad ('high', 'medium', 'low')
            message: Nachricht
            department: Abteilung
            metric_type: Typ der Metrik
            value: Wert der Metrik
        
        Returns:
            bool: True wenn Alert erstellt wurde, False wenn bereits vorhanden
        """
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Prüfe ob ähnlicher Alert bereits existiert (letzte 10 Minuten)
                cutoff = (timestamp - timedelta(minutes=10)).isoformat()
                cursor.execute("""
                    SELECT id FROM alerts
                    WHERE metric_type = ? AND department = ? AND severity = ? AND timestamp > ? AND resolved_at IS NULL
                """, (metric_type, department, severity, cutoff))
                
                if cursor.fetchone():
                    return False  # Alert bereits vorhanden
                
                # Mappe metric_type zu alert_type
                alert_type_map = {
                    'ed_load': 'capacity',
                    'waiting_count': 'patient',
                    'beds_free': 'capacity',
                    'transport_queue': 'transport',
                    'staff_load': 'staffing',
                    'or_load': 'capacity',
                    'rooms_free': 'capacity',
                    'inventory': 'inventory'
                }
                alert_type = alert_type_map.get(metric_type, 'general')
                
                # Erstelle neuen Alert
                cursor.execute("""
                    INSERT INTO alerts (timestamp, alert_type, severity, message, department, metric_type, value, acknowledged)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """, (timestamp.isoformat(), alert_type, severity, message, department, metric_type, value))
                conn.commit()
                return True
            finally:
                conn.close()
    
    # ===== AUDIT LOG =====
    
    def get_audit_log(self, limit: int = 100) -> List[Dict]:
        """Gibt Audit-Log zurück"""
        # Ensure migration has run
        try:
            self._migrate_schema()
        except Exception:
            pass  # Continue anyway - defensive query will handle missing columns
        
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                # Check if table exists first
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
                table_exists = cursor.fetchone()
                
                if not table_exists:
                    return []
                
                # Check if columns exist before querying
                try:
                    cursor.execute("PRAGMA table_info(audit_log)")
                    columns = [row[1] for row in cursor.fetchall()]
                except sqlite3.DatabaseError as db_err:
                    raise
                
                # Check for all required columns
                has_user = 'user' in columns
                has_user_role = 'user_role' in columns
                has_entity_type = 'entity_type' in columns
                has_entity_id = 'entity_id' in columns
                has_details = 'details' in columns
                
                # Build SELECT clause based on available columns
                select_parts = ['id', 'timestamp', 'action_type']
                
                if has_user:
                    select_parts.append('user')
                else:
                    select_parts.append('NULL as user')
                
                if has_user_role:
                    select_parts.append('user_role')
                else:
                    select_parts.append('NULL as user_role')
                
                if has_entity_type:
                    select_parts.append('entity_type')
                else:
                    select_parts.append('NULL as entity_type')
                
                if has_entity_id:
                    select_parts.append('entity_id')
                else:
                    select_parts.append('NULL as entity_id')
                
                if has_details:
                    select_parts.append('details')
                else:
                    select_parts.append('NULL as details')
                
                select_clause = ', '.join(select_parts)
                
                query = f"""
                    SELECT {select_clause}
                    FROM audit_log
                    ORDER BY timestamp DESC
                    LIMIT ?
                """
                
                try:
                    cursor.execute(query, (limit,))
                    rows = cursor.fetchall()
                except Exception as query_error:
                    # If query failed, try a minimal query with only required columns
                    try:
                        minimal_query = """
                            SELECT id, timestamp, action_type
                            FROM audit_log
                            ORDER BY timestamp DESC
                            LIMIT ?
                        """
                        cursor.execute(minimal_query, (limit,))
                        rows = cursor.fetchall()
                        # Return minimal results
                        return [{
                            'id': row[0],
                            'timestamp': row[1],
                            'action_type': row[2],
                            'user': None,
                            'user_role': None,
                            'entity_type': None,
                            'entity_id': None,
                            'details': None
                        } for row in rows]
                    except Exception as fallback_error:
                        raise query_error  # Raise original error
                
                # Map results to dict based on column positions
                result = []
                for row in rows:
                    row_dict = {
                        'id': row[0],
                        'timestamp': row[1],
                        'action_type': row[2],
                    }
                    
                    idx = 3
                    if has_user:
                        row_dict['user'] = row[idx]
                        idx += 1
                    else:
                        row_dict['user'] = None
                    
                    if has_user_role:
                        row_dict['user_role'] = row[idx]
                        idx += 1
                    else:
                        row_dict['user_role'] = None
                    
                    if has_entity_type:
                        row_dict['entity_type'] = row[idx]
                        idx += 1
                    else:
                        row_dict['entity_type'] = None
                    
                    if has_entity_id:
                        row_dict['entity_id'] = row[idx]
                        idx += 1
                    else:
                        row_dict['entity_id'] = None
                    
                    if has_details:
                        row_dict['details'] = row[idx]
                    else:
                        row_dict['details'] = None
                    
                    result.append(row_dict)
                
                return result
            finally:
                conn.close()
    
    # ===== BATCH QUERY METHODS =====
    # Kombinierte Abfragen für bessere Performance
    
    def get_dashboard_data_batch(self) -> Dict[str, List[Dict]]:
        """
        Lädt alle Dashboard-Daten in einer Batch-Query für bessere Performance.
        Verwendet eine einzige Datenbankverbindung für alle Queries.
        
        Returns:
            Dict mit Keys: alerts, recommendations, transport, inventory, devices, predictions
        """
        result = {
            'alerts': [],
            'recommendations': [],
            'transport': [],
            'inventory': [],
            'devices': [],
            'predictions': [],
            'metrics_recent': [],
            'audit_log': []
        }
        
        with self.connection_context() as conn:
            cursor = conn.cursor()
            try:
                # Alerts - defensive query to handle missing columns
                try:
                    # Check if columns exist before querying
                    cursor.execute("PRAGMA table_info(alerts)")
                    columns = [row[1] for row in cursor.fetchall()]
                    
                    # Check for all required columns
                    has_resolved_at = 'resolved_at' in columns
                    has_metric_type = 'metric_type' in columns
                    has_value = 'value' in columns
                    has_acknowledged = 'acknowledged' in columns
                    has_department = 'department' in columns
                    
                    # Build SELECT clause based on available columns
                    select_parts = ['id', 'timestamp', 'severity', 'message']
                    
                    if has_department:
                        select_parts.append('department')
                    else:
                        select_parts.append('NULL as department')
                    
                    if has_metric_type:
                        select_parts.append('metric_type')
                    else:
                        select_parts.append('NULL as metric_type')
                    
                    if has_value:
                        select_parts.append('value')
                    else:
                        select_parts.append('NULL as value')
                    
                    if has_acknowledged:
                        select_parts.append('acknowledged')
                    else:
                        select_parts.append('0 as acknowledged')
                    
                    if has_resolved_at:
                        select_parts.append('resolved_at')
                    else:
                        select_parts.append('NULL as resolved_at')
                    
                    select_clause = ', '.join(select_parts)
                    
                    # Build WHERE clause - only filter by resolved_at if column exists
                    where_clause = "WHERE resolved_at IS NULL" if has_resolved_at else ""
                    
                    query = f"""
                        SELECT {select_clause}
                        FROM alerts
                        {where_clause}
                        ORDER BY timestamp DESC
                    """
                    
                    cursor.execute(query)
                    rows = cursor.fetchall()
                    
                    # Handle DatabaseError when accessing row data
                    alerts_result = []
                    for row in rows:
                        try:
                            row_dict = {
                                'id': row[0],
                                'timestamp': row[1],
                                'severity': row[2],
                                'message': row[3],
                            }
                            
                            # Map columns based on their positions
                            idx = 4
                            if has_department:
                                row_dict['department'] = row[idx]
                                idx += 1
                            else:
                                row_dict['department'] = None
                            
                            if has_metric_type:
                                row_dict['metric_type'] = row[idx]
                                idx += 1
                            else:
                                row_dict['metric_type'] = None
                            
                            if has_value:
                                row_dict['value'] = row[idx]
                                idx += 1
                            else:
                                row_dict['value'] = None
                            
                            if has_acknowledged:
                                row_dict['acknowledged'] = bool(row[idx])
                                idx += 1
                            else:
                                row_dict['acknowledged'] = False
                            
                            if has_resolved_at:
                                row_dict['resolved_at'] = row[idx]
                            else:
                                row_dict['resolved_at'] = None
                            
                            alerts_result.append(row_dict)
                        except (sqlite3.DatabaseError, IndexError, TypeError):
                            continue
                    result['alerts'] = alerts_result
                except sqlite3.DatabaseError:
                    result['alerts'] = []
                except Exception:
                    pass
                
                # Recommendations
                try:
                    cursor.execute("""
                        SELECT id, timestamp, title, description, priority, department, rec_type, status, action, reason, expected_impact, safety_note, explanation_score
                        FROM recommendations
                        WHERE status = 'pending'
                        ORDER BY timestamp DESC
                    """)
                    rows = cursor.fetchall()
                    # Handle DatabaseError when accessing row data
                    recs_result = []
                    for row in rows:
                        try:
                            recs_result.append({
                                'id': row[0],
                                'timestamp': row[1],
                                'title': row[2],
                                'description': row[3],
                                'priority': row[4],
                                'department': row[5],
                                'rec_type': row[6],
                                'status': row[7],
                                'action': row[8],
                                'reason': row[9],
                                'expected_impact': row[10],
                                'safety_note': row[11],
                                'explanation_score': row[12]
                            })
                        except (sqlite3.DatabaseError, IndexError, TypeError):
                            continue
                    result['recommendations'] = recs_result
                except sqlite3.DatabaseError:
                    result['recommendations'] = []
                except Exception:
                    pass
                
                # Transport
                try:
                    cursor.execute("""
                        SELECT id, timestamp, from_location, to_location, priority, status, request_type,
                               estimated_time_minutes, actual_time_minutes, start_time, expected_completion_time,
                               delay_minutes, related_entity_type, related_entity_id, planned_start_time,
                               requested_time_start, requested_time_end
                        FROM transport_requests
                        ORDER BY timestamp DESC
                    """)
                    rows = cursor.fetchall()
                    result['transport'] = [{
                        'id': row[0],
                        'timestamp': row[1],
                        'from_location': row[2],
                        'to_location': row[3],
                        'priority': row[4],
                        'status': row[5],
                        'request_type': row[6],
                        'estimated_time_minutes': row[7],
                        'actual_time_minutes': row[8],
                        'start_time': row[9],
                        'expected_completion_time': row[10],
                        'delay_minutes': row[11],
                        'related_entity_type': row[12],
                        'related_entity_id': row[13],
                        'planned_start_time': row[14],
                        'requested_time_start': row[15] if len(row) > 15 else None,
                        'requested_time_end': row[16] if len(row) > 16 else None
                    } for row in rows]
                except Exception:
                    pass
                
                # Inventory
                try:
                    cursor.execute("""
                        SELECT id, item_name, department, current_stock, min_threshold, max_capacity, unit, last_updated, category
                        FROM inventory
                        ORDER BY department, item_name
                    """)
                    rows = cursor.fetchall()
                    result['inventory'] = [{
                        'id': row[0],
                        'item_name': row[1],
                        'department': row[2],
                        'current_stock': row[3],
                        'min_threshold': row[4],
                        'max_capacity': row[5],
                        'unit': row[6],
                        'last_updated': row[7],
                        'category': row[8]
                    } for row in rows]
                except Exception:
                    pass
                
                # Devices
                try:
                    cursor.execute("""
                        SELECT id, device_type, device_id, department, last_maintenance, next_maintenance_due, status, urgency_level
                        FROM devices
                        WHERE urgency_level IN ('high', 'hoch', 'medium', 'mittel')
                        ORDER BY 
                            CASE urgency_level
                                WHEN 'high' THEN 1
                                WHEN 'hoch' THEN 1
                                WHEN 'medium' THEN 2
                                WHEN 'mittel' THEN 2
                                ELSE 3
                            END,
                            next_maintenance_due ASC
                    """)
                    rows = cursor.fetchall()
                    result['devices'] = [{
                        'id': row[0],
                        'device_type': row[1],
                        'device_id': row[2],
                        'department': row[3],
                        'last_maintenance': row[4],
                        'next_maintenance_due': row[5],
                        'status': row[6],
                        'urgency_level': row[7]
                    } for row in rows]
                except Exception:
                    pass
                
                # Predictions (15 minutes)
                try:
                    cursor.execute("""
                        SELECT id, timestamp, prediction_type, predicted_value, confidence, time_horizon_minutes, department, model_version
                        FROM predictions
                        WHERE time_horizon_minutes <= 15
                        ORDER BY timestamp DESC, time_horizon_minutes ASC
                    """)
                    rows = cursor.fetchall()
                    result['predictions'] = [{
                        'id': row[0],
                        'timestamp': row[1],
                        'prediction_type': row[2],
                        'predicted_value': row[3],
                        'confidence': row[4],
                        'time_horizon_minutes': row[5],
                        'department': row[6],
                        'model_version': row[7]
                    } for row in rows]
                except Exception:
                    pass
                
                # Recent Metrics (für Metrics-Seite)
                try:
                    cursor.execute("""
                        SELECT id, timestamp, metric_type, value, unit, department
                        FROM metrics
                        ORDER BY timestamp DESC
                        LIMIT 100
                    """)
                    rows = cursor.fetchall()
                    result['metrics_recent'] = [{
                        'id': row[0],
                        'timestamp': row[1],
                        'metric_type': row[2],
                        'value': row[3],
                        'unit': row[4] if len(row) > 4 else None,
                        'department': row[5] if len(row) > 5 else None
                    } for row in rows]
                except Exception:
                    pass
                
                # Audit Log (für Operations-Seite)
                try:
                    cursor.execute("""
                        SELECT id, timestamp, action_type, user, user_role, entity_type, entity_id, details
                        FROM audit_log
                        ORDER BY timestamp DESC
                        LIMIT 100
                    """)
                    rows = cursor.fetchall()
                    result['audit_log'] = [{
                        'id': row[0],
                        'timestamp': row[1],
                        'action_type': row[2],
                        'user': row[3] if len(row) > 3 else None,
                        'user_role': row[4] if len(row) > 4 else None,
                        'entity_type': row[5] if len(row) > 5 else None,
                        'entity_id': row[6] if len(row) > 6 else None,
                        'details': row[7] if len(row) > 7 else None
                    } for row in rows]
                except Exception:
                    pass
                    
            except Exception as e:
                # Bei Fehler, verwende Fallback auf einzelne Methoden
                result['alerts'] = self.get_active_alerts()
                result['recommendations'] = self.get_pending_recommendations()
                result['transport'] = self.get_transport_requests()
                result['inventory'] = self.get_inventory_status()
                result['devices'] = self.get_device_maintenance_urgencies()
                result['predictions'] = self.get_predictions(15)
        
        return result
    
    def get_metrics_page_data_batch(self, time_range_minutes: int = None) -> Dict[str, List[Dict]]:
        """
        Lädt alle Metrics-Seite-Daten in einer Batch-Query.
        
        Args:
            time_range_minutes: Optional, Zeitraum für Metriken in Minuten
        
        Returns:
            Dict mit Keys: metrics, alerts, predictions, recommendations, transport, inventory, devices, capacity
        """
        result = {
            'metrics': [],
            'alerts': [],
            'predictions': [],
            'recommendations': [],
            'transport': [],
            'inventory': [],
            'devices': [],
            'capacity': []
        }
        
        with self.connection_context() as conn:
            cursor = conn.cursor()
            try:
                # Metrics
                try:
                    if time_range_minutes:
                        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=time_range_minutes)).isoformat()
                        cursor.execute("""
                            SELECT timestamp, metric_type, value, unit, department
                            FROM metrics
                            WHERE timestamp >= ?
                            ORDER BY timestamp DESC
                        """, (cutoff,))
                    else:
                        cursor.execute("""
                            SELECT timestamp, metric_type, value, unit, department
                            FROM metrics
                            ORDER BY timestamp DESC
                            LIMIT 1000
                        """)
                    rows = cursor.fetchall()
                    # Handle DatabaseError when accessing row data (corruption detected during read)
                    metrics_result = []
                    for row in rows:
                        try:
                            metrics_result.append({
                                'timestamp': row[0],
                                'metric_type': row[1],
                                'value': row[2],
                                'unit': row[3],
                                'department': row[4]
                            })
                        except (sqlite3.DatabaseError, IndexError, TypeError):
                            # Skip corrupted rows
                            continue
                    result['metrics'] = metrics_result
                except sqlite3.DatabaseError:
                    result['metrics'] = []  # Return empty list on corruption
                except Exception:
                    pass
                
                # Alerts
                try:
                    hours = (time_range_minutes // 60) if time_range_minutes else 168
                    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
                    cursor.execute("""
                        SELECT id, timestamp, severity, message, department, metric_type, value, acknowledged, resolved_at
                        FROM alerts
                        WHERE timestamp >= ? AND (resolved_at IS NULL OR resolved_at = '')
                        ORDER BY timestamp DESC
                    """, (cutoff,))
                    rows = cursor.fetchall()
                    result['alerts'] = [{
                        'id': row[0],
                        'timestamp': row[1],
                        'severity': row[2],
                        'message': row[3],
                        'department': row[4],
                        'metric_type': row[5],
                        'value': row[6],
                        'acknowledged': row[7],
                        'resolved_at': row[8]
                    } for row in rows]
                except Exception:
                    pass
                
                # Predictions
                try:
                    cursor.execute("""
                        SELECT id, timestamp, prediction_type, predicted_value, confidence, time_horizon_minutes, department, model_version
                        FROM predictions
                        WHERE time_horizon_minutes <= 60
                        ORDER BY timestamp DESC, time_horizon_minutes ASC
                    """)
                    rows = cursor.fetchall()
                    result['predictions'] = [{
                        'id': row[0],
                        'timestamp': row[1],
                        'prediction_type': row[2],
                        'predicted_value': row[3],
                        'confidence': row[4],
                        'time_horizon_minutes': row[5],
                        'department': row[6],
                        'model_version': row[7]
                    } for row in rows]
                except Exception:
                    pass
                
                # Recommendations
                try:
                    cursor.execute("""
                        SELECT id, timestamp, title, description, priority, department, rec_type, status, action, reason, expected_impact, safety_note, explanation_score
                        FROM recommendations
                        WHERE status = 'pending'
                        ORDER BY timestamp DESC
                    """)
                    rows = cursor.fetchall()
                    result['recommendations'] = [{
                        'id': row[0],
                        'timestamp': row[1],
                        'title': row[2],
                        'description': row[3],
                        'priority': row[4],
                        'department': row[5],
                        'rec_type': row[6],
                        'status': row[7],
                        'action': row[8],
                        'reason': row[9],
                        'expected_impact': row[10],
                        'safety_note': row[11],
                        'explanation_score': row[12]
                    } for row in rows]
                except Exception:
                    pass
                
                # Transport
                try:
                    cursor.execute("""
                        SELECT id, timestamp, from_location, to_location, priority, status, request_type, estimated_time_minutes, actual_time_minutes, start_time, expected_completion_time, delay_minutes
                        FROM transport_requests
                        ORDER BY timestamp DESC
                    """)
                    rows = cursor.fetchall()
                    result['transport'] = [{
                        'id': row[0],
                        'timestamp': row[1],
                        'from_location': row[2],
                        'to_location': row[3],
                        'priority': row[4],
                        'status': row[5],
                        'request_type': row[6],
                        'estimated_time_minutes': row[7],
                        'actual_time_minutes': row[8],
                        'start_time': row[9],
                        'expected_completion_time': row[10],
                        'delay_minutes': row[11]
                    } for row in rows]
                except Exception:
                    pass
                
                # Inventory
                try:
                    cursor.execute("""
                        SELECT id, item_name, department, current_stock, min_threshold, max_capacity, unit, last_updated, category
                        FROM inventory
                        ORDER BY department, item_name
                    """)
                    rows = cursor.fetchall()
                    result['inventory'] = [{
                        'id': row[0],
                        'item_name': row[1],
                        'department': row[2],
                        'current_stock': row[3],
                        'min_threshold': row[4],
                        'max_capacity': row[5],
                        'unit': row[6],
                        'last_updated': row[7],
                        'category': row[8]
                    } for row in rows]
                except Exception:
                    pass
                
                # Devices
                try:
                    cursor.execute("""
                        SELECT id, device_type, device_id, department, last_maintenance, next_maintenance_due, status, urgency_level
                        FROM devices
                        ORDER BY 
                            CASE urgency_level
                                WHEN 'high' THEN 1
                                WHEN 'hoch' THEN 1
                                WHEN 'medium' THEN 2
                                WHEN 'mittel' THEN 2
                                ELSE 3
                            END,
                            next_maintenance_due ASC
                    """)
                    rows = cursor.fetchall()
                    result['devices'] = [{
                        'id': row[0],
                        'device_type': row[1],
                        'device_id': row[2],
                        'department': row[3],
                        'last_maintenance': row[4],
                        'next_maintenance_due': row[5],
                        'status': row[6],
                        'urgency_level': row[7]
                    } for row in rows]
                except Exception:
                    pass
                
                # Capacity (wird separat geladen, da Simulation-Metriken benötigt werden)
                # Wird in der aufrufenden Funktion behandelt
                    
            except Exception as e:
                # Fallback auf einzelne Methoden bei Fehler
                if time_range_minutes:
                    result['metrics'] = self.get_metrics_last_n_minutes(time_range_minutes)
                else:
                    result['metrics'] = self.get_recent_metrics(1000)
                hours = (time_range_minutes // 60) if time_range_minutes else 168
                result['alerts'] = self.get_alerts_by_time_range(hours)
                result['predictions'] = self.get_predictions(60)
                result['recommendations'] = self.get_pending_recommendations()
                result['transport'] = self.get_transport_requests()
                result['inventory'] = self.get_inventory_status()
                result['devices'] = self.get_device_maintenance_urgencies()
        
        return result

