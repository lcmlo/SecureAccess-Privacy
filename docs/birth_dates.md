# Data de nascimento e idade calculada

O perfil guarda `birth_date`, um `DATE` facultativo. Não guarda a idade atual: `UserProfile.age` é uma propriedade calculada a partir da data atual. O campo Idade do formulário é apenas de leitura e não tem `name`, pelo que não é submetido. Valores `age` ou `legacy_age` enviados manualmente são ignorados pela lista de campos permitidos.

## Cálculo e validação

Python e JavaScript usam a data civil atual em **UTC**, coerente com a apresentação de horários da aplicação. A idade corresponde à diferença de anos menos um quando o mês/dia atual é anterior ao aniversário. Para quem nasceu em **29 de fevereiro**, o aniversário em anos não bissextos é considerado em **1 de março**. Num ano bissexto é considerado no próprio dia 29. Por exemplo, uma pessoa nascida em 29/02/2000 tem 24 anos em 28/02/2025 e 25 em 01/03/2025.

O servidor aceita apenas datas reais no formato ISO `AAAA-MM-DD`, não futuras, ou um valor vazio. Rejeita dias inexistentes, anos não bissextos com 29/02, ano zero, formatos alternativos e datas futuras. Não existe um limite arbitrário de idade; são aceites as datas representáveis por `datetime.date` (anos 1 a 9999), desde que não futuras. O input HTML `date` apresenta um calendário e `max` com a data atual.

No formulário, a idade é atualizada nos eventos `input` e `change`, sem pedidos ao servidor. A página de consulta tem o valor inicial calculado em Python e também se atualiza no navegador. Um temporizador volta a calcular à meia-noite UTC. O regresso a uma página suspensa, a mudança de visibilidade e o foco também atualizam a idade e o limite do calendário. Ao abrir uma página futuramente, Python volta a calcular a idade, mesmo que o perfil não tenha sido editado durante anos. Sem JavaScript, a idade é calculada no carregamento da página e após submissão.

## Migração e preservação

`migrations/versions/0004_birth_date.py` depende de `0003_registration_profile`. Em SQLite executa `RENAME COLUMN age TO legacy_age` e acrescenta `birth_date DATE NULL`; não recria a base nem as contas. Preserva integralmente as idades históricas e não as transforma em datas. O ambiente Alembic faz backup antes da migração e mantém as alterações numa transação.

`legacy_age` é histórico, não editável, não aparece como idade atual e não é alterado quando o titular preenche a data. Permanece associado ao perfil até ser definida uma estratégia explícita de conservação/migração. É incluído separadamente na exportação do titular quando existe, para não omitir dados conservados. O downgrade é bloqueado para evitar apagar datas de nascimento.

Aplicar com `python -m flask --app run db upgrade`, seguido de `db check`, usando o Python do ambiente virtual e a configuração local existente. A migração foi aplicada a `instance/secureaccess-local.db`; a comparação anterior/posterior confirmou que contas e idades históricas foram preservadas e nenhuma data foi inferida.

## Acesso, privacidade e interface

O titular consulta e altera exclusivamente o perfil identificado pela sessão. A edição mantém CSRF, palavra-passe atual e MFA. Não existem novos endpoints de consulta por ID nem exposição geral da data na lista Admin. O administrador autenticado pode gerir a sua própria data na página de dados pessoais.

A data de nascimento é **mais específica do que a idade**. Esta recolha é uma extensão demonstrativa e facultativa, destinada a dados fictícios; usar dados reais exige justificar finalidade, necessidade, acesso e conservação no âmbito de Privacy by Design. A auditoria continua a guardar apenas evento, referência pseudonimizada, data da operação e resultado, nunca a data de nascimento.

A exportação JSON/CSV inclui `birth_date` em ISO e a idade calculada no momento da exportação. A eliminação da conta elimina o perfil, incluindo data de nascimento e idade histórica, pela cascata existente.

O formulário apresenta Data de nascimento e Idade lado a lado em desktop e em coluna no telemóvel. A consulta do perfil usa a mesma disposição e apresenta a data em `DD/MM/AAAA`. Ambos são compatíveis com Claro, Escuro e Automático; na ausência de data, a idade é «Não indicada».

## Validação e ficheiros

**142 testes aprovados**, Ruff sem erros, JavaScript com sintaxe válida e Alembic sem diferenças pendentes. `tests/test_birth_dates.py` cobre datas válidas/vazias, limites do aniversário, anos bissextos, datas futuras e impossíveis, datas antigas sem limite arbitrário, persistência após login, idade recalculada sem edição, exportação, isolamento entre contas, eliminação e migração de idades históricas. Os testes existentes de perfis e migrações foram adaptados.

No Chrome, passaram 11 casos de cálculo/validação JavaScript, atualização após aniversário e verificações da disposição do formulário e da consulta. A verificação dos temas manteve 152 combinações de ecrã/tema/resolução aprovadas, incluindo os ecrãs de perfil.

Ficheiros desta alteração:

- `app/utils/birth_dates.py`, `app/models/user_profile.py`, `app/models/user.py`.
- `app/services/profile_service.py`, `app/routes/user.py`.
- `app/templates/user/edit_data.html`, `app/templates/user/my_data.html`.
- `app/static/js/main.js`, `app/static/css/main.css`.
- `migrations/versions/0004_birth_date.py`.
- `tests/test_birth_dates.py`, `tests/test_registration_extended_profile.py`, `tests/test_admin_migration.py`.
- `README.md`, `docs/personal_profiles.md`, `docs/birth_dates.md`.
