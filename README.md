## Digitaler Wahrsager - Gemmarndakel

Lokale Tkinter-App, die Sprache aufnimmt, mit Whisper transkribiert und ein lokales
LM-Studio-kompatibles LLM als Orakel befragt.

### Struktur

- `main.py`: schlanker Einstiegspunkt und Dependency-Wiring
- `app_initializer.py`: Start-Initialisierung fuer Audio, Whisper und LM Studio
- `splash.py`: Splash-Screen mit Ladeanimation
- `audio_player.py`: Musikloop fuer die Hintergrundmusik
- `settings.py`: Konfiguration und `.env`-Werte
- `audio_recorder.py`: Mikrofonaufnahme und Audio-Array-Konvertierung
- `transcriber.py`: Faster-Whisper-Anbindung
- `oracle_client.py`: OpenAI-kompatibler LM-Studio-Client
- `fortune_service.py`: fachliche Pipeline von Audio zu Prophezeiung
- `gui.py`: gezeichnete Tkinter-Oberfläche mit Kerze, Kristallkugel und Tarot-Karte
- `prompt_loader.py`: Laden und Validieren der JSON-Promptkonfiguration

### Starten unter Windows

- `Gemmarndakel.bat` startet die App.
- Falls noch keine `.venv` existiert, fuehrt der Launcher zuerst `uv sync --frozen` aus.
- `Gemmarndakel.lnk` ist die passende Verknuepfung mit Kerzen-Karo-Icon.
- Wenn der Projektordner verschoben wurde, `create_shortcut.ps1` ausfuehren, um die Verknuepfung fuer den neuen Pfad neu zu erzeugen.

### Konfiguration

Die Remote-LLM-Verbindung wird beim Start aus `remote_llm.yaml`
gelesen. Wenn die Datei fehlt, wird sie mit diesen Standardwerten erstellt:

```yaml
address: "http://127.0.0.1:1234/v1"
api_key: null
min_token_size: 10000
reasoning_level: "low"
therapy_plan_reasoning_enabled: true
scenario_reasoning_enabled: true
prophecy_reasoning_enabled: true
```

`remote_llm.yaml` ist in `.gitignore`, weil dort lokale Credentials stehen
koennen. Weitere App-Werte koennen optional in `.env` gesetzt
werden:

`reasoning_level` bleibt die globale Staerke fuer aktivierte Reasoning-Stufen.
Wenn eine der drei `*_reasoning_enabled`-Optionen auf `false` steht, wird fuer
diese Stufe kein `reasoning_effort` an das lokale LLM gesendet.

- `LLM_TIMEOUT_SECONDS`, Standard: `5`
- `LLM_GENERATION_TIMEOUT_SECONDS`, Standard: `600`
- `LLM_MODEL`, Standard: `google/gemma-4-12b-qat`
- `PROMPT_CONFIG_FILE`, Standard: `config.json`
- `PROMPT_TEST_QUESTION`, Standard: `Gibt es Aliens und wird die Menschheit Sie entdecken`
- `PREPROMPT_FILE`, alter Fallback fuer bestehende lokale Setups
- `WHISPER_MODEL_SIZE`, Standard: `base`
- `WHISPER_LOCAL_FILES_ONLY`, Standard: `true`
- `CARD_LETTER_DELAY_MS`, Standard: `50`
- `AUDIO_RATE`, Standard: `16000`
- `AUDIO_FRAMES_PER_BUFFER`, Standard: `1024`

### Prompt-Pipeline

`config.json` trennt den Orakel-Prompt in drei Stufen:

- `therapy_plan`: analysiert den Sprach-Input und gibt internes JSON aus
- `scenario`: nutzt den Therapy Plan und erzeugt ein internes Zukunftsszenario als JSON
- `prophecy`: nutzt nur Therapy Plan und Scenario und erzeugt den Kartentext

Jede Variante enthält eine `color` im HTML-Format und ein Gewicht. Die Auswahl
erfolgt zufällig per Mersenne Twister, initialisiert aus OS-Entropy, und wird in
der Konsole als `PICKED_VARIANT` geloggt. Die Pipeline meldet
zusätzlich explizite `STATUS_TRANSITION`-Events fuer `selected`, `reasoning`,
`answer` und `done` inklusive der Farbe der gezogenen Variante. Die
Fortschrittsanzeige ist event-basiert und wird nur grafisch geglättet.

Bei `scenario` werden die B-Varianten nach Gewicht gezogen. Bei `prophecy` wird
immer `style` dynamisch an die gezogene Variante angehängt; nur dort wird die
deutsche Kartenausgabe erzwungen.

Beim Start wird `legend.html` automatisch aus der aktiven Prompt-Konfiguration
neu erzeugt und ueberschrieben. Die Seite zeigt alle Varianten mit Farbe und
Kurzname, nach Stufe gruppiert.

### Prompt-Test ohne UI

Der direkte Prompt-Test umgeht Tkinter, Splash, Audio und Whisper. Er:

- liest die Frage aus `PROMPT_TEST_QUESTION` oder `--question`
- zieht genau eine `therapy_plan`-Variante und eine `scenario`-Variante nach Gewicht
- verwendet diese Zwischenresultate fuer alle `prophecy`-Varianten
- schreibt eine CSV mit einer Zeile pro Prophezeiungsvariante

Beispiele:

```powershell
uv run test
uv run prompt-test --seed 42
uv run test.py --output .\prompt_test_results.csv
```

### Musik

Die Hintergrundmusik startet mit dem Splashscreen und nutzt die lokale Datei
`sb_iwalkwithghosts.mp3`.

Attribution: 'I Walk With Ghosts' by Scott Buckley - released under CC-BY 4.0.
www.scottbuckley.com.au
