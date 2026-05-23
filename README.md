# Запуск корпоративного сервиса ведения документации с помощью MediaWiki
## Сбор требований
**ОС сервисов проекта:**<br>
Ubuntu Server 22.04 LTS.

**Необходимые библиотеки и фреймворки:**<br>
Nginx, PHP 8.1, PHP-FPM, PostgreSQL 14, MediaWiki 1.42.1, Zabbix 7.0, Ansible, Vagrant.<br>

**Планируемая нагрузка:**<br>
На первом этапе сервис рассчитан примерно на 40 сотрудников центрального офиса. В дальнейшем инфраструктура может быть расширена для офисных сотрудников и удалённых пользователей.<br>

**Специфика приложения:**<br>
MediaWiki используется как корпоративный сервис ведения документации. Сервис предоставляет возможность совместной работы с документами, хранения статей, загрузки изображений и доступа через веб-интерфейс.<br>

**Интерфейс взаимодействия с пользователем:**<br>
HTTP-сервис. Пользователи обращаются к MediaWiki через Nginx load balancer по адресу балансировщика.<br>

**Вспомогательные сервисы:**<br>
PostgreSQL primary/replica для хранения данных MediaWiki.<br>
Nginx load balancer для распределения трафика между двумя экземплярами MediaWiki.<br>
Backup-сервер для хранения резервных копий БД и файлов MediaWiki.<br>
Zabbix-сервер для мониторинга HTTP-доступности, времени ответа и доступности PostgreSQL по TCP-порту 5432.<br>

**Дополнительные технические решения:**<br>
Инфраструктура разворачивается локально с помощью Vagrant.<br>
Конфигурация серверов автоматизирована с помощью Ansible.<br>
Inventory формируется динамически на основе config.json.<br>
Резервное копирование выполняется по расписанию через cron.<br>

## Схема развёртывания
<img width="639" height="638" alt="Screenshot From 2026-04-29 09-36-53" src="https://github.com/user-attachments/assets/559177fc-1638-4560-a7ef-26de60d3d3e9" />

## План восстановления
**Отказ MediaWiki main-ноды**<br>
При отказе одной из MediaWiki нод сервис продолжает работать, так как балансировщик отправляет запросы на рабочую ноду<br>
Нерабочая нода чинится в зависимости от ошибки, если исправить ошибку нельзя можно пересоздать ВМ и запустить плейбук только для mediawiki_1 роли. Обязательно без повторной инициализации install.php

```console
vagrant destroy mediawiki-1 -f
vagrant up mediawiki-1
ansible-playbook playbook.yml --tags=mediawiki_1 -e mediawiki_run_installer=false
```
И скопировать из второй ноды или бэкапа LocalSetting.php<br>
С рабочей ноды:

```console
vagrant ssh mediawiki-2 -c "sudo cp /var/www/mediawiki/LocalSettings.php /tmp/LocalSettings.php && sudo chown vagrant:vagrant /tmp/LocalSettings.php"
vagrant ssh mediawiki-2 -c "cat /tmp/LocalSettings.php" > /tmp/LocalSettings.php
vagrant ssh mediawiki-1 -c "cat > /tmp/LocalSettings.php" < /tmp/LocalSettings.php
vagrant ssh mediawiki-1 -c "sudo cp /tmp/LocalSettings.php /var/www/mediawiki/LocalSettings.php && sudo chown www-data:www-data /var/www/mediawiki/LocalSettings.php && sudo chmod 600 /var/www/mediawiki/LocalSettings.php"
```
С бэкапа:

```console
vagrant ssh backup-1 -c "tar -tzf /srv/backups/mediawiki/latest.tar.gz | head"
vagrant ssh backup-1 -c "sudo base64 -w0 /srv/backups/mediawiki/latest.tar.gz" | \
vagrant ssh mediawiki-1 -c "base64 -d > /tmp/latest.tar.gz"
vagrant ssh mediawiki-1 -c "tar -tzf /tmp/latest.tar.gz | head"
vagrant ssh mediawiki-1 -c "
sudo rm -rf /var/www/mediawiki /var/www/mediawiki-1.42.1 &&
sudo tar -xzf /tmp/latest.tar.gz -C /var/www/ &&
sudo ln -sfn /var/www/mediawiki-1.42.1 /var/www/mediawiki &&
sudo chown -R www-data:www-data /var/www/mediawiki-1.42.1 &&
sudo chmod 600 /var/www/mediawiki/LocalSettings.php &&
sudo systemctl restart nginx php8.1-fpm
"
```

