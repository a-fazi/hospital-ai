# Streamlit Cloud Deployment Guide

Diese Anleitung erklärt, wie Sie HospitalFlow auf Streamlit Cloud deployen.

## Voraussetzungen

1. Ein GitHub-Account
2. Ein Streamlit Cloud Account (kostenlos auf [share.streamlit.io](https://share.streamlit.io))
3. Das Projekt muss in einem GitHub-Repository sein

## Schritt-für-Schritt Anleitung

### 1. Repository auf GitHub hochladen

1. Erstellen Sie ein neues Repository auf GitHub
2. Pushen Sie Ihren Code:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/IHR-USERNAME/IHR-REPO.git
   git push -u origin main
   ```

### 2. Auf Streamlit Cloud deployen

1. Gehen Sie zu [share.streamlit.io](https://share.streamlit.io)
2. Melden Sie sich mit Ihrem GitHub-Account an
3. Klicken Sie auf "New app"
4. Wählen Sie Ihr Repository aus
5. Wählen Sie den Branch (meist `main`)
6. Geben Sie den Main file path ein: `app.py`
7. Klicken Sie auf "Deploy!"

### 3. Secrets konfigurieren (WICHTIG!)

Nach dem ersten Deployment müssen Sie die Login-Daten konfigurieren:

1. Gehen Sie zu Ihrem App-Dashboard auf Streamlit Cloud
2. Klicken Sie auf "⚙️ Settings" (oben rechts)
3. Scrollen Sie zu "Secrets"
4. Klicken Sie auf "Edit secrets"
5. Fügen Sie folgende Konfiguration ein:

```toml
[authentication]
username = "ihr-benutzername"
password = "ihr-sicheres-passwort"
```

**WICHTIG:** 
- Ändern Sie `ihr-benutzername` und `ihr-sicheres-passwort` zu sicheren Werten!
- Verwenden Sie ein starkes Passwort (mindestens 12 Zeichen, Groß-/Kleinbuchstaben, Zahlen, Sonderzeichen)
- Die Secrets werden verschlüsselt gespeichert und sind nur für Sie sichtbar

6. Klicken Sie auf "Save"
7. Die App wird automatisch neu deployed

### 4. Lokale Entwicklung (Optional)

Für lokale Entwicklung können Sie entweder:

**Option A: secrets.toml erstellen**
1. Kopieren Sie `.streamlit/secrets.toml.template` zu `.streamlit/secrets.toml`
2. Bearbeiten Sie die Datei und setzen Sie Ihre Credentials:
   ```toml
   [authentication]
   username = "admin"
   password = "ihr-passwort"
   ```

**Option B: Environment Variables**
```bash
export HOSPITALFLOW_USERNAME="admin"
export HOSPITALFLOW_PASSWORD="ihr-passwort"
streamlit run app.py
```

## Sicherheitshinweise

- ⚠️ **Niemals** die `secrets.toml` Datei committen (sie ist bereits in `.gitignore`)
- ⚠️ Verwenden Sie **starke Passwörter** für Production
- ⚠️ Teilen Sie die Login-Daten nur mit autorisierten Personen
- ⚠️ Überprüfen Sie regelmäßig, wer Zugriff auf die App hat

## Troubleshooting

### App startet nicht
- Prüfen Sie, ob alle Dependencies in `requirements.txt` vorhanden sind
- Prüfen Sie die Logs in Streamlit Cloud (unter "Manage app" → "Logs")

### Login funktioniert nicht
- Prüfen Sie, ob die Secrets korrekt in Streamlit Cloud konfiguriert sind
- Stellen Sie sicher, dass die Formatierung in den Secrets korrekt ist (TOML-Format)
- Prüfen Sie die Logs auf Fehlermeldungen

### Datenbank-Probleme
- Die SQLite-Datenbank wird im Container erstellt
- Bei jedem Neustart werden die Daten zurückgesetzt (ephemeral storage)
- Für persistente Daten sollten Sie eine externe Datenbank verwenden (z.B. PostgreSQL)

## Weitere Konfiguration

### Theme anpassen
Bearbeiten Sie `.streamlit/config.toml` um das Theme zu ändern.

### Mehrere Benutzer
Die aktuelle Implementierung unterstützt einen einzelnen Benutzer. Für mehrere Benutzer können Sie die Authentifizierung erweitern.

## Support

Bei Problemen:
1. Prüfen Sie die Streamlit Cloud Logs
2. Testen Sie die App lokal mit `streamlit run app.py`
3. Prüfen Sie die [Streamlit Cloud Dokumentation](https://docs.streamlit.io/streamlit-community-cloud)

