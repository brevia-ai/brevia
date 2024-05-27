# Asynchronous Jobs

Brevia provides a built-in system to handle asynchronous jobs that can be particulary useful when dealing with long running tasks.

Internally these jobs are persistend in the `async_jobs` table (see [database](database.md) for more details), while the background processes are handled using [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/).

Asynchronous jobs are used internally in analysis endpoints like [`/upload_summarize`](endpoints_overview.md#post-upload_summarize) and [`/upload_analyze`](endpoints_overview.md#post-upload_analyze) where files are uploaded and analyzed using built-in or custom [services](analyze_services.md).

These endpoints will simply return a job id as response like this:

```json
{"job": "7ca33644-5ddb-4747-84c0-8818715a65f8"}
```

After that you can check the async job status calling [`GET /jobs/uuid`](endpoints_overview.md#get-jobsuuid) and retrieve the job results as it ends.
