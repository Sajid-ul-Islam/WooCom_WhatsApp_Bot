# Database Migrations

This directory contains numbered SQL migration files for setting up the Supabase (PostgreSQL) database required by the WooCommerce WhatsApp Bot.

## How to apply

### Option 1: Supabase SQL Editor (recommended for initial setup)

1. Open your Supabase project dashboard → **SQL Editor**.
2. Open each `.sql` file in **numerical order** (001, 002, ...).
3. Paste the contents and click **Run**.

### Option 2: psql CLI

```bash
# Run each migration in order
psql $SUPABASE_DATABASE_URL -f sql/001_initial_schema.sql
psql $SUPABASE_DATABASE_URL -f sql/002_*.sql   # if applicable
```

### Option 3: Supabase migration tool (for production)

```bash
# If using Supabase CLI
supabase migration new initial_schema
# Then copy the SQL content into the generated file
supabase db push
```

## Migration files

| File | Description |
|------|-------------|
| `001_initial_schema.sql` | All base tables (products, carts, orders, users, support_tickets, rate_limits, processed_messages, pending_messages, config), indexes, and the `match_products` vector similarity function. |

## Notes

- Migrations are **idempotent** — you can run them multiple times safely (uses `create if not exists` / `create or replace`).
- The `products.embedding` column uses `vector(384)` — this matches the `BAAI/bge-small-en-v1.5` embedding model.
- The IVFFlat index on `products.embedding` uses 100 lists, which is appropriate for ~5K–50K products. Adjust `lists` based on your catalog size (rule of thumb: `sqrt(n_rows)`).
