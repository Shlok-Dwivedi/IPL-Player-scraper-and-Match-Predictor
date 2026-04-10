# 🏏 IPL Fantasy XI Clash Analyzer (2008–2026)

A professional-grade, ball-by-ball IPL statistics engine and fantasy match predictor. Built to support **100% player coverage** from the inaugural 2008 season through the upcoming 2026 IPL season.

![IPL Analytics](https://img.shields.io/badge/Data%20Source-Cricsheet%20%2F%20Cricinfo-blue?style=for-the-badge)
![Python](https://img.shields.io/badge/Built%20With-Python%203.11+-ffd43b?style=for-the-badge&logo=python)

## 🚀 Key Features

*   **Global Player Registry**: Audit-verified database of **982+ players** (Every player from 2008–2026).
*   **3-Layer Scraping Pipeline**:
    1.  **Cricsheet (Ball-by-Ball)**: Locally computed career stats via Pandas + Python (High performance).
    2.  **Cricinfo/Cricbuzz Sweep**: Fallback profile scraping for brand-new debutants and modern stars (e.g., Mukul Choudhary, Cameron Green).
    3.  **Smart Resolver**: Resolves fuzzy names ("Kohli" → "Virat Kohli") and handles duplicate surnames with ID-based precision.
*   **Predictive Match Engine**:
    *   **Batting Order Optimization**: Auto-arranges 11 players into slots (Openers, Middle Order, Finishers, Tail).
    *   **Bowling Quota Allocation**: Distributes 20 overs among the 5+ best bowling options in your XI.
    *   **Match Simulation**: Simulates an XI vs. XI clash based on weighted impact, recent form, and team balance scores.

## 🛠️ Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/Shlok-Dwivedi/IPL-Player-scraper-and-Match-Predictor.git
    cd IPL-Player-scraper-and-Match-Predictor
    ```

2.  **Install dependencies**:
    ```bash
    pip install flask requests beautifulsoup4 pandas curl_cffi matplotlib
    ```

## 🎮 How to Use

### 🌐 Web GUI (Recommended)
Run the Flask server and open the interactive dashboard in your browser:
```bash
python app.py
```
*Open **http://localhost:5000** to start building and analyzing your Fantasy XIs.*

### ⌨️ CLI Mode
Run the interactive CLI for instant terminal-based analysis:
```bash
python main.py
```

### 🧹 Database Maintenance
To update the player registry or sweep the latest season for new stars:
```bash
python build_player_db.py
```

## 📊 Technical Architecture

*   **`models.py`**: OOP-based representation of Players, XIs, and Match Predictor logic.
*   **`scraper.py`**: Orchestrates the 3-layer data retrieval and caching system.
*   **`analyzer.py`**: Handles statistical aggregation and team impact calculations.
*   **`data/player_ids.json`**: The core audited registry (982 entries).

## 📄 License
MIT License - Created by Shlok Dwivedi.
