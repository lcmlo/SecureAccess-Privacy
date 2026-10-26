# Relatório técnico — arquitetura definitiva do SecureAccess Privacy

Data: 26 de outubro de 2026.

## Diagnóstico e checkpoint

O estado anterior já implementava os requisitos funcionais principais em Flask, SQLite, Flask-Login, TOTP/Fernet e templates Jinja. A fábrica e os Blueprints estavam em `secureaccess/`, com acesso direto por `sqlite3` e lógica de domínio nas rotas. Não existiam modelos SQLAlchemy nem um histórico Alembic. Templates e CSS estavam concentrados na raiz.

Antes da reestruturação foi criado o checkpoint Git **`6ba5aab`** (`checkpoint: SecureAccess Privacy antes da arquitetura SQLAlchemy`). Inclui a implementação funcional anterior e os mockups. `.env`, bases e backups não foram publicados nesse checkpoint; a remoção de `.env` do índice ficou registada. Não se reescreveu o histórico anterior.

O código antigo foi conservado durante a implementação e só removido depois de a aplicação nova passar 55 testes, preservar a base local e iniciar através de `run.py`. A suite foi repetida depois da remoção. Não existem duas aplicações Flask independentes no resultado final.

## Arquitetura final e responsabilidades

A estrutura principal segue a referência solicitada:

- `run.py`: entrada CLI/WSGI e execução local.
- `app/__init__.py`: única Application Factory; valida configuração, inicializa extensões e regista quatro Blueprints.
- `app/config.py`: DevelopmentConfig, TestingConfig, ProductionConfig; leitura tardia das variáveis de ambiente, caminhos absolutos coerentes e regras de sessão/segurança.
- `app/extensions.py`: SQLAlchemy, Flask-Migrate, Flask-Login e CSRFProtect. Um listener configura foreign keys e secure_delete em ligações SQLite.
- `app/models/`: modelos User, AuditLog, DeletionRequest, DeletionHistory e AuthAttempt, relações e restrições.
- `app/routes/auth.py`: registo, login, configuração/verificação MFA e logout.
- `app/routes/user.py`: dashboard, dados próprios e histórico.
- `app/routes/privacy.py`: transparência, exportação e pedido de eliminação.
- `app/routes/admin.py`: indicadores, contas, logs, processamento, permissões e definições.
- `app/services/`: regras de negócio, consultas ORM, transações e serialização por lista positiva.
- `app/utils/`: RBAC, pseudonimização, adaptação de formulários e políticas HTTP comuns.
- `app/templates/layouts/`: base partilhada e layouts distintos de autenticação, utilizador e administração.
- `app/templates/components/`: marca, sidebars separados, navbar, mensagens, cartões e tabelas partilhados.
- `app/templates/auth/`, `user/`, `admin/` e `errors/`: ecrãs específicos, incluindo os 12 ecrãs principais pedidos e erros 403/404/500.
- `app/static/css/`, `js/` e `images/`: recursos separados por área e logótipo SVG.
- `instance/secureaccess.db`: base de desenvolvimento fora do Git; `instance/backups/` conserva a base legada e o backup anterior.
- `migrations/`: configuração Alembic, ambiente, revisão `0001_privacy` e compatibilidade de reflexão em `schema_compat.py`.
- `scripts/`: configuração, migração/cópia segura, atribuição de administrador e limpeza agendável.
- `tests/`: testes por domínio, migrações, arquitetura e scripts de manutenção.

A árvore detalhada e os comandos operacionais estão no README. Os ficheiros auxiliares acrescentados têm função concreta: AuthAttempt mantém limites entre processos, DeletionHistory permite mostrar transições reais, forms adapta dados HTTP aos serviços e web_security aplica as políticas transversais.

## SQLAlchemy e modelo de dados

As consultas e alterações da aplicação usam SQLAlchemy; as rotas não contêm SQL de negócio. `sqlite3` fica limitado à cópia/verificação de ficheiros nos scripts/migrações e às verificações independentes de regressão em testes. O comando transacional `BEGIN IMMEDIATE` é executado pela sessão SQLAlchemy antes de consultar invariantes administrativas partilhadas.

Preservam-se os campos originais de `users`: id, username, password_hash, totp_secret, mfa_enabled e created_at. O perfil admite apenas user/admin, com user por omissão. Mantêm-se os campos de segurança da versão Privacy anterior: active, session_version e last_totp_step. São necessários para desativação, revogação e proteção contra repetição TOTP.

`audit_logs` guarda apenas os cinco campos pedidos e índices por referência/data. `deletion_requests` mantém os cinco campos pedidos, FK com SET NULL, estados permitidos, coerência da data de conclusão e índice único de pedido aberto por conta. `deletion_history` contém pedido, estado e timestamp. `auth_attempts` contém bucket HMAC, contador e expiração.

