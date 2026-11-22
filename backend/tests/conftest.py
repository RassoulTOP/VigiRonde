import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db as dbmod
from app.config import get_settings
from app.main import app
from app.models import Company, User
from app.security import hash_password


@pytest.fixture(scope="module")
def client():
    engine = create_engine(get_settings().test_database_url)
    dbmod.Base.metadata.drop_all(engine)
    dbmod.init_db(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[dbmod.get_db] = override
    with TestSession() as s:
        c = Company(name="Test Sécurité")
        s.add(c)
        s.flush()
        for email, role in [("chef@test.fr", "superviseur"), ("agent@test.fr", "agent"), ("autre@test.fr", "agent")]:
            s.add(User(company_id=c.id, email=email, full_name=email.split("@")[0].title(), role=role,
                       qualifications=["CQP_APS"], password_hash=hash_password("motdepasse123")))
        s.commit()
    # Pas de lifespan : la base de test est déjà initialisée
    yield TestClient(app)
    app.dependency_overrides.clear()


def login(client, email):
    r = client.post("/auth/login", data={"username": email, "password": "motdepasse123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


