# SecureAccess Privacy

**Privacy by Design in a Flask-Based Authentication System**

O SecureAccess Privacy é um protótipo web desenvolvido em Python com Flask, que evolui o projeto [SecureAccess](https://github.com/lcmlo/SecureAccess), inicialmente concebido para demonstrar autenticação multifator (MFA) através de username, password e TOTP (*Time-Based One-Time Password*).

O projeto é desenvolvido no âmbito da unidade curricular de **Privacidade de Dados** e tem como objetivo estudar e aplicar medidas de proteção da privacidade ao longo do ciclo de vida dos dados tratados por um sistema de autenticação.

A evolução proposta segue a abordagem *Privacy by Design* (PbD) e considera princípios como a minimização de dados, a pseudonimização, a limitação da conservação, a transparência e o controlo de acesso.

## Objetivos

- Analisar os dados pessoais e de autenticação tratados pelo sistema.
- Aplicar os princípios de *Privacy by Design* desde a conceção das novas funcionalidades.
- Minimizar os dados recolhidos e armazenados.
- Implementar registos de autenticação com informação limitada e identificadores pseudonimizados.
- Definir mecanismos de retenção e eliminação de dados.
- Disponibilizar funcionalidades de consulta, exportação e eliminação dos dados associados à conta.
- Reforçar o controlo de acesso segundo o princípio do menor privilégio.

## Funcionalidades

### Protótipo de base

- Registo e autenticação de utilizadores.
- Autenticação multifator através de TOTP.
- Armazenamento de passwords através de hash.
- Cifragem dos segredos TOTP armazenados.
- Gestão de sessão e acesso a uma área autenticada.

### Evolução orientada para a privacidade

As seguintes funcionalidades constituem objetivos de desenvolvimento e serão identificadas como implementadas apenas após a respetiva validação.

- Registos de autenticação minimizados e pseudonimizados.
- Política de retenção e eliminação de registos.
- Área de consulta dos dados associados à conta.
- Exportação dos dados do utilizador.
- Eliminação da conta e tratamento dos dados associados.
- Perfis de acesso e restrição das operações administrativas.

## Tecnologias

- **Python** — linguagem de programação.
- **Flask** — framework web.
- **SQLite** — sistema de gestão de base de dados.
- **TOTP** — mecanismo de autenticação multifator.
- **cryptography** — biblioteca utilizada para a cifragem dos segredos TOTP.

## Enquadramento

O projeto tem como referência os princípios de *Privacy by Design*, o Regulamento Geral sobre a Proteção de Dados (RGPD) e recomendações técnicas relevantes para a segurança e privacidade dos sistemas de autenticação.

## Equipa

Projeto desenvolvido no âmbito da unidade curricular de **Privacidade de Dados** por:

- Miguel Bento — GitHub: [mvbento](https://github.com/mvbento)
- Luís Lourenço — GitHub: [lcmlo](https://github.com/lcmlo)
- Ricardo Ourelo — GitHub: [ricardo-ourelo](https://github.com/ricardo-ourelo)
- Josué da Glória — GitHub: [josueclm](https://github.com/josueclm)
- Daniel Morgado — GitHub:

## Instalação e execução

### Pré-requisitos

- Python 3.11 ou superior.
- Git.
- Ambiente virtual Python recomendado.

### 1. Clonar o repositório

```bash
git clone https://github.com/TEU-UTILIZADOR/SecureAccess-Privacy.git
cd SecureAccess-Privacy
```

Substituir o URL pelo endereço real do repositório.

### 2. Criar e ativar o ambiente virtual

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

### 3. Instalar as dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar as variáveis de ambiente

Criar um ficheiro `.env` na raiz do projeto, de acordo com as variáveis exigidas pela aplicação:

```dotenv
FLASK_SECRET_KEY=SUBSTITUIR_POR_UMA_CHAVE_FORTE
MFA_ENC_KEY=SUBSTITUIR_POR_UMA_CHAVE_FERNET
MFA_DB_PATH=mfa.db
```

As chaves devem ser geradas para o ambiente local. O ficheiro `.env` não deve ser incluído no repositório.

### 5. Executar a aplicação

```bash
python app.py
```

Se a aplicação iniciar corretamente, poderá ser acedida em `http://127.0.0.1:5000`, conforme a configuração do servidor.

## Segurança e privacidade

- Não armazenar passwords em texto simples.
- Proteger os segredos TOTP através de cifragem.
- Não registar passwords, códigos TOTP ou segredos criptográficos nos logs.
- Evitar expor identificadores de sessão e outros dados sensíveis nos registos.
- Aplicar o princípio do menor privilégio.
- Definir prazos de conservação adequados à finalidade dos registos.
- Excluir ficheiros de configuração, chaves e bases de dados locais do controlo de versões.

O protótipo destina-se a fins académicos e de demonstração. A sua utilização em produção exige uma avaliação adicional da segurança, da privacidade e dos requisitos operacionais.

## Licença

Projeto académico desenvolvido no âmbito da unidade curricular de Privacidade de Dados.
