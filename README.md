# AI Hub

Több AI (OpenAI, Anthropic, Gemini, GitHub Models, Perplexity, opcionálisan
DeepSeek) egy felületen: egy AI, összehasonlítás, kerekasztal, vita, kritika.

## Indítás VS Code-ban

1. **Repó megnyitása:** `File → Open Folder…` → a `HUBPI` mappa.
   A felugró ablakban telepítsd az ajánlott Python bővítményeket.
2. **Virtuális környezet:** `Ctrl+Shift+P` → **Python: Create Environment** →
   **Venv** → válaszd a Python 3.10+ verziót → pipáld be a `requirements.txt`-t.
   (Ez létrehozza a `.venv` mappát és telepíti a csomagokat.)
3. **Kulcsok:** másold le a `.env.example` fájlt `.env` néven, és töltsd ki
   a kulcsokat. Elég egy is – a többi „nincs kulcs” jelzéssel szürke marad.
4. **Indítás:** `F5` (vagy bal oldalt *Run and Debug* → **AI Hub (helyi szerver)**).
   A böngésző magától megnyílik: http://127.0.0.1:8000
5. **Leállítás:** `Shift+F5`.

A **AI Hub (auto-újraindítás mentéskor)** változat minden mentésnél újraindul
– fejlesztéshez kényelmes, de ott a töréspontok nem mindig működnek.

Tesztek: `Ctrl+Shift+P` → **Tasks: Run Test Task**, vagy a bal oldali
lombik (Testing) ikon.

## Indítás terminálból

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # Windows: copy .env.example .env
uvicorn main:app --host 127.0.0.1 --port 8000
```

## Biztonság

- Jelszó nélkül csak helyben (`127.0.0.1`) futtasd. Hálózatra / internetre
  állítsd be a `HUB_PASSWORD`-öt, és csak HTTPS mögött tedd ki.
- A `.env` sosem kerülhet fel a GitHubra (a `.gitignore` kizárja).
- A DeepSeek „Limited” provider: az adatokat Kínában tárolják, ügyfél- vagy
  személyes adatot ne küldj neki. Kulcs nélkül meg sem jelenik.
