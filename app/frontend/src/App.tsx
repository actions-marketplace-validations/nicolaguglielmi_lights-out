import { useEffect, useState } from "react";
import * as api from "./api";
import type { Meetup } from "./api";

type View = "auth" | "list" | "create";

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [view, setView] = useState<View>("auth");
  const [error, setError] = useState<string | null>(null);

  if (!token) {
    return <AuthView onAuthenticated={setToken} error={error} setError={setError} />;
  }
  if (view === "create") {
    return (
      <CreateMeetupView
        token={token}
        onDone={() => setView("list")}
        onLogout={() => setToken(null)}
      />
    );
  }
  return (
    <MeetupListView
      token={token}
      onCreate={() => setView("create")}
      onLogout={() => setToken(null)}
    />
  );
}

function AuthView({
  onAuthenticated,
  error,
  setError,
}: {
  onAuthenticated: (token: string) => void;
  error: string | null;
  setError: (message: string | null) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  async function handleLogin() {
    setError(null);
    try {
      const { token } = await api.login(email, password);
      onAuthenticated(token);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleSignup() {
    setError(null);
    try {
      await api.signup(email, password);
      await handleLogin();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <main>
      <h1>meetups</h1>
      <input
        placeholder="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <input
        placeholder="password"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <button onClick={handleLogin}>log in</button>
      <button onClick={handleSignup}>sign up</button>
      {error && <p role="alert">{error}</p>}
    </main>
  );
}

function MeetupListView({
  token,
  onCreate,
  onLogout,
}: {
  token: string;
  onCreate: () => void;
  onLogout: () => void;
}) {
  const [meetups, setMeetups] = useState<Meetup[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listMeetups().then(setMeetups).catch((err) => setError(err.message));
  }, []);

  async function handleRegister(meetupId: number) {
    setError(null);
    try {
      await api.register(token, meetupId);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <main>
      <h1>meetups</h1>
      <button onClick={onCreate}>new meetup</button>
      <button onClick={onLogout}>log out</button>
      {error && <p role="alert">{error}</p>}
      <ul>
        {meetups.map((meetup) => (
          <li key={meetup.id}>
            {meetup.title} — {meetup.venue} — {meetup.capacity} spots
            <button onClick={() => handleRegister(meetup.id)}>register</button>
          </li>
        ))}
      </ul>
    </main>
  );
}

function CreateMeetupView({
  token,
  onDone,
  onLogout,
}: {
  token: string;
  onDone: () => void;
  onLogout: () => void;
}) {
  const [title, setTitle] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [venue, setVenue] = useState("");
  const [capacity, setCapacity] = useState(10);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    setError(null);
    try {
      await api.createMeetup(token, { title, starts_at: startsAt, venue, capacity });
      onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <main>
      <h1>new meetup</h1>
      <button onClick={onLogout}>log out</button>
      <input placeholder="title" value={title} onChange={(e) => setTitle(e.target.value)} />
      <input
        placeholder="starts at (ISO)"
        value={startsAt}
        onChange={(e) => setStartsAt(e.target.value)}
      />
      <input placeholder="venue" value={venue} onChange={(e) => setVenue(e.target.value)} />
      <input
        placeholder="capacity"
        type="number"
        value={capacity}
        onChange={(e) => setCapacity(Number(e.target.value))}
      />
      <button onClick={handleSubmit}>create</button>
      <button onClick={onDone}>cancel</button>
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
