# StockFlow

Sistema web de controle de estoque para organizar produtos, categorias e
movimentações. O StockFlow reúne cadastro, acompanhamento de saldo e histórico
de entradas e saídas em uma interface responsiva com indicadores operacionais.

## Funcionalidades

- Dashboard com valor de custo estimado, produtos ativos, alertas de estoque
  mínimo, movimentações do dia e atividade recente.
- Cadastro, edição, pesquisa e ativação/inativação de produtos e categorias.
- Registro transacional de entradas e saídas, com histórico associado ao
  produto e ao usuário autenticado.
- Histórico com paginação, ordenação e filtros por produto, código, usuário,
  operação e período.
- Autenticação por sessão, formulários protegidos por CSRF e senhas armazenadas
  com hash.
- Migrações de esquema com Flask-Migrate.

O módulo de saída atualiza o estoque e registra a movimentação; não é um módulo
de vendas com carrinho, pagamentos ou fechamento de caixa.

## Tecnologias

Python, Flask, Flask-SQLAlchemy, Flask-Migrate, MySQL, PyMySQL, Jinja, HTML,
CSS e JavaScript.

## Arquitetura

```text
app/
├── blueprints/       # Rotas de autenticação, produtos, categorias e estoque
├── models/           # Entidades SQLAlchemy
├── services/         # Regras de negócio e consultas
├── static/           # CSS e JavaScript
└── templates/        # Layouts e páginas Jinja
migrations/           # Histórico Alembic/Flask-Migrate
tests/                # Testes automatizados com banco isolado
config.py             # Configuração por ambiente
run.py                # Objeto WSGI e entrada local
Procfile              # Inicialização WSGI em hospedagens compatíveis
```

## Requisitos

- Python 3.10 ou superior.
- MySQL com InnoDB para desenvolvimento/deploy.
- PowerShell no Windows (ou shell equivalente).

As dependências de runtime estão fixadas no `requirements.txt`. Os testes
automatizados usam SQLite em memória e não precisam acessar o MySQL configurado
no arquivo `.env`.

## Executar localmente no Windows

Clone o repositório e, a partir da pasta do projeto, crie o ambiente virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Gere uma chave secreta para a aplicação:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Copie o resultado para `SECRET_KEY` no `.env`. A chave deve ser estável entre
reinicializações e igual em todas as instâncias da mesma aplicação. Não a
compartilhe nem a reutilize entre desenvolvimento e produção.

Crie um banco MySQL vazio e preencha manualmente `DATABASE_URL` no `.env`:

```text
mysql+pymysql://USUARIO:SENHA_CODIFICADA@HOST:3306/NOME_DO_BANCO?charset=utf8mb4
```

Mantenha essa variável em branco no `.env.example`. Caracteres reservados da
senha, como `@`, `:`, `/`, `?` e `#`, precisam ser codificados como URL antes
de serem inseridos na conexão. Uma URL iniciada por `mysql://` também é aceita
e convertida para o driver PyMySQL.

Use estes valores no ambiente local:

```dotenv
APP_ENV=development
FLASK_DEBUG=0
APP_TIMEZONE=America/Sao_Paulo
```

Confira a conexão e aplique o esquema versionado:

```powershell
flask --app run check-db
flask --app run db upgrade
flask --app run db current
```

Crie o primeiro usuário administrativo. A senha é digitada sem eco e persistida
como hash:

```powershell
flask --app run create-user --email pessoa@empresa.com --name "Pessoa Usuária"
```

Inicie a aplicação localmente:

```powershell
python run.py
```

Acesse `http://127.0.0.1:5000`. O servidor local só ativa debug quando
`APP_ENV=development` e `FLASK_DEBUG=1`; deixe-o desativado no uso normal.
`python run.py` recusa explicitamente o ambiente de produção.

### Migrações

Use `flask db migrate -m "Descrição"` após alterações nos modelos; revise o
arquivo criado antes de aplicá-lo. `flask db upgrade` aplica as revisões
pendentes. Não execute `flask db init` novamente: o repositório de migrações já
está incluído.

Se o banco já contiver tabelas, compare o esquema antes de executar migrações.
`flask db stamp head` só registra a revisão existente e não cria nem altera
tabelas. Faça backup antes de migrar um banco com dados importantes.

## Configuração de ambiente

| Variável | Finalidade |
| --- | --- |
| `SECRET_KEY` | Chave persistente para sessões e proteção CSRF. Obrigatória em produção. |
| `DATABASE_URL` | URL SQLAlchemy do MySQL. Obrigatória em produção; vazia no `.env.example`. |
| `APP_ENV` | `development`, `testing` ou `production`; produção é o padrão. |
| `APP_TIMEZONE` | Fuso de relatórios diários e filtros de data; padrão `America/Sao_Paulo`. |
| `FLASK_DEBUG` | Habilita debug somente no servidor local e apenas com `APP_ENV=development`. |
| `PORT` | Porta de escuta local; o padrão é `5000`. A hospedagem define essa variável. |

