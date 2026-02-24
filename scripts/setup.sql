-- todo-schwesti: Supabase schema
-- Run this in the Supabase SQL Editor to set up all tables + triggers.

-- ── Projects ─────────────────────────────────────────────────────────────
create table if not exists projects (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  slug        text not null unique,
  color       text,
  position    int not null default 0,
  archived    boolean not null default false,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- ── Tasks ────────────────────────────────────────────────────────────────
create table if not exists tasks (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid not null references projects(id) on delete cascade,
  description     text not null,
  done            boolean not null default false,
  due             date,
  urgent          boolean not null default false,
  effort          text,
  position        int not null default 0,
  priority_score  int not null default 0,
  notes           text,
  recurring_rule  text,
  effort_minutes  int,
  actual_minutes  int,
  source          text default 'cli',
  done_date       date,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists idx_tasks_project on tasks(project_id);
create index if not exists idx_tasks_done on tasks(done);
create index if not exists idx_tasks_due on tasks(due) where due is not null;

-- ── Daily Plans ──────────────────────────────────────────────────────────
create table if not exists daily_plans (
  id          uuid primary key default gen_random_uuid(),
  plan_date   date not null unique,
  content     text not null,
  created_at  timestamptz not null default now()
);

-- ── Task Activity (audit log) ────────────────────────────────────────────
create table if not exists task_activity (
  id          uuid primary key default gen_random_uuid(),
  task_id     uuid not null references tasks(id) on delete cascade,
  action      text not null,  -- 'created', 'completed', 'updated', 'moved'
  details     jsonb,
  created_at  timestamptz not null default now()
);

create index if not exists idx_activity_task on task_activity(task_id);
create index if not exists idx_activity_created on task_activity(created_at);

-- ── Triggers ─────────────────────────────────────────────────────────────

-- Auto-update updated_at on projects
create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create or replace trigger projects_updated_at
  before update on projects
  for each row execute function update_updated_at();

create or replace trigger tasks_updated_at
  before update on tasks
  for each row execute function update_updated_at();

-- Auto-compute priority_score on tasks
-- overdue=3, urgent=2, due within 3 days=1, else=0
create or replace function compute_priority_score()
returns trigger as $$
begin
  new.priority_score = 0;
  if new.done then
    new.priority_score = 0;
  elsif new.due is not null and new.due < current_date then
    new.priority_score = 3;  -- overdue
  elsif new.urgent then
    new.priority_score = 2;  -- urgent
  elsif new.due is not null and new.due <= current_date + interval '3 days' then
    new.priority_score = 1;  -- due soon
  end if;
  return new;
end;
$$ language plpgsql;

create or replace trigger tasks_priority_score
  before insert or update on tasks
  for each row execute function compute_priority_score();

-- Auto-log task activity
create or replace function log_task_activity()
returns trigger as $$
begin
  if tg_op = 'INSERT' then
    insert into task_activity (task_id, action, details)
    values (new.id, 'created', jsonb_build_object('description', new.description));
  elsif tg_op = 'UPDATE' then
    if old.done = false and new.done = true then
      insert into task_activity (task_id, action, details)
      values (new.id, 'completed', jsonb_build_object('description', new.description));
    elsif old.project_id != new.project_id then
      insert into task_activity (task_id, action, details)
      values (new.id, 'moved', jsonb_build_object(
        'from_project', old.project_id::text,
        'to_project', new.project_id::text
      ));
    else
      insert into task_activity (task_id, action, details)
      values (new.id, 'updated', jsonb_build_object('description', new.description));
    end if;
  end if;
  return new;
end;
$$ language plpgsql;

create or replace trigger tasks_activity_log
  after insert or update on tasks
  for each row execute function log_task_activity();

-- ── Realtime ─────────────────────────────────────────────────────────────
-- Enable realtime for tasks and projects tables.
-- In Supabase dashboard: Database > Replication > enable tables.
-- Or via SQL:
alter publication supabase_realtime add table tasks;
alter publication supabase_realtime add table projects;
