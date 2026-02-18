# Production deployment (Ubuntu + systemd + nginx)

## 1. Prepare server

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip nginx git
```

## 2. Clone project

```bash
cd /opt
sudo git clone https://github.com/MaximNNVolkov/auto_service.git
sudo chown -R $USER:$USER /opt/auto_service
cd /opt/auto_service
```

## 3. Setup virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Setup production env

```bash
cp .env.prod.example .env
nano .env
```

Set real values in `.env`, especially:
- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`

## 5. Migrate and collect static

```bash
set -a; source .env; set +a
python manage.py migrate --settings=config.settings.prod
python manage.py collectstatic --noinput --settings=config.settings.prod
```

## 6. Run Gunicorn (systemd)

Create `/etc/systemd/system/auto_service.service`:

```ini
[Unit]
Description=auto_service gunicorn
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/auto_service
EnvironmentFile=/opt/auto_service/.env
ExecStart=/opt/auto_service/venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now auto_service
sudo systemctl status auto_service
```

## 7. Configure nginx

Create `/etc/nginx/sites-available/auto_service`:

```nginx
server {
    listen 80;
    server_name example.com www.example.com;

    location /static/ {
        alias /opt/auto_service/staticfiles/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/auto_service /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```
