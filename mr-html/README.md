# mr-html (pure frontend demo)

Static HTML/CSS/Vanilla JS client for a mcprpc-style Registry + Router setup, using fetch streaming.

## Run

```bash
cd /home/valenti/mcprpc/mr-html
./run.sh
```

Open:

- http://127.0.0.1:8386/

## Connect to registry + router

Set these fields in the header:

- **Registry URL** (example: `http://localhost:7000`) used for tool discovery via `GET /functions`
- **Router URL** (example: `http://localhost:7010`) used for invocation via `POST /call`

## Troubleshooting

If you see `OSError: [Errno 98] Address already in use`, something is already listening on port 8386.

Try:

```bash
pgrep -af 'http\.server 8386'
pkill -f 'http\.server 8386'
```

If `ss` is available and you have sudo:

```bash
sudo ss -ltnp '( sport = :8386 )'
```

Cross-origin note: if the registry/router are on different ports than this static server, they must enable CORS for browser requests.
