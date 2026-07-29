-- =============================================================================
-- Migration 001: Initial Schema
-- 
-- Creates all base tables, indexes, and the vector similarity search function
-- required by the WooCommerce WhatsApp Bot.
--
-- Run this once when setting up a new Supabase project.
-- =============================================================================

-- 0. Extensions
-- =============================================================================
create extension if not exists vector;
create extension if not exists "uuid-ossp";


-- 1. Products table (vector search + RAG)
-- =============================================================================
create table if not exists public.products (
    id          bigint primary key,    -- WooCommerce Product ID
    name        text not null,
    description text,
    price       numeric,
    permalink   text,
    images      jsonb,                 -- list of image URLs/meta
    categories  jsonb,                 -- list of categories
    embedding   vector(384),           -- size of bge-small-en-v1.5 embeddings
    updated_at  timestamptz default timezone('utc'::text, now()) not null
);

-- IVFFlat index for approximate nearest-neighbor search on embeddings
create index if not exists idx_products_embedding
    on public.products
    using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);


-- 2. User carts (persistent shopping sessions)
-- =============================================================================
create table if not exists public.carts (
    phone_number  text primary key,
    items         jsonb not null default '[]'::jsonb,
    updated_at    timestamptz default timezone('utc'::text, now()) not null
);


-- 3. Orders cache (fast history without WooCommerce API calls)
-- =============================================================================
create table if not exists public.orders (
    id           bigint primary key,   -- WooCommerce Order ID
    phone_number text not null,
    status       text,
    total        numeric,
    items        jsonb,
    created_at   timestamptz default timezone('utc'::text, now()) not null
);

-- Index for common lookup pattern: orders by phone, sorted by date
create index if not exists idx_orders_phone_created
    on public.orders (phone_number, created_at desc);


-- 4. WhatsApp users (conversational memory, human handoff, language)
-- =============================================================================
create table if not exists public.whatsapp_users (
    phone_number   text primary key,
    first_name     text,
    chat_history   jsonb default '[]'::jsonb,
    command_counts jsonb default '{}'::jsonb,
    language       text default 'en',
    bot_paused     boolean default false,
    state          text default 'idle',
    last_active    timestamptz default timezone('utc'::text, now())
);


-- 5. Support tickets (returns, exchanges, escalations)
-- =============================================================================
create table if not exists public.support_tickets (
    id           uuid primary key default uuid_generate_v4(),
    phone_number text not null,
    issue_type   text not null,       -- 'return', 'exchange', 'complaint', 'escalation'
    order_id     bigint,
    description  text,
    status       text default 'open', -- 'open', 'in_progress', 'resolved', 'closed'
    priority     text default 'normal',
    created_at   timestamptz default timezone('utc'::text, now()) not null
);

create index if not exists idx_support_tickets_phone
    on public.support_tickets (phone_number, created_at desc);

create index if not exists idx_support_tickets_status
    on public.support_tickets (status);


-- 6. Rate limiting (shared across workers / restarts)
-- =============================================================================
create table if not exists public.rate_limits (
    phone_number  text not null,
    window_start  timestamptz not null,
    request_count integer default 1,
    primary key (phone_number, window_start)
);

create index if not exists idx_rate_limits_window
    on public.rate_limits (window_start);


-- 7. Message deduplication (persistent across restarts)
-- =============================================================================
create table if not exists public.processed_messages (
    msg_id       text primary key,
    processed_at timestamptz default timezone('utc'::text, now()) not null
);

create index if not exists idx_processed_messages_time
    on public.processed_messages (processed_at);


-- 8. Durable pending messages queue (crash recovery)
-- =============================================================================
create table if not exists public.pending_messages (
    id           uuid primary key default uuid_generate_v4(),
    msg_id       text,
    phone_number text not null,
    payload      jsonb,
    status       text default 'pending',  -- 'pending', 'processing', 'completed', 'failed'
    error        text,
    created_at   timestamptz default timezone('utc'::text, now()) not null,
    processed_at timestamptz
);

create index if not exists idx_pending_messages_status
    on public.pending_messages (status, created_at);


-- 9. Config table (remote secret management)
-- =============================================================================
create table if not exists public.config (
    key        text primary key,
    value      text not null,
    updated_at timestamptz default timezone('utc'::text, now()) not null
);


-- 10. Vector similarity search function
-- =============================================================================
-- Used by RAGAgent to find products by semantic similarity.
-- Returns products whose cosine distance from the query embedding is
-- below the threshold, ordered by closest match first.
create or replace function match_products (
    query_embedding vector(384),
    match_threshold float,
    match_count     int
)
returns table (
    id         bigint,
    name       text,
    description text,
    price      numeric,
    permalink  text,
    images     jsonb,
    categories jsonb,
    similarity float
)
language sql stable
as $$
    select
        id,
        name,
        description,
        price,
        permalink,
        images,
        categories,
        1 - (products.embedding <=> query_embedding) as similarity
    from products
    where 1 - (products.embedding <=> query_embedding) > match_threshold
    order by products.embedding <=> query_embedding
    limit match_count;
$$;