Em produção, a aplicação falha na inicialização se `SECRET_KEY` ou
`DATABASE_URL` estiver ausente, força cookies de sessão seguros e mantém o
debug desativado. Em desenvolvimento, uma chave aleatória temporária é gerada
quando nenhuma chave está configurada; as sessões deixam de ser válidas quando
o processo reinicia.

## Deploy com Railway e MySQL

O projeto está preparado para uma hospedagem Linux que ofereça Gunicorn e
MySQL. O `Procfile` inicia `run:app` com Gunicorn, vinculado a `0.0.0.0:$PORT`.
O endpoint `/health` verifica se a aplicação responde; `/ready` executa
`SELECT 1` e só retorna sucesso quando a conexão com o banco está disponível.

Fluxo recomendado para o Railway:

1. Crie um projeto, adicione um serviço MySQL e conecte o repositório como
   serviço da aplicação.
2. Configure as variáveis `APP_ENV=production`, `SECRET_KEY` (chave aleatória
   estável), `APP_TIMEZONE=America/Sao_Paulo` e `DATABASE_URL`.
3. Aponte `DATABASE_URL` para a URL privada de conexão do serviço MySQL. Se
   usar uma referência de variável Railway entre serviços, selecione a URL
   gerada pelo seu serviço de banco no painel. O adaptador aceita os esquemas
   `mysql://` e `mysql+pymysql://`.
4. Configure o comando de migração como etapa pré-deploy, se disponível:
   `flask --app run db upgrade`. Revise e aplique as migrações antes de enviar
   tráfego para uma versão que dependa de um novo esquema.
5. Use `gunicorn --workers 2 --bind 0.0.0.0:$PORT run:app` como comando de
   inicialização. O mesmo comando está no `Procfile`.
6. Configure `/ready` como verificação de prontidão, habilite o domínio e HTTPS
   e confira os logs de inicialização.
7. No shell do ambiente de produção, após as migrações, crie a primeira conta
   com `flask --app run create-user --email ... --name ...`. Não habilite
   cadastro público nem use senhas demonstrativas em produção.

Use a rede privada entre aplicação e banco quando disponível; não publique a
porta MySQL sem necessidade. Configure backups gerenciados e teste o
procedimento de restauração antes de guardar dados importantes. Faça backup
antes de migrações e nunca apague/recrie o banco de produção para corrigir um
problema de esquema.
Se o provedor exigir TLS para conexões MySQL, siga os parâmetros oficiais dele,
habilite validação do certificado/hostname e disponibilize certificados por
secret ou arquivo montado; nunca os adicione ao repositório.

O repositório ainda não está publicado por este ambiente e não há uma URL de
demonstração. O deploy real exige configurar a conta/projeto, provisionar o
MySQL, cadastrar as variáveis secretas e validar a conectividade no provedor.

## API de movimentações

| Método | Endpoint | Descrição |
| --- | --- | --- |
| `GET` | `/api/produtos` | Produtos ativos para registro de movimentações |
| `GET` | `/api/movimentacoes` | Histórico paginado, filtrável e ordenável |
| `GET` | `/api/movimentacoes/<id>` | Detalhe de movimentação |
| `POST` | `/api/movimentacoes/entradas` | Registra uma entrada |
| `POST` | `/api/movimentacoes/saidas` | Registra uma saída |

A API exige sessão autenticada. Requisições POST recebem JSON com
`produto_id`, `quantidade` e, opcionalmente, `observacao`; envie o token CSRF da
meta `csrf-token` no cabeçalho `X-CSRFToken`.

Parâmetros do histórico: `page`, `page_size` (1–100), `sort` (`data`,
`produto`, `tipo`, `quantidade` ou `usuario`), `direction` (`asc` ou `desc`),
`q` (nome/código do produto ou nome do usuário), `tipo` (`ENTRADA` ou `SAIDA`),
`data_inicio` e `data_fim` (`AAAA-MM-DD`). As datas são inclusivas no fuso
`APP_TIMEZONE` e podem ser combinadas com os demais filtros.

## Testes

```powershell
python -m unittest discover -s tests -v
```

A suíte aplica as migrações em SQLite em memória e cria dados fictícios
reproduzíveis. Ela cobre autenticação, CRUD, consistência do ciclo de estoque,
rollback de falhas, paginação, filtros, datas, consultas SQL e indicadores.
Os testes não leem nem modificam o banco indicado por `DATABASE_URL`.

## Capturas de tela

Capturas reais da interface, produzidas com registros fictícios em um banco
SQLite isolado:

| Dashboard | Produtos |
| --- | --- |
| ![Dashboard com indicadores e alertas de estoque](docs/images/dashboard.png) | ![Catálogo de produtos e saldos](docs/images/produtos.png) |

| Categorias | Movimentações |
| --- | --- |
| ![Categorias e quantidade de produtos associados](docs/images/categorias.png) | ![Registro e histórico de movimentações](docs/images/movimentacoes.png) |
