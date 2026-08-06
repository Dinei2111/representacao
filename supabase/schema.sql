-- Estrutura do sistema de pedidos da Opert Representações.
-- Cole este arquivo inteiro no SQL Editor do Supabase e execute uma vez.
-- Pode ser executado de novo sem estragar nada (tudo é "if not exists"/"replace").

-- ---------------------------------------------------------------- perfis ----
create table if not exists public.perfis (
  id           uuid primary key references auth.users on delete cascade,
  razao_social text not null,
  cnpj         text not null unique,
  telefone     text not null,
  cidade       text,
  uf           text,
  aprovado     boolean not null default false,
  admin        boolean not null default false,
  criado_em    timestamptz not null default now()
);

-- ---------------------------------------------------------------- precos ----
create table if not exists public.precos (
  codigo     text primary key,
  de         text,                       -- preço antigo da promoção (riscado)
  valor      text not null,              -- preço à vista atual
  faixas     jsonb not null default '[]'::jsonb,  -- [{a_partir, unidade, valor}]
  fornecedor text not null default 'Knup',
  atualizado_em timestamptz not null default now()
);

-- --------------------------------------------------------------- pedidos ----
do $$ begin
  create type public.status_pedido as enum
    ('pendente', 'pago', 'faturado', 'enviado', 'entregue', 'cancelado');
exception when duplicate_object then null;
end $$;

create sequence if not exists public.pedido_numero_seq;

create table if not exists public.pedidos (
  id         uuid primary key default gen_random_uuid(),
  numero     text not null unique
             default to_char(now(), 'YYYY') || '-' ||
                     lpad(nextval('public.pedido_numero_seq')::text, 4, '0'),
  cliente_id uuid not null references public.perfis(id) on delete cascade
             default auth.uid(),
  status     public.status_pedido not null default 'pendente',
  total      numeric(12,2) not null default 0,
  observacao text,
  criado_em  timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create table if not exists public.pedido_itens (
  id            bigint generated always as identity primary key,
  pedido_id     uuid not null references public.pedidos(id) on delete cascade,
  codigo        text not null,
  nome          text not null,
  caixas        integer not null default 1,
  pecas         integer not null default 1,
  preco_unit    numeric(12,2) not null,
  subtotal      numeric(12,2) not null
);

create table if not exists public.pedido_eventos (
  id        bigint generated always as identity primary key,
  pedido_id uuid not null references public.pedidos(id) on delete cascade,
  status    public.status_pedido not null,
  criado_em timestamptz not null default now()
);

create index if not exists idx_pedidos_cliente on public.pedidos(cliente_id);
create index if not exists idx_itens_pedido    on public.pedido_itens(pedido_id);
create index if not exists idx_eventos_pedido  on public.pedido_eventos(pedido_id);

-- ------------------------------------------------------------- funções ------
-- security definer para a política poder consultar 'perfis' sem cair na
-- própria política e entrar em recursão
create or replace function public.eh_admin()
returns boolean language sql stable security definer set search_path = public as $$
  select coalesce((select admin from public.perfis where id = auth.uid()), false);
$$;

create or replace function public.eh_aprovado()
returns boolean language sql stable security definer set search_path = public as $$
  select coalesce((select aprovado from public.perfis where id = auth.uid()), false);
$$;

-- ninguém se aprova nem se promove a admin sozinho
create or replace function public.trava_aprovacao()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if (new.aprovado is distinct from old.aprovado
      or new.admin is distinct from old.admin) and not public.eh_admin() then
    raise exception 'somente um administrador altera aprovação ou perfil de acesso';
  end if;
  return new;
end $$;

drop trigger if exists trg_trava_aprovacao on public.perfis;
create trigger trg_trava_aprovacao before update on public.perfis
  for each row execute function public.trava_aprovacao();

-- toda mudança de status vira histórico, sem depender do aplicativo
create or replace function public.registra_evento()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if tg_op = 'INSERT' or new.status is distinct from old.status then
    insert into public.pedido_eventos (pedido_id, status) values (new.id, new.status);
  end if;
  new.atualizado_em := now();
  return new;
end $$;

drop trigger if exists trg_evento_insert on public.pedidos;
create trigger trg_evento_insert after insert on public.pedidos
  for each row execute function public.registra_evento();

drop trigger if exists trg_evento_update on public.pedidos;
create trigger trg_evento_update before update on public.pedidos
  for each row execute function public.registra_evento();

-- --------------------------------------------------------------- RLS --------
alter table public.perfis         enable row level security;
alter table public.precos         enable row level security;
alter table public.pedidos        enable row level security;
alter table public.pedido_itens   enable row level security;
alter table public.pedido_eventos enable row level security;

-- perfis: cada um enxerga e edita o próprio; admin enxerga e edita todos
drop policy if exists perfis_ler on public.perfis;
create policy perfis_ler on public.perfis for select
  using (id = auth.uid() or public.eh_admin());

drop policy if exists perfis_criar on public.perfis;
create policy perfis_criar on public.perfis for insert
  with check (id = auth.uid());

drop policy if exists perfis_editar on public.perfis;
create policy perfis_editar on public.perfis for update
  using (id = auth.uid() or public.eh_admin());

-- preços: só quem foi aprovado
drop policy if exists precos_ler on public.precos;
create policy precos_ler on public.precos for select
  using (public.eh_aprovado() or public.eh_admin());

drop policy if exists precos_gravar on public.precos;
create policy precos_gravar on public.precos for all
  using (public.eh_admin()) with check (public.eh_admin());

-- pedidos: o cliente cria e acompanha os seus; só admin muda status
drop policy if exists pedidos_ler on public.pedidos;
create policy pedidos_ler on public.pedidos for select
  using (cliente_id = auth.uid() or public.eh_admin());

drop policy if exists pedidos_criar on public.pedidos;
create policy pedidos_criar on public.pedidos for insert
  with check (cliente_id = auth.uid() and public.eh_aprovado());

drop policy if exists pedidos_editar on public.pedidos;
create policy pedidos_editar on public.pedidos for update
  using (public.eh_admin()) with check (public.eh_admin());

drop policy if exists itens_ler on public.pedido_itens;
create policy itens_ler on public.pedido_itens for select
  using (exists (select 1 from public.pedidos p
                 where p.id = pedido_id and (p.cliente_id = auth.uid() or public.eh_admin())));

drop policy if exists itens_criar on public.pedido_itens;
create policy itens_criar on public.pedido_itens for insert
  with check (exists (select 1 from public.pedidos p
                      where p.id = pedido_id and p.cliente_id = auth.uid()));

drop policy if exists eventos_ler on public.pedido_eventos;
create policy eventos_ler on public.pedido_eventos for select
  using (exists (select 1 from public.pedidos p
                 where p.id = pedido_id and (p.cliente_id = auth.uid() or public.eh_admin())));

-- --------------------------------------------------------- primeiro admin ---
-- Depois de criar sua conta pelo site, rode a linha abaixo trocando o e-mail:
--
-- update public.perfis set admin = true, aprovado = true
--  where id = (select id from auth.users where email = 'voce@exemplo.com');
