"""Username/email authentication and both HTTP login contracts."""

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from landppt.auth.auth_service import AuthService
from landppt.database.models import Base, User, UserSession


@pytest.fixture
def login_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=[User.__table__, UserSession.__table__])
    with sessionmaker(bind=engine, expire_on_commit=False)() as db:
        yield db
    engine.dispose()


def add_user(
    db,
    username="demo-user",
    email="Demo+Tag@Example.COM",
    password="correct password",
    active=True,
):
    user = User(username=username, email=email, is_active=active)
    user.set_password(password)
    db.add(user)
    db.commit()
    return user


@pytest.mark.parametrize(
    "identifier",
    [
        "demo-user",
        " demo-user ",
        "Demo+Tag@Example.COM",
        "demo+tag@example.com",
        " DEMO+TAG@EXAMPLE.COM ",
    ],
)
def test_usernames_and_normalized_emails_authenticate_the_same_user(
    login_db, identifier
):
    user = add_user(login_db)
    assert (
        AuthService().authenticate_user(login_db, identifier, "correct password").id
        == user.id
    )
    assert user.last_login is not None


@pytest.mark.parametrize(
    "identifier,password",
    [
        ("", "correct password"),
        ("  ", "correct password"),
        ("unknown", "correct password"),
        ("missing@example.com", "correct password"),
        ("Demo-User", "correct password"),
        ("demo+tag@example.com", "incorrect"),
        ("demo-user", "incorrect"),
    ],
)
def test_invalid_credentials_do_not_authenticate_or_update_last_login(
    login_db, identifier, password
):
    user = add_user(login_db)
    assert AuthService().authenticate_user(login_db, identifier, password) is None
    assert user.last_login is None


@pytest.mark.parametrize("identifier", ["demo-user", "DEMO+TAG@EXAMPLE.COM"])
def test_disabled_accounts_cannot_login_by_username_or_email(login_db, identifier):
    user = add_user(login_db, active=False)
    assert (
        AuthService().authenticate_user(login_db, identifier, "correct password")
        is None
    )
    assert user.last_login is None


def test_password_whitespace_and_legacy_username_whitespace_are_preserved(login_db):
    user = add_user(login_db, username=" legacy user ", password=" secret ")
    auth = AuthService()
    assert auth.authenticate_user(login_db, " legacy user ", " secret ").id == user.id
    assert (
        auth.authenticate_user(login_db, "demo+tag@example.com", " secret ").id
        == user.id
    )
    assert auth.authenticate_user(login_db, "demo+tag@example.com", "secret") is None


@pytest.mark.parametrize("active", [True, False])
def test_exact_username_takes_priority_over_another_accounts_email(login_db, active):
    named_user = add_user(
        login_db,
        username="owner@example.com",
        email="different@example.com",
        password="username password",
        active=active,
    )
    email_owner = add_user(
        login_db,
        username="email-owner",
        email="owner@example.com",
        password="email password",
    )
    auth = AuthService()
    result = auth.authenticate_user(login_db, "owner@example.com", "username password")
    assert (result.id if result else None) == (named_user.id if active else None)
    assert (
        auth.authenticate_user(login_db, "owner@example.com", "email password") is None
    )
    assert (
        auth.authenticate_user(login_db, "email-owner", "email password").id
        == email_owner.id
    )


def test_case_ambiguous_legacy_emails_are_rejected_without_breaking_username_login(
    login_db,
):
    first = add_user(login_db, username="first-user", email="Duplicate@Example.COM")
    second = add_user(login_db, username="second-user", email="duplicate@example.com")
    auth = AuthService()
    assert (
        auth.authenticate_user(login_db, "DUPLICATE@EXAMPLE.COM", "correct password")
        is None
    )
    assert first.last_login is second.last_login is None
    assert (
        auth.authenticate_user(login_db, "first-user", "correct password").id
        == first.id
    )
    assert (
        auth.authenticate_user(login_db, "second-user", "correct password").id
        == second.id
    )


@pytest.fixture
def login_client(login_db, monkeypatch):
    routes = importlib.import_module("landppt.auth.routes")
    auth = AuthService()
    monkeypatch.setattr(auth, "_schedule_session_cache_write", lambda *args: None)
    monkeypatch.setattr(routes, "_get_client_ip", lambda request: None)
    monkeypatch.setattr(routes, "_turnstile_template_ctx", lambda: {})

    async def flags():
        return {}

    monkeypatch.setattr(routes, "_registration_template_ctx", flags)
    monkeypatch.setattr(routes, "_oauth_template_ctx", flags)

    class CaptureTemplates:
        def TemplateResponse(self, name, context):
            from starlette.responses import HTMLResponse

            # Render the actual restored template without querying app services.
            from jinja2 import Environment, FileSystemLoader

            env = Environment(
                loader=FileSystemLoader("src/landppt/web/templates"), autoescape=True
            )
            return HTMLResponse(
                env.get_template(name).render(registration_enabled=True, **context)
            )

    monkeypatch.setattr(routes, "templates", CaptureTemplates())
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.get_db] = lambda: login_db
    app.dependency_overrides[routes.get_auth_service] = lambda: auth
    with TestClient(app, follow_redirects=False) as client:
        yield client


@pytest.mark.parametrize("path", ["/auth/login", "/api/auth/login"])
@pytest.mark.parametrize("identifier", ["demo-user", " DEMO+TAG@EXAMPLE.COM "])
def test_both_http_login_endpoints_accept_username_or_email(
    login_db, login_client, path, identifier
):
    user = add_user(login_db)
    response = login_client.post(
        path, data={"username": identifier, "password": "correct password"}
    )
    session = login_db.query(UserSession).one()
    assert session.user_id == user.id
    assert session.is_active
    if path == "/auth/login":
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"
        assert response.cookies.get("session_id") == session.session_id
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=lax" in response.headers["set-cookie"]
    else:
        assert response.status_code == 200
        assert response.json()["session_id"] == session.session_id
        assert response.json()["user"]["id"] == user.id
        assert "password_hash" not in response.json()["user"]


@pytest.mark.parametrize("path", ["/auth/login", "/api/auth/login"])
@pytest.mark.parametrize("reason", ["password", "missing", "disabled"])
def test_login_rejection_is_uniform_and_creates_no_session(
    login_db, login_client, path, reason
):
    user = add_user(login_db, active=reason != "disabled")
    identifier = (
        " missing@example.com " if reason == "missing" else " DEMO+TAG@EXAMPLE.COM "
    )
    response = login_client.post(
        path,
        data={
            "username": identifier,
            "password": "incorrect" if reason == "password" else "correct password",
        },
    )
    assert login_db.query(UserSession).count() == 0
    assert user.last_login is None
    if path == "/auth/login":
        assert response.status_code == 200
        assert "账号或密码错误" in response.text
        assert f'value="{identifier}"' in response.text
        assert 'placeholder="输入用户名或邮箱"' in response.text
        assert "incorrect" not in response.text
    else:
        assert response.status_code == 401
        assert response.json() == {"detail": "账号或密码错误"}
