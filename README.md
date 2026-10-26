# SecureAccess Privacy

Aplicação académica que evolui o SecureAccess, mantendo Flask, SQLite, Jinja, Werkzeug, Flask-Login, TOTP e cifra Fernet. Demonstra controlo sobre os próprios dados, minimização, pseudonimização e retenção limitada. Não constitui uma certificação de conformidade com o RGPD.

## Instalação e execução (Windows / PowerShell)

Requer Python 3.11 ou superior. Validado com Python 3.13.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/configure.py
.\.venv\Scripts\python.exe -m flask --app app migrate --dry-run
.\.venv\Scripts\python.exe -m flask --app app migrate
.\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1
```

Abrir http://127.0.0.1:5000. O servidor de desenvolvimento escuta apenas no computador local. Não usar o servidor Flask em produção. O modo debug não é ativado por omissão.

Em Linux/macOS: usar `python3 -m venv .venv` e `.venv/bin/python` nos comandos seguintes.

## Configuração

O script `scripts/configure.py` completa o `.env` local sem imprimir segredos e sem substituir a chave Fernet existente. Se a chave de sessão anterior tiver menos de 32 caracteres, substitui-a e invalida os cookies antigos. Nunca copiar `.env` para o controlo de versões.

| Variável | Finalidade |
| --- | --- |
| `FLASK_SECRET_KEY` | Chave aleatória para assinatura dos cookies; pelo menos 32 caracteres |
| `MFA_ENC_KEY` | Chave Fernet válida; preservar a chave original para decifrar TOTP existentes |
| `AUDIT_HMAC_KEY` | Chave aleatória independente para HMAC-SHA256; pelo menos 32 caracteres |
| `MFA_DB_PATH` | Caminho da base SQLite; por omissão `mfa.db` na raiz |
| `COOKIE_SECURE` | `0` apenas para HTTP local; definir `1` quando servido por HTTPS |

`.env.example` contém apenas os nomes das variáveis. Fora de desenvolvimento, fornecer segredos pelo ambiente e limitar permissões de acesso aos ficheiros. Não rodar a chave MFA sem recifrar os segredos; não rodar a chave HMAC sem um plano para os eventos ainda conservados.

**Segredos históricos:** o repositório original incluía `.env`. Foi retirado do índice, mantendo a cópia local. A exclusão atual não remove versões anteriores do histórico Git. As chaves históricas devem ser consideradas expostas caso o repositório tenha sido partilhado. Uma rotação da chave MFA exige recifrar os dados, pelo que não é feita automaticamente.

## Migração e base de dados

O arranque não altera silenciosamente o esquema. Executar `migrate` explicitamente antes de servir pedidos. O comando `--dry-run` aplica a migração a uma cópia em memória. A aplicação definitiva cria primeiro um backup SQLite consistente, com data e hora no nome, e aplica alterações numa transação. A migração é repetível.

Para evoluir uma base existente, definir `MFA_DB_PATH` para o respetivo ficheiro e manter a `MFA_ENC_KEY` original. Os IDs, nomes, hashes, segredos cifrados, estado MFA e datas são preservados. Não foi importada ou modificada a base de outro repositório.

Novos campos de `users`: `role` (`user` por omissão; CHECK user/admin), `active`, `session_version` e `last_totp_step`. Estes suportam autorização, desativação, revogação e proteção contra repetição TOTP. As tabelas novas são `audit_logs`, `deletion_requests`, `deletion_history` e `auth_attempts`. As relações usam foreign keys e os comprovativos são desvinculados com `ON DELETE SET NULL`.

As cópias `.bak` contêm dados e segredos cifrados anteriores: devem ter acesso restrito e um prazo operacional próprio. Não ficam publicamente acessíveis. Para este protótipo, eliminar os backups da migração depois de validar o resultado, antes de processar eliminações reais; não manter cópias esquecidas. A eliminação na aplicação não apaga backups externos.

## Primeiro administrador e permissões

1. Registar uma conta e concluir a configuração MFA.
2. Num terminal local autorizado, executar:

```powershell
.\.venv\Scripts\python.exe -m flask --app app promote-admin NOME_DO_UTILIZADOR
```

3. Autenticar novamente: a promoção revoga as sessões anteriores.

O registo público ignora qualquer perfil enviado e atribui sempre `user`. A promoção pela CLI exige conta ativa com MFA e fica auditada. Não existe palavra-passe de administrador predefinida.

O utilizador consulta apenas os próprios dados. O administrador pode pesquisar contas, desativar/reativar, atribuir perfis, consultar logs pseudonimizados e processar pedidos. Estas operações exigem palavra-passe e um código MFA novo. Não pode alterar o próprio perfil ou estado, tratar o próprio pedido ou remover o último administrador ativo. O backend verifica o perfil em todas as rotas administrativas.

Os menus têm seis secções distintas por perfil. Um administrador também mantém os seus direitos pessoais através de `/my-data`, `/history`, `/privacy`, `/export` e `/deletion`, sem inserir essas secções no menu administrativo.

## Funcionalidades

- Registo, login, configuração MFA, TOTP e logout por POST.
- Dashboard do utilizador com MFA, último login conservado, privacidade e consulta dos dados.
- Histórico próprio e logs administrativos com filtros por data, evento e resultado; 100 registos por página.
- Centro de Privacidade com categorias e prazos correspondentes ao código.
- Exportação seletiva em JSON ou CSV de dados da conta, atividade e pedidos. Os CSV usam linhas `categoria,registo,campo,valor`. Neutralizam-se valores com prefixos de fórmulas.
- Exportação em memória, sem ficheiros públicos ou acesso por ID de terceiros. Exclui hashes, segredos, códigos, contadores e identificadores de sessão. Confirmação com palavra-passe e MFA.
- Pedidos de eliminação únicos em aberto: `pendente` → `em processamento` → `concluído`.
- A conclusão elimina a conta, hash, segredo, eventos e contadores associados à identidade, na mesma transação. O comprovativo e as três transições ficam sem ligação à conta. A sessão deixa de ser válida.
- Pesquisa administrativa por nome e perfil, até 200 contas; até 200 pedidos recentes.
- Indicadores administrativos reais: contas ativas, falhas nas últimas 24 horas, pedidos pendentes e contas com MFA. Não existe um sistema de alertas: o quarto cartão mostra cobertura MFA.
- Matriz de permissões, consulta de políticas e execução da limpeza.

## Segurança e proteção de dados

Novas palavras-passe: 12 a 128 caracteres, hash scrypt do Werkzeug; hashes antigos continuam válidos. Segredos TOTP cifrados com Fernet. QR Code em memória, mostrado apenas na ativação pendente. Cada intervalo TOTP só é aceite uma vez, com atualização condicional atómica; não se guardam códigos. Depois de iniciar sessão, aguardar pelo próximo código antes de exportar ou confirmar outra operação.

Autenticação pendente válida durante cinco minutos. Sessões assinadas HttpOnly, SameSite=Lax, duração absoluta de 30 minutos. A versão de sessão guardada na base revoga sessões e autenticações pendentes após alterações administrativas. Logout limpa o cookie; uma cópia previamente roubada do cookie só deixa de funcionar com expiração ou revogação administrativa. Não existe armazenamento de sessões em servidor.

Todas as operações POST validam CSRF. Queries parametrizadas, validação de entrada, limites de tamanho, autoescape Jinja, CSP sem scripts, proteção contra framing, `no-store` e `no-referrer`. Em HTTPS aplica-se HSTS. Os erros apresentados não incluem stacks nem segredos.

Cinco tentativas por identidade e por origem em cada janela de 15 minutos para login/MFA/confirmação/registo. Contadores persistentes SQLite guardam apenas HMAC e expiração. O IP não é guardado em bruto nem mostrado. Não se confia no cabeçalho `X-Forwarded-For`; atrás de proxy é necessário configurar uma origem de confiança de forma explícita. O limite partilhado por origem pode afetar utilizadores na mesma rede.

Eventos técnicos contêm apenas referência HMAC-SHA256, evento, timestamp e resultado. A associação é calculada no servidor com chave independente e o ID da conta. As referências são dados pessoais pseudonimizados, não dados anónimos. Não há endpoints para editar logs. Quem tem acesso direto à base/host continua a poder alterar dados: usar permissões do sistema e controlo de acesso ao ambiente.

## Retenção e limpeza

| Categoria | Prazo / regra |
| --- | --- |
| Conta e autenticação | Até à conclusão da eliminação |
| Auditoria | 90 dias; eventos associados removidos antecipadamente na eliminação |
| Pedidos abertos | Até ao tratamento |
| Comprovativos concluídos desvinculados | 90 dias após conclusão |
| Contadores temporários | Janela de 15 minutos; limpeza na próxima execução |
| Cookie autenticado / pendente | 30 / 5 minutos |

Os 90 dias são uma decisão documentada deste protótipo para permitir análise de incidentes e demonstrar o ciclo de vida, reduzindo a conservação indefinida. **Não são um prazo universal imposto pelo RGPD.** O projeto não implementa conservação especial, bloqueios legais ou arquivo por obrigação legal: não deve tratar dados sujeitos a essas regras sem adaptação.

A limpeza é idempotente, executada em cada pedido não estático e disponível pela CLI:

```powershell
.\.venv\Scripts\python.exe -m flask --app app cleanup
```

Para funcionar mesmo sem tráfego, configurar no Agendador de Tarefas do Windows uma tarefa diária às 03:00, com a conta de serviço autorizada, e a ação:

- Programa: `powershell.exe`
- Argumentos: `-NoProfile -File "C:\CAMINHO\SecureAccess-Privacy\scripts\cleanup.ps1"`
- Ativar execução assim que possível se a hora agendada for perdida.

O script fixa o diretório do projeto e devolve o código de saída. Confirmar o resultado na tarefa e na saída CLI. A tarefa do sistema não é instalada automaticamente; até ser configurada, a limpeza sem tráfego exige executar o comando manualmente. Em Linux, agendar o mesmo comando diariamente por cron/systemd.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Os testes usam bases temporárias e chaves efémeras, nunca a base local. Cobrem registo, MFA, repetição, login, logout, expiração, CSRF, limites, RBAC, isolamento de contas, exports, auditoria, retenção, transições/eliminação, revogação e preservação de credenciais na migração. Consulte `IMPLEMENTATION_REPORT.md` para os resultados da execução.

## Estrutura

```text
app.py                    Entrada compatível com Flask CLI
secureaccess/
  __init__.py             Fábrica e configuração
  db.py                   SQLite, migração e comandos de manutenção
  security.py             CSRF, RBAC, auditoria, HMAC, limitação, cabeçalhos
  auth.py                 Login, registo, sessões e MFA
  privacy.py              Direitos pessoais, filtros e exportação
  admin.py                Contas, pedidos e definições