**Отказ MediaWiki ноды**<br>
При отказе одной из MediaWiki нод сервис продолжает работать, так как балансировщик отправляет запросы на рабочую ноду<br>
Нерабочая нода чинится в зависимости от ошибки, если исправить ошибку нельзя можно пересоздать ВМ и запустить плейбук только для mediawiki_2 роли.

```console
vagrant destroy mediawiki-2 -f
vagrant up mediawiki-2
ansible-playbook playbook.yml --tags=mediawiki_2
```

**Отказ Nginx балансировщика**<br>
При отказе балансировщика сервис не работает<br>
Для восстановления можно пересоздать ВМ и запустить плейбук

```console
vagrant destroy nginx-lb -f
vagrant up nginx-lb
ansible-playbook playbook.yml --tags=nginx
```

**Отказ Backup/Zabbix сервера**<br>
Сервера не влияют на работоспособность сервиса<br>
Для восстановления можно пересоздать ВМ и запустить плейбук

```console
vagrant destroy backup-1 -f
vagrant up backup-1
ansible-playbook playbook.yml --tags=backup
vagrant destroy zabbix-1 -f
vagrant up zabbix-1
ansible-playbook playbook.yml --tags=zabbix
```

**Отказ DB Replica**<br>
При отказе реплики сервис будет продолжать работать<br>
Для восстановления в зависимости от ошибки можно пересоздать ВМ и запустить плейбук, запустить плейбук с pg_basebackup с DB Primary или просто перезапустить плейбук

```console
vagrant destroy db-replica -f
vagrant up db-replica
ansible-playbook playbook.yml --tags=db_replica
ansible-playbook playbook.yml --tags=db_replica -e force_reinit_replica=true
vagrant ssh db-replica -c "sudo -u postgres psql -tAc 'SELECT pg_is_in_recovery();'"
vagrant ssh db-primary -c "sudo -u postgres psql -c 'SELECT client_addr, state FROM pg_stat_replication;'"
```

**Отказ DB Primary**<br>
При отказе праймари сервис не работает<br>
Для восстановления можно переключить реплику в праймари

```console
vagrant halt db-primary
vagrant ssh db-replica -c "sudo -u postgres pg_ctlcluster 14 main promote"
vagrant ssh db-replica -c "sudo -u postgres psql -tAc 'SELECT pg_is_in_recovery();'"
```
И поменять DB host в LocalSettings.php

```console
vagrant ssh mediawiki-1 -c "sudo sed -i 's/192.168.56.10/192.168.56.11/' /var/www/mediawiki/LocalSettings.php"
vagrant ssh mediawiki-2 -c "sudo sed -i 's/192.168.56.10/192.168.56.11/' /var/www/mediawiki/LocalSettings.php"
vagrant ssh mediawiki-1 -c "sudo systemctl restart php8.1-fpm nginx"
vagrant ssh mediawiki-2 -c "sudo systemctl restart php8.1-fpm nginx"
vagrant ssh db-replica -c "echo 'host    my_wiki    wikiuser    192.168.56.12/32    md5' | sudo tee -a /etc/postgresql/14/main/pg_hba.conf"
vagrant ssh db-replica -c "echo 'host    my_wiki    wikiuser    192.168.56.13/32    md5' | sudo tee -a /etc/postgresql/14/main/pg_hba.conf"
vagrant ssh db-replica -c "sudo systemctl reload postgresql"
```
Для восстановления также можно удалить DB Primary и DB replica, создать их снова и запустить плейбук. БД взять из бэкапа

**Проверка работоспособности бэкапа:**<br>
Добавим тестовых страниц в MediaWiki

```console
vagrant ssh db-primary -c "sudo -u postgres psql -d my_wiki -c 'SELECT COUNT(*) FROM mediawiki.page;'"
vagrant ssh backup-1 -c "sudo /opt/backup/backup_db.sh"
vagrant ssh backup-1 -c "sudo base64 -w0 /srv/backups/postgresql/latest.dump" | \
vagrant ssh db-primary -c "base64 -d > /tmp/latest_from_backup.dump"
vagrant ssh db-primary -c "sudo -u postgres dropdb my_wiki"
vagrant ssh db-primary -c "
sudo -u postgres createdb -O wikiuser my_wiki &&
sudo -u postgres pg_restore -d my_wiki /tmp/latest_from_backup.dump
"
```

## Выполнение работы

```console
ssh-keygen -f "/home/spark/.ssh/known_hosts" -R "[127.0.0.1]:2222"
ssh-keygen -f "/home/spark/.ssh/known_hosts" -R "[127.0.0.1]:2200"
ssh -i ~/.vagrant.d/insecure_private_key vagrant@ip
```

