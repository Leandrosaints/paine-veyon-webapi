# Veyon Control Panel

Painel local para gerenciar computadores e ambientes e integrar a Veyon WebAPI v1. A aplicação escuta somente em `127.0.0.1:8000`.

## Iniciar

Instale as dependências e execute o painel:

```powershell
python -m pip install -r requirements.txt
python main.py
```

Ou abra `iniciar_painel.bat`. Acesse [http://127.0.0.1:8000](http://127.0.0.1:8000); a documentação interativa está em [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

O endereço padrão do serviço Veyon é `http://127.0.0.1:11080`. Defina `VEYON_API_URL` para apontar a um servidor WebAPI proxy. Cada computador também pode usar um endereço de WebAPI próprio. O WebAPI precisa estar habilitado no Veyon.

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

Referência: [documentação oficial da Veyon WebAPI](https://docs.veyon.io/en/latest/developer/webapi.html).
