# Relatório de implementação — SecureAccess Privacy

Data: 26 de outubro de 2026.

## Diagnóstico e plano executado

A base original concentrava a aplicação em `app.py`: registo, verificação de hashes Werkzeug, MFA TOTP, configuração por QR Code, cifra Fernet e Flask-Login, com SQLite e templates Jinja/CSS. A base tinha apenas `users`. Foram mantidos a stack, os campos existentes e os percursos públicos `/`, `/register`, `/login`, `/setup-mfa`, `/mfa`, `/dashboard` e `/logout`; o logout passou a exigir POST por segurança.

Lacunas identificadas: chave de sessão com fallback `change-me`, `.env` versionado, ausência de CSRF e limites de tentativas, sessão pendente sem expiração, repetição de códigos TOTP, ausência de RBAC, auditoria, retenção e funcionalidades de privacidade. O debug e a exposição em todas as interfaces foram removidos do ponto de entrada.

Foram implementadas as fases de esquema/migração, segurança, privacidade, interface user, interface admin e testes/documentação. A validação automatizada abrange a integração de todas as camadas; não havia uma suite de testes anterior.

## Arquitetura final

`app.py` mantém o ponto de entrada e usa uma fábrica em `secureaccess/__init__.py`. Os módulos `auth`, `privacy` e `admin` organizam as rotas por responsabilidade; `db` concentra acesso SQLite, migração, retenção e CLI; `security` concentra CSRF, RBAC, limitação persistente, HMAC, auditoria e cabeçalhos. Não existe uma API paralela sem necessidade: os formulários Jinja fazem POST diretamente às rotas Flask.

As seis secções de cada menu são determinadas pelo perfil carregado da base em cada pedido autenticado. As verificações no backend não dependem do menu. Os dados pessoais são selecionados pelo ID da sessão; IDs de terceiros enviados em parâmetros de consulta ou formulários não escolhem o titular dos dados.

## Base de dados e migração

Migração aditiva com `BEGIN IMMEDIATE`, rollback em falha, `PRAGMA user_version=1`, backup consistente pela API SQLite e simulação numa cópia em memória. A execução é explícita por CLI e não ocorre silenciosamente no arranque.

- `users`: preserva os seis campos originais; adiciona `role`, `active`, `session_version`, `last_totp_step`.
- `audit_logs`: os cinco campos pedidos, índices por referência/data e restrição do resultado.
- `deletion_requests`: os cinco campos pedidos, estados restringidos, coerência de conclusão, FK anulável e índice único para um pedido aberto por conta.
- `deletion_history`: identificador, pedido, estado e data. Necessária para mostrar as transições reais sem inventar um histórico.
- `auth_attempts`: bucket HMAC, contador e expiração. Necessária para limites persistentes entre processos/reinícios.

Não se reconstroem contas nem se recifram os segredos. Testes com o esquema original verificam preservação byte a byte de hash e ciphertext, compatibilidade de hash PBKDF2 legado e decifragem após duas migrações.

## Funcionalidades e interface

Interface PT-PT, fundo claro, azul principal, escudo com cadeado SVG, sidebar por perfil, topbar com pesquisa funcional, identificação e logout. Grelhas de cartões responsivas e tabelas com scroll horizontal em ecrãs pequenos.

User: dashboard com dados reais; dados da conta; histórico próprio com filtros e paginação; transparência e retenção; exportação seletiva JSON/CSV; pedido e histórico de eliminação. Não se recolheram campos pessoais adicionais para preencher a interface.

Admin: indicadores reais; pesquisa por nome/perfil; estado MFA; desativação/reativação; atribuição de perfis; logs pseudonimizados com filtros; processamento de pedidos; matriz de permissões; consulta das regras e limpeza executável. Alterações administrativas invalidam sessões anteriores.

A identidade visual foi baseada no mockup local do dashboard. Não foram reproduzidas afirmações como «em conformidade», localizações ou dispositivos fictícios. O quarto indicador administrativo mostra MFA ativa porque não existe um mecanismo de alertas.

## Privacy by Design e controlos de segurança

- Minimização: sem email, morada, telefone, localização ou dispositivos. Os IPs usados para limitar tentativas são HMAC temporários e não aparecem nos logs.
- Segregação: rotas administrativas com `admin_required` e dados próprios com `login_required`; perfil e estado obtidos da base. Não é permitido alterar a própria conta administrativamente.
- Hash scrypt para novas palavras-passe; hashes legados preservados. Segredos TOTP continuam protegidos com Fernet e chave externa ao código.
- Códigos TOTP não guardados. O último intervalo aceite é atualizado condicionalmente para impedir reutilização e concorrência.
- Reautenticação com palavra-passe e código MFA novo para exportação, pedidos e operações administrativas.
- CSRF em todos os POST, consultas parametrizadas, validação e tamanho de pedidos limitado; escape Jinja e CSP sem scripts.
- Cookie HttpOnly e SameSite=Lax; Secure configurável para HTTPS; HSTS apenas em HTTPS; sem cache de respostas sensíveis.
- Sessão absoluta de 30 minutos e autenticação pendente de cinco minutos. Versão de sessão revogável, incluindo a autenticação pendente.
- Limites persistentes por identidade/origem. Erros de autenticação genéricos e hash fictício para contas inexistentes.
- Auditoria sem usernames, hashes, códigos, segredos ou tokens em bruto. HMAC-SHA256 com chave separada; a pseudonimização não é apresentada como anonimização.
- Exportações sem segredos, geradas em memória e com nome fixo; proteção contra fórmulas no CSV. A própria operação é auditada.
- Não existem rotas de edição ou eliminação arbitrária dos logs. O administrador do host continua a ter controlo sobre SQLite: a integridade não é criptograficamente inviolável.