Создадим директорию для проекта

```console
mkdir yandex_practicum && cd yandex_practicum
mkdir vagrant
cd vagrant/
```

Установим Vagrant

```console
wget https://mirror.yandex.ru/mirrors/releases.hashicorp.com/vagrant/2.4.9/vagrant_2.4.9-1_amd64.deb
sudo dpkg -i vagrant_2.4.9-1_amd64.deb
rm vagrant_2.4.9-1_amd64.deb
vagrant --version
```

Установим Virtualbox

```console
sudo apt install virtualbox -y
```

Сделаем общий конфиг файл для переменных config.json. Будет нужен чтобы в одном месте менять основную конфигурацию и добавлять новые VM

```console
cd ~/yandex_practicum
code config.json
```
<img width="356" height="402" alt="Screenshot From 2026-04-29 09-46-48" src="https://github.com/user-attachments/assets/7cef713a-4adb-43a0-9a74-8708171ad4d4" />
<br><br>
Создадим Vagrantfile. Сперва поднимем 2 VM - DB Primary и DB Replica

```console
cd yandex_practicum/vagrant/
code Vagrantfile
```
<img width="616" height="345" alt="Screenshot From 2026-04-29 09-47-43" src="https://github.com/user-attachments/assets/987915e8-8aa0-41c4-af50-e518a06fa7ce" />
<br>
<img width="614" height="328" alt="Screenshot From 2026-04-29 09-48-09" src="https://github.com/user-attachments/assets/87420c56-02c2-41a0-87b6-2e7b94b783a4" />
<br><br>

Проверим
```console
vagrant up
```

Установим ansible

```console
sudo apt update
sudo apt install -y ansible
ansible --version
```

Создадим директорию в проекте для ansible и ролей

```console
mkdir ~/yandex_practicum/ansible/
mkdir ~/yandex_practicum/ansible/roles
cd ~/yandex_practicum/ansible/
```

И создадим динамический inventory для ansible

```console
code inventory.py
```
Скрипт отправляет команду vagrant ssh-config с названием каждой VM. Полученный ответ от Vagrant скрипт раскладывает и заносит в json который сможет понять ansible

<img width="618" height="288" alt="Screenshot From 2026-04-29 09-54-19" src="https://github.com/user-attachments/assets/9bb26a03-33cd-4d17-b8ca-05ad409235a6" />
<br>
<img width="620" height="404" alt="Screenshot From 2026-04-29 09-49-40" src="https://github.com/user-attachments/assets/983af836-a1e0-4819-adf8-c37dd82b156d" />
<br>
<img width="618" height="290" alt="Screenshot From 2026-04-29 09-50-06" src="https://github.com/user-attachments/assets/2a0dfb4e-2724-48d8-b872-94160115b002" />
<br><br>
Создадим ansible.cfg

```console
code ansible.cfg
```
<img width="404" height="193" alt="Screenshot From 2026-04-29 09-51-09" src="https://github.com/user-attachments/assets/8e76e52b-a27a-4aee-928e-96af96afa38d" />
<br><br>
И проверим

```console
ansible-inventory --list
ansible all -m ping
```
<img width="494" height="185" alt="Screenshot From 2026-04-29 09-51-45" src="https://github.com/user-attachments/assets/c6fcb809-713d-4d82-9c88-75a201af2a3b" />
<br><br>
Создадим requirements.yml в /ansible для переносимости

```console
code requirements.yml
```
<img width="429" height="150" alt="Screenshot From 2026-04-29 09-52-18" src="https://github.com/user-attachments/assets/6305ea41-a8ab-469f-9388-655e01438696" />
<br><br>

```console
ansible-galaxy collection install -r requirements.yml
```

Вынесим глобальные переменные в отдельную директорию group_vars чтобы не писать их для каждой роли

```console
mkdir group_vars
cd group_vars/
code all.yml
```
<img width="619" height="339" alt="Screenshot From 2026-04-29 10-01-48" src="https://github.com/user-attachments/assets/3fcaf897-d2d7-4b23-a468-8700e5a4222b" />
<br><br>
Создадим роль ansible для настройки DB Primary в /ansible/roles

```console
cd roles/
ansible-galaxy init db_primary
```

db_primary/defaults/main.yml
<br><br>
<img width="355" height="234" alt="Screenshot From 2026-04-29 10-02-52" src="https://github.com/user-attachments/assets/aff21c1d-47f9-4e10-ac03-eaa4ef55053b" />

