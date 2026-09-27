# Scheduler

The `ROLE=scheduler` entrypoint (`main.py`): a fixed-interval timer, nothing
more. Every `settings.scheduler_interval_seconds`, it calls the Data
Service's `EnqueueDuePatients` RPC with `settings.effective_as_of_date()` and
logs how many patients got enqueued. A plain `while True: call, sleep` loop —
one fixed interval doesn't need a cron-expression scheduler.

No MySQL, no Kafka — just one gRPC call per tick.

## Running the tests

```
python -m pytest services/scheduler/tests -v
```

The one test mocks the gRPC stub and `time.sleep` (so it doesn't actually
wait, and stops after one iteration) and checks the request carries the
right `as_of_date` and that it sleeps for `scheduler_interval_seconds`
between ticks. No live Data Service needed.

Importing `main.py` pulls in the generated `libs/common/grpc_gen` stubs,
which need `protobuf>=5.28`. See `../engine/README.md` for the throwaway-venv
recipe if the host's Python doesn't have a current enough `protobuf`.
