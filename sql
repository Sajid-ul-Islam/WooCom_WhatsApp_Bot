-- Enable vector extension
create extension if not exists vector;

-- Enable uuid-ossp extension
create extension if not exists "uuid-ossp";

-- Products table for search and RAG
create table if not exists public.products (
    id bigint primary key, -- WooCommerce Product ID
    name text not null,
    description text,
    price numeric,
    permalink text,
    images jsonb, -- list of image URLs/meta
    categories jsonb, -- list of categories
    embedding vector(384), -- size of bge-small-en-v1.5 embeddings
    updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Index for similarity search
create index on public.products using ivfflat (embedding vector_cosine_ops)
with (lists = 100);

-- User Carts table (persistent shopping sessions)
create table if not exists public.carts (
    phone_number text primary key,
    items jsonb not null default '[]'::jsonb,
    updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Orders cache table (to retrieve history quickly without hammering WooCommerce API)
create table if not exists public.orders (
    id bigint primary key, -- WooCommerce Order ID
    phone_number text not null,
    status text,
    total numeric,
    items jsonb,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- WhatsApp Users table (for conversational memory and human handoff)
create table if not exists public.whatsapp_users (
    phone_number text primary key,
    first_name text,
    chat_history jsonb default '[]'::jsonb,
    command_counts jsonb default '{}'::jsonb,
    bot_paused boolean default false,
    state text default 'idle',
    last_active timestamp with time zone default timezone('utc'::text, now())
);

-- Support Tickets table (for returns, exchanges, complaints, and human escalations)
create table if not exists public.support_tickets (
    id uuid primary key default uuid_generate_v4(),
    phone_number text not null,
    issue_type text not null, -- 'return', 'exchange', 'complaint', 'escalation'
    order_id bigint,
    description text,
    status text default 'open',
    priority text default 'normal',
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Rate limiting table (shared across workers/restarts)
create table if not exists public.rate_limits (
    phone_number text not null,
    window_start timestamp with time zone not null,
    request_count integer default 1,
    primary key (phone_number, window_start)
);

-- Message deduplication table (persistent across restarts)
create table if not exists public.processed_messages (
    msg_id text primary key,
    processed_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Durable pending messages queue (prevents message loss on crash during bg processing)
create table if not exists public.pending_messages (
    id uuid primary key default uuid_generate_v4(),
    msg_id text,
    phone_number text not null,
    payload jsonb,
    status text default 'pending', -- 'pending', 'processing', 'completed', 'failed'
    error text,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null,
    processed_at timestamp with time zone
);

-- Index for pending message cleanup
create index on public.pending_messages (status, created_at);

-- Index for rate limit cleanup
create index on public.rate_limits (window_start);

-- Index for processed message cleanup
create index on public.processed_messages (processed_at);

-- Config table for remote secret management
create table if not exists public.config (
    key text primary key,
    value text not null,
    updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Vector similarity search helper function
create or replace function match_products (
  query_embedding vector(384),
  match_threshold float,
  match_count int
)
returns table (
  id bigint,
  name text,
  description text,
  price numeric,
  permalink text,
  images jsonb,
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