db_primary/handlers/main.yml
<br><br>
<img width="344" height="201" alt="Screenshot From 2026-04-29 10-03-21" src="https://github.com/user-attachments/assets/b6d93bb4-544b-40fc-b3f1-5f241277b003" />

db_primary/tasks/main.yml
В тасках также будет несколько проверок. Конфиг postgresql.conf не перезаписываем так как будет ломаться кластер, а заменяем отдельные строчки. И после замены конфигов обязательно перезапускаем сервис
<br><br>
<img width="618" height="668" alt="Screenshot From 2026-04-29 10-07-39" src="https://github.com/user-attachments/assets/7986e6f0-b0f4-48f8-8be8-9dbee46aaa35" />
<br>
<img width="489" height="619" alt="Screenshot From 2026-04-29 10-08-08" src="https://github.com/user-attachments/assets/a958dc3a-a7af-4e8d-a951-7019a18324ce" />
<br>
<img width="618" height="432" alt="Screenshot From 2026-04-29 10-08-48" src="https://github.com/user-attachments/assets/78ce8248-df90-437b-8d69-64631289244a" />
<br><br>
db_primary/templates/pg_hba.conf.j2

<img width="618" height="281" alt="Screenshot From 2026-04-29 10-09-35" src="https://github.com/user-attachments/assets/a91ee2d8-b214-4c36-9498-224da1f1bc04" />
<br><br>
Создадим playbook.yml в /ansible и проверим DB primary

```console
code playbook.yml
```

<img width="549" height="238" alt="Screenshot From 2026-04-29 10-10-34" src="https://github.com/user-attachments/assets/3200ddef-863f-4d18-b9e8-838b4922a630" />

```console
ansible-playbook playbook.yml
```

Теперь создадим роль ansible для настройки DB Replica в /ansible/roles

```console
cd roles/
ansible-galaxy init db_replica
```

db_replica/defaults/main.yml
Переменная force_reinit_replica будет отвечать за pg_basebackup при повторных вызовах плейбука. Чтобы каждый раз не копировать БД если реплика уже настроена
<br><br>
<img width="616" height="262" alt="Screenshot From 2026-04-29 10-12-39" src="https://github.com/user-attachments/assets/4cad7268-0ecf-4bf2-a860-2139cb3a1598" />
<br><br>
db_replica/handlers/main.yml
<br><br>
<img width="338" height="202" alt="Screenshot From 2026-04-29 10-13-52" src="https://github.com/user-attachments/assets/2160a01d-b098-44e8-9f29-1ca75b359d33" />
<br><br>
db_replica/tasks/main.yml
<br><br>
<img width="617" height="605" alt="Screenshot From 2026-04-29 10-15-53" src="https://github.com/user-attachments/assets/c3960455-33f7-4859-b3a7-ef41dbfadd96" />
<br><br>
<img width="618" height="618" alt="Screenshot From 2026-04-29 10-16-21" src="https://github.com/user-attachments/assets/6115e291-1f92-4810-85f1-646b9fdec8d7" />
<br><br>
<img width="616" height="600" alt="Screenshot From 2026-04-29 10-18-30" src="https://github.com/user-attachments/assets/e7bf721c-3914-4056-80b3-62f0afe3e6d3" />
<br><br>
<img width="617" height="423" alt="Screenshot From 2026-04-29 10-18-57" src="https://github.com/user-attachments/assets/d218d1a8-ff2d-4e30-ba31-6d2158dc9cc0" />
<br><br>
Обновим playbook.yml в /ansible и проверим DB replica

```console
code playbook.yml
```

<img width="217" height="166" alt="Screenshot From 2026-04-29 10-19-58" src="https://github.com/user-attachments/assets/2ddd79b1-0d1c-4f18-b49c-6227ea709c92" />

```console
ansible-playbook playbook.yml
```

Проверим, на db_primary выполнив команду

<img width="598" height="133" alt="Screenshot From 2026-04-29 10-20-49" src="https://github.com/user-attachments/assets/87521a20-7f04-4125-bd5a-aede403943dc" />
<br><br>
Теперь создадим VM для приложения MediaWiki, добавив в config.json две VM

```console
code config.json
```

<img width="310" height="330" alt="Screenshot From 2026-04-29 10-21-49" src="https://github.com/user-attachments/assets/366a4f4f-08bf-4057-80c3-a2370d36ef69" />
<br><br>
Создадим роль для первого хоста MediaWiki где будут происходить все настройки

```console
ansible-galaxy init mediawiki_1
```

