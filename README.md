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
<img width="355" height="234" alt="Screenshot From 2026-04-29 10-02-52" src="https://github.com/user-attachments/assets/aff21c1d-47f9-4e10-ac03-eaa4ef55053b" />

db_primary/handlers/main.yml
<img width="344" height="201" alt="Screenshot From 2026-04-29 10-03-21" src="https://github.com/user-attachments/assets/b6d93bb4-544b-40fc-b3f1-5f241277b003" />

db_primary/tasks/main.yml
В тасках также будет несколько проверок. Конфиг postgresql.conf не перезаписываем так как будет ломаться кластер, а заменяем отдельные строчки. И после замены конфигов обязательно перезапускаем сервис
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
<img width="616" height="262" alt="Screenshot From 2026-04-29 10-12-39" src="https://github.com/user-attachments/assets/4cad7268-0ecf-4bf2-a860-2139cb3a1598" />
<br><br>
db_replica/handlers/main.yml
<img width="338" height="202" alt="Screenshot From 2026-04-29 10-13-52" src="https://github.com/user-attachments/assets/2160a01d-b098-44e8-9f29-1ca75b359d33" />
<br><br>
db_replica/tasks/main.yml
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

Создадим роль для первого хоста MediaWiki где будут происходить все настройки

```console
ansible-galaxy init mediawiki_1
```

Обновим all.yml в group_vars
<img width="617" height="111" alt="Screenshot From 2026-04-29 10-27-17" src="https://github.com/user-attachments/assets/b4819170-e112-416d-9e2d-d1996995e534" />
<br><br>
<img width="238" height="312" alt="Screenshot From 2026-04-29 10-27-38" src="https://github.com/user-attachments/assets/a8efc6c4-4dc6-4133-ad31-0cf8f7aeed79" />
<br><br>
mediawiki_1/defaults/main.yml
<img width="617" height="367" alt="Screenshot From 2026-04-29 10-28-24" src="https://github.com/user-attachments/assets/e54f5bd1-0ac3-485c-aba1-c36494d9ccfc" />
<br><br>
mediawiki_1/handlers/main.yml
<img width="352" height="294" alt="Screenshot From 2026-04-29 10-29-01" src="https://github.com/user-attachments/assets/f3ca0272-a915-40f2-a863-a2c3009b55fd" />
<br><br>
mediawiki_1/templates/mediawiki.nginx.conf.j2
<img width="617" height="638" alt="Screenshot From 2026-04-29 10-30-00" src="https://github.com/user-attachments/assets/4acd3646-bc2e-4b18-9fda-99fa2d6a76da" />
<br><br>
mediawiki_1/tasks/main.yml
