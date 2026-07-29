# WooCommerce WhatsApp Chatbot with RAG AI

This repository contains a production-ready WooCommerce WhatsApp chatbot that integrates Meta's official WhatsApp Business Cloud API with a local semantic search agent (RAG) powered by FastEmbed and Supabase (pgvector). 

## Features

- 🏠 **Main Menu Navigation**: Reply buttons for browsing categories, view cart, and order status.
- 📦 **Interactive Product Browser**: List menus showing categories and product details (with images, prices, and direct links).
- 🛒 **Full Cart System**: Add items, increase quantities, remove items, clear cart, and calculate totals.
- 💳 **WhatsApp Checkout**: Place cash-on-delivery (COD) orders directly via chat messaging.
- 🔍 **AI RAG Product Recommendation**: Seamless semantic searching using local embeddings (`BAAI/bge-small-en-v1.5`) and LLMs (OpenAI or Anthropic).
- ⚡ **Order History Cache**: Fast order tracking using phone numbers linked directly to WooCommerce backend.

---

## 🛠️ Step-by-Step Setup Guide

### 1. Supabase Vector Database Setup
1. Create a free project on [Supabase](https://supabase.com).
2. Go to the **SQL Editor** in your Supabase dashboard and execute the following SQL to enable extensions, create tables, build indexes, and register the RPC similarity function:

```sql
-- Enable vector extension
create extension if not exists vector;
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
create index on public.products using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- User Carts table
create table if not exists public.carts (
    phone_number text primary key,
    items jsonb not null default '[]'::jsonb,
    updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Orders cache table
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
```

### 2. WooCommerce REST API Credentials
1. Go to your WooCommerce dashboard → **Settings** → **Advanced** → **REST API**.
2. Click **Add Key**. Enter a description, select a user, and set Permissions to **Read/Write**.
3. Copy the **Consumer Key** (`ck_...`) and **Consumer Secret** (`cs_...`).

### 3. Meta Developer Portal Configuration
1. Register as a Meta Developer at [developers.facebook.com](https://developers.facebook.com).
2. Create an App (type: **Business** or **Other** with the **WhatsApp** product added).
3. Go to **WhatsApp** → **Quickstart** / **API Setup** to get:
   - **Phone Number ID**
   - **WhatsApp Business Account ID**
   - A **Temporary Access Token** (or generate a permanent token using System User permissions).
4. Set up a Webhook in the Meta developer dashboard:
   - Under **WhatsApp** → **Configuration**, click **Edit Webhook**.
   - Callback URL: `https://your-domain.com/webhook`
   - Verify Token: A secret string you choose (set it as `WHATSAPP_WEBHOOK_VERIFY_TOKEN` in `.env`).
   - Subscribe to the **`messages`** webhook field.

### 4. Configuration Variables (`.env`)
Create a `.env` file from the template:
```bash
cp .env.example .env
```
Fill in the configuration details:
```env
# WhatsApp credentials
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_ACCESS_TOKEN=EAAB...
WHATSAPP_WEBHOOK_VERIFY_TOKEN=my_random_secret_string

# WooCommerce credentials
WOOCOMMERCE_URL=https://my-store.com
WOOCOMMERCE_KEY=ck_...
WOOCOMMERCE_SECRET=cs_...

# Supabase credentials
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=ey...

# AI Model Configuration
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

---

## 🚀 Running locally

### Install Dependencies
Ensure you have Python 3.10+ installed:
```bash
pip install -r requirements.txt
```

### Sync WooCommerce Products to Supabase Vector Database
Before running the bot, synchronize your WooCommerce catalog to generate embeddings:
```bash
python product_embeddings.py
```

### Start Webhook Server
Run the FastAPI development server:
```bash
uvicorn main:app --reload --port 8000
```
Use `ngrok` or similar to expose your port 8000 so Meta can send webhook POST requests:
```bash
ngrok http 8000
```
Update your Meta Webhook URL to the ngrok URL (e.g. `https://xxxx.ngrok-free.app/webhook`).

---

## 🐋 Docker Deployment

Build and run using Docker:
```bash
docker build -t woocommerce-whatsapp-bot .
docker run -d -p 8000:8000 --env-file .env woocommerce-whatsapp-bot
```

---

## 💬 Chat Commands & Interface Actions

- **Hi / Menu / Hello**: Trigger the main menu reply buttons.
- **Browse Categories**: Triggers a list menu displaying the top 10 store categories.
- **Product Listing**: Category clicks list products, selecting a product opens a visual details card showing the description, price, product image, and **Add to Cart** buttons.
- **View Cart**: Displays all items, sub-totals, and the overall cart total.
- **Checkout**: Displays checkout format instruction.
- **Checkout: [Name], [Address]**: Places order directly onto WooCommerce and clears cart.
- **My Orders**: Returns a summary of the 5 most recent orders and their current processing status.
- **Natural Language Query**: If the message doesn't match a command, it is passed to the RAG Agent. The AI will answer queries (e.g. *"Do you sell blue dresses under $50?"*) and append an interactive selection list of matching items.
