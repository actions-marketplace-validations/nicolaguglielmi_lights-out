CREATE TABLE schema_migrations (
    name       text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id            bigserial PRIMARY KEY,
    email         text NOT NULL UNIQUE,
    password_hash text NOT NULL
);

CREATE TABLE sessions (
    token_hash text PRIMARY KEY,
    user_id    bigint NOT NULL REFERENCES users (id),
    expires_at timestamptz NOT NULL
);

CREATE TABLE meetups (
    id         bigserial PRIMARY KEY,
    title      text NOT NULL,
    starts_at  text NOT NULL,
    venue      text NOT NULL,
    venue_lat  double precision,
    venue_lon  double precision,
    capacity   int NOT NULL
);

CREATE TABLE registrations (
    meetup_id  bigint NOT NULL REFERENCES meetups (id),
    user_id    bigint NOT NULL REFERENCES users (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (meetup_id, user_id)
);
