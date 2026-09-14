export interface Meetup {
  id: number;
  title: string;
  starts_at: string;
  venue: string;
  venue_lat: number | null;
  venue_lon: number | null;
  capacity: number;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `request failed: ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export function signup(email: string, password: string): Promise<{ id: number }> {
  return request("/signup", { method: "POST", body: JSON.stringify({ email, password }) });
}

export function login(email: string, password: string): Promise<{ token: string }> {
  return request("/login", { method: "POST", body: JSON.stringify({ email, password }) });
}

export function listMeetups(): Promise<Meetup[]> {
  return request("/meetups");
}

export function createMeetup(
  token: string,
  meetup: { title: string; starts_at: string; venue: string; capacity: number },
): Promise<Meetup> {
  return request("/meetups", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(meetup),
  });
}

export function register(token: string, meetupId: number): Promise<void> {
  return request(`/meetups/${meetupId}/registrations`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}
