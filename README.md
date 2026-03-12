# Marketing Hub

Dein taegliches Marketing-Update — Trends, Studien, Kampagnen und mehr.
Automatisch aktualisiert via GitHub Actions.

## Setup in 3 Schritten

### 1. Repository erstellen

1. Gehe zu [github.com/new](https://github.com/new)
2. Name: `marketing-hub`
3. Sichtbarkeit: **Public** (noetig fuer GitHub Pages Free)
4. Klicke **Create repository**

### 2. Dateien hochladen

Lade alle Dateien aus diesem Ordner in dein neues Repository hoch.
Oder einfach per Drag & Drop auf github.com im Browser!

### 3. GitHub Pages aktivieren

1. Gehe zu **Settings** > **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`, Ordner: `/ (root)`
4. Klicke **Save**

Deine Seite ist in ca. 1 Minute live unter:
`https://Magdalena0301.github.io/marketing-hub/`

## Wie funktioniert es?

- **GitHub Actions** laeuft taeglich um 9:00 Uhr (MESZ)
- Das Python-Script holt News von 10+ Marketing-Quellen per RSS
- Die News werden als `data/news.json` gespeichert
- Die Webseite laedt diese JSON-Datei und zeigt die Artikel an

## News-Quellen

- HubSpot Marketing Blog
- Content Marketing Institute
- Social Media Today
- Search Engine Journal
- Marketing Week
- Adweek
- Think with Google
- Neil Patel Blog
- Moz Blog
- Social Media Examiner

## Manuelles Update

Du kannst die News auch manuell aktualisieren:
1. Gehe zu **Actions** > **Update Marketing News**
2. Klicke **Run workflow**

## Technik

- Reines HTML/CSS/JS — kein Framework noetig
- Python 3.12 fuer RSS-Fetching (nur Standardbibliothek)
- GitHub Actions fuer taegliche Automatisierung
- GitHub Pages fuer kostenloses Hosting
