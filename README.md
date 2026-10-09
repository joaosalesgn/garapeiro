# Sistema local da pastelaria — etapa inicial

Base do sistema definida em **Python + Django + SQLite**. Esta primeira etapa prepara o projeto, os modelos de cadastro e auditoria, o painel administrativo, os atalhos de Windows e a cópia de segurança do banco.

## O que já está incluído

- Modelos-base com data de criação/alteração e usuários responsáveis.
- Cancelamento lógico com data, usuário e motivo, preparado para as entidades financeiras.
- Cadastros de categorias, produtos, adicionais, vínculo produto–adicional, mesas, clientes e tipos de movimentação.
- Produtos com categoria selecionada a partir de um cadastro, preço e indicador de envio à cozinha.
- A migração de categorias transforma automaticamente os nomes de categoria já registrados em cadastros, sem apagar os produtos.
- Painel Django Admin para manter os cadastros e os usuários.
- Tela de atendimento: abertura de comandas para mesa, balcão/retirada ou entrega, inclusão de produtos e adicionais, histórico de pedidos, recebimentos parciais e fechamento após quitação.
- Painel da cozinha para avançar os itens de pendente a enviado e pronto.
- Tela de caixa para abertura com troco, entradas e saídas avulsas, acompanhamento do saldo esperado e fechamento com valor contado.
- Banco SQLite local (`db.sqlite3`), dentro desta pasta; não o compartilhe por pasta de rede.
- Rotina para gerar e verificar cópias de segurança do banco.

## Requisitos

- Windows 10/11 (atalhos fornecidos nesta etapa).
- Python 3.13 recomendado (as migrações entregues foram geradas com Django 5.2); Python 3.11 ou superior pode ser usado se compatível com a versão instalada do Django.
- Acesso à internet somente durante a preparação inicial para baixar Django. Depois, as telas e o banco funcionam localmente.

## Primeira preparação

1. Extraia a pasta do projeto em um local permanente no computador da empresa.
2. Execute `scripts\preparar_sistema.bat` uma vez. Ele cria o ambiente isolado, instala as dependências, cria o banco e solicita a criação do usuário administrador.
3. Para usar o sistema, execute `scripts\iniciar_sistema.bat`. O navegador abrirá o painel em `http://127.0.0.1:8000/admin/`; mantenha a janela do servidor aberta enquanto estiver usando.
4. Cadastre usuários em **Autenticação e autorização → Usuários** e os dados básicos pelas seções de cadastros.
5. Entre em **Cadastros** para acessar o Admin e manter usuários, categorias, produtos, adicionais, mesas e clientes. Faça login com o usuário criado na preparação inicial.

O comando `runserver` é destinado a esta primeira fase local, em um único computador. Antes de disponibilizar o sistema a outros computadores ou para uso de produção, será necessário preparar autenticação/HTTPS e um servidor apropriado; não exponha esta porta à internet.

Para criar um super usuário
.venv\Scripts\python.exe manage.py createsuperuser

Para resetar a senha de um super usuário
.venv\Scripts\python.exe manage.py changepassword admin

## Backup do SQLite

- Execute `scripts\backup_banco.bat` com o sistema aberto ou fechado. O comando SQLite de backup produz uma cópia consistente e verifica sua integridade.
- As cópias ficam em `backups\` com data e horário no nome. Copie periodicamente uma dessas cópias para outro dispositivo, como um HD externo; manter o backup apenas no mesmo computador não protege contra falha do disco.
- Para restaurar: feche o sistema; guarde uma cópia do `db.sqlite3` atual; copie o backup desejado para a pasta do projeto e renomeie-o para `db.sqlite3`; reabra o sistema.
- Confira periodicamente se o backup existe e se pode ser aberto; não apague a única cópia válida.

## Desenvolvimento

No terminal, dentro desta pasta:

```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe manage.py makemigrations atendimento
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createsuperuser
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Quando os modelos mudarem, gere e revise as migrações antes de aplicá-las. O arquivo SQLite guarda os dados locais e não deve ser enviado a repositório público.

## Sobre tabelas
Depois de efetuar suas mudanças na models.py execute esse comando para criar uma nova migration
.venv\Scripts\python.exe manage.py makemigrations atendimento

Depois de criado a migration execute esse comando para rodar as migrations
.venv\Scripts\python.exe manage.py migrate

## Próxima etapa

Esta base ainda não inclui tela de atendimento, vendas, comandas, caixa, contas a pagar/receber, relatórios ou impressão. O passo seguinte é construir o fluxo de atendimento e pedidos, preservando as regras de caixa já acordadas.

# Atualização incremental: comandas, pagamentos e caixa

Pacote de atualização para a cópia enviada do projeto. Ele contém somente os arquivos que devem ser adicionados/substituídos:

- Substituir `atendimento/models.py`, `atendimento/admin.py` e `atendimento/tests.py`.
- Adicionar `atendimento/migrations/0007_comandas_caixa.py`.

Não substitua todo o projeto e não copie banco SQLite. Faça backup antes de aplicar. A migração parte do histórico `0006_alter_adicional_nome` já aplicado.

## Instalação

Na pasta do projeto, feche o servidor e faça backup do banco. Copie os arquivos conforme a estrutura acima e rode, nessa ordem:

```bat
.venv\Scripts\python.exe manage.py showmigrations atendimento
.venv\Scripts\python.exe manage.py migrate --plan
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py test atendimento
```

Antes de aplicar, confira que as migrações `0001` a `0006` aparecem como aplicadas e que o plano propõe apenas `0007_comandas_caixa`. Se não, pare e não force a atualização.

## Escopo

Inclui entidades de comanda e seus itens, adicionais vendidos com preços históricos, pagamentos parciais e sua associação ao caixa, abertura/fechamento e movimentações avulsas. O painel Django Admin permite administrar os registros nesta fase.

Ainda não inclui telas próprias para atendimento/cozinha, nem uma operação transacional guiada para validar saldo, fechar comanda e apurar o valor contado do caixa. Não lance pagamentos também como entradas avulsas, para não duplicar valores. A estrutura inicial não deve ser tratada como solução de produção ou caixa fiscal.


## Endereços do sistema

- Atendimento e comandas: `http://127.0.0.1:8000/`
- Cozinha: `http://127.0.0.1:8000/cozinha/`
- Caixa: `http://127.0.0.1:8000/caixa/`
- Cadastros administrativos: `http://127.0.0.1:8000/admin/`

As telas operacionais exigem login. O painel administrativo serve para manter os cadastros e usuários. Para verificar a instalação e executar os testes no Windows, rode `scripts\testar_sistema.bat` ou use `.venv\Scripts\python.exe manage.py check` e `.venv\Scripts\python.exe manage.py test atendimento`.

## Atualização desta versão

A migração `0007` já existente é mantida sem alterações; as telas operacionais não mudam os modelos do banco, então não há nova migração nesta entrega. Faça backup do `db.sqlite3` com o sistema fechado antes de substituir a pasta do projeto. Não use o banco de exemplo nem os arquivos de backup que possam acompanhar o pacote como banco de produção.

Após substituir o código, rode:

```bat
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py test atendimento
```

As regras impedem mais de uma comanda aberta por mesa na tela, pagamentos superiores ao saldo e fechamento de comanda com valor em aberto. Pagamentos já entram no caixa automaticamente: não os registre novamente como entradas avulsas. O fechamento do caixa registra o valor contado e mostra o saldo esperado para conferência.

O projeto permanece voltado a uso local em um computador. Não exponha o servidor de desenvolvimento à internet; autenticação/HTTPS, impressão, relatórios e contas financeiras podem ser etapas futuras.