scripts/
  configure.py            Preparação segura de .env
  cleanup.ps1             Execução agendável no Windows
templates/                Interfaces PT-PT e componentes Jinja
static/                   CSS responsivo e logótipo SVG
tests/                    Testes pytest
docs/mockups/             Referências visuais fornecidas
```

## Demonstração

Registar duas contas e associá-las a uma aplicação TOTP. Promover uma delas pela CLI. Na conta user, visitar as seis secções, exportar JSON/CSV e apresentar pedido de eliminação. Na conta admin, consultar indicadores/logs, pesquisar contas, iniciar processamento e concluir a eliminação. Confirmar que a conta eliminada perde o acesso e que fica apenas o comprovativo desvinculado. Utilizar contas descartáveis de demonstração.

## Limitações

Sem recuperação de conta, códigos de recuperação, substituição de autenticador ou alteração de palavra-passe/perfil pessoal. Sem exportação administrativa, alertas automáticos ou configuração de prazos pela interface. Sem mecanismo de retenção legal ou logs invioláveis. SQLite e contadores por origem destinam-se a um protótipo de pequena escala. A eliminação lógica e `secure_delete` não garantem apagamento físico de SSD, cópias, snapshots ou histórico Git. É necessária uma política de backups e operação segura fora da aplicação. A inspeção visual em navegador e dispositivos reais não substitui testes de acessibilidade e compatibilidade completos.

Referências técnicas: [segurança no Flask](https://flask.palletsprojects.com/en/stable/web-security/) e [autenticação na OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).
