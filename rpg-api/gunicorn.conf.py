bind = "0.0.0.0:5000"
workers = 1
threads = 4
worker_tmp_dir = "/dev/shm"  # nosec B108 - /dev/shm est propre au conteneur, gunicorn y crée des fichiers à nom aléatoire (recommandation officielle pour Docker)
control_socket_disable = True


def post_worker_init(worker):
    from prometheus_client import start_http_server
    from app import init_db

    init_db()
    start_http_server(9100)
