# Veyon Control Panel

Painel web local que integra as operações da **Veyon WebAPI v1**. A aplicação escuta somente em `127.0.0.1:8000`; a conexão com o serviço Veyon é configurável no painel.

## Iniciar no Windows

Execute `iniciar_painel.bat` ou, com o ambiente virtual ativado, rode:

```powershell
python main.py
```

Abra [http://127.0.0.1:8000](http://127.0.0.1:8000). A documentação OpenAPI interativa fica em [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

O endereço padrão da WebAPI é `http://127.0.0.1:11080`. Ele pode ser alterado no botão de configurações ou pela variável de ambiente `VEYON_API_URL`. O serviço Veyon precisa estar com WebAPI habilitada (porta padrão `11080`). Para o cenário proxy, informe o endereço do servidor Veyon e o host do computador remoto no formulário de conexão.

Exemplo de configuração:

```powershell
$env:VEYON_API_URL = "http://192.168.0.5:11080"
python main.py
```

## Operações disponíveis

- Descobrir métodos de autenticação; autenticar e fechar conexões.
- Capturar o framebuffer em PNG/JPEG e configurar qualidade e dimensões.
- Listar recursos, consultar status e iniciar/parar recursos.
- Interface para os recursos padrão: ScreenLock, InputDevicesLock, TextMessage, OpenWebsite, StartApp, UserLogin, UserLogoff, Reboot, PowerDown e recursos de demonstração.
- Consultar usuário e sessão da máquina.
- Executar UUIDs de recursos personalizados com argumentos JSON.

As rotas locais estão em `main.py`. A credencial é enviada ao Veyon somente durante a autenticação; o painel conserva a sessão em memória no backend e o navegador conserva apenas os cadastros e o identificador opaco local da conexão. Reiniciar o painel encerra o acesso a essas sessões locais.

## Rotas locais

| Método | Rota | Uso |
| --- | --- | --- |
| GET | `/api/config` | Configuração padrão |
| GET | `/api/health` | Saúde do painel |
| GET | `/api/authentication/{host}/methods` | Métodos de autenticação do host |
| POST | `/api/connections` | Criar conexão autenticada |
| GET | `/api/connections` | Listar conexões ativas |
| DELETE | `/api/connections/{id}` | Fechar conexão |
| GET | `/api/connections/{id}/framebuffer` | Captura de tela |
| GET | `/api/connections/{id}/features` | Listar recursos |
| GET | `/api/connections/{id}/features/{uuid}` | Consultar estado do recurso |
| PUT | `/api/connections/{id}/features/{uuid}` | Ativar/parar recurso |
| GET | `/api/connections/{id}/user` | Usuário da máquina |
| GET | `/api/connections/{id}/session` | Sessão da máquina |

Fonte da API: [documentação oficial Veyon WebAPI](https://docs.veyon.io/en/latest/developer/webapi.html).
