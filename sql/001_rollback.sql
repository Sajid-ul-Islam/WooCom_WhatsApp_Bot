-- =============================================================================
-- Migration 999: Full Rollback
--
-- Drops all objects created by migration 001.
-- Use ONLY if you need to completely reset the database schema.
-- =============================================================================

-- Drop the vector similarity function first (it depends on the products table)
drop function if exists public.match_products;

-- Drop all tables (order matters: dependent tables first, then independent)
drop table if exists public.pending_messages;
drop table if exists public.processed_messages;
drop table if exists public.rate_limits;
drop table if exists public.support_tickets;
drop table if exists public.whatsapp_users;
drop table if exists public.orders;
drop table if exists public.carts;
drop table if exists public.products;
drop table if exists public.config;

-- Note: Extensions (vector, uuid-ossp) are NOT dropped because other
-- projects in the same Supabase instance may depend on them.
