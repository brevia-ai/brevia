# Brevia 1.0 — documento di progetto

Specifica di progetto della libreria: componenti, dati, API e criteri di verifica. Avanzamento, deviazioni e limiti noti sono in [`docs/IMPLEMENTATION.md`](../IMPLEMENTATION.md).

---

## 1. Stato attuale: Brevia 0.15.2

Libreria Python e API REST (FastAPI) per RAG e analisi di testi con LLM. Repo pubblico `brevia-ai/brevia`, licenza MIT (copyright "Brevia AI"), ultimo commit funzionale 24 settembre 2025. Si usa come libreria in un progetto FastAPI o come immagine Docker.

**Stack (lock):** Python 3.10–3.13, FastAPI 0.115, LangChain 0.3 + `langchain-community`, SQLAlchemy 2.0, Pydantic 2.11 beta, Postgres 16 + pgvector 0.7.4. LangChain fornisce modelli, ricerca vettoriale, catene RAG e di riassunto, prompt, splitter.

**Database**

| Tabella | Contenuto |
|---|---|
| `langchain_pg_collection` | raccolte: nome, configurazione JSON |
| `langchain_pg_embedding` | pezzi di testo: vettore, testo, metadati, identificativo del documento |
| `chat_history` | una riga per domanda/risposta |
| `async_jobs` | job: classe di servizio, payload, risultato, lock, tentativi |
| `config` | configurazione modificabile a runtime |

Unici indici: chiavi primarie e unicità della chiave di configurazione.

**Endpoint (33 decoratori nei router)**

| Area | Endpoint |
|---|---|
| Chat e ricerca | `/chat`, `/prompt` (deprecato), `/search`, `/completion` |
| Storico | `/chat_history`, `/chat_history/sessions`, `/evaluate` |
| Raccolte | CRUD su `/collections` |
| Indice | `/index`, `/index/upload`, `/index/link`, `/index/metadata`, lettura e cancellazione documenti |
| Analisi e job | `/summarize`, `/upload_summarize`, `/upload_analyze`, `/jobs`, `/download/{path}` |
| Altro | `/transcribe`, `/config` (lettura, schema, modifica, reset), `/providers`, `/status` |

**Estensioni:** retriever, splitter e servizi dei job caricati per nome di classe. Configurazione da variabili d'ambiente, tabella `config` e JSON della raccolta; il client può sovrascrivere parte della configurazione dei modelli. Formati indicizzabili: PDF, testo, CSV, HTML.

