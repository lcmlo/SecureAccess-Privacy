# Departamentos e cargos profissionais

Esta extensão representa a estrutura de uma empresa tecnológica fictícia. O cargo profissional e o departamento são independentes de `User.role`: atribuir CEO, Tech Lead ou Responsável de Segurança não concede acesso administrativo.

## Modelo e preservação

`Department (1) → (N) JobPosition (1) → (N) UserProfile (1) → (1) User`.

O perfil guarda apenas `job_position_id`, opcional; o departamento é obtido pelo cargo. As tabelas do catálogo têm nome, descrição facultativa, estado e datas UTC de criação/atualização. As chaves estrangeiras impedem eliminar cargos referenciados. A interface prefere desativação e não oferece eliminação definitiva. A eliminação da conta continua a eliminar o perfil e a sua atribuição, conservando o catálogo.

A migração `0005_organization`, posterior a `0004_birth_date`, cria as duas tabelas e a FK/index no perfil. O mecanismo existente em `migrations/env.py` cria uma cópia SQLite `.pre-alembic.bak` antes da operação. Não há recriação da base nem eliminação de contas. O antigo `job_title` fica intacto, identificado como texto anterior; não é convertido em atribuição por semelhança de nomes. O administrador revê e atribui um cargo relacional; remover essa atribuição não elimina o texto histórico. Este dado histórico pode ser objeto de uma migração futura aprovada, com finalidade e retenção definidas.

Os nomes usam a collation SQLite `ORGANIZATION_NOCASE`: normalização Unicode NFC, casefold, espaços exteriores removidos e sequências de espaços reduzidas. A unicidade existe na base: departamento por nome e cargo por par departamento/nome. Cargos com o mesmo nome em departamentos diferentes são permitidos. `IntegrityError` torna-se uma mensagem de conflito e rollback integral. Ferramentas SQLite externas que comparem estes índices devem registar a collation; os scripts da aplicação fazem-no.

## Inicialização em PowerShell

Na raiz do projeto, com o `.env` já configurado:

```powershell
.\.venv\Scripts\python.exe -m flask --app run:app db upgrade
.\.venv\Scripts\python.exe scripts/seed_job_positions.py
```

O seed usa a configuração e a sessão da aplicação, reserva a escrita SQLite e insere os dados numa transação. A repetição conserva atribuições, descrições, estados inativos e cargos adicionais. Informa departamentos/cargos criados e existentes; atualizados é zero por política de não substituir registos existentes. Executar apenas como operação de manutenção autorizada.

## Catálogo inicial: 6 departamentos e 21 cargos

| Departamento | Cargos |
|---|---|
| Direção | Diretor-Geral (CEO); Diretor de Tecnologia (CTO) |
| Desenvolvimento de Software | Tech Lead; Engenheiro de Software; Programador Backend; Programador Frontend; Engenheiro DevOps; Engenheiro de Qualidade de Software (QA) |
| Dados e Inteligência Artificial | Analista de Dados; Engenheiro de Dados; Cientista de Dados; Engenheiro de Inteligência Artificial |
| Cibersegurança e Privacidade | Analista de Cibersegurança; Responsável de Segurança da Informação; Responsável de Privacidade |
| Produto e Negócio | Gestor de Produto; Analista de Negócio; Designer UX/UI |
| Operações e Administração | Técnico de Recursos Humanos; Técnico de Suporte Informático; Técnico Financeiro e Administrativo |

## Utilização

Em **Admin → Utilizadores**, os separadores dão acesso à gestão de departamentos e cargos. Criar pede nome e descrição opcional; cargos também pedem departamento ativo. Selecionar **Editar / Alterar estado** permite editar, desativar ou reativar. Mudar um cargo de departamento, quando tem colaboradores, exige a confirmação explícita do impacto. Reativar um cargo exige departamento ativo.

**Atribuir/Alterar cargo** abre um formulário próprio com o colaborador e a atribuição atual. O departamento selecionado limita os cargos ativos apresentados. O servidor valida sempre a correspondência e os estados, mesmo sem JavaScript. **Remover atribuição** deixa cargo/departamento por atribuir e conserva a conta e o seu `role`. O administrador pode atribuir um cargo a si próprio através deste fluxo, nunca pela edição pessoal.