Обновим all.yml в group_vars
<br><br>
<img width="617" height="111" alt="Screenshot From 2026-04-29 10-27-17" src="https://github.com/user-attachments/assets/b4819170-e112-416d-9e2d-d1996995e534" />
<br><br>
<img width="238" height="312" alt="Screenshot From 2026-04-29 10-27-38" src="https://github.com/user-attachments/assets/a8efc6c4-4dc6-4133-ad31-0cf8f7aeed79" />
<br><br>
mediawiki_1/defaults/main.yml
<br><br>
<img width="617" height="367" alt="Screenshot From 2026-04-29 10-28-24" src="https://github.com/user-attachments/assets/e54f5bd1-0ac3-485c-aba1-c36494d9ccfc" />
<br><br>
mediawiki_1/handlers/main.yml
<br><br>
<img width="352" height="294" alt="Screenshot From 2026-04-29 10-29-01" src="https://github.com/user-attachments/assets/f3ca0272-a915-40f2-a863-a2c3009b55fd" />
<br><br>
mediawiki_1/templates/mediawiki.nginx.conf.j2
<br><br>
<img width="617" height="638" alt="Screenshot From 2026-04-29 10-30-00" src="https://github.com/user-attachments/assets/4acd3646-bc2e-4b18-9fda-99fa2d6a76da" />
<br><br>
mediawiki_1/tasks/main.yml
<br><br>
<img width="407" height="672" alt="Screenshot From 2026-04-29 12-37-25" src="https://github.com/user-attachments/assets/b3be2808-e242-4af4-a10d-54cf4bf597e4" />
<br><br>
<img width="503" height="697" alt="Screenshot From 2026-04-29 12-38-09" src="https://github.com/user-attachments/assets/d4a1735f-4ea7-44ee-9d07-c9cf050c0414" />
<br><br>
<img width="678" height="621" alt="Screenshot From 2026-04-29 12-38-42" src="https://github.com/user-attachments/assets/0dbfdd27-6bdb-4409-b805-d8e63fde65a3" />
<br><br>
<img width="739" height="462" alt="Screenshot From 2026-04-29 12-39-28" src="https://github.com/user-attachments/assets/2d1da3b4-62ba-4a7e-b0a0-d628df13171d" />
<br><br>
Также нужно обновить pg_hba.conf для роли db_primary чтобы MediaWiki хост мог подключаться к БД
<br><br>
<img width="617" height="163" alt="Screenshot From 2026-04-29 12-40-28" src="https://github.com/user-attachments/assets/9ac55b4e-8397-41cb-b408-beaefe3aa157" />
<br><br>
Обновим плейбук и проверим
<br><br>
<img width="241" height="194" alt="Screenshot From 2026-04-29 12-41-01" src="https://github.com/user-attachments/assets/4130522d-ce49-4acd-804c-acae73d70ddc" />
<br><br>
<img width="619" height="286" alt="Screenshot From 2026-04-29 12-41-24" src="https://github.com/user-attachments/assets/bf08100f-675d-4c4e-aee7-f8bf73343893" />
<br><br>
Теперь создадим роль для второго хоста MediaWiki. Туда будут импортированы настройки сервиса с первого хоста

```console
ansible-galaxy init mediawiki_2
```

mediawiki_2/defaults/main.yml
<br><br>
<img width="619" height="286" alt="Screenshot From 2026-04-29 12-42-38" src="https://github.com/user-attachments/assets/23344351-73d6-47ea-bb04-83f939623115" />
<br><br>
mediawiki_2/handlers/main.yml
<br><br>
<img width="361" height="299" alt="Screenshot From 2026-04-29 12-43-18" src="https://github.com/user-attachments/assets/566aff9a-8841-4fb0-8b66-a871aad39b10" />
<br><br>
mediawiki_2/templates/mediawiki.nginx.conf.j2
<br><br>
<img width="612" height="669" alt="Screenshot From 2026-04-29 12-43-49" src="https://github.com/user-attachments/assets/82306474-6b60-4f60-8d56-0bb9d634d831" />
<br><br>
mediawiki_2/tasks/main.yml<br>
Будет похоже на таски с mediawiki_1 но без установки MediaWiki. Конфиг с настройками LocalSettings.php будет просто копироваться
<br><br>
<img width="485" height="680" alt="Screenshot From 2026-04-29 12-44-33" src="https://github.com/user-attachments/assets/c43cf9a7-9155-4891-8642-fcec0a1011b0" />
<br><br>
<img width="506" height="691" alt="Screenshot From 2026-04-29 12-44-56" src="https://github.com/user-attachments/assets/2685be31-0fc5-4e1f-87c9-25c03f66ea3b" />
<br><br>
<img width="612" height="430" alt="Screenshot From 2026-04-29 12-45-21" src="https://github.com/user-attachments/assets/9722e786-b296-401f-aa8b-da46289bb7fc" />
<br><br>
<img width="548" height="504" alt="Screenshot From 2026-04-29 12-45-54" src="https://github.com/user-attachments/assets/5e542097-5c5c-4ed8-bed5-389e682fc93e" />
<br><br>
Обновим плейбук и проверим
<br><br>
<img width="252" height="189" alt="Screenshot From 2026-04-29 12-46-29" src="https://github.com/user-attachments/assets/edebd84c-cb1a-4d17-a7c2-4e66385995ce" />
<br><br>
Сейчас mediawiki_2 будет редиректить на mediawiki_1, так как в LocalSetting.php в качестве сервера указан именно mediawiki_1 и эти настройки скопированы на mediawiki_2. После настройки балансировщика указать надо будет именно его

