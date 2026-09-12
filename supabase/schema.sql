-- Run once in the Supabase SQL editor. Re-running safely retains existing data.
begin;
create extension if not exists pgcrypto;
create table if not exists public.organizations (
 id uuid primary key default gen_random_uuid(), name text not null,
 created_at timestamptz not null default now()
);
create table if not exists public.users (
 id uuid primary key default gen_random_uuid(), organization_id uuid references public.organizations(id),
 name text not null, email text unique, role text not null check(role in ('recruiter','candidate','admin')),
 created_at timestamptz not null default now()
);
create table if not exists public.jobs (
 id uuid primary key default gen_random_uuid(), organization_id uuid not null references public.organizations(id),
 title text not null, description text not null default ''
);
create table if not exists public.competencies (
 id uuid primary key default gen_random_uuid(), organization_id uuid not null references public.organizations(id),
 name text not null, unique(organization_id,name)
);
create table if not exists public.assessments (
 id uuid primary key default gen_random_uuid(), job_id uuid references public.jobs(id),
 title text not null, job_title text not null, description text not null,
 max_questions integer not null check(max_questions between 4 and 100),
 confidence_target double precision not null check(confidence_target between .30 and .95),
 competencies jsonb not null check(jsonb_typeof(competencies)='array' and jsonb_array_length(competencies) between 1 and 12),
 priorities jsonb not null default '{}', created_at timestamptz not null default now()
);
create table if not exists public.questions (
 id uuid primary key default gen_random_uuid(), assessment_id uuid not null references public.assessments(id),
 competency_id uuid references public.competencies(id), question_text text not null,
 skill text not null, difficulty integer not null check(difficulty between 1 and 5),
 question_type text not null check(question_type in ('MCQ','Subjective','Coding')),
 options jsonb not null default '[]' check(jsonb_typeof(options)='array'), correct_answer text,
 rubric jsonb not null default '{}' check(jsonb_typeof(rubric)='object'),
 points double precision not null check(points > 0 and points <= 100),
 check(question_type <> 'MCQ' or (correct_answer is not null and jsonb_array_length(options) between 2 and 8))
);
create table if not exists public.attempts (
 id uuid primary key default gen_random_uuid(), assessment_id uuid not null references public.assessments(id),
 candidate_id uuid references public.users(id), candidate_name text not null,
 status text not null check(status in ('active','completed')),
 skill_state jsonb not null, answered_ids jsonb not null default '[]',
 current_question_id uuid references public.questions(id), version integer not null default 0 check(version >= 0),
 started_at timestamptz not null default now(), completed_at timestamptz,
 termination_reason text check(termination_reason in ('maximum_questions','confidence_reached','question_pool_exhausted')),
 check((status='active' and completed_at is null and current_question_id is not null)
    or (status='completed' and completed_at is not null and current_question_id is null))
);
create table if not exists public.responses (
 id uuid primary key default gen_random_uuid(), attempt_id uuid not null references public.attempts(id),
 question_id uuid not null references public.questions(id), answer text not null check(length(trim(answer)) > 0),
 evaluation jsonb not null, skill text not null, points double precision not null check(points > 0 and points <= 100),
 created_at timestamptz not null default now(), unique(attempt_id,question_id)
);
create table if not exists public.candidate_reports (
 id uuid primary key default gen_random_uuid(), attempt_id uuid not null unique references public.attempts(id),
 overall_score double precision not null check(overall_score between 0 and 100), skill_state jsonb not null,
 coverage double precision not null check(coverage between 0 and 100), strengths jsonb not null, gaps jsonb not null,
 evidence jsonb not null, interview_questions jsonb not null,
 termination_reason text not null, answered_count integer not null,
 created_at timestamptz not null default now()
);
create index if not exists users_org_idx on public.users(organization_id);
create index if not exists jobs_org_idx on public.jobs(organization_id);
create index if not exists assessments_job_idx on public.assessments(job_id);
create index if not exists questions_assessment_skill_idx on public.questions(assessment_id,skill,difficulty);
create index if not exists questions_competency_idx on public.questions(competency_id);
create index if not exists attempts_assessment_status_idx on public.attempts(assessment_id,status);
create index if not exists attempts_candidate_idx on public.attempts(candidate_id);
create index if not exists attempts_current_question_idx on public.attempts(current_question_id);
create index if not exists responses_question_idx on public.responses(question_id);

-- Safe upgrade for existing installations. Full schema reruns update RPCs below.
alter table public.attempts add column if not exists question_override jsonb;

-- Single-workspace MVP. Authentication/tenant routing must replace this fixed workspace before multi-tenancy.
create or replace function public.create_catalog_assessment(p_assessment jsonb)
returns jsonb language plpgsql security invoker set search_path = public as $$
declare
 org_id uuid := '00000000-0000-4000-8000-000000000001';
 job uuid;
 result public.assessments;
 skill_name text;
