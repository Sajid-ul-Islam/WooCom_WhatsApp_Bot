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