Os timestamps continuam em UTC textual para compatibilidade com SQLite legado. Não se convertem hashes, ciphertexts, datas ou identificadores desnecessariamente. A comparação automática de tipos no Alembic está desativada devido ao TIMESTAMP original; alterações futuras de tipos exigem revisão explícita. A comparação dos restantes elementos do esquema continua disponível por `flask db check`. O comparador de compatibilidade normaliza apenas a reflexão das chaves INTEGER PRIMARY KEY/ROWID legadas e verifica ações de FKs inline por PRAGMA. Só exclui falsos diffs quando a regra real coincide com o modelo; uma alteração real de ação continua detetável, como verifica um teste dedicado. Não foram reconstruídas tabelas apenas para satisfazer diferenças de reflexão.

## Migrações e preservação

`0001_privacy` deteta tabelas, colunas e índices existentes. Suporta base vazia, SecureAccess original e a primeira versão Privacy, adicionando apenas o que falta. Não usa `db.create_all()`, não recria utilizadores e não faz stamp sem executar/verificar a migração.

O ambiente Alembic cria uma cópia SQLite consistente antes de atuar sobre um ficheiro existente e aplica DDL e revisão na mesma transação. A revisão inicial não disponibiliza downgrade que apague dados: o regresso ao esquema anterior exige restaurar um backup com o código do checkpoint.

O script `migrate_database.py` suporta `--source` e `--dry-run`, recusa origens explícitas inexistentes e destinos existentes que seriam substituídos. A simulação usa cópia temporária; o modo definitivo cria `instance/secureaccess.db` e atualiza apenas o caminho no `.env`. A chave Fernet e a chave HMAC foram preservadas.

Na base local, compararam-se todas as linhas de todas as tabelas anteriores com a cópia migrada: **preservação integral confirmada**, integridade SQLite **ok**, **zero violações de FK**, revisão **0001_privacy**. A base anterior foi depois arquivada como `instance/backups/mfa.db.legacy.bak`, preservando também o backup original. Não foram criadas contas fictícias na base local.

## Autenticação, MFA e sessões

Reutilizada a lógica funcional: hashes Werkzeug (scrypt para novas contas e compatibilidade com hashes legados), TOTP de seis dígitos, Fernet e QR Code gerado em memória. A proteção contra reutilização é uma atualização SQLAlchemy condicional do último intervalo aceite; o código em si não é armazenado.

O segredo só é apresentado na configuração MFA pendente. O pedido pendente expira após cinco minutos e exige uma versão de sessão ainda válida. A sessão autenticada tem duração absoluta de 30 minutos. Alterações administrativas incrementam a versão e revogam sessões e autenticações pendentes. O logout é exclusivamente POST.

CSRF passou para Flask-WTF, com token assinado, duração de 30 minutos e validação de todos os POST, inclusive formulários de autenticação. Os testes continuam com CSRF ativo; usam o token realmente renderizado no HTML.

Contadores de tentativas usam UPSERT SQLite parametrizado pela camada SQLAlchemy, com limites por identidade e origem. Continuam a persistir entre pedidos/processos. Operações sensíveis exigem palavra-passe e um código MFA novo.

## RBAC, dados pessoais e auditoria

Novas contas recebem user no serviço, sem confiar em campos role enviados pelo cliente. O decorator administrativo verifica o perfil carregado da base em cada pedido. Os próprios dados são selecionados pelo utilizador autenticado, sem aceitar IDs de terceiros para exportação ou consulta.

Administradores podem executar apenas as operações implementadas. Não podem alterar o próprio perfil/estado, tratar o próprio pedido ou remover o último administrador ativo. As regras aplicam-se também no backend e os eventos relevantes são auditados.

As referências HMAC-SHA256 mantêm o formato e a chave da versão anterior, preservando a correlação autorizada do histórico. Os logs não recebem usernames, passwords, hashes, segredos, códigos ou identificadores de sessão em bruto. Pseudonimização não é anonimização.

A exportação usa listas positivas explícitas nos modelos/serviço, sem introspeção de todos os campos. JSON/CSV são gerados em memória, com titular autenticado, nome fixo e registo de auditoria. O CSV protege valores que poderiam ser interpretados como fórmulas.

## Eliminação e retenção

Transições: pendente → em processamento → concluído. O serviço conclui apenas depois de eliminar a conta, credenciais, eventos e contadores associados. O comprovativo fica desvinculado e conserva apenas os estados/datas mínimos. Todas as alterações são transacionais; um teste injeta falha na conclusão e verifica rollback de conta, logs e pedido.

