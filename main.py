"""API endpoint definitions with FastAPI."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from brevia.routers.app_routers import add_routers
from brevia.utilities.openapi import metadata


meta = metadata(f'{Path(__file__).parent}/pyproject.toml')
app = FastAPI(**meta)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["*"],
)
add_routers(app)


if __name__ == '__main__':
    run_opts = {
        'reload': True,
        'reload_excludes': ['*.log', './history/*'],
        'reload_dirs': ['brevia/'],
    }
    ROOT_PATH = str(Path(__file__).parents[0])
    log_config = f'{ROOT_PATH}/log.ini'
    if Path(log_config).exists():
        run_opts['log_config'] = log_config
        run_opts['reload'] = False  # avoid continuous `change detected` logs for now
    uvicorn.run('main:app', **run_opts)
