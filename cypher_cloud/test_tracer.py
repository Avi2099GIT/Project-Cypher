from cloud.api.assistant.orchestrator.tracer import tracer

tracer.record(
    node="test-node",
    status="OK",
    message="hello tracer",
    extra={"foo": "bar"}
)

print(tracer.to_dict())
print(tracer.summary())