As medidas foram verificadas contra as orientações primárias de [segurança do Flask](https://flask.palletsprojects.com/en/stable/web-security/) e [autenticação da OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html). Não foi efetuada uma auditoria externa de segurança ou conformidade.

## Eliminação e retenção

O estado inicial é pendente. O administrador inicia processamento e, numa operação posterior, conclui. A conclusão elimina a conta e eventos associados, remove contadores associados à identidade e desvincula o comprovativo por FK, na mesma transação. Um rollback impede conclusões parciais. Outro administrador deve tratar pedidos administrativos próprios.

O comprovativo conserva apenas ID do pedido, datas e estados/histórico, sem `user_id` após a conclusão. O evento da conclusão fica associado ao administrador executor, sem guardar a identidade eliminada. Não se mantém uma tabela de associação secreta à conta eliminada.

Logs e comprovativos concluídos: 90 dias, escolhidos para a demonstração de análise de incidentes e limitação da conservação. Não é um prazo legal universal. Dados da conta duram até à eliminação; pedidos abertos duram até ao tratamento; contadores expiram ao fim de 15 minutos. A limpeza é automática em pedidos não estáticos, executável pela CLI e tem script para tarefa diária Windows. O agendamento do sistema operativo está documentado, mas não foi instalado no computador do utilizador.

`secure_delete=ON` reduz resíduos nas páginas SQLite. Não garante apagamento físico de SSD, snapshots, cópias de segurança ou histórico Git. Os backups de migração não são eliminados automaticamente: a gestão operacional deve impedir que prolonguem indevidamente a retenção.

## Testes e resultados

Ambiente: Windows, Python 3.13, ambiente virtual isolado `.venv`. Stack original preservada; Flask atualizado para 3.1.3, Werkzeug para 3.1.9 e Pillow para 13.0.0 após consulta ao índice de pacotes. Pytest adicionado em `requirements-dev.txt`. A compatibilidade dos hashes e do QR Code foi novamente testada.

- Primeira execução integrada: **31 testes aprovados**, 9,11 s.
- Execução ampliada: **37 testes aprovados**, 11,06 s.
- Após as correções de autenticação pendente e formatação: **37 testes aprovados**, 10,30 s. Após atualização das dependências: **37 testes aprovados**, 10,60 s; `pip check` sem conflitos. Execução final após tradução dos erros HTTP: **37 testes aprovados**, 10,98 s. O servidor final respondeu a `/login` com HTTP 200, PT-PT, CSRF e `no-store`.
- Configuração local executada sem apresentar segredos e preservando a chave Fernet.
- `flask --app app migrate --dry-run`: validado.
- `flask --app app migrate`: concluído com backup.
- Servidor HTTP local iniciado em 127.0.0.1:5000, debug desativado.

Cobertura funcional: registo e perfil imposto pelo servidor; login válido/inválido; ativação MFA e código incorreto; repetição TOTP; logout; expiração; CSRF; limitação persistente; seis rotas administrativas bloqueadas a user; isolamento de dados/pedidos/exportação; filtros; JSON e CSV sem segredos; auditoria pseudonimizada; eliminação real e integridade referencial; transições inválidas; retenção com conservação de pedidos abertos; desativação e revogação; pesquisa/injeção SQL; escape XSS; CLI e preservação de credenciais na migração.

A renderização de páginas foi validada pelos testes HTTP/Jinja para ambos os perfis. A inspeção visual interativa não ficou concluída: o navegador não expôs acessibilidade e a captura deixou de corresponder à janela alvo após interação do utilizador. Não se declara aprovação visual em dispositivos reais nem testes end-to-end completos de navegador.

## Diferenças e limitações

- Sem contas fictícias na base da aplicação. As fixtures de testes existem apenas em SQLite temporário.
- A MFA é obrigatória, como no fluxo original. A página de gestão informa o estado e a política; não permite desativação, substituição ou recuperação de autenticador.
- Não há alteração de palavra-passe ou dados de perfil. Não se introduziram campos pessoais adicionais.
- Exportação administrativa e alertas não foram implementados por falta de finalidade/autorização específica; a interface não simula estas funções.
- Os prazos de retenção e as políticas são consultáveis, mas não editáveis pela interface.
- Sem conservação por obrigação legal, bloqueio de eliminação por litígio ou gestão de backups dentro da aplicação. Não usar o protótipo para dados sujeitos a esses regimes sem adaptação.
- Sessões Flask assinadas, sem repositório central de sessões. Logout não revoga uma cópia roubada do mesmo cookie; expiração/desativação/alteração de versão revogam-na.
- Sem auditoria inviolável, recuperação de conta ou execução autónoma de um scheduler dentro do servidor web. O Agendador de Tarefas exige configuração operacional.
- Limites de escala: até 200 contas/pedidos por consulta administrativa, SQLite e limites de origem partilhados por NAT.
- O `.env` foi removido do índice Git, mantendo o ficheiro local. As versões históricas exigem avaliação e rotação coordenada se houve exposição. Não foi reescrito o histórico.

A implementação demonstra mecanismos concretos de Privacy by Design; a avaliação jurídica, medidas organizativas e operação segura continuam necessárias e não são substituídas por estas funcionalidades.