Logs e comprovativos concluídos: 90 dias. Pedidos abertos: até ao tratamento. Contadores: janela de 15 minutos. Os prazos são escolhas documentadas do protótipo e não prazos universais do RGPD. Não se implementam conservação legal especial ou bloqueios por litígio.

A retenção automática por pedidos HTTP foi preservada. Existe comando CLI e `scripts/cleanup_logs.py`, executável a partir de qualquer diretório e compatível com Agendador de Tarefas/cron. O agendamento diário está documentado, mas não foi instalado no sistema operativo.

Uma tentativa de executar a limpeza sobre a base local real foi bloqueada pela revisão automática por poder eliminar registos sem pré-visualização do alcance. Não se contornou essa restrição: o script é validado por subprocesso apontado explicitamente a uma base temporária, com verificação de que apenas registos expirados são eliminados. A suite também valida a retenção e a cascata dos comprovativos.

## Interface e recursos reutilizáveis

Os menus têm exatamente seis entradas por perfil. Uma conta admin que visita os próprios dados mantém o layout administrativo. As rotas /dashboard, /my-data, /history, /privacy, /export, /deletion e /admin/* foram preservadas; apenas os nomes internos dos endpoints pessoais passaram de privacy para user.

O estilo claro/azul, escudo, cartões, tabelas responsivas e terminologia PT-PT foram preservados. JavaScript local acrescenta fecho de mensagens, validação da seleção de categorias e gestão de painéis administrativos, sem substituir a validação do servidor. CSP permite apenas scripts locais, sem inline.

Os dashboards e tabelas usam componentes partilhados, mantendo páginas e layouts separados. Não há indicadores, localizações, dispositivos ou alertas fictícios. O quarto cartão administrativo continua a apresentar cobertura MFA.

## Validação

Ambiente: Windows, Python 3.13 e .venv isolado. Stack existente preservada e acrescentados Flask-SQLAlchemy 3.1.1, SQLAlchemy 2.1.6, Flask-Migrate 4.1.0, Alembic 1.20.1 e Flask-WTF 1.3.0. Pytest e Ruff são ferramentas de desenvolvimento.

Resultados intermédios:

- Regressão anterior adaptada ao ORM/Alembic: **37 testes aprovados**.
- Arquitetura, 12 ecrãs, menus, CSRF, metadados e rollback: **55 testes aprovados**.
- Suite repetida após remoção do código obsoleto: **55 testes aprovados**.
- Scripts de migração/cópia/simulação: **57 testes aprovados**, 14,72 s.
- `run.py`: servidor iniciado em 127.0.0.1:5000, debug desligado; `/login` respondeu HTTP 200 com PT-PT, CSS no novo caminho e CSRF.
- Comparação da base local: todas as tabelas preservadas, integridade ok e sem violações FK.
- Verificação de dependências: `pip check` sem conflitos.

Execução final: **60 testes aprovados em 16,84 s**, incluindo login/MFA de uma conta do esquema original depois da migração e scripts de limpeza/promoção em subprocessos isolados. **Ruff sem erros**, **49 ficheiros Python com formatação validada**, **pip check sem conflitos**, **flask db check sem novas operações**. As fixtures nunca usam `db.create_all()` e não limpam nem semeiam a base local.

A revisão visual interativa em navegadores/dispositivos reais continua por concluir; os testes HTTP/Jinja verificam a renderização das 12 páginas, os nomes dos templates, os menus, os recursos e o isolamento de perfis. Não se declara uma aprovação visual ou de acessibilidade completa.

## Limitações e operação

Sem recuperação/substituição/desativação da MFA, alteração da palavra-passe ou edição do perfil pessoal. Sem alertas, exportação administrativa, políticas editáveis pela interface, retenção legal especial, logs invioláveis ou scheduler instalado automaticamente. SQLite é adequado à escala do protótipo; consultas administrativas têm limite de 200 e os limites por origem podem afetar utilizadores atrás do mesmo NAT.

A eliminação em SQLite e secure_delete não apagam cópias externas, snapshots, histórico Git ou garantem apagamento físico em SSD. Os backups preservados exigem permissões e política de conservação própria. Uma cópia roubada do cookie após logout só deixa de funcionar por expiração ou revogação da versão.

A chave MFA histórica não foi rodada automaticamente para não inutilizar os segredos existentes. Se houve exposição do `.env` em commits anteriores, é necessário um plano de recifragem/rotação; o histórico não foi reescrito.

A implementação demonstra mecanismos concretos de Privacy by Design, mas a avaliação jurídica, medidas organizativas e segurança operacional continuam necessárias.

Referências: [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/en/stable/quickstart/), [Flask-Migrate](https://flask-migrate.readthedocs.io/en/latest/) e [Flask-WTF CSRF](https://flask-wtf.readthedocs.io/en/1.2.x/csrf/).
