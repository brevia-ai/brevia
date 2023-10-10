# Brevia

Il repository contiene un progetto di LLM API minimale in Python basato su LangChain per l'interazione con LLM e FastAPI per l'interfaccia API.

## Requirements

E' necessaria una versione di Python 3.10 o superiore e [Poetry](https://python-poetry.org/docs/#installation)

Si consiglia di utilizzare il virtualenv nel progetto.
Verifica le impostazioni con

```bash
poetry config --list
```

Verifica che la configurazione `virtualenvs.in-project` sia `true` altrimenti lancia:

```bash
poetry config virtualenvs.in-project true
```

## Setup

* installa le dipendenze lanciando `poetry install`, verrà automaticamente creato un virtualenv nel folder `.venv`
* attiva quindi il virtualenv lanciando il comando `poetry shell`
* copia il file `.env.sample` in `.env` e valorizza le variabili di ambiente, soprattutto `OPENAI_API_KEY` con la secret key di OpenAI e `PGVECTOR_*` vedi la sezione [Database](#database)

## Aggiornamento pacchetti

Si usa `poetry update` che aggiornerà il file di lock `poetry.lock`
Per cambiare versioni delle dipendenze si può anche modificare direttamente `pyproject.toml` nella seziona `[tool.poetry.dependencies]`

## Database

Lancia `docker compose --profile admin up` per fare partire le immagini docker di postgres+pgvector e pgadmin.

Col browser apri `pgadmin` all'indirizzo http://localhost:4000

La porta `4000` è configurabile con la var di ambiente `PGADMIN_PORT` nel file `.env`.

* fai login su pgadmin con credenziali `PGADMIN_DEFAULT_*` del file .env
* crea una connessione con `Add New Server` impostando
  * in General `brevia` o altro nome a scelta (`PGVECTOR_DATABASE`)
  * in Connection come host name `pgdatabase` e scegli uno Username a Password (`PGVECTOR_USER`, `PGVECTOR_PASSWORD`)

Lancia le migrations per creare lo schema iniziale con [Alembic](https://alembic.sqlalchemy.org)

```bash
alembic upgrade head
```

## Test setup

Per verificare che il setup sia corretto lanciare

```py
python brevia/scripts/csv_import.py data/test_min_dataset.csv test
```

Per creare indicizzazione da un CSV di test con una sola riga.
Se alla fine in output trovate
`Index collection {name} updated with {n} documents and {n} texts`
allora è tutto ok.

## Import/export di collections

Per esportare usare lo script `export_collection.py`dal virtual env

```bash
python export_collection.py /path/to/folder collection
```

Dove

* `/path/to/folder` è il path dove verranno creati i 2 file CSV, uno per record di collection e altro con embeddings
* `collection` è il nome della collection

Per esportare usare lo script `import_collection.py`dal virtual env

```bash
python import_collection.py /path/to/folder biologia
```

Dove

* `/path/to/folder`  è il path dove sono cercati i 2 file CSV da caricare, uno per record di collection e altro con embeddings
* `collection` è il nome della collection

NB: per questi script è necessario il client postgres `psql`, i parametri di connessione saranno letti da var di ambiente (file `.env`)

## API server

Per far partire il server, digita il seguente comando da virtualenv:

```bash
uvicorn main:app --reload
```

Il server inizierà ad eseguire sulla porta `8000`.

## Docker

Per lanciare l'immagine docker delle API insieme al servizio Postgres usa

```bash
docker compose --profile api up
```

Per lanciare l'immagine docker di PgAdmin insieme a Postgres usa

```bash
docker compose --profile admin up
```

Per lanciare l'immagine docker dell'APP e delle API insieme a Postgres

```bash
docker compose --profile app up
```

La versione dell'immagine docker utilizzata è definita nel file `.env` nelle variabili d'ambiente `API_VERSION` per le API e `APP_VERSION` per l'app

## Tracing log

Per abilitare la funzionalità di trace delle chiamate, integrata in langchain aggiungere/scommentare la variabile di sistema su `app.py`:

```py
environ["LANGCHAIN_HANDLER"] = langchain
```

assicurandosi che venga eseguita prima di qualsiasi operazione sulle librerie di langchain.

Far partire il server tramite immagini docker dalla console:

```bash
langchain-server
```

Navigare su `http://localhost:4173/` per visualizzare il pannello di controllo dei trace e utilizzare la sessione di default.

Per cambiare il nome della sessione impostare:

```py
.environ ["LANGCHAIN_SESSION"] = "my_session" # Assicurandoti che questa sessione esista effettivamente. È possibile creare una nuova sessione nell'interfaccia utente.
```

Mentre per cambiare dinamicamente sessione nel codice NON impostare la variabile d'ambiente LANGCHAIN_SESSION, usa invece:

```py
langchain.set_tracing_callback_manager(session_name = "my_session")
```

## Access Tokens

There is a built-in basic support for access tokens for API security

Access tokens are actively checked via `Authoritazion: Bearer <token>` header if a `TOKENS_SECRET` env variable has been set.
You may then generate a new access token using:

```bash
poetry run create_token --user {user} --duration {minutes}
```

If the env `TOKENS_SECRET` variable is set token verification is automatically performed on every endpoint using `brevia.dependencies.get_dependencies` in its dependencies.

The recommended way yo generate `TOKENS_SECRET` is by using openssl via cli like

```bash
openssl rand -hex 32
```

You can also define a list of valid users as a comma separated string in the `TOKENS_USERS` env variable.

Setting it like `TOKENS_USERS="brevia,gustavo"` means that only `brevia` and `gustavo` are considered valid users names. Remember to use double quotes in a `.env` file.
