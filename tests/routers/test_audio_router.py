"""Status router tests"""
from pathlib import Path
from fastapi.testclient import TestClient
from fastapi import FastAPI
from brevia.routers import audio_router
from brevia import models

app = FastAPI()
app.include_router(audio_router.router)
client = TestClient(app)


def test_audio_transcriptions():
    """Test POST /transcribe success"""

    test_path = Path(__file__).parent.parent
    file_path = f'{test_path}/files/silence.mp3'
    handle = open(file_path, 'rb')
    with TestClient(app) as client:
        response = client.post(
            '/transcribe',
            files={'file': handle},
            data={'language': 'it'},
        )
        assert response.status_code == 200
        data = response.json()
        assert data is not None
        assert data['text'] == models.LOREM_IPSUM
