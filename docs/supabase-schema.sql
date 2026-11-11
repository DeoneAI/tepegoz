-- Tepegoz session index mirror for Supabase (free tier).
-- Paste into Supabase → SQL Editor → New query → Run. Safe to run more than once.
-- Only session metadata is mirrored; frames and raw IMU stay on the collector PC.

create table if not exists public.sessions (
  id text primary key,
  name text not null,
  created_at timestamptz not null,
  ended_at timestamptz,
  status text not null,
  connection_mode text,
  frames integer,
  samples integer,
  duration_s double precision,
  device_user_agent text,
  manifest jsonb not null,
  updated_at timestamptz not null default now()
);

create index if not exists sessions_created_at_idx on public.sessions (created_at desc);

-- Row Level Security on, with no public policies: only the service_role key (used by the collector
-- on the PC) can read or write. Add a SELECT policy later if teammates should read via the anon key.
alter table public.sessions enable row level security;