Добавим VM балансировщика в config.json

<img width="367" height="195" alt="Screenshot From 2026-04-29 12-50-59" src="https://github.com/user-attachments/assets/a3be3666-febb-4b10-9468-1f4f036cc6d5" />
<br><br>
Теперь создадим роль для балансировщика нагрузки на nginx который будет редиректить на mediawiki_1 или mediawiki_2

```console
ansible-galaxy init nginx_lb
```

nginx_lb/defaults/main.yml
<br><br>
<img width="431" height="187" alt="Screenshot From 2026-04-29 12-52-04" src="https://github.com/user-attachments/assets/4a71ed08-e5f8-4b15-856e-10f6c6b88749" />
<br><br>
nginx_lb/handlers/main.yml
<br><br>
<img width="313" height="201" alt="Screenshot From 2026-04-29 12-52-38" src="https://github.com/user-attachments/assets/d6c76fc5-44b1-4c38-b43b-77df180fdcaa" />
<br><br>
nginx_lb/templates/mediawiki-lb.conf.j2
<br><br>
<img width="615" height="477" alt="Screenshot From 2026-04-29 12-53-15" src="https://github.com/user-attachments/assets/4c03258b-2c66-4244-a92c-1d13a3efede3" />
<br><br>
nginx_lb/tasks/main.yml
<br><br>
<img width="587" height="710" alt="Screenshot From 2026-04-29 12-54-00" src="https://github.com/user-attachments/assets/cd0abe71-2930-431f-bb4e-97db6c749f07" />
<br><br>
<img width="520" height="732" alt="Screenshot From 2026-04-29 12-54-27" src="https://github.com/user-attachments/assets/a34d0e91-dfdd-43d8-bfd6-e69d0f57975b" />
<br><br>
Обновим плейбук
<br><br>
<img width="201" height="155" alt="Screenshot From 2026-04-29 12-55-34" src="https://github.com/user-attachments/assets/e8aea3f7-9162-477e-ab31-7561a004baec" />
<br><br>
Также нужно изменить адрес сервера MediaWiki на адрес балансировщика в mediawiki_1/defaults/main.yml

```console
mediawiki_server_url: "http://{{ hostvars[groups['nginx_lb'][0]].private_ip }}"
```

Проверки для ролей mediawiki_1 и mediawiki_2 также придется переделать чтобы не падал плейбук
<img width="531" height="310" alt="Screenshot From 2026-04-29 12-58-12" src="https://github.com/user-attachments/assets/c4978b64-8623-4bea-830a-b398d4a2ebd0" />

И проверим пересоздав всю инфраструктуру и заново запустив плейбук, так как в тасках нет перезаписи LocalSettings.php в случае изменения каких то параметров

```console
vagrant destroy
vagrant up
ansible-playbook playbook.ym
```

<img width="619" height="255" alt="Screenshot From 2026-04-29 12-58-59" src="https://github.com/user-attachments/assets/ac3832b4-5faa-4d05-b575-2fa5cbe09020" />

Проверим балансировку нагрузки<br>
На mediawiki-1

```console
echo "mediawiki-1" | sudo tee /var/www/mediawiki/node.txt
```

На mediawiki-2

```console
echo "mediawiki-2" | sudo tee /var/www/mediawiki/node.txt
```

