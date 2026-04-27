#!/usr/bin/env python3
import json, subprocess, os, sys

# Поиск конфиг файла на уровне выше
CONFIG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../config.json"))

# Если находим файл то парсим
try:
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    print(f"Error: Config file {CONFIG_FILE} not found", file=sys.stderr)
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"Error: Failed to parse config.json: {e}", file=sys.stderr)
    sys.exit(1)

# Поиск директории с Vagrantfile и смена текущей рабочей директории на неё для выполнения команды ниже
VAGRANT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../vagrant"))
os.chdir(VAGRANT_DIR)

# Выполняем команду vagrant ssh-config для получения конфигурации по каждой ВМ
def get_vm_ssh_config(vm):
    try:
        out = subprocess.check_output(["vagrant", "ssh-config", vm], text=True, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print(f"Warning: failed to get ssh-config for {vm}", file=sys.stderr)
        return {}
    
    # Парсим вывод команды vagrant ssh-config
    host_config = {}
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        key, value = parts
        value = value.strip('"')
        
        # Преобразовываем в понятные для ansible параметры
        if key == "HostName":
            host_config["ansible_host"] = value
        elif key == "User":
            host_config["ansible_user"] = value
        elif key == "IdentityFile":
            host_config["ansible_ssh_private_key_file"] = value
        elif key == "Port":
            host_config["ansible_port"] = int(value)

    host_config.setdefault("ansible_python_interpreter", "/usr/bin/python3")
    return host_config

# Формируем пустой inventory который поймет ansible
inventory = {"_meta": {"hostvars": {}}}

# Заполняем inventory параметрами из конфиг файла разделяя их по ролям
# Роль ansible будет равна группе хостов, поэтому role
for vm_name, vm_config in config['vms'].items():
    role = vm_config['role']
    inventory.setdefault(role, {"hosts": []})
    host_config = get_vm_ssh_config(vm_name)
    if host_config:
        host_config["private_ip"] = vm_config.get("ip")
        inventory[role]["hosts"].append(vm_name)
        inventory["_meta"]["hostvars"][vm_name] = host_config

print(json.dumps(inventory, indent=2))