A listagem combina pesquisa por username/nome, departamento, cargo, perfil e estado, com paginação de 25 contas no servidor. Não apresenta email por não ser necessário a esta operação, nem NIF, morada ou fotografias. Os perfis User/Admin mostram a atribuição no cabeçalho e nos dados pessoais; o formulário pessoal apresenta campos de leitura e ignora valores profissionais manipulados. Cargo desativado continua identificável e bloqueia novas atribuições; desativar departamento impede novas atribuições de todos os seus cargos.

## Segurança e auditoria

As rotas usam sessão autenticada, `admin_required`, CSRF e confirmação por palavra-passe/TOTP. O serviço volta a ler o ator, estado, MFA, `role` e versão de sessão sob `BEGIN IMMEDIATE`, antes de qualquer escrita. O destino só é selecionado nas rotas administrativas autorizadas; a edição pessoal usa exclusivamente o titular autenticado. As consultas usam SQLAlchemy e parâmetros.

Eventos: `DEPARTMENT_CREATED`, `DEPARTMENT_UPDATED`, `DEPARTMENT_DEACTIVATED`, `DEPARTMENT_REACTIVATED`, `JOB_POSITION_CREATED`, `JOB_POSITION_UPDATED`, `JOB_POSITION_DEACTIVATED`, `JOB_POSITION_REACTIVATED`, `JOB_POSITION_ASSIGNED`, `JOB_POSITION_CHANGED`, `JOB_POSITION_REMOVED` e `ORGANIZATION_CHANGE_DENIED`. São registados tipo, data UTC, resultado e referência HMAC do ator; atribuições também produzem referência do titular quando distinto. Não são registados nomes pessoais, valores alterados, passwords ou códigos. Usam a mesma tabela e política `LOG_RETENTION_DAYS` existentes. CSRF/permissões recusados antes de entrar na rota mantêm o comportamento dos controlos globais existentes.

A exportação JSON/CSV da conta inclui cargo, departamento, identificador e estado da atribuição, além do texto histórico quando existir; mantém a lista positiva que exclui segredos. A eliminação elimina o perfil e a FK; não elimina entradas partilhadas do catálogo.

## Interface e validação

Os novos formulários reutilizam o layout e os temas existentes. Em desktop a gestão de colaboradores usa tabela; até 767 px os mesmos registos passam a cartões com labels e ações. Os catálogos usam uma grelha fluida, de uma coluna em mobile, e os formulários usam duas/uma colunas conforme o espaço. Não há dependência de hover, cores alternativas ou backend mobile.

A validação automatizada usa bases temporárias migradas por Alembic, contas fictícias, Pytest e Chrome headless. Abrange seed, unicidade na base, CRUD, atribuições a User/Admin, estados, mudança de departamento, CSRF, reautenticação, manipulação HTTP, sessões, paginação, auditoria, exportação, eliminação e preservação de dados legados. A verificação visual inclui 1920×1080, 1366×768, 768×1024, 430×932 e 390×844, mais tablet horizontal/mobile horizontal, em Claro/Escuro; os testes comuns verificam Automático e persistência. Não substitui uma validação manual em Safari/iPhone ou Android físicos.

## Ficheiros

- Modelos: `app/models/organization.py`, `user_profile.py`, `user.py`, `__init__.py`.
- Persistência: `migrations/versions/0005_organization.py`, `app/extensions.py`, `app/utils/organization_names.py`.
- Serviços e rotas: `app/services/organization_service.py`, `audit_service.py`, `app/routes/organization.py`, `admin.py`, `__init__.py`.
- Interface: `admin/organization_catalog.html`, `admin/job_assignment.html`, `admin/users.html`, `components/organization_tabs.html`, `components/sidebar_admin.html`, `user/my_data.html`, `user/edit_data.html`, `app/static/js/organization.js`, `app/static/css/main.css`.
- Recuperados componentes partilhados ausentes: `components/sidebar.html`, `components/account_identity.html`, `components/role_confirmation_form.html`, `admin/role_confirmation.html`.
- Operação: `scripts/seed_job_positions.py`, `scripts/migrate_database.py`.
- Testes: `tests/test_organization.py` e expectativas de arquitetura/migração/minimização nos testes existentes.
- Documentação: este documento, `README.md`, `docs/implementation_report.md`.