<img width="619" height="141" alt="Screenshot From 2026-04-29 13-00-01" src="https://github.com/user-attachments/assets/c35aeae1-4ad4-4d32-8d3c-20e10d1f91cd" />
<br><br>
Теперь создадим VM где будут бэкапы для файловой системы приложения и базы данных<br>
Добавим VM для бэкапов в config.json
<br><br>
<img width="304" height="183" alt="Screenshot From 2026-04-29 13-00-48" src="https://github.com/user-attachments/assets/16d61900-395b-43de-8cb7-719813aa773a" />
<br><br>
И создадим роль backup для настройки

```console
ansible-galaxy init backup
```

Обновим group_vars/all.yml
<br><br>
<img width="211" height="115" alt="Screenshot From 2026-04-29 13-01-34" src="https://github.com/user-attachments/assets/eabd080e-9e4f-45d9-a00c-35a0048460d3" />
<br><br>
backup/defaults/main.yml
<br><br>
<img width="601" height="626" alt="Screenshot From 2026-04-29 13-02-23" src="https://github.com/user-attachments/assets/50cf723b-9cb6-4f9d-8b36-351dba09043a" />
<br><br>
backup/templates/backup_db.sh.j2
<br><br>
<img width="612" height="513" alt="Screenshot From 2026-04-29 13-02-58" src="https://github.com/user-attachments/assets/41de3b7b-60ec-4bdc-9fd0-eab9786afc00" />
<br><br>
backup/templates/backup_mediawiki_fs.sh.j2
<br><br>
<img width="612" height="592" alt="Screenshot From 2026-04-29 13-03-33" src="https://github.com/user-attachments/assets/b74d87f1-2d16-4351-a272-9bb09a9d5c81" />
<br><br>
backup/tasks/main.yml
<br><br>
<img width="617" height="722" alt="Screenshot From 2026-04-30 11-46-22" src="https://github.com/user-attachments/assets/97d81531-82d9-4d59-8447-83a739bf1459" />
<br><br>
<img width="518" height="747" alt="Screenshot From 2026-04-30 11-47-07" src="https://github.com/user-attachments/assets/b699f6a5-9f60-489d-97ed-4e681fb450af" />
<br><br>
<img width="614" height="472" alt="Screenshot From 2026-04-30 11-47-43" src="https://github.com/user-attachments/assets/79a18b52-447b-43b0-a41a-dd0261bc8726" />
<br><br>
И обновим плейбук
<br><br>
<img width="186" height="147" alt="Screenshot From 2026-04-30 11-48-19" src="https://github.com/user-attachments/assets/9a0013e3-37b9-4bfb-ab31-a75093ab8746" />
<br><br>
Проверим

```console
ls -lh /srv/backups/postgresql/
ls -lh /srv/backups/mediawiki/
sudo crontab -l
```

<img width="680" height="211" alt="Screenshot From 2026-04-30 11-51-04" src="https://github.com/user-attachments/assets/cc415d91-c5b1-4e4c-9563-a2c14ab83c00" />
<br><br>
Теперь создадим VM для мониторинга где будет Zabbix<br>
Добавим VM в конфиг файл. Нужно дать больше памяти чтобы не было ошибки при импорте схемы PostgreSQL
<br><br>
<img width="449" height="197" alt="Screenshot From 2026-04-30 11-51-54" src="https://github.com/user-attachments/assets/3b5441ee-eba4-4c4a-aa96-296a287af07f" />

И создадим роль

```console
ansible-galaxy init zabbix
```

Обновим requirements.yml для Zabbix
<br><br>
<img width="362" height="209" alt="Screenshot From 2026-04-30 11-52-42" src="https://github.com/user-attachments/assets/b408cbc7-a5e8-41ac-ac36-6d0091eb2834" />

И модуль community.zabbix

```console
ansible-galaxy collection install community.zabbix --upgrade
```

