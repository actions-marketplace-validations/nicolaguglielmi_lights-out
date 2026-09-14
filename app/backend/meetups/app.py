"""The meetups app: routes, table 3 of docs/adr/0005."""

import os

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from psycopg import errors as pg_errors
from pydantic import BaseModel

from meetups.auth import current_user_id, hash_password, issue_session, verify_password
from meetups.db import get_db
from meetups.flags import waitlist_enabled
from meetups.geocoder_client import GeocoderUnavailable, geocode
from meetups.metrics import CONTENT_TYPE, metrics_text, setup_metrics

APP_VERSION = os.environ.get("APP_VERSION", "dev")
FRONTEND_DIST = "/srv/frontend"

app = FastAPI(title="meetups")
setup_metrics(app)


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class MeetupCreateRequest(BaseModel):
    title: str
    starts_at: str
    venue: str
    capacity: int


def _meetup_row(row: tuple) -> dict:
    id_, title, starts_at, venue, venue_lat, venue_lon, capacity = row
    return {
        "id": id_,
        "title": title,
        "starts_at": starts_at,
        "venue": venue,
        "venue_lat": venue_lat,
        "venue_lon": venue_lon,
        "capacity": capacity,
    }


@app.post("/api/signup", status_code=201)
def signup(body: SignupRequest, db: psycopg.Connection = Depends(get_db)):
    with db.cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
                (body.email, hash_password(body.password)),
            )
        except pg_errors.UniqueViolation:
            db.rollback()
            raise HTTPException(status_code=409, detail="email already registered")
        (user_id,) = cur.fetchone()
    db.commit()
    return {"id": user_id}


@app.post("/api/login")
def login(body: LoginRequest, db: psycopg.Connection = Depends(get_db)):
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, password_hash FROM users WHERE email = %s", (body.email,)
        )
        row = cur.fetchone()
        if row is None or not verify_password(body.password, row[1]):
            raise HTTPException(status_code=401, detail="invalid credentials")
        token = issue_session(cur, row[0])
    db.commit()
    return {"token": token}


@app.get("/api/meetups")
def list_meetups(db: psycopg.Connection = Depends(get_db)):
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, title, starts_at, venue, venue_lat, venue_lon, capacity "
            "FROM meetups ORDER BY id"
        )
        rows = cur.fetchall()
    return [_meetup_row(row) for row in rows]


@app.get("/api/meetups/{meetup_id}")
def get_meetup(meetup_id: int, db: psycopg.Connection = Depends(get_db)):
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, title, starts_at, venue, venue_lat, venue_lon, capacity "
            "FROM meetups WHERE id = %s",
            (meetup_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="meetup not found")
    return _meetup_row(row)


@app.post("/api/meetups", status_code=201)
def create_meetup(
    body: MeetupCreateRequest,
    db: psycopg.Connection = Depends(get_db),
    _user_id: int = Depends(current_user_id),
):
    try:
        venue_lat, venue_lon = geocode(body.venue)
    except GeocoderUnavailable:
        raise HTTPException(status_code=502, detail="geocoder unavailable")
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO meetups (title, starts_at, venue, venue_lat, venue_lon, capacity) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (body.title, body.starts_at, body.venue, venue_lat, venue_lon, body.capacity),
        )
        (meetup_id,) = cur.fetchone()
    db.commit()
    return {
        "id": meetup_id,
        "title": body.title,
        "starts_at": body.starts_at,
        "venue": body.venue,
        "venue_lat": venue_lat,
        "venue_lon": venue_lon,
        "capacity": body.capacity,
    }


@app.post("/api/meetups/{meetup_id}/registrations", status_code=201)
def register(
    meetup_id: int,
    db: psycopg.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
):
    with db.cursor() as cur:
        cur.execute("SELECT capacity FROM meetups WHERE id = %s", (meetup_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="meetup not found")
        (capacity,) = row

        cur.execute(
            "SELECT count(*) FROM registrations WHERE meetup_id = %s", (meetup_id,)
        )
        (registered,) = cur.fetchone()

        if registered >= capacity:
            if waitlist_enabled():
                raise HTTPException(
                    status_code=501,
                    detail="waitlist is not implemented; see the golden path ticket",
                )
            raise HTTPException(status_code=409, detail="meetup is full")

        try:
            cur.execute(
                "INSERT INTO registrations (meetup_id, user_id) VALUES (%s, %s)",
                (meetup_id, user_id),
            )
        except pg_errors.UniqueViolation:
            db.rollback()
            raise HTTPException(status_code=409, detail="already registered")
    db.commit()
    return {"meetup_id": meetup_id, "user_id": user_id}


@app.get("/healthz")
def healthz():
    try:
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except psycopg.Error:
        return Response(
            status_code=503, content='{"status":"error"}', media_type="application/json"
        )
    return {"status": "ok", "version": APP_VERSION}


@app.get("/metrics")
def metrics_endpoint():
    return Response(content=metrics_text(), media_type=CONTENT_TYPE)


if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