**Problemi noti** (audit dell'8 ottobre 2026 e prove)
- **Sicurezza:**
  - lettura di file arbitrari via `/download`;
  - furto delle chiavi dei modelli via `/chat`;
  - funzioni arbitrarie e SSRF via `/index/link`;
  - storico di tutti gli utenti leggibile;
  - API aperta se `TOKENS_SECRET` è vuoto (default).
- **Dipendenze:** non si installa con le librerie aggiornate. LangChain 0.3 è supportata fino a dicembre 2026; i componenti usati sono in `langchain-classic` e `langchain-community` è in dismissione.
- **Funzionali:**
  - una chiamata al modello in più a ogni domanda;
  - conteggio dei token solo per OpenAI;
  - storico non filtrato per raccolta;
  - stato di streaming condiviso tra richieste.
- **Database:**
  - nessun indice vettoriale;
  - vettori senza dimensione;
  - nessuna entità documento;
  - nome della raccolta non univoco;
  - nessuna struttura per agenti, passi e file prodotti.

---

## 2. Progetti che usano Brevia

Brevia 0.x è usata da alcuni progetti interni (API, chatbot e una piattaforma di test), da portare sulla 1.0 dopo la prima consegna della libreria (§10). I progetti utilizzatori della 1.0 tengono requisiti, integrazione e piani nella propria documentazione: non definiscono il comportamento generale della libreria.

---

## 3. Proposta: Brevia 1.0

**Motivazioni**
1. La base attuale non è più installabile né manutenibile.
2. Le falle di sicurezza derivano da scelte di progetto: vanno eliminate nel progetto.
3. Nuovi casi d'uso non supportati: agenti, output validato, processi a passi in background, tracciamento dei costi.
4. Database senza indici né entità adatte a crescere.
5. Modifiche incompatibili ammesse: i progetti da mantenere sono pochi e interni.

**Obiettivo:** Brevia diventa il **framework interno** per sviluppare software di IA in generale (RAG, servizi, agenti, processi a passi), non solo RAG, mantenendo il pieno controllo della pipeline e la massima configurabilità.

**Vincolo generale confermato:** Brevia 1.0 è indipendente da BEdita e dai domini dei progetti utilizzatori. I frontend possono chiamare direttamente le API di un'applicazione basata su Brevia, oppure passare da un backend (BEdita o altro); il progetto può anche usare la libreria direttamente da Python. Le modalità hanno le stesse capacità e gli stessi controlli del nucleo. Il plugin BEdita è un adattatore opzionale. Le esigenze della prima consegna determinano priorità temporanee, non l'architettura generale.


### 3.1 Riferimento storico e progetto moderno della 1.0

**La vecchia Brevia è il riferimento tecnico e funzionale, non una specifica da replicare.** Il valore da preservare è la capacità di rispondere ai casi d'uso, la configurabilità, l'estensibilità e l'uso come libreria. Nomi, algoritmi, strutture dati, API e modalità di composizione possono evolvere quando rendono la 1.0 più adatta ai programmi IA attuali. L'ammodernamento riguarda anche il modello di utilizzo, non soltanto la sostituzione delle dipendenze.

Per ogni area si legge il codice esistente per capire bisogni e soluzioni, poi si progetta la 1.0 con una motivazione tecnica. Non sono richieste corrispondenze uno a uno dei nomi o fedeltà agli algoritmi precedenti. Le scelte esplicite dell'utente restano ferme, in particolare autenticazione JWT e stack Pydantic AI + DBOS. Le decisioni che cambiano requisiti o perimetro si discutono; non si trasforma ogni dettaglio storico in un vincolo. Compatibilità e migrazione sono lavori distinti, rinviati: eventuali adattatori non devono governare il nucleo nuovo.

**I dimostratori si allineano a Brevia 1.0**, secondo le specifiche qui definite. Il confronto storico aiuta a progettare tali specifiche; non comporta riportare i dimostratori agli algoritmi della 0.x.

Rilettura del 10 ottobre 2026 sul checkout `brevia-ai/brevia`, commit `81ae7d6`, senza modifiche locali. Verifica documentale tramite lettura del codice, senza eseguire test. I percorsi seguenti sono relativi a quel repository.

| Area e codice di riferimento | Capacità e conoscenze di partenza | Ammodernamento o dettaglio da definire |
|---|---|---|
| Libreria e router — `routers/app_routers.py` | Progetto FastAPI che usa Brevia, router separati e funzioni utilizzabili da Python | Adattatori propri sopra Pydantic AI/DBOS; niente dipendenza obbligatoria da BEdita |
| Autenticazione — `tokens.py`, `dependencies.py`, `routers/status_router.py` | JWT, `TOKENS_SECRET`, `TOKENS_USERS`, scadenza, comando di emissione e `STATUS_TOKEN` | Nessun nuovo archivio di token o utenti; politica di accesso sostituibile, separata dall'autenticazione (§7.9) |
| Configurazione — `models.get_model_config`, `settings.py`, `routers/config_router.py` | Default, personalizzazioni per contesto e richiesta; lettura, schema, modifica/reset e controllo delle singole chiamate | Configurazione adatta ad attività, agenti e strumenti; nomi e regole di composizione della 1.0 espliciti (§7.2) |
| Prompt — `prompts.py`, `query.py` | Default nei file, personalizzazioni per raccolta, prompt separati per risposta, riscrittura e riassunto | Rendering indipendente da LangChain, storico delle personalizzazioni DB e snapshot (§7.3) |
| Provider — `models.py`, `providers.py` | Modello/provider configurabili e catalogo dei provider; Ollama locale | Adattatori Pydantic AI e capacità dichiarate; niente alias obbligatori al posto della scelta del modello |
| Ricerca e ingestione — `query.py`, `index.py`, `load_file.py` | Raccolte, numero di risultati, metadati/filtri, file e link, splitter e retriever personalizzabili; opzioni PDF/pagine/OCR da riportare nella specifica dei reader | Nuovo schema documenti/indici, ricerca ibrida, strategie RAG e strumenti di conoscenza (§7.7); acquisizione link controllata |
| Chat e streaming — `routers/qa_router.py`, `query.py`, `callback.py` | RAG e conversazione senza raccolta, lingua, storico passato o caricato per sessione, fonti e risposta progressiva | Composizione esplicita; riscrittura solo con storico. SSE per le nuove API (§9.1), non compatibile con lo stream attuale testo + JSON finale |
| Storico e feedback — `chat_history.py` | Sessioni, domande/risposte, raccolta, metadati, origine, valutazione e commento utente | Conversazioni con messaggi in parti, feedback per esecuzione (§§7.7, 9.0); accesso secondo la politica `per-caller` (§7.9) |
| Servizi e job — `services.py`, `async_jobs.py` | Servizi del progetto con validazione, input, risultato e file; lavori in background | DBOS sostituisce lock/code e gestione della ripresa; attività registrate e schemi tipizzati proposti |
| File — `utilities/output.py` | File scaricabili, filesystem e S3, possibilità di estensione | Identificativi al posto dei percorsi arbitrari, integrità e durata dei file; filesystem per la prima consegna; S3, Azure e file esterni previsti |
| Analisi e audio — `routers/analyze_router.py`, `routers/completion_router.py`, `models.py` | Completamento, riassunto, analisi dei file e trascrizione esistenti | Attività `summarize`, `extract`, `complete` (le prime due nella prima consegna) e modulo di trascrizione con adattatori (§7.7) |
| Consumi e qualità — `callback.py`, `chat_history.py` | Misure dei consumi e feedback già presenti | Estensione oltre OpenAI, cache/costi/tracce, revisioni e dataset Q/A richiesti; training rinviato |

La tabella documenta il riferimento di partenza, non impone la compatibilità completa. Prima di implementare ciascun modulo si definiscono comportamento e dati della 1.0; la mappatura dei vecchi campi serve quando si affrontano adattatori e migrazione. La perdita di una capacità utile va valutata, non confusa con il cambiamento dei suoi nomi o della sua implementazione.

**Licenza:** MIT, come le versioni ≤ 0.15 (P7, decisione del 19 ottobre 2026). Il codice riusato dalla 0.15 mantiene la nota MIT.

---

## 4. Scelte principali

### 4.1 Libreria di base

Decisione P10. Sono state provate quattro librerie sugli stessi dati, con lo stesso modello e le stesse domande.

| | Pydantic AI 2.54 | LangChain 1.4 + LangGraph | LlamaIndex 0.14 | Haystack 3.3 |
|---|---|---|---|---|
| RAG e ricerca vettoriale | equivalenti | equivalenti | equivalenti | equivalenti |
| Agente con strumenti | equivalente | equivalente | equivalente | equivalente |
| Output validato con nuovi tentativi | **sì, 1 chiamata** | sì, 3 chiamate | nessun nuovo tentativo | ciclo da scrivere |
| Limiti su chiamate e strumenti | sì | sì | solo sui giri | solo sui passi |
| Lavori durevoli | **con DBOS (provato)** | LangGraph: stato salvato, worker e ripresa da scrivere | plugin DBOS molto giovane | breakpoint e snapshot |
| Ricerca testuale su pgvector | (di Brevia) | inefficace con domande naturali | **corretta** | inefficace con domande naturali |
| Dipendenze | 32 pacchetti, 78 MB | 57, 163 MB | 77, 234 MB | 49, 128 MB |
| Licenza | MIT | MIT | MIT | Apache-2.0 |
| Versioni | 1.0 set 2025, 2.0 giu 2026; supporto della major precedente 6 mesi | 1.0 ott 2025 dopo 3 anni di 0.x; supporto 1 anno dopo la 2.0 | ancora 0.x: 5 serie in 20 mesi | 2.0 mar 2024, 3.0 lug 2026 |
| Repository GitHub dipendenti | 4.690 | 286.637 (LangGraph 44.958) | 24.823 | 1.516 |

**Perché LangChain è la più diffusa**
- È arrivata per prima, a ottobre 2022, due anni prima di Pydantic AI.
- Ha oltre 1000 integrazioni e uno stack completo (LangGraph, LangSmith a pagamento).
- I download non misurano l'uso: oscillano per installazioni automatiche. A maggio 2026 `pydantic-ai-slim` ha superato `langchain-core` (268 M contro 132 M).

**Per Brevia** l'ampiezza dell'ecosistema pesa poco: i fornitori di modelli usati sono supportati da tutte, la ricerca è implementata in Brevia e i formati sono pochi.

**Strategia proposta**
1. **Pydantic AI come base:** modelli, embedding, agenti, output validato, limiti, ragionamento.
2. **Brevia non espone la libreria ai progetti.** Definisce interfacce proprie (configurazione dei modelli, attività, strumenti, ricerca, splitter, esecuzione); la libreria resta interna. Un cambio di major si assorbe una volta, in Brevia, e la libreria resta sostituibile.
3. **LlamaIndex non è una dipendenza della 1.0.** Ricerca "small to big", riordino e riscrittura multipla sono opzioni della ricerca di Brevia (§7.7). Resta un riferimento: la sua fusione applicata alle due ricerche SQL di Brevia ha dato il risultato migliore di tutte le prove (pezzo giusto al primo posto 73%, tra i primi 4 100%). Valutabile in futuro soltanto per lettori di formati difficili.

**Alternativa esaminata nel confronto:** LangChain 1.x + LangGraph. La scelta per la 1.0 è ora fissata su Pydantic AI + DBOS.

**Stato:** stack confermato per Brevia 1.0: Pydantic AI + DBOS. Le alternative riportate sopra documentano il confronto svolto e non sono una decisione da riaprire in questa fase. LlamaIndex non è incluso (§11.4).

### 4.2 Database e ricerca

- **Postgres 18 + pgvector 0.8.7.** La 0.8 introduce la ricerca iterativa sugli indici: con un filtro, l'indice continua finché trova abbastanza risultati. Supporto di Postgres 18 fino a novembre 2030; la 19 è prevista per il 29 ottobre 2026, da rivalutare prima della produzione. La Brevia attuale funziona senza modifiche su questa combinazione.
- **Schema nuovo** (sezione 8):
  - documento come entità;
  - indici vettoriali e sulle chiavi;
  - JSONB;
  - nomi senza prefisso `langchain_`;
  - tabelle per conversazioni, esecuzioni, eventi, chiamate, file e valutazione; i checkpoint restano gestiti da DBOS.
- **Embedding:** una dimensione fissa per installazione, con modello e dimensione registrati su raccolte e documenti; un cambio di modello avvia un job di ricalcolo. Default proposto: `text-embedding-3-small` a 1536 (pezzo giusto tra i primi 4 nel 92% dei casi contro l'85% di `ada-002`, a circa un quinto del costo).
- **Ricerca ibrida nella 1.0:** vettoriale + testuale (parole in OR, stemming italiano), con fusione dei risultati.

  | Ricerca | Pezzo giusto al 1° posto | Tra i primi 4 |
  |---|---|---|
  | vettoriale | 58% | 85% |
  | testuale | 69% | 96% |
  | fusione | 73% | 100% |

  Cautela: le domande sono state scritte leggendo i testi, il che favorisce la ricerca testuale.
- **Suddivisione dei testi:** gli errori residui derivano da pezzi che mescolano argomenti diversi. Suddivisione per struttura predefinita (§7.7).
- **Ricerca implementata in Brevia**, non con langchain-postgres. Motivi:
  - una tabella per raccolta;
  - nessuna entità documento;
  - il migratore ufficiale fallisce sulle tabelle di Brevia;
  - la ricerca testuale richiede tutte le parole della domanda;
  - versione 0.0.x.

  La ricerca di Brevia dà gli stessi risultati con circa 55 righe.
- **Migrazione dei dati** dei progetti 0.x con uno script. Un progetto che usa `ada-002` può mantenere i vettori esistenti all'inizio.

### 4.3 Esecuzione dei job: DBOS

- **Cos'è:** libreria MIT per l'esecuzione durevole. Workflow e step, con il risultato di ogni step salvato su Postgres; dopo un crash il worker riprende dall'ultimo step completato. Include messaggi tra processi, code e pianificazioni, senza un server dedicato. Integrazione ufficiale con Pydantic AI: ogni chiamata al modello diventa uno step salvato.
- **Provato contro LangGraph:** entrambi riprendono senza ripetere la chiamata al modello e gestiscono l'approvazione. Solo DBOS ha ripresa automatica, stati dei job e code già pronti.
- **Rilasci:** la ripresa è legata alla versione dell'applicazione; procedura «svuota e aggiorna» (§11.5).
- **Da approfondire:**
  - le sue 13 tabelle;
  - frequenza delle major (1.0, 2.0, 3.0 in 16 mesi).

### 4.4 Librerie proposte

| Libreria | Ruolo | Licenza | Download/mese (set 2026) |
|---|---|---|---|
| Pydantic AI | modelli, agenti, output validato | MIT | 24 M |
| Pydantic Evals | valutazione per progetto (da valutare) | MIT | 8 M |
| DBOS | job durevoli | MIT | 2,7 M |
| LlamaIndex (non incluso) | riferimento; eventuali lettori di formati difficili | MIT | 6,7 M |
| PyJWT | token JWT, al posto di `python-jose` della 0.15 (§7.9) | MIT | — |
| FastAPI | API | MIT | 382 M |
| SQLAlchemy + Alembic | database, migrazioni | MIT | 330 M / 179 M |
| psycopg 3 | driver Postgres (richiesto da DBOS) | **LGPL-3.0** (P9) | 134 M |
| pgvector (Python) | tipi vettoriali | MIT | 31 M |
| Postgres + pgvector | database, ricerca | PostgreSQL License | — |

---

## 5. Piano generale e perimetro preliminare

Brevia 1.0 è una libreria generale. Il progetto definisce componenti, dati e API dell'intera versione, mantenendo la vecchia Brevia come riferimento tecnico (§3.1). Il perimetro preliminare seleziona ciò che si realizza prima, senza eliminare le altre funzionalità.

Percorso: definire le specifiche → allineare un dimostratore → realizzare la prima consegna della libreria → completare i moduli (§7.10). Scadenze, input/output e integrazioni di ciascun progetto appartengono alla documentazione del progetto utilizzatore.

**Nucleo preliminare concordato:** configurazione su tre livelli con personalizzazioni facoltative, storico dei prompt e snapshot, adattatori dei modelli, output strutturato, attività registrate, job DBOS, file, JWT esistente, politica di accesso e idempotenza, consumi/tracce e API di avvio/stato/risultato.

**Prima consegna — decisa il 13 ottobre 2026.** Criterio: ciò che serve ai progetti utilizzatori attuali e ciò che sarebbe costoso aggiungere dopo.

| Area | Prima consegna |
|---|---|
| Configurazione, prompt, snapshot; adattatori dei modelli e output strutturato | Sì |
| Attività, job DBOS, file, idempotenza, accessi | Sì |
| Attività di analisi `summarize` ed `extract` | Sì: servono entrambe le possibilità, riportare o riassumere un testo |
| Lettori di documenti (PDF, DOCX, testo) e strumenti file (`read_file`, `save_file`) | Sì: servono alle attività di analisi |
| Limiti per esecuzione (richieste, strumenti, token, tempo) | Sì; budget monetario condiviso rinviato (§7.5) |
| Tracce e consumi | Sì |
| Documentazione delle API: OpenAPI (Swagger UI, ReDoc) e collezione Postman | Sì |
| Feedback strutturato sulle esecuzioni (`POST /runs/{id}/feedback`, §9.0) | Sì: correzioni e giudizi; Brevia non conserva il file finale, il confronto dei documenti è del progetto utilizzatore |
| RAG, conversazioni, strumenti di conoscenza | No |
| Dataset ed esperimenti, trascrizione, indici a grafo | No |

Le funzioni escluse restano nel progetto completo. La migrazione dei vecchi progetti è successiva. Criterio per tutto il consolidamento: in Brevia soltanto capacità minime e generiche utili a più progetti; report di controllo, confronto dei file Office e regole di dominio restano nel progetto utilizzatore. Trasferimento dei file da BEdita (caricamento o adattatore) e notifica di completamento (polling o callback) si decidono all'integrazione: `POST /files` e `GET /runs/{id}` sono comunque nel nucleo.

Le specifiche sono chiuse (§12.2); cosa resta per l'implementazione in §12.1.

---

## 6. Accesso diretto e integrazioni opzionali

Le capacità generiche sono equivalenti nei diversi canali, secondo i moduli abilitati e la configurazione del progetto. BEdita è un'integrazione importante dell'ecosistema, tramite plugin opzionale.

### 6.1 Esempi generali

```text
Frontend → API dell'applicazione basata su Brevia → libreria Brevia

Frontend → BEdita + plugin → API dell'applicazione basata su Brevia
                 ↑                         |
                 └── risultati/callback ────┘

Frontend → altro backend → API dell'applicazione basata su Brevia

Codice Python → libreria Brevia
```

Il backend applicativo mantiene il proprio workflow, utenti, approvazioni e regole di dominio. Brevia esegue attività delimitate: non deve conoscere né replicare il workflow del chiamante. Un workflow DBOS è il processo tecnico interno di un job, distinto dal workflow aziendale del backend. Per il frontend diretto sono disponibili stato, risultati, file e streaming senza obbligo di callback.

### 6.2 Plugin BEdita esistente

Sorgenti di [`brevia-ai/brevia-bedita`](https://github.com/brevia-ai/brevia-bedita) già letti: `BreviaClient.php` gestisce HTTP, token e upload; `BreviaEventHandler.php`, `CollectionHandler.php` e `IndexFileService.php` sincronizzano raccolte/documenti e indicizzano file tramite job BEdita. Il manifest dichiara BEdita `^5.15`, CakePHP `^4.4.1`, PHP `^8.1`, licenza `proprietary`. La compatibilità con altre versioni non è implicita e richiede un adeguamento del plugin.

### 6.3 Estensione del plugin proposta

Client delle API Brevia, correlazione tra oggetto/revisione esterna ed esecuzione, avvio e polling, callback firmata, importazione dei file con retry e deduplicazione, sincronizzazione RAG e inoltro di feedback. Le regole di dominio restano nel progetto utilizzatore. Versioni BEdita supportate e mapping specifici si documentano nelle integrazioni; protocollo riusabile in §9.6.

Anche con database condiviso, ciascun servizio gestisce le proprie tabelle e migrazioni (§8.1). Gli stati di esecuzione Brevia, ricezione/importazione del risultato e approvazione del backend rimangono distinti.

---

## 7. Componenti della 1.0

**Stato:** specifiche chiuse nelle decisioni il 13 ottobre 2026 (§12.2). Le responsabilità e le specifiche seguenti descrivono il progetto da realizzare, non funzionalità già implementate. Stack confermato; migrazione dei progetti 0.x rinviata. Il codice della Brevia 0.15.2 resta il riferimento per comportamenti, configurazione ed estensioni.

**Decisioni confermate:** installazione e database separati per progetto, con più applicazioni chiamanti e token; configurazioni e prompt nei file del progetto, personalizzazioni DB facoltative e storico dei prompt; conservazione configurabile delle richieste/risposte per revisione e analisi; supporto ai modelli locali tramite Ollama. La condivisione fisica del database con BEdita è un'opzione di deployment per singolo progetto (§8.1), non multi-tenancy tra progetti. Filesystem per la prima consegna; deployment definitivo scelto dal progetto.

### 7.1 Moduli e confini

Modalità supportate dal progetto generale:

| Modalità | Accesso alle capacità Brevia |
|---|---|
| Frontend → applicazione FastAPI basata su Brevia | Router pubblicati dal progetto e autenticazione JWT configurabile come oggi; nessun backend BEdita necessario |
| Frontend → BEdita → applicazione Brevia | Stesse API del nucleo tramite plugin; BEdita aggiunge funzioni del proprio dominio |
| Frontend → altro backend → applicazione Brevia | Stesse API e autenticazione JWT; integrazione configurata dal progetto |
| Codice Python → libreria Brevia | Stessi servizi e contesto di esecuzione/accesso, senza obbligo di HTTP |

Stato, file, streaming, prompt, revisioni, esperimenti e feedback devono essere disponibili attraverso le API generiche, senza richiedere tabelle, utenti o callback BEdita. Gli endpoint di dominio restano nel progetto utilizzatore. Equivalenza funzionale non significa accesso indiscriminato: ogni client vede le funzioni e le risorse autorizzate.

| Modulo | Responsabilità e interfaccia | Riferimento nella vecchia Brevia |
|---|---|---|
| `configuration` | Risolvere e validare configurazioni correnti; produrre snapshot senza segreti | `settings.py`, `models.get_model_config` |
| `prompts` | Template nominati, variabili dichiarate, storico delle personalizzazioni, rendering e composizione dei messaggi | `prompts.py`, prompt per raccolta |
| `models` | Generazione, output strutturato, streaming, embedding e adattatori dei provider | `models.py`, `providers.py` |
| `activities` e `tools` | Registrare attività e strumenti generali, schemi e modalità; comporre pipeline e agenti | `services.py`, servizi personalizzati |
| `execution` | Avvio, stato, risultato, limiti e controllo dei job tramite DBOS | `async_jobs.py` |
| `files` | Identità, integrità, accesso e ciclo di vita dei file tramite `Storage` | `utilities/output.py` |
| `documents` | Lettori dei formati e struttura del testo | `load_file.py` |
| `analysis` | `summarize`, `extract`, `complete` | `services.py`, `tasks/`, `completions.py` |
| `knowledge` | Raccolte, documenti, ingestione, splitter, embedding, ricerca, strategie RAG e strumenti di conoscenza | `collections.py`, `index.py`, `load_file.py`, `base_retriever.py`, `query.py` |
| `transcription` | Trascrizione con adattatori | `routers/audio_router.py`, `models.py` |
| `conversations` | Conversazioni e messaggi collegati alle esecuzioni | `chat_history.py` |
| `feedback` | Correzioni e giudizi sulle esecuzioni | `chat_history.py` (`/evaluate`) |
| `tracing` | Chiamate al modello e agli strumenti, tentativi, consumi, cache, costi, errori, durata e tracce | `callback.py` |
| `evaluation` | Dataset revisionati, esperimenti, metriche, revisione ed esportazione | Q/A e confronti del laboratorio |
| `access` e `api` | Autenticazione JWT esistente e router opzionali; politica di autorizzazione sostituibile | `tokens.py`, `dependencies.py`, `routers/` |

Le funzioni sono utilizzabili da Python e via HTTP. I router validano il trasporto e invocano i servizi: non contengono pipeline o regole di dominio. Pydantic per gli schemi pubblici è ammesso; oggetti e classi di Pydantic AI e DBOS rimangono dietro adattatori Brevia.

Le interfacce pubbliche comprendono `Brevia`, `RunContext`, `ModelRequest/ModelResult`, definizioni di attività e strumenti, `FileRef`, `SearchQuery/SearchResult` e interfacce per reader, splitter, retriever, storage ed evaluator. Firme della prima consegna in §7.5, organizzazione del codice in §11.4; nomi definitivi in implementazione.

### 7.2 Configurazione del progetto e snapshot

**Decisione di semplificazione:** Brevia è una libreria usata da un progetto, non richiede una piattaforma di pubblicazione delle configurazioni. Default nel codice/file versionati con Git; personalizzazioni DB facoltative; override ammessi della richiesta. Nessun catalogo di default versionati, revisione iniziale obbligatoria o passaggio separato di attivazione.

La vecchia Brevia resta riferimento per personalizzazione del contesto, configurazione per ogni uso del modello, lettura/schema/modifica/reset. La 1.0 rende esplicita la composizione e conserva quanto effettivamente usato nelle esecuzioni.

| Aspetto | Regola |
|---|---|
| Precedenza | Default del progetto → personalizzazione corrente del contesto → override ammessi della richiesta |
| Composizione | Campo assente eredita; scalari/liste presenti sostituiscono; oggetti strutturati composti per campi secondo schema. Mappe libere sostituite salvo regola dichiarata. Nessuna fusione universale |
| `null` e reset | `null` è un valore solo se ammesso. Reset rimuove la personalizzazione e torna ai default correnti; nessuna revisione da attivare |
| Modifica | Valori validati e salvati nel DB, immediatamente disponibili alle nuove esecuzioni. Nessuna scrittura DB necessaria per usare solo i file |
| Concorrenza | Versione del record confrontata atomicamente durante modifica/reset via API, per evitare aggiornamenti persi. Non è un catalogo di revisioni |
| Vincoli | Segreti, endpoint fidati e implementazioni registrate fuori dagli override. Budget e permessi imposti dall'installazione non ampliabili dalla richiesta |
| Deploy | I nuovi default possono cambiare le nuove esecuzioni nei campi non personalizzati; lo snapshot protegge quelle già avviate. Nessun blocco automatico sui vecchi default |

Ogni attività dichiara schema e campi personalizzabili, anche per singole operazioni. Raccolta, attività e agente non introducono una catena implicita di precedenze: il progetto dichiara il contesto utilizzato. Campi ignoti o incompatibili respinti; opzioni provider validate dall'adattatore. Nomi e payload finali restano da fissare senza obblighi derivati dalla 0.x.

**Snapshot per esecuzione:** copia dei valori effettivi, template/istruzioni effettivamente selezionati, identificativi dei prompt storicizzati quando disponibili, versione del codice/attività e formato dello snapshot. Nessun segreto. La ripresa non ricostruisce i valori dai default correnti o da una catena di revisioni. Decisione del 14 ottobre 2026 (audit): i valori serializzati dello snapshot possono non ricostruire la stessa configurazione (campi esclusi dalla serializzazione, serializzatori personalizzati), quindi lo snapshot resta una registrazione e non è la fonte della ripresa. Un job risolve configurazione e prompt nel worker, nel primo step DBOS, dai valori registrati (input, override, personalizzazione); la ripresa li rilegge dal checkpoint di quello step; un `retry` riparte dagli stessi input e override e risolve di nuovo configurazione e prompt con le personalizzazioni presenti al suo avvio (decisione del 15 ottobre 2026: chi corregge una personalizzazione dopo un fallimento la ritrova nel rilancio). Gli override dei job devono avere forma JSON, come l'input. Scartata una prima soluzione che registrava gli ingressi della risoluzione nello snapshot e li ricostruiva: rompeva chiamate dirette con override senza forma JSON e richiedeva casi speciali (NUL, schemi rigidi, valori `Any`). Ogni chiamata al modello registra le opzioni effettive (ragionamento, temperatura, token massimi). Le chiamate dinamiche registrano i prompt renderizzati e le scelte effettive secondo la politica delle tracce; i dati necessari alla ripresa restano disponibili per tutta la sua finestra.

Per un job la sottomissione verifica che configurazione e prompt si risolvano; la lettura che fa fede avviene nel primo step DBOS del worker, conservata nel checkpoint e nello snapshot; un job accodato usa le personalizzazioni presenti al suo avvio. Una chiamata diretta legge tutto all'avvio; un errore del DB usato per le personalizzazioni non autorizza il fallback silenzioso ai file. La configurazione risolta non viene mutata dai loader. Strategia iniziale confermata: file caricati all'avvio, personalizzazioni DB lette per ogni nuova esecuzione e poi conservate nello snapshot; nessuna cache condivisa delle impostazioni modificabili. Eventuali ottimizzazioni future devono verificare la versione, non assumere invalidazione tra processi. I file distribuiti sono immutabili durante la vita del processo; un aggiornamento richiede il rilascio/riavvio coerente di API e worker.

#### 7.2.1 Esempi e dettagli residui

**Analisi documentale:** file con modello A, limite 1.200 token e lingua italiana; personalizzazione DB del limite a 1.800; richiesta autorizzata in inglese. Il job salva modello A/1.800/inglese. Reset del limite: i nuovi job ereditano 1.200, quello già avviato conserva 1.800. Un deploy che cambia il default a 2.000 vale per i nuovi job senza override.

**RAG:** il progetto configura ricerca ibrida, limite 8, riscrittura facoltativa e modello di risposta. Una raccolta può personalizzare il limite a 12; una richiesta può cambiare la lingua se ammesso. Filtri di autorizzazione non sono sovrascrivibili dai filtri utente. Per agenti dinamici si dichiarano capacità e limiti, senza elencare in anticipo ogni chiamata.

**Prompt modificabile:** file del progetto come base; un salvataggio API crea/aggiorna la personalizzazione corrente nel DB e conserva lo storico. I nuovi job usano il nuovo contenuto; quelli in ripresa usano lo snapshot. Ripristino di una versione precedente come nuova modifica corrente; reset torna al file senza cancellare lo storico.

Da precisare in implementazione: schema dei valori per modulo, payload di modifica/reset e formato dello snapshot. Errori nel catalogo di §9.1. Anteprima della risoluzione utile ma facoltativa, senza inferenza e senza prenotare i valori per un successivo avvio.

### 7.3 Prompt, cache e storico

Prompt nei file del progetto; personalizzazione DB facoltativa con storico per confronto e ripristino. Il salvataggio cambia direttamente il valore corrente per i nuovi job; nessuna attivazione separata o associazione obbligatoria tra revisioni di configurazione e prompt. Il confronto legacy e le proposte residue sono in §12.2.

Un template ha nome, variabili obbligatorie/facoltative e contenuto; lo storico DB identifica le modifiche quando presente, senza revisione iniziale obbligatoria per i file. Un'attività dichiara quali template usa. Confermata la sostituzione semplice di variabili dichiarate dal codice: niente cicli, condizioni o esecuzione arbitraria nei template iniziali. Variabili obbligatorie mancanti, nomi sconosciuti e personalizzazioni incompatibili con lo schema sono errori; i valori inseriti non vengono interpretati nuovamente come template. Le variabili facoltative sono da introdurre con una sintassi dichiarata al primo caso concreto. L'anteprima non chiama il modello. Nuove variabili obbligatorie richiedono l'adeguamento del codice chiamante; contenuti della richiesta e istruzioni restano distinti.

Confermata anche la lettura API distinta di default, personalizzazioni, valori effettivi, schema e versione del record; i segreti restano esclusi. Il DB conserva soltanto le personalizzazioni. Il comportamento del blocco configurazioni/prompt è approvato; nomi e payload finali saranno consolidati insieme alle interfacce Python/API e ai moduli, senza riaprire queste decisioni.

Composizione esplicita: istruzioni stabili, schema/strumenti, materiale condiviso, dati specifici della richiesta. Ordine e serializzazione devono essere stabili; timestamp, UUID e valori variabili non entrano nei blocchi riusabili se non necessari. L'adattatore applica le opzioni di cache supportate dal provider/modello; il prefisso stabile è un criterio di costruzione, non una garanzia di hit.

Metriche separate, aggregate per provider, modello, attività e revisione del prompt:
- token input, output, letti dalla cache e scritti in cache quando disponibili;
- quota token da cache = somma dei token letti dalla cache / somma degli input, sulle richieste con misure compatibili e note;
- quota richieste con cache = richieste con lettura cache positiva / richieste con metrica disponibile;
- copertura delle metriche, durata e costo stimato, con listino e data usati.

Un valore non comunicato dal provider resta `null`, non zero. I contatori normalizzati conservano anche la misura originale e la sua provenienza. Token di ragionamento e cache possono essere sottoinsiemi di contatori totali: il calcolo non li somma due volte. Eventuali risparmi stimati sono distinti dai consumi osservati.

Il caching del provider è distinto dalla cache interna delle impostazioni e dal riuso delle risposte: nessuna cache generale delle risposte IA nel nucleo iniziale. Ordine effettivo di strumenti/messaggi, requisiti, durata e opzioni di caching dipendono dall'adattatore e dal modello, senza un ordine universale imposto dal nucleo. Lo snapshot supporta diagnosi e ripresa, non garantisce risposte generative identiche. La scalabilità di questa impostazione è una valutazione progettuale, da misurare successivamente; nessun requisito iniziale di cache distribuita.

Verifica delle fonti ufficiali dell'11 ottobre 2026: [caching Anthropic](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [caching OpenAI](https://developers.openai.com/api/docs/guides/prompt-caching), [impostazioni Pydantic AI](https://pydantic.dev/docs/ai/api/pydantic-ai/settings/). Confermano la necessità di prefissi compatibili e gestione specifica per provider; non attestano prestazioni della futura implementazione.

### 7.4 Modelli, provider e sistemi futuri

**Perimetro iniziale concordato:** OpenAI, Anthropic e Ollama attraverso Pydantic AI; modelli concreti e capacità richieste scelti dal progetto. Nessun fallback implicito: ogni cambio deve essere configurato e tracciato. Costi sconosciuti indicati come tali, mai zero; una politica di budget monetario richiede prezzi disponibili, pur restando una stima e non una garanzia sulla fattura.

**Predisposizione concordata:** registro di adattatori estendibile dal progetto, con interfacce Brevia indipendenti dal trasporto e dalle classi di Pydantic AI. Pydantic AI è l'implementazione iniziale concordata; un futuro provider o motore locale può avere un adattatore dedicato senza cambiare attività, file, revisioni e consumi. Non si promette compatibilità automatica con sistemi non ancora verificati.

- Separare generazione, embedding e trascrizione: un adattatore può offrire solo alcune capacità. Prevedere contenuti tipizzati estendibili a immagini/audio e risultati strutturati, senza implementare ora tutte le modalità.
- Parametri comuni minimi e opzioni specifiche del provider validate dal suo adattatore; ragionamento, limiti e incompatibilità non si deducono da prefissi del nome del modello nel nucleo.
- Endpoint, credenziali e impostazioni del trasporto appartengono alla configurazione fidata. Un protocollo compatibile con OpenAI non garantisce le stesse capacità: dichiararle per adattatore/modello e rifiutare le richieste non supportate.
- Errori, streaming, annullamento, timeout e consumi espongono forme comuni, conservando i dettagli originali utili. Capacità o contatori non disponibili restano espliciti; niente valori inventati.
- Nello snapshot registrare identificativo dell'adattatore e versione dello schema delle sue opzioni; cambi di implementazione devono poter rileggere le configurazioni e i job pendenti o dichiarare una conversione.

**Confronto con il codice:** la 0.x consente classi di modello configurabili (`models.py`) ma il catalogo provider è una mappa statica (`providers.py`). Conservare l'estensibilità senza importare classi da input non fidati. Nel prototipo delle interfacce i vincoli su ragionamento e temperatura sono capacità dichiarate per modello nell'installazione e verificate dall'adattatore, non dedotte dal nome del modello.

`ModelRequest` comprende messaggi renderizzati, modello/provider, parametri, schema di output, strumenti ammessi e budget. `ModelResult` comprende output, riferimenti alle chiamate, consumi ed esito della validazione. La stessa infrastruttura raccoglie tentativi riusciti e falliti.

**Semplicità confermata:** lo strato Brevia resta piccolo e cura configurazioni, autorizzazioni, snapshot e tracciamento. Schemi degli strumenti, ciclo del modello e validazione sono delegati a Pydantic AI dove disponibili, senza riscriverne il framework. Nomi descrittivi di modello sono riferimenti configurati dal progetto, non un catalogo universale da mantenere. Si verificano le capacità richieste dei modelli configurati; incompatibilità non anticipabili sono gestite esplicitamente alla risposta del provider. Le interfacce comuni non promettono equivalenza di tutte le funzionalità dei provider.

Ogni adattatore dichiara le capacità effettive (streaming, strumenti, output strutturato, ragionamento, embedding e contatori): parametri non supportati vengono respinti o trasformati con una regola esplicita, mai ignorati silenziosamente. La politica di fallback è configurabile e ogni cambio di modello è tracciato; default: nessun fallback implicito.

**Ollama è parte del progetto 1.0**, mantenendo l'uso locale già presente in `brevia/providers.py`, `models.py` e `tests/test_models.py`. Le capacità vanno verificate per il modello scelto. Salvare identificativo e versione/digest quando disponibili: un tag locale da solo può cambiare nel tempo. Per i modelli locali il costo infrastrutturale stimato, se configurato, è distinto dal prezzo del provider e non è assunto nullo.

La documentazione corrente di Pydantic AI include [Ollama](https://pydantic.dev/docs/ai/models/ollama/); l'adattatore dovrà usare le API della versione fissata nel progetto, senza imporre aggiornamenti solo per seguire la documentazione corrente. Ollama documenta l'[importazione di modelli Safetensors/GGUF](https://docs.ollama.com/import). L'addestramento e la conversione dei modelli restano una futura integrazione distinta dall'inferenza locale.

### 7.5 Attività, strumenti ed esecuzione

**Regole concordate:** attività registrate con nome, versione e schemi Pydantic di input/output; strumenti e capacità eseguibili registrati, con selezione dinamica entro quell'insieme. DBOS resta l'unico responsabile dell'esecuzione durevole dei job; il loro stato pubblico viene derivato e riconciliato. Retry limitati con attese crescenti per errori temporanei; input/configurazione invalidi terminano subito. Correzione dell'output separata dai retry di rete. Successo solo dopo validazione e pubblicazione degli artefatti; annullamento cooperativo senza annullamento automatico degli effetti esterni già prodotti. Ogni job resta associato alla versione dell'applicazione con cui è partito; rilasci con procedura «svuota e aggiorna» (§11.5). Sospensione e approvazione umana predisposte, da realizzare al primo caso concreto.

**Orientamento della 1.0:** chiamata semplice, pipeline deterministica e agente con ciclo dinamico di strumenti sono forme di utilizzo native. Si sceglie quella adatta al compito; il vecchio RAG non determina l'architettura di tutte le attività. Un agente può scegliere strumenti e passi entro limiti dichiarati; una pipeline può includere agenti e viceversa.

**Terminologia approvata e da esplicitare nella documentazione della libreria:**

| Concetto | Responsabilità |
|---|---|
| Funzione | Operazione ordinaria del codice, per esempio leggere dati o calcolare un valore |
| Attività | Funzionalità applicativa con input/output definiti; implementata mediante funzioni, chiamate IA ed eventuali agenti |
| Agente | Componente che usa il modello per scegliere passi o strumenti entro obiettivo, permessi e limiti stabiliti |
| Strumento | Funzione esposta al modello con descrizione, parametri e autorizzazioni; la stessa funzione può essere chiamata direttamente dal codice |
| Job | Esecuzione durevole di un'attività, con identificativo, stato e ripresa |

Le attività possono essere deterministiche, usare IA con percorso definito oppure includere decisioni agentiche; queste modalità sono combinabili e non impongono tre gerarchie di classi. L'applicazione invoca l'attività direttamente o come job; il codice dell'attività usa le funzioni, i modelli e gli eventuali agenti necessari. Uno strumento non richiede un agente complesso. Un job non è necessariamente agentico e un agente non richiede necessariamente un job. Il nome tecnico `Agent` di Pydantic AI non implica autonomia decisionale: può servire anche una semplice richiesta strutturata. DBOS governa i job durevoli, non ogni funzione ordinaria.

**Documentazione come requisito di sviluppo:** fornire una spiegazione breve di questa relazione e tre esempi minimi (attività deterministica, chiamata IA strutturata, agente con strumenti), mostrando anche quando usare un job. Documentare input/output, errori, effetti esterni e limiti insieme alle funzionalità implementate; mantenere esempi e riferimenti coerenti con le API reali. Separare capacità disponibili e pianificate, e spiegazione generale ed esempi dei progetti utilizzatori. Chiarezza e concisione sono requisiti, non una fase facoltativa dopo lo sviluppo.

Il disegno comprende output strutturati validati, strumenti tipizzati anche collegati a servizi esterni, contesto composto da messaggi/file/risultati degli strumenti, streaming di eventi, limiti e interruzioni, esecuzioni durevoli, eventuale intervento umano e valutazione delle tracce. Selezioni dinamiche di modelli e strumenti restano entro la configurazione approvata e vengono registrate per ogni chiamata: lo snapshot iniziale conserva regole e revisioni, non predetermina tutte le decisioni dell'agente.

Collaborazione tra agenti, protocolli per strumenti remoti e sistemi di agenti gestiti dai provider restano estensioni possibili tramite adattatori; non diventano dipendenze obbligatorie né funzionalità dichiarate già disponibili. Per la prima versione si definisce un sottoinsieme concreto senza impedirne l'evoluzione. I criteri sono utilità, controllo, verificabilità e semplicità d'uso, non la sola novità della tecnologia.

Un'attività dichiara nome, versione del contratto, schemi input/output/configurazione, modalità supportate (`direct`, `job`) e possibilità di streaming, strumenti, limiti e implementazione registrata. Pipeline e agenti condividono questo contratto; una pipeline può usare un agente in un passo. Il DB personalizza implementazioni esistenti: non contiene classi da importare o workflow Python da eseguire.

Uno strumento è una funzione tipizzata registrata, con autorizzazioni e indicazione degli effetti esterni. Il progetto definisce idempotenza, chiave dell'operazione e gestione degli errori per gli effetti esterni. Ricerca/lettura documenti sono generiche; lettori e generatori specifici di dominio appartengono al progetto utilizzatore.

**Regole operative approvate per gli strumenti:** nome e descrizione chiari, input/output tipizzati, implementazione registrata, timeout e limiti applicabili. Il modello fornisce soltanto gli argomenti esposti; dipendenze, identità e permessi provengono dal codice fidato e sono verificati all'esecuzione. Letture rispettano gli accessi alle risorse; scritture e pubblicazioni richiedono protezione dai duplicati nei retry. Le approvazioni umane sono previste solo dalla politica dell'operazione e verificate dal codice prima dell'effetto, non decise dal modello. Le funzioni restano richiamabili direttamente dal codice.

#### Strumenti generali — decisione del 13 ottobre 2026

Uno strumento è una funzione Brevia tipizzata, registrata una volta e usata dal codice, dagli endpoint (per esempio `POST /search`) e dagli agenti. Tre famiglie:

| Famiglia | Strumenti | Stato |
|---|---|---|
| Generali Brevia — conoscenza | `search` (vettoriale, testuale, ibrida; filtri; espressione logica per la testuale), `list_documents`, `open` (sezione o intervallo di un documento), `find` (testo esatto o pattern in un documento) | 1.0 |
| Generali Brevia — grafo | Esplorazione di entità e relazioni | Previsto con gli indici a grafo (§7.7) |
| Generali Brevia — file | `read_file` (testo e struttura di un file), `file_info`, `save_file` (effetto in scrittura, §7.6) | 1.0 |
| Generali Brevia — web | `fetch_url` controllato: solo http/https, domini ammessi, timeout | 1.0, disattivato di default |
| Generali Brevia — intervento umano | Richiesta di approvazione con sospensione (`waiting`) | Al primo caso concreto |
| Attività come strumenti | Ogni attività registrata può essere offerta a un agente: riassunto, estrazione strutturata, trascrizione | 1.0 |
| Progetto ed esterni | Strumenti di dominio registrati dal progetto; server MCP tramite Pydantic AI | 1.0 come estensione |

Con molti strumenti si usa il caricamento differito di Pydantic AI (`DeferredLoadingToolset`). Esclusi dalla 1.0: esecuzione di codice arbitrario (i calcoli restano funzioni deterministiche del progetto) e ricerca web generica, eventualmente tramite strumenti nativi dei provider quando un progetto la richiede. Fonte: [toolset Pydantic AI](https://pydantic.dev/docs/ai/tools-toolsets/toolsets/).

Risposte degli strumenti contenute e pertinenti: filtri, paginazione e limiti di dimensione quando necessari; ricerche restituiscono estratti e riferimenti invece di interi archivi. Troncamenti e risultati parziali sono espliciti e indicano come ottenere ulteriori dati. Nessuna introduzione obbligatoria di sistemi multiagente o protocolli remoti.

I limiti distinguono richieste al modello, invocazioni degli strumenti, token e tempo; includono tentativi e operazioni concorrenti secondo regole da fissare in implementazione. Superare un limite interrompe l'esecuzione con motivo preciso; risultati parziali solo se previsti dall'attività e dichiarati incompleti. Alcuni consumi sono conosciuti dopo la risposta: non si promette un tetto preventivo esatto ai token o alla spesa. Un timeout non garantisce l'annullamento di effetti esterni già avvenuti. Retry HTTP, Pydantic AI e DBOS devono avere responsabilità e limiti coordinati, senza moltiplicazioni implicite. Scalabilità da verificare con concorrenza controllata e limiti dei provider, non dedotta dal solo numero di worker.

Fonti primarie della revisione: [strumenti](https://pydantic.dev/docs/ai/tools-toolsets/tools/), [dipendenze](https://pydantic.dev/docs/ai/core-concepts/dependencies/), [approvazioni](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/), [limiti](https://pydantic.dev/docs/ai/api/pydantic-ai/usage/) e [retry Pydantic AI](https://pydantic.dev/docs/ai/core-concepts/retries/); [semplicità degli agenti](https://www.anthropic.com/engineering/building-effective-agents) e [efficienza degli strumenti](https://www.anthropic.com/engineering/writing-tools-for-agents). Validazione progettuale, non evidenza di prestazioni o compatibilità della versione da installare.

DBOS è l'unico motore dei job. Brevia registra input, snapshot, identità del chiamante, versione del codice, risultato e collegamenti ai file; non replica code, lock e checkpoint. Stati API: `queued`, `running`, `succeeded`, `failed`, `cancelled`, più `waiting` quando sarà introdotta la sospensione per intervento umano; nessuno stato separato per una richiesta di annullamento (decisione del 15 ottobre 2026): l'annullamento si registra subito e ferma il job in corso entro circa un secondo (vedi più avanti).

Un job interrotto con il suo worker riparte da capo, da solo, con la configurazione e i prompt risolti al primo avvio (decisione del 15 ottobre 2026): le chiamate al modello dell'esecuzione persa si rifanno e si ripagano, e non vengono registrate; si registrano esito e chiamate dell'esecuzione che arriva in fondo. Un job riparte al massimo 3 volte, poi fallisce. Scartata la ripresa dall'ultima chiamata completata: chiamate durevoli, contatori delle esecuzioni perse, costi sconosciuti e controllo che la chiamata ripresa sia uguale erano la fonte principale della complessità dei job, per un risparmio che si ha solo quando un worker si ferma. L'attività di un job può quindi essere eseguita più volte: effetti esterni protetti da idempotenza. Retry del provider, dell'output e degli step sono coordinati per evitare moltiplicazioni. Nella prima consegna limiti per esecuzione: richieste, strumenti, token e tempo. Un budget monetario condiviso tra esecuzioni collegate, con prenotazione sotto concorrenza, è rinviato a un'esigenza concreta; un limite monetario resta una stima e richiede prezzi noti.

Le attività dichiarano quali modalità supportano; non tutte sono streamabili. Una disconnessione HTTP non annulla implicitamente un job. Le elaborazioni Office bloccanti vengono eseguite nei worker con concorrenza limitata. Rilasci secondo §11.5.

Per altri progetti è previsto `waiting` con richiesta di intervento e risposta tipizzata, identificativo e scadenza. Un progetto può separare proposta e generazione in due attività e gestire la conferma nel proprio backend. Una nuova esecuzione dopo fallimento è collegata alla precedente; la ripresa da crash resta interna a DBOS.

#### Esempio approvato: attività di sintesi con prompt del progetto

Comportamento concordato, scritto con le firme della prima consegna (sotto); nomi definitivi in implementazione. Registrazione esplicita nel codice del progetto, senza scoperta automatica di file o import di classi dal DB.

Il progetto contiene `summary.py` (schemi e funzione), `prompts/summary.md` (istruzioni) e `app.py` (registrazione e utilizzo). Il prompt contiene:

```text
Riassumi il documento nella lingua {language}.
Conserva i fatti principali, i numeri e le incertezze.
Non aggiungere informazioni assenti dal documento.
```

Schemi e funzione illustrativi in `summary.py`:

```python
from pydantic import BaseModel, Field
from brevia import RunContext  # Interfaccia della prima consegna, non ancora implementata.


class SummaryRequest(BaseModel):
    text: str = Field(min_length=1)
    language: str | None = None


class SummaryConfig(BaseModel):
    model: str
    max_output_tokens: int = Field(default=1200, gt=0)
    language: str = 'it'


class SummaryResult(BaseModel):
    summary: str


async def summarize(request: SummaryRequest, ctx: RunContext) -> SummaryResult:
    language = request.language if request.language is not None else ctx.config.language
    return await ctx.model().generate(
        instructions=ctx.prompt('summary').render(language=language),
        user_text=request.text,
        output_type=SummaryResult,
        max_output_tokens=ctx.config.max_output_tokens,
    )
```

`SummaryRequest` descrive la richiesta della singola esecuzione; `SummaryConfig` le impostazioni dell'attività; `SummaryResult` il risultato. Qui `language=None` significa esplicitamente nessuna preferenza nella richiesta, non reset della configurazione. La possibilità di cambiare lingua deve essere autorizzata dalla definizione dell'attività.

Registrazione e chiamata illustrative in `app.py`:

```python
from brevia import Brevia
from summary import SummaryConfig, SummaryRequest, SummaryResult, summarize

brevia = Brevia.from_settings()
brevia.register_activity(
    name='summarize',
    version='1',
    function=summarize,
    input_type=SummaryRequest,
    output_type=SummaryResult,
    config_type=SummaryConfig,
    prompts={'summary': 'prompts/summary.md'},
    modes={'direct', 'job'},
)


async def main():
    result = await brevia.run(
        'summarize',
        SummaryRequest(text='Il documento da riassumere...'),
    )
    print(result.summary)
```

Il modello concreto (`SummaryConfig.model`) è un default della configurazione del progetto; provider e credenziali appartengono all'installazione. L'esempio non definisce una configurazione d'installazione completa.

Prima della chiamata Brevia valida input e override, risolve configurazione e prompt (file o personalizzazione DB), conserva lo snapshot e fornisce alla funzione le dipendenze previste. Registra log/consumi e valida il risultato. Modificare il prompt via API non modifica la funzione se le variabili restano compatibili. È una chiamata IA a percorso definito, senza strumenti o scelte agentiche. L'avvio `await brevia.submit("summarize", request)` restituisce invece un job, se l'attività supporta l'esecuzione durevole; le regole di esecuzione sono definite di seguito.

#### Firme Python della prima consegna — decisione del 13 ottobre 2026

L'attività riceve un unico contesto `ctx`, così nuove capacità non cambiano la firma delle attività già scritte. Nomi definitivi da confermare in implementazione.

```python
from brevia import Brevia, RunContext

brevia = Brevia.from_settings()  # ambiente/.env e file del progetto

brevia.register_activity(
    name='document.summarize',
    version='1',
    function=summarize,  # async def summarize(request: In, ctx: RunContext) -> Out
    input_type=In,
    output_type=Out,
    config_type=Cfg,  # campi personalizzabili e default
    prompts={'summary': 'prompts/summary.md'},
    modes={'direct', 'job'},
)

result = await brevia.run('document.summarize', In(...))  # diretta → Out
handle = await brevia.submit('document.summarize', In(...), idempotency_key='...')  # job → RunHandle
output = await handle.result()

app = brevia.create_app()  # FastAPI con i router Brevia selezionabili
```

`RunContext` espone `config` (risolta e validata), `prompt(nome).render(...)`, `model()` con `generate(...)` e `run_agent(...)`, `files` (lettura e salvataggio), `tools` e `log`.

#### Chiamata diretta, job e avanzamento — decisioni del 12 ottobre 2026

Riferimento legacy riletto: `brevia/services.py`, `async_jobs.py` e `routers/jobs_router.py`. Conservare la separazione fra operazione applicativa e gestione del job, con risultato e identificativo consultabile; lock e recupero artigianali sono sostituiti dal motore durevole concordato.

- **Chiamata diretta:** esegue l'attività e restituisce risultato tipizzato o errore; non richiede DBOS e non riparte automaticamente dopo un arresto. Tracciamento e conservazione seguono la configurazione dell'installazione; registrare una chiamata non la rende durevole. Nessuna conversione automatica in background.
- **Job durevole:** restituisce un identificativo dopo accettazione persistente e accodamento; conserva input, snapshot e risultato, con ripartenza da capo affidata a DBOS. L'attività mantiene input/output ma deve sopportare una ripetizione dei propri effetti esterni.
- **Attesa e streaming:** aspettare per un tempo limitato il risultato di un job non cambia la sua natura; alla fine dell'attesa il chiamante conserva lo stesso identificativo. La disconnessione del client non annulla il job accettato. Streaming è una modalità di consegna, distinta dalla durabilità, disponibile solo dove supportata; firme e combinazioni si consolidano nelle API.

Stati pubblici iniziali dei job: `queued` (accettato e in attesa), `running` (in corso, inclusi retry automatici), `succeeded` (risultato validato e artefatti pubblicati), `failed` (errore terminale), `cancelled` (annullato prima della fine). L'annullamento si registra subito, senza stato intermedio; un job in corso si ferma entro circa un secondo, anche durante una chiamata al modello; le chiamate fatte fino a quel momento si registrano con il job e gli effetti già prodotti non vengono annullati. Timeout e limiti esauriti sono motivi espliciti di fallimento. `waiting` sarà introdotto con la sospensione per intervento umano. Il raccordo con gli stati DBOS va precisato senza introdurre un secondo motore.

Retry automatico di un'operazione e ripartenza dopo arresto restano nello stesso job, con limiti coordinati e snapshot originale. Il rilancio applicativo esplicito dopo fallimento o annullamento crea un nuovo job collegato con gli stessi input e override, senza copiare i checkpoint; configurazione e prompt si risolvono di nuovo al suo avvio (§7.2). Modifiche a input o override richiedono un nuovo avvio. Effetti esterni già avvenuti richiedono protezioni dai duplicati anche nel rilancio; recupero e comandi amministrativi DBOS restano distinti dall'API applicativa di rilancio.

**`stalled`: segnalazione diagnostica, non stato di esecuzione.** Indica mancato avanzamento osservato oltre una soglia configurabile per attività, con motivo, ultimo avanzamento noto e orario dell'osservazione. Può accompagnare un job non terminale; non dimostra da sola un blocco effettivo. Attese previste (pausa, approvazione, intervallo di retry) non producono questa segnalazione. Scompare quando riprende l'avanzamento e non causa automaticamente retry, riavvio o annullamento. Un timeout effettivamente raggiunto segue la politica di fallimento. Fonti dell'avanzamento, soglie e rilevazione restano da definire; nessuna deduzione di blocco dal solo tempo trascorso dall'ultimo log.

Riferimento consultato: [stati e gestione DBOS](https://docs.dbos.dev/python/reference/client). `stalled` non è uno stato nativo del motore; la diagnostica Brevia non sostituisce la sua autorità sui job. Prova del 14 ottobre su dbos 3.2.0 con la libreria: un job accodato è `ENQUEUED`, in corso o interrotto `PENDING`, poi `SUCCESS`, `ERROR` o `CANCELLED`. Con la ripartenza da capo (decisione del 15 ottobre 2026) il run di un job è un unico step DBOS interrompibile: l'annullamento si registra in `runs` prima di fermarlo nel motore, il run si ferma entro circa un secondo e aggiunge le sue chiamate al job annullato; la lettura dello stato riconcilia `runs` dallo stato DBOS.

### 7.6 File e storage

`Storage` espone lettura, metadati e pubblicazione; cancellazione e collegamenti di download sono capacità aggiuntive soggette a supporto e permessi. Casi base concordati per lettura e salvataggio: **filesystem persistente, BEdita tramite integrazione API/plugin, S3 compatibile e Azure Blob Storage**, servizio di object storage di Azure ([Microsoft](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blobs-introduction)). L'interfaccia non assume un protocollo S3 universale. Filesystem persistente per la prima consegna; adattatori cloud prima del deployment che li richiede. Il vecchio `LinkedFileOutput` contiene filesystem e S3; Azure è un'estensione prevista, non già implementata o verificata.

Il progetto può aggiungere altri sistemi mediante adattatori registrati nel codice fidato, senza modificare le attività o introdurre diramazioni per provider nel nucleo. BEdita è un caso base previsto ma resta una dipendenza opzionale: l’accesso riguarda risorse e media attraverso la sua integrazione, non l’accesso diretto al suo bucket. Le operazioni comuni coprono lettura e salvataggio; le firme definitive restano da consolidare. Questo requisito non implica che gli adattatori siano già implementati.

Ogni file pubblicato ha UUID, impronta, dimensione e MIME; il nome originale è descrittivo e non determina il percorso. Dimensione massima e tipi ammessi dei caricamenti sono configurabili per installazione (i modelli Office possono superare i 30 MB); oltre il limite errore `file_too_large`. Il contenuto è immutabile: una correzione produce un nuovo file. `FileRef` è indipendente dal backend storage. Il download è autorizzato per identificativo; input e output rimangono disponibili per tutta la finestra di ripresa e conservazione. Pulizia e pubblicazione devono gestire anche file orfani o upload incompleti.

Distinguere file gestiti da Brevia e file gestiti da sistemi esterni. Per BEdita lettura e salvataggio passano dall'integrazione tramite API/plugin, rispettando permessi e gestione dei media: Brevia non deve conoscere lo storage sottostante. Anche con bucket condiviso si usano namespace e autorizzazioni separate; nessuna cancellazione dei file dell'altro servizio.

I riferimenti esterni identificano sistema, risorsa e versione o checksum; disponibilità e stabilità del contenuto devono essere garantite per la ripresa. Una URL temporanea è un mezzo di accesso, non l'identità del file. Quando queste garanzie mancano, conservare una copia immutabile per l'esecuzione. Il backend applicativo gestisce documenti definitivi e approvazioni; conservazione e cancellazione delle copie Brevia seguono una politica esplicita. Formato dei riferimenti e gestione dei trasferimenti restano da dettagliare.

#### FileRef e operazioni comuni — decisioni del 12 ottobre 2026

`FileRef` identifica il file e la connessione configurata, la risorsa nel sistema di origine, versione o impronta quando disponibili e metadati descrittivi (nome, tipo e dimensione). Il formato pubblico e quello interno restano da finalizzare; credenziali e URL temporanei non appartengono al riferimento persistente. Sono ammesse più connessioni dello stesso tipo, per esempio installazioni BEdita o bucket differenti. La logica delle attività non dipende dal sistema concreto.

| Operazione comune | Comportamento |
|---|---|
| Lettura | Aprire il contenuto anche progressivamente, senza imporre il caricamento completo in memoria |
| Metadati | Consultare le informazioni del file e verificare la versione identificata |
| Salvataggio | Pubblicare il contenuto nella destinazione configurata e restituire il suo `FileRef` |
| Copia locale temporanea | Rendere disponibile un percorso alle librerie che lo richiedono, con durata e pulizia controllate |

Gli adattatori dichiarano le capacità disponibili; operazioni non supportate producono un errore esplicito. Cancellazione e collegamenti di download non sono requisiti universali. La pulizia automatica riguarda soltanto file di competenza Brevia; l'accesso in lettura o scrittura a un sistema esterno non conferisce proprietà o diritto di cancellazione.

**BEdita sorgente e destinazione:** lettura di documenti e salvataggio di risultati attraverso API/plugin. Tipo di media, metadati e collegamenti agli oggetti applicativi sono responsabilità dell'adattatore e del progetto utilizzatore. Si può leggere da un sistema e pubblicare in un altro senza cambiare la logica dell'attività. Per ogni pubblicazione si sceglie un responsabile: salvataggio tramite adattatore oppure successiva importazione dal plugin. La scelta tra caricamento, adattatore e importazione si fa all'integrazione (§5).

**Input stabile nei job:** versione e disponibilità del contenuto devono essere garantite per la ripresa; altrimenti si conserva una copia immutabile. Un'impronta rileva un cambiamento ma non recupera la versione precedente. Contenuti diversi non sostituiscono silenziosamente quelli dello snapshot.

**Pubblicazione senza duplicati:** ogni salvataggio ha un identificativo stabile dell'operazione; l'adattatore riconosce una pubblicazione già avvenuta. Dopo un esito incerto riconcilia il risultato prima di ripetere la creazione. Se il sistema non consente di garantire questo comportamento, il limite va dichiarato e l'incertezza resta esplicita, senza ritentare alla cieca. Meccanismi concreti per ciascun adattatore da verificare prima dell'implementazione; nessuna garanzia universale dedotta dalla sola interfaccia.

#### Prima consegna: file da URL e output del run — decisione del 16 ottobre 2026

Semplificazione decisa nel piano della tappa 4 per un progetto utilizzatore che tiene i documenti nel proprio sistema (BEdita) e avvia i job passando gli URL. Il disegno sopra resta la destinazione; upload, archivio dei documenti e adattatori si aggiungono quando un progetto li chiede, senza cambiare le attività.

- **Input:** un campo `FileSource` dell'input (`name`, `url`, `sha256` e `size` facoltativi) indica un URL `https` di un host ammesso dall'installazione, oppure un percorso locale soltanto per il codice fidato (script e test senza chiamante). All'invio si rifiutano host non ammessi, estensioni non ammesse, dimensioni dichiarate oltre il limite e percorsi locali di un chiamante. L'attività ottiene una copia locale con `ctx.files.local_path(...)`: il file è scaricato una volta per esecuzione, controllato in dimensione, tipo (estensione) e impronta se fornita, e conservato in una cartella di lavoro cancellata alla fine dell'esecuzione, qualunque sia l'esito. Un job ripartito scarica di nuovo; un URL scaduto fa fallire il job con errore esplicito. Gli errori non riportano l'URL, che può contenere una firma; anche i log del client HTTP lo registrano senza query.
- **Output:** `ctx.files.save(nome, contenuto)` scrive il file a parte e lo sposta al suo posto solo se l'esecuzione è ancora in corso; lo stesso nome dà lo stesso file, quindi un job ripartito lo sostituisce senza duplicati. Restituisce `FileRef` con esecuzione, nome, MIME, dimensione e SHA-256, senza percorso né URL. L'output di un job si legge attraverso il job (`RunHandle.file`, poi `GET /runs/{id}/files/{name}` con la tappa 5), con la politica di accesso.
- **Pulizia:** la pulizia giornaliera rimuove le cartelle di lavoro lasciate da un processo fermato un giorno dopo l'ultima modifica e gli output `BREVIA_FILES_RETENTION_DAYS` (30) dopo l'ultimo salvato; `0` li conserva senza limite.
- **Responsabile della pubblicazione su BEdita:** l'applicazione (plugin), che scarica l'output a job concluso e lo salva come media; Brevia non riceve credenziali BEdita e non rischia pubblicazioni doppie dopo una ripartenza. Una destinazione BEdita di `ctx.files.save` resta possibile in seguito.
- **Dati esterni mutabili:** spetta al consumer leggerli prima dell'invio e passarli nell'input (dati piccoli) o come file con impronta; la libreria conserva l'input del job e verifica le impronte. Gli effetti esterni dell'attività devono sopportare una ripetizione.
- **Non inclusi:** upload (`POST /files`), tabelle `files` e `run_files`, archivio con UUID, adattatori S3/Azure/BEdita, idempotenza dei caricamenti.

### 7.7 Conoscenza e conversazioni

**Perimetro concordato:** ricerca ibrida nel modulo RAG, reranking opzionale; Markdown e DOCX aggiunti ai formati esistenti. XLSX/PPTX tramite lettori opzionali quando serve ingestione, distinta dalla generazione Office. Trascrizione conservata come modulo opzionale con adattatori, fuori dal nucleo preliminare.

Ingestione esplicita: acquisizione → estrazione → suddivisione → embedding → pubblicazione dell'indice. Reader, splitter, retriever e reranker sono registrati nel codice. Formati previsti: PDF, TXT, CSV, HTML, Markdown e DOCX; XLSX/PPTX tramite lettori opzionali secondo necessità. La generazione Office di un progetto resta indipendente dall'ingestione RAG.

Documento con identità stabile e revisioni del contenuto; chunk con riferimenti a documento, revisione, posizione e indice. Una nuova generazione dell'indice è costruita a parte e attivata solo quando completa. Modello embedding e dimensione sono parte dell'identità dell'indice; vietato mescolare spazi vettoriali diversi anche se della stessa dimensione. Il numero di dimensioni resta fisso per installazione come deciso; cambiarlo richiede adeguamento dello schema/indice.

Ricerca vettoriale e testuale, filtri e fusione esplicita; risultati con chunk/documento/revisione, posizione e punteggi con significato dichiarato. La chat RAG è un'attività pronta: riscrittura della domanda opzionale, ricerca, composizione del contesto, generazione e fonti. Conservare anche conversazione senza RAG, generazione libera, riassunto e analisi strutturata. Trascrizione audio opzionale prevista per la 1.0 completa, anche per l'uso già rilevato in un progetto 0.x.

Conversazioni e messaggi sostituiscono la sola coppia domanda/risposta: ordinamento esplicito, ruoli, stato, fonti e collegamento all'esecuzione. Le chiamate agli strumenti sono tracciate separatamente dal testo mostrato. Feedback e correzioni non sovrascrivono la risposta originale. Le richieste concorrenti nella stessa conversazione devono essere serializzate o rifiutate per conflitto di revisione.

#### RAG, indicizzazione e strumenti di conoscenza — decisioni del 13 ottobre 2026

Riferimento legacy riletto: `index.py`, `query.py`, `base_retriever.py`, `routers/qa_router.py`, `chat_history.py`, `prompts/rag/system.yml`. Nella 0.15 la chat esegue una catena fissa: riscrittura della domanda anche senza storico, ricerca vettoriale, risposta. Suddivisione per frasi (`NLTKTextSplitter`, 2.000 caratteri, sovrapposizione 200) o splitter registrato dal progetto; documento come gruppo di pezzi con lo stesso `custom_id`, aggiornato con cancellazione e reinserimento non atomici; rifiuto delle domande fuori tema affidato solo al prompt (`score_threshold` predefinita 0). Evidenze del laboratorio: la suddivisione pesa più del modello di embedding; ricerca testuale in OR con stemming e fusione esplicita migliori della sola vettoriale; agente con strumento di ricerca migliore sui confronti, ma ha risposto fuori tema nonostante le istruzioni.

**Strategie.** Un RAG ha una strategia tra:

| Strategia | Funzionamento | Uso |
|---|---|---|
| `fixed` (predefinita) | Brevia esegue una ricerca e il modello risponde | Chat veloci, domande semplici; latenza e costo prevedibili |
| `agent` | Il modello sceglie strumenti, modalità e numero di ricerche entro limiti dichiarati | Domande complesse, confronti, analisi |
| `full_context` | Nessuna ricerca: l'intera raccolta nel prompt, con cache del provider | Raccolte piccole |

Riscrittura multipla della domanda, riordino dei risultati e recupero «small to big» sono opzioni della ricerca, non strategie. Lo smistamento automatico tra strategie resta un'evoluzione possibile, non prevista nella 1.0.

**Configurazione.** Più RAG con nome nello stesso progetto, ciascuno con una o più raccolte e la stessa struttura: `retrieval` (modalità di ricerca, numero di estratti, soglia di pertinenza, contesto `chunk`/`section`, riscrittura solo con storico per `fixed`), `answer` (modello, prompt, comportamento senza risultati, fonti obbligatorie), `agent` (strumenti, modalità ammesse, limiti di chiamate; solo per `agent`), limiti e override ammessi della richiesta. Una raccolta può personalizzare i valori nel database secondo §7.2. La richiesta indica il RAG da usare. Esempio illustrativo:

```toml
[rags.faq]
strategy = "fixed"
collections = ["faq-clienti"]

[rags.faq.retrieval]
search = "hybrid"
docs_num = 4
min_score = 0.3
min_score_on = "vector"        # punteggio a cui si applica la soglia: "vector" o "rerank"

[rags.faq.answer]
model = "<modello>"
when_nothing_found = "decline"

[rags.documenti]
strategy = "agent"
collections = ["verbali", "manuali"]

[rags.documenti.retrieval]
search = "hybrid"
docs_num = 8
min_score = 0.3
min_score_on = "vector"        # punteggio a cui si applica la soglia: "vector" o "rerank"

[rags.documenti.answer]
model = "<modello>"
when_nothing_found = "decline"
require_sources = true

[rags.documenti.agent]
tools = ["search", "list_documents", "open", "find"]
max_tool_calls = 5
```

Nomi e valori sono illustrativi; le soglie si misurano sui dati di ogni raccolta. Un agente su misura del progetto riusa gli stessi blocchi `retrieval` e `answer`.

**Domande fuori tema e fonti.** La soglia di pertinenza si applica a un punteggio che misura la pertinenza, dichiarato in configurazione: similarità vettoriale o punteggio del reranker. Il punteggio della fusione RRF dipende solo dalle posizioni in classifica e non è usabile come soglia. Controllo nel codice oltre al prompt: con `fixed`, se nessun estratto supera la soglia, Brevia risponde secondo `when_nothing_found` senza chiamare il modello. Con `agent` e `require_sources`, le fonti citate devono appartenere agli estratti restituiti dagli strumenti nella stessa esecuzione; altrimenti correzione richiesta al modello e, se persiste, fallimento esplicito.

**Indicizzazione.** Suddivisione per struttura (titoli, sezioni, paragrafi, tabelle) come predefinita, con ripiego a dimensione fissa per documenti senza struttura; ogni pezzo conserva percorso della sezione e posizione. Splitter registrabili dal progetto. Testo estratto completo conservato per ogni revisione del documento (§8.4), necessario per contesto `section`, `open` e `find`. Arricchimento contestuale facoltativo per raccolta: un modello antepone a ogni pezzo una breve descrizione del contesto prima di embedding e indice testuale, con costo all'indicizzazione ([Anthropic](https://www.anthropic.com/news/contextual-retrieval)). Aggiornamento di un documento atomico; nuova generazione dell'indice solo per cambio di embedding o suddivisione.

**Indici a grafo (predisposizione).** Il tipo di indice è estendibile: oltre ai pezzi con vettore e testo, un futuro indice a grafo (entità e relazioni) per raccolte che lo giustificano, esposto come ulteriore modalità di ricerca o strumento utilizzabile da tutte le strategie. Non incluso nella 1.0; adozione dopo misura sui dati reali. Le valutazioni indicano benefici su domande che collegano più fatti e sintesi dell'intera raccolta, non sulle domande fattuali semplici, con costo di indicizzazione maggiore ([Han et al.](https://arxiv.org/abs/2502.11371), [GraphRAG-Bench](https://arxiv.org/abs/2506.05690), [LazyGraphRAG](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)).

**Integrazione con gli altri moduli.** Conversazioni: serie di esecuzioni RAG collegate; storico per la riscrittura, fonti salvate sul messaggio. Riassunto e analisi: attività su file caricati, con documento intero nel prompt o lettura a sezioni. Trascrizione: lettore in ingresso audio → testo, indicizzabile o analizzabile. Valutazione: le tracce registrano estratti, punteggi, strumenti e risposta; gli esperimenti confrontano strategie e parametri della stessa configurazione.

Fonti dello stato dell'arte consultate: [AgenticRAG](https://arxiv.org/abs/2605.05538), [Direct Corpus Interaction](https://arxiv.org/abs/2605.05242), [ricerca logica guidata dal modello](https://arxiv.org/abs/2605.27123), [ricerca per parole chiave agentica](https://arxiv.org/abs/2602.23368v1), [LlamaIndex: file system e ricerca vettoriale](https://www.llamaindex.ai/blog/did-filesystem-tools-kill-vector-search), [Anthropic: context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents). Validazione progettuale; parte dei risultati letti solo dagli abstract e su corpus piccoli, nessuna evidenza di prestazioni sui dati Brevia.

Da precisare: dettaglio della suddivisione per formato, valori iniziali di soglie e limiti, schema delle conversazioni, firme degli strumenti.

#### Conversazioni, analisi e trascrizione — decisioni del 13 ottobre 2026

Riferimento legacy riletto: `chat_history.py`, `routers/qa_router.py`, `routers/analyze_router.py`, `tasks/text_analysis.py`, `completions.py`, `routers/audio_router.py`. Nella 0.15 una riga per coppia domanda/risposta con sessione nell'header `X-Chat-Session`, storico dal client o dalle ultime 3 coppie nel DB, feedback sì/no e commento sulla stessa riga; `/summarize` con catene `stuff`/`map_reduce`/`refine`; `/upload_summarize` e `/upload_analyze` come job con servizio indicato per nome di classe; `/completion` con prompt libero; `/transcribe` sincrono, solo OpenAI.

**Conversazioni.** Entità con chiamante, `end_user` e RAG usato (o nessuno per la chat semplice). Messaggi con ruolo e contenuto in parti (testo, fonti, chiamate agli strumenti), ciascuna risposta collegata alla propria esecuzione. Storico passato al modello: ultimi N scambi, riassunto facoltativo dei precedenti; filtro dello storico non correlato conservato come opzione. Un invio alla volta per conversazione, conflitto sugli invii concorrenti. Feedback separato dalla risposta. Storico nella richiesta ammesso per client che non salvano la conversazione.

**Analisi.** Attività pronte, dirette o come job, usabili anche come strumenti: `summarize` (documento intero se entra nel contesto, altrimenti riassunti per sezione poi combinati), `extract` (estrazione strutturata con schema del progetto, validata e ritentata), `complete` (prompt e testo). La modalità `refine` della 0.15 non è riportata salvo esigenza concreta di un progetto. Riportare un testo così com'è resta un'operazione deterministica del progetto, senza modello.

**Trascrizione.** Modulo facoltativo con adattatori per provider; risultato con testo e, se forniti, segmenti, tempi e interlocutori; audio lunghi come job; testo indicizzabile o analizzabile. OpenAI ha annunciato il 26 agosto 2026 la rimozione dall'API di `whisper-1`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe` e `gpt-4o-transcribe-diarize` dal 26 febbraio 2027, indicando `gpt-transcribe` e `gpt-live-transcribe` come sostituti ([deprecazioni OpenAI](https://developers.openai.com/api/docs/deprecations)): l'adattatore va riscritto, non soltanto conservato.

### 7.8 Tracce, revisione, valutazione e dati per fine tuning

**Impostazione concordata:** tracciamento interoperabile con OpenTelemetry; conservazione dei contenuti configurabile separatamente dai metadati operativi. Dataset e rubriche versionati, confronti, correzioni umane ed export fanno parte del modulo di valutazione iniziale; UI dedicata e training successivi. Il nucleo preliminare conserva da subito tracce e riferimenti necessari; gli endpoint completi di valutazione seguono nel relativo modulo. Durate di conservazione e rubriche concrete sono scelte del progetto, compatibili con ripresa e dataset conservati.

**Requisito confermato:** Brevia conserva, secondo configurazione dell'attività, prompt renderizzati, input/contesto effettivo, risposte, chiamate agli strumenti, errori e consumi, per revisione e analisi. Metadati e metriche sempre interrogabili; contenuti completi con permessi dedicati e retention configurabile. Non salvare credenziali o header di autenticazione. La scadenza dei contenuti è esplicita e non deve rendere impossibile la ripresa di un job ancora attivo.

Funzioni previste nella 1.0 completa:
1. **Revisione:** confronto tra revisioni di prompt e tra output originali/corretti; annotazioni, rubriche, punteggi, accettazione/rifiuto e motivazione. Una revisione umana e un giudizio automatico restano distinguibili.
2. **Dataset:** casi Q/A, output strutturati attesi, documenti/chunk rilevanti o rubriche; revisioni immutabili, provenienza e collegamenti alle esecuzioni revisionate. I casi proposti automaticamente diventano dati di riferimento solo dopo revisione.
3. **Esperimenti:** confronto tra combinazioni di prompt, modello, parametri, splitter e indice; congelare dataset, versione del codice e metriche. Ogni caso produce un risultato con esito, errori e consumi; i fallimenti non spariscono dalla media.
4. **Metriche:** correttezza rispetto ai riferimenti, aderenza alle fonti, validità dello schema, hit@k/MRR per il retrieval, tasso di accettazione e correzione umana, latenza, token, cache e costo. Distinguere qualità della ricerca e della generazione. Un evaluator LLM registra modello, prompt/rubrica e revisione; il suo giudizio non è verità di riferimento.
5. **Evoluzione nel tempo:** confronti sulla stessa revisione del dataset e segmenti omogenei, con numero di casi, variabilità e condizioni di cache dichiarate. Una nuova revisione del dataset apre una nuova base di confronto. Promozione di prompt/modelli esplicita, non automatica sulla sola media.
6. **Preparazione al fine tuning:** selezione degli esempi revisionati, deduplicazione, correzioni target e split train/validation/test senza sovrapposizioni della stessa fonte o conversazione. Esportazione versionata (formato canonico e adattatori JSONL), manifest con provenienza, modelli/prompt originari e trasformazioni. Dataset di valutazione riservati non diventano automaticamente dati di training.

Gli esperimenti e gli export sono attività Brevia eseguite con DBOS; nessun secondo scheduler. Pydantic Evals resta un possibile adattatore interno, non il formato obbligatorio dei dati del progetto. Importare/eseguire un modello affinato in Ollama sarà possibile nei formati compatibili: training, selezione del relativo framework e orchestrazione GPU sono un'evoluzione separata. Preparare adesso dati e contratti non implica implementare l'addestramento nella prima consegna.

#### Revisione e valutazione — decisioni del 13 ottobre 2026

- **Conservazione dei contenuti:** durata predefinita configurabile per progetto, compatibile con ripresa e dataset conservati.
- **Copie dei dati (audit del 14 ottobre 2026):** la durata dei contenuti delle chiamate non cancella le altre copie. Oggi `retention_days` vale per `trace_contents` e per gli step registrati da DBOS dei job terminati; input, risultato, dettagli degli errori e snapshot con i testi dei prompt restano in `runs` senza scadenza, anche con `capture="metadata"`; con i job si aggiungono input e output degli step DBOS. Prima della produzione serve una regola esplicita per ogni copia: metriche e metadati (conservazione indipendente dai contenuti); input, output e snapshot (durata e permessi di lettura); checkpoint DBOS (compatibili con ripresa e cancellazione dei workflow); file (riferimenti attivi, scadenze, orfani); dataset approvati (conservazione autonoma dalle tracce da cui derivano). Nessun sistema di governance generale: solo che «conservazione di 30 giorni» non significhi cancellare una sola tabella.
- **Interfaccia:** nessuna UI nella 1.0; API e report. L'interfaccia della piattaforma di test sarà aggiornata alle API 1.0 (§10).
- **Rubriche iniziali:** elenco di criteri con scala, usato da revisori o da un modello giudice. Fornite da Brevia: correttezza rispetto al riferimento (1–5), aderenza alle fonti (sì/no), completezza (1–5); il progetto può aggiungerne.
- **Collegamenti:** feedback delle conversazioni e correzioni umane diventano revisioni; revisioni approvate diventano casi dei dataset; gli esperimenti confrontano configurazioni RAG o di analisi sugli stessi casi con metriche di ricerca (hit@k, MRR), di risposta (correttezza, aderenza), costo e tempi. [Pydantic Evals](https://pydantic.dev/docs/ai/evals/) resta possibile motore interno (dataset, valutatori, giudizio della sequenza di strumenti).

### 7.9 Accesso indipendente dal canale e plugin opzionali

**Decisione del 10 ottobre 2026:** mantenere l'autenticazione della vecchia Brevia: JWT HS256 con `user` e scadenza `exp`, header `Authorization: Bearer`, segreto `TOKENS_SECRET` e lista facoltativa `TOKENS_USERS`. Senza segreto la protezione è disattivata, come oggi. **Modificata il 14 ottobre 2026 (audit):** senza segreto il servizio non parte; la modalità senza autenticazione richiede un'attivazione esplicita in configurazione (`BREVIA_AUTH_DISABLED=true`, tappa 4), così che un deployment incompleto non apra l'API. Differenza voluta rispetto alla 0.15; i token già emessi restano validi. Un token condiviso identifica un'applicazione chiamante, non una persona: `per-caller` da solo non separa due utenti dello stesso backend (per questo esiste `end_user`). Conservare l'emissione dei token da riga di comando, ora `brevia token create` (§11.4), e l'eccezione `STATUS_TOKEN` per `/status` (passato come `?token=`). Libreria PyJWT al posto di `python-jose` della 0.15, con lo stesso algoritmo e payload: i token già emessi restano validi. Più token possono coesistere nella stessa installazione. Riferimenti verificati: `brevia/tokens.py`, `brevia/dependencies.py`, `brevia/routers/status_router.py` e `docs/security.md` della 0.15.2.

**Criterio generale:** la vecchia Brevia è riferimento tecnico e funzionale, non specifica da replicare (§3.1). JWT resta invariato per scelta esplicita; configurazione, API e algoritmi seguono le decisioni della 1.0, motivando le differenze.

La verifica legacy controlla la validità del token; non fornisce autorizzazioni per risorsa. Per la 1.0 è concordata una politica di autorizzazione sostituibile, separata dall'autenticazione: accesso condiviso nell'installazione oppure restrizioni per chiamante, attività e raccolta. Nessun nuovo sistema di login o token opachi obbligatorio. Identità applicativa e utente finale restano distinti: un token condiviso non distingue gli utenti. I frontend diretti usano credenziali con permessi adeguati. Formato interno delle regole da consolidare nelle firme.

**Implementazione della tappa 4 (16 ottobre 2026):** impostazioni con il prefisso comune `BREVIA_TOKENS_SECRET` e `BREVIA_TOKENS_USERS` (nella migrazione si rinominano `TOKENS_SECRET` e `TOKENS_USERS`; conta il valore del segreto, quindi i token restano validi, verificato con un token emesso dalla 0.15); token senza `exp` rifiutati (`create_token` della 0.15 lo imposta sempre); `brevia token create --user NOME [--minutes 60]`. Fino alla HTTP API il codice che riceve le richieste verifica il token e passa il chiamante alle operazioni (`caller=`); un'operazione senza chiamante è codice fidato. Con la tappa 5 lo fanno i router.

#### Chiamante, accesso e idempotenza — decisioni del 12 ottobre 2026

Riferimento legacy riletto: `tokens.py`, `dependencies.py`, `async_jobs.py`, `routers/jobs_router.py`, `routers/download_router.py`, `chat_history.py`. Nella 0.15 il campo `user` è verificato soltanto rispetto a `TOKENS_USERS` e non viene usato dopo la verifica; ogni token valido legge tutti i job, lo storico e le raccolte; ogni avvio crea un nuovo job; `/download/{file_path:path}` non dichiara autenticazione e unisce il percorso ricevuto alla cartella di output senza controlli. Questi limiti non si riportano nella 1.0.

- **Chiamante:** il campo `user` del JWT identifica l'applicazione chiamante, non una persona. È registrato su esecuzioni, file e conversazioni.
- **Utente finale (`end_user`):** identificativo opaco facoltativo (un id o un hash, mai nome o email), fornito da un chiamante fidato (per esempio un backend con un solo token per tutti i suoi utenti). Serve a tracciabilità, filtri, autore di feedback/revisioni e consumi per utente. Non conferisce permessi, salvo regola esplicita della politica di accesso. Via HTTP è il campo facoltativo `end_user` nel corpo delle richieste che registrano qualcosa (esecuzioni, modifiche di configurazione e prompt, feedback). **Modificata il 17 ottobre 2026:** nome `end_user` al posto di `on_behalf_of` e campo nel corpo invece di un'intestazione, come i servizi LLM (OpenAI `safety_identifier`, Anthropic `metadata.user_id`) e OpenTelemetry (`enduser.id`); le intestazioni come `Impersonate-User` di Kubernetes cambiano i permessi, e "on behalf of" richiama il flusso OAuth che li concede.
- **Politica di accesso:** interfaccia sostituibile che decide se un chiamante può eseguire un'azione su una risorsa (esecuzione, file, raccolta, conversazione). Politiche fornite: `shared` (ogni token valido accede a tutto, come nella 0.15) e `per-caller` (ogni chiamante accede a esecuzioni, file e conversazioni creati da lui; raccolte condivise salvo elenco di chiamanti ammessi; chiamanti amministratori configurabili). Scelta tramite impostazione di installazione; regole diverse tramite politica registrata nel codice del progetto, mai da database o richiesta. Default `per-caller`.
- **File:** accesso per identificativo; un file è accessibile se lo è l'esecuzione collegata o se il chiamante lo ha caricato. Nessun accesso per percorso.
- **Idempotenza:** su avvio dei job e caricamento dei file; esclusa per le chiamate dirette, per le quali si usa un job con attesa limitata quando serve protezione dai duplicati. Chiave facoltativa, ambito chiamante + operazione + chiave (per i job l'operazione è l'attività: la stessa chiave su due attività dà due job); impronta canonica di attività, versione, input, override e riferimenti ai file. Stessa chiave e stessa impronta: stessa esecuzione, in qualunque stato, anche `failed`. Stessa chiave e impronta diversa: conflitto 409. Il rilancio richiede `retry` esplicito o una nuova chiave. La chiave vive quanto l'esecuzione che la contiene, senza archivio separato.

**Modificata il 16 ottobre 2026 (piano della tappa 4):** la politica non è sostituibile nella prima consegna: due forme scelte dall'installazione (`BREVIA_ACCESS_POLICY=per-caller`, default, oppure `shared`) e un elenco di amministratori (`BREVIA_ACCESS_ADMINS`), senza regole per attività, raccolta o operazione. Con `per-caller` un chiamante trova soltanto i propri job (un job di un altro dà `not_found`, come uno inesistente, senza rivelarne l'esistenza), un rilancio resta del chiamante originale anche se chiesto da un amministratore, e modificare configurazioni e prompt è riservato agli amministratori; la lettura resta aperta. Liste, tracce e feedback ricevono il filtro della politica con la tappa 5. Un token per frontend separa le applicazioni, non i loro utenti; `end_user` non aggiunge isolamento. Per un'unica applicazione interna basta `shared`. L'idempotenza dei caricamenti non si applica finché non c'è upload (§7.6).

**BEdita è un'integrazione opzionale di riferimento**, progettata insieme ai contratti e implementata nel plugin PHP. Le stesse funzioni generiche sono accessibili dai frontend diretti, dagli altri backend e da Python. Il plugin gestisce client HTTP, avvio e correlazione delle esecuzioni, callback, polling, file, inoltro delle revisioni umane e sincronizzazione RAG. Il workflow aziendale del chiamante resta esterno: Brevia conosce soltanto i job richiesti e i riferimenti opachi di correlazione. Dettaglio del flusso e stato del plugin in §6.

### 7.10 Sequenza di lavoro

La sequenza è in §12.2: specifiche generali → allineamento di un dimostratore → prima consegna della libreria (§5) → servizio utilizzatore. Le tracce entrano subito nel nucleo per non perdere dati utili. Nessun modulo è dichiarato pronto prima di implementazione e verifica (§11.6).

---

## 8. Schema del database

**Proposta logica**, con campi e vincoli principali. Il DDL e le migrazioni Alembic si scrivono dopo il consolidamento dei contratti. Tipi comuni: UUID, timestamp con timezone, JSONB per payload/configurazioni/metadati, colonne tipizzate per campi filtrati, `numeric` per prezzi/costi, contatori interi per token. Segreti fuori dalle tabelle di configurazione pubbliche.

**Confronto con la vecchia Brevia:** conservare responsabilità e dati utili, senza conservare la dipendenza delle tabelle da LangChain. Riferimenti: `settings.ConfigStore`, `chat_history.ChatHistoryStore`, `async_jobs.AsyncJobsStore` e gli store raccolte/embedding usati da `collections.py`, `index.py` e `query.py`.

| Struttura attuale | Evoluzione proposta e dati da non perdere |
|---|---|
| `config` con chiave/valore | Personalizzazioni con versione concorrente e storico dei prompt (§8.2); mantenere default, schema e reset, senza confondere valori e segreti |
| Raccolte e embedding LangChain | Raccolte, documenti, revisioni, indici e chunk; preservare UUID/riferimenti esterni, metadati e configurazione di raccolta |
| `chat_history` | Conversazioni/messaggi/feedback; preservare sessione, raccolta, domanda/risposta, date, `cmetadata`, `chat_source`, valutazione e commento |
| `async_jobs` | Esecuzioni Brevia + stato durevole DBOS; preservare servizio/attività, input, risultato, scadenza e date. Lock e tentativi di esecuzione competono a DBOS, non a un secondo scheduler |
| File su filesystem/S3 | Catalogo dei file e collegamenti alle esecuzioni; integrare i backend esistenti con UUID, impronte e retention |

Il disegno è coerente per responsabilità, ma prima delle migrazioni vanno precisati scadenza dei job, metadati/origine delle conversazioni e mappatura degli identificativi. I campi mancanti non vanno persi per effetto della nuova nomenclatura. Nessuna tabella del workflow aziendale entra nel nucleo Brevia.

### 8.1 Topologia e rapporto con BEdita

Brevia e DBOS usano lo stesso database PostgreSQL con schemi distinti (`brevia` e `dbos`). `DBOSClient.enqueue_in_transaction` permette di accodare dentro una transazione SQLAlchemy sul database di sistema DBOS; `dbos_system_schema` configura lo schema. Verificato il 14 ottobre con dbos 3.2.0 e il motore asincrono della libreria, tramite `AsyncConnection.run_sync`: con un rollback non restano né il run né il job. Questo consente di registrare `runs` e accodare atomicamente senza intervenire direttamente sulle tabelle interne DBOS.

Per BEdita sono previste queste topologie, tutte compatibili con l'integrazione HTTP:

| Topologia | Valore e vincoli |
|---|---|
| Istanze e database separati | Nessun accoppiamento di versione o gestione del database tra Brevia e BEdita; comunicazione tramite API |
| Stessa istanza PostgreSQL, database distinti | Proposta iniziale: infrastruttura condivisa, proprietà e backup/ripristini logici più separabili; stessa versione del server e risorse comunque condivise |
| Stesso database, schemi distinti | Opzione per progetto: BEdita nel proprio schema esistente, Brevia in `brevia`, DBOS in `dbos`; provisioning unico e possibilità di viste di reporting controllate, maggiore accoppiamento di gestione e ripristino |

La co-locazione richiede compatibilità della versione PostgreSQL, delle estensioni, del driver e delle migrazioni di entrambi i servizi. Non è una compatibilità già verificata: configurazione e controlli del progetto utilizzatore sono documentati separatamente.

Se il database è condiviso: ruoli e privilegi distinti, nomi di schema qualificati e `search_path` controllato; ogni servizio scrive soltanto nelle proprie tabelle e gestisce le proprie migrazioni. Nessuna FK, trigger o scrittura di dominio incrociata come requisito del nucleo. Collegamenti tramite ID esterni e API. Eventuali viste per reporting sono un adattatore di progetto. I namespace PostgreSQL richiedono privilegi corretti: [documentazione degli schemi](https://www.postgresql.org/docs/current/ddl-schemas.html).

Il DB condiviso non rende atomiche le operazioni di due servizi che comunicano via HTTP: restano necessari idempotenza, callback e riconciliazione. La transazione Brevia–DBOS riguarda solo registrazione/accodamento interni a Brevia. Nessuna decisione di co-locazione è ancora presa.

**Predisposizione da implementare:** schema Brevia configurabile, tabelle/FK/indici qualificati, registro Alembic separato, ispezione e migrazioni limitate allo schema di proprietà; schema DBOS configurato tramite il suo SDK. Evitare assunzioni su `public` anche in query SQL, controlli di avvio e percorsi di ricerca dei tipi pgvector. La vecchia `connection.py` costruisce un engine dalla configurazione ma non imposta questa separazione; la co-locazione richiede quindi lavoro esplicito, non soltanto lo stesso URL di connessione. Backup/ripristino delle esecuzioni Brevia e dello stato DBOS devono restare coerenti.

### 8.2 Nucleo: configurazione e prompt

Autenticazione tramite JWT come nella 0.x: nessuna nuova tabella per token o identità richiesta. Chiamante, utente finale e ambito di idempotenza sono definiti in §7.9. Il campo `user` del JWT non è automaticamente un utente finale e non implica permessi sulle risorse.

| Tabella | Campi principali e vincoli |
|---|---|
| `configurations` | `id`, chiave/contesto univoci, tipo/schema, personalizzazioni JSONB, versione concorrente, autore/data. Assenza di personalizzazioni: default del progetto |
| `prompts` | `id`, chiave univoca, personalizzazione corrente facoltativa, schema variabili, versione concorrente, autore/data |
| `prompt_revisions` | Storico immutabile delle modifiche/reset: FK prompt, numero versione, contenuto e tipo operazione, impronta, autore/data; unicità prompt/versione |

Nessuna tabella `configuration_revisions` o catalogo dei default obbligatori. I cataloghi delle implementazioni e i default sono nel progetto. Modifica corrente e storico del prompt salvati nella stessa transazione; reset conserva lo storico e la versione concorrente, anche se il valore torna ai file. Gli snapshot conservano il contenuto effettivo: nessuna ricostruzione da una catena di revisioni. Dettagli fisici e vincoli da precisare nel DDL.

### 8.3 Nucleo: esecuzioni, file e tracce

| Tabella | Campi principali e vincoli |
|---|---|
| `runs` | `id`, `caller` (campo `user` del JWT), `end_user` facoltativo, attività/contratto, versione codice, modalità, input JSONB, snapshot risolto, versioni/impronte dei prompt, per i job l'identificativo del workflow DBOS coincide con `runs.id` (nessun workflow nelle chiamate dirette), stato proiettato, risultato/errore, date e scadenza di esecuzione, `parent_run_id`/`retry_of_run_id`, contesto esterno, chiave idempotenza e impronta richiesta |
| `run_events` | FK run, sequenza, tipo, payload, data; unicità run/sequenza e ID evento stabile |
| `model_calls` | FK run, una riga per chiamata logica (`run_id`, `sequence`) con numero di richieste, nessuna riga per tentativo, scritte con l'esito del run (diretto o job); provider/modello/versione, opzioni effettive (ragionamento, temperatura, token massimi), esito/errore, token/cache, costo e listino, durata, ID richiesta provider se disponibile |
| `trace_contents` | Una riga per chiamata con contenuti catturati, identificata dalla chiamata stessa (chiave primaria); contenuti JSONB o riferimento file, scadenza e stato di eliminazione; credenziali escluse. Decisioni del 16 ottobre 2026: nessuna impronta dei contenuti (non serviva e, dopo la scadenza, permetteva di confermare per tentativi un'uscita breve); nessuna colonna della modalità di cattura (la riga esiste solo con la cattura completa, la modalità è nello snapshot); indice delle scadenze limitato ai contenuti non ancora cancellati |
| `files` | Rinviata (16 ottobre 2026, §7.6): nella prima consegna nessuna tabella, gli output sono file della cartella dell'esecuzione. Destinazione: `id`, `caller` proprietario, connessione configurata, backend/storage key oppure sistema/risorsa/versione esterni, nome, MIME, byte, hash, stato (`pending`/`ready`/`deleted`), proprietà e date/retention, chiave di idempotenza del caricamento (univoca per chiamante quando presente); vincoli dei riferimenti esterni da dettagliare |
| `run_files` | Rinviata con `files`. Destinazione: FK run/file, ruolo (`input`, `output`, `trace`, `report`), nome logico; unicità run/ruolo/nome |
| `tool_calls` | FK run, passo, strumento, argomenti, dimensione ed esito della risposta, durata, errore; per tracce degli agenti e valutazione della sequenza di strumenti |
| `feedback` | FK run, tipo (`correction`, `rating`), elementi JSONB (elemento, originale, corretto) o voto/commento, `caller`, `end_user`, riferimento esterno opaco, data; solo inserimenti. Il feedback su un messaggio è feedback sull'esecuzione che lo ha prodotto |
| `webhook_deliveries` | ID evento, run, chiave destinazione configurata, stato, tentativi, prossimo invio/esito HTTP; unicità evento/destinazione; rinviata all'integrazione con callback |

Idempotenza (§7.9): vincolo univoco parziale su chiamante, attività e chiave non nulla; il contenuto della richiesta include attività, versione, input e override. Una ripetizione con la stessa chiave restituisce il job esistente senza ricontrollare la configurazione corrente. Stessa chiave e richiesta diversa: conflitto. La deduplicazione viene risolta prima dell'enqueue nella transazione, senza affidarsi a una seconda policy concorrente.

DBOS è l'autorità sullo stato durevole; `runs` è la registrazione applicativa e la sua proiezione viene riconciliata in caso di arresto. Gli eventi non sostituiscono i checkpoint DBOS. Esito e chiamate di un run si scrivono una sola volta, insieme (decisione del 15 ottobre 2026). Una chiamata interrotta senza risposta può avere consumo sconosciuto: non inventare un importo zero. Le chiamate di un'esecuzione persa con il worker non si registrano. Registrazione e motore possono divergere per poco (per esempio dopo un arresto): la lettura dello stato e la pulizia giornaliera riconciliano `runs` dallo stato DBOS. `model_calls` si scrive con l'esito del run, diretto o job; la revisione del prompt è nello snapshot del run.

Indici: run per stato/data e per chiamante/data; eventi per run/sequenza; chiamate per run e modello/data; consegne per stato/prossimo invio. Contenuti pesanti separati dai contatori per interrogare metriche senza caricare prompt e documenti.

### 8.4 Conoscenza e conversazioni

| Tabella | Campi principali e vincoli |
|---|---|
| `collections` | Nome univoco, configurazione, metadati e indice attivo |
| `documents` | Raccolta, origine/ID esterno, metadati, stato, revisione corrente; unicità raccolta/origine/ID esterno quando presente |
| `document_revisions` | Documento, revisione, file/testo estratto completo, struttura (sezioni e titoli con posizioni), hash e metadati della fonte; revisione immutabile |
| `collection_indexes` | Raccolta, generazione, tipo (`chunks`; in futuro `graph`), modello/dimensione embedding, configurazione splitter/estrattore, snapshot dei documenti inclusi e stato |
| `chunks` | Indice, revisione documento, posizione, percorso della sezione, testo, contesto facoltativo (arricchimento), metadati, vettore e campo di ricerca testuale; unicità indice/revisione/posizione |
| `conversations` | Identificativo/sessione, `caller`, `end_user`, RAG usato, riassunto facoltativo dello storico precedente, raccolta quando presente, origine (`chat_source`), configurazione/attività, revisione di concorrenza, metadati e date |
| `messages` | Conversazione, sequenza, ruolo, contenuto in parti JSONB (testo, fonti, chiamate agli strumenti)/stato, run, metadati della risposta, riferimenti fonti e data; unicità conversazione/sequenza |
| Grafo | Tabelle di entità e relazioni previste per gli indici a grafo (§7.7), da progettare quando serviranno |

Pubblicazione atomica del riferimento all'indice pronto; vincolo che l'indice appartenga alla raccolta. Unicità e FK devono impedire chunk attribuiti a una raccolta diversa. Indici GIN per ricerca testuale, vettoriali coerenti con dimensione/metrica e B-tree sui collegamenti; gli indici JSONB vengono aggiunti sui filtri effettivamente richiesti.

La conservazione delle revisioni permette riferimenti alle fonti verificabili nel tempo. Una cancellazione applicativa e l'eliminazione fisica hanno tempi espliciti; non eliminare contenuti ancora referenziati da job, dataset o revisioni conservate senza gestire quei riferimenti.

### 8.5 Revisione, dataset, esperimenti ed export

| Tabella | Campi principali e vincoli |
|---|---|
| `reviews` | Valutazioni deliberate del modulo di valutazione, distinte dal `feedback` del nucleo: Run/chiamata, revisore umano o automatico, rubrica/versione, stato, annotazioni, correzione target o preferenza, data; revisioni append-only |
| `datasets` / `dataset_revisions` | Identità, scopo, revisione immutabile, manifest dei casi, schema e impronta |
| `dataset_cases` | Revisione dataset, chiave caso, input, target/rubrica, fonti, provenienza run/review, split e gruppo anti-duplicazione |
| `experiments` | Dataset/revisione, varianti, riferimento baseline, piano metriche/evaluator versionati, run di orchestrazione |
| `evaluation_results` | Esperimento, variante, caso, ripetizione, run, valori metriche, valutatore, errori e consumi; unicità esperimento/variante/caso/ripetizione |
| `dataset_exports` | Dataset/revisione, selezione e trasformazioni, formato/versione, manifest, file prodotto, autore/run e date |

Gli esperimenti si eseguono come attività e condividono stato, limiti, file e consumi di `runs`. Le tabelle di evaluation conservano il significato del confronto, non una nuova macchina dei job. I dataset approvati sono risorse con propria retention: non dipendono accidentalmente dalla scadenza delle tracce operative da cui derivano.

---

## 9. API

**Decisioni consolidate:** nessun prefisso `/v1` obbligatorio; nucleo API per attività, esecuzioni, file, configurazioni, prompt e consumi. OpenAPI, modifiche additive e cambi incompatibili espliciti. Polling iniziale; SSE per le attività che richiedono streaming, senza WebSocket obbligatorio. Adattatori legacy separati e rinviati alla migrazione, salvo autenticazione già confermata. Le tabelle seguenti restano bozze delle firme e dei payload, non endpoint implementati.

### 9.0 Mappa consolidata — decisioni del 13 ottobre 2026

| Gruppo | Endpoint | Prima consegna |
|---|---|---|
| Catalogo | `GET /activities`, `/activities/{name}` | Sì |
| Esecuzioni | `POST /runs` (con `end_user` facoltativo, §7.9), `GET /runs`, `/runs/{id}`, `/result`, `/events` (SSE), `/usage`, `POST /runs/{id}/cancel`, `/retry` | Sì |
| Feedback | `POST /runs/{id}/feedback` | Sì |
| File | `POST /files`, `GET /files/{id}`, `/content`, `DELETE /files/{id}` | No (16 ottobre 2026, §7.6): nella prima consegna `GET /runs/{id}/files/{name}` per gli output di un job; input come URL nel corpo di `POST /runs` |
| Configurazione e prompt | §9.3 | Sì |
| Modelli, consumi, salute | `GET /models`, `GET /usage`, `GET /health/live`, `/health/ready`, `GET /status` | Sì |
| Scorciatoie | `POST /rags/{name}/ask`, `POST /summarize`, `POST /extract`, `POST /transcribe` | Le scorciatoie delle funzioni incluse (`summarize`, `extract`) |
| Raccolte, documenti, ricerca | §9.4, più `GET /documents/{id}/content?section=…` (strumento `open`) | No |
| Conversazioni | §9.4 | No |
| Valutazione | §9.5 | No |
| BEdita | Callback firmata (§9.6) | All'integrazione |

Analisi, trascrizione e RAG sono attività avviate con `POST /runs`. Le scorciatoie sono adattatori sottili sullo stesso servizio, senza logica propria. Nessun router legacy nella prima consegna: l'interfaccia della piattaforma di test viene aggiornata alle API 1.0 (§10). Eventuali adattatori per i client 0.x si valutano nella migrazione (§9.7).

**Feedback strutturato.** Generico per qualsiasi attività: correzioni (elemento, testo originale, testo corretto), giudizi (voto, commento), autore o `end_user`, riferimento esterno opaco al documento finale. Brevia conserva le differenze e il riferimento, non il file finale: il confronto tra documenti (per esempio bozza e versione ricaricata) è una funzione del progetto utilizzatore. Esempio:

```json
POST /runs/{id}/feedback
{ "kind": "correction",
  "items": [{"target": "<elemento>", "original": "<testo generato>", "corrected": "<testo corretto>"}],
  "external_ref": {"system": "bedita", "object_id": "<id>", "revision": "<rev>"},
  "end_user": "<utente>" }
```

Il feedback alimenta le revisioni del §7.8; dataset ed esperimenti seguono nel modulo di valutazione.

**Documentazione delle API (dalla prima consegna).** Specifica OpenAPI generata da FastAPI, con pagine interattive Swagger UI (`/docs`) e ReDoc (`/redoc`) disattivabili per installazione, ed esportazione della specifica in file. Collezione Postman con ambiente di esempio, versionata con la libreria e aggiornata insieme agli endpoint. Riferimento 0.15: `brevia/postman/` (collezione e ambiente), comando `create_openapi`, impostazione `block_openapi_urls`.

### 9.1 Regole comuni

**Criterio:** progettare API coerenti con le capacità della 1.0 e usare quelle esistenti come riferimento funzionale. Riutilizzare nomi e formati quando sono ancora adatti, senza imporre compatibilità completa. Eventuali adattatori per vecchi client restano separati dal nucleo e verranno precisati nella migrazione (§3.1).

**Regole per le funzioni nuove:** percorsi senza prefisso di versione obbligatorio, router opzionali sullo stesso nucleo Python, paginazione a cursore, errori uniformi ed eventi SSE. Queste scelte non impongono di rinominare o sostituire tutte le API esistenti. Gli adattamenti legacy sono da valutare separatamente; nessuna compatibilità è dichiarata verificata. `/status` e il relativo `STATUS_TOKEN` restano previsti anche se si aggiungono endpoint di salute più dettagliati.

I termini «autorizzato», «proprietario» e «permesso dedicato» rimandano alla politica sostituibile concordata (§7.9): schema delle regole e controlli per risorsa ancora da specificare. Vale l'autenticazione JWT attuale; nessuna gestione utenti implicita.

- Autenticazione JWT come nella vecchia Brevia (§7.9), uguale per frontend diretti e backend. I permessi sono valutati dalla politica di accesso e non sono impliciti nella validità del token.
- JSON per dati e multipart per upload; file per UUID. Paginazione a cursore con ordinamento stabile e limiti di pagina.
- Errori con `code`, `message`, `details`, `request_id`; codici HTTP coerenti, inclusi 409 per idempotenza e 412 per revisione attesa non più corrente.
- `Idempotency-Key` per comandi ritentabili; `If-Match` o revisione attesa per modifiche concorrenti. Contratto di attività esplicito nell'avvio.
- Stessa chiave, chiamante e operazione restituiscono lo stesso job; contenuto diverso con la stessa chiave produce conflitto. La chiave vive quanto l'esecuzione; un'esecuzione fallita resta associata alla chiave e si rilancia con `retry` (§7.9). Gli effetti esterni degli strumenti richiedono protezioni proprie dai duplicati.
- Configurazioni/provider pubblici senza segreti. Le destinazioni callback sono configurate nell'installazione, non URL arbitrari nell'input del job.
- SSE per lo streaming nuovo, eventi tipizzati (`started`, `text_delta`, `progress`, `completed`, `failed`) e ID run. Gli eventi durevoli di stato sono riproducibili; la ripresa dei singoli token non è garantita se non vengono persistiti. Il risultato completo resta recuperabile.

**Catalogo degli errori — decisione del 13 ottobre 2026.** Stesso codice in HTTP (`{code, message, details, request_id}`) e in Python (una classe per codice, derivata da `BreviaError`).

| Codice | HTTP | Quando |
|---|---|---|
| `invalid_input` | 422 | Input o override non validi |
| `override_not_allowed` | 422 | Parametro non ammesso nella richiesta |
| `unauthorized` | 401 | Token mancante o non valido |
| `forbidden` | 403 | La politica di accesso nega l'operazione |
| `not_found` | 404 | Risorsa inesistente o non visibile al chiamante |
| `idempotency_conflict` | 409 | Stessa chiave, richiesta diversa |
| `version_conflict` | 412 | Modifica concorrente di configurazione o prompt |
| `not_ready` | 409 | Risultato richiesto prima della fine del job |
| `busy` | 409 | Conversazione con un invio già in corso |
| `unsupported` | 422 | Capacità non offerta da modello o adattatore |
| `provider_error` | 502 | Errore del provider del modello |
| `file_too_large` | 413 | File oltre la dimensione ammessa |
| `unavailable` | 503 | Database o configurazione non disponibili |

Un job fallito riporta `error: {code, message, details, retryable}` con codici `limit_exceeded`, `timeout`, `output_invalid`, `tool_error`, `provider_error`, `cancelled`, `internal`; inoltre ogni errore del catalogo sollevato durante il run, in particolare `invalid_input`, `unsupported` (rilanciabile per un'attività cambiata di versione prima dell'avvio) e `unavailable`. Un job interrotto da un rilascio fallisce con `internal` rilanciabile (§11.5).

### 9.2 Catalogo, esecuzioni e file

| Metodo e percorso proposti | Dati e comportamento |
|---|---|
| `GET /activities` e `/{name}` | Catalogo autorizzato, versioni, schemi input/output/configurazione e modalità |
| `POST /runs` | Attività, versione contratto, modalità, input, file, override ammessi, contesto esterno e chiave destinazione callback opzionale |
| `GET /runs` e `/{id}` | Elenco filtrato e dettaglio: stato, avanzamento, risultato/errore, link, revisioni |
| `GET /runs/{id}/result` | Output tipizzato; conflitto se non ancora disponibile |
| `GET /runs/{id}/events` e `/usage` | Eventi paginati/SSE e consumi con copertura dei dati |
| `POST /runs/{id}/cancel` | Richiesta di annullamento idempotente |
| `POST /runs/{id}/retry` | Nuovo run collegato, input/snapshot precedenti; cambi di input o configurazione richiedono un nuovo avvio esplicito |
| `POST /runs/{id}/responses` | Risposta tipizzata a richiesta di intervento in stato `waiting`; modulo successivo |
| `GET /runs/{id}/files/{name}` | Prima consegna: output di un job, con la politica di accesso del job |
| `POST /files` | Upload; restituisce `FileRef` pronto soltanto dopo pubblicazione e verifica. Rinviato (§7.6) |
| `GET /files/{id}` e `/content` | Metadati e download autorizzato |
| `DELETE /files/{id}` | Cancellazione secondo proprietà, riferimenti e retention; conflitto se ancora necessario |

`job`: 202 con `run_id` e URL di stato, dopo salvataggio/accodamento. Un job può prevedere attesa limitata: risultato 200 se completato con successo, altrimenti 202 con lo stesso run se ancora in corso; gli errori terminali restano espliciti. `direct`: risultato 200 o errore, senza conversione automatica in job alla scadenza dell’attesa. Streaming: SSE solo per attività che lo dichiarano, sia diretto sia da un job; consegna degli eventi e durabilità sono scelte distinte, con payload da consolidare. Un replay idempotente di un avvio in streaming restituisce l'identità del run e il modo di consultarne il risultato; non promette il replay dei token già emessi.

Esempio di forma dell'avvio (nomi proposti, non endpoint già implementato):

```json
{
  "activity": "document.summarize",
  "contract_version": "1",
  "mode": "job",
  "input": {"file_ids": ["<uuid>"]},
  "overrides": {"calls": {"section_text": {"thinking": "low"}}},
  "external_context": {"system": "bedita", "object_id": "<id>", "revision": "<rev>"},
  "callback_destination": "bedita"
}
```

I campi di input dipendono dall'attività registrata; i riferimenti esterni e la callback sono opzionali e non richiedono BEdita.

### 9.3 Configurazione, prompt e modelli

| Metodo e percorso proposti | Dati e comportamento |
|---|---|
| `GET /configurations` e `/{key}` | Valori correnti accessibili, default, schema e versione concorrente |
| `PATCH /configurations/{key}` | Modifica validata della personalizzazione, con versione attesa; effetto sui nuovi job |
| `POST /configurations/{key}/reset` | Rimuove personalizzazioni indicate, con versione attesa; torna ai default correnti |
| `GET /prompts` e `/{key}/revisions` | Template correnti, variabili e storico delle modifiche |
| `PUT /prompts/{key}` | Salva personalizzazione corrente e storico nella stessa operazione, con versione attesa |
| `POST /prompts/{key}/reset` | Torna al file del progetto, conservando storico e controllo concorrenza |
| `POST /prompts/{key}/render` | Anteprima con revisione e variabili, senza inferenza |
| `GET /models` | Modelli consentiti, provider, capacità e prezzi configurati; identificativi locali quando disponibili |
| `GET /health/live` e `/health/ready` | Processo e dipendenze indispensabili, senza segreti |

Default e template iniziali provengono dal progetto; nessuna importazione DB obbligatoria. Personalizzazioni API entro gli schemi registrati. Ripristinare un prompt storico equivale a salvarne il contenuto come nuova versione corrente; lettura puntuale dello storico nel router prompt. Nessun endpoint di attivazione richiesto. Nomi dei percorsi e payload sono proposte da finalizzare; conservare lettura/schema/reset e catalogo provider come capacità legacy. Le metriche aggregate sono esposte da `GET /usage`, filtrabili per periodo, attività, modello e versione/impronta del prompt, con permesso dedicato.

### 9.4 Conoscenza e conversazioni

CRUD sotto `/collections` e `/collections/{id}/documents`; documenti con origine/ID esterno per sincronizzazione BEdita. Ingestione e reindicizzazione sono attività e restituiscono run. `POST /search` riceve raccolta, query, filtri tipizzati, modalità e limite; restituisce documenti/chunk/revisioni e punteggi dichiarati.

`POST /conversations`, `GET /conversations/{id}`, `GET/POST /conversations/{id}/messages`; il feedback su un messaggio usa `POST /runs/{id}/feedback` dell'esecuzione che lo ha prodotto. L'invio crea un'esecuzione della chat configurata e collega la risposta alla conversazione. Controllo della revisione per invii concorrenti; fonti e consumi leggibili senza ricostruire lo stream. L'eventuale route breve di chat invoca lo stesso servizio.

Riassunto, analisi strutturata e trascrizione si espongono come attività con schemi dichiarati; eventuali endpoint di comodità restano adattatori sottili.

### 9.5 Revisione, valutazione ed esportazione

| Metodo e percorso proposti | Dati e comportamento |
|---|---|
| `GET /runs/{id}/calls` e `/traces` | Chiamate, tentativi e contenuti autorizzati; scadenza esplicita se eliminati |
| `POST /reviews`, `GET /reviews` e `/{id}` | Annotazione, correzione target, valutazione e provenienza del revisore |
| `GET/POST /datasets` e `/{id}/revisions` | Dataset e revisioni dei casi con target, fonti e split |
| `GET/POST /experiments` | Definizione/confronto delle varianti e avvio come run con budget |
| `GET /experiments/{id}/results` e `/report` | Risultati per caso e confronto aggregato con copertura/errori |
| `POST /datasets/{id}/exports` | Esportazione di una revisione/selezione approvata tramite run |
| `GET /datasets/{id}/exports/{export_id}` | Manifest, provenienza e riferimenti ai file prodotti |

Un esperimento non modifica automaticamente il prompt corrente. Adottare il risultato è una scelta esplicita tramite il normale salvataggio del prompt, con storico; nessun flusso distinto di promozione obbligatorio. Le UI consumano queste API anche direttamente. Il Manager BEdita è una possibile interfaccia, non un requisito delle funzioni di valutazione.

### 9.6 Scambio di dati con il plugin BEdita (opzionale)

Questa sezione specifica l'adattatore BEdita. Per accesso diretto il frontend usa avvio, stato, SSE, file e revisione delle API generiche; callback e importazione in BEdita non sono richieste. I backend diversi da BEdita possono utilizzare le stesse notifiche webhook.

Il plugin chiama le API del servizio Brevia configurato. Attività, mappature, autenticazione e importazione dei risultati sono configurate nel progetto utilizzatore.

L'avvio porta un riferimento esterno opaco (oggetto, revisione, tipo operazione) e una chiave di idempotenza persistita dal plugin. Brevia restituisce run e riferimenti ai file. Callback proposta: `event_id`, `event_type`, `run_id`, stato terminale, riferimento esterno e link autorizzati al risultato; firma del corpo e timestamp verificati dal plugin. I retry mantengono lo stesso ID evento, aggiornando il timestamp/firma dell'invio. Un polling recupera eventi mancati.

Se un progetto sceglie l'importazione tramite plugin (la scelta avviene all'integrazione), il plugin registra la ricezione in modo durevole e poi importa i file con un job BEdita; deduplica per evento e file. L'importazione si può ritentare senza rigenerare. Se la revisione dell'oggetto esterno è cambiata, il risultato è conservato come superato e non sostituisce quello corrente. Distinguere `generation_completed`, `artifact_imported` e approvazione nel backend applicativo.

Le correzioni strutturate e i feedback dell'utente si inviano con `POST /runs/{id}/feedback` (§9.0), preservando l'output originale e la provenienza. Caricare un PPTX/Word corretto non produce automaticamente coppie input/target: l'estrazione delle differenze e la trasformazione in esempi revisionati sono funzioni di progetto da definire.

---

### 9.7 Endpoint esistenti: inventario e possibili adattamenti

Elenco ricavato dai decoratori in `brevia/routers/` della 0.15.2 (`81ae7d6`). Le indicazioni di conservazione nella tabella sono ipotesi per eventuali adattatori legacy, non obblighi di nomenclatura o formato del nucleo 1.0. La scelta degli endpoint mantenuti sarà fatta nella fase di compatibilità/migrazione, salvo le decisioni già esplicite sull'autenticazione. Gli adattatori chiameranno gli stessi servizi delle nuove API, senza duplicare il motore.

| Metodi e percorsi attuali | Trattamento nella 1.0 |
|---|---|
| `POST /chat`, `/prompt`, `/completion`, `/search` | Conservare funzioni e formati; `/prompt` resta alias già deprecato. Per `/chat` mantenere anche lo stream testo + JSON finale; SSE nuovo soltanto con scelta esplicita |
| `GET /chat_history`, `/chat_history/sessions`; `POST /evaluate` | Adattare conversazioni e feedback al formato esistente; definire i controlli di accesso senza perdere filtri/sessioni |
| `GET/POST /collections`; `GET/PATCH/DELETE /collections/{uuid}` | Conservare CRUD, identificativi e metadati/configurazione; nessun secondo router incompatibile sullo stesso percorso |
| `POST /index`, `/index/upload`, `/index/link`, `/index/metadata` | Adattare alla nuova ingestione; mantenere input e gestione metadati, correggendo acquisizione link e caricamenti non controllati |
| `GET /index/{collection_id}`, `/index/{collection_id}/documents_metadata`; `GET/DELETE /index/{collection_id}/{document_id}` | Adattare documenti/chunk ai risultati attuali; precedenza delle route statiche rispetto a quelle parametriche |
| `POST /summarize`, `/upload_summarize`, `/upload_analyze` | Adattatori delle attività di analisi; scegliere e documentare corrispondenza dei servizi registrati e risposta sincrona/job |
| `GET /jobs`, `/jobs/{uuid}` | Vista compatibile sulle esecuzioni DBOS; mapping stati/filtri/risultati da definire, senza ripristinare il vecchio scheduler |
| `GET/HEAD /config`, `/config/schema`; `POST /config`, `/config/reset` | Conservare lettura, schema, modifica e reset; collegare internamente le revisioni |
| `GET /providers`, `/providers/{provider}` | Conservare catalogo provider/modelli, anche locali; `/models` è un'eventuale estensione |
| `POST /transcribe`; `GET/HEAD /status` | Conservare trascrizione e controllo di salute, compreso `STATUS_TOKEN` |
| `GET/HEAD /download/{file_path:path}` | Non mantenere accesso arbitrario al filesystem. Proposta: tradurre soltanto riferimenti registrati in file autorizzati; altrimenti esplicitare la discontinuità e usare `/files/{id}/content` |

Se si sceglie di mantenere i router legacy, `/collections` e `/search` devono conservare i formati promessi; nuovi comportamenti incompatibili non possono essere montati sopra gli stessi metodi/percorso. `/runs`, `/files`, `/activities` e gli altri percorsi nuovi sono aggiuntivi. Un eventuale prefisso di montaggio appartiene all'applicazione e non è obbligatorio nella libreria.

**Distinzione operativa:** un nome già esistente non rende un endpoint legacy. La 1.0 può riusare `/collections` o `/search` con le specifiche nuove; un vecchio client che richiede i formati 0.x usa invece un adattatore opzionale, da realizzare nella migrazione. L'adattatore traduce richieste/risposte e chiama gli stessi servizi nuovi. La tabella sopra descrive possibili adattamenti, non obblighi della prima versione. Se il vecchio e il nuovo formato occupano lo stesso metodo/percorso e sono incompatibili, il progetto li espone in applicazioni/host distinti o con un prefisso configurato; non li monta entrambi sullo stesso indirizzo. Nessun `/legacy`, doppio router o header di versione obbligatorio ora.

**Versionamento concordato:** nessun `/v1` obbligatorio; API stabili e modifiche additive. Se in futuro servono due formati incompatibili contemporaneamente: header di versione oppure media type in `Accept`, documentando anche cache e client; in alternativa endpoint distinto per una risorsa realmente diversa. Prefisso `/api` o host separato possono organizzare il deployment, ma da soli non versionano i formati. La versione del pacchetto e quella dello schema di un'attività restano distinte dal percorso HTTP. Nessun meccanismo aggiuntivo di versionamento da implementare prima che serva.

## 10. Migrazione dalla 0.x

Rinviata a una fase successiva. La progettazione corrente riguarda componenti, database e API della 1.0 (§§7–9). Le API esistenti restano il riferimento della progettazione (§3.1 e §9.1); analisi puntuale dei client, procedure di trasferimento dati e piano di passaggio verranno definiti separatamente.

**Interfaccia della piattaforma di test (decisione del 13 ottobre 2026):** si aggiorna alle API 1.0 invece di mantenere un adattatore legacy nella libreria. Oggi usa tramite proxy `/chat` (flusso testo + JSON finale), `/chat_history`, `/evaluate`, `/collections`, `/index/*`, `/config`, `/config/schema`, `/config/reset`, `/providers`, `/jobs/{uuid}`, `/upload_analyze`, `/upload_summarize`, `/transcribe` e `/service_usage` (solo l'API della piattaforma); l'editor delle raccolte scrive le chiavi di configurazione 0.15. Le modifiche riguardano editor della configurazione, chat (parsing del flusso nel layer `nuxt-chatbot-layer`), cronologia e job; da pianificare dopo la libreria.

**API della piattaforma di test:** progetto API sulla 0.13 con servizi propri (tramite `/upload_analyze`) ed endpoint `/service_usage` usato dall'interfaccia. Da migrare insieme alla piattaforma di test: servizi come attività registrate, consumi tramite `GET /usage`; piano da definire con la migrazione.

---

## 11. Repository

| Repository | Contenuto |
|---|---|
| `brevia-ai/brevia` (pubblico, MIT) | Brevia ≤ 0.15, riferimento tecnico; ultima versione 0.15.2 |

Le decisioni e le prove di laboratorio da cui derivano le scelte di questa specifica sono riportate qui nei loro risultati.

---

### 11.1 Istruzioni per lo sviluppo con agenti IA

Preparare queste istruzioni insieme al nuovo repository, mantenendo separate le regole generali della libreria dai requisiti dei progetti utilizzatori. File brevi e versionati; specifiche nei documenti autorevoli, senza copiarle integralmente nei prompt di ogni agente.

| File previsto | Responsabilità |
|---|---|
| `AGENTS.md` | Regole comuni: architettura, confini, documenti autorevoli, comandi verificati, autorizzazioni operative e dichiarazione delle verifiche eseguite |
| `CLAUDE.md` | Importazione `@AGENTS.md` e sole eventuali indicazioni specifiche Claude |
| `.github/copilot-instructions.md` | Indicazioni essenziali autonome per Copilot e richiamo alla skill di review; non presumere lettura automatica di tutti i documenti collegati |
| `.github/skills/code-review/SKILL.md` | Procedura di review: difetti concreti, regressioni funzionali/IA e adeguatezza dei test, evidenze e limiti |
| `.github/instructions/*.instructions.md` | Regole per percorsi, solo quando servono: API, persistenza/DBOS, adattatori, test; evitare duplicazioni |
| `CONTRIBUTING.md` | Preparazione, flusso di sviluppo, verifiche concordate, documentazione e gestione delle modifiche incompatibili |
| `.github/PULL_REQUEST_TEMPLATE.md` | Problema, comportamento finale, verifiche effettive, limiti e conseguenze su API/dati |

Le regole comuni non devono divergere tra strumenti. Istruzioni locali per moduli solo dove aggiungono informazioni; skill aggiuntive, MCP e agenti specializzati quando c'è un'esigenza concreta. Nessun obbligo di nuovi strumenti per usare Brevia. Non confondere gli agenti che sviluppano il codice con gli agenti applicativi eseguiti dalla libreria.

Riferimenti: [AGENTS.md per Codex](https://developers.openai.com/codex/guides/agents-md), [memoria/importazioni Claude](https://code.claude.com/docs/en/memory), [istruzioni Copilot](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions), [skill di Copilot code review](https://github.blog/changelog/2026-07-31-copilot-code-review-agent-skills-and-mcp-now-generally-available/). Le istruzioni guidano gli agenti; non sostituiscono vincoli nel codice e verifiche automatiche concordate.

### 11.2 Review e regressioni delle funzionalità IA

La review segue i comportamenti modificati e i test collegati, anche per cambiamenti a prompt, configurazioni, modelli, dipendenze, strumenti o ricerca. Un test superato non dimostra da solo assenza di regressioni.

| Controllo | Criterio |
|---|---|
| Funzionalità interessate | Ricostruire dal diff le conseguenze dirette e indirette e i requisiti da preservare |
| Adeguatezza dei test | Leggere casi e asserzioni: possono rilevare la regressione ipotizzata? Coprono errori, limiti e casi significativi? Segnalare lacune concrete senza chiedere test che duplicano l'implementazione |
| Qualità IA | Valutare correttezza, aderenza alle fonti, output strutturato, strumenti scelti, retrieval, consumi e limiti secondo la funzione coinvolta |
| Modifiche alle aspettative | Segnalare casi rimossi, soglie indebolite o risultati aggiornati soltanto per rendere verde la verifica; un cambio intenzionale richiede motivazione nei requisiti |
| Variabilità | Confrontare criteri e soglie su dataset versionati; identità testuale solo dove il comportamento la richiede. Registrare modelli, prompt, configurazioni e condizioni per confronti interpretabili |
| Evidenze | Distinguere mock, prove deterministiche, valutazioni con modelli reali e revisione umana. I mock non dimostrano qualità del modello; le verifiche non eseguite restano esplicite |

Restano prioritari anche effetti duplicati alla ripresa, idempotenza, revisioni/concorrenza, autorizzazioni/file, migrazioni, capacità dei provider e separazione del dominio dei progetti utilizzatori. La review riporta difetti concreti e verifiche necessarie; non avvia automaticamente test, servizi o chiamate reali/costose. Autorizzazioni di esecuzione distinte dal criterio di review.

La skill di review copre confronti, job, validazione, limiti delle evidenze e controllo esplicito sull'efficacia dei test contro le regressioni. Non si considera verificata online l'attivazione della skill soltanto perché il file è presente.

### 11.3 Stile, struttura e qualità del codice

Regole concordate l'11 ottobre 2026, recepite nel `CONTRIBUTING.md` del repository e richiamate dalle istruzioni degli agenti.

| Area | Brevia 1.0 |
|---|---|
| Stile | Ruff formatter, 4 spazi, obiettivo 88 caratteri; lint Ruff con regole selezionate, sintassi compatibile con le versioni Python supportate |
| Tipi | mypy come controllo principale, rigoroso sul nuovo nucleo; annotazioni complete delle API pubbliche e tipi distribuiti col pacchetto. Validazione degli input distinta dalle annotazioni |
| Nomi e documentazione | Identificatori inglesi e convenzioni Python; docstring per comportamento, errori ed effetti; commenti sulle motivazioni |
| Dimensioni | File preferibilmente entro 300–400 righe, riesame oltre 500; funzioni entro 40–50; attenzione oltre 3 livelli di annidamento o 5–6 parametri. Soglie di review motivate, non blocchi automatici né standard universali |
| Organizzazione | Pacchetto installabile `src/brevia/`, API pubbliche curate, nucleo/adattatori/moduli distinti; dominio dei progetti esterno |
| Dipendenze ed effetti | Configurazioni e servizi espliciti; calcolo separato da I/O; niente stato globale modificabile o I/O all'importazione; astrazioni motivate da variazioni concrete |
| Affidabilità | Errori espliciti, timeout/cancellazione, risorse e concorrenza controllate, idempotenza e checkpoint rispettati; niente fallback silenziosi |
| Modifiche | PR circoscritte; riformattazioni estese e aggiornamenti dipendenze separati dalle modifiche funzionali. Cambi incompatibili dichiarati per API, configurazioni, snapshot e ripresa |
| Verifiche | Formatter/lint/tipi e verifiche concordate previsti dall'avvio del nuovo repository, compresi installazione e uso da applicazione separata; regressioni IA secondo §11.2 |

La libreria parte con tali criteri; Python minimo 3.12 (§11.4). Test e chiamate reali seguono le autorizzazioni operative, non sono autorizzati dalla sola presenza delle istruzioni.

Le soglie non giustificano frammentazioni artificiali; dati dichiarativi, migrazioni e casi parametrizzati possono richiedere eccezioni.

#### Programmazione leggibile e logging dal nucleo iniziale

Scelte approvate: funzioni per operazioni riconoscibili, classi per risorse e comportamenti coerenti, dipendenze esplicite e moduli per funzionalità. Pydantic ai confini da validare, dataclass interne quando utili, dizionari per mappe variabili; niente conversioni o gerarchie prive di necessità. Piccole interfacce `Protocol` per variazioni concrete di modelli/storage; API HTTP sottili sulle operazioni Python. Calcoli e trasformazioni restano separabili da DBOS. Flussi lineari, condizioni leggibili e `async` per attese supportate. uv e `pyproject.toml` per lo sviluppo, lockfile per riproducibilità. Ogni modifica, anche generata da IA, deve essere comprensibile e verificabile da un manutentore umano.

Il logging è requisito del nucleo iniziale: `logging` standard con logger per modulo, configurato centralmente dall'applicazione; formato leggibile in sviluppo e JSON in produzione, console iniziale e conservazione affidata all'ambiente. Identificativi di richiesta/esecuzione/attività propagati ai job collegano eventi di avvio, completamento, durata, retry, timeout, cancellazione e fallimento. Le chiamate ai modelli espongono provider, modello e consumi disponibili.

Livelli con significato uniforme: `DEBUG` diagnosi, `INFO` eventi significativi, `WARNING` problemi recuperabili, `ERROR` operazioni fallite. Causa e stack trace registrati nel punto responsabile senza duplicazioni. Credenziali, token, documenti e prompt/risposte integrali esclusi dai log ordinari, inclusi gli errori delle dipendenze. Log operativi e tracce IA del §7.8 restano distinti e correlati per esecuzione; accessi e conservazione dei dettagli delle tracce sono controllati.

Predisposizione futura OpenTelemetry, verificando prima quanto offerto da Pydantic AI e DBOS per evitare doppia strumentazione. Le regole operative complete sono nel CONTRIBUTING. Queste decisioni non attivano strumenti; restano da fissare campi degli eventi e modalità di propagazione durante la specifica delle esecuzioni.

### 11.4 Pacchetto e repository della libreria — decisioni del 13 ottobre 2026

- **Python:** minimo 3.12, verifiche automatiche su 3.12–3.14. Pydantic AI e Pydantic Evals richiedono almeno 3.11 (verificato su PyPI, ottobre 2026).
- **Un solo pacchetto con tutte le funzioni** (nucleo, API, documenti, analisi, conoscenza e RAG, conversazioni, trascrizione, valutazione, CLI). Le API FastAPI fanno parte del nucleo; il progetto sceglie quali router montare. Extra soltanto per librerie legate a un'infrastruttura specifica: `s3`, `azure`, in futuro `graph`. Un nuovo adattatore si aggiunge con una nuova versione; nel frattempo il progetto può registrarne uno proprio.
- **Dipendenze principali:** Pydantic AI, DBOS, SQLAlchemy e Alembic, psycopg 3, pgvector, FastAPI e uvicorn, pydantic-settings, PyJWT (al posto di `python-jose` della 0.15), lettori PDF e DOCX. Versioni fissate nel lock; licenza di psycopg compatibile con MIT (P9).
- **Ordine di sviluppo** distinto dal disegno del pacchetto: prima consegna in §5.
- **API Python pubblica:** stabile soltanto ciò che si importa da `brevia`; il resto è interno. Pydantic AI e DBOS non sono esposti.
- **Riga di comando:** comando unico `brevia` con sottocomandi (`token`, `db`, `openapi`, `worker`), al posto dei comandi separati della 0.15.
- **Distribuzione:** su PyPI con lo stesso nome della 0.15 (`brevia`), dal ramo `1.x` di `brevia-ai/brevia` (decisione del 19 ottobre 2026). Le versioni della 1.0 precedenti a quella finale sono pre-release: chi installa `brevia` senza versione né `--pre` riceve ancora la 0.15.2, quindi un progetto della 0.15 non passa alla 1.0 per errore. Il template si prende dal repository al tag della release e installa Brevia da PyPI.
- **Compatibilità delle dipendenze (audit del 14 ottobre):** il lock del repository non vincola i consumer. Prima della prima distribuzione: intervalli realmente supportati con limiti alle major dove servono (Pydantic AI ammette cambi incompatibili nelle major e alcuni nelle minor), una run simulata sul wheel installato in un ambiente pulito, una procedura esplicita di aggiornamento e verifica degli adattatori. Resta il pacchetto unico, con moduli e dipendenze interne separati.

Struttura proposta del repository della libreria:

```text
brevia/
├── pyproject.toml, uv.lock, README.md, CHANGELOG.md, CONTRIBUTING.md
├── AGENTS.md, CLAUDE.md, .github/            istruzioni e verifiche (§11.1)
├── src/brevia/
│   ├── __init__.py                           API Python pubblica
│   ├── core/  config/ prompts/ models/ activities/ tools/ files/ access/ tracing/ feedback/
│   ├── documents/                            lettori e struttura del testo
│   ├── analysis/                             summarize, extract, complete
│   ├── knowledge/                            raccolte, indicizzazione, ricerca, RAG
│   ├── conversations/
│   ├── transcription/
│   ├── evaluation/
│   ├── api/                                  router FastAPI sottili
│   ├── cli/
│   ├── db/  tables/ migrations/              schema `brevia`, Alembic
│   └── defaults/prompts/                     prompt predefiniti sovrascrivibili
├── docs/  api/ (OpenAPI) postman/
├── examples/                                 tre esempi minimi (§7.5)
└── tests/  unit/ integration/ ai/
```

Un progetto utilizzatore contiene soltanto configurazione, prompt e codice di dominio (attività, lettori, generatori) e crea l'applicazione montando i router Brevia.

### 11.5 Operatività — decisioni del 13 ottobre 2026

| Aspetto | Decisione |
|---|---|
| Processi | API (FastAPI con uvicorn: richieste e chiamate dirette) e worker (`brevia worker`: job DBOS), stesso codice e stessa immagine, scalabili separatamente. Per installazioni piccole il worker può girare nel processo API. Nella 0.15 i job giravano in `BackgroundTasks` del processo API |
| Configurazione e segreti | Variabili d'ambiente o `.env` (pydantic-settings), come nella 0.15. Segreti mai nei file versionati né nel database |
| Migrazioni | `brevia db upgrade` come passo esplicito del rilascio, prima dell'avvio dei processi; migra lo schema `brevia` (Alembic) e lo schema dei job (DBOS, `dbos` per default). Né il client DBOS né i worker migrano mai: lo fa solo il comando |
| Rilasci con job in corso | Rilasci manuali con procedura «svuota e aggiorna»: il worker smette di prendere nuovi job, si attende la fine di quelli in corso, si aggiorna e si riavvia. DBOS riprende un workflow interrotto solo con la stessa versione dell'applicazione e lo stesso `executor_id` del worker; con un'altra versione il job resta `PENDING`, senza diventare fallito da solo. All'avvio un worker della nuova versione registra come falliti, rilanciabili con `retry` (§7.5), i job interrotti di un'altra versione e li annulla nel motore. I job accodati non hanno versione e li esegue la nuova versione. Un worker che si avvia rende la propria versione quella corrente, anche tornando a una versione precedente. Worker di due versioni contemporaneamente non sono supportati. La versione la imposta Brevia in modo esplicito: quella calcolata da DBOS deriva dal sorgente dei workflow e, con un workflow generico, non cambia quando cambiano le attività. È `BREVIA_APP_VERSION` oppure, se non impostata, la versione di Brevia (`brevia-<versione>`): con la ripartenza da capo il motore riprende soltanto il workflow di Brevia, e il cambio di un'attività è intercettato dalla sua `version` (decisione del 16 ottobre 2026). Ogni worker ha un `executor_id` stabile. Comportamento verificato il 14 ottobre e implementato nella tappa 3. Rilascio affiancato o patching DBOS rinviati a rilasci automatici o carichi elevati ([DBOS](https://docs.dbos.dev/java/tutorials/upgrading-workflows)) |
| Pulizia | Job pianificato con DBOS per eliminare tracce e file scaduti secondo la conservazione del progetto; sostituisce `cleanup_jobs` della 0.15 |
| Salute e log | `/health/live`, `/health/ready`, `/status`; log JSON in produzione (§11.3) |
| Installazione di riferimento | `Dockerfile` e `docker-compose` di sviluppo con PostgreSQL + pgvector, API e worker. Infrastruttura reale decisa dal progetto utilizzatore |

### 11.6 Criteri di verifica della prima consegna — decisione del 13 ottobre 2026

Da eseguire soltanto su autorizzazione; per ogni criterio si dichiara il tipo di prova (simulata, con database reale, con modello reale; §11.2).

| Area | Criterio |
|---|---|
| Installazione | Un'applicazione separata installa Brevia, registra un'attività, monta i router e la esegue |
| Configurazione | Precedenza dei livelli rispettata; override vietati respinti; dopo un reset i nuovi job usano i default, quelli avviati il proprio snapshot |
| Job | Stessa chiave → stesso job; stessa chiave con dati diversi → 409; worker interrotto a metà → il job riparte da capo con gli stessi valori, al massimo 3 volte; annullamento anche durante una chiamata; `retry` |
| Interruzioni (audit del 14 ottobre) | Arresto fra registrazione e accodamento; durante l'attività (il job riparte da capo, l'esito si scrive una volta sola); dopo la pubblicazione di un file ma prima dell'esito; risposta persa al chiamante dopo l'accettazione; annullamento durante una chiamata o una pubblicazione; rilascio con job accodati o interrotti |
| Snapshot e ripartenza | Un job ripartito dopo un arresto usa la stessa configurazione e gli stessi prompt della prima esecuzione, letti dal checkpoint, anche se nel frattempo progetto o personalizzazioni sono cambiati |
| Accessi | JWT come nella 0.15, token già emessi validi; con `per-caller` un chiamante non vede job e file di un altro |
| File | Caricamento con impronta verificata, accesso solo per identificativo. Prima consegna (16 ottobre 2026): input scaricati da host ammessi con impronta verificata se fornita, output accessibili soltanto attraverso il job |
| Modelli | Output strutturato validato e ritentato; limiti rispettati; costo `null` con prezzo sconosciuto |
| Tracce | Chiamate al modello e agli strumenti registrate; nessun segreto nei log |
| Analisi e feedback | `summarize` ed `extract` su documenti di esempio; feedback registrato su un'esecuzione |
| Documentazione | OpenAPI generata e collezione Postman funzionante; tre esempi eseguibili (attività deterministica, generazione validata, job con file e ripartenza dopo un'interruzione), ciascuno con ciò che Brevia garantisce e ciò che resta al consumer |
| Qualità (audit del 14 ottobre) | Piccolo corpus versionato con casi normali, ambigui, incompleti e negativi; misure separate di validità dello schema, fedeltà alle fonti, completezza, tentativi, costo e latenza. Le prove del laboratorio bastano per la direzione, non dimostrano qualità generale |

I criteri di un progetto utilizzatore restano nella sua documentazione (§5).

## 12. Punti aperti

**Stato al 13 ottobre 2026:** punto 0 chiuso (§12.2). Le voci seguenti indicano gli aspetti ancora aperti, per lo più di implementazione o esterni; nessuna implementazione è implicita.

- **P1 — Esecuzione dei job:** DBOS confermato; schema e confini in §8; rilasci con procedura «svuota e aggiorna» (§11.5). Riconciliazione dello stato e job accodati o interrotti al rilascio implementati nella tappa 3 (§§8.3, 11.5).
- **P2 — Ricerca ibrida:** confermata nella 1.0 (4.2), con fusione esplicita; reranking opzionale. Strategie `fixed`/`agent`/`full_context`, indicizzazione e strumenti in §§7.5 e 7.7; indici a grafo predisposti, non inclusi.
- **P3 — Trascrizione audio:** modulo facoltativo con adattatori (§7.7). I modelli OpenAI attuali, incluso `whisper-1`, sono rimossi dall'API dal 26 febbraio 2027: adattatore da realizzare sui sostituti indicati.
- **P4 — Formati di ingestione:** lettori PDF, DOCX e testo nella prima consegna per l'analisi; Markdown e DOCX previsti anche per il RAG; XLSX/PPTX lettori opzionali secondo necessità. Implementazioni concrete da scegliere; nessuna dipendenza aggiuntiva per formati difficili già approvata.
- **P5 — Autorizzazione:** decisa (§7.9): chiamante, `end_user`, politiche `shared` e `per-caller` con default `per-caller`. Implementata nella tappa 4 in forma non sostituibile, con amministratori; regole per attività o operazione quando un progetto le chiede.
- **P6 — Modelli iniziali:** OpenAI, Anthropic e Ollama tramite Pydantic AI; definire matrice delle capacità e opzioni validate. I modelli concreti appartengono al progetto utilizzatore.
- **P7 — Licenza:** chiuso: MIT (19 ottobre 2026).
- **P8 — Copyright:** chiuso: nel `LICENSE` della 1.0 Brevia AI (dal 2023) e Atlas (dal 2026).
- **P9 — Licenze delle dipendenze:** chiuso: psycopg (LGPL-3.0) è una dipendenza installata, non inclusa nel pacchetto, ed è compatibile con la licenza MIT.
- **P10 — Libreria di base:** chiuso per questa progettazione: Pydantic AI + DBOS. LlamaIndex non incluso; valutabile in futuro soltanto per lettori di formati difficili (§4.1).
- **P11 — Integrazione BEdita:** architettura e responsabilità del plugin in §§6 e 9.6; da dettagliare schema locale di correlazione, firma callback e mapping del progetto. Compatibilità delle versioni BEdita/CakePHP da dichiarare nel plugin.
- **P12 — Installazione e gestione:** processi, configurazione, migrazioni, rilasci, pulizia e installazione di riferimento decisi (§11.5); pacchetto in §11.4. Infrastruttura, fornitori e vincoli sui dati nel progetto utilizzatore; distribuzione con la licenza (P7).
- **P13 — Storage e deployment:** filesystem persistente per la prima consegna; adattatori previsti filesystem/S3/Azure Blob Storage e integrazione per file gestiti da sistemi esterni (§7.6). FileRef e operazioni comuni decisi (§7.6); nella prima consegna input da URL e output nella cartella dell'esecuzione, con pulizia e retention degli output (§7.6, decisione del 16 ottobre 2026); retention delle tracce configurabile per progetto (§7.8); formato dei riferimenti e trasferimenti da BEdita all'integrazione. Schema Brevia e schema DBOS nello stesso database per accodamento atomico; co-locazione con BEdita opzionale, con ruoli/migrazioni separati. Deployment definitivo scelto dal progetto.
- **P14 — Revisione e valutazione:** retention predefinita configurabile per progetto, nessuna UI nella 1.0, rubriche iniziali definite (§7.8); nella prima consegna soltanto il feedback strutturato sulle esecuzioni (§§5, 9.0). Fine tuning futuro: predisposizione dati/export, framework di training da scegliere successivamente.
- **P15 — Specifiche delle funzioni:** chiuso con il punto 0: firme (§7.5), API ed errori (§§9.0–9.1), schema (§8), verifiche (§11.6). Nomi definitivi, payload e DDL in implementazione.
- **P16 — Autenticazione: deciso.** Conservare il funzionamento della vecchia Brevia (§7.9). Non progettare un nuovo sistema di identità/sessioni come prerequisito. Libreria PyJWT; autorizzazioni nella politica di accesso (P5).

### 12.1 Cosa resta per l'implementazione

| Fase | Da fare |
|---|---|
| Allineamento di un dimostratore | Svolto il 13 ottobre 2026 su un prototipo delle interfacce: attività registrate, `RunContext`, configurazione e snapshot, `FileRef` su filesystem, errori di §9.1, limiti per esecuzione. Mitigazione dei rifiuti delle citazioni: messaggi di correzione precisi e ripiego per sezione |
| Prima consegna della libreria | In corso: avanzamento in [`docs/IMPLEMENTATION.md`](../IMPLEMENTATION.md) |
| Prima consegna della libreria | Strumento candidato per gli agenti: citazione per numero di frase (la fonte è divisa in frasi numerate, il modello indica i numeri e il testo esatto lo recupera il codice), da decidere insieme agli strumenti `open`/`find` di §7.5 per non duplicarli; non necessario alla prima consegna |
| Prima consegna della libreria | Payload e nomi definitivi; OpenAPI e collezione Postman |
| Prima della produzione (audit del 14 ottobre) | Regola di conservazione per ogni copia dei dati (§7.8); compatibilità delle dipendenze (§11.4); limiti fra run misurati con un carico rappresentativo: concorrenza per worker e per provider, rifiuto del sovraccarico delle code, connessioni moltiplicate per processi, memoria di documenti, snapshot e tracce, arresto ordinato e tempo di svuotamento, lavori CPU o Office che continuano dopo un timeout. Le code DBOS limitano gli avvii dei job, non le richieste ai modelli. Backup e ripristino coerenti di `brevia` e `dbos`. Niente microservizi, partizionamenti o cache distribuite prima delle misure |
| Esterni | Integrazione BEdita (caricamento o adattatore, polling o callback) |
| Non bloccanti | RAG, conversazioni, valutazione completa, trascrizione, indici a grafo, migrazione dei progetti 0.x |

### 12.2 Punto 0 — completamento delle specifiche generali

La fase corrente riguarda Brevia 1.0 general purpose, non soltanto le funzioni della prima consegna. Sequenza: completare specifiche generali → allineare un dimostratore → implementare un sottoinsieme della libreria necessario alla prima consegna → creare il servizio utilizzatore con la libreria e il job allineato. I requisiti dei progetti utilizzatori non determinano il modello generale.

Per ogni blocco: leggere il codice della vecchia Brevia, identificare capacità da conservare e limiti, proporre schemi/comportamento/errori con esempi generici, confermare le decisioni e consolidarle qui. Stack, database e autenticazione già concordati non si riaprono automaticamente. Nessun test o adeguamento del dimostratore autorizzato dalla sola progettazione.

| Ordine | Specifiche da chiudere |
|---|---|
| 1 | Configurazioni, prompt, reset, storico e snapshot — chiuso nelle decisioni (§§7.2–7.3) |
| 2 | Modelli, strumenti e attività: interfacce Python, capacità, input/output, limiti — chiuso nelle decisioni (§§7.4–7.5) |
| 3 | Esecuzioni, file e accesso: stati, ripresa, idempotenza, storage, autorizzazioni — chiuso nelle decisioni (§§7.5, 7.6, 7.9) |
| 4 | Moduli funzionali: RAG, conversazioni, analisi, trascrizione, revisione/valutazione — chiuso nelle decisioni (§§7.5, 7.7, 7.8) |
| 5 | Consolidamento API, schema dati e vincoli, pacchetto e operatività — chiuso nelle decisioni (§§5, 8, 9.0, 11.4, 11.5) |

Chiusura del punto 0: responsabilità, dati, comportamento ed errori definiti; Python/API/database coerenti; separazione tra versione completa, sottoinsieme minimo e sviluppi successivi; criteri di verifica documentati. DDL eseguibile e migrazioni sono implementazione successiva, non un motivo per ridiscutere PostgreSQL e la separazione degli schemi Brevia/DBOS.

**Punto 0 chiuso il 13 ottobre 2026** nelle decisioni: blocchi 1–5, firme Python (§7.5), catalogo degli errori (§9.1), criteri di verifica (§11.6), separazione tra prima consegna (§5) e versione completa. Dettagli residui (nomi definitivi, payload, DDL) si fissano in implementazione senza riaprire le decisioni.

**Blocco 1 — lettura legacy dell'11 ottobre 2026.** Riletti `brevia/models.py`, `settings.py`, `prompts.py`, `routers/config_router.py` e i richiami di `query.py` nel checkout della 0.x. Nessun test.

| Pattern osservato | Trattamento nella 1.0 |
|---|---|
| Default, contesto e richiesta; configurazione per ogni uso del modello | Conservare capacità e personalizzazione; composizione esplicita secondo §7.2 |
| Prompt da file, variabili dichiarate, messaggi distinti e personalizzazione | Conservare il principio; formati indipendenti da LangChain, storico DB e snapshot |
| Lettura/schema/modifica/reset via API | Conservare le funzioni; reset come rimozione della personalizzazione, distinto da `null` |
| `get_model_config` restituisce il primo valore non `None`, anche un dizionario intero | Non replicare questo algoritmo: distingue male assenza/null e non realizza la composizione concordata |
| Tabella `config` aggiornata sul posto | Conservare personalizzazione corrente con controllo concorrenza; snapshot per esecuzione e storico dei prompt, senza revisioni generiche obbligatorie |
| Cache `get_settings()` invalidata nel processo scrivente | Specificare coerenza API/worker, senza presumere invalidazione condivisa |
| Errore di lettura DB registrato e prosecuzione su altre impostazioni | Specificare il fallimento esplicito quando non si può risolvere la configurazione richiesta |
| Loader LangChain, funzione privata per few-shot e `pop` su dizionari ricevuti | Adattatori propri, esempi tipizzati, configurazione risolta non modificata dai loader |

**Proposte residue dopo la semplificazione concordata:** default versionati separatamente, revisioni di configurazione, binding obbligatori e attivazioni coordinate sono rimossi dal piano corrente. Resta lo snapshot autosufficiente; le proposte seguenti non sono nuovi prerequisiti.

| Proposta | Scopo e comportamento |
|---|---|
| Risoluzione ispezionabile senza inferenza | Diagnostica facoltativa dei valori effettivi e loro origine; segreti esclusi |
| Versione dello schema e validazione rigorosa | Rifiutare campi sconosciuti nei blocchi tipizzati; opzioni provider in un blocco esplicito validato dall'adattatore. Conversioni ammesse dichiarate; versioni incompatibili respinte, non corrette silenziosamente |
| Diagnostica delle modifiche ai prompt | Confronto nello storico e collegamento facoltativo alle valutazioni; il normale salvataggio cambia il valore corrente |
| Template con superficie limitata — confermato | Sostituzione di variabili dichiarate, dati preparati dal codice (§7.3). Motori con condizioni/cicli rimandati a un'esigenza concreta |
| Messaggi ed esempi strutturati | Prompt come sequenza tipizzata di messaggi/parti; esempi few-shot espliciti, riferimenti a contenuti multimodali senza binari nelle configurazioni. Mappatura delle capacità affidata agli adattatori |

Fonti primarie consultate nell'ottobre 2026: [validazione Pydantic](https://docs.pydantic.dev/latest/concepts/models/), [strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/), [concorrenza/versionamento SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/versioning.html), [limiti della sandbox Jinja](https://jinja.palletsprojects.com/en/stable/sandbox/). Sono basi tecniche delle proposte, non prova della loro implementazione né obbligo di aggiornare le dipendenze installate. Il controllo della revisione va garantito dalla transazione: il solo contatore ORM non copre ogni forma di aggiornamento.

### Terminologia usata nel progetto

Per **specifiche di ingresso, uscita e comportamento** (in gergo, «contratti») si intende: quali dati riceve una funzione o API, quali restituisce, quali errori segnala e quali regole deve rispettare. Esempio: avvio di un job, identificativi dei file richiesti, identificativo restituito, stati consultabili ed errori. Per le funzioni esistenti si parte dalle specifiche ricavate dal codice della vecchia Brevia; si descrivono quelle nuove e le differenze necessarie. Non significa riscrivere tutte le API.

## 13. Criteri di lavoro

Stato, tappe e prossimi passi sono in [`docs/IMPLEMENTATION.md`](../IMPLEMENTATION.md).

**Criteri da mantenere:** semplicità, codice leggibile e strato Brevia piccolo; vecchia Brevia come riferimento tecnico e funzionale (§3.1), con progetto moderno, scalabilità da verificare e punti di estensione concreti per evoluzioni future. Nessuna infrastruttura speculativa. Lettura e salvataggio su filesystem, BEdita, S3 e Azure come casi base, altri sistemi aggiungibili. Decisioni già confermate da non riaprire implicitamente; dettagli residui da chiudere senza presentare proposte come implementazioni.

**Regole operative:** nessun test o esperimento senza richiesta; descrivere distintamente proposte, codice ed evidenze. Documentazione, materiali, scadenze ed esiti dei progetti utilizzatori restano nei loro repository; nessun workflow aziendale entra nella libreria.
