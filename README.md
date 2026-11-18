# Veyon Control Panel

Painel para gerenciar computadores e ambientes e integrar a Veyon WebAPI v1. A aplicação escuta em todas as interfaces de rede na porta `8000`, permitindo acesso por `localhost` ou pelo IP da máquina na rede local.

## Iniciar

Instale as dependências e execute o painel:

```powershell
python -m pip install -r requirements.txt
python main.py
```

Ou abra `iniciar_painel.bat`. No próprio computador, acesse [http://localhost:8000](http://localhost:8000). Para acessar de outro dispositivo na mesma rede, descubra o endereço do computador que está executando o painel e acesse `http://<ENDERECO-DA-MAQUINA>:8000`. A documentação interativa fica em `http://<ENDERECO-DA-MAQUINA>:8000/docs`.

All /api routes require X-API-Key unless PANEL_DEV_MODE=true is enabled. The key is stored in the session and sent in the X-API-Key header.

For development, set PANEL_DEV_MODE=true in .env to disable the panel API key requirement. The default is false; restart the server after changing it.

## Catálogo e deploy de software

O catálogo é criado pela migração do banco e recebe um software de exemplo na primeira inicialização. Configure `LOCAL_NETWORK_CIDRS` no `.env` com uma ou mais redes separadas por vírgulas em formato CIDR para selecionar `url_local`; alvos fora dessas redes usam `url_publica`. Sem redes configuradas, o painel usa a URL pública. `SEED_SOFTWARE_LOCAL_URL` e `SEED_SOFTWARE_PUBLIC_URL` podem substituir as URLs da entrada de exemplo.

O endereço padrão do serviço Veyon é `http://localhost:11080`. Defina `VEYON_API_URL` para apontar a um servidor WebAPI proxy. Cada computador também pode usar um endereço de WebAPI próprio. O WebAPI precisa estar habilitado no Veyon.

Screen capture uses on-demand HTTP when opening a computer or clicking Refresh. Temporary failures leave the last displayed image in place.

Capturas HTTP bem-sucedidas ficam em cache por dois segundos; cada captura espera no m?ximo dois segundos e retorna sem conte?do quando o Veyon ainda n?o disponibilizou uma imagem.

## Banco de dados e migrações

O SQLite é criado em `data/veyon_panel.sqlite3`. Ao iniciar, o painel executa as migrações Alembic até a revisão mais recente. Para aplicar migrações manualmente:

```powershell
alembic upgrade head
```

Para criar uma migração após alterações nos modelos:

```powershell
alembic revision --autogenerate -m "descricao da alteracao"
```

`PANEL_DATA_DIR` pode apontar para outro diretório de dados e `DATABASE_URL` pode substituir a URL do banco. O `.gitignore` exclui os dados locais.

## Organização

- `veyon_panel/api/routers`: rotas REST de computadores, ambientes e proxy Veyon.
- `veyon_panel/models`: modelos SQLAlchemy.
- `veyon_panel/schemas`: validação Pydantic.
- `veyon_panel/db`: engine, sessão e execução Alembic.
- `veyon_panel/services`: comunicação HTTP com a WebAPI do Veyon.
- `migrations/versions`: histórico versionado do esquema do SQLite.
- `static/`: interface e estilos.

Ambientes agrupam computadores na navegação lateral e na grade, no estilo de locais/salas do Veyon. Nomes, endereços, observações e associação ao ambiente são persistidos no SQLite. Chaves privadas ficam apenas no navegador durante o login; sessões WebAPI ficam em memória e precisam ser refeitas após reiniciar o painel.

Para habilitar execução remota de scripts, configure `PANEL_PUBLIC_BASE_URL` com a URL alcançável pelos computadores clientes (incluindo esquema e porta). Os arquivos `.ps1` e `.bat` ficam em `PANEL_UPLOADS_DIR` ou, por padrão, em `data/uploads`. A execução, coleta do log e inventário usam `StartApp` e callbacks autenticados do painel; a URL pública e `X-API-Key` precisam estar acessíveis dos clientes.

Screen captures are requested on demand over HTTP. A two-second timeout returns no content, and the browser keeps the last displayed image.

O endpoint de execução aguarda o callback final dos scripts por até `SCRIPT_EXECUTION_TIMEOUT_SECONDS` (padrão de 300 segundos). O resultado inclui código de saída e saída padrão/erro; em timeout, o painel orienta consultar **Ver Log**.

## Rotas

| Método | Rota | Uso |
| --- | --- | --- |
| GET/POST | `/api/environments` | Listar e criar ambientes |
| PATCH/DELETE | `/api/environments/{id}` | Editar e remover ambientes |
| GET/POST | `/api/computers` | Listar e cadastrar computadores |
| PATCH/DELETE | `/api/computers/{id}` | Editar e remover computadores |
| GET | `/api/authentication/{host}/methods` | Consultar métodos de autenticação |
| POST/GET | `/api/connections` | Autenticar e listar sessões |
| DELETE | `/api/connections/{id}` | Encerrar sessão |
| GET | `/api/connections/{id}/framebuffer` | Capturar tela |
| GET | `/api/connections/{id}/features` | Listar recursos Veyon |
| GET/PUT | `/api/connections/{id}/features/{uuid}` | Consultar e controlar recurso |
| GET | `/api/connections/{id}/user` | Informações do usuário |
| GET | `/api/connections/{id}/session` | Informações da sessão |
| POST/GET | `/api/scripts/upload`, `/api/scripts` | Enviar e listar scripts `.ps1`/`.bat` |
| POST | `/api/scripts/execute` | Executar em lotes nos IPs selecionados |
| GET | `/api/scripts/log/{ip}` | Coletar log remoto |
| GET | `/api/inventory/{ip}` | Coletar inventário do registro do Windows |

Referência: [documentação oficial da Veyon WebAPI](https://docs.veyon.io/en/latest/developer/webapi.html).
