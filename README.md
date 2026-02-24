# RAT - Remote Administration Tool

Projet académique de Remote Administration Tool (RAT) développé en Python.
Ce système est composé d'un **serveur** (contrôleur) et d'un **client** (agent) communiquant via une connexion TCP chiffrée TLS.

> ⚠️ Ce projet est réalisé dans un cadre strictement éducatif. Toute utilisation malveillante est interdite.

## Auteurs

- **Horace KOUGBLA** — h.kougbla@myskolae.fr
- **Omar MALIH** — o.malih@myskolae.fr

## Prérequis

- Python >= 3.12
- [Poetry](https://python-poetry.org/) pour la gestion des dépendances
- **Linux** : `portaudio19-dev` (nécessaire pour PyAudio)
  ```bash
  sudo apt install portaudio19-dev
  ```
- **Windows** : aucun prérequis système supplémentaire

## Installation

```bash
# Cloner le dépôt
git clone <url-du-repo>
cd rat-project

# Installer les dépendances avec Poetry
poetry install
```

## Génération des certificats TLS

Le serveur nécessite un certificat et une clé privée pour le chiffrement TLS.

```bash
mkdir -p certificats
openssl req -x509 -newkey rsa:4096 -keyout certificats/server.key -out certificats/server.crt -days 365 -nodes -subj "/CN=localhost"
```

## Lancement

### Serveur

```bash
poetry run server <host> <port> <certfile> <keyfile>
```

Exemple :

```bash
poetry run server 0.0.0.0 4443 certificats/server.crt certificats/server.key
```

### Client (Agent)

```bash
poetry run client <server_host> <server_port>
```

Exemple :

```bash
poetry run client 127.0.0.1 4443
```

## Commandes disponibles

### Commandes serveur (console interactive)

| Commande | Description |
|---|---|
| `help` | Affiche la liste des commandes disponibles |
| `sessions` | Liste les agents connectés |
| `use <id>` | Sélectionne un agent par son identifiant |
| `exit` | Arrête le serveur |

### Commandes envoyées à l'agent

| Commande | Description |
|---|---|
| `help` | Affiche les commandes disponibles côté agent |
| `download <filepath>` | Télécharge un fichier depuis la machine victime |
| `upload <filepath>` | Envoie un fichier vers la machine victime |
| `shell <port>` | Ouvre un reverse shell interactif (bash/powershell) |
| `ipconfig` | Récupère la configuration réseau de la victime |
| `screenshot` | Prend une capture d'écran de la victime |
| `search <filename>` | Recherche un fichier sur la machine victime |
| `hashdump` | Récupère la base SAM (Windows) ou /etc/shadow (Linux) |
| `keylogger <seconds>` | Enregistre les frappes clavier pendant N secondes |
| `webcam_snapshot` | Prend une photo via la webcam de la victime |
| `webcam_stream <seconds>` | Diffuse le flux webcam en direct pendant N secondes |
| `record_audio <seconds>` | Enregistre l'audio du micro pendant N secondes |

## Architecture du projet

```
rat-project/
├── pyproject.toml                  # Configuration Poetry et dépendances
├── .pre-commit-config.yaml         # Configuration pre-commit (black, flake8, isort)
├── .gitignore
├── README.md
├── src/
│   ├── config.py                   # Configuration globale du logger
│   ├── client/
│   │   ├── main.py                 # Point d'entrée de l'agent
│   │   └── utils/
│   │       ├── client.py           # Classe AgentClient (logique client)
│   │       └── config.py           # Logger client
│   ├── server/
│   │   ├── main.py                 # Point d'entrée du serveur
│   │   └── utils/
│   │       ├── server.py           # Classe TLSServer (logique serveur)
│   │       └── config.py           # Logger serveur
│   └── utils/
│       ├── file_utils.py           # Utilitaires d'envoi/réception de fichiers
│       └── socket_utils.py         # Utilitaires de lecture socket (readline, read_buffer)
├── tests/
│   ├── __init__.py
│   ├── test_socket_utils.py        # Tests unitaires socket_utils
│   └── test_file_utils.py          # Tests unitaires file_utils
└── certificats/                    # Certificats TLS (non versionnés)
    ├── server.crt
    └── server.key
```

## Communication

La communication entre le serveur et l'agent repose sur un protocole texte simple au-dessus de TLS :

- **Commandes** : envoyées sous forme de lignes terminées par `\n`
- **Transfert de fichiers** : protocole `SEND_FILE <filename>\n<size>\n<data>`
- **Affichage de résultats** : protocole `DISPLAY\n<size>\n<data>`
- **Stream webcam** : protocole `FRAME\n<size>\n<data>` suivi de `STREAM_END\n`

## Tests

Les tests unitaires utilisent **pytest** :

```bash
poetry run pytest tests/ -v
```

## Outils de développement

- **Poetry** : gestion des dépendances et packaging
- **pre-commit** : formatage automatique du code (black, isort, flake8)
- **Logger** : utilisation du module `logging` (aucun `print` dans le code)
- **pytest** : tests unitaires

### Installation de pre-commit

```bash
poetry run pre-commit install
```

## Dépendances principales

| Paquet | Usage |
|---|---|
| `cryptography` | Support TLS/SSL |
| `pynput` | Keylogger (capture des frappes clavier) |
| `opencv-python` | Webcam snapshot et stream vidéo |
| `pyaudio` | Enregistrement audio depuis le microphone |

## Compatibilité

| OS | Statut |
|---|---|
| Linux (Ubuntu/Debian) | ✅ Supporté |
| Windows 10/11 | ✅ Supporté |
