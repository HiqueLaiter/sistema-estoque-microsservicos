FROM nginx:alpine

# Configuração do servidor (substitui a padrão)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Arquivos estáticos da página
COPY index.html style.css app.js /usr/share/nginx/html/

EXPOSE 80