# Registo e perfis pessoais

O registo solicita username, email, palavra-passe e confirmação da palavra-passe. O hash seguro, CSRF, role=user e a configuração/validação MFA existentes mantêm-se. O nome e os restantes dados são preenchidos posteriormente em «Os meus dados».

## Unicidade e validação

Username: espaços exteriores removidos, 3 a 64 caracteres (letras, números, ponto, hífen e sublinhado). A comparação usa normalização Unicode NFC e casefold. O login também ignora diferenças de caixa.

Email: espaços exteriores removidos, formato validado (parte local ASCII até 64 caracteres, domínio válido convertido para IDNA, máximo 254 caracteres). A política de conta trata a parte local e o domínio sem distinção de caixa. Não remove pontos nem sufixos +tag. Endereços com parte local internacionalizada ou entre aspas não são suportados neste protótipo.

Os índices únicos uq_users_username_ci e uq_users_email_ci usam a collation SQLite IDENTITY_NOCASE, registada em todas as ligações SQLAlchemy. A verificação prévia apresenta mensagens específicas e o tratamento de IntegrityError cobre conflitos concorrentes. Ferramentas externas que escrevam diretamente na base também devem registar a collation; sem ela, as escritas que dependam dos índices são recusadas.

O email não é usado para contacto, recuperação ou login e não é considerado verificado. Uma futura recuperação exige um fluxo de verificação do endereço com token de uso único e expiração.

## Migrações e contas existentes

0002_user_profiles mantém a relação 1:1. 0003_registration_profile acrescenta email à conta e os campos facultativos ao perfil. Antes de qualquer alteração verifica conflitos normalizados e interrompe com os IDs afetados; não modifica nem elimina contas para resolver duplicados. As contas antigas mantêm o email NULL até o titular o preencher. Vários NULL são permitidos apenas para compatibilidade com essas contas; o registo HTTP exige email.

0004_birth_date substitui a idade editável pela data de nascimento facultativa. A antiga coluna age é renomeada para legacy_age, preservando os valores históricos sem inferir datas. A idade atual é calculada sempre que apresentada. Ver [data de nascimento e idade](birth_dates.md).

Aplicar com o servidor parado:

```powershell
.\.venv\Scripts\python.exe -m flask --app run db upgrade
.\.venv\Scripts\python.exe -m flask --app run db check
```

O ambiente Alembic cria automaticamente um backup SQLite consistente antes da migração e executa o DDL numa transação. Não recriar a base, gerar novas chaves nem alterar credenciais. O downgrade é bloqueado para evitar perda de dados pessoais; restaurar um backup se for necessário reverter.

A base local configurada é instance/secureaccess-local.db. A base original e os backups locais antigos foram eliminados a pedido do utilizador. Apenas a base ativa foi mantida. Ambas foram analisadas antes da migração: não tinham conflitos de usernames nem coluna de email.

## Perfil e fotografia

GET /my-data apresenta os valores guardados e a idade calculada. GET/POST /my-data/edit permite editar nome, username, email, data de nascimento, género, NIF, morada, estado civil e fotografia. A idade é apenas de leitura. O cargo é apenas consultável quando estiver definido e não é aceite do formulário. Role, estado da conta e MFA também não são editáveis neste fluxo.

Todos os campos adicionais são facultativos e destinados a demonstração académica com dados fictícios. Antes de recolher dados reais é necessário documentar finalidade, necessidade, fundamento, controlo de acessos e conservação. Estes campos não são necessários para autenticar. O titular pode apagá-los; são eliminados com a conta, sem conservação adicional.

Validação: nome até 120 caracteres, data de nascimento válida e não futura (sem idade máxima arbitrária), género e estado civil em listas fechadas, NIF com nove algarismos e dígito de controlo válido, morada até 300 caracteres. Rejeitam-se caracteres de controlo. As alterações exigem palavra-passe e um código MFA novo. Alterações de username ou email revogam outras sessões, mantendo válida a sessão atual.

A fotografia aceita JPEG, PNG ou WebP até 2 MB e 16 megapíxeis. O servidor verifica o conteúdo, reduz para até 512x512, converte para JPEG e remove metadados. Os bytes ficam em SQLite, associados ao perfil, sem caminhos ou nomes de ficheiros fornecidos pelo cliente. GET /my-data/photo obtém exclusivamente a fotografia da conta autenticada, com no-store. É possível substituir ou remover a fotografia. Em caso de erro o formulário mantém os campos textuais, mas é necessário voltar a selecionar o ficheiro.

O formulário tem duas colunas em desktop e uma em telemóvel, conservando navbar e sidebar. A confirmação de identidade mantém-se separada dos dados pessoais.

## Exportação, eliminação e auditoria

A lista positiva User.public_data inclui os campos pessoais e o indicador de fotografia, nunca segredos. A exportação account inclui também photo_jpeg_base64 quando houver imagem, em JSON e CSV. Mantém-se a proteção CSV contra fórmulas.

A cascata SQLAlchemy elimina o perfil, incluindo a fotografia, ao eliminar a conta pelo fluxo existente. A auditoria regista dados_pessoais_alterados com referência pseudonimizada, data UTC e resultado, sem valores antigos/novos. A área Admin mantém os dados mínimos para gestão de acesso e não expõe indiscriminadamente os campos pessoais.

## Testes e ficheiros

Os testes abrangem registo com confirmação da palavra-passe, MFA, validação de email, usernames e emails duplicados, diferenças de caixa e Unicode, restrições SQLite e fallback IntegrityError, conflitos na migração sem perda de dados, edição, datas de nascimento e idades, upload/substituição/remoção de imagens, rejeição de ficheiros inválidos, isolamento de perfis, CSRF, persistência após login e nova instância Flask, exportação e eliminação.

Ficheiros: app/utils/identifiers.py; app/extensions.py; app/models/user.py; app/models/user_profile.py; app/services/auth_service.py; app/services/profile_service.py; app/services/profile_photo.py; app/services/privacy_service.py; app/routes/auth.py; app/routes/user.py; app/utils/web_security.py; app/templates/auth/register.html; app/templates/user/edit_data.html; app/templates/user/my_data.html; app/static/css/main.css; migrations/versions/0003_registration_profile.py; tests/test_registration_extended_profile.py; tests/test_profiles.py; tests/test_auth.py; tests/test_admin_migration.py; tests/db_helpers.py; README.md; docs/personal_profiles.md.