Обновим group_vars/all.yml
<br><br>
<img width="290" height="507" alt="Screenshot From 2026-04-30 11-53-35" src="https://github.com/user-attachments/assets/1b808f4a-9520-457c-acc7-8545d44f80d3" />
<br><br>
zabbix/defaults/main.yml
<br><br>
<img width="677" height="562" alt="Screenshot From 2026-04-30 11-54-11" src="https://github.com/user-attachments/assets/bfe1cd0e-5b31-475f-bd1e-c9042de85509" />
<br><br>
<img width="513" height="729" alt="Screenshot From 2026-04-30 11-54-54" src="https://github.com/user-attachments/assets/a3b29432-8b36-4cff-9fbf-13f5b343fa37" />
<br><br>
<img width="616" height="456" alt="Screenshot From 2026-04-30 11-55-32" src="https://github.com/user-attachments/assets/cb0db01e-b8aa-416a-9216-684b98950c2e" />
<br><br>
zabbix/handlers/main.yml
<br><br>
<img width="416" height="483" alt="Screenshot From 2026-04-30 11-56-59" src="https://github.com/user-attachments/assets/fbb35ee5-6bf9-41c6-b075-2d7f20a9c64e" />
<br><br>
zabbix/templates/zabbix.conf.php.j2
<br><br>
<img width="462" height="411" alt="Screenshot From 2026-04-30 11-57-39" src="https://github.com/user-attachments/assets/be2896b6-8802-4e9c-b7ac-8b949cffb582" />
<br><br>
zabbix/templates/zabbix.nginx.conf.j2
<br><br>
<img width="531" height="438" alt="Screenshot From 2026-04-30 11-58-26" src="https://github.com/user-attachments/assets/54c450ec-bf4f-42e1-8e73-ace9d0986ccc" />
<br><br>
zabbix/tasks/main.yml
<br><br>
<img width="864" height="674" alt="Screenshot From 2026-04-30 11-59-13" src="https://github.com/user-attachments/assets/3d15f07e-be86-414c-97ca-9b1b9631e8a4" />
<br><br>
<img width="866" height="746" alt="Screenshot From 2026-04-30 11-59-52" src="https://github.com/user-attachments/assets/11a2e7cb-382b-4b8a-8174-fa11f66551cf" />
<br><br>
<img width="514" height="741" alt="Screenshot From 2026-04-30 12-00-37" src="https://github.com/user-attachments/assets/60626b9b-5d15-4435-969e-099555cad667" />
<br><br>
<img width="501" height="697" alt="Screenshot From 2026-04-30 12-01-08" src="https://github.com/user-attachments/assets/4757711b-1472-4385-b8ef-16eef5944fdd" />
<br><br>
<img width="477" height="515" alt="Screenshot From 2026-04-30 12-02-06" src="https://github.com/user-attachments/assets/40374d77-5980-475d-a44a-2c91d112a01f" />
<br><br>
zabbix/tasks/monitoring.yml
<br><br>
<img width="541" height="767" alt="Screenshot From 2026-04-30 12-03-06" src="https://github.com/user-attachments/assets/d163faf5-83e4-4d53-9b31-31e7c93bd026" />
<br><br>
<img width="661" height="521" alt="Screenshot From 2026-04-30 12-03-49" src="https://github.com/user-attachments/assets/d166ef50-8785-421e-a6c3-606df42ab656" />
<br><br>
<img width="676" height="721" alt="Screenshot From 2026-04-30 12-04-40" src="https://github.com/user-attachments/assets/c2d8098a-6e7b-4988-9ed8-becbf876a843" />
<br><br>
<img width="864" height="676" alt="Screenshot From 2026-04-30 12-07-01" src="https://github.com/user-attachments/assets/a784e690-d1b8-4bd3-83f2-cc4a9c2c4129" />
<br><br>
<img width="868" height="337" alt="Screenshot From 2026-04-30 12-09-26" src="https://github.com/user-attachments/assets/e5906d30-5de1-4356-bce0-84c6cdd5d3dc" />
<br><br>
Обновим плейбук
<br><br>
<img width="274" height="213" alt="Screenshot From 2026-04-30 12-10-02" src="https://github.com/user-attachments/assets/6bf4e4f8-c35e-4269-8c83-53ed4a1bf4d3" />
<br><br>
И проверим
<img width="887" height="306" alt="Screenshot From 2026-04-30 12-10-38" src="https://github.com/user-attachments/assets/fa64c89b-b333-45ff-96eb-6a7c144f9e83" />
<br><br>
<img width="904" height="555" alt="Screenshot From 2026-04-30 12-11-09" src="https://github.com/user-attachments/assets/11f29493-b4a7-4174-a370-05dc2919f43f" />
<br><br>
<img width="887" height="180" alt="Screenshot From 2026-04-30 12-11-31" src="https://github.com/user-attachments/assets/ba071848-f9d5-440b-a820-d9e58c71556b" />
<br><br>
Также для восстановления MediaWiki ноды для роли mediawiki_1 нужно добавить в defaults

```console
mediawiki_run_installer: true
```

И в tasks «Run MediaWiki console installer», «Fail if LocalSettings.php was not created»

```console
when:
    - mediawiki_run_installer | bool
```

И в tasks «Check MediaWiki main page over HTTP», «Check that response contains MediaWiki»

```console
when: final_localsettings.stat.exists
```
