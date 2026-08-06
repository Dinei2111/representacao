-- Testes das regras de segurança do banco, para rodar num Postgres local.
-- Reproduz o ambiente do Supabase (schema auth, auth.uid(), role authenticated)
-- e verifica na prática o que cada tipo de usuário consegue fazer.
--
--   psql -f supabase/testes.sql
--
-- Qualquer linha "FALHOU" no resultado significa regra frouxa ou quebrada.

\set ON_ERROR_STOP on
\set QUIET on

drop schema if exists public cascade;
create schema public;
drop schema if exists auth cascade;
create schema auth;

create table auth.users (id uuid primary key, email text unique);

-- no Supabase auth.uid() lê o usuário do token; aqui lê de uma variável de sessão
create or replace function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('teste.usuario', true), '')::uuid;
$$;

do $$ begin create role authenticated; exception when duplicate_object then null; end $$;
grant usage on schema public, auth to authenticated;

\i supabase/schema.sql

grant select, insert, update on all tables in schema public to authenticated;
grant usage, select on all sequences in schema public to authenticated;

-- três usuários: o representante (admin), o cliente aprovado e um cliente novo
insert into auth.users (id, email) values
  ('11111111-1111-1111-1111-111111111111', 'admin@opert.com'),
  ('22222222-2222-2222-2222-222222222222', 'cliente@loja.com'),
  ('33333333-3333-3333-3333-333333333333', 'novo@loja.com');

insert into public.perfis (id, razao_social, cnpj, telefone, aprovado, admin) values
  ('11111111-1111-1111-1111-111111111111', 'Opert', '00.000.000/0001-00', '11', true, true),
  ('22222222-2222-2222-2222-222222222222', 'Loja Boa', '11.111.111/0001-11', '11', true, false),
  ('33333333-3333-3333-3333-333333333333', 'Loja Nova', '22.222.222/0001-22', '11', false, false);

insert into public.precos (codigo, de, valor) values ('KP-586', '768,90', '670,00');

\set QUIET off
\pset tuples_only on

create or replace function public.checar(descricao text, condicao boolean)
returns text language sql as $$
  select case when condicao then 'ok      ' else 'FALHOU  ' end || descricao;
$$;

-- ============================ cliente aprovado ==============================
set role authenticated;
set teste.usuario = '22222222-2222-2222-2222-222222222222';

select public.checar('cliente aprovado lê a tabela de preços',
                     (select count(*) from public.precos) = 1);

select public.checar('cliente aprovado enxerga só o próprio perfil',
                     (select count(*) from public.perfis) = 1);

insert into public.pedidos (total, observacao) values (100.00, 'teste');
insert into public.pedido_itens (pedido_id, codigo, nome, caixas, pecas, preco_unit, subtotal)
  select id, 'KP-586', 'INVERSOR', 1, 3, 670.00, 2010.00 from public.pedidos limit 1;

select public.checar('cliente cria pedido e recebe número',
                     (select numero ~ '^\d{4}-\d{4}$' from public.pedidos limit 1));

select public.checar('pedido nasce como pendente',
                     (select status = 'pendente' from public.pedidos limit 1));

select public.checar('histórico registrado sozinho na criação',
                     (select count(*) from public.pedido_eventos) = 1);

do $$
declare erro text := 'sem erro';
begin
  update public.perfis set aprovado = true, admin = true
   where id = '22222222-2222-2222-2222-222222222222';
exception when others then erro := 'bloqueado';
end $$;

select public.checar('cliente não consegue se tornar admin',
                     (select not admin from public.perfis
                       where id = '22222222-2222-2222-2222-222222222222'));

update public.pedidos set status = 'pago';
select public.checar('cliente não muda o status do próprio pedido',
                     (select status = 'pendente' from public.pedidos limit 1));

-- ============================== cliente novo ================================
set teste.usuario = '33333333-3333-3333-3333-333333333333';

select public.checar('cliente sem aprovação não vê preço nenhum',
                     (select count(*) from public.precos) = 0);

select public.checar('cliente não enxerga pedido de outro cliente',
                     (select count(*) from public.pedidos) = 0);

do $$ begin
  insert into public.pedidos (total) values (50.00);
exception when others then null;    -- barrado pela RLS, que é o esperado
end $$;
select public.checar('cliente sem aprovação não consegue pedir',
                     (select count(*) from public.pedidos) = 0);

-- =================================== admin ==================================
set teste.usuario = '11111111-1111-1111-1111-111111111111';

select public.checar('admin enxerga todos os cadastros',
                     (select count(*) from public.perfis) = 3);

select public.checar('admin enxerga todos os pedidos',
                     (select count(*) from public.pedidos) = 1);

update public.perfis set aprovado = true
 where id = '33333333-3333-3333-3333-333333333333';
select public.checar('admin aprova cadastro',
                     (select aprovado from public.perfis
                       where id = '33333333-3333-3333-3333-333333333333'));

update public.pedidos set status = 'faturado';
select public.checar('admin muda status do pedido',
                     (select status = 'faturado' from public.pedidos limit 1));

select public.checar('mudança de status virou histórico',
                     (select count(*) from public.pedido_eventos) = 2);

-- ============================ visitante sem conta ===========================
set teste.usuario = '';
select public.checar('visitante sem conta não lê preço',
                     (select count(*) from public.precos) = 0);
select public.checar('visitante sem conta não lê pedidos',
                     (select count(*) from public.pedidos) = 0);

reset role;
