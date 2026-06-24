# Deploy no Render (gratuito)

## Pré-requisitos
- Conta no GitHub (github.com)
- Conta no Render (render.com) — gratuito

## Passo a passo

### 1. Publicar no GitHub
```bash
cd audiencias
git init
git add .
git commit -m "Sistema de Audiências PF"
# Crie um repositório PRIVADO no GitHub e siga as instruções
git remote add origin https://github.com/SEU_USUARIO/audiencias-pf.git
git push -u origin main
```

### 2. Deploy no Render
1. Acesse render.com e faça login
2. Clique em **New > Blueprint**
3. Conecte seu repositório GitHub
4. O Render detecta o `render.yaml` automaticamente
5. Clique em **Apply** — banco PostgreSQL e app são criados juntos

### 3. Variáveis de ambiente (já configuradas pelo render.yaml)
- `SECRET_KEY` — gerada automaticamente
- `DATABASE_URL` — PostgreSQL gratuito conectado automaticamente

### 4. Primeiro acesso
- URL será: `https://audiencias-pf.onrender.com`
- Login: `admin` / Senha: `admin123`  ⚠️ **TROQUE IMEDIATAMENTE**

### 5. Copiar chaves VAPID para o Render
No painel do Render > audiencias-pf > Environment, adicione:
- `VAPID_PUBLIC_KEY` = conteúdo de vapid_keys.json → public_key
- `VAPID_PRIVATE_KEY` = conteúdo de vapid_keys.json → private_key

## Acesso pelo celular (PWA)

### Android (Chrome)
1. Abra o link do app no Chrome
2. Menu ⋮ > **Adicionar à tela inicial**
3. Toque em **Adicionar** — ícone aparece como app nativo

### iPhone (Safari)
1. Abra o link no Safari
2. Toque em **Compartilhar** (ícone de seta)
3. Toque em **Adicionar à Tela de Início**
4. Toque em **Adicionar**

> Notificações push funcionam no Android nativamente.
> No iPhone exigem iOS 16.4+ e o app adicionado à tela inicial.
