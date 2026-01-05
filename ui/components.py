"""
Wiederverwendbare UI-Komponenten für HospitalFlow

Diese Datei enthält wiederverwendbare UI-Komponenten, die konsistent
in der gesamten Anwendung verwendet werden können. Dies sorgt für
einheitliches Design und bessere Wartbarkeit.
"""
from utils import get_severity_color


def render_badge(text: str, severity: str = "low") -> str:
    """
    Rendert ein konsistentes Schweregrad-Badge mit Farbe.
    
    Badges werden verwendet, um Schweregrade, Prioritäten oder Status
    visuell darzustellen. Die Farbe wird automatisch basierend auf
    dem Schweregrad gewählt (rot für hoch, gelb für mittel, grün für niedrig).
    
    Args:
        text (str): Text des Badges (z.B. "Hoch", "Mittel", "Niedrig")
        severity (str): Schweregrad ("high"/"hoch", "medium"/"mittel", "low"/"niedrig").
                       Standard: "low"
    
    Returns:
        str: HTML-String für das Badge
    """
    # Hole Farbe basierend auf Schweregrad
    color = get_severity_color(severity)
    # Erstelle Badge mit konsistentem Styling
    return f'<span class="badge" style="background: {color}; color: white;">{text}</span>'


def render_empty_state(icon: str, title: str, text: str) -> str:
    """
    Rendert einen konsistenten leeren Zustand (Empty State).
    
    Empty States werden angezeigt, wenn keine Daten vorhanden sind
    (z.B. keine Warnungen, keine Empfehlungen). Sie bieten dem Benutzer
    hilfreiche Informationen über den Zustand.
    
    Args:
        icon (str): Icon/Emoji für den leeren Zustand (z.B. "📋", "⚠️")
        title (str): Titel des leeren Zustands (z.B. "Keine Warnungen")
        text (str): Beschreibungstext (z.B. "Es gibt derzeit keine aktiven Warnungen")
    
    Returns:
        str: HTML-String für den leeren Zustand
    """
    return f"""
    <div class="empty-state">
        <div class="empty-state-icon">{icon}</div>
        <div class="empty-state-title">{title}</div>
        <div class="empty-state-text">{text}</div>
    </div>
    """


def render_loading_spinner(text: str = "Lade Daten...") -> str:
    """
    Rendert einen Loading-Spinner mit Text.
    
    Wird während des Ladens von Daten angezeigt, um dem Benutzer
    Feedback zu geben, dass Inhalte geladen werden.
    
    Args:
        text (str): Text der beim Spinner angezeigt wird. Standard: "Lade Daten..."
    
    Returns:
        str: HTML-String für den Loading-Spinner
    """
    return f"""
    <div class="loading-spinner-container fade-in">
        <div class="loading-spinner">
            <div class="spinner"></div>
        </div>
        <div class="loading-text">{text}</div>
    </div>
    """


def render_progressive_container(content: str, delay_class: str = "fade-in") -> str:
    """
    Rendert einen Container mit progressiver Animation.
    
    Wird verwendet, um Inhalte smooth einzublenden.
    Die Animation wird über CSS-Klassen gesteuert.
    
    Args:
        content (str): HTML-Inhalt der eingeblendet werden soll
        delay_class (str): CSS-Klasse für die Animation. 
                          Standard: "fade-in", alternativ: "fade-in-delayed"
    
    Returns:
        str: HTML-String mit animiertem Container
    """
    return f'<div class="{delay_class}">{content}</div>'


