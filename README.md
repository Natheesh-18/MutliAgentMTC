# MTC — Manual Test Case Generation

AI-powered backend that generates structured manual test cases from text prompts, documents, images, videos, Jira tickets, and Figma designs.

The service is a FastAPI app. It stores metadata in MongoDB, embeddings in Qdrant, and session memory in Redis. LLM calls go through a multi-provider client (Groq, OpenAI, Anthropic, Gemini/Vertex).

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill in `.env`, then:

```bash
uvicorn src.main:app --host 0.0.0.0 --port 5000
```

Video preprocessing (`POST /video_upload_preprocess`) returns 202 and publishes to Kafka topic `video-preprocessing`. The Kafka consumer runs in the same API process (background thread). One container / one `uvicorn` or Gunicorn command is enough.

Kafka env vars (PLAINTEXT only):

- `KAFKA_BOOTSTRAP_SERVERS` (required for the consumer to start)
- `KAFKA_VIDEO_TOPIC` (default `video-preprocessing`)
- `KAFKA_VIDEO_PARTITIONS` (default `3`; created or scaled on startup)
- `KAFKA_VIDEO_CONSUMERS` (default `3` in-process subscribe workers, same group)
- `KAFKA_VIDEO_GROUP_ID` (default `mtc-video-worker`)
- `KAFKA_EMBEDDED_CONSUMER` (default `true`; set `false` to disable the in-process consumer)

Docker:

```bash
docker build -t mtc .
docker run --env-file .env -p 5000:5000 mtc
```

The production entry point is `src.main:app` (Gunicorn + Uvicorn workers on port 5000).

## Project layout

```
mtc/
├── src/
│   ├── main.py                 # FastAPI app, CORS, lifespan
│   ├── config.py               # env loading and logging
│   ├── api/                    # routes and shared request deps
│   ├── agents/                 # LangGraph orchestration and prompt library
│   ├── persistence/            # Prompt class, document processor, Mongo writes
│   ├── services/               # chunking, summarization, batch generation
│   ├── integrations/           # Jira, Figma, video, Kafka clients
│   ├── workers/                # Kafka video consumer (started from API lifespan)
│   ├── schemas/                # Pydantic request/response models
│   ├── llm/                    # multi-provider LLM client
│   ├── vector_db/              # retriever helpers
│   ├── preprocessing/          # file partitioning
│   ├── core/                   # errors and generation cancel
│   └── utils/                  # shared helpers
├── certificates/               # TLS material for Mongo/Kafka
├── notebooks/                  # exploratory notebooks
├── archive/                    # unused modules kept for reference
├── docs/
├── requirements.txt
├── pyproject.toml
└── Dockerfile
```

`src.PromptTemp4` remains as a compatibility shim that re-exports `Prompt`. New code should import from `src.persistence.prompt` and run `src.main:app`.

## API groups

- Generation: `/generate-prompt`, `/prompt-to-mtc`, `/stream-generation`, `/terminate-mtc-generation`
- CRUD: update/delete/get prompts and sessions
- Preprocess: `/data-preprocess`, `/delete-chunks`
- Media: image, file, and video MTC endpoints
- Jira: ticket fetch and Jira-to-MTC
- Figma: file process and Figma-to-MTC
- Extras: code generation, Excel download, follow-up queries

## Notes

- Copy `.env.example` to `.env`. Do not commit secrets.
- Unused historical modules live under `archive/`.
- `DefaultFireFlink` at the repo root is a sample FireFlink module fixture.
