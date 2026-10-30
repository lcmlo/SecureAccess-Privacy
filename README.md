# SecureAccess Privacy

Evolução académica do [SecureAccess](https://github.com/lcmlo/SecureAccess) com autenticação multifator e funcionalidades de controlo dos dados pessoais. Demonstra minimização, pseudonimização, transparência, menor privilégio e retenção limitada. Não constitui uma declaração de conformidade integral com o RGPD.

## Arquitetura

Monólito modular Flask com Application Factory, quatro Blueprints, Service Layer, modelos SQLAlchemy e migrações Flask-Migrate/Alembic. Frontend Jinja2, HTML5, CSS3 e JavaScript progressivo, sem frameworks frontend. SQLite continua a ser a base de dados.

- `app/__init__.py`: única fábrica `create_app()`; configuração e registo das extensões/Blueprints.
- `app/config.py`: configuração de desenvolvimento, teste e produção.
- `app/extensions.py`: SQLAlchemy, Flask-Migrate, Flask-Login e CSRFProtect (Flask-WTF).
- `app/models/`: User, AuditLog, DeletionRequest, DeletionHistory e AuthAttempt.
- `app/routes/`: HTTP, validação/autorização, chamadas aos serviços e respostas.
- `app/services/`: autenticação, MFA, auditoria, contas, exportação/eliminação e retenção.
- `app/utils/`: RBAC, HMAC, adaptação de formulários e controlos HTTP comuns.
- `app/templates/`: layouts e componentes partilhados, autenticação, seis ecrãs user, seis admin e erros.
- `app/static/`: CSS e JavaScript por área, logótipo SVG.

```text
SecureAccess-Privacy/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── extensions.py
│   ├── cli.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── audit_log.py
│   │   ├── deletion_request.py
│   │   └── auth_attempt.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── user.py
│   │   ├── admin.py
│   │   └── privacy.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── mfa_service.py
│   │   ├── audit_service.py
│   │   ├── user_service.py
│   │   ├── privacy_service.py
│   │   └── retention_service.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── decorators.py
│   │   ├── pseudonymization.py
│   │   ├── forms.py
│   │   └── web_security.py
│   ├── templates/
│   │   ├── layouts/       # base, auth_base, user_base, admin_base
│   │   ├── components/    # sidebars, navbar, alerts, tabelas e cartões
│   │   ├── auth/          # login, register, mfa_setup, mfa_verify
│   │   ├── user/          # os seis ecrãs do utilizador
│   │   ├── admin/         # os seis ecrãs administrativos
│   │   └── errors/        # 403, 404, 500 e fallback
│   └── static/
│       ├── css/           # main, auth, user, admin
│       ├── js/            # main, user, admin
│       └── images/logo.svg
├── instance/              # ignorada pelo Git
│   ├── secureaccess.db
│   └── backups/           # cópias legadas locais preservadas
├── migrations/
│   ├── alembic.ini
│   ├── env.py
│   ├── schema_compat.py
│   ├── script.py.mako
│   └── versions/0001_privacy_baseline.py
├── scripts/
│   ├── configure.py
│   ├── migrate_database.py
│   ├── create_admin.py
│   ├── cleanup_logs.py
│   └── cleanup.ps1
├── tests/                 # autenticação, MFA, permissões, privacidade,
│                          # auditoria, eliminação, arquitetura e migrações
├── docs/
│   ├── mockups/
│   └── implementation_report.md
├── .env.example
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── run.py
└── README.md
```

Não existe uma segunda aplicação Flask nem diretórios legados `secureaccess/`, `templates/` ou `static/` na raiz. O ponto de entrada anterior `app.py` foi substituído por `run.py` e pelo pacote `app`.

## Instalação e configuração

Requer Python 3.11 ou superior; validado com Python 3.13 no Windows. Dependências: Flask, Flask-SQLAlchemy/SQLAlchemy, Flask-Migrate/Alembic, Flask-WTF, Flask-Login, Werkzeug, pyotp, cryptography, qrcode/Pillow e python-dotenv. Pytest e Ruff são dependências de desenvolvimento.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/configure.py
```

O configurador completa `.env` sem imprimir segredos e preserva a chave Fernet existente. Só substitui a chave de sessão se tiver menos de 32 caracteres, invalidando cookies antigos. Nunca versionar `.env`.

| Variável | Finalidade |
| --- | --- |
| `FLASK_SECRET_KEY` | Chave aleatória de assinatura de sessão, mínimo 32 caracteres |
| `MFA_ENC_KEY` | Chave Fernet; preservar para conseguir decifrar os segredos existentes |
| `AUDIT_HMAC_KEY` | Chave aleatória independente para HMAC-SHA256, mínimo 32 caracteres |
| `MFA_DB_PATH` | Caminho SQLite absoluto ou relativo à raiz; omissão `instance/secureaccess.db` |
| `APP_ENV` | `development` (omissão), `testing` ou `production` |
| `COOKIE_SECURE` | Opcional: `0` apenas em HTTP local, `1` em HTTPS; produção exige `1` |

As configurações de produção ativam cookies Secure por omissão. Um override que os desative em produção é rejeitado. A aplicação não ativa debug automaticamente. Para HTTPS real usar um servidor WSGI e proxy configurados, sem expor o servidor de desenvolvimento.

## Base de dados e migrações

**Base nova:**

```powershell
.\.venv\Scripts\python.exe -m flask --app run db upgrade
```

**Importar uma base anterior:** parar o servidor antigo e executar, mantendo a chave MFA e a chave HMAC anteriores:

```powershell
.\.venv\Scripts\python.exe scripts/migrate_database.py --source CAMINHO_DA_BASE_ANTIGA --dry-run
.\.venv\Scripts\python.exe scripts/migrate_database.py --source CAMINHO_DA_BASE_ANTIGA
```

O script copia SQLite de forma consistente para `instance/secureaccess.db`, verifica a integridade e executa Alembic. A simulação usa uma cópia temporária e não altera a origem. Um destino existente nunca é substituído silenciosamente. A origem e os backups são preservados. O script atualiza apenas `MFA_DB_PATH` no `.env`, sem substituir chaves. Se `MFA_DB_PATH` estiver definido no ambiente do processo, atualizar também essa variável para o novo caminho.

A revisão `0001_privacy` suporta uma base vazia, o esquema SecureAccess original e a versão Privacy anterior. Adiciona os campos/tabelas/índices em falta sem recriar os utilizadores. Mantém os IDs, usernames, hashes, segredos cifrados, datas, eventos e pedidos. `role` tem valor inicial `user` e restrição user/admin. Os campos de segurança `active`, `session_version` e `last_totp_step` são preservados.

Antes de executar Alembic sobre um ficheiro existente, `migrations/env.py` cria um backup `.pre-alembic.bak`. As alterações e a revisão Alembic são gravadas numa transação SQLite. Não se utiliza `db.create_all()`. As datas mantêm a representação UTC textual compatível com os dados legados; a comparação automática de tipos está desativada para não converter o TIMESTAMP SQLite antigo desnecessariamente. O comparador `schema_compat.py` confirma no PRAGMA as ações das FKs inline legadas e normaliza a reflexão dos ROWIDs; não elimina diferenças reais de regras. Rever sempre as migrações geradas.

```powershell
.\.venv\Scripts\python.exe -m flask --app run db current
.\.venv\Scripts\python.exe -m flask --app run db check
# Apenas quando o modelo mudar, rever o ficheiro gerado antes de aplicar:
.\.venv\Scripts\python.exe -m flask --app run db migrate -m "descricao da alteracao"
.\.venv\Scripts\python.exe -m flask --app run db upgrade
```

A migração inicial de adoção não oferece downgrade destrutivo: para regressar ao esquema antigo, parar o servidor e restaurar o backup com o código do checkpoint correspondente. A base local anterior foi arquivada em `instance/backups/mfa.db.legacy.bak` e o seu backup original foi conservado. Novas instalações não têm estes ficheiros.

## Execução e administrador

O `run.py` inicia o servidor de desenvolvimento Flask sem modo debug e escuta em `0.0.0.0:5000`, o que permite aceder à aplicação a partir de outros dispositivos da mesma rede local.

```powershell
.\.venv\Scripts\python.exe run.py
```

- **No computador que executa a aplicação:** abrir http://127.0.0.1:5000.
- **Noutro dispositivo da mesma rede local:** abrir `http://IP_DO_SERVIDOR:5000`, substituindo `IP_DO_SERVIDOR` pelo endereço IPv4 do computador que executa a aplicação. No Windows, consultar o endereço através de `ipconfig`.
- **Alternativa com a CLI do Flask:** `.\.venv\Scripts\python.exe -m flask --app run run --host 0.0.0.0 --port 5000`.

O endereço `0.0.0.0` serve para escutar nas interfaces de rede; **não** é o endereço a introduzir no navegador de outro dispositivo. O acesso pode exigir uma regra de firewall que permita a porta 5000 na rede privada. Esta configuração destina-se apenas a testes numa rede local de confiança: não expor o servidor de desenvolvimento Flask diretamente à Internet. Para uma disponibilização pública, utilizar servidor WSGI, HTTPS e proxy configurados.

O registo atribui sempre `user`, mesmo quando o pedido tenta enviar `role=admin`. Para o primeiro administrador, registar uma conta, concluir a MFA e executar num terminal autorizado:

```powershell
.\.venv\Scripts\python.exe scripts/create_admin.py NOME_DO_UTILIZADOR
# Comando CLI equivalente:
.\.venv\Scripts\python.exe -m flask --app run promote-admin NOME_DO_UTILIZADOR
```

Autenticar novamente após a promoção. Não existem contas ou palavras-passe administrativas predefinidas. O script promove uma conta existente ativa com MFA; não contorna a configuração do segundo fator.

## Funcionalidades e perfis

O menu **user** contém exatamente Dashboard, Os meus dados, Histórico de acessos, Centro de Privacidade, Exportação de dados e Pedido de eliminação. Apresenta informação real da própria conta. O histórico tem filtros e paginação de 100 registos. A exportação seleciona conta, atividade e/ou pedidos, em JSON ou CSV, gerados em memória. O CSV usa linhas `categoria,registo,campo,valor` e neutraliza prefixos de fórmulas.

O menu **admin** contém exatamente Dashboard, Utilizadores, Logs de autenticação, Pedidos de eliminação, Perfis e permissões e Definições. Permite pesquisar contas, desativar/reativar, atribuir perfis, consultar logs pseudonimizados, processar pedidos e executar limpeza. As consultas administrativas apresentam até 200 contas/pedidos, com pesquisa de contas por nome/perfil. O quarto indicador mostra contas com MFA, pois não existe mecanismo de alertas.

Os perfis são verificados no backend em todas as rotas administrativas. Um administrador não pode alterar o próprio perfil/estado, processar o próprio pedido ou remover o último administrador ativo. Mantém os direitos pessoais em `/my-data`, `/history`, `/privacy`, `/export` e `/deletion`, sempre com o layout administrativo. Não se misturam menus.

Pedidos: `pendente` → `em processamento` → `concluído`. A conclusão elimina a conta, credenciais, eventos associados e contadores ligados à identidade na mesma transação. O comprovativo perde a ligação à conta; a sua história mínima é conservada temporariamente. Não se concluem pedidos sem executar a eliminação.

## Segurança e Privacy by Design

- Novas palavras-passe: 12 a 128 caracteres, hash scrypt; os hashes antigos continuam válidos.
- MFA TOTP obrigatória, com Fernet, QR em memória e proteção atómica contra reutilização do intervalo.
- Sessão autenticada: 30 minutos; autenticação pendente: cinco minutos. A versão na base permite revogar sessões e autenticações pendentes após alterações administrativas.
- Cookies HttpOnly e SameSite=Lax; Secure em HTTPS; HSTS em pedidos HTTPS.
- Flask-WTF valida CSRF assinado em todos os POST, inclusive autenticação e logout.
- SQLAlchemy parametriza consultas. Validação no servidor, autoescape Jinja, CSP só com scripts locais, proteção contra framing, `no-store` e `no-referrer`.
- Cinco tentativas por identidade/origem a cada 15 minutos; contadores SQLite HMAC persistem entre processos/reinícios. Não se guardam IPs em bruto nem se confia em `X-Forwarded-For` arbitrário.
- Exportações e operações sensíveis exigem palavra-passe e um código MFA ainda não usado. Depois de iniciar sessão, aguardar pelo próximo código.
- Exportação por lista positiva: exclui hashes, segredos, chaves, tokens, sessões e contadores internos. O titular é sempre selecionado pela identidade autenticada.
- Auditoria contém apenas referência HMAC, evento, data e resultado. As referências são dados pessoais pseudonimizados, não dados anónimos. Não há endpoints para editar logs.
- Sem telefone, localização ou histórico de dispositivos. Não se armazenam palavras-passe originais, códigos TOTP ou QR Codes.

## Retenção e agendamento

| Categoria | Prazo |
| --- | --- |
| Conta e autenticação | Até à conclusão da eliminação |
| Eventos de auditoria | 90 dias; removidos antecipadamente quando a conta é eliminada |
| Pedidos em aberto | Até ao tratamento |
| Comprovativos concluídos sem ligação à conta | 90 dias após conclusão |
| Contadores temporários | Janela de 15 minutos; remoção na limpeza seguinte |

Os 90 dias são uma decisão do protótipo para permitir análise de incidentes e demonstrar conservação limitada; não um prazo universal imposto pelo RGPD. Não existe mecanismo de conservação legal especial ou bloqueio por litígio.

A limpeza é idempotente e executa-se em pedidos HTTP não estáticos. Para correr sem tráfego:

```powershell
.\.venv\Scripts\python.exe scripts/cleanup_logs.py
# Alternativa:
.\.venv\Scripts\python.exe -m flask --app run cleanup
```

Configurar no Agendador de Tarefas do Windows uma tarefa diária às 03:00, com o executável absoluto `.venv\Scripts\python.exe` e o argumento absoluto `scripts\cleanup_logs.py`. O script não depende do diretório de trabalho. Alternativamente usar `powershell.exe -NoProfile -File "CAMINHO\scripts\cleanup.ps1"`. Ativar execução após uma hora agendada perdida e verificar o código de saída. A tarefa não é instalada automaticamente. Em Linux, agendar o mesmo script por cron/systemd.

Backups contêm dados históricos e segredos cifrados. Restringir permissões e definir conservação operacional: depois de validar uma migração, eliminar backups dispensáveis antes de tratar eliminações reais. A aplicação não apaga backups, snapshots ou histórico Git. `secure_delete` reduz resíduos nas páginas SQLite, sem garantir apagamento físico em SSD.

## Testes e qualidade

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check app scripts tests run.py migrations
.\.venv\Scripts\python.exe -m pip check
```

Validação final: **60 testes aprovados**, Ruff sem erros, formatação validada, dependências sem conflitos e Alembic sem diferenças pendentes. Os testes usam chaves efémeras e bases temporárias criadas por Alembic. Validam os 12 ecrãs, layouts e menus, login/MFA, sessões, CSRF, limites, RBAC/IDOR, auditoria, exportação, eliminação transacional, rollback, retenção, migração legada e scripts de simulação. Resultados detalhados em [docs/implementation_report.md](docs/implementation_report.md).

## Limitações

Sem recuperação/substituição/desativação de MFA, alteração de palavra-passe ou edição do perfil pessoal. Sem alertas, exportação administrativa, retenção legal especial, logs invioláveis ou scheduler instalado automaticamente. SQLite e limites por origem destinam-se a pequena escala e podem afetar utilizadores na mesma rede. Logout limpa o cookie atual; uma cópia roubada só é invalidada por expiração ou revogação da versão.

O `.env` original foi retirado do controlo de versões no checkpoint, mas pode existir no histórico anterior. Se houve exposição, a rotação da chave MFA exige recifrar os dados; a chave HMAC exige um plano para logs existentes. Não houve reescrita do histórico nem substituição automática dessas chaves.

Referências técnicas: [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/en/stable/quickstart/), [Flask-Migrate](https://flask-migrate.readthedocs.io/en/latest/) e [CSRF no Flask-WTF](https://flask-wtf.readthedocs.io/en/1.2.x/csrf/).