begin
 insert into public.organizations(id,name) values(org_id,'Local recruitment workspace') on conflict(id) do nothing;
 if exists(select 1 from public.assessments where id=(p_assessment->>'id')::uuid) then
   select * into result from public.assessments where id=(p_assessment->>'id')::uuid;
   return to_jsonb(result);
 end if;
 insert into public.jobs(organization_id,title,description)
 values(org_id,p_assessment->>'job_title',p_assessment->>'description') returning id into job;
 for skill_name in select jsonb_array_elements_text(p_assessment->'competencies') loop
   insert into public.competencies(organization_id,name) values(org_id,skill_name) on conflict do nothing;
 end loop;
 insert into public.assessments(id,job_id,title,job_title,description,max_questions,confidence_target,competencies,priorities)
 values((p_assessment->>'id')::uuid,job,p_assessment->>'title',p_assessment->>'job_title',p_assessment->>'description',
        (p_assessment->>'max_questions')::integer,(p_assessment->>'confidence_target')::double precision,
        p_assessment->'competencies',p_assessment->'priorities') returning * into result;
 return to_jsonb(result);
end $$;

create or replace function public.link_question_competency()
returns trigger language plpgsql security invoker set search_path = public as $$
begin
 select c.id into new.competency_id from public.competencies c
 join public.jobs j on j.organization_id=c.organization_id
 join public.assessments a on a.job_id=j.id
 where a.id=new.assessment_id and c.name=new.skill;
 if new.competency_id is null then raise exception 'unknown_competency'; end if;
 return new;
end $$;
drop trigger if exists question_competency_link on public.questions;
create trigger question_competency_link before insert or update on public.questions
for each row execute function public.link_question_competency();

-- A candidate identity and attempt are created in one transaction; no email required in this MVP.
create or replace function public.create_candidate_attempt(p_attempt jsonb)
returns jsonb language plpgsql security invoker set search_path = public as $$
declare
 candidate uuid;
 new_attempt public.attempts;
begin
 insert into public.users(name,role) values(p_attempt->>'candidate_name','candidate') returning id into candidate;
 new_attempt := jsonb_populate_record(null::public.attempts,
    p_attempt || jsonb_build_object('candidate_id',candidate));
 insert into public.attempts select new_attempt.*;
 return to_jsonb(new_attempt);
end $$;

-- Optimistic compare-and-swap plus row lock. Answer, skill state and final report commit together.
create or replace function public.commit_assessment_answer(
 p_version integer, p_attempt jsonb, p_response jsonb, p_report jsonb default null
) returns void language plpgsql security invoker set search_path = public as $$
declare
 current_attempt public.attempts;
 next_attempt public.attempts;
 response_row public.responses;
 report_row public.candidate_reports;
begin
 select * into current_attempt from public.attempts where id=(p_attempt->>'id')::uuid for update;
 if not found or current_attempt.version <> p_version or current_attempt.status <> 'active'
    or current_attempt.current_question_id <> (p_response->>'question_id')::uuid then
    raise exception 'attempt_conflict';
 end if;
 next_attempt := jsonb_populate_record(null::public.attempts,p_attempt);
 response_row := jsonb_populate_record(null::public.responses,p_response);
 if response_row.attempt_id <> current_attempt.id or next_attempt.version <> p_version+1
    or next_attempt.assessment_id <> current_attempt.assessment_id
    or exists(select 1 from public.responses where attempt_id=current_attempt.id and question_id=response_row.question_id)
    or not exists(select 1 from public.questions where id=response_row.question_id and assessment_id=current_attempt.assessment_id)
    or jsonb_array_length(next_attempt.answered_ids) <> jsonb_array_length(current_attempt.answered_ids)+1 then
    raise exception 'attempt_conflict';
 end if;
 if next_attempt.status='completed' and p_report is null then raise exception 'report_required'; end if;
 insert into public.responses select response_row.*;
 update public.attempts set status=next_attempt.status, skill_state=next_attempt.skill_state,
   answered_ids=next_attempt.answered_ids, current_question_id=next_attempt.current_question_id,
   version=next_attempt.version, question_override=next_attempt.question_override, completed_at=next_attempt.completed_at, termination_reason=next_attempt.termination_reason
 where id=current_attempt.id;
 if p_report is not null then
   report_row := jsonb_populate_record(null::public.candidate_reports,p_report);
   if report_row.attempt_id <> current_attempt.id or next_attempt.status <> 'completed' then
     raise exception 'invalid_report';
   end if;
   insert into public.candidate_reports select report_row.*;
 end if;
end $$;

-- Browser clients have no data access. Only server-held service-role credentials are supported.
alter table public.organizations enable row level security;
alter table public.users enable row level security;
alter table public.jobs enable row level security;
alter table public.competencies enable row level security;
alter table public.assessments enable row level security;
alter table public.questions enable row level security;
alter table public.attempts enable row level security;
alter table public.responses enable row level security;
alter table public.candidate_reports enable row level security;
revoke all on function public.create_catalog_assessment(jsonb) from public, anon, authenticated;
revoke all on function public.commit_assessment_answer(integer,jsonb,jsonb,jsonb) from public, anon, authenticated;
revoke all on function public.create_candidate_attempt(jsonb) from public, anon, authenticated;
grant execute on function public.create_candidate_attempt(jsonb) to service_role;
grant execute on function public.create_catalog_assessment(jsonb) to service_role;
grant execute on function public.commit_assessment_answer(integer,jsonb,jsonb,jsonb) to service_role;
grant all on public.organizations,public.users,public.jobs,public.competencies,public.assessments,
 public.questions,public.attempts,public.responses,public.candidate_reports to service_role;
commit;
